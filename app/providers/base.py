from __future__ import annotations
from abc import ABC, abstractmethod

class MusicProvider(ABC):
    """Abstract music provider interface (spec §6)."""
    
    @abstractmethod
    def search(self, query: str, limit: int = 10) -> list[dict]:
        """Search for songs."""
        pass
        
    @abstractmethod
    def get_song(self, song_id: str) -> dict | None:
        """Get details of a specific song."""
        pass
        
    @abstractmethod
    def play(self, song_id: str) -> bool:
        """Play a specific song."""
        pass
        
    @abstractmethod
    def pause(self) -> bool:
        """Pause playback."""
        pass
        
    @abstractmethod
    def resume(self) -> bool:
        """Resume playback."""
        pass
        
    @abstractmethod
    def stop(self) -> bool:
        """Stop playback completely."""
        pass
        
    @abstractmethod
    def skip(self) -> bool:
        """Skip to the next track."""
        pass
        
    @abstractmethod
    def previous(self) -> bool:
        """Go back to the previous track."""
        pass
        
    @abstractmethod
    def seek(self, seconds: float) -> bool:
        """Seek to a specific time in the current song."""
        pass
        
    @abstractmethod
    def volume(self, value: int) -> bool:
        """Set the playback volume (0-100)."""
        pass
        
    @abstractmethod
    def current_song(self) -> dict | None:
        """Get the currently playing song."""
        pass
        
    @abstractmethod
    def get_remaining_time(self) -> float:
        """Get remaining time in seconds for the current song."""
        pass
        
    @abstractmethod
    def is_playing(self) -> bool:
        """Check if audio is currently playing."""
        pass
