"""Growth Intelligence FastAPI application.

    uvicorn backend.main:app --reload            # http://localhost:8000/docs

Configuration: environment variables (see backend/config.py and .env.example).
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from backend import errors
from backend.api.component_3 import schemas as sc
from backend.api.component_3.routes import router as component_3_router
from backend.config import Settings, load_settings
from backend.services.component_3.service import Component3Service

DESCRIPTION = """Read-only API over the J26-DS-334 research results.

**Component 3: Diffusion-Based Cross-Channel Audience Bridge Scoring.** Channels, Audience Bridge
Scores (STEP 19, provisional formula), explanations (STEP 22), evaluation (STEP 21) and artifact
status. Results are read from stored research artifacts; no model is trained or rerun by a request.

Scores are potential audience bridge signals. They do not show audience migration, subscriber
transfer, causality or growth. No commenter identifiers (raw or pseudonymized) are ever returned.
"""


def create_app(settings: Settings | None = None, service: Component3Service | None = None) -> FastAPI:
    settings = settings or load_settings()
    app = FastAPI(title=settings.title, version=settings.api_version, description=DESCRIPTION,
                  openapi_tags=[{"name": "system", "description": "API liveness."},
                                {"name": "Component 3: status", "description": "Research data / artifact availability."},
                                {"name": "Component 3: channels", "description": "Channels and aggregate features."},
                                {"name": "Component 3: audience bridge",
                                 "description": "Audience Bridge Scores, decomposition and explanations."},
                                {"name": "Component 3: evaluation", "description": "Stored STEP 21 evaluation results."}])
    app.state.settings = settings
    app.state.component3 = service or Component3Service()
    app.add_middleware(CORSMiddleware, allow_origins=list(settings.cors_origins), allow_credentials=False,
                       allow_methods=["GET"], allow_headers=["Accept", "Content-Type"])

    @app.middleware("http")
    async def timeout(request: Request, call_next):
        try:
            return await asyncio.wait_for(call_next(request), timeout=settings.request_timeout_seconds)
        except asyncio.TimeoutError:
            return errors.error(504, "timeout", "the request took too long")

    errors.install(app)

    @app.get("/health", response_model=sc.HealthResponse, tags=["system"], summary="API liveness")
    def health():
        """`ok` means the API process is running. It does **not** mean research artifacts exist;
        see `/api/v1/component-3/status` for that."""
        return {"status": "ok", "service": settings.title, "version": settings.api_version,
                "time": datetime.now(timezone.utc).replace(microsecond=0)}

    app.include_router(component_3_router)
    return app


app = create_app()
