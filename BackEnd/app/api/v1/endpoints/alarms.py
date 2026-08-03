# BackEnd/app/api/v1/endpoints/alarms.py
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime, timezone
import logging

from app.database import get_db
from app.models.scada import AlarmModel, TagModel
from app.services.alarm_service import evaluar_alarmas_tag_async

router = APIRouter()
logger = logging.getLogger("SCADA_Jageg_AlarmsAPI")


@router.get("/active")
async def get_active_alarms(db: AsyncSession = Depends(get_db)):
    """
    Retorna todas las alarmas que se encuentran actualmente activas en la planta.
    """
    query = select(AlarmModel).where(AlarmModel.is_active == True).order_by(AlarmModel.timestamp_active.desc())
    result = await db.execute(query)
    return result.scalars().all()


@router.post("/evaluate-all")
async def evaluate_plant_alarms(db: AsyncSession = Depends(get_db)):
    """
    Endpoint estratégico: Evalúa todos los tags en tiempo real y actualiza 
    el estado de las alarmas antes de que el frontend pinte la HMI.
    """
    query_tags = select(TagModel)
    result_tags = await db.execute(query_tags)
    tags = result_tags.scalars().all()
    
    alertas_procesadas = 0
    errores_detectados = 0
    
    for tag in tags:
        # 🛡️ BLOQUE DE MITIGACIÓN INDUSTRIAL: Evita que la falla de un tag tire la evaluación general
        try:
            await evaluar_alarmas_tag_async(db, tag)
            alertas_procesadas += 1
        except Exception as tag_err:
            errores_detectados += 1
            logger.warning(f"Error evaluando límites de alarma para el tag {tag.tag_name}: {str(tag_err)}")
            continue
            
    try:
        await db.commit()
    except Exception as commit_err:
        logger.error(f"Error crítico al confirmar la evaluación de alarmas en DB: {str(commit_err)}")
        await db.rollback()
        raise HTTPException(
            status_code=500, 
            detail="Error interno al procesar y almacenar el estado de las alarmas en planta"
        )
        
    return {
        "status": "success", 
        "message": f"Evaluación completada. Tags procesados con éxito: {alertas_procesadas}. Tags con anomalías: {errores_detectados}."
    }


@router.post("/{alarm_id}/acknowledge")
async def acknowledge_alarm(alarm_id: int, db: AsyncSession = Depends(get_db)):
    """
    Permite al operador del Frontend 'reconocer' o aceptar una alarma activa.
    """
    query = select(AlarmModel).where(AlarmModel.id == alarm_id)
    result = await db.execute(query)
    alarma = result.scalar_one_or_none()
    
    if not alarma:
        raise HTTPException(status_code=404, detail="Alarma no encontrada")
        
    alarma.is_acknowledged = True
    alarma.timestamp_ack = datetime.now(timezone.utc)
    
    await db.commit()
    return {"status": "success", "message": f"Alarma {alarm_id} reconocida por el operador"}