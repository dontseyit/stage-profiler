"""High-level profile entry point — parse a GPX, attach roadbook labels, render the SVG."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from .geometry import RouteMetrics, Series, build_series
from .gpx import extract_name, parse_gpx
from .render import render_profile_svg

__all__ = ["StageProfile", "Climb", "prettify_name"]


def prettify_name(name: str) -> str:
    """Turn a filename/slug into a display title, e.g. ``tirano-bormio`` → ``TIRANO BORMIO``."""
    pretty = re.sub(r"\s+", " ", re.sub(r"[-_]+", " ", name)).strip().upper()
    return pretty or "ROUTE"


@dataclass(frozen=True)
class Climb:
    """A named climb labelled over its summit. ``km`` is the summit's distance along the route."""

    name: str
    km: float


@dataclass
class StageProfile:
    """A parsed route plus the roadbook labels the design places on it.

    The profile shows no title of its own — the ``start_town`` / ``finish_town`` (with their
    GPX elevations) and the ``climbs`` are the only text on the chart. ``name`` is kept for
    filenames and reporting.
    """

    series: Series
    name: str = "ROUTE"
    start_town: str = ""
    finish_town: str = ""
    climbs: "tuple[Climb, ...]" = ()

    @classmethod
    def from_gpx(
        cls,
        text: str,
        *,
        name: "str | None" = None,
        start_town: str = "",
        finish_town: str = "",
        climbs: "Iterable[Climb]" = (),
    ) -> "StageProfile":
        """Build from GPX XML text."""
        if name is None:
            name = extract_name(text) or "route"
        return cls(
            series=build_series(parse_gpx(text)),
            name=prettify_name(name),
            start_town=start_town,
            finish_town=finish_town,
            climbs=tuple(climbs),
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
    ) -> "StageProfile":
        """Build from a ``.gpx`` file. Title falls back to the ``<name>`` tag, then the filename."""
        p = Path(path)
        text = p.read_text(encoding="utf-8")
        if name is None:
            name = extract_name(text) or p.stem
        return cls.from_gpx(
            text, name=name, start_town=start_town, finish_town=finish_town, climbs=climbs,
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
            climbs=[(c.name, c.km) for c in self.climbs],
        )
