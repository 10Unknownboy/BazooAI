from __future__ import annotations

import logging
from typing import Dict, Any

from app.models.song import Song
from app.event.event_bus import get_event_bus, BusEvent

logger = logging.getLogger(__name__)


class VibeVector:
    """Representation of a vibe."""
    def __init__(self, acousticness: float, danceability: float, energy: float, valence: float):
        self.acousticness = acousticness
        self.danceability = danceability
        self.energy = energy
        self.valence = valence


class VibeEngine:
    """Vibe vector system."""
    
    PRESETS = {
        "party": VibeVector(0.1, 0.9, 0.9, 0.8),
        "chill": VibeVector(0.7, 0.5, 0.3, 0.5),
        "romantic": VibeVector(0.6, 0.4, 0.4, 0.7),
        "sad": VibeVector(0.8, 0.3, 0.2, 0.1),
    }
    
    def __init__(self):
        self.current_vibe = self.PRESETS["chill"]
        self.event_bus = get_event_bus()
        
    def set_vibe(self, preset_name: str, force: bool = False):
        """Maps preset to VibeVector."""
        if preset_name in self.PRESETS:
            target = self.PRESETS[preset_name]
            if force:
                self.current_vibe = target
            else:
                self.blend_toward(target)
            self._publish_change()
        else:
            logger.warning(f"Unknown vibe preset: {preset_name}")
            
    def blend_toward(self, target_vector: VibeVector, alpha: float = 0.3):
        """Gradual transition towards a target vibe."""
        self.current_vibe.acousticness = (1 - alpha) * self.current_vibe.acousticness + alpha * target_vector.acousticness
        self.current_vibe.danceability = (1 - alpha) * self.current_vibe.danceability + alpha * target_vector.danceability
        self.current_vibe.energy = (1 - alpha) * self.current_vibe.energy + alpha * target_vector.energy
        self.current_vibe.valence = (1 - alpha) * self.current_vibe.valence + alpha * target_vector.valence
        self._publish_change()
        
    def get_current_vibe(self) -> VibeVector:
        """Get the current vibe vector."""
        return self.current_vibe
        
    def calculate_vibe_match(self, song: Song, current_vibe: VibeVector) -> float:
        """Calculate vibe match (0-1)."""
        # Simplistic Euclidean distance inverse
        try:
            dist = (
                (getattr(song, "acousticness", 0.5) - current_vibe.acousticness) ** 2 +
                (getattr(song, "danceability", 0.5) - current_vibe.danceability) ** 2 +
                (getattr(song, "energy", 0.5) - current_vibe.energy) ** 2 +
                (getattr(song, "valence", 0.5) - current_vibe.valence) ** 2
            ) ** 0.5
            return max(0.0, 1.0 - (dist / 2.0))
        except Exception as e:
            logger.error(f"Error calculating vibe match: {e}")
            return 0.5
            
    def _publish_change(self):
        self.event_bus.publish(BusEvent("VIBE_CHANGED", {"vibe": self.current_vibe}))
