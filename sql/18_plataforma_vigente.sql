-- MOPEDETU · plan_migracion_front.md A2, A3, A5, §12.1 · Configuración vigente, tiempos de planeación y cabeceras
-- Idempotente.

-- 1. Parámetros del optimizador de rutas: una sola fuente de verdad para el pipeline y el tablero.
--    factor_planeacion: margen sobre los tiempos OSRM de flujo libre (sin tráfico), por región; supuesto de
--    planeación, no medición. Las restricciones de 75 y 240 min se evalúan con el tiempo de planeación.
INSERT INTO dw.dim_version_calculo (nombre, descripcion, pesos)
SELECT 'optimizador_rutas_v2', 'Parámetros del optimizador de rutas (model/reglas_rutas.py)', '{}'::jsonb
WHERE NOT EXISTS (SELECT 1 FROM dw.dim_version_calculo WHERE nombre = 'optimizador_rutas_v2');
UPDATE dw.dim_version_calculo SET pesos = jsonb_build_object(
    'max_tramo_min', 75, 'max_total_min', 240, 'min_paradas', 3, 'max_paradas', 6, 'max_paradas_usuario', 9,
    'min_emergentes', 2, 'min_hospedaje_pernocta', 10, 'horas_dia', 10,
    'estancia_ancla_h', 3, 'estancia_emergente_h', 2,
    'bono_bandera', 0.35, 'bono_social', 0.40, 'bono_tema', 0.25, 'bono_tramo_nuevo', 0.3,
    'region_excluida', 'Angelópolis',
    'banderas_no_emergente', jsonb_build_array('BARRERA_ACCESO'),
    'exigir_punto_visitable', true,
    'factor_planeacion', jsonb_build_object('Sierra Norte', 1.25, 'Sierra Nororiental', 1.25,
                                            'Tehuacán y Sierra Negra', 1.25, '_otras', 1.10),
    'n_rutas', 5, 'max_solape', 0.5, 'max_por_ancla', 2, 'max_por_tema', 2)
WHERE nombre = 'optimizador_rutas_v2';

-- 2. Qué está vigente: el tablero y las vistas leen de aquí en lugar de "la versión más alta".
INSERT INTO dw.dim_version_calculo (nombre, descripcion, pesos)
SELECT 'plataforma_vigente', 'Versiones vigentes que muestra el tablero', '{}'::jsonb
WHERE NOT EXISTS (SELECT 1 FROM dw.dim_version_calculo WHERE nombre = 'plataforma_vigente');
UPDATE dw.dim_version_calculo SET pesos = jsonb_build_object(
    'indice', 'v3_dominio_osrm', 'modelo_crecimiento', 'crecimiento_ue_eje_lgbm_v2',
    'optimizador', 'optimizador_rutas_v2', 'semaforos', 'ficha_semaforos_v1', 'periodo_oferta', 'DENUE 2026-05')
WHERE nombre = 'plataforma_vigente';

CREATE OR REPLACE VIEW dw.v_vigente WITH (security_invoker = on) AS
SELECT (SELECT version_sk FROM dw.dim_version_calculo WHERE nombre = c.pesos ->> 'indice')        AS version_indice_sk,
       c.pesos ->> 'indice'                                                                        AS version_indice,
       (SELECT modelo_sk FROM dw.dim_modelo WHERE nombre = c.pesos ->> 'modelo_crecimiento')       AS modelo_sk,
       c.pesos ->> 'modelo_crecimiento'                                                            AS modelo,
       (SELECT version_sk FROM dw.dim_version_calculo WHERE nombre = c.pesos ->> 'optimizador')   AS optimizador_sk,
       (SELECT pesos FROM dw.dim_version_calculo WHERE nombre = c.pesos ->> 'optimizador')        AS parametros_rutas,
       (SELECT version_sk FROM dw.dim_version_calculo WHERE nombre = c.pesos ->> 'semaforos')     AS semaforos_sk,
       (SELECT periodo_sk FROM dw.dim_periodo WHERE etiqueta = c.pesos ->> 'periodo_oferta')      AS periodo_oferta_sk,
       (SELECT pesos FROM dw.dim_version_calculo WHERE nombre = c.pesos ->> 'indice')             AS pesos_indice
FROM dw.dim_version_calculo c
WHERE c.nombre = 'plataforma_vigente';

-- 3. Tiempo de planeación (A3): factor de la región más lenta entre origen y destino.
CREATE OR REPLACE VIEW dw.v_tiempo_municipios WITH (security_invoker = on) AS
WITH f AS (SELECT parametros_rutas -> 'factor_planeacion' AS fp FROM dw.v_vigente)
SELECT a.municipio_origen_sk, a.municipio_destino_sk,
       COALESCE(a.tiempo_min_carretera, a.tiempo_min_est)       AS tiempo_min,
       COALESCE(a.distancia_km_carretera, a.distancia_km_recta) AS distancia_km,
       COALESCE(a.fuente_tiempo, 'recta_x1.8')                AS fuente_tiempo,
       GREATEST(COALESCE((f.fp ->> o.region)::numeric, (f.fp ->> '_otras')::numeric, 1),
                COALESCE((f.fp ->> d.region)::numeric, (f.fp ->> '_otras')::numeric, 1)) AS factor_planeacion,
       round(COALESCE(a.tiempo_min_carretera, a.tiempo_min_est)
             * GREATEST(COALESCE((f.fp ->> o.region)::numeric, (f.fp ->> '_otras')::numeric, 1),
                        COALESCE((f.fp ->> d.region)::numeric, (f.fp ->> '_otras')::numeric, 1)), 1) AS tiempo_min_planeacion
FROM dw.fact_accesibilidad a
JOIN dw.dim_municipio o ON o.municipio_sk = a.municipio_origen_sk
JOIN dw.dim_municipio d ON d.municipio_sk = a.municipio_destino_sk
CROSS JOIN f;

ALTER TABLE dw.fact_ruta_parada     ADD COLUMN IF NOT EXISTS tiempo_desde_anterior_min_planeacion numeric(6,1);
ALTER TABLE dw.fact_ruta_evaluacion ADD COLUMN IF NOT EXISTS tiempo_total_min_planeacion numeric(7,1);

-- 4. v_ruta_parada: coordenadas de la cabecera (A5), tiempo de planeación y puntos para la agenda.
DROP VIEW IF EXISTS dw.v_ruta_parada;
CREATE VIEW dw.v_ruta_parada WITH (security_invoker = on) AS
SELECT r.ruta_sk, r.nombre AS ruta, r.origen, r.tipo, r.tema, r.num_municipios, r.duracion_estimada_h, r.descripcion,
       COALESCE(e.tiempo_total_min_real, e.tiempo_total_min) AS tiempo_total_min,
       e.potencial_pred_medio_pct, e.necesidad_social_media, e.num_municipios_emergentes, e.puntaje_total,
       n.clasificacion_novedad, n.pct_tramos_existentes,
       p.orden_parada, p.municipio_sk, m.cve_geo, m.nombre AS municipio, m.region, m.es_pueblo_magico,
       x.codigo AS eje,
       COALESCE(p.distancia_desde_anterior_km_real, a.distancia_km, p.distancia_desde_anterior_km)
           AS distancia_desde_anterior_km,
       COALESCE(p.tiempo_desde_anterior_min_real, a.tiempo_min, p.tiempo_desde_anterior_min)
           AS tiempo_desde_anterior_min,
       p.es_ancla, p.es_emergente, p.estancia_sugerida_h,
       round(m.cabecera_lon::numeric, 5) AS lon,
       round(m.cabecera_lat::numeric, 5) AS lat,
       p.tiempo_desde_anterior_min AS tiempo_desde_anterior_min_est,
       e.tiempo_total_min          AS tiempo_total_min_est,
       p.es_pernocta, p.unidades_hospedaje, e.dias_sugeridos, e.region_beneficiada, e.cumple_restricciones,
       e.incumplimientos, e.paradas_infra_rojo, e.riesgo_seguridad,
       COALESCE(p.tiempo_desde_anterior_min_planeacion, a.tiempo_min_planeacion) AS tiempo_desde_anterior_min_planeacion,
       e.tiempo_total_min_planeacion,
       m.cabecera_nombre,
       round(st_x(m.centroide)::numeric, 5) AS lon_centroide,
       round(st_y(m.centroide)::numeric, 5) AS lat_centroide
FROM dw.dim_ruta r
JOIN dw.fact_ruta_parada p ON p.ruta_sk = r.ruta_sk
JOIN dw.dim_municipio m ON m.municipio_sk = p.municipio_sk
LEFT JOIN dw.fact_ruta_parada q ON q.ruta_sk = p.ruta_sk AND q.orden_parada = p.orden_parada - 1
LEFT JOIN dw.v_tiempo_municipios a ON a.municipio_origen_sk = q.municipio_sk AND a.municipio_destino_sk = p.municipio_sk
LEFT JOIN dw.fact_ruta_evaluacion e ON e.ruta_sk = r.ruta_sk
LEFT JOIN dw.v_novedad_ruta n ON n.ruta_sk = r.ruta_sk
LEFT JOIN dw.dim_eje x ON x.eje_sk = p.eje_sk;
GRANT SELECT ON dw.v_ruta_parada, dw.v_vigente, dw.v_tiempo_municipios TO anon, authenticated, service_role;

-- 5. v_indice_municipio: la versión vigente (antes: la de version_sk más alto).
CREATE OR REPLACE VIEW dw.v_indice_municipio WITH (security_invoker = on) AS
WITH v AS (SELECT version_indice_sk AS version_sk FROM dw.v_vigente),
mejor AS (
    SELECT DISTINCT ON (i.municipio_sk) i.municipio_sk, i.eje_sk, i.indice_oportunidad, i.score_potencial,
           i.score_oferta, i.score_social, i.score_accesibilidad
    FROM dw.fact_indice_oportunidad i JOIN v USING (version_sk)
    ORDER BY i.municipio_sk, i.indice_oportunidad DESC
)
SELECT m.municipio_sk, m.cve_geo, m.nombre, m.region, m.es_ancla, x.codigo AS eje_lider,
       round(b.indice_oportunidad, 4) AS indice_oportunidad, round(b.score_potencial, 4) AS score_potencial,
       round(b.score_oferta, 4) AS score_oferta, round(b.score_social, 4) AS score_social,
       round(b.score_accesibilidad, 4) AS score_accesibilidad,
       rank() OVER (ORDER BY b.indice_oportunidad DESC) AS ranking_estatal
FROM dw.dim_municipio m
JOIN mejor b USING (municipio_sk)
LEFT JOIN dw.dim_eje x ON x.eje_sk = b.eje_sk;
GRANT SELECT ON dw.v_indice_municipio TO anon, authenticated, service_role;
