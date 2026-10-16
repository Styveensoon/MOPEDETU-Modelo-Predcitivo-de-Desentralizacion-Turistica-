"""Prueba de humo del tablero con datos reales (publishable key): cada página carga sin excepciones.

Uso:  python tests/test_tablero.py      (se omite con aviso si no hay .env con SUPABASE_URL y la publishable key)
"""

import ast
import sys
from pathlib import Path

from streamlit.testing.v1 import AppTest

RAIZ = Path(__file__).resolve().parents[1]
DASH = str(RAIZ / "dashboard")
sys.path[:0] = [DASH, str(RAIZ / "model")]

import supabase_cliente  # noqa: E402

PAGINAS = ["presentacion", "panorama", "metodologia", "rutas"]
FICHAS = ["21043", "21027", "21121", "21114", "21170"]   # + un municipio sin oferta (se agrega en la prueba)


def _pagina(dash: str, raiz: str, pagina: str):
    import importlib
    import sys

    sys.path[:0] = [dash, raiz + "/model"]
    import streamlit as st

    import estado
    import tema

    tema.aplicar()
    st.session_state.setdefault("paginas", {})
    estado.barra_lateral()
    importlib.import_module(f"vistas.{pagina}").render()


def _correr(pagina: str, **estado) -> AppTest:
    at = AppTest.from_function(_pagina, args=(DASH, str(RAIZ), pagina), default_timeout=240)
    for k, v in estado.items():
        at.session_state[k] = v
    at.run()
    assert not at.exception, f"{pagina} {estado}: {[e.message for e in at.exception]}"
    return at


def test_paginas():
    for pagina in PAGINAS:
        _correr(pagina)
        print(f"✔ {pagina}")
    for paso in range(5):
        _correr("presentacion", pres_paso=paso)
        print(f"✔ presentacion paso {paso + 1}")


def test_rutas():
    import bd
    rp = bd.rutas.__wrapped__()
    prop = rp[rp.origen == "propuesta_modelo"]
    nombres = prop.drop_duplicates("ruta_sk")
    for r in nombres.itertuples():
        # el selector usa la etiqueta "<icono> <nombre>"; basta con fijar la ruta por su clave
        _correr("rutas", rt_recorrer=int(r.ruta_sk))
        print(f"✔ rutas · recorrer #{r.ruta_sk}")


def test_ficha_tecnica():
    import bd
    import ficha_bd

    df = bd.ficha.__wrapped__()
    sin_oferta = df[df.actividades_principales.map(len) == 0].cve_geo.head(1).tolist()
    for i, cve in enumerate(FICHAS + sin_oferta):
        dim = list(ficha_bd.DIMENSIONES)[i % len(ficha_bd.DIMENSIONES)]
        _correr("ficha_tecnica", ft_cve=cve, ft_dim=dim)
        print(f"✔ ficha_tecnica  {cve} · {dim}")


def test_sin_demo():
    """Nada de lo que carga app.py importa el generador DEMO ni genera datos aleatorios."""
    arbol = ast.parse((RAIZ / "dashboard" / "app.py").read_text(encoding="utf-8"))
    vistas = [a.name for n in ast.walk(arbol) if isinstance(n, ast.ImportFrom) and n.module == "vistas" for a in n.names]
    archivos = [RAIZ / "dashboard" / f"{m}.py" for m in ("app", "estado", "bd", "ficha_bd", "mapas", "navegacion",
                                                         "tema", "supabase_cliente")]
    archivos += [RAIZ / "dashboard" / "vistas" / f"{v}.py" for v in vistas]
    for f in archivos:
        texto = f.read_text(encoding="utf-8")
        for prohibido in ("import datos", "from datos", "import motor", "generar_demo", "np.random", "default_rng"):
            assert prohibido not in texto, f"{f.name} contiene '{prohibido}'"
    print(f"✔ sin DEMO en {len(archivos)} archivos que carga app.py")


def test_sin_red():
    """§12.10: con las variables de Supabase vacías, las páginas abren desde data/snapshot/ y lo avisan."""
    import os
    import subprocess

    # Subproceso: el entorno sin credenciales no contamina las cachés de este proceso
    env ={**os.environ, "SUPABASE_URL": "", "SUPABASE_PUBLISHABLE_KEY": ""}
    r = subprocess.run([sys.executable, __file__, "--sin-red"], env=env, capture_output=True, text=True,
                       encoding="utf-8", timeout=1200)
    assert r.returncode == 0, r.stdout[-2000:] + r.stderr[-2000:]
    print(r.stdout.strip().splitlines()[-1])


def _paginas_sin_red():
    for pagina in PAGINAS + ["ficha_tecnica"]:
        at = _correr(pagina)
        avisos = " ".join(str(w.value) for w in at.sidebar.warning)
        assert "Copia local" in avisos, f"{pagina}: no avisa que usa la copia local ({avisos})"
    print("✔ sin red: las páginas abren desde data/snapshot/ y lo avisan")


if __name__ == "__main__":
    if "--sin-red" in sys.argv:
        _paginas_sin_red()
        sys.exit(0)
    if not supabase_cliente.configurado():
        print("… pruebas del tablero omitidas: falta .env con SUPABASE_URL y SUPABASE_PUBLISHABLE_KEY")
        sys.exit(0)
    test_sin_red()
    test_sin_demo()
    test_paginas()
    test_rutas()
    test_ficha_tecnica()
    print("OK")
