"""Pydantic schemas for Component 4 REST API."""

from __future__ import annotations

from pydantic import BaseModel, Field


class EmergingTopicSignalResponse(BaseModel):
    channel_id: str
    channel_name: str
    channel_niche: str
    topic_id: int
    topic_label: str
    changepoint_week: str
    changepoint_probability: float
    trend_direction: str
    change_magnitude: float
    current_prevalence: float
    prior_prevalence: float
    ci_lower: float
    ci_upper: float
    signal_score: float
    is_sparse_channel: bool


class BenchmarkResultResponse(BaseModel):
    Methodology: str
    Detected_Emerging_Flags: int = Field(alias="Detected Emerging Flags")
    Transient_Noise_Spikes: int = Field(alias="Transient / Noise Spikes")
    False_Alarm_Rate_Pct: float = Field(alias="False Alarm Rate (%)")
    Flags_on_Sparse_Channels: int = Field(alias="Flags on Sparse Channels")
    Prevalence_Stability_Score: float = Field(alias="Prevalence Stability Score")
    Provides_Uncertainty: str = Field(alias="Provides Uncertainty")


class Component4StatusResponse(BaseModel):
    has_videos: bool
    has_trajectories: bool
    has_emerging_signals: bool
    has_benchmarks: bool
    total_signals_detected: int
