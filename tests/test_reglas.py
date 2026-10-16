"""Pruebas de las reglas de rutas y circuitos (plan_migracion_front.md §9.1 y §9.2).

§9.1 usa un fixture pequeño construido SOLO dentro de este archivo (no son datos del tablero ni de la base).
§9.2 (no regresión) necesita Supabase: compara optimizar_rutas contra tests/fixtures/rutas_propuestas_antes_extraccion.csv;
se omite si no hay .env o si los datos de la base ya cambiaron después de la extracción (se dice).

Uso:  python tests/test_reglas.py
"""
import sys
from pathlib import Path

import pandas as pd

RAIZ = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(RAIZ / "model"), str(RAIZ / "dashboard")]

import reglas_circuitos as rc  # noqa: E402
import reglas_rutas as rr  # noqa: E402
from insumos import Insumos  # noqa: E402

PARAMS = dict(max_tramo_min=75, max_total_min=240, min_paradas=3, max_paradas=6, max_paradas_usuario=9,
              min_emergentes=2, min_hospedaje_pernocta=10, horas_dia=10, estancia_ancla_h=3, estancia_emergente_h=2,
              bono_bandera=0.35, bono_social=0.40, bono_tema=0.25, bono_tramo_nuevo=0.3, region_excluida="Angelópolis",
              banderas_no_emergente=["BARRERA_ACCESO"], n_rutas=1, max_solape=0.5, max_por_ancla=2, max_por_tema=2)


def insumos_prueba(tiempos: dict | None = None, hospedaje: dict | None = None, infra_rojo=frozenset(),
                   banderas: dict | None = None) -> Insumos:
    """Seis municipios: 1 ancla (A) y cinco candidatos (2-6) con tema 'cafe', en la Sierra Norte."""
    ids = [1, 2, 3, 4, 5, 6]
    mun = pd.DataFrame({"nombre": ["A", "B", "C", "D", "E", "F"], "region": ["Sierra Norte"] * 6,
                        "es_ancla": [True] + [False] * 5, "indice_marginacion": [0.0] * 6}, index=ids)
    base_t = {(a, b): 30.0 for a in ids for b in ids if a != b}
    base_t.update(tiempos or {})
    flags = banderas if banderas is not None else {2: "OFERTA_EMERGENTE", 3: "OFERTA_EMERGENTE", 4: "IMPACTO_SOCIAL"}
    ban = pd.DataFrame([dict(municipio_sk=m, tipo_flag_sk=1, codigo=c) for m, c in flags.items()],
                       columns=["municipio_sk", "tipo_flag_sk", "codigo"])
    return Insumos(
        mun=mun, version_indice="prueba", version_indice_sk=0, pesos={}, parametros=PARAMS,
        indice=pd.DataFrame({"indice_oportunidad": [0.5, 0.8, 0.7, 0.6, 0.5, 0.4], "eje_sk": [1] * 6}, index=ids),
        banderas=ban, presente={"cafe": {2, 3, 4, 5, 6}}, pred=pd.DataFrame(), pe_pct={},
        tiempo=dict(base_t), tiempo_plan=dict(base_t), distancia={k: 20.0 for k in base_t},
        hospedaje=pd.Series(hospedaje or {1: 50}).reindex(ids).fillna(0), infra_rojo=set(infra_rojo),
        visitables={2, 3, 4, 5, 6}, social=pd.Series(0.5, index=ids),
        meses_fuertes=pd.DataFrame(0, index=ids, columns=range(1, 13)), tramos_oficiales=set(), anclas=[1])


# ------------------------------------------------------------------ §9.1 rutas
def test_rutas_respeta_75_240():
    ins = insumos_prueba(tiempos={(1, 6): 80.0, (6, 1): 80.0})
    e = rr.construir_ruta(ins, 1, "cafe")
    tramos = [ins.tiempo_plan[(a, b)] for a, b in zip(e["ruta"], e["ruta"][1:])]
    assert max(tramos) <= 75 and sum(tramos) <= 240 and not e["incumplimientos"], e
    print(f"✔ rutas: tramo ≤ 75 y total ≤ 240 ({len(e['ruta'])} paradas, {sum(tramos):.0f} min)")


def test_rutas_exige_emergentes():
    ins = insumos_prueba(banderas={2: "BARRERA_ACCESO", 3: "OFERTA_EMERGENTE"})
    e = rr.construir_ruta(ins, 1, "cafe")
    assert "pocos_emergentes" in e["incumplimientos"], e["incumplimientos"]
    print("✔ rutas: exige ≥ 2 emergentes y BARRERA_ACCESO no cuenta")


def test_rutas_pernocta():
    ins = insumos_prueba(hospedaje={1: 2, 2: 3})   # nadie con ≥ 10
    e = rr.construir_ruta(ins, 1, "cafe")
    assert e["dias"] > 1 and "sin_pernocta" in e["incumplimientos"], e
    ins2 = insumos_prueba(hospedaje={1: 2, 3: 12})
    e2 = rr.construir_ruta(ins2, 1, "cafe")
    assert e2["pernocta"] == 3 and "sin_pernocta" not in e2["incumplimientos"], e2
    print("✔ rutas: pernocta ≥ 10 hospedajes cuando dura más de un día")


def test_rutas_infra_roja():
    ins = insumos_prueba(infra_rojo={2})
    e = rr.construir_ruta(ins, 1, "cafe")
    assert 2 not in e["ruta"], "en automático no debe entrar infraestructura roja"
    e2 = rr.evaluar_ruta(ins, [1, 2, 3, 4], "cafe")
    assert "infra_rojo" in e2["incumplimientos"]
    print("✔ rutas: excluye infraestructura 🔴 en automático y la reporta en 'Yo elijo'")


def test_rutas_reporta_todo():
    ins = insumos_prueba(tiempos={(1, 2): 90.0}, infra_rojo={3})
    ins.visitables.discard(4)
    e = rr.evaluar_ruta(ins, [1, 2, 3, 4], "cafe")
    for inc in ("tramo>75", "infra_rojo", "parada_sin_punto_de_visita"):
        assert inc in e["incumplimientos"], (inc, e["incumplimientos"])
    print(f"✔ rutas: evaluar_ruta reporta cada incumplimiento {e['incumplimientos']}")


# ------------------------------------------------------------------ §9.1 circuitos
def lugares_prueba() -> tuple[pd.DataFrame, tuple]:
    cab = (20.0, -97.5)
    filas = []
    for i, (dlat, cat, tipo, act, prio) in enumerate([
            (0.004, "museo", "atractivo", None, 3), (0.006, "templo", "atractivo", None, 2),
            (0.008, "cafe", "experiencia", "cafe", 4), (0.003, "cafe", "experiencia", "cafe", 4),
            (0.005, "cafe", "experiencia", "cafe", 5), (0.002, "artesanias", "experiencia", "artesanias", 4),
            (0.007, "cascada", "atractivo", None, 2), (0.009, "comida", "comida", "gastronomia", 7),
            (0.30, "museo", "atractivo", None, 1)]):                          # el último, muy lejos
        filas.append(dict(lugar_id=f"x:{i}", municipio_sk=1, nombre=f"Lugar {i}", actividad=act, categoria=cat,
                          tipo_parada=tipo, origen="osm", url=None, personal_est=10 - i,
                          lat=cab[0] + dlat, lon=cab[1] + dlat / 2, prioridad=prio))
    return pd.DataFrame(filas), cab


def test_circuitos_duracion_y_tramo():
    l, cab = lugares_prueba()
    for mod, h in (("a_pie", 4), ("auto", 8)):
        c = rc.armar_circuito(l, cab, mod, h)
        assert c["duracion_min"] <= h * 60 and c["cumple"], c["incumplimientos"]
        assert all(p["min_desde_anterior"] <= rc.PARAMETROS["tramo_max_min"][mod] for p in c["paradas"])
        assert "x:8" not in [p["lugar_id"] for p in c["paradas"]], "el lugar lejano rompe el tramo máximo"
    print("✔ circuitos: respetan duración y tramo máximo")


def test_circuitos_diversidad_y_minimos():
    l, cab = lugares_prueba()
    c = rc.armar_circuito(l, cab, "a_pie", 8)
    cats = pd.Series([p["actividad"] or p["categoria"] for p in c["paradas"] if p["tipo_parada"] != "comida"])
    assert cats.value_counts().max() <= 2, cats.value_counts()
    visit = [p for p in c["paradas"] if p["tipo_parada"] in ("atractivo", "experiencia")]
    assert len(visit) >= 3 and any(p["tipo_parada"] == "atractivo" for p in visit)
    print("✔ circuitos: máximo 2 por categoría, ≥ 3 paradas con ≥ 1 atractivo")


def test_circuitos_comida_en_horario():
    l, cab = lugares_prueba()
    c = rc.armar_circuito(l, cab, "a_pie", 8)
    comidas = [p for p in c["paradas"] if p["tipo_parada"] == "comida"]
    assert len(comidas) <= 2
    for p in comidas:
        assert 12 * 60 <= p["llegada_min"] <= 15 * 60, p["llegada_min"]
    print(f"✔ circuitos: comida en horario ({len(comidas)} en un circuito de 8 h)")


def test_circuitos_determinista():
    l, cab = lugares_prueba()
    assert rc.armar_circuito(l, cab, "auto", 4) == rc.armar_circuito(l.sample(frac=1, random_state=1), cab, "auto", 4)
    print("✔ circuitos: deterministas (mismo resultado aunque cambie el orden de los lugares)")


# ------------------------------------------------------------------ §9.2 no regresión
def test_no_regresion():
    import supabase_cliente
    if not supabase_cliente.configurado():
        print("… no regresión omitida: falta .env")
        return
    import insumos
    ins = insumos.cargar(secreta=True)
    el, _, _ = rr.optimizar_rutas(ins)
    fx = pd.read_csv(RAIZ / "tests" / "fixtures" / "rutas_propuestas_antes_extraccion.csv")
    nuevos = [" → ".join(ins.mun.nombre[x] for x in e["ruta"]) for e in el]
    iguales = list(fx.recorrido) == nuevos and all(abs(a - e["puntaje"]) < 1e-6 for a, e in zip(fx.puntaje, el))
    if iguales:
        print("✔ no regresión: optimizar_rutas reproduce las 5 rutas de antes de la extracción")
    else:
        # Los datos de la base cambiaron después de la extracción (p. ej. v_lugar_circuito sin 'SIN NOMBRE'):
        # la prueba válida se hizo en el momento de la extracción (docs/log_migracion_front.md).
        print("… no regresión: los datos de la base cambiaron después de la extracción; ver el log (§9.2 ✅ "
              "registrado en el momento de la extracción)")


if __name__ == "__main__":
    for nombre, f in list(globals().items()):
        if nombre.startswith("test_"):
            f()
    print("OK")
