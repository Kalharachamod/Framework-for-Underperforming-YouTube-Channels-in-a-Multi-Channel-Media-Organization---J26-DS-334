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
from backend.api.component_1.routes import router as component_1_router
from backend.api.component_2.routes import router as component_2_router
from backend.api.component_3 import schemas as sc
from backend.api.component_3.routes import router as component_3_router
from backend.api.component_4.routes import router as component_4_router
from backend.api.ai.routes import router as ai_router
from backend.config import Settings, load_settings
from backend.services.component_1.service import Component1Service
from backend.services.component_2.service import Component2Service
from backend.services.component_3.service import Component3Service
from backend.services.component_4.service import Component4Service
from backend.services.ai.recommender import AiGrowthService

DESCRIPTION = """Read-only API over the J26-DS-334 research results.

**Component 1: Channel-Specific Growth Opportunity Prediction with Pooled Learning.**
**Component 2: Quantified Audience Demand Mining and Content-Gap Divergence.**
**Component 3: Diffusion-Based Cross-Channel Audience Bridge Scoring.**
**Component 4: Hierarchically Pooled Dynamic Topic Modelling with Bayesian Changepoint Flagging.**
**AI Growth Copilot: Ollama Local LLM & 4-Pillar Strategy Recommendations.**
"""


def create_app(settings: Settings | None = None, service: Component3Service | None = None) -> FastAPI:
    settings = settings or load_settings()
    app = FastAPI(
        title=settings.title,
        version=settings.api_version,
        description=DESCRIPTION,
        openapi_tags=[
            {"name": "system", "description": "API liveness."},
            {"name": "Component 1: Channel Growth Prediction", "description": "Channel-specific growth opportunity matrix and tree models."},
            {"name": "Component 2: Audience Demand Mining", "description": "Comment intent mining, multilingual NLP and content-gap divergence."},
            {"name": "Component 3: status", "description": "Research data / artifact availability."},
            {"name": "Component 3: channels", "description": "Channels and aggregate features."},
            {"name": "Component 3: audience bridge", "description": "Audience Bridge Scores, decomposition and explanations."},
            {"name": "Component 3: evaluation", "description": "Stored STEP 21 evaluation results."},
            {"name": "Component 4: Emerging Topic Detection", "description": "Hierarchically Pooled Dynamic Topic Modelling with BOCPD emerging signals."},
            {"name": "AI Growth Intelligence & Chatbot", "description": "Ollama LLM and 4-pillar multi-channel growth copilot."},
        ],
    )
    app.state.settings = settings
    app.state.component1 = Component1Service()
    app.state.component2 = Component2Service()
    app.state.component3 = service or Component3Service()
    app.state.component4 = Component4Service()
    app.state.ai_service = AiGrowthService()

    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.cors_origins),
        allow_credentials=False,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["*"],
    )

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
        return {
            "status": "ok",
            "service": settings.title,
            "version": settings.api_version,
            "time": datetime.now(timezone.utc).replace(microsecond=0),
        }

    app.include_router(component_1_router)
    app.include_router(component_2_router)
    app.include_router(component_3_router)
    app.include_router(component_4_router)
    app.include_router(ai_router)
    return app


app = create_app()
