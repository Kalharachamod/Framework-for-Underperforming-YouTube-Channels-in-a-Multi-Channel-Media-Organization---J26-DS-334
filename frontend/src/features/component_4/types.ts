/** TypeScript definitions for Component 4: Emerging Topic Detection. */

export interface EmergingTopicSignal {
  channel_id: string;
  channel_name: string;
  channel_niche: string;
  topic_id: number;
  topic_label: string;
  changepoint_week: string;
  changepoint_probability: number;
  trend_direction: string;
  change_magnitude: number;
  current_prevalence: number;
  prior_prevalence: number;
  ci_lower: number;
  ci_upper: number;
  signal_score: number;
  is_sparse_channel: boolean;
}

export interface BenchmarkResult {
  Methodology: string;
  "Detected Emerging Flags": number;
  "Transient / Noise Spikes": number;
  "False Alarm Rate (%)": number;
  "Flags on Sparse Channels": number;
  "Prevalence Stability Score": number;
  "Provides Uncertainty": string;
}

export interface Component4Status {
  has_videos: boolean;
  has_trajectories: boolean;
  has_emerging_signals: boolean;
  has_benchmarks: boolean;
  total_signals_detected: number;
}

export interface TopicTrajectoryPoint {
  channel_id: string;
  channel_name: string;
  channel_niche: string;
  topic_id: number;
  topic_label: string;
  upload_week: string;
  video_count: number;
  shorts_count: number;
  shorts_ratio: number;
  channel_weekly_total_uploads: number;
  topic_prevalence: number;
  is_sparse_channel_week: boolean;
}
