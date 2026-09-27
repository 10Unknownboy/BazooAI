from __future__ import annotations

import logging
from typing import Any

from app.config.settings import load_scoring_config
from app.models.event import EventState
from app.models.song import Song

logger = logging.getLogger(__name__)


class ScoringResult:
    """Result of the scoring engine for a candidate song."""

    def __init__(
        self,
        final_score: float,
        score_components: dict[str, float],
        penalty_components: dict[str, float],
        detailed_breakdown: dict[str, Any],
    ):
        self.final_score = final_score
        self.score_components = score_components
        self.penalty_components = penalty_components
        self.detailed_breakdown = detailed_breakdown


class ScoringEngine:
    """Deterministic candidate scoring engine."""

    def __init__(self):
        self.config = load_scoring_config()
        self.weights = self.config.get("positive_weights", {})
        self.penalty_weights = self.config.get("penalty_weights", {})

    def calculate_vibe_match(self, song: Song, event_state: EventState) -> float:
        """Calculate vibe match (0-100)."""
        target = event_state.vibe_vector.model_dump()
        song_values = {
            "energy": song.effective_energy(),
            "danceability": song.effective_danceability(),
            "valence": song.effective_valence(),
            "chill": 1.0 - song.effective_energy(),
        }
        lyrics = song.lyrics_features
        if lyrics:
            song_values.update(
                romance=lyrics.romance,
                nostalgia=lyrics.nostalgia,
                aggression=lyrics.aggression,
            )
        dimensions = song_values.keys()
        mean_squared_error = sum(
            (song_values[name] - target[name]) ** 2 for name in dimensions
        ) / len(song_values)
        return max(0.0, 100.0 * (1.0 - mean_squared_error**0.5))

    def calculate_energy_match(self, song: Song, event_state: EventState) -> float:
        """Calculate energy match (0-100)."""
        difference = abs(song.effective_energy() - event_state.target_energy)
        return max(0.0, 100.0 * (1.0 - difference))

    def calculate_genre_match(self, song: Song, event_state: EventState) -> float:
        """Calculate genre match (0-100)."""
        preferred = {
            genre.casefold()
            for genre in (
                event_state.event_config.prefer_genres + event_state.agent_preferred_genres
            )
        }
        avoided = {
            genre.casefold()
            for genre in (event_state.event_config.avoid_genres + event_state.agent_avoided_genres)
        }
        song_genres = {genre.casefold() for genre in (song.genres or [])}
        if song.genre:
            song_genres.add(song.genre.casefold())
        if song_genres & avoided:
            return 0.0
        if not preferred:
            return 70.0
        return 100.0 if song_genres & preferred else 35.0

    def calculate_language_match(self, song: Song, event_state: EventState) -> float:
        """Calculate language match (0-100)."""
        allowed = {
            language.casefold()
            for language in (
                event_state.event_config.languages + event_state.agent_preferred_languages
            )
        }
        song_languages = {language.casefold() for language in (song.languages or [])}
        if song.language:
            song_languages.add(song.language.casefold())
        if not song_languages:
            return 50.0
        agent_preferred = {
            language.casefold() for language in event_state.agent_preferred_languages
        }
        if song_languages & agent_preferred:
            return 100.0
        if not allowed:
            return 70.0
        return 70.0 if song_languages & allowed else 0.0

    def calculate_artist_match(self, song: Song, event_state: EventState) -> float:
        preferred = {
            artist.casefold()
            for artist in (
                event_state.event_config.prefer_artists + event_state.agent_preferred_artists
            )
        }
        avoided = {
            artist.casefold()
            for artist in (
                event_state.event_config.avoid_artists + event_state.agent_avoided_artists
            )
        }
        song_artists = {artist.casefold() for artist in song.artists}
        song_artists.add(song.artist.casefold())
        if song_artists & avoided:
            return 0.0
        if not preferred:
            return 70.0
        return 100.0 if song_artists & preferred else 35.0

    def calculate_popularity(self, song: Song) -> float:
        """Calculate popularity score (0-100)."""
        return max(0.0, min(100.0, song.popularity * 100.0))

    def score_candidate(
        self,
        song: Song,
        event_state: EventState,
        transition_score: float = 0.0,
        penalty_engine_result: dict[str, float] | None = None,
        request_score: float = 0.0,
        learned_preference: float = 0.0,
    ) -> ScoringResult:
        """Calculate overall score for a candidate song."""
        components = {
            "vibe_match": self.calculate_vibe_match(song, event_state),
            "energy_match": self.calculate_energy_match(song, event_state),
            "genre_match": self.calculate_genre_match(song, event_state),
            "artist_match": self.calculate_artist_match(song, event_state),
            "language_match": self.calculate_language_match(song, event_state),
            "transition_score": max(0.0, min(100.0, transition_score)),
            "popularity": self.calculate_popularity(song),
            "event_type_match": self._event_type_match(song, event_state),
            "request_score": max(0.0, min(100.0, request_score)),
            "crowd_feedback": self._crowd_feedback(song, event_state),
            "learned_preference": max(0.0, min(100.0, 50.0 + learned_preference)),
        }
        weighted_components = {
            name: value * self.weights.get(name, 0.0) for name, value in components.items()
        }
        penalties = {
            name: max(0.0, value) * self.penalty_weights.get(name, 1.0)
            for name, value in (penalty_engine_result or {}).items()
        }
        positive_score = sum(weighted_components.values())
        total_penalty = sum(penalties.values())
        max_score = self.config.get("normalization", {}).get("max_score", 100.0)
        final_score = max(0.0, min(max_score, positive_score - total_penalty))

        return ScoringResult(
            final_score=final_score,
            score_components=weighted_components,
            penalty_components=penalties,
            detailed_breakdown={
                "positive_score": positive_score,
                "total_penalty": total_penalty,
                "unweighted_components": components,
            },
        )

    def _event_type_match(self, song: Song, event_state: EventState) -> float:
        preferred = {
            genre.casefold()
            for genre in (
                event_state.event_config.prefer_genres + event_state.agent_preferred_genres
            )
        }
        song_genres = {genre.casefold() for genre in (song.genres or [])}
        if song.genre:
            song_genres.add(song.genre.casefold())
        return 100.0 if preferred & song_genres else 50.0

    @staticmethod
    def _crowd_feedback(song: Song, event_state: EventState) -> float:
        ratings = [
            entry.get("reward", 0.0)
            for entry in event_state.crowd_feedback_history
            if entry.get("song_id") == song.song_id
        ]
        if not ratings:
            return 50.0
        return max(0.0, min(100.0, 50.0 + sum(ratings) / len(ratings) * 50.0))
