# BackEnd/app/seed/tags.py
"""
Seeder de tags de la Máquina 3.

🆕 CAMBIO DE DISEÑO: este seeder ya NO contiene una lista Python hardcodeada
de ~30 tags. El listado real de WinCC tiene 1362 tags con dirección física
(de los cuales 1133 quedaron con una dirección física única y parseable tras
deduplicar por dirección — ver `data/tags_wincc_export.json`), así que se
migró a un archivo de datos versionable en vez de código Python.

Origen de cada tag (campo "origen" en el JSON):
  - "curado (seed actual)"  -> son los ~16 tags que ya tenías validados y en
    uso real por SCADALoggerService. Se insertan exactamente igual que antes,
    is_simulated=False, para NO tocar nada de lo que ya está en producción.
  - "import_wincc"          -> todo lo demás, importado directo del export de
    WinCC. Se inserta con is_simulated=True (tal como pediste: "si no lo
    usamos en el momento lo cambias a simulados"). Cuando alguien valide una
    dirección contra el PLC real y quiera empezar a muestrearla, basta con
    poner is_simulated=False para ese tag_name puntual — no hace falta tocar
    este archivo.

⚠️ Quedaron 40 tags (19 direcciones) marcados con "conflicto": true. Son
direcciones donde WinCC tiene DOS nombres reales distintos apuntando al mismo
byte del PLC (no basura de exportación). Ambos se insertan igual, pero
Xavier debe confirmar cuál nombre es el vigente — ver
`documentacion/conflictos_direcciones_wincc.md`.
"""
import asyncio
import json
import logging
from pathlib import Path

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import AsyncSessionLocal
from ..models.scada import TagModel

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("SCADA_Seeder")

DATA_FILE = Path(__file__).parent / "data" / "tags_wincc_export.json"

# Límites de ingeniería conocidos para los ~16 tags curados y validados.
# Estos SÍ generan acción/alarma real, por eso mantienen sus límites originales.
CURATED_LIMITS = {
    "S1_PV_Z1": {"limit_high": 260.0, "limit_low": 180.0, "limit_high_high": 275.0},
    "S1_PV_Z2": {"limit_high": 270.0, "limit_low": 190.0, "limit_high_high": 285.0},
    "S1_PV_Z3": {"limit_high": 280.0, "limit_low": 200.0, "limit_high_high": 295.0},
    "S1_PV_Z4": {"limit_high": 280.0, "limit_low": 200.0, "limit_high_high": 295.0},
    "S1_PV_Z5": {"limit_high": 280.0, "limit_low": 200.0, "limit_high_high": 295.0},
    "S1_PV_Z6": {"limit_high": 280.0, "limit_low": 200.0, "limit_high_high": 295.0},
    "S1_EXT_PRESS_IN": {"limit_high": 350.0, "limit_low": 0.0, "limit_high_high": 380.0},
    "TEMP_CHILLER_RETORNO": {"limit_high": 13.0, "limit_low": 5.0, "limit_high_high": 17.0},
    "M_DIE_PRESS_SP": {"limit_high": 3000.0, "limit_low": 0.0, "limit_high_high": None},
    "M_STOCK_RPM_SP": {"limit_high": 100.0, "limit_low": 0.0, "limit_high_high": None},
    "M_DOSIF_GR_RATIO": {"limit_high": 500.0, "limit_low": 0.0, "limit_high_high": None},
    "M_MOTOR_COLOR1_RPM": {"limit_high": 60.0, "limit_low": 0.0, "limit_high_high": None},
    "M_PCT_COLOR1": {"limit_high": 10.0, "limit_low": 0.0, "limit_high_high": None},
    "S1_SP_Z1": {"limit_high": 260.0, "limit_low": 180.0, "limit_high_high": None},
}


def _load_master_tags() -> list[dict]:
    with open(DATA_FILE, encoding="utf-8") as f:
        return json.load(f)


async def execute_seed():
    tags_data = _load_master_tags()

    # 🐛 FIX: el conteo anterior filtraba por t["origen"] == "curado (seed actual)",
    # que no incluye los 16 tags recuperados con origen "curado (seed actual,
    # sin match en export WinCC)" (ver docstring de este módulo). Esto hacía
    # que el log dijera "16 curados" cuando en realidad se insertaban 32 con
    # is_simulated=False — el INSERT en sí siempre fue correcto, esto solo
    # afectaba el resumen impreso al final. Ahora se cuenta por el campo real.
    curados = [t for t in tags_data if not t["is_simulated"]]
    importados = [t for t in tags_data if t["is_simulated"]]
    conflictos = [t for t in tags_data if t["conflicto"]]

    async with AsyncSessionLocal() as session:
        try:
            logger.info("Ejecutando la limpieza total de la tabla de tags...")
            await session.execute(delete(TagModel))
            await session.flush()
            logger.info("Tabla purgada correctamente.")

            logger.info(f"Insertando {len(tags_data)} tags ({len(curados)} curados + "
                        f"{len(importados)} importados de WinCC)...")

            for tag_data in tags_data:
                limites = CURATED_LIMITS.get(tag_data["tag_name"], {})

                new_tag = TagModel(
                    tag_name=tag_data["tag_name"],
                    description=tag_data["description"],
                    data_type=tag_data["data_type"],
                    current_value=0.0,
                    is_simulated=tag_data["is_simulated"],
                    limit_high=limites.get("limit_high"),
                    limit_low=limites.get("limit_low"),
                    limit_high_high=limites.get("limit_high_high"),
                )
                new_tag.direccion_fisica = tag_data["direccion_fisica"]
                session.add(new_tag)

            await session.commit()

            logger.info("=" * 65)
            logger.info("¡SEED MASIVO DE MÁQUINA 3 COMPLETADO EXITOSAMENTE!")
            logger.info(f" -> Total tags registrados: {len(tags_data)}")
            logger.info(f" -> Curados / activos en muestreo real (is_simulated=False): {len(curados)}")
            logger.info(f" -> Importados de WinCC en espera (is_simulated=True): {len(importados)}")
            logger.info(f" -> ⚠️ Tags con conflicto de dirección pendiente de revisar: {len(conflictos)}")
            logger.info("    Ver documentacion/conflictos_direcciones_wincc.md")
            logger.info("=" * 65)

        except Exception as e:
            await session.rollback()
            logger.error(f"❌ Error crítico durante la carga de tags en la base de datos: {e}")
            raise


if __name__ == "__main__":
    asyncio.run(execute_seed())