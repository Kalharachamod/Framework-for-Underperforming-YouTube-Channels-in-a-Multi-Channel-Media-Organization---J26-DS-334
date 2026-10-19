"""Pydantic schemas for Component 2: Audience Demand Mining & Content-Gap."""

from __future__ import annotations
from pydantic import BaseModel


class IntentCategory(BaseModel):
    intent: str
    percentage: str
    count: int
    color: str
    description: str


class LanguageDistribution(BaseModel):
    language: str
    percentage: str
    count: int
    color: str
    description: str


class ContentGapRow(BaseModel):
    niche_cluster: str
    video_supply_share: str
    audience_demand_share: str
    jsd_divergence: float
    operational_alert: str
    is_severe: bool = False


class DemandOverviewResponse(BaseModel):
    total_comments: int
    unique_commenters: int
    language_mix_pct: float
    categories_count: int
    intents: list[IntentCategory]
