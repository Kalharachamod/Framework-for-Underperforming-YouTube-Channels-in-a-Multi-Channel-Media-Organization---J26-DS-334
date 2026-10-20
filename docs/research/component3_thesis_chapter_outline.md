# Component 3: Recommended Thesis Chapter Outline

Each section lists the repository documents to draw from.

## Chapter 1: Introduction

| Section | Source |
|---|---|
| 1.1 Problem | [final_research_overview](component3_final_research_overview.md) |
| 1.2 Motivation | multi-channel media organisation; public data only |
| 1.3 Research gap (summary) | [research_position](component3_research_position.md), "Research Gap Statements", Version 2 |
| 1.4 Objectives | [methodology_traceability §2](component3_methodology_traceability.md) |
| 1.5 Scope | [scope_boundary](component3_scope_boundary.md), [claims_and_boundaries](component3_claims_and_boundaries.md) |

## Chapter 2: Literature Review

| Section | Source |
|---|---|
| 2.1 YouTube audience networks (commenter overlap) | R1–R6, R13 in [research_position](component3_research_position.md#references) |
| 2.2 Graph-based audience analysis | [closest_work_comparison](component3_closest_work_comparison.md) |
| 2.3 Representation learning (metapath2vec, HGT, node2vec) | F2, F3, F4, R7, R8, R12 |
| 2.4 Diffusion (PageRank, PPR, PathRank) | F1, F6, R9, R14 |
| 2.5 Semantic similarity | F7, R7 |
| 2.6 Confidence / evidence weighting | R10, R11 |
| 2.7 Research gap | [literature_gap_matrix](component3_literature_gap_matrix.md); research position, Version 3 |

Before submission, run the systematic review recommended in STEP 32.

## Chapter 3: Methodology

Source: [final_methodology](component3_final_methodology.md), sections 4.1–4.14:
- data
- graph
- representation learning
- diffusion
- topic similarity
- confidence
- Audience Bridge Score (state the **three-part** formula)
- baselines
- evaluation

## Chapter 4: Implementation

| Section | Source |
|---|---|
| 4.1 Architecture | [final_system_architecture](component3_final_system_architecture.md) |
| 4.2 Data pipeline | [data_pipeline](component3_data_pipeline.md) |
| 4.3 Backend (read-only API) | `backend/README.md` |
| 4.4 Research pipeline and reproducibility | [reproduction_guide](component3_reproduction_guide.md), [reproducibility_checklist](component3_reproducibility_checklist.md) |
| 4.5 Dashboard | `frontend/README.md`; screenshots (Figure 9) |
| 4.6 Testing | [end_to_end_test_plan](component3_end_to_end_test_plan.md), [integration_test_results](component3_integration_test_results.md) |

## Chapter 5: Results

Source: [final_results](component3_final_results.md).

| Section | Results sections |
|---|---|
| 5.1 Dataset | 8.1 |
| 5.2 Graph | 8.2 |
| 5.3 Scoring | 8.3–8.7 |
| 5.4 Baselines | 8.8–8.10 |
| 5.5 Evaluation | 8.11–8.12 |
| 5.6 Robustness | 8.13 |
| 5.7 Explainability | 8.11 and sensitivity |
| 5.8 Computational cost | 8.14 |

## Chapter 6: Discussion

| Section | Source |
|---|---|
| 6.1 Findings | interpretation of diffusion dominance, baseline difference and sparse stability |
| 6.2 Research contribution | [contribution_statement](component3_contribution_statement.md) |
| 6.3 Comparison with literature | [closest_work_comparison](component3_closest_work_comparison.md) |
| 6.4 Negative results | HGT collapse; evaluation cost ([known_findings](component3_known_findings_and_limitations.md)) |
| 6.5 Limitations | [limitations](component3_limitations.md) |
| 6.6 Ethics | [ethics_and_privacy](component3_ethics_and_privacy.md) |
| 6.7 Implications | for channel strategy, as research signals only |

## Chapter 7: Conclusion

- 7.1 Summary
- 7.2 Contribution, in conservative wording
- 7.3 Limitations
- 7.4 Future work:
  - relevance labels
  - repeated comparable snapshots
  - a simple-overlap baseline and ablations
  - HGT objective / configuration study
  - a systematic literature review
