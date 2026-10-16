"""Circuitos precalculados por municipio (plan_migracion_front.md A10) con model/reglas_circuitos.py.

Para cada municipio apto (dw.v_aptitud_circuito):
  · variado de medio día (4 h) y de un día (8 h), a pie y en auto
  · temático (4 h en auto) por cada actividad principal del municipio con ≥ 3 puntos de esa actividad
El estándar (el que el tablero muestra por omisión) es el primer variado que cumple en este orden: 4 h a pie, 4 h en
auto, 8 h a pie, 8 h en auto. Un municipio es APTO si tiene estándar que cumple (v_aptitud_circuito). Su trazo OSRM
se guarda (§12.2). Se procesan los municipios con lugares suficientes (`apto_por_lugares`). Escribe dw.dim_circuito y dw.fact_circuito_parada y los parámetros en
dim_version_calculo 'circuitos_v1'.

Uso: python model/circuitos.py [--sin-trazo]
"""
import json
import sys
import time
import urllib.request

import pandas as pd

import base
import reglas_circuitos as rc

VERSION = "circuitos_v1"
OSRM = {"a_pie": "https://routing.openstreetmap.de/routed-foot/route/v1/driving/",
        "auto": "https://routing.openstreetmap.de/routed-car/route/v1/driving/"}


def trazo(puntos: list, modalidad: str):
    coords = ";".join(f"{lon},{lat}" for lat, lon in puntos)
    for intento in range(3):
        try:
            req = urllib.request.Request(f"{OSRM[modalidad]}{coords}?overview=simplified&geometries=geojson",
                                         headers={"User-Agent": "MOPEDETU/1.0 (proyecto academico UTP)"})
            with urllib.request.urlopen(req, timeout=60) as r:
                res = json.load(r)
            if res.get("code") == "Ok":
                rt = res["routes"][0]
                return rt["geometry"], rt["distance"] / 1000, rt["duration"] / 60
        except Exception as e:  # noqa: BLE001 - servidor público
            print(f"    OSRM intento {intento + 1}: {e}")
            time.sleep(3 * (intento + 1))
    return None


def aptitud_por_lugares(lug: pd.DataFrame, mun: pd.DataFrame) -> pd.DataFrame:
    """Conteos de puntos por municipio y aptitud por lugares (especificación en sql/25_aptitud_circuito.sql)."""
    ae = lug.tipo_parada.isin(["atractivo", "experiencia"])
    ubic = lug.lat.notna()
    g = lambda m: lug[m].groupby("municipio_sk").size()  # noqa: E731
    apt = pd.DataFrame({
        "atractivos": g(lug.tipo_parada == "atractivo"), "experiencias": g(lug.tipo_parada == "experiencia"),
        "comidas": g(lug.tipo_parada == "comida"), "sin_coordenadas": g(ae & ~ubic),
        "actividades": lug[ae].groupby("municipio_sk").actividad.nunique(),
        "puntos_ubicados": g(ae & ubic), "atractivos_ubicados": g((lug.tipo_parada == "atractivo") & ubic),
    }).reindex(mun.index).fillna(0).astype(int)
    apt = apt.join(mun[["cve_geo", "nombre", "region"]])
    apt["apto_por_lugares"] = (apt.puntos_ubicados >= 3) & (apt.atractivos_ubicados >= 1)
    return apt


def escribir_aptitud(apt: pd.DataFrame, circuitos: list):
    """dw.fact_aptitud_circuito: apto = aptitud por lugares y un circuito estándar que cumple; motivo si no."""
    sb = base.sb
    idx = sb.leer("v_indice_municipio", "dw", "municipio_sk,indice_oportunidad", secreta=True)
    apt = apt.join(idx.set_index("municipio_sk").indice_oportunidad.astype(float))
    est = sb.leer("dim_circuito", "dw", "circuito_sk,municipio_sk,cumple,incumplimientos", secreta=True,
                  filtro="es_estandar=eq.true").set_index("municipio_sk")
    apt = apt.join(est)

    def motivo(r):
        if r.atractivos + r.experiencias == 0:
            return "sin lugares registrados"
        if r.puntos_ubicados < 3:
            return f"solo {r.puntos_ubicados} lugar(es) ubicado(s)"
        if r.atractivos_ubicados < 1:
            return "sin ningún atractivo ubicado (solo experiencias)"
        if pd.isna(r.circuito_sk):
            return "circuito pendiente de calcular (model/circuitos.py)"
        if not r.cumple:
            return "con sus lugares no se arma un circuito que cumpla las reglas (" + ", ".join(r.incumplimientos or []) + ")"
        return None
    apt["apto"] = apt.apto_por_lugares & apt.cumple.fillna(False).astype(bool)
    apt["motivo_no_apto"] = apt.apply(motivo, axis=1)
    pr = lambda s: (s.rank(method="min") - 1) / (len(s) - 1)  # noqa: E731  (percent_rank de PostgreSQL)
    apt["potencial_circuito"] = (0.5 * pr(apt.atractivos + apt.experiencias) + 0.3 * pr(apt.actividades)
                                 + 0.2 * apt.indice_oportunidad.fillna(0)).round(4)
    cols = ["cve_geo", "nombre", "region", "atractivos", "experiencias", "comidas", "sin_coordenadas", "actividades",
            "puntos_ubicados", "atractivos_ubicados", "indice_oportunidad", "apto_por_lugares", "apto",
            "motivo_no_apto", "circuito_sk", "potencial_circuito"]
    filas = [{**{k: base.limpio(v) for k, v in r.items()}, "municipio_sk": int(mk)}
             for mk, r in apt[cols].rename(columns={"circuito_sk": "circuito_estandar_sk"}).iterrows()]
    for f in filas:
        if f["circuito_estandar_sk"] is not None:
            f["circuito_estandar_sk"] = int(f["circuito_estandar_sk"])
        for k in ("atractivos", "experiencias", "comidas", "sin_coordenadas", "actividades", "puntos_ubicados",
                  "atractivos_ubicados"):
            f[k] = int(f[k])
        f["apto_por_lugares"], f["apto"] = bool(f["apto_por_lugares"]), bool(f["apto"])
    sb._peticion("fact_aptitud_circuito?municipio_sk=not.is.null", True, "dw", "DELETE")
    sb.insertar("fact_aptitud_circuito", filas, "dw")
    print(f"✓ fact_aptitud_circuito: {int(apt.apto.sum())} aptos · {int((apt.apto_por_lugares & ~apt.apto).sum())} "
          f"con lugares pero sin circuito que cumpla · {int((~apt.apto_por_lugares).sum())} sin lugares suficientes")


def main():
    sb = base.sb
    vsk = base.asegurar_version(VERSION, "Parámetros de circuitos municipales (model/reglas_circuitos.py)", rc.PARAMETROS)
    lug = sb.leer("fact_lugar_circuito", "dw", secreta=True)
    mun = sb.leer("dim_municipio", "dw", "municipio_sk,cve_geo,nombre,region,cabecera_lat,cabecera_lon",
                  secreta=True).set_index("municipio_sk")
    apt = aptitud_por_lugares(lug, mun)
    aptos = apt[apt.apto_por_lugares].reset_index()
    act = sb.leer("fact_actividad_municipio", "dw", "municipio_sk,actividad_sk,es_principal", secreta=True)
    cat = sb.leer("dim_actividad", "dw", "actividad_sk,codigo,nombre", secreta=True)
    act = act[act.es_principal.astype(bool)].merge(cat)
    principales = act.groupby("municipio_sk").codigo.apply(set).to_dict()
    nom_act = dict(zip(cat.codigo, cat.nombre))

    circuitos = []
    for r in aptos.itertuples():
        l = lug[lug.municipio_sk == r.municipio_sk]
        cab = (float(mun.cabecera_lat[r.municipio_sk]), float(mun.cabecera_lon[r.municipio_sk]))
        orden = [("a_pie", 4), ("auto", 4), ("a_pie", 8), ("auto", 8)]
        variados = {k: rc.armar_circuito(l, cab, *k) for k in orden}
        estandar = next((k for k in orden if variados[k]["cumple"]), ("auto", 4))
        for k, c in variados.items():
            circuitos.append((r.municipio_sk, r.nombre, c, k == estandar))
        ubicados = l[l.lat.notna() & l.tipo_parada.isin(["atractivo", "experiencia"])]
        for a in sorted(principales.get(r.municipio_sk, set())):
            de_a = ubicados[ubicados.actividad == a]
            if len(de_a) >= 3 and (de_a.tipo_parada == "atractivo").any():
                circuitos.append((r.municipio_sk, r.nombre,
                                  rc.armar_circuito(l, cab, "auto", 4, "tematico", a, principales[r.municipio_sk]),
                                  False))
    ok = sum(c["cumple"] for _, _, c, _ in circuitos)
    print(f"Circuitos: {len(circuitos)} en {len(aptos)} municipios aptos · cumplen {ok} · "
          f"estándar {sum(e for *_, e in circuitos)}")

    sb._peticion("dim_circuito?circuito_sk=not.is.null", True, "dw", "DELETE")   # cascada a las paradas
    for i in range(0, len(circuitos), 200):
        lote = circuitos[i:i + 200]
        filas = [dict(municipio_sk=int(mk), modalidad=c["modalidad"], duracion_h=c["duracion_h"], tipo=c["tipo"],
                      actividad=c["actividad"], num_paradas=len(c["paradas"]), minutos_traslado=c["minutos_traslado"],
                      duracion_min=c["duracion_min"], es_estandar=bool(est), cumple=bool(c["cumple"]),
                      incumplimientos=c["incumplimientos"], version_sk=vsk,
                      descripcion=(f"Circuito {'temático de ' + nom_act.get(c['actividad'], c['actividad']).lower() if c['tipo'] == 'tematico' else 'variado'}"
                                   f" de {c['duracion_h']:g} h {'a pie' if c['modalidad'] == 'a_pie' else 'en auto'} "
                                   f"desde la cabecera de {nombre}"))
                 for mk, nombre, c, est in lote]
        creados = sb._peticion("dim_circuito", True, "dw", "POST", filas, {"Prefer": "return=representation"})
        paradas = [dict(circuito_sk=d["circuito_sk"], **{k: v for k, v in pa.items() if k != "url"})
                   for d, (_, _, c, _) in zip(creados, lote) for pa in c["paradas"]]
        for j in range(0, len(paradas), 1000):
            sb._peticion("fact_circuito_parada", True, "dw", "POST", paradas[j:j + 1000], {"Prefer": "return=minimal"})
    print(f"✓ dim_circuito / fact_circuito_parada: {len(circuitos)} circuitos")

    escribir_aptitud(apt, circuitos)
    if "--sin-trazo" in sys.argv:
        return
    est = sb.leer("dim_circuito", "dw", "circuito_sk,municipio_sk,modalidad", secreta=True, filtro="es_estandar=eq.true")
    par = sb.leer("fact_circuito_parada", "dw", "circuito_sk,orden,lat,lon", secreta=True)
    sin = 0
    for c in est.itertuples():
        g = par[par.circuito_sk == c.circuito_sk].sort_values("orden")
        cab = (float(mun.cabecera_lat[c.municipio_sk]), float(mun.cabecera_lon[c.municipio_sk]))
        puntos = [cab] + [(float(a), float(o)) for a, o in zip(g.lat, g.lon)] + [cab]
        t = trazo(puntos, c.modalidad)
        if t is None:
            sin += 1
            continue
        geom, km_, min_ = t
        sb._peticion(f"dim_circuito?circuito_sk=eq.{c.circuito_sk}", True, "dw", "PATCH",
                     dict(geom_trazo=geom, km_trazo=round(km_, 2), min_trazo=round(min_, 1)), {"Prefer": "return=minimal"})
        time.sleep(0.5)
    print(f"✓ trazos guardados de {len(est) - sin} circuitos estándar" + (f" · {sin} sin trazo" if sin else ""))


if __name__ == "__main__":
    main()
