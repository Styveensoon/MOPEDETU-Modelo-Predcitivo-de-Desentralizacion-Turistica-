import html

import pandas as pd
import pydeck as pdk
import streamlit as st

import estado
import ficha_bd as fb
import mapas
import tema


def render():
    tema.hero("🏘️ Ficha técnica municipal",
              "Datos reales por municipio: actividades, infraestructura, temporadas y semáforos. "
              "Pasa el cursor para ver el resumen y haz clic para abrir la ficha completa.",
              ["DENUE 05/2026", "Censo 2020", "OpenStreetMap", "Sectur Puebla"])

    df = fb.cargar()
    if df is None:
        st.error("No se pudo leer `dw.v_ficha_municipio`. Revisa el archivo `.env` con SUPABASE_URL y "
                 "SUPABASE_PUBLISHABLE_KEY (ver `.env.example`).")
        return

    c1, c2 = st.columns([3, 1])
    dim = c1.segmented_control("Colorear el mapa por", list(fb.DIMENSIONES), default="turismo_actual",
                               format_func=lambda k: " ".join(fb.DIMENSIONES[k]), key="ft_dim") or "turismo_actual"
    nombres_fijos = c2.toggle("🏷️ Todos los nombres", value=False, key="ft_nombres")

    geo = estado.datos().geo
    props = pd.DataFrame([f["properties"] for f in geo["features"]])
    fichas = df.set_index("cve_geo")

    mapa, panel = st.columns([1.55, 1])
    with mapa:
        p = mapas.poligonos(geo).copy()
        niveles = {c: fb.nivel(f, dim) for c, f in fichas.iterrows()}
        p["color"] = p.cve_geo.map(lambda c: list(fb.COLOR[niveles.get(c, "gris")]) + [225])
        p["tt"] = p.cve_geo.map(lambda c: _tooltip(fichas.loc[c]) if c in fichas.index else "")
        sel_prev = st.session_state.get("ft_cve")
        p["borde"] = p.cve_geo.map(lambda c: [14, 42, 92, 255] if c == sel_prev else [255, 255, 255, 220])
        p["ancho"] = p.cve_geo.map(lambda c: 3.5 if c == sel_prev else 0.8)
        capa = pdk.Layer("PolygonLayer", p, id="ficha_municipios", get_polygon="poly", get_fill_color="color",
                         get_line_color="borde", get_line_width="ancho", line_width_units=mapas.PIXELES,
                         stroked=True, filled=True, pickable=True, auto_highlight=True,
                         highlight_color=[14, 42, 92, 120])
        anclas = set(df[df.es_ancla].cve_geo)
        capas = [capa] + mapas.capas_nombres(props, anclas, fijos=nombres_fijos)
        vista = mapas.vista_ajustada(mapas.LIMITES_PUEBLA["lat"], mapas.LIMITES_PUEBLA["lon"],
                                     ancho=760, alto=620, margen=1.12)
        evento = st.pydeck_chart(mapas.deck(capas, vista), height=620, on_select="rerun",
                                 selection_mode="single-object", key="ft_mapa")
        _leyenda(dim)

    try:
        objs = evento.selection.objects.get("ficha_municipios", [])
        if objs:
            st.session_state["ft_cve"] = objs[0]["cve_geo"]
    except Exception:
        pass

    with panel:
        orden = df.sort_values("nombre")
        cves = orden.cve_geo.tolist()
        actual = st.session_state.get("ft_cve") or df.loc[df.nombre == "Cuetzalan del Progreso", "cve_geo"].iloc[0]
        cve = st.selectbox("🔎 Municipio", cves, index=cves.index(actual),
                           format_func=dict(zip(orden.cve_geo, orden.nombre)).get, key=f"ft_sel_{actual}")
        st.session_state["ft_cve"] = cve
        _ficha(fichas.loc[cve], df)


# ---------------------------------------------------------------- piezas
def _tooltip(f) -> str:
    marcas = (" ✨" if f.es_pueblo_magico else "") + (" ⚓" if f.es_ancla else "")
    acts = " · ".join(f"{a['icono']} {html.escape(a['nombre'])}" for a in (f.actividades_principales or [])[:3]) \
        or "Sin actividad principal"
    sem = "  ".join(f"{fb.DIMENSIONES[d][0]}{fb.EMOJI[fb.nivel(f, d)]}" for d in fb.DIMENSIONES)
    meses = " · ".join(fb.MESES_LARGO[m - 1] for m in (f.meses_fuertes or [])) or "sin temporada propia"
    return (f"<b>{html.escape(f.nombre)}</b>{marcas}<br/><span style='opacity:.8'>{f.region}</span><br/>"
            f"{acts}<br/>{sem}<br/>📅 {meses}")


def _leyenda(dim: str):
    items = "".join(
        f"<span style='display:inline-flex;align-items:center;margin-right:14px'>"
        f"<span style='width:12px;height:12px;border-radius:3px;margin-right:5px;"
        f"background:rgb{fb.COLOR[n]}'></span>{texto}</span>"
        for n, texto in fb.LECTURA[dim].items())
    st.markdown(f"<div class='mope-leyenda'><b>{' '.join(fb.DIMENSIONES[dim])}</b><br/>{items}</div>",
                unsafe_allow_html=True)
    st.caption("🧳 Turismo · 🛣️ Infraestructura · 🎯 Oferta · 📈 Potencial · 🤝 Social. "
               "El color indica qué hacer, no si el municipio es bueno o malo. ⚓ = destino ancla.")


def _ficha(f, todos: pd.DataFrame):
    marcas = []
    if f.es_pueblo_magico:
        marcas.append('<span class="mope-tag">✨ Pueblo Mágico</span>')
    if f.es_ancla:
        marcas.append('<span class="mope-tag ancla">⚓ Ancla</span>')
    pob = f"{f.poblacion:,.0f} hab." if pd.notna(f.poblacion) else ""
    st.markdown(f"### {f.nombre}")
    st.markdown(f"{' '.join(marcas)} <span style='opacity:.75'>{f.region} · clave {f.name} · {pob}</span>",
                unsafe_allow_html=True)

    # Semáforos
    filas = []
    for d, (ico, nom) in fb.DIMENSIONES.items():
        s = (f.semaforos or {}).get(d) or {}
        n = s.get("nivel", "gris")
        filas.append(f"<div style='display:flex;gap:8px;margin:3px 0'><span>{fb.EMOJI[n]}</span>"
                     f"<span><b>{ico} {nom}</b> · {fb.LECTURA[d][n]}<br/>"
                     f"<small style='opacity:.7'>{html.escape(s.get('motivo') or '')}</small></span></div>")
    st.markdown(f"<div class='mope-card'>{''.join(filas)}</div>", unsafe_allow_html=True)

    t1, t2, t3, t4 = st.tabs(["🎯 Actividades", "🛣️ Infraestructura", "📅 Temporadas", "🧭 Rutas y banderas"])
    with t1:
        principales = f.actividades_principales or []
        if not principales:
            st.info("Sin actividades principales registradas.")
        for a in principales:
            nivel = a["nivel"].replace("_", " ")
            ej = ", ".join(a.get("ejemplos") or [])
            detalle = f"{a['unidades']} establecimientos · CL {a['cl']}" if a["unidades"] else "atractivo de catálogo oficial"
            st.markdown(f"<div class='mope-card'><b>{a['icono']} {a['nombre']}</b> "
                        f"<span class='mope-tag'>{nivel}</span><br/><small>{detalle}</small>"
                        + (f"<br/><small style='opacity:.7'>Ej.: {html.escape(ej)}</small>" if ej else "")
                        + "</div>", unsafe_allow_html=True)
        otras = f.otras_actividades or []
        if otras:
            st.caption("También: " + " · ".join(f"{a['icono']} {a['nombre']}" for a in otras[:6]))
        if f.oferta_sin_registro:
            st.warning("🚩 Oferta reconocida por la Secretaría sin registro en el DENUE: "
                       + ", ".join(f.oferta_sin_registro))
    with t2:
        i = f.infraestructura or {}
        ancla = todos.set_index("municipio_sk").nombre.get(int(i.get("ancla_cercana_sk") or 0), "—")
        a, b = st.columns(2)
        a.metric("Ancla más cercana", f"{i.get('min_ancla_cercana', 0):.0f} min", ancla, delta_color="off")
        b.metric("A la capital", f"{i.get('min_capital', 0):.0f} min")
        a.metric("Hospedajes", f"{i.get('unidades_hospedaje', 0):.0f}")
        b.metric("Restaurantes", f"{i.get('unidades_alimentos', 0):.0f}")
        a.metric("Vías principales", f"{i.get('km_vias_por_km2', 0):.2f} km/km²")
        b.metric("Viviendas con internet", f"{i.get('pct_viviendas_internet', 0):.0f} %")
        st.caption(f"⛽ {i.get('gasolineras', 0):.0f} gasolineras · 🏦 {i.get('bancos', 0):.0f} bancos · "
                   f"💊 {i.get('farmacias', 0):.0f} farmacias · 🏥 {i.get('unidades_salud', 0):.0f} salud · "
                   f"🚌 {i.get('terminales_autobus', 0):.0f} terminales · 📍 {i.get('atractivos_osm', 0):.0f} atractivos OSM · "
                   f"{i.get('municipios_colindantes', 0):.0f} municipios vecinos. Tiempos estimados en línea recta × factor de rodeo.")
    with t3:
        meses = f.temporada_meses or [0] * 12
        fuertes = set(f.meses_fuertes or [])
        colores = ["#E9EEF5", "#BFD4EE", "#5C8FD6", "#1B3F8B"]
        celdas = "".join(
            f"<div style='flex:1;text-align:center'><div style='height:{14 + 12 * v}px;background:{colores[v]};"
            f"border-radius:5px;{'outline:2px solid #E8B10D;' if (k + 1) in fuertes else ''}'></div>"
            f"<small>{fb.MESES[k]}</small></div>" for k, v in enumerate(meses))
        st.markdown(f"<div style='display:flex;gap:4px;align-items:flex-end'>{celdas}</div>", unsafe_allow_html=True)
        st.caption("Altura = intensidad (vacaciones nacionales + temporadas de sus actividades + eventos propios). "
                   "Contorno amarillo = mes fuerte propio del municipio.")
        for e in f.eventos or []:
            rango = fb.MESES_LARGO[e["mes_inicio"] - 1] + (
                "" if e["mes_inicio"] == e["mes_fin"] else f"–{fb.MESES_LARGO[e['mes_fin'] - 1]}")
            liga = f" · [fuente]({e['url']})" if e.get("url") else ""
            st.markdown(f"- **{e['nombre']}** ({rango}) · {e.get('notas') or ''}{liga}")
    with t4:
        if f.rutas_existentes:
            st.markdown("**Rutas oficiales que lo incluyen**")
            for r in f.rutas_existentes:
                st.markdown(f"- {r}")
        else:
            st.caption("No aparece en las 29 rutas oficiales: candidato a rutas nuevas.")
        if f.rutas_propuestas:
            st.markdown("**Rutas propuestas por el modelo**")
            for r in f.rutas_propuestas:
                st.markdown(f"- {r}")
        for b in f.banderas or []:
            st.markdown(f'<span class="mope-tag flag">{b["codigo"]}</span> {b.get("motivo") or ""}',
                        unsafe_allow_html=True)
        if not f.banderas:
            st.caption("Banderas de oportunidad: se llenan cuando se calcule el índice (fact_flag_oportunidad).")
