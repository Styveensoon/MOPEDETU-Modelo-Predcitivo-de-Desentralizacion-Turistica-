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
| **LightGBM** | **0.879** | **0.083** |
| Línea base: solo distancia | 0.856 | 0.042 |
| Línea base: solo similitud | 0.686 | 0.019 |

La tasa base es 0.93 %. **SHAP:** distancia (30 %), turismo actual de los dos municipios (25 %), actividades compartidas (9 %), atractivos (7 %).

## 4. Rutas propuestas (`dim_ruta` origen `propuesta_modelo`, `fact_ruta_parada`, `fact_ruta_evaluacion`)

**Restricciones:**
- 3 a 6 paradas, tramos ≤ 75 min y recorrido ≤ 240 min.
- Empieza en un ancla y lleva ≥ 2 municipios con bandera.
- Tema con presencia fuerte (alta, muy alta o reconocida).
- Dos rutas no comparten más del 50 % de sus municipios.
- Primero una ruta por región; máximo 2 por tema.

| # | Ruta | Recorrido | Novedad |
|---|---|---|---|
| 1 | Gastronomía tradicional · Zacatlán → Jopala | Zacatlán → Zapotitlán de Méndez → Jonotla → Huehuetla → Olintla → Jopala (137 min) | nueva |
| 2 | Café · Tlatlauquitepec → Jonotla | Tlatlauquitepec → Zacapoaxtla → Xochitlán de V. S. → Zapotitlán de Méndez → Zoquiapan → Jonotla (79 min) | nueva |
| 3 | Volcanes y alta montaña · San Pedro Cholula → Huaquechula | Cholula → Nealtican → Calpan → Tochimilco → Atzitzihuacán → Huaquechula (116 min) | parcialmente existente (20 % de tramos) |
| 4 | Gastronomía tradicional · Tehuacán → Zacapala | Tehuacán → San Gabriel Chilac → Zapotitlán → Atexcal → Coyotepec → Zacapala (178 min) | nueva |
| 5 | Turismo comunitario · Atlixco → Acajete | Atlixco → San Salvador el Verde → San Matías Tlalancaleca → Coronango → Amozoc → Acajete (226 min) | nueva |

Las 5 rutas salen de 5 regiones distintas y llevan de 3 a 5 municipios emergentes cada una. Cada ruta tiene en `descripcion` el porqué: banderas, crecimiento esperado, tramos nuevos y temporada compartida.

## Validaciones (docs/modelo_predictivo_anillos.md §5)

| # | Validación | Resultado |
|---|---|---|
| V1 | Cobertura A0, A2 y A4 en 217 municipios | ✅ 100 % |
| V2 | Anclas con intensidad turística ≥ P50 (sin forzar) | ✅ 12/12 |
| V3 | El DENUE detecta la actividad en los municipios de su ruta oficial | Café 66 %, mezcal 50 %. La brecha es la bandera OFERTA_INVISIBLE (29) |
| V4 | El modelo de crecimiento gana a las líneas base | ✅ En MAE, Spearman y top 20 %. Validación entre municipios; no hay segundo periodo temporal porque el CE 2014 no tiene descarga |
| V5 | El modelo de enlaces gana a la distancia | ✅ AUC 0.879 vs 0.856; AP 2× |
| V6 | Sensibilidad del índice a ±20 % en los pesos | Pendiente |
| V7 | Al menos 1 ruta nueva y 1 parcialmente existente | ✅ 4 nuevas, 1 parcialmente existente |
| V8 | Concentración del turismo | Hoy HHI 1,306 (top 5 = 51.9 %) → tendencial 1,132 (49.1 %) → **con rutas, hipotético** 1,093 (48.2 %). Supuesto: los emergentes de las rutas alcanzan el límite superior de su intervalo |
| V9 | Proxy de turismo contra DATATUR | Pendiente |

## Limitaciones (para el jurado)

- Los datos son de **oferta** (establecimientos y empleo), no de visitantes.
- Hay un solo periodo censal (2019-2024, con la pandemia incluida).
- El modelo de enlaces aprende cómo arma rutas la Secretaría, con sesgo hacia anclas. Por eso el optimizador combina su probabilidad con el índice y las banderas para llevar las rutas a municipios emergentes.
- Las rutas son **hipótesis de trabajo**: el siguiente paso es validarlas con las comunidades.
