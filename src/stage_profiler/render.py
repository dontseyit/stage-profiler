"""The stage-profile SVG — an official-roadbook profile.

One baked-in look, no options: a fixed 640×192 (10:3) banner in the manner of the printed
Grand-Tour roadbook. The elevation silhouette is tinted with the race accent under a bold
ink outline; categorised climbs float over their summits (ink badge · altitude · name) on
hairline location rules that run down through the mountain to the km scale; sprint points
sit on the route line; a solid départ pennant and a checkered arrivée flag bookend the
corners, where the start / finish towns and their elevations anchor the foot, with the km
scale ticking along the foot between them.

The vertical scale floors the elevation span (:data:`FLOOR_SPAN_M`) so a flat classic stage
reads as flat instead of being stretched into fake mountains, while a real mountain stage
fills the frame.
"""

from __future__ import annotations

from typing import Sequence, Tuple

from .geometry import Series, ele_at, nice_tick_step
from .theme import (
    ACCENT,
    BACKGROUND,
    INK,
    INK_MUTE,
    PAPER,
    _fmt_ele,
    _num,
    _text,
)

__all__ = ["render_profile_svg", "WIDTH", "HEIGHT"]

_SVG_NS = "http://www.w3.org/2000/svg"

# Canvas & plot frame (fixed) — a 640×192 banner, a deliberate 10:3 ratio.
# The canvas is not configurable: SVG scales losslessly, so size it at display time.
WIDTH, HEIGHT = 640, 192
PAD_X = 20.0          # side padding around the corner text and the profile
BASE_Y = 148.0        # baseline bar (the km axis)
LINE_BOTTOM = 140.0   # the route's low point sits here (a foot of space above the baseline)
LINE_TOP = 76.0       # the top of the elevation span (room for the climb labels above)
PLOT_H = LINE_BOTTOM - LINE_TOP

# Floor the elevation span so low-relief stages stay visually flat.
FLOOR_SPAN_M = 1000.0

# Elevation line resolution (points across the width).
_LINE_POINTS = 300

# The silhouette tint — the race accent laid flat over the ground, roadbook-print style.
_FILL_OPACITY = 0.35

# Climb labels: two rows centred over each summit — the name, and beneath it the category
# badge + summit altitude — tied down by a location rule through the mountain. Labels near
# the frame edge slide inward; ones that would collide with a neighbour lift up a row.
_CLIMB_NAME_RISE = 26.0   # name baseline above the summit
_CLIMB_META_RISE = 13.0   # badge + altitude row above the summit
_CLIMB_EDGE_PAD = 55.0    # labels stay at least this far inside the frame edges
_CLIMB_LIFT = 26.0        # vertical de-collision step between neighbouring labels
_BADGE_H = 13.0

# Finish marker row — the top of the finish border rule.
_FLAG_Y = 20.0

# Foot: the km scale under the baseline bar, towns + elevations at the corners.
_KM_Y = 15.0
_TICK_LEN = 5.0       # scale ticks, below the baseline bar
_SCALE_DY = 16.0      # scale-numeral baseline, below BASE_Y (shares the row with the towns)
_TOWN_DY = 16.0       # town baseline, below BASE_Y
_ELE_DY = 29.0        # elevation baseline, below BASE_Y

Climb = Tuple[str, float, str]  # (name, summit_km, category "HC"|"1".."4"|"")


def render_profile_svg(
    series: Series,
    *,
    start_town: str = "",
    finish_town: str = "",
    climbs: "Sequence[Climb]" = (),
    sprints: "Sequence[float]" = (),
    accent: str = "",
) -> str:
    """Render ``series`` to a self-contained stage-profile SVG string.

    ``accent`` is the race colour (hex) tinting the silhouette; empty uses the default.
    ``sprints`` are intermediate-sprint locations in km along the route.
    """
    tint = accent or ACCENT
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

    # Climb summits, resolved and de-collided once. Their location rules are drawn *first*
    # so the translucent silhouette lays over them — full-strength above the profile,
    # ghosted through the mountain, the printed-roadbook layering.
    marks = _climb_marks(climbs, ds, es, total, x, y)
    for mark in marks:
        body.append(
            f'<line class="sp-leader" x1="{mark.px:.2f}" y1="{mark.meta_y + 4:.2f}" '
            f'x2="{mark.px:.2f}" y2="{_num(BASE_Y)}" stroke="{INK}" stroke-width="0.6"/>'
        )

    # The silhouette — race-accent tint under a bold ink outline.
    fill_d = (f"M{x(0):.2f},{_num(BASE_Y)} "
              + " ".join(f"L{px:.2f},{py:.2f}" for px, py in pts)
              + f" L{x(total):.2f},{_num(BASE_Y)} Z")
    body.append(
        f'<path class="sp-fill" d="{fill_d}" fill="{tint}" fill-opacity="{_FILL_OPACITY}"/>'
    )

    # Bold black baseline bar (the km axis) and elevation line.
    body.append(
        f'<line class="sp-baseline" x1="{_num(PAD_X)}" y1="{_num(BASE_Y)}" '
        f'x2="{_num(WIDTH - PAD_X)}" y2="{_num(BASE_Y)}" stroke="{INK}" stroke-width="2"/>'
    )
    body.append(
        f'<polyline class="sp-line" points="{line}" fill="none" stroke="{INK}" '
        f'stroke-width="2" stroke-linejoin="round" stroke-linecap="round"/>'
    )

    # Climb labels: name over badge + altitude, painted on top of the profile.
    for mark in marks:
        body.append(_climb_label(mark))

    # Sprint points, marked on the route line where they happen.
    for km in sprints:
        d = max(0.0, min(float(km) * 1000.0, total))
        body.append(_sprint_marker(x(d), y(ele_at(ds, es, d))))

    # Start (left) and finish (right) corners, bookended by their flags — a solid départ
    # pennant and the checkered arrivée. Both carry the full-height border rule; only the
    # finish adds the distance marker.
    body.append(_corner(PAD_X, start_town, es[0], "", marker="start", anchor="start", flag_dir=1, border=True))
    body.append(_corner(WIDTH - PAD_X, finish_town, es[-1], f"{total / 1000:.1f} KM",
                        marker="finish", anchor="end", flag_dir=-1, border=True))

    # The km scale along the foot, kept clear of the corner town names.
    body.append(_km_scale(total, x, start_town, finish_town))

    return (
        f'<svg xmlns="{_SVG_NS}" class="stage-profile" viewBox="0 0 {WIDTH} {HEIGHT}" '
        f'width="{WIDTH}" height="{HEIGHT}">' + "".join(body) + "</svg>"
    )


def _even_distances(total: float, n: int) -> "list[float]":
    return [total * i / (n - 1) for i in range(n)]


# ── Climbs ────────────────────────────────────────────────────────────────────

class _Mark:
    """A resolved climb label: where the rule stands and where the two rows sit."""

    __slots__ = ("name", "category", "ele", "px", "cx", "name_y", "meta_y")

    def __init__(self, name: str, category: str, ele: float, px: float, cx: float,
                 name_y: float, meta_y: float):
        self.name, self.category, self.ele = name, category, ele
        self.px, self.cx = px, cx
        self.name_y, self.meta_y = name_y, meta_y


def _climb_marks(climbs: "Sequence[Climb]", ds: "list[float]", es: "list[float]",
                 total: float, x, y) -> "list[_Mark]":
    """Resolve climb labels: summit position, edge-clamped text centre, and a single
    de-collision pass that lifts a label overlapping its left neighbour."""
    marks: "list[_Mark]" = []
    for name, km, category in climbs:
        d = max(0.0, min(float(km) * 1000.0, total))
        ele = ele_at(ds, es, d)
        px = x(d)
        cx = min(max(px, PAD_X + _CLIMB_EDGE_PAD), WIDTH - PAD_X - _CLIMB_EDGE_PAD)
        peak_y = y(ele)
        marks.append(_Mark(str(name), str(category), ele, px, cx,
                           peak_y - _CLIMB_NAME_RISE, peak_y - _CLIMB_META_RISE))
    marks.sort(key=lambda m: m.px)
    for prev, mark in zip(marks, marks[1:]):
        too_close = (mark.cx - prev.cx) < 110 and abs(mark.name_y - prev.name_y) < _CLIMB_LIFT
        if too_close:
            lift = min(mark.name_y, prev.name_y) - _CLIMB_LIFT
            mark.name_y, mark.meta_y = lift, lift + (_CLIMB_NAME_RISE - _CLIMB_META_RISE)
    return marks


def _climb_label(mark: _Mark) -> str:
    """The two label rows over a summit: bold name, then category badge + altitude."""
    parts = [_text(mark.cx, mark.name_y, mark.name, size=11, weight=700, fill=INK,
                   anchor="middle", ls="0.01em", cls="sp-climb")]
    alt = _fmt_ele(mark.ele)
    alt_w = len(alt) * 5.1
    if mark.category:
        badge_w = 20.0 if mark.category == "HC" else 13.0
        row_w = badge_w + 5 + alt_w
        bx = mark.cx - row_w / 2
        by = mark.meta_y - _BADGE_H + 3
        parts.append(
            f'<rect class="sp-cat" x="{bx:.1f}" y="{by:.1f}" width="{_num(badge_w)}" '
            f'height="{_num(_BADGE_H)}" fill="{INK}"/>'
        )
        parts.append(_text(bx + badge_w / 2, mark.meta_y, mark.category, size=8.5,
                           weight=700, fill=PAPER, anchor="middle", ls="0.04em", cls="sp-cat"))
        parts.append(_text(bx + badge_w + 5, mark.meta_y, alt, size=9.5, weight=500,
                           fill=INK_MUTE, cls="sp-climb-ele"))
    else:
        parts.append(_text(mark.cx, mark.meta_y, alt, size=9.5, weight=500,
                           fill=INK_MUTE, anchor="middle", cls="sp-climb-ele"))
    return "".join(parts)


# ── Sprints ───────────────────────────────────────────────────────────────────

def _sprint_marker(px: float, py: float) -> str:
    """An intermediate sprint on the route line — a paper roundel with an ink ``S``."""
    return (
        f'<g class="sp-sprint">'
        f'<circle cx="{px:.2f}" cy="{py:.2f}" r="6.5" fill="{PAPER}" '
        f'stroke="{INK}" stroke-width="1.5"/>'
        + _text(px, py + 3, "S", size=8, weight=700, fill=INK, anchor="middle")
        + "</g>"
    )


# ── Foot & corners ────────────────────────────────────────────────────────────

def _km_scale(total: float, x, start_town: str, finish_town: str) -> str:
    """Ticks + numerals along the foot, skipping steps that would crowd the corner towns."""
    total_km = total / 1000
    step = nice_tick_step(total_km, 7)
    decimals = 0 if step >= 1 else (1 if step >= 0.1 else 2)
    left_clear = PAD_X + (len(start_town) * 8.2 + 14 if start_town else 0)
    right_clear = WIDTH - PAD_X - (len(finish_town) * 8.2 + 14 if finish_town else 0)
    parts: "list[str]" = []
    km = step
    while km < total_km - step / 2:
        px = x(km * 1000)
        if left_clear <= px <= right_clear:
            parts.append(
                f'<line class="sp-scale" x1="{px:.1f}" x2="{px:.1f}" '
                f'y1="{_num(BASE_Y + 2)}" y2="{_num(BASE_Y + 2 + _TICK_LEN)}" '
                f'stroke="{INK}" stroke-width="1"/>'
            )
            parts.append(_text(px, BASE_Y + _SCALE_DY, f"{km:.{decimals}f}", size=8.5,
                               weight=500, fill=INK_MUTE, anchor="middle", cls="sp-scale"))
        km += step
    return "".join(parts)


def _corner(x_edge: float, town: str, ele: float, km_label: str, *,
            marker: str, anchor: str, flag_dir: int, border: bool) -> str:
    """A start/finish corner: the flag up top (a solid pennant for the start, the checkered
    flag for the finish), an optional distance marker, and the town + its elevation at the
    foot. When ``border`` is set a hairline rule runs the full height, tying the corner to
    the route — and serving as the flagpole the pennant flies from."""
    if not town:
        return ""
    parts: "list[str]" = []
    if km_label:
        parts.append(_text(x_edge, _KM_Y, km_label, size=16, weight=700, fill=INK, anchor=anchor, ls="0.04em", cls="sp-dist"))
    if border:
        parts.append(f'<line class="sp-border" x1="{x_edge:.1f}" y1="{_FLAG_Y:.1f}" '
                     f'x2="{x_edge:.1f}" y2="{BASE_Y:.1f}" stroke="{INK}" stroke-width="2"/>')
    if marker == "finish":
        parts.append(_finish_marker(x_edge, _FLAG_Y, direction=flag_dir))
    elif marker == "start":
        parts.append(_start_marker(x_edge, _FLAG_Y, direction=flag_dir))
    parts.append(_text(x_edge, BASE_Y + _TOWN_DY, town.upper(), size=14, weight=700, fill=INK, anchor=anchor, ls="0.02em", cls="sp-town"))
    parts.append(_text(x_edge, BASE_Y + _ELE_DY + 2, _fmt_ele(ele), size=12, weight=500, fill=INK_MUTE, anchor=anchor, ls="0.04em", cls="sp-ele"))
    return "".join(parts)


def _start_marker(x: float, y: float, *, direction: int) -> str:
    """The start marker — a solid pennant flying inward from the corner's border rule, which
    doubles as its flagpole (``direction`` +1 right / -1 left)."""
    tip = x + direction * 12.0
    return (
        f'<g class="sp-start">'
        f'<path d="M{x:.1f},{y:.1f} L{tip:.1f},{y + 4.5:.1f} L{x:.1f},{y + 9:.1f} Z" fill="{INK}"/>'
        f'</g>'
    )


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
