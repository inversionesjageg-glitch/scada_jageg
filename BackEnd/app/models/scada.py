# BackEnd/app/models/scada.py
import logging
import re
from sqlalchemy import Column, Integer, String, Float, Boolean, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.ext.hybrid import hybrid_property
from datetime import datetime, timezone
from ..database import Base

logger = logging.getLogger("SCADA_Jageg_Models")

# ==============================================================================
# CONTENEDOR 1: CONTROL DE TIEMPO REAL Y ALERTAS (PERSISTENCIA VIVA)
# ==============================================================================

class TagModel(Base):
    """
    Mantiene el estado vivo de la Máquina 3. Aquí el simulador/worker hace UPDATES cada 1s.
    De aquí el WebSocket toma los datos crudos para el streaming en tiempo real.
    """
    __tablename__ = "scada_tags"

    id = Column(Integer, primary_key=True, index=True)
    tag_name = Column(String(100), unique=True, index=True, nullable=False) # Ej: "S1_PV_Z1", "M_STOCK_RPM"
    description = Column(String(255), nullable=True)
    data_type = Column(String(50), nullable=False, default="FLOAT")
    unit = Column(String(20), nullable=True)
    current_value = Column(Float, default=0.0) # Modificado constantemente por el hardware o simulador
    is_simulated = Column(Boolean, default=True)

    # --------------------------------------------------------------------------
    # 🆕 DIRECCIONAMIENTO FÍSICO S7 EXTENDIDO
    # --------------------------------------------------------------------------
    # El diseño original solo contemplaba el área de Data Blocks (DB), pero el
    # export real de WinCC (1362 tags con dirección física) mostró que ~49% de
    # los tags de la Máquina 3 viven en Entradas (I), Salidas (Q), Marcas
    # (M/MB/MW/MD) y Periféricos (PIW). Se agregan `plc_area` y `plc_width`
    # para poder representar cualquiera de esas zonas sin perder la capacidad
    # de reconstruir el string original.
    #
    #   plc_area  : "DB" | "M" | "I" | "Q" | "PIW"
    #   plc_db    : número de Data Block (solo aplica si plc_area == "DB")
    #   plc_width : "X" (bit) | "B" (byte) | "W" (word/int) | "D" (dword/real)
    #   plc_byte  : offset de byte dentro del área
    #   plc_bit   : índice de bit (solo si plc_width == "X")
    plc_area = Column(String(10), nullable=True, default="DB")
    plc_db = Column(Integer, nullable=True)     # Bloque de datos (Ej: 33, 34, 42) — solo área DB
    plc_width = Column(String(2), nullable=True)  # 'X' | 'B' | 'W' | 'D'
    plc_byte = Column(Integer, nullable=True)   # Offset del byte (Ej: 6, 14, 30)
    plc_bit = Column(Integer, nullable=True)    # Índice del bit para booleanos (Ej: 0, 1, 2)

    # Patrones de parseo reutilizados por el setter (compilados una sola vez)
    _RE_DB_BIT = re.compile(r"^DB(\d+)\.DBX(\d+)\.(\d+)$")
    _RE_DB_WIDTH = re.compile(r"^DB(\d+)\.DB([BWD])(\d+)$")
    _RE_MIQ_BIT = re.compile(r"^([MIQ])(\d+)\.(\d+)$")
    _RE_M_WIDTH = re.compile(r"^M([BWD])(\d+)$")
    _RE_PIW = re.compile(r"^PIW(\d+)$")

    @hybrid_property
    def direccion_fisica(self) -> str:
        """Reconstruye el string de dirección física a partir de los campos normalizados."""
        if self.plc_area is None or self.plc_byte is None:
            return "N/A"

        if self.plc_area == "DB":
            if self.plc_db is None:
                return "N/A"
            if self.plc_width == "X":
                return f"DB{self.plc_db}.DBX{self.plc_byte}.{self.plc_bit}"
            return f"DB{self.plc_db}.DB{self.plc_width or 'D'}{self.plc_byte}"

        if self.plc_area in ("M", "I", "Q"):
            if self.plc_width == "X" or self.plc_width is None:
                return f"{self.plc_area}{self.plc_byte}.{self.plc_bit}"
            return f"{self.plc_area}{self.plc_width}{self.plc_byte}"

        if self.plc_area == "PIW":
            return f"PIW{self.plc_byte}"

        return "N/A"

    @direccion_fisica.setter
    def direccion_fisica(self, direccion: str):
        """
        Acepta el formato compacto propio del proyecto para cualquier área S7:
          - 'DB33.DBW154'      -> Data Block, word
          - 'DB42.DBX30.0'     -> Data Block, bit
          - 'M120.7'           -> Marca, bit
          - 'MB9' / 'MW4' / 'MD5' -> Marca, byte/word/dword
          - 'I10.0' / 'Q11.2'  -> Entrada / Salida, bit
          - 'PIW752'           -> Entrada periférica, word
        """
        if not direccion:
            self.plc_area = None
            self.plc_db = None
            self.plc_width = None
            self.plc_byte = None
            self.plc_bit = None
            return

        direccion_limpia = direccion.upper().replace(" ", "")

        m = self._RE_DB_BIT.match(direccion_limpia)
        if m:
            db, byte, bit = m.groups()
            self.plc_area, self.plc_db = "DB", int(db)
            self.plc_width, self.plc_byte, self.plc_bit = "X", int(byte), int(bit)
            return

        m = self._RE_DB_WIDTH.match(direccion_limpia)
        if m:
            db, width, byte = m.groups()
            self.plc_area, self.plc_db = "DB", int(db)
            self.plc_width, self.plc_byte, self.plc_bit = width, int(byte), None
            return

        m = self._RE_MIQ_BIT.match(direccion_limpia)
        if m:
            area, byte, bit = m.groups()
            self.plc_area, self.plc_db = area, None
            self.plc_width, self.plc_byte, self.plc_bit = "X", int(byte), int(bit)
            return

        m = self._RE_M_WIDTH.match(direccion_limpia)
        if m:
            width, byte = m.groups()
            self.plc_area, self.plc_db = "M", None
            self.plc_width, self.plc_byte, self.plc_bit = width, int(byte), None
            return

        m = self._RE_PIW.match(direccion_limpia)
        if m:
            byte = m.group(1)
            self.plc_area, self.plc_db = "PIW", None
            self.plc_width, self.plc_byte, self.plc_bit = "W", int(byte), None
            return

        logger.error(f"Error parseando dirección física recibida '{direccion}': formato no reconocido")
        raise ValueError(
            "Formato de dirección física inválido. Ejemplos válidos: 'DB33.DBW154', "
            "'DB42.DBX30.0', 'M120.7', 'MB9', 'I10.0', 'Q11.2', 'PIW752'."
        )
    # --------------------------------------------------------------------------

    limit_high_high = Column(Float, nullable=True)
    limit_high = Column(Float, nullable=True)
    limit_low = Column(Float, nullable=True)
    limit_low_low = Column(Float, nullable=True)

    alarms = relationship("AlarmModel", back_populates="tag", cascade="all, delete-orphan", lazy="raise_on_sql")

class AlarmModel(Base):
    """
    Gestiona el ciclo de vida de las alarmas activas e históricas de la planta.
    Se han homologado todas las estampas de tiempo a DateTime(timezone=True).
    """
    __tablename__ = "scada_alarms"

    id = Column(Integer, primary_key=True, index=True)
    tag_id = Column(Integer, ForeignKey("scada_tags.id", ondelete="CASCADE"), nullable=False)
    alarm_type = Column(String(50), nullable=False) # Ej: "HIGH_HIGH", "LOW_LOW"
    message = Column(String(255), nullable=False)
    severity = Column(String(20), default="WARNING") # INFO, WARNING, CRITICAL
    
    timestamp_active = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    timestamp_ack = Column(DateTime(timezone=True), nullable=True)
    timestamp_cleared = Column(DateTime(timezone=True), nullable=True)
    
    is_active = Column(Boolean, default=True)
    is_acknowledged = Column(Boolean, default=False)

    tag = relationship("TagModel", back_populates="alarms", lazy="raise_on_sql")


class TagHistoryModel(Base):
    """
    Respaldo genérico e individual (EAV). Se mantiene para auditoría profunda 
    o variables huérfanas que no formen parte de los bloques matriciales principales.
    """
    __tablename__ = "scada_tag_history"

    id = Column(Integer, primary_key=True, index=True)
    tag_id = Column(Integer, ForeignKey("scada_tags.id", ondelete="CASCADE"), nullable=False)
    value = Column(Float, nullable=False)
    timestamp = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True)


# ==============================================================================
# CONTENEDOR 2: HISTÓRICOS MATRICIALES (OPTIMIZADOS PARA TENDENCIAS Y GRÁFICAS)
# ==============================================================================

class HistoricoExtrusoraS1Model(Base):
    """
    Ventana: Historicos_S1
    Fotografía térmica de S1 guardada de forma periódica (DB2 - 60 Bytes).
    """
    __tablename__ = "scada_history_extrusora_s1"

    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True)

    pv_zona1 = Column(Float, nullable=False)
    sp_zona1 = Column(Float, nullable=False)
    pv_zona2 = Column(Float, nullable=False)
    sp_zona2 = Column(Float, nullable=False)
    pv_zona3 = Column(Float, nullable=False)
    sp_zona3 = Column(Float, nullable=False)
    pv_zona4 = Column(Float, nullable=False)
    sp_zona4 = Column(Float, nullable=False)
    pv_zona5 = Column(Float, nullable=False)
    sp_zona5 = Column(Float, nullable=False)
    pv_zona6 = Column(Float, nullable=False)
    sp_zona6 = Column(Float, nullable=False)


class HistoricoExtrusoraS2Model(Base):
    """
    Ventana: Historicos_S2
    Perfil térmico completo de la extrusora correspondiente a la Capa Externa S2 (DB3 - 60 Bytes).
    """
    __tablename__ = "scada_history_extrusora_s2"

    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True)

    pv_zona1 = Column(Float, nullable=False)
    sp_zona1 = Column(Float, nullable=False)
    pv_zona2 = Column(Float, nullable=False)
    sp_zona2 = Column(Float, nullable=False)
    pv_zona3 = Column(Float, nullable=False)
    sp_zona3 = Column(Float, nullable=False)
    pv_zona4 = Column(Float, nullable=False)
    sp_zona4 = Column(Float, nullable=False)
    pv_zona5 = Column(Float, nullable=False)
    sp_zona5 = Column(Float, nullable=False)
    pv_zona6 = Column(Float, nullable=False)
    sp_zona6 = Column(Float, nullable=False)


class HistoricoExtrusoraMeltblownModel(Base):
    """
    Ventana: Historicos_M_Ext
    Mapea el perfil de precalentamiento y fusión de la extrusora central Meltblown (DB4 - 60 Bytes).
    """
    __tablename__ = "scada_history_extrusora_meltblown"

    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True)

    pv_zona1 = Column(Float, nullable=False)
    sp_zona1 = Column(Float, nullable=False)
    pv_zona2 = Column(Float, nullable=False)
    sp_zona2 = Column(Float, nullable=False)
    pv_zona3 = Column(Float, nullable=False)
    sp_zona3 = Column(Float, nullable=False)
    pv_zona4 = Column(Float, nullable=False)
    sp_zona4 = Column(Float, nullable=False)
    pv_zona5 = Column(Float, nullable=False)
    sp_zona5 = Column(Float, nullable=False)
    pv_zona6 = Column(Float, nullable=False)
    sp_zona6 = Column(Float, nullable=False)


class HistoricoProcesoMecanicoModel(Base):
    """
    Ventana: Historicos_Proceso_Mecanico
    Registra presiones críticas de cabezal, prefiltros, circuitos de aceite y enfriamiento (DB5 - 52 Bytes).
    """
    __tablename__ = "scada_history_proceso_mecanico"

    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True)

    # --- Retornos de Aceite e Intercambiadores ---
    sp_rbody = Column(Float, nullable=False)           # DB5.DBD0
    pv_rbody = Column(Float, nullable=False)           # DB5.DBD4
    sp_coolarea = Column(Float, nullable=False)        # DB5.DBD8
    pv_coolarea = Column(Float, nullable=False)        # DB5.DBD12
    sp_coolfan = Column(Float, nullable=False)         # DB5.DBD16
    pv_coolfan = Column(Float, nullable=False)         # DB5.DBD20
    
    # --- Presiones Hidráulicas ---
    sv1_filter_ex_pre = Column(Float, nullable=False)  # DB5.DBD24
    sv2_filter_ex_pre = Column(Float, nullable=False)  # DB5.DBD28
    pv_filter_ex_pre = Column(Float, nullable=False)   # DB5.DBD32
    sp_die_pre = Column(Float, nullable=False)          # DB5.DBD36
    pv_die_pre = Column(Float, nullable=False)          # DB5.DBD40

    # --- Rodillo Grafito ---
    rgrafito_temp_sp = Column(Float, nullable=False)   # DB5.DBD44
    rgrafito_temp_pv = Column(Float, nullable=False)   # DB5.DBD48


class HistoricoMotoresVelocidadesModel(Base):
    """
    Ventana: Historicos_Velocidades
    Almacena las RPMs reales y consignas de motores, VDFs y drivers DC en planta (DB6 - 48 Bytes).
    """
    __tablename__ = "scada_history_motores_velocidades"

    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True)

    sp_bomba_hiladora = Column(Float, nullable=False)  # DB6.DBD0
    pv_bomba_hiladora = Column(Float, nullable=False)  # DB6.DBD4
    sp_m_incoex_rpm = Column(Float, nullable=False)    # DB6.DBD8
    pv_m_incoex_rpm = Column(Float, nullable=False)    # DB6.DBD12
    sp_m_monomero = Column(Float, nullable=False)      # DB6.DBD16
    pv_m_monomero = Column(Float, nullable=False)      # DB6.DBD20
    sp_m_cooling = Column(Float, nullable=False)       # DB6.DBD24
    pv_m_cooling = Column(Float, nullable=False)       # DB6.DBD28
    sp_m_chiladora = Column(Float, nullable=False)     # DB6.DBD32
    pv_m_chiladora = Column(Float, nullable=False)     # DB6.DBD36
    sp_m_suction = Column(Float, nullable=False)       # DB6.DBD40
    pv_m_suction = Column(Float, nullable=False)       # DB6.DBD44


class HistoricoDosificacionGlobalModel(Base):
    """
    Ventana: Historico_Dosificacion
    Estructura analítica integrada. Recibe los parámetros activos de Meltblown desde DB7 (20 Bytes).
    Los campos de S1 y S2 se dejan como nulos (True) para expansiones o cargas interbucle.
    """
    __tablename__ = "scada_history_dosificacion_global"

    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True)

    # --- Capa Central: Meltblown (M) -> Provisto por DB7 ---
    m_stock_rpm = Column(Float, nullable=False)                 # DB7.DBD0
    dosificacion_mot_m = Column(Float, nullable=False)          # DB7.DBD4
    porcentaje_mot_mezclador_m = Column(Float, nullable=False)  # DB7.DBD8
    motor_c1_m = Column(Float, nullable=False)                  # DB7.DBD12
    motor_c2_m = Column(Float, nullable=False)                  # DB7.DBD16
    porcentaje_m_c1_m = Column(Float, nullable=True)
    porcentaje_m_c2_m = Column(Float, nullable=True)

    # --- Capa Externa: S1 (Estructura lista, mapeo diferido) ---
    s1_stock_rpm = Column(Float, nullable=True)
    dosificacion_mot_s1 = Column(Float, nullable=True)
    porcentaje_mot_mezclador_s1 = Column(Float, nullable=True)
    motor_c1_s1 = Column(Float, nullable=True)
    porcentaje_m_c1_s1 = Column(Float, nullable=True)

    # --- Capa Externa: S2 (Estructura lista, mapeo diferido) ---
    s2_stock_rpm = Column(Float, nullable=True)
    dosificacion_mot_s2 = Column(Float, nullable=True)
    porcentaje_mot_mezclador_s2 = Column(Float, nullable=True)
    motor_c1_s2 = Column(Float, nullable=True)
    porcentaje_m_c1_s2 = Column(Float, nullable=True)


# ==============================================================================
# CONTENEDOR 3: ANALÍTICAS DE PLANTA
# ==============================================================================

class OEELogModel(Base):
    """
    Contenedor analítico que consolida los indicadores de productividad (OEE)
    calculados a partir de la telemetría histórica matricial.
    """
    __tablename__ = "scada_analytics_oee"

    id = Column(Integer, primary_key=True, index=True)
    linea = Column(String(50), nullable=False, index=True) # spunbond_1, spunbond_2, meltblown
    timestamp_calculo = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True)
    
    # Rango temporal evaluado
    fecha_inicio = Column(DateTime(timezone=True), nullable=False)
    fecha_fin = Column(DateTime(timezone=True), nullable=False)

    # Indicadores Clave (Métricas 0.0 a 100.0 %)
    disponibilidad = Column(Float, nullable=False)
    rendimiento = Column(Float, nullable=False)
    calidad = Column(Float, nullable=False)
    oee_total = Column(Float, nullable=False)
    
    # Datos de soporte analítico
    minutos_operativos = Column(Float, nullable=False)
    minutos_parada = Column(Float, nullable=False)