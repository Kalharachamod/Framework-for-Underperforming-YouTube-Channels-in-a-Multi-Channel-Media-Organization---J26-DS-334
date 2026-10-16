"""Transparent multilingual candidate-demand screening rules.

The detector is intentionally high-recall and exploratory. Its output is a
candidate queue, never a human label or a production filtering decision.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from typing import Any

import pandas as pd

from research.component_2.src.text_processing import normalize_unicode, script_features


SIGNAL_CLASSES = (
    "EXPLICIT_CONTENT_REQUEST",
    "CONTENT_CHANGE_PREFERENCE",
    "INFORMATION_NEED",
    "CONTENT_QUALITY_FEEDBACK",
    "TOPICAL_INTEREST_OR_DISCUSSION",
    "ORDINARY_REACTION",
    "SPAM_OR_IRRELEVANT",
    "UNCLEAR",
)

REQUEST_PATTERNS = (
    r"\b(?:please|pls|can you|could you|would you|make|do|create|cover|upload|show|bring|give us|need|want)\b",
    r"\b(?:another|more|new|next|full|part\s*2|episode|interview|story|update)\b",
    r"\b(?:thawath|tawath|me gana|meka gena|video ekak|karanna(?:ko)?|danna(?:ko)?|denna(?:ko)?|puluwanda|one|onai)\b",
    r"(?:තව\s*(?:වීඩියෝ|video|විස්තර)|වීඩියෝ\s*එකක්\s*(?:කරන්න|දාන්න)|කරන්නකෝ|දාන්නකෝ|දෙන්නකෝ|පුළුවන්ද)",
)

CHANGE_PATTERNS = (
    r"\b(?:subtitle|subtitles|caption|translate|translation|sinhala|english|tamil|short|long|full|live|interview|part\s*2|format)\b",
    r"\b(?:quality|audio|sound|volume|mic|camera|clear|too\s+(?:short|long))\b",
    r"\b(?:සිංහල|ඉංග්‍රීසි|දෙමළ|උපසිරැසි|ශබ්ද|හඬ|ගුණාත්මක)\b",
    r"\b(?:sinhala|english|tamil|subtitles?)\s*(?:walin|version|karanna|danna|denna)\b",
)

INFORMATION_PATTERNS = (
    r"\b(?:explain|explanation|details?|more\s+detail|what\s+happened|why|how|when|where|who|update|follow[- ]?up|clarify|answer|information|tell us)\b",
    r"\b(?:visthara|wisthara|pahadili|update ekak|mona wage|ai|aida|kohomada|kawda|mokakda|kiyanna|danaganna)\b",
    r"(?:විස්තර|පැහැදිලි|තොරතුරු|ඇයි|කොහොමද|කවදා|කවුද|මොකක්ද|කියන්න|දැනගන්න)",
)

QUESTION_PATTERNS = (
    r"\?",
    r"\b(?:what|why|how|when|where|who|is|are|can|will|did|does)\b",
    r"\b(?:ai|aida|kohomada|kawda|mokakda|puluwanda|kiyannada)\b",
    r"(?:ඇයි|කොහොමද|කවදා|කවුද|මොකක්ද|පුළුවන්ද)",
)

QUALITY_PATTERNS = (
    r"\b(?:bad|poor|improve|fix|better|quality|audio|sound|volume|mic|camera|clear|blurry|slow|fast|too\s+(?:short|long))\b",
    r"\b(?:quality\s+madi|sound\s+madi|clear\s+naha|audio\s+adui)\b",
    r"(?:ගුණාත්මක|ශබ්දය|හඬ|පැහැදිලි|වැරදියි|වැඩිදියුණු|නිවැරදි)",
)

SPAM_PATTERNS = (
    r"\b(?:earn|make)\s+(?:rs\.?|\$|usd)?\s*[\d,]+\s*(?:daily|per\s+day|a\s+day)\b",
    r"\b(?:investment|forex|crypto|loan|profit|money[- ]making|double\s+your\s+money|free\s+gift)\b",
    r"\b(?:contact|dm|whatsapp|telegram)\s+(?:me|us)\b",
    r"\b(?:visit|check|subscribe\s+to)\s+(?:my|our)\s+(?:page|channel|profile|link)\b",
    r"\b(?:buy|sell)\s+(?:followers|views|likes|subscribers)\b",
    r"\b(?:promo|promotion|advertisement|giveaway)\b",
    r"(?:ආයෝජන|මුදල්|ලාභ|තෑගි|අමතන්න)\s*(?:අවස්ථා|කරන්න|දෙන්න)?",
)

REACTION_PATTERNS = (
    r"\b(?:good|great|nice|love|wow|amazing|excellent|thanks|thank you|patta|supiri|maru|ela|jaya|congratulations)\b",
    r"(?:හොඳයි|නියමයි|සුපිරි|ස්තුතියි|ජය|ආදරෙයි)",
)

FORMAT_PATTERNS = (
    (r"\b(?:subtitle|subtitles|caption|translate|translation|sinhala|english|tamil)\b", "language_or_accessibility"),
    (r"\b(?:part\s*2|episode|full\s+(?:video|episode)|live|interview|short|long)\b", "format_or_length"),
    (r"\b(?:audio|sound|volume|mic|camera|quality)\b", "production_quality"),
    (r"(?:උපසිරැසි|ශබ්ද|හඬ|ගුණාත්මක)", "language_or_production_quality"),
)

STOPWORDS = {
    "about", "after", "again", "another", "comment", "content", "from", "give", "have", "more",
    "please", "that", "this", "video", "what", "when", "where", "which", "with", "would", "you",
}


def _matches(text: str, patterns: Iterable[str]) -> list[str]:
    matches: list[str] = []
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE | re.UNICODE)
        if match:
            value = match.group(0).strip()
            if value and value not in matches:
                matches.append(value)
    return matches


def _has_signal(text: str, patterns: Iterable[str]) -> bool:
    return bool(_matches(text, patterns))


def _first_evidence(text: str, patterns: Iterable[str]) -> str | None:
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE | re.UNICODE)
        if match:
            return match.group(0).strip()
    return None


def _topic_from_request(text: str) -> str | None:
    patterns = (
        r"\b(?:about|on|regarding|gana|gena)\s+([^.!?\n]{2,100})",
        r"(?:ගැන|පිළිබඳව)\s*([^.!?\n]{2,100})",
    )
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE | re.UNICODE)
        if match:
            value = match.group(1).strip(" ,:;-\t")
            if value and value.casefold() not in STOPWORDS:
                return value
    return None


def _requested_format(text: str) -> str | None:
    for pattern, value in FORMAT_PATTERNS:
        if re.search(pattern, text, flags=re.IGNORECASE | re.UNICODE):
            return value
    return None


def _language_or_script(text: str, row: dict[str, Any]) -> str:
    if row.get("script_category"):
        return str(row["script_category"])
    features = script_features(text)
    if features["emoji_only"]:
        return "emoji_only"
    if features["mixed_sinhala_latin"]:
        return "mixed_sinhala_latin"
    if features["has_sinhala"]:
        return "sinhala_script"
    if features["has_latin"]:
        return "latin_script"
    return "other_or_symbolic"


def _context_overlap(text: str, title: str, description: str) -> bool:
    text_terms = {
        term.casefold()
        for term in re.findall(r"[A-Za-z\u0D80-\u0DFF]{4,}", text)
        if term.casefold() not in STOPWORDS
    }
    context_terms = {
        term.casefold()
        for term in re.findall(r"[A-Za-z\u0D80-\u0DFF]{4,}", f"{title} {description}")
        if term.casefold() not in STOPWORDS
    }
    return bool(text_terms.intersection(context_terms))


def detect_comment(row: dict[str, Any]) -> dict[str, Any]:
    """Return an auditable heuristic record for one comment.

    The fields deliberately describe evidence and uncertainty. They are not
    compatible with the portal's human labels and must not be copied into it.
    """

    original_text = normalize_unicode(row.get("original_text", row.get("comment_text", "")))
    cleaned_text = normalize_unicode(row.get("cleaned_text", original_text))
    analysis_text = cleaned_text or original_text
    title = normalize_unicode(row.get("video_title", row.get("title", "")))
    description = normalize_unicode(row.get("video_description", row.get("description", "")))
    language_or_script = _language_or_script(analysis_text, row)
    if not analysis_text:
        return {
            "primary_signal": "UNCLEAR",
            "secondary_signals": [],
            "candidate_for_content_demand": False,
            "actionable_content_demand": None,
            "requested_action": None,
            "requested_topic": None,
            "requested_format": None,
            "evidence_span": None,
            "language_or_script": language_or_script,
            "uncertainty_reason": "empty_or_missing_comment_text",
            "baseline_score": 0,
        }

    spam_matches = _matches(original_text, SPAM_PATTERNS)
    request_matches = _matches(original_text, REQUEST_PATTERNS)
    change_matches = _matches(original_text, CHANGE_PATTERNS)
    info_matches = _matches(original_text, INFORMATION_PATTERNS)
    question_matches = _matches(original_text, QUESTION_PATTERNS)
    quality_matches = _matches(original_text, QUALITY_PATTERNS)
    reaction_matches = _matches(original_text, REACTION_PATTERNS)
    context_match = _context_overlap(analysis_text, title, description)

    if spam_matches:
        primary_signal = "SPAM_OR_IRRELEVANT"
        candidate = False
        action = None
        uncertainty = "heuristic_promotional_or_solicitation_signal"
        evidence = spam_matches[0]
    elif change_matches and request_matches:
        primary_signal = "CONTENT_CHANGE_PREFERENCE"
        candidate = True
        action = "change_format_or_presentation"
        uncertainty = None
        evidence = _first_evidence(original_text, (*CHANGE_PATTERNS, *REQUEST_PATTERNS))
    elif request_matches and info_matches:
        primary_signal = "INFORMATION_NEED"
        candidate = True
        action = "provide_explanation_or_update"
        uncertainty = None
        evidence = _first_evidence(original_text, (*INFORMATION_PATTERNS, *REQUEST_PATTERNS))
    elif request_matches:
        primary_signal = "EXPLICIT_CONTENT_REQUEST"
        candidate = True
        action = "create_or_extend_content"
        uncertainty = None
        evidence = request_matches[0]
    elif quality_matches and (request_matches or any(word in original_text.casefold() for word in ("bad", "poor", "madi", "naha", "වැරදි"))):
        primary_signal = "CONTENT_QUALITY_FEEDBACK"
        candidate = True
        action = "improve_content_quality"
        uncertainty = None
        evidence = quality_matches[0]
    elif info_matches and question_matches and ("update" in analysis_text.casefold() or "more" in analysis_text.casefold() or context_match):
        primary_signal = "INFORMATION_NEED"
        candidate = True
        action = "provide_explanation_or_update"
        uncertainty = "question_or_topic_request_requires_context"
        evidence = info_matches[0]
    elif question_matches or context_match:
        primary_signal = "TOPICAL_INTEREST_OR_DISCUSSION"
        candidate = False
        action = None
        uncertainty = "current-topic-question_or_discussion_not_future_content_request"
        evidence = question_matches[0] if question_matches else None
    elif reaction_matches or language_or_script == "emoji_only" or len(analysis_text.split()) <= 3:
        primary_signal = "ORDINARY_REACTION"
        candidate = False
        action = None
        uncertainty = None
        evidence = reaction_matches[0] if reaction_matches else None
    else:
        primary_signal = "UNCLEAR"
        candidate = False
        action = None
        uncertainty = "no_high_precision_actionable_signal"
        evidence = None

    secondary: list[str] = []
    if change_matches and primary_signal != "CONTENT_CHANGE_PREFERENCE":
        secondary.append("CONTENT_CHANGE_PREFERENCE")
    if info_matches and primary_signal != "INFORMATION_NEED":
        secondary.append("INFORMATION_NEED")
    if quality_matches and primary_signal != "CONTENT_QUALITY_FEEDBACK":
        secondary.append("CONTENT_QUALITY_FEEDBACK")
    if question_matches and primary_signal != "TOPICAL_INTEREST_OR_DISCUSSION":
        secondary.append("QUESTION_PATTERN")
    if reaction_matches and primary_signal != "ORDINARY_REACTION":
        secondary.append("ORDINARY_REACTION")
    if context_match:
        secondary.append("VIDEO_CONTEXT_OVERLAP")

    return {
        "primary_signal": primary_signal,
        "secondary_signals": ";".join(dict.fromkeys(secondary)),
        "candidate_for_content_demand": bool(candidate),
        "actionable_content_demand": True if candidate else None,
        "requested_action": action,
        "requested_topic": _topic_from_request(original_text) if candidate else None,
        "requested_format": _requested_format(original_text) if candidate else None,
        "evidence_span": evidence,
        "language_or_script": language_or_script,
        "uncertainty_reason": uncertainty,
        "baseline_score": int(bool(request_matches)) * 3 + int(bool(change_matches)) * 2 + int(bool(info_matches)) * 2 + int(bool(quality_matches)) + int(bool(context_match)),
    }


def detect_frame(frame: pd.DataFrame) -> pd.DataFrame:
    records = [detect_comment(row) for row in frame.to_dict("records")]
    return pd.DataFrame(records, index=frame.index)
