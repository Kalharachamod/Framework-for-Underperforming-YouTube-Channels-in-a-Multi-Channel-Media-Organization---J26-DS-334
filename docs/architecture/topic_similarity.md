# Topic Modeling and Topic Similarity (Component 3)

Code: [`research/component_3/model/topic_similarity.py`](../../research/component_3/model/topic_similarity.py) · Tests: [`tests/component_3/test_topic_similarity.py`](../../tests/component_3/test_topic_similarity.py)

```
graph → metapath2vec / HGT → Personalized PageRank → [topic similarity]
  → (later) confidence weighting → Audience Bridge Score
```

Topic similarity is **content-semantic evidence**: how similar two channels' public video content is. It measures **content affinity only**. It does **not** prove audience overlap, audience migration, shared viewers, subscriber movement, influence, causality or conversion, and it isn't an Audience Bridge Score.

```powershell
python -m research.component_3.model.topic_similarity                    # primary (multilingual e5), latest snapshot
python -m research.component_3.model.topic_similarity --backend char_lsa # exploratory baseline
python -m research.component_3.model.topic_similarity --topics 8         # optional topic clustering
```

## Data and text fields

- **Input:** the research snapshot's `videos` table (STEP 12). There are no API calls and no other data sources.
- **Text per video:** `title` + the first **1,000 characters** of the cleaned `description`.
  - Descriptions are truncated because they often end in boilerplate: links, social handles, sponsor text.
  - `tags` aren't used, since they're often missing or generic.
- **Text isn't stored** in the artifacts; only its length and a SHA-256 (for provenance) are kept.

## Preprocessing (`text-v1`, deterministic)

1. Unicode **NFC** normalization.
2. Remove URLs (`http…`, `www.…`) and e-mail addresses.
3. Drop `#` from hashtags, keeping the word.
4. Remove control characters only. **Zero-width joiners are kept**, because Sinhala conjuncts such as "ශ්‍රී" need them.
5. Collapse whitespace.

There's **no lowercasing, stemming, stop-word removal or translation**, so Sinhala, Tamil, English and mixed text keep their meaning.

**Insufficient text:** a video with **fewer than 3 letters** after cleaning (for example an empty title plus only a link) is marked `insufficient_text`. It gets **no embedding**, is excluded from its channel profile, and is reported. Nothing is fabricated.

## Semantic representation

| Backend | Role | Details |
|---|---|---|
| `e5` | **Primary** | `intfloat/multilingual-e5-small` at pinned revision `614241f6…`, via `sentence-transformers`. 384 dimensions, L2-normalized, `"query: "` prefix (symmetric use), CPU |
| `char_lsa` | Exploratory baseline | Character n-gram (2–4) TF-IDF + truncated SVD (64 dimensions, seeded), fitted on the snapshot's texts. Works for any script, but **not cross-lingual** |

**Multilingual handling:**
- e5 is trained on about 100 languages, **including Sinhala and Tamil**, and maps them into one space. Checked on test sentences: Sinhala ↔ English "cricket match" scored 0.92, Tamil ↔ English 0.92, and cricket ↔ cooking 0.78.
- **Known limitations:**
  - The model is small, so quality on low-resource languages is lower than on English.
  - Text longer than 512 tokens is truncated.
  - Scores are compressed into a **high range** (anisotropy: unrelated content still scores around 0.75–0.8). See the centered similarity below.
- The model is downloaded once from Hugging Face; the tests never download it.

## Channel profiles

```
profile(channel) = normalize( mean( normalize(e_v) for each usable video v of the channel ) )
```

- **Each video counts once**, so a channel's profile is its average content direction.
- **Channels with more videos don't dominate:** cosine similarity is scale-free, and every channel has exactly one profile. `max_videos_per_channel=N` optionally caps each channel to its **N most recent** videos, deterministically.
- **No profile** (`profile_available = false`) for a channel with **no usable video**, or an all-zero mean.

**Coverage per channel:** `total_videos`, `usable_videos`, `insufficient_text_videos`, `coverage_ratio = usable / total` (NULL when there are no videos), and `profile_available`. This is input for later confidence weighting, **not** a confidence score.

## Topic similarity

```
topic_similarity(A, B) = cos(profile_A, profile_B) = (A · B) / (‖A‖ ‖B‖)      range [−1, 1]
```

- **Symmetric**, since similarity(A, B) = similarity(B, A). It's stored for every **ordered** pair to match the diffusion output, with no self pairs. This doesn't make it directional.
- **No forced rescaling to [0, 1].** The raw cosine is kept; it can be negative in principle, though rarely is with e5.
- **Undefined values:** if either channel has no profile, or a vector is zero, the similarity is **NULL**, never 0.
- **`topic_similarity_centered`** (secondary, labelled): the cosine after subtracting the mean profile of the snapshot's channels. It removes the direction shared by all channels (the anisotropy above) and spreads out relative differences. It's **within-snapshot only**.

Output columns: `source_channel_id`, `destination_channel_id` (`channel:<id>`, as in the PageRank output), `topic_similarity`, `topic_similarity_centered`, `both_profiles_available`, `snapshot_id`, `experiment_id`.

## Optional topic clustering

`n_topics=K` runs KMeans (seeded, `n_init=10`) on the usable video embeddings:
- **Runs only with at least `K × min_videos_per_topic` usable videos.** Otherwise it's **skipped** with the reason, and the continuous representation is still produced.
- **Topic IDs** are `t00, t01, …`, ordered by cluster size and then by the smallest member video, so they're stable for a given seed.
- **Labels** are only `"cluster tNN"`; no semantic labels are invented.
- **Assignments** are hard (weight 1.0) and **directly usable as graph topic nodes**: `hetero_graph.build_graph(snapshot, topics=…, video_topics=…)` creates `topic:<id>` nodes and `video –has_topic→ topic` edges. The saved STEP 13 graph isn't changed.

## Temporal boundary and leakage

- **Snapshot-level:** profiles are built per research snapshot, as of the snapshot's extraction time by default.
- **Historical profiles:** `as_of=<time>` uses only videos **published at or before** that time, and an `as_of` after the snapshot is refused. Each video's `published_at` is kept for later topic-drift analysis.
- **Leakage note:** the `char_lsa` baseline is fitted on the snapshot's own texts, which is transductive and fine for descriptive similarity. For prediction, fit it only on texts up to the prediction time. e5 is pre-trained and fitted on nothing here.

## Artifacts

`data/processed/component_3/<snapshot_id>/topics/<top-…>/` (git-ignored; written once per experiment):

| File | Contents |
|---|---|
| `video_semantic_embeddings.parquet` | `video_id`, `channel_id`, `published_at`, `text_status`, `text_chars`, `text_sha256`, `embedding` |
| `channel_semantic_profiles.parquet` | Coverage columns, `profile_available`, `profile` |
| `channel_topic_similarity.parquet` | Channel-pair similarity (above) |
| `topics.parquet`, `video_topics.parquet` | Only if clustering ran |
| `topic_run.json` | Experiment ID, snapshot, `as_of`, model name and **version**, preprocessing version and steps, embedding dimension, aggregation, similarity definitions, clustering configuration, seed, coverage, creation time, validation |

Experiment ID: `top-<hash(snapshot + as_of + configuration + model version + preprocessing version)>`.

## Validation

Each of these is a failure:
- duplicate videos or channel profiles
- videos for unknown channels
- inconsistent embedding dimensions
- non-finite values
- an embedding on an `insufficient_text` video, or a missing one on a usable video
- similarity outside [−1, 1]
- **asymmetric** similarity
- a similarity value without both profiles, or missing with both
- a foreign `snapshot_id`
- topic assignments to unknown or text-less videos, or to unknown topic IDs

## Limitations

- **Small text sample:** about 10 recent videos per channel, mostly titles plus short descriptions. Profiles reflect recent content only.
- **Model limits:** see the multilingual handling above.
- **No cross-script matching in the baseline:** `char_lsa` can't match Sinhala text to English text.
- **Content only:** topic similarity says nothing about audiences.
