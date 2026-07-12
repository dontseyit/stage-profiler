"""Tests for the stage_profiler profile + steepness. Run with `pytest` (PYTHONPATH=src)."""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET

import pytest

from stage_profiler import (
    Climb,
    RouteMetrics,
    Sample,
    Series,
    StageProfile,
    build_series,
    parse_gpx,
    prettify_name,
    steepness_bands,
)
from stage_profiler.render import HEIGHT, WIDTH
from stage_profiler.steepness import MIN_BAND_M
from stage_profiler.theme import BACKGROUND, BAND_COLORS

SIMPLE_GPX = """<?xml version="1.0" encoding="UTF-8"?>
<gpx version="1.1" xmlns="http://www.topografix.com/GPX/1/1">
  <trk><name>Alpe Test</name><trkseg>
    <trkpt lat="45.0000" lon="6.0000"><ele>1000</ele></trkpt>
    <trkpt lat="45.0010" lon="6.0000"><ele>1050</ele></trkpt>
    <trkpt lat="45.0020" lon="6.0000"><ele>1120</ele></trkpt>
    <trkpt lat="45.0030" lon="6.0000"><ele>1090</ele></trkpt>
  </trkseg></trk>
</gpx>
"""


def _series(dist_ele: "list[tuple[float, float]]") -> Series:
    """A synthetic Series from ``(distance_m, elevation_m)`` samples — precise for banding."""
    samples = [Sample(float(d), float(e)) for d, e in dist_ele]
    es = [e for _, e in dist_ele]
    return Series(samples, RouteMetrics(
        total_distance_m=dist_ele[-1][0], ascent_m=0.0, descent_m=0.0,
        min_ele_m=min(es), max_ele_m=max(es), max_gradient_pct=0.0,
    ))


def _ramp(pct: float, length_m: float = 4000.0, step: float = 250.0) -> "list[tuple[float, float]]":
    """A constant-gradient climb of ``pct``% over ``length_m``, sampled every ``step``."""
    n = int(length_m / step)
    return [(i * step, i * step * pct / 100.0) for i in range(n + 1)]


# --- parsing & metrics (gpx.py / geometry.py) ---------------------------------

def test_parse_gpx_reads_points_across_namespace():
    points = parse_gpx(SIMPLE_GPX)
    assert len(points) == 4
    assert points[0].lat == 45.0 and points[0].lon == 6.0
    assert points[2].ele == 1120


def test_parse_gpx_raises_on_bad_xml():
    with pytest.raises(ValueError):
        parse_gpx("<gpx><trkpt lat=")


def test_missing_elevation_is_carried_forward():
    series = build_series(parse_gpx(SIMPLE_GPX.replace("<ele>1050</ele>", "")))
    assert series.samples[1].elevation_m == 1000


def test_metrics_values():
    m = build_series(parse_gpx(SIMPLE_GPX)).metrics
    assert m.ascent_m == pytest.approx(120.0)
    assert m.descent_m == pytest.approx(30.0)
    assert m.min_ele_m == 1000 and m.max_ele_m == 1120
    assert 300 < m.total_distance_m < 360


def test_build_series_requires_two_points():
    with pytest.raises(ValueError):
        build_series(parse_gpx(SIMPLE_GPX)[:1])


# --- steepness bands ----------------------------------------------------------

def test_flat_route_is_all_gentle():
    bands = steepness_bands(_series([(0, 100), (5000, 100)]))
    assert bands and all(b.tier == 0 for b in bands)


def test_descent_is_gentle_not_steep():
    bands = steepness_bands(_series(_ramp(-10)))  # a 10% *descent*
    assert all(b.tier == 0 for b in bands)


def test_moderate_and_steep_tiers():
    assert max(b.tier for b in steepness_bands(_series(_ramp(6)))) == 1   # 6% → moderate
    assert max(b.tier for b in steepness_bands(_series(_ramp(11)))) == 2  # 11% → steep


def test_opacity_follows_tier():
    steep = [b for b in steepness_bands(_series(_ramp(12))) if b.tier == 2][0]
    assert steep.opacity == 1.0


def test_short_spike_is_absorbed_no_slivers():
    # A 250 m steep blip buried in 8 km of flat should not survive as its own band.
    route = [(0, 0), (4000, 0), (4250, 30), (8000, 30)]
    bands = steepness_bands(_series(route))
    assert all((b.d1 - b.d0) >= MIN_BAND_M for b in bands[1:-1])


# --- rendering ----------------------------------------------------------------

def _profile(**kw) -> str:
    return StageProfile.from_gpx(
        SIMPLE_GPX, start_town="Tirano", finish_town="Bormio",
        climbs=[Climb("Mortirolo", 0.15)], **kw,
    ).render()


def test_render_is_valid_svg_at_fixed_size():
    root = ET.fromstring(_profile())
    assert root.get("viewBox") == f"0 0 {WIDTH} {HEIGHT}"
    assert root.get("class") == "stage-profile"


def test_render_has_bands_line_and_markers():
    svg = _profile()
    assert 'class="sp-band"' in svg and any(c in svg for c in BAND_COLORS)
    assert 'class="sp-line"' in svg and "polyline" in svg
    assert 'class="sp-baseline"' in svg
    assert 'class="sp-finish"' in svg   # finish marker (the start has none)


def test_render_labels_towns_uppercase_climbs_letter_case():
    svg = _profile()
    assert "TIRANO" in svg and "BORMIO" in svg      # towns are uppercased
    assert "Mortirolo" in svg                        # climbs keep their letter case
    assert " M<" in svg or "M</text>" in svg         # elevation unit


def test_render_has_no_axes_or_header():
    svg = _profile()
    assert "sp-tick" not in svg and "STAGE PROFILE" not in svg  # no axes / header


def test_render_shows_finish_distance_only():
    svg = _profile()
    assert svg.count('class="sp-dist"') == 1   # finish km only; no start "0"
    assert "KM" in svg


def test_render_has_solid_background():
    svg = _profile()
    assert 'class="sp-bg"' in svg and BACKGROUND in svg


def test_low_relief_stage_stays_flat():
    # 50 m of relief must not be stretched to fill the plot (the floored span).
    svg = StageProfile.from_gpx(_ramp_gpx(50)).render()
    ys = [float(p.split(",")[1]) for p in re.search(r'class="sp-line" points="([^"]+)"', svg).group(1).split()]
    assert max(ys) - min(ys) < 40   # gentle, not mountainous


def test_name_is_prettified_and_labels_escaped():
    assert prettify_name("tirano-bormio") == "TIRANO BORMIO"
    svg = StageProfile.from_gpx(SIMPLE_GPX, start_town="A & B").render()
    assert "A &amp; B" in svg


def _ramp_gpx(relief_m: float) -> str:
    """A GPX rising ``relief_m`` over ~1 km — low relief to exercise the floored span."""
    return (
        '<gpx version="1.1" xmlns="http://www.topografix.com/GPX/1/1"><trk><trkseg>'
        '<trkpt lat="45.0000" lon="6.0000"><ele>0</ele></trkpt>'
        '<trkpt lat="45.0050" lon="6.0000"><ele>0</ele></trkpt>'
        f'<trkpt lat="45.0100" lon="6.0000"><ele>{relief_m}</ele></trkpt>'
        "</trkseg></trk></gpx>"
    )
