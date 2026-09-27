from __future__ import annotations

import asyncio
import logging
from typing import Any

from app.agents.learning_agent import LearningAgent
from app.agents.request_agent import RequestAgent
from app.agents.song_selection_agent import ScoredCandidate, SongSelectionAgent
from app.agents.vibe_agent import VibeAgent
from app.config.settings import get_settings
from app.database.engine import init_database
from app.database.repositories import get_repository
from app.event.event_bus import BusEvent, BusMessage, get_event_bus, get_runtime_state
from app.models.agent import ScoringSnapshot
from app.models.base import PlaybackState, RequestStatus, VibePreset, VibeVector, utc_now
from app.models.event import EventConfig, EventState
from app.models.feedback import SongFeedback, TransitionFeedback
from app.models.request import RequestDecision, SongRequest
from app.policies.policy_engine import PolicyEngine
from app.queue.queue_manager import QueueManager
from app.ranking.candidate_generator import CandidateGenerator
from app.ranking.penalty_engine import PenaltyEngine
from app.ranking.scoring_engine import ScoringEngine
from app.ranking.transition_engine import TransitionEngine

logger = logging.getLogger(__name__)


class DJOrchestrator:
    """Central coordinator for the AI DJ system."""

    def __init__(self, queue_manager: QueueManager | None = None):
        init_database()
        self.settings = get_settings()
        self.event_bus = get_event_bus()
        self.runtime_state = get_runtime_state()
        self.current_state: EventState | None = None
        self.is_running = False
        self._loop: asyncio.AbstractEventLoop | None = None
        self._decision_lock = asyncio.Lock()
        self._subscriptions = []
        self.event_repository = get_repository("event")
        self.decision_repository = get_repository("agent_decision")

        # Instantiate agents and engines
        self.vibe_agent = VibeAgent()
        self.song_selection_agent = SongSelectionAgent()
        self.request_agent = RequestAgent()
        self.learning_agent = LearningAgent()
        self.candidate_generator = CandidateGenerator()
        self.scoring_engine = ScoringEngine()
        self.penalty_engine = PenaltyEngine()
        self.transition_engine = TransitionEngine()
        self.policy_engine = PolicyEngine()
        self.queue_manager = queue_manager or QueueManager()

        self._subscribe_to_events()

    def _subscribe_to_events(self) -> None:
        if self._subscriptions:
            return
        for event_type, callback in (
            (BusEvent.SONG_STARTED, self._on_song_started),
            (BusEvent.SONG_ENDED, self._on_song_ended),
            (BusEvent.PLAYBACK_PAUSED, self._on_playback_state_changed),
            (BusEvent.PLAYBACK_RESUMED, self._on_playback_state_changed),
            (BusEvent.PLAYBACK_STOPPED, self._on_playback_state_changed),
            (BusEvent.REQUEST_RECEIVED, self._on_request_received),
            (BusEvent.REQUEST_DECIDED, self._on_request_decided),
            (BusEvent.FEEDBACK_RECEIVED, self._on_feedback_received),
            (BusEvent.QUEUE_UPDATED, self._on_queue_updated),
            (BusEvent.COMMAND_EXECUTED, self._on_command_executed),
        ):
            self.event_bus.subscribe(event_type, callback)
            self._subscriptions.append((event_type, callback))

    async def start(self, event_config: EventConfig) -> None:
        """Start the DJ session with the given configuration."""
        self._subscribe_to_events()
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
            event_started_at=utc_now(),
            agent_statuses={
                "DJ": "ACTIVE",
                "REQUEST": "IDLE",
                "LYRICS": "IDLE",
                "AUDIO": "IDLE",
                "LEARNING": "ACTIVE",
                "POLICY": "ACTIVE",
            },
        )
        self.is_running = True
        self.queue_manager.clear()
        self.event_repository.save_event(event_config, self.current_state)
        self._publish_runtime_state()

        # Initial decision cycle
        await self.run_decision_cycle("event_start")

    async def stop(self) -> None:
        """Stop the DJ session."""
        logger.info("Stopping DJ Orchestrator")
        self.is_running = False
        if self.current_state:
            self.current_state.is_ended = True
            self.current_state.event_ended_at = utc_now()
            self.current_state.playback_state = PlaybackState.STOPPED
            self.event_repository.save_event(self.current_state.event_config, self.current_state)
            self._publish_runtime_state()
        for event_type, callback in self._subscriptions:
            self.event_bus.unsubscribe(event_type, callback)
        self._subscriptions.clear()
        self._loop = None

    def get_state(self) -> EventState | None:
        """Get the current event state."""
        return self.current_state

    async def handle_command(self, cmd: dict[str, Any]) -> None:
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
        async with self._decision_lock:
            if not self.is_running or not self.current_state:
                return

            logger.info("Running decision cycle triggered by: %s", trigger)
            if self.current_state.event_started_at:
                elapsed = utc_now() - self.current_state.event_started_at
                self.current_state.elapsed_minutes = max(0.0, elapsed.total_seconds() / 60.0)
                self.current_state.update_progress()
            self.current_state.advance_epoch()

            if trigger in {"event_start", "manual_command", "feedback_received"}:
                recommendation = await self.vibe_agent.evaluate_vibe(self.current_state)
                self.current_state.vibe_vector = recommendation.recommended_vibe
                self.current_state.agent_statuses["VIBE"] = "ACTIVE"

            if self.queue_manager.needs_refill():
                await self._refill_queue()

            self.current_state.queue = [item.song_id for item in self.queue_manager.items]
            self.current_state.last_state_update = utc_now()
            self.event_repository.save_state(self.current_state.event_id, self.current_state)
            self._publish_runtime_state()

    async def _refill_queue(self) -> None:
        if not self.current_state:
            return

        state = self.current_state
        exclude_ids = state.recent_history + [item.song_id for item in self.queue_manager.items]
        candidates = self.candidate_generator.get_candidates(state, exclude_ids=exclude_ids)

        requested_song_ids: dict[str, str] = {}
        for request_id in state.accepted_requests:
            request = self.request_agent.requests.get(request_id)
            if request and request.matched_song_id and request.matched_song_id not in exclude_ids:
                requested_song_ids[request.matched_song_id] = request_id
                if not any(song.song_id == request.matched_song_id for song in candidates):
                    song = self.candidate_generator.song_repo.get(request.matched_song_id)
                    if song:
                        candidates.append(song)

        previous_song = (
            self.candidate_generator.song_repo.get(state.current_song_id)
            if state.current_song_id
            else None
        )
        ranked: list[ScoredCandidate] = []
        for song in candidates:
            policy = self.policy_engine.check_song(song, state)
            if not policy.passed:
                self.event_bus.publish(
                    BusEvent.POLICY_VIOLATION,
                    source="policy_engine",
                    data={"song_id": song.song_id, "violations": policy.violations},
                )
                continue

            transition_score = 75.0
            transition_penalty = {}
            if previous_song:
                transition = self.transition_engine.score_transition(previous_song, song)
                transition_score = transition.score * 100.0
                if transition.warnings:
                    transition_penalty["transition_penalty"] = max(
                        0.0, (0.6 - transition.score) * 20.0
                    )

            penalties = self.penalty_engine.calculate_penalties(song, state)
            penalties.update(transition_penalty)
            request_id = requested_song_ids.get(song.song_id)
            result = self.scoring_engine.score_candidate(
                song,
                state,
                transition_score=transition_score,
                penalty_engine_result=penalties,
                request_score=100.0 if request_id else 0.0,
                learned_preference=self.learning_agent.get_learned_adjustment(song, state),
            )
            ranked.append(
                ScoredCandidate(
                    song=song,
                    score=result.final_score,
                    breakdown=result.score_components,
                    penalties=result.penalty_components,
                    request_id=request_id,
                )
            )

        needed = self.queue_manager._lookahead_size - len(self.queue_manager.items)
        if not ranked or needed <= 0:
            if not ranked:
                logger.warning("No policy-compatible songs are available to fill the queue")
            return

        selected = await self.song_selection_agent.select_songs(state, ranked, top_n=needed)
        recommendations = {
            "vibe": state.vibe_vector.model_dump(mode="json"),
            "preferred_genres": state.event_config.prefer_genres,
            "preferred_languages": state.event_config.languages,
        }
        for candidate in selected:
            item = self.queue_manager.add_song(
                song_id=candidate.song.song_id,
                score=candidate.score,
                components=candidate.breakdown,
                penalty_components=candidate.penalties,
                song_title=candidate.song.title,
                song_artist=candidate.song.artist,
                decision_epoch=state.decision_epoch,
                request_id=candidate.request_id,
            )
            if item is None:
                continue

            snapshot = ScoringSnapshot(
                event_id=state.event_id,
                decision_epoch=state.decision_epoch,
                song_id=candidate.song.song_id,
                final_score=candidate.score,
                score_components=candidate.breakdown,
                penalty_components=candidate.penalties,
                scoring_weights=self.scoring_engine.weights,
                penalty_weights=self.scoring_engine.penalty_weights,
                policy_passed=True,
                event_state_snapshot=state.model_dump(mode="json"),
                agent_recommendations=recommendations,
                candidate_features=candidate.song.model_dump(
                    mode="json",
                    exclude={"audio_features", "lyrics_features"},
                ),
            )
            self.decision_repository.save_scoring_snapshot(snapshot)

    def _on_song_started(self, message: BusMessage) -> None:
        if self.is_running and self.current_state and self._loop:
            logger.info("Song started event received")
            future = asyncio.run_coroutine_threadsafe(
                self._record_song_started(message.data.get("song_id")),
                self._loop,
            )
            future.add_done_callback(self._log_background_failure)

    def _on_playback_state_changed(self, message: BusMessage) -> None:
        if self.is_running and self.current_state and self._loop:
            future = asyncio.run_coroutine_threadsafe(
                self._record_playback_state(message.event_type),
                self._loop,
            )
            future.add_done_callback(self._log_background_failure)

    async def _record_playback_state(self, event_type: BusEvent) -> None:
        if not self.current_state:
            return
        if event_type == BusEvent.PLAYBACK_PAUSED:
            self.current_state.playback_state = PlaybackState.PAUSED
        elif event_type == BusEvent.PLAYBACK_RESUMED:
            self.current_state.playback_state = PlaybackState.PLAYING
        elif event_type == BusEvent.PLAYBACK_STOPPED:
            self.current_state.playback_state = PlaybackState.STOPPED
            self.current_state.current_song_id = None
        self.current_state.last_state_update = utc_now()
        self.event_repository.save_state(self.current_state.event_id, self.current_state)
        self._publish_runtime_state()

    async def _record_song_started(self, song_id: str | None) -> None:
        if not self.current_state or not song_id:
            return
        self.current_state.current_song_id = song_id
        self.current_state.current_song_started_at = utc_now()
        self.current_state.playback_state = PlaybackState.PLAYING
        self.event_repository.save_state(self.current_state.event_id, self.current_state)
        self._publish_runtime_state()
        await self.run_decision_cycle("song_begins")

    def _on_song_ended(self, message: BusMessage) -> None:
        if self.is_running and self.current_state and self._loop:
            logger.info("Song ended event received")
            song_id = message.data.get("song_id")
            current_item = self.queue_manager.get_current()
            if song_id and current_item and current_item.song_id == song_id:
                song = self.candidate_generator.song_repo.get(song_id)
                if song:
                    self.current_state.recent_history.append(song_id)
                    self.current_state.recent_artists.append(song.artist)
                    if song.genre:
                        self.current_state.recent_genres.append(song.genre)
                    self.current_state.current_energy = song.effective_energy()
                    self.current_state.songs_played_count += 1
                self.queue_manager.advance()
            self.current_state.current_song_id = None
            self.current_state.playback_state = PlaybackState.STOPPED
            future = asyncio.run_coroutine_threadsafe(
                self.run_decision_cycle("song_ending"),
                self._loop,
            )
            future.add_done_callback(self._log_background_failure)

    def _on_request_received(self, message: BusMessage) -> None:
        if self.is_running and self.current_state and self._loop:
            logger.info("Request received event received")
            future = asyncio.run_coroutine_threadsafe(
                self._process_request(message.data),
                self._loop,
            )
            future.add_done_callback(self._log_background_failure)

    async def _process_request(self, payload: dict[str, Any]) -> None:
        if not self.current_state:
            return
        try:
            request = SongRequest.model_validate(payload["request"])
        except (KeyError, ValueError, TypeError):
            logger.exception("Invalid song request event payload")
            return
        self.current_state.pending_requests.append(request.request_id)
        request.current_vibe = self.current_state.vibe_vector
        request.current_energy = self.current_state.current_energy
        request.current_song_id = self.current_state.current_song_id
        request.recent_song_ids = self.current_state.recent_history[-10:]
        request.event_progress = self.current_state.event_progress
        self._publish_runtime_state()
        await self.request_agent.evaluate_request(request, self.current_state)
        request_repository = get_repository("request")
        request_repository.save(
            {
                "request_id": request.request_id,
                "event_id": self.current_state.event_id,
                "requested_song_query": request.requested_song_query,
                "matched_song_id": request.matched_song_id,
                "requester": request.requester,
                "status": request.status.value,
                "status_history": [
                    entry.model_dump(mode="json") for entry in request.status_history
                ],
                "decision": request.decision.value if request.decision else None,
                "decision_reason": request.decision_reason,
                "decision_confidence": request.decision_confidence,
                "priority": request.priority,
                "target_position": request.target_position,
                "bridge_strategy": (
                    request.bridge_strategy.model_dump(mode="json")
                    if request.bridge_strategy
                    else None
                ),
                "context_json": request.model_dump(mode="json"),
                "created_at": request.created_at,
                "decided_at": request.decided_at,
                "played_at": request.played_at,
            }
        )

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
                    if request.request_id in self.current_state.pending_requests:
                        self.current_state.pending_requests.remove(request.request_id)
                    if (
                        request.status == RequestStatus.QUEUED
                        and request.request_id not in self.current_state.accepted_requests
                    ):
                        self.current_state.accepted_requests.append(request.request_id)
                    elif (
                        request.status == RequestStatus.DEFERRED
                        and request.request_id not in self.current_state.deferred_requests
                    ):
                        self.current_state.deferred_requests.append(request.request_id)
                    elif (
                        request.status == RequestStatus.REJECTED
                        and request.request_id not in self.current_state.rejected_requests
                    ):
                        self.current_state.rejected_requests.append(request.request_id)
                    if request.status == RequestStatus.QUEUED:
                        asyncio.run_coroutine_threadsafe(
                            self.run_decision_cycle("request_accepted"), self._loop
                        )
                    else:
                        self._publish_runtime_state()
                except Exception as e:
                    logger.error(f"Error processing request decision: {e}")

    def _on_feedback_received(self, message: BusMessage) -> None:
        if self.is_running and self.current_state and self._loop:
            logger.info("Feedback received event received")
            future = asyncio.run_coroutine_threadsafe(
                self._process_feedback(message.data),
                self._loop,
            )
            future.add_done_callback(self._log_background_failure)

    async def _process_feedback(self, payload: dict[str, Any]) -> None:
        if not self.current_state:
            return
        try:
            feedback = SongFeedback.model_validate(payload["feedback"])
        except (KeyError, ValueError, TypeError):
            logger.exception("Invalid feedback event payload")
            return

        if feedback.event_id != self.current_state.event_id:
            logger.warning("Ignoring feedback for inactive event %s", feedback.event_id)
            return

        repository = get_repository("feedback")
        repository.save_song_feedback(feedback)
        song = self.candidate_generator.song_repo.get(feedback.song_id)
        queue_item = next(
            (item for item in self.queue_manager.items if item.song_id == feedback.song_id),
            None,
        )
        self.learning_agent.process_feedback(
            feedback,
            self.current_state,
            selected_song=song,
            score=queue_item.final_score if queue_item else feedback.decision_score or 0.0,
            score_components=queue_item.score_components
            if queue_item
            else feedback.score_components,
            penalty_components=queue_item.penalty_components
            if queue_item
            else feedback.penalty_components,
        )

        if feedback.transition_rating is not None and feedback.previous_song_ids:
            previous_id = feedback.previous_song_ids[-1]
            previous_song = self.candidate_generator.song_repo.get(previous_id)
            repository.save_transition_feedback(
                TransitionFeedback(
                    event_id=feedback.event_id,
                    from_song_id=previous_id,
                    to_song_id=feedback.song_id,
                    transition_rating=feedback.transition_rating,
                    from_genre=previous_song.genre if previous_song else None,
                    to_genre=song.genre if song else None,
                    from_energy=previous_song.effective_energy() if previous_song else None,
                    to_energy=song.effective_energy() if song else None,
                    from_bpm=previous_song.effective_bpm() if previous_song else None,
                    to_bpm=song.effective_bpm() if song else None,
                    vibe_at_transition=feedback.current_vibe or self.current_state.vibe_vector,
                    event_progress=feedback.event_progress,
                    decision_epoch=feedback.decision_epoch,
                )
            )

        self.current_state.average_feedback = repository.get_song_feedback_avg(
            self.current_state.event_id
        )
        self.event_repository.save_state(self.current_state.event_id, self.current_state)
        self._publish_runtime_state()
        await self.run_decision_cycle("feedback_received")

    def _on_queue_updated(self, message: BusMessage) -> None:
        if self.is_running and self.current_state and self._loop:
            logger.info("Queue updated event received")
            if self.queue_manager.needs_refill():
                asyncio.run_coroutine_threadsafe(
                    self.run_decision_cycle("queue_needs_refill"), self._loop
                )

    def _on_command_executed(self, message: BusMessage) -> None:
        if self.is_running and self._loop:
            future = asyncio.run_coroutine_threadsafe(self.handle_command(message.data), self._loop)
            future.add_done_callback(self._log_background_failure)

    def _publish_runtime_state(self) -> None:
        if not self.current_state:
            return
        state_snapshot = self.current_state.model_dump(mode="json")
        queue_snapshot = self.queue_manager.get_state().model_dump(mode="json")
        self.event_bus.publish(
            BusEvent.EVENT_STATE_UPDATED,
            source="orchestrator",
            data={"state": state_snapshot},
        )
        self.runtime_state.update_event_state(state_snapshot)
        self.runtime_state.update_queue_state(queue_snapshot)

    @staticmethod
    def _log_background_failure(future: Any) -> None:
        try:
            future.result()
        except Exception:
            logger.exception("Background orchestrator task failed")
