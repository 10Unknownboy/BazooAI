from __future__ import annotations
from abc import ABC, abstractmethod
import logging

logger = logging.getLogger(__name__)

class MusicMetadataProvider(ABC):
    """Abstract metadata provider interface (spec §7, 68)."""
    
    provider_name: str
    
    @abstractmethod
    async def search_song(self, query: str, limit: int = 10) -> list[dict]:
        """Search for a song and return metadata."""
        pass
        
    @abstractmethod
    async def get_metadata(self, provider_id: str) -> dict | None:
        """Get rich metadata for a specific song ID."""
        pass
        
    @abstractmethod
    async def get_audio_features(self, provider_id: str) -> dict | None:
        """Get pre-computed audio features if available."""
        pass
