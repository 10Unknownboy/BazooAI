from __future__ import annotations
import logging
from typing import Optional, Dict, Any, List

from app.models.base import VibeVector
from app.models.event import EventState
from app.models.agent import AIRequest, AIResponse
from app.agents.ai_client import AIModelClient

logger = logging.getLogger(__name__)

class VibeRecommendation:
    def __init__(self, recommended_vibe: VibeVector, preferred_genres: List[str], preferred_languages: List[str], reason: str, confidence: float):
        self.recommended_vibe = recommended_vibe
        self.preferred_genres = preferred_genres
        self.preferred_languages = preferred_languages
        self.reason = reason
        self.confidence = confidence

class VibeAgent:
    """Agent responsible for determining the target vibe direction."""
    
    def __init__(self, ai_client: Optional[AIModelClient] = None):
        self.ai_client = ai_client or AIModelClient()
        self.target_vibe: Optional[VibeVector] = None

    def set_vibe(self, preset_name: str, force: bool = False) -> None:
        """Request a manual vibe change."""
        logger.info(f"Setting vibe manually to preset: {preset_name}")
        # In a real implementation, this would look up the preset
        pass

    async def evaluate_vibe(self, event_state: EventState) -> VibeRecommendation:
        """Evaluate current event state and recommend a vibe direction."""
        
        # Try to use AI reasoning
        try:
            request = AIRequest(
                agent_id="vibe_agent",
                task_type="vibe_recommendation",
                context={"event_state": event_state.model_dump(mode="json")},
                prompt="Based on the event state, recommend a vibe direction."
            )
            response = await self.ai_client.decide(request)
            
            if response.success and response.content:
                data = response.content
                return VibeRecommendation(
                    recommended_vibe=VibeVector(**data.get("vibe", {})),
                    preferred_genres=data.get("genres", []),
                    preferred_languages=data.get("languages", []),
                    reason=data.get("reason", "AI decided"),
                    confidence=data.get("confidence", 0.8)
                )
        except Exception as e:
            logger.warning(f"AI vibe evaluation failed: {e}. Falling back to deterministic config.")
            
        # Fallback to deterministic config
        return VibeRecommendation(
            recommended_vibe=event_state.config.base_vibe,
            preferred_genres=event_state.config.allowed_genres,
            preferred_languages=[],
            reason="Fallback to event config base vibe",
            confidence=1.0
        )
