"""Tests for the stage_profiler package. Run with `pytest` (PYTHONPATH=src)."""

from __future__ import annotations

import xml.etree.ElementTree as ET

import pytest

from stage_profiler import (
    RenderOptions,
    StageProfile,
    auto_y_range,
    build_series,
    parse_gpx,
    prettify_name,
    render_svg,
)
from stage_profiler.render import (
    AUTO_Y_FLOOR,
    AUTO_Y_FLOOR_LONG,
    AUTO_Y_FOOTROOM,
    AUTO_Y_HEADROOM,
    AUTO_Y_LONG_KM,
)

# A tiny synthetic climb: 3 segments, ~111 m apart (0.001° latitude), so the metrics
# are easy to reason about. Uses a GPX 1.1 namespace to exercise the parser.
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


def _gpx_peaking_at(peak_ele: float, *, span_deg: float = 0.01) -> str:
    """A minimal 2-point route with a given peak elevation and latitude span."""
    return (
        '<gpx version="1.1" xmlns="http://www.topografix.com/GPX/1/1"><trk><trkseg>'
        '<trkpt lat="45.0000" lon="6.0000"><ele>0</ele></trkpt>'
        f'<trkpt lat="{45.0 + span_deg:.4f}" lon="6.0000"><ele>{peak_ele}</ele></trkpt>'
        "</trkseg></trk></gpx>"
    )


def _svg_tags(svg: str) -> list[str]:
    return [el.tag.rsplit("}", 1)[-1] for el in ET.fromstring(svg).iter()]


# --- parsing ------------------------------------------------------------------

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


# --- metrics ------------------------------------------------------------------

def test_metrics_values():
    m = build_series(parse_gpx(SIMPLE_GPX)).metrics
    assert m.ascent_m == pytest.approx(120.0)
    assert m.descent_m == pytest.approx(30.0)
    assert m.min_ele_m == 1000
    assert m.max_ele_m == 1120
    assert 300 < m.total_distance_m < 360
    assert m.total_distance_km == pytest.approx(m.total_distance_m / 1000)
    assert m.max_gradient_pct > 0


def test_metrics_to_dict_includes_km():
    d = build_series(parse_gpx(SIMPLE_GPX)).metrics.to_dict()
    assert set(d) >= {
        "total_distance_m", "total_distance_km", "ascent_m",
        "descent_m", "min_ele_m", "max_ele_m", "max_gradient_pct",
    }


def test_build_series_requires_two_points():
    with pytest.raises(ValueError):
        build_series(parse_gpx(SIMPLE_GPX)[:1])


# --- rendering ----------------------------------------------------------------

@pytest.mark.parametrize("width, height", [(1280, 520), (320, 240), (1080, 1080)])
def test_render_is_valid_svg_with_requested_size(width, height):
    svg = StageProfile.from_gpx(SIMPLE_GPX).render(width=width, height=height)
    root = ET.fromstring(svg)
    assert root.get("viewBox") == f"0 0 {width} {height}"
    assert root.get("width") == str(width)


def test_default_render_is_the_full_1280x520():
    svg = StageProfile.from_gpx(SIMPLE_GPX).render()
    root = ET.fromstring(svg)
    assert root.get("viewBox") == "0 0 1280 520"
    assert "STAGE PROFILE" in svg  # full header kicker


def test_header_full_minimal_none():
    p = StageProfile.from_gpx(SIMPLE_GPX)
    full = p.render(header="full")
    minimal = p.render(header="minimal")
    none = p.render(header="none")
    assert "sp-kicker" in full and "sp-title" in full
    assert "sp-kicker" not in minimal and "sp-title" in minimal
    assert "sp-title" not in none and "sp-kicker" not in none
    assert "sp-tick" in none  # axes remain when only the header is dropped


def test_invalid_header_raises():
    with pytest.raises(ValueError):
        StageProfile.from_gpx(SIMPLE_GPX).render(header="banner")


def test_bare_drops_all_chrome_and_background():
    svg = StageProfile.from_gpx(SIMPLE_GPX).render(bare=True)
    tags = _svg_tags(svg)
    assert "text" not in tags
    assert 'class="sp-bg"' not in svg
    assert 'class="sp-line"' in svg


def test_background_false_is_transparent_but_keeps_chrome():
    svg = StageProfile.from_gpx(SIMPLE_GPX).render(background=False)
    assert 'class="sp-bg"' not in svg
    assert "sp-tick" in svg and "STAGE PROFILE" in svg


def test_fill_off_removes_area_keeps_line():
    svg = StageProfile.from_gpx(SIMPLE_GPX).render(fill=False)
    assert 'class="sp-area"' not in svg
    assert 'class="sp-line"' in svg


def test_line_only_gradient_colours_the_stroke():
    svg = StageProfile.from_gpx(SIMPLE_GPX).render(fill=False, gradient_shading=True)
    assert 'stroke="url(#steepFill)"' in svg


def test_accent_colour_propagates():
    svg = StageProfile.from_gpx(SIMPLE_GPX).render(gradient_shading=False, color="#ff5a4d")
    assert "#ff5a4d" in svg


def test_name_is_prettified_and_escaped():
    assert prettify_name("stage-1_alpe duez") == "STAGE 1 ALPE DUEZ"
    svg = StageProfile.from_gpx(SIMPLE_GPX, name="A & B").render()
    assert "A &amp; B" in svg


def test_render_svg_low_level_matches_high_level():
    p = StageProfile.from_gpx(SIMPLE_GPX)
    assert p.render(RenderOptions(header="minimal")) == render_svg(
        p.series, p.name, RenderOptions(header="minimal")
    )


def test_render_rejects_options_and_kwargs_together():
    with pytest.raises(TypeError):
        StageProfile.from_gpx(SIMPLE_GPX).render(RenderOptions(), color="#fff")


# --- auto_y (cross-compatible altitude axis) ----------------------------------

@pytest.mark.parametrize(
    "min_ele, max_ele, dist_km",
    [
        (0, 73, 30),
        (2, 111, 80),
        (-40, 300, 50),
        (120, 1850, 60),
        (0, 300, 150),
        (0, 2500, 200),
    ],
)
def test_auto_y_range_rule(min_ele, max_ele, dist_km):
    low, high = auto_y_range(min_ele, max_ele, dist_km * 1000)
    ceiling = AUTO_Y_FLOOR_LONG if dist_km > AUTO_Y_LONG_KM else AUTO_Y_FLOOR
    assert low == min_ele - AUTO_Y_FOOTROOM
    assert high == max(ceiling, max_ele + AUTO_Y_HEADROOM)   # ceiling is a minimum


def test_auto_y_headroom_lifts_the_top_above_the_minimum_ceiling():
    # A long route peaking below the long ceiling still breathes by headroom rather than
    # being flattened to a hard 2000 (the bug this behaviour replaced).
    _, high = auto_y_range(0, 1950, 150_000)
    assert high == 1950 + AUTO_Y_HEADROOM
    assert high > AUTO_Y_FLOOR_LONG


def test_auto_y_distance_threshold_is_exclusive():
    below = auto_y_range(0, 300, AUTO_Y_LONG_KM * 1000)[1]       # exactly 100 km → short
    above = auto_y_range(0, 300, AUTO_Y_LONG_KM * 1000 + 1)[1]   # just over → long
    assert below == max(AUTO_Y_FLOOR, 300 + AUTO_Y_HEADROOM)
    assert above == max(AUTO_Y_FLOOR_LONG, 300 + AUTO_Y_HEADROOM)
    assert above > below


def test_auto_y_boundary_peak_at_ceiling_uses_headroom():
    assert auto_y_range(0, AUTO_Y_FLOOR, 30_000) == (-AUTO_Y_FOOTROOM, AUTO_Y_FLOOR + AUTO_Y_HEADROOM)


def test_auto_y_changes_axis_versus_tight_fit():
    p = StageProfile.from_gpx(_gpx_peaking_at(120))
    assert p.render(auto_y=True) != p.render()   # option is wired and moves the axis


def test_auto_y_long_route_reaches_the_taller_ceiling():
    # ~1.35° latitude ≈ 150 km → "long"; a low peak is framed to the 2000 m minimum.
    svg = StageProfile.from_gpx(_gpx_peaking_at(120, span_deg=1.35)).render(auto_y=True)
    assert f">{int(AUTO_Y_FLOOR_LONG)}<" in svg


def test_auto_y_takes_precedence_over_manual_range():
    p = StageProfile.from_gpx(_gpx_peaking_at(73))
    assert p.render(auto_y=True, y_min=0, y_max=9999) == p.render(auto_y=True)
