"""Anillo A1 · Actividades turísticas por municipio a partir del DENUE + catálogos oficiales.

Salidas:
  data/derivados/actividad_municipio.csv   217 municipios × 14 actividades (unidades, personal, CL, nivel, principal)
  data/derivados/totales_municipio.csv     unidades y personal total, hospedaje y alimentos por municipio
  dw.dim_actividad y dw.fact_actividad_municipio en Supabase (si existen las tablas de sql/05)

Uso:
    python scripts/calcular_actividades.py ruta/denue_inegi_21_.csv [--sin-bd]
DENUE: https://www.inegi.org.mx/contenidos/masiva/denue/denue_21_csv.zip
"""
import csv
import math
import re
import sys
import unicodedata
from pathlib import Path

import numpy as np
import pandas as pd

RAIZ = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(RAIZ / "dashboard"), str(RAIZ / "model"), str(RAIZ / "scripts")]

from actividades import (ACTIVIDADES, PUNTO_MEDIO, REGLAS, ZONAS_ARQUEOLOGICAS,  # noqa: E402
                         nivel_predominancia)
from cargar_rutas_existentes import cargar_municipios  # noqa: E402

SALIDA = RAIZ / "data" / "derivados"
CORTE_DENUE = "DENUE 2026-05"
TOP_PRINCIPALES = 3
PESO_CL, PESO_VOLUMEN, PESO_CATALOGO = 0.5, 0.3, 0.2
# Actividades que el DENUE no registra: una zona INAH abierta es atractivo principal; el patrimonio religioso, secundario.
SCORE_SOLO_CATALOGO = {"arqueologia": 0.9, "religioso": 0.6}


def sin_acentos(s: pd.Series) -> pd.Series:
    return s.fillna("").str.lower().map(
        lambda t: "".join(c for c in unicodedata.normalize("NFKD", t) if not unicodedata.combining(c)))


def leer_denue(ruta: str) -> pd.DataFrame:
    cols = ["id", "nom_estab", "raz_social", "codigo_act", "per_ocu", "cve_mun"]
    try:
        df = pd.read_csv(ruta, dtype=str, usecols=cols, encoding="utf-8")
    except UnicodeDecodeError:
        df = pd.read_csv(ruta, dtype=str, usecols=cols, encoding="latin-1")
    df["cve_geo"] = "21" + df.cve_mun.str.zfill(3)
    df["personal"] = df.per_ocu.map(PUNTO_MEDIO).fillna(2.5)
    df["texto"] = sin_acentos(df.nom_estab + " " + df.raz_social.fillna(""))
    return df


def senales_catalogo(buscar) -> dict:
    """{(cve_geo, actividad): True} a partir de los temas de rutas oficiales y las zonas INAH."""
    temas = {}
    with (RAIZ / "data" / "catalogos" / "rutas_existentes.csv").open(encoding="utf-8") as f:
        for r in csv.DictReader(f):
            temas.setdefault(buscar(r["municipio"])["cve_geo"], set()).add(r["tema"])
    out = {}
    for act, regla in REGLAS.items():
        for cve, ts in temas.items():
            if ts & set(regla["catalogo"]):
                out[(cve, act)] = True
    for cve in ZONAS_ARQUEOLOGICAS:
        out[(cve, "arqueologia")] = True
    return out


def detectar(df: pd.DataFrame) -> dict:
    """{actividad: DataFrame de establecimientos que la tienen, con la señal que la detectó}."""
    res = {}
    for act, r in REGLAS.items():
        por_scian = df.codigo_act.str.startswith(r["scian"]) if r["scian"] else pd.Series(False, index=df.index)
        por_nombre = pd.Series(False, index=df.index)
        if r["nombre"]:
            en = df.codigo_act.str.startswith(tuple(r["nombre_en"])) if r["nombre_en"] else True
            por_nombre = en & df.texto.str.contains(r["nombre"], regex=True)
        sel = df[por_scian | por_nombre].copy()
        sel["por_scian"] = por_scian[sel.index]
        sel["por_nombre"] = por_nombre[sel.index] & ~sel.por_scian
        res[act] = sel
    return res


def pct_rank(s: pd.Series) -> pd.Series:
    return s.rank(pct=True) if s.notna().any() else s


def calcular(df: pd.DataFrame, municipios: list, catalogo: dict) -> tuple[pd.DataFrame, pd.DataFrame]:
    tot = df.groupby("cve_geo").agg(unidades_total=("id", "size"), personal_total=("personal", "sum"))
    tot["unidades_hospedaje"] = df[df.codigo_act.str.startswith("721")].groupby("cve_geo").size()
    tot["personal_hospedaje"] = df[df.codigo_act.str.startswith("721")].groupby("cve_geo").personal.sum()
    tot["unidades_alimentos"] = df[df.codigo_act.str.startswith("7225")].groupby("cve_geo").size()
    tot["personal_alimentos"] = df[df.codigo_act.str.startswith("7225")].groupby("cve_geo").personal.sum()
    tot = tot.reindex([m["cve_geo"] for m in municipios]).fillna(0)
    personal_estado = tot.personal_total.sum()

    filas = []
    for act, sel in detectar(df).items():
        g = sel.groupby("cve_geo").agg(unidades=("id", "size"), personal_est=("personal", "sum"),
                                       senal_scian=("por_scian", "sum"), senal_nombre=("por_nombre", "sum"))
        ejemplos = (sel.assign(n=sel.nom_estab.fillna("").str.strip().str.title()).query("n != ''")
                    .sort_values("personal", ascending=False).groupby("cve_geo").n
                    .apply(lambda s: list(dict.fromkeys(s))[:3]))
        participacion_estatal = g.personal_est.sum() / personal_estado if len(g) else 0
        solo_catalogo = not REGLAS[act]["scian"] and not REGLAS[act]["nombre"]
        for m in municipios:
            c = m["cve_geo"]
            u = int(g.unidades.get(c, 0))
            p = float(g.personal_est.get(c, 0.0))
            cl = (p / tot.personal_total[c]) / participacion_estatal if u and participacion_estatal else 0.0
            cat = catalogo.get((c, act), False)
            nivel = ("reconocida" if cat else "sin_oferta") if solo_catalogo else nivel_predominancia(cl, u, cat)
            filas.append(dict(cve_geo=c, municipio=m["nombre"], actividad=act, unidades=u, personal_est=p,
                              cociente_localizacion=round(cl, 3), nivel_predominancia=nivel,
                              senal_scian=int(g.senal_scian.get(c, 0)), senal_nombre=int(g.senal_nombre.get(c, 0)),
                              senal_catalogo=cat, ejemplos=ejemplos.get(c, []), solo_catalogo=solo_catalogo))
    out = pd.DataFrame(filas)

    # Puntaje para elegir las actividades principales de cada municipio.
    con = out.unidades > 0
    out["p_cl"] = 0.0
    out["p_vol"] = 0.0
    out.loc[con, "p_cl"] = out[con].groupby("actividad").cociente_localizacion.transform(pct_rank)
    out.loc[con, "p_vol"] = out[con].groupby("actividad").unidades.transform(lambda s: pct_rank(np.log1p(s)))
    out["score"] = PESO_CL * out.p_cl + PESO_VOLUMEN * out.p_vol + PESO_CATALOGO * out.senal_catalogo
    sc = out.solo_catalogo & out.senal_catalogo
    out.loc[sc, "score"] = out.loc[sc, "actividad"].map(SCORE_SOLO_CATALOGO)
    out["score"] = out.score.round(4)
    out["rango_en_municipio"] = (out[out.score > 0].groupby("cve_geo").score
                                 .rank(ascending=False, method="first"))
    out["es_principal"] = out.rango_en_municipio.le(TOP_PRINCIPALES) & out.nivel_predominancia.ne("baja")
    out = out.drop(columns=["p_cl", "p_vol", "solo_catalogo"])
    return out, tot.reset_index()


def cargar_bd(out: pd.DataFrame):
    import supabase_cliente as sb
    import urllib.error

    try:
        sb._peticion("dim_actividad?select=actividad_sk&limit=1", True, "dw")
    except urllib.error.HTTPError:
        print("… Falta crear las tablas: corre sql/05_ddl_ficha_y_actividades.sql en el SQL Editor y repite.")
        return
    ejes = {r["codigo"]: r["eje_sk"] for r in sb._peticion("dim_eje?select=eje_sk,codigo", True, "dw")}
    actuales = {r["codigo"]: r["actividad_sk"] for r in sb._peticion("dim_actividad?select=actividad_sk,codigo", True, "dw")}
    for clave, nombre, icono, eje, desc in ACTIVIDADES:
        fila = dict(codigo=clave, nombre=nombre, icono=icono, eje_sk=ejes.get(eje), descripcion=desc,
                    reglas={k: (list(v) if isinstance(v, tuple) else v) for k, v in REGLAS[clave].items()})
        if clave in actuales:
            sb._peticion(f"dim_actividad?actividad_sk=eq.{actuales[clave]}", True, "dw", "PATCH", fila,
                         {"Prefer": "return=minimal"})
        else:
            actuales[clave] = sb._peticion("dim_actividad", True, "dw", "POST", fila,
                                           {"Prefer": "return=representation"})[0]["actividad_sk"]
    print(f"✓ dim_actividad: {len(ACTIVIDADES)} actividades")

    periodo = sb._peticion(f"dim_periodo?select=periodo_sk&etiqueta=eq.{CORTE_DENUE.replace(' ', '%20')}", True, "dw")
    if not periodo:
        raise SystemExit(f"No existe el periodo '{CORTE_DENUE}' en dw.dim_periodo (lo crea sql/05).")
    psk = periodo[0]["periodo_sk"]
    mun = sb.leer("dim_municipio", "dw", "municipio_sk,cve_geo", secreta=True)
    msk = dict(zip(mun.cve_geo.str.strip(), mun.municipio_sk))

    filas = [dict(municipio_sk=int(msk[r.cve_geo]), actividad_sk=int(actuales[r.actividad]), periodo_sk=psk,
                  unidades=int(r.unidades), personal_est=float(r.personal_est),
                  cociente_localizacion=float(r.cociente_localizacion), nivel_predominancia=r.nivel_predominancia,
                  score=float(r.score), rango_en_municipio=None if math.isnan(r.rango_en_municipio) else int(r.rango_en_municipio),
                  es_principal=bool(r.es_principal), senal_scian=int(r.senal_scian), senal_nombre=int(r.senal_nombre),
                  senal_catalogo=bool(r.senal_catalogo), ejemplos=list(r.ejemplos))
             for r in out.itertuples()]
    sb._peticion(f"fact_actividad_municipio?periodo_sk=eq.{psk}", True, "dw", "DELETE")
    sb.insertar("fact_actividad_municipio", filas, "dw")
    print(f"✓ fact_actividad_municipio: {len(filas)} filas (periodo {CORTE_DENUE})")


def main():
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    municipios, buscar = cargar_municipios()
    df = leer_denue(sys.argv[1])
    out, tot = calcular(df, municipios, senales_catalogo(buscar))

    SALIDA.mkdir(parents=True, exist_ok=True)
    out.assign(ejemplos=out.ejemplos.map(" | ".join)).to_csv(SALIDA / "actividad_municipio.csv", index=False)
    tot.to_csv(SALIDA / "totales_municipio.csv", index=False)

    activos = out[out.unidades.gt(0) | out.senal_catalogo]
    print(f"DENUE: {len(df):,} establecimientos · {df.cve_geo.nunique()} municipios")
    print("Municipios con cada actividad: " + ", ".join(
        f"{a} {n}" for a, n in activos.groupby("actividad").cve_geo.nunique().sort_values(ascending=False).items()))
    print(f"Municipios con ≥1 actividad principal: {out[out.es_principal].cve_geo.nunique()} de 217")

    # V3: ¿el DENUE (sin contar el catálogo) detecta la actividad en los municipios de su ruta oficial?
    for act in ("cafe", "mezcal"):
        ruta = out[(out.actividad == act) & out.senal_catalogo]
        hay = ruta[ruta.unidades > 0]
        print(f"V3 {act}: {len(hay)}/{len(ruta)} municipios de la ruta oficial con registro DENUE "
              f"({len(hay) / max(1, len(ruta)):.0%}); sin registro: {', '.join(ruta[ruta.unidades == 0].municipio)}")
    if "--sin-bd" not in sys.argv:
        cargar_bd(out)


if __name__ == "__main__":
    main()
