"""Pieza 1 · Índice de oportunidad por municipio × eje (v1_base) y banderas de oportunidad.

    indice = 0.35·oferta + 0.15·complementarios + 0.25·accesibilidad + 0.25·social      (pesos en dim_version_calculo)

  oferta          0.6·percentil(cociente de localización del eje) + 0.4·percentil(log personal del eje)   [DENUE]
  complementarios 0.4·percentil medio de los otros ejes + 0.3·percentil(atractivos OSM+INAH)
                  + 0.3·percentil(número de actividades presentes)                                   [DENUE, OSM]
  accesibilidad   0.7·percentil(−minutos al ancla más cercana) + 0.3·percentil(km de vías/km²)       [INEGI, OSM]
  social          percentil(marginación CONAPO 2020): más marginación = más prioridad                 [CONAPO]

Banderas (fact_flag_oportunidad), con el motivo en texto:
  OFERTA_EMERGENTE        CL ≥ 1.25 y ≥ 3 establecimientos en el eje, sin ser ancla ni Pueblo Mágico
  ACCESIBLE_NO_EXPLOTADO  ≤ 60 min de un ancla, oferta del eje baja (< P40) pero complementarios altos (≥ P50)
  BARRERA_ACCESO          oferta del eje alta (≥ P60) pero > 75 min de un ancla (tramo máximo de ruta), o > 45 min
                          con vías en el cuartil inferior
  OFERTA_SIN_REGISTRO     actividad reconocida en ruta oficial sin ningún registro en el DENUE (antes se llamaba
                          OFERTA_INVISIBLE; sql/14_banderas_visibilidad.sql)
  OFERTA_INVISIBLE        (solo v3, con dw.fact_visibilidad) oferta del eje ≥ P60 y visibilidad ≤ P35
  IMPACTO_SOCIAL          cualquiera de las anteriores en municipio con marginación alta o muy alta

Versión v3_dominio_osrm (la escribe model/crecimiento.py; plan de afinación F2-F3): tiempos por carretera, potencial
solo en celdas dentro del dominio del modelo (pesos renormalizados si falta), oferta de alimentos y comercio medida
como exceso sobre lo que explica la población (dw.v_exceso_oferta) y OFERTA_EMERGENTE en esos dos ejes solo con
residuo ≥ P75.

Uso: python model/indice.py
"""
import numpy as np
import pandas as pd

import base
from base import EJES, pct

# Umbrales de OFERTA_INVISIBLE (percentil de oferta del eje, percentil de visibilidad): los usa también el tablero
UMBRAL_INVISIBLE_OFERTA, UMBRAL_INVISIBLE_VISIBILIDAD = 0.6, 0.35
FLAGS_NUEVOS = [dict(codigo="OFERTA_SIN_REGISTRO", prioridad=1,
                     descripcion="Actividad reconocida en una ruta oficial sin registro en el DENUE (oferta informal o "
                                 "no registrada)"),
                dict(codigo="OFERTA_INVISIBLE", prioridad=1,
                     descripcion="Oferta del eje en percentil ≥ 60 con visibilidad en percentil ≤ 35 (vistas de "
                                 "Wikipedia, dw.fact_visibilidad)")]


def componentes(b: base.Base) -> pd.DataFrame:
    m = b.mun
    of = b.oferta.pivot(index="municipio_sk", columns="eje_sk", values=["cociente_localizacion", "personal_est",
                                                                        "unidades"])
    inf, soc = b.infra.reindex(m.index), b.social.reindex(m.index)

    atr = b.atractivos.groupby("municipio_sk").num_atractivos.sum().reindex(m.index).fillna(0)
    n_act = (b.actividades[~b.actividades.nivel_predominancia.isin(["sin_oferta"])]
             .groupby("municipio_sk").actividad_sk.nunique().reindex(m.index).fillna(0))
    p_oferta = {e: 0.6 * pct(of["cociente_localizacion"][e]) + 0.4 * pct(np.log1p(of["personal_est"][e]))
                for e in EJES}
    acceso = 0.7 * pct(-inf.min_ancla_cercana) + 0.3 * pct(inf.km_vias_por_km2)
    social = pct(-soc.indice_marginacion)  # índice DP2 de CONAPO: menor valor = más marginación

    filas = []
    for e in EJES:
        otros = pd.concat([p_oferta[o] for o in EJES if o != e], axis=1).mean(axis=1)
        compl = 0.4 * otros + 0.3 * pct(atr) + 0.3 * pct(n_act)
        for mk in m.index:
            filas.append(dict(municipio_sk=mk, eje_sk=e, score_oferta=p_oferta[e][mk], score_complementarios=compl[mk],
                              score_accesibilidad=acceso[mk], score_social=social[mk],
                              cl=of["cociente_localizacion"][e][mk], unidades=of["unidades"][e][mk]))
    return pd.DataFrame(filas)


def indice(c: pd.DataFrame, pesos: dict, potencial: pd.Series | None = None, renormalizar: bool = False) -> pd.DataFrame:
    """renormalizar=True: sin potencial (celda fuera de dominio) su peso se reparte entre los demás componentes
    en vez de contar como 0."""
    c = c.copy()
    c["score_potencial"] = potencial.reindex(pd.MultiIndex.from_frame(c[["municipio_sk", "eje_sk"]])).to_numpy() \
        if potencial is not None else np.nan
    c["indice_oportunidad"] = (pesos["oferta"] * c.score_oferta + pesos["complementarios"] * c.score_complementarios
                               + pesos["accesibilidad"] * c.score_accesibilidad + pesos["social"] * c.score_social
                               + pesos.get("potencial_predicho", 0) * c.score_potencial.fillna(0))
    if renormalizar:
        w_pot = pesos.get("potencial_predicho", 0)
        total = pesos["oferta"] + pesos["complementarios"] + pesos["accesibilidad"] + pesos["social"] + w_pot
        c["indice_oportunidad"] *= np.where(c.score_potencial.isna(), total / (total - w_pot), 1.0)
    c["ranking_estatal"] = c.groupby("eje_sk").indice_oportunidad.rank(ascending=False, method="min").astype(int)
    return c


def banderas(b: base.Base, c: pd.DataFrame, exceso: pd.Series | None = None,
             visibilidad: pd.Series | None = None) -> pd.DataFrame:
    """exceso (percentil del residuo de dw.v_exceso_oferta por municipio × eje): si se da, OFERTA_EMERGENTE en
    alimentos y comercio exige además residuo ≥ P75, porque esos ejes atienden sobre todo a residentes.
    visibilidad (percentil de vistas por municipio): si se da, se evalúa la OFERTA_INVISIBLE real."""
    m, inf, soc = b.mun, b.infra, b.social
    tipos = {r["codigo"]: r["tipo_flag_sk"] for r in base.sb._peticion("dim_tipo_flag?select=*", True, "dw")}
    vias_p25 = inf.km_vias_por_km2.quantile(0.25)
    act = b.actividades.merge(b.cat_act, on="actividad_sk")
    invisibles = act[act.nivel_predominancia == "reconocida_sin_registro"]
    filas = []
    for r in c.itertuples():
        mk, e = r.municipio_sk, r.eje_sk
        x = m.loc[mk]
        no_marca = not (x.es_ancla or x.es_pueblo_magico)
        minutos, vias = inf.min_ancla_cercana[mk], inf.km_vias_por_km2[mk]
        eje = EJES[e].replace("_", " ")
        residentes_ok = exceso is None or e in (1, 3) or exceso.get((mk, e), 0) >= 0.75
        reglas = {
            "OFERTA_EMERGENTE": (r.cl >= 1.25 and r.unidades >= 3 and no_marca and residentes_ok,
                                 f"Cociente de localización {r.cl:.1f} en {eje} con {r.unidades:.0f} establecimientos, "
                                 f"fuera de anclas y Pueblos Mágicos"),
            "ACCESIBLE_NO_EXPLOTADO": (minutos <= 60 and r.score_oferta < 0.4 and r.score_complementarios >= 0.5
                                       and not x.es_ancla,
                                       f"A {minutos:.0f} min de un ancla, con atractivos y actividades pero poca oferta "
                                       f"de {eje} (percentil {r.score_oferta:.0%})"),
            # 75 min = tramo máximo de una ruta: más lejos, el municipio no entra a una ruta desde un ancla
            "BARRERA_ACCESO": (r.score_oferta >= 0.6 and (minutos > 75 or (vias < vias_p25 and minutos > 45))
                               and not x.es_ancla,
                               f"Oferta de {eje} en percentil {r.score_oferta:.0%} pero a {minutos:.0f} min del ancla más "
                               f"cercana y {vias:.2f} km de vías principales/km²"),
        }
        inv = invisibles[(invisibles.municipio_sk == mk) & (invisibles.eje_sk == e)]
        reglas["OFERTA_SIN_REGISTRO"] = (len(inv) > 0, "Reconocida en ruta oficial sin registro DENUE: "
                                         + ", ".join(inv.nombre) if len(inv) else "")
        if visibilidad is not None:
            pv = visibilidad.get(mk, np.nan)
            reglas["OFERTA_INVISIBLE"] = (r.score_oferta >= UMBRAL_INVISIBLE_OFERTA and pv <= UMBRAL_INVISIBLE_VISIBILIDAD
                                          and not x.es_ancla,
                                          f"Oferta de {eje} en percentil {r.score_oferta:.0%} pero visibilidad en "
                                          f"percentil {pv:.0%} (vistas de su artículo en Wikipedia)")
        algun = any(v[0] for v in reglas.values())
        grado = str(soc.grado_marginacion.get(mk, ""))
        reglas["IMPACTO_SOCIAL"] = (algun and grado in ("Alto", "Muy alto"),
                                    f"Bandera activa en municipio con grado de marginación {grado.lower()} (CONAPO 2020)")
        for codigo, (activo, motivo) in reglas.items():
            filas.append(dict(municipio_sk=int(mk), eje_sk=int(e), tipo_flag_sk=tipos[codigo], flag_activo=bool(activo),
                              motivo=motivo if activo else None, codigo=codigo))
    return pd.DataFrame(filas)


def asegurar_flags():
    existentes = {r["codigo"] for r in base.sb._peticion("dim_tipo_flag?select=codigo", True, "dw")}
    for f in FLAGS_NUEVOS:
        if f["codigo"] not in existentes:
            base.sb._peticion("dim_tipo_flag", True, "dw", "POST", f, {"Prefer": "return=minimal"})


def guardar_indice(c: pd.DataFrame, version_sk: int, periodo_sk: int):
    cols = ["municipio_sk", "eje_sk", "score_oferta", "score_complementarios", "score_accesibilidad", "score_social",
            "indice_oportunidad", "ranking_estatal", "score_potencial"]
    filas = [{k: base.limpio(round(v, 4) if isinstance(v, float) else v) for k, v in r.items()}
             | dict(periodo_sk=periodo_sk, version_sk=version_sk) for r in c[cols].to_dict("records")]
    base.reemplazar("fact_indice_oportunidad", f"version_sk=eq.{version_sk}", filas)


def main():
    b = base.cargar()
    asegurar_flags()
    pesos = base.sb._peticion("dim_version_calculo?select=pesos&nombre=eq.v1_base", True, "dw")[0]["pesos"]
    version = base.asegurar_version("v1_base", "Índice sin predicción (model/indice.py)", pesos)
    c = indice(componentes(b), pesos)
    guardar_indice(c, version, b.periodos["DENUE 2026-05"])
    print(f"✓ fact_indice_oportunidad: {len(c)} filas (217 × 4 ejes, versión v1_base)")

    f = banderas(b, c)
    base.reemplazar("fact_flag_oportunidad", f"version_sk=eq.{version}",
                    [r | dict(version_sk=version) for r in f.drop(columns="codigo").to_dict("records")])
    activos = f[f.flag_activo]
    print(f"✓ fact_flag_oportunidad: {len(f)} filas · activas: {activos.codigo.value_counts().to_dict()} · "
          f"municipios con alguna bandera: {activos.municipio_sk.nunique()}")

    # Resumen: mejores oportunidades fuera de anclas (promedio de ejes)
    g = c.groupby("municipio_sk").indice_oportunidad.max().to_frame("indice").join(b.mun[["nombre", "es_ancla"]])
    top = g[~g.es_ancla].nlargest(10, "indice")
    print("Top 10 oportunidades (no anclas, mejor eje):", ", ".join(f"{n} {v:.2f}" for n, v in zip(top.nombre, top.indice)))
    anclas = g[g.es_ancla].indice
    print(f"Validación: índice medio anclas {anclas.mean():.2f} vs resto {g[~g.es_ancla].indice.mean():.2f}")


if __name__ == "__main__":
    main()
