import asyncio
import json
from datetime import datetime, timedelta, timezone

import pytest

from btc15_widget import app as app_module
from btc15_widget.app import WidgetApp, snapshot_text
from btc15_widget.model import LiveTick, Window
from btc15_widget.sources import DataSources
from btc15_widget.state import WidgetState
from btc15_widget.windows import MARKET_SLUG, floor_window

import re

ROW = re.compile(r"\d\d-\d\d \d\d:\d\d-\d\d:\d\d")
UTC = timezone.utc
NOW = datetime(2026, 9, 30, 9, 20, tzinfo=UTC)
STEP = timedelta(minutes=15)


def history(now=NOW):
    live = floor_window(now)
    return [
        Window(live - i * STEP, open=84000.0 + i, close=None if i == 0 else 84001.0 + i, status="OPEN" if i == 0 else "RESOLVED")
        for i in range(96, -1, -1)
    ]


class FakeFeed:
    def __init__(self, on_tick, now):
        self.on_tick, self.now = on_tick, now

    async def run(self, stop):
        slug = MARKET_SLUG.format(floor_window(self.now()))
        self.on_tick(LiveTick(slug, 0.62, 0.61, 0.62, 0.62, 10.0))
        await stop.wait()


def sources(clock, load=None):
    return DataSources(
        load_history=load or (lambda now: history()),
        fetch_quotes=lambda: {"a": 84000.5},
        fetch_candles=lambda start, end: (_ for _ in ()).throw(OSError("no candles in tests")),
        feed_factory=lambda on_tick: FakeFeed(on_tick, clock),
    )


def make_app(tmp_path, clock=lambda: NOW, load=None, src="default"):
    return WidgetApp(sources=sources(clock, load) if src == "default" else src, clock=clock)


async def until(pilot, cond, tries=100):
    for _ in range(tries):
        if cond():
            return True
        await pilot.pause(0.05)
    return False


def run(coro):
    asyncio.run(asyncio.wait_for(coro, timeout=30))


def test_app_renders_header_strip_and_legend(tmp_path):
    async def scenario():
        app = make_app(tmp_path)
        async with app.run_test(size=(100, 30)) as pilot:
            assert await until(pilot, lambda: app.state.windows and app.state.quotes and app.state.live_tick(NOW))
            app.refresh_view()
            paint = app.last_paint
            assert "≈ $84,000.50" in paint["header"] and "beat $84,000.00" in paint["header"]
            assert "Up 0.62" in paint["header"]
            assert len(ROW.findall(paint["table"])) == 97  # 96 past windows + the live one
            assert "Window (ET)" in paint["thead"] and "UP?" in paint["table"]  # live row leans UP (84000.50 vs open 84000.00)
            assert "net up" in paint["legend"] and "Chg" in paint["legend"]
            assert "Signals: off" in paint["status"] and "feed: live" in paint["status"]

    run(scenario())


def test_q_quits(tmp_path):
    async def scenario():
        app = make_app(tmp_path)
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.press("q")
            await pilot.pause(0.2)
        assert app._stop.is_set()

    run(scenario())


def test_there_is_no_theme_key(tmp_path):
    assert "t" not in {binding[0] for binding in WidgetApp.BINDINGS}

    async def scenario():
        app = make_app(tmp_path)
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.press("t")  # does nothing, and certainly does not crash
            await pilot.pause(0.1)
            assert not (tmp_path / "config.json").exists()

    run(scenario())


def test_startup_error_shows_panel_not_traceback(tmp_path):
    def broken(now):
        raise RuntimeError("Missing credentials")

    async def scenario():
        app = make_app(tmp_path, load=broken)
        async with app.run_test(size=(100, 30)) as pilot:
            assert await until(pilot, lambda: app.state.error)
            app.refresh_view()
            assert "Error: Missing credentials" in app.last_paint["status"]
            await pilot.press("q")
            await pilot.pause(0.2)

    run(scenario())


def test_default_sources_failure_is_shown_in_app(tmp_path, monkeypatch):
    def no_creds():
        raise RuntimeError("Missing POLYMARKET_KEY_ID / POLYMARKET_SECRET_KEY")

    monkeypatch.setattr(app_module, "default_sources", no_creds)

    async def scenario():
        app = make_app(tmp_path, src=None)
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause(0.2)
            app.refresh_view()
            assert "Error: Missing POLYMARKET_KEY_ID" in app.last_paint["status"]
            assert "feed: offline" in app.last_paint["status"]

    run(scenario())


def test_too_small_terminal(tmp_path):
    async def scenario():
        app = make_app(tmp_path)
        async with app.run_test(size=(30, 8)) as pilot:
            await pilot.pause(0.2)
            app.refresh_view()
            assert app.last_paint["header"] == "Terminal too small (need 80x16)"
            assert app.last_paint["strip"] == "" and app.last_paint["status"] == ""

    run(scenario())


def test_rollover_repaint(tmp_path):
    clock_now = {"t": datetime(2026, 9, 30, 9, 29, 30, tzinfo=UTC)}

    async def scenario():
        app = make_app(tmp_path, clock=lambda: clock_now["t"], load=lambda now: history())  # history never gains 09:30
        async with app.run_test(size=(100, 30)) as pilot:
            assert await until(pilot, lambda: app.state.windows and app.state.quotes)
            app.refresh_view()
            assert "ends in 00:30" in app.last_paint["header"]
            clock_now["t"] = datetime(2026, 9, 30, 9, 30, 30, tzinfo=UTC)
            app.refresh_view()
            header, table = app.last_paint["header"], app.last_paint["table"]
            assert "ends in 14:30" in header and "beat —" in header  # new window has no open yet
            rows = [line for line in table.split("\n") if ROW.search(line)]
            assert len(rows) == 97  # still 96 past windows + the live one
            assert "LIVE" in rows[-1]
            assert "UP" not in rows[-2] and "DOWN" not in rows[-2]  # the 09:15 window is pending until Polymarket settles it
            await pilot.press("v")
            strip_rows = app.last_paint["strip"].split("\n")
            assert len(strip_rows) == 4 and all(len(r) == 36 for r in strip_rows) and strip_rows[-1].endswith("?")

    run(scenario())


def test_snapshot_text_is_plain_and_complete():
    s = WidgetState()
    s.set_history(history(), NOW)
    s.apply_quotes({"a": 84000.5}, NOW)
    out = snapshot_text(s, NOW, "dark")
    assert "≈ $84,000.50" in out and "net up" in out and "Signals: off" in out
    assert "Window (ET)" in out and len(ROW.findall(out)) == 97
    assert "\x1b" not in out


def test_failed_history_load_backs_off_instead_of_hammering_the_api(tmp_path):
    calls = []

    def failing(now):
        calls.append(now)
        raise RuntimeError("rate limited by Polymarket (Cloudflare 1015)")

    async def scenario():
        app = make_app(tmp_path, load=failing)  # the injected clock never advances
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause(2.6)  # the once-a-second timer fires at least twice
            assert len(calls) == 1

    run(scenario())


def test_r_key_retries_immediately_even_during_backoff(tmp_path):
    calls = []

    def failing(now):
        calls.append(now)
        raise RuntimeError("down")

    async def scenario():
        app = make_app(tmp_path, load=failing)
        async with app.run_test(size=(100, 30)) as pilot:
            assert await until(pilot, lambda: len(calls) == 1)
            await pilot.pause(0.3)
            await pilot.press("r")
            assert await until(pilot, lambda: len(calls) == 2, tries=60)

    run(scenario())


def test_status_shows_loading_until_history_arrives(tmp_path):
    import threading

    release = threading.Event()

    def slow(now):
        release.wait(10)
        return history()

    async def scenario():
        app = make_app(tmp_path, load=slow)
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause(0.3)
            app.refresh_view()
            assert "loading" in app.last_paint["status"]
            release.set()
            assert await until(pilot, lambda: app.state.windows)
            app.refresh_view()
            assert "loading" not in app.last_paint["status"]

    run(scenario())


class DownClient:
    """Stands in for the Polymarket client during an API outage (drives the REAL load_history)."""

    def __init__(self):
        self.calls = 0
        self.events = self
        self.markets = self

    def retrieve_by_slug(self, slug):
        self.calls += 1
        raise RuntimeError("Error 1015: rate limited")


def test_history_outage_shows_error_and_backs_off(tmp_path):
    from btc15_widget.history import load_history

    down = DownClient()

    async def scenario():
        app = make_app(tmp_path, load=lambda now: load_history(down, now, hours=24, sleep=lambda s: None, with_volume=False))
        async with app.run_test(size=(100, 30)) as pilot:
            assert await until(pilot, lambda: app.state.error)
            app.refresh_view()
            assert "Error:" in app.last_paint["status"] and "history" in app.last_paint["status"]
            calls_after_first_load = down.calls
            await pilot.pause(2.6)  # the once-a-second timer fires, but the backoff must hold
            assert down.calls == calls_after_first_load

    run(scenario())


def test_q_quits_promptly_during_a_slow_history_load(tmp_path):
    import threading
    import time

    release = threading.Event()

    def slow(now):
        release.wait(25)
        return history()

    async def scenario():
        app = make_app(tmp_path, load=slow)
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause(0.3)
            await pilot.press("q")
            await pilot.pause(0.2)

    started = time.monotonic()
    try:
        run(scenario())
        assert time.monotonic() - started < 10  # must not wait for the 25 s load
    finally:
        release.set()


def test_layout_fits_an_80_column_terminal(tmp_path):
    async def scenario():
        for size, too_small in [((80, 24), False), ((80, 16), False), ((79, 24), True), ((80, 15), True)]:
            app = make_app(tmp_path)
            async with app.run_test(size=size) as pilot:
                assert await until(pilot, lambda: app.state.windows and app.state.quotes and app.state.live_tick(NOW))
                app.refresh_view()
                assert app.last_paint["header"].startswith("Terminal too small") == too_small, size

    run(scenario())


def test_v_toggles_between_table_and_strip_views(tmp_path):
    async def scenario():
        app = make_app(tmp_path)
        async with app.run_test(size=(100, 30)) as pilot:
            assert await until(pilot, lambda: app.state.windows)
            assert app.query_one("#table").display and not app.query_one("#strip").display
            await pilot.press("v")
            assert app.query_one("#strip").display and not app.query_one("#table").display
            await pilot.press("v")
            assert app.query_one("#table").display

    run(scenario())


def test_table_view_starts_scrolled_to_the_newest_window(tmp_path):
    async def scenario():
        app = make_app(tmp_path)
        async with app.run_test(size=(100, 30)) as pilot:
            assert await until(pilot, lambda: app.state.windows)
            assert await until(pilot, lambda: app.query_one("#body").is_vertical_scroll_end, tries=60)
            assert app.query_one("#body").max_scroll_y > 0  # 97 rows do not fit in 30 lines

    run(scenario())


def test_column_headers_stay_pinned_while_rows_scroll(tmp_path):
    async def scenario():
        app = make_app(tmp_path)
        async with app.run_test(size=(100, 30)) as pilot:
            assert await until(pilot, lambda: app.state.windows)
            assert await until(pilot, lambda: app.query_one("#body").is_vertical_scroll_end and app.query_one("#body").max_scroll_y > 0, tries=60)
            app.refresh_view()
            assert "Chg $" in app.last_paint["thead"] and "Chg $" not in app.last_paint["table"]
            assert app.query_one("#thead").display
            await pilot.press("v")
            assert not app.query_one("#thead").display  # the strip view has no column headers

    run(scenario())


def test_coin_panel_adapts_to_the_terminal_size(tmp_path):
    async def scenario():
        for size, shown in [((130, 50), True), ((115, 50), False), ((130, 27), False)]:
            app = make_app(tmp_path)
            async with app.run_test(size=size) as pilot:
                assert await until(pilot, lambda: app.state.windows and app.state.quotes and app.state.live_tick(NOW))
                app.refresh_view()
                coin = app.last_paint["coin"]
                assert bool(coin) == shown, size
                if shown:
                    assert "$" in coin and "*" in coin and len(coin.split("\n")) == 15
                assert "ends in 10:00" in app.last_paint["header"]  # the text countdown stays in every layout
                assert app.query_one("#side").display == shown

    run(scenario())


def test_scrollbar_is_attached_to_the_table(tmp_path):
    async def scenario():
        app = make_app(tmp_path)
        async with app.run_test(size=(130, 50)) as pilot:
            assert await until(pilot, lambda: app.state.windows and app.query_one("#body").max_scroll_y > 0, tries=60)
            assert await until(pilot, lambda: app.query_one("#body").is_vertical_scroll_end, tries=60)
            app.refresh_view()
            table_width = max(len(line) for line in app.last_paint["thead"].split("\n"))  # the grid's real width
            body = app.query_one("#body")
            gap = body.region.width - body.scrollbar_size_vertical - table_width
            assert gap == 0, f"{gap} columns between the table's right edge and its scrollbar"


    run(scenario())


def test_scrollbar_spans_the_whole_table_top_to_bottom(tmp_path):
    async def scenario():
        app = make_app(tmp_path)
        async with app.run_test(size=(130, 50)) as pilot:
            assert await until(pilot, lambda: app.state.windows and app.query_one("#body").max_scroll_y > 0, tries=60)
            assert await until(pilot, lambda: app.query_one("#body").is_vertical_scroll_end, tries=60)
            body, thead, table = app.query_one("#body"), app.query_one("#thead"), app.query_one("#table")
            assert thead.region.y == body.region.y, "the scrollbar must start at the table's top border"
            assert thead.region.height == 3
            assert table.region.bottom == body.region.bottom, "and end at the table's bottom border"
            body.scroll_home(animate=False)
            await pilot.pause(0.2)
            assert thead.region.y == body.region.y  # the column names stay put while rows scroll under them

    run(scenario())


def test_coin_is_centred_in_the_space_right_of_the_table(tmp_path):
    async def scenario():
        app = make_app(tmp_path)
        async with app.run_test(size=(130, 50)) as pilot:
            assert await until(pilot, lambda: app.state.windows and app.state.quotes)
            app.refresh_view()
            await pilot.pause(0.2)
            body, coin, main = app.query_one("#body"), app.query_one("#coin"), app.query_one("#main")
            free_middle = (body.region.right + 130) / 2
            assert abs(coin.region.x + coin.region.width / 2 - free_middle) <= 1, "coin is not centred horizontally"
            main_middle = main.region.y + main.region.height / 2
            assert abs(coin.region.y + coin.region.height / 2 - main_middle) <= 1, "coin is not centred vertically"

    run(scenario())
