from __future__ import annotations

import logging
import time
from typing import Optional

from app.models.event import EventState, EventConfig
from app.database.repositories import get_repository
from app.event.event_bus import get_event_bus, BusEvent

logger = logging.getLogger(__name__)


class EventManager:
    """Event lifecycle manager."""
    
    def __init__(self):
        self.event_repo = get_repository("event")
        self.event_bus = get_event_bus()
        self.current_state: Optional[EventState] = None
        
    def create_event(self, config: EventConfig) -> EventState:
        """Create a new event."""
        state = EventState(
            id="evt_" + str(int(time.time())),
            config=config,
            status="CREATED"
        )
        self.current_state = state
        self.save_state()
        return state
        
    def start_event(self, event_id: str):
        """Start the event."""
        if self.current_state and self.current_state.id == event_id:
            self.current_state.status = "ACTIVE"
            self.current_state.start_time = time.time()
            self.save_state()
            self.event_bus.publish(BusEvent("EVENT_STARTED", {"event_id": event_id}))
            
    def pause_event(self):
        """Pause the event."""
        if self.current_state and self.current_state.status == "ACTIVE":
            self.current_state.status = "PAUSED"
            self.save_state()
            self.event_bus.publish(BusEvent("EVENT_PAUSED", {"event_id": self.current_state.id}))
            
    def resume_event(self):
        """Resume the event."""
        if self.current_state and self.current_state.status == "PAUSED":
            self.current_state.status = "ACTIVE"
            self.save_state()
            self.event_bus.publish(BusEvent("EVENT_RESUMED", {"event_id": self.current_state.id}))
            
    def end_event(self):
        """End the event."""
        if self.current_state:
            self.current_state.status = "ENDED"
            self.current_state.end_time = time.time()
            self.save_state()
            self.event_bus.publish(BusEvent("EVENT_ENDED", {"event_id": self.current_state.id}))
            
    def save_state(self):
        """Persist to DB for crash recovery."""
        if self.current_state:
            try:
                self.event_repo.save(self.current_state)
            except Exception as e:
                logger.error(f"Error saving event state: {e}")
                
    def load_state(self, event_id: str) -> Optional[EventState]:
        """Restore from DB."""
        try:
            state = self.event_repo.get(event_id)
            if state:
                self.current_state = state
            return state
        except Exception as e:
            logger.error(f"Error loading event state: {e}")
            return None
            
    def update_progress(self):
        """Recalculates elapsed time and progress."""
        if self.current_state and self.current_state.status == "ACTIVE":
            # Logic to update elapsed time
            pass
