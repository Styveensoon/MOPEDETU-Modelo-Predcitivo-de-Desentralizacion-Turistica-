"""Lanzador de MOPEDETU: instala lo necesario (solo la primera vez) y abre el tablero.

Uso:  python iniciar.py      (o doble clic en MOPEDETU.bat en Windows)
"""

import hashlib
import importlib.util
import os
import socket
import subprocess
import sys
import venv
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
REQ = RAIZ / "requirements.txt"
VENV = RAIZ / ".venv"
APP = RAIZ / "dashboard" / "app.py"
PAQUETES = ["streamlit", "pydeck", "plotly", "pandas", "numpy"]


def banner():
    print(r"""
  __  __  ___  ____  _____ ____  _____ _____ _   _
 |  \/  |/ _ \|  _ \| ____|  _ \| ____|_   _| | | |
 | |\/| | | | | |_) |  _| | | | |  _|   | | | | | |
 | |  | | |_| |  __/| |___| |_| | |___  | | | |_| |
 |_|  |_|\___/|_|   |_____|____/|_____| |_|  \___/
   Descentralización turística de Puebla · HACK 2026
""")


def tiene_paquetes() -> bool:
    return all(importlib.util.find_spec(p) is not None for p in PAQUETES)


def python_venv() -> Path:
    return VENV / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def preparar_venv() -> Path:
    py = python_venv()
    if not py.exists():
        print("📦 Primera vez: creando entorno virtual (.venv)…")
        venv.create(VENV, with_pip=True)
    huella = hashlib.sha256(REQ.read_bytes()).hexdigest()
    marca = VENV / ".req_hash"
    if not marca.exists() or marca.read_text() != huella:
        print("⬇️  Instalando dependencias (solo cuando cambian)…")
        subprocess.check_call([str(py), "-m", "pip", "install", "-q", "--upgrade", "pip"])
        subprocess.check_call([str(py), "-m", "pip", "install", "-q", "-r", str(REQ)])
        marca.write_text(huella)
    return py


def puerto_libre(inicio=8501) -> int:
    for p in range(inicio, inicio + 50):
        with socket.socket() as s:
            if s.connect_ex(("127.0.0.1", p)) != 0:
                return p
    return inicio


def main():
    banner()
    if sys.version_info < (3, 10):
        sys.exit("❌ Se necesita Python 3.10 o superior. Descárgalo en https://www.python.org/downloads/")

    py = Path(sys.executable) if tiene_paquetes() else preparar_venv()
    puerto = puerto_libre()
    print(f"🚀 Abriendo el tablero en http://localhost:{puerto}  (Ctrl+C para cerrar)\n")
    try:
        subprocess.call([str(py), "-m", "streamlit", "run", str(APP), "--server.port", str(puerto),
                         "--server.headless", "false", "--browser.gatherUsageStats", "false"], cwd=RAIZ)
    except KeyboardInterrupt:
        pass
    print("\n👋 Tablero cerrado.")


if __name__ == "__main__":
    main()
