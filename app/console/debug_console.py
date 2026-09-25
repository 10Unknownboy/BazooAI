from __future__ import annotations

import logging
from datetime import datetime
from rich.console import Console
from rich.theme import Theme
from queue import Queue

from app.event.event_bus import get_event_bus, BusEvent

logger = logging.getLogger(__name__)

class DebugConsole:
    """
    Debug console for real-time internal system monitoring.
    """
    def __init__(self) -> None:
        self.console = Console()
        self.bus = get_event_bus()
        self.event_queue: Queue[BusEvent] = Queue()
        self.running = False
        
        self.bus.subscribe_all(self.on_event)

    def on_event(self, event: BusEvent) -> None:
        self.event_queue.put(event)

    def format_event(self, event: BusEvent) -> str:
        timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        prefix = f"[dim cyan][{timestamp}][/dim cyan] [bold yellow]{event.type}[/bold yellow]"
        
        if event.type == "SCORING_COMPLETE":
            return f"{prefix} Candidates scored: {len(event.payload.get('candidates', []))}"
        elif event.type == "POLICY_VIOLATION":
            return f"{prefix} [red]Policy rejected:[/red] {event.payload.get('reason', '')}"
        elif event.type == "AGENT_DECISION":
            return f"{prefix} Agent {event.payload.get('agent', '')}: {event.payload.get('reasoning', '')}"
        elif event.type == "QUEUE_UPDATED":
            return f"{prefix} Queue length: {event.payload.get('length', 0)}"
        elif event.type == "EVENT_STATE_UPDATED":
            return f"{prefix} State -> {event.payload.get('state', 'unknown')}"
        elif event.type == "ERROR":
            return f"{prefix} [bold red]ERROR: {event.payload.get('message', '')}[/bold red]"
        else:
            # Generic fallback
            payload_str = str(event.payload)[:100] + ("..." if len(str(event.payload)) > 100 else "")
            return f"{prefix} {payload_str}"

    def run(self) -> None:
        self.console.print("[bold magenta]Debug Console Started[/bold magenta]")
        self.running = True
        try:
            while self.running:
                try:
                    event = self.event_queue.get(timeout=1.0)
                    self.console.print(self.format_event(event))
                    self.event_queue.task_done()
                except Exception as e:
                    if type(e).__name__ != 'Empty':
                        pass
        except KeyboardInterrupt:
            self.console.print("[bold red]Shutting down Debug Console...[/bold red]")
            self.running = False
