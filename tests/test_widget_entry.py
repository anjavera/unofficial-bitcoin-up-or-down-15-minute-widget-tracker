import json
from datetime import datetime, timedelta, timezone

import pytest

from btc15_widget import app as app_module
from btc15_widget import cli
from btc15_widget.model import LiveTick, Window
from btc15_widget.sources import DataSources
from btc15_widget.windows import MARKET_SLUG, floor_window

UTC = timezone.utc
NOW = datetime(2026, 9, 30, 9, 20, tzinfo=UTC)
STEP = timedelta(minutes=15)


def history():
    live = floor_window(NOW)
    return [Window(live - i * STEP, open=84000.0 + i, close=None if i == 0 else 84001.0 + i, status="OPEN" if i == 0 else "RESOLVED")
            for i in range(96, -1, -1)]


class FakeFeed:
    def __init__(self, on_tick):
        self.on_tick = on_tick

    async def run(self, stop):
        self.on_tick(LiveTick(MARKET_SLUG.format(floor_window(NOW)), 0.62, 0.61, 0.62, 0.62, 10.0))
        await stop.wait()


def fake_sources():
    return DataSources(
        load_history=lambda now: history(),
        fetch_quotes=lambda: {"a": 84000.5},
        fetch_candles=lambda start, end: (_ for _ in ()).throw(OSError("no candles")),
        feed_factory=lambda on_tick: FakeFeed(on_tick),
    )


def run_main(argv, tmp_path, sources=None):
    app_module.main(argv, sources=sources, clock=lambda: NOW)


def test_main_snapshot_prints_and_exits(tmp_path, capsys):
    run_main(["--snapshot"], tmp_path, fake_sources())
    out = capsys.readouterr().out
    assert "≈ $84,000.50" in out and "beat $84,000.00" in out
    assert "Up 0.62" in out and "net up" in out and "Signals: off" in out


def test_theme_option_is_gone(tmp_path, capsys):
    with pytest.raises(SystemExit):
        run_main(["--snapshot", "--theme", "light"], tmp_path, fake_sources())
    assert not (tmp_path / "config.json").exists()


def test_missing_credentials_message(tmp_path, capsys, monkeypatch):
    def no_creds(**kwargs):
        raise RuntimeError("Missing POLYMARKET_KEY_ID / POLYMARKET_SECRET_KEY")

    monkeypatch.setattr(app_module, "default_sources", no_creds)
    with pytest.raises(SystemExit) as exit_info:
        run_main(["--snapshot"], tmp_path, None)
    assert exit_info.value.code == 1
    assert "Error: Missing POLYMARKET_KEY_ID" in capsys.readouterr().err


def test_pm_has_widget_command():
    assert cli.build_parser().parse_args(["widget"]).command == "widget"


def test_pm_widget_delegates_without_needing_a_client(monkeypatch):
    seen = []
    monkeypatch.setattr(app_module, "main", lambda argv=None, **kw: seen.append(argv))
    monkeypatch.setattr(cli, "get_client", lambda: (_ for _ in ()).throw(AssertionError("widget must not build a client")))
    cli.main(["widget", "--snapshot"])
    assert seen == [["--snapshot"]]


def test_pm_widget_has_no_theme_option():
    with pytest.raises(SystemExit):
        cli.build_parser().parse_args(["widget", "--theme", "dark"])


def test_keyless_flag_tells_default_sources_to_ignore_keys(tmp_path, monkeypatch, capsys):
    seen = []

    def fake_default(**kwargs):
        seen.append(kwargs)
        return fake_sources()

    monkeypatch.setattr(app_module, "default_sources", fake_default)
    run_main(["--snapshot"], tmp_path, None)
    run_main(["--snapshot", "--keyless"], tmp_path, None)
    assert seen == [{"use_keys": True}, {"use_keys": False}]


def test_pm_widget_passes_keyless_through(monkeypatch):
    seen = []
    monkeypatch.setattr(app_module, "main", lambda argv=None, **kw: seen.append(argv))
    cli.main(["widget", "--keyless"])
    assert seen == [["--keyless"]]


def test_snapshot_explains_a_missing_live_market_without_waiting_for_a_tick(tmp_path, capsys):
    import time
    from btc15_widget.history import NO_MARKET

    def no_live_market(now):
        ws = history()
        ws[-1] = Window(ws[-1].start, open=None, close=None, error=NO_MARKET)
        return ws

    class NeverTicks:
        def __init__(self, on_tick):
            pass

        async def run(self, stop):
            await stop.wait()

    sources = fake_sources()
    sources.load_history = no_live_market
    sources.feed_factory = lambda on_tick: NeverTicks(on_tick)
    started = time.monotonic()
    run_main(["--snapshot"], tmp_path, sources)
    assert time.monotonic() - started < 3  # the 5 s tick timeout is skipped when there is no market to listen to
    assert "feed: no market yet" in capsys.readouterr().out


def test_version_flag_prints_the_version_and_exits(capsys):
    with pytest.raises(SystemExit) as exit_info:
        app_module.main(["--version"])
    assert exit_info.value.code == 0
    assert capsys.readouterr().out.strip().startswith("btc15-widget ")
