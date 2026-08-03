# BackEnd/app/simulator.py
import asyncio
import random
from datetime import datetime, timezone
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
import snap7
from snap7.util import get_real

# Infraestructura y Configuración Dinámica del Proyecto
from app.config import settings
from app.database import AsyncSessionLocal 
from BackEnd.app.models.scada import (
    TagModel, 
    AlarmModel, 
    TagHistoryModel,
    HistoricoExtrusoraS1Model,
    HistoricoExtrusoraS2Model,
    HistoricoExtrusoraMeltblownModel,
    HistoricoMeltblownDieModel,
    HistoricoDosificacionGlobalModel
)

async def run_scada_worker():
    """
    Worker dinámico unificado del SCADA Jageg (Máquina 3).
    - Lee en ráfaga (Burst Read) el PLC físico usando variables de entorno (.env).
    - Simula mediante inercia matemática los tags configurados como simulados (Híbrido).
    - Realiza actualizaciones en tiempo real (1s), alertas y snapshots matriciales (60s).
    """
    print(f"🚀 Worker SCADA Jageg Activo. Apuntando a PLC físico en {settings.plc_ip} (DB {settings.plc_db_s1})...")
    
    contador_ciclos = 0
    INTERVALO_HISTORICOS_SEGUNDOS = 60 
    
    # Inicialización del cliente nativo S7
    plc_client = snap7.client.Client()

    while True:
        try:
            async with AsyncSessionLocal() as session:
                async with session.begin():
                    
                    # 1. Recuperar la totalidad de tags configurados en PostgreSQL
                    result = await session.execute(select(TagModel))
                    all_tags = result.scalars().all()
                    tags_dict = {tag.tag_name.upper(): tag for tag in all_tags}
                    
                    contador_ciclos += 1
                    guardar_en_historico = (contador_ciclos >= INTERVALO_HISTORICOS_SEGUNDOS)
                    if guardar_en_historico:
                        contador_ciclos = 0

                    # 2. LECTURA DINÁMICA DE PLANTA: Conexión parametrizada por .env
                    plc_datos_reales = {}
                    if any(not tag.is_simulated for tag in all_tags):
                        try:
                            if not plc_client.get_connected():
                                plc_client.connect(settings.plc_ip, settings.plc_rack, settings.plc_slot)
                            
                            if plc_client.get_connected():
                                # Lectura en ráfaga de 48 bytes desde el offset cero del DB parametrizado
                                buffer_db = plc_client.db_read(settings.plc_db_s1, start=0, size=48)
                                plc_datos_reales = {
                                    "S1_PV_Z1": get_real(buffer_db, 0),  "S1_SP_Z1": get_real(buffer_db, 4),
                                    "S1_PV_Z2": get_real(buffer_db, 8),  "S1_SP_Z2": get_real(buffer_db, 12),
                                    "S1_PV_Z3": get_real(buffer_db, 16), "S1_SP_Z3": get_real(buffer_db, 20),
                                    "S1_PV_Z4": get_real(buffer_db, 24), "S1_SP_Z4": get_real(buffer_db, 28),
                                    "S1_PV_Z5": get_real(buffer_db, 32), "S1_SP_Z5": get_real(buffer_db, 36),
                                    "S1_PV_Z6": get_real(buffer_db, 40), "S1_SP_Z6": get_real(buffer_db, 44),
                                }
                        except Exception as plc_err:
                            print(f"⚠️ Enlace S7 [{settings.plc_ip}] fuera de línea. Corriendo modo preventivo analítico: {plc_err}")

                    # 3. Procesamiento y actualización del estado vivo
                    for tag in all_tags:
                        nombre_tag = tag.tag_name.upper()
                        
                        if not tag.is_simulated and nombre_tag in plc_datos_reales:
                            nuevo_valor = round(plc_datos_reales[nombre_tag], 2)
                        else:
                            nuevo_valor = calcular_valor_industrial_real(tag, tags_dict)
                        
                        tag.current_value = nuevo_valor
                        
                        # Respaldo de auditoría EAV individual
                        if guardar_en_historico:
                            nuevo_registro_historico = TagHistoryModel(
                                tag_id=tag.id,
                                value=nuevo_valor,
                                timestamp=datetime.now(timezone.utc)
                            )
                            session.add(nuevo_registro_historico)
                        
                        # Despachador asíncrono de incidencias y alarmas
                        await gestionar_ciclo_alertas(tag, session)
                    
                    # 4. Guardado Masivo en Tablas Matriciales (Cada 1 minuto)
                    if guardar_en_historico:
                        now_utc = datetime.now(timezone.utc)
                        
                        # --- MATRIZ 1: HISTÓRICO EXTRUSORA S1 ---
                        if all(f"S1_PV_Z{i}" in tags_dict for i in range(1, 7)):
                            hist_s1 = HistoricoExtrusoraS1Model(
                                timestamp=now_utc,
                                pv_zona1=tags_dict["S1_PV_Z1"].current_value, sp_zona1=tags_dict["S1_SP_Z1"].current_value if "S1_SP_Z1" in tags_dict else 210.0,
                                pv_zona2=tags_dict["S1_PV_Z2"].current_value, sp_zona2=tags_dict["S1_SP_Z2"].current_value if "S1_SP_Z2" in tags_dict else 215.0,
                                pv_zona3=tags_dict["S1_PV_Z3"].current_value, sp_zona3=tags_dict["S1_SP_Z3"].current_value if "S1_SP_Z3" in tags_dict else 220.0,
                                pv_zona4=tags_dict["S1_PV_Z4"].current_value, sp_zona4=tags_dict["S1_SP_Z4"].current_value if "S1_SP_Z4" in tags_dict else 220.0,
                                pv_zona5=tags_dict["S1_PV_Z5"].current_value, sp_zona5=tags_dict["S1_SP_Z5"].current_value if "S1_SP_Z5" in tags_dict else 225.0,
                                pv_zona6=tags_dict["S1_PV_Z6"].current_value, sp_zona6=tags_dict["S1_SP_Z6"].current_value if "S1_SP_Z6" in tags_dict else 230.0,
                            )
                            session.add(hist_s1)

                        # --- MATRICES COMPLEMENTARIAS (S2, Meltblown, DIE, Dosificación) ---
                        await _guardar_resto_matrices(session, tags_dict, now_utc)
                        print(f"📉 [Matriz SCADA] Snapshots analíticos de producción persistidos a las {now_utc.strftime('%H:%M:%S')}")

        except Exception as e:
            print(f"❌ Error crítico en el bucle principal de adquisición del SCADA: {e}")
            
        await asyncio.sleep(1.0)


def calcular_valor_industrial_real(tag: TagModel, tags_dict: dict) -> float:
    """Algoritmo de inercia térmica y mecánica original."""
    valor_pv_actual = tag.current_value
    nombre = tag.tag_name.upper()

    nombre_sp = nombre.replace("_PV_", "_SP_")
    if nombre_sp in tags_dict:
        objetivo_sp = tags_dict[nombre_sp].current_value
    else:
        objetivo_sp = tag.limit_high if tag.limit_high is not None else 210.0

    if "ZONA" in nombre or "TEMP" in nombre or "DIE" in nombre:
        factor_inercia = 0.04
        ruido_proceso = random.uniform(-0.15, 0.15)
        nuevo_valor = valor_pv_actual + (factor_inercia * (objetivo_sp - valor_pv_actual)) + ruido_proceso
    elif "RPM" in nombre or "MOTOR" in nombre or "VARIADOR" in nombre:
        factor_mecanico = 0.25
        ruido_mecanico = random.uniform(-0.6, 0.6)
        nuevo_valor = valor_pv_actual + (factor_mecanico * (objetivo_sp - valor_pv_actual)) + ruido_mecanico
    else:
        nuevo_valor = valor_pv_actual + random.uniform(-0.2, 0.2)

    max_absoluto = tag.limit_high_high if tag.limit_high_high is not None else 300.0
    min_absoluto = tag.limit_low_low if tag.limit_low_low is not None else 0.0

    return round(max(min(nuevo_valor, max_absoluto), min_absoluto), 2)


async def gestionar_ciclo_alertas(tag: TagModel, session: AsyncSession):
    """Detector de Umbrales Críticos e Historial normativo de alarmas."""
    limite_hh = tag.limit_high_high
    valor_actual = tag.current_value
    condicion_disparada = (limite_hh is not None and valor_actual >= limite_hh)

    query = select(AlarmModel).where(
        AlarmModel.tag_id == tag.id, 
        AlarmModel.is_active == True,
        AlarmModel.alarm_type == "HIGH_HIGH"
    )
    res = await session.execute(query)
    alarma_activa = res.scalar_one_or_none()

    if condicion_disparada:
        if not alarma_activa:
            nueva_alarma = AlarmModel(
                tag_id=tag.id,
                alarm_type="HIGH_HIGH",
                message=f"Alerta Crítica: Límite HH superado en {tag.tag_name} ({valor_actual} >= {limite_hh})",
                severity="CRITICAL",
                timestamp_active=datetime.now(timezone.utc),
                is_active=True,
                is_acknowledged=False
            )
            session.add(nueva_alarma)
            print(f"🚨 [ALERTA SCADA] {tag.tag_name} ha ingresado en estado CRÍTICO: {valor_actual}")
    else:
        if alarma_activa:
            alarma_activa.is_active = False
            alarma_activa.timestamp_cleared = datetime.now(timezone.utc)
            print(f"✅ [ALERTA SCADA] {tag.tag_name} se ha normalizado de forma segura: {valor_actual}")


async def _guardar_resto_matrices(session: AsyncSession, tags_dict: dict, now_utc: datetime):
    """Estructuras analíticas complementarias de las capas secundarias de extrusión."""
    # S2
    if all(f"S2_PV_Z{i}" in tags_dict for i in range(1, 7)):
        session.add(HistoricoExtrusoraS2Model(
            timestamp=now_utc,
            pv_zona1=tags_dict["S2_PV_Z1"].current_value, sp_zona1=210.0,
            pv_zona2=tags_dict["S2_PV_Z2"].current_value, sp_zona2=215.0,
            pv_zona3=tags_dict["S2_PV_Z3"].current_value, sp_zona3=220.0,
            pv_zona4=tags_dict["S2_PV_Z4"].current_value, sp_zona4=220.0,
            pv_zona5=tags_dict["S2_PV_Z5"].current_value, sp_zona5=225.0,
            pv_zona6=tags_dict["S2_PV_Z6"].current_value, sp_zona6=230.0,
        ))
    # Meltblown Extrusora
    if all(f"M_EXT_PV_Z{i}" in tags_dict for i in range(1, 7)):
        session.add(HistoricoExtrusoraMeltblownModel(
            timestamp=now_utc,
            pv_zona1=tags_dict["M_EXT_PV_Z1"].current_value, sp_zona1=230.0,
            pv_zona2=tags_dict["M_EXT_PV_Z2"].current_value, sp_zona2=235.0,
            pv_zona3=tags_dict["M_EXT_PV_Z3"].current_value, sp_zona3=240.0,
            pv_zona4=tags_dict["M_EXT_PV_Z4"].current_value, sp_zona4=240.0,
            pv_zona5=tags_dict["M_EXT_PV_Z5"].current_value, sp_zona5=245.0,
            pv_zona6=tags_dict["M_EXT_PV_Z6"].current_value, sp_zona6=250.0,
        ))
    # Meltblown Die
    if all(f"M_DIE_PV_Z{i}" in tags_dict for i in range(1, 7)):
        session.add(HistoricoMeltblownDieModel(
            timestamp=now_utc,
            pv_zona1=tags_dict["M_DIE_PV_Z1"].current_value, sp_zona1=240.0,
            pv_zona2=tags_dict["M_DIE_PV_Z2"].current_value, sp_zona2=240.0,
            pv_zona3=tags_dict["M_DIE_PV_Z3"].current_value, sp_zona3=240.0,
            pv_zona4=tags_dict["M_DIE_PV_Z4"].current_value, sp_zona4=240.0,
            pv_zona5=tags_dict["M_DIE_PV_Z5"].current_value, sp_zona5=240.0,
            pv_zona6=tags_dict["M_DIE_PV_Z6"].current_value, sp_zona6=240.0,
        ))
    # Dosificación Global
    session.add(HistoricoDosificacionGlobalModel(
        timestamp=now_utc,
        m_stock_rpm=tags_dict.get("M_STOCK_RPM", TagModel(current_value=45.0)).current_value,
        dosificacion_mot_m=tags_dict.get("DOSIFICACION_MOT_M", TagModel(current_value=2.4)).current_value,
        porcentaje_mot_mezclador_m=tags_dict.get("PORCENTAJE_MOT_MEZCLADOR_M", TagModel(current_value=98.1)).current_value,
        motor_c1_m=tags_dict.get("MOTOR_C1_M", TagModel(current_value=12.0)).current_value,
        porcentaje_m_c1_m=tags_dict.get("PORCENTAJE_M_C1_M", TagModel(current_value=1.5)).current_value,
        motor_c2_m=tags_dict.get("MOTOR_C2_M", TagModel(current_value=0.0)).current_value,
        porcentaje_m_c2_m=tags_dict.get("PORCENTAJE_M_C2_M", TagModel(current_value=0.0)).current_value,
        s1_stock_rpm=tags_dict.get("S1_STOCK_RPM", TagModel(current_value=55.0)).current_value,
        dosificacion_mot_s1=tags_dict.get("DOSIFICACION_MOT_S1", TagModel(current_value=3.1)).current_value,
        porcentaje_mot_mezclador_s1=tags_dict.get("PORCENTAJE_MOT_MEZCLADOR_S1", TagModel(current_value=95.4)).current_value,
        motor_c1_s1=tags_dict.get("MOTOR_C1_S1", TagModel(current_value=8.5)).current_value,
        porcentaje_m_c1_s1=tags_dict.get("PORCENTAJE_M_C1_S1", TagModel(current_value=1.1)).current_value,
        s2_stock_rpm=tags_dict.get("S2_STOCK_RPM", TagModel(current_value=52.0)).current_value,
        dosificacion_mot_s2=tags_dict.get("DOSIFICACION_MOT_s2", TagModel(current_value=2.9)).current_value,
        porcentaje_mot_mezclador_s2=tags_dict.get("PORCENTAJE_MOT_MEZCLADOR_S2", TagModel(current_value=96.0)).current_value,
        motor_c1_s2=tags_dict.get("MOTOR_C1_S2", TagModel(current_value=7.0)).current_value,
        porcentaje_m_c1_s2=tags_dict.get("PORCENTAJE_M_C1_S2", TagModel(current_value=0.9)).current_value,
    ))