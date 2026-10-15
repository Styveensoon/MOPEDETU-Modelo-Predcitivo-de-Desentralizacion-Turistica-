# MOPEDETU · Contexto completo del proyecto

> **Modelo Predictivo de Descentralización Turística de Puebla.**
> Este documento describe el proyecto de punta a punta para alguien que **no ha visto el código**: qué problema
> resuelve, de qué datos parte, cómo está organizada la base de datos, qué hace cada script y cada módulo, cómo
> funciona el tablero página por página y qué resultados produce hoy.
>
> Las fórmulas, umbrales, reglas de validación y criterios exactos con los que se predicen índices, crecimiento,
> enlaces, rutas y circuitos están en el documento hermano **[`Validations.md`](Validations.md)**. Aquí se
> mencionan para dar contexto; allá se detallan número por número.

Fecha de corte de este documento: **15 de octubre de 2026** (estado de la rama `main`, commit `f6c633d`).

---

## Índice

1. [Qué es MOPEDETU](#1-qué-es-mopedetu)
2. [Equipo, roles y propiedad de las tablas](#2-equipo-roles-y-propiedad-de-las-tablas)
3. [Mapa del repositorio](#3-mapa-del-repositorio)
4. [Arquitectura general](#4-arquitectura-general)
5. [Fuentes de datos](#5-fuentes-de-datos)
6. [Base de datos (Supabase · PostgreSQL + PostGIS)](#6-base-de-datos-supabase--postgresql--postgis)
7. [Pipeline de carga y cálculo (ETL)](#7-pipeline-de-carga-y-cálculo-etl)
8. [El modelo por anillos (A0 a A6)](#8-el-modelo-por-anillos-a0-a6)
9. [Módulos de Python del modelo (`model/`)](#9-módulos-de-python-del-modelo-model)
10. [El tablero (`dashboard/`)](#10-el-tablero-dashboard)
11. [Página por página](#11-página-por-página)
12. [Mapas y navegación satelital](#12-mapas-y-navegación-satelital)
13. [Datos DEMO y motor ligero del tablero](#13-datos-demo-y-motor-ligero-del-tablero)
14. [Cómo ejecutar todo](#14-cómo-ejecutar-todo)
15. [Resultados actuales](#15-resultados-actuales)
16. [Archivos de datos versionados](#16-archivos-de-datos-versionados)
17. [Seguridad y credenciales](#17-seguridad-y-credenciales)
18. [Pruebas](#18-pruebas)
19. [Limitaciones, pendientes y discrepancias conocidas](#19-limitaciones-pendientes-y-discrepancias-conocidas)
20. [Glosario](#20-glosario)

---

## 1. Qué es MOPEDETU

### 1.1 El problema

El turismo de Puebla se concentra en pocos destinos: la capital, Cholula, Atlixco y algunos Pueblos Mágicos.
Muchos de los **217 municipios** del estado tienen patrimonio, naturaleza, gastronomía y tradiciones con potencial,
pero reciben poca derrama económica.

La cifra que resume el problema sale de la propia base de datos (vista `dw.v_concentracion`, personal ocupado
turístico estimado con el DENUE 05/2026):

> **5 municipios concentran el 51.9 % de la oferta turística del estado. Índice Herfindahl-Hirschman (HHI) = 1,306.**

### 1.2 El objetivo

Construir un sistema que:

1. **Identifique municipios con potencial turístico subaprovechado** con un *índice de oportunidad* por municipio
   y eje turístico, más *banderas* (flags) que explican por qué.
2. **Prediga** cuánto puede crecer la oferta turística de cada municipio en los próximos 5 años (modelo de
   aprendizaje automático validado contra líneas base).
3. **Proponga rutas turísticas nuevas** que salgan de un destino consolidado (*ancla*) y lleven visitantes a
   municipios emergentes, y las **compare contra las 29 rutas oficiales** de la Secretaría de Desarrollo Turístico
   para demostrar que son nuevas.
4. Lo muestre todo en un **tablero interactivo** con mapas, fichas técnicas por municipio, simulador de escenarios
   y navegación satelital de rutas y circuitos.

### 1.3 Contexto de entrega

- Hackathon **"Puebla Turística 360°"** (Tech Capital 2026). Presentación: **viernes 16 de octubre de 2026**.
- Los entregables exigidos por la convocatoria y su estado están en `docs/entregables.md`.

### 1.4 Lo que el proyecto **no** afirma

Esta frase atraviesa todo el diseño: los datos son de **oferta** (establecimientos, empleo, unidades económicas),
**no de visitantes ni de derrama**. Por eso:

- El modelo predice **potencial de crecimiento de la oferta turística**, no turistas.
- Las rutas son **hipótesis de trabajo** que deben validarse con las comunidades.
- El escenario "con rutas" o "con inversión" es un **escenario hipotético basado en correlaciones**, no una
  prueba causal.
- Un semáforo rojo en "turismo actual" **no es malo**: significa "ya concentra turismo, no conviene cargarlo más".

---

## 2. Equipo, roles y propiedad de las tablas

| Rol | Persona | Responsabilidad | Tablas que solo esa persona escribe |
|---|---|---|---|
| **A** | Galo | Base de datos, ETL, oferta e índice | `dim_municipio` (geometría), `dim_scian`, `bridge_scian_eje`, `dim_establecimiento`, `fact_oferta_municipio_eje`, `fact_accesibilidad`, `stg.*`, catálogos del DDL. Es el único que ejecuta cambios de estructura (DDL). |
| **B** | Raúl | Datos censales, contexto social, modelo predictivo de personal ocupado, frontend del tablero | `stg.censo_economico`, `stg.contexto_social`, `data/modelo/*` |
| **C** | Styveen | Rutas, mapa, ficha técnica, modelo de crecimiento de unidades, índice v2, enlaces, optimizador, entregables | `dim_ruta`, `fact_ruta_parada`, `fact_ruta_evaluacion`, columnas `es_pueblo_magico` / `es_ancla` / `region` de `dim_municipio`, tablas de `sql/05` a `sql/08` |

En la práctica, el rol C terminó cargando también datos base que eran del rol A (`scripts/cargar_datos_base.py`)
para no bloquear el modelo; todos los scripts sincronizan por clave natural (`cve_geo`, nombre) y son idempotentes.

**Ramas Git:** `main` (estable), `Styveen`, `Raul`, `Galo`. Commits con *Conventional Commits* (`feat:`, `fix:`,
`docs:`, `data:`). El último merge integró la rama de Styveen (lógica y modelo) sobre la de Raúl (frontend y ETL).

---

## 3. Mapa del repositorio

```
HACK2026/
├── README.md                     Presentación del proyecto
├── MOPEDETU.bat / mopedetu.sh    Lanzadores del tablero (Windows / macOS-Linux)
├── iniciar.py                    Lanzador multiplataforma: crea .venv, instala dependencias y abre Streamlit
├── requirements.txt              streamlit, pydeck, plotly, pandas, numpy, scikit-learn, scipy
├── package.json                  Dependencia @supabase/server (no la usa el código Python)
├── .env.example                  Plantilla de credenciales de Supabase
├── .streamlit/config.toml        Tema claro del tablero (colores Talavera)
├── tareas_A_galo.md              Plan de trabajo del rol A
│
├── DDL/                          Estructura de la base de datos (núcleo del equipo)
│   ├── 01_ddl_mopedetu.sql       Esquemas stg/dw, dimensiones, hechos, índices y vistas base
│   ├── 02_etl_mopedetu.sql       ETL SQL de stg → dw por pasos (0 a 7)
│   ├── 03_ddl_prediccion_mopedetu.sql  Capa de predicción: dim_modelo, predicciones, evaluación y novedad de rutas
│   └── 04_permisos_mopedetu.sql  Permisos de los roles dev_raul y dev_styveen
│
├── sql/                          Estructura agregada por el rol C
│   ├── 04_catalogo_rutas_styveen.sql   SQL generado: rutas oficiales, Pueblos Mágicos, anclas, regiones
│   ├── 05_ddl_ficha_y_actividades.sql  Actividades, infraestructura, temporadas y semáforos (+ RLS)
│   ├── 06_vista_ficha_municipio.sql    Vista dw.v_ficha_municipio (una fila por municipio con JSON)
│   ├── 07_vistas_rutas.sql             Vistas dw.v_ruta_parada y dw.v_indice_municipio
│   └── 08_atractivos_lugar.sql         Tabla dw.fact_atractivo_lugar (lugares con nombre)
│
├── scripts/                      Descarga, carga y cálculo de datos (anillos A0-A3)
│   ├── db.py                     Conexión psycopg a Postgres con DATABASE_URL
│   ├── ejecutar_sql.py           Ejecuta un .sql completo o pasos del ETL en una transacción
│   ├── consultar.py              Consulta de solo lectura para verificaciones
│   ├── crear_roles.py            Crea los roles dev_raul / dev_styveen con contraseñas largas
│   ├── preparar_geo.py           Simplifica el GeoJSON de INEGI para el tablero
│   ├── cargar_municipios.py      217 polígonos → stg.mun_geo y dw.dim_municipio
│   ├── cargar_mun_geo.py         Alternativa: Marco Geoestadístico (shapefile) → stg.mun_geo
│   ├── cargar_denue.py           Alternativa: DENUE → stg.totales_municipio y stg.denue
│   ├── cargar_datos_base.py      Carga integral: SCIAN, DENUE, oferta, censos, social, accesibilidad, atractivos
│   ├── cargar_rutas_existentes.py 29 rutas oficiales, Pueblos Mágicos, anclas y regiones
│   ├── cargar_atractivos.py      Lugares con nombre (catálogo curado + OSM) → fact_atractivo_lugar
│   ├── calcular_actividades.py   14 actividades temáticas por municipio (A1)
│   ├── calcular_ficha.py         Infraestructura (A2), temporadas (A3) y semáforos
│   ├── descargar_osm.py          Descarga de OpenStreetMap vía Overpass (vías, servicios, atractivos)
│   ├── buscar_osm_nuevos.py      Establecimientos de OSM que no están en el DENUE
│   ├── censo_economico.py        (Rol B) Censos Económicos 2014-2019-2024 → data/stg/
│   ├── contexto_social.py        (Rol B) CONAPO 2020 → data/stg/contexto_social.csv
│   ├── carga_stg_censo_economico.sql  (Rol B) \copy a stg.censo_economico
│   └── carga_stg_rol_b.sql       (Rol B) \copy de contexto social y predicciones a stg
│
├── model/                        Modelos (anillos A4-A6)
│   ├── base.py                   Carga común de datos desde Supabase y utilidades de escritura
│   ├── actividades.py            Catálogo de 14 actividades y reglas de detección
│   ├── indice.py                 Índice de oportunidad v1 y banderas
│   ├── crecimiento.py            Modelo de crecimiento de unidades (LightGBM) + índice v2
│   ├── enlaces.py                Perfiles, similitud, clusters y modelo de enlaces (LightGBM)
│   ├── rutas.py                  Optimizador de rutas nuevas
│   ├── escenario_hhi.py          Concentración hoy / tendencial / hipotético con rutas
│   └── prediccion_crecimiento.py (Rol B) Modelo de crecimiento del personal ocupado con validación temporal
│
├── dashboard/                    Tablero Streamlit
│   ├── app.py                    Punto de entrada y navegación
│   ├── estado.py                 Barra lateral, contexto y cachés
│   ├── datos.py                  Generador de datos DEMO sobre los 217 municipios reales
│   ├── motor.py                  Motor analítico ligero (índice, flags, crecimiento, rutas, circuitos, HHI)
│   ├── supabase_cliente.py       Cliente PostgREST mínimo (sin dependencias)
│   ├── ficha_bd.py               Lectura de vistas reales de Supabase para el tablero
│   ├── mapas.py                  Mapas coropléticos Plotly (SVG o sobre mosaicos satelitales)
│   ├── navegacion.py             Mapa MapLibre GL con ruta real OSRM y recorrido animado
│   ├── tema.py                   Identidad visual Talavera (colores, CSS, escalas)
│   └── vistas/                   Una función render() por página
│       ├── panorama.py · ficha_tecnica.py · oportunidades.py · rutas.py
│       └── circuitos.py · simulador.py · ficha.py · alertas.py
│
├── data/
│   ├── geo/puebla_municipios.geojson     217 polígonos simplificados + centroides (lat, lon) y área
│   ├── catalogos/                         Capturas manuales con fuente
│   │   ├── rutas_existentes.csv          134 paradas de 29 rutas oficiales
│   │   ├── municipios_turismo.csv        217 municipios con región, Pueblo Mágico, año y ancla
│   │   ├── temporadas.csv                31 temporadas y eventos
│   │   └── atractivos.csv                8 lugares curados a mano (Jonotla, Zoquiapan)
│   ├── derivados/                         Salidas de los scripts y modelos (copias locales)
│   ├── stg/                               Entradas del rol B (censos y contexto social)
│   ├── modelo/                            Salidas del modelo del rol B
│   ├── processed/                         Resultado de buscar_osm_nuevos.py
│   └── raw/                               Descargas pesadas (no se versionan)
│
├── docs/                          Documentación (este archivo, Validations.md y los de diseño)
└── tests/test_tablero.py          Prueba de humo de todas las páginas
```

---

## 4. Arquitectura general

### 4.1 Flujo de datos de punta a punta

```
 FUENTES                         CARGA (scripts/)                 SUPABASE (stg → dw)           MODELO (model/)                 TABLERO (dashboard/)
 ───────                         ────────────────                 ───────────────────           ───────────────                 ────────────────────
 DENUE 05/2026 ─────┐
 Censos Económicos ─┤            cargar_datos_base.py ───────►   stg.denue, stg.totales        indice.py      ─► índice v1 + banderas
 ITER 2020 ─────────┤            cargar_municipios.py ───────►   dim_municipio, dim_scian     crecimiento.py ─► predicción + índice v2
 CONAPO / CONEVAL ──┤            cargar_rutas_existentes.py ─►   fact_oferta, fact_censo      enlaces.py     ─► clusters, similitud, enlaces   ─►  Ficha técnica (real)
 Marco INEGI ───────┤            calcular_actividades.py ────►   fact_contexto_social         rutas.py       ─► 5 rutas nuevas + evaluación    ─►  Rutas del modelo (real)
 OpenStreetMap ─────┤            calcular_ficha.py ──────────►   fact_accesibilidad           escenario_hhi.py ─► HHI hoy / con rutas          ─►  Panorama, Mapa, Simulador,
 Rutas oficiales ───┤            cargar_atractivos.py ───────►   fact_actividad_municipio                                                      Circuitos, Ficha, Alertas
 Pueblos Mágicos ───┤                                             fact_infraestructura,                                                        (motor DEMO)
 Temporadas ────────┘                                             fact_temporada, semáforos
```

### 4.2 Dos "mundos" dentro del tablero

Es importante entender que el tablero mezcla dos fuentes:

| Mundo | Páginas | Fuente | Qué calcula |
|---|---|---|---|
| **Datos reales** | 🏘️ *Ficha técnica (datos reales)* y 🧭 *Rutas → Rutas del modelo* | Vistas de Supabase (`v_ficha_municipio`, `v_ruta_parada`, `v_indice_municipio`) leídas con la *publishable key* | Nada: muestra lo que el pipeline (`scripts/` + `model/`) dejó calculado |
| **Motor DEMO** | 🏠 Panorama, 🗺️ Mapa de oportunidades, 🛠️ Arma tu ruta, 🔁 Circuitos, 🔮 Simulador, 🏘️ Ficha municipal, 🚩 Alertas | `dashboard/datos.py` genera datos **sintéticos pero coherentes** sobre los 217 municipios reales (geometría real, valores simulados) y `dashboard/motor.py` los procesa en milisegundos | Índice, flags, crecimiento, escenarios, rutas y circuitos "en vivo" según la barra lateral |

La barra lateral lo advierte con la etiqueta *"⚠️ Datos DEMO simulados sobre los 217 municipios reales"*. El diseño
previó que `cargar_datos()` lea algún día de Supabase sin cambiar el resto del tablero (`FUENTE = "demo"` en
`datos.py`), pero esa conexión no está implementada.

### 4.3 Arquitectura en anillos

El proyecto organiza el cálculo en **anillos concéntricos**: cada anillo consume lo que producen los internos y
nunca al revés. Si cambia un anillo interior (por ejemplo, llega un DENUE nuevo) hay que recalcular todo lo que está
afuera; si cambia uno exterior (por ejemplo, los pesos del índice) no se tocan los internos.

| Anillo | Qué responde | Implementación real |
|---|---|---|
| **A0 · Identidad** | ¿Qué municipio es y dónde está? | `dim_municipio`, región, Pueblo Mágico, ancla, rutas oficiales |
| **A1 · Oferta y actividades** | ¿Qué se puede hacer ahí? | 4 ejes económicos (`fact_oferta_municipio_eje`) + 14 actividades temáticas (`fact_actividad_municipio`) |
| **A2 · Infraestructura** | ¿Qué tan fácil es llegar y quedarse? | 21 indicadores en `fact_infraestructura` (tiempos, vías OSM, hospedaje, servicios, internet) |
| **A3 · Demanda y temporada** | ¿Cuánto turismo hay hoy y cuándo? | Intensidad turística (proxy) y temporadas (`fact_temporada`) |
| **A4 · Contexto social** | ¿A quién beneficia? | `fact_contexto_social` (CONAPO, CONEVAL, ITER) |
| **A5 · Predicción** | ¿Qué puede crecer y qué municipios se enlazan? | Modelo de crecimiento (LightGBM), clusters, similitud, modelo de enlaces |
| **A6 · Decisión** | ¿Qué rutas proponemos? | Índice de oportunidad v1/v2, banderas, optimizador de rutas, novedad, escenario HHI |

La **ficha técnica** que ve el usuario al hacer clic en un municipio es A0 + A1 + A2 + A3 + A4 resumidos en
semáforos; el **modelo** que propone rutas es A5 + A6 alimentados por todos los anteriores.

> Nota: `docs/arquitectura_modelo_y_tablero.md` describe una versión aspiracional con otros números de anillo
> (A3 = predicción, A5 = rutas, A6 = simulación), un paquete `mopedetu/` con orquestador por *hash*, esquema `ml`,
> OR-Tools y GitHub Actions. **Nada de eso existe en el código**: la numeración vigente es la de esta tabla
> (`docs/modelo_predictivo_anillos.md`) y la orquestación es manual, script por script.

---

## 5. Fuentes de datos

Fecha de consulta de todas las fuentes: **14 de octubre de 2026**. Cada fuente tiene su fila en `dw.dim_fuente`
con URL, versión, licencia, cobertura, notas de calidad y uso en el modelo.

| Fuente | Institución | Versión | Qué aporta | Dónde entra |
|---|---|---|---|---|
| **DENUE** | INEGI | 05/2026, 410,693 establecimientos de Puebla | Establecimientos con SCIAN, estrato de personal, coordenadas y nombre | Oferta por eje (A1), actividades (A1), hospedaje y servicios (A2), intensidad (A3) |
| **Censos Económicos** | INEGI | CE 2019 (SCIAN 2018) y CE 2024 (SCIAN 2023), datos abiertos por entidad; el rol B usa además la versión histórica homologada 2014-2019-2024 | Unidades, personal ocupado y valor agregado por municipio y código SCIAN | Modelos de crecimiento (A5) |
| **Censo de Población y Vivienda 2020 (ITER)** | INEGI | Principales resultados por localidad, renglones de total municipal | Población, % de viviendas con internet, variables de carencias | A2, A4 |
| **Índice de marginación 2020** | CONAPO | Método DP2; copia de `IMM_2020.xlsx` del repositorio IndiceMx (el sitio de CONAPO bloquea descargas automáticas) | Índice y grado de marginación | A4 (necesidad social) |
| **Pobreza municipal 2020** | CONEVAL | Concentrado de indicadores municipales | % de población en pobreza | A4, variable del modelo |
| **Marco Geoestadístico** | INEGI | Polígonos 2023 (vía PhantomInsights/mexico-geojson) | Polígonos, claves, centroides, superficie, colindancia | A0, A2 |
| **OpenStreetMap** | Colaboradores OSM (ODbL) | Consulta Overpass del 14/10/2026 | Red vial principal, terminales, atractivos con nombre | A2, A1 (lugares) |
| **Zonas arqueológicas INAH** | INAH | Cholula, Cantona, Yohualichan, Tepexi el Viejo | Señal de catálogo para arqueología | A1 |
| **Catálogo de Rutas Turísticas** | Secretaría de Desarrollo Turístico de Puebla | PDF, 22 rutas en 4 circuitos | Rutas oficiales | Novedad, modelo de enlaces |
| **Guía Bioruta del Café** | Sectur Puebla | PDF, 4 circuitos, 29 municipios numerados | Rutas oficiales del café | Novedad, actividad café |
| **Guía Ruta del Mezcal Poblano** | Sectur Puebla | PDF, 3 circuitos con orden A-E | Rutas oficiales del mezcal | Novedad, actividad mezcal |
| **Pueblos Mágicos** | SECTUR (vía prensa: N+, Milenio, gopueblos.com) | 12 Pueblos Mágicos = 13 municipios, nombramientos 2002-2023 | Marca turística y criterio de ancla | A0 |
| **Regionalización socioeconómica** | Congreso del Estado (2015), transcrita de Wikipedia | 7 regiones | Región de cada municipio | A0, filtros, selección de rutas |
| **Calendario de ferias y temporadas** | SEP, Sectur Puebla, prensa, agregadores | 2026 | Temporadas nacionales, por actividad y eventos municipales | A3 |
| **Catálogo curado de atractivos** | MOPEDETU (revisión manual con fuente por lugar) | 8 lugares | Lugares sin negocio detrás (El Peñón de Jonotla) | A1 |

**Decisiones de homologación importantes** (detalle en `docs/datos_base.md`):

- El archivo del CE 2019 trae una coma final por renglón: se lee con `index_col=False` para que no se corran las columnas.
- Las celdas confidenciales del censo vienen vacías: se marcan (`hay_confidencial` / `confidencial`) y **no se rellenan**.
- El CE 2014 no tiene descarga directa por entidad; el rol B lo obtuvo de la versión histórica publicada con el CE 2024.
- El DDL solo admite niveles `Alta / Media / Baja` en `fact_oferta_municipio_eje`: `muy_alta → Alta`, `sin_oferta → NULL`.
- La validación de CONAPO contra un índice de carencias propio del Censo 2020 dio Spearman **−0.914** (el signo
  es negativo porque en el índice DP2 un valor mayor significa **menos** marginación).
- Totales estatales del CE coinciden con INEGI: 1,117,993 personas ocupadas (2019) y 1,251,065 (2024).

---

## 6. Base de datos (Supabase · PostgreSQL + PostGIS)

### 6.1 Esquemas y convenciones

- **Motor:** PostgreSQL 15+ con PostGIS (en el esquema `extensions`), alojado en Supabase capa gratuita (~500 MB).
- **`stg`**: datos de entrada filtrados, nunca se editan a mano.
- **`dw`**: modelo dimensional tipo **constelación** (varias tablas de hechos que comparten dimensiones, Kimball).
- Convenciones: `snake_case`, prefijos `dim_`, `fact_`, `bridge_`; llaves subrogadas `*_sk` (identity); claves
  naturales conservadas (`cve_geo`, `codigo_scian`). Todos los DDL son idempotentes (`IF NOT EXISTS`,
  `ON CONFLICT DO NOTHING`, `CREATE OR REPLACE VIEW`).
- **Acceso:** los scripts escriben vía **PostgREST** (la API REST de Supabase) con la *secret key*; el tablero lee
  con la *publishable key*, sujeta a **RLS** (Row Level Security) con política de solo lectura.

### 6.2 Staging (`stg`)

| Tabla | Grano | Contenido |
|---|---|---|
| `stg.denue` | Establecimiento turístico | 60,446 establecimientos del DENUE 05/2026 cuyas clases SCIAN pertenecen a algún eje; id, nombre, SCIAN, rango de personal, municipio, coordenadas, fecha de alta, corte |
| `stg.totales_municipio` | Municipio | Unidades y personal estimado de **todos** los sectores (denominador del cociente de localización) |
| `stg.mun_geo` | Municipio | Polígono MultiPolygon EPSG:4326 |
| `stg.censo_economico` | Municipio × año censal × código SCIAN | Unidades, personal, valor agregado y bandera de confidencialidad (CE 2019 y 2024; 2,503 filas) |
| `stg.contexto_social`, `stg.dim_modelo`, `stg.prediccion_crecimiento` | — | Entregas del rol B (`scripts/carga_stg_rol_b.sql`) |

### 6.3 Dimensiones (`dw`)

| Tabla | Filas | Descripción |
|---|---|---|
| `dim_municipio` | 217 | `cve_geo` (21XXX), nombre, **región** (7), **es_pueblo_magico**, **es_ancla**, superficie, polígono y centroide |
| `dim_eje` | 5 | 0 = global, 1 = hospedaje, 2 = alimentos, 3 = turismo (y cultura), 4 = comercio turístico |
| `dim_scian` | 2,002 | Catálogo SCIAN 2023 + códigos del DENUE; `es_turistico` |
| `bridge_scian_eje` | 39 | Clase SCIAN → eje con **peso** (≤ 1 cuando la actividad atiende también a residentes) |
| `dim_estrato_personal` | 7 | Rango del DENUE → punto medio (2.5, 8, 20.5, 40.5, 75.5, 175.5, 300) |
| `dim_periodo` | — | `DENUE 2024-11`, `DENUE 2025-05`, `DENUE 2026-05`, `CE 2014`, `CE 2019`, `CE 2024`, `Censo Pob 2020` |
| `dim_fuente` | ≥ 15 | Inventario documentado de fuentes (entregable de la convocatoria) |
| `dim_establecimiento` | 60,446 | Un establecimiento turístico con municipio, SCIAN, estrato, periodo y punto PostGIS |
| `dim_version_calculo` | — | Versiones con sus **pesos en JSON**: `v1_base`, `v2_con_prediccion`, `perfil_v1`, `ficha_semaforos_v1` |
| `dim_tipo_flag` | 5 | `OFERTA_EMERGENTE`, `ACCESIBLE_NO_EXPLOTADO`, `BARRERA_ACCESO`, `IMPACTO_SOCIAL`, `OFERTA_INVISIBLE` |
| `dim_ruta` | 29 + 5 | Rutas: `origen ∈ {existente, propuesta_modelo}`, `tipo ∈ {ruta_intermunicipal, circuito_municipal}`, tema, duración, descripción, fuente |
| `dim_modelo` | — | Registro de cada modelo y línea base: tarea, algoritmo, variables, hiperparámetros, esquema de validación, métricas (JSON), explicabilidad, limitaciones |
| `dim_actividad` | 14 | Actividades temáticas con icono, eje y reglas de detección (JSON) |

### 6.4 Hechos (`dw`)

| Tabla | Grano | Filas | Escribe |
|---|---|---|---|
| `fact_oferta_municipio_eje` | municipio × eje × periodo | 868 | `cargar_datos_base.py` |
| `fact_censo_economico` | municipio × eje × censo | 1,736 | `cargar_datos_base.py` |
| `fact_contexto_social` | municipio × periodo | 217 | `cargar_datos_base.py` |
| `fact_accesibilidad` | municipio origen × destino | 46,872 | `cargar_datos_base.py` |
| `fact_atractivo` | municipio × fuente × categoría (conteos) | 208 | `cargar_datos_base.py` |
| `fact_atractivo_lugar` | lugar con nombre | 580 (8 curados + 572 OSM) en 102 municipios | `cargar_atractivos.py` |
| `fact_actividad_municipio` | municipio × actividad × periodo | 3,038 (217 × 14) | `calcular_actividades.py` |
| `fact_infraestructura` | municipio × indicador | 21 indicadores × 217 | `calcular_ficha.py` |
| `fact_temporada` | temporada o evento | 31 | `calcular_ficha.py` |
| `fact_semaforo_municipio` | municipio × dimensión × versión | 1,085 (217 × 5) | `calcular_ficha.py` |
| `fact_indice_oportunidad` | municipio × eje × periodo × versión | 868 por versión | `indice.py`, `crecimiento.py` |
| `fact_flag_oportunidad` | municipio × eje × tipo de bandera × versión | 4,340 por versión | `indice.py`, `crecimiento.py` |
| `fact_prediccion_crecimiento` | municipio × eje × modelo × periodo base × horizonte | 868 | `crecimiento.py` |
| `fact_cluster_municipio` | municipio × versión | 217 | `enlaces.py` |
| `fact_similitud` | par a < b × versión | 8,452 | `enlaces.py` |
| `fact_prediccion_enlace` | par a < b × modelo | 8,452 | `enlaces.py` |
| `fact_ruta_parada` | ruta × orden de parada | 134 oficiales + 30 propuestas | `cargar_rutas_existentes.py`, `rutas.py` |
| `fact_ruta_evaluacion` | ruta | 5 | `rutas.py` |

### 6.5 Vistas

| Vista | Qué devuelve | Quién la usa |
|---|---|---|
| `v_perfil_municipio` | Una fila por municipio con CL y personal por eje, población y marginación | Análisis |
| `v_concentracion` | Por periodo: % de la oferta en el top 5, **HHI** y municipios con oferta | Cifra del problema |
| `v_crecimiento_censal` | Personal 2019 vs 2024 por municipio y eje | Validación hacia atrás |
| `v_panel_crecimiento` | Panel municipio × eje × transición con `delta_log` | Modelado |
| `v_pares_rutas_existentes` | Pares (a < b) consecutivos en rutas oficiales: **84 tramos** | Novedad, enlaces |
| `v_novedad_ruta` | Para cada ruta: % de tramos y de municipios ya existentes y clasificación `nueva` / `parcialmente_existente` / `existente` | Rutas propuestas |
| `v_ficha_municipio` | Una fila por municipio: identidad + semáforos{} + actividades[] + infraestructura{} + tira de 12 meses + eventos[] + rutas[] + banderas[] + atractivos[] | Página *Ficha técnica* (una sola consulta) |
| `v_ruta_parada` | Una fila por parada de cada ruta con evaluación, novedad y coordenadas | Página *Rutas* |
| `v_indice_municipio` | Mejor eje e índice de la versión más reciente por municipio, con ranking estatal | Página *Rutas* (fondo del mapa) |

### 6.6 Seguridad en la base

- Las tablas de `sql/05` y `sql/08` tienen RLS activado con política `lectura_publica` (`SELECT USING (true)`),
  `GRANT SELECT` a `anon` y `authenticated` y `GRANT ALL` a `service_role`.
- Las vistas de `sql/06` y `sql/07` se exponen con `GRANT SELECT` a los mismos roles.
- `DDL/04_permisos_mopedetu.sql` da a `dev_raul` y `dev_styveen` lectura y escritura en `stg` y `dw`.
- Después de cambios de estructura se ejecuta `NOTIFY pgrst, 'reload schema'` para que PostgREST los vea.

---

## 7. Pipeline de carga y cálculo (ETL)

### 7.1 Orden de ejecución

```bash
# 0. Estructura (una vez, en el SQL Editor de Supabase o con scripts/ejecutar_sql.py)
DDL/01_ddl_mopedetu.sql → DDL/03_ddl_prediccion_mopedetu.sql → sql/05 → sql/08 → sql/06 → sql/07
python scripts/crear_roles.py && DDL/04_permisos_mopedetu.sql

# 1. Identidad (A0)
python scripts/cargar_municipios.py [Puebla.json]          # 217 municipios con geometría
python scripts/cargar_rutas_existentes.py                  # rutas oficiales, Pueblos Mágicos, anclas, regiones

# 2. Datos base (A1, A4 y accesibilidad)
python scripts/descargar_osm.py data/raw/osm
python scripts/cargar_datos_base.py --denue ... --ce2019 ... --ce2024 ... --catalogo ... \
       --iter ... --conapo ... --coneval ... --geo ... --osm data/raw/osm

# 3. Lugares, actividades, infraestructura, temporadas y semáforos (A1-A3)
python scripts/cargar_atractivos.py --osm data/raw/osm --geo ...
python scripts/calcular_actividades.py data/raw/denue_inegi_21_.csv
python scripts/calcular_ficha.py --denue ... --osm ... --iter ... --geo ...

# 4. Modelo (A5-A6)
python model/indice.py
python model/crecimiento.py
python model/enlaces.py
python model/rutas.py
python model/escenario_hhi.py
python scripts/calcular_ficha.py ...     # otra vez: el semáforo "potencial" necesita la predicción

# 5. Modelo alterno del rol B (independiente, en archivos locales)
python scripts/censo_economico.py && python scripts/contexto_social.py && python model/prediccion_crecimiento.py
```

Todo es **idempotente**: cada script borra lo suyo (por versión, periodo, modelo u origen) y lo vuelve a insertar.

### 7.2 Qué hace cada script de carga

| Script | Lee | Escribe | Detalle |
|---|---|---|---|
| `cargar_municipios.py` | GeoJSON INEGI 2023 (PhantomInsights) | `stg.mun_geo`, `dim_municipio` | Envía geometrías como EWKT SRID 4326; convierte Polygon → MultiPolygon; sincroniza por `cve_geo` sin tocar región/PM/ancla |
| `cargar_rutas_existentes.py` | `data/catalogos/rutas_existentes.csv`, `municipios_turismo.csv`, GeoJSON | `dim_fuente` (filas 7-11), `dim_ruta`, `fact_ruta_parada`, columnas de `dim_municipio`; genera `sql/04_...sql` | Normaliza nombres sin acentos para cruzar con `cve_geo`; aplica el criterio de ancla; calcula distancia en línea recta entre paradas; verifica que las 7 regiones cubran los 217 municipios |
| `cargar_datos_base.py` | DENUE, CE 2019/2024, catálogo SCIAN, ITER, CONAPO, CONEVAL, GeoJSON, OSM | `dim_scian`, `bridge_scian_eje`, `stg.denue`, `stg.totales_municipio`, `dim_establecimiento`, `fact_oferta_municipio_eje`, `stg.censo_economico`, `fact_censo_economico`, `fact_contexto_social`, `fact_accesibilidad`, `fact_atractivo`, `dim_fuente` | Ejecutable por secciones (`--solo scian,denue,...`). Calcula cociente de localización, matriz de 46,872 pares y colindancia con margen de ~100 m |
| `cargar_atractivos.py` | OSM (`atractivos.json`, `puntos.json`), `atractivos.csv`, GeoJSON | `fact_atractivo_lugar`, `data/derivados/atractivos_lugares.csv` | Clasifica lugares en santuario, cascada, gruta, mirador, volcán, museo, zona arqueológica…; asigna municipio por polígono; el curado gana en duplicados |
| `calcular_actividades.py` | DENUE completo, rutas oficiales, INAH, `atractivos_lugares.csv` | `dim_actividad`, `fact_actividad_municipio`, `data/derivados/actividad_municipio.csv` | Detecta 14 actividades por SCIAN, palabra clave y catálogo; calcula CL, nivel, puntaje y top 3; imprime la validación V3 |
| `calcular_ficha.py` | DENUE, OSM, ITER, GeoJSON, tablas de Supabase | `fact_infraestructura`, `fact_temporada`, `fact_semaforo_municipio`, `dim_fuente`, `dim_version_calculo` | 21 indicadores, índice de infraestructura, intensidad turística, 5 semáforos; imprime la validación V2 |
| `descargar_osm.py` | Overpass API | `vias.json`, `puntos.json` | Vías motorway-tertiary, servicios y atractivos de Puebla |
| `buscar_osm_nuevos.py` | Overpass + DENUE completo | `data/processed/osm_nuevos.csv` (821), `osm_dudosos.csv`, `osm_ya_en_denue.csv` | Detecta establecimientos con nombre en OSM que no están en el DENUE (comparación por similitud de nombre y distancia); **todavía no se cargan** a la base |
| `censo_economico.py` (B) | Datos abiertos INEGI | `data/stg/censo_economico*.csv` | Versión histórica homologada a SCIAN 2023; formato largo; no rellena confidenciales |
| `contexto_social.py` (B) | CONAPO 2020 (datos.gob.mx) | `data/stg/contexto_social.csv` | Población 2020 e índice/grado de marginación |
| `DDL/02_etl_mopedetu.sql` | `stg.*` | `dw.*` | ETL SQL original del rol A por pasos 0-7; **los pasos 4 y 6 fueron reemplazados** por `cargar_datos_base.py` (otros pesos SCIAN, factor de tiempo 1.8 min/km, niveles CL ≥ 2 / 1.25 / 0.75) |

---

## 8. El modelo por anillos (A0 a A6)

Resumen narrativo; las fórmulas exactas están en [`Validations.md`](Validations.md).

### A0 · Identidad

- 217 municipios con polígono INEGI, región (7 regiones de 2015) y marcas turísticas.
- **13 municipios Pueblo Mágico** (12 nombramientos; Cholula cuenta San Pedro y San Andrés).
- **12 anclas** = destinos consolidados: Puebla y Tehuacán (UNESCO + nodo urbano) más los Pueblos Mágicos con al
  menos 10 años de nombramiento (≤ 2016): Cuetzalan del Progreso, Zacatlán, Chignahuapan, Pahuatlán,
  Tlatlauquitepec, Xicotepec, San Pedro Cholula, San Andrés Cholula, Atlixco y Huauchinango.
- **29 rutas oficiales** con 134 paradas en 70 municipios distintos.

### A1 · Oferta y actividades

Dos niveles:

1. **Ejes económicos (4).** Cada clase SCIAN turística se asigna a hospedaje, alimentos, turismo y cultura o
   comercio turístico con un peso. Por municipio y eje se calculan unidades, personal estimado (punto medio del
   estrato), participación estatal, **cociente de localización (CL)**, nivel de predominancia y ranking.
2. **Actividades temáticas (14).** Lo que el visitante entiende: ☕ café, 🥃 mezcal, 🍷 bebidas tradicionales,
   🏺 artesanías, 🍲 gastronomía, 🏛️ museos, 🗿 arqueología, ⛪ religioso, 🌲 ecoturismo, 🌋 volcanes,
   ♨️ balnearios, 🌸 flores y viveros, 🤝 comunitario y 🧭 operadores. Se detectan con tres señales (código SCIAN,
   palabra clave en el nombre del negocio dentro de SCIAN permitidos, y catálogo oficial o lugar con nombre). Cada
   municipio obtiene un nivel por actividad y sus **3 actividades principales**.

Un nivel especial, `reconocida_sin_registro`, marca actividades que la Secretaría reconoce (por ejemplo, el
municipio está en la Ruta del Mezcal) pero que no tienen ningún negocio en el DENUE: es la **oferta invisible**.

### A2 · Infraestructura

21 indicadores por municipio: minutos al ancla más cercana y a la capital, municipios colindantes, km de vías
principales (OSM) y densidad por km², terminales de autobús, atractivos OSM, hospedaje y alimentos (unidades y
personal), gasolineras, bancos, farmacias, unidades de salud, población, % de viviendas con internet, servicios por
10 mil habitantes, índice de carencias e intensidad turística. Con ellos se arma un **índice de infraestructura 0-1**.

### A3 · Demanda actual y temporadas

- **Intensidad turística (proxy):** empleo turístico por mil habitantes, hospedaje, número de rutas oficiales y
  marca (ancla / Pueblo Mágico). Como no hay datos de visitantes, se declara como proxy.
- **Temporadas:** 31 registros en tres capas que se suman en una tira de 12 meses por municipio: vacaciones
  nacionales (para todos), temporadas de actividad (cosecha de café, chiles en nogada, alta montaña, palenques) y
  eventos municipales (ferias, festivales, fiestas patronales). Los **meses fuertes** son los de intensidad ≥ 2
  propia del municipio.

### A4 · Contexto social

Población 2020, índice y grado de marginación CONAPO 2020, % de pobreza CONEVAL 2020 y % de viviendas con
internet. Se usa como **necesidad social**: pesa **a favor** de proponer un municipio, nunca en contra.

### A5 · Predicción

| Pieza | Pregunta | Técnica | Salida |
|---|---|---|---|
| Crecimiento (rol C) | ¿Cuánto crecerán las unidades económicas turísticas de cada municipio y eje a 5 años? | LightGBM + intervalo conformal 80 %, validación agrupada por municipio, 2 líneas base | `fact_prediccion_crecimiento` |
| Crecimiento (rol B) | ¿Cuánto crecerá el personal ocupado turístico al siguiente censo? | HistGradientBoosting vs Ridge, validación temporal 2014→2019 / 2019→2024 + espacial por región, 3 líneas base | `data/modelo/fact_prediccion_crecimiento.csv` |
| Perfiles y clusters | ¿Qué municipios se parecen? | Perfil de 33 dimensiones, similitud coseno, k-means con k por silueta | `fact_similitud`, `fact_cluster_municipio` |
| Enlaces | ¿Qué pares de municipios formarían un tramo de ruta? | LightGBM clasificador entrenado con los tramos de las rutas oficiales, validación agrupada por ruta | `fact_prediccion_enlace` |

### A6 · Decisión

1. **Índice de oportunidad** por municipio × eje: versión `v1_base` (oferta, complementarios, accesibilidad,
   social) y versión `v2_con_prediccion` (agrega el potencial predicho).
2. **Banderas** con motivo en texto: `OFERTA_EMERGENTE`, `ACCESIBLE_NO_EXPLOTADO`, `BARRERA_ACCESO`,
   `OFERTA_INVISIBLE` e `IMPACTO_SOCIAL`.
3. **Optimizador de rutas**: para cada ancla × tema construye una ruta por inserción voraz y la mejora con 2-opt;
   evalúa restricciones (paradas, tiempos, emergentes) y elige la **mejor combinación de 5 rutas** que maximice
   primero el número de regiones beneficiadas y luego la calidad.
4. **Novedad**: cada ruta se clasifica contra las 29 oficiales.
5. **Escenario de concentración (V8)**: HHI hoy, tendencial y con rutas (hipotético).

---

## 9. Módulos de Python del modelo (`model/`)

### 9.1 `base.py`

- `cargar()` (con `lru_cache`): lee de Supabase con la *secret key* todas las tablas que necesitan los modelos y
  las devuelve en un `dataclass Base` con: `mun` (identidad + centroide del GeoJSON), `oferta` (DENUE 2026-05),
  `censo`, `social`, `infra` (pivotada a formato ancho), `actividades`, `cat_act`, `acceso`, `atractivos`,
  `temporadas`, `rutas` (solo paradas de rutas existentes), `periodos` y `fuentes`. Así **todas las piezas trabajan
  exactamente con los mismos datos**.
- `pct(s)`: percentil en [0, 1] con empates promediados; los `NaN` se vuelven 0.
- `EJES = {1: hospedaje, 2: alimentos, 3: turismo, 4: comercio_turistico}`.
- `asegurar_modelo(fila)`: crea o actualiza una fila de `dim_modelo` por nombre.
- `publicar(modelo, tabla, filas)`: registra el modelo y escribe sus filas con `modelo_sk`; si la base rechaza el
  registro, guarda todo en `data/derivados/pendientes/` (el script `publicar_pendientes.py` mencionado en el código
  **no existe** todavía).
- `asegurar_version(nombre, descripcion, pesos)`: crea o actualiza una versión de cálculo con sus pesos.
- `reemplazar(tabla, filtro, filas)`: `DELETE` por filtro + `POST` por lotes de 1,000 (idempotencia).
- `limpio(v)`: convierte tipos de NumPy a JSON y `NaN/inf` a `None`.

### 9.2 `actividades.py`

Catálogo `ACTIVIDADES` (clave, nombre, icono, eje, descripción), reglas `REGLAS` por actividad (códigos SCIAN,
expresión regular sobre el nombre sin acentos, SCIAN donde se permite buscar la palabra clave y temas de catálogo),
zonas arqueológicas INAH, puntos medios del estrato y la función `nivel_predominancia(cl, unidades, catalogo)`.

### 9.3 `indice.py`

`componentes()` calcula por municipio × eje los cuatro scores (oferta, complementarios, accesibilidad, social);
`indice()` los pondera con los pesos de `dim_version_calculo` (y opcionalmente el potencial); `banderas()` evalúa
las cinco reglas con su motivo. `main()` escribe la versión `v1_base`, imprime el top 10 de oportunidades fuera de
anclas y la comparación del índice medio de anclas contra el resto.

### 9.4 `crecimiento.py`

Arma el panel municipio × eje con CE 2019 y CE 2024, construye 23 variables medidas en el año base, valida con
GroupKFold por municipio contra dos líneas base, ajusta el modelo final, calcula SHAP, predice 2024 → 2029,
publica `fact_prediccion_crecimiento` y registra modelo y líneas base en `dim_modelo`. Después recalcula el
**índice v2** y sus banderas. Guarda `data/derivados/prediccion_crecimiento.csv` y `metricas_crecimiento.json`.

### 9.5 `enlaces.py`

Construye perfiles por municipio, la matriz de similitud coseno, los clusters (k-means) y el modelo de enlaces.
Escribe `fact_cluster_municipio`, `fact_similitud`, `fact_prediccion_enlace` y `data/derivados/enlaces_pares.csv`
(cada par con su probabilidad final y su predicción fuera de muestra).

### 9.6 `rutas.py`

Lee el índice v2, las banderas v2, la predicción, la probabilidad de enlace y los tiempos. Construye una ruta por
cada combinación ancla × tema (12 × 12 = 144), las evalúa, guarda el diagnóstico completo en
`data/derivados/rutas_candidatas.csv`, selecciona 5 con búsqueda exhaustiva con poda, borra las propuestas
anteriores y escribe `dim_ruta`, `fact_ruta_parada` y `fact_ruta_evaluacion`. Al final lee `v_novedad_ruta` e
imprime cada ruta con su novedad; guarda `data/derivados/rutas_propuestas.csv`.

### 9.7 `escenario_hhi.py`

Calcula HHI y % del top 5 del personal turístico en tres escenarios (hoy, tendencial a 5 años y con rutas) y lo
guarda en `data/derivados/escenario_concentracion.json`, que lee la página de Rutas.

### 9.8 `prediccion_crecimiento.py` (rol B)

Modelo independiente que trabaja con archivos locales (`data/stg/`), no con Supabase. Panel de dos transiciones,
validación temporal real, validación espacial por región, intervalos empíricos por eje y reglas de corte que
**dejan sin predicción** las celdas con personal confidencial. Salidas en `data/modelo/`. Usa `ANCLAS`,
`haversine_km` y `region_aprox` de `dashboard/datos.py`, es decir, las anclas y regiones aproximadas del modo DEMO
(9 anclas y región por coordenadas), no las oficiales.

---

## 10. El tablero (`dashboard/`)

### 10.1 Stack y arranque

- **Streamlit ≥ 1.50** (páginas, filtros y estado), **Plotly** (mapas coropléticos y gráficas), **MapLibre GL
  4.7.1** dentro de un componente HTML (navegación satelital), **pydeck** listado en dependencias pero ya no se usa
  en los mapas (se reemplazó por Plotly porque su detección de clic quedaba desfasada en Windows con escalado).
- **Arranque:** `MOPEDETU.bat` (Windows), `sh mopedetu.sh` (macOS/Linux) o `python iniciar.py`. El lanzador:
  1. Exige Python ≥ 3.10.
  2. Si ya están `streamlit, pydeck, plotly, pandas, numpy` usa el Python actual; si no, crea `.venv` e instala
     `requirements.txt` (solo cuando cambia el *hash* SHA-256 del archivo, guardado en `.venv/.req_hash`).
  3. Busca un puerto libre desde el 8501 y lanza `streamlit run dashboard/app.py`.

### 10.2 `app.py`

Configura la página (`layout="wide"`), aplica el tema y define la navegación en tres grupos:

| Grupo | Páginas |
|---|---|
| **Explorar** | 🏠 Panorama · 🏘️ Ficha técnica (datos reales) · 🗺️ Mapa de oportunidades |
| **Predecir** | 🧭 Rutas · 🔁 Circuitos · 🔮 Simulador |
| **Detalle** | 🏘️ Ficha municipal · 🚩 Alertas |

### 10.3 `estado.py` · barra lateral y cachés

- `datos()`: genera los datos DEMO una vez (`st.cache_resource`).
- `barra_lateral()` construye el **Contexto** global:

| Control | Modo General | Modo Concreto |
|---|---|---|
| Modo | General | Concreto |
| ¿Qué predecir? | Rutas y Circuitos | Rutas, Circuitos o ambos |
| Actividades | Todas | Una, Varias (por defecto café, ecoturismo, mezcal) o Todas |
| Escenario | Tendencial | Tendencial, Con inversión reciente 2024-25, Con inversión simulada, Con promoción y rutas, Combinado |
| Región | Todo el estado | Una de las 7 o todas |
| Inversión (si aplica) | — | Monto 50-3,000 MDP y destino (municipios con flag, región, destinos consolidados, todos) |
| Promoción (si aplica) | — | +0 a 100 % de visibilidad |
| Horizonte | 1, 3 o 5 años (por defecto 3) | 1, 3 o 5 años |
| Enfoque del índice | Balanceado | Balanceado, Económico, Social, Descentralización |
| Duración máxima de ruta | 2 días | 1 a 4 días |
| Mínimo de emergentes por ruta | 2 | 1 a 4 |

- `prediccion(supuestos)` y `rutas(contexto)` se cachean con `st.cache_data` (64 entradas) usando como llave una
  tupla de todos los supuestos, así que mover un control repetido no recalcula.
- `chips()` produce las etiquetas que aparecen en el encabezado de cada página.

### 10.4 `supabase_cliente.py`

Cliente PostgREST sin dependencias (`urllib`): lee `.env`, arma cabeceras `apikey`, `Accept-Profile` /
`Content-Profile` (para elegir esquema `dw` o `stg`), pagina de 1,000 en 1,000 (`Range`), hace upsert por lotes de
500 y expone `probar()` para diagnosticar la conexión. El tablero usa la *publishable key*; la *secret key* solo la
usan los scripts.

### 10.5 `ficha_bd.py`

Lee de Supabase, con caché de 10 minutos, `v_ficha_municipio`, `v_ruta_parada` y `v_indice_municipio`. Define las
5 dimensiones del semáforo, sus colores (verde, amarillo, rojo, gris) y el texto de lectura de cada color. Si no
hay `.env` o la vista no responde, devuelve `None` y la página muestra un error claro.

### 10.6 `tema.py` · identidad visual Talavera

Azul cobalto `#1B3F8B`, azul oscuro `#0E2A5C`, amarillo `#E8B10D`, guinda `#8A1538`, verde `#2E7D32`. Escala
secuencial amarillo → turquesa → cobalto para el índice y amarillo → naranja → guinda para el crecimiento; un color
por región. Inyecta CSS para el encabezado (*hero*) con rombo decorativo, tarjetas, métricas con borde cobalto y
etiquetas `ANCLA` (cobalto), `EMERGENTE` / flags (guinda) y la advertencia DEMO.

---

## 11. Página por página

### 11.1 🏠 Panorama (motor DEMO)

- **KPIs:** municipios analizados y cuántos tienen oferta; municipios con flag `OFERTA_INVISIBLE`; rutas propuestas
  por el motor y municipios emergentes que tocan; **HHI** del empleo turístico hoy y su cambio "con rutas"; empleo
  turístico proyectado al horizonte.
- **Mapa** del índice de oportunidad (cuantiles, fondo satelital) con anclas, los 5 emergentes con mayor índice en
  guinda y los tramos de las rutas del motor en amarillo (grosor según puntaje).
- **Top 10 emergentes** (no anclas) en barras con el icono de su actividad líder.
- **Curva de Lorenz** hoy contra con rutas, con su **Gini**.
- **Treemap** región → actividad (tamaño = personal, color = índice medio).
- **Barras por región**: empleo hoy, proyectado y con rutas (escala logarítmica).

### 11.2 🏘️ Ficha técnica (datos reales de Supabase)

- Mapa coroplético de los 217 municipios coloreado por la dimensión elegida: 🧳 Turismo actual, 🛣️ Infraestructura,
  🎯 Oferta, 📈 Potencial o 🤝 Necesidad social. Nombres de las anclas siempre visibles; interruptor para todos.
- **Hover** con nombre, marcas ✨⚓, región, 3 actividades principales, los 5 semáforos con su lectura y los meses
  fuertes.
- **Clic** (o buscador) abre el panel lateral:
  - Tarjeta con los 5 semáforos y el **motivo** de cada uno.
  - Pestaña 🎯 *Actividades*: principales con nivel, número de establecimientos, CL y ejemplos de negocios; otras
    actividades; advertencia de **oferta reconocida sin registro DENUE**; hasta 12 **lugares para visitar** (✅ los
    curados con fuente, el resto de OSM).
  - Pestaña 🛣️ *Infraestructura*: ancla más cercana y minutos, minutos a la capital, hospedajes, restaurantes,
    densidad vial, internet, gasolineras, bancos, farmacias, salud, terminales, atractivos y vecinos.
  - Pestaña 📅 *Temporadas*: tira de 12 meses (altura = intensidad, contorno amarillo = mes fuerte propio) y lista de
    eventos con fuente.
  - Pestaña 🧭 *Rutas y banderas*: rutas oficiales que lo incluyen, rutas propuestas por el modelo y banderas con
    motivo. Si no aparece en ninguna ruta oficial lo dice: "candidato a rutas nuevas".
- Municipio inicial: Cuetzalan del Progreso.

### 11.3 🗺️ Mapa de oportunidades (motor DEMO)

- Selector de indicador: índice de oportunidad, crecimiento proyectado, personal ocupado, visibilidad (menciones),
  inversión reciente, marginación, % de vías pavimentadas, número de flags o **CL de una actividad**.
- Resaltado con contorno guinda de los municipios con un flag elegido; burbujas opcionales de empleo.
- Clic en un municipio: detalle con índice, crecimiento y actividades con CL, nivel y flags; botón para abrir la
  *Ficha municipal*. Sin selección: ranking del indicador.
- Gráfica **oferta contra visibilidad** con el cuadrante 🚩 *OFERTA INVISIBLE* (visibilidad ≤ 0.35 y oferta ≥ 0.6).

### 11.4 🧭 Rutas

Tiene dos modos:

**🧠 Rutas del modelo (datos reales):**
- KPIs: rutas propuestas y cuántas son totalmente nuevas; municipios emergentes; % de tramos nuevos; crecimiento
  esperado medio; **concentración top 5** con el escenario hipotético (lee `escenario_concentracion.json`).
- Mapa con el índice de oportunidad de fondo, las rutas propuestas con su color y paradas numeradas (ancla en azul
  oscuro); opcionalmente las rutas oficiales en gris.
- Lista de rutas: novedad (Nueva / Parcialmente existente / Ya existe), % de tramos oficiales, región, duración,
  emergentes, crecimiento, paradas con etiqueta ANCLA/EMERGENTE, minutos y estancia, y la **descripción** generada
  por el optimizador (banderas traducidas a lenguaje legible).
- Tabla comparativa descargable en CSV y catálogo de las 29 rutas oficiales.
- **🛰️ Recorrer una ruta propuesta:** traza la ruta por carretera real (OSRM), arma la agenda por días (jornadas de
  9:00 a 19:00 con la estancia sugerida), muestra km y horas reales, indicaciones paso a paso y enlaces a Google
  Maps y Waze.

**🛠️ Arma tu ruta (motor DEMO):** el usuario elige el municipio de salida y deja que el motor proponga las paradas
(con días y máximo de paradas) o las elige él (hasta 9, el orden se optimiza con 2-opt). Se traza por carretera real
con agenda, itinerario, indicaciones y enlaces.

### 11.5 🔁 Circuitos (motor DEMO)

- Recorridos de medio día o un día **dentro de un municipio**, variados o de una sola actividad, en auto (25 km/h)
  o a pie (4.5 km/h), de 3 a 10 horas.
- Las paradas son puntos de interés simulados (en producción serían establecimientos geolocalizados del DENUE).
- Mapa de navegación con la ruta real por calles, horario de llegada a cada parada (1 hora por parada desde las
  9:00), advertencia si los traslados reales exceden la duración elegida, itinerario, indicaciones y enlaces.
- Ranking de municipios con mejor **potencial de circuito** con los filtros actuales.

### 11.6 🔮 Simulador (motor DEMO)

- Controles: inversión 0-3,000 MDP, destino de la inversión, región objetivo, promoción (+% de visibilidad) y
  horizonte.
- Compara el escenario **tendencial** contra el **combinado** con esos supuestos.
- KPIs: empleos turísticos adicionales, municipios beneficiados (+1 % o más), empleos por cada 10 MDP, HHI simulado
  contra tendencial y % del beneficio fuera de las anclas.
- Mapa del cambio porcentual, trayectoria estatal año por año y top 10 municipios que más ganan.
- Aviso: escenario **estimado** con correlaciones, no demuestra causalidad.

### 11.7 🏘️ Ficha municipal (motor DEMO)

Versión DEMO de la ficha: KPIs (índice y ranking, personal, proyección, minutos al ancla, inversión), barras de CL
por actividad, gráfica de cascada **"¿Por qué?"** con la contribución de cada factor al índice según el enfoque,
flags por actividad, rutas del motor que lo incluyen, proyección del empleo con banda de incertidumbre y mapa de
ubicación con vecinos. Descarga en CSV.

### 11.8 🚩 Alertas (motor DEMO)

Conteo de cada flag DEMO, tabla filtrable por flag, actividad e índice mínimo (descargable en CSV) y mapa de calor
de flags por región.

---

## 12. Mapas y navegación satelital

### 12.1 `mapas.py` (Plotly)

- Clase `Mapa` con métodos encadenables: `municipios()` (coroplético con cuantiles o escala lineal, municipios
  atenuados en gris, contorno guinda para resaltar y azul para el seleccionado), `nombres()`, `puntos()`,
  `trayecto()`, `encuadre()` y `figura()`.
- Con `fondo="satelital"` (Esri World Imagery, ~19 KB por mosaico, el predeterminado) o `"relieve"`
  (OpenTopoMap) usa `Choroplethmap` sobre mosaicos con opacidad 0.72; sin fondo dibuja SVG.
- `mostrar(mapa, clave, estado_sel)`: si se pasa `estado_sel`, un clic en un municipio guarda su `cve_geo` en
  `st.session_state` y redibuja. La llave del gráfico incluye la selección para evitar que Plotly alterne entre
  seleccionar y deseleccionar.
- Alias de etiquetas para anclas que se enciman (`21140` se rotula "Cholula" y `21119` no se rotula).

### 12.2 `navegacion.py` (MapLibre + OSRM)

- `ruta(puntos, perfil)`: pide la ruta a **OSRM** sobre OpenStreetMap (`routing.openstreetmap.de` para auto y a
  pie; `router.project-osrm.org` de respaldo para auto), con `overview=full`, geometría GeoJSON y pasos. Devuelve
  coordenadas, km y minutos totales y por tramo, indicaciones en español (giros, glorietas, bifurcaciones) con su
  posición relativa y los puntos de enganche a la calle. Caché de 24 horas; *timeout* de 8 s.
- `ruta_recta(puntos, minutos)`: respaldo sin conexión con tramos rectos y los tiempos estimados por el motor.
- `mapa(...)`: inyecta los datos en una plantilla HTML con MapLibre GL: satélite de Esri con capas de referencia de
  vías y lugares (vista híbrida), mapa de calles de Esri, **relieve 3D** con Terrain Tiles de AWS, contornos de los
  municipios, botón **▶ Recorrer** que anima el trayecto como un navegador, inclinación y giro con clic derecho, y
  fichas emergentes por parada.
- `enlace_google()` (hasta 9 paradas intermedias) y `enlace_waze()`.

---

## 13. Datos DEMO y motor ligero del tablero

### 13.1 `datos.py` · generador DEMO

Con semilla fija (2026), sobre la geometría real de los 217 municipios:

- **Región aproximada por coordenadas** (`region_aprox`), no la oficial.
- 11 Pueblos Mágicos y **9 anclas DEMO** (Puebla, San Pedro Cholula, San Andrés Cholula, Atlixco, Cuetzalan,
  Zacatlán, Chignahuapan, Tehuacán, Xicotepec): distinto de las 12 anclas oficiales de la base.
- Población real de 16 municipios grandes; el resto, lognormal.
- Marginación por región ajustada por tamaño urbano; % de vía pavimentada menor en la sierra.
- **Matriz de tiempos** = distancia haversine × 1.35 (rodeo) a 42 km/h en sierra o 58 km/h fuera.
- 14 actividades DEMO (café, mezcal, arqueología, conventos, sidra, ecoturismo, volcanes, talavera, gastronomía,
  termales, desierto, flores, religioso, comunitario) con afinidad regional y municipios destacados conocidos;
  personal ocupado, unidades, CL, visibilidad (menciones, reseñas) sesgada a destinos famosos, inversión reciente
  concentrada en anclas y Pueblos Mágicos, crecimiento histórico simulado y **puntos de interés** sintéticos
  alrededor de la cabecera.

### 13.2 `motor.py` · motor analítico ligero

Cálculo vectorizado en milisegundos: índice de oportunidad con 6 componentes y 4 enfoques de pesos, crecimiento
anual sustituto (en lugar de LightGBM) que reacciona a escenarios de inversión y promoción, 6 flags DEMO, resumen
por municipio, HHI, curva de Lorenz y Gini, efecto de rutas, rutas intermunicipales (voraz + 2-opt con presupuesto
en días), ruta personalizada desde cualquier municipio, circuitos municipales (vecino más cercano) y ranking de
circuitos. Todas las fórmulas están en `Validations.md` §17.

---

## 14. Cómo ejecutar todo

### 14.1 Solo el tablero

```bash
python iniciar.py          # o doble clic en MOPEDETU.bat
```

Las páginas DEMO funcionan sin internet ni credenciales (salvo mosaicos satelitales y OSRM, que tienen respaldo).
Para *Ficha técnica* y *Rutas del modelo* hace falta `.env` con `SUPABASE_URL` y `SUPABASE_PUBLISHABLE_KEY`.

### 14.2 Configurar credenciales

```bash
cp .env.example .env       # y llenar SUPABASE_URL, SUPABASE_PUBLISHABLE_KEY, SUPABASE_SECRET_KEY
python dashboard/supabase_cliente.py   # diagnóstico: prueba ambas llaves y lista tablas
```

Los scripts de `scripts/db.py` y `scripts/ejecutar_sql.py` usan además `DATABASE_URL` (cadena del *Session
pooler*, puerto 5432, porque la conexión directa de la capa gratuita es solo IPv6).

### 14.3 Regenerar el modelo

Ver §7.1. Los modelos requieren además `lightgbm`, `scikit-learn`, `scipy`, `shapely` y `openpyxl`, que no están
todos en `requirements.txt` (este solo cubre el tablero).

### 14.4 Pruebas

```bash
python tests/test_tablero.py
```

---

## 15. Resultados actuales

### 15.1 Datos

| Indicador | Valor |
|---|---|
| Establecimientos DENUE de Puebla | 410,693 (60,446 turísticos) |
| Concentración hoy | Top 5 = **51.9 %**, HHI **1,306** |
| Municipios con al menos una actividad principal | 184-188 de 217 (según la corrida) |
| Niveles de actividad (217 × 14) | muy alta 95 · alta 98 · media 264 · baja 271 · reconocida 32 · reconocida sin registro 45 · sin oferta 2,233 |
| Rutas oficiales | 29 rutas, 134 paradas, 70 municipios, 84 tramos únicos |

### 15.2 Semáforos (`ficha_semaforos_v1`, 217 municipios)

| Dimensión | 🟢 | 🟡 | 🔴 | ⚪ |
|---|---|---|---|---|
| Turismo actual | 106 | 76 | 33 | 2 |
| Infraestructura | 61 | 106 | 50 | — |
| Oferta | 119 | 60 | 21 | 17 |
| Potencial | 108 | 108 | 1 | — |
| Necesidad social | 65 | 66 | 86 | — |

### 15.3 Modelos

| Modelo | Métrica principal | Líneas base |
|---|---|---|
| Crecimiento de unidades (LightGBM, rol C) | MAE **0.246**, Spearman **+0.476**, precisión top 20 % **54 %**, cobertura del intervalo 80 % = **79.9 %**, n = 482 | Media del eje: 0.273 / +0.333 / 34 % · Ridge: 0.283 / +0.329 / 45 % |
| Crecimiento de personal (gradient boosting, rol B) | Temporal: Spearman **0.268**, precisión top 20 = **0.25**, MAE 0.327 (n = 208); espacial: Spearman 0.378 | Persistencia −0.171 · mediana del eje 0.241 · CL −0.304 · Ridge 0.254 |
| Enlaces (LightGBM) | AUC **0.881**, precisión media **0.096** | Solo distancia 0.856 / 0.042 · Solo similitud 0.699 / 0.019 |
| Clusters | k = 5 por silueta | — |

### 15.4 Índice y banderas

- Versión v2: **385 banderas activas en 131 municipios**.
- Mejores oportunidades fuera de anclas: **Jonotla (#1, 0.86)**, Huehuetla, Jalpan, Zacapoaxtla, Zapotitlán de
  Méndez, Huehuetlán el Grande, Pantepec…

### 15.5 Rutas propuestas (última corrida, `data/derivados/rutas_propuestas.csv`)

| # | Ruta | Recorrido | Minutos | Novedad |
|---|---|---|---|---|
| 1 | ☕ Café · Cuetzalan → Zacapoaxtla | Cuetzalan del Progreso → Jonotla → Zoquiapan → Zapotitlán de Méndez → Xochitlán de Vicente Suárez → Zacapoaxtla | 77 | nueva |
| 2 | 🌋 Volcanes · San Pedro Cholula → Atzitzihuacán | San Pedro Cholula → San Jerónimo Tecuanipan → Nealtican → Calpan → Tochimilco → Atzitzihuacán | 99 | nueva |
| 3 | 🍲 Gastronomía · Cuetzalan → Zihuateutla | Cuetzalan del Progreso → Jonotla → Huehuetla → Olintla → Jopala → Zihuateutla | 86 | nueva |
| 4 | 🌲 Ecoturismo · San Andrés Cholula → Huaquechula | San Andrés Cholula → Nealtican → Calpan → San Nicolás de los Ranchos → Atzitzihuacán → Huaquechula | 132 | parcialmente existente |
| 5 | 🥃 Mezcal · San Andrés Cholula → Ixcaquixtla | San Andrés Cholula → Huehuetlán el Grande → Tzicatlacoyan → Tecali de Herrera → Molcaxac → Ixcaquixtla | 189 | parcialmente existente |

De 144 combinaciones ancla × tema, **56 fueron factibles**. Los 20 municipios emergentes de las rutas alimentan el
escenario de concentración:

| Escenario | HHI | Top 5 |
|---|---|---|
| Hoy | 1,306 | 51.9 % |
| Tendencial a 5 años | 1,132 | 49.1 % |
| Con rutas (hipotético) | 1,103 | 48.5 % |

> La tabla de rutas de `docs/resultados_modelo.md` corresponde a una corrida anterior (Xicotepec → Naupan,
> Chignahuapan → Tuzamapan, etc.). La vigente es la de arriba, posterior a la incorporación de El Peñón de Jonotla.

---

## 16. Archivos de datos versionados

| Archivo | Contenido |
|---|---|
| `data/geo/puebla_municipios.geojson` | 217 polígonos simplificados con `cve_geo`, `nombre`, `lat`, `lon`, `area_km2` |
| `data/catalogos/rutas_existentes.csv` | `ruta_id, ruta, circuito, tema, tipo, es_monotematica, orden, municipio, localidad_mencionada, fuente, fuente_url, pagina` |
| `data/catalogos/municipios_turismo.csv` | `cve_geo, nombre, region, es_pueblo_magico, anio_pueblo_magico, es_ancla, criterio_ancla, lon, lat` |
| `data/catalogos/temporadas.csv` | `municipio, actividad, nombre, tipo, mes_inicio, mes_fin, intensidad, url, notas` |
| `data/catalogos/atractivos.csv` | `municipio, nombre, categoria, actividades, descripcion, fuente_url` |
| `data/derivados/actividad_municipio.csv` | 217 × 14 con unidades, personal, CL, nivel, señales, puntaje, rango, principal y ejemplos |
| `data/derivados/totales_municipio.csv` | Totales DENUE, hospedaje y alimentos por municipio |
| `data/derivados/infraestructura_municipio.csv` | 21 indicadores por municipio |
| `data/derivados/semaforos_municipio.csv` | 1,085 semáforos con valor, percentil y motivo |
| `data/derivados/atractivos_lugares.csv` | 580 lugares con nombre |
| `data/derivados/prediccion_crecimiento.csv` | 868 predicciones (rol C) |
| `data/derivados/metricas_crecimiento.json` | Métricas del modelo de crecimiento |
| `data/derivados/enlaces_pares.csv` | 8,452 pares con variables, etiqueta, probabilidad y predicción fuera de muestra |
| `data/derivados/rutas_candidatas.csv` | 144 combinaciones ancla × tema con factibilidad y puntaje |
| `data/derivados/rutas_propuestas.csv` | Las 5 rutas elegidas |
| `data/derivados/escenario_concentracion.json` | HHI hoy, tendencial e hipotético |
| `data/stg/*.csv` | Entradas del rol B |
| `data/modelo/*.csv` | Panel, métricas, registro de modelos y 270 predicciones del rol B |
| `data/processed/osm_*.csv` | Comparación OSM contra DENUE |

---

## 17. Seguridad y credenciales

- `.env` está en `.gitignore`; solo se versiona `.env.example`.
- El tablero usa la **publishable key** (lectura con RLS). La **secret key** solo la usan los scripts de carga y los
  modelos.
- `scripts/crear_roles.py` genera contraseñas largas para `dev_raul` y `dev_styveen` y las escribe en
  `.credenciales_roles.txt` (ignorado por Git); si un rol ya existe no cambia su contraseña.
- Regla del equipo: no usar el usuario administrador en scripts, no editar tablas a mano desde el panel (todo
  cambio va en un script repetible) y no compartir credenciales en el chat de grupo.

---

## 18. Pruebas

`tests/test_tablero.py` (Streamlit `AppTest`):

- `test_paginas()`: ejecuta las 7 páginas DEMO (panorama, oportunidades, rutas, circuitos, simulador, ficha,
  alertas) en 4 configuraciones (General; Concreto combinado con varias actividades; inversión simulada con una
  actividad en la Mixteca; promoción con todas las actividades y 1 día) y exige que no haya excepciones.
- `test_ficha_tecnica()`: si hay conexión a Supabase, abre la ficha técnica real de Cuetzalan del Progreso (21043,
  ancla), Caltepec (21027), San Diego la Mesa Tochimiltzingo (21121), Puebla (21114), Tepeyahualco (21170, Cantona)
  y un municipio sin actividades principales, cada uno con una dimensión distinta del semáforo. Sin `.env` se omite.

Es una **prueba de humo** (que nada truene), no de valores.

---

## 19. Limitaciones, pendientes y discrepancias conocidas

### 19.1 Limitaciones de método

- Datos de **oferta**, no de visitantes ni derrama.
- Un solo periodo censal para el modelo del rol C (2019 → 2024, con la pandemia dentro).
- Tiempos de traslado = distancia en línea recta × 1.8 min/km: **subestiman la sierra** (una ruta del café de
  2.3 h estimadas resultó de 5.8 h por carretera). Mejora pendiente: recalcular `fact_accesibilidad` con OSRM.
- Productores fuera del DENUE (economía informal): se reconocen como `reconocida_sin_registro` y bandera
  `OFERTA_INVISIBLE`, pero no se cuantifican.
- El modelo de enlaces aprende cómo arma rutas la Secretaría (sesgo hacia anclas).
- Cobertura de OSM desigual en municipios rurales (por eso se usa en percentiles).
- Pueblos Mágicos verificados con prensa; falta el decreto oficial.

### 19.2 Pendientes

- Conectar el tablero DEMO a Supabase (`datos.py` con `FUENTE = "supabase"`).
- V6 (sensibilidad del índice) y V9 (proxy contra DATATUR): sin hacer.
- Validación temporal del modelo de unidades (incorporar CE 2014).
- Cargar a la base los 821 establecimientos de `osm_nuevos.csv` (`scripts/cargar_osm.py` no existe).
- `model/publicar_pendientes.py` referido en `base.py` no existe.
- Mapa HTML exportado sin internet (respaldo de la demo).
- Reincorporar el tema "comunitario" con un catálogo confiable de cooperativas turísticas.

### 19.3 Discrepancias entre documentos y código (manda el código)

| Tema | Documento | Código vigente |
|---|---|---|
| Numeración de anillos | `arquitectura_modelo_y_tablero.md` (A3 predicción, A5 rutas) | A5 predicción, A6 decisión |
| Bono social del valor de un municipio en ruta | Docstring de `rutas.py`: 0.20 | `valor()` usa **0.40** |
| Selección de rutas | Comentario "selección voraz por puntaje ajustado" | Búsqueda **exhaustiva con poda** (`seleccionar()`) |
| Temporada compartida en rutas | `modelo_predictivo_anillos.md`: restricción | **Bono** de +10 % al puntaje, no restricción |
| Pesos de intensidad turística | Doc: 40/25/15/10/10 con visibilidad | `calcular_ficha.py`: 40/25/15/**20** (marca), sin visibilidad |
| Umbrales de flags | `tareas_A_galo.md`: CL ≥ 1.5, > 120 min | `indice.py`: CL ≥ 1.25, > 75 min |
| Niveles de predominancia del eje | `02_etl` paso 4: CL ≥ 1.5 / 1.0 y "No concluyente" | `cargar_datos_base.py`: 2 / 1.25 / 0.75 (y `muy_alta → Alta`) |
| Tiempo estimado | `02_etl` paso 6: × 1.35 / 45 km/h | × **1.8 min/km** |
| Rutas propuestas | Tabla de `resultados_modelo.md` | `rutas_propuestas.csv` (§15.5) |
| Anclas | Modo DEMO y modelo del rol B: 9 | Base de datos y modelo del rol C: **12** |
| Temporadas | "30 temporadas" | 31 filas en `temporadas.csv` |

---

## 20. Glosario

| Término | Significado |
|---|---|
| **Ancla** | Destino consolidado reconocido en un catálogo oficial; punto de salida de las rutas |
| **Emergente** | Municipio de una ruta que no es ancla y tiene al menos una bandera activa |
| **Eje** | Agrupación económica de la oferta: hospedaje, alimentos, turismo y cultura, comercio turístico |
| **Actividad** | Tema turístico entendible por el visitante (café, mezcal, volcanes…) |
| **CL (cociente de localización)** | Qué tan especializado está un municipio en algo respecto al estado; > 1 = más que el promedio |
| **Personal estimado** | Suma del punto medio del estrato de personal de cada establecimiento DENUE |
| **Unidades económicas (UE)** | Establecimientos |
| **HHI** | Índice Herfindahl-Hirschman: suma de participaciones al cuadrado × 10,000; mayor = más concentrado |
| **Gini / Lorenz** | Medidas de desigualdad de la distribución del empleo turístico |
| **Bandera / flag** | Regla que señala una oportunidad o barrera con su motivo en texto |
| **Semáforo** | Lectura en color (verde, amarillo, rojo, gris) de una dimensión de la ficha; dice qué hacer, no si es bueno o malo |
| **Novedad** | Clasificación de una ruta contra las oficiales: nueva, parcialmente existente o existente |
| **Tramo** | Par de paradas consecutivas de una ruta |
| **Línea base** | Modelo simple contra el que se compara el modelo de IA; si no se le gana, se usa la línea base |
| **Fuga de información** | Usar datos del futuro para predecir el pasado; el diseño la evita midiendo las variables al inicio |
| **SHAP** | Contribución de cada variable a cada predicción (explicabilidad) |
| **Intervalo conformal** | Banda de predicción construida con los errores fuera de muestra; garantiza la cobertura nominal |
| **RLS** | Row Level Security de Postgres: quién puede leer o escribir cada fila |
| **PostgREST** | API REST automática de Supabase sobre las tablas |
| **OSRM** | Motor de rutas sobre OpenStreetMap usado para el trazo por carretera real |
| **SCIAN** | Sistema de Clasificación Industrial de América del Norte (códigos de actividad económica de INEGI) |
| **DENUE** | Directorio Estadístico Nacional de Unidades Económicas (INEGI) |
