"""Validación V8 · Concentración del turismo (HHI, % en los 5 municipios principales y Gini): hoy, tendencial y con rutas.

  Hoy:         personal turístico estimado del DENUE 05/2026 (4 ejes).
  Tendencial:  cada municipio × eje crece lo que predice el modelo vigente (dw.v_vigente; fuera de dominio, sin
               cambio).
  Con rutas:   ESCENARIO HIPOTÉTICO. Supuesto: en los municipios emergentes de las 5 rutas propuestas se
               alcanza el límite superior del intervalo de 80 % en vez de la predicción central.
Escribe dw.fact_escenario_concentracion (plan_migracion_front A8) y data/derivados/escenario_concentracion.json.
Las fórmulas están en model/metricas.py, las mismas que usa el tablero.
Uso: python model/escenario_hhi.py
"""
import json

import numpy as np

import base
import metricas
from base import RAIZ

ESCENARIOS = (("hoy", "personal_est"), ("tendencial", "tendencial"), ("con_rutas_hipotetico", "con_rutas"))
SUPUESTOS = {
    "hoy": "Personal turístico estimado del DENUE 05/2026 (4 ejes).",
    "tendencial": "Cada municipio × eje crece lo que predice el modelo de crecimiento vigente a 5 años; las celdas "
                  "fuera del dominio del modelo (< 3 unidades) se mantienen en su valor actual.",
    "con_rutas_hipotetico": "Escenario hipotético: los municipios emergentes de las rutas propuestas alcanzan el "
                            "límite superior del intervalo de 80 % de su crecimiento predicho; el resto sigue la "
                            "tendencia. No es una predicción.",
}


def main():
    b = base.cargar()
    vig = base.sb._peticion("v_vigente?select=modelo_sk,version_indice_sk,modelo", True, "dw")[0]
    pred = base.sb.leer("fact_prediccion_crecimiento", "dw", secreta=True)
    pred = pred[pred.modelo_sk == vig["modelo_sk"]].copy()
    pred[["crecimiento_pred_pct", "intervalo_sup_pct"]] = pred[["crecimiento_pred_pct", "intervalo_sup_pct"]].fillna(0)
    rutas = base.sb.leer("fact_ruta_parada", "dw", secreta=True)
    propuestas = {r["ruta_sk"] for r in base.sb._peticion("dim_ruta?select=ruta_sk&origen=eq.propuesta_modelo", True, "dw")}
    emergentes = set(rutas[rutas.ruta_sk.isin(propuestas) & rutas.es_emergente].municipio_sk)

    x = b.oferta[["municipio_sk", "eje_sk", "personal_est"]].merge(pred, on=["municipio_sk", "eje_sk"])
    x["tendencial"] = x.personal_est * (1 + x.crecimiento_pred_pct / 100)
    x["con_rutas"] = np.where(x.municipio_sk.isin(emergentes), x.personal_est * (1 + x.intervalo_sup_pct / 100),
                              x.tendencial)
    res, filas = {}, []
    for nombre, col in ESCENARIOS:
        v = x.groupby("municipio_sk")[col].sum()
        r = dict(hhi=round(metricas.hhi(v), 1), pct_top5=round(metricas.pct_top(v), 1), gini=round(metricas.gini(v), 3))
        res[nombre] = r
        filas.append(dict(escenario=nombre, **r, supuesto=SUPUESTOS[nombre], modelo_sk=vig["modelo_sk"],
                          version_sk=vig["version_indice_sk"]))
        print(f"  {nombre:<22} HHI {r['hhi']:>7,.0f} · top 5 concentra {r['pct_top5']:.1f} % · Gini {r['gini']:.3f}")
    base.sb.insertar("fact_escenario_concentracion", filas, "dw")
    res["municipios_emergentes_en_rutas"] = len(emergentes)
    res["supuesto"] = SUPUESTOS["con_rutas_hipotetico"]
    res["modelo"] = vig["modelo"]
    (RAIZ / "data" / "derivados" / "escenario_concentracion.json").write_text(
        json.dumps(res, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"✓ fact_escenario_concentracion: {len(filas)} escenarios")


if __name__ == "__main__":
    main()
