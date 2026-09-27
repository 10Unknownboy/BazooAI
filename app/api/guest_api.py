from fastapi import FastAPI, APIRouter
from pydantic import BaseModel
import logging
import uuid
import time
from app.event.event_bus import get_event_bus, BusEvent
from app.models.request import SongRequest as OrchestratorSongRequest

logger = logging.getLogger(__name__)

guest_router = APIRouter()
app = FastAPI(title="AI DJ Guest API")
app.include_router(guest_router)

class SongRequest(BaseModel):
    guest_name: str | None = None
    song_title: str
    artist: str | None = None
    dedication: str | None = None

@guest_router.post("/request")
async def submit_request(req: SongRequest):
    """Guest submits a song request."""
    bus = get_event_bus()
    request_id = f"req_{uuid.uuid4().hex[:8]}"
    
    query = f"{req.song_title} {req.artist}".strip() if req.artist else req.song_title
    request = OrchestratorSongRequest(
        request_id=request_id,
        requested_song_query=query,
        requester=req.guest_name or "anonymous",
    )
    
    # Emit event for the orchestrator/agent to handle
    bus.publish(BusEvent.REQUEST_RECEIVED,
        source="guest_api",
        data={
            "request": request.model_dump(mode="json"),
            "guest_name": req.guest_name,
            "dedication": req.dedication,
            "timestamp": time.time(),
        }
    )
    
    logger.info(f"Received guest request {request_id}: {req.song_title} by {req.artist}")
    return {"status": "success", "message": "Request submitted successfully", "request_id": request_id}
