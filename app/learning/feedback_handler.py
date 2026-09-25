from __future__ import annotations
import logging
from datetime import datetime
from typing import Optional, Dict, Any

from app.models.feedback import SongFeedback, TransitionFeedback, EventFeedback
from app.event.event_bus import get_event_bus, BusEvent

logger = logging.getLogger(__name__)

class FeedbackHandler:
    """Processes user and crowd feedback."""

    def __init__(self, feedback_repo):
        self.feedback_repo = feedback_repo
        self.event_bus = get_event_bus()

    def process_simple_feedback(self, event_id: str, song_id: str, rating: int, event_state: Any) -> SongFeedback:
        """Process a simple 1-10 rating for a song."""
        logger.info(f"Received simple feedback for {song_id}: {rating}")
        
        feedback = SongFeedback(
            event_id=event_id,
            song_id=song_id,
            timestamp=datetime.now(),
            overall_rating=rating,
            energy_rating=rating,
            song_choice_rating=rating,
            transition_rating=rating,
            vibe_rating=rating,
            context={
                "vibe": event_state.current_vibe if hasattr(event_state, 'current_vibe') else None,
                "energy": event_state.current_energy if hasattr(event_state, 'current_energy') else None
            }
        )
        self.feedback_repo.save_song_feedback(feedback)
        self.event_bus.publish(BusEvent.FEEDBACK_RECEIVED, {"type": "song", "data": feedback.model_dump()})
        return feedback

    def process_rich_feedback(self, event_id: str, song_id: str, overall: int, energy: int, 
                              song_choice: int, transition: int, vibe: int, event_state: Any) -> SongFeedback:
        """Process rich multi-dimensional feedback."""
        logger.info(f"Received rich feedback for {song_id}: overall {overall}")
        
        feedback = SongFeedback(
            event_id=event_id,
            song_id=song_id,
            timestamp=datetime.now(),
            overall_rating=overall,
            energy_rating=energy,
            song_choice_rating=song_choice,
            transition_rating=transition,
            vibe_rating=vibe,
            context={
                "vibe": event_state.current_vibe if hasattr(event_state, 'current_vibe') else None,
                "energy": event_state.current_energy if hasattr(event_state, 'current_energy') else None
            }
        )
        self.feedback_repo.save_song_feedback(feedback)
        self.event_bus.publish(BusEvent.FEEDBACK_RECEIVED, {"type": "song", "data": feedback.model_dump()})
        return feedback

    def process_transition_feedback(self, event_id: str, from_song_id: str, to_song_id: str, rating: int, event_state: Any) -> TransitionFeedback:
        """Process feedback specific to a transition."""
        feedback = TransitionFeedback(
            event_id=event_id,
            from_song_id=from_song_id,
            to_song_id=to_song_id,
            timestamp=datetime.now(),
            rating=rating,
            context={
                 "vibe": event_state.current_vibe if hasattr(event_state, 'current_vibe') else None
            }
        )
        self.feedback_repo.save_transition_feedback(feedback)
        self.event_bus.publish(BusEvent.FEEDBACK_RECEIVED, {"type": "transition", "data": feedback.model_dump()})
        return feedback

    def process_event_feedback(self, event_id: str, overall: int, song_selection: int, vibe: int, 
                               transitions: int, requests: int, variety: int, comments: str) -> EventFeedback:
        """Process end-of-event feedback."""
        feedback = EventFeedback(
            event_id=event_id,
            timestamp=datetime.now(),
            overall_rating=overall,
            song_selection_rating=song_selection,
            vibe_rating=vibe,
            transitions_rating=transitions,
            requests_rating=requests,
            variety_rating=variety,
            comments=comments
        )
        self.feedback_repo.save_event_feedback(feedback)
        self.event_bus.publish(BusEvent.FEEDBACK_RECEIVED, {"type": "event", "data": feedback.model_dump()})
        return feedback
