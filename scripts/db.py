"""Conexión a Postgres (Supabase) para los scripts de carga y ETL.

Lee DATABASE_URL del entorno o del archivo .env en la raíz del repo.
Usar la cadena del Session pooler (puerto 5432); la conexión directa de la capa
gratuita es solo IPv6.
"""
import os
from pathlib import Path

from sqlalchemy import create_engine

RAIZ = Path(__file__).resolve().parent.parent


def _cargar_env(ruta: Path = RAIZ / ".env") -> None:
    if not ruta.exists():
        return
    for linea in ruta.read_text(encoding="utf-8").splitlines():
        linea = linea.strip()
        if linea and not linea.startswith("#") and "=" in linea:
            k, v = linea.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def motor():
    _cargar_env()
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise SystemExit("Falta DATABASE_URL en .env (Supabase -> Connect -> Session pooler).")
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]
    if url.startswith("postgresql://"):
        url = "postgresql+psycopg2://" + url[len("postgresql://"):]
    return create_engine(url, connect_args={"options": "-c search_path=public,extensions"},
                         pool_pre_ping=True)
