"""Offline end-to-end integration test of Component 3 (STEP 25).

TEST DATA (synthetic, never real YouTube data): API-shaped channel / video / comment resources
for channels A-F and X. A, B, C (cricket) share commenters G1-G4; D, E (cooking) share H1-H3;
F has one own commenter; X has no videos. Results below are pipeline checks, NOT findings.

Path exercised (every stage runs real project code; nothing is skipped silently):
  collector record mapping (+ pseudonymization) -> PostgreSQL research schema (throwaway local
  server standing in for Supabase) -> research snapshots (Parquet) -> DuckDB preparation ->
  topic clusters -> heterogeneous graph with topic nodes -> features -> metapath2vec -> HGT ->
  PPR diffusion -> topic similarity -> confidence-weighted Audience Bridge Score
  (diffusion + embedding + topic) -> Louvain / node2vec -> evaluation ->
  explanations -> FastAPI -> React (TypeScript) data contracts.

Blocked-stage policy: without PostgreSQL server tools the `db` fixture skips the whole test
explicitly (pytest reports it as SKIPPED); no stage is ever reported as passed without running.
"""

import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from shared.data_collection.channel_collector import to_channel_record
from shared.data_collection.comment_collector import VideoRef, to_comment_record
from shared.data_collection.video_collector import to_video_record
from shared.database import repository as repo
from shared.database.snapshot_export import export_research_snapshot
from shared.utils import privacy
from shared.utils import snapshots as s

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "component_3"))
from test_evaluation import FakeEncoder  # noqa: E402  (keyword test encoder, no model download)

ROOT = Path(__file__).resolve().parents[2]
API = "/api/v1/component-3"
CH = {k: f"UC_e2e_{k}" for k in "ABCDEFX"}
TOPIC = {"A": "Cricket", "B": "Cricket", "C": "Cricket", "D": "Cooking", "E": "Cooking", "F": "Cooking", "X": "Cricket"}
VIDEOS = {"A1": "A", "A2": "A", "B1": "B", "C1": "C", "D1": "D", "E1": "E", "F1": "F"}
RAW = {w: f"UC_raw_e2e_commenter_{w}" for w in ["G1", "G2", "G3", "G4", "H1", "H2", "H3", "F9"]}  # TEST raw ids
FIRST = [("G1", "A1"), ("G1", "B1"), ("G2", "B1"), ("G2", "C1"), ("G3", "A2"), ("G3", "C1"), ("G4", "A1"),
         ("G4", "B1"), ("G4", "C1"), ("H1", "D1"), ("H1", "E1"), ("H2", "D1"), ("H2", "E1"), ("H3", "E1"),
         ("F9", "F1")]
LATER = [("H3", "D1"), ("G1", "C1"), ("G2", "A2")]   # new comments before the second snapshot
COLLECTED = datetime(2026, 9, 30, 8, 0, tzinfo=timezone.utc)


def channel_item(k):
    return {"id": CH[k], "snippet": {"title": f"E2E Channel {k}", "description": "Synthetic.",
                                     "publishedAt": "2020-01-01T00:00:00Z"},
            "statistics": {"subscriberCount": "1000", "viewCount": "50000", "videoCount": "4"}}


def video_item(vid, k):
    return {"id": vid, "snippet": {"channelId": CH[k], "title": f"{TOPIC[k]} episode {vid}",
                                   "description": f"{TOPIC[k]} programme.", "publishedAt": "2026-09-01T00:00:00Z",
                                   "tags": [TOPIC[k].lower()]},
            "statistics": {"viewCount": "100", "likeCount": "5", "commentCount": "3"},
            "contentDetails": {"duration": "PT10M"}}


def comment_item(i, who, vid):
    day = f"2026-09-{(i % 25) + 2:02d}T10:00:00Z"
    return {"id": f"e2e_c{i}", "snippet": {"videoId": vid, "textDisplay": "Synthetic comment.", "publishedAt": day,
                                          "updatedAt": day, "likeCount": 0, "authorDisplayName": "Test",
                                          "authorChannelId": {"value": RAW[who]}}}


def comments(pairs, start):
    key = privacy.get_salt()
    return [to_comment_record(comment_item(start + i, w, v), VideoRef(v, CH[VIDEOS[v]]), None, key, COLLECTED)
            for i, (w, v) in enumerate(pairs)]


@pytest.fixture
def ticking(monkeypatch):
    times = iter(datetime(2026, 10, 9, 10, 0, tzinfo=timezone.utc) + timedelta(seconds=i) for i in range(3000))
    monkeypatch.setattr(s, "_utcnow", lambda: next(times))


def ts_interfaces() -> dict[str, set[str]]:
    """Field names of every exported interface in the dashboard's Component 3 contract."""
    text = (ROOT / "frontend/src/features/component_3/types.ts").read_text(encoding="utf-8")
    raw = {m.group(1): (m.group(2), set(re.findall(r"^\s+(\w+)\??:", m.group(3), re.M)))
           for m in re.finditer(r"export interface (\w+)(?: extends (\w+))? \{(.*?)\n\}", text, re.S)}

    def resolve(name):
        parent, fields = raw[name]
        return fields | (resolve(parent) if parent else set())
    return {n: resolve(n) for n in raw}


def test_component3_end_to_end(db, isolated_data_dir, ticking):
    from backend.config import Settings
    from backend.main import create_app
    from research.component_3.evaluation import evaluate as ev
    from research.component_3.explainability import explain as ex
    from research.component_3.model import audience_bridge as ab
    from research.component_3.model import baselines as bl
    from research.component_3.model import hgt
    from research.component_3.model import metapath2vec as m2v
    from research.component_3.model import ppr_diffusion as ppr
    from research.component_3.model import topic_similarity as ts
    from research.component_3.preprocessing import graph_features as gf
    from research.component_3.preprocessing import hetero_graph as hg
    from research.component_3.preprocessing import research_dataset as rd

    stages = []

    # 1-2. collector mapping -> shared research database (PostgreSQL research schema)
    repo.upsert_channels(db, [to_channel_record(channel_item(k), COLLECTED) for k in CH])
    repo.upsert_videos(db, [to_video_record(video_item(v, k), COLLECTED) for v, k in VIDEOS.items()])
    first = comments(FIRST, 0)
    assert all(privacy.is_pseudonymized(c["author_channel_id"]) for c in first)       # before persistence
    repo.upsert_comments(db, first)
    db.commit()
    assert repo.count_rows(db, "comments") == len(FIRST)
    stages.append("collect+database")

    # 3. reproducible Parquet research snapshots (an earlier and a later one, same collection depth)
    earlier = export_research_snapshot(db).snapshot_id
    repo.upsert_comments(db, comments(LATER, 100))
    db.commit()
    sid = export_research_snapshot(db).snapshot_id
    assert earlier != sid and s.verify_research_snapshot(earlier).ok and s.verify_research_snapshot(sid).ok
    assert s.get_research_snapshot(sid).row_counts["comments"] == len(FIRST) + len(LATER)
    stages.append("parquet snapshots")

    # 4. DuckDB preparation / validation
    report = rd.prepare(sid, export=False, save_report=False)
    assert report.research_ready and report.quality_status == "VALID"
    stages.append("duckdb validation")

    # 5-6. topic clusters (STEP 18) -> heterogeneous graph WITH topic nodes -> features (as by their CLIs)
    snap_time = gf._snapshot_time(s.get_research_snapshot(sid))
    topic_cfg = ts.TopicConfig(n_topics=2)
    ts.save(ts.run(sid, topic_cfg, as_of=snap_time, encoder=FakeEncoder()))
    graph = hg.build_graph(sid, **dict(zip(("topics", "video_topics"), hg.load_topic_assignments(sid))))
    hg.save_graph(graph)
    assert set(graph.nodes["node_type"]) == {"commenter", "video", "channel", "topic"}
    assert (graph.edges["relation"] == "has_topic").sum() == len(VIDEOS)
    fs = gf.build_features(sid, graph=graph)
    gf.save_features(fs)
    stages.append("graph+features")

    # 7. representation learning: metapath2vec (primary) and HGT (alternative)
    emb = m2v.train(graph, m2v.Config(walks_per_node=3, walk_length=10, dimensions=8, window=2, negative=2,
                                      epochs=2, seed=7))
    m2v.save_embeddings(emb)
    assert emb.snapshot_id == sid and len(emb.nodes) > 0
    assert emb.metadata["walks"]["per_metapath"]["VTV"]["walks"] > 0        # topic metapath used
    h_emb, model = hgt.train(graph, hgt.HGTConfig(hidden=8, layers=1, heads=2, dropout=0.0, epochs=3,
                                                  negatives_per_positive=2, validation_fraction=0.25,
                                                  min_validation_edges=2, seed=3))
    hgt.save(h_emb, model)
    assert h_emb.snapshot_id == sid
    stages.append("metapath2vec+hgt")

    # 8-10. diffusion, topic similarity, confidence-weighted Audience Bridge Score from SAVED components
    inp = bl.load_input(sid)
    assert "has_topic" not in set(ppr.build_diffusion_graph(inp.graph).edges["relation"])   # no double counting
    diffusion = ppr.run_diffusion(inp.graph)
    ppr.save_run(diffusion)
    topic = ts.run(sid, topic_cfg, as_of=inp.as_of, encoder=FakeEncoder())
    ts.save(topic)
    bridge = ab.score(inp, ppr.load_run(ppr.diffusion_dir(sid, diffusion.experiment_id)),
                      ts.load(ts.topics_dir(sid, topic.experiment_id)), ab.BridgeConfig(),
                      m2v.load_embeddings(m2v.embeddings_dir(sid, emb.experiment_id)))
    assert bridge.scores.equals(ab.run(sid, encoder=FakeEncoder(), inp=inp, topic_config=topic_cfg).scores)
    assert bridge.metadata["inputs"]["embedding_experiment_id"] == emb.experiment_id   # saved embeddings reused
    ab.save(bridge)
    sc = bridge.scores
    assert (sc.source_channel_id != sc.destination_channel_id).all()
    ok = sc[sc.score_status == "ok"]
    assert ((ok.diffusion_contribution + ok.embedding_contribution + ok.topic_contribution) * ok.confidence
            - ok.audience_bridge_score).abs().max() < 1e-12                          # three-component formula
    assert (ok.embedding_contribution > 0).any()
    top_a = sc[(sc.source_channel_id == f"channel:{CH['A']}") & (sc["rank"] == 1)].destination_channel_id.iloc[0]
    assert top_a in (f"channel:{CH['B']}", f"channel:{CH['C']}")
    stages.append("ppr+topic+abs")

    # 11. baselines (persisted)
    bl.save_louvain(bl.run_louvain(inp))
    bl.save_node2vec(bl.run_node2vec(inp, bl.Node2VecConfig(dimensions=8, walk_length=10, walks_per_node=3, window=2,
                                                            negative=2, epochs=2, seed=5)))
    stages.append("baselines")

    # 12. evaluation (agreement, top-k, temporal, one seeded sparse simulation, performance)
    evaluation = ev.evaluate(sid, ev.EvaluationConfig(sparse_fractions=(0.5,), sparse_seeds=(0,)),
                             encoder=FakeEncoder(), topic_config=topic_cfg, node2vec_config=bl.Node2VecConfig(
                                 dimensions=8, walk_length=10, walks_per_node=3, window=2, negative=2, epochs=2, seed=5))
    ev.save(evaluation)
    assert evaluation.metadata["methods"]["audience_bridge_score"]["experiment_id"] == bridge.experiment_id
    assert evaluation.metadata["methods"]["metapath2vec_similarity"]["experiment_id"] == emb.experiment_id
    assert evaluation.metadata["methods"]["hgt_similarity"]["experiment_id"] == h_emb.experiment_id
    assert evaluation.metadata["temporal"]["comparable_pairs"] == 1                  # earlier -> later snapshot
    rel = evaluation.tables["ranking_evaluation_results"]
    assert set(rel[rel.analysis == "relevance"].status) == {"not_computed"}           # no labels, no metrics
    assert s.verify_research_snapshot(sid).ok                                         # simulations isolated
    stages.append("evaluation")

    # 13. explanations
    explanation = ex.explain(bridge)
    ex.save(explanation)
    assert explanation.metadata["evaluation_context"]["evaluations_of_this_experiment"][0]["evaluation_id"] == \
        evaluation.evaluation_id
    stages.append("explainability")

    # 14. FastAPI reads the artifacts
    client = TestClient(create_app(Settings()))
    status = client.get(f"{API}/status").json()
    assert {a["name"]: a["status"] for a in status["artifacts"]} == {
        n: "available" for n in ("heterogeneous_graph", "graph_features", "ppr_diffusion", "topic_similarity",
                                 "baseline_louvain", "baseline_node2vec", "audience_bridge_scores",
                                 "explanations", "evaluations")}
    responses = {
        "HealthResponse": client.get("/health").json(),
        "ResearchStatusResponse": status,
        "ChannelListResponse": client.get(f"{API}/channels").json(),
        "ChannelDetailResponse": client.get(f"{API}/channels/{CH['A']}").json(),
        "ChannelPairListResponse": client.get(f"{API}/channels/{CH['A']}/pairs").json(),
        "BridgeExperimentListResponse": client.get(f"{API}/bridge/experiments").json(),
        "BridgeRankingResponse": client.get(f"{API}/bridge/{CH['A']}/destinations", params={"limit": 100}).json(),
        "BridgePairResponse": client.get(f"{API}/bridge/{CH['A']}/destinations/{CH['B']}").json(),
        "EvaluationRunListResponse": client.get(f"{API}/evaluation/runs").json(),
        "EvaluationMetadataResponse": client.get(f"{API}/evaluation/{evaluation.evaluation_id}/metadata").json(),
        "EvaluationRowsResponse": client.get(f"{API}/evaluation/{evaluation.evaluation_id}/sparse_robustness").json(),
    }
    ranking = responses["BridgeRankingResponse"]
    assert ranking["experiment_id"] == bridge.experiment_id and ranking["snapshot_id"] == sid
    assert all(i["destination_channel_id"] != CH["A"] for i in ranking["items"])
    pair = responses["BridgePairResponse"]
    stored = sc[(sc.source_channel_id == f"channel:{CH['A']}") & (sc.destination_channel_id == f"channel:{CH['B']}")].iloc[0]
    assert pair["audience_bridge_score"] == pytest.approx(float(stored.audience_bridge_score))
    assert pair["explanation_status"] == "available" and pair["explanation_id"] == explanation.explanation_id
    assert responses["EvaluationRowsResponse"]["total"] > 0
    stages.append("fastapi")

    # 15. React dashboard contract: every response has exactly the fields the TypeScript types declare
    types = ts_interfaces()
    nested = {"ResearchStatusResponse": {"snapshots": "SnapshotSummary", "artifacts": "ArtifactStatus"},
              "ChannelListResponse": {"items": "ChannelSummary"}, "ChannelPairListResponse": {"items": "ChannelPair"},
              "BridgeExperimentListResponse": {"items": "BridgeExperiment"},
              "BridgeRankingResponse": {"items": "BridgeDestination"},
              "EvaluationRunListResponse": {"items": "EvaluationRun"}}
    for name, body in responses.items():
        assert set(body) == types[name], name
        for field, item_type in nested.get(name, {}).items():
            assert body[field], f"{name}.{field} is empty"
            assert all(set(item) == types[item_type] for item in body[field]), f"{name}.{field}"
    assert set(pair["score_breakdown"]) == types["ScoreBreakdown"]
    assert set(pair["evidence_summary"]) == types["EvidenceSummary"]
    assert set(pair["ranking_context"]) == types["RankingContext"]
    assert all(set(r) == types["ExplanationReason"] for r in pair["explanation_reasons"])
    stages.append("dashboard contract")

    # privacy across every persisted artifact and API response
    pseudonyms = [privacy.pseudonymize_id(r, privacy.get_salt()) for r in RAW.values()]
    for path in Path(isolated_data_dir).rglob("*"):
        if not path.is_file():
            continue
        text = pd.read_parquet(path).to_csv() if path.suffix == ".parquet" else path.read_text(encoding="utf-8", errors="ignore")
        assert not any(r in text for r in RAW.values()), f"raw commenter id in {path.name}"
    api_text = json.dumps(responses)
    assert not any(p in api_text for p in pseudonyms) and "anon_" not in api_text
    stages.append("privacy")

    assert stages == ["collect+database", "parquet snapshots", "duckdb validation", "graph+features",
                      "metapath2vec+hgt", "ppr+topic+abs", "baselines", "evaluation", "explainability", "fastapi",
                      "dashboard contract", "privacy"]


def test_typescript_contract_matches_backend_schemas():
    """The dashboard's TypeScript interfaces mirror the backend's Pydantic response models."""
    from backend.api.component_3 import schemas

    types = ts_interfaces()
    checked = 0
    for name, fields in types.items():
        model = getattr(schemas, name, None)
        if model is not None:
            assert set(model.model_fields) == fields, name
            checked += 1
    assert checked >= 20
