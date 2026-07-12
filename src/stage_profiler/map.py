"""The stage map — a country outline restyled to the roadbook look, marking start & finish.

One baked-in look, no options: the outline is simplified and drawn as soft land (a pale fill
with a thin cool stroke), the start is a hollow green ring, the finish a solid green dot, and
each carries its town name plus ``START`` / ``FINISH`` and the GPX elevation. No header.

Depends on **shapely** (outline simplification) and **pyproj** (Web Mercator projection).
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence, Union

from pyproj import Transformer
from shapely.geometry import LineString

from .profile import prettify_name
from .theme import ACCENT, BACKGROUND, INK, INK_MUTE, LAND_FILL, LAND_STROKE, PAPER, _num, _text

__all__ = ["StageMap", "Marker", "render_map_svg", "WIDTH", "HEIGHT"]

GeoJSONLike = Union[dict, str]
LonLat = Sequence[float]

_SVG_NS = "http://www.w3.org/2000/svg"

# Canvas & framing (fixed).
WIDTH, HEIGHT = 460, 220
PADDING = 20.0        # inset between the country and the frame
SIMPLIFY_TOL = 1.4    # Douglas-Peucker tolerance (px) — soft, cute outline
SMOOTHING = 0.5       # centripetal Catmull-Rom
PIN_R = 5.0
_LABEL_SPLIT_PX = 34.0

_TO_MERCATOR = Transformer.from_crs("EPSG:4326", "EPSG:3857", always_xy=True)
_NAME_KEYS = ("shapeName", "name", "NAME", "ADMIN", "admin", "NAME_EN", "country")


@dataclass(frozen=True)
class Marker:
    """A labelled point. ``icon`` is ``"start"`` (hollow ring) or ``"finish"`` (solid dot)."""

    lon: float
    lat: float
    label: str = ""
    icon: str = "start"
    ele: "float | None" = None


# ── GeoJSON loading ──────────────────────────────────────────────────────────

def _load_geojson(geojson: GeoJSONLike) -> dict:
    if isinstance(geojson, dict):
        return geojson
    if isinstance(geojson, str):
        if os.path.exists(geojson):
            with open(geojson, encoding="utf-8") as fh:
                return json.load(fh)
        return json.loads(geojson)
    raise TypeError("geojson must be a dict, JSON string, or file path")


def _rings(geojson: dict) -> "list[list[LonLat]]":
    """Flatten every (Multi)Polygon ring into a list of ``[(lon, lat), ...]``."""
    if geojson.get("type") == "FeatureCollection":
        geometries = [f["geometry"] for f in geojson["features"]]
    elif geojson.get("type") == "Feature":
        geometries = [geojson["geometry"]]
    else:
        geometries = [geojson]

    rings: "list[list[LonLat]]" = []
    for geom in geometries:
        if geom is None:
            continue
        if geom["type"] == "MultiPolygon":
            polygons = geom["coordinates"]
        elif geom["type"] == "Polygon":
            polygons = [geom["coordinates"]]
        else:
            continue
        for polygon in polygons:
            rings.extend(polygon)
    return rings


def _name_from_geojson(data: dict) -> "str | None":
    features = data.get("features") if isinstance(data, dict) else None
    for feature in (features or [data]):
        props = (feature or {}).get("properties") or {}
        for key in _NAME_KEYS:
            value = props.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    return None


# ── Projection & framing ─────────────────────────────────────────────────────

class _Frame:
    """Projects (lon, lat) to pixel space, fitting the country into the frame.

    Works from projected vertices (never spherical winding) so inconsistently wound GeoJSON
    frames correctly instead of collapsing to a dot.
    """

    def __init__(self, rings: "list[list[LonLat]]", box_w: float, box_h: float, padding: float):
        xs: "list[float]" = []
        ys: "list[float]" = []
        for ring in rings:
            for lon, lat in ring:
                mx, my = _TO_MERCATOR.transform(lon, lat)
                xs.append(mx)
                ys.append(my)
        if not xs:
            raise ValueError("GeoJSON contains no polygon geometry")

        self._minx, self._maxx = min(xs), max(xs)
        self._miny, self._maxy = min(ys), max(ys)
        span_x = (self._maxx - self._minx) or 1.0
        span_y = (self._maxy - self._miny) or 1.0
        self._scale = min((box_w - 2 * padding) / span_x, (box_h - 2 * padding) / span_y)
        self._ox = (box_w - span_x * self._scale) / 2
        self._oy = (box_h - span_y * self._scale) / 2

    def __call__(self, lon: float, lat: float) -> "tuple[float, float]":
        mx, my = _TO_MERCATOR.transform(lon, lat)
        px = self._ox + (mx - self._minx) * self._scale
        py = self._oy + (self._maxy - my) * self._scale  # flip Y for SVG
        return px, py


def _catmull_rom_closed(points: "list[tuple[float, float]]", alpha: float) -> str:
    """Closed centripetal Catmull-Rom spline as an SVG cubic-Bézier subpath."""
    n = len(points)
    if n < 3:
        return ""

    def knot(t, a, b):
        d = ((b[0] - a[0]) ** 2 + (b[1] - a[1]) ** 2) ** 0.5
        return t + (d ** alpha or 1e-9)

    d = f"M{points[0][0]:.2f},{points[0][1]:.2f}"
    for i in range(n):
        p0, p1, p2, p3 = points[(i - 1) % n], points[i], points[(i + 1) % n], points[(i + 2) % n]
        t0 = 0.0
        t1 = knot(t0, p0, p1)
        t2 = knot(t1, p1, p2)
        t3 = knot(t2, p2, p3)
        m1x = ((p2[0] - p1[0]) / (t2 - t1) - (p2[0] - p0[0]) / (t2 - t0) + (p1[0] - p0[0]) / (t1 - t0)) * (t2 - t1)
        m1y = ((p2[1] - p1[1]) / (t2 - t1) - (p2[1] - p0[1]) / (t2 - t0) + (p1[1] - p0[1]) / (t1 - t0)) * (t2 - t1)
        m2x = ((p2[0] - p1[0]) / (t2 - t1) - (p3[0] - p1[0]) / (t3 - t1) + (p3[0] - p2[0]) / (t3 - t2)) * (t2 - t1)
        m2y = ((p2[1] - p1[1]) / (t2 - t1) - (p3[1] - p1[1]) / (t3 - t1) + (p3[1] - p2[1]) / (t3 - t2)) * (t2 - t1)
        c1x, c1y = p1[0] + m1x / 3, p1[1] + m1y / 3
        c2x, c2y = p2[0] - m2x / 3, p2[1] - m2y / 3
        d += f"C{c1x:.2f},{c1y:.2f} {c2x:.2f},{c2y:.2f} {p2[0]:.2f},{p2[1]:.2f}"
    return d + "Z"


# ── Markers ───────────────────────────────────────────────────────────────────

def _pin(px: float, py: float, marker: Marker, place: str) -> str:
    """A start (hollow ring) or finish (solid dot) pin plus its town + elevation labels.

    ``place`` positions the two-line label: ``"straddle"`` (name above the pin, elevation
    below — the roomy default), or a stacked ``"above"`` / ``"below"`` block used when the two
    pins sit close enough that straddling would overprint.
    """
    parts = ['<g class="sm-marker">']
    if marker.icon == "finish":
        parts.append(f'<circle cx="{px:.2f}" cy="{py:.2f}" r="{_num(PIN_R)}" fill="{ACCENT}"/>')
        kind = "FINISH"
    else:
        parts.append(f'<circle cx="{px:.2f}" cy="{py:.2f}" r="{_num(PIN_R)}" '
                     f'fill="{PAPER}" stroke="{ACCENT}" stroke-width="2.5"/>')
        kind = "START"

    if marker.label:
        right = px < WIDTH * 0.72
        lx = px + 10 if right else px - 10
        anchor = "start" if right else "end"
        if place == "above":
            name_y, sub_y = py - 16, py - 5
        elif place == "below":
            name_y, sub_y = py + 14, py + 25
        else:  # straddle
            name_y, sub_y = py - 3, py + 10
        sub = kind if marker.ele is None else f"{kind} · {round(marker.ele):,}M"
        parts.append(_text(lx, name_y, marker.label.upper(), size=12, weight=700, fill=INK, anchor=anchor, cls="sm-label"))
        parts.append(_text(lx, sub_y, sub, size=9, weight=500, fill=INK_MUTE, anchor=anchor, cls="sm-sub"))
    parts.append("</g>")
    return "".join(parts)


# ── Public API ────────────────────────────────────────────────────────────────

@dataclass
class StageMap:
    """A parsed country outline plus its start/finish markers and name."""

    rings: "list[list[LonLat]]"
    start: Marker
    end: Marker
    name: str = "ROUTE"

    @classmethod
    def from_geojson(
        cls,
        geojson: GeoJSONLike,
        *,
        start: LonLat,
        end: LonLat,
        start_label: str = "",
        end_label: str = "",
        start_ele: "float | None" = None,
        finish_ele: "float | None" = None,
        name: "str | None" = None,
    ) -> "StageMap":
        """Build from GeoJSON (dict, JSON string, or path). ``start`` / ``end`` are ``(lon, lat)``."""
        data = _load_geojson(geojson)
        if name is None:
            name = _name_from_geojson(data) or "route"
        return cls(
            rings=_rings(data),
            start=Marker(start[0], start[1], start_label, "start", start_ele),
            end=Marker(end[0], end[1], end_label, "finish", finish_ele),
            name=prettify_name(name),
        )

    @classmethod
    def from_file(
        cls,
        path: "str | Path",
        *,
        start: LonLat,
        end: LonLat,
        start_label: str = "",
        end_label: str = "",
        start_ele: "float | None" = None,
        finish_ele: "float | None" = None,
        name: "str | None" = None,
    ) -> "StageMap":
        """Build from a ``.geojson`` file."""
        data = _load_geojson(str(path))
        if name is None:
            name = _name_from_geojson(data) or Path(path).stem
        return cls.from_geojson(
            data, start=start, end=end, start_label=start_label, end_label=end_label,
            start_ele=start_ele, finish_ele=finish_ele, name=name,
        )

    def render(self) -> str:
        """Render the stage-map SVG string."""
        return render_map_svg(self.rings, self.start, self.end, self.name)


def render_map_svg(
    rings: "list[list[LonLat]]",
    start: Marker,
    end: Marker,
    name: str = "ROUTE",
) -> str:
    """Render ``rings`` (flattened polygon rings) to a self-contained stage-map SVG string."""
    frame = _Frame(rings, WIDTH, HEIGHT, PADDING)

    path = ""
    for ring in rings:
        pts = [frame(lon, lat) for lon, lat in ring]
        if len(pts) > 1 and pts[0] == pts[-1]:
            pts = pts[:-1]
        if len(pts) >= 3:
            simplified = list(LineString(pts).simplify(SIMPLIFY_TOL, preserve_topology=False).coords)
            if simplified and simplified[0] == simplified[-1]:
                simplified = simplified[:-1]
            if len(simplified) >= 3:
                path += _catmull_rom_closed(simplified, SMOOTHING)

    body = [
        f'<rect class="sm-bg" width="{WIDTH}" height="{HEIGHT}" fill="{BACKGROUND}"/>',
        f'<path class="sm-land" d="{path}" fill="{LAND_FILL}" fill-rule="evenodd" '
        f'stroke="{LAND_STROKE}" stroke-width="1.2" stroke-linejoin="round" '
        f'stroke-linecap="round"/>'
    ]

    sx, sy = frame(start.lon, start.lat)
    ex, ey = frame(end.lon, end.lat)
    # When the two pins sit close (a short stage on a big country), straddled labels would
    # overprint — stack the upper pin's label above it and the lower pin's below it instead.
    if ((ex - sx) ** 2 + (ey - sy) ** 2) ** 0.5 < _LABEL_SPLIT_PX:
        s_place, e_place = ("above", "below") if sy <= ey else ("below", "above")
    else:
        s_place = e_place = "straddle"
    body.append(_pin(sx, sy, start, s_place))
    body.append(_pin(ex, ey, end, e_place))

    return (
        f'<svg xmlns="{_SVG_NS}" class="stage-map" viewBox="0 0 {WIDTH} {HEIGHT}" '
        f'width="{WIDTH}" height="{HEIGHT}">' + "".join(body) + "</svg>"
    )
