# Datos base del modelo: fuentes, homologación y carga

Carga: `python scripts/cargar_datos_base.py` (idempotente: cada sección borra y reinserta lo suyo).
Fecha de consulta de todas las fuentes: **14 de octubre de 2026**.

## Estado en Supabase

| Tabla | Filas | Fuente |
|---|---|---|
| `stg.denue` | 60,446 | DENUE 05/2026: solo los establecimientos turísticos (las clases de `bridge_scian_eje`) |
| `stg.totales_municipio` | 217 | DENUE 05/2026: todos los establecimientos (denominador del cociente de localización) |
| `dw.dim_scian` | 2,002 | Catálogo SCIAN 2023 del CE 2024 + códigos del DENUE; 39 clases turísticas |
| `dw.bridge_scian_eje` | 39 | Clases turísticas → 4 ejes, con pesos |
| `dw.dim_establecimiento` | 60,446 | Establecimientos turísticos con municipio, clase, estrato y punto |
| `dw.fact_oferta_municipio_eje` | 868 | 217 municipios × 4 ejes: unidades, personal, participación, CL, nivel y ranking |
| `stg.censo_economico` | 2,503 | CE 2019 y 2024: total municipal + 16 códigos turísticos |
| `dw.fact_censo_economico` | 1,736 | 217 × 4 ejes × 2 censos |
| `dw.fact_contexto_social` | 217 | Población e internet (ITER 2020), marginación (CONAPO 2020), pobreza (CONEVAL 2020) |
| `dw.fact_accesibilidad` | 46,872 | Todos los pares de municipios: distancia, tiempo estimado y colindancia |
| `dw.fact_atractivo` | 208 | Atractivos de OSM por categoría + 4 zonas INAH |

Las vistas del Rol A ya funcionan: `v_perfil_municipio`, `v_concentracion`, `v_crecimiento_censal` y `v_panel_crecimiento`.

**Cifra del problema** (`v_concentracion`): **5 municipios concentran el 51.9 % de la oferta turística** de Puebla (HHI 1,306).

## Ejes turísticos (SCIAN 2023)

| Eje | Clases (prefijo) y peso |
|---|---|
| Hospedaje | 721 (1.0) |
| Alimentos y bebidas | 7225 restaurantes (1.0), 7224 bares (0.5) |
| Turismo y cultura | 712 museos y sitios; 713111/713112 parques; 713113/713114 balnearios; 713910 golf; 713998 recreativos; 5615 agencias; 4871/4872/4879 transporte turístico (1.0) |
| Comercio turístico | 465915 artesanías (1.0), 465912 regalos (0.5), 327111 alfarería y talavera (0.5), 465913 artículos religiosos (0.3) |

Un peso menor que 1 indica una actividad que atiende tanto a visitantes como a residentes. Las demás clases del sector 713 (gimnasios, billares, casinos) quedan fuera.

## Decisiones de homologación

- **Censos Económicos.**
  - Se usaron los archivos de datos abiertos por entidad de 2019 (SCIAN 2018) y 2024 (SCIAN 2023). Los códigos turísticos usados no cambian entre versiones.
  - El archivo de 2019 trae una coma final en cada renglón; se lee con `index_col=False` para que no se corran las columnas.
  - Las celdas confidenciales vienen vacías en personal y valor agregado. Se marcan con `hay_confidencial` / `confidencial` y se suma lo disponible.
  - Los totales estatales coinciden con los de INEGI: 1,117,993 personas ocupadas (2019) y 1,251,065 (2024).
  - **CE 2014 no tiene descarga directa por entidad**: solo existe en la herramienta en línea de INEGI. Queda pendiente para un segundo periodo de validación.
- **Nivel de predominancia.** El DDL del Rol A solo admite `Alta`, `Media` y `Baja`. La equivalencia es: muy alta → `Alta`, sin oferta → `NULL`.
- **Eje global (0).** `fact_oferta_municipio_eje` y `fact_censo_economico` no lo admiten (restricción del DDL). Se calcula sumando los ejes cuando haga falta.
- **Accesibilidad.**
  - Distancia en línea recta entre centroides y tiempo = distancia × 1.8 min/km, el mismo factor de las 1,560 filas que ya existían.
  - Comparación con esas filas: diferencia media de 0.67 km y colindancia idéntica (100 %). Se reemplazaron por los 46,872 pares completos.
  - Colindancia con un margen de ~100 m, porque los polígonos de INEGI no siempre comparten el borde exacto.
- **Marginación.**
  - El sitio de CONAPO bloquea descargas automáticas. Se usó la copia de `IMM_2020.xlsx` del repositorio IndiceMx/IM_2020.
  - Validación: correlación de Spearman de −0.914 con el índice de carencias calculado del Censo 2020. El signo es negativo porque en el índice DP2 de CONAPO un valor mayor significa menos marginación.
  - Los semáforos sociales ya usan el grado de CONAPO.
- **Pobreza.** Porcentaje de población en pobreza 2020 del concentrado municipal de CONEVAL.

## Fuentes

- [DENUE 05/2026 (INEGI)](https://www.inegi.org.mx/contenidos/masiva/denue/denue_21_csv.zip)
- [Censos Económicos 2024, datos abiertos de Puebla (INEGI)](https://www.inegi.org.mx/contenidos/programas/ce/2024/datosabiertos/conjunto_de_datos_ce_pue_2024_csv.zip)
- [Censos Económicos 2019, datos abiertos de Puebla (INEGI)](https://www.inegi.org.mx/contenidos/programas/ce/2019/Datosabiertos/ce2019_pue_csv.zip)
- [ITER 2020 (INEGI)](https://www.inegi.org.mx/contenidos/programas/ccpv/2020/datosabiertos/iter/iter_21_cpv2020_csv.zip)
- [Índice de marginación 2020 (CONAPO, copia IndiceMx)](https://github.com/IndiceMx/IM_2020)
- [Pobreza municipal 2020 (CONEVAL)](https://www.coneval.org.mx/Medicion/Documents/Pobreza_municipal/2020/Concentrado_indicadores_de_pobreza_2020.zip)
- [OpenStreetMap / Overpass](https://overpass-api.de/) (ODbL)

## Lo que sigue (anillos A5 y A6)

1. Índice de oportunidad v1 → `fact_indice_oportunidad` y `fact_flag_oportunidad`.
2. Modelo de crecimiento (CE 2019 → 2024, validación cruzada entre municipios) → `fact_prediccion_crecimiento`.
3. Modelo de enlaces (84 tramos de rutas oficiales) → `fact_prediccion_enlace`; clusters y similitud.
4. Optimizador de rutas → `dim_ruta` / `fact_ruta_parada` (origen `propuesta_modelo`) y `fact_ruta_evaluacion`.
