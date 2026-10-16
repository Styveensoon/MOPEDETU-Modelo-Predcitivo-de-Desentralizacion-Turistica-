"""Respaldo LOCAL de los esquemas dw y stg (plan_migracion_front.md §1, regla 2).

Sin pg_dump ni DATABASE_URL, exporta cada tabla expuesta por la API a CSV con la secret key, en
data/respaldo/AAAA-MM-DD/<esquema>.<tabla>.csv, más un LEEME.txt con conteos. Las vistas no se respaldan (su
definición está en sql/). Para restaurar: insertar los CSV en el mismo orden de dependencias que DDL/ y sql/.

Uso: python scripts/respaldo_local.py
"""
import sys
from datetime import date
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(RAIZ / "dashboard")]

import supabase_cliente as sb  # noqa: E402


def tablas_base(esquema: str) -> list[str]:
    spec = sb._peticion("", True, esquema, extra={"Accept": "application/openapi+json"})
    # En el OpenAPI de PostgREST las vistas no aceptan POST (salvo las actualizables); nos quedamos con lo que
    # tiene POST, que en dw/stg son las tablas.
    return sorted(p.strip("/") for p, ops in spec.get("paths", {}).items()
                  if p.strip("/") and not p.startswith("/rpc") and "post" in ops)


def main():
    destino = RAIZ / "data" / "respaldo" / date.today().isoformat()
    destino.mkdir(parents=True, exist_ok=True)
    resumen = []
    for esquema in ("dw", "stg"):
        for t in tablas_base(esquema):
            df = sb.leer(t, esquema, secreta=True)
            df.to_csv(destino / f"{esquema}.{t}.csv", index=False)
            resumen.append(f"{esquema}.{t}\t{len(df)}")
            print(f"  {esquema}.{t}: {len(df):,}")
    (destino / "LEEME.txt").write_text("Respaldo local de MOPEDETU (Supabase dw y stg)\n"
                                       f"Fecha: {date.today().isoformat()}\nTabla\tFilas\n" + "\n".join(resumen) + "\n",
                                       encoding="utf-8")
    print(f"✓ {len(resumen)} tablas en {destino.relative_to(RAIZ)}")


if __name__ == "__main__":
    main()
