"""Estado compartido: datos en caché, barra lateral global y resultados calculados."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd
import streamlit as st

import motor
from datos import REGIONES, Datos, cargar_datos


@st.cache_resource(show_spinner="Cargando municipios de Puebla…")
def datos() -> Datos:
    return cargar_datos()


@dataclass
class Contexto:
    modo: str
    predecir: list[str]
    supuestos: motor.Supuestos
    dias: int
    min_emergentes: int


def barra_lateral() -> Contexto:
    d = datos()
    act = d.actividades
    sb = st.sidebar
    sb.markdown("### 🧭 Configuración")
    modo = sb.segmented_control("Modo", ["General", "Concreto"], default="General", key="modo",
                                width="stretch") or "General"

    if modo == "General":
        sb.caption("Predicción general: todas las actividades, rutas y circuitos, "
                   "escenario tendencial a 3 años y enfoque balanceado.")
        horizonte = sb.segmented_control("Horizonte (años)", [1, 3, 5], default=3, key="hz_g") or 3
        ctx = Contexto(modo, ["Rutas", "Circuitos"], motor.Supuestos(horizonte=horizonte), 2, 2)
    else:
        predecir = sb.pills("¿Qué quiero predecir?", ["Rutas", "Circuitos"], selection_mode="multi",
                            default=["Rutas", "Circuitos"], key="predecir") or ["Rutas"]
        alcance = sb.radio("Actividades", ["Una", "Varias", "Todas"], index=1, horizontal=True, key="alcance")
        opciones = act.clave.tolist()
        fmt = dict(zip(act.clave, act.icono + " " + act.nombre)).get
        if alcance == "Una":
            elegidas = [sb.selectbox("Actividad", opciones, format_func=fmt, key="act_una")]
        elif alcance == "Varias":
            elegidas = sb.multiselect("Actividades", opciones, default=["cafe", "ecoturismo", "mezcal"],
                                      format_func=fmt, key="act_varias") or opciones
        else:
            elegidas = []

        escenario = sb.selectbox("Escenario", list(motor.ESCENARIOS), format_func=motor.ESCENARIOS.get,
                                 key="escenario")
        monto, destino, promo = 500.0, "Municipios con flag", 30.0
        region = sb.selectbox("Región", ["Todas"] + REGIONES, key="region")
        region = None if region == "Todas" else region
        if escenario in ("inversion_simulada", "combinado"):
            with sb.expander("💰 Supuestos de inversión", expanded=True):
                monto = st.slider("Monto (millones MXN)", 50, 3000, 500, 50, key="monto")
                destino = st.selectbox("¿A dónde va?", ["Municipios con flag", "Región seleccionada",
                                                        "Destinos consolidados", "Todos"], key="destino")
        if escenario in ("promocion", "combinado"):
            promo = sb.slider("📣 Aumento de visibilidad por promoción (%)", 0, 100, 30, 5, key="promo")
        horizonte = sb.segmented_control("Horizonte (años)", [1, 3, 5], default=3, key="hz_c") or 3
        enfoque = sb.select_slider("Enfoque del índice", list(motor.ENFOQUES), value="Balanceado", key="enfoque")
        dias = sb.slider("Duración máxima de ruta (días)", 1, 4, 2, key="dias")
        min_em = sb.slider("Mínimo de municipios emergentes por ruta", 1, 4, 2, key="min_em")
        ctx = Contexto(modo, predecir, motor.Supuestos(
            escenario=escenario, horizonte=horizonte, monto_mdp=float(monto), destino=destino,
            region=region, promocion_pct=float(promo), enfoque=enfoque, actividades=elegidas), dias, min_em)

    sb.divider()
    sb.markdown('<span class="mope-demo">⚠️ Datos DEMO simulados sobre los 217 municipios reales</span>',
                unsafe_allow_html=True)
    st.session_state["ctx"] = ctx
    return ctx


def contexto() -> Contexto:
    return st.session_state["ctx"]


def _llave(sp: motor.Supuestos) -> tuple:
    return (sp.escenario, sp.horizonte, sp.monto_mdp, sp.destino, sp.region, sp.promocion_pct,
            sp.enfoque, tuple(sp.actividades))


@st.cache_data(show_spinner=False, max_entries=64)
def _prediccion(llave: tuple) -> tuple[pd.DataFrame, pd.DataFrame]:
    sp = motor.Supuestos(*llave[:-1], actividades=list(llave[-1]))
    d = datos()
    pred = motor.predecir(d, sp)
    return pred, motor.por_municipio(d, pred)


def prediccion(sp: motor.Supuestos | None = None) -> tuple[pd.DataFrame, pd.DataFrame]:
    sp = sp or contexto().supuestos
    return _prediccion(_llave(sp))


@st.cache_data(show_spinner="Optimizando rutas…", max_entries=64)
def _rutas(llave: tuple, dias: int, region: str | None, min_em: int) -> list[motor.Ruta]:
    pred, _ = _prediccion(llave)
    return motor.proponer_rutas(datos(), pred, dias=dias, region=region, min_emergentes=min_em)


def rutas(ctx: Contexto | None = None) -> list[motor.Ruta]:
    ctx = ctx or contexto()
    sp = ctx.supuestos
    return _rutas(_llave(sp), ctx.dias, sp.region, ctx.min_emergentes)


def filtrar_region(df: pd.DataFrame) -> pd.DataFrame:
    r = contexto().supuestos.region
    return df if r is None else df[df.region == r]


def chips() -> list[str]:
    ctx = contexto()
    sp = ctx.supuestos
    act = datos().actividades.set_index("clave")
    acts = "Todas las actividades" if not sp.actividades else (
        ", ".join(act.icono[a] + " " + act.corto[a] for a in sp.actividades[:4])
        + ("…" if len(sp.actividades) > 4 else ""))
    return [f"Modo {ctx.modo}", motor.ESCENARIOS[sp.escenario], f"Horizonte {sp.horizonte} años",
            sp.region or "Todo el estado", acts, f"Enfoque {sp.enfoque}"]
