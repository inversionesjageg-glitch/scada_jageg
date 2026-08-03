# BackEnd/app/api/v1/endpoints/history.py
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime

from app.database import AsyncSessionLocal
from app.models.scada import (
    TagHistoryModel,
    HistoricoExtrusoraS1Model,
    HistoricoExtrusoraS2Model,
    HistoricoExtrusoraMeltblownModel,
    HistoricoDosificacionGlobalModel
)

router = APIRouter()

async def get_db():
    async with AsyncSessionLocal() as session:
        yield session

# --- CONSULTA GENÉRICA ORIGINAL (RESPALDO EAV) ---
@router.get("/tag/{tag_id}")
async def get_tag_history(tag_id: int, start_time: datetime, end_time: datetime, db: AsyncSession = Depends(get_db)):
    """
    Retorna los datos históricos individuales de un Tag específico (Auditoría profunda).
    """
    query = select(TagHistoryModel).where(
        TagHistoryModel.tag_id == tag_id,
        TagHistoryModel.timestamp >= start_time,
        TagHistoryModel.timestamp <= end_time
    ).order_by(TagHistoryModel.timestamp.asc())
    
    result = await db.execute(query)
    return result.scalars().all()


# --- MATRICES DE TENDENCIAS OPTIMIZADAS PARA VENTANAS DEL SCADA ---

@router.get("/extrusora-s1")
async def get_extrusora_s1_trends(start_time: datetime, end_time: datetime, db: AsyncSession = Depends(get_db)):
    """
    Ventana: Historicos_S1. Retorna la matriz de perfiles térmicos (PV y SP) de la Capa S1.
    """
    query = select(HistoricoExtrusoraS1Model).where(
        HistoricoExtrusoraS1Model.timestamp >= start_time,
        HistoricoExtrusoraS1Model.timestamp <= end_time
    ).order_by(HistoricoExtrusoraS1Model.timestamp.asc())
    
    result = await db.execute(query)
    return result.scalars().all()


@router.get("/extrusora-s2")
async def get_extrusora_s2_trends(start_time: datetime, end_time: datetime, db: AsyncSession = Depends(get_db)):
    """
    Ventana: Historicos_S2. Retorna la matriz de perfiles térmicos (PV y SP) de la Capa S2.
    """
    query = select(HistoricoExtrusoraS2Model).where(
        HistoricoExtrusoraS2Model.timestamp >= start_time,
        HistoricoExtrusoraS2Model.timestamp <= end_time
    ).order_by(HistoricoExtrusoraS2Model.timestamp.asc())
    
    result = await db.execute(query)
    return result.scalars().all()


@router.get("/extrusora-meltblown")
async def get_extrusora_meltblown_trends(start_time: datetime, end_time: datetime, db: AsyncSession = Depends(get_db)):
    """
    Ventana: Historicos_M_Ext. Retorna las tendencias térmicas de la extrusora central Meltblown.
    """
    query = select(HistoricoExtrusoraMeltblownModel).where(
        HistoricoExtrusoraMeltblownModel.timestamp >= start_time,
        HistoricoExtrusoraMeltblownModel.timestamp <= end_time
    ).order_by(HistoricoExtrusoraMeltblownModel.timestamp.asc())
    
    result = await db.execute(query)
    return result.scalars().all()


@router.get("/dosificacion")
async def get_dosificacion_global_trends(start_time: datetime, end_time: datetime, db: AsyncSession = Depends(get_db)):
    """
    Ventana: Historico_Dosficacion. Retorna los indicadores de dosificación de aditivos (RPM, G/R, %) de Meltblown, S1 y S2.
    """
    query = select(HistoricoDosificacionGlobalModel).where(
        HistoricoDosificacionGlobalModel.timestamp >= start_time,
        HistoricoDosificacionGlobalModel.timestamp <= end_time
    ).order_by(HistoricoDosificacionGlobalModel.timestamp.asc())
    
    result = await db.execute(query)
    return result.scalars().all()