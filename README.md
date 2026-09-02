## Cover X/Y customization — v2.7

The optional **Cover / Workspace box** can now be customized in all three axes. In addition to **Top Z** and **Bottom Z**, the toolbar exposes **Center X**, **Center Y**, **Size X**, and **Size Y**. Workspace profiles still provide convenient defaults, but the cover can be translated or resized independently before export. Existing project JSON files remain compatible; missing X/Y overrides fall back to the selected workspace profile.

# QLabs Track Editor

A desktop visual editor for designing road networks, placing actors and scenery, and exporting runnable Python setup scripts for **Quanser Interactive Labs (QLabs)**.

The editor provides a 2-D, meter-based canvas with snapping, calibrated workspace references, object properties, project save/load, and a standalone QLabs exporter. It is intended to make repeatable QLabs scene construction faster than positioning every actor manually in code.

> **Status:** active development (`v2.0.0-dev`). Project files and generated scripts should be reviewed before use in important experiments.

## Features

- Build roads from straight sections, 45°/90° curves, intersections, T-junctions, road ends, and median walls.
- Sketch CAD-style Line, three-point Arc, and Circle guides, connect them at endpoints or real intersections, then generate seamless road surfaces. Two-guide corners receive automatic circular fillets, while crossing roads overlap directly without separate junction objects.
- Draw connected continuous roads by clicking an arbitrary sequence of control nodes, then reshape them directly on the canvas.
- Configure 1–12 total lanes while preserving per-lane width, plus road markings, colors, line styles, and component transforms.
- Place traffic lights, road signs, size-adjustable crosswalks, pedestrians, animals, QCar2 actors, and trigger zones.
- Add buildings, trees, benches, lamps, bins, planters, fountains, and other static scenery, with mouse-resizable footprints.
- Automatically fill the whole canvas—or brush-select a rectangular area—with urban, suburban, or park scenery while preserving a roadside reserve.
- Create manual movement paths for supported actors without relying on a QLabs navigation mesh.
- Resize CAD road geometry directly with orange mouse handles; right-click a handle for exact position/radius and line-constraint controls. Generation removes the construction guides and leaves editable continuous roads with cyan point handles and right-click insert/delete controls.
- Snap guide endpoints to guide connections, circle perimeters, and any point along a road centerline. Use automatic horizontal/vertical line constraints, an adaptive grid, duplication, rotation, deletion, and undo.
- Trim unwanted guide sections between crossings; trimming a circle between two crossings converts the retained geometry to an editable arc, including half-circle layouts.
- Import movable and resizable reference images for manual tracing.
- Save complete editor projects as JSON and reopen them later.
- Export a standalone Python script that connects to QLabs and builds the configured scene.
- Switch between system, light, and dark application themes.

## Supported workspaces

| Editor selection | QLabs workspace | Reference behavior |
| --- | --- | --- |
| Plane / Custom | Plane | Freeform meter-based canvas |
| Open Road | OpenRoad | Large native-road reference overlay |
| Cityscape | Cityscape | Calibrated map and automatic canvas fit |
| Cityscape Lite | CityscapeLite | Shares the calibrated Cityscape map |
| Townscape | Townscape | Calibrated map and automatic canvas fit |
| Townscape Lite | TownscapeLite | Shares the calibrated Townscape map |
| Studio | Studio | Indoor workspace profile |
| Warehouse | Warehouse | Indoor workspace profile |

Workspace reference overlays are editor-only placement guides. They are not exported as road geometry.

## Requirements

### Editor

- Python 3.10 or newer
- [PySide6](https://pypi.org/project/PySide6/)

### Running exported scenes

- A working Quanser Interactive Labs installation
- The Quanser QLabs Python libraries (`qvl`) available in the environment used to run the exported script
- The matching QLabs workspace open before executing the generated script

The editor itself does not need QLabs to be running. QLabs is required only when executing an exported setup script.

## Quick start

Clone the repository and enter it:

```bash
git clone https://github.com/Islahi/QLabs_Track_Maker.git
cd QLabs_Track_Maker
```

Create and activate a virtual environment:

```bash
python -m venv .venv
```

Windows PowerShell:

```powershell
.\.venv\Scripts\Activate.ps1
```

macOS/Linux:

```bash
source .venv/bin/activate
```

Install the editor dependency and launch the application:

```bash
python -m pip install PySide6
python main.py
```

## Typical workflow

1. Open the **Setup** tab and select the project scale, canvas size, and target QLabs workspace.
2. Adjust **Spline Z** if the generated road surface must sit above native workspace geometry. The current native-workspace defaults are **Plane 0.20 m**, **Cityscape/Cityscape Lite 0.50 m**, **Townscape/Townscape Lite 0.50 m**, and **Open Road 1.20 m**. These are editor/export defaults and can be tuned for your QLabs installation.
3. Use **Build → Sketch** to draw a **Line** (two clicks), **Arc** (start, point on arc, end), or **Circle** (center, radius). The selected sketch tool remains active after each shape so connected lines can be drawn without repeatedly choosing it. Endpoints snap to compatible guide endpoints, circle perimeters, and the nearest point along an existing road centerline. Green nodes show actual guide intersections. Use **Trim** and click the unwanted section between crossings to remove excess construction geometry or turn a crossed circle into an arc. Select a guide and drag its orange handles to resize it, or right-click a handle for precise editing. Click **Generate Road** to merge degree-two connections with automatic tangent fillets and remove the construction guides. The resulting continuous roads remain editable with cyan nodes.
   The original continuous-road tool remains available: left-click nodes; press **Enter** or right-click to finish, **Backspace** to remove the latest node, or **Esc** to cancel. Select a completed continuous road to drag its cyan nodes, insert/remove nodes, reverse its direction, or enable smooth corners.
4. Use **Scenery** to place objects manually, fill the entire editable canvas, or activate the **Environment Brush** and drag one or more rectangular fill areas. The brush stays active until right-click or `Esc`. Select a scenery object and drag its cyan corner handle to resize it uniformly; the exact scale remains available in the inspector.
5. Select a road and set **Lanes** in the inspector. This is the total lane count; changing it preserves the current per-lane width and resizes the road. If a road is selected when a crosswalk is added, the crosswalk span defaults to that road's per-lane width. Crosswalk span and depth can then be edited in **Properties** or with its cyan corner handle.
6. Save the editable project with **File → Save**. Projects use the `.json` format.
7. Choose **File → Export QLabs Setup** to generate a standalone `.py` file.
8. Open the selected workspace in QLabs, then run the exported Python file in an environment with `qvl` installed.

The generated script connects to QLabs, spawns the configured scene, starts QCar2 real-time support when required, and remains active while movement or trigger monitoring is needed.

## Keyboard shortcuts

| Action | Shortcut |
| --- | --- |
| New project | `Ctrl+N` |
| Open project | `Ctrl+O` |
| Save project | `Ctrl+S` |
| Save as | `Ctrl+Shift+S` |
| Import reference image | `Ctrl+I` |
| Export QLabs setup | `Ctrl+E` |
| Undo | `Ctrl+Z` |
| Duplicate selected | `Ctrl+D` |
| Rotate selected forward | `R` |
| Rotate selected backward | `Shift+R` |
| Delete selected | `Delete` |

Mouse-wheel zoom and middle-button panning are available in the graphics view. Objects can be selected and moved directly on the canvas.

The application starts maximized. The Inspector is a resizable dock with vertical and horizontal scrolling, and each top toolbar page scrolls horizontally when the window is too narrow to show every command.

## Project and export formats

Editor projects are JSON files containing:

- project scale and canvas dimensions;
- selected workspace and spline height;
- environment weather and time settings;
- optional workspace-cover configuration with editable Center X/Y, Size X/Y, Top Z, and Bottom Z;
- scenery-fill settings; and
- serialized roads, actors, triggers, paths, and scenery objects.

Exported files are standalone Python source files. The calibrated reference rasters and imported tracing images are not embedded as QLabs road actors.

## Repository structure

```text
QLabs_Track_Maker/
├── main.py                  # Application entry point
├── config.py                # Editor defaults and shared constants
├── registry.py              # Object creation/serialization registry
├── core/                    # Geometry and traffic-sign data
├── data/                    # Calibrated workspace references
├── export/                  # QLabs Python setup generator
├── items/                   # Roads, actors, scenery, and scene items
├── services/                # Undo and scenery-fill services
├── tools/                   # Workspace calibration/validation utilities
├── ui/                      # Main window, toolbar, view, icons, and themes
└── workspace/               # Workspace profiles and reference loaders
```

## Workspace calibration notes

Cityscape/Cityscape Lite and Townscape/Townscape Lite use calibrated visual references derived from QLabs top-down captures. The Townscape calibration uses four published reference locations:

- Open World Origin: `(0.000, 0.000)`
- Car Spawn Spot: `(0.000, -1.300)`
- Road Parking 1: `(-13.093, -7.572)`
- Road Parking 2: `(-18.078, -2.879)`

The four-marker Townscape fit produced an RMS residual of **0.0168 m** and a maximum residual of **0.0240 m** at those calibration points. These values measure agreement at the markers; they do not guarantee survey-grade accuracy across every road edge. Revalidate the references after major QLabs workspace, asset, or camera changes.

### Native workspace track-base defaults

| Workspace | Default Spline / Track Base Z |
| --- | ---: |
| Plane / Custom | 0.20 m |
| Cityscape / Cityscape Lite | 0.50 m |
| Townscape / Townscape Lite | 0.50 m |
| Open Road | 1.20 m |

`TRACK_BASE_Z` in an exported setup is derived from the selected workspace's saved **Spline Z** (or from the workspace-cover **Top Z** when the cover is enabled). The QCar is intentionally spawned above that surface (`TRACK_BASE_Z + 2.0 * scale`) and allowed to settle, so the table above is the **track base**, not the literal initial QCar center Z.

## Known considerations

- Workspace geometry and actor APIs can vary between QLabs releases.
- Weather support depends on the selected workspace and QLabs version.
- Native surfaces may require adjustment of **Spline Z** or the optional workspace cover.
- Auto-generated scenery and movement paths should be inspected before running an experiment.
- Keep project JSON files alongside any imported reference images needed for future editing.

## Development checks

Run a syntax check without launching the GUI:

```bash
python -m compileall main.py config.py registry.py core export items services ui workspace
```

For a clean repository, Python bytecode caches (`__pycache__`) should normally be ignored rather than committed.
