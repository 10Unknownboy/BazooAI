"""
5-song rolling lookahead queue manager (spec §10, 58).

Lock states:
  - LOCKED (positions 0-2): Cannot be changed
  - RECONSIDERING (positions 3-4): May be swapped
  - FLEXIBLE (positions 5+): Can be freely changed

GUARANTEES:
  - Current song (position 0) is NEVER auto-removed
  - No silence gap — always enough prepared songs
"""

from __future__ import annotations

import logging
from typing import Any

from app.models.base import LockStatus
from app.models.queue import QueueItem, QueueState
from app.event.event_bus import get_event_bus, BusEvent

logger = logging.getLogger(__name__)


class QueueManager:
    """5-song rolling lookahead queue manager."""

    def __init__(self, lookahead_size: int = 5):
        self._state = QueueState(items=[])
        self._lookahead_size = lookahead_size
        self._event_bus = get_event_bus()

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------
    @property
    def items(self) -> list[QueueItem]:
        return self._state.items

    # ------------------------------------------------------------------
    # Core operations
    # ------------------------------------------------------------------
    def add_song(
        self,
        song_id: str,
        score: float,
        components: dict[str, float] | None = None,
        position: int | None = None,
        song_title: str = "",
        song_artist: str = "",
        decision_epoch: int = 0,
    ) -> QueueItem | None:
        """Add a song to the queue."""
        try:
            if position is None:
                position = len(self._state.items)
            position = min(position, len(self._state.items))

            lock = self._lock_for_position(position)

            item = QueueItem(
                song_id=song_id,
                position=position,
                lock_status=lock,
                final_score=score,
                score_components=components or {},
                song_title=song_title,
                song_artist=song_artist,
                decision_epoch=decision_epoch,
            )

            self._state.items.insert(position, item)
            self._refresh_positions()
            self._publish(BusEvent.QUEUE_ITEM_ADDED, {"song_id": song_id, "position": position})
            return item

        except Exception as e:
            logger.error(f"Error adding song to queue: {e}")
            return None

    def remove_at(self, position: int) -> bool:
        """Remove a song from the queue. Only non-LOCKED positions allowed."""
        if not (0 <= position < len(self._state.items)):
            return False
        item = self._state.items[position]
        if item.lock_status == LockStatus.LOCKED:
            logger.warning(f"Cannot remove LOCKED item at position {position}")
            return False
        self._state.items.pop(position)
        self._refresh_positions()
        self._publish(BusEvent.QUEUE_ITEM_REMOVED, {"position": position})
        return True

    def get_current(self) -> QueueItem | None:
        """Get the currently playing song (position 0)."""
        if self._state.items:
            return self._state.items[0]
        return None

    def get_upcoming(self) -> list[QueueItem]:
        """Get upcoming songs (positions 1+)."""
        return self._state.items[1:]

    def advance(self) -> QueueItem | None:
        """
        Move to the next song.
        Removes position 0, shifts everything, updates lock states.
        """
        if not self._state.items:
            return None

        played = self._state.items.pop(0)
        self._refresh_positions()

        if self.needs_refill():
            self._publish(BusEvent.QUEUE_REFILL_NEEDED, {})

        self._publish(BusEvent.QUEUE_UPDATED, {"action": "advance"})
        return played

    def needs_refill(self) -> bool:
        """Check if the queue needs more songs."""
        return len(self._state.items) < self._lookahead_size

    def get_flexible_positions(self) -> list[int]:
        """Get positions that can be changed."""
        return [
            item.position
            for item in self._state.items
            if item.can_be_changed()
        ]

    def get_state(self) -> QueueState:
        """Get a copy of the current queue state."""
        return self._state.model_copy(deep=True)

    def clear(self) -> None:
        """Clear all items from the queue."""
        self._state.items.clear()
        self._publish(BusEvent.QUEUE_UPDATED, {"action": "clear"})

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _lock_for_position(self, position: int) -> LockStatus:
        """Determine lock status based on position."""
        if position <= 2:
            return LockStatus.LOCKED
        elif position <= 4:
            return LockStatus.RECONSIDERING
        else:
            return LockStatus.FLEXIBLE

    def _refresh_positions(self) -> None:
        """Re-index positions and update lock statuses."""
        for i, item in enumerate(self._state.items):
            item.position = i
            item.lock_status = self._lock_for_position(i)

    def _publish(self, event: BusEvent, data: dict[str, Any] | None = None) -> None:
        """Publish a queue event to the event bus."""
        try:
            self._event_bus.publish(event, source="queue_manager", data=data or {})
        except Exception as e:
            logger.error(f"Failed to publish queue event: {e}")
