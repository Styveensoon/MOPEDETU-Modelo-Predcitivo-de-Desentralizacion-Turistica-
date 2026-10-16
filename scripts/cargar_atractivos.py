"""Atractivos con nombre por municipio: catálogo curado + OpenStreetMap → dw.fact_atractivo_lugar.

Por qué: el DENUE registra negocios, no lugares. Un santuario, una peña o una cascada sin negocio detrás
(p. ej. El Peñón de Jonotla) no aparecía en el modelo. Esta tabla los nombra, los asigna a su municipio
y dice qué actividades respaldan, para que cuenten como señal de catálogo en las actividades (A1).

Clasificación (conservadora para no inflar actividades):
  religioso   santuarios, basílicas, ermitas, conventos (las parroquias y templos comunes se listan sin señal)
  ecoturismo  cascadas, grutas, manantiales, cañadas, peñas, miradores
  volcanes    volcanes
  catálogo    lo que diga data/catalogos/atractivos.csv (revisado a mano, con fuente)

Uso: python scripts/cargar_atractivos.py --osm DIR_OSM --geo GEOJSON_INEGI
"""
import argparse
import csv
import json
import re
import sys
import unicodedata
from pathlib import Path

import pandas as pd
from shapely.geometry import Point, shape
from shapely.strtree import STRtree

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "dashboard"))
import supabase_cliente as sb  # noqa: E402

FECHA = "2026-10-14"
FUENTE_CURADA = dict(nombre="Catálogo curado de atractivos", institucion="MOPEDETU (revisión manual con fuentes)",
                     tipo="Catálogo manual", url="https://github.com/Styveensoon/MOPEDETU-Modelo-Predcitivo-de-Desentralizacion-Turistica-",
                     version_corte="data/catalogos/atractivos.csv", fecha_descarga=FECHA,
                     licencia_terminos="Fuentes públicas citadas por atractivo",
                     calidad_notas="Atractivos que no están en OpenStreetMap ni tienen un negocio en el DENUE; cada uno con URL de fuente.",
                     uso_en_modelo="Señal de catálogo para actividades (A1) y ficha técnica")
RELIGIOSO = re.compile(r"santuario|basilica|ermita|convento|ex convento|exconvento", re.I)
NATURAL = {"waterfall": "cascada", "cave_entrance": "gruta", "spring": "manantial", "gorge": "cañada",
           "cliff": "peña", "rock": "peña", "peak": "cerro", "volcano": "volcán"}


def sin_acentos(t: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", t.lower()) if not unicodedata.combining(c))


def clasificar(t: dict) -> tuple[str, list]:
    nombre = sin_acentos(t.get("name", ""))
    if t.get("amenity") == "place_of_worship":
        return ("santuario", ["religioso"]) if RELIGIOSO.search(nombre) else ("templo", [])
    nat = t.get("natural") or ("waterfall" if t.get("waterway") == "waterfall" else None)
    if nat:
        cat = NATURAL.get(nat, nat)
        if nat == "volcano":
            return cat, ["volcanes"]
        return cat, ([] if nat == "peak" else ["ecoturismo"])
    if t.get("tourism") == "viewpoint":
        return "mirador", ["ecoturismo"]
    if t.get("historic") in ("monastery",) or RELIGIOSO.search(nombre):
        return "santuario", ["religioso"]
    if "arqueolog" in nombre or t.get("historic") == "archaeological_site":
        return "zona_arqueologica", ["arqueologia"]
    if "museo" in nombre or t.get("tourism") == "museum":
        return "museo", ["museos"]
    if "cascada" in nombre or "gruta" in nombre or "parque ecolog" in nombre:
        return "naturaleza", ["ecoturismo"]
    return "atractivo", []


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--osm", required=True)
    ap.add_argument("--geo", required=True)
    args = ap.parse_args()

    geo = json.loads(Path(args.geo).read_text(encoding="utf-8"))
    polys = {f["properties"]["CVEGEO"]: shape(f["geometry"]).buffer(0) for f in geo["features"]}
    claves = list(polys)
    arbol = STRtree([polys[c] for c in claves])
    mun = sb.leer("dim_municipio", "dw", "municipio_sk,cve_geo,nombre", secreta=True)
    mun["cve_geo"] = mun.cve_geo.str.strip()
    msk = dict(zip(mun.cve_geo, mun.municipio_sk))
    por_nombre = {sin_acentos(n): c for c, n in zip(mun.cve_geo, mun.nombre)}

    fuentes = {r["nombre"]: r["fuente_sk"] for r in sb._peticion("dim_fuente?select=fuente_sk,nombre", True, "dw")}
    if FUENTE_CURADA["nombre"] not in fuentes:
        fuentes[FUENTE_CURADA["nombre"]] = sb._peticion("dim_fuente", True, "dw", "POST", FUENTE_CURADA,
                                                        {"Prefer": "return=representation"})[0]["fuente_sk"]
    f_cur = fuentes[FUENTE_CURADA["nombre"]]
    f_osm = fuentes["OpenStreetMap · red vial principal y servicios (Overpass)"]

    filas = []
    with (RAIZ / "data" / "catalogos" / "atractivos.csv").open(encoding="utf-8") as f:
        for r in csv.DictReader(f):
            cve = por_nombre[sin_acentos(r["municipio"])]
            # lat/lon solo cuando hay una fuente verificable del punto; sin ellas el circuito omite el lugar
            lat, lon = (float(r["lat"]), float(r["lon"])) if r.get("lat") and r.get("lon") else (None, None)
            filas.append(dict(cve_geo=cve, nombre=r["nombre"].strip(), categoria=r["categoria"],
                              actividades=[a for a in r["actividades"].split("|") if a], descripcion=r["descripcion"],
                              lat=lat, lon=lon, origen="catalogo_curado", fuente_sk=f_cur, url=r["fuente_url"]))
    for archivo in ("atractivos.json", "puntos.json"):
        for e in json.loads((Path(args.osm) / archivo).read_text(encoding="utf-8"))["elements"]:
            t = e.get("tags", {})
            if not t.get("name"):
                continue
            if archivo == "puntos.json" and not (t.get("tourism") in ("attraction", "museum", "viewpoint")
                                                 or t.get("historic")):
                continue
            lat, lon = (e.get("lat"), e.get("lon")) if "lat" in e else (e.get("center", {}).get("lat"),
                                                                        e.get("center", {}).get("lon"))
            if lat is None:
                continue
            p = Point(lon, lat)
            cve = next((claves[j] for j in arbol.query(p, predicate="intersects")), None)
            if cve is None:
                continue
            cat, acts = clasificar(t)
            filas.append(dict(cve_geo=cve, nombre=t["name"].strip(), categoria=cat, actividades=acts,
                              descripcion=t.get("description"), lat=round(lat, 6), lon=round(lon, 6), origen="osm",
                              fuente_sk=f_osm, url=f"https://www.openstreetmap.org/{e['type']}/{e['id']}"))
    df = pd.DataFrame(filas)
    df["clave"] = df.nombre.map(sin_acentos)
    df = df.drop_duplicates(["cve_geo", "clave"]).drop(columns="clave")  # el curado va primero y gana

    salida = RAIZ / "data" / "derivados" / "atractivos_lugares.csv"
    df.assign(actividades=df.actividades.map("|".join)).to_csv(salida, index=False)
    registros = [dict(municipio_sk=int(msk[r.cve_geo]), nombre=r.nombre, categoria=r.categoria,
                      actividades=r.actividades, descripcion=r.descripcion if isinstance(r.descripcion, str) else None,
                      lat=None if pd.isna(r.lat) else r.lat, lon=None if pd.isna(r.lon) else r.lon,
                      origen=r.origen, fuente_sk=int(r.fuente_sk), url=r.url) for r in df.itertuples()]
    sb._peticion("fact_atractivo_lugar?atractivo_sk=gt.0", True, "dw", "DELETE")
    for i in range(0, len(registros), 500):
        sb._peticion("fact_atractivo_lugar", True, "dw", "POST", registros[i:i + 500], {"Prefer": "return=minimal"})
    con = df[df.actividades.map(bool)]
    print(f"✓ fact_atractivo_lugar: {len(df)} atractivos con nombre en {df.cve_geo.nunique()} municipios "
          f"(curados {sum(df.origen == 'catalogo_curado')}, OSM {sum(df.origen == 'osm')}) · "
          f"con señal de actividad: {len(con)} → {con.explode('actividades').actividades.value_counts().to_dict()}")
    print(f"  {salida.relative_to(RAIZ)}")


if __name__ == "__main__":
    main()
