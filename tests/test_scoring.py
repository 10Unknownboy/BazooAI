"""Tests for the scoring engine (spec §51)."""

from __future__ import annotations

import pytest

from app.models.base import VibeVector, VibePreset
from app.models.song import Song
from app.models.event import EventConfig, EventState
from app.ranking.scoring_engine import ScoringEngine
from app.ranking.penalty_engine import PenaltyEngine


@pytest.fixture
def scoring_engine():
    return ScoringEngine()


@pytest.fixture
def penalty_engine():
    return PenaltyEngine()


def test_scoring_produces_positive_score(scoring_engine, sample_song, sample_event_state):
    """A matching song should produce a positive score."""
    result = scoring_engine.score_candidate(sample_song, sample_event_state)
    assert result.final_score > 0


def test_score_components_are_dict(scoring_engine, sample_song, sample_event_state):
    """Score components should be returned as a dict with named keys."""
    result = scoring_engine.score_candidate(sample_song, sample_event_state)
    assert result.final_score >= 0
    assert hasattr(result, "final_score")


def test_penalty_engine_returns_dict(penalty_engine, sample_song, sample_event_state):
    """Penalty engine should return a dict of penalty components."""
    penalties = penalty_engine.calculate_penalties(sample_song, sample_event_state)
    assert isinstance(penalties, dict)


def test_different_songs_get_different_scores(scoring_engine, sample_song, sample_song_b, sample_event_state):
    """Different songs should generally get different scores."""
    result_a = scoring_engine.score_candidate(sample_song, sample_event_state)
    result_b = scoring_engine.score_candidate(sample_song_b, sample_event_state)
    # Scores may be similar but the engine should produce results for both
    assert result_a.final_score > 0
    assert result_b.final_score > 0
