-- MOPEDETU · plan_migracion_front.md A5, §6.3 · Ficha técnica con cabecera, versión vigente y campos nuevos
-- Cambios sobre sql/06_vista_ficha_municipio.sql:
--   · lat/lon = cabecera municipal (los tiempos se calculan entre cabeceras); el centroide queda en *_centroide
--   · semáforos y banderas de la versión vigente (dw.v_vigente), no "la más alta"
--   · rutas_propuestas solo con origen 'propuesta_modelo' (antes incluía las descartadas)
--   · columnas nuevas al final: cabecera, año de Pueblo Mágico, predicción por eje, seguridad (municipio y
--     carretera por separado), visibilidad y exceso de oferta
-- Idempotente (CREATE OR REPLACE conserva las columnas existentes y agrega las nuevas al final).

CREATE OR REPLACE VIEW dw.v_ficha_municipio WITH (security_invoker = on) AS
WITH vig AS (SELECT * FROM dw.v_vigente),
per AS (SELECT max(periodo_sk) AS p FROM dw.fact_actividad_municipio),
sem AS (
    SELECT s.municipio_sk,
           jsonb_object_agg(s.dimension, jsonb_build_object('nivel', s.nivel, 'valor', s.valor,
                            'percentil', s.percentil, 'motivo', s.motivo)) AS semaforos
    FROM dw.fact_semaforo_municipio s JOIN vig ON s.version_sk = vig.semaforos_sk
    GROUP BY s.municipio_sk
), act AS (
    SELECT f.municipio_sk,
           jsonb_agg(jsonb_build_object('codigo', a.codigo, 'nombre', a.nombre, 'icono', a.icono,
                     'nivel', f.nivel_predominancia, 'unidades', f.unidades, 'cl', round(f.cociente_localizacion, 2),
                     'ejemplos', to_jsonb(f.ejemplos)) ORDER BY f.rango_en_municipio) FILTER (WHERE f.es_principal)
               AS actividades_principales,
           jsonb_agg(jsonb_build_object('codigo', a.codigo, 'nombre', a.nombre, 'icono', a.icono,
                     'nivel', f.nivel_predominancia, 'unidades', f.unidades) ORDER BY f.score DESC)
               FILTER (WHERE NOT f.es_principal AND f.nivel_predominancia <> 'sin_oferta') AS otras_actividades,
           jsonb_agg(a.nombre) FILTER (WHERE f.nivel_predominancia = 'reconocida_sin_registro') AS oferta_sin_registro,
           array_agg(f.actividad_sk) FILTER (WHERE f.es_principal) AS principales_sk
    FROM dw.fact_actividad_municipio f
    JOIN per ON f.periodo_sk = per.p
    JOIN dw.dim_actividad a USING (actividad_sk)
    GROUP BY f.municipio_sk
), inf AS (
    SELECT municipio_sk, jsonb_object_agg(indicador, valor) AS infraestructura
    FROM dw.fact_infraestructura GROUP BY municipio_sk
), mes AS (
    SELECT m_1.municipio_sk, g.mes,
           COALESCE(max(t.intensidad)::integer, 0) AS intensidad,
           COALESCE(max(t.intensidad) FILTER (WHERE t.municipio_sk IS NOT NULL OR t.actividad_sk IS NOT NULL)::integer, 0)
               AS intensidad_propia
    FROM dw.dim_municipio m_1
    CROSS JOIN generate_series(1, 12) g(mes)
    LEFT JOIN act act_1 ON act_1.municipio_sk = m_1.municipio_sk
    LEFT JOIN dw.fact_temporada t
           ON (t.municipio_sk = m_1.municipio_sk OR t.municipio_sk IS NULL AND t.actividad_sk IS NULL
               OR t.municipio_sk IS NULL AND t.actividad_sk = ANY (act_1.principales_sk))
          AND CASE WHEN t.mes_inicio <= t.mes_fin THEN g.mes >= t.mes_inicio AND g.mes <= t.mes_fin
                   ELSE g.mes >= t.mes_inicio OR g.mes <= t.mes_fin END
    GROUP BY m_1.municipio_sk, g.mes
), tira AS (
    SELECT municipio_sk, array_agg(intensidad ORDER BY mes) AS temporada_meses,
           array_agg(mes ORDER BY mes) FILTER (WHERE intensidad_propia >= 2) AS meses_fuertes
    FROM mes GROUP BY municipio_sk
), eve AS (
    SELECT municipio_sk,
           jsonb_agg(jsonb_build_object('nombre', nombre, 'tipo', tipo, 'mes_inicio', mes_inicio, 'mes_fin', mes_fin,
                     'intensidad', intensidad, 'url', url, 'notas', notas) ORDER BY mes_inicio, intensidad DESC) AS eventos
    FROM dw.fact_temporada WHERE municipio_sk IS NOT NULL GROUP BY municipio_sk
), rut AS (
    SELECT p.municipio_sk,
           jsonb_agg(DISTINCT r.nombre) FILTER (WHERE r.origen = 'existente') AS rutas_existentes,
           jsonb_agg(DISTINCT r.nombre) FILTER (WHERE r.origen = 'propuesta_modelo') AS rutas_propuestas
    FROM dw.fact_ruta_parada p JOIN dw.dim_ruta r USING (ruta_sk)
    GROUP BY p.municipio_sk
), atr AS (
    SELECT municipio_sk,
           jsonb_agg(jsonb_build_object('nombre', nombre, 'categoria', categoria, 'actividades', to_jsonb(actividades),
                     'descripcion', descripcion, 'url', url, 'origen', origen)
                     ORDER BY (origen = 'catalogo_curado') DESC, nombre) AS atractivos
    FROM dw.fact_atractivo_lugar GROUP BY municipio_sk
), ban AS (
    SELECT x.municipio_sk,
           jsonb_agg(jsonb_build_object('codigo', x.codigo, 'motivo', x.motivos) ORDER BY x.prioridad, x.codigo) AS banderas
    FROM (SELECT f.municipio_sk, t.codigo, t.prioridad, string_agg(DISTINCT f.motivo, ' · ') AS motivos
          FROM dw.fact_flag_oportunidad f
          JOIN dw.dim_tipo_flag t USING (tipo_flag_sk)
          JOIN vig ON f.version_sk = vig.version_indice_sk
          WHERE f.flag_activo
          GROUP BY f.municipio_sk, t.codigo, t.prioridad) x
    GROUP BY x.municipio_sk
), pre AS (
    SELECT p.municipio_sk,
           jsonb_agg(jsonb_build_object('eje', e.codigo, 'eje_nombre', e.nombre, 'en_dominio', p.en_dominio,
                     'unidades_base', p.unidades_base, 'personal_base', p.personal_base,
                     'crecimiento_pct', p.crecimiento_pred_pct, 'inf_pct', p.intervalo_inf_pct,
                     'sup_pct', p.intervalo_sup_pct, 'motivo', p.motivo_sin_prediccion) ORDER BY e.eje_sk) AS prediccion
    FROM dw.fact_prediccion_crecimiento p
    JOIN vig ON p.modelo_sk = vig.modelo_sk
    JOIN dw.dim_eje e ON e.eje_sk = p.eje_sk
    GROUP BY p.municipio_sk
), seg_base AS (
    SELECT municipio_sk, anio,
           sum(tasa_100k) FILTER (WHERE grupo_delito IN ('homicidio', 'secuestro_extorsion', 'robo_transeunte')) AS tasa_municipio,
           sum(tasa_100k) FILTER (WHERE grupo_delito = 'robo_carretera') AS tasa_carretera,
           sum(tasa_100k) FILTER (WHERE grupo_delito = 'homicidio') AS tasa_homicidio
    FROM dw.fact_seguridad
    WHERE anio = (SELECT max(anio) FROM dw.fact_seguridad)
    GROUP BY municipio_sk, anio
), seg AS (
    SELECT municipio_sk,
           jsonb_build_object('anio', anio,
               'tasa_municipio', round(tasa_municipio, 1),
               'percentil_municipio', round(percent_rank() OVER (ORDER BY tasa_municipio)::numeric, 3),
               'tasa_carretera', round(tasa_carretera, 1),
               'percentil_carretera', round(percent_rank() OVER (ORDER BY tasa_carretera)::numeric, 3),
               'tasa_homicidio', round(tasa_homicidio, 1),
               'nota', 'SESNSP: carpetas de investigación (denuncias) por 100 mil hab.; no es victimización') AS seguridad
    FROM seg_base
), vis AS (
    SELECT municipio_sk,
           jsonb_build_object('vistas', vistas,
               'percentil', round(percent_rank() OVER (ORDER BY vistas)::numeric, 3),
               'titulo', titulo_wikipedia, 'periodo_inicio', periodo_inicio, 'periodo_fin', periodo_fin) AS visibilidad
    FROM dw.fact_visibilidad
    WHERE actividad_sk IS NULL AND periodo_inicio = (SELECT max(periodo_inicio) FROM dw.fact_visibilidad)
), exc AS (
    SELECT x.municipio_sk,
           jsonb_agg(jsonb_build_object('eje', COALESCE(e.codigo, 'global'), 'personal', x.personal_est,
                     'esperado', x.personal_esperado, 'exceso_pct', x.exceso_pct,
                     'percentil', x.percentil_residuo) ORDER BY x.eje_sk) AS exceso_oferta
    FROM dw.v_exceso_oferta x
    JOIN vig ON x.periodo_sk = vig.periodo_oferta_sk
    LEFT JOIN dw.dim_eje e ON e.eje_sk = x.eje_sk AND x.eje_sk > 0
    GROUP BY x.municipio_sk
)
SELECT m.municipio_sk, m.cve_geo, m.nombre, m.region, m.es_pueblo_magico, m.es_ancla, m.superficie_km2,
       round(m.cabecera_lon::numeric, 5) AS lon,
       round(m.cabecera_lat::numeric, 5) AS lat,
       (inf.infraestructura ->> 'poblacion_2020')::numeric AS poblacion,
       sem.semaforos,
       COALESCE(act.actividades_principales, '[]'::jsonb) AS actividades_principales,
       COALESCE(act.otras_actividades, '[]'::jsonb) AS otras_actividades,
       COALESCE(act.oferta_sin_registro, '[]'::jsonb) AS oferta_sin_registro,
       inf.infraestructura,
       tira.temporada_meses,
       COALESCE(tira.meses_fuertes, '{}'::integer[]) AS meses_fuertes,
       COALESCE(eve.eventos, '[]'::jsonb) AS eventos,
       COALESCE(rut.rutas_existentes, '[]'::jsonb) AS rutas_existentes,
       COALESCE(rut.rutas_propuestas, '[]'::jsonb) AS rutas_propuestas,
       COALESCE(ban.banderas, '[]'::jsonb) AS banderas,
       COALESCE(atr.atractivos, '[]'::jsonb) AS atractivos,
       m.cabecera_nombre,
       m.anio_pueblo_magico,
       round(st_x(m.centroide)::numeric, 5) AS lon_centroide,
       round(st_y(m.centroide)::numeric, 5) AS lat_centroide,
       COALESCE(pre.prediccion, '[]'::jsonb) AS prediccion,
       seg.seguridad,
       vis.visibilidad,
       COALESCE(exc.exceso_oferta, '[]'::jsonb) AS exceso_oferta
FROM dw.dim_municipio m
LEFT JOIN sem USING (municipio_sk)
LEFT JOIN act USING (municipio_sk)
LEFT JOIN inf USING (municipio_sk)
LEFT JOIN tira USING (municipio_sk)
LEFT JOIN eve USING (municipio_sk)
LEFT JOIN rut USING (municipio_sk)
LEFT JOIN ban USING (municipio_sk)
LEFT JOIN atr USING (municipio_sk)
LEFT JOIN pre USING (municipio_sk)
LEFT JOIN seg USING (municipio_sk)
LEFT JOIN vis USING (municipio_sk)
LEFT JOIN exc USING (municipio_sk);

GRANT SELECT ON dw.v_ficha_municipio TO anon, authenticated, service_role;
