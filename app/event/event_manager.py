from __future__ import annotations

import logging

from app.database.repositories import EventRepository, get_repository
from app.event.event_bus import BusEvent, get_event_bus
from app.models.base import PlaybackState, VibeVector, utc_now
from app.models.event import EventConfig, EventState

logger = logging.getLogger(__name__)


class EventManager:
    """Persist event lifecycle changes through the event repository."""

    def __init__(self, event_repository: EventRepository | None = None):
        self.event_repo = event_repository or get_repository("event")
        self.event_bus = get_event_bus()
        self.current_state: EventState | None = None

    def create_event(self, config: EventConfig) -> EventState:
        vibe = VibeVector.from_preset(config.starting_vibe)
        state = EventState(
            event_id=config.event_id,
            event_config=config,
            current_vibe=config.starting_vibe,
            vibe_vector=vibe,
            target_energy=vibe.energy,
            current_energy=vibe.energy,
        )
        self.current_state = state
        self.event_repo.save_event(config, state)
        return state

    def start_event(self, event_id: str) -> EventState | None:
        state = self.load_state(event_id)
        if not state or state.is_ended:
            return None
        state.event_started_at = state.event_started_at or utc_now()
        state.is_paused = False
        state.playback_state = PlaybackState.STOPPED
        self._save(state)
        self.event_bus.publish(
            BusEvent.EVENT_STARTED,
            source="event_manager",
            data={"event_id": event_id},
        )
        return state

    def pause_event(self) -> EventState | None:
        state = self._active_state()
        if not state or state.is_paused:
            return state
        state.is_paused = True
        state.event_paused_at = utc_now()
        state.playback_state = PlaybackState.PAUSED
        self._save(state)
        self.event_bus.publish(
            BusEvent.EVENT_PAUSED,
            source="event_manager",
            data={"event_id": state.event_id},
        )
        return state

    def resume_event(self) -> EventState | None:
        state = self._active_state()
        if not state or not state.is_paused:
            return state
        if state.event_paused_at:
            paused_for = utc_now() - state.event_paused_at
            if state.event_started_at:
                state.event_started_at += paused_for
        state.event_paused_at = None
        state.is_paused = False
        state.playback_state = PlaybackState.PLAYING
        self._save(state)
        self.event_bus.publish(
            BusEvent.EVENT_RESUMED,
            source="event_manager",
            data={"event_id": state.event_id},
        )
        return state

    def end_event(self) -> EventState | None:
        state = self._active_state()
        if not state:
            return None
        state.is_ended = True
        state.event_ended_at = utc_now()
        state.playback_state = PlaybackState.STOPPED
        self._save(state)
        self.event_bus.publish(
            BusEvent.EVENT_ENDED,
            source="event_manager",
            data={"event_id": state.event_id},
        )
        return state

    def load_state(self, event_id: str) -> EventState | None:
        record = self.event_repo.get_event(event_id)
        if not record:
            return None
        _, state = record
        self.current_state = state
        return state

    def update_progress(self) -> EventState | None:
        state = self._active_state()
        if not state or state.is_paused or not state.event_started_at:
            return state
        elapsed = utc_now() - state.event_started_at
        state.elapsed_minutes = max(0.0, elapsed.total_seconds() / 60.0)
        state.update_progress()
        curve_energy = state.get_target_energy_from_curve()
        if curve_energy is not None:
            state.target_energy = curve_energy
        state.last_state_update = utc_now()
        self._save(state)
        return state

    def _active_state(self) -> EventState | None:
        if self.current_state and not self.current_state.is_ended:
            return self.current_state
        active = self.event_repo.get_active_event()
        if not active:
            return None
        _, self.current_state = active
        return self.current_state

    def _save(self, state: EventState) -> None:
        self.current_state = state
        self.event_repo.save_event(state.event_config, state)
