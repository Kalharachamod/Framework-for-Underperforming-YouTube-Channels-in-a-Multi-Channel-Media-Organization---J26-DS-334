-- TEST CONTAINER ONLY: the operator approval/enable SQL from the deployment
-- checklist, with synthetic approval values. Run as postgres (Supabase-like).
-- A. Approve (stays disabled)
BEGIN;
SET LOCAL ROLE c1_owner;
UPDATE c1.cohorts SET approval_status = 'approved',
  approved_by = 'synthetic-local-approver', approved_at = '2026-10-20 10:00+05:30',
  approval_reference = 'synthetic-local-approval',
  retention_decision_reference = 'synthetic-integration-retention'
WHERE cohort_id = 'component_1_derana_vs_cm' AND version = '0.3.0'
  AND approval_status = 'pending' AND NOT enabled
  AND manifest_hash = '945cecc929247adfeda0d8c9bd4d512f0cc471990d492ee7a81a73efd0b0a1bb';
DO $c$ BEGIN
  IF (SELECT count(*) FROM c1.cohorts WHERE cohort_id = 'component_1_derana_vs_cm'
      AND version = '0.3.0' AND approval_status = 'approved' AND NOT enabled) <> 1
  THEN RAISE EXCEPTION 'C1 approval did not apply'; END IF;
END $c$;
COMMIT;

-- B. Enable (separately, when ready)
BEGIN;
SET LOCAL ROLE c1_owner;
UPDATE c1.cohorts SET enabled = true
WHERE cohort_id = 'component_1_derana_vs_cm' AND version = '0.3.0'
  AND approval_status = 'approved' AND NOT enabled;
DO $c$ BEGIN
  IF (SELECT count(*) FROM c1.cohorts WHERE cohort_id = 'component_1_derana_vs_cm'
      AND version = '0.3.0' AND enabled) <> 1
  THEN RAISE EXCEPTION 'C1 enable did not apply'; END IF;
END $c$;
COMMIT;
