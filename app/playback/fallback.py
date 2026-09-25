from __future__ import annotations

import logging
from typing import List

from app.models.song import Song
from app.models.event import EventState
from app.event.event_bus import get_event_bus, BusEvent

logger = logging.getLogger(__name__)


class FallbackManager:
    """Fallback mode coordinator when AI or APIs are unavailable."""
    
    def __init__(self):
        self._is_fallback = False
        self.event_bus = get_event_bus()
        
    def is_fallback_mode(self) -> bool:
        """Check if system is currently in fallback mode."""
        return self._is_fallback
        
    def enter_fallback(self, reason: str):
        """Enter fallback mode."""
        if not self._is_fallback:
            self._is_fallback = True
            logger.warning(f"Entering fallback mode: {reason}")
            self.event_bus.publish(BusEvent.SYSTEM_MODE_CHANGED, source="fallback", data={"mode": "FALLBACK", "reason": reason})
            
    def exit_fallback(self):
        """Exit fallback mode."""
        if self._is_fallback:
            self._is_fallback = False
            logger.info("Exiting fallback mode.")
            self.event_bus.publish(BusEvent.SYSTEM_MODE_CHANGED, source="fallback", data={"mode": "NORMAL"})
            
    def get_fallback_candidates(self, event_state: EventState) -> List[Song]:
        """Provide basic safe candidates purely from cached data without external calls."""
        # Simple local fetch logic placeholder
        return []
