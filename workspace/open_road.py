"""Open Road documentation-derived reference overlay data and geometry."""

import json
import math
from pathlib import Path

from PySide6.QtGui import QPainterPath

from config import OPEN_ROAD_REFERENCE_FILENAME
from core.geometry import world_to_scene

DATA_FILE = Path(__file__).resolve().parents[1] / "data" / "open_road_reference.json"
PROJECT_REFERENCE_FILE = Path(__file__).resolve().parents[1] / OPEN_ROAD_REFERENCE_FILENAME

def open_road_reference_file_path() -> Path:
    """Return an optional user-supplied Open Road reference beside main.py."""
    return PROJECT_REFERENCE_FILE


def _built_in_reference() -> dict:
    with DATA_FILE.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def load_open_road_reference() -> tuple[dict, str]:
    """Load optional project reference; otherwise use packaged v1.0.1 data."""
    path = open_road_reference_file_path()
    if path.exists():
        try:
            with path.open("r", encoding="utf-8") as handle:
                data = json.load(handle)
            if (
                data.get("format") == "qlabs_workspace_reference"
                and data.get("workspace") == "Open Road"
                and data.get("road_reference", {}).get("points")
            ):
                return data, path.name
        except (OSError, json.JSONDecodeError, TypeError, ValueError):
            pass

    return _built_in_reference(), "built-in reference"


def _offset_world_polyline(
    points: list,
    offset_m: float,
    closed: bool = False,
) -> list[tuple[float, float]]:
    """Return a simple normal-offset copy of a world-XY polyline.

    This is used only to visualize approximate Open Road lane boundaries.
    It is intentionally not exported and should not be treated as surveyed
    road geometry.
    """
    clean = [
        (float(point[0]), float(point[1]))
        for point in points
        if len(point) >= 2
    ]

    count = len(clean)
    if count < 2:
        return clean

    result = []

    for index, (x, y) in enumerate(clean):
        if closed:
            prev_x, prev_y = clean[(index - 1) % count]
            next_x, next_y = clean[(index + 1) % count]
        elif index == 0:
            prev_x, prev_y = clean[index]
            next_x, next_y = clean[index + 1]
        elif index == count - 1:
            prev_x, prev_y = clean[index - 1]
            next_x, next_y = clean[index]
        else:
            prev_x, prev_y = clean[index - 1]
            next_x, next_y = clean[index + 1]

        tangent_x = next_x - prev_x
        tangent_y = next_y - prev_y
        length = math.hypot(tangent_x, tangent_y)

        if length <= 1e-9:
            result.append((x, y))
            continue

        # Left-hand unit normal in world XY.
        normal_x = -tangent_y / length
        normal_y = tangent_x / length

        result.append(
            (
                x + normal_x * float(offset_m),
                y + normal_y * float(offset_m),
            )
        )

    return result

def _world_polyline_path(
    points: list,
    closed: bool = False,
) -> QPainterPath:
    """Create a QPainterPath from world-XY coordinates."""
    path = QPainterPath()

    if not points:
        return path

    first = world_to_scene(
        float(points[0][0]),
        float(points[0][1]),
    )
    path.moveTo(first)

    for point in points[1:]:
        path.lineTo(
            world_to_scene(
                float(point[0]),
                float(point[1]),
            )
        )

    if closed:
        path.closeSubpath()

    return path
