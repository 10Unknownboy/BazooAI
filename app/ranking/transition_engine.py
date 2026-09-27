from __future__ import annotations

import logging

from app.models.song import Song

logger = logging.getLogger(__name__)


class TransitionResult:
    """Result of transition compatibility checks."""

    def __init__(self, score: float, breakdown: dict[str, float], warnings: list[str]):
        self.score = score
        self.breakdown = breakdown
        self.warnings = warnings


class TransitionEngine:
    """Deterministic transition compatibility scorer."""

    def calculate_bpm_compatibility(self, song_a: Song, song_b: Song) -> float:
        """Score beat-match-friendly tempos, accounting for half/double tempo."""
        bpm_a = song_a.effective_bpm()
        bpm_b = song_b.effective_bpm()
        if not bpm_a or not bpm_b:
            return 0.5
        difference = min(
            abs(bpm_a - bpm_b),
            abs(bpm_a - 2 * bpm_b),
            abs(2 * bpm_a - bpm_b),
        )
        return max(0.0, 1.0 - difference / 40.0)

    def calculate_key_compatibility(self, song_a: Song, song_b: Song) -> float:
        """Return a neutral value when keys are missing, otherwise score nearby keys."""
        if not song_a.key or not song_b.key:
            return 0.5
        a, b = self._key_number(song_a.key), self._key_number(song_b.key)
        if a is None or b is None:
            return 0.5
        distance = min((a - b) % 12, (b - a) % 12)
        return {0: 1.0, 5: 0.8, 7: 0.8, 1: 0.65, 11: 0.65}.get(
            distance, max(0.0, 1.0 - distance / 6.0)
        )

    def score_transition(self, current_song: Song, next_song: Song) -> TransitionResult:
        """Score the transition quality from available local song features."""
        bpm = self.calculate_bpm_compatibility(current_song, next_song)
        key = self.calculate_key_compatibility(current_song, next_song)
        energy = max(
            0.0,
            1.0 - abs(current_song.effective_energy() - next_song.effective_energy()),
        )
        danceability = max(
            0.0,
            1.0
            - abs(
                current_song.effective_danceability()
                - next_song.effective_danceability()
            ),
        )
        breakdown = {
            "bpm": bpm,
            "key": key,
            "energy": energy,
            "danceability": danceability,
        }
        score = sum(breakdown.values()) / len(breakdown)
        warnings = []
        if bpm < 0.5:
            warnings.append("Large BPM jump detected")
        if energy < 0.65:
            warnings.append("Large energy jump detected")
        return TransitionResult(score=score, breakdown=breakdown, warnings=warnings)

    @staticmethod
    def _key_number(key: str) -> int | None:
        normalized = key.strip().casefold()
        names = {
            "c": 0,
            "b#": 0,
            "c#": 1,
            "db": 1,
            "d": 2,
            "d#": 3,
            "eb": 3,
            "e": 4,
            "fb": 4,
            "f": 5,
            "e#": 5,
            "f#": 6,
            "gb": 6,
            "g": 7,
            "g#": 8,
            "ab": 8,
            "a": 9,
            "a#": 10,
            "bb": 10,
            "b": 11,
            "cb": 11,
        }
        root = normalized.split()[0].replace("minor", "").replace("major", "")
        root = root.removesuffix("m")
        return names.get(root)
