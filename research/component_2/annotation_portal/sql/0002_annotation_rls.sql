-- 0002_annotation_rls.sql
-- Server-side access controls for Component 2 annotation tables.
-- Prepared only; review and apply with approval.
--
-- Three database roles are deliberately separated:
--   annotation_app      participant sessions only
--   annotation_admin    researcher export/revoke only
--   annotation_importer snapshot/context import only
--
-- All roles are created NOLOGIN. Configure separate LOGIN passwords out of
-- band after review. Never give any role SUPERUSER, ownership, or BYPASSRLS.

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'annotation_app') THEN
        CREATE ROLE annotation_app NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOREPLICATION NOBYPASSRLS;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'annotation_admin') THEN
        CREATE ROLE annotation_admin NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOREPLICATION NOBYPASSRLS;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'annotation_importer') THEN
        CREATE ROLE annotation_importer NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOREPLICATION NOBYPASSRLS;
    END IF;
END
$$;

-- Harden existing roles without changing their LOGIN state. LOGIN/password
-- setup is an explicit out-of-band deployment step and can be rotated safely.
ALTER ROLE annotation_app
    NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOREPLICATION NOBYPASSRLS;
ALTER ROLE annotation_admin
    NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOREPLICATION NOBYPASSRLS;
ALTER ROLE annotation_importer
    NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOREPLICATION NOBYPASSRLS;

ALTER TABLE annotation.annotation_runs     ENABLE ROW LEVEL SECURITY;
ALTER TABLE annotation.sections            ENABLE ROW LEVEL SECURITY;
ALTER TABLE annotation.comments            ENABLE ROW LEVEL SECURITY;
ALTER TABLE annotation.section_assignments ENABLE ROW LEVEL SECURITY;
ALTER TABLE annotation.participants        ENABLE ROW LEVEL SECURITY;
ALTER TABLE annotation.responses           ENABLE ROW LEVEL SECURITY;
ALTER TABLE annotation.researcher_admins   ENABLE ROW LEVEL SECURITY;
ALTER TABLE annotation.adjudications       ENABLE ROW LEVEL SECURITY;

ALTER TABLE annotation.annotation_runs     FORCE ROW LEVEL SECURITY;
ALTER TABLE annotation.sections            FORCE ROW LEVEL SECURITY;
ALTER TABLE annotation.comments            FORCE ROW LEVEL SECURITY;
ALTER TABLE annotation.section_assignments FORCE ROW LEVEL SECURITY;
ALTER TABLE annotation.participants        FORCE ROW LEVEL SECURITY;
ALTER TABLE annotation.responses           FORCE ROW LEVEL SECURITY;
ALTER TABLE annotation.researcher_admins   FORCE ROW LEVEL SECURITY;
ALTER TABLE annotation.adjudications       FORCE ROW LEVEL SECURITY;

CREATE OR REPLACE FUNCTION annotation.current_operation()
RETURNS text
LANGUAGE sql
STABLE
SET search_path = pg_catalog, annotation
AS $$
    SELECT current_setting('annotation.operation', true)
$$;

CREATE OR REPLACE FUNCTION annotation.current_run_id()
RETURNS text
LANGUAGE sql
STABLE
SET search_path = pg_catalog, annotation
AS $$
    SELECT current_setting('annotation.run_id', true)
$$;

CREATE OR REPLACE FUNCTION annotation.current_participant_id()
RETURNS text
LANGUAGE sql
STABLE
SET search_path = pg_catalog, annotation
AS $$
    SELECT current_setting('annotation.participant_id', true)
$$;

CREATE OR REPLACE FUNCTION annotation.current_admin_id()
RETURNS text
LANGUAGE sql
STABLE
SET search_path = pg_catalog, annotation
AS $$
    SELECT current_setting('annotation.admin_id', true)
$$;

CREATE OR REPLACE FUNCTION annotation.is_active_admin()
RETURNS boolean
LANGUAGE sql
STABLE
SET search_path = pg_catalog, annotation
AS $$
    SELECT EXISTS (
        SELECT 1
        FROM annotation.researcher_admins a
        WHERE a.admin_id = annotation.current_admin_id()
          AND a.active = true
    )
$$;

-- Return-code lookup is deliberately narrowed to one exact hash. The public
-- Streamlit app never receives or queries the participants table directly.
-- Keep this function owned by the controlled migration owner, never an app role.
CREATE OR REPLACE FUNCTION annotation.resume_participant(p_run_id text, p_return_code_hash text)
RETURNS TABLE (
    participant_id text,
    display_name text,
    section_id text,
    section_label text,
    assignment_template text,
    active boolean
)
LANGUAGE sql
SECURITY DEFINER
SET search_path = pg_catalog, annotation
AS $$
    SELECT p.participant_id, p.display_name, p.section_id,
           s.section_label, s.assignment_template, p.active
    FROM annotation.participants p
    JOIN annotation.sections s
      ON s.run_id = p.run_id AND s.section_id = p.section_id
    WHERE p.run_id = p_run_id
      AND p.return_code_hash = p_return_code_hash
      AND p.active = true
    LIMIT 1
$$;

-- Participant application role: session setup and own assigned data only.
DROP POLICY IF EXISTS annotation_runs_app_select ON annotation.annotation_runs;
CREATE POLICY annotation_runs_app_select ON annotation.annotation_runs
FOR SELECT TO annotation_app
USING (
    run_id = annotation.current_run_id()
    AND annotation.current_operation() = 'participant_session'
);

DROP POLICY IF EXISTS sections_app_select ON annotation.sections;
CREATE POLICY sections_app_select ON annotation.sections
FOR SELECT TO annotation_app
USING (
    run_id = annotation.current_run_id()
    AND (
        annotation.current_operation() = 'participant_create'
        OR (
            annotation.current_operation() = 'participant_session'
            AND EXISTS (
                SELECT 1 FROM annotation.participants p
                WHERE p.run_id = sections.run_id
                  AND p.section_id = sections.section_id
                  AND p.participant_id = annotation.current_participant_id()
                  AND p.active = true
            )
        )
    )
);

DROP POLICY IF EXISTS comments_app_select ON annotation.comments;
CREATE POLICY comments_app_select ON annotation.comments
FOR SELECT TO annotation_app
USING (
    run_id = annotation.current_run_id()
    AND annotation.current_operation() = 'participant_session'
    AND EXISTS (
        SELECT 1
        FROM annotation.section_assignments sa
        JOIN annotation.participants p
          ON p.run_id = sa.run_id AND p.section_id = sa.section_id
        WHERE sa.run_id = comments.run_id
          AND sa.comment_id = comments.comment_id
          AND p.participant_id = annotation.current_participant_id()
          AND p.active = true
    )
);

DROP POLICY IF EXISTS section_assignments_app_select ON annotation.section_assignments;
CREATE POLICY section_assignments_app_select ON annotation.section_assignments
FOR SELECT TO annotation_app
USING (
    run_id = annotation.current_run_id()
    AND annotation.current_operation() = 'participant_session'
    AND EXISTS (
        SELECT 1 FROM annotation.participants p
        WHERE p.run_id = section_assignments.run_id
          AND p.section_id = section_assignments.section_id
          AND p.participant_id = annotation.current_participant_id()
          AND p.active = true
    )
);

DROP POLICY IF EXISTS participants_app_select ON annotation.participants;
CREATE POLICY participants_app_select ON annotation.participants
FOR SELECT TO annotation_app
USING (
    run_id = annotation.current_run_id()
    AND participant_id = annotation.current_participant_id()
);

DROP POLICY IF EXISTS participants_app_insert ON annotation.participants;
CREATE POLICY participants_app_insert ON annotation.participants
FOR INSERT TO annotation_app
WITH CHECK (
    run_id = annotation.current_run_id()
    AND annotation.current_operation() = 'participant_create'
    AND (
        (section_id = 'primary_researcher' AND participant_role = 'primary_researcher')
        OR (section_id <> 'primary_researcher' AND participant_role = 'section_annotator')
    )
);

DROP POLICY IF EXISTS responses_app_select ON annotation.responses;
CREATE POLICY responses_app_select ON annotation.responses
FOR SELECT TO annotation_app
USING (
    run_id = annotation.current_run_id()
    AND participant_id = annotation.current_participant_id()
);

DROP POLICY IF EXISTS responses_app_insert ON annotation.responses;
CREATE POLICY responses_app_insert ON annotation.responses
FOR INSERT TO annotation_app
WITH CHECK (
    run_id = annotation.current_run_id()
    AND participant_id = annotation.current_participant_id()
    AND annotation.current_operation() = 'participant_response'
);

DROP POLICY IF EXISTS responses_app_update ON annotation.responses;
CREATE POLICY responses_app_update ON annotation.responses
FOR UPDATE TO annotation_app
USING (
    run_id = annotation.current_run_id()
    AND participant_id = annotation.current_participant_id()
    AND annotation.current_operation() = 'participant_response'
)
WITH CHECK (
    run_id = annotation.current_run_id()
    AND participant_id = annotation.current_participant_id()
);

-- Researcher-admin role: export and revoke only after active-admin validation.
DROP POLICY IF EXISTS sections_admin_select ON annotation.sections;
CREATE POLICY sections_admin_select ON annotation.sections
FOR SELECT TO annotation_admin
USING (
    run_id = annotation.current_run_id()
    AND annotation.current_operation() = 'admin_export'
    AND annotation.is_active_admin()
);

DROP POLICY IF EXISTS section_assignments_admin_select ON annotation.section_assignments;
CREATE POLICY section_assignments_admin_select ON annotation.section_assignments
FOR SELECT TO annotation_admin
USING (
    run_id = annotation.current_run_id()
    AND annotation.current_operation() = 'admin_export'
    AND annotation.is_active_admin()
);

DROP POLICY IF EXISTS participants_admin_select ON annotation.participants;
CREATE POLICY participants_admin_select ON annotation.participants
FOR SELECT TO annotation_admin
USING (
    run_id = annotation.current_run_id()
    AND annotation.current_operation() IN ('admin_export', 'admin_revoke')
    AND annotation.is_active_admin()
);

DROP POLICY IF EXISTS participants_admin_update ON annotation.participants;
CREATE POLICY participants_admin_update ON annotation.participants
FOR UPDATE TO annotation_admin
USING (
    run_id = annotation.current_run_id()
    AND annotation.current_operation() = 'admin_revoke'
    AND annotation.is_active_admin()
)
WITH CHECK (run_id = annotation.current_run_id());

DROP POLICY IF EXISTS responses_admin_select ON annotation.responses;
CREATE POLICY responses_admin_select ON annotation.responses
FOR SELECT TO annotation_admin
USING (
    run_id = annotation.current_run_id()
    AND annotation.current_operation() = 'admin_export'
    AND annotation.is_active_admin()
);

DROP POLICY IF EXISTS researcher_admins_admin_select ON annotation.researcher_admins;
CREATE POLICY researcher_admins_admin_select ON annotation.researcher_admins
FOR SELECT TO annotation_admin
USING (
    admin_id = annotation.current_admin_id()
    AND active = true
);

DROP POLICY IF EXISTS adjudications_admin_select ON annotation.adjudications;
CREATE POLICY adjudications_admin_select ON annotation.adjudications
FOR SELECT TO annotation_admin
USING (
    run_id = annotation.current_run_id()
    AND annotation.current_operation() = 'admin_export'
    AND annotation.is_active_admin()
);

-- Importer role: snapshot/context tables only. It cannot read or write human
-- responses, participants, admins, or adjudications.
DROP POLICY IF EXISTS runs_import_select ON annotation.annotation_runs;
CREATE POLICY runs_import_select ON annotation.annotation_runs
FOR SELECT TO annotation_importer
USING (
    run_id = annotation.current_run_id()
    AND annotation.current_operation() = 'snapshot_import'
);

DROP POLICY IF EXISTS runs_import_insert ON annotation.annotation_runs;
CREATE POLICY runs_import_insert ON annotation.annotation_runs
FOR INSERT TO annotation_importer
WITH CHECK (
    run_id = annotation.current_run_id()
    AND annotation.current_operation() = 'snapshot_import'
);

DROP POLICY IF EXISTS runs_import_update ON annotation.annotation_runs;
CREATE POLICY runs_import_update ON annotation.annotation_runs
FOR UPDATE TO annotation_importer
USING (
    run_id = annotation.current_run_id()
    AND annotation.current_operation() = 'snapshot_import'
)
WITH CHECK (run_id = annotation.current_run_id());

DROP POLICY IF EXISTS sections_import_write ON annotation.sections;
CREATE POLICY sections_import_write ON annotation.sections
FOR ALL TO annotation_importer
USING (
    run_id = annotation.current_run_id()
    AND annotation.current_operation() = 'snapshot_import'
)
WITH CHECK (
    run_id = annotation.current_run_id()
    AND annotation.current_operation() = 'snapshot_import'
);

DROP POLICY IF EXISTS comments_import_write ON annotation.comments;
CREATE POLICY comments_import_write ON annotation.comments
FOR ALL TO annotation_importer
USING (
    run_id = annotation.current_run_id()
    AND annotation.current_operation() = 'snapshot_import'
)
WITH CHECK (
    run_id = annotation.current_run_id()
    AND annotation.current_operation() = 'snapshot_import'
);

DROP POLICY IF EXISTS assignments_import_write ON annotation.section_assignments;
CREATE POLICY assignments_import_write ON annotation.section_assignments
FOR ALL TO annotation_importer
USING (
    run_id = annotation.current_run_id()
    AND annotation.current_operation() = 'snapshot_import'
)
WITH CHECK (
    run_id = annotation.current_run_id()
    AND annotation.current_operation() = 'snapshot_import'
);

-- Remove inherited/default access before granting only the role-specific paths.
REVOKE ALL ON SCHEMA annotation FROM PUBLIC, anon, authenticated;
REVOKE ALL ON ALL TABLES IN SCHEMA annotation FROM PUBLIC, anon, authenticated;
REVOKE ALL ON ALL SEQUENCES IN SCHEMA annotation FROM PUBLIC, anon, authenticated;
REVOKE ALL ON ALL FUNCTIONS IN SCHEMA annotation FROM PUBLIC, anon, authenticated;
REVOKE ALL ON ALL TABLES IN SCHEMA annotation FROM annotation_app, annotation_admin, annotation_importer;
REVOKE ALL ON ALL SEQUENCES IN SCHEMA annotation FROM annotation_app, annotation_admin, annotation_importer;
REVOKE ALL ON ALL FUNCTIONS IN SCHEMA annotation FROM annotation_app, annotation_admin, annotation_importer;

GRANT USAGE ON SCHEMA annotation TO annotation_app, annotation_admin, annotation_importer;

GRANT EXECUTE ON FUNCTION annotation.current_operation() TO annotation_app, annotation_admin, annotation_importer;
GRANT EXECUTE ON FUNCTION annotation.current_run_id() TO annotation_app, annotation_admin, annotation_importer;
GRANT EXECUTE ON FUNCTION annotation.current_participant_id() TO annotation_app, annotation_admin, annotation_importer;
GRANT EXECUTE ON FUNCTION annotation.current_admin_id() TO annotation_app, annotation_admin, annotation_importer;
GRANT EXECUTE ON FUNCTION annotation.is_active_admin() TO annotation_admin;
GRANT EXECUTE ON FUNCTION annotation.resume_participant(text, text) TO annotation_app;
REVOKE ALL ON FUNCTION annotation.resume_participant(text, text) FROM PUBLIC, anon, authenticated;

GRANT SELECT ON annotation.annotation_runs, annotation.sections,
    annotation.comments, annotation.section_assignments TO annotation_app;
GRANT SELECT ON annotation.responses TO annotation_app;
GRANT INSERT (
    run_id, participant_id, display_name, section_id,
    participant_role, return_code_hash, active
) ON annotation.participants TO annotation_app;
GRANT SELECT (
    run_id, participant_id, display_name, section_id,
    participant_role, active, created_at, updated_at
) ON annotation.participants TO annotation_app;
GRANT INSERT, UPDATE ON annotation.responses TO annotation_app;

GRANT SELECT ON annotation.sections, annotation.section_assignments,
    annotation.responses, annotation.researcher_admins,
    annotation.adjudications TO annotation_admin;
GRANT SELECT (
    run_id, participant_id, display_name, section_id,
    participant_role, active, created_at, updated_at
) ON annotation.participants TO annotation_admin;
GRANT UPDATE (active, updated_at) ON annotation.participants TO annotation_admin;

GRANT SELECT, INSERT, UPDATE ON annotation.annotation_runs,
    annotation.sections, annotation.comments,
    annotation.section_assignments TO annotation_importer;

-- Do not grant anon or authenticated access. Do not expose annotation or
-- research through the public REST API for this server-side connection.
