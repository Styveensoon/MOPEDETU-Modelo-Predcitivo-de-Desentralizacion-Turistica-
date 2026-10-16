"""Pieza 4 · Optimizador de rutas turísticas nuevas (A6), versión optimizador_rutas_v2.

Parámetros: dw.dim_version_calculo 'optimizador_rutas_v2' (vía dw.v_vigente.parametros_rutas); los mismos que usa
el tablero.

Valor de un municipio m en una ruta de tema t (actividad):
    v(m) = índice(m, eje dominante) · (1 + 0.35·emergente) · (1 + 0.40·necesidad social) · (1 + 0.25·tema presente)
Construcción (por cada ancla × tema): inserción voraz de la parada con mayor
    v(m) · (0.5 + p_enlace(prev, m)) · (1 + 0.3·tramo nuevo) / (1 + minutos de planeación/60)
y reordenamiento 2-opt con el ancla fija al inicio.
Tiempos: OSRM de flujo libre entre cabeceras × factor de planeación por región (1.25 en las sierras y Tehuacán,
         1.10 en el resto; dw.v_tiempo_municipios.tiempo_min_planeacion). Las restricciones usan el tiempo de
         planeación; se guardan los dos.
Restricciones: 3-6 paradas · tramo ≤ 75 min · recorrido ≤ 240 min · inicia en un ancla y el resto no son anclas
               · ≥ 2 emergentes: municipios con alguna bandera activa distinta de BARRERA_ACCESO (que significa
                 justamente "lejos del ancla") · todos con el tema presente (o reconocido en catálogo)
               · sin paradas con semáforo de infraestructura rojo
               · toda parada no ancla con al menos un punto visitable (dw.v_lugar_circuito, atractivo o experiencia)
               · si traslado + estancias > 10 h: pernocta en una parada con ≥ 10 unidades de hospedaje (DENUE);
                 se prefiere una emergente cercana al fin del día 1 y, si no hay, el ancla
               · la región beneficiada (la que predomina entre las paradas) no puede ser Angelópolis
               · bono si la mayoría de las paradas comparte un mes de temporada
Selección: búsqueda exhaustiva (con poda) de la mejor combinación de 5 rutas, lexicográfica: primero el máximo de
           regiones beneficiadas distintas, luego Σ puntaje + 1.0 por cada tema distinto. ≤ 50 % de municipios
           compartidos, ≤ 2 rutas por tema, ≤ 2 rutas por ancla.
Tema:      solo cuenta presencia fuerte (alta, muy alta o reconocida en catálogo oficial). Especificidad: el puntaje
           se multiplica de ×0.85 (tema más común, p. ej. gastronomía) a ×1.15 (tema más distintivo).
Las rutas que la selección sin las reglas de operación habría elegido y que no las cumplen se guardan con
origen = 'propuesta_descartada', cumple_restricciones = false y sus incumplimientos.
Escribe dim_ruta / fact_ruta_parada (origen = 'propuesta_modelo') y fact_ruta_evaluacion; reporta v_novedad_ruta.
Uso: python model/rutas.py
"""
import numpy as np
import pandas as pd

import base
import insumos
import reglas_rutas
from base import RAIZ


def main():
    ins = insumos.cargar(secreta=True)
    elegidas, descartadas, diag = reglas_rutas.optimizar_rutas(ins)
    diag.to_csv(RAIZ / "data" / "derivados" / "rutas_candidatas.csv", index=False)
    n_fact = int(diag.factible.sum())
    print(f"Candidatas factibles: {n_fact} (anclas × temas) · elegidas: {len(elegidas)} · "
          f"descartadas registradas: {len(descartadas)}")

    m, mejor, social, hosp = ins.mun, ins.indice, ins.social, ins.hospedaje
    tiempo_libre, tiempo, dist = ins.tiempo, ins.tiempo_plan, ins.distancia
    recta = base.sb.leer("fact_accesibilidad", "dw", "municipio_origen_sk,municipio_destino_sk,tiempo_min_est,"
                                                     "distancia_km_recta", secreta=True)
    recta = recta.set_index(["municipio_origen_sk", "municipio_destino_sk"])
    tiempo_est, dist_est = recta.tiempo_min_est.astype(float).to_dict(), recta.distancia_km_recta.astype(float).to_dict()
    vig = base.sb._peticion("v_vigente?select=version_indice_sk,modelo_sk", True, "dw")[0]
    v3, modelo_sk = vig["version_indice_sk"], vig["modelo_sk"]
    crec = ins.pred.set_index(["municipio_sk", "eje_sk"]).crecimiento_pred_pct
    motivo_flag = reglas_rutas.motivo_flag(ins)
    cat_act = base.sb.leer("dim_actividad", "dw", "codigo,nombre,icono", secreta=True)

    # --- escritura
    viejas = base.sb._peticion("dim_ruta?select=ruta_sk&origen=in.(propuesta_modelo,propuesta_descartada)", True, "dw")
    if viejas:
        ids = ",".join(str(r["ruta_sk"]) for r in viejas)
        for t in ("fact_ruta_evaluacion", "fact_ruta_parada"):
            base.sb._peticion(f"{t}?ruta_sk=in.({ids})", True, "dw", "DELETE")
        base.sb._peticion(f"dim_ruta?ruta_sk=in.({ids})", True, "dw", "DELETE")
    nom_act = dict(zip(cat_act.codigo, cat_act.nombre))
    ico_act = dict(zip(cat_act.codigo, cat_act.icono))
    meses_txt = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"]

    def escribir(e, i, origen):
        ruta, tema = e["ruta"], e["tema"]
        nombres = [m.nombre[x] for x in ruta]
        crec_ruta = [crec.get((x, int(mejor.eje_sk[x])), np.nan) for x in ruta[1:]]
        crec_medio = np.nanmean(crec_ruta) if np.isfinite(crec_ruta).any() else np.nan
        desc = (f"{ico_act[tema]} Ruta de {nom_act[tema].lower()} que parte de {nombres[0]} (ancla) hacia "
                f"{len(e['emergentes'])} municipios emergentes con bandera de oportunidad: "
                + "; ".join(f"{m.nombre[x]} ({', '.join(motivo_flag.get(x, []))})" for x in e["emergentes"])
                + f". Recorrido {e['minutos']:.0f} min por carretera, {e['horas']} h con estancias"
                + (f" en {e['dias']} días con pernocta en {m.nombre[e['pernocta']]}" if e["pernocta"] else "")
                + ". "
                + (f"Crecimiento esperado medio {crec_medio:+.0f} % a 5 años. " if np.isfinite(crec_medio) else "")
                + f"{e['tramos_nuevos']:.0%} de los tramos no existe en rutas oficiales."
                + (f" Temporada compartida: {', '.join(meses_txt[k - 1] for k in e['meses_comunes'])}."
                   if e["meses_comunes"] else "")
                + (f" Descartada: {', '.join(e['incumplimientos'])}." if e["incumplimientos"] else ""))
        etiqueta = "propuesta" if origen == "propuesta_modelo" else "descartada"
        fila = dict(nombre=f"{nom_act[tema]} · {nombres[0]} → {nombres[-1]} ({etiqueta} {i})",
                    tipo="ruta_intermunicipal", tema=tema, es_monotematica=True, origen=origen,
                    version_sk=v3, num_municipios=len(ruta), duracion_estimada_h=e["horas"], descripcion=desc[:1500])
        sk = base.sb._peticion("dim_ruta", True, "dw", "POST", fila, {"Prefer": "return=representation"})[0]["ruta_sk"]
        paradas = []
        for k, x in enumerate(ruta):
            prev = ruta[k - 1] if k else None
            paradas.append(dict(ruta_sk=sk, orden_parada=k + 1, municipio_sk=int(x), eje_sk=int(mejor.eje_sk[x]),
                                distancia_desde_anterior_km=round(dist_est[(prev, x)], 2) if prev else None,
                                tiempo_desde_anterior_min=round(tiempo_est[(prev, x)], 1) if prev else None,
                                distancia_desde_anterior_km_real=round(dist[(prev, x)], 2) if prev else None,
                                tiempo_desde_anterior_min_real=round(tiempo_libre[(prev, x)], 1) if prev else None,
                                tiempo_desde_anterior_min_planeacion=round(tiempo[(prev, x)], 1) if prev else None,
                                es_ancla=bool(m.es_ancla[x]), es_emergente=x in e["emergentes"],
                                estancia_sugerida_h=e["estancias"][k], es_pernocta=x == e["pernocta"],
                                unidades_hospedaje=int(hosp.get(x, 0))))
        base.sb._peticion("fact_ruta_parada", True, "dw", "POST", paradas, {"Prefer": "return=minimal"})
        base.sb._peticion("fact_ruta_evaluacion", True, "dw", "POST", dict(
            ruta_sk=sk, modelo_sk=modelo_sk, version_sk=v3,
            tiempo_total_min=round(sum(tiempo_est[(a, c)] for a, c in zip(ruta, ruta[1:])), 1),
            tiempo_total_min_real=round(e["minutos"], 1), tiempo_total_min_planeacion=round(e["minutos_plan"], 1),
            potencial_pred_medio_pct=base.limpio(round(float(crec_medio), 2)),
            necesidad_social_media=round(float(np.mean([social[x] for x in ruta[1:]])), 3),
            num_municipios_emergentes=len(e["emergentes"]), puntaje_total=round(float(e["puntaje"]), 4),
            dias_sugeridos=e["dias"], region_beneficiada=e["region"], cumple_restricciones=not e["incumplimientos"],
            incumplimientos=e["incumplimientos"], paradas_infra_rojo=e["infra_rojo"]),
            {"Prefer": "return=minimal"})
        return sk, fila["nombre"], " → ".join(nombres), e

    resumen = [escribir(e, i, "propuesta_modelo") for i, e in enumerate(elegidas, 1)]
    for i, e in enumerate(descartadas, 1):
        sk, nombre, recorrido_txt, _ = escribir(e, i, "propuesta_descartada")
        print(f"  descartada #{sk} {nombre}: {', '.join(e['incumplimientos'])} · {recorrido_txt}")
    print(f"✓ dim_ruta / fact_ruta_parada / fact_ruta_evaluacion: {len(resumen)} rutas propuestas")

    nov = base.sb.leer("v_novedad_ruta", "dw", secreta=True).set_index("ruta_sk")
    for sk, nombre, recorrido_txt, e in resumen:
        n = nov.loc[sk]
        print(f"  #{sk} {nombre}\n      {recorrido_txt} · {e['minutos']:.0f} min · {e['dias']} día(s)"
              + (f", pernocta en {m.nombre[e['pernocta']]}" if e["pernocta"] else "")
              + f" · región {e['region']} · emergentes {len(e['emergentes'])} · "
              f"enlace P{e['enlace_medio']:.0%} · novedad: {n.clasificacion_novedad} "
              f"({n.pct_tramos_existentes:.0f} % tramos existentes)")
    pd.DataFrame([dict(ruta_sk=sk, nombre=n_, recorrido=r_, puntaje=e["puntaje"], minutos=e["minutos"],
                       novedad=nov.loc[sk].clasificacion_novedad) for sk, n_, r_, e in resumen]).to_csv(
        RAIZ / "data" / "derivados" / "rutas_propuestas.csv", index=False)


if __name__ == "__main__":
    main()
