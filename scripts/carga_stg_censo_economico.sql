-- Carga de stg.censo_economico desde data/stg/censo_economico.csv (generado por scripts/censo_economico.py).
-- Ejecutar con psql desde la raíz del repo:  psql "$DATABASE_URL" -f scripts/carga_stg_censo_economico.sql
-- Si 01_ddl_mopedetu.sql ya creó la tabla, el CREATE no hace nada.

CREATE SCHEMA IF NOT EXISTS stg;

CREATE TABLE IF NOT EXISTS stg.censo_economico (
    cve_geo          CHAR(5)       NOT NULL,
    anio_censal      SMALLINT      NOT NULL,
    sector_scian     VARCHAR(6)    NOT NULL,
    unidades         INTEGER,
    personal_ocupado INTEGER,
    va_censal_bruto  NUMERIC(14,3),   -- millones de pesos corrientes
    confidencial     BOOLEAN       NOT NULL DEFAULT FALSE,
    PRIMARY KEY (cve_geo, anio_censal, sector_scian)
);

DELETE FROM stg.censo_economico WHERE anio_censal IN (2014, 2019, 2024);

\copy stg.censo_economico (cve_geo, anio_censal, sector_scian, unidades, personal_ocupado, va_censal_bruto, confidencial) FROM 'data/stg/censo_economico.csv' WITH (FORMAT csv, HEADER true, NULL '')

SELECT anio_censal, sector_scian, COUNT(*) AS filas, SUM(unidades) AS ue,
       COUNT(*) FILTER (WHERE confidencial) AS confidenciales
FROM stg.censo_economico
GROUP BY 1, 2
ORDER BY 1, 2;
