"""Tests for the organization-analysis endpoints (search + quick analysis jobs).

TEST DATA (synthetic): a fake discovery result and a fake job runner. No YouTube API call, no
Supabase, no pipeline run; jobs run synchronously in a temporary folder.
"""

import json

import pytest
from fastapi.testclient import TestClient

from backend.config import ConfigError, Settings, load_settings
from backend.main import create_app
from backend.services.component_3.analysis_jobs import AnalysisJobs, _safe
from research.component_3 import analysis as an

API = "/api/v1/component-3/analysis"
CH1, CH2, CH3 = "UC" + "a" * 22, "UC" + "b" * 22, "UC" + "c" * 22
CANDIDATES = {"organization": "Sirasa", "discovered_at": "2026-10-16T00:00:00Z", "quota_used": 120,
              "candidates": [{"channel_id": CH1, "title": "Sirasa TV", "handle": "@sirasatv", "country": "LK",
                              "subscriber_count": 1000, "video_count": 10, "score": 7.5, "confidence": "high",
                              "evidence": ["organization name in channel title"], "previously_confirmed": False}]}


def fake_runner(calls):
    def run(organization, channels, progress):
        calls.append((organization, dict(channels)))
        progress("preflight", "completed", {"free_disk_gb": 10})
        progress("comments", "running", {"videos_done": 5, "videos_total": 10})
        progress("comments", "completed", {"collected": 42, "note": "anon_" + "0" * 64})
        progress("audience_bridge", "completed", {"artifact": "abs-0123456789ab"})
        return {"organization": organization, "snapshot_id": "rs-20261016T000000Z",
                "experiment_id": "abs-0123456789ab", "client": object()}
    return run


@pytest.fixture
def setup(tmp_path):
    calls, confirmed = [], []
    jobs = AnalysisJobs(runner=fake_runner(calls), discoverer=lambda org, region: {**CANDIDATES, "region": region},
                        jobs_dir=tmp_path / "jobs", confirm=lambda org, ids: confirmed.append((org, ids)),
                        background=False)
    client = TestClient(create_app(Settings(), analysis=jobs))
    return client, jobs, calls, confirmed, tmp_path / "jobs"


def body(*ids, org="Sirasa"):
    return {"organization": org, "channels": [{"channel_id": i, "title": f"T{n}"} for n, i in enumerate(ids)]}


def test_config_lists_quick_steps(setup):
    client, *_ = setup
    r = client.get(f"{API}/config")
    assert r.status_code == 200
    data = r.json()
    assert data["enabled"] is True and data["active_job_id"] is None
    steps = [s["step"] for s in data["stages"]]
    assert steps[0] == "preflight" and "audience_bridge" in steps
    assert not {"hgt", "node2vec", "evaluation"} & set(steps)   # skipped for speed
    assert data["limits"]["max_videos_per_channel"] == an.QUICK_LIMITS["max_videos_per_channel"]


def test_discover_uses_youtube_search_and_validates(setup):
    client, *_ = setup
    r = client.post(f"{API}/discover", json={"organization": "Sirasa", "region_code": "lk"})
    assert r.status_code == 200
    assert r.json()["source"] == "youtube" and r.json()["region"] == "LK"
    assert r.json()["candidates"][0]["channel_id"] == CH1
    assert client.post(f"{API}/discover", json={"organization": "x"}).status_code == 422
    assert client.post(f"{API}/discover", json={"organization": "Sirasa;DROP"}).status_code == 422
    assert client.post(f"{API}/discover", json={"organization": "Sirasa", "region_code": "1K"}).status_code == 422


def test_saved_discovery_missing_is_404(setup):
    client, *_ = setup
    r = client.get(f"{API}/discover", params={"organization": "No Such Org Zz"})
    assert r.status_code == 404 and r.json()["error"]["code"] == "not_found"


def test_job_runs_records_progress_and_persists(setup):
    client, jobs, calls, confirmed, jobs_dir = setup
    r = client.post(f"{API}/jobs", json=body(CH1, CH2))
    assert r.status_code == 202
    job = r.json()
    assert job["status"] == "completed" and job["organization"] == "Sirasa"
    assert calls == [("Sirasa", {CH1: "T0", CH2: "T1"})]
    assert confirmed == [("Sirasa", [CH1, CH2])]
    steps = {s["step"]: s for s in job["steps"]}
    assert steps["comments"]["status"] == "completed" and steps["comments"]["details"]["collected"] == 42
    assert steps["comments"]["details"]["note"] == "[redacted]"           # never an identifier
    assert steps["videos"]["status"] == "pending"                         # not reported by the fake
    assert job["result"]["snapshot_id"] == "rs-20261016T000000Z" and "client" not in job["result"]
    assert (jobs_dir / f"{job['job_id']}.json").is_file()
    assert client.get(f"{API}/jobs/{job['job_id']}").json()["status"] == "completed"
    assert client.get(f"{API}/jobs").json()["items"][0]["job_id"] == job["job_id"]


def test_job_validation(setup):
    client, *_ = setup
    assert client.post(f"{API}/jobs", json=body(CH1)).status_code == 422            # one channel: no pairs
    r = client.post(f"{API}/jobs", json=body(CH1, "not a channel id"))
    assert r.status_code == 422 and "valid" in r.json()["error"]["message"]
    assert client.get(f"{API}/jobs/job-zzz").status_code == 422
    assert client.get(f"{API}/jobs/job-000000000000").status_code == 404


def test_one_job_at_a_time(setup):
    client, jobs, *_ = setup
    first = client.post(f"{API}/jobs", json=body(CH1, CH2)).json()
    jobs._jobs[first["job_id"]].status = "running"                       # simulate an active job
    r = client.post(f"{API}/jobs", json=body(CH2, CH3))
    assert r.status_code == 409 and r.json()["error"]["code"] == "conflict"
    assert client.get(f"{API}/config").json()["active_job_id"] == first["job_id"]


def test_failed_job_reports_safe_message(tmp_path):
    def boom(organization, channels, progress):
        progress("videos", "running", {})
        raise an.AnalysisError("no videos were collected; the channels may have no public uploads")

    jobs = AnalysisJobs(runner=boom, discoverer=lambda o, r: CANDIDATES, jobs_dir=tmp_path,
                        confirm=lambda o, i: None, background=False)
    job = TestClient(create_app(Settings(), analysis=jobs)).post(f"{API}/jobs", json=body(CH1, CH2)).json()
    assert job["status"] == "failed" and "no videos" in job["error"]
    assert next(s for s in job["steps"] if s["step"] == "videos")["status"] == "failed"

    def crash(organization, channels, progress):
        raise KeyError("C:/secret/path")

    jobs.runner = crash
    job = TestClient(create_app(Settings(), analysis=jobs)).post(f"{API}/jobs", json=body(CH1, CH2)).json()
    assert job["status"] == "failed" and "secret" not in job["error"] and "KeyError" in job["error"]


def test_disabled_server_refuses_writes(tmp_path):
    jobs = AnalysisJobs(enabled=False, runner=fake_runner([]), discoverer=lambda o, r: CANDIDATES,
                        jobs_dir=tmp_path, background=False)
    client = TestClient(create_app(Settings(analysis_enabled=False), analysis=jobs))
    assert client.get(f"{API}/config").json()["enabled"] is False
    for r in (client.post(f"{API}/discover", json={"organization": "Sirasa"}),
              client.post(f"{API}/jobs", json=body(CH1, CH2))):
        assert r.status_code == 403 and r.json()["error"]["code"] == "forbidden"


def test_running_job_becomes_interrupted_after_restart(tmp_path):
    (tmp_path / "job-0123456789ab.json").write_text(json.dumps(
        {"job_id": "job-0123456789ab", "organization": "Sirasa", "channels": [], "status": "running"}),
        encoding="utf-8")
    job = AnalysisJobs(jobs_dir=tmp_path).get("job-0123456789ab")
    assert job["status"] == "interrupted" and job["finished_at"]


def test_enable_flag_setting(monkeypatch):
    monkeypatch.setenv("API_ENABLE_ANALYSIS", "false")
    assert load_settings().analysis_enabled is False
    monkeypatch.setenv("API_ENABLE_ANALYSIS", "maybe")
    with pytest.raises(ConfigError):
        load_settings()


def test_cors_allows_post_from_dashboard(setup):
    client, *_ = setup
    r = client.options(f"{API}/jobs", headers={"Origin": "http://localhost:5173", "Access-Control-Request-Method": "POST"})
    assert r.status_code == 200 and "POST" in r.headers["access-control-allow-methods"]


def test_safe_drops_clients_and_identifiers():
    assert _safe({"client": object(), "a": ["commenter:x", 1, None]}) == {"a": ["[redacted]", 1, None]}


def test_complete_runs_skipped_stages_on_a_quick_snapshot(tmp_path):
    seen = []

    def completer(snapshot_id, progress):
        seen.append(snapshot_id)
        for step in ("hgt", "node2vec", "evaluation"):
            progress(step, "completed", {"artifact": f"{step}-x"})
        return {"snapshot_id": snapshot_id, "evaluation": "eval-0123456789ab"}

    jobs = AnalysisJobs(runner=fake_runner([]), discoverer=lambda o, r: CANDIDATES, jobs_dir=tmp_path,
                        background=False, completer=completer, snapshot_organization=lambda sid: "Sirasa")
    client = TestClient(create_app(Settings(), analysis=jobs))
    r = client.post(f"{API}/complete", json={"snapshot_id": "rs-20261016T095457Z"})
    assert r.status_code == 202
    job = r.json()
    assert job["kind"] == "complete" and job["snapshot_id"] == "rs-20261016T095457Z" and job["status"] == "completed"
    assert [s["step"] for s in job["steps"]] == ["hgt", "node2vec", "evaluation"]
    assert all(s["status"] == "completed" for s in job["steps"]) and seen == ["rs-20261016T095457Z"]
    assert client.post(f"{API}/complete", json={"snapshot_id": "rs-bad-id-0000000000"}).status_code == 422


def test_complete_refuses_research_snapshots(tmp_path):
    from backend.services.component_3.service import InvalidParameter

    def refuse(sid):
        raise InvalidParameter("only quick-analysis snapshots can be completed from the dashboard")

    jobs = AnalysisJobs(jobs_dir=tmp_path, background=False, snapshot_organization=refuse)
    r = TestClient(create_app(Settings(), analysis=jobs)).post(f"{API}/complete", json={"snapshot_id": "rs-20261010T081534Z"})
    assert r.status_code == 422 and "quick-analysis" in r.json()["error"]["message"]
