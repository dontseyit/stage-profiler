"""GPX parsing — namespace-agnostic, stdlib only.

Prefer ``<trkpt>``, fall back to ``<rtept>`` then ``<wpt>``; keep points with valid
coordinates; a missing ``<ele>`` is left as ``None`` (elevation is carried forward
later in :mod:`stage_profiler.geometry`).
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import dataclass

__all__ = ["Point", "parse_gpx", "extract_name"]


@dataclass(frozen=True)
class Point:
    """A single GPX point. ``ele`` is ``None`` when the source omitted elevation."""

    lat: float
    lon: float
    ele: "float | None" = None


def _local(tag: str) -> str:
    """Strip any ``{namespace}`` prefix so GPX 1.0/1.1 parse identically."""
    return tag.rsplit("}", 1)[-1]


def _root(text: str) -> ET.Element:
    try:
        return ET.fromstring(text)
    except ET.ParseError as exc:  # pragma: no cover - message passthrough
        raise ValueError(f"Invalid GPX (XML parse error): {exc}") from exc


def parse_gpx(text: str) -> "list[Point]":
    """Parse GPX XML text into a list of :class:`Point`.

    Raises :class:`ValueError` if the XML is malformed.
    """
    root = _root(text)

    buckets: "dict[str, list[ET.Element]]" = {"trkpt": [], "rtept": [], "wpt": []}
    for el in root.iter():
        name = _local(el.tag)
        if name in buckets:
            buckets[name].append(el)

    candidates = buckets["trkpt"] or buckets["rtept"] or buckets["wpt"]

    points: "list[Point]" = []
    for el in candidates:
        try:
            lat = float(el.get("lat"))  # type: ignore[arg-type]
            lon = float(el.get("lon"))  # type: ignore[arg-type]
        except (TypeError, ValueError):
            continue
        ele: "float | None" = None
        for child in el:
            if _local(child.tag) == "ele":
                try:
                    ele = float((child.text or "").strip())
                except ValueError:
                    ele = None
                break
        points.append(Point(lat, lon, ele))
    return points


def extract_name(text: str) -> "str | None":
    """Return the first ``<name>`` found (metadata or track), or ``None``."""
    try:
        root = _root(text)
    except ValueError:
        return None
    for el in root.iter():
        if _local(el.tag) == "name" and el.text and el.text.strip():
            return el.text.strip()
    return None
