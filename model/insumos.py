"""Insumos de las reglas de rutas y circuitos, con cualquier llave (plan_migracion_front.md §4.1).

El pipeline los carga con la secret key (`cargar(secreta=True)`) y el tablero con la publishable key: es la MISMA
estructura, así que "Arma tu ruta" y el optimizador del modelo aplican exactamente las mismas reglas.
Todo sale de dw y de la configuración vigente (dw.v_vigente); nada está escrito a mano aquí.
"""
from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

RAIZ = Path(__file__).resolve().parent.parent
if str(RAIZ / "dashboard") not in sys.path:
    sys.path.insert(0, str(RAIZ / "dashboard"))

import supabase_cliente as sb  # noqa: E402

FUERTES = ["muy_alta", "alta", "reconocida", "reconocida_sin_registro"]


def pct(s: pd.Series) -> pd.Series:
    """Percentil en [0, 1]; NaN → 0.5 (igual que model/base.py)."""
    return s.rank(pct=True, method="average").fillna(0.5)


@dataclass
class Insumos:
    mun: pd.DataFrame                 # índice municipio_sk: nombre, región, ancla, PM, cabecera, marginación
    version_indice: str
    version_indice_sk: int
    pesos: dict                       # pesos del índice vigente
    parametros: dict                  # parámetros del optimizador (dim_version_calculo)
    indice: pd.DataFrame              # mejor eje por municipio (índice vigente), índice municipio_sk
    banderas: pd.DataFrame            # activas de la versión vigente, con 'codigo'
    presente: dict                    # tema → set(municipio_sk) con presencia fuerte
    pred: pd.DataFrame                # predicción del modelo vigente, solo en dominio
    pe_pct: dict                      # (a, b) → percentil de la probabilidad de enlace (simétrica)
    tiempo: dict                      # (a, b) → minutos de flujo libre (OSRM)
    tiempo_plan: dict                 # (a, b) → minutos de planeación (con margen por región)
    distancia: dict                   # (a, b) → km por carretera
    hospedaje: pd.Series              # unidades de hospedaje DENUE por municipio
    infra_rojo: set                   # municipios con semáforo de infraestructura rojo
    visitables: set                   # municipios con ≥ 1 punto atractivo/experiencia
    social: pd.Series                 # pct(−índice de marginación)
    meses_fuertes: pd.DataFrame       # 12 columnas 0/1 por municipio
    tramos_oficiales: set             # frozenset({a, b}) de las rutas oficiales
    anclas: list = field(default_factory=list)


def _leer(t: str, sel: str = "*", secreta: bool = False, filtro: str = "") -> pd.DataFrame:
    return sb.leer(t, "dw", sel, secreta=secreta, filtro=filtro)


def meses_fuertes(mun_idx, temporadas: pd.DataFrame, actividades: pd.DataFrame) -> pd.DataFrame:
    """Misma regla que model/enlaces.py::meses_fuertes: eventos propios (intensidad ≥ 2) y temporadas de sus
    actividades principales."""
    principales = actividades[actividades.es_principal][["municipio_sk", "actividad_sk"]]
    out = pd.DataFrame(0, index=mun_idx, columns=range(1, 13))

    def rango(i, f):
        return list(range(i, f + 1)) if i <= f else list(range(i, 13)) + list(range(1, f + 1))
    t = temporadas
    for r in t[t.municipio_sk.notna() & (t.intensidad >= 2)].itertuples():
        out.loc[int(r.municipio_sk), rango(int(r.mes_inicio), int(r.mes_fin))] = 1
    for r in t[t.municipio_sk.isna() & t.actividad_sk.notna()].itertuples():
        for mk in principales[principales.actividad_sk == r.actividad_sk].municipio_sk:
            out.loc[mk, rango(int(r.mes_inicio), int(r.mes_fin))] = 1
    return out


def cargar(secreta: bool = False) -> Insumos:
    vig = _leer("v_vigente", secreta=secreta).iloc[0]
    v = int(vig.version_indice_sk)

    mun = _leer("dim_municipio", "municipio_sk,cve_geo,nombre,region,es_ancla,es_pueblo_magico,cabecera_nombre,"
                                 "cabecera_lat,cabecera_lon", secreta).set_index("municipio_sk").sort_index()
    mun["cve_geo"] = mun.cve_geo.str.strip()
    soc = _leer("fact_contexto_social", "municipio_sk,indice_marginacion,grado_marginacion", secreta)
    mun = mun.join(soc.set_index("municipio_sk"))

    idx = _leer("fact_indice_oportunidad", "*", secreta, f"version_sk=eq.{v}")
    mejor = idx.loc[idx.groupby("municipio_sk").indice_oportunidad.idxmax()].set_index("municipio_sk")
    tipos = _leer("dim_tipo_flag", "tipo_flag_sk,codigo", secreta)
    ban = _leer("fact_flag_oportunidad", "*", secreta, f"version_sk=eq.{v}")
    ban = ban[ban.flag_activo.astype(bool)].merge(tipos, on="tipo_flag_sk")

    act = _leer("fact_actividad_municipio", "municipio_sk,actividad_sk,nivel_predominancia,es_principal", secreta)
    cat = _leer("dim_actividad", "actividad_sk,codigo", secreta)
    act = act.merge(cat, on="actividad_sk")
    presente = act[act.nivel_predominancia.isin(FUERTES)].groupby("codigo").municipio_sk.apply(set).to_dict()

    pred = _leer("fact_prediccion_crecimiento", "municipio_sk,eje_sk,crecimiento_pred_pct,en_dominio", secreta,
                 f"modelo_sk=eq.{int(vig.modelo_sk)}")
    pred = pred[pred.en_dominio.astype(bool)]

    enl = _leer("fact_prediccion_enlace", "municipio_a_sk,municipio_b_sk,probabilidad", secreta)
    p_enl = {}
    for r in enl.itertuples():
        p_enl[(r.municipio_a_sk, r.municipio_b_sk)] = p_enl[(r.municipio_b_sk, r.municipio_a_sk)] = r.probabilidad
    pe_pct = pd.Series(p_enl).rank(pct=True).to_dict()  # la probabilidad cruda es muy baja (tasa base del 1 %)

    t = sb.leer_por_bloques("v_tiempo_municipios", "municipio_origen_sk", list(mun.index), "dw",
                            "municipio_origen_sk,municipio_destino_sk,tiempo_min,tiempo_min_planeacion,distancia_km",
                            secreta).set_index(["municipio_origen_sk", "municipio_destino_sk"])

    infra = _leer("fact_infraestructura", "municipio_sk,indicador,valor", secreta, "indicador=eq.unidades_hospedaje")
    hosp = infra.set_index("municipio_sk").valor.astype(float).reindex(mun.index).fillna(0)
    sem = _leer("fact_semaforo_municipio", "municipio_sk,dimension,nivel,version_sk", secreta,
                f"version_sk=eq.{int(vig.semaforos_sk)}")
    infra_rojo = set(sem[(sem.dimension == "infraestructura") & (sem.nivel == "rojo")].municipio_sk)
    lug = _leer("v_lugar_circuito", "municipio_sk", secreta, "tipo_parada=in.(atractivo,experiencia)")
    visitables = set(lug.municipio_sk)

    temp = _leer("fact_temporada", "municipio_sk,actividad_sk,intensidad,mes_inicio,mes_fin", secreta)
    rutas = _leer("v_ruta_parada", "ruta_sk,origen,orden_parada,municipio_sk", secreta)
    oficiales = set()
    for _, g in rutas[rutas.origen == "existente"].sort_values("orden_parada").groupby("ruta_sk"):
        ms = g.municipio_sk.tolist()
        oficiales |= {frozenset(x) for x in zip(ms, ms[1:])}

    return Insumos(
        mun=mun, version_indice=vig.version_indice, version_indice_sk=v, pesos=vig.pesos_indice,
        parametros=vig.parametros_rutas, indice=mejor, banderas=ban, presente=presente, pred=pred, pe_pct=pe_pct,
        tiempo=t.tiempo_min.astype(float).to_dict(), tiempo_plan=t.tiempo_min_planeacion.astype(float).to_dict(),
        distancia=t.distancia_km.astype(float).to_dict(), hospedaje=hosp, infra_rojo=infra_rojo,
        visitables=visitables, social=pct(-mun.indice_marginacion.astype(float)),
        meses_fuertes=meses_fuertes(mun.index, temp, act), tramos_oficiales=oficiales,
        anclas=list(mun[mun.es_ancla.astype(bool)].index))
