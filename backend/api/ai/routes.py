"""FastAPI routes for Ollama-powered AI recommendations and conversational chat."""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/v1/ai", tags=["AI Growth Intelligence & Chatbot"])


class GrowthStrategyRequest(BaseModel):
    channel_name: str = Field(default="eTunes", description="Name of the channel")
    niche: str = Field(default="Music", description="Channel niche")
    subs: str = Field(default="120K", description="Subscribers formatted")
    views_per_sub: float = Field(default=0.14, description="Calculated views to subscriber ratio")


class ChatRequest(BaseModel):
    message: str = Field(..., description="User question or prompt for the AI copilot")
    channel_context: str = Field(default="eTunes", description="Active channel context")
    conversation_history: Optional[List[Dict[str, str]]] = Field(default=None, description="Previous messages")


@router.get("/status", summary="Check Ollama local LLM status")
def get_ai_status(request: Request) -> Dict[str, Any]:
    ai_service = getattr(request.app.state, "ai_service", None)
    if not ai_service:
        from backend.services.ai.recommender import AiGrowthService
        ai_service = AiGrowthService()
        request.app.state.ai_service = ai_service
    return ai_service.check_ollama_status()


@router.post("/recommend", summary="Generate 4-pillar AI growth strategy for a channel")
def get_recommendation(request: Request, body: GrowthStrategyRequest) -> Dict[str, Any]:
    ai_service = getattr(request.app.state, "ai_service", None)
    if not ai_service:
        from backend.services.ai.recommender import AiGrowthService
        ai_service = AiGrowthService()
        request.app.state.ai_service = ai_service
    return ai_service.get_channel_growth_strategy(
        channel_name=body.channel_name,
        niche=body.niche,
        subs=body.subs,
        views_per_sub=body.views_per_sub,
    )


@router.post("/chat", summary="Chat with Trendora AI Copilot")
def chat_with_copilot(request: Request, body: ChatRequest) -> Dict[str, Any]:
    ai_service = getattr(request.app.state, "ai_service", None)
    if not ai_service:
        from backend.services.ai.recommender import AiGrowthService
        ai_service = AiGrowthService()
        request.app.state.ai_service = ai_service
    return ai_service.chat_advisory(
        message=body.message,
        channel_context=body.channel_context,
        conversation_history=body.conversation_history,
    )
