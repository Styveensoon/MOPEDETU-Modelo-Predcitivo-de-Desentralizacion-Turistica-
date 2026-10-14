"""Prueba de humo: cada página del tablero se ejecuta sin excepciones en ambos modos.

Uso:  python tests/test_tablero.py
"""

from pathlib import Path

from streamlit.testing.v1 import AppTest

DASH = str(Path(__file__).resolve().parents[1] / "dashboard")
PAGINAS = ["panorama", "oportunidades", "rutas", "circuitos", "simulador", "ficha", "alertas"]
CONFIGS = [
    {},
    {"modo": "Concreto", "escenario": "combinado", "alcance": "Varias"},
    {"modo": "Concreto", "escenario": "inversion_simulada", "alcance": "Una", "region": "Mixteca"},
    {"modo": "Concreto", "escenario": "promocion", "alcance": "Todas", "dias": 1},
]


def _pagina(dash: str, pagina: str):
    import importlib
    import sys

    sys.path.insert(0, dash)
    import streamlit as st

    import estado
    import tema

    tema.aplicar()
    st.session_state.setdefault("paginas", {})
    estado.barra_lateral()
    importlib.import_module(f"vistas.{pagina}").render()


def test_paginas():
    for cfg in CONFIGS:
        for pagina in PAGINAS:
            at = AppTest.from_function(_pagina, args=(DASH, pagina), default_timeout=180)
            for k, v in cfg.items():
                at.session_state[k] = v
            at.run()
            assert not at.exception, f"{pagina} {cfg}: {[e.message for e in at.exception]}"
            print(f"✔ {pagina:<14} {cfg or 'General'}")


if __name__ == "__main__":
    test_paginas()
    print("OK")
