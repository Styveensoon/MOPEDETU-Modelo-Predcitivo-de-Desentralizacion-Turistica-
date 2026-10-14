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


def test_ficha_tecnica():
    """Ficha con datos reales de Supabase: varios perfiles (ancla, emergente, sin oferta) y cada semáforo."""
    import sys

    sys.path.insert(0, DASH)
    import ficha_bd

    df = ficha_bd.cargar.__wrapped__()
    if df is None:
        print("… ficha_tecnica omitida: sin conexión a Supabase (.env)")
        return
    sin_oferta = df[df.actividades_principales.map(len) == 0].cve_geo.head(1).tolist()
    muestras = ["21043", "21027", "21121", "21114", "21170"] + sin_oferta
    for i, cve in enumerate(muestras):
        dim = list(ficha_bd.DIMENSIONES)[i % len(ficha_bd.DIMENSIONES)]
        at = AppTest.from_function(_pagina, args=(DASH, "ficha_tecnica"), default_timeout=180)
        at.session_state["ft_cve"] = cve
        at.session_state["ft_dim"] = dim
        at.run()
        assert not at.exception, f"ficha_tecnica {cve}: {[e.message for e in at.exception]}"
        print(f"✔ ficha_tecnica  {cve} · {dim}")


if __name__ == "__main__":
    test_paginas()
    test_ficha_tecnica()
    print("OK")
