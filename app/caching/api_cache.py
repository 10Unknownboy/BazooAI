from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from app.database.repositories import CacheRepository
from app.event.event_bus import BusEvent, get_event_bus
from app.models.base import utc_now
from app.models.cache import CacheEntry

logger = logging.getLogger(__name__)


class APICache:
    """Universal API cache layer (spec §42)."""

    def __init__(self, repository: CacheRepository):
        self.repository = repository
        self.stats = {"cache_hit": 0, "cache_miss": 0, "providers": {}}
        self.event_bus = get_event_bus()

    def _get_key(self, provider: str, resource_type: str, resource_id: str) -> str:
        return f"{provider}:{resource_type}:{resource_id}"

    def get(self, provider: str, resource_type: str, resource_id: str) -> Any | None:
        key = self._get_key(provider, resource_type, resource_id)
        cached_item = self.repository.get(provider, resource_type, resource_id)

        if provider not in self.stats["providers"]:
            self.stats["providers"][provider] = {"hits": 0, "misses": 0}

        if cached_item:
            self._record_hit(provider, key)
            return cached_item.data

        self._record_miss(provider, key)
        return None

    def save(
        self,
        provider: str,
        resource_type: str,
        resource_id: str,
        data: Any,
        ttl_seconds: int = 3600,
        source_url: str | None = None,
        status_code: int | None = None,
    ) -> None:
        key = self._get_key(provider, resource_type, resource_id)
        if not isinstance(data, dict):
            data = {"value": data}
        self.repository.save(
            CacheEntry(
                provider=provider,
                resource_type=resource_type,
                resource_id=resource_id,
                data=data,
                ttl_seconds=ttl_seconds,
                expires_at=utc_now() + timedelta(seconds=ttl_seconds),
                source_url=source_url,
                status_code=status_code,
            )
        )
        logger.debug(f"Cache saved for {key}")

    def invalidate(self, provider: str, resource_type: str, resource_id: str) -> bool:
        key = self._get_key(provider, resource_type, resource_id)
        deleted = self.repository.delete(provider, resource_type, resource_id)
        logger.debug("Cache invalidated for %s (deleted=%s)", key, deleted)
        return deleted

    def _record_hit(self, provider: str, key: str):
        self.stats["cache_hit"] += 1
        self.stats["providers"][provider]["hits"] += 1
        self.event_bus.publish(
            BusEvent.CACHE_HIT,
            source="api_cache",
            data={"key": key, "provider": provider},
        )
        logger.debug(f"Cache hit: {key}")

    def _record_miss(self, provider: str, key: str):
        self.stats["cache_miss"] += 1
        self.stats["providers"][provider]["misses"] += 1
        self.event_bus.publish(
            BusEvent.CACHE_MISS,
            source="api_cache",
            data={"key": key, "provider": provider},
        )
        logger.debug(f"Cache miss: {key}")
