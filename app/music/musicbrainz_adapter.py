from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx

from app.config.settings import get_settings
from app.music.metadata_adapter import MusicMetadataProvider

logger = logging.getLogger(__name__)


class MusicBrainzAdapter(MusicMetadataProvider):
    """MusicBrainz metadata adapter."""

    provider_name = "musicbrainz"

    def __init__(self, client: httpx.AsyncClient | None = None):
        settings = get_settings()
        self.user_agent = settings.musicbrainz.user_agent
        self.rate_limit = max(0.0, settings.musicbrainz.rate_limit)
        self.base_url = "https://musicbrainz.org/ws/2"
        self._last_request_time = 0.0
        self._rate_limit_lock = asyncio.Lock()
        self._client = client

    async def _rate_limit(self):
        """Implement 1 req/sec rate limit."""
        async with self._rate_limit_lock:
            now = asyncio.get_event_loop().time()
            elapsed = now - self._last_request_time
            if elapsed < self.rate_limit:
                await asyncio.sleep(self.rate_limit - elapsed)
            self._last_request_time = asyncio.get_event_loop().time()

    async def _request(self, endpoint: str, params: dict[str, Any]) -> dict | None:
        request_params = {**params, "fmt": "json"}
        headers = {"User-Agent": self.user_agent}
        for attempt in range(3):
            await self._rate_limit()
            try:
                if self._client:
                    response = await self._client.get(
                        f"{self.base_url}/{endpoint}",
                        params=request_params,
                        headers=headers,
                        timeout=10.0,
                    )
                else:
                    async with httpx.AsyncClient() as client:
                        response = await client.get(
                            f"{self.base_url}/{endpoint}",
                            params=request_params,
                            headers=headers,
                            timeout=10.0,
                        )
                if response.status_code == 503:
                    logger.warning("MusicBrainz rate limit hit, backing off...")
                    await asyncio.sleep(2**attempt)
                    continue
                response.raise_for_status()
                return response.json()
            except httpx.HTTPError:
                logger.warning("MusicBrainz request failed", exc_info=True)
        return None

    async def search_song(self, query: str, limit: int = 10) -> list[dict]:
        data = await self._request(
            "recording",
            {"query": query, "limit": limit, "inc": "artist-credits+releases+tags"},
        )
        if not data or "recordings" not in data:
            return []

        results = []
        for rec in data["recordings"]:
            artist_credits = rec.get("artist-credit", [])
            artist_name = artist_credits[0].get("name", "Unknown") if artist_credits else "Unknown"

            tags = rec.get("tags", [])
            releases = rec.get("releases", [])
            results.append(
                {
                    "provider_id": rec["id"],
                    "title": rec["title"],
                    "artist": artist_name,
                    "duration": rec.get("length", 0) / 1000.0 if rec.get("length") else 0.0,
                    "releases": [release["title"] for release in releases if release.get("title")],
                    "release_date": next(
                        (release.get("date") for release in releases if release.get("date")),
                        None,
                    ),
                    "genres": [
                        tag["name"]
                        for tag in tags
                        if tag.get("name") and float(tag.get("count", 0)) > 0
                    ],
                }
            )
        return results

    async def get_metadata(self, provider_id: str) -> dict | None:
        data = await self._request(
            "recording", {"query": f"rid:{provider_id}", "inc": "releases+artists"}
        )
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
            "releases": [rel["title"] for rel in rec.get("releases", [])],
            "release_date": next(
                (release.get("date") for release in rec.get("releases", []) if release.get("date")),
                None,
            ),
            "genres": [
                tag["name"]
                for tag in rec.get("tags", [])
                if tag.get("name") and float(tag.get("count", 0)) > 0
            ],
        }

    async def get_audio_features(self, provider_id: str) -> dict | None:
        # MusicBrainz generally does not provide rich audio features directly in this API.
        # This is a stub for potential AcousticBrainz integration if it were still active.
        return None
