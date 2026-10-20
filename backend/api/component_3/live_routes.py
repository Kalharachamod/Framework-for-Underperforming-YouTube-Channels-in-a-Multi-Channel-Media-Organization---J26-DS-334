"""Component 3 live results (published nightly by research/component_3/live.py). Read-only."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, Request

from backend.services.component_3.live_results import LiveResults

router = APIRouter(prefix="/api/v1/component-3/live", tags=["Component 3: live results"])


def live(request: Request) -> LiveResults:
    return request.app.state.live


Live = Annotated[LiveResults, Depends(live)]


@router.get("/runs", summary="Recent nightly runs (newest first) with status and data counts")
def live_runs(lv: Live, limit: Annotated[int, Query(ge=1, le=100)] = 30) -> dict[str, Any]:
    return lv.runs(limit)


@router.get("/bridges", summary="Bridge scores and channel counts of the latest (or a given) completed nightly run")
def live_bridges(lv: Live, run_id: Annotated[str | None, Query(max_length=24)] = None,
                 source: Annotated[str | None, Query(max_length=64, description="Only this source channel (UC...).")] = None,
                 limit: Annotated[int, Query(ge=1, le=1000)] = 100) -> dict[str, Any]:
    return lv.bridges(run_id, source, limit)


@router.get("/history", summary="One directed pair's score over the nightly runs (trend)")
def live_history(lv: Live, source: Annotated[str, Query(max_length=64)], destination: Annotated[str, Query(max_length=64)],
                 limit: Annotated[int, Query(ge=1, le=365)] = 60) -> dict[str, Any]:
    return lv.history(source, destination, limit)
