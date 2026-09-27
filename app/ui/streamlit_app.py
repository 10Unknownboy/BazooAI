from __future__ import annotations

import asyncio
import logging
import threading
from concurrent.futures import Future
from typing import Any

import streamlit as st

from app.agents.ai_client import AIModelClient
from app.agents.orchestrator import DJOrchestrator
from app.api.guest_api import configure_runtime, guest_url, start_guest_server
from app.config.settings import get_settings
from app.console.logging_setup import setup_logging
from app.event.event_bus import BusEvent, get_event_bus, get_runtime_state
from app.models.agent import AIRequest
from app.models.base import AIMessageType, EventType, VibePreset
from app.models.event import EventConfig
from app.models.feedback import SongFeedback
from app.models.request import SongRequest
from app.music.library_enrichment import LibraryEnrichmentService
from app.music.local_library import sync_local_library
from app.playback.playback_controller import PlaybackController
from app.providers.local_file_provider import LocalFileProvider
from app.queue.queue_manager import QueueManager

logger = logging.getLogger(__name__)

st.set_page_config(page_title="AI DJ System", page_icon="🎛️", layout="wide")


def _run_coroutine(loop: asyncio.AbstractEventLoop, coroutine) -> Future:
    if not loop.is_running():
        coroutine.close()
        raise RuntimeError("The DJ runtime event loop is not running")
    return asyncio.run_coroutine_threadsafe(coroutine, loop)


@st.cache_resource
def init_system() -> dict[str, Any]:
    settings = get_settings()
    setup_logging(log_dir=str(settings.log_dir))

    music_dir = settings.local_music_dir
    music_dir.mkdir(parents=True, exist_ok=True)

    provider = LocalFileProvider(directory=str(music_dir))
    synced_songs = sync_local_library(provider)
    enrichment_service = LibraryEnrichmentService()
    queue_manager = QueueManager()
    orchestrator = DJOrchestrator(queue_manager=queue_manager)
    playback_controller = PlaybackController(queue_manager, provider)
    event_bus = get_event_bus()
    runtime_state = get_runtime_state()
    configure_runtime(
        playback=playback_controller,
        music_provider=provider,
        event_bus=event_bus,
        runtime_state=runtime_state,
    )
    guest_server_error = None
    try:
        guest_portal_url, guest_server_ready = start_guest_server()
    except (RuntimeError, TimeoutError) as error:
        logger.exception("Guest request portal failed to start")
        guest_portal_url = guest_url()
        guest_server_ready = False
        guest_server_error = str(error)

    loop = asyncio.new_event_loop()

    def run_loop() -> None:
        asyncio.set_event_loop(loop)
        loop.run_forever()

    thread = threading.Thread(target=run_loop, name="dj-runtime", daemon=True)
    thread.start()

    return {
        "music_dir": music_dir,
        "synced_songs": synced_songs,
        "enrichment_service": enrichment_service,
        "provider": provider,
        "queue_manager": queue_manager,
        "orchestrator": orchestrator,
        "playback_controller": playback_controller,
        "event_bus": event_bus,
        "runtime_state": runtime_state,
        "guest_portal_url": guest_portal_url,
        "guest_server_ready": guest_server_ready,
        "guest_server_error": guest_server_error,
        "loop": loop,
        "thread": thread,
    }


system = init_system()
orchestrator: DJOrchestrator = system["orchestrator"]
provider: LocalFileProvider = system["provider"]
playback: PlaybackController = system["playback_controller"]
event_bus = system["event_bus"]
runtime_state = system["runtime_state"]
loop: asyncio.AbstractEventLoop = system["loop"]

st.title("AI DJ System")
st.caption(
    "Local music library · deterministic policies and ranking · optional remote AI reasoning"
)
st.info(f"Music folder: `{system['music_dir']}` · Indexed tracks: {len(provider.list_songs())}")

with st.sidebar:
    st.subheader("Guest requests QR")
    st.caption("Guests open this page to see the live queue and send song requests.")
    st.link_button("Open guest page", system["guest_portal_url"])
    st.code(system["guest_portal_url"], language=None)
    if system["guest_server_ready"]:
        try:
            import qrcode

            st.image(qrcode.make(system["guest_portal_url"]).get_image(), width=220)
        except ImportError:
            st.warning("QR display dependency is unavailable; guests can open the URL above.")
        if system["guest_portal_url"].startswith("http://127.0.0.1"):
            st.warning(
                "This address only works on this computer. Set GUEST_PUBLIC_URL to a reachable "
                "HTTPS URL or connect guests to the same LAN and use the displayed LAN address."
            )
        else:
            st.caption(
                "For guests on another network, set GUEST_PUBLIC_URL to your secure public "
                "tunnel URL and expose guest port 8003."
            )
    else:
        st.error(f"Guest request server is unavailable: {system['guest_server_error']}")
    st.divider()
    st.header("Event")
    if not orchestrator.is_running:
        event_name = st.text_input("Event name", "Local DJ session")
        event_id = st.text_input("Event ID", "local-event")
        event_type = st.selectbox("Event type", [value.value for value in EventType])
        vibe = st.selectbox("Starting vibe", [value.value for value in VibePreset])
        col_age_min, col_age_max = st.columns(2)
        min_age = col_age_min.number_input("Minimum age", 0, 100, 18)
        max_age = col_age_max.number_input("Maximum age", 0, 100, 30)
        duration = st.number_input("Duration (minutes)", 1, 1440, 240)
        languages = st.multiselect(
            "Allowed languages",
            ["Hindi", "Punjabi", "English", "Spanish", "Other"],
            default=["Hindi", "Punjabi", "English"],
        )
        explicit_allowed = st.checkbox("Allow explicit tracks", value=False)
        preferred_genres = st.text_input("Preferred genres (comma-separated)")
        avoided_genres = st.text_input("Avoided genres (comma-separated)")
        preferred_artists = st.text_input("Preferred artists (comma-separated)")
        avoided_artists = st.text_input("Avoided artists (comma-separated)")
        allow_requests = st.checkbox("Allow guest requests", value=True)

        if st.button("Start event", type="primary", use_container_width=True):
            if max_age < min_age:
                st.error("Maximum audience age must be at least the minimum age.")
            elif not provider.list_songs():
                st.error(
                    "No playable tracks found. Add MP3/WAV/FLAC/OGG files to "
                    f"`{system['music_dir']}` and refresh."
                )
            else:
                config = EventConfig(
                    event_id=event_id,
                    name=event_name,
                    event_type=event_type,
                    min_age=min_age,
                    max_age=max_age,
                    duration_minutes=duration,
                    languages=languages,
                    starting_vibe=vibe,
                    explicit_allowed=explicit_allowed,
                    prefer_genres=[
                        item.strip() for item in preferred_genres.split(",") if item.strip()
                    ],
                    avoid_genres=[
                        item.strip() for item in avoided_genres.split(",") if item.strip()
                    ],
                    prefer_artists=[
                        item.strip() for item in preferred_artists.split(",") if item.strip()
                    ],
                    avoid_artists=[
                        item.strip() for item in avoided_artists.split(",") if item.strip()
                    ],
                    allow_requests=allow_requests,
                )
                try:
                    with st.spinner("Starting event and preparing the lookahead queue..."):
                        _run_coroutine(loop, orchestrator.start(config)).result(timeout=90)
                    st.rerun()
                except Exception as error:
                    st.error(f"Could not start event: {error}")
    else:
        state = orchestrator.get_state()
        st.success(f"Running: {state.event_config.name if state else 'Event'}")
        if st.button("Stop event", use_container_width=True):
            try:
                playback.stop()
                _run_coroutine(loop, orchestrator.stop()).result(timeout=30)
                st.rerun()
            except Exception as error:
                st.error(f"Could not stop event cleanly: {error}")

    st.divider()
    if st.button("Refresh local music library", use_container_width=True):
        try:
            provider.refresh()
            system["synced_songs"] = sync_local_library(provider)
            st.success(f"Indexed {len(provider.list_songs())} local tracks.")
            st.rerun()
        except Exception as error:
            st.error(f"Could not refresh local music: {error}")
    if st.button("Fetch MusicBrainz metadata + LRCLIB lyrics", use_container_width=True):
        active_job = system.get("enrichment_future")
        if active_job and not active_job.done():
            st.warning("Library enrichment is already running.")
        else:
            system["enrichment_future"] = _run_coroutine(
                loop, system["enrichment_service"].enrich_library()
            )
            st.success("Enrichment started in the background; playback remains available.")

tabs = st.tabs(["Dashboard Console", "Debug Console", "API Console"])

@st.fragment(run_every="2s")
def render_dashboard_console():
    state = runtime_state.get_event_state()
    queue_snapshot = runtime_state.get_queue_state() or {"items": []}
    queue_items = queue_snapshot.get("items", [])
    job = system.get("enrichment_future")
    if job:
        if job.done():
            try:
                result = job.result()
            except Exception as error:
                st.error(f"Library enrichment failed: {error}")
            else:
                st.success(
                    f"Metadata/lyrics enrichment complete: {result['metadata_updated']} "
                    f"metadata updates, {result['lyrics_found']} lyric matches, "
                    f"{result['errors']} errors."
                )
            system["enrichment_future"] = None
        else:
            progress = system["enrichment_service"].progress
            st.info(
                f"Enrichment running: {progress['checked']}/{progress['total']} tracks checked; "
                f"{progress['lyrics_found']} lyrics found."
            )
    if not state:
        st.info("Create an event from the sidebar to start the DJ.")
    else:
        event_config = state.get("event_config", {})
        metrics = st.columns(4)
        metrics[0].metric("Event", event_config.get("name", state.get("event_id", "")))
        metrics[1].metric("Vibe", state.get("current_vibe", ""))
        metrics[2].metric("Energy", f"{state.get('current_energy', 0.0):.0%}")
        metrics[3].metric("Progress", f"{state.get('event_progress', 0.0):.0%}")

        current = provider.current_song()
        if current and playback.is_playing:
            remaining = playback.get_remaining_time()
            st.success(
                f"Now playing: **{current.get('title', 'Unknown')}** — "
                f"{current.get('artist', 'Unknown Artist')} "
                f"({remaining / 60:.1f} min remaining)"
            )
        elif playback.is_paused and playback.current_song:
            st.warning(
                f"Paused: **{playback.current_song.title}** — {playback.current_song.artist}"
            )
        else:
            st.info("Nothing is currently playing.")
        if not provider.audio_available:
            st.warning(
                "No audio output device is available to the machine running this app. "
                "Playback will fail instead of pretending to play."
            )

        control_columns = st.columns(5)
        if control_columns[0].button("Play / Resume"):
            if not playback.play():
                error = playback.last_error or "unknown provider error"
                st.warning(f"Playback could not start: {error}")
            else:
                st.rerun()
        if control_columns[1].button("Pause"):
            if not playback.pause():
                st.warning("Nothing is currently playing, or the audio device could not pause.")
            st.rerun()
        if control_columns[2].button("Skip"):
            if not playback.skip():
                st.warning("No current track could be skipped.")
            st.rerun()
        if control_columns[3].button("Stop playback"):
            if not playback.stop():
                st.error("The audio provider failed to stop playback.")
            st.rerun()
        volume = control_columns[4].slider("Volume", 0, 100, 50, key="volume")
        if not playback.volume(volume):
            st.caption("Volume control requires an initialized audio output device.")

        st.subheader("Event controls")
        vibe_col, energy_col = st.columns(2)
        with vibe_col:
            requested_vibe = st.selectbox(
                "Change vibe", [item.value for item in VibePreset], key="vibe_change"
            )
            if st.button("Apply vibe"):
                _run_coroutine(
                    loop, orchestrator.handle_command({"command": "vibe", "args": [requested_vibe]})
                ).result(timeout=90)
                st.rerun()
        with energy_col:
            target_energy = st.slider(
                "Target energy",
                min_value=0,
                max_value=100,
                value=round(state.get("target_energy", 0.5) * 100),
                key=f"target-energy-{state.get('decision_epoch', 0)}",
            )
            if st.button("Apply energy"):
                _run_coroutine(
                    loop,
                    orchestrator.handle_command(
                        {"command": "energy", "args": [str(target_energy)]}
                    ),
                ).result(timeout=90)
                st.rerun()

        st.subheader("Five-song lookahead")
        if not queue_items:
            st.warning("The queue is empty. Add playable tracks and refresh the music library.")
        else:
            for item in queue_items[:5]:
                position = item.get("position", 0)
                icon = (
                    "🔊"
                    if position == 0 and playback.is_playing
                    else {
                        "LOCKED": "🔒",
                        "RECONSIDERING": "🟡",
                        "FLEXIBLE": "🟢",
                    }.get(item.get("lock_status"), "🟢")
                )
                st.write(
                    f"{icon} **{position + 1}. {item.get('song_title') or item['song_id']}** — "
                    f"{item.get('song_artist') or 'Unknown Artist'} · "
                    f"score {item.get('final_score', 0):.1f} · "
                    f"{item.get('lock_status', 'FLEXIBLE')}"
                )

        request_column, feedback_column = st.columns(2)
        with request_column:
            st.subheader("Guest request")
            requested_song = st.text_input("Song title or title + artist", key="song-request")
            requester = st.text_input("Guest name (optional)", key="requester")
            if st.button("Submit request", disabled=not event_config.get("allow_requests", True)):
                if not requested_song.strip():
                    st.error("Enter a song title or search phrase.")
                else:
                    request = SongRequest(
                        requested_song_query=requested_song.strip(),
                        requester=requester.strip() or "dashboard",
                    )
                    event_bus.publish(
                        BusEvent.REQUEST_RECEIVED,
                        source="streamlit",
                        data={"request": request.model_dump(mode="json")},
                    )
                    st.success(f"Request received: {requested_song.strip()}")

        with feedback_column:
            st.subheader("Crowd feedback")
            if state.get("current_song_id"):
                overall = st.slider("Overall", 1, 10, 8, key="feedback-overall")
                energy = st.slider("Energy", 1, 10, 8, key="feedback-energy")
                song_choice = st.slider("Song choice", 1, 10, 8, key="feedback-song")
                transition = st.slider("Transition", 1, 10, 8, key="feedback-transition")
                vibe_rating = st.slider("Vibe", 1, 10, 8, key="feedback-vibe")
                if st.button("Send feedback"):
                    feedback = SongFeedback(
                        event_id=state["event_id"],
                        song_id=state["current_song_id"],
                        overall_rating=overall,
                        energy_rating=energy,
                        song_choice_rating=song_choice,
                        transition_rating=transition,
                        vibe_rating=vibe_rating,
                        current_vibe=state.get("vibe_vector"),
                        target_energy=state.get("target_energy"),
                        current_energy=state.get("current_energy"),
                        current_song_id=state.get("current_song_id"),
                        previous_song_ids=state.get("recent_history", []),
                        next_song_ids=[
                            item.get("song_id")
                            for item in queue_items
                            if item.get("song_id") != state.get("current_song_id")
                        ],
                        event_type=event_config.get("event_type"),
                        audience_age_range=[
                            event_config.get("min_age", 0),
                            event_config.get("max_age", 100),
                        ],
                        event_progress=state.get("event_progress"),
                        decision_epoch=state.get("decision_epoch", 0),
                    )
                    event_bus.publish(
                        BusEvent.FEEDBACK_RECEIVED,
                        source="streamlit",
                        data={"feedback": feedback.model_dump(mode="json")},
                    )
                    st.success("Feedback recorded.")
            else:
                st.caption("Start playback before submitting track feedback.")

with tabs[0]:
    render_dashboard_console()

state = runtime_state.get_event_state()

with tabs[1]:
    st.subheader("Runtime state and decision history")
    st.json(state or {})
    messages = event_bus.get_history(limit=100)
    for message in reversed(messages):
        if message.event_type in {
            BusEvent.POLICY_VIOLATION,
            BusEvent.SCORING_COMPLETE,
            BusEvent.AGENT_DECISION,
            BusEvent.EVENT_STATE_UPDATED,
            BusEvent.ERROR,
            BusEvent.WARNING,
        }:
            st.write(
                f"{message.timestamp.isoformat()} · {message.event_type.value} · "
                f"{message.source}: {message.data}"
            )

with tabs[2]:
    st.subheader("AI/API activity")
    if st.button("Run live AI decision check"):
        playable_tracks = (
            orchestrator.candidate_generator.get_playable_library_tracks(limit=3)
        )
        if not playable_tracks:
            st.error("No local music tracks at least 30 seconds long are available to test.")
        else:
            request = AIRequest(
                message_type=AIMessageType.DJ_DECISION,
                candidate_songs=[
                    {
                        "song_id": track.song_id,
                        "title": track.title,
                        "artist": track.artist,
                    }
                    for track in playable_tracks
                ],
                request_data={
                    "prompt": (
                        "Choose one suitable supplied track for the event. "
                        "Return only an ID from the candidates and a short reason."
                    )
                },
            )
            try:
                result = _run_coroutine(
                    loop, AIModelClient().decide(request)
                ).result(timeout=120)
            except Exception as error:
                logger.exception("Manual AI model check failed")
                st.error(f"AI model check failed: {error}")
            else:
                if (
                    result.success
                    and result.model_name
                    and result.model_name.startswith("local:")
                ):
                    st.success(
                        f"Live model: {result.model_name} · "
                        f"{result.latency_ms or 0:.0f} ms"
                    )
                    st.write(result.reason)
                    st.write(f"Recommended IDs: {result.recommended_song_ids}")
                else:
                    st.error(
                        f"No live model response: {result.error or 'unknown AI error'}"
                    )
    messages = event_bus.get_history(limit=100)
    if not messages:
        st.caption("No API or model events have been recorded yet.")
    for message in reversed(messages):
        if message.event_type in {
            BusEvent.AI_REQUEST_SENT,
            BusEvent.AI_RESPONSE_RECEIVED,
            BusEvent.AI_UNAVAILABLE,
            BusEvent.HTTP_REQUEST,
            BusEvent.HTTP_RESPONSE,
            BusEvent.RETRY_ATTEMPT,
            BusEvent.RATE_LIMIT_EXCEEDED,
            BusEvent.CONNECTION_STATE_CHANGED,
            BusEvent.CACHE_HIT,
            BusEvent.CACHE_MISS,
        }:
            st.write(
                f"{message.timestamp.isoformat()} · {message.event_type.value} · "
                f"{message.source}: {message.data}"
            )

st.caption("Dashboard runtime and queue refresh automatically while the page is open.")
