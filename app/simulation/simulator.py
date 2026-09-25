from __future__ import annotations
import logging
import time
from typing import Dict, Any

from app.event.event_bus import get_event_bus
from app.learning.event_summary import EventSummaryGenerator

logger = logging.getLogger(__name__)

class MockMusicProvider:
    def __init__(self):
        self.queue = []
        
    def add_to_queue(self, song, position=None):
        if position is not None:
            self.queue.insert(position, song)
        else:
            self.queue.append(song)
            
    def get_current(self):
        return self.queue[0] if self.queue else None

class EventSimulator:
    """Simulates an event for testing and learning."""

    def __init__(self, dj_engine: Any, crowd_simulator: Any):
        self.dj_engine = dj_engine
        self.crowd_simulator = crowd_simulator
        self.event_bus = get_event_bus()

    def simulate(self, event_config: Any, speed: float = 10.0) -> Any:
        """Run a complete simulated event."""
        logger.info(f"Starting simulation at {speed}x speed")
        
        # Initialize
        self.dj_engine.start_event(event_config)
        
        # Simulate time progression (mock loop)
        for i in range(10):  # Simulate 10 song plays
            # Ask DJ engine for next action
            self.dj_engine.process_cycle()
            
            # Assume song starts playing
            song = self.dj_engine.get_current_song()
            state = self.dj_engine.get_current_state()
            
            if song:
                # Generate crowd feedback
                feedback = self.crowd_simulator.generate_feedback(song, state)
                logger.info(f"Simulated feedback for {song.title}: {feedback.overall_rating}")
                
                # Advance simulated time
                time.sleep(30.0 / speed)
                
                # Report song ended
                self.dj_engine.handle_song_end()
        
        # End event
        self.dj_engine.end_event()
        logger.info("Simulation complete")
        return {"songs_played": 10, "status": "success"}
