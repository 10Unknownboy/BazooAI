from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys

import httpx

from app.agents.ai_client import AIModelClient
from app.config.settings import get_settings
from app.models.agent import AIRequest
from app.models.base import AIMessageType, VibeVector


async def probe_model(base_url: str, timeout: int) -> int:
    base_url = base_url.rstrip("/")
    try:
        async with httpx.AsyncClient(timeout=10.0) as http:
            response = await http.get(f"{base_url}/health")
            response.raise_for_status()
            health = response.json()
    except (httpx.HTTPError, ValueError) as error:
        print(f"Model server health check failed: {error}", file=sys.stderr)
        return 2

    print(
        "Model server:",
        json.dumps(
            {
                "status": health.get("status"),
                "active_backend": health.get("active_backend"),
                "model_name": health.get("model_name"),
            }
        ),
    )
    if health.get("active_backend") == "mock":
        print("No real model backend is active; this is not a live AI test.", file=sys.stderr)
        return 2

    request = AIRequest(
        message_type=AIMessageType.DJ_DECISION,
        current_vibe=VibeVector(energy=0.75, danceability=0.8, valence=0.7),
        current_energy=0.7,
        target_energy=0.85,
        candidate_songs=[
            {
                "song_id": "manual_probe_1",
                "title": "Levitating",
                "artist": "Dua Lipa",
                "genre": "Pop",
                "energy": 0.82,
                "bpm": 103,
            },
            {
                "song_id": "manual_probe_2",
                "title": "Blinding Lights",
                "artist": "The Weeknd",
                "genre": "Synth-pop",
                "energy": 0.86,
                "bpm": 171,
            },
        ],
        request_data={
            "prompt": (
                "Choose the best supplied candidate for a high-energy party. "
                "Return only its supplied ID and a brief reason."
            )
        },
    )
    client = AIModelClient(timeout_seconds=timeout, max_retries=1)
    client.base_url = base_url
    result = await client.decide(request)
    output = {
        "success": result.success,
        "backend": result.model_name,
        "latency_ms": result.latency_ms,
        "recommendations": result.recommended_song_ids,
        "reason": result.reason,
        "error": result.error,
    }
    print("Live decision:", json.dumps(output, ensure_ascii=False))

    candidate_ids = {song["song_id"] for song in request.candidate_songs}
    if not result.success or not result.model_name or result.model_name == "mock":
        return 1
    if not result.recommended_song_ids or not set(result.recommended_song_ids) <= candidate_ids:
        print("Model response did not contain valid candidate IDs.", file=sys.stderr)
        return 1
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Send one real AI decision request to the configured model server."
    )
    parser.add_argument(
        "--url",
        default=os.getenv("AI_MODEL_URL", get_settings().ai_model.url),
        help="Model server base URL (defaults to AI_MODEL_URL).",
    )
    parser.add_argument(
        "--timeout", type=int, default=90, help="Decision request timeout in seconds."
    )
    args = parser.parse_args()
    return asyncio.run(probe_model(args.url, args.timeout))


if __name__ == "__main__":
    raise SystemExit(main())
