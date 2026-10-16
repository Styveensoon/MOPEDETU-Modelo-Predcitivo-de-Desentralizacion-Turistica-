"""▶️ Recorrido de presentación: cinco pasos, cada uno con datos reales de la base (plan_migracion_front §12.7)."""
import pandas as pd
import plotly.express as px
import streamlit as st

import bd
import ficha_bd as fb
import mapas
import tema

PASOS = ["1 · El problema", "2 · Dónde está la oportunidad", "3 · Una ruta nueva", "4 · Un municipio a fondo",
         "5 · Cómo sabemos que funciona"]


def render():
    try:
        vig, conc, esc, idx, rutas, val = (bd.vigente(), bd.concentracion(), bd.escenarios(), bd.indice_municipio(),
                                           bd.rutas(), bd.validaciones())
    except bd.SinDatos as e:
        st.error(f"No se pudieron leer los datos: {e}")
        return
    paso = st.session_state.get("pres_paso", 0)
    tema.hero("MOPEDETU · Descentralización turística de Puebla",
              "Recorrido de presentación con datos reales de Supabase.", [PASOS[paso]])
    elegido = st.segmented_control("Paso", PASOS, default=PASOS[paso], key=f"pres_sel_{paso}",
                                   label_visibility="collapsed")
    if elegido and PASOS.index(elegido) != paso:
        st.session_state["pres_paso"] = PASOS.index(elegido)
        st.rerun()

    c = conc.set_index("eje_sk")
    if paso == 0:
        st.markdown(f"## El top 5 tiene el **{float(c.pct_top5_poblacion.iloc[0]):.1f} %** de la población, pero el "
                    f"**{float(c.pct_top5[1]):.1f} %** del hospedaje y el **{float(c.pct_top5[3]):.1f} %** de la "
                    f"oferta cultural.")
        d = pd.DataFrame({"Qué": ["Población", "Los 4 ejes", "Hospedaje", "Turismo y cultura"],
                          "Top 5 (%)": [float(c.pct_top5_poblacion.iloc[0]), float(c.pct_top5[0]),
                                        float(c.pct_top5[1]), float(c.pct_top5[3])]})
        fig = px.bar(d, x="Qué", y="Top 5 (%)", text="Top 5 (%)", color="Qué",
                     color_discrete_sequence=["#8C9BB0", tema.COBALTO, "#2f5fb3", tema.GUINDA])
        fig.update_traces(texttemplate="%{text:.1f} %", textposition="outside")
        fig.update_layout(height=380, showlegend=False, yaxis=dict(range=[0, 100]), xaxis_title=None)
        st.plotly_chart(fig, config={"displayModeBar": False}, key="pres_problema")
        st.caption("Participación de los 5 municipios principales. DENUE 05/2026 y Censo 2020 (dw.v_concentracion_eje).")
    elif paso == 1:
        st.markdown("## La oportunidad está fuera de las anclas")
        izq, der = st.columns([1.6, 1])
        with izq:
            m = mapas.Mapa(bd.geo(), alto=520, fondo=bd.fondo_mapa()).municipios(idx, "indice_oportunidad",
                                                                                 cuantiles=True)
            mapas.mostrar(m, "pres_mapa")
        with der:
            top = idx[~idx.es_ancla].nsmallest(10, "ranking_estatal")
            st.dataframe(pd.DataFrame({"#": top.ranking_estatal, "Municipio": top.nombre, "Región": top.region,
                                       "Índice": top.indice_oportunidad.astype(float)}), hide_index=True,
                         width="stretch")
            st.caption(f"Índice de oportunidad `{vig['version_indice']}`: oferta, complementarios, accesibilidad por "
                       "carretera, necesidad social y crecimiento predicho.")
    elif paso == 2:
        prop = rutas[rutas.origen == "propuesta_modelo"]
        mejor = prop.drop_duplicates("ruta_sk").sort_values("puntaje_total", ascending=False).iloc[0]
        g = prop[prop.ruta_sk == mejor.ruta_sk]
        st.markdown(f"## {mejor.ruta}")
        k = st.columns(4)
        k[0].metric("Días", int(mejor.dias_sugeridos))
        k[1].metric("Carretera", f"{mejor.tiempo_total_min / 60:.1f} h",
                    f"{float(mejor.tiempo_total_min_planeacion) / 60:.1f} h de planeación", delta_color="off")
        k[2].metric("Emergentes", int(mejor.num_municipios_emergentes))
        k[3].metric("Novedad", str(mejor.clasificacion_novedad).replace("_", " "))
        for p in g.itertuples():
            st.markdown(f"**{p.orden_parada}. {p.municipio}**" + (" ⚓" if p.es_ancla else "")
                        + (" 🚩 emergente" if p.es_emergente else "") + (" 🛏️ pernocta" if p.es_pernocta else ""))
        st.caption(f"Beneficia a {mejor.region_beneficiada}. 🛡️ {mejor.riesgo_seguridad}")
        if st.button("Ver todas las rutas →"):
            st.switch_page(st.session_state["paginas"]["rutas"])
    elif paso == 3:
        f = bd.ficha().set_index("nombre").loc["Jonotla"]
        st.markdown("## Jonotla: El Peñón y un municipio que nadie veía")
        sem = " · ".join(f"{fb.EMOJI[fb.nivel(f, d)]} {n}" for d, (_, n) in fb.DIMENSIONES.items())
        st.markdown(sem)
        r = idx.set_index("nombre").loc["Jonotla"]
        k = st.columns(3)
        k[0].metric("Índice de oportunidad", f"{float(r.indice_oportunidad):.3f}", f"#{int(r.ranking_estatal)} de 217",
                    delta_color="off")
        k[1].metric("Actividades principales", ", ".join(a["nombre"] for a in (f.actividades_principales or [])[:2]))
        k[2].metric("Rutas propuestas que lo incluyen", len(f.rutas_propuestas or []))
        st.markdown("**Lugares:** " + " · ".join(a["nombre"] for a in (f.atractivos or [])[:6]))
        if st.button("Abrir la ficha técnica de Jonotla →"):
            st.session_state["ir_a_cve"] = f.cve_geo
            st.switch_page(st.session_state["paginas"]["ficha_tecnica"])
    else:
        st.markdown(f"## {int((val.estado == 'ok').sum())} de {len(val)} validaciones en verde")
        st.dataframe(pd.DataFrame({"": val.estado.map({"ok": "✅", "pendiente": "⏳", "falla": "❌"}),
                                   "Validación": val.descripcion, "Resultado": val.resultado}),
                     hide_index=True, width="stretch")
        st.markdown(f"- Escenario con rutas (hipotético): top 5 de **{esc.pct_top5['hoy']:.1f} %** a "
                    f"**{esc.pct_top5['con_rutas_hipotetico']:.1f} %**, Gini {esc.gini['hoy']:.3f} → "
                    f"{esc.gini['con_rutas_hipotetico']:.3f}.\n"
                    "- **Qué sigue:** medir cada ruta contra su línea base (nuevo corte del DENUE cada semestre, "
                    "visibilidad, seguridad) y validarla con las comunidades.")
        if st.button("Ver metodología y fuentes →"):
            st.switch_page(st.session_state["paginas"]["metodologia"])

    a, _, b = st.columns([1, 4, 1])
    if a.button("← Anterior", disabled=paso == 0, width="stretch"):
        st.session_state["pres_paso"] = paso - 1
        st.rerun()
    if b.button("Siguiente →", disabled=paso == len(PASOS) - 1, width="stretch"):
        st.session_state["pres_paso"] = paso + 1
        st.rerun()
