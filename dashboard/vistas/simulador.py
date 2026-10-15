import dataclasses

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
import streamlit as st

import estado
import mapas
import motor
import tema
from datos import REGIONES


def render():
    d = estado.datos()
    ctx = estado.contexto()

    tema.hero("🔮 Simulador de escenarios",
              "¿Qué pasa si invertimos y promovemos en otro lugar? Compara el escenario tendencial contra tu propuesta.",
              estado.chips())

    with st.container(border=True):
        c = st.columns([1.2, 1.3, 1.2, 1, 1])
        monto = c[0].slider("💰 Inversión (millones MXN)", 0, 3000, 600, 50)
        destino = c[1].selectbox("¿A dónde va la inversión?", ["Municipios con flag", "Región seleccionada",
                                                                "Destinos consolidados", "Todos"])
        region = c[2].selectbox("Región objetivo", REGIONES, index=REGIONES.index("Sierra Nororiental"),
                                disabled=destino != "Región seleccionada")
        promo = c[3].slider("📣 Promoción (+% visibilidad)", 0, 100, 40, 5)
        horizonte = c[4].segmented_control("Años", [1, 3, 5], default=5, key="sim_h") or 5

    base_sp = dataclasses.replace(ctx.supuestos, escenario="tendencial", horizonte=horizonte, region=None)
    sim_sp = dataclasses.replace(base_sp, escenario="combinado", monto_mdp=float(monto), destino=destino,
                                 region=region if destino == "Región seleccionada" else None,
                                 promocion_pct=float(promo))
    _, base = estado.prediccion(base_sp)
    _, sim = estado.prediccion(sim_sp)

    df = base[["cve_geo", "nombre", "region", "lat", "lon", "po_actual", "po_proyectado"]].merge(
        sim[["cve_geo", "po_proyectado", "inversion_simulada_mdp"]], on="cve_geo", suffixes=("_base", "_sim"))
    df["delta"] = df.po_proyectado_sim - df.po_proyectado_base
    df["delta_pct"] = np.where(df.po_proyectado_base > 0, df.delta / df.po_proyectado_base * 100, 0)

    extra = df.delta.sum()
    hhi_b, hhi_s = motor.hhi(df.po_proyectado_base) * 1e4, motor.hhi(df.po_proyectado_sim) * 1e4
    k = st.columns(5)
    k[0].metric("Empleos turísticos adicionales", f"{extra:,.0f}", f"en {horizonte} años", delta_color="off")
    k[1].metric("Municipios beneficiados", int((df.delta_pct > 1).sum()), "con +1 % o más", delta_color="off")
    k[2].metric("Empleos por cada 10 MDP", f"{extra / max(monto, 1) * 10:,.1f}" if monto else "—",
                help="Incluye el efecto conjunto de inversión y promoción.")
    k[3].metric("Concentración (HHI)", f"{hhi_s:,.0f}", f"{hhi_s - hhi_b:,.0f} vs. tendencial", delta_color="inverse")
    fuera = df[~df.cve_geo.isin(d.municipios[d.municipios.es_ancla].cve_geo)].delta.sum()
    k[4].metric("Beneficio fuera de destinos ancla", f"{fuera / extra * 100 if extra else 0:.0f} %")

    izq, der = st.columns([1.5, 1])
    with izq:
        st.markdown("#### 🗺️ Cambio en empleo turístico vs. tendencial")
        df["tt"] = df.apply(lambda r: f"<b>{r.nombre}</b><br/>Tendencial: {r.po_proyectado_base:,.0f}<br/>"
                                      f"Simulado: {r.po_proyectado_sim:,.0f}<br/><b>{r.delta_pct:+.1f} %</b>"
                                      f"<br/>Inversión: {r.inversion_simulada_mdp:,.1f} MDP", axis=1)
        tope = max(df.delta_pct.quantile(.97), 1)
        m = mapas.Mapa(d.geo, alto=600, fondo=mapas.FONDO_ESTADO).municipios(df, "delta_pct", df.set_index("cve_geo").tt,
                                                   paleta=tema.SEQ_CRECIMIENTO, vmin=0, vmax=tope)
        m.nombres(df.nlargest(10, "delta_pct"), tamano=10)
        mapas.mostrar(m, "sim_mapa")
        mapas.leyenda("Cambio porcentual contra el escenario tendencial", "0 %", f"+{tope:.0f} %", tema.SEQ_CRECIMIENTO)

    with der:
        st.markdown("#### 📈 Trayectoria estatal")
        anios = list(range(0, horizonte + 1))
        traj = {}
        for nombre, sp in (("Tendencial", base_sp), ("Simulado", sim_sp)):
            serie = []
            for h in anios:
                _, m = estado.prediccion(dataclasses.replace(sp, horizonte=max(h, 1)))
                serie.append(m.po_actual.sum() if h == 0 else m.po_proyectado.sum())
            traj[nombre] = serie
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=anios, y=traj["Tendencial"], name="Tendencial", line=dict(color="#90A4AE", width=3)))
        fig.add_trace(go.Scatter(x=anios, y=traj["Simulado"], name="Simulado", fill="tonexty",
                                 fillcolor="rgba(232,177,13,.25)", line=dict(color=tema.COBALTO, width=4)))
        fig.update_layout(height=240, margin=dict(l=0, r=0, t=0, b=0), xaxis_title="Años",
                          yaxis_title="Personal ocupado", legend=dict(orientation="h", y=-0.3))
        st.plotly_chart(fig)

        st.markdown("#### 🌱 Municipios que más ganan")
        top = df.nlargest(10, "delta")
        fig = px.bar(top.iloc[::-1], x="delta", y="nombre", orientation="h", color="region",
                     color_discrete_map=tema.REGION_COLORES, text=top.iloc[::-1].delta_pct.map("{:+.0f} %".format))
        fig.update_layout(height=300, margin=dict(l=0, r=0, t=0, b=0), xaxis_title="Empleos adicionales",
                          yaxis_title=None, showlegend=False)
        st.plotly_chart(fig)

    st.caption("⚠️ Escenario **estimado** con base en correlaciones (modelo sustituto en modo demo). "
               "No demuestra causalidad; sirve para comparar alternativas de política pública.")
