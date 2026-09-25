import click
import sys
import threading
import subprocess
import time
import os

from app.console.logging_setup import setup_logging

def start_orchestrator(dry_run: bool = False, simulate: bool = False) -> None:
    # Placeholder for actual orchestrator startup
    import logging
    logger = logging.getLogger("app.orchestrator")
    logger.info(f"Orchestrator started (dry_run={dry_run}, simulate={simulate})")
    
    # In a real app, this would be where the main loop/event processing starts
    while True:
        time.sleep(1)

@click.command()
@click.option('--dashboard', is_flag=True, help='Run dashboard only')
@click.option('--debug', is_flag=True, help='Run debug console only')
@click.option('--api', is_flag=True, help='Run API console only')
@click.option('--all', 'run_all', is_flag=True, help='Launch all three in separate windows')
@click.option('--dry-run', is_flag=True, help='Dry-run mode')
@click.option('--event', type=click.Path(exists=True), help='Load event from config file')
@click.option('--simulate', is_flag=True, help='Simulation mode')
def main(dashboard, debug, api, run_all, dry_run, event, simulate):
    """AI DJ System Entry Point"""
    setup_logging()

    if run_all:
        print("Launching all consoles in separate windows...")
        if os.name == 'nt':
            # Windows
            subprocess.Popen(['start', 'cmd', '/c', 'python -m app --dashboard'], shell=True)
            subprocess.Popen(['start', 'cmd', '/c', 'python -m app --debug'], shell=True)
            subprocess.Popen(['start', 'cmd', '/c', 'python -m app --api'], shell=True)
        else:
            # Linux/Mac (assuming xterm or similar is available)
            subprocess.Popen(['xterm', '-e', 'python -m app --dashboard'])
            subprocess.Popen(['xterm', '-e', 'python -m app --debug'])
            subprocess.Popen(['xterm', '-e', 'python -m app --api'])
            
        # Start orchestrator in the main process
        start_orchestrator(dry_run, simulate)
        return

    # Database init placeholder
    # from app.database.repositories import init_database
    # init_database()

    if not any([dashboard, debug, api]):
        # Default is dashboard
        dashboard = True

    # Start orchestrator in background
    orch_thread = threading.Thread(target=start_orchestrator, args=(dry_run, simulate), daemon=True)
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
