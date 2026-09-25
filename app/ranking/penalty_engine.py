from __future__ import annotations

import logging
from typing import Dict, List, Any

from app.models.song import Song
from app.models.event import EventState
from app.config.settings import load_scoring_config

logger = logging.getLogger(__name__)


class PenaltyResult:
    """Result of a single penalty calculation."""
    def __init__(self, name: str, value: float, reason: str, threshold: float):
        self.name = name
        self.value = value
        self.reason = reason
        self.threshold = threshold


class PenaltyEngine:
    """Transparent penalty calculator."""
    
    def __init__(self):
        self.config = load_scoring_config()
        self.thresholds = self.config.get("penalty_thresholds", {})
        
    def check_recency(self, song: Song, event_state: EventState) -> PenaltyResult:
        """Penalty for recently played songs."""
        # Stub
        return PenaltyResult("recency", 0.0, "Not recently played", 10.0)
        
    def check_artist_repetition(self, song: Song, event_state: EventState) -> PenaltyResult:
        """Penalty for repeating the same artist too soon."""
        return PenaltyResult("artist_repetition", 0.0, "Artist not repeated", 5.0)
        
    def calculate_penalties(self, song: Song, event_state: EventState) -> Dict[str, float]:
        """Calculates all penalties for a given song and event state."""
        penalties = []
        try:
            penalties.append(self.check_recency(song, event_state))
            penalties.append(self.check_artist_repetition(song, event_state))
            
            return {p.name: p.value for p in penalties if p.value > 0}
        except Exception as e:
            logger.error(f"Error calculating penalties for {song}: {e}")
            return {}
