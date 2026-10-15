-- MOPEDETU · Atractivos con nombre (catálogo curado + OpenStreetMap) · Rol C (Styveen)
-- Antes solo había conteos por categoría (fact_atractivo) y el modelo no veía lugares sin un negocio detrás,
-- como El Peñón de Jonotla. Idempotente.

CREATE TABLE IF NOT EXISTS dw.fact_atractivo_lugar (
    atractivo_sk  integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    municipio_sk  integer NOT NULL REFERENCES dw.dim_municipio (municipio_sk),
    nombre        text NOT NULL,
    categoria     text NOT NULL,
    actividades   text[],              -- códigos de dw.dim_actividad que este lugar respalda
    descripcion   text,
    lat           numeric,
    lon           numeric,
    origen        text NOT NULL CHECK (origen IN ('catalogo_curado', 'osm')),
    fuente_sk     integer REFERENCES dw.dim_fuente (fuente_sk),
    url           text
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_atractivo_lugar ON dw.fact_atractivo_lugar (municipio_sk, nombre);

ALTER TABLE dw.fact_atractivo_lugar ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS lectura_publica ON dw.fact_atractivo_lugar;
CREATE POLICY lectura_publica ON dw.fact_atractivo_lugar FOR SELECT USING (true);
GRANT SELECT ON dw.fact_atractivo_lugar TO anon, authenticated;
GRANT ALL ON dw.fact_atractivo_lugar TO service_role;

NOTIFY pgrst, 'reload schema';
