# BTC15 Terminal Widget Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A live terminal widget (`btc15-widget`, also `pm widget`) showing the 24-hour window strip, the live window, odds, the exchange-proxy price and a countdown, with dark/light/system themes.

**Architecture:** A pure `WidgetState` (no I/O, injected clock) plus pure renderers returning `rich.text.Text`; a thin Textual app wires the core's data sources into the state and repaints. Everything except the app shell is unit-tested without a terminal. The desktop window and desktop shortcut are later plans and reuse `WidgetState` and the renderers.

**Tech Stack:** Python >=3.12, Textual (adds Rich; record the resolved version), existing `btc15_widget` core modules, pytest.

**Spec:** `docs/superpowers/specs/2026-09-30-btc15-widget-design.md` (core plan: `docs/superpowers/plans/2026-09-30-btc15-core.md`)

## Global Constraints

- Result marks: **green = UP, red = DOWN**. Net-change fill: **positive = blue, negative = orange**, 9 steps (0-10, 10-25, 25-50, 50-100, 100-200, 200-300, 300-400, 400-500, 500-1000, capped) via `colors.net_color` / `colors.result_color`.
- Strip = last **96 windows (24h)** of real settled BRTI, plus the live window shown separately. **Proxy values never enter history**; the live window's colours are provisional until Polymarket publishes `settlementPrice`.
- Live BTC price is the exchange composite, always displayed with "≈" and its measured error.
- Theme: `dark` / `light` / `system`, default `system`, persisted via `theme.save_theme_setting`; background `#0e1117` (dark) / `#ffffff` (light).
- Signals row is display-only and **off**: the recorded-data analysis found no pattern that beats "always UP" (see `data/patterns.md`).
- Read-only: no order placement anywhere. Never print credentials.
- Python >=3.12; all times displayed in America/New_York, stored in UTC.

## Review Focus

1. Terminal narrower than the strip (< 40 columns) or shorter than the layout: a one-line "terminal too small" message, never a crash or garbled wrap.
2. Feed down, all exchanges failing, or data older than 10 s: shows "—" / "stale", never a stale number styled as live.
3. 15-minute rollover: the previous live window stays "pending" (not coloured) until its `settlementPrice` exists, the new window appears with its own open, and no cell is duplicated or shifted.
4. No credentials or history fetch fails at startup: a clear error panel inside the app, `q` still quits cleanly, no traceback.
5. Live window with no price-to-beat (`open is None`, e.g. Polymarket status `RESOLVING`) or no proxy yet: gap shows "—", never `None` or a crash.

---

## File Structure

| File | Responsibility |
|---|---|
| `src/btc15_widget/state.py` | `WidgetState`: holds history, tick, quotes, calibration; derives live window, gap, staleness, refresh need |
| `src/btc15_widget/render.py` | pure renderers: `render_strip`, `render_header`, `render_status`, `render_legend` |
| `src/btc15_widget/sources.py` | `DataSources` (injectable loaders), `run_calibration`, refresh scheduling |
| `src/btc15_widget/app.py` | Textual app: layout, bindings, workers, timers |
| `src/btc15_widget/colors.py` (modify) | add `BACKGROUND` |
| `src/btc15_widget/cli.py` (modify) | `pm widget` |
| `tests/test_state.py`, `test_render.py`, `test_sources.py`, `test_app.py` | one per module |

---

### Task 1: WidgetState

**Files:**
- Create: `src/btc15_widget/state.py`, `tests/test_state.py`

**Interfaces:**
- Consumes: `Window`, `LiveTick`, `Calibration`, `windows.floor_window`, `proxy.composite`, `proxy.apply_bias`.
- Produces: `STALE_SECONDS = 10`; `@dataclass WidgetState(windows: list[Window] = [], tick: LiveTick | None = None, tick_at: datetime | None = None, quotes: dict[str, float | None] = {}, quotes_at: datetime | None = None, calibration: Calibration | None = None, feed_status: str = "connecting", error: str | None = None, history_at: datetime | None = None)` with methods `set_history(windows, now)`, `apply_tick(tick, now)`, `apply_quotes(quotes, now)`, `strip_windows(now) -> list[Window]` (exactly 96 windows ending at the window before `floor_window(now)`; any missing start becomes a placeholder `Window(start, None, None)` so nothing shifts), `live_window(now) -> Window` (window starting at `floor_window(now)`, placeholder if absent), `proxy_price(now) -> float | None` (composite, plus `calibration.bias` negated when `calibration.n >= 8`; `None` when quotes are older than `STALE_SECONDS` or empty), `gap(now) -> float | None` (`proxy_price - live_window.open`, `None` if either missing), `is_stale(kind: "tick"|"quotes", now) -> bool`, `needs_history_refresh(now) -> bool` (True when: no history; or `floor_window(now)` has no entry in `windows`; or any window before the live one is unsettled and `history_at` is over 20 s old; or `history_at` is over 300 s old).

- [ ] **Step 1: Write the failing tests** in `tests/test_state.py` with a fixed `NOW = 2026-09-30 09:20Z` and a helper building settled windows: `test_strip_windows_is_96_ending_before_live` (history of 97 -> 96 returned; with `NOW` 09:20Z the live window starts 09:15Z, so the last strip start is `floor(now) - 15min` and the first is `floor(now) - 24h`); `test_strip_fills_missing_windows_in_place` (drop the 5th window -> placeholder at that start, neighbours unmoved); `test_rollover_keeps_previous_window_pending` (history loaded at 09:10, `now` 09:16: `live_window(now).start == 09:15Z`, placeholder with `open None`; the 09:00Z window unsettled stays unsettled in `strip_windows`); `test_proxy_price_applies_bias_only_with_enough_samples` (quotes `{a: 100, b: 102}`, calibration `bias=-4, n=8` -> `105.0`; `n=3` -> `101.0`); `test_proxy_price_none_when_stale_or_empty` (quotes 11 s old -> None; `{}` -> None); `test_gap_none_without_open_or_proxy`; `test_gap_value` (proxy 105, open 100 -> 5.0); `test_needs_refresh_rules` (empty -> True; fresh and complete -> False; missing live window -> True; unsettled previous window and `history_at` 25 s ago -> True, 10 s ago -> False; 301 s ago -> True).
- [ ] **Step 2: Run** `uv run pytest tests/test_state.py -v` — expect FAIL (import error).
- [ ] **Step 3: Implement** `WidgetState` per the interface (index `windows` by `start` for the placeholder logic).
- [ ] **Step 4: Run** the same command — expect all PASS.
- [ ] **Step 5: Commit** `feat: widget state`.

### Task 2: Strip and legend renderer

**Files:**
- Create: `src/btc15_widget/render.py`, `tests/test_render.py`
- Modify: `src/btc15_widget/colors.py` (add `BACKGROUND = {"dark": "#0e1117", "light": "#ffffff"}`), `tests/test_colors.py` (use it in place of the local `BG`)

**Interfaces:**
- Consumes: `Window`, `colors.net_color`, `colors.result_color`, `colors.BACKGROUND`.
- Produces: `CELLS_PER_ROW = 24`; `render_strip(windows: list[Window], theme: str) -> rich.text.Text` (rows of 24 cells, oldest first, each row prefixed `"MM-DD HH:MM "` in ET of its first window; a settled window is the glyph `▌` with foreground `result_color` and background `net_color`; an unsettled/pending window is a dim `?`; a gap (`error` set) is a dim `·`); `render_legend(theme: str) -> rich.text.Text` (explains left half = result, right half = net change, and shows the 9 blue and 9 orange steps with their upper edges).

- [ ] **Step 1: Write the failing tests** in `tests/test_render.py` (inspect `Text.plain` and `Text.spans` / `Text.get_style_at_offset`): `test_strip_layout` (96 windows -> 4 lines, each prefix + 24 glyphs); `test_settled_cell_uses_result_fg_and_net_bg` (UP, net +50, dark theme: fg `result_color("UP","dark")`, bg `net_color(50,"dark")`; DOWN, net -300: red fg, orange bg); `test_pending_and_gap_cells` (`?` and `·`, both dim, never green/red/blue/orange); `test_first_prefix_is_eastern_time` (a window starting 2026-09-30 13:00Z shows `09-30 09:00`); `test_light_theme_uses_light_palette`; `test_legend_lists_all_bands` (contains `10`, `25`, `50`, `100`, `200`, `300`, `400`, `500`, `1000`).
- [ ] **Step 2: Run** `uv run pytest tests/test_render.py tests/test_colors.py -v` — expect FAIL.
- [ ] **Step 3: Implement** `render_strip` and `render_legend`; rows shorter than 24 (fewer windows than a full row) are not padded.
- [ ] **Step 4: Run** — expect PASS.
- [ ] **Step 5: Commit** `feat: strip and legend renderer`.

### Task 3: Header and status renderer

**Files:**
- Modify: `src/btc15_widget/render.py`, `tests/test_render.py`

**Interfaces:**
- Consumes: `WidgetState` (Task 1), `colors.*`, `windows.seconds_remaining`.
- Produces: `render_header(state: WidgetState, now: datetime, theme: str) -> rich.text.Text` with line 1 `BTC ≈ $83,874.95 (±$4.5)   beat $83,874.16   gap +$0.79 (UP)   ends 07:42` and line 2 `Up 0.62  Down 0.38  spread 0.01   provisional ▌` (the block: fg result colour from the gap's sign, bg `net_color(gap)`, dim); `render_status(state: WidgetState, now: datetime, theme: str) -> rich.text.Text` (feed status, `quotes Ns ago`, `Signals: off (no pattern beat always-UP; see data/patterns.md)`, and the error text when `state.error` is set). Formatting rules: missing/stale price, open or gap -> `—`; stale tick or quotes -> the value replaced by `stale`; Down is `1 - up_price`; countdown `MM:SS`; the error margin `±$X` is `calibration.mean_abs_error` (omitted with no calibration).

- [ ] **Step 1: Write the failing tests:** `test_header_full` (complete state -> contains `≈ $83,874.95`, `beat $83,874.16`, `gap +$0.79 (UP)`, `ends` countdown, `Up 0.62  Down 0.38`); `test_header_down_gap_sign` (gap -12.3 -> `-$12.30 (DOWN)`); `test_header_no_open_shows_dash` (Review Focus 5: live `open None` -> `beat —` and `gap —`, no `None` in output); `test_header_no_proxy_shows_dash`; `test_stale_data_is_labelled_not_shown` (quotes 15 s old -> `stale`, and the old price string absent); `test_status_shows_error_and_signals_off`; `test_countdown_format` (live window 09:15Z at `now` 09:20:00Z -> `10:00` remaining; at 09:29:59Z -> `00:01`; at 09:30Z -> `00:00`; always `MM:SS` zero-padded).
- [ ] **Step 2: Run** `uv run pytest tests/test_render.py -v` — expect FAIL on the new tests.
- [ ] **Step 3: Implement** both renderers.
- [ ] **Step 4: Run** — expect PASS.
- [ ] **Step 5: Commit** `feat: header and status renderer`.

### Task 4: Data sources and scheduling

**Files:**
- Create: `src/btc15_widget/sources.py`, `tests/test_sources.py`

**Interfaces:**
- Consumes: `history.load_history`, `proxy.fetch_quotes`, `calibration.fetch_candles`/`measure`, `feed.LiveFeed`, `client.get_client`, `WidgetState`.
- Produces: `@dataclass DataSources(load_history: Callable[[datetime], list[Window]], fetch_quotes: Callable[[], dict[str, float|None]], fetch_candles: Callable[[datetime, datetime], dict], feed_factory: Callable[[Callable[[LiveTick], None]], LiveFeed])`; `default_sources() -> DataSources` (real: `get_client()` once, `load_history(client, now, 24, cache_path=HISTORY_CACHE)`, etc.; raises `RuntimeError` on missing credentials); `run_calibration(state: WidgetState, sources: DataSources, now: datetime) -> Calibration | None` (measures over the **last 4 hours** of settled windows so Coinbase's 300-candle cap is respected; stores on `state.calibration`; returns None and leaves state unchanged on failure); `CALIBRATION_EVERY = 1800` and `QUOTES_EVERY = 2.0` seconds constants.

- [ ] **Step 1: Write the failing tests** with fakes: `test_default_sources_needs_credentials` (env cleared, dotenv patched -> `RuntimeError`); `test_run_calibration_uses_last_four_hours` (fake `fetch_candles` records its `(start, end)`: `end - start <= 4.5h`; fake history of 24h, result `Calibration.n` only counts the last 4h of windows); `test_run_calibration_failure_keeps_state` (fake raises -> returns None, `state.calibration` unchanged); `test_run_calibration_sets_state`.
- [ ] **Step 2: Run** `uv run pytest tests/test_sources.py -v` — expect FAIL.
- [ ] **Step 3: Implement** `DataSources`, `default_sources`, `run_calibration`.
- [ ] **Step 4: Run** — expect PASS.
- [ ] **Step 5: Commit** `feat: injectable data sources and calibration`.

### Task 5: Textual app

**Files:**
- Create: `src/btc15_widget/app.py`, `tests/test_app.py`
- Modify: `pyproject.toml` (add `textual` dependency; run `uv sync`; record the resolved version in the commit message)

**Interfaces:**
- Consumes: Tasks 1-4, `theme.load_theme_setting`/`save_theme_setting`/`resolve_theme`/`DEFAULT_CONFIG_PATH`.
- Produces: `class WidgetApp(App)` with `__init__(self, sources: DataSources | None = None, config_path: Path = DEFAULT_CONFIG_PATH, clock: Callable[[], datetime] = utcnow)`; bindings `q` quit, `t` cycle theme (dark -> light -> system, saved immediately, repaint), `r` force refresh; on mount: a background worker loads history (`state.set_history`), calibration runs once then every `CALIBRATION_EVERY`, a worker polls `fetch_quotes` every `QUOTES_EVERY`, a worker runs `LiveFeed.run` (status `live` on first tick, `reconnecting` after it exits early), a 1 s timer repaints the header/status (countdown) and re-checks `needs_history_refresh`. Startup failures set `state.error` (never raised) and the status panel shows them. Fewer than 40 columns or 12 rows shows only `Terminal too small (need 40x12)`. `snapshot_text(state, now, theme) -> str` (plain text of header + strip + legend + status, used by `--snapshot`).

- [ ] **Step 1: Write the failing tests** using `App.run_test()` (Textual Pilot) and fake `DataSources` (history of 97 windows, a scripted tick feed, fixed quotes, fixed clock): `test_app_renders_header_strip_and_legend` (after settling, the screen text contains `≈ $`, `beat $`, four strip rows, `Signals: off`); `test_q_quits`; `test_t_cycles_theme_and_persists` (start with saved theme `dark`: first `t` -> config JSON theme `light`, second `t` -> `system`, third -> `dark`); `test_startup_error_shows_panel_not_traceback` (history loader raises `RuntimeError("Missing credentials")` -> text shows it and `q` still exits cleanly); `test_too_small_terminal` (`run_test(size=(30, 8))` -> message only); `test_rollover_repaint` (advance the injected clock across 09:30Z: live window start changes, strip still 96 cells, previous window renders `?` until the fake history returns it settled).
- [ ] **Step 2: Run** `uv run pytest tests/test_app.py -v` — expect FAIL.
- [ ] **Step 3: Implement** `WidgetApp` and `snapshot_text`; use `run_worker` (thread workers for the blocking loaders, an async worker for the feed); repaint via `Static.update(render_*(...))`; set the screen background from `colors.BACKGROUND`.
- [ ] **Step 4: Run** `uv run pytest -q` — entire suite PASS.
- [ ] **Step 5: Commit** `feat: terminal widget app`.

### Task 6: Entry points, docs and live smoke test

**Files:**
- Modify: `pyproject.toml` (script `btc15-widget = "btc15_widget.app:main"`), `src/btc15_widget/cli.py` (`pm widget`), `README.md`, `CLAUDE.md`, `tests/test_cli.py`
- Create: `tests/test_widget_entry.py`

**Interfaces:**
- Consumes: `WidgetApp`, `default_sources`, `snapshot_text`.
- Produces: `app.main(argv: list[str] | None = None) -> None` with flags `--snapshot` (load data once, print `snapshot_text`, exit; no TUI), `--theme dark|light|system` (overrides and saves the setting); `pm widget` delegates to it.

- [ ] **Step 1: Write the failing tests:** `test_pm_has_widget_command`; `test_main_snapshot_prints_and_exits` (injected fake sources, `capsys`: output contains `≈ $` and the legend, return without starting the app); `test_theme_flag_persists` (`--theme light` -> config JSON `light`); `test_missing_credentials_message` (snapshot with failing sources prints `Error: Missing ...` to stderr, exit code 1).
- [ ] **Step 2: Run** `uv run pytest tests/test_widget_entry.py tests/test_cli.py -v` — expect FAIL.
- [ ] **Step 3: Implement** `main` and the `pm widget` subcommand; update README/CLAUDE.md command lists.
- [ ] **Step 4: Run** `uv run pytest -q` — all PASS. Then the live smoke test: `uv run btc15-widget --snapshot` prints a full snapshot with a real price, real strip colours and the legend; run `uv run btc15-widget` in a real terminal for 30 s and confirm it updates, `t` switches theme, and `q` exits. Report what was seen; note that only the `--snapshot` path can be verified without a human at a terminal.
- [ ] **Step 5: Commit** `feat: btc15-widget entry points and docs`.

---

## Self-Review Notes

- **Spec coverage:** header (price ≈, beat, gap, countdown) T3; odds/spread T3; 96-window strip with result mark + net-change gradient T2; dark/light/system incl. live toggle and persistence T5-6; provisional live colours T3; signals row off T3; terminal widget as step 2 of the architecture T5; `pm widget` T6. **Not in this plan by design:** the native desktop window and the desktop shortcut.
- **Type consistency:** `WidgetState`, `DataSources`, `render_strip/header/status/legend`, `snapshot_text` are named identically across tasks; `Window`, `LiveTick`, `Calibration` come from the core unchanged.
- **Known limits carried from the core:** candle fetching is capped (Coinbase 300 candles), hence the 4-hour calibration window; a window stuck in `RESOLVING` has no open and shows `—`.
