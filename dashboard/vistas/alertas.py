import plotly.express as px
import streamlit as st

import estado
import motor
import tema


def render():
    d = estado.datos()
    act = d.actividades.set_index("clave")
    pred, _ = estado.prediccion()
    pred = estado.filtrar_region(pred)

    tema.hero("🚩 Alertas y áreas de oportunidad",
              "Flags automáticos por municipio y actividad: dónde actuar primero.", estado.chips())

    conteo = pred[list(motor.FLAGS)].sum()
    cols = st.columns(len(motor.FLAGS))
    for c, (flag, desc) in zip(cols, motor.FLAGS.items()):
        c.metric(flag.replace("_", " ").title(), int(conteo[flag]), help=desc)

    f1, f2, f3 = st.columns([2, 2, 1])
    flags = f1.multiselect("Flags", list(motor.FLAGS), default=["OFERTA_INVISIBLE", "IMPACTO_SOCIAL"])
    acts = f2.multiselect("Actividad", act.index, format_func=lambda k: f"{act.icono[k]} {act.nombre[k]}")
    minimo = f3.slider("Índice mínimo", 0.0, 1.0, 0.0, 0.05)

    t = pred.copy()
    if flags:
        t = t[t[flags].any(axis=1)]
    if acts:
        t = t[t.actividad.isin(acts)]
    t = t[t.indice_oportunidad >= minimo]
    t["Actividad"] = t.actividad.map(lambda k: f"{act.icono[k]} {act.nombre[k]}")
    t["Flags"] = t.apply(lambda r: ", ".join(f for f in motor.FLAGS if r[f]), axis=1)
    tabla = t[["nombre", "region", "Actividad", "indice_oportunidad", "cociente_localizacion", "personal_ocupado",
               "menciones", "inversion_reciente_mdp", "indice_marginacion", "Flags"]].sort_values(
        "indice_oportunidad", ascending=False)

    st.dataframe(tabla, hide_index=True, width="stretch", height=420, column_config={
        "nombre": "Municipio", "region": "Región",
        "indice_oportunidad": st.column_config.ProgressColumn("Índice", min_value=0, max_value=1, format="%.2f"),
        "cociente_localizacion": st.column_config.NumberColumn("CL", format="%.2f"),
        "personal_ocupado": st.column_config.NumberColumn("Personal", format="%d"),
        "menciones": "Menciones", "inversion_reciente_mdp": st.column_config.NumberColumn("Inversión MDP", format="%.1f"),
        "indice_marginacion": st.column_config.NumberColumn("Marginación", format="%.2f"),
    })
    st.download_button("⬇️ Descargar alertas (CSV)", tabla.to_csv(index=False).encode("utf-8-sig"),
                       "alertas_mopedetu.csv", "text/csv")

    st.markdown("#### 🧮 Flags por región y actividad")
    larga = pred.melt(id_vars=["region", "actividad"], value_vars=list(motor.FLAGS), var_name="flag", value_name="v")
    larga = larga[larga.v].groupby(["region", "flag"]).size().reset_index(name="n")
    fig = px.density_heatmap(larga, x="flag", y="region", z="n", color_continuous_scale=["#F7F5EF", "#E8B10D", "#8A1538"],
                             text_auto=True)
    fig.update_layout(height=380, margin=dict(l=0, r=0, t=10, b=0), xaxis_title=None, yaxis_title=None)
    st.plotly_chart(fig)
