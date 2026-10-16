-- MOPEDETU · F6d del plan de afinación · Banderas con visibilidad medida
-- La bandera OFERTA_INVISIBLE medía "actividad reconocida en ruta oficial sin registro en el DENUE": eso es oferta
-- SIN REGISTRO, no invisible. Se renombra conservando su tipo_flag_sk (las filas de v1 y v2 siguen apuntando a ella
-- con el nombre correcto) y se crea la OFERTA_INVISIBLE real, que usa dw.fact_visibilidad. Idempotente.

UPDATE dw.dim_tipo_flag
SET codigo = 'OFERTA_SIN_REGISTRO',
    descripcion = 'Actividad reconocida en una ruta oficial sin registro en el DENUE (oferta informal o no registrada)'
WHERE codigo = 'OFERTA_INVISIBLE'
  AND NOT EXISTS (SELECT 1 FROM dw.dim_tipo_flag WHERE codigo = 'OFERTA_SIN_REGISTRO');

INSERT INTO dw.dim_tipo_flag (codigo, descripcion, prioridad)
SELECT 'OFERTA_INVISIBLE',
       'Oferta del eje en percentil ≥ 60 con visibilidad en percentil ≤ 35 (vistas de Wikipedia, dw.fact_visibilidad)',
       1
WHERE NOT EXISTS (SELECT 1 FROM dw.dim_tipo_flag WHERE codigo = 'OFERTA_INVISIBLE');
