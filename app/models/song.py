"""Song, artist, album, and audio/lyrics feature models."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import Field

from app.models.base import AnalysisStatus, DJBaseModel, generate_id, utc_now


class Artist(DJBaseModel):
    artist_id: str = Field(default_factory=lambda: generate_id("ART"))
    name: str
    aliases: list[str] = Field(default_factory=list)
    genres: list[str] = Field(default_factory=list)
    region: str | None = None
    popularity: float = Field(default=0.5, ge=0.0, le=1.0)
    first_seen: datetime = Field(default_factory=utc_now)
    last_updated: datetime = Field(default_factory=utc_now)


class Album(DJBaseModel):
    album_id: str = Field(default_factory=lambda: generate_id("ALB"))
    title: str
    artist_id: str | None = None
    artist_name: str | None = None
    release_year: int | None = None
    release_date: str | None = None
    genre: str | None = None
    cover_art_url: str | None = None
    first_seen: datetime = Field(default_factory=utc_now)
    last_updated: datetime = Field(default_factory=utc_now)


class AudioFeatures(DJBaseModel):
    """Audio analysis results for a song — stored permanently after analysis."""

    song_id: str
    bpm: float | None = None
    tempo: float | None = None
    key: str | None = None
    loudness: float | None = None
    energy: float | None = None
    danceability: float | None = None
    valence: float | None = None
    acousticness: float | None = None
    instrumentalness: float | None = None
    speechiness: float | None = None
    spectral_centroid: float | None = None
    spectral_bandwidth: float | None = None
    spectral_rolloff: float | None = None
    zero_crossing_rate: float | None = None
    mfcc_mean: list[float] | None = None
    chroma_mean: list[float] | None = None
    onset_rate: float | None = None
    duration: float | None = None

    # Analysis provenance
    file_hash: str | None = None
    analyzer_version: str | None = None
    analysis_version: int = Field(default=1)
    analysis_status: AnalysisStatus = AnalysisStatus.PENDING
    analyzed_at: datetime | None = None

    # Embedding
    audio_embedding: list[float] | None = None


class LyricsFeatures(DJBaseModel):
    """Lyrics analysis results — classification/metadata, NOT full lyrics text."""

    song_id: str
    language: str | None = None
    themes: list[str] = Field(default_factory=list)
    sentiment: float | None = None  # -1.0 to 1.0
    mood: str | None = None
    romance: float = Field(default=0.0, ge=0.0, le=1.0)
    sadness: float = Field(default=0.0, ge=0.0, le=1.0)
    celebration: float = Field(default=0.0, ge=0.0, le=1.0)
    aggression: float = Field(default=0.0, ge=0.0, le=1.0)
    sexual_content: float = Field(default=0.0, ge=0.0, le=1.0)
    explicitness: float = Field(default=0.0, ge=0.0, le=1.0)
    violence: float = Field(default=0.0, ge=0.0, le=1.0)
    drugs: float = Field(default=0.0, ge=0.0, le=1.0)
    breakup: float = Field(default=0.0, ge=0.0, le=1.0)
    nostalgia: float = Field(default=0.0, ge=0.0, le=1.0)
    family_friendly: bool = True
    event_suitability: dict[str, float] = Field(default_factory=dict)

    # Analysis provenance
    source: str | None = None
    content_hash: str | None = None
    analysis_model: str | None = None
    analysis_version: int = Field(default=1)
    analysis_status: AnalysisStatus = AnalysisStatus.PENDING
    analyzed_at: datetime | None = None

    # Embedding
    lyrics_embedding: list[float] | None = None


class Song(DJBaseModel):
    """Complete song record with metadata from potentially multiple providers."""

    song_id: str = Field(default_factory=lambda: generate_id("SNG"))
    title: str
    artist: str
    artists: list[str] = Field(default_factory=list)
    album: str | None = None
    album_id: str | None = None
    release_year: int | None = None
    release_date: str | None = None
    duration: float | None = None  # seconds
    language: str | None = None
    languages: list[str] = Field(default_factory=list)
    genre: str | None = None
    subgenre: str | None = None
    genres: list[str] = Field(default_factory=list)
    explicit: bool = False
    popularity: float = Field(default=0.5, ge=0.0, le=1.0)
    is_remix: bool = False
    is_live: bool = False
    is_clean_version: bool = False
    version_type: str | None = None  # original | remix | live | clean | acoustic
    original_song_id: str | None = None  # link to original if this is a variant

    # BPM/key metadata (may come from provider or audio analysis)
    bpm: float | None = None
    key: str | None = None
    energy: float | None = None
    danceability: float | None = None
    valence: float | None = None

    # Lyrics
    lyrics_available: bool = False
    lyrics_analysis_available: bool = False

    # Analysis status
    audio_analysis_status: AnalysisStatus = AnalysisStatus.PENDING
    lyrics_analysis_status: AnalysisStatus = AnalysisStatus.PENDING

    # Provider metadata
    source_provider: str | None = None
    source_provider_id: str | None = None
    provider_ids: dict[str, str] = Field(default_factory=dict)  # provider -> id

    # File info (for local files)
    file_path: str | None = None
    file_hash: str | None = None

    # Timestamps
    first_seen: datetime = Field(default_factory=utc_now)
    last_updated: datetime = Field(default_factory=utc_now)

    # Related analysis objects (not stored in same table)
    audio_features: AudioFeatures | None = None
    lyrics_features: LyricsFeatures | None = None

    def has_audio_analysis(self) -> bool:
        return self.audio_analysis_status == AnalysisStatus.COMPLETE

    def has_lyrics_analysis(self) -> bool:
        return self.lyrics_analysis_status == AnalysisStatus.COMPLETE

    def effective_energy(self) -> float:
        """Best estimate of energy from any available source."""
        if self.audio_features and self.audio_features.energy is not None:
            return self.audio_features.energy
        if self.energy is not None:
            return self.energy
        return 0.5

    def effective_bpm(self) -> float | None:
        if self.audio_features and self.audio_features.bpm is not None:
            return self.audio_features.bpm
        return self.bpm

    def effective_danceability(self) -> float:
        if self.audio_features and self.audio_features.danceability is not None:
            return self.audio_features.danceability
        if self.danceability is not None:
            return self.danceability
        return 0.5

    def effective_valence(self) -> float:
        if self.audio_features and self.audio_features.valence is not None:
            return self.audio_features.valence
        if self.valence is not None:
            return self.valence
        return 0.5
