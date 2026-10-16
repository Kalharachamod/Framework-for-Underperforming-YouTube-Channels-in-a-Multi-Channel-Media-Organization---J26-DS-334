"""Optional local multilingual semantic adapter.

This module is lazy and opt-in. Importing it never downloads a model or runs
inference. Any model's coverage of Sinhala, Singlish, and code-mixed text must
be checked empirically before it is used for research decisions.
"""

from __future__ import annotations

from dataclasses import dataclass
import os
from typing import Sequence


class OptionalModelUnavailable(RuntimeError):
    """Raised when the optional semantic dependency or model is unavailable."""


@dataclass(frozen=True)
class SemanticModelConfig:
    model_name: str

    @classmethod
    def from_environment(cls) -> "SemanticModelConfig":
        model_name = os.environ.get("COMPONENT2_FEASIBILITY_MODEL", "").strip()
        if not model_name:
            raise OptionalModelUnavailable(
                "Set COMPONENT2_FEASIBILITY_MODEL only when an optional local model is approved."
            )
        return cls(model_name=model_name)


class MultilingualSemanticAdapter:
    """Encode text and label descriptions using sentence-transformers."""

    def __init__(self, config: SemanticModelConfig):
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:
            raise OptionalModelUnavailable("sentence-transformers is not installed") from exc
        self._model = SentenceTransformer(config.model_name)

    def score(self, texts: Sequence[str], label_descriptions: Sequence[str]) -> list[dict[str, object]]:
        if not label_descriptions:
            raise ValueError("At least one label description is required")
        text_embeddings = self._model.encode(list(texts), normalize_embeddings=True)
        label_embeddings = self._model.encode(list(label_descriptions), normalize_embeddings=True)
        scores = text_embeddings @ label_embeddings.T
        return [
            {
                "best_label": label_descriptions[int(row.argmax())],
                "score": float(row.max()),
            }
            for row in scores
        ]
