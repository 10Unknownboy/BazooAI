from __future__ import annotations

import logging

from app.agents.ai_client import AIModelClient
from app.models.agent import AIRequest
from app.models.base import VibeVector
from app.models.event import EventState

logger = logging.getLogger(__name__)


class VibeRecommendation:
    def __init__(
        self,
        recommended_vibe: VibeVector,
        preferred_genres: list[str],
        preferred_languages: list[str],
        reason: str,
        confidence: float,
        preferred_artists: list[str] | None = None,
        avoid_genres: list[str] | None = None,
        avoid_artists: list[str] | None = None,
    ):
        self.recommended_vibe = recommended_vibe
        self.preferred_genres = preferred_genres
        self.preferred_languages = preferred_languages
        self.reason = reason
        self.confidence = confidence
        self.preferred_artists = preferred_artists or []
        self.avoid_genres = avoid_genres or []
        self.avoid_artists = avoid_artists or []


class VibeAgent:
    """Agent responsible for determining the target vibe direction."""

    def __init__(self, ai_client: AIModelClient | None = None):
        self.ai_client = ai_client or AIModelClient()
        self.target_vibe: VibeVector | None = None

    def set_vibe(self, preset_name: str, force: bool = False) -> None:
        """Request a manual vibe change."""
        logger.info(f"Setting vibe manually to preset: {preset_name}")
        # In a real implementation, this would look up the preset
        pass

    async def evaluate_vibe(self, event_state: EventState) -> VibeRecommendation:
        """Evaluate current event state and recommend a vibe direction."""

        from app.models.base import AIMessageType

        # Try to use AI reasoning
        try:
            request = AIRequest(
                message_type=AIMessageType.VIBE_UPDATE,
                request_data={
                    "event_state": event_state.model_dump(mode="json"),
                    "prompt": "Based on the event state, recommend a vibe direction.",
                },
            )
            response = await self.ai_client.decide(request)

            if response.success and response.recommended_vibe:
                return VibeRecommendation(
                    recommended_vibe=response.recommended_vibe,
                    preferred_genres=response.preferred_genres or [],
                    preferred_languages=response.preferred_languages or [],
                    reason=response.reason or "AI decided",
                    confidence=response.confidence or 0.8,
                    preferred_artists=response.preferred_artists,
                    avoid_genres=response.avoid_genres,
                    avoid_artists=response.avoid_artists,
                )
        except Exception as e:
            logger.warning(f"AI vibe evaluation failed: {e}. Falling back to deterministic config.")

        # Fallback to deterministic config
        return VibeRecommendation(
            recommended_vibe=event_state.vibe_vector,
            preferred_genres=event_state.event_config.prefer_genres,
            preferred_languages=[],
            reason="Fallback to event config base vibe",
            confidence=1.0,
        )
