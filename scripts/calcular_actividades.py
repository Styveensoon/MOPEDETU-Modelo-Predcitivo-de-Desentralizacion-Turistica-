"""Anillo A1 · Actividades turísticas por municipio a partir del DENUE + catálogos oficiales.

Salidas:
  data/derivados/actividad_municipio.csv   217 municipios × 14 actividades (unidades, personal, CL, nivel, principal)
  data/derivados/totales_municipio.csv     unidades y personal total, hospedaje y alimentos por municipio
  dw.dim_actividad y dw.fact_actividad_municipio en Supabase (si existen las tablas de sql/05)
  dw.fact_establecimiento_actividad: la misma detección, por negocio (sql/20, plan_migracion_front A9). Los
      negocios detectados que no estaban en dw.dim_establecimiento (productores de café, mezcal o bebidas, viveros:
      SCIAN fuera de los ejes turísticos) se agregan ahí con su clave del DENUE.
  dw.fact_lugar_circuito: puntos visitables (atractivos, experiencias, cocina tradicional) para rutas y circuitos.

Uso:
    python scripts/calcular_actividades.py ruta/denue_inegi_21_.csv [--sin-bd] [--solo-establecimientos] [--solo-lugares]
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
SENAL_OSM = {"religioso", "ecoturismo", "volcanes"}


def sin_acentos(s: pd.Series) -> pd.Series:
    return s.fillna("").str.lower().map(
        lambda t: "".join(c for c in unicodedata.normalize("NFKD", t) if not unicodedata.combining(c)))


def leer_denue(ruta: str) -> pd.DataFrame:
    cols = ["id", "nom_estab", "raz_social", "codigo_act", "per_ocu", "cve_mun", "latitud", "longitud"]
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
    # Lugares sin negocio detrás (El Peñón de Jonotla): el catálogo curado cuenta completo; de OSM solo
    # santuarios, naturaleza y volcanes (museos y zonas arqueológicas ya vienen del DENUE y del INAH).
    lugares = RAIZ / "data" / "derivados" / "atractivos_lugares.csv"
    if lugares.exists():
        for r in pd.read_csv(lugares, dtype=str).fillna("").itertuples():
            for act in filter(None, r.actividades.split("|")):
                if act in REGLAS and (r.origen == "catalogo_curado" or act in SENAL_OSM):
                    out[(r.cve_geo, act)] = True
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


def cargar_establecimientos(df: pd.DataFrame):
    """dw.fact_establecimiento_actividad con la detección de detectar(); agrega a dim_establecimiento los negocios
    detectados que faltan (mismo periodo, estrato y punto que el resto)."""
    import supabase_cliente as sb

    act_sk = {r["codigo"]: r["actividad_sk"] for r in sb._peticion("dim_actividad?select=actividad_sk,codigo", True, "dw")}
    psk = sb._peticion(f"dim_periodo?select=periodo_sk&etiqueta=eq.{CORTE_DENUE.replace(' ', '%20')}", True, "dw")[0]["periodo_sk"]
    det = pd.concat([sel.assign(actividad=act, senal=np.where(sel.por_scian, "scian", "nombre"))
                     [["id", "actividad", "senal"]] for act, sel in detectar(df).items() if len(sel)])
    det = det.drop_duplicates(["id", "actividad"])
    est = sb.leer("dim_establecimiento", "dw", "establecimiento_sk,id_denue", secreta=True)
    sk = dict(zip(est.id_denue.astype(str), est.establecimiento_sk))
    faltan = df[df.id.isin(set(det.id) - set(sk)) & df.nom_estab.notna()].copy()
    if len(faltan):
        scian = dict(zip(*[sb.leer("dim_scian", "dw", "scian_sk,codigo_scian", secreta=True)[c]
                           for c in ("codigo_scian", "scian_sk")]))
        scian = {str(k).strip(): v for k, v in scian.items()}
        estratos = {r["rango_texto"]: r["estrato_sk"] for r in sb._peticion("dim_estrato_personal?select=*", True, "dw")}
        mun = sb.leer("dim_municipio", "dw", "municipio_sk,cve_geo", secreta=True)
        msk = dict(zip(mun.cve_geo.str.strip(), mun.municipio_sk))
        nuevos = [dict(id_denue=r.id, municipio_sk=int(msk[r.cve_geo]), scian_sk=int(scian[r.codigo_act]),
                       estrato_sk=int(estratos.get(r.per_ocu, 1)), periodo_sk=psk, nombre=r.nom_estab.strip()[:200],
                       geom=f"SRID=4326;POINT({r.longitud} {r.latitud})" if pd.notna(r.latitud) else None)
                  for r in faltan.itertuples() if r.codigo_act in scian]
        sb.insertar("dim_establecimiento", nuevos, "dw")
        est = sb.leer("dim_establecimiento", "dw", "establecimiento_sk,id_denue", secreta=True)
        sk = dict(zip(est.id_denue.astype(str), est.establecimiento_sk))
        print(f"✓ dim_establecimiento: {len(nuevos)} negocios agregados (detectados por actividad, fuera de los ejes)")
    det = det[det.id.isin(sk) & det.actividad.isin(act_sk)]
    filas = [dict(establecimiento_sk=int(sk[r.id]), actividad_sk=int(act_sk[r.actividad]), senal=r.senal)
             for r in det.itertuples()]
    sb._peticion("fact_establecimiento_actividad?establecimiento_sk=not.is.null", True, "dw", "DELETE")
    sb.insertar("fact_establecimiento_actividad", filas, "dw")
    print(f"✓ fact_establecimiento_actividad: {len(filas):,} filas · por actividad: "
          + ", ".join(f"{a} {n}" for a, n in det.actividad.value_counts().items()))



EXPERIENCIAS = ("cafe", "mezcal", "bebidas_tradicionales", "artesanias", "flores_viveros")
ACENTOS = str.maketrans("ÁÉÍÓÚÜÑáéíóúüñ", "AEIOUUNaeiouun")


def _redondeo_sql(v: pd.Series) -> pd.Series:
    """round() de PostgreSQL sobre numeric: mitades lejos de cero (Python redondea al par)."""
    return np.sign(v) * np.floor(np.abs(v) + 0.5)


def calcular_lugares(df: pd.DataFrame, solo: bool = False):
    """dw.fact_lugar_circuito: puntos visitables para rutas y circuitos (especificación en sql/21_lugar_circuito.sql).
    prioridad: 1 curado · 2 lugar OSM con actividad · 3 negocio 712/713 de bridge_scian_eje · 4 experiencia por SCIAN ·
    5 experiencia por nombre · 6 lugar OSM sin actividad · 7 cocina tradicional (7225 con actividad gastronomía).
    Sin negocios registrados como "SIN NOMBRE" ni sin coordenadas; duplicados (mismo nombre a ~50 m) fuera."""
    import supabase_cliente as sb

    est = sb.leer("dim_establecimiento", "dw", "establecimiento_sk,id_denue,municipio_sk", secreta=True)
    est["id_denue"] = est.id_denue.astype(str)
    det = pd.concat([sel.assign(actividad=act, senal=np.where(sel.por_scian, "scian", "nombre"))[["id", "actividad", "senal"]]
                     for act, sel in detectar(df).items() if len(sel)]).drop_duplicates(["id", "actividad"])
    br = sb.leer("bridge_scian_eje", "dw", "scian_sk", secreta=True)
    sc = sb.leer("dim_scian", "dw", "scian_sk,codigo_scian", secreta=True)
    sc["codigo_scian"] = sc.codigo_scian.astype(str).str.strip()
    scian_atr = set(sc[sc.scian_sk.isin(br.scian_sk) & sc.codigo_scian.str.match(r"71[23]")].codigo_scian)

    d = df.merge(est, left_on="id", right_on="id_denue")
    d["nombre"] = d.nom_estab.fillna("").str.strip().str[:200]
    d["lat"] = pd.to_numeric(d.latitud, errors="coerce")
    d["lon"] = pd.to_numeric(d.longitud, errors="coerce")
    d = d[(d.nombre != "") & ~d.nombre.str.contains("sin nombre", case=False) & d.lat.notna() & d.lon.notna()]
    d["personal_est"] = d.per_ocu.map(PUNTO_MEDIO)
    d["lugar_id"] = "de:" + d.establecimiento_sk.astype(str)
    a = det.merge(d[["id", "lugar_id", "municipio_sk", "nombre", "codigo_act", "personal_est", "lat", "lon"]], on="id")

    atr = d[d.codigo_act.isin(scian_atr)].copy()
    atr["actividad"] = atr.id.map(det.groupby("id").actividad.min())
    atr["categoria"] = np.select([atr.codigo_act.isin(["712111", "712112"]), atr.codigo_act.str.startswith("7121"),
                                  atr.codigo_act.isin(["713113", "713114"])], ["museo", "patrimonio", "balneario"],
                                 "recreacion")
    atr = atr.assign(tipo_parada="atractivo", origen="denue", prioridad=3)
    exp = a[a.actividad.isin(EXPERIENCIAS) & ~a.codigo_act.isin(scian_atr)].copy()
    exp = exp.assign(categoria=exp.actividad, tipo_parada="experiencia", origen="denue",
                     prioridad=np.where(exp.senal == "scian", 4, 5))
    com = a[(a.actividad == "gastronomia") & a.codigo_act.str.startswith("7225")].copy()
    com = com.assign(categoria="comida", tipo_parada="comida", origen="denue", prioridad=7)

    lug = sb.leer("fact_atractivo_lugar", "dw", "atractivo_sk,municipio_sk,nombre,categoria,actividades,lat,lon,origen,url",
                  secreta=True)
    con_act = lug.actividades.map(lambda x: bool(x))
    # Templos y parroquias no son señal de actividad religiosa del municipio (no inflan A1), pero sí son paradas
    # religiosas reales: para el circuito temático cuentan como 'religioso'. La prioridad no cambia.
    actividad = lug.actividades.map(lambda x: x[0] if x else None)
    actividad = actividad.where(actividad.notna() | ~lug.categoria.isin(["templo", "santuario"]), "religioso")
    al = pd.DataFrame({
        "lugar_id": "al:" + lug.atractivo_sk.astype(str), "municipio_sk": lug.municipio_sk, "nombre": lug.nombre,
        "actividad": actividad, "categoria": lug.categoria,
        "tipo_parada": "atractivo", "origen": np.where(lug.origen == "catalogo_curado", "curado", "osm"),
        "url": lug.url, "personal_est": np.nan, "lat": pd.to_numeric(lug.lat), "lon": pd.to_numeric(lug.lon),
        "prioridad": np.where(lug.origen == "catalogo_curado", 1, np.where(con_act, 2, 6))})

    cols = ["lugar_id", "municipio_sk", "nombre", "actividad", "categoria", "tipo_parada", "origen", "url",
            "personal_est", "lat", "lon", "prioridad"]
    todos = pd.concat([al[cols]] + [x.assign(url=None)[cols] for x in (atr, exp, com)], ignore_index=True)
    # un renglón por lugar (mejor prioridad, luego actividad)
    todos = todos.sort_values(["lugar_id", "prioridad", "actividad"], na_position="last").drop_duplicates("lugar_id")
    # mismo nombre normalizado en la misma celda de ~50 m: queda el de mejor prioridad y más personal
    todos["_n"] = todos.nombre.str.strip().str.translate(ACENTOS).str.lower()
    todos["_la"] = _redondeo_sql(todos.lat / 0.0005)
    todos["_lo"] = _redondeo_sql(todos.lon / 0.0005)
    todos = todos.sort_values(["municipio_sk", "_n", "_la", "_lo", "prioridad", "personal_est"],
                              ascending=[True, True, True, True, True, False], na_position="last")
    todos = todos.drop_duplicates(["municipio_sk", "_n", "_la", "_lo"])[cols]
    todos["lat"], todos["lon"] = todos.lat.round(6), todos.lon.round(6)

    filas = [{k: (None if (isinstance(v, float) and np.isnan(v)) else
                  int(v) if k in ("municipio_sk", "prioridad") else v) for k, v in r.items()}
             for r in todos.to_dict("records")]
    sb._peticion("fact_lugar_circuito?lugar_id=not.is.null", True, "dw", "DELETE")
    sb.insertar("fact_lugar_circuito", filas, "dw")
    print(f"✓ fact_lugar_circuito: {len(filas):,} lugares · " + ", ".join(
        f"{t} {n}" for t, n in todos.groupby(["tipo_parada", "origen"]).size().items()))


def main():
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    df = leer_denue(sys.argv[1])
    if "--solo-establecimientos" in sys.argv:
        cargar_establecimientos(df)
        calcular_lugares(df)
        return
    if "--solo-lugares" in sys.argv:
        calcular_lugares(df)
        return
    municipios, buscar = cargar_municipios()
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
        cargar_establecimientos(df)
        calcular_lugares(df)


if __name__ == "__main__":
    main()
