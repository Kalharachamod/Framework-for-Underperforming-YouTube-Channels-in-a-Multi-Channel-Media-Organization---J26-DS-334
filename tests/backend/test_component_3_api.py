"""Tests for the Component 3 FastAPI layer (STEP 23).

TEST DATA (synthetic): the STEP 21 evaluation fixture snapshot (cricket channels A, B, C sharing
commenters, cooking channels D, E, F isolated, X without videos), scored (STEP 19), explained
(STEP 22) and evaluated (STEP 21) once per module in a temporary data folder. No network, no
Supabase, no real data.
"""

import json
import os
import sys
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from backend.api.component_3 import schemas as sc
from backend.config import ConfigError, Settings, load_settings
from backend.database import component_3_artifacts as store_mod
from backend.database.component_3_artifacts import Component3Store, StorageError
from backend.main import create_app
from backend.services.component_3 import service as svc_mod
from shared.utils import snapshots as s

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "component_3"))
from test_evaluation import CH, P, RAW, SMALL_N2V, FakeEncoder, build_snapshot  # noqa: E402

API = "/api/v1/component-3"
A, B, C, D, X = (CH[k] for k in "ABCDX")
SALT = "test-salt-" + "0" * 54


@contextmanager
def env(**values):
    old = {k: os.environ.get(k) for k in values}
    os.environ.update(values)
    try:
        yield
    finally:
        for k, v in old.items():
            os.environ.pop(k, None) if v is None else os.environ.__setitem__(k, v)


@contextmanager
def ticking_clock():
    times = iter(datetime(2026, 10, 9, 10, 0, tzinfo=timezone.utc) + timedelta(seconds=i) for i in range(500))
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(s, "_utcnow", lambda: next(times))
        yield


def build_artifacts(root: Path, explain: bool = True, evaluate: bool = True) -> dict:
    from research.component_3.evaluation import evaluate as ev
    from research.component_3.explainability import explain as ex
    from research.component_3.model import audience_bridge as ab

    with env(DATA_DIR=str(root), COMMENTER_HASH_SALT=SALT), ticking_clock():
        sid = build_snapshot()
        from research.component_3.preprocessing import graph_features as gf
        from research.component_3.preprocessing import hetero_graph as hg

        graph = hg.build_graph(sid)                    # persisted as by the STEP 13 / 14 commands
        hg.save_graph(graph)
        gf.save_features(gf.build_features(sid, graph=graph))
        bridge = ab.run(sid, encoder=FakeEncoder())
        ab.save(bridge)
        out = {"sid": sid, "eid": bridge.experiment_id}
        if explain:
            out["xid"] = ex.save(ex.explain(bridge)).name
        if evaluate:
            r = ev.evaluate(sid, ev.EvaluationConfig(run_sparse=False), encoder=FakeEncoder(), node2vec_config=SMALL_N2V)
            ev.save(r)
            out["evid"] = r.evaluation_id
    return out


@pytest.fixture(scope="module")
def full(tmp_path_factory):
    root = tmp_path_factory.mktemp("api_full")
    return {"root": root, **build_artifacts(root)}


@pytest.fixture
def client(full, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(full["root"]))
    return TestClient(create_app(Settings()))


def get(client, url, status=200, **params):
    r = client.get(url, params=params)
    assert r.status_code == status, r.text
    return r.json()


# 1-2. health and status ----------------------------------------------------------------------

def test_health_does_not_claim_artifacts(isolated_data_dir):
    c = TestClient(create_app(Settings()))
    body = get(c, "/health")
    assert body["status"] == "ok" and "time" in body
    status = get(c, f"{API}/status")
    assert status["research_data"] == "missing" and status["artifacts"] == []


def test_status_reports_each_artifact(client, full):
    body = get(client, f"{API}/status")
    sc.ResearchStatusResponse.model_validate(body)
    arts = {a["name"]: a for a in body["artifacts"]}
    assert body["latest_snapshot_id"] == full["sid"] == body["snapshot_id"]
    assert arts["audience_bridge_scores"]["status"] == "available" and arts["audience_bridge_scores"]["latest_id"] == full["eid"]
    assert arts["explanations"]["latest_id"] == full["xid"] and arts["evaluations"]["latest_id"] == full["evid"]
    assert arts["baseline_louvain"]["status"] == "missing"          # evaluation does not persist baselines
    assert "does not imply" in body["note"]


# 3-4. channels -----------------------------------------------------------------------------------

def test_channel_list_and_detail(client, full):
    body = get(client, f"{API}/channels")
    assert body["total"] == 7 and body["features_status"] == "available"
    a = next(i for i in body["items"] if i["channel_id"] == A)
    assert a["channel_name"] == "A" and a["stored_video_count"] == 2
    d = get(client, f"{API}/channels/{A}")
    assert d["channel_id"] == A and d["unique_commenter_count"] == 3 and d["snapshot_id"] == full["sid"]
    assert get(client, f"{API}/channels/channel:{A}")["channel_id"] == A           # graph id form accepted


def test_channel_pairs(client):
    body = get(client, f"{API}/channels/{A}/pairs", limit=1)
    assert body["total"] == 2 and len(body["items"]) == 1
    assert body["items"][0]["shared_commenters"] == 2 and body["items"][0]["destination_channel_id"] in (B, C)


def test_unknown_and_invalid_channels(client):
    err = get(client, f"{API}/channels/UC_unknown_channel", 404)
    assert err["error"]["code"] == "not_found"
    assert get(client, f"{API}/channels/bad id!", 422)["error"]["code"] == "invalid_parameter"
    assert get(client, f"{API}/bridge/UC_unknown_channel/destinations", 404)["error"]["code"] == "not_found"


# 5-8. audience bridge ------------------------------------------------------------------------------

def test_ranked_destinations(client, full):
    body = get(client, f"{API}/bridge/{A}/destinations", limit=2)
    sc.BridgeRankingResponse.model_validate(body)
    assert body["experiment_id"] == full["eid"] and body["total"] == 5
    assert [i["rank"] for i in body["items"]] == [1, 2] and body["items"][0]["destination_channel_id"] == C
    nxt = get(client, f"{API}/bridge/{A}/destinations", limit=2, offset=2)
    assert [i["rank"] for i in nxt["items"]] == [3, 4]
    allp = get(client, f"{API}/bridge/{A}/destinations", include_unscored=True, limit=100)
    assert allp["total"] == 6 and allp["items"][-1]["rank"] is None and allp["items"][-1]["destination_channel_id"] == X


def test_self_pairs_excluded(client):
    body = get(client, f"{API}/bridge/{A}/destinations", include_unscored=True, limit=100)
    assert all(i["destination_channel_id"] != A for i in body["items"])
    assert get(client, f"{API}/bridge/{A}/destinations/{A}", 422)["error"]["code"] == "invalid_parameter"


def test_pair_decomposition_and_explanation(client, full):
    body = get(client, f"{API}/bridge/{A}/destinations/{C}")
    sc.BridgePairResponse.model_validate(body)
    b = body["score_breakdown"]
    assert body["audience_bridge_score"] == pytest.approx((b["diffusion_component"] + b["topic_component"]) *
                                                          b["confidence_component"]) == pytest.approx(0.4)
    assert b["w_diffusion"] == 0.5 and b["shared_commenters"] == 2
    assert body["explanation_status"] == "available" and body["explanation_outcome"] == "complete"
    assert body["evidence_summary"]["shared_commenter_state"] == "observed"
    assert {r["reason_code"] for r in body["explanation_reasons"]} >= {"low_confidence_sparse_evidence"}
    assert body["ranking_context"]["scored_destinations"] == 5
    assert (body["snapshot_id"], body["experiment_id"]) == (full["sid"], full["eid"])


def test_missing_explanation_artifact(tmp_path, monkeypatch):
    info = build_artifacts(tmp_path / "data", explain=False, evaluate=False)
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    c = TestClient(create_app(Settings()))
    body = get(c, f"{API}/bridge/{A}/destinations/{C}")
    assert body["explanation_status"] == "unavailable" and "no explanation artifact" in body["explanation_detail"]
    assert body["explanation_reasons"] == [] and body["evidence_summary"] is None
    assert body["audience_bridge_score"] == pytest.approx(0.4)                 # the stored score is still served
    assert get(c, f"{API}/evaluation/runs")["items"] == []
    err = get(c, f"{API}/evaluation/eval-000000000000/ranking", 404)["error"]
    assert err["code"] == "artifact_unavailable"
    assert info["eid"] == get(c, f"{API}/bridge/experiments")["items"][0]["experiment_id"]


# 9-10. evaluation ------------------------------------------------------------------------------------

def test_evaluation_results(client, full):
    runs = get(client, f"{API}/evaluation/runs")["items"]
    assert runs[0]["evaluation_id"] == full["evid"] and runs[0]["audience_bridge_experiment_id"] == full["eid"]
    body = get(client, f"{API}/evaluation/{full['evid']}/ranking", method="audience_bridge_score", metric="spearman")
    sc.EvaluationRowsResponse.model_validate(body)
    assert body["total"] == 4 and {i["reference_method"] for i in body["items"]} == \
        {"ppr_diffusion", "topic_similarity", "louvain", "node2vec"}
    assert get(client, f"{API}/evaluation/{full['evid']}/temporal_stability")["items"][0]["status"] == \
        "insufficient_temporal_data"
    perf = get(client, f"{API}/evaluation/{full['evid']}/performance", method="input_preparation")
    assert perf["total"] >= 1
    meta = get(client, f"{API}/evaluation/{full['evid']}/metadata")
    assert "labels_path" not in meta["config"] and "path" not in meta["labels"]
    assert get(client, f"{API}/evaluation/{full['evid']}/ranking", method="louvain", metric="mrr")["items"] == []


def test_invalid_filters_and_pagination(client, full):
    e = full["evid"]
    for url, params in [(f"{API}/evaluation/{e}/ranking", {"method": "magic"}),
                        (f"{API}/evaluation/{e}/top_k", {"metric": "spearman"}),
                        (f"{API}/evaluation/{e}/nonsense", {}),
                        (f"{API}/evaluation/not-an-id/ranking", {}),
                        (f"{API}/bridge/{A}/destinations", {"limit": 0}),
                        (f"{API}/bridge/{A}/destinations", {"limit": 101}),
                        (f"{API}/bridge/{A}/destinations", {"offset": -1}),
                        (f"{API}/channels", {"snapshot_id": "latest"}),
                        (f"{API}/bridge/{A}/destinations", {"experiment_id": "abs-xyz"})]:
        body = get(client, url, 422, **params)
        assert body["error"]["code"] == "invalid_parameter", url
    assert get(client, f"{API}/evaluation/eval-000000000000/ranking", 404)["error"]["code"] == "not_found"


# 11-13. empty data, storage failures, filtering -----------------------------------------------------

def test_empty_dataset(isolated_data_dir):
    c = TestClient(create_app(Settings()))
    for url in (f"{API}/channels", f"{API}/bridge/experiments", f"{API}/evaluation/runs", f"{API}/bridge/{A}/destinations"):
        assert get(c, url, 404)["error"]["code"] == "not_found"


def test_storage_failure_is_safe(client, monkeypatch):
    def boom(*a, **k):
        raise StorageError("artifact query failed (IOException)")
    monkeypatch.setattr(Component3Store, "query", boom)
    body = get(client, f"{API}/channels", 503)
    assert body["error"]["code"] == "storage_unavailable" and "IOException" not in json.dumps(body)

    def crash(*a, **k):
        raise RuntimeError(f"secret path C:/data and {RAW['G1']}")
    monkeypatch.setattr(Component3Store, "list_snapshots", crash)
    c = TestClient(create_app(Settings()), raise_server_exceptions=False)
    r = c.get(f"{API}/status")
    assert r.status_code == 500 and r.json() == {"error": {"code": "internal_error", "message": "an internal error occurred"}}


def test_corrupt_artifact_is_storage_error(tmp_path, monkeypatch):
    build_artifacts(tmp_path / "data", explain=False, evaluate=False)
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    for f in (tmp_path / "data").rglob("audience_bridge_scores.parquet"):
        f.write_bytes(b"not parquet")
    assert get(TestClient(create_app(Settings())), f"{API}/bridge/{A}/destinations", 503)["error"]["code"] == \
        "storage_unavailable"


def test_snapshot_and_experiment_filtering(client, full):
    explicit = get(client, f"{API}/bridge/{A}/destinations", snapshot_id=full["sid"], experiment_id=full["eid"])
    assert explicit["items"] == get(client, f"{API}/bridge/{A}/destinations")["items"]
    assert get(client, f"{API}/bridge/{A}/destinations", 404, experiment_id="abs-000000000000")["error"]["code"] == \
        "not_found"
    assert get(client, f"{API}/channels", 404, snapshot_id="rs-20990101T000000Z")["error"]["code"] == "not_found"
    exp = get(client, f"{API}/bridge/experiments")["items"][0]
    assert exp["explanation_ids"] == [full["xid"]] and exp["evaluation_ids"] == [full["evid"]] and exp["provisional"]


# 14-16. schemas, CORS, privacy -------------------------------------------------------------------------

def test_openapi_documents_every_endpoint(client):
    spec = get(client, "/openapi.json")
    paths = set(spec["paths"])
    assert {"/health", f"{API}/status", f"{API}/channels", f"{API}/channels/{{channel_id}}",
            f"{API}/channels/{{channel_id}}/pairs", f"{API}/bridge/experiments",
            f"{API}/bridge/{{source_channel_id}}/destinations",
            f"{API}/bridge/{{source_channel_id}}/destinations/{{destination_channel_id}}", f"{API}/evaluation/runs",
            f"{API}/evaluation/{{evaluation_id}}/metadata", f"{API}/evaluation/{{evaluation_id}}/{{table}}"} <= paths
    text = json.dumps(spec)
    assert "SUPABASE" not in text and "postgresql://" not in text and "ErrorResponse" in text


def test_cors_restricted_to_configured_origins(full, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(full["root"]))
    c = TestClient(create_app(Settings(cors_origins=("http://localhost:5173",))))
    ok = c.get("/health", headers={"Origin": "http://localhost:5173"})
    assert ok.headers.get("access-control-allow-origin") == "http://localhost:5173"
    bad = c.get("/health", headers={"Origin": "http://evil.example"})
    assert "access-control-allow-origin" not in bad.headers
    with pytest.raises(ConfigError):
        Settings(cors_origins=("*",))
    monkeypatch.setenv("API_CORS_ORIGINS", "https://a.example, https://b.example/")
    assert load_settings().cors_origins == ("https://a.example", "https://b.example")
    monkeypatch.setenv("API_MAX_PAGE_SIZE", "abc")
    with pytest.raises(ConfigError):
        load_settings()


def test_no_commenter_identifiers_in_any_response(client, full):
    urls = [f"{API}/status", f"{API}/channels", f"{API}/channels/{A}", f"{API}/channels/{A}/pairs",
            f"{API}/bridge/experiments", f"{API}/bridge/{A}/destinations?include_unscored=true",
            f"{API}/bridge/{A}/destinations/{C}", f"{API}/evaluation/runs",
            f"{API}/evaluation/{full['evid']}/metadata"] + \
        [f"{API}/evaluation/{full['evid']}/{t}?limit=100" for t in ("ranking", "top_k", "temporal_stability",
                                                                    "sparse_robustness", "performance")]
    blob = "".join(client.get(u).text for u in urls)
    assert "anon_" not in blob and not any(v in blob for v in RAW.values()) and not any(v in blob for v in P.values())
    assert "commenter:" not in blob


def test_identifier_guard_blocks_leaks(client, monkeypatch):
    real = svc_mod.Component3Service.list_channels

    def leaky(self, sid):
        out = real(self, sid)
        out["items"][0]["channel_name"] = P["G1"]
        return svc_mod._clean(out)
    monkeypatch.setattr(svc_mod.Component3Service, "list_channels", leaky)
    body = get(client, f"{API}/channels", 500)
    assert body["error"]["code"] == "internal_error" and "anon_" not in json.dumps(body)


# 17. research modules unaffected / folder contract ---------------------------------------------------

def test_artifact_layout_matches_research_modules():
    from research.component_3.evaluation import evaluate as ev
    from research.component_3.explainability import explain as ex
    from research.component_3.model import audience_bridge as ab
    from research.component_3.model import baselines as bl
    from research.component_3.model import ppr_diffusion as ppr
    from research.component_3.model import topic_similarity as ts
    from research.component_3.preprocessing import graph_features as gf
    from research.component_3.preprocessing import hetero_graph as hg

    assert (store_mod.BRIDGE_DIR, store_mod.BRIDGE_RUN) == (ab.BRIDGE_DIR, ab.RUN_FILE)
    assert (store_mod.EVALUATION_DIR, store_mod.EVALUATION_META) == (ev.EVALUATION_DIR, ev.METADATA_FILE)
    assert (store_mod.EXPLANATIONS_DIR, store_mod.EXPLANATION_META) == (ex.EXPLANATIONS_DIR, ex.METADATA_FILE)
    assert store_mod.DIFFUSION_DIR == ppr.DIFFUSION_DIR and store_mod.BASELINES_DIR == bl.BASELINES_DIR
    assert store_mod.TOPICS_DIR == ts.TOPICS_DIR and store_mod.FEATURES_DIR == gf.FEATURES_DIR
    assert store_mod.GRAPH_DIR == hg.graph_dir("rs-20260101T000000Z").name
    assert set(svc_mod.EVAL_TABLES.values()) == set(ev.DETERMINISTIC_TABLES) | {"computational_performance_results"}


def test_api_reads_do_not_modify_artifacts(client, full):
    before = {p: p.stat().st_mtime_ns for p in Path(full["root"]).rglob("*") if p.is_file()}
    for u in (f"{API}/status", f"{API}/bridge/{A}/destinations/{C}", f"{API}/evaluation/{full['evid']}/ranking"):
        client.get(u)
    after = {p: p.stat().st_mtime_ns for p in Path(full["root"]).rglob("*") if p.is_file()}
    assert before == after
