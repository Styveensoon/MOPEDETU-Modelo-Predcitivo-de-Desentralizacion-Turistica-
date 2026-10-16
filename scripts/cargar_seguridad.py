"""Incidencia delictiva municipal (SESNSP) → dw.fact_seguridad y riesgo de las rutas (F6c del plan de afinación).

Fuente: "Incidencia delictiva del fuero común municipal 2015-2025" (metodología 2015-2025) del Secretariado Ejecutivo
del Sistema Nacional de Seguridad Pública, en https://www.gob.mx/sesnsp/acciones-y-programas/datos-abiertos-de-incidencia-delictiva
(enlace de SharePoint; se descarga con .../_layouts/15/download.aspx?share=<id>).

Agrupación (por subtipo):
  homicidio            homicidio doloso y feminicidio
  robo_transeunte      robo a transeúnte (vía pública y espacio abierto) y en transporte público e individual
  robo_carretera       robo a transportista (carreteras)
  secuestro_extorsion  secuestro y extorsión
  otros                el resto
Tasa por 100 mil habitantes con la población CONAPO del año (dw.fact_poblacion_anual; si falta, Censo 2020).

Riesgo de ruta (fact_ruta_evaluacion.riesgo_seguridad), con el último año y por separado (plan_migracion_front A6):
  · delitos en el municipio: homicidio + secuestro/extorsión + robo a transeúnte, por 100 mil hab.
  · robo en carretera: robo a transportista, por 100 mil hab. (lo pone la autopista que cruza el municipio, no el
    municipio; antes se mezclaba y dejaba a Esperanza como el municipio "más peligroso")
Cada uno en percentil estatal; el nivel de la ruta sale del percentil MEDIO de sus paradas: bajo (< P50), medio
(P50-P80), alto (≥ P80), y se informa la parada más alta. Con el máximo, casi toda ruta de 6 paradas salía "alta"
(en municipios chicos una o dos denuncias disparan la tasa).
Es un semáforo para el operador, no una etiqueta pública del municipio; SESNSP mide denuncias, no victimización.

Uso: python scripts/cargar_seguridad.py data/raw/sesnsp/idm_puebla_2015_2025.csv
     python scripts/cargar_seguridad.py --solo-riesgo     (recalcula el riesgo de las rutas con fact_seguridad)
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
    "robo_transeunte": {"Robo a transeúnte en vía pública", "Robo a transeúnte en espacio abierto al público",
                        "Robo en transporte público colectivo", "Robo en transporte individual",
                        "Robo en transporte público individual"},
    "robo_carretera": {"Robo a transportista"},
    "secuestro_extorsion": {"Secuestro", "Extorsión"},
}
EN_MUNICIPIO = ["homicidio", "secuestro_extorsion", "robo_transeunte"]
CARRETERA = ["robo_carretera"]
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
    if "--solo-riesgo" in sys.argv:
        riesgo_rutas()
        return
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
    riesgo_rutas()


def riesgo_rutas():
    """Riesgo para el visitante de cada ruta evaluada, con el último año de dw.fact_seguridad."""
    g = sb.leer("fact_seguridad", "dw", "municipio_sk,anio,grupo_delito,tasa_100k", secreta=True)
    g["tasa_100k"] = g.tasa_100k.astype(float)
    ultimo = int(g.anio.max())
    ult = g[g.anio == ultimo]
    mun = sb.leer("dim_municipio", "dw", "municipio_sk,nombre", secreta=True)
    pct = {k: ult[ult.grupo_delito.isin(grupos)].groupby("municipio_sk").tasa_100k.sum().rank(pct=True)
           for k, grupos in (("municipio", EN_MUNICIPIO), ("carretera", CARRETERA))}
    nombre = mun.set_index("municipio_sk").nombre
    paradas = sb.leer("fact_ruta_parada", "dw", "ruta_sk,municipio_sk", secreta=True)
    evaluadas = {r["ruta_sk"] for r in sb._peticion("fact_ruta_evaluacion?select=ruta_sk", True, "dw")}

    def nivel(q):
        return "alto" if q >= 0.8 else ("medio" if q >= 0.5 else "bajo")

    for sk, p in paradas[paradas.ruta_sk.isin(evaluadas)].groupby("ruta_sk"):
        partes = []
        for etiqueta, pv in (("delitos en el municipio", pct["municipio"]), ("robo en carretera", pct["carretera"])):
            q = pv.reindex(p.municipio_sk)
            peor = q.idxmax()
            partes.append(f"{etiqueta}: {nivel(q.mean())} (P{q.mean() * 100:.0f} medio; más alta "
                          f"{nombre[peor]} P{q[peor] * 100:.0f})")
        texto = " · ".join(partes) + f" · SESNSP {ultimo}"
        sb._peticion(f"fact_ruta_evaluacion?ruta_sk=eq.{sk}", True, "dw", "PATCH", {"riesgo_seguridad": texto},
                     {"Prefer": "return=minimal"})
        print(f"  ruta #{sk}: {texto}")


if __name__ == "__main__":
    main()
