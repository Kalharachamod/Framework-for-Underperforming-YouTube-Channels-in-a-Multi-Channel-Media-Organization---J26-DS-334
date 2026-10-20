"""Organization search and quick-analysis jobs (the only endpoints that call YouTube or write data).

All other Component 3 routes stay read-only. These can be switched off with API_ENABLE_ANALYSIS=false.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Path, Query, Request, status
from pydantic import BaseModel, ConfigDict, Field

from backend.services.component_3.analysis_jobs import AnalysisJobs

router = APIRouter(prefix="/api/v1/component-3/analysis", tags=["Component 3: organization analysis"])


def jobs(request: Request) -> AnalysisJobs:
    return request.app.state.analysis


Jobs = Annotated[AnalysisJobs, Depends(jobs)]


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


class DiscoverRequest(_Model):
    organization: str = Field(min_length=2, max_length=60, description="Organization or main channel name.")
    region_code: str | None = Field(None, min_length=2, max_length=2, description="2-letter region bias, e.g. LK.")


class ChannelChoice(_Model):
    channel_id: str = Field(min_length=3, max_length=128)
    title: str | None = Field(None, max_length=200)


class CompleteRequest(_Model):
    snapshot_id: str = Field(min_length=19, max_length=19, description="A quick-analysis snapshot (rs-...).")


class StartRequest(_Model):
    organization: str = Field(min_length=2, max_length=60)
    channels: list[ChannelChoice] = Field(min_length=1, max_length=50)


@router.get("/config", summary="Whether analysis is enabled, its limits and the active job")
def analysis_config(j: Jobs) -> dict[str, Any]:
    return j.config()


@router.get("/discover", summary="Saved channel candidates of an earlier search (no quota)")
def saved_candidates(j: Jobs, organization: Annotated[str, Query(min_length=2, max_length=60)]) -> dict[str, Any]:
    return j.discover(organization, None, refresh=False)


@router.post("/discover", summary="Search YouTube for an organization's channels (about 100-150 quota units)")
def discover(j: Jobs, body: DiscoverRequest) -> dict[str, Any]:
    """Candidates come with evidence and a confidence level. YouTube does not publish ownership, so a
    person confirms which channels belong before anything is collected."""
    return j.discover(body.organization, body.region_code, refresh=True)


@router.post("/jobs", status_code=status.HTTP_202_ACCEPTED,
             summary="Start a quick analysis of the confirmed channels (collection + scoring)")
def start_job(j: Jobs, body: StartRequest) -> dict[str, Any]:
    return j.start(body.organization, [c.model_dump() for c in body.channels])


@router.post("/complete", status_code=status.HTTP_202_ACCEPTED,
             summary="Complete a quick analysis: HGT, node2vec and an evaluation (no sparse re-runs)")
def complete_job(j: Jobs, body: CompleteRequest) -> dict[str, Any]:
    """Only quick-analysis snapshots are accepted. Temporal stability compares snapshots of the same
    organization only."""
    return j.complete(body.snapshot_id)


@router.get("/jobs", summary="Recent analysis jobs (newest first)")
def list_jobs(j: Jobs) -> dict[str, Any]:
    return j.list()


@router.get("/jobs/{job_id}", summary="One analysis job with per-step progress")
def get_job(j: Jobs, job_id: Annotated[str, Path(min_length=16, max_length=16)]) -> dict[str, Any]:
    return j.get(job_id)
