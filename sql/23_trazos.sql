-- MOPEDETU · plan_migracion_front.md §12.2 · Trazo por carretera guardado (la demo no depende de OSRM en vivo)
-- geom_trazo: GeoJSON LineString (simplificado) entre las cabeceras de la ruta, calculado por
-- scripts/trazar_rutas.py. Idempotente.
ALTER TABLE dw.fact_ruta_evaluacion
  ADD COLUMN IF NOT EXISTS geom_trazo    jsonb,
  ADD COLUMN IF NOT EXISTS km_carretera  numeric(7,1),
  ADD COLUMN IF NOT EXISTS min_carretera numeric(7,1),
  ADD COLUMN IF NOT EXISTS fuente_trazo  text;
