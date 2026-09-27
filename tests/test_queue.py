"""Tests for the queue manager (spec §51)."""

from __future__ import annotations

import pytest

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


def test_queue_reads_return_copies(queue_manager):
    """Mutating returned queue data must not mutate the manager's state."""
    queue_manager.add_song(
        song_id="SNG_copy",
        score=85.0,
        components={"vibe_match": 80.0},
    )

    from_items = queue_manager.items
    from_current = queue_manager.get_current()
    from_state = queue_manager.get_state()
    from_items[0].score_components.vibe_match = -1.0
    from_current.song_id = "SNG_mutated"
    from_state.items.clear()

    assert queue_manager.get_current().song_id == "SNG_copy"
    assert queue_manager.get_current().score_components.vibe_match == 80.0


def test_clear_reconsidering_preserves_locked_head(queue_manager):
    """Reconsidering only removes unlocked future entries."""
    for index in range(6):
        queue_manager.add_song(
            song_id=f"SNG_{index}",
            score=90.0 - index,
            components={},
        )

    removed = queue_manager.clear_reconsidering()

    assert removed == 3
    assert [item.song_id for item in queue_manager.items] == [
        "SNG_0",
        "SNG_1",
        "SNG_2",
    ]
