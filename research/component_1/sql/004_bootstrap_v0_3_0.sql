-- REVIEW ONLY. Run after 002b_access.sql, as postgres with c1_owner membership
-- (002a1). Seeds C1 from config/cohorts/component_1_derana_vs_cm_v0.3.0.proposed.json
-- only: 2 organizations, one pending/disabled cohort, 41 channels and their roles,
-- and the coordination row. No videos: the first approved discovery run seeds
-- them. Nothing is read from or written to any other schema.
-- manifest_hash is the canonical-JSON SHA-256 described in the manifest's
-- manifest_hash_method; tests/component_1/test_c1_cohort_v030.py recomputes it.
-- Plain INSERTs fail on any existing row; the DO block checks counts and flags
-- before COMMIT, so any mismatch rolls back the whole bootstrap.
BEGIN;
SET LOCAL ROLE c1_owner;

INSERT INTO c1.organizations (organization_id, name, country, is_holdout) VALUES
  ('derana', 'Derana', 'LK', false),
  ('capital_maharaja', 'Capital Maharaja', 'LK', true);

INSERT INTO c1.cohorts (cohort_id, version, manifest_hash, channel_ids,
  total_attempt_budget, discovery_attempt_budget, candidate_attempt_reserve,
  max_pages_per_channel, admission_lookback_days)
VALUES ('component_1_derana_vs_cm', '0.3.0',
  '945cecc929247adfeda0d8c9bd4d512f0cc471990d492ee7a81a73efd0b0a1bb',
  ARRAY[
    'UC0xVuSfC72x3e7ijncDLgYQ', 'UC11bd3xGXwzf_naIePO1n4g', 'UC1YAG2ZbQUjBx3b60c0Qmyg',
    'UC8fCPqq-Q3Ki3RrMyTsmckg', 'UCBNxaWOXx6B1B4CEtxoNS3Q', 'UCCK3OZi788Ok44K97WAhLKQ',
    'UCEbTQZF9_vDOducFY8gOfag', 'UCHKtXGbqRIM0hA4Manb9DNg', 'UCJr5vlnK6HEBVISUtxnq_sg',
    'UCKkzOyGRuPyea04qr7aC1NQ', 'UCLNz9bgiJfM3ImTtYDOt8Ew', 'UCOPPH1_whpThgY6e7r3qg-w',
    'UCRDDfbYPHX_GUJ4lcQYTc8A', 'UCSTl549eJYdeUAY0NmZLU6A', 'UCV1NPkc2O0YZBtx_rhDkicw',
    'UCVsi4vIpAcKl825aPQV4IjA', 'UCW_rA_jb-_vbZtU4cTpnT5Q', 'UCXFcukf9VvSWp731oQDJ7Bg',
    'UCXJQwWh7dEdEfmIaIJpZ4SQ', 'UCXhjcvbJcbtKLxjTZpO1Xvw', 'UCYPchfdlyZHi2gt2_FrLL3Q',
    'UCZ418aLcVbJDo0fc01aQDQQ', 'UC_m6TcsKwid_mmOScbuYltg', 'UCbkMFGQ_RWIf0OiYeOpf6Ng',
    'UCdCI-4lcsMaDfkhlTr550Vw', 'UCe13xXtdfx_n0_z1qeXV6_g', 'UCfnZtEDnl84njUQgtF186cA',
    'UCgnFSj7jQffD5V5m05j4dPw', 'UCir6eRv6gShvpiWR2TehHzg', 'UCjm7vbOwssao7Bhm9wX3-bw',
    'UClSmnnGOPwfN-cnhQpdR2Cg', 'UCmqflTSJ6911aCrnaWIXxsA', 'UCn0XmAUFv6d2tofMFEesSNw',
    'UCpp3TTx7OU3SmCECA1-6r3w', 'UCqrJfySpfHED-jYFNjWNIqw', 'UCrWPzTW4EjXNQGcCkCfOvog',
    'UCrZs77rjxjbn_BMaSccMXnQ', 'UCs8gVM6lPhRZk3L_zZmedpw', 'UCsExZudI-3Bfi2ubAdwcgHw',
    'UCtBhlCYSLlz2TO9hK93micg', 'UCuOtdpOPjHeoEAT4i44mVOg'
  ],
  200, 70, 20, 10, 30);

-- channel_name is starting metadata; the collector replaces it with API values.
INSERT INTO c1.channels (channel_id, organization_id, channel_name, admitted_at, admission_source)
SELECT channel_id, organization_id, channel_name, now(), 'cohort_manifest:component_1_derana_vs_cm@0.3.0'
FROM (VALUES
  ('UC_m6TcsKwid_mmOScbuYltg', 'derana', 'Derana Shorts'),
  ('UC0xVuSfC72x3e7ijncDLgYQ', 'capital_maharaja', 'Sirasa Cinescope'),
  ('UC11bd3xGXwzf_naIePO1n4g', 'derana', 'Ada Derana Tamil'),
  ('UC1YAG2ZbQUjBx3b60c0Qmyg', 'capital_maharaja', 'Sirasa Live'),
  ('UC8fCPqq-Q3Ki3RrMyTsmckg', 'capital_maharaja', 'Sirasa Dhamma - සිරස ධම්ම'),
  ('UCbkMFGQ_RWIf0OiYeOpf6Ng', 'derana', 'TV Derana LIVE'),
  ('UCBNxaWOXx6B1B4CEtxoNS3Q', 'capital_maharaja', 'Sirasa Dancing Star'),
  ('UCCK3OZi788Ok44K97WAhLKQ', 'derana', 'Ada Derana'),
  ('UCdCI-4lcsMaDfkhlTr550Vw', 'capital_maharaja', 'Sirasa tv live'),
  ('UCe13xXtdfx_n0_z1qeXV6_g', 'capital_maharaja', 'M Entertainments'),
  ('UCEbTQZF9_vDOducFY8gOfag', 'capital_maharaja', 'Sirasa Catchpoint'),
  ('UCfnZtEDnl84njUQgtF186cA', 'capital_maharaja', 'Sirasa Lakshapathi'),
  ('UCgnFSj7jQffD5V5m05j4dPw', 'capital_maharaja', 'Newsfirst Sri Lanka'),
  ('UCHKtXGbqRIM0hA4Manb9DNg', 'derana', 'Ada Derana Sports'),
  ('UCir6eRv6gShvpiWR2TehHzg', 'derana', 'Ada Derana World News'),
  ('UCjm7vbOwssao7Bhm9wX3-bw', 'capital_maharaja', 'Shakthi TV'),
  ('UCJr5vlnK6HEBVISUtxnq_sg', 'derana', 'Derana Little Star'),
  ('UCKkzOyGRuPyea04qr7aC1NQ', 'capital_maharaja', 'Shakthi FM'),
  ('UCLNz9bgiJfM3ImTtYDOt8Ew', 'capital_maharaja', 'Sirasa TV Digital'),
  ('UClSmnnGOPwfN-cnhQpdR2Cg', 'capital_maharaja', 'Kisa - Sirasa TV'),
  ('UCmqflTSJ6911aCrnaWIXxsA', 'capital_maharaja', 'The Voice Sri Lanka '),
  ('UCn0XmAUFv6d2tofMFEesSNw', 'capital_maharaja', 'Sirasa TV'),
  ('UCOPPH1_whpThgY6e7r3qg-w', 'derana', 'FM Derana'),
  ('UCpp3TTx7OU3SmCECA1-6r3w', 'capital_maharaja', 'Sirasa FM'),
  ('UCqrJfySpfHED-jYFNjWNIqw', 'capital_maharaja', '5 Million Money Drop'),
  ('UCRDDfbYPHX_GUJ4lcQYTc8A', 'derana', 'TV Derana'),
  ('UCrWPzTW4EjXNQGcCkCfOvog', 'capital_maharaja', 'Sri Lanka''s Got Talent'),
  ('UCrZs77rjxjbn_BMaSccMXnQ', 'derana', 'Derana City Of Music'),
  ('UCs8gVM6lPhRZk3L_zZmedpw', 'derana', 'Dream Star'),
  ('UCsExZudI-3Bfi2ubAdwcgHw', 'capital_maharaja', 'Y FM'),
  ('UCSTl549eJYdeUAY0NmZLU6A', 'derana', 'Ada Derana Biz'),
  ('UCtBhlCYSLlz2TO9hK93micg', 'capital_maharaja', 'The Voice Kids Sri Lanka'),
  ('UCuOtdpOPjHeoEAT4i44mVOg', 'derana', 'Ada Derana News Channel | English'),
  ('UCV1NPkc2O0YZBtx_rhDkicw', 'derana', 'Ada Derana Education'),
  ('UCVsi4vIpAcKl825aPQV4IjA', 'derana', 'Pulse.lk'),
  ('UCW_rA_jb-_vbZtU4cTpnT5Q', 'derana', 'Ada Derana News Channel'),
  ('UCXFcukf9VvSWp731oQDJ7Bg', 'capital_maharaja', 'Yes FM Sri Lanka'),
  ('UCXhjcvbJcbtKLxjTZpO1Xvw', 'capital_maharaja', 'Sirasa Subasiri'),
  ('UCXJQwWh7dEdEfmIaIJpZ4SQ', 'capital_maharaja', 'Sirasa Lunch Time TV'),
  ('UCYPchfdlyZHi2gt2_FrLL3Q', 'derana', 'Lokaya Saha Lokayo'),
  ('UCZ418aLcVbJDo0fc01aQDQQ', 'derana', 'Derana 60 Plus')
) AS seed (channel_id, organization_id, channel_name);

INSERT INTO c1.cohort_channels (cohort_id, version, channel_id, role, admitted_at)
SELECT cohort_id, version, channel_id, role, now()
FROM (VALUES
  ('component_1_derana_vs_cm', '0.3.0', 'UC_m6TcsKwid_mmOScbuYltg', 'owned'),
  ('component_1_derana_vs_cm', '0.3.0', 'UC0xVuSfC72x3e7ijncDLgYQ', 'competitor'),
  ('component_1_derana_vs_cm', '0.3.0', 'UC11bd3xGXwzf_naIePO1n4g', 'owned'),
  ('component_1_derana_vs_cm', '0.3.0', 'UC1YAG2ZbQUjBx3b60c0Qmyg', 'competitor'),
  ('component_1_derana_vs_cm', '0.3.0', 'UC8fCPqq-Q3Ki3RrMyTsmckg', 'competitor'),
  ('component_1_derana_vs_cm', '0.3.0', 'UCbkMFGQ_RWIf0OiYeOpf6Ng', 'owned'),
  ('component_1_derana_vs_cm', '0.3.0', 'UCBNxaWOXx6B1B4CEtxoNS3Q', 'competitor'),
  ('component_1_derana_vs_cm', '0.3.0', 'UCCK3OZi788Ok44K97WAhLKQ', 'owned'),
  ('component_1_derana_vs_cm', '0.3.0', 'UCdCI-4lcsMaDfkhlTr550Vw', 'competitor'),
  ('component_1_derana_vs_cm', '0.3.0', 'UCe13xXtdfx_n0_z1qeXV6_g', 'competitor'),
  ('component_1_derana_vs_cm', '0.3.0', 'UCEbTQZF9_vDOducFY8gOfag', 'competitor'),
  ('component_1_derana_vs_cm', '0.3.0', 'UCfnZtEDnl84njUQgtF186cA', 'competitor'),
  ('component_1_derana_vs_cm', '0.3.0', 'UCgnFSj7jQffD5V5m05j4dPw', 'competitor'),
  ('component_1_derana_vs_cm', '0.3.0', 'UCHKtXGbqRIM0hA4Manb9DNg', 'owned'),
  ('component_1_derana_vs_cm', '0.3.0', 'UCir6eRv6gShvpiWR2TehHzg', 'owned'),
  ('component_1_derana_vs_cm', '0.3.0', 'UCjm7vbOwssao7Bhm9wX3-bw', 'competitor'),
  ('component_1_derana_vs_cm', '0.3.0', 'UCJr5vlnK6HEBVISUtxnq_sg', 'owned'),
  ('component_1_derana_vs_cm', '0.3.0', 'UCKkzOyGRuPyea04qr7aC1NQ', 'competitor'),
  ('component_1_derana_vs_cm', '0.3.0', 'UCLNz9bgiJfM3ImTtYDOt8Ew', 'competitor'),
  ('component_1_derana_vs_cm', '0.3.0', 'UClSmnnGOPwfN-cnhQpdR2Cg', 'competitor'),
  ('component_1_derana_vs_cm', '0.3.0', 'UCmqflTSJ6911aCrnaWIXxsA', 'competitor'),
  ('component_1_derana_vs_cm', '0.3.0', 'UCn0XmAUFv6d2tofMFEesSNw', 'competitor'),
  ('component_1_derana_vs_cm', '0.3.0', 'UCOPPH1_whpThgY6e7r3qg-w', 'owned'),
  ('component_1_derana_vs_cm', '0.3.0', 'UCpp3TTx7OU3SmCECA1-6r3w', 'competitor'),
  ('component_1_derana_vs_cm', '0.3.0', 'UCqrJfySpfHED-jYFNjWNIqw', 'competitor'),
  ('component_1_derana_vs_cm', '0.3.0', 'UCRDDfbYPHX_GUJ4lcQYTc8A', 'owned'),
  ('component_1_derana_vs_cm', '0.3.0', 'UCrWPzTW4EjXNQGcCkCfOvog', 'competitor'),
  ('component_1_derana_vs_cm', '0.3.0', 'UCrZs77rjxjbn_BMaSccMXnQ', 'owned'),
  ('component_1_derana_vs_cm', '0.3.0', 'UCs8gVM6lPhRZk3L_zZmedpw', 'owned'),
  ('component_1_derana_vs_cm', '0.3.0', 'UCsExZudI-3Bfi2ubAdwcgHw', 'competitor'),
  ('component_1_derana_vs_cm', '0.3.0', 'UCSTl549eJYdeUAY0NmZLU6A', 'owned'),
  ('component_1_derana_vs_cm', '0.3.0', 'UCtBhlCYSLlz2TO9hK93micg', 'competitor'),
  ('component_1_derana_vs_cm', '0.3.0', 'UCuOtdpOPjHeoEAT4i44mVOg', 'owned'),
  ('component_1_derana_vs_cm', '0.3.0', 'UCV1NPkc2O0YZBtx_rhDkicw', 'owned'),
  ('component_1_derana_vs_cm', '0.3.0', 'UCVsi4vIpAcKl825aPQV4IjA', 'owned'),
  ('component_1_derana_vs_cm', '0.3.0', 'UCW_rA_jb-_vbZtU4cTpnT5Q', 'owned'),
  ('component_1_derana_vs_cm', '0.3.0', 'UCXFcukf9VvSWp731oQDJ7Bg', 'competitor'),
  ('component_1_derana_vs_cm', '0.3.0', 'UCXhjcvbJcbtKLxjTZpO1Xvw', 'competitor'),
  ('component_1_derana_vs_cm', '0.3.0', 'UCXJQwWh7dEdEfmIaIJpZ4SQ', 'competitor'),
  ('component_1_derana_vs_cm', '0.3.0', 'UCYPchfdlyZHi2gt2_FrLL3Q', 'owned'),
  ('component_1_derana_vs_cm', '0.3.0', 'UCZ418aLcVbJDo0fc01aQDQQ', 'owned')
) AS seed (cohort_id, version, channel_id, role);

INSERT INTO c1.collection_coordination (cohort_id, version) VALUES ('component_1_derana_vs_cm', '0.3.0');

DO $verify$
BEGIN
  IF (SELECT count(*) FROM c1.organizations) <> 2
    OR (SELECT count(*) FROM c1.organizations WHERE is_holdout) <> 1
    OR NOT EXISTS (SELECT 1 FROM c1.organizations WHERE organization_id = 'capital_maharaja' AND is_holdout)
    OR (SELECT count(*) FROM c1.channels) <> 41
    OR (SELECT count(*) FROM c1.cohort_channels WHERE cohort_id = 'component_1_derana_vs_cm' AND version = '0.3.0') <> 41
    OR (SELECT count(*) FROM c1.cohort_channels WHERE role = 'owned') <> 18
    OR (SELECT count(*) FROM c1.cohort_channels WHERE role = 'competitor') <> 23
    OR (SELECT count(*) FROM c1.videos) <> 0
    OR NOT EXISTS (SELECT 1 FROM c1.cohorts WHERE cohort_id = 'component_1_derana_vs_cm' AND version = '0.3.0'
      AND approval_status = 'pending' AND NOT enabled AND cardinality(channel_ids) = 41)
  THEN
    RAISE EXCEPTION 'C1 bootstrap verification failed';
  END IF;
  RAISE NOTICE 'C1 bootstrap OK: 2 organizations, 41 channels (18 owned, 23 competitor), cohort pending and disabled';
END; $verify$;
COMMIT;
