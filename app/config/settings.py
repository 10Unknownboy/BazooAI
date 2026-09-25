"""Application settings loaded from environment variables and config files."""

from __future__ import annotations

import os
from pathlib import Path
from functools import lru_cache

import yaml
from dotenv import load_dotenv
from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
CONFIG_DIR = PROJECT_ROOT / "config"
DATA_DIR = PROJECT_ROOT / "data"
CACHE_DIR = PROJECT_ROOT / "cache"
LOG_DIR = PROJECT_ROOT / "logs"

for _d in (DATA_DIR, CACHE_DIR, LOG_DIR):
    _d.mkdir(parents=True, exist_ok=True)

load_dotenv(PROJECT_ROOT / ".env")


# ---------------------------------------------------------------------------
# Settings model
# ---------------------------------------------------------------------------
class AIModelSettings(BaseModel):
    url: str = Field(default="http://localhost:8000")
    timeout: int = Field(default=30)
    retries: int = Field(default=3)


class DatabaseSettings(BaseModel):
    url: str = Field(default="sqlite:///data/ai_dj.db")


class MusicBrainzSettings(BaseModel):
    user_agent: str = Field(default="AIDJSystem/0.1.0 (contact@example.com)")
    rate_limit: float = Field(default=1.0, description="Minimum seconds between requests")


class AudioSettings(BaseModel):
    enabled: bool = Field(default=True)
    fallback: str = Field(default="metadata")  # metadata | skip


class SimulationSettings(BaseModel):
    speed: float = Field(default=1.0)
    dry_run: bool = Field(default=False)


class ServerSettings(BaseModel):
    host: str = Field(default="127.0.0.1")
    port: int = Field(default=8000)


class AppSettings(BaseModel):
    """Top-level application settings assembled from env vars."""

    ai_model: AIModelSettings = Field(default_factory=AIModelSettings)
    database: DatabaseSettings = Field(default_factory=DatabaseSettings)
    musicbrainz: MusicBrainzSettings = Field(default_factory=MusicBrainzSettings)
    audio: AudioSettings = Field(default_factory=AudioSettings)
    simulation: SimulationSettings = Field(default_factory=SimulationSettings)
    server: ServerSettings = Field(default_factory=ServerSettings)
    log_level: str = Field(default="INFO")
    log_dir: Path = Field(default=LOG_DIR)

    @classmethod
    def from_env(cls) -> "AppSettings":
        """Build settings from environment variables."""
        return cls(
            ai_model=AIModelSettings(
                url=os.getenv("AI_MODEL_URL", "http://localhost:8000"),
                timeout=int(os.getenv("AI_MODEL_TIMEOUT", "30")),
                retries=int(os.getenv("AI_MODEL_RETRIES", "3")),
            ),
            database=DatabaseSettings(
                url=os.getenv("DATABASE_URL", f"sqlite:///{DATA_DIR / 'ai_dj.db'}"),
            ),
            musicbrainz=MusicBrainzSettings(
                user_agent=os.getenv(
                    "MUSICBRAINZ_USER_AGENT",
                    "AIDJSystem/0.1.0 (contact@example.com)",
                ),
                rate_limit=float(os.getenv("MUSICBRAINZ_RATE_LIMIT", "1.0")),
            ),
            audio=AudioSettings(
                enabled=os.getenv("AUDIO_ANALYSIS_ENABLED", "true").lower() == "true",
                fallback=os.getenv("AUDIO_ANALYSIS_FALLBACK", "metadata"),
            ),
            simulation=SimulationSettings(
                speed=float(os.getenv("SIMULATION_SPEED", "1.0")),
                dry_run=os.getenv("DRY_RUN", "false").lower() == "true",
            ),
            server=ServerSettings(
                host=os.getenv("API_HOST", "127.0.0.1"),
                port=int(os.getenv("API_PORT", "8000")),
            ),
            log_level=os.getenv("LOG_LEVEL", "INFO"),
            log_dir=Path(os.getenv("LOG_DIR", str(LOG_DIR))),
        )


@lru_cache(maxsize=1)
def get_settings() -> AppSettings:
    """Return cached application settings singleton."""
    return AppSettings.from_env()


# ---------------------------------------------------------------------------
# YAML config loaders
# ---------------------------------------------------------------------------
def load_yaml_config(filename: str) -> dict:
    """Load a YAML config file from the config directory."""
    path = CONFIG_DIR / filename
    if not path.exists():
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


@lru_cache(maxsize=1)
def load_policy_config() -> dict:
    return load_yaml_config("policy.yaml")


@lru_cache(maxsize=1)
def load_scoring_config() -> dict:
    return load_yaml_config("scoring_weights.yaml")


def load_event_config(path: str | Path | None = None) -> dict:
    """Load event config from a specific path or the default example."""
    if path:
        p = Path(path)
        if p.exists():
            with open(p, "r", encoding="utf-8") as f:
                return yaml.safe_load(f) or {}
    return load_yaml_config("event_example.yaml")
