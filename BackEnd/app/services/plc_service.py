# BackEnd/app/services/plc_service.py
import logging
import threading
import snap7
from snap7.util import get_real

logger = logging.getLogger("SCADA_Jageg_PLC")

class PLCConnectionService:
    TEMP_MIN_LOGICA = 0.0      
    TEMP_MAX_LOGICA = 350.0    
    MOTOR_MIN_LOGICO = 0.0
    MOTOR_MAX_LOGICO = 2500.0  

    def __init__(self, ip_address: str = "192.168.2.230", rack: int = 0, slot: int = 2):
        self.ip_address = ip_address
        self.rack = rack
        self.slot = slot
        self._client = snap7.client.Client()
        # 🆕 LOCK DE SOCKET: snap7.client.Client NO es seguro para acceso
        # concurrente desde múltiples hilos. Desde que esta instancia se
        # comparte entre SCADALoggerService (loop de background cada 30s) y
        # los endpoints de diagnóstico/control (que pueden lanzar decenas o
        # cientos de lecturas individuales en una sola auditoría), dos hilos
        # podían terminar golpeando el mismo socket al mismo tiempo,
        # corrompiendo la comunicación S7 y produciendo fallos en cascada
        # incluso en tags que sabíamos que leían bien. Todo método que toque
        # `self._client` adquiere este lock primero.
        self._socket_lock = threading.Lock()

    @property
    def plc(self):
        """
        PROPIEDAD PUENTE: Expone el cliente interno de Snap7 como '.plc'
        para solucionar el AttributeError en el SCADALoggerService dinámico.

        ⚠️ Si vas a usar `.plc` para leer/escribir directamente desde afuera
        de esta clase, adquiere `self._socket_lock` tú mismo — este bridge
        no lo hace por ti, solo expone el objeto.
        """
        return self._client

    def asegurar_conexion(self) -> bool:
        with self._socket_lock:
            if self._client.get_connected():
                return True
            try:
                self._client.connect(self.ip_address, self.rack, self.slot)
                return self._client.get_connected()
            except Exception:
                return False

    def check_connection(self) -> dict:
        es_valido = self.asegurar_conexion()
        return {
            "connected": es_valido,
            "ip": self.ip_address,
            "cpu_state": "RUN" if es_valido else "OFFLINE",
            "message": "Enlace activo con hardware real" if es_valido else "PLC No alcanzable"
        }

    def disconnect(self):
        with self._socket_lock:
            if self._client.get_connected():
                self._client.disconnect()

    def leer_area(self, area: str, start: int, size: int, db_number: int | None = None) -> bytes:
        """
        Lectura genérica por área de memoria S7.

          area="DB"  -> requiere db_number, lee un Data Block   (client.db_read)
          area="M"   -> lee Marcas / Flags                       (client.mb_read)
          area="I"   -> lee imagen de proceso de Entradas        (client.eb_read)
          area="Q"   -> lee imagen de proceso de Salidas         (client.ab_read)
          area="PIW" -> NO SOPORTADO. El acceso "periférico directo" (bypass de
                        la imagen de proceso) que representa PIW dentro del
                        programa del PLC no está expuesto por el protocolo
                        S7comm a un cliente externo como Snap7 — es una
                        limitación del protocolo, no de esta implementación.
                        Los 34 tags PIW del dataset deben quedar permanentemente
                        `is_simulated=True` a menos que exista un equivalente
                        mapeado en el área de Entradas (I) que sí sea legible.

        Serializado con `_socket_lock` igual que el resto de los accesos.
        """
        with self._socket_lock:
            if not self._client.get_connected():
                raise Exception(f"PLC Offline al intentar leer área {area}")

            if area == "DB":
                if db_number is None:
                    raise ValueError("db_number es obligatorio para area='DB'")
                return self._client.db_read(db_number, start, size)
            if area == "M":
                return self._client.mb_read(start, size)
            if area == "I":
                return self._client.eb_read(start, size)
            if area == "Q":
                return self._client.ab_read(start, size)
            if area == "PIW":
                raise NotImplementedError(
                    "El área PIW (periférico directo) no está soportada por el "
                    "protocolo S7comm para clientes externos. No es un fallo de "
                    "dirección — es una limitación de acceso remoto."
                )
            raise ValueError(f"Área de memoria desconocida: '{area}'")

    def leer_bloque_db(self, db_number: int, size: int) -> bytes:
        """
        MÉTODO AGREGADO: Permite al Logger Service dinámico solicitar 
        un bloque de bytes exacto de cualquier DB sin saltar excepciones.

        Se mantiene como wrapper delgado sobre `leer_area()` por compatibilidad
        descendente — todo el código existente que llama `leer_bloque_db`
        sigue funcionando igual, ahora reutilizando la misma ruta serializada.
        """
        return self.leer_area("DB", 0, size, db_number=db_number)

    def _validar_termico(self, valor: float, tag: str) -> float | None:
        if valor < self.TEMP_MIN_LOGICA or valor > self.TEMP_MAX_LOGICA:
            return None
        return round(valor, 2)

    def _validar_motor(self, valor: float, tag: str) -> float | None:
        if valor < self.MOTOR_MIN_LOGICO or valor > self.MOTOR_MAX_LOGICO:
            return None
        return round(valor, 2)

    # -------------------------------------------------------------------------
    # Métodos legacy (Se mantienen intactos para compatibilidad descendente)
    # -------------------------------------------------------------------------
    def read_extrusion_zones(self, db_number: int, tag_prefix: str) -> list:
        buffer = self.leer_bloque_db(db_number, 48)
        zonas_data = []
        
        if db_number == 2:
            raw_sp_z1 = get_real(buffer, 20)  
            raw_pv_z1 = get_real(buffer, 24)  
            
            zonas_data.append({
                "zona": 1,
                "pv_tag": f"{tag_prefix}_PV_Z1",
                "pv_value": self._validar_termico(raw_pv_z1, f"{tag_prefix}_PV_Z1") or 45.2,
                "sp_tag": f"{tag_prefix}_SP_Z1",
                "sp_value": self._validar_termico(raw_sp_z1, f"{tag_prefix}_SP_Z1") or 250.0,
            })
        else:
            raw_pv_z1 = get_real(buffer, 24)
            raw_sp_z1 = get_real(buffer, 28)
            
            zonas_data.append({
                "zona": 1,
                "pv_tag": f"{tag_prefix}_PV_Z1",
                "pv_value": self._validar_termico(raw_pv_z1, f"{tag_prefix}_PV_Z1") or 0.0,
                "sp_tag": f"{tag_prefix}_SP_Z1",
                "sp_value": self._validar_termico(raw_sp_z1, f"{tag_prefix}_SP_Z1") or 0.0,
            })

        for zona in range(2, 7):
            offset_test = 24 + ((zona - 1) * 8)
            
            val_pv, val_sp = 0.0, 0.0
            if offset_test + 4 <= len(buffer):
                r_pv = get_real(buffer, offset_test)
                r_sp = get_real(buffer, offset_test + 4)
                val_pv = self._validar_termico(r_pv, f"{tag_prefix}_PV_Z{zona}") or 0.0
                val_sp = self._validar_termico(r_sp, f"{tag_prefix}_SP_Z{zona}") or 0.0

            zonas_data.append({
                "zona": zona,
                "pv_tag": f"{tag_prefix}_PV_Z{zona}",
                "pv_value": val_pv,
                "sp_tag": f"{tag_prefix}_SP_Z{zona}",
                "sp_value": val_sp,
            })
            
        return zonas_data

    def read_motor_speeds(self, db_number: int = 6) -> list:
        buffer = self.leer_bloque_db(db_number, 48)
        nombres_motores = [
            "Extrusora_Spunbond_1", "Extrusora_Spunbond_2", "Extrusora_Meltblown",
            "Bomba_Masa_S1", "Bomba_Masa_S2", "Bomba_Masa_M"
        ]
        
        motores_data = []
        offset_base = 20 
        
        for i, nombre in enumerate(nombres_motores):
            tag_pv_name = f"{nombre}_RPM_PV"
            tag_sp_name = f"{nombre}_RPM_SP"
            offset_pv = offset_base + (i * 4)
            
            if offset_pv + 4 <= len(buffer):
                raw_pv = get_real(buffer, offset_pv)
                final_pv = self._validar_motor(raw_pv, tag_pv_name) or 0.0
            else:
                final_pv = 0.0
                
            motores_data.append({
                "motor_id": i + 1,
                "nombre": nombre,
                "pv_tag": tag_pv_name,
                "pv_value": final_pv,
                "sp_tag": tag_sp_name,
                "sp_value": final_pv, 
            })
            
        return motores_data