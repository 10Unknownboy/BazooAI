from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, Mock

from app.agents.orchestrator import DJOrchestrator
from app.models.base import VibePreset, VibeVector
from app.models.event import EventConfig, EventState
from app.models.song import LyricsFeatures, Song
from app.policies.policy_engine import PolicyEngine
from app.queue.queue_manager import QueueManager
from app.ranking.scoring_engine import ScoringEngine


def test_full_vibe_vector_and_lyrics_features_change_candidate_score():
    event = EventState(
        event_id="event-vibe",
        event_config=EventConfig(event_id="event-vibe", languages=[]),
        vibe_vector=VibeVector.from_preset(VibePreset.ROMANTIC),
    )
    romantic = Song(
        song_id="romantic",
        title="Romantic",
        artist="Artist",
        energy=0.35,
        danceability=0.3,
        valence=0.7,
        lyrics_features=LyricsFeatures(
            song_id="romantic",
            romance=0.92,
            nostalgia=0.4,
            aggression=0.02,
        ),
    )
    aggressive = romantic.model_copy(
        update={
            "song_id": "aggressive",
            "lyrics_features": LyricsFeatures(
                song_id="aggressive",
                romance=0.05,
                nostalgia=0.05,
                aggression=0.95,
            ),
        }
    )

    engine = ScoringEngine()

    assert engine.calculate_vibe_match(romantic, event) > engine.calculate_vibe_match(
        aggressive, event
    )


def test_queue_reconsideration_keeps_locked_head():
    queue = QueueManager()
    for position in range(5):
        queue.add_song(f"song-{position}", 50.0)

    removed = queue.clear_reconsidering()

    assert removed == 2
    assert [item.song_id for item in queue.items] == ["song-0", "song-1", "song-2"]


def test_custom_artist_preferences_and_lyrics_explicitness_affect_decisions():
    event = EventState(
        event_id="event-policy",
        event_config=EventConfig(
            event_id="event-policy",
            languages=[],
            prefer_artists=["Preferred Artist"],
            explicit_allowed=False,
        ),
    )
    preferred = Song(song_id="preferred", title="Track", artist="Preferred Artist")
    explicit_lyrics = Song(
        song_id="explicit",
        title="Track",
        artist="Other Artist",
        lyrics_features=LyricsFeatures(
            song_id="explicit",
            explicitness=0.9,
            family_friendly=False,
        ),
    )
    engine = ScoringEngine()

    assert engine.calculate_artist_match(preferred, event) == 100.0
    assert not PolicyEngine().check_song(explicit_lyrics, event).passed


def test_manual_vibe_is_not_overwritten_by_next_decision_cycle(sample_event_state):
    orchestrator = DJOrchestrator.__new__(DJOrchestrator)
    orchestrator._decision_lock = asyncio.Lock()
    orchestrator.is_running = True
    orchestrator.current_state = sample_event_state
    orchestrator.current_state.vibe_vector = VibeVector.from_preset(VibePreset.PARTY)
    orchestrator._manual_vibe_override = True
    orchestrator.vibe_agent = Mock(evaluate_vibe=AsyncMock())
    orchestrator.queue_manager = Mock(needs_refill=Mock(return_value=False), items=[])
    orchestrator.event_repository = Mock()
    orchestrator._publish_runtime_state = Mock()

    asyncio.run(orchestrator.run_decision_cycle("feedback_received"))

    orchestrator.vibe_agent.evaluate_vibe.assert_not_awaited()
    assert orchestrator.current_state.vibe_vector == VibeVector.from_preset(VibePreset.PARTY)
