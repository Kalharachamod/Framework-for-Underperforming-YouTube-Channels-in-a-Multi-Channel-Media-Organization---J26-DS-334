-- REVIEW ONLY. Separate administrative provisioning transaction.
-- Plain CREATE deliberately fails if either role already exists. No passwords.
-- LOGIN has no usable password provisioned here; secure authentication is a
-- separately authorized operational step. Operator needs SET ROLE c1_owner
-- capability through the deployment environment; do not grant it to collector.
BEGIN;
CREATE ROLE c1_owner NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOREPLICATION NOBYPASSRLS;
CREATE ROLE c1_collector LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOREPLICATION NOBYPASSRLS;
COMMIT;