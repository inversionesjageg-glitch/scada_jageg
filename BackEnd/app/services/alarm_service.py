from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.models.scada import TagModel, AlarmModel

async def evaluar_alarmas_tag_async(db: AsyncSession, tag: TagModel) -> list[str]:
    """
    Versión asíncrona para integrarse con los endpoints de la API.
    Evalúa el current_value de un tag frente a sus límites.
    """
    if tag.current_value is None:
        return []

    tipo_alarma_detectada = None
    mensaje_alarma = ""
    severidad = "WARNING"

    # 1. Evaluación de límites
    if tag.limit_high_high is not None and tag.current_value >= tag.limit_high_high:
        tipo_alarma_detectada = "HIGH_HIGH"
        mensaje_alarma = f"Crítico: {tag.description or tag.tag_name} superó límite máximo ({tag.current_value} >= {tag.limit_high_high})"
        severidad = "CRITICAL"
    elif tag.limit_high is not None and tag.current_value >= tag.limit_high:
        tipo_alarma_detectada = "HIGH"
        mensaje_alarma = f"Advertencia: {tag.description or tag.tag_name} elevado ({tag.current_value} >= {tag.limit_high})"
        severidad = "WARNING"
    elif tag.limit_low_low is not None and tag.current_value <= tag.limit_low_low:
        tipo_alarma_detectada = "LOW_LOW"
        mensaje_alarma = f"Crítico: {tag.description or tag.tag_name} por debajo del mínimo ({tag.current_value} <= {tag.limit_low_low})"
        severidad = "CRITICAL"
    elif tag.limit_low is not None and tag.current_value <= tag.limit_low:
        tipo_alarma_detectada = "LOW"
        mensaje_alarma = f"Advertencia: {tag.description or tag.tag_name} bajo ({tag.current_value} <= {tag.limit_low})"
        severidad = "WARNING"

    # 2. Búsqueda asíncrona tolerante a duplicados huerfanos
    query = (
        select(AlarmModel)
        .where(AlarmModel.tag_id == tag.id, AlarmModel.is_active == True)
        .order_by(AlarmModel.timestamp_active.desc())  # Trae la más reciente primero
    )
    result = await db.execute(query)
    alarma_activa = result.scalars().first()  # 🛡️ Cambiado para evitar crasheos por filas múltiples

    ahora = datetime.now(timezone.utc)

    # CASO A: Anomalía detectada
    if tipo_alarma_detectada:
        if alarma_activa:
            if alarma_activa.alarm_type != tipo_alarma_detectada:
                alarma_activa.alarm_type = tipo_alarma_detectada
                alarma_activa.message = mensaje_alarma
                alarma_activa.severity = severidad
                alarma_activa.timestamp_active = ahora
                alarma_activa.is_acknowledged = False
                alarma_activa.timestamp_ack = None
        else:
            nueva_alarma = AlarmModel(
                tag_id=tag.id,
                alarm_type=tipo_alarma_detectada,
                message=mensaje_alarma,
                severity=severidad,
                timestamp_active=ahora,
                is_active=True,
                is_acknowledged=False
            )
            db.add(nueva_alarma)
        
        return [tipo_alarma_detectada]

    # CASO B: Proceso normalizado
    else:
        if alarma_activa:
            alarma_activa.is_active = False
            alarma_activa.timestamp_cleared = ahora
        
        return []