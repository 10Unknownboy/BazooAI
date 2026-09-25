"""Base enums, types, and shared model utilities used across all models."""

from __future__ import annotations

import enum
import uuid
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# ID helpers
# ---------------------------------------------------------------------------
def generate_id(prefix: str = "") -> str:
    """Generate a unique ID with optional prefix."""
    short = uuid.uuid4().hex[:12]
    return f"{prefix}_{short}" if prefix else short


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------
class LockStatus(str, enum.Enum):
    LOCKED = "LOCKED"
    RECONSIDERING = "RECONSIDERING"
    FLEXIBLE = "FLEXIBLE"


class RequestStatus(str, enum.Enum):
    RECEIVED = "RECEIVED"
    VALIDATING = "VALIDATING"
    POLICY_CHECK = "POLICY_CHECK"
    ANALYZING = "ANALYZING"
    DECISION = "DECISION"
    QUEUED = "QUEUED"
    DEFERRED = "DEFERRED"
    BRIDGING = "BRIDGING"
    REJECTED = "REJECTED"
    PLAYED = "PLAYED"
    SATISFIED = "SATISFIED"


class RequestDecisionType(str, enum.Enum):
    ACCEPT_NOW = "ACCEPT_NOW"
    QUEUE = "QUEUE"
    DEFER = "DEFER"
    BRIDGE = "BRIDGE"
    REJECT = "REJECT"


class VibePreset(str, enum.Enum):
    PARTY = "party"
    ROMANTIC = "romantic"
    SAD = "sad"
    CHILL = "chill"
    HYPE = "hype"
    DANCE = "dance"
    NOSTALGIC = "nostalgic"
    CELEBRATION = "celebration"
    EMOTIONAL = "emotional"
    CUSTOM = "custom"


class EventType(str, enum.Enum):
    COLLEGE_PARTY = "college_party"
    BIRTHDAY = "birthday"
    WEDDING = "wedding"
    SANGEET = "sangeet"
    HOUSE_PARTY = "house_party"
    BOYS_NIGHTOUT = "boys_nightout"
    GIRLS_NIGHTOUT = "girls_nightout"
    CORPORATE = "corporate"
    SCHOOL_EVENT = "school_event"
    ROMANTIC_EVENING = "romantic_evening"
    FAMILY_FUNCTION = "family_function"
    FESTIVAL = "festival"
    CHILL_GATHERING = "chill_gathering"
    CUSTOM = "custom"


class AgentRole(str, enum.Enum):
    DJ_ORCHESTRATOR = "DJ_ORCHESTRATOR"
    VIBE_AGENT = "VIBE_AGENT"
    SONG_SELECTION = "SONG_SELECTION"
    REQUEST_AGENT = "REQUEST_AGENT"
    LYRICS_AGENT = "LYRICS_AGENT"
    TRANSITION_AGENT = "TRANSITION_AGENT"
    LEARNING_AGENT = "LEARNING_AGENT"
    AUDIO_ANALYZER = "AUDIO_ANALYZER"
    POLICY_ENGINE = "POLICY_ENGINE"


class AgentStatus(str, enum.Enum):
    IDLE = "IDLE"
    ACTIVE = "ACTIVE"
    ANALYZING = "ANALYZING"
    WAITING = "WAITING"
    ERROR = "ERROR"


class AIMessageType(str, enum.Enum):
    DJ_DECISION = "DJ_DECISION"
    VIBE_UPDATE = "VIBE_UPDATE"
    REQUEST_DECISION = "REQUEST_DECISION"
    QUEUE_REVIEW = "QUEUE_REVIEW"
    LYRIC_ANALYSIS = "LYRIC_ANALYSIS"
    EVENT_SUMMARY = "EVENT_SUMMARY"
    LEARNING_ANALYSIS = "LEARNING_ANALYSIS"
    TRANSITION_REVIEW = "TRANSITION_REVIEW"


class PlaybackState(str, enum.Enum):
    STOPPED = "STOPPED"
    PLAYING = "PLAYING"
    PAUSED = "PAUSED"


class AnalysisStatus(str, enum.Enum):
    PENDING = "PENDING"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETE = "COMPLETE"
    FAILED = "FAILED"
    NOT_AVAILABLE = "NOT_AVAILABLE"


class SystemMode(str, enum.Enum):
    NORMAL = "NORMAL"
    FALLBACK = "FALLBACK"
    DRY_RUN = "DRY_RUN"
    SIMULATION = "SIMULATION"


# ---------------------------------------------------------------------------
# Base Pydantic model with common config
# ---------------------------------------------------------------------------
class DJBaseModel(BaseModel):
    """Base model with standard serialization config."""

    model_config = {
        "from_attributes": True,
        "populate_by_name": True,
    }


# ---------------------------------------------------------------------------
# Common embedded types
# ---------------------------------------------------------------------------
class VibeVector(DJBaseModel):
    """Multi-dimensional vibe representation."""

    energy: float = Field(default=0.5, ge=0.0, le=1.0)
    danceability: float = Field(default=0.5, ge=0.0, le=1.0)
    valence: float = Field(default=0.5, ge=0.0, le=1.0)
    romance: float = Field(default=0.0, ge=0.0, le=1.0)
    nostalgia: float = Field(default=0.0, ge=0.0, le=1.0)
    aggression: float = Field(default=0.0, ge=0.0, le=1.0)
    chill: float = Field(default=0.0, ge=0.0, le=1.0)

    def distance(self, other: "VibeVector") -> float:
        """Euclidean distance between two vibe vectors."""
        dims = ["energy", "danceability", "valence", "romance", "nostalgia", "aggression", "chill"]
        return sum((getattr(self, d) - getattr(other, d)) ** 2 for d in dims) ** 0.5

    def blend(self, target: "VibeVector", alpha: float = 0.3) -> "VibeVector":
        """Blend this vector toward target by alpha (0=no change, 1=fully target)."""
        dims = ["energy", "danceability", "valence", "romance", "nostalgia", "aggression", "chill"]
        new_vals = {}
        for d in dims:
            current = getattr(self, d)
            tgt = getattr(target, d)
            new_vals[d] = current + alpha * (tgt - current)
        return VibeVector(**new_vals)

    def to_dict(self) -> dict[str, float]:
        return self.model_dump()

    @classmethod
    def from_preset(cls, preset: VibePreset) -> "VibeVector":
        """Create a vibe vector from a named preset."""
        presets: dict[VibePreset, dict[str, float]] = {
            VibePreset.PARTY: dict(energy=0.88, danceability=0.91, valence=0.78, romance=0.12, nostalgia=0.15, aggression=0.18, chill=0.05),
            VibePreset.ROMANTIC: dict(energy=0.35, danceability=0.30, valence=0.70, romance=0.92, nostalgia=0.40, aggression=0.02, chill=0.55),
            VibePreset.SAD: dict(energy=0.20, danceability=0.15, valence=0.15, romance=0.30, nostalgia=0.70, aggression=0.05, chill=0.45),
            VibePreset.CHILL: dict(energy=0.25, danceability=0.30, valence=0.60, romance=0.20, nostalgia=0.35, aggression=0.02, chill=0.92),
            VibePreset.HYPE: dict(energy=0.95, danceability=0.90, valence=0.85, romance=0.05, nostalgia=0.08, aggression=0.40, chill=0.02),
            VibePreset.DANCE: dict(energy=0.85, danceability=0.95, valence=0.80, romance=0.10, nostalgia=0.10, aggression=0.10, chill=0.05),
            VibePreset.NOSTALGIC: dict(energy=0.45, danceability=0.40, valence=0.55, romance=0.25, nostalgia=0.92, aggression=0.05, chill=0.35),
            VibePreset.CELEBRATION: dict(energy=0.82, danceability=0.85, valence=0.90, romance=0.15, nostalgia=0.20, aggression=0.08, chill=0.08),
            VibePreset.EMOTIONAL: dict(energy=0.30, danceability=0.20, valence=0.35, romance=0.45, nostalgia=0.60, aggression=0.05, chill=0.30),
            VibePreset.CUSTOM: dict(energy=0.50, danceability=0.50, valence=0.50, romance=0.50, nostalgia=0.50, aggression=0.10, chill=0.30),
        }
        return cls(**presets.get(preset, presets[VibePreset.CUSTOM]))


class EnergyCurvePoint(DJBaseModel):
    time_minutes: int = Field(ge=0)
    energy: float = Field(ge=0.0, le=1.0)


class ScoreComponents(DJBaseModel):
    """Transparent breakdown of all positive score components."""

    vibe_match: float = 0.0
    energy_match: float = 0.0
    genre_match: float = 0.0
    language_match: float = 0.0
    transition_score: float = 0.0
    popularity: float = 0.0
    event_type_match: float = 0.0
    request_score: float = 0.0
    crowd_feedback: float = 0.0
    learned_preference: float = 0.0

    def total(self, weights: dict[str, float] | None = None) -> float:
        if weights is None:
            return sum(self.model_dump().values())
        return sum(getattr(self, k, 0.0) * v for k, v in weights.items())


class PenaltyComponents(DJBaseModel):
    """Transparent breakdown of all penalties."""

    recency_penalty: float = 0.0
    artist_repetition_penalty: float = 0.0
    genre_repetition_penalty: float = 0.0
    album_repetition_penalty: float = 0.0
    energy_jump_penalty: float = 0.0
    mood_jump_penalty: float = 0.0
    bpm_jump_penalty: float = 0.0
    explicit_penalty: float = 0.0
    overplay_penalty: float = 0.0
    transition_penalty: float = 0.0
    low_historical_penalty: float = 0.0
    duplicate_version_penalty: float = 0.0

    def total(self, weights: dict[str, float] | None = None) -> float:
        if weights is None:
            return sum(self.model_dump().values())
        return sum(getattr(self, k, 0.0) * v for k, v in weights.items())
