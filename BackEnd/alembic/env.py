import os
import asyncio
from logging.config import fileConfig
import sys
from os.path import abspath, dirname

from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context

# 1. Forzar que Python encuentre la carpeta de la app antes de importar
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# 2. Importar los metadatos reales de tus modelos SCADA
from app.database import Base

from app.models.auth import UserModel, RoleModel, PermissionModel, RolePermissionModel
from app.models.scada import TagModel, AlarmModel, TagHistoryModel,HistoricoExtrusoraS1Model, HistoricoExtrusoraS2Model, HistoricoExtrusoraMeltblownModel,HistoricoProcesoMecanicoModel, HistoricoMotoresVelocidadesModel, HistoricoDosificacionGlobalModel,OEELogModel

# Este es el objeto que Alembic necesita para el --autogenerate
target_metadata = Base.metadata

# Configuración del archivo de logs de Alembic
config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)


# 1. Función de filtrado por LISTA BLANCA
def include_object(object, name, type_, reflected, compare_to):
    if type_ == "table":
        # SOLO procesar tablas del proyecto (scada_) o la de control de Alembic
        if name.startswith("scada_") or name == "alembic_version":
            return True
        else:
            return False
    return True  


# 2. Modifica la función 'do_run_migrations' para inyectar el filtro
def do_run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection, 
        target_metadata=target_metadata,
        include_object=include_object  # <-- Filtro activo en modo online
    )

    with context.begin_transaction():
        context.run_migrations()


# 3. Modifica también 'run_migrations_offline' para que tenga el mismo filtro
def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        include_object=include_object  # <-- Filtro activo en modo offline
    )

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Ejecutar migraciones en modo 'online' asíncrono."""
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    """Ejecutar migraciones en modo 'online'."""
    try:
        # Intentar ejecutar en el bucle asíncrono existente de FastAPI si aplica
        loop = asyncio.get_running_loop()
    except RuntimeError:
        # Si no hay bucle activo, crear uno nuevo
        loop = None

    if loop and loop.is_running():
        # Si ya estamos en una tarea asíncrona
        loop.create_task(run_async_migrations())
    else:
        asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()