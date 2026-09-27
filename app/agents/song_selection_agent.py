from __future__ import annotations
import logging
from typing import Optional, Dict, Any, List

from app.models.song import Song
from app.models.event import EventState
from app.models.agent import AIRequest, AIResponse, ScoringSnapshot
from app.agents.ai_client import AIModelClient

logger = logging.getLogger(__name__)

class ScoredCandidate:
    def __init__(self, song: Song, score: float, breakdown: Dict[str, float]):
        self.song = song
        self.score = score
        self.breakdown = breakdown

class SongSelectionAgent:
    """Agent responsible for selecting and scoring candidate songs."""
    
    def __init__(self, ai_client: Optional[AIModelClient] = None):
        self.ai_client = ai_client or AIModelClient()

    async def select_songs(self, event_state: EventState, candidates: List[ScoredCandidate], top_n: int = 5) -> List[ScoredCandidate]:
        """Score candidate songs and return the top N recommendations."""
        
        # 1. Sort by pre-calculated score
        candidates.sort(key=lambda x: x.score, reverse=True)
        top_candidates = candidates[:top_n]
        
        # 2. Optional AI review
        try:
            from app.models.base import AIMessageType
            candidates_data = [{"id": c.song.song_id, "title": c.song.title, "artist": c.song.artist} for c in top_candidates]
            request = AIRequest(
                message_type=AIMessageType.DJ_DECISION,
                candidate_songs=candidates_data,
                request_data={
                    "event_state": event_state.model_dump(mode="json"),
                    "prompt": "Review these candidate songs for the current event state and re-rank them if necessary. Return the IDs in ranked order."
                }
            )
            response = await self.ai_client.decide(request)
            
            if response.success and response.recommended_song_ids:
                ranked_ids = response.recommended_song_ids
                # Reorder top_candidates based on AI ranking
                ranked_candidates = []
                for song_id in ranked_ids:
                    for c in top_candidates:
                        if c.song.song_id == song_id:
                            ranked_candidates.append(c)
                            break
                
                # Append any that AI missed
                for c in top_candidates:
                    if c not in ranked_candidates:
                        ranked_candidates.append(c)
                        
                return ranked_candidates[:top_n]
                
        except Exception as e:
            logger.warning(f"AI song selection review failed: {e}. Returning deterministically scored candidates.")
            
        return top_candidates
