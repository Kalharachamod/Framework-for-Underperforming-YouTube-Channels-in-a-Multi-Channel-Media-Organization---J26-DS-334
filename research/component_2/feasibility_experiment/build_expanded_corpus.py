"""Experiment 3A: expanded Derana corpus with a frozen v2 partition.

The frozen Experiment 2A.2 pilot partition (v1) is carried forward unchanged.
Newly collected comments are routed by video so that nothing new can reach
the protected v1 held-out or calibration videos, and a fresh video-grouped
held-out slice is reserved for channels and videos the pilot never covered.

The v1 manifest and lock are read and verified, never rewritten. The v2
identity is frozen separately in ``experiment_3a_corpus_lock.json``.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
from typing import Any

import pandas as pd

from research.component_2.src.text_processing import clean_text, script_features

from .annotation_schema import normalized_text, raw_text_sha256
from .audit import sha256
from .partition_guard import (
    DEFAULT_PARTITION_LOCK,
    DEFAULT_PARTITION_MANIFEST,
    PartitionGuard,
    PartitionIntegrityError,
)


EXPERIMENT_3A_SEED = 20261020
EXPANDED_HELDOUT_FRACTION = 0.15
LOCK_VERSION = "component2.experiment-3a.corpus-lock.v2"
FINGERPRINT_ALGORITHM = "sha256-canonical-partition-v2-expanded"

# v1 roles are copied verbatim for the 2,000 pilot comments.
V1_ROLES = ("calibration_only", "development_pool", "held_out_evaluation")
# New comments on protected v1 videos are quarantined, never used or reviewed.
HELDOUT_QUARANTINE = "heldout_quarantine"
CALIBRATION_QUARANTINE = "calibration_quarantine"
EXPANDED_DEVELOPMENT = "expanded_development_pool"
EXPANDED_HELDOUT = "expanded_heldout_evaluation"
V2_ROLES = V1_ROLES + (
    HELDOUT_QUARANTINE,
    CALIBRATION_QUARANTINE,
    EXPANDED_DEVELOPMENT,
    EXPANDED_HELDOUT,
)
TRAINING_ROLES = frozenset({"development_pool", EXPANDED_DEVELOPMENT})

PACKAGE_DIR = Path(__file__).resolve().parent
REPO_ROOT = PACKAGE_DIR.parents[2]
DEFAULT_PILOT_COMMENTS = REPO_ROOT / "data/raw/component_2/component2_pilot_comments.csv"
DEFAULT_PILOT_VIDEOS = REPO_ROOT / "data/raw/component_2/component2_pilot_videos.csv"
DEFAULT_EXPANSION_DIR = REPO_ROOT / "data/raw/component_2/expansion_20261019"
DEFAULT_OUTPUT_DIR = PACKAGE_DIR / "outputs" / "experiment_3a"
DEFAULT_V2_LOCK = PACKAGE_DIR / "experiment_3a_corpus_lock.json"

COMMENT_COLUMNS = [
    "comment_id",
    "video_id",
    "channel_id",
    "channel_name",
    "parent_comment_id",
    "is_reply",
    "published_at",
    "like_count",
    "author_hash",
    "source",
    "raw_comment_text",
    "raw_comment_text_sha256",
    "normalized_text",
    "cleaned_text",
    "has_sinhala",
    "has_latin",
    "has_mixed_sinhala_latin",
    "is_emoji_only",
]


def manifest_fingerprint(frame: pd.DataFrame) -> str:
    """Row-order-independent fingerprint of v2 (comment, video, role) identities."""

    canonical = frame[["comment_id", "video_id", "dataset_role"]].astype("string").fillna("")
    for column in canonical.columns:
        canonical[column] = canonical[column].str.strip()
        if canonical[column].eq("").any():
            raise PartitionIntegrityError(f"Expanded manifest contains an empty {column}")
    if canonical["comment_id"].duplicated().any():
        raise PartitionIntegrityError("Expanded manifest contains duplicate comment IDs")
    unknown = set(canonical["dataset_role"]).difference(V2_ROLES)
    if unknown:
        raise PartitionIntegrityError(f"Expanded manifest contains unknown roles: {sorted(unknown)}")
    canonical = canonical.sort_values(list(canonical.columns), kind="mergesort")
    digest = hashlib.sha256((FINGERPRINT_ALGORITHM + "\n").encode("ascii"))
    for row in canonical.itertuples(index=False):
        digest.update(json.dumps(row._asdict(), ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8"))
        digest.update(b"\n")
    return digest.hexdigest()


def _stable_rank(value: str, seed: int) -> str:
    return hashlib.sha256(f"{seed}:experiment-3a:{value}".encode("utf-8")).hexdigest()


def _read_jsonl(path: Path) -> pd.DataFrame:
    with path.open(encoding="utf-8") as handle:
        rows = [json.loads(line) for line in handle if line.strip()]
    return pd.DataFrame(rows)


def load_pilot_comments(path: Path) -> pd.DataFrame:
    pilot = pd.read_csv(path, dtype={"comment_id": "string", "video_id": "string"}, keep_default_na=False)
    return pd.DataFrame(
        {
            "comment_id": pilot["comment_id"],
            "video_id": pilot["video_id"],
            "channel_id": pilot["channel_id"],
            "channel_name": pilot["channel_name"],
            "parent_comment_id": pilot["parent_comment_id"].replace("", pd.NA),
            "is_reply": pilot["parent_comment_id"].ne(""),
            "published_at": pilot["published_at"],
            "like_count": pd.to_numeric(pilot["like_count"], errors="coerce"),
            "author_hash": pd.NA,
            "source": "pilot_v1",
            "raw_comment_text": pilot["comment_text"],
        }
    )


def load_expansion_comments(path: Path) -> pd.DataFrame:
    raw = _read_jsonl(path)
    return pd.DataFrame(
        {
            "comment_id": raw["comment_id"].astype("string"),
            "video_id": raw["video_id"].astype("string"),
            "channel_id": raw["channel_id"],
            "channel_name": raw["channel_name"],
            "parent_comment_id": raw["parent_id"],
            "is_reply": raw["is_reply"].astype(bool),
            "published_at": raw["published_at"],
            "like_count": pd.to_numeric(raw["like_count"], errors="coerce"),
            "author_hash": raw["author_hash"],
            "source": "expansion_20261019",
            "raw_comment_text": raw["text"].fillna(""),
        }
    )


def merge_comments(pilot: pd.DataFrame, expansion: pd.DataFrame) -> pd.DataFrame:
    """Union both sources; pilot text wins so frozen v1 evidence stays byte-identical."""

    expansion = expansion.drop_duplicates("comment_id", keep="last")
    author = expansion.set_index("comment_id")["author_hash"]
    pilot = pilot.copy()
    pilot["author_hash"] = pilot["comment_id"].map(author)
    pilot["also_in_expansion"] = pilot["comment_id"].isin(expansion["comment_id"])
    new = expansion.loc[~expansion["comment_id"].isin(pilot["comment_id"])].copy()
    new["also_in_expansion"] = True
    merged = pd.concat([pilot, new], ignore_index=True)
    if merged["comment_id"].duplicated().any():
        raise PartitionIntegrityError("Merged corpus still contains duplicate comment IDs")
    return merged


def add_text_fields(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame.copy()
    out["raw_comment_text_sha256"] = out["raw_comment_text"].map(raw_text_sha256)
    out["normalized_text"] = out["raw_comment_text"].map(normalized_text)
    out["cleaned_text"] = out["raw_comment_text"].map(clean_text)
    features = pd.DataFrame(out["raw_comment_text"].map(script_features).tolist(), index=out.index)
    for column, source in (
        ("has_sinhala", "has_sinhala"),
        ("has_latin", "has_latin"),
        ("has_mixed_sinhala_latin", "mixed_sinhala_latin"),
        ("is_emoji_only", "emoji_only"),
    ):
        out[column] = features[source].astype(bool)
    return out


def assign_v2_roles(
    comments: pd.DataFrame,
    v1_manifest: pd.DataFrame,
    videos: pd.DataFrame,
    *,
    seed: int = EXPERIMENT_3A_SEED,
    heldout_fraction: float = EXPANDED_HELDOUT_FRACTION,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Route every comment by video; return (comment roles, video selection)."""

    v1_comment_role = v1_manifest.set_index("comment_id")["dataset_role"]
    v1_video_role = v1_manifest.drop_duplicates("video_id").set_index("video_id")["dataset_role"]
    roles = comments[["comment_id", "video_id", "channel_name"]].copy()
    roles["dataset_role"] = roles["comment_id"].map(v1_comment_role)

    unrouted = roles["dataset_role"].isna()
    video_v1 = roles["video_id"].map(v1_video_role)
    roles.loc[unrouted & video_v1.eq("held_out_evaluation"), "dataset_role"] = HELDOUT_QUARANTINE
    roles.loc[unrouted & video_v1.eq("calibration_only"), "dataset_role"] = CALIBRATION_QUARANTINE
    roles.loc[unrouted & video_v1.eq("development_pool"), "dataset_role"] = EXPANDED_DEVELOPMENT

    # Videos never seen by the pilot: video-grouped held-out sample per
    # channel x publication-quarter stratum, ranked by a seeded hash only.
    new_video_ids = roles.loc[roles["dataset_role"].isna(), "video_id"].drop_duplicates()
    video_info = videos.drop_duplicates("video_id").set_index("video_id")
    fallback_channel = roles.drop_duplicates("video_id").set_index("video_id")["channel_name"]
    selection = pd.DataFrame({"video_id": new_video_ids.to_numpy()})
    selection["channel_name"] = selection["video_id"].map(video_info["channel_name"]).fillna(
        selection["video_id"].map(fallback_channel)
    )
    published = pd.to_datetime(selection["video_id"].map(video_info["published_at"]), utc=True, errors="coerce", format="ISO8601")
    quarter = published.dt.tz_convert(None).dt.to_period("Q").astype(str)
    selection["stratum"] = selection["channel_name"].astype(str) + "|" + quarter
    selection["rank_key"] = selection["video_id"].map(lambda value: _stable_rank(value, seed))
    selection = selection.sort_values(["stratum", "rank_key"]).reset_index(drop=True)
    selection["stratum_size"] = selection.groupby("stratum")["video_id"].transform("size")
    selection["stratum_position"] = selection.groupby("stratum").cumcount()
    take = selection["stratum_size"].map(lambda n: math.floor(n * heldout_fraction + 0.5) if n >= 4 else 0)
    selection["selected_heldout"] = selection["stratum_position"] < take
    selection["inclusion_probability"] = (take / selection["stratum_size"]).round(6)
    heldout_videos = set(selection.loc[selection["selected_heldout"], "video_id"])

    remaining = roles["dataset_role"].isna()
    roles.loc[remaining & roles["video_id"].isin(heldout_videos), "dataset_role"] = EXPANDED_HELDOUT
    roles.loc[roles["dataset_role"].isna(), "dataset_role"] = EXPANDED_DEVELOPMENT

    _check_v2_invariants(roles, v1_manifest)
    return roles[["comment_id", "video_id", "dataset_role"]], selection.drop(columns=["stratum_position"])


def _check_v2_invariants(roles: pd.DataFrame, v1_manifest: pd.DataFrame) -> None:
    unknown = set(roles["dataset_role"]).difference(V2_ROLES)
    if unknown:
        raise PartitionIntegrityError(f"Unknown v2 roles: {sorted(unknown)}")
    v1 = v1_manifest.set_index("comment_id")["dataset_role"]
    carried = roles.loc[roles["comment_id"].isin(v1.index)]
    if len(carried) != len(v1) or not carried["dataset_role"].eq(carried["comment_id"].map(v1)).all():
        raise PartitionIntegrityError("v1 pilot roles were not carried forward unchanged")
    protected = {
        "held_out_evaluation": {"held_out_evaluation", HELDOUT_QUARANTINE},
        "calibration_only": {"calibration_only", CALIBRATION_QUARANTINE},
    }
    v1_video = v1_manifest.drop_duplicates("video_id").set_index("video_id")["dataset_role"]
    for v1_role, allowed in protected.items():
        videos = set(v1_video[v1_video.eq(v1_role)].index)
        leaked = roles.loc[roles["video_id"].isin(videos) & ~roles["dataset_role"].isin(allowed)]
        if not leaked.empty:
            raise PartitionIntegrityError(f"{len(leaked)} comments on {v1_role} videos escaped quarantine")
    video_roles = roles.assign(
        group=roles["dataset_role"].map(
            lambda r: "eval" if r in {EXPANDED_HELDOUT} else ("train" if r in TRAINING_ROLES else "other")
        )
    )
    crossing = video_roles.loc[video_roles["group"].isin({"eval", "train"})].groupby("video_id")["group"].nunique()
    if crossing.gt(1).any():
        raise PartitionIntegrityError("A video crosses the expanded training and held-out partitions")


def role_counts(manifest: pd.DataFrame) -> tuple[dict[str, int], dict[str, int]]:
    comments = {str(k): int(v) for k, v in manifest["dataset_role"].value_counts().sort_index().items()}
    videos = {
        str(k): int(v)
        for k, v in manifest.drop_duplicates(["video_id", "dataset_role"])["dataset_role"].value_counts().sort_index().items()
    }
    return comments, videos


def load_v2_lock(path: str | Path = DEFAULT_V2_LOCK) -> dict[str, Any]:
    lock_path = Path(path)
    if not lock_path.exists():
        raise FileNotFoundError(f"Experiment 3A corpus lock is missing: {lock_path}")
    payload = json.loads(lock_path.read_text(encoding="utf-8"))
    if payload.get("lock_version") != LOCK_VERSION:
        raise PartitionIntegrityError("Unsupported Experiment 3A lock version")
    return payload


def verify_v2_manifest(manifest: pd.DataFrame, lock: dict[str, Any]) -> str:
    fingerprint = manifest_fingerprint(manifest)
    if fingerprint != lock["manifest_fingerprint"]:
        raise PartitionIntegrityError("Expanded manifest fingerprint differs from the frozen v2 lock")
    comments, videos = role_counts(manifest)
    if comments != lock["comment_role_counts"] or videos != lock["video_role_counts"]:
        raise PartitionIntegrityError("Expanded manifest role counts differ from the frozen v2 lock")
    return fingerprint


class ExpandedCorpusGuard:
    """Training boundary for the expanded corpus (development roles only)."""

    def __init__(self, manifest: pd.DataFrame, lock: dict[str, Any]):
        self.fingerprint = verify_v2_manifest(manifest, lock)
        self.manifest = manifest
        self.lock = lock
        self._role = manifest.set_index("comment_id")["dataset_role"]

    @classmethod
    def load(cls, manifest_path: str | Path, lock_path: str | Path = DEFAULT_V2_LOCK) -> "ExpandedCorpusGuard":
        manifest = pd.read_csv(manifest_path, dtype="string")
        return cls(manifest, load_v2_lock(lock_path))

    def validate_training_frame(self, frame: pd.DataFrame) -> pd.DataFrame:
        if "comment_id" not in frame.columns:
            raise PartitionIntegrityError("Training data must contain comment_id provenance")
        ids = frame["comment_id"].astype("string")
        if ids.duplicated().any():
            raise PartitionIntegrityError("Training data contains duplicate comment IDs")
        roles = ids.map(self._role)
        if roles.isna().any():
            raise PartitionIntegrityError(f"{int(roles.isna().sum())} comment IDs are absent from the v2 manifest")
        protected = ~roles.isin(TRAINING_ROLES)
        if protected.any():
            raise PartitionIntegrityError(
                f"Training data contains protected comments: {roles[protected].value_counts().to_dict()}"
            )
        return frame


def build_videos(pilot_videos_path: Path, expansion_videos_path: Path) -> pd.DataFrame:
    expansion = _read_jsonl(expansion_videos_path)
    expansion["source"] = "expansion_20261019"
    pilot = pd.read_csv(pilot_videos_path, dtype={"video_id": "string"}, keep_default_na=False)
    pilot["source"] = "pilot_v1"
    pilot["tags"] = pilot["tags"].astype(str)
    expansion["tags"] = expansion["tags"].map(lambda t: json.dumps(t, ensure_ascii=False))
    pilot_only = pilot.loc[~pilot["video_id"].isin(expansion["video_id"])]
    videos = pd.concat([expansion, pilot_only], ignore_index=True, sort=False)
    return videos.drop_duplicates("video_id", keep="first").reset_index(drop=True)


def build(
    *,
    pilot_comments: Path = DEFAULT_PILOT_COMMENTS,
    pilot_videos: Path = DEFAULT_PILOT_VIDEOS,
    expansion_dir: Path = DEFAULT_EXPANSION_DIR,
    v1_manifest_path: Path = DEFAULT_PARTITION_MANIFEST,
    v1_lock_path: Path = DEFAULT_PARTITION_LOCK,
    v2_lock_path: Path = DEFAULT_V2_LOCK,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    seed: int = EXPERIMENT_3A_SEED,
    freeze: bool = False,
) -> dict[str, Any]:
    v1_guard = PartitionGuard.load(v1_manifest_path, v1_lock_path)
    v1_manifest = v1_guard.manifest

    comments = merge_comments(
        load_pilot_comments(pilot_comments),
        load_expansion_comments(expansion_dir / "comments.jsonl"),
    )
    videos = build_videos(pilot_videos, expansion_dir / "videos.jsonl")
    roles, selection = assign_v2_roles(comments, v1_manifest, videos, seed=seed)
    comments = add_text_fields(comments.merge(roles[["comment_id", "dataset_role"]], on="comment_id"))

    manifest = roles.sort_values("comment_id").reset_index(drop=True)
    fingerprint = manifest_fingerprint(manifest)
    comment_roles, video_roles = role_counts(manifest)
    inputs = {
        "pilot_comments": sha256(pilot_comments),
        "pilot_videos": sha256(pilot_videos),
        "expansion_comments": sha256(expansion_dir / "comments.jsonl"),
        "expansion_videos": sha256(expansion_dir / "videos.jsonl"),
    }
    lock = {
        "lock_version": LOCK_VERSION,
        "fingerprint_algorithm": FINGERPRINT_ALGORITHM,
        "manifest_fingerprint": fingerprint,
        "v1_manifest_fingerprint": v1_guard.fingerprint,
        "split_seed": seed,
        "expanded_heldout_fraction": EXPANDED_HELDOUT_FRACTION,
        "comment_count": int(len(manifest)),
        "video_count": int(manifest["video_id"].nunique()),
        "comment_role_counts": comment_roles,
        "video_role_counts": video_roles,
        "training_roles": sorted(TRAINING_ROLES),
        "input_sha256": inputs,
    }

    if v2_lock_path.exists():
        frozen = load_v2_lock(v2_lock_path)
        if frozen["manifest_fingerprint"] != fingerprint or frozen["input_sha256"] != inputs:
            raise PartitionIntegrityError(
                "Rebuilt corpus differs from the frozen v2 lock; a new lock version is a research decision"
            )
    elif freeze:
        v2_lock_path.write_text(json.dumps(lock, indent=2) + "\n", encoding="utf-8")

    output_dir.mkdir(parents=True, exist_ok=True)
    comments[COMMENT_COLUMNS + ["dataset_role", "also_in_expansion"]].to_csv(
        output_dir / "expanded_comments.csv", index=False, encoding="utf-8"
    )
    manifest.to_csv(output_dir / "comment_partition_manifest_v2.csv", index=False, encoding="utf-8")
    selection.to_csv(output_dir / "expanded_heldout_video_selection.csv", index=False, encoding="utf-8")
    videos.to_csv(output_dir / "expanded_videos.csv", index=False, encoding="utf-8")

    summary = summarize(comments, videos, lock)
    (output_dir / "experiment_3a_summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return summary


def summarize(comments: pd.DataFrame, videos: pd.DataFrame, lock: dict[str, Any]) -> dict[str, Any]:
    month = pd.to_datetime(comments["published_at"], utc=True, errors="coerce", format="ISO8601").dt.strftime("%Y-%m")
    by_channel_role = comments.groupby(["channel_name", "dataset_role"]).size().unstack(fill_value=0)
    by_channel_month = comments.assign(month=month).groupby(["channel_name", "month"]).size().unstack(fill_value=0)
    video_month = pd.to_datetime(videos["published_at"], utc=True, errors="coerce", format="ISO8601").dt.strftime("%Y-%m")
    supply = videos.assign(month=video_month).groupby(["channel_name", "month"]).size().unstack(fill_value=0)
    return {
        "lock": lock,
        "comments_total": int(len(comments)),
        "comments_unique_authors": int(comments["author_hash"].nunique()),
        "comments_replies": int(comments["is_reply"].sum()),
        "pilot_comments_recollected": int(comments.loc[comments["source"].eq("pilot_v1"), "also_in_expansion"].sum()),
        "script": {
            "sinhala": int(comments["has_sinhala"].sum()),
            "latin": int(comments["has_latin"].sum()),
            "mixed": int(comments["has_mixed_sinhala_latin"].sum()),
            "emoji_only": int(comments["is_emoji_only"].sum()),
        },
        "comments_by_channel_role": by_channel_role.to_dict(orient="index"),
        "comments_by_channel_month": by_channel_month.to_dict(orient="index"),
        "videos_by_channel_month": supply.to_dict(orient="index"),
    }


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build the Experiment 3A expanded corpus and v2 partition.")
    parser.add_argument("--expansion-dir", type=Path, default=DEFAULT_EXPANSION_DIR)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--freeze", action="store_true", help="Write the v2 lock if none exists yet.")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    summary = build(expansion_dir=args.expansion_dir, output_dir=args.output_dir, freeze=args.freeze)
    lock = summary["lock"]
    print(json.dumps({k: lock[k] for k in ("manifest_fingerprint", "comment_count", "video_count", "comment_role_counts")}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
