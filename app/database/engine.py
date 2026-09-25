"""
Database engine, table definitions, and session management.

Uses SQLAlchemy 2.0 with SQLite + WAL mode for development.
Schema is PostgreSQL-compatible for future migration.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    create_engine,
    event,
)
from sqlalchemy.orm import (
    DeclarativeBase,
    Session,
    sessionmaker,
    relationship,
)

from app.config.settings import get_settings, DATA_DIR


# ---------------------------------------------------------------------------
# Base
# ---------------------------------------------------------------------------
class Base(DeclarativeBase):
    pass


# ---------------------------------------------------------------------------
# SQLite WAL mode
# ---------------------------------------------------------------------------
def _set_sqlite_wal(dbapi_conn, connection_record):
    cursor = dbapi_conn.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA synchronous=NORMAL")
    cursor.execute("PRAGMA busy_timeout=5000")
    cursor.close()


# ---------------------------------------------------------------------------
# Engine factory
# ---------------------------------------------------------------------------
_engine = None
_SessionLocal = None


def get_engine(url: str | None = None):
    global _engine
    if _engine is None:
        if url is None:
            url = get_settings().database.url
        # Ensure SQLite path parent directory exists
        if url.startswith("sqlite:///"):
            db_path = Path(url.replace("sqlite:///", ""))
            db_path.parent.mkdir(parents=True, exist_ok=True)
        _engine = create_engine(
            url,
            echo=False,
            pool_pre_ping=True,
            connect_args={"check_same_thread": False} if "sqlite" in url else {},
        )
        # Enable WAL mode for SQLite
        if "sqlite" in url:
            event.listen(_engine, "connect", _set_sqlite_wal)
    return _engine


def get_session_factory(engine=None) -> sessionmaker:
    global _SessionLocal
    if _SessionLocal is None:
        if engine is None:
            engine = get_engine()
        _SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    return _SessionLocal


def get_session() -> Session:
    factory = get_session_factory()
    return factory()


def init_database(url: str | None = None) -> None:
    """Create all tables. Safe to call multiple times."""
    engine = get_engine(url)
    Base.metadata.create_all(engine)


# ---------------------------------------------------------------------------
# Table definitions
# ---------------------------------------------------------------------------

class SongTable(Base):
    __tablename__ = "songs"

    song_id = Column(String(50), primary_key=True)
    title = Column(String(500), nullable=False, index=True)
    artist = Column(String(500), nullable=False, index=True)
    artists = Column(JSON, default=list)
    album = Column(String(500))
    album_id = Column(String(50))
    release_year = Column(Integer)
    release_date = Column(String(20))
    duration = Column(Float)
    language = Column(String(50), index=True)
    languages = Column(JSON, default=list)
    genre = Column(String(100), index=True)
    subgenre = Column(String(100))
    genres = Column(JSON, default=list)
    explicit = Column(Boolean, default=False)
    popularity = Column(Float, default=0.5)
    is_remix = Column(Boolean, default=False)
    is_live = Column(Boolean, default=False)
    is_clean_version = Column(Boolean, default=False)
    version_type = Column(String(50))
    original_song_id = Column(String(50))

    bpm = Column(Float)
    key = Column(String(20))
    energy = Column(Float)
    danceability = Column(Float)
    valence = Column(Float)

    lyrics_available = Column(Boolean, default=False)
    lyrics_analysis_available = Column(Boolean, default=False)
    audio_analysis_status = Column(String(20), default="PENDING")
    lyrics_analysis_status = Column(String(20), default="PENDING")

    source_provider = Column(String(50))
    source_provider_id = Column(String(200))
    provider_ids = Column(JSON, default=dict)

    file_path = Column(Text)
    file_hash = Column(String(128))

    first_seen = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    last_updated = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class AudioFeaturesTable(Base):
    __tablename__ = "audio_features"

    id = Column(Integer, primary_key=True, autoincrement=True)
    song_id = Column(String(50), ForeignKey("songs.song_id"), unique=True, index=True)

    bpm = Column(Float)
    tempo = Column(Float)
    key = Column(String(20))
    loudness = Column(Float)
    energy = Column(Float)
    danceability = Column(Float)
    valence = Column(Float)
    acousticness = Column(Float)
    instrumentalness = Column(Float)
    speechiness = Column(Float)
    spectral_centroid = Column(Float)
    spectral_bandwidth = Column(Float)
    spectral_rolloff = Column(Float)
    zero_crossing_rate = Column(Float)
    mfcc_mean = Column(JSON)
    chroma_mean = Column(JSON)
    onset_rate = Column(Float)
    duration = Column(Float)

    file_hash = Column(String(128))
    analyzer_version = Column(String(50))
    analysis_version = Column(Integer, default=1)
    analysis_status = Column(String(20), default="PENDING")
    analyzed_at = Column(DateTime)

    audio_embedding = Column(JSON)


class LyricsFeaturesTable(Base):
    __tablename__ = "lyrics_features"

    id = Column(Integer, primary_key=True, autoincrement=True)
    song_id = Column(String(50), ForeignKey("songs.song_id"), unique=True, index=True)

    language = Column(String(50))
    themes = Column(JSON, default=list)
    sentiment = Column(Float)
    mood = Column(String(50))
    romance = Column(Float, default=0.0)
    sadness = Column(Float, default=0.0)
    celebration = Column(Float, default=0.0)
    aggression = Column(Float, default=0.0)
    sexual_content = Column(Float, default=0.0)
    explicitness = Column(Float, default=0.0)
    violence = Column(Float, default=0.0)
    drugs = Column(Float, default=0.0)
    breakup = Column(Float, default=0.0)
    nostalgia = Column(Float, default=0.0)
    family_friendly = Column(Boolean, default=True)
    event_suitability = Column(JSON, default=dict)

    source = Column(String(50))
    content_hash = Column(String(128))
    analysis_model = Column(String(100))
    analysis_version = Column(Integer, default=1)
    analysis_status = Column(String(20), default="PENDING")
    analyzed_at = Column(DateTime)

    lyrics_embedding = Column(JSON)


class EventTable(Base):
    __tablename__ = "events"

    event_id = Column(String(50), primary_key=True)
    name = Column(String(200))
    event_type = Column(String(50))
    config_json = Column(JSON)
    state_json = Column(JSON)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    ended_at = Column(DateTime)
    is_active = Column(Boolean, default=True)


class PlayHistoryTable(Base):
    __tablename__ = "play_history"

    id = Column(Integer, primary_key=True, autoincrement=True)
    event_id = Column(String(50), ForeignKey("events.event_id"), index=True)
    song_id = Column(String(50), ForeignKey("songs.song_id"), index=True)
    position = Column(Integer)
    start_time = Column(DateTime)
    end_time = Column(DateTime)
    duration_played = Column(Float)
    score = Column(Float)
    score_components = Column(JSON)
    penalties = Column(JSON)
    vibe_at_selection = Column(JSON)
    energy_at_selection = Column(Float)
    previous_song_id = Column(String(50))
    next_song_id = Column(String(50))
    request_related = Column(Boolean, default=False)
    request_id = Column(String(50))
    feedback_rating = Column(Integer)
    decision_epoch = Column(Integer)
    timestamp = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class RequestTable(Base):
    __tablename__ = "requests"

    request_id = Column(String(50), primary_key=True)
    event_id = Column(String(50), ForeignKey("events.event_id"), index=True)
    requested_song_query = Column(Text)
    matched_song_id = Column(String(50))
    requester = Column(String(200))
    status = Column(String(30), default="RECEIVED", index=True)
    status_history = Column(JSON, default=list)
    decision = Column(String(30))
    decision_reason = Column(Text)
    decision_confidence = Column(Float)
    priority = Column(Float, default=0.0)
    target_position = Column(Integer)
    bridge_strategy = Column(JSON)
    context_json = Column(JSON)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    decided_at = Column(DateTime)
    played_at = Column(DateTime)
    satisfied_at = Column(DateTime)


class FeedbackTable(Base):
    __tablename__ = "song_feedback"

    feedback_id = Column(String(50), primary_key=True)
    event_id = Column(String(50), ForeignKey("events.event_id"), index=True)
    song_id = Column(String(50), ForeignKey("songs.song_id"), index=True)
    overall_rating = Column(Integer)
    energy_rating = Column(Integer)
    song_choice_rating = Column(Integer)
    transition_rating = Column(Integer)
    vibe_rating = Column(Integer)
    context_json = Column(JSON)
    decision_epoch = Column(Integer)
    was_requested = Column(Boolean, default=False)
    request_id = Column(String(50))
    timestamp = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class TransitionFeedbackTable(Base):
    __tablename__ = "transition_feedback"

    feedback_id = Column(String(50), primary_key=True)
    event_id = Column(String(50), ForeignKey("events.event_id"), index=True)
    from_song_id = Column(String(50), index=True)
    to_song_id = Column(String(50), index=True)
    transition_rating = Column(Integer)
    context_json = Column(JSON)
    decision_epoch = Column(Integer)
    timestamp = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class EventFeedbackTable(Base):
    __tablename__ = "event_feedback"

    feedback_id = Column(String(50), primary_key=True)
    event_id = Column(String(50), ForeignKey("events.event_id"), index=True)
    overall_performance = Column(Integer)
    song_selection = Column(Integer)
    vibe_maintenance = Column(Integer)
    transitions = Column(Integer)
    request_handling = Column(Integer)
    variety = Column(Integer)
    songs_played = Column(Integer)
    total_requests = Column(Integer)
    accepted_requests = Column(Integer)
    deferred_requests = Column(Integer)
    rejected_requests = Column(Integer)
    average_song_feedback = Column(Float)
    comments = Column(Text)
    timestamp = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class AgentDecisionTable(Base):
    __tablename__ = "agent_decisions"

    decision_id = Column(String(50), primary_key=True)
    agent = Column(String(50), index=True)
    decision_type = Column(String(50))
    decision = Column(String(50))
    reason = Column(Text)
    confidence = Column(Float)
    event_id = Column(String(50), index=True)
    current_song_id = Column(String(50))
    candidate_song_id = Column(String(50))
    request_id = Column(String(50))
    decision_epoch = Column(Integer)
    input_data = Column(JSON)
    output_data = Column(JSON)
    latency_ms = Column(Float)
    used_ai = Column(Boolean, default=False)
    ai_fallback = Column(Boolean, default=False)
    timestamp = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class ScoringSnapshotTable(Base):
    __tablename__ = "scoring_snapshots"

    snapshot_id = Column(String(50), primary_key=True)
    event_id = Column(String(50), index=True)
    decision_epoch = Column(Integer, index=True)
    song_id = Column(String(50), index=True)
    final_score = Column(Float)
    score_components = Column(JSON)
    penalty_components = Column(JSON)
    scoring_weights = Column(JSON)
    penalty_weights = Column(JSON)
    policy_passed = Column(Boolean, default=True)
    policy_violations = Column(JSON)
    event_state_snapshot = Column(JSON)
    agent_recommendations = Column(JSON)
    candidate_features = Column(JSON)
    timestamp = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class RewardTable(Base):
    __tablename__ = "rewards"

    reward_id = Column(String(50), primary_key=True)
    event_id = Column(String(50), ForeignKey("events.event_id"), index=True)
    decision_epoch = Column(Integer)
    state_json = Column(JSON)
    action_song_id = Column(String(50))
    action_score = Column(Float)
    action_components = Column(JSON)
    reward = Column(Float)
    raw_feedback = Column(JSON)
    next_state_json = Column(JSON)
    context_json = Column(JSON)
    timestamp = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class LearnedPreferenceTable(Base):
    __tablename__ = "learned_preferences"

    id = Column(Integer, primary_key=True, autoincrement=True)
    event_type = Column(String(50), index=True)
    context_key = Column(String(200), index=True)
    preference_type = Column(String(50))  # genre, artist, transition, song
    preference_value = Column(String(200))
    score_adjustment = Column(Float, default=0.0)
    confidence = Column(Float, default=0.0)
    sample_count = Column(Integer, default=0)
    last_reward = Column(Float)
    average_reward = Column(Float)
    context_json = Column(JSON)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class APICacheTable(Base):
    __tablename__ = "api_cache"

    cache_id = Column(String(50), primary_key=True)
    provider = Column(String(50), index=True)
    resource_type = Column(String(50), index=True)
    resource_id = Column(String(200), index=True)
    data = Column(JSON)
    cache_version = Column(Integer, default=1)
    source_url = Column(Text)
    status_code = Column(Integer)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    last_updated = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    expires_at = Column(DateTime)
    ttl_seconds = Column(Integer)
    hit_count = Column(Integer, default=0)
    last_accessed = Column(DateTime)

    __table_args__ = (
        Index("ix_cache_lookup", "provider", "resource_type", "resource_id"),
    )
