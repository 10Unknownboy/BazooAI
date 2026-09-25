from __future__ import annotations
import os
import time
import logging
from typing import Dict, Any, Optional
from fastapi import FastAPI, HTTPException, Request, Response
from pydantic import BaseModel

from app.models.agent import AIRequest, AIResponse

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="AI DJ Model Server", description="Remote LLM backend for AI DJ")

# For a real implementation, this would use the official SDK of the LLM provider
# e.g., OpenAI, Anthropic, or a local HuggingFace model.
LLM_API_KEY = os.getenv("LLM_API_KEY", "")

class HealthResponse(BaseModel):
    status: str
    model: str
    uptime: float

START_TIME = time.time()

@app.get("/health", response_model=HealthResponse)
async def health_check():
    return HealthResponse(
        status="ok",
        model="dummy_model_v1",
        uptime=time.time() - START_TIME
    )

@app.post("/v1/ai/decide", response_model=AIResponse)
async def ai_decide(request: AIRequest):
    """Main endpoint for all AI decisions."""
    start_time = time.time()
    
    # 1. Build prompt based on task_type
    prompt = _build_prompt(request)
    
    # 2. Call LLM (mocked here)
    try:
        content = _mock_llm_call(request.task_type, request.context, prompt)
        
        # 3. Log latency
        latency = time.time() - start_time
        logger.info(f"Task {request.task_type} completed in {latency:.2f}s")
        
        return AIResponse(
            request_id=request.request_id,
            success=True,
            content=content
        )
    except Exception as e:
        logger.error(f"LLM call failed: {e}")
        return AIResponse(
            request_id=request.request_id,
            success=False,
            error_message=str(e),
            content=None
        )

# Specific endpoints just mapping to decide for convenience
@app.post("/v1/ai/request")
async def ai_request(request: AIRequest):
    request.task_type = "request_evaluation"
    return await ai_decide(request)

@app.post("/v1/ai/vibe")
async def ai_vibe(request: AIRequest):
    request.task_type = "vibe_recommendation"
    return await ai_decide(request)

@app.post("/v1/ai/lyrics")
async def ai_lyrics(request: AIRequest):
    request.task_type = "lyrics_analysis"
    return await ai_decide(request)

@app.post("/v1/ai/review-queue")
async def ai_review_queue(request: AIRequest):
    request.task_type = "queue_review"
    return await ai_decide(request)

@app.post("/v1/ai/event-summary")
async def ai_event_summary(request: AIRequest):
    request.task_type = "event_summary"
    return await ai_decide(request)

def _build_prompt(request: AIRequest) -> str:
    system_prompt = (
        "You are an autonomous professional DJ. Your goal is event suitability, "
        "crowd satisfaction, vibe consistency, smooth transitions, appropriate "
        "energy progression, request satisfaction, musical variety, policy compliance, "
        "learned contextual preferences.\n"
        "Model response MUST: be valid JSON, use only supplied song IDs, "
        "never invent songs, never override hard policy, state a reason, include confidence."
    )
    return f"{system_prompt}\n\nTask: {request.task_type}\nContext: {request.context}\nPrompt: {request.prompt}"

def _mock_llm_call(task_type: str, context: Dict[str, Any], prompt: str) -> Dict[str, Any]:
    """Mock LLM response for demonstration."""
    if task_type == "vibe_recommendation":
        return {
            "vibe": {"energy": 0.8, "danceability": 0.9, "happiness": 0.7},
            "genres": ["house", "pop"],
            "languages": ["en"],
            "reason": "Crowd energy is high, keeping it upbeat.",
            "confidence": 0.9
        }
    elif task_type == "request_evaluation":
        return {
            "decision": "QUEUE",
            "reason": "Fits the current high energy vibe perfectly.",
            "confidence": 0.95
        }
    elif task_type == "lyrics_analysis":
        return {
            "language": "en",
            "themes": ["love", "party"],
            "sentiment": 0.8,
            "mood": "happy",
            "celebration": 0.9,
            "family_friendly": True
        }
    elif task_type == "queue_review":
        if "candidates" in context:
            # Just return them in the same order for the mock
            return {"ranked_ids": [c.get("id") for c in context["candidates"]]}
        if "issues" in context:
            # Mock transition fix
            return {"changes": []}
    
    return {"result": "success", "reason": "Default mock response"}
