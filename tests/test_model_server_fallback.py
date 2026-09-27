from __future__ import annotations

import asyncio

import pytest
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


def test_local_only_router_never_falls_back_to_external(monkeypatch):
    router = model_server.InferenceRouter()
    router.local_only = True
    router.active_backend = model_server.LLMBackend.LOCAL
    router.local.loaded = True
    router.local.generate = lambda *args, **kwargs: (_ for _ in ()).throw(
        RuntimeError("local inference failed")
    )
    router.external.available = True

    async def unexpected_external_call(prompt, max_tokens=1024):
        raise AssertionError("local-only mode must not call the external API")

    monkeypatch.setattr(router.external, "generate", unexpected_external_call)

    text, backend, error = asyncio.run(router.generate("test"))

    assert text == ""
    assert backend == "mock"
    assert "local inference failed" in error


def test_local_router_reuses_loaded_model_without_reloading(monkeypatch):
    router = model_server.InferenceRouter()
    router.local.loaded = True
    router.local.model_name = "Qwen/Qwen2.5-1.5B-Instruct"
    monkeypatch.setattr(
        router.local,
        "load",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("model should not reload")),
    )

    active = router.initialize(
        force_backend="local",
        model_name="Qwen/Qwen2.5-1.5B-Instruct",
    )

    assert active == model_server.LLMBackend.LOCAL


def test_local_only_startup_fails_if_backend_did_not_load(monkeypatch):
    monkeypatch.setenv("LLM_BACKEND", "local")
    monkeypatch.setattr(
        model_server.router,
        "initialize",
        lambda **kwargs: model_server.LLMBackend.MOCK,
    )
    monkeypatch.setattr(model_server.router.local, "load_error", "weights unavailable")

    with pytest.raises(RuntimeError, match="weights unavailable"):
        asyncio.run(model_server.initialize_backend())
