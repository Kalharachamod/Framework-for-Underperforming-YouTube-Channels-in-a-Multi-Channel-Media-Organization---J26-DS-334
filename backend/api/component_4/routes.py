"""Component 4 REST API Endpoints.

Provides read-only access to emerging topic signals, dynamic trajectories,
and comparative baseline evaluation results.
"""

from __future__ import annotations

from typing import Annotated
from fastapi import APIRouter, Depends, Query, Request

from backend.api.component_4 import schemas as sc
from backend.services.component_4.service import Component4Service

router = APIRouter(prefix="/api/v1/component-4", tags=["Component 4: Emerging Topic Detection"])


def get_service(request: Request) -> Component4Service:
    service = getattr(request.app.state, "component4", None)
    return service or Component4Service()


@router.get("/status", response_model=sc.Component4StatusResponse, summary="Artifact and pipeline status")
def get_status(service: Annotated[Component4Service, Depends(get_service)]):
    """Check readiness and presence of Component 4 research artifacts."""
    return service.get_status()


@router.get("/emerging-topics", response_model=list[sc.EmergingTopicSignalResponse], summary="Detected emerging topic signals")
def get_emerging_topics(
    service: Annotated[Component4Service, Depends(get_service)],
    channel_id: Annotated[str | None, Query(description="Filter by YouTube channel ID")] = None,
    niche: Annotated[str | None, Query(description="Filter by channel niche (e.g. News, Music, Entertainment)")] = None,
    min_score: Annotated[float, Query(ge=0.0, le=1.0, description="Minimum signal score")] = 0.0,
):
    """Retrieve ranked emerging topic momentum signals detected via Hierarchically-Pooled BOCPD."""
    return service.get_emerging_topics(channel_id=channel_id, niche=niche, min_score=min_score)


@router.get("/benchmarks", summary="Baseline comparative evaluation")
def get_benchmarks(service: Annotated[Component4Service, Depends(get_service)]):
    """Retrieve comparative evaluation results comparing Proposed vs Baselines (Simple Trend, CUSUM, Non-hierarchical)."""
    return service.get_benchmarks()


@router.get("/trajectories", summary="Channel-topic prevalence trajectories")
def get_trajectories(
    service: Annotated[Component4Service, Depends(get_service)],
    channel_id: Annotated[str | None, Query(description="Filter by YouTube channel ID")] = None,
    topic_id: Annotated[int | None, Query(description="Filter by topic ID")] = None,
):
    """Retrieve weekly topic prevalence trajectories across channels."""
    return service.get_topic_trajectories(channel_id=channel_id, topic_id=topic_id)


@router.get("/cannibalization-shield", summary="Multi-channel cannibalization prevention & allocation")
def get_cannibalization_shield(service: Annotated[Component4Service, Depends(get_service)]):
    """Calculate channel fit and allocate production rights across the 52 network channels."""
    return service.get_cannibalization_shield()


@router.get("/sensitivity-heatmap", summary="BOCPD hyperparameter sensitivity grid")
def get_sensitivity_heatmap(service: Annotated[Component4Service, Depends(get_service)]):
    """Return 2D grid of detection delay and false alarm rate across lambda and kappa."""
    return service.get_sensitivity_heatmap()

