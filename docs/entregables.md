# MOPEDETU · Entregables de la convocatoria

Hackathon "Puebla Turística 360°" (Tech Capital 2026). Presentación: viernes 16 de octubre.
**Este documento lo genera `scripts/generar_entregables.py` con cifras leídas de la base** (corte 2026-10-15,
índice `v3_dominio_osrm`, modelo `crecimiento_ue_eje_lgbm_v2`). No editar las cifras a mano: correr el script.

| # | Entregable | Estado |
|---|---|---|
| 1 | Descripción ejecutiva | ✅ |
| 2 | Problema y beneficiarios | ✅ |
| 3 | Descripción de la solución | ✅ |
| 4 | Inventario y documentación de fuentes | ✅ 22 fuentes en `dim_fuente` |
| 5 | Justificación de la selección de datos | ✅ |
| 6 | Procesos de obtención, limpieza, integración y análisis | ✅ |
| 7 | Arquitectura o metodología | ✅ |
| 8 | Prototipo funcional | ✅ tablero con datos reales + mapa HTML sin internet |
| 9 | Evidencia de análisis y resultados | ✅ 11 de 12 validaciones en verde |
| 10 | Presentación y demostración | 🟨 recorrido en el tablero listo; ensayo y video pendientes del equipo |
| 11 | Documentación del modelo de IA | ✅ |

---

## 1. Descripción ejecutiva
MOPEDETU es una plataforma de datos para **descentralizar el turismo de Puebla**. Con datos oficiales y abiertos de los
217 municipios mide dónde se concentra hoy la oferta turística, calcula un **índice de oportunidad** por municipio y
eje, **predice** dónde puede crecer la oferta (solo donde el modelo tiene fundamento) y **propone rutas** que llevan al
visitante desde un destino ancla a municipios emergentes, con tiempos por carretera, pernocta y riesgo conocido. Está
pensada para la Secretaría de Turismo del Estado (planear y priorizar) y para operadores turísticos (vender rutas).

## 2. Problema y beneficiarios
- Los 5 municipios principales tienen el **37.5 %** de la población, pero el **51.9 %** del empleo turístico,
  el **63.1 %** del hospedaje y el **77.7 %** de la oferta de turismo y cultura (DENUE 05/2026, `v_concentracion_eje`).
  HHI del empleo turístico: 1,306 (población: 749).
- Beneficiarios: municipios con oferta real y poca visibilidad (77 celdas con
  `OFERTA_INVISIBLE`), prestadores locales (incluida la oferta sin registro: 37
  celdas con `OFERTA_SIN_REGISTRO`), la Secretaría y los operadores.

## 3. Descripción de la solución
DENUE + Censos Económicos (2014, 2019, 2024) + contexto social, accesibilidad por carretera y fuentes abiertas →
oferta por municipio y eje → **índice de oportunidad** (`v3_dominio_osrm`) + **banderas** + **predicción de
crecimiento** (`crecimiento_ue_eje_lgbm_v2`) + **modelo de enlaces** → **optimizador de rutas** con reglas de operación → tablero.
Resultado vigente: 5 rutas propuestas, 19 municipios
emergentes, 86 municipios aptos para circuito.

## 4. Inventario y documentación de fuentes
Una fila de `dw.dim_fuente` por fuente (también en la página **Metodología y fuentes** del tablero).

| fuente_sk | Fuente | Institución | Versión / corte | Ficha completa |
|---|---|---|---|---|
| 1 | DENUE | INEGI | 05/2026 (misma descarga que la fuente "DENUE 05/2026") | ✅ |
| 2 | Marco Geoestadístico | INEGI | Marco Geoestadístico 2023 de INEGI (GeoJSON 2023/states/Puebla.json) | ✅ |
| 3 | Censos Económicos | INEGI | CE 2019 y CE 2024 (datos abiertos por entidad, Puebla) | ✅ |
| 4 | Censo de Población y Vivienda | INEGI | 2020 · ITER (principales resultados por localidad) | ✅ |
| 5 | Marginación municipal | CONAPO | Índice de marginación 2020 (método DP2) | ✅ |
| 6 | OpenStreetMap | OSM | Consulta Overpass 2026-10-14 (atractivos con nombre) | ✅ |
| 7 | Catálogo de destinos y Pueblos Mágicos | Secretaría de Turismo federal (SECTUR), programa Pueblos Mágicos | 12 Pueblos Mágicos de Puebla, nombramientos 2002-2023 | ✅ |
| 8 | Catálogo de rutas turísticas existentes | Secretaría de Desarrollo Turístico del Estado de Puebla (visitpuebla.mx) | Catálogo de Rutas Turísticas del Estado de Puebla: 22 rutas en 4 circuitos | ✅ |
| 9 | Guía Bioruta del Café Puebla | Secretaría de Desarrollo Turístico del Estado de Puebla (visitpuebla.mx) | 4 circuitos: Sierra Norte, Sierra Nororiental, Sierra Nevada y Sierra Negra | ✅ |
| 10 | Guía Ruta del Mezcal Poblano | Secretaría de Desarrollo Turístico del Estado de Puebla (visitpuebla.mx) | 3 circuitos: Reserva de la Biosfera, Popocatépetl y Mixteca Poblana | ✅ |
| 11 | Regionalización socioeconómica del estado de Puebla (7 regiones) | Congreso del Estado de Puebla, Ley de Desarrollo Económico Sustentable (2015) | 7 regiones, 2015 | ✅ |
| 12 | DENUE 05/2026 (descarga directa) | INEGI | 05/2026 | ✅ |
| 13 | Censo 2020 · Principales resultados por localidad (ITER) | INEGI | Censo de Población y Vivienda 2020 | ✅ |
| 14 | OpenStreetMap · red vial principal y servicios (Overpass) | Colaboradores de OpenStreetMap | Consulta 2026-10-15 | ✅ |
| 15 | Calendario de ferias, festivales y temporadas | Varias (Sectur Puebla, prensa, agregadores) | 2026 | ✅ |
| 16 | Medición de la pobreza municipal 2020 | CONEVAL | 2020 | ✅ |
| 17 | Catálogo curado de atractivos | MOPEDETU (revisión manual con fuentes) | data/catalogos/atractivos.csv | ✅ |
| 18 | OSRM · tiempos por carretera entre cabeceras | Proyecto OSRM sobre OpenStreetMap | osrm_publico, 2026-10-15 | ✅ |
| 19 | DATATUR · Monitoreo Hotelero (mensual) | Secretaría de Turismo federal (SECTUR) | 2023-09-01 a 2026-08-01 | ✅ |
| 20 | Vistas de página de Wikipedia en español (Wikimedia) | Fundación Wikimedia | 2025-10-01 a 2026-09-30 | ✅ |
| 21 | SESNSP · Incidencia delictiva municipal (fuero común) | Secretariado Ejecutivo del Sistema Nacional de Seguridad Pública | Metodología 2015-2025, corte de agosto de 2026 | ✅ |
| 22 | CONAPO · Reconstrucción y proyecciones de la población municipal 1990-2040 | Consejo Nacional de Población (CONAPO) | Edición 2024 (base Censo 2020) | ✅ |

## 5. Justificación de la selección de datos
- **DENUE e INEGI Censos Económicos**: únicas fuentes oficiales con oferta por establecimiento y municipio; los censos
  permiten entrenar y validar en el tiempo (2014 → 2019 → 2024). El DENUE se actualiza a partir de los censos: no se
  presentan como evidencias independientes.
- **Censo 2020, CONAPO y CONEVAL**: población, marginación y pobreza para la necesidad social y las tasas.
- **OSRM sobre OpenStreetMap**: tiempos por carretera entre cabeceras (la línea recta subestimaba la sierra).
- **DATATUR, SESNSP, Wikipedia, CONAPO 2040**: demanda observada (solo la capital), seguridad para planear rutas,
  visibilidad y población por año.
- Catálogos de la Secretaría (rutas oficiales, Pueblos Mágicos): para comparar la novedad de las rutas.

## 6. Procesos de obtención, limpieza, integración y análisis
Scripts versionados en `scripts/` y `model/`, migraciones idempotentes en `sql/` y la orquestación en
`scripts/pipeline.py` (ver `docs/Validations.md` §25 y `docs/log_migracion_front.md`). Reglas clave: los ceros de OSM
en municipios poco mapeados son "sin dato"; el personal confidencial del censo se lee como "al menos X"; la
predicción solo existe con ≥ 3 unidades en el eje; los tiempos de rutas llevan un margen de planeación por región.

## 7. Arquitectura o metodología
Pipeline (Python) → Supabase/PostgreSQL + PostGIS (esquemas `stg` de entrada y `dw` dimensional, RLS de solo
lectura pública, vistas `security_invoker`) → tablero Streamlit que **solo lee la base** con la *publishable key*
(o una copia local en `data/snapshot/` si no hay red). La configuración vigente (versiones y parámetros) vive en
`dw.v_vigente`: el pipeline y el tablero leen las mismas reglas.

## 8. Prototipo funcional
- Tablero: `MOPEDETU.bat` / `python iniciar.py`. Páginas: Recorrido de presentación, Panorama, Ficha técnica,
  Metodología y fuentes, Rutas.
- Mapa HTML que funciona sin internet: `docs/demo/mapa_mopedetu.html`.

## 9. Evidencia de análisis y resultados
**Rutas propuestas** (`v_ruta_parada`):

| Ruta | Recorrido | Min. carretera | Días · pernocta | Región beneficiada | Novedad |
|---|---|---|---|---|---|
| Talavera y artesanías · Tlatlauquitepec → Tenampulco (propuesta 1) | Tlatlauquitepec → Zautla → Zacapoaxtla → Jonotla → Tuzamapan de Galeana → Tenampulco | 173 | 2 · Zacapoaxtla | Sierra Nororiental | nueva |
| Volcanes y alta montaña · San Pedro Cholula → Atzitzihuacán (propuesta 2) | San Pedro Cholula → Nealtican → Calpan → San Jerónimo Tecuanipan → Tochimilco → Atzitzihuacán | 107 | 2 · San Pedro Cholula | Valle de Atlixco y Matamoros | nueva |
| Turismo religioso y conventos · Tehuacán → Cuautinchán (propuesta 3) | Tehuacán → Chalchicomula de Sesma → Quecholac → Acatzingo → Atoyatempan → Cuautinchán | 179 | 2 · Acatzingo | Valle de Serdán | nueva |
| Mezcal y destilados · Tehuacán → Huehuetlán el Grande (propuesta 4) | Tehuacán → Tlacotepec de Benito Juárez → Tecali de Herrera → Molcaxac → Huehuetlán el Grande | 171 | 2 · Tehuacán | Mixteca | parcialmente existente |
| Gastronomía tradicional · Pahuatlán → Tlaxco (propuesta 5) | Pahuatlán → Honey → Tlacuilotepec → Tlaxco | 99 | 2 · Pahuatlán | Sierra Norte | nueva |

Descartadas y registradas: Ecoturismo y aventura · San Andrés Cholula → Huaquechula (descartada 1).

**Top 10 municipios emergentes** (sin anclas): Santa Isabel Cholula (0.793), Jonotla (0.791), Huehuetla (0.722), Tlacuilotepec (0.720), Huehuetlán el Grande (0.718), Tochimilco (0.716), Ajalpan (0.716), Nauzontla (0.715), Zapotitlán (0.714), Tepexco (0.712).

**Escenarios de concentración** (`fact_escenario_concentracion`): HHI 1,306 hoy → 1,141
tendencial → 1,106 con rutas (hipotético); top 5 51.9 % →
48.4 %; Gini 0.817 → 0.801.

**Validaciones** (`fact_validacion`):

| Código | Validación | Resultado | Estado |
|---|---|---|---|
| D1 | Predicción solo dentro del dominio del modelo | 0 fuera de dominio con predicción · 467 con predicción | ✅ |
| R1 | Rutas del modelo operables | 5/5 cumplen · tramo máx. 75 min | ✅ |
| R2 | Paradas con qué visitar y emergentes reales (§12.1) | 0 sin punto visitable · 0 emergentes solo con BARRERA_ACCESO | ✅ |
| V1 | Cobertura de los 217 municipios | 217/217 con semáforos · 217/217 con contexto | ✅ |
| V2 | Coherencia de anclas | 12/12 | ✅ |
| V3 | El DENUE detecta la actividad en los municipios de su ruta oficial | cafe 19/29 · mezcal 6/12 | ✅ |
| V4 | El modelo de crecimiento gana a sus líneas base | CV: MAE 0.2468 vs 0.2728 / 0.2832; Spearman 0.461 · temporal: Spearman 0.336 vs 0.061 | ✅ |
| V5 | El modelo de enlaces gana a la distancia y a la similitud | AUC 0.89 vs distancia 0.856 y similitud 0.702 | ✅ |
| V6 | Sensibilidad del índice | 95%-100% | ✅ |
| V7 | Novedad de las rutas | 4 nuevas · 1 parcialmente existentes | ✅ |
| V8 | Descentralización (escenario hipotético) | HHI 1,306 → 1,141 → 1,106 | ✅ |
| V9 | Proxy de turismo contra DATATUR | No ejecutable: DATATUR público trae 1 destino(s) de Puebla | ⏳ |

## 10. Presentación y demostración
Recorrido de 5 pasos en la página de inicio del tablero (problema → oportunidad → una ruta → Jonotla → validaciones).
- [ ] Pitch ensayado dos veces (equipo)
- [ ] Video corto de respaldo del recorrido (equipo)

## 11. Documentación del modelo de IA
- **Crecimiento** (`crecimiento_ue_eje_lgbm_v2`, LightGBM): validación cruzada por municipio MAE 0.2468 vs
  0.2728 (media del eje) y 0.2832 (Ridge); Spearman 0.461.
  Validación temporal (2014→2019 entrena, 2019→2024 prueba): Spearman 0.336 vs
  0.061. Intervalo conformal de 80 % (cobertura 80%).
  Sin predicción con < 3 unidades.
- **Enlaces** (`enlace_municipios_lgbm_v1`): AUC 0.89 vs 0.856 (distancia) y
  0.702 (similitud).
- Uso correcto: priorizar municipios, no pronosticar cifras exactas. Limitaciones en la página Metodología y fuentes.
