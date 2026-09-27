from __future__ import annotations

from app.database.engine import init_database
from app.database.repositories import get_repository
from app.models.song import Song
from app.providers.local_file_provider import LocalFileProvider


def sync_local_library(provider: LocalFileProvider) -> int:
    """Upsert indexed local tracks into the primary SQLite song catalog."""
    init_database()
    repository = get_repository("song")
    synced = 0
    for track in provider.list_songs():
        path = track["path"]
        song = Song(
            song_id=track["id"],
            title=track["title"],
            artist=track["artist"],
            artists=[track["artist"]] if track["artist"] != "Unknown Artist" else [],
            duration=track["duration"],
            source_provider="local_file",
            source_provider_id=track["id"],
            provider_ids={"local_file": track["id"]},
            file_path=path,
        )
        repository.save(song)
        synced += 1
    return synced
