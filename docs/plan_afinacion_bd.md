# MOPEDETU · Plan de afinación de la base de datos

> **Para quién es:** instrucciones para Claude Code (u otra persona del equipo) que va a dejar la base de Supabase
> `Mopedetu` (proyecto `hwqphjzymxlzjdjsifpj`, esquemas `stg` y `dw`) lista para usarse como producto.
>
> **De dónde sale:** auditoría de solo lectura hecha el **15 de octubre de 2026** sobre la base viva, más medición
> de las 5 rutas propuestas con OSRM. Las cifras de la sección 1 son medidas, no estimadas.
>
> **Documentos relacionados:** `docs/Context.md`, `docs/Validations.md`, `docs/datos_base.md`,
> `docs/modelo_dimensional.md`.

---

## 0. Reglas de trabajo (leer antes de tocar nada)

1. **Respaldo primero.** Antes de cualquier migración, exportar `dw` y `stg` (`pg_dump --schema=dw --schema=stg`)
   o crear una rama de Supabase. Nada se borra sin respaldo.
2. **Todo cambio de estructura va en una migración versionada** en `sql/` (siguiente número libre, por ejemplo
   `sql/09_...sql`), idempotente (`IF NOT EXISTS`, `ADD COLUMN IF NOT EXISTS`, `CREATE OR REPLACE VIEW`). Nunca
   editar tablas a mano desde el panel.
3. **Agregar, no reemplazar.** Las columnas y tablas actuales las lee el tablero (`dashboard/ficha_bd.py`,
   `v_ficha_municipio`, `v_ruta_parada`, `v_indice_municipio`). Las mejoras se agregan como columnas o versiones
   nuevas; lo viejo se retira solo cuando el código ya no lo usa.
4. **Nunca inventar datos.** Lo que no se observa queda `NULL` con su marca de calidad; no se rellena con 0 ni con
   promedios sin decirlo.
5. **Cada fuente nueva tiene su fila en `dw.dim_fuente`** con `url`, `version_corte`, `fecha_descarga`,
   `licencia_terminos`, `cobertura`, `calidad_notas` y `uso_en_modelo`.
6. **Credenciales:** solo por variables de entorno (`DATABASE_URL`, `SUPABASE_SECRET_KEY`). Nada en el repo.
7. **Después de cada fase**, correr las consultas de validación de esa fase y anotar el resultado en
   `docs/Validations.md`.
8. Tamaño actual de la base: **72 MB** (límite de la capa gratuita: 500 MB). Agregar datos agregados, no crudos.

---

## 1. Diagnóstico medido (15-oct-2026)

| # | Hallazgo | Evidencia | Gravedad |
|---|---|---|---|
| D1 | Los tiempos de `fact_accesibilidad` (línea recta × 1.8 min/km) subestiman hasta 3 veces | Rutas propuestas: café 77 min estimado vs **185** real; gastronomía 86 vs **260**; volcanes 99 vs **197** (tramo de 94 min). 3 de 5 rutas violan sus propias restricciones (75 min/tramo, 240 total) | Crítica |
| D2 | El modelo de crecimiento predice fuera de su dominio | 401 de 868 celdas tienen UE < 3 en CE 2024 (no se entrenó con ellas): mediana **+312 %**, 0 negativos, límite inferior medio +140 %. En el índice v2 reciben `score_potencial` medio 0.64 vs 0.38 y ocupan 35 de 80 lugares del top 20 por eje | Crítica |
| D3 | La "oferta turística" es 80.8 % restaurantes | Personal estimado DENUE 2026 por eje: alimentos 80.8 %, comercio 9.1 %, hospedaje 7.5 %, turismo y cultura 2.6 % | Alta |
| D4 | La cifra del problema no está contrastada con la población | Top 5: población 37.5 % (HHI 749), 4 ejes 51.9 % (1,306), **hospedaje 63.1 % (1,872)**, **turismo y cultura 77.7 % (3,478)** | Alta (y oportunidad) |
| D5 | DENUE y Censos Económicos no son fuentes independientes | Correlación de ln(1+UE) por municipio × eje DENUE 2026 vs CE 2024: **0.998** | Media (de interpretación) |
| D6 | El personal del CE está subestimado sin marca | 447 de 868 celdas CE 2024 con `hay_confidencial`; se suma solo lo publicado. Turismo y cultura: 2,293 publicado vs 4,704 estimado DENUE | Media |
| D7 | Los ceros de OSM significan "no mapeado", no "no existe" | `atractivos_osm` = 0 en 144/217; `terminales_autobus` = 0 en 183/217. `pct(NaN)=0` y los ceros castigan a los municipios rurales | Media |
| D8 | Capas delgadas con mucho peso | Eventos municipales en solo **17** municipios (23 filas); lugares curados solo en Jonotla y Zoquiapan; 4 zonas INAH | Media |
| D9 | Rutas sin pernocta ni filtro de infraestructura | Paradas con 0 hospedaje: Zoquiapan, San Jerónimo Tecuanipan, Nealtican, Atzitzihuacán, Tzicatlacoyan. Ruta mezcal con 2 municipios 🔴 en infraestructura | Alta |
| D10 | Una ruta "descentraliza" hacia Angelópolis | Ecoturismo: 3 de 5 paradas no ancla en Angelópolis | Media |
| D11 | Faltan piezas declaradas | `CE 2014` existe en `dim_periodo` pero no en `fact_censo_economico`; el modelo del rol B no está en la base; `dim_modelo` no registra la línea base "solo similitud"; no hay permisos de `dev_raul`/`dev_styveen` en `dw`/`stg` | Media |
| D12 | Seguridad de Supabase | 9 vistas `SECURITY DEFINER` (ERROR del asesor); 29 tablas con RLS sin políticas; `anon` con SELECT en 40 objetos de `dw`; `public.rls_auto_enable()` ejecutable por `anon` | Media |
| D13 | Documentación vs base | `Context.md` dice Jonotla 0.86: ese valor es de `v1_base` (0.855); en `v2_con_prediccion` es **0.735** | Baja |
| D14 | Sensibilidad V6 (ya medida) | ±20 % en cada peso: el top 20 conserva 85-100 % ✅. Sin el componente de potencial: **60 %** (el componente distorsionado de D2 decide el ranking) | Informativa |

Lo que **sí está bien** y no hay que tocar: cobertura de los 217 municipios sin nulos en marginación ni pobreza,
totales del CE iguales a INEGI, claves y CHECK del DDL, versionado de pesos y modelos, catálogo de 29 rutas
oficiales.

---

## 2. Objetivo de la afinación

Que la base pueda responder, **con datos observados y su incertidumbre declarada**, cuatro preguntas que
interesan a la Secretaría de Turismo de Puebla y a un operador turístico:

1. ¿Dónde se concentra hoy el turismo (oferta **y demanda**) y cuánto más de lo que explicaría la población?
2. ¿Qué municipios tienen oferta o atractivos reales, se puede llegar a ellos en un tiempo razonable y son seguros?
3. ¿Qué puede crecer, solo donde el modelo tiene fundamento?
4. ¿Qué rutas se pueden **vender**: tiempos reales, un nodo de pernocta, temporada y riesgo conocido?

---

## 3. Fases

Orden recomendado. Cada fase dice: problema, cambios en tablas, carga, validación y criterio de aceptación.

### F0 · Respaldo y seguridad (D12)

**Cambios (`sql/09_seguridad_vistas.sql`):**

```sql
-- 1. Las vistas respetan los permisos de quien consulta
ALTER VIEW dw.v_concentracion          SET (security_invoker = on);
ALTER VIEW dw.v_crecimiento_censal     SET (security_invoker = on);
ALTER VIEW dw.v_ficha_municipio        SET (security_invoker = on);
ALTER VIEW dw.v_indice_municipio       SET (security_invoker = on);
ALTER VIEW dw.v_novedad_ruta           SET (security_invoker = on);
ALTER VIEW dw.v_panel_crecimiento      SET (security_invoker = on);
ALTER VIEW dw.v_pares_rutas_existentes SET (security_invoker = on);
ALTER VIEW dw.v_perfil_municipio       SET (security_invoker = on);
ALTER VIEW dw.v_ruta_parada            SET (security_invoker = on);

-- 2. Política de lectura en TODA tabla de dw que lean las vistas (hoy 25 tablas de dw sin política)
--    Generar con un bloque DO sobre pg_tables WHERE schemaname='dw' y sin política:
--    CREATE POLICY lectura_publica ON dw.<tabla> FOR SELECT TO anon, authenticated USING (true);

-- 3. stg NO se expone: sin GRANT a anon/authenticated (verificar que siga así)

-- 4. Función expuesta por error
REVOKE EXECUTE ON FUNCTION public.rls_auto_enable() FROM anon, authenticated;

-- 5. Roles de desarrollo (si se siguen usando): aplicar DDL/04_permisos_mopedetu.sql
```

> ⚠️ **Orden obligatorio:** crear las políticas (paso 2) **antes** de cambiar las vistas (paso 1). Si se hace al
> revés, la ficha técnica y las rutas del tablero dejan de cargar.

**Validación:**
- `get_advisors(security)` sin errores `security_definer_view` ni avisos de `rls_auto_enable`.
- Con la *publishable key*: `GET /rest/v1/v_ficha_municipio?limit=1` (perfil `dw`) responde 200 con datos.
- `python tests/test_tablero.py` pasa, incluido `test_ficha_tecnica`.

---

### F1 · Accesibilidad real (D1)

**Problema:** todas las restricciones de rutas, el índice de infraestructura, la bandera `BARRERA_ACCESO` y la
variable `min_ancla` usan tiempos en línea recta.

**Cambios en tablas:**

```sql
-- Punto de origen realista: la cabecera municipal, no el centroide del polígono
ALTER TABLE dw.dim_municipio
  ADD COLUMN IF NOT EXISTS cabecera_nombre text,
  ADD COLUMN IF NOT EXISTS cabecera_lat    numeric(9,6),
  ADD COLUMN IF NOT EXISTS cabecera_lon    numeric(9,6),
  ADD COLUMN IF NOT EXISTS anio_pueblo_magico smallint;   -- hoy solo vive en municipios_turismo.csv

ALTER TABLE dw.fact_accesibilidad
  ADD COLUMN IF NOT EXISTS distancia_km_carretera numeric(8,2),
  ADD COLUMN IF NOT EXISTS tiempo_min_carretera   numeric(8,1),
  ADD COLUMN IF NOT EXISTS fuente_tiempo          text      -- 'osrm_local' | 'osrm_publico' | 'recta_x1.8'
       CHECK (fuente_tiempo IN ('osrm_local','osrm_publico','recta_x1.8')),
  ADD COLUMN IF NOT EXISTS fecha_calculo          date;
```

`tiempo_min_est` **se conserva** (lo leen scripts actuales). Se agrega una vista de conveniencia:

```sql
CREATE OR REPLACE VIEW dw.v_tiempo_municipios AS
SELECT municipio_origen_sk, municipio_destino_sk,
       COALESCE(tiempo_min_carretera, tiempo_min_est)       AS tiempo_min,
       COALESCE(distancia_km_carretera, distancia_km_recta) AS distancia_km,
       COALESCE(fuente_tiempo, 'recta_x1.8')                AS fuente_tiempo
FROM dw.fact_accesibilidad;
```

**Carga (nuevo `scripts/calcular_tiempos_osrm.py`):**
1. Cabeceras: del ITER 2020 tomar la localidad cabecera de cada municipio (normalmente `LOC = 0001`; verificar
   contra el Catálogo Único de Claves Geoestadísticas) con `LATITUD`/`LONGITUD` (vienen en grados-minutos-segundos
   en el ITER: convertir).
2. Matriz: **OSRM local** con el extracto de México de Geofabrik (Docker `osrm/osrm-backend`, perfil `car`).
   El servidor público `router.project-osrm.org` tiene política de uso justo: sirve para pruebas, no para la matriz
   completa. Si se usa, hacerlo por lotes con el servicio `table` y registrarlo como `osrm_publico`.
3. Calcular al menos los **8,452 pares a ≤ 150 min** (universo del modelo de enlaces); idealmente los 46,872.
4. Recalcular en `fact_infraestructura`: `min_ancla_cercana`, `ancla_cercana_sk` y `min_capital` con tiempos de
   carretera. Guardar los indicadores viejos con sufijo `_recta` en vez de borrarlos.

**Validación:**
```sql
-- Cobertura
SELECT fuente_tiempo, count(*) FROM dw.fact_accesibilidad GROUP BY 1;
-- Factor real/estimado por región (esperado: > 1.8 en sierras)
SELECT m.region, round(avg(a.tiempo_min_carretera / NULLIF(a.tiempo_min_est,0)),2) factor
FROM dw.fact_accesibilidad a JOIN dw.dim_municipio m ON m.municipio_sk = a.municipio_origen_sk
WHERE a.es_colindante GROUP BY 1 ORDER BY 2 DESC;
```
**Aceptación:** ≥ 8,452 pares con `fuente_tiempo LIKE 'osrm%'`; ningún par con tiempo de carretera < tiempo en
línea recta a 90 km/h (control de errores de *snapping*).

---

### F2 · Calidad del dato y dominio de predicción (D2, D6, D7)

**2a. Marcar la calidad de cada indicador**

```sql
ALTER TABLE dw.fact_infraestructura
  ADD COLUMN IF NOT EXISTS calidad text DEFAULT 'observado'
    CHECK (calidad IN ('observado','cero_confirmado','sin_dato','estimado'));
```

Regla para indicadores de OSM (`atractivos_osm`, `terminales_autobus`, `km_vias_principales`):
- Calcular un **índice de completitud OSM** por municipio = POIs de OSM con nombre / establecimientos DENUE
  (ya existe la comparación en `scripts/buscar_osm_nuevos.py`). Guardarlo como indicador `completitud_osm`.
- Si `valor = 0` y `completitud_osm` < P25 estatal → `calidad = 'sin_dato'` y `valor = NULL`.
- Si `valor = 0` y la completitud es buena → `cero_confirmado`.

**Cambio de código asociado:** en `model/base.py` y `scripts/calcular_ficha.py`, `pct(NaN)` debe dar **0.5**
(neutral) o excluirse del promedio ponderado y renormalizar, no **0**. Documentarlo en `Validations.md` §1.1.

**2b. Confidencialidad del censo**

```sql
ALTER TABLE dw.fact_censo_economico
  ADD COLUMN IF NOT EXISTS unidades_con_personal_publicado integer,  -- UE de códigos con personal visible
  ADD COLUMN IF NOT EXISTS pct_personal_cubierto numeric(5,2);       -- 100 · UE publicadas / UE totales
```

Así `personal_ocupado` se puede leer como "al menos X" y filtrar celdas con cobertura < 80 %.

**2c. Dominio de la predicción**

```sql
ALTER TABLE dw.fact_prediccion_crecimiento
  ADD COLUMN IF NOT EXISTS unidades_base integer,
  ADD COLUMN IF NOT EXISTS en_dominio boolean,             -- unidades_base >= 3 (mismo filtro del entrenamiento)
  ADD COLUMN IF NOT EXISTS motivo_sin_prediccion text;
```

- En `model/crecimiento.py`: si `en_dominio = false`, `crecimiento_pred_pct`, intervalos y `ranking_potencial`
  quedan `NULL` con `motivo_sin_prediccion = 'base menor a 3 unidades: fuera del rango de entrenamiento'`.
- Publicar como **nuevo modelo** en `dim_modelo` (`crecimiento_ue_eje_lgbm_v2`) para no perder la corrida v1.
- El índice pasa a una nueva versión `v3_dominio_osrm` en `dim_version_calculo`: `score_potencial` solo con
  celdas en dominio; fuera de dominio, neutral (0.5) o se renormalizan los pesos.

**Validación:**
```sql
SELECT en_dominio, count(*), percentile_cont(0.5) WITHIN GROUP (ORDER BY crecimiento_pred_pct) mediana,
       sum((crecimiento_pred_pct < 0)::int) negativos
FROM dw.fact_prediccion_crecimiento WHERE modelo_sk = <nuevo> GROUP BY 1;
```
**Aceptación:** ninguna celda con `unidades_base < 3` tiene predicción; el semáforo de potencial tiene al menos 10
municipios en rojo o gris (hoy 1), o se documenta por qué no.

---

### F3 · Concentración y oferta en exceso (D3, D4, D5)

**Vistas nuevas (`sql/10_vistas_concentracion.sql`):**

```sql
-- Concentración por eje, con la población como referencia
CREATE OR REPLACE VIEW dw.v_concentracion_eje AS ...
-- columnas: periodo_sk, eje_sk (0 = 4 ejes), pct_top5, hhi, pct_top5_poblacion, hhi_poblacion,
--           municipios_con_oferta

-- Oferta en exceso de lo esperado por la población (proxy de turismo)
CREATE OR REPLACE VIEW dw.v_exceso_oferta AS ...
-- por municipio × eje: ln_po_obs = ln(1+personal_est), ln_pob = ln(poblacion_total)
-- ajuste por eje con regr_slope / regr_intercept(ln_po_obs, ln_pob) sobre los 217 municipios
-- residuo = ln_po_obs − (a + b·ln_pob); exceso_pct = (exp(residuo) − 1)·100; percentil del residuo
```

- `v_concentracion` **se conserva** (la usan el tablero y los documentos).
- `v_exceso_oferta` es la base recomendada para reemplazar `score_oferta` en el índice v3 en los ejes alimentos y
  comercio, que hoy atienden sobre todo a residentes.
- Recomendación para las banderas: `OFERTA_EMERGENTE` solo en hospedaje y turismo y cultura, o en alimentos y
  comercio **solo si** el residuo es ≥ P75.

**Registro de la dependencia DENUE ↔ CE (D5):** en `dim_fuente.calidad_notas` del DENUE y del CE, anotar que el
DENUE se actualiza a partir de los Censos Económicos (correlación medida 0.998) y no deben presentarse como dos
evidencias independientes.

**Validación:**
```sql
SELECT * FROM dw.v_concentracion_eje WHERE periodo_sk = 7 ORDER BY eje_sk;
-- Esperado (DENUE 2026-05): eje 0 = 51.9 % / 1,306; hospedaje = 63.1 % / 1,872; turismo = 77.7 % / 3,478;
-- población = 37.5 % / 749
```

---

### F4 · Completar el panel censal y traer el modelo del rol B (D11)

1. **CE 2014 en `fact_censo_economico` (`periodo_sk = 6`).** Fuente: la serie histórica homologada que publica
   INEGI con el CE 2024 (la que ya descarga `scripts/censo_economico.py` del rol B). Cargar con los **mismos
   códigos y pesos** de `bridge_scian_eje` que usan 2019 y 2024. Las unidades no se ocultan: así el modelo de
   unidades tiene **validación temporal** (entrenar 2014 → 2019, probar 2019 → 2024).
2. **Modelo del rol B en la base**: cargar `data/modelo/fact_prediccion_crecimiento.csv` en
   `dw.fact_prediccion_crecimiento` con su propio `modelo_sk` y su registro en `dim_modelo` (métricas de
   `data/modelo/metricas.csv`).
   - ⚠️ **Homologar ejes antes de cargar:** en el rol B `comercio_turistico = 5615 (agencias)`; en la base
     `comercio_turistico = artesanías, regalos y talavera` y 5615 está en turismo. Recalcular con el mapeo de
     `bridge_scian_eje` o registrar el eje del rol B con otro código. No mezclar con el mismo `eje_sk`.
   - Las anclas y regiones del rol B son las 9 del modo DEMO: volver a correr con las 12 anclas y 7 regiones de
     `dim_municipio`.
3. **Registrar en `dim_modelo`** la línea base "solo similitud" del modelo de enlaces (AUC 0.699, AP 0.019).

**Validación:**
```sql
SELECT periodo_sk, count(*), sum(unidades) FROM dw.fact_censo_economico GROUP BY 1 ORDER BY 1;  -- 3 censos × 868
SELECT nombre, tarea, metricas FROM dw.dim_modelo ORDER BY modelo_sk;
```

---

### F5 · Rutas que se puedan operar (D9, D10)

**Cambios en tablas:**

```sql
ALTER TABLE dw.fact_ruta_parada
  ADD COLUMN IF NOT EXISTS tiempo_desde_anterior_min_real numeric(6,1),
  ADD COLUMN IF NOT EXISTS distancia_desde_anterior_km_real numeric(7,2),
  ADD COLUMN IF NOT EXISTS es_pernocta boolean DEFAULT false,
  ADD COLUMN IF NOT EXISTS unidades_hospedaje integer;

ALTER TABLE dw.fact_ruta_evaluacion
  ADD COLUMN IF NOT EXISTS tiempo_total_min_real numeric(7,1),
  ADD COLUMN IF NOT EXISTS dias_sugeridos smallint,
  ADD COLUMN IF NOT EXISTS region_beneficiada text,
  ADD COLUMN IF NOT EXISTS cumple_restricciones boolean,
  ADD COLUMN IF NOT EXISTS incumplimientos text[],          -- p. ej. {'tramo>75','total>240','sin_pernocta'}
  ADD COLUMN IF NOT EXISTS paradas_infra_rojo smallint,
  ADD COLUMN IF NOT EXISTS riesgo_seguridad text;           -- se llena en F6
```

**Reglas nuevas para `model/rutas.py` (versión del optimizador v2):**
- Usar `dw.v_tiempo_municipios` (F1), no `tiempo_min_est`.
- Excluir como candidatas las paradas con semáforo de infraestructura 🔴.
- Rutas de más de 1 día (traslado + estancias > 10 h): exigir **un nodo de pernocta** con
  `unidades_hospedaje` ≥ P50 estatal (el ancla cuenta).
- `region_beneficiada` ≠ región del ancla cuando el ancla está en Angelópolis, o penalizar las rutas cuya región
  beneficiada sea Angelópolis.
- Guardar las rutas que no cumplen en `fact_ruta_evaluacion` con `cumple_restricciones = false` en vez de
  descartarlas sin rastro (sirve para explicar al jurado por qué se eligieron otras).

**Validación:**
```sql
SELECT r.nombre, e.tiempo_total_min, e.tiempo_total_min_real, e.cumple_restricciones, e.incumplimientos
FROM dw.dim_ruta r JOIN dw.fact_ruta_evaluacion e USING (ruta_sk)
WHERE r.origen = 'propuesta_modelo';
```
**Aceptación:** las 5 rutas publicadas tienen `cumple_restricciones = true` con tiempos reales y al menos una
`es_pernocta` cuando son de más de un día.

---

### F6 · Fuentes nuevas (demanda, formalidad, seguridad, visibilidad)

Cada una es independiente: se pueden hacer en cualquier orden según la disponibilidad del dato. **Todas requieren
investigación previa** (sección 5).

**6a. Demanda hotelera (DATATUR)**

```sql
CREATE TABLE IF NOT EXISTS dw.dim_destino_datatur (
  destino_sk   smallint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  nombre       text NOT NULL UNIQUE,         -- como lo publica DATATUR (p. ej. "Puebla", "Cholula")
  tipo         text                          -- ciudad, pueblo mágico, centro de playa...
);
CREATE TABLE IF NOT EXISTS dw.bridge_destino_municipio (
  destino_sk   smallint REFERENCES dw.dim_destino_datatur,
  municipio_sk smallint REFERENCES dw.dim_municipio,
  peso         numeric(4,3) DEFAULT 1,       -- si un destino abarca varios municipios
  PRIMARY KEY (destino_sk, municipio_sk)
);
CREATE TABLE IF NOT EXISTS dw.fact_demanda_hotelera (
  destino_sk            smallint REFERENCES dw.dim_destino_datatur,
  mes                   date NOT NULL,       -- primer día del mes
  cuartos_disponibles   integer,
  cuartos_ocupados      integer,
  pct_ocupacion         numeric(5,2),
  llegadas_nacionales   integer,
  llegadas_extranjeros  integer,
  estadia_promedio      numeric(4,2),
  densidad_ocupacion    numeric(4,2),
  fuente_sk             smallint REFERENCES dw.dim_fuente,
  PRIMARY KEY (destino_sk, mes)
);
```

Usos: validación **V9** (orden del proxy `intensidad_turistica` vs ocupación, criterio Spearman ≥ 0.6),
estacionalidad real para `fact_temporada`, y concentración de la **demanda** en `v_concentracion_eje`.

**6b. Prestadores formales (Registro Nacional de Turismo)**

```sql
CREATE TABLE IF NOT EXISTS dw.fact_prestador_rnt (
  municipio_sk     smallint REFERENCES dw.dim_municipio,
  giro             text NOT NULL,            -- hospedaje, agencia, guía, alimentos, operador de aventura...
  num_prestadores  integer NOT NULL,
  fecha_corte      date NOT NULL,
  fuente_sk        smallint REFERENCES dw.dim_fuente,
  PRIMARY KEY (municipio_sk, giro, fecha_corte)
);
```

Usos: segunda fuente de oferta **independiente** del DENUE (D5); convertir `reconocida_sin_registro` en una lista
para un programa de formalización.

**6c. Seguridad (SESNSP, incidencia municipal)**

```sql
CREATE TABLE IF NOT EXISTS dw.fact_seguridad (
  municipio_sk   smallint REFERENCES dw.dim_municipio,
  anio           smallint NOT NULL,
  grupo_delito   text NOT NULL,              -- agrupar: homicidio, robo a transeúnte/carretera, secuestro/extorsión, otros
  incidentes     integer NOT NULL,
  tasa_100k      numeric(8,2),               -- con población 2020 o proyección CONAPO del año
  fuente_sk      smallint REFERENCES dw.dim_fuente,
  PRIMARY KEY (municipio_sk, anio, grupo_delito)
);
```

Agregar por año y grupo (no mes × delito) para no crecer la base. **Uso con cuidado político:** como semáforo de
"riesgo para el visitante" con percentiles, nunca como etiqueta pública de "municipio peligroso". Llena
`fact_ruta_evaluacion.riesgo_seguridad`. Nota: SESNSP mide denuncias, no victimización real.

**6d. Visibilidad (para que `OFERTA_INVISIBLE` mida lo que dice)**

```sql
CREATE TABLE IF NOT EXISTS dw.fact_visibilidad (
  municipio_sk   smallint REFERENCES dw.dim_municipio,
  actividad_sk   integer  REFERENCES dw.dim_actividad,   -- NULL = municipio completo
  fuente_sk      smallint REFERENCES dw.dim_fuente,
  periodo_inicio date NOT NULL,
  periodo_fin    date NOT NULL,
  menciones      integer,                                -- boletines, notas, publicaciones
  vistas         integer,                                -- p. ej. vistas de página de Wikipedia
  resenas        integer,
  rating_medio   numeric(3,2),
  PRIMARY KEY (municipio_sk, actividad_sk, fuente_sk, periodo_inicio)
);
```

Fuentes posibles, de la más simple a la más costosa: vistas de páginas de Wikipedia por municipio (API pública
gratuita), menciones en boletines de la Secretaría (scraping de su sitio), Google Trends, reseñas. Con datos aquí:
renombrar la bandera actual a `OFERTA_SIN_REGISTRO` y crear la `OFERTA_INVISIBLE` real
(oferta ≥ P60 y visibilidad ≤ P35).

**6e. Población del año (opcional)**

Si CONAPO publica proyecciones municipales vigentes: `dw.fact_poblacion_anual (municipio_sk, anio, poblacion,
fuente_sk)` para que las tasas por habitante y el modelo no queden fijos en 2020.

---

### F7 · Catálogos y documentación (D8, D13)

- **`fact_temporada`:** ampliar eventos municipales desde el Sistema de Información Cultural y el calendario de la
  Secretaría. Meta mínima: un evento con fuente en cada municipio que aparezca en una ruta (oficial o propuesta).
  Agregar columna `cobertura` en `dim_fuente` o una vista que diga cuántos municipios tienen evento propio.
- **`fact_atractivo_lugar`:** curar lugares para los municipios de las 5 rutas propuestas (mismo formato de
  `data/catalogos/atractivos.csv`, con URL de fuente por lugar).
- **Zonas arqueológicas:** completar desde el catálogo del INAH (hoy solo 4).
- **`dim_municipio.region`:** si la Secretaría usa otra regionalización, agregar `region_vigente` sin borrar la de
  2015.
- **Docs:** corregir en `Context.md` y `resultados_modelo.md` el índice de Jonotla (0.86 es v1; v2 = 0.735) y la
  tabla de rutas; registrar V6 como ✅ (85-100 %, con la nota de D14).

---

## 4. Cómo quedan las tablas

### 4.1 Existentes que cambian

| Tabla | Cambio | Fase |
|---|---|---|
| `dim_municipio` | + `cabecera_nombre`, `cabecera_lat`, `cabecera_lon`, `anio_pueblo_magico` (y opcional `region_vigente`) | F1, F7 |
| `fact_accesibilidad` | + `distancia_km_carretera`, `tiempo_min_carretera`, `fuente_tiempo`, `fecha_calculo` | F1 |
| `fact_infraestructura` | + `calidad`; nuevo indicador `completitud_osm`; tiempos recalculados (los viejos con sufijo `_recta`) | F1, F2 |
| `fact_censo_economico` | + `unidades_con_personal_publicado`, `pct_personal_cubierto`; + filas CE 2014 | F2, F4 |
| `fact_prediccion_crecimiento` | + `unidades_base`, `en_dominio`, `motivo_sin_prediccion`; + filas del modelo v2 y del rol B | F2, F4 |
| `fact_indice_oportunidad`, `fact_flag_oportunidad` | + versión `v3_dominio_osrm` (filas nuevas, no columnas) | F2, F3 |
| `fact_ruta_parada` | + tiempos reales, `es_pernocta`, `unidades_hospedaje` | F5 |
| `fact_ruta_evaluacion` | + `tiempo_total_min_real`, `dias_sugeridos`, `region_beneficiada`, `cumple_restricciones`, `incumplimientos`, `paradas_infra_rojo`, `riesgo_seguridad` | F5, F6 |
| `dim_modelo` | + `crecimiento_ue_eje_lgbm_v2`, modelo del rol B, línea base de similitud | F2, F4 |
| `dim_tipo_flag` | + `OFERTA_SIN_REGISTRO` (y `OFERTA_INVISIBLE` real cuando haya F6d) | F6 |
| `dim_fuente` | + una fila por fuente nueva; nota DENUE ↔ CE | F3, F6 |
| 9 vistas `v_*` | `security_invoker = on` | F0 |

### 4.2 Nuevas

| Objeto | Grano | Fase |
|---|---|---|
| `v_tiempo_municipios` (vista) | par origen × destino con el mejor tiempo disponible | F1 |
| `v_concentracion_eje` (vista) | periodo × eje, con referencia de población | F3 |
| `v_exceso_oferta` (vista) | municipio × eje: residuo contra población | F3 |
| `dim_destino_datatur` + `bridge_destino_municipio` | destino DATATUR ↔ municipio | F6a |
| `fact_demanda_hotelera` | destino × mes | F6a |
| `fact_prestador_rnt` | municipio × giro × corte | F6b |
| `fact_seguridad` | municipio × año × grupo de delito | F6c |
| `fact_visibilidad` | municipio × actividad × fuente × periodo | F6d |
| `fact_poblacion_anual` (opcional) | municipio × año | F6e |

### 4.3 Matriz de bus resultante (hechos nuevos)

| Hecho \ Dimensión | Municipio | Actividad | Eje | Periodo / fecha | Fuente | Destino DATATUR |
|---|:-:|:-:|:-:|:-:|:-:|:-:|
| demanda_hotelera | (bridge) | | | ✅ | ✅ | ✅ |
| prestador_rnt | ✅ | | | ✅ | ✅ | |
| seguridad | ✅ | | | ✅ | ✅ | |
| visibilidad | ✅ | ○ | | ✅ | ✅ | |

---

## 5. Investigación pendiente (hacer antes de cargar F6 y F7)

Cada punto tiene que terminar en una fila de `dim_fuente` o en una nota de "no disponible" en `datos_base.md`.

| # | Pregunta | Dónde buscar | Qué decide |
|---|---|---|---|
| I1 | ¿Qué destinos de Puebla mide DATATUR (monitoreo hotelero) y desde qué año? | Portal DATATUR de SECTUR federal; boletines de la Secretaría de Turismo de Puebla | Si F6a es viable y para cuántos municipios |
| I2 | ¿Se pueden obtener prestadores del RNT por municipio y giro? ¿Consulta pública, datos abiertos o solicitud? | Sitio del RNT (SECTUR); datos.gob.mx; solicitud de transparencia (Plataforma Nacional de Transparencia) | F6b |
| I3 | ¿Dónde está el CSV vigente de incidencia delictiva **municipal** y qué agrupaciones de delito tiene? | Datos abiertos del SESNSP | F6c |
| I4 | ¿Cuál es el nombre oficial vigente de la dependencia ("Secretaría de Turismo" vs "Secretaría de Desarrollo Turístico") y qué regionalización usa para planear? | sectur.puebla.gob.mx; Plan Estatal de Desarrollo vigente; Periódico Oficial del Estado | Textos del tablero, `region_vigente` |
| I5 | Lista oficial de Pueblos Mágicos de Puebla con año (hoy verificada solo con prensa) | gob.mx/sectur (programa Pueblos Mágicos) | `dim_municipio.es_pueblo_magico`, `anio_pueblo_magico` |
| I6 | Cabecera municipal: ¿siempre `LOC = 0001` en el ITER? | Catálogo Único de Claves Geoestadísticas (INEGI) | F1 |
| I7 | ¿Se levanta OSRM local o se usa otra matriz (Red Nacional de Caminos de INEGI con velocidades por tipo de vía)? | Geofabrik (extracto México); documentación de OSRM; INEGI Red Nacional de Caminos | F1 |
| I8 | Términos de uso de fuentes de reseñas (Google Places, TripAdvisor): ¿se pueden almacenar? | Términos de cada API | F6d; si no se pueden guardar, usar Wikipedia y boletines |
| I9 | ¿Qué datos puede compartir la Secretaría? (encuesta de perfil del visitante, afluencia a recintos, ferias, padrón de cooperativas) | Reunión con la Secretaría; boletines trimestrales | F6a, F6d, F7 y el tema "comunitario" |
| I10 | Catálogo confiable de turismo comunitario y cooperativas turísticas (para reactivar el tema `comunitario`) | INPI (programas de turismo de naturaleza indígena), padrón de la Secretaría de Turismo estatal, redes como Tosepan | Tema comunitario en rutas |
| I11 | ¿Hay proyecciones municipales de población vigentes? | CONAPO | F6e |
| I12 | Lista completa de zonas arqueológicas abiertas y museos | INAH; Sistema de Información Cultural (Secretaría de Cultura) | F7 |

---

## 6. Catálogo de fuentes (actuales y propuestas)

**Verificar cada URL antes de usarla**; algunas cambian de ruta con frecuencia.

| Fuente | Institución | Qué aporta | Estado | URL de partida |
|---|---|---|---|---|
| DENUE 05/2026 | INEGI | Establecimientos con SCIAN, estrato y coordenadas | ✅ cargada | https://www.inegi.org.mx/contenidos/masiva/denue/denue_21_csv.zip |
| Censos Económicos 2019 y 2024 | INEGI | UE, personal, valor agregado por municipio | ✅ cargada | https://www.inegi.org.mx/programas/ce/2024/ |
| Censos Económicos serie histórica (incluye 2014) | INEGI | Tercer censo para validación temporal | 🟨 en archivos del rol B, falta en la base | Script `scripts/censo_economico.py` |
| ITER 2020 | INEGI | Población, internet, carencias, **coordenadas de localidades** (cabeceras) | ✅ cargada (falta cabecera) | https://www.inegi.org.mx/programas/ccpv/2020/ |
| Catálogo Único de Claves Geoestadísticas | INEGI | Validar cabeceras municipales | ⬜ | https://www.inegi.org.mx/app/ageeml/ |
| Marco Geoestadístico 2023 | INEGI | Polígonos | ✅ cargada | https://www.inegi.org.mx/temas/mg/ |
| Red Nacional de Caminos | INEGI | Red vial con tipo y velocidad (alternativa a OSM) | ⬜ | https://www.inegi.org.mx/temas/caminos/ |
| Índice de marginación 2020 | CONAPO | Necesidad social | ✅ (copia IndiceMx; buscar la oficial) | https://www.gob.mx/conapo |
| Proyecciones municipales de población | CONAPO | Población por año | ⬜ investigar (I11) | https://www.gob.mx/conapo |
| Pobreza municipal 2020 | CONEVAL | % de pobreza | ✅ cargada | https://www.coneval.org.mx/Medicion/Paginas/Pobreza-municipal.aspx |
| OpenStreetMap / Overpass | OSM (ODbL) | Vías, terminales, atractivos | ✅ cargada (completitud desigual) | https://overpass-api.de/ |
| Extracto OSM de México | Geofabrik | Base para OSRM local | ⬜ | https://download.geofabrik.de/north-america/mexico.html |
| OSRM | Proyecto OSRM | Tiempos por carretera | 🟨 solo en el tablero | https://project-osrm.org/ |
| DATATUR (monitoreo hotelero) | SECTUR federal | Ocupación, cuartos, llegadas, estadía | ⬜ investigar (I1) | https://www.datatur.sectur.gob.mx/ |
| Registro Nacional de Turismo | SECTUR federal | Prestadores formales por giro | ⬜ investigar (I2) | https://www.gob.mx/sectur (sección RNT) |
| Incidencia delictiva municipal | SESNSP | Seguridad | ⬜ investigar (I3) | https://www.gob.mx/sesnsp/acciones-y-programas/datos-abiertos-de-incidencia-delictiva |
| Boletines y estadística estatal | Secretaría de Turismo de Puebla | Afluencia, ocupación, eventos, menciones | ⬜ | https://sectur.puebla.gob.mx/ |
| Catálogo de rutas, Bioruta del Café, Ruta del Mezcal | Secretaría de Turismo de Puebla (visitpuebla.mx) | Rutas oficiales | ✅ cargada | https://visitpuebla.mx/ |
| Pueblos Mágicos | SECTUR federal | Nombramientos y años | 🟨 verificado con prensa (I5) | https://www.gob.mx/sectur |
| Sistema de Información Cultural | Secretaría de Cultura | Festivales, museos, recintos por municipio | 🟨 parcial | https://sic.cultura.gob.mx/ |
| Zonas arqueológicas | INAH | Arqueología | 🟨 4 zonas | https://www.inah.gob.mx/ |
| Vistas de páginas de Wikipedia | Wikimedia (API pública) | Proxy gratuito de visibilidad | ⬜ | https://wikimedia.org/api/rest_v1/ |
| Google Trends | Google | Interés de búsqueda por destino | ⬜ (sin API oficial estable) | https://trends.google.com/ |

---

## 7. Orden de reejecución después de afinar

```bash
# Estructura
sql/09_seguridad_vistas.sql            # F0 (políticas antes de cambiar las vistas)
sql/10_afinacion_columnas.sql          # F1, F2, F5: columnas nuevas
sql/11_vistas_concentracion.sql        # F3 y v_tiempo_municipios
sql/12_tablas_fuentes_nuevas.sql       # F6 (solo las que tengan dato)

# Datos y modelo
python scripts/calcular_tiempos_osrm.py        # F1 (nuevo)
python scripts/calcular_ficha.py ...           # infraestructura con tiempos reales y calidad
python scripts/cargar_datos_base.py --solo censo   # con CE 2014 (F4)
python model/indice.py
python model/crecimiento.py                    # v2 con dominio y validación temporal
python model/enlaces.py
python model/rutas.py                          # optimizador v2 con pernocta e infraestructura
python model/escenario_hhi.py
python scripts/calcular_ficha.py ...           # otra vez: semáforo de potencial
python tests/test_tablero.py
```

---

## 8. Lo que no hay que hacer

- No borrar `tiempo_min_est`, `v_concentracion` ni las versiones `v1_base` / `v2_con_prediccion`: el tablero y
  los documentos las usan.
- No rellenar celdas confidenciales ni ceros de OSM con promedios.
- No exponer `stg` a `anon`.
- No guardar datos de APIs cuyos términos lo prohíban (reseñas).
- No presentar la seguridad como etiqueta pública de un municipio.
- No mezclar ejes del rol B y del rol C con el mismo `eje_sk`.
- No usar el servidor público de OSRM para la matriz completa.

---

## 9. Lista de aceptación final

- [ ] F0: asesor de seguridad sin errores; tablero real funcionando con la *publishable key*.
- [ ] F1: ≥ 8,452 pares con tiempo de carretera; indicadores de acceso recalculados.
- [ ] F2: ninguna predicción fuera de dominio; `pct(NaN)` neutral; calidad marcada en indicadores OSM.
- [ ] F3: `v_concentracion_eje` y `v_exceso_oferta` publicadas; cifra del problema actualizada en los documentos.
- [ ] F4: tres censos en `fact_censo_economico`; modelo del rol B en la base con ejes homologados.
- [ ] F5: 5 rutas con `cumple_restricciones = true` sobre tiempos reales y con pernocta.
- [ ] F6: al menos una fuente de demanda (DATATUR) o de formalidad (RNT) cargada; V9 ejecutada si hay DATATUR.
- [ ] F7: eventos y lugares curados para los municipios de las rutas; documentación corregida.
- [ ] Todas las fuentes nuevas con fila completa en `dim_fuente`.
- [ ] `docs/Validations.md` actualizado con los resultados de cada fase.
