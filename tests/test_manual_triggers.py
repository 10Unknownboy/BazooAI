from __future__ import annotations

from unittest.mock import Mock

from fastapi.testclient import TestClient

from app.api.guest_api import app as guest_api
from app.api.guest_api import configure_runtime, guest_url
from app.console.command_handler import CommandHandler
from app.event.event_bus import BusEvent, EventBus, RuntimeState
from app.models.request import SongRequest


def test_console_request_command_publishes_orchestrator_request():
    bus = EventBus()
    handler = CommandHandler()
    handler.bus = bus
    received = []
    bus.subscribe(BusEvent.REQUEST_RECEIVED, received.append)

    result = handler.dispatch("request", ["Brown", "Munde"])

    assert result.success
    assert len(received) == 1
    request = SongRequest.model_validate(received[0].data["request"])
    assert request.requested_song_query == "Brown Munde"
    assert request.requester == "console"


def test_guest_api_request_publishes_orchestrator_request():
    bus = EventBus()
    runtime_state = RuntimeState()
    runtime_state.update_event_state(
        {
            "event_id": "EVT_guest_test",
            "is_ended": False,
            "event_config": {"name": "Test Event", "allow_requests": True},
            "current_song_id": None,
        }
    )
    runtime_state.update_queue_state({"items": []})
    configure_runtime(
        playback=Mock(),
        music_provider=Mock(),
        event_bus=bus,
        runtime_state=runtime_state,
    )
    received = []

    def capture(message):
        received.append(message)

    bus.subscribe(BusEvent.REQUEST_RECEIVED, capture)
    try:
        response = TestClient(guest_api).post(
            "/request",
            json={
                "guest_name": "Manual tester",
                "song_title": "Brown Munde",
                "artist": "AP Dhillon",
            },
        )
    finally:
        bus.unsubscribe(BusEvent.REQUEST_RECEIVED, capture)

    assert response.status_code == 202
    request = SongRequest.model_validate(received[0].data["request"])
    assert request.requested_song_query == "Brown Munde AP Dhillon"
    assert request.requester == "Manual tester"


def test_guest_playlist_reads_live_runtime_state():
    bus = EventBus()
    runtime_state = RuntimeState()
    runtime_state.update_event_state(
        {
            "event_id": "EVT_live",
            "is_ended": False,
            "event_config": {"name": "Live Party", "allow_requests": True},
            "current_song_id": "song-1",
            "playback_state": "PLAYING",
        }
    )
    runtime_state.update_queue_state(
        {
            "items": [
                {
                    "song_id": "song-1",
                    "song_title": "Current Track",
                    "song_artist": "Current Artist",
                },
                {
                    "song_id": "song-2",
                    "song_title": "Next Track",
                    "song_artist": "Next Artist",
                },
            ]
        }
    )
    provider = Mock()
    provider.get_song.return_value = {
        "title": "Current Track",
        "artist": "Current Artist",
    }
    configure_runtime(Mock(), provider, bus, runtime_state)

    response = TestClient(guest_api).get("/api/playlist")

    assert response.status_code == 200
    assert response.json()["event_name"] == "Live Party"
    assert response.json()["now_playing"]["title"] == "Current Track"
    assert response.json()["up_next"][0]["title"] == "Next Track"


def test_guest_request_rejected_without_live_event():
    configure_runtime(
        playback=Mock(),
        music_provider=Mock(),
        event_bus=EventBus(),
        runtime_state=RuntimeState(),
    )

    response = TestClient(guest_api).post("/api/requests", json={"song_title": "Brown Munde"})

    assert response.status_code == 409


def test_guest_request_rejected_when_event_disallows_requests():
    runtime_state = RuntimeState()
    runtime_state.update_event_state(
        {
            "event_id": "EVT_no_requests",
            "is_ended": False,
            "event_config": {"allow_requests": False},
        }
    )
    configure_runtime(Mock(), Mock(), EventBus(), runtime_state)

    response = TestClient(guest_api).post("/api/requests", json={"song_title": "Brown Munde"})

    assert response.status_code == 403


def test_guest_url_uses_configured_public_url(monkeypatch):
    monkeypatch.setenv("GUEST_PUBLIC_URL", "https://dj.example.test/requests/")

    assert guest_url() == "https://dj.example.test/requests"


def test_guest_portal_serves_request_page():
    response = TestClient(guest_api).get("/")

    assert response.status_code == 200
    assert "Now playing" in response.text
    assert "/api/playlist" in response.text
    assert "/api/requests" in response.text
