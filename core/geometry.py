"""Coordinate, snapping, angle, and identifier helpers."""

import math
import uuid

from PySide6.QtCore import QPointF

from config import PIXELS_PER_METER, SNAP_HEADING_TOLERANCE_DEG

def scene_to_world(scene_pos: QPointF) -> tuple[float, float]:
    """Convert Qt scene coordinates to editor/QLabs-style XY meters."""
    x_m = scene_pos.x() / PIXELS_PER_METER
    y_m = -scene_pos.y() / PIXELS_PER_METER
    return x_m, y_m

def world_to_scene(x_m: float, y_m: float) -> QPointF:
    """Convert editor/QLabs-style XY meters to Qt scene coordinates."""
    return QPointF(
        x_m * PIXELS_PER_METER,
        -y_m * PIXELS_PER_METER,
    )

def snap_value(value: float, step: float) -> float:
    return round(value / step) * step

def normalize_angle(degrees: float) -> float:
    angle = degrees % 360.0
    if math.isclose(angle, 360.0):
        angle = 0.0
    return angle

def shortest_angle_difference(a_deg: float, b_deg: float) -> float:
    """Return signed shortest angle difference a-b in [-180, 180)."""
    return (a_deg - b_deg + 180.0) % 360.0 - 180.0

def endpoints_face_each_other(heading_a: float, heading_b: float) -> bool:
    """True when endpoint outward headings are approximately opposite."""
    difference = abs(shortest_angle_difference(heading_a, heading_b))
    return abs(180.0 - difference) <= SNAP_HEADING_TOLERANCE_DEG

def point_distance(a: QPointF, b: QPointF) -> float:
    return math.hypot(a.x() - b.x(), a.y() - b.y())

def make_object_id() -> str:
    return uuid.uuid4().hex[:12]
