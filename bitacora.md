Markdown
# 📔 BITÁCORA TÉCNICA: CONFIGURACIÓN DE ENTORNO ASYNC
**Proyecto:** SCADA API Server (FastAPI + Alembic + PostGIS en Docker)  
**Fecha de última revisión:** Junio 2026  

---


## 📌 PARTE 1: RESOLUCIÓN DE RED Y CONEXIÓN DNS EN DOCKER

### 1. Diagnóstico del Problema de Red
Al levantar la aplicación dentro de un contenedor Docker (`apiserver`) e intentar conectar con una base de datos PostgreSQL externa utilizando un nombre de dominio o DNS local (ej. `midominio.local` o el nombre asignado al host físico), el contenedor falla al resolver la ruta. 

**Causa:** Los contenedores dentro de la red por defecto de Docker (`bridge`) manejan un aislamiento de DNS interno y no heredan de forma automática las tablas de resolución de nombres o servidores DNS configurados en el host del sistema operativo o en la red local empresarial.

### 2. Solución 1: Configuración Estática en `alembic.ini`
Para entornos de desarrollo locales o pruebas rápidas, se debe omitir el DNS utilizando directamente la **IP física** del servidor de base de datos. 

> ⚠️ **REGLA DE ORO ASÍNCRONA:** Al trabajar con arquitecturas asíncronas (`asyncio`) en FastAPI/SQLAlchemy, es obligatorio reemplazar el driver síncrono tradicional (`postgresql://`) por el driver asíncrono **`asyncpg`** (`postgresql+asyncpg://`).

* **Configuración Incorrecta (Síncrona y con DNS):**
  `sqlalchemy.url = postgresql://postgres:password@midominio.local:5432/db_scada`
* **Configuración Correcta (Asíncrona y por IP):**
  ```ini
  # alembic.ini
  sqlalchemy.url = postgresql+asyncpg://postgres:tu_password@192.168.1.50:5432/tu_base_datos
3. Solución 2: Enfoque Inyectado para Producción (Variables de Entorno)
Para evitar exponer credenciales en texto plano dentro del archivo .ini, se debe configurar alembic/env.py para interceptar la URL y sobreescribirla dinámicamente en tiempo de ejecución:

Python
# Dentro de alembic/env.py
import os
from alembic import context

config = context.config

# Sobrescribir la URL del archivo .ini si existe la variable de entorno
if os.getenv("DATABASE_URL"):
    config.set_main_option("sqlalchemy.url", os.getenv("DATABASE_URL"))
📌 PARTE 2: EL CONFLICTO ENTRE ALEMBIC AUTOGENERATE Y POSTGIS
1. ¿Por qué Alembic intenta borrar tablas nativas?
El comando alembic revision --autogenerate realiza un proceso de inspección llamado Reflection. Compara de forma estricta el estado físico real de la base de datos PostgreSQL contra los modelos de Python registrados en el objeto Base.metadata.

Cuando la base de datos cuenta con la extensión PostGIS y herramientas como Tiger Geocoder o Topology, se crean automáticamente en el esquema público decenas de tablas auxiliares (ej. zcta5, edges, faces, loader_lookuptables, topology, state_lookup). Al no encontrar estas tablas declaradas en el código de Python de tu aplicación, Alembic asume de forma errónea que las has eliminado del proyecto y genera instrucciones destructivas (op.drop_table()) para borrarlas de PostgreSQL.

2. El fallo de las Listas Negras (Regex)
Intentar excluir estas tablas mediante filtros basados en expresiones regulares (buscando prefijos como tiger_.* o pagc_.*) es ineficiente y propenso a errores. PostGIS genera tablas de metadatos con nomenclaturas muy variadas que evaden los patrones, haciendo que en cada nueva migración aparezcan comandos drop_table inesperados.

3. La Solución Definitiva: Política de Lista Blanca Estricta
La solución infalible consiste en invertir la lógica: en lugar de decirle a Alembic qué ignorar, se le define una Lista Blanca. Alembic tendrá estrictamente prohibido evaluar cualquier tabla que no comience explícitamente con el prefijo de la aplicación (scada_) o que no sea su propia tabla operativa de control (alembic_version).

📌 PARTE 3: CÓDIGO COMPLETO Y BLINDADO DE alembic/env.py
Reemplaza la totalidad del archivo alembic/env.py con el siguiente código estructurado para entornos asíncronos y protegido con Lista Blanca:

Python
import asyncio
from logging.config import fileConfig
import sys
from os.path import abspath, dirname

from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context

# 1. Forzar a Python a encontrar la raíz de la app antes de las importaciones locales
sys.path.insert(0, dirname(dirname(abspath(__file__))))

# 2. Importación controlada del Metadata y Modelos de la Aplicación
from app.database import Base
from app.models import TagModel, AlarmModel  # IMPORTANTE: Registrar todos los modelos aquí

target_metadata = Base.metadata

# Configuración del pipeline de logs
config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)


# ==============================================================================
# 3. FILTRO EXTENDIDO DE LISTA BLANCA (ESCUDO ANTIPOSTGIS)
# ==============================================================================
def include_object(object, name, type_, reflected, compare_to):
    if type_ == "table":
        # PERMITIR únicamente tablas del núcleo SCADA o el control de Alembic
        if name.startswith("scada_") or name == "alembic_version":
            return True
        else:
            return False  # Ignora y protege en silencio todo lo demás (PostGIS/Nativos)
    return True  
# ==============================================================================


def do_run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection, 
        target_metadata=target_metadata,
        include_object=include_object  # <-- Activación en modo Online
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        include_object=include_object  # <-- Activación en modo Offline
    )

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Ejecución de migraciones en modo online asíncrono."""
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    """Manejador del ciclo de eventos asíncronos para el modo online."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        loop.create_task(run_async_migrations())
    else:
        asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
📌 PARTE 4: FLUJO DE TRABAJO ESTÁNDAR EN LA TERMINAL
Ejecuta estrictamente este orden de comandos en el prompt (root@apiserver:/app#) ante cualquier cambio de base de datos:

Paso 1: Declaración en Código
Crea o modifica tus entidades en app/models.py. Asegúrate de que hereden de la clase Base compartida e importada en env.py.

Paso 2: Generación Automática del Script
Genera el archivo secuencial de migración:

Bash
alembic revision --autogenerate -m "descripcion_de_los_cambios"
Paso 3: Control de Calidad Obligatorio (Auditoría Humana)
Abre el archivo .py creado dentro del directorio alembic/versions/.

Resultado Correcto esperado: Únicamente funciones op.create_table, op.add_column u op.create_index apuntando a objetos con prefijo scada_.

Indicador de Error: Presencia de cualquier instrucción op.drop_table(), op.drop_index() apuntando a tablas del sistema o espaciales.

Acción correctiva inmediata: Si detectas código intruso, elimina el archivo físico .py de la carpeta versions/, no apliques el upgrade y audita la función include_object en env.py.

Paso 4: Impactar la Base de Datos
Una vez verificado que el script está limpio de comandos destructivos, consolida los cambios en PostgreSQL:

Bash
alembic upgrade head
📌 PARTE 5: PLAN DE CONTINGENCIA Y RESPUESTA A ERRORES
Caso A: El script se genera vacío (pass) pero las tablas de la app no existen en la BD

Revisa que las tablas no hayan sido creadas prematuramente por la app al levantar mediante comandos nativos como Base.metadata.create_all(engine). Si es así, elimínalas manualmente con DROP TABLE scada_alarms; DROP TABLE scada_tags; y vuelve a generar la revisión.

Asegúrate de haber importado el modelo explícitamente en el encabezado de env.py. Si el archivo del modelo no se lee, SQLAlchemy no lo carga en la memoria de ejecución y Alembic asumirá que no hay cambios que procesar.

Caso B: Se aplicó un upgrade erróneo o corrupto
Si el script contenía errores pero no llegó a alterar tablas críticas, puedes revertir el último paso apuntando al ID anterior o a la base limpia usando:

Bash
alembic downgrade base
Luego, borra el archivo corrupto de la carpeta de versiones antes de iniciar un nuevo ciclo de autogeneración.