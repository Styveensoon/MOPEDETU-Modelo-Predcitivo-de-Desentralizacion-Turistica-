"""🔁 Circuitos: recorridos dentro de un municipio desde su cabecera (dw.dim_circuito y model/reglas_circuitos.py)."""
import html

import pandas as pd
import streamlit as st

import bd
import navegacion
import reglas_circuitos as rc
import tema

PERFIL = {"a_pie": "pie", "auto": "auto"}
INCUMPLIMIENTO = {"pocas_paradas": "no hay suficientes lugares dentro del radio del circuito",
                  "sin_atractivo": "ningún atractivo queda dentro del radio", "excede_duracion": "no cabe en el tiempo",
                  "tramo_largo": "algún tramo es demasiado largo", "actividad_no_principal": "la actividad no es "
                  "principal del municipio", "tematico_sin_actividad": "elige una actividad"}


def render():
    tema.hero("🔁 Circuitos municipales",
              "Recorridos de medio día o un día dentro de un municipio, desde su cabecera, con lugares reales: "
              "atractivos, experiencias (talleres, productores) y cocina tradicional.", [])
    try:
        apt, (circ, par), mun = bd.aptitud_circuitos(), bd.circuitos(), bd.municipios().set_index("municipio_sk")
    except bd.SinDatos as e:
        st.error(f"No se pudieron leer los circuitos: {e}")
        return
    aptos = apt[apt.apto.astype(bool)].sort_values("potencial_circuito", ascending=False)
    no_aptos = apt[~apt.apto.astype(bool)]
    k = st.columns(3)
    k[0].metric("Municipios aptos", len(aptos), "con un circuito que cumple las reglas", delta_color="off")
    k[1].metric("Circuitos calculados", int(circ.cumple.astype(bool).sum()), "que cumplen", delta_color="off")
    k[2].metric("Sin circuito", len(no_aptos), "con su motivo", delta_color="off")

    nombres = dict(zip(aptos.municipio_sk, aptos.nombre))
    pref = st.session_state.pop("ir_a_circuito", None)
    opciones = list(nombres)
    mk = st.selectbox("Municipio (ordenados por potencial de circuito)", opciones, format_func=nombres.get,
                      index=opciones.index(pref) if pref in opciones else 0, key="ci_mun")
    cab = (float(mun.cabecera_lat[mk]), float(mun.cabecera_lon[mk]))

    c = st.columns([1, 1, 1, 1.4])
    personalizar = c[0].toggle("Personalizar", value=False, key="ci_pers")
    modalidad = c[1].segmented_control("Modalidad", ["a_pie", "auto"], default="a_pie", key="ci_mod",
                                       format_func={"a_pie": "🚶 A pie", "auto": "🚗 En auto"}.get,
                                       disabled=not personalizar) or "a_pie"
    horas = c[2].slider("Horas", 3, 10, 4, key="ci_h", disabled=not personalizar)
    ficha = bd.ficha().set_index("municipio_sk")
    principales = {a["codigo"]: f"{a['icono']} {a['nombre']}" for a in (ficha.actividades_principales.get(mk) or [])}
    tipo = c[3].selectbox("Tipo", ["variado"] + list(principales), key="ci_tipo", disabled=not personalizar,
                          format_func=lambda t: "Variado" if t == "variado" else f"Temático: {principales[t]}")

    lugares = bd.lugares(mk)
    if personalizar:
        res = rc.armar_circuito(lugares, cab, modalidad, horas, "variado" if tipo == "variado" else "tematico",
                                None if tipo == "variado" else tipo, set(principales))
        paradas = pd.DataFrame(res["paradas"])
        trazo, fuente = None, "personalizado"
        if not res["cumple"]:
            st.warning("Este circuito no cumple: " + "; ".join(INCUMPLIMIENTO.get(i, i) for i in res["incumplimientos"])
                       + ". Prueba más horas, en auto o el circuito variado.")
    else:
        est = circ[(circ.municipio_sk == mk) & circ.es_estandar.astype(bool)].iloc[0]
        paradas = par[par.circuito_sk == est.circuito_sk].copy()
        res = dict(modalidad=est.modalidad, duracion_h=float(est.duracion_h), duracion_min=float(est.duracion_min),
                   minutos_traslado=float(est.minutos_traslado))
        modalidad = est.modalidad
        trazo = est.geom_trazo if isinstance(est.geom_trazo, dict) else None
        fuente = "estándar"
        st.caption(f"Circuito estándar: {est.descripcion}.")
    if paradas.empty:
        st.info("Sin paradas para este circuito.")
        return
    paradas = paradas.merge(lugares[["lugar_id", "url"]], on="lugar_id", how="left") if "url" not in paradas else paradas

    puntos = tuple([cab] + [(float(a), float(o)) for a, o in zip(paradas.lat, paradas.lon)] + [cab])
    mins = paradas.min_desde_anterior.astype(float).tolist() + [rc.minutos(puntos[-2], cab, modalidad)]
    if trazo:
        kms = [rc.km(a, b) * rc.PARAMETROS["factor_rodeo"] for a, b in zip(puntos, puntos[1:])]
        r = navegacion.ruta_guardada(trazo, puntos, kms, mins)
    else:
        r = navegacion.ruta(puntos, PERFIL[modalidad]) or navegacion.ruta_recta(puntos, mins)
    hora = lambda m: f"{int(m // 60):02d}:{int(m % 60):02d}"  # noqa: E731
    k = st.columns(4)
    k[0].metric("Paradas", len(paradas))
    k[1].metric("Duración", f"{res['duracion_min'] / 60:.1f} h", f"de {res['duracion_h']:g} h", delta_color="off")
    k[2].metric("Traslados", f"{res['minutos_traslado']:.0f} min", "estimados", delta_color="off")
    k[3].metric("Por calle (OSRM)" if r["real"] else "En línea recta", f"{r['km']:.1f} km", f"{r['min']:.0f} min",
                delta_color="off")
    if r["real"] and r["min"] > 1.15 * res["minutos_traslado"]:
        st.warning(f"Por calle real el traslado toma {r['min']:.0f} min, más de 15 % sobre lo estimado: deja margen.")

    izq, der = st.columns([1.6, 1])
    with izq:
        color = tema.hex_rgb(tema.GUINDA)
        pts = [dict(lon=float(p.lon), lat=float(p.lat), nombre=p.nombre,
                    icono="🍽️" if p.tipo_parada == "comida" else ("🧑‍🎨" if p.tipo_parada == "experiencia" else "📍"),
                    actividad=p.categoria, detalle=f"estancia {int(p.estancia_min)} min", color=color, orden=i + 1,
                    hora=hora(float(p.llegada_min))) for i, p in enumerate(paradas.itertuples())]
        limites = [f["geometry"] for f in bd.geo()["features"] if f["properties"]["cve_geo"] == mun.cve_geo[mk]]
        navegacion.mapa(dict(lon=cab[1], lat=cab[0], nombre=f"Cabecera de {mun.nombre[mk]}",
                             detalle="Salida 09:00 y regreso"), pts, r, limites, PERFIL[modalidad], alto=560)
    with der:
        tabla = pd.DataFrame({
            "Llegada": [hora(float(x)) for x in paradas.llegada_min], "Lugar": paradas.nombre,
            "Tipo": paradas.tipo_parada, "Categoría": paradas.categoria,
            "Estancia (min)": paradas.estancia_min.astype(int),
            "Fuente": paradas.origen.map({"curado": "✅ curado", "osm": "OpenStreetMap", "denue": "DENUE"})})
        st.dataframe(tabla, hide_index=True, width="stretch")
        st.download_button("⬇️ Itinerario (CSV)", tabla.to_csv(index=False).encode("utf-8-sig"),
                           f"circuito_{mun.nombre[mk]}.csv", "text/csv", width="stretch")
        curados = paradas[paradas.origen == "curado"]
        for p in curados.itertuples():
            if isinstance(p.url, str):
                st.markdown(f"✅ [{html.escape(p.nombre)}]({p.url})")
        st.caption(f"Circuito {fuente}. Velocidades {rc.PARAMETROS['velocidad_kmh']['a_pie']} km/h a pie y "
                   f"{rc.PARAMETROS['velocidad_kmh']['auto']} km/h en auto con rodeo ×{rc.PARAMETROS['factor_rodeo']}.")

    with st.expander(f"Municipios sin circuito ({len(no_aptos)}) y por qué"):
        st.dataframe(no_aptos[["nombre", "region", "motivo_no_apto"]].rename(
            columns={"nombre": "Municipio", "region": "Región", "motivo_no_apto": "Motivo"}),
            hide_index=True, width="stretch")
        elegido = st.selectbox("Armar una ruta intermunicipal desde…", list(no_aptos.municipio_sk),
                               format_func=dict(zip(no_aptos.municipio_sk, no_aptos.nombre)).get, key="ci_ruta_desde")
        if st.button("🧭 Armar ruta desde aquí"):
            st.session_state["rutas_modo"] = "🛠️ Arma tu ruta"
            st.session_state["ar_inicio"] = int(elegido)
            st.switch_page(st.session_state["paginas"]["rutas"])
