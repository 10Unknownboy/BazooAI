from __future__ import annotations

from types import SimpleNamespace

from app.event.event_bus import BusEvent, get_event_bus
from app.playback.playback_controller import PlaybackController
from app.providers import local_file_provider
from app.queue.queue_manager import QueueManager


class FakeMusic:
    def __init__(self):
        self.path = None
        self.busy = False
        self.position_ms = 2500
        self.volume_value = None
        self.seek_position = None

    def load(self, path):
        self.path = path

    def play(self):
        self.busy = True

    def pause(self):
        self.busy = False

    def unpause(self):
        self.busy = True

    def stop(self):
        self.busy = False

    def get_busy(self):
        return self.busy

    def get_pos(self):
        return self.position_ms

    def set_pos(self, seconds):
        self.seek_position = seconds

    def set_volume(self, value):
        self.volume_value = value


class FakeMixer:
    def __init__(self):
        self.music = FakeMusic()

    @staticmethod
    def get_init():
        return True


def install_fake_audio(monkeypatch):
    mixer = FakeMixer()
    monkeypatch.setattr(
        local_file_provider,
        "pygame",
        SimpleNamespace(mixer=mixer, error=RuntimeError),
    )
    monkeypatch.setattr(local_file_provider, "PYGAME_AVAILABLE", True)
    return mixer


def test_provider_refuses_to_claim_playback_without_audio_output(monkeypatch, tmp_path):
    track = tmp_path / "silent.mp3"
    track.write_bytes(b"")
    monkeypatch.setattr(local_file_provider, "PYGAME_AVAILABLE", False)

    provider = local_file_provider.LocalFileProvider(str(tmp_path))
    song_id = provider.list_songs()[0]["id"]

    assert not provider.audio_available
    assert not provider.play(song_id)
    assert not provider.is_playing()
    assert provider.current_song() is None


def test_missing_queue_track_reports_actionable_playback_error(tmp_path):
    queue = QueueManager()
    queue.add_song(
        "obsolete-local-id",
        score=55.4,
        song_title="All CS radio commands",
        song_artist="Unknown Artist",
    )
    provider = local_file_provider.LocalFileProvider(str(tmp_path))
    controller = PlaybackController(queue, provider)
    try:
        assert not controller.play()
        assert "not indexed" in controller.last_error
        assert "obsolete-local-id" in controller.last_error
    finally:
        controller.close()


def test_streamlit_controls_drive_real_provider_operations(monkeypatch, tmp_path):
    mixer = install_fake_audio(monkeypatch)
    for name in ("first.mp3", "second.mp3"):
        (tmp_path / name).write_bytes(b"")
    provider = local_file_provider.LocalFileProvider(str(tmp_path))
    tracks = provider.list_songs()

    queue = QueueManager()
    for position, track in enumerate(tracks):
        queue.add_song(
            track["id"],
            score=80 - position,
            song_title=track["title"],
            song_artist=track["artist"],
        )
    bus = get_event_bus()

    def advance_on_end(message):
        queue.advance()

    bus.subscribe(BusEvent.SONG_ENDED, advance_on_end)
    controller = PlaybackController(queue, provider)
    try:
        assert controller.play()
        assert provider.is_playing()
        assert mixer.music.path == tracks[0]["path"]
        assert controller.pause()
        assert controller.is_paused
        assert not provider.is_playing()
        assert controller.resume()
        assert provider.is_playing()
        assert controller.volume(35)
        assert mixer.music.volume_value == 0.35
        assert controller.seek(12.0)
        assert mixer.music.seek_position == 12.0
        assert controller.skip()
        assert mixer.music.path == tracks[1]["path"]
        assert controller.stop()
        assert not provider.is_playing()
        assert provider.current_song() is None
    finally:
        bus.unsubscribe(BusEvent.SONG_ENDED, advance_on_end)
        controller.close()
