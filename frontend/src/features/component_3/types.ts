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
  organization?: string | null;
  quick_analysis?: boolean;
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

// --- dashboard aggregates (backend /api/v1/component-3/dashboard/*) -----------------------------------

export interface DashboardSummary {
  snapshot_id: string;
  extracted_at: string | null;
  channels: number;
  subscribers: number | null;
  channels_hidden_subscribers: number;
  videos: number;
  views: number | null;
  likes: number | null;
  videos_without_views: number;
  public_comments: number | null;
  collected_comments: number;
  unique_commenters: number;
  first_video: string | null;
  last_video: string | null;
  note: string;
}

export interface ChannelPerformance {
  channel_id: string;
  channel_name: string | null;
  subscriber_count: number | null;
  channel_views: number | null;
  channel_videos: number | null;
  videos: number;
  views: number | null;
  likes: number | null;
  public_comments: number | null;
  last_video: string | null;
  collected_comments: number;
  unique_commenters: number;
}

export interface ChannelPerformanceResponse {
  snapshot_id: string;
  items: ChannelPerformance[];
  note: string;
}

export interface TopVideo {
  video_id: string;
  title: string | null;
  channel_id: string;
  channel_name: string | null;
  published_at: string | null;
  views: number | null;
  likes: number | null;
  comments: number | null;
  duration_seconds: number | null;
  thumbnail_url: string;
  video_url: string;
}

export interface TopVideosResponse {
  snapshot_id: string;
  sort: "views" | "likes" | "comments";
  items: TopVideo[];
  note: string;
}

export interface TimelineSeries {
  channel_id: string;
  channel_name: string | null;
  views: (number | null)[];
  videos: number[];
  total_views: number;
}

export interface ViewsTimelineResponse {
  snapshot_id: string;
  granularity: "week" | "month";
  periods: string[];
  series: TimelineSeries[];
  note: string;
}

export interface OverlapNode {
  channel_id: string;
  channel_name: string | null;
  unique_commenters: number;
}

export interface OverlapEdge {
  source_channel_id: string;
  destination_channel_id: string;
  shared_commenters: number;
  jaccard_similarity: number | null;
}

export interface OverlapResponse {
  snapshot_id: string;
  commenters_on_multiple_channels: number;
  nodes: OverlapNode[];
  edges: OverlapEdge[];
  note: string;
}

export interface TopicSummary {
  topic_id: string;
  label: string;
  videos: number;
  share: number | null;
  views: number | null;
  top_channel_name: string | null;
}

export interface TopicsResponse {
  snapshot_id: string;
  topic_run_id: string;
  items: TopicSummary[];
  flows?: { channel_id: string; channel_name: string | null; topic_id: string; videos: number }[];
  note: string;
}

export interface TopBridge {
  source_channel_id: string;
  source_channel_name: string | null;
  destination_channel_id: string;
  destination_channel_name: string | null;
  audience_bridge_score: number | null;
  confidence: number | null;
  shared_commenters: number | null;
  rank: number | null;
}

export interface TopBridgesResponse {
  snapshot_id: string;
  experiment_id: string;
  items: TopBridge[];
  note: string;
}

// --- research views (graph intelligence, topic similarity, all pairs, run browser) ---------------------


export interface GraphRelation {
  relation: string;
  source_type: string | null;
  target_type: string | null;
  derived: boolean;
  edges: number | null;
  weight_definition: string | null;
}

export interface DegreeDistribution {
  node_type: string;
  nodes: number;
  mean_degree: number | null;
  max_degree: number;
  bins: { label: string; nodes: number }[];
}

export interface ChannelConnectivity {
  channel_id: string;
  channel_name: string | null;
  connected_channels: number;
  shared_commenters_summed: number;
}

export interface Representation {
  method: string;
  status: "available" | "missing";
  experiment_id?: string | null;
  created_at?: string | null;
  role?: string | null;
  dimensions?: number | null;
  coverage_ratio?: number | null;
  validation_passed?: boolean | null;
  config?: Record<string, Scalar>;
}

export interface DiffusionSummary {
  status: "available" | "missing";
  experiment_id?: string | null;
  created_at?: string | null;
  alpha?: number | null;
  tolerance?: number | null;
  max_iterations?: number | null;
  directionality?: string | null;
  include_topic_edges?: boolean | null;
  include_derived_participation?: boolean | null;
  sources?: number | null;
  converged_sources?: number | null;
  iterations_max?: number | null;
  residual_max?: number | null;
  graph_nodes?: number | null;
  graph_edges?: number | null;
  validation_passed?: boolean | null;
}

export interface GraphSummaryResponse {
  snapshot_id: string;
  built_at: string | null;
  node_counts: Record<string, number>;
  edge_counts: Record<string, number>;
  total_nodes: number | null;
  total_edges: number | null;
  total_edges_excluding_derived: number | null;
  commenters_on_multiple_channels: number | null;
  channel_pairs_with_shared_commenters: number | null;
  relations: GraphRelation[];
  degree_distribution: DegreeDistribution[];
  channel_connectivity: ChannelConnectivity[];
  connected_components: number[];
  representations: Representation[];
  diffusion: DiffusionSummary;
  note: string;
}

export interface TopicChannel {
  channel_id: string;
  channel_name: string | null;
  profile_available: boolean;
  usable_videos: number | null;
  coverage_ratio: number | null;
}

export interface TopicCell {
  source_channel_id: string;
  destination_channel_id: string;
  topic_similarity: number | null;
}

export interface TopicSimilarityResponse {
  snapshot_id: string;
  experiment_id: string | null;
  created_at: string | null;
  model: string | null;
  n_topics: number | null;
  channels: TopicChannel[];
  cells: TopicCell[];
  note: string;
}

export interface BridgePairRow {
  source_channel_id: string;
  source_channel_name: string | null;
  destination_channel_id: string;
  destination_channel_name: string | null;
  rank: number | null;
  audience_bridge_score: number | null;
  base_score: number | null;
  diffusion_component: number | null;
  embedding_component: number | null;
  topic_component: number | null;
  confidence_component: number | null;
  evidence_confidence: number | null;
  topic_coverage_confidence: number | null;
  shared_commenters: number | null;
  score_status: string;
  /** raw cosine similarity of the two channels' content profiles (symmetric) */
  topic_similarity?: number | null;
}

export interface BridgePairsResponse {
  snapshot_id: string;
  experiment_id: string;
  items: BridgePairRow[];
  note: string;
}

export interface ResearchRun {
  run_id: string;
  kind: string;
  method: string;
  step: string;
  created_at: string | null;
  validation_passed: boolean | null;
  config: Record<string, Scalar>;
}

export interface ResearchRunsResponse {
  snapshot_id: string;
  snapshot_created_at: string | null;
  snapshot_extracted_at: string | null;
  row_counts: Record<string, number>;
  items: ResearchRun[];
  note: string;
}

// --- neural models ------------------------------------------------------------------------------------

export interface EpochRecord {
  epoch: number;
  train_loss: number | null;
  valid_loss: number | null;
  valid_roc_auc: number | null;
  valid_average_precision: number | null;
}

export interface HgtModel {
  status: "available" | "missing";
  experiment_id?: string | null;
  created_at?: string | null;
  role?: string | null;
  config?: Record<string, Scalar>;
  objective?: string | null;
  negative_sampling?: Record<string, Scalar>;
  split?: { kind: string | null; train_edges: number | null; validation_edges: number | null; cutoff: string | null } | null;
  node_features?: Record<string, string[]>;
  history?: EpochRecord[];
  duration_seconds?: number | null;
  dimensions?: number | null;
  coverage_ratio?: number | null;
  validation_passed?: boolean | null;
}

export interface MetapathWalks {
  metapath: string;
  node_types: string[];
  start_nodes: number | null;
  walks: number | null;
  truncated: number | null;
}

export interface Metapath2VecModel {
  status: "available" | "missing";
  experiment_id?: string | null;
  created_at?: string | null;
  config?: Record<string, Scalar>;
  metapaths?: MetapathWalks[];
  total_walks?: number | null;
  mean_walk_length?: number | null;
  training?: Record<string, Scalar>;
  dimensions?: number | null;
  coverage_ratio?: number | null;
  validation_passed?: boolean | null;
}

export interface NeuralModelsResponse {
  snapshot_id: string;
  hgt: HgtModel;
  metapath2vec: Metapath2VecModel;
  note: string;
}

export interface CompareRun {
  snapshot_id: string;
  experiment_id: string | null;
  created_at: string | null;
  method_version: string | null;
  w_diffusion: number | null;
  w_embedding: number | null;
  w_topic: number | null;
  embedding_source: string | null;
}

export interface CompareRow {
  source_channel_id: string;
  source_channel_name: string | null;
  destination_channel_id: string;
  destination_channel_name: string | null;
  previous_score: number | null;
  current_score: number | null;
  score_change: number | null;
  previous_rank: number | null;
  current_rank: number | null;
  rank_change: number | null;
  previous_confidence: number | null;
  current_confidence: number | null;
  confidence_change: number | null;
  previous_diffusion: number | null;
  current_diffusion: number | null;
  diffusion_change: number | null;
  previous_topic_similarity: number | null;
  current_topic_similarity: number | null;
  topic_similarity_change: number | null;
}

export interface CompareResponse {
  compatible: boolean;
  reason: string | null;
  base: CompareRun | null;
  current: CompareRun | null;
  same_configuration: boolean | null;
  items: CompareRow[];
  note: string;
}

export interface ChannelIconsResponse {
  fetched_at: string | null;
  items: { channel_id: string; icon_url: string }[];
  note: string;
}
