"""Capa de datos del tablero: todo sale de Supabase (esquema dw) con la publishable key.

Reemplaza al generador DEMO (`datos.py`). Cada lectura está en caché; si Supabase no responde se usa la copia local
de la base en `data/snapshot/` (mismos datos reales, exportados por `scripts/exportar_snapshot.py`) y el tablero lo
avisa con la fecha de la copia. No hay respaldo simulado.
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import streamlit as st

import supabase_cliente

RAIZ = Path(__file__).resolve().parent.parent
SNAPSHOT = RAIZ / "data" / "snapshot"
GEO_PATH = RAIZ / "data" / "geo" / "puebla_municipios.geojson"

# Objetos de dw que lee el tablero (también es la lista que exporta la copia local)
OBJETOS = {
    "v_vigente": "*", "v_ficha_municipio": "*", "v_ruta_parada": "*", "v_indice_municipio": "*",
    "fact_indice_oportunidad": "*", "fact_flag_oportunidad": "*", "dim_tipo_flag": "*",
    "v_concentracion_eje": "*", "fact_escenario_concentracion": "*", "fact_oferta_municipio_eje": "*",
    "fact_ruta_evaluacion": "ruta_sk,geom_trazo,km_carretera,min_carretera,fuente_trazo",
    "dim_fuente": "*", "dim_modelo": "nombre,tarea,algoritmo,periodo_entrenamiento,periodo_validacion,"
                                    "esquema_validacion,metricas,limitaciones",
    "fact_validacion": "*", "dim_actividad": "actividad_sk,codigo,nombre,icono,eje_sk", "dim_eje": "*",
    "dim_municipio": "municipio_sk,cve_geo,nombre,region,es_ancla,es_pueblo_magico,cabecera_nombre,"
                     "cabecera_lat,cabecera_lon",
    "v_lugar_circuito": "*", "fact_demanda_hotelera": "*", "v_aptitud_circuito": "*",
    "dim_circuito": "*", "fact_circuito_parada": "*",
    "fact_contexto_social": "municipio_sk,poblacion_total,indice_marginacion,grado_marginacion,pct_pobreza",
    "fact_actividad_municipio": "municipio_sk,actividad_sk,unidades,cociente_localizacion,nivel_predominancia,es_principal",
}


# Marca de proceso (no de sesión): las lecturas en caché se comparten entre sesiones, así que el aviso también.
_ESTADO = {"snapshot": False}


class SinDatos(RuntimeError):
    """Ni Supabase ni la copia local tienen el objeto pedido."""


def _desde_snapshot(tabla: str) -> pd.DataFrame:
    archivo = SNAPSHOT / f"{tabla}.jsonl"
    if not archivo.exists():
        raise SinDatos(f"Supabase no respondió y no hay copia local de dw.{tabla}")
    _ESTADO["snapshot"] = True
    return pd.read_json(archivo, lines=True, dtype=False)


def _leer(tabla: str, filtro: str = "") -> pd.DataFrame:
    select = OBJETOS.get(tabla, "*")
    if supabase_cliente.configurado():
        try:
            return supabase_cliente.leer(tabla, "dw", select, filtro=filtro)
        except Exception:  # noqa: BLE001 - sin red o sin servicio: copia local
            pass
    df = _desde_snapshot(tabla)
    if filtro:  # solo filtros de igualdad "col=eq.valor" sobre la copia
        col, _, valor = filtro.partition("=eq.")
        df = df[df[col].astype(str) == valor]
    return df


def fuente() -> str:
    """'supabase' o 'snapshot <fecha>' para el pie de página."""
    if _ESTADO["snapshot"]:
        leeme = SNAPSHOT / "LEEME.txt"
        fecha = leeme.read_text(encoding="utf-8").splitlines()[1] if leeme.exists() else ""
        return f"Copia local de la base ({fecha})"
    return "Supabase"


def fondo_mapa():
    """Mosaicos satelitales solo con red; con la copia local, el mapa se dibuja sobre los polígonos."""
    import mapas
    return None if _ESTADO["snapshot"] else mapas.FONDO_ESTADO


def _cve(df: pd.DataFrame) -> pd.DataFrame:
    if "cve_geo" in df:
        df["cve_geo"] = df.cve_geo.astype(str).str.strip().str.zfill(5)
    return df


# ------------------------------------------------------------------ lecturas
@st.cache_data(ttl=86400, show_spinner=False)
def vigente() -> dict:
    return _leer("v_vigente").iloc[0].to_dict()


@st.cache_data(ttl=86400, show_spinner=False)
def geo() -> dict:
    return json.loads(GEO_PATH.read_text(encoding="utf-8"))


@st.cache_data(ttl=3600, show_spinner="Leyendo municipios…")
def municipios() -> pd.DataFrame:
    return _cve(_leer("dim_municipio")).sort_values("nombre")


@st.cache_data(ttl=3600, show_spinner="Leyendo la ficha técnica…")
def ficha() -> pd.DataFrame:
    return _cve(_leer("v_ficha_municipio"))


@st.cache_data(ttl=3600, show_spinner="Leyendo rutas…")
def rutas() -> pd.DataFrame:
    """Una fila por parada: rutas oficiales, propuestas del modelo y descartadas (v_ruta_parada)."""
    return _cve(_leer("v_ruta_parada")).sort_values(["ruta_sk", "orden_parada"])


@st.cache_data(ttl=3600, show_spinner=False)
def trazos() -> dict:
    """{ruta_sk: dict(geom, km, min, fuente)} con el trazo por carretera guardado por el pipeline."""
    df = _leer("fact_ruta_evaluacion")
    return {int(r.ruta_sk): dict(geom=r.geom_trazo, km=r.km_carretera, min=r.min_carretera, fuente=r.fuente_trazo)
            for r in df.itertuples() if isinstance(r.geom_trazo, dict)}


@st.cache_data(ttl=3600, show_spinner=False)
def indice_municipio() -> pd.DataFrame:
    return _cve(_leer("v_indice_municipio"))


@st.cache_data(ttl=3600, show_spinner=False)
def indice_detalle() -> pd.DataFrame:
    """Componentes del índice por municipio × eje en la versión vigente."""
    v = vigente()["version_indice_sk"]
    return _leer("fact_indice_oportunidad", f"version_sk=eq.{v}")


@st.cache_data(ttl=3600, show_spinner=False)
def banderas() -> pd.DataFrame:
    """Banderas activas de la versión vigente, con código y descripción."""
    v = vigente()["version_indice_sk"]
    f = _leer("fact_flag_oportunidad", f"version_sk=eq.{v}")
    f = f[f.flag_activo.astype(bool)]
    return f.merge(_leer("dim_tipo_flag"), on="tipo_flag_sk")


@st.cache_data(ttl=3600, show_spinner=False)
def concentracion() -> pd.DataFrame:
    p = vigente()["periodo_oferta_sk"]
    return _leer("v_concentracion_eje", f"periodo_sk=eq.{p}")


@st.cache_data(ttl=3600, show_spinner=False)
def escenarios() -> pd.DataFrame:
    return _leer("fact_escenario_concentracion").set_index("escenario")


@st.cache_data(ttl=3600, show_spinner=False)
def oferta() -> pd.DataFrame:
    """Personal estimado por municipio × eje en el periodo vigente (DENUE)."""
    p = vigente()["periodo_oferta_sk"]
    return _leer("fact_oferta_municipio_eje", f"periodo_sk=eq.{p}")


@st.cache_data(ttl=3600, show_spinner=False)
def actividades() -> pd.DataFrame:
    return _leer("dim_actividad")


@st.cache_data(ttl=3600, show_spinner=False)
def ejes() -> pd.DataFrame:
    return _leer("dim_eje")


@st.cache_data(ttl=3600, show_spinner=False)
def fuentes() -> pd.DataFrame:
    return _leer("dim_fuente").sort_values("fuente_sk")


@st.cache_data(ttl=3600, show_spinner=False)
def modelos() -> pd.DataFrame:
    return _leer("dim_modelo")


@st.cache_data(ttl=3600, show_spinner=False)
def validaciones() -> pd.DataFrame:
    return _leer("fact_validacion").sort_values("codigo")


@st.cache_data(ttl=3600, show_spinner=False)
def demanda_hotelera() -> pd.DataFrame:
    return _leer("fact_demanda_hotelera")


@st.cache_data(ttl=3600, show_spinner=False)
def lugares(municipio_sk: int) -> pd.DataFrame:
    """Puntos visitables de un municipio (v_lugar_circuito), mejor prioridad primero."""
    df = _leer("v_lugar_circuito", f"municipio_sk=eq.{int(municipio_sk)}")
    if df.empty:  # municipio sin ningún lugar: la API no devuelve columnas
        return pd.DataFrame(columns=["lugar_id", "municipio_sk", "nombre", "actividad", "categoria", "tipo_parada",
                                     "origen", "url", "personal_est", "lat", "lon", "prioridad"])
    return df.sort_values(["prioridad", "nombre"])


@st.cache_resource(ttl=86400, show_spinner="Cargando las reglas de rutas (una vez al día)…")
def insumos():
    """Los MISMOS insumos que usa el optimizador del pipeline (model/insumos.py), con la publishable key.
    Requieren conexión: no se guardan en la copia local."""
    import insumos as ins_mod
    try:
        return ins_mod.cargar(secreta=False)
    except Exception as e:  # noqa: BLE001
        raise SinDatos(f"no se pudieron cargar las reglas de rutas ({e.__class__.__name__}); requieren conexión") from e


@st.cache_data(ttl=3600, show_spinner=False)
def circuitos() -> tuple[pd.DataFrame, pd.DataFrame]:
    """Circuitos precalculados (dim_circuito) y sus paradas (fact_circuito_parada)."""
    return _leer("dim_circuito"), _leer("fact_circuito_parada").sort_values(["circuito_sk", "orden"])


@st.cache_data(ttl=3600, show_spinner=False)
def aptitud_circuitos() -> pd.DataFrame:
    """Aptitud de cada municipio para un circuito (v_aptitud_circuito), por potencial."""
    return _cve(_leer("v_aptitud_circuito")).sort_values("potencial_circuito", ascending=False)


@st.cache_data(ttl=3600, show_spinner=False)
def contexto() -> pd.DataFrame:
    return _leer("fact_contexto_social").set_index("municipio_sk")


@st.cache_data(ttl=3600, show_spinner=False)
def actividad_municipio() -> pd.DataFrame:
    return _leer("fact_actividad_municipio").merge(actividades(), on="actividad_sk")
