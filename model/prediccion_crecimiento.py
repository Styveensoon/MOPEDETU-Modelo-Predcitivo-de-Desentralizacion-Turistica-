"""Modelo predictivo de crecimiento del personal ocupado turístico por municipio × eje.

Pregunta: ¿en qué municipios y ejes crecerá más el personal ocupado en la siguiente etapa censal?

Panel: municipio × eje × transición (2014→2019, 2019→2024).
Objetivo: delta_log = ln(1 + PO_fin) − ln(1 + PO_inicio).
Variables: solo las del inicio de cada transición (más población y marginación 2020, estáticas).

Validación temporal: entrena con 2014→2019 y prueba con 2019→2024, contra tres líneas base
(persistencia, mediana del eje y orden por cociente de localización). Adicional: validación
espacial dejando fuera una región completa en cada pliegue.
Ajuste final con ambas transiciones para predecir 2024 → siguiente censo (horizonte 5 años),
con intervalos empíricos (cuantiles 10 % y 90 % del residuo fuera de muestra).
Cuando el personal base es confidencial se usa un segundo modelo que solo usa variables que
INEGI siempre publica (unidades y contexto).

Entradas (generadas por scripts/censo_economico.py y scripts/contexto_social.py):
    data/stg/censo_economico.csv, data/stg/censo_economico_totales.csv, data/stg/contexto_social.csv
    data/geo/puebla_municipios.geojson
Salidas en data/modelo/:
    panel_crecimiento.csv, metricas.csv, dim_modelo.csv, fact_prediccion_crecimiento.csv

Uso:
    python model/prediccion_crecimiento.py
    python model/prediccion_crecimiento.py --homologado data/raw/censos   # plan de afinación F4

Modo --homologado: los ejes son los de dw.dim_eje con los pesos SCIAN de scripts/cargar_datos_base.py (no los
subsectores completos de arriba, donde comercio_turistico eran las agencias 5615), y las anclas (12) y regiones (7)
son las de dw.dim_municipio, no las del modo DEMO. Lee la serie histórica del CE 2024 (tr_ce_pue_{2014,2019,2024}.csv
en la carpeta dada) y el contexto social de Supabase. Escribe en data/modelo/homologado/.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import spearmanr
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.impute import SimpleImputer
from sklearn.inspection import permutation_importance
from sklearn.linear_model import RidgeCV
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "dashboard"))
from datos import ANCLAS, haversine_km, region_aprox  # noqa: E402

STG = RAIZ / "data" / "stg"
SALIDA = RAIZ / "data" / "modelo"
SEMILLA = 2026
TOP_K = 20
VERSION = "v1"

# Ejes de oferta turística → subsectores SCIAN del censo. Ajustar si dim_eje de Galo los define distinto.
EJES = {
    "hospedaje": ["721"],
    "alimentos": ["722"],
    "turismo_cultura": ["711", "712", "713"],
    "comercio_turistico": ["5615"],  # agencias de viajes y servicios de reservaciones
}
TRANSICIONES = [(2014, 2019), (2019, 2024)]
PREDICCION = (2024, 2029)

NUMERICAS = ["log_po", "log_ue", "po_por_ue", "part_po_estatal", "part_ue_estatal", "va_trab_rel",
             "lq_po", "lq_ue", "log_po_total_mun", "log_poblacion", "indice_marginacion", "dist_ancla_km"]
PO_VARS = ["log_po", "po_por_ue", "part_po_estatal", "va_trab_rel", "lq_po"]  # dependen del personal
NUMERICAS_UE = [v for v in NUMERICAS if v not in PO_VARS]
CATEGORICAS = ["eje", "region"]


# --------------------------------------------------------------------------- datos

def cargar():
    censo = pd.read_csv(STG / "censo_economico.csv", dtype={"cve_geo": str, "sector_scian": str})
    totales = pd.read_csv(STG / "censo_economico_totales.csv", dtype={"cve_geo": str, "sector_scian": str})
    social = pd.read_csv(STG / "contexto_social.csv", dtype={"cve_geo": str})
    geo = json.loads((RAIZ / "data" / "geo" / "puebla_municipios.geojson").read_text(encoding="utf-8"))
    mun = pd.DataFrame([f["properties"] for f in geo["features"]])[["cve_geo", "nombre", "lat", "lon"]]
    return censo, totales, social, mun


def cargar_homologado(carpeta: Path):
    """Mismas salidas que cargar(), pero con un pseudo-sector por eje de la base (sector_scian = código de dim_eje),
    agregado con agregar_ce() de cargar_datos_base: mismos códigos, pesos y regla de confidencialidad que dw."""
    global EJES, ANCLAS_USO, REGION_DE
    sys.path.insert(0, str(RAIZ / "scripts"))
    import cargar_datos_base as cdb
    sb = cdb.sb
    dim = sb.leer("dim_municipio", "dw", "municipio_sk,cve_geo,nombre,region,es_ancla", secreta=True)
    dim["cve_geo"] = dim.cve_geo.str.strip()
    ejes = {r["codigo"]: r["eje_sk"] for r in sb._peticion("dim_eje?select=eje_sk,codigo", True, "dw") if r["eje_sk"]}
    EJES = {e: [e] for e in ejes}
    codigo_eje = {sk: e for e, sk in ejes.items()}
    largo, totales = [], []
    for anio in (2014, 2019, 2024):
        crudo = pd.read_csv(carpeta / f"ce_{anio}" / "conjunto_de_datos" / f"tr_ce_pue_{anio}.csv", dtype=str)
        crudo = crudo[crudo.ID_ESTRATO.isna()]
        ce = cdb.leer_ce(carpeta / f"ce_{anio}" / "conjunto_de_datos" / f"tr_ce_pue_{anio}.csv", anio)
        sel = ce[ce.codigo.isin(cdb.CODIGOS_CE + ["TOTAL"])].drop_duplicates(["cve_geo", "codigo"])
        # Renglón estatal (E04 vacío) con el mismo formato, como municipio "21000"
        est = crudo[crudo.E04.isna()].copy()
        est["codigo"] = np.where(est.SECTOR.isna(), "TOTAL", est.CODIGO.fillna("").str.strip())
        est = est.assign(cve_geo="21000", unidades=pd.to_numeric(est.UE), personal=pd.to_numeric(est.H001A),
                         vacb=pd.to_numeric(est.A131A))[["cve_geo", "codigo", "unidades", "personal", "vacb"]]
        msk = dict(zip(dim.cve_geo, dim.municipio_sk)) | {"21000": 0}
        todo = pd.concat([sel, est[est.codigo.isin(cdb.CODIGOS_CE + ["TOTAL"])]]).drop_duplicates(["cve_geo", "codigo"])
        cve = {v: k for k, v in msk.items()}
        for f in cdb.agregar_ce(todo, 0, msk, ejes):
            fila = dict(cve_geo=cve[f["municipio_sk"]], anio_censal=anio, sector_scian=codigo_eje[f["eje_sk"]],
                        unidades=f["unidades"], personal_ocupado=f["personal_ocupado"],
                        va_censal_bruto=f["va_censal_bruto_mdp"], confidencial=f["hay_confidencial"])
            (totales if fila["cve_geo"] == "21000" else largo).append(fila)
        for r in todo[todo.codigo == "TOTAL"].itertuples():
            totales.append(dict(cve_geo=r.cve_geo, anio_censal=anio, sector_scian="TOTAL", unidades=r.unidades,
                                personal_ocupado=r.personal, va_censal_bruto=r.vacb, confidencial=False))
    censo = pd.DataFrame(largo)
    censo = censo[censo.unidades > 0]  # como INEGI: sin renglón cuando no hay establecimientos
    soc = sb.leer("fact_contexto_social", "dw", "municipio_sk,poblacion_total,indice_marginacion", secreta=True)
    social = soc.merge(dim[["municipio_sk", "cve_geo"]])[["cve_geo", "poblacion_total", "indice_marginacion"]]
    geo = json.loads((RAIZ / "data" / "geo" / "puebla_municipios.geojson").read_text(encoding="utf-8"))
    mun = pd.DataFrame([f["properties"] for f in geo["features"]])[["cve_geo", "nombre", "lat", "lon"]]
    ANCLAS_USO = set(dim[dim.es_ancla].nombre)
    REGION_DE = dict(zip(dim.cve_geo, dim.region))
    print(f"Homologado: {len(EJES)} ejes de dim_eje · {len(ANCLAS_USO)} anclas · {len(set(REGION_DE.values()))} regiones")
    return censo, pd.DataFrame(totales), social, mun


ANCLAS_USO, REGION_DE = set(ANCLAS), None  # modo original: anclas y región aproximada del modo DEMO


def _por_eje(df: pd.DataFrame) -> pd.DataFrame:
    """Agrega sectores a ejes. Si algún sector del eje es confidencial, PO y VA del eje quedan nulos."""
    mapa = {s: e for e, ss in EJES.items() for s in ss}
    df = df[df["sector_scian"].isin(mapa)].assign(eje=lambda d: d["sector_scian"].map(mapa))
    g = df.groupby(["cve_geo", "anio_censal", "eje"])
    return pd.DataFrame({
        "ue": g["unidades"].sum(),
        "po": g["personal_ocupado"].sum(min_count=1).where(~g["confidencial"].any()),
        "va": g["va_censal_bruto"].sum(min_count=1).where(~g["confidencial"].any()),
    }).reset_index()


def armar_base(censo, totales, social, mun) -> pd.DataFrame:
    """Una fila por municipio × eje × año censal con las variables de nivel."""
    anios = sorted(censo["anio_censal"].unique())
    rejilla = pd.MultiIndex.from_product([mun["cve_geo"], anios, list(EJES)],
                                         names=["cve_geo", "anio_censal", "eje"]).to_frame(index=False)
    base = rejilla.merge(_por_eje(censo), how="left")

    # Total de actividades del municipio: si el municipio aparece en el censo, la ausencia de un
    # sector significa cero establecimientos (INEGI no publica renglones vacíos).
    tot_mun = (totales[(totales["sector_scian"] == "TOTAL") & (totales["cve_geo"] != "21000")]
               .rename(columns={"personal_ocupado": "po_total_mun", "unidades": "ue_total_mun"})
               [["cve_geo", "anio_censal", "po_total_mun", "ue_total_mun"]])
    base = base.merge(tot_mun, how="left")
    censado = base["ue_total_mun"].notna()
    sin_sector = censado & base["ue"].isna()
    base.loc[sin_sector, ["ue", "po", "va"]] = 0.0

    est = _por_eje(totales[totales["cve_geo"] == "21000"]).drop(columns="cve_geo")
    est = est.rename(columns={"ue": "ue_est", "po": "po_est", "va": "va_est"})
    est_total = (totales[(totales["cve_geo"] == "21000") & (totales["sector_scian"] == "TOTAL")]
                 [["anio_censal", "personal_ocupado", "unidades"]]
                 .rename(columns={"personal_ocupado": "po_est_total", "unidades": "ue_est_total"}))
    base = base.merge(est, how="left").merge(est_total, how="left")

    base = base.merge(social[["cve_geo", "poblacion_total", "indice_marginacion"]], how="left")
    base = base.merge(mun, how="left")
    anclas = mun[mun["nombre"].isin(ANCLAS_USO)]
    dist = haversine_km(mun["lat"].values[:, None], mun["lon"].values[:, None],
                        anclas["lat"].values[None, :], anclas["lon"].values[None, :]).min(axis=1)
    region = ([REGION_DE[c] for c in mun["cve_geo"]] if REGION_DE else
              [region_aprox(a, o) for a, o in zip(mun["lat"], mun["lon"])])
    base = base.merge(pd.DataFrame({"cve_geo": mun["cve_geo"], "dist_ancla_km": dist, "region": region}),
                      how="left")

    with np.errstate(divide="ignore", invalid="ignore"):
        base["log_po"] = np.log1p(base["po"])
        base["log_ue"] = np.log1p(base["ue"])
        base["po_por_ue"] = base["po"] / base["ue"].where(base["ue"] > 0)
        base["part_po_estatal"] = base["po"] / base["po_est"]
        base["part_ue_estatal"] = base["ue"] / base["ue_est"]
        base["va_trab_rel"] = (base["va"] / base["po"].where(base["po"] > 0)) / (base["va_est"] / base["po_est"])
        base["lq_po"] = (base["po"] / base["po_total_mun"]) / (base["po_est"] / base["po_est_total"])
        base["lq_ue"] = (base["ue"] / base["ue_total_mun"]) / (base["ue_est"] / base["ue_est_total"])
        base["log_po_total_mun"] = np.log1p(base["po_total_mun"])
        base["log_poblacion"] = np.log(base["poblacion_total"])
    return base.replace([np.inf, -np.inf], np.nan)


def armar_panel(base: pd.DataFrame, transiciones) -> pd.DataFrame:
    filas = []
    for t0, t1 in transiciones:
        ini = base[base["anio_censal"] == t0]
        fin = base[base["anio_censal"] == t1][["cve_geo", "eje", "po", "ue"]].rename(
            columns={"po": "po_fin", "ue": "ue_fin"})
        p = ini.merge(fin, on=["cve_geo", "eje"], how="left")
        p["anio_inicio"], p["anio_fin"] = t0, t1
        p["delta_log"] = np.log1p(p["po_fin"]) - np.log1p(p["po"])
        filas.append(p)
    panel = pd.concat(filas, ignore_index=True)
    # Solo celdas con presencia del eje al inicio o al final (sin ellas no hay nada que crecer)
    return panel[(panel["ue"] > 0) | (panel["ue_fin"] > 0)].reset_index(drop=True)


# --------------------------------------------------------------------------- modelos

def matriz(df: pd.DataFrame, variables: list[str], columnas=None) -> pd.DataFrame:
    X = pd.get_dummies(df[variables + CATEGORICAS], columns=CATEGORICAS, dtype=float)
    return X.reindex(columns=columnas, fill_value=0.0) if columnas is not None else X


def modelo_ridge():
    return make_pipeline(SimpleImputer(strategy="median", add_indicator=True), StandardScaler(),
                         RidgeCV(alphas=np.logspace(-2, 3, 30)))


def modelo_gbm():
    return HistGradientBoostingRegressor(max_depth=3, learning_rate=0.05, max_iter=250, min_samples_leaf=20,
                                         l2_regularization=1.0, random_state=SEMILLA)


# nombre: (descripción, fábrica, variables). "ridge" y "gbm" compiten como modelo principal;
# "gbm_ue" cubre las celdas con personal base confidencial (solo variables que INEGI siempre publica).
MODELOS = {
    "ridge": ("Ridge (regularizado L2, imputación por mediana con indicador de faltante)", modelo_ridge, NUMERICAS),
    "gbm": ("Gradient boosting (HistGradientBoosting, árboles poco profundos)", modelo_gbm, NUMERICAS),
    "gbm_ue": ("Gradient boosting solo con variables siempre publicadas (unidades, contexto); "
               "se usa cuando el personal base es confidencial", modelo_gbm, NUMERICAS_UE),
}
PRINCIPALES = ["ridge", "gbm"]
HIPERPARAMETROS = {
    "ridge": {"alphas": "logspace(-2, 3, 30), elegido por validación cruzada interna"},
    "gbm": {"max_depth": 3, "learning_rate": 0.05, "max_iter": 250, "min_samples_leaf": 20, "l2_regularization": 1.0},
}
HIPERPARAMETROS["gbm_ue"] = HIPERPARAMETROS["gbm"]


def ajustar(nombre: str, df: pd.DataFrame):
    _, fabrica, variables = MODELOS[nombre]
    X = matriz(df, variables)
    return fabrica().fit(X, df["delta_log"]), X.columns


def predecir(ajuste, nombre: str, df: pd.DataFrame) -> np.ndarray:
    mod, columnas = ajuste
    return mod.predict(matriz(df, MODELOS[nombre][2], columnas))


def oof_por_region(nombre: str, df: pd.DataFrame) -> pd.Series:
    """Predicción fuera de muestra dejando fuera una región completa en cada pliegue."""
    pred = pd.Series(np.nan, index=df.index)
    for reg in df["region"].unique():
        fuera = df["region"] == reg
        pred[fuera] = predecir(ajustar(nombre, df[~fuera]), nombre, df[fuera])
    return pred


def cuantiles_residuo(df: pd.DataFrame, pred: pd.Series) -> pd.DataFrame:
    """Cuantiles 10 % y 90 % del residuo fuera de muestra por eje (intervalos empíricos)."""
    res = (df["delta_log"] - pred).groupby(df["eje"])
    global_ = (df["delta_log"] - pred).quantile([0.1, 0.9]).values
    q = pd.DataFrame({"q10": res.quantile(0.1), "q90": res.quantile(0.9), "n": res.size()})
    q.loc[q["n"] < 15, ["q10", "q90"]] = global_  # ejes con pocas filas usan el residuo global
    return q


# --------------------------------------------------------------------------- métricas

def metricas(df: pd.DataFrame, score: str, con_error: bool = True) -> dict:
    """df con columnas delta_log (real), eje y `score` (predicción o puntaje para ordenar)."""
    d = df.dropna(subset=["delta_log", score])
    m = {"n": len(d), "spearman_global": spearmanr(d[score], d["delta_log"]).statistic}
    top_real = set(d.nlargest(TOP_K, "delta_log").index)
    m["precision_top20_global"] = len(top_real & set(d.nlargest(TOP_K, score).index)) / TOP_K
    por_eje_rho, por_eje_p = [], []
    for eje, g in d.groupby("eje"):
        if len(g) >= 10:
            # Un puntaje constante dentro del eje (p. ej. la mediana del eje) no tiene correlación definida
            rho = spearmanr(g[score], g["delta_log"]).statistic if g[score].nunique() > 1 else np.nan
            k = min(TOP_K, len(g) // 2)
            p = len(set(g.nlargest(k, "delta_log").index) & set(g.nlargest(k, score).index)) / k
            m[f"spearman_{eje}"], m[f"precision_topk_{eje}"] = rho, p
            por_eje_rho.append(rho)
            por_eje_p.append(p)
    m["spearman_media_ejes"] = float(np.nanmean(por_eje_rho)) if not np.all(np.isnan(por_eje_rho)) else np.nan
    m["precision_media_ejes"] = float(np.mean(por_eje_p))
    m["mae_delta_log"] = float(np.mean(np.abs(d[score] - d["delta_log"]))) if con_error else np.nan
    return {k: (round(float(v), 4) if isinstance(v, (float, np.floating)) else v) for k, v in m.items()}


def lineas_base(entr: pd.DataFrame, prueba: pd.DataFrame) -> dict[str, pd.Series]:
    mediana = entr.groupby("eje")["delta_log"].median()
    previo = entr.set_index(["cve_geo", "eje"])["delta_log"]
    persist = pd.Series([previo.get((c, e), np.nan) for c, e in zip(prueba["cve_geo"], prueba["eje"])],
                        index=prueba.index)
    return {
        "lb_persistencia": persist.fillna(prueba["eje"].map(mediana)),
        "lb_mediana_eje": prueba["eje"].map(mediana),
        "lb_cociente_localizacion": prueba["lq_po"].fillna(prueba["lq_ue"]),
    }


def supera(temporal: pd.DataFrame, nombre: str) -> bool:
    lb = temporal[temporal.index.str.startswith("lb_")]
    fila = temporal.loc[nombre]
    return bool((fila["spearman_global"] > lb["spearman_global"]).all()
                and (fila["precision_top20_global"] >= lb["precision_top20_global"]).all())


# --------------------------------------------------------------------------- flujo

def main():
    global SALIDA, VERSION
    if len(sys.argv) > 2 and sys.argv[1] == "--homologado":
        SALIDA, VERSION = SALIDA / "homologado", "v2_homologado"
        datos = cargar_homologado(Path(sys.argv[2]))
    else:
        datos = cargar()
    SALIDA.mkdir(parents=True, exist_ok=True)
    base = armar_base(*datos)
    panel = armar_panel(base, TRANSICIONES)
    panel.to_csv(SALIDA / "panel_crecimiento.csv", index=False)
    con_obj = panel.dropna(subset=["delta_log"])
    print(panel.groupby(["anio_inicio", "anio_fin"]).agg(filas=("eje", "size"),
                                                        con_objetivo=("delta_log", "count")))

    # 1) Validación temporal: entrena 2014→2019, prueba 2019→2024
    entr = con_obj[con_obj["anio_inicio"] == 2014]
    prueba = con_obj[con_obj["anio_inicio"] == 2019].copy()
    resultados, cobertura = [], {}
    for nombre, serie in lineas_base(entr, prueba).items():
        prueba[nombre] = serie
        resultados.append({"modelo": nombre, "validacion": "temporal",
                           **metricas(prueba, nombre, con_error=nombre != "lb_cociente_localizacion")})
    for nombre in MODELOS:
        prueba[nombre] = predecir(ajustar(nombre, entr), nombre, prueba)
        resultados.append({"modelo": nombre, "validacion": "temporal", **metricas(prueba, nombre)})
        # Intervalos con residuos fuera de muestra de 2014→2019; cobertura medida en 2019→2024
        q = cuantiles_residuo(entr, oof_por_region(nombre, entr))
        dentro = ((prueba["delta_log"] >= prueba[nombre] + prueba["eje"].map(q["q10"]))
                  & (prueba["delta_log"] <= prueba[nombre] + prueba["eje"].map(q["q90"])))
        cobertura[nombre] = round(float(dentro.mean()), 4)

    # 2) Validación espacial con ambas transiciones (sus residuos dan los intervalos finales)
    oof = {}
    for nombre in MODELOS:
        oof[nombre] = oof_por_region(nombre, con_obj)
        resultados.append({"modelo": nombre, "validacion": "espacial_por_region",
                           **metricas(con_obj.assign(**{nombre: oof[nombre]}), nombre)})

    met = pd.DataFrame(resultados)
    met.to_csv(SALIDA / "metricas.csv", index=False)
    temporal = met[met["validacion"] == "temporal"].set_index("modelo")
    with pd.option_context("display.width", 200, "display.max_columns", 10):
        print(temporal[["n", "spearman_global", "spearman_media_ejes", "precision_top20_global", "mae_delta_log"]])

    # 3) Selección: el principal con mejor Spearman; ambos modelos deben superar las líneas base
    elegido = temporal.loc[PRINCIPALES, "spearman_global"].idxmax()
    supera_principal, supera_ue = supera(temporal, elegido), supera(temporal, "gbm_ue")
    print(f"Principal: {elegido} (supera líneas base: {supera_principal}) · "
          f"gbm_ue supera líneas base: {supera_ue} · cobertura 10–90 %: {cobertura}")

    # Importancia de variables por permutación sobre la prueba temporal
    explic = {}
    for nombre in (elegido, "gbm_ue"):
        mod, cols = ajustar(nombre, entr)
        Xp = matriz(prueba, MODELOS[nombre][2], cols)
        imp = permutation_importance(mod, Xp, prueba["delta_log"], n_repeats=20, random_state=SEMILLA,
                                     scoring="neg_mean_absolute_error")
        variables = MODELOS[nombre][2] + CATEGORICAS
        grupo = lambda c: next((v for v in variables if c == v or c.startswith(v + "_")), c)  # noqa: E731
        explic[nombre] = (pd.Series(imp.importances_mean, index=cols).groupby(grupo).sum()
                          .sort_values(ascending=False).round(4))
        print(f"Importancia {nombre} (aumento de MAE al permutar):", explic[nombre].head(6).to_dict())

    # 4) Ajuste final con ambas transiciones y predicción 2024 → siguiente censo
    nuevo = base[(base["anio_censal"] == PREDICCION[0]) & (base["ue"] > 0)].copy()
    conf = nuevo["po"].isna()
    nuevo["modelo"] = np.where(conf, "gbm_ue", elegido)
    if not supera_ue:  # sin modelo válido para bases confidenciales no se predice
        nuevo = nuevo[~conf].copy()
        conf = nuevo["po"].isna()
    nuevo["delta_log_pred"] = np.nan
    for nombre in nuevo["modelo"].unique():
        sel = nuevo["modelo"] == nombre
        nuevo.loc[sel, "delta_log_pred"] = predecir(ajustar(nombre, con_obj), nombre, nuevo[sel])
        q = cuantiles_residuo(con_obj, oof[nombre])
        nuevo.loc[sel, "delta_log_inf"] = nuevo.loc[sel, "delta_log_pred"] + nuevo.loc[sel, "eje"].map(q["q10"])
        nuevo.loc[sel, "delta_log_sup"] = nuevo.loc[sel, "delta_log_pred"] + nuevo.loc[sel, "eje"].map(q["q90"])

    pct = lambda d: ((np.exp(d) - 1) * 100).round(2)  # noqa: E731
    personal_pred = np.expm1(np.log1p(nuevo["po"]) + nuevo["delta_log_pred"]).round()
    pred = pd.DataFrame({
        "cve_geo": nuevo["cve_geo"], "nom_mun": nuevo["nombre"], "eje": nuevo["eje"],
        "modelo": "crecimiento_" + nuevo["modelo"] + f"_{VERSION}", "periodo_base": "CE 2024",
        "horizonte_anios": PREDICCION[1] - PREDICCION[0],
        "personal_base": nuevo["po"].astype("Int64"), "base_confidencial": conf,
        "unidades_base": nuevo["ue"].astype(int),
        "delta_log_pred": nuevo["delta_log_pred"].round(4),
        "crecimiento_pred_pct": pct(nuevo["delta_log_pred"]),
        "intervalo_inf_pct": pct(nuevo["delta_log_inf"]),
        "intervalo_sup_pct": pct(nuevo["delta_log_sup"]),
        "personal_pred": personal_pred.astype("Int64"),
        "incremento_personal_pred": (personal_pred - nuevo["po"]).astype("Int64"),
    })
    pred["ranking_potencial"] = pred.groupby("eje")["delta_log_pred"].rank(ascending=False, method="first").astype(int)
    pred = pred.sort_values(["eje", "ranking_potencial"])
    pred.to_csv(SALIDA / "fact_prediccion_crecimiento.csv", index=False)

    # 5) dim_modelo: modelos candidatos y líneas base, con métricas y limitaciones
    limitaciones = (
        "2019→2024 incluye la pandemia (cambio de régimen); la validación temporal es más débil de lo que parece. "
        "Pocas filas: ~50 % de las celdas son confidenciales en municipios pequeños y no entran al entrenamiento "
        "(no se rellenan). Para bases confidenciales se usa gbm_ue, validado solo sobre celdas publicadas. "
        "Población y marginación son de 2020 (estáticas en ambas transiciones). "
        "Distancia al ancla en línea recta desde el centroide (sustituto de fact_accesibilidad) y región aproximada por coordenadas. "
        "Censos homologados a SCIAN 2023 por INEGI (versión histórica CE 2024). "
        "Se predice potencial de empleo en oferta turística, no visitantes ni derrama; no es garantía de crecimiento. "
        "El porcentaje se calcula sobre (1 + personal): bases muy pequeñas dan porcentajes altos."
    )
    algoritmos_lb = {
        "lb_persistencia": "Se repite el delta_log 2014→2019 del mismo municipio y eje",
        "lb_mediana_eje": "Mediana de delta_log del eje en 2014→2019",
        "lb_cociente_localizacion": "Orden por cociente de localización al inicio (solo ranking)",
    }
    filas_modelo = []
    for nombre, fila in temporal.iterrows():
        es_modelo = nombre in MODELOS
        metr = {"temporal": fila.drop("validacion").dropna().to_dict()}
        espacial = met[(met["modelo"] == nombre) & (met["validacion"] == "espacial_por_region")]
        if len(espacial):
            metr["espacial_por_region"] = espacial.iloc[0].drop(["modelo", "validacion"]).dropna().to_dict()
        if es_modelo:
            metr["cobertura_intervalo_10_90_temporal"] = cobertura[nombre]
            metr["supera_lineas_base"] = supera(temporal, nombre)
        filas_modelo.append({
            "nombre": f"crecimiento_{nombre}_{VERSION}" if es_modelo else nombre,
            "tarea": "crecimiento_municipal" if es_modelo else "linea_base",
            "algoritmo": MODELOS[nombre][0] if es_modelo else algoritmos_lb[nombre],
            "en_uso": nombre == elegido or (nombre == "gbm_ue" and supera_ue),
            "objetivo": "delta_log = ln(1+PO_fin) − ln(1+PO_inicio)",
            "variables": json.dumps(MODELOS[nombre][2] + CATEGORICAS) if es_modelo else "",
            "hiperparametros": json.dumps(HIPERPARAMETROS.get(nombre, {}), ensure_ascii=False),
            "intervalos": "Cuantiles 10/90 % del residuo fuera de muestra por eje (validación espacial)" if es_modelo else "",
            "periodo_entrenamiento": ("2014→2019 (validación); 2014→2019 + 2019→2024 (ajuste final)"
                                      if es_modelo else "2014→2019"),
            "periodo_validacion": "2019→2024; además validación espacial dejando fuera una región",
            "metricas": json.dumps(metr, ensure_ascii=False),
            "explicabilidad": json.dumps(explic[nombre].head(10).to_dict(), ensure_ascii=False) if nombre in explic else "",
            "limitaciones": limitaciones,
        })
    pd.DataFrame(filas_modelo).to_csv(SALIDA / "dim_modelo.csv", index=False)
    print(f"Predicciones: {len(pred)} filas ({int(conf.sum())} con base confidencial)")


if __name__ == "__main__":
    main()
