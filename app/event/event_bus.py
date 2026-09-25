"""
Lightweight local event bus for runtime state observation.

The DJ Orchestrator is the single source of truth for EventState.
All consoles (Dashboard, Debug, API) observe the same runtime state
through this event bus rather than maintaining separate copies.
"""

from __future__ import annotations

import asyncio
import logging
import threading
from collections import defaultdict
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable

from pydantic import Field

from app.models.base import DJBaseModel, generate_id, utc_now

logger = logging.getLogger("event_bus")


# ---------------------------------------------------------------------------
# Event types
# ---------------------------------------------------------------------------
class BusEvent(str, Enum):
    # Playback
    SONG_STARTED = "SONG_STARTED"
    SONG_ENDED = "SONG_ENDED"
    PLAYBACK_PAUSED = "PLAYBACK_PAUSED"
    PLAYBACK_RESUMED = "PLAYBACK_RESUMED"
    PLAYBACK_STOPPED = "PLAYBACK_STOPPED"
    PLAYBACK_SKIPPED = "PLAYBACK_SKIPPED"

    # Queue
    QUEUE_UPDATED = "QUEUE_UPDATED"
    QUEUE_ITEM_ADDED = "QUEUE_ITEM_ADDED"
    QUEUE_ITEM_REMOVED = "QUEUE_ITEM_REMOVED"
    QUEUE_REFILL_NEEDED = "QUEUE_REFILL_NEEDED"

    # Event lifecycle
    EVENT_STARTED = "EVENT_STARTED"
    EVENT_PAUSED = "EVENT_PAUSED"
    EVENT_RESUMED = "EVENT_RESUMED"
    EVENT_ENDED = "EVENT_ENDED"
    EVENT_STATE_UPDATED = "EVENT_STATE_UPDATED"

    # Vibe & Energy
    VIBE_CHANGED = "VIBE_CHANGED"
    ENERGY_CHANGED = "ENERGY_CHANGED"

    # Requests
    REQUEST_RECEIVED = "REQUEST_RECEIVED"
    REQUEST_DECIDED = "REQUEST_DECIDED"

    # Feedback
    FEEDBACK_RECEIVED = "FEEDBACK_RECEIVED"

    # AI / Agents
    AGENT_DECISION = "AGENT_DECISION"
    AI_REQUEST_SENT = "AI_REQUEST_SENT"
    AI_RESPONSE_RECEIVED = "AI_RESPONSE_RECEIVED"
    AI_UNAVAILABLE = "AI_UNAVAILABLE"

    # Analysis
    AUDIO_ANALYSIS_COMPLETE = "AUDIO_ANALYSIS_COMPLETE"
    LYRICS_ANALYSIS_COMPLETE = "LYRICS_ANALYSIS_COMPLETE"

    # Cache
    CACHE_HIT = "CACHE_HIT"
    CACHE_MISS = "CACHE_MISS"

    # System
    SYSTEM_MODE_CHANGED = "SYSTEM_MODE_CHANGED"
    ERROR = "ERROR"
    WARNING = "WARNING"

    # Policy
    POLICY_VIOLATION = "POLICY_VIOLATION"

    # Scoring
    SCORING_COMPLETE = "SCORING_COMPLETE"

    # Commands
    COMMAND_EXECUTED = "COMMAND_EXECUTED"


class BusMessage(DJBaseModel):
    """A message published on the event bus."""

    message_id: str = Field(default_factory=lambda: generate_id("MSG"))
    event_type: BusEvent
    source: str = ""  # which component published
    data: dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=utc_now)


# ---------------------------------------------------------------------------
# Synchronous event bus (thread-safe)
# ---------------------------------------------------------------------------
class EventBus:
    """
    Thread-safe synchronous event bus.
    Subscribers receive BusMessage objects when events they subscribed to are published.
    """

    def __init__(self):
        self._subscribers: dict[BusEvent, list[Callable[[BusMessage], None]]] = defaultdict(list)
        self._global_subscribers: list[Callable[[BusMessage], None]] = []
        self._lock = threading.Lock()
        self._history: list[BusMessage] = []
        self._max_history = 1000

    def subscribe(self, event_type: BusEvent, callback: Callable[[BusMessage], None]) -> None:
        """Subscribe to a specific event type."""
        with self._lock:
            self._subscribers[event_type].append(callback)

    def subscribe_all(self, callback: Callable[[BusMessage], None]) -> None:
        """Subscribe to ALL event types (useful for debug console)."""
        with self._lock:
            self._global_subscribers.append(callback)

    def unsubscribe(self, event_type: BusEvent, callback: Callable[[BusMessage], None]) -> None:
        """Unsubscribe from a specific event type."""
        with self._lock:
            if callback in self._subscribers[event_type]:
                self._subscribers[event_type].remove(callback)

    def publish(self, event_type: BusEvent, source: str = "", data: dict[str, Any] | None = None) -> BusMessage:
        """Publish an event to all subscribers."""
        message = BusMessage(
            event_type=event_type,
            source=source,
            data=data or {},
        )

        with self._lock:
            # Store in history
            self._history.append(message)
            if len(self._history) > self._max_history:
                self._history = self._history[-self._max_history:]

            # Get subscriber lists (copy to avoid holding lock during callbacks)
            specific = list(self._subscribers.get(event_type, []))
            global_subs = list(self._global_subscribers)

        # Call subscribers outside lock
        for callback in specific:
            try:
                callback(message)
            except Exception as e:
                logger.error(f"Event bus subscriber error ({event_type}): {e}")

        for callback in global_subs:
            try:
                callback(message)
            except Exception as e:
                logger.error(f"Event bus global subscriber error ({event_type}): {e}")

        return message

    def get_history(self, event_type: BusEvent | None = None, limit: int = 50) -> list[BusMessage]:
        """Get recent event history, optionally filtered by type."""
        with self._lock:
            if event_type:
                filtered = [m for m in self._history if m.event_type == event_type]
            else:
                filtered = list(self._history)
        return filtered[-limit:]

    def clear_history(self) -> None:
        with self._lock:
            self._history.clear()


# ---------------------------------------------------------------------------
# Runtime State — single shared reference to live event state
# ---------------------------------------------------------------------------
class RuntimeState:
    """
    Shared runtime state container.
    The Orchestrator writes to this; consoles read from it.
    Thread-safe via lock.
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._event_state: dict[str, Any] | None = None
        self._queue_state: dict[str, Any] | None = None
        self._agent_statuses: dict[str, str] = {}
        self._system_mode: str = "NORMAL"
        self._last_update: datetime | None = None

    def update_event_state(self, state_dict: dict[str, Any]) -> None:
        with self._lock:
            self._event_state = state_dict
            self._last_update = datetime.now(timezone.utc)

    def get_event_state(self) -> dict[str, Any] | None:
        with self._lock:
            return self._event_state.copy() if self._event_state else None

    def update_queue_state(self, queue_dict: dict[str, Any]) -> None:
        with self._lock:
            self._queue_state = queue_dict

    def get_queue_state(self) -> dict[str, Any] | None:
        with self._lock:
            return self._queue_state.copy() if self._queue_state else None

    def update_agent_status(self, agent: str, status: str) -> None:
        with self._lock:
            self._agent_statuses[agent] = status

    def get_agent_statuses(self) -> dict[str, str]:
        with self._lock:
            return self._agent_statuses.copy()

    def set_system_mode(self, mode: str) -> None:
        with self._lock:
            self._system_mode = mode

    def get_system_mode(self) -> str:
        with self._lock:
            return self._system_mode


# ---------------------------------------------------------------------------
# Global singletons
# ---------------------------------------------------------------------------
_event_bus: EventBus | None = None
_runtime_state: RuntimeState | None = None


def get_event_bus() -> EventBus:
    global _event_bus
    if _event_bus is None:
        _event_bus = EventBus()
    return _event_bus


def get_runtime_state() -> RuntimeState:
    global _runtime_state
    if _runtime_state is None:
        _runtime_state = RuntimeState()
    return _runtime_state
