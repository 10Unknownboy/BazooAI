import click
import sys
import threading
import subprocess
import time
import os
from pathlib import Path

from app.console.logging_setup import setup_logging
from app.config.settings import load_event_config
from app.models.event import EventConfig


def event_config_from_file(path: str | Path) -> EventConfig:
    """Convert the documented YAML event format into the runtime event model."""
    raw = load_event_config(path)
    event = raw.get("event", {})
    audience = raw.get("audience", {})
    music = raw.get("music", {})
    requests = raw.get("requests", {})
    learning = raw.get("learning", {})
    audio = raw.get("audio", {})
    simulation = raw.get("simulation", {})
    return EventConfig(
        name=event.get("name", "Untitled Event"),
        event_type=event.get("type", "custom"),
        description=event.get("description", ""),
        min_age=audience.get("min_age", 0),
        max_age=audience.get("max_age", 100),
        expected_count=audience.get("expected_count"),
        duration_minutes=raw.get("duration_minutes", 240),
        languages=raw.get("languages", ["Hindi", "English"]),
        region=raw.get("region"),
        starting_vibe=music.get("starting_vibe", "chill"),
        target_vibe=music.get("target_vibe"),
        explicit_allowed=music.get("explicit_allowed", False),
        prefer_genres=music.get("prefer_genres", []),
        avoid_genres=music.get("avoid_genres", []),
        prefer_artists=music.get("prefer_artists", []),
        avoid_artists=music.get("avoid_artists", []),
        energy_curve=raw.get("energy_curve", []),
        allow_requests=requests.get("allow_requests", True),
        request_mode=requests.get("mode", "adaptive"),
        requests_affect_vibe=requests.get("affect_vibe", True),
        learning_enabled=learning.get("enabled", True),
        feedback_prompt=learning.get("feedback_prompt", True),
        lookahead_songs=audio.get("lookahead_songs", 5),
        analyze_on_add=audio.get("analyze_on_add", True),
        simulation_speed=simulation.get("speed", 1.0),
        dry_run=simulation.get("dry_run", False),
        custom_instructions=raw.get("custom_instructions", ""),
    )


def start_orchestrator(
    dry_run: bool = False,
    simulate: bool = False,
    event_path: str | None = None,
) -> None:
    import logging
    import asyncio
    from app.agents.orchestrator import DJOrchestrator
    from app.models.event import EventConfig

    logger = logging.getLogger("app.orchestrator")
    logger.info(f"Orchestrator started (dry_run={dry_run}, simulate={simulate})")
    
    async def run():
        orchestrator = DJOrchestrator()
        event_config = (
            event_config_from_file(event_path)
            if event_path
            else EventConfig(event_type="college_party", starting_vibe="party")
        )
        event_config.dry_run = dry_run or simulate or event_config.dry_run
        await orchestrator.start(event_config)
        
        while True:
            await asyncio.sleep(1)

    # Note: If it's called in a thread, asyncio.run works to run the event loop for that thread
    asyncio.run(run())

@click.command()
@click.option('--dashboard', is_flag=True, help='Run terminal dashboard only')
@click.option('--streamlit', 'run_streamlit', is_flag=True, help='Run Streamlit UI dashboard')
@click.option('--debug', is_flag=True, help='Run debug console only')
@click.option('--api', is_flag=True, help='Run API console only')
@click.option('--model-server', is_flag=True, help='Run model server (main.py)')
@click.option('--all', 'run_all', is_flag=True, help='Launch all consoles and model server in separate windows')
@click.option('--dry-run', is_flag=True, help='Dry-run mode')
@click.option('--event', type=click.Path(exists=True), help='Load event from config file')
@click.option('--simulate', is_flag=True, help='Simulation mode')
def main(dashboard, run_streamlit, debug, api, model_server, run_all, dry_run, event, simulate):
    """AI DJ System Entry Point"""
    setup_logging()
    if run_streamlit:
        print("Launching Streamlit Dashboard...")
        subprocess.run([sys.executable, "-m", "streamlit", "run", "app/ui/streamlit_app.py"])
        return
    if run_all:
        print("Launching all consoles in separate windows...")
        if os.name == 'nt':
            # Windows
            subprocess.Popen(['start', 'cmd', '/k', 'python main.py'], shell=True)
            subprocess.Popen(['start', 'cmd', '/k', 'python -m app --dashboard'], shell=True)
            subprocess.Popen(['start', 'cmd', '/k', 'python -m app --debug'], shell=True)
            subprocess.Popen(['start', 'cmd', '/k', 'python -m app --api'], shell=True)
        else:
            # Linux/Mac (assuming xterm or similar is available)
            subprocess.Popen(['xterm', '-e', 'python main.py'])
            subprocess.Popen(['xterm', '-e', 'python -m app --dashboard'])
            subprocess.Popen(['xterm', '-e', 'python -m app --debug'])
            subprocess.Popen(['xterm', '-e', 'python -m app --api'])
            
        # Start orchestrator in the main process
        start_orchestrator(dry_run, simulate, event)
        return
    
    if model_server:
        print("Launching model server...")
        subprocess.run([sys.executable, "main.py"])
        return


    # Database init placeholder
    # from app.database.repositories import init_database
    # init_database()

    if not any([dashboard, debug, api]):
        # Default is dashboard
        dashboard = True

    # Start orchestrator in background
    orch_thread = threading.Thread(
        target=start_orchestrator,
        args=(dry_run, simulate, event),
        daemon=True,
    )
    orch_thread.start()

    if dashboard:
        from app.console.dashboard import DashboardConsole
        console = DashboardConsole()
        console.run()
    elif debug:
        from app.console.debug_console import DebugConsole
        console = DebugConsole()
        console.run()
    elif api:
        from app.console.api_console import APIConsole
        console = APIConsole()
        console.run()

if __name__ == '__main__':
    main()
