"""Simplifica el GeoJSON oficial de municipios de Puebla (INEGI) para el tablero.

Fuente: https://github.com/PhantomInsights/mexico-geojson (2023/states/Puebla.json),
derivado del Marco Geoestadístico de INEGI.

Uso:
    python scripts/preparar_geo.py <entrada.json> data/geo/puebla_municipios.geojson
"""

import json
import math
import sys

TOLERANCIA = 0.0025  # grados (~250 m); suficiente para escala estatal
DECIMALES = 4


def _dist_segmento(p, a, b):
    (x, y), (x1, y1), (x2, y2) = p, a, b
    dx, dy = x2 - x1, y2 - y1
    if dx == 0 and dy == 0:
        return math.hypot(x - x1, y - y1)
    t = max(0.0, min(1.0, ((x - x1) * dx + (y - y1) * dy) / (dx * dx + dy * dy)))
    return math.hypot(x - (x1 + t * dx), y - (y1 + t * dy))


def rdp(puntos, tol):
    """Ramer-Douglas-Peucker iterativo."""
    if len(puntos) < 3:
        return puntos
    conservar = [False] * len(puntos)
    conservar[0] = conservar[-1] = True
    pila = [(0, len(puntos) - 1)]
    while pila:
        i, j = pila.pop()
        dmax, idx = 0.0, None
        for k in range(i + 1, j):
            d = _dist_segmento(puntos[k], puntos[i], puntos[j])
            if d > dmax:
                dmax, idx = d, k
        if idx is not None and dmax > tol:
            conservar[idx] = True
            pila += [(i, idx), (idx, j)]
    return [p for p, c in zip(puntos, conservar) if c]


def simplificar_anillo(anillo):
    pts = rdp([tuple(p[:2]) for p in anillo], TOLERANCIA)
    pts = [[round(x, DECIMALES), round(y, DECIMALES)] for x, y in pts]
    if len(pts) < 4:
        return None
    if pts[0] != pts[-1]:
        pts.append(pts[0])
    return pts


def poligonos(geom):
    if geom["type"] == "Polygon":
        return [geom["coordinates"]]
    return geom["coordinates"]


def area_centroide(anillo):
    a = cx = cy = 0.0
    for (x1, y1), (x2, y2) in zip(anillo, anillo[1:]):
        f = x1 * y2 - x2 * y1
        a += f
        cx += (x1 + x2) * f
        cy += (y1 + y2) * f
    a /= 2
    if a == 0:
        return 0.0, anillo[0][0], anillo[0][1]
    return abs(a), cx / (6 * a), cy / (6 * a)


def main(entrada, salida):
    with open(entrada, encoding="utf-8") as fh:
        gj = json.load(fh)

    features = []
    for f in gj["features"]:
        p = f["properties"]
        nuevos, mejor = [], (0.0, 0.0, 0.0)
        for poly in poligonos(f["geometry"]):
            ext = simplificar_anillo(poly[0])
            if not ext:
                continue
            nuevos.append([ext])
            ac = area_centroide([tuple(x[:2]) for x in poly[0]])
            if ac[0] > mejor[0]:
                mejor = ac
        features.append({
            "type": "Feature",
            "properties": {
                "cve_geo": p["CVEGEO"],
                "cve_mun": p["CVE_MUN"],
                "nombre": p["NOMGEO"],
                "area_km2": round(p.get("AREA", 0.0), 1),
                "lon": round(mejor[1], 5),
                "lat": round(mejor[2], 5),
            },
            "geometry": {"type": "MultiPolygon", "coordinates": nuevos},
        })

    features.sort(key=lambda x: x["properties"]["cve_geo"])
    with open(salida, "w", encoding="utf-8") as fh:
        json.dump({"type": "FeatureCollection", "features": features}, fh,
                  ensure_ascii=False, separators=(",", ":"))
    print(f"{len(features)} municipios -> {salida}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
