-- REVIEW ONLY. Run after 002a_roles.sql (and 002a2) and before 001_schema.sql,
-- as the SQL Editor role postgres. Supabase's postgres is not a superuser, so it
-- needs membership in c1_owner to CREATE SCHEMA c1 AUTHORIZATION c1_owner and to
-- SET LOCAL ROLE c1_owner in 001, 002b and 004. Nothing is granted to c1_collector
-- or c1_model_reader. Keep exactly one of the two GRANT forms below uncommented,
-- chosen from server_version_num in 000_preflight_readonly.sql.

-- PostgreSQL 16 or newer (server_version_num >= 160000): SET only, no inheritance.
GRANT c1_owner TO postgres WITH INHERIT FALSE, SET TRUE;

-- PostgreSQL 15 (server_version_num < 160000): comment out the line above and use:
-- GRANT c1_owner TO postgres;
