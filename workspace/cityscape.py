"""Cityscape road-only vector reference overlay."""

import json
from pathlib import Path

from config import CITYSCAPE_REFERENCE_FILENAME


DATA_FILE = (
    Path(__file__).resolve().parents[1]
    / "data"
    / "cityscape_reference.json"
)

PROJECT_REFERENCE_FILE = (
    Path(__file__).resolve().parents[1]
    / CITYSCAPE_REFERENCE_FILENAME
)


def load_cityscape_reference() -> tuple[dict, str]:
    """Load editable project override, otherwise packaged reference."""

    for path, source_name in (
        (PROJECT_REFERENCE_FILE, PROJECT_REFERENCE_FILE.name),
        (DATA_FILE, "built-in Cityscape road reference"),
    ):
        if not path.exists():
            continue

        try:
            with path.open("r", encoding="utf-8") as handle:
                data = json.load(handle)

            if (
                data.get("format")
                == "qlabs_workspace_vector_reference"
                and data.get("workspace") == "Cityscape"
                and (
                    data.get("road_references")
                    or data.get("raster_reference")
                )
            ):
                # Resolve an optional raster relative to the JSON that
                # declares it.  The absolute path is runtime-only and is not
                # written back into project files.
                raster = data.get("raster_reference", {})
                image_file = str(raster.get("image_file", "") or "")
                if image_file:
                    raster_path = (path.parent / image_file).resolve()
                    if raster_path.exists():
                        data["_raster_path"] = str(raster_path)
                return data, source_name
        except (
            OSError,
            json.JSONDecodeError,
            TypeError,
            ValueError,
        ):
            continue

    raise FileNotFoundError(
        "No usable Cityscape vector reference found"
    )
