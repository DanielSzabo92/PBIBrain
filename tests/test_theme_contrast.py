"""Contrast of the theme.css tokens in the dark and the light theme (UI design A2, A3).

The expected values are the ticket 01 measurement
(.scratch/dev-center-ui/gates/theme-contrast-2026-10-31.txt), re-measured on
2026-11-07 for the ink-accent palette of docs/design/visual-contract.md. The test computes
each ratio again from frontend/src/theme.css with the WCAG 2.2 formula, so a
token change that is not measured again makes this test fail.
"""

import re
import unittest
from pathlib import Path

THEME_CSS = Path(__file__).resolve().parents[1] / "frontend" / "src" / "theme.css"

SURFACES = ("bg", "bg-sidebar", "surface", "surface-2", "surface-3", "surface-hover")
TEXT_TOKENS = ("text", "text-2", "text-3", "brand", "brand-strong", "ok", "warn", "bad", "info")
STATUS_TOKENS = ("ok", "warn", "bad", "info", "brand")
INK_PAIRS = (("brand-ink", "brand"), ("brand-ink", "brand-strong"), ("text-inverse", "text"))
NON_TEXT_SURFACES = ("bg", "surface", "surface-2")
# Control boundaries, focus rings, and status marks must have 3:1 (A3).
NON_TEXT_TOKENS = ("control-border", "brand")
# These tokens are below 3:1 on each surface. Use them only for decorative
# lines, never for a control boundary or a status mark.
DECORATIVE_ONLY = ("line", "line-strong", "line-focus")

TEXT_MIN = 4.5
NON_TEXT_MIN = 3.0

# Ticket 01 values. Rows: foreground token, then one value for each surface of SURFACES.
TICKET_01_TEXT = {
    "dark": {
        "text": (16.35, 15.99, 15.46, 14.72, 13.61, 13.44),
        "text-2": (9.35, 9.15, 8.85, 8.42, 7.79, 7.69),
        "text-3": (5.94, 5.81, 5.62, 5.35, 4.94, 4.88),
        "brand": (16.35, 15.99, 15.46, 14.72, 13.61, 13.44),
        "brand-strong": (19.28, 18.86, 18.24, 17.36, 16.06, 15.85),
        "ok": (9.96, 9.74, 9.42, 8.97, 8.29, 8.19),
        "warn": (10.69, 10.46, 10.11, 9.63, 8.91, 8.79),
        "bad": (7.39, 7.23, 6.99, 6.65, 6.15, 6.07),
        "info": (8.82, 8.62, 8.34, 7.94, 7.34, 7.25),
    },
    "light": {
        "text": (16.53, 15.53, 17.73, 16.97, 15.67, 14.83),
        "text-2": (7.81, 7.33, 8.37, 8.01, 7.40, 7.00),
        "text-3": (5.30, 4.98, 5.69, 5.44, 5.03, 4.76),
        "brand": (16.53, 15.53, 17.73, 16.97, 15.67, 14.83),
        "brand-strong": (19.58, 18.39, 21.00, 20.09, 18.56, 17.57),
        "ok": (5.48, 5.14, 5.87, 5.62, 5.19, 4.91),
        "warn": (5.84, 5.48, 6.26, 5.99, 5.53, 5.24),
        "bad": (5.39, 5.07, 5.79, 5.54, 5.11, 4.84),
        "info": (5.40, 5.07, 5.79, 5.54, 5.12, 4.84),
    },
}
# Status token on its "-soft" tint, composed over "surface" and over "bg".
TICKET_01_SOFT = {
    "dark": {"ok": (7.58, 8.20), "warn": (7.99, 8.71), "bad": (5.86, 6.30), "info": (6.81, 7.34), "brand": (12.80, 13.79)},
    "light": {"ok": (5.25, 4.92), "warn": (5.58, 5.24), "bad": (5.15, 4.83), "info": (5.12, 4.79), "brand": (15.70, 14.72)},
}
TICKET_01_INK = {
    "dark": (16.35, 19.28, 16.35),
    "light": (17.73, 21.00, 17.73),
}
# Rows: token, then one value for each surface of NON_TEXT_SURFACES.
TICKET_01_NON_TEXT = {
    "dark": {
        "control-border": (3.65, 3.45, 3.29),
        "brand": (16.35, 15.46, 14.72),
        "line": (1.28, 1.21, 1.15),
        "line-strong": (1.53, 1.45, 1.38),
        "line-focus": (2.03, 1.92, 1.82),
    },
    "light": {
        "control-border": (3.42, 3.66, 3.51),
        "brand": (16.53, 17.73, 16.97),
        "line": (1.19, 1.27, 1.22),
        "line-strong": (1.40, 1.50, 1.44),
        "line-focus": (1.77, 1.90, 1.82),
    },
}


# UI design 7.4 (ticket 09 section 2.4). Rows: foreground, background, minimum, dark value, light value.
# The tokens can be aliases (var(--x)); the test follows each alias to its color.
SECTION_7_4_PAIRS = (
    ("ok", "ok-tint", TEXT_MIN, 7.58, 5.25),
    ("warn", "warn-tint", TEXT_MIN, 7.99, 5.58),
    ("bad", "bad-tint", TEXT_MIN, 5.86, 5.15),
    ("info", "info-tint", TEXT_MIN, 6.81, 5.12),
    ("brand", "brand-tint", TEXT_MIN, 12.80, 15.70),
    ("proposal", "proposal-tint", TEXT_MIN, 7.79, 7.40),
    ("text-2", "row-active", TEXT_MIN, 7.79, 7.40),
    ("text-3", "row-active", TEXT_MIN, 4.94, 5.03),
    ("text-2", "row-selected", TEXT_MIN, 7.79, 7.40),
    # U-fix-1: the destructive Button fill and its hover.
    ("bad-ink", "bad", TEXT_MIN, 7.39, 5.79),
    ("bad-ink", "bad-strong", TEXT_MIN, 9.12, 7.56),
    ("bad", "surface", TEXT_MIN, 6.99, 5.79),
    # Edge of the destructive hover fill against the page.
    ("bad-strong", "surface", NON_TEXT_MIN, 8.63, 7.56),
    ("ring", "row-active", NON_TEXT_MIN, 13.61, 15.67),
    ("ring", "row-selected", NON_TEXT_MIN, 13.61, 15.67),
    ("control-border", "row-active", NON_TEXT_MIN, 3.04, 3.24),
    ("control-border", "row-selected", NON_TEXT_MIN, 3.04, 3.24),
)
TINT_TOKENS = ("ok", "warn", "bad", "info", "brand")
# Lowest value of "text" on each -tint token.
TEXT_ON_TINT_LOWEST = {"dark": 12.21, "light": 15.68}
# Wireframe status borders on "surface" (UI design 7.3). Lowest value.
WIREFRAME_BORDERS = ("impact-removed", "impact-breaks", "impact-changes", "impact-new", "impact-unchecked", "impact-unchanged")
WIREFRAME_BORDER_LOWEST = {"dark": 3.45, "light": 3.66}


def _block(css: str, selector: str) -> dict[str, str]:
    start = css.index(selector)
    opening = css.index("{", start)
    closing = css.index("}", opening)
    return dict(re.findall(r"--([\w-]+):\s*([^;]+);", css[opening:closing]))


def load_themes(path: Path = THEME_CSS) -> dict[str, dict[str, str]]:
    """Return the token values of each theme. The light theme inherits each dark token that it does not set."""
    css = path.read_text(encoding="utf-8")
    dark = _block(css, ":root {")
    light = {**dark, **_block(css, ':root[data-theme="light"]')}
    return {"dark": dark, "light": light}


def parse_color(value: str) -> tuple[tuple[int, int, int], float]:
    value = value.strip()
    if value.startswith("#"):
        digits = value[1:]
        if len(digits) == 3:
            digits = "".join(character * 2 for character in digits)
        if len(digits) != 6:
            raise ValueError(f"Unsupported hex color: {value}")
        return tuple(int(digits[index:index + 2], 16) for index in (0, 2, 4)), 1.0
    match = re.fullmatch(r"rgb\((\d+) (\d+) (\d+) / ([\d.]+)\)", value)
    if not match:
        raise ValueError(f"Unsupported color value: {value}")
    return tuple(int(part) for part in match.groups()[:3]), float(match.group(4))


def compose(foreground: tuple[int, int, int], alpha: float, background: tuple[int, int, int]) -> tuple[int, int, int]:
    return tuple(round(front * alpha + back * (1 - alpha)) for front, back in zip(foreground, background))


def _linear(channel: int) -> float:
    value = channel / 255
    return value / 12.92 if value <= 0.03928 else ((value + 0.055) / 1.055) ** 2.4


def luminance(rgb: tuple[int, int, int]) -> float:
    red, green, blue = (_linear(channel) for channel in rgb)
    return 0.2126 * red + 0.7152 * green + 0.0722 * blue


def contrast(first: tuple[int, int, int], second: tuple[int, int, int]) -> float:
    high, low = sorted((luminance(first), luminance(second)), reverse=True)
    return (high + 0.05) / (low + 0.05)


class ThemeContrastTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.themes = load_themes()

    def opaque(self, theme: str, token: str) -> tuple[int, int, int]:
        rgb, alpha = parse_color(self.themes[theme][token])
        self.assertEqual(alpha, 1.0, f"{theme} --{token} must be opaque")
        return rgb

    def ratio(self, theme: str, foreground: str, background: str) -> float:
        return contrast(self.opaque(theme, foreground), self.opaque(theme, background))

    def soft_ratio(self, theme: str, status: str, over: str) -> float:
        tint, alpha = parse_color(self.themes[theme][f"{status}-soft"])
        return contrast(self.opaque(theme, status), compose(tint, alpha, self.opaque(theme, over)))

    def assertMeasured(self, measured: float, expected: float, label: str) -> None:
        self.assertEqual(round(measured, 2), expected, f"{label}: measured {measured:.2f}, ticket 01 gives {expected:.2f}")

    def test_text_tokens_on_each_surface_match_ticket_01_and_pass_4_5(self) -> None:
        for theme, rows in TICKET_01_TEXT.items():
            self.assertEqual(tuple(rows), TEXT_TOKENS)
            for token, values in rows.items():
                for surface, expected in zip(SURFACES, values):
                    with self.subTest(theme=theme, token=token, surface=surface):
                        measured = self.ratio(theme, token, surface)
                        self.assertMeasured(measured, expected, f"{theme} {token} on {surface}")
                        self.assertGreaterEqual(measured, TEXT_MIN)

    def test_status_text_on_its_soft_tint_matches_ticket_01_and_passes_4_5(self) -> None:
        for theme, rows in TICKET_01_SOFT.items():
            self.assertEqual(tuple(rows), STATUS_TOKENS)
            for status, values in rows.items():
                for over, expected in zip(("surface", "bg"), values):
                    with self.subTest(theme=theme, status=status, over=over):
                        measured = self.soft_ratio(theme, status, over)
                        self.assertMeasured(measured, expected, f"{theme} {status} on {status}-soft over {over}")
                        self.assertGreaterEqual(measured, TEXT_MIN)

    def test_ink_pairs_match_ticket_01_and_pass_4_5(self) -> None:
        for theme, values in TICKET_01_INK.items():
            for (foreground, background), expected in zip(INK_PAIRS, values):
                with self.subTest(theme=theme, foreground=foreground, background=background):
                    measured = self.ratio(theme, foreground, background)
                    self.assertMeasured(measured, expected, f"{theme} {foreground} on {background}")
                    self.assertGreaterEqual(measured, TEXT_MIN)

    def test_non_text_tokens_match_ticket_01(self) -> None:
        for theme, rows in TICKET_01_NON_TEXT.items():
            self.assertEqual(set(rows), set(NON_TEXT_TOKENS) | set(DECORATIVE_ONLY))
            for token, values in rows.items():
                for surface, expected in zip(NON_TEXT_SURFACES, values):
                    with self.subTest(theme=theme, token=token, surface=surface):
                        self.assertMeasured(self.ratio(theme, token, surface), expected, f"{theme} {token} on {surface}")

    def test_control_boundary_tokens_pass_3_to_1(self) -> None:
        for theme in self.themes:
            for token in NON_TEXT_TOKENS:
                for surface in NON_TEXT_SURFACES:
                    with self.subTest(theme=theme, token=token, surface=surface):
                        self.assertGreaterEqual(self.ratio(theme, token, surface), NON_TEXT_MIN)

    def test_line_tokens_are_decorative_only(self) -> None:
        # If a line token gets 3:1 on each surface, measure it again and move it out of DECORATIVE_ONLY.
        self.assertEqual(DECORATIVE_ONLY, ("line", "line-strong", "line-focus"))
        for theme in self.themes:
            for token in DECORATIVE_ONLY:
                with self.subTest(theme=theme, token=token):
                    lowest = min(self.ratio(theme, token, surface) for surface in NON_TEXT_SURFACES)
                    self.assertLess(lowest, NON_TEXT_MIN)

    def test_formula_matches_the_wcag_reference_values(self) -> None:
        self.assertAlmostEqual(contrast((0, 0, 0), (255, 255, 255)), 21.0, places=6)
        self.assertAlmostEqual(contrast((255, 255, 255), (255, 255, 255)), 1.0, places=6)
        self.assertEqual(round(contrast((255, 255, 255), (118, 118, 118)), 2), 4.54)


class NewTokenContrastTest(unittest.TestCase):
    """UI design 7.1 to 7.4: the new tint, destructive, and alias tokens of step U1."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.themes = load_themes()

    def color(self, theme: str, token: str) -> tuple[int, int, int]:
        value = self.themes[theme][token]
        seen = {token}
        while value.startswith("var("):
            alias = re.fullmatch(r"var\(--([\w-]+)\)", value.strip())
            self.assertIsNotNone(alias, f"{theme} --{token}: unsupported alias {value}")
            name = alias.group(1)
            self.assertNotIn(name, seen, f"{theme} --{token}: alias loop")
            seen.add(name)
            value = self.themes[theme][name]
        rgb, alpha = parse_color(value)
        self.assertEqual(alpha, 1.0, f"{theme} --{token} must be opaque")
        return rgb

    def ratio(self, theme: str, foreground: str, background: str) -> float:
        return contrast(self.color(theme, foreground), self.color(theme, background))

    def test_each_tint_is_its_soft_token_over_surface(self) -> None:
        for theme in self.themes:
            surface = self.color(theme, "surface")
            for status in TINT_TOKENS:
                with self.subTest(theme=theme, status=status):
                    tint, alpha = parse_color(self.themes[theme][f"{status}-soft"])
                    self.assertEqual(self.color(theme, f"{status}-tint"), compose(tint, alpha, surface))

    def test_section_7_4_pairs_match_the_measurement_and_pass(self) -> None:
        for foreground, background, minimum, dark, light in SECTION_7_4_PAIRS:
            for theme, expected in (("dark", dark), ("light", light)):
                with self.subTest(theme=theme, foreground=foreground, background=background):
                    measured = self.ratio(theme, foreground, background)
                    self.assertEqual(round(measured, 2), expected, f"{theme} {foreground} on {background}: {measured:.2f}")
                    self.assertGreaterEqual(measured, minimum)

    def test_text_on_each_tint_passes(self) -> None:
        for theme, expected in TEXT_ON_TINT_LOWEST.items():
            lowest = min(self.ratio(theme, "text", f"{status}-tint") for status in TINT_TOKENS)
            self.assertEqual(round(lowest, 2), expected, theme)
            self.assertGreaterEqual(lowest, TEXT_MIN)

    def test_wireframe_borders_on_surface_pass_3_to_1(self) -> None:
        for theme, expected in WIREFRAME_BORDER_LOWEST.items():
            lowest = min(self.ratio(theme, token, "surface") for token in WIREFRAME_BORDERS)
            self.assertEqual(round(lowest, 2), expected, theme)
            self.assertGreaterEqual(lowest, NON_TEXT_MIN)

    def test_destructive_fill_no_longer_uses_white_on_bad_in_dark(self) -> None:
        # U-fix-1: white text on --bad is 2.61:1 in the dark theme. The Button uses --bad-ink.
        self.assertEqual(round(contrast((255, 255, 255), self.color("dark", "bad")), 2), 2.61)
        app_css = (THEME_CSS.parent / "app.css").read_text(encoding="utf-8")
        rule = re.search(r"\.ui-button-destructive\s*\{([^}]*)\}", app_css)
        self.assertIsNotNone(rule)
        self.assertIn("color: var(--bad-ink)", rule.group(1))
        self.assertIn("background: var(--bad)", rule.group(1))
        hover = re.search(r"\.ui-button-destructive:hover[^{]*\{([^}]*)\}", app_css)
        self.assertIsNotNone(hover)
        self.assertIn("var(--bad-strong)", hover.group(1))


if __name__ == "__main__":
    unittest.main()
