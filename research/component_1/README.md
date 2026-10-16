# Component 1

**Channel-Specific Growth Opportunity Prediction with Pooled Learning**
Owner: Samarasinghe S I (IT23333802)

## Planned modules
- Normalised indicators (views/subscriber, views/day, likes and comments per 1,000 views)
- Channel-relative growth labels (above-baseline, top-quartile)
- Similarity-weighted pooled learning across niche-similar channels
- Baselines: Random Forest, XGBoost, LightGBM
- SHAP / feature importance and confidence levels
- Time-based train-test validation

## Folders
`preprocessing/` · `model/` · `evaluation/` · `notebooks/` · `results/` (git-ignored)


## Read-only data audit

From the repository root, run `python research/component_1/audit_data.py` after
configuring `COMPONENT1_DB_URL` locally with the `component1_readonly` role.
The script discovers live columns and primary keys before building aggregate
queries. It explicitly begins a read-only repeatable-read transaction, verifies
the role and transaction state, uses UTC and 30-second statement / 5-second lock
timeouts, and rolls back after reading. Connection startup options alone are not
sufficient with every connection pooler.

Timestamped JSON reports are written only after a complete audit to `results/`,
which is ignored by Git. They include column types, row/distinct counts, missing
identifiers/dates/numeric metrics, intended-grain duplicates, date ranges,
per-entity snapshot/day coverage and gaps, and daily frequencies. Video-history
channel counts are derived through the current video mapping. No source rows,
titles, connection URLs, or raw driver errors are exported. Read-only role/RLS
visibility defines the audit scope; gap thresholds describe observations rather
than an assumed schedule. A missing schema/grain column stops the audit.

Run offline safety checks with
`python -m unittest discover -s tests/component_1 -p test_audit_data.py -v`.
Do not commit generated reports or `.env`. Reports are diagnostic and do not
establish training readiness without a forecast horizon and leakage-safe splits.
