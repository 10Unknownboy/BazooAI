from __future__ import annotations

from pathlib import Path

from app.config.settings import load_scoring_config
from app.database.repositories import get_repository
from app.models.event import EventState
from app.models.song import Song


class CandidateGenerator:
    """Generate a bounded candidate pool from the local music catalog."""

    def __init__(self):
        self.song_repo = get_repository("song")
        config = load_scoring_config().get("candidates", {})
        self.initial_pool_size = int(config.get("initial_pool_size", 200))

    def get_candidates(
        self,
        event_state: EventState,
        exclude_ids: list[str] | None = None,
        limit: int = 50,
    ) -> list[Song]:
        """Exclude queued/recent tracks, then return a popularity-ordered shortlist."""
        exclude = set(exclude_ids or ())
        songs = self.song_repo.get_all(limit=self.initial_pool_size)
        available = [
            song
            for song in songs
            if song.song_id not in exclude
            and not (
                song.source_provider == "local_file"
                and song.file_path
                and not Path(song.file_path).is_file()
            )
        ]
        available.sort(key=lambda song: song.popularity, reverse=True)
        return available[:limit]
