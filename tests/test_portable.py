import inspect
import io
import tomllib
from pathlib import Path

import pytest

from btc15_widget import client, history, paths
from btc15_widget.textio import ensure_utf8_output

ROOT = Path(__file__).resolve().parents[1]


def test_data_lives_in_per_user_app_directories():
    assert "btc15-widget" in paths.cache_dir().parts and "btc15-widget" in paths.config_dir().parts
    assert paths.env_file().name == ".env" and paths.env_file().parent == paths.config_dir()
    assert history.HISTORY_CACHE == paths.cache_dir() / "history.json"


def test_directories_follow_the_platform_conventions(monkeypatch, tmp_path):
    import sys

    if not sys.platform.startswith("linux"):
        pytest.skip("XDG variables only apply on Linux")
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    assert paths.cache_dir() == tmp_path / "cache" / "btc15-widget"
    assert paths.config_dir() == tmp_path / "config" / "btc15-widget"


def test_no_personal_paths_are_baked_into_the_code():
    for module in (client, history, paths):
        source = inspect.getsource(module)
        assert "polymarket-bot" not in source, f"{module.__name__} mentions the author's own folder"


def test_keys_are_read_from_the_user_config_dir(monkeypatch, tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("POLYMARKET_KEY_ID=the-id\nPOLYMARKET_SECRET_KEY=the-secret\n")
    monkeypatch.setattr(client, "env_file", lambda: env_file)
    monkeypatch.setattr(client, "find_dotenv", lambda **kw: "")  # nothing in the working directory
    monkeypatch.delenv("POLYMARKET_KEY_ID", raising=False)
    monkeypatch.delenv("POLYMARKET_SECRET_KEY", raising=False)
    assert client.has_credentials() is True
    assert client.load_credentials() == ("the-id", "the-secret")


def test_timezone_data_is_a_declared_dependency():
    """Windows has no system tz database: zoneinfo needs the `tzdata` package or the widget dies at import."""
    deps = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["dependencies"]
    assert any(d.lower().startswith("tzdata") for d in deps)
    assert any(d.lower().startswith("platformdirs") for d in deps)


def test_utf8_output_survives_a_legacy_windows_code_page():
    raw = io.BytesIO()
    stream = io.TextIOWrapper(raw, encoding="cp1252", errors="strict", write_through=True)
    with pytest.raises(UnicodeEncodeError):
        stream.write("≈ ▌ ·")  # the crash this guards against
    stream = io.TextIOWrapper(io.BytesIO(), encoding="cp1252", errors="strict", write_through=True)
    ensure_utf8_output([stream])
    stream.write("BTC ≈ $83,000  ▌ ·")  # must not raise now
    assert stream.encoding.lower().replace("-", "") == "utf8"


def test_utf8_output_leaves_streams_without_reconfigure_alone():
    class Plain:
        encoding = "ascii"

    ensure_utf8_output([Plain()])  # no error
