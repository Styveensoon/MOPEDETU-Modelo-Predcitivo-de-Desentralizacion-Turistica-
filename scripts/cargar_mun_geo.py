"""Carga los polígonos municipales de Puebla (Marco Geoestadístico, INEGI) en stg.mun_geo.

Uso:
    python scripts/cargar_mun_geo.py data/raw/mg/21_puebla.zip --edicion "Diciembre 2024"

- Filtra la entidad 21 y exige 217 municipios.
- Reproyecta de la cónica conforme de Lambert de INEGI a EPSG:4326 (lo exige el DDL).
- Simplifica como cobertura (las fronteras compartidas quedan idénticas entre vecinos) cuando
  la versión de geopandas lo permite; si no, simplifica municipio por municipio.
- Reemplaza el contenido de stg.mun_geo (se puede volver a ejecutar) y documenta la fuente.
"""
import argparse
import zipfile
from datetime import date
from pathlib import Path

import geopandas as gpd
from shapely.geometry import MultiPolygon, Polygon
from sqlalchemy import text

from db import motor

TOLERANCIA = 0.001  # grados (~100 m)


def a_multipoligono(g):
    if isinstance(g, MultiPolygon):
        return g
    if isinstance(g, Polygon):
        return MultiPolygon([g])
    # make_valid puede devolver GeometryCollection: conservar solo las partes poligonales
    partes = [p for p in getattr(g, "geoms", []) if isinstance(p, (Polygon, MultiPolygon))]
    polis = []
    for p in partes:
        polis.extend(p.geoms if isinstance(p, MultiPolygon) else [p])
    return MultiPolygon(polis)


def buscar_shp(zip_path: Path) -> Path:
    destino = zip_path.with_suffix("")
    if not destino.exists():
        with zipfile.ZipFile(zip_path) as z:
            z.extractall(destino)
    candidatos = sorted(destino.rglob("*mun.shp"))
    if not candidatos:
        raise SystemExit(f"No encontré la capa municipal (*mun.shp) dentro de {zip_path}")
    return candidatos[0]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("zip")
    ap.add_argument("--edicion", required=True, help='Edición del Marco Geoestadístico, p. ej. "Diciembre 2024"')
    args = ap.parse_args()

    shp = buscar_shp(Path(args.zip))
    gdf = gpd.read_file(shp)
    gdf = gdf[gdf["CVE_ENT"] == "21"].copy()
    if len(gdf) != 217:
        raise SystemExit(f"Se esperaban 217 municipios y hay {len(gdf)}")

    gdf = gdf.to_crs(epsg=4326)
    gdf["geometry"] = gdf.geometry.make_valid()
    if hasattr(gdf.geometry, "simplify_coverage"):
        gdf["geometry"] = gdf.geometry.simplify_coverage(TOLERANCIA)
        metodo = "simplify_coverage"
    else:
        gdf["geometry"] = gdf.geometry.simplify(TOLERANCIA, preserve_topology=True)
        metodo = "simplify por municipio"
    gdf["geometry"] = gdf.geometry.make_valid().apply(a_multipoligono)

    salida = gpd.GeoDataFrame(
        {"cve_geo": gdf["CVE_ENT"] + gdf["CVE_MUN"], "nombre": gdf["NOMGEO"]},
        geometry=gdf.geometry.values, crs="EPSG:4326",
    ).rename_geometry("geom")
    assert salida["cve_geo"].is_unique and salida["cve_geo"].str.match(r"^21\d{3}$").all()
    vacias = salida.geom.is_empty.sum()
    if vacias:
        raise SystemExit(f"{vacias} geometrías quedaron vacías tras simplificar")

    with motor().begin() as conn:
        conn.execute(text("DELETE FROM stg.mun_geo"))
        salida.to_postgis("mun_geo", conn, schema="stg", if_exists="append", index=False)
        conn.execute(text("""
            UPDATE dw.dim_fuente
               SET version_corte = :ed, fecha_descarga = :hoy,
                   url = 'https://www.inegi.org.mx/temas/mg/',
                   licencia_terminos = 'Términos de Libre Uso de la Información del INEGI (citar la fuente)',
                   cobertura = 'Puebla (entidad 21), 217 municipios',
                   calidad_notas = :notas
             WHERE nombre = 'Marco Geoestadístico'"""),
            {"ed": args.edicion, "hoy": date.today(),
             "notas": f"Reproyectado a EPSG:4326 y simplificado ({metodo}, tolerancia {TOLERANCIA}°). "
                      "Superficies y distancias calculadas sobre la geometría simplificada."})
    print(f"stg.mun_geo: {len(salida)} municipios cargados ({metodo})")


if __name__ == "__main__":
    main()
