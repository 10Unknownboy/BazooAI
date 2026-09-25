"""Tests for the cache layer (spec §51)."""

from __future__ import annotations

import pytest

from app.caching.api_cache import APICache
from app.database.repositories import CacheRepository
from app.database.engine import Base
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


def test_cache_repository_returns_none_on_miss():
    """Cache repository should return None for non-existent entries."""
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    
    repo = CacheRepository(session=session)
    result = repo.get("test_provider", "song_metadata", "nonexistent_id")
    assert result is None
    
    session.close()


def test_cache_repository_save_and_retrieve():
    """Saved data should be retrievable from cache repository."""
    from app.models.cache import CacheEntry
    
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    
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
    Session = sessionmaker(bind=engine)
    session = Session()
    
    repo = CacheRepository(session=session)
    stats = repo.stats()
    assert isinstance(stats, dict)
    assert "total_entries" in stats
    
    session.close()
