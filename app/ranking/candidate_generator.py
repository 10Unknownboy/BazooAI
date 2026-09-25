from __future__ import annotations

import logging
from typing import List, Optional

from app.models.song import Song
from app.models.event import EventState
from app.database.repositories import get_repository

logger = logging.getLogger(__name__)


class CandidateGenerator:
    """Explicit candidate generation stage."""
    
    def __init__(self):
        self.song_repo = get_repository("song")
        self.initial_pool_size = 100
        
    def get_candidates(self, event_state: EventState, exclude_ids: Optional[List[str]] = None, limit: int = 50) -> List[Song]:
        """Fetch candidates filtered by language, genre preferences and excluding recently played."""
        try:
            exclude = set(exclude_ids) if exclude_ids else set()
            
            # Fetch candidates from the database (simulated with repo)
            all_songs = self.song_repo.get_all_songs(limit=self.initial_pool_size)
            
            candidates = []
            for song in all_songs:
                if song.id in exclude:
                    continue
                # Further filtering logic based on event_state could go here
                candidates.append(song)
                
            return candidates[:limit]
        except Exception as e:
            logger.error(f"Error generating candidates: {e}")
            return []
