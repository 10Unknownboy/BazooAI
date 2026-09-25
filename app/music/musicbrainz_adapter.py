from __future__ import annotations
import logging
import httpx
import asyncio
from typing import Optional
from app.music.metadata_adapter import MusicMetadataProvider
from app.config.settings import get_settings

logger = logging.getLogger(__name__)

class MusicBrainzAdapter(MusicMetadataProvider):
    """MusicBrainz metadata adapter."""
    
    provider_name = "musicbrainz"
    
    def __init__(self):
        settings = get_settings()
        self.user_agent = getattr(settings, "MUSICBRAINZ_USER_AGENT", "BazooAI/1.0.0 ( bazoo@example.com )")
        self.base_url = "https://musicbrainz.org/ws/2"
        self._last_request_time = 0.0
        self._rate_limit_lock = asyncio.Lock()
        
    async def _rate_limit(self):
        """Implement 1 req/sec rate limit."""
        async with self._rate_limit_lock:
            now = asyncio.get_event_loop().time()
            elapsed = now - self._last_request_time
            if elapsed < 1.0:
                await asyncio.sleep(1.0 - elapsed)
            self._last_request_time = asyncio.get_event_loop().time()

    async def _request(self, endpoint: str, params: dict) -> dict | None:
        params["fmt"] = "json"
        headers = {"User-Agent": self.user_agent}
        
        for attempt in range(3):
            await self._rate_limit()
            try:
                async with httpx.AsyncClient() as client:
                    response = await client.get(f"{self.base_url}/{endpoint}", params=params, headers=headers, timeout=10.0)
                    if response.status_code == 503:
                        logger.warning("MusicBrainz rate limit hit, backing off...")
                        await asyncio.sleep(2 ** attempt)
                        continue
                    response.raise_for_status()
                    return response.json()
            except Exception as e:
                logger.error(f"MusicBrainz API error: {e}")
                if attempt == 2:
                    return None
        return None

    async def search_song(self, query: str, limit: int = 10) -> list[dict]:
        data = await self._request("recording", {"query": query, "limit": limit})
        if not data or "recordings" not in data:
            return []
            
        results = []
        for rec in data["recordings"]:
            artist_credits = rec.get("artist-credit", [])
            artist_name = artist_credits[0].get("name", "Unknown") if artist_credits else "Unknown"
            
            results.append({
                "provider_id": rec["id"],
                "title": rec["title"],
                "artist": artist_name,
                "duration": rec.get("length", 0) / 1000.0 if rec.get("length") else 0.0,
            })
        return results

    async def get_metadata(self, provider_id: str) -> dict | None:
        data = await self._request("recording", {"query": f"rid:{provider_id}", "inc": "releases+artists"})
        if not data or "recordings" not in data or not data["recordings"]:
            return None
            
        rec = data["recordings"][0]
        artist_credits = rec.get("artist-credit", [])
        artist_name = artist_credits[0].get("name", "Unknown") if artist_credits else "Unknown"
        
        return {
            "provider_id": rec["id"],
            "title": rec["title"],
            "artist": artist_name,
            "duration": rec.get("length", 0) / 1000.0 if rec.get("length") else 0.0,
            "releases": [rel["title"] for rel in rec.get("releases", [])]
        }

    async def get_audio_features(self, provider_id: str) -> dict | None:
        # MusicBrainz generally does not provide rich audio features directly in this API.
        # This is a stub for potential AcousticBrainz integration if it were still active.
        return None
