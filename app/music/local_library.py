from __future__ import annotations

import logging
import os

from app.audio.analyzer import AudioAnalyzer
from app.audio.feature_extractor import FeatureExtractor
from app.database.engine import init_database
from app.database.repositories import get_repository
from app.models.song import Song
from app.providers.local_file_provider import LocalFileProvider

logger = logging.getLogger(__name__)


def sync_local_library(provider: LocalFileProvider) -> int:
    """Upsert indexed local tracks into the primary SQLite song catalog."""
    init_database()
    tracks = provider.list_songs()
    repository = get_repository("song")
    audio_repository = get_repository("audio_features")
    features_by_song = audio_repository.get_by_song_ids([track["id"] for track in tracks])
    features_by_path = audio_repository.get_for_file_paths(
        [track["path"] for track in tracks]
    )
    extractor = FeatureExtractor()
    migrated_analyses = 0
    synced = 0
    for track in tracks:
        path = track["path"]
        audio_features = features_by_song.get(track["id"])
        current_file_hash = ""
        path_key = os.path.normcase(os.path.abspath(path))
        legacy_features = features_by_path.get(path_key, [])
        migrate_analysis = False
        if audio_features or legacy_features:
            try:
                current_file_hash = extractor.compute_file_hash(path)
            except OSError:
                logger.warning(
                    "Could not verify cached analysis for %s; it will not be reused",
                    path,
                    exc_info=True,
                )
            if (
                audio_features
                and (
                    audio_features.file_hash != current_file_hash
                    or audio_features.analyzer_version != AudioAnalyzer.ANALYZER_VERSION
                    or audio_features.analysis_status != "COMPLETE"
                )
            ):
                audio_features = None
            if not audio_features:
                audio_features = next(
                    (
                        feature
                        for feature in legacy_features
                        if feature.file_hash == current_file_hash
                        and feature.analyzer_version == AudioAnalyzer.ANALYZER_VERSION
                        and feature.analysis_status == "COMPLETE"
                    ),
                    None,
                )
                if audio_features:
                    audio_features = audio_features.model_copy(
                        update={"song_id": track["id"]}
                    )
                    migrate_analysis = True

        existing = repository.get(track["id"])
        feature_fields = {"file_hash": current_file_hash} if current_file_hash else {}
        if (features_by_song.get(track["id"]) or legacy_features) and not audio_features:
            feature_fields["audio_analysis_status"] = "PENDING"
        if audio_features:
            feature_fields = {
                "file_hash": current_file_hash or audio_features.file_hash,
                "audio_analysis_status": audio_features.analysis_status,
                "bpm": (
                    existing.bpm
                    if existing and existing.bpm is not None
                    else audio_features.bpm
                ),
                "key": existing.key if existing and existing.key else audio_features.key,
                "energy": (
                    existing.energy
                    if existing and existing.energy is not None
                    else audio_features.energy
                ),
                "danceability": (
                    existing.danceability
                    if existing and existing.danceability is not None
                    else audio_features.danceability
                ),
                "valence": (
                    existing.valence
                    if existing and existing.valence is not None
                    else audio_features.valence
                ),
            }
        if existing:
            song = existing.model_copy(
                update={
                    "title": track["title"],
                    "artist": (
                        track["artist"]
                        if track["artist"] != "Unknown Artist"
                        else existing.artist
                    ),
                    "artists": (
                        [track["artist"]]
                        if track["artist"] != "Unknown Artist"
                        else existing.artists
                    ),
                    "duration": track["duration"],
                    "source_provider": "local_file",
                    "source_provider_id": track["id"],
                    "provider_ids": {
                        **existing.provider_ids,
                        "local_file": track["id"],
                    },
                    "file_path": path,
                    **feature_fields,
                }
            )
        else:
            song = Song(
                song_id=track["id"],
                title=track["title"],
                artist=track["artist"],
                artists=[track["artist"]] if track["artist"] != "Unknown Artist" else [],
                duration=track["duration"],
                source_provider="local_file",
                source_provider_id=track["id"],
                provider_ids={"local_file": track["id"]},
                file_path=path,
                **feature_fields,
            )
        repository.save(song)
        if migrate_analysis:
            audio_repository.save(audio_features)
            features_by_song[track["id"]] = audio_features
            migrated_analyses += 1
        synced += 1
    if migrated_analyses:
        logger.info(
            "Reused %d verified audio analyses for stable local track IDs",
            migrated_analyses,
        )
    return synced
