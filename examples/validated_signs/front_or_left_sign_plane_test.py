import math
import sys

from qvl.qlabs import QuanserInteractiveLabs
from qvl.basic_shape import QLabsBasicShape


# ================================================================
# Front-or-Left traffic sign - Plane test
# ================================================================
# Mirrors the approved Front-or-Right sign geometry so the curved branch
# exits to the left while preserving the same plate, pole, stroke, and
# arrowhead construction rules.
# ================================================================


WHITE = [0.98, 0.98, 0.98]
BLUE = [0.06, 0.36, 0.78]
POST_GRAY = [0.55, 0.55, 0.57]

POST_HEIGHT = 2.30
POST_WIDTH = 0.08
POST_BACK_OFFSET = 0.10
PLATE_CENTER_Z = 2.45
PLATE_DIAMETER = 1.20
PLATE_DEPTH = 0.08

# Approved symbol geometry, scaled to the circular plate.
SYMBOL_SCALE = 0.92
STROKE_WIDTH = 0.055 * SYMBOL_SCALE
STROKE_DEPTH = 0.025
FACE_OFFSET = 0.060

ARC_SEGMENTS = 20
ARROW_HEAD_BOXES_PER_SIDE = 6
ARROW_HEAD_FILL_LAYERS = 14


class ActorNumberAllocator:
    def __init__(self, start=7000):
        self._next = start

    def next(self):
        value = self._next
        self._next += 1
        return value


def spawn_shape(
    shape,
    actor_ids,
    location,
    rotation,
    scale,
    configuration,
    color,
    roughness=0.25,
    collisions=False,
):
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
        raise RuntimeError(
            f"Failed to spawn BasicShape actor {actor_number}; status={status}"
        )

    shape.set_material_properties(
        color=list(color),
        roughness=float(roughness),
        metallic=False,
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
    """Convert a 3x3 rotation matrix to QLabs [roll, pitch, yaw]."""

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
    """Map logical (lateral, vertical) symbol coordinates to the sign face."""

    lateral = float(point[0]) * SYMBOL_SCALE
    vertical = float(point[1]) * SYMBOL_SCALE
    n_left = left_axis(heading)

    return [
        face_origin[0] + n_left[0] * lateral,
        face_origin[1] + n_left[1] * lateral,
        face_origin[2] + vertical,
    ]


def segment_rotation(heading, p1, p2):
    """Return a full 3-D rotation that keeps the box flat on the sign face."""

    du = (float(p2[0]) - float(p1[0])) * SYMBOL_SCALE
    dv = (float(p2[1]) - float(p1[1])) * SYMBOL_SCALE
    length = math.hypot(du, dv)

    if length <= 1e-9:
        return None

    n_left = left_axis(heading)
    face_normal = [-v for v in tangent(heading)]

    x_axis = [
        n_left[0] * du / length,
        n_left[1] * du / length,
        dv / length,
    ]
    y_axis = face_normal
    z_axis = vector_cross(x_axis, y_axis)

    matrix = [
        [x_axis[0], y_axis[0], z_axis[0]],
        [x_axis[1], y_axis[1], z_axis[1]],
        [x_axis[2], y_axis[2], z_axis[2]],
    ]

    return rotation_matrix_to_euler_zyx(matrix)


def spawn_face_segment(
    shape,
    actor_ids,
    face_origin,
    heading,
    p1,
    p2,
    width=STROKE_WIDTH,
):
    """Spawn one approved ground-test segment on the vertical sign face."""

    du = (float(p2[0]) - float(p1[0])) * SYMBOL_SCALE
    dv = (float(p2[1]) - float(p1[1])) * SYMBOL_SCALE
    length = math.hypot(du, dv)

    if length <= 1e-9:
        return

    midpoint = (
        (float(p1[0]) + float(p2[0])) / 2.0,
        (float(p1[1]) + float(p2[1])) / 2.0,
    )

    center = logical_to_world(face_origin, heading, midpoint)
    rotation = segment_rotation(heading, p1, p2)

    spawn_shape(
        shape=shape,
        actor_ids=actor_ids,
        location=center,
        rotation=rotation,
        scale=[
            length * 1.10,
            STROKE_DEPTH,
            width,
        ],
        configuration=QLabsBasicShape.SHAPE_CUBE,
        color=WHITE,
        roughness=0.12,
        collisions=False,
    )


def draw_polyline(
    shape,
    actor_ids,
    face_origin,
    heading,
    points,
    subdivisions=1,
    width=STROKE_WIDTH,
):
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

            spawn_face_segment(
                shape,
                actor_ids,
                face_origin,
                heading,
                previous,
                current,
                width=width,
            )

            previous = current


def arc_points(
    center_x,
    center_y,
    radius,
    start_deg,
    end_deg,
    segments,
):
    points = []

    for index in range(segments + 1):
        fraction = index / segments
        angle_deg = start_deg + (end_deg - start_deg) * fraction
        angle = math.radians(angle_deg)

        points.append(
            (
                center_x + radius * math.cos(angle),
                center_y + radius * math.sin(angle),
            )
        )

    return points


def draw_filled_triangle(
    shape,
    actor_ids,
    face_origin,
    heading,
    tip,
    back_a,
    back_b,
    layers=ARROW_HEAD_FILL_LAYERS,
):
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

        spawn_face_segment(
            shape,
            actor_ids,
            face_origin,
            heading,
            point_a,
            point_b,
            width=STROKE_WIDTH * 1.05,
        )


def draw_arrow_head(
    shape,
    actor_ids,
    face_origin,
    heading,
    tip,
    back_a,
    back_b,
    boxes_per_side=ARROW_HEAD_BOXES_PER_SIDE,
):
    draw_filled_triangle(
        shape,
        actor_ids,
        face_origin,
        heading,
        tip,
        back_a,
        back_b,
    )

    draw_polyline(
        shape,
        actor_ids,
        face_origin,
        heading,
        [back_a, tip],
        subdivisions=boxes_per_side,
    )

    draw_polyline(
        shape,
        actor_ids,
        face_origin,
        heading,
        [back_b, tip],
        subdivisions=boxes_per_side,
    )


def mirror_point(point):
    return (-float(point[0]), float(point[1]))


def spawn_front_or_left_symbol(shape, actor_ids, face_origin, heading):
    """Mirror of the approved Front-or-Right symbol."""

    stem = [
        (0.00, -0.34),
        (0.00, -0.22),
        (0.00, -0.10),
        (0.00, 0.02),
        (0.00, 0.14),
        (0.00, 0.26),
        (0.00, 0.34),
    ]

    draw_polyline(shape, actor_ids, face_origin, heading, stem)

    draw_arrow_head(
        shape,
        actor_ids,
        face_origin,
        heading,
        tip=(0.00, 0.46),
        back_a=(-0.13, 0.31),
        back_b=(0.13, 0.31),
    )

    # Mirror the approved right-turn branch to the left.
    branch_arc = [
        mirror_point(point)
        for point in arc_points(
            center_x=0.22,
            center_y=-0.03,
            radius=0.22,
            start_deg=180.0,
            end_deg=90.0,
            segments=ARC_SEGMENTS,
        )
    ]

    draw_polyline(
        shape,
        actor_ids,
        face_origin,
        heading,
        branch_arc,
    )

    arc_end = branch_arc[-1]
    branch_end = (-0.42, 0.19)

    draw_polyline(
        shape,
        actor_ids,
        face_origin,
        heading,
        [arc_end, branch_end],
        subdivisions=4,
    )

    draw_arrow_head(
        shape,
        actor_ids,
        face_origin,
        heading,
        tip=(-0.54, 0.19),
        back_a=(-0.39, 0.32),
        back_b=(-0.39, 0.06),
    )


def spawn_front_or_left_sign(
    shape,
    actor_ids,
    ground_location,
    heading=0.0,
):
    ground = [float(v) for v in ground_location]

    t = tangent(heading)

    post_center = [
        ground[0] + t[0] * POST_BACK_OFFSET,
        ground[1] + t[1] * POST_BACK_OFFSET,
        ground[2] + POST_HEIGHT / 2.0,
    ]

    spawn_shape(
        shape,
        actor_ids,
        location=post_center,
        rotation=[0.0, 0.0, heading],
        scale=[POST_WIDTH, POST_WIDTH, POST_HEIGHT],
        configuration=QLabsBasicShape.SHAPE_CUBE,
        color=POST_GRAY,
        roughness=0.75,
        collisions=True,
    )

    plate_center = [
        ground[0],
        ground[1],
        ground[2] + PLATE_CENTER_Z,
    ]

    spawn_shape(
        shape,
        actor_ids,
        location=plate_center,
        rotation=[0.0, math.pi / 2.0, heading],
        scale=[PLATE_DIAMETER, PLATE_DIAMETER, PLATE_DEPTH],
        configuration=QLabsBasicShape.SHAPE_CYLINDER,
        color=BLUE,
        roughness=0.22,
        collisions=False,
    )

    face_origin = [
        plate_center[0] - t[0] * FACE_OFFSET,
        plate_center[1] - t[1] * FACE_OFFSET,
        plate_center[2],
    ]

    spawn_front_or_left_symbol(
        shape,
        actor_ids,
        face_origin,
        heading,
    )


def main():
    print("Open the QLabs Plane workspace before running this script.")
    print("This test mirrors the approved Front-or-Right symbol to create Front-or-Left.")

    qlabs = QuanserInteractiveLabs()

    if not qlabs.open("localhost"):
        print("Unable to connect to QLabs.")
        sys.exit(1)

    qlabs.destroy_all_spawned_actors()

    shape = QLabsBasicShape(qlabs)
    actor_ids = ActorNumberAllocator(start=7000)

    spawn_front_or_left_sign(
        shape,
        actor_ids,
        ground_location=[0.0, 0.0, 0.0],
        heading=0.0,
    )

    print("Front-or-Left traffic sign created.")
    print(f"Arc segments: {ARC_SEGMENTS}")
    print(f"Arrow fill layers: {ARROW_HEAD_FILL_LAYERS}")


if __name__ == "__main__":
    main()
