from __future__ import annotations

import logging
from typing import List

from app.models.song import Song
from app.models.event import EventState
from app.config.settings import load_policy_config

logger = logging.getLogger(__name__)


class PolicyResult:
    """Result of the hard policy gate."""
    def __init__(self, passed: bool, violations: List[str]):
        self.passed = passed
        self.violations = violations


class PolicyEngine:
    """Hard policy gate for deterministic constraints."""
    
    def __init__(self):
        self.policies = load_policy_config()
        
    def check_song(self, song: Song, event_state: EventState) -> PolicyResult:
        """Check if a song passes all hard policies."""
        violations = []
        try:
            # Example hard policy checks
            if getattr(song, "explicit", False) and not self.policies.get("allow_explicit", True):
                violations.append("Explicit content is not allowed.")
                
            if getattr(song, "artist_id", None) in self.policies.get("blocked_artists", []):
                violations.append("Artist is blocked.")
                
            passed = len(violations) == 0
            return PolicyResult(passed=passed, violations=violations)
        except Exception as e:
            logger.error(f"Error checking policy for {song}: {e}")
            return PolicyResult(False, [f"Error checking policy: {str(e)}"])
