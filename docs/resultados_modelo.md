# MOPEDETU · Modelo predictivo: piezas, resultados y validación

Todo vive en Supabase (`dw`) y se regenera con:

```
python model/indice.py        # 1. índice v1 + banderas
python model/crecimiento.py   # 2. modelo de crecimiento + índice v2
python model/enlaces.py       # 3. perfiles, clusters, similitud, modelo de enlaces
python model/rutas.py         # 4. optimizador de rutas
python model/escenario_hhi.py # V8. concentración hoy / tendencial / hipotético
```

Los datos de entrada están en `docs/datos_base.md`. Las piezas comparten `model/base.py`, así que todas leen exactamente los mismos datos.

---

## 1. Índice de oportunidad (`fact_indice_oportunidad`, `fact_flag_oportunidad`)

`índice = 0.35·oferta + 0.15·complementarios + 0.25·accesibilidad + 0.25·social` (versión `v1_base`). Se calcula por municipio × eje, y todos los componentes son percentiles estatales:

| Componente | Cálculo |
|---|---|
| oferta | 0.6·percentil del cociente de localización del eje + 0.4·percentil del log del personal (DENUE) |
| complementarios | Otros ejes + atractivos (OSM, INAH) + número de actividades presentes |
| accesibilidad | Minutos al ancla más cercana (70 %) + densidad de vías principales (30 %) |
| social | Marginación CONAPO 2020: más marginación, más prioridad |

**Versión `v2_con_prediccion`:** usa los pesos 0.25 / 0.10 / 0.25 / 0.20 y agrega 0.20 de **potencial predicho**, que es el percentil del crecimiento esperado dentro del eje.

**Banderas** (v2: 385 activas en 131 municipios), cada una con su motivo en texto:

| Bandera | Regla |
|---|---|
| OFERTA_EMERGENTE | Cociente de localización ≥ 1.25 y ≥ 3 establecimientos en el eje, sin ser ancla ni Pueblo Mágico |
| ACCESIBLE_NO_EXPLOTADO | ≤ 60 min de un ancla, con atractivos y actividades pero poca oferta del eje (< P40) |
| BARRERA_ACCESO | Oferta alta (≥ P60) pero a > 75 min de un ancla (el tramo máximo de una ruta) |
| OFERTA_INVISIBLE (nueva) | Actividad reconocida en una ruta oficial sin ningún registro en el DENUE |
| IMPACTO_SOCIAL | Cualquiera de las anteriores en un municipio con grado de marginación alto o muy alto |

Mejores oportunidades fuera de las anclas: Jonotla, Huehuetla, Jalpan, Zacapoaxtla, Zapotitlán de Méndez, Huehuetlán el Grande, Pantepec…

## 2. Modelo de crecimiento (`dim_modelo` #141, `fact_prediccion_crecimiento`)

- **Objetivo:** crecimiento logarítmico de las **unidades económicas turísticas** por municipio × eje.
  - Se usan unidades y no personal ocupado porque INEGI oculta el personal por confidencialidad en la mayoría de los municipios pequeños: solo 136 de 868 casos lo tenían en ambos censos. Las unidades nunca se ocultan, y así se usan 482 casos.
- **Entrenamiento:** transición CE 2019 → CE 2024, con variables medidas en 2019.
  - No se usa el DENUE 2026.
  - Los Pueblos Mágicos solo cuentan si ya lo eran en 2019.
- **Predicción:** 2024 → 2029, aplicando el modelo a las mismas variables medidas en 2024.
- **Validación:** GroupKFold de 5 particiones por municipio. Un municipio nunca está a la vez en entrenamiento y prueba.

| Modelo | MAE | Spearman | Precisión top 20 % |
|---|---|---|---|
| **LightGBM** | **0.246** | **+0.476** | **54 %** |
| Línea base: media del eje | 0.273 | +0.333 | 34 % |
| Línea base: Ridge | 0.283 | +0.329 | 45 % |

- **Intervalo conformal de 80 %:** cobertura medida del 80 %.
- **Explicabilidad (SHAP):** oferta actual del eje (16 %), eje (9 %), especialización (7 %), tamaño medio (6 %), población (6 %), oferta de los municipios vecinos (6 %).
- **Líneas base:** registradas en `dim_modelo` con `tarea = 'linea_base'`.

## 3. Perfiles, clusters y enlaces (`fact_cluster_municipio`, `fact_similitud`, `dim_modelo` #144, `fact_prediccion_enlace`)

- **Perfil por municipio:** 14 actividades, 4 ejes, 12 meses de temporada, intensidad turística, marginación y accesibilidad.
- **Similitud:** coseno de los perfiles para 8,452 pares a ≤ 150 min.
- **Clusters:** 5 grupos (k elegido por silueta):

  | Cluster | Municipios |
  |---|---|
  | Café + alta marginación (Sierra Norte) | 36 |
  | Gastronomía tradicional (Mixteca) | 89 |
  | Turismo religioso y museos: destinos consolidados (Angelópolis) | 8 |
  | Artesanías + alta marginación (Mixteca) | 62 |
  | Mezcal y ecoturismo | 22 |

- **Modelo de enlaces:** aprende cuándo dos municipios forman un tramo de ruta. Los positivos son los 79 tramos de las rutas oficiales dentro del universo de pares.
- **Validación:** StratifiedGroupKFold agrupado por ruta.
  - Primero se usó GroupKFold, pero juntaba las 29 rutas en una sola partición y dejaba otra sin positivos para entrenar. Se corrigió.

| Modelo | AUC | Precisión media (AP) |
|---|---|---|
| **LightGBM** | **0.881** | **0.096** |
| Línea base: solo distancia | 0.856 | 0.042 |
| Línea base: solo similitud | 0.699 | 0.019 |

La tasa base es 0.93 %. **SHAP:** distancia (30 %), turismo actual de los dos municipios (25 %), actividades compartidas (9 %), atractivos (7 %).

## 4. Rutas propuestas (`dim_ruta` origen `propuesta_modelo`, `fact_ruta_parada`, `fact_ruta_evaluacion`)

**Restricciones:**
- 3 a 6 paradas, tramos ≤ 75 min y recorrido ≤ 240 min.
- Empieza en un ancla y lleva ≥ 2 municipios con bandera.
- Tema con presencia fuerte (alta, muy alta o reconocida).
- Dos rutas no comparten más del 50 % de sus municipios; máximo 2 rutas por tema y 2 por ancla.

**Selección:**
- Búsqueda exhaustiva de la mejor combinación de 5 rutas.
- Criterio lexicográfico: primero el **número de regiones beneficiadas** distintas y después la calidad.
- La región de una ruta es la que predomina entre sus paradas (donde llega el beneficio), no la del ancla.
- **Especificidad del tema:** un tema distintivo (mezcal, café, volcanes) vale hasta ×1.15; uno casi universal (gastronomía tradicional), ×0.85.
- El tema "comunitario" queda fuera hasta tener un catálogo confiable: la señal por nombre ("cooperativa", "ejido") es ruidosa.

| # | Ruta | Recorrido | Región beneficiada | Novedad |
|---|---|---|---|---|
| 1 | ☕ Café · Xicotepec → Naupan | Xicotepec → Jopala → Zihuateutla → Tlacuilotepec → Tlaxco → Naupan (136 min) | Sierra Norte | nueva |
| 2 | 🏺 Talavera y artesanías · Chignahuapan → Tuzamapan | Chignahuapan → Aquixtla → Zautla → Zacapoaxtla → Jonotla → Tuzamapan de Galeana (174 min) | Sierra Nororiental | nueva |
| 3 | 🌋 Volcanes · San Pedro Cholula → Huaquechula | Cholula → Nealtican → Calpan → Tochimilco → Atzitzihuacán → Huaquechula (116 min) | Valle de Atlixco y Matamoros | parcialmente existente (20 %) |
| 4 | ⛪ Conventos · Puebla → Tecamachalco | Puebla → Cuautinchán → Tecali de Herrera → Acatzingo → Quecholac → Tecamachalco (150 min) | Valle de Serdán | parcialmente existente (60 %) |
| 5 | 🥃 Mezcal · Puebla → Ixcaquixtla | Puebla → Huehuetlán el Grande → Tzicatlacoyan → Tecali de Herrera → Molcaxac → Ixcaquixtla (180 min) | Mixteca | parcialmente existente (40 %): extiende la Ruta del Mezcal Legado de la Mixteca hasta Ixcaquixtla |

Las rutas benefician a 4 regiones distintas y llevan de 4 a 5 municipios emergentes cada una. Cada ruta tiene en `descripcion` el porqué: banderas, crecimiento esperado, tramos nuevos y temporada compartida. El diagnóstico de todas las candidatas (ancla × tema) está en `data/derivados/rutas_candidatas.csv`.

## Validaciones (docs/modelo_predictivo_anillos.md §5)

| # | Validación | Resultado |
|---|---|---|
| V1 | Cobertura A0, A2 y A4 en 217 municipios | ✅ 100 % |
| V2 | Anclas con intensidad turística ≥ P50 (sin forzar) | ✅ 12/12 |
| V3 | El DENUE detecta la actividad en los municipios de su ruta oficial | Café 66 %, mezcal 50 %. La brecha es la bandera OFERTA_INVISIBLE (29) |
| V4 | El modelo de crecimiento gana a las líneas base | ✅ En MAE, Spearman y top 20 %. Validación entre municipios y, desde oct-2026, también temporal con el CE 2014 de la serie histórica (Spearman 0.336 vs 0.061 de la media del eje) |
| V5 | El modelo de enlaces gana a la distancia | ✅ AUC 0.881 vs 0.856; AP 2.3× |
| V6 | Sensibilidad del índice a ±20 % en los pesos | ✅ El top 20 conserva 85-100 % (v2) y 95-100 % (v3). Sin el componente de potencial, solo 60 % / 65 %: ese componente pesa mucho en el ranking |
| V7 | Al menos 1 ruta nueva y 1 parcialmente existente | ✅ 3 nuevas, 2 parcialmente existentes (extienden circuitos oficiales a municipios emergentes) |
| V8 | Concentración del turismo | Hoy HHI 1,306 (top 5 = 51.9 %) → tendencial 1,132 (49.1 %) → **con rutas, hipotético** 1,103 (48.5 %). Supuesto: los emergentes de las rutas alcanzan el límite superior de su intervalo |
| V9 | Proxy de turismo contra DATATUR | Pendiente |

## Integración con el trabajo del equipo (merge en `main`)

- **Dos modelos de crecimiento complementarios:**
  - **Rol B (Raúl): `model/prediccion_crecimiento.py`, documentado en `docs/modelo_prediccion.md`.**
    - Predice el **personal ocupado**.
    - Usa CE 2014, 2019 y 2024 de la versión histórica armonizada del CE 2024.
    - Tiene **validación temporal real**: entrena 2014→2019 y prueba 2019→2024.
    - Cubre menos celdas (208 con objetivo observable), por la confidencialidad del personal.
  - **Rol C (este documento): `model/crecimiento.py`.**
    - Predice **unidades económicas**, que nunca se ocultan, con validación agrupada por municipio.
    - Cubre 482 casos y es el que alimenta el índice v2 y las rutas en Supabase.
  - **Siguiente paso:** incorporar la transición 2014→2019 de Raúl al panel de unidades, para tener también validación temporal.
- **Tablero:**
  - La página de Rutas combina **"🧠 Rutas del modelo"**, que lee las rutas reales de Supabase (Rol C), con **"🛠️ Arma tu ruta"** de Raúl.
  - Cada ruta propuesta se puede **recorrer por carretera real** (OSRM) con el navegador satelital de Raúl.
- **Hallazgo al recorrer por carretera real:** los tiempos de `fact_accesibilidad` se estiman con 1.8 min por km en línea recta y **subestiman la sierra**. La primera ruta del café (Xicotepec → Naupan, versión anterior) eran 2.3 h estimadas contra 5.8 h por carretera (227 km). Próxima mejora: recalcular `fact_accesibilidad` con tiempos de OSRM y volver a correr el optimizador con el límite de 75 min por tramo sobre tiempos reales.

## Limitaciones (para el jurado)

- Los datos son de **oferta** (establecimientos y empleo), no de visitantes.
- Hay un solo periodo censal (2019-2024, con la pandemia incluida).
- El modelo de enlaces aprende cómo arma rutas la Secretaría, con sesgo hacia anclas. Por eso el optimizador combina su probabilidad con el índice y las banderas para llevar las rutas a municipios emergentes.
- Las rutas son **hipótesis de trabajo**: el siguiente paso es validarlas con las comunidades.

## Atractivos sin negocio detrás (`dw.fact_atractivo_lugar`, `scripts/cargar_atractivos.py`)

- **Problema:** El Peñón de Jonotla (santuario a la Virgen de Guadalupe tallada en la roca y mirador de 360°) no aparecía. El DENUE solo registra negocios, lo religioso salía únicamente de las rutas oficiales y OSM no tiene el lugar.
- **Solución:**
  - Catálogo curado con fuente (`data/catalogos/atractivos.csv`): 8 lugares de Jonotla y las Cascadas de Zoquiapan.
  - Más 572 atractivos con nombre de OpenStreetMap (santuarios, cascadas, grutas, manantiales, miradores, volcanes, museos y zonas arqueológicas), asignados a su municipio por polígono INEGI.
  - Cuentan como **señal de catálogo** en A1: el curado completo; de OSM solo religioso, ecoturismo y volcanes, para no inflar actividades.
  - La Fiesta de la Virgen del Peñón (22 de octubre) entra en las temporadas.
- **Efecto:**
  - Jonotla pasa a tener turismo religioso y ecoturismo como actividades principales.
  - Es la **oportunidad número 1 del índice** en `v1_base` (0.855) y en `v2_con_prediccion` (0.735); en
    `v3_dominio_osrm` es la número 2 (0.791).
  - Entra en dos de las cinco rutas: café y gastronomía, ambas desde Cuetzalan.
  - La ficha técnica lista sus lugares para visitar.