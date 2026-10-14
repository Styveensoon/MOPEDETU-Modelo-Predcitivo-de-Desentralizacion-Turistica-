import pandas as pd
import plotly.express as px
import streamlit as st

import estado
import mapas
import tema

COLORES_RUTA = ["#1B3F8B", "#8A1538", "#E8B10D", "#2E7D32", "#00897B", "#D81B60", "#546E7A", "#6D4C41"]


def render():
    d = estado.datos()
    ctx = estado.contexto()
    act = d.actividades.set_index("clave")
    _, mp = estado.prediccion()

    tema.hero("🧭 Rutas turísticas intermunicipales",
              "Cada ruta parte de un destino consolidado (⚓) y lleva al visitante hacia municipios emergentes con oferta real.",
              estado.chips() + [f"Máx. {ctx.dias} días"])

    if "Rutas" not in ctx.predecir:
        st.info("En el modo Concreto desactivaste la predicción de **Rutas**. Actívala en la barra lateral.")
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
            lambda r: f"<b>{r.nombre}</b><br/>Índice {r.indice_oportunidad:.2f}<br/>{r.icono_lider} {r.actividad_lider}", axis=1)
        capas = [mapas.capa_municipios(d.geo, base, "indice_oportunidad", tt, paleta=tema.SEQ_TALAVERA[:3], cuantiles=True)]
        paradas = []
        for i in idx:
            r = rutas[i]
            color = tema.hex_rgb(COLORES_RUTA[i % len(COLORES_RUTA)])
            capas.append(mapas.capa_trayecto(pd.DataFrame([{
                "path": [[p["lon"], p["lat"]] for p in r.paradas],
                "tt": f"<b>{r.nombre}</b><br/>{len(r.paradas)} paradas · {r.minutos / 60:.1f} h"}]), color))
            for k, p in enumerate(r.paradas):
                paradas.append(dict(lon=p["lon"], lat=p["lat"], etiqueta=f"{k + 1}",
                                    color=[14, 42, 92, 255] if p["es_ancla"] else color + [255],
                                    tt=f"<b>{k + 1}. {p['nombre']}</b><br/>{p['iconos']}<br/>"
                                       + ("⚓ Ancla" if p["es_ancla"] else f"🌱 Emergente · score {p['score']:.2f}")))
        pdf = pd.DataFrame(paradas)
        capas.append(mapas.pdk.Layer("ScatterplotLayer", pdf, get_position=["lon", "lat"], get_fill_color="color",
                                     get_radius=2600, radius_min_pixels=7, stroked=True, get_line_color=[255, 255, 255],
                                     line_width_min_pixels=2, pickable=True))
        capas.append(mapas.capa_texto(pdf, "etiqueta", 12))
        centro = pdf[["lat", "lon"]].mean()
        vista = mapas.pdk.ViewState(latitude=centro.lat, longitude=centro.lon, zoom=7.6, pitch=0)
        st.pydeck_chart(mapas.deck(capas, vista), height=600)

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
