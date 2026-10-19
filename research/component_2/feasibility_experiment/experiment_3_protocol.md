# Experiment 3: Expanded Derana Corpus (3A) and Content-Supply Topics (3B)

## Why Experiment 3 was needed

The 2,000-comment pilot cannot support the proposal's later stages:

- Ada Derana and TV Derana pilot videos span only 3-4 days, so no
  temporal validation of demand-supply gaps is possible on them.
- The pilot holds only the videos that received sampled comments, while
  content-supply modelling (Objective 4) needs each channel's catalogue.
- A read-only YouTube Data API audit on 2026-10-19 (about 1,100 quota units)
  showed that the team's Supabase snapshot holds only about 2-12% of public
  comments for the target channels, and that the entertainment channels run in
  seasons (for example Dream Star April 2025 - January 2026, then a new season
  from October 2026; Derana 60 Plus April-June 2025 and November 2025 - April
  2026). Seasons give a natural setting for temporal validation: demand
  expressed in one season can be compared with what the next season supplied.

## Collection (read-only)

Run `expansion_20261019`, stored under the Git-ignored
`data/raw/component_2/expansion_20261019/`:

- Supply: YouTube metadata (title, description, tags, category, duration,
  view/like/comment counts) for every upload since 2025-04-01 of Dream Star,
  FM Derana, Derana 60 Plus, Derana Little Star, Ada Derana Sports, Lokaya Saha
  Lokayo and TV Derana (the latest 8,000 TV Derana uploads, from 2025-08-08).
- Demand: comment threads for every commented upload of the first six channels,
  capped at 300 threads per video so a few viral videos cannot dominate, with up
  to five replies per thread as returned by `commentThreads`.
- Commenter identities are stored only as `author_hash`, the project's salted
  HMAC from `shared/utils/privacy.py`. Nothing is written to Supabase.
- Ada Derana and TV Derana comments were not collected (over 600,000 public
  comments, beyond a daily quota); their pilot comments remain available.

## 3A: Expanded corpus and frozen v2 partition

Implemented in `build_expanded_corpus.py`.

1. Pilot and expansion comments are merged by `comment_id`. Pilot text wins for
   the 2,000 frozen comments so v1 evidence stays byte-identical; their
   `author_hash` is attached from the expansion when available.
2. The v1 Experiment 2A.2 manifest and lock are verified and never rewritten.
   Every v1 comment keeps its v1 role.
3. New comments are routed by video:

| New comment on | v2 role | Use |
|---|---|---|
| a v1 held-out video | `heldout_quarantine` | never used or reviewed |
| a v1 calibration video | `calibration_quarantine` | never used or reviewed |
| a v1 development video | `expanded_development_pool` | training and review |
| a video new to the corpus | `expanded_heldout_evaluation` (about 15% of videos) or `expanded_development_pool` | see below |

4. Videos new to the corpus are sampled for a fresh held-out slice within
   channel x publication-quarter strata, by a seeded SHA-256 rank of `video_id`
   only (seed `20261020`). Comment text, labels, rules and engagement do not
   influence selection. Inclusion probabilities are recorded. This gives the
   channels the pilot never covered (Derana 60 Plus, Little Star, Lokaya Saha
   Lokayo) a protected evaluation set.
5. The v2 identity is frozen in `experiment_3a_corpus_lock.json` with its own
   fingerprint algorithm (`sha256-canonical-partition-v2-expanded`), the v1
   fingerprint it extends, role counts and input hashes. A rebuild that differs
   from the lock fails; a new lock version is a research decision.
6. `ExpandedCorpusGuard` admits only `development_pool` and
   `expanded_development_pool` comments into training data.

Text provenance follows schema v1: `raw_comment_text`, its SHA-256,
`normalized_text` (NFC) and `cleaned_text`.

## 3B: Content-supply topic modelling

Implemented in `supply_topics.py`.

### Supply documents

One document per video: cleaned title plus description lines specific to that
video, truncated to 600 characters. Two cleaning rules are frequency- and
label-based rather than hand-picked:

- Lines repeated in at least 10% (and at least five) of a channel's videos are
  channel packaging (social links, channel slogans, phone numbers) and removed.
  A consequence is that information constant across a whole channel, such as a
  judging panel listed on every video, is also removed. Such constants cannot
  distinguish one supply topic from another within the channel.
- Labelled production-crew credit lines (director, producer, script, camera,
  vision mixer, GFX and similar) are removed. Host, judges, cast and contestant
  lines are kept because audiences request and discuss on-screen people.

URLs, e-mail addresses and phone numbers are removed and Sinhala conjuncts
(ZWJ) preserved. Tokenisation for c-TF-IDF, LDA and coherence keeps Sinhala and
Latin word tokens and removes only English/Sinhala function words and
channel-branding words (derana, tv, season, episode, official and similar).

### Models

- Proposed: BERTopic over `intfloat/multilingual-e5-small` embeddings at the
  revision pinned by Component 3 (`614241f6…`), with the `query: ` prefix; UMAP
  (15 neighbours, 5 dimensions, seed 42), HDBSCAN (minimum topic size 15),
  outliers reassigned to the nearest topic by embedding similarity.
- Baseline: gensim LDA with the same number of topics (proposal Section 3.9).
- Both scored with c_v coherence on identical tokens (top 10 words).

### First results (10,104 videos, 8 channels)

| Summary of topic c_v | BERTopic | LDA |
|---|---:|---:|
| Mean | 0.687 | 0.407 |
| Median | 0.704 | 0.338 |
| Video-weighted mean | 0.606 | 0.443 |
| Mean excluding topics with c_v >= 0.95 | 0.577 | 0.371 |
| Topics with c_v >= 0.95 | 39 / 151 | 9 / 151 |

BERTopic exceeds the LDA baseline on every summary. The near-perfect topics
are mostly teledrama cast and contestant lists: they are real programme
identity, but repeated name lists inflate c_v, so the robust summaries above
should be reported alongside the mean. The raw outlier share before
reassignment was 12.5%. One cluster of heterogeneous Ada Derana news headlines
has no repeated vocabulary and is reported as unlabelled.

### Methodological finding for the gap stage

TV Derana contributes 8,000 of the 10,104 documents, so a single
organisation-wide model allocates most topics to teledramas. Single-programme
channels collapse into few topics (Derana Little Star 5, Derana 60 Plus 7,
Ada Derana Sports 7). Jensen-Shannon Divergence compares demand and supply
within a channel, so the next stage should fit a channel-specific topic space
shared by that channel's video documents and its demand comments. The
organisation-wide model remains useful for cross-channel description.

## Not done in Experiment 3

No comment was labelled, no demand classifier was trained, no demand topics or
divergence were computed, and the v1 held-out and calibration comments were not
read for modelling.

## Reproduce

```bash
.venv/bin/python -m research.component_2.feasibility_experiment.build_expanded_corpus
.venv/bin/python -m research.component_2.feasibility_experiment.supply_topics
```

Outputs are written to the Git-ignored `outputs/experiment_3a/` and
`outputs/experiment_3b/` directories.
