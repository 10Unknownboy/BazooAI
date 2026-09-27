from __future__ import annotations

import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)


class LRCLibAdapter:
    """Fetch plain or synchronized lyrics from LRCLIB."""

    provider_name = "lrclib"
    base_url = "https://lrclib.net/api"

    def __init__(self, client: httpx.AsyncClient | None = None):
        self._client = client

    async def get_lyrics(
        self,
        *,
        title: str,
        artist: str,
        album: str | None = None,
        duration: float | None = None,
    ) -> dict[str, Any] | None:
        params: dict[str, Any] = {"track_name": title, "artist_name": artist}
        if album:
            params["album_name"] = album
        if duration and duration > 0:
            params["duration"] = round(duration)
        try:
            if self._client:
                response = await self._client.get(
                    f"{self.base_url}/get", params=params, timeout=10.0
                )
            else:
                async with httpx.AsyncClient() as client:
                    response = await client.get(f"{self.base_url}/get", params=params, timeout=10.0)
            if response.status_code == 404:
                return {"not_found": True}
            response.raise_for_status()
            payload = response.json()
            return payload if isinstance(payload, dict) else None
        except httpx.HTTPError, ValueError:
            logger.warning("LRCLIB lookup failed for %r by %r", title, artist, exc_info=True)
            return None
