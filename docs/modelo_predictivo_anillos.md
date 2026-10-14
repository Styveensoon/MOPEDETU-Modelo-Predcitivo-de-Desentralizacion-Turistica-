# MOPEDETU · Modelo predictivo por anillos y ficha técnica municipal

> Objetivo: **proponer rutas turísticas nuevas que descentralicen el turismo de Puebla**, a partir de lo que cada municipio *tiene* (actividades, infraestructura, temporadas, nivel turístico actual y contexto social) y de lo que el modelo *predice* que puede crecer.
>
> Este documento une el modelo dimensional de Supabase (`dw`), el reparto de roles (Galo A, Raúl B, Styveen C) y la ficha técnica que verá el usuario en el mapa.

---

## 1. La idea en una imagen

Cada municipio es un **centro con anillos**. Los anillos interiores describen *qué hay hoy*. Los exteriores *predicen y deciden*. Un anillo solo consume a los que están dentro de él.

```
                       ┌───────────────────────────────────────────┐
                       │  A6 · DECISIÓN: rutas nuevas + novedad    │
                       │  ┌─────────────────────────────────────┐  │
                       │  │ A5 · PREDICCIÓN: crecimiento, enlace│  │
                       │  │  ┌───────────────────────────────┐  │  │
                       │  │  │ A4 · CONTEXTO SOCIAL          │  │  │
                       │  │  │  ┌─────────────────────────┐  │  │  │
                       │  │  │  │ A3 · DEMANDA Y TEMPORADA│  │  │  │
                       │  │  │  │  ┌───────────────────┐  │  │  │  │
                       │  │  │  │  │ A2 · INFRAESTRUC. │  │  │  │  │
                       │  │  │  │  │  ┌─────────────┐  │  │  │  │  │
                       │  │  │  │  │  │A1 · OFERTA Y│  │  │  │  │  │
                       │  │  │  │  │  │ ACTIVIDADES │  │  │  │  │  │
                       │  │  │  │  │  │ ┌─────────┐ │  │  │  │  │  │
                       │  │  │  │  │  │ │A0 · ID  │ │  │  │  │  │  │
                       │  │  │  │  │  │ └─────────┘ │  │  │  │  │  │
                       └──┴──┴──┴──┴──┴─────────────┴──┴──┴──┴──┴──┘
   Ficha técnica (lo que se ve al hacer clic) = A0 + A1 + A2 + A3 + A4, resumidos en semáforos
   Modelo (lo que se calcula)                 = A5 + A6, alimentados por todos los anteriores
```

Cada anillo tiene **dueño, tablas, fuente, frecuencia de actualización y validación**. Si un anillo exterior cambia (por ejemplo, los pesos del índice), no se recalculan los interiores. Si cambia uno interior (por ejemplo, un nuevo corte del DENUE), se recalcula todo lo que está fuera de él. Es el mismo principio de "hash por anillo" de `arquitectura_modelo_y_tablero.md`.

---

## 2. Los anillos

### A0 · Identidad del municipio ✅ (cargado)
| Qué | Tabla | Fuente |
|---|---|---|
| Clave, nombre, polígono, centroide, superficie | `dw.dim_municipio` | INEGI, Marco Geoestadístico 2023 |
| Región (7 regiones 2015) | `dim_municipio.region` | Congreso del Estado |
| Pueblo Mágico, ancla | `dim_municipio.es_pueblo_magico`, `.es_ancla` | SECTUR + criterio documentado |
| Rutas oficiales en las que aparece | `dw.fact_ruta_parada` (origen existente) | Sectur Puebla |

### A1 · Oferta y actividades turísticas (qué se puede hacer)
Dos niveles complementarios:

1. **Ejes económicos (ya diseñado por Galo).** Hospedaje, alimentos, turismo y cultura, y comercio turístico. Se calculan con DENUE + SCIAN → `fact_oferta_municipio_eje` (unidades, personal estimado, cociente de localización y predominancia).
2. **Actividades temáticas (nuevo).** Es lo que el visitante entiende: café, mezcal, arqueología y otras. Se asignan con tres señales, y cada actividad puede usar una o varias:
   - **SCIAN específico:** por ejemplo, 312142 *bebidas destiladas de agave* → mezcal; 311920 *beneficio y tostado de café* → café.
   - **Palabras clave en el nombre del establecimiento DENUE:** "mezcal", "café", "talavera", "temazcal", "cabañas", "ecoturismo", "balneario".
   - **Atractivos y catálogos:** OSM (`tourism=*`, `historic=*`, `natural=*`), zonas arqueológicas del INAH, paradas de las rutas oficiales y Pueblos Mágicos.

Códigos verificados contra el **DENUE 05/2026 de Puebla** (410,693 establecimientos). Las reglas están en `model/actividades.py` y el cálculo en `scripts/calcular_actividades.py`.

| Actividad | SCIAN | Palabras clave (solo dentro de los SCIAN indicados) | Catálogo |
|---|---|---|---|
| ☕ Café | 311921, 311922 | finca, cafetal, beneficio de café, tostador | Bioruta del Café |
| 🥃 Mezcal y destilados | 312145, 312149 | mezcal, palenque (en 3121, 4612, 7224, 7225) | Ruta del Mezcal |
| 🍎 Pulque y sidra | 312132, 312139 | pulque, sidra, tlachiquero | — |
| 🏺 Talavera y artesanías | 327111, 465915 | talavera, artesanía, alfarería, ónix | — |
| 🍲 Gastronomía tradicional | — | mole, antojitos, barbacoa, mixiote, cemita (en 7225, 3114) | Rutas gastronómicas |
| 🏛️ Museos | 712111, 712112 | — | — |
| 🗿 Arqueología | — | — | INAH: Cholula, Cantona, Yohualichan, Tepexi el Viejo |
| ⛪ Religioso y conventos | — | — | Rutas religiosas y Ex Conventos |
| 🌲 Ecoturismo y aventura | 721190, 721210, 712190, 713998 | ecoturismo, cabañas, campamento, tirolesa, rappel (solo hospedaje y recreación) | Rutas de senderismo, naturaleza y ciclismo |
| 🌋 Volcanes y alta montaña | — | volcán, Citlaltépetl, Izta-Popo (solo hospedaje y recreación) | Ruta de los Volcanes |
| ♨️ Balnearios y termales | 713113, 713114 | balneario, aguas termales | — |
| 🌸 Flores y viveros | — | vivero, floricultura, invernadero (en 4663) | — |
| 🤝 Turismo comunitario | — | cooperativa (no escolar), S.P.R., ejido, comunitario | — |
| 🧭 Agencias y operadores | 561510, 561520, 487110, 487210, 487990 | — | — |

**Resultado de la primera corrida:** 188 de 217 municipios tienen al menos una actividad principal.

**Validación V3:**
- **Café:** el DENUE detecta la actividad en 19 de los 29 municipios de la Bioruta (66 %).
- **Mezcal:** la detecta en 6 de los 12 de la Ruta del Mezcal (50 %).

Los municipios faltantes (Caltepec, Tepexi, Naupan, Zoquitlán…) son productores **reconocidos por la Secretaría pero sin registro en el DENUE**. Se marcan con el nivel `reconocida_sin_registro`. Es evidencia directa de la oferta invisible y de la limitación "productores fuera del DENUE".

**Predominancia por actividad:** cociente de localización `CL = (PO_act,mun / PO_mun) / (PO_act,estado / PO_estado)`.

| Nivel | Regla |
|---|---|
| Muy alta | CL ≥ 2 y al menos 3 unidades |
| Alta | 1.25 ≤ CL < 2 |
| Media | 0.75 ≤ CL < 1.25 |
| Baja | CL > 0 y por debajo del nivel medio |
| Sin oferta | CL = 0 |

**Principales actividades del municipio:** el top 3 por un puntaje que mezcla 50 % CL normalizado, 30 % volumen y 20 % presencia en catálogo. Si una actividad solo tiene señal de catálogo y ninguna del DENUE, se muestra marcada como "reconocida, sin establecimientos registrados". **Esa diferencia es justo uno de los flags.**

### A2 · Infraestructura y accesibilidad (qué tan fácil es llegar y quedarse)
| Indicador | Cálculo | Fuente |
|---|---|---|
| Minutos al ancla más cercana | Grafo `fact_accesibilidad` (tiempo estimado) | Centroides INEGI + factor de rodeo |
| Municipios colindantes | `fact_accesibilidad.es_colindante` | Marco Geoestadístico |
| Densidad de red vial pavimentada (km/km²) | Longitud de vías `highway` ∈ {primary, secondary, tertiary, trunk} con `surface` pavimentada | OSM (Overpass) o Red Nacional de Caminos (INEGI) |
| Capacidad de hospedaje | Unidades y personal en SCIAN 721 | DENUE |
| Servicios al visitante | Gasolineras, cajeros, farmacias, clínicas y terminal de autobuses por cada 10 mil habitantes | OSM / DENUE (468411, 522110, 464111, 621…) |
| Conectividad digital | % de viviendas con internet | Censo 2020 (`fact_contexto_social`) |

**Índice de infraestructura (0-1)** = promedio de percentiles: 35 % acceso al ancla (invertido), 25 % red vial, 20 % hospedaje, 10 % servicios y 10 % internet.

### A3 · Demanda actual y temporadas (cuánto turismo hay y cuándo)
**Nivel de turismo actual (intensidad).** Los datos son de *oferta*, no de visitantes, así que se mide con proxies y se declara así:

| Proxy | Peso |
|---|---|
| Personal ocupado en hospedaje + alimentos por cada 1,000 habitantes (DENUE) | 40 % |
| Unidades de hospedaje (DENUE 721) | 25 % |
| Presencia en rutas oficiales (número de rutas existentes que lo incluyen) | 15 % |
| Pueblo Mágico / ancla | 10 % |
| Visibilidad (menciones en boletines y fuentes oficiales; si no hay datos, se omite y se renormaliza) | 10 % |

Validación externa: DATATUR (ocupación hotelera) existe para Puebla capital y pocos destinos. Se usa para comprobar que el proxy ordena bien esos destinos, no para todos los municipios.

**Temporadas.** Hay tres capas que se suman en una tira de 12 meses por municipio:
1. **Base nacional** (igual para todos): Semana Santa (mar-abr), verano (jul-ago), Día de Muertos (oct-nov) e invierno (dic).
2. **Temporada de la actividad:** cosecha de café (nov-mar), luciérnagas (jun-jul), manzana y sidra (ago-sep), chiles en nogada (ago-sep), Día de Muertos en Huaquechula (nov), avistamiento de mariposa monarca y otras.
3. **Fiestas y ferias municipales:** fiesta patronal, ferias y festivales. Fuentes: calendario de la Sectur Puebla, el **Sistema de Información Cultural (SIC, Secretaría de Cultura)**, que tiene festivales por municipio, y los sitios oficiales de los ayuntamientos.

Resultado: `intensidad_mes ∈ {0, 1, 2, 3}` por municipio y mes. La ficha muestra los **meses fuertes** (intensidad ≥ 2) y el **evento principal**.

### A4 · Contexto social (a quién beneficia) · Raúl
`fact_contexto_social`: población, índice y grado de marginación (CONAPO), % de pobreza y % de viviendas con internet. Se usa como **necesidad social**: pesa a favor de proponer un municipio, nunca en contra.

> **Mientras Raúl carga CONAPO:** el semáforo social usa un **índice de carencias** calculado con el ITER del Censo 2020 (INEGI). Es el promedio de percentiles de analfabetismo, población sin escolaridad, viviendas sin drenaje, sin electricidad, sin agua entubada, con piso de tierra y sin refrigerador, y de ocupantes por cuarto, que son las variables con que CONAPO construye su índice. En cuanto `fact_contexto_social` tenga datos, `calcular_ficha.py` usa el grado de CONAPO automáticamente. El sitio de CONAPO tiene una verificación anti-bot y no se descargó por script.

### A5 · Predicción (qué puede crecer) · Raúl
| Modelo | Tarea | Salida | Tabla |
|---|---|---|---|
| Crecimiento por eje | Regresión del Δ log de personal ocupado 2019→2024 (validación temporal: entrenar 2014→2019 y probar 2019→2024) | % de crecimiento esperado + intervalo | `fact_prediccion_crecimiento` |
| Enlace entre municipios | Clasificación: ¿el par (a, b) podría formar parte de una misma ruta? Positivos = pares de rutas existentes (`v_pares_rutas_existentes`, 84 tramos) | Probabilidad del par | `fact_prediccion_enlace` |
| Perfil / similitud | Clustering de perfiles A1-A4 + coseno | Cluster y similitud | `fact_cluster_municipio`, `fact_similitud` |

**Líneas base obligatorias** para presumir que "la IA aporta":
- Crecimiento: persistencia (crecimiento igual al del periodo anterior) y la media del eje.
- Enlace: distancia inversa y "mismo cluster".

Si el modelo no le gana a la línea base, se usa la línea base y se dice.

### A6 · Decisión (qué rutas proponemos) · Styveen
1. **Índice de oportunidad** por municipio × actividad (versión `v2_con_prediccion`):
   `0.25·oferta + 0.20·social + 0.25·accesibilidad + 0.10·complementarios + 0.20·potencial_predicho`
2. **Flags** (`fact_flag_oportunidad`): OFERTA_EMERGENTE, ACCESIBLE_NO_EXPLOTADO, BARRERA_ACCESO, IMPACTO_SOCIAL; con un `motivo` legible.
3. **Optimizador de rutas.** Es un *Orienteering Problem* con restricciones:
   - Paradas: entre 3 y 6.
   - Tiempos: cada tramo ≤ 75 min y el total ≤ 240 min.
   - Al menos 1 ancla y al menos 2 municipios con flag.
   - Coherencia temática: misma actividad principal o similitud ≥ umbral, y probabilidad de enlace alta.
   - Diversidad: dos rutas no comparten más del 50 % de sus municipios.
   - **Temporada compatible:** los municipios deben compartir al menos un mes fuerte, así la ruta se puede vender como "ruta de temporada".
4. **Valor del municipio en la ruta** = índice × (1 + bono por flag) × (1 + bono social). Se resuelve con inserción voraz por valor/minuto desde cada ancla y luego 2-opt o búsqueda local.
5. **Novedad:** `v_novedad_ruta` compara cada ruta contra las 29 rutas oficiales y la clasifica como *nueva*, *parcialmente existente* o *existente*.
6. **Escritura:** `dim_ruta` (origen `propuesta_modelo`), `fact_ruta_parada` y `fact_ruta_evaluacion`.

---

## 3. Ficha técnica municipal (hover y clic en el mapa)

### 3.1 Semáforos
Cinco dimensiones, con la misma regla de color en todas: **el color dice qué hacer, no si el municipio es "bueno" o "malo"**.

| Dimensión | Valor base | 🟢 | 🟡 | 🔴 | ⚪ |
|---|---|---|---|---|---|
| **Turismo actual** (A3) | Intensidad proxy, en percentil | Bajo: tiene capacidad de recibir visitantes (P < 50) | Medio (P 50-85) | Alto/concentrado: no conviene cargarlo más (P ≥ 85 o ancla) | Sin oferta registrada |
| **Infraestructura** (A2) | Índice de infraestructura | Lista para recibir (≥ 0.6) | Mejorable (0.35-0.6) | Barrera de acceso (< 0.35) | Sin datos |
| **Oferta turística** (A1) | Máximo CL entre actividades + volumen | Especializada (alguna actividad con predominancia muy alta o alta) | Diversa, sin especialización | Mínima | Sin oferta |
| **Potencial** (A5) | Crecimiento predicho por eje | Crecimiento por encima de la mediana estatal y con intervalo > 0 | Incierto (el intervalo cruza 0) | Estancado o en retroceso | Sin modelo |
| **Necesidad social** (A4) | Grado de marginación | Baja / muy baja | Media | Alta / muy alta: prioridad de impacto | Sin dato |

Además se muestran las **banderas de oportunidad** (los flags de A6) como etiquetas, cada una con su motivo.

**Lectura del mapa para el jurado:** un municipio 🟢 en turismo actual, 🟢 en oferta y 🟢/🟡 en infraestructura es **justo el que queremos llevar a una ruta**. Uno 🔴 en turismo actual es un ancla que *envía* visitantes.

Los umbrales son percentiles estatales y se guardan con la `version_sk` del cálculo, igual que los pesos del índice. Así cualquier cambio queda registrado y se puede comparar.

### 3.2 Hover (tooltip, 1 segundo de lectura)
```
┌────────────────────────────────────┐
│ Cuetzalan del Progreso  ✨⚓        │
│ Sierra Nororiental                  │
│ ☕ Café · 🌲 Ecoturismo · 🤝 Comun.  │
│ Turismo 🔴  Infra 🟡  Oferta 🟢     │
│ Meses fuertes: oct · nov · mar      │
└────────────────────────────────────┘
```

### 3.3 Clic (panel lateral / página Ficha)
```
┌──────────────────────────────────────────────────────────────────┐
│ CUETZALAN DEL PROGRESO  · 21043 · Sierra Nororiental             │
│ ✨ Pueblo Mágico (2002) · ⚓ Ancla · 47,433 hab · Marginación alta │
├─────────────── SEMÁFOROS ────────────────────────────────────────┤
│ Turismo actual 🔴  Infraestructura 🟡  Oferta 🟢  Potencial 🟢  Social 🔴 │
├─────────────── A1 · ACTIVIDADES PRINCIPALES ─────────────────────┤
│ ☕ Café            ████████ CL 3.4  muy alta  · 42 establecimientos│
│ 🌲 Ecoturismo      █████    CL 2.1  muy alta  · 18                 │
│ 🤝 Comunitario     ████     CL 1.6  alta      · 9 (Tosepan Kali…)  │
├─────────────── A2 · INFRAESTRUCTURA ─────────────────────────────┤
│ 🚗 34 min al ancla más cercana (Zacapoaxtla→…) · vías 0.42 km/km² │
│ 🏨 63 unidades de hospedaje · 🏧 2 cajeros · ⛽ 1 gasolinera        │
├─────────────── A3 · TEMPORADAS ──────────────────────────────────┤
│ E  F  M  A  M  J  J  A  S  O  N  D                                │
│ ▂  ▂  ▅  ▅  ▂  ▂  ▅  ▅  ▂  █  █  ▅   Feria del Café y del Huipil (oct) │
├─────────────── A5 · PREDICCIÓN ──────────────────────────────────┤
│ Hospedaje +8.2 % [+3.1, +13.0] a 5 años · rank 12/217             │
├─────────────── RUTAS ────────────────────────────────────────────┤
│ Existentes: Bioruta del Café (Nororiental), Pueblos Mágicos 3.ª,  │
│ Moles Poblanos · Propuestas: —                                    │
├─────────────── BANDERAS ─────────────────────────────────────────┤
│ 🚩 IMPACTO_SOCIAL: flag activo con marginación alta               │
└──────────────────────────────────────────────────────────────────┘
```
*(Las cifras son ilustrativas: muestran el formato, no datos reales.)*

### 3.4 De dónde lee la ficha
Una sola vista `dw.v_ficha_municipio`, con una fila por municipio y JSON para las listas. Así el tablero hace **una consulta** y el mapa se mantiene rápido:
`identidad + semaforos{} + actividades[] + infraestructura{} + temporadas[12] + eventos[] + prediccion{} + rutas[] + banderas[]`.

---

## 4. Tablas nuevas (propuesta, `sql/05_ddl_ficha_y_actividades.sql`)
| Tabla | Grano | Dueño |
|---|---|---|
| `dw.dim_actividad` | Actividad temática (14) | Styveen |
| `dw.regla_actividad` | Regla de asignación: SCIAN, palabra clave u OSM → actividad | Styveen |
| `dw.fact_actividad_municipio` | Municipio × actividad × periodo: unidades, personal, CL, nivel, es_principal, origen de la señal | Styveen (lee `stg.denue` de Galo) |
| `dw.fact_infraestructura` | Municipio × indicador | Styveen |
| `dw.fact_temporada` | Municipio × evento o temporada, con meses e intensidad | Styveen |
| `dw.fact_semaforo_municipio` | Municipio × dimensión × versión: nivel, valor, percentil, motivo | Styveen |
| `dw.v_ficha_municipio` | Vista: una fila por municipio | Styveen |

No se modifica ninguna tabla de Galo ni de Raúl. Solo se leen.

---

## 5. Validaciones

| # | Validación | Criterio de aceptación |
|---|---|---|
| V1 | **Cobertura:** los 217 municipios tienen A0, A2 y A4 | 100 % |
| V2 | **Coherencia de anclas:** las 12 anclas tienen turismo actual 🔴 o 🟡 | ≥ 11 de 12; las excepciones se documentan |
| V3 | **Actividades contra catálogo:** ¿el DENUE detecta ☕ en los municipios de la Bioruta y 🥃 en los de la Ruta del Mezcal? | Resultado: café 66 %, mezcal 50 %. La brecha se reporta como oferta reconocida sin registro, no como error |
| V4 | **Validación temporal** del crecimiento (2014→2019 para entrenar, 2019→2024 para probar) | Gana a la persistencia en MAE |
| V5 | **Enlace:** AUC sobre pares de rutas existentes, excluidos del entrenamiento por ruta | AUC > línea base de distancia |
| V6 | **Sensibilidad del índice:** ±20 % en cada peso | El top 20 conserva ≥ 70 % de sus municipios |
| V7 | **Novedad de las rutas:** las propuestas se clasifican contra las 29 oficiales | Al menos 1 *nueva* y 1 *parcialmente existente* |
| V8 | **Descentralización:** HHI del personal turístico hoy contra el escenario hipotético con rutas | Se presenta como escenario con supuesto, no como predicción |
| V9 | **Proxy de turismo contra DATATUR** en los destinos con datos | Orden de Spearman ≥ 0.6 |

---

## 6. Plan de trabajo (empezamos por la ficha)
| Paso | Entrega | Depende de |
|---|---|---|
| 1 | DDL de tablas nuevas (`sql/05_ddl_ficha_y_actividades.sql`) y catálogo de 14 actividades ✅ | — |
| 2 | **A1 actividades:** DENUE 05/2026 → `fact_actividad_municipio` ✅ 3,038 filas (14 × 217) | Descarga directa de INEGI |
| 3 | **A2 infraestructura** ✅ 21 indicadores × 217 en `fact_infraestructura` (`scripts/calcular_ficha.py`) | Marco INEGI, OSM, DENUE, ITER 2020 |
| 4 | **A3 temporadas** ✅ 30 temporadas y eventos en `fact_temporada` (`data/catalogos/temporadas.csv`) | Calendario SEP, Sectur, prensa |
| 5 | Semáforos ✅ 1,085 en `fact_semaforo_municipio` (versión `ficha_semaforos_v1`) + vista `dw.v_ficha_municipio` ✅ (`sql/06`) | A1-A4 |
| 6 | Tablero ✅ página **Ficha técnica (datos reales)**: mapa por semáforo, tooltip al pasar el cursor y ficha al hacer clic | 5 |
| 7 | A6: optimizador con índice v1 → v2 cuando llegue la predicción de Raúl | A5 |

## 7. Lo que no vamos a afirmar
- Que el modelo mide visitantes: mide **oferta** y usa proxies de demanda.
- Que una ruta "garantiza" derrama: es una **hipótesis de trabajo** que hay que validar con las comunidades.
- Que el semáforo rojo es "malo": significa "ya concentra turismo".
