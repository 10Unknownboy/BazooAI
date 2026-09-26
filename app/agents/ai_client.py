from __future__ import annotations
import os
import httpx
import logging
import asyncio
from typing import Optional, Dict, Any

from app.models.agent import AIRequest, AIResponse
from app.event.event_bus import get_event_bus, BusEvent
from app.config.settings import get_settings

logger = logging.getLogger(__name__)

class AIModelClient:
    """Client for communicating with the remote AI model server."""
    
    def __init__(self, timeout_seconds: int = 30, max_retries: int = 3):
        self.settings = get_settings()
        self.base_url = os.getenv("AI_MODEL_URL", "http://localhost:8000")
        
        self.timeout = timeout_seconds
        self.max_retries = max_retries
        self.event_bus = get_event_bus()

    async def check_health(self) -> bool:
        """Check if the model server is available."""
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(f"{self.base_url}/health")
                response.raise_for_status()
                return True
        except Exception as e:
            logger.warning(f"AI model server health check failed: {e}")
            self.event_bus.publish(BusEvent.AI_UNAVAILABLE, source="ai_client", data={"error": str(e)})
            return False

    async def decide(self, request: AIRequest) -> AIResponse:
        """Send a structured request to the AI model and get a response."""
        return await self._send_request(f"{self.base_url}/v1/ai/decide", request)

    async def generate(self, prompt: str, context: Optional[Dict[str, Any]] = None) -> AIResponse:
        """Generate a generic response based on a prompt."""
        request = AIRequest(
            agent_id="generic",
            task_type="generation",
            context=context or {},
            prompt=prompt
        )
        return await self._send_request(f"{self.base_url}/v1/ai/decide", request)

    async def classify(self, data: Dict[str, Any], schema: Optional[Dict[str, Any]] = None) -> AIResponse:
        """Classify data using the AI model."""
        request = AIRequest(
            agent_id="classifier",
            task_type="classification",
            context={"data": data, "schema": schema},
            prompt="Classify the following data."
        )
        return await self._send_request(f"{self.base_url}/v1/ai/decide", request)

    async def _send_request(self, url: str, request: AIRequest) -> AIResponse:
        self.event_bus.publish(BusEvent.AI_REQUEST_SENT, source="ai_client", data={"request_id": request.request_id, "task": request.task_type})
        
        for attempt in range(self.max_retries):
            try:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    response = await client.post(url, json=request.model_dump(mode="json"))
                    response.raise_for_status()
                    
                    data = response.json()
                    ai_response = AIResponse.model_validate(data)
                    
                    self.event_bus.publish(BusEvent.AI_RESPONSE_RECEIVED, source="ai_client", data={
                        "request_id": request.request_id,
                        "success": ai_response.success
                    })
                    return ai_response
                    
            except httpx.HTTPStatusError as e:
                logger.error(f"HTTP error {e.response.status_code} from AI model server: {e.response.text}")
            except httpx.RequestError as e:
                logger.error(f"Network error communicating with AI model server: {e}")
            except Exception as e:
                logger.error(f"Unexpected error in AI model client: {e}")
            
            if attempt < self.max_retries - 1:
                sleep_time = 2 ** attempt
                logger.info(f"Retrying in {sleep_time} seconds (attempt {attempt + 1}/{self.max_retries})...")
                await asyncio.sleep(sleep_time)
        
        logger.error(f"AI model request failed after {self.max_retries} attempts.")
        self.event_bus.publish(BusEvent.AI_UNAVAILABLE, source="ai_client", data={"request_id": request.request_id})
        return AIResponse(
            request_id=request.request_id,
            success=False,
            error_message="AI model server unavailable after retries",
            content=None
        )
