#!/usr/bin/env python3
"""
audit_all_dbs.py
------------------------------------------------------------------------------
Recorre un rango de Data Blocks contra el endpoint /diagnostico-memoria,
DB por DB (para no repetir el problema de auditar todo de una sola ráfaga),
y consolida un reporte único de direcciones válidas vs inválidas.

Uso:
    python3 audit_all_dbs.py --host http://192.168.2.27:8080 --db-min 1 --db-max 60

Opciones:
    --host             Base URL del backend (default: http://localhost:8080)
    --db-min           Primer DB a auditar (default: 1)
    --db-max           Último DB a auditar (default: 60)
    --delay            Segundos de espera entre cada llamada (default: 0.3)
    --incluir-simulados  true/false (default: true — es el caso de uso principal)
    --output-prefix    Prefijo para los archivos de salida (default: auditoria_dbs)

Salida:
    <prefix>_validas.csv     -> tag_name, direccion, tipo_dato, valor_bd, valor_plc
    <prefix>_invalidas.csv   -> tag_name, direccion, error
    <prefix>_resumen.json    -> resumen consolidado + lista de DBs vacíos/con error de conexión

No requiere librerías fuera de la librería estándar + `requests`
(pip install requests --break-system-packages si hace falta).
------------------------------------------------------------------------------
"""
import argparse
import csv
import json
import sys
import time

import requests


def parse_args():
    p = argparse.ArgumentParser(description="Audita un rango de DBs contra /diagnostico-memoria")
    p.add_argument("--host", default="http://localhost:8080")
    p.add_argument("--db-min", type=int, default=1)
    p.add_argument("--db-max", type=int, default=60)
    p.add_argument("--delay", type=float, default=0.3, help="segundos entre cada request")
    p.add_argument("--incluir-simulados", default="true", choices=["true", "false"])
    p.add_argument("--output-prefix", default="auditoria_dbs")
    p.add_argument("--timeout", type=float, default=60.0, help="timeout por request, en segundos")
    return p.parse_args()


def auditar_db(host: str, db: int, incluir_simulados: str, timeout: float):
    """Llama /diagnostico-memoria para un único DB. Devuelve (estado, payload)."""
    url = f"{host.rstrip('/')}/api/v1/control/diagnostico-memoria"
    params = {
        "incluir_simulados": incluir_simulados,
        "db_min": db,
        "db_max": db,
    }
    try:
        resp = requests.get(url, params=params, timeout=timeout)
    except requests.RequestException as e:
        return "error_conexion", {"db": db, "error": str(e)}

    if resp.status_code == 200:
        return "ok", resp.json()

    if resp.status_code == 404:
        return "sin_tags", {"db": db}

    if resp.status_code == 400:
        # El 400 tiene dos causas MUY distintas y hay que separarlas:
        #  a) direcciones físicas inválidas detectadas de verdad (esto es un
        #     resultado ÚTIL de la auditoría, no un fallo del script)
        #  b) la guarda de "consulta sin acotar" (no debería pasar nunca acá
        #     porque siempre pedimos un solo DB, pero se contempla por si acaso)
        try:
            body = resp.json()
        except ValueError:
            return "error_http", {"db": db, "status": 400, "detail": resp.text}

        detail = body.get("detail")
        if isinstance(detail, dict) and "tags_inexistentes_en_plc" in detail:
            return "direcciones_invalidas", {"db": db, "invalidas": detail["tags_inexistentes_en_plc"]}
        return "rechazado", {"db": db, "detail": detail}

    return "error_http", {"db": db, "status": resp.status_code, "detail": resp.text}


def main():
    args = parse_args()

    validas = []
    invalidas = []
    dbs_sin_tags = []
    dbs_con_error = []

    total_dbs = args.db_max - args.db_min + 1
    print(f"Auditando DB{args.db_min} a DB{args.db_max} ({total_dbs} bloques) contra {args.host} ...")
    print(f"incluir_simulados={args.incluir_simulados} | delay={args.delay}s entre llamadas\n")

    for i, db in enumerate(range(args.db_min, args.db_max + 1), start=1):
        estado, payload = auditar_db(args.host, db, args.incluir_simulados, args.timeout)

        if estado == "ok":
            tags_ok = payload.get("tags_validados", [])
            for t in tags_ok:
                validas.append({
                    "tag_name": t["tag_name"],
                    "direccion": t["direccion_fisica"],
                    "tipo_dato": t["tipo_dato"],
                    "valor_en_bd": t["valor_en_bd_actual"],
                    "valor_real_plc": t["valor_real_plc"],
                    "estado_lectura": t["estado_lectura"],
                })
            print(f"  [DB{db:>4}] OK — {len(tags_ok)} tag(s) válidos")

        elif estado == "direcciones_invalidas":
            invs = payload["invalidas"]
            invalidas.extend(invs)
            print(f"  [DB{db:>4}] {len(invs)} dirección(es) inválida(s) detectada(s)")

        elif estado == "sin_tags":
            dbs_sin_tags.append(db)
            print(f"  [DB{db:>4}] sin tags configurados (404, se omite)")

        elif estado == "rechazado":
            dbs_con_error.append({"db": db, "motivo": "400_no_reconocido", "detalle": payload.get("detail")})
            print(f"  [DB{db:>4}] ⚠️ 400 con formato inesperado — revisar manualmente")

        elif estado == "error_conexion":
            dbs_con_error.append({"db": db, "motivo": "error_conexion", "detalle": payload.get("error")})
            print(f"  [DB{db:>4}] ❌ error de conexión: {payload.get('error')}")

        else:  # error_http
            dbs_con_error.append({
                "db": db, "motivo": f"http_{payload.get('status')}", "detalle": payload.get("detail")
            })
            print(f"  [DB{db:>4}] ❌ HTTP {payload.get('status')}")

        if i < total_dbs:
            time.sleep(args.delay)

    # --- Salidas ---------------------------------------------------------
    validas_file = f"{args.output_prefix}_validas.csv"
    invalidas_file = f"{args.output_prefix}_invalidas.csv"
    resumen_file = f"{args.output_prefix}_resumen.json"

    with open(validas_file, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["tag_name", "direccion", "tipo_dato", "valor_en_bd", "valor_real_plc", "estado_lectura"])
        w.writeheader()
        w.writerows(validas)

    with open(invalidas_file, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["tag_name", "direccion", "error"])
        w.writeheader()
        w.writerows(invalidas)

    resumen = {
        "rango_auditado": {"db_min": args.db_min, "db_max": args.db_max},
        "total_validas": len(validas),
        "total_invalidas": len(invalidas),
        "dbs_sin_tags_configurados": dbs_sin_tags,
        "dbs_con_error_de_auditoria": dbs_con_error,
    }
    with open(resumen_file, "w", encoding="utf-8") as f:
        json.dump(resumen, f, ensure_ascii=False, indent=2)

    print("\n" + "=" * 70)
    print(f"Listo. {len(validas)} direcciones válidas, {len(invalidas)} inválidas.")
    print(f"  -> {validas_file}")
    print(f"  -> {invalidas_file}")
    print(f"  -> {resumen_file}")
    if dbs_con_error:
        print(f"\n⚠️ {len(dbs_con_error)} DB(s) tuvieron un error real de auditoría (no solo 'sin tags').")
        print("   Revisa el resumen.json antes de confiar en la lista de inválidas.")
    print("=" * 70)


if __name__ == "__main__":
    sys.exit(main())