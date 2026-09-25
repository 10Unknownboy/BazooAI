from __future__ import annotations
import os
import logging
from pathlib import Path
from app.providers.base import MusicProvider

logger = logging.getLogger(__name__)

class LocalFileProvider(MusicProvider):
    """Local file provider stub."""
    
    SUPPORTED_EXTS = {'.mp3', '.wav', '.flac', '.ogg'}

    def __init__(self, directory: str):
        self.directory = directory
        self._index: dict[str, dict] = {}
        self._playing = False
        self._current_song: dict | None = None
        self._build_index()

    def _build_index(self):
        logger.info(f"Scanning local directory: {self.directory}")
        if not os.path.exists(self.directory):
            logger.warning(f"Directory {self.directory} does not exist.")
            return
            
        for root, _, files in os.walk(self.directory):
            for file in files:
                ext = Path(file).suffix.lower()
                if ext in self.SUPPORTED_EXTS:
                    path = os.path.join(root, file)
                    song_id = f"local_{hash(path)}"
                    self._index[song_id] = {
                        "id": song_id,
                        "title": Path(file).stem,
                        "path": path,
                        "duration": 210.0 # Stub duration
                    }
        logger.info(f"Indexed {len(self._index)} local files.")

    def search(self, query: str, limit: int = 10) -> list[dict]:
        results = [song for song in self._index.values() if query.lower() in song["title"].lower()]
        return results[:limit]

    def get_song(self, song_id: str) -> dict | None:
        return self._index.get(song_id)

    def play(self, song_id: str) -> bool:
        song = self.get_song(song_id)
        if not song:
            return False
        self._current_song = song
        self._playing = True
        logger.info(f"LocalFileProvider playing: {song['title']} (audio playback is future work)")
        return True

    def pause(self) -> bool:
        self._playing = False
        logger.info("LocalFileProvider paused")
        return True

    def resume(self) -> bool:
        if self._current_song:
            self._playing = True
            logger.info("LocalFileProvider resumed")
            return True
        return False

    def stop(self) -> bool:
        self._playing = False
        self._current_song = None
        logger.info("LocalFileProvider stopped")
        return True

    def skip(self) -> bool:
        self.stop()
        logger.info("LocalFileProvider skipped")
        return True

    def previous(self) -> bool:
        logger.info("LocalFileProvider previous")
        return True

    def seek(self, seconds: float) -> bool:
        logger.info(f"LocalFileProvider seek to {seconds}")
        return True

    def volume(self, value: int) -> bool:
        logger.info(f"LocalFileProvider volume set to {value}")
        return True

    def current_song(self) -> dict | None:
        return self._current_song

    def get_remaining_time(self) -> float:
        return 0.0

    def is_playing(self) -> bool:
        return self._playing
