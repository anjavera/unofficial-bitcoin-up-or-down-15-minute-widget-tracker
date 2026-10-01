"""Persisted set of pinned market slugs, shared by the CLI and the dashboard widget."""

import json
from pathlib import Path

DEFAULT_PATH = Path.home() / ".config" / "btc15-widget" / "watchlist.json"


class Watchlist:
    def __init__(self, path: Path = DEFAULT_PATH) -> None:
        self.path = path
        self._slugs: set[str] = self._load()

    def _load(self) -> set[str]:
        try:
            return set(json.loads(self.path.read_text()))
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            return set()

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(sorted(self._slugs)))

    def __contains__(self, slug: str) -> bool:
        return slug in self._slugs

    def __iter__(self):
        return iter(sorted(self._slugs))

    def __len__(self) -> int:
        return len(self._slugs)

    def add(self, slug: str) -> None:
        self._slugs.add(slug)
        self.save()

    def remove(self, slug: str) -> None:
        self._slugs.discard(slug)
        self.save()

    def toggle(self, slug: str) -> bool:
        """Pin/unpin `slug`; returns True if it is now pinned."""
        pinned = slug not in self._slugs
        if pinned:
            self._slugs.add(slug)
        else:
            self._slugs.discard(slug)
        self.save()
        return pinned
