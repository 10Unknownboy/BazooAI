from __future__ import annotations

import logging
from datetime import datetime
from rich.console import Console
from rich.theme import Theme
from queue import Empty, Queue

from app.event.event_bus import BusEvent, BusMessage, get_event_bus

logger = logging.getLogger(__name__)

class DebugConsole:
    """
    Debug console for real-time internal system monitoring.
    """
    def __init__(self) -> None:
        self.console = Console()
        self.bus = get_event_bus()
        self.event_queue: Queue[BusMessage] = Queue()
        self.running = False
        
        self.bus.subscribe_all(self.on_event)

    def on_event(self, event: BusMessage) -> None:
        self.event_queue.put(event)

    def format_event(self, event: BusMessage) -> str:
        timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        event_type = event.event_type.value
        payload = event.data
        prefix = f"[dim cyan][{timestamp}][/dim cyan] [bold yellow]{event_type}[/bold yellow]"
        
        if event.event_type == BusEvent.SCORING_COMPLETE:
            return f"{prefix} Candidates scored: {len(payload.get('candidates', []))}"
        elif event.event_type == BusEvent.POLICY_VIOLATION:
            return f"{prefix} [red]Policy rejected:[/red] {payload.get('reason', '')}"
        elif event.event_type == BusEvent.AGENT_DECISION:
            return f"{prefix} Agent {payload.get('agent', '')}: {payload.get('reasoning', payload.get('reason', ''))}"
        elif event.event_type == BusEvent.QUEUE_UPDATED:
            return f"{prefix} Queue update: {payload.get('action', payload)}"
        elif event.event_type == BusEvent.EVENT_STATE_UPDATED:
            return f"{prefix} Decision epoch: {payload.get('state', {}).get('decision_epoch', 'unknown')}"
        elif event.event_type == BusEvent.ERROR:
            return f"{prefix} [bold red]ERROR: {payload.get('message', '')}[/bold red]"
        else:
            # Generic fallback
            payload_str = str(payload)[:100] + ("..." if len(str(payload)) > 100 else "")
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
                except Empty:
                    continue
        except KeyboardInterrupt:
            self.console.print("[bold red]Shutting down Debug Console...[/bold red]")
            self.running = False
