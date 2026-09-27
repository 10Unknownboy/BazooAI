from __future__ import annotations
import logging
import asyncio
from typing import Optional, Dict, Any, List

from app.models.event import EventState, EventConfig
from app.models.agent import AgentDecision
from app.event.event_bus import get_event_bus, get_runtime_state, BusEvent
from app.config.settings import get_settings

from app.agents.vibe_agent import VibeAgent
from app.agents.song_selection_agent import SongSelectionAgent, ScoredCandidate
from app.agents.request_agent import RequestAgent
from app.agents.learning_agent import LearningAgent
from app.ranking.candidate_generator import CandidateGenerator
from app.ranking.scoring_engine import ScoringEngine
from app.policies.policy_engine import PolicyEngine
from app.queue.queue_manager import QueueManager
from app.models.request import SongRequest
from app.models.feedback import SongFeedback

logger = logging.getLogger(__name__)

class DJOrchestrator:
    """Central coordinator for the AI DJ system."""
    
    def __init__(self):
        self.settings = get_settings()
        self.event_bus = get_event_bus()
        self.runtime_state = get_runtime_state()
        self.current_state: Optional[EventState] = None
        self.is_running = False
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        
        # Instantiate agents and engines
        self.vibe_agent = VibeAgent()
        self.song_selection_agent = SongSelectionAgent()
        self.request_agent = RequestAgent()
        self.learning_agent = LearningAgent()
        self.candidate_generator = CandidateGenerator()
        self.scoring_engine = ScoringEngine()
        self.policy_engine = PolicyEngine()
        self.queue_manager = QueueManager()
        
        # Subscribe to events
        self.event_bus.subscribe(BusEvent.SONG_STARTED, self._on_song_started)
        self.event_bus.subscribe(BusEvent.SONG_ENDED, self._on_song_ended)
        self.event_bus.subscribe(BusEvent.REQUEST_RECEIVED, self._on_request_received)
        self.event_bus.subscribe(BusEvent.REQUEST_DECIDED, self._on_request_decided)
        self.event_bus.subscribe(BusEvent.FEEDBACK_RECEIVED, self._on_feedback_received)
        self.event_bus.subscribe(BusEvent.QUEUE_UPDATED, self._on_queue_updated)

    async def start(self, event_config: EventConfig) -> None:
        """Start the DJ session with the given configuration."""
        self._loop = asyncio.get_running_loop()
        logger.info(f"Starting DJ Orchestrator for event: {event_config.event_id}")
        self.current_state = EventState(
            event_id=event_config.event_id,
            event_config=event_config
        )
        self.is_running = True
        
        # Initial decision cycle
        await self.run_decision_cycle("event_start")

    async def stop(self) -> None:
        """Stop the DJ session."""
        logger.info("Stopping DJ Orchestrator")
        self.is_running = False
        self.current_state = None
        self._loop = None

    def get_state(self) -> Optional[EventState]:
        """Get the current event state."""
        return self.current_state

    async def handle_command(self, cmd: Dict[str, Any]) -> None:
        """Handle a manual command from the user interface."""
        logger.info(f"Received manual command: {cmd}")
        # Process command and run decision cycle
        await self.run_decision_cycle("manual_command")

    async def run_decision_cycle(self, trigger: str) -> None:
        """Run the main decision loop based on a trigger."""
        if not self.is_running or not self.current_state:
            return
            
        logger.info(f"Running decision cycle triggered by: {trigger}")
        
        # Advance epoch
        self.current_state.advance_epoch()
        
        # 1. Update Vibe
        vibe_rec = await self.vibe_agent.evaluate_vibe(self.current_state)
        self.current_state.vibe_vector = vibe_rec.recommended_vibe
        
        # 2. Check Queue
        if self.queue_manager.needs_refill():
            # 3. Generate Candidates
            exclude_ids = self.current_state.recent_history + [item.song_id for item in self.queue_manager.items]
            candidates = self.candidate_generator.get_candidates(self.current_state, exclude_ids=exclude_ids)
            
            # Inject requested songs
            req_song_ids = []
            for req_id in self.current_state.accepted_requests:
                if req_id in self.request_agent.requests:
                    req = self.request_agent.requests[req_id]
                    if req.matched_song_id and req.matched_song_id not in exclude_ids:
                        req_song_ids.append(req.matched_song_id)
                        # Fetch the song if not already in candidates
                        if not any(c.song_id == req.matched_song_id for c in candidates):
                            song = self.candidate_generator.song_repo.get(req.matched_song_id)
                            if song:
                                candidates.append(song)
            
            # 4. Apply Policies
            valid_candidates = []
            for c in candidates:
                pol_res = self.policy_engine.check_song(c, self.current_state)
                if pol_res.passed:
                    valid_candidates.append(c)
            
            # 5. Score Candidates
            scored_candidates = []
            for c in valid_candidates:
                score_res = self.scoring_engine.score_candidate(c, self.current_state)
                adjustment = self.learning_agent.get_learned_adjustment(c, self.current_state)
                final_score = score_res.final_score + adjustment
                
                if c.song_id in req_song_ids:
                    final_score += 100.0  # Big boost for requested songs
                    
                scored_candidates.append(ScoredCandidate(song=c, score=final_score, breakdown=score_res.score_components))
                
            # 6. Select Songs
            needed = self.queue_manager._lookahead_size - len(self.queue_manager.items)
            if needed > 0 and scored_candidates:
                selected = await self.song_selection_agent.select_songs(self.current_state, scored_candidates, top_n=needed)
                
                # 7. Update Queue
                for sc in selected:
                    title = getattr(sc.song, 'title', 'Unknown')
                    artist = getattr(sc.song, 'artist', 'Unknown')
                    self.queue_manager.add_song(
                        song_id=sc.song.song_id,
                        score=sc.score,
                        components=sc.breakdown,
                        song_title=title,
                        song_artist=artist,
                        decision_epoch=self.current_state.decision_epoch
                    )
                    
            # Sync queue state to current_state
            self.current_state.queue = [item.song_id for item in self.queue_manager.items]
        
        # Publish state update
        self.event_bus.publish(BusEvent.EVENT_STATE_UPDATED, source="orchestrator", data={"state": self.current_state.model_dump()})
        self.runtime_state.update_event_state(self.current_state.model_dump())

    def _on_song_started(self, payload: Dict[str, Any]) -> None:
        if self.is_running and self.current_state and self._loop:
            logger.info("Song started event received")
            # Update state with playing song
            asyncio.run_coroutine_threadsafe(self.run_decision_cycle("song_begins"), self._loop)

    def _on_song_ended(self, payload: Dict[str, Any]) -> None:
        if self.is_running and self.current_state and self._loop:
            logger.info("Song ended event received")
            # Usually advance the queue
            self.queue_manager.advance()
            asyncio.run_coroutine_threadsafe(self.run_decision_cycle("song_ending"), self._loop)

    def _on_request_received(self, payload: Dict[str, Any]) -> None:
        if self.is_running and self.current_state and self._loop:
            logger.info("Request received event received")
            if "request" in payload:
                try:
                    req = SongRequest(**payload["request"])
                    asyncio.run_coroutine_threadsafe(self.request_agent.evaluate_request(req, self.current_state), self._loop)
                except Exception as e:
                    logger.error(f"Error parsing request: {e}")
            asyncio.run_coroutine_threadsafe(self.run_decision_cycle("request_received"), self._loop)

    def _on_request_decided(self, payload: Dict[str, Any]) -> None:
        if self.is_running and self.current_state and self._loop:
            logger.info("Request decided event received")
            if "decision" in payload:
                try:
                    from app.models.request import RequestDecision
                    from app.models.base import RequestStatus
                    decision = RequestDecision(**payload["decision"])
                    if decision.status == RequestStatus.QUEUED:
                        self.current_state.accepted_requests.append(decision.request_id)
                        asyncio.run_coroutine_threadsafe(self.run_decision_cycle("request_accepted"), self._loop)
                except Exception as e:
                    logger.error(f"Error processing request decision: {e}")

    def _on_feedback_received(self, payload: Dict[str, Any]) -> None:
        if self.is_running and self.current_state and self._loop:
            logger.info("Feedback received event received")
            if "feedback" in payload:
                try:
                    fb = SongFeedback(**payload["feedback"])
                    self.learning_agent.process_feedback(fb, self.current_state)
                except Exception as e:
                    logger.error(f"Error parsing feedback: {e}")
            asyncio.run_coroutine_threadsafe(self.run_decision_cycle("feedback_received"), self._loop)

    def _on_queue_updated(self, payload: Dict[str, Any]) -> None:
        if self.is_running and self.current_state and self._loop:
            logger.info("Queue updated event received")
            if self.queue_manager.needs_refill():
                asyncio.run_coroutine_threadsafe(self.run_decision_cycle("queue_needs_refill"), self._loop)

