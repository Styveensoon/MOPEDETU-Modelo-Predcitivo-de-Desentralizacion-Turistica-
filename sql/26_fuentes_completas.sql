-- MOPEDETU · plan_afinacion §0.5 / plan_migracion_front §12.9 · Fichas completas de las fuentes del ETL original
-- Las filas 1, 2 y 6 se crearon sin versión, fecha ni licencia. Se completan con lo que usan los scripts de carga
-- (scripts/cargar_datos_base.py, scripts/cargar_municipios.py, scripts/descargar_osm.py). Idempotente.
UPDATE dw.dim_fuente SET
  version_corte = COALESCE(version_corte, '05/2026 (misma descarga que la fuente "DENUE 05/2026")'),
  fecha_descarga = COALESCE(fecha_descarga, DATE '2026-10-14'),
  licencia_terminos = COALESCE(licencia_terminos, 'Términos de Libre Uso de la Información del INEGI'),
  cobertura = COALESCE(cobertura, 'Establecimientos de los ejes turísticos de Puebla (dw.dim_establecimiento) y '
                                  'productores detectados por actividad')
WHERE fuente_sk = 1;

UPDATE dw.dim_fuente SET
  url = 'https://github.com/PhantomInsights/mexico-geojson',
  version_corte = COALESCE(version_corte, 'Marco Geoestadístico 2023 de INEGI (GeoJSON 2023/states/Puebla.json)'),
  fecha_descarga = COALESCE(fecha_descarga, DATE '2026-10-14'),
  licencia_terminos = COALESCE(licencia_terminos, 'Términos de Libre Uso de la Información del INEGI (datos de origen)'),
  cobertura = COALESCE(cobertura, '217 polígonos municipales de Puebla'),
  calidad_notas = COALESCE(calidad_notas, 'Copia en GitHub de los polígonos de INEGI 2023; simplificada para el '
                                          'tablero (data/geo/puebla_municipios.geojson). Las cabeceras salen del ITER 2020.')
WHERE fuente_sk = 2;

UPDATE dw.dim_fuente SET
  version_corte = COALESCE(version_corte, 'Consulta Overpass 2026-10-14 (atractivos con nombre)'),
  fecha_descarga = COALESCE(fecha_descarga, DATE '2026-10-14'),
  licencia_terminos = COALESCE(licencia_terminos, 'ODbL (atribución a los colaboradores de OpenStreetMap)'),
  cobertura = COALESCE(cobertura, 'Atractivos, templos, museos, cerros y naturaleza con nombre en Puebla'),
  calidad_notas = COALESCE(calidad_notas, 'Mapeo desigual: muchos municipios rurales casi sin puntos con nombre.')
WHERE fuente_sk = 6;
