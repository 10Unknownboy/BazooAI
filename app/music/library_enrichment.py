from __future__ import annotations

import asyncio
import hashlib
import logging

from app.agents.lyrics_agent import LyricsAgent
from app.caching.api_cache import APICache
from app.database.repositories import (
    CacheRepository,
    LyricsFeaturesRepository,
    SongRepository,
    get_repository,
)
from app.models.base import AnalysisStatus
from app.models.song import LyricsFeatures as StoredLyricsFeatures
from app.models.song import Song
from app.music.lrclib_adapter import LRCLibAdapter
from app.music.musicbrainz_adapter import MusicBrainzAdapter

logger = logging.getLogger(__name__)


class LibraryEnrichmentService:
    """Enrich local songs with cached MusicBrainz metadata and LRCLIB lyrics."""

    def __init__(
        self,
        songs: SongRepository | None = None,
        cache: CacheRepository | None = None,
        lyrics_repository: LyricsFeaturesRepository | None = None,
        musicbrainz: MusicBrainzAdapter | None = None,
        lrclib: LRCLibAdapter | None = None,
        lyrics_agent: LyricsAgent | None = None,
    ):
        self.songs = songs or get_repository("song")
        self.cache = cache or get_repository("cache")
        self.api_cache = APICache(self.cache)
        self.musicbrainz = musicbrainz or MusicBrainzAdapter()
        self.lrclib = lrclib or LRCLibAdapter()
        self.lyrics_agent = lyrics_agent or LyricsAgent()
        self.lyrics_repository = lyrics_repository or get_repository("lyrics_features")
        self._task_scoped_repositories = (
            songs is None and cache is None and lyrics_repository is None
        )
        self.progress = {
            "checked": 0,
            "total": 0,
            "metadata_updated": 0,
            "lyrics_found": 0,
            "errors": 0,
        }

    async def enrich_library(self, concurrency: int = 4) -> dict[str, int]:
        """Fetch missing enrichment in bounded concurrent jobs; MusicBrainz rate limits itself."""
        semaphore = asyncio.Semaphore(max(1, concurrency))
        tracks = self.songs.get_candidates(source_provider="local_file", limit=100_000)
        counts = {"checked": 0, "metadata_updated": 0, "lyrics_found": 0, "errors": 0}
        self.progress = {**counts, "total": len(tracks)}

        async def enrich(song: Song) -> None:
            async with semaphore:
                worker = self
                try:
                    worker = self._new_worker()
                    metadata_updated, lyrics_found = await worker.enrich_song(song)
                    counts["metadata_updated"] += int(metadata_updated)
                    counts["lyrics_found"] += int(lyrics_found)
                except Exception:
                    counts["errors"] += 1
                    logger.exception("Library enrichment failed for song %s", song.song_id)
                finally:
                    worker._close_worker_repositories(self)
                    counts["checked"] += 1
                    self.progress = {**counts, "total": len(tracks)}

        await asyncio.gather(*(enrich(song) for song in tracks))
        return counts

    def _new_worker(self) -> LibraryEnrichmentService:
        if not self._task_scoped_repositories:
            return self
        return LibraryEnrichmentService(
            songs=get_repository("song"),
            cache=get_repository("cache"),
            lyrics_repository=get_repository("lyrics_features"),
            musicbrainz=self.musicbrainz,
            lrclib=self.lrclib,
            lyrics_agent=self.lyrics_agent,
        )

    def _close_worker_repositories(self, parent: LibraryEnrichmentService) -> None:
        if self is parent:
            return
        for repository in (self.songs, self.cache, self.lyrics_repository):
            repository.session.close()

    async def enrich_song(self, song: Song) -> tuple[bool, bool]:
        metadata, lyrics = await asyncio.gather(
            self._get_metadata(song),
            self._get_lyrics(song),
        )
        updated = False
        current_song = song
        if metadata:
            provider_ids = {**song.provider_ids, "musicbrainz": metadata["provider_id"]}
            genres = metadata.get("genres") or song.genres
            date = metadata.get("release_date")
            enriched = song.model_copy(
                update={
                    "album": song.album or next(iter(metadata.get("releases", [])), None),
                    "release_date": song.release_date or date,
                    "release_year": song.release_year or _release_year(date),
                    "genre": song.genre or next(iter(genres or []), None),
                    "genres": genres or [],
                    "provider_ids": provider_ids,
                }
            )
            self.songs.save(enriched)
            current_song = enriched
            updated = True
        if lyrics:
            features = await self._analyze_lyrics(current_song, lyrics)
            language = (
                features.language
                if features.language and features.language.casefold() != "unknown"
                else current_song.language
            )
            self.songs.save(
                current_song.model_copy(
                    update={
                        "lyrics_available": True,
                        "lyrics_analysis_available": True,
                        "lyrics_analysis_status": AnalysisStatus.COMPLETE,
                        "lyrics_features": features,
                        "language": language,
                        "languages": current_song.languages or ([language] if language else []),
                    }
                )
            )
        return updated, bool(lyrics)

    async def _analyze_lyrics(self, song: Song, lyrics: dict) -> StoredLyricsFeatures:
        content_hash = lyrics["content_hash"]
        cached_analysis = self.lyrics_repository.get(song.song_id)
        if (
            cached_analysis
            and cached_analysis.analysis_status == "COMPLETE"
            and cached_analysis.content_hash == content_hash
            and cached_analysis.analysis_version == self.lyrics_agent.ANALYSIS_VERSION
        ):
            return cached_analysis

        text = lyrics.get("plainLyrics") or lyrics.get("syncedLyrics") or ""
        analyzed = await self.lyrics_agent.analyze_lyrics(song.song_id, text)
        model_name = (
            f"lyrics-agent-v{self.lyrics_agent.ANALYSIS_VERSION}:"
            f"{analyzed.analysis_model or 'unknown'}"
        )
        features = StoredLyricsFeatures(
            song_id=song.song_id,
            language=analyzed.language,
            themes=analyzed.themes,
            sentiment=analyzed.sentiment,
            mood=analyzed.mood,
            romance=analyzed.romance,
            sadness=analyzed.sadness,
            celebration=analyzed.celebration,
            aggression=analyzed.aggression,
            sexual_content=analyzed.sexual_content,
            explicitness=analyzed.explicitness,
            violence=analyzed.violence,
            drugs=analyzed.drugs,
            breakup=analyzed.breakup,
            nostalgia=analyzed.nostalgia,
            family_friendly=analyzed.family_friendly,
            event_suitability=analyzed.event_suitability,
            source="lrclib",
            content_hash=content_hash,
            analysis_model=model_name,
            analysis_version=self.lyrics_agent.ANALYSIS_VERSION,
            analysis_status="COMPLETE",
        )
        self.lyrics_repository.save(features)
        cached_lyrics = self.api_cache.get("lrclib", "song_lyrics", song.song_id)
        if cached_lyrics:
            cached_lyrics["analysis_model"] = model_name
            cached_lyrics["analysis_version"] = self.lyrics_agent.ANALYSIS_VERSION
            self.api_cache.save(
                "lrclib",
                "song_lyrics",
                song.song_id,
                cached_lyrics,
                ttl_seconds=30 * 24 * 60 * 60,
                source_url="https://lrclib.net/api/get",
            )
        return features

    async def _get_metadata(self, song: Song) -> dict | None:
        cached = self.api_cache.get("musicbrainz", "song_metadata", song.song_id)
        if cached:
            return cached
        query = (
            f'recording:"{_escape_lucene(song.title)}" AND artist:"{_escape_lucene(song.artist)}"'
        )
        results = await self.musicbrainz.search_song(query, limit=5)
        if not results:
            return None
        selected = max(results, key=lambda result: _metadata_match(song, result))
        if _metadata_match(song, selected) < 0.5:
            return None
        self.api_cache.save(
            "musicbrainz",
            "song_metadata",
            song.song_id,
            selected,
            ttl_seconds=90 * 24 * 60 * 60,
            source_url="https://musicbrainz.org/ws/2/recording",
        )
        return selected

    async def _get_lyrics(self, song: Song) -> dict | None:
        cached = self.api_cache.get("lrclib", "song_lyrics", song.song_id)
        if cached:
            return None if cached.get("not_found") else cached
        lyrics = await self.lrclib.get_lyrics(
            title=song.title,
            artist=song.artist,
            album=song.album,
            duration=song.duration,
        )
        if lyrics is None:
            return None
        if lyrics.get("not_found") or not (lyrics.get("plainLyrics") or lyrics.get("syncedLyrics")):
            self.api_cache.save(
                "lrclib",
                "song_lyrics",
                song.song_id,
                {"not_found": True, "source": "lrclib"},
                ttl_seconds=24 * 60 * 60,
                source_url="https://lrclib.net/api/get",
            )
            return None
        lyrics_text = lyrics.get("plainLyrics") or lyrics.get("syncedLyrics") or ""
        lyrics["content_hash"] = hashlib.sha256(lyrics_text.encode("utf-8")).hexdigest()
        lyrics["source"] = "lrclib"
        lyrics["analysis_model"] = None
        lyrics["analysis_version"] = 1
        self.api_cache.save(
            "lrclib",
            "song_lyrics",
            song.song_id,
            lyrics,
            ttl_seconds=30 * 24 * 60 * 60,
            source_url="https://lrclib.net/api/get",
        )
        return lyrics


def _release_year(value: str | None) -> int | None:
    if value and len(value) >= 4 and value[:4].isdigit():
        return int(value[:4])
    return None


def _metadata_match(song: Song, result: dict) -> float:
    expected_title = _normalize(song.title)
    expected_artist = _normalize(song.artist)
    result_title = _normalize(str(result.get("title", "")))
    result_artist = _normalize(str(result.get("artist", "")))
    title_match = _similarity(expected_title, result_title)
    artist_match = _similarity(expected_artist, result_artist)
    return (title_match * 0.65) + (artist_match * 0.35)


def _normalize(value: str) -> str:
    return " ".join("".join(char.casefold() if char.isalnum() else " " for char in value).split())


def _escape_lucene(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def _similarity(left: str, right: str) -> float:
    if not left or not right:
        return 0.0
    if left == right:
        return 1.0
    left_words, right_words = set(left.split()), set(right.split())
    return len(left_words & right_words) / max(len(left_words), len(right_words))
