# Component 3: Systematic Literature Review Protocol

**Purpose:** confirm or refute the research gap claimed in [component3_research_position.md](component3_research_position.md) before thesis submission. STEP 32 used a *targeted* search. This protocol makes the search **systematic, repeatable and reportable** (PRISMA 2020 style), so the thesis can say *how* the gap was established.

**Outcome:** one of three verdicts on the claimed gap:
- **CONFIRMED:** no study does what Component 3 does.
- **NARROWED:** close work exists; reword the contribution.
- **REFUTED:** an equivalent method exists; reposition as an application study.

Record every step in [component3_review_screening_log.csv](component3_review_screening_log.csv).

---

## 1. Review questions

| ID | Question | Why it matters |
|---|---|---|
| RQ1 | Has any study ranked **individual channel pairs** (or creators / pages / communities) as potential audience bridges from shared audience interaction data? | Core gap: ranking vs. description |
| RQ2 | Has any study combined **graph diffusion** (PageRank / PPR / random walk with restart) with **content similarity** to relate channels or creators? | Closest methodological threat (PathRank-style hybrids) |
| RQ3 | Has any study used **heterogeneous** user–content–creator graphs (HIN, metapaths, HGT) for creator-to-creator relatedness? | Graph-schema novelty |
| RQ4 | Has any study **weighted channel / creator similarity by evidence quantity** (support, shrinkage, significance weighting)? | Confidence-formulation novelty |
| RQ5 | Has any study produced **directional** (asymmetric, source-specific) audience-overlap scores between channels? | Directionality claim |
| RQ6 | What evaluation is used when **no ground truth** for audience bridges exists? | Defends the consistency-based evaluation |

## 2. Eligibility criteria

**Include** when all of these apply:
- **Peer-reviewed** journal or conference paper, or arXiv preprint (flag preprints separately)
- **2010–2026**
- **English**
- **Platform:** YouTube, **or** another platform with creators, channels or pages and public audience interaction (Twitch, TikTok, Bilibili, Douyin, Reddit communities, Facebook pages, podcasts, X/Twitter accounts)
- **Addresses at least one of RQ1–RQ6**

**Exclude:**
- Studies using only private analytics with no method transferable to public data
- Video recommendation to *users* with no creator-to-creator relation (but keep it if it is a methodological analogue for RQ2 or RQ4)
- Pure misinformation or toxicity detection with no audience-overlap component
- No full text available after a reasonable attempt (record as "not retrieved")

## 3. Information sources

| Source | Access | Notes |
|---|---|---|
| Google Scholar | free | Use Publish or Perish to export the first 200 results per string |
| Scopus | SLIIT library | Primary structured database; export RIS/CSV |
| ACM Digital Library | free search | KDD, WWW, WSDM, RecSys, CSCW, HT, ICWSM (some) |
| IEEE Xplore | SLIIT library | Social network analysis, ASONAM |
| AAAI / ICWSM proceedings | free | ojs.aaai.org/index.php/ICWSM |
| arXiv (cs.SI, cs.IR, cs.CY) | free | Preprints; flag them |
| Semantic Scholar | free | Citation chasing |

Record the **date searched** and the **exact string** for every source. Do this all in one week so that results are comparable.

## 4. Search strings

Combine **blocks A AND B AND (C OR D OR E)**. Adapt the syntax per database; the Scopus syntax is shown.

| Block | Concept | Terms |
|---|---|---|
| A | Platform / unit | `YouTube OR "video channel*" OR creator* OR influencer* OR "content creator*" OR Twitch OR TikTok OR Bilibili` |
| B | Audience relation | `"audience overlap" OR "shared audience" OR "co-comment*" OR "commenter overlap" OR "shared commenter*" OR "user overlap" OR "cross-channel" OR "audience similarity" OR "audience migration"` |
| C | Graph / diffusion | `"personalized pagerank" OR "random walk with restart" OR diffusion OR "graph propagation"` |
| D | Representation | `"heterogeneous graph" OR "heterogeneous information network" OR metapath OR "graph embedding" OR node2vec OR "graph neural network"` |
| E | Ranking / similarity | `ranking OR "channel similarity" OR "creator similarity" OR "channel recommendation" OR "creator recommendation" OR "collaboration recommendation"` |

**Scopus example:**

```
TITLE-ABS-KEY ( ( youtube OR "video channel*" OR creator* OR influencer* OR twitch OR tiktok OR bilibili )
  AND ( "audience overlap" OR "shared audience" OR "co-comment*" OR "commenter overlap" OR "user overlap" OR "cross-channel" OR "audience similarity" )
  AND ( "personalized pagerank" OR "random walk" OR diffusion OR "heterogeneous graph" OR metapath OR "graph embedding" OR node2vec OR ranking OR "channel similarity" OR "creator recommendation" ) )
  AND PUBYEAR > 2009
```

**Additional targeted strings** (RQ2 and RQ4 analogues; methods may come from outside YouTube):
1. `"personalized pagerank" AND ( "content similarity" OR "semantic similarity" ) AND ( hybrid OR recommendation )`
2. `( "significance weighting" OR "shrinkage" OR "support weighting" ) AND similarity AND ( "collaborative filtering" OR neighbourhood )`
3. `"influencer" AND ( "brand matching" OR "audience overlap" OR "collaboration" ) AND ( graph OR network )`. This targets the marketing / creator-economy literature flagged in STEP 32.
4. `( "co-commenting" OR "commenter network" ) AND YouTube`

## 5. Citation chasing (snowballing)

Go **backward** (their reference lists) and **forward** (who cites them, via Google Scholar "Cited by" and Semantic Scholar) from these seeds:

| Seed | Why |
|---|---|
| [R1] Horta Ribeiro et al. 2020, *Auditing Radicalization Pathways on YouTube* | Most-cited YouTube audience-overlap / migration study |
| [R2] Violot et al. 2025, *YouTube's Political Communication Networks* | Closest data and graph design |
| [R7] Boesinger et al. 2023, *Tube2Vec* | Closest channel-representation work |
| [R9] *PathRank* | Closest PPR + content hybrid |
| [R12] Clark & Zaitsev 2020, *Subscription-based Channel Embeddings* | Audience-based channel similarity |
| [R13] Lee & Oh 2025, *K-pop diffusion … brokers* | "Broker" vocabulary close to "bridge"; **read in full** |

Run one round of forward and backward chasing. Run a second round only from newly included studies that score as a high threat (see section 7).

## 6. Screening procedure

1. **Deduplicate** all exports (Zotero or a spreadsheet; match on DOI, then title).
2. **Title / abstract screening** against section 2. Record include, exclude or maybe, with the exclusion reason code:

   | Code | Reason |
   |---|---|
   | E1 | wrong platform or unit |
   | E2 | no audience relation |
   | E3 | user-level recommendation only |
   | E4 | not a research paper |
   | E5 | outside the date or language range |

3. **Full-text screening** of include and maybe records.
4. **Reliability:** ideally a second person (supervisor or teammate) screens a random 20 % independently. Report the agreement (Cohen's κ). If no second screener is available, state this as a limitation.
5. **PRISMA counts:** record the numbers at each stage (identified, after deduplication, screened, full-text assessed, included) for the PRISMA flow diagram.

## 7. Data extraction and threat scoring

For each included study, fill these columns in the log:
- platform
- data (interaction type)
- unit ranked or related
- graph type
- diffusion (Y/N)
- content similarity (Y/N)
- evidence weighting (Y/N)
- directional (Y/N)
- per-source ranking (Y/N)
- explainability (Y/N)
- evaluation / ground truth
- read level (full / abstract)

**Threat score** (0–6): one point each for diffusion, content similarity, evidence weighting, directional, per-source ranking between creators, and the same data type (public co-commenting or co-engagement).

| Score | Meaning | Action |
|---|---|---|
| 0–2 | Related work | Cite in the literature review |
| 3–4 | Close work | Add to [component3_closest_work_comparison.md](component3_closest_work_comparison.md); state the difference explicitly |
| 5–6 | **Gap threat** | Read in full. If equivalent, the verdict becomes NARROWED or REFUTED |

## 8. Synthesis and outputs

1. Update [component3_literature_gap_matrix.md](component3_literature_gap_matrix.md) with the included studies.
2. Write a PRISMA 2020 flow diagram (a thesis figure) and a summary table per RQ.
3. Revise the gap statement and the contribution wording if the verdict is NARROWED.
4. Upgrade read levels. Every study cited in the thesis must be read **in full**; replace all "(sum)" entries.
5. Resolve the open reference issues from STEP 32: authors and venue of [R6]; authors of [R9]; full reading of [R13].

## 9. Timeline (suggested)

| Day | Task |
|---|---|
| 1 | Run all database searches; export; deduplicate |
| 2–3 | Title / abstract screening |
| 4–5 | Full-text screening, extraction and threat scoring |
| 6 | Citation chasing round 1; screen new records |
| 7 | Synthesis: PRISMA counts, update the gap matrix and position, verdict |

## 10. Reporting in the thesis (method paragraph template)

> "A systematic search was conducted on [dates] in Scopus, IEEE Xplore, ACM DL, Google Scholar (first 200 results per query) and arXiv, using the strings in Appendix X. After removing duplicates, N records were screened by title and abstract and M full texts were assessed against predefined eligibility criteria, leaving K included studies. Backward and forward citation chasing from six seed studies added J studies. Each study was coded for diffusion, content similarity, evidence weighting, directionality and per-source ranking (Table X). No included study combined [...] / Study S is the closest, differing in [...]."

Fill N, M, K and J only from the log. Never estimate them.
