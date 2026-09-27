from __future__ import annotations
import logging
import asyncio
from typing import Optional, Dict, Any, List

from app.models.event import EventState, EventConfig
from app.models.agent import AgentDecision
from app.event.event_bus import BusEvent, BusMessage, get_event_bus, get_runtime_state
from app.config.settings import get_settings

from app.agents.vibe_agent import VibeAgent
from app.agents.song_selection_agent import SongSelectionAgent, ScoredCandidate
from app.agents.request_agent import RequestAgent
from app.agents.learning_agent import LearningAgent
from app.ranking.candidate_generator import CandidateGenerator
from app.ranking.scoring_engine import ScoringEngine
from app.policies.policy_engine import PolicyEngine
from app.queue.queue_manager import QueueManager
from app.models.request import RequestDecision, SongRequest
from app.models.base import PlaybackState, RequestStatus, VibePreset, VibeVector
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
        self.event_bus.subscribe(BusEvent.COMMAND_EXECUTED, self._on_command_executed)

    async def start(self, event_config: EventConfig) -> None:
        """Start the DJ session with the given configuration."""
        self._loop = asyncio.get_running_loop()
        logger.info(f"Starting DJ Orchestrator for event: {event_config.event_id}")
        starting_vibe = VibeVector.from_preset(event_config.starting_vibe)
        self.current_state = EventState(
            event_id=event_config.event_id,
            event_config=event_config,
            current_vibe=event_config.starting_vibe,
            vibe_vector=starting_vibe,
            target_energy=starting_vibe.energy,
            current_energy=starting_vibe.energy,
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
        if not self.current_state:
            return

        command = cmd.get("command")
        args = cmd.get("args", [])
        if command == "vibe" and args:
            try:
                preset = VibePreset(str(args[0]).lower())
            except ValueError:
                logger.warning("Ignoring unknown vibe preset %r", args[0])
                return
            self.current_state.current_vibe = preset
            self.current_state.vibe_vector = VibeVector.from_preset(preset)
            self.current_state.target_energy = self.current_state.vibe_vector.energy
        elif command == "energy" and args:
            try:
                value = float(args[0])
            except ValueError:
                logger.warning("Ignoring invalid energy value %r", args[0])
                return
            if str(args[0]).startswith(("+", "-")):
                value = self.current_state.target_energy + value / 100.0
            else:
                value /= 100.0
            self.current_state.target_energy = min(1.0, max(0.0, value))
        else:
            return

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
        state_snapshot = self.current_state.model_dump(mode="json")
        self.event_bus.publish(
            BusEvent.EVENT_STATE_UPDATED,
            source="orchestrator",
            data={"state": state_snapshot},
        )
        self.runtime_state.update_event_state(state_snapshot)
        self.runtime_state.update_queue_state(self.queue_manager.get_state().model_dump(mode="json"))

    def _on_song_started(self, message: BusMessage) -> None:
        if self.is_running and self.current_state and self._loop:
            logger.info("Song started event received")
            self.current_state.current_song_id = message.data.get("song_id")
            self.current_state.playback_state = PlaybackState.PLAYING
            asyncio.run_coroutine_threadsafe(self.run_decision_cycle("song_begins"), self._loop)

    def _on_song_ended(self, message: BusMessage) -> None:
        if self.is_running and self.current_state and self._loop:
            logger.info("Song ended event received")
            self.current_state.current_song_id = None
            self.current_state.playback_state = PlaybackState.STOPPED
            # Usually advance the queue
            self.queue_manager.advance()
            asyncio.run_coroutine_threadsafe(self.run_decision_cycle("song_ending"), self._loop)

    def _on_request_received(self, message: BusMessage) -> None:
        if self.is_running and self.current_state and self._loop:
            logger.info("Request received event received")
            payload = message.data
            if "request" in payload:
                try:
                    req = SongRequest.model_validate(payload["request"])
                    asyncio.run_coroutine_threadsafe(self.request_agent.evaluate_request(req, self.current_state), self._loop)
                except Exception as e:
                    logger.error(f"Error parsing request: {e}")
            asyncio.run_coroutine_threadsafe(self.run_decision_cycle("request_received"), self._loop)

    def _on_request_decided(self, message: BusMessage) -> None:
        if self.is_running and self.current_state and self._loop:
            logger.info("Request decided event received")
            payload = message.data
            if "decision" in payload and "request" in payload:
                try:
                    decision = RequestDecision.model_validate(payload["decision"])
                    request = SongRequest.model_validate(payload["request"])
                    if decision.request_id != request.request_id:
                        raise ValueError("Request decision ID does not match its request")
                    if request.status == RequestStatus.QUEUED and request.request_id not in self.current_state.accepted_requests:
                        self.current_state.accepted_requests.append(request.request_id)
                        asyncio.run_coroutine_threadsafe(self.run_decision_cycle("request_accepted"), self._loop)
                except Exception as e:
                    logger.error(f"Error processing request decision: {e}")

    def _on_feedback_received(self, message: BusMessage) -> None:
        if self.is_running and self.current_state and self._loop:
            logger.info("Feedback received event received")
            payload = message.data
            if "feedback" in payload:
                try:
                    fb = SongFeedback(**payload["feedback"])
                    self.learning_agent.process_feedback(fb, self.current_state)
                except Exception as e:
                    logger.error(f"Error parsing feedback: {e}")
            asyncio.run_coroutine_threadsafe(self.run_decision_cycle("feedback_received"), self._loop)

    def _on_queue_updated(self, message: BusMessage) -> None:
        if self.is_running and self.current_state and self._loop:
            logger.info("Queue updated event received")
            if self.queue_manager.needs_refill():
                asyncio.run_coroutine_threadsafe(self.run_decision_cycle("queue_needs_refill"), self._loop)

    def _on_command_executed(self, message: BusMessage) -> None:
        if self.is_running and self._loop:
            asyncio.run_coroutine_threadsafe(self.handle_command(message.data), self._loop)
