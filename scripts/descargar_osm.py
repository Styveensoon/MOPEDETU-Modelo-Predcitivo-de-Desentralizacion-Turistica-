"""Descarga de OpenStreetMap (Overpass) para el anillo A2: red vial principal, servicios y atractivos de Puebla.

Uso:
    python scripts/descargar_osm.py carpeta_destino
Genera vias.json (ways con geometría) y puntos.json (nodos y centros de ways con su etiqueta).
Datos © colaboradores de OpenStreetMap, licencia ODbL.
"""
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

SERVIDORES = ["https://overpass-api.de/api/interpreter", "https://overpass.kumi.systems/api/interpreter"]
AREA = 'area["ISO3166-2"="MX-PUE"]->.a;'
CONSULTAS = {
    "vias.json": AREA + 'way(area.a)["highway"~"^(motorway|trunk|primary|secondary|tertiary)(_link)?$"];out tags geom;',
    "puntos.json": AREA + """(
      nwr(area.a)["amenity"~"^(fuel|atm|bank|hospital|clinic|pharmacy|bus_station)$"];
      nwr(area.a)["tourism"~"^(hotel|motel|guest_house|hostel|camp_site|attraction|museum|viewpoint|information)$"];
      nwr(area.a)["historic"~"^(archaeological_site|monument|church|monastery|ruins)$"];
      nwr(area.a)["leisure"~"^(nature_reserve|park|water_park)$"];
    );out tags center;""",
}


def descargar(consulta: str, destino: Path):
    cuerpo = urllib.parse.urlencode({"data": "[out:json][timeout:600];" + consulta}).encode()
    for intento, url in enumerate(SERVIDORES * 2):
        try:
            req = urllib.request.Request(url, data=cuerpo, headers={"User-Agent": "MOPEDETU-hackathon/1.0"})
            with urllib.request.urlopen(req, timeout=900) as r:
                destino.write_bytes(r.read())
            print(f"✓ {destino.name}: {destino.stat().st_size / 1e6:.1f} MB ({url})")
            return
        except Exception as e:  # servidores públicos: reintentar en el otro
            print(f"… {url} falló ({e}); reintento")
            time.sleep(10 * (intento + 1))
    raise SystemExit(f"No se pudo descargar {destino.name}")


if __name__ == "__main__":
    carpeta = Path(sys.argv[1])
    carpeta.mkdir(parents=True, exist_ok=True)
    for nombre, consulta in CONSULTAS.items():
        descargar(consulta, carpeta / nombre)
