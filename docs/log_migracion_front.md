# MOPEDETU · Log de ejecución de `plan_migracion_front.md`

Registro paso a paso de lo que se hizo al ejecutar `docs/plan_migracion_front.md`: qué cambió, cómo se probó, qué
falló y cómo se resolvió. Rama: `feat/plataforma-datos-reales` (desde `main` en `358f085`).
Fecha: 15-oct-2026.

Leyenda: ✅ hecho y probado · ⚠️ hecho con salvedad · ❌ falló / no se pudo · ⏭️ pospuesto.

---

## Paso 0 · Rama y respaldo local (§1)

- ✅ Rama `feat/plataforma-datos-reales`.
- ✅ Respaldo local: no hay `pg_dump` ni `DATABASE_URL` en la máquina, así que se escribió
  `scripts/respaldo_local.py`, que exporta con la *secret key* cada tabla de `dw` y `stg` a
  `data/respaldo/2026-10-15/` (42 objetos, 56 MB, con `LEEME.txt` de conteos). `data/respaldo/` se agregó a
  `.gitignore`. Incluye también `v_tiempo_municipios` (vista simple, la API la expone como actualizable).

## Corte P0 · Fase A (datos y criterios)

### A1 · Visibilidad ✅
- **Causa encontrada:** se contaba solo el artículo "Municipio de X"; los lectores van al de la ciudad cabecera
  ("Puebla de Zaragoza", "Cholula de Rivadavia", "Atlixco"). Por eso Puebla salía #5 con 7,524 vistas.
- **Cambio:** `scripts/cargar_visibilidad_wikipedia.py` suma el artículo del municipio (Wikidata P3801) y el de su
  localidad cabecera (P1976, clave terminada en 0001), cada uno resuelto a su título canónico (redirecciones de la
  API de MediaWiki). Nueva columna `fact_visibilidad.titulo_wikipedia` (`sql/16_visibilidad_titulo.sql`).
- **Validación:** 217/217 municipios con los dos títulos. Top: Puebla #1 (82,283), San Pedro Cholula #2 (35,350),
  Tehuacán #3, Cuetzalan #7, Atlixco #12. ✅ Los cuatro del criterio en el top 15. Total 941,881 vistas
  (antes 440,648).
- Nota: el plan pedía la siguiente migración como `15_…`; `15` ya estaba ocupado (`15_cobertura_catalogos.sql`), así
  que la numeración sigue desde `16`.

### A4 · Pares con *snapping* "erróneo" ✅ (no eran errores)
- Los 42 pares por debajo de la recta a 90 km/h salen solo al comparar el tiempo **entre cabeceras** con la recta
  **entre centroides** (`distancia_km_recta`). Entre cabeceras: **0 pares** (tampoco a 110 km/h). No hubo que
  recalcular nada: la causa es la incongruencia de coordenadas (P5), que se corrige en A5.

### A6 · Seguridad ✅
- `fact_seguridad` separa `robo_transeunte` (calle y transporte) de `robo_carretera` (transportista)
  (`sql/17_seguridad_grupos.sql`, `scripts/cargar_seguridad.py`). 11,935 filas (217 × 11 años × 5 grupos).
- `riesgo_seguridad` de cada ruta ahora da dos lecturas: **delitos en el municipio** (homicidio + secuestro/
  extorsión + robo a transeúnte) y **robo en carretera**.
- ⚠️ Ajuste no previsto en el plan: con "la parada más alta" como nivel, las 6 rutas salían "alto" (con 6 paradas
  casi siempre una cae en ≥ P80 y en municipios chicos 1-2 denuncias disparan la tasa). El nivel ahora sale del
  **percentil medio de las paradas** y la parada más alta se informa aparte. Resultado: talavera bajo/bajo,
  volcanes medio/bajo, café bajo/bajo, religioso medio/medio, gastronomía medio/medio (Esperanza sigue siendo P100
  en robo en carretera, pero ya no define sola la etiqueta).

### A3 + A5 · Configuración vigente, tiempo de planeación y cabeceras ✅ (`sql/18_plataforma_vigente.sql`, `sql/19_ficha_municipio.sql`)
- **Una sola fuente de verdad** para versiones y parámetros: filas `plataforma_vigente` (índice `v3_dominio_osrm`,
  modelo `crecimiento_ue_eje_lgbm_v2`, optimizador, semáforos, periodo) y `optimizador_rutas_v2` (75/240 min,
  3-6 paradas, pernocta ≥ 10, bonos, `banderas_no_emergente`, `factor_planeacion` por región) en
  `dim_version_calculo`, expuestas en la vista `dw.v_vigente`.
- `v_tiempo_municipios` + `factor_planeacion` (el de la región más lenta entre origen y destino: 1.25 en Sierra
  Norte, Sierra Nororiental y Tehuacán y Sierra Negra; 1.10 en el resto) y `tiempo_min_planeacion`.
  29,316 pares con 1.25 y 17,556 con 1.10.
- `v_ruta_parada`, `v_ficha_municipio`: `lat/lon` = cabecera; centroide en `lat_centroide/lon_centroide`.
  `v_indice_municipio` y las banderas/semáforos de la ficha leen la versión **vigente** (antes: el `version_sk` más
  alto).
- `model/base.py`: `mun.lat/lon` desde `dim_municipio.cabecera_lat/lon` (ya no del GeoJSON).
- **Bug corregido** en `v_ficha_municipio`: `rutas_propuestas` usaba `origen <> 'existente'` y contaba la ruta
  descartada; ahora `= 'propuesta_modelo'`.
- Ficha con columnas nuevas (§6.3): `prediccion` (por eje, con `en_dominio` y motivo), `seguridad` (municipio y
  carretera con percentil), `visibilidad` (vistas, percentil, títulos), `exceso_oferta`, `cabecera_nombre`,
  `anio_pueblo_magico`.

### A9 · Puntos visitables ✅ con salvedad (`sql/20_…`, `sql/21_lugar_circuito.sql`)
- `fact_establecimiento_actividad`: 13,107 asignaciones con la misma `detectar()` de `calcular_actividades.py`
  (nuevo `cargar_establecimientos()`, opción `--solo-establecimientos`).
- ⚠️ Hallazgo: `dim_establecimiento` solo tenía los SCIAN de los ejes turísticos; los productores de café, mezcal,
  bebidas y viveros (las "experiencias" del plan) no estaban. Se agregaron **1,596** negocios detectados por
  actividad, con su clave DENUE, estrato y punto.
- `v_lugar_circuito`: 12,003 puntos (572 OSM, 337 negocios 712/713, 4,340 experiencias, 6,746 comidas
  tradicionales, 8 curados), con prioridad §4.3 y sin duplicados (~50 m). **105 municipios aptos** para circuito
  (≥ 3 atractivo/experiencia con ≥ 1 atractivo); 40 municipios sin ningún punto.
- ⚠️ Los **8 lugares curados no tienen coordenadas** en `fact_atractivo_lugar` (Jonotla y Zoquiapan). Entran a la
  vista con `lat/lon` nulos: cuentan como punto visitable, pero un circuito no puede ubicarlos. No se inventaron
  coordenadas; queda pendiente georreferenciarlos con fuente.

### A2, A3, A11, §12.1 · Optimizador de rutas con reglas de operación ✅ (`model/rutas.py`)
- Parámetros leídos de `v_vigente.parametros_rutas` (ya no constantes en el código).
- **A2:** pernocta en parada con ≥ 10 unidades de hospedaje (antes P50 = 2); si ninguna emergente cumple, el ancla.
- **A3:** todas las decisiones y restricciones (75/240 min) con `tiempo_min_planeacion`; se guardan los dos
  tiempos (`*_real` = flujo libre, `*_planeacion`).
- **§12.1 (1):** emergente = bandera activa **distinta de `BARRERA_ACCESO`**. Decisión: el plan da dos variantes
  ("o BARRERA_ACCESO con tramo ≤ 75 min"); en una ruta factible todo tramo es ≤ 75, así que esa variante no
  cambiaría nada, y la prueba §12.10 exige que ningún emergente tenga solo `BARRERA_ACCESO`. Se aplicó la estricta.
- **§12.1 (2):** toda parada no ancla debe tener ≥ 1 punto `atractivo`/`experiencia` en `v_lugar_circuito`;
  se filtra en la construcción y, si falla, la ruta incumple `parada_sin_punto_de_visita`.
- **A11:** docstring reescrito (bono social 0.40, pernocta ≥ 10, tiempos de planeación, nuevas reglas) y borrados
  los comentarios duplicados de la "selección voraz".
- **Antes de correr:** se volvieron a calcular las banderas v3 con la visibilidad corregida (`crecimiento.py`):
  `OFERTA_INVISIBLE` pasó de 92 a 77 celdas.

**Cómo cambiaron las 5 rutas** (56 candidatas factibles, 35 operables):

| # | Ruta | Min. libre | Pernocta | Región | Antes |
|---|---|---|---|---|---|
| 1 | Talavera · Tlatlauquitepec → Tenampulco | 173 | Zacapoaxtla | Sierra Nororiental | salía de Chignahuapan |
| 2 | Volcanes · San Pedro Cholula → Atzitzihuacán | 107 | San Pedro Cholula (ancla) | Valle de Atlixco y Matamoros | pernocta en Calpan (3 hospedajes) |
| 3 | Flores y viveros · Tlatlauquitepec → Chapulco | 193 | Tlatlauquitepec (ancla) | Valle de Serdán | **nueva** (reemplaza a religioso) |
| 4 | Gastronomía · Tehuacán → Nicolás Bravo | 174 | Tehuacán (ancla) | Tehuacán y Sierra Negra | pernocta en Esperanza (2) |
| 5 | Mezcal · Tehuacán → Huehuetlán el Grande | 171 | Tehuacán (ancla) | Mixteca | **nueva** (reemplaza a café) |

- La ruta de **café** (Xicotepec, 236 min libres) ya no cabe con el margen de 1.25 de la Sierra Norte (295 min de
  planeación > 240). Descartada registrada: Ecoturismo · San Andrés Cholula (región Angelópolis).
- ⚠️ Con el umbral de 10 hospedajes, 4 de 5 rutas pernoctan en el **ancla**: en la mayoría de los municipios
  emergentes no hay hospedaje suficiente. Es una limitación real de la oferta, no del modelo.
- Riesgo (A6) y escenario (A8) recalculados después. Línea base para la no regresión guardada en
  `tests/fixtures/rutas_propuestas_antes_extraccion.csv` y `…candidatas…`.

### A7 · Rol B sin depender del tablero ✅
- Nuevo `model/geo_utils.py` (`haversine_km`). `model/prediccion_crecimiento.py` ya no importa `dashboard/datos`:
  anclas y regiones salen de `dim_municipio` en los dos modos. Reentrenado: mismos resultados (205 predicciones,
  mismas importancias).

### A8 · Escenarios en la base ✅ (`sql/22_escenarios.sql`)
- `fact_escenario_concentracion` con HHI, top 5 y **Gini**; `model/escenario_hhi.py` escribe ahí (y el JSON) con
  `model/metricas.py` (`hhi`, `pct_top`, `lorenz`, `gini`, movidos de `dashboard/motor.py`).
- Hoy 1,306 / 51.9 % / 0.817 → tendencial 1,141 / 49.2 % / 0.804 → con rutas (hipotético) 1,098 / 48.2 % / 0.800.
- Nota: la migración del plan se llamaba `15_escenarios.sql`; quedó como `22_escenarios.sql` por la numeración.

### §12.2 · Trazos guardados y copia local ✅
- `sql/23_trazos.sql` + `scripts/trazar_rutas.py`: `geom_trazo` (GeoJSON), `km_carretera`, `min_carretera` en
  `fact_ruta_evaluacion` para las 6 rutas (5 propuestas + 1 descartada), con OSRM de FOSSGIS. Coinciden con la base
  (talavera 173 min vs 172.9 guardado).
- ⚠️ Una primera ejecución de dos llamadas en paralelo fue rechazada en la sesión; se repitió una a la vez sin
  problema.
- `scripts/exportar_snapshot.py`: copia local de los 19 objetos que lee el tablero en `data/snapshot/*.jsonl`
  (6.5 MB, leída con la *publishable key*, con `LEEME.txt` y fecha de corte).

### §12.4 · Validaciones en la base ✅ (`sql/24_validaciones.sql`, `scripts/validaciones.py`)
- `fact_validacion` calculada desde la base (no copiada): V1 ✅ 217/217 · V2 ✅ 12/12 · V3 ✅ café 19/29, mezcal 6/12
  · V4 ✅ (CV y temporal) · V5 ✅ AUC 0.881 · V6 ✅ 95-100 % · V7 ✅ 3 nuevas, 2 parciales · V8 ✅ 1,306 → 1,098 ·
  V9 ⏳ (DATATUR trae 1 destino) · R1 ✅ 5/5 rutas operables, tramo máx. 68 min · R2 ✅ 0 paradas sin punto
  visitable, 0 emergentes solo con barrera · D1 ✅ 0 predicciones fuera de dominio.

## Corte P0 · Tablero

### Capa de datos ✅
- `supabase_cliente.leer(..., filtro=)` (§5.1).
- Nuevo `dashboard/bd.py`: todas las lecturas del tablero desde `dw` con la *publishable key* y caché; si Supabase
  no responde, usa `data/snapshot/` y lo avisa ("Copia local de la base (fecha)"). Sin respaldo DEMO.
- Prueba: los 19 objetos se leen con la *publishable key* (ninguno requirió política nueva).

### A10 (parte) · Aptitud para circuito ✅ (`sql/25_aptitud_circuito.sql`)
- `v_aptitud_circuito`: apto si tiene ≥ 3 puntos atractivo/experiencia **ubicados** y ≥ 1 atractivo ubicado;
  `motivo_no_apto` y `potencial_circuito` (0.5·pct puntos + 0.3·pct actividades + 0.2·índice). **105 aptos**, 112 no
  aptos con motivo. (Se creó en P0 porque el Panorama muestra el conteo.)

### Páginas P0 ✅
- **Navegación** (`app.py`): Inicio → Recorrido de presentación · Explorar → Panorama, Ficha técnica, Metodología y
  fuentes · Proponer → Rutas. Las páginas DEMO (Mapa, Circuitos, Simulador, Ficha municipal, Alertas y "Arma tu
  ruta") **ya no se cargan** en el corte P0. `app.py` agrega `model/` y la raíz a `sys.path`.
- **Barra lateral** (`estado.py`): sin modo, escenarios, monto ni horizonte inventados; muestra versión del índice,
  modelo, corte de datos, reglas de rutas y la fuente (Supabase o copia local).
- **Rutas del modelo** (`vistas/rutas.py`, reescrita): pernocta 🛏️ con hospedajes, días, región beneficiada,
  riesgo (municipio y carretera), tiempo libre y de planeación, 3 puntos visitables por parada, trazo guardado (sin
  OSRM en vivo), agenda que corta el día en la pernocta, itinerario CSV y sección "Rutas descartadas" con motivos
  legibles. "Arma tu ruta" queda para P1 (necesita `reglas_rutas`).
- **Panorama** (`vistas/panorama.py`, reescrita): KPI reales, la cifra del problema (`v_concentracion_eje`), mapa
  del índice con trazos y anclas en la cabecera, top 10 emergentes, Lorenz y Gini (`model/metricas.py` +
  `fact_escenario_concentracion`), treemap región × eje.
- **Ficha técnica**: lee `bd`; pestañas nuevas "Índice y predicción" (cascada peso × componente con los pesos
  vigentes, predicción por eje con intervalo o motivo, exceso de oferta), "Qué visitar" (`v_lugar_circuito`),
  "Seguridad y visibilidad" (municipio y carretera por separado; títulos de Wikipedia). Banderas con nombre legible.
  `ficha_bd.py` quedó solo con etiquetas de lectura.
- **Metodología y fuentes** (nueva): validaciones de `fact_validacion`, modelos contra líneas base (CV y temporal;
  enlaces; rol B), `dim_fuente` y limitaciones.
- **Recorrido de presentación** (nueva): los 5 pasos de §12.7 con datos de la base y botones a Rutas, Ficha de
  Jonotla y Metodología.
- **Mapa HTML sin internet**: `scripts/exportar_mapa_html.py` → `docs/demo/mapa_mopedetu.html` (5.1 MB, plotly.js
  embebido, sin `<script src>` externo, sin mosaicos).
  ⚠️ No se pudo abrir en un navegador sin red dentro de esta sesión; conviene probarlo a mano antes de la demo.

### Pruebas P0 ✅ (`tests/test_tablero.py`, reescrito)
- Sin DEMO: ninguno de los 13 archivos que carga `app.py` importa `datos`/`motor` ni genera aleatorios. ✅
- Páginas: Recorrido (5 pasos), Panorama, Metodología, Rutas (recorrer cada una de las 5) y Ficha técnica (los
  mismos 6 municipios de prueba, incluido uno sin oferta). ✅
- **Falló y se corrigió:** la ficha de un municipio sin ningún lugar rompía (`KeyError: 'prioridad'`, la API
  devuelve 0 columnas); `bd.lugares()` ahora devuelve las columnas vacías.
- **Sin red** (§12.10): con `SUPABASE_URL` vacío las páginas abren desde `data/snapshot/` y la barra avisa "Copia
  local de la base". ✅ **Falló y se corrigió:** el aviso dependía de la sesión y se perdía cuando la lectura venía de
  la caché; ahora la marca es del proceso.

### §12.9 · Entregables ✅
- `docs/entregables.md` ahora lo genera `scripts/generar_entregables.py` con consultas a la base (o a la copia local):
  problema, fuentes, rutas, top 10, escenarios, validaciones y modelos. Las 11 filas en ✅ salvo la 10 (🟨: ensayo y
  video son tareas del equipo).
- El generador detectó 3 fuentes con ficha incompleta (DENUE, Marco Geoestadístico, OpenStreetMap: filas del ETL
  original sin versión ni licencia). Completadas con lo que usan los scripts de carga (`sql/26_fuentes_completas.sql`).

### Cierre del corte P0
- Pendiente del equipo (no es código): ensayar la demo con el recorrido de §12.7 y grabar el video de respaldo;
  abrir `docs/demo/mapa_mopedetu.html` en un navegador sin red para confirmarlo.

## Corte P1 · Fase B (reglas compartidas)

### §4.1 `model/insumos.py` ✅
- `cargar(secreta: bool)`: índice, banderas, temas presentes, predicción en dominio, enlaces en percentil, tiempos
  (libre y planeación), hospedaje, infraestructura roja, municipios con punto visitable, necesidad social, meses
  fuertes, tramos oficiales y parámetros del optimizador, todo desde `dw` y `v_vigente`. Misma estructura para el
  pipeline (secret key) y el tablero (publishable key).
- ⚠️ Carga en 47 s (sobre todo los 46,872 pares de `v_tiempo_municipios` en páginas de 1,000). Se atiende en §12.3.

### §4.2 `model/reglas_rutas.py` ✅ y no regresión §9.2 ✅
- Extraídas sin cambiar la lógica: `valor`, `recorrido`, `dos_opt`, `candidatos`, `evaluar_ruta` (ya no devuelve
  `None`: siempre trae `incumplimientos`), `seleccionar`; API pública `construir_ruta(ins, inicio, tema, destinos,
  max_paradas, exigir_ancla)` y `optimizar_rutas(ins)`. "Sin tema" = cualquier tema presente.
- `model/rutas.py` quedó en: `insumos.cargar(secreta=True)` → `optimizar_rutas` → escritura.
- **No regresión:** contra `tests/fixtures/rutas_propuestas_antes_extraccion.csv` (generado justo antes, ya con
  A2-A5): las 5 rutas y sus puntajes idénticos (diferencia < 1e-9), la misma descartada y las 144 combinaciones
  ancla × tema con el mismo recorrido y puntaje.

### §4.3 `model/reglas_circuitos.py` + A10 `model/circuitos.py` ✅ (`sql/27_circuitos.sql`)
- Parámetros de §4.3 en `PARAMETROS` y en `dim_version_calculo` `circuitos_v1`. Determinista (empates por personal y
  `lugar_id`).
- **Ajustes encontrados al probar con datos reales:**
  1. La prioridad multiplicativa (×1.25 por nivel) casi no pesaba frente a la distancia: elegía negocios contiguos del
     centro en vez del museo o el santuario. Ahora es **aditiva** (+10 min por nivel de prioridad).
  2. En 8 h no cabía la comida porque las visitas llenaban el tiempo: ahora se **reserva** el tiempo de comida si el
     circuito cruza el mediodía.
  3. El regreso a la cabecera no se limitaba al tramo máximo y el voraz podía no elegir ningún atractivo: ahora la
     primera parada es un atractivo y toda parada queda a ≤ tramo máximo de la cabecera.
  4. Aparecían negocios del DENUE registrados como "SIN NOMBRE": se excluyen en `v_lugar_circuito` (8,681 puntos;
     antes 12,003).
- `model/circuitos.py`: 398 circuitos (variados 4/8 h a pie y en auto + temáticos de 4 h en auto cuando hay ≥ 3 puntos
  de la actividad y al menos un atractivo). Estándar = primer variado que cumple en el orden 4 h a pie → 4 h auto →
  8 h a pie → 8 h auto; trazo OSRM (a pie o auto) guardado para los 96 estándar.
- `v_aptitud_circuito` ahora distingue `apto_por_lugares` (conteo) de `apto` (hay estándar que cumple): **86 aptos**,
  10 con lugares pero sin circuito que cumpla (motivo: pocas paradas dentro del radio o de categorías distintas), 121
  sin lugares suficientes.
- ⚠️ Los temáticos que no cumplen (9) quedan guardados con `cumple = false`; el tablero solo ofrece los que cumplen.
- ⚠️ Con la exclusión de "SIN NOMBRE", una parada de las rutas publicadas se quedó sin punto visitable: se corrige al
  volver a correr el pipeline (rutas).

### A12 · `scripts/pipeline.py` ✅ (con dos fallas resueltas)
- Orquestador con 15 pasos, `--desde` y `--solo`; se detiene ante el primer error.
- ❌→✅ **Primera corrida falló en `rutas`**: `v_aptitud_circuito` (vistas encadenadas con subconsulta correlacionada)
  excedía el `statement timeout` incluso con la secret key; tampoco se pudo crear como vista materializada dentro del
  tiempo del conector (la base, en capa gratuita, quedó lenta tras el pipeline). Solución (`sql/28_lugares_aptitud_tablas.sql`):
  lugares y aptitud se calculan en Python dentro del pipeline (`calcular_actividades.py::calcular_lugares`,
  `circuitos.py::escribir_aptitud`) con la misma lógica de `sql/21` y `sql/25`, se guardan en
  `fact_lugar_circuito` / `fact_aptitud_circuito` y las vistas solo los leen. Verificado: 8,681 lugares, igual que la vista.
- ❌→✅ Lectura de `v_tiempo_municipios` por offsets en paralelo daba timeout: ahora `supabase_cliente.leer_por_bloques`
  (por municipio de origen, sin offsets).
- **Segunda corrida (`--desde rutas`) en verde, 7.4 min:** 5 rutas operables (talavera, volcanes, religioso, mezcal y
  gastronomía Pahuatlán → Tlaxco; la descartada sigue siendo ecoturismo/Angelópolis), 398 circuitos, 86 municipios
  aptos, 11 de 12 validaciones ✅ y V9 ⏳ (sin datos de DATATUR por destino).

### Páginas P1 escritas (pendiente correr sus pruebas)
- Rutas: modo **Arma tu ruta** con `reglas_rutas` (mismas reglas, checklist ✅/⚠️, motivo y qué cambiar).
- **Circuitos** (estándar con trazo guardado, personalizar, no aptos con motivo y "Armar ruta desde aquí").
- **Mapa de oportunidades**, **Alertas** (con lista de formalización), **Escenarios y sensibilidad** (usa
  `model/indice.py::indice`, no copia la fórmula). Ficha técnica con aptitud y botón "Ver circuito". Navegación completa.

## Pendiente
- Correr `tests/test_tablero.py` sobre las páginas nuevas (y agregarles casos: Arma tu ruta, Circuitos apto/no apto).
- Fase E: borrar `dashboard/datos.py`, `motor.py`, `vistas/ficha.py`, `vistas/simulador.py`, clase `mope-demo`.
- §9.3 `tests/test_cobertura.py` (217 municipios), §9.5 `tests/test_congruencia.py`, §9.6 prueba manual.
- §12.3 medir tiempos de carga, §12.5 semáforos, §12.6 resto (proveedores, línea base de impacto, query params), §12.8.
- Fase F: actualizar `Context.md` y `Validations.md`; marcar `arquitectura_modelo_y_tablero.md` como histórico.
