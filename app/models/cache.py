"""API and analysis cache models."""

from __future__ import annotations

from datetime import datetime, timedelta

from pydantic import Field

from app.models.base import DJBaseModel, generate_id, utc_now


class CacheEntry(DJBaseModel):
    """A single cached API response or analysis result."""

    cache_id: str = Field(default_factory=lambda: generate_id("CC"))
    provider: str  # e.g. "musicbrainz", "audd", "audio_analysis", "lyrics_analysis"
    resource_type: str  # e.g. "song_metadata", "artist", "audio_features"
    resource_id: str  # provider-specific ID or song_id

    # Data
    data: dict = Field(default_factory=dict)

    # Provenance
    cache_version: int = 1
    source_url: str | None = None
    status_code: int | None = None

    # Timing
    created_at: datetime = Field(default_factory=utc_now)
    last_updated: datetime = Field(default_factory=utc_now)
    expires_at: datetime | None = None
    ttl_seconds: int | None = None

    # Stats
    hit_count: int = 0
    last_accessed: datetime = Field(default_factory=utc_now)

    def is_expired(self) -> bool:
        if self.expires_at is None:
            return False
        return utc_now() > self.expires_at

    def touch(self) -> None:
        self.hit_count += 1
        self.last_accessed = utc_now()


class CacheStats(DJBaseModel):
    """Aggregate cache statistics."""

    total_entries: int = 0
    hits: int = 0
    misses: int = 0
    hit_rate: float = 0.0
    providers: dict[str, int] = Field(default_factory=dict)
    last_cleanup: datetime | None = None
