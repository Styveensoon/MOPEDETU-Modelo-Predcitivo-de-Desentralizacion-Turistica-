"""Ejecuta un script .sql completo, o solo algunos pasos del ETL, en una transacción.

Uso:
    python scripts/ejecutar_sql.py DDL/03_ddl_prediccion_mopedetu.sql
    python scripts/ejecutar_sql.py DDL/02_etl_mopedetu.sql --pasos 0
    python scripts/ejecutar_sql.py DDL/02_etl_mopedetu.sql --pasos 1 2 3

Los pasos se reconocen por los encabezados '-- Paso N.' del archivo. Todo lo que está
antes del primer paso (SET search_path...) se ejecuta siempre.
"""
import argparse
import re
from pathlib import Path

from db import motor

PATRON_PASO = re.compile(r"^-- Paso (\d+)\.", re.MULTILINE)


def partir_pasos(sql: str) -> tuple[str, dict[int, str]]:
    marcas = list(PATRON_PASO.finditer(sql))
    if not marcas:
        return sql, {}
    # El bloque de un paso empieza en la línea de guiones anterior a su encabezado.
    inicios = [sql.rfind("\n-- ----", 0, m.start()) + 1 for m in marcas]
    cabecera = sql[:inicios[0]]
    pasos = {}
    for i, m in enumerate(marcas):
        fin = inicios[i + 1] if i + 1 < len(marcas) else len(sql)
        pasos[int(m.group(1))] = sql[inicios[i]:fin]
    return cabecera, pasos


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("archivo")
    ap.add_argument("--pasos", nargs="*", type=int)
    args = ap.parse_args()

    sql = Path(args.archivo).read_text(encoding="utf-8")
    if args.pasos:
        cabecera, pasos = partir_pasos(sql)
        faltan = [p for p in args.pasos if p not in pasos]
        if faltan:
            raise SystemExit(f"Pasos no encontrados en {args.archivo}: {faltan}")
        sql = cabecera + "\n".join(pasos[p] for p in args.pasos)

    conn = motor().raw_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(sql)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
    print(f"OK: {args.archivo}" + (f" pasos {args.pasos}" if args.pasos else ""))


if __name__ == "__main__":
    main()
