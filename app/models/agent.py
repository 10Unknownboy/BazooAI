"""Agent decision, logging, and AI communication models."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import Field

from app.models.base import (
    AgentRole,
    AIMessageType,
    DJBaseModel,
    VibeVector,
    generate_id,
    utc_now,
)


class AgentDecision(DJBaseModel):
    """Record of a single agent's decision for audit and debugging."""

    decision_id: str = Field(default_factory=lambda: generate_id("AD"))
    agent: AgentRole
    decision_type: str  # e.g. "song_selection", "request_evaluation", "vibe_update"

    # Decision content
    decision: str  # e.g. "QUEUE", "REJECT", "ACCEPT_NOW"
    reason: str = ""
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)

    # Context
    event_id: str | None = None
    current_song_id: str | None = None
    candidate_song_id: str | None = None
    request_id: str | None = None
    decision_epoch: int = 0

    # Input/output data
    input_data: dict[str, Any] = Field(default_factory=dict)
    output_data: dict[str, Any] = Field(default_factory=dict)

    # Performance
    latency_ms: float | None = None
    used_ai: bool = False
    ai_fallback: bool = False  # True if AI was unavailable and deterministic fallback used

    timestamp: datetime = Field(default_factory=utc_now)


class AgentLog(DJBaseModel):
    """Structured log entry from an agent."""

    log_id: str = Field(default_factory=lambda: generate_id("LOG"))
    agent: AgentRole
    level: str = "INFO"  # DEBUG, INFO, WARNING, ERROR
    message: str
    data: dict[str, Any] = Field(default_factory=dict)
    event_id: str | None = None
    decision_epoch: int | None = None
    timestamp: datetime = Field(default_factory=utc_now)


# ---------------------------------------------------------------------------
# AI Communication schemas — structured messages to/from the remote LLM
# ---------------------------------------------------------------------------

class AIRequest(DJBaseModel):
    """Structured request sent to the remote AI model server."""

    request_id: str = Field(default_factory=lambda: generate_id("AIR"))
    message_type: AIMessageType

    # Event context (minimal subset needed for this decision)
    event_type: str | None = None
    event_progress: float | None = None
    current_vibe: VibeVector | None = None
    target_energy: float | None = None
    current_energy: float | None = None
    current_song_id: str | None = None
    recent_song_ids: list[str] = Field(default_factory=list)
    recent_genres: list[str] = Field(default_factory=list)
    recent_artists: list[str] = Field(default_factory=list)

    # Request-specific data
    candidate_songs: list[dict[str, Any]] = Field(default_factory=list)
    request_data: dict[str, Any] = Field(default_factory=dict)
    queue_data: list[dict[str, Any]] = Field(default_factory=list)
    lyrics_data: dict[str, Any] = Field(default_factory=dict)

    # Custom instructions from event config
    custom_instructions: str = ""
    audience_age_range: list[int] = Field(default_factory=list)
    allowed_languages: list[str] = Field(default_factory=list)

    timestamp: datetime = Field(default_factory=utc_now)


class AIResponse(DJBaseModel):
    """Structured response from the remote AI model server."""

    request_id: str
    message_type: AIMessageType
    success: bool = True
    error: str | None = None

    # Decision output
    decision: str | None = None
    reason: str = ""
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)

    # Vibe/energy recommendations (NOT direct scores)
    recommended_vibe: VibeVector | None = None
    recommended_energy: float | None = None
    preferred_genres: list[str] = Field(default_factory=list)
    preferred_languages: list[str] = Field(default_factory=list)
    preferred_artists: list[str] = Field(default_factory=list)
    avoid_genres: list[str] = Field(default_factory=list)
    avoid_artists: list[str] = Field(default_factory=list)

    # Song recommendations (song_ids from candidates, NOT invented)
    recommended_song_ids: list[str] = Field(default_factory=list)
    rejected_song_ids: list[str] = Field(default_factory=list)

    # Request-specific
    request_decision: str | None = None  # ACCEPT_NOW / QUEUE / DEFER / BRIDGE / REJECT
    bridge_strategy: list[str] | None = None  # genre/style progression
    recommended_position: int | None = None

    # Lyrics analysis results
    lyrics_analysis: dict[str, Any] = Field(default_factory=dict)

    # Queue review
    queue_approved: bool = True
    queue_changes: list[dict[str, Any]] = Field(default_factory=list)

    # Event summary
    event_summary: dict[str, Any] = Field(default_factory=dict)

    # Metadata
    model_name: str | None = None
    latency_ms: float | None = None
    timestamp: datetime = Field(default_factory=utc_now)


class ScoringSnapshot(DJBaseModel):
    """
    Immutable snapshot of every factor that went into a song-selection decision.
    Saved with every queue insertion for full auditability.
    """

    snapshot_id: str = Field(default_factory=lambda: generate_id("SS"))
    event_id: str
    decision_epoch: int
    song_id: str

    # Score breakdown
    final_score: float = 0.0
    score_components: dict[str, float] = Field(default_factory=dict)
    penalty_components: dict[str, float] = Field(default_factory=dict)
    scoring_weights: dict[str, float] = Field(default_factory=dict)
    penalty_weights: dict[str, float] = Field(default_factory=dict)

    # Policy state
    policy_passed: bool = True
    policy_violations: list[str] = Field(default_factory=list)

    # Event state at decision time
    event_state_snapshot: dict[str, Any] = Field(default_factory=dict)

    # Agent recommendations
    agent_recommendations: dict[str, Any] = Field(default_factory=dict)

    # Candidate features
    candidate_features: dict[str, Any] = Field(default_factory=dict)

    timestamp: datetime = Field(default_factory=utc_now)
