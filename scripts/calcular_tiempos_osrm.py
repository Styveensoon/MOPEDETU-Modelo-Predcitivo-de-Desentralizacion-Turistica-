"""Tiempos y distancias por carretera entre cabeceras municipales (F1 del plan de afinación, D1).

Hasta ahora dw.fact_accesibilidad solo tenía línea recta × 1.8 min/km, que subestima hasta 3 veces en las sierras.
Este script:
  1. Toma la cabecera oficial de cada municipio (clave cve_cab del Catálogo Único de Claves Geoestadísticas de
     INEGI, servicio wscatgeo) y sus coordenadas del ITER 2020 (vienen en grados-minutos-segundos).
  2. Pide a OSRM la matriz completa (servicio `table`, perfil auto) por bloques de 50 × 50 cabeceras.
  3. Escribe dim_municipio.cabecera_* y fact_accesibilidad.{distancia_km_carretera, tiempo_min_carretera,
     fuente_tiempo, fecha_calculo}; tiempo_min_est (línea recta) no se toca.

Servidor: por omisión el público de project-osrm.org (uso justo: 25 peticiones con pausa, se registra como
'osrm_publico'). Con un OSRM local (Docker osrm/osrm-backend + extracto de México de Geofabrik) usar
--osrm http://localhost:5000 y queda como 'osrm_local'.

Uso:
    python scripts/calcular_tiempos_osrm.py --iter data/raw/iter/.../conjunto_de_datos_iter_21CSV20.csv
        [--osrm URL] [--sin-bd]
"""
import argparse
import json
import math
import re
import sys
import time
import urllib.parse
import urllib.request
from datetime import date
from pathlib import Path

import pandas as pd

RAIZ = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(RAIZ / "dashboard"), str(RAIZ / "scripts")]

import supabase_cliente as sb  # noqa: E402

SALIDA = RAIZ / "data" / "derivados"
OSRM_PUBLICO = "https://router.project-osrm.org"
URL_AGEEM = "https://gaia.inegi.org.mx/wscatgeo/v2/mgem/21"
BLOQUE = 50          # 50 orígenes + 50 destinos = 100 coordenadas por petición (límite del servidor público)
PAUSA_S = 1.5
VEL_MAX_KMH = 90     # control de snapping: ningún tiempo por carretera puede ser menor que la recta a 90 km/h
FUENTE = dict(nombre="OSRM · tiempos por carretera entre cabeceras", institucion="Proyecto OSRM sobre OpenStreetMap",
              tipo="API", url="https://project-osrm.org/",
              licencia_terminos="Datos ODbL (OpenStreetMap); servidor público con política de uso justo",
              cobertura="217 cabeceras municipales de Puebla, matriz completa 217 × 216",
              calidad_notas="Perfil auto sin tráfico: tiempos de flujo libre. Cabecera = cve_cab del Catálogo Único "
                            "de Claves Geoestadísticas (INEGI) con coordenadas del ITER 2020.",
              uso_en_modelo="fact_accesibilidad (tiempo_min_carretera), min_ancla_cercana, min_capital, rutas v2")


def dms_a_decimal(texto: str) -> float:
    """' 97°57'09.774" W' → -97.952715"""
    g, m, s, h = re.match(r"\s*(\d+)°(\d+)'([\d.]+)\"\s*([NSEW])", texto).groups()
    v = int(g) + int(m) / 60 + float(s) / 3600
    return -v if h in "SW" else v


def haversine_km(lat1, lon1, lat2, lon2):
    p = math.pi / 180
    a = math.sin((lat2 - lat1) * p / 2) ** 2 + math.cos(lat1 * p) * math.cos(lat2 * p) * math.sin((lon2 - lon1) * p / 2) ** 2
    return 2 * 6371.0 * math.asin(math.sqrt(a))


def cabeceras(iter_csv: str) -> pd.DataFrame:
    with urllib.request.urlopen(URL_AGEEM, timeout=120) as r:
        cat = pd.DataFrame(json.load(r)["datos"])[["cvegeo", "cve_mun", "cve_cab"]]
    it = pd.read_csv(iter_csv, dtype=str, encoding="utf-8-sig", usecols=["MUN", "LOC", "NOM_LOC", "LONGITUD", "LATITUD"])
    cab = cat.merge(it, left_on=["cve_mun", "cve_cab"], right_on=["MUN", "LOC"], how="left")
    faltan = cab[cab.LATITUD.isna()]
    if len(faltan):
        raise SystemExit(f"Cabeceras sin coordenadas en el ITER: {faltan.cvegeo.tolist()}")
    cab["lat"] = cab.LATITUD.map(dms_a_decimal).round(6)
    cab["lon"] = cab.LONGITUD.map(dms_a_decimal).round(6)
    print(f"Cabeceras: {len(cab)} · con LOC distinta de 0001: {(cab.cve_cab != '0001').sum()}")
    return cab.rename(columns={"cvegeo": "cve_geo", "NOM_LOC": "cabecera_nombre"})[
        ["cve_geo", "cve_cab", "cabecera_nombre", "lat", "lon"]]


def matriz(cab: pd.DataFrame, osrm: str) -> pd.DataFrame:
    coords = [f"{r.lon},{r.lat}" for r in cab.itertuples()]
    n, filas = len(coords), []
    bloques = [list(range(i, min(i + BLOQUE, n))) for i in range(0, n, BLOQUE)]
    for bo in bloques:
        for bd in bloques:
            pts = bo + [j for j in bd if j not in bo]
            url = (f"{osrm}/table/v1/driving/{';'.join(coords[k] for k in pts)}"
                   f"?sources={';'.join(str(pts.index(i)) for i in bo)}"
                   f"&destinations={';'.join(str(pts.index(j)) for j in bd)}&annotations=duration,distance")
            for intento in range(4):
                try:
                    req = urllib.request.Request(url, headers={"User-Agent": "MOPEDETU (proyecto académico UTP)"})
                    with urllib.request.urlopen(req, timeout=120) as r:
                        res = json.load(r)
                    break
                except Exception as e:  # noqa: BLE001
                    print(f"  reintento {intento + 1}: {e}")
                    time.sleep(10 * (intento + 1))
            else:
                raise SystemExit("OSRM no respondió")
            if res.get("code") != "Ok":
                raise SystemExit(f"OSRM: {res}")
            for a, i in enumerate(bo):
                for b, j in enumerate(bd):
                    if i != j:
                        filas.append((cab.cve_geo.iat[i], cab.cve_geo.iat[j],
                                      res["durations"][a][b], res["distances"][a][b]))
            time.sleep(PAUSA_S)
        print(f"  bloque de orígenes {bo[0]}-{bo[-1]} listo")
    m = pd.DataFrame(filas, columns=["origen", "destino", "seg", "m"])
    m["tiempo_min_carretera"] = (m.seg / 60).round(1)
    m["distancia_km_carretera"] = (m.m / 1000).round(2)
    return m.drop(columns=["seg", "m"])


def controles(m: pd.DataFrame, cab: pd.DataFrame) -> pd.DataFrame:
    p = cab.set_index("cve_geo")
    recta = [haversine_km(p.lat[o], p.lon[o], p.lat[d], p.lon[d]) for o, d in zip(m.origen, m.destino)]
    m["km_recta_cabeceras"] = recta
    sin_ruta = m.tiempo_min_carretera.isna()
    rapido = m.tiempo_min_carretera < m.km_recta_cabeceras / VEL_MAX_KMH * 60
    print(f"Pares: {len(m)} · sin ruta: {sin_ruta.sum()} · más rápidos que la recta a {VEL_MAX_KMH} km/h: {rapido.sum()}")
    if rapido.any():
        print(m[rapido].head(10).to_string())
    return m


def cargar(cab: pd.DataFrame, m: pd.DataFrame, fuente_tiempo: str) -> None:
    mun = sb.leer("dim_municipio", "dw", "municipio_sk,cve_geo", secreta=True)
    msk = dict(zip(mun.cve_geo, mun.municipio_sk))
    for r in cab.itertuples():
        sb._peticion(f"dim_municipio?municipio_sk=eq.{msk[r.cve_geo]}", True, "dw", "PATCH",
                     {"cabecera_nombre": r.cabecera_nombre, "cabecera_lat": r.lat, "cabecera_lon": r.lon},
                     {"Prefer": "return=minimal"})
    print(f"✓ dim_municipio: cabeceras de {len(cab)} municipios")

    # Upsert con todas las columnas de la fila (las de línea recta se reenvían iguales).
    acc = sb.leer("fact_accesibilidad", "dw",
                  "municipio_origen_sk,municipio_destino_sk,distancia_km_recta,tiempo_min_est,es_colindante", secreta=True)
    m = m.assign(municipio_origen_sk=m.origen.map(msk), municipio_destino_sk=m.destino.map(msk))
    acc = acc.merge(m[["municipio_origen_sk", "municipio_destino_sk", "tiempo_min_carretera", "distancia_km_carretera"]],
                    how="left")
    hoy = date.today().isoformat()
    filas = [dict(municipio_origen_sk=int(r.municipio_origen_sk), municipio_destino_sk=int(r.municipio_destino_sk),
                  distancia_km_recta=float(r.distancia_km_recta), tiempo_min_est=float(r.tiempo_min_est),
                  es_colindante=bool(r.es_colindante),
                  tiempo_min_carretera=None if pd.isna(r.tiempo_min_carretera) else float(r.tiempo_min_carretera),
                  distancia_km_carretera=None if pd.isna(r.distancia_km_carretera) else float(r.distancia_km_carretera),
                  fuente_tiempo=None if pd.isna(r.tiempo_min_carretera) else fuente_tiempo,
                  fecha_calculo=None if pd.isna(r.tiempo_min_carretera) else hoy)
             for r in acc.itertuples()]
    sb.insertar("fact_accesibilidad", filas, "dw")
    print(f"✓ fact_accesibilidad: {sum(f['fuente_tiempo'] is not None for f in filas)} de {len(filas)} pares con tiempo por carretera")

    existentes = sb._peticion(f"dim_fuente?select=fuente_sk&nombre=eq.{urllib.parse.quote(FUENTE['nombre'])}", True, "dw")
    fila = {**FUENTE, "version_corte": f"{fuente_tiempo}, {hoy}", "fecha_descarga": hoy}
    if existentes:
        sb._peticion(f"dim_fuente?fuente_sk=eq.{existentes[0]['fuente_sk']}", True, "dw", "PATCH", fila,
                     {"Prefer": "return=minimal"})
    else:
        sb._peticion("dim_fuente", True, "dw", "POST", fila, {"Prefer": "return=minimal"})
    print("✓ dim_fuente: OSRM registrado")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--iter", required=True)
    ap.add_argument("--osrm", default=OSRM_PUBLICO)
    ap.add_argument("--sin-bd", action="store_true")
    args = ap.parse_args()
    fuente_tiempo = "osrm_publico" if "project-osrm.org" in args.osrm or "openstreetmap.de" in args.osrm else "osrm_local"

    SALIDA.mkdir(parents=True, exist_ok=True)
    cab = cabeceras(args.iter)
    cab.to_csv(SALIDA / "cabeceras_municipales.csv", index=False)
    archivo = SALIDA / "tiempos_carretera.csv"
    if archivo.exists():
        print(f"Usando la matriz ya calculada en {archivo.relative_to(RAIZ)} (borrarla para volver a pedirla)")
        m = pd.read_csv(archivo, dtype={"origen": str, "destino": str})
    else:
        m = controles(matriz(cab, args.osrm), cab)
        m.to_csv(archivo, index=False)
    if not args.sin_bd:
        cargar(cab, m, fuente_tiempo)


if __name__ == "__main__":
    main()
