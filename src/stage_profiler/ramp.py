"""Grand-Tour roadbook steepness colour ramp: teal descents → green flats →
lime → yellow → orange → red for the brutal pitches.

Edit :data:`RAMP` to change how climbs are coloured — each entry is
``(gradient_percent, (r, g, b))`` and colours interpolate linearly between stops.
"""

from __future__ import annotations

__all__ = ["RAMP", "grad_color"]

RAMP: "list[tuple[float, tuple[int, int, int]]]" = [
    (-6, (47, 111, 122)),   # descent — teal
    (0, (74, 143, 74)),     # flat — green
    (3, (154, 209, 63)),    # gentle — lime
    (5, (242, 196, 61)),    # rising — yellow
    (7, (240, 144, 46)),    # hard — orange
    (9, (223, 83, 32)),     # steep — deep orange
    (12, (200, 30, 43)),    # brutal — red
    (20, (150, 18, 30)),    # wall — dark red
]


def _lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def _rgb(c: "tuple[float, float, float]") -> str:
    return f"rgb({round(c[0])},{round(c[1])},{round(c[2])})"


def grad_color(pct: float) -> str:
    """Return the ``rgb(...)`` colour for a gradient of ``pct`` percent."""
    if pct <= RAMP[0][0]:
        return _rgb(RAMP[0][1])
    if pct >= RAMP[-1][0]:
        return _rgb(RAMP[-1][1])
    for i in range(len(RAMP) - 1):
        p0, c0 = RAMP[i]
        p1, c1 = RAMP[i + 1]
        if p0 <= pct <= p1:
            t = (pct - p0) / (p1 - p0)
            return _rgb((_lerp(c0[0], c1[0], t), _lerp(c0[1], c1[1], t), _lerp(c0[2], c1[2], t)))
    return _rgb(RAMP[-1][1])
