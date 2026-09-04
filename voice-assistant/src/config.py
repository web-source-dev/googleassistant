"""Configuration for Google Assistant."""

from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path
from typing import Any

from src.targets import ALIASES, KNOWN_TARGETS  # re-exported for callers

APP_NAME = "Google Assistant"
APP_ID = "GoogleAssistant"
DEFAULT_BACKEND_URL = "http://187.127.151.185:8000"

DEFAULTS: dict[str, Any] = {
    "wake_word": "asistan",
    "require_wake_word": True,
    "autostart": False,
    "speech_timeout": 8,
    "phrase_time_limit": 12,
    "energy_threshold": 150,
    "pause_threshold": 1.0,
    "screen_record": True,
    "send_voice": True,
    "backend_url": DEFAULT_BACKEND_URL,
    "record_fps": 30,
    "record_quality": 50,
    "record_max_width": 0,
}


def get_resource_dir() -> Path:
    """Return the directory that holds bundled files (example config, assets)."""
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    return Path(__file__).resolve().parent.parent


def get_app_dir() -> Path:
    """Writable user data. Installed builds use Local AppData, not Program Files."""
    if getattr(sys, "frozen", False):
        local = os.environ.get("LOCALAPPDATA")
        base = Path(local) if local else Path.home() / "AppData" / "Local"
        path = base / APP_NAME
        path.mkdir(parents=True, exist_ok=True)
        return path
    return Path(__file__).resolve().parent.parent


def get_config_path() -> Path:
    """Return path to user config file."""
    return get_app_dir() / "config.json"


def load_config() -> dict[str, Any]:
    """Load config from disk, merging with defaults."""
    config = DEFAULTS.copy()
    path = get_config_path()

    if not path.exists():
        example = get_resource_dir() / "config.example.json"
        if example.exists():
            shutil.copy(example, path)
        else:
            save_config(config)
        return config

    try:
        with path.open("r", encoding="utf-8") as f:
            stored = json.load(f)
        if isinstance(stored, dict):
            config.update(stored)
    except (json.JSONDecodeError, OSError):
        pass

    current = str(config.get("backend_url") or "").rstrip("/")
    if current in {"", "http://127.0.0.1:8000", "http://localhost:8000"}:
        config["backend_url"] = DEFAULT_BACKEND_URL

    return config


def save_config(config: dict[str, Any]) -> None:
    """Persist config to disk."""
    path = get_config_path()
    stale = ("openrouter_api_key", "openrouter_model", "recordings_dir", "record_segment_minutes", "debug_panel")
    stored = {key: value for key, value in config.items() if key not in stale}
    with path.open("w", encoding="utf-8") as f:
        json.dump(stored, f, indent=2)


def get_assets_dir() -> Path:
    bundled = get_resource_dir() / "assets"
    if bundled.exists():
        return bundled
    return get_app_dir() / "assets"
