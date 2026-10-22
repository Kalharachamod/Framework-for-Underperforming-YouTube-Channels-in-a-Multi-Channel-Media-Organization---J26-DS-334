# Component 3: Dashboard Guide (What Each Screen Shows and What to Say)

A page-by-page guide to the Growth Intelligence dashboard. For every screen it lists **what is on it**, **where the data comes from** and **what to say to the panel**.

Related documents:
- the methods and equations: [component3_system_guide.md](component3_system_guide.md)
- the architecture: [component3_final_system_architecture.md](component3_final_system_architecture.md)

> **Before the viva**
> 1. Start the backend (`uvicorn backend.main:app --port 8000`) and the frontend (`npx vite`). Open `http://localhost:5173`.
> 2. In the top bar, choose **Snapshot → `rs-20261010T081534Z`**. These are the thesis results: 18 Derana channels, 851 videos, 10,823 comments.
>    The default "Latest" may be a quick 25-channel organization analysis, whose numbers differ from the thesis.
> 3. Use a network that can reach Supabase, so Live Results and the Overview trend load. Otherwise they show a saved offline copy or a short message.
>
> **One sentence to repeat whenever you show a score:**
> *"This is a potential audience bridge, an affinity signal from public comments. It does not show audience migration, causality or growth."*

---

## Suggested demo order (10–12 minutes)

| # | Page | Time | Point to make |
|---|---|---|---|
| 1 | Welcome | 15 s | the system and its purpose |
| 2 | Overview | 2 min | the whole result at a glance |
| 3 | Audience Bridges | 1.5 min | direction matters: A→B ≠ B→A |
| 4 | Explainability | 2 min | every score is transparent |
| 5 | Channel Explorer | 1 min | everything about one channel |
| 6 | Pipeline Graph | 1 min | the method, as stored runs |
| 7 | Graph / Topic / Neural | 2 min | the three signals |
| 8 | Baselines & Evaluation | 1.5 min | validation without labels |
| 9 | Live Results | 1 min | updated every night automatically |
| 10 | Analyze Organization | 1 min | works for any media organization |

---

## Parts on every page

### Sidebar (left)

| Element | What it is |
|---|---|
| Logo (top) | the system logo; click it to go back to the Welcome page |
| **Results**: Overview, Audience Bridges, Explainability, Channel Explorer | the answers |
| **Method**: Pipeline Graph, Graph Intelligence, Topic Intelligence, Neural Models | how the answers are produced |
| **Validation**: Baselines & Evaluation | how the method is tested |
| **Live system**: Live Results, Analyze Organization | the extensions: nightly updates and any organization |
| **System**: System Status | health of the API and the data |

The menu groups follow the order of the presentation: **results → method → validation → live system**.

### Top bar

| Element | What it does | What to say |
|---|---|---|
| Page title | the current page | — |
| **Snapshot** selector | chooses which frozen data snapshot every page shows | "Every result belongs to one frozen snapshot, so it can be reproduced." |
| **Scoring experiment** selector | chooses which stored scoring run to show (for example `abs-7cf3eab938ad`) | "Each run has an ID made from its data and settings." |
| Channel search | jumps to a channel | — |
| **API Connected** / **Research data Available** | shows that the backend is up and that the snapshot has research data | — |

---

## 1. Welcome (`/`)

**What you see:** the logo in the centre, "SLIIT · J26-DS-334", the title **Growth Intelligence**, the line *"Cross-channel audience bridge analysis for YouTube media organizations"*, and a small gradient triangle button.

**What it does:** the button opens **Analyze Organization**.

**Say:**
> "Growth Intelligence identifies potential audience bridges between the YouTube channels of a media organization: which channels share an audience, how strongly, and why, using only public data."

---

## 2. Overview (`/dashboard`)

### Header
- **"Research dashboard"** label and the title **Cross-Channel Audience Bridge Analysis**.
- A description: *directional, confidence-weighted scoring … from public comment networks, graph diffusion and content similarity*.
- **Four tiles:** Graph analysis → Graph Intelligence, Audience insights → Channel Explorer, Cross-channel connections → Audience Bridges, Content similarity → Topic Intelligence.
- **Orbit illustration:** the YouTube logo with the 5 largest channels' logos around it.

### Metric cards (all real values from the selected snapshot)

| Card | Number | Highlight | Mini chart |
|---|---|---|---|
| Channels analysed | channels in the snapshot | total public subscribers | commenters of the 10 largest channels |
| Public comments | collected comments | % of commenters active on 2+ channels | comments per channel, **sorted, not a timeline** |
| Graph nodes | nodes in the heterogeneous graph | edges · 4 node types | node-type bars (Channel, Video, Commenter, Topic) |
| Scored directed pairs | channels × (channels − 1) | % of pairs with shared-commenter evidence | score distribution (0.1 bins) |

**Say:**
> "The graph has four node types: commenters, videos, channels and topics. Every ordered pair of channels gets a score. Most pairs score 0 because they share no commenters, and that is the confidence gate working."

### Top channels by potential bridges (table)
- **Columns:** #, Channel, Subscribers, **Potential bridges** (destinations with score > 0), **Avg. confidence** (mean n/(n+3) over those bridges).
- **Data:** calculated from the stored scores.

**Say:**
> "These channels have the most potential bridges, and confidence shows how much evidence supports them on average."

### Audience bridge trend
- **Data:** the score of the 4 strongest **live** pairs across the nightly runs, from the Supabase live tables.
- **What to know:** it has one point per night, so it grows over time.

**Say:**
> "This is the live monitoring: the score is recalculated every night on a rolling 90-day window."

### Bridge network
- **What it shows:** the 16 strongest directed bridges drawn between channel logos. The arrow points source → destination, a thicker line means a stronger score, and the numbers are the scores.
- **Click:** an arrow opens that pair on Audience Bridges.

### Strongest audience bridge
- **What it shows:**
  - the source and destination logos and the score ring
  - confidence, shared commenters and topic similarity
  - bars for the **diffusion, embedding and topic** contributions
  - the line "Base score × confidence = score"
- **Buttons:** "Open in bridge graph" and "Why this score?".

**Say:**
> "Here is the strongest bridge. Its score is the base score from three signals multiplied by the confidence from shared commenters."

### Top bridges · Channels by audience · Score distribution · Research pipeline
- **Top bridges:** the 7 highest-scoring pairs.
- **Channels by audience:** a podium of the top 3 channels by unique commenters, then the list continues.
- **Score distribution:** a histogram of all scores, with counts for pairs at 0, pairs above 0, and the median.
- **Research pipeline:** the 7 stages (Data, Graph, Representation learning, Diffusion, Topic modeling, Scoring, Evaluation) with their status, plus model chips (metapath2vec, HGT, PageRank, Topic similarity, Audience Bridge Score, Louvain, node2vec).

**Footer:** the limitation sentence, plus the snapshot and experiment IDs.

---

## 3. Audience Bridges (`/bridges`)

| Element | What it shows |
|---|---|
| **Source channel** selector, **Bridges per side**, "Hide confidence below 0.5" | the controls |
| **Bridge map** | the selected source in the middle. **Inbound** bridges (other → source) above, **outbound** (source → other) below. Each card shows the score, confidence and shared commenters. A dashed line means confidence < 0.5. Colours: ≥ 0.6, 0.3–0.6, < 0.3 |
| Selected-bridge panel | click a card to see its decomposition and evidence |
| **Bridge ranking** table | every pair: rank, source → destination, bridge score, confidence, diffusion, topic similarity, evidence (shared commenters), snapshot. Filters: search, source, destination, minimum score, minimum confidence |
| "No bridge evidence" | shown instead of a rank when a pair shares no commenters (score 0) |

**Say:**
> "The score is **directional**. For example, eTunes → TV Derana is 0.786, but TV Derana → eTunes is 0.783. PageRank restarts at the source, and normalisation is done per source, so the same pair can differ by direction. In the thesis data the biggest difference is 0.160."

---

## 4. Explainability (`/explainability`)

It **opens on the strongest bridge** automatically. You can pick any source and destination, or swap the direction with ⇄.

| Section | What it shows | What to say |
|---|---|---|
| Header | "Why this score?" | — |
| Pair card | logos, the **score ring**, rank (for example #1 of 24), confidence, shared commenters | — |
| **How the score is built** | a flow: Diffusion, Embedding and Topic (each w × normalised value) → **Base score** → × **Confidence** (evidence × topic coverage) → **Audience Bridge Score** | "This is the equation live: ⅓ diffusion + ⅓ embedding + ⅓ topic, times n/(n+3) × coverage." |
| What it means | generated sentences that describe the result | "These are generated from the stored values only, with no causal language." |
| Ranking context | where this destination sits among the source's destinations (next higher and lower) | — |
| Exact values | the contributions, raw PPR, raw embedding cosine, raw topic cosine, and the formula line | "Every score is rebuilt from these parts with zero error." |
| Explanation reasons | for example strong structural connectivity, strong embedding similarity, high topic similarity, strong shared-commenter evidence, each with its rule | "Each reason has an explicit rule, for example the top 25% of destinations, or n ≥ 3." |
| Aggregate evidence | shared commenters, Jaccard, directional overlap, coverage, active days, first and last shared comment, each with a state | "States separate a real zero from missing data. No commenter is ever identified." |
| Uncertainty | the caveats recorded with the explanation | — |

---

## 5. Channel Explorer (`/channels`)

| Element | What it shows |
|---|---|
| Channel list (left) | every channel, ranked by unique commenters, with a filter box |
| Channel header | logo, name, ID, created date, public views, public videos; facts: channels sharing commenters, mean outbound score, rank by strongest bridge |
| **Audience ladder** | public views → subscribers → collected comments → unique commenters → repeat commenters (log scale) |
| **Data coverage** | % of public videos collected, % of videos with usable text for the topic profile, comments per video |
| **Bridge position** | this channel's inbound and outbound bridges (a small bridge map) |
| **Content neighbours** | the most content-similar channels (topic cosine) |
| **Publishing rhythm** | collected videos per month (last 12 months) |
| **Shared commenters** | other channels sharing commenters with this one (bubble size = count) |

**Say:**
> "This shows everything the system knows about one channel, and how much of it the data covers. Coverage matters, because the confidence uses it."

---

## 6. Pipeline Graph (`/pipeline`)

| Element | What it shows |
|---|---|
| Header facts | pipeline steps, % with a stored run, number of stored runs; a progress bar (validated / stored / not run / failed) |
| Run timeline | every stored run of the snapshot, in order |
| **Pipeline graph** | cards for each stage: Research snapshot → Heterogeneous graph → Graph features → metapath2vec (primary) / HGT (alternative) / Personalized PageRank / Topic similarity → **Audience Bridge Score** → Explainability; Louvain and node2vec baselines → Evaluation. Each card shows its run ID and settings (for example α 0.85, dim 64, weights 0.333) |

**Say:**
> "This is the frozen method as a graph of stored runs. Every card is a real saved result with its ID and settings, so the whole pipeline can be traced and reproduced."

---

## 7. Graph Intelligence (`/graph`)

| Element | What it shows |
|---|---|
| Header | "Heterogeneous research graph", nodes, edges, relation count, node-type bar |
| **Graph map** | node types **Commenter, Video, Channel, Topic** with counts and degree statistics; relations **comments**, **belongs_to**, **participates_in** (derived), **has_topic** with edge counts |
| Built on the graph | Channel overlap (linked pairs, isolated channels), **metapath2vec** (64-dim), **HGT** (64-dim), **PageRank** (sources, α 0.85, iterations) |

**Say:**
> "I use a heterogeneous graph so the video and topic layers and the multi-hop paths are kept. A channel-only graph would lose them. PageRank and metapath2vec both work on this graph."

---

## 8. Topic Intelligence (`/topics`)

| Element | What it shows |
|---|---|
| Header facts | channel profiles, topic clusters (10), mean similarity |
| **Channel → topic flow** | a Sankey diagram: where each channel's videos fall among the 10 content clusters |
| **Content similarity wheel** | the 12 most content-similar channel pairs, with a ranked list |
| **Topic similarity matrix** | the cosine for every channel pair (a heat map) |

**Say:**
> "Content similarity uses the multilingual E5 model on video titles and descriptions, which covers Sinhala, Tamil and English. It measures what channels publish, not who watches. That's why it's one signal among three, and confidence gates it."

---

## 9. Neural Models (`/neural`)

| Element | What it shows |
|---|---|
| Header facts | HGT layers × heads, final validation ROC-AUC, metapath2vec walk count |
| Model map | Graph → metapath2vec (primary) / HGT (alternative) → 64-dim embeddings → cosine → bridge score |
| **HGT neural network** | a drawing of the 14 input features by node type, 64 hidden units, 2 layers × 2 heads, the 64-dim channel embedding |
| **metapath2vec neural network** | the metapath walks (with walk counts and shares), sliding window, skip-gram network with negative samples |
| Training and validation loss | HGT loss per epoch |
| Validation ranking quality | ROC-AUC and average precision per epoch |
| Walk share by metapath | how the walks split across the metapaths |
| HGT input features | the features of each node type |

**Say:**
> "metapath2vec is primary and HGT is the alternative. HGT learned the link task (ROC-AUC around 0.86), but its channel vectors collapsed: cosine 0.90–1.00 between every pair. metapath2vec separated the channels well, at 0.20–0.56. I report the HGT collapse as a negative result."

---

## 10. Baselines & Evaluation (`/evaluation`)

| Element | What it shows |
|---|---|
| Header facts | methods evaluated, relevance labels ("none"), sparse simulations; the note *"No relevance labels: results show agreement between methods, not accuracy"* |
| Evaluation run selector | which stored evaluation to show |
| **Methods compared** | Louvain ← Spearman → **Audience Bridge Score** → Spearman → node2vec |
| **Agreement with the proposed score** | Kendall, Spearman and top-k Jaccard (@1, @3, @5) between the score and each component and baseline, from −1 to 1 |
| Ranking quality / Temporal stability / Sparse-data robustness | the status of each test |
| All agreement results | the full pairwise table |
| Top-k results, Computational performance | top-k list statistics; time and memory per stage |

**Say:**
> "There are no ground-truth labels, so I measure consistency, not accuracy. In the thesis run:
> - the score agrees most with PageRank (Spearman 0.81)
> - it differs from Louvain communities (0.33)
> - it disagrees with node2vec (−0.29)
>
> So bridges are not just communities. With half the comments removed it stays at 0.81, against 0.51 for Louvain and 0.63 for node2vec."

**If they ask "Is it just counting shared commenters?":**
> "Mostly, on this sparse data: Spearman about 0.84 among pairs with evidence. But it chooses a different top bridge for 3–4 of 13 channels and explains why. I report that as a limitation."

---

## 11. Experiments (`/experiments`, not in the sidebar)

Open it by typing `/experiments` in the address bar, or by clicking the **Research snapshot** card on Pipeline Graph.

| Element | What it shows |
|---|---|
| Scoring experiments | each scoring run: ID, snapshot, created time, observation period, channels, weights, status |
| Snapshot comparison | rankings of the same organization compared across snapshots, when one exists |
| Research runs | every stored run (evaluation, node2vec, HGT, explainability, Louvain, score, PPR, metapath2vec, features, graph, topics) with status validated or recorded; click one for its configuration |
| Snapshots | every snapshot with channel, video and comment counts; the selected one is marked |

**Say:**
> "Everything is reproducible: each run has an ID that is a hash of its data and settings, and snapshots are never changed."

---

## 12. Live Results (`/live`)

| Element | What it shows |
|---|---|
| Header | "Live audience bridges", last update (for example "10 hours ago"), channels, videos, comments; run ID, 90-day window, pairs that share commenters |
| Red alert (only if needed) | last night's run failed; the last good results stay visible |
| Blue note (only if needed) | an **offline copy** is shown because this network can't reach the database |
| **Top bridges right now** | the 12 strongest live bridges; click one to see its trend |
| **Trend** | that pair's score across the nightly runs |
| Channels in the window | videos, comments and commenters per channel in the current window |
| Nightly runs | each run: status, time, videos, comments, quota used |

**Say:**
> "Every night at midnight a GitHub Actions job collects new data, scores the same 90-day window for every channel, and publishes the results here. No computer needs to be on. It's monitoring; my thesis results stay on the frozen snapshot."

---

## 13. Analyze Organization (`/analyze`)

| Step | What you see |
|---|---|
| Header | "Analyze an organization", counts of organizations analysed and fully analysed, videos per channel, a cloud of channel logos |
| **1 · Find channels** | a search box (for example "Sirasa", "Hiru"), a region selector, suggestion chips |
| **2 · Confirm channels** | candidate cards with logo, subscribers and evidence (links, name match). High-confidence channels are pre-ticked; you tick the ones that belong |
| **3 · Analyze** | a live progress grid per channel (waiting / collecting / done), then the stages |
| **Recent analyses** | one card per organization: date, status (quick or fully analysed), channels, videos, comments, **top bridge**, Compare checkbox, Open results |
| **Compare** | two organizations side by side: metrics and their top bridges |
| Complete analysis | adds HGT, node2vec and the evaluation to a quick analysis |

**Say:**
> "The method isn't limited to Derana. Any media organization can be analysed from the dashboard. YouTube doesn't publish ownership, so a person confirms which channels belong. Quick analyses use smaller samples and are exploratory; the thesis uses the confirmed Derana set."

---

## 14. System Status (`/status`)

| Element | What it shows |
|---|---|
| API | whether the backend is up |
| Research data | whether the selected snapshot has research data |
| Pipeline artifacts | which stored results exist (graph, features, PPR, topics, scores, evaluation, baselines, explanations) |

Show this only if asked how the system checks its own health.

---

## Quick answers when the panel points at the screen

| They point at | You say |
|---|---|
| a score of 0.000 / "No bridge evidence" | "The pair shares no commenters, so confidence is 0 and the score is 0. Content similarity alone can't create a bridge." |
| a dashed line | "Confidence below 0.5, which means fewer than 3 shared commenters." |
| two scores for the same pair | "The score is directional: per-source PageRank and normalisation." |
| ⅓ weights | "Equal, documented defaults. Without labels there was nothing to tune them on." |
| the HGT numbers | "A negative result: good link prediction, but collapsed channel vectors. metapath2vec stays primary." |
| "evaluation: none labels" | "No ground truth exists, so I report agreement, stability and robustness, not accuracy." |
| the live trend | "Nightly monitoring; consecutive windows overlap by 89 days, so changes aren't evidence of audience movement." |
| the 25-channel snapshot | "That's a quick organization analysis. The thesis uses the 18 confirmed Derana channels in `rs-20261010T081534Z`." |
