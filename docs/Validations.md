# MOPEDETU · Validaciones, criterios y lógica de predicción

> Este documento explica **con todo detalle técnico** cómo MOPEDETU calcula, predice y valida: los índices, las
> banderas, los semáforos, los dos modelos de crecimiento, los perfiles y clusters, el modelo de enlaces, el
> optimizador que crea las rutas nuevas, la clasificación de novedad, el escenario de concentración, el motor del
> tablero que arma rutas y circuitos en vivo, y todas las validaciones con su criterio de aceptación y su resultado.
>
> Todo lo que aparece aquí está tomado **del código vigente** (rama `main`, commit `f6c633d`). Cuando un documento
> de diseño dice otra cosa, se indica la diferencia. El contexto general del proyecto está en
> [`Context.md`](Context.md).

---

## Índice

0. [Principios de validación](#0-principios-de-validación)
1. [Convenciones matemáticas](#1-convenciones-matemáticas)
2. [A0 · Identidad: Pueblo Mágico, ancla y región](#2-a0--identidad-pueblo-mágico-ancla-y-región)
3. [A1 · Oferta por eje turístico](#3-a1--oferta-por-eje-turístico)
4. [A1 · Actividades temáticas](#4-a1--actividades-temáticas)
5. [A1 · Lugares con nombre (atractivos)](#5-a1--lugares-con-nombre-atractivos)
6. [A2 · Accesibilidad e infraestructura](#6-a2--accesibilidad-e-infraestructura)
7. [A3 · Intensidad turística y temporadas](#7-a3--intensidad-turística-y-temporadas)
8. [A4 · Contexto social](#8-a4--contexto-social)
9. [Semáforos de la ficha técnica](#9-semáforos-de-la-ficha-técnica)
10. [Índice de oportunidad (v1 y v2)](#10-índice-de-oportunidad-v1-y-v2)
11. [Banderas de oportunidad](#11-banderas-de-oportunidad)
12. [Modelo de crecimiento de unidades económicas (rol C, en producción)](#12-modelo-de-crecimiento-de-unidades-económicas-rol-c-en-producción)
13. [Modelo de crecimiento del personal ocupado (rol B)](#13-modelo-de-crecimiento-del-personal-ocupado-rol-b)
14. [Perfiles, similitud y clusters](#14-perfiles-similitud-y-clusters)
15. [Modelo de enlaces entre municipios](#15-modelo-de-enlaces-entre-municipios)
16. [Optimizador de rutas nuevas](#16-optimizador-de-rutas-nuevas)
17. [Clasificación de novedad](#17-clasificación-de-novedad)
18. [Escenario de concentración (HHI)](#18-escenario-de-concentración-hhi)
19. [Motor del tablero: índice, escenarios, rutas y circuitos en vivo](#19-motor-del-tablero-índice-escenarios-rutas-y-circuitos-en-vivo)
20. [Validaciones V1 a V9 y controles de calidad de datos](#20-validaciones-v1-a-v9-y-controles-de-calidad-de-datos)
21. [Reglas de corte](#21-reglas-de-corte)
22. [Tabla maestra de parámetros](#22-tabla-maestra-de-parámetros)
23. [Riesgos metodológicos detectados en el código](#23-riesgos-metodológicos-detectados-en-el-código)
24. [Lo que no se afirma](#24-lo-que-no-se-afirma)

---

## 0. Principios de validación

1. **Línea base obligatoria.** Ningún modelo de IA se usa si no le gana a una regla simple (persistencia, media o
   mediana del eje, Ridge, solo distancia, solo similitud). Si no gana, se publica la línea base y se dice.
2. **Sin fuga de información.** Las variables se miden **al inicio** del periodo que se predice; el DENUE 2026 no se
   usa para entrenar; un Pueblo Mágico cuenta solo si ya lo era en el año base.
3. **Validación que imita el uso real.** Nunca partición aleatoria simple: se valida agrupando por municipio, por
   región, por ruta o en el tiempo, para que el modelo no "vea" el mismo municipio o la misma ruta en
   entrenamiento y prueba.
4. **Incertidumbre explícita.** Toda predicción numérica lleva intervalo y se mide su cobertura real.
5. **Explicabilidad.** Cada bandera y cada semáforo guarda un **motivo en texto**; los modelos guardan SHAP o
   importancia por permutación; cada ruta guarda en su descripción por qué existe.
6. **Versionado.** Pesos y umbrales viven en `dw.dim_version_calculo` (JSON) y cada modelo en `dw.dim_modelo` con
   sus métricas, de modo que dos corridas se pueden comparar.
7. **Idempotencia.** Recalcular borra y reescribe por versión, periodo o modelo, nunca acumula.
8. **Honestidad del dominio.** Se mide **oferta**, no visitantes; los escenarios son hipotéticos; las rutas son
   hipótesis para validar con las comunidades.

---

## 1. Convenciones matemáticas

### 1.1 Percentil

Casi todo se normaliza con percentiles estatales en [0, 1] para que fuentes con escalas distintas sean comparables
y robustas a valores extremos:

```
pct(x) = rango(x) / n         con empates promediados (rank(pct=True, method="average"))
pct(NaN) = 0                  (model/base.py y scripts/calcular_ficha.py)
```

Para invertir el sentido (menos es mejor) se toma el percentil del negativo: `pct(−minutos)`.

### 1.2 Personal ocupado estimado

El DENUE reporta personal en rangos. Se usa el **punto medio** del estrato (`dw.dim_estrato_personal`):

| Rango | 0-5 | 6-10 | 11-30 | 31-50 | 51-100 | 101-250 | 251+ |
|---|---|---|---|---|---|---|---|
| Punto medio | 2.5 | 8 | 20.5 | 40.5 | 75.5 | 175.5 | 300 (supuesto, sin tope) |

Rango desconocido → 2.5.

### 1.3 Cociente de localización (CL)

```
CL(m, x) = ( PO(x, m) / PO_total(m) ) / ( PO(x, estado) / PO_total(estado) )
```

- `PO(x, m)`: personal estimado del eje o actividad `x` en el municipio `m`.
- `PO_total`: personal estimado de **todos** los sectores del DENUE (`stg.totales_municipio`), no solo turísticos.
- CL > 1: el municipio está más especializado que el promedio estatal. Municipio sin oferta en `x` → CL = 0.

### 1.4 Crecimiento logarítmico

```
Δlog = ln(1 + valor_final) − ln(1 + valor_inicial)
crecimiento % = (e^Δlog − 1) × 100
```

Se usa `1 +` para admitir ceros. Es estable con bases pequeñas, pero **bases muy pequeñas producen porcentajes
altos** aunque sumen pocas unidades (por eso las rutas y los semáforos ponderan por la base).

### 1.5 Concentración

```
participación s_m = PO_m / Σ PO
HHI = Σ s_m² × 10,000                 (0 = totalmente repartido; 10,000 = un solo municipio)
% top 5 = suma de las 5 participaciones mayores × 100
Gini = 1 − 2 · ∫ Lorenz              (motor del tablero)
```

### 1.6 Distancias y tiempos

- **Distancia:** haversine (radio 6,371 km) entre centroides municipales.
- **Tiempo estimado** en la base: `tiempo_min_est = distancia_km × 1.8` (factor calibrado con filas previas:
  241.1 min / 133.96 km). Es un tiempo en línea recta con factor de rodeo, **no** un tiempo de carretera.
- **Colindancia:** dos polígonos INEGI se consideran vecinos si se intersecan con un margen de 0.001° (~100 m),
  porque los polígonos no siempre comparten el borde exacto.

### 1.7 Similitud coseno

```
sim(a, b) = (v_a · v_b) / (‖v_a‖ · ‖v_b‖),  recortada a [0, 1]    (vectores sin componentes negativas)
```

---

## 2. A0 · Identidad: Pueblo Mágico, ancla y región

Código: `scripts/cargar_rutas_existentes.py`.

### 2.1 Pueblo Mágico

13 municipios (12 nombramientos; Cholula = San Pedro + San Andrés) con su año:

| Municipio | Año | | Municipio | Año |
|---|---|---|---|---|
| Cuetzalan del Progreso | 2002 | | San Andrés Cholula | 2012 |
| Zacatlán | 2011 | | Atlixco | 2015 |
| Chignahuapan | 2012 | | Huauchinango | 2015 |
| Pahuatlán | 2012 | | Tetela de Ocampo | 2020 |
| Tlatlauquitepec | 2012 | | Huejotzingo | 2023 |
| Xicotepec | 2012 | | Teziutlán | 2023 |
| San Pedro Cholula | 2012 | | | |

### 2.2 Criterio de ancla

> **Ancla = destino turístico consolidado y reconocido en un catálogo oficial.** Se cumple con cualquiera de:
> 1. Reconocimiento UNESCO y nodo urbano principal: **Puebla** (Centro Histórico, 1987) y **Tehuacán** (Reserva de
>    la Biosfera Tehuacán-Cuicatlán, 2018; segunda ciudad del estado). Constante `ANCLAS_EXTRA`.
> 2. **Pueblo Mágico con al menos 10 años de nombramiento** (año ≤ 2016). Constante `ANIOS_CONSOLIDACION = 10`.

Resultado: **12 anclas** (Puebla, Tehuacán, Cuetzalan, Zacatlán, Chignahuapan, Pahuatlán, Tlatlauquitepec,
Xicotepec, San Pedro Cholula, San Andrés Cholula, Atlixco, Huauchinango). Tetela, Huejotzingo y Teziutlán son Pueblo
Mágico pero **no** ancla (destino en consolidación).

**Validación del criterio (V2):** sin forzar el color, la intensidad turística calculada de las 12 anclas debe
quedar en la mitad alta del estado (percentil ≥ 50). Resultado: **12 de 12** (ver §7.1).

### 2.3 Región

Regionalización oficial de 7 regiones (Congreso del Estado, 2015): Sierra Norte (35), Sierra Nororiental (28),
Valle de Serdán (31), Angelópolis (33), Valle de Atlixco y Matamoros (24), Mixteca (45), Tehuacán y Sierra Negra
(21). El script **verifica que cubran exactamente los 217 municipios**; si un nombre no cruza, falla.

### 2.4 Cruce de nombres

Los nombres se normalizan (minúsculas, sin acentos) antes de buscarlos. Localidades mencionadas en las guías se
asignan a su municipio: Chipilo → San Gregorio Atzompa; Santa María Tonantzintla → San Andrés Cholula; Ciudad
Serdán → Chalchicomula de Sesma; San Miguel Tenextatiloyan → Zautla; Zapotitlán Salinas → Zapotitlán; "Cholula" →
San Pedro y San Andrés.

### 2.5 Rutas oficiales

- 29 rutas (22 del catálogo general en 4 circuitos, 4 circuitos de la Bioruta del Café, 3 de la Ruta del Mezcal),
  134 paradas, 70 municipios.
- Donde la fuente no numera, el orden es el de aparición. Las rutas de un solo municipio (Nopal y Tuna, Antojitos,
  Marisco) son `circuito_municipal`; las demás, `ruta_intermunicipal`.
- `es_ancla` de cada parada = el municipio es ancla; `distancia_desde_anterior_km` = línea recta entre centroides.
- **Tramos oficiales** (`dw.v_pares_rutas_existentes`): pares `(min, max)` de paradas consecutivas de rutas con
  `origen = 'existente'`; **84 tramos** únicos.

---

## 3. A1 · Oferta por eje turístico

Código: `scripts/cargar_datos_base.py` (sustituye a los pasos 2 y 4 de `DDL/02_etl_mopedetu.sql`).

### 3.1 Asignación SCIAN → eje (con pesos)

| Eje (`eje_sk`) | Prefijo / clase SCIAN 2023 | Peso |
|---|---|---|
| 1 · hospedaje | 721 | 1.0 |
| 2 · alimentos | 7225 restaurantes | 1.0 |
| | 7224 bares | 0.5 |
| 3 · turismo y cultura | 712 museos y sitios; 713111, 713112 parques; 713113, 713114 balnearios; 713910 golf; 713998 recreativos; 5615 agencias; 4871, 4872, 4879 transporte turístico | 1.0 |
| 4 · comercio turístico | 465915 artesanías | 1.0 |
| | 465912 regalos | 0.5 |
| | 327111 alfarería y talavera | 0.5 |
| | 465913 artículos religiosos | 0.3 |

- Un peso < 1 significa que la actividad atiende **a visitantes y a residentes**.
- Cuando varios prefijos coinciden, **gana el más largo**.
- El resto del sector 713 (gimnasios, billares, casinos, juegos) queda fuera.
- Resultado: 39 clases turísticas en `bridge_scian_eje`.

### 3.2 Cálculo por municipio y eje

```
unidades(m, e)     = Σ peso de los establecimientos del eje
personal_est(m, e) = Σ peso × punto_medio
participacion(m,e) = personal_est(m, e) / Σ_m personal_est(m, e)
CL(m, e)           = (personal_est(m,e) / PO_total(m)) / (Σ_m personal_est(m,e) / Σ_m PO_total(m))
ranking_estatal    = rango de personal_est dentro del eje (1 = mayor, método "min")
```

### 3.3 Nivel de predominancia (eje)

| Nivel interno | Regla | Valor guardado (restricción del DDL) |
|---|---|---|
| muy_alta | CL ≥ 2 **y** unidades ≥ 3 | `Alta` |
| alta | CL ≥ 1.25 **y** unidades ≥ 2 | `Alta` |
| media | CL ≥ 0.75 | `Media` |
| baja | CL < 0.75 con unidades > 0 | `Baja` |
| sin_oferta | unidades = 0 | `NULL` |

> El ETL SQL original (`02_etl`, paso 4) usaba CL ≥ 1.5 = Alta, ≥ 1.0 = Media y "No concluyente" con menos de
> 3 unidades. **Ese criterio fue reemplazado** por el de la tabla.

### 3.4 Censos Económicos por eje

Para CE 2019 y CE 2024 se suman los códigos `721, 7224, 7225, 712, 713111, 713112, 713113, 713114, 713910, 713998,
5615, 487, 465912, 465913, 465915, 327111` con los mismos pesos (487 completo cuenta como turismo):

- `unidades` = Σ peso × UE (vacío → 0).
- `personal_ocupado` y `va_censal_bruto_mdp` = Σ peso × valor **solo de los códigos publicados**.
- `hay_confidencial = true` si algún código con UE > 0 tiene personal oculto (la suma queda subestimada).

### 3.5 Concentración actual (`dw.v_concentracion`)

Suma `personal_est` de los 4 ejes por municipio y periodo y calcula el % del top 5 (por `RANK`) y el HHI.
DENUE 05/2026: **51.9 %** y **1,306**.

---

## 4. A1 · Actividades temáticas

Código: reglas en `model/actividades.py`, cálculo en `scripts/calcular_actividades.py`.

### 4.1 Tres señales

1. **SCIAN:** el código del establecimiento empieza con alguno de los códigos de la actividad.
2. **Nombre:** expresión regular sobre `nom_estab + raz_social` en minúsculas y sin acentos, **solo** si el SCIAN
   del establecimiento empieza con alguno de los prefijos permitidos (`nombre_en`). Evita falsos positivos como un
   "Café Internet", "Pulquería La Cabaña" o "Carnitas El Volcán". Un establecimiento detectado por SCIAN no se
   cuenta además por nombre.
3. **Catálogo:** el municipio aparece en una ruta oficial cuyo tema está en la lista de la actividad, es zona INAH
   (arqueología), o tiene un lugar con nombre que respalda la actividad (§5).

### 4.2 Reglas por actividad

Conjuntos de prefijos usados como `nombre_en`:
- `SCIAN_TURISTICO` = 7211, 7212, 7213, 7224, 7225, 7121, 7131, 7139, 5615, 4871, 4872, 4879, 3119, 3121, 3271,
  4659, 4612, 3114, 4663.
- `SCIAN_HOSPEDAJE_RECREACION` = 7211, 7212, 7213, 7121, 7131, 7139, 5615, 4871, 4872, 4879.

| Actividad | Eje | SCIAN | Palabras clave (regex) | Solo dentro de | Temas de catálogo |
|---|---|---|---|---|---|
| ☕ cafe | turismo | 311921, 311922 | `\bfinca\b`, cafetal, beneficio de cafe, cafe de altura, cafe organico, tostador | SCIAN_TURISTICO | cafe |
| 🥃 mezcal | turismo | 312145, 312149 | mezcal, mexcal, palenque | 3121, 4612, 7224, 7225, 4659 | mezcal |
| 🍷 bebidas_tradicionales | alimentos | 312132, 312139 | pulque, sidra, tlachiquer, licor, vino(s) de fruta, rompope | 3121 (solo elaboración) | — |
| 🏺 artesanias | comercio | 327111, 465915 | talavera, artesania, alfarer, `\bonix\b`, barro brunido | SCIAN_TURISTICO | — |
| 🍲 gastronomia | alimentos | — | `\bmoles?\b`, antojit, barbacoa, mixiote, cocina tradicional, chile(s) en nogada, cemita, mole de caderas | 7225, 3114, 4612 | gastronomia |
| 🏛️ museos | turismo | 712111, 712112 | — | — | — |
| 🗿 arqueologia | turismo | — | — | — | arqueologia (+ 4 zonas INAH) |
| ⛪ religioso | turismo | — | — | — | religioso, conventos |
| 🌲 ecoturismo | turismo | 721190, 721210, 712190, 713998 | ecotur, cabaña(s), campamento, tirolesa, rappel, parque ecologico, senderismo, canopy | SCIAN_HOSPEDAJE_RECREACION | senderismo, naturaleza, ciclismo, naturaleza_cultura, arqueologia_naturaleza |
| 🌋 volcanes | turismo | — | volcan, popocatepetl, iztaccihuatl, citlaltepetl, pico de orizaba, alta montana | SCIAN_HOSPEDAJE_RECREACION | naturaleza_cultura |
| ♨️ balnearios | turismo | 713113, 713114 | balneario, aguas termales, `termal\b`, spa termal | SCIAN_TURISTICO | — |
| 🌸 flores_viveros | comercio | — | vivero, floricult, invernadero | 4663, 1114 | — |
| 🤝 comunitario | turismo | — | `cooperativa(?! escolar)`, S.P.R., sociedad de produccion rural, ejido, comunitari | 7211, 7213, 7225, 7139, 7121, 5615, 4659 | — |
| 🧭 operadores | turismo | 561510, 561520, 487110, 487210, 487990 | — | — | — |

Zonas arqueológicas INAH: 21140 Cholula, 21170 Cantona (Tepeyahualco), 21043 Yohualichan (Cuetzalan), 21169 Tepexi el Viejo.

### 4.3 CL por actividad

```
participacion_estatal(a) = Σ_m personal(a, m) / Σ_m PO_total(m)
CL(m, a) = (personal(a, m) / PO_total(m)) / participacion_estatal(a)       (0 si no hay unidades)
```

### 4.4 Nivel de predominancia (actividad)

Para actividades con señal de DENUE (`nivel_predominancia(cl, unidades, catalogo)`):

| Nivel | Regla |
|---|---|
| `reconocida_sin_registro` | unidades = 0 **y** señal de catálogo (oferta invisible) |
| `sin_oferta` | unidades = 0 sin catálogo |
| `muy_alta` | CL ≥ 2 **y** unidades ≥ 3 |
| `alta` | CL ≥ 1.25 **y** unidades ≥ 2 ("un solo establecimiento no hace especialización") |
| `media` | CL ≥ 0.75 |
| `baja` | resto con unidades > 0 |

Para actividades **solo de catálogo** (arqueología y religioso, sin SCIAN ni palabra clave): `reconocida` si hay
señal de catálogo, `sin_oferta` si no.

Resultado (217 × 14 = 3,038 celdas): muy alta 95 · alta 98 · media 264 · baja 271 · reconocida 32 ·
reconocida sin registro 45 · sin oferta 2,233.

### 4.5 Actividades principales del municipio

```
p_cl  = percentil del CL dentro de la actividad (solo municipios con unidades > 0)
p_vol = percentil de ln(1 + unidades) dentro de la actividad (ídem)
score = 0.5·p_cl + 0.3·p_vol + 0.2·[señal de catálogo]
```

- Actividades solo de catálogo con señal: score fijo **0.9 arqueología** (zona INAH abierta = atractivo principal) y
  **0.6 religioso**.
- `rango_en_municipio` = orden por score descendente entre las actividades con score > 0.
- `es_principal` = rango ≤ 3 **y** nivel ≠ `baja`.
- Una actividad `reconocida_sin_registro` tiene score 0.2 y **puede** ser principal: así se muestra en la ficha como
  "reconocida, sin establecimientos registrados".

### 4.6 Validación V3 (actividades contra catálogo oficial)

¿El DENUE (sin contar la señal de catálogo) detecta la actividad en los municipios de su ruta oficial?

| Actividad | Detectada | Sin registro |
|---|---|---|
| ☕ Café (Bioruta) | **19 de 29 (66 %)** | Ajalpan, Eloxochitlán, Naupan, San Sebastián Tlacotepec, Tlacuilotepec, Tochimilco, Xochitlán de Vicente Suárez, Zautla, Zoquiapan, Zoquitlán |
| 🥃 Mezcal (Ruta del Mezcal) | **6 de 12 (50 %)** | Caltepec, Molcaxac, Huehuetlán el Grande, Tepeojuma, Tepexi de Rodríguez, Tzicatlacoyan |

Varios de estos municipios sin registro (Zoquiapan, Xochitlán, Huehuetlán el Grande, Tzicatlacoyan, Molcaxac)
aparecen después en las rutas propuestas: la oferta invisible es justamente lo que el optimizador lleva a las rutas.

**Criterio:** la brecha **no** se trata como error del modelo sino como evidencia de oferta informal reconocida
por la Secretaría y ausente del DENUE; se convierte en el nivel `reconocida_sin_registro` y en la bandera
`OFERTA_INVISIBLE`.

---

## 5. A1 · Lugares con nombre (atractivos)

Código: `scripts/cargar_atractivos.py`, tabla `dw.fact_atractivo_lugar`.

**Problema que resuelve:** el DENUE solo registra negocios. Un santuario o una cascada sin negocio detrás (El Peñón
de Jonotla) no existía para el modelo.

### 5.1 Clasificación de lugares de OSM (conservadora)

| Condición (en orden) | Categoría | Actividades que respalda |
|---|---|---|
| `amenity=place_of_worship` y nombre con santuario, basílica, ermita, convento, exconvento | santuario | religioso |
| `amenity=place_of_worship` sin esas palabras | templo | ninguna (se lista sin señal) |
| `natural=volcano` | volcán | volcanes |
| `natural=peak` | cerro | ninguna |
| `natural` ∈ waterfall, cave_entrance, spring, gorge, cliff, rock (o `waterway=waterfall`) | cascada, gruta, manantial, cañada, peña | ecoturismo |
| `tourism=viewpoint` | mirador | ecoturismo |
| `historic=monastery` o nombre religioso | santuario | religioso |
| nombre con "arqueolog" o `historic=archaeological_site` | zona_arqueologica | arqueologia |
| nombre con "museo" o `tourism=museum` | museo | museos |
| nombre con cascada, gruta, parque ecológico | naturaleza | ecoturismo |
| cualquier otro | atractivo | ninguna |

- Solo lugares **con nombre**; de `puntos.json` solo `tourism ∈ {attraction, museum, viewpoint}` o con `historic`.
- Municipio por punto en polígono INEGI (STRtree).
- Duplicados por municipio + nombre normalizado: **gana el catálogo curado**.
- Resultado: **580 lugares** (8 curados + 572 OSM) en 102 municipios.

### 5.2 Cómo cuentan como señal de catálogo

En `calcular_actividades.py`: el catálogo curado (`data/catalogos/atractivos.csv`, cada lugar con URL de fuente)
cuenta **completo**; de OSM solo cuentan **religioso, ecoturismo y volcanes** (museos y arqueología ya vienen del
DENUE y del INAH; así no se inflan actividades).

**Efecto verificado:** Jonotla pasa a tener turismo religioso y ecoturismo como actividades principales, es la
oportunidad #1 del índice (0.86) y entra en dos de las cinco rutas propuestas.

---

## 6. A2 · Accesibilidad e infraestructura

### 6.1 Matriz de accesibilidad (`dw.fact_accesibilidad`)

- Todos los pares ordenados de municipios: 217 × 216 = **46,872** filas.
- `distancia_km_recta` (haversine entre centroides), `tiempo_min_est = distancia × 1.8`, `es_colindante` (§1.6).
- **Control de calidad:** comparada con las 1,560 filas previas del rol A: diferencia media de distancia
  **0.67 km** y colindancia **100 %** idéntica.

### 6.2 Indicadores (`dw.fact_infraestructura`, `scripts/calcular_ficha.py`)

| Indicador | Cálculo | Fuente |
|---|---|---|
| `min_ancla_cercana` | haversine desde el *representative point* del polígono al de la ancla más cercana × 1.8; **0 si el municipio es ancla** | Marco INEGI |
| `ancla_cercana_sk` | municipio_sk de esa ancla (el propio si es ancla) | Marco INEGI |
| `min_capital` | ídem hacia Puebla (21114) | Marco INEGI |
| `municipios_colindantes` | polígonos que intersecan con margen 0.001° | Marco INEGI |
| `km_vias_principales` | cada segmento de vía OSM (motorway a tertiary) se asigna al municipio de su punto medio; longitud haversine | OSM |
| `km_vias_por_km2` | km de vías / superficie | OSM + INEGI |
| `terminales_autobus` | `amenity=bus_station` | OSM |
| `atractivos_osm` | `tourism ∈ {attraction, museum, viewpoint}`, `historic`, `leisure ∈ {nature_reserve, water_park}` | OSM |
| `unidades_hospedaje`, `personal_hospedaje` | SCIAN 721 | DENUE |
| `unidades_alimentos`, `personal_alimentos` | SCIAN 7225 | DENUE |
| `gasolineras` | 468411 | DENUE |
| `bancos` | 522110 | DENUE |
| `farmacias` | 464111, 464112 | DENUE |
| `unidades_salud` | 6211, 6221, 6222 | DENUE |
| `poblacion_2020` | POBTOT | ITER 2020 |
| `pct_viviendas_internet` | 100 × VPH_INTER / VIVPAR_HAB | ITER 2020 |
| `servicios_por_10k_hab` | 10,000 × (gasolineras + bancos + farmacias + salud) / población | DENUE + ITER |
| `indice_carencias` | promedio de percentiles de 8 variables (§8.2) | ITER 2020 |
| `intensidad_turistica` | §7.1 | DENUE + rutas + marcas |

### 6.3 Índice de infraestructura (0-1)

```
I_infra = 0.35·pct(−min_ancla_cercana)
        + 0.25·pct(km_vias_por_km2)
        + 0.20·pct(ln(1 + unidades_hospedaje))
        + 0.10·pct(servicios_por_10k_hab)
        + 0.10·pct(pct_viviendas_internet)
```

Pesos guardados en `dim_version_calculo` → `ficha_semaforos_v1`.

---

## 7. A3 · Intensidad turística y temporadas

### 7.1 Intensidad turística actual (proxy de demanda)

```
por_mil  = 1000 × (personal_hospedaje + personal_alimentos) / poblacion_2020
n_rutas  = número de rutas oficiales distintas que pasan por el municipio
marca    = 1.0 si es ancla · 0.5 si es Pueblo Mágico no ancla · 0 en otro caso

intensidad = 0.40·pct(por_mil) + 0.25·pct(ln(1 + unidades_hospedaje)) + 0.15·pct(n_rutas) + 0.20·marca
```

> El diseño (`modelo_predictivo_anillos.md`) proponía 40/25/15/10/10 con un componente de visibilidad en
> boletines. Como no hay datos de visibilidad, el código usa **40/25/15/20** y la marca absorbe el 20 %.

**V2:** las 12 anclas quedan en percentil ≥ 50 de intensidad (12/12) sin forzar el color.

**V9 (pendiente):** comparar el orden del proxy contra la ocupación hotelera de DATATUR en los destinos que tienen
datos (criterio: Spearman ≥ 0.6).

### 7.2 Temporadas (`dw.fact_temporada`, 31 registros)

Tres capas con `intensidad ∈ {1, 2, 3}`:

| Capa | Ejemplos | Aplica a |
|---|---|---|
| Vacaciones nacionales (municipio y actividad vacíos) | Semana Santa (mar-abr, 3), verano (jul-ago, 2), Día de Muertos (oct-nov, 2), invierno (dic-ene, 2) | Todos los municipios |
| Temporada de actividad (municipio vacío, actividad llena) | Cosecha de café (nov-mar, 2), chiles en nogada (ago-sep, 2), alta montaña (nov-mar, 2), palenques (todo el año, 1) | Municipios donde esa actividad es **principal** |
| Evento municipal | Feria del Café y el Huipil (Cuetzalan, oct, 3), Fiesta de la Virgen del Peñón (Jonotla, oct, 2), Carnaval de Huejotzingo (feb, 3)… | Ese municipio |

Los rangos que cruzan el año (dic → ene) se manejan como `mes ≥ inicio OR mes ≤ fin`.

### 7.3 Tira de 12 meses y meses fuertes (vista `v_ficha_municipio`)

```
intensidad(m, mes)        = máx intensidad de: vacaciones nacionales + temporadas de sus actividades principales + sus eventos
intensidad_propia(m, mes) = máx intensidad de: temporadas de sus actividades principales + sus eventos (sin vacaciones)
meses_fuertes(m)          = meses con intensidad_propia ≥ 2
```

### 7.4 Meses fuertes para el modelo (`model/enlaces.py → meses_fuertes`)

Variante binaria 0/1 por mes usada en perfiles, enlaces y rutas:
- Eventos del municipio con intensidad ≥ 2 → 1 en sus meses.
- Temporadas de actividad (sin municipio) → 1 en sus meses para los municipios donde la actividad es principal,
  **sin filtrar por intensidad** (por eso los municipios con mezcal principal quedan con los 12 meses).

---

## 8. A4 · Contexto social

### 8.1 Variables (`dw.fact_contexto_social`)

Población 2020 (ITER), `indice_marginacion` y `grado_marginacion` (CONAPO 2020, método DP2), `pct_pobreza`
(CONEVAL 2020) y `pct_viviendas_internet`.

> **Atención al signo:** en el índice DP2 de CONAPO un valor **mayor** significa **menos** marginación. Por eso en
> todo el modelo la necesidad social es `pct(−indice_marginacion)`.

### 8.2 Índice de carencias (respaldo)

Mientras no había CONAPO, el semáforo social usaba el promedio de percentiles de 8 variables del Censo 2020 (las
mismas con que CONAPO construye su índice): analfabetismo, población sin escolaridad (ambas sobre 15 años y más),
viviendas sin drenaje, sin electricidad, sin agua entubada, con piso de tierra, sin refrigerador y ocupantes por
cuarto.

**Validación:** Spearman entre este índice y el de CONAPO = **−0.914** (concordancia fuerte; signo negativo por la
convención DP2).

### 8.3 Regla de uso

La necesidad social **solo suma**: entra al índice, al valor de un municipio en las rutas y al semáforo como
prioridad de impacto. Nunca resta oportunidad.

---

## 9. Semáforos de la ficha técnica

Código: `scripts/calcular_ficha.py`, versión `ficha_semaforos_v1`. Regla de lectura: **el color dice qué hacer, no
si el municipio es bueno o malo**. Cada semáforo guarda `valor`, `percentil` y `motivo`.

| Dimensión | Valor | 🟢 verde | 🟡 amarillo | 🔴 rojo | ⚪ gris |
|---|---|---|---|---|---|
| **🧳 Turismo actual** | percentil `p` de la intensidad (§7.1) | `p < 0.5`: capacidad para recibir visitantes | `0.5 ≤ p < 0.85` | `p ≥ 0.85` **o es ancla** (siempre rojo): ya concentra turismo | sin hospedaje **ni** restaurantes en el DENUE |
| **🛣️ Infraestructura** | `I_infra` (§6.3) | `≥ 0.6`: lista para recibir | `0.35 ≤ I < 0.6`: mejorable | `< 0.35`: barrera de acceso | valor faltante |
| **🎯 Oferta** | máx CL entre actividades | alguna actividad `muy_alta` o `alta`: especializada | ≥ 2 actividades presentes (cualquier nivel ≠ sin_oferta) sin especialización: diversa | exactamente 1 actividad presente: mínima | ninguna |
| **📈 Potencial** | crecimiento predicho ponderado (abajo) | `v > mediana estatal` **y** límite inferior `> 0`: crece | `v > 0`: incierto | `v ≤ 0`: estancado o en retroceso | sin predicción |
| **🤝 Necesidad social** | grado CONAPO | bajo o muy bajo | medio | alto o muy alto: prioridad de impacto | sin dato |

**Detalle del potencial:**

```
peso_e = max(1, personal_base_e)           (personal_base nulo → 0 → 1)
v      = Σ_e peso_e · crecimiento_pred_pct_e / Σ_e peso_e
lo     = Σ_e peso_e · intervalo_inf_pct_e    / Σ_e peso_e
mediana estatal = mediana de v entre municipios
```

Se pondera por empleo porque el máximo entre ejes lo inflaba un eje con 3 negocios.

**Detalle social con respaldo:** si no hay grado CONAPO, se usa el percentil `q` del índice de carencias: `q ≥ 0.6`
rojo, `q ≥ 0.4` amarillo, resto verde.

**Resultado (217 municipios):**

| Dimensión | 🟢 | 🟡 | 🔴 | ⚪ |
|---|---|---|---|---|
| Turismo actual | 106 | 76 | 33 | 2 |
| Infraestructura | 61 | 106 | 50 | — |
| Oferta | 119 | 60 | 21 | 17 |
| Potencial | 108 | 108 | 1 | — |
| Social | 65 | 66 | 86 | — |

**Lectura de negocio:** un municipio 🟢 en turismo actual, 🟢 en oferta y 🟢/🟡 en infraestructura es justo el que
conviene llevar a una ruta; uno 🔴 en turismo actual es un ancla que **envía** visitantes.

---

## 10. Índice de oportunidad (v1 y v2)

Código: `model/indice.py` (v1) y `model/crecimiento.py` (v2). Tabla `fact_indice_oportunidad`. Se calcula **por
municipio × eje** (217 × 4 = 868 filas por versión); todos los componentes son percentiles estatales.

### 10.1 Componentes

```
score_oferta(m, e)          = 0.6·pct(CL_e) + 0.4·pct(ln(1 + personal_est_e))           [DENUE 05/2026]

score_complementarios(m, e) = 0.4·promedio(score_oferta de los otros 3 ejes)
                            + 0.3·pct(Σ atractivos de fact_atractivo: OSM + INAH)
                            + 0.3·pct(número de actividades con nivel ≠ sin_oferta)

score_accesibilidad(m)      = 0.7·pct(−min_ancla_cercana) + 0.3·pct(km_vias_por_km2)

score_social(m)             = pct(−indice_marginacion)                                    [más marginación, más prioridad]

score_potencial(m, e)       = percentil del crecimiento_pred_pct dentro del eje            [solo v2; NaN → 0]
```

### 10.2 Pesos por versión (`dim_version_calculo.pesos`)

| Componente | `v1_base` | `v2_con_prediccion` |
|---|---|---|
| oferta | 0.35 | 0.25 |
| complementarios | 0.15 | 0.10 |
| accesibilidad | 0.25 | 0.25 |
| social | 0.25 | 0.20 |
| potencial predicho | — | 0.20 |

```
indice_oportunidad = Σ peso_k · score_k           (∈ [0, 1])
ranking_estatal    = orden descendente dentro del eje (método "min")
```

### 10.3 Índice del municipio

`dw.v_indice_municipio` toma la **versión más reciente** y, por municipio, el **eje con mayor índice** (eje líder);
ranking estatal sobre ese máximo. Las rutas también usan el mejor eje de v2 (§16.1).

### 10.4 Validaciones del índice

- **Coherencia:** `indice.py` imprime el índice medio de anclas contra el resto (control visual).
- **Resultado:** mejores oportunidades fuera de anclas: Jonotla (0.86), Huehuetla, Jalpan, Zacapoaxtla, Zapotitlán
  de Méndez, Huehuetlán el Grande, Pantepec.
- **V6 (pendiente):** sensibilidad de ±20 % en cada peso; criterio: el top 20 conserva ≥ 70 % de sus municipios.

---

## 11. Banderas de oportunidad

Código: `model/indice.py → banderas()`. Tabla `fact_flag_oportunidad`, una fila por municipio × eje × tipo ×
versión (4,340 por versión), con `flag_activo` y `motivo` legible.

| Bandera | Regla exacta (por municipio `m` y eje `e`) | Motivo guardado |
|---|---|---|
| `OFERTA_EMERGENTE` | `CL_e ≥ 1.25` **y** `unidades_e ≥ 3` **y** no es ancla **ni** Pueblo Mágico | "Cociente de localización X en <eje> con N establecimientos, fuera de anclas y Pueblos Mágicos" |
| `ACCESIBLE_NO_EXPLOTADO` | `min_ancla ≤ 60` **y** `score_oferta < 0.4` **y** `score_complementarios ≥ 0.5` **y** no es ancla | "A X min de un ancla, con atractivos y actividades pero poca oferta de <eje> (percentil P)" |
| `BARRERA_ACCESO` | `score_oferta ≥ 0.6` **y** (`min_ancla > 75` **o** (`km_vias_por_km2 < P25 estatal` **y** `min_ancla > 45`)) **y** no es ancla | "Oferta de <eje> en percentil P pero a X min del ancla más cercana y Y km de vías principales/km²" |
| `OFERTA_INVISIBLE` | el municipio tiene alguna actividad de ese eje con nivel `reconocida_sin_registro` | "Reconocida en ruta oficial sin registro DENUE: <actividades>" |
| `IMPACTO_SOCIAL` | alguna de las cuatro anteriores activa **y** grado de marginación `Alto` o `Muy alto` | "Bandera activa en municipio con grado de marginación <grado> (CONAPO 2020)" |

- 75 min es el **tramo máximo de una ruta**: más lejos, el municipio no entra a una ruta desde un ancla.
- Resultado v2: **385 banderas activas en 131 municipios**.
- Las banderas se recalculan igual para v1 y v2 (solo cambian si cambia algún score que usan).

> Umbrales del borrador (`tareas_A_galo.md`, `modelo_dimensional.md`): CL ≥ 1.5 y > 120 min, y banderas de
> visibilidad o inversión (`OFERTA_SIN_INVERSION`, `INVERSION_SIN_RETORNO`, `BARRERA_INFRAESTRUCTURA`). En el modelo
> real **no hay datos de visibilidad ni inversión**: esas banderas solo existen en el motor DEMO (§19.4).

---

## 12. Modelo de crecimiento de unidades económicas (rol C, en producción)

Código: `model/crecimiento.py`. Es el modelo que **alimenta el índice v2, los semáforos de potencial, las rutas y el
escenario HHI** en Supabase. Registro: `dim_modelo` → `crecimiento_ue_eje_lgbm_v1`.

### 12.1 Pregunta y objetivo

¿Cuánto crecerán las **unidades económicas turísticas** de cada municipio y eje en 5 años?

```
y = ln(1 + UE_2024) − ln(1 + UE_2019)        (Censos Económicos, por municipio × eje)
```

**Por qué unidades y no personal:** INEGI oculta el personal por confidencialidad en la mayoría de los municipios
pequeños: solo **136 de 868** casos tenían personal en ambos censos. Las unidades **nunca** se ocultan.

### 12.2 Filtro de casos válidos

`y` es válido solo si `UE_2019 ≥ 3` **o** `UE_2024 ≥ 3` (vacíos tratados como 0). Evita crecimientos espurios de
bases mínimas. Resultado: **482 casos** de 868.

### 12.3 Variables (23, medidas en el año base `t`)

Para entrenar `t = 2019`; para predecir `t = 2024`.

| # | Variable | Definición |
|---|---|---|
| 1 | `eje` | 1-4 (entero; LightGBM la usa como numérica) |
| 2 | `log_po` | ln(1 + personal ocupado del eje) |
| 3 | `log_ue` | ln(1 + unidades del eje) |
| 4 | `tamano_medio` | personal / unidades |
| 5 | `productividad` | valor agregado censal bruto / personal |
| 6 | `confidencial` | 1 si alguna celda del eje fue confidencial |
| 7 | `peso_en_municipio` | personal del eje / personal total del municipio (sector TOTAL del censo) |
| 8 | `cociente_localizacion` | `peso_en_municipio` / (personal estatal del eje / personal estatal total) |
| 9 | `log_po_municipio` | ln(1 + personal total del municipio) |
| 10 | `log_po_vecinos` | **rezago espacial**: promedio de `log_po` del mismo eje en los municipios colindantes |
| 11 | `pueblo_magico` | 1 solo si el nombramiento es ≤ `t` (sin fuga) |
| 12 | `ancla` | es ancla |
| 13 | `region` | código de categoría de la región |
| 14 | `marginacion` | índice CONAPO 2020 |
| 15 | `pobreza` | % CONEVAL 2020 |
| 16 | `internet` | % viviendas con internet 2020 |
| 17 | `log_poblacion` | ln(1 + población 2020) |
| 18 | `min_ancla` | minutos al ancla más cercana |
| 19 | `min_capital` | minutos a Puebla |
| 20 | `vias_km2` | km de vías principales por km² |
| 21 | `colindantes` | número de municipios vecinos |
| 22 | `atractivos` | Σ atractivos (OSM + INAH) |
| 23 | `rutas_oficiales` | número de rutas oficiales que lo incluyen |

Los faltantes (personal confidencial, divisiones entre cero) quedan como `NaN`: LightGBM los maneja de forma nativa.

### 12.4 Algoritmo e hiperparámetros

LightGBM regresor: `n_estimators=400, learning_rate=0.03, num_leaves=15, min_child_samples=12, subsample=0.8,
subsample_freq=1, colsample_bytree=0.8, reg_lambda=1.0, random_state=2026`.

### 12.5 Esquema de validación

- **GroupKFold de 5 particiones agrupado por municipio**: un municipio (con sus 4 ejes) nunca está a la vez en
  entrenamiento y prueba. Las predicciones de cada partición se juntan en un vector fuera de muestra.
- **Líneas base**, evaluadas en las mismas particiones:
  - **B1 · media del eje:** crecimiento medio del eje en el entrenamiento.
  - **B2 · Ridge:** `StandardScaler + Ridge(alpha=3.0)` con las mismas variables, faltantes imputados con la
    mediana del entrenamiento.
- No hay segundo periodo temporal porque el CE 2014 no tiene descarga por entidad en datos abiertos.

### 12.6 Métricas

```
MAE         = promedio |ŷ − y|
Spearman    = correlación de rangos entre ŷ y y
precisión top 20 % = |{y ≥ P80(y)} ∩ {ŷ ≥ P80(ŷ)}| / |{ŷ ≥ P80(ŷ)}|
```

| Modelo | MAE | Spearman | Precisión top 20 % |
|---|---|---|---|
| **LightGBM** | **0.246** | **+0.476** | **54 %** |
| B1 · media del eje | 0.273 | +0.333 | 34 % |
| B2 · Ridge | 0.283 | +0.329 | 45 % |

### 12.7 Intervalo de predicción conformal (80 %)

```
q80 = percentil 80 de |ŷ_fuera_de_muestra − y|     → 0.374 en escala logarítmica
intervalo = [ŷ − q80, ŷ + q80]                      → en %: [(e^(ŷ−0.374) − 1)·100, (e^(ŷ+0.374) − 1)·100]
```

Cobertura medida fuera de muestra: **79.9 %** (nominal 80 %). En escala multiplicativa equivale a ±0.374 log:
el límite superior es ~1.45 veces y el inferior ~0.69 veces la predicción central (sobre 1 + UE).

### 12.8 Regla de corte

```
gana = MAE(LightGBM) < min(MAE(B1), MAE(B2))
```

Si no gana, se publica la predicción de Ridge ajustado con todos los datos. En la corrida vigente **gana**.

### 12.9 Explicabilidad

Contribuciones SHAP exactas de LightGBM (`pred_contrib=True`), promedio del valor absoluto por variable,
normalizado a 100 %. Las más influyentes: oferta actual del eje (16 %), eje (9 %), especialización (7 %), tamaño
medio (6 %), población (6 %), oferta de los vecinos (6 %).

### 12.10 Predicción 2024 → 2029

1. Ajuste final con los 482 casos.
2. Se aplican las variables medidas en 2024 a **las 868 celdas** (todas las combinaciones municipio × eje).
3. Columnas:
   - `personal_base`: personal del CE 2024 si es público; si INEGI lo ocultó, el personal estimado del DENUE 05/2026
     para ese eje.
   - `crecimiento_pred_pct = (e^ŷ − 1) × 100`.
   - `intervalo_inf_pct`, `intervalo_sup_pct` (§12.7).
   - `ranking_potencial`: orden por crecimiento dentro del eje (1 = mayor).
   - `horizonte_anios = 5`, `periodo_base = CE 2024`.
4. Se registran también las dos líneas base en `dim_modelo` (`tarea = 'linea_base'`) con sus métricas.

**Cuidado de interpretación:** al predecir sobre las 868 celdas, las de base cero o mínima producen porcentajes
muy altos (media 136 %, mediana 62 %). Por eso el semáforo de potencial pondera por `personal_base` y las rutas
reportan el crecimiento de sus paradas como referencia, no como cifra exacta.

### 12.11 Paso al índice v2

```
score_potencial(m, e) = percentil de crecimiento_pred_pct dentro del eje e
```

Luego se recalculan índice y banderas con los pesos `v2_con_prediccion`.

---

## 13. Modelo de crecimiento del personal ocupado (rol B)

Código: `model/prediccion_crecimiento.py` (trabaja con archivos locales en `data/stg/` y escribe `data/modelo/`).
Es un modelo **complementario**: tiene validación temporal real pero cubre menos celdas.

### 13.1 Datos y ejes

- Censos Económicos 2014, 2019 y 2024 en la **versión histórica del CE 2024** (homologa las tres ediciones a SCIAN
  2023 y al marco geoestadístico vigente).
- Ejes por subsector: hospedaje = 721; alimentos = 722; turismo_cultura = 711, 712, 713; comercio_turistico = 5615.
- **Si cualquier sector del eje es confidencial, el personal y el valor agregado del eje quedan nulos** (no se
  rellenan).
- Si el municipio aparece en el censo y un sector no, ese sector vale **0** (INEGI no publica renglones vacíos).
- Totales estatales desde la clave 21000.

### 13.2 Panel y objetivo

- Panel municipio × eje × transición: (2014 → 2019) y (2019 → 2024); solo celdas con presencia del eje al inicio
  o al final. 574 y 590 celdas; con objetivo observable, **214 y 208**.
- Objetivo: `delta_log = ln(1 + PO_fin) − ln(1 + PO_inicio)`.

### 13.3 Variables (todas al inicio de la transición)

Numéricas (12): `log_po`, `log_ue`, `po_por_ue`, `part_po_estatal`, `part_ue_estatal`, `va_trab_rel` (valor
agregado por trabajador relativo al estado), `lq_po`, `lq_ue` (CL por personal y por unidades), `log_po_total_mun`,
`log_poblacion`, `indice_marginacion`, `dist_ancla_km`. Categóricas con *one-hot*: `eje`, `region`.

- `dist_ancla_km` y `region` se calculan con las **9 anclas DEMO** y la región aproximada por coordenadas de
  `dashboard/datos.py`, no con las 12 anclas y 7 regiones oficiales.
- Población y marginación son de 2020 (estáticas en ambas transiciones).

### 13.4 Modelos candidatos

| Nombre | Algoritmo | Variables |
|---|---|---|
| `ridge` | `SimpleImputer(mediana, indicador de faltante) + StandardScaler + RidgeCV(alphas = logspace(−2, 3, 30))` | 12 + categóricas |
| `gbm` | `HistGradientBoostingRegressor(max_depth=3, learning_rate=0.05, max_iter=250, min_samples_leaf=20, l2_regularization=1.0)` | 12 + categóricas |
| `gbm_ue` | Igual que `gbm` | sin las 5 que dependen del personal (para celdas con personal confidencial) |

### 13.5 Líneas base

| Línea base | Regla |
|---|---|
| Persistencia | repite el `delta_log` 2014 → 2019 del mismo municipio y eje (si falta, la mediana del eje) |
| Mediana del eje | mediana de `delta_log` del eje en 2014 → 2019 |
| Cociente de localización | ordena por `lq_po` (o `lq_ue`); solo sirve para ranking, sin MAE |

### 13.6 Validación

1. **Temporal (principal):** entrena con 2014 → 2019, prueba con 2019 → 2024 (208 celdas).
2. **Espacial (adicional):** con ambas transiciones, deja fuera **una región completa** en cada pliegue.

Métricas: Spearman global; **precisión top 20** (las 20 celdas con mayor crecimiento real contra las 20 con mayor
predicción); por eje con ≥ 10 filas: Spearman y precisión top `k = min(20, n/2)`; promedios por eje; MAE.

| Modelo (temporal) | Spearman global | Spearman medio por eje | Precisión top 20 | MAE |
|---|---|---|---|---|
| Persistencia | −0.171 | −0.267 | 0.05 | 0.482 |
| Mediana del eje | 0.241 | — | 0.15 | 0.338 |
| Cociente de localización | −0.304 | −0.396 | 0.05 | — |
| Ridge | 0.254 | 0.160 | 0.20 | **0.322** |
| **Gradient boosting** | **0.268** | **0.215** | **0.25** | 0.327 |
| Gradient boosting solo unidades | 0.229 | 0.125 | 0.25 | 0.341 |

Espacial (422 filas): gbm Spearman **0.378**, precisión top 20 = 0.30, MAE 0.297.

**Hallazgo:** persistencia y CL tienen correlación **negativa**: los municipios que más crecieron o ya están
especializados tienden a crecer menos después (**regresión a la media**).

### 13.7 Reglas de selección y de corte

```
elegido = el de mayor Spearman global entre ridge y gbm           → gbm
supera(modelo) = Spearman(modelo) > Spearman de TODAS las líneas base
                 Y precisión_top20(modelo) ≥ precisión de TODAS las líneas base
```

- `gbm` supera las tres líneas base → se usa.
- `gbm_ue` **no** supera a la mediana del eje (0.229 < 0.241) → **las celdas con personal confidencial quedan sin
  predicción** (no se inventan).

### 13.8 Intervalos empíricos

- Cuantiles 10 % y 90 % del residuo fuera de muestra **por eje** (de la validación espacial); ejes con < 15 filas
  usan los cuantiles globales.
- Cobertura medida en la prueba temporal (con residuos de 2014 → 2019): **75 %** contra 80 % nominal.

### 13.9 Explicabilidad

Importancia por permutación sobre la prueba temporal (20 repeticiones, aumento del MAE), agrupando las columnas
*one-hot* de cada variable. Orden: personal por unidad, CL por unidades, personal inicial, CL por personal, valor
agregado por trabajador. Población, marginación y distancia al ancla aportan poco.

### 13.10 Predicción

Ajuste final con ambas transiciones, predicción desde CE 2024 (horizonte 5 años) para celdas con `UE > 0` y personal
publicado: **270 celdas** (alimentos 129, hospedaje 86, turismo_cultura 49, comercio_turistico 6), con
`personal_pred = e^(ln(1+PO) + Δlog) − 1`, `incremento_personal_pred`, intervalos y `ranking_potencial` por eje.

**Uso recomendado:** combinar `ranking_potencial` con `incremento_personal_pred` o `personal_base`.

---

## 14. Perfiles, similitud y clusters

Código: `model/enlaces.py`. Versión `perfil_v1` con los pesos de bloque en JSON.

### 14.1 Perfil del municipio (33 dimensiones, todas ≥ 0)

| Bloque | Dimensiones | Normalización | Peso de bloque |
|---|---|---|---|
| Actividades | 14 (score de §4.5) | dividido entre el máximo de cada actividad | **1.0** |
| Ejes | 4 (CL por eje) | percentil | **0.8** |
| Temporada | 12 meses fuertes 0/1 (§7.4) | — | **0.35** |
| Contexto | intensidad turística, marginación `pct(−índice)`, accesibilidad `pct(−min_ancla)` | percentil | **0.5** |

El tema (actividades y ejes) define la compatibilidad; temporada y contexto la matizan.

### 14.2 Similitud

Coseno entre perfiles, recortado a [0, 1]. Se guarda en `fact_similitud` para los **8,452 pares** (a < b) a
≤ 150 min estimados.

### 14.3 Clusters

1. Estandarización z de cada dimensión del perfil.
2. K-means (`n_init=20`, semilla 2026) para k ∈ {5, 6, 7, 8, 9}; se elige **k con mayor silueta** → **k = 5**.
3. Etiqueta automática: los 2 rasgos no mensuales con mayor valor en el centroide + la región más frecuente.

| Cluster (etiqueta resumida) | Municipios |
|---|---|
| Café + alta marginación (Sierra Norte) | 36 |
| Gastronomía tradicional (Mixteca) | 89 |
| Turismo religioso y museos: destinos consolidados (Angelópolis) | 8 |
| Artesanías + alta marginación (Mixteca) | 62 |
| Mezcal y ecoturismo | 22 |

---

## 15. Modelo de enlaces entre municipios

Código: `model/enlaces.py`. Registro: `enlace_municipios_lgbm_v1`. Tabla `fact_prediccion_enlace`.

### 15.1 Pregunta

¿Forman los municipios `a` y `b` un **tramo** de ruta turística? Aprende de cómo la Secretaría arma sus rutas.

### 15.2 Universo y etiquetas

- **Universo:** pares a < b con `tiempo_min_est ≤ 150` → **8,452 pares**.
- **Positivos:** pares consecutivos (distintos) de las 29 rutas oficiales, deduplicados → **79** dentro del universo
  (84 tramos oficiales; 5 quedan fuera por estar a más de 150 min).
- **Negativos:** el resto. **Tasa base 0.93 %** (muy desbalanceado).

### 15.3 Variables del par (14)

| Variable | Definición |
|---|---|
| `distancia_km` | línea recta entre centroides |
| `colindante` | 0/1 |
| `misma_region` | 0/1 |
| `similitud` | coseno de perfiles (§14.2) |
| `mismo_cluster` | 0/1 |
| `act_compartidas` | número de actividades **principales** en común |
| `misma_lider` | 0/1, misma actividad #1 |
| `meses_compartidos` | número de meses fuertes en común |
| `intensidad_max`, `intensidad_min` | intensidad turística del más y del menos turístico |
| `anclas` | número de anclas en el par (0-2) |
| `pueblos_magicos` | número de Pueblos Mágicos en el par (0-2) |
| `atractivos_min` | mínimo de ln(1 + atractivos) |
| `dif_marginacion` | diferencia absoluta del índice de marginación |

### 15.4 Algoritmo

LightGBM clasificador: `n_estimators=300, learning_rate=0.03, num_leaves=15, min_child_samples=10, subsample=0.8,
subsample_freq=1, colsample_bytree=0.8, class_weight="balanced", random_state=2026`.

### 15.5 Validación

- **StratifiedGroupKFold de 5 particiones** (barajado, semilla 2026). Grupos: para un positivo, **su ruta**; para un
  negativo, un grupo pseudoaleatorio estable `1000 + (7a + b) mod 29`.
- Así **los tramos de una misma ruta nunca se reparten entre entrenamiento y prueba**, y cada partición tiene
  positivos.
- *Corrección documentada:* primero se usó GroupKFold, que juntaba las 29 rutas (grupos pequeños) en una sola
  partición y dejaba otras sin positivos para entrenar.
- **Líneas base:** puntaje = −distancia; puntaje = similitud.

| Modelo | AUC | Precisión media (AP) |
|---|---|---|
| **LightGBM** | **0.881** | **0.096** |
| Solo distancia | 0.856 | 0.042 |
| Solo similitud | 0.699 | 0.019 |

AP 2.3 veces la de la distancia (sobre una tasa base de 0.0093). **SHAP:** distancia (30 %), turismo actual de los
dos municipios (25 %), actividades compartidas (9 %), atractivos (7 %).

### 15.6 Salida y uso

- Ajuste final con todos los pares; se guarda la probabilidad **cruda** en [0, 1].
- En el optimizador se transforma a **percentil** (`pe_pct`), porque la probabilidad cruda es muy baja por la tasa
  base de ~1 %.
- **Limitación asumida:** aprende el sesgo de la Secretaría hacia anclas y municipios conocidos; por eso el
  optimizador **no** se guía solo por esta probabilidad: la combina con el índice y las banderas para llevar la ruta
  a municipios emergentes.

---

## 16. Optimizador de rutas nuevas

Código: `model/rutas.py`. Escribe `dim_ruta` / `fact_ruta_parada` (`origen = 'propuesta_modelo'`) y
`fact_ruta_evaluacion`.

### 16.1 Insumos

| Insumo | De dónde |
|---|---|
| Índice del municipio | fila de **mayor índice v2** entre sus 4 ejes (también define su `eje_sk` en la ruta) |
| Con bandera | municipios con **cualquier** bandera v2 activa |
| Crecimiento | `fact_prediccion_crecimiento` |
| Probabilidad de enlace | `fact_prediccion_enlace`, simétrica, convertida a percentil `pe_pct` |
| Tiempos y distancias | `fact_accesibilidad` |
| Tramos oficiales | conjunto de pares consecutivos de las rutas oficiales |
| Necesidad social | `pct(−indice_marginacion)` |
| Meses fuertes | §7.4 |
| Anclas | las 12 oficiales |

### 16.2 Temas

12 temas: café, mezcal, ecoturismo, gastronomía, artesanías, bebidas tradicionales, religioso, balnearios, flores y
viveros, museos, arqueología y volcanes.

- **Excluidos:** `comunitario` (señal por nombre ruidosa: "cooperativa", "ejido" aparecen en restaurantes y
  cooperativas escolares; se reincorporará con un catálogo de cooperativas turísticas) y `operadores`.
- **Tema presente** en un municipio solo con presencia **fuerte**: nivel `muy_alta`, `alta`, `reconocida` o
  `reconocida_sin_registro`. Un nivel `media` puede venir de un solo negocio (por ejemplo, una vinatería para el
  mezcal) y no cuenta.

### 16.3 Valor de un municipio en una ruta de tema `t`

```
valor(m, t) = índice_v2(m)
            × (1 + 0.35 · [m tiene bandera activa])
            × (1 + 0.40 · necesidad_social(m))
            × (1 + 0.25 · [t presente en m])
```

> El docstring del archivo dice 0.20 para el bono social; el código usa **0.40**.

### 16.4 Construcción de una ruta (por cada ancla × tema: 12 × 12 = 144)

**Candidatos:** municipios con el tema presente, **excluyendo todas las anclas** (la única ancla de la ruta es la
de salida).

**Inserción voraz** desde `ruta = [ancla]`, mientras la ruta tenga menos de 6 paradas:

```
para cada candidato c no incluido:
    t = tiempo(fin, c)
    descartar si no hay tiempo, si t > 75 min o si recorrido(ruta) + t > 240 min
    nuevo = 1 si el tramo (fin, c) no está en ninguna ruta oficial
    ganancia(c) = valor(c, t) · (0.5 + pe_pct(fin, c)) · (1 + 0.3·nuevo) / (1 + t/60)
agregar el candidato de mayor ganancia; detenerse si no hay ninguno factible
```

La ganancia premia valor, coherencia aprendida de las rutas oficiales (enlace), tramos nuevos y cercanía (la
penalización por tiempo es suave: 1 hora de tramo divide la ganancia entre 2).

**Mejora 2-opt (una pasada, ancla fija):** se prueban todas las inversiones de segmento `ruta[i..j]` con
`1 ≤ i < j`; se queda la mejor que mantenga todos los tramos ≤ 75 min y **reduzca** el recorrido total.

### 16.5 Evaluación y restricciones duras

Una ruta es **factible** si:

| Restricción | Valor |
|---|---|
| Paradas | entre **3 y 6** (incluida el ancla) |
| Tramo máximo | **75 min** estimados |
| Recorrido máximo | **240 min** estimados de traslado |
| Inicio | un **ancla**; ninguna otra parada es ancla |
| Emergentes | **≥ 2** paradas (sin contar el ancla) con bandera activa |
| Tema | todas las paradas no ancla con el tema **presente** (§16.2) |

### 16.6 Puntaje de una ruta factible

```
meses_comunes = meses donde al menos max(2, ⌈0.6 · n_paradas⌉) paradas (incluida el ancla) tienen mes fuerte
enlace_medio  = promedio de pe_pct de sus tramos
tramos_nuevos = fracción de tramos que no existen en rutas oficiales

puntaje = Σ_{paradas no ancla} valor(m, t)
        × (0.7 + 0.3 · enlace_medio)
        × (1 + 0.2 · tramos_nuevos)
        × (1 + 0.1 · [hay al menos un mes común])
        × especificidad(t)
        − 0.15 · recorrido / 240
```

**Especificidad del tema** (un tema raro distingue y vende más que uno casi universal):

```
especificidad(t) = 0.85 + 0.30 · (1 − (n_t − n_min) / (n_max − n_min))
n_t = número de municipios con el tema presente
```

Va de **×0.85** (tema más común, gastronomía) a **×1.15** (tema más raro).

> La temporada compartida es un **bono** de +10 %, no una restricción (el diseño la planteaba como restricción).

### 16.7 Región beneficiada de la ruta

```
región(ruta) = la región más frecuente entre las paradas NO ancla
```

Es donde llega el beneficio, no la del ancla: la ruta del mezcal sale de un ancla de Angelópolis pero sus paradas
están en la Mixteca.

### 16.8 Selección de las 5 rutas

Búsqueda **exhaustiva con poda** (DFS) sobre las candidatas factibles ordenadas por puntaje:

```
maximizar  Σ puntaje + 100 · (# regiones beneficiadas distintas) + 1 · (# temas distintos)
sujeto a   solape(A, B) = |A ∩ B| / min(|A|, |B|) ≤ 0.5     para todo par de rutas elegidas
           ≤ 2 rutas por tema
           ≤ 2 rutas por ancla (Puebla y otras anclas pueden ser puerta de entrada de dos rutas)
```

- `BONO_REGION = 100` es mayor que cualquier diferencia posible de puntajes: **una región más siempre gana**
  (criterio lexicográfico: primero descentralizar, luego calidad); `BONO_TEMA = 1` premia la variedad.
- **Poda:** si `suma actual + suma de los mejores puntajes restantes + 101 · 5 ≤ mejor valor`, se corta la rama.
- Solo se registra una combinación cuando tiene exactamente 5 rutas; si no existiera ninguna combinación compatible
  de 5, no se publicaría ninguna (no ocurre en la corrida vigente).

### 16.9 Escritura

- Se borran las propuestas anteriores (evaluación, paradas y rutas con `origen = 'propuesta_modelo'`).
- `dim_ruta`: nombre `"<Tema> · <ancla> → <última> (propuesta i)"`, `tipo = ruta_intermunicipal`,
  `es_monotematica = true`, `version_sk = v2`, `num_municipios`, `duracion_estimada_h`, `descripcion`.
- **Estancia sugerida:** 3 h en el ancla y 2 h en cada emergente.
- `duracion_estimada_h = recorrido/60 + Σ estancias`.
- `fact_ruta_parada`: orden, municipio, eje líder, distancia y tiempo desde la anterior, `es_ancla`,
  `es_emergente` (= tiene bandera), estancia.
- `fact_ruta_evaluacion`: `tiempo_total_min`, `potencial_pred_medio_pct` (promedio del crecimiento predicho de las
  paradas no ancla en su eje líder), `necesidad_social_media`, `num_municipios_emergentes`, `puntaje_total`,
  `modelo_sk` del modelo de crecimiento.
- **Descripción** (explicabilidad): municipios emergentes con sus banderas, minutos de carretera, horas con
  estancias, crecimiento esperado medio a 5 años, % de tramos que no existen en rutas oficiales y meses de temporada
  compartida.
- **Diagnóstico completo** de las 144 combinaciones (factible o no, paradas, emergentes, puntaje, candidatos del
  tema, necesidad social) en `data/derivados/rutas_candidatas.csv`.

### 16.10 Resultado vigente

56 de 144 combinaciones factibles (gastronomía 12, ecoturismo 10, artesanías 9, café 7, mezcal 5, religioso 4,
volcanes 4, flores 4, arqueología 1).

| # | Tema | Recorrido | Min | Puntaje | Novedad |
|---|---|---|---|---|---|
| 1 | ☕ Café | Cuetzalan → Jonotla → Zoquiapan → Zapotitlán de Méndez → Xochitlán de V. Suárez → Zacapoaxtla | 77 | 9.20 | nueva |
| 2 | 🌋 Volcanes | San Pedro Cholula → San Jerónimo Tecuanipan → Nealtican → Calpan → Tochimilco → Atzitzihuacán | 99 | 8.29 | nueva |
| 3 | 🍲 Gastronomía | Cuetzalan → Jonotla → Huehuetla → Olintla → Jopala → Zihuateutla | 86 | 8.06 | nueva |
| 4 | 🌲 Ecoturismo | San Andrés Cholula → Nealtican → Calpan → San Nicolás de los Ranchos → Atzitzihuacán → Huaquechula | 132 | 6.87 | parcialmente existente |
| 5 | 🥃 Mezcal | San Andrés Cholula → Huehuetlán el Grande → Tzicatlacoyan → Tecali de Herrera → Molcaxac → Ixcaquixtla | 189 | 6.44 | parcialmente existente |

### 16.11 Validación cruzada con carretera real (hallazgo)

Las rutas se pueden recorrer por carretera real con OSRM en el tablero. Hallazgo: `tiempo_min_est` (1.8 min/km en
línea recta) **subestima la sierra**; una versión anterior de la ruta del café (Xicotepec → Naupan) eran 2.3 h
estimadas contra **5.8 h** por carretera (227 km). **Mejora pendiente:** recalcular `fact_accesibilidad` con OSRM y
volver a correr el optimizador con el límite de 75 min sobre tiempos reales.

---

## 17. Clasificación de novedad

Vista `dw.v_novedad_ruta` (`DDL/03_ddl_prediccion_mopedetu.sql`). Para cada ruta:

```
tramos                 = pares consecutivos (a < b) de la ruta
tramos_existentes      = cuántos están en v_pares_rutas_existentes (84 tramos oficiales)
pct_tramos_existentes  = 100 · tramos_existentes / tramos
pct_municipios_en_rutas_existentes = 100 · paradas que aparecen en alguna ruta oficial / paradas

clasificacion_novedad =
    'existente'               si la ruta es del catálogo oficial
    'nueva'                   si ningún tramo coincide con una ruta oficial
    'existente'               si todos los tramos coinciden
    'parcialmente_existente'  en otro caso
```

**V7 (criterio):** al menos 1 ruta *nueva* y 1 *parcialmente existente*. **Resultado: 3 nuevas y 2 parcialmente
existentes** ✅. Una ruta parcialmente existente que extiende un circuito oficial a municipios emergentes también
es un resultado valioso (por ejemplo, la del mezcal extiende la Ruta del Mezcal Legado de la Mixteca hasta
Ixcaquixtla).

**Regla:** ninguna ruta se presenta como "nueva" sin pasar por esta vista.

---

## 18. Escenario de concentración (HHI)

Código: `model/escenario_hhi.py` → `data/derivados/escenario_concentracion.json`. **Validación V8.**

| Escenario | Personal por municipio × eje |
|---|---|
| **Hoy** | `personal_est` DENUE 05/2026 (4 ejes) |
| **Tendencial a 5 años** | `personal_est × (1 + crecimiento_pred_pct / 100)` |
| **Con rutas (hipotético)** | en los **20 municipios emergentes** de las 5 rutas: `personal_est × (1 + intervalo_sup_pct / 100)`; en el resto, el tendencial |

Se suma por municipio y se calcula HHI y % del top 5.

| Escenario | HHI | Top 5 |
|---|---|---|
| Hoy | 1,306 | 51.9 % |
| Tendencial | 1,132 | 49.1 % |
| Con rutas (hipotético) | 1,103 | 48.5 % |

**Supuesto declarado:** los emergentes de las rutas alcanzan el **límite superior del intervalo de 80 %** de su
crecimiento predicho. Se presenta como escenario con supuesto, **no** como predicción del efecto de las rutas.

---

## 19. Motor del tablero: índice, escenarios, rutas y circuitos en vivo

Código: `dashboard/motor.py` sobre los datos DEMO de `dashboard/datos.py`. Todo se recalcula en milisegundos en
cada interacción. **Es un modelo sustituto con datos simulados**: sirve para demostrar la interacción y comparar
alternativas, no para dar cifras reales.

### 19.1 Datos DEMO relevantes para las fórmulas

- `menciones_10k` (visibilidad), `inversion_reciente_mdp`, `crecimiento_hist`, `pct_via_pavimentada`,
  `indice_marginacion` en [0, 1] (**mayor = más marginado**, al revés que CONAPO) y `min_a_ancla` desde la matriz
  DEMO (`haversine × 1.35 / velocidad`, 42 km/h en sierra y 58 km/h fuera).
- Nivel DEMO por CL: ≤ 1 Baja, 1-1.5 Media, > 1.5 Alta.

### 19.2 Scores (por municipio × actividad)

```
s_oferta        = pct( ln(1 + PO) · min(CL, 4) )
s_visibilidad   = pct( menciones por 10 mil habitantes )
s_inversion     = pct( inversión reciente / población )          (se calcula, no entra al índice)
s_accesibilidad = clip(1 − min_a_ancla / 240, 0, 1)
s_social        = indice_marginacion
s_barrera       = 1 − pct_via_pavimentada
```

### 19.3 Escenarios

| Escenario | Inversión extra | Visibilidad extra | Inversión reciente cuenta |
|---|---|---|---|
| Tendencial | 0 | 0 | no |
| Con inversión reciente 2024-25 | 0 | 0 | **sí** |
| Con inversión simulada | `monto × PO / Σ PO` entre el **destino** | 0 | no |
| Con promoción y rutas | 0 | `promo/100 × (1 − s_visibilidad)` | no |
| Combinado | ambas | ambas | **sí** |

Destino de la inversión simulada: *municipios con flag* (CL ≥ 1.5, visibilidad ≤ 0.35, no ancla), *región
seleccionada*, *destinos consolidados* (anclas) o *todos*.

**Crecimiento anual sustituto** (en lugar de LightGBM):

```
g = 0.012
  + 0.045 · s_oferta · (1 − s_visibilidad) · 0.8          (oferta invisible crece más)
  + 0.015 · s_accesibilidad
  − 0.012 · s_barrera
  + 0.5 · clip(crecimiento_hist, −0.05, 0.08) · 0.4        (inercia)
  [+ 0.012 · ln(1 + inversión_reciente) / ln(51)]          (si cuenta la inversión reciente)
  + 0.025 · ln(1 + inversión_extra) / ln(51)
  + 0.06 · visibilidad_extra · s_oferta
g = clip(g, −0.04, 0.25)

PO_proyectado = PO · (1 + g)^h
banda         = 0.012 + 0.008 · h
p10 / p90     = PO · (1 + g ∓ banda)^h
s_crecimiento = pct(g)
```

### 19.4 Índice DEMO con enfoques

```
índice = w1·s_oferta + w2·s_crecimiento + w3·(1 − s_visibilidad) + w4·s_accesibilidad + w5·s_social − w6·s_barrera
índice = clip(índice, 0, 1)
```

| Enfoque | oferta | crecimiento | baja visibilidad | accesibilidad | social | barrera (resta) |
|---|---|---|---|---|---|---|
| Balanceado | .25 | .20 | .20 | .15 | .15 | .05 |
| Económico | .35 | .35 | .10 | .15 | .03 | .02 |
| Social | .15 | .10 | .15 | .10 | .45 | .05 |
| Descentralización | .20 | .10 | .35 | .25 | .05 | .05 |

La gráfica de cascada "¿Por qué?" de la Ficha municipal muestra exactamente estos sumandos.

**Flags DEMO** (con `alto_cl = CL ≥ 1.5`, `alta_oferta = s_oferta ≥ 0.6`, `baja_vis = s_visibilidad ≤ 0.35`):

| Flag | Regla |
|---|---|
| `OFERTA_INVISIBLE` | alto_cl **y** alta_oferta **y** baja_vis **y** no ancla |
| `OFERTA_SIN_INVERSION` | alto_cl **y** s_oferta ≥ 0.75 **y** inversión reciente = 0 |
| `INVERSION_SIN_RETORNO` | inversión ≥ P60 de las inversiones positivas **y** crecimiento histórico < 0 |
| `ACCESIBLE_NO_EXPLOTADO` | ≤ 60 min de un ancla **y** baja_vis **y** CL ≥ 1 **y** no ancla |
| `BARRERA_INFRAESTRUCTURA` | alto_cl **y** vía pavimentada < 50 % |
| `IMPACTO_SOCIAL` | (OFERTA_INVISIBLE **o** ACCESIBLE_NO_EXPLOTADO) **y** marginación ≥ 0.6 |

`flag_activo` = OFERTA_INVISIBLE **o** ACCESIBLE_NO_EXPLOTADO **o** OFERTA_SIN_INVERSION.

**Resumen por municipio:** la actividad con mayor índice es la **líder** y su índice es el del municipio;
`crecimiento_pct = PO_proyectado / PO_actual − 1`.

### 19.5 Concentración en el tablero

- HHI = Σ s² (mostrado × 10,000), curva de Lorenz y **Gini** = 1 − 2·∫Lorenz.
- **Efecto de rutas (Panorama):** el personal proyectado de cada parada no ancla se multiplica por
  `1 + 0.18 · score_norm` de su ruta. Escenario ilustrativo.
- **Simulador:** compara tendencial contra combinado con los supuestos del usuario: empleos adicionales, municipios
  con +1 % o más, empleos por cada 10 MDP, HHI y % del beneficio fuera de anclas.

### 19.6 Rutas DEMO (Panorama y Ficha municipal)

**Nodos:** filas con CL ≥ 1; por municipio, `score = máx índice + 0.05 · (min(# actividades, 4) − 1)`, `flag` =
alguna activa, `social` = marginación.

**Presupuesto:** `días × 9 h × 60 min` (días de la barra lateral, por defecto 2).

**Anclas DEMO:** 9 (Puebla, San Pedro y San Andrés Cholula, Atlixco, Cuetzalan, Zacatlán, Chignahuapan, Tehuacán,
Xicotepec). Con región elegida: nodos de esa región más las anclas; anclas de la región o, si no hay, las 2 más
cercanas a su centro.

**Construcción desde cada ancla** (3 variantes; la 2.ª y 3.ª prohíben como segunda parada las ya usadas desde esa
ancla):

```
estancia: 180 min en ancla, 150 min en el resto;  usado = 180
mientras paradas < 6:
    viaje = tiempo(actual, candidato);  costo = viaje + 150
    factible si usado + costo ≤ presupuesto, viaje ≤ 150 min y no elegido (y no es ancla)
    valor = score + 0.15·flag + 0.1·social
    elegir el máximo de valor / costo^0.6
si hay menos de 3 paradas → descartar
2-opt iterativo (hasta que no haya mejora) con el ancla fija
minutos = Σ viajes + Σ estancias
score_ruta = Σ score (sin ancla) + 0.1 · promedio(social)
```

**Filtros:** al menos `min_emergentes` paradas no ancla (barra lateral, por defecto 2); orden por score; primero la
mejor de cada ancla y luego el resto; sin duplicados por conjunto de municipios; máximo 8; `score_norm = score /
máx`.

**Nombre y tema:** se cuentan las actividades de las paradas; si una tiene ≥ 60 % → "Ruta del <tema> · <región>",
si no → "Ruta Mixta: A + B · <región>" (región más frecuente entre las paradas no ancla).

### 19.7 Arma tu ruta (desde cualquier municipio)

- **Automáticas:** la misma construcción de §19.6 desde el municipio elegido, con días (1-4) y máximo de paradas
  (3-8).
- **Yo elijo:** hasta 9 municipios; el orden se optimiza con 2-opt dejando fija la salida.
- Sin municipios alcanzables (≤ 2.5 h entre sí) se avisa y se sugiere más días o más actividades.

### 19.8 Agenda por días (Rutas del modelo y Arma tu ruta)

```
jornada de 9:00 a 19:00
llegada = reloj + traslado (OSRM real o estimado)
si llegada + estancia > 19:00  →  día siguiente, llegada = 9:00 + traslado
reloj = llegada + estancia
```

Estancias: en *Rutas del modelo*, la sugerida por el optimizador (3 h ancla, 2 h emergente); en *Arma tu ruta*,
3 h en destinos consolidados y 2.5 h en el resto.

### 19.9 Circuitos municipales

```
puntos = puntos de interés del municipio (filtrados por actividades; "una actividad" = la de más puntos)
ordenados por valoración
inicio = cabecera; restante = horas × 60
mientras haya puntos:
    viaje = haversine × 1.4 / velocidad × 60        (velocidad: 25 km/h en auto, 4.5 km/h a pie)
    penalización = 8 min × veces que ya se visitó esa actividad     (solo en circuito variado)
    costo = viaje + 60 min de visita
    factible si costo ≤ restante
    elegir el mínimo de viaje + penalización (vecino más cercano con diversidad)
```

- Si el filtro de actividades deja el municipio vacío en modo variado, se repite con todas sus actividades y se
  avisa.
- Con los tiempos reales por calle (OSRM) se recalcula el horario (1 h por parada desde las 9:00) y se **advierte**
  si la duración real supera en más de 15 % las horas elegidas.

**Potencial de circuito** (ranking de sugerencias):

```
potencial = 0.6 · índice medio del municipio + 0.4 · min(# actividades, 5) / 5
```

### 19.10 Ruta por carretera real (OSRM)

- Servidores: `routing.openstreetmap.de` (auto y a pie) y `router.project-osrm.org` (respaldo auto); *timeout* 8 s;
  caché 24 h.
- Si ninguno responde: tramos rectos con los tiempos estimados, y la página lo declara ("Sin conexión al servicio
  de rutas: distancias en línea recta").

---

## 20. Validaciones V1 a V9 y controles de calidad de datos

### 20.1 Validaciones del modelo

| # | Validación | Criterio de aceptación | Resultado | Estado |
|---|---|---|---|---|
| **V1** | Cobertura: los 217 municipios tienen A0, A2 y A4 | 100 % | 100 % | ✅ |
| **V2** | Coherencia de anclas | Diseño: ≥ 11 de 12 con turismo actual 🔴 o 🟡. Código: intensidad ≥ P50 sin forzar el color | 12 / 12 | ✅ |
| **V3** | El DENUE detecta la actividad en los municipios de su ruta oficial | Se reporta; la brecha se trata como oferta reconocida sin registro | Café 66 % (19/29), mezcal 50 % (6/12); se convierte en bandera `OFERTA_INVISIBLE` | ✅ reportado |
| **V4** | El modelo de crecimiento gana a sus líneas base | Rol C: menor MAE que media del eje y Ridge. Rol B: mayor Spearman y precisión ≥ que todas las líneas base en la prueba temporal | Rol C gana en MAE, Spearman y top 20 %. Rol B gana en Spearman y top 20 (MAE: Ridge 0.322 es algo mejor que gbm 0.327) | ✅ |
| **V5** | El modelo de enlaces gana a la distancia | AUC > línea base de distancia, validado por ruta | AUC 0.881 vs 0.856; AP 2.3× | ✅ |
| **V6** | Sensibilidad del índice | ±20 % en cada peso; el top 20 conserva ≥ 70 % de sus municipios | — | ⏳ pendiente |
| **V7** | Novedad de las rutas | ≥ 1 nueva y ≥ 1 parcialmente existente | 3 nuevas, 2 parcialmente existentes | ✅ |
| **V8** | Descentralización | HHI hoy vs escenario con rutas, presentado como hipotético | 1,306 → 1,132 → 1,103 | ✅ |
| **V9** | Proxy de turismo contra DATATUR | Spearman ≥ 0.6 en destinos con datos | — | ⏳ pendiente |

### 20.2 Controles de calidad de los datos

| Control | Criterio | Resultado |
|---|---|---|
| Totales del CE contra INEGI | Coincidir con los totales estatales publicados | 1,117,993 (2019) y 1,251,065 (2024) ✅ |
| Marginación CONAPO vs índice de carencias propio | Concordancia fuerte | Spearman −0.914 ✅ |
| Accesibilidad nueva vs filas previas | Diferencias pequeñas | 0.67 km de diferencia media; colindancia 100 % ✅ |
| Regiones | Cubrir exactamente 217 municipios | ✅ (el script falla si no) |
| `dim_municipio` | 217 filas, `cve_geo ~ '^21[0-9]{3}$'` | ✅ (restricción CHECK) |
| Marco geoestadístico | 217 municipios de la entidad 21 | ✅ (`cargar_mun_geo.py` lo exige) |
| Suma de pesos por SCIAN | Revisar SCIAN con suma ≠ 1 | Consulta 7.3 de `02_etl` |
| Establecimientos sin coordenadas | Contar | Consulta 7.4 |
| Municipios sin oferta turística | Revisar si es dato o faltante | Consulta 7.5 |
| Tamaño de la base | < 500 MB | Consulta 7.2 |
| Rangos de personal sin *match* | Diagnóstico del paso 3 del ETL | Consulta comentada en `02_etl` |
| Restricciones de dominio | Scores e índice en [0, 1], niveles y semáforos en listas cerradas, `municipio_a < municipio_b` | `CHECK` del DDL |

### 20.3 Validación de establecimientos de OSM que faltan en el DENUE

`scripts/buscar_osm_nuevos.py` compara cada POI de OSM con nombre contra el **DENUE completo** (todos los
sectores):

| Caso | Regla |
|---|---|
| Ya está en el DENUE | similitud de nombre ≥ 0.85 a < 1 km, **o** ≥ 0.75 a < 300 m, **o** ≥ 0.6 a < 40 m |
| Dudoso (revisión manual) | sin *match* pero similitud ≥ 0.5 con algo a < 150 m |
| Nombre genérico ("Taquería", "Motel") | existente si hay un establecimiento del mismo subsector a < 75 m; si no, dudoso |
| Nuevo | el resto |

Resultado: 821 nuevos, dudosos y descartados en `data/processed/`. **No se cargan aún** a la base.

### 20.4 Pruebas del software

`tests/test_tablero.py`: las 7 páginas DEMO en 4 configuraciones y la ficha técnica real en 6 municipios con cada
semáforo, sin excepciones (prueba de humo, no de valores).

---

## 21. Reglas de corte

| Situación | Qué se hace |
|---|---|
| El modelo de crecimiento (rol C) no gana en MAE a sus líneas base | Se publica la predicción de Ridge |
| El modelo del rol B no supera a las líneas base | No se usa ese modelo |
| `gbm_ue` (celdas confidenciales) no supera a las líneas base | Esas celdas quedan **sin predicción** |
| La predicción no llega a tiempo | El índice se queda en `v1_base` y el optimizador sigue con v1 |
| Una ruta no tiene 3 paradas o 2 emergentes | Se descarta (queda en el diagnóstico como no factible) |
| `dim_modelo` rechaza el registro | Se guarda en `data/derivados/pendientes/` y el script sigue |
| Catálogo de rutas existentes pequeño | Se usa igual para medir novedad, declarando su cobertura |
| Espacio en la base cerca de 500 MB | Vaciar `stg.denue` (se conserva el CSV local) |
| Sin conexión a OSRM | Tramos rectos con tiempos estimados, declarado en pantalla |
| Sin `.env` | Las páginas de datos reales muestran un error claro; las DEMO siguen funcionando |

---

## 22. Tabla maestra de parámetros

| Parámetro | Valor | Dónde |
|---|---|---|
| Minutos por km en línea recta | 1.8 | `cargar_datos_base.py`, `calcular_ficha.py` |
| Margen de colindancia | 0.001° (~100 m) | ídem |
| Puntos medios del estrato | 2.5 / 8 / 20.5 / 40.5 / 75.5 / 175.5 / 300 | `dim_estrato_personal`, `actividades.py` |
| Nivel muy alta / alta / media | CL ≥ 2 y ≥ 3 u · CL ≥ 1.25 y ≥ 2 u · CL ≥ 0.75 | `actividades.py`, `cargar_datos_base.py` |
| Puntaje de actividad | 0.5 CL · 0.3 volumen · 0.2 catálogo | `calcular_actividades.py` |
| Score solo catálogo | arqueología 0.9 · religioso 0.6 | ídem |
| Actividades principales | top 3 y nivel ≠ baja | ídem |
| Índice de infraestructura | 0.35 / 0.25 / 0.20 / 0.10 / 0.10 | `calcular_ficha.py` |
| Umbrales infraestructura | 0.35 · 0.6 | ídem |
| Intensidad turística | 0.40 / 0.25 / 0.15 / 0.20 | ídem |
| Umbrales turismo actual | P50 · P85 (ancla siempre rojo) | ídem |
| Umbrales social (respaldo) | P40 · P60 | ídem |
| Índice v1 | 0.35 / 0.15 / 0.25 / 0.25 | `dim_version_calculo` |
| Índice v2 | 0.25 / 0.10 / 0.25 / 0.20 / 0.20 | ídem |
| Sub-pesos de oferta | 0.6 CL · 0.4 personal | `indice.py` |
| Sub-pesos de complementarios | 0.4 otros ejes · 0.3 atractivos · 0.3 actividades | ídem |
| Sub-pesos de accesibilidad | 0.7 ancla · 0.3 vías | ídem |
| `OFERTA_EMERGENTE` | CL ≥ 1.25, ≥ 3 unidades | ídem |
| `ACCESIBLE_NO_EXPLOTADO` | ≤ 60 min, oferta < 0.4, complementarios ≥ 0.5 | ídem |
| `BARRERA_ACCESO` | oferta ≥ 0.6 y (> 75 min o vías < P25 y > 45 min) | ídem |
| Filtro de casos (crecimiento C) | UE ≥ 3 en 2019 o 2024 | `crecimiento.py` |
| Horizonte | 5 años | ídem |
| LightGBM crecimiento | 400 árboles, lr 0.03, 15 hojas, min 12, sub 0.8, col 0.8, λ 1 | ídem |
| Validación crecimiento C | GroupKFold 5 por municipio | ídem |
| Intervalo conformal | percentil 80 del error absoluto | ídem |
| Ridge línea base | α = 3 | ídem |
| HistGB rol B | profundidad 3, lr 0.05, 250 iteraciones, hoja ≥ 20, L2 1 | `prediccion_crecimiento.py` |
| Top K rol B | 20 | ídem |
| Bloques de perfil | 1.0 / 0.8 / 0.35 / 0.5 | `enlaces.py` |
| Universo de pares | ≤ 150 min | ídem |
| k de clusters | 5-9 por silueta (→ 5) | ídem |
| LightGBM enlaces | 300 árboles, lr 0.03, 15 hojas, min 10, balanced | ídem |
| Validación enlaces | StratifiedGroupKFold 5 por ruta | ídem |
| Paradas por ruta | 3-6 | `rutas.py` |
| Tramo máximo / recorrido máximo | 75 / 240 min | ídem |
| Emergentes mínimos | 2 | ídem |
| Bonos del valor | bandera 0.35 · social 0.40 · tema 0.25 | ídem |
| Ganancia de inserción | (0.5 + enlace) · (1 + 0.3 nuevo) / (1 + t/60) | ídem |
| Puntaje de ruta | (0.7 + 0.3 enlace) · (1 + 0.2 nuevos) · (1 + 0.1 temporada) · especificidad − 0.15 · min/240 | ídem |
| Especificidad | 0.85 a 1.15 | ídem |
| Mes común | ≥ max(2, ⌈0.6 n⌉) paradas | ídem |
| Selección | 5 rutas, solape ≤ 50 %, ≤ 2 por tema, ≤ 2 por ancla, bono región 100, bono tema 1 | ídem |
| Estancia sugerida | 3 h ancla · 2 h emergente | ídem |
| Escenario con rutas | límite superior del intervalo en los emergentes | `escenario_hhi.py` |
| DEMO: presupuesto de ruta | días × 9 h | `motor.py` |
| DEMO: estancia | 180 min ancla · 150 min resto | ídem |
| DEMO: viaje máximo entre paradas | 150 min | ídem |
| DEMO: efecto de rutas | +18 % × score_norm | ídem |
| DEMO: circuito | 1 h por parada, rodeo × 1.4, 25 km/h auto, 4.5 km/h a pie, penalización 8 min | ídem |
| DEMO: potencial de circuito | 0.6 índice + 0.4 diversidad | ídem |
| Agenda | 9:00 a 19:00 | `vistas/rutas.py` |

---

## 23. Riesgos metodológicos detectados en el código

Se documentan para que nadie los descubra en la presentación:

1. **Variables estáticas en el modelo de crecimiento (rol C).** Infraestructura (vías 2026, minutos al ancla),
   atractivos, número de rutas oficiales y la marca de **ancla** son actuales y se usan igual para el año base 2019
   y para 2024. Solo el Pueblo Mágico se filtra por año. Es una fuga leve de información (el estado actual podría
   reflejar parte del crecimiento pasado) que no invalida el orden, pero conviene declararla.
2. **Validación no temporal en el modelo de producción.** La validación del rol C es entre municipios (no en el
   tiempo); el rol B sí tiene validación temporal, pero con 2019 → 2024 atravesado por la pandemia.
3. **Predicción sobre bases cero.** El modelo del rol C predice las 868 celdas, incluidas las de base nula o
   mínima, que dan porcentajes muy altos. Mitigación: ponderación por `personal_base` en el semáforo y lectura como
   ranking.
4. **Tiempos estimados en línea recta** que subestiman la sierra (§16.11); afectan los límites de 75 y 240 min.
5. **Sesgo del modelo de enlaces** hacia cómo la Secretaría arma sus rutas (anclas y municipios conocidos).
6. **Anclas y regiones distintas** entre el modelo del rol B / modo DEMO (9 anclas, región aproximada) y la base
   (12 anclas, 7 regiones oficiales).
7. **2-opt de una pasada** en `rutas.py` (una sola mejor inversión), frente al 2-opt iterativo del motor DEMO.
8. **Meses fuertes con actividades de intensidad 1** (palenques todo el año) en el perfil y en las rutas; la vista de
   la ficha sí exige intensidad ≥ 2.
9. **V6 y V9 sin ejecutar.**

---

## 24. Lo que no se afirma

- Que el modelo mide visitantes o derrama: mide **oferta** (establecimientos y empleo) y usa proxies de demanda.
- Que una ruta "garantiza" derrama o "optimiza flujos": es una **hipótesis de trabajo** que hay que validar con las
  comunidades.
- Que el escenario con inversión o con rutas es causal: es una **simulación basada en correlaciones** con su
  supuesto explícito.
- Que una ruta es nueva sin haberla comparado con el catálogo oficial.
- Que el semáforo rojo es malo: significa "ya concentra turismo".
- Que el crecimiento predicho es un compromiso: es un **escenario tendencial** con intervalo.
