-- =============================================================================
-- MOPEDETU · Permisos para los roles del equipo (sin contraseñas).
-- Los roles se crean con scripts/crear_roles.py (genera contraseñas y no las sube a Git).
-- Idempotente; volver a ejecutar si se crean tablas con otro usuario.
-- =============================================================================
GRANT USAGE ON SCHEMA stg, dw, extensions TO dev_raul, dev_styveen;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA stg, dw TO dev_raul, dev_styveen;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA stg, dw TO dev_raul, dev_styveen;

-- Tablas y secuencias que se creen después (por el usuario que ejecuta los DDL).
ALTER DEFAULT PRIVILEGES IN SCHEMA stg, dw
    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO dev_raul, dev_styveen;
ALTER DEFAULT PRIVILEGES IN SCHEMA stg, dw
    GRANT USAGE, SELECT ON SEQUENCES TO dev_raul, dev_styveen;

ALTER ROLE dev_raul    SET search_path = public, extensions;
ALTER ROLE dev_styveen SET search_path = public, extensions;
