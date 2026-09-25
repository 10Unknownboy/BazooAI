from __future__ import annotations
import logging
import random
from typing import List, Optional, Any

from app.models.song import Song
from app.config.settings import get_settings

logger = logging.getLogger(__name__)

class ExplorationManager:
    """Manages the exploration vs exploitation trade-off."""

    def __init__(self):
        settings = get_settings()
        self.exploration_rate = getattr(settings, 'exploration_rate', 0.10)
        self.min_exploration_score = getattr(settings, 'min_exploration_score', 0.5)

    def should_explore(self) -> bool:
        """Determine if we should explore on this turn."""
        return random.random() < self.exploration_rate

    def select_exploration_candidate(self, candidates: List[Song], policy_engine: Any, event_state: Any) -> Optional[Song]:
        """Select a lower-ranked but valid candidate for exploration."""
        if not candidates:
            return None
            
        # Filter candidates that pass the policy engine
        valid_candidates = []
        for c in candidates:
            try:
                # Assuming policy engine returns a result object or throws
                result = policy_engine.evaluate(c, event_state)
                if getattr(result, 'is_allowed', True):
                    # In a real impl, we might check scoring engine to ensure it meets min threshold
                    valid_candidates.append(c)
            except Exception:
                pass
                
        if len(valid_candidates) < 2:
            return None
            
        # Exclude the top candidate (exploitation)
        # Assuming candidates is sorted by score descending
        exploration_pool = valid_candidates[1:]
        
        if not exploration_pool:
            return None
            
        # Pick a random candidate from the valid pool
        selected = random.choice(exploration_pool)
        logger.info(f"Selected {selected.title} for exploration")
        return selected
