"""Console text encoding: keep piped output from crashing on a legacy (non-UTF-8) code page."""

import sys


def ensure_utf8_output(streams=None) -> None:
    """Switch stdout/stderr to UTF-8 when they use another encoding (Windows consoles often use cp1252)."""
    for stream in streams if streams is not None else (sys.stdout, sys.stderr):
        encoding = (getattr(stream, "encoding", None) or "").lower().replace("-", "")
        if encoding != "utf8" and hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
