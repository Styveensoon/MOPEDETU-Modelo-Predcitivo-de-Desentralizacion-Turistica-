-- MOPEDETU · plan_migracion_front.md §12.4 · Validaciones en la base (las llena scripts/validaciones.py)
-- La página "Metodología y fuentes" las muestra con ✅/⏳/❌. Idempotente.
CREATE TABLE IF NOT EXISTS dw.fact_validacion (
    codigo      text PRIMARY KEY,
    descripcion text NOT NULL,
    criterio    text NOT NULL,
    resultado   text,
    estado      text NOT NULL CHECK (estado IN ('ok', 'pendiente', 'falla')),
    fecha       timestamptz DEFAULT now()
);
ALTER TABLE dw.fact_validacion ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS lectura_publica ON dw.fact_validacion;
CREATE POLICY lectura_publica ON dw.fact_validacion FOR SELECT TO anon, authenticated USING (true);
GRANT SELECT ON dw.fact_validacion TO anon, authenticated;
GRANT ALL ON dw.fact_validacion TO service_role;
