from __future__ import annotations
import os
import httpx
import logging
import asyncio
import time
from typing import Optional, Dict, Any

from app.models.agent import AIRequest, AIResponse
from app.event.event_bus import get_event_bus, BusEvent
from app.config.settings import get_settings

logger = logging.getLogger(__name__)

class AIModelClient:
    """Client for communicating with the remote AI model server."""
    
    def __init__(self, timeout_seconds: int | None = None, max_retries: int | None = None):
        self.settings = get_settings()
        self.base_url = os.getenv("AI_MODEL_URL", self.settings.ai_model.url).rstrip("/")
        
        self.timeout = timeout_seconds or self.settings.ai_model.timeout
        self.max_retries = max_retries or self.settings.ai_model.retries
        self.event_bus = get_event_bus()

    async def check_health(self) -> bool:
        """Check if the model server is available."""
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(f"{self.base_url}/health")
                response.raise_for_status()
                health = response.json()
                available = (
                    health.get("status") == "ok"
                    and health.get("active_backend") != "mock"
                )
                if not available:
                    self.event_bus.publish(
                        BusEvent.AI_UNAVAILABLE,
                        source="ai_client",
                        data={"reason": "AI server is running without an active model backend"},
                    )
                return available
        except Exception as e:
            logger.warning(f"AI model server health check failed: {e}")
            self.event_bus.publish(BusEvent.AI_UNAVAILABLE, source="ai_client", data={"error": str(e)})
            return False

    async def decide(self, request: AIRequest) -> AIResponse:
        """Send a structured request to the AI model and get a response."""
        return await self._send_request(f"{self.base_url}/v1/ai/decide", request)

    async def generate(self, prompt: str, context: Optional[Dict[str, Any]] = None) -> AIResponse:
        """Generate a generic response based on a prompt."""
        from app.models.base import AIMessageType
        request = AIRequest(
            message_type=AIMessageType.DJ_DECISION,
            request_data={"prompt": prompt, "context": context or {}}
        )
        return await self._send_request(f"{self.base_url}/v1/ai/decide", request)

    async def classify(self, data: Dict[str, Any], schema: Optional[Dict[str, Any]] = None) -> AIResponse:
        """Classify data using the AI model."""
        from app.models.base import AIMessageType
        request = AIRequest(
            message_type=AIMessageType.DJ_DECISION,
            request_data={"data": data, "schema": schema, "prompt": "Classify the following data."}
        )
        return await self._send_request(f"{self.base_url}/v1/ai/decide", request)

    async def _send_request(self, url: str, request: AIRequest) -> AIResponse:
        self.event_bus.publish(
            BusEvent.AI_REQUEST_SENT,
            source="ai_client",
            data={"request_id": request.request_id, "task": request.message_type.value},
        )
        last_error = "AI model request failed"

        for attempt in range(self.max_retries):
            attempt_started = time.perf_counter()
            try:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    self.event_bus.publish(
                        BusEvent.HTTP_REQUEST,
                        source="ai_client",
                        data={"method": "POST", "url": url, "attempt": attempt + 1},
                    )
                    response = await client.post(url, json=request.model_dump(mode="json"))
                    latency_ms = (time.perf_counter() - attempt_started) * 1000
                    self.event_bus.publish(
                        BusEvent.HTTP_RESPONSE,
                        source="ai_client",
                        data={"status_code": response.status_code, "latency_ms": latency_ms},
                    )
                    response.raise_for_status()
                    
                    data = response.json()
                    ai_response = AIResponse.model_validate(data)
                    
                    self.event_bus.publish(
                        BusEvent.AI_RESPONSE_RECEIVED,
                        source="ai_client",
                        data={
                            "request_id": request.request_id,
                            "success": ai_response.success,
                            "latency_ms": latency_ms,
                            "model": ai_response.model_name,
                        },
                    )
                    if ai_response.success:
                        self.event_bus.publish(
                            BusEvent.CONNECTION_STATE_CHANGED,
                            source="ai_client",
                            data={"state": "connected"},
                        )
                    else:
                        self.event_bus.publish(
                            BusEvent.AI_UNAVAILABLE,
                            source="ai_client",
                            data={
                                "request_id": request.request_id,
                                "reason": ai_response.error or "AI server reported no active model",
                            },
                        )
                    return ai_response
                    
            except httpx.HTTPStatusError as e:
                last_error = f"AI model server returned HTTP {e.response.status_code}"
                logger.error(last_error)
                if e.response.status_code == 429:
                    self.event_bus.publish(
                        BusEvent.RATE_LIMIT_EXCEEDED,
                        source="ai_client",
                        data={"status_code": e.response.status_code},
                    )
            except httpx.RequestError as e:
                last_error = f"Network error communicating with AI model server: {e}"
                logger.error(last_error)
                self.event_bus.publish(
                    BusEvent.CONNECTION_STATE_CHANGED,
                    source="ai_client",
                    data={"state": "disconnected", "error": str(e)},
                )
            except Exception as e:
                last_error = f"Unexpected error in AI model client: {e}"
                logger.error(last_error)
            
            if attempt < self.max_retries - 1:
                sleep_time = 2 ** attempt
                logger.info(f"Retrying in {sleep_time} seconds (attempt {attempt + 1}/{self.max_retries})...")
                self.event_bus.publish(
                    BusEvent.RETRY_ATTEMPT,
                    source="ai_client",
                    data={"attempt": attempt + 2, "target": url},
                )
                await asyncio.sleep(sleep_time)
        
        logger.error(f"AI model request failed after {self.max_retries} attempts.")
        self.event_bus.publish(
            BusEvent.AI_UNAVAILABLE,
            source="ai_client",
            data={"request_id": request.request_id, "reason": last_error},
        )
        return AIResponse(
            request_id=request.request_id,
            message_type=request.message_type,
            success=False,
            error=last_error,
        )
