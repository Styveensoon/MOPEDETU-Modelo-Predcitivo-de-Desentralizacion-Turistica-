-- MOPEDETU · F5 del plan de afinación (D9, D10) · Rutas que se puedan operar
-- 1. Las rutas que el optimizador v2 descarta por no cumplir (sin pernocta, región Angelópolis...) se guardan con
--    origen 'propuesta_descartada' y sus incumplimientos, en vez de perderse. El tablero solo muestra
--    'propuesta_modelo' y 'existente'.
-- 2. v_ruta_parada presenta el mejor tiempo disponible: el real por carretera (fact_ruta_parada.*_real o, para las
--    rutas oficiales, el par en fact_accesibilidad) y, si no hay, la línea recta. Los valores en línea recta siguen
--    en las tablas y en la vista con sufijo _est. Idempotente.

ALTER TABLE dw.dim_ruta DROP CONSTRAINT IF EXISTS dim_ruta_origen_check;
ALTER TABLE dw.dim_ruta ADD CONSTRAINT dim_ruta_origen_check
  CHECK (origen IN ('existente', 'propuesta_modelo', 'propuesta_descartada'));

DROP VIEW IF EXISTS dw.v_ruta_parada;
CREATE VIEW dw.v_ruta_parada WITH (security_invoker = on) AS
SELECT r.ruta_sk,
       r.nombre AS ruta,
       r.origen,
       r.tipo,
       r.tema,
       r.num_municipios,
       r.duracion_estimada_h,
       r.descripcion,
       COALESCE(e.tiempo_total_min_real, e.tiempo_total_min) AS tiempo_total_min,
       e.potencial_pred_medio_pct,
       e.necesidad_social_media,
       e.num_municipios_emergentes,
       e.puntaje_total,
       n.clasificacion_novedad,
       n.pct_tramos_existentes,
       p.orden_parada,
       p.municipio_sk,
       m.cve_geo,
       m.nombre AS municipio,
       m.region,
       m.es_pueblo_magico,
       x.codigo AS eje,
       COALESCE(p.distancia_desde_anterior_km_real, a.distancia_km_carretera, p.distancia_desde_anterior_km)
           AS distancia_desde_anterior_km,
       COALESCE(p.tiempo_desde_anterior_min_real, a.tiempo_min_carretera, p.tiempo_desde_anterior_min)
           AS tiempo_desde_anterior_min,
       p.es_ancla,
       p.es_emergente,
       p.estancia_sugerida_h,
       round(st_x(m.centroide)::numeric, 5) AS lon,
       round(st_y(m.centroide)::numeric, 5) AS lat,
       -- columnas nuevas (F5)
       p.tiempo_desde_anterior_min        AS tiempo_desde_anterior_min_est,
       e.tiempo_total_min                 AS tiempo_total_min_est,
       p.es_pernocta,
       p.unidades_hospedaje,
       e.dias_sugeridos,
       e.region_beneficiada,
       e.cumple_restricciones,
       e.incumplimientos,
       e.paradas_infra_rojo,
       e.riesgo_seguridad
FROM dw.dim_ruta r
JOIN dw.fact_ruta_parada p ON p.ruta_sk = r.ruta_sk
JOIN dw.dim_municipio m ON m.municipio_sk = p.municipio_sk
LEFT JOIN dw.fact_ruta_parada q ON q.ruta_sk = p.ruta_sk AND q.orden_parada = p.orden_parada - 1
LEFT JOIN dw.fact_accesibilidad a ON a.municipio_origen_sk = q.municipio_sk AND a.municipio_destino_sk = p.municipio_sk
LEFT JOIN dw.fact_ruta_evaluacion e ON e.ruta_sk = r.ruta_sk
LEFT JOIN dw.v_novedad_ruta n ON n.ruta_sk = r.ruta_sk
LEFT JOIN dw.dim_eje x ON x.eje_sk = p.eje_sk;

GRANT SELECT ON dw.v_ruta_parada TO anon, authenticated, service_role;
