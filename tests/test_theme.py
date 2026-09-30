import subprocess

import pytest

from btc15_widget.theme import (
    THEMES,
    detect_system_theme,
    load_theme_setting,
    resolve_theme,
    save_theme_setting,
)


def fake_run(stdout="", exc=None):
    def run(*args, **kwargs):
        if exc:
            raise exc
        return subprocess.CompletedProcess(args, 0, stdout=stdout)

    return run


def test_themes_constant():
    assert THEMES == ("dark", "light", "system")


def test_resolve_explicit_settings():
    assert resolve_theme("dark") == "dark"
    assert resolve_theme("light") == "light"


def test_resolve_system_uses_hint():
    assert resolve_theme("system", system="light") == "light"
    assert resolve_theme("system", system="dark") == "dark"


def test_resolve_rejects_unknown():
    with pytest.raises(ValueError):
        resolve_theme("sepia")


def test_detect_system_theme_reads_gsettings():
    assert detect_system_theme(run=fake_run("'prefer-dark'\n")) == "dark"
    assert detect_system_theme(run=fake_run("'default'\n")) == "light"
    assert detect_system_theme(run=fake_run("'prefer-light'\n")) == "light"


def test_detect_system_theme_failure_falls_back_to_dark():
    assert detect_system_theme(run=fake_run(exc=FileNotFoundError())) == "dark"
    assert detect_system_theme(run=fake_run(exc=subprocess.TimeoutExpired("gsettings", 2))) == "dark"


def test_config_roundtrip(tmp_path):
    path = tmp_path / "sub" / "config.json"
    save_theme_setting(path, "light")
    assert load_theme_setting(path) == "light"


def test_missing_file_defaults_to_system(tmp_path):
    assert load_theme_setting(tmp_path / "nope.json") == "system"


def test_corrupt_file_defaults_to_system(tmp_path):
    path = tmp_path / "config.json"
    path.write_text("{not json")
    assert load_theme_setting(path) == "system"
    path.write_text('{"theme": "sepia"}')
    assert load_theme_setting(path) == "system"


def test_invalid_setting_rejected(tmp_path):
    with pytest.raises(ValueError):
        save_theme_setting(tmp_path / "config.json", "sepia")
