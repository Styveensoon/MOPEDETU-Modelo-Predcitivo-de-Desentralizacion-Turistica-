"""Validación V8 · Concentración del turismo (HHI y % en los 5 municipios principales): hoy, tendencial y con rutas.

  Hoy:         personal turístico estimado del DENUE 05/2026 (4 ejes).
  Tendencial:  cada municipio × eje crece lo que predice el modelo (crecimiento_ue_eje_lgbm_v1).
  Con rutas:   ESCENARIO HIPOTÉTICO. Supuesto: en los municipios emergentes de las 5 rutas propuestas se
               alcanza el límite superior del intervalo de 80 % en vez de la predicción central.
Uso: python model/escenario_hhi.py
"""
import json

import numpy as np
import pandas as pd

import base
from base import RAIZ


def concentracion(s: pd.Series) -> dict:
    p = s / s.sum()
    return dict(hhi=round(float((p ** 2).sum() * 1e4), 1), pct_top5=round(float(p.nlargest(5).sum() * 100), 1))


def main():
    b = base.cargar()
    pred = base.sb.leer("fact_prediccion_crecimiento", "dw", secreta=True)
    rutas = base.sb.leer("fact_ruta_parada", "dw", secreta=True)
    propuestas = {r["ruta_sk"] for r in base.sb._peticion("dim_ruta?select=ruta_sk&origen=eq.propuesta_modelo", True, "dw")}
    emergentes = set(rutas[rutas.ruta_sk.isin(propuestas) & rutas.es_emergente].municipio_sk)

    x = b.oferta[["municipio_sk", "eje_sk", "personal_est"]].merge(pred, on=["municipio_sk", "eje_sk"])
    x["tendencial"] = x.personal_est * (1 + x.crecimiento_pred_pct / 100)
    x["con_rutas"] = np.where(x.municipio_sk.isin(emergentes), x.personal_est * (1 + x.intervalo_sup_pct / 100),
                              x.tendencial)
    res = {k: concentracion(x.groupby("municipio_sk")[c].sum()) for k, c in
           (("hoy", "personal_est"), ("tendencial_5_anios", "tendencial"), ("con_rutas_hipotetico", "con_rutas"))}
    res["municipios_emergentes_en_rutas"] = len(emergentes)
    res["supuesto"] = ("Escenario hipotético: los municipios emergentes de las rutas propuestas alcanzan el límite "
                       "superior del intervalo de 80 % de su crecimiento predicho.")
    for k in ("hoy", "tendencial_5_anios", "con_rutas_hipotetico"):
        print(f"  {k:<22} HHI {res[k]['hhi']:>7,.0f} · top 5 concentra {res[k]['pct_top5']:.1f} %")
    (RAIZ / "data" / "derivados" / "escenario_concentracion.json").write_text(json.dumps(res, indent=2, ensure_ascii=False),
                                                                             encoding="utf-8")


if __name__ == "__main__":
    main()
