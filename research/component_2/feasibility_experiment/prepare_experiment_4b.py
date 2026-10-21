"""Experiment 4B preparation: contestant list, name spellings and a blind validation sheet.

Experiment 4A showed that topic clusters cannot tell support from criticism and
that video-to-topic assignment scatters performance videos across unrelated
topics. Experiment 4B adds a comment-understanding step: for each meaningful
comment, the targets it talks about (contestants, judges, voting, the show),
the stance towards each target and the comment's intent.

This module prepares the inputs a researcher must check before any model is run:

- the Season 2025 (Dream Star Season 12) contestant list, parsed from video
  titles of the form "Song (සිංහල) First Last | Dream Star Season 12 | ...";
- candidate Singlish and Sinhala-script spellings of each main contestant's
  name, discovered from the comments with their frequencies, for verification;
- a blind, shuffled 200-comment validation sheet (no model output) and a
  separate 40-comment prompt-development sample. The validation sheet is the
  test set for the extraction model and must not be used to tune its prompt.

Only training-pool comments are read (``ExpandedCorpusGuard``). Batch-1
comments are excluded from both samples.
"""

from __future__ import annotations

import argparse
import difflib
import hashlib
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

import pandas as pd

from .annotation_schema import PRIMARY_SIGNALS
from .build_expanded_corpus import DEFAULT_OUTPUT_DIR as CORPUS_DIR
from .build_expanded_corpus import ExpandedCorpusGuard, TRAINING_ROLES
from .prepare_experiment_3c import DEFAULT_OUTPUT_DIR as BATCH_DIR


SEED = 20261021
CHANNEL = "Dream Star"
SEASON_WINDOW = ("2025-04-01", "2026-02-01")
MAIN_MIN_VIDEOS = 10
VALIDATION_STRATA = {"contestant_mention": 120, "judges_or_voting": 40, "random": 40}
PROMPT_DEV_SIZE = 40
MAX_PER_VIDEO = 3
MAX_VARIANTS = 12
MIN_VARIANT_COUNT = 3
PACKAGE_DIR = Path(__file__).resolve().parent
DEFAULT_OUTPUT_DIR = PACKAGE_DIR / "outputs" / "experiment_4b"
MEANINGFUL_PATH = PACKAGE_DIR / "outputs" / "experiment_4a" / "dream_star" / "comment_topics.csv"

NON_PERSON_TITLES = frozenset({"Group Song", "Judjes Performance", "Judges Performance"})
_PERFORMER = re.compile(r"\)\s*([A-Z][a-zA-Z]+(?:\s+[A-Za-z][a-zA-Z]+)?)\s*(?:\||\bFt\b|\bft\b|&|\bVS\b)")
_LATIN_TOKEN = re.compile(r"[a-z]+")
_SINHALA_TOKEN = re.compile(r"[඀-෿‍]+")

# Sinhala-script stems used only to discover candidate spellings; every
# discovered spelling is verified by the researcher before it is used.
SINHALA_STEMS: dict[str, tuple[str, ...]] = {
    "Janani": ("ජනන", "ජානන"),
    "Anupama": ("අනුපම", "අනූපම"),
    "Brian": ("බ්‍රය", "බ්රය", "බ්‍රයි", "බ්‍රෙය"),
    "Nipuni": ("නිපුන", "නිපුණ"),
    "Pahanmi": ("පහන්ම", "පහම්"),
    "Thenuka": ("තේනුක", "තෙනුක"),
    "Shamitha": ("ශමිත", "ෂමිත", "ශාමිත"),
    "Dasith": ("දසිත", "දසීත", "දශිත"),
    "Thusitha": ("තුසිත", "තුෂිත"),
    "Ayesha": ("අයේෂ", "අයෙෂ", "ආයේෂ", "ආයෙෂ"),
    "Thanuri": ("තනුරි", "තනූරි", "තනුරී"),
    "Venuri": ("වෙනුරි", "වෙනූරි", "වේනුරි"),
}
# Known ambiguous spellings flagged for the researcher.
AMBIGUOUS = {"ජනනී": "also the Sinhala word for 'mother'", "bring": "English word", "jana": "common word stem"}

JUDGES_OR_VOTING = re.compile(
    r"judge|vote|voting|sms|marks|manapa|wild\s*card|eliminat|විනිශ්චය|ඡන්ද|මනාප|ලකුණු|වෝට්",
    re.IGNORECASE,
)

TARGET_CATEGORIES = ("OTHER_CONTESTANT", "JUDGES", "VOTING_OR_RESULTS", "HOST_OR_CREW", "CHANNEL_OR_SHOW", "OTHER_PERSON")
STANCES = ("SUPPORT", "CRITICISE", "NEUTRAL", "UNCLEAR")
CONTEXT_COLUMNS = [
    "review_id", "video_title", "video_published", "is_reply", "parent_comment_text",
    "comment_published", "comment_text", "video_url",
]
ANNOTATION_COLUMNS = [
    "target_1", "stance_1", "target_2", "stance_2", "target_3", "stance_3",
    "intent", "requested_action", "notes",
]


def _rank(value: str, namespace: str, seed: int = SEED) -> str:
    return hashlib.sha256(f"{seed}:{namespace}:{value}".encode("utf-8")).hexdigest()


def in_window(published: pd.Series, window: tuple[str, str] = SEASON_WINDOW) -> pd.Series:
    times = pd.to_datetime(published, utc=True, format="ISO8601")
    return times.ge(pd.Timestamp(window[0], tz="UTC")) & times.lt(pd.Timestamp(window[1], tz="UTC"))


def title_performers(title: str) -> list[str]:
    """Performer names in a title, title-cased; group songs and judge segments are not people."""

    names = [" ".join(part.title() for part in match.split()) for match in _PERFORMER.findall(title)]
    return [name for name in names if name not in NON_PERSON_TITLES]


def contestant_table(videos: pd.DataFrame, min_main: int = MAIN_MIN_VIDEOS) -> pd.DataFrame:
    rows = videos.assign(performer=videos["title"].map(title_performers)).explode("performer").dropna(subset=["performer"])
    # A lone first name ("Pahanmi") is merged into the full name that starts with it.
    full = sorted({n for n in rows["performer"] if " " in n}, key=len, reverse=True)
    rows["performer"] = rows["performer"].map(lambda n: n if " " in n else next((f for f in full if f.split()[0] == n), n))
    table = (
        rows.groupby("performer")
        .agg(videos=("video_id", "nunique"), first_upload=("published_at", "min"), last_upload=("published_at", "max"))
        .reset_index()
        .rename(columns={"performer": "full_name"})
    )
    table["first_name"] = table["full_name"].str.split().str[0]
    table["is_main"] = table["videos"].ge(min_main)
    table["first_upload"] = table["first_upload"].str[:10]
    table["last_upload"] = table["last_upload"].str[:10]
    return table.sort_values(["videos", "full_name"], ascending=[False, True]).reset_index(drop=True)[
        ["full_name", "first_name", "videos", "first_upload", "last_upload", "is_main"]
    ]


def _token_counts(texts: pd.Series, pattern: re.Pattern[str], lower: bool) -> Counter[str]:
    counts: Counter[str] = Counter()
    for text in texts:
        counts.update(set(pattern.findall(text.lower() if lower else text)))
    return counts


def latin_variants(name: str, counts: Counter[str], limit: int = MAX_VARIANTS, min_count: int = MIN_VARIANT_COUNT) -> list[tuple[str, int]]:
    key = name.lower()
    found = [
        (token, n) for token, n in counts.items()
        if n >= min_count and token[:3] == key[:3]
        and difflib.SequenceMatcher(None, token[: len(key) + 1], key).ratio() >= 0.75
    ]
    return sorted(found, key=lambda item: (-item[1], item[0]))[:limit]


def sinhala_variants(stems: tuple[str, ...], counts: Counter[str], limit: int = MAX_VARIANTS, min_count: int = MIN_VARIANT_COUNT) -> list[tuple[str, int]]:
    found = [(token, n) for token, n in counts.items() if n >= min_count and token.startswith(stems)]
    return sorted(found, key=lambda item: (-item[1], item[0]))[:limit]


def spelling_candidates(contestants: pd.DataFrame, comments: pd.DataFrame) -> pd.DataFrame:
    """Candidate spellings of each main contestant's first name, with comment counts and one example."""

    texts = comments["normalized_text"]
    latin = _token_counts(texts, _LATIN_TOKEN, lower=True)
    sinhala = _token_counts(texts, _SINHALA_TOKEN, lower=False)
    rows: list[dict[str, Any]] = []
    for name in contestants.loc[contestants["is_main"], "first_name"]:
        found = [("Singlish/English", t, n) for t, n in latin_variants(name, latin)]
        found += [("Sinhala", t, n) for t, n in sinhala_variants(SINHALA_STEMS.get(name, ()), sinhala)]
        for script, token, n in found:
            pattern = re.compile(rf"(?<![a-z]){re.escape(token)}(?![a-z])" if script != "Sinhala" else re.escape(token), re.IGNORECASE)
            example = next((t for t in texts if pattern.search(t)), "")
            starts_with_name = token.startswith(name.lower()) if script != "Sinhala" else True
            rows.append({
                "contestant": name, "script": script, "spelling": token, "comments_with_spelling": n,
                "suggestion": "CHECK" if token in AMBIGUOUS or not starts_with_name else "LIKELY",
                "flag": AMBIGUOUS.get(token, ""),
                "example_comment": re.sub(r"\s+", " ", example)[:120],
                "correct": "", "note": "",
            })
    return pd.DataFrame(rows)


def mention_mask(texts: pd.Series, spellings: list[str]) -> pd.Series:
    latin = {s for s in spellings if _LATIN_TOKEN.fullmatch(s)}
    sinhala = [s for s in spellings if s not in latin]

    def hit(text: str) -> bool:
        if latin.intersection(_LATIN_TOKEN.findall(text.lower())):
            return True
        return any(token.startswith(tuple(sinhala)) for token in _SINHALA_TOKEN.findall(text)) if sinhala else False

    return texts.map(hit)


def _take(frame: pd.DataFrame, n: int, namespace: str, used_videos: Counter[str]) -> pd.DataFrame:
    ranked = frame.assign(rank=frame["comment_id"].map(lambda v: _rank(v, namespace))).sort_values("rank")
    picked = []
    for row in ranked.itertuples(index=False):
        if used_videos[row.video_id] >= MAX_PER_VIDEO:
            continue
        used_videos[row.video_id] += 1
        picked.append(row.comment_id)
        if len(picked) == n:
            break
    return frame.loc[frame["comment_id"].isin(picked)]


def draw_samples(
    meaningful: pd.DataFrame,
    spellings: list[str],
    excluded: set[str],
    strata: dict[str, int] = VALIDATION_STRATA,
    prompt_dev_size: int = PROMPT_DEV_SIZE,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return (blind validation rows with stratum, prompt-development rows); the two never overlap."""

    pool = meaningful.loc[~meaningful["comment_id"].isin(excluded)].copy()
    pool["mentions_contestant"] = mention_mask(pool["normalized_text"], spellings)
    pool["judges_or_voting"] = pool["normalized_text"].str.contains(JUDGES_OR_VOTING)
    prompt_dev = _take(pool, prompt_dev_size, "prompt_dev", Counter())
    pool = pool.loc[~pool["comment_id"].isin(prompt_dev["comment_id"])]

    used: Counter[str] = Counter()
    parts = []
    conditions = {
        "contestant_mention": pool["mentions_contestant"],
        "judges_or_voting": pool["judges_or_voting"] & ~pool["mentions_contestant"],
        "random": pd.Series(True, index=pool.index),
    }
    taken: set[str] = set()
    for stratum, n in strata.items():
        eligible = pool.loc[conditions[stratum] & ~pool["comment_id"].isin(taken)]
        part = _take(eligible, n, stratum, used).assign(stratum=stratum)
        taken.update(part["comment_id"])
        parts.append(part)
    return pd.concat(parts, ignore_index=True), prompt_dev.reset_index(drop=True)


def build_sheet_rows(sample: pd.DataFrame, comments: pd.DataFrame, videos: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    text_by_id = comments.set_index("comment_id")["raw_comment_text"]
    video_by_id = videos.set_index("video_id")
    rows = sample.assign(order=sample["comment_id"].map(lambda v: _rank(v, "order"))).sort_values("order").reset_index(drop=True)
    rows["review_id"] = [f"V4B-{i + 1:03d}" for i in range(len(rows))]
    rows["video_title"] = rows["video_id"].map(video_by_id["title"]).fillna("")
    rows["video_published"] = rows["video_id"].map(video_by_id["published_at"]).fillna("").str[:10]
    rows["parent_comment_text"] = rows["parent_comment_id"].map(text_by_id).fillna("")
    rows.loc[rows["is_reply"].str.lower().eq("true") & rows["parent_comment_text"].eq(""), "parent_comment_text"] = (
        "(reply; parent comment not collected)"
    )
    rows["comment_published"] = rows["published_at"].str[:10]
    rows["comment_text"] = rows["raw_comment_text"]
    rows["video_url"] = "https://www.youtube.com/watch?v=" + rows["video_id"]
    for column in ANNOTATION_COLUMNS:
        rows[column] = ""
    key = rows[["review_id", "comment_id", "video_id", "stratum"]].copy()
    return rows[CONTEXT_COLUMNS + ANNOTATION_COLUMNS], key


def guide_lines(main_names: list[str]) -> list[str]:
    return [
        "Experiment 4B blind validation sheet: who is the comment about, and what does it say about them?",
        "",
        "Label every row on your own judgement. Do not use AI tools, and do not look at any model output. Rows are shuffled; you can stop and resume anywhere.",
        "These labels are the test set for the comment-understanding model, so they must be independent of it.",
        "",
        "1. target_1 … target_3: who or what the comment gives a view about or asks about (most important first; leave extra slots blank).",
        f"   Main contestants: {', '.join(main_names)}.",
        "   OTHER_CONTESTANT: any other contestant. JUDGES: the judges or their marks and decisions.",
        "   VOTING_OR_RESULTS: SMS or online voting, eliminations, results, wild card. HOST_OR_CREW: presenters, band, production.",
        "   CHANNEL_OR_SHOW: Derana, Dream Star as a programme, uploads or schedule. OTHER_PERSON: anyone else (original singer, family member).",
        "   If the comment praises or criticises the performance without naming anyone, and the video features one contestant, that contestant is the target.",
        "   On group-song or live-episode videos, name a contestant only if the comment identifies them.",
        "   A comment with no target (for example 'super show') can use CHANNEL_OR_SHOW, or leave target_1 blank if nothing fits.",
        "",
        "2. stance_1 … stance_3 (one per filled target):",
        "   SUPPORT: praise, encouragement, wants them to win or stay, defends them.",
        "   CRITICISE: negative judgement, says they did not deserve something, complains about them.",
        "   NEUTRAL: mentions them without a positive or negative view (for example a question).",
        "   UNCLEAR: sarcasm or missing context makes the stance impossible to tell.",
        "   Example: 'manapa pahanmita denna tebba, anupamata dunne aparade' → Pahanmi SUPPORT; JUDGES CRITICISE; Anupama CRITICISE (says she did not deserve the marks).",
        "",
        "3. intent: the same eight primary signals as batch 1 (EXPLICIT_CONTENT_REQUEST, CONTENT_CHANGE_PREFERENCE, INFORMATION_NEED,",
        "   CONTENT_QUALITY_FEEDBACK, TOPICAL_INTEREST_OR_DISCUSSION, ORDINARY_REACTION, SPAM_OR_IRRELEVANT, UNCLEAR).",
        "   Support for a contestant on its own is ORDINARY_REACTION.",
        "",
        "4. requested_action: only for EXPLICIT_CONTENT_REQUEST or CONTENT_CHANGE_PREFERENCE, a few words on what is asked for",
        "   (for example 'upload the full episode', 'give Pahanmi another chance').",
        "5. notes: anything ambiguous.",
        "",
        "Keep review_id and comment_text unchanged. A blank target_1 and intent means 'not yet labelled'.",
    ]


def _style_header(sheet: Any, headers: list[str], label_columns: set[str], widths: dict[str, int]) -> None:
    from openpyxl.styles import Alignment, Font, PatternFill

    header_fill = PatternFill("solid", fgColor="DDE7F5")
    label_fill = PatternFill("solid", fgColor="FFF4CC")
    for index, header in enumerate(headers, start=1):
        cell = sheet.cell(row=1, column=index)
        sheet.column_dimensions[cell.column_letter].width = widths.get(header, 14)
        cell.font = Font(bold=True)
        cell.fill = label_fill if header in label_columns else header_fill
    for row in sheet.iter_rows(min_row=2):
        for cell in row:
            cell.alignment = Alignment(wrap_text=True, vertical="top")
    sheet.freeze_panes = "B2"


def _list_validation(sheet: Any, column: int, last_row: int, source: str) -> None:
    from openpyxl.worksheet.datavalidation import DataValidation

    letter = sheet.cell(row=1, column=column).column_letter
    validation = DataValidation(type="list", formula1=source, allow_blank=True)
    validation.error = "Choose a value from the list."
    sheet.add_data_validation(validation)
    validation.add(f"{letter}2:{letter}{last_row}")


def write_validation_workbook(rows: pd.DataFrame, main_names: list[str], path: Path) -> None:
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font

    wb = Workbook()
    guide = wb.active
    guide.title = "Guide"
    for line in guide_lines(main_names):
        guide.append([line])
    guide.column_dimensions["A"].width = 150
    for cell in guide["A"]:
        cell.alignment = Alignment(wrap_text=True, vertical="top")
    guide["A1"].font = Font(bold=True, size=14)

    lists = wb.create_sheet("Lists")
    targets = [*main_names, *TARGET_CATEGORIES]
    for index, values in enumerate((targets, list(STANCES), list(PRIMARY_SIGNALS)), start=1):
        for row, value in enumerate(values, start=1):
            lists.cell(row=row, column=index, value=value)
    ranges = {
        "target": f"Lists!$A$1:$A${len(targets)}",
        "stance": f"Lists!$B$1:$B${len(STANCES)}",
        "intent": f"Lists!$C$1:$C${len(PRIMARY_SIGNALS)}",
    }
    lists.sheet_state = "hidden"

    sheet = wb.create_sheet("Annotate", 1)
    headers = CONTEXT_COLUMNS + ANNOTATION_COLUMNS
    sheet.append(headers)
    for record in rows[headers].itertuples(index=False):
        sheet.append(list(record))
    widths = {
        "review_id": 10, "video_title": 38, "video_published": 12, "is_reply": 8, "parent_comment_text": 30,
        "comment_published": 12, "comment_text": 60, "video_url": 18, "requested_action": 28, "notes": 30,
        **{f"target_{i}": 18 for i in (1, 2, 3)}, **{f"stance_{i}": 12 for i in (1, 2, 3)}, "intent": 30,
    }
    _style_header(sheet, headers, set(ANNOTATION_COLUMNS), widths)
    last = len(rows) + 1
    for header in headers:
        kind = "target" if header.startswith("target_") else "stance" if header.startswith("stance_") else header
        if kind in ranges:
            _list_validation(sheet, headers.index(header) + 1, last, ranges[kind])
    wb.active = 1
    path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(path)


CONTESTANT_GUIDE = [
    "Experiment 4B: Season 2025 (Dream Star Season 12) contestants and name spellings, to verify",
    "",
    "Contestants sheet: names were read from video titles ('Song (සිංහල) First Last | Dream Star Season 12'). Check that each is a",
    "   contestant (not a guest artist), and fill 'correct' with YES or NO. 'is_main' marks contestants with at least 10 videos;",
    "   the others are grouped as OTHER_CONTESTANT in the validation sheet.",
    "",
    "Spellings sheet: spellings of each main contestant's first name found in the comments, with how many comments use them.",
    "   Fill 'correct' with YES if the spelling refers to that contestant in these comments, NO otherwise.",
    "   'LIKELY' and 'CHECK' are only hints: CHECK marks spellings that do not start with the name or are also ordinary words.",
    "   Add missing spellings or nicknames (for example a pet name fans use) as new rows with correct = YES.",
    "",
    "Other people sheet: add the judges' and presenters' names (with their Sinhala spellings, if you know them), so the model can",
    "   recognise comments about them.",
    "",
    "Verified spellings are used to (1) give the model the names in all scripts, (2) count simple name mentions as the baseline,",
    "   and (3) report how many mentions are written in Sinhala script.",
]


def write_contestant_workbook(contestants: pd.DataFrame, spellings: pd.DataFrame, path: Path) -> None:
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font

    wb = Workbook()
    guide = wb.active
    guide.title = "Guide"
    for line in CONTESTANT_GUIDE:
        guide.append([line])
    guide.column_dimensions["A"].width = 140
    for cell in guide["A"]:
        cell.alignment = Alignment(wrap_text=True, vertical="top")
    guide["A1"].font = Font(bold=True, size=14)

    for title, frame, labels, widths in (
        ("Contestants", contestants.assign(correct="", note=""), {"correct", "note"},
         {"full_name": 28, "first_name": 14, "videos": 8, "first_upload": 12, "last_upload": 12, "is_main": 8, "note": 30}),
        ("Spellings", spellings, {"correct", "note"},
         {"contestant": 12, "script": 16, "spelling": 22, "comments_with_spelling": 12, "suggestion": 11, "flag": 24,
          "example_comment": 70, "correct": 9, "note": 28}),
        ("Other people", pd.DataFrame({"name": [""] * 8, "role": [""] * 8, "sinhala_spelling": [""] * 8, "singlish_spellings": [""] * 8}),
         {"name", "role", "sinhala_spelling", "singlish_spellings"}, {"name": 28, "role": 16, "sinhala_spelling": 24, "singlish_spellings": 30}),
    ):
        sheet = wb.create_sheet(title)
        headers = list(frame.columns)
        sheet.append(headers)
        for record in frame.itertuples(index=False):
            sheet.append([bool(v) if isinstance(v, bool) else v for v in record])
        _style_header(sheet, headers, labels, widths)
        if "correct" in headers:
            _list_validation(sheet, headers.index("correct") + 1, len(frame) + 1, '"YES,NO"')
    path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(path)


def load_inputs(corpus_dir: Path = CORPUS_DIR, meaningful_path: Path = MEANINGFUL_PATH) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Return (all comments, Season 2025 training comments, Season 2025 meaningful comments, Season 2025 videos)."""

    comments = pd.read_csv(corpus_dir / "expanded_comments.csv", dtype=str, keep_default_na=False)
    season = comments.loc[
        comments["channel_name"].eq(CHANNEL) & comments["dataset_role"].isin(TRAINING_ROLES)
        & comments["cleaned_text"].str.strip().ne("")
    ]
    season = season.loc[in_window(season["published_at"])].reset_index(drop=True)
    ExpandedCorpusGuard.load(corpus_dir / "comment_partition_manifest_v2.csv").validate_training_frame(season[["comment_id"]])
    meaningful_ids = set(pd.read_csv(meaningful_path, dtype=str, usecols=["comment_id"])["comment_id"])
    meaningful = season.loc[season["comment_id"].isin(meaningful_ids)].reset_index(drop=True)
    videos = pd.read_csv(corpus_dir / "expanded_videos.csv", dtype=str, keep_default_na=False)
    videos = videos.loc[videos["channel_name"].eq(CHANNEL) & in_window(videos["published_at"])].reset_index(drop=True)
    return comments, season, meaningful, videos


def prepare(output_dir: Path = DEFAULT_OUTPUT_DIR) -> dict[str, Any]:
    comments, season, meaningful, videos = load_inputs()
    contestants = contestant_table(videos)
    spellings = spelling_candidates(contestants, season)
    main_names = contestants.loc[contestants["is_main"], "first_name"].tolist()
    batch1 = set(pd.read_csv(BATCH_DIR / "annotation_batch1_504.csv", dtype=str, usecols=["comment_id"])["comment_id"])
    likely = spellings.loc[spellings["suggestion"].eq("LIKELY"), "spelling"].tolist()
    sample, prompt_dev = draw_samples(meaningful, likely, batch1)
    rows, key = build_sheet_rows(sample, comments, videos)

    output_dir.mkdir(parents=True, exist_ok=True)
    write_contestant_workbook(contestants, spellings, output_dir / "contestants_season_2025.xlsx")
    write_validation_workbook(rows, main_names, output_dir / "validation_blind_200.xlsx")
    key.to_csv(output_dir / "validation_private_key.csv", index=False, encoding="utf-8")
    prompt_dev[["comment_id", "video_id", "published_at", "raw_comment_text"]].to_csv(
        output_dir / "prompt_dev_40.csv", index=False, encoding="utf-8"
    )
    summary = {
        "channel": CHANNEL, "season_window": list(SEASON_WINDOW),
        "season_training_comments": int(len(season)), "season_meaningful_comments": int(len(meaningful)),
        "season_videos": int(len(videos)),
        "videos_with_named_performer": int(videos["title"].map(lambda t: bool(title_performers(t))).sum()),
        "contestants": int(len(contestants)), "main_contestants": main_names,
        "spelling_candidates": int(len(spellings)),
        "validation_strata": key["stratum"].value_counts().to_dict(),
        "validation_videos": int(key["video_id"].nunique()),
        "prompt_dev_rows": int(len(prompt_dev)),
        "excluded_batch1_comments": len(batch1),
        "seed": SEED,
    }
    (output_dir / "prepare_summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return summary


def main() -> int:
    argparse.ArgumentParser(description="Prepare Experiment 4B contestant list, spellings and blind validation sheet.").parse_args()
    print(json.dumps(prepare(), indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
