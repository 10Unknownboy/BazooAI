from __future__ import annotations

import logging
from typing import Any, Dict

from app.models.song import Song
from app.models.event import EventState
from app.config.settings import load_scoring_config

logger = logging.getLogger(__name__)


class ScoringResult:
    """Result of the scoring engine for a candidate song."""
    def __init__(
        self,
        final_score: float,
        score_components: Dict[str, float],
        penalty_components: Dict[str, float],
        detailed_breakdown: Dict[str, Any]
    ):
        self.final_score = final_score
        self.score_components = score_components
        self.penalty_components = penalty_components
        self.detailed_breakdown = detailed_breakdown


class ScoringEngine:
    """Deterministic candidate scoring engine."""
    
    def __init__(self):
        self.config = load_scoring_config()
        self.weights = self.config.get("weights", {})
        
    def calculate_vibe_match(self, song: Song, event_state: EventState) -> float:
        """Calculate vibe match (0-100)."""
        # Placeholder for actual vibe match logic
        return 80.0
        
    def calculate_energy_match(self, song: Song, event_state: EventState) -> float:
        """Calculate energy match (0-100)."""
        return 80.0
        
    def calculate_genre_match(self, song: Song, event_state: EventState) -> float:
        """Calculate genre match (0-100)."""
        return 80.0
        
    def calculate_language_match(self, song: Song, event_state: EventState) -> float:
        """Calculate language match (0-100)."""
        return 100.0
        
    def calculate_popularity(self, song: Song) -> float:
        """Calculate popularity score (0-100)."""
        return getattr(song, "popularity", 50.0)
        
    def score_candidate(self, song: Song, event_state: EventState, transition_score: float = 0.0, penalty_engine_result: Dict = None) -> ScoringResult:
        """Calculate overall score for a candidate song."""
        try:
            score_components = {
                "vibe_match": self.calculate_vibe_match(song, event_state) * self.weights.get("vibe", 1.0),
                "energy_match": self.calculate_energy_match(song, event_state) * self.weights.get("energy", 1.0),
                "genre_match": self.calculate_genre_match(song, event_state) * self.weights.get("genre", 1.0),
                "language_match": self.calculate_language_match(song, event_state) * self.weights.get("language", 1.0),
                "popularity": self.calculate_popularity(song) * self.weights.get("popularity", 1.0),
                "transition_score": transition_score * self.weights.get("transition", 1.0),
            }
            
            base_score = sum(score_components.values())
            
            penalty_components = penalty_engine_result or {}
            total_penalty = sum(penalty_components.values())
            
            final_score = max(0.0, base_score - total_penalty)
            
            return ScoringResult(
                final_score=final_score,
                score_components=score_components,
                penalty_components=penalty_components,
                detailed_breakdown={"base": base_score, "penalty": total_penalty}
            )
        except Exception as e:
            logger.error(f"Error scoring candidate {song}: {e}")
            return ScoringResult(0.0, {}, {}, {})
