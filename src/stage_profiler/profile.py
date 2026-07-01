"""High-level entry point tying parsing, metrics, and rendering together."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from .geometry import RouteMetrics, Series, build_series
from .gpx import extract_name, parse_gpx
from .render import RenderOptions, render_svg

__all__ = ["StageProfile", "prettify_name"]


def prettify_name(name: str) -> str:
    """Turn a filename/slug into a display title, e.g. ``stage-1_alpe`` → ``STAGE 1 ALPE``."""
    pretty = re.sub(r"\s+", " ", re.sub(r"[-_]+", " ", name)).strip().upper()
    return pretty or "ROUTE"


@dataclass
class StageProfile:
    """A parsed route: its :class:`~stage_profiler.geometry.Series`, metrics, and name."""

    series: Series
    name: str = "ROUTE"

    @classmethod
    def from_gpx(cls, text: str, *, name: "str | None" = None) -> "StageProfile":
        """Build from GPX XML text. ``name`` overrides the auto-detected title."""
        if name is None:
            name = extract_name(text) or "route"
        return cls(series=build_series(parse_gpx(text)), name=prettify_name(name))

    @classmethod
    def from_file(cls, path: "str | Path", *, name: "str | None" = None) -> "StageProfile":
        """Build from a ``.gpx`` file. Title falls back to the ``<name>`` tag, then the filename."""
        p = Path(path)
        text = p.read_text(encoding="utf-8")
        if name is None:
            name = extract_name(text) or p.stem
        return cls.from_gpx(text, name=name)

    @property
    def metrics(self) -> RouteMetrics:
        return self.series.metrics

    def render(self, options: "RenderOptions | None" = None, **kwargs: object) -> str:
        """Render to an SVG string. Pass either ``options=RenderOptions(...)`` or keyword
        overrides (``color=``, ``width=``, ``header=``, ``bare=``, …)."""
        if options is None:
            options = RenderOptions(**kwargs)  # type: ignore[arg-type]
        elif kwargs:
            raise TypeError("Pass either `options` or keyword overrides, not both.")
        return render_svg(self.series, self.name, options)
