-- =============================================================================
-- MOPEDETU · Modelo dimensional (núcleo para el hackathon)
-- PostgreSQL 15+ con PostGIS · pensado para capa gratuita (~500 MB)
--
-- Convenciones: snake_case · prefijos dim_ / fact_ / bridge_ · llaves subrogadas *_sk
--               claves naturales conservadas como atributos (cve_geo, codigo_scian)
-- Idempotente: se puede volver a ejecutar sin romper lo existente.
-- Orden de uso: 01_ddl_mopedetu.sql  ->  cargar stg.*  ->  02_etl_mopedetu.sql
--
-- Ahorro de espacio: una sola copia del DENUE filtrado (stg.denue) y los hechos
-- son agregados por municipio y eje (217 municipios x pocos ejes).
-- =============================================================================

-- ---------------------------------------------------------------------------
-- 0. Extensión y esquemas
-- ---------------------------------------------------------------------------
CREATE SCHEMA IF NOT EXISTS extensions;
CREATE EXTENSION IF NOT EXISTS postgis WITH SCHEMA extensions;

-- En Supabase el search_path por defecto ya incluye "extensions". En otro Postgres,
-- ejecuta además:  ALTER DATABASE <tu_bd> SET search_path = public, extensions;
SET search_path = public, extensions;

CREATE SCHEMA IF NOT EXISTS stg;   -- datos de entrada filtrados; no se editan a mano
CREATE SCHEMA IF NOT EXISTS dw;    -- modelo dimensional

-- ---------------------------------------------------------------------------
-- 1. STAGING (entrada)
-- ---------------------------------------------------------------------------

-- DENUE ya filtrado: solo Puebla (cve_ent = '21') y solo los SCIAN de interés.
-- Cargar solo estas columnas para ahorrar espacio.
CREATE TABLE IF NOT EXISTS stg.denue (
    id_denue     text        PRIMARY KEY,
    nom_estab    text,
    codigo_act   char(6)     NOT NULL,          -- SCIAN a 6 dígitos
    nombre_act   text,
    per_ocu      text        NOT NULL,          -- rango de personal tal como viene en el DENUE
    cve_ent      char(2)     NOT NULL,
    cve_mun      char(3)     NOT NULL,
    latitud      double precision,
    longitud     double precision,
    fecha_alta   text,
    corte_denue  text        NOT NULL           -- ej. '2024-11' (debe coincidir con dw.dim_periodo)
);

-- Totales por municipio de TODOS los sectores (denominador del cociente de localización).
-- Se calcula una vez con el DENUE completo de Puebla (fuera de la BD, p. ej. en Python)
-- y se suben 217 filas. Usar el mismo método de personal estimado (punto medio del estrato).
CREATE TABLE IF NOT EXISTS stg.totales_municipio (
    cve_geo            char(5)       PRIMARY KEY,
    unidades_total     integer       NOT NULL,
    personal_est_total numeric(14,1) NOT NULL,
    corte_denue        text          NOT NULL
);

-- Marco Geoestadístico (INEGI): polígonos municipales de Puebla.
-- Cargar con geopandas.to_postgis() u ogr2ogr. Conviene simplificar la geometría
-- (ST_SimplifyPreserveTopology) para ahorrar espacio.
CREATE TABLE IF NOT EXISTS stg.mun_geo (
    cve_geo  char(5) PRIMARY KEY,
    nombre   text    NOT NULL,
    geom     geometry(MultiPolygon, 4326) NOT NULL
);

-- Censos Económicos (INEGI) a nivel municipio y subsector/rama SCIAN.
-- Las celdas confidenciales vienen vacías: marcar confidencial = true.
CREATE TABLE IF NOT EXISTS stg.censo_economico (
    cve_geo          char(5)  NOT NULL,
    anio_censal      smallint NOT NULL,         -- 2019, 2024
    sector_scian     text     NOT NULL,         -- ej. '721', '722', '5615'
    unidades         integer,
    personal_ocupado integer,
    va_censal_bruto  numeric(16,2),             -- millones de pesos
    confidencial     boolean  NOT NULL DEFAULT false,
    PRIMARY KEY (cve_geo, anio_censal, sector_scian)
);

-- ---------------------------------------------------------------------------
-- 2. DIMENSIONES
-- ---------------------------------------------------------------------------

-- Dimensión central (conformada): los 217 municipios de Puebla.
CREATE TABLE IF NOT EXISTS dw.dim_municipio (
    municipio_sk     smallint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    cve_geo          char(5)  NOT NULL UNIQUE CHECK (cve_geo ~ '^21[0-9]{3}$'),
    cve_ent          char(2)  GENERATED ALWAYS AS (substr(cve_geo, 1, 2)) STORED,
    cve_mun          char(3)  GENERATED ALWAYS AS (substr(cve_geo, 3, 3)) STORED,
    nombre           text     NOT NULL,
    region           text,                                  -- región socioeconómica
    es_pueblo_magico boolean  NOT NULL DEFAULT false,       -- catálogo oficial (carga manual)
    es_ancla         boolean  NOT NULL DEFAULT false,       -- destino consolidado (carga manual)
    superficie_km2   numeric(10,2),
    geom             geometry(MultiPolygon, 4326),
    centroide        geometry(Point, 4326)
);

-- Ejes de análisis. eje_sk = 0 es el valor "global" (índice combinado de todos los ejes).
CREATE TABLE IF NOT EXISTS dw.dim_eje (
    eje_sk       smallint PRIMARY KEY,
    codigo       text     NOT NULL UNIQUE,
    nombre       text     NOT NULL,
    descripcion  text
);

INSERT INTO dw.dim_eje (eje_sk, codigo, nombre, descripcion) VALUES
    (0, 'global',             'Global',              'Índice combinado de todos los ejes'),
    (1, 'hospedaje',          'Hospedaje',           'Hoteles, cabañas, campamentos, casas de huéspedes'),
    (2, 'alimentos',          'Alimentos y bebidas', 'Restaurantes, cafeterías, bares y preparación de alimentos'),
    (3, 'turismo',            'Turismo y cultura',   'Agencias de viajes, museos, sitios históricos, esparcimiento y recreación'),
    (4, 'comercio_turistico', 'Comercio turístico',  'Artesanías y comercio dirigido al visitante (definir códigos SCIAN)')
ON CONFLICT (eje_sk) DO NOTHING;

-- Catálogo SCIAN (se llena desde stg.denue en el ETL).
CREATE TABLE IF NOT EXISTS dw.dim_scian (
    scian_sk      integer  GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    codigo_scian  char(6)  NOT NULL UNIQUE,
    descripcion   text,
    sector        char(2),
    subsector     char(3),
    rama          char(4),
    es_turistico  boolean  NOT NULL DEFAULT true
);

-- Relación muchos a muchos SCIAN <-> eje. La suma de pesos por SCIAN debe ser 1.
CREATE TABLE IF NOT EXISTS dw.bridge_scian_eje (
    scian_sk  integer      NOT NULL REFERENCES dw.dim_scian,
    eje_sk    smallint     NOT NULL REFERENCES dw.dim_eje CHECK (eje_sk > 0),
    peso      numeric(4,3) NOT NULL DEFAULT 1 CHECK (peso > 0 AND peso <= 1),
    PRIMARY KEY (scian_sk, eje_sk)
);

-- El DENUE reporta personal por rangos. punto_medio = valor usado para estimar personal.
-- Los puntos medios son un SUPUESTO documentado (se pueden contrastar con los Censos Económicos).
CREATE TABLE IF NOT EXISTS dw.dim_estrato_personal (
    estrato_sk   smallint PRIMARY KEY,
    rango_texto  text     NOT NULL UNIQUE,
    minimo       integer  NOT NULL,
    maximo       integer,
    punto_medio  numeric(7,1) NOT NULL
);

INSERT INTO dw.dim_estrato_personal (estrato_sk, rango_texto, minimo, maximo, punto_medio) VALUES
    (1, '0 a 5 personas',     0,   5,   2.5),
    (2, '6 a 10 personas',    6,   10,  8.0),
    (3, '11 a 30 personas',   11,  30,  20.5),
    (4, '31 a 50 personas',   31,  50,  40.5),
    (5, '51 a 100 personas',  51,  100, 75.5),
    (6, '101 a 250 personas', 101, 250, 175.5),
    (7, '251 y más personas', 251, NULL, 300.0)   -- sin tope: supuesto
ON CONFLICT (estrato_sk) DO NOTHING;

-- Periodos de referencia (cortes del DENUE, censos). Ajusta las etiquetas al corte que descargues.
CREATE TABLE IF NOT EXISTS dw.dim_periodo (
    periodo_sk  smallint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    etiqueta    text     NOT NULL UNIQUE,
    anio        smallint NOT NULL,
    tipo        text     NOT NULL CHECK (tipo IN ('denue','censo_economico','censo_poblacion','otro'))
);

INSERT INTO dw.dim_periodo (etiqueta, anio, tipo) VALUES
    ('DENUE 2024-11',  2024, 'denue'),
    ('DENUE 2025-05',  2025, 'denue'),
    ('CE 2019',        2019, 'censo_economico'),
    ('CE 2024',        2024, 'censo_economico'),
    ('Censo Pob 2020', 2020, 'censo_poblacion')
ON CONFLICT (etiqueta) DO NOTHING;

-- Inventario y documentación de fuentes (entregable explícito de la convocatoria).
CREATE TABLE IF NOT EXISTS dw.dim_fuente (
    fuente_sk        smallint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    nombre           text NOT NULL UNIQUE,
    institucion      text,
    tipo             text,                 -- Oficial, Abierta colaborativa, Catálogo manual...
    url              text,
    version_corte    text,                 -- corte o edición descargada
    fecha_descarga   date,
    licencia_terminos text,                -- términos de uso / atribución requerida
    cobertura        text,
    calidad_notas    text,                 -- limitaciones conocidas
    uso_en_modelo    text                  -- para qué se usa
);

INSERT INTO dw.dim_fuente (nombre, institucion, tipo, url, uso_en_modelo) VALUES
    ('DENUE',                         'INEGI', 'Oficial',             'https://www.inegi.org.mx/app/mapa/denue/', 'Oferta por eje: establecimientos, SCIAN, estrato de personal, coordenadas'),
    ('Marco Geoestadístico',          'INEGI', 'Oficial',             'https://www.inegi.org.mx/',                'Polígonos y claves municipales, distancias'),
    ('Censos Económicos',             'INEGI', 'Oficial',             'https://www.inegi.org.mx/',                'Personal ocupado real y validación histórica 2019-2024'),
    ('Censo de Población y Vivienda', 'INEGI', 'Oficial',             'https://www.inegi.org.mx/',                'Población y contexto social'),
    ('Marginación municipal',         'CONAPO', 'Oficial',            NULL,                                       'Necesidad social (verificar medición vigente)'),
    ('OpenStreetMap',                 'OSM',   'Abierta colaborativa','https://www.openstreetmap.org/',           'Atractivos por municipio (licencia ODbL: atribución)'),
    ('Catálogo de destinos y Pueblos Mágicos', 'Secretaría de Desarrollo Turístico', 'Catálogo manual', NULL,    'Anclas y flags de visibilidad aproximada')
ON CONFLICT (nombre) DO NOTHING;

-- Establecimientos individuales (conserva las coordenadas para mapas y rutas).
CREATE TABLE IF NOT EXISTS dw.dim_establecimiento (
    establecimiento_sk  bigint   GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    id_denue            text     NOT NULL UNIQUE,
    municipio_sk        smallint NOT NULL REFERENCES dw.dim_municipio,
    scian_sk            integer  NOT NULL REFERENCES dw.dim_scian,
    estrato_sk          smallint NOT NULL REFERENCES dw.dim_estrato_personal,
    periodo_sk          smallint NOT NULL REFERENCES dw.dim_periodo,
    nombre              text,
    geom                geometry(Point, 4326)
);

-- Versiones de cálculo (pesos del índice y parámetros) para análisis de sensibilidad.
CREATE TABLE IF NOT EXISTS dw.dim_version_calculo (
    version_sk   smallint    GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    nombre       text        NOT NULL UNIQUE,
    descripcion  text,
    pesos        jsonb       NOT NULL,
    creado_en    timestamptz NOT NULL DEFAULT now()
);

INSERT INTO dw.dim_version_calculo (nombre, descripcion, pesos) VALUES
    ('v1_base', 'Pesos iniciales; calibrar con análisis de sensibilidad',
     '{"oferta":0.35,"complementarios":0.15,"accesibilidad":0.25,"social":0.25}')
ON CONFLICT (nombre) DO NOTHING;

CREATE TABLE IF NOT EXISTS dw.dim_tipo_flag (
    tipo_flag_sk  smallint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    codigo        text     NOT NULL UNIQUE,
    descripcion   text     NOT NULL,
    prioridad     smallint NOT NULL DEFAULT 3
);

INSERT INTO dw.dim_tipo_flag (codigo, descripcion, prioridad) VALUES
    ('OFERTA_EMERGENTE',      'Cociente de localización alto con volumen mínimo y sin ser ancla ni Pueblo Mágico', 1),
    ('ACCESIBLE_NO_EXPLOTADO','Cercano a un ancla y con oferta baja respecto a su potencial',                      2),
    ('BARRERA_ACCESO',        'Oferta relevante pero lejos de anclas o de municipios con servicios',               3),
    ('IMPACTO_SOCIAL',        'Flag activo en municipio con marginación alta o muy alta',                          1)
ON CONFLICT (codigo) DO NOTHING;

CREATE TABLE IF NOT EXISTS dw.dim_ruta (
    ruta_sk              integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    nombre               text    NOT NULL,
    tipo                 text    NOT NULL CHECK (tipo IN ('ruta_intermunicipal','circuito_municipal')),
    tema                 text,                                   -- mezcal, café, mixta...
    es_monotematica      boolean NOT NULL DEFAULT false,
    origen               text    NOT NULL CHECK (origen IN ('existente','propuesta_modelo')),
    version_sk           smallint REFERENCES dw.dim_version_calculo,
    num_municipios       smallint,
    duracion_estimada_h  numeric(5,1),
    descripcion          text
);

-- ---------------------------------------------------------------------------
-- 3. HECHOS
-- ---------------------------------------------------------------------------

-- Oferta por municipio x eje (calculada desde dim_establecimiento).
-- Los municipios sin establecimientos en un eje no tienen fila: tratar como 0.
CREATE TABLE IF NOT EXISTS dw.fact_oferta_municipio_eje (
    municipio_sk           smallint NOT NULL REFERENCES dw.dim_municipio,
    eje_sk                 smallint NOT NULL REFERENCES dw.dim_eje CHECK (eje_sk > 0),
    periodo_sk             smallint NOT NULL REFERENCES dw.dim_periodo,
    unidades               numeric(10,2) NOT NULL,              -- ponderado por bridge.peso
    personal_est           numeric(12,1) NOT NULL,
    participacion_estatal  numeric(8,5),                        -- % del personal estatal del eje
    cociente_localizacion  numeric(8,3),
    nivel_predominancia    text CHECK (nivel_predominancia IN ('Alta','Media','Baja','No concluyente')),
    ranking_estatal        smallint,
    PRIMARY KEY (municipio_sk, eje_sk, periodo_sk)
);

-- Personal ocupado real por eje (Censos Económicos), para validar con 2019 vs 2024.
CREATE TABLE IF NOT EXISTS dw.fact_censo_economico (
    municipio_sk         smallint NOT NULL REFERENCES dw.dim_municipio,
    eje_sk               smallint NOT NULL REFERENCES dw.dim_eje CHECK (eje_sk > 0),
    periodo_sk           smallint NOT NULL REFERENCES dw.dim_periodo,
    unidades             integer,
    personal_ocupado     integer,
    va_censal_bruto_mdp  numeric(16,2),
    hay_confidencial     boolean NOT NULL DEFAULT false,        -- suma subestimada si es true
    PRIMARY KEY (municipio_sk, eje_sk, periodo_sk)
);

CREATE TABLE IF NOT EXISTS dw.fact_contexto_social (
    municipio_sk         smallint NOT NULL REFERENCES dw.dim_municipio,
    periodo_sk           smallint NOT NULL REFERENCES dw.dim_periodo,
    poblacion_total      integer,
    indice_marginacion   numeric(8,4),
    grado_marginacion    text,                                  -- Muy bajo ... Muy alto
    pct_pobreza          numeric(5,2),
    pct_viviendas_internet numeric(5,2),
    PRIMARY KEY (municipio_sk, periodo_sk)
);

-- Atractivos complementarios (OSM, catálogos culturales, áreas naturales protegidas).
CREATE TABLE IF NOT EXISTS dw.fact_atractivo (
    municipio_sk    smallint NOT NULL REFERENCES dw.dim_municipio,
    fuente_sk       smallint NOT NULL REFERENCES dw.dim_fuente,
    categoria       text     NOT NULL,                          -- cultural, natural, religioso, histórico...
    num_atractivos  integer  NOT NULL CHECK (num_atractivos >= 0),
    fecha_corte     date,
    PRIMARY KEY (municipio_sk, fuente_sk, categoria)
);

-- Matriz origen-destino (aristas del grafo). Distancia en línea recta entre centroides;
-- tiempo_min_est es una ESTIMACIÓN (ver supuestos en 02_etl). Afinar con tiempos reales después.
CREATE TABLE IF NOT EXISTS dw.fact_accesibilidad (
    municipio_origen_sk   smallint NOT NULL REFERENCES dw.dim_municipio,
    municipio_destino_sk  smallint NOT NULL REFERENCES dw.dim_municipio,
    distancia_km_recta    numeric(7,2) NOT NULL,
    tiempo_min_est        numeric(7,1),
    es_colindante         boolean NOT NULL DEFAULT false,
    PRIMARY KEY (municipio_origen_sk, municipio_destino_sk),
    CHECK (municipio_origen_sk <> municipio_destino_sk)
);

-- Índice de oportunidad por municipio x eje (eje_sk = 0 para el global) x versión.
CREATE TABLE IF NOT EXISTS dw.fact_indice_oportunidad (
    municipio_sk          smallint NOT NULL REFERENCES dw.dim_municipio,
    eje_sk                smallint NOT NULL REFERENCES dw.dim_eje,
    periodo_sk            smallint NOT NULL REFERENCES dw.dim_periodo,
    version_sk            smallint NOT NULL REFERENCES dw.dim_version_calculo,
    score_oferta          numeric(5,4) CHECK (score_oferta          BETWEEN 0 AND 1),
    score_complementarios numeric(5,4) CHECK (score_complementarios BETWEEN 0 AND 1),
    score_accesibilidad   numeric(5,4) CHECK (score_accesibilidad   BETWEEN 0 AND 1),
    score_social          numeric(5,4) CHECK (score_social          BETWEEN 0 AND 1),
    indice_oportunidad    numeric(5,4) NOT NULL CHECK (indice_oportunidad BETWEEN 0 AND 1),
    ranking_estatal       smallint,
    PRIMARY KEY (municipio_sk, eje_sk, periodo_sk, version_sk)
);

CREATE TABLE IF NOT EXISTS dw.fact_flag_oportunidad (
    municipio_sk   smallint NOT NULL REFERENCES dw.dim_municipio,
    eje_sk         smallint NOT NULL REFERENCES dw.dim_eje,
    tipo_flag_sk   smallint NOT NULL REFERENCES dw.dim_tipo_flag,
    version_sk     smallint NOT NULL REFERENCES dw.dim_version_calculo,
    flag_activo    boolean  NOT NULL,
    motivo         text,                                        -- explicación legible (explicabilidad)
    PRIMARY KEY (municipio_sk, eje_sk, tipo_flag_sk, version_sk)
);

-- Resultado del agrupamiento (clustering) de municipios por perfil de oferta.
CREATE TABLE IF NOT EXISTS dw.fact_cluster_municipio (
    municipio_sk  smallint NOT NULL REFERENCES dw.dim_municipio,
    version_sk    smallint NOT NULL REFERENCES dw.dim_version_calculo,
    cluster_id    smallint NOT NULL,
    etiqueta      text,                                         -- nombre legible del perfil
    PRIMARY KEY (municipio_sk, version_sk)
);

-- Similitud entre pares de municipios (a < b para no duplicar). 217*216/2 = 23,436 filas.
CREATE TABLE IF NOT EXISTS dw.fact_similitud (
    municipio_a_sk  smallint NOT NULL REFERENCES dw.dim_municipio,
    municipio_b_sk  smallint NOT NULL REFERENCES dw.dim_municipio,
    version_sk      smallint NOT NULL REFERENCES dw.dim_version_calculo,
    similitud       numeric(5,4) NOT NULL CHECK (similitud BETWEEN 0 AND 1),
    PRIMARY KEY (municipio_a_sk, municipio_b_sk, version_sk),
    CHECK (municipio_a_sk < municipio_b_sk)
);

-- Paradas de cada ruta (existente o propuesta por el modelo).
CREATE TABLE IF NOT EXISTS dw.fact_ruta_parada (
    ruta_sk                    integer  NOT NULL REFERENCES dw.dim_ruta,
    orden_parada               smallint NOT NULL,
    municipio_sk               smallint NOT NULL REFERENCES dw.dim_municipio,
    eje_sk                     smallint REFERENCES dw.dim_eje,
    distancia_desde_anterior_km numeric(7,2),
    tiempo_desde_anterior_min   numeric(7,1),
    es_ancla                   boolean NOT NULL DEFAULT false,
    es_emergente               boolean NOT NULL DEFAULT false,
    estancia_sugerida_h        numeric(4,1),
    PRIMARY KEY (ruta_sk, orden_parada),
    UNIQUE (ruta_sk, municipio_sk)
);

-- ---------------------------------------------------------------------------
-- 4. ÍNDICES (pocos, por espacio)
-- ---------------------------------------------------------------------------
CREATE INDEX IF NOT EXISTS ix_estab_geom   ON dw.dim_establecimiento USING gist (geom);
CREATE INDEX IF NOT EXISTS ix_estab_mun    ON dw.dim_establecimiento (municipio_sk, scian_sk);
CREATE INDEX IF NOT EXISTS ix_acc_destino  ON dw.fact_accesibilidad (municipio_destino_sk);
CREATE INDEX IF NOT EXISTS ix_oferta_eje   ON dw.fact_oferta_municipio_eje (eje_sk, periodo_sk, cociente_localizacion DESC);
CREATE INDEX IF NOT EXISTS ix_flag_activo  ON dw.fact_flag_oportunidad (tipo_flag_sk) WHERE flag_activo;

-- ---------------------------------------------------------------------------
-- 5. VISTAS
-- ---------------------------------------------------------------------------

-- Tabla plana (una fila por municipio) lista para clustering y modelos.
CREATE OR REPLACE VIEW dw.v_perfil_municipio AS
SELECT m.municipio_sk,
       m.cve_geo,
       m.nombre,
       m.es_pueblo_magico,
       m.es_ancla,
       MAX(f.cociente_localizacion) FILTER (WHERE e.codigo = 'hospedaje')          AS cl_hospedaje,
       MAX(f.cociente_localizacion) FILTER (WHERE e.codigo = 'alimentos')          AS cl_alimentos,
       MAX(f.cociente_localizacion) FILTER (WHERE e.codigo = 'turismo')            AS cl_turismo,
       MAX(f.cociente_localizacion) FILTER (WHERE e.codigo = 'comercio_turistico') AS cl_comercio_turistico,
       MAX(f.personal_est)          FILTER (WHERE e.codigo = 'hospedaje')          AS personal_hospedaje,
       MAX(f.personal_est)          FILTER (WHERE e.codigo = 'alimentos')          AS personal_alimentos,
       MAX(f.personal_est)          FILTER (WHERE e.codigo = 'turismo')            AS personal_turismo,
       MAX(f.personal_est)          FILTER (WHERE e.codigo = 'comercio_turistico') AS personal_comercio_turistico,
       MAX(c.poblacion_total)       AS poblacion_total,
       MAX(c.indice_marginacion)    AS indice_marginacion,
       MAX(c.grado_marginacion)     AS grado_marginacion
FROM dw.dim_municipio m
LEFT JOIN dw.fact_oferta_municipio_eje f
       ON f.municipio_sk = m.municipio_sk
      AND f.periodo_sk = (SELECT MAX(periodo_sk) FROM dw.fact_oferta_municipio_eje)
LEFT JOIN dw.dim_eje e ON e.eje_sk = f.eje_sk
LEFT JOIN LATERAL (
        SELECT * FROM dw.fact_contexto_social c0
        WHERE c0.municipio_sk = m.municipio_sk
        ORDER BY c0.periodo_sk DESC LIMIT 1
     ) c ON true
GROUP BY m.municipio_sk, m.cve_geo, m.nombre, m.es_pueblo_magico, m.es_ancla;

-- Indicador de concentración de la oferta turística (problema central del proyecto):
-- % del personal estimado en los 5 municipios principales e índice HHI (0 a 10,000).
CREATE OR REPLACE VIEW dw.v_concentracion AS
WITH tot AS (
    SELECT municipio_sk, periodo_sk, SUM(personal_est) AS personal
    FROM dw.fact_oferta_municipio_eje
    GROUP BY municipio_sk, periodo_sk
), sh AS (
    SELECT periodo_sk, municipio_sk, personal,
           personal / NULLIF(SUM(personal) OVER (PARTITION BY periodo_sk), 0) AS participacion,
           RANK() OVER (PARTITION BY periodo_sk ORDER BY personal DESC)       AS rnk
    FROM tot
)
SELECT periodo_sk,
       ROUND(100 * SUM(participacion) FILTER (WHERE rnk <= 5), 1)  AS pct_top5,
       ROUND(SUM(participacion * participacion) * 10000, 0)        AS hhi,
       COUNT(*) FILTER (WHERE personal > 0)                        AS municipios_con_oferta
FROM sh
GROUP BY periodo_sk;

-- Crecimiento del personal ocupado real entre CE 2019 y CE 2024 (base de la validación hacia atrás).
CREATE OR REPLACE VIEW dw.v_crecimiento_censal AS
SELECT a.municipio_sk,
       a.eje_sk,
       a.personal_ocupado AS po_2019,
       b.personal_ocupado AS po_2024,
       b.personal_ocupado - a.personal_ocupado AS delta_abs,
       CASE WHEN a.personal_ocupado > 0
            THEN ROUND(100.0 * (b.personal_ocupado - a.personal_ocupado) / a.personal_ocupado, 1)
       END AS delta_pct
FROM dw.fact_censo_economico a
JOIN dw.dim_periodo pa ON pa.periodo_sk = a.periodo_sk AND pa.etiqueta = 'CE 2019'
JOIN dw.fact_censo_economico b ON b.municipio_sk = a.municipio_sk AND b.eje_sk = a.eje_sk
JOIN dw.dim_periodo pb ON pb.periodo_sk = b.periodo_sk AND pb.etiqueta = 'CE 2024';

-- ---------------------------------------------------------------------------
-- 6. ACCESOS (opcional; descomentar y adaptar). No usen el usuario administrador en scripts.
-- ---------------------------------------------------------------------------
-- CREATE ROLE dev_galo LOGIN PASSWORD '...';
-- GRANT USAGE ON SCHEMA stg, dw TO dev_galo;
-- GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA stg, dw TO dev_galo;
