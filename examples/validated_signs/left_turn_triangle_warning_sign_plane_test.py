import math
import sys

from qvl.qlabs import QuanserInteractiveLabs
from qvl.basic_shape import QLabsBasicShape


# ================================================================
# Left-Turn Warning Sign - triangular plate - Plane test v2
# ================================================================
# Built to resemble the supplied reference:
#   - white filled triangular plate
#   - thick red triangular border
#   - black curved left-turn symbol
#   - pole shifted behind the sign face
#
# QLabs BasicShape has no native triangle primitive, so the triangular plate
# is approximated with many thin horizontal white boxes plus three thick red
# border bars.
# ================================================================


WHITE = [0.98, 0.98, 0.98]
RED = [0.92, 0.06, 0.06]
BLACK = [0.04, 0.04, 0.04]
POST_GRAY = [0.55, 0.55, 0.57]

POST_HEIGHT = 2.25
POST_WIDTH = 0.08
POST_BACK_OFFSET = 0.11

PLATE_CENTER_Z = 2.45
PLATE_DEPTH = 0.035
FACE_OFFSET = 0.055

# Triangle logical geometry on the sign face.
TRIANGLE_HALF_WIDTH = 0.62
TRIANGLE_BOTTOM_Z = -0.52
TRIANGLE_TOP_Z = 0.58
TRIANGLE_FILL_ROWS = 42
TRIANGLE_BORDER_WIDTH = 0.095

# Curved black symbol.
SYMBOL_STROKE_WIDTH = 0.095
SYMBOL_DEPTH = 0.028
ARC_SEGMENTS = 20


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
    # Mirror the approved right-turn geometry across the vertical centerline.
    lateral = -float(point[0])
    vertical = float(point[1])
    n_left = left_axis(heading)

    return [
        face_origin[0] + n_left[0] * lateral,
        face_origin[1] + n_left[1] * lateral,
        face_origin[2] + vertical,
    ]


def segment_rotation(heading, p1, p2):
    # Mirror the lateral component to match logical_to_world().
    du = -(float(p2[0]) - float(p1[0]))
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
    overlap=1.06,
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
        roughness=0.14,
        collisions=False,
    )


def spawn_face_box(
    shape,
    actor_ids,
    face_origin,
    heading,
    center_x,
    center_z,
    size_x,
    size_z,
    depth,
    color,
    forward_offset=0.0,
):
    t = tangent(heading)
    center = logical_to_world(face_origin, heading, (center_x, center_z))
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
        scale=[size_x, size_z, depth],
        configuration=QLabsBasicShape.SHAPE_CUBE,
        color=color,
        roughness=0.18,
        collisions=False,
    )


def spawn_rotated_face_square(
    shape,
    actor_ids,
    face_origin,
    heading,
    center_point,
    side,
    angle_deg,
    depth,
    color,
    forward_offset=0.0,
):
    """Spawn one square on the sign face, rotated inside the face plane."""
    angle = math.radians(angle_deg)
    half = side / 2.0
    dx = math.cos(angle) * half
    dz = math.sin(angle) * half

    p1 = (center_point[0] - dx, center_point[1] - dz)
    p2 = (center_point[0] + dx, center_point[1] + dz)

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
        scale=[side, depth, side],
        configuration=QLabsBasicShape.SHAPE_CUBE,
        color=color,
        roughness=0.14,
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
                shape,
                actor_ids,
                face_origin,
                heading,
                previous,
                current,
                width=width,
                depth=depth,
                color=color,
                forward_offset=forward_offset,
            )
            previous = current


def arc_points(center_x, center_y, radius, start_deg, end_deg, segments):
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


def spawn_triangle_fill(shape, actor_ids, face_origin, heading):
    """Fill the triangular plate using stacked horizontal face segments."""

    total_height = TRIANGLE_TOP_Z - TRIANGLE_BOTTOM_Z
    row_height = total_height / TRIANGLE_FILL_ROWS * 1.18

    for index in range(TRIANGLE_FILL_ROWS):
        fraction = (index + 0.5) / TRIANGLE_FILL_ROWS
        z = TRIANGLE_BOTTOM_Z + total_height * fraction

        # Triangle width shrinks linearly toward the apex.
        half_width = TRIANGLE_HALF_WIDTH * (1.0 - fraction)

        # Use spawn_face_segment instead of a rotated face box. This is the
        # same mapping used by the working arrow geometry, so the white fill
        # lies correctly on the vertical sign plane.
        spawn_face_segment(
            shape=shape,
            actor_ids=actor_ids,
            face_origin=face_origin,
            heading=heading,
            p1=(-half_width, z),
            p2=(half_width, z),
            width=row_height,
            depth=PLATE_DEPTH,
            color=WHITE,
            forward_offset=0.0,
            overlap=1.04,
        )


def spawn_triangle_border(shape, actor_ids, face_origin, heading):
    apex = (0.0, TRIANGLE_TOP_Z)
    left_bottom = (-TRIANGLE_HALF_WIDTH, TRIANGLE_BOTTOM_Z)
    right_bottom = (TRIANGLE_HALF_WIDTH, TRIANGLE_BOTTOM_Z)

    # Three thick red bars.
    for p1, p2 in [
        (left_bottom, apex),
        (apex, right_bottom),
        (right_bottom, left_bottom),
    ]:
        spawn_face_segment(
            shape=shape,
            actor_ids=actor_ids,
            face_origin=face_origin,
            heading=heading,
            p1=p1,
            p2=p2,
            width=TRIANGLE_BORDER_WIDTH,
            depth=PLATE_DEPTH * 0.95,
            color=RED,
            forward_offset=0.012,
            overlap=1.02,
        )


def spawn_left_turn_symbol(shape, actor_ids, face_origin, heading):
    """Black curved left-turn warning symbol."""

    # Vertical lower stem, slightly left of center like the reference.
    stem = [
        (-0.12, -0.28),
        (-0.12, -0.18),
        (-0.12, -0.08),
        (-0.12, 0.02),
    ]

    draw_polyline(
        shape,
        actor_ids,
        face_origin,
        heading,
        stem,
        width=SYMBOL_STROKE_WIDTH,
        depth=SYMBOL_DEPTH,
        color=BLACK,
        forward_offset=0.028,
    )

    # Shorter bend than the previous version.
    #
    # Stop the arc BEFORE it becomes horizontal.  The last part of the arrow
    # will therefore continue as a straight angled line, closer to the
    # reference sign.
    curve = arc_points(
        center_x=0.04,
        center_y=0.02,
        radius=0.16,
        start_deg=180.0,
        end_deg=115.0,
        segments=ARC_SEGMENTS,
    )

    draw_polyline(
        shape,
        actor_ids,
        face_origin,
        heading,
        curve,
        width=SYMBOL_STROKE_WIDTH,
        depth=SYMBOL_DEPTH,
        color=BLACK,
        forward_offset=0.028,
    )

    # Continue directly along the tangent of the final arc segment.
    # This removes the visible kink between the curve and the angled head.
    arc_before_end = curve[-2]
    arc_end = curve[-1]

    direction_x = arc_end[0] - arc_before_end[0]
    direction_z = arc_end[1] - arc_before_end[1]
    direction_length = math.hypot(direction_x, direction_z)

    direction_x /= direction_length
    direction_z /= direction_length

    straight_length = 0.095
    branch_end = (
        arc_end[0] + direction_x * straight_length,
        arc_end[1] + direction_z * straight_length,
    )

    draw_polyline(
        shape,
        actor_ids,
        face_origin,
        heading,
        [arc_end, branch_end],
        width=SYMBOL_STROKE_WIDTH,
        depth=SYMBOL_DEPTH,
        color=BLACK,
        subdivisions=5,
        forward_offset=0.028,
    )

    # A single rotated square forms the point.  Its corner is aligned with the
    # same direction as the straight continuation.
    branch_angle_deg = math.degrees(
        math.atan2(direction_z, direction_x)
    )

    spawn_rotated_face_square(
        shape=shape,
        actor_ids=actor_ids,
        face_origin=face_origin,
        heading=heading,
        center_point=branch_end,
        side=0.070,
        angle_deg=branch_angle_deg - 45.0,
        depth=SYMBOL_DEPTH,
        color=BLACK,
        forward_offset=0.030,
    )


def spawn_left_turn_warning_sign(
    shape,
    actor_ids,
    ground_location,
    heading=0.0,
):
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

    plate_center = [
        ground[0],
        ground[1],
        ground[2] + PLATE_CENTER_Z,
    ]

    face_origin = [
        plate_center[0] - t[0] * FACE_OFFSET,
        plate_center[1] - t[1] * FACE_OFFSET,
        plate_center[2],
    ]

    # Build the white triangle first, red border second, symbol last.
    spawn_triangle_fill(shape, actor_ids, face_origin, heading)
    spawn_triangle_border(shape, actor_ids, face_origin, heading)
    spawn_left_turn_symbol(shape, actor_ids, face_origin, heading)


def main():
    print("Open the QLabs Plane workspace before running this script.")
    print("This v6 test uses a larger rotated square and an angled final head segment.")

    qlabs = QuanserInteractiveLabs()

    if not qlabs.open("localhost"):
        print("Unable to connect to QLabs.")
        sys.exit(1)

    qlabs.destroy_all_spawned_actors()

    shape = QLabsBasicShape(qlabs)
    actor_ids = ActorNumberAllocator(start=7000)

    spawn_left_turn_warning_sign(
        shape=shape,
        actor_ids=actor_ids,
        ground_location=[0.0, 0.0, 0.0],
        heading=0.0,
    )

    print("Triangular Left-Turn warning sign v2 created.")
    print(f"Triangle fill rows: {TRIANGLE_FILL_ROWS}")
    print(f"Curve segments: {ARC_SEGMENTS}")


if __name__ == "__main__":
    main()
