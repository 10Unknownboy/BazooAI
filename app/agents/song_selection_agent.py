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

    async def select_songs(self, event_state: EventState, candidates: List[Song], top_n: int = 5) -> List[ScoredCandidate]:
        """Score candidate songs and return the top N recommendations."""
        
        # 1. Deterministic scoring (simplified for placeholder)
        scored = []
        for song in candidates:
            # Placeholder deterministic logic
            score = 0.5
            breakdown = {"base": 0.5}
            scored.append(ScoredCandidate(song=song, score=score, breakdown=breakdown))
            
        scored.sort(key=lambda x: x.score, reverse=True)
        top_candidates = scored[:top_n]
        
        # 2. Optional AI review
        try:
            candidates_data = [{"id": c.song.id, "title": c.song.title, "artist": c.song.artist} for c in top_candidates]
            request = AIRequest(
                agent_id="song_selection_agent",
                task_type="queue_review",
                context={
                    "event_state": event_state.model_dump(mode="json"),
                    "candidates": candidates_data
                },
                prompt="Review these candidate songs for the current event state and re-rank them if necessary. Return the IDs in ranked order."
            )
            response = await self.ai_client.decide(request)
            
            if response.success and response.content and "ranked_ids" in response.content:
                ranked_ids = response.content["ranked_ids"]
                # Reorder top_candidates based on AI ranking
                ranked_candidates = []
                for song_id in ranked_ids:
                    for c in top_candidates:
                        if c.song.id == song_id:
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
