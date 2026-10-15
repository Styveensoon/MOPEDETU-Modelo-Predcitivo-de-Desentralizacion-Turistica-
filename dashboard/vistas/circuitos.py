import pandas as pd
import streamlit as st

import estado
import motor
import navegacion
import tema


def render():
    d = estado.datos()
    ctx = estado.contexto()
    act = d.actividades.set_index("clave")
    pred, _ = estado.prediccion()

    tema.hero("🔁 Circuitos municipales",
              "Recorridos de medio día o un día dentro de un municipio, de una sola actividad o variados, "
              "armados con los establecimientos geolocalizados del DENUE.",
              estado.chips())

    if "Circuitos" not in ctx.predecir:
        st.info("En el modo Concreto desactivaste la predicción de **Circuitos**. Actívala en la barra lateral.")
        return

    ranking = motor.ranking_circuitos(estado.filtrar_region(pred), top=25)
    potencial = motor.ranking_circuitos(pred, top=len(d.municipios)).set_index("cve_geo").potencial

    # Cualquier municipio del estado; de inicio, el de mejor potencial con los filtros actuales.
    mun = d.municipios.sort_values("nombre")
    opciones, nombres = mun.cve_geo.tolist(), dict(zip(mun.cve_geo, mun.nombre))
    inicial = ranking.cve_geo.iloc[0] if not ranking.empty else opciones[0]
    with st.container(border=True):
        c = st.columns([1.4, 1.1, 1.3, 1.1, 1.1])
        cve = c[0].selectbox("📍 Municipio (escribe para buscar)", opciones, index=opciones.index(inicial),
                             format_func=nombres.get, key="circ_mun")
        tipo = c[1].segmented_control("Tipo de circuito", ["Variado", "Una actividad"], default="Variado",
                                      key="circ_tipo") or "Variado"
        acts_mun = sorted(d.poi[d.poi.cve_geo == cve].actividad.unique())
        actividad = c[2].selectbox("Actividad", acts_mun, format_func=lambda k: f"{act.icono[k]} {act.nombre[k]}",
                                   disabled=tipo != "Una actividad")
        horas = c[3].select_slider("⏱️ Duración", [3, 4, 6, 8, 10], value=6, format_func=lambda h: f"{h} h")
        modo = c[4].segmented_control("Recorrido", ["🚗 En auto", "🚶 A pie"], default="🚗 En auto",
                                      key="circ_perfil") or "🚗 En auto"
    perfil = "pie" if "pie" in modo else "auto"

    if not acts_mun:
        st.warning(f"{nombres[cve]} no tiene establecimientos turísticos geolocalizados en el DENUE para armar "
                   "un circuito. Elige otro municipio.")
        return
    kmh = 4.5 if perfil == "pie" else 25
    foco = [actividad] if tipo == "Una actividad" else (ctx.supuestos.actividades or None)
    circ = motor.circuito_municipal(d, cve, foco, horas, tipo == "Variado", kmh=kmh)
    if circ.empty and tipo == "Variado" and foco:  # el filtro de actividades no existe en este municipio
        circ = motor.circuito_municipal(d, cve, None, horas, True, kmh=kmh)
        if not circ.empty:
            st.info(f"{nombres[cve]} no tiene oferta en las actividades filtradas en la barra lateral: "
                    "el circuito usa todas sus actividades.")
    m = d.municipios.set_index("cve_geo").loc[cve]
    if circ.empty:
        st.warning("Este municipio no tiene puntos de interés para esa selección"
                   + (" a distancia caminable: prueba **En auto** o más horas." if perfil == "pie" else "."))
        return

    puntos = tuple([(float(m.lat), float(m.lon))] + list(zip(circ.lat.astype(float), circ.lon.astype(float))))
    r = navegacion.ruta(puntos, perfil)
    if r is None:
        r = navegacion.ruta_recta(puntos, circ.min_desde_anterior.tolist())
    circ["traslado"] = [t["min"] for t in r["tramos"]]
    circ["km"] = [t["km"] for t in r["tramos"]]
    reloj, horas_llegada = 9 * 60, []
    for t in circ.traslado:
        reloj += t
        horas_llegada.append(f"{int(reloj // 60):02d}:{int(reloj % 60):02d}")
        reloj += 60
    circ["hora"] = horas_llegada
    fin = f"{int(reloj // 60):02d}:{int(reloj % 60):02d}"
    if reloj - 9 * 60 > horas * 60 * 1.15:
        st.warning(f"Con los traslados reales por calle el circuito dura **{(reloj - 9 * 60) / 60:.1f} h**, más de las "
                   f"{horas} h elegidas" + (": a pie conviene recortar paradas o ir en auto." if perfil == "pie" else "."))

    k = st.columns(5)
    k[0].metric("Paradas", len(circ), f"{circ.actividad.nunique()} actividades", delta_color="off")
    k[1].metric("Distancia por calles" if r["real"] else "Distancia en línea recta", f"{r['km']:.1f} km")
    k[2].metric("Tiempo de traslado", f"{r['min']:.0f} min", f"{'en auto' if perfil == 'auto' else 'a pie'}",
                delta_color="off")
    k[3].metric("Horario", f"09:00 – {fin}", "1 h por parada", delta_color="off")
    k[4].metric("Valoración media", f"⭐ {circ.valoracion.mean():.1f}",
                f"potencial {potencial[cve]:.2f}" if cve in potencial.index else None, delta_color="off",
                help="Potencial del municipio = 0.6 × índice de oportunidad + 0.4 × diversidad de actividades.")

    izq, der = st.columns([1.7, 1])
    with izq:
        st.markdown(f"#### 🛰️ Circuito {tipo.lower()} en {m.nombre}")
        paradas = [dict(lon=float(p.lon), lat=float(p.lat), nombre=p.nombre, actividad=act.nombre[p.actividad],
                        icono=act.icono[p.actividad], color=list(act.color[p.actividad]),
                        valoracion=float(p.valoracion), orden=int(p.orden), hora=p.hora) for p in circ.itertuples()]
        limite = next((f["geometry"] for f in d.geo["features"] if f["properties"]["cve_geo"] == cve), None)
        navegacion.mapa(dict(lon=float(m.lon), lat=float(m.lat), nombre=f"Cabecera de {m.nombre}"),
                        paradas, r, limite, perfil, alto=640)
        st.caption("**▶ Recorrer** sigue la ruta como en un navegador · arrastra con clic derecho para inclinar o "
                   "girar · 🛰️/🗺️ cambia entre satélite y mapa de calles · clic en una parada para ver su ficha.")

    with der:
        st.markdown("#### 🗒️ Itinerario sugerido")
        filas = pd.DataFrame({"Hora": circ.hora, "#": circ.orden, "Lugar": circ.nombre,
                              "Actividad": [f"{act.icono[a]} {act.nombre[a]}" for a in circ.actividad],
                              "Traslado": [f"{t:.0f} min · {km:.1f} km" for t, km in zip(circ.traslado, circ.km)],
                              "⭐": circ.valoracion})
        st.dataframe(filas, hide_index=True, width="stretch")

        b = st.columns(2)
        b[0].link_button("🗺️ Abrir en Google Maps", navegacion.enlace_google(puntos, perfil), width="stretch")
        b[1].link_button("🚙 Ir a la parada 1 en Waze", navegacion.enlace_waze(*puntos[1]), width="stretch")

        if r["pasos"]:
            with st.expander(f"🧭 Indicaciones paso a paso ({len(r['pasos'])})"):
                for tramo, grupo in pd.DataFrame(r["pasos"]).groupby("tramo"):
                    p = circ.iloc[tramo]
                    st.markdown(f"**{'Cabecera' if tramo == 0 else f'Parada {tramo}'} → parada {tramo + 1}: "
                                f"{p.nombre}** · {p.traslado:.0f} min")
                    st.markdown("\n".join(f"- {s.flecha} {s.texto}" + (f" · {s.km * 1000:.0f} m" if s.km < 1 and s.km > 0
                                                                     else f" · {s.km:.1f} km" if s.km >= 1 else "")
                                          for s in grupo.itertuples()))

        st.markdown("#### 🏆 Sugerencias: mejor potencial")
        st.caption("Con los filtros actuales. Puedes elegir cualquier otro municipio arriba.")
        st.dataframe(ranking[["nombre", "actividades", "potencial"]], hide_index=True,
                     height=250, width="stretch",
                     column_config={"nombre": "Municipio", "actividades": "Actividades",
                                    "potencial": st.column_config.ProgressColumn("Potencial", min_value=0, max_value=1,
                                                                                 format="%.2f")})

    fuente = ("Ruta y tiempos por calles de OpenStreetMap (OSRM)" if r["real"]
              else "Sin conexión al servicio de rutas: distancias en línea recta y tiempos estimados a 25 km/h")
    st.caption(f"⚠️ {fuente}. Paradas tomadas de puntos del DENUE; verifica horarios y accesos antes de publicar. "
               "Imágenes satelitales y mapa de calles © Esri, Maxar, OpenStreetMap.")
