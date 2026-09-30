import pytest

from btc15_widget.colors import result_color
from btc15_widget.panel import COIN_COLS, COIN_ROWS, coin_cells, panel_layout, render_coin

ORANGE = "#f7931a"


def cells_of(grid, kind):
    return [(r, c) for r, row in enumerate(grid) for c, (_, k) in enumerate(row) if k == kind]


def hex_color(style):
    return style.color.get_truecolor().hex


def test_coin_grid_has_fixed_size():
    grid = coin_cells(0.25)
    assert len(grid) == COIN_ROWS == 15 and all(len(row) == COIN_COLS == 31 for row in grid)


def test_coin_is_a_ring_of_stars_around_a_dollar_sign_b():
    grid = coin_cells(0.25)
    assert {ch for row in grid for ch, k in row if k.startswith("ring") or k == "hand"} == {"*"}
    assert {ch for row in grid for ch, k in row if k == "b"} == {"$"}
    assert len(cells_of(grid, "b")) >= 40
    assert all(ch == " " for row in grid for ch, k in row if k == "space")


def test_the_b_sits_inside_the_ring_and_roughly_centred():
    grid = coin_cells(0.25)
    b = cells_of(grid, "b")
    rows, cols = [r for r, _ in b], [c for _, c in b]
    assert min(rows) > 0 and max(rows) < COIN_ROWS - 1
    assert abs((min(cols) + max(cols)) / 2 - (COIN_COLS - 1) / 2) <= 1.5
    assert abs((min(rows) + max(rows)) / 2 - (COIN_ROWS - 1) / 2) <= 0.5


def test_ring_is_closed_on_every_side():
    ring = {(r, c) for k in ("ring_left", "ring_used", "hand") for r, c in cells_of(coin_cells(0.25), k)}
    mid = COIN_ROWS // 2
    assert any(r == 0 for r, _ in ring) and any(r == COIN_ROWS - 1 for r, _ in ring)
    assert any(c < 4 for r, c in ring if r == mid) and any(c > COIN_COLS - 5 for r, c in ring if r == mid)


def test_nothing_used_at_the_start_and_nothing_left_at_the_end():
    assert cells_of(coin_cells(0.0), "ring_used") == []
    assert cells_of(coin_cells(1.0), "ring_left") == []


def test_used_arc_grows_with_elapsed_time():
    used = [len(cells_of(coin_cells(e), "ring_used")) for e in (0.1, 0.3, 0.5, 0.8)]
    assert used == sorted(used) and used[0] < used[-1]


def test_half_elapsed_uses_the_right_half_of_the_ring():
    grid = coin_cells(0.5)
    mid = (COIN_COLS - 1) / 2
    assert all(c >= mid - 1 for _, c in cells_of(grid, "ring_used"))  # clockwise from 12: right side first
    assert all(c <= mid + 1 for _, c in cells_of(grid, "ring_left"))


def test_there_is_one_hand_moving_clockwise_from_twelve():
    top, bottom = cells_of(coin_cells(0.0), "hand"), cells_of(coin_cells(0.5), "hand")
    quarter = cells_of(coin_cells(0.25), "hand")
    assert len(top) == len(bottom) == len(quarter) == 1
    assert top[0][0] == 0 and abs(top[0][1] - 15) <= 1  # 12 o'clock
    assert bottom[0][0] == COIN_ROWS - 1 and abs(bottom[0][1] - 15) <= 1  # 6 o'clock
    assert quarter[0][1] > 25 and abs(quarter[0][0] - 7) <= 1  # 3 o'clock


def test_render_coin_uses_the_requested_characters_and_colours():
    text = render_coin(450, "UP", "dark")
    plain_lines = text.plain.split("\n")
    assert len(plain_lines) == COIN_ROWS and all(len(line) == COIN_COLS for line in plain_lines)
    assert "$" in text.plain and "*" in text.plain
    grid = coin_cells(0.5)
    (br, bc) = cells_of(grid, "b")[0]
    (lr, lc) = cells_of(grid, "ring_left")[0]
    (ur, uc) = cells_of(grid, "ring_used")[0]
    offset = lambda r, c: sum(len(line) + 1 for line in plain_lines[:r]) + c
    style_at = lambda r, c: text.get_style_at_offset(__import__("rich.console", fromlist=["Console"]).Console(), offset(r, c))
    assert hex_color(style_at(br, bc)) == "#ffffff"          # the B: white $
    assert hex_color(style_at(lr, lc)) == ORANGE              # time left: orange *
    assert hex_color(style_at(ur, uc)) == result_color("UP", "dark")  # time used: green for an UP lean


def test_used_arc_shifts_to_red_for_a_down_lean_and_is_dim_without_a_lean():
    from rich.console import Console

    def used_color(lean):
        text = render_coin(450, lean, "dark")
        grid = coin_cells(0.5)
        r, c = cells_of(grid, "ring_used")[0]
        offset = sum(len(line) + 1 for line in text.plain.split("\n")[:r]) + c
        return hex_color(text.get_style_at_offset(Console(), offset))

    assert used_color("DOWN") == result_color("DOWN", "dark")
    assert used_color(None) not in (result_color("UP", "dark"), result_color("DOWN", "dark"), ORANGE)


def test_render_coin_clamps_out_of_range_time():
    assert render_coin(-50, "UP", "dark").plain == render_coin(0, "UP", "dark").plain
    assert render_coin(99999, "UP", "dark").plain == render_coin(900, "UP", "dark").plain


def test_light_theme_keeps_the_b_visible_on_a_white_background():
    from rich.console import Console

    text = render_coin(450, "UP", "light")
    r, c = cells_of(coin_cells(0.5), "b")[0]
    offset = sum(len(line) + 1 for line in text.plain.split("\n")[:r]) + c
    assert hex_color(text.get_style_at_offset(Console(), offset)) != "#ffffff"


@pytest.mark.parametrize("width, height, shown", [(200, 50, True), (116, 28, True), (115, 50, False), (200, 27, False), (80, 24, False)])
def test_panel_layout_needs_room_beside_the_table(width, height, shown):
    assert panel_layout(width, height) is shown
