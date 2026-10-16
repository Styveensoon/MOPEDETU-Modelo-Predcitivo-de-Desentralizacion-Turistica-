-- MOPEDETU · plan_migracion_front.md A9 (parte 2) · Puntos visitables para circuitos y rutas
-- tipo_parada: 'atractivo' | 'experiencia' | 'comida'. prioridad (§4.3, menor = mejor):
--   1 curado (con URL) · 2 lugar OSM con actividad · 3 negocio SCIAN 712/713 de bridge_scian_eje ·
--   4 experiencia por SCIAN · 5 experiencia por nombre · 6 lugar OSM sin actividad · 7 comida tradicional
-- Excluye negocios sin nombre (o registrados como "SIN NOMBRE" en el DENUE) o sin coordenadas y los duplicados (mismo nombre normalizado en ~50 m: rejilla de
-- 0.0005°), quedándose con el de mejor prioridad. Idempotente.
CREATE OR REPLACE VIEW dw.v_lugar_circuito WITH (security_invoker = on) AS
WITH den AS (
    SELECT d.establecimiento_sk, d.municipio_sk, d.nombre, trim(s.codigo_scian) AS scian, ep.punto_medio,
           st_y(d.geom) AS lat, st_x(d.geom) AS lon
    FROM dw.dim_establecimiento d
    JOIN dw.dim_scian s ON s.scian_sk = d.scian_sk
    LEFT JOIN dw.dim_estrato_personal ep ON ep.estrato_sk = d.estrato_sk
    WHERE d.nombre IS NOT NULL AND btrim(d.nombre) <> '' AND d.nombre !~* 'sin nombre' AND d.geom IS NOT NULL
), act AS (
    SELECT fa.establecimiento_sk, a.codigo, fa.senal
    FROM dw.fact_establecimiento_actividad fa JOIN dw.dim_actividad a ON a.actividad_sk = fa.actividad_sk
), scian_atr AS (
    SELECT DISTINCT trim(s.codigo_scian) AS scian
    FROM dw.bridge_scian_eje b JOIN dw.dim_scian s ON s.scian_sk = b.scian_sk
    WHERE s.codigo_scian LIKE '712%' OR s.codigo_scian LIKE '713%'
), todos AS (
    SELECT 'al:' || l.atractivo_sk AS lugar_id, l.municipio_sk, l.nombre,
           -- templos/parroquias sin señal de actividad cuentan como parada religiosa del circuito temático
           COALESCE(l.actividades[1], CASE WHEN l.categoria IN ('templo', 'santuario') THEN 'religioso' END) AS actividad,
           l.categoria, 'atractivo' AS tipo_parada,
           CASE WHEN l.origen = 'catalogo_curado' THEN 'curado' ELSE 'osm' END AS origen, l.url,
           NULL::numeric AS personal_est, l.lat::float8 AS lat, l.lon::float8 AS lon,
           CASE WHEN l.origen = 'catalogo_curado' THEN 1 WHEN cardinality(l.actividades) > 0 THEN 2 ELSE 6 END AS prioridad
    FROM dw.fact_atractivo_lugar l
    -- los curados no traen coordenadas: entran igual (cuentan como punto visitable; el circuito los omite)
    UNION ALL
    SELECT 'de:' || d.establecimiento_sk, d.municipio_sk, d.nombre,
           (SELECT min(a.codigo) FROM act a WHERE a.establecimiento_sk = d.establecimiento_sk),
           CASE WHEN d.scian IN ('712111', '712112') THEN 'museo'
                WHEN d.scian LIKE '7121%' THEN 'patrimonio'
                WHEN d.scian IN ('713113', '713114') THEN 'balneario'
                ELSE 'recreacion' END,
           'atractivo', 'denue', NULL, d.punto_medio, d.lat, d.lon, 3
    FROM den d JOIN scian_atr x ON x.scian = d.scian
    UNION ALL
    SELECT 'de:' || d.establecimiento_sk, d.municipio_sk, d.nombre, a.codigo, a.codigo, 'experiencia', 'denue', NULL,
           d.punto_medio, d.lat, d.lon, CASE WHEN a.senal = 'scian' THEN 4 ELSE 5 END
    FROM den d JOIN act a ON a.establecimiento_sk = d.establecimiento_sk
    WHERE a.codigo IN ('cafe', 'mezcal', 'bebidas_tradicionales', 'artesanias', 'flores_viveros')
      AND d.scian NOT IN (SELECT scian FROM scian_atr)
    UNION ALL
    SELECT 'de:' || d.establecimiento_sk, d.municipio_sk, d.nombre, 'gastronomia', 'comida', 'comida', 'denue', NULL,
           d.punto_medio, d.lat, d.lon, 7
    FROM den d JOIN act a ON a.establecimiento_sk = d.establecimiento_sk
    WHERE a.codigo = 'gastronomia' AND d.scian LIKE '7225%'
), uno AS (   -- un renglón por lugar (un negocio con dos actividades de experiencia queda una vez)
    SELECT DISTINCT ON (lugar_id) * FROM todos ORDER BY lugar_id, prioridad, actividad
)
SELECT DISTINCT ON (municipio_sk, lower(translate(btrim(nombre), 'ÁÉÍÓÚÜÑáéíóúüñ', 'AEIOUUNaeiouun')),
                    round(lat::numeric / 0.0005), round(lon::numeric / 0.0005))
       lugar_id, municipio_sk, nombre, actividad, categoria, tipo_parada, origen, url, personal_est,
       round(lat::numeric, 6) AS lat, round(lon::numeric, 6) AS lon, prioridad
FROM uno
ORDER BY municipio_sk, lower(translate(btrim(nombre), 'ÁÉÍÓÚÜÑáéíóúüñ', 'AEIOUUNaeiouun')),
         round(lat::numeric / 0.0005), round(lon::numeric / 0.0005), prioridad, personal_est DESC NULLS LAST;

GRANT SELECT ON dw.v_lugar_circuito TO anon, authenticated, service_role;
