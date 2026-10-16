"""MOPEDETU · Tablero de descentralización turística de Puebla.

Todo lo que muestra sale de Supabase (esquema dw) o de la copia local de la base (data/snapshot/).
Ejecutar:  python iniciar.py   (o doble clic en MOPEDETU.bat)
"""

import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(Path(__file__).resolve().parent), str(RAIZ / "model"), str(RAIZ)]

import streamlit as st  # noqa: E402

st.set_page_config(page_title="MOPEDETU · Puebla", page_icon="🗺️", layout="wide",
                   initial_sidebar_state="expanded")

import estado  # noqa: E402
import tema  # noqa: E402
from vistas import ficha_tecnica, metodologia, panorama, presentacion, rutas  # noqa: E402

tema.aplicar()

paginas = {
    "presentacion": st.Page(presentacion.render, title="Recorrido de presentación", icon="▶️",
                            url_path="presentacion", default=True),
    "panorama": st.Page(panorama.render, title="Panorama", icon="🏠", url_path="panorama"),
    "ficha_tecnica": st.Page(ficha_tecnica.render, title="Ficha técnica", icon="🏘️", url_path="ficha-tecnica"),
    "metodologia": st.Page(metodologia.render, title="Metodología y fuentes", icon="📚", url_path="metodologia"),
    "rutas": st.Page(rutas.render, title="Rutas", icon="🧭", url_path="rutas"),
}
st.session_state["paginas"] = paginas

# Corte P0 (plan_migracion_front.md §0.1): solo las páginas con datos reales. Mapa de oportunidades, Circuitos,
# Escenarios y Alertas se agregan en P1.
nav = st.navigation({
    "Inicio": [paginas["presentacion"]],
    "Explorar": [paginas["panorama"], paginas["ficha_tecnica"], paginas["metodologia"]],
    "Proponer": [paginas["rutas"]],
})
estado.barra_lateral()
nav.run()
