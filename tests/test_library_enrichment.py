from __future__ import annotations

import asyncio
import hashlib

import httpx
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.agents.lyrics_agent import LyricsFeatures as AnalyzedLyricsFeatures
from app.database.engine import Base
from app.database.repositories import CacheRepository, LyricsFeaturesRepository, SongRepository
from app.models.song import Song
from app.music.library_enrichment import LibraryEnrichmentService
from app.music.lrclib_adapter import LRCLibAdapter
from app.music.musicbrainz_adapter import MusicBrainzAdapter


class FakeMusicBrainz:
    async def search_song(self, query: str, limit: int = 10) -> list[dict]:
        return [
            {
                "provider_id": "recording-1",
                "title": "Example Song",
                "artist": "Example Artist",
                "releases": ["Example Album"],
                "release_date": "2020-04-03",
                "genres": ["pop"],
            }
        ]


class FakeLRCLib:
    async def get_lyrics(self, **kwargs) -> dict:
        return {"plainLyrics": "Example lyric", "syncedLyrics": None}


class FakeLyricsAgent:
    ANALYSIS_VERSION = 1

    def __init__(self):
        self.calls = 0

    async def analyze_lyrics(self, song_id: str, lyrics_text: str):
        self.calls += 1
        assert lyrics_text == "Example lyric"
        return AnalyzedLyricsFeatures(
            song_id=song_id,
            language="English",
            romance=0.8,
            analysis_model="test-model",
        )


def test_musicbrainz_uses_configured_user_agent_and_returns_tags(monkeypatch):
    monkeypatch.setattr(
        "app.music.musicbrainz_adapter.get_settings",
        lambda: type(
            "Settings",
            (),
            {
                "musicbrainz": type(
                    "MusicBrainz", (), {"user_agent": "BazooTest/1.0", "rate_limit": 0}
                )()
            },
        )(),
    )
    observed = {}

    def response(request: httpx.Request) -> httpx.Response:
        observed["user_agent"] = request.headers["User-Agent"]
        return httpx.Response(
            200,
            json={
                "recordings": [
                    {
                        "id": "recording-1",
                        "title": "Example Song",
                        "artist-credit": [{"name": "Example Artist"}],
                        "length": 180_000,
                        "releases": [{"title": "Example Album", "date": "2020-04-03"}],
                        "tags": [{"name": "pop", "count": 3}],
                    }
                ]
            },
        )

    async def run():
        client = httpx.AsyncClient(transport=httpx.MockTransport(response))
        try:
            results = await MusicBrainzAdapter(client=client).search_song("Example Song")
            return results
        finally:
            await client.aclose()

    results = asyncio.run(run())

    assert observed["user_agent"] == "BazooTest/1.0"
    assert results[0]["provider_id"] == "recording-1"
    assert results[0]["genres"] == ["pop"]
    assert results[0]["release_date"] == "2020-04-03"


def test_lrclib_queries_exact_track_and_handles_not_found():
    observed = {}

    def response(request: httpx.Request) -> httpx.Response:
        observed.update(dict(request.url.params))
        return httpx.Response(404)

    async def run():
        client = httpx.AsyncClient(transport=httpx.MockTransport(response))
        try:
            result = await LRCLibAdapter(client=client).get_lyrics(
                title="Example Song",
                artist="Example Artist",
                album="Example Album",
                duration=180.2,
            )
            return result
        finally:
            await client.aclose()

    assert asyncio.run(run()) == {"not_found": True}
    assert observed == {
        "track_name": "Example Song",
        "artist_name": "Example Artist",
        "album_name": "Example Album",
        "duration": "180",
    }


def test_enrichment_updates_song_and_reuses_cached_metadata_and_lyrics():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    songs = SongRepository(session)
    cache = CacheRepository(session)
    lyrics_agent = FakeLyricsAgent()
    song = Song(
        song_id="local-example",
        title="Example Song",
        artist="Example Artist",
        source_provider="local_file",
        file_path="example.mp3",
    )
    songs.save(song)
    service = LibraryEnrichmentService(
        songs=songs,
        cache=cache,
        lyrics_repository=LyricsFeaturesRepository(session),
        musicbrainz=FakeMusicBrainz(),
        lrclib=FakeLRCLib(),
        lyrics_agent=lyrics_agent,
    )

    metadata_updated, lyrics_found = asyncio.run(service.enrich_song(song))
    enriched = songs.get(song.song_id)
    lyrics_cache = cache.get("lrclib", "song_lyrics", song.song_id)

    assert metadata_updated and lyrics_found
    assert enriched.album == "Example Album"
    assert enriched.release_year == 2020
    assert enriched.provider_ids["musicbrainz"] == "recording-1"
    assert enriched.lyrics_available
    assert enriched.lyrics_analysis_available
    assert enriched.lyrics_features.romance == 0.8
    assert lyrics_agent.calls == 1
    assert lyrics_cache.data["source"] == "lrclib"
    assert lyrics_cache.data["analysis_model"] == "lyrics-agent-v1:test-model"
    assert lyrics_cache.data["analysis_version"] == 1
    assert lyrics_cache.data["content_hash"] == hashlib.sha256(b"Example lyric").hexdigest()

    repeat_agent = FakeLyricsAgent()
    repeated = LibraryEnrichmentService(
        songs=songs,
        cache=cache,
        lyrics_repository=LyricsFeaturesRepository(session),
        musicbrainz=FakeMusicBrainz(),
        lrclib=FakeLRCLib(),
        lyrics_agent=repeat_agent,
    )
    asyncio.run(repeated.enrich_song(song))
    assert repeat_agent.calls == 0
    session.close()
