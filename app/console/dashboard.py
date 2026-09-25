from __future__ import annotations

import logging
import time
import threading
from typing import Any
from rich.console import Console
from rich.layout import Layout
from rich.panel import Panel
from rich.table import Table
from rich.live import Live
from rich.progress import Progress, BarColumn, TextColumn
from rich.text import Text
from rich.columns import Columns

from app.event.event_bus import get_runtime_state, get_event_bus
from app.console.command_handler import CommandHandler

logger = logging.getLogger(__name__)

class DashboardConsole:
    """
    Rich-based live dashboard for the AI DJ System.
    """
    def __init__(self) -> None:
        self.console = Console()
        self.state = get_runtime_state()
        self.bus = get_event_bus()
        self.command_handler = CommandHandler()
        self.running = False

    def make_layout(self) -> Layout:
        layout = Layout(name="root")
        layout.split(
            Layout(name="header", size=5),
            Layout(name="main"),
            Layout(name="footer", size=3)
        )
        layout["main"].split_row(
            Layout(name="left_column", ratio=2),
            Layout(name="right_column", ratio=1)
        )
        layout["left_column"].split(
            Layout(name="now_playing", size=6),
            Layout(name="queue")
        )
        layout["right_column"].split(
            Layout(name="agents", size=8),
            Layout(name="requests")
        )
        return layout

    def generate_header(self) -> Panel:
        event_name = getattr(self.state, 'event_name', 'UNKNOWN EVENT')
        vibe = getattr(self.state, 'current_vibe', 'MIXED')
        energy = getattr(self.state, 'current_energy', 50)
        progress = getattr(self.state, 'event_progress', 0)
        
        grid = Table.grid(expand=True)
        grid.add_column(justify="left", ratio=1)
        grid.add_column(justify="right", ratio=1)
        
        energy_bar = f"{'█' * (energy // 10)}{'░' * (10 - (energy // 10))} {energy}%"
        progress_bar = f"{'█' * (progress // 10)}{'░' * (10 - (progress // 10))} {progress}%"
        
        grid.add_row(f"EVENT: [bold cyan]{event_name}[/bold cyan]", f"ENERGY: [yellow]{energy_bar}[/yellow]")
        grid.add_row(f"VIBE: [magenta]{vibe}[/magenta]", f"EVENT PROGRESS: [green]{progress_bar}[/green]")
        
        return Panel(grid, title="AI DJ", border_style="bold blue")

    def generate_now_playing(self) -> Panel:
        np = getattr(self.state, 'now_playing', None)
        if not np:
            return Panel(Text("Nothing currently playing", justify="center"), title="NOW PLAYING")
        
        title = np.get("title", "Unknown Title")
        artist = np.get("artist", "Unknown Artist")
        bpm = np.get("bpm", 0)
        energy = np.get("energy", 0.0)
        pos = np.get("position", 0)
        dur = np.get("duration", 1)
        
        pos_str = f"{pos//60}:{pos%60:02d}"
        dur_str = f"{dur//60}:{dur%60:02d}"
        
        content = f"[bold white]{title}[/bold white] — [dim white]{artist}[/dim white]\n"
        content += f"BPM: {bpm} | Energy: {energy:.2f} | {pos_str}/{dur_str}"
        return Panel(content, title="NOW PLAYING", border_style="green")

    def generate_queue(self) -> Panel:
        queue = getattr(self.state, 'queue', [])
        table = Table(show_header=False, expand=True, box=None)
        table.add_column("Pos", width=3)
        table.add_column("Song")
        table.add_column("Status", width=3)
        table.add_column("Score", justify="right")
        
        for i, song in enumerate(queue[:5], 1):
            lock = song.get("lock_status", "🟡")
            score = song.get("score", 0.0)
            title = song.get("title", "Unknown")
            table.add_row(f"{i}.", title, lock, f"{score:.1f}")
            
        if not queue:
            table.add_row("", "Queue is empty", "", "")
            
        return Panel(table, title="QUEUE", border_style="cyan")

    def generate_agents(self) -> Panel:
        agents = getattr(self.state, 'agent_statuses', {})
        text = Text()
        
        # Default agents to show if state is empty
        default_agents = ["DJ", "REQUEST", "LYRICS", "AUDIO", "LEARNING", "POLICY"]
        
        count = 0
        for name in default_agents:
            status = agents.get(name, "IDLE")
            color = "green" if status == "ACTIVE" else "yellow" if status == "ANALYZING" else "red" if status == "ERROR" else "dim white"
            
            text.append(f"{name}: ", style="bold")
            text.append(f"{status}", style=color)
            
            count += 1
            if count % 2 == 0:
                text.append("\n")
            else:
                text.append(" | ")
                
        return Panel(text, title="AGENTS", border_style="magenta")

    def generate_requests(self) -> Panel:
        stats = getattr(self.state, 'request_stats', {"pending": 0, "accepted": 0, "deferred": 0, "rejected": 0})
        
        text = (
            f"Pending:  [yellow]{stats['pending']}[/yellow]\n"
            f"Accepted: [green]{stats['accepted']}[/green]\n"
            f"Deferred: [blue]{stats['deferred']}[/blue]\n"
            f"Rejected: [red]{stats['rejected']}[/red]"
        )
        return Panel(text, title="REQUESTS", border_style="yellow")
        
    def generate_footer(self) -> Panel:
        return Panel("Type a command and press Enter (e.g. 'help', 'vibe hype', 'skip')", title="COMMAND INPUT", border_style="dim")

    def update_layout(self, layout: Layout) -> None:
        layout["header"].update(self.generate_header())
        layout["now_playing"].update(self.generate_now_playing())
        layout["queue"].update(self.generate_queue())
        layout["agents"].update(self.generate_agents())
        layout["requests"].update(self.generate_requests())
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
                    if not res.success:
                        logger.warning(f"Command failed: {res.message}")
            except EOFError:
                break
            except Exception as e:
                logger.error(f"Input error: {e}")

    def run(self) -> None:
        self.running = True
        layout = self.make_layout()
        
        input_thread = threading.Thread(target=self.input_loop, daemon=True)
        input_thread.start()

        with Live(layout, refresh_per_second=1, screen=True) as live:
            try:
                while self.running:
                    self.update_layout(layout)
                    time.sleep(1.0)
            except KeyboardInterrupt:
                self.running = False
