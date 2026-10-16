"""Demanda hotelera mensual de DATATUR (Monitoreo Hotelero, SECTUR) → dw.fact_demanda_hotelera (F6a del plan).

Cada archivo mensual público (AAAA-MES_MM_Publico.zip, hoja ExcelMes) compara el mismo mes de tres años:
cuartos disponibles y ocupados en promedio diario y porcentaje de ocupación por centro turístico. De Puebla solo
aparece "PUEBLA, PUE." (la ciudad, municipio 21114). Si un mes aparece en varios archivos se toma el más reciente.
Toda la publicación está marcada como "resultados preliminares" (es_preliminar = true).

Uso:
    python scripts/cargar_datatur.py data/raw/datatur        # carpeta con los .xlsx ya descomprimidos
Descarga: https://www.datatur.sectur.gob.mx/SitePages/hoteleria.aspx (sección Monitoreo Hotelero, archivos mensuales)
"""
import re
import sys
import urllib.parse
from datetime import date
from pathlib import Path

import pandas as pd

RAIZ = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(RAIZ / "dashboard")]

import supabase_cliente as sb  # noqa: E402

MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre",
         "noviembre", "diciembre"]
DESTINOS = {"PUEBLA, PUE.": dict(tipo="ciudad", municipios={"21114": 1.0})}
FUENTE = dict(nombre="DATATUR · Monitoreo Hotelero (mensual)", institucion="Secretaría de Turismo federal (SECTUR)",
              tipo="Oficial", url="https://www.datatur.sectur.gob.mx/SitePages/hoteleria.aspx",
              licencia_terminos="Información pública de SECTUR (citar DataTur como fuente)",
              cobertura="Un solo destino de Puebla en la publicación: PUEBLA, PUE. (ciudad de Puebla)",
              calidad_notas="Resultados preliminares. Cuartos disponibles y ocupados en promedio diario del mes. "
                            "El archivo público no trae llegadas, estadía ni densidad. Un solo destino de Puebla: no "
                            "alcanza para la validación V9 entre destinos (requiere el monitoreo estatal por destino).",
              uso_en_modelo="Demanda observada y estacionalidad de la capital; referencia para el proxy de intensidad")


def leer(archivo: Path) -> list[dict]:
    d = pd.read_excel(archivo, sheet_name="ExcelMes", header=None)
    mes = next(i + 1 for i, m in enumerate(MESES) if m in str(d.iat[1, 2]).lower())
    anios = [int(re.sub(r"\D", "", str(v))) for v in d.iloc[6, 2:5]]
    filas = []
    for nombre in DESTINOS:
        r = d[d[1].astype(str).str.strip() == nombre]
        if r.empty:
            continue
        r = r.iloc[0]
        for k, anio in enumerate(anios):
            num = lambda c: None if pd.isna(r[c]) or str(r[c]).strip() in ("n.d.", "n.c.") else float(r[c])  # noqa: E731
            filas.append(dict(destino=nombre, mes=date(anio, mes, 1).isoformat(), cuartos_disponibles=num(2 + k),
                              cuartos_ocupados=num(9 + k), pct_ocupacion=num(16 + k), archivo=archivo.name))
    return filas


def main():
    carpeta = Path(sys.argv[1])
    filas = [f for a in sorted(carpeta.glob("*-MES_*_Publico.xlsx")) for f in leer(a)]
    df = pd.DataFrame(filas).sort_values("archivo").drop_duplicates(["destino", "mes"], keep="last")
    print(f"DATATUR: {len(df)} meses × destino ({df.mes.min()} a {df.mes.max()}) de {df.archivo.nunique()} archivos")

    hoy = date.today().isoformat()
    previa = sb._peticion("dim_fuente?select=fuente_sk&nombre=eq." + urllib.parse.quote(FUENTE["nombre"]), True, "dw")
    fila_f = {**FUENTE, "version_corte": f"{df.mes.min()} a {df.mes.max()}", "fecha_descarga": hoy}
    if previa:
        fuente_sk = previa[0]["fuente_sk"]
        sb._peticion(f"dim_fuente?fuente_sk=eq.{fuente_sk}", True, "dw", "PATCH", fila_f, {"Prefer": "return=minimal"})
    else:
        fuente_sk = sb._peticion("dim_fuente", True, "dw", "POST", fila_f, {"Prefer": "return=representation"})[0]["fuente_sk"]

    mun = {r["cve_geo"].strip(): r["municipio_sk"] for r in sb._peticion("dim_municipio?select=municipio_sk,cve_geo", True, "dw")}
    for nombre, cfg in DESTINOS.items():
        sb.insertar("dim_destino_datatur", [dict(nombre=nombre, tipo=cfg["tipo"])], "dw")
    dsk = {r["nombre"]: r["destino_sk"] for r in sb._peticion("dim_destino_datatur?select=destino_sk,nombre", True, "dw")}
    sb.insertar("bridge_destino_municipio", [dict(destino_sk=dsk[n], municipio_sk=mun[c], peso=p)
                                             for n, cfg in DESTINOS.items() for c, p in cfg["municipios"].items()], "dw")
    sb.insertar("fact_demanda_hotelera", [dict(destino_sk=dsk[r.destino], mes=r.mes, cuartos_disponibles=r.cuartos_disponibles,
                                               cuartos_ocupados=r.cuartos_ocupados, pct_ocupacion=r.pct_ocupacion,
                                               es_preliminar=True, fuente_sk=fuente_sk)
                                          for r in df.itertuples()], "dw")
    print(f"✓ fact_demanda_hotelera: {len(df)} filas · ocupación media {df.pct_ocupacion.mean():.1f} %")
    por_mes = df.assign(m=pd.to_datetime(df.mes).dt.month).groupby("m").pct_ocupacion.mean().round(1)
    print("  ocupación media por mes del año:", por_mes.to_dict())


if __name__ == "__main__":
    main()
