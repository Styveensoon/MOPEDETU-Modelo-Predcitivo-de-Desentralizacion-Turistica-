"""Motor analítico del tablero (versión ligera de los anillos A2–A6).

Todo es cálculo vectorizado sobre tablas pequeñas: se ejecuta en milisegundos en
cada interacción. Cuando exista el pipeline real, `predecir()` usará el modelo
LightGBM del anillo A3 en lugar de la función sustituta.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from datos import Datos

ESCENARIOS = {
    "tendencial": "Tendencial (inercia)",
    "inversion_reciente": "Con inversión reciente 2024-25",
    "inversion_simulada": "Con inversión simulada",
    "promocion": "Con promoción y rutas",
    "combinado": "Combinado (inversión + promoción)",
}

ENFOQUES = {
    #                   oferta crec  invis  acces  social barrera
    "Balanceado":        (.25, .20, .20, .15, .15, .05),
    "Económico":         (.35, .35, .10, .15, .03, .02),
    "Social":            (.15, .10, .15, .10, .45, .05),
    "Descentralización": (.20, .10, .35, .25, .05, .05),
}

FLAGS = {
    "OFERTA_INVISIBLE": "Hay actividad real y casi nadie la promociona",
    "OFERTA_SIN_INVERSION": "Potencial alto sin inversión pública reciente",
    "INVERSION_SIN_RETORNO": "Recibió inversión pero crece poco",
    "ACCESIBLE_NO_EXPLOTADO": "A menos de 1 h de un destino consolidado y poco visible",
    "BARRERA_INFRAESTRUCTURA": "Especializado pero con caminos deficientes",
    "IMPACTO_SOCIAL": "Oportunidad en municipio de alta marginación",
}


@dataclass
class Supuestos:
    escenario: str = "tendencial"
    horizonte: int = 3
    monto_mdp: float = 500.0          # inversión simulada total (millones MXN)
    destino: str = "Municipios con flag"
    region: str | None = None
    promocion_pct: float = 30.0       # aumento de visibilidad por promoción
    enfoque: str = "Balanceado"
    actividades: list[str] = field(default_factory=list)


def _pct(s: pd.Series) -> pd.Series:
    return s.rank(pct=True, method="average").fillna(0)


def predecir(d: Datos, sp: Supuestos) -> pd.DataFrame:
    """Índice de oportunidad, crecimiento proyectado y flags por municipio × actividad."""
    m = d.municipios.set_index("cve_geo")
    t = d.mun_act.copy()
    if sp.actividades:
        t = t[t.actividad.isin(sp.actividades)]
    t = t.join(m[["nombre", "region", "poblacion", "indice_marginacion", "pct_via_pavimentada",
                  "min_a_ancla", "es_ancla", "es_pueblo_magico"]], on="cve_geo")

    t["s_oferta"] = _pct(np.log1p(t.personal_ocupado) * t.cociente_localizacion.clip(upper=4))
    t["s_visibilidad"] = _pct(t.menciones_10k)
    t["s_inversion"] = _pct(t.inversion_reciente_mdp / t.poblacion)
    t["s_accesibilidad"] = (1 - t.min_a_ancla / 240).clip(0, 1)
    t["s_social"] = t.indice_marginacion
    t["s_barrera"] = 1 - t.pct_via_pavimentada

    # Inversión y promoción adicionales según el escenario
    inv_extra = pd.Series(0.0, index=t.index)
    vis_extra = pd.Series(0.0, index=t.index)
    usa_inv_reciente = sp.escenario in ("inversion_reciente", "combinado")
    if sp.escenario in ("inversion_simulada", "combinado"):
        objetivo = _objetivo(t, sp)
        if objetivo.any():
            peso = t.personal_ocupado.where(objetivo, 0)
            inv_extra = sp.monto_mdp * peso / peso.sum()
    if sp.escenario in ("promocion", "combinado"):
        vis_extra = (sp.promocion_pct / 100) * (1 - t.s_visibilidad)

    # Modelo sustituto de crecimiento anual (demo; en producción: LightGBM del anillo A3)
    invisib = (1 - t.s_visibilidad)
    g = (
        0.012
        + 0.045 * t.s_oferta * invisib * 0.8
        + 0.015 * t.s_accesibilidad
        - 0.012 * t.s_barrera
        + 0.5 * t.crecimiento_hist.clip(-0.05, 0.08) * 0.4
    )
    if usa_inv_reciente:
        g += 0.012 * np.log1p(t.inversion_reciente_mdp) / np.log1p(50)
    g += 0.025 * np.log1p(inv_extra) / np.log1p(50)
    g += 0.06 * vis_extra * t.s_oferta
    t["crecimiento_anual"] = g.clip(-0.04, 0.25)
    h = sp.horizonte
    t["po_proyectado"] = t.personal_ocupado * (1 + t.crecimiento_anual) ** h
    banda = 0.012 + 0.008 * h
    t["po_p10"] = t.personal_ocupado * (1 + t.crecimiento_anual - banda) ** h
    t["po_p90"] = t.personal_ocupado * (1 + t.crecimiento_anual + banda) ** h
    t["inversion_simulada_mdp"] = inv_extra.round(1)

    t["s_crecimiento"] = _pct(t.crecimiento_anual)
    w = ENFOQUES[sp.enfoque]
    comp = {
        "Oferta (DENUE)": w[0] * t.s_oferta,
        "Crecimiento proyectado": w[1] * t.s_crecimiento,
        "Baja visibilidad": w[2] * (1 - t.s_visibilidad),
        "Accesibilidad": w[3] * t.s_accesibilidad,
        "Necesidad social": w[4] * t.s_social,
        "Barrera vial": -w[5] * t.s_barrera,
    }
    for k, v in comp.items():
        t[f"c::{k}"] = v
    t["indice_oportunidad"] = sum(comp.values()).clip(0, 1).round(3)

    # Flags
    alto_cl = t.cociente_localizacion >= 1.5
    alta_oferta = t.s_oferta >= 0.6
    baja_vis = t.s_visibilidad <= 0.35
    t["OFERTA_INVISIBLE"] = alto_cl & alta_oferta & baja_vis & ~t.es_ancla
    t["OFERTA_SIN_INVERSION"] = alto_cl & (t.s_oferta >= 0.75) & (t.inversion_reciente_mdp == 0)
    umbral_inv = t.inversion_reciente_mdp[t.inversion_reciente_mdp > 0].quantile(.6)
    t["INVERSION_SIN_RETORNO"] = (t.inversion_reciente_mdp >= umbral_inv) & (t.crecimiento_hist < 0.0)
    t["ACCESIBLE_NO_EXPLOTADO"] = (t.min_a_ancla <= 60) & baja_vis & (t.cociente_localizacion >= 1) & ~t.es_ancla
    t["BARRERA_INFRAESTRUCTURA"] = alto_cl & (t.pct_via_pavimentada < 0.5)
    t["IMPACTO_SOCIAL"] = (t.OFERTA_INVISIBLE | t.ACCESIBLE_NO_EXPLOTADO) & (t.indice_marginacion >= 0.6)
    t["num_flags"] = t[list(FLAGS)].sum(axis=1)
    t["flag_activo"] = t.OFERTA_INVISIBLE | t.ACCESIBLE_NO_EXPLOTADO | t.OFERTA_SIN_INVERSION
    return t


def _objetivo(t: pd.DataFrame, sp: Supuestos) -> pd.Series:
    if sp.destino == "Municipios con flag":
        return (t.cociente_localizacion >= 1.5) & (t.s_visibilidad <= 0.35) & ~t.es_ancla
    if sp.destino == "Región seleccionada" and sp.region:
        return t.region == sp.region
    if sp.destino == "Destinos consolidados":
        return t.es_ancla
    return pd.Series(True, index=t.index)


def por_municipio(d: Datos, pred: pd.DataFrame) -> pd.DataFrame:
    """Resume la predicción a nivel municipio (mejor actividad = actividad líder)."""
    act = d.actividades.set_index("clave")
    lider = pred.sort_values("indice_oportunidad", ascending=False).drop_duplicates("cve_geo")
    agg = pred.groupby("cve_geo").agg(
        po_actual=("personal_ocupado", "sum"),
        po_proyectado=("po_proyectado", "sum"),
        menciones=("menciones", "sum"),
        inversion_reciente_mdp=("inversion_reciente_mdp", "sum"),
        inversion_simulada_mdp=("inversion_simulada_mdp", "sum"),
        num_actividades=("actividad", "nunique"),
        num_flags=("num_flags", "sum"),
        flag_activo=("flag_activo", "any"),
    )
    agg["indice_oportunidad"] = lider.set_index("cve_geo").indice_oportunidad
    agg["actividad_lider"] = lider.set_index("cve_geo").actividad.map(act.nombre)
    agg["icono_lider"] = lider.set_index("cve_geo").actividad.map(act.icono)
    agg["crecimiento_pct"] = (agg.po_proyectado / agg.po_actual - 1) * 100
    out = d.municipios.set_index("cve_geo").join(agg)
    out["indice_oportunidad"] = out.indice_oportunidad.fillna(0)
    out["po_actual"] = out.po_actual.fillna(0)
    out["po_proyectado"] = out.po_proyectado.fillna(0)
    out["crecimiento_pct"] = out.crecimiento_pct.fillna(0)
    out["num_flags"] = out.num_flags.fillna(0).astype(int)
    out["flag_activo"] = out.flag_activo.astype("boolean").fillna(False).astype(bool)
    out["actividad_lider"] = out.actividad_lider.fillna("—")
    out["icono_lider"] = out.icono_lider.fillna("")
    return out.reset_index()


# --- Concentración / descentralización -----------------------------------------

def hhi(valores) -> float:
    v = np.asarray(valores, dtype=float)
    v = v[v > 0]
    if v.sum() == 0:
        return 0.0
    s = v / v.sum()
    return float((s ** 2).sum())


def lorenz(valores) -> tuple[np.ndarray, np.ndarray]:
    v = np.sort(np.asarray(valores, dtype=float))
    x = np.linspace(0, 1, len(v) + 1)
    y = np.concatenate([[0], np.cumsum(v) / v.sum()]) if v.sum() else x
    return x, y


def gini(valores) -> float:
    x, y = lorenz(valores)
    return float(1 - 2 * np.trapezoid(y, x))


def con_efecto_rutas(mpio: pd.DataFrame, rutas: list["Ruta"], impulso: float = 0.18) -> pd.Series:
    """Personal ocupado proyectado si se promueven las rutas propuestas."""
    po = mpio.set_index("cve_geo").po_proyectado.copy()
    for r in rutas:
        for p in r.paradas:
            if not p["es_ancla"]:
                po[p["cve_geo"]] *= 1 + impulso * r.score_norm
    return po


# --- Rutas intermunicipales (Orienteering Problem, heurística voraz + 2-opt) ----

@dataclass
class Ruta:
    nombre: str
    tema: str
    paradas: list[dict]
    minutos: float
    score: float
    score_norm: float = 0.0

    @property
    def municipios(self) -> list[str]:
        return [p["nombre"] for p in self.paradas]

    @property
    def emergentes(self) -> int:
        return sum(not p["es_ancla"] for p in self.paradas)


def _nodos(d: Datos, pred: pd.DataFrame) -> pd.DataFrame:
    act = d.actividades.set_index("clave")
    cand = pred[pred.cociente_localizacion >= 1.0]
    g = cand.sort_values("indice_oportunidad", ascending=False).groupby("cve_geo")
    n = g.agg(score=("indice_oportunidad", "max"), n_act=("actividad", "nunique"),
              flag=("flag_activo", "any"), social=("indice_marginacion", "first"))
    n["actividades"] = g.actividad.apply(list)
    n["score"] += 0.05 * (n.n_act.clip(upper=4) - 1)
    m = d.municipios.reset_index().set_index("cve_geo")
    n = n.join(m[["index", "nombre", "lat", "lon", "region", "es_ancla"]])
    n["iconos"] = n.actividades.apply(lambda a: "".join(act.icono[x] for x in a[:3]))
    return n.reset_index()


def proponer_rutas(d: Datos, pred: pd.DataFrame, dias: int = 2, region: str | None = None,
                   min_emergentes: int = 2, max_paradas: int = 6, top: int = 8) -> list[Ruta]:
    act = d.actividades.set_index("clave")
    nodos = _nodos(d, pred)
    if nodos.empty:
        return []
    presupuesto = dias * 9 * 60
    T = d.tiempos
    mun = d.municipios

    anclas = mun[mun.es_ancla]
    if region:
        nodos = nodos[(nodos.region == region) | nodos.es_ancla]
        locales = anclas[anclas.region == region]
        if locales.empty:
            centro = nodos[nodos.region == region][["lat", "lon"]].mean()
            dist = (anclas.lat - centro.lat) ** 2 + (anclas.lon - centro.lon) ** 2
            locales = anclas.loc[dist.nsmallest(2).index]
        anclas = locales

    rutas: list[Ruta] = []
    for _, a in anclas.iterrows():
        for variante in range(3):
            prohibidos = {r.paradas[1]["cve_geo"] for r in rutas
                          if r.paradas[0]["cve_geo"] == a.cve_geo and len(r.paradas) > 1} if variante else set()
            ruta = _construir(a, nodos, T, presupuesto, max_paradas, prohibidos)
            if ruta and sum(not p["es_ancla"] for p in ruta[0]) >= min_emergentes:
                paradas, minutos, score = ruta
                rutas.append(Ruta(_nombre(paradas, act), _tema(paradas, act), paradas, minutos, score))

    # Diversidad: primero la mejor ruta de cada ancla, luego el resto por score
    rutas.sort(key=lambda r: -r.score)
    mejores, vistas_ancla = [], set()
    for r in rutas:
        if r.paradas[0]["cve_geo"] not in vistas_ancla:
            vistas_ancla.add(r.paradas[0]["cve_geo"])
            mejores.append(r)
    rutas = mejores + [r for r in rutas if r not in mejores]

    vistas, unicas = set(), []
    for r in rutas:
        llave = frozenset(p["cve_geo"] for p in r.paradas)
        if llave not in vistas:
            vistas.add(llave)
            unicas.append(r)
    unicas = unicas[:top]
    if unicas:
        mx = max(r.score for r in unicas)
        for r in unicas:
            r.score_norm = round(r.score / mx, 3)
    return unicas


def _construir(ancla, nodos, T, presupuesto, max_paradas, prohibidos):
    estancia = lambda n: 180 if n.es_ancla else 150  # noqa: E731
    fila_ancla = nodos[nodos.cve_geo == ancla.cve_geo]
    inicio = fila_ancla.iloc[0] if not fila_ancla.empty else None
    actual_idx = int(ancla.name) if inicio is None else int(inicio["index"])
    paradas = [_parada(inicio, ancla, True)]
    usado = 180
    disponibles = nodos[(nodos.cve_geo != ancla.cve_geo) & ~nodos.cve_geo.isin(prohibidos) & ~nodos.es_ancla]
    elegidos = set()
    while len(paradas) < max_paradas:
        viaje = T[actual_idx, disponibles["index"].to_numpy()]
        costo = viaje + 150
        ok = (usado + costo <= presupuesto) & ~disponibles.cve_geo.isin(elegidos).to_numpy() & (viaje <= 150)
        if not ok.any():
            break
        valor = (disponibles.score.to_numpy() + 0.15 * disponibles.flag.to_numpy() + 0.1 * disponibles.social.to_numpy())
        ratio = np.where(ok, valor / (costo ** 0.6), -np.inf)
        k = int(np.argmax(ratio))
        n = disponibles.iloc[k]
        elegidos.add(n.cve_geo)
        usado += costo[k]
        actual_idx = int(n["index"])
        paradas.append(_parada(n, None, False, viaje[k]))
    if len(paradas) < 3:
        return None
    paradas = _dos_opt(paradas, T)
    minutos = sum(p["min_desde_anterior"] for p in paradas) + sum(180 if p["es_ancla"] else 150 for p in paradas)
    score = sum(p["score"] for p in paradas[1:]) + 0.1 * np.mean([p["social"] for p in paradas])
    return paradas, minutos, score


def _parada(n, ancla, es_ancla, viaje=0.0):
    if n is None:  # ancla sin actividades seleccionadas
        return dict(cve_geo=ancla.cve_geo, nombre=ancla.nombre, lat=ancla.lat, lon=ancla.lon, idx=int(ancla.name),
                    region=ancla.region, es_ancla=True, score=0.0, social=0.0, flag=False,
                    actividades=[], iconos="⚓", min_desde_anterior=0.0)
    return dict(cve_geo=n.cve_geo, nombre=n.nombre, lat=n.lat, lon=n.lon, idx=int(n["index"]), region=n.region,
                es_ancla=bool(es_ancla or n.es_ancla), score=float(n.score), social=float(n.social),
                flag=bool(n.flag), actividades=list(n.actividades), iconos=n.iconos,
                min_desde_anterior=float(viaje))


def _dos_opt(paradas, T):
    """Mejora el orden de las paradas (ruta abierta que inicia en el ancla)."""
    def largo(ps):
        return sum(T[a["idx"], b["idx"]] for a, b in zip(ps, ps[1:]))
    mejor, mejora = paradas, True
    while mejora:
        mejora = False
        for i in range(1, len(mejor) - 1):
            for j in range(i + 1, len(mejor)):
                nueva = mejor[:i] + mejor[i:j + 1][::-1] + mejor[j + 1:]
                if largo(nueva) + 1e-6 < largo(mejor):
                    mejor, mejora = nueva, True
    for k, p in enumerate(mejor):
        p["min_desde_anterior"] = 0.0 if k == 0 else float(T[mejor[k - 1]["idx"], p["idx"]])
    return mejor


def _tema(paradas, act) -> str:
    conteo = pd.Series([a for p in paradas for a in p["actividades"]]).value_counts()
    return conteo.index[0] if len(conteo) else "mixta"


def _nombre(paradas, act) -> str:
    conteo = pd.Series([a for p in paradas for a in p["actividades"]]).value_counts()
    regiones = pd.Series([p["region"] for p in paradas[1:]]).value_counts()
    region = regiones.index[0] if len(regiones) else paradas[0]["region"]
    if len(conteo) == 0:
        return f"Ruta · {region}"
    if len(conteo) == 1 or conteo.iloc[0] >= 0.6 * conteo.sum():
        return f"{act.ruta[conteo.index[0]]} · {region}"
    dos = " + ".join(act.corto[c] for c in conteo.index[:2])
    return f"Ruta Mixta: {dos} · {region}"


# --- Circuitos municipales -------------------------------------------------------

def circuito_municipal(d: Datos, cve_geo: str, actividades: list[str] | None,
                       horas: float = 6, variado: bool = True) -> pd.DataFrame:
    """Circuito dentro del municipio: vecino más cercano sobre puntos de interés."""
    mun = d.municipios.set_index("cve_geo").loc[cve_geo]
    p = d.poi[d.poi.cve_geo == cve_geo].copy()
    if actividades:
        p = p[p.actividad.isin(actividades)]
    if p.empty:
        return p
    if not variado:
        top = p.actividad.value_counts().index[0]
        p = p[p.actividad == top]
    p = p.sort_values("valoracion", ascending=False)

    actual = (mun.lat, mun.lon)
    restante, orden, usadas = horas * 60, [], {}
    pendientes = p.copy()
    while not pendientes.empty:
        dist = _km(actual[0], actual[1], pendientes.lat.to_numpy(), pendientes.lon.to_numpy())
        viaje = dist * 1.4 / 25 * 60
        if variado:  # alterna actividades para que el circuito sea diverso
            penal = pendientes.actividad.map(usadas).fillna(0).to_numpy() * 8
        else:
            penal = 0
        costo = viaje + 60
        ok = costo <= restante
        if not ok.any():
            break
        k = int(np.argmin(np.where(ok, viaje + penal, np.inf)))
        fila = pendientes.iloc[k].to_dict()
        fila["min_desde_anterior"] = float(viaje[k])
        orden.append(fila)
        restante -= costo[k]
        usadas[fila["actividad"]] = usadas.get(fila["actividad"], 0) + 1
        actual = (fila["lat"], fila["lon"])
        pendientes = pendientes.drop(pendientes.index[k])
    out = pd.DataFrame(orden)
    if not out.empty:
        out.insert(0, "orden", range(1, len(out) + 1))
    return out


def _km(lat1, lon1, lat2, lon2):
    r = 6371.0
    p1, p2 = np.radians(lat1), np.radians(lat2)
    a = np.sin((p2 - p1) / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(np.radians(lon2 - lon1) / 2) ** 2
    return 2 * r * np.arcsin(np.sqrt(a))


def ranking_circuitos(pred: pd.DataFrame, top: int = 15) -> pd.DataFrame:
    """Municipios con mejor potencial para circuitos (diversidad + oportunidad)."""
    g = pred.groupby(["cve_geo", "nombre", "region"]).agg(
        actividades=("actividad", "nunique"), indice=("indice_oportunidad", "mean"),
        flag=("flag_activo", "any")).reset_index()
    g["potencial"] = (0.6 * g.indice + 0.4 * (g.actividades.clip(upper=5) / 5)).round(3)
    return g.sort_values("potencial", ascending=False).head(top)
