"""Fuente de datos del tablero.

Por ahora genera datos DEMO (sintéticos pero coherentes) sobre los 217 municipios
reales de Puebla. Cuando exista el backend, `cargar_datos()` leerá de Supabase y
el resto del tablero no cambia: las tablas tienen la forma del modelo dimensional.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

RAIZ = Path(__file__).resolve().parents[1]
GEO_PATH = RAIZ / "data" / "geo" / "puebla_municipios.geojson"
FUENTE = "demo"  # "demo" | "supabase" (pendiente)
SEMILLA = 2026

REGIONES = [
    "Sierra Norte",
    "Sierra Nororiental",
    "Valle de Serdán",
    "Angelópolis",
    "Valle de Atlixco y Matamoros",
    "Mixteca",
    "Tehuacán y Sierra Negra",
]

PUEBLOS_MAGICOS = {
    "Atlixco", "Chignahuapan", "Cuetzalan del Progreso", "Huauchinango", "Pahuatlán",
    "Tetela de Ocampo", "Tlatlauquitepec", "Xicotepec", "Zacatlán",
    "San Pedro Cholula", "San Andrés Cholula",
}

# Destinos consolidados: anclas que atraen el flujo hacia municipios emergentes
ANCLAS = {
    "Puebla", "San Pedro Cholula", "San Andrés Cholula", "Atlixco",
    "Cuetzalan del Progreso", "Zacatlán", "Chignahuapan", "Tehuacán", "Xicotepec",
}

# clave, nombre, categoría, ícono, color RGB, nombre de ruta, afinidad regional, municipios destacados
_ACTIVIDADES = [
    ("cafe", "Café de altura", "Gastronómica", "☕", (121, 85, 61), "Ruta del Café",
     {"Sierra Norte": .8, "Sierra Nororiental": .9},
     ["Cuetzalan del Progreso", "Xicotepec", "Hueytamalco", "Zihuateutla", "Tlatlauquitepec", "Jonotla", "Huehuetla"]),
    ("mezcal", "Mezcal", "Gastronómica", "🥃", (196, 140, 32), "Ruta del Mezcal",
     {"Mixteca": .8, "Tehuacán y Sierra Negra": .45, "Valle de Atlixco y Matamoros": .3},
     ["Caltepec", "Zapotitlán", "Tehuitzingo", "Chiautla", "Petlalcingo", "Acatlán", "Ixcaquixtla"]),
    ("arqueologia", "Zonas arqueológicas", "Cultural", "🏛️", (138, 21, 56), "Ruta Arqueológica",
     {"Angelópolis": .2, "Mixteca": .2, "Valle de Serdán": .15},
     ["San Pedro Cholula", "San Andrés Cholula", "Tepeyahualco", "Cuetzalan del Progreso", "Tepexi de Rodríguez", "Tehuacán"]),
    ("conventos", "Conventos y arte sacro", "Religiosa", "⛪", (94, 53, 177), "Ruta de los Conventos",
     {"Angelópolis": .5, "Valle de Atlixco y Matamoros": .5, "Valle de Serdán": .3},
     ["Huejotzingo", "Calpan", "Tochimilco", "San Pedro Cholula", "Tecali de Herrera", "Tepeaca", "Cuautinchán", "Tecamachalco", "Huaquechula"]),
    ("sidra", "Sidra y manzana", "Gastronómica", "🍎", (198, 40, 40), "Ruta de la Sidra",
     {"Sierra Norte": .6, "Angelópolis": .2},
     ["Zacatlán", "Chignahuapan", "Huejotzingo", "Aquixtla", "Tetela de Ocampo"]),
    ("ecoturismo", "Ecoturismo y cascadas", "Naturaleza", "🌿", (46, 125, 50), "Ruta Verde",
     {"Sierra Norte": .8, "Sierra Nororiental": .9, "Tehuacán y Sierra Negra": .4},
     ["Cuetzalan del Progreso", "Zacatlán", "Tlatlauquitepec", "Pahuatlán", "Xicotepec", "Huauchinango", "Jonotla", "Zapotitlán de Méndez"]),
    ("volcanes", "Montaña y volcanes", "Aventura", "🌋", (84, 110, 122), "Ruta de los Volcanes",
     {"Valle de Serdán": .35, "Angelópolis": .2, "Valle de Atlixco y Matamoros": .25},
     ["San Nicolás de los Ranchos", "Tochimilco", "Chalchicomula de Sesma", "Atzitzintla", "Tlachichuca", "Calpan"]),
    ("talavera", "Talavera y artesanías", "Artesanal", "🏺", (21, 67, 160), "Ruta Artesanal",
     {"Angelópolis": .5, "Sierra Nororiental": .3, "Mixteca": .3},
     ["Puebla", "San Pedro Cholula", "Amozoc", "Acatlán", "Izúcar de Matamoros", "Chignahuapan", "Hueyapan"]),
    ("gastronomia", "Mole y cocina tradicional", "Gastronómica", "🍲", (230, 81, 0), "Ruta del Mole",
     {"Angelópolis": .7, "Valle de Atlixco y Matamoros": .4},
     ["Puebla", "San Pedro Cholula", "Atlixco", "Tehuacán", "Huaquechula", "San Andrés Cholula"]),
    ("termales", "Aguas termales y balnearios", "Naturaleza", "♨️", (0, 131, 143), "Ruta Termal",
     {"Valle de Atlixco y Matamoros": .5, "Tehuacán y Sierra Negra": .3},
     ["Chignahuapan", "Atlixco", "Izúcar de Matamoros", "Tehuacán", "Chietla", "Tepeojuma"]),
    ("desierto", "Desierto y paleontología", "Naturaleza", "🌵", (158, 157, 36), "Ruta del Desierto",
     {"Tehuacán y Sierra Negra": .8, "Mixteca": .5},
     ["Zapotitlán", "Caltepec", "San José Miahuatlán", "Coxcatlán", "Tepexi de Rodríguez", "Atexcal"]),
    ("flores", "Flores y viveros", "Rural", "🌸", (216, 27, 96), "Ruta de las Flores",
     {"Valle de Atlixco y Matamoros": .7, "Angelópolis": .2},
     ["Atlixco", "Huaquechula", "Tianguismanalco", "Santa Isabel Cholula"]),
    ("religioso", "Fiestas y turismo religioso", "Religiosa", "🕯️", (255, 143, 0), "Ruta de la Fe",
     {"Angelópolis": .3, "Sierra Norte": .3, "Sierra Nororiental": .3},
     ["San Pedro Cholula", "Chignahuapan", "Huaquechula", "Cuetzalan del Progreso", "Pahuatlán", "Zacatlán", "Puebla"]),
    ("comunitario", "Turismo rural comunitario", "Rural", "🏡", (0, 105, 92), "Ruta Comunitaria",
     {"Sierra Nororiental": .7, "Sierra Norte": .7, "Tehuacán y Sierra Negra": .6, "Mixteca": .4},
     ["Huehuetla", "Cuetzalan del Progreso", "Zoquitlán", "Coyomeapan", "Pahuatlán", "Naupan"]),
]

CORTOS = {
    "cafe": "Café", "mezcal": "Mezcal", "arqueologia": "Arqueología", "conventos": "Conventos",
    "sidra": "Sidra", "ecoturismo": "Ecoturismo", "volcanes": "Volcanes", "talavera": "Artesanías",
    "gastronomia": "Gastronomía", "termales": "Termales", "desierto": "Desierto", "flores": "Flores",
    "religioso": "Fiestas", "comunitario": "Comunitario",
}

# Tipos de lugar genéricos para los puntos de interés de los circuitos
TIPOS_POI = {
    "cafe": ["Finca cafetalera", "Beneficio de café", "Cafetería de origen", "Tostador artesanal"],
    "mezcal": ["Palenque", "Destilería artesanal", "Campo de maguey", "Mezcalería"],
    "arqueologia": ["Zona arqueológica", "Museo de sitio", "Mirador prehispánico"],
    "conventos": ["Exconvento", "Parroquia", "Capilla posa", "Museo de arte sacro"],
    "sidra": ["Sidrería", "Huerto de manzana", "Tienda de frutales"],
    "ecoturismo": ["Cascada", "Sendero", "Mirador", "Río y pozas", "Grutas"],
    "volcanes": ["Albergue de montaña", "Ruta de ascenso", "Mirador volcánico"],
    "talavera": ["Taller de talavera", "Taller artesanal", "Mercado de artesanías"],
    "gastronomia": ["Cocina tradicional", "Mercado gastronómico", "Fonda de mole"],
    "termales": ["Balneario", "Aguas termales", "Spa natural"],
    "desierto": ["Jardín botánico", "Salinas", "Sitio paleontológico", "Bosque de cactáceas"],
    "flores": ["Vivero", "Campo de flores", "Mercado de plantas"],
    "religioso": ["Santuario", "Templo", "Plaza de fiestas"],
    "comunitario": ["Cooperativa turística", "Hospedaje comunitario", "Taller comunitario"],
}

POBLACION_CONOCIDA = {
    "Puebla": 1_692_181, "Tehuacán": 327_312, "San Martín Texmelucan": 155_738,
    "San Andrés Cholula": 154_448, "Atlixco": 141_793, "San Pedro Cholula": 138_433,
    "Amozoc": 125_513, "Cuautlancingo": 137_302, "Huauchinango": 103_946,
    "Teziutlán": 103_583, "Tepeaca": 85_000, "Izúcar de Matamoros": 82_000,
    "Zacatlán": 87_361, "Xicotepec": 81_000, "Chignahuapan": 66_000,
    "Cuetzalan del Progreso": 49_000,
}


@dataclass
class Datos:
    geo: dict
    municipios: pd.DataFrame       # dim_municipio + contexto social + infraestructura
    actividades: pd.DataFrame      # dim_actividad
    mun_act: pd.DataFrame          # especialización + visibilidad + inversión por municipio × actividad
    poi: pd.DataFrame              # puntos de interés (simulan establecimientos DENUE)
    tiempos: np.ndarray            # matriz de tiempos (min) entre municipios, mismo orden que `municipios`
    fuente: str = FUENTE


def region_aprox(lat: float, lon: float) -> str:
    """Regionalización aproximada por coordenadas (demo)."""
    if lat >= 19.72:
        return "Sierra Norte" if lon < -97.62 else "Sierra Nororiental"
    if lon >= -97.75 and lat >= 18.85:
        return "Valle de Serdán"
    if lon >= -97.65:
        return "Tehuacán y Sierra Negra"
    if lat >= 18.85 and lon >= -98.62 and not (lat < 19.0 and lon < -98.30):
        return "Angelópolis"
    if lat >= 18.45 and lon < -98.20:
        return "Valle de Atlixco y Matamoros"
    return "Mixteca"


def haversine_km(lat1, lon1, lat2, lon2):
    r = 6371.0
    p1, p2 = np.radians(lat1), np.radians(lat2)
    dp, dl = p2 - p1, np.radians(lon2 - lon1)
    a = np.sin(dp / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(dl / 2) ** 2
    return 2 * r * np.arcsin(np.sqrt(a))


def _cargar_geo() -> dict:
    with open(GEO_PATH, encoding="utf-8") as fh:
        return json.load(fh)


def cargar_datos() -> Datos:
    if FUENTE != "demo":
        raise NotImplementedError("La conexión a Supabase aún no está implementada.")
    return generar_demo(_cargar_geo())


def generar_demo(geo: dict) -> Datos:
    rng = np.random.default_rng(SEMILLA)

    # --- dim_municipio + contexto ---------------------------------------------
    mun = pd.DataFrame([f["properties"] for f in geo["features"]])
    mun["region"] = [region_aprox(a, o) for a, o in zip(mun.lat, mun.lon)]
    mun["es_pueblo_magico"] = mun.nombre.isin(PUEBLOS_MAGICOS)
    mun["es_ancla"] = mun.nombre.isin(ANCLAS)

    pob = np.exp(rng.normal(np.log(16_000), 0.75, len(mun))).clip(2_000, 90_000)
    mun["poblacion"] = [int(POBLACION_CONOCIDA.get(n, p)) for n, p in zip(mun.nombre, pob)]
    mun["po_total"] = (mun.poblacion * rng.uniform(0.18, 0.32, len(mun))).round()

    base_marg = {
        "Sierra Norte": 0.65, "Sierra Nororiental": 0.70, "Tehuacán y Sierra Negra": 0.62,
        "Mixteca": 0.55, "Valle de Serdán": 0.45, "Valle de Atlixco y Matamoros": 0.42,
        "Angelópolis": 0.28,
    }
    urb = np.log10(mun.poblacion) - 4
    marg = mun.region.map(base_marg) - 0.12 * urb + rng.normal(0, 0.08, len(mun))
    mun["indice_marginacion"] = marg.clip(0.02, 0.98).round(3)
    mun["grado_marginacion"] = pd.cut(
        mun.indice_marginacion, [0, .2, .4, .6, .8, 1],
        labels=["Muy bajo", "Bajo", "Medio", "Alto", "Muy alto"]).astype(str)

    sierra = mun.region.isin(["Sierra Norte", "Sierra Nororiental", "Tehuacán y Sierra Negra"])
    mun["pct_via_pavimentada"] = (
        0.85 - 0.25 * sierra - 0.2 * mun.indice_marginacion + rng.normal(0, 0.07, len(mun))
    ).clip(0.15, 0.99).round(2)
    mun["visitantes_anuales"] = 0  # se completa abajo

    # --- matriz de tiempos (min) ----------------------------------------------
    lat, lon = mun.lat.to_numpy(), mun.lon.to_numpy()
    dist = haversine_km(lat[:, None], lon[:, None], lat[None, :], lon[None, :])
    vel = np.where(sierra.to_numpy()[:, None] | sierra.to_numpy()[None, :], 42.0, 58.0)
    tiempos = dist * 1.35 / vel * 60.0
    idx_anclas = np.flatnonzero(mun.es_ancla.to_numpy())
    mun["min_a_ancla"] = tiempos[:, idx_anclas].min(axis=1).round(0)
    mun["min_a_capital"] = tiempos[:, mun.index[mun.nombre == "Puebla"][0]].round(0)

    # --- dim_actividad ---------------------------------------------------------
    act = pd.DataFrame(
        [dict(clave=a[0], nombre=a[1], corto=CORTOS[a[0]], categoria=a[2], icono=a[3], color=list(a[4]), ruta=a[5])
         for a in _ACTIVIDADES]
    )

    # --- municipio × actividad (DENUE simulado) ---------------------------------
    filas = []
    for clave, _, _, _, _, _, afin, destacados in _ACTIVIDADES:
        intensidad = (
            mun.region.map(afin).fillna(0.05).to_numpy()
            + 1.3 * mun.nombre.isin(destacados).to_numpy()
            + rng.normal(0, 0.22, len(mun))
        )
        presente = intensidad > 0.35
        share = 0.006 * np.exp(1.6 * intensidad) * rng.uniform(0.6, 1.4, len(mun))
        po = np.where(presente, mun.po_total.to_numpy() * share, 0).round()
        po = np.where(presente, np.maximum(po, rng.integers(3, 12, len(mun))), 0)
        for i in range(len(mun)):
            if po[i] > 0:
                filas.append((mun.cve_geo.iat[i], clave, po[i], destacados and mun.nombre.iat[i] in destacados))
    ma = pd.DataFrame(filas, columns=["cve_geo", "actividad", "personal_ocupado", "destacado"])
    ma["unidades"] = np.maximum(1, (ma.personal_ocupado / rng.uniform(2.5, 5.5, len(ma))).round()).astype(int)

    # Cociente de localización
    po_mun = ma.groupby("cve_geo").personal_ocupado.transform("sum") + mun.set_index("cve_geo").po_total.reindex(ma.cve_geo).to_numpy() * 0.25
    po_act = ma.groupby("actividad").personal_ocupado.transform("sum")
    total = ma.personal_ocupado.sum() + mun.po_total.sum() * 0.25
    ma["cociente_localizacion"] = ((ma.personal_ocupado / po_mun) / (po_act / total)).round(2)
    ma["nivel_predominancia"] = pd.cut(
        ma.cociente_localizacion, [-1, 1, 1.5, np.inf], labels=["Baja", "Media", "Alta"]).astype(str)

    # Visibilidad: menciones en boletines, prensa y reseñas (sesgada a destinos conocidos)
    m = mun.set_index("cve_geo")
    fama = (
        2.2 * m.es_ancla.reindex(ma.cve_geo).to_numpy()
        + 1.2 * m.es_pueblo_magico.reindex(ma.cve_geo).to_numpy()
        + 0.35 * np.log10(m.poblacion.reindex(ma.cve_geo).to_numpy())
    )
    ma["menciones"] = np.round(np.exp(fama + 0.25 * np.log1p(ma.personal_ocupado) + rng.normal(0, 0.5, len(ma)))).astype(int)
    ma["resenas"] = np.round(ma.menciones * rng.uniform(2, 9, len(ma))).astype(int)
    ma["menciones_10k"] = (ma.menciones / m.poblacion.reindex(ma.cve_geo).to_numpy() * 1e4).round(2)

    # Inversión pública reciente (2024-2025, millones MXN), concentrada en destinos conocidos
    p_inv = 0.12 + 0.55 * m.es_ancla.reindex(ma.cve_geo).to_numpy() + 0.25 * m.es_pueblo_magico.reindex(ma.cve_geo).to_numpy()
    recibe = rng.random(len(ma)) < p_inv
    ma["inversion_reciente_mdp"] = np.where(recibe, np.exp(rng.normal(1.2, 1.0, len(ma))) * (1 + 2 * fama / 4), 0).round(1)

    # Crecimiento histórico (dos cortes DENUE simulados)
    ma["crecimiento_hist"] = (0.02 + rng.normal(0, 0.03, len(ma)) + 0.01 * (ma.inversion_reciente_mdp > 0)).round(3)

    vis = ma.groupby("cve_geo").resenas.sum()
    mun["visitantes_anuales"] = (mun.cve_geo.map(vis).fillna(0) * 38 + mun.poblacion * 0.05).round()

    # --- puntos de interés (simulan establecimientos geolocalizados del DENUE) --------
    pois = []
    for r in ma.itertuples():
        mm = m.loc[r.cve_geo]
        n = int(np.clip(r.unidades // 4, 1, 6))
        radio_km = max(2.5, np.sqrt(mm.area_km2 / np.pi) * 0.8)
        tipos = TIPOS_POI[r.actividad]
        for k in range(n):
            ang, d = rng.uniform(0, 2 * np.pi), radio_km * np.sqrt(rng.uniform(0.02, 1))
            pois.append(dict(
                cve_geo=r.cve_geo, actividad=r.actividad,
                nombre=f"{tipos[k % len(tipos)]} {chr(65 + k)}",
                lat=mm.lat + d * np.sin(ang) / 111.0,
                lon=mm.lon + d * np.cos(ang) / (111.0 * np.cos(np.radians(mm.lat))),
                valoracion=round(float(rng.uniform(3.6, 4.9)), 1),
            ))

    return Datos(geo=geo, municipios=mun, actividades=act, mun_act=ma,
                 poi=pd.DataFrame(pois), tiempos=tiempos)
