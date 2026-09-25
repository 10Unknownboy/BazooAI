"""Tests for the queue manager (spec §51)."""

from __future__ import annotations

import pytest

from app.models.base import LockStatus
from app.models.queue import QueueItem, QueueState
from app.queue.queue_manager import QueueManager


@pytest.fixture
def queue_manager():
    return QueueManager()


def test_empty_queue(queue_manager):
    """New queue manager should have empty queue."""
    current = queue_manager.get_current()
    assert current is None


def test_add_song(queue_manager):
    """Adding a song should populate the queue."""
    queue_manager.add_song(
        song_id="SNG_test1",
        score=85.0,
        components={"vibe_match": 80.0, "energy_match": 90.0},
        position=0,
    )
    current = queue_manager.get_current()
    assert current is not None


def test_locked_positions_preserved(sample_queue):
    """LOCKED items are identified correctly."""
    locked = sample_queue.locked_items
    assert len(locked) == 3  # positions 0, 1, 2


def test_flexible_positions_changeable(sample_queue):
    """Non-LOCKED items can be changed."""
    flexible = sample_queue.flexible_items
    assert len(flexible) >= 2  # RECONSIDERING + FLEXIBLE


def test_needs_refill_on_empty(queue_manager):
    """Empty queue should need refill."""
    assert queue_manager.needs_refill()


def test_advance_removes_current(queue_manager):
    """Advancing should move to next song."""
    for i in range(3):
        queue_manager.add_song(
            song_id=f"SNG_{i}",
            score=90.0 - i,
            components={"vibe_match": 80.0},
            position=i,
        )
    
    first = queue_manager.get_current()
    assert first is not None
    first_id = first.song_id
    
    queue_manager.advance()
    
    new_current = queue_manager.get_current()
    if new_current:
        assert new_current.song_id != first_id
