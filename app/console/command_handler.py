from __future__ import annotations

import logging
from typing import Any, Tuple, Optional
from pydantic import BaseModel

from app.event.event_bus import get_event_bus, get_runtime_state, BusEvent

logger = logging.getLogger(__name__)

class CommandResult(BaseModel):
    success: bool
    message: str
    data: Optional[Any] = None

class CommandHandler:
    """
    Parses and dispatches console commands.
    Updates event state and notifies AI/orchestrator via BusEvents.
    """
    def __init__(self) -> None:
        self.bus = get_event_bus()
        self.state = get_runtime_state()

    def parse_command(self, input_str: str) -> Tuple[str, list[str]]:
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
                self.bus.publish(
                    BusEvent.COMMAND_EXECUTED,
                    source="command_handler",
                    data={"command": command, "args": args, "result": result.model_dump()},
                )
                return result
            except Exception as e:
                logger.error(f"Error executing command {command}: {e}", exc_info=True)
                return CommandResult(success=False, message=f"Internal error executing {command}: {e}")
        else:
            return CommandResult(success=False, message=f"Unknown command: {command}. Type 'help' for available commands.")

    # Static commands
    def handle_play(self, args: list[str]) -> CommandResult:
        self.bus.publish(BusEvent.PLAYBACK_RESUMED, source="command_handler")
        return CommandResult(success=True, message="Playback resumed.")

    def handle_pause(self, args: list[str]) -> CommandResult:
        self.bus.publish(BusEvent.PLAYBACK_PAUSED, source="command_handler")
        return CommandResult(success=True, message="Playback paused.")
        
    def handle_stop(self, args: list[str]) -> CommandResult:
        self.bus.publish(BusEvent.PLAYBACK_STOPPED, source="command_handler")
        return CommandResult(success=True, message="Playback stopped.")

    def handle_skip(self, args: list[str]) -> CommandResult:
        self.bus.publish(BusEvent.PLAYBACK_SKIPPED, source="command_handler")
        return CommandResult(success=True, message="Skipped to next track.")

    def handle_previous(self, args: list[str]) -> CommandResult:
        self.bus.publish(BusEvent.PLAYBACK_PREVIOUS, source="command_handler")
        return CommandResult(success=True, message="Going to previous track.")

    def handle_volume(self, args: list[str]) -> CommandResult:
        if not args:
            return CommandResult(success=False, message="Usage: volume <0-100>")
        try:
            vol = int(args[0])
            if 0 <= vol <= 100:
                self.bus.publish(BusEvent.VOLUME_CHANGED, source="command_handler", data={"volume": vol})
                return CommandResult(success=True, message=f"Volume set to {vol}.")
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
            self.bus.publish(BusEvent.SEEK_REQUESTED, source="command_handler", data={"seconds": sec})
            return CommandResult(success=True, message=f"Seeking to {sec}s.")
        except ValueError:
            return CommandResult(success=False, message="Invalid seconds value.")

    def handle_queue(self, args: list[str]) -> CommandResult:
        if not args:
            return CommandResult(success=True, message="Displaying queue...", data=self.state.get_queue_state())
        subcmd = args[0].lower()
        if subcmd == "add":
            query = " ".join(args[1:])
            self.bus.publish(BusEvent.QUEUE_ADD_REQUESTED, source="command_handler", data={"query": query})
            return CommandResult(success=True, message=f"Requested to add: {query}")
        elif subcmd == "remove":
            pos = int(args[1]) if len(args) > 1 and args[1].isdigit() else -1
            if pos >= 0:
                self.bus.publish(BusEvent.QUEUE_REMOVE_REQUESTED, source="command_handler", data={"position": pos})
                return CommandResult(success=True, message=f"Requested to remove position: {pos}")
            return CommandResult(success=False, message="Invalid position.")
        elif subcmd == "clear":
            self.bus.publish(BusEvent.QUEUE_CLEAR_REQUESTED, source="command_handler")
            return CommandResult(success=True, message="Requested to clear queue.")
        return CommandResult(success=False, message=f"Unknown queue subcommand: {subcmd}")

    def handle_event(self, args: list[str]) -> CommandResult:
        if not args:
            return CommandResult(success=False, message="Usage: event <pause|resume|end>")
        subcmd = args[0].lower()
        if subcmd == "pause":
            self.bus.publish(BusEvent.EVENT_PAUSED, source="command_handler")
            return CommandResult(success=True, message="Event paused.")
        elif subcmd == "resume":
            self.bus.publish(BusEvent.EVENT_RESUMED, source="command_handler")
            return CommandResult(success=True, message="Event resumed.")
        elif subcmd == "end":
            self.bus.publish(BusEvent.EVENT_ENDED, source="command_handler")
            return CommandResult(success=True, message="Event ended.")
        return CommandResult(success=False, message=f"Unknown event subcommand: {subcmd}")

    # AI-driven commands
    def handle_vibe(self, args: list[str]) -> CommandResult:
        if not args:
            return CommandResult(success=False, message="Usage: vibe <preset>")
        preset = args[0].lower()
        self.bus.publish(BusEvent.VIBE_CHANGE_REQUESTED, source="command_handler", data={"preset": preset})
        return CommandResult(success=True, message=f"Requested vibe change to: {preset}")

    def handle_energy(self, args: list[str]) -> CommandResult:
        if not args:
            return CommandResult(success=False, message="Usage: energy <value>")
        val_str = args[0]
        try:
            if val_str.startswith('+') or val_str.startswith('-'):
                val = int(val_str)
                self.bus.publish(BusEvent.ENERGY_CHANGE_RELATIVE, source="command_handler", data={"delta": val})
                return CommandResult(success=True, message=f"Requested energy change by {val}")
            else:
                val = int(val_str)
                self.bus.publish(BusEvent.ENERGY_CHANGE_ABSOLUTE, source="command_handler", data={"value": val})
                return CommandResult(success=True, message=f"Requested energy set to {val}")
        except ValueError:
            return CommandResult(success=False, message="Invalid energy value.")

    def handle_request(self, args: list[str]) -> CommandResult:
        if not args:
            return CommandResult(success=False, message="Usage: request \"<song name>\"")
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
            return CommandResult(success=False, message="Usage: feedback <1-10> [energy] [song_choice] [transition] [vibe]")
        try:
            if len(args) not in (1, 5):
                return CommandResult(success=False, message="Provide either one rating or all five ratings.")
            event_state = self.state.get_event_state() or {}
            if not event_state.get("event_id") or not event_state.get("current_song_id"):
                return CommandResult(success=False, message="Feedback requires an active event and a current song.")
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
        return CommandResult(success=True, message="Current status", data=self.state.get_event_state())

    def handle_history(self, args: list[str]) -> CommandResult:
        state = self.state.get_event_state() or {}
        return CommandResult(success=True, message="Play history", data=state.get("recent_history", []))

    def handle_scores(self, args: list[str]) -> CommandResult:
        return CommandResult(success=True, message="Scoring details are available in the Debug Console.")

    def handle_why(self, args: list[str]) -> CommandResult:
        return CommandResult(success=True, message="Decision details are available in the Debug Console.")

    def handle_agents(self, args: list[str]) -> CommandResult:
        return CommandResult(success=True, message="Agent statuses", data=self.state.get_agent_statuses())

    def handle_learning(self, args: list[str]) -> CommandResult:
        return CommandResult(success=True, message="Learning stats are not yet exposed by RuntimeState.")

    def handle_help(self, args: list[str]) -> CommandResult:
        from app.console.help_system import HelpSystem
        hs = HelpSystem()
        hs.show_help(args[0] if args else None)
        return CommandResult(success=True, message="Help displayed.")
