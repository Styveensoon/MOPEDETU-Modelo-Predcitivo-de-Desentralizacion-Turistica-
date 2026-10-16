-- MOPEDETU · F0 del plan de afinación (docs/plan_afinacion_bd.md, D12) · Seguridad de vistas y tablas
-- Las 9 vistas de dw corrían como SECURITY DEFINER (con los permisos del dueño) y 25 tablas de dw tenían RLS
-- sin políticas. Orden obligatorio: primero las políticas de lectura, después security_invoker; al revés, la
-- ficha técnica y las rutas del tablero dejan de cargar. Idempotente.

-- 1. Política de lectura en toda tabla de dw que todavía no tenga una (dw es de lectura pública)
DO $$
DECLARE t text;
BEGIN
  FOR t IN
    SELECT c.relname FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
    WHERE n.nspname = 'dw' AND c.relkind = 'r'
      AND NOT EXISTS (SELECT 1 FROM pg_policies p WHERE p.schemaname = 'dw' AND p.tablename = c.relname)
  LOOP
    EXECUTE format('ALTER TABLE dw.%I ENABLE ROW LEVEL SECURITY', t);
    EXECUTE format('CREATE POLICY lectura_publica ON dw.%I FOR SELECT TO anon, authenticated USING (true)', t);
  END LOOP;
END $$;

-- 2. Las vistas respetan los permisos de quien consulta
ALTER VIEW dw.v_concentracion          SET (security_invoker = on);
ALTER VIEW dw.v_crecimiento_censal     SET (security_invoker = on);
ALTER VIEW dw.v_ficha_municipio        SET (security_invoker = on);
ALTER VIEW dw.v_indice_municipio       SET (security_invoker = on);
ALTER VIEW dw.v_novedad_ruta           SET (security_invoker = on);
ALTER VIEW dw.v_panel_crecimiento      SET (security_invoker = on);
ALTER VIEW dw.v_pares_rutas_existentes SET (security_invoker = on);
ALTER VIEW dw.v_perfil_municipio       SET (security_invoker = on);
ALTER VIEW dw.v_ruta_parada            SET (security_invoker = on);

-- 3. stg no se expone: sin USAGE ni SELECT para anon/authenticated
REVOKE ALL ON SCHEMA stg FROM anon, authenticated;
REVOKE ALL ON ALL TABLES IN SCHEMA stg FROM anon, authenticated;

-- 4. Función de mantenimiento expuesta por error
REVOKE EXECUTE ON FUNCTION public.rls_auto_enable() FROM PUBLIC, anon, authenticated;

-- 5. Roles de desarrollo: hoy no existen dev_raul ni dev_styveen; si se vuelven a usar, aplicar
--    DDL/04_permisos_mopedetu.sql.
