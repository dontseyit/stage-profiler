"""SVG generation.

Produces a self-contained SVG *string* from a sampled :class:`~stage_profiler.geometry.Series`.
Fonts are referenced (not embedded): inline the SVG in a page that loads the display and
body fonts and the type renders correctly, while the output stays tiny and cache-friendly.
Every meaningful element carries an ``sp-*`` class so downstream CSS can theme it.

There are no baked-in presets — everything (canvas size, margins, header style, colours,
axis behaviour) is configured through :class:`RenderOptions`.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from xml.sax.saxutils import escape

_ATTR_ESCAPE = {'"': "&quot;", "'": "&#39;"}


def _attr(v: str) -> str:
    """Escape a string for safe interpolation into an SVG attribute value."""
    return escape(v, _ATTR_ESCAPE)

from .geometry import Series, moving_average, nice_tick_step, slope_at
from .ramp import grad_color

__all__ = ["RenderOptions", "render_svg", "auto_y_range", "DEFAULT_COLOR", "CHART_BG"]

_SVG_NS = "http://www.w3.org/2000/svg"

# Default font stacks and colours. Override per render via RenderOptions where applicable.
DISPLAY_STACK = "'Bebas Neue','Oswald','Arial Narrow',sans-serif"
BODY_STACK = "'Barlow','Helvetica Neue',Arial,sans-serif"
DEFAULT_COLOR = "#c8f135"
CHART_BG = "#0c0f0b"

_HEADERS = ("full", "minimal", "none")

# Cross-compatible altitude axis so profiles stay comparable. The floor sits just below
# the route's lowest point; the ceiling is a standardised *minimum* (taller for long
# routes), and the axis top is the larger of that minimum and peak + AUTO_Y_HEADROOM —
# so flat routes stay pinned/comparable while real climbs always breathe above the peak.
AUTO_Y_FLOOR = 500.0        # minimum ceiling for short routes
AUTO_Y_FLOOR_LONG = 2000.0  # taller minimum ceiling for long routes (> AUTO_Y_LONG_KM)
AUTO_Y_LONG_KM = 100.0      # distance (km) above which the taller minimum applies
AUTO_Y_HEADROOM = 1000.0    # axis top clears the peak by at least this much
AUTO_Y_FOOTROOM = 10.0      # floor sits this far below the route's lowest point


@dataclass
class RenderOptions:
    """Everything tunable about a single render — there are no presets, only this.

    Canvas & layout
        ``width`` / ``height`` — SVG size in user units (the exported/viewBox size).
        ``margin_*`` — plot inset; give the header room in ``margin_top``.
        ``header`` — ``"full"`` (kicker + title + stat blocks), ``"minimal"`` (one line),
        or ``"none"``. The ``"full"`` header is designed for ``margin_top`` ≈ 116 and
        ``"minimal"`` for ≈ 34.

    Axis
        ``axis_size`` / ``tick_gap`` / ``x_tick_dy`` / ``x_ticks`` — tick type and spacing.

    Altitude range (priority: ``auto_y`` → manual ``y_min``/``y_max`` → tight auto-fit)
        ``auto_y`` — cross-compatible axis so routes stay comparable (see :func:`auto_y_range`).
        ``y_min`` / ``y_max`` — a manual range, when *both* are given.

    Appearance
        ``color`` — accent (line + solid fill). ``gradient_shading`` — colour the fill by
        steepness. ``fill`` — shade under the line, or ``False`` for line-only.
        ``stroke_grad`` / ``stroke_solid`` — line widths for shaded vs solid/line-only.
        ``smoothing`` — moving-average radius (points) applied to the drawn line only.
        ``background`` — draw the dark backdrop, or ``False`` for a transparent canvas.
        ``bare`` — profile only: no header/axes/labels/background, silhouette edge-to-edge.
    """

    # canvas & layout
    width: int = 1280
    height: int = 520
    margin_top: float = 116
    margin_right: float = 36
    margin_bottom: float = 48
    margin_left: float = 58
    header: str = "full"
    # axis
    axis_size: float = 12
    tick_gap: float = 10
    x_tick_dy: float = 22
    x_ticks: int = 8
    # appearance
    color: str = DEFAULT_COLOR
    gradient_shading: bool = True
    fill: bool = True
    stroke_grad: float = 1.6
    stroke_solid: float = 2.4
    smoothing: int = 0
    background: bool = True
    bare: bool = False
    # altitude range
    auto_y: bool = False
    y_min: "float | None" = None
    y_max: "float | None" = None


def auto_y_range(min_ele_m: float, max_ele_m: float, total_distance_m: float) -> "tuple[float, float]":
    """The cross-compatible altitude axis for a route.

    Floor sits :data:`AUTO_Y_FOOTROOM` below the route's lowest point. The ceiling is a
    standardised *minimum* — :data:`AUTO_Y_FLOOR_LONG` for routes longer than
    :data:`AUTO_Y_LONG_KM`, otherwise :data:`AUTO_Y_FLOOR` — and the axis top is the
    larger of that minimum and the peak plus :data:`AUTO_Y_HEADROOM`. So flat routes stay
    pinned to a common frame while real climbs always breathe above their peak.
    """
    ceiling = AUTO_Y_FLOOR_LONG if total_distance_m / 1000 > AUTO_Y_LONG_KM else AUTO_Y_FLOOR
    low = min_ele_m - AUTO_Y_FOOTROOM
    high = max(ceiling, max_ele_m + AUTO_Y_HEADROOM)
    return low, high


def _round_half_up(v: float) -> int:
    """Round half toward +∞ (stable, direction-independent tick/label rounding)."""
    return math.floor(v + 0.5)


def _num(v: "float | int") -> str:
    """Compact numeric formatting: drop trailing zeros, keep integers clean."""
    if isinstance(v, int):
        return str(v)
    if float(v).is_integer():
        return str(int(v))
    return f"{v:.2f}".rstrip("0").rstrip(".")


def _stack(font: str) -> str:
    return DISPLAY_STACK if font == "display" else BODY_STACK


def _text(
    x: float,
    y: float,
    text: str,
    *,
    anchor: str = "start",
    size: float = 12,
    fill: str = "#9aa291",
    font: str = "body",
    weight: "int | None" = None,
    ls: "str | None" = None,
    baseline: "str | None" = None,
    cls: "str | None" = None,
    tspans: str = "",
) -> str:
    parts = [
        f'<text x="{_num(x)}" y="{_num(y)}"',
        f'text-anchor="{anchor}"',
        f'font-size="{_num(size)}"',
        f'fill="{fill}"',
        f'font-family="{_stack(font)}"',
    ]
    if weight is not None:
        parts.append(f'font-weight="{weight}"')
    if ls is not None:
        parts.append(f'letter-spacing="{ls}"')
    if baseline is not None:
        parts.append(f'dominant-baseline="{baseline}"')
    if cls is not None:
        parts.append(f'class="{cls}"')
    return " ".join(parts) + ">" + escape(str(text)) + tspans + "</text>"


def _tspan(
    text: str,
    *,
    font: "str | None" = None,
    size: "float | None" = None,
    fill: "str | None" = None,
    weight: "int | None" = None,
    dx: "float | None" = None,
) -> str:
    parts = ["<tspan"]
    if font is not None:
        parts.append(f'font-family="{_stack(font)}"')
    if size is not None:
        parts.append(f'font-size="{_num(size)}"')
    if fill is not None:
        parts.append(f'fill="{fill}"')
    if weight is not None:
        parts.append(f'font-weight="{weight}"')
    if dx is not None:
        parts.append(f'dx="{_num(dx)}"')
    return " ".join(parts) + ">" + escape(str(text)) + "</tspan>"


def _divider(x1: float, x2: float, yy: float) -> str:
    return (
        f'<line class="sp-divider" x1="{_num(x1)}" x2="{_num(x2)}" '
        f'y1="{_num(yy)}" y2="{_num(yy)}" stroke="#262d22" stroke-width="1"/>'
    )


def _truncate(s: str, max_len: int) -> str:
    return (s[: max_len - 1].rstrip() + "…") if len(s) > max_len else s


# --- stat formatting (single source of truth) ---------------------------------

def _distance_km(series: Series) -> str:
    km = series.metrics.total_distance_km
    return f"{km:.0f}" if km >= 100 else f"{km:.1f}"


def _gain(series: Series) -> str:
    return f"{_round_half_up(series.metrics.ascent_m):,}"


def _max_alt(series: Series) -> str:
    return f"{_round_half_up(series.metrics.max_ele_m):,}"


# --- header renderers ---------------------------------------------------------

def _full_header(series: Series, name: str, width: float, left: float, right: float, color: str) -> str:
    out = [
        _text(left, 42, "STAGE PROFILE", size=13, weight=600, fill=color, ls="0.34em", cls="sp-kicker"),
        _text(left, 86, name, size=46, font="display", fill="#f1eee2", ls="0.01em", cls="sp-title"),
    ]
    head_stats = [
        ("DISTANCE", _distance_km(series), "KM", False),
        ("ELEV GAIN", _gain(series), "M", True),
        ("MAX ALT", _max_alt(series), "M", False),
    ]
    n = len(head_stats)
    for i, (label, value, unit, accent) in enumerate(head_stats):
        xr = width - right - (n - 1 - i) * 172
        out.append(_text(xr, 50, label, size=11, weight=600, fill="#6b7363", anchor="end", ls="0.16em", cls="sp-stat-label"))
        unit_span = _tspan(unit, font="body", size=14, weight=600, fill="#9aa291", dx=3)
        out.append(
            _text(
                xr, 86, value, size=34, font="display", anchor="end",
                fill=(color if accent else "#f1eee2"), ls="0.01em", cls="sp-stat-value", tspans=unit_span,
            )
        )
    out.append(_divider(left, width - right, 100))
    return "".join(out)


def _minimal_header(series: Series, name: str, width: float, left: float, right: float, top: float, color: str) -> str:
    title = _text(left, 21, _truncate(name, 18), size=15, font="display", fill="#f1eee2", ls="0.01em", cls="sp-title")
    tspans = (
        _tspan("KM", font="body", size=8, weight=600, fill="#9aa291", dx=2)
        + _tspan("↑" + _gain(series), font="display", size=13, fill=color, dx=8)
        + _tspan("M", font="body", size=8, weight=600, fill="#9aa291", dx=2)
    )
    stat = _text(
        width - right, 21, _distance_km(series), size=13, font="display",
        anchor="end", fill="#f1eee2", ls="0.01em", cls="sp-stat-value", tspans=tspans,
    )
    return title + stat + _divider(left, width - right, top - 4)


def _format_km_tick(km: float, step: float) -> str:
    decimals = 0 if step >= 1 else (1 if step >= 0.1 else 2)
    return f"{km:.{decimals}f}"


def _defs(options: RenderOptions, ds: "list[float]", elevations: "list[float]", x_max: float) -> str:
    if options.gradient_shading:
        n = 160
        stops = [f'<stop offset="0" stop-color="{grad_color(slope_at(ds, elevations, 0, x_max / n))}"/>']
        for i in range(n):
            d0 = (i / n) * x_max
            d1 = ((i + 1) / n) * x_max
            stops.append(f'<stop offset="{(i + 0.5) / n:.4f}" stop-color="{grad_color(slope_at(ds, elevations, d0, d1))}"/>')
        stops.append(f'<stop offset="1" stop-color="{grad_color(slope_at(ds, elevations, x_max - x_max / n, x_max))}"/>')
        grad = f'<linearGradient id="steepFill" x1="0" y1="0" x2="1" y2="0">{"".join(stops)}</linearGradient>'
    else:
        grad = (
            '<linearGradient id="accentFill" x1="0" y1="0" x2="0" y2="1">'
            f'<stop offset="0" stop-color="{_attr(options.color)}" stop-opacity="0.55"/>'
            f'<stop offset="1" stop-color="{_attr(options.color)}" stop-opacity="0.04"/>'
            "</linearGradient>"
        )
    return f"<defs>{grad}</defs>"


def _y_bounds(series: Series, opts: RenderOptions) -> "tuple[float, float]":
    if opts.auto_y:
        return auto_y_range(series.metrics.min_ele_m, series.metrics.max_ele_m, series.metrics.total_distance_m)
    if opts.y_min is not None and opts.y_max is not None:
        if opts.y_max <= opts.y_min:
            raise ValueError(f"y_max ({opts.y_max}) must be greater than y_min ({opts.y_min}).")
        return opts.y_min, opts.y_max
    y_min = math.floor(series.metrics.min_ele_m)
    y_max = math.ceil(series.metrics.max_ele_m)
    y_range = max(y_max - y_min, 1)
    return y_min - y_range * 0.06, y_max + y_range * 0.08


def render_svg(series: Series, name: str = "ROUTE", options: "RenderOptions | None" = None) -> str:
    """Render ``series`` to a self-contained SVG string, configured by ``options``."""
    opts = options or RenderOptions()
    if opts.header not in _HEADERS:
        raise ValueError(f"header must be one of {_HEADERS}, got {opts.header!r}")

    width, height = opts.width, opts.height
    bare = opts.bare
    color = _attr(opts.color)

    top, right, bottom, left = (0.0, 0.0, 0.0, 0.0) if bare else (
        opts.margin_top, opts.margin_right, opts.margin_bottom, opts.margin_left
    )
    inner_w = width - left - right
    inner_h = height - top - bottom
    baseline_y = top + inner_h

    x_max = series.metrics.total_distance_m or 1.0
    y_low, y_high = _y_bounds(series, opts)

    def x(d: float) -> float:
        return left + (d / x_max) * inner_w

    def y(e: float) -> float:
        return top + inner_h - ((e - y_low) / (y_high - y_low)) * inner_h

    elevations = moving_average([s.elevation_m for s in series.samples], opts.smoothing)
    ds = [s.distance_m for s in series.samples]

    body: "list[str]" = []

    # Background (skipped when bare or disabled → transparent)
    if not bare and opts.background:
        body.append(f'<rect class="sp-bg" width="{_num(width)}" height="{_num(height)}" fill="{CHART_BG}"/>')

    body.append(_defs(opts, ds, elevations, x_max))

    # Header band
    if not bare and opts.header != "none":
        if opts.header == "minimal":
            body.append(_minimal_header(series, name, width, left, right, top, color))
        else:
            body.append(_full_header(series, name, width, left, right, color))

    # Y tick labels
    if not bare:
        step = nice_tick_step(y_high - y_low, 5)
        v = math.ceil(y_low / step) * step
        while v <= y_high:
            body.append(_text(left - opts.tick_gap, y(v), str(_round_half_up(v)), size=opts.axis_size, fill="#7c8472", anchor="end", baseline="central", cls="sp-tick"))
            v += step

    # Profile geometry
    d_attr = " ".join(
        f'{"M" if i == 0 else "L"} {x(ds[i]):.2f} {y(elevations[i]):.2f}'
        for i in range(len(series.samples))
    )

    if opts.fill:
        area_d = f"{d_attr} L {x(x_max):.2f} {baseline_y:.2f} L {x(0):.2f} {baseline_y:.2f} Z"
        fill_ref = "url(#steepFill)" if opts.gradient_shading else "url(#accentFill)"
        fill_op = "0.92" if opts.gradient_shading else "1"
        body.append(f'<path class="sp-area" d="{area_d}" fill="{fill_ref}" fill-opacity="{fill_op}"/>')

    if opts.gradient_shading:
        stroke = "rgba(245,242,232,0.92)" if opts.fill else "url(#steepFill)"
    else:
        stroke = color
    stroke_w = opts.stroke_grad if (opts.gradient_shading and opts.fill) else opts.stroke_solid
    body.append(
        f'<path class="sp-line" d="{d_attr}" fill="none" stroke="{stroke}" '
        f'stroke-width="{_num(stroke_w)}" stroke-linejoin="round" stroke-linecap="round"/>'
    )

    # Baseline
    if not bare:
        body.append(
            f'<line class="sp-baseline" x1="{_num(left)}" x2="{_num(left + inner_w)}" '
            f'y1="{_num(baseline_y)}" y2="{_num(baseline_y)}" stroke="#2a3226" stroke-width="1"/>'
        )

    # X tick labels
    if not bare:
        x_max_km = x_max / 1000
        step_km = nice_tick_step(x_max_km, opts.x_ticks)
        kmt = 0.0
        while kmt <= x_max_km + 1e-9:
            body.append(_text(x(kmt * 1000), baseline_y + opts.x_tick_dy, _format_km_tick(kmt, step_km), size=opts.axis_size, fill="#7c8472", anchor="middle", cls="sp-tick"))
            kmt += step_km

    return (
        f'<svg xmlns="{_SVG_NS}" class="stage-profile" '
        f'viewBox="0 0 {width} {height}" width="{width}" height="{height}">'
        + "".join(body)
        + "</svg>"
    )
