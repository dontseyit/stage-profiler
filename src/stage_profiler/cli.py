"""The ``stage-profiler`` command — the roadbook generator.

Point it at a **manifest** (JSON) describing your races, a **folder** of ``.gpx`` files, or
a single ``.gpx``, and it writes an on-brand stage-profile (and a stage-map, when the race
gives map inputs) per race — each a self-contained SVG and a matching PNG::

    stage-profiler races.json                 # → build/ (or the manifest's output_dir)
    stage-profiler races.json --out posters/
    stage-profiler routes/                     # a profile for every .gpx in the folder
    stage-profiler stage-4.gpx --no-png        # one route, SVG only

There are no styling flags — the look is fixed (see :mod:`stage_profiler.theme`). Everything
about a race — towns, climbs, sprints, accent, map — is data you supply in the manifest; the
manifest format is documented in :mod:`stage_profiler.roadbook`.
"""

from __future__ import annotations

import argparse
import sys

from . import roadbook

__all__ = ["main"]


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="stage-profiler",
        description="Turn a race manifest (JSON) — or a folder / single .gpx — into on-brand "
                    "stage-profile and stage-map SVG posters (and matching PNGs).",
    )
    parser.add_argument("source", help="A manifest .json, a folder of .gpx files, or a single .gpx")
    parser.add_argument("-o", "--out", metavar="DIR",
                        help="Output directory (default: the manifest's output_dir, else ./build)")
    parser.add_argument("--no-png", action="store_true",
                        help="Write SVG only (skip PNG rasterisation)")
    parser.add_argument("--scale", type=float, default=2.0, metavar="N",
                        help="PNG scale factor (default 2×)")
    return parser


def main(argv: "list[str] | None" = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        return roadbook.generate(args.source, out=args.out, png=not args.no_png, scale=args.scale)
    except (ValueError, OSError, TypeError) as exc:
        print(f"stage-profiler: error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
