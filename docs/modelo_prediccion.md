# 📈 Modelo de potencial de crecimiento · MOPEDETU (rol B)

> **Qué responde:** ¿en qué municipios y ejes turísticos crecerá más el personal ocupado en la siguiente etapa censal (2024 → ~2029)?
> **Cómo decirlo en el pitch:** "potencial estimado de crecimiento del empleo turístico", **no** "garantía de crecimiento" ni "visitantes" o "derrama".

---

## 1. Datos

| Insumo | Fuente | Archivo |
|---|---|---|
| Unidades económicas, personal ocupado y valor agregado por municipio y subsector (721, 722, 711, 712, 713 y rama 5615) | INEGI, Censos Económicos 2014, 2019 y 2024. Se usa la **versión histórica del CE 2024**, que homologa las tres ediciones a SCIAN 2023 y a los municipios vigentes | `data/stg/censo_economico.csv` (`scripts/censo_economico.py`) |
| Totales estatales por sector y total de actividades por municipio | Mismos censos | `data/stg/censo_economico_totales.csv` |
| Población total y marginación | CONAPO, Índice de marginación municipal 2020 (población del Censo de Población y Vivienda 2020) | `data/stg/contexto_social.csv` (`scripts/contexto_social.py`) |
| Centroides y anclas turísticas | `data/geo/puebla_municipios.geojson` y la lista de destinos consolidados del tablero | — |

**Confidencialidad:** INEGI oculta el personal y el valor agregado en ~50 % de las celdas municipio × sector, sobre todo en municipios pequeños. Esas celdas se marcan con `confidencial = true` y **no se rellenan**. La ausencia de un sector en un municipio que sí aparece en el censo se toma como cero establecimientos, porque INEGI no publica renglones vacíos.

Sobre la pobreza municipal, la medición más reciente sigue siendo la de 2020. La medición 2024 de INEGI es nacional y estatal, así que no se usa.

## 2. Ejes

| Eje | Subsectores SCIAN |
|---|---|
| `hospedaje` | 721 |
| `alimentos` | 722 |
| `turismo_cultura` | 711, 712, 713 |
| `comercio_turistico` | 5615 (agencias de viajes y reservaciones) |

Si algún sector del eje es confidencial, el personal del eje queda nulo. El mapeo vive en `EJES` dentro de `model/prediccion_crecimiento.py` y debe coincidir con `dim_eje`.

## 3. Panel y variables

- **Panel:** municipio × eje × transición (2014→2019 y 2019→2024). Tiene 574 y 590 celdas con presencia del eje; con objetivo observable hay 214 y 208.
- **Objetivo:** `delta_log = ln(1 + PO_fin) − ln(1 + PO_inicio)`.
- **Variables:** todas se toman **al inicio** de cada transición, para no filtrar información del futuro.
  - Personal y unidades (log).
  - Personal por unidad.
  - Participación en el personal y en las unidades estatales del eje.
  - Valor agregado por trabajador relativo al estado.
  - Cociente de localización por personal y por unidades.
  - Empleo total del municipio.
  - Población y marginación 2020 (estáticas).
  - Distancia al ancla más cercana.
  - Región y eje.

## 4. Validación

- **Temporal:** entrena con 2014→2019 y prueba con 2019→2024.
- **Espacial (adicional):** deja fuera una región completa en cada pliegue, con las dos transiciones.

Las métricas se miden en la prueba temporal, con 208 celdas:

| Modelo | Spearman global | Spearman medio por eje | Precisión top 20 | MAE `delta_log` |
|---|---|---|---|---|
| LB persistencia | −0.171 | −0.267 | 0.05 | 0.482 |
| LB mediana del eje | 0.241 | — | 0.15 | 0.338 |
| LB cociente de localización | −0.304 | −0.396 | 0.05 | — |
| Ridge | 0.254 | 0.160 | 0.20 | **0.322** |
| **Gradient boosting (elegido)** | **0.268** | **0.215** | **0.25** | 0.327 |
| Gradient boosting solo unidades | 0.229 | 0.125 | 0.25 | 0.341 |

- En la validación espacial, el modelo elegido obtiene Spearman 0.378 y precisión top 20 de 0.30.
- **El modelo elegido supera a las tres líneas base** en orden (Spearman) y en precisión top 20. La mejora es **modesta**: sirve para ordenar prioridades, no para dar cifras exactas.
- La persistencia y el cociente de localización tienen **correlación negativa**. Los municipios que más crecieron o que ya están especializados tienden a crecer menos después, lo que indica regresión a la media.
- El modelo de solo unidades se pensó para las celdas con personal confidencial, pero **no supera a la mediana del eje**. Por la regla de corte, **esas celdas se quedan sin predicción**: no se inventan.

Todas las métricas, incluidas las de las líneas base y por eje, están en `data/modelo/metricas.csv` y en `dim_modelo.metricas`.

## 5. Variables que más pesan

Se mide con importancia por permutación, que es el aumento del MAE al revolver cada variable:

1. Personal por unidad (tamaño promedio del establecimiento). Los municipios con negocios muy pequeños tienden a crecer más.
2. Cociente de localización por unidades.
3. Personal ocupado inicial.
4. Cociente de localización por personal.
5. Valor agregado por trabajador.

Población, marginación y distancia al ancla aportan poco una vez que se conoce la estructura de la oferta.

## 6. Predicción

- **Ajuste final:** con ambas transiciones; predice desde CE 2024 a 5 años.
- **Resultado:** 270 celdas municipio × eje con personal base publicado, en `data/modelo/fact_prediccion_crecimiento.csv`:

  | Eje | Celdas |
  |---|---|
  | alimentos | 129 |
  | hospedaje | 86 |
  | turismo_cultura | 49 |
  | comercio_turistico | 6 |

- **Columnas:**
  - `crecimiento_pred_pct = (exp(delta_log_pred) − 1) × 100`.
  - `intervalo_inf_pct` y `intervalo_sup_pct`: cuantiles 10 % y 90 % del residuo fuera de muestra por eje, tomados de la validación espacial. En la prueba temporal cubren el 75 % de los casos, contra el 80 % nominal.
  - `personal_pred` e `incremento_personal_pred`: personas adicionales estimadas.
  - `ranking_potencial`: orden por eje según `delta_log_pred`, donde 1 es el mayor crecimiento relativo.
- **Recomendación para el índice y las rutas:** combinar `ranking_potencial` con `incremento_personal_pred` o con `personal_base`. Los municipios con bases muy pequeñas tienen porcentajes altos aunque sumen pocas personas.

## 7. Limitaciones

- 2019→2024 incluye la pandemia (cambio de régimen), así que la validación temporal es más débil de lo que parece.
- Hay pocas filas y la mitad de las celdas son confidenciales. Las predicciones cubren 270 de 564 celdas con presencia del eje.
- Población y marginación son de 2020 y quedan estáticas en ambas transiciones.
- La distancia al ancla es en línea recta desde el centroide, como sustituto de `fact_accesibilidad`. La región es aproximada por coordenadas.
- Los censos están homologados a SCIAN 2023 por INEGI. Los valores monetarios son nominales, y por eso se usan relativos al estado.
- Se predice **potencial de empleo en oferta turística**, no visitantes ni derrama.

## 8. Cómo reproducir

```bash
python scripts/censo_economico.py         # descarga INEGI → data/stg/censo_economico*.csv
python scripts/contexto_social.py         # descarga CONAPO → data/stg/contexto_social.csv
python model/prediccion_crecimiento.py    # panel, validación, métricas, predicción → data/modelo/
psql "$DATABASE_URL" -f scripts/carga_stg_censo_economico.sql
psql "$DATABASE_URL" -f scripts/carga_stg_rol_b.sql
```

Las credenciales van en una variable de entorno, nunca en Git.
