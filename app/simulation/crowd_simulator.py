from __future__ import annotations
import logging
import random
from typing import Dict, Any

from app.models.song import Song
from app.models.feedback import SongFeedback, TransitionFeedback
from datetime import datetime

logger = logging.getLogger(__name__)

class CrowdSimulator:
    """Generates simulated crowd feedback for testing."""

    def __init__(self, variance: float = 1.0):
        self.variance = variance

    def generate_feedback(self, song: Song, event_state: Any) -> SongFeedback:
        """Generate plausible feedback based on song and state match."""
        base_score = 7.0
        
        # Configurable rules
        vibe = event_state.current_vibe if hasattr(event_state, 'current_vibe') else None
        song_vibe = getattr(song, 'vibe', None)
        
        if vibe and song_vibe:
            if vibe == song_vibe:
                base_score += 2.0
            else:
                base_score -= 2.0
                
        # Random variation
        noise = (random.random() * 2 - 1) * self.variance
        final_score = max(1.0, min(10.0, base_score + noise))
        int_score = int(round(final_score))
        
        return SongFeedback(
            event_id=getattr(event_state, 'event_id', 'sim_event'),
            song_id=song.id,
            timestamp=datetime.now(),
            overall_rating=int_score,
            energy_rating=int_score,
            song_choice_rating=int_score,
            transition_rating=int_score,
            vibe_rating=int_score,
            context={"simulated": True}
        )

    def simulate_crowd_response(self, song: Song, event_state: Any) -> Dict[str, int]:
        """Returns raw dict of simulated response dimensions."""
        fb = self.generate_feedback(song, event_state)
        return {
            "overall": fb.overall_rating,
            "energy": fb.energy_rating,
            "vibe": fb.vibe_rating
        }
