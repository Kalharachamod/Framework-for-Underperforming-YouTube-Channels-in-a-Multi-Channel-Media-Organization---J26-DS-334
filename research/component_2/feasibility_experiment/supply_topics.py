"""Experiment 3B: content-supply topic modelling from video metadata.

Supply is what each channel publishes. Each video becomes one document built
from its title, hashtags and the description lines that are specific to that
video (channel-wide boilerplate such as social links, crew lists and phone
numbers is removed by frequency, not by hand-written rules).

BERTopic over multilingual-e5-small embeddings (the same pinned model and
revision Component 3 uses) is the proposed method; LDA with the same number of
topics is the classical baseline required by proposal Section 3.9. Both are
scored with c_v coherence on identical tokenization. Outputs are per-channel
and per-channel-month supply distributions for later Jensen-Shannon comparison.
"""

from __future__ import annotations

import argparse
import json
import re
import unicodedata
from collections import Counter
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


SEED = 42
E5_MODEL = "intfloat/multilingual-e5-small"
E5_REVISION = "614241f622f53c4eeff9890bdc4f31cfecc418b3"  # same pin as Component 3
BOILERPLATE_MIN_SHARE = 0.10
BOILERPLATE_MIN_VIDEOS = 5
DESCRIPTION_CHARS = 600
MIN_TOPIC_SIZE = 15
TOP_WORDS = 10

PACKAGE_DIR = Path(__file__).resolve().parent
DEFAULT_VIDEOS = PACKAGE_DIR / "outputs" / "experiment_3a" / "expanded_videos.csv"
DEFAULT_OUTPUT_DIR = PACKAGE_DIR / "outputs" / "experiment_3b"

_URL = re.compile(r"(?:https?://|www\.)\S+", re.IGNORECASE)
_EMAIL = re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")
_PHONE = re.compile(r"(?:\+?\d[\d\s-]{7,}\d)")
_SPACE = re.compile(r"\s+")
# Production-crew credit lines ("Director : ...", "Vision Mixer : ...") describe who made a
# programme, not what it offers viewers. Host, judges, cast and contestants are kept because
# audiences request and discuss them.
_CREW_CREDIT = re.compile(
    r"^\s*(?:senior\s+|supervising\s+|executive\s+|creative\s+|music\s+|head\s+of\s+)*"
    r"(?:director|producer|produce|script|script\s+writer|writer|editor|camera|cinematography|dop|"
    r"vision\s+mixer|sound|set\s+designer|post\s+production|vfx|technical|gfx|cg|make\s*-?\s*up|makeup|"
    r"information\s+technology|lighting|programming|tags|full\s+program)\b[^:–\-]{0,40}[:–\-]",
    re.IGNORECASE,
)
_TOKEN = re.compile(r"[඀-෿‌‍]+|[a-z][a-z']+")
# Brand and packaging words that name the channel or the upload, not its content.
STOPWORDS = frozenset(
    """
    the and of to in a an for on with at by is are this that from you your our we it be as or
    tv derana deranalk tvderana fmderana adaderana ada lk official full video videos channel
    season episode ep part watch subscribe follow us live new latest updates programmes programme
    shorts short viral trending
    """.split()
) | frozenset({"සහ", "හා", "මේ", "ඒ", "ද", "ය", "වන", "සඳහා", "බව", "ලෙස", "කළ", "විසින්"})


def clean_line(text: object) -> str:
    if not isinstance(text, str):
        return ""
    value = unicodedata.normalize("NFC", text)
    value = _URL.sub(" ", value)
    value = _EMAIL.sub(" ", value)
    value = _PHONE.sub(" ", value)
    value = value.replace("#", " ")
    value = "".join(" " if unicodedata.category(ch) == "Cc" else ch for ch in value)
    return _SPACE.sub(" ", value).strip()


def boilerplate_lines(descriptions: pd.Series) -> set[str]:
    """Description lines repeated across a channel's videos are packaging, not content."""

    counts: Counter[str] = Counter()
    for description in descriptions.fillna(""):
        counts.update({line.strip() for line in str(description).splitlines() if line.strip()})
    threshold = max(BOILERPLATE_MIN_VIDEOS, BOILERPLATE_MIN_SHARE * len(descriptions))
    return {line for line, count in counts.items() if count >= threshold}


def build_supply_documents(videos: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for channel, group in videos.groupby("channel_name", sort=True):
        repeated = boilerplate_lines(group["description"])
        for video in group.itertuples(index=False):
            title = clean_line(video.title)
            kept = [
                clean_line(line)
                for line in str(video.description if isinstance(video.description, str) else "").splitlines()
                if line.strip() and line.strip() not in repeated and not _CREW_CREDIT.match(line)
            ]
            description = " ".join(part for part in kept if part and part != title)[:DESCRIPTION_CHARS]
            rows.append(
                {
                    "video_id": video.video_id,
                    "channel_name": channel,
                    "published_at": video.published_at,
                    "view_count": getattr(video, "view_count", np.nan),
                    "title": title,
                    "document": " . ".join(part for part in (title, description) if part),
                }
            )
    documents = pd.DataFrame(rows)
    documents["tokens"] = documents["document"].map(tokenize)
    return documents


def tokenize(text: str) -> list[str]:
    tokens = _TOKEN.findall(unicodedata.normalize("NFC", text).lower())
    return [token for token in tokens if len(token) > 1 and token not in STOPWORDS]


def embed(documents: list[str]) -> np.ndarray:
    import torch
    from sentence_transformers import SentenceTransformer

    torch.manual_seed(SEED)
    model = SentenceTransformer(E5_MODEL, revision=E5_REVISION, device="cpu")
    return model.encode(
        [f"query: {text}" for text in documents],
        batch_size=32,
        normalize_embeddings=True,
        show_progress_bar=False,
    ).astype(np.float32)


def fit_bertopic(documents: pd.DataFrame, embeddings: np.ndarray) -> tuple[Any, np.ndarray]:
    from bertopic import BERTopic
    from hdbscan import HDBSCAN
    from sklearn.feature_extraction.text import CountVectorizer
    from umap import UMAP

    model = BERTopic(
        embedding_model=None,
        umap_model=UMAP(n_neighbors=15, n_components=5, min_dist=0.0, metric="cosine", random_state=SEED),
        hdbscan_model=HDBSCAN(min_cluster_size=MIN_TOPIC_SIZE, metric="euclidean", prediction_data=True),
        vectorizer_model=CountVectorizer(tokenizer=tokenize, lowercase=False, token_pattern=None, min_df=2),
        top_n_words=TOP_WORDS,
        calculate_probabilities=False,
    )
    topics, _ = model.fit_transform(documents["document"].tolist(), embeddings=embeddings)
    return model, np.asarray(topics)


def bertopic_topic_words(model: Any) -> dict[int, list[str]]:
    # Topics whose documents share no repeated vocabulary (e.g. heterogeneous news headlines)
    # get empty c-TF-IDF words; they are kept as topics but reported as unlabelled.
    return {
        int(topic): [word for word, _ in words if word][:TOP_WORDS]
        for topic, words in model.get_topics().items()
        if int(topic) != -1
    }


def fit_lda(tokens: list[list[str]], num_topics: int) -> tuple[Any, Any, np.ndarray, dict[int, list[str]]]:
    from gensim.corpora import Dictionary
    from gensim.models import LdaModel

    dictionary = Dictionary(tokens)
    dictionary.filter_extremes(no_below=2, no_above=0.5)
    corpus = [dictionary.doc2bow(doc) for doc in tokens]
    lda = LdaModel(
        corpus=corpus,
        id2word=dictionary,
        num_topics=num_topics,
        passes=10,
        random_state=SEED,
        alpha="auto",
        eta="auto",
    )
    assignment = np.array(
        [max(lda.get_document_topics(bow, minimum_probability=0.0), key=lambda item: item[1])[0] if bow else -1 for bow in corpus]
    )
    words = {k: [word for word, _ in lda.show_topic(k, topn=TOP_WORDS)] for k in range(num_topics)}
    return lda, dictionary, assignment, words


def coherence_cv(topic_words: dict[int, list[str]], tokens: list[list[str]]) -> dict[str, Any]:
    from gensim.corpora import Dictionary
    from gensim.models import CoherenceModel

    dictionary = Dictionary(tokens)
    usable = {k: [w for w in words if w in dictionary.token2id] for k, words in topic_words.items()}
    usable = {k: words for k, words in usable.items() if len(words) >= 3}
    if not usable:
        return {"mean": float("nan"), "per_topic": {}}
    model = CoherenceModel(topics=list(usable.values()), texts=tokens, dictionary=dictionary, coherence="c_v", processes=1)
    scores = model.get_coherence_per_topic()
    return {"mean": float(np.mean(scores)), "per_topic": {int(k): float(s) for k, s in zip(usable, scores)}}


def supply_distributions(documents: pd.DataFrame, column: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    assigned = documents.loc[documents[column].ne(-1)]
    by_channel = pd.crosstab(assigned["channel_name"], assigned[column], normalize="index")
    month = pd.to_datetime(assigned["published_at"], utc=True, errors="coerce", format="ISO8601").dt.strftime("%Y-%m")
    by_month = (
        assigned.assign(month=month)
        .groupby(["channel_name", "month", column])
        .size()
        .rename("videos")
        .reset_index()
    )
    by_month["share"] = by_month["videos"] / by_month.groupby(["channel_name", "month"])["videos"].transform("sum")
    return by_channel, by_month


def run(videos_path: Path = DEFAULT_VIDEOS, output_dir: Path = DEFAULT_OUTPUT_DIR) -> dict[str, Any]:
    videos = pd.read_csv(videos_path, dtype={"video_id": "string"}, keep_default_na=False)
    documents = build_supply_documents(videos)
    documents = documents.loc[documents["tokens"].map(len).gt(0)].reset_index(drop=True)

    embeddings = embed(documents["document"].tolist())
    bertopic_model, raw_topics = fit_bertopic(documents, embeddings)
    documents["bertopic_raw"] = raw_topics
    reduced = bertopic_model.reduce_outliers(documents["document"].tolist(), raw_topics, strategy="embeddings", embeddings=embeddings)
    documents["bertopic"] = np.asarray(reduced)
    bert_words = bertopic_topic_words(bertopic_model)

    lda, _, lda_assignment, lda_words = fit_lda(documents["tokens"].tolist(), num_topics=len(bert_words))
    documents["lda"] = lda_assignment

    tokens = documents["tokens"].tolist()
    coherence = {"bertopic": coherence_cv(bert_words, tokens), "lda": coherence_cv(lda_words, tokens)}

    output_dir.mkdir(parents=True, exist_ok=True)
    documents.drop(columns=["tokens"]).to_csv(output_dir / "supply_documents_topics.csv", index=False, encoding="utf-8")
    np.save(output_dir / "supply_embeddings_e5_small.npy", embeddings)
    for name, words in (("bertopic", bert_words), ("lda", lda_words)):
        topic_frame = pd.DataFrame(
            [
                {
                    "topic": k,
                    "videos": int((documents[name] == k).sum()),
                    "c_v": coherence[name]["per_topic"].get(k),
                    "top_words": " ".join(w),
                    "channels": "; ".join(
                        f"{c}:{n}" for c, n in documents.loc[documents[name] == k, "channel_name"].value_counts().head(3).items()
                    ),
                    "example_titles": " || ".join(documents.loc[documents[name] == k, "title"].head(3)),
                }
                for k, w in sorted(words.items())
            ]
        ).sort_values("videos", ascending=False)
        topic_frame.to_csv(output_dir / f"{name}_topics.csv", index=False, encoding="utf-8")
        by_channel, by_month = supply_distributions(documents, name)
        by_channel.to_csv(output_dir / f"{name}_supply_by_channel.csv", encoding="utf-8")
        by_month.to_csv(output_dir / f"{name}_supply_by_channel_month.csv", index=False, encoding="utf-8")

    summary = {
        "videos": int(len(documents)),
        "videos_by_channel": documents["channel_name"].value_counts().to_dict(),
        "embedding_model": {"name": E5_MODEL, "revision": E5_REVISION, "prefix": "query: "},
        "bertopic": {
            "topics": len(bert_words),
            "raw_outlier_share": float((raw_topics == -1).mean()),
            "min_topic_size": MIN_TOPIC_SIZE,
            "c_v_mean": coherence["bertopic"]["mean"],
        },
        "lda": {"topics": len(lda_words), "c_v_mean": coherence["lda"]["mean"]},
        "seed": SEED,
    }
    (output_dir / "experiment_3b_summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="Experiment 3B content-supply topic modelling.")
    parser.add_argument("--videos", type=Path, default=DEFAULT_VIDEOS)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args()
    print(json.dumps(run(args.videos, args.output_dir), indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
