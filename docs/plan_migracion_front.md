# MOPEDETU · Plataforma de punta a punta con datos reales

> **Para quién es:** instrucciones para Claude Code.
>
> **Resultado esperado al terminar:** la plataforma funcionando de punta a punta. Datos reales en Supabase → pipeline
> con criterios corregidos → tablero que **solo** lee la base y los productos del pipeline, y que arma rutas y
> circuitos para cualquier municipio, con las mismas reglas del modelo, sin errores y con cifras congruentes en
> todas las páginas.
>
> **De dónde sale:** revisión del código (`main`, commit `358f085`) y de la base viva `Mopedetu`
> (`hwqphjzymxlzjdjsifpj`) del **15 de octubre de 2026**, después de aplicar `docs/plan_afinacion_bd.md`.
> Este documento **reemplaza** la versión anterior de `plan_migracion_front.md`.

---

## 0. Definición de "terminado"

La plataforma está terminada cuando **todo** esto es cierto y se demostró con la salida de las pruebas (§9):

1. Ningún archivo de `dashboard/` genera, simula ni escribe a mano datos de municipios, actividades, anclas,
   regiones, pesos, umbrales, lugares o tiempos. Todo sale de Supabase (`dw`) o de un producto del pipeline guardado
   en la base.
2. `python scripts/pipeline.py` reconstruye de principio a fin índice, banderas, predicción, enlaces, rutas,
   circuitos, semáforos y escenarios, se detiene si algo falla e imprime las validaciones.
3. El tablero abre con `python iniciar.py` y las 7 páginas cargan sin excepciones con la *publishable key*.
4. **Rutas:** "Arma tu ruta" devuelve una ruta factible, o un motivo claro de por qué no la hay, para **cualquiera
   de los 217 municipios** de salida, y toda ruta mostrada cumple las reglas de §4.2. Las 5 rutas del modelo se
   reproducen con las mismas reglas.
5. **Circuitos:** para cada municipio apto (§4.3) se arma un circuito que cumple sus reglas; para los no aptos se
   dice por qué y se ofrece una ruta intermunicipal.
6. **Congruencia:** un municipio muestra el mismo índice, ranking, banderas, semáforos y predicción en todas las
   páginas, y esas cifras coinciden con la base (§9.5).
7. `docs/Context.md` y `docs/Validations.md` describen la plataforma tal como quedó (ya no hay "dos mundos").
8. **La demo no depende de servicios externos en vivo:** las rutas del modelo y los circuitos estándar tienen su
   trazo guardado, y existe una copia local de la base y un mapa HTML que funcionan sin internet (§12.2).
9. **Rendimiento:** primera carga ≤ 10 s y cambio de página ≤ 2 s con la caché caliente (§12.3).
10. Existe la página **Metodología y fuentes**, con fuentes, modelos contra líneas base, validaciones y
    limitaciones leídas de la base (§12.4), y los entregables de la convocatoria están completos con cifras reales
    (§12.9).

---

## 0.1 Calendario y corte de prioridades

La presentación es el **viernes 16 de octubre**. Este plan completo es de **2 a 4 días** de trabajo. Por eso se
divide en dos cortes. **El corte P0 se hace primero y por completo**; P1 se hace después, sin romper P0.

| Corte | Qué incluye | Para qué |
|---|---|---|
| **P0 · Antes de la presentación** | A2 (pernocta), A5 (cabeceras), A1 (visibilidad; si no da tiempo, ocultar `OFERTA_INVISIBLE` en el tablero y decirlo), A11, §12.1 (emergentes y paradas visitables), **Rutas del modelo** completa (§6.5, primera parte), **Panorama** con datos reales (§6.2), **Ficha técnica** con lo nuevo (§6.3), página **Metodología y fuentes** (§12.4), trazos guardados y respaldo sin internet (§12.2), recorrido de presentación (§12.7), entregables (§12.9). Las páginas que siguen siendo DEMO (Arma tu ruta, Circuitos, Mapa, Escenarios, Alertas, Ficha municipal) **se ocultan de la navegación**, no se muestran con datos simulados | Que todo lo que vea el jurado sea real y no falle |
| **P1 · Después** | El resto de la Fase A, Fases B a G, §12.3, §12.5, §12.6, §12.8 | Plataforma completa: rutas y circuitos para cualquier municipio |

Al terminar P0: commit, ensayo de la demo con el recorrido de §12.7 y, solo entonces, empezar P1.

---

## 1. Reglas de trabajo

1. Trabajar en una rama nueva (por ejemplo `feat/plataforma-datos-reales`). No hacer push sin que el equipo lo pida.
2. Respaldo antes de migraciones: `pg_dump --schema=dw --schema=stg` a un archivo **local** (el esquema
   `respaldo_20261015` vive en la misma base y no protege contra perder el proyecto).
3. Migraciones nuevas en `sql/` (siguiente número: `15_…`), idempotentes, con `security_invoker = on` en vistas y
   política de lectura (`lectura_publica`) en tablas nuevas.
4. El tablero usa **solo** `SUPABASE_PUBLISHABLE_KEY`. Si algo no se puede leer con esa llave, se arregla con una
   política, no cambiando de llave.
5. **Una sola fuente de verdad para cada regla.** Si una fórmula, umbral o restricción está en el pipeline, el
   front la importa; no la copia.
6. Si Supabase no responde, se muestra un error claro. No hay respaldo DEMO.
7. Al terminar cada fase: correr sus pruebas, reportar qué cambió y el resultado, y detenerse si algo no pasa.
8. Nunca inventar datos: lo que no existe se muestra como "sin dato" con su motivo.

---

## 2. Estado verificado (15-oct-2026)

### 2.1 Tablero

| Página | Fuente actual | Estado |
|---|---|---|
| 🏘️ Ficha técnica | `v_ficha_municipio` | ✅ real, faltan campos nuevos |
| 🧭 Rutas del modelo | `v_ruta_parada`, `v_indice_municipio` | ✅ real; no muestra pernocta, riesgo, `cumple_restricciones`, días ni la ruta descartada |
| 🧭 Arma tu ruta | `datos.py` + `motor.ruta_personalizada` | ❌ DEMO |
| 🏠 Panorama · 🗺️ Mapa · 🔁 Circuitos · 🔮 Simulador · 🏘️ Ficha municipal · 🚩 Alertas | `datos.py` + `motor.py` | ❌ DEMO |
| Barra lateral (`estado.py`) | `motor.Supuestos` (escenarios de inversión y promoción, horizonte 1/3/5, enfoques inventados) | ❌ DEMO |
| `tests/test_tablero.py` | Prueba las 7 páginas DEMO en 4 configuraciones | ❌ hay que reescribirlo |

### 2.2 Pipeline y base: problemas que afectan rutas, circuitos y métricas

| # | Problema | Evidencia | Efecto |
|---|---|---|---|
| P1 | Visibilidad de Wikipedia con títulos equivocados | Puebla capital #5 (7,524 vistas/año), debajo de Tecamachalco (12,645) y Cuautlancingo (11,419); Cholula #10; Cuetzalan #30 | `OFERTA_INVISIBLE` (92 banderas v3) mal calculada; esas banderas cuentan como "emergente" en las rutas |
| P2 | Pernocta con hospedaje ≥ P50 estatal = **2 unidades** | `model/rutas.py`: `hosp_p50 = hosp.median()`; pernoctas actuales en Calpan (3), Tlacuilotepec (2), Esperanza (2) | Rutas de 2 días que no se pueden operar |
| P3 | Tiempos OSRM de flujo libre (sin tráfico) | Dos rutas al límite: tramo Aquixtla → Zacapoaxtla de 75.0 min y ruta del café con 235/240 min | En la realidad no cumplen |
| P4 | 42 pares con tiempo menor que una línea recta a 90 km/h | `fact_accesibilidad` | Errores de *snapping* que pueden meter tramos imposibles |
| P5 | Coordenadas incongruentes | Los tiempos se calculan entre **cabeceras**, pero `v_ruta_parada`, `v_ficha_municipio` y `model/base.py` usan **centroides** del polígono | El trazo OSRM del tablero sale de otro punto y da otros tiempos |
| P6 | Riesgo de seguridad mal etiquetado | Esperanza aparece como P100 de "delitos al visitante" por **robo en carretera** (669/100k vs 262 en Puebla); en homicidio está por debajo de Puebla (7 vs 10) | Se estigmatiza un municipio por la autopista que lo cruza |
| P7 | `model/prediccion_crecimiento.py` importa `ANCLAS`, `haversine_km` y `region_aprox` de `dashboard/datos.py` | línea 51 | Se rompe al borrar `datos.py` |
| P8 | Escenarios de concentración solo en un JSON | `data/derivados/escenario_concentracion.json` | El tablero depende de un archivo local, no de la base |
| P9 | No existe la relación establecimiento → actividad | Solo hay el agregado `fact_actividad_municipio` | No se pueden armar circuitos temáticos con negocios reales |
| P10 | Cobertura de lugares para circuitos | Municipios con puntos de atractivo (lugares con nombre + negocios 712/713 + talleres 327111/465915): **0 en 58**, 1–2 en 58, 3–5 en 33, > 5 en 68. De 572 lugares OSM, **376 no tienen actividad** asignada | Solo ~101 municipios pueden tener un circuito con sentido |
| P11 | Documentación del optimizador | El docstring de `model/rutas.py` dice bono social 0.20 (el código usa 0.40) y hay comentarios duplicados de una "selección voraz" que ya no existe | Confunde a quien audite los criterios |

---

## 3. Fase A · Corregir datos y criterios en el pipeline

### A1 · Visibilidad (P1)
- En `scripts/cargar_visibilidad_wikipedia.py`: resolver el título correcto por municipio. Buscar con la API de
  Wikipedia (`action=query&list=search` o `rop=pageprops` con el código INEGI/Wikidata), **seguir redirecciones**
  y sumar las vistas del título canónico. Para la capital usar el artículo del municipio (no el del estado).
  Guardar el título usado en una columna `titulo_wikipedia` de `fact_visibilidad`.
- Volver a correr `sql/14_banderas_visibilidad.sql` (o el script que crea `OFERTA_INVISIBLE`).
- **Validación:** Puebla, San Pedro Cholula, Atlixco y Cuetzalan dentro del top 15 de vistas; ningún municipio
  sin título resuelto (o listado como "sin artículo").

### A2 · Pernocta (P2)
- En `model/rutas.py`: `MIN_HOSPEDAJE_PERNOCTA = 10` (unidades DENUE de hospedaje), en lugar del P50. Si ninguna
  parada emergente lo cumple, se permite la pernocta en el ancla. Si tampoco, la ruta incumple `sin_pernocta`.
- Guardar el umbral en `dim_version_calculo.pesos` de la versión del optimizador para que el front lo lea.

### A3 · Margen sobre tiempos de flujo libre (P3)
- Agregar a `dw.v_tiempo_municipios` una columna `tiempo_min_planeacion = tiempo_min × factor`, con el factor
  **por región** guardado en una tabla o en `dim_version_calculo.pesos` (valor inicial: 1.25 en Sierra Norte,
  Sierra Nororiental y Tehuacán y Sierra Negra; 1.10 en el resto). Documentarlo como **supuesto de planeación**.
- Las restricciones de 75 y 240 min se evalúan con `tiempo_min_planeacion`; el tablero muestra los dos tiempos
  (flujo libre y de planeación).

### A4 · Pares con *snapping* erróneo (P4)
- Recalcular esos 42 pares moviendo el punto a la localidad cabecera con OSRM `nearest`, o marcarlos con
  `fuente_tiempo = 'osrm_sospechoso'` y excluirlos de las rutas. Validación: 0 pares por debajo de la línea recta
  a 90 km/h entre los que usan rutas y circuitos.

### A5 · Coordenadas de cabecera en todo (P5)
- `v_ruta_parada` y `v_ficha_municipio`: `lat`/`lon` = `dim_municipio.cabecera_lat/lon` (conservar el centroide
  como `lat_centroide`/`lon_centroide` si algo lo usa).
- `model/base.py`: `mun.lat/lon` desde la cabecera.

### A6 · Seguridad (P6)
- `fact_ruta_evaluacion.riesgo_seguridad` y la ficha: separar **"delitos en el municipio"** (homicidio,
  secuestro/extorsión, robo a transeúnte) de **"robo en carretera"**, cada uno con su percentil. Si
  `fact_seguridad` mezcla transeúnte y carretera en `robo_transeunte_carretera`, separarlos en la carga.

### A7 · Rol B sin depender del front (P7)
- Crear `model/geo_utils.py` con `haversine_km`. `model/prediccion_crecimiento.py` usa las anclas y regiones de
  `dim_municipio` (vía `base.py`) y deja de importar `datos`.

### A8 · Escenarios en la base (P8)
```sql
-- sql/15_escenarios.sql
CREATE TABLE IF NOT EXISTS dw.fact_escenario_concentracion (
  escenario    text PRIMARY KEY CHECK (escenario IN ('hoy','tendencial','con_rutas_hipotetico')),
  hhi          numeric(8,1), pct_top5 numeric(5,2), gini numeric(5,3),
  supuesto     text, modelo_sk smallint, version_sk smallint, calculado_en timestamptz DEFAULT now()
);
```
`model/escenario_hhi.py` escribe aquí (y sigue escribiendo el JSON). Agregar Gini con la misma fórmula de
`motor.gini`.

### A9 · Lugares para circuitos (P9, P10)
```sql
-- sql/16_lugares_circuito.sql
CREATE TABLE IF NOT EXISTS dw.fact_establecimiento_actividad (
  establecimiento_sk bigint  REFERENCES dw.dim_establecimiento,
  actividad_sk       integer REFERENCES dw.dim_actividad,
  senal              text    CHECK (senal IN ('scian','nombre')),
  PRIMARY KEY (establecimiento_sk, actividad_sk)
);

CREATE OR REPLACE VIEW dw.v_lugar_circuito WITH (security_invoker = on) AS
-- tipo_parada: 'atractivo' | 'experiencia' | 'comida'
SELECT ... -- ver reglas de §4.3
```
- `scripts/calcular_actividades.py::detectar()` ya clasifica cada establecimiento por SCIAN y por nombre: escribir
  esa misma asignación en `fact_establecimiento_actividad` (usar `id_denue` para cruzar con `dim_establecimiento`).
- `v_lugar_circuito` une, con `lat`, `lon`, `municipio_sk`, `nombre`, `actividad` (puede ser nula), `categoria`,
  `tipo_parada`, `origen` (`curado`, `osm`, `denue`), `url` y `personal_est` (punto medio del estrato):
  1. `fact_atractivo_lugar` (580; los 376 sin actividad entran como `atractivo` sin tema).
  2. Establecimientos con SCIAN 712 y 713 de `bridge_scian_eje` → `atractivo`.
  3. Establecimientos con actividad en `fact_establecimiento_actividad` de café, mezcal, bebidas tradicionales,
     artesanías, flores y viveros → `experiencia`.
  4. Establecimientos 7225 con actividad `gastronomia` (cocina tradicional por nombre) → `comida`; el resto de 7225
     no entra, para no llenar los circuitos de fondas genéricas.
- Excluir los que no tienen nombre y los duplicados (mismo nombre normalizado a < 50 m).

### A10 · Circuitos precalculados (para velocidad y congruencia)
```sql
-- sql/17_circuitos.sql
CREATE TABLE IF NOT EXISTS dw.dim_circuito (
  circuito_sk  integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  municipio_sk smallint REFERENCES dw.dim_municipio,
  modalidad    text CHECK (modalidad IN ('a_pie','auto')),
  duracion_h   numeric(3,1), tipo text CHECK (tipo IN ('variado','tematico')),
  actividad    text, num_paradas smallint, minutos_traslado numeric(6,1),
  version_sk   smallint, descripcion text
);
CREATE TABLE IF NOT EXISTS dw.fact_circuito_parada (
  circuito_sk integer REFERENCES dw.dim_circuito, orden smallint,
  lugar_id text, nombre text, tipo_parada text, actividad text,
  lat numeric(9,6), lon numeric(9,6), min_desde_anterior numeric(6,1), estancia_min smallint,
  PRIMARY KEY (circuito_sk, orden)
);
CREATE OR REPLACE VIEW dw.v_aptitud_circuito WITH (security_invoker = on) AS ...
-- por municipio: puntos por tipo_parada, actividades distintas, apto (bool), motivo_no_apto, potencial_circuito
```
- Nuevo `model/circuitos.py`: para cada municipio apto, circuito **variado** de medio día (4 h) y de un día (8 h),
  a pie y en auto, y uno **temático** por actividad principal con ≥ 3 puntos. Usa `model/reglas_circuitos.py`
  (§4.3).

### A11 · Limpieza del optimizador (P11)
- Corregir el docstring de `model/rutas.py` (bono social 0.40, pernocta ≥ 10, tiempos de planeación) y borrar los
  comentarios duplicados de la "selección voraz".

### A12 · Orquestador
Nuevo `scripts/pipeline.py` que corre en orden, se detiene ante el primer error e imprime las validaciones:

```
calcular_actividades (con fact_establecimiento_actividad)
→ calcular_ficha (infraestructura) → model/indice.py → model/crecimiento.py → model/enlaces.py
→ banderas de visibilidad (A1) → model/rutas.py → model/circuitos.py → model/escenario_hhi.py
→ calcular_ficha (semáforos con la predicción) → validaciones V1–V9 y de §9.5
```
Opción `--desde <paso>` para retomar.

---

## 4. Fase B · Reglas compartidas (pipeline y tablero)

### 4.1 Insumos con cualquier llave

`model/base.py::cargar()` hoy usa siempre la *secret key*. Crear `model/insumos.py` con
`cargar(secreta: bool = False) -> Insumos`, que lea con `supabase_cliente.leer(..., secreta=secreta)` todo lo que
necesitan las reglas:

| Campo de `Insumos` | Fuente |
|---|---|
| `mun` (índice `municipio_sk`) | `dim_municipio` (cabecera, región, ancla, PM) + `fact_contexto_social` |
| `version_indice`, `pesos` | `dim_version_calculo` vigente |
| `indice` (mejor eje por municipio) | `fact_indice_oportunidad` de la versión vigente |
| `banderas` | `fact_flag_oportunidad` vigente activas + `dim_tipo_flag` |
| `presente` (tema → municipios) | `fact_actividad_municipio` con nivel `muy_alta`, `alta`, `reconocida`, `reconocida_sin_registro` |
| `pred` | `fact_prediccion_crecimiento` del modelo vigente, solo `en_dominio` |
| `pe_pct` | `fact_prediccion_enlace` en percentil (simétrica) |
| `tiempo`, `tiempo_plan`, `distancia` | `v_tiempo_municipios` |
| `hospedaje` | `fact_infraestructura.unidades_hospedaje` |
| `infra_rojo` | `fact_semaforo_municipio` (infraestructura = rojo) |
| `social` | `pct(−indice_marginacion)` con `base.pct` |
| `meses_fuertes` | misma función que `model/enlaces.py::meses_fuertes` |
| `tramos_oficiales` | `v_pares_rutas_existentes` |
| `parametros` | umbrales del optimizador desde `dim_version_calculo` (75, 240, 3–6 paradas, pernocta, bonos) |

`model/base.py` puede seguir existiendo para los modelos que escriben, pero `rutas.py` y `circuitos.py` usan
`insumos.py`.

### 4.2 `model/reglas_rutas.py` (sin acceso a la base)

Extraer de `model/rutas.py` las funciones internas de `main()` sin cambiar su lógica: `valor`, `recorrido`,
`dos_opt`, `construir`, `evaluar`, `especificidad` y `seleccionar`. Todas reciben `ins: Insumos`.

API pública:

```python
construir_ruta(ins, inicio_sk, tema=None, destinos=None, max_paradas=6, exigir_ancla=True) -> dict
evaluar_ruta(ins, ruta: list[int], tema) -> dict   # siempre devuelve incumplimientos, nunca None
optimizar_rutas(ins) -> (elegidas, descartadas, diagnostico)   # lo que hoy hace main()
```

**Reglas (iguales para el modelo y para el usuario):**

| Regla | Modelo | Arma tu ruta |
|---|---|---|
| Paradas | 3–6 | 3–6 (con "Yo elijo", hasta 9 y se avisa si pasa de 6) |
| Tramo máximo | 75 min de planeación | igual |
| Recorrido máximo | 240 min de planeación | igual |
| Inicio | un ancla | cualquier municipio (`exigir_ancla=False`); si no es ancla, se indica |
| Otras anclas | no permitidas | permitidas solo si el usuario las elige |
| Emergentes (con bandera) | ≥ 2 | ≥ el mínimo de la barra lateral (por defecto 2) |
| Tema | todas las paradas no ancla con el tema presente | igual; "sin tema" = paradas con cualquier tema presente y `valor` = máximo entre sus temas |
| Infraestructura 🔴 | excluida | excluida en automático; en "Yo elijo" se marca como incumplimiento |
| Pernocta | ≥ 10 unidades de hospedaje si dura > 1 día | igual |
| Región beneficiada ≠ Angelópolis | obligatoria | se muestra como aviso, no bloquea |
| Estancias | 3 h ancla, 2 h emergente | igual |

- "Yo elijo": ordenar con `dos_opt` (inicio fijo) y llamar a `evaluar_ruta`; mostrar **todos** los
  incumplimientos.
- Sin ruta factible: devolver el motivo (`sin_candidatos_tema`, `tramo>75`, `total>240`, `pocos_emergentes`,
  `sin_pernocta`).
- `model/rutas.py` queda como: `ins = insumos.cargar(secreta=True)` → `optimizar_rutas(ins)` → escritura.
- **No regresión:** con los mismos datos, `optimizar_rutas` antes y después de la extracción devuelve las mismas
  rutas (comparar contra `data/derivados/rutas_propuestas.csv` generado justo antes del cambio, ya con A2–A5).

### 4.3 `model/reglas_circuitos.py` (sin acceso a la base)

Un circuito es un recorrido **dentro de un municipio** a partir de su cabecera.

**Parámetros** (un solo diccionario, guardado en `dim_version_calculo` como versión `circuitos_v1`):

| Parámetro | Valor |
|---|---|
| Estancia por categoría | museo y zona arqueológica 90 min · santuario y templo 45 · cascada, gruta, mirador y naturaleza 90 · experiencia (taller, productor) 60 · comida 60 · otro atractivo 45 |
| Velocidad | a pie 4.5 km/h · en auto 25 km/h (factor de rodeo 1.4 sobre la línea recta para elegir; OSRM para mostrar) |
| Tramo máximo | a pie 25 min · en auto 30 min |
| Duración | 4 h (medio día) u 8 h (un día), elegible de 3 a 10 h en el tablero |
| Mínimo | 3 paradas de tipo `atractivo` o `experiencia`, con al menos 1 `atractivo` |
| Comida | máximo 1 por cada 4 h, colocada entre las 13:00 y las 15:00 si el circuito pasa por ese horario |
| Diversidad (variado) | máximo 2 paradas de la misma actividad o categoría |
| Temático | todas las paradas de `atractivo`/`experiencia` con la actividad elegida, que debe ser principal del municipio |

**Prioridad de los puntos:** curado (con URL) > lugar OSM con actividad > negocio 712/713 > experiencia por SCIAN
> experiencia por nombre > lugar OSM sin actividad. Desempate: mayor `personal_est` (capacidad de recibir).

**Algoritmo:** vecino más cercano ponderado por prioridad desde la cabecera, respetando tramo máximo y duración,
más `dos_opt` con la cabecera fija. Es determinista (sin aleatoriedad).

**Aptitud del municipio** (`v_aptitud_circuito`): apto si tiene ≥ 3 puntos `atractivo` o `experiencia` y al menos
1 `atractivo`. Si no, `motivo_no_apto` ("sin lugares registrados" o "solo N lugares").

**Potencial de circuito** (para el ranking):
`0.5·pct(puntos atractivo + experiencia) + 0.3·pct(actividades distintas entre los puntos) + 0.2·índice vigente`.
Documentarlo en `Validations.md`.

---

## 5. Fase C · Capa de datos del tablero

### 5.1 `dashboard/supabase_cliente.py`
- Agregar a `leer()` un parámetro `filtro: str = ""` (p. ej. `"municipio_sk=eq.43"`) para no descargar tablas
  completas cuando no hace falta.

### 5.2 `dashboard/bd.py` (reemplaza a `datos.py`)
- `insumos()` → `model.insumos.cargar(secreta=False)`, con `st.cache_resource` (ttl 1 día). Es la **misma**
  estructura que usa el pipeline.
- `geo()` → GeoJSON de `data/geo/`.
- Lecturas para las páginas, con `st.cache_data(ttl=600)`: `ficha()` (`v_ficha_municipio`), `rutas()`
  (`v_ruta_parada`, incluye `propuesta_descartada`), `indice_municipio()`, `indice_detalle()` (componentes por
  eje), `banderas()`, `semaforos()`, `prediccion()`, `oferta()`, `concentracion()` (`v_concentracion_eje`),
  `exceso_oferta()`, `escenarios()` (`fact_escenario_concentracion`), `seguridad()`, `visibilidad()`,
  `aptitud_circuitos()`, `circuitos()` (`dim_circuito` + `fact_circuito_parada`) y `lugares(municipio_sk)`
  (`v_lugar_circuito` filtrado).
- Constantes que salen de la base: regiones, anclas, Pueblos Mágicos, actividades (icono, nombre), temas de ruta,
  pesos y umbrales.
- `ficha_bd.py` se integra en `bd.py` o se queda solo con las etiquetas de lectura de los semáforos (texto, no
  datos).

---

## 6. Fase D · Páginas

### 6.1 Barra lateral
- Quedan: actividades (14 de `dim_actividad`), región (de `dim_municipio`), enfoque del índice (§6.7), y para
  "Arma tu ruta": días y mínimo de emergentes.
- Se quitan: modo, escenarios de inversión y promoción, monto, destino, horizonte 1/3 (el horizonte es 5 años y
  se muestra como texto).
- Pie de la barra: "Fuente: Supabase · índice `<versión>` · modelo `<nombre>` · DENUE 05/2026", leído de la base.

### 6.2 🏠 Panorama
- KPI: municipios con bandera (por tipo), rutas propuestas y emergentes, top 5 y HHI de hoy, escenario con rutas,
  municipios aptos para circuito.
- La cifra del problema: `concentracion()`. Top 5 de población (37.5 %) contra hospedaje (63.1 %) y turismo y
  cultura (77.7 %).
- Mapa del índice vigente con anclas, emergentes y trazos de las rutas del modelo (coordenadas de cabecera).
- Top 10 emergentes (sin anclas), de `indice_municipio()`.
- Lorenz y Gini: hoy desde `oferta()`, tendencial y con rutas desde `escenarios()`. Supuesto visible.
- Treemap región × eje (tamaño = personal, color = índice medio).

### 6.3 🏘️ Ficha técnica (única ficha)
- Lo actual, más: cascada "¿Por qué este índice?" (`peso × score` del eje líder, pesos de la versión vigente);
  predicción por eje con intervalo, o `motivo_sin_prediccion`; seguridad separada (A6); visibilidad con el título de
  Wikipedia usado; exceso de oferta; aptitud de circuito y botón "Ver circuito"; rutas oficiales y propuestas que
  pasan por el municipio.
- Se borra `vistas/ficha.py`; los enlaces de otras páginas abren esta con `cve_geo` en `session_state`.

### 6.4 🗺️ Mapa de oportunidades
- Indicadores: índice vigente y cada componente, crecimiento predicho (en dominio), personal estimado, exceso de
  oferta, marginación, minutos al ancla, visibilidad, seguridad, número de banderas, CL de una actividad, aptitud de
  circuito.
- Resaltar cualquiera de las banderas de `dim_tipo_flag` con su descripción.
- Clic: índice y ranking, componentes, banderas con `motivo`, actividades principales y enlace a la ficha.
- Gráfica oferta contra visibilidad con el cuadrante de `OFERTA_INVISIBLE`, dibujado con los umbrales que usa la
  bandera (leerlos, no copiarlos).

### 6.5 🧭 Rutas
**Rutas del modelo:** agregar pernocta (🛏️ con unidades de hospedaje), días, región beneficiada, riesgo (A6),
paradas con infraestructura 🔴, tiempo de flujo libre y de planeación, y una sección "Rutas descartadas" con sus
incumplimientos en lenguaje legible. La agenda por días corta el día 1 en la parada `es_pernocta`.

**Arma tu ruta:** `reglas_rutas.construir_ruta(bd.insumos(), …)` en modo automático; `evaluar_ruta` en "Yo elijo".
Selector de tema con los temas del optimizador o "sin tema". Mostrar el cumplimiento de cada regla con ✅/⚠️ y, si
no hay ruta, el motivo y qué cambiar. El trazo y la agenda usan OSRM con las coordenadas de cabecera, y como
respaldo los tiempos de la base (no la línea recta inventada).

### 6.6 🔁 Circuitos
- Selector de municipio con la lista de `aptitud_circuitos()` ordenada por potencial; los no aptos aparecen
  deshabilitados con su motivo y un botón "Armar ruta desde aquí".
- Circuito estándar precalculado (`circuitos()`) y opción de personalizar (horas, a pie o en auto, variado o
  temático) con `reglas_circuitos` sobre `lugares(municipio_sk)`.
- Lugares curados con ✅ y su URL; categoría y estancia por parada; horario desde las 9:00.
- Trazo OSRM a pie o en auto; si el tiempo real supera la duración en más de 15 %, avisar (ya existe la lógica).

### 6.7 🔮 Escenarios y sensibilidad (antes Simulador)
- Escenarios de `escenarios()` con su supuesto visible.
- Sensibilidad: sliders de peso por componente sobre `indice_detalle()` de la versión vigente. Mostrar el top 20
  resultante y el porcentaje que conserva del top 20 oficial (V6 en vivo). Leyenda: "no cambia la base".
- Se quita todo lo de inversión y promoción.

### 6.8 🚩 Alertas
- Banderas activas de la versión vigente con municipio, eje, `motivo`, región e índice; filtros y CSV; conteo por
  tipo; mapa de calor región × bandera.

### 6.9 Navegación (`app.py`)
Inicio: Recorrido de presentación (§12.7). Explorar: Panorama · Ficha técnica · Mapa de oportunidades ·
Metodología y fuentes (§12.4). Proponer: Rutas · Circuitos · Escenarios y sensibilidad. Actuar: Alertas.
En el corte P0, solo las páginas listas con datos reales aparecen en la navegación (§0.1). Agregar la raíz del repo y `model/` a `sys.path` para importar las reglas.

---

## 7. Fase E · Borrar lo DEMO

- Borrar `dashboard/datos.py` y `dashboard/vistas/ficha.py`.
- En `dashboard/motor.py` quedan solo `hhi`, `lorenz` y `gini`; mejor moverlos a `model/geo_utils.py` o a un
  `model/metricas.py` y borrar `motor.py`.
- Quitar la clase CSS `mope-demo` y toda mención a "DEMO".
- `grep -rniE "demo|generar_demo|rng\.|random|SEMILLA|POBLACION_CONOCIDA|region_aprox" dashboard model` no debe
  devolver nada relacionado con datos simulados.

---

## 8. Fase F · Documentación
- `docs/Context.md`: §4.2 (ya no hay dos mundos), §10–§13 (páginas y capa de datos), §14 (`scripts/pipeline.py`).
- `docs/Validations.md`: reglas de circuitos, margen de planeación, pernocta, visibilidad corregida, resultados de
  §9.
- Marcar `docs/arquitectura_modelo_y_tablero.md` como diseño histórico.

---

## 9. Fase G · Pruebas (todas deben pasar)

### 9.1 Unitarias, sin base (`tests/test_reglas.py`)
Con un fixture pequeño **solo dentro del test**:
- `reglas_rutas`: respeta 75/240 de planeación, exige emergentes, exige pernocta ≥ 10 cuando dura más de un día,
  excluye infraestructura 🔴 en automático, `evaluar_ruta` reporta cada incumplimiento.
- `reglas_circuitos`: respeta duración y tramo máximo, máximo 2 por categoría en variado, comida en horario,
  ≥ 3 paradas con ≥ 1 atractivo, determinismo (dos corridas iguales).

### 9.2 No regresión del optimizador
`optimizar_rutas` reproduce `rutas_propuestas.csv` generado justo antes de la extracción (§4.2).

### 9.3 Cobertura total con la base (`tests/test_cobertura.py`)
- `construir_ruta` desde **cada uno de los 217 municipios** (sin tema y con cada tema que tenga candidatos):
  ninguna excepción; cada resultado es factible y cumple §4.2, o trae un motivo válido. Reportar cuántos municipios
  tienen ruta factible.
- Circuito para **cada municipio apto**: ninguna excepción y se cumplen las reglas de §4.3. Para los no aptos,
  `motivo_no_apto` no vacío.

### 9.4 Tablero (`tests/test_tablero.py`, reescrito)
- `AppTest` de las 7 páginas con la *publishable key*; si no hay `.env`, omitir con aviso.
- Ficha técnica con los mismos 6 municipios de prueba de hoy.
- "Arma tu ruta" desde un ancla, desde un municipio no ancla y en "Yo elijo" con una parada de infraestructura 🔴.
- Circuitos en un municipio apto y en uno no apto.
- Prueba "sin DEMO": falla si `dashboard/` importa `datos` o contiene generación aleatoria.

### 9.5 Congruencia front contra base (`tests/test_congruencia.py`)

| Se compara | Contra |
|---|---|
| Top 5 y HHI de Panorama | `v_concentracion_eje` (periodo vigente) |
| Índice y ranking de 10 municipios al azar en Mapa, Ficha y Rutas | `v_indice_municipio` |
| Banderas de esos municipios en Mapa, Ficha y Alertas | `fact_flag_oportunidad` vigente |
| Predicción | `fact_prediccion_crecimiento` del modelo vigente (vacía si `en_dominio = false`) |
| Tiempos de Arma tu ruta | `v_tiempo_municipios` |
| Rutas del modelo | `v_ruta_parada` (5 propuestas + descartadas) |
| Escenarios | `fact_escenario_concentracion` |
| Paradas de un circuito estándar | `fact_circuito_parada` |

### 9.6 Prueba manual final
`python iniciar.py`, recorrer las 7 páginas, armar una ruta desde Cuetzalan, otra desde un municipio de la Mixteca
y un circuito en Cuetzalan, y reportar capturas o la salida de las pruebas.

---

## 10. Orden de ejecución

**Primero el corte P0 de §0.1, completo, con commit y ensayo.** Después, P1 en este orden:

1. Rama y respaldo local (§1).
2. Fase A completa y `python scripts/pipeline.py` en verde.
3. Fase B (`insumos.py`, `reglas_rutas.py`, `reglas_circuitos.py`, `model/circuitos.py`) con §9.1 y §9.2.
4. Fase C (`bd.py`, filtro en `supabase_cliente`).
5. Fase D, página por página, en este orden: Rutas → Circuitos → Ficha técnica → Panorama → Mapa → Alertas →
   Escenarios.
6. Fase E (borrar DEMO).
7. §9.3 a §9.6.
8. Fase F (documentación).

En cada paso: reportar qué cambió y el resultado de las pruebas, y no seguir si algo falla.

---

## 11. Lo que no hay que hacer
- No conservar `datos.py` ni un modo DEMO oculto "por si acaso".
- No copiar fórmulas ni umbrales al front: importarlos o leerlos de la base.
- No usar la *secret key* en `dashboard/`.
- No inventar lugares, eventos, predicciones ni tiempos donde no hay datos.
- No presentar el escenario con rutas ni la sensibilidad como predicciones.
- No relajar las reglas de rutas o circuitos para que "salgan más": si no hay ruta o circuito, se explica por qué.

---

## 12. Lo que faltaba para la versión final

Las fases A a G dejan la plataforma correcta. Esta sección agrega lo necesario para que además sea **confiable en
la demo y útil para quien la va a usar**: la Secretaría de Turismo (planear, priorizar, rendir cuentas) y un
operador como Yankuilotl (vender y operar rutas).

### 12.1 Criterios que todavía permiten rutas mal armadas (P0)

Revisando `model/rutas.py` contra los datos aparecen dos huecos:

1. **"Emergente" incluye `BARRERA_ACCESO`.** Hoy cualquier bandera activa vuelve emergente a un municipio, pero
   `BARRERA_ACCESO` significa justamente "está lejos del ancla". Regla nueva: una parada cuenta como emergente si
   tiene alguna bandera **distinta de `BARRERA_ACCESO`** (o `BARRERA_ACCESO` **y** el tramo real que la conecta en
   la ruta es ≤ 75 min de planeación). Guardar la regla en `dim_version_calculo`.
2. **Paradas sin nada que visitar.** El tema cuenta como presente con `reconocida_sin_registro` (la Secretaría lo
   reconoce, pero no hay ningún negocio). Regla nueva: toda parada no ancla debe tener **al menos un punto
   visitable** en `v_lugar_circuito` (un lugar con nombre o un negocio de `atractivo`/`experiencia`). Si no lo
   tiene, la ruta incumple `parada_sin_punto_de_visita`. En la ficha de la ruta, cada parada lista sus puntos
   visitables (máximo 3, curados primero).

Volver a correr `model/rutas.py` después de estos cambios y de A2–A5, y anotar en `Validations.md` cómo cambiaron
las 5 rutas.

### 12.2 La demo no puede depender de internet en vivo (P0)

- **Trazos guardados:** agregar `geom_trazo` (GeoJSON `LineString`), `km_carretera` y `min_carretera` a
  `fact_ruta_evaluacion` y a `dim_circuito`, calculados por el pipeline con OSRM. El tablero dibuja ese trazo; solo
  llama a OSRM en vivo para "Arma tu ruta" y circuitos personalizados, con el respaldo ya existente.
- **Copia local de la base:** el pipeline exporta a `data/snapshot/` (parquet o CSV) cada vista y tabla que lee
  `bd.py`, con la fecha de corte en `data/snapshot/LEEME.txt`. Si Supabase no responde, `bd.py` usa esa copia y el
  tablero muestra "Copia de la base del <fecha>". **No es DEMO:** son los mismos datos reales.
- **Mapa HTML sin internet** (pendiente de `entregables.md` §8): exportar con Plotly/Folium el mapa del índice, las
  5 rutas y sus paradas a `docs/demo/mapa_mopedetu.html`, sin mosaicos externos (fondo de polígonos).
- **Video corto de respaldo** del recorrido de §12.7 (tarea del equipo, no de código).

### 12.3 Rendimiento (P1)

- Medir con `time` la primera carga y el cambio de página; meta de §0 (≤ 10 s y ≤ 2 s).
- `v_tiempo_municipios` (46,872 filas, ~47 peticiones): leerlo una vez con `st.cache_resource` o desde la copia de
  §12.2.
- No descargar `dim_establecimiento` completo: los lugares se piden por municipio (`filtro` de §5.1).
- `st.cache_data` en todas las lecturas; `ttl` largo para lo que solo cambia cuando corre el pipeline.

### 12.4 Página "Metodología y fuentes" (P0)

Nueva página en el grupo Explorar, **solo con datos de la base**:
- **Fuentes:** tabla de `dim_fuente` (institución, versión, fecha de descarga, licencia, cobertura, notas de
  calidad, uso en el modelo).
- **Modelos:** `dim_modelo` con métricas contra sus líneas base: crecimiento v2 (validación cruzada y temporal),
  rol B y enlaces. Mensaje claro: "le gana a las líneas base; sirve para priorizar, no para pronosticar cifras".
- **Validaciones:** crear `dw.fact_validacion (codigo, descripcion, criterio, resultado, estado, fecha)`, que el
  pipeline llena con V1–V9 y las pruebas de §9. La página la muestra con ✅/⏳/❌.
- **Limitaciones** (texto fijo, revisado por el equipo): mide oferta, no visitantes; tiempos de flujo libre con
  margen; DATATUR solo de la capital; RNT no disponible; seguridad = denuncias; rutas = hipótesis para validar con
  las comunidades.

Responde las preguntas probables del jurado y cubre los entregables 4, 9 y 11.

### 12.5 Semáforos que se leen igual en todas las dimensiones (P1)

Hoy 🔴 significa "no cargar más" en turismo actual, "barrera" en infraestructura y "prioridad" en necesidad social,
y todas las anclas salen en rojo. Cambiar en `scripts/calcular_ficha.py` y `ficha_bd.LECTURA`:
- **Turismo actual:** escala neutra (azul claro → azul cobalto) con la etiqueta "emisor" para las anclas, en vez
  de rojo.
- **Necesidad social:** "prioridad" en guinda con un ícono distinto (🎯), no el mismo rojo de "barrera".
- El rojo queda reservado a barreras y retrocesos.
- Siempre color + emoji + texto (accesible para daltonismo).

### 12.6 Lo que usarían la Secretaría y un operador (P1)

- **Itinerario descargable** de cada ruta y circuito: CSV y una versión imprimible (HTML o PDF) con día, hora,
  municipio, puntos visitables, pernocta, tiempos y enlace a Google Maps.
- **Proveedores por parada** (para operadores): hospedaje, alimentos y experiencias del DENUE en cada municipio de
  la ruta, con nombre y estrato. El DENUE público también trae teléfono, correo y sitio web: agregarlos a
  `stg.denue` y `dim_establecimiento` (`telefono`, `correo`, `sitio_web`) desde el mismo CSV de INEGI y registrarlo
  en `dim_fuente`. Es información pública de negocios, no de personas.
- **Enlace para compartir:** `st.query_params` con municipio, ruta o circuito seleccionados.
- **Línea base para medir el impacto** de cada ruta propuesta: crear
  `dw.fact_linea_base_ruta (ruta_sk, municipio_sk, indicador, valor, fecha_corte)` con unidades DENUE por eje,
  hospedaje, visibilidad y seguridad de cada parada al día de hoy. En la página de Rutas, sección "Cómo mediremos
  el impacto": indicadores, línea base y fuente (nuevo corte del DENUE cada semestre, RNT, ocupación cuando haya
  datos). Responde "¿cómo medirían la derrama?".
- **Lista de formalización:** desde `OFERTA_SIN_REGISTRO`, municipios y actividades reconocidas por la Secretaría
  sin ningún negocio en el DENUE, descargable. Es una acción concreta para la Secretaría.

### 12.7 Recorrido de presentación (P0)

Una página de inicio (o un modo "Presentación" en la barra lateral) con 5 pasos, cada uno con datos reales:
1. **El problema:** el top 5 tiene el 37.5 % de la población, pero el 63.1 % del hospedaje y el 77.7 % de la oferta
   cultural (`v_concentracion_eje`).
2. **Dónde está la oportunidad:** mapa del índice y top 10 emergentes.
3. **Una ruta nueva y por qué:** la mejor ruta del modelo con sus banderas, tiempos reales, pernocta y novedad.
4. **Un municipio a fondo:** ficha de Jonotla (El Peñón, semáforos, predicción, lugares).
5. **Cómo sabemos que funciona y qué sigue:** métricas contra líneas base, validaciones y línea base de impacto.

### 12.8 Calidad de la experiencia (P1)

- Textos en español claro para funcionarios: tooltips con un glosario (CL, HHI, bandera, emergente, ancla,
  intervalo).
- Estados de carga y de error en cada página; nunca un *traceback* en pantalla.
- Que se vea bien a 1280 px y en una tableta (columnas que se apilan).
- Fecha de corte de los datos visible en el pie de cada página.

### 12.9 Entregables de la convocatoria (P0)

`docs/entregables.md` tiene casi todo en ⬜. Completarlo con cifras **leídas de la base** (no de memoria): problema
(§12.7 paso 1), fuentes (`dim_fuente`), procesos (Fase A y `scripts/pipeline.py`), arquitectura (pipeline → base →
tablero, con el diagrama actualizado), resultados (rutas, banderas, validaciones), modelo de IA (`dim_modelo`) y
prototipo (estado real del tablero). Marcar cada fila ✅ solo cuando esté escrita.

### 12.10 Pruebas adicionales

- §12.1: ninguna ruta publicada tiene una parada sin punto visitable ni un emergente que solo tenga
  `BARRERA_ACCESO`.
- §12.2: con la red desconectada (variables de Supabase vacías), el tablero abre desde `data/snapshot/` y las
  rutas del modelo se dibujan con su trazo guardado.
- §12.3: medición de tiempos registrada en `Validations.md`.
