"""Validaciones de la plataforma calculadas desde la base → dw.fact_validacion (plan_migracion_front §12.4, §12.10).

Calcula V1-V9 (docs/Validations.md §20) y las pruebas de datos de rutas con lo que hay hoy en Supabase; no copia
cifras escritas a mano. La página "Metodología y fuentes" las muestra. Lo corre scripts/pipeline.py al final.

Uso: python scripts/validaciones.py      (sale con código 1 si alguna validación queda en 'falla')
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

RAIZ = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(RAIZ / "dashboard")]

import supabase_cliente as sb  # noqa: E402


def leer(t, sel="*"):
    return sb.leer(t, "dw", sel, secreta=True)


def v1(vig):
    sem = leer("fact_semaforo_municipio", "municipio_sk,dimension,version_sk")
    sem = sem[sem.version_sk == vig["semaforos_sk"]].groupby("municipio_sk").dimension.nunique()
    ctx = leer("fact_contexto_social", "municipio_sk")
    ok = int(((sem == 5).reindex(range(1, 218), fill_value=False)).sum())
    return ("V1", "Cobertura de los 217 municipios", "100 % con los 5 semáforos y contexto social",
            f"{ok}/217 con semáforos · {ctx.municipio_sk.nunique()}/217 con contexto", ok == 217 and ctx.municipio_sk.nunique() == 217)


def v2(vig):
    sem = leer("fact_semaforo_municipio", "municipio_sk,dimension,percentil,version_sk")
    sem = sem[(sem.version_sk == vig["semaforos_sk"]) & (sem.dimension == "turismo_actual")].set_index("municipio_sk")
    anc = leer("dim_municipio", "municipio_sk,es_ancla")
    anc = anc[anc.es_ancla].municipio_sk
    n = int((sem.percentil.reindex(anc).astype(float) >= 0.5).sum())
    return ("V2", "Coherencia de anclas", "Intensidad turística ≥ P50 en ≥ 11 de 12 anclas", f"{n}/{len(anc)}", n >= 11)


def v3():
    act = leer("fact_actividad_municipio", "actividad_sk,unidades,senal_catalogo")
    cat = leer("dim_actividad", "actividad_sk,codigo")
    act = act.merge(cat)
    txt = []
    for a in ("cafe", "mezcal"):
        r = act[(act.codigo == a) & act.senal_catalogo]
        txt.append(f"{a} {int((r.unidades > 0).sum())}/{len(r)}")
    return ("V3", "El DENUE detecta la actividad en los municipios de su ruta oficial",
            "Se reporta; la brecha se trata como OFERTA_SIN_REGISTRO", " · ".join(txt), True)


def v4(modelos, vig):
    m = modelos[vig["modelo"]]
    lg, b1, b2 = m["lgbm"], m["b1_media_eje"], m["b2_ridge"]
    t = m.get("validacion_temporal_2014_2019_a_2019_2024", {})
    gana = lg["mae"] < min(b1["mae"], b2["mae"]) and (not t or t["lgbm"]["spearman"] > t["b1_media_eje"]["spearman"])
    res = (f"CV: MAE {lg['mae']} vs {b1['mae']} / {b2['mae']}; Spearman {lg['spearman']}"
           + (f" · temporal: Spearman {t['lgbm']['spearman']} vs {t['b1_media_eje']['spearman']}" if t else ""))
    return ("V4", "El modelo de crecimiento gana a sus líneas base",
            "Menor MAE que media del eje y Ridge; en la prueba temporal, mayor Spearman que la media del eje", res, gana)


def v5(modelos):
    m = modelos["enlace_municipios_lgbm_v1"]
    return ("V5", "El modelo de enlaces gana a la distancia y a la similitud", "AUC mayor que ambas líneas base",
            f"AUC {m['lgbm']['auc']} vs distancia {m['b_distancia']['auc']} y similitud {m['b_similitud']['auc']}",
            m["lgbm"]["auc"] > max(m["b_distancia"]["auc"], m["b_similitud"]["auc"]))


def v6(vig):
    idx = leer("fact_indice_oportunidad")
    c = idx[idx.version_sk == vig["version_indice_sk"]]
    w = vig["pesos_indice"]
    comp = {"oferta": "score_oferta", "complementarios": "score_complementarios",
            "accesibilidad": "score_accesibilidad", "social": "score_social", "potencial_predicho": "score_potencial"}

    def top(wx):
        s = sum(wx.get(k, 0) * c[v].astype(float).fillna(0) for k, v in comp.items())
        tot = sum(wx.values())
        s = s * np.where(c.score_potencial.isna(), tot / max(tot - wx.get("potencial_predicho", 0), 1e-9), 1)
        return set(c.assign(i=s).groupby("municipio_sk").i.max().nlargest(20).index)

    base = top(w)
    res = [len(base & top({**w, k: w[k] * f})) / 20 for k in w for f in (0.8, 1.2)]
    return ("V6", "Sensibilidad del índice", "±20 % en cada peso: el top 20 conserva ≥ 70 %",
            f"{min(res):.0%}-{max(res):.0%}", min(res) >= 0.7)


def v7_rutas():
    nov = leer("v_novedad_ruta", "ruta_sk,origen,clasificacion_novedad")
    p = nov[nov.origen == "propuesta_modelo"].clasificacion_novedad.value_counts()
    n, pe = int(p.get("nueva", 0)), int(p.get("parcialmente_existente", 0))
    return ("V7", "Novedad de las rutas", "≥ 1 nueva y ≥ 1 parcialmente existente",
            f"{n} nuevas · {pe} parcialmente existentes", n >= 1 and pe >= 1)


def v8():
    e = leer("fact_escenario_concentracion").set_index("escenario")
    return ("V8", "Descentralización (escenario hipotético)", "HHI con rutas menor que hoy, presentado como hipótesis",
            f"HHI {e.hhi['hoy']:,.0f} → {e.hhi['tendencial']:,.0f} → {e.hhi['con_rutas_hipotetico']:,.0f}",
            float(e.hhi["con_rutas_hipotetico"]) < float(e.hhi["hoy"]))


def v9():
    d = leer("dim_destino_datatur", "destino_sk,nombre")
    return ("V9", "Proxy de turismo contra DATATUR", "Spearman ≥ 0.6 entre destinos con datos",
            f"No ejecutable: DATATUR público trae {len(d)} destino(s) de Puebla", None)


def rutas_operables():
    rp = leer("v_ruta_parada", "ruta_sk,origen,municipio_sk,es_ancla,es_emergente,es_pernocta,dias_sugeridos,"
                               "cumple_restricciones,tiempo_desde_anterior_min_planeacion,tiempo_total_min_planeacion")
    rp = rp[rp.origen == "propuesta_modelo"]
    rut = rp.drop_duplicates("ruta_sk")
    pern = rp.groupby("ruta_sk").es_pernocta.any()
    falla = [int(r.ruta_sk) for r in rut.itertuples()
             if not r.cumple_restricciones or (r.dias_sugeridos > 1 and not pern[r.ruta_sk])
             or float(r.tiempo_total_min_planeacion) > 240]
    tramo = float(rp.tiempo_desde_anterior_min_planeacion.astype(float).max())
    return ("R1", "Rutas del modelo operables", "5 rutas que cumplen, con pernocta si duran > 1 día, tramo ≤ 75 y "
            "total ≤ 240 min de planeación", f"{len(rut) - len(falla)}/{len(rut)} cumplen · tramo máx. {tramo:.0f} min",
            len(rut) == 5 and not falla and tramo <= 75)


def rutas_paradas():
    rp = leer("v_ruta_parada", "ruta_sk,origen,municipio_sk,es_ancla,es_emergente")
    rp = rp[(rp.origen == "propuesta_modelo") & ~rp.es_ancla]
    lug = leer("v_lugar_circuito", "municipio_sk,tipo_parada")
    vis = set(lug[lug.tipo_parada.isin(["atractivo", "experiencia"])].municipio_sk)
    vig = leer("v_vigente", "version_indice_sk").iloc[0, 0]
    fl = leer("fact_flag_oportunidad", "municipio_sk,tipo_flag_sk,flag_activo,version_sk")
    tipos = leer("dim_tipo_flag", "tipo_flag_sk,codigo")
    fl = fl[(fl.version_sk == vig) & fl.flag_activo].merge(tipos)
    otras = set(fl[fl.codigo != "BARRERA_ACCESO"].municipio_sk)
    sin_punto = int((~rp.municipio_sk.isin(vis)).sum())
    solo_barrera = int((rp.es_emergente & ~rp.municipio_sk.isin(otras)).sum())
    return ("R2", "Paradas con qué visitar y emergentes reales (§12.1)",
            "0 paradas sin punto visitable y 0 emergentes con solo BARRERA_ACCESO",
            f"{sin_punto} sin punto visitable · {solo_barrera} emergentes solo con BARRERA_ACCESO",
            sin_punto == 0 and solo_barrera == 0)


def dominio(vig):
    p = leer("fact_prediccion_crecimiento", "modelo_sk,unidades_base,crecimiento_pred_pct")
    p = p[p.modelo_sk == vig["modelo_sk"]]
    malas = int(((p.unidades_base < 3) & p.crecimiento_pred_pct.notna()).sum())
    return ("D1", "Predicción solo dentro del dominio del modelo", "0 celdas con < 3 unidades con predicción",
            f"{malas} fuera de dominio con predicción · {int(p.crecimiento_pred_pct.notna().sum())} con predicción",
            malas == 0)


def main():
    vig = sb._peticion("v_vigente?select=*", True, "dw")[0]
    modelos = {r["nombre"]: r["metricas"] for r in sb._peticion("dim_modelo?select=nombre,metricas", True, "dw")}
    filas = []
    for f in (lambda: v1(vig), lambda: v2(vig), v3, lambda: v4(modelos, vig), lambda: v5(modelos), lambda: v6(vig),
              v7_rutas, v8, v9, rutas_operables, rutas_paradas, lambda: dominio(vig)):
        codigo, desc, crit, res, ok = f()
        estado = "pendiente" if ok is None else ("ok" if ok else "falla")
        filas.append(dict(codigo=codigo, descripcion=desc, criterio=crit, resultado=res, estado=estado,
                          fecha=pd.Timestamp.now(tz="UTC").isoformat()))
        print(f"{'✅' if estado == 'ok' else '⏳' if estado == 'pendiente' else '❌'} {codigo} {desc}: {res}")
    sb.insertar("fact_validacion", filas, "dw")
    if any(f["estado"] == "falla" for f in filas):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
