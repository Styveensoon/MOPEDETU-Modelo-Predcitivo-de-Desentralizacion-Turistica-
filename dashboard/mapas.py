"""Mapas de Puebla por municipios con Plotly (hover y clic nativos del navegador).

Antes se usaba pydeck/deck.gl, pero dentro de Streamlit su picking quedaba desfasado del dibujo
(en Windows con escalado de pantalla el resaltado caía en otro municipio). Plotly dibuja SVG y
resuelve el hover sobre el mismo elemento que se ve.

Uso:
    m = mapas.Mapa(geo, alto=600)
    m.municipios(df, "indice_oportunidad", hover, cuantiles=True)
    m.nombres(df[df.es_ancla])
    mapas.mostrar(m, "clave")                       # solo ver
    cve = mapas.mostrar(m, "clave", "estado_sel")   # ver y seleccionar con clic
"""

from __future__ import annotations

import html

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import tema

LIMITES_PUEBLA = dict(lat=(17.86, 20.84), lon=(-99.07, -96.72))
GRIS = "rgb(214,220,230)"
AZUL = "#0E2A5C"
GUINDA = "#8A1538"
HOVER = dict(bgcolor=AZUL, bordercolor=tema.AMARILLO, align="left",
             font=dict(color="white", size=13, family="Source Sans Pro, Segoe UI, Arial"))
CONFIG = {"displayModeBar": False, "scrollZoom": True}
# Alias de etiqueta (None = no se rotula) y posición del texto para anclas vecinas que se enciman.
ETIQUETAS = {"21140": "Cholula", "21119": None}
POSICION = {"21109": "middle left", "21197": "top right", "21140": "middle left", "21114": "bottom right",
            "21208": "middle left", "21053": "bottom left", "21186": "bottom right", "21071": "top center"}


def _rgb(c) -> str:
    return c if isinstance(c, str) else f"rgb({c[0]},{c[1]},{c[2]})"


def _escala(paleta) -> list:
    n = len(paleta) - 1
    return [[i / n, _rgb(c)] for i, c in enumerate(paleta)]


def _texto(s) -> str:
    """Plotly entiende <br>, <b>, <i> y <span style>; normaliza <br/>."""
    return "" if s is None or (isinstance(s, float) and np.isnan(s)) else str(s).replace("<br/>", "<br>")


class Mapa:
    def __init__(self, geo: dict, alto: int = 600):
        self.geo = geo
        self.alto = alto
        self.fig = go.Figure()
        self._rango = None
        self._seleccionable = None  # índice de la traza de municipios que responde al clic

    # ------------------------------------------------------------ capas
    def municipios(self, df: pd.DataFrame, valor: str | None = None, hover=None, paleta=tema.SEQ_TALAVERA,
                   cuantiles: bool = False, vmin=None, vmax=None, atenuar: set | None = None,
                   resaltar: set | None = None, seleccionado: str | None = None, color_fijo=None):
        """Coroplético. `atenuar` = municipios en gris de contexto; `resaltar` = contorno guinda;
        `seleccionado` = contorno azul grueso (municipio elegido con clic)."""
        d = df.drop_duplicates("cve_geo").reset_index(drop=True)
        atenuar, resaltar = atenuar or set(), resaltar or set()
        tt = d.cve_geo.map(hover).map(_texto) if hover is not None else d.get("nombre", d.cve_geo)

        if color_fijo is not None or valor is None:
            z = np.zeros(len(d))
            escala = [[0, _rgb(color_fijo or GRIS)], [1, _rgb(color_fijo or GRIS)]]
        else:
            v = d[valor].astype(float)
            if cuantiles:
                z = v.rank(pct=True).to_numpy()
            else:
                lo = v.min() if vmin is None else vmin
                hi = v.max() if vmax is None else vmax
                z = ((v - lo) / (hi - lo if hi > lo else 1)).clip(0, 1).to_numpy()
            escala = _escala(paleta)
        z = np.where(d.cve_geo.isin(atenuar), np.nan, z)

        borde = [AZUL if c == seleccionado else GUINDA if c in resaltar else "white" for c in d.cve_geo]
        ancho = [3.2 if c == seleccionado else 2.4 if c in resaltar else 0.6 for c in d.cve_geo]
        if atenuar:  # capa gris de fondo para los municipios atenuados (z = NaN no se pinta)
            g = d[d.cve_geo.isin(atenuar)]
            self.fig.add_trace(go.Choropleth(
                geojson=self.geo, featureidkey="properties.cve_geo", locations=g.cve_geo, z=np.zeros(len(g)),
                colorscale=[[0, GRIS], [1, GRIS]], showscale=False, marker=dict(line=dict(color="white", width=0.6)),
                text=tt[g.index], hovertemplate="%{text}<extra></extra>", name="contexto"))
        self._seleccionable = len(self.fig.data)
        self.fig.add_trace(go.Choropleth(
            geojson=self.geo, featureidkey="properties.cve_geo", locations=d.cve_geo, z=z,
            zmin=0, zmax=1, colorscale=escala, showscale=False,
            marker=dict(line=dict(color=borde, width=ancho), opacity=1),
            selected=dict(marker=dict(opacity=1)), unselected=dict(marker=dict(opacity=1)),
            text=tt, hovertemplate="%{text}<extra></extra>", name="municipios"))
        self._cves = d.cve_geo.tolist()
        return self

    def nombres(self, df: pd.DataFrame, columna: str = "nombre", tamano: int = 11, color: str = AZUL,
                posicion=None, separacion: float = 0.11):
        """Etiquetas de municipios. Aplica alias y posiciones de ETIQUETAS/POSICION y, con `separacion`
        (grados), omite las que caerían encima de otra ya colocada (el orden de `df` es la prioridad).
        Las omitidas siguen visibles en el hover."""
        if df.empty:
            return self
        d = df.copy()
        if "cve_geo" in d:
            d[columna] = [ETIQUETAS.get(c, n) if c in ETIQUETAS else n for c, n in zip(d.cve_geo, d[columna])]
            d = d[d[columna].notna()]
        colocadas = getattr(self, "_etiquetas", [])
        filas = []
        for r in d.itertuples():
            fija = getattr(r, "cve_geo", None) in POSICION  # ya tiene posición pensada para no chocar
            if separacion and not fija and any(abs(r.lat - la) < separacion * 0.8 and abs(r.lon - lo) < separacion * 1.6
                                  for la, lo in colocadas):
                continue
            colocadas.append((r.lat, r.lon))
            filas.append(r.Index)
        self._etiquetas = colocadas
        d = d.loc[filas]
        if posicion is None:
            posicion = [POSICION.get(c, "middle center") for c in d.cve_geo] if "cve_geo" in d else "middle center"
        fuente = dict(size=tamano, color=color, family="Arial Black, Source Sans Pro" if tamano >= 11 else "Arial")
        self.fig.add_trace(go.Scattergeo(
            lon=d.lon, lat=d.lat, text=d[columna], mode="text", hoverinfo="skip", textfont=fuente,
            textposition=posicion, selected=dict(textfont=dict(color=color)),
            unselected=dict(textfont=dict(color=color)), showlegend=False))
        return self

    def puntos(self, df: pd.DataFrame, color, tamano=10, hover: str | None = "tt", texto: str | None = None,
               posicion_texto="top center", simbolo="circle", color_texto: str = AZUL, tamano_texto: int = 11):
        colores = df[color].map(_rgb).tolist() if isinstance(color, str) and color in df else _rgb(color)
        self.fig.add_trace(go.Scattergeo(
            lon=df.lon, lat=df.lat, mode="markers+text" if texto else "markers",
            text=df[texto] if texto else None, textposition=posicion_texto,
            textfont=dict(size=tamano_texto, color=color_texto, family="Arial Black"),
            marker=dict(size=df[tamano] if isinstance(tamano, str) else tamano, color=colores, symbol=simbolo,
                        line=dict(color="white", width=1.5), opacity=1),
            selected=dict(marker=dict(opacity=1)), unselected=dict(marker=dict(opacity=1)),
            hovertext=df[hover].map(_texto) if hover and hover in df else None,
            hoverinfo="text" if hover and hover in df else "skip", showlegend=False))
        return self

    def trayecto(self, lons, lats, color=AZUL, ancho: float = 4, hover: str | None = None):
        self.fig.add_trace(go.Scattergeo(
            lon=list(lons), lat=list(lats), mode="lines", line=dict(color=_rgb(color), width=ancho),
            hovertext=_texto(hover) if hover else None, hoverinfo="text" if hover else "skip", showlegend=False))
        return self

    def encuadre(self, lats, lons, margen: float = 0.12, aspecto: float | None = None):
        """Rango visible. `aspecto` = ancho/alto del contenedor: ensancha el rango para que el mapa
        llene el recuadro en lugar de quedar como una franja."""
        lat0, lat1, lon0, lon1 = float(min(lats)), float(max(lats)), float(min(lons)), float(max(lons))
        dlat, dlon = max(lat1 - lat0, 0.02), max(lon1 - lon0, 0.02)
        lat0, lat1, lon0, lon1 = lat0 - dlat * margen, lat1 + dlat * margen, lon0 - dlon * margen, lon1 + dlon * margen
        if aspecto:
            k = 1 / np.cos(np.radians((lat0 + lat1) / 2))  # en Mercator 1° de latitud mide más que 1° de longitud
            alto_merc, ancho = (lat1 - lat0) * k, lon1 - lon0
            if ancho < alto_merc * aspecto:
                extra = (alto_merc * aspecto - ancho) / 2
                lon0, lon1 = lon0 - extra, lon1 + extra
            else:
                extra = (ancho / aspecto - alto_merc) / 2 / k
                lat0, lat1 = lat0 - extra, lat1 + extra
        self._rango = ([lat0, lat1], [lon0, lon1])
        return self

    # ------------------------------------------------------------ salida
    def figura(self) -> go.Figure:
        f = self.fig
        if not self._rango:  # por defecto, todo el estado (fitbounds de Plotly deja demasiado margen)
            self.encuadre(LIMITES_PUEBLA["lat"], LIMITES_PUEBLA["lon"], margen=0.01)
        # projection_scale=1: el rango lat/lon llena el marco (Plotly si no lo aleja a ~0.66)
        f.update_geos(fitbounds=False, lataxis_range=self._rango[0], lonaxis_range=self._rango[1],
                      projection_scale=1, center=dict(lat=sum(self._rango[0]) / 2, lon=sum(self._rango[1]) / 2))
        f.update_geos(visible=False, projection_type="mercator", bgcolor="rgba(0,0,0,0)")
        f.update_layout(height=self.alto, margin=dict(l=0, r=0, t=0, b=0), paper_bgcolor="rgba(0,0,0,0)",
                        showlegend=False, dragmode="pan", hoverlabel=HOVER)
        return f


def mostrar(mapa: Mapa, clave: str, estado_sel: str | None = None) -> str | None:
    """Dibuja el mapa. Con `estado_sel`, un clic sobre un municipio guarda su cve_geo en
    st.session_state[estado_sel] y redibuja.

    La llave del gráfico incluye la selección actual: cada selección crea un mapa nuevo sin estado de
    selección previo en Plotly (si no, los clics alternan entre seleccionar y deseleccionar y Plotly
    atenúa al resto de municipios)."""
    fig = mapa.figura()
    if estado_sel is None:
        st.plotly_chart(fig, key=clave, config=CONFIG)
        return None
    actual = st.session_state.get(estado_sel)
    evento = st.plotly_chart(fig, key=f"{clave}_{actual}", on_select="rerun", selection_mode="points",
                             config=CONFIG)
    puntos = [p for p in (evento.selection.points if evento else [])
              if p.get("curve_number") == mapa._seleccionable]
    if puntos:
        cve = puntos[0].get("location") or mapa._cves[puntos[0]["point_index"]]
        if cve != actual:
            st.session_state[estado_sel] = cve
            st.rerun()
    return actual


def leyenda(titulo: str, minimo: str, maximo: str, paleta=tema.SEQ_TALAVERA):
    stops = ", ".join(f"rgb{tuple(c)}" for c in paleta)
    st.markdown(
        f"""<div class="mope-leyenda">{titulo}
        <div style="height:10px;border-radius:6px;background:linear-gradient(90deg,{stops});margin:4px 0"></div>
        <div style="display:flex;justify-content:space-between;opacity:.75"><span>{minimo}</span><span>{maximo}</span></div></div>""",
        unsafe_allow_html=True,
    )


def escapar(s: str) -> str:
    return html.escape(str(s))
