# BackEnd/app/api/v1/api.py
from fastapi import APIRouter
from app.api.v1.endpoints import tags
from app.api.v1.endpoints import alarms
from app.api.v1.endpoints import hardware
from app.api.v1.endpoints import analytics
from app.api.v1.endpoints import history
from app.api.v1.endpoints import websockets  # 🟢 Inyección del módulo de WebSockets
from app.api.v1.endpoints import control

api_router = APIRouter()

# Unificar los endpoints modulares del SCADA Jageg V2
api_router.include_router(tags.router, prefix="/tags", tags=["SCADA Tags"])
api_router.include_router(alarms.router, prefix="/alarms", tags=["SCADA Alarms"])
api_router.include_router(history.router, prefix="/history", tags=["SCADA History"])
api_router.include_router(hardware.router, prefix="/hardware", tags=["Hardware Industrial"])

# 🟢 Dejamos el prefijo vacío o plano si el archivo ya define la ruta interna
api_router.include_router(analytics.router, tags=["Analítica de Producción"])
api_router.include_router(websockets.router, prefix="/stream", tags=["HMI Streaming"])

api_router.include_router(control.router, prefix="/Control", tags=["Control"])