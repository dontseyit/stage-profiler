"""Command-line interface with two subcommands::

    stage-profiler profile route.gpx --start-town Tirano --finish-town Bormio \\
        --climb "Mortirolo:55" --climb "Foscagno:140" -o profile.svg

    stage-profiler map ita.geojson --start 10.17 46.22 --end 10.37 46.47 \\
        --start-town Tirano --finish-town Bormio --start-ele 440 --finish-ele 1225 -o map.svg

There are no styling flags — the look is fixed. You supply the route and its labels.
"""

from __future__ import annotations

import argparse
import json
import sys

from .map import StageMap
from .profile import Climb, StageProfile

__all__ = ["main"]


def _climb(spec: str) -> Climb:
    """Parse a ``"Name:km"`` or ``"Name:km:category"`` climb spec (km is the summit's
    distance along the route; category is ``HC`` or ``1``–``4``)."""
    name, _, km = spec.rpartition(":")
    category = ""
    if km.upper() in ("HC", "1", "2", "3", "4") and ":" in name:
        category, (name, _, km) = km.upper(), name.rpartition(":")
    if not name or not km:
        raise argparse.ArgumentTypeError(f"climb must be 'Name:km[:category]', got {spec!r}")
    try:
        return Climb(name.strip(), float(km), category)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(str(exc))


def _add_profile_parser(sub: "argparse._SubParsersAction") -> None:
    p = sub.add_parser("profile", help="Render a stage-profile SVG from a GPX route.")
    p.add_argument("gpx", help="Path to a .gpx file, or '-' to read GPX from stdin")
    p.add_argument("-o", "--output", help="Write the SVG here (default: stdout)")
    p.add_argument("--name", help="Override the route title (used for reporting only)")
    p.add_argument("--start-town", default="", help="Start town label")
    p.add_argument("--finish-town", default="", help="Finish town label")
    p.add_argument("--climb", action="append", type=_climb, default=[], metavar="NAME:KM[:CAT]",
                   help="A named climb over its summit km, with an optional UCI category "
                        "(HC, 1-4), e.g. 'Mortirolo:55:HC' (repeatable)")
    p.add_argument("--sprint", action="append", type=float, default=[], metavar="KM",
                   help="An intermediate sprint at this km (repeatable)")
    p.add_argument("--accent", default="", metavar="HEX",
                   help="Race colour tinting the silhouette, e.g. '#E4002B'")
    p.add_argument("--length", type=float, metavar="KM",
                   help="Draw only the first KM of the route (clip the tail; that point "
                        "becomes the finish) — for stages shorter than their GPX")
    p.add_argument("--metrics", action="store_true", help="Also print route metrics as JSON to stderr")
    p.set_defaults(func=_run_profile)


def _add_map_parser(sub: "argparse._SubParsersAction") -> None:
    p = sub.add_parser("map", help="Render a stage-map SVG from a country GeoJSON.")
    p.add_argument("geojson", help="Path to a .geojson file, or '-' to read GeoJSON from stdin")
    p.add_argument("-o", "--output", help="Write the SVG here (default: stdout)")
    p.add_argument("--start", nargs=2, type=float, metavar=("LON", "LAT"), required=True, help="Start (lon lat)")
    p.add_argument("--end", nargs=2, type=float, metavar=("LON", "LAT"), required=True, help="Finish (lon lat)")
    p.add_argument("--start-town", default="", help="Start town label")
    p.add_argument("--finish-town", default="", help="Finish town label")
    p.add_argument("--start-ele", type=float, help="Start elevation (m), shown in the label")
    p.add_argument("--finish-ele", type=float, help="Finish elevation (m), shown in the label")
    p.add_argument("--name", help="Override the map title (used for reporting only)")
    p.set_defaults(func=_run_map)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="stage-profiler",
        description="Render a stage-profile SVG from a GPX route, or a stage-map SVG from a country GeoJSON.",
    )
    sub = parser.add_subparsers(dest="command", required=True, metavar="{profile,map}")
    _add_profile_parser(sub)
    _add_map_parser(sub)
    return parser


def _write_svg(svg: str, output: "str | None") -> None:
    if output:
        with open(output, "w", encoding="utf-8") as fh:
            fh.write(svg)
    else:
        sys.stdout.write(svg)
        if sys.stdout.isatty():
            sys.stdout.write("\n")


def _run_profile(args: argparse.Namespace) -> int:
    try:
        if args.gpx == "-":
            profile = StageProfile.from_gpx(
                sys.stdin.read(), name=args.name,
                start_town=args.start_town, finish_town=args.finish_town,
                climbs=args.climb, sprints=args.sprint, accent=args.accent,
                length_km=args.length,
            )
        else:
            profile = StageProfile.from_file(
                args.gpx, name=args.name,
                start_town=args.start_town, finish_town=args.finish_town,
                climbs=args.climb, sprints=args.sprint, accent=args.accent,
                length_km=args.length,
            )
    except (ValueError, OSError) as exc:
        print(f"stage-profiler: error: {exc}", file=sys.stderr)
        return 1

    _write_svg(profile.render(), args.output)
    if args.metrics:
        json.dump(profile.metrics.to_dict(), sys.stderr, indent=2)
        sys.stderr.write("\n")
    return 0


def _run_map(args: argparse.Namespace) -> int:
    try:
        # from_geojson accepts a file path or JSON text, so stdin and a path both work.
        source = sys.stdin.read() if args.geojson == "-" else args.geojson
        smap = StageMap.from_geojson(
            source, start=tuple(args.start), end=tuple(args.end),
            start_label=args.start_town, end_label=args.finish_town,
            start_ele=args.start_ele, finish_ele=args.finish_ele, name=args.name,
        )
    except (ValueError, OSError, TypeError) as exc:
        print(f"stage-profiler: error: {exc}", file=sys.stderr)
        return 1

    _write_svg(smap.render(), args.output)
    return 0


def main(argv: "list[str] | None" = None) -> int:
    args = _build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
