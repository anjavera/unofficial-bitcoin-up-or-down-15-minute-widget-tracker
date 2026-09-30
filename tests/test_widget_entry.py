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
    app_module.main(argv, sources=sources, config_path=tmp_path / "config.json", clock=lambda: NOW)


def test_main_snapshot_prints_and_exits(tmp_path, capsys):
    run_main(["--snapshot"], tmp_path, fake_sources())
    out = capsys.readouterr().out
    assert "≈ $84,000.50" in out and "beat $84,000.00" in out
    assert "Up 0.62" in out and "net up" in out and "Signals: off" in out


def test_theme_flag_persists(tmp_path, capsys):
    run_main(["--snapshot", "--theme", "light"], tmp_path, fake_sources())
    assert json.loads((tmp_path / "config.json").read_text()) == {"theme": "light"}


def test_missing_credentials_message(tmp_path, capsys, monkeypatch):
    def no_creds():
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
    cli.main(["widget", "--snapshot", "--theme", "dark"])
    assert seen == [["--snapshot", "--theme", "dark"]]
