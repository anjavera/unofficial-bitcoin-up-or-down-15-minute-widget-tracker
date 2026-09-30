import json
from datetime import datetime, timezone

import pytest

from btc15_widget import cli
from btc15_widget.model import Window

T = datetime(2026, 9, 30, 9, 0, tzinfo=timezone.utc)


def test_parser_has_all_commands():
    parser = cli.build_parser()
    for argv in (["account"], ["balances"], ["positions"], ["orders"], ["search", "bitcoin"],
                 ["price", "slug"], ["book", "slug"], ["market", "slug"], ["event", "slug"],
                 ["btc15"], ["btc15", "--hours", "2"]):
        assert parser.parse_args(argv).command == argv[0]
    assert parser.parse_args(["btc15"]).hours == 6


def test_no_order_commands():
    parser = cli.build_parser()
    choices = next(a.choices for a in parser._actions if a.dest == "command")
    assert not {"create", "modify", "cancel", "close", "order", "buy", "sell"} & set(choices)


def windows():
    return [
        Window(T, open=100.0, close=110.0, status="RESOLVED", volume=1000.0),
        Window(datetime(2026, 9, 30, 9, 15, tzinfo=timezone.utc), open=110.0, close=105.0, status="RESOLVED"),
        Window(datetime(2026, 9, 30, 9, 30, tzinfo=timezone.utc), open=None, close=None, error="boom"),
        Window(datetime(2026, 9, 30, 9, 45, tzinfo=timezone.utc), open=105.0, close=None, status="OPEN"),
    ]


def test_btc15_table_renders_up_down_gap_and_live(capsys):
    cli.print_table(windows())
    out = capsys.readouterr().out
    assert "UP" in out and "DOWN" in out and "LIVE" in out and "gap" in out
    assert "1 up / 1 down" in out
    assert "+10.00" in out and "-5.00" in out


def test_btc15_json_has_iso_dates_net_and_result():
    data = cli.windows_to_json(windows())
    assert data[0]["start"] == "2026-09-30T09:00:00+00:00"
    assert data[0]["net"] == 10.0 and data[0]["result"] == "UP"
    assert data[2]["error"] == "boom" and data[3]["result"] is None
    json.dumps(data)  # serialisable


def test_usd_formatting():
    assert cli.usd(None) == "-"
    assert cli.usd({"value": "0.0100"}) == "$0.0100"
