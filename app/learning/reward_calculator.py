from __future__ import annotations
import logging
from typing import Dict, Any

from app.models.feedback import SongFeedback, TransitionFeedback
from app.config.settings import load_scoring_config

logger = logging.getLogger(__name__)

class RewardCalculator:
    """Calculates normalized reward values from feedback."""

    def __init__(self):
        self.config = load_scoring_config()
        self.weights = self.config.get("reward_weights", {
            "song_choice": 0.35,
            "energy": 0.20,
            "transition": 0.20,
            "vibe": 0.25
        })

    def _normalize(self, rating: float) -> float:
        """Normalize 1-10 scale to -1.0 to +1.0."""
        # 1 -> -1.0, 5.5 -> 0, 10 -> 1.0
        return ((rating - 1) / 4.5) - 1.0

    def calculate_reward(self, feedback: SongFeedback) -> float:
        """Calculate normalized reward from SongFeedback."""
        # Use overall rating if specific dimensions are missing or not applicable
        song_choice = feedback.song_choice_rating or feedback.overall_rating
        energy = feedback.energy_rating or feedback.overall_rating
        transition = feedback.transition_rating or feedback.overall_rating
        vibe = feedback.vibe_rating or feedback.overall_rating

        raw_score = (
            self.weights.get("song_choice", 0.35) * song_choice +
            self.weights.get("energy", 0.20) * energy +
            self.weights.get("transition", 0.20) * transition +
            self.weights.get("vibe", 0.25) * vibe
        )
        
        normalized = self._normalize(raw_score)
        logger.debug(f"Calculated reward {normalized:.2f} for song {feedback.song_id}")
        return max(-1.0, min(1.0, normalized))

    def calculate_transition_reward(self, feedback: TransitionFeedback) -> float:
        """Calculate normalized reward from TransitionFeedback."""
        normalized = self._normalize(feedback.rating)
        logger.debug(f"Calculated transition reward {normalized:.2f} from {feedback.from_song_id} to {feedback.to_song_id}")
        return max(-1.0, min(1.0, normalized))
