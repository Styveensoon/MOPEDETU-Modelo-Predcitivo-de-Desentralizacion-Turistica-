"""Reglas de circuitos dentro de un municipio (plan_migracion_front.md §4.3), sin acceso a la base.

Un circuito es un recorrido que sale de la cabecera municipal y regresa a ella, visitando puntos de
dw.v_lugar_circuito. Lo usan model/circuitos.py (circuitos estándar guardados) y la página Circuitos (personalizados).

Parámetros: dw.dim_version_calculo 'circuitos_v1' (PARAMETROS es el valor con que se crea esa fila).
Algoritmo: vecino más cercano ponderado por prioridad desde la cabecera (minutos + 10 por cada nivel de prioridad:
un lugar curado a 10 min gana a un negocio genérico de al lado), respetando el tramo máximo y la duración (incluido el
regreso y, si el circuito cruza el mediodía, el tiempo reservado para comer); la primera parada es un atractivo y
ninguna parada queda a más del tramo máximo de la cabecera; luego 2-opt con la cabecera fija y una
parada de comida entre las 13:00 y las 15:00. Determinista: los empates se rompen por personal ocupado y por lugar_id.
"""
from __future__ import annotations

import itertools
import math

import pandas as pd

PARAMETROS = {
    "estancia_min": {"museo": 90, "zona_arqueologica": 90, "patrimonio": 60, "santuario": 45, "templo": 45,
                     "santuario_mirador": 60, "cascada": 90, "gruta": 90, "mirador": 90, "naturaleza": 90,
                     "poza": 90, "peña": 60, "manantial": 60, "volcán": 90, "cerro": 60, "balneario": 120,
                     "recreacion": 60, "experiencia": 60, "comida": 60, "otro": 45},
    "velocidad_kmh": {"a_pie": 4.5, "auto": 25.0},
    "factor_rodeo": 1.4,
    "tramo_max_min": {"a_pie": 25, "auto": 30},
    "min_paradas": 3, "min_atractivos": 1, "max_por_categoria": 2,
    "comida_cada_h": 4, "comida_ventana": [13, 15], "hora_inicio": 9,
    "penalizacion_prioridad_min": 10,   # minutos efectivos = minutos + 10·(prioridad − 1)
}


def km(a: tuple[float, float], b: tuple[float, float]) -> float:
    la1, lo1, la2, lo2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 2 * 6371 * math.asin(math.sqrt(h))


def minutos(a, b, modalidad: str, p: dict = PARAMETROS) -> float:
    return km(a, b) * p["factor_rodeo"] / p["velocidad_kmh"][modalidad] * 60


def estancia(fila, p: dict = PARAMETROS) -> int:
    if fila["tipo_parada"] in ("experiencia", "comida"):
        return p["estancia_min"][fila["tipo_parada"]]
    return p["estancia_min"].get(fila["categoria"], p["estancia_min"]["otro"])


def _clave(fila) -> str:
    """Categoría para el límite de diversidad: la actividad si tiene, si no la categoría."""
    return fila["actividad"] if isinstance(fila["actividad"], str) and fila["actividad"] else fila["categoria"]


def armar_circuito(lugares: pd.DataFrame, cabecera: tuple[float, float], modalidad: str = "a_pie",
                   duracion_h: float = 4, tipo: str = "variado", actividad: str | None = None,
                   principales: set | None = None, p: dict = PARAMETROS) -> dict:
    """Circuito desde la cabecera. `lugares` = filas de v_lugar_circuito de UN municipio.
    Devuelve dict con paradas, minutos de traslado, duración, `cumple` y `incumplimientos`."""
    limite = duracion_h * 60
    tramo_max = p["tramo_max_min"][modalidad]
    l = lugares[lugares.lat.notna() & lugares.lon.notna()].copy()
    l["personal_est"] = pd.to_numeric(l.personal_est, errors="coerce").fillna(0)
    incumple = []
    if tipo == "tematico":
        if not actividad:
            incumple.append("tematico_sin_actividad")
        elif principales is not None and actividad not in principales:
            incumple.append("actividad_no_principal")
    visitas = l[l.tipo_parada.isin(["atractivo", "experiencia"])]
    if tipo == "tematico" and actividad:
        visitas = visitas[visitas.actividad == actividad]
    visitas = visitas.sort_values(["prioridad", "personal_est", "lugar_id"], ascending=[True, False, True])
    comidas = l[l.tipo_parada == "comida"].sort_values(["prioridad", "personal_est", "lugar_id"],
                                                       ascending=[True, False, True])

    # Tiempo reservado para comer si el circuito llega a la ventana de comida y hay dónde
    cruza = p["hora_inicio"] * 60 + limite >= p["comida_ventana"][0] * 60 + p["estancia_min"]["comida"]
    reserva = p["estancia_min"]["comida"] if (cruza and not comidas.empty and limite >= p["comida_cada_h"] * 60) else 0

    # --- vecino más cercano ponderado por prioridad
    ruta, usado_cat, reloj, pos = [], {}, 0.0, cabecera
    disponibles = list(visitas.to_dict("records"))
    while True:
        mejor = None
        for f in disponibles:
            if f["lugar_id"] in {r["lugar_id"] for r in ruta}:
                continue
            if tipo == "variado" and usado_cat.get(_clave(f), 0) >= p["max_por_categoria"]:
                continue
            if not ruta and f["tipo_parada"] != "atractivo":
                continue  # la primera parada es un atractivo: garantiza el mínimo de atractivos
            t = minutos(pos, (f["lat"], f["lon"]), modalidad, p)
            regreso = minutos((f["lat"], f["lon"]), cabecera, modalidad, p)
            # tramo ≤ máximo, y la parada a ≤ tramo máximo de la cabecera (el regreso también es un tramo)
            if t > tramo_max or regreso > tramo_max or reloj + t + estancia(f, p) + regreso > limite - reserva:
                continue
            efectivo = t + p["penalizacion_prioridad_min"] * (f["prioridad"] - 1)
            clave = (efectivo, -f["personal_est"], f["lugar_id"])
            if mejor is None or clave < mejor[0]:
                mejor = (clave, f, t)
        if mejor is None:
            break
        _, f, t = mejor
        ruta.append(f)
        usado_cat[_clave(f)] = usado_cat.get(_clave(f), 0) + 1
        reloj += t + estancia(f, p)
        pos = (f["lat"], f["lon"])

    ruta = _dos_opt(ruta, cabecera, modalidad, tramo_max, p)
    ruta = _agregar_comida(ruta, comidas, cabecera, modalidad, tramo_max, limite, p)
    paradas, total_traslado, reloj, pos = [], 0.0, p["hora_inicio"] * 60, cabecera
    for k, f in enumerate(ruta, 1):
        t = minutos(pos, (f["lat"], f["lon"]), modalidad, p)
        reloj += t
        total_traslado += t
        paradas.append(dict(orden=k, lugar_id=f["lugar_id"], nombre=f["nombre"], tipo_parada=f["tipo_parada"],
                            actividad=f["actividad"] if isinstance(f["actividad"], str) else None,
                            categoria=f["categoria"], origen=f["origen"], url=f.get("url"),
                            lat=float(f["lat"]), lon=float(f["lon"]), min_desde_anterior=round(t, 1),
                            estancia_min=estancia(f, p), llegada_min=round(reloj, 1)))
        reloj += estancia(f, p)
        pos = (f["lat"], f["lon"])
    regreso = minutos(pos, cabecera, modalidad, p) if ruta else 0.0
    total_traslado += regreso
    duracion = sum(x["estancia_min"] for x in paradas) + total_traslado

    visitables = [x for x in paradas if x["tipo_parada"] in ("atractivo", "experiencia")]
    if len(visitables) < p["min_paradas"]:
        incumple.append("pocas_paradas")
    if sum(x["tipo_parada"] == "atractivo" for x in paradas) < p["min_atractivos"]:
        incumple.append("sin_atractivo")
    if duracion > limite + 1e-6:
        incumple.append("excede_duracion")
    if any(x["min_desde_anterior"] > tramo_max + 1e-6 for x in paradas) or regreso > tramo_max + 1e-6:
        incumple.append("tramo_largo")
    return dict(paradas=paradas, minutos_traslado=round(total_traslado, 1), minutos_regreso=round(regreso, 1),
                duracion_min=round(duracion, 1), modalidad=modalidad, duracion_h=duracion_h, tipo=tipo,
                actividad=actividad, cumple=not incumple, incumplimientos=incumple)


def _largo(ruta, cabecera, modalidad, p) -> float:
    puntos = [cabecera] + [(f["lat"], f["lon"]) for f in ruta] + [cabecera]
    return sum(minutos(a, b, modalidad, p) for a, b in zip(puntos, puntos[1:]))


def _dos_opt(ruta, cabecera, modalidad, tramo_max, p) -> list:
    """2-opt iterativo con la cabecera fija al inicio y al final; solo acepta órdenes que respetan el tramo máximo."""
    mejor, largo = list(ruta), _largo(ruta, cabecera, modalidad, p)
    mejora = True
    while mejora:
        mejora = False
        for i, j in itertools.combinations(range(len(mejor)), 2):
            cand = mejor[:i] + mejor[i:j + 1][::-1] + mejor[j + 1:]
            puntos = [cabecera] + [(f["lat"], f["lon"]) for f in cand] + [cabecera]
            if any(minutos(a, b, modalidad, p) > tramo_max for a, b in zip(puntos, puntos[1:])):
                continue
            nuevo = _largo(cand, cabecera, modalidad, p)
            if nuevo < largo - 1e-9:
                mejor, largo, mejora = cand, nuevo, True
    return mejor


def _agregar_comida(ruta, comidas, cabecera, modalidad, tramo_max, limite, p) -> list:
    """Hasta 1 comida por cada `comida_cada_h` horas, insertada donde el reloj cae entre 13:00 y 15:00."""
    maximo = int(limite // (p["comida_cada_h"] * 60))
    if maximo < 1 or comidas.empty or not ruta:
        return ruta
    ini, fin = (h * 60 for h in p["comida_ventana"])
    reloj, pos, llegadas = p["hora_inicio"] * 60, cabecera, []
    for f in ruta:
        reloj += minutos(pos, (f["lat"], f["lon"]), modalidad, p) + estancia(f, p)
        llegadas.append(reloj)       # hora al salir de cada parada
        pos = (f["lat"], f["lon"])
    huecos = [k for k, h in enumerate(llegadas) if ini <= h <= fin]
    if not huecos:
        return ruta
    k = huecos[0]
    a = (ruta[k]["lat"], ruta[k]["lon"])
    b = (ruta[k + 1]["lat"], ruta[k + 1]["lon"]) if k + 1 < len(ruta) else cabecera
    mejor = None
    for f in comidas.to_dict("records"):
        c = (f["lat"], f["lon"])
        t1, t2 = minutos(a, c, modalidad, p), minutos(c, b, modalidad, p)
        if t1 > tramo_max or t2 > tramo_max:
            continue
        clave = (t1 + t2, f["prioridad"], -f["personal_est"], f["lugar_id"])
        if mejor is None or clave < mejor[0]:
            mejor = (clave, f)
    if mejor is None:
        return ruta
    nueva = ruta[:k + 1] + [mejor[1]] + ruta[k + 1:]
    return nueva if _largo(nueva, cabecera, modalidad, p) + sum(estancia(f, p) for f in nueva) <= limite else ruta
