import html

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import bd
import ficha_bd as fb
import tema

from mapas import ETIQUETAS, POSICION  # alias y posiciones compartidos con el resto de mapas


def render():
    tema.hero("🏘️ Ficha técnica municipal",
              "Datos reales por municipio: actividades, infraestructura, temporadas y semáforos. "
              "Pasa el cursor para ver el resumen y haz clic para abrir la ficha completa.",
              ["DENUE 05/2026", "Censo 2020", "OpenStreetMap", "Sectur Puebla"])

    try:
        df = bd.ficha()
    except bd.SinDatos as e:
        st.error(f"No se pudo leer la ficha técnica: {e}. Revisa el archivo `.env` (ver `.env.example`).")
        return

    c1, c2 = st.columns([3, 1])
    dim = c1.segmented_control("Colorear el mapa por", list(fb.DIMENSIONES), default="turismo_actual",
                               format_func=lambda k: " ".join(fb.DIMENSIONES[k]), key="ft_dim") or "turismo_actual"
    nombres_fijos = c2.toggle("🏷️ Todos los nombres", value=False, key="ft_nombres")

    if st.session_state.get("ir_a_cve"):  # otras páginas abren la ficha de un municipio
        st.session_state["ft_cve"] = st.session_state.pop("ir_a_cve")
    if not st.session_state.get("ft_cve"):
        st.session_state["ft_cve"] = df.loc[df.nombre == "Cuetzalan del Progreso", "cve_geo"].iloc[0]
    actual = st.session_state["ft_cve"]

    mapa, panel = st.columns([1.55, 1])
    with mapa:
        # La llave incluye el municipio elegido: cada selección crea un mapa nuevo, sin estado de selección
        # previo en Plotly (si no, los clics alternaban entre seleccionar y deseleccionar).
        evento = st.plotly_chart(_figura(df, dim, actual, nombres_fijos), on_select="rerun",
                                 selection_mode="points", key=f"ft_mapa_{actual}_{dim}_{nombres_fijos}",
                                 config={"displayModeBar": False, "scrollZoom": True})
        _leyenda(dim)

    puntos = [p for p in (evento.selection.points if evento else []) if p.get("curve_number", 0) == 0]
    if puntos:
        clic = puntos[0].get("location") or df.cve_geo.iloc[puntos[0]["point_index"]]
        if clic != actual:
            st.session_state["ft_cve"] = clic
            st.rerun()  # redibuja ya con el contorno y la ficha del municipio clicado
    fichas = df.set_index("cve_geo")

    with panel:
        orden = df.sort_values("nombre")
        cves = orden.cve_geo.tolist()
        cve = st.selectbox("🔎 Municipio", cves, index=cves.index(actual),
                           format_func=dict(zip(orden.cve_geo, orden.nombre)).get, key=f"ft_sel_{actual}")
        if cve != actual:
            st.session_state["ft_cve"] = cve
            st.rerun()
        _ficha(fichas.loc[cve], df)


# ---------------------------------------------------------------- piezas
CORTO = {"turismo_actual": "Turismo", "infraestructura": "Infra", "oferta": "Oferta", "potencial": "Potencial",
         "social": "Social"}


def _hover(f) -> str:
    """Texto del hover nativo de Plotly (admite <b>, <br> y <span style=color>)."""
    marcas = (" ✨" if f.es_pueblo_magico else "") + (" ⚓" if f.es_ancla else "")
    acts = "<br>".join(f"{a['icono']} {html.escape(a['nombre'])}" for a in (f.actividades_principales or [])[:3]) \
        or "Sin actividad principal registrada"
    sem = "<br>".join(
        f"<span style='color:rgb{fb.COLOR[fb.nivel(f, d)]};font-size:15px'>⬤</span> <b>{CORTO[d]}</b>: "
        f"{fb.LECTURA[d][fb.nivel(f, d)]}" for d in fb.DIMENSIONES)
    meses = " · ".join(fb.MESES_LARGO[m - 1] for m in (f.meses_fuertes or [])) or "sin temporada propia"
    return (f"<b>{html.escape(f.nombre)}</b>{marcas}<br><span style='color:#c9d6ee'>{f.region}</span>"
            f"<br><br>{acts}<br><br>{sem}<br><br><span style='color:#c9d6ee'>📅 Meses fuertes: {meses}</span>")


def _figura(df: pd.DataFrame, dim: str, seleccion: str | None, nombres_fijos: bool) -> go.Figure:
    geo = bd.geo()
    props = pd.DataFrame([f["properties"] for f in geo["features"]]).set_index("cve_geo")
    niveles = list(fb.COLOR)  # verde, amarillo, rojo, gris → 0..3
    z = [niveles.index(fb.nivel(f, dim)) for _, f in df.iterrows()]
    escala = []
    for i, n in enumerate(niveles):  # escala discreta: un color sólido por nivel
        c = f"rgb{fb.COLOR[n]}"
        escala += [[i / len(niveles), c], [(i + 1) / len(niveles), c]]
    borde = ["#0E2A5C" if c == seleccion else "white" for c in df.cve_geo]
    ancho = [3 if c == seleccion else 0.6 for c in df.cve_geo]

    fig = go.Figure(go.Choropleth(
        geojson=geo, featureidkey="properties.cve_geo", locations=df.cve_geo, z=z,
        # zmin/zmax desplazados medio nivel: cada valor queda al centro de su franja de color, no en la frontera.
        zmin=-0.5, zmax=len(niveles) - 0.5, colorscale=escala, showscale=False,
        marker=dict(line=dict(color=borde, width=ancho), opacity=1),
        text=[_hover(f) for _, f in df.iterrows()], hovertemplate="%{text}<extra></extra>",
        # La selección de Plotly no debe pintar nada (atenuaba a los demás municipios);
        # el municipio elegido se marca solo con el contorno azul de `borde`.
        selected=dict(marker=dict(opacity=1)), unselected=dict(marker=dict(opacity=1)),
    ))

    # Nombres: anclas siempre; todos los municipios con el interruptor.
    # (selected = unselected para que Plotly no atenúe los nombres al seleccionar un municipio)
    if nombres_fijos:
        t = props.loc[df.cve_geo]
        f8 = dict(size=8, color="#14213D")
        fig.add_trace(go.Scattergeo(lon=t.lon, lat=t.lat, text=t.nombre, mode="text", hoverinfo="skip",
                                    textfont=f8, selected=dict(textfont=dict(color=f8["color"])),
                                    unselected=dict(textfont=dict(color=f8["color"]))))
    anc = props.loc[df[df.es_ancla].cve_geo].copy()
    anc["nombre"] = [ETIQUETAS.get(c, n) for c, n in zip(anc.index, anc.nombre)]
    anc = anc[anc.nombre.notna()]
    fig.add_trace(go.Scattergeo(lon=anc.lon, lat=anc.lat, text=anc.nombre, mode="text", hoverinfo="skip",
                                textfont=dict(size=12, color="#0E2A5C", family="Arial Black, Source Sans Pro"),
                                textposition=[POSICION.get(c, "middle center") for c in anc.index],
                                selected=dict(textfont=dict(color="#0E2A5C")),
                                unselected=dict(textfont=dict(color="#0E2A5C"))))

    fig.update_geos(fitbounds="locations", visible=False, projection_type="mercator", bgcolor="rgba(0,0,0,0)")
    fig.update_layout(
        height=700, margin=dict(l=0, r=0, t=0, b=0), paper_bgcolor="rgba(0,0,0,0)", showlegend=False,
        dragmode="pan",
        hoverlabel=dict(bgcolor="#0E2A5C", bordercolor="#E8B10D", align="left",
                        font=dict(color="white", size=13, family="Source Sans Pro, Segoe UI, Arial")),
    )
    return fig


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

    t0, t1, t5, t2, t6, t3, t4 = st.tabs(["📊 Índice y predicción", "🎯 Actividades", "📍 Qué visitar",
                                          "🛣️ Infraestructura", "🛡️ Seguridad y visibilidad", "📅 Temporadas",
                                          "🧭 Rutas y banderas"])
    with t0:
        _indice_y_prediccion(f)
    with t5:
        _que_visitar(f)
    with t6:
        _seguridad_visibilidad(f)
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
        atractivos = getattr(f, "atractivos", None) or []
        if atractivos:
            st.markdown("**📍 Lugares para visitar**")
            filas = []
            for a in atractivos[:12]:
                nom = html.escape(a["nombre"])
                nom = f"<a href='{html.escape(a['url'])}' target='_blank'>{nom}</a>" if a.get("url") else nom
                desc = html.escape(a.get("descripcion") or "")
                sello = " ✅" if a.get("origen") == "catalogo_curado" else ""
                filas.append(f"<li>{nom} <span class='mope-tag'>{html.escape(a['categoria'])}</span>{sello}"
                             + (f"<br/><small style='opacity:.7'>{desc}</small>" if desc else "") + "</li>")
            st.markdown(f"<div class='mope-card'><ul style='margin:0'>{''.join(filas)}</ul></div>",
                        unsafe_allow_html=True)
            if len(atractivos) > 12:
                st.caption(f"…y {len(atractivos) - 12} más (OpenStreetMap).")
            st.caption("✅ revisado a mano con fuente · el resto viene de OpenStreetMap")
    with t2:
        i = f.infraestructura or {}

        def v(clave, fmt=".0f"):
            # NULL = sin dato (p. ej. cero de OSM en un municipio poco mapeado): no se muestra como 0
            x = i.get(clave)
            return "s/d" if x is None else format(x, fmt)

        ancla = todos.set_index("municipio_sk").nombre.get(int(i.get("ancla_cercana_sk") or 0), "—")
        a, b = st.columns(2)
        a.metric("Ancla más cercana", f"{v('min_ancla_cercana')} min", ancla, delta_color="off")
        b.metric("A la capital", f"{v('min_capital')} min")
        a.metric("Hospedajes", v("unidades_hospedaje"))
        b.metric("Restaurantes", v("unidades_alimentos"))
        a.metric("Vías principales", f"{v('km_vias_por_km2', '.2f')} km/km²")
        b.metric("Viviendas con internet", f"{v('pct_viviendas_internet')} %")
        st.caption(f"⛽ {v('gasolineras')} gasolineras · 🏦 {v('bancos')} bancos · "
                   f"💊 {v('farmacias')} farmacias · 🏥 {v('unidades_salud')} salud · "
                   f"🚌 {v('terminales_autobus')} terminales · 📍 {v('atractivos_osm')} atractivos OSM · "
                   f"{v('municipios_colindantes')} municipios vecinos. Tiempos por carretera desde la cabecera "
                   "(OSRM, sin tráfico); s/d = OpenStreetMap no tiene mapeado este municipio.")
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
            st.markdown(f'<span class="mope-tag flag">{fb.BANDERA.get(b["codigo"], b["codigo"])}</span> '
                        f'{html.escape(b.get("motivo") or "")}', unsafe_allow_html=True)
        if not f.banderas:
            st.caption("Sin banderas de oportunidad activas en la versión vigente del índice.")


# ---------------------------------------------------------------- secciones nuevas (§6.3)
COMPONENTES = {"oferta": ("score_oferta", "Oferta del eje"), "complementarios": ("score_complementarios", "Complementarios"),
               "accesibilidad": ("score_accesibilidad", "Accesibilidad"), "social": ("score_social", "Necesidad social"),
               "potencial_predicho": ("score_potencial", "Potencial predicho")}


def _indice_y_prediccion(f):
    vig = bd.vigente()
    idx = bd.indice_municipio().set_index("municipio_sk")
    det = bd.indice_detalle()
    if f.municipio_sk not in idx.index:
        st.info("Sin índice para este municipio en la versión vigente.")
        return
    r = idx.loc[f.municipio_sk]
    ejes = bd.ejes().set_index("codigo").nombre
    eje_sk = bd.ejes().set_index("codigo").eje_sk
    a, b = st.columns(2)
    a.metric("Índice de oportunidad", f"{float(r.indice_oportunidad):.3f}", f"#{int(r.ranking_estatal)} de 217",
             delta_color="off")
    b.metric("Eje líder", ejes.get(r.eje_lider, r.eje_lider))

    # ¿Por qué este índice? peso × componente del eje líder, con los pesos de la versión vigente
    fila = det[(det.municipio_sk == f.municipio_sk) & (det.eje_sk == eje_sk[r.eje_lider])]
    pesos = vig["pesos_indice"] or {}
    if len(fila):
        fila = fila.iloc[0]
        sin_pot = pd.isna(fila.get("score_potencial"))
        total = sum(pesos.values())
        factor = total / (total - pesos.get("potencial_predicho", 0)) if sin_pot else 1.0
        aportes = [(nombre, pesos[k] * float(fila[col]) * factor) for k, (col, nombre) in COMPONENTES.items()
                   if k in pesos and pd.notna(fila.get(col))]
        fig = go.Figure(go.Waterfall(orientation="h", y=[n for n, _ in aportes] + ["Índice"],
                                     x=[v for _, v in aportes] + [0], measure=["relative"] * len(aportes) + ["total"],
                                     text=[f"{v:.3f}" for _, v in aportes] + [f"{float(r.indice_oportunidad):.3f}"],
                                     connector=dict(line=dict(color="#c9d6ee")),
                                     increasing=dict(marker=dict(color=tema.COBALTO)),
                                     totals=dict(marker=dict(color=tema.AMARILLO))))
        fig.update_layout(height=260, margin=dict(l=0, r=0, t=10, b=0), showlegend=False)
        st.markdown("**¿Por qué este índice?** (peso × componente del eje líder)")
        st.plotly_chart(fig, config={"displayModeBar": False}, key=f"ft_cascada_{f.municipio_sk}")
        nota = (" Sin predicción en dominio: el peso del potencial se repartió entre los demás componentes."
                if sin_pot else "")
        st.caption(f"Versión `{vig['version_indice']}` · pesos {', '.join(f'{k} {v}' for k, v in pesos.items())}.{nota}")

    st.markdown(f"**📈 Crecimiento esperado de la oferta a 5 años** · modelo `{vig['modelo']}`")
    filas = []
    for p in f.prediccion or []:
        if p.get("en_dominio"):
            txt = f"{p['crecimiento_pct']:+.0f} % (80 %: {p['inf_pct']:+.0f} a {p['sup_pct']:+.0f} %)"
        else:
            txt = f"sin predicción · {p.get('motivo') or 'fuera del dominio del modelo'}"
        filas.append({"Eje": p["eje_nombre"], "Unidades base (CE 2024)": p.get("unidades_base"), "Predicción": txt})
    if filas:
        st.dataframe(pd.DataFrame(filas), hide_index=True, width="stretch")
    st.caption("Escenario tendencial (no compromiso). Con menos de 3 unidades en el eje el modelo no predice: queda "
               "fuera del rango con el que se entrenó.")

    exc = [e for e in (f.exceso_oferta or []) if e["eje"] != "global"]
    if exc:
        st.markdown("**Oferta en exceso de lo que explica la población** (proxy de turismo)")
        st.dataframe(pd.DataFrame([{"Eje": ejes.get(e["eje"], e["eje"]), "Personal estimado": e["personal"],
                                    "Esperado por población": e["esperado"], "Exceso (%)": e["exceso_pct"],
                                    "Percentil": e["percentil"]} for e in exc]),
                     hide_index=True, width="stretch",
                     column_config={"Percentil": st.column_config.ProgressColumn(min_value=0, max_value=1, format="%.2f"),
                                    "Exceso (%)": st.column_config.NumberColumn(format="%+.0f %%")})


def _que_visitar(f):
    apt = bd.aptitud_circuitos().set_index("municipio_sk")
    if f.municipio_sk in apt.index:
        a = apt.loc[f.municipio_sk]
        if bool(a.apto):
            col1, col2 = st.columns([3, 1])
            col1.success(f"🔁 Apto para circuito (potencial {float(a.potencial_circuito):.2f})")
            if col2.button("Ver circuito", key=f"ft_circ_{f.municipio_sk}"):
                st.session_state["ir_a_circuito"] = int(f.municipio_sk)
                st.switch_page(st.session_state["paginas"]["circuitos"])
        else:
            st.info(f"🔁 Sin circuito: {a.motivo_no_apto}. Puede ser parada de una ruta intermunicipal.")
    lug = bd.lugares(int(f.municipio_sk))
    vis = lug[lug.tipo_parada.isin(["atractivo", "experiencia"])]
    com = lug[lug.tipo_parada == "comida"]
    a, b, c = st.columns(3)
    a.metric("Atractivos", int((lug.tipo_parada == "atractivo").sum()))
    b.metric("Experiencias", int((lug.tipo_parada == "experiencia").sum()), help="Talleres, productores, viveros")
    c.metric("Cocina tradicional", len(com))
    if vis.empty:
        st.info("Sin puntos visitables registrados (ni lugares con nombre ni negocios de atractivo o experiencia).")
        return
    origen = {"curado": "✅ revisado con fuente", "osm": "OpenStreetMap", "denue": "DENUE"}
    st.dataframe(pd.DataFrame({
        "Lugar": vis.nombre, "Tipo": vis.tipo_parada, "Categoría": vis.categoria.fillna("—"),
        "Actividad": vis.actividad.fillna("—"), "Fuente": vis.origen.map(origen),
        "Ubicado": vis.lat.notna().map({True: "📍", False: "sin coordenadas"})}).head(40),
        hide_index=True, width="stretch")
    st.caption(f"{len(vis)} puntos visitables (máx. 40 en la tabla), ordenados por prioridad: curados, lugares con "
               "actividad, museos y recreación, experiencias. Fuente: dw.v_lugar_circuito.")


def _seguridad_visibilidad(f):
    s = f.seguridad if isinstance(f.seguridad, dict) else None
    if s:
        st.markdown(f"**🛡️ Seguridad · SESNSP {s['anio']}** (por 100 mil habitantes)")
        a, b = st.columns(2)
        a.metric("Delitos en el municipio", f"{s['tasa_municipio']:,.0f}",
                 f"percentil {s['percentil_municipio']:.0%} estatal", delta_color="off",
                 help="Homicidio + secuestro/extorsión + robo a transeúnte y en transporte")
        b.metric("Robo en carretera", f"{s['tasa_carretera']:,.0f}", f"percentil {s['percentil_carretera']:.0%} estatal",
                 delta_color="off", help="Robo a transportista: lo pone la autopista que cruza el municipio")
        st.caption(f"{s['nota']}. Es un dato para planear rutas, no una etiqueta del municipio.")
    else:
        st.caption("Sin datos de seguridad.")
    v = f.visibilidad if isinstance(f.visibilidad, dict) else None
    if v:
        st.markdown("**👀 Visibilidad en Wikipedia** (12 meses)")
        st.metric("Vistas de sus artículos", f"{v['vistas']:,.0f}", f"percentil {v['percentil']:.0%} estatal",
                  delta_color="off")
        titulos = " · ".join(f"[{t.replace('_', ' ')}](https://es.wikipedia.org/wiki/{t})"
                             for t in (v.get("titulo") or "").split(" + ") if t)
        st.caption(f"Artículos: {titulos}. Proxy de interés, no de visitantes ({v['periodo_inicio']} a {v['periodo_fin']}).")
