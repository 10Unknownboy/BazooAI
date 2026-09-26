from __future__ import annotations
import logging
import asyncio
from typing import Optional, Dict, Any, List

from app.models.event import EventState, EventConfig
from app.models.agent import AgentDecision
from app.event.event_bus import get_event_bus, get_runtime_state, BusEvent
from app.config.settings import get_settings

logger = logging.getLogger(__name__)

class DJOrchestrator:
    """Central coordinator for the AI DJ system."""
    
    def __init__(self):
        self.settings = get_settings()
        self.event_bus = get_event_bus()
        self.runtime_state = get_runtime_state()
        self.current_state: Optional[EventState] = None
        self.is_running = False
        
        # Subscribe to events
        self.event_bus.subscribe(BusEvent.SONG_STARTED, self._on_song_started)
        self.event_bus.subscribe(BusEvent.SONG_ENDED, self._on_song_ended)
        self.event_bus.subscribe(BusEvent.REQUEST_RECEIVED, self._on_request_received)
        self.event_bus.subscribe(BusEvent.FEEDBACK_RECEIVED, self._on_feedback_received)
        self.event_bus.subscribe(BusEvent.QUEUE_UPDATED, self._on_queue_updated)

    async def start(self, event_config: EventConfig) -> None:
        """Start the DJ session with the given configuration."""
        logger.info(f"Starting DJ Orchestrator for event: {event_config.event_id}")
        self.current_state = EventState(
            event_id=event_config.event_id,
            config=event_config
        )
        self.is_running = True
        
        # Initial decision cycle
        await self.run_decision_cycle("event_start")

    async def stop(self) -> None:
        """Stop the DJ session."""
        logger.info("Stopping DJ Orchestrator")
        self.is_running = False
        self.current_state = None

    def get_state(self) -> Optional[EventState]:
        """Get the current event state."""
        return self.current_state

    async def handle_command(self, cmd: Dict[str, Any]) -> None:
        """Handle a manual command from the user interface."""
        logger.info(f"Received manual command: {cmd}")
        # Process command and run decision cycle
        await self.run_decision_cycle("manual_command")

    async def run_decision_cycle(self, trigger: str) -> None:
        """Run the main decision loop based on a trigger."""
        if not self.is_running or not self.current_state:
            return
            
        logger.info(f"Running decision cycle triggered by: {trigger}")
        
        # 1. Update Vibe
        # 2. Check Queue
        # 3. Generate Candidates
        # 4. Score Candidates
        # 5. Apply Policies
        # 6. Select Songs
        # 7. Update Queue
        
        # Publish state update
        self.event_bus.publish(BusEvent.EVENT_STATE_UPDATED, source="orchestrator", data={"state": self.current_state.model_dump()})
        self.runtime_state.update(self.current_state)

    def _on_song_started(self, payload: Dict[str, Any]) -> None:
        if self.is_running and self.current_state:
            logger.info("Song started event received")
            # Update state with playing song
            asyncio.create_task(self.run_decision_cycle("song_begins"))

    def _on_song_ended(self, payload: Dict[str, Any]) -> None:
        if self.is_running and self.current_state:
            logger.info("Song ended event received")
            asyncio.create_task(self.run_decision_cycle("song_ending"))

    def _on_request_received(self, payload: Dict[str, Any]) -> None:
        if self.is_running and self.current_state:
            logger.info("Request received event received")
            asyncio.create_task(self.run_decision_cycle("request_received"))

    def _on_feedback_received(self, payload: Dict[str, Any]) -> None:
        if self.is_running and self.current_state:
            logger.info("Feedback received event received")
            asyncio.create_task(self.run_decision_cycle("feedback_received"))

    def _on_queue_updated(self, payload: Dict[str, Any]) -> None:
        if self.is_running and self.current_state:
            logger.info("Queue updated event received")
            # Maybe check if queue needs more songs
