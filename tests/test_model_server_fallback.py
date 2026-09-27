from __future__ import annotations

from fastapi.testclient import TestClient

from app.api import model_server


def test_invalid_remote_model_output_is_reported_as_fallback(monkeypatch):
    async def malformed_response(prompt, max_tokens=1024):
        return "not valid JSON", "external:test-model", None

    monkeypatch.setattr(model_server.router, "generate", malformed_response)

    response = TestClient(model_server.app).post(
        "/v1/ai/decide",
        json={"message_type": "DJ_DECISION"},
    )

    assert response.status_code == 200
    assert response.json()["success"] is False
    assert response.json()["model_name"] == "mock"
    assert response.json()["error"] == "AI model returned invalid JSON"


def test_empty_remote_model_response_preserves_failure_reason(monkeypatch):
    async def empty_response(prompt, max_tokens=1024):
        return (
            "",
            "mock",
            "External AI provider returned an empty response",
        )

    monkeypatch.setattr(model_server.router, "generate", empty_response)

    response = TestClient(model_server.app).post(
        "/v1/ai/decide",
        json={"message_type": "VIBE_UPDATE"},
    )

    assert response.status_code == 200
    assert response.json()["success"] is False
    assert response.json()["model_name"] == "mock"
    assert "empty response" in response.json()["error"]
