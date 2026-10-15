-- MOPEDETU · Tablas de la ficha técnica municipal (anillos A1-A3 y semáforos) · Rol C (Styveen)
-- Ver docs/modelo_predictivo_anillos.md. Idempotente: se puede correr más de una vez.
-- Solo crea tablas nuevas; de las tablas del equipo únicamente agrega el periodo 'DENUE 2026-05' a dw.dim_periodo.

BEGIN;

-- Periodo del DENUE descargado (corte 05/2026, publicado el 2026-05-20).
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM dw.dim_periodo WHERE etiqueta = 'DENUE 2026-05') THEN
    IF (SELECT attidentity FROM pg_attribute
        WHERE attrelid = 'dw.dim_periodo'::regclass AND attname = 'periodo_sk') IN ('a', 'd') THEN
      INSERT INTO dw.dim_periodo (etiqueta, anio, tipo) VALUES ('DENUE 2026-05', 2026, 'denue');
    ELSE
      INSERT INTO dw.dim_periodo (periodo_sk, etiqueta, anio, tipo)
      SELECT coalesce(max(periodo_sk), 0) + 1, 'DENUE 2026-05', 2026, 'denue' FROM dw.dim_periodo;
    END IF;
  END IF;
END $$;

-- A1 · Actividades turísticas temáticas (café, mezcal, arqueología, …)
CREATE TABLE IF NOT EXISTS dw.dim_actividad (
    actividad_sk  integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    codigo        text NOT NULL UNIQUE,
    nombre        text NOT NULL,
    icono         text,
    eje_sk        integer REFERENCES dw.dim_eje (eje_sk),
    descripcion   text,
    reglas        jsonb            -- señales SCIAN, palabras clave y catálogos que la detectan
);

CREATE TABLE IF NOT EXISTS dw.fact_actividad_municipio (
    municipio_sk          integer NOT NULL REFERENCES dw.dim_municipio (municipio_sk),
    actividad_sk          integer NOT NULL REFERENCES dw.dim_actividad (actividad_sk),
    periodo_sk            integer NOT NULL REFERENCES dw.dim_periodo (periodo_sk),
    unidades              integer NOT NULL DEFAULT 0,
    personal_est          numeric NOT NULL DEFAULT 0,
    cociente_localizacion numeric,
    nivel_predominancia   text NOT NULL CHECK (nivel_predominancia IN
                          ('muy_alta', 'alta', 'media', 'baja', 'reconocida', 'reconocida_sin_registro', 'sin_oferta')),
    score                 numeric,
    rango_en_municipio    integer,
    es_principal          boolean NOT NULL DEFAULT false,
    senal_scian           integer NOT NULL DEFAULT 0,   -- establecimientos detectados por código SCIAN
    senal_nombre          integer NOT NULL DEFAULT 0,   -- detectados solo por palabra clave en el nombre
    senal_catalogo        boolean NOT NULL DEFAULT false, -- aparece en ruta oficial o catálogo (INAH)
    ejemplos              text[],
    PRIMARY KEY (municipio_sk, actividad_sk, periodo_sk)
);

-- A2 · Infraestructura y accesibilidad (formato largo: un indicador por fila)
CREATE TABLE IF NOT EXISTS dw.fact_infraestructura (
    municipio_sk  integer NOT NULL REFERENCES dw.dim_municipio (municipio_sk),
    indicador     text NOT NULL,     -- p. ej. min_ancla_cercana, km_via_pavimentada_km2, unidades_hospedaje
    valor         numeric,
    unidad        text,
    fuente_sk     integer REFERENCES dw.dim_fuente (fuente_sk),
    fecha_corte   date,
    PRIMARY KEY (municipio_sk, indicador)
);

-- A3 · Temporadas y eventos (municipio_sk NULL = temporada estatal o nacional)
CREATE TABLE IF NOT EXISTS dw.fact_temporada (
    temporada_sk  integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    municipio_sk  integer REFERENCES dw.dim_municipio (municipio_sk),
    actividad_sk  integer REFERENCES dw.dim_actividad (actividad_sk),
    nombre        text NOT NULL,
    tipo          text NOT NULL CHECK (tipo IN ('vacacional', 'actividad', 'fiesta_patronal', 'feria', 'festival', 'natural')),
    mes_inicio    smallint NOT NULL CHECK (mes_inicio BETWEEN 1 AND 12),
    mes_fin       smallint NOT NULL CHECK (mes_fin BETWEEN 1 AND 12),
    intensidad    smallint NOT NULL DEFAULT 2 CHECK (intensidad BETWEEN 1 AND 3),
    fuente_sk     integer REFERENCES dw.dim_fuente (fuente_sk),
    url           text,
    notas         text
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_fact_temporada ON dw.fact_temporada (coalesce(municipio_sk, 0), nombre);

-- Semáforos de la ficha (uno por municipio × dimensión × versión de cálculo)
CREATE TABLE IF NOT EXISTS dw.fact_semaforo_municipio (
    municipio_sk  integer NOT NULL REFERENCES dw.dim_municipio (municipio_sk),
    version_sk    integer NOT NULL REFERENCES dw.dim_version_calculo (version_sk),
    dimension     text NOT NULL CHECK (dimension IN ('turismo_actual', 'infraestructura', 'oferta', 'potencial', 'social')),
    nivel         text NOT NULL CHECK (nivel IN ('verde', 'amarillo', 'rojo', 'gris')),
    valor         numeric,
    percentil     numeric,
    motivo        text,
    PRIMARY KEY (municipio_sk, version_sk, dimension)
);

-- Lectura pública (el tablero usa la publishable key); escritura solo con la secret key.
DO $$
DECLARE t text;
BEGIN
  FOREACH t IN ARRAY ARRAY['dim_actividad', 'fact_actividad_municipio', 'fact_infraestructura',
                           'fact_temporada', 'fact_semaforo_municipio'] LOOP
    EXECUTE format('ALTER TABLE dw.%I ENABLE ROW LEVEL SECURITY', t);
    EXECUTE format('DROP POLICY IF EXISTS lectura_publica ON dw.%I', t);
    EXECUTE format('CREATE POLICY lectura_publica ON dw.%I FOR SELECT USING (true)', t);
    EXECUTE format('GRANT SELECT ON dw.%I TO anon, authenticated', t);
    EXECUTE format('GRANT ALL ON dw.%I TO service_role', t);
  END LOOP;
END $$;

COMMIT;

NOTIFY pgrst, 'reload schema';
