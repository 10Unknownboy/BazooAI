from __future__ import annotations

import logging
from datetime import datetime
from rich.console import Console
from rich.theme import Theme
from queue import Queue

from app.event.event_bus import get_event_bus, BusEvent

logger = logging.getLogger(__name__)

class APIConsole:
    """
    API/Server console monitoring HTTP requests, API calls, caching, and model latency.
    """
    def __init__(self) -> None:
        custom_theme = Theme({
            "info": "blue",
            "success": "green",
            "warning": "yellow",
            "error": "red bold"
        })
        self.console = Console(theme=custom_theme)
        self.bus = get_event_bus()
        self.event_queue: Queue[BusEvent] = Queue()
        self.running = False
        
        self.subscribe_events()

    def subscribe_events(self) -> None:
        events = [
            "AI_REQUEST_SENT", 
            "AI_RESPONSE_RECEIVED", 
            "AI_UNAVAILABLE", 
            "CACHE_HIT", 
            "CACHE_MISS", 
            "ERROR",
            "HTTP_REQUEST",
            "HTTP_RESPONSE",
            "RETRY_ATTEMPT",
            "RATE_LIMIT_EXCEEDED",
            "CONNECTION_STATE_CHANGED"
        ]
        for evt in events:
            self.bus.subscribe(evt, self.on_event)

    def on_event(self, event: BusEvent) -> None:
        self.event_queue.put(event)

    def format_event(self, event: BusEvent) -> str:
        timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        base = f"[{timestamp}] {event.type}: "
        
        if event.type == "AI_REQUEST_SENT":
            return f"[info]{base}Sent request to {event.payload.get('model', 'unknown')} for {event.payload.get('task', 'unknown')}[/info]"
        elif event.type == "AI_RESPONSE_RECEIVED":
            latency = event.payload.get('latency_ms', 0)
            return f"[success]{base}Response received in {latency}ms[/success]"
        elif event.type == "AI_UNAVAILABLE":
            return f"[error]{base}Model unavailable: {event.payload.get('reason', 'unknown')}[/error]"
        elif event.type == "CACHE_HIT":
            return f"[success]{base}Cache HIT for {event.payload.get('key', 'unknown')}[/success]"
        elif event.type == "CACHE_MISS":
            return f"[warning]{base}Cache MISS for {event.payload.get('key', 'unknown')}[/warning]"
        elif event.type == "ERROR":
            return f"[error]{base}{event.payload.get('message', 'Unknown error')}[/error]"
        elif event.type == "HTTP_REQUEST":
            return f"[info]{base}{event.payload.get('method', 'GET')} {event.payload.get('url', '')}[/info]"
        elif event.type == "HTTP_RESPONSE":
            status = event.payload.get('status_code', 200)
            color = "success" if 200 <= status < 300 else "warning" if 300 <= status < 400 else "error"
            return f"[{color}]{base}Status: {status} ({event.payload.get('latency_ms', 0)}ms)[/{color}]"
        elif event.type == "RETRY_ATTEMPT":
            return f"[warning]{base}Retry {event.payload.get('attempt', 1)} for {event.payload.get('target', 'unknown')}[/warning]"
        elif event.type == "CONNECTION_STATE_CHANGED":
            state = event.payload.get('state', 'unknown')
            color = "success" if state == "connected" else "error"
            return f"[{color}]{base}Connection state: {state}[/{color}]"
        else:
            return f"[info]{base}{event.payload}[/info]"

    def run(self) -> None:
        self.console.print("[bold magenta]API/Server Console Started[/bold magenta]")
        self.running = True
        try:
            while self.running:
                try:
                    event = self.event_queue.get(timeout=1.0)
                    formatted = self.format_event(event)
                    self.console.print(formatted)
                    self.event_queue.task_done()
                except Exception as e:
                    # Timeout exception is normal
                    if type(e).__name__ != 'Empty':
                        pass
        except KeyboardInterrupt:
            self.console.print("[bold red]Shutting down API Console...[/bold red]")
            self.running = False
