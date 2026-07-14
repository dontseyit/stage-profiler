# stage-profiler

A roadbook toolkit with two visuals that share **one baked-in design language** — a
segmented steepness-band **stage profile** and a soft **stage map**, both driven by data
(no styling options):

- **`StageProfile`** — turn a `.gpx` route into a **stage-profile SVG** in the manner of
  the official Grand-Tour roadbook: the elevation silhouette filled with the race colour
  **segmented by steepness** (darker tones for steeper gradients) under a bold ink outline,
  categorised climbs over their summits (ink **HC/1–4 badge** ·
  altitude · name, on location rules that run down through the mountain), intermediate
  **sprints** on the route line (each over a rule to the km scale), start/finish towns +
  elevations at the corners bookended by a **départ pennant** and a **checkered finish
  flag**, and a **km scale** along the foot. No header — the route is the chart.
- **`StageMap`** — turn a country **GeoJSON** into a **stage-map SVG**: the outline
  simplified into soft land, with a hollow-green **start** ring and a solid-green **finish**
  dot, each labelled with its town + elevation.

```python
from stage_profiler import StageProfile, Climb

profile = StageProfile.from_file(
    "stage.gpx",
    start_town="Tirano", finish_town="Bormio",
    climbs=[Climb("Mortirolo", 55, "HC"), Climb("Foscagno", 140, "2")],  # name·km·category
    sprints=[88.4],                    # intermediate sprints (km)
    accent="#E4108C",                  # race colour tinting the silhouette (optional)
    length_km=172,                     # clip a long GPX to the real stage length (optional)
)
print(profile.metrics.to_dict())      # {'total_distance_km': 182.2, 'ascent_m': ..., ...}
svg = profile.render()                 # 640×192 (10:3) banner
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
| `StageProfile.from_file(path, *, name=None, start_town="", finish_town="", climbs=(), sprints=(), accent="", length_km=None)` | Parse a `.gpx` file. |
| `StageProfile.from_gpx(text, *, ...)` | Parse GPX XML already in memory. Same keywords. |
| `.metrics` | A `RouteMetrics` (`total_distance_km`, `ascent_m`, `max_gradient_pct`, …). |
| `.start_ele` / `.finish_ele` | The route's first / last elevation (m) — used for the end labels. |
| `.render()` | Return the SVG string. No arguments — the look and the 640×192 (10:3) canvas are fixed; SVG scales losslessly, so size it at display time. |

`climbs` is a sequence of `Climb(name, km, category="", offset=0)`, each labelled over its
summit km with the UCI category (`"HC"`, `"1"`…`"4"`) drawn as the badge — leave it empty
for an uncategorised climb. A name may contain a newline (`\n`) to wrap onto two stacked
lines — handy for long climb names. `offset` nudges just the **label** left (`-`) or right
(`+`) in canvas units while its location rule stays on the summit — use it to pull apart
labels that would otherwise overlap. A climb that tops out at the finish is drawn as a **mountaintop
finish**: its badge sits just below the finish flag (the finish town + elevation already
carry its name and height). `sprints` are intermediate-sprint kilometres, marked on the
route line with a rule down to the km scale. `accent` is the race colour tinting the silhouette (maillot-jaune yellow when
empty). `length_km` clips a route that's longer than the real stage (a neutral start zone
or GPS overrun): the tail is dropped, that point becomes the drawn finish, and the metrics
are recomputed for the shortened stage. `start_town` / `finish_town` are the labels at the
ends (their elevations come from the GPX). `name` is kept for filenames/reporting; it is
**not** drawn.

### `StageMap`

| Method | Description |
| --- | --- |
| `StageMap.from_file(path, *, start, end, start_label="", end_label="", start_ele=None, finish_ele=None, name=None)` | Parse a `.geojson`. `start`/`end` are `(lon, lat)`. |
| `StageMap.from_geojson(geojson, *, ...)` | Same, from a dict, JSON string, or path in memory. |
| `.render()` | Return the SVG string. No arguments. |

Any FeatureCollection / Feature / (Multi)Polygon works. `start_ele` / `finish_ele` (metres)
are shown in the `START · …M` / `FINISH · …M` labels; pass `profile.start_ele` /
`profile.finish_ele` to keep the two visuals consistent.

The low-level `render_profile_svg(series, *, start_town, finish_town, climbs, sprints,
accent)` and `render_map_svg(rings, start, end, name)` are exported too, if you already
have a `Series` or flattened rings — as is `clip_series(series, length_m)`, which does the
`length_km` shortening on a `Series` directly.

---

## CLI

```bash
# profile — from a GPX route
stage-profiler profile stage.gpx \
  --start-town Tirano --finish-town Bormio \
  --climb "Mortirolo:55:HC" --climb "Foscagno:140:2" \
  --sprint 88.4 --accent "#E4108C" -o profile.svg
cat stage.gpx | stage-profiler profile - --metrics > profile.svg   # read from stdin

# map — from a country GeoJSON
stage-profiler map ita.geojson --start 10.17 46.22 --end 10.37 46.47 \
  --start-town Tirano --finish-town Bormio --start-ele 440 --finish-ele 1225 -o map.svg
```

`profile` flags: `--start-town`, `--finish-town`, `--climb NAME:KM[:CAT]` (repeatable,
CAT = `HC`/`1`–`4`), `--sprint KM` (repeatable), `--accent HEX`, `--length KM` (clip the
route to this length), `--name`, `--metrics`. `map` flags: `--start LON LAT`,
`--end LON LAT`, `--start-town`, `--finish-town`, `--start-ele`, `--finish-ele`, `--name`.

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
      "accent": "#E4002B",
      "sprints": [88.4],
      "length_km": 172,
      "climbs": [
        { "name": "Port de Lers", "km": 118, "category": "1" },
        { "name": "Mur de Péguère", "km": 147, "category": "2", "offset": -30 }
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

`accent`, `sprints`, `length_km` and each climb's `category` / `offset` are optional, like
`start`/`end` (which fall back to the GPX endpoints); omit `map` for a profile-only race.
A climb's `offset` shifts its label sideways (canvas units, `-` left / `+` right) to avoid
overlaps, leaving its location rule on the summit.
`length_km` clips a route longer than the real stage to that distance (the drawn finish).
A race that fails is logged and skipped so the rest still render.

---

## Fonts & theming

**Fonts are referenced, not embedded**, so SVGs stay small. Inline the SVG in a page that
loads **Jost** (the single family used across both visuals) and the type renders as
designed. Every element carries a class for CSS theming — `sp-*` on the profile
(`sp-fill`, `sp-band`, `sp-line`, `sp-climb`, `sp-cat`, `sp-sprint`, `sp-leader`, `sp-scale`,
`sp-town`, `sp-ele`, `sp-dist`, `sp-start`, `sp-finish`, …) and `sm-*` on the map (`sm-land`,
`sm-marker`, `sm-label`, …).

The palette and type live in [`theme.py`](src/stage_profiler/theme.py). The profile is
the **printed roadbook**: the silhouette wears the race `accent` (default maillot-jaune
`ACCENT`), segmented by steepness into the three [`BAND_OPACITY`](src/stage_profiler/theme.py)
tones — darker for steeper — under a bold ink outline; the climb badges, rules and type
stay ink so any accent works. The steepness cut points (**4 %** moderate, **8 %** steep)
live in [`steepness.py`](src/stage_profiler/steepness.py). The look is fixed by design —
restyle via the CSS classes, or fork `theme.py`.

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
