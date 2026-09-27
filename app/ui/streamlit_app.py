import streamlit as st
import threading
import time
import asyncio
from typing import Optional
import os

from app.event.event_bus import get_event_bus, BusEvent
from app.agents.orchestrator import DJOrchestrator
from app.queue.queue_manager import QueueManager
from app.playback.playback_controller import PlaybackController
from app.providers.local_file_provider import LocalFileProvider
from app.config.settings import get_settings
from app.models.event import EventConfig

st.set_page_config(page_title="AI DJ System Dashboard", layout="wide")

@st.cache_resource
def init_system():
    settings = get_settings()
    
    event_bus = get_event_bus()
    
    music_dir = str(settings.local_music_dir) if settings.local_music_dir else r"D:\media\music"
    if not os.path.exists(music_dir):
        try:
            os.makedirs(music_dir, exist_ok=True)
        except Exception:
            pass
        
    provider = LocalFileProvider(directory=music_dir)
    
    queue_manager = QueueManager()
    playback_controller = PlaybackController(queue_manager, provider)
    
    orchestrator = DJOrchestrator()
    
    loop = asyncio.new_event_loop()
    def run_loop(loop):
        asyncio.set_event_loop(loop)
        loop.run_forever()
        
    t = threading.Thread(target=run_loop, args=(loop,), daemon=True)
    t.start()
    
    return {
        "event_bus": event_bus,
        "provider": provider,
        "queue_manager": queue_manager,
        "playback_controller": playback_controller,
        "orchestrator": orchestrator,
        "loop": loop
    }

system = init_system()
orchestrator = system["orchestrator"]
playback_controller = system["playback_controller"]
queue_manager = system["queue_manager"]
provider = system["provider"]
loop = system["loop"]

st.title("🎛️ AI DJ System Dashboard")

if "req_query" not in st.session_state:
    st.session_state.req_query = ""

with st.sidebar:
    st.header("Event Configuration")
    
    if not orchestrator.is_running:
        event_id = st.text_input("Event ID", value="event_test_01")
        vibe = st.text_input("Initial Vibe", value="chill, upbeat")
        
        if st.button("Start Event"):
            config = EventConfig(
                event_id=event_id,
                vibe=vibe
            )
            asyncio.run_coroutine_threadsafe(orchestrator.start(config), loop)
            st.rerun()
    else:
        st.success("Event is currently running!")
        if st.button("Stop Event"):
            asyncio.run_coroutine_threadsafe(orchestrator.stop(), loop)
            playback_controller.stop()
            st.rerun()
            

        st.subheader("System Status")
        st.write(f"Songs in library: {len(provider._index)}")
        
        st.markdown("---")
        st.subheader("Guest Requests API")
        st.write("Scan to submit requests:")
        try:
            import requests
            import io
            from PIL import Image
            # Fetch QR code from local Guest API if running
            qr_res = requests.get("http://127.0.0.1:8003/qr", timeout=1)
            if qr_res.status_code == 200:
                img = Image.open(io.BytesIO(qr_res.content))
                st.image(img, use_container_width=True)
            else:
                st.warning("Guest API QR not available (API might not be running).")
        except Exception:
            st.warning("Guest API not running. Run API separately to enable QR requests.")


if orchestrator.is_running:
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("Playback Control")
        
        current_song = playback_controller.get_current_song()
        if current_song:
            st.info(f"🎶 **Now Playing:** {current_song.title} - {current_song.artist}")
        elif provider.current_song():
            s = provider.current_song()
            st.info(f"🎶 **Now Playing:** {s.get('title')} - {s.get('artist', 'Unknown')}")
        else:
            st.info("No song playing.")
            
        c_play, c_pause, c_next = st.columns(3)
        with c_play:
            if st.button("▶️ Play"):
                playback_controller.play()
                st.rerun()
        with c_pause:
            if st.button("⏸️ Pause"):
                playback_controller.pause()
                st.rerun()
        with c_next:
            if st.button("⏭️ Next"):
                playback_controller.skip()
                st.rerun()
                
        volume = st.slider("Volume", 0, 100, 50)
        playback_controller.volume(volume)
            
    with col2:
        st.subheader("Interactions")
        
        st.write("Submit a Song Request:")
        req = st.text_input("Search/Request Song", key="req_input")
        if st.button("Submit Request"):
            system["event_bus"].publish(BusEvent.REQUEST_RECEIVED, source="dashboard", data={"query": req})
            st.success(f"Requested: {req}")
            
        st.write("Audience Feedback:")
        feedback = st.selectbox("How is the crowd feeling?", ["Awesome", "Too slow", "Too fast", "Boring"])
        if st.button("Send Feedback"):
            system["event_bus"].publish(BusEvent.FEEDBACK_RECEIVED, source="dashboard", data={"feedback": feedback})
            st.success(f"Feedback sent: {feedback}")
            
    st.subheader("Upcoming Queue")
    
    items = queue_manager.items
    if not items:
        st.write("Queue is empty. Waiting for AI DJ to select songs...")
        if st.button("Refresh Queue"):
            st.rerun()
    else:
        for i, item in enumerate(items):
            status = "🔊 Playing" if i == 0 else f"{i}"
            st.write(f"{status} | **{item.song_title}** by {item.song_artist} (Score: {item.final_score:.2f})")
            
else:
    st.info("Please start the event from the sidebar to activate controls.")
