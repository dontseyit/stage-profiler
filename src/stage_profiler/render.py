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
    ACCENT,
    BACKGROUND,
    BASELINE,
    INK,
    INK_MUTE,
    INK_SOFT,
    PAPER,
    _fmt_ele,
    _num,
    _text,
)

__all__ = ["render_profile_svg", "WIDTH", "HEIGHT"]

_SVG_NS = "http://www.w3.org/2000/svg"

# Canvas & plot frame (fixed) — a compact 768×128 banner strip.
WIDTH, HEIGHT = 768, 128
PAD_X = 14.0
BASE_Y = 102.0        # baseline hairline
LINE_BOTTOM = 94.0    # the route's low point sits here (a foot of space above the baseline)
LINE_TOP = 44.0       # the top of the elevation span sits here (room for climb labels above)
PLOT_H = LINE_BOTTOM - LINE_TOP

# Floor the elevation span so low-relief stages stay visually flat.
FLOOR_SPAN_M = 1000.0

# Elevation line resolution (points across the width).
_LINE_POINTS = 300

# Climb labels: centred over each summit (the centre of the near-highest stretch within
# this window — a plateau at its middle, a peak at its point), a fixed rise above it and
# tied down by a thin leader. Different summit heights separate the names vertically.
_SUMMIT_WINDOW_M = 2000.0
_SUMMIT_TOL_M = 10.0
_CLIMB_RISE = 11.0

# Start/finish flag row — the top of each corner border rule.
_FLAG_Y = 18.0

# Foot labels (town + elevation) and the km marker, relative to the frame.
_KM_Y = 12.0
_TOWN_DY = 12.0       # town baseline, below BASE_Y
_ELE_DY = 22.0        # elevation baseline, below BASE_Y

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
        f'<line class="sp-baseline" x1="{_num(PAD_X)}" y1="{_num(BASE_Y)}" '
        f'x2="{_num(WIDTH - PAD_X)}" y2="{_num(BASE_Y)}" stroke="{BASELINE}" stroke-width="1"/>',
    ]

    # Steepness bands, clipped to the silhouette under the line.
    clip = (f"M{x(0):.2f},{BASE_Y} "
            + " ".join(f"L{px:.2f},{py:.2f}" for px, py in pts)
            + f" L{x(total):.2f},{BASE_Y} Z")
    rects = []
    for band in steepness_bands(series):
        bx = x(band.d0)
        rects.append(
            f'<rect class="sp-band" x="{bx:.2f}" y="0" width="{x(band.d1) - bx:.2f}" '
            f'height="{_num(BASE_Y)}" fill="{ACCENT}" opacity="{band.opacity:g}"/>'
        )
    body.append(
        f'<defs><clipPath id="sp-clip"><path d="{clip}"/></clipPath></defs>'
        f'<g clip-path="url(#sp-clip)">{"".join(rects)}</g>'
    )

    body.append(
        f'<polyline class="sp-line" points="{line}" fill="none" stroke="{INK}" '
        f'stroke-width="2" stroke-linejoin="round" stroke-linecap="round"/>'
    )

    # Climb names centred over each summit, a fixed rise above it, tied down by a thin
    # leader. Taller climbs' names sit higher, which also keeps close summits from colliding.
    for name, km in climbs:
        d = _summit(ds, es, max(0.0, min(km * 1000.0, total)), total)
        px, peak_y = x(d), y(ele_at(ds, es, d))
        label_y = peak_y - _CLIMB_RISE
        body.append(
            f'<line class="sp-leader" x1="{px:.2f}" y1="{label_y + 3:.2f}" x2="{px:.2f}" '
            f'y2="{peak_y - 3:.2f}" stroke="{INK_MUTE}" stroke-width="1"/>'
        )
        body.append(_text(
            px, label_y, str(name),
            size=11, weight=600, fill=INK_SOFT, anchor="middle", ls="0.01em", cls="sp-climb",
        ))

    # Start (left) and finish (right) corners: town + elevation at the foot for both. Only
    # the finish carries the distance marker and the full-height border rule; the start flag
    # simply flies from its own short pole.
    body.append(_corner(PAD_X, start_town, es[0], "", checker=False, anchor="start", flag_dir=1, border=False))
    body.append(_corner(WIDTH - PAD_X, finish_town, es[-1], f"{total / 1000:.1f} KM",
                        checker=True, anchor="end", flag_dir=-1, border=True))

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
    """A start/finish corner: an optional distance marker (km-axis endpoint) and a flag up
    top, the town and its elevation at the foot. When ``border`` is set, a rule runs the full
    height between them, planting the flag and tying the corner to the route; otherwise the
    flag flies from its own short pole."""
    if not town:
        return ""
    parts: "list[str]" = []
    if km_label:
        parts.append(_text(x_edge, _KM_Y, km_label, size=12, weight=600, fill=INK_SOFT, anchor=anchor, ls="0.04em", cls="sp-dist"))
    if border:
        parts.append(f'<line class="sp-border" x1="{x_edge:.1f}" y1="{_FLAG_Y:.1f}" '
                     f'x2="{x_edge:.1f}" y2="{BASE_Y:.1f}" stroke="{INK}" stroke-width="1.3"/>')
    parts.append(_flag(x_edge, _FLAG_Y, checker=checker, direction=flag_dir, pole=not border))
    parts.append(_text(x_edge, BASE_Y + _TOWN_DY, town.upper(), size=13, weight=700, fill=INK, anchor=anchor, ls="0.02em", cls="sp-town"))
    parts.append(_text(x_edge, BASE_Y + _ELE_DY, _fmt_ele(ele), size=10, weight=500, fill=INK_MUTE, anchor=anchor, ls="0.04em", cls="sp-ele"))
    return "".join(parts)


def _flag(pole_x: float, y: float, *, checker: bool, direction: int, pole: bool) -> str:
    """A start/finish flag: a solid accent pennant (start) or a checkered flag (finish), in
    ``direction`` (+1 right / -1 left) so both fly inward. With ``pole`` it carries its own
    short staff; otherwise it flies from the corner border drawn by :func:`_corner`."""
    d = 1.0 if direction > 0 else -1.0
    staff = ([f'<line x1="{pole_x:.1f}" y1="{y:.1f}" x2="{pole_x:.1f}" y2="{y + 18:.1f}" '
              f'stroke="{INK}" stroke-width="1.6" stroke-linecap="round"/>'] if pole else [])
    if not checker:
        fw, fh = 13.0, 9.0
        tip = pole_x + d * fw
        pennant = (f'<path d="M{pole_x:.1f},{y:.1f} L{tip:.1f},{y + fh / 2:.1f} '
                   f'L{pole_x:.1f},{y + fh:.1f} Z" fill="{ACCENT}"/>')
        return f'<g class="sp-start">{"".join(staff)}{pennant}</g>'
    cell, cols, rows = 5.0, 3, 2
    bx = pole_x if d > 0 else pole_x - cols * cell
    cells = staff + [
        f'<rect x="{bx + c * cell:.1f}" y="{y + r * cell:.1f}" width="{cell}" height="{cell}" '
        f'fill="{INK if (r + c) % 2 == 0 else PAPER}"/>'
        for r in range(rows) for c in range(cols)
    ]
    outline = (f'<rect x="{bx:.1f}" y="{y:.1f}" width="{cols * cell}" height="{rows * cell}" '
               f'fill="none" stroke="{INK}" stroke-width="1"/>')
    return f'<g class="sp-finish">{"".join(cells)}{outline}</g>'
