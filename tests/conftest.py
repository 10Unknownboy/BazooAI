"""Shared pytest fixtures for the AI DJ system tests."""

from __future__ import annotations

import os
import sys
import pytest

# Ensure project root is on path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.models.base import VibeVector, VibePreset, LockStatus
from app.models.song import Song, AudioFeatures
from app.models.event import EventConfig, EventState
from app.models.queue import QueueItem, QueueState
from app.database.engine import Base, get_engine, get_session_factory, init_database
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


@pytest.fixture
def in_memory_engine():
    """Create an in-memory SQLite database for testing."""
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(engine)
    return engine


@pytest.fixture
def db_session(in_memory_engine):
    """Create a test database session."""
    Session = sessionmaker(bind=in_memory_engine)
    session = Session()
    yield session
    session.close()


@pytest.fixture
def sample_song() -> Song:
    """A realistic test song."""
    return Song(
        song_id="SNG_test001",
        title="Tauba Tauba",
        artist="Karan Aujla",
        artists=["Karan Aujla"],
        album="Bad Newz",
        release_year=2024,
        duration=210.0,
        language="Punjabi",
        languages=["Punjabi", "Hindi"],
        genre="Punjabi Pop",
        genres=["Punjabi Pop", "Bollywood"],
        explicit=False,
        popularity=0.85,
        bpm=104.0,
        energy=0.91,
        danceability=0.87,
        valence=0.79,
    )


@pytest.fixture
def sample_song_explicit() -> Song:
    """An explicit test song."""
    return Song(
        song_id="SNG_test002",
        title="Explicit Track",
        artist="Test Artist",
        artists=["Test Artist"],
        duration=200.0,
        language="English",
        genre="Hip Hop",
        explicit=True,
        popularity=0.70,
        bpm=90.0,
        energy=0.80,
        danceability=0.75,
        valence=0.60,
    )


@pytest.fixture
def sample_song_b() -> Song:
    """A second test song for comparison / transitions."""
    return Song(
        song_id="SNG_test003",
        title="Brown Munde",
        artist="AP Dhillon",
        artists=["AP Dhillon", "Gurinder Gill"],
        duration=185.0,
        language="Punjabi",
        genre="Punjabi Pop",
        explicit=False,
        popularity=0.90,
        bpm=100.0,
        energy=0.88,
        danceability=0.85,
        valence=0.75,
    )


@pytest.fixture
def sample_event_config() -> EventConfig:
    """A test event configuration."""
    return EventConfig(
        event_id="EVT_test001",
        name="Test College Party",
        event_type="college_party",
        min_age=17,
        max_age=23,
        duration_minutes=240,
        languages=["Hindi", "Punjabi", "English"],
        starting_vibe=VibePreset.PARTY,
        explicit_allowed=False,
        prefer_genres=["Bollywood", "Punjabi Pop"],
        avoid_genres=["Classical"],
        allow_requests=True,
    )


@pytest.fixture
def sample_event_state(sample_event_config) -> EventState:
    """A test event state."""
    return EventState(
        event_id=sample_event_config.event_id,
        event_config=sample_event_config,
        current_vibe=VibePreset.PARTY,
        vibe_vector=VibeVector.from_preset(VibePreset.PARTY),
        target_energy=0.85,
        current_energy=0.80,
        recent_history=[],
        recent_artists=[],
        recent_genres=[],
        songs_played_count=10,
        elapsed_minutes=60.0,
        event_progress=0.25,
    )


@pytest.fixture
def sample_queue() -> QueueState:
    """A test queue with 5 items."""
    items = []
    for i, (sid, title, artist, lock) in enumerate([
        ("SNG_q1", "Song A", "Artist A", LockStatus.LOCKED),
        ("SNG_q2", "Song B", "Artist B", LockStatus.LOCKED),
        ("SNG_q3", "Song C", "Artist C", LockStatus.LOCKED),
        ("SNG_q4", "Song D", "Artist D", LockStatus.RECONSIDERING),
        ("SNG_q5", "Song E", "Artist E", LockStatus.FLEXIBLE),
    ]):
        items.append(QueueItem(
            song_id=sid,
            position=i,
            lock_status=lock,
            final_score=90.0 - i * 3,
            song_title=title,
            song_artist=artist,
        ))
    return QueueState(items=items)
