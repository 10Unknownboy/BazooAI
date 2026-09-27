import asyncio
from app.agents.orchestrator import DJOrchestrator
from app.models.event import EventConfig
from app.event.event_bus import get_event_bus
from app.database.repositories import get_repository

async def main():
    config = EventConfig(name="Test Event")
    orchestrator = DJOrchestrator()
    
    # We should pre-populate the DB repository or mock it?
    # CandidateGenerator uses self.song_repo.get_all_songs()
    # By default, get_repository("song") might return empty list. Let's see if it errors out.
    await orchestrator.start(config)
    
    # Check if queue has been filled
    queue_items = orchestrator.queue_manager.items
    print(f"Queue size after start: {len(queue_items)}")
    for item in queue_items:
        print(f"  - {item.song_title} (score: {item.final_score})")
        
    await orchestrator.stop()

if __name__ == "__main__":
    asyncio.run(main())
