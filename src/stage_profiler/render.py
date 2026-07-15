"""The stage-profile SVG — an official-roadbook profile.

One baked-in look, no options: a fixed 640×192 (10:3) banner in the manner of the printed
Grand-Tour roadbook. The elevation silhouette is filled with the race accent segmented by
steepness — three opacities, darker tones for steeper gradients — under a bold ink outline;
categorised climbs float over their summits (ink badge · altitude · name) on
hairline location rules that run down through the mountain to the km scale; sprint points
sit on the route line, each over its own rule to the km scale; a solid départ pennant and a
checkered arrivée flag bookend the corners, where the start / finish towns and their
elevations anchor the foot, with the km scale ticking along the foot between them. A climb
that tops out at the finish (a mountaintop finish) shows its category badge just below the
finish flag instead of a floating label the flag would collide with. A climb name may carry
a newline to wrap onto stacked lines.

The vertical scale floors the elevation span (:data:`FLOOR_SPAN_M`) so a flat classic stage
reads as flat instead of being stretched into fake mountains, while a real mountain stage
fills the frame.
"""

from __future__ import annotations

from typing import Sequence, Tuple

from .geometry import Series, ele_at, nice_tick_step
from .steepness import steepness_bands
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

# The silhouette is filled per steepness band with the accent at that tier's BAND_OPACITY —
# darker tones for steeper gradients (see theme.BAND_OPACITY).

# Climb labels: two rows centred over each summit — the name, and beneath it the category
# badge + summit altitude — tied down by a location rule through the mountain. Labels near
# the frame edge slide inward; ones that would collide with a neighbour lift up a row.
_CLIMB_NAME_RISE = 26.0   # name baseline above the summit
_CLIMB_META_RISE = 13.0   # badge + altitude row above the summit
_CLIMB_EDGE_PAD = 55.0    # labels stay at least this far inside the frame edges
_CLIMB_LIFT = 26.0        # vertical de-collision step between neighbouring labels
_CLIMB_CHAR_W = 3.1       # ≈ half a name character's width (size 11) — keeps names on-canvas
_CLIMB_LINE_H = 12.0      # line height for a multi-line (newline-split) climb name
_BADGE_H = 13.0

# A climb whose summit sits within this of the finish is a mountaintop finish: its badge
# moves onto the finish corner instead of a floating label that would collide with the flag.
_SUMMIT_FINISH_TOL_M = 1000.0

# Finish marker row — the top of the finish border rule.
_FLAG_Y = 20.0

# Foot: the km scale under the baseline bar, towns + elevations at the corners.
_KM_Y = 15.0
_TICK_LEN = 5.0       # scale ticks, below the baseline bar
_SCALE_DY = 16.0      # scale-numeral baseline, below BASE_Y (shares the row with the towns)
_TOWN_DY = 16.0       # town baseline, below BASE_Y
_ELE_DY = 29.0        # elevation baseline, below BASE_Y

Climb = Tuple[str, float, str, float]  # (name, summit_km, category "HC"|"1".."4"|"", label_offset)


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
    line_ds = _even_distances(total, _LINE_POINTS)
    pts = [(x(d), y(ele_at(ds, es, d))) for d in line_ds]
    line = " ".join(f"{px:.2f},{py:.2f}" for px, py in pts)

    body: "list[str]" = [
        f'<rect class="sp-bg" width="{WIDTH}" height="{HEIGHT}" fill="{BACKGROUND}"/>',
    ]

    # A climb topping out at (or within a stride of) the finish is a mountaintop finish: its
    # badge belongs on the finish corner, not a floating label colliding with the flag and
    # distance — the finish town + elevation already carry its name and height. (Kept as a
    # normal label when there's no finish town to carry the name.)
    finish_category = ""
    field_climbs: "list[Climb]" = []
    summit_tol = min(_SUMMIT_FINISH_TOL_M, total * 0.1)  # bound it on short routes
    for climb in climbs:
        if finish_town and float(climb[1]) * 1000.0 >= total - summit_tol:
            finish_category = climb[2] or finish_category
        else:
            field_climbs.append(climb)

    # Climb summits, resolved and de-collided once. Location rules — for climbs and sprints
    # alike — are drawn *first* so the translucent silhouette lays over them: full-strength
    # above the profile, ghosted through the mountain, the printed-roadbook layering.
    marks = _climb_marks(field_climbs, ds, es, total, x, y)
    sprint_pts = [(x(d), y(ele_at(ds, es, d)))
                  for d in (max(0.0, min(float(km) * 1000.0, total)) for km in sprints)]
    for mark in marks:
        body.append(
            f'<line class="sp-leader" x1="{mark.px:.2f}" y1="{mark.meta_y + 4:.2f}" '
            f'x2="{mark.px:.2f}" y2="{_num(BASE_Y)}" stroke="{INK}" stroke-width="0.6"/>'
        )
    for spx, spy in sprint_pts:
        body.append(
            f'<line class="sp-leader" x1="{spx:.2f}" y1="{spy:.2f}" '
            f'x2="{spx:.2f}" y2="{_num(BASE_Y)}" stroke="{INK}" stroke-width="0.6"/>'
        )

    # The silhouette, segmented by steepness — the accent at three opacities (light → dark for
    # gentle → steep), under a bold ink outline. Each band is its own filled slice under the
    # line, so the SVG stays self-contained (no shared clip-path id to collide when several
    # profiles are inlined on one page).
    dist_pts = list(zip(line_ds, pts))
    bands = "".join(_band_fill(band, tint, dist_pts, x, y, ds, es)
                    for band in steepness_bands(series))
    body.append(f'<g class="sp-fill">{bands}</g>')

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

    # Sprint roundels on the route line (their location rules are drawn above, with the climbs').
    for spx, spy in sprint_pts:
        body.append(_sprint_marker(spx, spy))

    # Start (left) and finish (right) corners, bookended by their flags — a solid départ
    # pennant and the checkered arrivée. Both carry the full-height border rule; only the
    # finish adds the distance marker.
    body.append(_corner(PAD_X, start_town, es[0], "", marker="start", anchor="start", flag_dir=1, border=True))
    body.append(_corner(WIDTH - PAD_X, finish_town, es[-1], f"{total / 1000:.1f} KM",
                        marker="finish", anchor="end", flag_dir=-1, border=True,
                        category=finish_category))

    # The km scale along the foot, kept clear of the corner town names.
    body.append(_km_scale(total, x, start_town, finish_town))

    return (
        f'<svg xmlns="{_SVG_NS}" class="stage-profile" viewBox="0 0 {WIDTH} {HEIGHT}" '
        f'width="{WIDTH}" height="{HEIGHT}">' + "".join(body) + "</svg>"
    )


def _even_distances(total: float, n: int) -> "list[float]":
    return [total * i / (n - 1) for i in range(n)]


def _band_fill(band, tint: str, dist_pts, x, y, ds: "list[float]", es: "list[float]") -> str:
    """One steepness band as a filled slice of the area under the line — the accent at the
    tier's opacity (darker = steeper). ``dist_pts`` are the ``(distance, (px, py))`` line
    samples; the band spans ``[band.d0, band.d1)`` with its ends interpolated onto the line."""
    d0, d1 = band.d0, band.d1
    top = [(x(d0), y(ele_at(ds, es, d0)))]
    top += [pt for d, pt in dist_pts if d0 < d < d1]
    top.append((x(d1), y(ele_at(ds, es, d1))))
    seg = " ".join(f"L{px:.2f},{py:.2f}" for px, py in top)
    d_attr = f"M{x(d0):.2f},{_num(BASE_Y)} {seg} L{x(d1):.2f},{_num(BASE_Y)} Z"
    return f'<path class="sp-band" d="{d_attr}" fill="{tint}" fill-opacity="{band.opacity:g}"/>'


# ── Climbs ────────────────────────────────────────────────────────────────────

def _name_lines(name: str) -> "list[str]":
    """Split a climb name on explicit newlines into stacked label lines, trimming each and
    dropping blanks — so a long name can be wrapped by hand. Always at least one line."""
    lines = [ln.strip() for ln in str(name).split("\n")]
    return [ln for ln in lines if ln] or [""]


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
    for name, km, category, offset in climbs:
        d = max(0.0, min(float(km) * 1000.0, total))
        ele = ele_at(ds, es, d)
        px = x(d)
        # The label centre is the summit x plus the per-climb offset (to pull overlapping
        # labels apart); the leader rule stays at ``px``. Keep the whole centred label
        # on-canvas: inset by half its widest line, never less than the base edge pad.
        widest = max(len(ln) for ln in _name_lines(name))
        half_w = max(_CLIMB_EDGE_PAD, widest * _CLIMB_CHAR_W)
        lo, hi = PAD_X + half_w, WIDTH - PAD_X - half_w
        cx = (lo + hi) / 2 if lo > hi else min(max(px + offset, lo), hi)
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
    """The label over a summit: the (optionally multi-line) name, then category badge +
    altitude. Extra name lines stack *upward*, keeping the last line just over the badge."""
    lines = _name_lines(mark.name)
    parts = [
        _text(mark.cx, mark.name_y - (len(lines) - 1 - i) * _CLIMB_LINE_H, line,
              size=11, weight=700, fill=INK, anchor="middle", ls="0.01em", cls="sp-climb")
        for i, line in enumerate(lines)
    ]
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
            marker: str, anchor: str, flag_dir: int, border: bool, category: str = "") -> str:
    """A start/finish corner: the flag up top (a solid pennant for the start, the checkered
    flag for the finish), an optional distance marker, and the town + its elevation at the
    foot. When ``border`` is set a hairline rule runs the full height, tying the corner to
    the route — and serving as the flagpole the pennant flies from. ``category`` sets a
    climb-category badge inboard of the finish flag (a mountaintop finish)."""
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
        if category:
            parts.append(_finish_badge(x_edge, category, direction=flag_dir))
    elif marker == "start":
        parts.append(_start_marker(x_edge, _FLAG_Y, direction=flag_dir))
    parts.append(_text(x_edge, BASE_Y + _TOWN_DY, town.upper(), size=14, weight=700, fill=INK, anchor=anchor, ls="0.02em", cls="sp-town"))
    parts.append(_text(x_edge, BASE_Y + _ELE_DY + 2, _fmt_ele(ele), size=12, weight=500, fill=INK_MUTE, anchor=anchor, ls="0.04em", cls="sp-ele"))
    return "".join(parts)


def _finish_badge(x_edge: float, category: str, *, direction: int) -> str:
    """A climb-category badge for a mountaintop finish, centred just below the checkered flag
    (``direction`` -1 = flag flies left from the right edge)."""
    badge_w = 20.0 if category == "HC" else 13.0
    flag_w = 16.0
    flag_center = x_edge - flag_w / 2 if direction < 0 else x_edge + flag_w / 2
    bx = flag_center - badge_w / 2 + direction * 2.0   # nudge off the corner's border rule
    by = _FLAG_Y + flag_w + 5.0   # below the flag (flag runs _FLAG_Y … _FLAG_Y + flag_w)
    return (
        f'<rect class="sp-cat" x="{bx:.1f}" y="{by:.1f}" width="{_num(badge_w)}" '
        f'height="{_num(_BADGE_H)}" fill="{INK}"/>'
        + _text(bx + badge_w / 2, by + 10, category, size=8.5, weight=700, fill=PAPER,
                anchor="middle", ls="0.04em", cls="sp-cat")
    )


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
