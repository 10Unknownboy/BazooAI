from __future__ import annotations

import logging
import threading

from app.event.event_bus import BusEvent, get_event_bus
from app.models.song import Song
from app.providers.base import MusicProvider
from app.queue.queue_manager import QueueManager

logger = logging.getLogger(__name__)


class PlaybackController:
    """Coordinate provider playback with the orchestrator-owned queue."""

    def __init__(self, queue_manager: QueueManager, provider: MusicProvider):
        self.queue = queue_manager
        self.provider = provider
        self.event_bus = get_event_bus()
        self.current_song: Song | None = None
        self.previous_item = None
        self.is_playing = False
        self.last_error: str | None = None
        self._stop_monitor = threading.Event()
        self._monitor_thread = threading.Thread(
            target=self._monitor_playback,
            name="playback-monitor",
            daemon=True,
        )
        self._monitor_thread.start()

    def _monitor_playback(self) -> None:
        while not self._stop_monitor.wait(0.25):
            if (
                self.is_playing
                and not self.provider.is_playing()
                and not getattr(self.provider, "_paused", False)
            ):
                logger.info("Playback monitor detected song end")
                self.on_song_end()
                self.play()

    def play(self) -> bool:
        """Start the current queue item or resume a paused track."""
        if self.is_playing:
            return True

        if self.current_song and getattr(self.provider, "_paused", False):
            if not self.provider.resume():
                return False
            self.is_playing = True
            self.event_bus.publish(BusEvent.PLAYBACK_RESUMED, source="playback")
            return True

        item = self.queue.get_current()
        if item is None:
            self.last_error = "The playback queue is empty."
            logger.warning("Cannot play: queue is empty")
            return False
        if not self.provider.play(item.song_id):
            provider_error = getattr(self.provider, "last_error", None)
            self.last_error = provider_error or (
                f"Playback provider could not start {item.song_title or item.song_id} "
                f"({item.song_id})."
            )
            logger.error(
                "Playback provider failed to start song %s: %s",
                item.song_id,
                self.last_error,
            )
            self.event_bus.publish(
                BusEvent.ERROR,
                source="playback",
                data={
                    "message": self.last_error,
                    "song_id": item.song_id,
                },
            )
            return False

        self.last_error = None
        provider_song = self.provider.get_song(item.song_id) or {}
        self.current_song = Song(
            song_id=item.song_id,
            title=item.song_title or provider_song.get("title") or "Unknown Title",
            artist=item.song_artist or provider_song.get("artist") or "Unknown Artist",
            duration=provider_song.get("duration") or 210.0,
            bpm=item.song_bpm,
            energy=item.song_energy,
        )
        self.is_playing = True
        self.event_bus.publish(
            BusEvent.SONG_STARTED,
            source="playback",
            data={"song_id": item.song_id},
        )
        return True

    def pause(self) -> bool:
        if not self.provider.pause():
            return False
        self.is_playing = False
        self.event_bus.publish(BusEvent.PLAYBACK_PAUSED, source="playback")
        return True

    def resume(self) -> bool:
        return self.play()

    def stop(self) -> bool:
        stopped = self.provider.stop()
        self.is_playing = False
        self.current_song = None
        self.event_bus.publish(BusEvent.PLAYBACK_STOPPED, source="playback")
        return stopped

    def skip(self) -> bool:
        if self.current_song is None:
            return self.play()
        if not self.provider.stop():
            logger.error("Playback provider failed to stop the current song for skip")
            return False
        self.on_song_end()
        return self.play()

    def previous(self) -> bool:
        previous = self.previous_item
        if previous is None:
            return False
        self.provider.stop()
        if self.current_song is not None:
            self.queue.add_song(
                song_id=self.current_song.song_id,
                score=0.0,
                song_title=self.current_song.title,
                song_artist=self.current_song.artist,
                position=1,
            )
        self.queue.add_song(
            song_id=previous.song_id,
            score=previous.final_score,
            song_title=previous.song_title or "",
            song_artist=previous.song_artist or "",
            position=0,
            decision_epoch=previous.decision_epoch,
        )
        self.current_song = None
        self.is_playing = False
        return self.play()

    def volume(self, value: int) -> bool:
        if not 0 <= value <= 100:
            raise ValueError("Volume must be between 0 and 100")
        return self.provider.volume(value)

    def seek(self, seconds: float) -> bool:
        if seconds < 0:
            raise ValueError("Seek position cannot be negative")
        return self.provider.seek(seconds)

    def on_song_end(self) -> None:
        """Notify the orchestrator; it alone advances the shared queue."""
        if self.current_song:
            finished = self.current_song
            self.current_song = None
            self.is_playing = False
            self.previous_item = self.queue.get_current()
            self.event_bus.publish(
                BusEvent.SONG_ENDED,
                source="playback",
                data={"song_id": finished.song_id},
            )

    def get_current_song(self) -> Song | None:
        return self.current_song

    @property
    def is_paused(self) -> bool:
        return bool(getattr(self.provider, "_paused", False))

    def get_remaining_time(self) -> float:
        return self.provider.get_remaining_time()

    def close(self) -> None:
        self.stop()
        self._stop_monitor.set()
        self._monitor_thread.join(timeout=1.0)
