from __future__ import annotations

import json
from pathlib import Path
from typing import Any


BASE_DIR = Path(__file__).resolve().parent.parent
CONFIG_PATH = BASE_DIR / "config" / "config.json"
UPLOAD_DIR = BASE_DIR / "uploads"
EDITED_DIR = UPLOAD_DIR / "edited"
DATABASE_PATH = BASE_DIR / "database" / "database.db"


DEFAULT_CONFIG: dict[str, Any] = {
    "general_kpi_threshold": 98,
    "general_utilization_threshold": 75,
    "special_kpi_thresholds": {},
}


def ensure_project_dirs() -> None:
    """Create local runtime folders without touching user workbooks."""
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    EDITED_DIR.mkdir(parents=True, exist_ok=True)
    DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)


def load_config() -> dict[str, Any]:
    """Load threshold settings from JSON, creating defaults on first run."""
    ensure_project_dirs()
    if not CONFIG_PATH.exists():
        CONFIG_PATH.write_text(json.dumps(DEFAULT_CONFIG, indent=2), encoding="utf-8")

    with CONFIG_PATH.open("r", encoding="utf-8") as file:
        user_config = json.load(file)

    return {**DEFAULT_CONFIG, **user_config}
