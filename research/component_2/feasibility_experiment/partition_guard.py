"""Frozen Experiment 2A.2 partition validation and training-data guard."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd


PARTITION_FINGERPRINT_ALGORITHM = "sha256-canonical-partition-v1"
PARTITION_ROLES = {
    "calibration_only",
    "development_pool",
    "held_out_evaluation",
}
DEVELOPMENT_ROLE = "development_pool"
PACKAGE_DIR = Path(__file__).resolve().parent
DEFAULT_PARTITION_MANIFEST = (
    PACKAGE_DIR / "outputs" / "experiment_2a2" / "comment_partition_manifest.csv"
)
DEFAULT_PARTITION_LOCK = PACKAGE_DIR / "experiment_2a2_partition_lock.json"
IDENTITY_COLUMNS = ("comment_id", "video_id", "dataset_role")


class PartitionIntegrityError(ValueError):
    """Raised when data crosses or changes the frozen experiment boundary."""


def _canonical_partition(frame: pd.DataFrame) -> pd.DataFrame:
    missing = sorted(set(IDENTITY_COLUMNS).difference(frame.columns))
    if missing:
        raise PartitionIntegrityError(f"Partition manifest is missing columns: {missing}")
    canonical = frame[list(IDENTITY_COLUMNS)].copy()
    for column in IDENTITY_COLUMNS:
        canonical[column] = canonical[column].astype("string").fillna("").str.strip()
        if canonical[column].eq("").any():
            raise PartitionIntegrityError(f"Partition manifest contains an empty {column}")
    if canonical["comment_id"].duplicated().any():
        raise PartitionIntegrityError("Partition manifest contains duplicate comment IDs")
    unexpected_roles = sorted(set(canonical["dataset_role"]).difference(PARTITION_ROLES))
    if unexpected_roles:
        raise PartitionIntegrityError(
            f"Partition manifest contains unexpected roles: {unexpected_roles}"
        )
    if set(canonical["dataset_role"]) != PARTITION_ROLES:
        raise PartitionIntegrityError("Partition manifest does not contain all three roles")
    if canonical.groupby("video_id")["dataset_role"].nunique().max() != 1:
        raise PartitionIntegrityError("A video ID crosses partition roles")
    return canonical.sort_values(list(IDENTITY_COLUMNS), kind="mergesort").reset_index(
        drop=True
    )


def manifest_fingerprint(frame: pd.DataFrame) -> str:
    """Return a row-order-independent fingerprint of partition identities."""

    canonical = _canonical_partition(frame)
    digest = hashlib.sha256()
    digest.update((PARTITION_FINGERPRINT_ALGORITHM + "\n").encode("ascii"))
    for row in canonical.to_dict("records"):
        encoded = json.dumps(
            row,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        digest.update(encoded.encode("utf-8"))
        digest.update(b"\n")
    return digest.hexdigest()


def load_partition_lock(path: str | Path = DEFAULT_PARTITION_LOCK) -> dict[str, Any]:
    lock_path = Path(path)
    if not lock_path.exists():
        raise FileNotFoundError(f"Frozen partition lock is missing: {lock_path}")
    try:
        payload = json.loads(lock_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise PartitionIntegrityError(f"Partition lock is invalid JSON: {lock_path}") from exc
    required = {
        "fingerprint_algorithm",
        "manifest_fingerprint",
        "comment_count",
        "video_count",
        "comment_role_counts",
        "video_role_counts",
        "split_seed",
    }
    missing = sorted(required.difference(payload))
    if missing:
        raise PartitionIntegrityError(f"Partition lock is missing fields: {missing}")
    if payload["fingerprint_algorithm"] != PARTITION_FINGERPRINT_ALGORITHM:
        raise PartitionIntegrityError("Partition lock uses an unsupported fingerprint algorithm")
    return payload


@dataclass(frozen=True)
class PartitionGuard:
    """Verified lookup boundary for future Component 2 model inputs."""

    manifest: pd.DataFrame
    fingerprint: str
    lock: dict[str, Any]

    @classmethod
    def load(
        cls,
        manifest_path: str | Path = DEFAULT_PARTITION_MANIFEST,
        lock_path: str | Path = DEFAULT_PARTITION_LOCK,
    ) -> "PartitionGuard":
        path = Path(manifest_path)
        if not path.exists():
            raise FileNotFoundError(f"Frozen partition manifest is missing: {path}")
        manifest = pd.read_csv(
            path,
            dtype={"comment_id": "string", "video_id": "string", "dataset_role": "string"},
        )
        return cls.verify(manifest, load_partition_lock(lock_path))

    @classmethod
    def verify(cls, manifest: pd.DataFrame, lock: dict[str, Any]) -> "PartitionGuard":
        canonical = _canonical_partition(manifest)
        fingerprint = manifest_fingerprint(canonical)
        expected = str(lock.get("manifest_fingerprint", ""))
        if fingerprint != expected:
            raise PartitionIntegrityError(
                "Partition manifest fingerprint differs from the frozen Experiment 2A.2 lock"
            )

        actual_comment_roles = {
            str(role): int(count)
            for role, count in canonical["dataset_role"].value_counts().items()
        }
        actual_video_roles = {
            str(role): int(count)
            for role, count in canonical.drop_duplicates("video_id")[
                "dataset_role"
            ].value_counts().items()
        }
        expected_comment_roles = {
            str(role): int(count)
            for role, count in lock["comment_role_counts"].items()
        }
        expected_video_roles = {
            str(role): int(count)
            for role, count in lock["video_role_counts"].items()
        }
        if len(canonical) != int(lock["comment_count"]):
            raise PartitionIntegrityError("Partition comment count differs from the lock")
        if canonical["video_id"].nunique() != int(lock["video_count"]):
            raise PartitionIntegrityError("Partition video count differs from the lock")
        if actual_comment_roles != expected_comment_roles:
            raise PartitionIntegrityError("Partition comment-role counts differ from the lock")
        if actual_video_roles != expected_video_roles:
            raise PartitionIntegrityError("Partition video-role counts differ from the lock")
        return cls(canonical, fingerprint, dict(lock))

    @property
    def development_comment_ids(self) -> frozenset[str]:
        values = self.manifest.loc[
            self.manifest["dataset_role"].eq(DEVELOPMENT_ROLE), "comment_id"
        ]
        return frozenset(values.astype(str))

    @property
    def development_video_ids(self) -> frozenset[str]:
        values = self.manifest.loc[
            self.manifest["dataset_role"].eq(DEVELOPMENT_ROLE), "video_id"
        ]
        return frozenset(values.astype(str))

    def validate_training_frame(self, frame: pd.DataFrame) -> pd.DataFrame:
        """Reject any non-development identifier before training or validation."""

        if "comment_id" not in frame.columns and "video_id" not in frame.columns:
            raise PartitionIntegrityError(
                "Training data must contain comment_id or video_id provenance"
            )
        checked = frame.copy()
        comment_lookup = self.manifest.set_index("comment_id")
        video_lookup = self.manifest.drop_duplicates("video_id").set_index("video_id")

        if "comment_id" in checked.columns:
            checked["comment_id"] = (
                checked["comment_id"].astype("string").fillna("").str.strip()
            )
            if checked["comment_id"].eq("").any():
                raise PartitionIntegrityError("Training data contains an empty comment ID")
            if checked["comment_id"].duplicated().any():
                raise PartitionIntegrityError("Training data contains duplicate comment IDs")
            unknown = sorted(set(checked["comment_id"]).difference(comment_lookup.index))
            if unknown:
                raise PartitionIntegrityError(
                    f"Training data contains {len(unknown)} comment IDs absent from the frozen manifest"
                )
            roles = checked["comment_id"].map(comment_lookup["dataset_role"])
            protected = roles.ne(DEVELOPMENT_ROLE)
            if protected.any():
                counts = roles[protected].value_counts().to_dict()
                raise PartitionIntegrityError(
                    f"Training data contains protected comments: {counts}"
                )

        if "video_id" in checked.columns:
            checked["video_id"] = (
                checked["video_id"].astype("string").fillna("").str.strip()
            )
            if checked["video_id"].eq("").any():
                raise PartitionIntegrityError("Training data contains an empty video ID")
            unknown_videos = sorted(set(checked["video_id"]).difference(video_lookup.index))
            if unknown_videos:
                raise PartitionIntegrityError(
                    f"Training data contains {len(unknown_videos)} video IDs absent from the frozen manifest"
                )
            video_roles = checked["video_id"].map(video_lookup["dataset_role"])
            protected_videos = video_roles.ne(DEVELOPMENT_ROLE)
            if protected_videos.any():
                counts = video_roles[protected_videos].value_counts().to_dict()
                raise PartitionIntegrityError(
                    f"Training data contains protected videos: {counts}"
                )

        if "comment_id" in checked.columns and "video_id" in checked.columns:
            expected_videos = checked["comment_id"].map(comment_lookup["video_id"])
            if not checked["video_id"].eq(expected_videos).all():
                raise PartitionIntegrityError(
                    "Training comment/video identifiers conflict with the frozen manifest"
                )
        return checked


def load_development_data(
    data_path: str | Path,
    *,
    manifest_path: str | Path = DEFAULT_PARTITION_MANIFEST,
    lock_path: str | Path = DEFAULT_PARTITION_LOCK,
) -> pd.DataFrame:
    """Load a local CSV only after enforcing the frozen development boundary."""

    path = Path(data_path)
    if not path.exists():
        raise FileNotFoundError(f"Training data is missing: {path}")
    frame = pd.read_csv(path, dtype={"comment_id": "string", "video_id": "string"})
    guard = PartitionGuard.load(manifest_path, lock_path)
    return guard.validate_training_frame(frame)
