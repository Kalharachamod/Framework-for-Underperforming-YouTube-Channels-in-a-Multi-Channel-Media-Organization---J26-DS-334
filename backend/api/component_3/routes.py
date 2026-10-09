"""Component 3 API routes (read-only). Mounted under /api/v1/component-3.

Every endpoint reads stored research artifacts; none trains a model or reruns the pipeline.
Selection: ``snapshot_id`` defaults to the latest research snapshot, ``experiment_id`` to the
latest Audience Bridge Score run of that snapshot. Responses always echo the ids actually used.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, Request

from backend.api.component_3 import schemas as sc
from backend.services.component_3.service import Component3Service, InvalidParameter

router = APIRouter(prefix="/api/v1/component-3")

ERRORS = {404: {"model": sc.ErrorResponse, "description": "Unknown snapshot / channel / experiment / evaluation "
                                                          "(`not_found`), or the artifact has not been produced yet "
                                                          "(`artifact_unavailable`)."},
          422: {"model": sc.ErrorResponse, "description": "Invalid parameter (`invalid_parameter`)."},
          503: {"model": sc.ErrorResponse, "description": "Stored artifacts could not be read (`storage_unavailable`)."}}

SnapshotQ = Annotated[str | None, Query(description="Research snapshot id (rs-YYYYMMDDTHHMMSSZ); default: latest.")]
ExperimentQ = Annotated[str | None, Query(description="Audience Bridge experiment id (abs-...); default: latest "
                                                      "run of the snapshot.")]
ChannelP = Annotated[str, Path(description="YouTube channel id (UC...).", min_length=2, max_length=72)]


def service(request: Request) -> Component3Service:
    return request.app.state.component3


Service = Annotated[Component3Service, Depends(service)]


def page(request: Request, limit: Annotated[int, Query(ge=1, description="Page size (max API_MAX_PAGE_SIZE).")] = 20,
         offset: Annotated[int, Query(ge=0, le=100_000)] = 0) -> tuple[int, int]:
    maximum = request.app.state.settings.max_page_size
    if limit > maximum:
        raise InvalidParameter(f"limit must be <= {maximum}")
    return limit, offset


Paging = Annotated[tuple[int, int], Depends(page)]


# --- status ---------------------------------------------------------------------------------------

@router.get("/status", response_model=sc.ResearchStatusResponse, tags=["Component 3: status"], responses=ERRORS,
            summary="Research data and artifact availability")
def research_status(svc: Service, snapshot_id: SnapshotQ = None):
    """Lists research snapshots and, for the selected snapshot, reports each artifact (graph, features,
    diffusion, topics, baselines, bridge scores, explanations, evaluations) **separately** as
    `available` / `missing`. Read-only: never triggers a pipeline run."""
    return svc.research_status(snapshot_id)


# --- channels -------------------------------------------------------------------------------------

@router.get("/channels", response_model=sc.ChannelListResponse, tags=["Component 3: channels"], responses=ERRORS,
            summary="List research channels")
def list_channels(svc: Service, snapshot_id: SnapshotQ = None):
    """Channels of the research snapshot with aggregate STEP 14 features (NULL with
    `features_status = missing` when features were not computed)."""
    return svc.list_channels(snapshot_id)


@router.get("/channels/{channel_id}", response_model=sc.ChannelDetailResponse, tags=["Component 3: channels"],
            responses=ERRORS, summary="One channel's metadata and aggregate features")
def channel_detail(channel_id: ChannelP, svc: Service, snapshot_id: SnapshotQ = None):
    return svc.channel_detail(channel_id, snapshot_id)


@router.get("/channels/{channel_id}/pairs", response_model=sc.ChannelPairListResponse,
            tags=["Component 3: channels"], responses=ERRORS, summary="Channels sharing commenters with a channel")
def channel_pairs(channel_id: ChannelP, svc: Service, paging: Paging, snapshot_id: SnapshotQ = None):
    """Aggregate shared-commenter overlap (counts, Jaccard, directional overlap) from STEP 14,
    sorted by shared commenters. No individual commenter is exposed."""
    return svc.channel_pairs(channel_id, snapshot_id, *paging)


# --- audience bridge --------------------------------------------------------------------------------

@router.get("/bridge/experiments", response_model=sc.BridgeExperimentListResponse,
            tags=["Component 3: audience bridge"], responses=ERRORS, summary="Audience Bridge Score experiments")
def bridge_experiments(svc: Service, snapshot_id: SnapshotQ = None):
    """STEP 19 scoring runs of a snapshot (newest first) with their weights, and the STEP 22
    explanations and STEP 21 evaluations that refer to each."""
    return svc.bridge_experiments(snapshot_id)


@router.get("/bridge/{source_channel_id}/destinations", response_model=sc.BridgeRankingResponse,
            tags=["Component 3: audience bridge"], responses=ERRORS, summary="Ranked destination channels")
def bridge_ranking(source_channel_id: ChannelP, svc: Service, paging: Paging, snapshot_id: SnapshotQ = None,
                   experiment_id: ExperimentQ = None,
                   include_unscored: Annotated[bool, Query(description="Also list pairs whose score is incomplete "
                                                                       "(NULL score, no rank).")] = False):
    """Destinations ranked by stored Audience Bridge Score (rank 1 = strongest). Self pairs are
    never returned. Scores are read, not recalculated."""
    return svc.bridge_ranking(source_channel_id, snapshot_id, experiment_id, *paging, include_unscored)


@router.get("/bridge/{source_channel_id}/destinations/{destination_channel_id}", response_model=sc.BridgePairResponse,
            tags=["Component 3: audience bridge"], responses=ERRORS, summary="One pair: score, decomposition, evidence")
def bridge_pair(source_channel_id: ChannelP, destination_channel_id: ChannelP, svc: Service,
                snapshot_id: SnapshotQ = None, experiment_id: ExperimentQ = None):
    """Stored score and its decomposition, plus the STEP 22 explanation (aggregate evidence,
    reasons, uncertainty, ranking context). If no explanation artifact exists for the experiment,
    `explanation_status` is `unavailable` with the reason; nothing is invented."""
    return svc.bridge_pair(source_channel_id, destination_channel_id, snapshot_id, experiment_id)


# --- evaluation -------------------------------------------------------------------------------------

@router.get("/evaluation/runs", response_model=sc.EvaluationRunListResponse, tags=["Component 3: evaluation"],
            responses=ERRORS, summary="Stored evaluation runs")
def evaluation_runs(svc: Service, snapshot_id: SnapshotQ = None):
    """STEP 21 evaluation runs of a snapshot (newest first). An empty list means no evaluation has run."""
    return svc.evaluation_runs(snapshot_id)


@router.get("/evaluation/{evaluation_id}/metadata", response_model=sc.EvaluationMetadataResponse,
            tags=["Component 3: evaluation"], responses=ERRORS, summary="Evaluation run metadata")
def evaluation_metadata(evaluation_id: str, svc: Service, snapshot_id: SnapshotQ = None):
    return svc.evaluation_metadata(evaluation_id, snapshot_id)


@router.get("/evaluation/{evaluation_id}/{table}", response_model=sc.EvaluationRowsResponse,
            tags=["Component 3: evaluation"], responses=ERRORS, summary="Evaluation result rows")
def evaluation_rows(evaluation_id: str, table: sc.EvaluationTable, svc: Service, paging: Paging,
                    snapshot_id: SnapshotQ = None,
                    method: Annotated[str | None, Query(description="Filter by method (must be a method of the run).")] = None,
                    metric: Annotated[str | None, Query(description="Filter by metric (tables with a metric column).")] = None):
    """Rows of one STEP 21 table: `ranking`, `top_k`, `temporal_stability`, `sparse_robustness` or
    `performance`. An empty `items` list means no row matched the filters; an unknown method or an
    unsupported filter is `invalid_parameter`; a run that does not exist is `not_found`."""
    return svc.evaluation_rows(evaluation_id, table, snapshot_id, method, metric, *paging)
