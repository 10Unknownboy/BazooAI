from __future__ import annotations
import logging
from typing import Optional, Dict, Any
from pydantic import BaseModel, Field

from app.models.agent import AIRequest, AIResponse
from app.agents.ai_client import AIModelClient
from app.event.event_bus import get_event_bus, BusEvent

logger = logging.getLogger(__name__)

class LyricsFeatures(BaseModel):
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
    event_suitability: Dict[str, float] = Field(default_factory=dict)

class LyricsAgent:
    """Agent responsible for analyzing song lyrics for themes, sentiment, and appropriateness."""
    
    def __init__(self, ai_client: Optional[AIModelClient] = None):
        self.ai_client = ai_client or AIModelClient()
        self.event_bus = get_event_bus()

    async def analyze_lyrics(self, song_id: str, lyrics_text: Optional[str] = None) -> LyricsFeatures:
        """Analyze lyrics and extract features."""
        
        # In a real implementation, we would check LyricsFeaturesRepository first
        # to avoid re-analyzing
        
        if not lyrics_text:
            logger.warning(f"No lyrics provided for {song_id}. Returning default features.")
            return LyricsFeatures(song_id=song_id)
            
        try:
            # We don't send full copyrighted text if possible, or we send it
            # just for analysis and don't store it
            
            # Truncate if too long
            text_to_analyze = lyrics_text[:2000] if len(lyrics_text) > 2000 else lyrics_text
            
            request = AIRequest(
                agent_id="lyrics_agent",
                task_type="lyrics_analysis",
                context={"lyrics": text_to_analyze},
                prompt="Analyze these lyrics. Identify language, themes, sentiment (-1 to 1), mood, and score various content categories (0 to 1) like romance, sadness, celebration, explicit content, etc."
            )
            response = await self.ai_client.decide(request)
            
            if response.success and response.content:
                data = response.content
                features = LyricsFeatures(
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
                    event_suitability=data.get("event_suitability", {})
                )
                
                self.event_bus.publish(BusEvent.LYRICS_ANALYSIS_COMPLETE, source="lyrics_agent", data={"song_id": song_id})
                return features
                
        except Exception as e:
            logger.warning(f"AI lyrics analysis failed: {e}. Falling back to basic analysis.")
            
        # Fallback to basic deterministic analysis (e.g., keyword spotting)
        is_explicit = "fuck" in lyrics_text.lower() or "shit" in lyrics_text.lower()
        return LyricsFeatures(
            song_id=song_id,
            family_friendly=not is_explicit,
            explicitness=1.0 if is_explicit else 0.0
        )
