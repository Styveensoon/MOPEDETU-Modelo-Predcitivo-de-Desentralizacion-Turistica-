"""Construye stg.censo_economico a partir de los Censos Económicos de INEGI (datos abiertos).

Descarga los conjuntos de datos de Puebla, toma los totales municipales (suma de estratos)
de los subsectores turísticos y los deja en formato largo:

    cve_geo, anio_censal, sector_scian, unidades, personal_ocupado, va_censal_bruto, confidencial

- cve_geo: entidad (21) + municipio (3 dígitos), texto de 5 caracteres.
- Si INEGI suprimió las variables económicas por confidencialidad, personal_ocupado y
  va_censal_bruto quedan nulos y confidencial = true. No se rellena nada.
- va_censal_bruto en millones de pesos corrientes (A131A).

Las combinaciones municipio × sector sin establecimientos no aparecen en INEGI y no se crean aquí.

El Censo 2014 no tiene conjunto de datos abiertos descargable de forma directa (solo vía SAIC).

Uso:
    python scripts/censo_economico.py
Salidas:
    data/stg/censo_economico.csv
    data/stg/dim_fuente_censos.csv
"""

import csv
import io
import urllib.request
import zipfile
from datetime import date
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
RAW = RAIZ / "data" / "raw" / "censos"
STG = RAIZ / "data" / "stg"

ENTIDAD = "21"
SECTORES = {"721", "722", "711", "712", "713", "5615"}
LICENCIA = "Términos de libre uso de la información del INEGI: https://www.inegi.org.mx/inegi/terminos.html"

CENSOS = {
    2019: {
        "url": "https://www.inegi.org.mx/contenidos/programas/ce/2019/Datosabiertos/ce2019_pue_csv.zip",
        "csv": "conjunto_de_datos/ce2019_pue.csv",
        "cols": {"ent": "ENTIDAD", "mun": "MUNICIPIO", "codigo": "CODIGO", "estrato": "ID_ESTRATO"},
        "version": "Censos Económicos 2019, resultados definitivos (datos abiertos, ref. 2018), SCIAN 2018",
    },
    2024: {
        "url": "https://www.inegi.org.mx/contenidos/programas/ce/2024/datosabiertos/conjunto_de_datos_ce_pue_2024_csv.zip",
        "csv": "conjunto_de_datos/tr_ce_pue_2024.csv",
        "cols": {"ent": "E03", "mun": "E04", "codigo": "CODIGO", "estrato": "ID_ESTRATO"},
        "version": "Censos Económicos 2024, resultados definitivos (datos abiertos, ref. 2023), SCIAN 2023",
    },
}


def descargar(url: str, destino: Path) -> Path:
    if not destino.exists():
        destino.parent.mkdir(parents=True, exist_ok=True)
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=300) as r, open(destino, "wb") as f:
            f.write(r.read())
    return destino


def _num(valor: str):
    valor = valor.strip()
    return float(valor) if valor else None


def filas_censo(anio: int, cfg: dict):
    zip_path = descargar(cfg["url"], RAW / Path(cfg["url"]).name)
    c = cfg["cols"]
    with zipfile.ZipFile(zip_path) as z, z.open(cfg["csv"]) as f:
        lector = csv.DictReader(io.TextIOWrapper(f, encoding="utf-8-sig"))
        for r in lector:
            ent, mun = r[c["ent"]].strip(), r[c["mun"]].strip()
            codigo, estrato = r[c["codigo"]].strip(), r[c["estrato"]].strip()
            if ent != ENTIDAD or not mun or estrato or codigo not in SECTORES:
                continue
            personal, va = _num(r["H001A"]), _num(r["A131A"])
            yield {
                "cve_geo": ENTIDAD + mun.zfill(3),
                "anio_censal": anio,
                "sector_scian": codigo,
                "unidades": int(float(r["UE"])),
                "personal_ocupado": None if personal is None else int(round(personal)),
                "va_censal_bruto": va,
                "confidencial": personal is None or va is None,
            }


def main():
    STG.mkdir(parents=True, exist_ok=True)
    filas = []
    for anio, cfg in CENSOS.items():
        filas.extend(filas_censo(anio, cfg))
    filas.sort(key=lambda r: (r["anio_censal"], r["cve_geo"], r["sector_scian"]))

    campos = ["cve_geo", "anio_censal", "sector_scian", "unidades", "personal_ocupado", "va_censal_bruto", "confidencial"]
    with open(STG / "censo_economico.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=campos)
        w.writeheader()
        for r in filas:
            w.writerow({k: ("" if r[k] is None else str(r[k]).lower() if k == "confidencial" else r[k]) for k in campos})

    hoy = date.today().isoformat()
    with open(STG / "dim_fuente_censos.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["fuente", "version", "url", "fecha_descarga", "licencia"])
        for anio, cfg in CENSOS.items():
            w.writerow([f"INEGI · Censos Económicos {anio}", cfg["version"], cfg["url"], hoy, LICENCIA])

    for anio in CENSOS:
        sub = [r for r in filas if r["anio_censal"] == anio]
        conf = sum(r["confidencial"] for r in sub)
        muns = len({r["cve_geo"] for r in sub})
        print(f"CE {anio}: {len(sub)} filas, {muns} municipios, {conf} confidenciales")


if __name__ == "__main__":
    main()
