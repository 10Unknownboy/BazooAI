from __future__ import annotations
import logging
from typing import Optional, Dict, Any, List

from app.models.feedback import SongFeedback
from app.models.event import EventState
from app.models.song import Song
from app.event.event_bus import get_event_bus, BusEvent

logger = logging.getLogger(__name__)

class LearningAgent:
    """Agent responsible for processing feedback and adjusting preferences."""
    
    def __init__(self):
        self.event_bus = get_event_bus()

    def process_feedback(self, feedback: SongFeedback, event_state: EventState) -> None:
        """Process incoming feedback from the crowd or DJ."""
        logger.info(f"Processing feedback for song {feedback.song_id}")
        
        reward = self.calculate_reward(feedback)
        self.apply_immediate_learning(feedback, event_state, reward)
        self.store_learning_record(event_state, "play_song", reward, event_state, {"song_id": feedback.song_id})
        
        self.event_bus.publish(BusEvent.FEEDBACK_RECEIVED, {"feedback_id": feedback.feedback_id, "reward": reward})

    def calculate_reward(self, feedback: SongFeedback) -> float:
        """Calculate a reward score (-1.0 to 1.0) based on feedback."""
        # Map 1-10 rating to -1.0 to 1.0
        # 1 -> -1.0, 5 -> -0.11, 5.5 -> 0.0, 10 -> 1.0
        normalized = (feedback.overall_rating - 5.5) / 4.5
        return max(-1.0, min(1.0, normalized))

    def apply_immediate_learning(self, feedback: SongFeedback, event_state: EventState, reward: float) -> None:
        """Apply learning immediately to the current event context."""
        # e.g., if negative, lower the score of similar songs for this event
        pass

    def store_learning_record(self, state: EventState, action: str, reward: float, next_state: EventState, context: Dict[str, Any]) -> None:
        """Store the learning record for long-term preferences."""
        # In a real implementation, this would save to LearnedPreferenceRepository
        pass

    def get_learned_adjustment(self, song: Song, event_state: EventState) -> float:
        """Get the score adjustment based on learned preferences for this song in this context."""
        # Returns a float to be added to the song's score
        return 0.0
