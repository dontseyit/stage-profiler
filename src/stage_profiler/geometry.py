"""Distance, elevation metrics, and the sampled series — pure math, stdlib only."""

from __future__ import annotations

import bisect
import math
from dataclasses import asdict, dataclass

from .gpx import Point

__all__ = [
    "Sample",
    "RouteMetrics",
    "Series",
    "haversine_m",
    "build_series",
    "moving_average",
    "nice_tick_step",
]


@dataclass(frozen=True)
class Sample:
    """One point on the profile: cumulative ``distance_m`` and ``elevation_m``."""

    distance_m: float
    elevation_m: float


@dataclass(frozen=True)
class RouteMetrics:
    """Summary numbers for a route — the values a platform will want to store."""

    total_distance_m: float
    ascent_m: float
    descent_m: float
    min_ele_m: float
    max_ele_m: float
    max_gradient_pct: float

    @property
    def total_distance_km(self) -> float:
        return self.total_distance_m / 1000.0

    def to_dict(self) -> "dict[str, float]":
        data = asdict(self)
        data["total_distance_km"] = self.total_distance_km
        return data


@dataclass(frozen=True)
class Series:
    """Sampled profile plus its :class:`RouteMetrics`."""

    samples: "list[Sample]"
    metrics: RouteMetrics


def haversine_m(a: Point, b: Point) -> float:
    """Great-circle distance between two points, in metres."""
    radius = 6_371_000.0
    d_lat = math.radians(b.lat - a.lat)
    d_lon = math.radians(b.lon - a.lon)
    lat1 = math.radians(a.lat)
    lat2 = math.radians(b.lat)
    h = math.sin(d_lat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(d_lon / 2) ** 2
    return 2 * radius * math.asin(math.sqrt(h))


def build_series(points: "list[Point]") -> Series:
    """Turn raw GPX points into a distance/elevation series and its metrics.

    Missing elevations are carried forward from the last known value (starting at 0).
    Raises :class:`ValueError` for fewer than two points.
    """
    if len(points) < 2:
        raise ValueError("GPX route has fewer than two track points.")

    # Carry missing elevations forward.
    elevations: "list[float]" = []
    last = 0.0
    for p in points:
        if p.ele is None:
            elevations.append(last)
        else:
            last = p.ele
            elevations.append(p.ele)

    cumulative = 0.0
    ascent = 0.0
    descent = 0.0
    min_ele = math.inf
    max_ele = -math.inf
    samples: "list[Sample]" = []

    for i in range(len(points)):
        ele = elevations[i]
        if i > 0:
            cumulative += haversine_m(points[i - 1], points[i])
            d_ele = elevations[i] - elevations[i - 1]
            if d_ele > 0:
                ascent += d_ele
            else:
                descent += -d_ele
        min_ele = min(min_ele, ele)
        max_ele = max(max_ele, ele)
        samples.append(Sample(cumulative, ele))

    metrics = RouteMetrics(
        total_distance_m=cumulative,
        ascent_m=ascent,
        descent_m=descent,
        min_ele_m=min_ele,
        max_ele_m=max_ele,
        max_gradient_pct=_max_sustained_gradient(samples),
    )
    return Series(samples=samples, metrics=metrics)


def _max_sustained_gradient(samples: "list[Sample]", window_m: float = 100.0) -> float:
    """Max gradient over a ~``window_m`` rolling window (tames GPS spikes)."""
    n = len(samples)
    j = 0
    max_grad = 0.0
    for i in range(n):
        if j < i:
            j = i
        while j < n - 1 and samples[j].distance_m - samples[i].distance_m < window_m:
            j += 1
        dd = samples[j].distance_m - samples[i].distance_m
        if dd >= window_m * 0.6:
            g = ((samples[j].elevation_m - samples[i].elevation_m) / dd) * 100.0
            if g > max_grad:
                max_grad = g
    return max_grad


def moving_average(values: "list[float]", radius: int) -> "list[float]":
    """Sliding-window mean; ``radius`` in points. ``radius <= 0`` returns a copy."""
    r = round(radius)
    if r <= 0 or not values:
        return list(values)
    n = len(values)
    out = [0.0] * n
    for i in range(n):
        lo = max(0, i - r)
        hi = min(n - 1, i + r)
        out[i] = sum(values[lo : hi + 1]) / (hi - lo + 1)
    return out


def nice_tick_step(value_range: float, target_ticks: int) -> float:
    """A human-friendly tick step (1/2/5 × 10ⁿ) near ``value_range / target_ticks``."""
    rough = value_range / target_ticks if target_ticks else value_range
    if rough <= 0:
        return 1.0
    pow10 = 10 ** math.floor(math.log10(rough))
    norm = rough / pow10
    if norm < 1.5:
        step = 1
    elif norm < 3:
        step = 2
    elif norm < 7:
        step = 5
    else:
        step = 10
    return step * pow10


# --- interpolation helpers used by the steepness gradient ---------------------

def ele_at(ds: "list[float]", es: "list[float]", d: float) -> float:
    """Linear-interpolated elevation at distance ``d`` along sorted ``ds``."""
    if d <= ds[0]:
        return es[0]
    if d >= ds[-1]:
        return es[-1]
    hi = bisect.bisect_left(ds, d)
    lo = hi - 1
    span = (ds[hi] - ds[lo]) or 1.0
    t = (d - ds[lo]) / span
    return es[lo] + (es[hi] - es[lo]) * t


def slope_at(ds: "list[float]", es: "list[float]", d0: float, d1: float) -> float:
    """Average slope (percent) between distances ``d0`` and ``d1``."""
    e0 = ele_at(ds, es, d0)
    e1 = ele_at(ds, es, d1)
    return ((e1 - e0) / max(d1 - d0, 1e-6)) * 100.0
