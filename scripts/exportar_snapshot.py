"""Copia local de la base para el tablero (plan_migracion_front.md §12.2).

Exporta a data/snapshot/<objeto>.jsonl cada vista y tabla que lee dashboard/bd.py (lista bd.OBJETOS), con la
fecha de corte en data/snapshot/LEEME.txt. Si Supabase no responde, el tablero usa esta copia y lo dice. No es
DEMO: son los mismos datos reales. Lo corre scripts/pipeline.py al final.

Uso: python scripts/exportar_snapshot.py
"""
import sys
from datetime import datetime
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(RAIZ / "dashboard")]

import supabase_cliente as sb  # noqa: E402
from bd import OBJETOS, SNAPSHOT  # noqa: E402


def main():
    SNAPSHOT.mkdir(parents=True, exist_ok=True)
    resumen = []
    for tabla, select in OBJETOS.items():
        df = sb.leer(tabla, "dw", select)          # publishable key: exactamente lo que ve el tablero
        df.to_json(SNAPSHOT / f"{tabla}.jsonl", orient="records", lines=True, force_ascii=False, date_format="iso")
        resumen.append(f"dw.{tabla}\t{len(df)}")
        print(f"  {tabla}: {len(df):,}")
    corte = datetime.now().strftime("%Y-%m-%d %H:%M")
    (SNAPSHOT / "LEEME.txt").write_text(
        "Copia local de la base MOPEDETU (Supabase, esquema dw) para usar el tablero sin internet\n"
        f"{corte}\nObjeto\tFilas\n" + "\n".join(resumen) + "\n", encoding="utf-8")
    print(f"✓ data/snapshot: {len(resumen)} objetos · corte {corte}")


if __name__ == "__main__":
    main()
