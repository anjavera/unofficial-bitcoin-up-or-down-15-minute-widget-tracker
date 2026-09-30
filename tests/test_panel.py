import math

import pytest
from rich.style import Style

from btc15_widget.colors import result_color
from btc15_widget.panel import dial_pixels, panel_layout, render_dial, render_logo


def kinds(grid):
    return {k for row in grid for k in row}


def at(grid, x, y):
    return grid[y][x]


@pytest.mark.parametrize("size", [20, 28])
def test_dial_is_a_square_grid_with_transparent_corners(size):
    grid = dial_pixels(450, size)
    assert len(grid) == size and all(len(row) == size for row in grid)
    assert at(grid, 0, 0) == "out" and at(grid, size - 1, size - 1) == "out"


def test_full_window_has_nothing_elapsed_and_the_hand_points_to_twelve():
    grid = dial_pixels(900, 28)
    assert "elapsed" not in kinds(grid) and "remaining" in kinds(grid)
    hand_xs = [x for y, row in enumerate(grid) for x, k in enumerate(row) if k == "hand" and y < 12]
    assert hand_xs and all(abs(x - 13.5) <= 1.5 for x in hand_xs)  # straight up from the centre


def test_half_window_splits_the_face_down_the_middle_with_the_hand_at_six():
    grid = dial_pixels(450, 28)
    c = 13
    assert at(grid, c - 6, c) == "remaining" and at(grid, c + 6, c + 4) == "elapsed"  # left half left, right half used up
    hand = [(x, y) for y, row in enumerate(grid) for x, k in enumerate(row) if k == "hand"]
    assert hand and all(y >= c and abs(x - 13.5) <= 1.5 for x, y in hand)  # one revolution per window: half gone = 6 o'clock


def test_empty_window_has_no_wedge_left():
    assert "remaining" not in kinds(dial_pixels(0, 28))


def test_wedge_shrinks_as_time_runs_out():
    counts = [sum(row.count("remaining") for row in dial_pixels(s, 28)) for s in (900, 600, 300, 60)]
    assert counts == sorted(counts, reverse=True) and counts[0] > counts[-1] > 0


def test_dial_has_a_tick_for_each_minute():
    ticks = sum(row.count("tick") for row in dial_pixels(450, 28))
    assert ticks >= 15


def test_render_dial_shows_digital_time_and_lean_colour():
    text = render_dial(450, "UP", "dark", 20)
    lines = text.plain.split("\n")
    assert len(lines) == 20 // 2 + 1 and lines[-1].strip() == "07:30"
    used = {str(s.style.color.get_truecolor().hex) for s in text.spans if s.style.color} | {
        str(s.style.bgcolor.get_truecolor().hex) for s in text.spans if s.style.bgcolor}
    assert result_color("UP", "dark") in used
    down = render_dial(450, "DOWN", "dark", 20)
    used_down = {str(s.style.color.get_truecolor().hex) for s in down.spans if s.style.color} | {
        str(s.style.bgcolor.get_truecolor().hex) for s in down.spans if s.style.bgcolor}
    assert result_color("DOWN", "dark") in used_down and result_color("UP", "dark") not in used_down


def test_render_dial_without_a_lean_is_neutral():
    text = render_dial(450, None, "dark", 20)
    colours = {str(s.style.color.get_truecolor().hex) for s in text.spans if s.style.color}
    assert result_color("UP", "dark") not in colours and result_color("DOWN", "dark") not in colours


def test_render_dial_clamps_out_of_range_time():
    assert render_dial(-5, "UP", "dark", 20).plain.split("\n")[-1].strip() == "00:00"
    assert render_dial(5000, "UP", "dark", 20).plain.split("\n")[-1].strip() == "15:00"


@pytest.mark.parametrize("size", [20, 28])
def test_logo_is_block_art_in_bitcoin_colours(size):
    text = render_logo(size)
    lines = text.plain.split("\n")
    assert len(lines) == size // 2 and all(len(line) == size for line in lines)
    colours = {str(s.style.color.get_truecolor().hex) for s in text.spans if s.style.color}
    assert "#f7931a" in colours and "#ffffff" in colours


def test_logo_rejects_unknown_sizes():
    with pytest.raises(ValueError):
        render_logo(13)


@pytest.mark.parametrize(
    "width, height, expected",
    [(200, 50, (28, True)), (112, 41, (28, True)), (111, 50, (20, True)), (104, 33, (20, True)),
     (104, 32, (20, False)), (200, 22, (20, False)), (103, 40, None), (200, 21, None), (80, 24, None)],
)
def test_panel_layout_fits_the_terminal(width, height, expected):
    assert panel_layout(width, height) == expected
