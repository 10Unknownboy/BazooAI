from __future__ import annotations
import logging
from typing import Optional, Dict, Any, List
from pydantic import BaseModel

from app.models.queue import QueueItem
from app.models.base import LockStatus
from app.models.agent import AIRequest, AIResponse
from app.agents.ai_client import AIModelClient
from app.event.event_bus import get_event_bus, BusEvent

logger = logging.getLogger(__name__)

class TransitionIssue(BaseModel):
    index1: int
    index2: int
    issue_type: str
    severity: float
    description: str

class QueueChange(BaseModel):
    action: str
    target_index: int
    new_index: Optional[int] = None
    reason: str

class TransitionAgent:
    """Agent responsible for evaluating and improving transitions between queued songs."""
    
    def __init__(self, ai_client: Optional[AIModelClient] = None):
        self.ai_client = ai_client or AIModelClient()
        self.event_bus = get_event_bus()

    def evaluate_queue_transitions(self, queue_items: List[QueueItem], songs_db: Dict[str, Any]) -> List[TransitionIssue]:
        """Detect issues between consecutive items in the queue."""
        issues = []
        # In a real implementation, this would look at BPM, energy, key, etc.
        # using the deterministic TransitionEngine
        
        # Placeholder deterministic logic
        for i in range(len(queue_items) - 1):
            if queue_items[i].lock_status == LockStatus.LOCKED and queue_items[i+1].lock_status == LockStatus.LOCKED:
                continue # Can't change these anyway
            
            # Simulated check
            if i % 3 == 0:
                issues.append(TransitionIssue(
                    index1=i,
                    index2=i+1,
                    issue_type="bpm_jump",
                    severity=0.8,
                    description="Large BPM jump detected"
                ))
                
        return issues

    async def recommend_improvements(self, queue_items: List[QueueItem], issues: List[TransitionIssue]) -> List[QueueChange]:
        """Use AI to recommend fixes for the detected issues."""
        if not issues:
            return []
            
        try:
            # Only send flexible items to AI
            flexible_items = [
                {"index": i, "song_id": item.song_id} 
                for i, item in enumerate(queue_items) 
                if item.lock_status == LockStatus.FLEXIBLE
            ]
            
            request = AIRequest(
                agent_id="transition_agent",
                task_type="queue_review",
                context={
                    "flexible_items": flexible_items,
                    "issues": [i.model_dump() for i in issues]
                },
                prompt="Given these transition issues, recommend reordering of flexible queue items to fix them. Return a list of actions (e.g. swap)."
            )
            response = await self.ai_client.decide(request)
            
            changes = []
            if response.success and response.content and "changes" in response.content:
                for change_data in response.content["changes"]:
                    changes.append(QueueChange(**change_data))
                    self.event_bus.publish(BusEvent.AGENT_DECISION, source="transition_agent", data={
                        "agent": "transition_agent",
                        "decision": "queue_change",
                        "details": change_data
                    })
                return changes
                
        except Exception as e:
            logger.warning(f"AI transition recommendation failed: {e}")
            
        return []
