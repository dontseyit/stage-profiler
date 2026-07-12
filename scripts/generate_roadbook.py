#!/usr/bin/env python3
"""Batch roadbook generator — turn a set of races into on-brand stage posters.

Point this at a **manifest** (JSON) describing your races, or at a **folder** of ``.gpx``
files, and it writes two visuals per race in the toolkit's baked-in look, each as a
self-contained SVG *and* a matching PNG (rasterised with ``rsvg-convert``):

    {stem}-profile.svg / .png   the segmented steepness-band profile   (from the .gpx)
    {stem}-map.svg / .png       the start/finish stage map             (from a country GeoJSON)

The look lives entirely in the library — this script only supplies the data (route, town
names, named climbs, and the map's country + start/finish). PNG output needs ``rsvg-convert``
(``brew install librsvg``); without it the script writes SVG only. Pass ``--no-png`` to skip
it, ``--scale N`` to change the PNG resolution (default 2×).

Manifest format (paths resolve relative to the manifest file)::

    {
      "output_dir": "build",
      "races": [
        {
          "gpx": "stage-4-course.gpx",        # required
          "name": "Carcassonne — Foix",         # optional — title (falls back to GPX/filename)
          "start_town": "Carcassonne",          # profile + map start label
          "finish_town": "Foix",                # profile + map finish label
          "climbs": [                           # named climbs, labelled over their summit km
            { "name": "Port de Lers", "km": 118 },
            { "name": "Mur de Péguère", "km": 147 }
          ],
          "map": {                              # optional — omit for a profile-only race
            "geojson": "fra.geojson",
            "start": [2.4362, 43.2006],         # optional [lon, lat] — else the GPX's first point
            "end": [1.6075, 42.9640]            # optional [lon, lat] — else the GPX's last point
          }
        }
      ]
    }

Usage::

    python scripts/generate_roadbook.py races.example.json
    python scripts/generate_roadbook.py races.example.json --out posters/
    python scripts/generate_roadbook.py path/to/gpx-folder/     # profiles for every .gpx
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Make the src-layout package importable when running in-place (no `pip install -e .`).
sys.path.insert(0, str(ROOT / "src"))

from stage_profiler import (  # noqa: E402
    Climb,
    RouteMetrics,
    StageMap,
    StageProfile,
    parse_gpx,
)

LonLat = tuple[float, float]


# ── Manifest model ────────────────────────────────────────────────────────────

@dataclass
class MapSpec:
    """A race's map inputs: a country outline plus start/finish (both optional —
    missing coordinates fall back to the GPX endpoints)."""

    geojson: Path
    start: "LonLat | None" = None
    end: "LonLat | None" = None


@dataclass
class RaceSpec:
    """One race: its route, the roadbook labels, and optional map inputs."""

    gpx: Path
    name: "str | None" = None
    start_town: str = ""
    finish_town: str = ""
    climbs: "tuple[Climb, ...]" = ()
    map: "MapSpec | None" = None


@dataclass
class Result:
    """What one race produced — for the run report."""

    name: str
    files: "list[Path]" = field(default_factory=list)
    metrics: "RouteMetrics | None" = None


# ── Manifest loading ──────────────────────────────────────────────────────────

def _resolve(base: Path, path: str) -> Path:
    """Resolve a manifest path relative to the manifest's own directory."""
    p = Path(path)
    return p if p.is_absolute() else base / p


def _coord(value: object) -> "LonLat | None":
    """Validate an optional ``[lon, lat]`` pair from the manifest."""
    if value is None:
        return None
    if not (isinstance(value, (list, tuple)) and len(value) == 2):
        raise ValueError(f"expected [lon, lat], got {value!r}")
    return (float(value[0]), float(value[1]))


def _climbs(value: object, gpx: str) -> "tuple[Climb, ...]":
    """Validate a manifest ``climbs`` list of ``{name, km}`` entries."""
    climbs: "list[Climb]" = []
    for entry in value or []:
        if not (isinstance(entry, dict) and "name" in entry and "km" in entry):
            raise ValueError(f"{gpx}: each climb needs 'name' and 'km', got {entry!r}")
        climbs.append(Climb(str(entry["name"]), float(entry["km"])))
    return tuple(climbs)


def _race_from_dict(entry: dict, base: Path) -> RaceSpec:
    if not isinstance(entry, dict):
        raise ValueError(f"each race must be an object, got {entry!r}")
    if "gpx" not in entry:
        raise ValueError("each race needs a 'gpx' path")
    gpx = entry["gpx"]

    map_spec = None
    raw_map = entry.get("map")
    if raw_map:
        if not isinstance(raw_map, dict):
            raise ValueError(f"{gpx}: 'map' must be an object")
        if "geojson" not in raw_map:
            raise ValueError(f"{gpx}: 'map' needs a 'geojson' path")
        map_spec = MapSpec(
            geojson=_resolve(base, raw_map["geojson"]),
            start=_coord(raw_map.get("start")),
            end=_coord(raw_map.get("end")),
        )

    return RaceSpec(
        gpx=_resolve(base, gpx),
        name=entry.get("name"),
        start_town=entry.get("start_town", ""),
        finish_town=entry.get("finish_town", ""),
        climbs=_climbs(entry.get("climbs"), gpx),
        map=map_spec,
    )


def load_manifest(path: Path) -> "tuple[Path, list[RaceSpec]]":
    """Parse a manifest file into (output_dir, races)."""
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("manifest must be a JSON object with a 'races' array")
    base = path.parent
    out_dir = _resolve(base, data.get("output_dir", "build"))
    races = [_race_from_dict(entry, base) for entry in data.get("races", [])]
    return out_dir, races


def discover_folder(folder: Path) -> "tuple[Path, list[RaceSpec]]":
    """Folder mode: render a profile for every ``.gpx``. A ``races.json`` alongside
    them supplies names / towns / climbs / maps; any unlisted ``.gpx`` still gets a profile."""
    manifest = folder / "races.json"
    if manifest.exists():
        out_dir, races = load_manifest(manifest)
        listed = {race.gpx.resolve() for race in races}
        extra = [RaceSpec(gpx=g) for g in sorted(folder.glob("*.gpx")) if g.resolve() not in listed]
        return out_dir, races + extra
    return folder / "build", [RaceSpec(gpx=g) for g in sorted(folder.glob("*.gpx"))]


# ── Rendering ─────────────────────────────────────────────────────────────────

def _gpx_endpoints(gpx: Path) -> "tuple[LonLat, LonLat]":
    """First and last track point of a GPX, as ``(lon, lat)`` — the route's ends."""
    points = parse_gpx(gpx.read_text(encoding="utf-8"))
    if not points:
        raise ValueError(f"{gpx.name}: no track points")
    start, end = points[0], points[-1]
    return (start.lon, start.lat), (end.lon, end.lat)


def _unique_stems(races: "list[RaceSpec]") -> "list[str]":
    """One output stem per race (the GPX filename), disambiguating repeats with ``-2``,
    ``-3``, … so two same-named routes never silently overwrite each other's SVGs."""
    counts: "dict[str, int]" = {}
    stems: "list[str]" = []
    for race in races:
        base = race.gpx.stem
        counts[base] = counts.get(base, 0) + 1
        stems.append(base if counts[base] == 1 else f"{base}-{counts[base]}")
    return stems


def render_race(race: RaceSpec, out_dir: Path, stem: str) -> Result:
    """Render a race's profile (always) and map (when map inputs are given)."""
    out_dir.mkdir(parents=True, exist_ok=True)

    profile = StageProfile.from_file(
        race.gpx, name=race.name,
        start_town=race.start_town, finish_town=race.finish_town, climbs=race.climbs,
    )
    result = Result(name=profile.name, metrics=profile.metrics)

    profile_path = out_dir / f"{stem}-profile.svg"
    profile_path.write_text(profile.render(), encoding="utf-8")
    result.files.append(profile_path)

    if race.map is not None:
        start, end = race.map.start, race.map.end
        if start is None or end is None:
            gpx_start, gpx_end = _gpx_endpoints(race.gpx)
            start = start or gpx_start
            end = end or gpx_end
        smap = StageMap.from_file(
            race.map.geojson, start=start, end=end,
            start_label=race.start_town, end_label=race.finish_town,
            start_ele=profile.start_ele, finish_ele=profile.finish_ele,
            name=race.name,
        )
        map_path = out_dir / f"{stem}-map.svg"
        map_path.write_text(smap.render(), encoding="utf-8")
        result.files.append(map_path)

    return result


def _rasterize(svg_path: Path, scale: float) -> "Path | None":
    """Write a PNG next to ``svg_path`` via rsvg-convert. Returns the PNG path, or ``None``
    if rasterisation fails — the SVG is already saved, so a bad PNG never sinks the render."""
    png_path = svg_path.with_suffix(".png")
    try:
        subprocess.run(
            ["rsvg-convert", "-z", f"{scale:g}", "-o", str(png_path), str(svg_path)],
            check=True, capture_output=True,
        )
        return png_path
    except (OSError, subprocess.CalledProcessError) as exc:
        print(f"  ! PNG failed for {svg_path.name}: {exc}", file=sys.stderr)
        return None


# ── Reporting & CLI ───────────────────────────────────────────────────────────

def _report(result: Result, cwd: Path) -> None:
    print(result.name)
    m = result.metrics
    if m is not None:
        print(f"  {m.total_distance_km:.1f} km · ↑ {round(m.ascent_m):,} m · "
              f"max {m.max_gradient_pct:.0f}%")
    for path in result.files:
        try:
            shown = path.relative_to(cwd)
        except ValueError:
            shown = path
        print(f"  → {shown}")


def main(argv: "list[str] | None" = None) -> int:
    parser = argparse.ArgumentParser(
        prog="generate_roadbook",
        description="Generate stage-profile + stage-map SVG posters for a set of races.",
    )
    parser.add_argument("source", help="A manifest .json, or a folder of .gpx files")
    parser.add_argument("-o", "--out", help="Override the output directory")
    parser.add_argument("--no-png", action="store_true", help="Write SVG only (skip PNG rasterisation)")
    parser.add_argument("--scale", type=float, default=2.0, metavar="N", help="PNG scale factor (default 2×)")
    args = parser.parse_args(argv)

    source = Path(args.source)
    if not source.exists():
        print(f"generate_roadbook: error: no such file or folder: {source}", file=sys.stderr)
        return 2

    try:
        if source.is_dir():
            out_dir, races = discover_folder(source)
        else:
            out_dir, races = load_manifest(source)
    except (ValueError, OSError, TypeError) as exc:
        print(f"generate_roadbook: error: {exc}", file=sys.stderr)
        return 2
    if args.out:
        out_dir = Path(args.out)

    if not races:
        print("generate_roadbook: nothing to render (no races found).", file=sys.stderr)
        return 1

    scale: "float | None" = None
    if not args.no_png:
        if shutil.which("rsvg-convert"):
            scale = args.scale
        else:
            print("generate_roadbook: warning: rsvg-convert not found — writing SVG only "
                  "(install it with `brew install librsvg` for PNG output).", file=sys.stderr)

    cwd = Path.cwd()
    stems = _unique_stems(races)
    failures = 0
    for race, stem in zip(races, stems):
        try:
            result = render_race(race, out_dir, stem)
            if scale is not None:
                result.files += [p for svg in list(result.files) if (p := _rasterize(svg, scale))]
            _report(result, cwd)
        except Exception as exc:  # keep going — one bad race shouldn't sink the batch
            failures += 1
            print(f"  ✗ {race.gpx.name}: {exc}", file=sys.stderr)

    rendered = len(races) - failures
    print(f"\n{rendered}/{len(races)} race(s) → {out_dir}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
