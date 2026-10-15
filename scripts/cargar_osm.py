"""Sube data/processed/osm_nuevos.csv a stg.establecimiento_externo y lo pasa a dw.

Uso (después de scripts/buscar_osm_nuevos.py y de cargar el DENUE con el ETL pasos 1 a 3):
    python scripts/cargar_osm.py

Reemplaza los registros de OpenStreetMap en staging y ejecuta DDL/05_establecimientos_osm.sql
(crea la tabla si no existe, agrega a dw.dim_establecimiento y actualiza dw.dim_fuente).
"""
from pathlib import Path

import pandas as pd
from sqlalchemy import text

from db import motor

RAIZ = Path(__file__).resolve().parent.parent
CSV = RAIZ / "data" / "processed" / "osm_nuevos.csv"
SQL = RAIZ / "DDL" / "05_establecimientos_osm.sql"


def main():
    df = pd.read_csv(CSV, dtype={"cve_geo": str, "codigo_act": str, "codigo_postal": str,
                                 "telefono": str, "wikidata": str})
    for c in ("estrellas", "habitaciones", "capacidad", "personal_ocupado"):
        df[c] = df[c].astype("Int64")
    for c in ("ultima_edicion_osm", "fecha_consulta"):
        df[c] = pd.to_datetime(df[c]).dt.date

    eng = motor()
    sql = SQL.read_text(encoding="utf-8")
    estructura = sql[:sql.index("-- 2. Carga a dw")]
    with eng.begin() as conn:
        # Cursor de psycopg2 sin parámetros: el SQL lleva '%' en los LIKE.
        cur = conn.connection.cursor()
        cur.execute(estructura)
        sin_scian = set(df["codigo_act"]) - set(pd.read_sql_query(
            "SELECT codigo_scian FROM dw.dim_scian", conn)["codigo_scian"].str.strip())
        if sin_scian:
            raise SystemExit(f"SCIAN que no están en dw.dim_scian (correr ETL pasos 1-2): {sin_scian}")
        conn.execute(text("DELETE FROM stg.establecimiento_externo WHERE fuente = 'OpenStreetMap'"))
        df.to_sql("establecimiento_externo", conn, schema="stg", if_exists="append", index=False,
                  method="multi", chunksize=500)
        cur.execute(sql)
        res = conn.execute(text("""
            SELECT COUNT(*) FROM dw.dim_establecimiento WHERE id_denue LIKE 'OSM:%'""")).scalar()
    print(f"stg.establecimiento_externo: {len(df):,} filas · dw.dim_establecimiento (OSM): {res:,}")


if __name__ == "__main__":
    main()
