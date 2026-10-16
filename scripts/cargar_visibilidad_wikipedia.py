"""Visibilidad de los municipios: vistas de su artículo en Wikipedia en español (F6d del plan de afinación).

1. Wikidata: dos artículos de eswiki por municipio: el del municipio (clave INEGI municipal, propiedad P3801) y el
   de su localidad cabecera (clave de localidad INEGI terminada en 0001, propiedad P1976). La gente lee sobre todo el
   de la ciudad ("Atlixco", "Cholula de Rivadavia", "Puebla de Zaragoza"), no el de "Municipio de X"; contar solo el
   del municipio dejaba a la capital debajo de Tecamachalco (plan_migracion_front.md A1).
2. Cada título se resuelve a su forma canónica siguiendo redirecciones (API de MediaWiki) y se suman las vistas de
   la API de Wikimedia (per-article, usuarios humanos, todos los accesos), mensual, últimos 12 meses completos.
3. dw.fact_visibilidad: una fila por municipio con la suma del periodo (actividad_sk NULL = municipio completo) y
   los títulos usados en titulo_wikipedia.

Es un proxy gratuito y abierto del interés por el municipio, no de visitantes: cuenta lectores en español de
cualquier lugar.

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
SPARQL_CAB = ('SELECT ?code ?art WHERE { ?item wdt:P1976 ?code . FILTER(STRSTARTS(?code, "21") && STRENDS(?code, "0001") '
              '&& STRLEN(?code)=9) ?art schema:about ?item ; schema:isPartOf <https://es.wikipedia.org/> }')
VISTAS = ("https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/es.wikipedia/all-access/user/"
          "{titulo}/monthly/{ini}/{fin}")
FUENTE = dict(nombre="Vistas de página de Wikipedia en español (Wikimedia)", institucion="Fundación Wikimedia",
              tipo="API abierta", url="https://wikimedia.org/api/rest_v1/",
              licencia_terminos="Datos de vistas en dominio público (CC0); artículos enlazados por Wikidata (CC0)",
              cobertura="217 municipios de Puebla: artículo del municipio (P3801) + artículo de su cabecera (P1976, LOC 0001)",
              calidad_notas="Proxy de visibilidad/interés, no de visitantes. Usuarios humanos (agent=user), todos los "
                            "accesos; títulos canónicos (redirecciones resueltas). Los artículos de municipios grandes "
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

    def sparql(q):
        res = obtener("https://query.wikidata.org/sparql?" + urllib.parse.urlencode({"query": q, "format": "json"}))
        return {b["code"]["value"]: urllib.parse.unquote(b["art"]["value"].rsplit("/wiki/", 1)[1])
                for b in res["results"]["bindings"]}
    arts = sparql(SPARQL)
    cab = {k[:5]: v for k, v in sparql(SPARQL_CAB).items()}
    print(f"Wikidata: {len(arts)} municipios con artículo · {len(cab)} cabeceras con artículo propio")

    def canonico(titulo: str) -> str:
        r = obtener("https://es.wikipedia.org/w/api.php?" + urllib.parse.urlencode(
            {"action": "query", "titles": titulo.replace("_", " "), "redirects": 1, "format": "json"}))
        paginas = list(r["query"]["pages"].values())
        return paginas[0]["title"].replace(" ", "_") if paginas and "missing" not in paginas[0] else titulo

    def vistas_de(titulo: str) -> tuple[int, int]:
        d = obtener(VISTAS.format(titulo=urllib.parse.quote(titulo, safe=""), ini=ini.strftime("%Y%m%d00"),
                                  fin=fin.strftime("%Y%m%d00")))
        return (sum(i["views"] for i in d["items"]), len(d["items"])) if d else (0, 0)

    filas = []
    for cve in sorted(arts):
        titulos = list(dict.fromkeys(canonico(t) for t in (arts[cve], cab.get(cve)) if t))
        conteo = [vistas_de(t) for t in titulos]
        filas.append(dict(cve_geo=cve, titulo=" + ".join(titulos), vistas=sum(v for v, _ in conteo),
                          meses=max(m for _, m in conteo)))
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
                       vistas=int(r.vistas), titulo_wikipedia=r.titulo,
                       referencia="es.wikipedia.org/wiki/" + r.titulo.split(" + ")[0])
                  for r in df.itertuples()], {"Prefer": "return=minimal"})
    print(f"✓ fact_visibilidad: {len(df)} municipios")


if __name__ == "__main__":
    main()
