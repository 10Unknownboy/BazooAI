from __future__ import annotations

import asyncio
import threading
from concurrent.futures import Future

from app.agents.orchestrator import DJOrchestrator
from app.config.settings import get_settings
from app.database.engine import init_database
from app.models.event import EventConfig
from app.music.local_library import sync_local_library
from app.playback.playback_controller import PlaybackController
from app.providers.local_file_provider import LocalFileProvider
from app.providers.mock_provider import MockMusicProvider
from app.queue.queue_manager import QueueManager


class ConsoleRuntime:
    """Own the shared in-process event, queue, and playback services for CLI consoles."""

    def __init__(
        self,
        event_config: EventConfig,
        *,
        dry_run: bool = False,
        simulate: bool = False,
    ):
        self.settings = get_settings()
        init_database()
        self.library_provider = LocalFileProvider(directory=str(self.settings.local_music_dir))
        sync_local_library(self.library_provider)
        if dry_run or simulate or event_config.dry_run:
            speed = (
                event_config.simulation_speed
                if event_config.simulation_speed > 1
                else (10.0 if simulate else 1.0)
            )
            self.provider = MockMusicProvider(
                simulation_speed=speed,
                songs=self.library_provider.list_songs(),
            )
        else:
            self.provider = self.library_provider

        self.queue_manager = QueueManager(event_config.lookahead_songs)
        self.orchestrator = DJOrchestrator(queue_manager=self.queue_manager)
        self.playback = PlaybackController(self.queue_manager, self.provider)
        self.loop = asyncio.new_event_loop()
        self._thread = threading.Thread(
            target=self._run_loop, name="dj-console-runtime", daemon=True
        )
        self._thread.start()
        started: Future = asyncio.run_coroutine_threadsafe(
            self.orchestrator.start(event_config), self.loop
        )
        started.result(timeout=120)

    def _run_loop(self) -> None:
        asyncio.set_event_loop(self.loop)
        self.loop.run_forever()

    def close(self) -> None:
        if self.loop.is_running():
            stopped = asyncio.run_coroutine_threadsafe(self.orchestrator.stop(), self.loop)
            stopped.result(timeout=30)
            self.playback.close()
            self.loop.call_soon_threadsafe(self.loop.stop)
            self._thread.join(timeout=5)
        self.loop.close()
