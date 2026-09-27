import asyncio
import os
import sys
import logging
from dotenv import load_dotenv

# Load env before importing app
load_dotenv()
os.environ["AI_MODEL_URL"] = "http://127.0.0.1:8000"
os.environ["LLM_BACKEND"] = "external"

logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("test_playlist")

from app.models.event import EventConfig
from app.agents.orchestrator import DJOrchestrator
from app.api.model_server import app, router
import threading
import uvicorn
import time

def run_server():
    router.initialize(force_backend="external")
    uvicorn.run(app, host="127.0.0.1", port=8000, log_level="error")

async def test_workflow():
    
    # Start local server
    t = threading.Thread(target=run_server, daemon=True)
    t.start()
    time.sleep(3)
    
    config = EventConfig(
        event_id="test_event_01",
        name="Test Party",
        event_type="college_party"
    )
    
    orchestrator = DJOrchestrator()
    await orchestrator.start(config)
    
    logger.info(f"Current Queue Length: {len(orchestrator.queue_manager.items)}")
    for item in orchestrator.queue_manager.items:
        logger.info(f"Queue Item: {item.position} - {item.song_id}")
        
    if len(orchestrator.queue_manager.items) == 0:
        logger.error("AI FAILED TO CREATE PLAYLIST!")
        sys.exit(1)
    else:
        logger.info("AI SUCCESSFULLY CREATED PLAYLIST!")
        sys.exit(0)

if __name__ == "__main__":
    asyncio.run(test_workflow())
