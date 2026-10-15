"""Lectura de la ficha técnica municipal desde Supabase (dw.v_ficha_municipio, publishable key)."""

from __future__ import annotations

import pandas as pd
import streamlit as st

import supabase_cliente

DIMENSIONES = {
    "turismo_actual": ("🧳", "Turismo actual"),
    "infraestructura": ("🛣️", "Infraestructura"),
    "oferta": ("🎯", "Oferta turística"),
    "potencial": ("📈", "Potencial"),
    "social": ("🤝", "Necesidad social"),
}
COLOR = {"verde": (46, 158, 91), "amarillo": (232, 177, 13), "rojo": (192, 57, 43), "gris": (184, 193, 204)}
EMOJI = {"verde": "🟢", "amarillo": "🟡", "rojo": "🔴", "gris": "⚪"}
LECTURA = {
    "turismo_actual": {"verde": "Bajo: capacidad para recibir visitantes", "amarillo": "Medio",
                       "rojo": "Alto: ya concentra turismo", "gris": "Sin oferta registrada"},
    "infraestructura": {"verde": "Lista para recibir", "amarillo": "Mejorable", "rojo": "Barrera de acceso",
                        "gris": "Sin datos"},
    "oferta": {"verde": "Especializada", "amarillo": "Diversa, sin especialización", "rojo": "Mínima",
               "gris": "Sin oferta"},
    "potencial": {"verde": "Crece", "amarillo": "Incierto", "rojo": "Estancado", "gris": "Sin modelo aún"},
    "social": {"verde": "Baja", "amarillo": "Media", "rojo": "Alta: prioridad de impacto", "gris": "Sin dato"},
}
MESES = ["E", "F", "M", "A", "M", "J", "J", "A", "S", "O", "N", "D"]
MESES_LARGO = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"]


@st.cache_data(ttl=600, show_spinner="Leyendo la ficha técnica de Supabase…")
def cargar() -> pd.DataFrame | None:
    """Una fila por municipio. Devuelve None si no hay conexión configurada o la vista no responde."""
    if not supabase_cliente.configurado():
        return None
    try:
        df = supabase_cliente.leer("v_ficha_municipio", "dw")
    except Exception:
        return None
    df["cve_geo"] = df.cve_geo.str.strip()
    return df


def nivel(fila, dimension: str) -> str:
    s = fila["semaforos"] or {}
    return (s.get(dimension) or {}).get("nivel", "gris")
