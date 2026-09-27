from fastapi import FastAPI, APIRouter, HTTPException, BackgroundTasks, Request
from pydantic import BaseModel
import qrcode
import io
from fastapi.responses import Response
import logging
import uuid
import time
from app.event.event_bus import get_event_bus, BusEvent

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
    
    # Emit event for the orchestrator/agent to handle
    bus.publish(BusEvent.REQUEST_RECEIVED,
        source="guest_api",
        data={
            "request_id": request_id,
            "guest_name": req.guest_name,
            "song_title": req.song_title,
            "artist": req.artist,
            "dedication": req.dedication,
            "timestamp": time.time(),
            "query": query
        }
    )
    
    logger.info(f"Received guest request {request_id}: {req.song_title} by {req.artist}")
    return {"status": "success", "message": "Request submitted successfully", "request_id": request_id}

@guest_router.get("/qr")
async def get_qr_code(request: Request):
    """Generate a QR code pointing to the request API/UI."""
    # Assuming the API is running at the host URL, we point to a theoretical frontend or Swagger for now
    base_url = str(request.base_url).rstrip('/')
    target_url = f"{base_url}/docs#/default/submit_request_request_post"
    
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=10,
        border=4,
    )
    qr.add_data(target_url)
    qr.make(fit=True)
    
    img = qr.make_image(fill_color="black", back_color="white")
    
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    
    return Response(content=buf.getvalue(), media_type="image/png")
