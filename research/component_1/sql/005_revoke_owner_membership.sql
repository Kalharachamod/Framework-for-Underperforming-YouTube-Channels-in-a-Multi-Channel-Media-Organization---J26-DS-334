-- REVIEW ONLY. Optional. Run as postgres after 004 bootstrap and after the cohort
-- has been approved and enabled, to remove postgres's standing ability to act as
-- c1_owner. Re-grant it with 002a1_owner_membership.sql before any later C1
-- migration, a new cohort bootstrap, or an approval/enable/disable UPDATE on
-- c1.cohorts, because those all run as c1_owner; revoke again afterwards.
REVOKE c1_owner FROM postgres;
