# QLabs Track Editor — Modular OOP Rewrite

This project is a behavior-preserving modularization of the working v1.0.1
Track Editor. The UI/workflow and QLabs exporter are carried over from v1.0.1;
the source is separated by responsibility.

## Run

```bash
python main.py
```

## Structure

- `main.py` — application entry point
- `config.py` — editor constants/defaults/theme values
- `core/geometry.py` — coordinate conversion, snapping math, IDs
- `workspace/open_road.py` — Open Road reference loading/geometry
- `data/open_road_reference.json` — packaged v1.0.1 Open Road reference
- `items/base.py` — TrackItem abstraction
- `items/roads.py` — straight/curve/junction/end road classes
- `items/vehicles.py` — primary QCar2 start marker
- `items/actors.py` — traffic signs/lights/crosswalk/simple building box
- `items/environment.py` — detailed building and park gallery items
- `items/experiment.py` — people, animals, secondary QCar2, triggers
- `registry.py` — polymorphic item factory
- `ui/scene.py` — QGraphicsScene + endpoint snapping
- `ui/view.py` — adaptive grid, zoom/pan, waypoint display
- `ui/main_window.py` — UI orchestration and inspectors
- `export/qlabs_exporter.py` — standalone QLabs setup source generator
- `legacy/qlabs_track_editor_v10_1.py` — untouched reference copy

## Parity target

The modular version retains the v1.0.1 feature set and now adds reusable building/park scenery:
project scaling; Open Road overlay; weather/time; all six road components;
lane-following guides; QCar2 start and camera; traffic lights/signs/crosswalk;
building box; pedestrian/animal/secondary-QCar experiment actors; waypoint
editing; once/loop/ping-pong movement; triggers; readable identifiers;
save/load compatibility; and standalone QLabs export.

## UI update: compact top tool bar

This variant moves the former left-side palette to a compact top control bar.
Project/workspace/environment controls occupy the first row; roads, traffic,
experiment, QCar and editing tools use symbolic buttons in the second row; the
third row contains BUILD and PARK galleries. Hover any symbol to see its full
tool name.

The right-side selected-object/property inspector is unchanged.

## Building and park gallery

BUILD contains Simple Box, Office, Apartment, Commercial Shop and Stepped Tower.
PARK contains Round Tree, Pine Tree, Bench, Lamp Post, Trash Bin, Planter and
Fountain. These are composite QLabsBasicShape assets and the compact exporter
includes only the asset construction functions actually used by the current map.

A ready-to-load visual check is included at
`examples/building_park_gallery.json`.

## Auto-fill scenery

The **FILL** button in the building/park toolbar row populates the currently
visible open canvas area with decorative buildings, trees, and park furniture.
It avoids road footprints and existing editor objects and uses a capped density
so large/Open Road views cannot create an excessive number of QLabs actors in
one click. Pedestrians, animals, traffic controls, triggers, and QCars are never
auto-created because they affect experiment behaviour.

## Editable canvas and static scenery fill

The editor now has a user-defined **Canvas W × H** design boundary centered on
world origin. Track items are constrained to this area, the grid is drawn only
inside it, and scenery auto-fill operates only inside the same rectangle.

The FILL controls provide **Urban / Suburban / Park** styles, **Low / Medium /
High** density, and a configurable **roadside reserve**. The default 4 m reserve
is measured outward from the road footprint; trees and buildings receive
additional setback. Auto-fill uses only static building/park environment
assets—never QCars, people, animals, triggers, traffic controls, or signs.

Auto-filled composite QLabs BasicShape scenery is exported with dynamics
disabled so it remains static in the simulation.

## Streetscape fill + undo update

- Auto-filled **buildings are restricted to a road-side corridor** instead of
  being scattered across the whole editable canvas. `Road reserve` controls the
  minimum clear verge; `Bldg` controls the maximum distance from the road edge
  where an auto-filled building center may appear.
- Trees and other static park scenery may still use open areas elsewhere in the
  editable canvas.
- `Ctrl+Z` and the Undo toolbar button restore the previous project snapshot for
  common edits including add, move, rotate, duplicate, delete, property edits,
  and scenery auto-fill.
- The stepped tower now exports a front door, multiple glazed window rows, and a
  roof cap so it reads as an occupied building rather than stacked blank blocks.

## Workspace cover platform for outdoor weather

The **COVER** row can export one static `QLabsBasicShape` box over a native
QLabs workspace.  When enabled, every exported road, marking, scenery actor,
experiment actor, and QCar is translated upward to the box **Top Z**, allowing
the custom track to run above the native workspace while retaining that
workspace's supported lighting/weather system.

Published QLabs world footprints used by the editor:

| Workspace | Footprint used by cover |
|---|---:|
| Cityscape | approx. 500 m × 500 m |
| Cityscape Lite | 500 m × 500 m |
| Townscape | approx. 500 m × 500 m |
| Townscape Lite | approx. 500 m × 500 m |
| Open Road | approx. 10 km × 5 km |
| Plane | 20,000 m × 20,000 m |
| Studio | 15 m × 14 m |
| Warehouse | 50 m × 30 m |

Quanser explicitly documents the Outdoor Environment weather tutorial for
**Cityscape**, and Open Road is explicitly documented as including time-of-day
and weather systems. Quanser also notes that not every Open World supports all
environmental features, so other profiles are provided primarily for geometry
coverage and should be tested with the installed QLabs release.

`Top Z` and `Bottom Z` are editor choices, not published workspace heights.
The default Cityscape/Townscape cover top is intentionally high so native map
geometry is likely to remain below the custom driving surface. If native
geometry protrudes through the box in your QLabs release, increase **Top Z**.
Use the COVER fit button to inspect the full platform footprint in the editor.

## Traffic signs and camel

The TRAFFIC toolbar keeps the original QLabs traffic controls as dedicated
items: **Traffic Light**, **Stop Sign**, **Yield Sign**, **Roundabout Sign**, and
**Crosswalk**. Stop, Yield, and Roundabout continue to export through their
native QLabs actor classes.

The adjacent custom-sign selector now contains **only the Plane-validated
custom signs** developed in this project: Front-or-Right, Front-or-Left,
Right Turn, Left Turn, U-Turn, No U-Turn, Right-or-Left, Parking, No Parking,
No Overtaking, Pedestrian Crossing, and speed signs 30/40/50/60/80/100.
The old unvalidated fallback entries (Road Hump, Narrow From Right/Left,
No Horn, Slow, and catalog duplicates of Stop/Roundabout) were removed.

The Animal inspector also includes **Camel**. QLabsAnimal itself documents
Goat, Sheep, and Cow only, so the camel is a low-poly articulated-looking
BasicShape rig parented to one addressable root. It can use the same immediate
or triggered spawn and manual waypoint system as the other experiment animals.

For a quick test, open `examples/traffic_sign_camel_gallery.json` in the editor
or run `examples/traffic_sign_camel_gallery_qlabs.py` in QLabs.

## Plane-validated custom traffic signs

The traffic-sign selector in the top toolbar lets you choose a validated custom
sign before placing it. The exporter has **no generic fallback catalog** now:
every entry shown in that selector maps to a tested BasicShape builder. Native
QLabs Stop, Yield, and Roundabout signs remain available through their separate
toolbar buttons.

## Workspace selector, spline height, and intersection guides

The main **Workspace** selector now exposes Plane/Custom, Open Road, Cityscape,
Cityscape Lite, Townscape, Townscape Lite, Studio, and Warehouse. Selecting a
workspace also aligns the optional COVER profile with that workspace while
leaving the cover itself off until explicitly enabled.

A new **Spline Z** control sets the base Z used by exported spline roads,
markings, guide lines, and track-relative actors when no cover box is active.
Outdoor native workspaces default to **1.0 m** so custom spline geometry is less
likely to be hidden under the native road mesh. Plane defaults to 0.05 m and
Studio/Warehouse to 0.10 m. If the COVER box is enabled, its Top Z overrides
Spline Z and the road surface is lifted 1 cm above the cover to avoid
z-fighting.

Lane-following guides are now supported by **T-Junction** and **4-Way
Intersection** items as well as normal roads and curves. The same guide controls
(position, custom offset, color/RGB, width, solid/dashed style, and project-scale
width) are available in the inspector, saved in project JSON, drawn in the
editor, and exported as QLabs spline lines.

## Open Road width / spline calibration

- Open Road now defaults spline roads, markings, and guide lines to **Z = 1.20 m**.
- New Open Road road components default to **8.4 m** wide, matching the
  user-validated QLabs comparison for one native three-lane carriageway.
  Existing saved roads keep their stored width and can be changed from
  Properties.
- The editor Open Road visual reference now uses **8.4 m per carriageway**
  (**2.8 m per displayed lane**) and a **0.6 m median/barrier band**, for an
  overall visual width of **17.4 m**. These are visual calibration values from
  the QLabs comparison, not surveyed engineering dimensions.
- Road markings are independently switchable in the **ROAD MARKINGS** inspector:
  Edge A, Center line, Edge B, and the Road End bar. Hidden markings are also
  omitted from the generated QLabs setup script.
- A **Median / Barrier Wall** tool is available in the ROAD toolbar. It exports
  as a static collision-enabled concrete BasicShape and straight roads/road ends
  can snap flush to either side of it while endpoint snapping is enabled.

## Open Road overlay calibration and road markings

This build keeps `DEFAULT_ROAD_WIDTH_M = 8.4` from the supplied configuration.
The Open Road *reference overlay* is deliberately wider than a custom 8.4 m
road: it is drawn as three 4.3 m lanes per carriageway plus an approximately
0.5 m centre divider, for an estimated total two-direction reference width of
26.3 m. The overlay remains editor-only and is never exported.

Spline roads, road markings and lane-following guides default to `Z = 1.20 m`
for every workspace unless a saved project overrides the value or a workspace
cover box supplies its own top-Z surface.

Select a road, curve, road end, T-junction or 4-way intersection to open the
**ROAD MARKINGS** inspector. Edge A, Center line, Edge B (and the Road-end bar
where applicable) can each be switched on/off and assigned one of the preset
colors plus either **Solid** or **Dashed** style. The same settings are written
to project JSON and reproduced by the QLabs exporter.

## Cityscape and Townscape documentation maps

Cityscape and Townscape now provide editor reference maps in the same Workspace
reference workflow as Open Road. The packaged raster overlays are taken from the
official Quanser navigation-area documentation images and are editor-only; they
are never exported as QLabs actors.

Quanser documents both worlds as approximately **500 m × 500 m**, centered on
the origin, with ground at **Z = 0 m**. The documented outer navigation boundary
is **400 m × 400 m**. The editor draws that outer boundary as a dashed frame and
also exposes the common coordinates listed by Quanser as optional labeled
reference points.

Important calibration limitation: Quanser does not publish surveyed vector road
centerlines for these two pages. The official top-down image is therefore
centered on the documented origin and mapped across the approximate 500 m ×
500 m world footprint. Treat it as a placement/visual reference rather than a
CAD-accurate road map. The JSON files in `data/` keep this calibration explicit
so it can be refined later without changing the drawing code.

Packaged files:

- `workspace/documentation_maps.py`
- `data/cityscape_reference.json`
- `data/cityscape_nav_area.png`
- `data/townscape_reference.json`
- `data/townscape_nav_area.png`

Official documentation sources are recorded inside each JSON reference file.


## Open Road editor alignment

This build keeps the working calibration supplied by the user:

- default road width: 8.4 m
- Open Road reference lane width: 4.0 m
- three lanes per carriageway
- reference centre divider: 0.25 m
- default spline Z: 1.20 m

The Open Road editor reference is shifted visually down by one 1 m grid block:

```python
OPEN_ROAD_REFERENCE_OFFSET_X_M = 0.0
OPEN_ROAD_REFERENCE_OFFSET_Y_M = -1.0
```

The offset is editor-only and is never exported to QLabs.

## Cityscape and Townscape reference maps

Cityscape and Townscape documentation-derived reference maps are included.
Select either workspace to show its packaged top-down reference, navigation
area and documented reference points. These maps are editor placement aids
and are not exported as actors.
