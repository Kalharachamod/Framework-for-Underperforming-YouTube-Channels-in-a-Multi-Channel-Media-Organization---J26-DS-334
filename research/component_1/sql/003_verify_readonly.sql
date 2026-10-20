-- REVIEW ONLY: catalog queries for a separately authorized future audit.
-- Run this file as c1_collector; default output is identity/privilege metadata.
-- No configuration values or raw definitions are included. Detailed definition
-- review is a separate local inspection and must not be blindly exported.
-- No DDL/DML, canary writes, EXPLAIN ANALYZE, or SET ROLE attempts here.
BEGIN READ ONLY;
SELECT session_user, current_user, current_database();
SELECT rolname, rolsuper, rolinherit, rolcreaterole, rolcreatedb,
  rolcanlogin, rolreplication, rolbypassrls
FROM pg_roles WHERE rolname IN ('c1_owner','c1_collector');

-- Include SET-reachable membership even with NOINHERIT. UNION prevents cycles.
WITH RECURSIVE reachable(oid) AS (
  SELECT oid FROM pg_roles WHERE rolname = current_user
  UNION SELECT m.roleid FROM pg_auth_members m JOIN reachable r ON m.member = r.oid
)
SELECT p.rolname, p.rolsuper, p.rolcreaterole, p.rolcreatedb, p.rolbypassrls
FROM reachable r JOIN pg_roles p ON p.oid = r.oid;
SELECT rolname,
  pg_has_role(current_user, oid, 'MEMBER') AS member_path,
  pg_has_role(current_user, oid, 'USAGE') AS inherited_now
FROM pg_roles;
SELECT parent.rolname AS granted_role, child.rolname AS member,
  m.admin_option, to_jsonb(m) - 'grantor' AS membership_options
FROM pg_auth_members m JOIN pg_roles parent ON parent.oid = m.roleid
JOIN pg_roles child ON child.oid = m.member
WHERE child.rolname IN ('c1_owner','c1_collector');

SELECT d.datname, p.privilege,
  has_database_privilege(current_user, d.oid, p.privilege) AS effective,
  pg_get_userbyid(d.datdba) AS owner, d.datacl
FROM pg_database d CROSS JOIN (VALUES ('CONNECT'),('CREATE'),('TEMP')) p(privilege)
WHERE d.datname = current_database();
SELECT n.nspname, pg_get_userbyid(n.nspowner) AS owner, n.nspacl,
  has_schema_privilege(current_user, n.oid, 'USAGE') AS can_use,
  has_schema_privilege(current_user, n.oid, 'CREATE') AS can_create
FROM pg_namespace n WHERE n.nspname NOT LIKE 'pg_%' AND n.nspname <> 'information_schema';

-- Effective rights include direct, inherited and PUBLIC grants. Inspect raw
-- ACLs as well, and repeat the audit under each reachable role if necessary.
SELECT n.nspname, c.relname, c.relkind, pg_get_userbyid(c.relowner) AS owner,
  c.relacl, c.relrowsecurity, c.relforcerowsecurity, p.privilege,
  has_table_privilege(current_user, c.oid, p.privilege) AS effective
FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
CROSS JOIN (VALUES ('SELECT'),('INSERT'),('UPDATE'),('DELETE'),('TRUNCATE'),('REFERENCES'),('TRIGGER')) p(privilege)
WHERE c.relkind IN ('r','p','v','m','f') AND n.nspname NOT LIKE 'pg_%'
  AND n.nspname <> 'information_schema';
SELECT n.nspname, c.relname, a.attname, a.attacl, p.privilege,
  has_column_privilege(current_user, c.oid, a.attnum, p.privilege) AS effective
FROM pg_attribute a JOIN pg_class c ON c.oid = a.attrelid
JOIN pg_namespace n ON n.oid = c.relnamespace
CROSS JOIN (VALUES ('SELECT'),('INSERT'),('UPDATE'),('REFERENCES')) p(privilege)
WHERE a.attnum > 0 AND NOT a.attisdropped AND c.relkind IN ('r','p','v','f')
  AND n.nspname NOT LIKE 'pg_%' AND n.nspname <> 'information_schema';
SELECT n.nspname, c.relname, c.relacl, p.privilege,
  has_sequence_privilege(current_user, c.oid, p.privilege) AS effective
FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
CROSS JOIN (VALUES ('SELECT'),('USAGE'),('UPDATE')) p(privilege) WHERE c.relkind = 'S';

-- PUBLIC EXECUTE defaults, SECURITY DEFINER and reachable extension routines
-- can defeat table-level isolation; metadata review must trace their effects.
SELECT n.nspname, p.proname, pg_get_function_identity_arguments(p.oid) AS arguments,
  p.oid AS routine_oid, pg_get_userbyid(p.proowner) AS owner,
  p.prosecdef, (p.proconfig IS NOT NULL) AS has_local_configuration, p.proacl,
  has_function_privilege(current_user, p.oid, 'EXECUTE') AS can_execute
FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace;
SELECT pg_get_userbyid(defaclrole) AS owner, defaclnamespace::regnamespace,
  defaclobjtype, defaclacl FROM pg_default_acl;
-- Explicit PUBLIC entries, including default ACL when relacl is NULL.
SELECT n.nspname, c.relname, a.privilege_type, a.is_grantable
FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
CROSS JOIN LATERAL aclexplode(coalesce(c.relacl,
  acldefault(CASE WHEN c.relkind = 'S' THEN 'S'::"char" ELSE 'r'::"char" END, c.relowner))) a
WHERE c.relkind IN ('r','p','v','m','f','S') AND a.grantee = 0
  AND n.nspname NOT LIKE 'pg_%' AND n.nspname <> 'information_schema';
SELECT schemaname, tablename, policyname, permissive, roles, cmd,
  (qual IS NOT NULL) AS has_using_expression,
  (with_check IS NOT NULL) AS has_check_expression
FROM pg_policies WHERE schemaname IN ('c1','research','annotation');
SELECT n.nspname, c.relname, pg_get_userbyid(c.relowner) AS owner,
  t.oid AS trigger_oid, t.tgname, t.tgfoid AS routine_oid,
  t.tgfoid::regprocedure AS routine, t.tgenabled
FROM pg_trigger t JOIN pg_class c ON c.oid = t.tgrelid
JOIN pg_namespace n ON n.oid = c.relnamespace WHERE NOT t.tgisinternal;
SELECT n.nspname, c.relname, pg_get_userbyid(c.relowner) AS owner,
  r.oid AS rule_oid, r.rulename, r.ev_class AS relation_oid,
  r.ev_type, r.ev_enabled, r.is_instead
FROM pg_rewrite r JOIN pg_class c ON c.oid = r.ev_class
JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE n.nspname NOT LIKE 'pg_%' AND n.nspname <> 'information_schema';
SELECT n.nspname, c.relname, c.oid AS relation_oid, c.relkind,
  pg_get_userbyid(c.relowner) AS owner
FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE c.relkind IN ('v','m') AND n.nspname NOT LIKE 'pg_%'
  AND n.nspname <> 'information_schema';
-- C1 model views: expect owner c1_owner, security_barrier=true, security_invoker=false.
SELECT c.relname, pg_get_userbyid(c.relowner) AS owner, c.reloptions
FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE n.nspname = 'c1' AND c.relkind = 'v';
-- Dependency identifiers support subsequent targeted local definition review.
SELECT classid, objid, objsubid, refclassid, refobjid, refobjsubid, deptype
FROM pg_depend;
SELECT extname, extnamespace::regnamespace, extowner::regrole FROM pg_extension;
SELECT n.nspname, c.relname, f.ftserver
FROM pg_foreign_table f JOIN pg_class c ON c.oid = f.ftrelid
JOIN pg_namespace n ON n.oid = c.relnamespace;
-- Do not export user mappings, connection strings, vault values or function
-- bodies blindly: operator review of routine dependencies must redact secrets.
ROLLBACK;
