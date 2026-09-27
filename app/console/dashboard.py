from __future__ import annotations

import logging
import threading
import time

from rich.console import Console
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from app.console.command_handler import CommandHandler
from app.event.event_bus import BusEvent, get_event_bus, get_runtime_state

logger = logging.getLogger(__name__)


class DashboardConsole:
    """
    Rich-based live dashboard for the AI DJ System.
    """

    def __init__(
        self,
        command_handler: CommandHandler | None = None,
        *,
        show_all: bool = False,
    ) -> None:
        self.console = Console()
        self.state = get_runtime_state()
        self.bus = get_event_bus()
        self.command_handler = command_handler or CommandHandler()
        self.show_all = show_all
        self.running = False

    def make_layout(self) -> Layout:
        layout = Layout(name="root")
        sections = [
            Layout(name="header", size=5),
            Layout(name="main", ratio=3),
        ]
        if self.show_all:
            sections.append(Layout(name="diagnostics", ratio=2))
        sections.append(Layout(name="footer", size=3))
        layout.split(*sections)
        layout["main"].split_row(
            Layout(name="left_column", ratio=2), Layout(name="right_column", ratio=1)
        )
        layout["left_column"].split(Layout(name="now_playing", size=6), Layout(name="queue"))
        layout["right_column"].split(Layout(name="agents", size=8), Layout(name="requests"))
        if self.show_all:
            layout["diagnostics"].split_row(
                Layout(name="debug_console"),
                Layout(name="api_console"),
            )
        return layout

    def generate_diagnostics(self, *, api: bool) -> Panel:
        api_events = {
            BusEvent.AI_REQUEST_SENT,
            BusEvent.AI_RESPONSE_RECEIVED,
            BusEvent.AI_UNAVAILABLE,
            BusEvent.HTTP_REQUEST,
            BusEvent.HTTP_RESPONSE,
            BusEvent.RETRY_ATTEMPT,
            BusEvent.CONNECTION_STATE_CHANGED,
            BusEvent.CACHE_HIT,
            BusEvent.CACHE_MISS,
        }
        events = self.bus.get_history(limit=100)
        selected = [
            event
            for event in events
            if (event.event_type in api_events) == api
            and event.event_type
            in (
                api_events
                if api
                else {
                    BusEvent.SCORING_COMPLETE,
                    BusEvent.POLICY_VIOLATION,
                    BusEvent.AGENT_DECISION,
                    BusEvent.EVENT_STATE_UPDATED,
                    BusEvent.ERROR,
                    BusEvent.WARNING,
                    BusEvent.QUEUE_UPDATED,
                    BusEvent.QUEUE_ITEM_ADDED,
                }
            )
        ][-8:]
        lines = [
            f"[dim]{event.timestamp:%H:%M:%S}[/dim] "
            f"[yellow]{event.event_type.value}[/yellow] {str(event.data)[:100]}"
            for event in reversed(selected)
        ]
        title = "API CONSOLE" if api else "DEBUG CONSOLE"
        return Panel("\n".join(lines) or "No events recorded.", title=title)

    def generate_header(self) -> Panel:
        state = self.state.get_event_state() or {}
        event_config = state.get("event_config") or {}
        event_name = event_config.get("name", state.get("event_id", "UNKNOWN EVENT"))
        vibe = state.get("current_vibe", "MIXED")
        if isinstance(vibe, dict):
            vibe = ", ".join(f"{key}={value:.2f}" for key, value in vibe.items())
        energy = round(state.get("current_energy", 0.0) * 100)
        progress = round(state.get("event_progress", 0.0) * 100)

        grid = Table.grid(expand=True)
        grid.add_column(justify="left", ratio=1)
        grid.add_column(justify="right", ratio=1)

        energy_bar = f"{'█' * (energy // 10)}{'░' * (10 - (energy // 10))} {energy}%"
        progress_bar = f"{'█' * (progress // 10)}{'░' * (10 - (progress // 10))} {progress}%"

        grid.add_row(
            f"EVENT: [bold cyan]{event_name}[/bold cyan]", f"ENERGY: [yellow]{energy_bar}[/yellow]"
        )
        grid.add_row(
            f"VIBE: [magenta]{vibe}[/magenta]", f"EVENT PROGRESS: [green]{progress_bar}[/green]"
        )

        return Panel(grid, title="AI DJ", border_style="bold blue")

    def generate_now_playing(self) -> Panel:
        state = self.state.get_event_state() or {}
        current_song_id = state.get("current_song_id")
        queue_state = self.state.get_queue_state() or {}
        queue = queue_state.get("items", [])
        np = next((item for item in queue if item.get("song_id") == current_song_id), None)
        if not np:
            return Panel(Text("Nothing currently playing", justify="center"), title="NOW PLAYING")

        title = np.get("song_title", np.get("title", "Unknown Title"))
        artist = np.get("song_artist", np.get("artist", "Unknown Artist"))
        bpm = np.get("bpm", 0)
        energy = np.get("energy", 0.0)
        pos = np.get("position", 0)
        dur = np.get("duration", 1)

        pos_str = f"{pos // 60}:{pos % 60:02d}"
        dur_str = f"{dur // 60}:{dur % 60:02d}"

        content = f"[bold white]{title}[/bold white] — [dim white]{artist}[/dim white]\n"
        content += f"BPM: {bpm} | Energy: {energy:.2f} | {pos_str}/{dur_str}"
        return Panel(content, title="NOW PLAYING", border_style="green")

    def generate_queue(self) -> Panel:
        queue = (self.state.get_queue_state() or {}).get("items", [])
        table = Table(show_header=False, expand=True, box=None)
        table.add_column("Pos", width=3)
        table.add_column("Song")
        table.add_column("Status", width=3)
        table.add_column("Score", justify="right")

        for i, song in enumerate(queue[:5], 1):
            lock = song.get("lock_status", "FLEXIBLE")
            score = song.get("final_score", song.get("score", 0.0))
            title = song.get("song_title", song.get("title", "Unknown"))
            table.add_row(f"{i}.", title, lock, f"{score:.1f}")

        if not queue:
            table.add_row("", "Queue is empty", "", "")

        return Panel(table, title="QUEUE", border_style="cyan")

    def generate_agents(self) -> Panel:
        agents = self.state.get_agent_statuses()
        text = Text()

        # Default agents to show if state is empty
        default_agents = ["DJ", "REQUEST", "LYRICS", "AUDIO", "LEARNING", "POLICY"]

        count = 0
        for name in default_agents:
            status = agents.get(name, "IDLE")
            color = (
                "green"
                if status == "ACTIVE"
                else "yellow"
                if status == "ANALYZING"
                else "red"
                if status == "ERROR"
                else "dim white"
            )

            text.append(f"{name}: ", style="bold")
            text.append(f"{status}", style=color)

            count += 1
            if count % 2 == 0:
                text.append("\n")
            else:
                text.append(" | ")

        return Panel(text, title="AGENTS", border_style="magenta")

    def generate_requests(self) -> Panel:
        state = self.state.get_event_state() or {}
        stats = {
            "pending": 0,
            "accepted": len(state.get("accepted_requests", [])),
            "deferred": 0,
            "rejected": 0,
        }

        text = (
            f"Pending:  [yellow]{stats['pending']}[/yellow]\n"
            f"Accepted: [green]{stats['accepted']}[/green]\n"
            f"Deferred: [blue]{stats['deferred']}[/blue]\n"
            f"Rejected: [red]{stats['rejected']}[/red]"
        )
        return Panel(text, title="REQUESTS", border_style="yellow")

    def generate_footer(self) -> Panel:
        return Panel(
            "Type a command and press Enter (e.g. 'help', 'vibe hype', 'skip')",
            title="COMMAND INPUT",
            border_style="dim",
        )

    def update_layout(self, layout: Layout) -> None:
        layout["header"].update(self.generate_header())
        layout["now_playing"].update(self.generate_now_playing())
        layout["queue"].update(self.generate_queue())
        layout["agents"].update(self.generate_agents())
        layout["requests"].update(self.generate_requests())
        if self.show_all:
            layout["debug_console"].update(self.generate_diagnostics(api=False))
            layout["api_console"].update(self.generate_diagnostics(api=True))
        layout["footer"].update(self.generate_footer())

    def input_loop(self) -> None:
        while self.running:
            try:
                cmd_str = input()
                if cmd_str.strip():
                    cmd, args = self.command_handler.parse_command(cmd_str)
                    if cmd == "exit" or cmd == "quit":
                        self.running = False
                        break
                    res = self.command_handler.dispatch(cmd, args)
                    self.console.print(
                        f"[green]{res.message}[/green]"
                        if res.success
                        else f"[red]{res.message}[/red]"
                    )
                    if not res.success:
                        logger.warning("Command failed: %s", res.message)
            except EOFError:
                break
            except Exception as e:
                logger.error(f"Input error: {e}")

    def run(self) -> None:
        self.running = True
        layout = self.make_layout()

        input_thread = threading.Thread(target=self.input_loop, daemon=True)
        input_thread.start()

        with Live(layout, refresh_per_second=1, screen=True):
            try:
                while self.running:
                    self.update_layout(layout)
                    time.sleep(1.0)
            except KeyboardInterrupt:
                self.running = False
