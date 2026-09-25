from __future__ import annotations
import logging
import time
from threading import Timer, Lock
from typing import Callable, Optional

from app.providers.base import MusicProvider

logger = logging.getLogger(__name__)

class MockMusicProvider(MusicProvider):
    """Mock music provider for development and testing (spec §52)."""
    
    def __init__(self, simulation_speed: float = 1.0, on_song_end: Optional[Callable] = None):
        self.simulation_speed = simulation_speed
        self.on_song_end = on_song_end
        self._current_song: dict | None = None
        self._playing = False
        self._start_time = 0.0
        self._pause_time = 0.0
        self._elapsed_before_pause = 0.0
        self._timer: Optional[Timer] = None
        self._lock = Lock()
        
        # Local mock database for search
        self._mock_db = {
            "mock_1": {"id": "mock_1", "title": "Mock Song 1", "artist": "Mock Artist", "duration": 210.0},
            "mock_2": {"id": "mock_2", "title": "Mock Song 2", "artist": "Mock Artist", "duration": 180.0},
        }

    def _cancel_timer(self):
        if self._timer:
            self._timer.cancel()
            self._timer = None

    def _handle_song_end(self):
        with self._lock:
            self._playing = False
            self._current_song = None
            self._elapsed_before_pause = 0.0
        logger.info("Mock playback: song ended.")
        if self.on_song_end:
            self.on_song_end()

    def search(self, query: str, limit: int = 10) -> list[dict]:
        logger.info(f"Mock search query: {query}")
        results = [song for song in self._mock_db.values() if query.lower() in song["title"].lower() or query.lower() in song["artist"].lower()]
        return results[:limit]

    def get_song(self, song_id: str) -> dict | None:
        return self._mock_db.get(song_id)

    def play(self, song_id: str) -> bool:
        with self._lock:
            song = self.get_song(song_id)
            if not song:
                logger.error(f"Mock play failed: song {song_id} not found.")
                return False
                
            self._cancel_timer()
            self._current_song = song
            self._playing = True
            self._elapsed_before_pause = 0.0
            self._start_time = time.time()
            
            real_duration = song.get("duration", 210.0) / self.simulation_speed
            self._timer = Timer(real_duration, self._handle_song_end)
            self._timer.start()
            logger.info(f"Mock playing: {song['title']} (sim speed {self.simulation_speed}x)")
            return True

    def pause(self) -> bool:
        with self._lock:
            if not self._playing:
                return False
            self._cancel_timer()
            self._playing = False
            now = time.time()
            self._elapsed_before_pause += (now - self._start_time) * self.simulation_speed
            logger.info("Mock paused.")
            return True

    def resume(self) -> bool:
        with self._lock:
            if self._playing or not self._current_song:
                return False
            self._playing = True
            self._start_time = time.time()
            
            duration = self._current_song.get("duration", 210.0)
            remaining_sim_time = (duration - self._elapsed_before_pause) / self.simulation_speed
            if remaining_sim_time > 0:
                self._timer = Timer(remaining_sim_time, self._handle_song_end)
                self._timer.start()
            else:
                self._handle_song_end()
            logger.info("Mock resumed.")
            return True

    def stop(self) -> bool:
        with self._lock:
            self._cancel_timer()
            self._playing = False
            self._current_song = None
            self._elapsed_before_pause = 0.0
            logger.info("Mock stopped.")
            return True

    def skip(self) -> bool:
        logger.info("Mock skipped.")
        self.stop()
        if self.on_song_end:
            self.on_song_end()
        return True

    def previous(self) -> bool:
        logger.info("Mock previous.")
        return True

    def seek(self, seconds: float) -> bool:
        with self._lock:
            if not self._current_song:
                return False
            self._cancel_timer()
            self._elapsed_before_pause = seconds
            if self._playing:
                self._start_time = time.time()
                duration = self._current_song.get("duration", 210.0)
                remaining = (duration - seconds) / self.simulation_speed
                if remaining > 0:
                    self._timer = Timer(remaining, self._handle_song_end)
                    self._timer.start()
                else:
                    self._handle_song_end()
            logger.info(f"Mock seeked to {seconds}s.")
            return True

    def volume(self, value: int) -> bool:
        logger.info(f"Mock volume set to {value}")
        return True

    def current_song(self) -> dict | None:
        return self._current_song

    def get_remaining_time(self) -> float:
        with self._lock:
            if not self._current_song:
                return 0.0
            duration = self._current_song.get("duration", 210.0)
            elapsed = self._elapsed_before_pause
            if self._playing:
                elapsed += (time.time() - self._start_time) * self.simulation_speed
            return max(0.0, duration - elapsed)

    def is_playing(self) -> bool:
        return self._playing
