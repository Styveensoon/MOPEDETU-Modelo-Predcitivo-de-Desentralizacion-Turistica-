"""Crea los roles dev_raul y dev_styveen con contraseñas largas y aplica los permisos.

Uso:
    python scripts/crear_roles.py

Las credenciales se escriben en .credenciales_roles.txt (ignorado por Git). Compártelas por
mensaje privado o gestor de contraseñas, nunca en el chat de grupo. Si un rol ya existe,
no cambia su contraseña.
"""
import os
import secrets
from pathlib import Path
from urllib.parse import urlparse

from db import RAIZ, motor

ROLES = ["dev_raul", "dev_styveen"]
SALIDA = RAIZ / ".credenciales_roles.txt"


def main():
    eng = motor()
    url = urlparse(os.environ["DATABASE_URL"])
    # Con el pooler de Supabase el usuario lleva el identificador del proyecto: rol.<ref>
    sufijo = url.username.split(".", 1)[1] if url.username and "." in url.username else None

    nuevas = {}
    conn = eng.raw_connection()
    try:
        with conn.cursor() as cur:
            for rol in ROLES:
                cur.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (rol,))
                if cur.fetchone():
                    print(f"{rol}: ya existe, no se cambia la contraseña")
                    continue
                clave = secrets.token_urlsafe(24)
                cur.execute(f'CREATE ROLE "{rol}" LOGIN PASSWORD %s', (clave,))
                nuevas[rol] = clave
                print(f"{rol}: creado")
            cur.execute((RAIZ / "DDL" / "04_permisos_mopedetu.sql").read_text(encoding="utf-8"))
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    if nuevas:
        lineas = []
        for rol, clave in nuevas.items():
            usuario = f"{rol}.{sufijo}" if sufijo else rol
            lineas.append(f"{rol}\n  usuario: {usuario}\n  contraseña: {clave}\n"
                          f"  DATABASE_URL=postgresql://{usuario}:{clave}@{url.hostname}:{url.port or 5432}"
                          f"{url.path or '/postgres'}\n")
        with SALIDA.open("a", encoding="utf-8") as fh:
            fh.write("\n".join(lineas) + "\n")
        print(f"Credenciales guardadas en {SALIDA}")
    print("Permisos aplicados (DDL/04_permisos_mopedetu.sql)")


if __name__ == "__main__":
    main()
