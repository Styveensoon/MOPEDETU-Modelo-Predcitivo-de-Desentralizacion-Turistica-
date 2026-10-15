import pandas as pd
import plotly.express as px
import streamlit as st

import estado
import mapas
import motor
import navegacion
import tema

COLORES_RUTA = ["#1B3F8B", "#8A1538", "#E8B10D", "#2E7D32", "#00897B", "#D81B60", "#546E7A", "#6D4C41"]


def render():
    d = estado.datos()
    ctx = estado.contexto()
    act = d.actividades.set_index("clave")
    _, mp = estado.prediccion()

    tema.hero("🧭 Rutas turísticas intermunicipales",
              "Rutas que parten de un destino consolidado (⚓) o del municipio que elijas y llevan al visitante hacia "
              "municipios emergentes con oferta real.",
              estado.chips() + [f"Máx. {ctx.dias} días"])

    if "Rutas" not in ctx.predecir:
        st.info("En el modo Concreto desactivaste la predicción de **Rutas**. Actívala en la barra lateral.")
        return

    modo = st.segmented_control("Rutas", ["✨ Rutas sugeridas", "🛠️ Arma tu ruta"], default="✨ Rutas sugeridas",
                                key="rutas_modo", label_visibility="collapsed") or "✨ Rutas sugeridas"
    if modo == "🛠️ Arma tu ruta":
        _armar(d, act)
        return

    rutas = estado.rutas()
    if not rutas:
        st.warning("No se encontraron rutas con estos filtros. Prueba con más actividades, más días o menos "
                   "municipios emergentes mínimos.")
        return

    nombres = [f"#{i + 1} · {r.nombre}" for i, r in enumerate(rutas)]
    elegidas = st.multiselect("Rutas a mostrar en el mapa", nombres, default=nombres[:3])
    idx = [nombres.index(n) for n in elegidas] or [0]

    mapa, lista = st.columns([1.6, 1])
    with mapa:
        base = mp.copy()
        tt = base.set_index("cve_geo").apply(
            lambda r: f"<b>{r.nombre}</b><br>Índice {r.indice_oportunidad:.2f}<br>{r.icono_lider} {r.actividad_lider}", axis=1)
        m = mapas.Mapa(d.geo, alto=620, fondo=mapas.FONDO_ESTADO).municipios(base, "indice_oportunidad", tt, paleta=tema.SEQ_TALAVERA[:3],
                                                   cuantiles=True)
        paradas = []
        for i in idx:
            r = rutas[i]
            color = COLORES_RUTA[i % len(COLORES_RUTA)]
            m.trayecto([p["lon"] for p in r.paradas], [p["lat"] for p in r.paradas], color, 4,
                       f"<b>{r.nombre}</b><br>{len(r.paradas)} paradas · {r.minutos / 60:.1f} h")
            for k, p in enumerate(r.paradas):
                paradas.append(dict(lon=p["lon"], lat=p["lat"], etiqueta=f"{k + 1}. {p['nombre']}",
                                    color=tema.COBALTO_OSC if p["es_ancla"] else color,
                                    tt=f"<b>{k + 1}. {p['nombre']}</b><br>{p['iconos']}<br>"
                                       + ("⚓ Ancla" if p["es_ancla"] else f"🌱 Emergente · score {p['score']:.2f}")))
        pdf = pd.DataFrame(paradas).drop_duplicates(["lon", "lat"])
        m.puntos(pdf, "color", 12, "tt", texto="etiqueta")
        m.encuadre(pdf.lat, pdf.lon, margen=0.15, aspecto=1.15)
        mapas.mostrar(m, "rutas_mapa")

    with lista:
        for i, r in enumerate(rutas):
            color = COLORES_RUTA[i % len(COLORES_RUTA)]
            with st.expander(f"#{i + 1} · {r.nombre}", expanded=i in idx[:1]):
                a, b, c = st.columns(3)
                a.metric("Score", f"{r.score_norm:.2f}")
                b.metric("Duración", f"{r.minutos / 60:.1f} h")
                c.metric("Emergentes", r.emergentes)
                for k, p in enumerate(r.paradas):
                    tag = '<span class="mope-tag ancla">ANCLA</span>' if p["es_ancla"] else (
                        '<span class="mope-tag flag">OPORTUNIDAD</span>' if p["flag"] else '<span class="mope-tag">EMERGENTE</span>')
                    viaje = "" if k == 0 else f" · 🚗 {p['min_desde_anterior']:.0f} min"
                    st.markdown(f"<span style='color:{color};font-weight:800'>{k + 1}.</span> **{p['nombre']}** "
                                f"{p['iconos']} {tag}<br/><small style='opacity:.7'>{p['region']}{viaje}</small>",
                                unsafe_allow_html=True)

    st.markdown("#### 📊 Comparar rutas")
    tabla = pd.DataFrame([{
        "Ruta": f"#{i + 1} {r.nombre}", "Score": r.score_norm, "Horas": round(r.minutos / 60, 1),
        "Paradas": len(r.paradas), "Emergentes": r.emergentes,
        "Marginación media": round(sum(p["social"] for p in r.paradas[1:]) / max(1, len(r.paradas) - 1), 2),
        "Recorrido": " → ".join(r.municipios),
    } for i, r in enumerate(rutas)])
    c1, c2 = st.columns([1, 1.4])
    with c1:
        fig = px.scatter(tabla, x="Horas", y="Score", size="Emergentes", color="Marginación media",
                         hover_name="Ruta", color_continuous_scale=["#F6D678", "#C45228", "#8A1538"], size_max=30)
        fig.update_layout(height=320, margin=dict(l=0, r=0, t=10, b=0))
        st.plotly_chart(fig)
    with c2:
        st.dataframe(tabla, hide_index=True, width="stretch", height=320,
                     column_config={"Score": st.column_config.ProgressColumn(min_value=0, max_value=1, format="%.2f")})
    st.download_button("⬇️ Descargar rutas (CSV)", tabla.to_csv(index=False).encode("utf-8-sig"),
                       "rutas_mopedetu.csv", "text/csv")


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
