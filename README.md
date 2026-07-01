# stage-profiler

Turn a `.gpx` route into a **stage-profile SVG** — and the route **metrics** to go with
it. Pure Python, **zero runtime dependencies** (stdlib only). Everything is configured
through a single `RenderOptions` — there are no baked-in presets, so you compose the
exact look you want.

```python
from stage_profiler import StageProfile, RenderOptions

profile = StageProfile.from_file("stage-1.gpx")

print(profile.metrics.to_dict())
# {'total_distance_m': 158145.8, 'total_distance_km': 158.1, 'ascent_m': 1395.0,
#  'descent_m': 1784.0, 'min_ele_m': 148.0, 'max_ele_m': 594.0, 'max_gradient_pct': 13.9}

svg = profile.render()                                       # 1280×520, full header
thumb = profile.render(RenderOptions(width=320, height=240, header="minimal"))
line = profile.render(bare=True, fill=False, auto_y=True)    # transparent line only
```

`render()` returns a self-contained SVG **string** — cache it, inline it, or serve it.

---

## Install

```bash
pip install stage-profiler          # from a package index
# or, from a checkout:
pip install -e .
```

Requires Python 3.9+.

---

## Library API

### `StageProfile`

| Method | Description |
| --- | --- |
| `StageProfile.from_file(path, *, name=None)` | Parse a `.gpx` file. Title falls back to the GPX `<name>` tag, then the filename. |
| `StageProfile.from_gpx(text, *, name=None)` | Parse GPX XML already in memory. |
| `.metrics` | A `RouteMetrics` (see below). |
| `.render(options=None, **overrides)` | Return an SVG string. Pass an `options=RenderOptions(...)` **or** keyword overrides. |

### `RouteMetrics`

Everything you'd persist per route: `total_distance_m`, `total_distance_km`, `ascent_m`,
`descent_m`, `min_ele_m`, `max_ele_m`, `max_gradient_pct` — plus `.to_dict()` for JSON.
Max gradient is the **maximum sustained** gradient over a ~100 m rolling window, so GPS
spikes don't lie.

### `RenderOptions`

| Field | Default | Effect |
| --- | --- | --- |
| `width` / `height` | `1280` / `520` | Canvas size (the exported / `viewBox` size). |
| `margin_top/right/bottom/left` | `116/36/48/58` | Plot inset. Give the header room in `margin_top`. |
| `header` | `"full"` | `"full"` (kicker + title + stat blocks), `"minimal"` (one line), or `"none"`. `"full"` suits `margin_top ≈ 116`, `"minimal" ≈ 34`. |
| `axis_size` / `tick_gap` / `x_tick_dy` / `x_ticks` | `12 / 10 / 22 / 8` | Axis-label type and tick spacing. |
| `color` | `#c8f135` | Accent (line + solid fill). |
| `gradient_shading` | `True` | Colour the fill by climb steepness; `False` = solid accent fill. |
| `fill` | `True` | Shade the area under the line; `False` = **line only** (the line carries the colour). |
| `stroke_grad` / `stroke_solid` | `1.6 / 2.4` | Line widths for shaded vs solid / line-only. |
| `smoothing` | `0` | Moving-average radius (points) on the drawn line only; metrics stay from raw data. |
| `background` | `True` | Draw the dark backdrop, or `False` for a transparent canvas (keeping chrome). |
| `bare` | `False` | **Profile only** — no header/axes/labels/background; silhouette bleeds edge-to-edge. |
| `auto_y` | `False` | **Cross-compatible axis** (see below). Takes precedence over `y_min`/`y_max`. |
| `y_min` / `y_max` | `None` | Pin the altitude axis (both required); otherwise auto-fit tight to the data. |

The altitude axis has three modes, in priority order: `auto_y` → manual `y_min`/`y_max` →
tight auto-fit. **`auto_y`** keeps profiles visually comparable across routes: the floor
sits just below the route's lowest point, and the top is the larger of a standardised
minimum ceiling (500 m, or 2000 m for routes over 100 km) and `peak + headroom` — so flat
routes stay pinned to a common frame while real climbs always breathe above the peak.
The thresholds are the `AUTO_Y_*` module constants in `render.py`.

### Composing the low-level pieces

```python
from stage_profiler import parse_gpx, build_series, render_svg, RenderOptions

series = build_series(parse_gpx(gpx_text))
svg = render_svg(series, name="ALPE D'HUEZ",
                 options=RenderOptions(width=320, height=240, header="minimal", auto_y=True))
```

---

## CLI

```bash
stage-profiler route.gpx -o profile.svg                          # 1280×520 full header
stage-profiler route.gpx --width 320 --height 240 --header minimal --metrics
stage-profiler route.gpx --bare --no-fill --auto-y -o line.svg   # transparent line only
cat route.gpx | stage-profiler - -c '#ff5a4d'                    # read from stdin
```

Flags: `--width`, `--height`, `--header {full,minimal,none}`, `--color`, `--name`,
`--no-gradient`, `--no-fill`, `--no-background`, `--bare`, `--smoothing N`, `--auto-y`,
`--y-min`, `--y-max`, `--metrics`.

---

## Fonts & theming

**Fonts are referenced, not embedded**, so SVGs stay small. Inline the SVG in a page that
loads **Bebas Neue** (display) and **Barlow** (body) and the type renders correctly; every
element carries an `sp-*` class (`sp-line`, `sp-area`, `sp-title`, `sp-tick`, …) for CSS
theming. If you render an SVG in isolation (e.g. `<img src>`), supply those fonts there.

The steepness colour ramp is the `RAMP` array in
[`ramp.py`](src/stage_profiler/ramp.py) — `[(gradient%, (r, g, b)), …]`.

---

## Development

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e '.[dev]'
pytest
```

---

## Layout

```
src/stage_profiler/
  gpx.py        parse GPX → points (namespace-agnostic)
  geometry.py   distances, metrics, sampled series, smoothing, ticks
  ramp.py       steepness colour ramp
  render.py     RenderOptions + SVG string generation
  profile.py    StageProfile — the high-level entry point
  cli.py        command-line interface
tests/          pytest suite
```
