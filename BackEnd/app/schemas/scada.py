# BackEnd/app/schemas/scada.py
from pydantic import BaseModel, Field, ConfigDict
from typing import Optional, List
from datetime import datetime

# ==============================================================================
# SUB-MODULO: TAGS Y ADQUISICIÓN EN VIVO
# ==============================================================================
class TagResponseSchema(BaseModel):
    id: int
    tag_name: str
    description: Optional[str] = None
    data_type: str
    unit: Optional[str] = None
    direccion_fisica: Optional[str] = "N/A"
    current_value: Optional[float] = 0.0
    is_simulated: bool
    plc_db: Optional[int] = None
    plc_byte: Optional[int] = None
    plc_bit: Optional[int] = None
    limit_high_high: Optional[float] = None
    limit_high: Optional[float] = None
    limit_low: Optional[float] = None
    limit_low_low: Optional[float] = None

    model_config = ConfigDict(from_attributes=True)

class TagCreate(BaseModel):
    tag_name: str = Field(..., max_length=100, description="Ej: S1_PV_Z1")
    description: Optional[str] = Field(None, max_length=255)
    data_type: str = Field("FLOAT", max_length=50)
    unit: Optional[str] = Field(None, max_length=20)
    direccion_fisica: Optional[str] = Field(None, description="Formatos aceptados: DB2.DBD0")
    is_simulated: Optional[bool] = True
    limit_high_high: Optional[float] = None
    limit_high: Optional[float] = None
    limit_low: Optional[float] = None
    limit_low_low: Optional[float] = None

# ==============================================================================
# SUB-MODULO: ALARMAS Y EVENTOS
# ==============================================================================
class AlarmResponseSchema(BaseModel):
    id: int
    tag_id: int
    alarm_type: str
    message: str
    severity: str
    timestamp_active: datetime
    timestamp_ack: Optional[datetime] = None
    timestamp_cleared: Optional[datetime] = None
    is_active: bool
    is_acknowledged: bool

    model_config = ConfigDict(from_attributes=True)

class AlarmAcknowledgePayload(BaseModel):
    alarm_ids: List[int]

# ==============================================================================
# SUB-MODULO: HISTÓRICOS MATRICIALES (Para Tendencias del Frontend)
# ==============================================================================
class HistoricoExtrusoraS1Response(BaseModel):
    id: int; timestamp: datetime
    pv_zona1: float; sp_zona1: float; pv_zona2: float; sp_zona2: float
    pv_zona3: float; sp_zona3: float; pv_zona4: float; sp_zona4: float
    pv_zona5: float; sp_zona5: float; pv_zona6: float; sp_zona6: float
    model_config = ConfigDict(from_attributes=True)

class HistoricoExtrusoraS2Response(BaseModel):
    id: int; timestamp: datetime
    pv_zona1: float; sp_zona1: float; pv_zona2: float; sp_zona2: float
    pv_zona3: float; sp_zona3: float; pv_zona4: float; sp_zona4: float
    pv_zona5: float; sp_zona5: float; pv_zona6: float; sp_zona6: float
    model_config = ConfigDict(from_attributes=True)

class HistoricoExtrusoraMeltblownResponse(BaseModel):
    id: int; timestamp: datetime
    pv_zona1: float; sp_zona1: float; pv_zona2: float; sp_zona2: float
    pv_zona3: float; sp_zona3: float; pv_zona4: float; sp_zona4: float
    pv_zona5: float; sp_zona5: float; pv_zona6: float; sp_zona6: float
    model_config = ConfigDict(from_attributes=True)

class HistoricoProcesoMecanicoResponse(BaseModel):
    id: int; timestamp: datetime
    sp_rbody: float; pv_rbody: float; sp_coolarea: float; pv_coolarea: float
    sp_coolfan: float; pv_coolfan: float; rgrafito_temp_sp: float; rgrafito_temp_pv: float
    sv1_filter_ex_pre: float; sv2_filter_ex_pre: float; pv_filter_ex_pre: float
    sp_die_pre: float; pv_die_pre: float
    model_config = ConfigDict(from_attributes=True)

class HistoricoMotoresVelocidadesResponse(BaseModel):
    id: int; timestamp: datetime
    sp_bomba_hiladora: float; pv_bomba_hiladora: float
    sp_m_incoex_rpm: float; pv_m_incoex_rpm: float
    sp_m_monomero: float; pv_m_monomero: float
    sp_m_cooling: float; pv_m_cooling: float
    sp_m_chiladora: float; pv_m_chiladora: float
    sp_m_suction: float; pv_m_suction: float
    model_config = ConfigDict(from_attributes=True)

class HistoricoDosificacionGlobalResponse(BaseModel):
    id: int; timestamp: datetime
    m_stock_rpm: float; dosificacion_mot_m: float; porcentaje_mot_mezclador_m: float
    motor_c1_m: float; motor_c2_m: float
    porcentaje_m_c1_m: Optional[float] = None; porcentaje_m_c2_m: Optional[float] = None
    s1_stock_rpm: Optional[float] = None; dosificacion_mot_s1: Optional[float] = None
    s2_stock_rpm: Optional[float] = None; dosificacion_mot_s2: Optional[float] = None
    model_config = ConfigDict(from_attributes=True)

# ==============================================================================
# SUB-MODULO: ANALÍTICAS Y KPIs
# ==============================================================================
class OEELogResponse(BaseModel):
    id: int; linea: str; timestamp_calculo: datetime
    fecha_inicio: datetime; fecha_fin: datetime
    disponibilidad: float; rendimiento: float; calidad: float; oee_total: float
    minutos_operativos: float; minutos_parada: float
    model_config = ConfigDict(from_attributes=True)

# ==============================================================================
# SUB-MODULO: HARDWARE (Payload de Inyección Masiva del Driver PLC)
# ==============================================================================
class PLCTagsPayload(BaseModel):
    # Fluido térmico, presiones e intercambiador (DB5)
    SP_RBODY: float; PV_RBODY: float; SP_COOLAREA: float; PV_COOLAREA: float
    SP_COOLFAN: float; PV_COOLFAN: float; SV1_FILTER_EX_PRE: float; SV2_FILTER_EX_PRE: float
    PV_FILTER_EX_PRE: float; SP_DIE_PRE: float; PV_DIE_PRE: float
    RGRAFITO_TEMP_SP: float; RGRAFITO_TEMP_PV: float

    # Motores, variadores e hiladora (DB6)
    SP_BOMBA_HILADORA: float; PV_BOMBA_HILADORA: float
    SP_M_INCOEX_RPM: float; PV_M_INCOEX_RPM: float
    SP_M_MONOMERO: float; PV_M_MONOMERO: float
    SP_M_COOLING: float; PV_M_COOLING: float
    SP_M_CHILADORA: float; PV_M_CHILADORA: float
    SP_M_SUCTION: float; PV_M_SUCTION: float

    # Bloques Térmicos S1 (DB2)
    S1_PV_Z1: float; S1_SP_Z1: float; S1_PV_Z2: float; S1_SP_Z2: float
    S1_PV_Z3: float; S1_SP_Z3: float; S1_PV_Z4: float; S1_SP_Z4: float
    S1_PV_Z5: float; S1_SP_Z5: float; S1_PV_Z6: float; S1_SP_Z6: float

    # Bloques Térmicos S2 (DB3)
    S2_PV_Z1: float; S2_SP_Z1: float; S2_PV_Z2: float; S2_SP_Z2: float
    S2_PV_Z3: float; S2_SP_Z3: float; S2_PV_Z4: float; S2_SP_Z4: float
    S2_PV_Z5: float; S2_SP_Z5: float; S2_PV_Z6: float; S2_SP_Z6: float

    # Bloques Térmicos Meltblown (DB4)
    M_PV_Z1: float; M_SP_Z1: float; M_PV_Z2: float; M_SP_Z2: float
    M_PV_Z3: float; M_SP_Z3: float; M_PV_Z4: float; M_SP_Z4: float
    M_PV_Z5: float; M_SP_Z5: float; M_PV_Z6: float; M_SP_Z6: float