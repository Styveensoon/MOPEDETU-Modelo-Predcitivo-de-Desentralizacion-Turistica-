-- MOPEDETU · plan_migracion_front.md A8 · Escenarios de concentración en la base (antes solo en un JSON local)
-- Los escribe model/escenario_hhi.py con model/metricas.py (la misma fórmula que usa el tablero). Idempotente.
CREATE TABLE IF NOT EXISTS dw.fact_escenario_concentracion (
    escenario    text PRIMARY KEY CHECK (escenario IN ('hoy', 'tendencial', 'con_rutas_hipotetico')),
    hhi          numeric(8,1),
    pct_top5     numeric(5,2),
    gini         numeric(5,3),
    supuesto     text,
    modelo_sk    smallint REFERENCES dw.dim_modelo,
    version_sk   smallint REFERENCES dw.dim_version_calculo,
    calculado_en timestamptz DEFAULT now()
);
ALTER TABLE dw.fact_escenario_concentracion ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS lectura_publica ON dw.fact_escenario_concentracion;
CREATE POLICY lectura_publica ON dw.fact_escenario_concentracion FOR SELECT TO anon, authenticated USING (true);
GRANT SELECT ON dw.fact_escenario_concentracion TO anon, authenticated;
GRANT ALL ON dw.fact_escenario_concentracion TO service_role;
