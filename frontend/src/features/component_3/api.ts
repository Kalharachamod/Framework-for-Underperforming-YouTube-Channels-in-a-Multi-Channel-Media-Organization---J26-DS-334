/** Component 3 endpoints (paths and parameters exactly as in backend/api/component_3/routes.py). */
import { getJson, hasKeys, isList, type Params, type Validator } from "../../services/apiClient";
import type {
  BridgeExperimentListResponse,
  BridgePairResponse,
  BridgeRankingResponse,
  ChannelDetailResponse,
  ChannelListResponse,
  ChannelPairListResponse,
  EvaluationMetadataResponse,
  EvaluationRowsResponse,
  EvaluationRunListResponse,
  EvaluationTable,
  HealthResponse,
  ResearchStatusResponse,
} from "./types";

const BASE = "/api/v1/component-3";
export const MAX_PAGE = 100;

const shape =
  <T>(keys: string[], lists: string[] = []): Validator<T> =>
  (d: unknown): d is T =>
    hasKeys(d, keys) && lists.every((k) => isList(d[k]));

const enc = encodeURIComponent;

export interface Context {
  snapshotId?: string | null;
  experimentId?: string | null;
}

const ctx = (c: Context = {}): Params => ({ snapshot_id: c.snapshotId, experiment_id: c.experimentId });
const snap = (c: Context = {}): Params => ({ snapshot_id: c.snapshotId });

export const component3Api = {
  health: (signal?: AbortSignal) =>
    getJson<HealthResponse>("/health", {}, shape(["status", "version"]), signal),

  status: (c: Context, signal?: AbortSignal) =>
    getJson<ResearchStatusResponse>(`${BASE}/status`, snap(c), shape(["research_data", "artifacts"], ["artifacts", "snapshots"]), signal),

  channels: (c: Context, signal?: AbortSignal) =>
    getJson<ChannelListResponse>(`${BASE}/channels`, snap(c), shape(["snapshot_id", "items"], ["items"]), signal),

  channel: (channelId: string, c: Context, signal?: AbortSignal) =>
    getJson<ChannelDetailResponse>(`${BASE}/channels/${enc(channelId)}`, snap(c), shape(["channel_id", "snapshot_id"]), signal),

  channelPairs: (channelId: string, c: Context, limit: number, offset: number, signal?: AbortSignal) =>
    getJson<ChannelPairListResponse>(
      `${BASE}/channels/${enc(channelId)}/pairs`,
      { ...snap(c), limit, offset },
      shape(["items", "total"], ["items"]),
      signal,
    ),

  experiments: (c: Context, signal?: AbortSignal) =>
    getJson<BridgeExperimentListResponse>(`${BASE}/bridge/experiments`, snap(c), shape(["snapshot_id", "items"], ["items"]), signal),

  ranking: (source: string, c: Context, limit: number, offset: number, includeUnscored: boolean, signal?: AbortSignal) =>
    getJson<BridgeRankingResponse>(
      `${BASE}/bridge/${enc(source)}/destinations`,
      { ...ctx(c), limit, offset, include_unscored: includeUnscored },
      shape(["items", "total", "experiment_id", "snapshot_id"], ["items"]),
      signal,
    ),

  pair: (source: string, destination: string, c: Context, signal?: AbortSignal) =>
    getJson<BridgePairResponse>(
      `${BASE}/bridge/${enc(source)}/destinations/${enc(destination)}`,
      ctx(c),
      shape(["score_breakdown", "explanation_status", "experiment_id"], ["explanation_reasons", "uncertainty_notes"]),
      signal,
    ),

  evaluationRuns: (c: Context, signal?: AbortSignal) =>
    getJson<EvaluationRunListResponse>(`${BASE}/evaluation/runs`, snap(c), shape(["items"], ["items"]), signal),

  evaluationMetadata: (evaluationId: string, c: Context, signal?: AbortSignal) =>
    getJson<EvaluationMetadataResponse>(
      `${BASE}/evaluation/${enc(evaluationId)}/metadata`,
      snap(c),
      shape(["evaluation_id", "methods"]),
      signal,
    ),

  evaluationRows: (
    evaluationId: string,
    table: EvaluationTable,
    c: Context,
    filters: { method?: string; metric?: string; limit?: number; offset?: number },
    signal?: AbortSignal,
  ) =>
    getJson<EvaluationRowsResponse>(
      `${BASE}/evaluation/${enc(evaluationId)}/${table}`,
      { ...snap(c), method: filters.method, metric: filters.metric, limit: filters.limit ?? MAX_PAGE, offset: filters.offset ?? 0 },
      shape(["items", "total", "columns"], ["items", "columns"]),
      signal,
    ),

  /** All rows of an evaluation table, following pages (bounded to 20 pages). */
  async evaluationAllRows(
    evaluationId: string,
    table: EvaluationTable,
    c: Context,
    filters: { method?: string; metric?: string },
    signal?: AbortSignal,
  ): Promise<EvaluationRowsResponse> {
    const first = await component3Api.evaluationRows(evaluationId, table, c, { ...filters, limit: MAX_PAGE }, signal);
    const items = [...first.items];
    for (let page = 1; items.length < first.total && page < 20; page += 1) {
      const next = await component3Api.evaluationRows(evaluationId, table, c, { ...filters, limit: MAX_PAGE, offset: page * MAX_PAGE }, signal);
      if (next.items.length === 0) break;
      items.push(...next.items);
    }
    return { ...first, items, limit: items.length, offset: 0 };
  },
};
