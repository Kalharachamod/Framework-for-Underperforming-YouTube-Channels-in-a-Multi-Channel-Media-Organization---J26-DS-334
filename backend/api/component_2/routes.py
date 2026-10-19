"""API routes for Component 2: Audience Demand Mining & Content-Gap."""

from __future__ import annotations
from fastapi import APIRouter, Request
from backend.api.component_2 import schemas as sc

router = APIRouter(prefix="/api/v1/component-2", tags=["Component 2: Audience Demand Mining"])


@router.get("/intent-breakdown", response_model=sc.DemandOverviewResponse, summary="Live audience demand intent breakdown")
def get_intent_breakdown(request: Request):
    """Retrieve quantified demand intents mined from 26k+ viewer comments."""
    service = getattr(request.app.state, "component2", None)
    if not service:
        from backend.services.component_2.service import Component2Service
        service = Component2Service()
    return service.get_demand_overview()


@router.get("/content-gap", response_model=list[sc.ContentGapRow], summary="Jensen-Shannon supply-demand divergence")
def get_content_gap(request: Request):
    """Return supply vs demand divergence index across media niches."""
    service = getattr(request.app.state, "component2", None)
    if not service:
        from backend.services.component_2.service import Component2Service
        service = Component2Service()
    return service.get_content_gap()


@router.get("/language-stats", response_model=list[sc.LanguageDistribution], summary="Multilingual script distribution")
def get_language_stats(request: Request):
    """Return Sinhala, Tanglish, and English comment distribution."""
    service = getattr(request.app.state, "component2", None)
    if not service:
        from backend.services.component_2.service import Component2Service
        service = Component2Service()
    return service.get_language_stats()
