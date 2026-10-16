"""🧭 Rutas del modelo: las 5 rutas propuestas por el optimizador (model/rutas.py) y las descartadas, leídas de
Supabase (dw.v_ruta_parada) con su trazo por carretera guardado (sin servicios en vivo)."""
import html

import pandas as pd
import streamlit as st

import bd
import ficha_bd as fb
import mapas
import navegacion
import tema

COLORES_RUTA = ["#1B3F8B", "#8A1538", "#E8B10D", "#2E7D32", "#00897B", "#D81B60", "#546E7A", "#6D4C41"]
NOVEDAD = {"nueva": ("Nueva", "#2E7D32"), "parcialmente_existente": ("Parcialmente existente", "#E8B10D"),
           "existente": ("Ya existe", "#8A1538")}
INCUMPLIMIENTO = {"region_angelopolis": "su beneficio se queda en Angelópolis (la región de la capital)",
                  "sin_pernocta": "dura más de un día y ninguna parada tiene ≥ 10 hospedajes",
                  "infra_rojo": "pasa por un municipio con infraestructura en rojo",
                  "parada_sin_punto_de_visita": "tiene una parada sin ningún punto visitable",
                  "tramo>75": "algún tramo pasa de 75 min de planeación", "total>240": "el recorrido pasa de 240 min"}


def _legible(texto: str) -> str:
    for codigo, nombre in fb.BANDERA.items():
        texto = texto.replace(codigo, nombre.lower())
    return texto


def _icono(codigo: str) -> str:
    act = bd.actividades().set_index("codigo").icono
    return act.get(codigo, "🧭")


def render():
    modo = st.segmented_control("Rutas", ["🧠 Rutas del modelo", "🛠️ Arma tu ruta"], default="🧠 Rutas del modelo",
                                key="rutas_modo", label_visibility="collapsed") or "🧠 Rutas del modelo"
    if modo == "🛠️ Arma tu ruta":
        _armar()
        return
    try:
        paradas, idx = bd.rutas(), bd.indice_municipio()
    except bd.SinDatos as e:
        st.error(f"No se pudieron leer las rutas: {e}")
        return
    prop = paradas[paradas.origen == "propuesta_modelo"]
    desc = paradas[paradas.origen == "propuesta_descartada"]
    ofic = paradas[paradas.origen == "existente"]
    rutas = prop.drop_duplicates("ruta_sk").reset_index(drop=True)
    params = bd.vigente()["parametros_rutas"]

    tema.hero("🧭 Rutas turísticas propuestas por el modelo",
              "Cada ruta parte de un destino ancla (⚓) y lleva al visitante a municipios emergentes con bandera de "
              "oportunidad y algo que visitar. Tiempos por carretera con margen de planeación, pernocta donde hay "
              "hospedaje y riesgo conocido.",
              [f"{len(rutas)} rutas propuestas", f"comparadas con {ofic.ruta_sk.nunique()} rutas oficiales",
               f"tramo ≤ {params['max_tramo_min']} min · recorrido ≤ {params['max_total_min']} min de planeación",
               f"pernocta con ≥ {params['min_hospedaje_pernocta']} hospedajes"])
    if rutas.empty:
        st.info("Todavía no hay rutas propuestas. Corre `python scripts/pipeline.py`.")
        return

    esc = bd.escenarios()
    k = st.columns(5)
    k[0].metric("Rutas propuestas", len(rutas), f"{(rutas.clasificacion_novedad == 'nueva').sum()} totalmente nuevas",
                delta_color="off")
    k[1].metric("Municipios emergentes", prop[prop.es_emergente].municipio_sk.nunique(), "con bandera de oportunidad",
                delta_color="off")
    k[2].metric("Regiones beneficiadas", rutas.region_beneficiada.nunique(), "sin Angelópolis", delta_color="off")
    k[3].metric("Cumplen todas las reglas", f"{int(rutas.cumple_restricciones.sum())}/{len(rutas)}")
    k[4].metric("Concentración top 5", f"{esc.pct_top5['con_rutas_hipotetico']:.1f} %",
                f"{esc.pct_top5['con_rutas_hipotetico'] - esc.pct_top5['hoy']:+.1f} pp vs hoy (hipotético)",
                delta_color="inverse", help=esc.supuesto["con_rutas_hipotetico"])

    nombres = {r.ruta_sk: f"{_icono(r.tema)} {r.ruta}" for r in rutas.itertuples()}
    color = {sk: COLORES_RUTA[i % len(COLORES_RUTA)] for i, sk in enumerate(rutas.ruta_sk)}
    trazos = bd.trazos()
    c1, c2 = st.columns([3, 1])
    por_nombre = {v: k for k, v in nombres.items()}
    vistas = c1.multiselect("Rutas a mostrar en el mapa", list(por_nombre), default=list(por_nombre),
                            key="rt_sel") or list(por_nombre)
    elegidas = [por_nombre[v] for v in vistas]
    ver_oficiales = c2.toggle("Ver rutas oficiales", value=False, key="rt_ofic")

    mapa, lista = st.columns([1.55, 1])
    with mapa:
        tt = idx.set_index("cve_geo").apply(
            lambda r: f"<b>{r.nombre}</b><br>Índice de oportunidad {r.indice_oportunidad:.2f} "
                      f"(#{r.ranking_estatal})<br>Mejor eje: {str(r.eje_lider).replace('_', ' ')}", axis=1)
        m = mapas.Mapa(bd.geo(), alto=640, fondo=bd.fondo_mapa()).municipios(
            idx, "indice_oportunidad", tt, paleta=tema.SEQ_TALAVERA[:3], cuantiles=True)
        if ver_oficiales:
            for _, g in ofic.groupby("ruta_sk"):
                if len(g) > 1:
                    m.trayecto(g.lon, g.lat, "rgba(90,90,90,0.55)", 1.6, f"<b>{g.ruta.iat[0]}</b><br>Ruta oficial")
        sel = prop[prop.ruta_sk.isin(elegidas)]
        for sk, g in sel.groupby("ruta_sk"):
            tr = trazos.get(int(sk))
            lon, lat = (zip(*tr["geom"]["coordinates"]) if tr else (g.lon, g.lat))
            m.trayecto(list(lon), list(lat), color[sk], 4.5,
                       f"<b>{nombres[sk]}</b><br>{len(g)} paradas · {g.tiempo_total_min.iat[0]:.0f} min por carretera")
        pts = sel.copy()
        pts["color"] = [tema.COBALTO_OSC if a else color[sk] for a, sk in zip(pts.es_ancla, pts.ruta_sk)]
        pts["num"] = pts.orden_parada.astype(str)
        pts["tt"] = [f"<b>{r.orden_parada}. {r.municipio}</b>{' ⚓' if r.es_ancla else ''}"
                     f"{' 🛏️' if r.es_pernocta else ''}<br>{nombres[r.ruta_sk]}<br>"
                     + ("Destino ancla" if r.es_ancla else ("🚩 Emergente con bandera" if r.es_emergente else "Parada"))
                     + (f"<br>🚗 {r.tiempo_desde_anterior_min:.0f} min desde la anterior" if r.orden_parada > 1 else "")
                     for r in pts.itertuples()]
        m.puntos(pts, "color", 20, "tt", texto="num", posicion_texto="middle center", color_texto="white",
                 tamano_texto=11)
        if len(elegidas) <= 2:
            m.nombres(sel.drop_duplicates("municipio_sk"), columna="municipio", tamano=10, separacion=0.06)
        if len(sel):
            m.encuadre(sel.lat, sel.lon, margen=0.12, aspecto=1.15)
        mapas.mostrar(m, "rt_mapa")
        st.caption("Fondo: índice de oportunidad (más oscuro = mayor). Líneas = trazo por carretera guardado. "
                   "Números = orden de las paradas; azul oscuro = ancla; 🛏️ = pernocta.")

    with lista:
        for i, r in enumerate(rutas.itertuples()):
            g = prop[prop.ruta_sk == r.ruta_sk]
            nov, col_nov = NOVEDAD.get(r.clasificacion_novedad, (r.clasificacion_novedad, "#546E7A"))
            with st.expander(nombres[r.ruta_sk], expanded=i == 0):
                st.markdown(f"<span class='mope-tag' style='background:{col_nov};color:white'>{nov}</span> "
                            f"<small>{r.pct_tramos_existentes:.0f} % de tramos en rutas oficiales · beneficia a "
                            f"<b>{r.region_beneficiada}</b></small>", unsafe_allow_html=True)
                a, b, c = st.columns(3)
                a.metric("Días", int(r.dias_sugeridos), f"{r.duracion_estimada_h:.0f} h con estancias", delta_color="off")
                b.metric("Carretera", f"{r.tiempo_total_min / 60:.1f} h",
                         f"{float(r.tiempo_total_min_planeacion) / 60:.1f} h de planeación", delta_color="off",
                         help="Flujo libre (OSRM, sin tráfico) y con el margen de planeación por región que usan las reglas.")
                c.metric("Emergentes", int(r.num_municipios_emergentes))
                for p in g.itertuples():
                    etiqueta = ('<span class="mope-tag ancla">ANCLA</span>' if p.es_ancla else
                                '<span class="mope-tag flag">EMERGENTE</span>' if p.es_emergente else "")
                    cama = f" 🛏️ pernocta ({int(p.unidades_hospedaje)} hospedajes)" if p.es_pernocta else ""
                    viaje = f" · 🚗 {p.tiempo_desde_anterior_min:.0f} min" if p.orden_parada > 1 else ""
                    st.markdown(f"<span style='color:{color[r.ruta_sk]};font-weight:800'>{p.orden_parada}.</span> "
                                f"**{p.municipio}** {etiqueta}{cama}<br><small style='opacity:.7'>{p.region}{viaje} · "
                                f"estancia {p.estancia_sugerida_h:.0f} h</small>", unsafe_allow_html=True)
                    if not p.es_ancla:
                        _puntos_visitables(int(p.municipio_sk))
                if r.riesgo_seguridad:
                    st.caption("🛡️ " + r.riesgo_seguridad)
                st.caption(html.escape(_legible(r.descripcion or "")))

    st.markdown("#### 📊 Comparar rutas propuestas")
    tabla = pd.DataFrame([{
        "Ruta": nombres[r.ruta_sk], "Novedad": NOVEDAD.get(r.clasificacion_novedad, (r.clasificacion_novedad,))[0],
        "Región beneficiada": r.region_beneficiada, "Días": r.dias_sugeridos,
        "Carretera (h)": round(r.tiempo_total_min / 60, 1),
        "Planeación (h)": round(float(r.tiempo_total_min_planeacion) / 60, 1),
        "Pernocta": ", ".join(prop[(prop.ruta_sk == r.ruta_sk) & prop.es_pernocta].municipio) or "—",
        "Emergentes": r.num_municipios_emergentes, "Crecimiento esperado (%)": r.potencial_pred_medio_pct,
        "Necesidad social": r.necesidad_social_media, "Riesgo": r.riesgo_seguridad,
        "Recorrido": " → ".join(prop[prop.ruta_sk == r.ruta_sk].municipio),
    } for r in rutas.itertuples()])
    st.dataframe(tabla, hide_index=True, width="stretch", column_config={
        "Necesidad social": st.column_config.ProgressColumn(min_value=0, max_value=1, format="%.2f"),
        "Crecimiento esperado (%)": st.column_config.NumberColumn(format="%+.0f %%")})
    st.download_button("⬇️ Descargar rutas propuestas (CSV)", tabla.to_csv(index=False).encode("utf-8-sig"),
                       "rutas_propuestas_mopedetu.csv", "text/csv")

    _recorrer(prop, nombres, color, trazos)

    if len(desc):
        with st.expander(f"🚫 Rutas descartadas ({desc.ruta_sk.nunique()}) y por qué"):
            for sk, g in desc.groupby("ruta_sk"):
                motivos = [INCUMPLIMIENTO.get(m, m) for m in (g.incumplimientos.iat[0] or [])]
                st.markdown(f"**{g.ruta.iat[0]}** · {' → '.join(g.municipio)}  \nSe descartó porque "
                            + "; ".join(motivos) + ".")
            st.caption("El optimizador la habría elegido sin las reglas de operación; se guarda para explicar por "
                       "qué se eligieron otras.")
    with st.expander(f"📚 Rutas oficiales del catálogo de la Secretaría ({ofic.ruta_sk.nunique()})"):
        of = ofic.groupby("ruta_sk").agg(Ruta=("ruta", "first"), Tema=("tema", "first"),
                                         Recorrido=("municipio", " → ".join)).reset_index(drop=True)
        st.dataframe(of, hide_index=True, width="stretch")
    st.caption("Las rutas propuestas son hipótesis de trabajo generadas con datos de oferta (DENUE, Censos "
               "Económicos), no de visitantes; el siguiente paso es validarlas con las comunidades.")


def _puntos_visitables(municipio_sk: int):
    lug = bd.lugares(municipio_sk)
    lug = lug[lug.tipo_parada.isin(["atractivo", "experiencia"])].head(3)
    if len(lug):
        st.markdown("<small style='opacity:.8;margin-left:18px'>📍 " + " · ".join(
            html.escape(n) + (" ✅" if o == "curado" else "") for n, o in zip(lug.nombre, lug.origen))
            + "</small>", unsafe_allow_html=True)


def agenda(paradas: list, traslados: list[float]) -> list[tuple[int, float]]:
    """(día, minuto de llegada) por parada: jornadas de 9:00 a 19:00; el día termina en la parada de pernocta."""
    dia, reloj, out = 1, 9 * 60, []
    for k, p in enumerate(paradas):
        estancia = 60 * float(p.estancia_sugerida_h or 2)
        llegada = reloj + traslados[k]
        if k and (llegada + estancia > 19 * 60 or paradas[k - 1].es_pernocta):
            dia, llegada = dia + 1, 9 * 60 + traslados[k]
        out.append((dia, llegada))
        reloj = llegada + estancia
    return out


def _recorrer(prop: pd.DataFrame, nombres: dict, color: dict, trazos: dict):
    """Recorrido de una ruta del modelo con su trazo guardado, agenda por días e itinerario descargable."""
    st.markdown("#### 🛰️ Recorrer una ruta propuesta")
    sk = st.selectbox("Ruta", list(nombres), format_func=nombres.get, key="rt_recorrer",
                      label_visibility="collapsed")
    g = prop[prop.ruta_sk == sk].sort_values("orden_parada")
    filas = list(g.itertuples())
    puntos = tuple((float(r.lat), float(r.lon)) for r in filas)
    kms = g.distancia_desde_anterior_km.astype(float).tolist()[1:]
    mins = g.tiempo_desde_anterior_min.astype(float).tolist()[1:]
    tr = trazos.get(int(sk))
    r = navegacion.ruta_guardada(tr["geom"], puntos, kms, mins) if tr else navegacion.ruta_recta(puntos, mins)
    traslados = [0.0] + mins
    ag = agenda(filas, traslados)
    hora = lambda m: f"{int(m // 60):02d}:{int(m % 60):02d}"  # noqa: E731

    rgb = tema.hex_rgb(color[sk])
    paradas = [dict(lon=float(p.lon), lat=float(p.lat), nombre=p.municipio,
                    icono="🛏️" if p.es_pernocta else ("⚓" if p.es_ancla else "📍"),
                    actividad="Destino ancla" if p.es_ancla else ("Emergente con bandera" if p.es_emergente else "Parada"),
                    detalle=f"{p.region} · estancia {p.estancia_sugerida_h:.0f} h",
                    color=tema.hex_rgb(tema.COBALTO_OSC) if p.es_ancla else rgb, orden=i,
                    hora=f"día {ag[i][0]}, {hora(ag[i][1])}")
              for i, p in enumerate(filas) if i]
    limites = [f["geometry"] for f in bd.geo()["features"] if f["properties"]["cve_geo"] in set(g.cve_geo)]
    itinerario = pd.DataFrame({
        "Día": [a[0] for a in ag], "Llegada": [hora(a[1]) for a in ag],
        "Municipio": [("⚓ " if p.es_ancla else "") + p.municipio + (" 🛏️" if p.es_pernocta else "") for p in filas],
        "Traslado": ["salida"] + [f"{m:.0f} min · {k:.0f} km" for m, k in zip(mins, kms)],
        "Estancia (h)": [p.estancia_sugerida_h for p in filas]})
    izq, der = st.columns([1.7, 1])
    with izq:
        p0 = filas[0]
        navegacion.mapa(dict(lon=float(p0.lon), lat=float(p0.lat), nombre=p0.municipio,
                             detalle=f"Salida: día 1, 09:00 · {p0.region}"), paradas, r, limites, "auto", alto=560)
        st.caption("**▶ Recorrer** sigue el trazo guardado · 🛰️/🗺️ cambia entre satélite y calles.")
    with der:
        k = st.columns(2)
        k[0].metric("Por carretera", f"{r['km']:,.0f} km")
        k[1].metric("Manejo", f"{r['min'] / 60:.1f} h", f"{ag[-1][0]} día(s)", delta_color="off")
        st.dataframe(itinerario, hide_index=True, width="stretch")
        st.download_button("⬇️ Itinerario (CSV)", itinerario.to_csv(index=False).encode("utf-8-sig"),
                           f"itinerario_ruta_{sk}.csv", "text/csv", width="stretch")
        st.link_button("🗺️ Abrir en Google Maps", navegacion.enlace_google(puntos, "auto"), width="stretch")
    fuente = (f"Trazo por carretera guardado ({tr['fuente']})" if tr
              else "Sin trazo guardado: tramos rectos con los tiempos de la base")
    st.caption(f"{fuente}. Tiempos de flujo libre (sin tráfico); las reglas usan el tiempo de planeación.")


# ---------------------------------------------------------------- 🛠️ Arma tu ruta (mismas reglas que el modelo)
REGLAS_TEXTO = {
    "pocas_paradas": "menos de {min_paradas} paradas", "muchas_paradas": "más de {max_paradas} paradas",
    "pocos_emergentes": "menos de {min_emergentes} municipios emergentes (con bandera distinta de barrera de acceso)",
    "sin_pernocta": "dura más de un día y ninguna parada tiene ≥ {min_hospedaje_pernocta} hospedajes",
    "region_angelopolis": "el beneficio se queda en Angelópolis", "infra_rojo": "pasa por infraestructura en rojo",
    "parada_sin_punto_de_visita": "alguna parada no tiene ningún punto visitable",
    "sin_candidatos_tema": "no hay municipios con ese tema, punto visitable e infraestructura suficiente",
}
QUE_CAMBIAR = {
    "pocos_emergentes": "prueba otro tema o «sin tema», o baja el mínimo de emergentes",
    "sin_pernocta": "acorta la ruta (menos paradas) o incluye un municipio con más hospedaje",
    "sin_candidatos_tema": "elige «sin tema» u otro tema", "pocas_paradas": "elige otro tema o sal de otro municipio",
    "infra_rojo": "quita la parada marcada en rojo", "parada_sin_punto_de_visita": "cambia esa parada por otra",
}


def _texto_regla(codigo: str, p: dict) -> str:
    if codigo.startswith("tramo>"):
        return f"algún tramo pasa de {p['max_tramo_min']} min de planeación"
    if codigo.startswith("total>"):
        return f"el recorrido pasa de {p['max_total_min']} min de planeación"
    return REGLAS_TEXTO.get(codigo, codigo).format(**p)


def _armar():
    import dataclasses

    import reglas_rutas as rr

    tema.hero("🛠️ Arma tu ruta", "Sal de cualquier municipio: el motor aplica exactamente las mismas reglas que las "
              "rutas del modelo (tiempos de planeación, emergentes, pernocta, puntos visitables).", [])
    try:
        ins = bd.insumos()
    except bd.SinDatos as e:
        st.error(f"«Arma tu ruta» necesita conexión a la base: {e}.")
        return
    p = ins.parametros
    mun = ins.mun.sort_values("nombre")
    etiqueta = lambda k: ("⚓ " if mun.es_ancla[k] else "") + mun.nombre[k]  # noqa: E731
    act = bd.actividades().set_index("codigo")
    temas = ["(sin tema)"] + [t for t in rr.TEMAS if ins.presente.get(t)]
    with st.container(border=True):
        c = st.columns([1.3, 1.1, 1.3, 1.9, 0.9])
        capital = mun.index[mun.nombre == "Puebla"]
        inicio = c[0].selectbox("🚩 Salida", list(mun.index), format_func=etiqueta, key="ar_inicio",
                                index=list(mun.index).index(capital[0]) if len(capital) else 0)
        forma = c[1].segmented_control("Paradas", ["Automáticas", "Yo elijo"], default="Automáticas",
                                       key="ar_forma") or "Automáticas"
        tema_sel = c[2].selectbox("Tema", temas, key="ar_tema",
                                  format_func=lambda t: t if t.startswith("(") else
                                  f"{act.icono.get(t, '')} {act.nombre.get(t, t)}")
        destinos = c[3].multiselect("Municipios a visitar (el orden se optimiza)",
                                    [k for k in mun.index if k != inicio], format_func=etiqueta,
                                    max_selections=p["max_paradas_usuario"], key="ar_destinos",
                                    disabled=forma != "Yo elijo", placeholder="Escribe para buscar…")
        min_em = c[4].number_input("Mín. emergentes", 0, 5, int(p["min_emergentes"]), key="ar_min_em")
    tema_cod = None if tema_sel.startswith("(") else tema_sel
    if forma == "Yo elijo" and not destinos:
        st.info("Elige al menos un municipio a visitar. Puedes escribir su nombre para buscarlo.")
        return
    if forma == "Yo elijo" and len(destinos) + 1 > p["max_paradas"]:
        st.warning(f"Elegiste {len(destinos) + 1} paradas: las rutas del modelo usan máximo {p['max_paradas']}.")
    ins_u = dataclasses.replace(ins, parametros={**p, "min_emergentes": int(min_em),
                                                "max_paradas": max(p["max_paradas"], len(destinos) + 1)})
    e = rr.construir_ruta(ins_u, int(inicio), tema_cod,
                          [int(d) for d in destinos] if forma == "Yo elijo" else None, exigir_ancla=False)
    # Región beneficiada en Angelópolis: aviso, no bloquea (§4.2)
    bloquean = [i for i in e["incumplimientos"] if i != "region_angelopolis"]

    if e.get("aviso_inicio"):
        st.caption(f"ℹ️ {mun.nombre[inicio]} no es un destino ancla: las rutas del modelo salen de un ancla.")
    if len(e["ruta"]) < 2:
        st.error("No hay ruta: " + "; ".join(_texto_regla(i, ins_u.parametros) for i in e["incumplimientos"]) + ".")
        consejos = [QUE_CAMBIAR[i] for i in e["incumplimientos"] if i in QUE_CAMBIAR]
        if consejos:
            st.info("Qué cambiar: " + "; ".join(dict.fromkeys(consejos)) + ".")
        return

    ruta = e["ruta"]
    pu = ins_u.parametros
    reglas = [
        (f"{pu['min_paradas']}-{pu['max_paradas']} paradas", not ({"pocas_paradas", "muchas_paradas"} & set(bloquean))),
        (f"tramo ≤ {pu['max_tramo_min']} min", not any(i.startswith("tramo>") for i in bloquean)),
        (f"recorrido ≤ {pu['max_total_min']} min", not any(i.startswith("total>") for i in bloquean)),
        (f"≥ {int(min_em)} emergentes", "pocos_emergentes" not in bloquean),
        (f"pernocta con ≥ {pu['min_hospedaje_pernocta']} hospedajes", "sin_pernocta" not in bloquean),
        ("sin infraestructura en rojo", "infra_rojo" not in bloquean),
        ("todas las paradas con algo que visitar", "parada_sin_punto_de_visita" not in bloquean),
    ]
    k = st.columns(5)
    k[0].metric("Municipios", len(ruta), f"{len(e['emergentes'])} emergentes", delta_color="off")
    k[1].metric("Carretera", f"{e['minutos'] / 60:.1f} h", f"{e['minutos_plan'] / 60:.1f} h de planeación",
                delta_color="off")
    k[2].metric("Duración", f"{e['dias']} día(s)", f"{e['horas']:.0f} h con estancias", delta_color="off")
    k[3].metric("Pernocta", mun.nombre[e["pernocta"]] if e["pernocta"] else "—")
    k[4].metric("Región beneficiada", e["region"])
    st.markdown(" · ".join(f"{'✅' if ok else '⚠️'} {t}" for t, ok in reglas)
                + ("  \n⚠️ Aviso: el beneficio se queda en Angelópolis."
                   if "region_angelopolis" in e["incumplimientos"] else ""))
    if bloquean:
        consejos = [QUE_CAMBIAR[i] for i in bloquean if i in QUE_CAMBIAR]
        st.warning("Esta ruta no cumple: " + "; ".join(_texto_regla(i, pu) for i in bloquean) + "."
                   + (f" Qué cambiar: {'; '.join(dict.fromkeys(consejos))}." if consejos else ""))

    filas = [dict(orden=i + 1, municipio_sk=x, municipio=mun.nombre[x], region=mun.region[x],
                  es_ancla=bool(mun.es_ancla[x]), es_emergente=x in e["emergentes"], es_pernocta=x == e["pernocta"],
                  estancia_sugerida_h=e["estancias"][i], lat=float(mun.cabecera_lat[x]),
                  lon=float(mun.cabecera_lon[x])) for i, x in enumerate(ruta)]
    puntos = tuple((f["lat"], f["lon"]) for f in filas)
    mins = [ins.tiempo[(a, b)] for a, b in zip(ruta, ruta[1:])]
    r = navegacion.ruta(puntos, "auto") or navegacion.ruta_recta(puntos, mins)  # respaldo: tiempos de la base
    traslados = [0.0] + [t["min"] for t in r["tramos"]]
    g = pd.DataFrame(filas)
    ag = agenda(list(g.itertuples()), traslados)
    hora = lambda m: f"{int(m // 60):02d}:{int(m % 60):02d}"  # noqa: E731
    izq, der = st.columns([1.7, 1])
    with izq:
        paradas = [dict(lon=f["lon"], lat=f["lat"], nombre=f["municipio"],
                        icono="🛏️" if f["es_pernocta"] else ("⚓" if f["es_ancla"] else "📍"),
                        actividad="Destino ancla" if f["es_ancla"] else ("Emergente" if f["es_emergente"] else "Parada"),
                        detalle=f"{f['region']} · estancia {f['estancia_sugerida_h']:.0f} h",
                        color=tema.hex_rgb(tema.COBALTO_OSC if f["es_ancla"] else tema.GUINDA), orden=i,
                        hora=f"día {ag[i][0]}, {hora(ag[i][1])}") for i, f in enumerate(filas) if i]
        limites = [ft["geometry"] for ft in bd.geo()["features"]
                   if ft["properties"]["cve_geo"] in set(mun.cve_geo[ruta])]
        navegacion.mapa(dict(lon=filas[0]["lon"], lat=filas[0]["lat"], nombre=filas[0]["municipio"],
                             detalle=f"Salida: día 1, 09:00 · {filas[0]['region']}"), paradas, r, limites, "auto",
                        alto=600)
    with der:
        itinerario = pd.DataFrame({
            "Día": [a[0] for a in ag], "Llegada": [hora(a[1]) for a in ag],
            "Municipio": [("⚓ " if f["es_ancla"] else "") + f["municipio"] + (" 🛏️" if f["es_pernocta"] else "")
                          + (" 🚩" if f["es_emergente"] else "") for f in filas],
            "Traslado": ["salida"] + [f"{t['min']:.0f} min · {t['km']:.0f} km" for t in r["tramos"]]})
        st.dataframe(itinerario, hide_index=True, width="stretch")
        st.download_button("⬇️ Itinerario (CSV)", itinerario.to_csv(index=False).encode("utf-8-sig"),
                           "mi_ruta_mopedetu.csv", "text/csv", width="stretch")
        st.link_button("🗺️ Abrir en Google Maps", navegacion.enlace_google(puntos, "auto"), width="stretch")
        for f in filas[1:]:
            st.markdown(f"**{f['municipio']}**")
            _puntos_visitables(int(f["municipio_sk"]))
    st.caption(("Trazo y tiempos por carretera en vivo (OSRM)" if r["real"]
                else "Sin servicio de rutas en vivo: tramos rectos con los tiempos por carretera de la base")
               + ". Las reglas se evalúan con el tiempo de planeación.")
