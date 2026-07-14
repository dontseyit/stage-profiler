"""Stage Profiler — a roadbook toolkit that turns a route into a stage-profile SVG and a
country outline into a stage-map SVG, sharing one baked-in design language.

Quick start::

    from stage_profiler import StageProfile, Climb, StageMap

    profile = StageProfile.from_file(
        "stage.gpx",
        start_town="Tirano", finish_town="Bormio",
        climbs=[Climb("Mortirolo", 55), Climb("Foscagno", 140)],
    )
    svg = profile.render()

    smap = StageMap.from_file(
        "ita.geojson",
        start=(10.17, 46.22), end=(10.37, 46.47),
        start_label="Tirano", end_label="Bormio",
        start_ele=profile.start_ele, finish_ele=profile.finish_ele,
    )
    map_svg = smap.render()

There are no render options — the look is fixed (see :mod:`stage_profiler.theme`). The profile
side is stdlib-only; the map (:class:`StageMap`) additionally requires shapely and pyproj.
"""

from __future__ import annotations

from .geometry import (
    RouteMetrics,
    Sample,
    Series,
    build_series,
    clip_series,
    ele_at,
    haversine_m,
    slope_at,
)
from .gpx import Point, extract_name, parse_gpx
from .map import Marker, StageMap, render_map_svg
from .profile import Climb, StageProfile, prettify_name
from .render import render_profile_svg
from .roadbook import MapSpec, RaceSpec, generate, load_manifest, render_race
from .steepness import Band, steepness_bands

__version__ = "0.2.0"

__all__ = [
    "StageProfile",
    "Climb",
    "prettify_name",
    "StageMap",
    "Marker",
    "generate",
    "load_manifest",
    "render_race",
    "RaceSpec",
    "MapSpec",
    "render_profile_svg",
    "render_map_svg",
    "steepness_bands",
    "Band",
    "parse_gpx",
    "extract_name",
    "Point",
    "build_series",
    "clip_series",
    "ele_at",
    "slope_at",
    "haversine_m",
    "Sample",
    "Series",
    "RouteMetrics",
    "__version__",
]
