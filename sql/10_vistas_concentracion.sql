-- MOPEDETU · F3 del plan de afinación (D3, D4, D5) · Concentración por eje y oferta en exceso de la población
-- dw.v_concentracion se conserva (la usan el tablero y los documentos); estas vistas la complementan.
-- Idempotente.

-- Concentración por eje (eje 0 = suma de los 4 ejes), con la población 2020 como referencia: si el turismo se
-- concentra más que la gente, el top 5 y el HHI de la oferta superan a los de la población.
CREATE OR REPLACE VIEW dw.v_concentracion_eje WITH (security_invoker = on) AS
WITH oferta AS (
    SELECT periodo_sk, eje_sk, municipio_sk, personal_est AS valor
    FROM dw.fact_oferta_municipio_eje
    UNION ALL
    SELECT periodo_sk, 0, municipio_sk, sum(personal_est)
    FROM dw.fact_oferta_municipio_eje
    GROUP BY periodo_sk, municipio_sk
), sh AS (
    SELECT periodo_sk, eje_sk, valor,
           valor / NULLIF(sum(valor) OVER (PARTITION BY periodo_sk, eje_sk), 0) AS part,
           rank() OVER (PARTITION BY periodo_sk, eje_sk ORDER BY valor DESC) AS rnk
    FROM oferta
), pob AS (
    SELECT poblacion_total / sum(poblacion_total) OVER ()::numeric AS part,
           rank() OVER (ORDER BY poblacion_total DESC) AS rnk
    FROM dw.fact_contexto_social
    WHERE periodo_sk = 5
), ref AS (
    SELECT round(100 * sum(part) FILTER (WHERE rnk <= 5), 1) AS pct_top5_poblacion,
           round(sum(part * part) * 10000, 0)               AS hhi_poblacion
    FROM pob
)
SELECT sh.periodo_sk, sh.eje_sk,
       round(100 * sum(sh.part) FILTER (WHERE sh.rnk <= 5), 1) AS pct_top5,
       round(sum(sh.part * sh.part) * 10000, 0)                AS hhi,
       ref.pct_top5_poblacion, ref.hhi_poblacion,
       count(*) FILTER (WHERE sh.valor > 0)                    AS municipios_con_oferta
FROM sh CROSS JOIN ref
GROUP BY sh.periodo_sk, sh.eje_sk, ref.pct_top5_poblacion, ref.hhi_poblacion;

-- Oferta en exceso de lo que explicaría la población (proxy de turismo). Por periodo y eje se ajusta
-- ln(1 + personal) = a + b·ln(población) sobre los 217 municipios; el residuo es la oferta de más (o de menos).
CREATE OR REPLACE VIEW dw.v_exceso_oferta WITH (security_invoker = on) AS
WITH base AS (
    SELECT o.periodo_sk, o.eje_sk, o.municipio_sk, o.personal_est
    FROM dw.fact_oferta_municipio_eje o
    UNION ALL
    SELECT periodo_sk, 0, municipio_sk, sum(personal_est)
    FROM dw.fact_oferta_municipio_eje
    GROUP BY periodo_sk, municipio_sk
), obs AS (
    SELECT b.*, c.poblacion_total,
           ln(1 + b.personal_est)       AS ln_po_obs,
           ln(c.poblacion_total)        AS ln_pob
    FROM base b
    JOIN dw.fact_contexto_social c ON c.municipio_sk = b.municipio_sk AND c.periodo_sk = 5
), ajuste AS (
    SELECT periodo_sk, eje_sk,
           regr_intercept(ln_po_obs, ln_pob) AS a,
           regr_slope(ln_po_obs, ln_pob)     AS b,
           regr_r2(ln_po_obs, ln_pob)        AS r2
    FROM obs GROUP BY periodo_sk, eje_sk
), res AS (
    SELECT o.periodo_sk, o.eje_sk, o.municipio_sk, o.personal_est, o.poblacion_total,
           o.ln_po_obs, o.ln_pob, j.a, j.b, j.r2,
           o.ln_po_obs - (j.a + j.b * o.ln_pob) AS residuo
    FROM obs o JOIN ajuste j USING (periodo_sk, eje_sk)
)
SELECT periodo_sk, eje_sk, municipio_sk, personal_est, poblacion_total,
       round((exp(a + b * ln_pob) - 1)::numeric, 1)                                     AS personal_esperado,
       round(residuo::numeric, 4)                                              AS residuo,
       round(((exp(residuo) - 1) * 100)::numeric, 1)                           AS exceso_pct,
       round(percent_rank() OVER (PARTITION BY periodo_sk, eje_sk ORDER BY residuo)::numeric, 3)
                                                                               AS percentil_residuo,
       round(b::numeric, 3) AS pendiente, round(r2::numeric, 3) AS r2_ajuste
FROM res;

GRANT SELECT ON dw.v_concentracion_eje, dw.v_exceso_oferta TO anon, authenticated, service_role;

-- D5: DENUE y Censos Económicos no son evidencias independientes
UPDATE dw.dim_fuente
SET calidad_notas = concat_ws(' ', calidad_notas,
    'Dependencia DENUE ↔ CE: el DENUE se actualiza a partir de los Censos Económicos (correlación medida de '
    'ln(1+UE) por municipio × eje entre DENUE 2026 y CE 2024 = 0.998, 15-oct-2026); no presentarlos como dos '
    'evidencias independientes.')
WHERE (nombre ILIKE '%DENUE%' OR nombre ILIKE '%Censo%Econ%')
  AND coalesce(calidad_notas, '') NOT LIKE '%Dependencia DENUE ↔ CE%';
