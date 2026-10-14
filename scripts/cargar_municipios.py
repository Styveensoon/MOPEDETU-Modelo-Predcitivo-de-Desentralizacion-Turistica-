"""Carga los 217 municipios de Puebla en stg.mun_geo y dw.dim_municipio desde el Marco Geoestadístico de INEGI.

Fuente: https://github.com/PhantomInsights/mexico-geojson (2023/states/Puebla.json), polígonos de INEGI 2023
a resolución completa. Las geometrías se envían como EWKT (SRID 4326) y los polígonos simples se
convierten a MultiPolygon, que es el tipo de la columna.

dim_municipio se sincroniza por cve_geo (municipio_sk es identity): inserta las claves que faltan y
actualiza las existentes, sin tocar es_pueblo_magico, es_ancla ni region
(eso lo hace scripts/cargar_rutas_existentes.py).

Uso:
    python scripts/cargar_municipios.py [ruta/a/Puebla.json]
"""
import json
import sys
import urllib.request
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "dashboard"))

import supabase_cliente as sb  # noqa: E402

URL = "https://raw.githubusercontent.com/PhantomInsights/mexico-geojson/main/2023/states/Puebla.json"
GEO_SIMPLE = RAIZ / "data" / "geo" / "puebla_municipios.geojson"
LOTE = 10


def _anillo(coords) -> str:
    return "(" + ",".join(f"{x[0]} {x[1]}" for x in coords) + ")"


def ewkt_multipolygon(geom) -> str:
    polys = [geom["coordinates"]] if geom["type"] == "Polygon" else geom["coordinates"]
    return "SRID=4326;MULTIPOLYGON(" + ",".join("(" + ",".join(_anillo(r) for r in p) + ")" for p in polys) + ")"


def leer_fuente(ruta: str | None) -> dict:
    if ruta:
        return json.loads(Path(ruta).read_text(encoding="utf-8"))
    with urllib.request.urlopen(URL, timeout=120) as r:
        return json.loads(r.read().decode("utf-8"))


def main():
    geo = leer_fuente(sys.argv[1] if len(sys.argv) > 1 else None)
    feats = sorted(geo["features"], key=lambda f: f["properties"]["CVEGEO"])
    assert len(feats) == 217, f"Se esperaban 217 municipios y llegaron {len(feats)}"

    # Centroide (punto interior del polígono principal) calculado por scripts/preparar_geo.py.
    simple = json.loads(GEO_SIMPLE.read_text(encoding="utf-8"))
    centro = {f["properties"]["cve_geo"]: f["properties"] for f in simple["features"]}

    filas_stg, filas_dim = [], []
    for f in feats:
        p = f["properties"]
        cve = p["CVEGEO"]
        geom = ewkt_multipolygon(f["geometry"])
        c = centro[cve]
        filas_stg.append(dict(cve_geo=cve, nombre=p["NOMGEO"], geom=geom))
        # cve_ent y cve_mun son columnas generadas a partir de cve_geo.
        filas_dim.append(dict(cve_geo=cve, nombre=p["NOMGEO"],
                              superficie_km2=round(float(c["area_km2"]), 3), geom=geom,
                              centroide=f"SRID=4326;POINT({c['lon']} {c['lat']})"))

    # stg.mun_geo: tabla de entrada; se reemplaza completa.
    sb._peticion("mun_geo?cve_geo=not.is.null", True, "stg", "DELETE")
    for i in range(0, len(filas_stg), LOTE):
        sb._peticion("mun_geo", True, "stg", "POST", filas_stg[i:i + LOTE], {"Prefer": "return=minimal"})
    print(f"✓ stg.mun_geo: {len(filas_stg)} municipios")

    actuales = sb._peticion("dim_municipio?select=cve_geo", True, "dw")
    existentes = {r["cve_geo"].strip() for r in actuales}
    nuevas = [r for r in filas_dim if r["cve_geo"] not in existentes]
    for i in range(0, len(nuevas), LOTE):
        sb._peticion("dim_municipio", True, "dw", "POST", nuevas[i:i + LOTE], {"Prefer": "return=minimal"})
    for r in filas_dim:
        if r["cve_geo"] in existentes:
            sb._peticion(f"dim_municipio?cve_geo=eq.{r['cve_geo']}", True, "dw", "PATCH", r,
                         {"Prefer": "return=minimal"})
    print(f"✓ dw.dim_municipio: {len(nuevas)} insertados, {len(filas_dim) - len(nuevas)} actualizados")


if __name__ == "__main__":
    main()
