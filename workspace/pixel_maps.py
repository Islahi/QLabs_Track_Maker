"""Pixel-to-world calibration helpers for documentation workspace maps.

Cityscape/Townscape top-down images are stored as raster references.  Rather
than stretching each image into a square world rectangle, this module maps
source image pixels through an affine pixel->world transform.  That preserves
the image's native aspect ratio and provides the same calibration model used by
the Open Road reference data.
"""

from __future__ import annotations

import math
from typing import Iterable


def _affine(reference: dict) -> tuple[float, float, float, float, float, float]:
    image = reference.get("image", {})
    calibration = image.get("pixel_to_world_affine") or reference.get(
        "calibration", {}
    ).get("pixel_to_world_affine")

    if calibration:
        x = calibration.get("x", [])
        y = calibration.get("y", [])
        if len(x) == 3 and len(y) == 3:
            return (
                float(x[0]), float(x[1]), float(x[2]),
                float(y[0]), float(y[1]), float(y[2]),
            )

    # Backward-compatible fallback for older references that only supplied a
    # world rectangle.  This intentionally preserves their previous behavior.
    world_rect = image.get("world_rect_m", [-250.0, -250.0, 500.0, 500.0])
    min_x, min_y, width_m, height_m = [float(v) for v in world_rect]
    pixel_w = max(1.0, float(image.get("pixel_width", 1.0)))
    pixel_h = max(1.0, float(image.get("pixel_height", 1.0)))

    # Image v increases downward while world Y increases upward.
    sx = width_m / pixel_w
    sy = height_m / pixel_h
    return (
        sx, 0.0, min_x,
        0.0, -sy, min_y + height_m,
    )


def pixel_to_world(reference: dict, u: float, v: float) -> tuple[float, float]:
    """Map one raster pixel coordinate into editor/QLabs XY meters."""
    a, b, c, d, e, f = _affine(reference)
    return (
        a * float(u) + b * float(v) + c,
        d * float(u) + e * float(v) + f,
    )


def pixel_world_corners(reference: dict) -> list[tuple[float, float]]:
    """Return the four image-edge corners expressed in world meters."""
    image = reference.get("image", {})
    width = float(image.get("pixel_width", 1.0))
    height = float(image.get("pixel_height", 1.0))
    return [
        pixel_to_world(reference, 0.0, 0.0),
        pixel_to_world(reference, width, 0.0),
        pixel_to_world(reference, width, height),
        pixel_to_world(reference, 0.0, height),
    ]


def pixel_world_bounds(reference: dict) -> tuple[float, float, float, float]:
    """Return min_x, min_y, max_x, max_y for the mapped raster."""
    corners = pixel_world_corners(reference)
    xs = [point[0] for point in corners]
    ys = [point[1] for point in corners]
    return min(xs), min(ys), max(xs), max(ys)


def pixel_scale_summary(reference: dict) -> tuple[float, float]:
    """Return world meters represented by one +U pixel and one +V pixel."""
    a, b, _c, d, e, _f = _affine(reference)
    return math.hypot(a, d), math.hypot(b, e)


def image_is_axis_aligned(reference: dict, tolerance: float = 1e-9) -> bool:
    """True when U only affects X and V only affects Y.

    The current Cityscape/Townscape baseline is axis aligned.  The JSON format
    still stores a full affine matrix so later anchor calibration can add small
    rotation/shear without changing the data model.
    """
    _a, b, _c, d, _e, _f = _affine(reference)
    return abs(b) <= tolerance and abs(d) <= tolerance
