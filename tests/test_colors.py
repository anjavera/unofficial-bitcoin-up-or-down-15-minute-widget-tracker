import colorsys

import pytest

from btc15_widget.colors import BACKGROUND, BAND_EDGES, band_index, net_color, result_color

BG = BACKGROUND
MIDPOINTS = [5, 17, 37, 75, 150, 250, 350, 450, 750]  # one net value inside each band


def rgb(hex_color: str) -> tuple[int, int, int]:
    return tuple(int(hex_color[i : i + 2], 16) for i in (1, 3, 5))


def saturation(hex_color: str) -> float:
    r, g, b = (c / 255 for c in rgb(hex_color))
    return colorsys.rgb_to_hsv(r, g, b)[1]


def luminance(hex_color: str) -> float:
    def lin(c):
        c /= 255
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

    r, g, b = (lin(c) for c in rgb(hex_color))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(a: str, b: str) -> float:
    hi, lo = sorted((luminance(a), luminance(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


@pytest.mark.parametrize(
    "net, band",
    [(0, 0), (9.99, 0), (-9.99, 0), (10, 1), (-10, 1), (24.99, 1), (25, 2), (499.99, 7), (500, 8),
     (999.99, 8), (1000, 8), (5000, 8), (-5000, 8), (-0.0, 0)],
)
def test_band_index(net, band):
    assert band_index(net) == band


def test_band_edges_match_spec():
    assert BAND_EDGES == (10, 25, 50, 100, 200, 300, 400, 500, 1000)


@pytest.mark.parametrize("theme", ["dark", "light"])
def test_sign_picks_hue(theme):
    for net in MIDPOINTS:
        r, g, b = rgb(net_color(net, theme))
        assert b > r and b > g, f"+{net} should be blue-dominant"
        r, g, b = rgb(net_color(-net, theme))
        assert r > g and r > b, f"-{net} should be orange/red-dominant"
    assert rgb(net_color(0, theme))[2] > rgb(net_color(0, theme))[0]  # zero counts as positive (blue)


@pytest.mark.parametrize("theme", ["dark", "light"])
@pytest.mark.parametrize("sign", [1, -1])
def test_intensity_increases_with_band(theme, sign):
    sats = [saturation(net_color(sign * n, theme)) for n in MIDPOINTS]
    assert sats == sorted(sats) and len(set(sats)) == 9


@pytest.mark.parametrize("theme", ["dark", "light"])
@pytest.mark.parametrize("sign", [1, -1])
def test_every_step_stays_visible_on_background(theme, sign):
    for n in MIDPOINTS:
        assert contrast(net_color(sign * n, theme), BG[theme]) >= 1.3


@pytest.mark.parametrize("theme", ["dark", "light"])
def test_result_colors(theme):
    r, g, b = rgb(result_color("UP", theme))
    assert g > r and g > b
    r, g, b = rgb(result_color("DOWN", theme))
    assert r > g and r > b


def test_unknown_result_raises():
    with pytest.raises(ValueError):
        result_color("FLAT", "dark")
