import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import estado
import mapas
import motor
import tema


def render():
    d = estado.datos()
    ctx = estado.contexto()
    act = d.actividades.set_index("clave")
    pred, mp = estado.prediccion()

    nombres = dict(zip(mp.cve_geo, mp.nombre))
    orden = mp.sort_values("indice_oportunidad", ascending=False).cve_geo.tolist()
    defecto = st.session_state.get("ficha_cve", orden[0])
    cve = st.selectbox("🔎 Buscar municipio", orden, index=orden.index(defecto), format_func=nombres.get)
    st.session_state["ficha_cve"] = cve
    m = mp.set_index("cve_geo").loc[cve]
    filas = pred[pred.cve_geo == cve].sort_values("indice_oportunidad", ascending=False)

    etiquetas = []
    if m.es_ancla:
        etiquetas.append("⚓ Destino consolidado")
    if m.es_pueblo_magico:
        etiquetas.append("✨ Pueblo Mágico")
    tema.hero(f"🏘️ {m.nombre}", f"{m.region} · Clave INEGI {cve} · {m.poblacion:,.0f} habitantes",
              etiquetas + [f"Marginación {m.grado_marginacion.lower()}"])

    k = st.columns(5)
    rank = orden.index(cve) + 1
    k[0].metric("Índice de oportunidad", f"{m.indice_oportunidad:.2f}", f"#{rank} de {len(orden)}", delta_color="off")
    k[1].metric("Personal ocupado turístico", f"{m.po_actual:,.0f}")
    k[2].metric(f"Proyección a {ctx.supuestos.horizonte} años", f"{m.po_proyectado:,.0f}", f"{m.crecimiento_pct:+.1f} %")
    k[3].metric("A un destino ancla", f"{m.min_a_ancla:.0f} min")
    k[4].metric("Inversión reciente", f"{m.inversion_reciente_mdp:,.1f} MDP")

    if filas.empty:
        st.info("Este municipio no tiene oferta registrada en las actividades seleccionadas.")
        return

    a, b = st.columns([1, 1])
    with a:
        st.markdown("#### 🎯 Actividades y predominancia")
        fig = go.Figure(go.Bar(
            x=filas.cociente_localizacion, y=[f"{act.icono[x]} {act.nombre[x]}" for x in filas.actividad],
            orientation="h", marker_color=[tema.GUINDA if f else tema.COBALTO for f in filas.flag_activo],
            text=[f"CL {v:.1f} · {n}" for v, n in zip(filas.cociente_localizacion, filas.nivel_predominancia)],
            textposition="auto"))
        fig.add_vline(x=1, line_dash="dot", line_color="#888")
        fig.update_layout(height=60 + 42 * len(filas), margin=dict(l=0, r=0, t=0, b=0),
                          xaxis_title="Cociente de localización (1 = promedio estatal)", yaxis=dict(autorange="reversed"))
        st.plotly_chart(fig)
        st.caption("Guinda = actividad con flag de oportunidad.")

    with b:
        lider = filas.iloc[0]
        st.markdown(f"#### 🧠 ¿Por qué? · {act.icono[lider.actividad]} {act.nombre[lider.actividad]}")
        comp = {k[3:]: lider[k] for k in filas.columns if k.startswith("c::")}
        orden_c = sorted(comp.items(), key=lambda x: x[1])
        fig = go.Figure(go.Waterfall(
            orientation="h", y=[k for k, _ in orden_c] + ["Índice"], x=[v for _, v in orden_c] + [0],
            measure=["relative"] * len(orden_c) + ["total"],
            increasing=dict(marker=dict(color=tema.COBALTO)), decreasing=dict(marker=dict(color=tema.GUINDA)),
            totals=dict(marker=dict(color=tema.AMARILLO)), text=[f"{v:+.2f}" for _, v in orden_c] + [f"{lider.indice_oportunidad:.2f}"]))
        fig.update_layout(height=320, margin=dict(l=0, r=0, t=0, b=0))
        st.plotly_chart(fig)
        st.caption(f"Contribución de cada factor al índice con enfoque **{ctx.supuestos.enfoque}**. "
                   "En producción se reemplaza por valores SHAP del modelo.")

    c, e = st.columns([1, 1])
    with c:
        st.markdown("#### 🚩 Flags detectados")
        hay = False
        for f in filas.itertuples():
            activos = [k for k in motor.FLAGS if getattr(f, k)]
            if activos:
                hay = True
                tags = "".join(f'<span class="mope-tag flag" title="{motor.FLAGS[k]}">{k.replace("_", " ")}</span>'
                               for k in activos)
                st.markdown(f'<div class="mope-card"><b>{act.icono[f.actividad]} {act.nombre[f.actividad]}</b>'
                            f'<div style="margin-top:6px;line-height:2">{tags}</div></div>', unsafe_allow_html=True)
        if hay:
            st.caption("Pasa el cursor sobre una etiqueta para ver qué significa.")
        else:
            st.success("Sin alertas para este municipio.")

        st.markdown("#### 🧭 Aparece en estas rutas")
        rutas = [r for r in estado.rutas() if cve in {p["cve_geo"] for p in r.paradas}] if "Rutas" in ctx.predecir else []
        if rutas:
            for r in rutas:
                st.markdown(f"- **{r.nombre}**: {' → '.join(r.municipios)}")
        else:
            st.caption("No forma parte de las rutas propuestas con la configuración actual.")

    with e:
        st.markdown("#### 📈 Proyección del empleo turístico")
        anios = np.arange(0, ctx.supuestos.horizonte + 1)
        fig = go.Figure()
        for f in filas.head(4).itertuples():
            y = f.personal_ocupado * (1 + f.crecimiento_anual) ** anios
            banda = 0.012 + 0.008 * anios
            lo = f.personal_ocupado * (1 + f.crecimiento_anual - banda) ** anios
            hi = f.personal_ocupado * (1 + f.crecimiento_anual + banda) ** anios
            color = act.color[f.actividad]
            fig.add_trace(go.Scatter(x=np.r_[anios, anios[::-1]], y=np.r_[hi, lo[::-1]], fill="toself", mode="lines",
                                     fillcolor=f"rgba({color[0]},{color[1]},{color[2]},.15)", line=dict(width=0),
                                     showlegend=False, hoverinfo="skip"))
            fig.add_trace(go.Scatter(x=anios, y=y, mode="lines+markers", name=f"{act.icono[f.actividad]} {act.corto[f.actividad]}",
                                     line=dict(color=f"rgb({color[0]},{color[1]},{color[2]})", width=3)))
        fig.update_layout(height=320, margin=dict(l=0, r=0, t=0, b=0), xaxis_title="Años",
                          yaxis_title="Personal ocupado", legend=dict(orientation="h", y=-0.25))
        st.plotly_chart(fig)

    vecinos = mp[(np.abs(mp.lat - m.lat) < 0.35) & (np.abs(mp.lon - m.lon) < 0.35)]
    tt = mp.set_index("cve_geo").apply(lambda r: f"<b>{r.nombre}</b><br/>Índice {r.indice_oportunidad:.2f}", axis=1)
    capas = [mapas.capa_municipios(d.geo, mp, "indice_oportunidad", tt, cuantiles=True, resaltar={cve},
                                   atenuar=set(mp.cve_geo) - set(vecinos.cve_geo)),
             mapas.capa_texto(vecinos, "nombre", 11, offset=(0, 0))]
    st.markdown("#### 📍 Ubicación y vecinos")
    st.pydeck_chart(mapas.deck(capas, mapas.vista_ajustada([m.lat - 0.3, m.lat + 0.3], [m.lon - 0.5, m.lon + 0.5], 1300, 380, margen=1.0)),
                    height=380)

    st.download_button("⬇️ Descargar ficha (CSV)", filas.drop(columns=[c for c in filas if c.startswith("c::")])
                       .to_csv(index=False).encode("utf-8-sig"), f"ficha_{cve}.csv", "text/csv")
