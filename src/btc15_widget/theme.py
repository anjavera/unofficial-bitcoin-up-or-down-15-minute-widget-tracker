"""Theme setting: dark / light / system, with OS detection and persistence."""

import json
import subprocess
from pathlib import Path

THEMES = ("dark", "light", "system")
DEFAULT_CONFIG_PATH = Path.home() / ".config" / "btc15-widget" / "config.json"


def detect_system_theme(run=subprocess.run) -> str:
    """GNOME colour-scheme preference; anything unreadable falls back to dark."""
    try:
        out = run(
            ["gsettings", "get", "org.gnome.desktop.interface", "color-scheme"],
            capture_output=True, text=True, timeout=2,
        ).stdout
    except (OSError, subprocess.SubprocessError):
        return "dark"
    return "dark" if "prefer-dark" in out else "light"


def resolve_theme(setting: str, system: str | None = None) -> str:
    if setting not in THEMES:
        raise ValueError(f"theme must be one of {THEMES}, got {setting!r}")
    if setting == "system":
        return system or detect_system_theme()
    return setting


def load_theme_setting(path: Path = DEFAULT_CONFIG_PATH) -> str:
    try:
        setting = json.loads(Path(path).read_text()).get("theme")
    except (OSError, ValueError, AttributeError):
        return "system"
    return setting if setting in THEMES else "system"


def save_theme_setting(path: Path, setting: str) -> None:
    if setting not in THEMES:
        raise ValueError(f"theme must be one of {THEMES}, got {setting!r}")
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"theme": setting}))
