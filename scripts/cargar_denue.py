"""Carga el DENUE de Puebla en stg.totales_municipio (todos los sectores) y stg.denue (filtrado).

Uso:
    python scripts/cargar_denue.py data/raw/denue --corte 2026-05

- Lee todos los CSV de la descarga (vienen en latin-1) como texto, para no perder los ceros
  a la izquierda de cve_mun.
- El personal estimado usa los puntos medios de dw.dim_estrato_personal (los lee de la BD
  para que el total y el ETL usen exactamente el mismo supuesto).
- Registra el corte en dw.dim_periodo y documenta la fuente en dw.dim_fuente.
- Reemplaza el contenido de ambas tablas de staging (se puede volver a ejecutar).
"""
import argparse
from datetime import date
from pathlib import Path

import pandas as pd
from sqlalchemy import text

from db import motor

# Prefijos SCIAN que se cargan en stg.denue. Deben coincidir con el bridge del paso 2 del ETL.
PREFIJOS = ("721", "722", "711", "712", "713", "5615",
            "465915")  # comercio turístico: tiendas de artesanías
COLUMNAS = ["id", "nom_estab", "codigo_act", "nombre_act", "per_ocu",
            "cve_ent", "cve_mun", "latitud", "longitud", "fecha_alta"]


def leer_denue(carpeta: Path) -> pd.DataFrame:
    archivos = sorted(p for p in carpeta.rglob("*.csv") if "diccionario" not in str(p).lower())
    if not archivos:
        raise SystemExit(f"No hay CSV del DENUE en {carpeta}")
    df = pd.concat((pd.read_csv(a, encoding="latin-1", dtype=str, usecols=COLUMNAS)
                    for a in archivos), ignore_index=True)
    for c in ("per_ocu", "codigo_act", "cve_ent", "cve_mun", "nom_estab", "nombre_act"):
        df[c] = df[c].str.strip()
    df["cve_mun"] = df["cve_mun"].str.zfill(3)
    df = df[df["cve_ent"] == "21"]
    if not df["id"].is_unique:
        raise SystemExit("Hay id duplicados en el DENUE")
    print(f"DENUE leído: {len(df):,} establecimientos de {len(archivos)} archivo(s)")
    return df


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("carpeta")
    ap.add_argument("--corte", required=True, help="Corte del DENUE como AAAA-MM, p. ej. 2026-05")
    args = ap.parse_args()
    anio = int(args.corte[:4])

    df = leer_denue(Path(args.carpeta))
    eng = motor()

    with eng.connect() as conn:
        estratos = pd.read_sql_query(
            "SELECT rango_texto, punto_medio FROM dw.dim_estrato_personal", conn)
        municipios = set(pd.read_sql_query("SELECT cve_geo FROM dw.dim_municipio", conn)["cve_geo"])
    punto_medio = dict(zip(estratos["rango_texto"], estratos["punto_medio"].astype(float)))

    sin_estrato = df.loc[~df["per_ocu"].isin(punto_medio), "per_ocu"].value_counts(dropna=False)
    if len(sin_estrato):
        raise SystemExit(f"Rangos de per_ocu sin estrato en dim_estrato_personal:\n{sin_estrato}")
    df["personal_est"] = df["per_ocu"].map(punto_medio)
    df["cve_geo"] = df["cve_ent"] + df["cve_mun"]

    # Totales de TODOS los sectores (denominador del cociente de localización)
    totales = (df.groupby("cve_geo")
                 .agg(unidades_total=("id", "size"), personal_est_total=("personal_est", "sum"))
                 .reset_index())
    totales["corte_denue"] = args.corte
    if municipios and set(totales["cve_geo"]) != municipios:
        faltan = sorted(municipios - set(totales["cve_geo"]))
        sobran = sorted(set(totales["cve_geo"]) - municipios)
        raise SystemExit(f"Los totales no cuadran con dim_municipio. Faltan: {faltan} Sobran: {sobran}")
    if len(totales) != 217:
        raise SystemExit(f"Se esperaban 217 municipios en los totales y hay {len(totales)}")

    # Filtrado turístico
    tur = df[df["codigo_act"].str.startswith(PREFIJOS)].copy()
    tur = tur.rename(columns={"id": "id_denue"})
    tur["latitud"] = pd.to_numeric(tur["latitud"], errors="coerce")
    tur["longitud"] = pd.to_numeric(tur["longitud"], errors="coerce")
    tur["corte_denue"] = args.corte
    tur = tur[["id_denue", "nom_estab", "codigo_act", "nombre_act", "per_ocu", "cve_ent",
               "cve_mun", "latitud", "longitud", "fecha_alta", "corte_denue"]]

    with eng.begin() as conn:
        conn.execute(text("""
            INSERT INTO dw.dim_periodo (etiqueta, anio, tipo) VALUES (:et, :anio, 'denue')
            ON CONFLICT (etiqueta) DO NOTHING"""), {"et": f"DENUE {args.corte}", "anio": anio})
        conn.execute(text("DELETE FROM stg.totales_municipio"))
        totales.to_sql("totales_municipio", conn, schema="stg", if_exists="append", index=False)
        conn.execute(text("DELETE FROM stg.denue"))
        tur.to_sql("denue", conn, schema="stg", if_exists="append", index=False,
                   method="multi", chunksize=2000)
        conn.execute(text("""
            UPDATE dw.dim_fuente
               SET version_corte = :corte, fecha_descarga = :hoy,
                   url = 'https://www.inegi.org.mx/app/descarga/?ti=6',
                   licencia_terminos = 'Términos de Libre Uso de la Información del INEGI (citar la fuente)',
                   cobertura = 'Puebla (entidad 21), todos los sectores para totales; SCIAN turísticos para el detalle',
                   calidad_notas = :notas
             WHERE nombre = 'DENUE'"""),
            {"corte": f"DENUE {args.corte}", "hoy": date.today(),
             "notas": "Personal por rangos: se estima con el punto medio del estrato (supuesto; "
                      "251 y más = 300). Actualizado sobre todo en establecimientos grandes. "
                      f"Prefijos SCIAN cargados: {', '.join(PREFIJOS)}."})

    print(f"stg.totales_municipio: {len(totales)} municipios, "
          f"{int(totales['unidades_total'].sum()):,} unidades")
    print(f"stg.denue: {len(tur):,} establecimientos turísticos "
          f"({tur['latitud'].isna().sum()} sin coordenadas)")
    print(tur["codigo_act"].str[:3].value_counts().to_string())


if __name__ == "__main__":
    main()
