"""Run the roadbook generator as ``python -m stage_profiler <source>``."""

from __future__ import annotations

from .cli import main

if __name__ == "__main__":
    raise SystemExit(main())
