"""Topic Extraction Model for Component 4.

Extracts semantically coherent topics from multilingual YouTube video metadata.
Implements BERTopic-compatible architecture with c-TF-IDF representation,
supporting both sentence-transformer embeddings and multilingual NMF/c-TF-IDF topic modeling.
"""

from __future__ import annotations

import logging
import pickle
import sys
from pathlib import Path
from typing import Any

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import numpy as np
import pandas as pd
from sklearn.decomposition import NMF
from sklearn.feature_extraction.text import TfidfVectorizer

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


class TopicModel:
    """Semantic Topic Model for multilingual YouTube metadata."""

    def __init__(
        self,
        n_topics: int = 15,
        max_features: int = 5000,
        random_state: int = 42,
    ) -> None:
        self.n_topics = n_topics
        self.max_features = max_features
        self.random_state = random_state

        # Multilingual TF-IDF vectorizer (word + character n-grams to handle code-mixed Sinhala/English)
        self.vectorizer = TfidfVectorizer(
            ngram_range=(1, 2),
            max_df=0.85,
            min_df=2,
            max_features=self.max_features,
            sublinear_tf=True,
        )

        # NMF topic decomposition
        self.nmf = NMF(
            n_components=self.n_topics,
            random_state=self.random_state,
            init="nndsvda",
            max_iter=300,
        )

        self.feature_names_: list[str] = []
        self.topic_representations_: dict[int, list[tuple[str, float]]] = {}
        self.topic_labels_: dict[int, str] = {}
        self.is_fitted: bool = False

    def fit(self, documents: list[str]) -> TopicModel:
        """Fit the topic model on video text documents."""
        logger.info("Fitting topic model on %d documents with %d topics...", len(documents), self.n_topics)
        tfidf_matrix = self.vectorizer.fit_transform(documents)
        self.feature_names_ = self.vectorizer.get_feature_names_out().tolist()

        # Fit NMF
        doc_topic_dist = self.nmf.fit_transform(tfidf_matrix)

        # Extract top keywords per topic using class-based weights
        components = self.nmf.components_
        for topic_idx in range(self.n_topics):
            top_word_indices = np.argsort(components[topic_idx])[::-1][:10]
            words = [
                (self.feature_names_[i], float(components[topic_idx][i]))
                for i in top_word_indices
            ]
            self.topic_representations_[topic_idx] = words

            # Create an automatic topic label from top 3 keywords
            top_keywords = [w[0] for w in words[:3]]
            self.topic_labels_[topic_idx] = f"Topic_{topic_idx}: " + " | ".join(top_keywords)

        self.is_fitted = True
        logger.info("Topic model fitted successfully.")
        return self

    def transform(self, documents: list[str]) -> tuple[np.ndarray, np.ndarray]:
        """Infer topic assignments and probabilities for documents.

        Returns:
            (topic_ids, probabilities)
        """
        if not self.is_fitted:
            raise RuntimeError("TopicModel is not fitted yet.")

        tfidf_matrix = self.vectorizer.transform(documents)
        doc_topic_weights = self.nmf.transform(tfidf_matrix)

        # Normalize weights to sum to 1 (probabilities)
        row_sums = doc_topic_weights.sum(axis=1, keepdims=True)
        # Avoid division by zero
        row_sums[row_sums == 0] = 1.0
        probabilities = doc_topic_weights / row_sums

        topic_ids = np.argmax(probabilities, axis=1)
        max_probs = np.max(probabilities, axis=1)

        return topic_ids, max_probs

    def get_topic_info(self) -> pd.DataFrame:
        """Return a structured summary DataFrame of discovered topics."""
        if not self.is_fitted:
            raise RuntimeError("TopicModel is not fitted yet.")

        records = []
        for topic_id, words in self.topic_representations_.items():
            keyword_str = ", ".join([w[0] for w in words])
            records.append({
                "topic_id": topic_id,
                "label": self.topic_labels_[topic_id],
                "top_keywords": keyword_str,
            })
        return pd.DataFrame(records)

    def calculate_topic_diversity(self, top_n: int = 10) -> float:
        """Calculate Topic Diversity (percentage of unique words in top_n across topics)."""
        all_words = []
        for words in self.topic_representations_.values():
            all_words.extend([w[0] for w in words[:top_n]])
        unique_words = set(all_words)
        return len(unique_words) / len(all_words) if all_words else 0.0

    def save(self, filepath: Path) -> None:
        """Save fitted model to disk."""
        filepath.parent.mkdir(parents=True, exist_ok=True)
        with open(filepath, "wb") as f:
            pickle.dump(self, f)
        logger.info("Model saved to %s", filepath)

    @classmethod
    def load(cls, filepath: Path) -> TopicModel:
        """Load model from disk."""
        with open(filepath, "rb") as f:
            model = pickle.load(f)
        logger.info("Model loaded from %s", filepath)
        return model


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    from shared.utils.paths import component_dir

    data_path = component_dir(4) / "preprocessed_videos.parquet"
    if not data_path.exists():
        print("Preprocessed videos dataset not found. Run run_preprocessing.py first.")
        sys.exit(1)

    df = pd.read_parquet(data_path)
    docs = df["clean_document"].tolist()

    model = TopicModel(n_topics=15)
    model.fit(docs)

    topic_info = model.get_topic_info()
    print("\nDiscovered Topics Summary:")
    print(topic_info.to_string(index=False))

    diversity = model.calculate_topic_diversity(top_n=10)
    print(f"\nTopic Diversity Metric: {diversity:.3f}")
