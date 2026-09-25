from __future__ import annotations

import logging
from typing import Dict, Any, Union

from app.event.event_bus import get_event_bus, BusEvent

logger = logging.getLogger(__name__)


class EnergyManager:
    """Energy tracking system."""
    
    def __init__(self):
        self.current_energy = 50.0
        self.target_energy = 50.0
        self.event_bus = get_event_bus()
        
    def set_target_energy(self, value: Union[float, str]):
        """Set target energy. Accepts absolute value or relative string like '+10'."""
        try:
            if isinstance(value, str) and (value.startswith('+') or value.startswith('-')):
                change = float(value)
                self.target_energy = max(0.0, min(100.0, self.target_energy + change))
            else:
                self.target_energy = max(0.0, min(100.0, float(value)))
            self._publish_change()
        except Exception as e:
            logger.error(f"Error setting target energy: {e}")
            
    def get_current_energy(self) -> float:
        """Get current energy."""
        return self.current_energy
        
    def get_target_energy(self) -> float:
        """Get target energy."""
        return self.target_energy
        
    def interpolate_from_curve(self, elapsed_minutes: float, curve: Dict[float, float]) -> float:
        """Interpolate energy based on time curve."""
        # Stub implementation
        return 50.0
        
    def calculate_energy_match(self, song_energy: float, target: float) -> float:
        """Calculate energy match (0-1)."""
        diff = abs(song_energy - target)
        return max(0.0, 1.0 - (diff / 100.0))
        
    def _publish_change(self):
        self.event_bus.publish(BusEvent("ENERGY_CHANGED", {"target_energy": self.target_energy}))
