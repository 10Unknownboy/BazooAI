from __future__ import annotations
import logging
from typing import Optional, Dict, Any, List

from app.models.request import SongRequest, RequestDecision, RequestStatus
from app.models.event import EventState
from app.models.agent import AIRequest, AIResponse
from app.agents.ai_client import AIModelClient
from app.event.event_bus import get_event_bus, BusEvent

logger = logging.getLogger(__name__)

class RequestAgent:
    """Agent responsible for handling and evaluating song requests."""
    
    def __init__(self, ai_client: Optional[AIModelClient] = None):
        self.ai_client = ai_client or AIModelClient()
        self.event_bus = get_event_bus()
        self.deferred_requests: List[SongRequest] = []

    async def evaluate_request(self, request: SongRequest, event_state: EventState) -> RequestDecision:
        """Evaluate a song request and decide how to handle it."""
        self._update_status(request, RequestStatus.VALIDATING)
        
        # 1. Deterministic Policy Check (e.g. is it blacklisted?)
        self._update_status(request, RequestStatus.POLICY_CHECK)
        # Placeholder policy check
        
        self._update_status(request, RequestStatus.ANALYZING)
        
        try:
            ai_req = AIRequest(
                agent_id="request_agent",
                task_type="request_evaluation",
                context={
                    "event_state": event_state.model_dump(mode="json"),
                    "request": request.model_dump(mode="json")
                },
                prompt="Evaluate if this requested song is appropriate for the current event vibe. Decide: ACCEPT_NOW, QUEUE, DEFER, BRIDGE, REJECT."
            )
            response = await self.ai_client.decide(ai_req)
            
            if response.success and response.content:
                decision_str = response.content.get("decision", "QUEUE")
                reason = response.content.get("reason", "AI decided")
                
                decision = RequestDecision(
                    request_id=request.id,
                    status=self._map_decision_to_status(decision_str),
                    reason=reason
                )
                self._update_status(request, decision.status, reason)
                self.event_bus.publish(BusEvent.REQUEST_DECIDED, source="request_agent", data={"decision": decision.model_dump(mode="json")})
                
                if decision.status == RequestStatus.DEFERRED:
                    self.deferred_requests.append(request)
                    
                return decision
                
        except Exception as e:
            logger.warning(f"AI request evaluation failed: {e}. Falling back to deterministic.")
            
        # Fallback decision
        decision = RequestDecision(
            request_id=request.id,
            status=RequestStatus.QUEUED,
            reason="Fallback to accept and queue"
        )
        self._update_status(request, decision.status, decision.reason)
        self.event_bus.publish(BusEvent.REQUEST_DECIDED, source="request_agent", data={"decision": decision.model_dump(mode="json")})
        return decision

    def _map_decision_to_status(self, decision_str: str) -> RequestStatus:
        mapping = {
            "ACCEPT_NOW": RequestStatus.QUEUED, # Or PLAY_NEXT depending on logic
            "QUEUE": RequestStatus.QUEUED,
            "DEFER": RequestStatus.DEFERRED,
            "BRIDGE": RequestStatus.BRIDGING,
            "REJECT": RequestStatus.REJECTED
        }
        return mapping.get(decision_str.upper(), RequestStatus.QUEUED)

    def _update_status(self, request: SongRequest, status: RequestStatus, reason: Optional[str] = None) -> None:
        request.status = status
        # In a real app, we'd append to request.status_history here
        logger.info(f"Request {request.id} status updated to {status.value}")
