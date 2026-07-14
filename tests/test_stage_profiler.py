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
    clip_series,
    parse_gpx,
    prettify_name,
    steepness_bands,
)
from stage_profiler.render import HEIGHT, WIDTH
from stage_profiler.steepness import MIN_BAND_M
from stage_profiler.theme import ACCENT, BACKGROUND

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


# --- clip_series (shorten a route from the end) -------------------------------

def test_clip_series_truncates_and_recomputes_metrics():
    s = _series([(0, 0), (1000, 100), (2000, 200), (3000, 150)])
    c = clip_series(s, 1500)
    assert c.metrics.total_distance_m == 1500
    assert c.samples[-1].distance_m == 1500
    assert c.samples[-1].elevation_m == pytest.approx(150)  # interpolated at 1500 m
    assert c.metrics.max_ele_m == 150            # the 200 m peak beyond 1500 m is cut
    assert c.metrics.ascent_m == pytest.approx(150)


def test_clip_series_is_noop_at_or_beyond_route_length():
    s = _series([(0, 0), (1000, 100), (2000, 200)])
    assert clip_series(s, 2000) is s
    assert clip_series(s, 9999) is s


def test_clip_series_rejects_nonpositive_length():
    s = _series([(0, 0), (1000, 100)])
    with pytest.raises(ValueError):
        clip_series(s, 0)


def test_length_km_clips_profile_metrics_and_drawn_finish():
    full = StageProfile.from_gpx(SIMPLE_GPX).metrics.total_distance_km
    p = StageProfile.from_gpx(SIMPLE_GPX, finish_town="Bormio", length_km=0.2)
    assert p.metrics.total_distance_km == pytest.approx(0.2)
    assert p.metrics.total_distance_km < full
    assert "0.2 KM" in p.render()   # the finish marker reflects the clipped length


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
    assert (WIDTH, HEIGHT) == (640, 192)   # the canvas is a fixed 10:3 banner by design


def test_render_has_silhouette_line_and_markers():
    svg = _profile()
    assert 'class="sp-fill"' in svg and ACCENT in svg   # accent-tinted silhouette
    assert 'class="sp-line"' in svg and "polyline" in svg
    assert 'class="sp-baseline"' in svg
    assert 'class="sp-start"' in svg    # départ pennant
    assert 'class="sp-finish"' in svg   # checkered arrivée flag


def test_accent_from_data_tints_the_silhouette():
    svg = StageProfile.from_gpx(SIMPLE_GPX, accent="#E4002B").render()
    assert 'fill="#E4002B"' in svg and ACCENT not in svg


def test_climb_category_draws_the_summit_badge():
    svg = StageProfile.from_gpx(
        SIMPLE_GPX, climbs=[Climb("Mortirolo", 0.15, "HC")],
    ).render()
    assert 'class="sp-cat"' in svg and ">HC</text>" in svg


def test_uncategorised_climb_has_altitude_but_no_badge():
    svg = _profile()   # Mortirolo carries no category
    assert 'class="sp-climb-ele"' in svg
    assert 'class="sp-cat"' not in svg


def test_invalid_climb_category_raises():
    with pytest.raises(ValueError):
        Climb("Mortirolo", 55, "5")


def test_sprint_is_marked_on_the_route_line():
    svg = StageProfile.from_gpx(SIMPLE_GPX, sprints=[0.15]).render()
    assert 'class="sp-sprint"' in svg and ">S</text>" in svg


def test_km_scale_ticks_along_the_foot():
    svg = _profile()
    assert 'class="sp-scale"' in svg


def test_render_labels_towns_uppercase_climbs_letter_case():
    svg = _profile()
    assert "TIRANO" in svg and "BORMIO" in svg      # towns are uppercased
    assert "Mortirolo" in svg                        # climbs keep their letter case
    assert " M<" in svg or "M</text>" in svg         # elevation unit


def test_render_has_no_header_or_title():
    svg = _profile()
    assert "STAGE PROFILE" not in svg and "TIRANO BORMIO" not in svg  # name is never drawn


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
