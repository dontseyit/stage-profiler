"""The roadbook generator — turn a set of races into on-brand stage posters.

This is the engine behind the ``stage-profiler`` command. Give it a **manifest** (JSON)
describing your races, a **folder** of ``.gpx`` files, or a **single** ``.gpx``, and it
writes two visuals per race in the toolkit's baked-in look, each as a self-contained SVG
*and* a matching PNG (rasterised with ``rsvg-convert``):

    {stem}-profile.svg / .png   the segmented steepness-band profile   (from the .gpx)
    {stem}-map.svg / .png       the start/finish stage map             (from a country GeoJSON)

The look lives entirely in the library — the generator only supplies the data (route, town
names, named climbs, and the map's country + start/finish). PNG output needs ``rsvg-convert``
(``brew install librsvg``); without it only SVG is written.

Manifest format (paths resolve relative to the manifest file)::

    {
      "output_dir": "build",
      "races": [
        {
          "gpx": "stage-4-parcours.gpx",       # required
          "name": "Carcassonne — Foix",         # optional — title (falls back to GPX/filename)
          "start_town": "Carcassonne",          # profile + map start label
          "finish_town": "Foix",                # profile + map finish label
          "accent": "#E4002B",                  # optional — race colour tinting the profile
          "sprints": [88.4],                    # optional — intermediate sprints (km)
          "length_km": 172,                     # optional — clip the route here (drawn finish)
          "climbs": [                           # named climbs, labelled over their summit km
            { "name": "Port de Lers", "km": 118, "category": "1" },
            # optional "offset" nudges the label sideways (canvas units) to avoid overlaps
            { "name": "Mur de Péguère", "km": 147, "category": "2", "offset": -30 }
          ],
          "map": {                              # optional — omit for a profile-only race
            "geojson": "fra.geojson",
            "start": [2.4362, 43.2006],         # optional [lon, lat] — else the GPX's first point
            "end": [1.6075, 42.9640]            # optional [lon, lat] — else the GPX's last point
          }
        }
      ]
    }

Programmatic use mirrors the command::

    from stage_profiler import generate
    generate("races.json", out="posters/", png=False)
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

from .geometry import RouteMetrics
from .gpx import parse_gpx
from .map import StageMap
from .profile import Climb, StageProfile

__all__ = [
    "MapSpec",
    "RaceSpec",
    "Result",
    "load_manifest",
    "discover_folder",
    "render_race",
    "generate",
]

LonLat = "tuple[float, float]"


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
    sprints: "tuple[float, ...]" = ()
    accent: str = ""
    length_km: "float | None" = None
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
    """Validate a manifest ``climbs`` list of ``{name, km[, category][, offset]}`` entries."""
    climbs: "list[Climb]" = []
    for entry in value or []:
        if not (isinstance(entry, dict) and "name" in entry and "km" in entry):
            raise ValueError(f"{gpx}: each climb needs 'name' and 'km', got {entry!r}")
        offset = entry.get("offset", 0)
        if isinstance(offset, bool) or not isinstance(offset, (int, float)):
            raise ValueError(f"{gpx}: climb 'offset' must be a number, got {offset!r}")
        try:
            climbs.append(Climb(str(entry["name"]), float(entry["km"]),
                                str(entry.get("category", "")).upper(), float(offset)))
        except ValueError as exc:
            raise ValueError(f"{gpx}: {exc}") from exc
    return tuple(climbs)


def _sprints(value: object, gpx: str) -> "tuple[float, ...]":
    """Validate a manifest ``sprints`` list of km numbers."""
    sprints: "list[float]" = []
    for entry in value or []:
        if isinstance(entry, bool) or not isinstance(entry, (int, float)):
            raise ValueError(f"{gpx}: each sprint must be a km number, got {entry!r}")
        sprints.append(float(entry))
    return tuple(sprints)


def _length_km(value: object, gpx: str) -> "float | None":
    """Validate an optional manifest ``length_km`` (positive number, km)."""
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
        raise ValueError(f"{gpx}: 'length_km' must be a positive number, got {value!r}")
    return float(value)


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
        sprints=_sprints(entry.get("sprints"), gpx),
        accent=str(entry.get("accent", "")),
        length_km=_length_km(entry.get("length_km"), gpx),
        map=map_spec,
    )


def load_manifest(path: Path) -> "tuple[Path, list[RaceSpec]]":
    """Parse a manifest file into ``(output_dir, races)``."""
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


def plan(source: Path) -> "tuple[Path, list[RaceSpec]]":
    """Work out what to render from ``source`` — a manifest ``.json``, a folder of
    ``.gpx``, or a single ``.gpx`` — returning ``(output_dir, races)``."""
    if not source.exists():
        raise FileNotFoundError(f"no such file or folder: {source}")
    if source.is_dir():
        return discover_folder(source)
    if source.suffix.lower() == ".gpx":
        return source.parent / "build", [RaceSpec(gpx=source)]
    return load_manifest(source)


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
        start_town=race.start_town, finish_town=race.finish_town,
        climbs=race.climbs, sprints=race.sprints, accent=race.accent,
        length_km=race.length_km,
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


def _png_scale(scale: float) -> "float | None":
    """The PNG scale to use, or ``None`` (with a warning) when rsvg-convert is missing."""
    if shutil.which("rsvg-convert"):
        return scale
    print("stage-profiler: warning: rsvg-convert not found — writing SVG only "
          "(install it with `brew install librsvg` for PNG output).", file=sys.stderr)
    return None


def generate(source: "str | Path", *, out: "str | Path | None" = None,
             png: bool = True, scale: float = 2.0) -> int:
    """Render every race described by ``source`` into on-brand SVG (and PNG) posters.

    ``source`` is a manifest ``.json``, a folder of ``.gpx`` files, or a single ``.gpx``.
    ``out`` overrides the output directory; ``png`` toggles PNG rasterisation; ``scale`` is
    the PNG resolution factor. Returns ``0`` on success, ``1`` if any race failed or nothing
    was found. Raises ``ValueError`` / ``OSError`` for an unreadable source or manifest.
    """
    out_dir, races = plan(Path(source))
    if out is not None:
        out_dir = Path(out)
    if not races:
        print("stage-profiler: nothing to render (no races found).", file=sys.stderr)
        return 1

    scale_factor = _png_scale(scale) if png else None
    cwd = Path.cwd()
    stems = _unique_stems(races)
    failures = 0
    for race, stem in zip(races, stems):
        try:
            result = render_race(race, out_dir, stem)
            if scale_factor is not None:
                result.files += [p for svg in list(result.files) if (p := _rasterize(svg, scale_factor))]
            _report(result, cwd)
        except Exception as exc:  # keep going — one bad race shouldn't sink the batch
            failures += 1
            print(f"  ✗ {race.gpx.name}: {exc}", file=sys.stderr)

    rendered = len(races) - failures
    print(f"\n{rendered}/{len(races)} race(s) → {out_dir}")
    return 1 if failures else 0
