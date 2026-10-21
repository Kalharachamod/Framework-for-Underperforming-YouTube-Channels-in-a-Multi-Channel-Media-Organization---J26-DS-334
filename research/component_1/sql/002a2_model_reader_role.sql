-- REVIEW ONLY. Separate administrative provisioning transaction, run after
-- 002a_roles.sql. Plain CREATE deliberately fails if the role already exists.
-- c1_model_reader is the only login model code uses. 002b grants it SELECT on
-- c1.training_observations and c1.evaluation_observations only, never on the
-- base tables. No password is provisioned here; set it separately.
BEGIN;
CREATE ROLE c1_model_reader LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOREPLICATION NOBYPASSRLS;
COMMIT;
