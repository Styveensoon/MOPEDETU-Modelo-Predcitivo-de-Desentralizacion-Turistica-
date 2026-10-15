-- MOPEDETU · Vista de la ficha técnica municipal (una fila por municipio) · Rol C (Styveen)
-- Ver docs/modelo_predictivo_anillos.md §3.4. El tablero hace una sola consulta a esta vista.
-- Idempotente (CREATE OR REPLACE).

CREATE OR REPLACE VIEW dw.v_ficha_municipio AS
WITH
ver AS (SELECT max(version_sk) AS v FROM dw.dim_version_calculo WHERE nombre = 'ficha_semaforos_v1'),
per AS (SELECT max(periodo_sk) AS p FROM dw.fact_actividad_municipio),
sem AS (
    SELECT s.municipio_sk,
           jsonb_object_agg(s.dimension, jsonb_build_object('nivel', s.nivel, 'valor', s.valor,
                                                            'percentil', s.percentil, 'motivo', s.motivo)) AS semaforos
    FROM dw.fact_semaforo_municipio s JOIN ver ON s.version_sk = ver.v
    GROUP BY s.municipio_sk),
act AS (
    SELECT f.municipio_sk,
           jsonb_agg(jsonb_build_object('codigo', a.codigo, 'nombre', a.nombre, 'icono', a.icono,
                                        'nivel', f.nivel_predominancia, 'unidades', f.unidades,
                                        'cl', round(f.cociente_localizacion, 2), 'ejemplos', to_jsonb(f.ejemplos))
                     ORDER BY f.rango_en_municipio) FILTER (WHERE f.es_principal) AS actividades_principales,
           jsonb_agg(jsonb_build_object('codigo', a.codigo, 'nombre', a.nombre, 'icono', a.icono,
                                        'nivel', f.nivel_predominancia, 'unidades', f.unidades)
                     ORDER BY f.score DESC)
               FILTER (WHERE NOT f.es_principal AND f.nivel_predominancia <> 'sin_oferta') AS otras_actividades,
           jsonb_agg(a.nombre) FILTER (WHERE f.nivel_predominancia = 'reconocida_sin_registro') AS oferta_sin_registro,
           array_agg(f.actividad_sk) FILTER (WHERE f.es_principal) AS principales_sk
    FROM dw.fact_actividad_municipio f
    JOIN per ON f.periodo_sk = per.p
    JOIN dw.dim_actividad a USING (actividad_sk)
    GROUP BY f.municipio_sk),
inf AS (
    SELECT municipio_sk, jsonb_object_agg(indicador, valor) AS infraestructura
    FROM dw.fact_infraestructura GROUP BY municipio_sk),
-- Intensidad por mes: temporadas nacionales + temporadas de sus actividades principales + eventos propios.
mes AS (
    SELECT m.municipio_sk, g.mes,
           coalesce(max(t.intensidad), 0) AS intensidad,
           coalesce(max(t.intensidad) FILTER (WHERE t.municipio_sk IS NOT NULL OR t.actividad_sk IS NOT NULL), 0)
               AS intensidad_propia
    FROM dw.dim_municipio m
    CROSS JOIN generate_series(1, 12) AS g(mes)
    LEFT JOIN act ON act.municipio_sk = m.municipio_sk
    LEFT JOIN dw.fact_temporada t
           ON (t.municipio_sk = m.municipio_sk
               OR (t.municipio_sk IS NULL AND t.actividad_sk IS NULL)
               OR (t.municipio_sk IS NULL AND t.actividad_sk = ANY (act.principales_sk)))
          AND CASE WHEN t.mes_inicio <= t.mes_fin THEN g.mes BETWEEN t.mes_inicio AND t.mes_fin
                   ELSE g.mes >= t.mes_inicio OR g.mes <= t.mes_fin END
    GROUP BY m.municipio_sk, g.mes),
tira AS (
    SELECT municipio_sk,
           array_agg(intensidad ORDER BY mes) AS temporada_meses,
           array_agg(mes ORDER BY mes) FILTER (WHERE intensidad_propia >= 2) AS meses_fuertes
    FROM mes GROUP BY municipio_sk),
eve AS (
    SELECT municipio_sk,
           jsonb_agg(jsonb_build_object('nombre', nombre, 'tipo', tipo, 'mes_inicio', mes_inicio, 'mes_fin', mes_fin,
                                        'intensidad', intensidad, 'url', url, 'notas', notas)
                     ORDER BY mes_inicio, intensidad DESC) AS eventos
    FROM dw.fact_temporada WHERE municipio_sk IS NOT NULL GROUP BY municipio_sk),
rut AS (
    SELECT p.municipio_sk,
           jsonb_agg(DISTINCT r.nombre) FILTER (WHERE r.origen = 'existente') AS rutas_existentes,
           jsonb_agg(DISTINCT r.nombre) FILTER (WHERE r.origen <> 'existente') AS rutas_propuestas
    FROM dw.fact_ruta_parada p JOIN dw.dim_ruta r USING (ruta_sk)
    GROUP BY p.municipio_sk),
-- Atractivos con nombre: primero el catálogo curado, luego OpenStreetMap (sql/08)
atr AS (
    SELECT municipio_sk,
           jsonb_agg(jsonb_build_object('nombre', nombre, 'categoria', categoria, 'actividades', to_jsonb(actividades),
                                        'descripcion', descripcion, 'url', url, 'origen', origen)
                     ORDER BY (origen = 'catalogo_curado') DESC, nombre) AS atractivos
    FROM dw.fact_atractivo_lugar GROUP BY municipio_sk),
-- Banderas de la versión vigente del índice (la más reciente), una por tipo con sus motivos por eje
ban AS (
    SELECT municipio_sk,
           jsonb_agg(jsonb_build_object('codigo', codigo, 'motivo', motivos) ORDER BY prioridad, codigo) AS banderas
    FROM (
        SELECT f.municipio_sk, t.codigo, t.prioridad, string_agg(DISTINCT f.motivo, ' · ') AS motivos
        FROM dw.fact_flag_oportunidad f
        JOIN dw.dim_tipo_flag t USING (tipo_flag_sk)
        WHERE f.flag_activo AND f.version_sk = (SELECT max(version_sk) FROM dw.fact_flag_oportunidad)
        GROUP BY f.municipio_sk, t.codigo, t.prioridad) x
    GROUP BY municipio_sk)
SELECT m.municipio_sk, m.cve_geo, m.nombre, m.region, m.es_pueblo_magico, m.es_ancla, m.superficie_km2,
       round(extensions.st_x(m.centroide)::numeric, 5) AS lon,
       round(extensions.st_y(m.centroide)::numeric, 5) AS lat,
       (inf.infraestructura ->> 'poblacion_2020')::numeric AS poblacion,
       sem.semaforos,
       coalesce(act.actividades_principales, '[]') AS actividades_principales,
       coalesce(act.otras_actividades, '[]') AS otras_actividades,
       coalesce(act.oferta_sin_registro, '[]') AS oferta_sin_registro,
       inf.infraestructura,
       tira.temporada_meses,
       coalesce(tira.meses_fuertes, '{}') AS meses_fuertes,
       coalesce(eve.eventos, '[]') AS eventos,
       coalesce(rut.rutas_existentes, '[]') AS rutas_existentes,
       coalesce(rut.rutas_propuestas, '[]') AS rutas_propuestas,
       coalesce(ban.banderas, '[]') AS banderas,
       coalesce(atr.atractivos, '[]') AS atractivos
FROM dw.dim_municipio m
LEFT JOIN sem  USING (municipio_sk)
LEFT JOIN act  USING (municipio_sk)
LEFT JOIN inf  USING (municipio_sk)
LEFT JOIN tira USING (municipio_sk)
LEFT JOIN eve  USING (municipio_sk)
LEFT JOIN rut  USING (municipio_sk)
LEFT JOIN ban  USING (municipio_sk)
LEFT JOIN atr  USING (municipio_sk);

COMMENT ON VIEW dw.v_ficha_municipio IS
  'Ficha técnica municipal MOPEDETU: identidad, semáforos, actividades, infraestructura, temporadas, rutas y banderas.';

GRANT SELECT ON dw.v_ficha_municipio TO anon, authenticated, service_role;

NOTIFY pgrst, 'reload schema';
