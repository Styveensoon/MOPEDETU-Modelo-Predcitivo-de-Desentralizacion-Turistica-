"""Etiquetas de lectura de la ficha técnica (texto, no datos). Los datos salen de `bd.py`."""

from __future__ import annotations

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
    "potencial": {"verde": "Crece", "amarillo": "Incierto", "rojo": "Estancado",
                  "gris": "Sin predicción (fuera del dominio del modelo)"},
    "social": {"verde": "Baja", "amarillo": "Media", "rojo": "Alta: prioridad de impacto", "gris": "Sin dato"},
}
# Nombres legibles de las banderas de dw.dim_tipo_flag (la descripción completa se lee de la base)
BANDERA = {"OFERTA_EMERGENTE": "Oferta emergente", "ACCESIBLE_NO_EXPLOTADO": "Accesible no explotado",
           "BARRERA_ACCESO": "Barrera de acceso", "OFERTA_INVISIBLE": "Oferta invisible",
           "OFERTA_SIN_REGISTRO": "Oferta sin registro", "IMPACTO_SOCIAL": "Impacto social"}
MESES = ["E", "F", "M", "A", "M", "J", "J", "A", "S", "O", "N", "D"]
MESES_LARGO = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"]


def nivel(fila, dimension: str) -> str:
    s = fila["semaforos"] or {}
    return (s.get(dimension) or {}).get("nivel", "gris")
