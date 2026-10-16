"""Población municipal por año de CONAPO → dw.fact_poblacion_anual (F6e del plan de afinación).

Fuente: "Reconstrucción y proyecciones de la población de los municipios de México 1990-2040" (CONAPO), recurso
"Indicadores demográficos para los municipios de México (1990-2040)" en datos.gob.mx (pobproy_ggrupos.csv).
Se suma hombres + mujeres; 1990-2020 es reconstrucción y 2021-2040 proyección. Se cargan 2010-2040.

Uso: python scripts/cargar_poblacion_conapo.py data/raw/conapo/pobproy_ggrupos.csv
"""
import sys
import urllib.parse
from datetime import date
from pathlib import Path

import pandas as pd

RAIZ = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(RAIZ / "dashboard")]

import supabase_cliente as sb  # noqa: E402

URL = ("https://www.datos.gob.mx/dataset/f2b9b220-3ef7-4e3a-bde6-87e1dac78c6a/resource/"
       "99b28bb6-8e31-48e1-b162-85a7e4deafc3/download/pobproy_ggrupos.csv")
FUENTE = dict(nombre="CONAPO · Reconstrucción y proyecciones de la población municipal 1990-2040",
              institucion="Consejo Nacional de Población (CONAPO)", tipo="Oficial", url=URL,
              licencia_terminos="Libre Uso MX (datos.gob.mx)", cobertura="217 municipios de Puebla, 2010-2040",
              calidad_notas="Población a mitad de año. 1990-2020 reconstruida a partir de censos y conteos; 2021-2040 "
                            "proyectada y alineada con las proyecciones estatales 2020-2070.",
              uso_en_modelo="fact_poblacion_anual · tasas de fact_seguridad por año")


def main():
    d = pd.read_csv(sys.argv[1], encoding="latin-1", usecols=["CLAVE", "CLAVE_ENT", "ANO", "POB_TOTAL"])
    d = d[(d.CLAVE_ENT == 21) & (d.ANO >= 2010)]
    d = d.groupby(["CLAVE", "ANO"]).POB_TOTAL.sum().reset_index()
    d["cve_geo"] = d.CLAVE.astype(str).str.zfill(5)
    mun = {r["cve_geo"].strip(): r["municipio_sk"] for r in sb._peticion("dim_municipio?select=municipio_sk,cve_geo", True, "dw")}
    faltan = set(mun) - set(d.cve_geo)
    if faltan:
        raise SystemExit(f"Municipios sin población CONAPO: {sorted(faltan)}")
    d = d[d.cve_geo.isin(mun)]

    previa = sb._peticion("dim_fuente?select=fuente_sk&nombre=eq." + urllib.parse.quote(FUENTE["nombre"]), True, "dw")
    fila_f = {**FUENTE, "version_corte": "Edición 2024 (base Censo 2020)", "fecha_descarga": date.today().isoformat()}
    if previa:
        fuente_sk = previa[0]["fuente_sk"]
        sb._peticion(f"dim_fuente?fuente_sk=eq.{fuente_sk}", True, "dw", "PATCH", fila_f, {"Prefer": "return=minimal"})
    else:
        fuente_sk = sb._peticion("dim_fuente", True, "dw", "POST", fila_f, {"Prefer": "return=representation"})[0]["fuente_sk"]
    sb.insertar("fact_poblacion_anual", [dict(municipio_sk=mun[r.cve_geo], anio=int(r.ANO), poblacion=int(r.POB_TOTAL),
                                              es_proyeccion=bool(r.ANO > 2020), fuente_sk=fuente_sk)
                                         for r in d.itertuples()], "dw")
    tot = d.groupby("ANO").POB_TOTAL.sum()
    print(f"✓ fact_poblacion_anual: {len(d):,} filas · Puebla 2020 {tot[2020]:,} · 2026 {tot[2026]:,} · 2040 {tot[2040]:,}")


if __name__ == "__main__":
    main()
