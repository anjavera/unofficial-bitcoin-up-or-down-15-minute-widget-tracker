from datetime import datetime, timezone

from btc15_widget.windows import floor_window, window_slugs

UTC = timezone.utc


def test_floor_window_rounds_down_to_quarter_hour():
    assert floor_window(datetime(2026, 9, 30, 9, 29, 59, tzinfo=UTC)) == datetime(2026, 9, 30, 9, 15, tzinfo=UTC)
    assert floor_window(datetime(2026, 9, 30, 9, 30, 0, tzinfo=UTC)) == datetime(2026, 9, 30, 9, 30, tzinfo=UTC)


def test_window_slugs_cross_midnight():
    slugs = window_slugs(datetime(2026, 9, 30, 23, 50, tzinfo=UTC), 3)
    assert slugs == [
        "cpc-btc-updown-15m-2026-09-30-2345z",
        "cpc-btc-updown-15m-2026-10-01-0000z",
        "cpc-btc-updown-15m-2026-10-01-0015z",
    ]


def test_window_slugs_can_start_in_the_past():
    slugs = window_slugs(datetime(2026, 9, 30, 10, 0, tzinfo=UTC), 2, back=1)
    assert slugs[0] == "cpc-btc-updown-15m-2026-09-30-0945z"
    assert len(slugs) == 3


def test_event_slug():
    from btc15_widget.windows import event_slug

    assert event_slug(datetime(2026, 9, 30, 9, 15, tzinfo=UTC)) == "btc-updown-15m-2026-09-30-0915z"


def test_seconds_remaining_clamps_at_zero():
    from btc15_widget.windows import seconds_remaining

    start = datetime(2026, 9, 30, 9, 0, tzinfo=UTC)
    assert seconds_remaining(datetime(2026, 9, 30, 9, 10, tzinfo=UTC), start) == 300
    assert seconds_remaining(datetime(2026, 9, 30, 9, 20, tzinfo=UTC), start) == 0
