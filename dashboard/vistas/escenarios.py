"""🔮 Escenarios y sensibilidad: escenarios de concentración guardados (con su supuesto) y V6 en vivo con los pesos
del índice vigente. Nada de esta página cambia la base."""
import numpy as np
import pandas as pd
import streamlit as st

import bd
import tema

COMPONENTES = {"oferta": "score_oferta", "complementarios": "score_complementarios",
               "accesibilidad": "score_accesibilidad", "social": "score_social", "potencial_predicho": "score_potencial"}
NOMBRE = {"oferta": "Oferta", "complementarios": "Complementarios", "accesibilidad": "Accesibilidad",
          "social": "Necesidad social", "potencial_predicho": "Potencial predicho"}
ESC = {"hoy": "Hoy", "tendencial": "Tendencial a 5 años", "con_rutas_hipotetico": "Con rutas (hipotético)"}


def indice_con(det: pd.DataFrame, pesos: dict) -> pd.Series:
    """Índice con otros pesos usando LA MISMA función del pipeline (model/indice.py::indice, renormalizado como v3);
    mejor eje por municipio."""
    import indice
    c = det.copy()
    for col in COMPONENTES.values():
        c[col] = c[col].astype(float)
    pot = c.set_index(["municipio_sk", "eje_sk"]).score_potencial
    r = indice.indice(c.drop(columns="score_potencial"), pesos, potencial=pot, renormalizar=True)
    return r.groupby("municipio_sk").indice_oportunidad.max()


def render():
    tema.hero("🔮 Escenarios y sensibilidad",
              "Qué pasaría con la concentración del turismo y qué tan estable es el ranking si cambian los pesos. "
              "Esta página no cambia la base.", [])
    try:
        esc, det, vig, mun = bd.escenarios(), bd.indice_detalle(), bd.vigente(), bd.municipios().set_index("municipio_sk")
    except bd.SinDatos as e:
        st.error(f"No se pudieron leer los datos: {e}")
        return

    st.markdown("#### Escenarios de concentración")
    k = st.columns(3)
    for col, (e, n) in zip(k, ESC.items()):
        col.metric(n, f"{float(esc.pct_top5[e]):.1f} % en el top 5", f"HHI {float(esc.hhi[e]):,.0f} · Gini {float(esc.gini[e]):.3f}",
                   delta_color="off")
    for e, n in ESC.items():
        st.caption(f"**{n}:** {esc.supuesto[e]}")

    st.markdown("#### Sensibilidad del índice (V6 en vivo)")
    pesos = vig["pesos_indice"]
    cols = st.columns(len(pesos))
    nuevos = {k: cols[i].slider(NOMBRE.get(k, k), 0.0, 0.6, float(v), 0.01, key=f"es_{k}")
              for i, (k, v) in enumerate(pesos.items())}
    oficial = indice_con(det, pesos)
    prueba = indice_con(det, nuevos)
    top_o, top_p = set(oficial.nlargest(20).index), set(prueba.nlargest(20).index)
    conserva = len(top_o & top_p) / 20
    a, b = st.columns([1, 2])
    a.metric("Top 20 que se conserva", f"{conserva:.0%}", "criterio V6: ≥ 70 %", delta_color="off")
    a.caption(f"Pesos oficiales (`{vig['version_indice']}`): " + ", ".join(f"{NOMBRE.get(k, k)} {v}" for k, v in pesos.items()))
    tabla = pd.DataFrame({"Municipio": mun.nombre.reindex(prueba.nlargest(20).index).values,
                          "Índice con estos pesos": prueba.nlargest(20).round(3).values,
                          "En el top 20 oficial": ["✅" if x in top_o else "🆕" for x in prueba.nlargest(20).index]})
    b.dataframe(tabla, hide_index=True, width="stretch")
    st.caption("Sensibilidad = qué tanto cambia el ranking; no es una predicción ni modifica la base.")
