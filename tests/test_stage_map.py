"""Tests for the stage_profiler.map module. Run with `pytest` (PYTHONPATH=src).

Uses a synthetic square "country" so the suite is fast and needs no bundled GeoJSON.
"""

from __future__ import annotations

import json
import xml.etree.ElementTree as ET

import pytest

from stage_profiler import Marker, StageMap, render_map_svg
from stage_profiler.map import HEIGHT, WIDTH
from stage_profiler.theme import ACCENT, BACKGROUND, LAND_FILL, PAPER

SQUARE_GEOJSON = {
    "type": "FeatureCollection",
    "features": [
        {
            "type": "Feature",
            "properties": {"name": "Testland"},
            "geometry": {
                "type": "Polygon",
                "coordinates": [[[2.0, 44.0], [8.0, 44.0], [8.0, 48.0], [2.0, 48.0], [2.0, 44.0]]],
            },
        }
    ],
}

START = (3.0, 45.0)
END = (7.0, 47.0)


def _map(**kwargs) -> StageMap:
    return StageMap.from_geojson(
        SQUARE_GEOJSON, start=START, end=END,
        start_label="Tirano", end_label="Bormio", **kwargs,
    )


def _svg_tags(svg: str) -> "list[str]":
    return [el.tag.rsplit("}", 1)[-1] for el in ET.fromstring(svg).iter()]


# --- construction -------------------------------------------------------------

def test_from_geojson_accepts_dict_string_and_path(tmp_path):
    from_dict = _map()
    from_string = StageMap.from_geojson(json.dumps(SQUARE_GEOJSON), start=START, end=END)
    path = tmp_path / "testland.geojson"
    path.write_text(json.dumps(SQUARE_GEOJSON), encoding="utf-8")
    from_file = StageMap.from_file(path, start=START, end=END)
    for smap in (from_dict, from_string, from_file):
        assert smap.rings and len(smap.rings[0]) == 5
        assert smap.start.icon == "start" and smap.end.icon == "finish"


def test_name_detected_and_overridden():
    assert _map().name == "TESTLAND"
    assert _map(name="tirano-bormio").name == "TIRANO BORMIO"


def test_empty_geometry_raises():
    empty = {"type": "FeatureCollection", "features": []}
    with pytest.raises(ValueError):
        StageMap.from_geojson(empty, start=START, end=END).render()


# --- rendering ----------------------------------------------------------------

def test_render_is_valid_svg_at_fixed_size():
    root = ET.fromstring(_map().render())
    assert root.get("viewBox") == f"0 0 {WIDTH} {HEIGHT}"
    assert root.get("class") == "stage-map"


def test_background_land_and_two_markers():
    svg = _map().render()
    assert 'class="sm-bg"' in svg and BACKGROUND in svg
    assert 'class="sm-land"' in svg and LAND_FILL in svg
    assert svg.count('class="sm-marker"') == 2


def test_start_is_hollow_ring_finish_is_solid_dot():
    svg = _map().render()
    # hollow start: a ring stroked in the accent over paper; solid finish: a filled dot.
    assert f'fill="{PAPER}" stroke="{ACCENT}"' in svg
    assert f'r="5" fill="{ACCENT}"' in svg


def test_labels_show_town_kind_and_elevation():
    svg = StageMap.from_geojson(
        SQUARE_GEOJSON, start=START, end=END, start_label="Tirano", end_label="Bormio",
        start_ele=440, finish_ele=1225,
    ).render()
    assert "TIRANO" in svg and "BORMIO" in svg
    assert "START · 440M" in svg and "FINISH · 1,225M" in svg


def test_no_header():
    svg = _map().render()
    assert "STAGE MAP" not in svg and "sm-kicker" not in svg


def test_labels_are_escaped():
    svg = StageMap.from_geojson(
        SQUARE_GEOJSON, start=START, end=END, start_label="A & B", end_label="C",
    ).render()
    assert "A &amp; B" in svg


def test_close_pins_keep_both_labels():
    # Nearly-coincident start/finish must still render both town labels (the split path).
    svg = StageMap.from_geojson(
        SQUARE_GEOJSON, start=(4.99, 45.99), end=(5.01, 46.01),
        start_label="Alpha", end_label="Omega",
    ).render()
    assert "ALPHA" in svg and "OMEGA" in svg


def test_render_map_svg_low_level_matches_high_level():
    m = _map()
    assert m.render() == render_map_svg(m.rings, m.start, m.end, m.name)
