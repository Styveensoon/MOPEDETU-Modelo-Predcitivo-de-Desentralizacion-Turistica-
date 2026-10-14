-- =============================================================================
-- MOPEDETU · Capa de predicción y generación de rutas nuevas
-- Se ejecuta DESPUÉS de 01_ddl_mopedetu.sql (no modifica lo existente, solo agrega).
-- Idempotente.
--
-- Lógica en dos capas:
--   Capa 1 (predicción): potencial de crecimiento por municipio y eje
--          (panel de Censos Económicos 2014 -> 2019 -> 2024).
--   Capa 2 (rutas):      optimización sobre el grafo usando ese potencial, el índice y el tiempo
--          estimado; después se clasifica cada ruta como nueva / parcialmente existente / existente
--          comparándola con un catálogo de rutas actuales.
-- =============================================================================
SET search_path = public, extensions;

-- ---------------------------------------------------------------------------
-- 1. Periodo adicional y fuente del catálogo de rutas existentes
-- ---------------------------------------------------------------------------
INSERT INTO dw.dim_periodo (etiqueta, anio, tipo) VALUES
    ('CE 2014', 2014, 'censo_economico')
ON CONFLICT (etiqueta) DO NOTHING;
-- Nota: el ETL (paso 5 de 02_etl) ya construye la etiqueta 'CE ' || anio_censal,
-- así que basta con cargar los datos de 2014 en stg.censo_economico.
-- Cuidado: 2014 usa SCIAN 2013 y 2019/2024 usan SCIAN 2018; a nivel de subsector (721, 722...)
-- la comparación es razonable, pero confírmenlo y documenten la equivalencia.

INSERT INTO dw.dim_fuente (nombre, institucion, tipo, url, uso_en_modelo) VALUES
    ('Catálogo de rutas turísticas existentes', 'Secretaría de Desarrollo Turístico y otras fuentes', 'Catálogo manual', NULL,
     'Medir la novedad de las rutas propuestas (y, opcionalmente, etiquetas para el modelo de enlaces)')
ON CONFLICT (nombre) DO NOTHING;

-- Trazabilidad de cada ruta existente: de dónde se documentó.
ALTER TABLE dw.dim_ruta ADD COLUMN IF NOT EXISTS fuente_sk smallint REFERENCES dw.dim_fuente;

-- El índice incorpora el potencial predicho como un componente más.
ALTER TABLE dw.fact_indice_oportunidad
    ADD COLUMN IF NOT EXISTS score_potencial numeric(5,4) CHECK (score_potencial BETWEEN 0 AND 1);

INSERT INTO dw.dim_version_calculo (nombre, descripcion, pesos) VALUES
    ('v2_con_prediccion', 'Índice con potencial predicho; calibrar con análisis de sensibilidad',
     '{"oferta":0.25,"potencial_predicho":0.20,"complementarios":0.10,"accesibilidad":0.25,"social":0.20}')
ON CONFLICT (nombre) DO NOTHING;

-- ---------------------------------------------------------------------------
-- 2. Registro de modelos (documentación exigida por la convocatoria:
--    configuración, variables, resultados y limitaciones)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS dw.dim_modelo (
    modelo_sk            smallint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    nombre               text NOT NULL UNIQUE,
    tarea                text NOT NULL CHECK (tarea IN ('crecimiento_municipal','enlace_municipios','linea_base')),
    algoritmo            text NOT NULL,
    variables            jsonb,                 -- lista de variables de entrada
    hiperparametros      jsonb,
    periodo_entrenamiento text,                 -- ej. 'CE 2014 -> CE 2019'
    periodo_validacion   text,                  -- ej. 'CE 2019 -> CE 2024'
    esquema_validacion   text,                  -- ej. 'temporal + dejar una región fuera'
    metricas             jsonb,                 -- ej. {"spearman":0.41,"precision_at_20":0.35,"baseline_spearman":0.28}
    explicabilidad       text,                  -- ej. importancia de variables / coeficientes
    limitaciones         text,
    creado_en            timestamptz NOT NULL DEFAULT now()
);

-- ---------------------------------------------------------------------------
-- 3. Predicciones
-- ---------------------------------------------------------------------------

-- Crecimiento esperado del personal ocupado por municipio y eje para el siguiente periodo censal.
-- Es un POTENCIAL ordenable, no una garantía ni una estimación de visitantes.
CREATE TABLE IF NOT EXISTS dw.fact_prediccion_crecimiento (
    municipio_sk          smallint NOT NULL REFERENCES dw.dim_municipio,
    eje_sk                smallint NOT NULL REFERENCES dw.dim_eje CHECK (eje_sk > 0),
    modelo_sk             smallint NOT NULL REFERENCES dw.dim_modelo,
    periodo_base_sk       smallint NOT NULL REFERENCES dw.dim_periodo,   -- datos desde los que se predice
    horizonte_anios       smallint NOT NULL DEFAULT 5,
    personal_base         numeric(12,1),
    crecimiento_pred_pct  numeric(8,2),
    intervalo_inf_pct     numeric(8,2),                                  -- p. ej. cuantil 10 %
    intervalo_sup_pct     numeric(8,2),                                  -- p. ej. cuantil 90 %
    ranking_potencial     smallint,                                      -- dentro del eje
    PRIMARY KEY (municipio_sk, eje_sk, modelo_sk, periodo_base_sk, horizonte_anios)
);

-- OPCIONAL: probabilidad de que dos municipios formen un enlace de ruta. Solo tiene sentido
-- si el catálogo de rutas existentes es lo bastante grande para usarse como etiquetas.
CREATE TABLE IF NOT EXISTS dw.fact_prediccion_enlace (
    municipio_a_sk  smallint NOT NULL REFERENCES dw.dim_municipio,
    municipio_b_sk  smallint NOT NULL REFERENCES dw.dim_municipio,
    modelo_sk       smallint NOT NULL REFERENCES dw.dim_modelo,
    probabilidad    numeric(5,4) NOT NULL CHECK (probabilidad BETWEEN 0 AND 1),
    PRIMARY KEY (municipio_a_sk, municipio_b_sk, modelo_sk),
    CHECK (municipio_a_sk < municipio_b_sk)
);

-- ---------------------------------------------------------------------------
-- 4. Evaluación de rutas (propuestas por el modelo o existentes)
--    La novedad se calcula en la vista dw.v_novedad_ruta, no se guarda aquí.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS dw.fact_ruta_evaluacion (
    ruta_sk                    integer  PRIMARY KEY REFERENCES dw.dim_ruta,
    modelo_sk                  smallint REFERENCES dw.dim_modelo,
    version_sk                 smallint REFERENCES dw.dim_version_calculo,
    tiempo_total_min           numeric(7,1),
    potencial_pred_medio_pct   numeric(8,2),
    necesidad_social_media     numeric(5,4),      -- 0 a 1, a mayor marginación mayor valor
    num_municipios_emergentes  smallint,
    puntaje_total              numeric(6,4)
);

-- ---------------------------------------------------------------------------
-- 5. Vistas
-- ---------------------------------------------------------------------------

-- Panel de entrenamiento: cada fila es un municipio x eje x transición censal.
--   crecimiento_pct : puede ser extremo si la base inicial es muy pequeña.
--   delta_log       : LN(1+final) - LN(1+inicial); más estable, recomendable como variable objetivo.
-- Transiciones incluidas: 2014->2019 y 2019->2024 (el segundo periodo incluye el efecto de la pandemia:
-- cambio de régimen que debe declararse al evaluar el modelo).
CREATE OR REPLACE VIEW dw.v_panel_crecimiento AS
SELECT a.municipio_sk,
       a.eje_sk,
       pa.anio                       AS anio_inicio,
       pb.anio                       AS anio_fin,
       a.unidades                    AS unidades_inicio,
       a.personal_ocupado            AS po_inicio,
       a.va_censal_bruto_mdp         AS va_inicio_mdp,
       b.personal_ocupado            AS po_fin,
       (a.hay_confidencial OR b.hay_confidencial) AS hay_confidencial,
       CASE WHEN a.personal_ocupado > 0
            THEN ROUND(100.0 * (b.personal_ocupado - a.personal_ocupado) / a.personal_ocupado, 2)
       END                           AS crecimiento_pct,
       ROUND((LN(1 + b.personal_ocupado) - LN(1 + a.personal_ocupado))::numeric, 4) AS delta_log
FROM dw.fact_censo_economico a
JOIN dw.dim_periodo pa ON pa.periodo_sk = a.periodo_sk AND pa.tipo = 'censo_economico'
JOIN dw.fact_censo_economico b ON b.municipio_sk = a.municipio_sk AND b.eje_sk = a.eje_sk
JOIN dw.dim_periodo pb ON pb.periodo_sk = b.periodo_sk AND pb.tipo = 'censo_economico'
WHERE (pa.anio, pb.anio) IN ((2014, 2019), (2019, 2024))
  AND a.personal_ocupado IS NOT NULL
  AND b.personal_ocupado IS NOT NULL;

-- Pares de municipios unidos por tramos consecutivos de rutas EXISTENTES (a < b).
CREATE OR REPLACE VIEW dw.v_pares_rutas_existentes AS
SELECT DISTINCT
       LEAST(p1.municipio_sk, p2.municipio_sk)    AS municipio_a_sk,
       GREATEST(p1.municipio_sk, p2.municipio_sk) AS municipio_b_sk
FROM dw.fact_ruta_parada p1
JOIN dw.fact_ruta_parada p2
  ON p2.ruta_sk = p1.ruta_sk AND p2.orden_parada = p1.orden_parada + 1
JOIN dw.dim_ruta r ON r.ruta_sk = p1.ruta_sk AND r.origen = 'existente';

-- Novedad de cada ruta frente al catálogo de rutas existentes:
--   'nueva'                  : ningún tramo coincide con una ruta existente
--   'parcialmente_existente' : algunos tramos coinciden
--   'existente'              : todos los tramos coinciden (o la ruta es del catálogo)
CREATE OR REPLACE VIEW dw.v_novedad_ruta AS
WITH tramos AS (
    SELECT p1.ruta_sk,
           LEAST(p1.municipio_sk, p2.municipio_sk)    AS a,
           GREATEST(p1.municipio_sk, p2.municipio_sk) AS b
    FROM dw.fact_ruta_parada p1
    JOIN dw.fact_ruta_parada p2
      ON p2.ruta_sk = p1.ruta_sk AND p2.orden_parada = p1.orden_parada + 1
), resumen_tramos AS (
    SELECT tr.ruta_sk,
           COUNT(*)                                             AS tramos,
           COUNT(*) FILTER (WHERE x.municipio_a_sk IS NOT NULL) AS tramos_existentes
    FROM tramos tr
    LEFT JOIN dw.v_pares_rutas_existentes x
           ON x.municipio_a_sk = tr.a AND x.municipio_b_sk = tr.b
    GROUP BY tr.ruta_sk
), munis_existentes AS (
    SELECT DISTINCT pp.municipio_sk
    FROM dw.fact_ruta_parada pp
    JOIN dw.dim_ruta rr ON rr.ruta_sk = pp.ruta_sk
    WHERE rr.origen = 'existente'
), resumen_munis AS (
    SELECT p.ruta_sk,
           COUNT(*)                                            AS municipios,
           COUNT(*) FILTER (WHERE me.municipio_sk IS NOT NULL) AS municipios_en_existentes
    FROM dw.fact_ruta_parada p
    LEFT JOIN munis_existentes me ON me.municipio_sk = p.municipio_sk
    GROUP BY p.ruta_sk
)
SELECT r.ruta_sk,
       r.nombre,
       r.origen,
       rm.municipios,
       ROUND(100.0 * rm.municipios_en_existentes / NULLIF(rm.municipios, 0), 1) AS pct_municipios_en_rutas_existentes,
       COALESCE(rt.tramos, 0)                                                   AS tramos,
       ROUND(100.0 * COALESCE(rt.tramos_existentes, 0) / NULLIF(rt.tramos, 0), 1) AS pct_tramos_existentes,
       CASE WHEN r.origen = 'existente'                    THEN 'existente'
            WHEN COALESCE(rt.tramos_existentes, 0) = 0     THEN 'nueva'
            WHEN rt.tramos_existentes = rt.tramos          THEN 'existente'
            ELSE 'parcialmente_existente'
       END AS clasificacion_novedad
FROM dw.dim_ruta r
JOIN resumen_munis rm ON rm.ruta_sk = r.ruta_sk
LEFT JOIN resumen_tramos rt ON rt.ruta_sk = r.ruta_sk;

-- ---------------------------------------------------------------------------
-- 6. Consultas de ejemplo (descomentar)
-- ---------------------------------------------------------------------------
-- Top 20 municipios por potencial predicho en un eje (último modelo cargado):
-- SELECT m.nombre, e.codigo AS eje, f.crecimiento_pred_pct, f.intervalo_inf_pct, f.intervalo_sup_pct
-- FROM dw.fact_prediccion_crecimiento f
-- JOIN dw.dim_municipio m USING (municipio_sk) JOIN dw.dim_eje e USING (eje_sk)
-- WHERE f.modelo_sk = (SELECT MAX(modelo_sk) FROM dw.dim_modelo WHERE tarea = 'crecimiento_municipal')
--   AND e.codigo = 'turismo'
-- ORDER BY f.crecimiento_pred_pct DESC LIMIT 20;

-- Rutas propuestas ordenadas por puntaje, con su novedad:
-- SELECT n.nombre, n.clasificacion_novedad, n.pct_tramos_existentes, ev.puntaje_total, ev.tiempo_total_min
-- FROM dw.v_novedad_ruta n
-- JOIN dw.fact_ruta_evaluacion ev USING (ruta_sk)
-- WHERE n.origen = 'propuesta_modelo'
-- ORDER BY ev.puntaje_total DESC;
