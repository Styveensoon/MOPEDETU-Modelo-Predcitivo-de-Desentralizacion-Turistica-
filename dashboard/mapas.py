"""Constructores de mapas con pydeck: solo Puebla dividida por municipios, sin mapa base."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pydeck as pdk
import streamlit as st

import tema

LIMITES_PUEBLA = dict(lat=(17.86, 20.84), lon=(-99.07, -96.72))
# El estilo real del tooltip vive en tema.CSS (.deck-tooltip): Streamlit no aplica "style".
TOOLTIP = {"html": "{tt}"}
# Resaltado al pasar el cursor: aclara el municipio en lugar de taparlo con una sombra oscura.
RESALTADO = [255, 255, 255, 90]

# Juego de caracteres explícito para TextLayer (incluye acentos, ñ y números)
# (pydeck convierte cadenas y listas en expresiones; pdk.types.String las deja literales)
CARACTERES = pdk.types.String(
    " abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789.,:;·-–()/&+%#"
    "áéíóúüñÁÉÍÓÚÜÑ"
)
METROS = pdk.types.String("meters")
PIXELES = pdk.types.String("pixels")

FUENTE = pdk.types.String("Source Sans Pro, Arial, sans-serif")

_CACHE_POLIGONOS: dict[int, pd.DataFrame] = {}


def poligonos(geo: dict) -> pd.DataFrame:
    """Un renglón por polígono (los multipolígonos se separan)."""
    if id(geo) in _CACHE_POLIGONOS:
        return _CACHE_POLIGONOS[id(geo)]
    filas = []
    for f in geo["features"]:
        for poly in f["geometry"]["coordinates"]:
            filas.append({"cve_geo": f["properties"]["cve_geo"], "poly": poly})
    _CACHE_POLIGONOS[id(geo)] = pd.DataFrame(filas)
    return _CACHE_POLIGONOS[id(geo)]


def capa_municipios(geo: dict, df: pd.DataFrame, valor: str, tooltip: pd.Series,
                    paleta=tema.SEQ_TALAVERA, vmin=None, vmax=None, resaltar: set | None = None,
                    capa_id: str = "municipios", cuantiles: bool = False, atenuar: set | None = None) -> pdk.Layer:
    """Coroplético de municipios. `atenuar` = municipios que se pintan en gris (contexto)."""
    v = df.set_index("cve_geo")[valor].astype(float)
    if cuantiles:  # color por percentil: máximo contraste entre municipios
        norm = v.rank(pct=True)
    else:
        lo = v.min() if vmin is None else vmin
        hi = v.max() if vmax is None else vmax
        norm = ((v - lo) / (hi - lo if hi > lo else 1)).clip(0, 1)
    p = poligonos(geo).copy()
    atenuar = atenuar or set()
    p["color"] = p.cve_geo.map(
        lambda c: [214, 220, 230, 255] if c in atenuar or c not in norm.index else tema.escala(norm[c], paleta, 240))
    p["tt"] = p.cve_geo.map(tooltip).fillna("")
    resaltar = resaltar or set()
    p["borde"] = p.cve_geo.map(lambda c: [138, 21, 56, 255] if c in resaltar else [255, 255, 255, 220])
    p["ancho"] = p.cve_geo.map(lambda c: 3 if c in resaltar else 0.8)
    return pdk.Layer(
        "PolygonLayer", p, id=capa_id, get_polygon="poly", get_fill_color="color",
        get_line_color="borde", get_line_width="ancho", line_width_units=PIXELES,
        stroked=True, filled=True, pickable=True, auto_highlight=True,
        highlight_color=RESALTADO,
    )


def capas_nombres(mun: pd.DataFrame, destacados=None, todos: bool = False, fijos: bool = False) -> list[pdk.Layer]:
    """Nombres de municipios.

    - `destacados`: se ven siempre (tamaño fijo en pantalla).
    - `todos`: tamaño en metros, se vuelven legibles al hacer zoom sin saturar la vista estatal.
    - `fijos`: todos los nombres con tamaño fijo en pantalla (vista densa).
    """
    capas = []
    base = mun[["cve_geo", "nombre", "lat", "lon", "area_km2"]].copy()
    if fijos:
        return [capa_texto(base, "nombre", 9, offset=(0, 0))] + (
            capas_nombres(mun, destacados, todos=False) if destacados is not None else [])
    if todos:
        t = base.copy()
        t["tam"] = np.clip(np.sqrt(t.area_km2) * 330, 2200, 6000)
        capas.append(pdk.Layer(
            "TextLayer", t, id="nombres_todos", get_position=["lon", "lat"], get_text="nombre",
            get_size="tam", size_units=METROS, size_max_pixels=15, get_color=[20, 33, 61, 235],
            character_set=CARACTERES, font_family=FUENTE, font_weight=600,
            outline_width=2.5, outline_color=[255, 255, 255, 230], font_settings={"sdf": True},
        ))
    if destacados is not None and len(destacados):
        dd = base[base.cve_geo.isin(destacados)]
        capas.append(pdk.Layer(
            "TextLayer", dd, id="nombres_destacados", get_position=["lon", "lat"], get_text="nombre",
            get_size=12, get_color=[14, 42, 92, 255], character_set=CARACTERES,
            font_family=FUENTE, font_weight=700,
            outline_width=3, outline_color=[255, 255, 255, 255], font_settings={"sdf": True},
        ))
    return capas


def capa_columnas(df: pd.DataFrame, valor: str, escala_altura: float = 40.0) -> pdk.Layer:
    d = df[["lat", "lon", valor, "tt"]].copy()
    d["h"] = d[valor].astype(float)
    return pdk.Layer(
        "ColumnLayer", d, get_position=["lon", "lat"], get_elevation="h",
        elevation_scale=escala_altura, radius=2200, get_fill_color=[232, 177, 13, 220],
        pickable=True, auto_highlight=True, extruded=True,
    )


def capa_puntos(df: pd.DataFrame, color, radio=2500, capa_id=None) -> pdk.Layer:
    return pdk.Layer(
        "ScatterplotLayer", df, id=capa_id, get_position=["lon", "lat"], get_fill_color=color,
        get_radius=radio, radius_min_pixels=4, radius_max_pixels=18, stroked=True,
        get_line_color=[255, 255, 255], line_width_min_pixels=1.5, pickable=True,
    )


def capa_texto(df: pd.DataFrame, columna: str, tamano=13, offset=(0, -14)) -> pdk.Layer:
    return pdk.Layer(
        "TextLayer", df, get_position=["lon", "lat"], get_text=columna, get_size=tamano,
        get_color=[14, 42, 92, 255], get_pixel_offset=list(offset), character_set=CARACTERES,
        font_family=FUENTE, font_weight=700,
        outline_width=3, outline_color=[255, 255, 255, 255], font_settings={"sdf": True},
    )


def capa_arcos(df: pd.DataFrame) -> pdk.Layer:
    return pdk.Layer(
        "ArcLayer", df, get_source_position=["lon_a", "lat_a"], get_target_position=["lon_b", "lat_b"],
        get_source_color="color_a", get_target_color="color_b", get_width="ancho",
        get_height=0.35, pickable=True, auto_highlight=True,
    )


def capa_trayecto(df: pd.DataFrame, color=(138, 21, 56)) -> pdk.Layer:
    return pdk.Layer(
        "PathLayer", df, get_path="path", get_color=list(color) + [235], width_min_pixels=4,
        get_width=5, rounded=True, pickable=True,
    )


def _mercator_y(lat: float) -> float:
    """Latitud → coordenada Web Mercator en 'grados equivalentes' (misma escala que la longitud)."""
    return np.degrees(np.log(np.tan(np.pi / 4 + np.radians(lat) / 2)))


def vista_ajustada(lats, lons, ancho=900, alto=600, margen=1.35, zoom_max=10.5, pitch=0) -> pdk.ViewState:
    """Centra y ajusta el zoom para que todos los puntos quepan en el mapa (Web Mercator, mundo de 512 px)."""
    lat0, lat1, lon0, lon1 = float(min(lats)), float(max(lats)), float(min(lons)), float(max(lons))
    y0, y1 = _mercator_y(lat0), _mercator_y(lat1)
    span_lon = max((lon1 - lon0) * margen, 0.05)
    span_y = max((y1 - y0) * margen, 0.05)
    z = min(np.log2(ancho * 360 / (512 * span_lon)), np.log2(alto * 360 / (512 * span_y)))
    lat_c = float(np.degrees(2 * np.arctan(np.exp(np.radians((y0 + y1) / 2))) - np.pi / 2))
    return pdk.ViewState(latitude=lat_c, longitude=(lon0 + lon1) / 2,
                         zoom=float(np.clip(z, 5.5, zoom_max)), pitch=pitch)


VISTA_PUEBLA = vista_ajustada(LIMITES_PUEBLA["lat"], LIMITES_PUEBLA["lon"], ancho=950, alto=600, margen=1.06)


def deck(capas, vista=VISTA_PUEBLA, oscuro=False) -> pdk.Deck:
    """Sin mapa base: solo las capas de Puebla sobre el fondo del contenedor."""
    return pdk.Deck(layers=capas, initial_view_state=vista, tooltip=TOOLTIP,
                    map_provider=None, map_style=None)


def leyenda(titulo: str, minimo: str, maximo: str, paleta=tema.SEQ_TALAVERA):
    stops = ", ".join(f"rgb{tuple(c)}" for c in paleta)
    st.markdown(
        f"""<div class="mope-leyenda">{titulo}
        <div style="height:10px;border-radius:6px;background:linear-gradient(90deg,{stops});margin:4px 0"></div>
        <div style="display:flex;justify-content:space-between;opacity:.75"><span>{minimo}</span><span>{maximo}</span></div></div>""",
        unsafe_allow_html=True,
    )
