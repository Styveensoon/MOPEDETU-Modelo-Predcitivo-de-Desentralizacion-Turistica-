"""Carga el modelo de crecimiento del rol B (model/prediccion_crecimiento.py --homologado) en Supabase (F4 del plan
de afinación) y registra la línea base "solo similitud" del modelo de enlaces.

- dim_modelo: los tres modelos candidatos y las tres líneas base del rol B, con sus métricas de validación temporal
  y espacial. Las líneas base llevan prefijo rolb_ para no confundirse con las del rol C.
- fact_prediccion_crecimiento: las predicciones del modelo en uso, con su propio modelo_sk. Los ejes son los de
  dw.dim_eje (el modo --homologado ya agrega con los pesos de bridge_scian_eje); no se mezclan con el rol C porque
  el modelo_sk es distinto. Mismo dominio que el rol C: con menos de 3 unidades base la predicción queda NULL.

Uso:
    python model/prediccion_crecimiento.py --homologado data/raw/censos
    python scripts/cargar_modelo_rolb.py
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

RAIZ = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(RAIZ / "model")]

import base  # noqa: E402

CARPETA = RAIZ / "data" / "modelo" / "homologado"
MIN_UNIDADES = 3
MOTIVO_FUERA = f"base menor a {MIN_UNIDADES} unidades: fuera del rango de entrenamiento"


def jsonb(texto):
    return json.loads(texto) if isinstance(texto, str) and texto.strip() else {}


def main():
    dm = pd.read_csv(CARPETA / "dim_modelo.csv")
    pred = pd.read_csv(CARPETA / "fact_prediccion_crecimiento.csv", dtype={"cve_geo": str})
    sk = {}
    for r in dm.itertuples():
        nombre = r.nombre if r.tarea != "linea_base" else f"rolb_{r.nombre}_v2_homologado"
        sk[r.nombre] = base.asegurar_modelo(dict(
            nombre=nombre, tarea=r.tarea, algoritmo=r.algoritmo,
            variables={"lista": jsonb(r.variables) or None, "objetivo": r.objetivo, "en_uso": bool(r.en_uso),
                       "intervalos": r.intervalos if isinstance(r.intervalos, str) else None,
                       "ejes": "dw.dim_eje (pesos de bridge_scian_eje)", "anclas_regiones": "dw.dim_municipio"},
            hiperparametros=jsonb(r.hiperparametros), periodo_entrenamiento=r.periodo_entrenamiento,
            periodo_validacion=r.periodo_validacion,
            esquema_validacion="Rol B: validación temporal (entrena 2014→2019, prueba 2019→2024) y espacial dejando "
                               "fuera una región; objetivo en personal ocupado (no en unidades como el rol C).",
            metricas=jsonb(r.metricas), explicabilidad=r.explicabilidad if isinstance(r.explicabilidad, str) else None,
            limitaciones=r.limitaciones))
    print(f"✓ dim_modelo: {len(sk)} registros del rol B")

    mun = base.sb.leer("dim_municipio", "dw", "municipio_sk,cve_geo", secreta=True)
    msk = dict(zip(mun.cve_geo.str.strip(), mun.municipio_sk))
    ejes = {r["codigo"]: r["eje_sk"] for r in base.sb._peticion("dim_eje?select=eje_sk,codigo", True, "dw")}
    psk = base.sb._peticion("dim_periodo?select=periodo_sk&etiqueta=eq.CE%202024", True, "dw")[0]["periodo_sk"]
    for nombre_modelo, g in pred.groupby("modelo"):
        corto = nombre_modelo.removeprefix("crecimiento_").removesuffix("_v2_homologado")
        modelo_sk = sk[f"crecimiento_{corto}_v2_homologado"]
        dentro = g.unidades_base >= MIN_UNIDADES
        filas = [dict(municipio_sk=int(msk[r.cve_geo]), eje_sk=int(ejes[r.eje]), modelo_sk=modelo_sk,
                      periodo_base_sk=psk, horizonte_anios=int(r.horizonte_anios),
                      personal_base=base.limpio(float(r.personal_base)) if pd.notna(r.personal_base) else None,
                      unidades_base=int(r.unidades_base), en_dominio=bool(d),
                      crecimiento_pred_pct=float(r.crecimiento_pred_pct) if d else None,
                      intervalo_inf_pct=float(r.intervalo_inf_pct) if d else None,
                      intervalo_sup_pct=float(r.intervalo_sup_pct) if d else None,
                      ranking_potencial=None, motivo_sin_prediccion=None if d else MOTIVO_FUERA)
                 for r, d in zip(g.itertuples(), dentro)]
        # Ranking dentro del eje solo entre celdas en dominio
        df = pd.DataFrame(filas)
        df["ranking_potencial"] = df.groupby("eje_sk").crecimiento_pred_pct.rank(ascending=False, method="min")
        filas = [{k: base.limpio(int(v) if k == "ranking_potencial" and pd.notna(v) else v) for k, v in f.items()}
                 for f in df.replace({np.nan: None}).to_dict("records")]
        base.reemplazar("fact_prediccion_crecimiento", f"modelo_sk=eq.{modelo_sk}", filas)
        print(f"✓ fact_prediccion_crecimiento: {len(filas)} filas de {nombre_modelo} (#{modelo_sk}), "
              f"{int(dentro.sum())} en dominio")

    # Línea base "solo similitud" del modelo de enlaces, con las métricas guardadas en su propio registro
    enl = base.sb._peticion("dim_modelo?select=metricas&nombre=eq.enlace_municipios_lgbm_v1", True, "dw")
    if enl and "b_similitud" in (enl[0]["metricas"] or {}):
        base.asegurar_modelo(dict(nombre="enlace_linea_base_similitud", tarea="linea_base",
                                  algoritmo="Puntaje = similitud coseno de perfiles",
                                  metricas={"cv": enl[0]["metricas"]["b_similitud"]},
                                  variables={"compara_con": "enlace_municipios_lgbm_v1"}))
        print(f"✓ dim_modelo: enlace_linea_base_similitud {enl[0]['metricas']['b_similitud']}")


if __name__ == "__main__":
    main()
