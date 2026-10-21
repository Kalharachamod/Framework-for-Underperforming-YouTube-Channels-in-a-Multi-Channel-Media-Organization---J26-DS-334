# Component 3: Methodology Freeze

*STEP 33, §16–§20. Audit date: 2026-10-15. Method version: Audience Bridge Score 2.0.*

## Status

**MINOR CORRECTIONS REQUIRED → applied.** No critical or major methodological issue was found. After the corrections below, **the Component 3 methodology is ready to freeze.**

## Frozen pipeline

YouTube public data → pseudonymised immutable snapshot → DuckDB research dataset → heterogeneous commenter–video–channel–topic graph → graph features (`as_of`) → metapath2vec (primary) / HGT (alternative) embeddings → Personalized PageRank diffusion → multilingual topic similarity → **Audience Bridge Score** → explanations → read-only API and dashboard.

## Primary method

**Audience Bridge Score framework (method 2.0):**

```
ABS(s → d) = [ w_d·norm_PPR(s→d) + w_e·norm_emb(s,d) + w_t·norm_topic(s,d) ] × n/(n+3) × min(cov_s, cov_d)
```

- Weights are 1/3 each by default. Normalisation is per-source min-max, and ranking is per source.
- The embedding component uses metapath2vec by default.

## Supporting methods

- HGT (alternative embedding).
- Personalized PageRank (diffusion component).
- Multilingual E5 topic similarity.
- Evidence-and-coverage confidence.
- Rule-based explanations and sensitivity analysis.

## Baselines

- Louvain same-community indicator on a Jaccard shared-commenter projection.
- Type-agnostic node2vec cosine similarity.

## Evaluation

- Method agreement (Spearman, Kendall τ-b, top-k Jaccard).
- Top-k comparison.
- Temporal stability across comparable snapshots.
- Sparse-data robustness (seeded comment subsampling; CLI default 3 retain levels × 3 seeds; the reported run `eval-60ac93319497` used 50 % retention × 2 seeds).
- Performance measurement.
- Relevance metrics are implemented but need ground-truth labels, which do not exist.

## Limitations

1. **No ground truth:** evaluation shows consistency, not correctness.
2. **Small sample:** 18 Derana channels, 851 videos, about 10.8k comments, low video coverage per channel.
3. **Weak temporal evidence:** one comparable snapshot pair about 1.5 days apart.
4. **Popularity bias:** confidence uses absolute shared-commenter counts.
5. **Shared evidence:** commenter overlap enters both PPR (reachability) and confidence (support).
6. **Partial directionality:** only PPR and per-source normalisation are directional; confidence and topic similarity are symmetric.
7. **Relative scores:** per-source min-max means scores are not calibrated across sources.
8. **Untuned defaults:** all hyperparameters and weights are documented defaults, not tuned values.
9. **Noisy HGT validation:** HGT validation rests on 41 temporal edges.
10. **Dependencies:** `requirements.txt` uses minimum versions; the exact environment is pinned in `requirements-lock.txt` and recorded per run.
11. **Commenters are not viewers:** they are a self-selected subset.

## Safe claims

- Component 3 ranks **potential** cross-channel audience bridges from observed public commenter and content evidence.
- The score is directional through source-personalised diffusion and per-source ranking.
- Every score is decomposable and explained.
- An integrated, confidence-gated framework is a **potential contribution**, pending a systematic literature review.
- Rankings are strongly correlated with their PPR component (Spearman 0.809), weakly with the Louvain baseline (0.330) and negatively with node2vec (−0.286). Stability under subsampling and across the one comparable snapshot pair is reported as measured, with the exact numbers and experiment ID.

## Prohibited claims

- Audience migration, subscriber transfer or any causal effect.
- Future growth or forecasting.
- Accuracy or correctness (no labels).
- That any individual technique (PPR, metapath2vec, HGT, E5, Louvain, node2vec, shrinkage confidence, heterogeneous graphs, directional audience relations) is novel.
- "First", "novel algorithm", "no previous work".
- Demographic or individual-level inference.
- Representativeness of all YouTube viewers.

## Risks

- A systematic literature search may find a close prior formulation, which would reduce novelty to an application contribution.
- Examiners may question the validation because there are no labels. Mitigation: present the work as a consistency and robustness evaluation, and propose expert labelling as future work.
- More snapshots may show lower stability than the single short-window pair suggests.
- A fresh environment may install newer library versions. Mitigation: install from `requirements-lock.txt`.

## Corrections made in STEP 33 (documentation and wording only)

1. `research/component_3/README.md`:
   - The ABS bullet now lists the three components.
   - The evaluation bullet now includes metapath2vec / HGT similarity.
   - Weekly recomputation is marked as planned, not implemented.
2. `docs/architecture/metapath2vec.md`:
   - The pipeline line is no longer marked "(later)".
   - The stale "no topics yet" limitation is replaced by VTV-only topic use.
   - The old snapshot coverage figure was removed.
3. `docs/architecture/hgt.md`:
   - The stale "no topic nodes" and "no real temporal validation" statements are updated to the current temporal split (41 validation edges).
4. `docs/architecture/evaluation.md`:
   - Notes that `rs-20261008T191612Z` and `rs-20261010T081534Z` are comparable and evaluated.
5. Dashboard text only (no layout or logic change):
   - "who shares audiences with whom" → "which channels share public commenters".
   - "no shared audience" → "no shared commenters".
   - Channel Explorer block "Shared audience" → "Shared commenters".

No code logic, formula, configuration or component was changed or removed.

## Extensions after the freeze (no frozen setting changed)

- **Simple-overlap baseline** (evaluation version 1.2): ranks pairs by the shared-commenter count (Finding 6). It is added next to Louvain and node2vec; it does not replace them.
- **Nightly live results** ([live_results.md](../architecture/live_results.md)) run the frozen pipeline on a rolling 90-day window.
  - Their snapshot source is `supabase_postgresql_live`.
  - They are kept apart from the thesis snapshots and are not used as reported results.

## Freeze rule

From this point:
- The ABS formula, the confidence definition, default weights, k, the PPR settings, the graph schema, the baselines and the evaluation protocol are **frozen** for the thesis.
- Any later change must:
  - be a bug fix with a test, or
  - be reported as a named ablation or variant (with a new method version and experiment ID), never as a silent replacement.
- New results must be produced by the frozen pipeline and cited by experiment ID.
