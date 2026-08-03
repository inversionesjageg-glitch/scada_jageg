# BackEnd/app/config.py
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    # Variables globales y de seguridad
    PROJECT_NAME: str = "JAGEG - Sistema Produccion"
    SECRET_KEY: str
    ENCRYPTION_KEY: str

    # Base de Datos Administrativa/Histórica (PostgreSQL)
    POSTGRES_SERVER: str
    POSTGRES_USER: str
    POSTGRES_PASSWORD: str
    POSTGRES_DB: str
    POSTGRES_PORT: int = 5433

    # Infraestructura Siemens S7 (Campos en mayúsculas coincidiendo con tu .env)
    PLC_IP: str = "192.168.2.230"
    PLC_RACK: int = 0
    PLC_SLOT: int = 2
    PLC_DB_S1: int = 2
    
    # ponlo en False en tu .env mientras terminan de sanear las direcciones.
    ENABLE_SCADA_LOGGER: bool = True
    
    #Zona horaria
    APP_TIMEZONE: str = "UTC"

    # Construcción dinámica de la URL asíncrona para SQLAlchemy/Postgres
    @property
    def DATABASE_URL(self) -> str:
        return f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}@{self.POSTGRES_SERVER}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"

    # Configuración del motor de Pydantic Settings
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",          # Ignora variables de entorno extras del sistema operativo
        case_sensitive=True      # Fuerza a emparejar mayúsculas/minúsculas exactamente como tu .env
    )

settings = Settings()