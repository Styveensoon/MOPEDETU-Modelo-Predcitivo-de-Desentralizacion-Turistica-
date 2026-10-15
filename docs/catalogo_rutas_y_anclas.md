# Catálogo de rutas existentes, Pueblos Mágicos y anclas (Rol C · Styveen)

Fecha de consulta de todas las fuentes: **14 de octubre de 2026**.
Carga: `python scripts/cargar_rutas_existentes.py` (idempotente). El SQL equivalente está en `sql/04_catalogo_rutas_styveen.sql`.

## 1. Rutas existentes

**29 rutas oficiales, 134 paradas y 70 municipios distintos.** Todas vienen de la Secretaría de Desarrollo Turístico del Estado de Puebla (visitpuebla.mx).

| Fuente (`dim_fuente`) | Documento | Qué aporta |
|---|---|---|
| 8 · Catálogo de rutas turísticas existentes | [Catálogo de Rutas Turísticas del Estado de Puebla (PDF)](https://visitpuebla.mx/documents/CATALOGO%20DE%20RUTAS.pdf) | 22 rutas en 4 circuitos: Sierra Norte, De los Volcanes, Valle Central y Tehuacán-Cuicatlán |
| 9 · Guía Bioruta del Café Puebla | [Bioruta del Café (PDF)](https://visitpuebla.mx/documents/BIORUTA%20DEL%20CAFE.pdf) | 4 circuitos del café con municipios numerados del 1 al 29 |
| 10 · Guía Ruta del Mezcal Poblano | [Ruta del Mezcal (PDF)](https://visitpuebla.mx/documents/RUTA%20DEL%20MEZCAL.pdf) | 3 circuitos del mezcal con orden A-E |

Captura: `data/catalogos/rutas_existentes.csv`, con el formato `ruta, tema, orden, municipio, fuente_url` y además las columnas circuito, tipo, localidad mencionada y página.

**Decisiones de captura**
- **Bioruta del Café:** el catálogo general la resume en 5 municipios. Se usaron los 4 circuitos de la guía porque es más completa y trae el orden numerado.
- **Ruta de los Pueblos Mágicos:** se registró como 5 sub-rutas, tal como aparece en el catálogo.
- **Orden de paradas:** donde la fuente no numera las paradas, se usa el orden en que aparecen.
- **Tipo:** las rutas de un solo municipio (Nopal y Tuna, Antojitos Poblanos, Marisco) quedan como `circuito_municipal`; las demás, como `ruta_intermunicipal`.
- **Localidades asignadas a su municipio:**
  - Chipilo → San Gregorio Atzompa
  - Santa María Tonantzintla → San Andrés Cholula
  - Ciudad Serdán → Chalchicomula de Sesma
  - San Miguel Tenextatiloyan → Zautla
  - Zapotitlán Salinas → Zapotitlán
  - "Cholula" → San Pedro Cholula y San Andrés Cholula
- **Moles Poblanos:** Atlixco solo aparece en el mapa de la ruta, no en el listado. Está marcado en el CSV.
- **Mezcal Legado de la Mixteca:** Molcaxac sale del catálogo general (no está en la guía) y se colocó antes de Tepexi de Rodríguez.
- **`distancia_desde_anterior_km`:** es la distancia en línea recta entre centroides municipales. El tiempo se llenará con `fact_accesibilidad` cuando exista.

**Cobertura:** 29 rutas, por encima de la meta de 10 a 20. No incluye rutas privadas de operadoras ni rutas municipales que no aparezcan en los documentos estatales.

## 2. Pueblos Mágicos de Puebla

12 Pueblos Mágicos que corresponden a 13 municipios, porque Cholula abarca San Pedro y San Andrés.

| Municipio | cve_geo | Año |
|---|---|---|
| Cuetzalan del Progreso | 21043 | 2002 |
| Zacatlán | 21208 | 2011 |
| Chignahuapan | 21053 | 2012 |
| Pahuatlán | 21109 | 2012 |
| Tlatlauquitepec | 21186 | 2012 |
| Xicotepec | 21197 | 2012 |
| San Pedro Cholula | 21140 | 2012 |
| San Andrés Cholula | 21119 | 2012 |
| Atlixco | 21019 | 2015 |
| Huauchinango | 21071 | 2015 |
| Tetela de Ocampo | 21172 | 2020 |
| Huejotzingo | 21074 | 2023 |
| Teziutlán | 21174 | 2023 |

**Fuentes y verificación:** la lista y los años se cruzaron entre notas de prensa sobre los nombramientos de SECTUR: [N+ (2023)](https://www.nmas.com.mx/puebla/nuevos-pueblos-magicos-en-puebla-huejotzingo-y-teziutlan/), Milenio (2025) y [gopueblos.com](https://www.gopueblos.com/en/states/puebla). No se localizó el decreto en gob.mx; está pendiente de verificar en la fuente oficial.

## 3. Criterio de "ancla"

> **Ancla = destino turístico consolidado y reconocido en un catálogo oficial.** Se cumple con cualquiera de estas condiciones:
> 1. Tiene un reconocimiento UNESCO y es nodo urbano principal: **Puebla** (Centro Histórico, Patrimonio de la Humanidad, 1987) y **Tehuacán** (acceso a la Reserva de la Biosfera Tehuacán-Cuicatlán, Patrimonio Mixto, 2018; segunda ciudad del estado).
> 2. Es **Pueblo Mágico con al menos 10 años de nombramiento** (≤ 2016). Diez años de permanencia en el programa se usan como indicador de consolidación de la oferta y de la demanda.

Con este criterio hay **12 anclas**: Puebla, Tehuacán, Cuetzalan del Progreso, Zacatlán, Chignahuapan, Pahuatlán, Tlatlauquitepec, Xicotepec, San Pedro Cholula, San Andrés Cholula, Atlixco y Huauchinango.

Tetela de Ocampo (2020), Huejotzingo (2023) y Teziutlán (2023) **no** son anclas porque su destino todavía está en consolidación. Siguen marcados como Pueblo Mágico y pueden aparecer en las rutas como municipios con oferta.

Validación pendiente: cuando Galo cargue la oferta DENUE, comprobar que las anclas estén en el decil superior de hospedaje por municipio. Si alguna no lo está, documentar la excepción.

El criterio está en el código: `ANCLAS_EXTRA` y `ANIOS_CONSOLIDACION` en `scripts/cargar_rutas_existentes.py`.

## 4. Región

Se usa la regionalización socioeconómica oficial de **7 regiones** establecida por el Congreso del Estado en 2015 (fuente 11). Las regiones son Sierra Norte, Sierra Nororiental, Valle de Serdán, Angelópolis, Valle de Atlixco y Matamoros, Mixteca, y Tehuacán y Sierra Negra.

Cubre los 217 municipios y el script lo verifica. Fue transcrita de [Wikipedia](https://es.wikipedia.org/wiki/Regiones_de_Puebla). Las regionalizaciones posteriores (22 regiones en 2022-2024 y macrorregiones en 2025) no tienen una lista completa publicada.

## 5. Estado de la carga en Supabase

| Tabla | Estado |
|---|---|
| `stg.mun_geo` | ✅ 217 polígonos INEGI 2023 a resolución completa (`scripts/cargar_municipios.py`) |
| `dw.dim_municipio` | ✅ 217 municipios (`municipio_sk` 1-217 en orden de `cve_geo`), con geometría, centroide y superficie |
| `dw.dim_fuente` | ✅ Filas 7 y 8 completadas (url, fecha, cobertura, notas) y filas 9, 10 y 11 nuevas |
| `dw.dim_ruta` | ✅ 29 rutas, `origen = 'existente'` |
| `dw.fact_ruta_parada` | ✅ 134 paradas (50 en municipios ancla) |
| `dw.dim_municipio` (es_pueblo_magico, es_ancla, region) | ✅ 13 Pueblos Mágicos, 12 anclas y 7 regiones |
| `dw.v_pares_rutas_existentes` | ✅ 84 tramos existentes para medir novedad |

`dim_municipio` era tabla del Rol A (Galo) y se cargó desde aquí para no bloquear las rutas. Ambos scripts sincronizan por `cve_geo` y son idempotentes: si el ETL vuelve a cargar municipios, basta con volver a correr `python scripts/cargar_rutas_existentes.py`.
