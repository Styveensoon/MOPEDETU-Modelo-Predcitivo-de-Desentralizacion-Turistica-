-- MOPEDETU · plan_migracion_front.md A10, §12.2 · Circuitos precalculados (model/circuitos.py)
-- Un circuito sale de la cabecera municipal y regresa a ella. Los parámetros viven en dim_version_calculo
-- 'circuitos_v1' (los escribe model/circuitos.py desde model/reglas_circuitos.PARAMETROS). Idempotente.
CREATE TABLE IF NOT EXISTS dw.dim_circuito (
    circuito_sk      integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    municipio_sk     smallint REFERENCES dw.dim_municipio,
    modalidad        text CHECK (modalidad IN ('a_pie', 'auto')),
    duracion_h       numeric(3,1),
    tipo             text CHECK (tipo IN ('variado', 'tematico')),
    actividad        text,
    num_paradas      smallint,
    minutos_traslado numeric(6,1),
    duracion_min     numeric(6,1),
    es_estandar      boolean DEFAULT false,   -- el que muestra el tablero por omisión (con trazo guardado)
    cumple           boolean,
    incumplimientos  text[],
    version_sk       smallint REFERENCES dw.dim_version_calculo,
    descripcion      text,
    geom_trazo       jsonb,                   -- §12.2: trazo OSRM guardado (solo los estándar)
    km_trazo         numeric(7,2),
    min_trazo        numeric(7,1)
);
CREATE INDEX IF NOT EXISTS ix_dim_circuito_mun ON dw.dim_circuito (municipio_sk);
CREATE TABLE IF NOT EXISTS dw.fact_circuito_parada (
    circuito_sk        integer REFERENCES dw.dim_circuito ON DELETE CASCADE,
    orden              smallint,
    lugar_id           text,
    nombre             text,
    tipo_parada        text,
    actividad          text,
    categoria          text,
    origen             text,
    lat                numeric(9,6),
    lon                numeric(9,6),
    min_desde_anterior numeric(6,1),
    estancia_min       smallint,
    llegada_min        numeric(6,1),
    PRIMARY KEY (circuito_sk, orden)
);
DO $$
DECLARE t text;
BEGIN
  FOREACH t IN ARRAY ARRAY['dim_circuito', 'fact_circuito_parada'] LOOP
    EXECUTE format('ALTER TABLE dw.%I ENABLE ROW LEVEL SECURITY', t);
    EXECUTE format('DROP POLICY IF EXISTS lectura_publica ON dw.%I', t);
    EXECUTE format('CREATE POLICY lectura_publica ON dw.%I FOR SELECT TO anon, authenticated USING (true)', t);
    EXECUTE format('GRANT SELECT ON dw.%I TO anon, authenticated', t);
    EXECUTE format('GRANT ALL ON dw.%I TO service_role', t);
  END LOOP;
END $$;
