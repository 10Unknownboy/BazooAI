from __future__ import annotations

from app.models.song import AudioFeatures, Song
from app.ranking import candidate_generator


def test_song_repository_filters_local_songs_by_duration_and_title(db_session, tmp_path):
    from app.database.repositories import SongRepository

    short_path = tmp_path / "affirmative.mp3"
    sound_path = tmp_path / "gle-cs-radio-ok-lets-go.mp3"
    music_path = tmp_path / "concert-song.mp3"
    for path in (short_path, sound_path, music_path):
        path.write_bytes(b"audio")

    repository = SongRepository(db_session)
    for song in (
        Song(
            song_id="short-sfx",
            title="All CS radio commands",
            artist="Unknown Artist",
            duration=2.8,
            source_provider="local_file",
            file_path=str(short_path),
        ),
        Song(
            song_id="long-sfx",
            title="lesgoo",
            artist="Unknown Artist",
            duration=90,
            source_provider="local_file",
            file_path=str(sound_path),
        ),
        Song(
            song_id="valid-song",
            title="Live at the Concert",
            artist="Test Artist",
            duration=210,
            source_provider="local_file",
            file_path=str(music_path),
        ),
        Song(
            song_id="unplayable-provider",
            title="Another Song",
            artist="Test Artist",
            duration=210,
            source_provider="spotify",
            file_path=str(music_path),
        ),
    ):
        repository.save(song)

    results = repository.get_candidates(
        source_provider="local_file",
        min_duration=30,
        excluded_title_terms=["sound effect", "radio commands", "cs-radio"],
    )

    assert [song.song_id for song in results] == ["valid-song"]


def test_song_repository_hydrates_cached_audio_features(db_session, tmp_path):
    from app.database.repositories import AudioFeaturesRepository, SongRepository

    music_path = tmp_path / "analyzed-song.mp3"
    music_path.write_bytes(b"audio")
    songs = SongRepository(db_session)
    songs.save(
        Song(
            song_id="analyzed-local-song",
            title="Analyzed Song",
            artist="Test Artist",
            duration=180,
            source_provider="local_file",
            file_path=str(music_path),
        )
    )
    AudioFeaturesRepository(db_session).save(
        AudioFeatures(
            song_id="analyzed-local-song",
            bpm=124,
            energy=0.82,
            danceability=0.9,
            valence=0.76,
            analyzer_version="1.0.0",
            file_hash="verified-file-hash",
            analysis_status="COMPLETE",
        )
    )

    [song] = songs.get_candidates(source_provider="local_file")

    assert song.audio_features is not None
    assert song.audio_features.bpm == 124
    assert song.effective_energy() == 0.82
    assert song.effective_danceability() == 0.9
    assert song.effective_valence() == 0.76
    assert song.has_audio_analysis()


def test_song_repository_ignores_cached_features_for_different_file_hash(db_session, tmp_path):
    from app.database.repositories import AudioFeaturesRepository, SongRepository

    music_path = tmp_path / "replaced-song.mp3"
    music_path.write_bytes(b"new file")
    songs = SongRepository(db_session)
    songs.save(
        Song(
            song_id="replaced-local-song",
            title="Replaced Song",
            artist="Test Artist",
            duration=180,
            energy=0.7,
            file_hash="new-content-hash",
            source_provider="local_file",
            file_path=str(music_path),
        )
    )
    AudioFeaturesRepository(db_session).save(
        AudioFeatures(
            song_id="replaced-local-song",
            energy=0.1,
            file_hash="old-content-hash",
            analyzer_version="1.0.0",
            analysis_status="COMPLETE",
        )
    )

    song = songs.get("replaced-local-song")

    assert song.audio_features is None
    assert not song.has_audio_analysis()
    assert song.effective_energy() == 0.7


def test_unavailable_audio_analysis_falls_back_to_song_metadata():
    song = Song(
        song_id="metadata-fallback",
        title="Metadata Track",
        artist="Test Artist",
        bpm=118,
        energy=0.7,
        danceability=0.65,
        valence=0.8,
        audio_features=AudioFeatures(
            song_id="metadata-fallback",
            bpm=0,
            energy=0,
            danceability=0,
            valence=0,
            analysis_status="NOT_AVAILABLE",
        ),
    )

    assert song.effective_bpm() == 118
    assert song.effective_energy() == 0.7
    assert song.effective_danceability() == 0.65
    assert song.effective_valence() == 0.8


def test_candidate_generator_deduplicates_paths_and_skips_missing_files(
    monkeypatch, tmp_path, sample_event_state
):
    music_path = tmp_path / "track.mp3"
    music_path.write_bytes(b"audio")
    missing_path = tmp_path / "missing.mp3"
    songs = [
        Song(
            song_id="first-copy",
            title="Track",
            artist="Artist",
            duration=180,
            popularity=0.5,
            source_provider="local_file",
            file_path=str(music_path),
        ),
        Song(
            song_id="duplicate-copy",
            title="Track",
            artist="Artist",
            duration=180,
            popularity=0.5,
            source_provider="local_file",
            file_path=str(music_path),
        ),
        Song(
            song_id="missing-track",
            title="Missing",
            artist="Artist",
            duration=180,
            source_provider="local_file",
            file_path=str(missing_path),
        ),
    ]

    class FakeRepository:
        def get_candidates(self, **kwargs):
            assert kwargs["source_provider"] == "local_file"
            assert kwargs["min_duration"] == 30
            assert kwargs["excluded_title_terms"]
            return songs

    monkeypatch.setattr(candidate_generator, "get_repository", lambda name: FakeRepository())
    monkeypatch.setattr(
        candidate_generator,
        "load_scoring_config",
        lambda: {
            "candidates": {
                "initial_pool_size": 200,
                "minimum_track_duration": 30,
                "excluded_title_terms": ["sound effect"],
            }
        },
    )
    generator = candidate_generator.CandidateGenerator()

    candidates = generator.get_candidates(sample_event_state, limit=5)

    assert [song.song_id for song in candidates] == ["first-copy"]


def test_candidate_generator_prioritizes_tracks_with_valid_metadata(
    monkeypatch, tmp_path, sample_event_state
):
    analyzed_path = tmp_path / "analyzed.mp3"
    unanalyzed_path = tmp_path / "unanalyzed.mp3"
    analyzed_path.write_bytes(b"audio")
    unanalyzed_path.write_bytes(b"audio")
    songs = [
        Song(
            song_id="plain-track",
            title="Plain",
            artist="Artist",
            duration=180,
            source_provider="local_file",
            file_path=str(unanalyzed_path),
        ),
        Song(
            song_id="analyzed-track",
            title="Analyzed",
            artist="Artist",
            duration=180,
            source_provider="local_file",
            file_path=str(analyzed_path),
            audio_features=AudioFeatures(
                song_id="analyzed-track",
                bpm=124,
                energy=0.8,
                danceability=0.9,
                valence=0.7,
                file_hash="matching-hash",
                analyzer_version="1.0.0",
                analysis_status="COMPLETE",
            ),
        ),
    ]

    class FakeRepository:
        def get_candidates(self, **kwargs):
            return songs

    monkeypatch.setattr(candidate_generator, "get_repository", lambda name: FakeRepository())
    monkeypatch.setattr(
        candidate_generator,
        "load_scoring_config",
        lambda: {
            "candidates": {
                "initial_pool_size": 1,
                "minimum_track_duration": 30,
                "excluded_title_terms": [],
            }
        },
    )
    generator = candidate_generator.CandidateGenerator()

    candidates = generator.get_candidates(sample_event_state, limit=1)

    assert [song.song_id for song in candidates] == ["analyzed-track"]


def test_local_library_sync_preserves_enriched_metadata(monkeypatch, db_session):
    from app.database.repositories import AudioFeaturesRepository, SongRepository
    from app.models.base import AnalysisStatus
    from app.music import local_library

    repository = SongRepository(db_session)
    song = Song(
        song_id="stable-local-id",
        title="Tagged Title",
        artist="Tagged Artist",
        duration=180,
        genre="Pop",
        language="English",
        bpm=120,
        energy=0.8,
        popularity=0.9,
        source_provider="local_file",
        file_path="old-path.mp3",
    )
    song.audio_analysis_status = AnalysisStatus.COMPLETE
    repository.save(song)

    class FakeProvider:
        def list_songs(self):
            return [
                {
                    "id": "stable-local-id",
                    "title": "Filename Title",
                    "artist": "Unknown Artist",
                    "duration": 180,
                    "path": "new-path.mp3",
                }
            ]

    monkeypatch.setattr(local_library, "init_database", lambda: None)
    monkeypatch.setattr(
        local_library,
        "get_repository",
        lambda name: (
            repository
            if name == "song"
            else AudioFeaturesRepository(db_session)
        ),
    )

    assert local_library.sync_local_library(FakeProvider()) == 1
    synced = repository.get("stable-local-id")

    assert synced.title == "Filename Title"
    assert synced.artist == "Tagged Artist"
    assert synced.genre == "Pop"
    assert synced.language == "English"
    assert synced.bpm == 120
    assert synced.energy == 0.8
    assert synced.popularity == 0.9
    assert synced.audio_analysis_status == AnalysisStatus.COMPLETE
    assert synced.file_path == "new-path.mp3"


def test_local_library_sync_reuses_only_hash_verified_legacy_analysis(
    monkeypatch, db_session, tmp_path
):
    from app.audio.analyzer import AudioAnalyzer
    from app.audio.feature_extractor import FeatureExtractor
    from app.database.repositories import AudioFeaturesRepository, SongRepository
    from app.models.song import AudioFeatures
    from app.music import local_library

    audio_path = tmp_path / "legacy-analyzed-track.mp3"
    audio_path.write_bytes(b"current audio bytes")
    file_hash = FeatureExtractor().compute_file_hash(str(audio_path))
    songs = SongRepository(db_session)
    audio_features = AudioFeaturesRepository(db_session)
    songs.save(
        Song(
            song_id="legacy-process-hash-id",
            title="Legacy Track",
            artist="Test Artist",
            duration=180,
            file_path=str(audio_path),
        )
    )
    audio_features.save(
        AudioFeatures(
            song_id="legacy-process-hash-id",
            bpm=126,
            energy=0.8,
            danceability=0.88,
            valence=0.74,
            file_hash=file_hash,
            analyzer_version=AudioAnalyzer.ANALYZER_VERSION,
            analysis_status="COMPLETE",
        )
    )

    class FakeProvider:
        def list_songs(self):
            return [
                {
                    "id": "stable-path-hash-id",
                    "title": "Legacy Track",
                    "artist": "Test Artist",
                    "duration": 180,
                    "path": str(audio_path),
                }
            ]

    repositories = {"song": songs, "audio_features": audio_features}
    monkeypatch.setattr(local_library, "init_database", lambda: None)
    monkeypatch.setattr(local_library, "get_repository", repositories.__getitem__)

    assert local_library.sync_local_library(FakeProvider()) == 1
    migrated = audio_features.get("stable-path-hash-id")
    synced = songs.get("stable-path-hash-id")

    assert migrated is not None
    assert migrated.file_hash == file_hash
    assert migrated.bpm == 126
    assert synced.audio_analysis_status == "COMPLETE"
    assert synced.effective_energy() == 0.8
