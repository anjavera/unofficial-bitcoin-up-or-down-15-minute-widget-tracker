import pytest

from btc15_widget import cli


def test_pm_has_dashboard_and_watchlist_commands():
    parser = cli.build_parser()
    assert parser.parse_args(["dashboard"]).command == "dashboard"
    assert parser.parse_args(["watchlist", "list"]).command == "watchlist"


def test_dashboard_defaults():
    args = cli.build_parser().parse_args(["dashboard"])
    assert args.categories == "crypto,sports,politics"
    assert args.per_category == 8
    assert args.snapshot is False


def test_dashboard_accepts_custom_categories_and_limit():
    args = cli.build_parser().parse_args(["dashboard", "--categories", "crypto,politics", "--per-category", "3", "--snapshot"])
    assert args.categories == "crypto,politics" and args.per_category == 3 and args.snapshot is True


def test_pm_dashboard_delegates_without_needing_a_client(monkeypatch):
    from btc15_widget.dashboard import app as dashboard_app

    seen = []
    monkeypatch.setattr(dashboard_app, "main", lambda argv=None, **kw: seen.append(argv))
    monkeypatch.setattr(cli, "get_client", lambda: (_ for _ in ()).throw(AssertionError("dashboard must not build a client")))
    cli.main(["dashboard", "--categories", "crypto", "--per-category", "2", "--snapshot"])
    assert seen == [["--categories", "crypto", "--per-category", "2", "--snapshot"]]


def test_watchlist_requires_a_subcommand():
    with pytest.raises(SystemExit):
        cli.build_parser().parse_args(["watchlist"])


class FakeWatchlist:
    instances: list["FakeWatchlist"] = []

    def __init__(self):
        self.added, self.removed = [], []
        FakeWatchlist.instances.append(self)

    def add(self, slug):
        self.added.append(slug)

    def remove(self, slug):
        self.removed.append(slug)

    def __iter__(self):
        return iter(["pinned-a", "pinned-b"])


def test_watchlist_add_pins_the_slug(monkeypatch, capsys):
    FakeWatchlist.instances = []
    monkeypatch.setattr("btc15_widget.dashboard.watchlist.Watchlist", FakeWatchlist)
    cli.main(["watchlist", "add", "my-slug"])
    assert FakeWatchlist.instances[0].added == ["my-slug"]
    assert "pinned my-slug" in capsys.readouterr().out


def test_watchlist_remove_unpins_the_slug(monkeypatch, capsys):
    FakeWatchlist.instances = []
    monkeypatch.setattr("btc15_widget.dashboard.watchlist.Watchlist", FakeWatchlist)
    cli.main(["watchlist", "remove", "my-slug"])
    assert FakeWatchlist.instances[0].removed == ["my-slug"]
    assert "unpinned my-slug" in capsys.readouterr().out


def test_watchlist_list_prints_pinned_slugs(monkeypatch, capsys):
    monkeypatch.setattr("btc15_widget.dashboard.watchlist.Watchlist", FakeWatchlist)
    cli.main(["watchlist", "list"])
    out = capsys.readouterr().out
    assert "pinned-a" in out and "pinned-b" in out


class EmptyWatchlist(FakeWatchlist):
    def __iter__(self):
        return iter([])


def test_watchlist_list_reports_when_empty(monkeypatch, capsys):
    monkeypatch.setattr("btc15_widget.dashboard.watchlist.Watchlist", EmptyWatchlist)
    cli.main(["watchlist", "list"])
    assert "watchlist is empty" in capsys.readouterr().out
