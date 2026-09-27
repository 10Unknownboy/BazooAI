import asyncio
import threading
from app.agents.orchestrator import DJOrchestrator
from app.event.event_bus import get_event_bus, BusEvent

def test_bug():
    # Setup loop in background
    loop = asyncio.new_event_loop()
    def run_loop(l):
        asyncio.set_event_loop(l)
        l.run_forever()
    t = threading.Thread(target=run_loop, args=(loop,), daemon=True)
    t.start()

    orch = DJOrchestrator()
    orch.is_running = True
    orch.current_state = "mock_state"

    bus = get_event_bus()
    
    print("Testing if event bus from main thread crashes async callback...")
    try:
        bus.publish(BusEvent.SONG_ENDED, data={})
        print("Success? This shouldn't happen.")
    except Exception as e:
        print(f"Caught exception: {type(e).__name__}: {e}")

if __name__ == "__main__":
    test_bug()
