from __future__ import annotations

import logging

from pydantic import BaseModel, Field

from app.agents.ai_client import AIModelClient
from app.event.event_bus import BusEvent, get_event_bus
from app.models.agent import AIRequest

logger = logging.getLogger(__name__)


class LyricsFeatures(BaseModel):
    analysis_model: str | None = None
    song_id: str
    language: str = "unknown"
    themes: list[str] = Field(default_factory=list)
    sentiment: float = 0.0
    mood: str = "neutral"
    romance: float = 0.0
    sadness: float = 0.0
    celebration: float = 0.0
    aggression: float = 0.0
    sexual_content: float = 0.0
    explicitness: float = 0.0
    violence: float = 0.0
    drugs: float = 0.0
    breakup: float = 0.0
    nostalgia: float = 0.0
    family_friendly: bool = True
    event_suitability: dict[str, float] = Field(default_factory=dict)


class LyricsAgent:
    """Agent responsible for analyzing song lyrics for themes, sentiment, and appropriateness."""

    ANALYSIS_VERSION = 1

    def __init__(self, ai_client: AIModelClient | None = None):
        self.ai_client = ai_client or AIModelClient()
        self.event_bus = get_event_bus()

    async def analyze_lyrics(self, song_id: str, lyrics_text: str | None = None) -> LyricsFeatures:
        """Analyze lyrics and extract features."""

        # In a real implementation, we would check LyricsFeaturesRepository first
        # to avoid re-analyzing

        if not lyrics_text:
            logger.warning(f"No lyrics provided for {song_id}. Returning default features.")
            return LyricsFeatures(song_id=song_id)

        from app.models.base import AIMessageType

        try:
            # We don't send full copyrighted text if possible, or we send it
            # just for analysis and don't store it

            # Truncate if too long
            text_to_analyze = lyrics_text[:2000] if len(lyrics_text) > 2000 else lyrics_text

            request = AIRequest(
                message_type=AIMessageType.LYRIC_ANALYSIS,
                lyrics_data={"lyrics": text_to_analyze},
                request_data={
                    "prompt": (
                        "Analyze lyrics and return language, themes, sentiment (-1 to 1), mood, "
                        "and content scores (0 to 1) for romance, sadness, celebration, "
                        "aggression, sexual content, explicitness, violence, drugs, breakup, "
                        "and nostalgia."
                    )
                },
            )
            response = await self.ai_client.decide(request)

            if response.success and response.lyrics_analysis:
                data = response.lyrics_analysis
                features = LyricsFeatures(
                    analysis_model=response.model_name or "remote-model",
                    song_id=song_id,
                    language=data.get("language", "unknown"),
                    themes=data.get("themes", []),
                    sentiment=data.get("sentiment", 0.0),
                    mood=data.get("mood", "neutral"),
                    romance=data.get("romance", 0.0),
                    sadness=data.get("sadness", 0.0),
                    celebration=data.get("celebration", 0.0),
                    aggression=data.get("aggression", 0.0),
                    sexual_content=data.get("sexual_content", 0.0),
                    explicitness=data.get("explicitness", 0.0),
                    violence=data.get("violence", 0.0),
                    drugs=data.get("drugs", 0.0),
                    breakup=data.get("breakup", 0.0),
                    nostalgia=data.get("nostalgia", 0.0),
                    family_friendly=data.get("family_friendly", True),
                    event_suitability=data.get("event_suitability", {}),
                )

                self.event_bus.publish(
                    BusEvent.LYRICS_ANALYSIS_COMPLETE,
                    source="lyrics_agent",
                    data={"song_id": song_id},
                )
                return features

        except Exception as e:
            logger.warning(f"AI lyrics analysis failed: {e}. Falling back to basic analysis.")

        # Fallback to basic deterministic analysis (e.g., keyword spotting)
        is_explicit = "fuck" in lyrics_text.lower() or "shit" in lyrics_text.lower()
        return LyricsFeatures(
            analysis_model="deterministic-keyword-v1",
            song_id=song_id,
            family_friendly=not is_explicit,
            explicitness=1.0 if is_explicit else 0.0,
        )
