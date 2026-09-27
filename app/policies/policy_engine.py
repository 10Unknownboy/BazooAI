from __future__ import annotations

from app.config.settings import load_policy_config
from app.models.event import EventState
from app.models.song import Song


class PolicyResult:
    """Result of deterministic hard policy checks."""

    def __init__(self, passed: bool, violations: list[str]):
        self.passed = passed
        self.violations = violations


class PolicyEngine:
    """Enforce event and configured hard song-selection policies."""

    def __init__(self):
        self.policies = load_policy_config()

    def check_song(self, song: Song, event_state: EventState) -> PolicyResult:
        violations = []
        content = self.policies.get("content", {})
        languages = self.policies.get("languages", {})
        genres = self.policies.get("genres", {})
        artists = self.policies.get("artists", {})
        repetition = self.policies.get("repetition", {})

        explicit_allowed = event_state.event_config.explicit_allowed and content.get(
            "explicit_allowed", True
        )
        if song.explicit and not explicit_allowed:
            violations.append("Explicit content is not allowed for this event.")

        blocked_artists = {name.casefold() for name in artists.get("blocked", [])}
        song_artists = {name.casefold() for name in (song.artists or [])}
        song_artists.add(song.artist.casefold())
        if blocked_artists & song_artists:
            violations.append("Artist is blocked by policy.")

        song_genres = {genre.casefold() for genre in (song.genres or [])}
        if song.genre:
            song_genres.add(song.genre.casefold())
        blocked_genres = {genre.casefold() for genre in genres.get("blocked", [])}
        if blocked_genres & song_genres:
            violations.append("Genre is blocked by policy.")
        allowed_genres = {genre.casefold() for genre in genres.get("allowed", [])}
        if allowed_genres and not song_genres & allowed_genres:
            violations.append("Song is outside the policy's allowed genres.")
        avoided_genres = {
            genre.casefold() for genre in event_state.event_config.avoid_genres
        }
        if avoided_genres & song_genres:
            violations.append("Genre is excluded by the event configuration.")

        allowed_languages = {
            language.casefold()
            for language in (
                event_state.event_config.languages or languages.get("allowed", [])
            )
        }
        song_languages = {language.casefold() for language in (song.languages or [])}
        if song.language:
            song_languages.add(song.language.casefold())
        if allowed_languages and song_languages and not song_languages & allowed_languages:
            violations.append("Song language is not allowed for this event.")

        song_window = max(0, int(repetition.get("max_same_song_window", 0)))
        if song_window and song.song_id in event_state.recent_history[-song_window:]:
            violations.append("Song was played within the repetition policy window.")

        artist_window = max(0, int(repetition.get("max_same_artist_window", 0)))
        recent_artists = {
            artist.casefold() for artist in event_state.recent_artists[-artist_window:]
        }
        if artist_window and song_artists & recent_artists:
            violations.append("Artist was played within the repetition policy window.")

        return PolicyResult(passed=not violations, violations=violations)
