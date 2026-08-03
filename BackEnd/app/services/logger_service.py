# BackEnd/app/services/logger_service.py
import asyncio
import logging
import re
from datetime import datetime, timezone
from sqlalchemy import select, update

from snap7.util import get_real

from app.config import settings
from app.services.plc_service import PLCConnectionService
from app.models.scada import (
    TagModel, 
    HistoricoExtrusoraS1Model, 
    HistoricoExtrusoraS2Model, 
    HistoricoExtrusoraMeltblownModel,
    HistoricoProcesoMecanicoModel, 
    HistoricoMotoresVelocidadesModel, 
    HistoricoDosificacionGlobalModel
)
from app.database import AsyncSessionLocal 

logger = logging.getLogger("SCADA_Jageg_Logger")

class SCADALoggerService:
    def __init__(self, interval_seconds: int = 5, plc_service: PLCConnectionService | None = None):
        self.interval_seconds = interval_seconds
        self.is_running = False
        # 🆕 El driver PLC ahora se INYECTA desde main.py (misma instancia que
        # usan los endpoints de control.py vía Depends(get_plc_driver)), en vez
        # de crearse aquí de forma independiente. Esto evita abrir dos
        # conexiones TCP/IP distintas hacia el mismo PLC.
        # Si no se provee explícitamente (ej. en tests unitarios), se crea uno
        # local como fallback para no romper compatibilidad.
        self.plc_service = plc_service or PLCConnectionService(
            ip_address=settings.PLC_IP, 
            rack=settings.PLC_RACK, 
            slot=settings.PLC_SLOT
        )

    def _parsear_direccion_fisica(self, direccion: str) -> tuple[int, int] | None:
        """Utilitario para fragmentar la cadena 'DBX.DBDXX'"""
        if not direccion:
            return None
        match = re.match(r"^DB(\d+)\.DBD(\d+)$", direccion.strip().upper())
        if match:
            return int(match.group(1)), int(match.group(2))
        return None

    async def start_logging_loop(self):
        self.is_running = True
        logger.info(f"🚀 Motor SCADA Jageg Avanzado: Iniciando recolección dinámica cada {self.interval_seconds}s.")
        
        while self.is_running:
            try:
                tags_config = await self._load_tags_configuration()
                if not tags_config:
                    logger.warning("⚠️ No hay tags activos mapeados a hardware en la BD. Reintentando...")
                    await asyncio.sleep(self.interval_seconds)
                    continue

                conexion_ok = await asyncio.to_thread(self.plc_service.asegurar_conexion)
                
                if conexion_ok:
                    snapshot_valores = await asyncio.to_thread(self._execute_dynamic_read, tags_config)
                    if snapshot_valores:
                        await self._persist_and_update_scada(snapshot_valores, tags_config)
                else:
                    logger.warning(f"⚠️ PLC inaccesible en {settings.PLC_IP}. Saltando ciclo de adquisición.")
                    
            except Exception as e:
                logger.error(f"❌ Error crítico en el ciclo de recolección: {str(e)}", exc_info=True)
            
            await asyncio.sleep(self.interval_seconds)

    def stop_logging_loop(self):
        self.is_running = False
        self.plc_service.disconnect()
        logger.info("🛑 Motor SCADA Jageg: Deteniendo recolección automática de hardware.")

    async def _load_tags_configuration(self) -> list:
        """Descarga dinámicamente todos los tags activos que tengan dirección física configurada"""
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(TagModel).where(
                    TagModel.is_simulated == False,
                    TagModel.direccion_fisica != None
                )
            )
            return result.scalars().all()

    def _execute_dynamic_read(self, tags_config: list) -> dict:
        """Determina los DBs leyendo y parseando dinámicamente la columna 'direccion_fisica'."""
        snapshot = {}
        buffers_db = {}
        mapeo_validos = {} # tag_id -> (db, byte)

        for tag in tags_config:
            parsed = self._parsear_direccion_fisica(tag.direccion_fisica)
            if parsed:
                mapeo_validos[tag.id] = parsed

        if not mapeo_validos:
            return {}

        dbs_a_leer = set(db for db, _ in mapeo_validos.values())

        try:
            for db in dbs_a_leer:
                bytes_del_db = [byte for t_id, (db_num, byte) in mapeo_validos.items() if db_num == db]
                if not bytes_del_db:
                    continue
                max_byte = max(bytes_del_db) + 4
                
                buffers_db[db] = self.plc_service.leer_bloque_db(db, max_byte)

            for tag in tags_config:
                if tag.id not in mapeo_validos:
                    snapshot[tag.tag_name] = 0.0
                    continue

                db_num, offset_byte = mapeo_validos[tag.id]
                buffer = buffers_db.get(db_num)
                
                if buffer and offset_byte <= len(buffer) - 4:
                    snapshot[tag.tag_name] = get_real(buffer, offset_byte)
                else:
                    snapshot[tag.tag_name] = 0.0

            return snapshot
        except Exception as e:
            logger.warning(f"⚠️ Error de adquisición dinámica en ráfaga Snap7: {str(e)}")
            return {}

    async def _persist_and_update_scada(self, snapshot: dict, tags_config: list):
        ahora = datetime.now(timezone.utc)
        
        async with AsyncSessionLocal() as session:
            try:
                # FUNCIÓN SANITIZADORA
                def gv(tag_name: str) -> float:
                    valor = snapshot.get(tag_name, 0.0)
                    if abs(valor) < 1e-4:
                        return 0.0
                    # Filtro de límites reales de la planta de extrusión (Spunbond / Meltblown)
                    if valor > 30000.0 or valor < -5000.0:
                        return 0.0
                    return round(valor, 4)

                # ACTION 1: ACTUALIZACIÓN EN VIVO (BULK UPDATE) EN SCADA_TAGS
                mappings = [
                    {"id": tag.id, "current_value": gv(tag.tag_name)}
                    for tag in tags_config
                ]
                await session.execute(update(TagModel), mappings)

                # ACTION 2: HISTÓRICOS MATRICIALES COMPLETOS

                # 1. Histórico Spunbond 1 (S1) - DB2
                h_s1 = HistoricoExtrusoraS1Model(
                    timestamp=ahora,
                    pv_zona1=gv("S1_PV_Z1"), sp_zona1=gv("S1_SP_Z1"),
                    pv_zona2=gv("S1_PV_Z2"), sp_zona2=gv("S1_SP_Z2"),
                    pv_zona3=gv("S1_PV_Z3"), sp_zona3=gv("S1_SP_Z3"),
                    pv_zona4=gv("S1_PV_Z4"), sp_zona4=gv("S1_SP_Z4"),
                    pv_zona5=gv("S1_PV_Z5"), sp_zona5=gv("S1_SP_Z5"),
                    pv_zona6=gv("S1_PV_Z6"), sp_zona6=gv("S1_SP_Z6"),
                )
                
                # 2. Histórico Spunbond 2 (S2) - DB3
                h_s2 = HistoricoExtrusoraS2Model(
                    timestamp=ahora,
                    pv_zona1=gv("S2_PV_Z1"), sp_zona1=gv("S2_SP_Z1"),
                    pv_zona2=gv("S2_PV_Z2"), sp_zona2=gv("S2_SP_Z2"),
                    pv_zona3=gv("S2_PV_Z3"), sp_zona3=gv("S2_SP_Z3"),
                    pv_zona4=gv("S2_PV_Z4"), sp_zona4=gv("S2_SP_Z4"),
                    pv_zona5=gv("S2_PV_Z5"), sp_zona5=gv("S2_SP_Z5"),
                    pv_zona6=gv("S2_PV_Z6"), sp_zona6=gv("S2_SP_Z6"),
                )
                
                # 3. Histórico Meltblown (M) - DB4
                h_m = HistoricoExtrusoraMeltblownModel(
                    timestamp=ahora,
                    pv_zona1=gv("M_PV_Z1"), sp_zona1=gv("M_SP_Z1"),
                    pv_zona2=gv("M_PV_Z2"), sp_zona2=gv("M_SP_Z2"),
                    pv_zona3=gv("M_PV_Z3"), sp_zona3=gv("M_SP_Z3"),
                    pv_zona4=gv("M_PV_Z4"), sp_zona4=gv("M_SP_Z4"),
                    pv_zona5=gv("M_PV_Z5"), sp_zona5=gv("M_SP_Z5"),
                    pv_zona6=gv("M_PV_Z6"), sp_zona6=gv("M_SP_Z6"),
                )

                # 4. Histórico Proceso Mecánico - DB5 (Agregado e indexado con tu JSON)
                h_mecanico = HistoricoProcesoMecanicoModel(
                    timestamp=ahora,
                    sp_rbody=gv("SP_RBODY"),
                    pv_rbody=gv("PV_RBODY"),
                    sp_coolarea=gv("SP_COOLAREA"),
                    pv_coolarea=gv("PV_COOLAREA"),
                    sp_coolfan=gv("SP_COOLFAN"),
                    pv_coolfan=gv("PV_COOLFAN"),
                    sv1_filter_ex_pre=gv("SV1_FILTER_EX_PRE"),
                    sv2_filter_ex_pre=gv("SV2_FILTER_EX_PRE"),
                    pv_filter_ex_pre=gv("PV_FILTER_EX_PRE"),
                    sp_die_pre=gv("SP_DIE_PRE"),
                    pv_die_pre=gv("PV_DIE_PRE"),
                    rgrafito_temp_sp=gv("RGRAFITO_TEMP_SP"),
                    rgrafito_temp_pv=gv("RGRAFITO_TEMP_PV")
                )

                # 5. Histórico Motores y Velocidades - DB6 (Agregado e indexado con tu JSON)
                h_velocidades = HistoricoMotoresVelocidadesModel(
                    timestamp=ahora,
                    sp_bomba_hiladora=gv("SP_BOMBA_HILADORA"),
                    pv_bomba_hiladora=gv("PV_BOMBA_HILADORA"),
                    sp_m_incoex_rpm=gv("SP_M_INCOEX_RPM"),
                    pv_m_incoex_rpm=gv("PV_M_INCOEX_RPM"),
                    sp_m_monomero=gv("SP_M_MONOMERO"),
                    pv_m_monomero=gv("PV_M_MONOMERO"),
                    sp_m_cooling=gv("SP_M_COOLING"),
                    pv_m_cooling=gv("PV_M_COOLING"),
                    sp_m_chiladora=gv("SP_M_CHILADORA"),
                    pv_m_chiladora=gv("PV_M_CHILADORA"),
                    sp_m_suction=gv("SP_M_SUCTION"),
                    pv_m_suction=gv("PV_M_SUCTION")
                )
                
                # 6. Histórico Dosificación Global - DB7
                h_dosificacion = HistoricoDosificacionGlobalModel(
                    timestamp=ahora,
                    m_stock_rpm=gv("M_STOCK_RPM"),
                    dosificacion_mot_m=gv("DOSIFICACION_MOT_M"),
                    porcentaje_mot_mezclador_m=gv("PORCENTAJE_MOT_MEZCLADOR_M"),
                    motor_c1_m=gv("MOTOR_C1_M"),
                    motor_c2_m=gv("MOTOR_C2_M"),
                    porcentaje_m_c1_m=gv("PORCENTAJE_M_C1_M"),
                    porcentaje_m_c2_m=gv("PORCENTAJE_M_C2_M"),
                    # Campos de S1 y S2 quedan en None/Null listos para expansión futura
                    s1_stock_rpm=None, 
                    dosificacion_mot_s1=None, 
                    porcentaje_mot_mezclador_s1=None,
                    motor_c1_s1=None,
                    porcentaje_m_c1_s1=None,
                    s2_stock_rpm=None,
                    dosificacion_mot_s2=None,
                    porcentaje_mot_mezclador_s2=None,
                    motor_c1_s2=None,
                    porcentaje_m_c1_s2=None
                )
                
                # Agregamos las 6 instancias a la sesión de persistencia matricial
                session.add_all([h_s1, h_s2, h_m, h_mecanico, h_velocidades, h_dosificacion])
                await session.commit()
                logger.info(f"💾 Ciclo SCADA completado con éxito. {len(mappings)} tags sincronizados y 6 bloques matriciales guardados.")
                
            except Exception as db_err:
                await session.rollback()
                logger.error(f"❌ Fallo al guardar ráfaga en la Base de Datos: {str(db_err)}")