"""Colour palettes and helpers for the redesigned XTrader Bridge GUI.

The design uses CSS ``color-mix`` for the translucent "weak/soft" variants.
Tk has no alpha compositing, so we pre-compute opaque approximations by
blending the accent/semantic colour with the window background.
"""

from __future__ import annotations


def _hex_to_rgb(h: str) -> tuple[int, int, int]:
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))  # type: ignore[return-value]


def _rgb_to_hex(rgb) -> str:
    return "#%02x%02x%02x" % tuple(max(0, min(255, round(v))) for v in rgb)


def mix(c1: str, c2: str, t: float) -> str:
    """Blend ``c1`` over ``c2`` with weight ``t`` given to ``c1``."""
    a = _hex_to_rgb(c1)
    b = _hex_to_rgb(c2)
    return _rgb_to_hex(tuple(a[i] * t + b[i] * (1 - t) for i in range(3)))


# ── base design tokens (from XTrader Bridge.dc.html :root rules) ───────────────
DARK_BASE = {
    "desk": "#080b11", "win": "#0e131c", "titlebar": "#0b0f17", "surface": "#131a25",
    "surface2": "#19212f", "surface3": "#212b3c", "border": "#28313f", "border2": "#1c2431",
    "text": "#e7edf5", "text2": "#93a1b4", "text3": "#5d6a7b",
    "accent": "#3d8bff", "purple": "#7c5cff", "success": "#2bcf86",
    "danger": "#ff5468", "warn": "#ffb02e", "info": "#38bdf8",
}

LIGHT_BASE = {
    "desk": "#c3ccd9", "win": "#eef1f7", "titlebar": "#e4e9f1", "surface": "#ffffff",
    "surface2": "#f4f7fb", "surface3": "#eaeff6", "border": "#d6ddea", "border2": "#e5eaf2",
    "text": "#172234", "text2": "#586376", "text3": "#8895a7",
    "accent": "#2563eb", "purple": "#6d4aff", "success": "#0ca678",
    "danger": "#e03546", "warn": "#dc8a06", "info": "#0e9bd6",
}

_WEAK = {"accent": .15, "purple": .16, "success": .15, "danger": .15, "warn": .15, "info": .15}


def build_palette(base: dict) -> dict:
    """Return the full colour table (base tokens + derived variants)."""
    c = dict(base)
    win = base["win"]
    black = "#000000"
    for name, pct in _WEAK.items():
        c[f"{name}_weak"] = mix(base[name], win, pct)
        # hover = slightly darkened solid (mirrors the web opacity:.9 feel)
        c[f"{name}_h"] = mix(base[name], black, .86)
    c["accent_soft"] = mix(base["accent"], win, .40)
    c["hero"] = mix(base["accent"], base["surface"], .20)
    c["surface3_h"] = mix(base["surface2"], base["text3"], .82)
    c["ghost_h"] = base["surface2"]
    c["warn_ink"] = "#1a1204"          # dark ink for the warning (yellow) button
    c["on_accent"] = "#ffffff"
    return c


class Palette:
    """Holds the current theme colours and flips between dark and light."""

    def __init__(self, mode: str = "dark"):
        self.mode = mode
        self.c = build_palette(DARK_BASE if mode == "dark" else LIGHT_BASE)

    def toggle(self) -> str:
        self.mode = "light" if self.mode == "dark" else "dark"
        self.c = build_palette(DARK_BASE if self.mode == "dark" else LIGHT_BASE)
        return self.mode

    def __call__(self, key):
        if key is None:
            return None
        if key == "transparent" or (isinstance(key, str) and key.startswith("#")):
            return key
        return self.c.get(key, key)
