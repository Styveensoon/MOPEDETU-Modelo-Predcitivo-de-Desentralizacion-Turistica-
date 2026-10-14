# Rol A · Galo — Base de datos, oferta e índice de oportunidad

## Contexto del proyecto (para pegar en tu Claude)

MOPEDETU participa en el Hackathon "Puebla Turística 360°" (Tech Capital 2026; presentación el viernes 16 de octubre). Objetivo: descentralizar el turismo y la derrama económica en los 217 municipios de Puebla. Flujo: DENUE + Censos Económicos → oferta por municipio y eje (hospedaje, alimentos, turismo y cultura, comercio turístico) → índice de oportunidad + predicción de potencial → rutas nuevas, comparadas con las rutas existentes. Base de datos: PostgreSQL + PostGIS en capa gratuita (límite ~500 MB), esquemas `stg` (entrada) y `dw` (modelo). Scripts: `01_ddl_mopedetu.sql`, `02_etl_mopedetu.sql`, `03_ddl_prediccion_mopedetu.sql`.

Equipo: **Galo (A)**, **Raúl (B)** datos censales y predicción, **Styveen (C)** rutas, mapa y entregables. Horario de trabajo: 10:00 a 18:00.

## Tus tablas (eres la única persona que las escribe)

`dim_municipio` · `dim_scian` · `bridge_scian_eje` · `dim_establecimiento` · `fact_oferta_municipio_eje` · `fact_accesibilidad` · `fact_indice_oportunidad` · `fact_flag_oportunidad` · `fact_cluster_municipio` · `fact_similitud` · (si sobra tiempo) `fact_atractivo` · `stg.mun_geo` · `stg.denue` · `stg.totales_municipio` · y los catálogos que siembra el DDL.

También eres la única persona que ejecuta cambios de **estructura** (DDL). Los demás proponen por Git.

## Estado actual

- [x] Script 01 ejecutado.
- [ ] Script 03 pendiente (ejecutarlo **antes** de cargar datos).
- [ ] Roles de base de datos para Raúl y Styveen.

## Hoy, miércoles (hasta las 18:00)

### 1. Terminar la base (16:00-16:30)
1. Ejecutar `03_ddl_prediccion_mopedetu.sql` y verificar:
   ```sql
   SELECT table_type, COUNT(*) FROM information_schema.tables WHERE table_schema = 'dw' GROUP BY table_type;
   -- esperado: 25 tablas y 6 vistas
   SELECT etiqueta FROM dw.dim_periodo ORDER BY anio;   -- debe incluir 'CE 2014'
   ```
2. Crear un rol por persona y darles acceso (ajusta nombres y usa contraseñas largas):
   ```sql
   CREATE ROLE dev_raul LOGIN PASSWORD '<contraseña>';
   CREATE ROLE dev_styveen LOGIN PASSWORD '<contraseña>';
   GRANT USAGE ON SCHEMA stg, dw, extensions TO dev_raul, dev_styveen;
   GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA stg, dw TO dev_raul, dev_styveen;
   GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA stg, dw TO dev_raul, dev_styveen;
   ALTER ROLE dev_raul    SET search_path = public, extensions;
   ALTER ROLE dev_styveen SET search_path = public, extensions;
   ```
   Si la conexión directa falla, usen la cadena del **pooler** del proveedor (con el pooler, el nombre de usuario suele incluir el identificador del proyecto; confírmenlo en la cadena de conexión). Compartan credenciales por un gestor de contraseñas o mensaje privado, nunca en el chat de grupo.

### 2. Marco Geoestadístico → `stg.mun_geo` → `dim_municipio` (16:30-17:15)
1. Descargar el Marco Geoestadístico (INEGI), capa municipal; filtrar la entidad `21` (deben ser 217).
2. Con geopandas: reproyectar a **EPSG:4326** (el DDL lo exige), asegurar `MultiPolygon`, simplificar (por ejemplo `simplify(0.001, preserve_topology=True)`), crear `cve_geo = cve_ent + cve_mun`, renombrar la columna de geometría a `geom` y subir con `to_postgis(..., schema='stg', if_exists='append')`.
3. Ejecutar el **paso 0** del ETL y verificar `SELECT COUNT(*) FROM dw.dim_municipio;` (217).
4. Avisar a Raúl y Styveen que `dim_municipio` ya está lista.

### 3. DENUE → `stg.totales_municipio` y `stg.denue` (17:15-18:00, puede pasar a mañana)
1. Descarga masiva del DENUE del estado de Puebla (CSV, todos los sectores). Anota versión de corte y fecha de descarga en `dim_fuente`.
2. **Totales por municipio, todos los sectores:** `unidades_total` y `personal_est_total` (personal estimado = punto medio del estrato, igual que en `dim_estrato_personal`). Subir 217 filas a `stg.totales_municipio` con `cve_geo = cve_ent + cve_mun`.
3. **Filtrado:** códigos `codigo_act` que empiecen con 721, 722, 711, 712, 713 y 5615. Columnas: `id, nom_estab, codigo_act, nombre_act, per_ocu, cve_ent, cve_mun, latitud, longitud, fecha_alta`, más `corte_denue` (por ejemplo `2024-11`). Subir a `stg.denue` en lotes.
4. La etiqueta `'DENUE ' || corte_denue` debe existir en `dim_periodo`. Si usas otro corte, insértalo y cambia la etiqueta en el paso 4 del ETL.
5. Ejecutar pasos 1 a 3 del ETL. Revisar el diagnóstico de rangos `per_ocu` que no hicieron match.

**Meta de hoy a las 18:00:** `dim_municipio` con 217 filas, `stg.denue` cargado y `dim_establecimiento` poblada (si el DENUE se alarga, lo primero mañana).

## Mañana, jueves

| Hora | Tarea |
|---|---|
| 10:00-10:30 | Revisión conjunta del estado de las cargas |
| 10:30-12:00 | ETL pasos 4 y 6 (oferta con cociente de localización y accesibilidad); verificaciones 7.1 a 7.6; revisar tamaño de la BD |
| 12:00-13:00 | Scores del índice, versión `v1_base` → `fact_indice_oportunidad` |
| 14:30-16:00 | Flags (`fact_flag_oportunidad`), clustering y similitud |
| 16:00 | **Congelar alcance** |
| 16:00-17:00 | Recalcular índice `v2_con_prediccion` con la predicción de Raúl |
| 17:00-18:00 | Respaldo: `pg_dump` y copia local con PostGIS |

## Especificación del índice (documenta cualquier cambio)

Cada componente se normaliza entre 0 y 1 con percentiles (recortando extremos). Propuesta inicial, a calibrar:

| Score | Definición |
|---|---|
| `score_oferta` | Promedio del percentil del personal estimado y del percentil del cociente de localización (capado en 3), por eje; global = promedio de ejes |
| `score_complementarios` | Percentil de atractivos (si no hay `fact_atractivo`, redistribuir su peso y declararlo) |
| `score_accesibilidad` | 1 − percentil del tiempo estimado al ancla más cercana |
| `score_social` | Percentil del índice de marginación (más alto = más necesidad) |
| `score_potencial` | Percentil del crecimiento predicho (solo `v2`) |

`indice_oportunidad` = suma ponderada con los pesos de `dim_version_calculo`. Hacer una **sensibilidad de pesos** (variar cada peso ±0.10) y guardar cuántos municipios cambian de posición: es evidencia para el pitch.

## Flags (umbrales a calibrar, con una columna `motivo` legible)

- `OFERTA_EMERGENTE`: cociente de localización ≥ 1.5, al menos 3 unidades y no es ancla ni Pueblo Mágico.
- `ACCESIBLE_NO_EXPLOTADO`: a menos de 60 min estimados de un ancla, `score_oferta` bajo la mediana (y, en `v2`, `score_potencial` sobre la mediana).
- `BARRERA_ACCESO`: `score_oferta` en el cuartil superior y más de 120 min a un ancla.
- `IMPACTO_SOCIAL`: cualquier flag activo en un municipio con marginación alta o muy alta.

## Clustering y similitud

K-means sobre los cocientes de localización por eje (y personal en escala logarítmica), estandarizados. Elegir k con silueta (probablemente 5 a 8) y ponerle a cada grupo una etiqueta descriptiva según su perfil. Similitud coseno para los 23,436 pares (`a < b`) en `fact_similitud`.

## Lo que entregas a los demás

| Qué | Para | Límite |
|---|---|---|
| `dim_municipio` con 217 filas y geometrías | Raúl y Styveen | Hoy 18:00 |
| `fact_oferta_municipio_eje` y `fact_accesibilidad` | Raúl (variables), Styveen (grafo) | Jueves 12:00 |
| Índice `v1_base` | Styveen (optimizador de prueba) | Jueves 13:00 |
| Índice `v2_con_prediccion`, flags y clusters | Styveen | Jueves 16:30 |

## Reglas de corte

- Si el DENUE no está cargado hoy, es la prioridad uno mañana a las 10:00.
- Si el 13:00 del jueves el modelo de Raúl no supera la línea base: el índice se queda en `v1_base`.
- Si el espacio se acerca a 500 MB: vaciar `stg.denue` (conserva el CSV local).
- Recortes en orden: `fact_atractivo`, `fact_similitud`, afinar flags.

## Qué no hacer

- No editar tablas a mano desde el panel; todo cambio va en un script que se pueda repetir.
- No usar el usuario administrador en scripts ni subirlo a Git.
- No cargar el DENUE nacional ni columnas que no vas a usar.

## Checklist final

- [ ] 25 tablas y 6 vistas en `dw`
- [ ] 217 municipios con geometría
- [ ] Oferta calculada (`fact_oferta_municipio_eje`) y accesibilidad (`fact_accesibilidad`)
- [ ] Índice `v1_base` y `v2_con_prediccion`, con sensibilidad
- [ ] Flags con `motivo`, clusters y similitud
- [ ] `dim_fuente` completa para DENUE y Marco Geoestadístico
- [ ] Respaldo `pg_dump` y copia local
