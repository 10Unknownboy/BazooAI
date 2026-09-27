from __future__ import annotations

import logging

from app.database.repositories import get_repository
from app.event.event_bus import BusEvent, get_event_bus
from app.models.base import PenaltyComponents, ScoreComponents
from app.models.event import EventState
from app.models.feedback import RewardRecord, SongFeedback
from app.models.song import Song

logger = logging.getLogger(__name__)


class LearningAgent:
    """Agent responsible for processing feedback and adjusting preferences."""

    def __init__(self):
        self.event_bus = get_event_bus()
        self.reward_repository = get_repository("reward")
        self.preference_repository = get_repository("learned_preference")
        self._preference_cache: dict[tuple[str, str, str], float] = {}

    def process_feedback(
        self,
        feedback: SongFeedback,
        event_state: EventState,
        selected_song: Song | None = None,
        score: float = 0.0,
        score_components: ScoreComponents | None = None,
        penalty_components: PenaltyComponents | None = None,
    ) -> None:
        """Process incoming feedback from the crowd or DJ."""
        logger.info(f"Processing feedback for song {feedback.song_id}")

        reward = self.calculate_reward(feedback)
        self.apply_immediate_learning(feedback, event_state, reward)
        self.store_learning_record(
            feedback,
            event_state,
            reward,
            selected_song,
            score,
            score_components,
            penalty_components,
        )

        self.event_bus.publish(
            BusEvent.AGENT_DECISION,
            source="learning_agent",
            data={"feedback_id": feedback.feedback_id, "reward": reward},
        )

    def calculate_reward(self, feedback: SongFeedback) -> float:
        """Calculate a reward score (-1.0 to 1.0) based on feedback."""
        # Map 1-10 rating to -1.0 to 1.0
        # 1 -> -1.0, 5 -> -0.11, 5.5 -> 0.0, 10 -> 1.0
        normalized = (feedback.overall_rating - 5.5) / 4.5
        return max(-1.0, min(1.0, normalized))

    def apply_immediate_learning(
        self, feedback: SongFeedback, event_state: EventState, reward: float
    ) -> None:
        """Apply learning immediately to the current event context."""
        event_state.crowd_feedback_history.append(
            {
                "song_id": feedback.song_id,
                "reward": reward,
                "event_type": event_state.event_config.event_type.value,
                "vibe": event_state.current_vibe.value,
                "previous_genre": feedback.previous_genre,
                "timestamp": feedback.timestamp.isoformat(),
            }
        )

    def store_learning_record(
        self,
        feedback: SongFeedback,
        state: EventState,
        reward: float,
        song: Song | None,
        score: float,
        score_components: ScoreComponents | None,
        penalty_components: PenaltyComponents | None,
    ) -> None:
        """Persist the complete contextual reward and update event-specific preference."""
        age_range = [state.event_config.min_age, state.event_config.max_age]
        record = RewardRecord(
            event_id=state.event_id,
            decision_epoch=feedback.decision_epoch,
            state_vibe=feedback.current_vibe or state.vibe_vector,
            state_energy=feedback.current_energy
            if feedback.current_energy is not None
            else state.current_energy,
            state_event_type=state.event_config.event_type.value,
            state_event_progress=feedback.event_progress
            if feedback.event_progress is not None
            else state.event_progress,
            state_recent_genres=state.recent_genres[-5:],
            state_recent_artists=state.recent_artists[-5:],
            state_audience_age=age_range,
            action_song_id=feedback.song_id,
            action_score=score,
            action_score_components=score_components,
            action_penalty_components=penalty_components,
            reward=reward,
            raw_feedback=feedback.model_dump(mode="json"),
            next_state_vibe=state.vibe_vector,
            next_state_energy=state.current_energy,
            next_state_event_progress=state.event_progress,
            context={
                "song_title": song.title if song else None,
                "song_genre": song.genre if song else None,
                "previous_song_ids": feedback.previous_song_ids,
                "previous_genre": feedback.previous_genre,
                "ratings": {
                    "energy": feedback.energy_rating,
                    "song_choice": feedback.song_choice_rating,
                    "transition": feedback.transition_rating,
                    "vibe": feedback.vibe_rating,
                },
            },
        )
        self.reward_repository.save(record)
        context_key = f"{state.current_vibe.value}:{round(state.target_energy, 1)}"
        self.preference_repository.update_preference(
            event_type=state.event_config.event_type.value,
            context_key=context_key,
            preference_type="song",
            preference_value=feedback.song_id,
            reward=reward,
            context=record.context,
        )
        self._preference_cache.pop(
            (state.event_config.event_type.value, context_key, feedback.song_id),
            None,
        )

    def get_learned_adjustment(self, song: Song, event_state: EventState) -> float:
        """Get the score adjustment based on learned preferences for this song in this context."""
        local_adjustment = 0.0
        for fb in event_state.crowd_feedback_history:
            if (
                fb.get("song_id") == song.song_id
                and fb.get("event_type") == event_state.event_config.event_type.value
                and fb.get("vibe") == event_state.current_vibe.value
            ):
                local_adjustment += fb.get("reward", 0.0) * 10.0
        if local_adjustment:
            return local_adjustment

        context_key = f"{event_state.current_vibe.value}:{round(event_state.target_energy, 1)}"
        cache_key = (event_state.event_config.event_type.value, context_key, song.song_id)
        if cache_key not in self._preference_cache:
            preference = self.preference_repository.get_preference(
                event_type=cache_key[0],
                context_key=cache_key[1],
                preference_type="song",
                preference_value=cache_key[2],
            )
            self._preference_cache[cache_key] = (
                float(preference["score_adjustment"]) * 10.0 if preference else 0.0
            )
        return self._preference_cache[cache_key]
