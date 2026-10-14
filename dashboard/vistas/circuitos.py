import pandas as pd
import streamlit as st

import estado
import mapas
import motor
import tema


def render():
    d = estado.datos()
    ctx = estado.contexto()
    act = d.actividades.set_index("clave")
    pred, mp = estado.prediccion()

    tema.hero("🔁 Circuitos municipales",
              "Recorridos de medio día o un día dentro de un municipio, de una sola actividad o variados, "
              "armados con los establecimientos geolocalizados del DENUE.",
              estado.chips())

    if "Circuitos" not in ctx.predecir:
        st.info("En el modo Concreto desactivaste la predicción de **Circuitos**. Actívala en la barra lateral.")
        return

    ranking = motor.ranking_circuitos(estado.filtrar_region(pred), top=25)
    if ranking.empty:
        st.warning("No hay municipios con oferta para estas actividades.")
        return

    izq, der = st.columns([1, 2.2])
    with izq:
        st.markdown("#### 🏆 Mejor potencial para circuitos")
        st.dataframe(ranking[["nombre", "region", "actividades", "potencial"]], hide_index=True,
                     height=280, width="stretch",
                     column_config={"nombre": "Municipio", "region": "Región", "actividades": "Actividades",
                                    "potencial": st.column_config.ProgressColumn("Potencial", min_value=0, max_value=1,
                                                                                 format="%.2f")})
        nombres = dict(zip(mp.cve_geo, mp.nombre))
        opciones = ranking.cve_geo.tolist()
        cve = st.selectbox("Municipio", opciones, format_func=nombres.get)
        tipo = st.segmented_control("Tipo de circuito", ["Variado", "Una actividad"], default="Variado") or "Variado"
        horas = st.select_slider("Duración", [3, 4, 6, 8, 10], value=6, format_func=lambda h: f"{h} h")
        acts_mun = sorted(pred[pred.cve_geo == cve].actividad.unique())
        foco = None
        if tipo == "Una actividad":
            foco = [st.selectbox("Actividad", acts_mun, format_func=lambda k: f"{act.icono[k]} {act.nombre[k]}")]

    circ = motor.circuito_municipal(d, cve, foco or (ctx.supuestos.actividades or None), horas, tipo == "Variado")
    m = mp.set_index("cve_geo").loc[cve]

    with der:
        if circ.empty:
            st.warning("Este municipio no tiene puntos de interés para esa selección.")
            return
        k = st.columns(4)
        k[0].metric("Paradas", len(circ))
        k[1].metric("Actividades", circ.actividad.nunique())
        k[2].metric("Traslados", f"{circ.min_desde_anterior.sum():.0f} min")
        k[3].metric("Valoración media", f"⭐ {circ.valoracion.mean():.1f}")

        circ["tt"] = circ.apply(lambda r: f"<b>{r.orden}. {r.nombre}</b><br/>{act.icono[r.actividad]} "
                                          f"{act.nombre[r.actividad]}<br/>⭐ {r.valoracion}", axis=1)
        circ["color"] = circ.actividad.map(lambda a: list(act.color[a]) + [255])
        circ["etiqueta"] = circ.orden.astype(str)
        trayecto = pd.DataFrame([{"path": [[m.lon, m.lat]] + circ[["lon", "lat"]].values.tolist(),
                                  "tt": f"Circuito {tipo.lower()} · {m.nombre}"}])
        inicio = pd.DataFrame([{"lon": m.lon, "lat": m.lat, "tt": f"<b>Inicio: cabecera de {m.nombre}</b>",
                                "etiqueta": "★"}])
        sub = mp[mp.cve_geo == cve]
        capas = [
            mapas.capa_municipios(d.geo, sub, "indice_oportunidad", sub.set_index("cve_geo").nombre,
                                  vmin=0, vmax=1),
            mapas.capa_trayecto(trayecto, (14, 42, 92)),
            mapas.pdk.Layer("ScatterplotLayer", circ, get_position=["lon", "lat"], get_fill_color="color",
                            get_radius=250, radius_min_pixels=8, stroked=True, get_line_color=[255, 255, 255],
                            line_width_min_pixels=2, pickable=True),
            mapas.capa_puntos(inicio, [232, 177, 13, 255], 300),
            mapas.capa_texto(pd.concat([circ[["lon", "lat", "etiqueta"]], inicio[["lon", "lat", "etiqueta"]]]),
                             "etiqueta", 13),
        ]
        zoom = 11.2 if m.area_km2 < 250 else 10.4 if m.area_km2 < 700 else 9.7
        vista = mapas.pdk.ViewState(latitude=m.lat, longitude=m.lon, zoom=zoom, pitch=35)
        st.pydeck_chart(mapas.deck(capas, vista), height=470)

        st.markdown("#### 🗒️ Itinerario sugerido")
        reloj = 9 * 60
        filas = []
        for r in circ.itertuples():
            reloj += r.min_desde_anterior
            filas.append({"Hora": f"{int(reloj // 60):02d}:{int(reloj % 60):02d}", "#": r.orden, "Lugar": r.nombre,
                          "Actividad": f"{act.icono[r.actividad]} {act.nombre[r.actividad]}",
                          "Traslado (min)": round(r.min_desde_anterior), "⭐": r.valoracion})
            reloj += 60
        st.dataframe(pd.DataFrame(filas), hide_index=True, width="stretch")
