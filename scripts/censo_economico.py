"""Construye stg.censo_economico a partir de los Censos Económicos de INEGI (datos abiertos).

Descarga los conjuntos de datos de Puebla, toma los totales municipales (suma de estratos)
de los subsectores turísticos y los deja en formato largo:

    cve_geo, anio_censal, sector_scian, unidades, personal_ocupado, va_censal_bruto, confidencial

- cve_geo: entidad (21) + municipio (3 dígitos), texto de 5 caracteres.
- Si INEGI suprimió las variables económicas por confidencialidad, personal_ocupado y
  va_censal_bruto quedan nulos y confidencial = true. No se rellena nada.
- va_censal_bruto en millones de pesos corrientes (A131A).

Las combinaciones municipio × sector sin establecimientos no aparecen en INEGI y no se crean aquí.

Se usa la versión histórica publicada con los Censos Económicos 2024, que homologa 2014, 2019 y
2024 a SCIAN 2023 y al marco geoestadístico vigente, para que las transiciones sean comparables.

Uso:
    python scripts/censo_economico.py
Salidas:
    data/stg/censo_economico.csv
    data/stg/censo_economico_totales.csv  (auxiliar: totales estatales por sector, cve_geo 21000,
                                           y total de actividades por municipio, sector TOTAL)
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
TOTAL = "TOTAL"  # todas las actividades económicas
LICENCIA = "Términos de libre uso de la información del INEGI: https://www.inegi.org.mx/inegi/terminos.html"

# Versión histórica de los Censos Económicos 2024: las tres ediciones homologadas a SCIAN 2023
# y al marco geoestadístico vigente, con la misma estructura de columnas.
BASE_URL = "https://www.inegi.org.mx/contenidos/programas/ce/2024/datosabiertos"
CENSOS = {
    anio: {
        "url": f"{BASE_URL}/conjunto_de_datos_ce_pue_{anio}_csv.zip",
        "csv": f"conjunto_de_datos/tr_ce_pue_{anio}.csv",
        "version": f"Censos Económicos {anio} (ref. {anio - 1}), versión histórica CE 2024 homologada a SCIAN 2023",
    }
    for anio in (2014, 2019, 2024)
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
    with zipfile.ZipFile(zip_path) as z, z.open(cfg["csv"]) as f:
        lector = csv.DictReader(io.TextIOWrapper(f, encoding="utf-8-sig"))
        for r in lector:
            ent, mun = r["E03"].strip(), r["E04"].strip()
            codigo, estrato = r["CODIGO"].strip(), r["ID_ESTRATO"].strip()
            if r["SECTOR"].strip() == "" and codigo == "TOTAL DE SECTOR":
                codigo = TOTAL
            if ent != ENTIDAD or estrato or codigo not in SECTORES | {TOTAL}:
                continue
            personal, va = _num(r["H001A"]), _num(r["A131A"])
            yield {
                "cve_geo": ENTIDAD + (mun.zfill(3) if mun else "000"),
                "anio_censal": anio,
                "sector_scian": codigo,
                "unidades": int(float(r["UE"])),
                "personal_ocupado": None if personal is None else int(round(personal)),
                "va_censal_bruto": va,
                "confidencial": personal is None or va is None,
            }


def escribir(ruta: Path, filas: list[dict]):
    campos = ["cve_geo", "anio_censal", "sector_scian", "unidades", "personal_ocupado", "va_censal_bruto", "confidencial"]
    with open(ruta, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=campos)
        w.writeheader()
        for r in filas:
            w.writerow({k: ("" if r[k] is None else str(r[k]).lower() if k == "confidencial" else r[k]) for k in campos})


def main():
    STG.mkdir(parents=True, exist_ok=True)
    todas = []
    for anio, cfg in CENSOS.items():
        todas.extend(filas_censo(anio, cfg))
    todas.sort(key=lambda r: (r["anio_censal"], r["cve_geo"], r["sector_scian"]))

    # stg.censo_economico: municipio × censo × sector turístico
    filas = [r for r in todas if not r["cve_geo"].endswith("000") and r["sector_scian"] != TOTAL]
    escribir(STG / "censo_economico.csv", filas)
    # Auxiliar para el modelo: totales estatales por sector y total de actividades por municipio
    escribir(STG / "censo_economico_totales.csv", [r for r in todas if r not in filas])

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
