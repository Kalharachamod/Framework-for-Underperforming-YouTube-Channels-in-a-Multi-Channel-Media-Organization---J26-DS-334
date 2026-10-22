# Component 3: The Whole System, A to Z

**Diffusion-Based Cross-Channel Audience Bridge Scoring**: a study guide for the presentation and viva.

This guide explains every part of the system in the order the data flows: where it comes from, how it is stored, how the graph is built, how every score is calculated (with equations), which algorithm was used and why, and where each result appears in the dashboard. The numbers come from the stored thesis results ([component3_final_results.md](component3_final_results.md)) unless a section says otherwise.

---

## 0. The idea in one minute

**The problem.** A media organisation such as Derana runs many YouTube channels (Ada Derana, TV Derana, Dream Star, Derana Little Star, …). It wants to know **which of its channels are connected through their audiences**, for example for cross-promotion or content planning. It has no private data about viewers, only **public** data: videos, titles and public comments.

**The answer the system gives.** For every pair of channels, **source → destination**, it computes an **Audience Bridge Score** between 0 and 1. A high score means: *starting from this source channel, this destination channel is strongly connected to it through shared public commenters, graph structure and similar content, and the evidence is strong enough to trust that.*

**What it is not.** It is a *potential* audience bridge (an affinity signal). It does **not** show that people moved between channels, that subscribers transferred, causality or growth. Say this sentence in the viva whenever you show a score.

**The formula in one line:**

```
ABS(s → d) = [ ⅓·norm_PPR(s→d) + ⅓·norm_metapath2vec(s,d) + ⅓·norm_topic(s,d) ] × n/(n+3) × min(coverage_s, coverage_d)
```

Sections 6–9 explain every term.

---

## 1. Architecture: the whole flow

```
YouTube Data API v3 (public data only)
        │  channels.list · playlistItems.list · videos.list · commentThreads.list · comments.list
        ▼
Collectors (Python)  ── commenter ID → HMAC-SHA256 pseudonym BEFORE storage
        ▼
Supabase PostgreSQL (shared team database, schema "research")
        ▼  export
Research snapshot  rs-<UTC time>  (Parquet files + manifest with SHA-256 checksums, immutable)
        ▼  DuckDB validation (counts, duplicates, missing values, relationships, quality warnings)
Heterogeneous graph  (commenter · video · channel · topic)  ◄── topic similarity (E5 encoder + KMeans)
        ▼
Graph features (shared commenters, Jaccard, directional overlap, …)
        ▼
┌───────────────┬──────────────┬────────────────────┬──────────────────┐
│ metapath2vec  │ HGT          │ Personalized       │ Topic similarity │
│ (primary)     │ (alternative)│ PageRank (PPR)     │ (E5 cosine)      │
└──────┬────────┴──────┬───────┴─────────┬──────────┴─────────┬────────┘
       └── embedding ──┘                 │ diffusion          │ topic
                        ▼                ▼                    ▼
              AUDIENCE BRIDGE SCORE = base score × confidence
                        ▼
   Baselines: Louvain · node2vec · shared commenters      Explainability (decomposition + reasons)
                        ▼
   Evaluation: agreement · top-k · temporal stability · sparse robustness · runtime
                        ▼
   FastAPI backend (read-only)  ──►  React dashboard
```

**Technology stack**

| Layer | Tool | Why this tool |
|---|---|---|
| Data source | YouTube Data API v3 | Official, terms-governed, public data only; reproducible |
| Shared database | Supabase (PostgreSQL), `psycopg` | The whole team shares one online store; row-level security |
| Research snapshots | Parquet (`pyarrow`) + SHA-256 manifest | Immutable copies, so every result can be reproduced exactly |
| Analytics engine | DuckDB | Fast SQL over Parquet; used for validation and aggregates |
| Graph | NetworkX + SciPy sparse matrices | Graph storage and the PPR power iteration |
| metapath2vec | Our own walk sampler + `gensim` Word2Vec (skip-gram) | Standard, deterministic with 1 worker and a seed |
| HGT | PyTorch + PyTorch Geometric `HGTConv` | Reference implementation of HGT |
| Topic encoder | `sentence-transformers`, `intfloat/multilingual-e5-small` | Multilingual: Sinhala, Tamil and English |
| Clustering, metrics | scikit-learn (KMeans), SciPy | Standard implementations |
| Louvain | NetworkX `louvain_communities` | Standard implementation |
| Backend | FastAPI | Read-only API over the stored results |
| Frontend | React 19 + Vite + TypeScript | The dashboard |
| Automation | GitHub Actions | Nightly live pipeline, with no computer needed |

---

## 2. Data collection (where the data comes from)

**Collected through the YouTube Data API v3** for the **18 Derana channels** (the research set):

| Entity | What is collected | Limit (research runs) |
|---|---|---|
| Channel | title, created date, public statistics (subscribers, views, video count) | — |
| Video | title, description, publish time, public statistics | newest 50 per channel |
| Comment | public top-level comments and replies | up to 100 threads per video, all replies |
| Commenter | the public author channel ID, **pseudonymised immediately** | — |

- **Quota:** the API gives 10,000 units a day, and the collectors count every unit. Transient errors are retried, and every failure is recorded per item, never silently dropped.
- **Privacy (important for ethics questions):** `commenter_id = "anon_" + HMAC-SHA256(secret_salt, real_id)`.
  - This happens *before* anything is stored.
  - Without the secret salt the pipeline refuses to run (it "fails closed").
  - The dashboard never shows a commenter, only aggregate counts.

---

## 3. Storage: two layers, and why both

| Layer | Role |
|---|---|
| **Supabase PostgreSQL** | The *live, shared* database. Collection writes here, the team shares it, and it keeps growing. |
| **Research snapshot** `rs-<time>` | A *frozen copy* (Parquet + checksums). Every analysis reads exactly one snapshot, so the result can always be reproduced. |

**Why not analyse the database directly?** Because the database changes every day. A thesis result must be reproducible, so it is tied to an immutable snapshot ID, and checksums are verified before every analysis.

**Validation (DuckDB):** before a snapshot can be analysed it must pass these checks and be `research_ready`:
- required fields
- duplicates
- missing values
- referential integrity (comment → video → channel)
- quality warnings (for example, more likes than views)

**Thesis snapshot:** `rs-20261010T081534Z`

| Measure | Value |
|---|---|
| Channels | 18 |
| Videos | 851 |
| Comments | 10,823 |
| Unique commenters | 7,336 (175 commented on 2 or more channels) |

---

## 4. The heterogeneous graph (how the relationships are created)

A **heterogeneous graph** has different node types and different relation types.

| Node type | Meaning | Count (thesis) |
|---|---|---|
| `commenter` | one pseudonymous public commenter | 7,336 |
| `video` | one collected video | 851 |
| `channel` | one research channel | 18 |
| `topic` | one content cluster (KMeans over video text) | 10 |

| Edge | Direction | Created when | Weight |
|---|---|---|---|
| `comments` | commenter → video | the person wrote at least 1 public comment on the video | number of comments |
| `belongs_to` | video → channel | the channel published the video | 1 |
| `participates_in` | commenter → channel | **derived:** the person commented on at least one video of the channel | number of comments |
| `has_topic` | video → topic | the video's text falls in that topic cluster | 1 |

Thesis graph: **8,215 nodes and 18,271 edges**.

**Why heterogeneous and not just a channel–channel graph?** A channel-only projection throws away the videos, topics and multi-hop paths (channel → video → commenter → video → channel). PPR and metapath2vec both use those paths.

**Dashboard: Graph Intelligence** shows this exact graph:
- the 4 node types with counts and degree statistics
- the relations with their counts
- the models built on the graph (channel overlap, metapath2vec, HGT, PageRank)

---

## 5. Graph features (descriptive evidence)

For two channels A and B, let **A** and **B** be their sets of unique commenters:

```
shared_commenters      n = |A ∩ B|
jaccard_similarity        = |A ∩ B| / |A ∪ B|
directional_overlap A→B   = |A ∩ B| / |A|          (share of A's commenters also on B)
overlap_ratio             = |A ∩ B| / min(|A|, |B|)
interaction_weight        = ln(1 + comment_count)   (commenter–channel weight)
```

All features are computed **as of** the snapshot time, so no later data leaks in. Thesis: 41 of 153 channel pairs share at least one commenter (maximum 36: Derana Little Star – Dream Star).

**Dashboard:**
- **Channel Explorer**: "Shared commenters" bubbles and the "Audience ladder".
- **Explainability**: "Aggregate evidence".

---

## 6. Signal 1: Personalized PageRank (the "diffusion" part)

**Idea:** start a random walker at the **source** channel. At each step it follows an edge (with probability α = 0.85) or jumps back to the source (with probability 0.15). The share of time the walker spends on each destination channel measures how *reachable* that destination is from the source, through all paths and not only direct overlap.

**Equation** (power iteration until convergence):

```
r_s = (1 − α) · e_s + α · Pᵀ · r_s

  P(u→v) = w(u,v) / Σ_x w(u,x)        transitions proportional to edge weight
  e_s    = 1 on the source channel, 0 elsewhere
  α      = 0.85,   tolerance 1e-10,   at most 1000 iterations

diffusion(s → d) = r_s[d]             the stationary probability on destination d
```

- **Edges used:** comments and belongs_to, in both directions. Topic edges and the derived participates_in edges are excluded, so diffusion reflects *audience* structure, not content.
- **Directional:** the walk restarts at s, so PPR(s→d) ≠ PPR(d→s). This is the main source of direction in the score.
- **Unreachable destinations** get exactly 0 (`reachable = false`).
- **Thesis result:** it converged for all 18 sources; 156 of 306 ordered pairs are reachable.

**Why PPR?** It captures multi-hop reachability, which a pairwise overlap count cannot. It is directional by construction, and it is standard, convergent and interpretable. **Alternative considered:** a plain overlap count, which is now used as a baseline (Section 11).

**Dashboard:** Graph Intelligence (the PageRank card: "From every channel · α 0.85"), Pipeline Graph (PPR step) and Explainability ("Raw PPR diffusion").

---

## 7. Signal 2: graph embeddings, metapath2vec (primary) and HGT (alternative)

### 7.1 metapath2vec (PRIMARY)

**Idea:** turn every node into a 64-number vector, so that channels with similar audience structure get similar vectors. It learns from **random walks that follow meaningful type patterns (metapaths)**.

| Metapath | Meaning |
|---|---|
| `C-V-C` | two commenters on the same video (co-commenting) |
| `C-V-Ch-V-C` | two commenters on the same channel |
| `Ch-V-C-V-Ch` | channel → its audience → another channel (**channel–audience–channel**) |
| `V-Ch-V` | two videos of the same channel |
| `V-T-V` | two videos on the same topic |

**Training (skip-gram with negative sampling):** for each node *v* in a walk, the model learns to predict its neighbours within a window of 5. Standard objective:

```
maximise  Σ log σ(z_c · z_v)  +  Σ_{5 negatives} log σ(−z_n · z_v)
```

**Settings:** dimension 64, 10 walks per node, walk length 40, window 5, 5 negatives, 5 epochs, seed 42, 1 worker (deterministic).

**Used in the score:**

```
embedding_similarity(s, d) = cos(z_s, z_d) = (z_s · z_d) / (‖z_s‖ ‖z_d‖)
```

It is symmetric. Thesis: channel cosine 0.198–0.564 (median 0.411), so channels are well separated.

### 7.2 HGT, Heterogeneous Graph Transformer (ALTERNATIVE)

**Idea:** a graph neural network with **attention** that is specific to each node type and relation type. It is trained to predict `commenter → video` comment edges (link prediction, binary cross-entropy, 5 negatives per positive).

**Settings:**
- hidden size 64, 2 layers, 2 heads, dropout 0.2
- Adam optimiser (learning rate 0.005, weight decay 1e-4), 50 epochs
- temporal split: the newest 20 % of edges are held out for validation

**Result:** validation ROC-AUC **0.859**, so it does learn the link task. But the channel vectors **collapse**: channel–channel cosine is 0.90–1.00 (median 0.978), so the channels are barely distinguishable.

### 7.3 Why metapath2vec is primary and HGT the alternative

| | metapath2vec | HGT |
|---|---|---|
| Channel separation | good (cosine 0.20–0.56) | collapsed (0.90–1.00) |
| Determinism | fully deterministic | seeded on CPU only |
| Interpretability | walks follow named metapaths | attention is harder to explain |
| Cost | seconds | longer training |

**Viva answer:** "HGT is included to test whether a learned message-passing model gives better channel representations. On this data it did not: its training objective (commenter→video links) never pushes channels apart, and with only 18 channel nodes their representations converge. This is reported as a negative result, Finding 3. HGT can still be swapped in with `--embedding-source hgt`."

**Dashboard: Neural Models** shows:
- the model map
- the HGT network drawing, with its 14 input features
- the metapath2vec walk shares and skip-gram drawing
- HGT training and validation loss
- validation ROC-AUC and average precision

---

## 8. Signal 3: topic similarity (content), E5 (primary) and TF-IDF (alternative)

**Steps:**
1. **Text:** each video's title plus the first 1,000 characters of its description.
2. **Encoder:** `intfloat/multilingual-e5-small`, pinned to one model revision. It gives a 384-dimensional vector per video and covers **Sinhala, Tamil and English**.
3. **Channel profile:** the L2-normalised mean of the channel's video vectors.
4. **Similarity:** `topic_similarity(s, d) = cos(profile_s, profile_d)`. It is symmetric.
5. **Coverage:** `coverage = usable videos / all videos` of the channel. Text shorter than 3 letters counts as unusable.
6. **Topic nodes:** KMeans with **10 clusters** over the video vectors gives the `topic` nodes of the graph.

**Primary vs alternative:** E5 is primary because it understands meaning across languages. A character n-gram **TF-IDF + LSA** backend exists as a lightweight alternative that needs no model download. It only matches surface text, not meaning.

**Thesis result:** the raw cosines are compressed (0.78–0.98, median 0.935), which is typical of E5. Per-source normalisation (Section 9) spreads them out.

**Dashboard: Topic Intelligence** shows:
- the channel → topic flow (which channels publish in which clusters)
- the content similarity wheel
- the full similarity matrix

---

## 9. The Audience Bridge Score (the core calculation)

### Step 1: per-source min-max normalisation

The three signals have different scales (PPR ≈ 0.001, cosine ≈ 0.9). For each **source s**, every signal is rescaled over all its destinations:

```
norm_x(s, d) = ( x(s,d) − min_d' x(s,d') ) / ( max_d' x(s,d') − min_d' x(s,d') )
```

So for every source, its best destination on each signal gets 1 and its worst gets 0. This also makes the score **directional**, because the normalisation differs per source. An all-zero column gives 0. A constant non-zero column gives NULL (no ordering information).

### Step 2: base score (weighted sum)

```
base(s → d) = w_d · norm_PPR(s→d) + w_e · norm_embedding(s,d) + w_t · norm_topic(s,d)
              w_d = w_e = w_t = 1/3   (equal, documented defaults)
```

### Step 3: confidence (how much to trust the evidence)

```
evidence_confidence  = n / (n + k)          n = shared commenters, k = 3
coverage_confidence  = min(coverage_s, coverage_d)
confidence           = evidence_confidence × coverage_confidence
```

| Shared commenters n | 0 | 1 | 3 | 11 | 36 |
|---|---|---|---|---|---|
| n/(n+3) | **0** | 0.25 | 0.50 | 0.786 | 0.923 |

- `n/(n+k)` is the established **shrinkage** form (Bell & Koren 2007). One shared commenter is weak evidence; 36 is strong. k = 3 is the point where confidence reaches 0.5.
- **Confidence is a gate.** If n = 0, the score is 0, so **content similarity alone can never create a bridge.** That is why a score of 0.000 always means "no shared commenters" (the dashboard shows "No bridge evidence").

### Step 4: final score

```
AudienceBridgeScore(s → d) = base(s → d) × confidence(s, d)        ∈ [0, 1)
```

Rank destinations per source by descending score. Ties are broken by channel ID, so the order is deterministic.

### Worked example (shown in the dashboard: eTunes → TV Derana)

```
norm PPR = 1.000  → ⅓ × 1.000 = 0.333
norm m2v = 1.000  → ⅓ × 1.000 = 0.333
norm top = 1.000  → ⅓ × 1.000 = 0.333
base score                    = 1.000
shared commenters n = 11 → 11/14 = 0.786;  coverage 1.00 → confidence 0.786
ABS = 1.000 × 0.786 = 0.786   → rank #1 of 24 destinations for eTunes
```

TV Derana → eTunes scores 0.783, not 0.786, because the normalisation is per source. That small difference **is the directionality**.

### Thesis top results (`abs-7cf3eab938ad`)

| Source → Destination | Score | Shared commenters |
|---|---|---|
| Derana Little Star → Dream Star | 0.898 | 36 |
| Dream Star → Derana 60 Plus | 0.886 | 27 |
| Ada Derana Sports → Ada Derana | 0.872 | 21 |

Overall: 306 ordered pairs were scored; 73.2 % score 0 (no shared commenters); the decomposition reconstructs every score with error 0.

**Primary vs ablation:** the frozen method is the **three-part** score. The older **two-part** form (diffusion + topic only) is reproduced exactly as an ablation with `--weights 0.5 0 0.5 --embedding-source none`.

**Dashboard:**
- **Overview**: strongest bridge, top bridges and score distribution.
- **Audience Bridges**: the inbound/outbound bridge map per source and the full ranking table, with columns for score, confidence, diffusion, topic similarity and evidence.
- **Explainability**: the exact build-up shown above.

---

## 10. Explainability (why a pair got its score)

For every pair, the system rebuilds the score from its stored parts:

```
diffusion_contribution = w_d × norm_PPR
embedding_contribution = w_e × norm_embedding
topic_contribution     = w_t × norm_topic
base = sum of the three;   score = base × confidence
reconstruction_error = |rebuilt score − stored score|      (must be < 1e-9 → status "complete")
```

**Reason rules** (recorded per pair):

| Reason | Rule |
|---|---|
| Strong structural connectivity | norm_PPR > 0 and in the source's top 25 % of destinations |
| Strong embedding similarity | the same rule on the embedding signal |
| High topic similarity | the same rule on topic similarity |
| Strong shared-commenter evidence | shared commenters ≥ k (3) |
| Low-confidence sparse evidence | 0 < shared < 3 |
| No shared-commenter evidence | shared = 0, so the score is 0 by definition |

**Evidence states:**
- **observed:** the evidence exists.
- **zero:** both channels were observed, and the value really is 0.
- **insufficient coverage:** the absence tells us nothing.
- **missing:** the input is unavailable.

These states are never mixed up.

**Dashboard: Explainability** opens on the strongest bridge and shows:
- the pair, the score ring, its rank, confidence and shared commenters
- **How the score is built** (the flow diagram)
- **What it means** (generated sentences)
- **Ranking context** (the next higher and lower destinations)
- **Exact values**, **Explanation reasons**, **Aggregate evidence** and **Uncertainty**

All 306 explanations are `complete`.

---

## 11. Baselines (what the score is compared against)

| Baseline | How it is calculated | Question it answers |
|---|---|---|
| **Louvain** | Build a channel graph weighted by Jaccard of shared commenters, then find communities by maximising modularity Q (resolution 1.0, seed 42). Score = 1 if the destination is in the source's community, else 0 | "Are bridges just communities?" |
| **node2vec** | Random walks that **ignore node types** (p = q = 1, dimension 64), skip-gram, then channel cosine | "Do type-aware metapaths matter?" |
| **Shared commenters** | Rank destinations by the raw count n | "Is the score just counting?" |

Modularity, which Louvain maximises:

```
Q = (1/2m) Σ_ij [ A_ij − k_i k_j / (2m) ] · δ(c_i, c_j)
```

Thesis results:
- Louvain: 8 communities, modularity 0.193, 5 isolated channels.
- node2vec: embedded 8,205 nodes.

---

## 12. Evaluation (how the method is tested without labels)

There are **no ground-truth labels** (nobody can say which bridges are "correct"). The evaluation therefore measures **consistency, robustness and stability, not accuracy**.

**Agreement metrics** (per source, then averaged):

```
Spearman ρ   = 1 − 6 Σ d_i² / (n (n² − 1))          (rank correlation; d = rank difference)
Kendall τ-b  = (concordant − discordant) / sqrt[(n0 − n1)(n0 − n2)]
Top-k Jaccard = |TopK_A ∩ TopK_B| / |TopK_A ∪ TopK_B|      k = 1, 3, 5
```

**Main results** (`eval-60ac93319497`, Spearman with the Audience Bridge Score):

| Compared with | Spearman | Reading |
|---|---|---|
| PPR (component) | 0.809 | diffusion drives the score most |
| metapath2vec (component) | 0.406 | adds different information |
| Louvain (baseline) | 0.330 | bridges ≠ communities |
| topic (component) | 0.294 | content adds a different view |
| HGT (alternative) | 0.182 | collapsed vectors |
| node2vec (baseline) | −0.286 | type-agnostic walks disagree |

**Other tests:**

| Test | How | Result |
|---|---|---|
| Temporal stability | same channels, two snapshots 1.5 days apart | ABS ρ = 0.946 (high, but the snapshots share most of their data) |
| Sparse-data robustness | randomly keep 50 % of comments (2 seeds) and compare with the full ranking | ABS 0.814 vs Louvain 0.506 and node2vec 0.631, so **the score is more robust than both baselines** |
| Sensitivity | remove one component and check whether the top-1 destination stays | removing **confidence** changes the top-1 for 9 of 18 sources, the biggest effect |
| Runtime | wall-clock time per method | node2vec is the slowest |

**Honest finding (Finding 6), the simple-overlap baseline:**
- Over all pairs the score agrees almost perfectly with the plain count (ρ 0.989). This is inflated by zeros: 73 % of pairs are 0 in both.
- Among pairs that share commenters it is about **0.84**.
- It picks a **different top bridge for 3–4 of 13 channels**. Example: for Dream Star the score picks Derana 60 Plus, while the count picks Derana Little Star.

**Viva answer:** "On this sparse data the score mostly follows the evidence, and the other components mainly reorder close pairs and explain *why*. Showing larger added value needs more data and expert labels. I report this as a limitation."

**Dashboard: Baselines & Evaluation** shows:
- Methods compared (Louvain ← ABS → node2vec with Spearman)
- Agreement with the proposed score (all metrics as bars)
- Ranking quality, temporal and sparse panels
- the full agreement table, the top-k results and computational performance

**Experiments** lists every stored run (ID, step, status) and every snapshot, for reproducibility.

---

## 13. The dashboard, page by page (presentation order)

| # | Page | What to show | What to say |
|---|---|---|---|
| 1 | **Overview** | hero, KPI cards, bridge network, strongest bridge, top bridges, channels by audience, score distribution, research pipeline strip | "This is the whole result at a glance: the strongest directed bridges between the channels." |
| 2 | **Audience Bridges** | pick a source; inbound bridges above, outbound below; dashed = confidence < 0.5; the full ranking table | "Direction matters: A→B and B→A have different scores." |
| 3 | **Explainability** | opens on the strongest bridge; the build-up flow and the reasons | "Every score can be rebuilt from its three parts and the confidence. Nothing is a black box." |
| 4 | **Channel Explorer** | one channel: audience ladder, data coverage, bridge position, content neighbours, publishing rhythm, shared commenters | "Here is everything the system knows about one channel." |
| 5 | **Pipeline Graph** | steps 12–22 as cards, with stored run IDs and settings | "This is the frozen research pipeline, and every step is a stored, validated run." |
| 6 | **Graph Intelligence** | node types, relations, models built on the graph | "This is the heterogeneous graph: 4 node types and 4 relations." |
| 7 | **Topic Intelligence** | channel → topic flow, similarity wheel, matrix | "This is the content side: multilingual E5 embeddings." |
| 8 | **Neural Models** | metapath2vec (primary) and HGT (alternative): drawings, loss, ROC-AUC | "This is why metapath2vec is primary: HGT learned the link task but collapsed the channels." |
| 9 | **Baselines & Evaluation** | agreement with Louvain, node2vec and the components | "Without labels I measure consistency and robustness, not accuracy." |
| 10 | **Experiments** | run list and snapshots | "Every result has an ID and can be reproduced." |
| 11 | **Live Results** | nightly runs, top bridges now, trend per pair | "The system keeps itself up to date every night, with no computer on." |
| 12 | **Analyze Organization** | search an organisation (for example Sirasa), confirm its channels, analyse | "The same method works for any media organisation." |
| 13 | **System Status** | API and data health | (only if asked) |

**Before the viva: choose the right snapshot.** The top-bar **Snapshot** selector defaults to the *latest* snapshot, which may be a quick organisation analysis (25 channels, 15 videos per channel). To show the **thesis results**, select `rs-20261010T081534Z` (18 channels, 851 videos). Quick-analysis snapshots are labelled "(quick)".

---

## 14. Extensions: live results and organisation analysis

### 14.1 Nightly live pipeline (GitHub Actions)

- **When:** every night at 00:00 Sri Lanka time (cron `30 18 * * *` UTC), on GitHub's servers. **No laptop needs to be on.**
- **Collect:** for the 18 channels it collects the newest 50 uploads and re-checks comments on videos from the last 30 days.
- **Score:**
  - It takes a **rolling 90-day window, the same period for every channel**, which is fair to busy and quiet channels.
  - It runs the frozen pipeline (topics → graph → features → metapath2vec → PPR → ABS → Louvain → explanations).
- **Publish:** aggregates only go to `research.c3_live_*`.
- **First full run** (`live-20261020T215831Z`): 18 channels, 0 failures, 14,323 new comments, 622 quota units, 306 pairs (56 with shared commenters), about 19 minutes.
- **Safety:** a failed run publishes nothing and the page shows a red warning. Live results are **monitoring**, not thesis results; consecutive windows share 89 of 90 days, so nightly changes are not evidence of audience movement.

### 14.2 Analyze Organization (quick analysis)

1. **Search** an organisation. The discovery step finds the main channel and the channels it links to (about 100–150 quota units).
2. **Confirm** which channels belong. YouTube does not publish ownership, so a human confirms.
3. **Analyze:** quick limits (15 videos per channel, 50 threads per video). This runs the same scoring pipeline but skips HGT, node2vec and the full evaluation, so it takes minutes.
4. **Compare** two organisations side by side.
5. **Complete analysis** can later add HGT, node2vec and the evaluation.

These results are **exploratory**. The thesis scope stays Derana-only.

---

## 15. Novelty: what is new and what is not (say it exactly like this)

**Not novel (established techniques, cited as such):**
- the YouTube API and commenter overlap (Jaccard)
- heterogeneous graphs
- metapath2vec (Dong et al. 2017) and HGT (Hu et al. 2020)
- PageRank and Personalized PageRank
- E5 embeddings and KMeans
- shrinkage `n/(n+k)` (Bell & Koren 2007)
- Louvain (Blondel et al. 2008) and node2vec (Grover & Leskovec 2016)
- the evaluation metrics

**The contribution (a *potential* contribution, category C/D in the novelty analysis):**

> An **integrated, confidence-gated framework** that combines **multi-hop diffusion (PPR)**, **type-aware graph embeddings (metapath2vec)** and **multilingual content similarity (E5)** into a **directional, per-source, explainable ranking** of potential cross-channel audience bridges inside one media organisation, evaluated against community (Louvain), homogeneous-embedding (node2vec) and simple-overlap baselines.

**What makes it different from existing work:**
1. **Integration:** existing studies measure overlap, communities, embeddings or proximity **separately**, mostly to describe groups. This combines them into one ranked answer.
2. **Directional:** source → destination per channel, through PPR and per-source normalisation, not a symmetric similarity.
3. **Confidence-gated:** thin evidence is discounted, and content alone can never create a bridge.
4. **Explainable:** every score decomposes exactly into its parts, with reasons and evidence states.
5. **Applied context:** a Sri Lankan multilingual (Sinhala, Tamil, English) multi-channel media organisation.

**Careful wording:** "In a targeted literature search we did **not find** this exact combination. A systematic review is still required." Never say "first", "novel algorithm" or "no previous work".

---

## 16. Limitations (be ready for these)

1. **No ground-truth labels:** the results are consistency, not accuracy.
2. **Sparse data:** 73 % of pairs share no commenter. The score mostly follows the shared-commenter count (Finding 6).
3. **Commenters are a self-selected subset** of viewers. Collection is bounded (newest 50 videos).
4. **HGT collapse:** a negative result (Finding 3).
5. **Short temporal evidence:** one comparable snapshot pair, 1.5 days apart.
6. **Equal weights (⅓ each)** are documented defaults, not tuned (there are no labels to tune them against).
7. **No causality:** potential bridges, not migration.

---

## 17. Quick viva answers

| Question | Short answer |
|---|---|
| Why YouTube API? | Official, public, terms-governed, reproducible; no private analytics. |
| Why a heterogeneous graph? | It keeps videos, commenters and topics, and the multi-hop paths between them. |
| Why PPR? | Multi-hop reachability, directional by restart, standard and interpretable. |
| Why metapath2vec over HGT? | Better channel separation, deterministic, interpretable; HGT collapsed. |
| Why E5? | Multilingual semantic embeddings for Sinhala, Tamil and English. |
| Why confidence? | One shared commenter ≠ 36; shrinkage discounts thin evidence; removing it changes the top-1 for 9 of 18 sources. |
| Why multiply, not add, confidence? | It is a gate: no shared audience means no bridge, however similar the content is. |
| Why per-source normalisation? | Signals have different scales; it ranks destinations *for each source*, which also gives direction. |
| Why is a score 0? | n = 0 shared commenters, so confidence is 0. |
| Is it just counting commenters? | Mostly on sparse data (ρ ≈ 0.84 among evidence pairs), but it changes the top bridge for 3–4 of 13 channels and explains why. |
| How do you validate without labels? | Agreement with baselines, top-k overlap, temporal stability, sparse robustness, sensitivity and runtime. |
| Is it real-time? | Updated nightly through GitHub Actions on a rolling 90-day window. |
| Privacy? | HMAC-SHA256 pseudonyms before storage; only aggregates are shown. |
| Reproducibility? | Immutable checksum snapshots, content-addressed experiment IDs, fixed seeds, pinned model revision, `requirements-lock.txt`. |
