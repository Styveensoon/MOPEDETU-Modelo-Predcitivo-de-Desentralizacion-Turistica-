"""Reglas de rutas compartidas por el optimizador del modelo y "Arma tu ruta" (plan_migracion_front.md §4.2).

Sin acceso a la base: todo llega en `ins` (model/insumos.py). Las fórmulas son las de model/rutas.py (docstring con el
detalle); los parámetros (75/240 min, paradas, pernocta, bonos...) vienen de `ins.parametros`.

API:
    construir_ruta(ins, inicio_sk, tema=None, destinos=None, max_paradas=6, exigir_ancla=True) -> dict
    evaluar_ruta(ins, ruta, tema) -> dict          # siempre devuelve incumplimientos, nunca None
    optimizar_rutas(ins) -> (elegidas, descartadas, diagnostico)
"""
from __future__ import annotations

import itertools
import math

import numpy as np
import pandas as pd

# "comunitario" queda fuera: su señal (cooperativa, ejido en el nombre) es ruidosa. Se reincorpora con un catálogo.
TEMAS = ["cafe", "mezcal", "ecoturismo", "gastronomia", "artesanias", "bebidas_tradicionales", "religioso",
         "balnearios", "flores_viveros", "museos", "arqueologia", "volcanes"]
# Selección lexicográfica: una región beneficiada más siempre gana a cualquier diferencia de puntaje.
BONO_REGION, BONO_TEMA = 100.0, 1.0


# ------------------------------------------------------------------ piezas
def emergentes(ins) -> set:
    """Municipios con alguna bandera activa distinta de las que no cuentan (BARRERA_ACCESO = "lejos del ancla")."""
    no = set(ins.parametros["banderas_no_emergente"])
    return set(ins.banderas[~ins.banderas.codigo.isin(no)].municipio_sk)


def _cache(ins) -> dict:
    """Valores derivados de los insumos que se reutilizan en cada ruta (se calculan una vez por objeto)."""
    c = getattr(ins, "_cache_rutas", None)
    if c is None:
        n_tema = pd.Series({t: len(ins.presente.get(t, set())) for t in TEMAS})
        c = dict(con_flag=emergentes(ins),
                 especificidad=(0.85 + 0.30 * (1 - (n_tema - n_tema.min()) / max(1, n_tema.max() - n_tema.min()))).to_dict(),
                 motivo_flag=ins.banderas.sort_values("tipo_flag_sk").groupby("municipio_sk").codigo.apply(
                     lambda s: sorted(set(s))).to_dict())
        object.__setattr__(ins, "_cache_rutas", c)
    return c


def valor(ins, mk: int, tema: str | None) -> float:
    """v(m) = índice · (1 + 0.35·emergente) · (1 + 0.40·necesidad social) · (1 + 0.25·tema presente).
    Sin tema: el tema presente que más le conviene (cualquiera de sus temas)."""
    p, c = ins.parametros, _cache(ins)
    r = ins.indice.loc[mk]
    con_tema = (mk in ins.presente.get(tema, set())) if tema else any(mk in s for s in ins.presente.values())
    return (r.indice_oportunidad * (1 + p["bono_bandera"] * (mk in c["con_flag"]))
            * (1 + p["bono_social"] * ins.social.get(mk, 0)) * (1 + p["bono_tema"] * con_tema))


def recorrido(ins, ruta: list, plan: bool = True) -> float:
    t = ins.tiempo_plan if plan else ins.tiempo
    return sum(t[(a, c)] for a, c in zip(ruta, ruta[1:]))


def dos_opt(ins, ruta: list) -> list:
    """Una pasada de 2-opt con el inicio fijo: la mejor inversión que acorta el recorrido sin romper el tramo máximo."""
    mx = ins.parametros["max_tramo_min"]
    mejor_r, mejor_t = ruta, recorrido(ins, ruta)
    for i, j in itertools.combinations(range(1, len(ruta)), 2):
        cand = ruta[:i] + ruta[i:j + 1][::-1] + ruta[j + 1:]
        if all(ins.tiempo_plan[(a, c)] <= mx for a, c in zip(cand, cand[1:])) and recorrido(ins, cand) < mejor_t:
            mejor_r, mejor_t = cand, recorrido(ins, cand)
    return mejor_r


def candidatos(ins, tema: str | None, inicio: int, exigir_ancla: bool = True) -> set:
    """Paradas posibles: tema presente (o cualquier tema), con punto visitable, sin infraestructura roja y, en el
    modelo, sin otras anclas."""
    base = ins.presente.get(tema, set()) if tema else set().union(*ins.presente.values())
    cand = (base & ins.visitables) - ins.infra_rojo - {inicio}
    return cand - set(ins.anclas) if exigir_ancla else cand


def _construir(ins, inicio: int, tema: str | None, cand: set, max_paradas: int) -> list:
    p = ins.parametros
    ruta = [inicio]
    while len(ruta) < max_paradas:
        fin, opciones = ruta[-1], []
        for c in cand - set(ruta):
            t_ = ins.tiempo_plan.get((fin, c))
            if t_ is None or t_ > p["max_tramo_min"] or recorrido(ins, ruta) + t_ > p["max_total_min"]:
                continue
            nuevo = frozenset((fin, c)) not in ins.tramos_oficiales
            g = valor(ins, c, tema) * (0.5 + ins.pe_pct.get((fin, c), 0)) * (1 + p["bono_tramo_nuevo"] * nuevo) \
                / (1 + t_ / 60)
            opciones.append((g, c))
        if not opciones:
            break
        ruta.append(max(opciones)[1])
    return dos_opt(ins, ruta)


def evaluar_ruta(ins, ruta: list, tema: str | None) -> dict:
    """Evalúa una ruta contra TODAS las reglas. Siempre devuelve el diccionario con `incumplimientos` (lista vacía si
    cumple). El puntaje es el mismo del optimizador."""
    p, c = ins.parametros, _cache(ins)
    m = ins.mun
    resto = ruta[1:]
    emerg = [x for x in resto if x in c["con_flag"]]
    incumple = []
    if len(ruta) < p["min_paradas"]:
        incumple.append("pocas_paradas")
    if len(ruta) > p["max_paradas"]:
        incumple.append("muchas_paradas")
    if len(emerg) < p["min_emergentes"]:
        incumple.append("pocos_emergentes")
    meses = ins.meses_fuertes.loc[ruta].sum()
    meses_comunes = [int(k) for k, v in meses.items() if v >= max(2, int(np.ceil(len(ruta) * 0.6)))]
    enl_medio = float(np.mean([ins.pe_pct.get((a, b), 0) for a, b in zip(ruta, ruta[1:])])) if len(ruta) > 1 else 0.0
    tramos_nuevos = float(np.mean([frozenset((a, b)) not in ins.tramos_oficiales
                                   for a, b in zip(ruta, ruta[1:])])) if len(ruta) > 1 else 0.0
    espec = c["especificidad"].get(tema, 1.0) if tema else 1.0
    puntaje = (sum(valor(ins, x, tema) for x in resto) * (0.7 + 0.3 * enl_medio) * (1 + 0.2 * tramos_nuevos)
               * (1 + 0.1 * bool(meses_comunes)) * espec - 0.15 * recorrido(ins, ruta) / p["max_total_min"])
    estancias = [p["estancia_ancla_h"] if m.es_ancla[x] else p["estancia_emergente_h"] for x in ruta]
    horas = recorrido(ins, ruta) / 60 + sum(estancias)
    dias = max(1, math.ceil(horas / p["horas_dia"]))
    region = m.region.reindex(resto).mode().iat[0] if resto else m.region[ruta[0]]
    pernocta = None
    if dias > 1:
        # Dormir en una parada emergente cercana al fin del día 1 (la noche deja derrama fuera del ancla); el inicio
        # cuenta si ninguna otra tiene hospedaje suficiente.
        llegada, h = [], 0.0
        for k, x in enumerate(ruta):
            h += (ins.tiempo_plan[(ruta[k - 1], x)] / 60 if k else 0)
            llegada.append(h)
            h += estancias[k]
        hmin = p["min_hospedaje_pernocta"]
        ok = [k for k in range(1, len(ruta)) if ins.hospedaje.get(ruta[k], 0) >= hmin]
        if ok:
            pernocta = ruta[min(ok, key=lambda k: abs(llegada[k] + estancias[k] - p["horas_dia"]))]
        elif ins.hospedaje.get(ruta[0], 0) >= hmin:
            pernocta = ruta[0]
        else:
            incumple.append("sin_pernocta")
    if region == p["region_excluida"]:
        incumple.append("region_angelopolis")
    if any(ins.tiempo_plan[(a, b)] > p["max_tramo_min"] for a, b in zip(ruta, ruta[1:])):
        incumple.append(f"tramo>{p['max_tramo_min']}")
    if recorrido(ins, ruta) > p["max_total_min"]:
        incumple.append(f"total>{p['max_total_min']}")
    rojo = sum(x in ins.infra_rojo for x in ruta)
    if rojo:
        incumple.append("infra_rojo")
    if any(x not in ins.visitables for x in resto):
        incumple.append("parada_sin_punto_de_visita")
    return dict(ruta=list(ruta), tema=tema, puntaje=puntaje, emergentes=emerg, meses_comunes=meses_comunes,
                enlace_medio=enl_medio, tramos_nuevos=tramos_nuevos, minutos_plan=recorrido(ins, ruta),
                minutos=recorrido(ins, ruta, plan=False), estancias=estancias, horas=round(horas, 1), dias=dias,
                region=region, pernocta=pernocta, incumplimientos=incumple, infra_rojo=rojo)


def construir_ruta(ins, inicio_sk: int, tema: str | None = None, destinos: list | None = None,
                   max_paradas: int | None = None, exigir_ancla: bool = True) -> dict:
    """Ruta desde `inicio_sk`. Automática (destinos=None): inserción voraz + 2-opt con las reglas del modelo.
    "Yo elijo" (destinos = lista): ordena esas paradas con 2-opt (inicio fijo) y las evalúa tal cual.
    Devuelve la evaluación completa; si no hay ruta factible, `incumplimientos` dice por qué."""
    p = ins.parametros
    if destinos:
        ruta = dos_opt(ins, [inicio_sk] + [d for d in destinos if d != inicio_sk])
        e = evaluar_ruta(ins, ruta, tema)
        if not ins.mun.es_ancla[inicio_sk]:
            e["aviso_inicio"] = "no_es_ancla"
        return e
    cand = candidatos(ins, tema, inicio_sk, exigir_ancla)
    if not cand:
        e = evaluar_ruta(ins, [inicio_sk], tema)
        e["incumplimientos"] = ["sin_candidatos_tema"] + e["incumplimientos"]
        return e
    ruta = _construir(ins, inicio_sk, tema, cand, max_paradas or p["max_paradas"])
    e = evaluar_ruta(ins, ruta, tema)
    if not ins.mun.es_ancla[inicio_sk]:
        e["aviso_inicio"] = "no_es_ancla"
    return e


def seleccionar(ins, candidatas: list) -> list:
    """Mejor combinación de n_rutas (búsqueda exhaustiva con poda):
    máx. Σ puntaje + BONO_REGION·(regiones distintas) + BONO_TEMA·(temas distintos)
    s.a. ≤ max_solape de municipios compartidos, ≤ max_por_tema por tema y ≤ max_por_ancla por ancla."""
    p = ins.parametros
    n, N = len(candidatas), p["n_rutas"]
    conj = [set(e["ruta"]) for e in candidatas]
    compat = [[len(conj[i] & conj[j]) / min(len(conj[i]), len(conj[j])) <= p["max_solape"] for j in range(n)]
              for i in range(n)]
    cota = sorted((e["puntaje"] for e in candidatas), reverse=True)
    mejor = {"valor": -np.inf, "sel": []}

    def total(sel):
        es = [candidatas[i] for i in sel]
        return (sum(e["puntaje"] for e in es) + BONO_REGION * len({e["region"] for e in es})
                + BONO_TEMA * len({e["tema"] for e in es}))

    def buscar(inicio, sel, suma):
        if len(sel) == N:
            v = total(sel)
            if v > mejor["valor"]:
                mejor.update(valor=v, sel=list(sel))
            return
        if suma + sum(cota[:N - len(sel)]) + (BONO_REGION + BONO_TEMA) * N <= mejor["valor"]:
            return  # poda: ni con las mejores restantes se supera la mejor combinación
        for i in range(inicio, n):
            e = candidatas[i]
            if not all(compat[i][j] for j in sel):
                continue
            if sum(candidatas[j]["tema"] == e["tema"] for j in sel) >= p["max_por_tema"]:
                continue
            if sum(candidatas[j]["ruta"][0] == e["ruta"][0] for j in sel) >= p["max_por_ancla"]:
                continue
            buscar(i + 1, sel + [i], suma + e["puntaje"])

    buscar(0, [], 0.0)
    return [candidatas[i] for i in mejor["sel"]]


def optimizar_rutas(ins) -> tuple[list, list, pd.DataFrame]:
    """Lo que hacía model/rutas.py::main(): una ruta por ancla × tema, se evalúan, se eligen las n_rutas mejores
    que cumplen y se registran las que se habrían elegido sin las reglas de operación."""
    p, c = ins.parametros, _cache(ins)
    construidas = {}
    for a in ins.anclas:
        for t in TEMAS:
            cand = candidatos(ins, t, a, exigir_ancla=True)
            construidas[(a, t)] = _construir(ins, a, t, cand, p["max_paradas"])
    candidatas, diag = [], []
    for (a, t), r in construidas.items():
        e = evaluar_ruta(ins, r, t)
        # factible = forma mínima de ruta (paradas y emergentes); el resto de reglas se evalúa como "operable"
        factible = not ({"pocas_paradas", "pocos_emergentes"} & set(e["incumplimientos"]))
        if factible:
            candidatas.append(e)
        diag.append(dict(ancla=ins.mun.nombre[a], tema=t, paradas=len(r),
                         recorrido=" → ".join(ins.mun.nombre[x] for x in r),
                         emergentes=sum(x in c["con_flag"] for x in r[1:]), factible=factible,
                         puntaje=round(e["puntaje"], 3) if factible else None,
                         candidatos_tema=len(ins.presente.get(t, set()) - set(ins.anclas)),
                         necesidad_social=round(float(np.mean([ins.social[x] for x in r[1:]])), 2) if len(r) > 1 else None))
    candidatas.sort(key=lambda e: -e["puntaje"])
    operables = [e for e in candidatas if not e["incumplimientos"]]
    elegidas = seleccionar(ins, operables)
    descartadas = [e for e in seleccionar(ins, candidatas) if e["incumplimientos"]]
    diagnostico = pd.DataFrame(diag).sort_values(["tema", "puntaje"], ascending=[True, False])
    return elegidas, descartadas, diagnostico


def motivo_flag(ins) -> dict:
    return _cache(ins)["motivo_flag"]
