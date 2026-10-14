<div align="center">

# 🗺️ MOPEDETU

### Modelo Predictivo de Descentralización Turística · Puebla, México

*Llevar el turismo más allá de los destinos de siempre, con datos.*

![Estado](https://img.shields.io/badge/estado-en%20desarrollo-orange)
![Python](https://img.shields.io/badge/Python-3.11+-3776AB?logo=python&logoColor=white)
![Región](https://img.shields.io/badge/región-Puebla%20(217%20municipios)-8A1538)
![Hackathon](https://img.shields.io/badge/HACK-2026-blueviolet)

</div>

---

## 📌 El problema

El turismo en Puebla se concentra en unos pocos destinos: la capital, Cholula, Atlixco y algunos Pueblos Mágicos. Muchos de los **217 municipios** tienen patrimonio, naturaleza, gastronomía y tradiciones con potencial, pero reciben poca derrama económica y poca infraestructura.

## 🎯 Objetivo

Construir un **modelo predictivo** que:

1. **Identifique municipios con potencial turístico subaprovechado** mediante un *Índice de Oportunidad Turística*.
2. **Prediga el impacto** de dirigir flujo turístico e inversión hacia ellos.
3. **Proponga rutas y circuitos turísticos** que conecten destinos consolidados con municipios emergentes y repartan mejor la derrama.

## 🧩 Factores considerados

| Dimensión | Variables (ejemplos) |
|---|---|
| 🏛️ **Oferta turística** | Atractivos, patrimonio, Pueblos Mágicos, zonas arqueológicas, fiestas y tradiciones |
| 🥾 **Actividades** | Ecoturismo, aventura, gastronomía, cultura, turismo religioso, rural y comunitario |
| 💰 **Inversión pública** | Inversión estatal y federal reciente en infraestructura y promoción turística |
| 🛣️ **Conectividad** | Distancia y tiempo a polos turísticos, red carretera, transporte |
| 🏨 **Infraestructura** | Hospedaje, restaurantes, servicios, conectividad digital |
| 👥 **Socioeconómico** | Marginación, empleo, población, vocación productiva |
| 🛡️ **Contexto** | Seguridad, clima, estacionalidad |

## 🏗️ Arquitectura propuesta

```
 Fuentes de datos ─► Limpieza e integración ─► Índice de Oportunidad ─► Modelo predictivo ─► Generador de rutas ─► Visualización
 (INEGI, DATATUR,      (data/)                   (por municipio)          (model/)            (grafos / optimización)   (mapa + dashboard)
  SECTUR, CONEVAL,
  transparencia)
```

## 🚀 Abrir el tablero

**Windows:** doble clic en **`MOPEDETU.bat`**
**Mac / Linux:** `sh mopedetu.sh`
**Cualquier sistema:** `python iniciar.py`

Solo se necesita Python 3.10 o superior. La primera vez se instalan las dependencias de forma automática y después se abre el navegador. Por ahora el tablero funciona **sin backend**, con datos DEMO simulados sobre los 217 municipios reales.

| Página | Qué hace |
|---|---|
| 🏠 Panorama | KPIs, mapa del índice de oportunidad, rutas, top emergentes y curva de concentración |
| 🗺️ Mapa de oportunidades | Cualquier indicador por municipio, flags, columnas 3D y clic para ver el detalle |
| 🧭 Rutas | Rutas intermunicipales optimizadas a partir de destinos ancla |
| 🔁 Circuitos | Circuitos dentro de un municipio, variados o de una sola actividad |
| 🔮 Simulador | Inversión y promoción contra el escenario tendencial |
| 🏘️ Ficha municipal | Predominancia, explicación del índice, flags y proyección |
| 🚩 Alertas | Tabla filtrable de flags, exportable a CSV |

## 📂 Estructura del repositorio

```
MOPEDETU/
├── data/      # Datos crudos y procesados por municipio
├── model/     # Notebooks, scripts y modelos entrenados
├── docs/      # Documentación, metodología y presentación
└── README.md
```

## 📊 Fuentes de datos (previstas)

- **INEGI**: Censo de Población, DENUE, Marco Geoestadístico
- **DATATUR / SECTUR**: ocupación hotelera y afluencia turística
- **CONEVAL / CONAPO**: índices de rezago social y marginación
- **Gobierno del Estado de Puebla**: inversión pública y programas turísticos
- **Pueblos Mágicos**: catálogo oficial

## 🌿 Flujo de trabajo (Git)

| Rama | Uso |
|---|---|
| `main` | Rama estable; solo entra código revisado |
| `Styveen` | Rama de trabajo de Styveen |
| `Raul` | Rama de trabajo de Raúl |
| `Galo` | Rama de trabajo de Galo |

Los commits siguen [Conventional Commits](https://www.conventionalcommits.org/es/v1.0.0/):

```
feat: agrega cálculo del índice de oportunidad
fix: corrige claves municipales duplicadas
docs: actualiza la metodología
data: integra inversión pública 2024-2025
```

## 👥 Equipo

| | Integrante |
|---|---|
| 🧑‍💻 | **Styveen** |
| 🧑‍💻 | **Raúl** |
| 🧑‍💻 | **Galo** |

---

<div align="center">
Hecho con ❤️ para Puebla · HACK 2026
</div>
