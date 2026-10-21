-- REVIEW ONLY. Read-only preflight; run first in the SQL Editor. Changes nothing.
-- One SELECT so the editor shows every value in a single result row.
-- Use server_version_num to choose the GRANT form in 002a1_owner_membership.sql.
-- 001_schema.sql uses the view option security_invoker, which needs PostgreSQL 15+.
SELECT
  current_setting('server_version') AS server_version,
  current_setting('server_version_num')::integer AS server_version_num,
  CASE
    WHEN current_setting('server_version_num')::integer >= 160000
      THEN 'PG16+: use GRANT c1_owner TO postgres WITH INHERIT FALSE, SET TRUE'
    WHEN current_setting('server_version_num')::integer >= 150000
      THEN 'PG15: use the plain GRANT c1_owner TO postgres form'
    ELSE 'STOP: PostgreSQL 15 or newer is required'
  END AS grant_form_for_002a1,
  session_user,
  current_user,
  r.rolsuper AS current_user_is_superuser,
  r.rolcreaterole AS current_user_can_create_roles,
  has_database_privilege(current_database(), 'CREATE') AS current_user_can_create_schema,
  (SELECT string_agg(rolname, ',' ORDER BY rolname) FROM pg_roles
    WHERE rolname IN ('c1_owner','c1_collector','c1_model_reader')) AS existing_c1_roles_expected_null,
  EXISTS (SELECT 1 FROM pg_namespace WHERE nspname = 'c1') AS c1_schema_exists_expected_false
FROM pg_roles r
WHERE r.rolname = current_user;
