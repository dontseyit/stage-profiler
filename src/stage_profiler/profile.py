"""High-level profile entry point — parse a GPX, attach roadbook labels, render the SVG."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from .geometry import RouteMetrics, Series, build_series, clip_series
from .gpx import extract_name, parse_gpx
from .render import render_profile_svg

__all__ = ["StageProfile", "Climb", "prettify_name"]


def prettify_name(name: str) -> str:
    """Turn a filename/slug into a display title, e.g. ``tirano-bormio`` → ``TIRANO BORMIO``."""
    pretty = re.sub(r"\s+", " ", re.sub(r"[-_]+", " ", name)).strip().upper()
    return pretty or "ROUTE"


CLIMB_CATEGORIES = ("HC", "1", "2", "3", "4", "")


@dataclass(frozen=True)
class Climb:
    """A named climb labelled over its summit. ``km`` is the summit's distance along the
    route; ``category`` is the UCI climb category (``"HC"``, ``"1"``…``"4"``), drawn as the
    summit badge, or ``""`` for an uncategorised climb."""

    name: str
    km: float
    category: str = ""

    def __post_init__(self) -> None:
        if self.category not in CLIMB_CATEGORIES:
            raise ValueError(
                f"climb category must be one of 'HC', '1'…'4' or '', got {self.category!r}"
            )


@dataclass
class StageProfile:
    """A parsed route plus the roadbook labels the design places on it.

    The profile shows no title of its own — the ``start_town`` / ``finish_town`` (with their
    GPX elevations), the ``climbs`` and the ``sprints`` (intermediate-sprint km) are the only
    marks on the chart. ``accent`` is the race colour tinting the silhouette (empty for the
    default). ``name`` is kept for filenames and reporting.

    To draw a stage shorter than its GPX (a neutral start zone or GPS overrun), pass
    ``length_km`` to :meth:`from_file` / :meth:`from_gpx`: the route is clipped there and that
    point becomes the finish, with metrics recomputed for the shortened stage.
    """

    series: Series
    name: str = "ROUTE"
    start_town: str = ""
    finish_town: str = ""
    climbs: "tuple[Climb, ...]" = ()
    sprints: "tuple[float, ...]" = ()
    accent: str = ""

    @classmethod
    def from_gpx(
        cls,
        text: str,
        *,
        name: "str | None" = None,
        start_town: str = "",
        finish_town: str = "",
        climbs: "Iterable[Climb]" = (),
        sprints: "Iterable[float]" = (),
        accent: str = "",
        length_km: "float | None" = None,
    ) -> "StageProfile":
        """Build from GPX XML text. ``length_km`` clips the route to that distance (the
        drawn finish), when the stage is shorter than the recorded GPX."""
        if name is None:
            name = extract_name(text) or "route"
        series = build_series(parse_gpx(text))
        if length_km is not None:
            series = clip_series(series, length_km * 1000.0)
        return cls(
            series=series,
            name=prettify_name(name),
            start_town=start_town,
            finish_town=finish_town,
            climbs=tuple(climbs),
            sprints=tuple(float(km) for km in sprints),
            accent=accent,
        )

    @classmethod
    def from_file(
        cls,
        path: "str | Path",
        *,
        name: "str | None" = None,
        start_town: str = "",
        finish_town: str = "",
        climbs: "Iterable[Climb]" = (),
        sprints: "Iterable[float]" = (),
        accent: str = "",
        length_km: "float | None" = None,
    ) -> "StageProfile":
        """Build from a ``.gpx`` file. Title falls back to the ``<name>`` tag, then the filename."""
        p = Path(path)
        text = p.read_text(encoding="utf-8")
        if name is None:
            name = extract_name(text) or p.stem
        return cls.from_gpx(
            text, name=name, start_town=start_town, finish_town=finish_town,
            climbs=climbs, sprints=sprints, accent=accent, length_km=length_km,
        )

    @property
    def metrics(self) -> RouteMetrics:
        return self.series.metrics

    @property
    def start_ele(self) -> float:
        return self.series.samples[0].elevation_m

    @property
    def finish_ele(self) -> float:
        return self.series.samples[-1].elevation_m

    def render(self) -> str:
        """Render the stage-profile SVG string."""
        return render_profile_svg(
            self.series,
            start_town=self.start_town,
            finish_town=self.finish_town,
            climbs=[(c.name, c.km, c.category) for c in self.climbs],
            sprints=self.sprints,
            accent=self.accent,
        )
