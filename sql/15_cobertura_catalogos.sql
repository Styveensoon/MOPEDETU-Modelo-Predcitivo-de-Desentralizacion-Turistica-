-- MOPEDETU · F7 del plan de afinación (D8) · Cobertura de las capas delgadas
-- Cuántos eventos propios y lugares curados tiene cada municipio, y si aparece en una ruta oficial o propuesta.
-- Meta de F7: todo municipio de una ruta con al menos un evento con fuente. Idempotente.

CREATE OR REPLACE VIEW dw.v_cobertura_catalogos WITH (security_invoker = on) AS
WITH rutas AS (
    SELECT p.municipio_sk,
           bool_or(r.origen = 'existente')        AS en_ruta_oficial,
           bool_or(r.origen = 'propuesta_modelo') AS en_ruta_propuesta
    FROM dw.fact_ruta_parada p JOIN dw.dim_ruta r ON r.ruta_sk = p.ruta_sk
    GROUP BY p.municipio_sk
), eventos AS (
    SELECT municipio_sk, count(*) AS eventos_propios, count(url) AS eventos_con_url
    FROM dw.fact_temporada WHERE municipio_sk IS NOT NULL GROUP BY municipio_sk
), lugares AS (
    SELECT municipio_sk,
           count(*) FILTER (WHERE origen = 'catalogo_curado') AS lugares_curados,
           count(*) FILTER (WHERE origen = 'osm')             AS lugares_osm
    FROM dw.fact_atractivo_lugar GROUP BY municipio_sk
), inah AS (
    SELECT municipio_sk, sum(num_atractivos) AS zonas_inah
    FROM dw.fact_atractivo WHERE categoria = 'zona_arqueologica_inah' GROUP BY municipio_sk
)
SELECT m.municipio_sk, m.cve_geo, m.nombre, m.region,
       COALESCE(r.en_ruta_oficial, false)   AS en_ruta_oficial,
       COALESCE(r.en_ruta_propuesta, false) AS en_ruta_propuesta,
       COALESCE(e.eventos_propios, 0)       AS eventos_propios,
       COALESCE(e.eventos_con_url, 0)       AS eventos_con_url,
       COALESCE(l.lugares_curados, 0)       AS lugares_curados,
       COALESCE(l.lugares_osm, 0)           AS lugares_osm,
       COALESCE(i.zonas_inah, 0)            AS zonas_inah
FROM dw.dim_municipio m
LEFT JOIN rutas r   ON r.municipio_sk = m.municipio_sk
LEFT JOIN eventos e ON e.municipio_sk = m.municipio_sk
LEFT JOIN lugares l ON l.municipio_sk = m.municipio_sk
LEFT JOIN inah i    ON i.municipio_sk = m.municipio_sk;

GRANT SELECT ON dw.v_cobertura_catalogos TO anon, authenticated, service_role;
