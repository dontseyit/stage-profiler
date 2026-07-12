"""The stage-profile SVG — a segmented steepness-band profile.

One baked-in look, no options: a transparent 840×300 canvas with the elevation line in ink,
the area beneath it painted in the single green at three steepness opacities, named climbs
floating over their summits, a green start wedge, a checkered finish flag, and the start /
finish town + elevation at each end. There are no axes, ticks, or header — the towns and
climbs *are* the labels.

The vertical scale floors the elevation span (:data:`FLOOR_SPAN_M`) so a flat classic stage
reads as flat instead of being stretched into fake mountains, while a real mountain stage
fills the frame.
"""

from __future__ import annotations

from typing import Sequence, Tuple

from .geometry import Series, ele_at
from .steepness import steepness_bands
from .theme import (
    BACKGROUND,
    BAND_COLORS,
    INK,
    INK_MUTE,
    PAPER,
    _fmt_ele,
    _num,
    _text,
)

__all__ = ["render_profile_svg", "WIDTH", "HEIGHT"]

_SVG_NS = "http://www.w3.org/2000/svg"

# Canvas & plot frame (fixed) — a compact 768×128 banner strip.
WIDTH, HEIGHT = 768, 128
PAD_X = 20.0          # side padding around the corner text and the profile
BASE_Y = 96.0         # baseline hairline (lifted to give the foot labels breathing room)
LINE_BOTTOM = 88.0    # the route's low point sits here (a foot of space above the baseline)
LINE_TOP = 44.0       # the top of the elevation span sits here (room for climb labels above)
PLOT_H = LINE_BOTTOM - LINE_TOP

# Floor the elevation span so low-relief stages stay visually flat.
FLOOR_SPAN_M = 1000.0

# Elevation line resolution (points across the width).
_LINE_POINTS = 300

# Climb labels: centred over each summit (the centre of the near-highest stretch within
# this window — a plateau at its middle, a peak at its point), a fixed rise above it and
# tied down by a thin leader. Different summit heights separate the names vertically.
_SUMMIT_WINDOW_M = 0.0
_SUMMIT_TOL_M = 0.0
_CLIMB_RISE = 20.0

# Finish marker row — the top of the finish border rule.
_FLAG_Y = 20.0

# Foot labels (town + elevation) and the km marker, relative to the frame.
_KM_Y = 15.0
_TOWN_DY = 15.0       # town baseline, below BASE_Y (a gap under the baseline bar)
_ELE_DY = 25.0        # elevation baseline, below BASE_Y

Climb = Tuple[str, float]  # (name, summit_km)


def render_profile_svg(
    series: Series,
    *,
    start_town: str = "",
    finish_town: str = "",
    climbs: "Sequence[Climb]" = (),
) -> str:
    """Render ``series`` to a self-contained stage-profile SVG string."""
    total = series.metrics.total_distance_m or 1.0
    ds = [s.distance_m for s in series.samples]
    es = [s.elevation_m for s in series.samples]
    e_min = series.metrics.min_ele_m
    span = max(series.metrics.max_ele_m - e_min, FLOOR_SPAN_M)

    def x(d: float) -> float:
        return PAD_X + (d / total) * (WIDTH - 2 * PAD_X)

    def y(e: float) -> float:
        return LINE_BOTTOM - ((e - e_min) / span) * PLOT_H

    # Elevation line, resampled to a clean fixed resolution.
    pts = [(x(d), y(ele_at(ds, es, d))) for d in _even_distances(total, _LINE_POINTS)]
    line = " ".join(f"{px:.2f},{py:.2f}" for px, py in pts)

    body: "list[str]" = [
        f'<rect class="sp-bg" width="{WIDTH}" height="{HEIGHT}" fill="{BACKGROUND}"/>',
    ]

    # Climb summits, resolved once. Their location rules are drawn *first*, so the bands and
    # line paint over them — only the leader above the profile shows, never a streak across it.
    marks = []
    for name, km in climbs:
        d = _summit(ds, es, max(0.0, min(km * 1000.0, total)), total)
        px, peak_y = x(d), y(ele_at(ds, es, d))
        marks.append((str(name), px, peak_y, peak_y - _CLIMB_RISE))
    for _name, px, _peak_y, label_y in marks:
        body.append(
            f'<line class="sp-leader" x1="{px:.2f}" y1="{label_y + 3:.2f}" x2="{px:.2f}" '
            f'y2="{_num(BASE_Y)}" stroke="{INK}" stroke-width="0.75"/>'
        )

    # Steepness bands — flat primary blocks, clipped to the silhouette under the line.
    clip = (f"M{x(0):.2f},{BASE_Y} "
            + " ".join(f"L{px:.2f},{py:.2f}" for px, py in pts)
            + f" L{x(total):.2f},{BASE_Y} Z")
    rects = []
    for band in steepness_bands(series):
        bx = x(band.d0)
        rects.append(
            f'<rect class="sp-band" x="{bx:.2f}" y="0" width="{x(band.d1) - bx:.2f}" '
            f'height="{_num(BASE_Y)}" fill="{BAND_COLORS[band.tier]}"/>'
        )
    body.append(
        f'<defs><clipPath id="sp-clip"><path d="{clip}"/></clipPath></defs>'
        f'<g clip-path="url(#sp-clip)">{"".join(rects)}</g>'
    )

    # Bold black baseline bar (the km axis) and elevation line.
    body.append(
        f'<line class="sp-baseline" x1="{_num(PAD_X)}" y1="{_num(BASE_Y)}" '
        f'x2="{_num(WIDTH - PAD_X)}" y2="{_num(BASE_Y)}" stroke="{INK}" stroke-width="3"/>'
    )
    body.append(
        f'<polyline class="sp-line" points="{line}" fill="none" stroke="{INK}" '
        f'stroke-width="3" stroke-linejoin="round" stroke-linecap="round"/>'
    )

    # Climb names, painted on top of the profile.
    for name, px, _peak_y, label_y in marks:
        body.append(_text(
            px, label_y, name,
            size=11, weight=700, fill=INK, anchor="middle", ls="0.01em", cls="sp-climb",
        ))

    # Start (left) and finish (right) corners: town + elevation at the foot for both. Only
    # the finish carries the distance marker and the full-height border rule.
    body.append(_corner(PAD_X, start_town, es[0], "", checker=False, anchor="start", flag_dir=1, border=False))
    body.append(_corner(WIDTH - PAD_X, finish_town, es[-1], f"{total / 1000:.1f} KM",
                        checker=True, anchor="end", flag_dir=-1, border=True))

    # Steepness key — the one thing the primary-colour coding needs to read clearly.
    body.append(_legend(PAD_X + 30, 20))

    return (
        f'<svg xmlns="{_SVG_NS}" class="stage-profile" viewBox="0 0 {WIDTH} {HEIGHT}" '
        f'width="{WIDTH}" height="{HEIGHT}">' + "".join(body) + "</svg>"
    )


def _even_distances(total: float, n: int) -> "list[float]":
    return [total * i / (n - 1) for i in range(n)]


def _summit(ds: "list[float]", es: "list[float]", d: float, total: float) -> float:
    """Centre of the near-highest stretch within ``_SUMMIT_WINDOW_M`` of ``d`` — so a broad
    plateau labels at its middle and a sharp peak at its point."""
    lo, hi = max(0.0, d - _SUMMIT_WINDOW_M), min(total, d + _SUMMIT_WINDOW_M)
    n = 48
    xs = [lo + (hi - lo) * i / n for i in range(n + 1)]
    evs = [ele_at(ds, es, xx) for xx in xs]
    peak = max(evs)
    near = [xx for xx, e in zip(xs, evs) if e >= peak - _SUMMIT_TOL_M]
    return (near[0] + near[-1]) / 2 if near else d


def _corner(x_edge: float, town: str, ele: float, km_label: str, *,
            checker: bool, anchor: str, flag_dir: int, border: bool) -> str:
    """A start/finish corner: an optional distance marker (km-axis endpoint) and a geometric
    marker up top, the town and its elevation at the foot. When ``border`` is set, a grid rule
    runs the full height between them, tying the corner to the route."""
    if not town:
        return ""
    parts: "list[str]" = []
    if km_label:
        parts.append(_text(x_edge, _KM_Y, km_label, size=16, weight=700, fill=INK, anchor=anchor, ls="0.04em", cls="sp-dist"))
    if border:
        parts.append(f'<line class="sp-border" x1="{x_edge:.1f}" y1="{_FLAG_Y:.1f}" '
                     f'x2="{x_edge:.1f}" y2="{BASE_Y:.1f}" stroke="{INK}" stroke-width="0.75"/>')
    if checker:  # finish carries the checkered marker; the start has none
        parts.append(_finish_marker(x_edge, _FLAG_Y, direction=flag_dir))
    parts.append(_text(x_edge, BASE_Y + _TOWN_DY, town.upper(), size=14, weight=700, fill=INK, anchor=anchor, ls="0.02em", cls="sp-town"))
    parts.append(_text(x_edge, BASE_Y + _ELE_DY + 2, _fmt_ele(ele), size=12, weight=500, fill=INK_MUTE, anchor=anchor, ls="0.04em", cls="sp-ele"))
    return "".join(parts)


def _legend(x: float, y: float) -> str:
    """A compact steepness key — the three primary swatches with their gradient bands."""
    parts: "list[str]" = []
    cx = x
    for color, label in zip(BAND_COLORS, ("< 4%", "4–8%", "≥ 8%")):
        parts.append(f'<rect class="sp-legend" x="{cx:.1f}" y="{y - 9:.1f}" width="11" height="11" fill="{color}"/>')
        parts.append(_text(cx + 14, y, label, size=14, weight=600, fill=INK, ls="0.01em", cls="sp-legend"))
        cx += 56
    return "".join(parts)


def _finish_marker(x: float, y: float, *, direction: int) -> str:
    """The finish marker — a bold 2×2 checkered square, flying inward from its edge
    (``direction`` +1 right / -1 left)."""
    cell = 8.0
    bx = x if direction > 0 else x - 2 * cell
    cells = [
        f'<rect x="{bx + c * cell:.1f}" y="{y + r * cell:.1f}" width="{cell:g}" height="{cell:g}" '
        f'fill="{INK if (r + c) % 2 == 0 else PAPER}"/>'
        for r in range(2) for c in range(2)
    ]
    outline = (f'<rect x="{bx:.1f}" y="{y:.1f}" width="{2 * cell:g}" height="{2 * cell:g}" '
               f'fill="none" stroke="{INK}" stroke-width="1.25"/>')
    return f'<g class="sp-finish">{"".join(cells)}{outline}</g>'
