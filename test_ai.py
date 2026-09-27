import asyncio
import os
import sys

from app.agents.ai_client import AIModelClient
from app.models.agent import AIRequest
from app.models.base import AIMessageType

async def test_ai():
    os.environ["AI_MODEL_URL"] = "http://localhost:8000"
    client = AIModelClient()
    
    request = AIRequest(
        message_type=AIMessageType.DJ_DECISION,
        candidate_songs=[{"song_id": "123", "title": "Test", "artist": "Test", "genre": "Pop", "energy": 0.8, "bpm": 120}],
        request_data={"prompt": "Pick a song."}
    )
    print("Sending request...")
    response = await client.decide(request)
    print("Response:", response)

if __name__ == "__main__":
    asyncio.run(test_ai())
