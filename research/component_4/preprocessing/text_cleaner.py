"""Multilingual Text Cleaning and Normalization for Component 4.

Cleans YouTube titles, descriptions, and tags across Sinhala, English, and code-mixed
text, removing boilerplate and constructing weighted document representations for BERTopic.
"""

from __future__ import annotations

import html
import re
import unicodedata
from typing import Sequence

# Regex patterns for cleaning
_URL_PATTERN = re.compile(r"https?://\S+|www\.\S+", re.IGNORECASE)
_HTML_TAGS = re.compile(r"<[^>]+>")
_MULTIPLE_SPACES = re.compile(r"\s+")
_MULTIPLE_PUNCT = re.compile(r"([!?.,:;|\-_\~])\1+")

# Common social boilerplate patterns in Sri Lankan media YouTube descriptions
_BOILERPLATE_PATTERNS = [
    re.compile(r"(subscribe|like|share|comment|follow us|subscribe now|click the bell)[\s\S]*", re.IGNORECASE),
    re.compile(r"(connect with us|official website|download app|ringtone)[\s\S]*", re.IGNORECASE),
    re.compile(r"(stay tuned|all rights reserved|copyright)[\s\S]*", re.IGNORECASE),
]

# Unicode range for Sinhala characters
_SINHALA_CHAR_PATTERN = re.compile(r"[\u0D80-\u0DFF]")


def clean_text_field(text: str | None, max_len: int | None = None) -> str:
    """Normalize and clean a single text string."""
    if not text or not isinstance(text, str):
        return ""

    # 1. Unicode NFKC normalization
    text = unicodedata.normalize("NFKC", text)

    # 2. Unescape HTML entities (&amp; -> &, &quot; -> ", etc.)
    text = html.unescape(text)

    # 3. Strip HTML markup
    text = _HTML_TAGS.sub(" ", text)

    # 4. Remove URLs and links
    text = _URL_PATTERN.sub(" ", text)

    # 5. Compress repetitive punctuation (e.g., '!!!!' -> '!')
    text = _MULTIPLE_PUNCT.sub(r"\1", text)

    # 6. Normalize whitespace
    text = _MULTIPLE_SPACES.sub(" ", text).strip()

    if max_len and len(text) > max_len:
        text = text[:max_len].rsplit(" ", 1)[0]

    return text


def clean_description(desc: str | None, max_chars: int = 400) -> str:
    """Clean description while stripping recurring social links / boilerplate."""
    if not desc or not isinstance(desc, str):
        return ""

    desc = html.unescape(desc)
    desc = _URL_PATTERN.sub(" ", desc)

    # Strip boilerplate from the point it starts
    for pattern in _BOILERPLATE_PATTERNS:
        desc = pattern.sub(" ", desc)

    return clean_text_field(desc, max_len=max_chars)


def clean_tags(tags: Sequence[str] | None) -> str:
    """Clean and join video tags into a coherent keyword phrase."""
    if not tags:
        return ""
    if isinstance(tags, str):
        cleaned_tag_list = [clean_text_field(t) for t in tags.split(",") if t.strip()]
    elif isinstance(tags, (list, tuple)):
        cleaned_tag_list = [clean_text_field(str(t)) for t in tags if str(t).strip()]
    else:
        return ""

    # Filter out extremely generic tags like "shorts", "video", "tv", "derana", "sirasa"
    generic = {"shorts", "video", "videos", "derana", "sirasa", "tv", "channel", "official", "hd", "live"}
    filtered = [t for t in cleaned_tag_list if t.lower() not in generic and len(t) > 2]
    return " ".join(filtered[:15])


def detect_language_profile(text: str) -> str:
    """Classify text into 'sinhala', 'english', or 'code_mixed'."""
    if not text:
        return "unknown"
    has_sinhala = bool(_SINHALA_CHAR_PATTERN.search(text))
    # Simple check for ASCII letters
    has_english = bool(re.search(r"[a-zA-Z]", text))

    if has_sinhala and has_english:
        return "code_mixed"
    elif has_sinhala:
        return "sinhala"
    elif has_english:
        return "english"
    return "other"


def construct_video_document(
    title: str | None,
    description: str | None,
    tags: Sequence[str] | None,
    title_weight: int = 2,
) -> tuple[str, str]:
    """Construct a weighted semantic document for BERTopic from title, description, and tags.

    Returns:
        (document_text, language_profile)
    """
    cleaned_title = clean_text_field(title)
    cleaned_desc = clean_description(description)
    cleaned_tags = clean_tags(tags)

    # Title is the most informative signal: repeat it to give it higher term frequency weight
    parts: list[str] = []
    if cleaned_title:
        parts.extend([cleaned_title] * title_weight)
    if cleaned_tags:
        parts.append(cleaned_tags)
    if cleaned_desc:
        parts.append(cleaned_desc)

    combined_doc = " . ".join(parts).strip()
    lang = detect_language_profile(combined_doc)

    return combined_doc, lang


if __name__ == "__main__":
    sample_title = "Ada Derana 6.55 PM Sinhala News Bulletin | 17th October 2026"
    sample_desc = "Watch live bulletin! Subscribe to our channel: https://youtube.com/derana Follow us on FB"
    sample_tags = ["ada derana", "sinhala news", "breaking news", "news bulletin"]

    doc, lang = construct_video_document(sample_title, sample_desc, sample_tags)
    print("Language profile:", lang)
    print("Constructed Document:", doc)
