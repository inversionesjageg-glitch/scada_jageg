#!/usr/bin/env bash
#
# reset_and_migrate.sh
# ---------------------------------------------------------------------------
# Reinicia el volumen de Postgres y las migraciones de Alembic del proyecto
# JAGEG-SCADA, y genera un esquema limpio a partir de los modelos actuales
# (incluye plc_area/plc_width en scada_tags). Al final siembra los 1133 tags
# de app/seed/data/tags_wincc_export.json.
#
# Uso:
#   ./reset_and_migrate.sh          # modo interactivo, pide confirmación
#   ./reset_and_migrate.sh --yes    # sin pausas de confirmación (usar con cuidado)
#
# Debe correrse desde la raíz del proyecto (donde está docker-compose.yml).
# ---------------------------------------------------------------------------

set -euo pipefail

AUTO_YES=false
if [[ "${1:-}" == "--yes" ]]; then
    AUTO_YES=true
fi

BACKEND_DIR="./BackEnd"
ENV_FILE="${BACKEND_DIR}/.env"
BACKUP_DIR="./backups"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

log()  { echo -e "\n\033[1;36m▶ $1\033[0m"; }
warn() { echo -e "\033[1;33m⚠ $1\033[0m"; }
err()  { echo -e "\033[1;31m✖ $1\033[0m"; }

confirm() {
    # confirm "mensaje" -> continúa solo si el usuario escribe "si" (o --yes)
    if $AUTO_YES; then
        return 0
    fi
    read -r -p "$1 [escribe 'si' para continuar]: " respuesta
    if [[ "$respuesta" != "si" ]]; then
        err "Cancelado por el usuario. No se hicieron más cambios."
        exit 1
    fi
}

# --- Verificaciones previas -------------------------------------------------
if [[ ! -f "docker-compose.yml" ]]; then
    err "No se encontró docker-compose.yml en el directorio actual."
    err "Corre este script desde la raíz de JAGEG-SCADA."
    exit 1
fi

if [[ ! -f "$ENV_FILE" ]]; then
    err "No se encontró ${ENV_FILE}. Necesario para el backup y las credenciales de Postgres."
    exit 1
fi

# shellcheck disable=SC1090
set -a; source "$ENV_FILE"; set +a

if [[ -z "${POSTGRES_USER:-}" || -z "${POSTGRES_DB:-}" ]]; then
    err "POSTGRES_USER o POSTGRES_DB no están definidos en ${ENV_FILE}."
    exit 1
fi

echo "======================================================================"
echo " JAGEG-SCADA — Reset de volúmenes + migración limpia"
echo "======================================================================"
warn "Esto va a BORRAR el volumen 'scada_data' (todo el histórico de Postgres)"
warn "y todas las migraciones existentes en ${BACKEND_DIR}/alembic/versions/"
echo

# --- Paso 0: Backup ----------------------------------------------------------
log "Paso 0/8 — Backup de la base de datos actual"
if $AUTO_YES; then
    hacer_backup="si"
else
    read -r -p "¿Hacer backup antes de continuar? (muy recomendado) [si/no]: " hacer_backup
fi

if [[ "$hacer_backup" == "si" ]]; then
    if ! docker ps --format '{{.Names}}' | grep -q '^scada_postgres$'; then
        warn "El contenedor scada_postgres no está corriendo. Levantándolo temporalmente..."
        docker-compose up -d db
        sleep 5
    fi
    mkdir -p "$BACKUP_DIR"
    BACKUP_FILE="${BACKUP_DIR}/scada_backup_${TIMESTAMP}.dump"
    log "Generando backup en ${BACKUP_FILE} ..."
    docker exec scada_postgres pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -F c -f /tmp/scada_backup.dump
    docker cp scada_postgres:/tmp/scada_backup.dump "$BACKUP_FILE"
    log "Backup guardado: ${BACKUP_FILE}"
else
    warn "Backup omitido. Si algo sale mal, no habrá forma de recuperar el histórico."
    confirm "¿Confirmas que quieres continuar SIN backup?"
fi

# --- Paso 1: Bajar contenedores y borrar volumen ------------------------------
log "Paso 1/8 — Bajando contenedores y eliminando volúmenes (docker-compose down -v)"
confirm "Esto borra permanentemente el volumen scada_data. ¿Continuar?"
docker-compose down -v

# --- Paso 2: Borrar migraciones anteriores ------------------------------------
log "Paso 2/8 — Eliminando migraciones anteriores"
VERSIONS_DIR="${BACKEND_DIR}/alembic/versions"
if [[ -d "$VERSIONS_DIR" ]]; then
    N=$(find "$VERSIONS_DIR" -name '*.py' | wc -l | tr -d ' ')
    warn "Se eliminarán ${N} archivo(s) de migración en ${VERSIONS_DIR}"
    confirm "¿Continuar con el borrado de migraciones?"
    rm -f "${VERSIONS_DIR}"/*.py
    log "Migraciones eliminadas."
else
    warn "No se encontró ${VERSIONS_DIR}, se omite este paso."
fi

# --- Paso 3: Recordatorio de env.py -------------------------------------------
log "Paso 3/8 — Verificación de alembic/env.py"
ENV_PY="${BACKEND_DIR}/alembic/env.py"
if [[ -f "$ENV_PY" ]]; then
    if grep -q "target_metadata" "$ENV_PY"; then
        log "alembic/env.py encontrado con 'target_metadata'. Revisa manualmente que"
        log "importe TODOS tus módulos de modelos (app.models.scada, app.models.auth, etc.)"
        log "antes de continuar, o el autogenerate no va a ver esas tablas."
    fi
fi
confirm "¿Confirmaste que env.py importa todos los modelos?"

# --- Paso 4: Levantar solo la base de datos -----------------------------------
log "Paso 4/8 — Levantando el contenedor de base de datos"
docker-compose up -d db

log "Esperando a que Postgres esté listo..."
for i in $(seq 1 30); do
    if docker exec scada_postgres pg_isready -U "$POSTGRES_USER" >/dev/null 2>&1; then
        log "Postgres está listo."
        break
    fi
    sleep 1
    if [[ "$i" -eq 30 ]]; then
        err "Postgres no respondió a tiempo. Revisa 'docker-compose logs db'."
        exit 1
    fi
done

# --- Paso 5: Generar migración inicial ----------------------------------------
log "Paso 5/8 — Generando migración inicial (alembic revision --autogenerate)"
docker-compose run --rm backend alembic revision --autogenerate -m "initial_schema"

NEW_MIGRATION=$(find "$VERSIONS_DIR" -name '*.py' | head -n 1)
if [[ -z "$NEW_MIGRATION" ]]; then
    err "No se generó ningún archivo de migración. Revisa el output de Alembic arriba."
    exit 1
fi

echo
warn "Migración generada en: ${NEW_MIGRATION}"
warn "Ábrela y revisa que incluya todas tus tablas (scada_tags con plc_area/plc_width,"
warn "scada_alarms, scada_tag_history, los 6 históricos matriciales, scada_analytics_oee, etc.)"
confirm "¿Revisaste el archivo y quieres aplicarlo?"

# --- Paso 6: Aplicar la migración ---------------------------------------------
log "Paso 6/8 — Aplicando la migración (alembic upgrade head)"
docker-compose run --rm backend alembic upgrade head

# --- Paso 7: Levantar todos los servicios -------------------------------------
log "Paso 7/8 — Levantando todos los servicios"
docker-compose up -d

# --- Paso 8: Seed de tags ------------------------------------------------------
log "Paso 8/8 — Sembrando los 1133 tags (app/seed/tags.py)"
confirm "¿Ejecutar el seed masivo de tags ahora?"
docker-compose exec backend python -m app.seed.tags

echo
echo "======================================================================"
log "Listo. Esquema limpio aplicado y tags sembrados."
if [[ "$hacer_backup" == "si" ]]; then
    log "Backup disponible en: ${BACKUP_FILE}"
fi
echo "======================================================================"