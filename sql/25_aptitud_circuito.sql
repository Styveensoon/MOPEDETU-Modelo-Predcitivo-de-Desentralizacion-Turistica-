-- MOPEDETU · plan_migracion_front.md A10, §4.3 · Aptitud de cada municipio para un circuito
-- apto_por_lugares: ≥ 3 puntos 'atractivo' o 'experiencia' ubicados (con coordenadas) y al menos 1 'atractivo'.
-- apto: además, model/circuitos.py armó un circuito estándar que cumple todas las reglas (dw.dim_circuito); si no,
--       motivo_no_apto dice qué regla falló (lugares lejos de la cabecera, todos de la misma categoría...).
-- potencial_circuito = 0.5·pct(puntos atractivo + experiencia) + 0.3·pct(actividades distintas) + 0.2·índice vigente
-- Idempotente.
DROP VIEW IF EXISTS dw.v_aptitud_circuito;
CREATE VIEW dw.v_aptitud_circuito WITH (security_invoker = on) AS
WITH p AS (
    SELECT municipio_sk,
           count(*) FILTER (WHERE tipo_parada = 'atractivo')                     AS atractivos,
           count(*) FILTER (WHERE tipo_parada = 'experiencia')                   AS experiencias,
           count(*) FILTER (WHERE tipo_parada = 'comida')                        AS comidas,
           count(*) FILTER (WHERE tipo_parada IN ('atractivo', 'experiencia') AND lat IS NULL) AS sin_coordenadas,
           count(DISTINCT actividad) FILTER (WHERE tipo_parada IN ('atractivo', 'experiencia')) AS actividades
    FROM dw.v_lugar_circuito
    GROUP BY municipio_sk
), u AS (
    SELECT municipio_sk,
           count(*) FILTER (WHERE tipo_parada IN ('atractivo', 'experiencia')) AS ubicados,
           count(*) FILTER (WHERE tipo_parada = 'atractivo')                   AS atractivos_ubicados
    FROM dw.v_lugar_circuito WHERE lat IS NOT NULL
    GROUP BY municipio_sk
), base AS (
    SELECT m.municipio_sk, m.cve_geo, m.nombre, m.region,
           COALESCE(p.atractivos, 0) AS atractivos, COALESCE(p.experiencias, 0) AS experiencias,
           COALESCE(p.comidas, 0) AS comidas, COALESCE(p.sin_coordenadas, 0) AS sin_coordenadas,
           COALESCE(p.actividades, 0) AS actividades,
           COALESCE(u.ubicados, 0) AS puntos_ubicados, COALESCE(u.atractivos_ubicados, 0) AS atractivos_ubicados,
           i.indice_oportunidad
    FROM dw.dim_municipio m
    LEFT JOIN p ON p.municipio_sk = m.municipio_sk
    LEFT JOIN u ON u.municipio_sk = m.municipio_sk
    LEFT JOIN dw.v_indice_municipio i ON i.municipio_sk = m.municipio_sk
), est AS (
    SELECT DISTINCT ON (municipio_sk) municipio_sk, circuito_sk, cumple, incumplimientos
    FROM dw.dim_circuito WHERE es_estandar ORDER BY municipio_sk, cumple DESC
)
SELECT b.*,
       (b.puntos_ubicados >= 3 AND b.atractivos_ubicados >= 1) AS apto_por_lugares,
       (b.puntos_ubicados >= 3 AND b.atractivos_ubicados >= 1 AND COALESCE(est.cumple, false)) AS apto,
       CASE WHEN b.atractivos + b.experiencias = 0 THEN 'sin lugares registrados'
            WHEN b.puntos_ubicados < 3 THEN 'solo ' || b.puntos_ubicados || ' lugar(es) ubicado(s)'
            WHEN b.atractivos_ubicados < 1 THEN 'sin ningún atractivo ubicado (solo experiencias)'
            WHEN est.circuito_sk IS NULL THEN 'circuito pendiente de calcular (model/circuitos.py)'
            WHEN NOT est.cumple THEN 'con sus lugares no se arma un circuito que cumpla las reglas ('
                                     || array_to_string(est.incumplimientos, ', ') || ')'
       END AS motivo_no_apto,
       est.circuito_sk AS circuito_estandar_sk,
       round((0.5 * percent_rank() OVER (ORDER BY b.atractivos + b.experiencias)
            + 0.3 * percent_rank() OVER (ORDER BY b.actividades)
            + 0.2 * COALESCE(b.indice_oportunidad, 0))::numeric, 4) AS potencial_circuito
FROM base b
LEFT JOIN est ON est.municipio_sk = b.municipio_sk;

GRANT SELECT ON dw.v_aptitud_circuito TO anon, authenticated, service_role;
