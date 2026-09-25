from __future__ import annotations
import logging
from typing import Dict, Any, Optional

from app.models.feedback import SongFeedback
from app.models.song import Song

logger = logging.getLogger(__name__)

class PreferenceUpdater:
    """Updates immediate contextual preferences based on feedback."""

    def __init__(self, learned_preference_repo):
        self.repo = learned_preference_repo

    def update_from_feedback(self, feedback: SongFeedback, reward: float, event_state: Any):
        """Update contextual preference records from feedback and reward."""
        if reward == 0:
            return

        context_key = self._generate_context_key(event_state)
        song_id = feedback.song_id

        # Get existing record
        record = self.repo.get_preference(song_id, context_key)
        
        if record:
            # Running average
            n = record.get("sample_count", 0)
            old_score = record.get("score", 0.0)
            new_score = (old_score * n + reward) / (n + 1)
            new_count = n + 1
        else:
            new_score = reward
            new_count = 1

        self.repo.save_preference(song_id, context_key, {
            "score": new_score,
            "sample_count": new_count
        })
        logger.info(f"Updated preference for {song_id} in {context_key}: new score {new_score:.2f} (n={new_count})")

    def get_adjustment(self, song: Song, event_state: Any) -> float:
        """Get score adjustment for a song based on learned preferences."""
        context_key = self._generate_context_key(event_state)
        record = self.repo.get_preference(song.id, context_key)
        
        if not record:
            return 0.0
            
        score = record.get("score", 0.0)
        # Cap impact to avoid over-correcting from single examples
        return max(-0.3, min(0.3, score))

    def _generate_context_key(self, event_state: Any) -> str:
        """Generate a context string from the current state."""
        vibe = event_state.current_vibe if hasattr(event_state, 'current_vibe') else "unknown"
        event_type = event_state.event_type if hasattr(event_state, 'event_type') else "unknown"
        return f"{event_type}_{vibe}"
