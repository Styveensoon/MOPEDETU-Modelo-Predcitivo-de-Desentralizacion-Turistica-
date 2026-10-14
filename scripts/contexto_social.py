"""Construye la entrada de fact_contexto_social para los 217 municipios de Puebla.

Fuente única: Índice de Marginación por municipio 2020 de CONAPO (datos.gob.mx), que trae
la población total del Censo de Población y Vivienda 2020 (INEGI) junto con el índice y el
grado de marginación. Periodo: "Censo Pob 2020".

Pobreza municipal: la medición municipal más reciente sigue siendo la de 2020 (CONEVAL);
la medición 2024 que publicó INEGI en 2025 es nacional y estatal. Por eso no se agrega aquí.

Uso:
    python scripts/contexto_social.py
Salidas:
    data/stg/contexto_social.csv
    data/stg/dim_fuente_contexto_social.csv
"""

import csv
import urllib.request
from datetime import date
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
RAW = RAIZ / "data" / "raw" / "social"
STG = RAIZ / "data" / "stg"

ENTIDAD = "21"
PERIODO = "Censo Pob 2020"
URL_IMM = ("https://www.datos.gob.mx/dataset/d8f2a534-bcee-4114-853d-82982a81ce24/resource/"
           "551d8f48-5d0c-4d11-964a-e2911f732615/download/imm_2020-3.csv")
LICENCIA = "Libre uso MX (datos.gob.mx): https://datos.gob.mx/libreusomx"


def descargar(url: str, destino: Path) -> Path:
    if not destino.exists():
        destino.parent.mkdir(parents=True, exist_ok=True)
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=300) as r, open(destino, "wb") as f:
            f.write(r.read())
    return destino


def main():
    ruta = descargar(URL_IMM, RAW / "imm_2020.csv")
    with open(ruta, encoding="utf-8-sig") as f:
        filas = [r for r in csv.DictReader(f) if r["CVE_ENT"].strip() == ENTIDAD]

    STG.mkdir(parents=True, exist_ok=True)
    with open(STG / "contexto_social.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["cve_geo", "nom_mun", "periodo", "poblacion_total",
                    "indice_marginacion", "grado_marginacion", "indice_marginacion_normalizado"])
        for r in sorted(filas, key=lambda r: r["CVE_MUN"].zfill(5)):
            w.writerow([r["CVE_MUN"].zfill(5), r["NOM_MUN"], PERIODO, int(r["POB_TOT"]),
                        round(float(r["IM_2020"]), 4), r["GM_2020"], round(float(r["IMN_2020"]), 4)])

    with open(STG / "dim_fuente_contexto_social.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["fuente", "version", "url", "fecha_descarga", "licencia"])
        w.writerow(["CONAPO · Índice de marginación municipal 2020",
                    "IMM 2020 (método DP2) con población total del Censo de Población y Vivienda 2020 (INEGI)",
                    URL_IMM, date.today().isoformat(), LICENCIA])

    print(f"{len(filas)} municipios de Puebla")


if __name__ == "__main__":
    main()
