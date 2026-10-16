"""Mapa de navegación para circuitos: satélite con calles, ruta real y recorrido animado tipo Waze.

La ruta se pide a OSRM sobre OpenStreetMap (servidor de FOSSGIS, con perfiles en auto y a pie; el
demo de project-osrm.org queda de respaldo para auto). Si no hay conexión se dibujan tramos rectos.
El mapa es MapLibre GL dentro de un componente HTML: mosaicos satelitales de Esri con las capas de
referencia de vías y lugares encima (como la vista híbrida de Google Maps), mapa de calles de Esri
y relieve 3D de los Terrain Tiles de AWS.

Uso:
    r = navegacion.ruta(((lat, lon), ...), "auto")      # None si el servicio no responde
    navegacion.mapa(inicio, paradas, r, [limite], alto=640)
"""

from __future__ import annotations

import json
import math

import requests
import streamlit as st
import streamlit.components.v1 as components

SERVIDORES = {
    "auto": ["https://routing.openstreetmap.de/routed-car/route/v1/driving/",
             "https://router.project-osrm.org/route/v1/driving/"],
    "pie": ["https://routing.openstreetmap.de/routed-foot/route/v1/driving/"],
}
MODO_GOOGLE = {"auto": "driving", "pie": "walking"}
GIROS = {"uturn": ("Da vuelta en U", "↶"), "sharp right": ("Gira cerrado a la derecha", "↱"),
         "right": ("Gira a la derecha", "↱"), "slight right": ("Mantente a la derecha", "↗"),
         "straight": ("Sigue derecho", "↑"), "slight left": ("Mantente a la izquierda", "↖"),
         "left": ("Gira a la izquierda", "↰"), "sharp left": ("Gira cerrado a la izquierda", "↰")}


def km_entre(a, b) -> float:
    """Distancia en km entre (lat, lon)."""
    la1, lo1, la2, lo2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 6371 * 2 * math.asin(math.sqrt(h))


def _instruccion(paso: dict, tramo: int) -> tuple[str, str]:
    m, calle = paso["maneuver"], paso.get("name") or ""
    tipo, mod = m["type"], m.get("modifier", "straight")
    por = f" por {calle}" if calle else ""
    if tipo == "depart":
        return ("Sal de la cabecera" if tramo == 0 else f"Sal hacia la parada {tramo + 1}") + por, "🚩"
    if tipo == "arrive":
        return f"Llegas a la parada {tramo + 1}", "📍"
    if tipo in ("roundabout", "rotary", "roundabout turn"):
        salida = m.get("exit")
        return (f"En la glorieta toma la {salida}.ª salida" if salida else "Entra a la glorieta") + por, "⟳"
    texto, flecha = GIROS.get(mod, ("Continúa", "↑"))
    if tipo in ("continue", "new name", "notification") and mod == "straight":
        texto = "Continúa"
    elif tipo == "end of road":
        texto = "Al final de la calle, " + texto[0].lower() + texto[1:]
    elif tipo == "fork":
        texto = texto.replace("Gira", "En la bifurcación, ve")
    return texto + por, flecha


@st.cache_data(ttl=86400, show_spinner="Trazando la ruta por las calles…")
def ruta(puntos: tuple[tuple[float, float], ...], perfil: str = "auto") -> dict | None:
    """Ruta por calles que pasa por `puntos` (lat, lon) en orden. Devuelve geometría [lon, lat],
    km y minutos totales y por tramo, indicaciones con su posición relativa (`f` de 0 a 1) y el punto
    de la calle donde se engancha cada parada."""
    coords = ";".join(f"{lon:.6f},{lat:.6f}" for lat, lon in puntos)
    for base in SERVIDORES[perfil]:
        try:
            r = requests.get(f"{base}{coords}", params=dict(overview="full", geometries="geojson", steps="true"),
                             timeout=8, headers={"User-Agent": "MOPEDETU-tablero/1.0"})
            j = r.json()
        except (requests.RequestException, ValueError):
            continue
        if j.get("code") != "Ok" or not j.get("routes"):
            continue
        rt = j["routes"][0]
        total = max(rt["distance"], 1)
        pasos, recorrido, cortes = [], 0.0, []
        for i, tramo in enumerate(rt["legs"]):
            for p in tramo["steps"]:
                if p["maneuver"]["type"] != "arrive" and p["distance"] < 1:
                    continue
                texto, flecha = _instruccion(p, i)
                pasos.append(dict(texto=texto, flecha=flecha, km=p["distance"] / 1000, f=recorrido / total,
                                  lon=p["maneuver"]["location"][0], lat=p["maneuver"]["location"][1], tramo=i))
                recorrido += p["distance"]
            cortes.append(min(recorrido / total, 1.0))
        return dict(coords=rt["geometry"]["coordinates"], km=rt["distance"] / 1000, min=rt["duration"] / 60,
                    tramos=[dict(km=t["distance"] / 1000, min=t["duration"] / 60) for t in rt["legs"]],
                    cortes=cortes, pasos=pasos, enganches=[w["location"] for w in j["waypoints"]], real=True)
    return None


def ruta_guardada(geom: dict, puntos, kms: list[float], minutos: list[float]) -> dict:
    """Ruta a partir del trazo por carretera guardado por el pipeline (fact_ruta_evaluacion.geom_trazo) y los
    tiempos por tramo de la base: no llama a ningún servicio en vivo. Sin indicaciones paso a paso."""
    total = max(sum(kms), 1e-6)
    cortes = [sum(kms[:i + 1]) / total for i in range(len(kms))]
    return dict(coords=geom["coordinates"], km=float(sum(kms)), min=float(sum(minutos)),
                tramos=[dict(km=float(k), min=float(m)) for k, m in zip(kms, minutos)], cortes=cortes, pasos=[],
                enganches=[[lon, lat] for lat, lon in puntos], real=True)


def ruta_recta(puntos, minutos) -> dict:
    """Respaldo sin servicio: tramos rectos con los tiempos estimados por el motor."""
    kms = [km_entre(a, b) for a, b in zip(puntos, puntos[1:])]
    total = max(sum(kms), 1e-6)
    cortes = [sum(kms[:i + 1]) / total for i in range(len(kms))]
    return dict(coords=[[lon, lat] for lat, lon in puntos], km=sum(kms), min=float(sum(minutos)),
                tramos=[dict(km=k, min=float(m)) for k, m in zip(kms, minutos)], cortes=cortes, pasos=[],
                enganches=[[lon, lat] for lat, lon in puntos], real=False)


def indicaciones(r: dict, nombres: list[str], minutos: list[float]):
    """Lista de indicaciones agrupada por tramo. `nombres` = nombre de cada punto (inicio incluido)."""
    if not r["pasos"]:
        return
    with st.expander(f"🧭 Indicaciones paso a paso ({len(r['pasos'])})"):
        grupos: dict[int, list] = {}
        for p in r["pasos"]:
            grupos.setdefault(p["tramo"], []).append(p)
        for tramo, pasos in grupos.items():
            st.markdown(f"**{nombres[tramo]} → {tramo + 1}. {nombres[tramo + 1]}** · {minutos[tramo]:.0f} min")
            st.markdown("\n".join(f"- {p['flecha']} {p['texto']}" + (f" · {p['km']:.1f} km" if p["km"] >= 1 else
                                                                     f" · {p['km'] * 1000:.0f} m" if p["km"] > 0 else "")
                                  for p in pasos))


def enlace_google(puntos, perfil: str) -> str:
    """Ruta completa en Google Maps (admite hasta 9 paradas intermedias)."""
    ll = [f"{lat:.6f},{lon:.6f}" for lat, lon in puntos]
    medio = "|".join(ll[1:-1][:9])
    return (f"https://www.google.com/maps/dir/?api=1&origin={ll[0]}&destination={ll[-1]}"
            f"&travelmode={MODO_GOOGLE[perfil]}" + (f"&waypoints={medio}" if medio else ""))


def enlace_waze(lat: float, lon: float) -> str:
    return f"https://waze.com/ul?ll={lat:.6f},{lon:.6f}&navigate=yes"


def mapa(inicio: dict, paradas: list[dict], r: dict, limites: list[dict], perfil: str = "auto", alto: int = 640):
    """Dibuja el mapa. `inicio` = {lon, lat, nombre}; cada parada = {lon, lat, nombre, actividad, icono,
    color, orden, hora} y opcionales `valoracion` y `detalle`; `limites` = geometrías GeoJSON de los
    municipios que se contornean."""
    for p, f in zip(paradas, r["cortes"]):
        p["f"] = f
    accesos = [[[p["lon"], p["lat"]], e] for p, e in zip([inicio] + paradas, r["enganches"])
               if km_entre((p["lat"], p["lon"]), (e[1], e[0])) > 0.015]
    datos = dict(inicio=inicio, paradas=paradas, ruta=r["coords"], pasos=r["pasos"], km=r["km"], min=r["min"],
                 real=r["real"], accesos=accesos, limites=limites, perfil=perfil)
    js = json.dumps(datos, ensure_ascii=False).replace("</", "<\\/")
    pagina = PLANTILLA.replace("__DATOS__", js)
    if hasattr(st, "iframe"):  # components.v1.html quedó obsoleto en Streamlit reciente
        st.iframe(pagina, height=alto)
    else:
        components.html(pagina, height=alto)


PLANTILLA = r"""<!doctype html>
<html><head><meta charset="utf-8">
<link href="https://unpkg.com/maplibre-gl@4.7.1/dist/maplibre-gl.css" rel="stylesheet">
<script src="https://unpkg.com/maplibre-gl@4.7.1/dist/maplibre-gl-csp.js"></script>
<style>
html,body{margin:0;height:100%;background:transparent;font-family:"Source Sans Pro","Segoe UI",Arial,sans-serif}
#mapa{position:absolute;inset:0;border-radius:16px;overflow:hidden;background:#5d6b57}
.panel{position:absolute;z-index:3;background:rgba(14,42,92,.9);color:#fff;border-radius:12px;
  box-shadow:0 4px 18px rgba(0,0,0,.35);backdrop-filter:blur(4px)}
#controles{top:10px;left:10px;padding:7px;display:flex;flex-wrap:wrap;gap:5px;max-width:calc(100% - 70px)}
.b{background:rgba(255,255,255,.12);color:#fff;border:1px solid rgba(255,255,255,.28);border-radius:8px;
  padding:5px 9px;font:600 13px "Source Sans Pro","Segoe UI",Arial;cursor:pointer;white-space:nowrap}
.b:hover{background:rgba(255,255,255,.24)}
.b.on{background:#fff;color:#0E2A5C;border-color:#fff}
.b.play{background:#E8B10D;color:#2b2100;border-color:#E8B10D;min-width:96px}
.sep{width:1px;background:rgba(255,255,255,.25);margin:2px 2px}
#hud{top:58px;left:10px;padding:10px 14px;display:none;width:290px}
#hud .fila{display:flex;align-items:center;gap:12px}
#hFlecha{font-size:34px;line-height:1;min-width:36px;text-align:center}
#hDist{font-size:22px;font-weight:700}
#hTxt{font-size:13.5px;opacity:.95;line-height:1.25}
#hSig{margin-top:8px;padding-top:7px;border-top:1px solid rgba(255,255,255,.2);font-size:12.5px;opacity:.85}
#estado{bottom:30px;left:50%;transform:translateX(-50%);padding:8px 16px 11px;font-size:13px;display:flex;
  gap:18px;white-space:nowrap;overflow:hidden}
#estado b{color:#E8B10D}
#barra{position:absolute;left:0;bottom:0;height:4px;width:0;background:#E8B10D}
#aviso{bottom:30px;right:10px;padding:6px 10px;font-size:12px;background:rgba(138,21,56,.92);display:none}
.parada{width:26px;height:26px;border-radius:50%;border:3px solid #fff;color:#fff;font:700 13px/26px Arial;
  text-align:center;box-shadow:0 2px 8px rgba(0,0,0,.55);cursor:pointer;transition:transform .25s,box-shadow .25s}
.parada.activa{transform:scale(1.4);box-shadow:0 0 0 7px rgba(232,177,13,.65),0 2px 8px rgba(0,0,0,.55)}
.parada.visitada::after{content:"✓";position:absolute;right:-9px;top:-9px;width:16px;height:16px;border-radius:50%;
  background:#2E7D32;font:700 10px/16px Arial;border:2px solid #fff}
.inicio{width:34px;height:34px;border-radius:50% 50% 50% 4px;transform:rotate(-45deg);background:#E8B10D;
  border:3px solid #fff;box-shadow:0 2px 8px rgba(0,0,0,.55);display:flex;align-items:center;justify-content:center}
.inicio span{transform:rotate(45deg);font-size:16px}
.maplibregl-popup-content{border-radius:10px;padding:10px 13px;font:13px/1.35 "Source Sans Pro","Segoe UI",Arial;
  box-shadow:0 4px 16px rgba(0,0,0,.3)}
.maplibregl-popup-content h4{margin:0 0 3px;font-size:14.5px;color:#0E2A5C}
.maplibregl-popup-content a{color:#1B3F8B;font-weight:600}
</style></head>
<body>
<div id="mapa"></div>
<div id="controles" class="panel">
  <button class="b play" id="bPlay">▶ Recorrer</button>
  <button class="b" id="bReset" title="Reiniciar recorrido">⟲</button>
  <button class="b" id="bVel" title="Velocidad de la animación">1×</button>
  <button class="b" id="bSeguir" title="La cámara sigue el recorrido">🎯 Seguir</button>
  <button class="b" id="bGeneral" title="Ver todo el circuito">🧭 General</button>
  <span class="sep"></span>
  <button class="b on" id="bSat">🛰️ Satélite</button>
  <button class="b" id="bCalles">🗺️ Mapa</button>
  <button class="b on" id="b3d" title="Relieve en 3D">⛰️ 3D</button>
  <button class="b" id="bFull" title="Pantalla completa">⛶</button>
</div>
<div id="hud" class="panel">
  <div class="fila"><span id="hFlecha">↑</span><div><div id="hDist"></div><div id="hTxt"></div></div></div>
  <div id="hSig"></div>
</div>
<div id="estado" class="panel"><span id="eParada"></span><span id="eKm"></span><span id="eEta"></span><div id="barra"></div></div>
<div id="aviso" class="panel">Sin servicio de rutas: tramos en línea recta</div>
<script>
const D = __DATOS__;
const WORKER = "https://unpkg.com/maplibre-gl@4.7.1/dist/maplibre-gl-csp-worker.js";

function principal() {
  const $ = id => document.getElementById(id);
  const esc = s => String(s).replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
  const ESRI = "https://server.arcgisonline.com/ArcGIS/rest/services/";
  const rgb = c => Array.isArray(c) ? `rgb(${c[0]},${c[1]},${c[2]})` : c;

  const estilo = {version: 8, sources: {
    sat: {type: "raster", tiles: [ESRI + "World_Imagery/MapServer/tile/{z}/{y}/{x}"], tileSize: 256, maxzoom: 19,
          attribution: "Imágenes © Esri, Maxar, Earthstar Geographics"},
    vias: {type: "raster", tiles: [ESRI + "Reference/World_Transportation/MapServer/tile/{z}/{y}/{x}"], tileSize: 256, maxzoom: 19},
    lugares: {type: "raster", tiles: [ESRI + "Reference/World_Boundaries_and_Places/MapServer/tile/{z}/{y}/{x}"], tileSize: 256, maxzoom: 19},
    calles: {type: "raster", tiles: [ESRI + "World_Street_Map/MapServer/tile/{z}/{y}/{x}"], tileSize: 256, maxzoom: 19,
             attribution: "Mapa © Esri, HERE, Garmin, © OpenStreetMap"},
    dem: {type: "raster-dem", tiles: ["https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png"],
          tileSize: 256, maxzoom: 14, encoding: "terrarium", attribution: "Relieve: Terrain Tiles (AWS)"}
  }, layers: [
    {id: "fondo", type: "background", paint: {"background-color": "#5d6b57"}},
    {id: "sat", type: "raster", source: "sat"},
    {id: "vias", type: "raster", source: "vias", paint: {"raster-opacity": 0.95}},
    {id: "lugares", type: "raster", source: "lugares"},
    {id: "calles", type: "raster", source: "calles", layout: {visibility: "none"}}
  ]};

  // ---------- geometría de la ruta
  const R = D.ruta.length > 1 ? D.ruta : [[D.inicio.lon, D.inicio.lat], [D.inicio.lon, D.inicio.lat]];
  const rad = x => x * Math.PI / 180;
  function hav(a, b) {
    const h = Math.sin(rad(b[1] - a[1]) / 2) ** 2 + Math.cos(rad(a[1])) * Math.cos(rad(b[1])) * Math.sin(rad(b[0] - a[0]) / 2) ** 2;
    return 12742 * Math.asin(Math.sqrt(h));
  }
  const acum = [0];
  for (let i = 1; i < R.length; i++) acum.push(acum[i - 1] + hav(R[i - 1], R[i]));
  const L = Math.max(acum[acum.length - 1], 1e-6);
  function punto(f) {
    const d = Math.min(Math.max(f, 0), 1) * L;
    let lo = 0, hi = acum.length - 1;
    while (hi - lo > 1) { const m = (lo + hi) >> 1; if (acum[m] <= d) lo = m; else hi = m; }
    const t = (d - acum[lo]) / Math.max(acum[hi] - acum[lo], 1e-9);
    return [[R[lo][0] + (R[hi][0] - R[lo][0]) * t, R[lo][1] + (R[hi][1] - R[lo][1]) * t], lo];
  }
  function rumbo(a, b) {
    const y = Math.sin(rad(b[0] - a[0])) * Math.cos(rad(b[1]));
    const x = Math.cos(rad(a[1])) * Math.sin(rad(b[1])) - Math.sin(rad(a[1])) * Math.cos(rad(b[1])) * Math.cos(rad(b[0] - a[0]));
    return (Math.atan2(y, x) * 180 / Math.PI + 360) % 360;
  }
  const mezclaAng = (a, b, t) => a + ((((b - a) % 360) + 540) % 360 - 180) * t;
  const fmtDist = km => km < 1 ? `${Math.max(10, Math.round(km * 1000 / 10) * 10)} m` : `${km.toFixed(1)} km`;
  const fmtMin = m => m < 60 ? `${Math.round(m)} min` : `${Math.floor(m / 60)} h ${Math.round(m % 60)} min`;

  // ---------- mapa
  const caja = new maplibregl.LngLatBounds();
  [D.inicio, ...D.paradas].forEach(p => caja.extend([p.lon, p.lat]));
  R.forEach(c => caja.extend(c));
  const map = new maplibregl.Map({container: "mapa", style: estilo, center: [-97.9, 19.05], zoom: 7.4, pitch: 0,
                                  maxZoom: 19, maxPitch: 75, attributionControl: {compact: true}});
  map.addControl(new maplibregl.NavigationControl({visualizePitch: true}), "top-right");
  map.addControl(new maplibregl.ScaleControl({unit: "metric"}), "bottom-left");
  map.on("error", () => {});  // mosaicos faltantes en zonas sin cobertura: se ignoran
  // MapLibre 4.7 deja congelada la elevación de la cámara al terminar un vuelo con relieve: se queda en
  // 0 m y, con el suelo serrano a 1,500 m, el circuito se ve desplazado y de cerca la cámara queda bajo
  // tierra. Se libera al terminar cada movimiento para que tome la altura real del terreno.
  map.on("moveend", () => {
    if (map.terrain && map._elevationFreeze && !map.isMoving()) { map._elevationFreeze = false; map.triggerRepaint(); }
  });
  if (!D.real) $("aviso").style.display = "block";

  const padding = {top: 70, bottom: 70, left: 50, right: 60};
  function vistaGeneral(dur = 2200) {
    seguir = false; $("bSeguir").classList.remove("on"); if (map.getLayer("lugares")) capas();
    const cam = map.cameraForBounds(caja, {padding});
    map.flyTo({...cam, zoom: Math.min(cam.zoom - 0.25, 17), pitch: terreno ? 50 : 30, bearing: -12, duration: dur, essential: true});
    map.once("moveend", () => setTimeout(() => { if (!jugando && !map.isMoving()) ajustarEncuadre(); }, 120));
  }
  // cameraForBounds no considera la altura del terreno: en la sierra el circuito quedaba pegado al
  // borde. Se mide dónde cayó realmente en pantalla y se recentra en el área libre bajo la barra.
  function ajustarEncuadre() {
    const xy = [D.inicio, ...D.paradas].map(p => [p.lon, p.lat]).concat(R.filter((_, i) => i % 8 === 0))
      .map(c => map.project(c));
    const xs = xy.map(p => p.x), ys = xy.map(p => p.y);
    const x0 = Math.min(...xs), x1 = Math.max(...xs), y0 = Math.min(...ys), y1 = Math.max(...ys);
    const c = map.getContainer(), arriba = $("controles").offsetHeight + 30, abajo = 75, lado = 55;
    const k = Math.min((c.clientWidth - 2 * lado) / Math.max(x1 - x0, 1), (c.clientHeight - arriba - abajo) / Math.max(y1 - y0, 1));
    map.easeTo({center: map.unproject([(x0 + x1) / 2, (y0 + y1) / 2]), offset: [0, (arriba - abajo) / 2],
                zoom: Math.min(map.getZoom() + Math.log2(Math.max(0.25, Math.min(k * 0.92, 2))), 17), duration: 1100});
  }

  function flechaImg() {
    const c = document.createElement("canvas"); c.width = c.height = 32;
    const g = c.getContext("2d");
    g.strokeStyle = "white"; g.lineWidth = 5; g.lineCap = "round"; g.lineJoin = "round";
    g.beginPath(); g.moveTo(11, 8); g.lineTo(21, 16); g.lineTo(11, 24); g.stroke();
    return g.getImageData(0, 0, 32, 32);
  }

  const marcas = [];
  let auto, popupActivo = null, terreno = true, relieveActivo = false, satelite = true;
  // El relieve 3D solo se dibuja en vistas amplias: a nivel de calle la cámara queda bajo el terreno
  // serrano y el mapa se ve vacío; ahí queda inclinado y plano, como un navegador.
  function actualizarRelieve() {
    const quiere = terreno && map.getZoom() < (relieveActivo ? 14.6 : 14.2);
    if (quiere !== relieveActivo) { relieveActivo = quiere; map.setTerrain(quiere ? {source: "dem", exaggeration: 1.3} : null); }
  }

  map.on("load", () => {
    actualizarRelieve();
    map.on("zoom", actualizarRelieve);
    map.on("moveend", () => { if (!jugando) capas(); });
    if (D.limites.length) {
      map.addSource("limite", {type: "geojson", data: {type: "FeatureCollection",
                                                       features: D.limites.map(g => ({type: "Feature", geometry: g}))}});
      map.addLayer({id: "limite-halo", type: "line", source: "limite", paint: {"line-color": "#fff", "line-width": 5, "line-opacity": 0.55}});
      map.addLayer({id: "limite", type: "line", source: "limite", paint: {"line-color": "#8A1538", "line-width": 2.5, "line-dasharray": [3, 2]}});
    }
    map.addSource("accesos", {type: "geojson", data: {type: "Feature", geometry: {type: "MultiLineString", coordinates: D.accesos}}});
    map.addLayer({id: "accesos", type: "line", source: "accesos", layout: {"line-cap": "round"},
                  paint: {"line-color": "#fff", "line-width": 3, "line-dasharray": [0.2, 1.8]}});
    map.addSource("ruta", {type: "geojson", data: {type: "Feature", geometry: {type: "LineString", coordinates: R}}});
    map.addLayer({id: "ruta-borde", type: "line", source: "ruta", layout: {"line-cap": "round", "line-join": "round"},
                  paint: {"line-color": "#0E2A5C", "line-width": 10}});
    map.addLayer({id: "ruta", type: "line", source: "ruta", layout: {"line-cap": "round", "line-join": "round"},
                  paint: {"line-color": "#3B8CFF", "line-width": 6}});
    map.addSource("avance", {type: "geojson", data: {type: "Feature", geometry: {type: "LineString", coordinates: [R[0], R[0]]}}});
    map.addLayer({id: "avance", type: "line", source: "avance", layout: {"line-cap": "round", "line-join": "round"},
                  paint: {"line-color": "#E8B10D", "line-width": 6}});
    map.addImage("flecha", flechaImg(), {pixelRatio: 2});
    map.addLayer({id: "flechas", type: "symbol", source: "ruta",
                  layout: {"symbol-placement": "line", "symbol-spacing": 70, "icon-image": "flecha", "icon-size": 0.75,
                           "icon-allow-overlap": true, "icon-rotation-alignment": "map"}});

    // inicio y paradas
    const ei = document.createElement("div"); ei.className = "inicio"; ei.innerHTML = "<span>⭐</span>";
    new maplibregl.Marker({element: ei, anchor: "bottom"}).setLngLat([D.inicio.lon, D.inicio.lat])
      .setPopup(new maplibregl.Popup({offset: 30, closeButton: false})
        .setHTML(`<h4>Inicio</h4>${esc(D.inicio.nombre)}<br>${esc(D.inicio.detalle || "Salida: 09:00")}`)).addTo(map);
    D.paradas.forEach(p => {
      const e = document.createElement("div"); e.className = "parada"; e.textContent = p.orden;
      e.style.background = rgb(p.color);
      const pop = new maplibregl.Popup({offset: 18, closeButton: false}).setHTML(
        `<h4>${p.orden}. ${esc(p.nombre)}</h4>${esc(p.icono)} ${esc(p.actividad)}<br>` +
        (p.detalle ? `${esc(p.detalle)}<br>` : "") + (p.valoracion != null ? `⭐ ${p.valoracion} · ` : "") + `llegada ${esc(p.hora)}` +
        `<br><a href="https://www.google.com/maps/search/?api=1&query=${p.lat},${p.lon}" target="_blank">Ver en Google Maps ↗</a>`);
      marcas.push({el: e, pop, m: new maplibregl.Marker({element: e}).setLngLat([p.lon, p.lat]).setPopup(pop).addTo(map)});
    });
    const ea = document.createElement("div");
    ea.innerHTML = `<svg viewBox="0 0 44 44" width="44" height="44"><circle cx="22" cy="22" r="20" fill="rgba(59,140,255,.28)" stroke="rgba(255,255,255,.7)" stroke-width="1.5"/>
      <path d="M22 6 L33 35 L22 28 L11 35 Z" fill="#3B8CFF" stroke="#fff" stroke-width="2.6" stroke-linejoin="round"/></svg>`;
    auto = new maplibregl.Marker({element: ea, rotationAlignment: "map", pitchAlignment: "map"}).setLngLat(R[0]);

    pintarEstado();
    setTimeout(() => vistaGeneral(4200), 350);  // vuelo de entrada desde todo el estado
  });

  // ---------- recorrido
  let f = 0, jugando = false, vel = 1, ultimo = null, pausaHasta = 0, sig = 0, seguir = true, bSuave = null;
  const durBase = Math.min(95, Math.max(32, L * (D.perfil === "pie" ? 14 : 6)));  // segundos a 1×
  const zoomSeguir = D.perfil === "pie" ? 17.6 : L > 40 ? 15.4 : 16.6;  // en carretera se ve más adelante

  function proximoPaso() {
    for (const p of D.pasos) if (p.f > f + 1e-5) return p;
    return null;
  }
  function pintarEstado() {
    const n = D.paradas.length, p = D.paradas[sig];
    $("eParada").innerHTML = p ? `Siguiente: <b>${p.orden}. ${esc(p.nombre)}</b>` : `<b>Circuito completo</b> · ${n} paradas`;
    $("eKm").innerHTML = `<b>${(f * D.km).toFixed(1)}</b> / ${D.km.toFixed(1)} km`;
    $("eEta").innerHTML = `Restan <b>${fmtMin((1 - f) * D.min)}</b> de traslado`;
    $("barra").style.width = (f * 100) + "%";
    $("hud").style.top = ($("controles").offsetHeight + 18) + "px";  // la barra puede ocupar dos renglones
    if (!jugando && f === 0) { $("hud").style.display = "none"; return; }
    $("hud").style.display = "block";
    const paso = proximoPaso();
    if (paso) {
      $("hFlecha").textContent = paso.flecha; $("hDist").textContent = fmtDist((paso.f - f) * D.km);
      $("hTxt").textContent = paso.texto;
    } else if (p) {
      $("hFlecha").textContent = "📍"; $("hDist").textContent = fmtDist((p.f - f) * D.km);
      $("hTxt").textContent = `Hacia la parada ${p.orden}`;
    } else {
      $("hFlecha").textContent = "🏁"; $("hDist").textContent = "Llegaste"; $("hTxt").textContent = "Fin del circuito";
    }
    $("hSig").innerHTML = p ? `Parada ${p.orden} de ${n}: ${esc(p.icono)} ${esc(p.nombre)}` : `${n} paradas visitadas`;
  }
  function mover() {
    const [pos, i] = punto(f);
    const delante = punto(Math.min(1, f + 0.04 / L))[0];
    if (delante[0] !== pos[0] || delante[1] !== pos[1]) {
      const b = rumbo(pos, delante);
      bSuave = bSuave === null ? b : mezclaAng(bSuave, b, 0.08);
    }
    auto.setLngLat(pos).setRotation(bSuave || 0);
    map.getSource("avance").setData({type: "Feature", geometry: {type: "LineString", coordinates: R.slice(0, i + 1).concat([pos])}});
    if (seguir) map.jumpTo({center: pos, bearing: bSuave || 0, pitch: 60, zoom: zoomSeguir});
    pintarEstado();
  }
  function llegar(k) {
    marcas.forEach((m, j) => { m.el.classList.toggle("activa", j === k); if (j < k) m.el.classList.add("visitada"); });
    if (popupActivo) popupActivo.remove();
    popupActivo = marcas[k].pop; if (!popupActivo.isOpen()) marcas[k].m.togglePopup();
  }
  function cuadro(ts) {
    if (!jugando) return;
    if (ultimo === null) ultimo = ts;
    const dt = Math.min((ts - ultimo) / 1000, 0.1); ultimo = ts;
    if (ts < pausaHasta) { requestAnimationFrame(cuadro); return; }
    if (popupActivo) { popupActivo.remove(); popupActivo = null; marcas.forEach(m => m.el.classList.remove("activa")); }
    let nf = f + dt * vel / durBase;
    const p = D.paradas[sig];
    if (p && nf >= p.f) {
      nf = p.f; f = nf; mover(); llegar(sig);
      marcas[sig].el.classList.add("visitada"); sig++;
      pausaHasta = ts + 2600 / Math.sqrt(vel);
      pintarEstado(); requestAnimationFrame(cuadro); return;
    }
    f = Math.min(nf, 1); mover();
    if (f >= 1) { detener(); pintarEstado(); return; }
    requestAnimationFrame(cuadro);
  }
  function arrancar() {
    if (f >= 1) reiniciar();
    jugando = true; ultimo = null; $("bPlay").textContent = "⏸ Pausa"; pintarEstado();
    auto.addTo(map);
    if (!seguir) { seguir = true; $("bSeguir").classList.add("on"); }
    capas();
    const [pos] = punto(f);
    if (bSuave === null) bSuave = rumbo(pos, punto(Math.min(1, f + 0.04 / L))[0]);
    map.flyTo({center: pos, zoom: zoomSeguir, pitch: 60, bearing: bSuave, duration: 2000, essential: true});
    map.once("moveend", () => { if (jugando) requestAnimationFrame(cuadro); });
  }
  function detener() { jugando = false; $("bPlay").textContent = f >= 1 ? "↻ Otra vez" : "▶ Continuar"; capas(); }
  function reiniciar() {
    detener(); f = 0; sig = 0; bSuave = null; pausaHasta = 0;
    marcas.forEach(m => m.el.classList.remove("activa", "visitada"));
    if (popupActivo) { popupActivo.remove(); popupActivo = null; }
    map.getSource("avance").setData({type: "Feature", geometry: {type: "LineString", coordinates: [R[0], R[0]]}});
    auto.remove(); $("bPlay").textContent = "▶ Recorrer"; pintarEstado();
  }

  $("bPlay").onclick = () => jugando ? detener() : arrancar();
  $("bReset").onclick = () => { reiniciar(); vistaGeneral(); };
  $("bVel").onclick = () => { vel = vel === 1 ? 2 : vel === 2 ? 4 : 1; $("bVel").textContent = vel + "×"; };
  $("bSeguir").onclick = () => {
    seguir = !seguir; $("bSeguir").classList.toggle("on", seguir); capas();
    if (seguir && f > 0) mover();
  };
  $("bGeneral").onclick = () => vistaGeneral();
  map.on("dragstart", () => { if (seguir && jugando) { seguir = false; $("bSeguir").classList.remove("on"); capas(); } });

  // Con la cámara inclinada a nivel de calle, las etiquetas de lugares lejanos (mosaicos de menor
  // zoom) se ven enormes: se ocultan al navegar o al inclinar de cerca. Los nombres de calles vienen
  // en la capa de vías y siguen visibles.
  function capas() {
    const ver = v => v ? "visible" : "none";
    map.setLayoutProperty("sat", "visibility", ver(satelite));
    map.setLayoutProperty("vias", "visibility", ver(satelite));
    const inclinadoDeCerca = map.getZoom() > 15 && map.getPitch() > 35;
    map.setLayoutProperty("lugares", "visibility", ver(satelite && !(jugando && seguir) && !inclinadoDeCerca));
    map.setLayoutProperty("calles", "visibility", ver(!satelite));
  }
  function fondo(sat) {
    satelite = sat; capas();
    $("bSat").classList.toggle("on", sat); $("bCalles").classList.toggle("on", !sat);
  }
  $("bSat").onclick = () => fondo(true);
  $("bCalles").onclick = () => fondo(false);
  $("b3d").onclick = () => {
    terreno = !terreno; $("b3d").classList.toggle("on", terreno);
    actualizarRelieve();
    map.easeTo({pitch: terreno ? Math.max(map.getPitch(), 50) : 0, duration: 800});
  };
  if (document.fullscreenEnabled) {
    $("bFull").onclick = () => document.fullscreenElement ? document.exitFullscreen() : document.documentElement.requestFullscreen();
  } else {
    $("bFull").style.display = "none";
  }
  Object.assign(window, {map, arrancar, detener, fondo, vistaGeneral,  // para depurar desde la consola
                         progreso: () => ({f, sig, jugando, relieveActivo})});
}

// Streamlit dibuja el componente en un iframe con origen "null", pero los blobs que crea heredan el
// origen de la app (http://localhost:8501). MapLibre descarta los mensajes del worker cuyo `origin`
// no coincide con `location.origin`, así que la ruta, el límite y el relieve nunca cargaban. Se usa
// la versión CSP, cuyo worker se arma aquí declarando el mismo origen que este documento.
fetch(WORKER).then(r => r.text())
  .then(t => {
    const origen = `try{Object.defineProperty(WorkerLocation.prototype,"origin",{get:()=>${JSON.stringify(location.origin)}})}catch(e){}\n`;
    maplibregl.setWorkerUrl(URL.createObjectURL(new Blob([origen, t], {type: "text/javascript"})));
  })
  .catch(() => maplibregl.setWorkerUrl(WORKER))
  .finally(principal);
</script></body></html>"""
