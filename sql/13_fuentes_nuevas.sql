-- MOPEDETU · F6 del plan de afinación · Fuentes nuevas (solo las tablas que tienen dato cargado)
-- Idempotente. Lectura pública como el resto de dw; escritura solo con service_role.

-- 6a. Demanda hotelera (DATATUR, Monitoreo Hotelero de SECTUR)
-- La publicación mensual trae cuartos disponibles y ocupados como PROMEDIO DIARIO del mes (por eso numeric) y el
-- porcentaje de ocupación; llegadas, estadía y densidad no vienen en el archivo público y quedan NULL.
CREATE TABLE IF NOT EXISTS dw.dim_destino_datatur (
    destino_sk smallint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    nombre     text NOT NULL UNIQUE,          -- como lo publica DATATUR, p. ej. "PUEBLA, PUE."
    tipo       text
);
CREATE TABLE IF NOT EXISTS dw.bridge_destino_municipio (
    destino_sk   smallint REFERENCES dw.dim_destino_datatur,
    municipio_sk smallint REFERENCES dw.dim_municipio,
    peso         numeric(4,3) DEFAULT 1,
    PRIMARY KEY (destino_sk, municipio_sk)
);
CREATE TABLE IF NOT EXISTS dw.fact_demanda_hotelera (
    destino_sk           smallint REFERENCES dw.dim_destino_datatur,
    mes                  date NOT NULL,       -- primer día del mes
    cuartos_disponibles  numeric(10,2),       -- promedio diario
    cuartos_ocupados     numeric(10,2),       -- promedio diario
    pct_ocupacion        numeric(5,2),
    llegadas_nacionales  integer,
    llegadas_extranjeros integer,
    estadia_promedio     numeric(4,2),
    densidad_ocupacion   numeric(4,2),
    es_preliminar        boolean,             -- DATATUR marca las cifras recientes como preliminares
    fuente_sk            smallint REFERENCES dw.dim_fuente,
    PRIMARY KEY (destino_sk, mes)
);

DO $$
DECLARE t text;
BEGIN
  FOREACH t IN ARRAY ARRAY['dim_destino_datatur', 'bridge_destino_municipio', 'fact_demanda_hotelera'] LOOP
    EXECUTE format('ALTER TABLE dw.%I ENABLE ROW LEVEL SECURITY', t);
    EXECUTE format('DROP POLICY IF EXISTS lectura_publica ON dw.%I', t);
    EXECUTE format('CREATE POLICY lectura_publica ON dw.%I FOR SELECT TO anon, authenticated USING (true)', t);
    EXECUTE format('GRANT SELECT ON dw.%I TO anon, authenticated', t);
    EXECUTE format('GRANT ALL ON dw.%I TO service_role', t);
  END LOOP;
END $$;

-- 6d. Visibilidad (vistas de página de Wikipedia en español, API de Wikimedia)
-- La PK del plan incluía actividad_sk, que es NULL para "municipio completo"; una PK no admite NULL, así que se usa
-- una clave sustituta y un índice único con NULLS NOT DISTINCT (PostgreSQL 15+).
CREATE TABLE IF NOT EXISTS dw.fact_visibilidad (
    visibilidad_sk integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    municipio_sk   smallint NOT NULL REFERENCES dw.dim_municipio,
    actividad_sk   integer REFERENCES dw.dim_actividad,   -- NULL = municipio completo
    fuente_sk      smallint NOT NULL REFERENCES dw.dim_fuente,
    periodo_inicio date NOT NULL,
    periodo_fin    date NOT NULL,
    menciones      integer,
    vistas         integer,
    resenas        integer,
    rating_medio   numeric(3,2),
    referencia     text                                  -- p. ej. título del artículo consultado
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_visibilidad ON dw.fact_visibilidad
    (municipio_sk, actividad_sk, fuente_sk, periodo_inicio) NULLS NOT DISTINCT;
ALTER TABLE dw.fact_visibilidad ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS lectura_publica ON dw.fact_visibilidad;
CREATE POLICY lectura_publica ON dw.fact_visibilidad FOR SELECT TO anon, authenticated USING (true);
GRANT SELECT ON dw.fact_visibilidad TO anon, authenticated;
GRANT ALL ON dw.fact_visibilidad TO service_role;

-- 6c. Seguridad (SESNSP, incidencia delictiva municipal del fuero común, metodología 2015-2025)
-- Agregado por año y grupo de delito (no mes × subtipo) para no crecer la base. Mide carpetas de investigación
-- (denuncias), no victimización. Uso: riesgo para el visitante a nivel de RUTA, nunca como etiqueta pública de un
-- municipio.
CREATE TABLE IF NOT EXISTS dw.fact_seguridad (
    municipio_sk smallint NOT NULL REFERENCES dw.dim_municipio,
    anio         smallint NOT NULL,
    grupo_delito text NOT NULL CHECK (grupo_delito IN ('homicidio', 'robo_transeunte_carretera',
                                                       'secuestro_extorsion', 'otros')),
    incidentes   integer NOT NULL,
    tasa_100k    numeric(8,2),          -- con la población CONAPO del año (dw.fact_poblacion_anual)
    fuente_sk    smallint REFERENCES dw.dim_fuente,
    PRIMARY KEY (municipio_sk, anio, grupo_delito)
);
ALTER TABLE dw.fact_seguridad ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS lectura_publica ON dw.fact_seguridad;
CREATE POLICY lectura_publica ON dw.fact_seguridad FOR SELECT TO anon, authenticated USING (true);
GRANT SELECT ON dw.fact_seguridad TO anon, authenticated;
GRANT ALL ON dw.fact_seguridad TO service_role;

-- 6e. Población por año (CONAPO, Reconstrucción y proyecciones de la población de los municipios 1990-2040)
CREATE TABLE IF NOT EXISTS dw.fact_poblacion_anual (
    municipio_sk smallint NOT NULL REFERENCES dw.dim_municipio,
    anio         smallint NOT NULL,
    poblacion    integer NOT NULL,        -- a mitad de año; 1990-2020 reconstruida, 2021-2040 proyectada
    es_proyeccion boolean NOT NULL,
    fuente_sk    smallint REFERENCES dw.dim_fuente,
    PRIMARY KEY (municipio_sk, anio)
);
ALTER TABLE dw.fact_poblacion_anual ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS lectura_publica ON dw.fact_poblacion_anual;
CREATE POLICY lectura_publica ON dw.fact_poblacion_anual FOR SELECT TO anon, authenticated USING (true);
GRANT SELECT ON dw.fact_poblacion_anual TO anon, authenticated;
GRANT ALL ON dw.fact_poblacion_anual TO service_role;
