/**
 * Response contracts of the Component 3 API (mirrors backend/api/component_3/schemas.py).
 * Timestamps are ISO 8601 strings; channel ids are YouTube channel ids (UC...).
 */

export interface HealthResponse {
  status: "ok";
  service: string;
  version: string;
  time: string;
}

export interface SnapshotSummary {
  snapshot_id: string;
  created_at: string;
  extracted_at: string | null;
  channels: number;
  videos: number;
  comments: number;
}

export interface ArtifactStatus {
  name: string;
  status: "available" | "missing";
  count: number;
  latest_id: string | null;
  detail: string | null;
}

export interface ResearchStatusResponse {
  research_data: "available" | "missing";
  snapshots: SnapshotSummary[];
  latest_snapshot_id: string | null;
  snapshot_id: string | null;
  artifacts: ArtifactStatus[];
  note: string;
}

export interface ChannelSummary {
  channel_id: string;
  channel_name: string | null;
  observed_subscriber_count: number | null;
  stored_video_count: number | null;
  unique_commenter_count: number | null;
  comment_count: number | null;
}

export interface ChannelListResponse {
  snapshot_id: string;
  features_status: "available" | "missing";
  items: ChannelSummary[];
  total: number;
}

export interface ChannelDetailResponse {
  snapshot_id: string;
  features_status: "available" | "missing";
  as_of: string | null;
  channel_id: string;
  channel_name: string | null;
  description: string | null;
  published_at: string | null;
  observed_subscriber_count: number | null;
  observed_view_count: number | null;
  observed_api_video_count: number | null;
  stored_video_count: number | null;
  unique_commenter_count: number | null;
  comment_count: number | null;
  reply_count: number | null;
  avg_comments_per_video: number | null;
  active_commenter_count: number | null;
  first_interaction_at: string | null;
  last_interaction_at: string | null;
  active_days: number | null;
  collection_coverage: number | null;
}

export interface Page {
  total: number;
  limit: number;
  offset: number;
}

export interface ChannelPair {
  source_channel_id: string;
  destination_channel_id: string;
  destination_channel_name: string | null;
  shared_commenters: number;
  jaccard_similarity: number | null;
  directional_overlap_source_to_destination: number | null;
}

export interface ChannelPairListResponse extends Page {
  snapshot_id: string;
  source_channel_id: string;
  items: ChannelPair[];
  note: string;
}

export interface BridgeExperiment {
  experiment_id: string;
  snapshot_id: string;
  created_at: string | null;
  method_version: string | null;
  provisional: boolean;
  w_diffusion: number;
  w_embedding: number;
  w_topic: number;
  embedding_source: string;
  embedding_experiment_id: string | null;
  confidence_k: number;
  pairs: number | null;
  scored_pairs: number | null;
  explanation_ids: string[];
  evaluation_ids: string[];
}

export interface BridgeExperimentListResponse {
  snapshot_id: string;
  items: BridgeExperiment[];
}

export interface BridgeDestination {
  rank: number | null;
  destination_channel_id: string;
  destination_channel_name: string | null;
  audience_bridge_score: number | null;
  diffusion_component: number | null;
  embedding_component: number | null;
  topic_component: number | null;
  confidence_component: number | null;
  base_score: number | null;
  score_status: string;
}

export interface BridgeRankingResponse extends Page {
  snapshot_id: string;
  experiment_id: string;
  source_channel_id: string;
  source_channel_name: string | null;
  include_unscored: boolean;
  items: BridgeDestination[];
  note: string;
}

export interface ScoreBreakdown {
  raw_diffusion_score: number | null;
  normalized_diffusion: number | null;
  raw_embedding_similarity: number | null;
  normalized_embedding_similarity: number | null;
  raw_topic_similarity: number | null;
  normalized_topic_similarity: number | null;
  w_diffusion: number;
  w_embedding: number;
  w_topic: number;
  embedding_source: string;
  diffusion_component: number | null;
  embedding_component: number | null;
  topic_component: number | null;
  base_score: number | null;
  shared_commenters: number | null;
  evidence_confidence: number | null;
  topic_coverage_confidence: number | null;
  confidence_component: number | null;
  formula: string;
}

export type EvidenceState = "observed" | "zero" | "insufficient_coverage" | "missing" | "not_used" | string;

export interface EvidenceSummary {
  shared_commenters: number | null;
  shared_commenter_state: EvidenceState;
  jaccard_similarity: number | null;
  directional_overlap_source_to_destination: number | null;
  shared_comments_on_source: number | null;
  shared_comments_on_destination: number | null;
  shared_videos_on_source: number | null;
  shared_videos_on_destination: number | null;
  source_video_coverage: number | null;
  destination_video_coverage: number | null;
  video_coverage_state: EvidenceState;
  shared_active_days: number | null;
  shared_first_comment_at: string | null;
  shared_last_comment_at: string | null;
  temporal_state: EvidenceState;
  topic_similarity: number | null;
  topic_state: EvidenceState;
  embedding_similarity: number | null;
  embedding_state: EvidenceState;
}

export interface ExplanationReason {
  reason_code: string;
  reason_text: string;
  criterion: string;
  value: number | null;
  threshold: number | null;
}

export interface RankingContext {
  candidate_destinations: number | null;
  scored_destinations: number | null;
  score_percentile: number | null;
  next_higher_destination_id: string | null;
  next_higher_score: number | null;
  next_lower_destination_id: string | null;
  next_lower_score: number | null;
}

export interface BridgePairResponse {
  snapshot_id: string;
  experiment_id: string;
  source_channel_id: string;
  source_channel_name: string | null;
  destination_channel_id: string;
  destination_channel_name: string | null;
  rank: number | null;
  audience_bridge_score: number | null;
  score_status: string;
  score_breakdown: ScoreBreakdown;
  explanation_status: "available" | "unavailable";
  explanation_detail: string | null;
  explanation_id: string | null;
  explanation_config_id: string | null;
  explanation_outcome: string | null;
  explanation_text: string | null;
  evidence_summary: EvidenceSummary | null;
  explanation_reasons: ExplanationReason[];
  uncertainty_notes: string[];
  ranking_context: RankingContext | null;
  note: string;
}

export type EvaluationTable = "ranking" | "top_k" | "temporal_stability" | "sparse_robustness" | "performance";
export type Scalar = number | string | boolean | null;

export interface EvaluationRun {
  evaluation_id: string;
  snapshot_id: string;
  created_at: string | null;
  methods: Record<string, string>;
  audience_bridge_experiment_id: string | null;
  labels_status: string;
  temporal_status: string | null;
  sparse_runs: number;
}

export interface EvaluationRunListResponse {
  snapshot_id: string;
  items: EvaluationRun[];
}

export interface EvaluationRowsResponse extends Page {
  evaluation_id: string;
  snapshot_id: string;
  table: EvaluationTable;
  columns: string[];
  items: Record<string, Scalar>[];
  note: string;
}

export interface EvaluationMetadataResponse {
  evaluation_id: string;
  snapshot_id: string;
  created_at: string | null;
  graph_fingerprint: string | null;
  as_of: string | null;
  config: Record<string, Scalar | Scalar[]>;
  methods: Record<string, Record<string, Scalar>>;
  proposed_method: Record<string, Scalar>;
  labels: Record<string, Scalar | Scalar[]>;
  temporal: Record<string, Scalar>;
  sparse_robustness: Record<string, Scalar | Scalar[]>;
  performance: Record<string, Scalar>;
  interpretation: string | null;
  versions: Record<string, string>;
}
