from __future__ import annotations
import logging
import json
import os
from typing import List, Dict, Any

logger = logging.getLogger(__name__)

class RewardRecord:
    def __init__(self, state, action, reward, next_state, context):
        self.state = state
        self.action = action
        self.reward = reward
        self.next_state = next_state
        self.context = context

    def to_dict(self):
        return {
            "state": self.state,
            "action": self.action,
            "reward": self.reward,
            "next_state": self.next_state,
            "context": self.context
        }

class LongTermStore:
    """Manages the long-term learning dataset."""

    def __init__(self, reward_repo):
        self.repo = reward_repo

    def save_record(self, state: Dict, action: Dict, reward: float, next_state: Dict, context: Dict) -> RewardRecord:
        """Save a complete MDP tuple."""
        record = RewardRecord(state, action, reward, next_state, context)
        self.repo.save_reward_record(record.to_dict())
        return record

    def get_records(self, event_type: str, limit: int = 1000) -> List[RewardRecord]:
        """Retrieve recent records for an event type."""
        raw_records = self.repo.get_reward_records(event_type, limit)
        return [RewardRecord(**r) for r in raw_records]

    def export_dataset(self, filepath: str) -> None:
        """Export the dataset as JSON Lines for ML training."""
        records = self.repo.get_all_reward_records()
        
        # Ensure directory exists
        os.makedirs(os.path.dirname(os.path.abspath(filepath)), exist_ok=True)
        
        with open(filepath, 'w', encoding='utf-8') as f:
            for record in records:
                f.write(json.dumps(record) + '\n')
                
        logger.info(f"Exported {len(records)} records to {filepath}")
