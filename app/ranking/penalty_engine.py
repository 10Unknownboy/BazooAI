from __future__ import annotations

import logging

from app.config.settings import load_scoring_config
from app.models.event import EventState
from app.models.song import Song

logger = logging.getLogger(__name__)


class PenaltyResult:
    """Result of a single penalty calculation."""

    def __init__(self, name: str, value: float, reason: str, threshold: float):
        self.name = name
        self.value = value
        self.reason = reason
        self.threshold = threshold


class PenaltyEngine:
    """Transparent penalty calculator."""

    def __init__(self):
        self.config = load_scoring_config()
        self.thresholds = self.config.get("penalty_thresholds", {})

    def check_recency(self, song: Song, event_state: EventState) -> PenaltyResult:
        """Penalize songs that were played within the configured history window."""
        window = max(1, int(self.thresholds.get("recency_window", 20)))
        history = event_state.recent_history[-window:]
        if song.song_id not in history:
            return PenaltyResult("recency_penalty", 0.0, "Not recently played", window)
        distance = len(history) - history[::-1].index(song.song_id)
        penalty = 20.0 * (1.0 - distance / window)
        return PenaltyResult("recency_penalty", penalty, "Song was played recently", window)

    def check_artist_repetition(self, song: Song, event_state: EventState) -> PenaltyResult:
        """Penalize artists that were played within the configured artist window."""
        window = max(1, int(self.thresholds.get("artist_window", 4)))
        recent = [artist.casefold() for artist in event_state.recent_artists[-window:]]
        artists = {artist.casefold() for artist in (song.artists or [])}
        artists.add(song.artist.casefold())
        repeats = sum(artist in artists for artist in recent)
        penalty = min(15.0, repeats * 5.0)
        reason = "Artist recently played" if penalty else "Artist not repeated"
        return PenaltyResult("artist_repetition_penalty", penalty, reason, window)

    def calculate_penalties(self, song: Song, event_state: EventState) -> dict[str, float]:
        """Calculate explainable soft penalties for a candidate."""
        penalties = [
            self.check_recency(song, event_state),
            self.check_artist_repetition(song, event_state),
        ]

        genre_window = max(1, int(self.thresholds.get("genre_window", 5)))
        genres = {genre.casefold() for genre in (song.genres or [])}
        if song.genre:
            genres.add(song.genre.casefold())
        recent_genres = [genre.casefold() for genre in event_state.recent_genres[-genre_window:]]
        repeated_genres = sum(genre in genres for genre in recent_genres)
        if repeated_genres:
            penalties.append(
                PenaltyResult(
                    "genre_repetition_penalty",
                    min(12.0, repeated_genres * 3.0),
                    "Genre has appeared frequently",
                    genre_window,
                )
            )

        energy_jump = abs(song.effective_energy() - event_state.target_energy)
        max_energy_jump = float(self.thresholds.get("max_energy_jump", 0.25))
        if energy_jump > max_energy_jump:
            penalties.append(
                PenaltyResult(
                    "energy_jump_penalty",
                    min(20.0, (energy_jump - max_energy_jump) * 40.0),
                    "Energy differs sharply from target",
                    max_energy_jump,
                )
            )

        previous_song_id = event_state.current_song_id or (
            event_state.recent_history[-1] if event_state.recent_history else None
        )
        if previous_song_id:
            try:
                from app.database.repositories import get_repository

                previous = get_repository("song").get(previous_song_id)
            except Exception:
                logger.exception("Failed to load previous song for BPM penalty")
                previous = None
            bpm = song.effective_bpm()
            previous_bpm = previous.effective_bpm() if previous else None
            max_bpm_jump = float(self.thresholds.get("max_bpm_jump", 35))
            if bpm and previous_bpm and abs(bpm - previous_bpm) > max_bpm_jump:
                penalties.append(
                    PenaltyResult(
                        "bpm_jump_penalty",
                        min(15.0, (abs(bpm - previous_bpm) - max_bpm_jump) * 0.25),
                        "BPM differs sharply from previous song",
                        max_bpm_jump,
                    )
                )

        return {penalty.name: penalty.value for penalty in penalties if penalty.value > 0}
