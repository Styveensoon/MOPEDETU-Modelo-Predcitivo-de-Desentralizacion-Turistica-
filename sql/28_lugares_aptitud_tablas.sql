-- MOPEDETU · plan_migracion_front.md §12.3 · Lugares y aptitud de circuito como tablas calculadas por el pipeline
-- v_lugar_circuito y v_aptitud_circuito encadenaban vistas pesadas (DISTINCT ON sobre ~26 mil negocios, subconsulta
-- correlacionada, índice vigente) y la API las cortaba por 'statement timeout' (57014), incluso con la secret key;
-- una vista materializada tampoco se pudo crear dentro del tiempo del conector con la base en la capa gratuita.
-- Ahora las calcula el pipeline en Python con la MISMA lógica (sql/21 y sql/25 quedan como especificación):
--   · dw.fact_lugar_circuito   ← scripts/calcular_actividades.py (paso 'actividades')
--   · dw.fact_aptitud_circuito ← model/circuitos.py              (paso 'circuitos')
-- y las vistas públicas solo las leen. Idempotente.

CREATE TABLE IF NOT EXISTS dw.fact_lugar_circuito (
    lugar_id     text PRIMARY KEY,
    municipio_sk smallint NOT NULL REFERENCES dw.dim_municipio,
    nombre       text NOT NULL,
    actividad    text,
    categoria    text,
    tipo_parada  text NOT NULL CHECK (tipo_parada IN ('atractivo', 'experiencia', 'comida')),
    origen       text NOT NULL CHECK (origen IN ('curado', 'osm', 'denue')),
    url          text,
    personal_est numeric,
    lat          numeric(9,6),
    lon          numeric(9,6),
    prioridad    smallint NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_lugar_circuito_mun ON dw.fact_lugar_circuito (municipio_sk);

CREATE TABLE IF NOT EXISTS dw.fact_aptitud_circuito (
    municipio_sk         smallint PRIMARY KEY REFERENCES dw.dim_municipio,
    cve_geo              text,
    nombre               text,
    region               text,
    atractivos           integer,
    experiencias         integer,
    comidas              integer,
    sin_coordenadas      integer,
    actividades          integer,
    puntos_ubicados      integer,
    atractivos_ubicados  integer,
    indice_oportunidad   numeric,
    apto_por_lugares     boolean,
    apto                 boolean,
    motivo_no_apto       text,
    circuito_estandar_sk integer,
    potencial_circuito   numeric(6,4)
);

DO $$
DECLARE t text;
BEGIN
  FOREACH t IN ARRAY ARRAY['fact_lugar_circuito', 'fact_aptitud_circuito'] LOOP
    EXECUTE format('ALTER TABLE dw.%I ENABLE ROW LEVEL SECURITY', t);
    EXECUTE format('DROP POLICY IF EXISTS lectura_publica ON dw.%I', t);
    EXECUTE format('CREATE POLICY lectura_publica ON dw.%I FOR SELECT TO anon, authenticated USING (true)', t);
    EXECUTE format('GRANT SELECT ON dw.%I TO anon, authenticated', t);
    EXECUTE format('GRANT ALL ON dw.%I TO service_role', t);
  END LOOP;
END $$;

DROP VIEW IF EXISTS dw.v_aptitud_circuito;
DROP VIEW IF EXISTS dw.v_lugar_circuito;
CREATE VIEW dw.v_lugar_circuito WITH (security_invoker = on) AS SELECT * FROM dw.fact_lugar_circuito;
CREATE VIEW dw.v_aptitud_circuito WITH (security_invoker = on) AS SELECT * FROM dw.fact_aptitud_circuito;
GRANT SELECT ON dw.v_lugar_circuito, dw.v_aptitud_circuito TO anon, authenticated, service_role;
