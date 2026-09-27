from __future__ import annotations

from unittest.mock import Mock

from app.console.command_handler import CommandHandler
from app.playback.playback_controller import PlaybackController
from app.providers.mock_provider import MockMusicProvider
from app.queue.queue_manager import QueueManager


def test_console_playback_commands_call_the_provider_controller():
    playback = Mock()
    playback.resume.return_value = True
    playback.pause.return_value = True
    handler = CommandHandler(playback=playback, orchestrator=Mock())

    play = handler.dispatch("play", [])
    pause = handler.dispatch("pause", [])

    assert play.success
    assert pause.success
    playback.resume.assert_called_once_with()
    playback.pause.assert_called_once_with()


def test_console_reports_playback_failure_instead_of_claiming_success():
    playback = Mock()
    playback.skip.return_value = False
    playback.last_error = "audio device unavailable"
    handler = CommandHandler(playback=playback, orchestrator=Mock())

    result = handler.dispatch("skip", [])

    assert not result.success
    assert "audio device unavailable" in result.message


def test_console_volume_and_seek_are_applied_to_playback_provider():
    playback = Mock()
    playback.volume.return_value = True
    playback.seek.return_value = True
    handler = CommandHandler(playback=playback, orchestrator=Mock())

    assert handler.dispatch("volume", ["73"]).success
    assert handler.dispatch("seek", ["32"]).success
    playback.volume.assert_called_once_with(73)
    playback.seek.assert_called_once_with(32)


def test_vibe_command_rejects_unknown_preset():
    handler = CommandHandler(playback=Mock(), orchestrator=Mock())

    result = handler.dispatch("vibe", ["not-a-vibe"])

    assert not result.success
    assert "Unknown vibe" in result.message


def test_dry_run_provider_resumes_paused_queue_item_without_audio_device():
    song = {"id": "local-test", "title": "Local Test", "artist": "Test", "duration": 210.0}
    provider = MockMusicProvider(simulation_speed=0.001, songs=[song])
    queue = QueueManager()
    queue.add_song("local-test", 70.0, song_title="Local Test", song_artist="Test")
    playback = PlaybackController(queue, provider)
    try:
        assert playback.play()
        assert playback.pause()
        assert playback.is_paused
        assert playback.resume()
        assert playback.is_playing
        assert provider.current_song()["id"] == "local-test"
    finally:
        playback.close()
