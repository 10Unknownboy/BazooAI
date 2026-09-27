import click
import sys
import threading
import subprocess
import time
import os

from app.console.logging_setup import setup_logging

def start_orchestrator(dry_run: bool = False, simulate: bool = False) -> None:
    import logging
    import asyncio
    from app.agents.orchestrator import DJOrchestrator
    from app.models.event import EventConfig

    logger = logging.getLogger("app.orchestrator")
    logger.info(f"Orchestrator started (dry_run={dry_run}, simulate={simulate})")
    
    async def run():
        orchestrator = DJOrchestrator()
        # Default event config
        event_config = EventConfig(
            event_type="college_party",
            target_energy=0.85
        )
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
        print("Launching Guest API on port 8003...")
        api_proc = subprocess.Popen([sys.executable, "-m", "uvicorn", "app.api.guest_api:app", "--port", "8003"])
        print("Launching Streamlit Dashboard...")
        subprocess.run([sys.executable, "-m", "streamlit", "run", "app/ui/streamlit_app.py"])
        api_proc.terminate()
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
        start_orchestrator(dry_run, simulate)
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
