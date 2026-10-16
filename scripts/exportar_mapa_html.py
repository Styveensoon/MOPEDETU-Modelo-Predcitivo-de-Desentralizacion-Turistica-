"""Mapa HTML autocontenido para la demo sin internet (plan_migracion_front.md §12.2).

Índice de oportunidad vigente por municipio (polígonos, sin mosaicos externos), las 5 rutas del modelo con su trazo
por carretera guardado y sus paradas. plotly.js va embebido en el archivo, así que abre en cualquier navegador sin
conexión. Lee Supabase con la publishable key o, si no hay red, la copia local de data/snapshot/.

Uso: python scripts/exportar_mapa_html.py  →  docs/demo/mapa_mopedetu.html
"""
import json
import sys
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go

RAIZ = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(RAIZ / "dashboard")]

import supabase_cliente as sb  # noqa: E402

SALIDA = RAIZ / "docs" / "demo" / "mapa_mopedetu.html"
SNAP = RAIZ / "data" / "snapshot"
COLORES = ["#1B3F8B", "#8A1538", "#E8B10D", "#2E7D32", "#00897B", "#D81B60"]


def leer(tabla: str, sel: str = "*") -> pd.DataFrame:
    try:
        return sb.leer(tabla, "dw", sel)
    except Exception:  # noqa: BLE001 - sin red: copia local
        return pd.read_json(SNAP / f"{tabla}.jsonl", lines=True, dtype=False)


def main():
    geo = json.loads((RAIZ / "data" / "geo" / "puebla_municipios.geojson").read_text(encoding="utf-8"))
    idx = leer("v_indice_municipio")
    idx["cve_geo"] = idx.cve_geo.astype(str).str.zfill(5)
    rp = leer("v_ruta_parada")
    rp = rp[rp.origen == "propuesta_modelo"].sort_values(["ruta_sk", "orden_parada"])
    tr = leer("fact_ruta_evaluacion", "ruta_sk,geom_trazo")
    trazo = {int(r.ruta_sk): r.geom_trazo for r in tr.itertuples() if isinstance(r.geom_trazo, dict)}

    fig = go.Figure(go.Choropleth(
        geojson=geo, featureidkey="properties.cve_geo", locations=idx.cve_geo,
        z=idx.indice_oportunidad.astype(float).rank(pct=True), colorscale=[[0, "#FCDE70"], [0.5, "#3EAFBE"], [1, "#182878"]],
        marker_line_color="white", marker_line_width=0.5, colorbar=dict(title="Índice<br>(percentil)"),
        text=[f"<b>{n}</b><br>{r}<br>Índice {v:.3f} (#{k})" for n, r, v, k in
              zip(idx.nombre, idx.region, idx.indice_oportunidad.astype(float), idx.ranking_estatal)],
        hovertemplate="%{text}<extra></extra>", name="Índice"))
    for i, (sk, g) in enumerate(rp.groupby("ruta_sk")):
        color = COLORES[i % len(COLORES)]
        if sk in trazo:
            lon, lat = zip(*trazo[sk]["coordinates"])
        else:
            lon, lat = g.lon.astype(float), g.lat.astype(float)
        fig.add_trace(go.Scattergeo(lon=list(lon), lat=list(lat), mode="lines", line=dict(color=color, width=3.5),
                                    name=g.ruta.iat[0], hoverinfo="name"))
        fig.add_trace(go.Scattergeo(
            lon=g.lon.astype(float), lat=g.lat.astype(float), mode="markers+text", text=g.orden_parada.astype(str),
            textfont=dict(color="white", size=10), marker=dict(size=16, color=color, line=dict(color="white", width=1)),
            hovertext=[f"<b>{p.orden_parada}. {p.municipio}</b>" + (" ⚓" if p.es_ancla else "")
                       + (" 🛏️" if p.es_pernocta else "") for p in g.itertuples()],
            hoverinfo="text", showlegend=False))
    fig.update_geos(fitbounds="locations", visible=False, projection_type="mercator")
    fig.update_layout(title="MOPEDETU · Índice de oportunidad turística y rutas propuestas (Puebla)",
                      height=850, margin=dict(l=0, r=0, t=50, b=0), legend=dict(orientation="h", y=-0.02))
    SALIDA.parent.mkdir(parents=True, exist_ok=True)
    fig.write_html(SALIDA, include_plotlyjs=True, full_html=True)
    print(f"✓ {SALIDA.relative_to(RAIZ)} ({SALIDA.stat().st_size / 1e6:.1f} MB, sin dependencias externas)")


if __name__ == "__main__":
    main()
