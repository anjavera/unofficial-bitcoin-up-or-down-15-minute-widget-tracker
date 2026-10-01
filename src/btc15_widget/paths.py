"""Per-user directories for cache and config, following each platform's conventions."""

from pathlib import Path

from platformdirs import user_cache_dir, user_config_dir

APP_NAME = "btc15-widget"


def cache_dir() -> Path:
    """Linux ~/.cache/btc15-widget, macOS ~/Library/Caches/btc15-widget, Windows %LOCALAPPDATA%\\btc15-widget\\Cache."""
    return Path(user_cache_dir(APP_NAME))


def config_dir() -> Path:
    """Linux ~/.config/btc15-widget, macOS ~/Library/Application Support/btc15-widget, Windows %APPDATA%\\btc15-widget."""
    return Path(user_config_dir(APP_NAME, roaming=True))


def env_file() -> Path:
    """Where optional API keys can live so they work from any folder."""
    return config_dir() / ".env"
