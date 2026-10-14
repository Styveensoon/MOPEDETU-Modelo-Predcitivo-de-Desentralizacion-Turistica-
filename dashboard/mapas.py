"""Constructores de mapas con pydeck (sin token: mapa base de CARTO)."""

from __future__ import annotations

import pandas as pd
import pydeck as pdk
import streamlit as st

import tema

VISTA_PUEBLA = pdk.ViewState(latitude=19.0, longitude=-97.95, zoom=6.9, pitch=0, bearing=0)
TOOLTIP = {
    "html": "{tt}",
    "style": {"backgroundColor": "#0E2A5C", "color": "white", "fontSize": "12px",
              "borderRadius": "8px", "padding": "8px 10px", "maxWidth": "320px"},
}


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
                    capa_id: str = "municipios", cuantiles: bool = False) -> pdk.Layer:
    v = df.set_index("cve_geo")[valor].astype(float)
    if cuantiles:  # color por percentil: máximo contraste entre municipios
        norm = v.rank(pct=True)
    else:
        lo = v.min() if vmin is None else vmin
        hi = v.max() if vmax is None else vmax
        norm = ((v - lo) / (hi - lo if hi > lo else 1)).clip(0, 1)
    p = poligonos(geo).copy()
    p["color"] = p.cve_geo.map(lambda c: tema.escala(norm.get(c, 0), paleta))
    p["tt"] = p.cve_geo.map(tooltip)
    resaltar = resaltar or set()
    p["borde"] = p.cve_geo.map(lambda c: [138, 21, 56, 255] if c in resaltar else [255, 255, 255, 140])
    p["ancho"] = p.cve_geo.map(lambda c: 3 if c in resaltar else 1)
    return pdk.Layer(
        "PolygonLayer", p, id=capa_id, get_polygon="poly", get_fill_color="color",
        get_line_color="borde", get_line_width="ancho", line_width_units="pixels",
        stroked=True, filled=True, pickable=True, auto_highlight=True,
        highlight_color=[232, 177, 13, 200],
    )


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


def capa_texto(df: pd.DataFrame, columna: str, tamano=13) -> pdk.Layer:
    return pdk.Layer(
        "TextLayer", df, get_position=["lon", "lat"], get_text=columna, get_size=tamano,
        get_color=[14, 42, 92], get_alignment_baseline="'bottom'", get_pixel_offset=[0, -10],
        font_weight=700, character_set="auto", outline_width=3, outline_color=[255, 255, 255],
        font_settings={"sdf": True},
    )


def capa_arcos(df: pd.DataFrame) -> pdk.Layer:
    return pdk.Layer(
        "ArcLayer", df, get_source_position=["lon_a", "lat_a"], get_target_position=["lon_b", "lat_b"],
        get_source_color="color_a", get_target_color="color_b", get_width="ancho",
        get_height=0.35, pickable=True, auto_highlight=True,
    )


def capa_trayecto(df: pd.DataFrame, color=(138, 21, 56)) -> pdk.Layer:
    return pdk.Layer(
        "PathLayer", df, get_path="path", get_color=list(color) + [230], width_min_pixels=4,
        get_width=5, rounded=True, pickable=True,
    )


def deck(capas, vista=VISTA_PUEBLA, oscuro=False) -> pdk.Deck:
    return pdk.Deck(
        layers=capas, initial_view_state=vista, tooltip=TOOLTIP, map_provider="carto",
        map_style=pdk.map_styles.CARTO_DARK if oscuro else pdk.map_styles.CARTO_LIGHT,
    )


def leyenda(titulo: str, minimo: str, maximo: str, paleta=tema.SEQ_TALAVERA):
    stops = ", ".join(f"rgb{tuple(c)}" for c in paleta)
    st.markdown(
        f"""<div style="font-size:.8rem;margin-top:-4px">{titulo}
        <div style="height:10px;border-radius:6px;background:linear-gradient(90deg,{stops});margin:3px 0"></div>
        <div style="display:flex;justify-content:space-between;opacity:.75"><span>{minimo}</span><span>{maximo}</span></div></div>""",
        unsafe_allow_html=True,
    )
