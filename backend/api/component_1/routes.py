"""API routes for Component 1: Channel Growth Prediction."""

from __future__ import annotations
from fastapi import APIRouter, Request
from backend.api.component_1 import schemas as sc

router = APIRouter(prefix="/api/v1/component-1", tags=["Component 1: Channel Growth Prediction"])


@router.get("/growth-matrix", response_model=sc.GrowthMatrixResponse, summary="Live channel growth matrix")
def get_growth_matrix(request: Request):
    """Calculate and return channel views/sub and growth potential from live PostgreSQL data."""
    service = getattr(request.app.state, "component1", None)
    if not service:
        from backend.services.component_1.service import Component1Service
        service = Component1Service()
    return service.get_growth_matrix()


@router.get("/benchmarks", response_model=list[sc.BenchmarkModelRow], summary="Tree model benchmark evaluation")
def get_benchmarks(request: Request):
    """Return model comparison between Random Forest, XGBoost, and LightGBM."""
    service = getattr(request.app.state, "component1", None)
    if not service:
        from backend.services.component_1.service import Component1Service
        service = Component1Service()
    return service.get_benchmarks()


@router.get("/niche-clusters", response_model=list[sc.NicheClusterRow], summary="Portfolio niche cluster breakdown")
def get_niche_clusters(request: Request):
    """Return portfolio channels grouped into functional niche clusters."""
    service = getattr(request.app.state, "component1", None)
    if not service:
        from backend.services.component_1.service import Component1Service
        service = Component1Service()
    return service.get_niche_clusters()
