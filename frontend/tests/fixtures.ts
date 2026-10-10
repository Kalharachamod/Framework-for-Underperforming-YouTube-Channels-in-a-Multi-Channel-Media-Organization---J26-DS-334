/**
 * TEST DATA ONLY: synthetic API responses shaped exactly like the STEP 23 backend contracts.
 * Channel ids, names and numbers are invented for automated tests and are not research results.
 */
import { vi } from "vitest";

export const SID = "rs-20260101T000000Z";
export const EID = "abs-aaaaaaaaaaaa";
export const EVID = "eval-bbbbbbbbbbbb";
export const XID = "xpl-cccccccccccc";
export const A = "UC_test_A";
export const B = "UC_test_B";
export const C = "UC_test_C";

export const status = (overrides: Record<string, unknown> = {}) => ({
  research_data: "available",
  snapshots: [{ snapshot_id: SID, created_at: "2026-01-01T00:00:00Z", extracted_at: "2026-01-01T00:00:00Z", channels: 3, videos: 6, comments: 40 }],
  latest_snapshot_id: SID,
  snapshot_id: SID,
  artifacts: [
    { name: "heterogeneous_graph", status: "available", count: 1, latest_id: null, detail: "STEP 13" },
    { name: "baseline_louvain", status: "missing", count: 0, latest_id: null, detail: "STEP 20" },
    { name: "baseline_node2vec", status: "missing", count: 0, latest_id: null, detail: "STEP 20" },
    { name: "audience_bridge_scores", status: "available", count: 1, latest_id: EID, detail: "STEP 19 (provisional formula)" },
    { name: "explanations", status: "available", count: 1, latest_id: XID, detail: "STEP 22" },
    { name: "evaluations", status: "available", count: 1, latest_id: EVID, detail: "STEP 21" },
  ],
  note: "Each artifact is reported separately; a healthy API does not imply that all artifacts exist.",
  ...overrides,
});

export const channels = {
  snapshot_id: SID,
  features_status: "available",
  total: 3,
  items: [
    { channel_id: A, channel_name: "Test Channel A", observed_subscriber_count: 100, stored_video_count: 2, unique_commenter_count: 5, comment_count: 9 },
    { channel_id: B, channel_name: "Test Channel B", observed_subscriber_count: null, stored_video_count: 2, unique_commenter_count: 4, comment_count: 7 },
    { channel_id: C, channel_name: "Test Channel C", observed_subscriber_count: 50, stored_video_count: 2, unique_commenter_count: 3, comment_count: 6 },
  ],
};

export const experiments = {
  snapshot_id: SID,
  items: [{ experiment_id: EID, snapshot_id: SID, created_at: "2026-01-02T00:00:00Z", method_version: "1.0-provisional", provisional: true, w_diffusion: 0.25, w_topic: 0.25, confidence_k: 3, pairs: 6, scored_pairs: 6, explanation_ids: [XID], evaluation_ids: [EVID], w_embedding: 0.5, embedding_source: "metapath2vec", embedding_experiment_id: "m2v-eeeeeeeeeeee" }],
};

export const ranking = (source = A) => ({
  total: 2, limit: 10, offset: 0, snapshot_id: SID, experiment_id: EID, source_channel_id: source,
  source_channel_name: "Test Channel A", include_unscored: false, note: "Potential audience bridge signals.",
  items: [
    { rank: 1, destination_channel_id: C, destination_channel_name: "Test Channel C", audience_bridge_score: 0.4321, diffusion_component: 0.5, embedding_component: 0.1, topic_component: 0.2, confidence_component: 0.54, base_score: 0.8, score_status: "ok" },
    { rank: 2, destination_channel_id: B, destination_channel_name: "Test Channel B", audience_bridge_score: 0.1234, diffusion_component: 0.2, embedding_component: 0.05, topic_component: 0.05, confidence_component: 0.41, base_score: 0.3, score_status: "ok" },
  ],
});

export const pair = (overrides: Record<string, unknown> = {}) => ({
  snapshot_id: SID, experiment_id: EID, source_channel_id: A, source_channel_name: "Test Channel A",
  destination_channel_id: C, destination_channel_name: "Test Channel C", rank: 1, audience_bridge_score: 0.4321, score_status: "ok",
  score_breakdown: { raw_diffusion_score: 0.0123, normalized_diffusion: 1, raw_embedding_similarity: 0.7, normalized_embedding_similarity: 0.2, raw_topic_similarity: 0.9, normalized_topic_similarity: 0.8, w_diffusion: 0.5, w_embedding: 0.5, w_topic: 0.25, embedding_source: "metapath2vec", diffusion_component: 0.5, embedding_component: 0.1, topic_component: 0.2, base_score: 0.8, shared_commenters: 4, evidence_confidence: 0.5714, topic_coverage_confidence: 0.945, confidence_component: 0.54, formula: "audience_bridge_score = (diffusion_component + topic_component) x confidence_component" },
  explanation_status: "available", explanation_detail: null, explanation_id: XID, explanation_config_id: "xcfg-dddddddddddd", explanation_outcome: "complete",
  explanation_text: "Test explanation.",
  evidence_summary: { shared_commenters: 4, shared_commenter_state: "observed", jaccard_similarity: 0.25, directional_overlap_source_to_destination: 0.8, shared_comments_on_source: 6, shared_comments_on_destination: 5, shared_videos_on_source: 2, shared_videos_on_destination: 1, source_video_coverage: 1, destination_video_coverage: 0.5, video_coverage_state: "observed", shared_active_days: 0, shared_first_comment_at: null, shared_last_comment_at: null, temporal_state: "zero", topic_similarity: null, topic_state: "missing", embedding_similarity: 0.7, embedding_state: "observed" },
  explanation_reasons: [{ reason_code: "strong_structural_connectivity", reason_text: "Strong structural connectivity (test).", criterion: "rank <= ceil(0.25 * candidates)", value: 1, threshold: 1 }],
  uncertainty_notes: ["no labelled evaluation of this experiment: the score is not empirically validated"],
  ranking_context: { candidate_destinations: 2, scored_destinations: 2, score_percentile: 1, next_higher_destination_id: null, next_higher_score: null, next_lower_destination_id: B, next_lower_score: 0.1234 },
  note: "Potential audience bridge signals.",
  ...overrides,
});

export const evaluationRuns = { snapshot_id: SID, items: [{ evaluation_id: EVID, snapshot_id: SID, created_at: "2026-01-03T00:00:00Z", methods: { audience_bridge_score: "ok", louvain: "ok", node2vec: "ok" }, audience_bridge_experiment_id: EID, labels_status: "none supplied", temporal_status: "insufficient_temporal_data", sparse_runs: 0 }] };

export const evaluationMeta = {
  evaluation_id: EVID, snapshot_id: SID, created_at: "2026-01-03T00:00:00Z", graph_fingerprint: "f", as_of: "2026-01-01T00:00:00Z",
  config: { ks: [1, 3] }, methods: { audience_bridge_score: { status: "ok", role: "proposed method", experiment_id: EID, reason: null }, louvain: { status: "ok", role: "baseline", experiment_id: "louvain-1", reason: null }, node2vec: { status: "ok", role: "baseline", experiment_id: "node2vec-1", reason: null } },
  proposed_method: { method: "audience_bridge_score", status: "ok", note: null }, labels: { status: "none supplied" },
  temporal: { status: "insufficient_temporal_data", reason: "fewer than 2 research snapshots" }, sparse_robustness: { status: "skipped" },
  performance: { memory_note: "tracemalloc peak (test)", total_seconds: 1 }, interpretation: "Consistency, not correctness.", versions: {},
};

const rows = (table: string, items: Record<string, unknown>[], columns: string[]) => ({ evaluation_id: EVID, snapshot_id: SID, table, columns, total: items.length, limit: 100, offset: 0, items, note: "test" });

export const evaluationTables: Record<string, unknown> = {
  ranking: rows("ranking", [
    { analysis: "relevance", method: "audience_bridge_score", reference_method: null, metric: null, k: null, value: null, n_sources: 0, status: "not_computed", reason: "no explicit relevance labels supplied" },
    { analysis: "agreement", method: "audience_bridge_score", reference_method: "louvain", metric: "spearman", k: null, value: 0.3141, n_sources: 2, status: "ok", reason: null },
    { analysis: "agreement", method: "audience_bridge_score", reference_method: "node2vec", metric: "spearman", k: null, value: -0.2718, n_sources: 2, status: "ok", reason: null },
    { analysis: "top_k_summary", method: "louvain", reference_method: null, metric: "topk_distinct_destinations", k: 1, value: 2, n_sources: 2, status: "ok", reason: null },
  ], ["analysis", "method", "reference_method", "metric", "k", "value", "n_sources", "status", "reason"]),
  top_k: rows("top_k", [{ method: "audience_bridge_score", source_channel_id: A, rank: 1, destination_channel_id: C, score: 0.4321, tied: false }], ["method"]),
  temporal_stability: rows("temporal_stability", [{ method: "audience_bridge_score", status: "insufficient_temporal_data", reason: "fewer than 2 research snapshots", value: null }], ["method"]),
  sparse_robustness: rows("sparse_robustness", [], ["method"]),
  performance: rows("performance", [{ stage: "main", method: "louvain", status: "ok", seconds: 0.5, python_heap_peak_mib: 1.2, graph_nodes: 10, graph_edges: 20 }], ["stage"]),
};

export type Handler = (url: URL) => { status?: number; body: unknown } | undefined;

/** Install a fetch mock answering from route handlers (unknown route -> 404 not_found). */
export function mockFetch(handler: Handler) {
  const fn = vi.fn(async (input: RequestInfo | URL) => {
    const url = new URL(String(input));
    const res = handler(url) ?? { status: 404, body: { error: { code: "not_found", message: `no mock for ${url.pathname}` } } };
    return new Response(JSON.stringify(res.body), { status: res.status ?? 200, headers: { "Content-Type": "application/json" } });
  });
  vi.stubGlobal("fetch", fn);
  return fn;
}

/** Default routes for a fully populated synthetic backend. */
export function defaultRoutes(overrides: Partial<Record<string, unknown>> = {}): Handler {
  return (url) => {
    const p = url.pathname.replace("/api/v1/component-3", "");
    const pick = (key: string, value: unknown) => ({ body: key in overrides ? overrides[key] : value });
    if (url.pathname === "/health") return pick("health", { status: "ok", service: "Test API", version: "1.0.0", time: "2026-01-01T00:00:00Z" });
    if (p === "/status") return pick("status", status());
    if (p === "/channels") return pick("channels", channels);
    if (p === "/bridge/experiments") return pick("experiments", experiments);
    if (/^\/bridge\/[^/]+\/destinations$/.test(p)) return pick("ranking", ranking(decodeURIComponent(p.split("/")[2])));
    if (/^\/bridge\/[^/]+\/destinations\/[^/]+$/.test(p)) return pick("pair", pair());
    if (p === "/evaluation/runs") return pick("evaluationRuns", evaluationRuns);
    if (p.endsWith("/metadata")) return pick("evaluationMeta", evaluationMeta);
    const table = p.match(/^\/evaluation\/[^/]+\/([a-z_]+)$/)?.[1];
    if (table) return pick(`table:${table}`, evaluationTables[table]);
    return undefined;
  };
}
