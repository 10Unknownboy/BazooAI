from __future__ import annotations

import logging
import socket
import threading
import time
import uuid
from dataclasses import dataclass
from typing import Any

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from app.event.event_bus import BusEvent, EventBus, RuntimeState, get_event_bus, get_runtime_state
from app.models.request import SongRequest as OrchestratorSongRequest
from app.playback.playback_controller import PlaybackController
from app.providers.base import MusicProvider

logger = logging.getLogger(__name__)


@dataclass
class GuestRuntime:
    """Live objects shared with the DJ process that owns the orchestrator."""

    event_bus: EventBus
    runtime_state: RuntimeState
    playback: PlaybackController
    music_provider: MusicProvider


class GuestSongRequest(BaseModel):
    guest_name: str | None = Field(default=None, max_length=80)
    song_title: str = Field(min_length=1, max_length=200)
    artist: str | None = Field(default=None, max_length=200)
    dedication: str | None = Field(default=None, max_length=300)


app = FastAPI(title="AI DJ Guest Request Portal")
_runtime: GuestRuntime | None = None
_server: uvicorn.Server | None = None
_server_thread: threading.Thread | None = None

GUEST_PAGE = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="theme-color" content="#111827">
  <title>DJ Requests</title>
  <style>
    :root { color-scheme: dark; font-family: system-ui, sans-serif; }
    body { margin: 0; background: #111827; color: #f9fafb; }
    main { max-width: 620px; margin: auto; padding: 24px 18px 48px; }
    h1 { margin-bottom: 4px; } .muted { color: #9ca3af; }
    .card { background: #1f2937; border-radius: 16px; padding: 18px; margin: 16px 0; }
    .track { padding: 11px 0; border-bottom: 1px solid #374151; }
    .track:last-child { border: 0; } .track small { display: block; color: #9ca3af; }
    label { display: block; margin: 12px 0 5px; }
    input, textarea, button { box-sizing: border-box; width: 100%; padding: 12px;
      border-radius: 9px; border: 1px solid #4b5563; font: inherit; }
    input, textarea { color: #f9fafb; background: #111827; }
    button { margin-top: 15px; background: #7c3aed; color: white; border: 0;
      font-weight: 700; cursor: pointer; }
    button:disabled { opacity: .55; cursor: wait; }
    #notice { min-height: 1.5em; } .status { color: #a7f3d0; }
  </style>
</head>
<body><main>
  <h1 id="event-name">DJ requests</h1>
  <div id="event-status" class="muted">Loading live playlist…</div>
  <section class="card">
    <h2>Now playing</h2>
    <div id="now-playing" class="muted">No song playing</div>
  </section>
  <section class="card">
    <h2>Up next</h2>
    <div id="playlist" class="muted">Loading…</div>
  </section>
  <section class="card">
    <h2>Request a song</h2>
    <form id="request-form">
      <label for="song">Song title</label>
      <input id="song" name="song_title" maxlength="200" required>
      <label for="artist">Artist (optional)</label>
      <input id="artist" name="artist" maxlength="200">
      <label for="guest">Your name (optional)</label>
      <input id="guest" name="guest_name" maxlength="80">
      <label for="dedication">Dedication (optional)</label>
      <textarea id="dedication" name="dedication" maxlength="300" rows="2"></textarea>
      <button id="submit" type="submit">Send request</button>
      <p id="notice" role="status" aria-live="polite"></p>
    </form>
  </section>
  <p class="muted">Requests are reviewed by the DJ and may be queued or declined.</p>
</main>
<script>
  const playlist = document.querySelector("#playlist");
  async function refreshPlaylist() {
    try {
      const response = await fetch("/api/playlist", {cache: "no-store"});
      if (!response.ok) throw new Error("Playlist unavailable");
      const data = await response.json();
      document.querySelector("#event-name").textContent = data.event_name || "DJ requests";
      document.querySelector("#event-status").textContent = data.active
        ? "Live event · playlist refreshes automatically"
        : "The DJ has not started an event yet.";
      document.querySelector("#now-playing").textContent = data.now_playing
        ? `${data.now_playing.title} — ${data.now_playing.artist}` : "No song playing";
      playlist.replaceChildren();
      if (!data.up_next.length) {
        playlist.textContent = data.active
          ? "No songs queued yet."
          : "The live playlist will appear here.";
      }
      for (const track of data.up_next) {
        const row = document.createElement("div");
        row.className = "track";
        const title = document.createElement("span");
        title.textContent = `${track.position}. ${track.title}`;
        const artist = document.createElement("small");
        artist.textContent = track.artist;
        row.append(title, artist);
        playlist.append(row);
      }
      const form = document.querySelector("#request-form");
      form.querySelector("button").disabled = !data.requests_allowed;
      if (!data.requests_allowed) {
        document.querySelector("#notice").textContent = "Requests are currently disabled.";
      }
    } catch (_) {
      playlist.textContent = "Could not reach the DJ server. Check the connection and retry.";
    }
  }
  refreshPlaylist();
  setInterval(refreshPlaylist, 5000);
  document.querySelector("#request-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const form = event.currentTarget;
    const button = form.querySelector("button");
    const notice = document.querySelector("#notice");
    button.disabled = true;
    notice.textContent = "Sending request…";
    try {
      const payload = Object.fromEntries(new FormData(form).entries());
      const response = await fetch("/api/requests", {
        method: "POST", headers: {"Content-Type": "application/json"},
        body: JSON.stringify(payload)
      });
      const result = await response.json();
      if (!response.ok) throw new Error(result.detail || "Request could not be submitted.");
      notice.className = "status";
      notice.textContent = "Request sent to the DJ.";
      form.reset();
    } catch (error) {
      notice.className = "";
      notice.textContent = error.message;
    } finally {
      button.disabled = false;
      refreshPlaylist();
    }
  });
</script></body></html>"""


def configure_runtime(
    playback: PlaybackController,
    music_provider: MusicProvider,
    event_bus: EventBus | None = None,
    runtime_state: RuntimeState | None = None,
) -> None:
    """Bind guest endpoints to the same in-process orchestrator state and queue."""
    global _runtime
    _runtime = GuestRuntime(
        event_bus=event_bus or get_event_bus(),
        runtime_state=runtime_state or get_runtime_state(),
        playback=playback,
        music_provider=music_provider,
    )


def guest_url() -> str:
    """Return the URL guests can open from the same LAN or configured tunnel."""
    import os

    public_url = os.getenv("GUEST_PUBLIC_URL", "").strip().rstrip("/")
    if public_url:
        return public_url
    host = _lan_ipv4()
    port = int(os.getenv("GUEST_API_PORT", "8003"))
    return f"http://{host}:{port}/"


def _lan_ipv4() -> str:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect(("192.0.2.1", 80))
            address = sock.getsockname()[0]
            if not address.startswith("127."):
                return address
    except OSError:
        logger.exception("Could not detect the local network address for the guest QR URL")
    return "127.0.0.1"


def start_guest_server() -> tuple[str, bool]:
    """Run the guest web/API service in this process so bus events reach the DJ."""
    global _server, _server_thread
    import os

    if _server_thread and _server_thread.is_alive():
        return guest_url(), True

    host = os.getenv("GUEST_API_HOST", "0.0.0.0")
    port = int(os.getenv("GUEST_API_PORT", "8003"))
    config = uvicorn.Config(app, host=host, port=port, log_level="warning")
    _server = uvicorn.Server(config)
    _server_thread = threading.Thread(
        target=_server.run,
        name="guest-request-api",
        daemon=True,
    )
    _server_thread.start()
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        if _server.started:
            return guest_url(), True
        if not _server_thread.is_alive():
            raise RuntimeError(f"Guest request server failed to start on {host}:{port}")
        time.sleep(0.05)
    raise TimeoutError(f"Guest request server did not start on {host}:{port}")


def _require_runtime() -> GuestRuntime:
    if _runtime is None:
        raise HTTPException(status_code=503, detail="DJ runtime is not connected.")
    return _runtime


def _event_snapshot(runtime: GuestRuntime) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    state = runtime.runtime_state.get_event_state()
    queue = runtime.runtime_state.get_queue_state() or {"items": []}
    return state, queue


@app.get("/", response_class=HTMLResponse)
async def guest_home() -> HTMLResponse:
    return HTMLResponse(GUEST_PAGE)


@app.get("/api/playlist")
async def get_playlist() -> dict[str, Any]:
    runtime = _require_runtime()
    state, queue = _event_snapshot(runtime)
    config = (state or {}).get("event_config", {})
    current_id = (state or {}).get("current_song_id")
    current = runtime.music_provider.get_song(current_id) if current_id else None
    items = queue.get("items", [])
    up_next = []
    for item in items:
        if item.get("song_id") == current_id:
            continue
        up_next.append(
            {
                "song_id": item.get("song_id"),
                "title": item.get("song_title") or item.get("song_id") or "Unknown",
                "artist": item.get("song_artist") or "Unknown artist",
                "position": len(up_next) + 1,
            }
        )
    active = bool(state and not state.get("is_ended"))
    return {
        "active": active,
        "event_id": (state or {}).get("event_id"),
        "event_name": config.get("name"),
        "playback_state": (state or {}).get("playback_state", "STOPPED"),
        "now_playing": (
            {"song_id": current_id, "title": current.get("title"), "artist": current.get("artist")}
            if current
            else None
        ),
        "up_next": up_next,
        "requests_allowed": bool(active and config.get("allow_requests", False)),
    }


@app.post("/api/requests", status_code=202)
@app.post("/request", status_code=202, include_in_schema=False)
async def submit_request(request: GuestSongRequest) -> dict[str, str]:
    runtime = _require_runtime()
    state, _ = _event_snapshot(runtime)
    if not state or state.get("is_ended"):
        raise HTTPException(status_code=409, detail="There is no active DJ event.")
    if not state.get("event_config", {}).get("allow_requests", False):
        raise HTTPException(status_code=403, detail="Song requests are disabled for this event.")

    title = request.song_title.strip()
    artist = request.artist.strip() if request.artist else None
    if not title:
        raise HTTPException(status_code=422, detail="Song title cannot be blank.")
    query = f"{title} {artist}".strip() if artist else title
    song_request = OrchestratorSongRequest(
        request_id=f"req_{uuid.uuid4().hex}",
        requested_song_query=query,
        requester=request.guest_name.strip()
        if request.guest_name and request.guest_name.strip()
        else "guest",
    )
    runtime.event_bus.publish(
        BusEvent.REQUEST_RECEIVED,
        source="guest_portal",
        data={
            "request": song_request.model_dump(mode="json"),
            "dedication": request.dedication,
            "submitted_at": time.time(),
        },
    )
    logger.info("Accepted guest song request %s", song_request.request_id)
    return {"status": "received", "request_id": song_request.request_id}
