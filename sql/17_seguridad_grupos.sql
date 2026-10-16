-- MOPEDETU · plan_migracion_front.md A6 · Seguridad: robo en carretera separado de los delitos en el municipio
-- Antes 'robo_transeunte_carretera' mezclaba el robo en la calle con el robo a transportista en la autopista, y un
-- municipio pequeño cruzado por una autopista (Esperanza) quedaba como el más peligroso del estado. Idempotente:
-- las filas del grupo viejo se borran y scripts/cargar_seguridad.py las vuelve a cargar separadas.
ALTER TABLE dw.fact_seguridad DROP CONSTRAINT IF EXISTS fact_seguridad_grupo_delito_check;
DELETE FROM dw.fact_seguridad WHERE grupo_delito = 'robo_transeunte_carretera';
ALTER TABLE dw.fact_seguridad ADD CONSTRAINT fact_seguridad_grupo_delito_check
  CHECK (grupo_delito IN ('homicidio', 'robo_transeunte', 'robo_carretera', 'secuestro_extorsion', 'otros'));
