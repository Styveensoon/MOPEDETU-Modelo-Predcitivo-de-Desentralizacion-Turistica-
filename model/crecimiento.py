"""Pieza 2 · Modelo de crecimiento del empleo turístico por municipio × eje (A5).

Objetivo:  y = ln(1 + UE_t+5) − ln(1 + UE_t)  (unidades económicas del Censo Económico, eje turístico).
           Se usan unidades y no personal porque INEGI oculta el personal por confidencialidad en la mayoría
           de los municipios pequeños (solo 136 de 868 casos tenían personal en ambos censos); las unidades
           nunca se ocultan.
Entrena:   transición CE 2019 → CE 2024, con variables medidas en 2019 (sin fuga de información futura:
           no se usa el DENUE 2026 y los Pueblos Mágicos cuentan solo si ya lo eran en 2019).
Predice:   CE 2024 → 2029 aplicando el modelo a las mismas variables medidas en 2024.
Valida:    GroupKFold (5) por municipio: un municipio nunca está a la vez en entrenamiento y prueba.
           Líneas base: (B1) crecimiento medio del eje, (B2) regresión lineal Ridge con las mismas variables.
Intervalo: conformal: predicción ± cuantil 80 % del error absoluto observado en validación cruzada
           (cobertura del 80 % por construcción; se reporta la cobertura medida).

Dominio:   (v2, plan de afinación F2c) solo se predice donde el eje tiene ≥ 3 unidades en el CE 2024, el mismo
           filtro del entrenamiento; fuera de dominio la predicción queda NULL con su motivo. La corrida v1 (sin
           dominio) se conserva en la base con su propio modelo_sk.

Escribe dw.dim_modelo (crecimiento_ue_eje_lgbm_v2), dw.fact_prediccion_crecimiento y el índice v3_dominio_osrm.
Las versiones v1_base y v2_con_prediccion del índice no se tocan.
Uso: python model/crecimiento.py
"""
import json
import warnings

import lightgbm as lgb
import numpy as np
import pandas as pd
from scipy.stats import spearmanr
from sklearn.linear_model import Ridge
from sklearn.model_selection import GroupKFold
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

import base
import indice
from base import EJES, RAIZ, pct, publicar

warnings.filterwarnings("ignore")
TAREA = "crecimiento_municipal"  # dim_modelo.tarea ∈ {crecimiento_municipal, enlace_municipios, linea_base}
HORIZONTE = 5
SEMILLA = 2026
MIN_UNIDADES = 3   # dominio del modelo: mismo umbral que objetivo()
MOTIVO_FUERA = f"base menor a {MIN_UNIDADES} unidades: fuera del rango de entrenamiento"
VERSION_INDICE = "v3_dominio_osrm"
PARAMS = dict(n_estimators=400, learning_rate=0.03, num_leaves=15, min_child_samples=12, subsample=0.8,
              subsample_freq=1, colsample_bytree=0.8, reg_lambda=1.0, random_state=SEMILLA, verbose=-1)


def panel(b: base.Base) -> pd.DataFrame:
    """Una fila por municipio × eje con las variables en 2019 y 2024 y el crecimiento observado."""
    ce = b.censo.copy()
    anio = {b.periodos["CE 2014"]: 2014, b.periodos["CE 2019"]: 2019, b.periodos["CE 2024"]: 2024}
    ce["anio"] = ce.periodo_sk.map(anio)
    w = ce.pivot_table(index=["municipio_sk", "eje_sk"], columns="anio",
                       values=["personal_ocupado", "unidades", "va_censal_bruto_mdp", "hay_confidencial"],
                       aggfunc="first")
    w.columns = [f"{a}_{y}" for a, y in w.columns]
    w = w.reset_index()

    tot = base.sb._peticion("censo_economico?select=cve_geo,anio_censal,personal_ocupado&sector_scian=eq.TOTAL",
                            True, "stg")
    tot = pd.DataFrame(tot).assign(cve_geo=lambda d: d.cve_geo.str.strip())
    tot = tot.merge(b.mun.reset_index()[["municipio_sk", "cve_geo"]]).pivot(
        index="municipio_sk", columns="anio_censal", values="personal_ocupado")
    for y in (2014, 2019, 2024):
        if y in tot.columns:
            w[f"po_mun_{y}"] = w.municipio_sk.map(tot[y])
    return w


def variables(w: pd.DataFrame, b: base.Base, t: int) -> pd.DataFrame:
    """Variables medidas en el año base t (2019 para entrenar, 2024 para predecir)."""
    m, inf, soc = b.mun, b.infra, b.social
    po, ue, va = w[f"personal_ocupado_{t}"], w[f"unidades_{t}"], w[f"va_censal_bruto_mdp_{t}"]
    X = pd.DataFrame(index=w.index)
    X["eje"] = w.eje_sk.astype(int)
    X["log_po"] = np.log1p(po)
    X["log_ue"] = np.log1p(ue)
    X["tamano_medio"] = po / ue.replace(0, np.nan)
    X["productividad"] = va / po.replace(0, np.nan)
    X["confidencial"] = w[f"hay_confidencial_{t}"].astype(float)
    X["peso_en_municipio"] = po / w[f"po_mun_{t}"]
    estado = w.assign(po=po).groupby("eje_sk").po.transform("sum") / w.drop_duplicates("municipio_sk")[f"po_mun_{t}"].sum()
    X["cociente_localizacion"] = X.peso_en_municipio / estado
    X["log_po_municipio"] = np.log1p(w[f"po_mun_{t}"])

    # Rezago espacial: empleo del mismo eje en municipios colindantes (variable, no objetivo: sin fuga)
    col = b.acceso[b.acceso.es_colindante][["municipio_origen_sk", "municipio_destino_sk"]]
    lp = w.assign(lp=X.log_po).set_index(["municipio_sk", "eje_sk"]).lp
    vec = col.merge(w[["municipio_sk", "eje_sk"]], left_on="municipio_destino_sk", right_on="municipio_sk")
    vec["lp"] = [lp.get((d, e), np.nan) for d, e in zip(vec.municipio_destino_sk, vec.eje_sk)]
    rez = vec.groupby(["municipio_origen_sk", "eje_sk"]).lp.mean()
    X["log_po_vecinos"] = [rez.get((mk, e), np.nan) for mk, e in zip(w.municipio_sk, w.eje_sk)]

    mk = w.municipio_sk
    pm_anio = pd.read_csv(RAIZ / "data" / "catalogos" / "municipios_turismo.csv", dtype={"cve_geo": str})
    pm_anio = pm_anio.set_index("cve_geo").anio_pueblo_magico
    X["pueblo_magico"] = [float(pd.notna(pm_anio.get(m.cve_geo[k])) and pm_anio.get(m.cve_geo[k]) <= t) for k in mk]
    X["ancla"] = mk.map(m.es_ancla).astype(float)
    X["region"] = mk.map(m.region).astype("category").cat.codes
    X["marginacion"] = mk.map(soc.indice_marginacion)
    X["pobreza"] = mk.map(soc.pct_pobreza)
    X["internet"] = mk.map(soc.pct_viviendas_internet)
    X["log_poblacion"] = np.log1p(mk.map(soc.poblacion_total))
    X["min_ancla"] = mk.map(inf.min_ancla_cercana)
    X["min_capital"] = mk.map(inf.min_capital)
    X["vias_km2"] = mk.map(inf.km_vias_por_km2)
    X["colindantes"] = mk.map(inf.municipios_colindantes)
    X["atractivos"] = mk.map(b.atractivos.groupby("municipio_sk").num_atractivos.sum()).fillna(0)
    X["rutas_oficiales"] = mk.map(b.rutas.groupby("municipio_sk").ruta_sk.nunique()).fillna(0)
    return X


def objetivo(w: pd.DataFrame, t0: int = 2019, t1: int = 2024) -> pd.Series:
    """Crecimiento logarítmico de unidades económicas (nunca confidenciales). Se excluyen ejes sin oferta
    en ambos censos y los municipios con menos de 3 unidades en el eje en ambos (crecimientos espurios)."""
    u0, u1 = w[f"unidades_{t0}"].fillna(0), w[f"unidades_{t1}"].fillna(0)
    y = np.log1p(u1) - np.log1p(u0)
    return y.where((u0 >= MIN_UNIDADES) | (u1 >= MIN_UNIDADES))


def validar_temporal(w: pd.DataFrame, b: base.Base) -> dict | None:
    """Validación en el tiempo (plan de afinación F4): entrena con la transición CE 2014 → 2019 (variables de 2014)
    y predice 2019 → 2024 con variables de 2019, contra lo observado. Incluye la pandemia en el periodo de prueba."""
    if "unidades_2014" not in w or "po_mun_2014" not in w:
        return None
    y_tr, y_te = objetivo(w, 2014, 2019), objetivo(w, 2019, 2024)
    tr, te = y_tr.notna(), y_te.notna()
    X14, X19 = variables(w, b, 2014), variables(w, b, 2019)
    p = pd.DataFrame({"lgbm": lgb.LGBMRegressor(**PARAMS).fit(X14[tr], y_tr[tr]).predict(X19[te]),
                      "b1_media_eje": X19[te].eje.map(y_tr[tr].groupby(X14[tr].eje).mean()).to_numpy()},
                     index=y_te[te].index)
    y = y_te[te]
    res = {}
    for k in p:
        top_real, top_pred = y >= y.quantile(0.8), p[k] >= p[k].quantile(0.8)
        res[k] = dict(mae=round(float((p[k] - y).abs().mean()), 4),
                      spearman=round(float(spearmanr(p[k], y).correlation), 3),
                      precision_top20=round(float((top_real & top_pred).sum() / top_pred.sum()), 3))
    res["n_entrenamiento"], res["n_prueba"] = int(tr.sum()), int(te.sum())
    return res


def validar(X: pd.DataFrame, y: pd.Series, grupos: pd.Series) -> tuple[dict, pd.DataFrame]:
    pred = pd.DataFrame(index=X.index, columns=["lgbm", "b1_media_eje", "b2_ridge"], dtype=float)
    for tr, te in GroupKFold(n_splits=5).split(X, y, grupos):
        Xtr, Xte, ytr = X.iloc[tr], X.iloc[te], y.iloc[tr]
        pred.iloc[te, 0] = lgb.LGBMRegressor(**PARAMS).fit(Xtr, ytr).predict(Xte)
        pred.iloc[te, 1] = Xte.eje.map(ytr.groupby(Xtr.eje).mean()).to_numpy()
        ridge = make_pipeline(StandardScaler(), Ridge(alpha=3.0)).fit(Xtr.fillna(Xtr.median()), ytr)
        pred.iloc[te, 2] = ridge.predict(Xte.fillna(Xtr.median()))
    # Intervalo conformal: cuantil 80 % del error absoluto fuera de muestra
    q80 = float((pred.lgbm - y).abs().quantile(0.8))
    pred["q10"], pred["q90"] = pred.lgbm - q80, pred.lgbm + q80

    def metricas(p):
        top_real = y >= y.quantile(0.8)
        top_pred = p >= p.quantile(0.8)
        return dict(mae=round(float((p - y).abs().mean()), 4), spearman=round(float(spearmanr(p, y).correlation), 3),
                    precision_top20=round(float((top_real & top_pred).sum() / top_pred.sum()), 3))

    res = {k: metricas(pred[k]) for k in ("lgbm", "b1_media_eje", "b2_ridge")}
    res["cobertura_intervalo_80"] = round(float(((y >= pred.q10) & (y <= pred.q90)).mean()), 3)
    res["semiancho_intervalo_log"] = round(q80, 4)
    res["n_entrenamiento"] = int(len(y))
    return res, pred


def main():
    b = base.cargar()
    w = panel(b)
    y_full = objetivo(w)
    ok = y_full.notna()
    X19 = variables(w, b, 2019)
    X, y, g = X19[ok], y_full[ok], w.municipio_sk[ok]
    print(f"Panel: {len(w)} municipio×eje · con objetivo válido: {ok.sum()} (resto: confidenciales o sin empleo)")

    res, pred_cv = validar(X, y, g)
    for k in ("lgbm", "b1_media_eje", "b2_ridge"):
        print(f"  {k:<13} MAE {res[k]['mae']:.3f} · Spearman {res[k]['spearman']:+.3f} · precisión top 20 % {res[k]['precision_top20']:.0%}")
    print(f"  cobertura del intervalo de 80 %: {res['cobertura_intervalo_80']:.0%}")
    gana = res["lgbm"]["mae"] < min(res["b1_media_eje"]["mae"], res["b2_ridge"]["mae"])
    temporal = validar_temporal(w, b)
    if temporal:
        res["validacion_temporal_2014_2019_a_2019_2024"] = temporal
        for k in ("lgbm", "b1_media_eje"):
            print(f"  temporal {k:<13} MAE {temporal[k]['mae']:.3f} · Spearman {temporal[k]['spearman']:+.3f} · "
                  f"precisión top 20 % {temporal[k]['precision_top20']:.0%}")

    # Modelo final con todos los datos válidos y explicabilidad SHAP (contribuciones de LightGBM)
    final = lgb.LGBMRegressor(**PARAMS).fit(X, y)
    shap = pd.DataFrame(final.predict(X, pred_contrib=True)[:, :-1], columns=X.columns).abs().mean()
    shap = (shap / shap.sum()).sort_values(ascending=False)
    print("  variables más influyentes (SHAP):", ", ".join(f"{k} {v:.0%}" for k, v in shap.head(8).items()))

    # Predicción 2024 → 2029 con variables medidas en 2024
    X24 = variables(w, b, 2024)
    yhat = final.predict(X24)
    if not gana:  # regla de corte: si el modelo no supera a las líneas base se publica la línea base Ridge
        print("  ⚠ LightGBM no supera a las líneas base: se publica la predicción de Ridge")
        ridge = make_pipeline(StandardScaler(), Ridge(alpha=3.0)).fit(X.fillna(X.median()), y)
        yhat = ridge.predict(X24.fillna(X.median()))
    lo, hi = yhat - res["semiancho_intervalo_log"], yhat + res["semiancho_intervalo_log"]
    out = w[["municipio_sk", "eje_sk"]].copy()
    # Personal base: CE 2024 si es público; si INEGI lo oculta, la estimación del DENUE 05/2026 para ese eje
    denue = b.oferta.set_index(["municipio_sk", "eje_sk"]).personal_est
    out["personal_base"] = [p if pd.notna(p) and not c else round(float(denue.get((mk, e), np.nan)), 1)
                            for p, c, mk, e in zip(w.personal_ocupado_2024, w.hay_confidencial_2024.astype(bool),
                                                   w.municipio_sk, w.eje_sk)]
    out["unidades_base"] = w.unidades_2024.fillna(0).astype(int)
    out["en_dominio"] = out.unidades_base >= MIN_UNIDADES
    dentro = out.en_dominio.to_numpy()
    out["crecimiento_pred_pct"] = np.where(dentro, np.round((np.expm1(yhat)) * 100, 2), np.nan)
    out["intervalo_inf_pct"] = np.where(dentro, np.round(np.expm1(lo) * 100, 2), np.nan)
    out["intervalo_sup_pct"] = np.where(dentro, np.round(np.expm1(hi) * 100, 2), np.nan)
    out["ranking_potencial"] = out.groupby("eje_sk").crecimiento_pred_pct.rank(ascending=False, method="min") \
        .astype("Int64")
    out["motivo_sin_prediccion"] = np.where(dentro, None, MOTIVO_FUERA)
    d = out[out.en_dominio]
    print(f"  dominio: {len(d)} celdas con predicción, {(~out.en_dominio).sum()} sin predicción (< {MIN_UNIDADES} UE) · "
          f"mediana {d.crecimiento_pred_pct.median():+.1f} % · negativos {(d.crecimiento_pred_pct < 0).sum()}")

    modelo = dict(
        nombre="crecimiento_ue_eje_lgbm_v2", tarea=TAREA,
        algoritmo="LightGBM (gradient boosting) + intervalo conformal de 80 %",
        variables={"objetivo": "ln(1+UE_t+5) - ln(1+UE_t): unidades económicas turísticas por municipio y eje "
                               "(Censos Económicos)",
                   "lista": list(X.columns), "importancia_shap": {k: round(float(v), 4) for k, v in shap.items()}},
        hiperparametros=PARAMS, periodo_entrenamiento="CE 2019 → CE 2024 (variables medidas en 2019)",
        periodo_validacion="GroupKFold de 5 particiones por municipio",
        esquema_validacion="Validación cruzada agrupada por municipio; líneas base: media del eje y Ridge. "
                           "Además validación temporal: entrenar CE 2014 → 2019 y probar 2019 → 2024 (serie histórica "
                           "homologada del CE 2024; el periodo de prueba incluye la pandemia).",
        metricas=res,
        explicabilidad="Contribuciones SHAP exactas de LightGBM (pred_contrib); importancia media normalizada.",
        limitaciones="Un solo periodo censal (2019-2024, incluye la pandemia). Mide unidades económicas (oferta), "
                     "no visitantes. Municipios con menos de 3 unidades en el eje quedan fuera del entrenamiento y, "
                     "desde la v2, también sin predicción (en_dominio = false). Accesibilidad por carretera (OSRM). "
                     "La predicción es un escenario tendencial, no un compromiso de crecimiento.")
    psk = b.periodos["CE 2024"]
    filas = [{k: base.limpio(v) for k, v in r.items()} | dict(periodo_base_sk=psk, horizonte_anios=HORIZONTE)
             for r in out.to_dict("records")]
    publicar(modelo, "fact_prediccion_crecimiento", filas)
    for clave, nombre, algoritmo in (("b1_media_eje", "crecimiento_linea_base_media_eje_v2", "Media del eje en entrenamiento"),
                                     ("b2_ridge", "crecimiento_linea_base_ridge_v2", "Ridge (alpha=3) estandarizado")):
        base.asegurar_modelo(dict(nombre=nombre, tarea="linea_base", algoritmo=algoritmo,
                                  variables={"compara_con": modelo["nombre"]}, metricas={"cv": res[clave]},
                                  periodo_entrenamiento=modelo["periodo_entrenamiento"],
                                  periodo_validacion=modelo["periodo_validacion"],
                                  esquema_validacion="Mismas particiones que el modelo principal"))
    print("✓ dim_modelo: líneas base registradas con sus métricas")

    # Índice v3: potencial solo en dominio (percentil dentro del eje; fuera de dominio NaN y se renormalizan los
    # pesos), y en alimentos y comercio la oferta en exceso de la población en vez del tamaño bruto.
    pot = out.set_index(["municipio_sk", "eje_sk"]).crecimiento_pred_pct.groupby(level="eje_sk") \
        .rank(pct=True, method="average")
    exc = base.sb.leer("v_exceso_oferta", "dw", "municipio_sk,eje_sk,periodo_sk,percentil_residuo", secreta=True)
    exc = exc[exc.periodo_sk == b.periodos["DENUE 2026-05"]].set_index(["municipio_sk", "eje_sk"]).percentil_residuo
    pesos = base.sb._peticion("dim_version_calculo?select=pesos&nombre=eq.v2_con_prediccion", True, "dw")[0]["pesos"]
    v3 = base.asegurar_version(VERSION_INDICE, "Índice con potencial solo en dominio (≥ 3 UE), tiempos por carretera "
                               "(OSRM) y oferta de alimentos y comercio en exceso de la población "
                               "(model/crecimiento.py, plan de afinación F2-F3)", pesos)
    c = indice.componentes(b)
    residentes = c.eje_sk.isin([2, 4])
    c.loc[residentes, "score_oferta"] = [exc.get((m, e), np.nan) for m, e in
                                         zip(c.municipio_sk[residentes], c.eje_sk[residentes])]
    c = indice.indice(c, pesos, potencial=pot, renormalizar=True)
    indice.guardar_indice(c, v3, b.periodos["DENUE 2026-05"])
    vis = base.sb.leer("fact_visibilidad", "dw", "municipio_sk,vistas,periodo_inicio,actividad_sk", secreta=True)
    if len(vis):
        vis = vis[vis.actividad_sk.isna() & (vis.periodo_inicio == vis.periodo_inicio.max())]
        vis = vis.set_index("municipio_sk").vistas.rank(pct=True)
    indice.asegurar_flags()
    f = indice.banderas(b, c, exceso=exc, visibilidad=vis if len(vis) else None)
    base.reemplazar("fact_flag_oportunidad", f"version_sk=eq.{v3}",
                    [r | dict(version_sk=v3) for r in f.drop(columns="codigo").to_dict("records")])
    print(f"✓ fact_indice_oportunidad {VERSION_INDICE}: {len(c)} filas · banderas: "
          f"{f[f.flag_activo].codigo.value_counts().to_dict()}")

    top = out[out.en_dominio].merge(b.mun[["nombre", "es_ancla"]], left_on="municipio_sk", right_index=True)
    top = top[~top.es_ancla & (top.personal_base.fillna(0) >= 10)].nlargest(10, "crecimiento_pred_pct")
    print("Mayor crecimiento esperado (no anclas, ≥10 empleos):",
          ", ".join(f"{n} ({EJES[e][:4]}) {p:+.0f}%" for n, e, p in zip(top.nombre, top.eje_sk, top.crecimiento_pred_pct)))
    (RAIZ / "data" / "derivados").mkdir(exist_ok=True)
    out.merge(b.mun[["nombre"]], left_on="municipio_sk", right_index=True).to_csv(
        RAIZ / "data" / "derivados" / "prediccion_crecimiento.csv", index=False)
    (RAIZ / "data" / "derivados" / "metricas_crecimiento.json").write_text(json.dumps(res, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
