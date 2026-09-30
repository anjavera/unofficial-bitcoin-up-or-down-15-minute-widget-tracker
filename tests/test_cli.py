import json
from datetime import datetime, timezone

import pytest

from btc15_widget import cli
from btc15_widget.colors import net_color, result_color
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


def cells(table, name):
    col = next(c for c in table.columns if c.header == name)
    return list(col._cells)


def styled_table(theme="dark"):
    return cli.build_table(windows(), theme)


def test_table_is_a_grid_with_the_expected_columns():
    table = styled_table()
    assert [c.header for c in table.columns] == ["Window (ET)", "Open", "Close", "Chg $", "Chg %", "Result", "Volume"]
    assert table.show_lines is False and table.row_styles and table.box is not None
    assert len(table.rows) == 4


def test_change_cells_are_filled_with_the_net_gradient():
    for theme in ("dark", "light"):
        table = styled_table(theme)
        for name in ("Chg $", "Chg %"):
            up, down = cells(table, name)[0], cells(table, name)[1]
            assert up.style.bgcolor.get_truecolor().hex == net_color(10.0, theme)
            assert down.style.bgcolor.get_truecolor().hex == net_color(-5.0, theme)
            assert up.style.color is not None  # readable text colour chosen for the fill


def test_result_cells_are_filled_green_or_red():
    table = styled_table("dark")
    up, down, gap, live = cells(table, "Result")
    assert up.plain.strip() == "UP" and up.style.bgcolor.get_truecolor().hex == result_color("UP", "dark")
    assert down.plain.strip() == "DOWN" and down.style.bgcolor.get_truecolor().hex == result_color("DOWN", "dark")
    assert live.plain.strip() == "LIVE" and live.style.bgcolor is None  # provisional: no fill


def test_unsettled_and_gap_rows_have_no_gradient():
    table = styled_table()
    for name in ("Chg $", "Chg %"):
        gap_cell, live_cell = cells(table, name)[2], cells(table, name)[3]
        assert gap_cell.style.bgcolor is None and live_cell.style.bgcolor is None
    assert "gap" in cells(table, "Window (ET)")[2].plain or "gap" in "".join(c.plain for c in cells(table, "Result"))


@pytest.mark.parametrize("theme", ["dark", "light"])
def test_striped_rows_set_their_own_text_colour(theme):
    from rich.style import Style

    stripe = Style.parse(styled_table(theme).row_styles[1])
    assert stripe.color is not None and stripe.bgcolor is not None  # readable whatever the terminal's own colours
