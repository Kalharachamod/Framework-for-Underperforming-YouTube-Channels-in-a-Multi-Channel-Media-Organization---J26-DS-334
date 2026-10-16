"""Script detection and conservative multilingual preprocessing."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

import pandas as pd


URL_RE = re.compile(r"https?://\S+|www\.\S+", re.IGNORECASE)
WHITESPACE_RE = re.compile(r"\s+")
REPEATED_CHAR_RE = re.compile(r"(.)\1{3,}", re.UNICODE)
LATIN_RE = re.compile(r"[A-Za-z]")
SINHALA_RE = re.compile(r"[\u0D80-\u0DFF]")
ALNUM_RE = re.compile(r"[\w\u0D80-\u0DFF]", re.UNICODE)


@dataclass(frozen=True)
class PreprocessConfig:
    url_token: str = "<URL>"
    very_short_threshold: int = 5
    repeated_comment_threshold: int = 3


def normalize_unicode(text: object) -> str:
    if text is None or pd.isna(text):
        return ""
    value = str(text)
    if value.strip().lower() in {"null", "none", "nan"}:
        return ""
    return unicodedata.normalize("NFC", value)


def normalize_whitespace(text: str) -> str:
    return WHITESPACE_RE.sub(" ", text).strip()


def replace_urls(text: str, token: str = "<URL>") -> str:
    return URL_RE.sub(token, text)


def has_sinhala(text: str) -> bool:
    return bool(SINHALA_RE.search(text or ""))


def has_latin(text: str) -> bool:
    return bool(LATIN_RE.search(text or ""))


def has_mixed_sinhala_latin(text: str) -> bool:
    return has_sinhala(text) and has_latin(text)


def is_emoji_only(text: str) -> bool:
    cleaned = normalize_whitespace(text)
    if not cleaned:
        return False
    return not bool(ALNUM_RE.search(cleaned))


def has_repeated_char_pattern(text: str) -> bool:
    return bool(REPEATED_CHAR_RE.search(text or ""))


def word_count(text: str) -> int:
    cleaned = normalize_whitespace(text)
    return 0 if not cleaned else len(cleaned.split())


def script_features(text: object) -> dict[str, object]:
    value = normalize_unicode(text)
    return {
        "has_sinhala": has_sinhala(value),
        "has_latin": has_latin(value),
        "mixed_sinhala_latin": has_mixed_sinhala_latin(value),
        "emoji_only": is_emoji_only(value),
        "char_length": len(value),
        "word_count": word_count(value),
        "has_repeated_char_pattern": has_repeated_char_pattern(value),
    }


def clean_text(text: object, config: PreprocessConfig | None = None) -> str:
    config = config or PreprocessConfig()
    value = normalize_unicode(text)
    value = replace_urls(value, config.url_token)
    value = normalize_whitespace(value)
    return value


def preprocess_comment_text(text: object, config: PreprocessConfig | None = None) -> dict[str, object]:
    config = config or PreprocessConfig()
    original = normalize_unicode(text)
    cleaned = clean_text(original, config)
    features = script_features(cleaned)
    reasons: list[str] = []
    if not cleaned:
        reasons.append("empty_text")
    if features["char_length"] < config.very_short_threshold:
        reasons.append("very_short")
    if features["emoji_only"]:
        reasons.append("emoji_only")
    if features["has_repeated_char_pattern"]:
        reasons.append("repeated_character_pattern")
    if URL_RE.search(original):
        reasons.append("url_normalized")
    return {
        "original_text": original,
        "cleaned_text": cleaned,
        **features,
        "changed_by_preprocessing": original != cleaned,
        "review_reasons": ";".join(reasons),
        "exclude_from_modeling": "empty_text" in reasons,
    }


def preprocess_comments(
    comments: pd.DataFrame,
    text_column: str = "comment_text",
    config: PreprocessConfig | None = None,
) -> pd.DataFrame:
    config = config or PreprocessConfig()
    rows = [preprocess_comment_text(text, config) for text in comments[text_column]]
    features = pd.DataFrame(rows, index=comments.index)
    result = pd.concat(
        [
            comments[["comment_id", "channel_id", "video_id"]].reset_index(drop=True),
            features.reset_index(drop=True),
        ],
        axis=1,
    )
    duplicate_counts = result["cleaned_text"].value_counts()
    result["repeated_cleaned_text"] = result["cleaned_text"].map(duplicate_counts).fillna(0).astype(int) >= config.repeated_comment_threshold
    result.loc[result["repeated_cleaned_text"], "review_reasons"] = result.loc[
        result["repeated_cleaned_text"], "review_reasons"
    ].apply(lambda value: ";".join([x for x in [value, "repeated_cleaned_text"] if x]))
    return result


def preprocessing_summary(preprocessed: pd.DataFrame) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "metric": [
                "records_processed",
                "records_unchanged",
                "records_transformed",
                "records_flagged_for_review",
                "records_excluded",
                "sinhala_script",
                "latin_script",
                "mixed_sinhala_latin",
                "emoji_only",
            ],
            "value": [
                len(preprocessed),
                int((~preprocessed["changed_by_preprocessing"]).sum()),
                int(preprocessed["changed_by_preprocessing"].sum()),
                int((preprocessed["review_reasons"].fillna("") != "").sum()),
                int(preprocessed["exclude_from_modeling"].sum()),
                int(preprocessed["has_sinhala"].sum()),
                int(preprocessed["has_latin"].sum()),
                int(preprocessed["mixed_sinhala_latin"].sum()),
                int(preprocessed["emoji_only"].sum()),
            ],
        }
    )
