"""Event configuration and runtime state models."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import Field

from app.models.base import (
    DJBaseModel,
    EnergyCurvePoint,
    EventType,
    PlaybackState,
    SystemMode,
    VibePreset,
    VibeVector,
    generate_id,
    utc_now,
)


class EventConfig(DJBaseModel):
    """User-provided event configuration — immutable after event creation."""

    event_id: str = Field(default_factory=lambda: generate_id("EVT"))
    name: str = "Untitled Event"
    event_type: EventType = EventType.CUSTOM
    description: str = ""

    # Audience
    min_age: int = 0
    max_age: int = 100
    expected_count: int | None = None

    # Timing
    duration_minutes: int = 240
    start_time: datetime | None = None

    # Music
    languages: list[str] = Field(default_factory=lambda: ["Hindi", "English"])
    region: str | None = None
    starting_vibe: VibePreset = VibePreset.CHILL
    target_vibe: VibePreset | None = None
    explicit_allowed: bool = False
    prefer_genres: list[str] = Field(default_factory=list)
    avoid_genres: list[str] = Field(default_factory=list)
    prefer_artists: list[str] = Field(default_factory=list)
    avoid_artists: list[str] = Field(default_factory=list)

    # Energy curve
    energy_curve: list[EnergyCurvePoint] = Field(default_factory=list)

    # Requests
    allow_requests: bool = True
    request_mode: str = "adaptive"  # adaptive | strict | permissive
    requests_affect_vibe: bool = True

    # Learning
    learning_enabled: bool = True
    feedback_prompt: bool = True

    # Audio
    lookahead_songs: int = 5
    analyze_on_add: bool = True

    # Simulation
    simulation_speed: float = 1.0
    dry_run: bool = False

    # Custom
    custom_instructions: str = ""

    created_at: datetime = Field(default_factory=utc_now)


class EventState(DJBaseModel):
    """
    Live event state — the DJ Orchestrator's single source of truth.

    This is the temporary event memory that changes continuously during an event.
    It is persisted locally for crash recovery and audit.
    """

    event_id: str
    event_config: EventConfig

    # Current musical state
    current_vibe: VibePreset = VibePreset.CHILL
    vibe_vector: VibeVector = Field(default_factory=VibeVector)
    target_energy: float = Field(default=0.5, ge=0.0, le=1.0)
    current_energy: float = Field(default=0.5, ge=0.0, le=1.0)

    # Playback
    playback_state: PlaybackState = PlaybackState.STOPPED
    current_song_id: str | None = None
    current_song_started_at: datetime | None = None

    # Queue (song_ids)
    queue: list[str] = Field(default_factory=list)

    # History
    recent_history: list[str] = Field(default_factory=list)  # last N song_ids
    recent_artists: list[str] = Field(default_factory=list)
    recent_genres: list[str] = Field(default_factory=list)
    songs_played_count: int = 0

    # Requests
    pending_requests: list[str] = Field(default_factory=list)  # request_ids
    accepted_requests: list[str] = Field(default_factory=list)
    deferred_requests: list[str] = Field(default_factory=list)
    rejected_requests: list[str] = Field(default_factory=list)

    # Feedback
    crowd_feedback_history: list[dict[str, Any]] = Field(default_factory=list)
    average_feedback: float | None = None

    # Event progress
    event_started_at: datetime | None = None
    event_paused_at: datetime | None = None
    event_ended_at: datetime | None = None
    elapsed_minutes: float = 0.0
    event_progress: float = Field(default=0.0, ge=0.0, le=1.0)
    is_paused: bool = False
    is_ended: bool = False

    # System
    system_mode: SystemMode = SystemMode.NORMAL
    decision_epoch: int = 0  # increments on each decision
    last_decision_at: datetime | None = None
    last_state_update: datetime = Field(default_factory=utc_now)

    # Agent statuses
    agent_statuses: dict[str, str] = Field(default_factory=dict)

    def advance_epoch(self) -> int:
        """Increment and return the new decision epoch."""
        self.decision_epoch += 1
        self.last_decision_at = utc_now()
        self.last_state_update = utc_now()
        return self.decision_epoch

    def update_progress(self) -> None:
        """Recalculate event progress based on elapsed time."""
        if self.event_config.duration_minutes > 0:
            self.event_progress = min(
                1.0,
                self.elapsed_minutes / self.event_config.duration_minutes,
            )

    def get_target_energy_from_curve(self) -> float | None:
        """Interpolate target energy from the event's energy curve."""
        curve = self.event_config.energy_curve
        if not curve:
            return None
        elapsed = self.elapsed_minutes
        # Before first point
        if elapsed <= curve[0].time_minutes:
            return curve[0].energy
        # After last point
        if elapsed >= curve[-1].time_minutes:
            return curve[-1].energy
        # Interpolate
        for i in range(len(curve) - 1):
            t0 = curve[i].time_minutes
            t1 = curve[i + 1].time_minutes
            if t0 <= elapsed <= t1:
                frac = (elapsed - t0) / (t1 - t0) if t1 > t0 else 0.0
                e0 = curve[i].energy
                e1 = curve[i + 1].energy
                return e0 + frac * (e1 - e0)
        return curve[-1].energy
