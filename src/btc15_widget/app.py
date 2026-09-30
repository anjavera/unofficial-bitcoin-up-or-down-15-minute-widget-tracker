"""Terminal widget for the Polymarket US BTC Up/Down 15-minute markets (Textual)."""

import argparse
import asyncio
import io
import sys
import threading
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from pathlib import Path

from rich.console import Console
from rich.text import Text
from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.widgets import Static

from btc15_widget.colors import BACKGROUND
from btc15_widget.panel import panel_layout, render_dial, render_logo
from btc15_widget.render import build_table, render_header, render_legend, render_status, render_strip, split_table
from btc15_widget.sources import CALIBRATION_EVERY, QUOTES_EVERY, DataSources, default_sources, run_calibration
from btc15_widget.state import WidgetState
from btc15_widget.windows import floor_window, seconds_remaining
from btc15_widget.theme import DEFAULT_CONFIG_PATH, THEMES, load_theme_setting, resolve_theme, save_theme_setting

MIN_WIDTH, MIN_HEIGHT = 80, 16  # the widest text block is 80 columns; the stack is about 15 rows
TOO_SMALL = f"Terminal too small (need {MIN_WIDTH}x{MIN_HEIGHT})"
FOREGROUND = {"dark": "#e6edf3", "light": "#1f2328"}
SYSTEM_THEME_RECHECK = 30  # seconds between re-reading the OS theme while set to "system"
RETRY_FAILED_LOAD_AFTER = timedelta(seconds=30)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _plain(renderable, width: int = 100) -> str:
    if isinstance(renderable, str):
        return renderable
    if isinstance(renderable, Text):
        return renderable.plain
    console = Console(width=max(width, MIN_WIDTH), file=io.StringIO(), color_system=None, force_terminal=False)
    console.print(renderable)
    return console.file.getvalue().rstrip("\n")


def _table(state: WidgetState, now: datetime, theme: str):
    return build_table(state.table_windows(now), theme, volume=False,
                       live_start=floor_window(now), live_price=state.proxy_price(now))


def snapshot_text(state: WidgetState, now: datetime, theme: str, view: str = "table") -> str:
    """One plain-text frame of the whole widget (used by --snapshot)."""
    body = _table(state, now, theme) if view == "table" else render_strip(state.strip_windows(now), theme)
    parts = [render_header(state, now, theme), body, render_legend(theme, view), render_status(state, now, theme)]
    return "\n\n".join(_plain(p) for p in parts)


class WidgetApp(App):
    CSS = """
    #top { dock: top; height: auto; }
    #header { height: auto; margin-bottom: 1; }
    #thead { height: auto; }
    #bottom { dock: bottom; height: auto; }
    #legend { height: auto; margin-top: 1; }
    #status { height: auto; }
    #main { height: 1fr; }
    #body { width: 1fr; max-width: 84; }
    #body Static { height: auto; }
    #side { width: 22; height: auto; margin-left: 2; }
    #dial { height: auto; }
    #logo { height: auto; margin-top: 1; }
    """
    BINDINGS = [("q", "quit", "Quit"), ("t", "cycle_theme", "Theme"), ("v", "toggle_view", "Table/strip"),
                ("r", "refresh_data", "Refresh")]

    def __init__(self, sources: DataSources | None = None, config_path: Path = DEFAULT_CONFIG_PATH,
                 clock: Callable[[], datetime] = utcnow) -> None:
        super().__init__()
        self._sources, self._config_path, self.clock = sources, Path(config_path), clock
        self.state = WidgetState()
        self.setting = load_theme_setting(self._config_path)
        self.theme_resolved = resolve_theme(self.setting)
        self.view = "table"
        self._painted: dict = {}
        self._stop = threading.Event()
        self._feed_stop = asyncio.Event()
        self._loading = False
        self._retry_history_at: datetime | None = None
        self._last_calibration: datetime | None = None
        self._last_theme_check = 0.0

    @property
    def last_paint(self) -> dict[str, str]:
        """Plain text of the last painted frame (used by tests)."""
        return {name: _plain(content, self.size.width) for name, content in self._painted.items()}

    def compose(self) -> ComposeResult:
        with Vertical(id="top"):
            yield Static(id="header")
            yield Static(id="thead")  # column names, pinned above the scrolling rows
        with Horizontal(id="main"):
            with VerticalScroll(id="body"):
                yield Static(id="table")
                yield Static(id="strip")
            with Vertical(id="side"):  # analog countdown and logo, shown only when the terminal is big enough
                yield Static(id="dial")
                yield Static(id="logo")
        with Vertical(id="bottom"):
            yield Static(id="legend")
            yield Static(id="status")

    # ---- lifecycle -------------------------------------------------------------------------
    def on_mount(self) -> None:
        if self._sources is None:
            try:
                self._sources = default_sources()
            except Exception as e:  # missing credentials etc.: show it in the app, never a traceback
                self.state.error = str(e)[:200]
        self.query_one("#body").focus()  # so the arrow and page keys scroll the table
        self.refresh_view()
        if self._sources is not None:
            self._start_history_load()
            threading.Thread(target=self._poll_quotes, daemon=True, name="btc15-quotes").start()
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
        # daemon thread: Textual's thread workers run in asyncio's default executor, which blocks exit
        threading.Thread(target=self._load_history, daemon=True, name="btc15-history").start()

    def _apply(self, fn, *args) -> None:
        """Run `fn` on the UI thread; quietly give up if the app is shutting down."""
        if self._stop.is_set():
            return
        try:
            self.call_from_thread(fn, *args)
        except Exception:
            pass

    def _load_history(self) -> None:
        try:
            now = self.clock()
            windows = self._sources.load_history(now)
            self._apply(self.state.set_history, windows, now)
            failed = [w for w in windows if w.error]
            if windows and len(failed) * 2 > len(windows):  # load_history never raises: outages arrive as gaps
                self._retry_history_at = self.clock() + RETRY_FAILED_LOAD_AFTER
                message = f"history unavailable: {len(failed)} of {len(windows)} windows failed ({failed[0].error})"
                self._apply(setattr, self.state, "error", message)
            else:
                self._retry_history_at = None
                self._apply(setattr, self.state, "error", None)
                self._maybe_calibrate(now)
        except Exception as e:
            self._retry_history_at = self.clock() + RETRY_FAILED_LOAD_AFTER
            self._apply(setattr, self.state, "error", str(e)[:200] or type(e).__name__)
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
                self._apply(self.state.apply_quotes, quotes, self.clock())
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
            texts = {"header": TOO_SMALL, "thead": "", "table": "", "strip": "", "dial": "", "logo": "",
                     "legend": "", "status": ""}
            layout = None
        else:
            layout = panel_layout(width, height)
            thead, rows = ("", "")
            if self.view == "table":
                thead, rows = split_table(_table(self.state, now, theme))
            texts = {
                "header": render_header(self.state, now, theme),
                "thead": thead,
                "dial": self._dial(now, theme, layout[0]) if layout else "",
                "logo": render_logo(layout[0]) if layout and layout[1] else "",
                "table": rows,
                "strip": render_strip(self.state.strip_windows(now), theme) if self.view == "strip" else "",
                "legend": render_legend(theme, self.view),
                "status": render_status(self.state, now, theme),
            }
        body = self.query_one("#body")
        following = body.is_vertical_scroll_end  # stay on the newest row unless the user scrolled up
        for name, content in texts.items():
            self.query_one(f"#{name}", Static).update(content)
        side = self.query_one("#side")
        side.display = layout is not None
        if layout:
            side.styles.width = layout[0] + 2
        self.query_one("#table").display = self.view == "table"
        self.query_one("#thead").display = self.view == "table"
        self.query_one("#strip").display = self.view == "strip"
        if following:
            self.call_after_refresh(body.scroll_end, animate=False)
        self._painted = texts
        self.screen.styles.background = BACKGROUND[theme]
        self.screen.styles.color = FOREGROUND[theme]

    def _dial(self, now: datetime, theme: str, size: int):
        gap = self.state.gap(now)
        lean = None if gap is None else ("UP" if gap >= 0 else "DOWN")
        return render_dial(seconds_remaining(now, floor_window(now)), lean, theme, size)

    # ---- actions ---------------------------------------------------------------------------
    def action_cycle_theme(self) -> None:
        self.setting = THEMES[(THEMES.index(self.setting) + 1) % len(THEMES)]
        save_theme_setting(self._config_path, self.setting)
        self.theme_resolved = resolve_theme(self.setting)
        self.refresh_view()

    def action_toggle_view(self) -> None:
        self.view = "strip" if self.view == "table" else "table"
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
