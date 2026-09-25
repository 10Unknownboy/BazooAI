from __future__ import annotations

import logging
import time
from typing import List, Dict, Any, Optional

from app.database.repositories import get_repository
from app.models.agent import AgentDecision

logger = logging.getLogger(__name__)


class DecisionLogger:
    """Decision logging system for AI and Engine actions."""
    
    def __init__(self):
        self.repo = get_repository("agent_decision")
        
    def log_decision(self, agent: str, decision_type: str, decision: str, reason: str, confidence: float, context: Dict[str, Any]):
        """Log a decision made by an agent or system."""
        try:
            record = AgentDecision(
                id=f"dec_{int(time.time() * 1000)}",
                agent=agent,
                decision_type=decision_type,
                decision=decision,
                reason=reason,
                confidence=confidence,
                context=context,
                timestamp=time.time()
            )
            self.repo.save(record)
        except Exception as e:
            logger.error(f"Error logging decision: {e}")
            
    def get_latest_decision(self) -> Optional[AgentDecision]:
        """Get the most recently logged decision."""
        try:
            return self.repo.get_latest()
        except Exception as e:
            logger.error(f"Error getting latest decision: {e}")
            return None
            
    def get_decisions_for_song(self, song_id: str) -> List[AgentDecision]:
        """Get decisions related to a specific song."""
        try:
            return self.repo.get_by_context("song_id", song_id)
        except Exception as e:
            logger.error(f"Error getting decisions for song: {e}")
            return []
