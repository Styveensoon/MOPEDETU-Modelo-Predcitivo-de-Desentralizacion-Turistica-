"""Ficha técnica municipal: anillo A2 (infraestructura), A3 (temporadas) y semáforos.

Lee lo que ya está en Supabase (dim_municipio, fact_actividad_municipio, rutas) y estas fuentes locales:
  --denue   CSV del DENUE de Puebla (INEGI, 05/2026)
  --osm     carpeta con vias.json y puntos.json (scripts/descargar_osm.py)
  --iter    CSV del ITER 2020 de Puebla (INEGI, Censo de Población y Vivienda 2020)
  --geo     GeoJSON de municipios a resolución completa (INEGI 2023, el mismo de cargar_municipios.py)

Escribe dw.fact_infraestructura, dw.fact_temporada y dw.fact_semaforo_municipio, más copias en data/derivados/.
Uso:
    python scripts/calcular_ficha.py --denue ... --osm ... --iter ... --geo ... [--sin-bd]
"""
import argparse
import csv
import json
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from shapely.geometry import LineString, Point, shape
from shapely.strtree import STRtree

RAIZ = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(RAIZ / "dashboard"), str(RAIZ / "scripts")]

import supabase_cliente as sb  # noqa: E402

SALIDA = RAIZ / "data" / "derivados"
FECHA_CORTE = "2026-10-14"
MIN_POR_KM_RECTA = 1.8  # mismo factor que dw.fact_accesibilidad (241.1 min / 133.96 km)
VERSION = dict(nombre="ficha_semaforos_v1",
               descripcion="Semáforos de la ficha técnica municipal (docs/modelo_predictivo_anillos.md §3.1)",
               pesos={"infraestructura": {"acceso_ancla": 0.35, "red_vial": 0.25, "hospedaje": 0.20,
                                          "servicios": 0.10, "internet": 0.10},
                      "turismo_actual": {"personal_turistico_por_mil": 0.40, "hospedaje": 0.25,
                                         "rutas_existentes": 0.15, "pueblo_magico_ancla": 0.20},
                      "umbrales": {"turismo_actual": [0.5, 0.85], "infraestructura": [0.35, 0.6]}})
FUENTES_NUEVAS = [
    dict(clave="denue_2026", nombre="DENUE 05/2026 (descarga directa)", institucion="INEGI", tipo="Oficial",
         url="https://www.inegi.org.mx/contenidos/masiva/denue/denue_21_csv.zip", version_corte="05/2026",
         fecha_descarga=FECHA_CORTE, licencia_terminos="Términos de Libre Uso de la Información del INEGI",
         cobertura="410,693 establecimientos de Puebla, 217 municipios",
         calidad_notas="Personal ocupado estimado con el punto medio del estrato.",
         uso_en_modelo="Actividades (A1), hospedaje y servicios (A2), intensidad turística (A3)"),
    dict(clave="iter_2020", nombre="Censo 2020 · Principales resultados por localidad (ITER)", institucion="INEGI",
         tipo="Oficial", url="https://www.inegi.org.mx/contenidos/programas/ccpv/2020/datosabiertos/iter/iter_21_cpv2020_csv.zip",
         version_corte="Censo de Población y Vivienda 2020", fecha_descarga=FECHA_CORTE,
         licencia_terminos="Términos de Libre Uso de la Información del INEGI", cobertura="217 municipios",
         calidad_notas="Índice de carencias propio (proxy de marginación) mientras se carga CONAPO en fact_contexto_social.",
         uso_en_modelo="Población, internet (A2) y necesidad social (A4)"),
    dict(clave="osm_2026", nombre="OpenStreetMap · red vial principal y servicios (Overpass)",
         institucion="Colaboradores de OpenStreetMap", tipo="Abierta colaborativa",
         url="https://overpass-api.de/", version_corte=f"Consulta {FECHA_CORTE}", fecha_descarga=FECHA_CORTE,
         licencia_terminos="ODbL (atribución)", cobertura="Vías motorway-tertiary, servicios y atractivos de Puebla",
         calidad_notas="La cobertura de OSM es desigual en municipios rurales; se usa en percentiles, no en valores absolutos.",
         uso_en_modelo="Densidad vial, terminales y atractivos (A2)"),
    dict(clave="eventos", nombre="Calendario de ferias, festivales y temporadas", institucion="Varias (Sectur Puebla, prensa, agregadores)",
         tipo="Catálogo manual", url="https://www.zonaturistica.com/eventos-en/puebla", version_corte="2026",
         fecha_descarga=FECHA_CORTE, licencia_terminos="Información pública",
         cobertura="Temporadas nacionales, por actividad y 26 eventos municipales",
         calidad_notas="Fechas de agregadores y prensa; verificar con los ayuntamientos. URL por evento en fact_temporada.",
         uso_en_modelo="Temporadas fuertes (A3) y compatibilidad de temporada en rutas (A6)"),
]


def haversine_km(lat1, lon1, lat2, lon2):
    p = math.pi / 180
    a = math.sin((lat2 - lat1) * p / 2) ** 2 + math.cos(lat1 * p) * math.cos(lat2 * p) * math.sin((lon2 - lon1) * p / 2) ** 2
    return 2 * 6371.0 * math.asin(math.sqrt(a))


def pct(s: pd.Series) -> pd.Series:
    return s.rank(pct=True, method="average").fillna(0)


# ---------------------------------------------------------------- lectura de Supabase
def leer_bd():
    mun = sb.leer("dim_municipio", "dw", "municipio_sk,cve_geo,nombre,es_pueblo_magico,es_ancla,superficie_km2",
                  secreta=True)
    mun["cve_geo"] = mun.cve_geo.str.strip()
    act = sb.leer("fact_actividad_municipio", "dw", "municipio_sk,actividad_sk,unidades,cociente_localizacion,"
                  "nivel_predominancia,es_principal,rango_en_municipio", secreta=True)
    cat = sb.leer("dim_actividad", "dw", "actividad_sk,codigo,nombre", secreta=True)
    paradas = sb.leer("fact_ruta_parada", "dw", "ruta_sk,municipio_sk", secreta=True)
    rutas = sb._peticion("dim_ruta?select=ruta_sk&origen=eq.existente", True, "dw")
    paradas = paradas[paradas.ruta_sk.isin({r["ruta_sk"] for r in rutas})]
    social = sb.leer("fact_contexto_social", "dw", "municipio_sk,grado_marginacion,indice_marginacion", secreta=True)
    pred = sb.leer("fact_prediccion_crecimiento", "dw", "municipio_sk,crecimiento_pred_pct,intervalo_inf_pct,"
                   "intervalo_sup_pct,personal_base", secreta=True)
    return mun, act.merge(cat, on="actividad_sk"), paradas, social, pred


# ---------------------------------------------------------------- A2
def infraestructura(mun, geo_path, denue_path, osm_dir, iter_path):
    geo = json.loads(Path(geo_path).read_text(encoding="utf-8"))
    polys = {f["properties"]["CVEGEO"]: shape(f["geometry"]).buffer(0) for f in geo["features"]}
    claves = list(polys)
    arbol = STRtree([polys[c] for c in claves])

    def municipio_de(geom):
        for i in arbol.query(geom, predicate="intersects"):
            if polys[claves[i]].contains(geom.centroid if not isinstance(geom, Point) else geom):
                return claves[i]
        return None

    centro = {c: p.representative_point() for c, p in polys.items()}
    df = mun.set_index("cve_geo")
    out = pd.DataFrame(index=df.index)

    # Accesibilidad: ancla más cercana y capital (tiempo estimado con el factor de fact_accesibilidad).
    anclas = df[df.es_ancla].index
    for c in df.index:
        p = centro[c]
        dist = {a: haversine_km(p.y, p.x, centro[a].y, centro[a].x) for a in anclas if a != c}
        a_min = min(dist, key=dist.get)
        out.loc[c, "min_ancla_cercana"] = 0.0 if c in anclas else round(dist[a_min] * MIN_POR_KM_RECTA, 1)
        out.loc[c, "ancla_cercana_sk"] = df.municipio_sk[c] if c in anclas else df.municipio_sk[a_min]
        out.loc[c, "min_capital"] = round(haversine_km(p.y, p.x, centro["21114"].y, centro["21114"].x)
                                          * MIN_POR_KM_RECTA, 1)
    # Colindancia con margen de ~100 m: los polígonos de INEGI no siempre comparten el borde exacto.
    out["municipios_colindantes"] = [sum(1 for j in arbol.query(polys[c].buffer(0.001), predicate="intersects")
                                         if claves[j] != c) for c in out.index]

    # Red vial OSM: longitud por municipio (cada tramo se asigna por su punto medio).
    vias = json.loads((Path(osm_dir) / "vias.json").read_text(encoding="utf-8"))["elements"]
    km = dict.fromkeys(out.index, 0.0)
    for w in vias:
        pts = [(g["lon"], g["lat"]) for g in w.get("geometry", [])]
        for (x1, y1), (x2, y2) in zip(pts, pts[1:]):
            c = municipio_de(Point((x1 + x2) / 2, (y1 + y2) / 2))
            if c:
                km[c] += haversine_km(y1, x1, y2, x2)
    out["km_vias_principales"] = pd.Series(km).round(1)
    out["km_vias_por_km2"] = (out.km_vias_principales / df.superficie_km2.astype(float)).round(3)

    # Puntos OSM: terminales y atractivos.
    puntos = json.loads((Path(osm_dir) / "puntos.json").read_text(encoding="utf-8"))["elements"]
    cuenta = {"terminales_autobus": {}, "atractivos_osm": {}}
    for e in puntos:
        lat, lon = (e.get("lat"), e.get("lon")) if "lat" in e else (e.get("center", {}).get("lat"), e.get("center", {}).get("lon"))
        if lat is None:
            continue
        t = e.get("tags", {})
        if t.get("amenity") == "bus_station":
            k = "terminales_autobus"
        elif t.get("tourism") in ("attraction", "museum", "viewpoint") or "historic" in t or t.get("leisure") in ("nature_reserve", "water_park"):
            k = "atractivos_osm"
        else:
            continue
        c = municipio_de(Point(lon, lat))
        if c:
            cuenta[k][c] = cuenta[k].get(c, 0) + 1
    for k, v in cuenta.items():
        out[k] = pd.Series(v).reindex(out.index).fillna(0)

    # DENUE: hospedaje, alimentos y servicios al visitante.
    d = pd.read_csv(denue_path, dtype=str, usecols=["codigo_act", "per_ocu", "cve_mun"], encoding="latin-1")
    d["cve_geo"] = "21" + d.cve_mun.str.zfill(3)
    sys.path.insert(0, str(RAIZ / "model"))
    from actividades import PUNTO_MEDIO
    d["personal"] = d.per_ocu.map(PUNTO_MEDIO).fillna(2.5)
    def contar(prefijos, campo="size"):
        s = d[d.codigo_act.str.startswith(prefijos)].groupby("cve_geo")
        return (s.size() if campo == "size" else s.personal.sum()).reindex(out.index).fillna(0)
    out["unidades_hospedaje"] = contar(("721",))
    out["personal_hospedaje"] = contar(("721",), "personal")
    out["unidades_alimentos"] = contar(("7225",))
    out["personal_alimentos"] = contar(("7225",), "personal")
    out["gasolineras"] = contar(("468411",))
    out["bancos"] = contar(("522110",))
    out["farmacias"] = contar(("464111", "464112"))
    out["unidades_salud"] = contar(("6211", "6221", "6222"))

    # ITER 2020: población e internet.
    it = pd.read_csv(iter_path, dtype=str, encoding="utf-8-sig")
    it = it[(it.LOC == "0000") & (it.MUN != "000")].copy()
    it["cve_geo"] = "21" + it.MUN
    it = it.set_index("cve_geo")
    num = lambda col: pd.to_numeric(it[col], errors="coerce")
    out["poblacion_2020"] = num("POBTOT")
    out["pct_viviendas_internet"] = (100 * num("VPH_INTER") / num("VIVPAR_HAB")).round(1)
    out["servicios_por_10k_hab"] = (10000 * (out.gasolineras + out.bancos + out.farmacias + out.unidades_salud)
                                    / out.poblacion_2020).round(2)

    # Índice de carencias (proxy de marginación con las variables del Censo que usa CONAPO).
    p15 = num("P_15YMAS")
    viv = num("VIVPAR_HAB")
    carencias = pd.DataFrame({
        "analfabetismo": num("P15YM_AN") / p15,
        "sin_escolaridad": num("P15YM_SE") / p15,
        "sin_drenaje": num("VPH_NODREN") / viv,
        "sin_electricidad": num("VPH_S_ELEC") / viv,
        "sin_agua_entubada": num("VPH_AGUAFV") / viv,
        "piso_tierra": num("VPH_PISOTI") / viv,
        "sin_refrigerador": 1 - num("VPH_REFRI") / viv,
        "ocupantes_por_cuarto": num("PRO_OCUP_C"),
    })
    out["indice_carencias"] = carencias.apply(pct).mean(axis=1).round(4)
    return out


# ---------------------------------------------------------------- semáforos
def nivel_por_umbral(v, bajo, alto, invertido=False):
    if pd.isna(v):
        return "gris"
    if invertido:
        return "verde" if v >= alto else ("amarillo" if v >= bajo else "rojo")
    return "rojo" if v >= alto else ("amarillo" if v >= bajo else "verde")


def semaforos(mun, infra, act, paradas, social, pred):
    df = mun.set_index("municipio_sk")
    inf = infra.set_index(mun.set_index("cve_geo").loc[infra.index, "municipio_sk"].values)
    filas = []

    # Infraestructura (0-1, más es mejor).
    w = VERSION["pesos"]["infraestructura"]
    i_infra = (w["acceso_ancla"] * pct(-inf.min_ancla_cercana) + w["red_vial"] * pct(inf.km_vias_por_km2)
               + w["hospedaje"] * pct(np.log1p(inf.unidades_hospedaje)) + w["servicios"] * pct(inf.servicios_por_10k_hab)
               + w["internet"] * pct(inf.pct_viviendas_internet))
    b, a = VERSION["pesos"]["umbrales"]["infraestructura"]
    for m, v in i_infra.items():
        n = nivel_por_umbral(v, b, a, invertido=True)
        filas.append(dict(municipio_sk=m, dimension="infraestructura", nivel=n, valor=round(v, 4),
                          percentil=round(pct(i_infra)[m], 4),
                          motivo=f"{inf.min_ancla_cercana[m]:.0f} min al ancla más cercana · "
                                 f"{inf.km_vias_por_km2[m]:.2f} km de vías principales/km² · "
                                 f"{inf.unidades_hospedaje[m]:.0f} hospedajes · {inf.pct_viviendas_internet[m]:.0f} % viviendas con internet"))

    # Turismo actual (intensidad proxy; más = más concentrado).
    w = VERSION["pesos"]["turismo_actual"]
    por_mil = 1000 * (inf.personal_hospedaje + inf.personal_alimentos) / inf.poblacion_2020
    n_rutas = paradas.groupby("municipio_sk").ruta_sk.nunique().reindex(inf.index).fillna(0)
    marca = df.es_ancla.astype(float).reindex(inf.index) * 1.0 + (df.es_pueblo_magico & ~df.es_ancla).astype(float).reindex(inf.index) * 0.5
    intensidad = (w["personal_turistico_por_mil"] * pct(por_mil) + w["hospedaje"] * pct(np.log1p(inf.unidades_hospedaje))
                  + w["rutas_existentes"] * pct(n_rutas) + w["pueblo_magico_ancla"] * marca)
    p_int = pct(intensidad)
    b, a = VERSION["pesos"]["umbrales"]["turismo_actual"]
    for m in inf.index:
        sin_oferta = inf.unidades_hospedaje[m] + inf.unidades_alimentos[m] == 0
        n = "gris" if sin_oferta else ("rojo" if df.es_ancla[m] else nivel_por_umbral(p_int[m], b, a))
        filas.append(dict(municipio_sk=m, dimension="turismo_actual", nivel=n, valor=round(intensidad[m], 4),
                          percentil=round(p_int[m], 4),
                          motivo=("Sin hospedaje ni restaurantes registrados" if sin_oferta else
                                  f"{por_mil[m]:.1f} empleos turísticos por mil hab. · {inf.unidades_hospedaje[m]:.0f} hospedajes · "
                                  f"{n_rutas[m]:.0f} rutas oficiales" + (" · ancla" if df.es_ancla[m] else
                                                                        " · Pueblo Mágico" if df.es_pueblo_magico[m] else ""))))

    # Oferta turística (actividades A1).
    for m, g in act.groupby("municipio_sk"):
        fuertes = g[g.nivel_predominancia.isin(["muy_alta", "alta"])].sort_values("cociente_localizacion", ascending=False)
        presentes = g[~g.nivel_predominancia.isin(["sin_oferta"])]
        principal = g[g.es_principal].sort_values("rango_en_municipio")
        nombres = ", ".join(principal.nombre.head(3)) or "—"
        if len(fuertes):
            n, mot = "verde", f"Especializada en {', '.join(fuertes.nombre.head(3))}"
        elif len(presentes) >= 2:
            n, mot = "amarillo", f"Oferta diversa sin especialización: {nombres}"
        elif len(presentes) == 1:
            n, mot = "rojo", f"Oferta mínima: {nombres}"
        else:
            n, mot = "gris", "Sin oferta turística registrada"
        filas.append(dict(municipio_sk=m, dimension="oferta", nivel=n,
                          valor=round(float(g.cociente_localizacion.max()), 3), percentil=None, motivo=mot))

    # Potencial (modelo de Raúl, fact_prediccion_crecimiento).
    for m in inf.index:
        g = pred[pred.municipio_sk == m] if len(pred) else pred
        if len(g) == 0:
            filas.append(dict(municipio_sk=m, dimension="potencial", nivel="gris", valor=None, percentil=None,
                              motivo="Pendiente: predicción de crecimiento (Rol B)"))
            continue
        # Promedio de los ejes ponderado por su empleo: el máximo lo inflaba un eje con 3 negocios
        peso = g.personal_base.fillna(0).clip(lower=1)
        v = float(np.average(g.crecimiento_pred_pct, weights=peso))
        lo = float(np.average(g.intervalo_inf_pct, weights=peso))
        med = pred.groupby("municipio_sk").apply(
            lambda x: np.average(x.crecimiento_pred_pct, weights=x.personal_base.fillna(0).clip(lower=1))).median()
        n = "verde" if v > med and lo > 0 else ("amarillo" if v > 0 else "rojo")
        filas.append(dict(municipio_sk=m, dimension="potencial", nivel=n, valor=round(float(v), 2), percentil=None,
                          motivo=f"Crecimiento predicho de la oferta turística a 5 años {v:+.1f} % "
                                 f"(límite inferior del intervalo de 80 %: {lo:+.1f} %)"))

    # Necesidad social: CONAPO si ya está en fact_contexto_social; si no, índice de carencias del Censo 2020.
    grado = dict(zip(social.municipio_sk, social.grado_marginacion)) if len(social) else {}
    car = inf.indice_carencias
    q = car.rank(pct=True)
    for m in inf.index:
        if m in grado and grado[m]:
            gm = str(grado[m]).lower()
            n = "rojo" if "alto" in gm else ("amarillo" if "medio" in gm else "verde")
            filas.append(dict(municipio_sk=m, dimension="social", nivel=n, valor=None, percentil=None,
                              motivo=f"Grado de marginación {gm} (CONAPO 2020)"))
        else:
            etiqueta = ["muy baja", "baja", "media", "alta", "muy alta"][min(4, int(q[m] * 5))]
            n = "rojo" if q[m] >= 0.6 else ("amarillo" if q[m] >= 0.4 else "verde")
            filas.append(dict(municipio_sk=m, dimension="social", nivel=n, valor=round(car[m], 4),
                              percentil=round(q[m], 4),
                              motivo=f"Carencias {etiqueta} (proxy Censo 2020: analfabetismo, servicios y vivienda)"))
    return pd.DataFrame(filas), intensidad


# ---------------------------------------------------------------- escritura
def asegurar_fuentes():
    existentes = {r["nombre"]: r["fuente_sk"] for r in sb._peticion("dim_fuente?select=fuente_sk,nombre", True, "dw")}
    sk = {}
    for f in FUENTES_NUEVAS:
        fila = {k: v for k, v in f.items() if k != "clave"}
        if f["nombre"] in existentes:
            sb._peticion(f"dim_fuente?fuente_sk=eq.{existentes[f['nombre']]}", True, "dw", "PATCH", fila,
                         {"Prefer": "return=minimal"})
            sk[f["clave"]] = existentes[f["nombre"]]
        else:
            sk[f["clave"]] = sb._peticion("dim_fuente", True, "dw", "POST", fila,
                                          {"Prefer": "return=representation"})[0]["fuente_sk"]
    return sk


def asegurar_version():
    v = sb._peticion(f"dim_version_calculo?select=version_sk&nombre=eq.{VERSION['nombre']}", True, "dw")
    if v:
        sb._peticion(f"dim_version_calculo?version_sk=eq.{v[0]['version_sk']}", True, "dw", "PATCH",
                     {"descripcion": VERSION["descripcion"], "pesos": VERSION["pesos"]}, {"Prefer": "return=minimal"})
        return v[0]["version_sk"]
    return sb._peticion("dim_version_calculo", True, "dw", "POST", VERSION, {"Prefer": "return=representation"})[0]["version_sk"]


UNIDADES = {"min_ancla_cercana": "min", "ancla_cercana_sk": "municipio_sk", "min_capital": "min",
            "municipios_colindantes": "municipios", "km_vias_principales": "km", "km_vias_por_km2": "km/km²",
            "terminales_autobus": "terminales", "atractivos_osm": "puntos", "unidades_hospedaje": "establecimientos",
            "personal_hospedaje": "personas", "unidades_alimentos": "establecimientos", "personal_alimentos": "personas",
            "gasolineras": "establecimientos", "bancos": "sucursales", "farmacias": "establecimientos",
            "unidades_salud": "establecimientos", "poblacion_2020": "habitantes", "pct_viviendas_internet": "%",
            "servicios_por_10k_hab": "por 10 mil hab.", "indice_carencias": "0-1", "intensidad_turistica": "0-1"}
FUENTE_INDICADOR = {"min_ancla_cercana": "marco", "ancla_cercana_sk": "marco", "min_capital": "marco",
                    "municipios_colindantes": "marco", "km_vias_principales": "osm_2026", "km_vias_por_km2": "osm_2026",
                    "terminales_autobus": "osm_2026", "atractivos_osm": "osm_2026", "poblacion_2020": "iter_2020",
                    "pct_viviendas_internet": "iter_2020", "indice_carencias": "iter_2020",
                    "servicios_por_10k_hab": "denue_2026", "intensidad_turistica": "denue_2026"}


def cargar(mun, infra, temporadas, sem, fuentes, version_sk):
    fuentes = {**fuentes, "marco": 2}
    msk = dict(zip(mun.cve_geo, mun.municipio_sk))
    filas = []
    for c, r in infra.iterrows():
        for ind, v in r.items():
            filas.append(dict(municipio_sk=int(msk[c]), indicador=ind, valor=None if pd.isna(v) else float(v),
                              unidad=UNIDADES.get(ind), fuente_sk=fuentes[FUENTE_INDICADOR.get(ind, "denue_2026")],
                              fecha_corte=FECHA_CORTE))
    sb._peticion("fact_infraestructura?municipio_sk=not.is.null", True, "dw", "DELETE")
    sb.insertar("fact_infraestructura", filas, "dw")
    print(f"✓ fact_infraestructura: {len(filas)} filas ({infra.shape[1]} indicadores × {len(infra)} municipios)")

    acts = {r["codigo"]: r["actividad_sk"] for r in sb._peticion("dim_actividad?select=actividad_sk,codigo", True, "dw")}
    nombre_a_cve = {n: c for c, n in zip(mun.cve_geo, mun.nombre)}
    filas = []
    for t in temporadas:
        filas.append(dict(municipio_sk=int(msk[nombre_a_cve[t["municipio"]]]) if t["municipio"] else None,
                          actividad_sk=acts[t["actividad"]] if t["actividad"] else None, nombre=t["nombre"],
                          tipo=t["tipo"], mes_inicio=int(t["mes_inicio"]), mes_fin=int(t["mes_fin"]),
                          intensidad=int(t["intensidad"]), fuente_sk=fuentes["eventos"], url=t["url"] or None,
                          notas=t["notas"] or None))
    sb._peticion("fact_temporada?temporada_sk=gt.0", True, "dw", "DELETE")
    sb.insertar("fact_temporada", filas, "dw")
    print(f"✓ fact_temporada: {len(filas)} temporadas y eventos")

    sem = sem.assign(version_sk=version_sk)
    sem = sem.astype(object).where(sem.notna(), None)
    sb._peticion(f"fact_semaforo_municipio?version_sk=eq.{version_sk}", True, "dw", "DELETE")
    sb.insertar("fact_semaforo_municipio", [{k: (int(v) if k in ("municipio_sk", "version_sk") else v)
                                              for k, v in r.items()} for r in sem.to_dict("records")], "dw")
    print(f"✓ fact_semaforo_municipio: {len(sem)} semáforos (version_sk {version_sk})")


def main():
    ap = argparse.ArgumentParser()
    for a in ("--denue", "--osm", "--iter", "--geo"):
        ap.add_argument(a, required=True)
    ap.add_argument("--sin-bd", action="store_true")
    args = ap.parse_args()

    mun, act, paradas, social, pred = leer_bd()
    infra = infraestructura(mun, args.geo, args.denue, args.osm, args.iter)
    sem, intensidad = semaforos(mun, infra, act, paradas, social, pred)
    infra["intensidad_turistica"] = intensidad.values.round(4)
    with (RAIZ / "data" / "catalogos" / "temporadas.csv").open(encoding="utf-8") as f:
        temporadas = list(csv.DictReader(f))

    SALIDA.mkdir(parents=True, exist_ok=True)
    infra.to_csv(SALIDA / "infraestructura_municipio.csv")
    sem.merge(mun[["municipio_sk", "cve_geo", "nombre"]]).to_csv(SALIDA / "semaforos_municipio.csv", index=False)
    resumen = sem.pivot(index="municipio_sk", columns="dimension", values="nivel")
    print("Semáforos:", {d: resumen[d].value_counts().to_dict() for d in resumen.columns})

    # V2: sin forzar el color, la intensidad calculada de las anclas debe quedar en la mitad alta (P ≥ 50).
    anclas = mun.set_index("municipio_sk").es_ancla
    p = pct(intensidad)
    bajas = [mun.set_index("municipio_sk").nombre[m] for m in anclas[anclas].index if p[m] < 0.5]
    print(f"V2 anclas con intensidad ≥ P50: {anclas.sum() - len(bajas)}/{anclas.sum()}"
          + (f" (por debajo: {', '.join(bajas)})" if bajas else ""))
    if not args.sin_bd:
        cargar(mun, infra, temporadas, sem, asegurar_fuentes(), asegurar_version())


if __name__ == "__main__":
    main()
