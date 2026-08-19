"""Documentation-derived raster reference maps for compact QLabs workspaces.

These overlays are editor placement aids only. Quanser publishes world size,
navigation-area size, selected coordinates, and top-down navigation images for
Cityscape and Townscape, but not surveyed vector road-centerline geometry.
"""

import json
from pathlib import Path


DATA_DIR = Path(__file__).resolve().parents[1] / "data"
PROJECT_DIR = Path(__file__).resolve().parents[1]

REFERENCE_FILES = {
    "cityscape": "cityscape_reference.json",
    "townscape": "townscape_reference.json",
}


def _reference_path(mode: str, project: bool = False) -> Path:
    filename = REFERENCE_FILES[str(mode)]
    return (PROJECT_DIR if project else DATA_DIR) / filename


def load_documentation_workspace_reference(mode: str) -> tuple[dict, str]:
    """Load an optional project override, otherwise the packaged reference."""
    mode = str(mode)
    if mode not in REFERENCE_FILES:
        raise KeyError(f"No documentation map reference for workspace mode {mode!r}")

    project_path = _reference_path(mode, project=True)
    for path, source_name in (
        (project_path, project_path.name),
        (_reference_path(mode, project=False), "built-in documentation reference"),
    ):
        if not path.exists():
            continue
        try:
            with path.open("r", encoding="utf-8") as handle:
                data = json.load(handle)
            if (
                data.get("format") == "qlabs_workspace_raster_reference"
                and str(data.get("mode", "")) == mode
                and data.get("image", {}).get("filename")
                and data.get("image", {}).get("world_rect_m")
            ):
                data["_reference_json_path"] = str(path)
                return data, source_name
        except (OSError, json.JSONDecodeError, TypeError, ValueError):
            continue

    raise FileNotFoundError(f"No usable {mode} documentation reference found")


def reference_image_path(reference: dict) -> Path:
    """Resolve the image stored beside the reference JSON."""
    filename = str(reference.get("image", {}).get("filename", ""))
    json_path = Path(str(reference.get("_reference_json_path", "")))
    if json_path.exists():
        candidate = json_path.parent / filename
        if candidate.exists():
            return candidate
    return DATA_DIR / filename
