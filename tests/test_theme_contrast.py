"""Contrast of the theme.css tokens in the dark and the light theme (UI design A2, A3).

The expected values are the ticket 01 measurement
(.scratch/dev-center-ui/gates/theme-contrast-2026-10-31.txt). The test computes
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
        "text": (16.74, 16.39, 15.64, 14.90, 13.77, 14.26),
        "text-2": (8.12, 7.95, 7.59, 7.23, 6.68, 6.92),
        "text-3": (6.76, 6.62, 6.32, 6.02, 5.56, 5.76),
        "brand": (7.47, 7.32, 6.98, 6.65, 6.15, 6.36),
        "brand-strong": (9.63, 9.43, 9.00, 8.57, 7.92, 8.20),
        "ok": (10.10, 9.89, 9.44, 8.99, 8.31, 8.60),
        "warn": (10.85, 10.62, 10.14, 9.65, 8.92, 9.24),
        "bad": (7.49, 7.34, 7.00, 6.67, 6.17, 6.38),
        "info": (8.94, 8.76, 8.36, 7.96, 7.36, 7.62),
    },
    "light": {
        "text": (16.55, 15.55, 17.91, 17.00, 15.70, 15.84),
        "text-2": (5.90, 5.54, 6.38, 6.06, 5.59, 5.64),
        "text-3": (5.01, 4.71, 5.42, 5.15, 4.75, 4.80),
        "brand": (5.10, 4.79, 5.52, 5.24, 4.84, 4.88),
        "brand-strong": (6.71, 6.30, 7.26, 6.89, 6.36, 6.42),
        "ok": (5.43, 5.10, 5.87, 5.58, 5.15, 5.19),
        "warn": (5.79, 5.43, 6.26, 5.94, 5.49, 5.54),
        "bad": (5.35, 5.02, 5.79, 5.49, 5.07, 5.12),
        "info": (5.35, 5.03, 5.79, 5.50, 5.07, 5.12),
    },
}
# Status token on its "-soft" tint, composed over "surface" and over "bg".
TICKET_01_SOFT = {
    "dark": {"ok": (7.61, 8.39), "warn": (8.03, 8.87), "bad": (5.87, 6.45), "info": (6.83, 7.52), "brand": (5.80, 6.37)},
    "light": {"ok": (5.25, 4.87), "warn": (5.58, 5.19), "bad": (5.15, 4.79), "info": (5.12, 4.76), "brand": (4.87, 4.53)},
}
TICKET_01_INK = {
    "dark": (7.41, 9.56, 16.74),
    "light": (5.52, 7.26, 17.91),
}
# Rows: token, then one value for each surface of NON_TEXT_SURFACES.
TICKET_01_NON_TEXT = {
    "dark": {
        "control-border": (4.01, 3.74, 3.57),
        "brand": (7.47, 6.98, 6.65),
        "line": (1.23, 1.15, 1.09),
        "line-strong": (1.46, 1.36, 1.30),
        "line-focus": (1.85, 1.73, 1.65),
    },
    "light": {
        "control-border": (3.25, 3.52, 3.34),
        "brand": (5.10, 5.52, 5.24),
        "line": (1.16, 1.26, 1.20),
        "line-strong": (1.36, 1.47, 1.40),
        "line-focus": (1.76, 1.90, 1.81),
    },
}


# UI design 7.4 (ticket 09 section 2.4). Rows: foreground, background, minimum, dark value, light value.
# The tokens can be aliases (var(--x)); the test follows each alias to its color.
SECTION_7_4_PAIRS = (
    ("ok", "ok-tint", TEXT_MIN, 7.61, 5.25),
    ("warn", "warn-tint", TEXT_MIN, 8.03, 5.58),
    ("bad", "bad-tint", TEXT_MIN, 5.87, 5.15),
    ("info", "info-tint", TEXT_MIN, 6.83, 5.12),
    ("brand", "brand-tint", TEXT_MIN, 5.80, 4.87),
    ("proposal", "proposal-tint", TEXT_MIN, 7.47, 6.41),
    ("text-2", "row-active", TEXT_MIN, 6.30, 5.63),
    ("text-3", "row-active", TEXT_MIN, 5.24, 4.79),
    ("text-2", "row-selected", TEXT_MIN, 6.68, 5.59),
    # U-fix-1: the destructive Button fill and its hover.
    ("bad-ink", "bad", TEXT_MIN, 7.49, 5.79),
    ("bad-ink", "bad-strong", TEXT_MIN, 9.25, 7.56),
    ("bad", "surface", TEXT_MIN, 7.00, 5.79),
    # Edge of the destructive hover fill against the page.
    ("bad-strong", "surface", NON_TEXT_MIN, 8.65, 7.56),
    ("ring", "row-active", NON_TEXT_MIN, 5.80, 4.87),
    ("ring", "row-selected", NON_TEXT_MIN, 6.15, 4.84),
    ("control-border", "row-active", NON_TEXT_MIN, 3.11, 3.11),
    ("control-border", "row-selected", NON_TEXT_MIN, 3.30, 3.08),
)
TINT_TOKENS = ("ok", "warn", "bad", "info", "brand")
# Lowest value of "text" on each -tint token.
TEXT_ON_TINT_LOWEST = {"dark": 12.39, "light": 15.81}
# Wireframe status borders on "surface" (UI design 7.3). Lowest value.
WIREFRAME_BORDERS = ("impact-removed", "impact-breaks", "impact-changes", "impact-new", "impact-unchecked", "impact-unchanged")
WIREFRAME_BORDER_LOWEST = {"dark": 3.74, "light": 3.52}


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
