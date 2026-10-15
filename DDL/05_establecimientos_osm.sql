-- =============================================================================
-- MOPEDETU · Establecimientos turísticos que no están en el DENUE (OpenStreetMap)
-- Orden: python scripts/buscar_osm_nuevos.py  ->  python scripts/cargar_osm.py
-- (cargar_osm.py sube stg.establecimiento_externo y ejecuta este archivo). Idempotente.
--
-- Por qué van aparte del DENUE:
-- - No traen personal ocupado: estrato_sk queda NULL (no se inventa un rango).
-- - Se registran en un periodo propio ('OSM AAAA-MM', tipo 'otro'). El paso 4 del ETL toma
--   solo el corte DENUE más reciente, así que NO entran al cociente de localización (el
--   denominador, stg.totales_municipio, solo cuenta el DENUE). Sirven para mapas, rutas,
--   fact_atractivo y como evidencia de oferta no registrada.
-- - id_denue guarda el id de la fuente con prefijo ('OSM:n123', 'OSM:w456').
-- =============================================================================
SET search_path = public, extensions;

-- ---------------------------------------------------------------------------
-- 1. Estructura
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS stg.establecimiento_externo (
    id_externo             text             PRIMARY KEY,   -- 'OSM:' + n/w/r + id de OSM
    fuente                 text             NOT NULL,      -- 'OpenStreetMap'
    nombre                 text             NOT NULL,
    codigo_act             char(6)          NOT NULL,      -- SCIAN asignado (ver buscar_osm_nuevos.py)
    etiqueta_osm           text,                           -- etiqueta original, p. ej. 'tourism=hotel'
    cve_geo                char(5)          NOT NULL,
    municipio              text,
    lat                    double precision NOT NULL,
    lon                    double precision NOT NULL,
    direccion              text,
    codigo_postal          text,
    telefono               text,
    correo                 text,
    sitio_web              text,
    redes_sociales         text,
    horario                text,                           -- formato opening_hours de OSM
    cocina                 text,
    estrellas              smallint,
    habitaciones           integer,
    capacidad              integer,
    accesible_silla_ruedas boolean,
    internet               text,
    acepta_tarjeta         boolean,
    cuota_entrada          boolean,
    marca                  text,                           -- brand u operator
    descripcion            text,
    wikidata               text,
    personal_ocupado       integer,                        -- NULL: la fuente no lo reporta
    ultima_edicion_osm     date,
    url_osm                text,
    corte                  text             NOT NULL,      -- fecha de los datos de OSM (AAAA-MM-DD)
    fecha_consulta         date             NOT NULL
);

ALTER TABLE dw.dim_establecimiento ALTER COLUMN estrato_sk DROP NOT NULL;
COMMENT ON COLUMN dw.dim_establecimiento.estrato_sk IS
    'NULL = personal ocupado no disponible (fuentes distintas al DENUE)';
COMMENT ON COLUMN dw.dim_establecimiento.id_denue IS
    'Id del DENUE, o id de otra fuente con prefijo (OSM:n123)';

-- ---------------------------------------------------------------------------
-- 2. Carga a dw
-- ---------------------------------------------------------------------------
INSERT INTO dw.dim_periodo (etiqueta, anio, tipo)
SELECT DISTINCT 'OSM ' || LEFT(corte, 7), LEFT(corte, 4)::smallint, 'otro'
FROM stg.establecimiento_externo
ON CONFLICT (etiqueta) DO NOTHING;

UPDATE dw.dim_fuente
   SET url = 'https://www.openstreetmap.org/',
       version_corte = (SELECT MAX(corte) FROM stg.establecimiento_externo),
       fecha_descarga = (SELECT MAX(fecha_consulta) FROM stg.establecimiento_externo),
       licencia_terminos = 'ODbL 1.0: atribución "© colaboradores de OpenStreetMap"',
       cobertura = 'Puebla; POIs con nombre de la tipología turística que no están en el DENUE',
       calidad_notas = 'Colaborativa: cobertura desigual (mejor en zonas urbanas) y sin personal '
                    || 'ocupado. Se descartaron los que coinciden con el DENUE por nombre y distancia.',
       uso_en_modelo = 'Atractivos por municipio y establecimientos no registrados en el DENUE '
                    || '(mapas y rutas; no entran al cociente de localización)'
 WHERE nombre = 'OpenStreetMap';

-- Si buscar_osm_nuevos.py cambió de opinión sobre un registro (ahora coincide con el DENUE),
-- se quita de dw.
DELETE FROM dw.dim_establecimiento e
WHERE e.id_denue LIKE 'OSM:%'
  AND NOT EXISTS (SELECT 1 FROM stg.establecimiento_externo x WHERE x.id_externo = e.id_denue);

INSERT INTO dw.dim_establecimiento (id_denue, municipio_sk, scian_sk, estrato_sk, periodo_sk, nombre, geom)
SELECT x.id_externo,
       m.municipio_sk,
       s.scian_sk,
       NULL,
       p.periodo_sk,
       LEFT(x.nombre, 120),
       ST_SetSRID(ST_MakePoint(x.lon, x.lat), 4326)
FROM stg.establecimiento_externo x
JOIN dw.dim_municipio m ON m.cve_geo = x.cve_geo
JOIN dw.dim_scian     s ON s.codigo_scian = x.codigo_act
JOIN dw.dim_periodo   p ON p.etiqueta = 'OSM ' || LEFT(x.corte, 7)
ON CONFLICT (id_denue) DO UPDATE
   SET municipio_sk = EXCLUDED.municipio_sk,
       scian_sk     = EXCLUDED.scian_sk,
       periodo_sk   = EXCLUDED.periodo_sk,
       nombre       = EXCLUDED.nombre,
       geom         = EXCLUDED.geom;

-- ---------------------------------------------------------------------------
-- 3. Vista para mapas y rutas: todos los establecimientos con su fuente y detalle
-- ---------------------------------------------------------------------------
CREATE OR REPLACE VIEW dw.v_establecimiento AS
SELECT e.establecimiento_sk,
       e.id_denue                                  AS id_fuente,
       CASE WHEN e.id_denue LIKE 'OSM:%' THEN 'OpenStreetMap' ELSE 'DENUE' END AS fuente,
       e.nombre,
       s.codigo_scian,
       s.descripcion                               AS actividad,
       ej.codigo                                   AS eje,
       m.cve_geo,
       m.nombre                                    AS municipio,
       COALESCE(ep.rango_texto, 'No disponible')   AS personal_ocupado,
       p.etiqueta                                  AS periodo,
       x.direccion, x.telefono, x.correo, x.sitio_web, x.redes_sociales, x.horario,
       x.cocina, x.estrellas, x.habitaciones, x.accesible_silla_ruedas, x.url_osm,
       e.geom
FROM dw.dim_establecimiento e
JOIN dw.dim_municipio m ON m.municipio_sk = e.municipio_sk
JOIN dw.dim_scian     s ON s.scian_sk = e.scian_sk
JOIN dw.dim_periodo   p ON p.periodo_sk = e.periodo_sk
LEFT JOIN dw.dim_estrato_personal ep ON ep.estrato_sk = e.estrato_sk
LEFT JOIN dw.bridge_scian_eje b      ON b.scian_sk = e.scian_sk
LEFT JOIN dw.dim_eje ej              ON ej.eje_sk = b.eje_sk
LEFT JOIN stg.establecimiento_externo x ON x.id_externo = e.id_denue;

-- Verificación:
-- SELECT fuente, eje, COUNT(*) FROM dw.v_establecimiento GROUP BY 1, 2 ORDER BY 1, 2;
