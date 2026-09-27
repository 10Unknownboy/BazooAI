from __future__ import annotations

import logging
import threading
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
    def volume(self, value): pass
    def seek(self, seconds): pass


class PlaybackController:
    """Playback coordination layer bridging QueueManager and MusicProvider."""
    
    def __init__(self, queue_manager: QueueManager, provider: MusicProvider):
        self.queue = queue_manager
        self.provider = provider
        self.event_bus = get_event_bus()
        self.current_song: Optional[Song] = None
        self.is_playing = False
        
        # Start a background monitoring thread
        self._monitor_thread = threading.Thread(target=self._monitor_playback, daemon=True)
        self._monitor_thread.start()

    def _monitor_playback(self):
        import time
        while True:
            time.sleep(1)
            # If we think we are playing, but the provider says it stopped
            # (and not because we explicitly paused it)
            if self.is_playing and not self.provider.is_playing() and not getattr(self.provider, "_paused", False):
                logger.info("PlaybackController monitor detected song end.")
                self.on_song_end()
                self.play()  # Automatically start next song
        
    def play(self):
        """Start or resume playback."""
        if self.is_playing:
            return
            
        # If we have a current item and provider is paused, try resuming
        if getattr(self.provider, "_paused", False) and self.current_song:
            self.provider.resume()
            self.is_playing = True
            self.event_bus.publish(BusEvent.PLAYBACK_RESUMED, source="playback", data={})
            return

        item = self.queue.get_current()
        if item:
            # In a full system, we'd fetch the Song object.
            # We'll just create a dummy one for now if not fetched.
            self.current_song = Song(id=item.song_id, title=item.song_title, artist=item.song_artist, duration=210.0)
            
            # play() takes a song_id
            self.provider.play(item.song_id)
            self.is_playing = True
            self.event_bus.publish(BusEvent.SONG_STARTED, source="playback", data={"song_id": item.song_id})
            
    def pause(self):
        """Pause playback."""
        self.provider.pause()
        self.is_playing = False
        self.event_bus.publish(BusEvent.PLAYBACK_PAUSED, source="playback", data={})
        
    def resume(self):
        """Resume playback."""
        self.play()
        self.event_bus.publish(BusEvent.PLAYBACK_RESUMED, source="playback", data={})
        
    def stop(self):
        """Stop playback."""
        self.provider.stop()
        self.is_playing = False
        self.event_bus.publish(BusEvent.PLAYBACK_STOPPED, source="playback", data={})
        
    def skip(self):
        """Skip to next song."""
        self.on_song_end()
        self.play()
        
    def previous(self):
        """Go to previous song (not fully implemented in spec)."""
        pass
        
    def volume(self, value: int):
        """Set volume level."""
        self.provider.volume(value)
        
    def seek(self, seconds: float):
        """Seek to a position in current song."""
        self.provider.seek(seconds)
        
    def on_song_end(self):
        """Advances queue when song ends."""
        if self.current_song:
            self.event_bus.publish(BusEvent.SONG_ENDED, source="playback", data={"song_id": self.current_song.song_id})
        self.queue.advance()
        self.current_song = None
        self.is_playing = False
        
    def get_current_song(self) -> Optional[Song]:
        """Get the currently playing song."""
        return self.current_song
        
    def get_remaining_time(self) -> float:
        """Get remaining time in current song."""
        return 0.0
