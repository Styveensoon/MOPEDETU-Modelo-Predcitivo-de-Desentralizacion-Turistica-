"""🏠 Panorama: la concentración del turismo, dónde está la oportunidad y qué proponen las rutas (datos de dw)."""
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

import bd
import ficha_bd as fb
import mapas
import metricas
import tema

ETIQUETA_EJE = {0: "Los 4 ejes", 1: "Hospedaje", 2: "Alimentos", 3: "Turismo y cultura", 4: "Comercio turístico"}


def render():
    try:
        vig, idx, conc, esc = bd.vigente(), bd.indice_municipio(), bd.concentracion(), bd.escenarios()
        rutas, ban, apt, oferta = bd.rutas(), bd.banderas(), bd.aptitud_circuitos(), bd.oferta()
    except bd.SinDatos as e:
        st.error(f"No se pudieron leer los datos: {e}")
        return
    prop = rutas[rutas.origen == "propuesta_modelo"]
    mun = bd.municipios().set_index("municipio_sk")

    tema.hero("MOPEDETU · Descentralización turística de Puebla",
              "¿Dónde se concentra hoy el turismo, dónde está la oportunidad y qué rutas la aprovechan? "
              "Todo con datos reales de los 217 municipios.",
              [f"Índice {vig['version_indice']}", f"Modelo {vig['modelo']}", "DENUE 05/2026", "Censos Económicos 2014-2024"])

    total = conc.set_index("eje_sk")
    k = st.columns(5)
    con_bandera = ban[ban.codigo != "BARRERA_ACCESO"].municipio_sk.nunique()
    k[0].metric("🚩 Municipios con oportunidad", con_bandera, "con alguna bandera (sin contar barrera)",
                delta_color="off", help="Por tipo: " + " · ".join(
                    f"{fb.BANDERA.get(c, c)} {n}" for c, n in ban.groupby("codigo").municipio_sk.nunique().items()))
    k[1].metric("🧭 Rutas propuestas", prop.ruta_sk.nunique(),
                f"{prop[prop.es_emergente].municipio_sk.nunique()} municipios emergentes", delta_color="off")
    k[2].metric("Top 5 concentra hoy", f"{total.pct_top5[0]:.1f} %", f"HHI {total.hhi[0]:,.0f}", delta_color="off",
                help="Personal turístico estimado (4 ejes) en los 5 municipios con más oferta.")
    k[3].metric("Con rutas (hipotético)", f"{esc.pct_top5['con_rutas_hipotetico']:.1f} %",
                f"{esc.pct_top5['con_rutas_hipotetico'] - esc.pct_top5['hoy']:+.1f} pp", delta_color="inverse",
                help=esc.supuesto["con_rutas_hipotetico"])
    k[4].metric("🔁 Aptos para circuito", int(apt.apto.sum()), "≥ 3 lugares ubicados", delta_color="off")

    st.markdown("#### ⚖️ La cifra del problema: el turismo se concentra más que la gente")
    barras = pd.DataFrame([{"Qué": "Población", "Top 5 (%)": float(total.pct_top5_poblacion.iloc[0]),
                            "HHI": float(total.hhi_poblacion.iloc[0])}] +
                          [{"Qué": ETIQUETA_EJE[e], "Top 5 (%)": float(r.pct_top5), "HHI": float(r.hhi)}
                           for e, r in total.iterrows()])
    fig = px.bar(barras, x="Top 5 (%)", y="Qué", orientation="h", text="Top 5 (%)", hover_data=["HHI"],
                 color="Qué", color_discrete_sequence=["#8C9BB0", tema.COBALTO, "#2f5fb3", "#5C8FD6", tema.GUINDA,
                                                       tema.AMARILLO])
    fig.update_traces(texttemplate="%{text:.1f} %", textposition="outside")
    fig.update_layout(height=280, showlegend=False, margin=dict(l=0, r=30, t=10, b=0), yaxis_title=None,
                      xaxis=dict(range=[0, 100]))
    st.plotly_chart(fig, config={"displayModeBar": False}, key="pan_problema")
    st.caption(f"Participación de los 5 municipios con más personal ocupado (DENUE 05/2026) contra la de los 5 más "
               f"poblados (Censo 2020: {float(total.pct_top5_poblacion.iloc[0]):.1f} %). Fuente: dw.v_concentracion_eje.")

    izq, der = st.columns([1.65, 1])
    with izq:
        st.markdown("#### 🗺️ Índice de oportunidad turística")
        tt = idx.set_index("cve_geo").apply(
            lambda r: f"<b>{r.nombre}</b><br/>{r.region}<br/>Índice: <b>{r.indice_oportunidad:.3f}</b> "
                      f"(#{r.ranking_estatal})<br/>Eje líder: {str(r.eje_lider).replace('_', ' ')}"
                      + ("<br/>⚓ Destino ancla" if r.es_ancla else ""), axis=1)
        m = mapas.Mapa(bd.geo(), alto=600, fondo=bd.fondo_mapa()).municipios(idx, "indice_oportunidad", tt,
                                                                              cuantiles=True)
        for sk, tr in bd.trazos().items():
            if sk in set(prop.ruta_sk):
                lon, lat = zip(*tr["geom"]["coordinates"])
                m.trayecto(lon, lat, tema.AMARILLO, 3.5, f"<b>{prop[prop.ruta_sk == sk].ruta.iat[0]}</b>")
        anclas = idx[idx.es_ancla].merge(mun[["cabecera_lat", "cabecera_lon"]], left_on="municipio_sk", right_index=True)
        anclas = anclas.assign(lat=anclas.cabecera_lat.astype(float), lon=anclas.cabecera_lon.astype(float),
                               tt="<b>⚓ " + anclas.nombre + "</b><br>Destino ancla")
        m.puntos(anclas, tema.COBALTO_OSC, 11, "tt")
        top = idx[~idx.es_ancla].nsmallest(10, "ranking_estatal").merge(
            mun[["cabecera_lat", "cabecera_lon"]], left_on="municipio_sk", right_index=True)
        top = top.assign(lat=top.cabecera_lat.astype(float), lon=top.cabecera_lon.astype(float))
        m.nombres(anclas, tamano=11).nombres(top.head(5), tamano=10, color=tema.GUINDA)
        mapas.mostrar(m, "pan_mapa")
        mapas.leyenda("Índice de oportunidad (percentil estatal) · ⚓ anclas · amarillo = rutas del modelo · "
                      "guinda = top 5 emergentes", "bajo", "alto")
    with der:
        st.markdown("#### 🌱 Top 10 municipios emergentes")
        st.dataframe(pd.DataFrame({"#": top.ranking_estatal, "Municipio": top.nombre, "Región": top.region,
                                   "Índice": top.indice_oportunidad.astype(float),
                                   "Eje líder": top.eje_lider.str.replace("_", " ")}),
                     hide_index=True, width="stretch",
                     column_config={"Índice": st.column_config.ProgressColumn(min_value=0, max_value=1, format="%.3f")})
        st.caption("Sin contar las 12 anclas. Ranking estatal del índice vigente (dw.v_indice_municipio).")

        st.markdown("#### 📉 Curva de Lorenz del empleo turístico")
        hoy = oferta.groupby("municipio_sk").personal_est.sum()
        x, y = metricas.lorenz(hoy)
        fig = go.Figure([go.Scatter(x=[0, 1], y=[0, 1], mode="lines", line=dict(dash="dot", color="#8C9BB0"),
                                    name="Igualdad"),
                         go.Scatter(x=x, y=y, mode="lines", line=dict(color=tema.GUINDA, width=3), name="Hoy")])
        fig.update_layout(height=260, margin=dict(l=0, r=0, t=10, b=0), legend=dict(orientation="h", y=-0.2),
                          xaxis_title="% de municipios", yaxis_title="% del empleo")
        st.plotly_chart(fig, config={"displayModeBar": False}, key="pan_lorenz")
        st.caption(f"Gini hoy **{esc.gini['hoy']:.3f}** → tendencial {esc.gini['tendencial']:.3f} → con rutas "
                   f"{esc.gini['con_rutas_hipotetico']:.3f} (hipotético: {esc.supuesto['con_rutas_hipotetico']})")

    st.markdown("#### 🧩 Empleo turístico por región y eje")
    ejes = bd.ejes().set_index("eje_sk").nombre
    t = oferta.merge(mun[["region"]], left_on="municipio_sk", right_index=True)
    t = t.groupby(["region", "eje_sk"], as_index=False).personal_est.sum()
    t["eje"] = t.eje_sk.map(ejes)
    t = t.merge(idx.groupby("region", as_index=False).indice_oportunidad.mean().rename(
        columns={"indice_oportunidad": "indice_medio"}), on="region")
    fig = px.treemap(t, path=["region", "eje"], values="personal_est", color="indice_medio",
                     color_continuous_scale=tema.PLOTLY_SEQ, hover_data={"personal_est": ":,.0f"})
    fig.update_layout(height=420, margin=dict(l=0, r=0, t=10, b=0), coloraxis_colorbar=dict(title="Índice medio"))
    st.plotly_chart(fig, config={"displayModeBar": False}, key="pan_treemap")
    st.caption("Tamaño = personal ocupado estimado (DENUE 05/2026); color = índice de oportunidad medio de la región.")
