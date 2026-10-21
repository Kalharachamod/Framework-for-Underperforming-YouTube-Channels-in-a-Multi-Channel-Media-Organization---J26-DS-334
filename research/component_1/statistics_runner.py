"""Unscheduled, fixture-first C1 statistics runner. No database writer integration."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from shared.data_collection.channel_collector import to_channel_record
from shared.data_collection.video_collector import to_video_record
from shared.data_collection.youtube_api_client import YouTubeClient, HttpResult
from shared.schemas import Channel, Video
from shared.data_collection import youtube_api_client as yc

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MANIFEST = ROOT / "config/cohorts/component_1_derana_v0.1.0.proposed.json"
STATE = ROOT / "research/component_1/results/statistics_runner"


class PrerequisiteError(ValueError):
    """Static, credential-free operator guidance."""


class BudgetStop(RuntimeError):
    pass


class PhaseLimit(RuntimeError):
    """Local phase limit; must not stop other collection phases."""


FATAL = (BudgetStop, yc.InvalidAPIKeyError, yc.MissingAPIKeyError,
         yc.UnauthorizedError, yc.QuotaExceededError)


class LiveClient(YouTubeClient):
    """Budget applies before every transport attempt, including network failures."""

    def __init__(self, budget, *, authorized=False, transport=None, retries=2, sleep=None):
        if not authorized:
            raise PrerequisiteError("Explicit --live authorization is required.")
        if not isinstance(budget, int) or isinstance(budget, bool) or budget < 1:
            raise PrerequisiteError("Live mode requires a positive --api-budget.")
        if not 0 <= retries <= 5:
            raise PrerequisiteError("Retries must be between 0 and 5.")
        self.attempted_requests = 0
        self.budget = budget
        self.stopped = False
        self.stop_reason = None
        self.discovery_remaining = None
        self.refresh_ceiling = None
        self.endpoint_counts = {name: {"attempts": 0, "initial_attempts": 0,
            "retry_attempts": 0, "successful_requests": 0} for name in ("channels", "videos", "playlistItems")}
        self._call_attempts = 0
        underlying = transport or yc.urllib_transport

        def bounded(url, params, timeout):
            if self.stopped or self.attempted_requests >= self.budget:
                self.stopped = True
                self.stop_reason = "api_attempt_budget_reached"
                raise BudgetStop("API attempt budget reached")
            resource = url.rsplit("/", 1)[-1]
            if resource == "playlistItems" and self.discovery_remaining is not None:
                if self.discovery_remaining <= 0:
                    raise PhaseLimit("discovery_attempt_budget_reached")
                self.discovery_remaining -= 1
            if self.refresh_ceiling is not None and self.attempted_requests >= self.refresh_ceiling:
                raise PhaseLimit("refresh_retry_reserve_reached")
            stats = self.endpoint_counts[resource]
            stats["attempts"] += 1
            stats["retry_attempts" if self._call_attempts else "initial_attempts"] += 1
            self._call_attempts += 1
            self.attempted_requests += 1
            return underlying(url, params, timeout)

        kwargs = {"sleep": sleep} if sleep is not None else {}
        super().__init__(timeout=20, retry=yc.RetryPolicy(max_retries=retries,
                         backoff_seconds=1, max_backoff_seconds=8), transport=bounded, **kwargs)

    def _list(self, resource, params):
        self._call_attempts = 0
        response = super()._list(resource, params)
        self.endpoint_counts[resource]["successful_requests"] += 1
        return response


def bootstrap_inventory(manifest, *, connect=None):
    """Only the dedicated URL; no shared privileged connection fallback or commits."""
    import psycopg
    url = os.getenv("COMPONENT1_DB_URL", "").strip()
    if not url:
        raise PrerequisiteError("Read-only bootstrap requires COMPONENT1_DB_URL.")
    conn = None
    try:
        conn = (connect or psycopg.connect)(url, autocommit=True, sslmode="require",
            connect_timeout=10, prepare_threshold=None,
            options="-c default_transaction_read_only=on -c statement_timeout=30000 -c lock_timeout=5000 -c idle_in_transaction_session_timeout=60000")
        with conn.cursor() as cur:
            cur.execute("BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY")
            cur.execute("SELECT current_user, current_setting('transaction_read_only')")
            if cur.fetchone() != ("component1_readonly", "on"):
                raise PrerequisiteError("Bootstrap requires component1_readonly and a read-only transaction.")
            cur.execute("SELECT video_id, channel_id FROM research.videos WHERE channel_id = ANY(%s) ORDER BY video_id",
                        ([r["channel_id"] for r in manifest["channels"]],))
            rows = [{"video_id": vid, "channel_id": cid} for vid, cid in cur.fetchall()]
            return inventory_revision(manifest, [], rows, utc_now())
    except PrerequisiteError:
        raise
    except Exception:
        raise PrerequisiteError("Read-only bootstrap failed; verify connection and schema locally. Details suppressed.") from None
    finally:
        if conn is not None:
            try:
                conn.rollback()
            finally:
                conn.close()


def preflight(manifest, state, seed=None, *, budget=None, bootstrap=False, no_persist=False, discovery_budget=20, max_pages=10):
    if seed is not None and not no_persist:
        revisions = sorted(Path(state).glob("inventory_*.json"))
        previous = []
        if revisions:
            prior = json.loads(revisions[-1].read_text(encoding="utf-8"))
            if prior["manifest_hash"] != digest(manifest):
                raise PrerequisiteError("Inventory manifest changed; explicit migration required.")
            previous = prior["videos"]
        seed = inventory_revision(manifest, previous, seed, utc_now())
    videos = None if seed is None else len(seed)
    estimate = None if videos is None else (len(manifest["channels"]) + 49) // 50 + len(manifest["channels"]) + (videos + 49) // 50
    summary = {"cohort_version": manifest["version"],
        "approval_status": manifest.get("approval", {}).get("status", "unknown"),
        "channels": len(manifest["channels"]), "selected_videos": videos,
        "estimated_minimum_requests": estimate, "api_attempt_budget": budget,
        "inventory_reserved_initial_attempts": None if videos is None else (videos + 49) // 50,
        "request_order": "existing inventory, channels, bounded discovery, new candidates",
        "discovery_attempt_budget": discovery_budget, "max_pages_per_channel": max_pages,
        "output_root": None if no_persist else str(state),
        "outputs": "none; memory only" if no_persist else "inventory_*.json; run_*/batch_*.json, payload_*.json, report.json",
        "preflight": "read-only database bootstrap" if bootstrap else "offline; no connections",
        "database_writes": "disabled", "scheduling": "disabled",
        "manual_authorization": "separate from cohort approval; no approval changes",
        "estimate_caveat": "Discovery size, extra pages and retries are unknown; estimates do not guarantee completion."}
    print(json.dumps(summary, indent=2))
    return summary


def utc_now():
    return datetime.now(timezone.utc)


def timestamp(clock):
    value = clock()
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("Observation clock must be timezone aware")
    return value.astimezone(timezone.utc)


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def save_new(path, value):
    """Exclusive immutable artifacts; readers reject incomplete JSON after interruption."""
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, indent=2)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())


def load_manifest(path):
    manifest = json.loads(Path(path).read_text(encoding="utf-8"))
    ids = [row["channel_id"] for row in manifest["channels"]]
    if not ids or len(ids) != len(set(ids)) or not manifest.get("version"):
        raise ValueError("Invalid cohort manifest")
    return manifest


def inventory_revision(manifest, previous, additions, observed_at):
    allowed = {r["channel_id"] for r in manifest["channels"]}
    entries = {r["video_id"]: dict(r) for r in previous}
    for row in list(previous) + list(additions):
        if row["channel_id"] not in allowed:
            raise ValueError("Inventory channel is outside cohort")
        # Validate ID shape through the existing shared record schema.
        Video.model_validate({"video_id": row["video_id"], "channel_id": row["channel_id"],
            "title": "inventory validation", "published_at": observed_at,
            "collected_at": observed_at})
        old = entries.get(row["video_id"])
        if old and old["channel_id"] != row["channel_id"]:
            raise ValueError("Conflicting inventory ownership")
        if not old:
            entries[row["video_id"]] = {"video_id": row["video_id"],
                "channel_id": row["channel_id"], "admitted_at": observed_at.isoformat()}
    return sorted(entries.values(), key=lambda r: r["video_id"])


def replay_batch(path, manifest):
    """Read and validate the SAME stored payload/timestamps; never fetch or write DB."""
    batch = json.loads(Path(path).read_text(encoding="utf-8"))
    if "payload" in batch:
        original = dict(batch)
        checksum = original.pop("checksum")
        if checksum != digest(original) or batch["manifest_hash"] != digest(manifest):
            raise ValueError("Payload checksum/manifest mismatch")
        datetime.fromisoformat(batch["observed_at"])
        return batch
    if batch["manifest_hash"] != digest(manifest) or batch["checksum"] != digest(batch["records"]):
        raise ValueError("Batch manifest/checksum mismatch")
    allowed = {r["channel_id"] for r in manifest["channels"]}
    model = {"channels": Channel, "videos": Video}[batch["dataset"]]
    for record in batch["records"]:
        validated = model.model_validate(record)
        if validated.channel_id not in allowed:
            raise ValueError("Replay record outside cohort")
    return batch


def run(manifest, client, state_dir, seed=(), *, dry_run=True, clock=utc_now, max_pages=200, retention=None, no_persist=False, discovery_budget=20):
    """Local artifacts only. client may be shared YouTubeClient with injected transport.

    dry_run=False is intentionally rejected, regardless of manifest approval.
    """
    if discovery_budget < 0:
        raise ValueError("discovery_budget must be nonnegative")
    if max_pages < 1 or max_pages > 200:
        raise ValueError("max_pages must be between 1 and 200")
    if not dry_run:
        raise ValueError("Database writes are disabled")
    if not no_persist and isinstance(client, LiveClient) and (not retention or
            not isinstance(retention.get("payload_retention_days"), int) or
            retention["payload_retention_days"] < 1 or not retention.get("policy_reference")):
        raise PrerequisiteError("Live payload persistence requires explicit retention days and policy reference.")
    if no_persist:
        return _run(manifest, client, None, seed, clock, max_pages, None, discovery_budget)
    state_dir = Path(state_dir)
    state_dir.mkdir(parents=True, exist_ok=True)
    lock = state_dir / "runner.lock"
    with lock.open("x"):
        pass
    try:
        mode = "live" if isinstance(client, LiveClient) else "fixture"
        marker = state_dir / "mode.json"
        if marker.exists():
            if json.loads(marker.read_text())["mode"] != mode:
                raise ValueError("Synthetic and live state must be separate")
        else:
            if mode == "live" and any(state_dir.glob("inventory_*.json")):
                raise ValueError("Unclassified existing inventory cannot be used in live mode")
            save_new(marker, {"mode": mode})
        return _run(manifest, client, state_dir, seed, clock, max_pages, retention, discovery_budget)
    finally:
        lock.unlink()


def _run(manifest, client, state_dir, seed, clock, max_pages, retention, discovery_budget):
    allowed = {r["channel_id"] for r in manifest["channels"]}
    fingerprint = digest(manifest)
    revisions = sorted(state_dir.glob("inventory_*.json")) if state_dir is not None else []
    previous, revision = [], 0
    if revisions:
        prior = json.loads(revisions[-1].read_text(encoding="utf-8"))
        if prior["manifest_hash"] != fingerprint:
            raise ValueError("Inventory manifest changed; explicit migration required")
        previous, revision = prior["videos"], prior["revision"]
    inventory = inventory_revision(manifest, previous, seed, timestamp(clock))
    run_dir = None
    if state_dir is not None:
        run_dir = state_dir / ("run_" + uuid4().hex)
        run_dir.mkdir()
    failures, batches, playlists = [], [], {}

    payload_count = 0
    counts = {dataset: {"requested": 0, "returned": 0, "unavailable": 0,
                       "validation_failures": 0} for dataset in ("channels", "videos")}

    def fetch(method, **kwargs):
        nonlocal payload_count
        if getattr(client, "stopped", False):
            raise BudgetStop("Live collection stopped")
        before = getattr(client, "attempted_requests", len(client.request_log))
        try:
            response = method(**kwargs)
        except FATAL as exc:
            client.stopped = True
            if not client.stop_reason:
                client.stop_reason = type(exc).__name__
            raise
        finally:
            after = getattr(client, "attempted_requests", len(client.request_log))
            dataset = {"channels_list": "channels", "videos_list": "videos"}.get(getattr(method, "__name__", ""))
            if dataset and after > before:
                counts[dataset]["requested"] += len(kwargs["id"])
        observed = timestamp(clock)
        if run_dir is not None and isinstance(client, LiveClient):
            payload = {"manifest_hash": fingerprint, "observed_at": observed.isoformat(), "resource": response.resource,
                       "payload": response.raw}
            payload["checksum"] = digest(payload)
            save_new(run_dir / f"payload_{payload_count:05d}.json", payload)
            payload_count += 1
        return response, observed

    def persist(dataset, records):
        if records and run_dir is not None:
            batch = {"schema_version": 1, "manifest_hash": fingerprint,
                "dataset": dataset, "records": records, "checksum": digest(records)}
            path = run_dir / (f"batch_{len(batches):05d}.json")
            save_new(path, batch)
            batches.append(path.name)

    existing = {r["video_id"]: r["channel_id"] for r in inventory}
    discovered, additions = {}, []
    refresh_batches = (len(existing) + 49) // 50
    if isinstance(client, LiveClient):
        if client.budget - client.attempted_requests < refresh_batches:
            raise PrerequisiteError("API budget is insufficient for one attempt per existing inventory batch.")
        client.discovery_remaining = discovery_budget

    video_groups = {}

    def refresh_videos(ids, *, refresh=False):
        group = {"selected": len(ids), "requested": 0, "returned": 0,
                 "unavailable": 0, "invalid": 0, "failed_requests": 0,
                 "successful_requests": 0, "planned_requests": (len(ids) + 49) // 50,
                 "unattempted_requests": 0, "unconfirmed": 0}
        video_groups["inventory" if refresh else "candidates"] = group
        for start in range(0, len(ids), 50):
            requested = ids[start:start + 50]
            if refresh and isinstance(client, LiveClient):
                remaining_batches = (len(ids) - start - len(requested) + 49) // 50
                client.refresh_ceiling = client.budget - remaining_batches
            before_attempts = getattr(client, "attempted_requests", len(client.request_log))
            request_succeeded = False
            try:
                response, observed = fetch(client.videos_list, part="snippet,statistics,contentDetails", id=requested)
                request_succeeded = True
                group["successful_requests"] += 1
                found, records = set(), []
                for item in response.items:
                    vid = item.get("id")
                    if vid not in requested or vid in found:
                        continue
                    found.add(vid)
                    counts["videos"]["returned"] += 1
                    group["returned"] += 1
                    try:
                        record = Video.model_validate(to_video_record(item, observed))
                        cid = record.channel_id
                        if cid not in allowed or (vid in existing and existing[vid] != cid):
                            raise ValueError("Video outside inventory membership")
                        if vid not in existing and cid not in discovered.get(vid, set()):
                            raise ValueError("Discovery ownership mismatch")
                        records.append(record.model_dump(mode="json"))
                        additions.append({"video_id": vid, "channel_id": cid})
                    except ValueError:
                        failures.append({"stage": "video_validation", "id": vid})
                        counts["videos"]["validation_failures"] += 1
                        group["invalid"] += 1
                group["unavailable"] += len(set(requested) - found)
                counts["videos"]["unavailable"] += len(set(requested) - found)
                failures.extend({"stage": "video_unavailable", "id": vid} for vid in set(requested) - found)
                persist("videos", records)
            except OSError:
                raise
            except Exception:
                failures.append({"stage": "video_request", "count": len(requested)})
            finally:
                attempted = getattr(client, "attempted_requests", len(client.request_log)) > before_attempts
                if attempted:
                    group["requested"] += len(requested)
                    if not request_succeeded:
                        group["failed_requests"] += 1
                        group["unconfirmed"] += len(requested)
                else:
                    group["unattempted_requests"] += 1
        group["all_requests_completed"] = group["successful_requests"] == group["planned_requests"]
        group["all_videos_returned"] = group["returned"] == group["selected"]
        group["complete"] = group["all_requests_completed"] and group["all_videos_returned"] and group["invalid"] == 0
        if isinstance(client, LiveClient):
            client.refresh_ceiling = None

    # Inventory has first use of the budget. Retries cannot consume the one-attempt
    # reserve of later inventory batches. Discovery runs only after this phase.
    refresh_videos(sorted(existing), refresh=True)

    channel_ids = sorted(allowed)
    for start in range(0, len(channel_ids), 50):
        requested = channel_ids[start:start + 50]
        try:
            response, observed = fetch(client.channels_list, part="snippet,statistics,contentDetails", id=requested)
            found, records = set(), []
            for item in response.items:
                cid = item.get("id")
                if cid not in requested or cid in found:
                    continue
                found.add(cid)
                counts["channels"]["returned"] += 1
                playlist = item.get("contentDetails", {}).get("relatedPlaylists", {}).get("uploads")
                if playlist:
                    playlists[cid] = playlist
                try:
                    records.append(Channel.model_validate(to_channel_record(item, observed)).model_dump(mode="json"))
                except ValueError:
                    failures.append({"stage": "channel_validation", "id": cid})
                    counts["channels"]["validation_failures"] += 1
            counts["channels"]["unavailable"] += len(set(requested) - found)
            failures.extend({"stage": "channel_unavailable", "id": cid} for cid in set(requested) - found)
            persist("channels", records)
        except OSError:
            raise
        except Exception:
            failures.append({"stage": "channel_request", "count": len(requested)})

    # A channel gets at most one logical page per round. Shared-client retries
    # belong to that page and still consume both attempt budgets.
    discovery_incomplete, discovery_progress = [], {}
    pending = []
    for cid in channel_ids:
        discovery_progress[cid] = {"pages_returned": 0, "complete": False}
        if cid not in playlists:
            failures.append({"stage": "missing_playlist", "id": cid})
            discovery_incomplete.append({"channel_id": cid, "reason": "missing_playlist"})
        else:
            pending.append((cid, None, set()))
    while pending:
        next_round = []
        for cid, token, seen in pending:
            try:
                response, _ = fetch(client.playlist_items_list, playlist_id=playlists[cid], max_results=50, page_token=token)
                discovery_progress[cid]["pages_returned"] += 1
                for item in response.items:
                    vid = item.get("contentDetails", {}).get("videoId")
                    if vid:
                        discovered.setdefault(vid, set()).add(cid)
                token = response.next_page_token
                if not token:
                    discovery_progress[cid]["complete"] = True
                    continue
                if token in seen:
                    raise PhaseLimit("repeated_page_token")
                if discovery_progress[cid]["pages_returned"] >= max_pages:
                    raise PhaseLimit("per_channel_page_limit_reached")
                seen.add(token)
                next_round.append((cid, token, seen))
            except OSError:
                raise
            except Exception as exc:
                reason = str(exc) if isinstance(exc, PhaseLimit) else (getattr(client, "stop_reason", None) or "discovery_request_failure")
                discovery_incomplete.append({"channel_id": cid, "reason": reason})
                failures.append({"stage": "discovery_incomplete", "id": cid})
        pending = next_round

    requested_ids = sorted(set(existing) | set(discovered))
    refresh_videos(sorted(set(discovered) - set(existing)))
    inventory = inventory_revision(manifest, inventory, additions, timestamp(clock))
    if state_dir is not None:
        save_new(state_dir / f"inventory_{revision + 1:08d}.json", {
            "schema_version": 1, "manifest_hash": fingerprint, "cohort_version": manifest["version"],
            "revision": revision + 1, "videos": inventory})
    report = {"mode": "dry_run_no_database_writes", "inventory_revision": revision + 1 if state_dir is not None else None,
        "inventory_size": len(inventory), "requested_videos": len(requested_ids),
        "failures": failures, "batches": batches, "complete": not failures,
        "quota_used": client.quota_used,
        "attempted_requests": getattr(client, "attempted_requests", len(client.request_log)),
        "stopped": getattr(client, "stopped", False),
        "stop_reason": getattr(client, "stop_reason", None),
        "retention": retention, "database_writes": False, "scheduling": False}
    for values in counts.values():
        values["unconfirmed_due_to_request_failure"] = values["requested"] - values["returned"] - values["unavailable"]
    report["endpoint_requests"] = getattr(client, "endpoint_counts", {})
    report["inventory_refresh"] = {"videos": len(existing), "reserved_initial_attempts": refresh_batches,
                                    **video_groups["inventory"]}
    report["new_candidates"] = video_groups["candidates"]
    report["discovery"] = {"attempt_budget": discovery_budget, "max_pages_per_channel": max_pages,
                            "complete": not discovery_incomplete, "incomplete_channels": discovery_incomplete,
                            "channels": discovery_progress}
    report["counts"] = counts
    report["persistence"] = state_dir is not None
    if run_dir is not None:
        save_new(run_dir / "report.json", report)
    return report


def fixture_client(fixture):
    """Real shared client with an offline transport; no socket or environment key."""
    def transport(url, params, timeout):
        resource = url.rsplit("/", 1)[-1]
        if resource == "channels":
            body = {"items": [x for x in fixture["channels"] if x["id"] in params["id"].split(",")]}
        elif resource == "videos":
            body = {"items": [x for x in fixture["videos"] if x["id"] in params["id"].split(",")]}
        elif resource == "playlistItems":
            pages = fixture["playlists"][params["playlistId"]]
            index = int(params.get("pageToken", "0"))
            body = {"items": [{"contentDetails": {"videoId": v}} for v in pages[index]]}
            if index + 1 < len(pages):
                body["nextPageToken"] = str(index + 1)
        else:
            raise ValueError("Unsupported fixture resource")
        return HttpResult(200, {}, json.dumps(body).encode())
    return YouTubeClient(api_key="offline-fixture-key", transport=transport)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--fixture", type=Path, help="Synthetic response/seed JSON; no connections")
    source.add_argument("--replay", type=Path, help="Validate an existing batch without fetching or writing DB")
    source.add_argument("--live", action="store_true", help="Explicit manual live-fetch opt-in; no writes")
    source.add_argument("--offline-preflight", action="store_true", help="Manifest-only check; no connections")
    parser.add_argument("--preflight-only", action="store_true", help="With --live: bootstrap DB but do not fetch API")
    parser.add_argument("--no-persist", action="store_true", help="With --live: memory-only payloads/inventory and console summary; no files")
    parser.add_argument("--api-budget", type=int)
    parser.add_argument("--max-pages", type=int, default=10, help="Maximum discovery pages per channel")
    parser.add_argument("--discovery-budget", type=int, default=20, help="Global playlistItems attempt limit including retries")
    parser.add_argument("--max-retries", type=int, default=2)
    parser.add_argument("--payload-retention-days", type=int)
    parser.add_argument("--retention-policy-ref", help="Local policy reference; supplied reference does not establish approval")
    parser.add_argument("--dry-run", action="store_true", required=True)
    args = parser.parse_args(argv)
    try:
        if args.no_persist and not args.live:
            raise PrerequisiteError("--no-persist requires explicit --live and --dry-run.")
        manifest = load_manifest(args.manifest)
        state = STATE / ("live" if args.live else "fixture") / digest(manifest)[:16]
        if args.offline_preflight:
            preflight(manifest, STATE / "live" / digest(manifest)[:16], budget=args.api_budget)
            return 0
        if args.live:
            if args.api_budget is None or args.api_budget < 1:
                raise PrerequisiteError("Live mode requires a positive --api-budget.")
            if args.discovery_budget < 0:
                raise PrerequisiteError("--discovery-budget must be nonnegative.")
            if not 1 <= args.max_pages <= 200 or not 0 <= args.max_retries <= 5:
                raise PrerequisiteError("Use --max-pages 1..200 and --max-retries 0..5.")
            if not args.preflight_only and not args.no_persist and (not args.payload_retention_days or args.payload_retention_days < 1 or not args.retention_policy_ref):
                raise PrerequisiteError("Before live fetching/payload persistence, supply --payload-retention-days and --retention-policy-ref from an agreed policy. No approved period is assumed; no automatic deletion occurs.")
            print("Manual live dry run; cohort approval unchanged. Retention configuration is operator supplied, not policy approval.")
            preflight(manifest, state, budget=args.api_budget, no_persist=args.no_persist,
                      discovery_budget=args.discovery_budget, max_pages=args.max_pages)
            seed = bootstrap_inventory(manifest)
            preflight(manifest, state, seed, budget=args.api_budget, bootstrap=True, no_persist=args.no_persist,
                      discovery_budget=args.discovery_budget, max_pages=args.max_pages)
            if args.preflight_only:
                return 0
            client = LiveClient(args.api_budget, authorized=True, retries=args.max_retries)
            if args.no_persist:
                report = run(manifest, client, None, seed, max_pages=args.max_pages, no_persist=True, discovery_budget=args.discovery_budget)
                print(json.dumps({key: report[key] for key in (
                    "complete", "counts", "attempted_requests", "stop_reason",
                    "endpoint_requests", "inventory_refresh", "new_candidates", "discovery",
                    "inventory_size", "persistence", "database_writes", "scheduling")}, indent=2))
                return 0 if report["complete"] else 1
            # Separate immutable metadata; no cleanup or deletion of existing artifacts.
            state.mkdir(parents=True, exist_ok=True)
            save_new(state / ("retention_" + uuid4().hex + ".json"), {
                "configured_at": utc_now().isoformat(), "payload_retention_days": args.payload_retention_days,
                "policy_reference": args.retention_policy_ref, "approval_asserted": False,
                "enforcement": "Manual review/removal required; automatic deletion disabled"})
            report = run(manifest, client, state, seed, max_pages=args.max_pages, retention={
                "payload_retention_days": args.payload_retention_days, "policy_reference": args.retention_policy_ref},
                discovery_budget=args.discovery_budget)
            print(json.dumps({key: report[key] for key in (
                "complete", "counts", "attempted_requests", "stop_reason", "endpoint_requests",
                "inventory_refresh", "new_candidates", "discovery", "persistence", "database_writes", "scheduling")}, indent=2))
            return 0 if report["complete"] else 1
        if args.preflight_only:
            raise PrerequisiteError("--preflight-only requires --live; use --offline-preflight for no connections.")
        if args.replay:
            batch = replay_batch(args.replay, load_manifest(args.manifest))
            print("Replay validated:", len(batch.get("records", batch.get("payload", {}).get("items", []))), "records; payload/timestamps unchanged; no database writes.")
            return 0
        fixture = json.loads(args.fixture.read_text(encoding="utf-8"))
        manifest = load_manifest(args.manifest)
        preflight(manifest, state, fixture.get("seed", []))
        report = run(manifest, fixture_client(fixture), state,
                     seed=fixture.get("seed", []))
        print("Local fixture run complete; inventory:", report["inventory_size"],
              "failures:", len(report["failures"]), "; no database writes.")
        return 0 if report["complete"] else 1
    except PrerequisiteError as exc:
        print(str(exc))
        return 1
    except Exception:
        print("Runner failed. Details suppressed; inspect local configuration and artifacts.")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
