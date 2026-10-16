"""🚩 Alertas: banderas de oportunidad activas de la versión vigente (dw.fact_flag_oportunidad) y lista de formalización."""
import pandas as pd
import plotly.express as px
import streamlit as st

import bd
import ficha_bd as fb
import tema


def render():
    tema.hero("🚩 Alertas de oportunidad",
              "Cada bandera dice qué hacer y por qué, con el motivo calculado por el modelo.", [])
    try:
        ban, idx, mun = bd.banderas(), bd.indice_municipio().set_index("municipio_sk"), bd.municipios()
        ejes = bd.ejes().set_index("eje_sk").nombre
    except bd.SinDatos as e:
        st.error(f"No se pudieron leer las banderas: {e}")
        return
    d = ban.merge(mun[["municipio_sk", "nombre", "region"]], on="municipio_sk")
    d["Bandera"] = d.codigo.map(lambda c: fb.BANDERA.get(c, c))
    d["Eje"] = d.eje_sk.map(ejes)
    d["Índice"] = d.municipio_sk.map(idx.indice_oportunidad.astype(float))

    conteo = d.groupby("Bandera").municipio_sk.nunique().sort_values(ascending=False)
    k = st.columns(len(conteo))
    for col, (b, n) in zip(k, conteo.items()):
        col.metric(b, int(n), "municipios", delta_color="off")

    c = st.columns(3)
    tipos = c[0].multiselect("Banderas", list(conteo.index), default=list(conteo.index)[:3], key="al_tipos")
    regiones = c[1].multiselect("Regiones", sorted(d.region.unique()), key="al_reg")
    ejes_sel = c[2].multiselect("Ejes", sorted(d.Eje.dropna().unique()), key="al_eje")
    f = d[d.Bandera.isin(tipos or conteo.index)]
    if regiones:
        f = f[f.region.isin(regiones)]
    if ejes_sel:
        f = f[f.Eje.isin(ejes_sel)]
    tabla = f.sort_values("Índice", ascending=False)[["nombre", "region", "Eje", "Bandera", "motivo", "Índice"]].rename(
        columns={"nombre": "Municipio", "region": "Región", "motivo": "Motivo"})
    st.dataframe(tabla, hide_index=True, width="stretch",
                 column_config={"Índice": st.column_config.ProgressColumn(min_value=0, max_value=1, format="%.3f")})
    st.download_button("⬇️ Descargar alertas (CSV)", tabla.to_csv(index=False).encode("utf-8-sig"),
                       "alertas_mopedetu.csv", "text/csv")

    st.markdown("#### Región × bandera (municipios)")
    calor = d.groupby(["region", "Bandera"]).municipio_sk.nunique().unstack(fill_value=0)
    fig = px.imshow(calor, text_auto=True, color_continuous_scale=tema.PLOTLY_SEQ, aspect="auto")
    fig.update_layout(height=360, margin=dict(l=0, r=0, t=10, b=0), xaxis_title=None, yaxis_title=None)
    st.plotly_chart(fig, config={"displayModeBar": False}, key="al_calor")

    st.markdown("#### 📋 Lista de formalización")
    sr = d[d.codigo == "OFERTA_SIN_REGISTRO"][["nombre", "region", "Eje", "motivo"]].rename(
        columns={"nombre": "Municipio", "region": "Región", "motivo": "Actividad reconocida sin registro DENUE"})
    st.caption("Municipios y actividades que la Secretaría reconoce en sus rutas oficiales pero sin ningún negocio en "
               "el DENUE: candidatos a un programa de formalización y registro.")
    st.dataframe(sr, hide_index=True, width="stretch")
    st.download_button("⬇️ Lista de formalización (CSV)", sr.to_csv(index=False).encode("utf-8-sig"),
                       "lista_formalizacion_mopedetu.csv", "text/csv")
