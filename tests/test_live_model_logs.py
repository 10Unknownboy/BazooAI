from __future__ import annotations

import logging

from fastapi.testclient import TestClient

from app.api.model_server import app, recent_log_handler


def test_log_endpoint_returns_bounded_redacted_recent_records():
    record = logging.LogRecord(
        name="test.model",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="Authorization: Bearer secret-value api_key=private-value",
        args=(),
        exc_info=None,
    )
    recent_log_handler.emit(record)

    response = TestClient(app).get("/log?limit=1")

    assert response.status_code == 200
    logs = response.json()["logs"]
    assert len(logs) == 1
    assert "[REDACTED]" in logs[0]["message"]
    assert "secret-value" not in logs[0]["message"]
    assert "private-value" not in logs[0]["message"]


def test_log_endpoint_rejects_unbounded_limits():
    response = TestClient(app).get("/log?limit=501")

    assert response.status_code == 422
