import json

from btc15_widget.dashboard.watchlist import Watchlist


def test_new_watchlist_is_empty(tmp_path):
    wl = Watchlist(tmp_path / "watchlist.json")
    assert len(wl) == 0 and "any-slug" not in wl and list(wl) == []


def test_add_persists_across_instances(tmp_path):
    path = tmp_path / "watchlist.json"
    Watchlist(path).add("slug-a")
    assert "slug-a" in Watchlist(path)


def test_remove_persists_across_instances(tmp_path):
    path = tmp_path / "watchlist.json"
    wl = Watchlist(path)
    wl.add("slug-a")
    wl.remove("slug-a")
    assert "slug-a" not in Watchlist(path)


def test_toggle_pins_then_unpins_and_returns_new_state(tmp_path):
    wl = Watchlist(tmp_path / "watchlist.json")
    assert wl.toggle("slug-a") is True
    assert "slug-a" in wl
    assert wl.toggle("slug-a") is False
    assert "slug-a" not in wl


def test_iteration_is_sorted(tmp_path):
    wl = Watchlist(tmp_path / "watchlist.json")
    for slug in ("zebra", "alpha", "mango"):
        wl.add(slug)
    assert list(wl) == ["alpha", "mango", "zebra"]


def test_missing_file_is_treated_as_empty(tmp_path):
    assert list(Watchlist(tmp_path / "nested" / "watchlist.json")) == []


def test_corrupt_file_is_treated_as_empty(tmp_path):
    path = tmp_path / "watchlist.json"
    path.write_text("not json")
    assert list(Watchlist(path)) == []


def test_creates_parent_directory_on_save(tmp_path):
    path = tmp_path / "nested" / "dir" / "watchlist.json"
    Watchlist(path).add("slug-a")
    assert json.loads(path.read_text()) == ["slug-a"]
