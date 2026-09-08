"""Open Road measured/reference overlay data and display geometry."""

import json
import math
from pathlib import Path

from PySide6.QtGui import QPainterPath

from config import OPEN_ROAD_REFERENCE_FILENAME
from core.geometry import world_to_scene

DATA_FILE = Path(__file__).resolve().parents[1] / "data" / "open_road_reference.json"
PROJECT_REFERENCE_FILE = Path(__file__).resolve().parents[1] / OPEN_ROAD_REFERENCE_FILENAME

# Measured logger output is intentionally retained at full resolution in the
# JSON.  The editor builds a much smaller display-only copy at load time so the
# road band and lane-guide offsets remain responsive while zooming/panning.
MEASURED_DISPLAY_SIMPLIFY_TOLERANCE_M = 1.0
MEASURED_LOOP_MIN_DISTANCE_M = 10000.0
MEASURED_LOOP_RETURN_RADIUS_M = 25.0
# Ignore the first few hundred metres when choosing the visual lap seam.
# The logger run began while the QCar was still settling laterally on the
# South straight (about Y=7.24 m) and the returned pass was near Y=6.42 m.
# Moving the seam into the stable overlap prevents the reconstructed road
# edges/lane guides from showing an artificial step at the original start.
MEASURED_LOOP_SEAM_LEAD_IN_M = 200.0


def open_road_reference_file_path() -> Path:
    """Return an optional user-supplied Open Road reference beside main.py."""
    return PROJECT_REFERENCE_FILE


def _built_in_reference() -> dict:
    with DATA_FILE.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _is_measured_reference(data: dict) -> bool:
    road = data.get("road_reference", {})
    kind = str(road.get("kind", "")).lower()
    point_format = [str(value).lower() for value in road.get("point_format", [])]
    return (
        "qlabs_driven" in kind
        or point_format[:3] == ["x", "y", "elevation_z"]
        or bool(road.get("measurement"))
    )


def _first_completed_loop(points: list) -> tuple[list, dict]:
    """Extract the first measured lap using a stable overlap seam.

    The logger may begin before the QCar has fully settled in its lane and it
    may continue into a partial second lap.  Rather than closing the display
    loop at raw sample 0, choose a seam after a short lead-in on the same
    straight and then find the first later return to that point.  This keeps
    the displayed loop faithful to the measured route while avoiding a fake
    lateral step where the two passes meet.

    If no completed lap is detected, the complete recording is returned as an
    open path instead.
    """
    clean = [
        point
        for point in points
        if len(point) >= 2
        and math.isfinite(float(point[0]))
        and math.isfinite(float(point[1]))
    ]
    if len(clean) < 2:
        return clean, {
            "completed_loop_detected": False,
            "closed": False,
            "distance_m": 0.0,
            "return_distance_m": None,
            "start_index": None,
            "end_index": None,
            "seam_lead_in_m": 0.0,
        }

    cumulative = [0.0]
    for index in range(1, len(clean)):
        prev_x = float(clean[index - 1][0])
        prev_y = float(clean[index - 1][1])
        x = float(clean[index][0])
        y = float(clean[index][1])
        cumulative.append(
            cumulative[-1] + math.hypot(x - prev_x, y - prev_y)
        )

    seam_index = 0
    for index, distance_m in enumerate(cumulative):
        if distance_m >= MEASURED_LOOP_SEAM_LEAD_IN_M:
            seam_index = index
            break

    start_x = float(clean[seam_index][0])
    start_y = float(clean[seam_index][1])
    entered_return_zone = False
    best_return = None

    for index in range(seam_index + 1, len(clean)):
        travelled_m = cumulative[index] - cumulative[seam_index]
        if travelled_m < MEASURED_LOOP_MIN_DISTANCE_M:
            continue

        x = float(clean[index][0])
        y = float(clean[index][1])
        return_distance = math.hypot(x - start_x, y - start_y)

        if return_distance <= MEASURED_LOOP_RETURN_RADIUS_M:
            entered_return_zone = True
            if best_return is None or return_distance < best_return[0]:
                best_return = (return_distance, index, travelled_m)
            continue

        if entered_return_zone:
            # The first return encounter has finished; use its closest point.
            break

    if best_return is None:
        distance_m = cumulative[-1] - cumulative[seam_index]
        return clean, {
            "completed_loop_detected": False,
            "closed": False,
            "distance_m": float(distance_m),
            "return_distance_m": None,
            "start_index": int(seam_index),
            "end_index": None,
            "seam_lead_in_m": float(cumulative[seam_index]),
        }

    return_distance, end_index, loop_distance_m = best_return
    return clean[seam_index : end_index + 1], {
        "completed_loop_detected": True,
        "closed": True,
        "distance_m": float(loop_distance_m),
        "return_distance_m": float(return_distance),
        "start_index": int(seam_index),
        "end_index": int(end_index),
        "seam_lead_in_m": float(cumulative[seam_index]),
    }


def _point_segment_distance_sq(point, start, end) -> float:
    px, py = point
    ax, ay = start
    bx, by = end
    dx = bx - ax
    dy = by - ay
    denominator = dx * dx + dy * dy

    if denominator <= 1e-18:
        return (px - ax) ** 2 + (py - ay) ** 2

    t = ((px - ax) * dx + (py - ay) * dy) / denominator
    t = max(0.0, min(1.0, t))
    qx = ax + t * dx
    qy = ay + t * dy
    return (px - qx) ** 2 + (py - qy) ** 2


def _simplify_world_polyline(points: list, tolerance_m: float) -> list:
    """Iterative Ramer-Douglas-Peucker simplification in world XY metres."""
    if len(points) <= 2 or tolerance_m <= 0.0:
        return list(points)

    xy = [(float(point[0]), float(point[1])) for point in points]
    keep = [False] * len(points)
    keep[0] = True
    keep[-1] = True
    stack = [(0, len(points) - 1)]
    tolerance_sq = float(tolerance_m) ** 2

    while stack:
        start_index, end_index = stack.pop()
        if end_index <= start_index + 1:
            continue

        segment_start = xy[start_index]
        segment_end = xy[end_index]
        best_index = None
        best_distance_sq = -1.0

        for index in range(start_index + 1, end_index):
            distance_sq = _point_segment_distance_sq(
                xy[index], segment_start, segment_end
            )
            if distance_sq > best_distance_sq:
                best_distance_sq = distance_sq
                best_index = index

        if best_index is not None and best_distance_sq > tolerance_sq:
            keep[best_index] = True
            stack.append((start_index, best_index))
            stack.append((best_index, end_index))

    return [point for index, point in enumerate(points) if keep[index]]


def _prepare_reference(data: dict) -> dict:
    """Attach a private, display-only Open Road path to loaded reference data."""
    road = data.get("road_reference", {})
    raw_points = road.get("points", [])

    if len(raw_points) < 2:
        data["_display_reference"] = {
            "points": list(raw_points),
            "closed": False,
            "measured": _is_measured_reference(data),
            "raw_point_count": len(raw_points),
            "display_point_count": len(raw_points),
        }
        return data

    if not _is_measured_reference(data):
        data["_display_reference"] = {
            "points": raw_points,
            "closed": bool(road.get("closed", False)),
            "measured": False,
            "raw_point_count": len(raw_points),
            "display_point_count": len(raw_points),
        }
        return data

    lap_points, lap_info = _first_completed_loop(raw_points)
    display_points = _simplify_world_polyline(
        lap_points,
        MEASURED_DISPLAY_SIMPLIFY_TOLERANCE_M,
    )

    # The stable seam samples are already very close.  For display only, snap
    # the final XY exactly onto the first XY so QPainter never draws a tiny
    # diagonal closure across the straight.  Raw measured points/Z remain
    # untouched in road_reference.
    if lap_info["closed"] and len(display_points) >= 2:
        first = list(display_points[0])
        last = list(display_points[-1])
        if len(last) >= 2:
            last[0] = float(first[0])
            last[1] = float(first[1])
            display_points = list(display_points)
            display_points[-1] = last

    data["_display_reference"] = {
        "points": display_points,
        "closed": bool(lap_info["closed"]),
        "measured": True,
        "raw_point_count": len(raw_points),
        "lap_raw_point_count": len(lap_points),
        "display_point_count": len(display_points),
        "simplify_tolerance_m": MEASURED_DISPLAY_SIMPLIFY_TOLERANCE_M,
        "completed_loop_detected": bool(lap_info["completed_loop_detected"]),
        "completed_loop_distance_m": float(lap_info["distance_m"]),
        "return_distance_m": lap_info["return_distance_m"],
        "completed_loop_start_index": lap_info.get("start_index"),
        "completed_loop_end_index": lap_info["end_index"],
        "seam_lead_in_m": lap_info.get("seam_lead_in_m", 0.0),
    }
    return data


def load_open_road_reference() -> tuple[dict, str]:
    """Load optional project reference; otherwise use the packaged reference."""
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
                return _prepare_reference(data), path.name
        except (OSError, json.JSONDecodeError, TypeError, ValueError):
            pass

    return _prepare_reference(_built_in_reference()), "built-in measured reference"


def open_road_display_reference(reference: dict) -> dict:
    """Return the display-optimized road path created by the loader."""
    display = reference.get("_display_reference")
    if isinstance(display, dict) and display.get("points"):
        return display

    road = reference.get("road_reference", {})
    return {
        "points": road.get("points", []),
        "closed": bool(road.get("closed", False)),
        "measured": _is_measured_reference(reference),
        "raw_point_count": len(road.get("points", [])),
        "display_point_count": len(road.get("points", [])),
    }


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

    # A closed display loop may carry an explicit duplicate endpoint after the
    # seam is snapped.  Remove that duplicate before computing vertex normals;
    # otherwise the first/last normal can differ slightly and recreate a seam.
    if (
        closed
        and len(clean) >= 3
        and math.hypot(clean[-1][0] - clean[0][0], clean[-1][1] - clean[0][1])
        <= 1e-6
    ):
        clean = clean[:-1]

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

    points = list(points)
    if (
        closed
        and len(points) >= 3
        and math.hypot(
            float(points[-1][0]) - float(points[0][0]),
            float(points[-1][1]) - float(points[0][1]),
        ) <= 1e-6
    ):
        points = points[:-1]

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
