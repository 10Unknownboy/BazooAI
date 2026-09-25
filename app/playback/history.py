from __future__ import annotations

import logging
import time
from typing import Dict, List, Optional, Any

from app.models.song import Song
from app.database.repositories import get_repository

logger = logging.getLogger(__name__)


class PlayHistoryRecord:
    """Record of a single play."""
    def __init__(self, event_id: str, song_id: str, timestamp: float, score: float, 
                 components: Dict[str, float], penalties: Dict[str, float], 
                 vibe: Any, energy: float, prev_song_id: Optional[str], request_id: Optional[str]):
        self.event_id = event_id
        self.song_id = song_id
        self.timestamp = timestamp
        self.score = score
        self.components = components
        self.penalties = penalties
        self.vibe = vibe
        self.energy = energy
        self.prev_song_id = prev_song_id
        self.request_id = request_id


class PlaybackHistory:
    """Complete playback history logger."""
    
    def __init__(self):
        self.repo = get_repository("play_history")
        
    def record_play(
        self, event_id: str, song: Song, score: float, components: Dict[str, float],
        penalties: Dict[str, float], vibe: Any, energy: float, prev_song: Optional[Song], 
        request_id: Optional[str]
    ):
        """Record a played song."""
        try:
            record = PlayHistoryRecord(
                event_id=event_id,
                song_id=song.id,
                timestamp=time.time(),
                score=score,
                components=components,
                penalties=penalties,
                vibe=vibe,
                energy=energy,
                prev_song_id=prev_song.id if prev_song else None,
                request_id=request_id
            )
            self.repo.save(record)
        except Exception as e:
            logger.error(f"Error recording play history: {e}")
            
    def get_history(self, event_id: str) -> List[PlayHistoryRecord]:
        """Get full history for an event."""
        try:
            return self.repo.get_by_event(event_id)
        except Exception as e:
            logger.error(f"Error retrieving play history: {e}")
            return []
            
    def get_recent(self, event_id: str, n: int = 20) -> List[PlayHistoryRecord]:
        """Get recent plays for an event."""
        try:
            return self.repo.get_recent(event_id, n)
        except Exception as e:
            logger.error(f"Error retrieving recent play history: {e}")
            return []
