-- MOPEDETU · Vistas de lectura para la página de Rutas del tablero (publishable key) · Rol C (Styveen)
-- Las tablas base tienen RLS; estas vistas exponen solo lo que el tablero necesita. Idempotente.

-- Una fila por parada de cada ruta (existentes y propuestas), con evaluación y novedad.
CREATE OR REPLACE VIEW dw.v_ruta_parada AS
SELECT r.ruta_sk, r.nombre AS ruta, r.origen, r.tipo, r.tema, r.num_municipios, r.duracion_estimada_h, r.descripcion,
       e.tiempo_total_min, e.potencial_pred_medio_pct, e.necesidad_social_media, e.num_municipios_emergentes,
       e.puntaje_total, n.clasificacion_novedad, n.pct_tramos_existentes,
       p.orden_parada, p.municipio_sk, m.cve_geo, m.nombre AS municipio, m.region, m.es_pueblo_magico,
       x.codigo AS eje, p.distancia_desde_anterior_km, p.tiempo_desde_anterior_min,
       p.es_ancla, p.es_emergente, p.estancia_sugerida_h,
       round(extensions.st_x(m.centroide)::numeric, 5) AS lon,
       round(extensions.st_y(m.centroide)::numeric, 5) AS lat
FROM dw.dim_ruta r
JOIN dw.fact_ruta_parada p USING (ruta_sk)
JOIN dw.dim_municipio m USING (municipio_sk)
LEFT JOIN dw.fact_ruta_evaluacion e USING (ruta_sk)
LEFT JOIN dw.v_novedad_ruta n USING (ruta_sk)
LEFT JOIN dw.dim_eje x ON x.eje_sk = p.eje_sk;

-- Índice de oportunidad vigente (versión más reciente) por municipio: mejor eje y ranking.
CREATE OR REPLACE VIEW dw.v_indice_municipio AS
WITH v AS (SELECT max(version_sk) AS version_sk FROM dw.fact_indice_oportunidad),
mejor AS (
    SELECT DISTINCT ON (i.municipio_sk) i.municipio_sk, i.eje_sk, i.indice_oportunidad, i.score_potencial,
           i.score_oferta, i.score_social, i.score_accesibilidad
    FROM dw.fact_indice_oportunidad i JOIN v USING (version_sk)
    ORDER BY i.municipio_sk, i.indice_oportunidad DESC)
SELECT m.municipio_sk, m.cve_geo, m.nombre, m.region, m.es_ancla, x.codigo AS eje_lider,
       round(b.indice_oportunidad, 4) AS indice_oportunidad, round(b.score_potencial, 4) AS score_potencial,
       round(b.score_oferta, 4) AS score_oferta, round(b.score_social, 4) AS score_social,
       round(b.score_accesibilidad, 4) AS score_accesibilidad,
       rank() OVER (ORDER BY b.indice_oportunidad DESC) AS ranking_estatal
FROM dw.dim_municipio m
JOIN mejor b USING (municipio_sk)
LEFT JOIN dw.dim_eje x ON x.eje_sk = b.eje_sk;

GRANT SELECT ON dw.v_ruta_parada, dw.v_indice_municipio TO anon, authenticated, service_role;

NOTIFY pgrst, 'reload schema';
