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
        st.dataframe(ranking[["nombre", "actividades", "potencial"]], hide_index=True,
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

        circ["tt"] = circ.apply(lambda r: f"<b>{r.orden}. {r.nombre}</b><br>{act.icono[r.actividad]} "
                                          f"{act.nombre[r.actividad]}<br>⭐ {r.valoracion}", axis=1)
        circ["color"] = circ.actividad.map(lambda a: act.color[a])
        circ["etiqueta"] = circ.orden.astype(str)
        inicio = pd.DataFrame([{"lon": m.lon, "lat": m.lat, "tt": f"<b>Inicio: cabecera de {m.nombre}</b>",
                                "etiqueta": "Inicio"}])
        otros = set(mp.cve_geo) - {cve}
        mapa = (mapas.Mapa(d.geo, alto=520)
                .municipios(mp, None, mp.set_index("cve_geo").nombre, color_fijo=(255, 246, 214),
                            atenuar=otros, resaltar={cve})
                .nombres(mp[mp.cve_geo != cve], tamano=11)
                .trayecto([m.lon] + circ.lon.tolist(), [m.lat] + circ.lat.tolist(), tema.COBALTO_OSC, 3,
                          f"Circuito {tipo.lower()} · {m.nombre}")
                .puntos(circ, "color", 24, "tt", texto="etiqueta", posicion_texto="middle center",
                        color_texto="white", tamano_texto=12)
                .puntos(inicio, tema.AMARILLO, 20, "tt", texto="etiqueta", simbolo="star", posicion_texto="bottom center")
                .encuadre(list(circ.lat) + [m.lat], list(circ.lon) + [m.lon], margen=0.45, aspecto=1.7))
        mapas.mostrar(mapa, "circ_mapa")

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
