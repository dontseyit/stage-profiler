#!/usr/bin/env python3
"""Render the bundled sample route to a stage-profile SVG (and a stage map, if the map
dependencies are installed).

    python examples/demo.py

Writes into ``examples/out/``. Run from the repository root so ``sample.gpx`` and
``fra.geojson`` resolve.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Make the src-layout package importable when running in-place (no `pip install -e .`).
sys.path.insert(0, str(ROOT / "src"))

from stage_profiler import Climb, StageProfile  # noqa: E402


def main() -> int:
    out_dir = Path(__file__).resolve().parent / "out"
    out_dir.mkdir(parents=True, exist_ok=True)

    profile = StageProfile.from_file(
        ROOT / "sample.gpx",
        start_town="Valdorée",
        finish_town="Mont Sample",
        sprints=[63.0],
        climbs=[
            Climb("Col du Démo", 49.0, "1"),
            Climb("Côte de l'Exemple", 91.0, "2"),
        ],
    )
    print(f"Route: {profile.name}")
    print(json.dumps(profile.metrics.to_dict(), indent=2))

    profile_svg = out_dir / "sample-profile.svg"
    profile_svg.write_text(profile.render(), encoding="utf-8")
    print(f"\n  → {profile_svg.relative_to(ROOT)}")

    # The map needs shapely + pyproj (installed with the package); skip it if unavailable.
    geojson = ROOT / "fra.geojson"
    if geojson.exists():
        try:
            from stage_profiler import StageMap

            smap = StageMap.from_file(
                geojson,
                start=(5.95, 45.05), end=(6.78, 45.92),
                start_label="Valdorée", end_label="Mont Sample",
                start_ele=profile.start_ele, finish_ele=profile.finish_ele,
            )
            map_svg = out_dir / "sample-map.svg"
            map_svg.write_text(smap.render(), encoding="utf-8")
            print(f"  → {map_svg.relative_to(ROOT)}")
        except ImportError:
            print("  (skipped map: install shapely + pyproj to render it)")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
