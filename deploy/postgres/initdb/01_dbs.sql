-- PixelProwlers Studio — Postgres init (Sprint 0)
-- Creates two application databases (pxp_app, pxp_n8n) and least‑privileged users.
-- This script is idempotent and safe to run at container bootstrap.
--
-- IMPORTANT (local/dev only):
-- - Replace the example passwords below via environment or a secrets manager
--   in real environments. This file is meant for local bootstrap.
--
-- Model:
--   For each DB:
--     - An OWNER role (NOLOGIN) owns the database & objects (for migrations/admin).
--     - An APP role (LOGIN, least-privileged) is used by the running service.
--     - Deny-by-default: revoke PUBLIC create on schema; grant only what's needed.
--
--   pxp_app:    pxp_app_owner (NOLOGIN)   +   pxp_app_user (LOGIN)
--   pxp_n8n:    pxp_n8n_owner (NOLOGIN)   +   pxp_n8n_user (LOGIN)
--
-- Passwords here are placeholders for local development:
--   pxp_app_user  : pxp_app_pass
--   pxp_n8n_user  : pxp_n8n_pass
--
-- Notes:
-- - ALTER DEFAULT PRIVILEGES ensures future tables/sequences created by OWNER grant
--   CRUD/USAGE to the APP user.
-- - The APP user cannot create/alter schema; only OWNER can (migrations/admin).
-- - If you need the APP user to CREATE TEMP tables: GRANT TEMP ON DATABASE ... TO app_user;

---------------------------------------------------------------------------------------------------
-- Roles (idempotent)
---------------------------------------------------------------------------------------------------
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'pxp_app_owner') THEN
    CREATE ROLE pxp_app_owner NOLOGIN;
  END IF;

  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'pxp_app_user') THEN
    CREATE ROLE pxp_app_user
      LOGIN
      NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT
      PASSWORD 'pxp_app_pass';
  END IF;

  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'pxp_n8n_owner') THEN
    CREATE ROLE pxp_n8n_owner NOLOGIN;
  END IF;

  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'pxp_n8n_user') THEN
    CREATE ROLE pxp_n8n_user
      LOGIN
      NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT
      PASSWORD 'pxp_n8n_pass';
  END IF;
END
$$ LANGUAGE plpgsql;

---------------------------------------------------------------------------------------------------
-- Databases (idempotent): pxp_app, pxp_n8n
---------------------------------------------------------------------------------------------------
-- Conditional CREATE DATABASE using psql \gexec (CREATE DATABASE is not allowed inside DO)
SELECT 'CREATE DATABASE pxp_app OWNER pxp_app_owner'
WHERE NOT EXISTS (SELECT 1 FROM pg_database WHERE datname = 'pxp_app');
\gexec

SELECT 'CREATE DATABASE pxp_n8n OWNER pxp_n8n_owner'
WHERE NOT EXISTS (SELECT 1 FROM pg_database WHERE datname = 'pxp_n8n');
\gexec

---------------------------------------------------------------------------------------------------
-- pxp_app: privileges & defaults
---------------------------------------------------------------------------------------------------
-- Allow app user to connect; no CREATE at DB level (owner handles migrations).
GRANT CONNECT ON DATABASE pxp_app TO pxp_app_user;

-- Switch to pxp_app to configure schema-level privileges & defaults.
\connect pxp_app

-- Revoke dangerous defaults; only owner (pxp_app_owner) should create objects.
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
GRANT USAGE ON SCHEMA public TO pxp_app_user;

-- Ensure the DB owner is the dedicated owner role (defense in depth).
ALTER DATABASE pxp_app OWNER TO pxp_app_owner;

-- Optionally ensure public schema is owned by the DB owner (so migrations by owner are coherent).
ALTER SCHEMA public OWNER TO pxp_app_owner;

-- Default privileges: future objects created by OWNER grant least-privileged access to APP user.
ALTER DEFAULT PRIVILEGES FOR ROLE pxp_app_owner IN SCHEMA public
  GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO pxp_app_user;

ALTER DEFAULT PRIVILEGES FOR ROLE pxp_app_owner IN SCHEMA public
  GRANT USAGE, SELECT, UPDATE ON SEQUENCES TO pxp_app_user;

-- (If you plan to use functions from APP user)
-- ALTER DEFAULT PRIVILEGES FOR ROLE pxp_app_owner IN SCHEMA public
--   GRANT EXECUTE ON FUNCTIONS TO pxp_app_user;

---------------------------------------------------------------------------------------------------
-- pxp_n8n: privileges & defaults
---------------------------------------------------------------------------------------------------
GRANT CONNECT ON DATABASE pxp_n8n TO pxp_n8n_user;

\connect pxp_n8n

REVOKE CREATE ON SCHEMA public FROM PUBLIC;
GRANT USAGE ON SCHEMA public TO pxp_n8n_user;

ALTER DATABASE pxp_n8n OWNER TO pxp_n8n_owner;
ALTER SCHEMA public OWNER TO pxp_n8n_owner;

ALTER DEFAULT PRIVILEGES FOR ROLE pxp_n8n_owner IN SCHEMA public
  GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO pxp_n8n_user;

ALTER DEFAULT PRIVILEGES FOR ROLE pxp_n8n_owner IN SCHEMA public
  GRANT USAGE, SELECT, UPDATE ON SEQUENCES TO pxp_n8n_user;

-- (Optional)
-- ALTER DEFAULT PRIVILEGES FOR ROLE pxp_n8n_owner IN SCHEMA public
--   GRANT EXECUTE ON FUNCTIONS TO pxp_n8n_user;

---------------------------------------------------------------------------------------------------
-- End of init script
---------------------------------------------------------------------------------------------------
