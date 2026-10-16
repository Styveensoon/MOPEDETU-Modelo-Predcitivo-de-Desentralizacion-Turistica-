"""📚 Metodología y fuentes: fuentes, modelos contra sus líneas base, validaciones y limitaciones (datos de dw)."""
import pandas as pd
import streamlit as st

import bd
import tema

ESTADO = {"ok": "✅", "pendiente": "⏳", "falla": "❌"}
LIMITACIONES = [
    "Mide **oferta** (establecimientos y empleo del DENUE y los Censos Económicos), no visitantes ni derrama.",
    "Los tiempos por carretera son de **flujo libre** (OSRM, sin tráfico); las reglas de rutas les suman un margen "
    "de planeación por región (×1.25 en las sierras y Tehuacán, ×1.10 en el resto). Es un supuesto, no una medición.",
    "DATATUR público solo trae la **ciudad de Puebla**: no hay demanda hotelera medida para los demás destinos.",
    "El **Registro Nacional de Turismo** no está disponible como datos abiertos por municipio.",
    "Seguridad = **denuncias** (SESNSP), no victimización; se usa para planear rutas, nunca como etiqueta del municipio.",
    "Las rutas propuestas y los escenarios con rutas son **hipótesis** para validar con las comunidades, no predicciones.",
    "El modelo de crecimiento sirve para **priorizar** (ordenar municipios), no para pronosticar cifras exactas; con "
    "menos de 3 unidades en el eje no predice.",
]


def render():
    tema.hero("📚 Metodología y fuentes",
              "De dónde salen los datos, cómo se validaron los modelos y qué no afirma la plataforma.",
              ["Fuentes oficiales y abiertas", "Modelos contra líneas base", "Validaciones automáticas"])
    try:
        fuentes, modelos, val = bd.fuentes(), bd.modelos(), bd.validaciones()
        vig = bd.vigente()
    except bd.SinDatos as e:
        st.error(f"No se pudieron leer los datos: {e}")
        return

    t1, t2, t3, t4 = st.tabs(["✅ Validaciones", "🤖 Modelos", "🗂️ Fuentes", "⚠️ Limitaciones"])
    with t1:
        ok = (val.estado == "ok").sum()
        st.markdown(f"**{ok} de {len(val)} validaciones en verde** · calculadas por el pipeline sobre la base "
                    "(`scripts/validaciones.py`)")
        st.dataframe(pd.DataFrame({"": val.estado.map(ESTADO), "Código": val.codigo, "Qué se valida": val.descripcion,
                                   "Criterio": val.criterio, "Resultado": val.resultado,
                                   "Fecha": pd.to_datetime(val.fecha).dt.strftime("%Y-%m-%d")}),
                     hide_index=True, width="stretch")
    with t2:
        st.info("Los modelos le ganan a sus líneas base: sirven para **priorizar**, no para pronosticar cifras.")
        m = modelos.set_index("nombre")
        c = m.metricas.get(vig["modelo"]) or {}
        if c:
            st.markdown(f"**Crecimiento de la oferta por municipio × eje** · `{vig['modelo']}` (vigente)")
            filas = [{"Modelo": n, "Validación": "cruzada por municipio", "MAE": c[k]["mae"],
                      "Spearman": c[k]["spearman"], "Precisión top 20 %": c[k]["precision_top20"]}
                     for k, n in (("lgbm", "LightGBM"), ("b1_media_eje", "Línea base: media del eje"),
                                  ("b2_ridge", "Línea base: Ridge"))]
            t = c.get("validacion_temporal_2014_2019_a_2019_2024")
            if t:
                filas += [{"Modelo": n, "Validación": "temporal (2014→19 / 2019→24)", "MAE": t[k]["mae"],
                           "Spearman": t[k]["spearman"], "Precisión top 20 %": t[k]["precision_top20"]}
                          for k, n in (("lgbm", "LightGBM"), ("b1_media_eje", "Línea base: media del eje"))]
            st.dataframe(pd.DataFrame(filas), hide_index=True, width="stretch")
            st.caption(f"Cobertura del intervalo de 80 %: {c.get('cobertura_intervalo_80', 0):.0%} · "
                       f"{c.get('n_entrenamiento')} celdas de entrenamiento.")
        e = m.metricas.get("enlace_municipios_lgbm_v1") or {}
        if e:
            st.markdown("**Probabilidad de que dos municipios formen parte de una ruta** · `enlace_municipios_lgbm_v1`")
            st.dataframe(pd.DataFrame([{"Modelo": n, "AUC": e[k]["auc"], "Precisión media (AP)": e[k]["ap"]}
                                       for k, n in (("lgbm", "LightGBM"), ("b_distancia", "Línea base: solo distancia"),
                                                    ("b_similitud", "Línea base: solo similitud"))]),
                         hide_index=True, width="stretch")
        rb = m.metricas.get("crecimiento_ridge_v2_homologado") or {}
        if rb:
            tb = rb.get("temporal", {})
            st.markdown("**Modelo del rol B (personal ocupado)** · `crecimiento_ridge_v2_homologado`")
            st.caption(f"Validación temporal: Spearman {tb.get('spearman_global')} · precisión top 20 "
                       f"{tb.get('precision_top20_global')} · supera sus líneas base: "
                       f"{'sí' if rb.get('supera_lineas_base') else 'no'}.")
        with st.expander("Todos los modelos registrados (dw.dim_modelo)"):
            st.dataframe(modelos[["nombre", "tarea", "algoritmo", "periodo_entrenamiento", "periodo_validacion"]],
                         hide_index=True, width="stretch")
    with t3:
        st.dataframe(fuentes[["nombre", "institucion", "version_corte", "fecha_descarga", "licencia_terminos",
                              "cobertura", "calidad_notas", "uso_en_modelo"]].rename(columns={
            "nombre": "Fuente", "institucion": "Institución", "version_corte": "Versión", "fecha_descarga": "Descarga",
            "licencia_terminos": "Licencia", "cobertura": "Cobertura", "calidad_notas": "Notas de calidad",
            "uso_en_modelo": "Uso en el modelo"}), hide_index=True, width="stretch")
        st.caption(f"{len(fuentes)} fuentes registradas en dw.dim_fuente.")
    with t4:
        for t in LIMITACIONES:
            st.markdown(f"- {t}")
