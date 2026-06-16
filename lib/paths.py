"""Filesystem paths for Leona Discord plugin data (self-contained, no other plugins)."""

from pathlib import Path

_DATA_DIR = None


def get_data_dir() -> Path:
    global _DATA_DIR
    if _DATA_DIR is None:
        from core.plugin_loader import PROJECT_ROOT
        _DATA_DIR = PROJECT_ROOT / "user" / "plugin_data" / "leona_discord"
        _DATA_DIR.mkdir(parents=True, exist_ok=True)
    return _DATA_DIR


def get_sqlite_path() -> Path:
    return get_data_dir() / "discord_memory.sqlite"
