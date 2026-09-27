from __future__ import annotations

import logging
from datetime import datetime
from rich.console import Console
from rich.theme import Theme
from queue import Empty, Queue

from app.event.event_bus import BusEvent, BusMessage, get_event_bus

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
        self.event_queue: Queue[BusMessage] = Queue()
        self.running = False
        
        self.subscribe_events()

    def subscribe_events(self) -> None:
        events = (
            BusEvent.AI_REQUEST_SENT,
            BusEvent.AI_RESPONSE_RECEIVED,
            BusEvent.AI_UNAVAILABLE,
            BusEvent.CACHE_HIT,
            BusEvent.CACHE_MISS,
            BusEvent.ERROR,
            BusEvent.HTTP_REQUEST,
            BusEvent.HTTP_RESPONSE,
            BusEvent.RETRY_ATTEMPT,
            BusEvent.RATE_LIMIT_EXCEEDED,
            BusEvent.CONNECTION_STATE_CHANGED,
        )
        for event_type in events:
            self.bus.subscribe(event_type, self.on_event)

    def on_event(self, event: BusMessage) -> None:
        self.event_queue.put(event)

    def format_event(self, event: BusMessage) -> str:
        timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        event_type = event.event_type.value
        payload = event.data
        base = f"[{timestamp}] {event_type}: "
        
        if event_type == BusEvent.AI_REQUEST_SENT.value:
            return f"[info]{base}Sent request for {payload.get('task', 'unknown')}[/info]"
        elif event_type == BusEvent.AI_RESPONSE_RECEIVED.value:
            latency = payload.get('latency_ms', 0)
            return f"[success]{base}Response from {payload.get('model', 'unknown')} in {latency:.0f}ms (success={payload.get('success')})[/success]"
        elif event_type == BusEvent.AI_UNAVAILABLE.value:
            return f"[error]{base}Model unavailable: {payload.get('reason', payload.get('error', 'unknown'))}[/error]"
        elif event_type == BusEvent.CACHE_HIT.value:
            return f"[success]{base}Cache HIT for {payload.get('key', 'unknown')}[/success]"
        elif event_type == BusEvent.CACHE_MISS.value:
            return f"[warning]{base}Cache MISS for {payload.get('key', 'unknown')}[/warning]"
        elif event_type == BusEvent.ERROR.value:
            return f"[error]{base}{payload.get('message', 'Unknown error')}[/error]"
        elif event_type == BusEvent.HTTP_REQUEST.value:
            return f"[info]{base}{payload.get('method', 'GET')} {payload.get('url', '')}[/info]"
        elif event_type == BusEvent.HTTP_RESPONSE.value:
            status = payload.get('status_code', 200)
            color = "success" if 200 <= status < 300 else "warning" if 300 <= status < 400 else "error"
            return f"[{color}]{base}Status: {status} ({payload.get('latency_ms', 0):.0f}ms)[/{color}]"
        elif event_type == BusEvent.RETRY_ATTEMPT.value:
            return f"[warning]{base}Retry {payload.get('attempt', 1)} for {payload.get('target', 'unknown')}[/warning]"
        elif event_type == BusEvent.RATE_LIMIT_EXCEEDED.value:
            return f"[error]{base}Rate limit exceeded ({payload.get('status_code', 'unknown')})[/error]"
        elif event_type == BusEvent.CONNECTION_STATE_CHANGED.value:
            state = payload.get('state', 'unknown')
            color = "success" if state == "connected" else "error"
            return f"[{color}]{base}Connection state: {state}[/{color}]"
        else:
            return f"[info]{base}{payload}[/info]"

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
                except Empty:
                    continue
        except KeyboardInterrupt:
            self.console.print("[bold red]Shutting down API Console...[/bold red]")
            self.running = False
