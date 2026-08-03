from fastapi import APIRouter, Depends, HTTPException, Query, status, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from typing import Optional
import numpy as np
import pandas as pd
import io
from dateutil.parser import parse as parse_datetime
from app.database import get_db
from ....config import settings


from app.database import AsyncSessionLocal

router = APIRouter()

try:
    # Cargar la zona horaria configurada en el .env de forma dinámica
    ZONA_LOCAL = ZoneInfo(settings.APP_TIMEZONE)
except Exception:
    # Respaldo seguro en caso de que el string en el .env esté mal escrito
    ZONA_LOCAL = ZoneInfo("UTC")


# ==========================================
# ENDPOINT 1: TENDENCIAS Y LÍMITES SPC (GET)
# ==========================================
@router.get("/analytics/trends", tags=["Analítica de Producción y SPC"])
async def get_hardware_trends(
    linea: str = Query(..., description="Línea o componente matricial a consultar"),
    fecha_inicio: Optional[str] = Query(None, description="Fecha inicial del rango"),
    fecha_fin: Optional[str] = Query(None, description="Fecha final del rango"),
    agrupar_por: str = Query(default="crudo", description="Nivel de agregación de datos"),
    db: AsyncSession = Depends(get_db)
):
    """
    Endpoint analítico para la extracción de tendencias
    históricas y cálculo de límites SPC.
    """
    # 1. Normalización de segundos (Blindaje de formato ISO)
    if fecha_inicio and len(fecha_inicio) == 16:
        fecha_inicio += ":00"
    if fecha_fin and len(fecha_fin) == 16:
        fecha_fin += ":00"

    # 2. Validaciones de negocio preventivas
    if agrupar_por not in ["crudo", "1m", "5m", "1h", "1d"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El parámetro agrupar_por no contiene un intervalo válido."
        )

    if linea not in ["spunbond_1", "spunbond_2", "meltblown", "dosificacion_global"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="La línea especificada no es válida."
        )

    ahora = datetime.now(timezone.utc)
    
    # 3. Parseo y validación del rango de tiempo
    try:
        # 1. Capturar o parsear los inputs asumiendo que vienen en hora local de la planta
        if fecha_fin:
            f_fin_local = parse_datetime(fecha_fin)
            if f_fin_local.tzinfo is None:
                f_fin_local = f_fin_local.replace(tzinfo=ZONA_LOCAL)
        else:
            f_fin_local = datetime.now(ZONA_LOCAL)

        if fecha_inicio:
            f_inicio_local = parse_datetime(fecha_inicio)
            if f_inicio_local.tzinfo is None:
                f_inicio_local = f_inicio_local.replace(tzinfo=ZONA_LOCAL)
        else:
            f_inicio_local = f_fin_local - timedelta(hours=2)

        # 2. CONVERSIÓN CRÍTICA: Pasar a UTC para que la consulta BETWEEN en PostgreSQL sea exacta
        f_inicio = f_inicio_local.astimezone(timezone.utc)
        f_fin = f_fin_local.astimezone(timezone.utc)
            
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Formato de fecha no reconocible por el SCADA: {str(e)}"
        )

    if f_inicio >= f_fin:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="La fecha de inicio debe ser estrictamente anterior a la fecha de fin."
        )

    # 4. Mapeo dinámico de tablas de extrusión de tela no tejida
    tabla_mapeada = {
        "spunbond_1": "scada_history_extrusora_s1",
        "spunbond_2": "scada_history_extrusora_s2",
        "meltblown": "scada_history_extrusora_meltblown",
        "dosificacion_global": "scada_history_dosificacion_global"
    }.get(linea)

    # 5. Construcción de query de agregación temporal SQL
    if agrupar_por == "crudo":
        query_string = f"""
            SELECT * FROM {tabla_mapeada}
            WHERE timestamp BETWEEN :inicio AND :fin
            ORDER BY timestamp ASC;
        """
    else:
        intervalo_trunc = {
            "1m": "minute",
            "5m": "minute", 
            "1h": "hour",
            "1d": "day"
        }.get(agrupar_por, "minute")

        if linea == "dosificacion_global":
            columnas_promedio = """
                AVG(m_stock_rpm) as m_stock_rpm, AVG(dosificacion_mot_m) as dosificacion_mot_m,
                AVG(s1_stock_rpm) as s1_stock_rpm, AVG(dosificacion_mot_s1) as dosificacion_mot_s1,
                AVG(s2_stock_rpm) as s2_stock_rpm, AVG(dosificacion_mot_s2) as dosificacion_mot_s2
            """
        else:
            columnas_promedio = """
                AVG(pv_zona1) as pv_zona1, AVG(sp_zona1) as sp_zona1,
                AVG(pv_zona2) as pv_zona2, AVG(sp_zona2) as sp_zona2,
                AVG(pv_zona3) as pv_zona3, AVG(sp_zona3) as sp_zona3,
                AVG(pv_zona4) as pv_zona4, AVG(sp_zona4) as sp_zona4,
                AVG(pv_zona5) as pv_zona5, AVG(sp_zona5) as sp_zona5,
                AVG(pv_zona6) as pv_zona6, AVG(sp_zona6) as sp_zona6
            """

        query_string = f"""
            SELECT 
                date_trunc('{intervalo_trunc}', timestamp) as timestamp,
                {columnas_promedio}
            FROM {tabla_mapeada}
            WHERE timestamp BETWEEN :inicio AND :fin
            GROUP BY date_trunc('{intervalo_trunc}', timestamp)
            ORDER BY timestamp ASC;
        """

    # 6. Ejecución asíncrona y cálculo de analítica descriptiva
    try:
        result = await db.execute(text(query_string), {"inicio": f_inicio, "fin": f_fin})
        records = [dict(row._mapping) for row in result.fetchall()]

        statistics = {}
        if records:
            llaves_analizar = [k for k in records[0].keys() if k not in ["timestamp", "id"]]
            
            for llave in llaves_analizar:
                valores = [r[llave] for r in records if r[llave] is not None]
                if valores:
                    arr = np.array(valores, dtype=float)
                    promedio = float(np.mean(arr))
                    desviacion = float(np.std(arr))
                    
                    statistics[llave] = {
                        "maximo": round(float(np.max(arr)), 2),
                        "minimo": round(float(np.min(arr)), 2),
                        "promedio": round(promedio, 2),
                        "desviacion_estandar": round(desviacion, 2),
                        "lsc": round(promedio + (3 * desviacion), 2), 
                        "lic": round(promedio - (3 * desviacion), 2)  
                    }

        return {
            "status": "success",
            "linea": linea,
            "rango": {"desde": f_inicio.isoformat(), "hasta": f_fin.isoformat()},
            "agregacion_aplicada": agrupar_por,
            "total_puntos": len(records),
            "statistics": statistics,
            "data": records
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Fallo en la consulta analítica de base de datos: {str(e)}"
        )


# ==========================================
# ENDPOINT 2: EXPORTACIÓN HISTÓRICA A EXCEL
# ==========================================
@router.get("/analytics/export", tags=["Analítica de Producción y SPC"])
async def export_hardware_data(
    linea: str = Query(..., description="Línea industrial a exportar"),
    fecha_inicio: Optional[str] = Query(None, description="Fecha inicial del rango"),
    fecha_fin: Optional[str] = Query(None, description="Fecha final del rango"),
    agrupar_por: str = Query(default="crudo", description="Remuestreo para el reporte"),
    db: AsyncSession = Depends(get_db)
):
    """
    Genera y transmite un reporte en Excel (.xlsx) estructurado con los datos analíticos del proceso.
    """
    if fecha_inicio and len(fecha_inicio) == 16:
        fecha_inicio += ":00"
    if fecha_fin and len(fecha_fin) == 16:
        fecha_fin += ":00"

    if linea not in ["spunbond_1", "spunbond_2", "meltblown", "dosificacion_global"]:
        raise HTTPException(status_code=400, detail="Línea industrial no válida.")

    if agrupar_por not in ["crudo", "1m", "5m", "1h", "1d"]:
        raise HTTPException(status_code=400, detail="Agregación temporal no soportada.")

    ahora = datetime.now(timezone.utc)
    
    try:
        # 1. Capturar o parsear los inputs asumiendo que vienen en hora local de la planta
        if fecha_fin:
            f_fin_local = parse_datetime(fecha_fin)
            if f_fin_local.tzinfo is None:
                f_fin_local = f_fin_local.replace(tzinfo=ZONA_LOCAL)
        else:
            f_fin_local = datetime.now(ZONA_LOCAL)

        if fecha_inicio:
            f_inicio_local = parse_datetime(fecha_inicio)
            if f_inicio_local.tzinfo is None:
                f_inicio_local = f_inicio_local.replace(tzinfo=ZONA_LOCAL)
        else:
            f_inicio_local = f_fin_local - timedelta(hours=2)

        # 2. CONVERSIÓN CRÍTICA: Pasar a UTC para que la consulta BETWEEN en PostgreSQL sea exacta
        f_inicio = f_inicio_local.astimezone(timezone.utc)
        f_fin = f_fin_local.astimezone(timezone.utc)
            
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Formato de fecha no reconocible por el SCADA: {str(e)}"
        )

    if f_inicio >= f_fin:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="La fecha de inicio debe ser estrictamente anterior a la fecha de fin."
        )

    tabla_mapeada = {
        "spunbond_1": "scada_history_extrusora_s1",
        "spunbond_2": "scada_history_extrusora_s2",
        "meltblown": "scada_history_extrusora_meltblown",
        "dosificacion_global": "scada_history_dosificacion_global"
    }.get(linea)

    if agrupar_por == "crudo":
        query_string = f"SELECT * FROM {tabla_mapeada} WHERE timestamp BETWEEN :inicio AND :fin ORDER BY timestamp ASC;"
    else:
        intervalo_trunc = {"1m": "minute", "5m": "minute", "1h": "hour", "1d": "day"}.get(agrupar_por, "minute")
        columnas_promedio = (
            """
            AVG(m_stock_rpm) as m_stock_rpm, AVG(dosificacion_mot_m) as dosificacion_mot_m,
            AVG(s1_stock_rpm) as s1_stock_rpm, AVG(dosificacion_mot_s1) as dosificacion_mot_s1,
            AVG(s2_stock_rpm) as s2_stock_rpm, AVG(dosificacion_mot_s2) as dosificacion_mot_s2
            """
            if linea == "dosificacion_global" else
            """
            AVG(pv_zona1) as pv_zona1, AVG(sp_zona1) as sp_zona1,
            AVG(pv_zona2) as pv_zona2, AVG(sp_zona2) as sp_zona2,
            AVG(pv_zona3) as pv_zona3, AVG(sp_zona3) as sp_zona3,
            AVG(pv_zona4) as pv_zona4, AVG(sp_zona4) as sp_zona4,
            AVG(pv_zona5) as pv_zona5, AVG(sp_zona5) as sp_zona5,
            AVG(pv_zona6) as pv_zona6, AVG(sp_zona6) as sp_zona6
            """
        )
        query_string = f"""
            SELECT date_trunc('{intervalo_trunc}', timestamp) as timestamp, {columnas_promedio}
            FROM {tabla_mapeada} WHERE timestamp BETWEEN :inicio AND :fin
            GROUP BY date_trunc('{intervalo_trunc}', timestamp) ORDER BY timestamp ASC;
        """

    try:
        result = await db.execute(text(query_string), {"inicio": f_inicio, "fin": f_fin})
        records = [dict(row._mapping) for row in result.fetchall()]

        if not records:
            raise HTTPException(status_code=404, detail="No existen datos históricos en el rango seleccionado.")

        df = pd.DataFrame(records)
        
        if 'timestamp' in df.columns:
            df['timestamp'] = pd.to_datetime(df['timestamp']).dt.strftime('%Y-%m-%d %H:%M:%S')

        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name=f"Reporte_{linea[:10]}")
        output.seek(0)

        nombre_archivo = f"SCADA_{linea}_{f_inicio.strftime('%Y%md_%H%M')}_a_{f_fin.strftime('%Y%md_%H%M')}.xlsx"

        return StreamingResponse(
            output,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f"attachment; filename={nombre_archivo}"}
        )

    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Fallo crítico al estructurar archivo Excel: {str(e)}")

# ==========================================
# ENDPOINT 3: CÁLCULO ANALÍTICO DE OEE (GET)
# ==========================================
@router.get("/analytics/oee", tags=["Analítica de Producción y SPC"])
async def get_equipment_oee(
    linea: str = Query(..., description="Línea o componente a evaluar (spunbond_1, spunbond_2, meltblown)"),
    fecha_inicio: Optional[str] = Query(None, description="Fecha inicial del rango"),
    fecha_fin: Optional[str] = Query(None, description="Fecha final del rango"),
    db: AsyncSession = Depends(get_db)
):
    """
    Motor analítico retrospectivo de Solo Lectura: Evalúa la disponibilidad,
    rendimiento y calidad del proceso basándose en la telemetría histórica matricial.
    """
    # 1. Normalización de segundos (Blindaje de formato ISO)
    if fecha_inicio and len(fecha_inicio) == 16:
        fecha_inicio += ":00"
    if fecha_fin and len(fecha_fin) == 16:
        fecha_fin += ":00"

    if linea not in ["spunbond_1", "spunbond_2", "meltblown"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Línea no válida para el cálculo analítico de OEE."
        )

    # 2. Parseo y validación temporal con conversión crítica a UTC
    try:
        if fecha_fin:
            f_fin_local = parse_datetime(fecha_fin)
            if f_fin_local.tzinfo is None:
                f_fin_local = f_fin_local.replace(tzinfo=ZONA_LOCAL)
        else:
            f_fin_local = datetime.now(ZONA_LOCAL)

        if fecha_inicio:
            f_inicio_local = parse_datetime(fecha_inicio)
            if f_inicio_local.tzinfo is None:
                f_inicio_local = f_inicio_local.replace(tzinfo=ZONA_LOCAL)
        else:
            f_inicio_local = f_fin_local - timedelta(hours=24) # 24 horas por defecto para OEE

        f_inicio = f_inicio_local.astimezone(timezone.utc)
        f_fin = f_fin_local.astimezone(timezone.utc)
            
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Formato de fecha no reconocible: {str(e)}"
        )

    if f_inicio >= f_fin:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="La fecha de inicio debe ser anterior a la fecha de fin."
        )

    # 3. Mapeo dinámico de tablas de históricos
    tabla_mapeada = {
        "spunbond_1": "scada_history_extrusora_s1",
        "spunbond_2": "scada_history_extrusora_s2",
        "meltblown": "scada_history_extrusora_meltblown"
    }.get(linea)

    # 4. Extracción de variables de control térmico y dinámico
    # Nota: Usamos pv_zona2 como el punto crítico del barril para evaluar si el equipo está operando
    query_string = f"""
        SELECT timestamp, pv_zona2, sp_zona2 
        FROM {tabla_mapeada}
        WHERE timestamp BETWEEN :inicio AND :fin
        ORDER BY timestamp ASC;
    """

    try:
        result = await db.execute(text(query_string), {"inicio": f_inicio, "fin": f_fin})
        records = [dict(row._mapping) for row in result.fetchall()]

        if not records:
            return {
                "status": "empty",
                "linea": linea,
                "oee_global": 0.0,
                "kpis": {"disponibilidad": 0.0, "rendimiento": 0.0, "calidad": 0.0},
                "message": "No se encontraron registros en el rango seleccionado para calcular el OEE."
            }

        # 5. ALGORITMO VECTORIAL CON NUMPY (Alta velocidad)
        df_oee = pd.DataFrame(records)
        total_puntos = len(df_oee)

        # A. DISPONIBILIDAD: Si pv_zona2 > 50°C la extrusora está físicamente encendida/caliente (operativa)
        df_oee["is_running"] = df_oee["pv_zona2"] > 50.0
        puntos_operando = int(df_oee["is_running"].sum())

        if puntos_operando == 0:
            return {
                "status": "success",
                "linea": linea,
                "total_muestras": total_puntos,
                "kpis": {"disponibilidad": 0.0, "rendimiento": 0.0, "calidad": 0.0, "oee_global": 0.0},
                "message": "La línea se mantuvo completamente apagada o en mantenimiento en este rango."
            }

        disponibilidad = (puntos_operando / total_puntos) * 100.0

        # Filtrar el dataframe solo para los momentos donde la máquina estuvo operando
        df_running = df_oee[df_oee["is_running"] == True].copy()

        # B. RENDIMIENTO: Capacidad térmica real versus el setpoint ideal (Capado a un máximo de 100%)
        # Evitamos divisiones por cero si sp_zona2 es inconsistente
        df_running["eficiencia_vel"] = np.where(
            df_running["sp_zona2"] > 0, 
            df_running["pv_zona2"] / df_running["sp_zona2"], 
            0.0
        )
        # Se consideran puntos óptimos aquellos que rinden a más del 90% de la consigna configurada
        puntos_rendimiento_optimo = int((df_running["eficiencia_vel"] >= 0.90).sum())
        rendimiento = (puntos_rendimiento_optimo / puntos_operando) * 100.0

        # C. CALIDAD: Estabilidad del proceso de extrusión de tela no tejida
        # Si la temperatura fluctúa más de ±10°C del setpoint, el polímero pierde homogeneidad (Scrap automático)
        df_running["desviacion_termica"] = np.abs(df_running["pv_zona2"] - df_running["sp_zona2"])
        puntos_buena_calidad = int((df_running["desviacion_termica"] <= 10.0).sum())
        calidad = (puntos_buena_calidad / puntos_operando) * 100.0

        # D. OEE GLOBAL (Multiplicación de tasas decimales)
        oee_global = (disponibilidad / 100.0) * (rendimiento / 100.0) * (calidad / 100.0) * 100.0

        return {
            "status": "success",
            "linea": linea,
            "rango_analizado": {
                "desde": f_inicio.astimezone(ZONA_LOCAL).strftime('%Y-%m-%d %H:%M:%S'),
                "hasta": f_fin.astimezone(ZONA_LOCAL).strftime('%Y-%m-%d %H:%M:%S')
            },
            "total_muestras_analizadas": total_puntos,
            "kpis": {
                "disponibilidad": round(disponibilidad, 2),
                "rendimiento": round(rendimiento, 2),
                "calidad": round(calidad, 2),
                "oee_global": round(oee_global, 2)
            },
            "detalles": {
                "puntos_en_paro": total_puntos - puntos_operando,
                "puntos_en_produccion": puntos_operando
            }
        }

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error crítico en el cálculo del OEE de planta: {str(e)}"
        )