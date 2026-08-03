# BackEnd/app/api/v1/endpoints/control.py
import logging
import asyncio
import re
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, or_, and_
from datetime import datetime, timezone
# Importamos las utilidades de conversión nativas de Snap7 para cada tipo de dato
from snap7.util import get_real, get_int, get_bool

from app.database import AsyncSessionLocal
from app.models.scada import TagModel
from app.services.plc_service import PLCConnectionService
from app.infrastructure.plc.dependency import get_plc_driver
from app.config import settings

router = APIRouter()
logger = logging.getLogger("SCADA_Jageg_Control")

# 🆕 Ya NO se instancia un PLCConnectionService propio aquí. Antes esta línea
# creaba una SEGUNDA conexión TCP/IP independiente hacia el mismo PLC que ya
# usa SCADALoggerService en background, lo cual puede agotar el límite de
# conexiones concurrentes que soporta el CPU Siemens S7. Ahora el driver se
# recibe inyectado (misma instancia única creada en el lifespan de main.py)
# a través de `Depends(get_plc_driver)` en cada endpoint que lo necesite.

def parsear_direccion_fisica(direccion: str) -> tuple[str, int | None, int, int | None, str] | None:
    """
    Parsea cadenas S7comm de CUALQUIER área de memoria.
    Retorna: (area, db_number_o_None, offset_byte, bit_number_o_None, formato)
    o None si el formato no se reconoce.

    🆕 Antes solo reconocía direcciones DB.*. Ahora soporta también M, I, Q
    y PIW — aunque PIW se parsea igual (para poder listarlo en el reporte),
    pero `leer_area()` en plc_service.py rechaza explícitamente intentar
    leerlo (ver ese archivo para el porqué).
    """
    if not direccion:
        return None

    d = direccion.strip().upper()

    # --- Área DB ---
    m = re.match(r"^DB(\d+)\.DBD(\d+)$", d)
    if m:
        return "DB", int(m.group(1)), int(m.group(2)), None, "FLOAT"
    m = re.match(r"^DB(\d+)\.DBW(\d+)$", d)
    if m:
        return "DB", int(m.group(1)), int(m.group(2)), None, "INT"
    m = re.match(r"^DB(\d+)\.DBB(\d+)$", d)
    if m:
        return "DB", int(m.group(1)), int(m.group(2)), None, "BYTE"
    m = re.match(r"^DB(\d+)\.DBX(\d+)\.(\d+)$", d)
    if m:
        return "DB", int(m.group(1)), int(m.group(2)), int(m.group(3)), "BOOL"

    # --- Área M (Marcas) ---
    m = re.match(r"^MD(\d+)$", d)
    if m:
        return "M", None, int(m.group(1)), None, "FLOAT"
    m = re.match(r"^MW(\d+)$", d)
    if m:
        return "M", None, int(m.group(1)), None, "INT"
    m = re.match(r"^MB(\d+)$", d)
    if m:
        return "M", None, int(m.group(1)), None, "BYTE"
    m = re.match(r"^M(\d+)\.(\d+)$", d)
    if m:
        return "M", None, int(m.group(1)), int(m.group(2)), "BOOL"

    # --- Áreas I (Entradas) y Q (Salidas) — en el dataset actual, solo bit ---
    m = re.match(r"^I(\d+)\.(\d+)$", d)
    if m:
        return "I", None, int(m.group(1)), int(m.group(2)), "BOOL"
    m = re.match(r"^Q(\d+)\.(\d+)$", d)
    if m:
        return "Q", None, int(m.group(1)), int(m.group(2)), "BOOL"

    # --- PIW (se parsea para poder reportarlo, pero no se puede leer) ---
    m = re.match(r"^PIW(\d+)$", d)
    if m:
        return "PIW", None, int(m.group(1)), None, "INT"

    return None

def analizar_y_sanitizar_lectura(valor_crudo, valor_respaldo, tipo_dato: str) -> tuple[float | int | bool, str, str]:
    """
    Procesa, filtra ruido analógico y sanitiza los límites operacionales de la planta.
    """
    if valor_crudo is None:
        return (valor_respaldo if valor_respaldo is not None else 0.0), "ERROR_LECTURA", "Buffer vacío."

    if tipo_dato == "BOOL":
        return bool(valor_crudo), "OK", "Lectura correcta (Booleano)."

    # Filtros analógicos aplicados únicamente a FLOAT e INT
    abs_val = abs(valor_crudo)
    if tipo_dato == "FLOAT" and abs_val < 1e-4 and valor_crudo != 0.0:
        return 0.0, "OK", "Lectura correcta (Ruido analógico filtrado a 0.0)."

    # Límites lógicos de seguridad industrial para presiones y temperaturas de la Máquina 3
    LIMITE_MAX = 30000.0 if tipo_dato == "INT" else 350.0  # Adaptable según contexto
    if tipo_dato == "FLOAT" and "PRESS" in str(valor_crudo):
        LIMITE_MAX = 400.0

    if float(valor_crudo) > LIMITE_MAX or float(valor_crudo) < -10.0:
        logger.warning(f"Desfase o desalineación en PLC. Valor crudo recibido: {valor_crudo}.")
        if valor_respaldo is None:
            return 0.0 if tipo_dato != "BOOL" else False, "DESALINEADO", "Datos corruptos en PLC. BD purgada a seguro."
        return valor_respaldo, "DESALINEADO", "Mostrando último valor seguro guardado en la base de datos."

    return (round(valor_crudo, 4) if tipo_dato == "FLOAT" else valor_crudo), "OK", "Lectura correcta."


# 🆕 Antes esto era un límite "todo o nada": si la consulta superaba
# MAX_TAGS_SIN_ACOTAR tags, el endpoint rechazaba con 400 y no dejaba
# avanzar. En la práctica, hasta acotando a una sola área (ej. area=DB con
# 502 coincidencias) es fácil superar el límite legítimamente. Ahora es
# un límite de PÁGINA: se pagina con offset/limit en vez de rechazar.
DEFAULT_LIMIT = 60
MAX_LIMIT = 200


@router.get("/diagnostico-memoria", status_code=status.HTTP_200_OK)
async def obtener_diagnostico_memoria(
    plc_service: PLCConnectionService = Depends(get_plc_driver),
    incluir_simulados: bool = False,
    db_min: int | None = None,
    db_max: int | None = None,
    area: str | None = None,
    offset: int = 0,
    limit: int = DEFAULT_LIMIT,
):
    """
    Endpoint de auditoría y diagnóstico dinámico de memoria S7 del PLC físico.

    Por defecto (`incluir_simulados=False`) solo audita los tags con
    `is_simulated=False` — el comportamiento original, para no romper nada
    que ya dependa de esto.

    `incluir_simulados=true` audita TAMBIÉN los tags importados de WinCC
    que hoy están en espera (`is_simulated=True`).

    `db_min` / `db_max` acotan la auditoría a un rango de Data Blocks —
    SOLO afectan tags de área DB; los de área M/I/Q/PIW no tienen número de
    DB y se incluyen siempre salvo que los excluyas con `area`.

    `area` restringe la auditoría a UNA sola área ("DB", "M", "I", "Q" o "PIW").

    🆕 `offset` / `limit` paginan el resultado (`limit` por defecto 60, máximo
    200). La respuesta incluye `paginacion` con el total de coincidencias y
    el `siguiente_offset` para seguir avanzando. El orden es determinista
    (por `tag_id`), así que páginas sucesivas no se solapan ni se saltan tags.
    Ejemplo para barrer 502 tags de área DB en tandas de 100:
      ?incluir_simulados=true&area=DB&limit=100&offset=0
      ?incluir_simulados=true&area=DB&limit=100&offset=100
      ?incluir_simulados=true&area=DB&limit=100&offset=200
      ... hasta que "siguiente_offset" salga null.
    """
    if area is not None and area not in ("DB", "M", "I", "Q", "PIW"):
        raise HTTPException(status_code=400, detail="area debe ser una de: DB, M, I, Q, PIW.")
    if offset < 0:
        raise HTTPException(status_code=400, detail="offset no puede ser negativo.")
    if limit < 1 or limit > MAX_LIMIT:
        raise HTTPException(status_code=400, detail=f"limit debe estar entre 1 y {MAX_LIMIT}.")

    async with AsyncSessionLocal() as session:
        filtros = [TagModel.plc_area != None]
        if not incluir_simulados:
            filtros.append(TagModel.is_simulated == False)
        if area is not None:
            filtros.append(TagModel.plc_area == area)

        # La condición de rango SOLO restringe dentro del área DB (donde
        # plc_db no es NULL). M/I/Q/PIW no tienen número de DB, así que
        # quedan exentos de esta condición y no se filtran por accidente.
        if db_min is not None or db_max is not None:
            condiciones_rango = []
            if db_min is not None:
                condiciones_rango.append(TagModel.plc_db >= db_min)
            if db_max is not None:
                condiciones_rango.append(TagModel.plc_db <= db_max)
            filtros.append(
                or_(TagModel.plc_area != "DB", and_(*condiciones_rango))
            )

        # Orden determinista por tag_id: sin esto, dos llamadas con el mismo
        # offset/limit podrían devolver conjuntos distintos si Postgres decide
        # cambiar el plan de ejecución, y terminarías con tags saltados o
        # duplicados entre páginas.
        result_total = await session.execute(select(TagModel).where(*filtros).order_by(TagModel.id))
        tags_totales = result_total.scalars().all()

    total_coincidencias = len(tags_totales)
    tags_db = tags_totales[offset:offset + limit]
    siguiente_offset = offset + limit if (offset + limit) < total_coincidencias else None

    if not tags_db:
        raise HTTPException(
            status_code=404, 
            detail="No se encontraron tags físicos activos configurados en la base de datos."
        )

    tags_config = []
    tags_piw_no_soportados = []
    mapeo_tags_parsed = {}  # tag.id -> (area, db, byte, bit, formato)

    for tag in tags_db:
        parsed = parsear_direccion_fisica(tag.direccion_fisica)
        if not parsed:
            continue
        area = parsed[0]
        if area == "PIW":
            # No es un fallo de dirección: es un área que Snap7 no puede leer
            # desde un cliente externo. Se reporta aparte, nunca como
            # "dirección inválida en el PLC" (sería un falso positivo).
            tags_piw_no_soportados.append({
                "tag_name": tag.tag_name,
                "direccion": tag.direccion_fisica,
                "motivo": "Área PIW no soportada por el protocolo S7comm para clientes externos.",
            })
            continue
        tags_config.append(tag)
        mapeo_tags_parsed[tag.id] = parsed

    if not tags_config:
        if tags_piw_no_soportados:
            raise HTTPException(
                status_code=422,
                detail={
                    "error": "Todos los tags del rango consultado son de área PIW (no legible por protocolo).",
                    "tags_area_no_soportada": tags_piw_no_soportados,
                },
            )
        raise HTTPException(
            status_code=400,
            detail="Ninguno de los tags activos cuenta con una sintaxis S7comm parseable."
        )

    # 2. Conexión física asíncrona segura con el PLC de la Máquina 3
    conexion_ok = await asyncio.to_thread(plc_service.asegurar_conexion)
    if not conexion_ok:
        raise HTTPException(
            status_code=503, 
            detail=f"Error en comunicación: Sin enlace de red con el PLC en {settings.PLC_IP}"
        )

    # 3. Agrupación por (área, DB) — para M/I/Q no hay número de DB, así que
    #    se agrupan todos juntos dentro de su área (espacio de direcciones
    #    plano, a diferencia de DB que sí está particionado por número).
    grupos = set((mapeo_tags_parsed[tag.id][0], mapeo_tags_parsed[tag.id][1]) for tag in tags_config)
    buffers_grupo = {}
    tags_fallidos = []

    for area, db_num in grupos:
        tags_de_este_grupo = [
            t for t in tags_config
            if mapeo_tags_parsed[t.id][0] == area and mapeo_tags_parsed[t.id][1] == db_num
        ]

        bytes_del_grupo = []
        for tag in tags_de_este_grupo:
            offset = mapeo_tags_parsed[tag.id][2]
            formato = mapeo_tags_parsed[tag.id][4]
            ancho_bytes = {"FLOAT": 4, "INT": 2, "BYTE": 1, "BOOL": 1}.get(formato, 4)
            bytes_del_grupo.append(offset + ancho_bytes)

        max_byte = max(bytes_del_grupo)
        etiqueta_grupo = f"DB{db_num}" if area == "DB" else area

        try:
            buffers_grupo[(area, db_num)] = await asyncio.to_thread(
                plc_service.leer_area, area, 0, max_byte, db_num
            )
        except Exception as e:
            logger.warning(f"La lectura masiva de {etiqueta_grupo} (Tamaño: {max_byte} bytes) falló. Pasando a modo seguro tag por tag.")
            buffers_grupo[(area, db_num)] = bytearray(max_byte)

            for tag in tags_de_este_grupo:
                offset = mapeo_tags_parsed[tag.id][2]
                formato = mapeo_tags_parsed[tag.id][4]
                ancho = {"FLOAT": 4, "INT": 2, "BYTE": 1, "BOOL": 1}.get(formato, 4)

                try:
                    pedazo_buffer = await asyncio.to_thread(
                        plc_service.leer_area, area, 0, offset + ancho, db_num
                    )
                    buffers_grupo[(area, db_num)][offset:offset + ancho] = pedazo_buffer[offset:offset + ancho]
                except Exception as tag_err:
                    logger.error(f"¡DIRECCIÓN INVÁLIDA DETECTADA! El tag '{tag.tag_name}' en la dirección {tag.direccion_fisica} no pudo ser leído: {str(tag_err)}")
                    tags_fallidos.append({
                        "tag_name": tag.tag_name,
                        "direccion": tag.direccion_fisica,
                        "error": "Esta dirección no existe o está fuera de los límites en el PLC físico."
                    })

    if tags_fallidos:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "Se detectaron direcciones físicas inválidas en el PLC real.",
                "tags_inexistentes_en_plc": tags_fallidos,
                "tags_area_no_soportada": tags_piw_no_soportados,
            }
        )
    # --------------------------------------------------------------------------
    # MATRIZ 1: EXTRACCIÓN CONVERGENTE SEGÚN EL TIPO DE DATO REAL
    # --------------------------------------------------------------------------
    analisis_tags = []
    tags_mapeados_por_grupo = {}

    for tag in tags_config:
        area, db_num, offset_byte, bit_num, formato = mapeo_tags_parsed[tag.id]
        clave_grupo = (area, db_num)
        buffer = buffers_grupo.get(clave_grupo)

        valor_final = tag.current_value if tag.current_value is not None else 0.0
        estado_lectura = "OK"
        detalles = "Lectura correcta."

        tags_mapeados_por_grupo.setdefault(clave_grupo, set()).add(offset_byte)

        # Validación estricta de longitudes límites de buffer según el tipo
        ancho_requerido = {"FLOAT": 4, "INT": 2, "BYTE": 1, "BOOL": 1}.get(formato, 4)

        if buffer and (offset_byte + ancho_requerido) <= len(buffer):
            # Extracción tipada nativa
            if formato == "FLOAT":
                valor_crudo = get_real(buffer, offset_byte)
            elif formato == "INT":
                valor_crudo = get_int(buffer, offset_byte)
            elif formato == "BOOL":
                valor_crudo = get_bool(buffer, offset_byte, bit_num)
            elif formato == "BYTE":
                valor_crudo = buffer[offset_byte]  # indexado directo, no requiere snap7.util

            valor_final, estado_lectura, detalles = analizar_y_sanitizar_lectura(valor_crudo, tag.current_value, formato)
        else:
            estado_lectura = "ERROR_BUFFER_CORTO"
            detalles = f"El offset configurado excede las dimensiones físicas asignadas para el tipo {formato}."

        analisis_tags.append({
            "tag_id": tag.id,
            "tag_name": tag.tag_name,
            "descripcion": tag.description,
            "direccion_fisica": tag.direccion_fisica,
            "area": area,
            "tipo_dato": formato,
            "valor_en_bd_actual": tag.current_value,
            "valor_real_plc": valor_final,
            "estado_lectura": estado_lectura,
            "detalles": detalles
        })

    # --------------------------------------------------------------------------
    # MATRIZ 2: ESCANEO DE ESPACIOS LIBRES (EXCLUSIVAMENTE PARA ANALÓGICOS DBD/MD)
    # --------------------------------------------------------------------------
    analisis_huerfanos = []
    for (area, db_num), buffer in buffers_grupo.items():
        if area not in ("DB", "M"):
            # El escaneo de "huérfanos" asume floats alineados a 4 bytes; en
            # I/Q del dataset actual solo hay tags de bit, así que escanear
            # ahí como si fueran floats produciría ruido sin sentido.
            continue

        bytes_registrados = tags_mapeados_por_grupo.get((area, db_num), set())

        for offset in range(0, len(buffer) - 3, 4):
            if offset not in bytes_registrados:
                valor_anonimo_crudo = get_real(buffer, offset)
                valor_anonimo_limpio, estado_huerfano, _ = analizar_y_sanitizar_lectura(valor_anonimo_crudo, 0.0, "FLOAT")
                
                # Reporta si hay algún remanente analógico moviéndose no indexado
                if valor_anonimo_limpio != 0.0 and estado_huerfano == "OK" and abs(valor_anonimo_limpio) < 5000:
                    direccion_str = f"DB{db_num}.DBD{offset}" if area == "DB" else f"MD{offset}"
                    analisis_huerfanos.append({
                        "direccion_fisica": direccion_str,
                        "valor_detectado": valor_anonimo_limpio,
                        "tipo_sugerido": "FLOAT / REAL",
                        "alerta": "Offset con actividad en PLC ignorado por el SCADA."
                    })

    return {
        "timestamp_auditoria": datetime.now(timezone.utc).isoformat(),
        "plc_status": {
            "ip": settings.PLC_IP,
            "status": "CONNECTED"
        },
        "filtro_aplicado": {
            "incluir_simulados": incluir_simulados,
            "db_min": db_min,
            "db_max": db_max,
            "area": area,
        },
        "paginacion": {
            "total_coincidencias": total_coincidencias,
            "offset": offset,
            "limit": limit,
            "devueltos_en_esta_pagina": len(tags_db),
            "siguiente_offset": siguiente_offset,
        },
        "resumen": {
            "total_tags_validados": len(analisis_tags),
            "total_huerfanos_detectados": len(analisis_huerfanos),
            "total_tags_area_no_soportada": len(tags_piw_no_soportados),
        },
        "tags_validados": analisis_tags,
        "tags_area_no_soportada": tags_piw_no_soportados,
        "valores_plc_no_configurados": analisis_huerfanos
    }