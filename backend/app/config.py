"""Configuration for fetching and storing Elexon BMRS data."""

import os
from dataclasses import dataclass
from datetime import time
from pathlib import Path

BASE_URL = "https://data.elexon.co.uk/bmrs/api/v1"

# HTTP request timeout in seconds.
TIMEOUT = float(os.getenv("ELEXON_TIMEOUT_SECONDS", "30"))
if TIMEOUT <= 0:
    raise ValueError("ELEXON_TIMEOUT_SECONDS must be greater than zero")

# Purchasing cutoff in Europe/London local time, using HH:MM format.
CUTOFF_TIME = time.fromisoformat(os.getenv("ELEXON_CUTOFF_TIME", "09:00"))

PUBLICATION_LOOKBACK_DAYS = int(os.getenv("ELEXON_PUBLICATION_LOOKBACK_DAYS", "7"))
if PUBLICATION_LOOKBACK_DAYS < 1:
    raise ValueError("ELEXON_PUBLICATION_LOOKBACK_DAYS must be at least one")

# Relative paths are resolved from the backend directory.
BACKEND_DIR = Path(__file__).resolve().parent.parent
DATA_PATH = Path(os.getenv("ELEXON_DATA_PATH", "data")).expanduser()
if not DATA_PATH.is_absolute():
    DATA_PATH = BACKEND_DIR / DATA_PATH



@dataclass(frozen=True)
class Settings:
    """Shared HTTP defaults, retaining the existing environment configuration."""

    cutoff_time: str = CUTOFF_TIME.strftime("%H:%M")
    data_path: Path = DATA_PATH
    publication_lookback_days: int = PUBLICATION_LOOKBACK_DAYS


settings = Settings()
