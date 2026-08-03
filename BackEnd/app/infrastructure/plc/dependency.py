"""
Punto único de acceso al driver PLC compartido por todo el proceso.

Antes, `logger_service.py` y `control.py` creaban CADA UNO su propia
instancia de `PLCConnectionService`, lo que abría dos conexiones TCP/IP
independientes hacia el mismo PLC Siemens S7 (una para el logger de
background, otra para los endpoints de diagnóstico/control). Los CPUs
S7 tienen un límite bajo de conexiones concurrentes, así que esto podía
agotar ese margen sin necesidad.

Ahora la instancia real se crea UNA sola vez dentro del `lifespan` de
main.py y se guarda en `app.state.plc_driver`. Este módulo solo expone
un `Depends` para inyectarla en los endpoints que la necesiten.
"""
from fastapi import Request

from app.services.plc_service import PLCConnectionService


def get_plc_driver(request: Request) -> PLCConnectionService:
    """
    Devuelve la única instancia viva del driver PLC para todo el proceso.

    Uso en un endpoint:

        from fastapi import Depends
        from app.infrastructure.plc.dependency import get_plc_driver
        from app.services.plc_service import PLCConnectionService

        @router.get("/algo")
        async def algo(plc_service: PLCConnectionService = Depends(get_plc_driver)):
            ...
    """
    return request.app.state.plc_driver