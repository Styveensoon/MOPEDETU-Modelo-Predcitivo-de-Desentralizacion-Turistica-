"""MOPEDETU · Tablero de descentralización turística de Puebla.

Ejecutar:  python iniciar.py   (o doble clic en MOPEDETU.bat)
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import streamlit as st  # noqa: E402

st.set_page_config(page_title="MOPEDETU · Puebla", page_icon="🗺️", layout="wide",
                   initial_sidebar_state="expanded")

import estado  # noqa: E402
import tema  # noqa: E402
from vistas import alertas, circuitos, ficha, oportunidades, panorama, rutas, simulador  # noqa: E402

tema.aplicar()

paginas = {
    "panorama": st.Page(panorama.render, title="Panorama", icon="🏠", url_path="panorama", default=True),
    "mapa": st.Page(oportunidades.render, title="Mapa de oportunidades", icon="🗺️", url_path="mapa"),
    "rutas": st.Page(rutas.render, title="Rutas", icon="🧭", url_path="rutas"),
    "circuitos": st.Page(circuitos.render, title="Circuitos", icon="🔁", url_path="circuitos"),
    "simulador": st.Page(simulador.render, title="Simulador", icon="🔮", url_path="simulador"),
    "ficha": st.Page(ficha.render, title="Ficha municipal", icon="🏘️", url_path="ficha"),
    "alertas": st.Page(alertas.render, title="Alertas", icon="🚩", url_path="alertas"),
}
st.session_state["paginas"] = paginas

nav = st.navigation({
    "Explorar": [paginas["panorama"], paginas["mapa"]],
    "Predecir": [paginas["rutas"], paginas["circuitos"], paginas["simulador"]],
    "Detalle": [paginas["ficha"], paginas["alertas"]],
})
estado.barra_lateral()
nav.run()
