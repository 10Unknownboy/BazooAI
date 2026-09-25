from __future__ import annotations
import logging
from typing import Any, Callable, Awaitable
from threading import Lock
from app.caching.api_cache import APICache

logger = logging.getLogger(__name__)

class CacheManager:
    """Central cache coordination."""
    
    def __init__(self, api_cache: APICache):
        self.cache = api_cache
        self._lock = Lock()
        self._rate_limits: dict[str, float] = {}

    async def get_or_fetch_async(self, provider: str, resource_type: str, resource_id: str, fetch_fn: Callable[[], Awaitable[Any]], ttl: int = 3600) -> Any:
        """Cache-through pattern for async fetching."""
        data = self.cache.get(provider, resource_type, resource_id)
        if data is not None:
            return data
            
        try:
            data = await fetch_fn()
            if data is not None:
                self.cache.save(provider, resource_type, resource_id, data, ttl)
            return data
        except Exception as e:
            logger.error(f"Error fetching data to cache for {provider}:{resource_type}:{resource_id}: {e}")
            return None

    def get_or_fetch(self, provider: str, resource_type: str, resource_id: str, fetch_fn: Callable[[], Any], ttl: int = 3600) -> Any:
        """Cache-through pattern for sync fetching."""
        data = self.cache.get(provider, resource_type, resource_id)
        if data is not None:
            return data
            
        try:
            data = fetch_fn()
            if data is not None:
                self.cache.save(provider, resource_type, resource_id, data, ttl)
            return data
        except Exception as e:
            logger.error(f"Error fetching data to cache for {provider}:{resource_type}:{resource_id}: {e}")
            return None

    def cleanup_expired(self):
        """Remove expired entries. Assumes repository handles this or implements a cleanup method."""
        if hasattr(self.cache.repository, "cleanup_expired"):
            self.cache.repository.cleanup_expired()
            
    def get_stats(self) -> dict:
        return self.cache.stats

    def rate_limit_check(self, provider: str) -> bool:
        """Check if a provider is within rate limits."""
        # Simple placeholder for more complex rate limiting logic
        return True
