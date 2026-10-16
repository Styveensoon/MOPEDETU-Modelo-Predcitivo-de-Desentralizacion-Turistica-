-- MOPEDETU · F1, F2 y F5 del plan de afinación (docs/plan_afinacion_bd.md) · Columnas nuevas
-- Solo agrega: las columnas viejas (tiempo_min_est, personal_ocupado, crecimiento_pred_pct...) siguen igual porque
-- las leen el tablero y los scripts. Idempotente.

-- F1 · Cabecera municipal como punto de origen y año de Pueblo Mágico
ALTER TABLE dw.dim_municipio
  ADD COLUMN IF NOT EXISTS cabecera_nombre    text,
  ADD COLUMN IF NOT EXISTS cabecera_lat       numeric(9,6),
  ADD COLUMN IF NOT EXISTS cabecera_lon       numeric(9,6),
  ADD COLUMN IF NOT EXISTS anio_pueblo_magico smallint;

-- F1 · Tiempos por carretera
ALTER TABLE dw.fact_accesibilidad
  ADD COLUMN IF NOT EXISTS distancia_km_carretera numeric(8,2),
  ADD COLUMN IF NOT EXISTS tiempo_min_carretera   numeric(8,1),
  ADD COLUMN IF NOT EXISTS fuente_tiempo          text
       CHECK (fuente_tiempo IN ('osrm_local', 'osrm_publico', 'recta_x1.8')),
  ADD COLUMN IF NOT EXISTS fecha_calculo          date;

CREATE OR REPLACE VIEW dw.v_tiempo_municipios WITH (security_invoker = on) AS
SELECT municipio_origen_sk, municipio_destino_sk,
       COALESCE(tiempo_min_carretera, tiempo_min_est)       AS tiempo_min,
       COALESCE(distancia_km_carretera, distancia_km_recta) AS distancia_km,
       COALESCE(fuente_tiempo, 'recta_x1.8')                AS fuente_tiempo
FROM dw.fact_accesibilidad;
GRANT SELECT ON dw.v_tiempo_municipios TO anon, authenticated, service_role;

-- F2a · Calidad de cada indicador
ALTER TABLE dw.fact_infraestructura
  ADD COLUMN IF NOT EXISTS calidad text DEFAULT 'observado'
    CHECK (calidad IN ('observado', 'cero_confirmado', 'sin_dato', 'estimado'));

-- F2b · Confidencialidad del censo: personal_ocupado se lee como "al menos X"
ALTER TABLE dw.fact_censo_economico
  ADD COLUMN IF NOT EXISTS unidades_con_personal_publicado integer,
  ADD COLUMN IF NOT EXISTS pct_personal_cubierto           numeric(5,2);

-- F2c · Dominio de la predicción
ALTER TABLE dw.fact_prediccion_crecimiento
  ADD COLUMN IF NOT EXISTS unidades_base         integer,
  ADD COLUMN IF NOT EXISTS en_dominio            boolean,
  ADD COLUMN IF NOT EXISTS motivo_sin_prediccion text;

-- F5 · Rutas que se puedan operar
ALTER TABLE dw.fact_ruta_parada
  ADD COLUMN IF NOT EXISTS tiempo_desde_anterior_min_real   numeric(6,1),
  ADD COLUMN IF NOT EXISTS distancia_desde_anterior_km_real numeric(7,2),
  ADD COLUMN IF NOT EXISTS es_pernocta                      boolean DEFAULT false,
  ADD COLUMN IF NOT EXISTS unidades_hospedaje               integer;

ALTER TABLE dw.fact_ruta_evaluacion
  ADD COLUMN IF NOT EXISTS tiempo_total_min_real numeric(7,1),
  ADD COLUMN IF NOT EXISTS dias_sugeridos        smallint,
  ADD COLUMN IF NOT EXISTS region_beneficiada    text,
  ADD COLUMN IF NOT EXISTS cumple_restricciones  boolean,
  ADD COLUMN IF NOT EXISTS incumplimientos       text[],
  ADD COLUMN IF NOT EXISTS paradas_infra_rojo    smallint,
  ADD COLUMN IF NOT EXISTS riesgo_seguridad      text;
