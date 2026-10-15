"""Carga y homologación de los datos base del modelo en Supabase (stg y dw).

Fuentes (todas oficiales o abiertas, ver dw.dim_fuente):
  DENUE 05/2026 (INEGI) · Censos Económicos 2019 y 2024 (INEGI, datos abiertos por entidad)
  ITER 2020 (INEGI) · Índice de marginación 2020 (CONAPO) · Pobreza municipal 2020 (CONEVAL)
  Marco Geoestadístico 2023 (INEGI) · OpenStreetMap · Zonas arqueológicas INAH

Tablas que escribe:
  dw.dim_scian, dw.bridge_scian_eje, stg.denue, stg.totales_municipio, dw.dim_establecimiento,
  dw.fact_oferta_municipio_eje, stg.censo_economico, dw.fact_censo_economico, dw.fact_contexto_social,
  dw.fact_accesibilidad, dw.fact_atractivo (+ filas de dw.dim_fuente)

Uso:
    python scripts/cargar_datos_base.py --denue CSV --ce2019 CSV --ce2024 CSV --catalogo CSV \
        --iter CSV --conapo XLSX --coneval XLSX --geo GEOJSON --osm DIR [--solo seccion,...]
Es idempotente: cada sección borra y reinserta lo suyo.
"""
import argparse
import json
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from shapely.geometry import shape
from shapely.strtree import STRtree

RAIZ = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(RAIZ / "dashboard"), str(RAIZ / "model")]

import supabase_cliente as sb  # noqa: E402
from actividades import PUNTO_MEDIO, ZONAS_ARQUEOLOGICAS  # noqa: E402

FECHA = "2026-10-14"
CORTE_DENUE = "DENUE 2026-05"
MIN_POR_KM_RECTA = 1.8  # mismo factor que las filas de accesibilidad ya cargadas (241.1 min / 133.96 km)

# Clases SCIAN 2023 → eje turístico (dw.dim_eje.codigo) con peso. Un prefijo cubre todas sus clases.
# Pesos < 1: actividades que atienden a visitantes y a residentes (bares, regalos, alfarería).
EJES_SCIAN = {
    "hospedaje": {"721": 1.0},
    "alimentos": {"7225": 1.0, "7224": 0.5},
    "turismo": {"712": 1.0, "713111": 1.0, "713112": 1.0, "713113": 1.0, "713114": 1.0, "713910": 1.0,
                "713998": 1.0, "5615": 1.0, "4871": 1.0, "4872": 1.0, "4879": 1.0},
    "comercio_turistico": {"465915": 1.0, "465912": 0.5, "465913": 0.3, "327111": 0.5},
}
# Códigos que se guardan del Censo Económico (los agregados existen tal cual en los archivos de INEGI).
CODIGOS_CE = ["721", "7224", "7225", "712", "713111", "713112", "713113", "713114", "713910", "713998",
              "5615", "487", "465912", "465913", "465915", "327111"]

FUENTES = [
    dict(nombre="Censos Económicos", version_corte="CE 2019 y CE 2024 (datos abiertos por entidad, Puebla)",
         url="https://www.inegi.org.mx/programas/ce/2024/", fecha_descarga=FECHA,
         licencia_terminos="Términos de Libre Uso de la Información del INEGI",
         cobertura="217 municipios; sector, subsector, rama y clase",
         calidad_notas="Celdas confidenciales vienen vacías (se marca hay_confidencial). CE 2014 no tiene descarga "
                       "directa por entidad; 2019 usa SCIAN 2018 y 2024 SCIAN 2023 (los códigos turísticos usados "
                       "no cambian entre versiones)."),
    dict(nombre="Censo de Población y Vivienda", version_corte="2020 · ITER (principales resultados por localidad)",
         url="https://www.inegi.org.mx/contenidos/programas/ccpv/2020/datosabiertos/iter/iter_21_cpv2020_csv.zip",
         fecha_descarga=FECHA, licencia_terminos="Términos de Libre Uso de la Información del INEGI",
         cobertura="217 municipios", calidad_notas="Renglones de total municipal (LOC = 0000)."),
    dict(nombre="Marginación municipal", version_corte="Índice de marginación 2020 (método DP2)",
         url="https://github.com/IndiceMx/IM_2020/blob/main/IMM_2020.xlsx", fecha_descarga=FECHA,
         licencia_terminos="Información pública", cobertura="2,469 municipios (217 de Puebla)",
         calidad_notas="Copia del archivo IMM_2020 publicada en el repositorio IndiceMx; el sitio de CONAPO "
                       "(gob.mx/conapo) bloquea descargas automáticas."),
    dict(clave="coneval", nombre="Medición de la pobreza municipal 2020", institucion="CONEVAL", tipo="Oficial",
         url="https://www.coneval.org.mx/Medicion/Documents/Pobreza_municipal/2020/Concentrado_indicadores_de_pobreza_2020.zip",
         version_corte="2020", fecha_descarga=FECHA, licencia_terminos="Información pública",
         cobertura="2,469 municipios", calidad_notas="Porcentaje de población en pobreza 2020.",
         uso_en_modelo="Necesidad social (A4)"),
]


# ------------------------------------------------------------------ utilidades
def periodo(etiqueta: str) -> int:
    r = sb._peticion(f"dim_periodo?select=periodo_sk&etiqueta=eq.{etiqueta.replace(' ', '%20')}", True, "dw")
    if not r:
        raise SystemExit(f"Falta el periodo '{etiqueta}' en dw.dim_periodo")
    return r[0]["periodo_sk"]


def borrar(tabla: str, filtro: str, esquema: str = "dw"):
    sb._peticion(f"{tabla}?{filtro}", True, esquema, "DELETE")


def insertar(tabla: str, filas: list, esquema: str = "dw", lote: int = 1000):
    for i in range(0, len(filas), lote):
        sb._peticion(tabla, True, esquema, "POST", filas[i:i + lote], {"Prefer": "return=minimal"})


def limpiar(v):
    if v is None or (isinstance(v, float) and (math.isnan(v) or math.isinf(v))):
        return None
    if isinstance(v, (np.integer,)):
        return int(v)
    if isinstance(v, (np.floating,)):
        return float(v)
    return v


def registros(df: pd.DataFrame) -> list:
    return [{k: limpiar(v) for k, v in r.items()} for r in df.to_dict("records")]


def peso_eje(codigo: str) -> dict:
    """{eje: peso} para una clase SCIAN (el prefijo más largo que coincide gana)."""
    out = {}
    for eje, reglas in EJES_SCIAN.items():
        coinc = [p for p in reglas if codigo.startswith(p)]
        if coinc:
            out[eje] = reglas[max(coinc, key=len)]
    return out


def nivel(cl: float, unidades: float) -> str:
    if unidades <= 0:
        return "sin_oferta"
    if cl >= 2 and unidades >= 3:
        return "muy_alta"
    if cl >= 1.25 and unidades >= 2:
        return "alta"
    if cl >= 0.75:
        return "media"
    return "baja"


# ------------------------------------------------------------------ secciones
def fuentes():
    existentes = {r["nombre"]: r["fuente_sk"] for r in sb._peticion("dim_fuente?select=fuente_sk,nombre", True, "dw")}
    for f in FUENTES:
        fila = {k: v for k, v in f.items() if k != "clave"}
        if f["nombre"] in existentes:
            sb._peticion(f"dim_fuente?fuente_sk=eq.{existentes[f['nombre']]}", True, "dw", "PATCH", fila,
                         {"Prefer": "return=minimal"})
        else:
            sb._peticion("dim_fuente", True, "dw", "POST", fila, {"Prefer": "return=minimal"})
    print("✓ dim_fuente: Censos Económicos, Censo 2020, CONAPO completadas; CONEVAL agregada")


def scian(catalogo: str, denue: pd.DataFrame) -> dict:
    cat = pd.read_csv(catalogo, dtype=str).dropna(subset=["CODIGO"])
    cat["CODIGO"] = cat.CODIGO.str.strip()
    cat = cat[cat.CODIGO.str.fullmatch(r"\d{2,6}")][["CODIGO", "DESC_CODIGO"]]
    extra = denue[["codigo_act", "nombre_act"]].drop_duplicates("codigo_act").rename(
        columns={"codigo_act": "CODIGO", "nombre_act": "DESC_CODIGO"})
    cat = pd.concat([cat, extra[~extra.CODIGO.isin(cat.CODIGO)]]).drop_duplicates("CODIGO")
    filas = [dict(codigo_scian=c, descripcion=d.strip(), sector=c[:2], subsector=c[:3] if len(c) >= 3 else None,
                  rama=c[:4] if len(c) >= 4 else None, es_turistico=bool(peso_eje(c)) and len(c) == 6)
             for c, d in zip(cat.CODIGO, cat.DESC_CODIGO)]

    borrar("bridge_scian_eje", "scian_sk=not.is.null")
    actuales = {r["codigo_scian"].strip(): r["scian_sk"] for r in
                sb.leer("dim_scian", "dw", "scian_sk,codigo_scian", secreta=True).to_dict("records")}
    nuevas = [f for f in filas if f["codigo_scian"] not in actuales]
    insertar("dim_scian", nuevas)
    for f in filas:
        if f["codigo_scian"] in actuales:
            sb._peticion(f"dim_scian?scian_sk=eq.{actuales[f['codigo_scian']]}", True, "dw", "PATCH", f,
                         {"Prefer": "return=minimal"})
    sk = {r["codigo_scian"].strip(): r["scian_sk"] for r in
          sb.leer("dim_scian", "dw", "scian_sk,codigo_scian", secreta=True).to_dict("records")}

    ejes = {r["codigo"]: r["eje_sk"] for r in sb._peticion("dim_eje?select=eje_sk,codigo", True, "dw")}
    puente = [dict(scian_sk=sk[f["codigo_scian"]], eje_sk=ejes[e], peso=p)
              for f in filas if len(f["codigo_scian"]) == 6 for e, p in peso_eje(f["codigo_scian"]).items()]
    insertar("bridge_scian_eje", puente)
    print(f"✓ dim_scian: {len(filas)} códigos SCIAN ({sum(f['es_turistico'] for f in filas)} turísticos) · "
          f"bridge_scian_eje: {len(puente)} filas")
    return sk


def leer_denue(ruta: str) -> pd.DataFrame:
    cols = ["id", "nom_estab", "codigo_act", "nombre_act", "per_ocu", "cve_ent", "cve_mun", "latitud", "longitud",
            "fecha_alta"]
    d = pd.read_csv(ruta, dtype=str, usecols=cols, encoding="latin-1")
    d["cve_mun"] = d.cve_mun.str.zfill(3)
    d["cve_geo"] = "21" + d.cve_mun
    d["personal"] = d.per_ocu.map(PUNTO_MEDIO).fillna(2.5)
    d["pesos"] = d.codigo_act.map(peso_eje)
    return d


def denue(d: pd.DataFrame, sk_scian: dict, msk: dict):
    tot = d.groupby("cve_geo").agg(unidades_total=("id", "size"), personal_est_total=("personal", "sum")).reset_index()
    tot["corte_denue"] = CORTE_DENUE
    borrar("totales_municipio", "cve_geo=not.is.null", "stg")
    insertar("totales_municipio", registros(tot), "stg")

    tur = d[d.pesos.map(bool)].copy()
    stg = tur.rename(columns={"id": "id_denue"})[["id_denue", "nom_estab", "codigo_act", "nombre_act", "per_ocu",
                                                   "cve_ent", "cve_mun", "latitud", "longitud", "fecha_alta"]].copy()
    stg["latitud"] = pd.to_numeric(stg.latitud, errors="coerce")
    stg["longitud"] = pd.to_numeric(stg.longitud, errors="coerce")
    stg["corte_denue"] = CORTE_DENUE
    borrar("denue", "id_denue=not.is.null", "stg")
    insertar("denue", registros(stg), "stg")

    estratos = {r["rango_texto"]: r["estrato_sk"] for r in sb._peticion("dim_estrato_personal?select=*", True, "dw")}
    psk = periodo(CORTE_DENUE)
    est = [dict(id_denue=r.id, municipio_sk=int(msk[r.cve_geo]), scian_sk=int(sk_scian[r.codigo_act]),
                estrato_sk=int(estratos.get(r.per_ocu, 1)), periodo_sk=psk,
                nombre=r.nom_estab.strip()[:200] if isinstance(r.nom_estab, str) and r.nom_estab.strip() else None,
                geom=f"SRID=4326;POINT({r.longitud} {r.latitud})" if pd.notna(r.latitud) else None)
           for r in tur.itertuples()]
    borrar("dim_establecimiento", f"periodo_sk=eq.{psk}")
    insertar("dim_establecimiento", est)
    print(f"✓ stg.totales_municipio: {len(tot)} · stg.denue: {len(stg):,} establecimientos turísticos · "
          f"dim_establecimiento: {len(est):,}")
    return tot


def oferta(d: pd.DataFrame, tot: pd.DataFrame, msk: dict):
    ejes = {r["codigo"]: r["eje_sk"] for r in sb._peticion("dim_eje?select=eje_sk,codigo", True, "dw")}
    largo = [(r.cve_geo, e, p, r.personal) for r in d[d.pesos.map(bool)].itertuples() for e, p in r.pesos.items()]
    t = pd.DataFrame(largo, columns=["cve_geo", "eje", "peso", "personal"])
    t["unidades"] = t.peso
    t["personal_est"] = t.peso * t.personal
    # Solo los 4 ejes: el DDL del Rol A no admite eje_sk = 0 (global) en esta tabla.
    g = t.groupby(["cve_geo", "eje"])[["unidades", "personal_est"]].sum().reset_index()

    total = tot.set_index("cve_geo").personal_est_total
    estado_total = total.sum()
    psk = periodo(CORTE_DENUE)
    filas = []
    for eje, gg in g.groupby("eje"):
        gg = gg.set_index("cve_geo").reindex(total.index).fillna(0)
        estado_eje = gg.personal_est.sum()
        cl = (gg.personal_est / total) / (estado_eje / estado_total)
        rank = gg.personal_est.rank(ascending=False, method="min")
        for c, r in gg.iterrows():
            filas.append(dict(municipio_sk=int(msk[c]), eje_sk=ejes[eje], periodo_sk=psk,
                              unidades=round(float(r.unidades), 2), personal_est=round(float(r.personal_est), 2),
                              participacion_estatal=round(float(r.personal_est / estado_eje), 6),
                              cociente_localizacion=round(float(cl[c]), 4),
                              # El DDL del Rol A solo admite Alta/Media/Baja: muy alta → Alta, sin oferta → NULL
                              nivel_predominancia={"muy_alta": "Alta", "alta": "Alta", "media": "Media",
                                                   "baja": "Baja"}.get(nivel(float(cl[c]), float(r.unidades))),
                              ranking_estatal=int(rank[c])))
    borrar("fact_oferta_municipio_eje", f"periodo_sk=eq.{psk}")
    insertar("fact_oferta_municipio_eje", filas)
    print(f"✓ fact_oferta_municipio_eje: {len(filas)} filas (217 municipios × 4 ejes)")


def leer_ce(ruta: str, anio: int) -> pd.DataFrame:
    """Normaliza los dos formatos de INEGI a: cve_geo, codigo, unidades, personal, vacb."""
    if anio == 2019:  # los renglones traen una coma final: sin index_col=False se corre una columna
        df = pd.read_csv(ruta, dtype=str, index_col=False)
        df = df.rename(columns={"MUNICIPIO": "mun"})
        df = df[df.ID_ESTRATO.fillna("").str.strip() == ""]
        df["codigo"] = df.CODIGO.fillna("").str.strip().replace("", "TOTAL")
    else:
        df = pd.read_csv(ruta, dtype=str)
        df = df.rename(columns={"E04": "mun"})
        df = df[df.ID_ESTRATO.isna()]
        df["codigo"] = np.where(df.SECTOR.isna(), "TOTAL", df.CODIGO.fillna("").str.strip())
    df["mun"] = df.mun.fillna("").str.strip()
    df = df[df.mun != ""]
    df["cve_geo"] = "21" + df.mun.str.zfill(3)
    for c, n in (("UE", "unidades"), ("H001A", "personal"), ("A131A", "vacb")):
        df[n] = pd.to_numeric(df[c], errors="coerce")
    return df[["cve_geo", "codigo", "unidades", "personal", "vacb"]]


def censo(rutas: dict, msk: dict):
    ejes = {r["codigo"]: r["eje_sk"] for r in sb._peticion("dim_eje?select=eje_sk,codigo", True, "dw")}
    stg, fact = [], []
    for anio, ruta in rutas.items():
        ce = leer_ce(ruta, anio)
        sel = ce[ce.codigo.isin(CODIGOS_CE + ["TOTAL"])].drop_duplicates(["cve_geo", "codigo"])
        for r in sel.itertuples():
            entero = lambda v: None if pd.isna(v) else int(round(float(v)))
            stg.append(dict(cve_geo=r.cve_geo, anio_censal=anio, sector_scian=r.codigo,
                            unidades=entero(r.unidades), personal_ocupado=entero(r.personal),
                            va_censal_bruto=limpiar(r.vacb),
                            confidencial=bool(pd.notna(r.unidades) and r.unidades > 0 and pd.isna(r.personal))))
        psk = periodo(f"CE {anio}")
        piv = sel.set_index(["cve_geo", "codigo"])
        for c in msk:
            acum = {}
            for eje in EJES_SCIAN:
                u = p = v = 0.0
                conf = False
                for cod in CODIGOS_CE:
                    w = peso_eje(cod).get(eje, 0) if len(cod) == 6 else (EJES_SCIAN[eje].get(cod, 0))
                    if cod == "487":
                        w = 1.0 if eje == "turismo" else 0
                    if not w or (c, cod) not in piv.index:
                        continue
                    r = piv.loc[(c, cod)]
                    ue = 0.0 if pd.isna(r.unidades) else float(r.unidades)  # (NaN or 0) sería NaN
                    u += w * ue
                    if pd.isna(r.personal):
                        conf = conf or ue > 0
                    else:
                        p += w * r.personal
                        v += w * (r.vacb if pd.notna(r.vacb) else 0)
                acum[eje] = (u, p, v, conf)
                fact.append(dict(municipio_sk=int(msk[c]), eje_sk=ejes[eje], periodo_sk=psk, unidades=round(u),
                                 personal_ocupado=round(p), va_censal_bruto_mdp=round(v, 3), hay_confidencial=conf))
            # (sin fila global: el DDL del Rol A no admite eje_sk = 0 en esta tabla)
        tot = ce[ce.codigo == "TOTAL"]
        print(f"  CE {anio}: {tot.cve_geo.nunique()} municipios · personal ocupado total {tot.personal.sum():,.0f}")
    borrar("censo_economico", "cve_geo=not.is.null", "stg")
    insertar("censo_economico", stg, "stg")
    for anio in rutas:
        borrar("fact_censo_economico", f"periodo_sk=eq.{periodo(f'CE {anio}')}")
    insertar("fact_censo_economico", fact)
    print(f"✓ stg.censo_economico: {len(stg):,} filas · fact_censo_economico: {len(fact):,} filas")


def social(iter_csv: str, conapo: str, coneval: str, msk: dict):
    it = pd.read_csv(iter_csv, dtype=str, encoding="utf-8-sig")
    it = it[(it.LOC == "0000") & (it.MUN != "000")].copy()
    it["cve_geo"] = "21" + it.MUN
    it = it.set_index("cve_geo")
    pob = pd.to_numeric(it.POBTOT, errors="coerce")
    internet = 100 * pd.to_numeric(it.VPH_INTER, errors="coerce") / pd.to_numeric(it.VIVPAR_HAB, errors="coerce")

    im = pd.read_excel(conapo, sheet_name="IMM_2020", dtype={"CVE_MUN": str})
    im = im[im.CVE_MUN.str.startswith("21")].set_index("CVE_MUN")

    cv = pd.read_excel(coneval, sheet_name="Concentrado municipal", header=None, dtype=str)
    cv = cv[cv[3].astype(str).str.fullmatch(r"21\d{3}")].set_index(3)
    pobreza = pd.to_numeric(cv[10], errors="coerce")

    psk = periodo("Censo Pob 2020")
    filas = [dict(municipio_sk=int(msk[c]), periodo_sk=psk, poblacion_total=limpiar(pob.get(c)),
                  indice_marginacion=limpiar(round(float(im.IM_2020[c]), 4)) if c in im.index else None,
                  grado_marginacion=str(im.GM_2020[c]) if c in im.index else None,
                  pct_pobreza=limpiar(round(float(pobreza[c]), 2)) if c in pobreza.index else None,
                  pct_viviendas_internet=limpiar(round(float(internet[c]), 2)))
             for c in msk]
    borrar("fact_contexto_social", f"periodo_sk=eq.{psk}")
    insertar("fact_contexto_social", filas)
    faltan = [f for f in filas if f["indice_marginacion"] is None or f["pct_pobreza"] is None]
    print(f"✓ fact_contexto_social: {len(filas)} municipios (sin CONAPO/CONEVAL: {len(faltan)}) · "
          f"grados: {pd.Series([f['grado_marginacion'] for f in filas]).value_counts().to_dict()}")


def accesibilidad(geo_path: str, mun: pd.DataFrame):
    geo = json.loads(Path(geo_path).read_text(encoding="utf-8"))
    polys = {f["properties"]["CVEGEO"]: shape(f["geometry"]).buffer(0) for f in geo["features"]}
    claves = list(polys)
    arbol = STRtree([polys[c] for c in claves])
    vecinos = {c: {claves[j] for j in arbol.query(polys[c].buffer(0.001), predicate="intersects")} - {c}
               for c in claves}
    m = mun.set_index("cve_geo")
    lat, lon = np.radians(m.lat.to_numpy()), np.radians(m.lon.to_numpy())
    dlat, dlon = lat[:, None] - lat[None, :], lon[:, None] - lon[None, :]
    a = np.sin(dlat / 2) ** 2 + np.cos(lat[:, None]) * np.cos(lat[None, :]) * np.sin(dlon / 2) ** 2
    dist = 2 * 6371.0 * np.arcsin(np.sqrt(a))
    idx = list(m.index)
    filas = [dict(municipio_origen_sk=int(m.municipio_sk[o]), municipio_destino_sk=int(m.municipio_sk[d]),
                  distancia_km_recta=round(float(dist[i, j]), 2),
                  tiempo_min_est=round(float(dist[i, j]) * MIN_POR_KM_RECTA, 1), es_colindante=d in vecinos[o])
             for i, o in enumerate(idx) for j, d in enumerate(idx) if i != j]
    # Comparación con las filas que ya existían (cargadas por el ETL del Rol A)
    previas = sb.leer("fact_accesibilidad", "dw", secreta=True)
    if len(previas):
        nuevo = pd.DataFrame(filas).merge(previas, on=["municipio_origen_sk", "municipio_destino_sk"],
                                          suffixes=("", "_prev"))
        print(f"  accesibilidad previa: {len(previas)} filas · dif. media distancia "
              f"{(nuevo.distancia_km_recta - nuevo.distancia_km_recta_prev).abs().mean():.2f} km · "
              f"colindancia coincide {(nuevo.es_colindante == nuevo.es_colindante_prev).mean():.0%}")
    borrar("fact_accesibilidad", "municipio_origen_sk=not.is.null")
    insertar("fact_accesibilidad", filas, lote=2000)
    print(f"✓ fact_accesibilidad: {len(filas):,} pares (colindantes: {sum(f['es_colindante'] for f in filas)})")


def atractivos(osm_dir: str, geo_path: str, msk: dict):
    geo = json.loads(Path(geo_path).read_text(encoding="utf-8"))
    polys = {f["properties"]["CVEGEO"]: shape(f["geometry"]).buffer(0) for f in geo["features"]}
    claves = list(polys)
    arbol = STRtree([polys[c] for c in claves])
    from shapely.geometry import Point
    cat = {}
    for e in json.loads((Path(osm_dir) / "puntos.json").read_text(encoding="utf-8"))["elements"]:
        lat, lon = (e.get("lat"), e.get("lon")) if "lat" in e else (e.get("center", {}).get("lat"), e.get("center", {}).get("lon"))
        t = e.get("tags", {})
        if lat is None:
            continue
        if t.get("tourism") in ("attraction", "museum", "viewpoint"):
            k = t["tourism"]
        elif t.get("historic"):
            k = "historico_" + t["historic"]
        elif t.get("leisure") in ("nature_reserve", "water_park"):
            k = t["leisure"]
        elif t.get("tourism") in ("hotel", "motel", "guest_house", "hostel", "camp_site"):
            k = "hospedaje_osm"
        else:
            continue
        p = Point(lon, lat)
        for j in arbol.query(p, predicate="intersects"):
            cat[(claves[j], k)] = cat.get((claves[j], k), 0) + 1
            break
    fuentes_sk = {r["nombre"]: r["fuente_sk"] for r in sb._peticion("dim_fuente?select=fuente_sk,nombre", True, "dw")}
    osm = fuentes_sk["OpenStreetMap · red vial principal y servicios (Overpass)"]
    filas = [dict(municipio_sk=int(msk[c]), fuente_sk=osm, categoria=k, num_atractivos=n, fecha_corte=FECHA)
             for (c, k), n in cat.items()]
    inah = fuentes_sk["Catálogo de destinos y Pueblos Mágicos"]
    filas += [dict(municipio_sk=int(msk[c]), fuente_sk=inah, categoria="zona_arqueologica_inah", num_atractivos=1,
                   fecha_corte=FECHA) for c in ZONAS_ARQUEOLOGICAS]
    borrar("fact_atractivo", "municipio_sk=not.is.null")
    insertar("fact_atractivo", filas)
    print(f"✓ fact_atractivo: {len(filas)} filas · {len({f['municipio_sk'] for f in filas})} municipios con atractivos")


def main():
    ap = argparse.ArgumentParser()
    for a in ("--denue", "--ce2019", "--ce2024", "--catalogo", "--iter", "--conapo", "--coneval", "--geo", "--osm"):
        ap.add_argument(a)
    ap.add_argument("--solo", default="fuentes,scian,denue,oferta,censo,social,accesibilidad,atractivos")
    args = ap.parse_args()
    solo = set(args.solo.split(","))

    mun = sb.leer("dim_municipio", "dw", "municipio_sk,cve_geo", secreta=True)
    mun["cve_geo"] = mun.cve_geo.str.strip()
    geo_simple = json.loads((RAIZ / "data" / "geo" / "puebla_municipios.geojson").read_text(encoding="utf-8"))
    cent = pd.DataFrame([f["properties"] for f in geo_simple["features"]])[["cve_geo", "lon", "lat"]]
    mun = mun.merge(cent, on="cve_geo")
    msk = dict(zip(mun.cve_geo, mun.municipio_sk))

    if "fuentes" in solo:
        fuentes()
    d = leer_denue(args.denue) if solo & {"scian", "denue", "oferta"} else None
    sk_scian = scian(args.catalogo, d) if "scian" in solo else None
    tot = None
    if "denue" in solo:
        if sk_scian is None:
            sk_scian = {r["codigo_scian"].strip(): r["scian_sk"] for r in
                        sb.leer("dim_scian", "dw", "scian_sk,codigo_scian", secreta=True).to_dict("records")}
        tot = denue(d, sk_scian, msk)
    if "oferta" in solo:
        if tot is None:
            tot = d.groupby("cve_geo").agg(personal_est_total=("personal", "sum")).reset_index()
        oferta(d, tot, msk)
    if "censo" in solo:
        censo({2019: args.ce2019, 2024: args.ce2024}, msk)
    if "social" in solo:
        social(args.iter, args.conapo, args.coneval, msk)
    if "accesibilidad" in solo:
        accesibilidad(args.geo, mun)
    if "atractivos" in solo:
        atractivos(args.osm, args.geo, msk)


if __name__ == "__main__":
    main()
