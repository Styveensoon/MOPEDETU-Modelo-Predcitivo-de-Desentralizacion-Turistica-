"""Datos comunes de los modelos (anillos A5-A6), leídos de Supabase con la secret key.

Todas las piezas (índice, crecimiento, enlaces, rutas) parten de `cargar()` para trabajar sobre
exactamente los mismos datos. Las tablas por municipio quedan indexadas por municipio_sk.
"""
from __future__ import annotations

import sys
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "dashboard"))

import supabase_cliente as sb  # noqa: E402

EJES = {1: "hospedaje", 2: "alimentos", 3: "turismo", 4: "comercio_turistico"}


@dataclass
class Base:
    mun: pd.DataFrame          # identidad + centroide + región + PM/ancla
    oferta: pd.DataFrame       # municipio × eje (DENUE 2026-05)
    censo: pd.DataFrame        # municipio × eje × periodo (CE 2019, 2024)
    social: pd.DataFrame       # municipio (CONAPO, CONEVAL, ITER)
    infra: pd.DataFrame        # municipio × indicador (ancho)
    actividades: pd.DataFrame  # municipio × actividad
    cat_act: pd.DataFrame      # catálogo de actividades
    acceso: pd.DataFrame       # pares municipio_origen × destino
    atractivos: pd.DataFrame   # municipio × categoría
    temporadas: pd.DataFrame   # temporadas y eventos
    rutas: pd.DataFrame        # paradas de rutas existentes
    periodos: dict             # etiqueta → periodo_sk
    fuentes: dict              # nombre → fuente_sk


def pct(s: pd.Series) -> pd.Series:
    """Percentil en [0, 1] (empates promediados); NaN → 0.5 (sin dato = neutral, no castigo)."""
    return s.rank(pct=True, method="average").fillna(0.5)


@lru_cache(maxsize=1)
def cargar() -> Base:
    leer = lambda t, sel="*": sb.leer(t, "dw", sel, secreta=True)
    # Coordenadas de la cabecera municipal: los tiempos de fact_accesibilidad se calculan entre cabeceras
    mun = leer("dim_municipio", "municipio_sk,cve_geo,nombre,region,es_pueblo_magico,es_ancla,superficie_km2,"
                                "cabecera_nombre,cabecera_lat,cabecera_lon")
    mun["cve_geo"] = mun.cve_geo.str.strip()
    mun = mun.rename(columns={"cabecera_lat": "lat", "cabecera_lon": "lon"})
    mun[["lat", "lon"]] = mun[["lat", "lon"]].astype(float)
    mun = mun.set_index("municipio_sk").sort_index()

    periodos = {r["etiqueta"]: r["periodo_sk"] for r in sb._peticion("dim_periodo?select=*", True, "dw")}
    fuentes = {r["nombre"]: r["fuente_sk"] for r in sb._peticion("dim_fuente?select=fuente_sk,nombre", True, "dw")}

    oferta = leer("fact_oferta_municipio_eje")
    oferta = oferta[oferta.periodo_sk == periodos["DENUE 2026-05"]]
    censo = leer("fact_censo_economico")
    social = leer("fact_contexto_social").set_index("municipio_sk")
    infra = leer("fact_infraestructura", "municipio_sk,indicador,valor").pivot(
        index="municipio_sk", columns="indicador", values="valor")
    actividades = leer("fact_actividad_municipio")
    cat_act = leer("dim_actividad", "actividad_sk,codigo,nombre,icono,eje_sk")
    acceso = leer("fact_accesibilidad")
    atractivos = leer("fact_atractivo")
    temporadas = leer("fact_temporada")
    paradas = leer("fact_ruta_parada")
    dim_ruta = leer("dim_ruta", "ruta_sk,nombre,origen,tema")
    rutas = paradas.merge(dim_ruta, on="ruta_sk")
    return Base(mun, oferta, censo, social, infra, actividades, cat_act, acceso, atractivos, temporadas,
                rutas[rutas.origen == "existente"], periodos, fuentes)


def asegurar_modelo(fila: dict) -> int:
    """Crea o actualiza una fila de dw.dim_modelo identificada por nombre; devuelve modelo_sk."""
    r = sb._peticion(f"dim_modelo?select=modelo_sk&nombre=eq.{fila['nombre']}", True, "dw")
    if r:
        sb._peticion(f"dim_modelo?modelo_sk=eq.{r[0]['modelo_sk']}", True, "dw", "PATCH", fila,
                     {"Prefer": "return=minimal"})
        return r[0]["modelo_sk"]
    return sb._peticion("dim_modelo", True, "dw", "POST", fila, {"Prefer": "return=representation"})[0]["modelo_sk"]


PENDIENTES = RAIZ / "data" / "derivados" / "pendientes"


def publicar(modelo: dict, tabla: str, filas: list) -> int | None:
    """Registra el modelo en dim_modelo y escribe sus filas (con modelo_sk) en `tabla`.
    Si la base lo rechaza (p. ej. por una restricción del DDL), guarda todo en data/derivados/pendientes/
    para cargarlo después con `python model/publicar_pendientes.py`, y sigue."""
    import json
    import urllib.error
    try:
        sk = asegurar_modelo(modelo)
    except urllib.error.HTTPError as e:
        PENDIENTES.mkdir(parents=True, exist_ok=True)
        ruta = PENDIENTES / f"{modelo['nombre']}.json"
        ruta.write_text(json.dumps({"modelo": modelo, "tabla": tabla, "filas": filas}, ensure_ascii=False,
                                   default=str), encoding="utf-8")
        print(f"  ⚠ dim_modelo rechazó el registro ({e.msg.split('·')[-1][:160].strip()}). "
              f"Guardado en {ruta.relative_to(RAIZ)}")
        return None
    reemplazar(tabla, f"modelo_sk=eq.{sk}", [f | {"modelo_sk": sk} for f in filas])
    print(f"✓ dim_modelo #{sk} ({modelo['nombre']}) · {tabla}: {len(filas)} filas")
    return sk


def asegurar_version(nombre: str, descripcion: str, pesos: dict) -> int:
    r = sb._peticion(f"dim_version_calculo?select=version_sk&nombre=eq.{nombre}", True, "dw")
    if r:
        sb._peticion(f"dim_version_calculo?version_sk=eq.{r[0]['version_sk']}", True, "dw", "PATCH",
                     {"descripcion": descripcion, "pesos": pesos}, {"Prefer": "return=minimal"})
        return r[0]["version_sk"]
    return sb._peticion("dim_version_calculo", True, "dw", "POST",
                        {"nombre": nombre, "descripcion": descripcion, "pesos": pesos},
                        {"Prefer": "return=representation"})[0]["version_sk"]


def reemplazar(tabla: str, filtro: str, filas: list, lote: int = 1000):
    """Borra lo que cumple `filtro` y vuelve a insertar `filas` (idempotente por versión/modelo)."""
    sb._peticion(f"{tabla}?{filtro}", True, "dw", "DELETE")
    for i in range(0, len(filas), lote):
        sb._peticion(tabla, True, "dw", "POST", filas[i:i + lote], {"Prefer": "return=minimal"})


def limpio(v):
    if v is None or v is pd.NA:
        return None
    if isinstance(v, (np.floating, float)):
        return None if not np.isfinite(v) else float(v)
    if isinstance(v, (np.integer,)):
        return int(v)
    if isinstance(v, (np.bool_,)):
        return bool(v)
    return v
