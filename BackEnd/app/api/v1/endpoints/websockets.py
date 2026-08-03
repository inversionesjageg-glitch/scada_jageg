from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
import asyncio
import json
import logging
from datetime import datetime, timezone

from app.database import AsyncSessionLocal
from app.models.scada import TagModel
from app.services.alarm_service import evaluar_alarmas_tag_async

router = APIRouter()
logger = logging.getLogger("SCADA_Jageg_WS")

class ConnectionManager:
    """Gestiona los clientes WebSocket activos en las pantallas HMI."""
    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info(f"HMI Conectado: Nueva pantalla SCADA acoplada (Total: {len(self.active_connections)})")

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)
        logger.info(f"HMI Desconectado: Pantalla SCADA liberada (Total: {len(self.active_connections)})")

manager = ConnectionManager()

async def get_live_tags_snapshot() -> dict:
    """Consulta rápida al Contenedor 1 para extraer el estado vivo y evaluar alarmas."""
    async with AsyncSessionLocal() as session:
        try:
            result = await session.execute(select(TagModel))
            tags = result.scalars().all()
            
            payload_tags = {}
            lista_alertas_activas = []
            
            # Iterar los tags para armar los valores vivos y procesar alarmas
            for tag in tags:
                payload_tags[tag.tag_name] = tag.current_value
                
                # 🛡️ BLOQUE DE PROTECCIÓN LOCAL: Evita que un error de filas duplicadas en las alarmas tumbe el flujo de datos
                try:
                    alarmas_tag = await evaluar_alarmas_tag_async(session, tag)
                    if alarmas_tag:
                        lista_alertas_activas.append({
                            "tag": tag.tag_name,
                            "type": alarmas_tag[0],
                            "desc": tag.description
                        })
                except Exception as alarm_err:
                    # Si falla por filas múltiples o cualquier detalle de BD, lo registramos pero continuamos con los demás tags
                    logger.warning(f"Error evaluando alarma para el tag {tag.tag_name}: {str(alarm_err)}")
                    continue
            
            # Confirmar los cambios de estado en las alarmas de forma segura
            try:
                await session.commit()
            except Exception as commit_err:
                logger.error(f"Error al hacer commit del estado de alarmas: {str(commit_err)}")
                await session.rollback()
            
            # Estructurar la ráfaga de datos compatible con la HMI
            payload = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "tags": payload_tags,
                "active_alarms": lista_alertas_activas
            }
            return payload
            
        except Exception as e:
            logger.error(f"Error crítico en snapshot general de WS: {str(e)}")
            await session.rollback()
            return {}

@router.websocket("/ws/hmi")
async def websocket_hmi_endpoint(websocket: WebSocket):
    """
    Canal WebSocket duplex para el streaming de telemetría en tiempo real con alertas.
    """
    await manager.connect(websocket)
    try:
        while True:
            snapshot = await get_live_tags_snapshot()
            if snapshot and snapshot.get("tags"):
                await websocket.send_text(json.dumps(snapshot))
            await asyncio.sleep(1.0)
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as e:
        logger.error(f"Error en ciclo de comunicación WebSocket: {str(e)}")
        manager.disconnect(websocket)