-- MOPEDETU · plan_migracion_front.md A9 (parte 1) · Establecimiento → actividad
-- La misma asignación de scripts/calcular_actividades.py::detectar() (por SCIAN o por nombre), por negocio, para
-- armar circuitos y listar puntos visitables con negocios reales. Idempotente.
CREATE TABLE IF NOT EXISTS dw.fact_establecimiento_actividad (
    establecimiento_sk bigint  REFERENCES dw.dim_establecimiento,
    actividad_sk       integer REFERENCES dw.dim_actividad,
    senal              text    CHECK (senal IN ('scian', 'nombre')),
    PRIMARY KEY (establecimiento_sk, actividad_sk)
);
ALTER TABLE dw.fact_establecimiento_actividad ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS lectura_publica ON dw.fact_establecimiento_actividad;
CREATE POLICY lectura_publica ON dw.fact_establecimiento_actividad FOR SELECT TO anon, authenticated USING (true);
GRANT SELECT ON dw.fact_establecimiento_actividad TO anon, authenticated;
GRANT ALL ON dw.fact_establecimiento_actividad TO service_role;
