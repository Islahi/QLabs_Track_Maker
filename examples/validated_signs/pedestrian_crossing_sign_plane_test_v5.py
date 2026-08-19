import math
import sys

from qvl.qlabs import QuanserInteractiveLabs
from qvl.basic_shape import QLabsBasicShape


# ================================================================
# Pedestrian Crossing warning sign - Plane test
# ================================================================
# Reference style:
#   - triangular warning sign
#   - white face with thick red border
#   - black pedestrian figure
#   - black zebra crossing stripes
#
# The plate is built directly from BasicShape parts on a vertical sign face.
# ================================================================


WHITE = [0.98, 0.98, 0.98]
RED = [0.93, 0.12, 0.12]
BLACK = [0.05, 0.05, 0.06]
POST_GRAY = [0.55, 0.55, 0.57]

POST_HEIGHT = 2.30
POST_WIDTH = 0.08
POST_BACK_OFFSET = 0.10

PLATE_CENTER_Z = 2.45

# Triangle geometry in sign-face logical coordinates.
TOP_POINT = (0.0, 0.64)
LEFT_POINT = (-0.58, -0.38)
RIGHT_POINT = (0.58, -0.38)

TRIANGLE_DEPTH = 0.08
FACE_FORWARD = 0.052
PLATE_FILL_FORWARD = 0.000
BORDER_FORWARD = 0.010
SYMBOL_FORWARD = 0.028

BORDER_WIDTH = 0.12
FILL_ROWS = 44

FIGURE_STROKE = 0.070
ARM_STROKE = 0.050
LEG_STROKE = 0.060
STRIPE_DEPTH = 0.030
SYMBOL_DEPTH = 0.026

# Separate the zebra crossing and pedestrian in depth to avoid z-fighting.
CROSSWALK_FORWARD = 0.050
PEDESTRIAN_FORWARD = 0.068


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
    lateral = float(point[0])
    vertical = float(point[1])
    n_left = left_axis(heading)

    return [
        face_origin[0] + n_left[0] * lateral,
        face_origin[1] + n_left[1] * lateral,
        face_origin[2] + vertical,
    ]


def segment_rotation(heading, p1, p2):
    du = float(p2[0]) - float(p1[0])
    dv = float(p2[1]) - float(p1[1])
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
    width,
    depth,
    color,
    forward_offset=0.0,
    overlap=1.08,
):
    du = float(p2[0]) - float(p1[0])
    dv = float(p2[1]) - float(p1[1])
    length = math.hypot(du, dv)

    if length <= 1e-9:
        return

    midpoint = (
        (float(p1[0]) + float(p2[0])) / 2.0,
        (float(p1[1]) + float(p2[1])) / 2.0,
    )

    t = tangent(heading)
    center = logical_to_world(face_origin, heading, midpoint)
    center = [
        center[0] - t[0] * forward_offset,
        center[1] - t[1] * forward_offset,
        center[2],
    ]

    spawn_shape(
        shape=shape,
        actor_ids=actor_ids,
        location=center,
        rotation=segment_rotation(heading, p1, p2),
        scale=[length * overlap, depth, width],
        configuration=QLabsBasicShape.SHAPE_CUBE,
        color=color,
        roughness=0.12,
        collisions=False,
    )


def draw_polyline(
    shape,
    actor_ids,
    face_origin,
    heading,
    points,
    width,
    depth,
    color,
    subdivisions=1,
    forward_offset=0.0,
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
                shape=shape,
                actor_ids=actor_ids,
                face_origin=face_origin,
                heading=heading,
                p1=previous,
                p2=current,
                width=width,
                depth=depth,
                color=color,
                forward_offset=forward_offset,
            )
            previous = current


def spawn_face_box(
    shape,
    actor_ids,
    face_origin,
    heading,
    center_point,
    size_x,
    size_z,
    depth,
    color,
    forward_offset=0.0,
):
    t = tangent(heading)
    center = logical_to_world(face_origin, heading, center_point)
    center = [
        center[0] - t[0] * forward_offset,
        center[1] - t[1] * forward_offset,
        center[2],
    ]

    spawn_shape(
        shape=shape,
        actor_ids=actor_ids,
        location=center,
        rotation=[0.0, math.pi / 2.0, heading],
        scale=[float(size_x), float(size_z), float(depth)],
        configuration=QLabsBasicShape.SHAPE_CUBE,
        color=color,
        roughness=0.16,
        collisions=False,
    )


def spawn_face_disc(
    shape,
    actor_ids,
    face_origin,
    heading,
    center_point,
    diameter,
    depth,
    color,
    forward_offset=0.0,
):
    t = tangent(heading)
    center = logical_to_world(face_origin, heading, center_point)
    center = [
        center[0] - t[0] * forward_offset,
        center[1] - t[1] * forward_offset,
        center[2],
    ]

    spawn_shape(
        shape=shape,
        actor_ids=actor_ids,
        location=center,
        rotation=[0.0, math.pi / 2.0, heading],
        scale=[float(diameter), float(diameter), float(depth)],
        configuration=QLabsBasicShape.SHAPE_CYLINDER,
        color=color,
        roughness=0.16,
        collisions=False,
    )


def spawn_rotated_face_box(
    shape,
    actor_ids,
    face_origin,
    heading,
    center_point,
    size_along,
    size_across,
    angle_deg,
    depth,
    color,
    forward_offset=0.0,
):
    angle = math.radians(angle_deg)
    dx = math.cos(angle) * (size_along / 2.0)
    dz = math.sin(angle) * (size_along / 2.0)
    p1 = (center_point[0] - dx, center_point[1] - dz)
    p2 = (center_point[0] + dx, center_point[1] + dz)

    du = p2[0] - p1[0]
    dv = p2[1] - p1[1]
    length = math.hypot(du, dv)

    t = tangent(heading)
    center = logical_to_world(face_origin, heading, center_point)
    center = [
        center[0] - t[0] * forward_offset,
        center[1] - t[1] * forward_offset,
        center[2],
    ]

    spawn_shape(
        shape=shape,
        actor_ids=actor_ids,
        location=center,
        rotation=segment_rotation(heading, p1, p2),
        scale=[length, depth, size_across],
        configuration=QLabsBasicShape.SHAPE_CUBE,
        color=color,
        roughness=0.12,
        collisions=False,
    )


def triangle_edge_x_at_z(a, b, z):
    ax, az = a
    bx, bz = b

    if abs(bz - az) <= 1e-9:
        return ax

    fraction = (z - az) / (bz - az)
    return ax + (bx - ax) * fraction


def spawn_triangle_fill(
    shape,
    actor_ids,
    face_origin,
    heading,
    top_point,
    left_point,
    right_point,
    rows,
    color,
    depth,
    forward_offset=0.0,
):
    z_min = left_point[1]
    z_max = top_point[1]
    rows = max(2, int(rows))

    for index in range(rows):
        z = z_min + (index + 0.5) / rows * (z_max - z_min)

        left_x = triangle_edge_x_at_z(left_point, top_point, z)
        right_x = triangle_edge_x_at_z(right_point, top_point, z)

        spawn_face_segment(
            shape=shape,
            actor_ids=actor_ids,
            face_origin=face_origin,
            heading=heading,
            p1=(left_x, z),
            p2=(right_x, z),
            width=(z_max - z_min) / rows * 1.18,
            depth=depth,
            color=color,
            forward_offset=forward_offset,
            overlap=1.02,
        )


def spawn_warning_triangle(shape, actor_ids, face_origin, heading):
    # White filled triangle.
    spawn_triangle_fill(
        shape=shape,
        actor_ids=actor_ids,
        face_origin=face_origin,
        heading=heading,
        top_point=TOP_POINT,
        left_point=LEFT_POINT,
        right_point=RIGHT_POINT,
        rows=FILL_ROWS,
        color=WHITE,
        depth=TRIANGLE_DEPTH,
        forward_offset=PLATE_FILL_FORWARD,
    )

    # Thick red border.
    for p1, p2 in [
        (LEFT_POINT, TOP_POINT),
        (TOP_POINT, RIGHT_POINT),
        (RIGHT_POINT, LEFT_POINT),
    ]:
        spawn_face_segment(
            shape=shape,
            actor_ids=actor_ids,
            face_origin=face_origin,
            heading=heading,
            p1=p1,
            p2=p2,
            width=BORDER_WIDTH,
            depth=TRIANGLE_DEPTH * 0.88,
            color=RED,
            forward_offset=BORDER_FORWARD,
            overlap=1.02,
        )


def spawn_crosswalk_stripes(shape, actor_ids, face_origin, heading):
    """
    Five stable zebra stripes.

    This version uses simple upright rectangles instead of rotated bars, and
    keeps them slightly behind the pedestrian so the two black graphics do not
    z-fight on the plate surface.
    """

    stripes = [
        (-0.34, -0.245, 0.085, 0.205),
        (-0.17, -0.245, 0.078, 0.205),
        (0.00, -0.245, 0.080, 0.205),
        (0.17, -0.245, 0.078, 0.205),
        (0.34, -0.245, 0.085, 0.205),
    ]

    for center_x, center_z, width_x, height_z in stripes:
        # IMPORTANT:
        # For this vertical sign-face cube orientation, local X maps to the
        # sign's vertical axis and local Y maps to the sign's lateral axis.
        # Therefore the stripe HEIGHT must be passed as size_x and the stripe
        # WIDTH as size_z.  The previous version had these reversed, which
        # turned all five zebra stripes into horizontal bars.
        spawn_face_box(
            shape=shape,
            actor_ids=actor_ids,
            face_origin=face_origin,
            heading=heading,
            center_point=(center_x, center_z),
            size_x=height_z,
            size_z=width_x,
            depth=STRIPE_DEPTH,
            color=BLACK,
            forward_offset=CROSSWALK_FORWARD,
        )


def spawn_pedestrian(shape, actor_ids, face_origin, heading):
    """
    Cleaner walking-person silhouette.

    The figure is intentionally built from a small number of narrow strokes
    instead of thick overlapping polylines, so it stays readable at sign size.
    """

    # Head.
    spawn_face_disc(
        shape=shape,
        actor_ids=actor_ids,
        face_origin=face_origin,
        heading=heading,
        center_point=(0.00, 0.235),
        diameter=0.082,
        depth=SYMBOL_DEPTH,
        color=BLACK,
        forward_offset=PEDESTRIAN_FORWARD,
    )

    # Torso, slightly leaning in the walking direction.
    draw_polyline(
        shape=shape,
        actor_ids=actor_ids,
        face_origin=face_origin,
        heading=heading,
        points=[
            (-0.015, 0.145),
            (0.010, 0.070),
            (0.025, -0.015),
        ],
        width=FIGURE_STROKE,
        depth=SYMBOL_DEPTH,
        color=BLACK,
        subdivisions=4,
        forward_offset=PEDESTRIAN_FORWARD,
    )

    # Left arm: shoulder to hand.
    draw_polyline(
        shape=shape,
        actor_ids=actor_ids,
        face_origin=face_origin,
        heading=heading,
        points=[
            (-0.010, 0.115),
            (-0.090, 0.055),
            (-0.155, -0.005),
        ],
        width=ARM_STROKE,
        depth=SYMBOL_DEPTH,
        color=BLACK,
        subdivisions=4,
        forward_offset=PEDESTRIAN_FORWARD,
    )

    # Right arm.
    draw_polyline(
        shape=shape,
        actor_ids=actor_ids,
        face_origin=face_origin,
        heading=heading,
        points=[
            (0.010, 0.115),
            (0.080, 0.070),
            (0.145, 0.020),
        ],
        width=ARM_STROKE,
        depth=SYMBOL_DEPTH,
        color=BLACK,
        subdivisions=4,
        forward_offset=PEDESTRIAN_FORWARD,
    )

    # Small pelvis block to give the legs a clean common origin.
    spawn_face_box(
        shape=shape,
        actor_ids=actor_ids,
        face_origin=face_origin,
        heading=heading,
        center_point=(0.020, -0.030),
        size_x=0.090,
        size_z=0.060,
        depth=SYMBOL_DEPTH,
        color=BLACK,
        forward_offset=PEDESTRIAN_FORWARD,
    )

    # Forward leg.
    draw_polyline(
        shape=shape,
        actor_ids=actor_ids,
        face_origin=face_origin,
        heading=heading,
        points=[
            (0.020, -0.050),
            (0.105, -0.145),
            (0.165, -0.245),
        ],
        width=LEG_STROKE,
        depth=SYMBOL_DEPTH,
        color=BLACK,
        subdivisions=5,
        forward_offset=PEDESTRIAN_FORWARD,
    )

    # Rear leg.
    draw_polyline(
        shape=shape,
        actor_ids=actor_ids,
        face_origin=face_origin,
        heading=heading,
        points=[
            (0.010, -0.050),
            (-0.060, -0.150),
            (-0.125, -0.235),
        ],
        width=LEG_STROKE,
        depth=SYMBOL_DEPTH,
        color=BLACK,
        subdivisions=5,
        forward_offset=PEDESTRIAN_FORWARD,
    )


def spawn_pedestrian_crossing_sign(shape, actor_ids, ground_location, heading=0.0):
    ground = [float(v) for v in ground_location]
    t = tangent(heading)

    # Pole behind the plate.
    post_center = [
        ground[0] + t[0] * POST_BACK_OFFSET,
        ground[1] + t[1] * POST_BACK_OFFSET,
        ground[2] + POST_HEIGHT / 2.0,
    ]

    spawn_shape(
        shape=shape,
        actor_ids=actor_ids,
        location=post_center,
        rotation=[0.0, 0.0, heading],
        scale=[POST_WIDTH, POST_WIDTH, POST_HEIGHT],
        configuration=QLabsBasicShape.SHAPE_CUBE,
        color=POST_GRAY,
        roughness=0.75,
        collisions=True,
    )

    face_origin = [
        ground[0],
        ground[1],
        ground[2] + PLATE_CENTER_Z,
    ]

    spawn_warning_triangle(shape, actor_ids, face_origin, heading)
    spawn_crosswalk_stripes(shape, actor_ids, face_origin, heading)
    spawn_pedestrian(shape, actor_ids, face_origin, heading)


def main():
    print("Open the QLabs Plane workspace before running this script.")
    print("This v5 test fixes the zebra stripe orientation.")

    qlabs = QuanserInteractiveLabs()

    if not qlabs.open("localhost"):
        print("Unable to connect to QLabs.")
        sys.exit(1)

    qlabs.destroy_all_spawned_actors()

    shape = QLabsBasicShape(qlabs)
    actor_ids = ActorNumberAllocator(start=7000)

    spawn_pedestrian_crossing_sign(
        shape=shape,
        actor_ids=actor_ids,
        ground_location=[0.0, 0.0, 0.0],
        heading=0.0,
    )

    print("Pedestrian crossing warning sign v5 created.")


if __name__ == "__main__":
    main()
