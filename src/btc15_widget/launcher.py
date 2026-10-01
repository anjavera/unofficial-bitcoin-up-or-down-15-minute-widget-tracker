"""Entry point for the downloadable apps: runs the widget and keeps the window readable if something goes wrong."""

import sys
from collections.abc import Callable

from btc15_widget.textio import ensure_utf8_output

REPORT_URL = "https://github.com/anjavera/unofficial-bitcoin-up-or-down-15-minute-widget-tracker/issues"


def _wait_for_enter() -> None:
    try:
        input("\nPress Enter to close this window...")
    except EOFError:
        pass


def run(main: Callable[[], None] | None = None, wait: Callable[[], None] = _wait_for_enter,
        interactive: bool | None = None) -> int:
    """Run `main`; on a crash print a short explanation and (in a real terminal) wait before the window closes."""
    if main is None:
        from btc15_widget.app import main as widget_main

        main = widget_main
    if interactive is None:
        interactive = sys.stdin is not None and sys.stdin.isatty()
    try:
        main()
    except KeyboardInterrupt:
        return 0
    except SystemExit as e:
        if e.code in (None, 0):
            return 0
        if isinstance(e.code, int):
            return e.code
        print(e.code, file=sys.stderr)
        return 1
    except Exception as e:
        ensure_utf8_output()
        print(f"\nSomething went wrong: {e}\n\nIf this keeps happening, please report it at\n{REPORT_URL}",
              file=sys.stderr)
        if interactive:
            wait()
        return 1
    return 0


def cli() -> None:
    sys.exit(run())


if __name__ == "__main__":
    cli()
