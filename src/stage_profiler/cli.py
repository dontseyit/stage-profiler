"""Command-line interface: ``stage-profiler route.gpx -o out.svg``."""

from __future__ import annotations

import argparse
import json
import sys

from .profile import StageProfile
from .render import RenderOptions


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="stage-profiler",
        description="Render a stage-profile SVG from a GPX route.",
    )
    parser.add_argument("gpx", help="Path to a .gpx file, or '-' to read GPX from stdin")
    parser.add_argument("-o", "--output", help="Write the SVG here (default: stdout)")
    parser.add_argument("--name", help="Override the route title")
    # canvas & layout
    parser.add_argument("--width", type=int, default=RenderOptions.width, help="Canvas width")
    parser.add_argument("--height", type=int, default=RenderOptions.height, help="Canvas height")
    parser.add_argument("--header", choices=("full", "minimal", "none"), default=RenderOptions.header, help="Header style")
    # appearance
    parser.add_argument("-c", "--color", help="Accent colour hex, e.g. #c8f135")
    parser.add_argument("--no-gradient", action="store_true", help="Solid accent fill instead of steepness shading")
    parser.add_argument("--no-fill", action="store_true", help="Line only — no area fill")
    parser.add_argument("--no-background", action="store_true", help="Transparent canvas (keep chrome)")
    parser.add_argument("--bare", action="store_true", help="Profile only: no header/axes/labels, transparent background")
    parser.add_argument("--smoothing", type=int, default=0, metavar="N", help="Moving-average radius in points (0 = off)")
    # altitude axis
    parser.add_argument("--auto-y", action="store_true", help="Cross-compatible altitude axis so routes stay comparable")
    parser.add_argument("--y-min", type=float, help="Pin the altitude-axis minimum (metres)")
    parser.add_argument("--y-max", type=float, help="Pin the altitude-axis maximum (metres)")
    parser.add_argument("--metrics", action="store_true", help="Also print route metrics as JSON to stderr")
    return parser


def main(argv: "list[str] | None" = None) -> int:
    args = _build_parser().parse_args(argv)

    try:
        if args.gpx == "-":
            profile = StageProfile.from_gpx(sys.stdin.read(), name=args.name)
        else:
            profile = StageProfile.from_file(args.gpx, name=args.name)
    except (ValueError, OSError) as exc:
        print(f"stage-profiler: error: {exc}", file=sys.stderr)
        return 1

    opts_kwargs: "dict[str, object]" = {
        "width": args.width,
        "height": args.height,
        "header": args.header,
        "gradient_shading": not args.no_gradient,
        "fill": not args.no_fill,
        "background": not args.no_background,
        "bare": args.bare,
        "smoothing": args.smoothing,
        "auto_y": args.auto_y,
        "y_min": args.y_min,
        "y_max": args.y_max,
    }
    if args.color:
        opts_kwargs["color"] = args.color

    svg = profile.render(RenderOptions(**opts_kwargs))  # type: ignore[arg-type]

    if args.output:
        with open(args.output, "w", encoding="utf-8") as fh:
            fh.write(svg)
    else:
        sys.stdout.write(svg)
        if sys.stdout.isatty():
            sys.stdout.write("\n")

    if args.metrics:
        json.dump(profile.metrics.to_dict(), sys.stderr, indent=2)
        sys.stderr.write("\n")

    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
