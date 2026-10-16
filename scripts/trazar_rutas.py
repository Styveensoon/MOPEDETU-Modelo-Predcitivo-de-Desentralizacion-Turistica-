"""Trazo por carretera guardado de las rutas del modelo (plan_migracion_front.md §12.2).

Para cada ruta propuesta o descartada pide a OSRM (servicio route, perfil auto) el recorrido entre las cabeceras
de sus paradas, en el orden de la ruta, y guarda en dw.fact_ruta_evaluacion:
  geom_trazo (GeoJSON LineString simplificado), km_carretera, min_carretera y fuente_trazo.
El tablero dibuja este trazo y solo llama a OSRM en vivo para rutas armadas por el usuario.
Se corre después de model/rutas.py (que vuelve a crear las rutas).

Uso: python scripts/trazar_rutas.py
"""
import json
import sys
import time
import urllib.request
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(RAIZ / "dashboard")]

import supabase_cliente as sb  # noqa: E402

SERVIDORES = [("osrm_fossgis", "https://routing.openstreetmap.de/routed-car/route/v1/driving/"),
              ("osrm_publico", "https://router.project-osrm.org/route/v1/driving/")]
UA = {"User-Agent": "MOPEDETU/1.0 (proyecto academico UTP)"}


def trazar(puntos: list[tuple[float, float]]):
    coords = ";".join(f"{lon},{lat}" for lat, lon in puntos)
    for nombre, base in SERVIDORES:
        for intento in range(3):
            try:
                req = urllib.request.Request(f"{base}{coords}?overview=simplified&geometries=geojson", headers=UA)
                with urllib.request.urlopen(req, timeout=60) as r:
                    res = json.load(r)
                if res.get("code") == "Ok":
                    ruta = res["routes"][0]
                    return nombre, ruta["geometry"], ruta["distance"] / 1000, ruta["duration"] / 60
            except Exception as e:  # noqa: BLE001 - servidor público: reintentar o pasar al siguiente
                print(f"  {nombre} intento {intento + 1}: {e}")
                time.sleep(3 * (intento + 1))
    return None


def main():
    rp = sb.leer("v_ruta_parada", "dw", "ruta_sk,ruta,origen,orden_parada,lat,lon", secreta=True)
    rp = rp[rp.origen.isin(["propuesta_modelo", "propuesta_descartada"])].sort_values(["ruta_sk", "orden_parada"])
    sin = []
    for sk, g in rp.groupby("ruta_sk"):
        r = trazar([(float(a), float(o)) for a, o in zip(g.lat, g.lon)])
        if r is None:
            sin.append(g.ruta.iat[0])
            continue
        fuente, geom, km, minutos = r
        sb._peticion(f"fact_ruta_evaluacion?ruta_sk=eq.{sk}", True, "dw", "PATCH",
                     dict(geom_trazo=geom, km_carretera=round(km, 1), min_carretera=round(minutos, 1),
                          fuente_trazo=fuente), {"Prefer": "return=minimal"})
        print(f"✓ #{sk} {g.ruta.iat[0]}: {km:.0f} km · {minutos:.0f} min · {len(geom['coordinates'])} puntos ({fuente})")
        time.sleep(1)
    if sin:
        raise SystemExit(f"Sin trazo (OSRM no respondió): {sin}")


if __name__ == "__main__":
    main()
