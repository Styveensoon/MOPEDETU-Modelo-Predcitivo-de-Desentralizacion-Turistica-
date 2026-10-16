"""Incidencia delictiva municipal (SESNSP) → dw.fact_seguridad y riesgo de las rutas (F6c del plan de afinación).

Fuente: "Incidencia delictiva del fuero común municipal 2015-2025" (metodología 2015-2025) del Secretariado Ejecutivo
del Sistema Nacional de Seguridad Pública, en https://www.gob.mx/sesnsp/acciones-y-programas/datos-abiertos-de-incidencia-delictiva
(enlace de SharePoint; se descarga con .../_layouts/15/download.aspx?share=<id>).

Agrupación (por subtipo):
  homicidio                  homicidio doloso y feminicidio
  robo_transeunte_carretera  robo a transeúnte (vía pública y espacio abierto), en transporte público e individual,
                             y a transportista (carreteras)
  secuestro_extorsion        secuestro y extorsión
  otros                      el resto
Tasa por 100 mil habitantes con la población CONAPO del año (dw.fact_poblacion_anual; si falta, Censo 2020).

Riesgo de ruta (fact_ruta_evaluacion.riesgo_seguridad): con el último año, percentil estatal de la tasa de delitos
que afectan al visitante (los tres primeros grupos) en cada parada; la ruta toma el de su parada más alta:
bajo (< P50), medio (P50-P80), alto (≥ P80). Es un semáforo para el operador, no una etiqueta pública del municipio;
SESNSP mide denuncias, no victimización.

Uso: python scripts/cargar_seguridad.py data/raw/sesnsp/idm_puebla_2015_2025.csv
"""
import sys
import urllib.parse
from datetime import date
from pathlib import Path

import pandas as pd

RAIZ = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(RAIZ / "dashboard")]

import supabase_cliente as sb  # noqa: E402

MESES = ["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio", "Agosto", "Septiembre", "Octubre",
         "Noviembre", "Diciembre"]
GRUPOS = {
    "homicidio": {"Homicidio doloso", "Feminicidio"},
    "robo_transeunte_carretera": {"Robo a transeúnte en vía pública", "Robo a transeúnte en espacio abierto al público",
                                  "Robo en transporte público colectivo", "Robo en transporte individual",
                                  "Robo en transporte público individual", "Robo a transportista"},
    "secuestro_extorsion": {"Secuestro", "Extorsión"},
}
VISITANTE = list(GRUPOS)
FUENTE = dict(nombre="SESNSP · Incidencia delictiva municipal (fuero común)",
              institucion="Secretariado Ejecutivo del Sistema Nacional de Seguridad Pública", tipo="Oficial",
              url="https://www.gob.mx/sesnsp/acciones-y-programas/datos-abiertos-de-incidencia-delictiva",
              licencia_terminos="Datos abiertos del Gobierno de México (Libre Uso MX)",
              cobertura="217 municipios de Puebla, 2015-2025, por año y grupo de delito",
              calidad_notas="Carpetas de investigación (denuncias), no victimización: la cifra negra varía por "
                            "municipio. Tasas con la población CONAPO del año. Uso solo como riesgo para el visitante a nivel de "
                            "ruta, nunca como etiqueta pública de un municipio.",
              uso_en_modelo="fact_seguridad · fact_ruta_evaluacion.riesgo_seguridad")


def grupo(subtipo: str) -> str:
    return next((g for g, s in GRUPOS.items() if subtipo in s), "otros")


def main():
    d = pd.read_csv(sys.argv[1], encoding="utf-8")
    d["incidentes"] = d[MESES].sum(axis=1)
    d["grupo_delito"] = d["Subtipo de delito"].map(grupo)
    d["cve_geo"] = d["Cve. Municipio"].astype(str).str.zfill(5)
    g = d.groupby(["cve_geo", "Año", "grupo_delito"]).incidentes.sum().reset_index()

    mun = sb.leer("dim_municipio", "dw", "municipio_sk,cve_geo,nombre", secreta=True)
    mun["cve_geo"] = mun.cve_geo.str.strip()
    pob = sb.leer("fact_contexto_social", "dw", "municipio_sk,poblacion_total", secreta=True)
    mun = mun.merge(pob)
    g = g.merge(mun, on="cve_geo", how="inner")
    # Rejilla completa: un municipio sin carpetas en un grupo tiene 0 (el archivo trae todas las combinaciones)
    rejilla = pd.MultiIndex.from_product([mun.municipio_sk, sorted(g["Año"].unique()), list(GRUPOS) + ["otros"]],
                                         names=["municipio_sk", "Año", "grupo_delito"]).to_frame(index=False)
    g = rejilla.merge(g[["municipio_sk", "Año", "grupo_delito", "incidentes"]], how="left").fillna({"incidentes": 0})
    g = g.merge(mun[["municipio_sk", "poblacion_total"]])
    # Población del año (CONAPO, dw.fact_poblacion_anual) si está cargada; si no, la del Censo 2020
    anual = sb.leer("fact_poblacion_anual", "dw", "municipio_sk,anio,poblacion", secreta=True)
    if len(anual):
        g = g.merge(anual.rename(columns={"anio": "Año"}), how="left")
        g["poblacion_total"] = g.poblacion.fillna(g.poblacion_total)
    g["tasa_100k"] = (1e5 * g.incidentes / g.poblacion_total).round(2)
    print(f"SESNSP: {len(g):,} filas · {g.municipio_sk.nunique()} municipios · años {g['Año'].min()}-{g['Año'].max()}")

    previa = sb._peticion("dim_fuente?select=fuente_sk&nombre=eq." + urllib.parse.quote(FUENTE["nombre"]), True, "dw")
    fila_f = {**FUENTE, "version_corte": "Metodología 2015-2025, corte de agosto de 2026",
              "fecha_descarga": date.today().isoformat()}
    if previa:
        fuente_sk = previa[0]["fuente_sk"]
        sb._peticion(f"dim_fuente?fuente_sk=eq.{fuente_sk}", True, "dw", "PATCH", fila_f, {"Prefer": "return=minimal"})
    else:
        fuente_sk = sb._peticion("dim_fuente", True, "dw", "POST", fila_f, {"Prefer": "return=representation"})[0]["fuente_sk"]
    sb.insertar("fact_seguridad", [dict(municipio_sk=int(r.municipio_sk), anio=int(r.Año), grupo_delito=r.grupo_delito,
                                        incidentes=int(r.incidentes), tasa_100k=float(r.tasa_100k), fuente_sk=fuente_sk)
                                   for r in g.itertuples()], "dw")
    print(f"✓ fact_seguridad: {len(g):,} filas")

    # Riesgo para el visitante por ruta (último año)
    ultimo = g["Año"].max()
    v = g[(g["Año"] == ultimo) & g.grupo_delito.isin(VISITANTE)].groupby("municipio_sk").tasa_100k.sum()
    pv = v.rank(pct=True)
    nombre = mun.set_index("municipio_sk").nombre
    paradas = sb.leer("fact_ruta_parada", "dw", "ruta_sk,municipio_sk", secreta=True)
    evaluadas = {r["ruta_sk"] for r in sb._peticion("fact_ruta_evaluacion?select=ruta_sk", True, "dw")}
    for sk, p in paradas[paradas.ruta_sk.isin(evaluadas)].groupby("ruta_sk"):
        peor = pv.reindex(p.municipio_sk).idxmax()
        q = pv[peor]
        nivel = "alto" if q >= 0.8 else ("medio" if q >= 0.5 else "bajo")
        texto = f"{nivel} (parada más alta: {nombre[peor]}, P{q * 100:.0f} estatal de delitos al visitante {ultimo})"
        sb._peticion(f"fact_ruta_evaluacion?ruta_sk=eq.{sk}", True, "dw", "PATCH", {"riesgo_seguridad": texto},
                     {"Prefer": "return=minimal"})
        print(f"  ruta #{sk}: {texto}")


if __name__ == "__main__":
    main()
