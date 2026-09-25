"""Feedback, reward, and learning models with full context capture."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import Field

from app.models.base import (
    DJBaseModel,
    PenaltyComponents,
    ScoreComponents,
    VibeVector,
    generate_id,
    utc_now,
)


class SongFeedback(DJBaseModel):
    """Multi-dimensional song-level feedback with full decision context."""

    feedback_id: str = Field(default_factory=lambda: generate_id("FB"))
    event_id: str
    song_id: str

    # Multi-dimensional ratings (1-10)
    overall_rating: int = Field(ge=1, le=10)
    energy_rating: int | None = Field(default=None, ge=1, le=10)
    song_choice_rating: int | None = Field(default=None, ge=1, le=10)
    transition_rating: int | None = Field(default=None, ge=1, le=10)
    vibe_rating: int | None = Field(default=None, ge=1, le=10)

    # Context at feedback time
    current_vibe: VibeVector | None = None
    target_energy: float | None = None
    current_energy: float | None = None
    current_song_id: str | None = None
    previous_song_ids: list[str] = Field(default_factory=list)
    next_song_ids: list[str] = Field(default_factory=list)
    current_genre: str | None = None
    previous_genre: str | None = None
    event_type: str | None = None
    audience_age_range: list[int] = Field(default_factory=list)
    event_progress: float | None = None

    # Decision context
    decision_score: float | None = None
    score_components: ScoreComponents | None = None
    penalty_components: PenaltyComponents | None = None
    decision_epoch: int = 0

    # Request linkage
    was_requested: bool = False
    request_id: str | None = None

    timestamp: datetime = Field(default_factory=utc_now)


class TransitionFeedback(DJBaseModel):
    """Feedback specifically about the transition between two songs."""

    feedback_id: str = Field(default_factory=lambda: generate_id("TFB"))
    event_id: str
    from_song_id: str
    to_song_id: str

    # Transition quality (1-10)
    transition_rating: int = Field(ge=1, le=10)

    # Context
    from_genre: str | None = None
    to_genre: str | None = None
    from_energy: float | None = None
    to_energy: float | None = None
    from_bpm: float | None = None
    to_bpm: float | None = None
    vibe_at_transition: VibeVector | None = None
    event_progress: float | None = None
    decision_epoch: int = 0

    timestamp: datetime = Field(default_factory=utc_now)


class EventFeedback(DJBaseModel):
    """Overall event-level feedback collected at event end."""

    feedback_id: str = Field(default_factory=lambda: generate_id("EFB"))
    event_id: str
    event_type: str | None = None

    # Overall ratings (1-10)
    overall_performance: int = Field(ge=1, le=10)
    song_selection: int | None = Field(default=None, ge=1, le=10)
    vibe_maintenance: int | None = Field(default=None, ge=1, le=10)
    transitions: int | None = Field(default=None, ge=1, le=10)
    request_handling: int | None = Field(default=None, ge=1, le=10)
    variety: int | None = Field(default=None, ge=1, le=10)

    # Event statistics
    songs_played: int = 0
    total_requests: int = 0
    accepted_requests: int = 0
    deferred_requests: int = 0
    rejected_requests: int = 0
    average_song_feedback: float | None = None

    comments: str = ""
    timestamp: datetime = Field(default_factory=utc_now)


class RewardRecord(DJBaseModel):
    """
    Normalized reward record for learning: STATE → ACTION → REWARD → NEXT_STATE → CONTEXT.
    Ready for future contextual bandits / LTR / RL integration.
    """

    reward_id: str = Field(default_factory=lambda: generate_id("RW"))
    event_id: str
    decision_epoch: int

    # STATE: context at decision time
    state_vibe: VibeVector | None = None
    state_energy: float | None = None
    state_event_type: str | None = None
    state_event_progress: float | None = None
    state_recent_genres: list[str] = Field(default_factory=list)
    state_recent_artists: list[str] = Field(default_factory=list)
    state_audience_age: list[int] = Field(default_factory=list)

    # ACTION: what was selected
    action_song_id: str
    action_score: float = 0.0
    action_score_components: ScoreComponents | None = None
    action_penalty_components: PenaltyComponents | None = None

    # REWARD: normalized -1.0 to +1.0
    reward: float = Field(ge=-1.0, le=1.0)
    raw_feedback: dict[str, Any] = Field(default_factory=dict)

    # NEXT STATE: state after song played
    next_state_vibe: VibeVector | None = None
    next_state_energy: float | None = None
    next_state_event_progress: float | None = None

    # CONTEXT: additional metadata for learning
    context: dict[str, Any] = Field(default_factory=dict)

    timestamp: datetime = Field(default_factory=utc_now)


class PatternRecord(DJBaseModel):
    """A learned pattern (e.g. genre transition) with average feedback."""

    pattern: str
    average_feedback: float = 0.0
    sample_count: int = 0


class EventLearningReport(DJBaseModel):
    """Machine-readable event-end learning summary (spec §36)."""

    event_id: str
    event_type: str | None = None

    songs_played: int = 0
    total_requests: int = 0
    request_success_rate: float = 0.0

    successful_patterns: list[PatternRecord] = Field(default_factory=list)
    weak_patterns: list[PatternRecord] = Field(default_factory=list)

    successful_songs: list[str] = Field(default_factory=list)
    poorly_performing_songs: list[str] = Field(default_factory=list)

    successful_transition_types: list[PatternRecord] = Field(default_factory=list)
    poor_transition_types: list[PatternRecord] = Field(default_factory=list)

    crowd_preferences: dict[str, Any] = Field(default_factory=dict)

    timestamp: datetime = Field(default_factory=utc_now)
