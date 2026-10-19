"""Pydantic schemas for Component 1: Channel Growth Prediction."""

from __future__ import annotations
from pydantic import BaseModel


class ChannelGrowthRow(BaseModel):
    channel_id: str
    channel_name: str
    niche: str
    subscribers: int
    subscribers_formatted: str
    video_count: int
    total_views: int
    views_per_sub: float
    growth_potential_pct: int
    status: str


class GrowthMatrixResponse(BaseModel):
    total_channels: int
    total_videos: int
    total_subscribers: int
    channels: list[ChannelGrowthRow]


class BenchmarkModelRow(BaseModel):
    model: str
    accuracy: str
    precision: str
    recall: str
    roc_auc: str
    note: str
    is_best: bool = False


class NicheClusterRow(BaseModel):
    niche_cluster: str
    channel_count: int
    exemplar_channels: str
    color: str
