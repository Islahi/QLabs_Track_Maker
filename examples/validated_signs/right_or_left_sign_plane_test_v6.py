import math
import sys

from qvl.qlabs import QuanserInteractiveLabs
from qvl.basic_shape import QLabsBasicShape


# ================================================================
# Right-or-Left traffic sign - Plane test v6
# ================================================================
# This version matches the reference image more closely: two separate white
# arrows slant down from the top-center area, one to the left and one to the
# right, each with a broad angular head.
# ================================================================

WHITE = [0.98, 0.98, 0.98]
BLUE = [0.09, 0.31, 0.67]
POST_GRAY = [0.55, 0.55, 0.57]

POST_HEIGHT = 2.30
POST_WIDTH = 0.08
POST_BACK_OFFSET = 0.10
PLATE_CENTER_Z = 2.45
OUTER_DIAMETER = 1.22
INNER_DIAMETER = 1.14
PLATE_DEPTH = 0.08
BORDER_FORWARD = 0.008
FACE_OFFSET = 0.060

SYMBOL_SCALE = 0.92
STROKE_WIDTH = 0.060 * SYMBOL_SCALE
STROKE_DEPTH = 0.025
ARROW_HEAD_FILL_LAYERS = 16
SHAFT_SUBDIVISIONS = 8


class ActorNumberAllocator:
    def __init__(self, start=7000):
        self._next = start

    def next(self):
        value = self._next
        self._next += 1
        return value


def spawn_shape(shape, actor_ids, location, rotation, scale, configuration, color,
                roughness=0.25, collisions=False):
    actor_number = actor_ids.next()
    status = shape.spawn_id(
        actorNumber=actor_number,
        location=[float(v) for v in location],
        rotation=[float(v) for v in rotation],
        scale=[float(v) for v in scale],
        configuration=configuration,
        waitForConfirmation=True,
    )
    if status != 0:
        raise RuntimeError(f"Failed to spawn BasicShape actor {actor_number}; status={status}")

    shape.set_material_properties(
        color=list(color), roughness=float(roughness), metallic=False,
        waitForConfirmation=True,
    )
    shape.set_enable_dynamics(False, waitForConfirmation=True)
    shape.set_enable_collisions(bool(collisions), waitForConfirmation=True)


def tangent(heading):
    return [math.cos(heading), math.sin(heading), 0.0]


def left_axis(heading):
    return [math.sin(heading), -math.cos(heading), 0.0]


def vector_cross(a, b):
    return [
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    ]


def rotation_matrix_to_euler_zyx(matrix):
    r00, r01, r02 = matrix[0]
    r10, r11, r12 = matrix[1]
    r20, r21, r22 = matrix[2]
    if abs(r20) < 1.0 - 1e-8:
        pitch = -math.asin(r20)
        roll = math.atan2(r21, r22)
        yaw = math.atan2(r10, r00)
    else:
        pitch = -math.copysign(math.pi / 2.0, r20)
        roll = 0.0
        yaw = math.atan2(-r01, r11)
    return [roll, pitch, yaw]


def logical_to_world(face_origin, heading, point):
    lateral = float(point[0]) * SYMBOL_SCALE
    vertical = float(point[1]) * SYMBOL_SCALE
    n_left = left_axis(heading)
    return [
        face_origin[0] + n_left[0] * lateral,
        face_origin[1] + n_left[1] * lateral,
        face_origin[2] + vertical,
    ]


def segment_rotation(heading, p1, p2):
    du = (float(p2[0]) - float(p1[0])) * SYMBOL_SCALE
    dv = (float(p2[1]) - float(p1[1])) * SYMBOL_SCALE
    length = math.hypot(du, dv)
    if length <= 1e-9:
        return None

    n_left = left_axis(heading)
    face_normal = [-v for v in tangent(heading)]
    x_axis = [n_left[0] * du / length, n_left[1] * du / length, dv / length]
    y_axis = face_normal
    z_axis = vector_cross(x_axis, y_axis)
    matrix = [
        [x_axis[0], y_axis[0], z_axis[0]],
        [x_axis[1], y_axis[1], z_axis[1]],
        [x_axis[2], y_axis[2], z_axis[2]],
    ]
    return rotation_matrix_to_euler_zyx(matrix)


def spawn_face_segment(shape, actor_ids, face_origin, heading, p1, p2,
                       width=STROKE_WIDTH, color=WHITE):
    du = (float(p2[0]) - float(p1[0])) * SYMBOL_SCALE
    dv = (float(p2[1]) - float(p1[1])) * SYMBOL_SCALE
    length = math.hypot(du, dv)
    if length <= 1e-9:
        return
    midpoint = ((float(p1[0]) + float(p2[0])) / 2.0, (float(p1[1]) + float(p2[1])) / 2.0)
    center = logical_to_world(face_origin, heading, midpoint)
    rotation = segment_rotation(heading, p1, p2)
    spawn_shape(
        shape, actor_ids, center, rotation,
        [length * 1.08, STROKE_DEPTH, width],
        QLabsBasicShape.SHAPE_CUBE, color,
        roughness=0.12, collisions=False,
    )


def draw_polyline(shape, actor_ids, face_origin, heading, points,
                  subdivisions=1, width=STROKE_WIDTH, color=WHITE):
    if len(points) < 2:
        return
    for index in range(len(points) - 1):
        p1 = points[index]
        p2 = points[index + 1]
        steps = max(1, int(subdivisions))
        previous = p1
        for step in range(1, steps + 1):
            fraction = step / steps
            current = (
                p1[0] + (p2[0] - p1[0]) * fraction,
                p1[1] + (p2[1] - p1[1]) * fraction,
            )
            spawn_face_segment(shape, actor_ids, face_origin, heading, previous, current,
                               width=width, color=color)
            previous = current


def draw_filled_triangle(shape, actor_ids, face_origin, heading,
                         tip, back_a, back_b, layers=ARROW_HEAD_FILL_LAYERS,
                         color=WHITE):
    layers = max(2, int(layers))
    for index in range(layers):
        fraction = (index + 0.5) / layers
        point_a = (
            back_a[0] + (tip[0] - back_a[0]) * fraction,
            back_a[1] + (tip[1] - back_a[1]) * fraction,
        )
        point_b = (
            back_b[0] + (tip[0] - back_b[0]) * fraction,
            back_b[1] + (tip[1] - back_b[1]) * fraction,
        )
        spawn_face_segment(shape, actor_ids, face_origin, heading, point_a, point_b,
                           width=STROKE_WIDTH * 1.05, color=color)


def _aligned_arrow_geometry(start, shaft_end, head_length=0.19, head_half_width=0.14):
    """Return a shaft end plus a triangular arrowhead aligned to the shaft."""
    dx = shaft_end[0] - start[0]
    dy = shaft_end[1] - start[1]
    length = math.hypot(dx, dy)
    if length <= 1e-9:
        raise ValueError("Arrow shaft must have non-zero length")

    ux = dx / length
    uy = dy / length

    # Continue in the exact same direction to the head tip.
    tip = (
        shaft_end[0] + ux * head_length,
        shaft_end[1] + uy * head_length,
    )

    # Perpendicular vector in the sign plane.
    px = -uy
    py = ux

    back_a = (
        shaft_end[0] + px * head_half_width,
        shaft_end[1] + py * head_half_width,
    )
    back_b = (
        shaft_end[0] - px * head_half_width,
        shaft_end[1] - py * head_half_width,
    )

    return tip, back_a, back_b


def spawn_right_or_left_symbol(shape, actor_ids, face_origin, heading):
    """Two separate diagonal arrows whose heads are aligned with their shafts."""

    # Left arrow: diagonal tail from near the centre down toward the left.
    left_start = (-0.06, 0.24)
    left_shaft_end = (-0.25, 0.05)
    left_tip, left_back_a, left_back_b = _aligned_arrow_geometry(
        left_start,
        left_shaft_end,
        head_length=0.20,
        head_half_width=0.15,
    )

    draw_polyline(
        shape, actor_ids, face_origin, heading,
        [left_start, left_shaft_end],
        subdivisions=SHAFT_SUBDIVISIONS,
        width=STROKE_WIDTH,
    )

    draw_filled_triangle(
        shape, actor_ids, face_origin, heading,
        tip=left_tip,
        back_a=left_back_a,
        back_b=left_back_b,
    )
    draw_polyline(shape, actor_ids, face_origin, heading,
                  [left_back_a, left_tip], subdivisions=6)
    draw_polyline(shape, actor_ids, face_origin, heading,
                  [left_back_b, left_tip], subdivisions=6)

    # Right arrow: exact mirror of the left arrow.
    right_start = (0.06, 0.24)
    right_shaft_end = (0.25, 0.05)
    right_tip, right_back_a, right_back_b = _aligned_arrow_geometry(
        right_start,
        right_shaft_end,
        head_length=0.20,
        head_half_width=0.15,
    )

    draw_polyline(
        shape, actor_ids, face_origin, heading,
        [right_start, right_shaft_end],
        subdivisions=SHAFT_SUBDIVISIONS,
        width=STROKE_WIDTH,
    )

    draw_filled_triangle(
        shape, actor_ids, face_origin, heading,
        tip=right_tip,
        back_a=right_back_a,
        back_b=right_back_b,
    )
    draw_polyline(shape, actor_ids, face_origin, heading,
                  [right_back_a, right_tip], subdivisions=6)
    draw_polyline(shape, actor_ids, face_origin, heading,
                  [right_back_b, right_tip], subdivisions=6)


def spawn_right_or_left_sign(shape, actor_ids, ground_location, heading=0.0):
    ground = [float(v) for v in ground_location]
    t = tangent(heading)

    # Pole behind the plate.
    post_center = [
        ground[0] + t[0] * POST_BACK_OFFSET,
        ground[1] + t[1] * POST_BACK_OFFSET,
        ground[2] + POST_HEIGHT / 2.0,
    ]
    spawn_shape(shape, actor_ids, post_center, [0.0, 0.0, heading],
                [POST_WIDTH, POST_WIDTH, POST_HEIGHT],
                QLabsBasicShape.SHAPE_CUBE, POST_GRAY,
                roughness=0.75, collisions=True)

    plate_center = [ground[0], ground[1], ground[2] + PLATE_CENTER_Z]

    # Thin white border ring effect.
    spawn_shape(shape, actor_ids, plate_center,
                [0.0, math.pi / 2.0, heading],
                [OUTER_DIAMETER, OUTER_DIAMETER, PLATE_DEPTH],
                QLabsBasicShape.SHAPE_CYLINDER, WHITE,
                roughness=0.22, collisions=False)

    inner_center = [
        plate_center[0] - t[0] * BORDER_FORWARD,
        plate_center[1] - t[1] * BORDER_FORWARD,
        plate_center[2],
    ]
    spawn_shape(shape, actor_ids, inner_center,
                [0.0, math.pi / 2.0, heading],
                [INNER_DIAMETER, INNER_DIAMETER, PLATE_DEPTH * 0.88],
                QLabsBasicShape.SHAPE_CYLINDER, BLUE,
                roughness=0.22, collisions=False)

    face_origin = [
        plate_center[0] - t[0] * FACE_OFFSET,
        plate_center[1] - t[1] * FACE_OFFSET,
        plate_center[2],
    ]
    spawn_right_or_left_symbol(shape, actor_ids, face_origin, heading)


def main():
    print("Open the QLabs Plane workspace before running this script.")
    print("This v6 test aligns each diagonal shaft exactly through the center of its arrow head.")

    qlabs = QuanserInteractiveLabs()
    if not qlabs.open("localhost"):
        print("Unable to connect to QLabs.")
        sys.exit(1)

    qlabs.destroy_all_spawned_actors()
    shape = QLabsBasicShape(qlabs)
    actor_ids = ActorNumberAllocator(start=7000)

    spawn_right_or_left_sign(shape, actor_ids, [0.0, 0.0, 0.0], heading=0.0)

    print("Right-or-Left traffic sign v6 created.")


if __name__ == "__main__":
    main()
