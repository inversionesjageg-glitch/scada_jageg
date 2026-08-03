# BackEnd/app/api/v1/endpoints/history.py
from fastapi import APIRouter, Query, HTTPException, status
from app.services.plc_service import PLCConnectionService

router = APIRouter()

@router.get("/plc/validate", tags=["Hardware Industrial"])
def validate_plc_connection(
    ip: str = Query("192.168.2.230", description="Dirección IP del PLC Real"),
    rack: int = Query(0, description="Número de rack físico"),
    slot: int = Query(2, description="Slot de la CPU 315")
):
    """
    Endpoint técnico para auditar el estado del enlace con el PLC.
    Lanza una conexión S7 directa en tiempo real y reporta si el hardware está operativo (RUN/STOP).
    """
    plc_service = PLCConnectionService(ip_address=ip, rack=rack, slot=slot)
    result = plc_service.check_connection()
    
    if not result["connected"]:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=result
        )
        
    return result

@router.get("/plc/read-block/spunbond1", tags=["Hardware Industrial"])
def get_spunbond_1_data(
    ip: str = Query("192.168.2.230", description="Dirección IP del PLC Real"),
    rack: int = Query(0, description="Rack físico"),
    slot: int = Query(2, description="Slot de la CPU")
):
    """
    Lanza una lectura directa en ráfaga (Burst Read) al DB2 del PLC real.
    """
    plc_service = PLCConnectionService(ip_address=ip, rack=rack, slot=slot)
    if not plc_service.asegurar_conexion():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"status": "error", "message": f"No se pudo conectar al PLC {ip}"}
        )
    try:
        data = plc_service.read_extrusion_zones(db_number=2, tag_prefix="S1")
        return {
            "status": "success",
            "plc_ip": ip,
            "db_read": 2,
            "linea": "Spunbond 1",
            "data": data
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"status": "error", "message": str(e)}
        )

@router.get("/plc/read-block/spunbond2", tags=["Hardware Industrial"])
def get_spunbond_2_data(
    ip: str = Query("192.168.2.230", description="Dirección IP del PLC Real"),
    rack: int = Query(0, description="Rack físico"),
    slot: int = Query(2, description="Slot de la CPU")
):
    """
    Lanza una lectura directa en ráfaga (Burst Read) al DB3 del PLC real.
    """
    plc_service = PLCConnectionService(ip_address=ip, rack=rack, slot=slot)
    if not plc_service.asegurar_conexion():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"status": "error", "message": f"No se pudo conectar al PLC {ip}"}
        )
    try:
        data = plc_service.read_extrusion_zones(db_number=3, tag_prefix="S2")
        return {
            "status": "success",
            "plc_ip": ip,
            "db_read": 3,
            "linea": "Spunbond 2",
            "data": data
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"status": "error", "message": str(e)}
        )

@router.get("/plc/read-block/meltblown", tags=["Hardware Industrial"])
def get_meltblown_data(
    ip: str = Query("192.168.2.230", description="Dirección IP del PLC Real"),
    rack: int = Query(0, description="Rack físico"),
    slot: int = Query(2, description="Slot de la CPU")
):
    """
    Lanza una lectura directa en ráfaga (Burst Read) al DB4 del PLC real.
    """
    plc_service = PLCConnectionService(ip_address=ip, rack=rack, slot=slot)
    if not plc_service.asegurar_conexion():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"status": "error", "message": f"No se pudo conectar al PLC {ip}"}
        )
    try:
        data = plc_service.read_extrusion_zones(db_number=4, tag_prefix="M")
        return {
            "status": "success",
            "plc_ip": ip,
            "db_read": 4,
            "linea": "Meltblown",
            "data": data
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"status": "error", "message": str(e)}
        )
        
@router.get("/plc/read-block/motors", tags=["Hardware Industrial"])
def get_plc_motors_data(
    ip: str = Query("192.168.2.230", description="Dirección IP del PLC Real"),
    rack: int = Query(0, description="Rack físico"),
    slot: int = Query(2, description="Slot de la CPU")
):
    """
    Lanza una lectura en ráfaga al DB6 del PLC real.
    """
    plc_service = PLCConnectionService(ip_address=ip, rack=rack, slot=slot)
    if not plc_service.asegurar_conexion():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"status": "error", "message": f"No se pudo conectar al PLC {ip}"}
        )
    try:
        # Pasamos explícitamente el db_number para mantener consistencia con los demás endpoints
        data = plc_service.read_motor_speeds(db_number=6)
        return {
            "status": "success",
            "plc_ip": ip,
            "db_read": 6,
            "seccion": "Motores y Variadores",
            "data": data
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"status": "error", "message": str(e)}
        )