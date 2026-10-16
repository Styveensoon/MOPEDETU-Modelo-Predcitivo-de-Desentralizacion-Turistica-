"""Barra lateral: qué versión de datos y modelos se está viendo, leída de la base (sin supuestos simulados)."""

from __future__ import annotations

import streamlit as st

import bd


def barra_lateral():
    sb = st.sidebar
    try:
        vig = bd.vigente()
    except bd.SinDatos as e:
        sb.error(f"Sin conexión a los datos: {e}")
        return
    sb.markdown("### 🗂️ Datos que estás viendo")
    p = vig["parametros_rutas"]
    sb.caption(f"Índice **{vig['version_indice']}** · modelo **{vig['modelo']}** · oferta DENUE 05/2026 · "
               f"horizonte de predicción: 5 años · rutas: tramo ≤ {p['max_tramo_min']} min, "
               f"pernocta con ≥ {p['min_hospedaje_pernocta']} hospedajes.")
    sb.divider()
    fuente = bd.fuente()
    if fuente == "Supabase":
        sb.caption("Fuente: Supabase (esquema dw), solo lectura.")
    else:
        sb.warning(f"Sin conexión a Supabase: {fuente}.")
