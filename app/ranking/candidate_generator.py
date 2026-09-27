from __future__ import annotations

import os
import re
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
        self.minimum_track_duration = float(config.get("minimum_track_duration", 30))
        self.excluded_title_terms = [
            str(term).strip()
            for term in config.get("excluded_title_terms", [])
            if str(term).strip()
        ]

    def get_candidates(
        self,
        event_state: EventState,
        exclude_ids: list[str] | None = None,
        limit: int = 50,
    ) -> list[Song]:
        """Return playable, music-length local tracks, excluding queued/recent IDs."""
        available = self._get_playable_tracks(
            limit=max(self.initial_pool_size * 5, limit),
            exclude_ids=exclude_ids,
        )
        return available[: min(limit, self.initial_pool_size)]

    def get_playable_library_tracks(self, limit: int = 50) -> list[Song]:
        """Return playable local tracks for manual diagnostics and request matching."""
        pool_size = max(self.initial_pool_size * 5, limit * 3)
        return self._get_playable_tracks(limit=pool_size)[:limit]

    def find_local_matches(self, query: str, limit: int = 5) -> list[Song]:
        """Search only playable local music for requested title/artist terms."""
        query_terms = re.sub(r"[^\w]+", " ", query.casefold()).split()
        if not query_terms:
            return []
        matching = []
        for song in self._get_playable_tracks(limit=5000):
            search_text = re.sub(
                r"[^\w]+",
                " ",
                f"{song.title} {song.artist}".casefold(),
            )
            if all(term in search_text for term in query_terms):
                matching.append(song)
                if len(matching) == limit:
                    break
        return matching

    def is_playable_local_track(self, song: Song) -> bool:
        """Check the same local playback constraints for explicitly requested tracks."""
        return self._is_playable(song)

    def _get_playable_tracks(
        self,
        limit: int,
        exclude_ids: list[str] | None = None,
    ) -> list[Song]:
        songs = self.song_repo.get_candidates(
            exclude_ids=exclude_ids or [],
            source_provider="local_file",
            min_duration=self.minimum_track_duration,
            excluded_title_terms=self.excluded_title_terms,
            limit=limit,
        )
        available = []
        seen_paths: set[str] = set()
        for song in songs:
            if not self._is_playable(song):
                continue
            normalized_path = os.path.normcase(os.path.abspath(song.file_path))
            if normalized_path in seen_paths:
                continue
            seen_paths.add(normalized_path)
            available.append(song)
        available.sort(
            key=lambda song: (
                song.popularity,
                int(song.has_audio_analysis()),
                self._metadata_completeness(song),
            ),
            reverse=True,
        )
        return available

    def _is_playable(self, song: Song) -> bool:
        return bool(
            song.source_provider == "local_file"
            and song.file_path
            and Path(song.file_path).is_file()
            and song.duration is not None
            and song.duration >= self.minimum_track_duration
            and not any(
                term.casefold()
                in f"{song.title} {Path(song.file_path).stem}".casefold()
                for term in self.excluded_title_terms
            )
        )

    @staticmethod
    def _metadata_completeness(song: Song) -> int:
        return sum(
            bool(value)
            for value in (
                song.genre or song.genres,
                song.language or song.languages,
                song.effective_bpm(),
                song.energy,
                song.danceability,
                song.valence,
            )
        )
