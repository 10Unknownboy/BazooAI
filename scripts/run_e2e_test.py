import asyncio
import logging
import sys
from pathlib import Path

# Ensure project root in sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.agents.orchestrator import DJOrchestrator
from app.audio.analyzer import AudioAnalyzer
from app.audio.embeddings import EmbeddingManager
from app.audio.feature_extractor import FeatureExtractor
from app.config.settings import get_settings
from app.database.repositories import get_repository
from app.models.event import EventConfig
from app.models.song import Song
from app.providers.local_file_provider import LocalFileProvider

logger = logging.getLogger(__name__)

async def main():
    logging.basicConfig(level=logging.INFO, format='%(asctime)s | %(levelname)s | %(message)s')
    settings = get_settings()

    music_dir = settings.local_music_dir
    logger.info(f"Indexing local files from {music_dir}...")

    # 1. Initialize DB and Provider
    provider = LocalFileProvider(directory=music_dir)

    # 2. Run feature extraction
    feature_extractor = FeatureExtractor()
    embedding_manager = EmbeddingManager()

    analyzer = AudioAnalyzer(
        repository=get_repository("audio_features"),
        feature_extractor=feature_extractor,
        embedding_manager=embedding_manager
    )

    song_repo = get_repository("song")
    count = 0
    for song_id, song_data in provider._index.items():
        if count >= 20:
            break
        # Save to Song repository if not exists
        if not song_repo.get(song_id):
            song = Song(
                song_id=song_id,
                title=song_data["title"],
                artist=song_data["artist"],
                duration=song_data["duration"],
                file_path=song_data["path"]
            )
            song_repo.save(song)

        logger.info(f"Analyzing {song_data['title']}...")
        # Graceful feature extraction test
        analyzer.analyze(song_data["path"], song_id)
        count += 1

    # 3. Setup and start Orchestrator
    config = EventConfig(name="College Farewell Party", vibe="upbeat, emotional, party", event_type="college_party")
    orchestrator = DJOrchestrator()

    # Also start guest API in background
    import threading

    import uvicorn
    from fastapi import FastAPI

    from app.api.guest_api import guest_router
    api_app = FastAPI()
    api_app.include_router(guest_router)

    def run_server():
        uvicorn.run(api_app, host="127.0.0.1", port=8003, log_level="error")

    api_thread = threading.Thread(target=run_server, daemon=True)
    api_thread.start()

    await orchestrator.start(config)

    # Simulate time passing and requests
    await asyncio.sleep(2) # let initial queue generate

    # Hit guest API
    import httpx
    async with httpx.AsyncClient() as client:
        try:
            res = await client.post("http://127.0.0.1:8003/request", json={
                "guest_name": "Senior 26",
                "song_title": "lesgoo",
                "artist": "Unknown"
            })
            logger.info(f"Guest API response: {res.json()}")
        except Exception as e:
            logger.error(f"Failed to hit guest API: {e}")

    await asyncio.sleep(20) # Let AI process request and update queue

    # Simulate 30 mins (we'll just advance epochs and simulate song end)
    for i in range(3):
        logger.info(f"--- Simulating Song {i+1} End ---")
        orchestrator.queue_manager.advance()
        await orchestrator.run_decision_cycle("song_ending")
        await asyncio.sleep(10)

    await orchestrator.stop()
    logger.info("E2E Simulation completed successfully.")

if __name__ == "__main__":
    asyncio.run(main())
