"""Stage Profiler — turn a GPX route into a stage-profile SVG plus route metrics.

Quick start::

    from stage_profiler import StageProfile, RenderOptions

    profile = StageProfile.from_file("route.gpx")
    print(profile.metrics.to_dict())

    svg = profile.render(RenderOptions(width=320, height=240, header="minimal"))
    line_only = profile.render(bare=True, fill=False)   # keyword overrides also work

Everything is configured through :class:`RenderOptions` — there are no built-in presets.
Zero runtime dependencies (stdlib only).
"""

from __future__ import annotations

from .geometry import (
    RouteMetrics,
    Sample,
    Series,
    build_series,
    haversine_m,
    moving_average,
    nice_tick_step,
)
from .gpx import Point, extract_name, parse_gpx
from .profile import StageProfile, prettify_name
from .ramp import RAMP, grad_color
from .render import CHART_BG, DEFAULT_COLOR, RenderOptions, auto_y_range, render_svg

__version__ = "0.1.0"

__all__ = [
    "StageProfile",
    "prettify_name",
    "parse_gpx",
    "extract_name",
    "Point",
    "build_series",
    "haversine_m",
    "moving_average",
    "nice_tick_step",
    "Sample",
    "Series",
    "RouteMetrics",
    "render_svg",
    "RenderOptions",
    "auto_y_range",
    "DEFAULT_COLOR",
    "CHART_BG",
    "RAMP",
    "grad_color",
    "__version__",
]
