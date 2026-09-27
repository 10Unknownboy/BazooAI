from __future__ import annotations

from pathlib import Path

from app.__main__ import event_config_from_file
from app.agents.learning_agent import LearningAgent
from app.config.settings import PROJECT_ROOT, AppSettings
from app.event.event_bus import BusEvent, get_event_bus
from app.models.feedback import RewardRecord, SongFeedback
from app.providers.local_file_provider import LocalFileProvider


def test_learning_persists_context_and_does_not_republish_feedback(monkeypatch, sample_event_state):
    saved_records: list[RewardRecord] = []
    preference_updates: list[dict] = []

    class RewardRepository:
        def save(self, record):
            saved_records.append(record)

    class PreferenceRepository:
        def update_preference(self, **kwargs):
            preference_updates.append(kwargs)

    monkeypatch.setattr(
        "app.agents.learning_agent.get_repository",
        lambda name: RewardRepository() if name == "reward" else PreferenceRepository(),
    )
    bus = get_event_bus()
    bus.clear_history()

    feedback = SongFeedback(
        event_id=sample_event_state.event_id,
        song_id="SNG_test001",
        overall_rating=9,
        transition_rating=4,
        decision_epoch=7,
    )
    LearningAgent().process_feedback(feedback, sample_event_state)

    assert len(saved_records) == 1
    record = saved_records[0]
    assert record.reward > 0
    assert record.action_song_id == feedback.song_id
    assert record.state_event_type == sample_event_state.event_config.event_type.value
    assert record.raw_feedback["transition_rating"] == 4
    assert len(preference_updates) == 1
    assert bus.get_history(BusEvent.FEEDBACK_RECEIVED) == []
    assert len(bus.get_history(BusEvent.AGENT_DECISION)) == 1


def test_local_provider_refresh_indexes_new_tracks(tmp_path):
    provider = LocalFileProvider(directory=str(tmp_path))
    assert provider.list_songs() == []

    (tmp_path / "new-track.mp3").write_bytes(b"")
    provider.refresh()

    songs = provider.list_songs()
    assert len(songs) == 1
    assert songs[0]["title"] == "new-track"
    assert provider.get_song(songs[0]["id"]) is not None


def test_example_event_yaml_maps_to_runtime_configuration():
    config = event_config_from_file(
        Path(__file__).resolve().parents[1] / "config" / "event_example.yaml"
    )

    assert config.name == "College Freshers Party"
    assert config.event_type.value == "college_party"
    assert config.min_age == 17
    assert config.starting_vibe.value == "chill"
    assert config.target_vibe.value == "party"
    assert len(config.energy_curve) == 8


def test_local_music_dir_from_env_resolves_relative_to_project_root(monkeypatch):
    monkeypatch.setenv("LOCAL_MUSIC_DIR", ".\\test-music")

    settings = AppSettings.from_env()

    assert settings.local_music_dir == (PROJECT_ROOT / "test-music").resolve()


def test_blank_local_music_dir_uses_project_music_folder(monkeypatch):
    monkeypatch.setenv("LOCAL_MUSIC_DIR", "  ")

    settings = AppSettings.from_env()

    assert settings.local_music_dir == (PROJECT_ROOT / "music").resolve()


def test_local_music_dir_from_env_preserves_absolute_path(monkeypatch, tmp_path):
    monkeypatch.setenv("LOCAL_MUSIC_DIR", str(tmp_path))

    settings = AppSettings.from_env()

    assert settings.local_music_dir == tmp_path.resolve()
    (tmp_path / "env-track.mp3").write_bytes(b"")
    provider = LocalFileProvider(directory=str(settings.local_music_dir))

    assert len(provider.list_songs()) == 1
    assert Path(provider.list_songs()[0]["path"]) == tmp_path / "env-track.mp3"
