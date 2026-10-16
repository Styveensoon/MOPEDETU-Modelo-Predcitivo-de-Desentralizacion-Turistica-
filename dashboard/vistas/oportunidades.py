"""🗺️ Mapa de oportunidades: cualquier indicador de la base por municipio, banderas resaltadas y oferta contra
visibilidad (datos de dw; umbrales leídos de model/indice.py, los mismos de la bandera)."""
import html

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import bd
import ficha_bd as fb
import indice
import mapas
import tema


def _tabla_municipios() -> pd.DataFrame:
    idx = bd.indice_municipio().set_index("municipio_sk")
    f = bd.ficha().set_index("municipio_sk")
    m = idx[["cve_geo", "nombre", "region", "es_ancla", "eje_lider", "indice_oportunidad", "ranking_estatal",
             "score_oferta", "score_social", "score_accesibilidad", "score_potencial"]].copy()
    for c in ("indice_oportunidad", "score_oferta", "score_social", "score_accesibilidad", "score_potencial"):
        m[c] = m[c].astype(float)

    def crec(pr):
        v = [p["crecimiento_pct"] for p in (pr or []) if p.get("en_dominio")]
        return max(v) if v else np.nan
    m["crecimiento"] = f.prediccion.map(crec)
    m["personal"] = bd.oferta().groupby("municipio_sk").personal_est.sum().astype(float)
    m["exceso"] = f.exceso_oferta.map(lambda x: next((e["percentil"] for e in x or [] if e["eje"] == "global"), np.nan))
    m["marginacion"] = bd.contexto().indice_marginacion.astype(float)
    m["min_ancla"] = f.infraestructura.map(lambda i: (i or {}).get("min_ancla_cercana"))
    m["visibilidad"] = f.visibilidad.map(lambda v: v["percentil"] if isinstance(v, dict) else np.nan)
    m["seguridad"] = f.seguridad.map(lambda s: s["tasa_municipio"] if isinstance(s, dict) else np.nan)
    ban = bd.banderas()
    m["banderas"] = ban.groupby("municipio_sk").codigo.nunique().reindex(m.index).fillna(0)
    m["circuito"] = bd.aptitud_circuitos().set_index("municipio_sk").potencial_circuito.astype(float)
    det = bd.indice_detalle()
    m["oferta_max"] = det.groupby("municipio_sk").score_oferta.max().astype(float)
    return m


INDICADORES = {
    "indice_oportunidad": ("Índice de oportunidad (vigente)", False), "score_oferta": ("Componente: oferta", False),
    "score_accesibilidad": ("Componente: accesibilidad por carretera", False),
    "score_social": ("Componente: necesidad social", False), "score_potencial": ("Componente: potencial predicho", False),
    "crecimiento": ("Crecimiento predicho a 5 años (máx. eje en dominio, %)", False),
    "personal": ("Personal turístico estimado (DENUE)", False), "exceso": ("Oferta en exceso de la población (percentil)", False),
    "marginacion": ("Índice de marginación CONAPO (más bajo = más marginado)", True),
    "min_ancla": ("Minutos por carretera al ancla más cercana", True),
    "visibilidad": ("Visibilidad en Wikipedia (percentil)", False),
    "seguridad": ("Delitos en el municipio por 100 mil hab.", True), "banderas": ("Número de banderas activas", False),
    "circuito": ("Potencial de circuito", False), "cl_actividad": ("Cociente de localización de una actividad", False),
}


def render():
    tema.hero("🗺️ Mapa de oportunidades",
              "Elige un indicador, resalta una bandera y haz clic en un municipio para ver por qué.", [])
    try:
        m = _tabla_municipios()
        tipos = bd.banderas()[["codigo", "descripcion"]].drop_duplicates().sort_values("codigo")
    except bd.SinDatos as e:
        st.error(f"No se pudieron leer los datos: {e}")
        return
    c = st.columns([2, 1.4, 1.6])
    ind = c[0].selectbox("Indicador", list(INDICADORES), format_func=lambda k: INDICADORES[k][0], key="op_ind")
    if ind == "cl_actividad":
        act = bd.actividades()
        a = c[1].selectbox("Actividad", list(act.codigo), key="op_act",
                           format_func=dict(zip(act.codigo, act.icono + " " + act.nombre)).get)
        am = bd.actividad_municipio()
        m["cl_actividad"] = am[am.codigo == a].set_index("municipio_sk").cociente_localizacion.astype(float)
    bandera = c[2].selectbox("Resaltar bandera", ["(ninguna)"] + list(tipos.codigo), key="op_ban",
                             format_func=lambda k: k if k.startswith("(") else fb.BANDERA.get(k, k))
    if not bandera.startswith("("):
        st.caption(f"🚩 **{fb.BANDERA.get(bandera, bandera)}**: {tipos.set_index('codigo').descripcion[bandera]}")
    resaltar = set()
    ban = bd.banderas()
    if not bandera.startswith("("):
        resaltar = set(m.cve_geo[m.index.isin(ban[ban.codigo == bandera].municipio_sk)])

    nombre_ind, invertir = INDICADORES[ind]
    d = m.reset_index()
    d["valor"] = -d[ind] if invertir else d[ind]
    tt = d.set_index("cve_geo").apply(
        lambda r: f"<b>{html.escape(r.nombre)}</b><br>{r.region}<br>{nombre_ind}: "
                  + ("s/d" if pd.isna(r[ind]) else f"{r[ind]:,.2f}") + f"<br>Índice #{r.ranking_estatal}", axis=1)
    izq, der = st.columns([1.6, 1])
    with izq:
        mp = mapas.Mapa(bd.geo(), alto=620, fondo=bd.fondo_mapa()).municipios(
            d, "valor", tt, cuantiles=True, resaltar=resaltar, seleccionado=st.session_state.get("op_cve"))
        mapas.mostrar(mp, "op_mapa", "op_cve")
        mapas.leyenda(nombre_ind + (" (invertido: más oscuro = mejor)" if invertir else "") + " · guinda = bandera",
                      "bajo", "alto")
    with der:
        cve = st.session_state.get("op_cve")
        if not cve:
            st.info("Haz clic en un municipio para ver su detalle.")
        else:
            r = m[m.cve_geo == cve].iloc[0]
            mk = m.index[m.cve_geo == cve][0]
            st.markdown(f"### {r.nombre}" + (" ⚓" if r.es_ancla else ""))
            st.metric("Índice de oportunidad", f"{r.indice_oportunidad:.3f}", f"#{int(r.ranking_estatal)} de 217",
                      delta_color="off")
            comp = pd.DataFrame({"Componente": ["Oferta", "Accesibilidad", "Necesidad social", "Potencial"],
                                 "Valor": [r.score_oferta, r.score_accesibilidad, r.score_social, r.score_potencial]})
            st.dataframe(comp, hide_index=True, width="stretch", column_config={
                "Valor": st.column_config.ProgressColumn(min_value=0, max_value=1, format="%.2f")})
            for b in ban[ban.municipio_sk == mk].itertuples():
                st.markdown(f'<span class="mope-tag flag">{fb.BANDERA.get(b.codigo, b.codigo)}</span> '
                            f'<small>{html.escape(b.motivo or "")}</small>', unsafe_allow_html=True)
            acts = bd.ficha().set_index("municipio_sk").actividades_principales.get(mk) or []
            st.caption("Actividades principales: " + (" · ".join(f"{a['icono']} {a['nombre']}" for a in acts) or "—"))
            if st.button("Abrir ficha técnica →", key="op_ficha"):
                st.session_state["ir_a_cve"] = cve
                st.switch_page(st.session_state["paginas"]["ficha_tecnica"])

    st.markdown("#### 👀 Oferta contra visibilidad")
    uo, uv = indice.UMBRAL_INVISIBLE_OFERTA, indice.UMBRAL_INVISIBLE_VISIBILIDAD
    inv = set(ban[ban.codigo == "OFERTA_INVISIBLE"].municipio_sk)
    s = m.dropna(subset=["oferta_max", "visibilidad"])
    fig = go.Figure()
    for es, color, nombre in ((False, "#8C9BB0", "Resto"), (True, tema.GUINDA, "Oferta invisible")):
        g = s[s.index.isin(inv) == es]
        fig.add_trace(go.Scatter(x=g.oferta_max, y=g.visibilidad, mode="markers", name=nombre,
                                 marker=dict(color=color, size=8, opacity=0.8), text=g.nombre,
                                 hovertemplate="%{text}<br>oferta P%{x:.0%} · visibilidad P%{y:.0%}<extra></extra>"))
    fig.add_shape(type="rect", x0=uo, x1=1, y0=0, y1=uv, fillcolor="rgba(138,21,56,.08)", line=dict(width=0))
    fig.add_vline(x=uo, line_dash="dot", line_color=tema.GUINDA)
    fig.add_hline(y=uv, line_dash="dot", line_color=tema.GUINDA)
    fig.update_layout(height=380, margin=dict(l=0, r=0, t=10, b=0), xaxis_title="Percentil de oferta (mejor eje)",
                      yaxis_title="Percentil de visibilidad", legend=dict(orientation="h", y=-0.2))
    st.plotly_chart(fig, config={"displayModeBar": False}, key="op_scatter")
    st.caption(f"Cuadrante sombreado: oferta ≥ P{uo * 100:.0f} y visibilidad ≤ P{uv * 100:.0f} (umbrales de la "
               "bandera OFERTA_INVISIBLE en model/indice.py; la bandera además excluye anclas).")
