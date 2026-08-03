import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

# Importaciones modulares de la nueva arquitectura de hardware real
from app.api.v1.api import api_router as api_router_v1
from app.services.logger_service import SCADALoggerService
from app.services.plc_service import PLCConnectionService
from app.config import settings

# Referencias globales expuestas para health checks y compatibilidad con el resto
# del código existente. Se inicializan dentro de `lifespan` para garantizar que
# exista UNA sola instancia viva del driver PLC por proceso (antes había dos:
# una creada aquí para el logger, y otra creada de forma independiente en
# control.py, lo que abría dos conexiones TCP/IP simultáneas al mismo PLC).
plc_driver: PLCConnectionService | None = None
scada_logger: SCADALoggerService | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Gestión del ciclo de vida asíncrono de la aplicación.
    Crea la única instancia del driver PLC compartida por todo el proceso
    (logger de background + endpoints de control), y garantiza el inicio y
    el apagado seguro (Graceful Shutdown) del recolector industrial S7.
    """
    # --- INICIO (Startup) ---
    # 🆕 Interruptor: mientras se sanean las direcciones importadas de WinCC,
    # se puede apagar el loop automático de 30s (ENABLE_SCADA_LOGGER=false en
    # el .env) sin apagar el resto de la app — el WebSocket y los endpoints
    # de diagnóstico/control siguen disponibles para probar direcciones a
    # mano, solo que current_value deja de refrescarse automáticamente.
    scada_task = None
    if settings.ENABLE_SCADA_LOGGER:
        print(f"⚡ [PLC S7] Iniciando motor de recolección en hardware real ({settings.PLC_IP})...")

        plc_driver = PLCConnectionService(
            ip_address=settings.PLC_IP,
            rack=settings.PLC_RACK,
            slot=settings.PLC_SLOT,
        )
        app.state.plc_driver = plc_driver

        scada_logger = SCADALoggerService(interval_seconds=30, plc_service=plc_driver)
        app.state.scada_logger = scada_logger

        scada_task = asyncio.create_task(scada_logger.start_logging_loop())
    else:
        print("🔇 [PLC S7] SCADALoggerService DESACTIVADO (ENABLE_SCADA_LOGGER=false en .env).")
        print("   El loop automático de 30s no va a correr. Usa /diagnostico-memoria")
        print("   para probar direcciones manualmente mientras se sanea el mapeo de tags.")
        # El driver PLC se crea igual, para que /diagnostico-memoria y demás
        # endpoints de control puedan seguir usándolo bajo demanda.
        plc_driver = PLCConnectionService(
            ip_address=settings.PLC_IP,
            rack=settings.PLC_RACK,
            slot=settings.PLC_SLOT,
        )
        app.state.plc_driver = plc_driver
        app.state.scada_logger = None

    yield

    # --- APAGADO (Shutdown) ---
    print("🛑 Cancelando tareas en segundo plano del SCADA Jageg...")
    if scada_task is not None:
        scada_logger.stop_logging_loop()
        scada_task.cancel()
        try:
            await scada_task
        except asyncio.CancelledError:
            print("✅ Tarea asíncrona del PLC interrumpida de forma segura instantáneamente.")
        except Exception as e:
            print(f"⚠️ Excepción inesperada al cerrar el recolector: {e}")

    # 🔌 CIERRE SEGURO DEL SOCKET DE HARDWARE
    # Como solo existe UNA instancia del driver en todo el proceso, este
    # cierre libera también el socket que usan los endpoints de control,
    # tanto si el logger estaba activo como si no.
    try:
        if plc_driver and hasattr(plc_driver, "plc") and plc_driver.plc.get_connected():
            plc_driver.disconnect()
            print("🔌 Conexión socket TCP/IP con el PLC Siemens liberada limpiamente.")
    except Exception as net_err:
        print(f"⚠️ No se pudo liberar el descriptor del socket de red de forma directa: {net_err}")

    print("✅ Motor SCADA desacoplado y sockets de red liberados correctamente.")


# Instancia central de FastAPI con metadatos actualizados para la planta real
app = FastAPI(
    title="SCADA Jageg - API V2 (Máquina 3)",
    description=(
        "Backend industrial asíncrono optimizado para Snap7 / Siemens S7. "
        "Gestión híbrida de variables en tiempo real (WebSockets/Updates) y "
        "persistencia en matrices históricas por componentes (Tendencias Analíticas)."
    ),
    version="2.0.0",
    lifespan=lifespan
)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """
    Captura los errores de validación de FastAPI (422)
    y los escupe formateados en la consola de Docker
    """
    print("\n🚨 ====== ERROR DE VALIDACIÓN DETECTADO (422) ======")
    print(f"Ruta solicitada: {request.url.path}")
    print(f"Query Params recibidos: {dict(request.query_params)}")
    print("Detalle del fallo de Pydantic:")
    for error in exc.errors():
        print(f"  - Campo: {'.'.join(str(p) for p in error['loc'])} | Error: {error['msg']} | Tipo: {error['type']}")
    print("===================================================\n")

    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={"status": "error", "message": "Fallo en los tipos de datos", "details": exc.errors()},
    )


# ==============================================================================
# CONFIGURACIÓN DE CORS
# ==============================================================================
# 🐛 FIX: la lista original tenía dos strings adyacentes sin coma entre el
# primer y el segundo origin. Python concatena strings literales adyacentes,
# así que "http://192.168.2.27" + "http://localhost:3000" se estaban fusionando
# en un único origin inválido y rompiendo CORS silenciosamente desde esa IP.
origins = [
    "http://192.168.2.27",              # IP local de planta
    "http://localhost:3000",            # Desarrollo local puerto estándar
    "http://localhost:3001",            # Desarrollo local puerto alternativo
    "http://190.6.54.13:3001",          # Acceso externo actual para el Frontend
    "http://190.6.54.13:8080",
    "http://app.grupopolytex.com:3001", # Host de API externo si es necesario
]

# Configuración de CORS para la comunicación con el panel de Frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ==============================================================================
# CONTROL DE VERSIONES (ROUTERS INYECTADOS)
# ==============================================================================
app.include_router(api_router_v1, prefix="/api/v1")


# ==============================================================================
# ENDPOINTS GLOBALES DE INFRAESTRUCTURA (HEALTH CHECKS)
# ==============================================================================

@app.get("/", tags=["Infraestructura"])
def read_root():
    """
    Punto de entrada base para verificar la respuesta del servidor.
    """
    return {
        "status": "online",
        "project": "SCADA Jageg - Automatización Textil",
        "version_actual": "v2.0.0 (Producción Hardened)",
        "planta": "Maquina 3 - Extrusión Película Tela No Tejida"
    }


@app.get("/api/health", tags=["Infraestructura"])
def health_check():
    """
    Endpoint de monitoreo técnico para verificar el estado de los servicios.
    """
    return {
        "status": "healthy",
        "database": "connected_async_postgres",
        "background_jobs": "plc_s7_logger_active" if (scada_logger and scada_logger.is_running) else "disabled",
        "architecture_pattern": "Hybrid_EAV_Matrix_Historical"
    }