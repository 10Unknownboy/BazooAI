from __future__ import annotations

import logging

from app.agents.ai_client import AIModelClient
from app.event.event_bus import BusEvent, get_event_bus
from app.models.agent import AIRequest
from app.models.base import AIMessageType, RequestDecisionType, RequestStatus, utc_now
from app.models.event import EventState
from app.models.request import RequestDecision, SongRequest

logger = logging.getLogger(__name__)


class RequestAgent:
    """Agent responsible for handling and evaluating song requests."""

    def __init__(self, ai_client: AIModelClient | None = None):
        self.ai_client = ai_client or AIModelClient()
        self.event_bus = get_event_bus()
        self.deferred_requests: list[SongRequest] = []
        self.requests: dict[str, SongRequest] = {}

    async def evaluate_request(
        self, request: SongRequest, event_state: EventState
    ) -> RequestDecision:
        """Evaluate a request and record each lifecycle transition."""
        self.requests[request.request_id] = request
        self._update_status(request, RequestStatus.VALIDATING)
        self._update_status(request, RequestStatus.POLICY_CHECK)

        if not request.matched_song_id:
            try:
                from app.database.repositories import get_repository

                song_repo = get_repository("song")
                query = request.requested_song_query.casefold()
                for song in song_repo.get_all(limit=100):
                    if query in song.title.casefold() or query in song.artist.casefold():
                        request.matched_song_id = song.song_id
                        break
            except Exception:
                logger.exception(
                    "Failed to search the song catalog for request %s", request.request_id
                )
                return self._finish_request(
                    request,
                    RequestDecisionType.REJECT,
                    "Song catalog lookup failed",
                    1.0,
                    event_state,
                )

        self._update_status(request, RequestStatus.ANALYZING)
        if not request.matched_song_id:
            return self._finish_request(
                request,
                RequestDecisionType.REJECT,
                "No matching song is available in the local library",
                1.0,
                event_state,
            )

        try:
            response = await self.ai_client.decide(
                AIRequest(
                    message_type=AIMessageType.REQUEST_DECISION,
                    request_data={
                        "event_state": event_state.model_dump(mode="json"),
                        "request": request.model_dump(mode="json"),
                        "prompt": (
                            "Evaluate whether this request fits the current event. Choose "
                            "ACCEPT_NOW, QUEUE, DEFER, BRIDGE, or REJECT."
                        ),
                    },
                )
            )
            if response.success:
                proposed = (response.request_decision or response.decision or "").upper()
                try:
                    decision_type = RequestDecisionType(proposed)
                except ValueError:
                    logger.warning("AI returned invalid request decision %r; using QUEUE", proposed)
                else:
                    return self._finish_request(
                        request,
                        decision_type,
                        response.reason or "AI decision",
                        response.confidence,
                        event_state,
                    )
        except Exception:
            logger.exception("AI request evaluation failed for %s", request.request_id)

        return self._finish_request(
            request,
            RequestDecisionType.QUEUE,
            "AI unavailable; queued by deterministic fallback",
            0.0,
            event_state,
        )

    def _finish_request(
        self,
        request: SongRequest,
        decision_type: RequestDecisionType,
        reason: str,
        confidence: float,
        event_state: EventState,
    ) -> RequestDecision:
        request.decision = decision_type
        request.decision_reason = reason
        request.decision_confidence = confidence
        request.decided_at = utc_now()

        self._update_status(request, RequestStatus.DECISION, reason)
        status = self._map_decision_to_status(decision_type)
        self._update_status(request, status, reason)

        if status == RequestStatus.DEFERRED and request not in self.deferred_requests:
            self.deferred_requests.append(request)

        decision = RequestDecision(
            request_id=request.request_id,
            decision=decision_type,
            reason=reason,
            confidence=confidence,
            decision_epoch=event_state.decision_epoch,
            event_id=event_state.event_id,
        )
        self.event_bus.publish(
            BusEvent.REQUEST_DECIDED,
            source="request_agent",
            data={
                "decision": decision.model_dump(mode="json"),
                "request": request.model_dump(mode="json"),
            },
        )
        return decision

    @staticmethod
    def _map_decision_to_status(decision: RequestDecisionType) -> RequestStatus:
        return {
            RequestDecisionType.ACCEPT_NOW: RequestStatus.QUEUED,
            RequestDecisionType.QUEUE: RequestStatus.QUEUED,
            RequestDecisionType.DEFER: RequestStatus.DEFERRED,
            RequestDecisionType.BRIDGE: RequestStatus.BRIDGING,
            RequestDecisionType.REJECT: RequestStatus.REJECTED,
        }[decision]

    @staticmethod
    def _update_status(
        request: SongRequest,
        status: RequestStatus,
        reason: str = "",
    ) -> None:
        if request.status != status:
            request.transition_to(status, reason=reason, agent="REQUEST_AGENT")
        logger.info("Request %s status updated to %s", request.request_id, status.value)
