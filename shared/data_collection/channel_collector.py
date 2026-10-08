"""YouTube channel collector: configured channel ids -> YouTube API -> validation -> Supabase.

    python -m shared.data_collection.channel_collector                 # all configured groups
    python -m shared.data_collection.channel_collector --group owned   # one group
    python -m shared.data_collection.channel_collector --dry-run       # fetch + validate, store nothing

Uses ``channels.list`` only (1 quota unit per 50 channels; never ``search.list``).
Low-level retries and API errors stay in ``youtube_client``; this module decides
what a failure means for the collection run and reports per channel.

Channel data is the foundation only: it says nothing about audience movement,
subscriptions, identity or causality.
"""

from __future__ import annotations

import sys
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from pydantic import ValidationError

from shared.data_collection import youtube_client as yc
from shared.schemas import Channel

BATCH_SIZE = 50  # channels.list accepts up to 50 ids per request
CHANNEL_PARTS = "snippet,statistics"  # exactly what the Channel schema needs

# Errors after which further requests would fail too: stop the run.
FATAL_ERRORS = (yc.QuotaExceededError, yc.InvalidAPIKeyError, yc.UnauthorizedError, yc.MissingAPIKeyError)

Store = Callable[[list[Channel]], Any]  # returns a repository.WriteSummary (or None)


@dataclass(frozen=True)
class ChannelFailure:
    channel_id: str
    reason: str    # invalid_id | not_found | validation_error | quota_exceeded | auth_error | api_error | storage_error
    message: str


@dataclass
class ChannelCollectionResult:
    requested: list[str]
    collected: list[str] = field(default_factory=list)   # fetched and validated
    inserted: list[str] = field(default_factory=list)
    updated: list[str] = field(default_factory=list)     # = changed + refreshed
    changed: list[str] = field(default_factory=list)     # a value (e.g. subscribers) differs
    refreshed: list[str] = field(default_factory=list)   # same values, newer collected_at
    unchanged: list[str] = field(default_factory=list)   # not written (e.g. older than stored data)
    failed: list[ChannelFailure] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)     # not attempted (run stopped early)
    quota_used: int = 0
    stored: bool = True
    started_at: str = ""
    finished_at: str = ""

    @property
    def ok(self) -> bool:
        return not self.failed and not self.skipped

    def summary(self) -> str:
        lines = [
            f"Channel collection {self.started_at} -> {self.finished_at}"
            + ("" if self.stored else "  (dry run: nothing stored)"),
            f"  requested {len(self.requested)} | collected {len(self.collected)} | "
            f"inserted {len(self.inserted)} | updated {len(self.updated)} "
            f"(values changed {len(self.changed)}, refreshed only {len(self.refreshed)}) | "
            f"unchanged {len(self.unchanged)} | "
            f"failed {len(self.failed)} | skipped {len(self.skipped)} | quota used {self.quota_used}",
        ]
        lines += [f"  FAILED  {f.channel_id}: {f.reason} - {f.message}" for f in self.failed]
        if self.skipped:
            lines.append(f"  SKIPPED {len(self.skipped)} channel(s) after a fatal error")
        return "\n".join(lines)


def collect_channels(
    channel_ids: Sequence[str],
    client: yc.YouTubeClient,
    store: Store | None,
    *,
    clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
) -> ChannelCollectionResult:
    """Fetch, validate and store channels. ``store=None`` is a dry run."""
    ids = list(dict.fromkeys(c.strip() for c in channel_ids if isinstance(c, str)))
    if not ids:
        raise ValueError("no channel ids to collect; check config/research_channels.json")

    result = ChannelCollectionResult(requested=ids, stored=store is not None, started_at=_iso(clock()))
    quota_before = client.quota_used
    valid_ids = []
    for cid in ids:
        if yc.is_valid_id(cid):
            valid_ids.append(cid)
        else:
            result.failed.append(ChannelFailure(cid, "invalid_id", "not a valid YouTube channel id"))

    batches = [valid_ids[i:i + BATCH_SIZE] for i in range(0, len(valid_ids), BATCH_SIZE)]
    for n, batch in enumerate(batches):
        try:
            response = client.channels_list(part=CHANNEL_PARTS, id=batch)
        except FATAL_ERRORS as exc:
            reason = "quota_exceeded" if isinstance(exc, yc.QuotaExceededError) else "auth_error"
            result.failed += [ChannelFailure(cid, reason, _short(exc)) for cid in batch]
            result.skipped += [cid for later in batches[n + 1:] for cid in later]
            break
        except yc.YouTubeAPIError as exc:  # transient errors already retried by the client
            result.failed += [ChannelFailure(cid, "api_error", _short(exc)) for cid in batch]
            continue

        collected_at = clock()
        channels = _parse(batch, response.items, collected_at, result)
        result.collected += [c.channel_id for c in channels]
        if channels and store is not None:
            _store(channels, store, result)

    result.quota_used = client.quota_used - quota_before
    result.finished_at = _iso(clock())
    return result


def to_channel_record(item: dict[str, Any], collected_at: datetime) -> dict[str, Any]:
    """Map a channels.list resource to the Channel schema fields (public data only)."""
    snippet = item.get("snippet") or {}
    stats = item.get("statistics") or {}
    hidden = bool(stats.get("hiddenSubscriberCount"))
    return {
        "channel_id": item.get("id"),
        "channel_name": snippet.get("title"),
        "description": snippet.get("description"),
        "published_at": snippet.get("publishedAt"),
        "subscriber_count": None if hidden else stats.get("subscriberCount"),
        "view_count": stats.get("viewCount"),
        "video_count": stats.get("videoCount"),
        "collected_at": collected_at,
    }


def _parse(batch: list[str], items: list[dict[str, Any]], collected_at: datetime,
           result: ChannelCollectionResult) -> list[Channel]:
    wanted = set(batch)
    by_id = {}
    for item in items:
        cid = item.get("id") if isinstance(item, dict) else None
        if cid in wanted:
            by_id[cid] = item
    channels = []
    for cid in batch:
        if cid not in by_id:
            result.failed.append(ChannelFailure(cid, "not_found", "channel not returned by the API "
                                                "(deleted, terminated or wrong id)"))
            continue
        try:
            channels.append(Channel.model_validate(to_channel_record(by_id[cid], collected_at)))
        except ValidationError as exc:
            fields = sorted({".".join(str(p) for p in e["loc"]) for e in exc.errors()})
            result.failed.append(ChannelFailure(cid, "validation_error", f"invalid field(s): {', '.join(fields)}"))
    return channels


def _store(channels: list[Channel], store: Store, result: ChannelCollectionResult) -> None:
    try:
        summary = store(channels)
    except Exception as exc:  # database errors: keep going, report per channel
        result.failed += [ChannelFailure(c.channel_id, "storage_error", _short(exc)) for c in channels]
        failed = {c.channel_id for c in channels}
        result.collected = [cid for cid in result.collected if cid not in failed]
        return
    if summary is None:
        return
    result.inserted += list(summary.inserted_ids)
    result.updated += list(summary.updated_ids)
    result.changed += list(summary.changed_ids)
    result.refreshed += list(summary.refreshed_ids)
    done = set(summary.inserted_ids) | set(summary.updated_ids)
    result.unchanged += [c.channel_id for c in channels if c.channel_id not in done]


def supabase_store(conn) -> Store:
    """Store function writing to Supabase; commits after each batch."""
    from shared.database import repository

    def store(channels: list[Channel]):
        try:
            summary = repository.upsert_channels(conn, channels)
            conn.commit()
            return summary
        except Exception:
            conn.rollback()
            raise

    return store


def _short(exc: BaseException) -> str:
    text = str(exc).splitlines()[0] if str(exc) else type(exc).__name__
    return text[:300]


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


# --- command line ---------------------------------------------------------------------

def main(argv: Iterable[str] | None = None) -> int:
    import argparse

    from shared.data_collection.channel_config import ChannelConfigError, load_channels
    from shared.database.connection import DatabaseConfigError, DatabaseConnectionError, connect

    parser = argparse.ArgumentParser(prog="channel_collector", description="Collect configured YouTube channels.")
    parser.add_argument("--group", action="append", help="configured group to collect (repeatable)")
    parser.add_argument("--dry-run", action="store_true", help="fetch and validate only; store nothing")
    args = parser.parse_args(list(argv) if argv is not None else None)

    try:
        configured = load_channels(args.group)
        client = yc.YouTubeClient()
        groups = sorted({c.group for c in configured})
        print(f"Collecting {len(configured)} channel(s) from group(s): {', '.join(groups)}")
        if args.dry_run:
            result = collect_channels([c.channel_id for c in configured], client, None)
        else:
            with connect() as conn:
                result = collect_channels([c.channel_id for c in configured], client, supabase_store(conn))
    except (ChannelConfigError, yc.MissingAPIKeyError, DatabaseConfigError, DatabaseConnectionError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2
    print(result.summary())
    return 0 if result.ok else 1


if __name__ == "__main__":
    sys.exit(main())
