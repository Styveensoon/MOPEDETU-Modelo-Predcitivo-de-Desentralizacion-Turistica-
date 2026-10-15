"""Pieza 4 · Optimizador de rutas turísticas nuevas (A6).

Valor de un municipio m en una ruta de tema t (actividad):
    v(m) = índice_v2(m, eje dominante) · (1 + 0.35·bandera) · (1 + 0.20·necesidad social) · (1 + 0.25·tema presente)
Construcción (por cada ancla × tema): inserción voraz de la parada con mayor
    v(m) · (0.5 + p_enlace(prev, m)) · (1 + 0.3·tramo nuevo) / (1 + minutos/60)
y reordenamiento 2-opt con el ancla fija al inicio.
Restricciones: 3-6 paradas · tramo ≤ 75 min · recorrido ≤ 240 min · inicia en un ancla y el resto no son anclas
               · ≥ 2 municipios con bandera activa · todos con el tema presente (o reconocido en catálogo)
               · al menos un mes de temporada compartido por la mayoría de las paradas (bono)
Selección: búsqueda exhaustiva (con poda) de la mejor combinación de 5 rutas, lexicográfica: primero el
           máximo de regiones beneficiadas distintas, luego Σ puntaje + 1.0 por cada tema distinto. Región de la ruta = la que predomina entre sus
           paradas (donde llega el beneficio, no la del ancla). Restricciones: ≤ 50 % de municipios compartidos,
           ≤ 2 rutas por tema, ≤ 2 rutas por ancla (Puebla es la puerta de entrada del estado).
Tema:      solo cuenta presencia fuerte (alta, muy alta o reconocida en catálogo oficial). Especificidad: el
           puntaje se multiplica de ×0.85 (tema más común, p. ej. gastronomía) a ×1.15 (tema más distintivo).
Escribe dim_ruta / fact_ruta_parada (origen = 'propuesta_modelo') y fact_ruta_evaluacion; reporta v_novedad_ruta.
Uso: python model/rutas.py
"""
import itertools

import numpy as np
import pandas as pd

import base
import enlaces
from base import EJES, RAIZ, pct

MAX_TRAMO, MAX_TOTAL, MIN_PARADAS, MAX_PARADAS = 75, 240, 3, 6
N_RUTAS, MAX_SOLAPE = 5, 0.5
ESTANCIA = {True: 3.0, False: 2.0}  # horas sugeridas: ancla / municipio emergente
# "comunitario" queda fuera: se detecta por palabras como "cooperativa" o "ejido" en el nombre del negocio y
# esa señal es ruidosa (restaurantes, cooperativas escolares). Se reincorpora con un catálogo de cooperativas turísticas.
TEMAS = ["cafe", "mezcal", "ecoturismo", "gastronomia", "artesanias", "bebidas_tradicionales", "religioso",
         "balnearios", "flores_viveros", "museos", "arqueologia", "volcanes"]
# Criterio lexicográfico: primero el número de regiones beneficiadas distintas (descentralizar es el objetivo),
# luego la calidad. BONO_REGION es mayor que cualquier diferencia posible de puntajes, así que una región más
# siempre gana; BONO_TEMA premia la variedad de temas.
BONO_REGION, BONO_TEMA = 100.0, 1.0
MAX_POR_ANCLA = 2                   # Puebla y otras anclas pueden ser puerta de entrada de hasta 2 rutas


def seleccionar(candidatas: list) -> list:
    """Mejor combinación de N_RUTAS rutas (búsqueda exhaustiva con poda):
    máx. Σ puntaje + BONO_REGION·(regiones beneficiadas distintas) + BONO_TEMA·(temas distintos)
    s.a. ≤ 50 % de municipios compartidos entre dos rutas, ≤ 2 rutas por tema, ≤ MAX_POR_ANCLA por ancla."""
    n = len(candidatas)
    conj = [set(e["ruta"]) for e in candidatas]
    compat = [[len(conj[i] & conj[j]) / min(len(conj[i]), len(conj[j])) <= MAX_SOLAPE for j in range(n)]
              for i in range(n)]
    cota = sorted((e["puntaje"] for e in candidatas), reverse=True)
    mejor = {"valor": -np.inf, "sel": []}

    def valor(sel):
        es = [candidatas[i] for i in sel]
        return (sum(e["puntaje"] for e in es) + BONO_REGION * len({e["region"] for e in es})
                + BONO_TEMA * len({e["tema"] for e in es}))

    def buscar(inicio, sel, suma):
        if len(sel) == N_RUTAS:
            v = valor(sel)
            if v > mejor["valor"]:
                mejor.update(valor=v, sel=list(sel))
            return
        faltan = N_RUTAS - len(sel)
        if suma + sum(cota[:faltan]) + (BONO_REGION + BONO_TEMA) * N_RUTAS <= mejor["valor"]:
            return  # poda: ni con las mejores restantes se supera la mejor combinación
        for i in range(inicio, n):
            e = candidatas[i]
            if not all(compat[i][j] for j in sel):
                continue
            if sum(candidatas[j]["tema"] == e["tema"] for j in sel) >= 2:
                continue
            if sum(candidatas[j]["ruta"][0] == e["ruta"][0] for j in sel) >= MAX_POR_ANCLA:
                continue
            buscar(i + 1, sel + [i], suma + e["puntaje"])

    buscar(0, [], 0.0)
    return [candidatas[i] for i in mejor["sel"]]


def datos(b: base.Base):
    v2 = base.sb._peticion("dim_version_calculo?select=version_sk&nombre=eq.v2_con_prediccion", True, "dw")[0]["version_sk"]
    idx = base.sb.leer("fact_indice_oportunidad", "dw", secreta=True)
    idx = idx[idx.version_sk == v2]
    mejor = idx.loc[idx.groupby("municipio_sk").indice_oportunidad.idxmax()].set_index("municipio_sk")
    flags = base.sb.leer("fact_flag_oportunidad", "dw", secreta=True)
    flags = flags[(flags.version_sk == v2) & flags.flag_activo]
    tipos = {r["tipo_flag_sk"]: r["codigo"] for r in base.sb._peticion("dim_tipo_flag?select=*", True, "dw")}
    flags["codigo"] = flags.tipo_flag_sk.map(tipos)
    pred = base.sb.leer("fact_prediccion_crecimiento", "dw", secreta=True)
    enl = base.sb.leer("fact_prediccion_enlace", "dw", secreta=True)
    t = b.acceso.set_index(["municipio_origen_sk", "municipio_destino_sk"])
    return v2, mejor, flags, pred, enl, t


def main():
    b = base.cargar()
    v2, mejor, flags, pred, enl, acc = datos(b)
    m = b.mun
    tiempo = acc.tiempo_min_est.to_dict()
    dist = acc.distancia_km_recta.to_dict()
    p_enl = {}
    for r in enl.itertuples():
        p_enl[(r.municipio_a_sk, r.municipio_b_sk)] = p_enl[(r.municipio_b_sk, r.municipio_a_sk)] = r.probabilidad
    # Probabilidad de enlace normalizada a percentil (la cruda es muy baja por la tasa base del 1 %)
    pe = pd.Series(p_enl)
    pe_pct = pe.rank(pct=True).to_dict()
    oficiales = set()
    for _, g in b.rutas.sort_values("orden_parada").groupby("ruta_sk"):
        ms = g.municipio_sk.tolist()
        oficiales |= {frozenset(x) for x in zip(ms, ms[1:])}

    social = pct(-b.social.indice_marginacion)
    con_flag = set(flags.municipio_sk)
    motivo_flag = flags.sort_values("tipo_flag_sk").groupby("municipio_sk").codigo.apply(lambda s: sorted(set(s)))
    act = b.actividades.merge(b.cat_act[["actividad_sk", "codigo", "nombre", "icono"]])
    # Tema "presente" solo con presencia fuerte: especialización alta/muy alta o reconocida por la Secretaría
    # (un nivel "media" puede venir de un solo negocio, p. ej. una vinatería para el mezcal)
    fuertes = ["muy_alta", "alta", "reconocida", "reconocida_sin_registro"]
    presente = act[act.nivel_predominancia.isin(fuertes)].groupby("codigo").municipio_sk.apply(set)
    M = enlaces.meses_fuertes(b)
    crec = pred.set_index(["municipio_sk", "eje_sk"]).crecimiento_pred_pct
    anclas = list(m[m.es_ancla].index)

    def valor(mk, tema):
        r = mejor.loc[mk]
        return (r.indice_oportunidad * (1 + 0.35 * (mk in con_flag)) * (1 + 0.40 * social.get(mk, 0))
                * (1 + 0.25 * (mk in presente.get(tema, set()))))

    def recorrido(ruta):
        return sum(tiempo[(a, c)] for a, c in zip(ruta, ruta[1:]))

    def dos_opt(ruta):
        mejor_r, mejor_t = ruta, recorrido(ruta)
        for i, j in itertools.combinations(range(1, len(ruta)), 2):
            cand = ruta[:i] + ruta[i:j + 1][::-1] + ruta[j + 1:]
            if all(tiempo[(a, c)] <= MAX_TRAMO for a, c in zip(cand, cand[1:])) and recorrido(cand) < mejor_t:
                mejor_r, mejor_t = cand, recorrido(cand)
        return mejor_r

    def construir(ancla, tema):
        candidatos = presente.get(tema, set()) - set(anclas)
        ruta = [ancla]
        while len(ruta) < MAX_PARADAS:
            fin, opciones = ruta[-1], []
            for c in candidatos - set(ruta):
                t_ = tiempo.get((fin, c))
                if t_ is None or t_ > MAX_TRAMO or recorrido(ruta) + t_ > MAX_TOTAL:
                    continue
                nuevo = frozenset((fin, c)) not in oficiales
                g = valor(c, tema) * (0.5 + pe_pct.get((fin, c), 0)) * (1 + 0.3 * nuevo) / (1 + t_ / 60)
                opciones.append((g, c))
            if not opciones:
                break
            ruta.append(max(opciones)[1])
        return dos_opt(ruta)

    # Especificidad del tema: un tema presente en pocos municipios (mezcal, café, volcanes) distingue y vende
    # más que uno casi universal (gastronomía tradicional). Factor de ×0.85 (más común) a ×1.15 (más raro).
    n_tema = pd.Series({t: len(presente.get(t, set())) for t in TEMAS})
    especificidad = (0.85 + 0.30 * (1 - (n_tema - n_tema.min()) / max(1, n_tema.max() - n_tema.min()))).to_dict()

    def evaluar(ruta, tema):
        resto = ruta[1:]
        emerg = [x for x in resto if x in con_flag]
        if len(ruta) < MIN_PARADAS or len(emerg) < 2:
            return None
        meses = M.loc[ruta].sum()
        meses_comunes = [int(k) for k, v in meses.items() if v >= max(2, int(np.ceil(len(ruta) * 0.6)))]
        enl_medio = np.mean([pe_pct.get((a, c), 0) for a, c in zip(ruta, ruta[1:])])
        tramos_nuevos = np.mean([frozenset((a, c)) not in oficiales for a, c in zip(ruta, ruta[1:])])
        puntaje = (sum(valor(x, tema) for x in resto) * (0.7 + 0.3 * enl_medio) * (1 + 0.2 * tramos_nuevos)
                   * (1 + 0.1 * bool(meses_comunes)) * especificidad[tema] - 0.15 * recorrido(ruta) / MAX_TOTAL)
        return dict(ruta=ruta, tema=tema, puntaje=puntaje, emergentes=emerg, meses_comunes=meses_comunes,
                    enlace_medio=enl_medio, tramos_nuevos=tramos_nuevos, minutos=recorrido(ruta))

    construidas = {(a, t): construir(a, t) for a in anclas for t in TEMAS}
    candidatas = [e for (a, t), r in construidas.items() if (e := evaluar(r, t))]
    candidatas.sort(key=lambda e: -e["puntaje"])
    # Diagnóstico: todas las combinaciones ancla × tema, factibles o no y por qué
    diag = []
    for (a, t), r in construidas.items():
        e = evaluar(r, t)
        diag.append(dict(ancla=m.nombre[a], tema=t, paradas=len(r), recorrido=" → ".join(m.nombre[x] for x in r),
                         emergentes=sum(x in con_flag for x in r[1:]), factible=e is not None,
                         puntaje=round(e["puntaje"], 3) if e else None,
                         candidatos_tema=len(presente.get(t, set()) - set(anclas)),
                         necesidad_social=round(float(np.mean([social[x] for x in r[1:]])), 2) if len(r) > 1 else None))
    pd.DataFrame(diag).sort_values(["tema", "puntaje"], ascending=[True, False]).to_csv(
        RAIZ / "data" / "derivados" / "rutas_candidatas.csv", index=False)
    # Selección voraz por puntaje AJUSTADO: si la región del ancla o el tema ya tienen ruta, el puntaje se
    # multiplica por PENAL_REGION / PENAL_TEMA (penaliza, no excluye: una ruta mucho mejor sigue entrando).
    # Restricciones duras: anclas distintas, máximo 2 rutas por tema y ≤ 50 % de municipios compartidos.
    # Región de una ruta = región que predomina entre sus paradas (donde llega el beneficio), no la del ancla:
    # p. ej. la ruta del mezcal sale de Puebla (Angelópolis) pero sus paradas están en la Mixteca.
    for e in candidatas:
        e["region"] = m.region.reindex(e["ruta"][1:]).mode().iat[0]
    elegidas = seleccionar(candidatas)
    print(f"Candidatas factibles: {len(candidatas)} (anclas × temas) · elegidas: {len(elegidas)}")

    # --- escritura
    viejas = base.sb._peticion("dim_ruta?select=ruta_sk&origen=eq.propuesta_modelo", True, "dw")
    if viejas:
        ids = ",".join(str(r["ruta_sk"]) for r in viejas)
        for t in ("fact_ruta_evaluacion", "fact_ruta_parada"):
            base.sb._peticion(f"{t}?ruta_sk=in.({ids})", True, "dw", "DELETE")
        base.sb._peticion(f"dim_ruta?ruta_sk=in.({ids})", True, "dw", "DELETE")
    modelo_sk = base.sb._peticion("dim_modelo?select=modelo_sk&nombre=eq.crecimiento_ue_eje_lgbm_v1", True, "dw")[0]["modelo_sk"]
    nom_act = dict(zip(b.cat_act.codigo, b.cat_act.nombre))
    ico_act = dict(zip(b.cat_act.codigo, b.cat_act.icono))
    meses_txt = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"]
    resumen = []
    for i, e in enumerate(elegidas, 1):
        ruta, tema = e["ruta"], e["tema"]
        nombres = [m.nombre[x] for x in ruta]
        estancias = [ESTANCIA[bool(m.es_ancla[x])] for x in ruta]
        horas = round((e["minutos"] / 60) + sum(estancias), 1)
        crec_ruta = [crec.get((x, int(mejor.eje_sk[x])), np.nan) for x in ruta[1:]]
        desc = (f"{ico_act[tema]} Ruta de {nom_act[tema].lower()} que parte de {nombres[0]} (ancla) hacia "
                f"{len(e['emergentes'])} municipios emergentes con bandera de oportunidad: "
                + "; ".join(f"{m.nombre[x]} ({', '.join(motivo_flag.get(x, []))})" for x in e["emergentes"])
                + f". Recorrido {e['minutos']:.0f} min en carretera, {horas} h con estancias. "
                f"Crecimiento esperado medio {np.nanmean(crec_ruta):+.0f} % a 5 años. "
                f"{e['tramos_nuevos']:.0%} de los tramos no existe en rutas oficiales."
                + (f" Temporada compartida: {', '.join(meses_txt[k - 1] for k in e['meses_comunes'])}."
                   if e["meses_comunes"] else ""))
        fila = dict(nombre=f"{nom_act[tema]} · {nombres[0]} → {nombres[-1]} (propuesta {i})",
                    tipo="ruta_intermunicipal", tema=tema, es_monotematica=True, origen="propuesta_modelo",
                    version_sk=v2, num_municipios=len(ruta), duracion_estimada_h=horas, descripcion=desc[:1500])
        sk = base.sb._peticion("dim_ruta", True, "dw", "POST", fila, {"Prefer": "return=representation"})[0]["ruta_sk"]
        paradas = []
        for k, x in enumerate(ruta):
            prev = ruta[k - 1] if k else None
            paradas.append(dict(ruta_sk=sk, orden_parada=k + 1, municipio_sk=int(x), eje_sk=int(mejor.eje_sk[x]),
                                distancia_desde_anterior_km=round(dist[(prev, x)], 2) if prev else None,
                                tiempo_desde_anterior_min=round(tiempo[(prev, x)], 1) if prev else None,
                                es_ancla=bool(m.es_ancla[x]), es_emergente=x in e["emergentes"],
                                estancia_sugerida_h=estancias[k]))
        base.sb._peticion("fact_ruta_parada", True, "dw", "POST", paradas, {"Prefer": "return=minimal"})
        base.sb._peticion("fact_ruta_evaluacion", True, "dw", "POST", dict(
            ruta_sk=sk, modelo_sk=modelo_sk, version_sk=v2, tiempo_total_min=round(e["minutos"], 1),
            potencial_pred_medio_pct=base.limpio(round(float(np.nanmean(crec_ruta)), 2)),
            necesidad_social_media=round(float(np.mean([social[x] for x in ruta[1:]])), 3),
            num_municipios_emergentes=len(e["emergentes"]), puntaje_total=round(float(e["puntaje"]), 4)),
            {"Prefer": "return=minimal"})
        resumen.append((sk, fila["nombre"], " → ".join(nombres), e))
    print(f"✓ dim_ruta / fact_ruta_parada / fact_ruta_evaluacion: {len(resumen)} rutas propuestas")

    nov = base.sb.leer("v_novedad_ruta", "dw", secreta=True).set_index("ruta_sk")
    for sk, nombre, recorrido_txt, e in resumen:
        n = nov.loc[sk]
        print(f"  #{sk} {nombre}\n      {recorrido_txt} · {e['minutos']:.0f} min · emergentes {len(e['emergentes'])} · "
              f"enlace P{e['enlace_medio']:.0%} · novedad: {n.clasificacion_novedad} "
              f"({n.pct_tramos_existentes:.0f} % tramos existentes)")
    pd.DataFrame([dict(ruta_sk=sk, nombre=n_, recorrido=r_, puntaje=e["puntaje"], minutos=e["minutos"],
                       novedad=nov.loc[sk].clasificacion_novedad) for sk, n_, r_, e in resumen]).to_csv(
        RAIZ / "data" / "derivados" / "rutas_propuestas.csv", index=False)


if __name__ == "__main__":
    main()
