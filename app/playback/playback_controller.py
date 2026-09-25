from __future__ import annotations

import logging
from typing import Optional

from app.models.song import Song
from app.queue.queue_manager import QueueManager
from app.event.event_bus import get_event_bus, BusEvent

logger = logging.getLogger(__name__)


class MusicProvider:
    """Mock interface for the music provider (e.g. Spotify, local player)."""
    def play(self): pass
    def pause(self): pass
    def stop(self): pass
    def set_volume(self, value): pass
    def seek(self, seconds): pass


class PlaybackController:
    """Playback coordination layer bridging QueueManager and MusicProvider."""
    
    def __init__(self, queue_manager: QueueManager, provider: MusicProvider):
        self.queue = queue_manager
        self.provider = provider
        self.event_bus = get_event_bus()
        self.current_song: Optional[Song] = None
        self.is_playing = False
        
    def play(self):
        """Start or resume playback."""
        item = self.queue.get_current()
        if item:
            # Assume we fetch the actual Song object based on item.song_id
            # self.current_song = fetch_song(item.song_id)
            self.provider.play()
            self.is_playing = True
            self.event_bus.publish(BusEvent("SONG_STARTED", {"song_id": item.song_id}))
            
    def pause(self):
        """Pause playback."""
        self.provider.pause()
        self.is_playing = False
        self.event_bus.publish(BusEvent("PLAYBACK_PAUSED", {}))
        
    def resume(self):
        """Resume playback."""
        self.play()
        self.event_bus.publish(BusEvent("PLAYBACK_RESUMED", {}))
        
    def stop(self):
        """Stop playback."""
        self.provider.stop()
        self.is_playing = False
        self.event_bus.publish(BusEvent("PLAYBACK_STOPPED", {}))
        
    def skip(self):
        """Skip to next song."""
        self.on_song_end()
        self.play()
        
    def previous(self):
        """Go to previous song (not fully implemented in spec)."""
        pass
        
    def volume(self, value: int):
        """Set volume level."""
        self.provider.set_volume(value)
        
    def seek(self, seconds: float):
        """Seek to a position in current song."""
        self.provider.seek(seconds)
        
    def on_song_end(self):
        """Advances queue when song ends."""
        if self.current_song:
            self.event_bus.publish(BusEvent("SONG_ENDED", {"song_id": self.current_song.id}))
        self.queue.advance()
        self.current_song = None
        self.is_playing = False
        
    def get_current_song(self) -> Optional[Song]:
        """Get the currently playing song."""
        return self.current_song
        
    def get_remaining_time(self) -> float:
        """Get remaining time in current song."""
        return 0.0
