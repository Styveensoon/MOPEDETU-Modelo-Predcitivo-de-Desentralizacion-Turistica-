"""Pieza 3 · Perfiles, similitud, clusters y modelo de enlaces entre municipios (A5).

Perfil (por municipio, valores en [0, 1]):
  14 actividades (score de fact_actividad_municipio) · 4 ejes (percentil del cociente de localización)
  · 12 meses de temporada propia · intensidad turística · marginación · accesibilidad
Similitud:  coseno de los perfiles (todos no negativos → [0, 1]) → dw.fact_similitud (pares a < b, ≤ 150 min)
Clusters:   k-means sobre el perfil; k elegido por silueta (5-9); etiqueta = rasgos dominantes del centroide
            → dw.fact_cluster_municipio
Enlaces:    ¿forman (a, b) un tramo de ruta? Positivos = tramos consecutivos de las 29 rutas oficiales.
            Negativos = demás pares a ≤ 150 min. LightGBM con validación agrupada por ruta (GroupKFold);
            líneas base: solo distancia y solo similitud. → dw.fact_prediccion_enlace
            (validación: StratifiedGroupKFold, grupos = ruta; ver nota en main)
Uso: python model/enlaces.py
"""
import warnings

import lightgbm as lgb
import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.metrics import average_precision_score, roc_auc_score, silhouette_score
from sklearn.model_selection import StratifiedGroupKFold

import base
from base import EJES, RAIZ, pct, publicar

warnings.filterwarnings("ignore")
SEMILLA = 2026
MAX_MIN = 150  # universo de pares: hasta 2.5 h de distancia estimada
PARAMS = dict(n_estimators=300, learning_rate=0.03, num_leaves=15, min_child_samples=10, subsample=0.8,
              subsample_freq=1, colsample_bytree=0.8, random_state=SEMILLA, verbose=-1, class_weight="balanced")


def meses_fuertes(b: base.Base) -> pd.DataFrame:
    """12 columnas 0/1: meses con temporada propia (eventos del municipio + temporadas de sus actividades principales)."""
    t = b.temporadas
    principales = b.actividades[b.actividades.es_principal][["municipio_sk", "actividad_sk"]]
    out = pd.DataFrame(0, index=b.mun.index, columns=range(1, 13))
    def rango(i, f):
        return list(range(i, f + 1)) if i <= f else list(range(i, 13)) + list(range(1, f + 1))
    for r in t[t.municipio_sk.notna() & (t.intensidad >= 2)].itertuples():
        out.loc[int(r.municipio_sk), rango(r.mes_inicio, r.mes_fin)] = 1
    for r in t[t.municipio_sk.isna() & t.actividad_sk.notna()].itertuples():
        for mk in principales[principales.actividad_sk == r.actividad_sk].municipio_sk:
            out.loc[mk, rango(r.mes_inicio, r.mes_fin)] = 1
    return out


def perfiles(b: base.Base) -> pd.DataFrame:
    act = b.actividades.merge(b.cat_act[["actividad_sk", "codigo"]]).pivot(
        index="municipio_sk", columns="codigo", values="score").reindex(b.mun.index).fillna(0)
    act = act / act.max().replace(0, 1)
    ejes = b.oferta.pivot(index="municipio_sk", columns="eje_sk", values="cociente_localizacion")
    ejes = ejes.apply(pct).rename(columns=lambda e: f"eje_{EJES[e]}")
    meses = meses_fuertes(b).add_prefix("mes_")
    extra = pd.DataFrame({
        "intensidad": pct(b.infra.intensidad_turistica),
        "marginacion": pct(-b.social.indice_marginacion),
        "accesibilidad": pct(-b.infra.min_ancla_cercana),
    }, index=b.mun.index)
    # Pesos de bloque: el tema (actividades y ejes) define la compatibilidad; temporada y contexto la matizan
    return pd.concat([act * 1.0, ejes * 0.8, meses * 0.35, extra * 0.5], axis=1).fillna(0)


def similitud(P: pd.DataFrame) -> pd.DataFrame:
    V = P.to_numpy()
    n = np.linalg.norm(V, axis=1, keepdims=True)
    S = (V / np.where(n == 0, 1, n)) @ (V / np.where(n == 0, 1, n)).T
    return pd.DataFrame(np.clip(S, 0, 1), index=P.index, columns=P.index)


def clusters(P: pd.DataFrame, b: base.Base) -> tuple[pd.Series, dict]:
    X = (P - P.mean()) / P.std().replace(0, 1)
    mejor = max(range(5, 10), key=lambda k: silhouette_score(
        X, KMeans(k, n_init=20, random_state=SEMILLA).fit_predict(X)))
    km = KMeans(mejor, n_init=20, random_state=SEMILLA).fit(X)
    lab = pd.Series(km.labels_, index=P.index)
    nombres_act = dict(zip(b.cat_act.codigo, b.cat_act.nombre)) | {
        "marginacion": "alta marginación", "intensidad": "turismo consolidado", "accesibilidad": "cerca de anclas",
        "eje_hospedaje": "hospedaje", "eje_alimentos": "restaurantes", "eje_turismo": "servicios turísticos",
        "eje_comercio_turistico": "comercio turístico"}
    etiquetas = {}
    for c in range(mejor):
        cen = pd.Series(km.cluster_centers_[c], index=P.columns)
        rasgos = [k for k in cen.sort_values(ascending=False).index if not k.startswith("mes_")][:2]
        txt = [nombres_act.get(k, k.replace("eje_", "").replace("_", " ")) for k in rasgos]
        miembros = b.mun.loc[lab[lab == c].index]
        region = miembros.region.mode().iat[0]
        etiquetas[c] = f"{' + '.join(txt)} · {region}"[:120]
    return lab, {"k": mejor, "etiquetas": etiquetas}


def pares_existentes(b: base.Base) -> pd.DataFrame:
    filas = []
    for ruta, g in b.rutas.sort_values("orden_parada").groupby("ruta_sk"):
        ms = g.municipio_sk.tolist()
        for a, c in zip(ms, ms[1:]):
            if a != c:
                filas.append(dict(a=min(a, c), b=max(a, c), ruta_sk=ruta))
    return pd.DataFrame(filas).drop_duplicates(["a", "b"])


def tabla_pares(b: base.Base, S: pd.DataFrame, lab: pd.Series, M: pd.DataFrame) -> pd.DataFrame:
    acc = b.acceso[b.acceso.municipio_origen_sk < b.acceso.municipio_destino_sk]
    acc = acc[acc.tiempo_min_est <= MAX_MIN].rename(columns={"municipio_origen_sk": "a", "municipio_destino_sk": "b"})
    m, inf, soc = b.mun, b.infra, b.social
    principales = b.actividades[b.actividades.es_principal].groupby("municipio_sk").actividad_sk.apply(set)
    lider = b.actividades[b.actividades.rango_en_municipio == 1].set_index("municipio_sk").actividad_sk
    atr = np.log1p(b.atractivos.groupby("municipio_sk").num_atractivos.sum()).reindex(m.index).fillna(0)
    inten = inf.intensidad_turistica
    a, c = acc.a.to_numpy(), acc.b.to_numpy()
    X = pd.DataFrame({
        "distancia_km": acc.distancia_km_recta.to_numpy(),
        "colindante": acc.es_colindante.astype(float).to_numpy(),
        "misma_region": (m.region.reindex(a).to_numpy() == m.region.reindex(c).to_numpy()).astype(float),
        "similitud": S.to_numpy()[S.index.get_indexer(a), S.columns.get_indexer(c)],
        "mismo_cluster": (lab.reindex(a).to_numpy() == lab.reindex(c).to_numpy()).astype(float),
        "act_compartidas": [len(principales.get(x, set()) & principales.get(y, set())) for x, y in zip(a, c)],
        "misma_lider": [float(lider.get(x, -1) == lider.get(y, -2)) for x, y in zip(a, c)],
        "meses_compartidos": (M.reindex(a).to_numpy() * M.reindex(c).to_numpy()).sum(axis=1),
        "intensidad_max": np.maximum(inten.reindex(a).to_numpy(), inten.reindex(c).to_numpy()),
        "intensidad_min": np.minimum(inten.reindex(a).to_numpy(), inten.reindex(c).to_numpy()),
        "anclas": m.es_ancla.reindex(a).to_numpy().astype(float) + m.es_ancla.reindex(c).to_numpy().astype(float),
        "pueblos_magicos": (m.es_pueblo_magico.reindex(a).to_numpy().astype(float)
                            + m.es_pueblo_magico.reindex(c).to_numpy().astype(float)),
        "atractivos_min": np.minimum(atr.reindex(a).to_numpy(), atr.reindex(c).to_numpy()),
        "dif_marginacion": np.abs(soc.indice_marginacion.reindex(a).to_numpy() - soc.indice_marginacion.reindex(c).to_numpy()),
    })
    X.insert(0, "a", a)
    X.insert(1, "b", c)
    return X


def main():
    b = base.cargar()
    P = perfiles(b)
    S = similitud(P)
    lab, info = clusters(P, b)
    M = meses_fuertes(b)
    version = base.asegurar_version("perfil_v1", "Perfiles, similitud y clusters de municipios (model/enlaces.py)",
                                    {"bloques": {"actividades": 1.0, "ejes": 0.8, "meses": 0.35, "contexto": 0.5},
                                     "k": info["k"], "max_minutos_pares": MAX_MIN})

    filas_c = [dict(municipio_sk=int(mk), version_sk=version, cluster_id=int(c), etiqueta=info["etiquetas"][c])
               for mk, c in lab.items()]
    base.reemplazar("fact_cluster_municipio", f"version_sk=eq.{version}", filas_c)
    print(f"✓ fact_cluster_municipio: {len(filas_c)} municipios en {info['k']} clusters")
    for c, e in info["etiquetas"].items():
        miembros = b.mun.loc[lab[lab == c].index]
        print(f"   {c}: {e} ({len(miembros)}) · ej. {', '.join(miembros.nombre.head(4))}")

    X = tabla_pares(b, S, lab, M)
    filas_s = [dict(municipio_a_sk=int(r.a), municipio_b_sk=int(r.b), version_sk=version,
                    similitud=round(float(r.similitud), 4)) for r in X.itertuples()]
    base.reemplazar("fact_similitud", f"version_sk=eq.{version}", filas_s, lote=2000)
    print(f"✓ fact_similitud: {len(filas_s):,} pares a ≤ {MAX_MIN} min")

    pos = pares_existentes(b)
    X = X.merge(pos, on=["a", "b"], how="left")
    y = X.ruta_sk.notna().astype(int)
    fuera = len(pos) - y.sum()
    # Grupos: la ruta para los positivos; para los negativos, un grupo pseudoaleatorio estable
    grupos = np.where(y == 1, X.ruta_sk.fillna(0).astype(int), 1000 + (X.a * 7 + X.b) % 29)
    F = X.drop(columns=["a", "b", "ruta_sk"])
    pred = np.zeros(len(X))
    # StratifiedGroupKFold: agrupa por ruta Y reparte positivos en todas las particiones
    # (GroupKFold juntaba las 29 rutas —grupos pequeños— en una sola partición sin positivos para entrenar)
    for tr, te in StratifiedGroupKFold(n_splits=5, shuffle=True, random_state=SEMILLA).split(F, y, grupos):
        pred[te] = lgb.LGBMClassifier(**PARAMS).fit(F.iloc[tr], y.iloc[tr]).predict_proba(F.iloc[te])[:, 1]
    res = {
        "lgbm": dict(auc=round(roc_auc_score(y, pred), 3), ap=round(average_precision_score(y, pred), 3)),
        "b_distancia": dict(auc=round(roc_auc_score(y, -F.distancia_km), 3),
                            ap=round(average_precision_score(y, -F.distancia_km), 3)),
        "b_similitud": dict(auc=round(roc_auc_score(y, F.similitud), 3),
                            ap=round(average_precision_score(y, F.similitud), 3)),
        "positivos": int(y.sum()), "pares": int(len(y)), "tasa_base": round(float(y.mean()), 4),
        "positivos_fuera_de_universo": int(fuera),
    }
    for k in ("lgbm", "b_distancia", "b_similitud"):
        print(f"  {k:<12} AUC {res[k]['auc']:.3f} · precisión media (AP) {res[k]['ap']:.3f}")
    print(f"  {res['positivos']} tramos oficiales entre {res['pares']:,} pares (tasa base {res['tasa_base']:.2%})")

    final = lgb.LGBMClassifier(**PARAMS).fit(F, y)
    shap = pd.DataFrame(final.predict(F, pred_contrib=True)[:, :-1], columns=F.columns).abs().mean()
    shap = (shap / shap.sum()).sort_values(ascending=False)
    print("  variables más influyentes (SHAP):", ", ".join(f"{k} {v:.0%}" for k, v in shap.head(6).items()))
    # Probabilidad calibrada al orden: percentil de la probabilidad del modelo (se conserva el valor crudo en [0,1])
    prob = final.predict_proba(F)[:, 1]
    modelo = dict(
        nombre="enlace_municipios_lgbm_v1", tarea="enlace_municipios",
        algoritmo="LightGBM clasificador (class_weight balanced)",
        variables={"objetivo": "par (a, b) consecutivo en alguna de las 29 rutas oficiales",
                   "lista": list(F.columns), "importancia_shap": {k: round(float(v), 4) for k, v in shap.items()}},
        hiperparametros={k: v for k, v in PARAMS.items()}, periodo_entrenamiento="Catálogo de rutas Sectur 2026",
        periodo_validacion="StratifiedGroupKFold de 5 particiones agrupado por ruta",
        esquema_validacion="Los tramos de una misma ruta nunca se reparten entre entrenamiento y prueba; "
                           "líneas base: solo distancia y solo similitud de perfil.",
        metricas=res, explicabilidad="Contribuciones SHAP de LightGBM (pred_contrib)",
        limitaciones="Aprende cómo arma rutas la Secretaría (sesgo hacia anclas y municipios conocidos); por eso el "
                     "optimizador combina esta probabilidad con el índice y las banderas para llevar la ruta a "
                     "municipios emergentes. Pocos positivos (tramos oficiales).")
    filas_e = [dict(municipio_a_sk=int(a), municipio_b_sk=int(c), probabilidad=round(float(p), 4))
               for a, c, p in zip(X.a, X.b, prob)]
    publicar(modelo, "fact_prediccion_enlace", filas_e)
    base.asegurar_modelo(dict(nombre="enlace_linea_base_distancia", tarea="linea_base",
                              algoritmo="Puntaje = −distancia", metricas={"cv": res["b_distancia"]},
                              variables={"compara_con": modelo["nombre"]}))
    base.asegurar_modelo(dict(nombre="enlace_linea_base_similitud", tarea="linea_base",
                              algoritmo="Puntaje = similitud coseno de perfiles", metricas={"cv": res["b_similitud"]},
                              variables={"compara_con": modelo["nombre"]}))
    X.assign(prob=prob, cv=pred).to_csv(RAIZ / "data" / "derivados" / "enlaces_pares.csv", index=False)


if __name__ == "__main__":
    main()
