from __future__ import annotations

from fastapi.testclient import TestClient

from app.api.guest_api import app as guest_api
from app.console.command_handler import CommandHandler
from app.event.event_bus import BusEvent, EventBus
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
    from app.event.event_bus import get_event_bus

    bus = get_event_bus()
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

    assert response.status_code == 200
    request = SongRequest.model_validate(received[0].data["request"])
    assert request.requested_song_query == "Brown Munde AP Dhillon"
    assert request.requester == "Manual tester"
