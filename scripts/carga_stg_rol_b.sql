-- Carga a staging de las entregas del rol B (contexto social y modelo predictivo).
-- Ejecutar desde la raíz del repo, después de:
--   python scripts/contexto_social.py
--   python model/prediccion_crecimiento.py
--   psql "$DATABASE_URL" -f scripts/carga_stg_rol_b.sql
-- El paso a dw (municipio_sk, eje_sk, modelo_sk, periodo_base_sk) se hace con las dimensiones de
-- 01_ddl / 03_ddl: ver el bloque final, que hay que ajustar a los nombres reales de columnas.

CREATE SCHEMA IF NOT EXISTS stg;

-- Contexto social (CONAPO 2020 + población Censo 2020) ------------------------------------
CREATE TABLE IF NOT EXISTS stg.contexto_social (
    cve_geo                        CHAR(5)      PRIMARY KEY,
    nom_mun                        VARCHAR(120),
    periodo                        VARCHAR(40)  NOT NULL,
    poblacion_total                INTEGER,
    indice_marginacion             NUMERIC(10,4),
    grado_marginacion              VARCHAR(20),
    indice_marginacion_normalizado NUMERIC(10,4)
);
TRUNCATE stg.contexto_social;
\copy stg.contexto_social FROM 'data/stg/contexto_social.csv' WITH (FORMAT csv, HEADER true, NULL '')

-- Modelos y líneas base -----------------------------------------------------------------
CREATE TABLE IF NOT EXISTS stg.dim_modelo (
    nombre                 VARCHAR(80) PRIMARY KEY,
    tarea                  VARCHAR(40),
    algoritmo              TEXT,
    en_uso                 BOOLEAN,
    objetivo               TEXT,
    variables              JSONB,
    hiperparametros        JSONB,
    intervalos             TEXT,
    periodo_entrenamiento  TEXT,
    periodo_validacion     TEXT,
    metricas               JSONB,
    explicabilidad         JSONB,
    limitaciones           TEXT
);
TRUNCATE stg.dim_modelo;
CREATE TEMP TABLE tmp_dim_modelo (LIKE stg.dim_modelo);
ALTER TABLE tmp_dim_modelo ALTER COLUMN variables TYPE TEXT, ALTER COLUMN explicabilidad TYPE TEXT;
\copy tmp_dim_modelo FROM 'data/modelo/dim_modelo.csv' WITH (FORMAT csv, HEADER true, NULL '')
INSERT INTO stg.dim_modelo
SELECT nombre, tarea, algoritmo, en_uso, objetivo, NULLIF(variables, '')::jsonb, hiperparametros,
       intervalos, periodo_entrenamiento, periodo_validacion, metricas, NULLIF(explicabilidad, '')::jsonb, limitaciones
FROM tmp_dim_modelo;

-- Predicción de crecimiento 2024 → siguiente censo ----------------------------------------
CREATE TABLE IF NOT EXISTS stg.prediccion_crecimiento (
    cve_geo                  CHAR(5)      NOT NULL,
    nom_mun                  VARCHAR(120),
    eje                      VARCHAR(40)  NOT NULL,
    modelo                   VARCHAR(80)  NOT NULL,
    periodo_base             VARCHAR(20)  NOT NULL,
    horizonte_anios          SMALLINT     NOT NULL,
    personal_base            INTEGER,
    base_confidencial        BOOLEAN,
    unidades_base            INTEGER,
    delta_log_pred           NUMERIC(10,4),
    crecimiento_pred_pct     NUMERIC(10,2),
    intervalo_inf_pct        NUMERIC(10,2),
    intervalo_sup_pct        NUMERIC(10,2),
    personal_pred            INTEGER,
    incremento_personal_pred INTEGER,
    ranking_potencial        INTEGER,
    PRIMARY KEY (cve_geo, eje, modelo)
);
TRUNCATE stg.prediccion_crecimiento;
\copy stg.prediccion_crecimiento FROM 'data/modelo/fact_prediccion_crecimiento.csv' WITH (FORMAT csv, HEADER true, NULL '')

SELECT 'contexto_social' AS tabla, COUNT(*) FROM stg.contexto_social
UNION ALL SELECT 'dim_modelo', COUNT(*) FROM stg.dim_modelo
UNION ALL SELECT 'prediccion_crecimiento', COUNT(*) FROM stg.prediccion_crecimiento;

-- Paso a dw (PLANTILLA: ajustar nombres de columnas a 01_ddl / 03_ddl antes de descomentar) --
-- INSERT INTO dw.fact_contexto_social (municipio_sk, tiempo_sk, poblacion_total, indice_marginacion, grado_marginacion)
-- SELECT m.municipio_sk, t.tiempo_sk, s.poblacion_total, s.indice_marginacion, s.grado_marginacion
-- FROM stg.contexto_social s
-- JOIN dw.dim_municipio m ON m.cve_geo = s.cve_geo
-- JOIN dw.dim_tiempo   t ON t.periodo = s.periodo;          -- 'Censo Pob 2020'
--
-- INSERT INTO dw.fact_prediccion_crecimiento (municipio_sk, eje_sk, modelo_sk, periodo_base_sk, horizonte_anios,
--        personal_base, crecimiento_pred_pct, intervalo_inf_pct, intervalo_sup_pct, ranking_potencial)
-- SELECT m.municipio_sk, e.eje_sk, dm.modelo_sk, t.tiempo_sk, p.horizonte_anios,
--        p.personal_base, p.crecimiento_pred_pct, p.intervalo_inf_pct, p.intervalo_sup_pct, p.ranking_potencial
-- FROM stg.prediccion_crecimiento p
-- JOIN dw.dim_municipio m  ON m.cve_geo = p.cve_geo
-- JOIN dw.dim_eje       e  ON e.clave   = p.eje              -- hospedaje, alimentos, turismo_cultura, comercio_turistico
-- JOIN dw.dim_modelo    dm ON dm.nombre = p.modelo
-- JOIN dw.dim_tiempo    t  ON t.periodo = p.periodo_base;    -- 'CE 2024'
