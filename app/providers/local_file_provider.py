from __future__ import annotations

import hashlib
import logging
import os
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

    SUPPORTED_EXTS = {".mp3", ".wav", ".flac", ".ogg"}

    def __init__(self, directory: str):
        global PYGAME_AVAILABLE
        self.directory = directory
        self._index: dict[str, dict] = {}
        self._playing = False
        self._current_song: dict | None = None
        self._paused = False
        self.last_error: str | None = None

        if PYGAME_AVAILABLE:
            try:
                if not pygame.mixer.get_init():
                    pygame.mixer.init()
            except Exception as e:
                logger.error(f"Failed to initialize pygame mixer: {e}")
                PYGAME_AVAILABLE = False
        else:
            logger.warning(
                "pygame not installed. Audio playback will use pseudo-playback fallback."
            )

        self._build_index()

    def _build_index(self):
        self._index.clear()
        logger.info(f"Scanning local directory: {self.directory}")
        if not self.directory or not os.path.exists(self.directory):
            logger.warning(f"Directory {self.directory} does not exist.")
            return

        for root, _, files in os.walk(self.directory):
            for file in files:
                ext = Path(file).suffix.lower()
                if ext in self.SUPPORTED_EXTS:
                    path = os.path.join(root, file)
                    normalized_path = os.path.normcase(os.path.abspath(path))
                    song_id = (
                        f"local_{hashlib.sha256(normalized_path.encode('utf-8')).hexdigest()[:20]}"
                    )

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
                        "type": "local",
                    }
        logger.info(f"Indexed {len(self._index)} local files.")

    def refresh(self) -> None:
        """Rescan the local directory and refresh the provider index."""
        self._build_index()

    def search(self, query: str, limit: int = 10) -> list[dict]:
        query = query.lower()
        results = []
        for song in self._index.values():
            if query in song["title"].lower() or query in song["artist"].lower():
                results.append(song)
        return results[:limit]

    def get_song(self, song_id: str) -> dict | None:
        return self._index.get(song_id)

    def list_songs(self) -> list[dict]:
        """Return indexed local tracks for database synchronization."""
        return [song.copy() for song in self._index.values()]

    @property
    def audio_available(self) -> bool:
        """Whether the local audio output backend initialized successfully."""
        return PYGAME_AVAILABLE

    def play(self, song_id: str) -> bool:
        song = self.get_song(song_id)
        if not song:
            self.last_error = (
                f"Track {song_id} is not indexed by the local music provider. "
                "Refresh the library and rebuild the queue."
            )
            logger.error(self.last_error)
            return False

        if not PYGAME_AVAILABLE:
            self.last_error = "No audio output device is available on the machine running the DJ."
            logger.error("Cannot play %s: %s", song["title"], self.last_error)
            return False
        try:
            pygame.mixer.music.load(song["path"])
            pygame.mixer.music.play()
        except (pygame.error, OSError) as e:
            self.last_error = f"Audio playback failed for {song['path']}: {e}"
            logger.exception("Failed to play local track %s", song["path"])
            self._playing = False
            self._current_song = None
            return False
        self.last_error = None
        self._playing = True
        self._paused = False
        self._current_song = song
        logger.info("LocalFileProvider playing: %s", song["title"])
        return True

    def pause(self) -> bool:
        if not PYGAME_AVAILABLE or not self._playing or self._paused:
            return False
        try:
            pygame.mixer.music.pause()
        except pygame.error:
            logger.exception("Failed to pause local playback")
            return False
        self._paused = True
        logger.info("LocalFileProvider paused")
        return True

    def resume(self) -> bool:
        if not PYGAME_AVAILABLE or not self._current_song or not self._paused:
            return False
        try:
            pygame.mixer.music.unpause()
        except pygame.error:
            logger.exception("Failed to resume local playback")
            return False
        self._paused = False
        self._playing = True
        logger.info("LocalFileProvider resumed")
        return True

    def stop(self) -> bool:
        if PYGAME_AVAILABLE:
            try:
                pygame.mixer.music.stop()
            except pygame.error:
                logger.exception("Failed to stop local playback")
                return False
        self._playing = False
        self._paused = False
        self._current_song = None
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
        if not PYGAME_AVAILABLE or not self._playing:
            return False
        try:
            pygame.mixer.music.set_pos(seconds)
        except pygame.error:
            logger.exception("Failed to seek in local playback")
            return False
        logger.info("LocalFileProvider seek to %s", seconds)
        return True

    def volume(self, value: int) -> bool:
        if not PYGAME_AVAILABLE:
            return False
        try:
            pygame.mixer.music.set_volume(value / 100.0)
        except pygame.error:
            logger.exception("Failed to set local playback volume")
            return False
        logger.info(f"LocalFileProvider volume set to {value}")
        return True

    def set_volume(self, value: int) -> bool:
        return self.volume(value)

    def current_song(self) -> dict | None:
        return self._current_song

    def get_remaining_time(self) -> float:
        if not self._current_song or not PYGAME_AVAILABLE or not self._playing:
            return 0.0
        try:
            pos_ms = pygame.mixer.music.get_pos()
        except pygame.error:
            logger.exception("Failed to read local playback position")
            return 0.0
        if pos_ms < 0:
            return 0.0
        return max(0.0, self._current_song["duration"] - pos_ms / 1000.0)

    def is_playing(self) -> bool:
        if not PYGAME_AVAILABLE or not self._playing:
            return False
        if self._paused:
            return False
        try:
            playing = pygame.mixer.music.get_busy()
        except pygame.error:
            logger.exception("Failed to query local playback state")
            return False
        if not playing:
            self._playing = False
        return playing
