"""The roadbook design system — one baked-in look, no options.

A stage *profile* and a stage *map* render as two views of the same system: the same
paper, the same ink, the single green accent, and one condensed display face. Steepness
is that one green at three fixed opacities — there is no multi-hue ramp.

Fonts are referenced, not embedded: the host page must load **Jost** (and, for PNG output,
it must be installed) for the type to render as designed.
"""

from __future__ import annotations

import math
from xml.sax.saxutils import escape

__all__ = [
    "FONT_STACK",
    "PAPER",
    "BACKGROUND",
    "INK",
    "INK_SOFT",
    "INK_MUTE",
    "ACCENT",
    "BAND_OPACITY",
    "LAND_FILL",
    "LAND_STROKE",
    "BASELINE",
]

# ── Type ──────────────────────────────────────────────────────────────────────
# One family carries every label on both visuals — Jost.
FONT_STACK = "'Jost',sans-serif"

# ── Ink & paper ───────────────────────────────────────────────────────────────
PAPER = "#FAFAF8"      # light land / paper tone
BACKGROUND = "#E6E4DD"  # the warm ground both visuals are drawn on
INK = "#1A1917"        # elevation line, primary labels
INK_SOFT = "#4B4840"   # climb names
INK_MUTE = "#95908A"   # elevations, secondary labels

# ── The single accent ─────────────────────────────────────────────────────────
# Green. Steepness is this one green at three opacities: gentle · moderate · steep.
ACCENT = "#F2C200"
BAND_OPACITY = (0.14, 0.40, 1.0)

# ── Map ───────────────────────────────────────────────────────────────────────
LAND_FILL = "#FAFAF8"   # country reads as light land on the warm BACKGROUND
LAND_STROKE = "#C9C5BC"

# ── Profile baseline hairline ─────────────────────────────────────────────────
BASELINE = "rgba(26,25,23,0.12)"


# ── SVG text helpers ──────────────────────────────────────────────────────────

def _num(v: "float | int") -> str:
    """Compact number formatting: integers stay clean, floats drop trailing zeros."""
    if isinstance(v, int):
        return str(v)
    if float(v).is_integer():
        return str(int(v))
    return f"{v:.2f}".rstrip("0").rstrip(".")


def _esc(s: object) -> str:
    return escape(str(s))


def _text(
    x: float,
    y: float,
    s: object,
    *,
    size: float,
    weight: int = 400,
    fill: str = INK,
    anchor: str = "start",
    ls: "str | None" = None,
    cls: "str | None" = None,
) -> str:
    """One SVG ``<text>`` in the roadbook type system."""
    parts = [
        f'<text x="{_num(x)}" y="{_num(y)}"',
        f'font-family="{FONT_STACK}"',
        f'font-size="{_num(size)}"',
        f'font-weight="{weight}"',
        f'fill="{fill}"',
        f'text-anchor="{anchor}"',
    ]
    if ls is not None:
        parts.append(f'letter-spacing="{ls}"')
    if cls is not None:
        parts.append(f'class="{cls}"')
    return " ".join(parts) + f">{_esc(s)}</text>"


def _fmt_ele(metres: float) -> str:
    """A town elevation, e.g. ``1225`` → ``1,225 M``."""
    return f"{round(metres):,} M"
