# stage-profiler

A roadbook toolkit with two visuals that share **one baked-in design language** — a
segmented steepness-band **stage profile** and a soft **stage map**, both driven by data
(no styling options):

- **`StageProfile`** — turn a `.gpx` route into a **stage-profile SVG**, styled like a Tour
  roadbook: the elevation line in ink over the area painted in a single green at three
  steepness opacities, named climbs labelled over their summits (with leaders), start and
  finish **corner blocks** (town · elevation · a green start flag / checkered finish flag),
  and the distance along the foot (`0 … total km`). No axes, no header.
- **`StageMap`** — turn a country **GeoJSON** into a **stage-map SVG**: the outline
  simplified into soft land, with a hollow-green **start** ring and a solid-green **finish**
  dot, each labelled with its town + elevation.

```python
from stage_profiler import StageProfile, Climb

profile = StageProfile.from_file(
    "stage.gpx",
    start_town="Tirano", finish_town="Bormio",
    climbs=[Climb("Mortirolo", 55), Climb("Foscagno", 140)],   # name + summit km
)
print(profile.metrics.to_dict())      # {'total_distance_km': 182.2, 'ascent_m': ..., ...}
svg = profile.render()                 # 840×300, transparent
```

```python
from stage_profiler import StageMap

smap = StageMap.from_file(
    "ita.geojson",
    start=(10.17, 46.22), end=(10.37, 46.47),
    start_label="Tirano", end_label="Bormio",
    start_ele=profile.start_ele, finish_ele=profile.finish_ele,
)
map_svg = smap.render()                # 460×220, transparent
```

Both `render()` calls return a self-contained SVG **string** — cache it, inline it, or serve
it. The two visuals stay in sync because the whole look lives in one place
([`theme.py`](src/stage_profiler/theme.py)); callers only supply data.

---

## Install

```bash
git clone https://github.com/dontseyit/stage-profiler.git
cd stage-profiler
pip install -e .
```

Requires Python 3.9+. Installing pulls in **shapely** and **pyproj** (used by `StageMap`);
`StageProfile` itself stays stdlib-only.

---

## Library API

### `StageProfile`

| Method / property | Description |
| --- | --- |
| `StageProfile.from_file(path, *, name=None, start_town="", finish_town="", climbs=())` | Parse a `.gpx` file. |
| `StageProfile.from_gpx(text, *, ...)` | Parse GPX XML already in memory. Same keywords. |
| `.metrics` | A `RouteMetrics` (`total_distance_km`, `ascent_m`, `max_gradient_pct`, …). |
| `.start_ele` / `.finish_ele` | The route's first / last elevation (m) — used for the end labels. |
| `.render()` | Return the SVG string. No arguments — the look is fixed. |

`climbs` is a sequence of `Climb(name, km)`, each labelled over the summit nearest that
kilometre. `start_town` / `finish_town` are the labels at the ends (their elevations come
from the GPX). `name` is kept for filenames/reporting; it is **not** drawn.

### `StageMap`

| Method | Description |
| --- | --- |
| `StageMap.from_file(path, *, start, end, start_label="", end_label="", start_ele=None, finish_ele=None, name=None)` | Parse a `.geojson`. `start`/`end` are `(lon, lat)`. |
| `StageMap.from_geojson(geojson, *, ...)` | Same, from a dict, JSON string, or path in memory. |
| `.render()` | Return the SVG string. No arguments. |

Any FeatureCollection / Feature / (Multi)Polygon works. `start_ele` / `finish_ele` (metres)
are shown in the `START · …M` / `FINISH · …M` labels; pass `profile.start_ele` /
`profile.finish_ele` to keep the two visuals consistent.

The low-level `render_profile_svg(series, *, start_town, finish_town, climbs)` and
`render_map_svg(rings, start, end, name)` are exported too, if you already have a `Series`
or flattened rings.

---

## CLI

```bash
# profile — from a GPX route
stage-profiler profile stage.gpx \
  --start-town Tirano --finish-town Bormio \
  --climb "Mortirolo:55" --climb "Foscagno:140" -o profile.svg
cat stage.gpx | stage-profiler profile - --metrics > profile.svg   # read from stdin

# map — from a country GeoJSON
stage-profiler map ita.geojson --start 10.17 46.22 --end 10.37 46.47 \
  --start-town Tirano --finish-town Bormio --start-ele 440 --finish-ele 1225 -o map.svg
```

`profile` flags: `--start-town`, `--finish-town`, `--climb NAME:KM` (repeatable), `--name`,
`--metrics`. `map` flags: `--start LON LAT`, `--end LON LAT`, `--start-town`,
`--finish-town`, `--start-ele`, `--finish-ele`, `--name`.

---

## Batch roadbook

[`scripts/generate_roadbook.py`](scripts/generate_roadbook.py) turns a set of races into
posters in one pass. Point it at a **manifest** (JSON) — or a folder of `.gpx` files — and
it writes `{stem}-profile` and `{stem}-map` per race, each as an **SVG and a matching PNG**.

PNG rasterisation uses `rsvg-convert` (`brew install librsvg`); without it the script writes
SVG only. Pass `--no-png` to skip PNGs, or `--scale N` to change their resolution (default 2×).

```bash
python scripts/generate_roadbook.py races.example.json          # → build/
python scripts/generate_roadbook.py path/to/gpx-folder/         # a profile for every .gpx
```

The manifest lists races; every path resolves relative to the manifest file:

```json
{
  "output_dir": "build",
  "races": [
    {
      "gpx": "stage-4-course.gpx",
      "name": "Carcassonne — Foix",
      "start_town": "Carcassonne",
      "finish_town": "Foix",
      "climbs": [
        { "name": "Port de Lers", "km": 118 },
        { "name": "Mur de Péguère", "km": 147 }
      ],
      "map": {
        "geojson": "fra.geojson",
        "start": [2.4362, 43.2006],
        "end":   [1.6075, 42.9640]
      }
    }
  ]
}
```

`start`/`end` are optional (they fall back to the GPX endpoints); omit `map` for a
profile-only race. A race that fails is logged and skipped so the rest still render.

---

## Fonts & theming

**Fonts are referenced, not embedded**, so SVGs stay small. Inline the SVG in a page that
loads **Jost** (the single family used across both visuals) and the type renders as designed. Every element carries a class for CSS theming — `sp-*` on the
profile (`sp-line`, `sp-band`, `sp-climb`, `sp-town`, `sp-start`, `sp-finish`, …) and `sm-*`
on the map (`sm-land`, `sm-marker`, `sm-label`, …). Profile elements also carry `sp-climb`,
`sp-leader`, `sp-town`, `sp-ele`, `sp-start`, `sp-finish`, and `sp-dist`.

The palette and type live in [`theme.py`](src/stage_profiler/theme.py). The profile is
**Bauhaus**: steepness is painted in the three primaries (`BAND_COLORS` — blue → yellow → red,
cool to hot) over a bold black line and baseline. The two gradient cut points (**4 %**
moderate, **8 %** steep) live in [`steepness.py`](src/stage_profiler/steepness.py).

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
  geometry.py   distances, metrics, sampled series, interpolation
  steepness.py  segment a route into three steepness bands
  theme.py      the baked-in palette, type, and SVG text helpers
  render.py     the stage-profile SVG
  profile.py    StageProfile + Climb — the profile entry point
  map.py        StageMap — the map entry point (shapely + pyproj)
  cli.py        command-line interface (profile / map subcommands)
scripts/
  generate_roadbook.py   batch profile + map posters from a manifest or GPX folder
tests/          pytest suite
```
