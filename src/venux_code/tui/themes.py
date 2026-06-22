"""Theme definitions for the Venux Code TUI.

Provides Textual ``Theme`` objects for dark, light, and Catppuccin colour
schemes.  The active theme is selected via config and can be cycled at
runtime with a key binding.
"""

from __future__ import annotations

from textual.theme import Theme

# ---------------------------------------------------------------------------
# Dark theme (default)
# ---------------------------------------------------------------------------

DARK = Theme(
    name="dark",
    primary="#7c3aed",
    secondary="#06b6d4",
    accent="#f59e0b",
    success="#22c55e",
    warning="#eab308",
    error="#ef4444",
    surface="#1e1b2e",
    panel="#141124",
    background="#0c0a1a",
    foreground="#e2e0f0",
    dark=True,
    variables={
        "block-background": "#141124",
        "input-background": "#1e1b2e",
        "border": "#2d2945",
    },
)

# ---------------------------------------------------------------------------
# Light theme
# ---------------------------------------------------------------------------

LIGHT = Theme(
    name="light",
    primary="#6d28d9",
    secondary="#0891b2",
    accent="#d97706",
    success="#16a34a",
    warning="#ca8a04",
    error="#dc2626",
    surface="#f5f3ff",
    panel="#ede9fe",
    background="#fafaf9",
    foreground="#1c1917",
    dark=False,
    variables={
        "block-background": "#ede9fe",
        "input-background": "#f5f3ff",
        "border": "#c4b5fd",
    },
)

# ---------------------------------------------------------------------------
# Catppuccin Mocha (dark)
# ---------------------------------------------------------------------------

CATPPUCCIN_MOCHA = Theme(
    name="catppuccin",
    primary="#cba6f7",
    secondary="#89dceb",
    accent="#fab387",
    success="#a6e3a1",
    warning="#f9e2af",
    error="#f38ba8",
    surface="#1e1e2e",
    panel="#181825",
    background="#11111b",
    foreground="#cdd6f4",
    dark=True,
    variables={
        "block-background": "#181825",
        "input-background": "#1e1e2e",
        "border": "#313244",
        "overlay": "#6c7086",
        "subtext": "#a6adc8",
    },
)

# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

THEMES: dict[str, Theme] = {
    "dark": DARK,
    "light": LIGHT,
    "catppuccin": CATPPUCCIN_MOCHA,
}


def get_theme(name: str) -> Theme:
    """Return a theme by name, falling back to DARK."""
    return THEMES.get(name, DARK)
