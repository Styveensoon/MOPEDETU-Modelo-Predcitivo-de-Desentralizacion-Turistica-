-- MOPEDETU · plan_migracion_front.md A1 · Título de Wikipedia usado en cada fila de visibilidad
-- (artículo del municipio + artículo de su localidad cabecera, separados por " + "). Idempotente.
ALTER TABLE dw.fact_visibilidad ADD COLUMN IF NOT EXISTS titulo_wikipedia text;
