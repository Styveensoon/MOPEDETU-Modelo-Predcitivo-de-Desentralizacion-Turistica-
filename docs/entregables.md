# MOPEDETU · Entregables de la convocatoria

Hackathon "Puebla Turística 360°" (Tech Capital 2026). Presentación: viernes 16 de octubre.
Compila: **Styveen**. Cada sección indica quién la aporta y en qué estado está.

| # | Entregable | Aporta | Estado |
|---|---|---|---|
| 1 | Descripción ejecutiva | Styveen | ⬜ |
| 2 | Problema y beneficiarios | Styveen (con `v_concentracion`) | ⬜ |
| 3 | Descripción de la solución | Styveen | ⬜ |
| 4 | Inventario y documentación de fuentes | Cada quien su fila de `dim_fuente`; Styveen compila | 🟨 filas 7-11 listas |
| 5 | Justificación de la selección de datos | Galo (DENUE, Marco) y Raúl (censos, social) | ⬜ |
| 6 | Procesos de obtención, limpieza, integración y análisis | Galo (ETL) y Raúl (censos) | ⬜ |
| 7 | Arquitectura o metodología | Galo | ⬜ |
| 8 | Prototipo funcional | Styveen (mapa y rutas) + Galo (BD) | 🟨 tablero Streamlit con datos demo |
| 9 | Evidencia de análisis y resultados | Galo (índice, sensibilidad) y Raúl (métricas) | ⬜ |
| 10 | Presentación y demostración | Styveen | ⬜ |
| 11 | Documentación del modelo de IA | Raúl | ⬜ |

---

## 1. Descripción ejecutiva
*Responsable: Styveen.* Media página: qué es MOPEDETU, qué problema ataca, qué entrega (índice, predicción y rutas nuevas) y para quién.

## 2. Problema y beneficiarios
*Responsable: Styveen.*
- Cifra de concentración: porcentaje de la oferta turística en los 5 municipios principales (`dw.v_concentracion`).
- Beneficiarios directos: municipios con oferta real pero poca visibilidad, prestadores locales y la Secretaría de Desarrollo Turístico.

## 3. Descripción de la solución
*Responsable: Styveen.* Flujo: DENUE + Censos Económicos → oferta por municipio y eje → índice de oportunidad + predicción de potencial → rutas nuevas comparadas con las 29 rutas oficiales existentes.

## 4. Inventario y documentación de fuentes
*Compila: Styveen. Una fila de `dw.dim_fuente` por fuente.*

| fuente_sk | Fuente | Responsable | Documentada |
|---|---|---|---|
| 1 | DENUE (INEGI) | Galo | ⬜ |
| 2 | Marco Geoestadístico (INEGI) | Galo | ⬜ |
| 3 | Censos Económicos (INEGI) | Raúl | ⬜ |
| 4 | Censo de Población y Vivienda (INEGI) | Raúl | ⬜ |
| 5 | Marginación municipal (CONAPO) | Raúl | ⬜ |
| 6 | OpenStreetMap | Galo | ⬜ |
| 7 | Catálogo de destinos y Pueblos Mágicos | Styveen | ✅ |
| 8 | Catálogo de rutas turísticas existentes | Styveen | ✅ |
| 9 | Guía Bioruta del Café Puebla | Styveen | ✅ |
| 10 | Guía Ruta del Mezcal Poblano | Styveen | ✅ |
| 11 | Regionalización socioeconómica (7 regiones) | Styveen | ✅ |

Detalle de las fuentes 7 a 11: `docs/catalogo_rutas_y_anclas.md`.

## 5. Justificación de la selección de datos
*Responsables: Galo (DENUE, Marco) y Raúl (censos, social).*

## 6. Procesos de obtención, limpieza, integración y análisis
*Responsables: Galo (ETL `01_ddl`, `02_etl`) y Raúl (censos, `03_ddl_prediccion`).*
- Rutas existentes: captura manual desde los PDF oficiales → `data/catalogos/rutas_existentes.csv` → cruce por `cve_geo` → `dw.dim_ruta` / `dw.fact_ruta_parada` (`scripts/cargar_rutas_existentes.py`).

## 7. Arquitectura o metodología
*Responsable: Galo.* Esquemas `stg` (entrada) y `dw` (modelo dimensional) en PostgreSQL + PostGIS.

## 8. Prototipo funcional
*Responsables: Styveen (mapa y rutas) + Galo (BD).*
- Tablero: `MOPEDETU.bat` / `python iniciar.py`.
- Mapa HTML exportado que funciona sin internet (respaldo de la demo): ⬜

## 9. Evidencia de análisis y resultados
*Responsables: Galo (índice, sensibilidad) y Raúl (métricas).*
- Rutas propuestas y su clasificación de novedad (`dw.v_novedad_ruta`): Styveen ⬜

## 10. Presentación y demostración
*Responsable: Styveen.* Pitch en 6 partes: problema, datos, método, demo, impacto, y límites y escalabilidad.
- [ ] Pitch ensayado dos veces
- [ ] Video corto de respaldo

## 11. Documentación del modelo de IA
*Responsable: Raúl.* Validación temporal, líneas base y métricas.
