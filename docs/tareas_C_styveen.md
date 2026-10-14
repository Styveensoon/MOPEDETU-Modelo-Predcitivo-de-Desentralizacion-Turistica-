# Rol C · Styveen — Rutas, mapa y entregables

## Contexto del proyecto (para pegar en tu Claude)

MOPEDETU participa en el Hackathon "Puebla Turística 360°" (Tech Capital 2026; presentación el viernes 16 de octubre). Objetivo: descentralizar el turismo y la derrama económica en los 217 municipios de Puebla. Flujo: DENUE + Censos Económicos → oferta por municipio y eje (hospedaje, alimentos, turismo y cultura, comercio turístico) → índice de oportunidad + predicción de potencial → rutas nuevas, comparadas con las rutas existentes. Base de datos: PostgreSQL + PostGIS en capa gratuita (límite ~500 MB), esquemas `stg` (entrada) y `dw` (modelo). Scripts: `01_ddl_mopedetu.sql`, `02_etl_mopedetu.sql`, `03_ddl_prediccion_mopedetu.sql`.

Equipo: **Galo (A)** base de datos, oferta e índice; **Raúl (B)** datos censales y predicción; **Styveen (C)** rutas, mapa y entregables. Horario de trabajo: 10:00 a 18:00.

## Tus tablas (eres la única persona que las escribe)

`dim_ruta` y `fact_ruta_parada` (existentes y propuestas) · `fact_ruta_evaluacion` · las columnas `es_pueblo_magico`, `es_ancla` y `region` de `dim_municipio` (con `UPDATE`).

Consumes: `dim_municipio` (hoy 18:00), índice `v1_base` (jueves 13:00), predicciones de Raúl (jueves 13:30 preliminar, 15:00 final), `fact_accesibilidad`, `fact_cluster_municipio` y `fact_similitud`, y la vista `v_novedad_ruta`.

## Hoy, miércoles (hasta las 18:00)

### 1. Catálogo de rutas existentes (la tarea más importante de hoy)
Sin él no se puede afirmar que una ruta propuesta es nueva.

1. Reunir **entre 10 y 20 rutas turísticas actuales de Puebla** (Secretaría de Desarrollo Turístico, Pueblos Mágicos, rutas temáticas conocidas, sitios oficiales de municipios).
2. Por cada ruta: nombre, tema, fuente (URL) y **paradas en orden**. Si menciona localidades, asígnalas a su municipio.
3. Formato de captura (hoja de cálculo o CSV): `ruta, tema, orden, municipio, fuente_url`.
4. Cuando `dim_municipio` esté lista, cruzar los nombres con `cve_geo` (cuidado con acentos y nombres alternativos) y cargar:
   - `dim_ruta`: `origen = 'existente'`, `tipo` (`ruta_intermunicipal` o `circuito_municipal`), `tema`, `fuente_sk`.
   - `fact_ruta_parada`: `orden_parada` y `municipio_sk`.
5. Registrar cada fuente en `dim_fuente` (o usar la fila "Catálogo de rutas turísticas existentes") con fecha de consulta.

### 2. Anclas y Pueblos Mágicos
- Lista oficial de **Pueblos Mágicos de Puebla** (catálogo oficial).
- Define un **criterio de "ancla"** y documéntalo (por ejemplo, destino consolidado reconocido en un catálogo oficial).
- Prepara los `UPDATE` sobre `dim_municipio`:
  ```sql
  UPDATE dw.dim_municipio SET es_pueblo_magico = true WHERE cve_geo IN ('21...', '21...');
  UPDATE dw.dim_municipio SET es_ancla         = true WHERE cve_geo IN ('21...', '21...');
  ```
- `region` es opcional.

### 3. Esqueleto de entregables
Crear el documento de entregables (ver sección más abajo) con encabezados y responsables.

**Meta de hoy:** borrador del catálogo con al menos 10 rutas y la lista de anclas y Pueblos Mágicos.

## Mañana, jueves

| Hora | Tarea |
|---|---|
| 10:00-10:30 | Revisión conjunta |
| 10:30-11:00 | Terminar de cargar rutas existentes y marcar anclas |
| 11:00-13:00 | Prototipo del optimizador con el índice `v1_base` (o el cociente de localización si aún no existe) |
| 14:30-16:00 | Mapa; integrar la predicción de Raúl cuando la publique |
| 16:00 | **Congelar alcance** |
| 16:00-17:00 | Rerun del optimizador con el índice v2; clasificar novedad; escribir `fact_ruta_evaluacion` |
| 17:00-18:00 | Mapa exportado sin internet, capturas, video corto; ensayo del pitch |

## Optimizador de rutas

**Grafo:** nodos = municipios; aristas = `fact_accesibilidad` (tiempo estimado, no real).
**Valor de cada municipio:** combinación del índice de oportunidad, el potencial predicho y la necesidad social (pesos explícitos y documentados).
**Restricciones iniciales (a calibrar):**
- Entre 3 y 6 paradas.
- Cada tramo ≤ 75 min estimados y el total ≤ 240 min.
- Al menos un ancla (atrae el flujo) y al menos 2 municipios con flag activo.
- Perfil compatible: los municipios deben ser **similares** entre sí (misma etiqueta de clúster o similitud alta en `fact_similitud`).
- Diversidad: dos rutas propuestas no deben compartir más de la mitad de sus municipios.

**Método sugerido:** para cada ancla, construir una ruta por inserción voraz (mayor valor por minuto) y refinar con búsqueda local. Generar de **3 a 5 propuestas** y quedarse con las mejores.

**Escritura en la BD**
- `dim_ruta`: `origen = 'propuesta_modelo'`, `tipo`, `tema` (según el perfil dominante), `version_sk`, `num_municipios`, `duracion_estimada_h`, `descripcion`.
- `fact_ruta_parada`: `orden_parada`, `municipio_sk`, `eje_sk` dominante, `distancia_desde_anterior_km`, `tiempo_desde_anterior_min`, `es_ancla`, `es_emergente`, `estancia_sugerida_h`.
- `fact_ruta_evaluacion`: `tiempo_total_min`, `potencial_pred_medio_pct`, `necesidad_social_media`, `num_municipios_emergentes`, `puntaje_total`.

**Novedad:**
```sql
SELECT nombre, clasificacion_novedad, pct_tramos_existentes
FROM dw.v_novedad_ruta WHERE origen = 'propuesta_modelo';
```
Cada ruta resulta `nueva`, `parcialmente_existente` o `existente`. Presenta las tres categorías con honestidad: una ruta parcialmente existente que extiende un circuito actual a un municipio emergente también es un resultado valioso.

## Mapa

- Folium o Leaflet, con capas: índice por municipio, flags, anclas, atractivos (si existen) y rutas (existentes y propuestas con colores distintos).
- Al hacer clic en un municipio: perfil, índice, flags con su `motivo` y potencial predicho.
- **Exportar a HTML que funcione sin internet** (respaldo de la demo).
- Usa `v_concentracion` para mostrar el problema: porcentaje de la oferta en los cinco municipios principales.

## Entregables de la convocatoria (tú los compilas, cada quien aporta su parte)

| Entregable | Aporta |
|---|---|
| Descripción ejecutiva | Styveen |
| Problema y beneficiarios | Styveen (con `v_concentracion`) |
| Descripción de la solución | Styveen |
| Inventario y documentación de fuentes | **Cada quien su fila de `dim_fuente`**; Styveen compila |
| Justificación de la selección de datos | Galo (DENUE, Marco) y Raúl (censos, social) |
| Procesos de obtención, limpieza, integración y análisis | Galo (ETL) y Raúl (censos) |
| Arquitectura o metodología | Galo |
| Prototipo funcional | Styveen (mapa y rutas) + Galo (BD) |
| Evidencia de análisis y resultados | Galo (índice, sensibilidad) y Raúl (métricas) |
| Presentación y demostración | Styveen |
| Documentación del modelo de IA | Raúl |

## Estructura del pitch

1. **Problema:** concentración de la oferta turística en pocos municipios (con la cifra de `v_concentracion`).
2. **Datos:** qué fuentes, por qué, cómo se limpiaron (el criterio de datos pesa 20 %).
3. **Método:** índice de oportunidad + predicción de potencial + generación de rutas, y qué aporta la IA (explicable).
4. **Demo:** mapa; una ruta nueva y por qué se propone.
5. **Impacto:** a quién beneficia y cómo se medirá; cualquier efecto estimado se presenta como **escenario hipotético con su supuesto**, no como predicción.
6. **Límites y escalabilidad:** limitaciones honestas y extensión a otros estados con el mismo método.

**Preguntas probables del jurado** (prepárenlas):
- ¿Cómo saben que el modelo funciona? → validación temporal y líneas base.
- ¿Qué aporta la IA y no una simple regla? → predicción y agrupamiento; qué mejoran.
- ¿Qué pasa con productores que no aparecen en el DENUE? → limitación y validación de campo.
- ¿Las rutas fueron validadas con comunidades? → son hipótesis de trabajo; siguiente paso.
- ¿Cómo mediría la derrama económica? → indicadores propuestos.
- ¿Es replicable en otro estado? → fuentes nacionales.

## Reglas de corte

- Si el catálogo de rutas existentes es pequeño (menos de 10), úsalo igual para medir novedad, pero declara su cobertura.
- Si la predicción de Raúl no llega o no supera la línea base: el optimizador sigue con el índice `v1_base`.
- Recortes en orden: número de rutas propuestas (de 5 a 3), capas del mapa y, por último, el mapa interactivo (se mantiene el estático).

## Qué no hacer

- No presentar una ruta como "nueva" sin haberla comparado con el catálogo.
- No afirmar que las rutas "optimizan flujos" ni que garantizan derrama: los datos son de oferta, no de visitantes.
- No usar el usuario administrador ni subir credenciales a Git.

## Checklist final

- [ ] Catálogo de rutas existentes cargado (con fuentes)
- [ ] Anclas y Pueblos Mágicos marcados
- [ ] 3 a 5 rutas propuestas con evaluación y clasificación de novedad
- [ ] Mapa interactivo y copia exportada sin internet
- [ ] Documento de entregables completo, con todas las filas de `dim_fuente`
- [ ] Pitch ensayado al menos dos veces
- [ ] Video corto de respaldo
