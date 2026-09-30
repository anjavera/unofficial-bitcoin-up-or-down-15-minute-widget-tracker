"""Terminal widget for the Polymarket US BTC Up/Down 15-minute markets (Textual)."""

import argparse
import asyncio
import sys
import threading
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from pathlib import Path

from textual.app import App, ComposeResult
from textual.widgets import Static

from btc15_widget.colors import BACKGROUND
from btc15_widget.render import render_header, render_legend, render_status, render_strip
from btc15_widget.sources import CALIBRATION_EVERY, QUOTES_EVERY, DataSources, default_sources, run_calibration
from btc15_widget.state import WidgetState
from btc15_widget.theme import DEFAULT_CONFIG_PATH, THEMES, load_theme_setting, resolve_theme, save_theme_setting

MIN_WIDTH, MIN_HEIGHT = 40, 12
TOO_SMALL = f"Terminal too small (need {MIN_WIDTH}x{MIN_HEIGHT})"
FOREGROUND = {"dark": "#e6edf3", "light": "#1f2328"}
SYSTEM_THEME_RECHECK = 30  # seconds between re-reading the OS theme while set to "system"
RETRY_FAILED_LOAD_AFTER = timedelta(seconds=30)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def snapshot_text(state: WidgetState, now: datetime, theme: str) -> str:
    """One plain-text frame of the whole widget (used by --snapshot)."""
    parts = [
        render_header(state, now, theme),
        render_strip(state.strip_windows(now), theme),
        render_legend(theme),
        render_status(state, now, theme),
    ]
    return "\n\n".join(p.plain for p in parts)


class WidgetApp(App):
    CSS = "Static { height: auto; margin-bottom: 1; }"
    BINDINGS = [("q", "quit", "Quit"), ("t", "cycle_theme", "Theme"), ("r", "refresh_data", "Refresh")]

    def __init__(self, sources: DataSources | None = None, config_path: Path = DEFAULT_CONFIG_PATH,
                 clock: Callable[[], datetime] = utcnow) -> None:
        super().__init__()
        self._sources, self._config_path, self.clock = sources, Path(config_path), clock
        self.state = WidgetState()
        self.setting = load_theme_setting(self._config_path)
        self.theme_resolved = resolve_theme(self.setting)
        self.last_paint: dict[str, str] = {}
        self._stop = threading.Event()
        self._feed_stop = asyncio.Event()
        self._loading = False
        self._retry_history_at: datetime | None = None
        self._last_calibration: datetime | None = None
        self._last_theme_check = 0.0

    def compose(self) -> ComposeResult:
        for name in ("header", "strip", "legend", "status"):
            yield Static(id=name)

    # ---- lifecycle -------------------------------------------------------------------------
    def on_mount(self) -> None:
        if self._sources is None:
            try:
                self._sources = default_sources()
            except Exception as e:  # missing credentials etc.: show it in the app, never a traceback
                self.state.error = str(e)[:200]
        self.refresh_view()
        if self._sources is not None:
            self._start_history_load()
            self.run_worker(self._poll_quotes, thread=True, exit_on_error=False, group="quotes")
            self.run_worker(self._run_feed(), exit_on_error=False, group="feed")
        self.set_interval(1.0, self._on_second)

    def on_unmount(self) -> None:
        self._stop.set()
        self._feed_stop.set()
        if self._sources is not None:
            try:
                self._sources.close()
            except Exception:
                pass

    async def action_quit(self) -> None:
        self._stop.set()
        self._feed_stop.set()
        self.exit()

    # ---- background work -------------------------------------------------------------------
    def _start_history_load(self) -> None:
        if self._loading or self._sources is None:
            return
        if self._retry_history_at and self.clock() < self._retry_history_at:
            return  # an earlier load failed; do not hammer the API
        self._loading = True
        self.state.loading = True
        self.run_worker(self._load_history, thread=True, exit_on_error=False, group="history")

    def _load_history(self) -> None:
        try:
            now = self.clock()
            windows = self._sources.load_history(now)
            self.call_from_thread(self.state.set_history, windows, now)
            self.call_from_thread(setattr, self.state, "error", None)
            self._retry_history_at = None
            self._maybe_calibrate(now)
        except Exception as e:
            self._retry_history_at = self.clock() + RETRY_FAILED_LOAD_AFTER
            self.call_from_thread(setattr, self.state, "error", str(e)[:200] or type(e).__name__)
        finally:
            self._loading = False
            self.state.loading = False

    def _maybe_calibrate(self, now: datetime) -> None:
        if self._last_calibration and (now - self._last_calibration).total_seconds() < CALIBRATION_EVERY:
            return
        self._last_calibration = now
        run_calibration(self.state, self._sources, now)

    def _poll_quotes(self) -> None:
        while not self._stop.is_set():
            try:
                quotes = self._sources.fetch_quotes()
                self.call_from_thread(self.state.apply_quotes, quotes, self.clock())
            except Exception:
                pass  # a failed poll just leaves the last quotes to go stale
            self._stop.wait(QUOTES_EVERY)

    async def _run_feed(self) -> None:
        feed = self._sources.feed_factory(lambda tick: self.state.apply_tick(tick, self.clock()))
        if feed is not None:
            await feed.run(self._feed_stop)

    # ---- painting --------------------------------------------------------------------------
    def _on_second(self) -> None:
        now = self.clock()
        if self._sources is not None and self.state.needs_history_refresh(now):
            self._start_history_load()
        if self.setting == "system" and now.timestamp() - self._last_theme_check > SYSTEM_THEME_RECHECK:
            self._last_theme_check = now.timestamp()
            self.theme_resolved = resolve_theme("system")
        self.refresh_view()

    def _feed_status(self, now: datetime) -> str:
        if self._sources is None:
            return "offline"
        if self.state.live_tick(now) is None:
            return "connecting"
        return "reconnecting" if self.state.is_stale("tick", now) else "live"

    def refresh_view(self) -> None:
        now, theme = self.clock(), self.theme_resolved
        self.state.feed_status = self._feed_status(now)
        width, height = self.size
        if width < MIN_WIDTH or height < MIN_HEIGHT:
            texts = {"header": TOO_SMALL, "strip": "", "legend": "", "status": ""}
        else:
            texts = {
                "header": render_header(self.state, now, theme),
                "strip": render_strip(self.state.strip_windows(now), theme),
                "legend": render_legend(theme),
                "status": render_status(self.state, now, theme),
            }
        for name, content in texts.items():
            self.query_one(f"#{name}", Static).update(content)
        self.last_paint = {k: v if isinstance(v, str) else v.plain for k, v in texts.items()}
        self.screen.styles.background = BACKGROUND[theme]
        self.screen.styles.color = FOREGROUND[theme]

    # ---- actions ---------------------------------------------------------------------------
    def action_cycle_theme(self) -> None:
        self.setting = THEMES[(THEMES.index(self.setting) + 1) % len(THEMES)]
        save_theme_setting(self._config_path, self.setting)
        self.theme_resolved = resolve_theme(self.setting)
        self.refresh_view()

    def action_refresh_data(self) -> None:
        self.state.history_at = None  # forces a reload on the next second
        self._retry_history_at = None  # and overrides any failure backoff


async def _collect_tick(sources: DataSources, state: WidgetState, clock: Callable[[], datetime], timeout: float = 5.0) -> None:
    """Listen to the live feed until the live window's first tick arrives (or `timeout`)."""
    got = asyncio.Event()

    def on_tick(tick) -> None:
        state.apply_tick(tick, clock())
        if state.live_tick(clock()) is not None:
            got.set()

    feed = sources.feed_factory(on_tick)
    if feed is None:
        return
    stop = asyncio.Event()
    task = asyncio.create_task(feed.run(stop))
    try:
        await asyncio.wait_for(got.wait(), timeout)
    except asyncio.TimeoutError:
        pass
    stop.set()
    await asyncio.wait({task}, timeout=2)


def _print_snapshot(sources: DataSources, config_path: Path, clock: Callable[[], datetime]) -> None:
    state, now = WidgetState(), clock()
    state.set_history(sources.load_history(now), now)
    state.apply_quotes(sources.fetch_quotes(), clock())
    run_calibration(state, sources, now)
    asyncio.run(_collect_tick(sources, state, clock))
    state.feed_status = "live" if state.live_tick(clock()) else "no live tick"
    print(snapshot_text(state, clock(), resolve_theme(load_theme_setting(config_path))))


def main(argv: list[str] | None = None, sources: DataSources | None = None,
         config_path: Path = DEFAULT_CONFIG_PATH, clock: Callable[[], datetime] = utcnow) -> None:
    parser = argparse.ArgumentParser(prog="btc15-widget", description="Live BTC 15-minute Up/Down terminal widget")
    parser.add_argument("--snapshot", action="store_true", help="print one plain-text frame and exit")
    parser.add_argument("--theme", choices=THEMES, help="set and save the theme")
    args = parser.parse_args(argv)
    if args.theme:
        save_theme_setting(Path(config_path), args.theme)
    if not args.snapshot:
        WidgetApp(sources=sources, config_path=config_path, clock=clock).run()
        return
    try:
        _print_snapshot(sources or default_sources(), Path(config_path), clock)
    except Exception as e:
        print(f"Error: {str(e)[:300]}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
