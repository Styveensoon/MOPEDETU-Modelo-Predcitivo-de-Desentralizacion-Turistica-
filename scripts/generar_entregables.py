"""Genera docs/entregables.md con las cifras leídas de la base (plan_migracion_front.md §12.9).

Ninguna cifra se escribe a mano: todo sale de Supabase (dw) con la publishable key, o de la copia local si no hay
red. Se vuelve a correr al final del pipeline para que el documento quede al día. Las tareas que no son de código
(ensayar el pitch, grabar el video) quedan en ⬜ hasta que el equipo las marque.

Uso: python scripts/generar_entregables.py
"""
import sys
from datetime import date
from pathlib import Path

import pandas as pd

RAIZ = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(RAIZ / "dashboard"), str(RAIZ / "scripts")]

from exportar_mapa_html import leer  # noqa: E402  (Supabase o copia local)

SALIDA = RAIZ / "docs" / "entregables.md"


def main():
    vig = leer("v_vigente").iloc[0]
    conc = leer("v_concentracion_eje")
    conc = conc[conc.periodo_sk == vig.periodo_oferta_sk].set_index("eje_sk")
    esc = leer("fact_escenario_concentracion").set_index("escenario")
    fuentes = leer("dim_fuente").sort_values("fuente_sk")
    modelos = leer("dim_modelo").set_index("nombre")
    val = leer("fact_validacion").sort_values("codigo")
    rp = leer("v_ruta_parada")
    prop = rp[rp.origen == "propuesta_modelo"].sort_values(["ruta_sk", "orden_parada"])
    desc = rp[rp.origen == "propuesta_descartada"]
    ban = leer("fact_flag_oportunidad")
    ban = ban[(ban.version_sk == vig.version_indice_sk) & ban.flag_activo.astype(bool)]
    tipos = leer("dim_tipo_flag").set_index("tipo_flag_sk").codigo
    idx = leer("v_indice_municipio")
    apt = leer("v_aptitud_circuito")
    m = modelos.metricas[vig.modelo]
    t = m.get("validacion_temporal_2014_2019_a_2019_2024", {})
    e = modelos.metricas["enlace_municipios_lgbm_v1"]
    rutas = prop.drop_duplicates("ruta_sk")
    top = idx[~idx.es_ancla.astype(bool)].nsmallest(10, "ranking_estatal")
    pob, todo, hosp, tur = (float(conc.pct_top5_poblacion.iloc[0]), float(conc.pct_top5[0]), float(conc.pct_top5[1]),
                            float(conc.pct_top5[3]))

    fila_rutas = "\n".join(
        f"| {r.ruta} | {' → '.join(prop[prop.ruta_sk == r.ruta_sk].municipio)} | {r.tiempo_total_min:.0f} | "
        f"{int(r.dias_sugeridos)} · {', '.join(prop[(prop.ruta_sk == r.ruta_sk) & prop.es_pernocta.astype(bool)].municipio) or '—'} | "
        f"{r.region_beneficiada} | {str(r.clasificacion_novedad).replace('_', ' ')} |" for r in rutas.itertuples())
    fila_fuentes = "\n".join(
        f"| {f.fuente_sk} | {f.nombre} | {f.institucion} | {f.version_corte or '—'} | "
        f"{'✅' if f.url and f.licencia_terminos and f.uso_en_modelo else '🟨 incompleta'} |" for f in fuentes.itertuples())
    fila_val = "\n".join(f"| {v.codigo} | {v.descripcion} | {v.resultado} | "
                         f"{ {'ok': '✅', 'pendiente': '⏳', 'falla': '❌'}[v.estado] } |" for v in val.itertuples())
    conteo_ban = ban.tipo_flag_sk.map(tipos).value_counts()
    ok_val = int((val.estado == "ok").sum())

    texto = f"""# MOPEDETU · Entregables de la convocatoria

Hackathon "Puebla Turística 360°" (Tech Capital 2026). Presentación: viernes 16 de octubre.
**Este documento lo genera `scripts/generar_entregables.py` con cifras leídas de la base** (corte {date.today().isoformat()},
índice `{vig.version_indice}`, modelo `{vig.modelo}`). No editar las cifras a mano: correr el script.

| # | Entregable | Estado |
|---|---|---|
| 1 | Descripción ejecutiva | ✅ |
| 2 | Problema y beneficiarios | ✅ |
| 3 | Descripción de la solución | ✅ |
| 4 | Inventario y documentación de fuentes | ✅ {len(fuentes)} fuentes en `dim_fuente` |
| 5 | Justificación de la selección de datos | ✅ |
| 6 | Procesos de obtención, limpieza, integración y análisis | ✅ |
| 7 | Arquitectura o metodología | ✅ |
| 8 | Prototipo funcional | ✅ tablero con datos reales + mapa HTML sin internet |
| 9 | Evidencia de análisis y resultados | ✅ {ok_val} de {len(val)} validaciones en verde |
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
- Los 5 municipios principales tienen el **{pob:.1f} %** de la población, pero el **{todo:.1f} %** del empleo turístico,
  el **{hosp:.1f} %** del hospedaje y el **{tur:.1f} %** de la oferta de turismo y cultura (DENUE 05/2026, `v_concentracion_eje`).
  HHI del empleo turístico: {float(conc.hhi[0]):,.0f} (población: {float(conc.hhi_poblacion.iloc[0]):,.0f}).
- Beneficiarios: municipios con oferta real y poca visibilidad ({int(conteo_ban.get('OFERTA_INVISIBLE', 0))} celdas con
  `OFERTA_INVISIBLE`), prestadores locales (incluida la oferta sin registro: {int(conteo_ban.get('OFERTA_SIN_REGISTRO', 0))}
  celdas con `OFERTA_SIN_REGISTRO`), la Secretaría y los operadores.

## 3. Descripción de la solución
DENUE + Censos Económicos (2014, 2019, 2024) + contexto social, accesibilidad por carretera y fuentes abiertas →
oferta por municipio y eje → **índice de oportunidad** (`{vig.version_indice}`) + **banderas** + **predicción de
crecimiento** (`{vig.modelo}`) + **modelo de enlaces** → **optimizador de rutas** con reglas de operación → tablero.
Resultado vigente: {len(rutas)} rutas propuestas, {prop[prop.es_emergente.astype(bool)].municipio_sk.nunique()} municipios
emergentes, {int(apt.apto.astype(bool).sum())} municipios aptos para circuito.

## 4. Inventario y documentación de fuentes
Una fila de `dw.dim_fuente` por fuente (también en la página **Metodología y fuentes** del tablero).

| fuente_sk | Fuente | Institución | Versión / corte | Ficha completa |
|---|---|---|---|---|
{fila_fuentes}

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
{fila_rutas}

Descartadas y registradas: {', '.join(desc.drop_duplicates('ruta_sk').ruta) or 'ninguna'}.

**Top 10 municipios emergentes** (sin anclas): {', '.join(f"{n} ({v:.3f})" for n, v in zip(top.nombre, top.indice_oportunidad.astype(float)))}.

**Escenarios de concentración** (`fact_escenario_concentracion`): HHI {esc.hhi['hoy']:,.0f} hoy → {esc.hhi['tendencial']:,.0f}
tendencial → {esc.hhi['con_rutas_hipotetico']:,.0f} con rutas (hipotético); top 5 {esc.pct_top5['hoy']:.1f} % →
{esc.pct_top5['con_rutas_hipotetico']:.1f} %; Gini {esc.gini['hoy']:.3f} → {esc.gini['con_rutas_hipotetico']:.3f}.

**Validaciones** (`fact_validacion`):

| Código | Validación | Resultado | Estado |
|---|---|---|---|
{fila_val}

## 10. Presentación y demostración
Recorrido de 5 pasos en la página de inicio del tablero (problema → oportunidad → una ruta → Jonotla → validaciones).
- [ ] Pitch ensayado dos veces (equipo)
- [ ] Video corto de respaldo del recorrido (equipo)

## 11. Documentación del modelo de IA
- **Crecimiento** (`{vig.modelo}`, LightGBM): validación cruzada por municipio MAE {m['lgbm']['mae']} vs
  {m['b1_media_eje']['mae']} (media del eje) y {m['b2_ridge']['mae']} (Ridge); Spearman {m['lgbm']['spearman']}.
  Validación temporal (2014→2019 entrena, 2019→2024 prueba): Spearman {t.get('lgbm', {}).get('spearman')} vs
  {t.get('b1_media_eje', {}).get('spearman')}. Intervalo conformal de 80 % (cobertura {m.get('cobertura_intervalo_80', 0):.0%}).
  Sin predicción con < 3 unidades.
- **Enlaces** (`enlace_municipios_lgbm_v1`): AUC {e['lgbm']['auc']} vs {e['b_distancia']['auc']} (distancia) y
  {e['b_similitud']['auc']} (similitud).
- Uso correcto: priorizar municipios, no pronosticar cifras exactas. Limitaciones en la página Metodología y fuentes.
"""
    SALIDA.write_text(texto, encoding="utf-8")
    print(f"✓ {SALIDA.relative_to(RAIZ)} generado")


if __name__ == "__main__":
    main()
