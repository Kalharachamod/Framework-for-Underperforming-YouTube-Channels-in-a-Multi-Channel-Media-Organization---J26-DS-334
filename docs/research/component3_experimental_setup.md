# Component 3: Experimental Setup

Every value below comes from the stored experiment manifests or reports. Values that were not recorded are marked as such.

## Main experiment (reported results)

| Item | Value |
|---|---|
| Snapshot | `rs-20261010T081534Z` (extracted 2026-10-10T08:15:19Z; full-scale experiment, STEP 27) |
| Channels | 18 (approved Derana channel set; no competitor channels) |
| Videos | 851 (up to 50 per channel) |
| Comments | 10,823 (8,947 top-level, 1,876 replies), up to 100 threads per video, all replies fetched |
| Unique commenters | 7,336, of whom 175 commented on 2 or more channels |
| Observation window | videos 2022-03-06 to 2026-10-10; comments 2022-03-07 to 2026-10-10 |
| Data quality | `VALID_WITH_WARNINGS` (research-ready) |
| API usage | 606 requests, 605 quota units |
| Graph | 8,215 nodes: 18 channels, 851 videos, 7,336 commenters, 10 topics |
| Graph edges | 18,271: 9,044 `comments`, 851 `belongs_to`, 7,525 `participates_in`, 851 `has_topic` |
| Channel pairs with shared commenters | 41 of 153 |

### Experiment IDs

| Stage | ID |
|---|---|
| Topics | `top-6bf1e474f003` |
| Graph fingerprint | `ba6f77f20f19fc59` |
| Features | `asof-20261010T081519Z` |
| metapath2vec | `m2v-996c59079f77` |
| HGT | `hgt-c132bac52fc0` |
| PPR | `ppr-528039331d78` |
| Audience Bridge Score | `abs-7cf3eab938ad` |
| Louvain | `louvain-df378406c68c` |
| node2vec | `node2vec-421e71b0a640` |
| Explanations | `xpl-3baba8a75699` |
| Evaluation | `eval-60ac93319497` |

## Configuration

| Component | Setting |
|---|---|
| **metapath2vec** | metapaths CVC, CVChVC, ChVCVCh, VChV, VTV; dimension 64; 10 walks per node; walk length 40; uniform transitions; window 5; 5 negatives; 5 epochs; seed 42; 1 worker; gensim 4.4.0 |
| **HGT** | hidden 64; 2 layers; 2 heads; dropout 0.2; Adam lr 0.005, weight decay 1e-4; 50 epochs; 5 negatives; validation fraction 0.2 (temporal, warm edges); minimum 20 validation edges; seed 42; torch 2.14.1+cpu; torch_geometric 2.8.0.post1 |
| **HGT split (main run)** | temporal: 7,235 training and 41 validation edges; cutoff 2026-10-09T00:19:58Z |
| **PageRank** | α 0.85; tolerance 1e-10; max 1,000 iterations; relation-aware bidirectional; weight-proportional transitions; topic and `participates_in` edges excluded |
| **Topic similarity** | `intfloat/multilingual-e5-small` at revision `614241f622f53c4eeff9890bdc4f31cfecc418b3`; 384 dimensions; title + first 1,000 description characters; minimum 3 letters; KMeans with 10 topics; seed 42 |
| **Score weights** | w_d = w_e = w_t = 1/3; embedding source metapath2vec; per-source min-max normalisation |
| **Confidence** | k = 3; confidence = n/(n+k) × min(topic coverage) |
| **Louvain** | Jaccard projection; resolution 1.0; threshold 1e-7; seed 42 |
| **node2vec** | dimension 64; walk length 40; 10 walks per node; window 5; p = q = 1; 5 negatives; 5 epochs; weighted; seed 42 |
| **Evaluation** | methods: score, PPR, topic, metapath2vec, HGT, Louvain, node2vec; k = 1, 3, 5; no labels; temporal on, minimum depth ratio 0.8; sparse unit = comments, retain 0.5, seeds 0 and 1; sparse methods: score, PPR, metapath2vec, Louvain, node2vec |
| **Random seeds** | 42 for all models; 0 and 1 for sparse subsampling |

## Environment

| Item | Value |
|---|---|
| OS | Windows 11 (10.0.26200) |
| CPU | Intel64 Family 6 Model 186, 12 logical processors (CPU-only PyTorch) |
| Python | 3.13.2 |
| Libraries | numpy 2.5.3, pandas 3.0.6, scipy 1.18.1, networkx 3.7, gensim 4.4.0, torch 2.14.1+cpu, torch_geometric 2.8.0.post1 |
| RAM / GPU | Not explicitly recorded in the current experiment configuration. No GPU was used |
| Concurrent load | The findings report states that other jobs ran on the same machine during the experiment, so timings are not controlled benchmarks |

## Secondary snapshots

| Snapshot | Use | Notes |
|---|---|---|
| `rs-20261008T191612Z` | Earlier snapshot for temporal stability | 18 channels, 851 videos, 10,256 comments; 1.5 days before the main snapshot |
| `rs-20261010T072201Z` | Controlled pilot (STEP 26); integration and reproducibility tests | 3 channels, 45 videos, 862 comments |
| `rs-20261008T093922Z` | Early snapshot | Not comparable: about 10 videos per channel |
| `rs-20261015T174938Z` | Newest snapshot | **Incomplete** (718 comments not stored, 26 videos failed). Pipeline run: `abs-ba1203506d95`, `hgt-dc92f7182dd1`, `m2v-93eb6c2dec26`. Evaluation `eval-09420b1535eb` (CLI default sparse setting: retain 0.75/0.5/0.25 × seeds 0/1/2; 9,124 s); explanations `xpl-9ca69e2cd234`. Supplementary results only: [final_results §8.15](component3_final_results.md) |
