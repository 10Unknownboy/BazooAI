from __future__ import annotations

import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path
from rich.logging import RichHandler

def setup_logging(level: int = logging.INFO, log_dir: str = "logs") -> None:
    """
    Configures structured logging with rotating file handlers and a Rich console handler.
    Creates separate logs for different subsystems.
    """
    Path(log_dir).mkdir(parents=True, exist_ok=True)
    
    # Root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(level)
    
    # Clear existing handlers
    root_logger.handlers.clear()
    
    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | %(name)-20s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    
    # Subsystems
    log_files = {
        "debug": "debug.log",
        "ai": "ai.log",
        "api": "api.log",
        "playback": "playback.log",
        "audio": "audio.log",
        "lyrics": "lyrics.log",
        "learning": "learning.log"
    }
    
    for name, filename in log_files.items():
        filepath = os.path.join(log_dir, filename)
        handler = RotatingFileHandler(filepath, maxBytes=10*1024*1024, backupCount=5)
        handler.setFormatter(formatter)
        handler.setLevel(level)
        
        logger = logging.getLogger(f"app.{name}")
        logger.setLevel(level)
        logger.addHandler(handler)
        logger.propagate = False # Prevent double logging if we add root handlers later
        
        # Also add to root for the debug log file to capture everything
        if name == "debug":
            root_logger.addHandler(handler)

    # Console Handler using Rich
    rich_handler = RichHandler(rich_tracebacks=True, show_time=True, show_path=False)
    rich_handler.setLevel(level)
    root_logger.addHandler(rich_handler)

    logging.info("Logging configured successfully.")
