from __future__ import annotations
import os
import logging
from pathlib import Path

try:
    import pygame
    PYGAME_AVAILABLE = True
except ImportError:
    PYGAME_AVAILABLE = False

try:
    from tinytag import TinyTag
    TINYTAG_AVAILABLE = True
except ImportError:
    TINYTAG_AVAILABLE = False

from app.providers.base import MusicProvider

logger = logging.getLogger(__name__)

class LocalFileProvider(MusicProvider):
    """Local file provider with actual audio playback via pygame."""
    
    SUPPORTED_EXTS = {'.mp3', '.wav', '.flac', '.ogg'}

    def __init__(self, directory: str):
        global PYGAME_AVAILABLE
        self.directory = directory
        self._index: dict[str, dict] = {}
        self._playing = False
        self._current_song: dict | None = None
        self._paused = False

        if PYGAME_AVAILABLE:
            try:
                if not pygame.mixer.get_init():
                    pygame.mixer.init()
            except Exception as e:
                logger.error(f"Failed to initialize pygame mixer: {e}")
                PYGAME_AVAILABLE = False
        else:
            logger.warning("pygame not installed. Audio playback will use pseudo-playback fallback.")

        self._build_index()

    def _build_index(self):
        logger.info(f"Scanning local directory: {self.directory}")
        if not self.directory or not os.path.exists(self.directory):
            logger.warning(f"Directory {self.directory} does not exist.")
            return
            
        for root, _, files in os.walk(self.directory):
            for file in files:
                ext = Path(file).suffix.lower()
                if ext in self.SUPPORTED_EXTS:
                    path = os.path.join(root, file)
                    # use string path as seed for hash instead of random to ensure stable IDs across restarts
                    song_id = f"local_{abs(hash(path))}"
                    
                    title = Path(file).stem
                    artist = "Unknown Artist"
                    duration = 210.0
                    
                    if TINYTAG_AVAILABLE:
                        try:
                            tag = TinyTag.get(path)
                            if tag.title:
                                title = tag.title
                            if tag.artist:
                                artist = tag.artist
                            if tag.duration:
                                duration = tag.duration
                        except Exception as e:
                            logger.debug(f"Could not read metadata for {path}: {e}")

                    self._index[song_id] = {
                        "id": song_id,
                        "title": title,
                        "artist": artist,
                        "path": path,
                        "duration": duration,
                        "type": "local"
                    }
        logger.info(f"Indexed {len(self._index)} local files.")

    def search(self, query: str, limit: int = 10) -> list[dict]:
        query = query.lower()
        results = []
        for song in self._index.values():
            if query in song["title"].lower() or query in song["artist"].lower():
                results.append(song)
        return results[:limit]

    def get_song(self, song_id: str) -> dict | None:
        return self._index.get(song_id)

    def play(self, song_id: str) -> bool:
        song = self.get_song(song_id)
        if not song:
            return False
            
        import time
        if PYGAME_AVAILABLE:
            try:
                pygame.mixer.music.load(song["path"])
                pygame.mixer.music.play()
                self._playing = True
                self._paused = False
                self._current_song = song
                logger.info(f"LocalFileProvider playing: {song['title']}")
                return True
            except Exception as e:
                logger.error(f"Failed to play {song['path']}: {e}")
                return False
        else:
            self._current_song = song
            self._playing = True
            self._paused = False
            self._start_time = time.time()
            self._elapsed = 0.0
            logger.info(f"LocalFileProvider pseudo-playing: {song['title']}")
            return True

    def pause(self) -> bool:
        import time
        if PYGAME_AVAILABLE and self._playing:
            pygame.mixer.music.pause()
        elif self._playing and not self._paused:
            self._elapsed += time.time() - getattr(self, "_start_time", time.time())
        self._paused = True
        logger.info("LocalFileProvider paused")
        return True

    def resume(self) -> bool:
        import time
        if self._current_song and self._paused:
            if PYGAME_AVAILABLE:
                pygame.mixer.music.unpause()
            else:
                self._start_time = time.time()
            self._paused = False
            logger.info("LocalFileProvider resumed")
            return True
        return False

    def stop(self) -> bool:
        if PYGAME_AVAILABLE:
            try:
                pygame.mixer.music.stop()
            except Exception:
                pass
        self._playing = False
        self._paused = False
        self._current_song = None
        self._elapsed = 0.0
        logger.info("LocalFileProvider stopped")
        return True

    def skip(self) -> bool:
        self.stop()
        logger.info("LocalFileProvider skipped")
        return True

    def previous(self) -> bool:
        self.stop()
        logger.info("LocalFileProvider previous")
        return True

    def seek(self, seconds: float) -> bool:
        import time
        if PYGAME_AVAILABLE and self._playing:
            try:
                pygame.mixer.music.set_pos(seconds)
                logger.info(f"LocalFileProvider seek to {seconds}")
                return True
            except Exception as e:
                logger.error(f"Seek failed: {e}")
                return False
        elif self._playing:
            self._elapsed = seconds
            self._start_time = time.time()
            logger.info(f"LocalFileProvider pseudo-seek to {seconds}")
            return True
        return False

    def volume(self, value: int) -> bool:
        if PYGAME_AVAILABLE:
            # value is 0-100, pygame volume is 0.0 to 1.0
            try:
                pygame.mixer.music.set_volume(value / 100.0)
            except Exception:
                pass
        logger.info(f"LocalFileProvider volume set to {value}")
        return True

    def current_song(self) -> dict | None:
        return self._current_song

    def get_remaining_time(self) -> float:
        import time
        if not self._current_song:
            return 0.0
        if PYGAME_AVAILABLE and self._playing and not self._paused:
            try:
                pos_ms = pygame.mixer.music.get_pos()
                if pos_ms >= 0:
                    pos_sec = pos_ms / 1000.0
                    return max(0.0, self._current_song["duration"] - pos_sec)
            except Exception:
                pass
        elif self._playing:
            elapsed = getattr(self, "_elapsed", 0.0)
            if not self._paused:
                elapsed += time.time() - getattr(self, "_start_time", time.time())
            return max(0.0, self._current_song["duration"] - elapsed)
        return 0.0

    def is_playing(self) -> bool:
        if PYGAME_AVAILABLE:
            try:
                if pygame.mixer.music.get_busy() or (self._playing and self._paused):
                    return True
            except Exception:
                pass
        
        if self._playing:
            if self.get_remaining_time() <= 0:
                self._playing = False
                self._current_song = None
        return self._playing
