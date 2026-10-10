"""Response contracts of the Component 3 API (stable field names, explicit optionals).

Channel ids are YouTube channel ids (``UC...``); timestamps are ISO 8601 UTC. No schema has a
field for commenter identifiers (raw or pseudonymized): only aggregate counts are exposed.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


# --- errors ------------------------------------------------------------------------------------

class ErrorDetail(_Model):
    location: str
    message: str


class ErrorBody(_Model):
    code: Literal["not_found", "artifact_unavailable", "invalid_parameter", "storage_unavailable",
                  "timeout", "internal_error"]
    message: str
    details: list[ErrorDetail] | None = None


class ErrorResponse(_Model):
    error: ErrorBody


# --- status ------------------------------------------------------------------------------------

class HealthResponse(_Model):
    status: Literal["ok"] = Field(description="The API process is up. Says nothing about research artifacts.")
    service: str
    version: str
    time: datetime


class SnapshotSummary(_Model):
    snapshot_id: str
    created_at: datetime
    extracted_at: datetime | None
    channels: int
    videos: int
    comments: int


class ArtifactStatus(_Model):
    name: str
    status: Literal["available", "missing"]
    count: int = Field(description="Number of stored runs / files of this artifact for the snapshot.")
    latest_id: str | None = None
    detail: str | None = None


class ResearchStatusResponse(_Model):
    research_data: Literal["available", "missing"]
    snapshots: list[SnapshotSummary]
    latest_snapshot_id: str | None
    snapshot_id: str | None = Field(description="Snapshot whose artifacts are reported below.")
    artifacts: list[ArtifactStatus]
    note: str


# --- channels ----------------------------------------------------------------------------------

class ChannelSummary(_Model):
    channel_id: str
    channel_name: str | None
    observed_subscriber_count: int | None = Field(None, description="Public count at collection; NULL if hidden.")
    stored_video_count: int | None = None
    unique_commenter_count: int | None = None
    comment_count: int | None = None


class ChannelListResponse(_Model):
    snapshot_id: str
    features_status: Literal["available", "missing"]
    items: list[ChannelSummary]
    total: int


class ChannelDetailResponse(_Model):
    snapshot_id: str
    features_status: Literal["available", "missing"]
    as_of: datetime | None
    channel_id: str
    channel_name: str | None
    description: str | None
    published_at: datetime | None
    observed_subscriber_count: int | None
    observed_view_count: int | None
    observed_api_video_count: int | None
    stored_video_count: int | None
    unique_commenter_count: int | None
    comment_count: int | None
    reply_count: int | None
    avg_comments_per_video: float | None
    active_commenter_count: int | None
    first_interaction_at: datetime | None
    last_interaction_at: datetime | None
    active_days: int | None
    collection_coverage: float | None


class ChannelPair(_Model):
    source_channel_id: str
    destination_channel_id: str
    destination_channel_name: str | None
    shared_commenters: int
    jaccard_similarity: float | None
    directional_overlap_source_to_destination: float | None


class Page(_Model):
    total: int
    limit: int
    offset: int


class ChannelPairListResponse(Page):
    snapshot_id: str
    source_channel_id: str
    items: list[ChannelPair]
    note: str


# --- audience bridge ---------------------------------------------------------------------------

class BridgeExperiment(_Model):
    experiment_id: str
    snapshot_id: str
    created_at: datetime | None
    method_version: str | None
    provisional: bool
    w_diffusion: float
    w_embedding: float
    w_topic: float
    embedding_source: str = Field(description="metapath2vec (primary), hgt (alternative) or none")
    embedding_experiment_id: str | None
    confidence_k: float
    pairs: int | None
    scored_pairs: int | None
    explanation_ids: list[str]
    evaluation_ids: list[str]


class BridgeExperimentListResponse(_Model):
    snapshot_id: str
    items: list[BridgeExperiment]


class BridgeDestination(_Model):
    rank: int | None
    destination_channel_id: str
    destination_channel_name: str | None
    audience_bridge_score: float | None
    diffusion_component: float | None
    embedding_component: float | None
    topic_component: float | None
    confidence_component: float | None
    base_score: float | None
    score_status: str


class BridgeRankingResponse(Page):
    snapshot_id: str
    experiment_id: str
    source_channel_id: str
    source_channel_name: str | None
    include_unscored: bool
    items: list[BridgeDestination]
    note: str


class ScoreBreakdown(_Model):
    raw_diffusion_score: float | None
    normalized_diffusion: float | None
    raw_embedding_similarity: float | None
    normalized_embedding_similarity: float | None
    raw_topic_similarity: float | None
    normalized_topic_similarity: float | None
    w_diffusion: float
    w_embedding: float
    w_topic: float
    embedding_source: str
    diffusion_component: float | None
    embedding_component: float | None
    topic_component: float | None
    base_score: float | None
    shared_commenters: int | None
    evidence_confidence: float | None
    topic_coverage_confidence: float | None
    confidence_component: float | None
    formula: str


class EvidenceSummary(_Model):
    shared_commenters: int | None
    shared_commenter_state: str
    jaccard_similarity: float | None
    directional_overlap_source_to_destination: float | None
    shared_comments_on_source: int | None
    shared_comments_on_destination: int | None
    shared_videos_on_source: int | None
    shared_videos_on_destination: int | None
    source_video_coverage: float | None
    destination_video_coverage: float | None
    video_coverage_state: str
    shared_active_days: int | None
    shared_first_comment_at: datetime | None
    shared_last_comment_at: datetime | None
    temporal_state: str
    topic_similarity: float | None
    topic_state: str
    embedding_similarity: float | None
    embedding_state: str


class ExplanationReason(_Model):
    reason_code: str
    reason_text: str
    criterion: str
    value: float | None
    threshold: float | None


class RankingContext(_Model):
    candidate_destinations: int | None
    scored_destinations: int | None
    score_percentile: float | None
    next_higher_destination_id: str | None
    next_higher_score: float | None
    next_lower_destination_id: str | None
    next_lower_score: float | None


class BridgePairResponse(_Model):
    snapshot_id: str
    experiment_id: str
    source_channel_id: str
    source_channel_name: str | None
    destination_channel_id: str
    destination_channel_name: str | None
    rank: int | None
    audience_bridge_score: float | None
    score_status: str
    score_breakdown: ScoreBreakdown
    explanation_status: Literal["available", "unavailable"]
    explanation_detail: str | None
    explanation_id: str | None
    explanation_config_id: str | None
    explanation_outcome: str | None = Field(None, description="complete | incomplete | reconstruction_mismatch")
    explanation_text: str | None
    evidence_summary: EvidenceSummary | None
    explanation_reasons: list[ExplanationReason]
    uncertainty_notes: list[str]
    ranking_context: RankingContext | None
    note: str


# --- evaluation -------------------------------------------------------------------------------

EvaluationTable = Literal["ranking", "top_k", "temporal_stability", "sparse_robustness", "performance"]
Scalar = float | int | str | bool | None


class EvaluationRun(_Model):
    evaluation_id: str
    snapshot_id: str
    created_at: datetime | None
    methods: dict[str, str] = Field(description="method -> status (ok | unavailable | failed)")
    audience_bridge_experiment_id: str | None
    labels_status: str
    temporal_status: str | None
    sparse_runs: int


class EvaluationRunListResponse(_Model):
    snapshot_id: str
    items: list[EvaluationRun]


class EvaluationRowsResponse(Page):
    evaluation_id: str
    snapshot_id: str
    table: EvaluationTable
    columns: list[str]
    items: list[dict[str, Scalar]]
    note: str


class EvaluationMetadataResponse(_Model):
    evaluation_id: str
    snapshot_id: str
    created_at: datetime | None
    graph_fingerprint: str | None
    as_of: datetime | None
    config: dict[str, Scalar | list[Scalar]]
    methods: dict[str, dict[str, Scalar]]
    proposed_method: dict[str, Scalar]
    labels: dict[str, Scalar | list[Scalar]]
    temporal: dict[str, Scalar]
    sparse_robustness: dict[str, Scalar | list[Scalar]]
    performance: dict[str, Scalar]
    interpretation: str | None
    versions: dict[str, str]
