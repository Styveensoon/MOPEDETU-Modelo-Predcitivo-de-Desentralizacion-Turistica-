import plotly.express as px
import streamlit as st

import estado
import mapas
import motor
import tema

METRICAS = {
    "indice_oportunidad": ("Índice de oportunidad", tema.SEQ_TALAVERA, "{:.2f}"),
    "crecimiento_pct": ("Crecimiento proyectado del empleo (%)", tema.SEQ_CRECIMIENTO, "{:.1f} %"),
    "po_actual": ("Personal ocupado turístico (DENUE)", tema.SEQ_TALAVERA, "{:,.0f}"),
    "menciones": ("Visibilidad (menciones)", tema.SEQ_TALAVERA, "{:,.0f}"),
    "inversion_reciente_mdp": ("Inversión pública reciente (MDP)", tema.SEQ_CRECIMIENTO, "{:,.1f}"),
    "indice_marginacion": ("Índice de marginación", tema.SEQ_CRECIMIENTO, "{:.2f}"),
    "pct_via_pavimentada": ("Vías pavimentadas (%)", tema.SEQ_TALAVERA, "{:.0%}"),
    "num_flags": ("Número de flags", tema.SEQ_CRECIMIENTO, "{:.0f}"),
    "cl_actividad": ("Predominancia de una actividad (cociente de localización)", tema.SEQ_TALAVERA, "{:.2f}"),
}


def render():
    d = estado.datos()
    pred, mp = estado.prediccion()
    act = d.actividades.set_index("clave")

    tema.hero("🗺️ Mapa de oportunidades",
              "Explora cualquier indicador sobre los 217 municipios. Haz clic en un municipio para ver su detalle.",
              estado.chips())

    c1, c2, c3, c4 = st.columns([2, 1.4, 1, 1])
    metrica = c1.selectbox("Indicador", list(METRICAS), format_func=lambda k: METRICAS[k][0])
    actividad = None
    if metrica == "cl_actividad":
        actividad = c2.selectbox("Actividad", act.index, format_func=lambda k: f"{act.icono[k]} {act.nombre[k]}")
    flag = c2.selectbox("Resaltar flag", ["Ninguno"] + list(motor.FLAGS)) if metrica != "cl_actividad" else "Ninguno"
    columnas_3d = c3.toggle("Columnas 3D", value=False, help="Altura = personal ocupado turístico")
    oscuro = c4.toggle("Mapa oscuro", value=False)

    df = mp.copy()
    if actividad:
        cl = pred[pred.actividad == actividad].set_index("cve_geo").cociente_localizacion
        df["cl_actividad"] = df.cve_geo.map(cl).fillna(0)
    titulo, paleta, fmt = METRICAS[metrica]
    resaltar = set(pred[pred[flag]].cve_geo) if flag != "Ninguno" else set()

    df["tt"] = df.apply(
        lambda r: f"<b>{r.nombre}</b> · {r.region}<br/>{titulo}: <b>{fmt.format(r[metrica])}</b><br/>"
                  f"Líder: {r.icono_lider} {r.actividad_lider}<br/>Índice: {r.indice_oportunidad:.2f} · Flags: {r.num_flags}", axis=1)
    vmax = df[metrica].quantile(0.97) if metrica in ("po_actual", "menciones", "inversion_reciente_mdp") else None
    capas = [mapas.capa_municipios(d.geo, df, metrica, df.set_index("cve_geo").tt, paleta=paleta,
                                   vmax=vmax, resaltar=resaltar,
                                   cuantiles=metrica in ("indice_oportunidad", "po_actual", "menciones"))]
    vista = mapas.VISTA_PUEBLA
    if columnas_3d:
        capas.append(mapas.capa_columnas(df, "po_actual", escala_altura=25))
        vista = mapas.pdk.ViewState(latitude=18.7, longitude=-97.95, zoom=6.8, pitch=50, bearing=-15)

    mapa, panel = st.columns([2, 1])
    with mapa:
        evento = st.pydeck_chart(mapas.deck(capas, vista, oscuro), height=600, on_select="rerun",
                                 selection_mode="single-object", key="mapa_op")
        mapas.leyenda(titulo, "bajo", "alto", paleta)
        if resaltar:
            st.caption(f"Contorno guinda: {len(resaltar)} municipios con **{flag}** — {motor.FLAGS[flag]}")

    seleccion = None
    try:
        objs = evento.selection.objects.get("municipios", [])
        if objs:
            seleccion = objs[0]["cve_geo"]
    except Exception:
        pass

    with panel:
        if seleccion:
            r = df.set_index("cve_geo").loc[seleccion]
            st.markdown(f"### {r.nombre}")
            st.caption(f"{r.region} · {r.poblacion:,.0f} hab. · marginación {r.grado_marginacion.lower()}")
            a, b = st.columns(2)
            a.metric("Índice", f"{r.indice_oportunidad:.2f}")
            b.metric("Crecimiento", f"{r.crecimiento_pct:+.1f} %")
            filas = pred[pred.cve_geo == seleccion].sort_values("indice_oportunidad", ascending=False)
            for f in filas.itertuples():
                flags = [k for k in motor.FLAGS if getattr(f, k)]
                st.markdown(f"{act.icono[f.actividad]} **{act.nombre[f.actividad]}** · CL {f.cociente_localizacion:.1f} "
                            f"· {f.nivel_predominancia}" + ("".join(f' <span class="mope-tag flag">{x}</span>' for x in flags)),
                            unsafe_allow_html=True)
            if st.button("Abrir ficha completa →", width="stretch"):
                st.session_state["ficha_cve"] = seleccion
                st.switch_page(st.session_state["paginas"]["ficha"])
        else:
            st.markdown("#### Ranking")
            orden = df.sort_values(metrica, ascending=False)[["nombre", "region", metrica, "actividad_lider"]]
            st.dataframe(orden, hide_index=True, height=560, width="stretch",
                         column_config={metrica: st.column_config.NumberColumn(titulo.split(" (")[0], format="%.2f"),
                                        "actividad_lider": "Actividad líder", "nombre": "Municipio", "region": "Región"})

    st.markdown("#### 🔍 Oferta contra visibilidad: dónde está lo invisible")
    sc = pred.assign(actividad_n=pred.actividad.map(act.nombre))
    fig = px.scatter(sc, x="s_visibilidad", y="s_oferta", size="personal_ocupado", color="actividad_n",
                     hover_name="nombre", hover_data={"cociente_localizacion": ":.2f", "s_visibilidad": ":.2f", "s_oferta": ":.2f"},
                     size_max=28, opacity=.75, labels={"s_visibilidad": "Visibilidad (percentil)",
                                                       "s_oferta": "Oferta real DENUE (percentil)", "actividad_n": "Actividad"})
    fig.add_shape(type="rect", x0=0, x1=0.35, y0=0.6, y1=1.02, line=dict(color=tema.GUINDA, dash="dash"),
                  fillcolor="rgba(138,21,56,.06)")
    fig.add_annotation(x=0.17, y=1.05, text="🚩 OFERTA INVISIBLE", showarrow=False, font=dict(color=tema.GUINDA))
    fig.update_layout(height=430, margin=dict(l=0, r=0, t=20, b=0))
    st.plotly_chart(fig)
