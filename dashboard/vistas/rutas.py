import html
import json
from pathlib import Path

import pandas as pd
import streamlit as st

import estado
import ficha_bd as fb
import mapas
import motor
import navegacion
import tema

COLORES_RUTA = ["#1B3F8B", "#8A1538", "#E8B10D", "#2E7D32", "#00897B", "#D81B60", "#546E7A", "#6D4C41"]
ICONO_TEMA = {"cafe": "☕", "mezcal": "🥃", "gastronomia": "🍲", "comunitario": "🤝", "volcanes": "🌋",
              "ecoturismo": "🌲", "artesanias": "🏺", "bebidas_tradicionales": "🍷", "religioso": "⛪",
              "balnearios": "♨️", "flores_viveros": "🌸", "museos": "🏛️", "arqueologia": "🗿",
              "pueblos_magicos": "✨", "senderismo": "🥾", "conventos": "⛪", "naturaleza": "🌵"}
NOVEDAD = {"nueva": ("Nueva", "#2E7D32"), "parcialmente_existente": ("Parcialmente existente", "#E8B10D"),
           "existente": ("Ya existe", "#8A1538")}
ESCENARIO = Path(__file__).resolve().parents[2] / "data" / "derivados" / "escenario_concentracion.json"
BANDERAS = {"OFERTA_EMERGENTE": "oferta emergente", "ACCESIBLE_NO_EXPLOTADO": "accesible no explotado",
            "BARRERA_ACCESO": "barrera de acceso", "OFERTA_INVISIBLE": "oferta invisible",
            "OFERTA_SIN_REGISTRO": "oferta sin registro",
            "IMPACTO_SOCIAL": "impacto social"}


def _legible(texto: str) -> str:
    for codigo, nombre in BANDERAS.items():
        texto = texto.replace(codigo, nombre)
    return texto


def render():
    # Dos modos: las rutas que propone el modelo (Supabase) y la ruta a la medida desde cualquier municipio
    modo = st.segmented_control("Rutas", ["🧠 Rutas del modelo", "🛠️ Arma tu ruta"], default="🧠 Rutas del modelo",
                                key="rutas_modo", label_visibility="collapsed") or "🧠 Rutas del modelo"
    if modo == "🛠️ Arma tu ruta":
        d = estado.datos()
        tema.hero("🛠️ Arma tu ruta", "Sal de cualquier municipio y deja que el motor proponga las paradas, o elígelas "
                  "tú; el recorrido se traza por carretera real.", estado.chips())
        _armar(d, d.actividades.set_index("clave"))
        return

    paradas, idx = fb.rutas(), fb.indice()
    if paradas is None or idx is None:
        st.error("No se pudieron leer las rutas de Supabase (`dw.v_ruta_parada`). Revisa el `.env`.")
        return
    prop = paradas[paradas.origen == "propuesta_modelo"]
    ofic = paradas[paradas.origen == "existente"]
    rutas = prop.drop_duplicates("ruta_sk").reset_index(drop=True)

    tema.hero("🧭 Rutas turísticas propuestas por el modelo",
              "Cada ruta parte de un destino ancla (⚓) y lleva al visitante a municipios emergentes con bandera de "
              "oportunidad. Se arman con el índice de oportunidad, el crecimiento predicho y el modelo de enlaces, "
              "y se comparan contra las rutas oficiales.",
              [f"{len(rutas)} rutas propuestas", f"comparadas con {ofic.ruta_sk.nunique()} rutas oficiales",
               f"{rutas.duracion_estimada_h.max() // 8 + 1:.0f} días máx. con estancias"])
    if rutas.empty:
        st.info("Todavía no hay rutas propuestas. Corre `python model/rutas.py`.")
        return

    k = st.columns(5)
    k[0].metric("Rutas propuestas", len(rutas), f"{(rutas.clasificacion_novedad == 'nueva').sum()} totalmente nuevas",
                delta_color="off")
    k[1].metric("Municipios emergentes", prop[prop.es_emergente].municipio_sk.nunique(), "con bandera de oportunidad",
                delta_color="off")
    k[2].metric("Tramos nuevos", f"{100 - rutas.pct_tramos_existentes.mean():.0f} %",
                help="Porcentaje de tramos que no aparecen en ninguna de las rutas oficiales.")
    k[3].metric("Crecimiento esperado", f"{rutas.potencial_pred_medio_pct.mean():+.0f} %",
                "oferta turística a 5 años", delta_color="off",
                help="Promedio del crecimiento predicho de la oferta en las paradas emergentes.")
    try:
        esc = json.loads(ESCENARIO.read_text(encoding="utf-8"))
        k[4].metric("Concentración top 5", f"{esc['con_rutas_hipotetico']['pct_top5']:.1f} %",
                    f"{esc['con_rutas_hipotetico']['pct_top5'] - esc['hoy']['pct_top5']:+.1f} pp vs hoy",
                    delta_color="inverse", help=esc["supuesto"])
    except Exception:
        k[4].metric("Regiones", rutas.region.nunique())

    c1, c2 = st.columns([3, 1])
    nombres = {r.ruta_sk: f"{ICONO_TEMA.get(r.tema, '🧭')} {r.ruta}" for r in rutas.itertuples()}
    por_nombre = {v: k for k, v in nombres.items()}
    vistas = c1.multiselect("Rutas a mostrar en el mapa", list(por_nombre), default=list(por_nombre),
                            key="rt_sel") or list(por_nombre)
    elegidas = [por_nombre[v] for v in vistas]
    ver_oficiales = c2.toggle("Ver rutas oficiales", value=False, key="rt_ofic",
                              help="Dibuja en gris las rutas del catálogo de la Secretaría de Turismo.")
    color = {sk: COLORES_RUTA[i % len(COLORES_RUTA)] for i, sk in enumerate(rutas.ruta_sk)}

    mapa, lista = st.columns([1.55, 1])
    with mapa:
        geo = estado.datos().geo
        tt = idx.set_index("cve_geo").apply(
            lambda r: f"<b>{r.nombre}</b><br>Índice de oportunidad {r.indice_oportunidad:.2f} "
                      f"(#{r.ranking_estatal})<br>Mejor eje: {str(r.eje_lider).replace('_', ' ')}", axis=1)
        m = mapas.Mapa(geo, alto=640, fondo=mapas.FONDO_ESTADO).municipios(
            idx, "indice_oportunidad", tt, paleta=tema.SEQ_TALAVERA[:3], cuantiles=True)
        if ver_oficiales:
            for _, g in ofic.groupby("ruta_sk"):
                if len(g) > 1:
                    m.trayecto(g.lon, g.lat, "rgba(90,90,90,0.55)", 1.6, f"<b>{g.ruta.iat[0]}</b><br>Ruta oficial")
        sel = prop[prop.ruta_sk.isin(elegidas)]
        for sk, g in sel.groupby("ruta_sk"):
            m.trayecto(g.lon, g.lat, color[sk], 4.5, f"<b>{nombres[sk]}</b><br>{len(g)} paradas · "
                                                     f"{g.tiempo_total_min.iat[0]:.0f} min de traslado")
        pts = sel.copy()
        pts["color"] = [tema.COBALTO_OSC if a else color[sk] for a, sk in zip(pts.es_ancla, pts.ruta_sk)]
        pts["num"] = pts.orden_parada.astype(str)
        pts["tt"] = [f"<b>{r.orden_parada}. {r.municipio}</b>{' ⚓' if r.es_ancla else ''}<br>{nombres[r.ruta_sk]}<br>"
                     + ("Destino ancla" if r.es_ancla else ("🚩 Emergente con bandera" if r.es_emergente else "Parada"))
                     + (f"<br>🚗 {r.tiempo_desde_anterior_min:.0f} min desde la anterior" if r.orden_parada > 1 else "")
                     for r in pts.itertuples()]
        m.puntos(pts, "color", 20, "tt", texto="num", posicion_texto="middle center", color_texto="white",
                 tamano_texto=11)
        if len(elegidas) <= 2:  # con todas las rutas a la vez, los nombres se enciman: bastan números y hover
            m.nombres(sel.drop_duplicates("municipio_sk"), columna="municipio", tamano=10, separacion=0.06)
        if len(sel):
            m.encuadre(sel.lat, sel.lon, margen=0.12, aspecto=1.15)
        mapas.mostrar(m, "rt_mapa")
        st.caption("Fondo: índice de oportunidad (más oscuro = mayor). Números = orden de las paradas; "
                   "azul oscuro = destino ancla. Elige una o dos rutas para ver los nombres de las paradas.")

    with lista:
        for i, r in enumerate(rutas.itertuples()):
            g = prop[prop.ruta_sk == r.ruta_sk]
            nov, col_nov = NOVEDAD.get(r.clasificacion_novedad, (r.clasificacion_novedad, "#546E7A"))
            with st.expander(nombres[r.ruta_sk], expanded=i == 0):
                st.markdown(f"<span class='mope-tag' style='background:{col_nov};color:white'>{nov}</span> "
                            f"<small>{r.pct_tramos_existentes:.0f} % de tramos en rutas oficiales · "
                            f"{r.region}</small>", unsafe_allow_html=True)
                a, b, c = st.columns(3)
                a.metric("Duración", f"{r.duracion_estimada_h:.0f} h", f"{r.tiempo_total_min / 60:.1f} h en carretera",
                         delta_color="off")
                b.metric("Emergentes", int(r.num_municipios_emergentes))
                c.metric("Crecimiento", f"{r.potencial_pred_medio_pct:+.0f} %")
                for p in g.itertuples():
                    etiqueta = ('<span class="mope-tag ancla">ANCLA</span>' if p.es_ancla else
                                '<span class="mope-tag flag">EMERGENTE</span>' if p.es_emergente else "")
                    viaje = f" · 🚗 {p.tiempo_desde_anterior_min:.0f} min" if p.orden_parada > 1 else ""
                    st.markdown(f"<span style='color:{color[r.ruta_sk]};font-weight:800'>{p.orden_parada}.</span> "
                                f"**{p.municipio}** {etiqueta}<br><small style='opacity:.7'>{p.region}{viaje} · "
                                f"estancia {p.estancia_sugerida_h:.0f} h</small>", unsafe_allow_html=True)
                st.caption(html.escape(_legible(r.descripcion or "")))

    st.markdown("#### 📊 Comparar rutas propuestas")
    tabla = pd.DataFrame([{
        "Ruta": nombres[r.ruta_sk], "Novedad": NOVEDAD.get(r.clasificacion_novedad, (r.clasificacion_novedad,))[0],
        "Tramos en rutas oficiales (%)": r.pct_tramos_existentes, "Paradas": r.num_municipios,
        "Emergentes": r.num_municipios_emergentes, "Carretera (h)": round(r.tiempo_total_min / 60, 1),
        "Duración total (h)": r.duracion_estimada_h, "Crecimiento esperado (%)": r.potencial_pred_medio_pct,
        "Necesidad social": r.necesidad_social_media, "Puntaje": r.puntaje_total,
        "Recorrido": " → ".join(prop[prop.ruta_sk == r.ruta_sk].municipio),
    } for r in rutas.itertuples()])
    st.dataframe(tabla, hide_index=True, width="stretch", column_config={
        "Necesidad social": st.column_config.ProgressColumn(min_value=0, max_value=1, format="%.2f"),
        "Puntaje": st.column_config.NumberColumn(format="%.2f"),
        "Crecimiento esperado (%)": st.column_config.NumberColumn(format="%+.0f %%")})
    st.download_button("⬇️ Descargar rutas propuestas (CSV)", tabla.to_csv(index=False).encode("utf-8-sig"),
                       "rutas_propuestas_mopedetu.csv", "text/csv")

    _recorrer(prop, nombres, color)

    with st.expander(f"📚 Rutas oficiales del catálogo de la Secretaría ({ofic.ruta_sk.nunique()})"):
        of = ofic.groupby("ruta_sk").agg(Ruta=("ruta", "first"), Tema=("tema", "first"),
                                         Recorrido=("municipio", " → ".join)).reset_index(drop=True)
        st.dataframe(of, hide_index=True, width="stretch")
    st.caption("Las rutas propuestas son hipótesis de trabajo generadas con datos de oferta (DENUE, Censos "
               "Económicos), no de visitantes; el siguiente paso es validarlas con las comunidades.")


def _recorrer(prop: pd.DataFrame, nombres: dict, color: dict):
    """Recorre una ruta propuesta por carretera real (OSRM) en el mapa de navegación, con agenda por días,
    indicaciones y enlaces a Google Maps y Waze."""
    st.markdown("#### 🛰️ Recorrer una ruta propuesta")
    sk = st.selectbox("Ruta", list(nombres), format_func=nombres.get, key="rt_recorrer",
                      label_visibility="collapsed")
    g = prop[prop.ruta_sk == sk].sort_values("orden_parada")
    puntos = tuple((float(r.lat), float(r.lon)) for r in g.itertuples())
    estimados = g.tiempo_desde_anterior_min.fillna(0).tolist()[1:]
    r = navegacion.ruta(puntos, "auto") or navegacion.ruta_recta(puntos, estimados)
    traslados = [0.0] + [t["min"] for t in r["tramos"]]

    # Agenda: jornadas de 9:00 a 19:00 con la estancia sugerida por el modelo en cada parada
    dia, reloj, agenda = 1, 9 * 60, []
    for k, p in enumerate(g.itertuples()):
        estancia = 60 * float(p.estancia_sugerida_h or 2)
        llegada = reloj + traslados[k]
        if k and llegada + estancia > 19 * 60:
            dia, llegada = dia + 1, 9 * 60 + traslados[k]
        agenda.append((dia, llegada))
        reloj = llegada + estancia
    hora = lambda m: f"{int(m // 60):02d}:{int(m % 60):02d}"  # noqa: E731

    filas = list(g.itertuples())
    rgb = tema.hex_rgb(color[sk])
    paradas = [dict(lon=float(p.lon), lat=float(p.lat), nombre=p.municipio, icono="⚓" if p.es_ancla else "📍",
                    actividad="Destino ancla" if p.es_ancla else ("Emergente con bandera" if p.es_emergente else "Parada"),
                    detalle=f"{p.region} · estancia {p.estancia_sugerida_h:.0f} h",
                    color=tema.hex_rgb(tema.COBALTO_OSC) if p.es_ancla else rgb, orden=i,
                    hora=f"día {agenda[i][0]}, {hora(agenda[i][1])}")
              for i, p in enumerate(filas) if i]
    geo = estado.datos().geo
    limites = [f["geometry"] for f in geo["features"] if f["properties"]["cve_geo"] in set(g.cve_geo)]
    izq, der = st.columns([1.7, 1])
    with izq:
        p0 = filas[0]
        navegacion.mapa(dict(lon=float(p0.lon), lat=float(p0.lat), nombre=p0.municipio,
                             detalle=f"Salida: día 1, 09:00 · {p0.region}"), paradas, r, limites, "auto", alto=560)
        st.caption("**▶ Recorrer** sigue la carretera como en un navegador · 🛰️/🗺️ cambia entre satélite y calles.")
    with der:
        k = st.columns(2)
        k[0].metric("Por carretera" if r["real"] else "En línea recta", f"{r['km']:,.0f} km")
        k[1].metric("Manejo", f"{r['min'] / 60:.1f} h", f"{agenda[-1][0]} día(s)", delta_color="off")
        st.dataframe(pd.DataFrame({
            "Día": [a[0] for a in agenda], "Llegada": [hora(a[1]) for a in agenda],
            "Municipio": [("⚓ " if p.es_ancla else "") + p.municipio for p in filas],
            "Traslado": ["salida"] + [f"{t['min']:.0f} min · {t['km']:.0f} km" for t in r["tramos"]],
        }), hide_index=True, width="stretch")
        b = st.columns(2)
        b[0].link_button("🗺️ Google Maps", navegacion.enlace_google(puntos, "auto"), width="stretch")
        b[1].link_button(f"🚙 Waze a {filas[1].municipio}", navegacion.enlace_waze(*puntos[1]), width="stretch")
        navegacion.indicaciones(r, [p.municipio for p in filas], traslados[1:])
    fuente = ("Trazo y tiempos por carreteras de OpenStreetMap (OSRM)" if r["real"]
              else "Sin conexión al servicio de rutas: distancias en línea recta y tiempos estimados por el modelo")
    st.caption(f"⚠️ {fuente}.")


# ---------------------------------------------------------------- Arma tu ruta (Rol B · Raúl)
def _armar(d, act):
    """Ruta a la medida: sale de cualquier municipio y visita los que elija el usuario (o los propone
    el motor), dibujada por carretera en el mapa de navegación."""
    pred, mp = estado.prediccion()
    mun = d.municipios.sort_values("nombre")
    nombres = dict(zip(mun.cve_geo, mun.nombre))
    anclas = set(mun[mun.es_ancla].cve_geo)
    # Solo el nombre: con la región en la etiqueta, buscar "Atlixco" encontraba toda su región primero.
    etiqueta = lambda c: f"{'⚓ ' if c in anclas else ''}{nombres[c]}"  # noqa: E731
    opciones = mun.cve_geo.tolist()
    capital = mun[mun.nombre == "Puebla"].cve_geo
    with st.container(border=True):
        c = st.columns([1.3, 1.25, 1.85, 0.9, 0.9])
        inicio = c[0].selectbox("🚩 Salida", opciones, format_func=etiqueta, key="ruta_inicio",
                                index=opciones.index(capital.iloc[0]) if len(capital) else 0)
        forma = c[1].segmented_control("Paradas", ["Automáticas", "Yo elijo"], default="Automáticas",
                                       key="ruta_forma") or "Automáticas"
        destinos = c[2].multiselect("Municipios a visitar (el orden se optimiza)", [o for o in opciones if o != inicio],
                                    format_func=etiqueta, max_selections=9, key="ruta_destinos",
                                    disabled=forma != "Yo elijo", placeholder="Escribe para buscar…")
        dias = c[3].select_slider("📅 Días", [1, 2, 3, 4], value=2, disabled=forma != "Automáticas")
        maximo = c[4].select_slider("Máx. paradas", list(range(3, 9)), value=6, disabled=forma != "Automáticas")

    if forma == "Yo elijo" and not destinos:
        st.info("Elige al menos un municipio a visitar. Puedes escribir su nombre para buscarlo.")
        return
    ruta = motor.ruta_personalizada(d, pred, inicio, destinos if forma == "Yo elijo" else None, dias, maximo)
    if ruta is None:
        st.warning(f"No hay municipios con oferta turística a menos de 2.5 h de {nombres[inicio]} para estas "
                   "actividades. Prueba **Yo elijo**, más días o más actividades en la barra lateral.")
        return

    ps = ruta.paradas
    puntos = tuple((float(p["lat"]), float(p["lon"])) for p in ps)
    r = navegacion.ruta(puntos, "auto") or navegacion.ruta_recta(puntos, [p["min_desde_anterior"] for p in ps[1:]])
    traslados = [0.0] + [t["min"] for t in r["tramos"]]

    # Agenda: jornadas de 9:00 a 19:00; si la siguiente visita no cabe, se pasa al día siguiente.
    dia, reloj, agenda = 1, 9 * 60, []
    for k, p in enumerate(ps):
        estancia = 180 if p["es_ancla"] else 150
        llegada = reloj + traslados[k]
        if k and llegada + estancia > 19 * 60:
            dia, llegada = dia + 1, 9 * 60 + traslados[k]
        agenda.append((dia, llegada))
        reloj = llegada + estancia
    hora = lambda m: f"{int(m // 60):02d}:{int(m % 60):02d}"  # noqa: E731

    k = st.columns(5)
    k[0].metric("Municipios", len(ps), f"{ruta.emergentes} emergentes", delta_color="off")
    k[1].metric("Distancia por carretera" if r["real"] else "Distancia en línea recta", f"{r['km']:,.0f} km")
    k[2].metric("Manejo", f"{r['min'] / 60:.1f} h", "tiempo de traslado", delta_color="off")
    k[3].metric("Duración", f"{agenda[-1][0]} día{'s' if agenda[-1][0] > 1 else ''}",
                f"regreso ≈ {hora(reloj)}", delta_color="off")
    k[4].metric("Tema", act.corto[ruta.tema] if ruta.tema in act.index else "Mixta")

    def color(p):
        if p["es_ancla"]:
            return tema.hex_rgb(tema.COBALTO_OSC)
        return list(act.color[p["actividades"][0]]) if p["actividades"] else tema.hex_rgb(tema.GUINDA)

    def detalle(p):
        acts = ", ".join(act.corto[a] for a in p["actividades"][:3]) or "Sin actividad destacada"
        return f"{p['region']} · {acts}"

    izq, der = st.columns([1.7, 1])
    with izq:
        st.markdown(f"#### 🛰️ {ruta.nombre}")
        paradas = [dict(lon=float(p["lon"]), lat=float(p["lat"]), nombre=p["nombre"], icono=p["iconos"] or "📍",
                        actividad="Destino consolidado" if p["es_ancla"] else ("Oportunidad" if p["flag"] else "Emergente"),
                        detalle=detalle(p), color=color(p), orden=i, hora=f"día {agenda[i][0]}, {hora(agenda[i][1])}")
                   for i, p in enumerate(ps) if i]
        cves = {p["cve_geo"] for p in ps}
        limites = [f["geometry"] for f in d.geo["features"] if f["properties"]["cve_geo"] in cves]
        navegacion.mapa(dict(lon=float(ps[0]["lon"]), lat=float(ps[0]["lat"]), nombre=ps[0]["nombre"],
                             detalle=f"Salida: día 1, 09:00 · {detalle(ps[0])}"), paradas, r, limites, "auto", alto=640)
        st.caption("**▶ Recorrer** sigue la carretera como en un navegador · clic en un municipio para ver su ficha · "
                   "🛰️/🗺️ cambia entre satélite y mapa de calles.")

    with der:
        st.markdown("#### 🗒️ Itinerario")
        st.dataframe(pd.DataFrame({
            "Día": [a[0] for a in agenda], "Llegada": [hora(a[1]) for a in agenda],
            "Municipio": [("⚓ " if p["es_ancla"] else "") + p["nombre"] for p in ps],
            "Actividades": [p["iconos"] for p in ps],
            "Traslado": ["salida"] + [f"{t['min']:.0f} min · {t['km']:.0f} km" for t in r["tramos"]],
        }), hide_index=True, width="stretch")
        b = st.columns(2)
        b[0].link_button("🗺️ Abrir en Google Maps", navegacion.enlace_google(puntos, "auto"), width="stretch")
        b[1].link_button(f"🚙 Ir a {ps[1]['nombre']} en Waze", navegacion.enlace_waze(*puntos[1]), width="stretch")
        navegacion.indicaciones(r, [p["nombre"] for p in ps], traslados[1:])
        if forma == "Automáticas":
            st.caption(f"Paradas propuestas por el motor: municipios con oferta en las actividades elegidas, a menos "
                       f"de 2.5 h entre sí, priorizando oportunidad y marginación, dentro de {dias} día(s).")

    fuente = ("Trazo y tiempos por carreteras de OpenStreetMap (OSRM)" if r["real"]
              else "Sin conexión al servicio de rutas: distancias en línea recta y tiempos estimados")
    st.caption(f"⚠️ {fuente}. Estancia sugerida: 3 h en destinos consolidados y 2.5 h en el resto.")
