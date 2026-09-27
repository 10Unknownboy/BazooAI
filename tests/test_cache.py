"""Tests for the cache layer (spec §51)."""

from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.caching.api_cache import APICache
from app.database.engine import Base
from app.database.repositories import CacheRepository


def test_cache_repository_returns_none_on_miss():
    """Cache repository should return None for non-existent entries."""
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)
    session = session_factory()

    repo = CacheRepository(session=session)
    result = repo.get("test_provider", "song_metadata", "nonexistent_id")
    assert result is None

    session.close()


def test_cache_repository_save_and_retrieve():
    """Saved data should be retrievable from cache repository."""
    from app.models.cache import CacheEntry

    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)
    session = session_factory()

    repo = CacheRepository(session=session)
    entry = CacheEntry(
        provider="test_provider",
        resource_type="song_metadata",
        resource_id="song_123",
        data={"title": "Test Song", "artist": "Test Artist"},
    )
    repo.save(entry)

    result = repo.get("test_provider", "song_metadata", "song_123")
    assert result is not None
    assert result.data["title"] == "Test Song"

    session.close()


def test_cache_stats():
    """Cache repository should report stats."""
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)
    session = session_factory()

    repo = CacheRepository(session=session)
    stats = repo.stats()
    assert isinstance(stats, dict)
    assert "total_entries" in stats

    session.close()


def test_api_cache_uses_repository_contract_and_supports_invalidation():
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    api_cache = APICache(CacheRepository(session=session))

    assert api_cache.get("musicbrainz", "song_metadata", "song-1") is None
    api_cache.save(
        "musicbrainz",
        "song_metadata",
        "song-1",
        {"title": "Cached Song"},
        ttl_seconds=60,
    )
    assert api_cache.get("musicbrainz", "song_metadata", "song-1") == {"title": "Cached Song"}
    assert api_cache.stats["cache_hit"] == 1
    assert api_cache.stats["cache_miss"] == 1
    assert api_cache.invalidate("musicbrainz", "song_metadata", "song-1")
    assert api_cache.get("musicbrainz", "song_metadata", "song-1") is None
    session.close()
