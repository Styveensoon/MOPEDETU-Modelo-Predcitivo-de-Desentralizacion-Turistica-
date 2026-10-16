"""Conexión mínima a Supabase vía PostgREST, sin dependencias extra.

Lee las credenciales de variables de entorno o del archivo .env en la raíz del repo.
El tablero usa la publishable key (sujeta a RLS); la secret key solo se usa en scripts de carga.
"""
import json
import os
import urllib.error
import urllib.request
from pathlib import Path

import pandas as pd

RAIZ = Path(__file__).resolve().parent.parent


def _cargar_env(ruta: Path = RAIZ / ".env") -> None:
    if not ruta.exists():
        return
    for linea in ruta.read_text(encoding="utf-8").splitlines():
        linea = linea.strip()
        if linea and not linea.startswith("#") and "=" in linea:
            k, v = linea.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())


_cargar_env()


def configurado() -> bool:
    return bool(os.environ.get("SUPABASE_URL") and os.environ.get("SUPABASE_PUBLISHABLE_KEY"))


def _peticion(ruta: str, secreta: bool = False, esquema: str = "public", metodo: str = "GET",
              cuerpo=None, extra: dict | None = None):
    clave = os.environ["SUPABASE_SECRET_KEY" if secreta else "SUPABASE_PUBLISHABLE_KEY"]
    cab = {"apikey": clave, "Accept-Profile": esquema, "Content-Profile": esquema,
           "Content-Type": "application/json", **(extra or {})}
    datos = json.dumps(cuerpo).encode() if cuerpo is not None else None
    req = urllib.request.Request(f"{os.environ['SUPABASE_URL']}/rest/v1/{ruta}", data=datos,
                                 headers=cab, method=metodo)
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            texto = r.read().decode()
            return json.loads(texto) if texto else None
    except urllib.error.HTTPError as e:
        e.msg = f"{e.msg} · {metodo} {esquema}.{ruta.split('?')[0]} · {e.read().decode()[:500]}"
        raise


def leer(tabla: str, esquema: str = "public", select: str = "*", secreta: bool = False,
         filtro: str = "") -> pd.DataFrame:
    """Lee una tabla paginando de 1000 en 1000. `filtro` en sintaxis de PostgREST (p. ej. "municipio_sk=eq.43")
    para no descargar la tabla completa."""
    filas, ini = [], 0
    while True:
        lote = _peticion(f"{tabla}?select={select}" + (f"&{filtro}" if filtro else ""), secreta, esquema,
                         extra={"Range-Unit": "items", "Range": f"{ini}-{ini + 999}"})
        filas += lote
        if len(lote) < 1000:
            return pd.DataFrame(filas)
        ini += 1000


def leer_por_bloques(tabla: str, columna: str, valores: list, esquema: str = "public", select: str = "*",
                     secreta: bool = False, por_bloque: int = 4, hilos: int = 6) -> pd.DataFrame:
    """Lee una tabla grande por bloques de valores de `columna` (p. ej. municipio de origen), en paralelo.
    Sin offsets: cada petición filtra por la llave y trae menos de 1000 filas, así no choca con el tiempo máximo
    de consulta del rol público (con offsets altos, v_tiempo_municipios fallaba con 'statement timeout')."""
    from concurrent.futures import ThreadPoolExecutor
    bloques = [valores[i:i + por_bloque] for i in range(0, len(valores), por_bloque)]

    def uno(b):
        return leer(tabla, esquema, select, secreta, f"{columna}=in.({','.join(str(v) for v in b)})")
    with ThreadPoolExecutor(max_workers=hilos) as ex:
        return pd.concat(list(ex.map(uno, bloques)), ignore_index=True)


def insertar(tabla: str, registros: list[dict], esquema: str = "public") -> None:
    """Upsert con la secret key (solo scripts de carga, nunca desde el tablero)."""
    for i in range(0, len(registros), 500):
        _peticion(tabla, True, esquema, "POST", registros[i:i + 500],
                  {"Prefer": "resolution=merge-duplicates,return=minimal"})


def tablas(esquema: str = "public") -> list[str]:
    """Tablas y vistas expuestas por la API en ese esquema."""
    spec = _peticion("", True, esquema, extra={"Accept": "application/openapi+json"})
    return sorted(p.strip("/") for p in spec.get("paths", {}) if p.strip("/") and not p.startswith("/rpc"))


def probar() -> None:
    if not configurado():
        print("✗ Falta .env con SUPABASE_URL y SUPABASE_PUBLISHABLE_KEY")
        return
    print(f"Proyecto: {os.environ['SUPABASE_URL']}")
    try:
        req = urllib.request.Request(f"{os.environ['SUPABASE_URL']}/auth/v1/settings",
                                     headers={"apikey": os.environ["SUPABASE_PUBLISHABLE_KEY"]})
        urllib.request.urlopen(req, timeout=20).read()
        print("✓ Conexión con publishable key")
    except urllib.error.HTTPError as e:
        print(f"✗ publishable key: HTTP {e.code}")
    try:
        _peticion("", True, extra={"Accept": "application/openapi+json"})
        print("✓ Conexión con secret key")
    except (urllib.error.HTTPError, KeyError) as e:
        print(f"✗ secret key: {e}")
    try:
        t = tablas()
        print(f"Tablas en public ({len(t)}): {', '.join(t) or '(ninguna todavía)'}")
    except urllib.error.HTTPError as e:
        print(f"No se pudieron listar tablas: HTTP {e.code}")


if __name__ == "__main__":
    probar()
