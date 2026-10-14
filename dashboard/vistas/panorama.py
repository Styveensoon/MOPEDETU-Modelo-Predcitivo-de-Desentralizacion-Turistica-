import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

import estado
import mapas
import motor
import tema


def render():
    d = estado.datos()
    ctx = estado.contexto()
    pred, mp = estado.prediccion()
    rutas = estado.rutas() if "Rutas" in ctx.predecir else []

    tema.hero("MOPEDETU · Descentralización turística de Puebla",
              "¿Dónde está el turismo que nadie está viendo? Oportunidades, rutas y circuitos para los 217 municipios.",
              estado.chips())

    po_rutas = motor.con_efecto_rutas(mp, rutas)
    hhi_hoy, hhi_proy = motor.hhi(mp.po_actual) * 1e4, motor.hhi(po_rutas) * 1e4
    crec = (mp.po_proyectado.sum() / mp.po_actual.sum() - 1) * 100

    k = st.columns(5)
    k[0].metric("Municipios analizados", f"{len(mp)}", f"{mp.num_actividades.fillna(0).gt(0).sum()} con oferta turística",
                delta_color="off")
    k[1].metric("🚩 Oferta invisible", int(pred[pred.OFERTA_INVISIBLE].cve_geo.nunique()),
                "municipios con flag", delta_color="off")
    k[2].metric("🧭 Rutas propuestas", len(rutas),
                f"{len({p['cve_geo'] for r in rutas for p in r.paradas if not p['es_ancla']})} municipios emergentes",
                delta_color="off")
    k[3].metric("Concentración (HHI)", f"{hhi_hoy:,.0f}", f"{hhi_proy - hhi_hoy:,.0f} con rutas", delta_color="inverse",
                help="Índice Herfindahl-Hirschman del empleo turístico entre municipios (0-10,000). Menor = más descentralizado.")
    k[4].metric(f"Empleo turístico a {ctx.supuestos.horizonte} años", f"{mp.po_proyectado.sum():,.0f}", f"{crec:+.1f} %")

    izq, der = st.columns([1.65, 1])
    with izq:
        st.markdown("#### 🗺️ Índice de oportunidad turística")
        tt = mp.set_index("cve_geo").apply(
            lambda r: f"<b>{r.nombre}</b><br/>{r.region}<br/>Índice: <b>{r.indice_oportunidad:.2f}</b><br/>"
                      f"Líder: {r.icono_lider} {r.actividad_lider}<br/>Flags: {r.num_flags}"
                      + ("<br/>⚓ Destino consolidado" if r.es_ancla else ""), axis=1)
        fuera = set(mp.cve_geo) - set(estado.filtrar_region(mp).cve_geo)
        capas = [mapas.capa_municipios(d.geo, mp, "indice_oportunidad", tt, cuantiles=True, atenuar=fuera)]
        anclas = mp[mp.es_ancla].copy()
        anclas["tt"] = "<b>⚓ " + anclas.nombre + "</b><br/>Destino consolidado"
        if rutas:
            capas.append(mapas.capa_arcos(_arcos(rutas)))
        capas.append(mapas.capa_puntos(anclas, [14, 42, 92, 255], 2800))
        destacados = set(anclas.cve_geo) | set(estado.filtrar_region(mp[~mp.es_ancla]).nlargest(5, "indice_oportunidad").cve_geo)
        capas += mapas.capas_nombres(mp, destacados)
        st.pydeck_chart(mapas.deck(capas), height=600)
        mapas.leyenda("Índice de oportunidad (percentil estatal)", "bajo", "alto")

    with der:
        st.markdown("#### 🌱 Top municipios emergentes")
        top = estado.filtrar_region(mp[~mp.es_ancla]).nlargest(10, "indice_oportunidad")
        fig = px.bar(top.iloc[::-1], x="indice_oportunidad", y="nombre", orientation="h",
                     color="indice_oportunidad", color_continuous_scale=tema.PLOTLY_SEQ[1:],
                     hover_data={"actividad_lider": True, "region": True},
                     text=top.iloc[::-1].icono_lider)
        fig.update_layout(height=330, margin=dict(l=0, r=0, t=0, b=0), coloraxis_showscale=False,
                          xaxis_title=None, yaxis_title=None)
        fig.update_traces(textposition="inside")
        st.plotly_chart(fig)

        st.markdown("#### ⚖️ ¿Qué tan concentrado está el turismo?")
        x0, y0 = motor.lorenz(mp.po_actual)
        x1, y1 = motor.lorenz(po_rutas)
        f2 = go.Figure()
        f2.add_trace(go.Scatter(x=x0, y=x0, line=dict(color="#999", dash="dot"), name="Igualdad"))
        f2.add_trace(go.Scatter(x=x0, y=y0, line=dict(color=tema.GUINDA, width=3), name=f"Hoy (Gini {motor.gini(mp.po_actual):.2f})"))
        f2.add_trace(go.Scatter(x=x1, y=y1, line=dict(color=tema.COBALTO, width=3),
                                name=f"Con rutas (Gini {motor.gini(po_rutas):.2f})", fill="tonexty",
                                fillcolor="rgba(27,63,139,.12)"))
        f2.update_layout(height=230, margin=dict(l=0, r=0, t=0, b=0), legend=dict(orientation="h", y=-0.25),
                         xaxis_title="% acumulado de municipios", yaxis_title="% del empleo")
        st.plotly_chart(f2)

    a, b = st.columns([1, 1])
    with a:
        st.markdown("#### 🧩 Oportunidad por región y actividad")
        tm = pred.groupby(["region", "actividad"]).indice_oportunidad.mean().reset_index()
        tm["actividad"] = tm.actividad.map(d.actividades.set_index("clave").nombre)
        tm["peso"] = pred.groupby(["region", "actividad"]).personal_ocupado.sum().to_numpy()
        fig = px.treemap(tm, path=["region", "actividad"], values="peso", color="indice_oportunidad",
                         color_continuous_scale=tema.PLOTLY_SEQ)
        fig.update_layout(height=360, margin=dict(l=0, r=0, t=0, b=0))
        st.plotly_chart(fig)
    with b:
        st.markdown("#### 📈 Empleo turístico: hoy vs. proyectado por región")
        reg = mp.groupby("region")[["po_actual", "po_proyectado"]].sum().reset_index()
        reg["con rutas"] = mp.assign(r=mp.cve_geo.map(po_rutas)).groupby("region").r.sum().to_numpy()
        reg = reg.rename(columns={"po_actual": "Hoy", "po_proyectado": "Proyectado"})
        largo = reg.melt("region", var_name="Serie", value_name="Personal ocupado")
        fig = px.bar(largo, x="Personal ocupado", y="region", color="Serie", barmode="group", orientation="h",
                     color_discrete_sequence=["#B0BEC5", tema.AMARILLO, tema.COBALTO], log_x=True)
        fig.update_layout(height=360, margin=dict(l=0, r=0, t=0, b=0), yaxis_title=None,
                          legend=dict(orientation="h", y=-0.15))
        st.plotly_chart(fig)


def _arcos(rutas) -> pd.DataFrame:
    filas = []
    for r in rutas:
        for a, b in zip(r.paradas, r.paradas[1:]):
            filas.append(dict(lon_a=a["lon"], lat_a=a["lat"], lon_b=b["lon"], lat_b=b["lat"],
                              color_a=[14, 42, 92, 230], color_b=[232, 177, 13, 240],
                              ancho=2 + 4 * r.score_norm,
                              tt=f"<b>{r.nombre}</b><br/>{a['nombre']} → {b['nombre']}<br/>{b['min_desde_anterior']:.0f} min"))
    return pd.DataFrame(filas)
