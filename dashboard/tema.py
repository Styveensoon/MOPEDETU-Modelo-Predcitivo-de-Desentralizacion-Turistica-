"""Identidad visual inspirada en la Talavera poblana."""

import streamlit as st

COBALTO = "#1B3F8B"
COBALTO_OSC = "#0E2A5C"
AMARILLO = "#E8B10D"
GUINDA = "#8A1538"
VERDE = "#2E7D32"
CREMA = "#F7F5EF"

# Escala secuencial amarillo Talavera → turquesa → azul cobalto (RGB, sin blancos)
SEQ_TALAVERA = [(252, 222, 112), (150, 208, 160), (62, 175, 190), (40, 112, 176), (24, 40, 120)]
# Escala para crecimiento (amarillo → naranja → guinda)
SEQ_CRECIMIENTO = [(255, 236, 170), (250, 196, 80), (236, 128, 40), (196, 62, 50), (128, 16, 56)]
PLOTLY_SEQ = ["#FCDE70", "#96D0A0", "#3EAFBE", "#2870B0", "#182878"]

REGION_COLORES = {
    "Sierra Norte": "#2E7D32",
    "Sierra Nororiental": "#00897B",
    "Valle de Serdán": "#546E7A",
    "Angelópolis": "#1B3F8B",
    "Valle de Atlixco y Matamoros": "#D81B60",
    "Mixteca": "#E8B10D",
    "Tehuacán y Sierra Negra": "#8A1538",
}

CSS = f"""
<style>
.block-container {{ padding-top: 2.6rem; padding-bottom: 3rem; }}
/* Mapas (Plotly geo): fondo suave y bordes redondeados */
div[data-testid="stPlotlyChart"]:has(.geo) {{
  background: radial-gradient(ellipse at center, #F4F7FB 0%, #E3E9F2 100%);
  border-radius: 16px; overflow: hidden; border: 1px solid rgba(27,63,139,.12);
}}
.mope-leyenda {{ font-size: .8rem; margin: 6px 2px 14px 2px; }}
h4 {{ padding-top: .4rem !important; padding-bottom: .5rem !important; }}

h1, h2, h3 {{ letter-spacing: -0.01em; }}
.mope-hero {{
  background: linear-gradient(120deg, {COBALTO_OSC} 0%, {COBALTO} 60%, #2f5fb3 100%);
  color: white; border-radius: 18px; padding: 18px 24px; margin-bottom: 14px;
  position: relative; overflow: hidden;
}}
.mope-hero::after {{
  content: ""; position: absolute; right: 18px; top: 50%; transform: translateY(-50%) rotate(45deg);
  width: 74px; height: 74px; border: 3px solid rgba(232,177,13,.85); border-radius: 12px;
  box-shadow: 0 0 0 9px rgba(255,255,255,.10), 0 0 0 18px rgba(232,177,13,.18), inset 0 0 0 12px rgba(255,255,255,.12);
}}
.mope-hero h1 {{ color: white; margin: 0; font-size: 1.7rem; }}
.mope-hero p {{ color: #dbe5f7; margin: 4px 0 0 0; font-size: .95rem; }}
.mope-chip {{
  display: inline-block; background: rgba(255,255,255,.15); border: 1px solid rgba(255,255,255,.3);
  border-radius: 999px; padding: 2px 10px; margin: 8px 6px 0 0; font-size: .78rem; color: white;
}}
div[data-testid="stMetric"] {{
  background: var(--secondary-background-color); border-radius: 14px; padding: 12px 16px;
  border-left: 5px solid {COBALTO};
}}
div[data-testid="stMetricValue"] {{ font-size: 1.65rem; }}
.mope-card {{
  border: 1px solid rgba(128,128,128,.25); border-radius: 14px; padding: 12px 16px; margin-bottom: 10px;
  background: var(--secondary-background-color);
}}
.mope-card h4 {{ margin: 0 0 4px 0; }}
.mope-tag {{
  display: inline-block; border-radius: 6px; padding: 1px 8px; font-size: .75rem; margin-right: 4px;
  background: {AMARILLO}; color: #2b2100; font-weight: 600;
}}
.mope-tag.ancla {{ background: {COBALTO}; color: white; }}
.mope-tag.flag {{ background: {GUINDA}; color: white; }}
.mope-demo {{
  font-size: .75rem; color: #7a6a00; background: #fff6d6; border: 1px solid #f0d97a;
  border-radius: 8px; padding: 4px 10px; display: inline-block;
}}
</style>
"""


def aplicar():
    st.markdown(CSS, unsafe_allow_html=True)


def hero(titulo: str, subtitulo: str, chips: list[str] | None = None):
    chips_html = "".join(f'<span class="mope-chip">{c}</span>' for c in (chips or []))
    st.markdown(
        f'<div class="mope-hero"><h1>{titulo}</h1><p>{subtitulo}</p>{chips_html}</div>',
        unsafe_allow_html=True,
    )


def escala(valor: float, paleta=SEQ_TALAVERA, alpha: int = 215) -> list[int]:
    """Interpola un valor en [0, 1] sobre una paleta de colores RGB."""
    v = min(max(float(valor), 0.0), 1.0) * (len(paleta) - 1)
    i = min(int(v), len(paleta) - 2)
    f = v - i
    a, b = paleta[i], paleta[i + 1]
    return [round(a[k] + (b[k] - a[k]) * f) for k in range(3)] + [alpha]


def hex_rgb(h: str) -> list[int]:
    h = h.lstrip("#")
    return [int(h[i:i + 2], 16) for i in (0, 2, 4)]
