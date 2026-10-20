/** Component 3 live results (backend/api/component_3/live_routes.py): published nightly, read-only. */
import { getJson, hasKeys, isList, type Validator } from "../../services/apiClient";

const BASE = "/api/v1/component-3/live";

export interface LiveRun {
  run_id: string;
  started_at: string;
  finished_at: string | null;
  status: "running" | "completed" | "failed";
  window_start: string;
  window_end: string;
  snapshot_id: string | null;
  experiment_id: string | null;
  channels: number | null;
  videos: number | null;
  comments: number | null;
  unique_commenters: number | null;
  quota_units: number | null;
  error: string | null;
}

export interface LiveBridge {
  source_channel_id: string;
  destination_channel_id: string;
  source_channel_name: string | null;
  destination_channel_name: string | null;
  audience_bridge_score: number | null;
  base_score: number | null;
  diffusion_component: number | null;
  embedding_component: number | null;
  topic_component: number | null;
  confidence: number | null;
  shared_commenters: number | null;
  rank: number | null;
  score_status: string;
}

export interface LiveChannel {
  channel_id: string;
  channel_name: string | null;
  videos: number;
  comments: number;
  unique_commenters: number;
}

export interface LiveBridgesResponse {
  run: LiveRun;
  items: LiveBridge[];
  channels: LiveChannel[];
  pairs_with_evidence: number;
  pairs: number;
  note: string;
}

export interface LiveHistoryPoint {
  run_id: string;
  finished_at: string;
  audience_bridge_score: number | null;
  confidence: number | null;
  shared_commenters: number | null;
  rank: number | null;
}

const shape =
  <T>(keys: string[], lists: string[] = []): Validator<T> =>
  (d: unknown): d is T =>
    hasKeys(d, keys) && lists.every((k) => isList(d[k]));

export const liveApi = {
  runs: (limit: number, signal?: AbortSignal) =>
    getJson<{ items: LiveRun[]; latest_completed_run_id: string | null; note: string }>(`${BASE}/runs`, { limit },
      shape(["items", "latest_completed_run_id"], ["items"]), signal),
  bridges: (limit: number, signal?: AbortSignal) =>
    getJson<LiveBridgesResponse>(`${BASE}/bridges`, { limit }, shape(["run", "items", "channels"], ["items", "channels"]), signal),
  history: (source: string, destination: string, signal?: AbortSignal) =>
    getJson<{ items: LiveHistoryPoint[] }>(`${BASE}/history`, { source, destination }, shape(["items"], ["items"]), signal),
};
