"""Visibilidad de los municipios: vistas de su artículo en Wikipedia en español (F6d del plan de afinación).

1. Wikidata: artículo de eswiki de cada municipio por su clave INEGI municipal (propiedad P3801).
2. API de vistas de Wikimedia (per-article, usuarios humanos, todos los accesos), mensual, últimos 12 meses completos.
3. dw.fact_visibilidad: una fila por municipio con la suma del periodo (actividad_sk NULL = municipio completo).

Es un proxy gratuito y abierto del interés por el municipio, no de visitantes: cuenta lectores en español de
cualquier lugar y solo el título exacto (no suma redirecciones).

Uso: python scripts/cargar_visibilidad_wikipedia.py [--fin AAAA-MM]   (por omisión, el último mes completo)
"""
import argparse
import json
import sys
import time
import urllib.parse
import urllib.request
from datetime import date
from pathlib import Path

import pandas as pd

RAIZ = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(RAIZ / "dashboard")]

import supabase_cliente as sb  # noqa: E402

UA = {"User-Agent": "MOPEDETU/1.0 (proyecto academico UTP; https://github.com/gemo98)"}
SPARQL = ('SELECT ?code ?art WHERE { ?item wdt:P3801 ?code . FILTER(STRSTARTS(?code, "21") && STRLEN(?code)=5) '
          '?art schema:about ?item ; schema:isPartOf <https://es.wikipedia.org/> }')
VISTAS = ("https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/es.wikipedia/all-access/user/"
          "{titulo}/monthly/{ini}/{fin}")
FUENTE = dict(nombre="Vistas de página de Wikipedia en español (Wikimedia)", institucion="Fundación Wikimedia",
              tipo="API abierta", url="https://wikimedia.org/api/rest_v1/",
              licencia_terminos="Datos de vistas en dominio público (CC0); artículos enlazados por Wikidata (CC0)",
              cobertura="217 municipios de Puebla (artículo de eswiki enlazado por la clave INEGI P3801)",
              calidad_notas="Proxy de visibilidad/interés, no de visitantes. Usuarios humanos (agent=user), todos los "
                            "accesos; solo el título exacto, sin redirecciones. Los artículos de municipios grandes "
                            "también reciben lectores por motivos no turísticos.",
              uso_en_modelo="fact_visibilidad · bandera OFERTA_INVISIBLE (oferta ≥ P60 y visibilidad ≤ P35)")


def obtener(url: str):
    for intento in range(4):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA | {"Accept": "application/json"}),
                                        timeout=60) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            time.sleep(5 * (intento + 1))
    raise SystemExit(f"No respondió: {url}")


def main():
    ap = argparse.ArgumentParser()
    hoy = date.today()
    ultimo = date(hoy.year, hoy.month, 1) - pd.offsets.MonthBegin(1)
    ap.add_argument("--fin", default=ultimo.strftime("%Y-%m"))
    args = ap.parse_args()
    fin = pd.Timestamp(args.fin + "-01")
    ini = fin - pd.DateOffset(months=11)
    periodo_fin = (fin + pd.offsets.MonthEnd(0)).date()

    res = obtener("https://query.wikidata.org/sparql?" + urllib.parse.urlencode({"query": SPARQL, "format": "json"}))
    arts = {b["code"]["value"]: urllib.parse.unquote(b["art"]["value"].rsplit("/wiki/", 1)[1])
            for b in res["results"]["bindings"]}
    print(f"Wikidata: {len(arts)} municipios con artículo en eswiki")

    filas = []
    for cve, titulo in sorted(arts.items()):
        d = obtener(VISTAS.format(titulo=urllib.parse.quote(titulo, safe=""), ini=ini.strftime("%Y%m%d00"),
                                  fin=fin.strftime("%Y%m%d00")))
        vistas = sum(i["views"] for i in d["items"]) if d else 0
        filas.append(dict(cve_geo=cve, titulo=titulo, vistas=vistas, meses=len(d["items"]) if d else 0))
        time.sleep(0.1)
    df = pd.DataFrame(filas)
    (RAIZ / "data" / "derivados").mkdir(exist_ok=True)
    df.to_csv(RAIZ / "data" / "derivados" / "visibilidad_wikipedia.csv", index=False)
    print(f"Vistas {ini.date()} a {periodo_fin}: total {df.vistas.sum():,} · mediana {df.vistas.median():,.0f} · "
          f"sin datos: {(df.meses == 0).sum()}")

    previa = sb._peticion("dim_fuente?select=fuente_sk&nombre=eq." + urllib.parse.quote(FUENTE["nombre"]), True, "dw")
    fila_f = {**FUENTE, "version_corte": f"{ini.date()} a {periodo_fin}", "fecha_descarga": hoy.isoformat()}
    if previa:
        fuente_sk = previa[0]["fuente_sk"]
        sb._peticion(f"dim_fuente?fuente_sk=eq.{fuente_sk}", True, "dw", "PATCH", fila_f, {"Prefer": "return=minimal"})
    else:
        fuente_sk = sb._peticion("dim_fuente", True, "dw", "POST", fila_f, {"Prefer": "return=representation"})[0]["fuente_sk"]
    mun = {r["cve_geo"].strip(): r["municipio_sk"] for r in sb._peticion("dim_municipio?select=municipio_sk,cve_geo", True, "dw")}
    sb._peticion(f"fact_visibilidad?fuente_sk=eq.{fuente_sk}&periodo_inicio=eq.{ini.date()}", True, "dw", "DELETE")
    sb._peticion("fact_visibilidad", True, "dw", "POST",
                 [dict(municipio_sk=mun[r.cve_geo], actividad_sk=None, fuente_sk=fuente_sk,
                       periodo_inicio=ini.date().isoformat(), periodo_fin=periodo_fin.isoformat(),
                       vistas=int(r.vistas), referencia=f"es.wikipedia.org/wiki/{r.titulo}")
                  for r in df.itertuples()], {"Prefer": "return=minimal"})
    print(f"✓ fact_visibilidad: {len(df)} municipios")


if __name__ == "__main__":
    main()
