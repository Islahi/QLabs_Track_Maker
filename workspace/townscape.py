"""Townscape/Townscape Lite locked raster reference overlay."""

import json
from pathlib import Path

from config import TOWNSCAPE_REFERENCE_FILENAME


DATA_FILE = Path(__file__).resolve().parents[1] / "data" / "townscape_reference.json"
PROJECT_REFERENCE_FILE = Path(__file__).resolve().parents[1] / TOWNSCAPE_REFERENCE_FILENAME


def load_townscape_reference() -> tuple[dict, str]:
    """Load a project override, otherwise the packaged Townscape reference."""
    for path, source_name in (
        (PROJECT_REFERENCE_FILE, PROJECT_REFERENCE_FILE.name),
        (DATA_FILE, "built-in Townscape road reference"),
    ):
        if not path.exists():
            continue
        try:
            with path.open("r", encoding="utf-8") as handle:
                data = json.load(handle)
            if (
                data.get("format") == "qlabs_workspace_vector_reference"
                and data.get("workspace") == "Townscape"
                and data.get("raster_reference")
            ):
                raster = data.get("raster_reference", {})
                image_file = str(raster.get("image_file", "") or "")
                if image_file:
                    raster_path = (path.parent / image_file).resolve()
                    if raster_path.exists():
                        data["_raster_path"] = str(raster_path)
                return data, source_name
        except (OSError, json.JSONDecodeError, TypeError, ValueError):
            continue
    raise FileNotFoundError("No usable Townscape reference found")
