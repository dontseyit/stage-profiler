"""Segment a route into steepness bands — the single green at three opacities.

Each band is a contiguous stretch of route classified by its *sustained* uphill gradient
into one of three tiers (gentle/flat/descent · moderate · steep). The renderer paints each
band as a full-height rectangle of the accent green, clipped to the silhouette under the
elevation line, at the tier's :data:`~stage_profiler.theme.BAND_OPACITY`.

Two things keep the bands reading as clean blocks (like the design) rather than a picket
fence of slivers: the tier is decided from a gradient measured over a wide sustained
:data:`WINDOW_M` (so a single roller or GPS spike can't flip it), and any band narrower than
:data:`MIN_BAND_M` is absorbed into its dominant neighbour.

The two gradient cut points are the only tunable numbers in the look.
"""

from __future__ import annotations

from dataclasses import dataclass

from .geometry import Series, slope_at
from .theme import BAND_OPACITY

__all__ = ["Band", "steepness_bands", "GENTLE_MAX_PCT", "STEEP_MIN_PCT"]

GENTLE_MAX_PCT = 4.0   # below this (including flat and every descent) → tier 0
STEEP_MIN_PCT = 8.0    # at or above this → tier 2; in between → tier 1

SEGMENT_M = 250.0      # band-boundary resolution
WINDOW_M = 600.0       # sustained-gradient window a tier is decided over
MIN_BAND_M = 1000.0    # bands narrower than this are absorbed into a neighbour


@dataclass(frozen=True)
class Band:
    """A contiguous stretch ``[d0, d1)`` (metres) at one steepness ``tier`` (0/1/2)."""

    d0: float
    d1: float
    tier: int

    @property
    def opacity(self) -> float:
        return BAND_OPACITY[self.tier]


def _tier(pct: float) -> int:
    if pct < GENTLE_MAX_PCT:
        return 0
    if pct < STEEP_MIN_PCT:
        return 1
    return 2


def _merge(spans: "list[list[float]]") -> "list[list[float]]":
    """Combine consecutive same-tier spans (each ``[d0, d1, tier]``)."""
    out: "list[list[float]]" = []
    for d0, d1, tier in spans:
        if out and out[-1][2] == tier:
            out[-1][1] = d1
        else:
            out.append([d0, d1, tier])
    return out


def _absorb(spans: "list[list[float]]", min_band_m: float) -> "list[list[float]]":
    """Fold any span narrower than ``min_band_m`` into its longer neighbour, until none remain."""
    while len(spans) > 1:
        i = min(range(len(spans)), key=lambda k: spans[k][1] - spans[k][0])
        if spans[i][1] - spans[i][0] >= min_band_m:
            break
        left = spans[i - 1] if i > 0 else None
        right = spans[i + 1] if i < len(spans) - 1 else None
        if left and right:
            donor = left if (left[1] - left[0]) >= (right[1] - right[0]) else right
        else:
            donor = left or right
        spans[i][2] = donor[2]  # type: ignore[index]
        spans = _merge(spans)
    return spans


def steepness_bands(
    series: Series,
    *,
    segment_m: float = SEGMENT_M,
    window_m: float = WINDOW_M,
    min_band_m: float = MIN_BAND_M,
) -> "list[Band]":
    """Classify ``series`` into merged, sliver-free steepness bands, start to finish."""
    total = series.metrics.total_distance_m
    if total <= 0:
        return []

    ds = [s.distance_m for s in series.samples]
    es = [s.elevation_m for s in series.samples]

    spans: "list[list[float]]" = []
    d = 0.0
    while d < total - 1e-6:
        end = min(d + segment_m, total)
        mid = (d + end) / 2
        grad = slope_at(ds, es, max(0.0, mid - window_m / 2), min(total, mid + window_m / 2))
        spans.append([d, end, float(_tier(grad))])
        d = end

    spans = _absorb(_merge(spans), min_band_m)
    return [Band(d0, d1, int(tier)) for d0, d1, tier in spans]
