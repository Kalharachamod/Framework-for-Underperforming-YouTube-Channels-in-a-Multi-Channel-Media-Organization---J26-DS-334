# Component 3 Final Status

## Research Title

Diffusion-Based Cross-Channel Audience Bridge Scoring

## Research Problem

For each channel of a multi-channel YouTube organisation, rank the other channels that are its strongest **potential** audience bridges, using only partial public evidence, and explain each ranking.

## Research Gap

Commenter overlap, communities, embeddings, PPR proximity, content similarity and evidence shrinkage exist separately. In a targeted search, no work combined them into a directional, per-source, confidence-weighted and explainable ranking of potential cross-channel audience bridges, evaluated against community-detection and embedding baselines. A systematic review is still required.

## Proposed Contribution

A confidence-weighted framework for ranking potential directional cross-channel audience bridges: the task-specific integration and formulation of established techniques. STEP 32 classified it as a **moderate potential contribution**. See [contribution_statement](component3_contribution_statement.md).

## Methodology

Heterogeneous commenter–video–channel–topic graph → metapath2vec embeddings → Personalized PageRank → multilingual topic similarity → evidence-and-coverage confidence → three-part Audience Bridge Score → per-source ranking and explanations. The methodology is **frozen** (method 2.0, STEP 33).

## Data Source

YouTube Data API v3, public data only.
- **Stored in:** Supabase PostgreSQL → immutable Parquet snapshots → DuckDB.
- **Main snapshot:** `rs-20261010T081534Z`, with 18 channels, 851 videos and 10,823 comments.

## Primary Method

```
ABS(s → d) = [w_d·norm_PPR + w_e·norm_metapath2vec + w_t·norm_topic] × n/(n+3) × min(coverage)
```

Weights are 1/3 each. The two-part form is the `w_e = 0` ablation.

## Supporting Methods

- HGT (alternative embedding)
- Personalized PageRank
- multilingual-E5 topic similarity
- confidence weighting
- explainability: decomposition, reasons and sensitivity

## Baselines

- Louvain (Jaccard projection)
- node2vec (type-agnostic embeddings)

## Evaluation

There are no labels, so the evaluation measures consistency:
- agreement with the baselines and with the score's own components
- top-k overlap
- temporal stability (one comparable snapshot pair)
- sparse-data robustness
- computational performance
- sensitivity

## Main Findings

All from `eval-60ac93319497`:
- 41 of 153 channel pairs share commenters, and 73.2 % of ordered pairs score 0.
- The score is driven mostly by diffusion (Spearman 0.809 with PPR).
- It differs from both baselines: Spearman 0.330 with Louvain and −0.286 with node2vec.
- It is more stable than either baseline at 50 % comment retention (Spearman 0.814).
- Temporal stability is 0.946 over 1.5 days, largely reflecting shared data.
- Confidence is the most influential factor for the top-1 destination: removing it changes 9 of 18.
- **Negative result:** HGT channel embeddings collapse (cosine median 0.978).

## Limitations

- public commenters only
- one organisation and 18 channels
- sparse evidence
- no labels
- short temporal window
- partial directionality
- popularity bias
- untuned defaults
- HGT collapse
- evaluation cost

See [limitations](component3_limitations.md).

## Privacy / Ethics

- Commenter IDs are pseudonymised with HMAC-SHA256 (salt in `.env`, fail-closed).
- Outputs are aggregate only, and no identifiers are returned by the API or dashboard.
- Legal compliance with the YouTube terms is intended but not independently verified.

See [ethics_and_privacy](component3_ethics_and_privacy.md).

## Reproducibility

- seeded and deterministic training
- content-addressed, write-once experiment IDs
- library versions in every manifest
- pinned E5 revision
- reproduction guide

**Gap:** `requirements.txt` has lower bounds only.

## Dashboard Status

- All pages render real stored results from the API, with correct empty states when an artifact is missing.
- Direction (source → destination) is shown explicitly.
- No mock data is shown as real.
- Frontend tests pass (48/48) and the build is clean.

## Known Technical Issues

See [known_findings_and_limitations](component3_known_findings_and_limitations.md).

1. **Evaluation runtime:** 18.75 h recorded, dominated by one outlier step; about 1.4 h without it. The newest full evaluation (9 sparse runs) took 2.5 h with no outlier.
2. **Incomplete snapshot:** `rs-20261015T174938Z` is missing 718 comments and must be labelled as partial.
3. **HGT collapse:** HGT channel representations collapse. This is a negative result and does not affect the primary score.
4. **Zero-evidence channels:** they still show ranks 1–17 in the dashboard. Showing "No bridge evidence" instead is recommended.
5. **Bridges table columns:** "Diffusion" is a weighted component and "Topic sim." is the raw cosine. Both are explained by tooltips.

## Research Risks

- A systematic review may reveal closer prior work.
- Examiners may challenge validation without labels.
- Longer temporal data may show lower stability.
- The score may be seen as "engineering" rather than method.

## Final Readiness

**READY WITH MINOR DOCUMENTATION ISSUES**

The research pipeline, results and documentation are complete and consistent, and no critical research or integration issue remains.

**Remaining issues** (none critical; all documented):
- The newest snapshot is incomplete.
- Zero-evidence rows still show ranks in the dashboard.
- There is no dependency lock file.
- A systematic literature review must precede thesis submission.
