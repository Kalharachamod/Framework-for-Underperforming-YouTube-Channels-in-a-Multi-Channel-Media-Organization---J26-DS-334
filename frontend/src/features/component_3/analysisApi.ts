/** Organization search and quick-analysis jobs (backend/api/component_3/analysis_routes.py). */
import { getJson, hasKeys, isList, postJson, type Validator } from "../../services/apiClient";

const BASE = "/api/v1/component-3/analysis";

export interface Candidate {
  channel_id: string;
  title: string;
  handle: string | null;
  country: string | null;
  subscriber_count: number | null;
  video_count: number | null;
  score: number;
  confidence: "high" | "medium" | "low";
  evidence: string[];
  previously_confirmed: boolean;
}

export interface DiscoveryResponse {
  organization: string;
  discovered_at: string;
  quota_used: number;
  source: "youtube" | "saved";
  candidates: Candidate[];
}

export type StepStatus = "pending" | "running" | "completed" | "failed" | "skipped" | "not_executed" | "disabled";

export interface JobStep {
  step: string;
  label: string;
  status: StepStatus;
  details: Record<string, unknown>;
  started_at?: string;
  finished_at?: string;
}

export interface AnalysisJob {
  job_id: string;
  organization: string;
  channels: { channel_id: string; title: string }[];
  status: "queued" | "running" | "completed" | "failed" | "interrupted";
  kind?: "quick" | "complete";
  snapshot_id?: string | null;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
  steps: JobStep[];
  result: { snapshot_id?: string; experiment_id?: string; rows?: Record<string, number>; quota_units?: number; seconds?: number } | null;
  error: string | null;
}

export interface AnalysisConfig {
  enabled: boolean;
  min_channels: number;
  max_channels: number;
  limits: { max_videos_per_channel: number; max_threads_per_video: number; fetch_all_replies: boolean };
  stages: { step: string; label: string }[];
  active_job_id: string | null;
  note: string;
}

const shape =
  <T>(keys: string[], lists: string[] = []): Validator<T> =>
  (d: unknown): d is T =>
    hasKeys(d, keys) && lists.every((k) => isList(d[k]));

const isJob = shape<AnalysisJob>(["job_id", "status", "steps", "organization"], ["steps", "channels"]);
const isDiscovery = shape<DiscoveryResponse>(["organization", "candidates"], ["candidates"]);

/** Searching YouTube can take a while (several API calls), so it gets a longer client timeout. */
const SEARCH_TIMEOUT_MS = 60000;

export const analysisApi = {
  config: (signal?: AbortSignal) =>
    getJson<AnalysisConfig>(`${BASE}/config`, {}, shape(["enabled", "stages"], ["stages"]), signal),
  /** Saved candidates of an earlier search (no YouTube quota). */
  saved: (organization: string, signal?: AbortSignal) =>
    getJson<DiscoveryResponse>(`${BASE}/discover`, { organization }, isDiscovery, signal),
  /** Fresh YouTube search (about 100-150 quota units). */
  discover: (organization: string, regionCode?: string) =>
    postJson<DiscoveryResponse>(`${BASE}/discover`, { organization, region_code: regionCode || null }, isDiscovery, SEARCH_TIMEOUT_MS),
  start: (organization: string, channels: { channel_id: string; title: string }[]) =>
    postJson<AnalysisJob>(`${BASE}/jobs`, { organization, channels }, isJob),
  /** Run the stages a quick analysis skipped (HGT, node2vec, evaluation) on its snapshot. */
  complete: (snapshotId: string) => postJson<AnalysisJob>(`${BASE}/complete`, { snapshot_id: snapshotId }, isJob),
  job: (jobId: string, signal?: AbortSignal) => getJson<AnalysisJob>(`${BASE}/jobs/${encodeURIComponent(jobId)}`, {}, isJob, signal),
  jobs: (signal?: AbortSignal) =>
    getJson<{ items: AnalysisJob[] }>(`${BASE}/jobs`, {}, shape(["items"], ["items"]), signal),
};
