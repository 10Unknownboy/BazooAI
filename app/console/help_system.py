from __future__ import annotations

from rich.console import Console
from rich.table import Table
from typing import Optional

class HelpSystem:
    """
    Categorized help system for the AI DJ Console.
    """
    
    def __init__(self) -> None:
        self.console = Console()
        self.categories = {
            "PLAYBACK": [
                ("play", "Resume playback"),
                ("pause", "Pause playback"),
                ("stop", "Stop playback"),
                ("skip", "Skip to the next track"),
                ("previous", "Go back to the previous track"),
                ("seek <seconds>", "Seek to a specific time in the current track"),
                ("volume <0-100>", "Set playback volume")
            ],
            "VIBE": [
                ("vibe <preset>", "Change vibe (party/romantic/sad/chill/hype/nostalgic)"),
                ("vibe list", "List all available vibe presets")
            ],
            "QUEUE": [
                ("queue", "Show current queue"),
                ("queue add <song_query>", "Add a song to the queue"),
                ("queue remove <position>", "Remove a song from the queue by its position"),
                ("queue clear", "Clear the entire queue")
            ],
            "REQUESTS": [
                ("request \"<song name>\"", "Submit a song request"),
                ("requests pending", "Show pending requests"),
                ("requests history", "Show history of requests")
            ],
            "FEEDBACK": [
                ("feedback <1-10>", "Give overall feedback for the current song"),
                ("feedback <overall> <energy> <song_choice> <transition> <vibe>", "Give multi-dimensional feedback")
            ],
            "EVENT": [
                ("event pause", "Pause the current event"),
                ("event resume", "Resume the current event"),
                ("event end", "End the current event"),
                ("event status", "Show current event status"),
                ("event config", "Show event configuration")
            ],
            "ANALYSIS": [
                ("analyze <song>", "Analyze a specific song"),
                ("analyze queue", "Analyze the upcoming queue")
            ],
            "AGENTS": [
                ("agents", "Show statuses of all agents"),
                ("agent <name> status", "Show detailed status of a specific agent")
            ],
            "LEARNING": [
                ("learning stats", "Show learning statistics"),
                ("learning history", "Show learning history")
            ],
            "DEBUG": [
                ("scores", "Show last scoring breakdown"),
                ("why", "Explain latest/next decision"),
                ("debug on/off", "Toggle debug mode"),
                ("cache stats", "Show cache statistics")
            ]
        }

    def show_help(self, category: Optional[str] = None) -> None:
        """
        Displays help for a specific category or all categories.
        """
        if category:
            cat_upper = category.upper()
            if cat_upper in self.categories:
                self._print_category_table(cat_upper, self.categories[cat_upper])
            else:
                self.console.print(f"[red]Error: Category '{category}' not found.[/red]")
                self.console.print(f"Available categories: {', '.join(self.categories.keys())}")
        else:
            for cat, commands in self.categories.items():
                self._print_category_table(cat, commands)
                self.console.print()

    def _print_category_table(self, title: str, commands: list[tuple[str, str]]) -> None:
        table = Table(title=title, show_header=True, header_style="bold magenta")
        table.add_column("Command", style="cyan", width=40)
        table.add_column("Description", style="green")

        for cmd, desc in commands:
            table.add_row(cmd, desc)

        self.console.print(table)
