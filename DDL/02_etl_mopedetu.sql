-- =============================================================================
-- MOPEDETU · ETL de stg.* a dw.*  (ejecutar DESPUÉS de cargar stg.denue,
-- stg.totales_municipio, stg.mun_geo y, si ya los tienen, stg.censo_economico)
-- Cada paso es idempotente. Los pasos 0, 4 y 6 recalculan (UPDATE o DELETE + INSERT),
-- así que volver a ejecutarlos corrige resultados viejos. Ejecutar en orden.
-- Runner: python scripts/ejecutar_sql.py DDL/02_etl_mopedetu.sql --pasos 0 1 2 3
-- =============================================================================
SET search_path = public, extensions;

-- ---------------------------------------------------------------------------
-- Paso 0. dim_municipio desde el Marco Geoestadístico
-- ---------------------------------------------------------------------------
-- Centroide geométrico; si consiguen la ubicación de las cabeceras municipales,
-- sustitúyanlo: representa mejor el punto de llegada de una ruta.
INSERT INTO dw.dim_municipio (cve_geo, nombre, superficie_km2, geom, centroide)
SELECT g.cve_geo,
       g.nombre,
       ROUND((ST_Area(g.geom::geography) / 1000000.0)::numeric, 2),
       g.geom,
       ST_Centroid(g.geom)
FROM stg.mun_geo g
ON CONFLICT (cve_geo) DO UPDATE                      -- conserva es_ancla / es_pueblo_magico / region
   SET nombre         = EXCLUDED.nombre,
       superficie_km2 = EXCLUDED.superficie_km2,
       geom           = EXCLUDED.geom,
       centroide      = EXCLUDED.centroide;

-- Marcar anclas y Pueblos Mágicos con el catálogo oficial (carga manual), p. ej.:
-- UPDATE dw.dim_municipio SET es_pueblo_magico = true WHERE cve_geo IN ('21...', '21...');
-- UPDATE dw.dim_municipio SET es_ancla = true         WHERE cve_geo IN ('21114', ...);

-- ---------------------------------------------------------------------------
-- Paso 1. dim_scian desde el propio DENUE cargado
-- ---------------------------------------------------------------------------
INSERT INTO dw.dim_scian (codigo_scian, descripcion, sector, subsector, rama)
SELECT d.codigo_act,
       MAX(d.nombre_act),
       LEFT(d.codigo_act, 2),
       LEFT(d.codigo_act, 3),
       LEFT(d.codigo_act, 4)
FROM stg.denue d
GROUP BY d.codigo_act
ON CONFLICT (codigo_scian) DO NOTHING;

-- ---------------------------------------------------------------------------
-- Paso 2. bridge SCIAN -> eje por prefijo
-- VALIDAR contra el catálogo SCIAN 2018 de INEGI antes de presentar.
--   721  Servicios de alojamiento temporal         -> hospedaje
--   722  Servicios de preparación de alimentos     -> alimentos
--   711, 712, 713, 5615  Artes y espectáculos, museos y sitios históricos,
--        entretenimiento y recreación, agencias de viajes -> turismo
--   465915  Comercio al por menor en tiendas de artesanías       -> comercio_turistico
--           (465912 "regalos" se descartó: 6.8 mil unidades, casi todas de consumo local)
-- Excluidos aunque caen en los prefijos (servicio local, no turístico), quedan con
-- es_turistico = false y sin eje: gimnasios (713943/44), juegos electrónicos (713120),
-- lotería y azar (713291/99), clubes deportivos y ligas (713941/42, 713992), billares (713991)
-- y comedores para empresas (722310). La verificación 7.3 los lista con suma 0: es esperado.
-- ---------------------------------------------------------------------------
UPDATE dw.dim_scian
   SET es_turistico = codigo_scian NOT IN ('713943','713944','713120','713291','713299',
                                           '713941','713942','713992','713991','722310');

INSERT INTO dw.bridge_scian_eje (scian_sk, eje_sk, peso)
SELECT s.scian_sk, x.eje_sk, 1.0
FROM dw.dim_scian s
JOIN (VALUES (1, '721%'), (2, '722%'),
             (3, '711%'), (3, '712%'), (3, '713%'), (3, '5615%'),
             (4, '465915')) AS x(eje_sk, patron)
  ON s.codigo_scian LIKE x.patron
WHERE s.es_turistico
ON CONFLICT DO NOTHING;

DELETE FROM dw.bridge_scian_eje b
USING dw.dim_scian s
WHERE s.scian_sk = b.scian_sk AND NOT s.es_turistico;

-- ---------------------------------------------------------------------------
-- Paso 3. dim_establecimiento
-- ---------------------------------------------------------------------------
INSERT INTO dw.dim_establecimiento (id_denue, municipio_sk, scian_sk, estrato_sk, periodo_sk, nombre, geom)
SELECT d.id_denue,
       m.municipio_sk,
       s.scian_sk,
       ep.estrato_sk,
       p.periodo_sk,
       LEFT(d.nom_estab, 120),
       CASE WHEN d.latitud IS NOT NULL AND d.longitud IS NOT NULL
            THEN ST_SetSRID(ST_MakePoint(d.longitud, d.latitud), 4326)
       END
FROM stg.denue d
JOIN dw.dim_municipio        m  ON m.cve_geo = d.cve_ent || d.cve_mun
JOIN dw.dim_scian            s  ON s.codigo_scian = d.codigo_act
JOIN dw.dim_estrato_personal ep ON ep.rango_texto = d.per_ocu
JOIN dw.dim_periodo          p  ON p.etiqueta = 'DENUE ' || d.corte_denue
ON CONFLICT (id_denue) DO NOTHING;

-- Diagnóstico: filas de stg.denue que NO entraron (rangos con otro texto, municipios fuera del marco...).
-- SELECT d.per_ocu, COUNT(*) FROM stg.denue d
-- LEFT JOIN dw.dim_estrato_personal ep ON ep.rango_texto = d.per_ocu
-- WHERE ep.estrato_sk IS NULL GROUP BY d.per_ocu;

-- ---------------------------------------------------------------------------
-- Paso 4. fact_oferta_municipio_eje con cociente de localización
--   CL = (personal_eje_mun / personal_total_mun) / (personal_eje_estado / personal_total_estado)
-- El denominador usa TODOS los sectores (stg.totales_municipio), por eso se calcula aparte.
-- Municipios con menos de 3 unidades ponderadas se marcan 'No concluyente' (evita CL inflado)
-- y no reciben ranking (si no, un municipio con un solo hotel encabeza el eje).
-- Periodo: el corte DENUE más reciente con establecimientos cargados (sin etiqueta fija).
-- Se borra y recalcula ese periodo, así que el paso se puede repetir.
-- ---------------------------------------------------------------------------
CREATE TEMP TABLE etl_periodo_oferta ON COMMIT DROP AS
SELECT p.periodo_sk
FROM dw.dim_periodo p
WHERE p.tipo = 'denue'
  AND EXISTS (SELECT 1 FROM dw.dim_establecimiento e WHERE e.periodo_sk = p.periodo_sk)
ORDER BY p.etiqueta DESC
LIMIT 1;

DELETE FROM dw.fact_oferta_municipio_eje
WHERE periodo_sk = (SELECT periodo_sk FROM etl_periodo_oferta);

WITH p AS (
    SELECT periodo_sk FROM etl_periodo_oferta
), base AS (
    SELECT e.municipio_sk,
           b.eje_sk,
           SUM(b.peso)                  AS unidades,
           SUM(b.peso * ep.punto_medio) AS personal_est
    FROM dw.dim_establecimiento e
    JOIN p                       ON p.periodo_sk = e.periodo_sk
    JOIN dw.bridge_scian_eje b   ON b.scian_sk = e.scian_sk
    JOIN dw.dim_estrato_personal ep ON ep.estrato_sk = e.estrato_sk
    GROUP BY e.municipio_sk, b.eje_sk
), tot_mun AS (
    SELECT m.municipio_sk, t.personal_est_total
    FROM stg.totales_municipio t
    JOIN dw.dim_municipio m ON m.cve_geo = t.cve_geo
), tot_edo AS (
    SELECT SUM(personal_est_total) AS personal FROM tot_mun
), tot_eje AS (
    SELECT eje_sk, SUM(personal_est) AS personal FROM base GROUP BY eje_sk
), calc AS (
    SELECT b.municipio_sk, b.eje_sk, b.unidades, b.personal_est,
           b.personal_est / NULLIF(te.personal, 0) AS participacion,
           (b.personal_est / NULLIF(tm.personal_est_total, 0))
             / NULLIF(te.personal / NULLIF(ed.personal, 0), 0) AS cl
    FROM base b
    JOIN tot_mun tm ON tm.municipio_sk = b.municipio_sk
    JOIN tot_eje te ON te.eje_sk = b.eje_sk
    CROSS JOIN tot_edo ed
)
INSERT INTO dw.fact_oferta_municipio_eje
       (municipio_sk, eje_sk, periodo_sk, unidades, personal_est,
        participacion_estatal, cociente_localizacion, nivel_predominancia, ranking_estatal)
SELECT c.municipio_sk,
       c.eje_sk,
       (SELECT periodo_sk FROM p),
       c.unidades,
       c.personal_est,
       ROUND(c.participacion, 5),
       ROUND(c.cl, 3),
       CASE WHEN c.unidades < 3 THEN 'No concluyente'
            WHEN c.cl >= 1.5    THEN 'Alta'
            WHEN c.cl >= 1.0    THEN 'Media'
            ELSE 'Baja' END,
       CASE WHEN c.unidades >= 3
            THEN RANK() OVER (PARTITION BY c.eje_sk, (c.unidades >= 3) ORDER BY c.cl DESC NULLS LAST)
       END
FROM calc c;

-- ---------------------------------------------------------------------------
-- Paso 5. fact_censo_economico desde stg.censo_economico (mismo mapeo por prefijo)
-- ---------------------------------------------------------------------------
INSERT INTO dw.fact_censo_economico
       (municipio_sk, eje_sk, periodo_sk, unidades, personal_ocupado, va_censal_bruto_mdp, hay_confidencial)
SELECT m.municipio_sk,
       x.eje_sk,
       p.periodo_sk,
       SUM(s.unidades),
       SUM(s.personal_ocupado),
       SUM(s.va_censal_bruto),
       BOOL_OR(s.confidencial)
FROM stg.censo_economico s
JOIN dw.dim_municipio m ON m.cve_geo = s.cve_geo
JOIN dw.dim_periodo   p ON p.etiqueta = 'CE ' || s.anio_censal
CROSS JOIN LATERAL (
    SELECT CASE
             WHEN s.sector_scian LIKE '721%' THEN 1
             WHEN s.sector_scian LIKE '722%' THEN 2
             WHEN s.sector_scian LIKE '711%' OR s.sector_scian LIKE '712%'
               OR s.sector_scian LIKE '713%' OR s.sector_scian LIKE '5615%' THEN 3
           END AS eje_sk
) x
WHERE x.eje_sk IS NOT NULL
GROUP BY m.municipio_sk, x.eje_sk, p.periodo_sk
ON CONFLICT DO NOTHING;

-- ---------------------------------------------------------------------------
-- Paso 6. fact_accesibilidad (todos los pares, ~47 mil filas)
-- Supuestos DOCUMENTAR en el pitch: factor de rodeo 1.35 sobre la línea recta y
-- velocidad media 45 km/h. Reemplazar por tiempos reales (OSRM/ORS) para los pares cercanos.
-- Colindancia: las geometrías vienen simplificadas, así que dos vecinos pueden quedar con
-- un hueco o traslape mínimo; ST_Touches fallaría. Se usa una tolerancia de ~10 m.
-- ---------------------------------------------------------------------------
DELETE FROM dw.fact_accesibilidad;

INSERT INTO dw.fact_accesibilidad
       (municipio_origen_sk, municipio_destino_sk, distancia_km_recta, tiempo_min_est, es_colindante)
SELECT o.municipio_sk,
       d.municipio_sk,
       ROUND((ST_Distance(o.centroide::geography, d.centroide::geography) / 1000.0)::numeric, 2),
       ROUND((ST_Distance(o.centroide::geography, d.centroide::geography) / 1000.0 * 1.35 / 45.0 * 60.0)::numeric, 1),
       ST_DWithin(o.geom, d.geom, 0.0001)
FROM dw.dim_municipio o
JOIN dw.dim_municipio d ON d.municipio_sk <> o.municipio_sk
WHERE o.centroide IS NOT NULL AND d.centroide IS NOT NULL;

-- ---------------------------------------------------------------------------
-- Paso 7. Verificaciones (ejecutar y revisar a ojo)
-- ---------------------------------------------------------------------------
-- 7.1 Deben ser 217 municipios.
-- SELECT COUNT(*) AS municipios FROM dw.dim_municipio;

-- 7.2 Tamaño de la base (límite de la capa gratuita: ~500 MB).
-- SELECT pg_size_pretty(pg_database_size(current_database())) AS tamano_bd;
-- SELECT relname, pg_size_pretty(pg_total_relation_size(oid)) AS tamano
-- FROM pg_class WHERE relkind = 'r' AND relnamespace IN ('stg'::regnamespace, 'dw'::regnamespace)
-- ORDER BY pg_total_relation_size(oid) DESC LIMIT 10;

-- 7.3 La suma de pesos por SCIAN debe ser 1 (SCIAN sin eje asignado aparecen con 0).
-- SELECT s.codigo_scian, COALESCE(SUM(b.peso), 0) AS suma_pesos
-- FROM dw.dim_scian s LEFT JOIN dw.bridge_scian_eje b USING (scian_sk)
-- GROUP BY s.codigo_scian HAVING COALESCE(SUM(b.peso), 0) <> 1;

-- 7.4 Establecimientos sin coordenadas (afectan mapas y rutas).
-- SELECT COUNT(*) FILTER (WHERE geom IS NULL) AS sin_geom, COUNT(*) AS total FROM dw.dim_establecimiento;

-- 7.5 Municipios sin ningún establecimiento turístico cargado (revisar si es dato o es faltante).
-- SELECT m.cve_geo, m.nombre FROM dw.dim_municipio m
-- WHERE NOT EXISTS (SELECT 1 FROM dw.dim_establecimiento e WHERE e.municipio_sk = m.municipio_sk);

-- 7.6 Primer vistazo al resultado.
-- SELECT m.nombre, e.codigo AS eje, f.unidades, f.personal_est, f.cociente_localizacion, f.nivel_predominancia
-- FROM dw.fact_oferta_municipio_eje f
-- JOIN dw.dim_municipio m USING (municipio_sk) JOIN dw.dim_eje e USING (eje_sk)
-- WHERE f.nivel_predominancia = 'Alta' ORDER BY f.cociente_localizacion DESC LIMIT 20;

-- SELECT * FROM dw.v_concentracion;
