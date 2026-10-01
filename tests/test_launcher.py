import pytest

from btc15_widget import launcher


def test_normal_exit_returns_zero_without_waiting():
    waited = []
    assert launcher.run(lambda: None, wait=lambda: waited.append(1), interactive=True) == 0
    assert waited == []


def test_a_crash_is_explained_and_the_window_waits_for_enter(capsys):
    waited = []

    def boom():
        raise RuntimeError("network unreachable")

    code = launcher.run(boom, wait=lambda: waited.append(1), interactive=True)
    out = capsys.readouterr().err
    assert code == 1 and waited == [1]
    assert "network unreachable" in out and "github.com" in out  # says what happened and where to report it
    assert "Traceback" not in out  # no wall of text for a non-technical user


def test_no_waiting_when_not_attached_to_a_terminal(capsys):
    waited = []
    assert launcher.run(lambda: (_ for _ in ()).throw(RuntimeError("x")), wait=lambda: waited.append(1), interactive=False) == 1
    assert waited == []  # scripts and pipes must never hang on input()


def test_ctrl_c_is_a_clean_exit():
    def interrupted():
        raise KeyboardInterrupt

    assert launcher.run(interrupted, wait=lambda: None, interactive=True) == 0


def test_sys_exit_codes_pass_through():
    def argparse_style_exit():
        raise SystemExit(2)

    assert launcher.run(argparse_style_exit, wait=lambda: None, interactive=False) == 2

    def clean_exit_with_message():
        raise SystemExit("Error: rate limited")

    assert launcher.run(clean_exit_with_message, wait=lambda: None, interactive=False) == 1
