"""Song request and request decision models with full lifecycle tracking."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import Field

from app.models.base import (
    DJBaseModel,
    RequestDecisionType,
    RequestStatus,
    VibeVector,
    generate_id,
    utc_now,
)


class RequestStatusTransition(DJBaseModel):
    """A single transition in the request lifecycle."""

    from_status: RequestStatus
    to_status: RequestStatus
    timestamp: datetime = Field(default_factory=utc_now)
    reason: str = ""
    agent: str | None = None


class BridgeStrategy(DJBaseModel):
    """Strategy for bridging from current vibe to a requested song."""

    bridge_songs: list[str] = Field(default_factory=list)  # song_ids
    bridge_genres: list[str] = Field(default_factory=list)  # genre progression
    bridge_description: str = ""
    estimated_songs_until_request: int = 0


class SongRequest(DJBaseModel):
    """A human song request with full context and lifecycle tracking."""

    request_id: str = Field(default_factory=lambda: generate_id("REQ"))
    requested_song_query: str  # original search text
    matched_song_id: str | None = None  # resolved song_id
    requester: str = "anonymous"

    # Lifecycle
    status: RequestStatus = RequestStatus.RECEIVED
    status_history: list[RequestStatusTransition] = Field(default_factory=list)

    # Decision
    decision: RequestDecisionType | None = None
    decision_reason: str = ""
    decision_confidence: float = 0.0

    # Queue placement
    priority: float = 0.0
    target_position: int | None = None

    # Bridge strategy (for BRIDGE/DEFER decisions)
    bridge_strategy: BridgeStrategy | None = None

    # Context at request time
    current_vibe: VibeVector | None = None
    current_energy: float | None = None
    current_song_id: str | None = None
    recent_song_ids: list[str] = Field(default_factory=list)
    event_progress: float | None = None

    # Timestamps
    created_at: datetime = Field(default_factory=utc_now)
    decided_at: datetime | None = None
    played_at: datetime | None = None
    satisfied_at: datetime | None = None

    def transition_to(self, new_status: RequestStatus, reason: str = "", agent: str | None = None) -> None:
        """Record a status transition."""
        transition = RequestStatusTransition(
            from_status=self.status,
            to_status=new_status,
            reason=reason,
            agent=agent,
        )
        self.status_history.append(transition)
        self.status = new_status


class RequestDecision(DJBaseModel):
    """Detailed decision record for a song request."""

    decision_id: str = Field(default_factory=lambda: generate_id("RD"))
    request_id: str
    decision: RequestDecisionType
    reason: str
    confidence: float = 0.0

    # Scoring context
    vibe_compatibility: float = 0.0
    energy_compatibility: float = 0.0
    genre_compatibility: float = 0.0
    policy_compatible: bool = True
    policy_violations: list[str] = Field(default_factory=list)

    # Bridge recommendation
    bridge_strategy: BridgeStrategy | None = None
    recommended_position: int | None = None

    # Decision epoch
    decision_epoch: int = 0
    event_id: str | None = None
    timestamp: datetime = Field(default_factory=utc_now)
