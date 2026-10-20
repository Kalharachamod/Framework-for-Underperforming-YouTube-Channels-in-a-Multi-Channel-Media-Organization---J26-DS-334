"""Organization discovery and quick-analysis jobs for the dashboard's "Analyze organization" page.

Unlike the rest of the API (read-only over stored artifacts), these operations call the YouTube Data API
(quota) and write to the shared database and research data folder. They are therefore:

* switchable: ``API_ENABLE_ANALYSIS=false`` turns every write endpoint off (403)
* serialized: one analysis job runs at a time; a second request is refused while one is active
* bounded: 2-25 channels per job, quick collection limits and a quota cap (research.component_3.analysis)
* recorded: every job is written to ``data/raw/analysis_jobs/<job_id>.json``; a job that was still running
  when the API stopped is reported as ``interrupted`` (never as completed)

Messages never contain secrets or commenter identifiers.
"""

from __future__ import annotations

import json
import re
import threading
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from shared.utils import paths

from backend.services.component_3.service import InvalidParameter, NotFound

JOB_ID = re.compile(r"^job-[0-9a-f]{12}$")
ORG_NAME = re.compile(r"^[\w .&'()+-]{2,60}$", re.UNICODE)

Runner = Callable[[str, dict[str, str], Callable[[str, str, dict[str, Any]], None]], dict[str, Any]]
Completer = Callable[[str, Callable[[str, str, dict[str, Any]], None]], dict[str, Any]]
SNAPSHOT_ID = re.compile(r"^rs-\d{8}T\d{6}Z$")
Discoverer = Callable[[str, str | None], dict[str, Any]]


class AnalysisDisabled(PermissionError):
    pass


class AnalysisBusy(RuntimeError):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


@dataclass
class Job:
    job_id: str
    organization: str
    channels: list[dict[str, str]]
    status: str = "queued"                 # queued | running | completed | failed | interrupted
    kind: str = "quick"                    # quick (collect + score) | complete (HGT, node2vec, evaluation)
    snapshot_id: str | None = None         # the snapshot a "complete" job works on
    created_at: str = field(default_factory=_now)
    started_at: str | None = None
    finished_at: str | None = None
    steps: list[dict[str, Any]] = field(default_factory=list)
    result: dict[str, Any] | None = None
    error: str | None = None


def check_organization(name: str) -> str:
    name = (name or "").strip()
    if not ORG_NAME.fullmatch(name):
        raise InvalidParameter("organization must be 2-60 letters, digits, spaces or . & ' ( ) + -")
    return name


def default_discoverer(organization: str, region_code: str | None) -> dict[str, Any]:
    """Fresh YouTube search (about 100-150 quota units); the candidates are saved for review."""
    from shared.data_collection.org_discovery import discover_organization, save_review
    from shared.data_collection.youtube_api_client import YouTubeClient

    result = discover_organization(organization, YouTubeClient(), region_code=region_code)
    save_review(result)
    return discovery_payload(result)


def saved_discovery(organization: str) -> dict[str, Any] | None:
    from shared.data_collection.org_discovery import load_review

    try:
        return discovery_payload(load_review(organization))
    except (FileNotFoundError, ValueError, KeyError):
        return None


def discovery_payload(result) -> dict[str, Any]:
    from shared.data_collection.org_discovery import load_organization

    try:
        confirmed = {c["channel_id"] for c in load_organization(result.organization).get("channels", [])}
    except (FileNotFoundError, ValueError, KeyError):
        confirmed = set()
    return {"organization": result.organization, "discovered_at": result.discovered_at,
            "quota_used": result.quota_used,
            "candidates": [{"channel_id": c.channel_id, "title": c.title, "handle": c.handle, "country": c.country,
                            "subscriber_count": c.subscriber_count, "video_count": c.video_count,
                            "score": c.score, "confidence": c.confidence, "evidence": list(c.evidence),
                            "previously_confirmed": c.channel_id in confirmed}
                           for c in result.candidates]}


def default_runner(organization: str, channels: dict[str, str], progress) -> dict[str, Any]:
    from research.component_3.analysis import run_analysis

    return run_analysis(organization, channels, progress)


def default_completer(snapshot_id: str, progress) -> dict[str, Any]:
    from research.component_3.analysis import complete_analysis

    return complete_analysis(snapshot_id, progress)


def quick_snapshot_organization(snapshot_id: str) -> str:
    """The organization of a quick-analysis snapshot; anything else is refused."""
    from research.component_3.analysis import SNAPSHOT_SOURCE
    from shared.utils import snapshots

    try:
        info = snapshots.get_research_snapshot(snapshot_id)
    except Exception:  # noqa: BLE001 - unknown or unreadable snapshot
        raise NotFound(f"research snapshot {snapshot_id} does not exist") from None
    org = (info.manifest.get("details") or {}).get("organization")
    if info.source != SNAPSHOT_SOURCE or not org:
        raise InvalidParameter("only quick-analysis snapshots can be completed from the dashboard; the research "
                               "dataset uses the research commands")
    return str(org)


def record_confirmation(organization: str, channel_ids: list[str]) -> None:
    """Save the reviewer's channel choice as config/organizations/<slug>.json when none exists yet.
    An existing confirmed list (e.g. the research organization Derana) is never overwritten."""
    from shared.data_collection.org_discovery import confirm_organization, load_organization, load_review

    try:
        load_organization(organization)
        return
    except (FileNotFoundError, ValueError, KeyError):
        pass
    try:
        confirm_organization(load_review(organization), channel_ids)
    except (FileNotFoundError, ValueError, KeyError):
        pass  # no saved discovery: the job record still documents the channels


class AnalysisJobs:
    def __init__(self, *, enabled: bool = True, runner: Runner | None = None, discoverer: Discoverer | None = None,
                 jobs_dir: Path | None = None, confirm: Callable[[str, list[str]], None] | None = None,
                 background: bool = True, completer: Completer | None = None,
                 snapshot_organization: Callable[[str], str] | None = None):
        self.enabled = enabled
        self.runner = runner or default_runner
        self.discoverer = discoverer or default_discoverer
        self.confirm = confirm or record_confirmation
        self.completer = completer or default_completer
        self.snapshot_organization = snapshot_organization or quick_snapshot_organization
        self.jobs_dir = jobs_dir or (paths.get_data_paths().raw / "analysis_jobs")
        self.background = background
        self._lock = threading.Lock()
        self._jobs: dict[str, Job] = {}
        self._load()

    # --- persistence -------------------------------------------------------------------------------

    def _load(self) -> None:
        if not self.jobs_dir.is_dir():
            return
        for f in sorted(self.jobs_dir.glob("job-*.json")):
            try:
                job = Job(**json.loads(f.read_text(encoding="utf-8")))
            except (ValueError, TypeError):
                continue
            if job.status in ("queued", "running"):   # the process that ran it is gone
                job.status, job.error = "interrupted", "the API stopped before this analysis finished"
                job.finished_at = job.finished_at or _now()
                self._save(job)
            self._jobs[job.job_id] = job

    def _save(self, job: Job) -> None:
        self.jobs_dir.mkdir(parents=True, exist_ok=True)
        tmp = self.jobs_dir / f".{job.job_id}.tmp"
        tmp.write_text(json.dumps(asdict(job), indent=2), encoding="utf-8")
        tmp.replace(self.jobs_dir / f"{job.job_id}.json")

    # --- API operations ----------------------------------------------------------------------------

    def config(self) -> dict[str, Any]:
        from research.component_3 import analysis as an

        active = self.active()
        return {"enabled": self.enabled, "min_channels": an.MIN_CHANNELS, "max_channels": an.MAX_CHANNELS,
                "limits": dict(an.QUICK_LIMITS), "stages": [{"step": s, "label": an.STEP_LABELS[s]} for s in an.STEPS],
                "active_job_id": active.job_id if active else None,
                "note": "Quick analyses collect a small fresh sample and stop at the Audience Bridge Score "
                        "(HGT, node2vec and the evaluation are skipped). They are exploratory and separate "
                        "from the research dataset."}

    def discover(self, organization: str, region_code: str | None, *, refresh: bool) -> dict[str, Any]:
        organization = check_organization(organization)
        if region_code is not None and not re.fullmatch(r"[A-Za-z]{2}", region_code):
            raise InvalidParameter("region_code must be a 2-letter country code, e.g. LK")
        if not refresh:
            saved = saved_discovery(organization)
            if saved is None:
                raise NotFound(f"no saved search for '{organization}'; search YouTube first")
            return {**saved, "source": "saved"}
        self._require_enabled()
        return {**self.discoverer(organization, region_code.upper() if region_code else None), "source": "youtube"}

    def start(self, organization: str, channels: list[dict[str, str]]) -> dict[str, Any]:
        from research.component_3 import analysis as an

        self._require_enabled()
        organization = check_organization(organization)
        chosen = {c["channel_id"]: (c.get("title") or c["channel_id"]) for c in channels}
        try:
            an.validate_channels(chosen)
        except an.AnalysisError as exc:
            raise InvalidParameter(str(exc)) from None
        with self._lock:
            if self.active() is not None:
                raise AnalysisBusy("an analysis is already running; wait for it to finish")
            job = Job(job_id=f"job-{uuid.uuid4().hex[:12]}", organization=organization,
                      channels=[{"channel_id": k, "title": v} for k, v in chosen.items()],
                      steps=[{"step": s, "label": an.STEP_LABELS[s], "status": "pending", "details": {}}
                             for s in an.STEPS])
            self._jobs[job.job_id] = job
            self._save(job)
        self.confirm(organization, list(chosen))
        if self.background:
            threading.Thread(target=self._run, args=(job.job_id,), name=job.job_id, daemon=True).start()
        else:
            self._run(job.job_id)
        return self.get(job.job_id)

    def complete(self, snapshot_id: str) -> dict[str, Any]:
        """Run the stages a quick analysis skipped (HGT, node2vec, evaluation) on its snapshot."""
        from research.component_3 import analysis as an

        self._require_enabled()
        if not SNAPSHOT_ID.fullmatch(snapshot_id or ""):
            raise InvalidParameter("snapshot_id must look like rs-YYYYMMDDTHHMMSSZ")
        organization = self.snapshot_organization(snapshot_id)
        with self._lock:
            if self.active() is not None:
                raise AnalysisBusy("an analysis is already running; wait for it to finish")
            job = Job(job_id=f"job-{uuid.uuid4().hex[:12]}", organization=organization, channels=[],
                      kind="complete", snapshot_id=snapshot_id,
                      steps=[{"step": s, "label": an.STEP_LABELS[s], "status": "pending", "details": {}}
                             for s in an.COMPLETE_STEPS])
            self._jobs[job.job_id] = job
            self._save(job)
        if self.background:
            threading.Thread(target=self._run, args=(job.job_id,), name=job.job_id, daemon=True).start()
        else:
            self._run(job.job_id)
        return self.get(job.job_id)

    def get(self, job_id: str) -> dict[str, Any]:
        if not JOB_ID.fullmatch(job_id or ""):
            raise InvalidParameter("job_id must look like job-<12 hex characters>")
        job = self._jobs.get(job_id)
        if job is None:
            raise NotFound(f"analysis job {job_id} does not exist")
        with self._lock:
            return json.loads(json.dumps(asdict(job)))

    def list(self) -> dict[str, Any]:
        jobs = sorted(self._jobs.values(), key=lambda j: j.created_at, reverse=True)
        with self._lock:
            return {"items": [json.loads(json.dumps(asdict(j))) for j in jobs[:50]]}

    def active(self) -> Job | None:
        return next((j for j in self._jobs.values() if j.status in ("queued", "running")), None)

    def _require_enabled(self) -> None:
        if not self.enabled:
            raise AnalysisDisabled("organization analysis is disabled on this server (API_ENABLE_ANALYSIS=false)")

    # --- worker ------------------------------------------------------------------------------------

    def _progress(self, job: Job, step: str, status: str, details: dict[str, Any]) -> None:
        with self._lock:
            for s in job.steps:
                if s["step"] == step:
                    s["status"], s["details"] = status, _safe(details)
                    if status == "running" and "started_at" not in s:
                        s["started_at"] = _now()
                    if status in ("completed", "failed", "skipped"):
                        s["finished_at"] = _now()
            self._save(job)

    def _run(self, job_id: str) -> None:
        job = self._jobs[job_id]
        with self._lock:
            job.status, job.started_at = "running", _now()
            self._save(job)
        try:
            report = lambda step, status, details: self._progress(job, step, status, details)  # noqa: E731
            if job.kind == "complete":
                result = self.completer(job.snapshot_id, report)
            else:
                result = self.runner(job.organization, {c["channel_id"]: c["title"] for c in job.channels}, report)
            with self._lock:
                job.status, job.result = "completed", _safe(result)
        except Exception as exc:  # noqa: BLE001 - reported on the job; messages are already safe
            from research.component_3.analysis import AnalysisError

            message = str(exc) if isinstance(exc, (AnalysisError, ValueError)) else \
                f"{type(exc).__name__}: the analysis failed (see the API log)"
            with self._lock:
                job.status, job.error = "failed", message[:500]
                for s in job.steps:
                    if s["status"] == "running":
                        s["status"], s["finished_at"] = "failed", _now()
        finally:
            with self._lock:
                job.finished_at = _now()
                self._save(job)


def _safe(value: Any) -> Any:
    """JSON-serializable copy without client objects or commenter identifiers."""
    if isinstance(value, dict):
        return {str(k): _safe(v) for k, v in value.items() if k != "client"}
    if isinstance(value, (list, tuple)):
        return [_safe(v) for v in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        if isinstance(value, str) and ("anon_" in value or "commenter:" in value):
            return "[redacted]"
        return value
    return str(value)
