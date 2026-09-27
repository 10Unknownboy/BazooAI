from __future__ import annotations

import asyncio
import logging
from concurrent.futures import TimeoutError
from typing import Any

from pydantic import BaseModel

from app.agents.orchestrator import DJOrchestrator
from app.event.event_bus import BusEvent, get_event_bus, get_runtime_state
from app.models.agent import ScoringSnapshot
from app.models.base import VibePreset
from app.playback.playback_controller import PlaybackController

logger = logging.getLogger(__name__)


class CommandResult(BaseModel):
    success: bool
    message: str
    data: Any | None = None


class CommandHandler:
    """
    Parses and dispatches console commands.
    Updates event state and notifies AI/orchestrator via BusEvents.
    """

    def __init__(
        self,
        playback: PlaybackController | None = None,
        orchestrator: DJOrchestrator | None = None,
        loop: asyncio.AbstractEventLoop | None = None,
    ) -> None:
        self.bus = get_event_bus()
        self.state = get_runtime_state()
        self.playback = playback
        self.orchestrator = orchestrator
        self.loop = loop

    def _playback_command(self, action: str, *args) -> CommandResult:
        if not self.playback:
            return CommandResult(
                success=False,
                message=(
                    "Playback runtime is unavailable; start the console with a "
                    "configured event."
                ),
            )
        try:
            succeeded = getattr(self.playback, action)(*args)
        except (ValueError, RuntimeError) as error:
            return CommandResult(success=False, message=str(error))
        if not succeeded:
            return CommandResult(
                success=False,
                message=self.playback.last_error or f"Playback {action} failed.",
            )
        return CommandResult(success=True, message=f"Playback {action} completed.")

    def _orchestrator_command(self, command: dict[str, Any]) -> CommandResult:
        if not self.orchestrator or not self.loop or not self.loop.is_running():
            return CommandResult(success=False, message="DJ orchestrator is unavailable.")
        try:
            future = asyncio.run_coroutine_threadsafe(
                self.orchestrator.handle_command(command), self.loop
            )
            future.result(timeout=90)
        except (TimeoutError, RuntimeError) as error:
            return CommandResult(success=False, message=f"DJ command failed: {error}")
        return CommandResult(success=True, message="DJ command applied.")

    def parse_command(self, input_str: str) -> tuple[str, list[str]]:
        """Parses raw input string into command and arguments."""
        if not input_str:
            return "", []

        import shlex

        try:
            parts = shlex.split(input_str)
            return parts[0].lower(), parts[1:]
        except ValueError as e:
            logger.error(f"Error parsing command: {e}")
            return "", []

    def dispatch(self, command: str, args: list[str]) -> CommandResult:
        """Dispatches the command to the appropriate handler."""
        handler_name = f"handle_{command}"
        if hasattr(self, handler_name):
            try:
                result = getattr(self, handler_name)(args)
                if self.orchestrator is None:
                    self.bus.publish(
                        BusEvent.COMMAND_EXECUTED,
                        source="command_handler",
                        data={
                            "command": command,
                            "args": args,
                            "result": result.model_dump(),
                        },
                    )
                return result
            except Exception as e:
                logger.error(f"Error executing command {command}: {e}", exc_info=True)
                return CommandResult(
                    success=False, message=f"Internal error executing {command}: {e}"
                )
        else:
            return CommandResult(
                success=False,
                message=f"Unknown command: {command}. Type 'help' for available commands.",
            )

    # Static commands
    def handle_play(self, args: list[str]) -> CommandResult:
        return self._playback_command("resume")

    def handle_resume(self, args: list[str]) -> CommandResult:
        return self.handle_play(args)

    def handle_pause(self, args: list[str]) -> CommandResult:
        return self._playback_command("pause")

    def handle_stop(self, args: list[str]) -> CommandResult:
        return self._playback_command("stop")

    def handle_skip(self, args: list[str]) -> CommandResult:
        return self._playback_command("skip")

    def handle_previous(self, args: list[str]) -> CommandResult:
        return self._playback_command("previous")

    def handle_volume(self, args: list[str]) -> CommandResult:
        if not args:
            return CommandResult(success=False, message="Usage: volume <0-100>")
        try:
            vol = int(args[0])
            if 0 <= vol <= 100:
                result = self._playback_command("volume", vol)
                if result.success:
                    self.bus.publish(
                        BusEvent.VOLUME_CHANGED,
                        source="command_handler",
                        data={"volume": vol},
                    )
                return result
            return CommandResult(success=False, message="Volume must be between 0 and 100.")
        except ValueError:
            return CommandResult(success=False, message="Invalid volume value.")

    def handle_seek(self, args: list[str]) -> CommandResult:
        if not args:
            return CommandResult(success=False, message="Usage: seek <seconds>")
        try:
            sec = int(args[0])
            if sec < 0:
                return CommandResult(success=False, message="Seek position cannot be negative.")
            result = self._playback_command("seek", sec)
            if result.success:
                self.bus.publish(
                    BusEvent.SEEK_REQUESTED,
                    source="command_handler",
                    data={"seconds": sec},
                )
            return result
        except ValueError:
            return CommandResult(success=False, message="Invalid seconds value.")

    def handle_queue(self, args: list[str]) -> CommandResult:
        if not args:
            return CommandResult(
                success=True, message="Displaying queue...", data=self.state.get_queue_state()
            )
        subcmd = args[0].lower()
        if subcmd == "add":
            query = " ".join(args[1:])
            if not query:
                return CommandResult(success=False, message="Usage: queue add <song query>")
            if not self.orchestrator:
                return CommandResult(success=False, message="DJ orchestrator is unavailable.")
            state = self.orchestrator.get_state()
            if not state:
                return CommandResult(success=False, message="Start an event before adding tracks.")
            matches = self.orchestrator.candidate_generator.find_local_matches(query, limit=5)
            if not matches:
                return CommandResult(
                    success=False, message=f"No playable local match for {query!r}."
                )
            song = matches[0]
            policy = self.orchestrator.policy_engine.check_song(song, state)
            if not policy.passed:
                return CommandResult(
                    success=False,
                    message="Track rejected by event policy: " + "; ".join(policy.violations),
                )
            if any(item.song_id == song.song_id for item in self.orchestrator.queue_manager.items):
                return CommandResult(success=False, message="Track is already in the queue.")
            scored = self.orchestrator.scoring_engine.score_candidate(song, state)
            item = self.orchestrator.queue_manager.add_song(
                song_id=song.song_id,
                score=scored.final_score,
                components=scored.score_components,
                song_title=song.title,
                song_artist=song.artist,
                song_genre=song.genre,
                decision_epoch=state.decision_epoch,
                penalty_components=scored.penalty_components,
            )
            if item is None:
                return CommandResult(success=False, message="Track could not be added.")
            self.orchestrator.current_state.queue = [
                queued.song_id for queued in self.orchestrator.queue_manager.items
            ]
            self.orchestrator.decision_repository.save_scoring_snapshot(
                ScoringSnapshot(
                    event_id=state.event_id,
                    decision_epoch=state.decision_epoch,
                    song_id=song.song_id,
                    final_score=scored.final_score,
                    score_components=scored.score_components,
                    penalty_components=scored.penalty_components,
                    scoring_weights=self.orchestrator.scoring_engine.weights,
                    penalty_weights=self.orchestrator.scoring_engine.penalty_weights,
                    policy_passed=True,
                    event_state_snapshot=state.model_dump(mode="json"),
                    agent_recommendations={"source": "manual_queue_add"},
                    candidate_features=song.model_dump(
                        mode="json",
                        exclude={"audio_features", "lyrics_features"},
                    ),
                )
            )
            self.orchestrator._publish_runtime_state()
            return CommandResult(success=True, message=f"Queued {song.title} — {song.artist}.")
        elif subcmd == "remove":
            pos = int(args[1]) if len(args) > 1 and args[1].isdigit() else -1
            if pos > 0 and self.orchestrator:
                if not self.orchestrator.current_state:
                    return CommandResult(
                        success=False, message="Start an event before editing the queue."
                    )
                if self.orchestrator.queue_manager.remove_at(pos - 1):
                    self.orchestrator.current_state.queue = [
                        item.song_id for item in self.orchestrator.queue_manager.items
                    ]
                    self.orchestrator._publish_runtime_state()
                    return CommandResult(success=True, message=f"Removed queue position {pos}.")
                return CommandResult(
                    success=False,
                    message="That queue position does not exist or is locked.",
                )
            return CommandResult(success=False, message="Invalid position.")
        elif subcmd == "clear":
            if not self.orchestrator:
                return CommandResult(success=False, message="DJ orchestrator is unavailable.")
            if not self.orchestrator.current_state:
                return CommandResult(
                    success=False, message="Start an event before clearing the queue."
                )
            removed = 0
            for position in reversed(self.orchestrator.queue_manager.get_flexible_positions()):
                removed += int(self.orchestrator.queue_manager.remove_at(position))
            self.orchestrator.current_state.queue = [
                item.song_id for item in self.orchestrator.queue_manager.items
            ]
            self.orchestrator._publish_runtime_state()
            return CommandResult(
                success=True,
                message=f"Removed {removed} unlocked future queue item(s); locked songs remain.",
            )
        return CommandResult(success=False, message=f"Unknown queue subcommand: {subcmd}")

    def handle_event(self, args: list[str]) -> CommandResult:
        if not args:
            return CommandResult(success=False, message="Usage: event <pause|resume|end>")
        subcmd = args[0].lower()
        if subcmd == "pause":
            playback_result = self._playback_command("pause")
            if not playback_result.success:
                return playback_result
            return self._orchestrator_command({"command": "event_pause"})
        elif subcmd == "resume":
            playback_result = self._playback_command("resume")
            if not playback_result.success:
                return playback_result
            return self._orchestrator_command({"command": "event_resume"})
        elif subcmd == "end":
            playback_result = self._playback_command("stop")
            if not playback_result.success:
                return playback_result
            return self._orchestrator_command({"command": "event_end"})
        return CommandResult(success=False, message=f"Unknown event subcommand: {subcmd}")

    # AI-driven commands
    def handle_vibe(self, args: list[str]) -> CommandResult:
        if not args:
            return CommandResult(success=False, message="Usage: vibe <preset>")
        preset = args[0].lower()
        try:
            VibePreset(preset)
        except ValueError:
            return CommandResult(success=False, message=f"Unknown vibe preset: {preset}.")
        if self.orchestrator and self.loop:
            return self._orchestrator_command({"command": "vibe", "args": [preset]})
        self.bus.publish(
            BusEvent.VIBE_CHANGE_REQUESTED,
            source="command_handler",
            data={"preset": preset},
        )
        return CommandResult(success=True, message=f"Requested vibe change to: {preset}")

    def handle_energy(self, args: list[str]) -> CommandResult:
        if not args:
            return CommandResult(success=False, message="Usage: energy <value>")
        val_str = args[0]
        try:
            if val_str.startswith("+") or val_str.startswith("-"):
                val = int(val_str)
                if not -100 <= val <= 100:
                    return CommandResult(
                        success=False, message="Energy delta must be between -100 and 100."
                    )
                if self.orchestrator and self.loop:
                    return self._orchestrator_command({"command": "energy", "args": [val_str]})
                self.bus.publish(
                    BusEvent.ENERGY_CHANGE_RELATIVE, source="command_handler", data={"delta": val}
                )
                return CommandResult(success=True, message=f"Requested energy change by {val}")
            else:
                val = int(val_str)
                if not 0 <= val <= 100:
                    return CommandResult(success=False, message="Energy must be between 0 and 100.")
                if self.orchestrator and self.loop:
                    return self._orchestrator_command({"command": "energy", "args": [val_str]})
                self.bus.publish(
                    BusEvent.ENERGY_CHANGE_ABSOLUTE, source="command_handler", data={"value": val}
                )
                return CommandResult(success=True, message=f"Requested energy set to {val}")
        except ValueError:
            return CommandResult(success=False, message="Invalid energy value.")

    def handle_request(self, args: list[str]) -> CommandResult:
        if not args:
            return CommandResult(success=False, message='Usage: request "<song name>"')
        song_name = " ".join(args)
        from app.models.request import SongRequest

        request = SongRequest(requested_song_query=song_name, requester="console")
        self.bus.publish(
            BusEvent.REQUEST_RECEIVED,
            source="command_handler",
            data={"request": request.model_dump(mode="json")},
        )
        return CommandResult(success=True, message=f"Song request submitted: {song_name}")

    def handle_feedback(self, args: list[str]) -> CommandResult:
        if not args:
            return CommandResult(
                success=False,
                message="Usage: feedback <1-10> [energy] [song_choice] [transition] [vibe]",
            )
        try:
            if len(args) not in (1, 5):
                return CommandResult(
                    success=False, message="Provide either one rating or all five ratings."
                )
            event_state = self.state.get_event_state() or {}
            if not event_state.get("event_id") or not event_state.get("current_song_id"):
                return CommandResult(
                    success=False, message="Feedback requires an active event and a current song."
                )
            from app.models.feedback import SongFeedback

            ratings = [int(value) for value in args]
            feedback = SongFeedback(
                event_id=event_state["event_id"],
                song_id=event_state["current_song_id"],
                overall_rating=ratings[0],
                energy_rating=ratings[1] if len(ratings) == 5 else None,
                song_choice_rating=ratings[2] if len(ratings) == 5 else None,
                transition_rating=ratings[3] if len(ratings) == 5 else None,
                vibe_rating=ratings[4] if len(ratings) == 5 else None,
                current_energy=event_state.get("current_energy"),
                decision_epoch=event_state.get("decision_epoch", 0),
            )
            self.bus.publish(
                BusEvent.FEEDBACK_RECEIVED,
                source="command_handler",
                data={"feedback": feedback.model_dump(mode="json")},
            )
            return CommandResult(success=True, message="Feedback submitted.")
        except ValueError:
            return CommandResult(success=False, message="Invalid feedback values.")

    def handle_status(self, args: list[str]) -> CommandResult:
        return CommandResult(
            success=True, message="Current status", data=self.state.get_event_state()
        )

    def handle_history(self, args: list[str]) -> CommandResult:
        state = self.state.get_event_state() or {}
        return CommandResult(
            success=True, message="Play history", data=state.get("recent_history", [])
        )

    def handle_scores(self, args: list[str]) -> CommandResult:
        return CommandResult(
            success=True, message="Scoring details are available in the Debug Console."
        )

    def handle_why(self, args: list[str]) -> CommandResult:
        return CommandResult(
            success=True, message="Decision details are available in the Debug Console."
        )

    def handle_agents(self, args: list[str]) -> CommandResult:
        return CommandResult(
            success=True, message="Agent statuses", data=self.state.get_agent_statuses()
        )

    def handle_learning(self, args: list[str]) -> CommandResult:
        return CommandResult(
            success=True, message="Learning stats are not yet exposed by RuntimeState."
        )

    def handle_help(self, args: list[str]) -> CommandResult:
        from app.console.help_system import HelpSystem

        hs = HelpSystem()
        hs.show_help(args[0] if args else None)
        return CommandResult(success=True, message="Help displayed.")
