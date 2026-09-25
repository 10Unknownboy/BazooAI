from __future__ import annotations
import logging
import json
from datetime import datetime, timezone
from typing import Optional, Any
from app.database.repositories import CacheRepository
from app.event.event_bus import get_event_bus, BusEvent

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
        cached_item = self.repository.get(key)
        
        if provider not in self.stats["providers"]:
            self.stats["providers"][provider] = {"hits": 0, "misses": 0}
            
        if cached_item:
            if cached_item.expires_at and cached_item.expires_at < datetime.now(timezone.utc):
                self.repository.delete(key)
                self._record_miss(provider, key)
                return None
                
            self._record_hit(provider, key)
            try:
                return json.loads(cached_item.value)
            except json.JSONDecodeError:
                return cached_item.value
                
        self._record_miss(provider, key)
        return None

    def save(self, provider: str, resource_type: str, resource_id: str, data: Any, ttl_seconds: int = 3600):
        key = self._get_key(provider, resource_type, resource_id)
        value = json.dumps(data) if not isinstance(data, str) else data
        # Note: CacheRepository implementation manages CacheItem model mapping
        self.repository.set(key, value, ttl_seconds)
        logger.debug(f"Cache saved for {key}")

    def invalidate(self, provider: str, resource_type: str, resource_id: str):
        key = self._get_key(provider, resource_type, resource_id)
        self.repository.delete(key)

    def _record_hit(self, provider: str, key: str):
        self.stats["cache_hit"] += 1
        self.stats["providers"][provider]["hits"] += 1
        self.event_bus.publish(BusEvent(event_type="CACHE_HIT", data={"key": key, "provider": provider}))
        logger.debug(f"Cache hit: {key}")

    def _record_miss(self, provider: str, key: str):
        self.stats["cache_miss"] += 1
        self.stats["providers"][provider]["misses"] += 1
        self.event_bus.publish(BusEvent(event_type="CACHE_MISS", data={"key": key, "provider": provider}))
        logger.debug(f"Cache miss: {key}")
