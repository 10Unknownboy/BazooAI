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
                self.bus.publish(BusEvent(type="COMMAND_EXECUTED", payload={"command": command, "args": args, "result": result.model_dump()}))
                return result
            except Exception as e:
                logger.error(f"Error executing command {command}: {e}", exc_info=True)
                return CommandResult(success=False, message=f"Internal error executing {command}: {e}")
        else:
            return CommandResult(success=False, message=f"Unknown command: {command}. Type 'help' for available commands.")

    # Static commands
    def handle_play(self, args: list[str]) -> CommandResult:
        self.bus.publish(BusEvent(type="PLAYBACK_RESUMED", payload={}))
        return CommandResult(success=True, message="Playback resumed.")

    def handle_pause(self, args: list[str]) -> CommandResult:
        self.bus.publish(BusEvent(type="PLAYBACK_PAUSED", payload={}))
        return CommandResult(success=True, message="Playback paused.")
        
    def handle_stop(self, args: list[str]) -> CommandResult:
        self.bus.publish(BusEvent(type="PLAYBACK_STOPPED", payload={}))
        return CommandResult(success=True, message="Playback stopped.")

    def handle_skip(self, args: list[str]) -> CommandResult:
        self.bus.publish(BusEvent(type="PLAYBACK_SKIPPED", payload={}))
        return CommandResult(success=True, message="Skipped to next track.")

    def handle_previous(self, args: list[str]) -> CommandResult:
        self.bus.publish(BusEvent(type="PLAYBACK_PREVIOUS", payload={}))
        return CommandResult(success=True, message="Going to previous track.")

    def handle_volume(self, args: list[str]) -> CommandResult:
        if not args:
            return CommandResult(success=False, message="Usage: volume <0-100>")
        try:
            vol = int(args[0])
            if 0 <= vol <= 100:
                self.bus.publish(BusEvent(type="VOLUME_CHANGED", payload={"volume": vol}))
                return CommandResult(success=True, message=f"Volume set to {vol}.")
            return CommandResult(success=False, message="Volume must be between 0 and 100.")
        except ValueError:
            return CommandResult(success=False, message="Invalid volume value.")

    def handle_seek(self, args: list[str]) -> CommandResult:
        if not args:
            return CommandResult(success=False, message="Usage: seek <seconds>")
        try:
            sec = int(args[0])
            self.bus.publish(BusEvent(type="SEEK_REQUESTED", payload={"seconds": sec}))
            return CommandResult(success=True, message=f"Seeking to {sec}s.")
        except ValueError:
            return CommandResult(success=False, message="Invalid seconds value.")

    def handle_queue(self, args: list[str]) -> CommandResult:
        if not args:
            return CommandResult(success=True, message="Displaying queue...", data=self.state.queue)
        subcmd = args[0].lower()
        if subcmd == "add":
            query = " ".join(args[1:])
            self.bus.publish(BusEvent(type="QUEUE_ADD_REQUESTED", payload={"query": query}))
            return CommandResult(success=True, message=f"Requested to add: {query}")
        elif subcmd == "remove":
            pos = int(args[1]) if len(args) > 1 and args[1].isdigit() else -1
            if pos >= 0:
                self.bus.publish(BusEvent(type="QUEUE_REMOVE_REQUESTED", payload={"position": pos}))
                return CommandResult(success=True, message=f"Requested to remove position: {pos}")
            return CommandResult(success=False, message="Invalid position.")
        elif subcmd == "clear":
            self.bus.publish(BusEvent(type="QUEUE_CLEAR_REQUESTED", payload={}))
            return CommandResult(success=True, message="Requested to clear queue.")
        return CommandResult(success=False, message=f"Unknown queue subcommand: {subcmd}")

    def handle_event(self, args: list[str]) -> CommandResult:
        if not args:
            return CommandResult(success=False, message="Usage: event <pause|resume|end>")
        subcmd = args[0].lower()
        if subcmd == "pause":
            self.bus.publish(BusEvent(type="EVENT_PAUSED", payload={}))
            return CommandResult(success=True, message="Event paused.")
        elif subcmd == "resume":
            self.bus.publish(BusEvent(type="EVENT_RESUMED", payload={}))
            return CommandResult(success=True, message="Event resumed.")
        elif subcmd == "end":
            self.bus.publish(BusEvent(type="EVENT_ENDED", payload={}))
            return CommandResult(success=True, message="Event ended.")
        return CommandResult(success=False, message=f"Unknown event subcommand: {subcmd}")

    # AI-driven commands
    def handle_vibe(self, args: list[str]) -> CommandResult:
        if not args:
            return CommandResult(success=False, message="Usage: vibe <preset>")
        preset = args[0].lower()
        self.bus.publish(BusEvent(type="VIBE_CHANGE_REQUESTED", payload={"preset": preset}))
        return CommandResult(success=True, message=f"Requested vibe change to: {preset}")

    def handle_energy(self, args: list[str]) -> CommandResult:
        if not args:
            return CommandResult(success=False, message="Usage: energy <value>")
        val_str = args[0]
        try:
            if val_str.startswith('+') or val_str.startswith('-'):
                val = int(val_str)
                self.bus.publish(BusEvent(type="ENERGY_CHANGE_RELATIVE", payload={"delta": val}))
                return CommandResult(success=True, message=f"Requested energy change by {val}")
            else:
                val = int(val_str)
                self.bus.publish(BusEvent(type="ENERGY_CHANGE_ABSOLUTE", payload={"value": val}))
                return CommandResult(success=True, message=f"Requested energy set to {val}")
        except ValueError:
            return CommandResult(success=False, message="Invalid energy value.")

    def handle_request(self, args: list[str]) -> CommandResult:
        if not args:
            return CommandResult(success=False, message="Usage: request \"<song name>\"")
        song_name = " ".join(args)
        self.bus.publish(BusEvent(type="USER_SONG_REQUESTED", payload={"query": song_name}))
        return CommandResult(success=True, message=f"Song request submitted: {song_name}")

    def handle_feedback(self, args: list[str]) -> CommandResult:
        if not args:
            return CommandResult(success=False, message="Usage: feedback <1-10> [energy] [song_choice] [transition] [vibe]")
        try:
            overall = int(args[0])
            payload = {"overall": overall}
            if len(args) == 5:
                payload.update({
                    "energy": int(args[1]),
                    "song_choice": int(args[2]),
                    "transition": int(args[3]),
                    "vibe": int(args[4])
                })
            self.bus.publish(BusEvent(type="USER_FEEDBACK_SUBMITTED", payload=payload))
            return CommandResult(success=True, message="Feedback submitted.")
        except ValueError:
            return CommandResult(success=False, message="Invalid feedback values.")

    def handle_status(self, args: list[str]) -> CommandResult:
        return CommandResult(success=True, message="Current status", data=self.state.event_state)

    def handle_history(self, args: list[str]) -> CommandResult:
        return CommandResult(success=True, message="Play history", data=self.state.history)

    def handle_scores(self, args: list[str]) -> CommandResult:
        return CommandResult(success=True, message="Latest scoring", data=self.state.latest_scores)

    def handle_why(self, args: list[str]) -> CommandResult:
        return CommandResult(success=True, message="Explanation", data=self.state.latest_reasoning)

    def handle_agents(self, args: list[str]) -> CommandResult:
        return CommandResult(success=True, message="Agent statuses", data=self.state.agent_statuses)

    def handle_learning(self, args: list[str]) -> CommandResult:
        return CommandResult(success=True, message="Learning stats", data=self.state.learning_stats)

    def handle_help(self, args: list[str]) -> CommandResult:
        from app.console.help_system import HelpSystem
        hs = HelpSystem()
        hs.show_help(args[0] if args else None)
        return CommandResult(success=True, message="Help displayed.")
