"""Orquestador: reconstruye de principio a fin lo que usa la plataforma (plan_migracion_front.md A12).

Corre en orden, se detiene ante el primer error e imprime las validaciones. Usa los archivos crudos locales
(data/raw/, ignorados por git) para los pasos que los necesitan; las fuentes externas (OSRM, Wikipedia, DATATUR,
SESNSP, CONAPO) se refrescan con sus propios scripts, no aquí.

Pasos:
  actividades  scripts/calcular_actividades.py   actividades por municipio y por negocio
  ficha        scripts/calcular_ficha.py         infraestructura, temporadas y semáforos
  indice       model/indice.py                   índice v1_base y banderas (línea base)
  crecimiento  model/crecimiento.py              modelo vigente, índice v3 y banderas (incluye visibilidad)
  enlaces      model/enlaces.py                  perfiles, similitud y probabilidad de enlace
  rutas        model/rutas.py                    optimizador de rutas (reglas compartidas)
  trazos       scripts/trazar_rutas.py           trazo por carretera guardado de las rutas
  riesgo       scripts/cargar_seguridad.py --solo-riesgo
  circuitos    model/circuitos.py                circuitos estándar y temáticos con su trazo
  escenarios   model/escenario_hhi.py            HHI, top 5 y Gini
  semaforos    scripts/calcular_ficha.py         otra vez: semáforo de potencial con la predicción
  validaciones scripts/validaciones.py           V1-V9 y pruebas de datos → dw.fact_validacion
  snapshot     scripts/exportar_snapshot.py      copia local para el tablero sin internet
  mapa         scripts/exportar_mapa_html.py     mapa HTML de respaldo
  entregables  scripts/generar_entregables.py    docs/entregables.md con cifras de la base

Uso:
    python scripts/pipeline.py                     # todo
    python scripts/pipeline.py --desde rutas       # retomar desde un paso
    python scripts/pipeline.py --solo validaciones snapshot
"""
import argparse
import subprocess
import sys
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
PY = sys.executable
DENUE = RAIZ / "data/raw/denue/conjunto_de_datos/denue_inegi_21_.csv"
OSM = RAIZ / "data/raw/osm_a2"
ITER = RAIZ / "data/raw/iter/iter_21_cpv2020/conjunto_de_datos/conjunto_de_datos_iter_21CSV20.csv"
GEO = RAIZ / "data/raw/geo/Puebla.json"
FICHA = ["scripts/calcular_ficha.py", "--denue", str(DENUE), "--osm", str(OSM), "--iter", str(ITER), "--geo", str(GEO)]

PASOS = [
    ("actividades", ["scripts/calcular_actividades.py", str(DENUE)], RAIZ, [DENUE]),
    ("ficha", FICHA, RAIZ, [DENUE, OSM, ITER, GEO]),
    ("indice", ["indice.py"], RAIZ / "model", []),
    ("crecimiento", ["crecimiento.py"], RAIZ / "model", []),
    ("enlaces", ["enlaces.py"], RAIZ / "model", []),
    ("rutas", ["rutas.py"], RAIZ / "model", []),
    ("trazos", ["scripts/trazar_rutas.py"], RAIZ, []),
    ("riesgo", ["scripts/cargar_seguridad.py", "--solo-riesgo"], RAIZ, []),
    ("circuitos", ["circuitos.py"], RAIZ / "model", []),
    ("escenarios", ["escenario_hhi.py"], RAIZ / "model", []),
    ("semaforos", FICHA, RAIZ, [DENUE, OSM, ITER, GEO]),
    ("validaciones", ["scripts/validaciones.py"], RAIZ, []),
    ("snapshot", ["scripts/exportar_snapshot.py"], RAIZ, []),
    ("mapa", ["scripts/exportar_mapa_html.py"], RAIZ, []),
    ("entregables", ["scripts/generar_entregables.py"], RAIZ, []),
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--desde", choices=[p[0] for p in PASOS])
    ap.add_argument("--solo", nargs="*", choices=[p[0] for p in PASOS])
    args = ap.parse_args()
    nombres = [p[0] for p in PASOS]
    pasos = PASOS[nombres.index(args.desde):] if args.desde else PASOS
    if args.solo:
        pasos = [p for p in pasos if p[0] in args.solo]

    tiempos = []
    for nombre, cmd, cwd, requiere in pasos:
        faltan = [str(r.relative_to(RAIZ)) for r in requiere if not r.exists()]
        if faltan:
            raise SystemExit(f"✗ {nombre}: faltan archivos locales {faltan} (ver docs/Validations.md §25.10)")
        print(f"\n━━ {nombre} ━━ {' '.join(cmd)}", flush=True)
        t0 = time.time()
        r = subprocess.run([PY, *cmd], cwd=cwd, env={**__import__('os').environ, "PYTHONIOENCODING": "utf-8"})
        tiempos.append((nombre, time.time() - t0))
        if r.returncode != 0:
            print(f"\n✗ El pipeline se detuvo en '{nombre}' (código {r.returncode}). Retomar con --desde {nombre}")
            sys.exit(r.returncode)
    print("\n━━ resumen ━━")
    for n, t in tiempos:
        print(f"  ✓ {n:<12} {t:6.0f} s")
    print(f"  total {sum(t for _, t in tiempos) / 60:.1f} min")


if __name__ == "__main__":
    main()
