"""Queue item and queue state models with lock semantics."""

from __future__ import annotations

from datetime import datetime

from pydantic import Field

from app.models.base import (
    DJBaseModel,
    LockStatus,
    PenaltyComponents,
    ScoreComponents,
    generate_id,
    utc_now,
)


class QueueItem(DJBaseModel):
    """A single song in the DJ queue with scoring and lock metadata."""

    queue_item_id: str = Field(default_factory=lambda: generate_id("QI"))
    song_id: str
    position: int  # 0 = current, 1 = next, 2 = +2, ...
    lock_status: LockStatus = LockStatus.FLEXIBLE

    # Scoring snapshot at time of insertion
    final_score: float = 0.0
    score_components: ScoreComponents = Field(default_factory=ScoreComponents)
    penalty_components: PenaltyComponents = Field(default_factory=PenaltyComponents)

    # Decision context
    decision_epoch: int = 0
    added_at: datetime = Field(default_factory=utc_now)
    reason: str = ""

    # Request linkage
    request_id: str | None = None

    # Metadata cache for display (avoid repeated DB lookups)
    song_title: str | None = None
    song_artist: str | None = None
    song_bpm: float | None = None
    song_energy: float | None = None

    def is_locked(self) -> bool:
        return self.lock_status == LockStatus.LOCKED

    def can_be_changed(self) -> bool:
        return self.lock_status != LockStatus.LOCKED


class QueueState(DJBaseModel):
    """Complete queue snapshot."""

    items: list[QueueItem] = Field(default_factory=list)
    lookahead_size: int = 5
    last_updated: datetime = Field(default_factory=utc_now)

    @property
    def current(self) -> QueueItem | None:
        return self.items[0] if self.items else None

    @property
    def upcoming(self) -> list[QueueItem]:
        return self.items[1:] if len(self.items) > 1 else []

    @property
    def locked_items(self) -> list[QueueItem]:
        return [item for item in self.items if item.is_locked()]

    @property
    def flexible_items(self) -> list[QueueItem]:
        return [item for item in self.items if item.can_be_changed()]

    def needs_refill(self) -> bool:
        """True if the queue has fewer upcoming songs than the lookahead size."""
        return len(self.upcoming) < self.lookahead_size

    def song_ids(self) -> list[str]:
        return [item.song_id for item in self.items]
