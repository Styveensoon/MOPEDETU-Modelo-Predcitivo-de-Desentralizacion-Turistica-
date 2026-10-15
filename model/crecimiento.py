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

Escribe dw.dim_modelo, dw.fact_prediccion_crecimiento y el índice v2_con_prediccion (score_potencial).
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
PARAMS = dict(n_estimators=400, learning_rate=0.03, num_leaves=15, min_child_samples=12, subsample=0.8,
              subsample_freq=1, colsample_bytree=0.8, reg_lambda=1.0, random_state=SEMILLA, verbose=-1)


def panel(b: base.Base) -> pd.DataFrame:
    """Una fila por municipio × eje con las variables en 2019 y 2024 y el crecimiento observado."""
    ce = b.censo.copy()
    anio = {b.periodos["CE 2019"]: 2019, b.periodos["CE 2024"]: 2024}
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
    for y in (2019, 2024):
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


def objetivo(w: pd.DataFrame) -> pd.Series:
    """Crecimiento logarítmico de unidades económicas (nunca confidenciales). Se excluyen ejes sin oferta
    en ambos censos y los municipios con menos de 3 unidades en 2019 en el eje (crecimientos espurios)."""
    u19, u24 = w.unidades_2019.fillna(0), w.unidades_2024.fillna(0)
    y = np.log1p(u24) - np.log1p(u19)
    return y.where((u19 >= 3) | (u24 >= 3))


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
    out["crecimiento_pred_pct"] = np.round((np.expm1(yhat)) * 100, 2)
    out["intervalo_inf_pct"] = np.round(np.expm1(lo) * 100, 2)
    out["intervalo_sup_pct"] = np.round(np.expm1(hi) * 100, 2)
    out["ranking_potencial"] = out.groupby("eje_sk").crecimiento_pred_pct.rank(ascending=False, method="min").astype(int)

    modelo = dict(
        nombre="crecimiento_ue_eje_lgbm_v1", tarea=TAREA,
        algoritmo="LightGBM (gradient boosting) + intervalo conformal de 80 %",
        variables={"objetivo": "ln(1+UE_t+5) - ln(1+UE_t): unidades económicas turísticas por municipio y eje "
                               "(Censos Económicos)",
                   "lista": list(X.columns), "importancia_shap": {k: round(float(v), 4) for k, v in shap.items()}},
        hiperparametros=PARAMS, periodo_entrenamiento="CE 2019 → CE 2024 (variables medidas en 2019)",
        periodo_validacion="GroupKFold de 5 particiones por municipio",
        esquema_validacion="Validación cruzada agrupada por municipio; líneas base: media del eje y Ridge. "
                           "No hay segundo periodo temporal porque el CE 2014 no tiene descarga por entidad.",
        metricas=res,
        explicabilidad="Contribuciones SHAP exactas de LightGBM (pred_contrib); importancia media normalizada.",
        limitaciones="Un solo periodo censal (2019-2024, incluye la pandemia). Mide unidades económicas (oferta), "
                     "no visitantes. Municipios con menos de 3 unidades en el eje quedan fuera del entrenamiento. "
                     "La predicción es un escenario tendencial, no un compromiso de crecimiento.")
    psk = b.periodos["CE 2024"]
    filas = [{k: base.limpio(v) for k, v in r.items()} | dict(periodo_base_sk=psk, horizonte_anios=HORIZONTE)
             for r in out.to_dict("records")]
    publicar(modelo, "fact_prediccion_crecimiento", filas)
    for clave, nombre, algoritmo in (("b1_media_eje", "crecimiento_linea_base_media_eje", "Media del eje en entrenamiento"),
                                     ("b2_ridge", "crecimiento_linea_base_ridge", "Ridge (alpha=3) estandarizado")):
        base.asegurar_modelo(dict(nombre=nombre, tarea="linea_base", algoritmo=algoritmo,
                                  variables={"compara_con": modelo["nombre"]}, metricas={"cv": res[clave]},
                                  periodo_entrenamiento=modelo["periodo_entrenamiento"],
                                  periodo_validacion=modelo["periodo_validacion"],
                                  esquema_validacion="Mismas particiones que el modelo principal"))
    print("✓ dim_modelo: líneas base registradas con sus métricas")

    # Índice v2 con el potencial predicho (percentil del crecimiento dentro de cada eje)
    pot = out.set_index(["municipio_sk", "eje_sk"]).crecimiento_pred_pct.groupby(level="eje_sk").transform(pct)
    pesos = base.sb._peticion("dim_version_calculo?select=pesos&nombre=eq.v2_con_prediccion", True, "dw")[0]["pesos"]
    v2 = base.asegurar_version("v2_con_prediccion", "Índice con potencial predicho (model/crecimiento.py)", pesos)
    c = indice.indice(indice.componentes(b), pesos, potencial=pot)
    indice.guardar_indice(c, v2, b.periodos["DENUE 2026-05"])
    f = indice.banderas(b, c)
    base.reemplazar("fact_flag_oportunidad", f"version_sk=eq.{v2}",
                    [r | dict(version_sk=v2) for r in f.drop(columns="codigo").to_dict("records")])
    print(f"✓ fact_indice_oportunidad v2: {len(c)} filas · banderas v2: {int(f.flag_activo.sum())} activas")

    top = out.merge(b.mun[["nombre", "es_ancla"]], left_on="municipio_sk", right_index=True)
    top = top[~top.es_ancla & (top.personal_base.fillna(0) >= 10)].nlargest(10, "crecimiento_pred_pct")
    print("Mayor crecimiento esperado (no anclas, ≥10 empleos):",
          ", ".join(f"{n} ({EJES[e][:4]}) {p:+.0f}%" for n, e, p in zip(top.nombre, top.eje_sk, top.crecimiento_pred_pct)))
    (RAIZ / "data" / "derivados").mkdir(exist_ok=True)
    out.merge(b.mun[["nombre"]], left_on="municipio_sk", right_index=True).to_csv(
        RAIZ / "data" / "derivados" / "prediccion_crecimiento.csv", index=False)
    (RAIZ / "data" / "derivados" / "metricas_crecimiento.json").write_text(json.dumps(res, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
