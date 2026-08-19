import math
import sys

from qvl.qlabs import QuanserInteractiveLabs
from qvl.basic_shape import QLabsBasicShape


# ================================================================
# Parking sign - Plane test
# ================================================================
# Reference style:
#   - blue rectangular plate
#   - thin white rectangular border
#   - large white "P"
#
# The "P" uses an arc made from many short BasicShape cubes.
# ================================================================


WHITE = [0.98, 0.98, 0.98]
BLUE = [0.05, 0.36, 0.76]
POST_GRAY = [0.55, 0.55, 0.57]

POST_HEIGHT = 2.30
POST_WIDTH = 0.08
POST_BACK_OFFSET = 0.10

PLATE_CENTER_Z = 2.45
PLATE_WIDTH = 1.18
PLATE_HEIGHT = 1.35
PLATE_DEPTH = 0.08
PLATE_CORNER_RADIUS = 0.16

BORDER_THICKNESS = 0.045
INNER_FORWARD = 0.012
SYMBOL_FORWARD = 0.055

# P geometry
P_STROKE_WIDTH = 0.095
P_DEPTH = 0.026
P_ARC_SEGMENTS = 22


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


def spawn_face_disc(
    shape,
    actor_ids,
    face_origin,
    heading,
    center_x,
    center_z,
    diameter,
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
        scale=[diameter, diameter, depth],
        configuration=QLabsBasicShape.SHAPE_CYLINDER,
        color=color,
        roughness=0.18,
        collisions=False,
    )


def spawn_rounded_rectangle(
    shape,
    actor_ids,
    face_origin,
    heading,
    width,
    height,
    radius,
    depth,
    color,
    forward_offset=0.0,
):
    """
    Rounded rectangle made from:
      - one wide central box
      - one tall central box
      - four circular corner discs
    """

    # Horizontal center body.
    spawn_face_box(
        shape,
        actor_ids,
        face_origin,
        heading,
        center_x=0.0,
        center_z=0.0,
        size_x=width - 2.0 * radius,
        size_z=height,
        depth=depth,
        color=color,
        forward_offset=forward_offset,
    )

    # Vertical center body.
    spawn_face_box(
        shape,
        actor_ids,
        face_origin,
        heading,
        center_x=0.0,
        center_z=0.0,
        size_x=width,
        size_z=height - 2.0 * radius,
        depth=depth,
        color=color,
        forward_offset=forward_offset,
    )

    corner_x = width / 2.0 - radius
    corner_z = height / 2.0 - radius

    for x, z in [
        (-corner_x, corner_z),
        (corner_x, corner_z),
        (-corner_x, -corner_z),
        (corner_x, -corner_z),
    ]:
        spawn_face_disc(
            shape,
            actor_ids,
            face_origin,
            heading,
            center_x=x,
            center_z=z,
            diameter=2.0 * radius,
            depth=depth,
            color=color,
            forward_offset=forward_offset,
        )


def spawn_parking_symbol(shape, actor_ids, face_origin, heading):
    """Large white P with an arc-built bowl."""

    # Vertical P stem.
    draw_polyline(
        shape=shape,
        actor_ids=actor_ids,
        face_origin=face_origin,
        heading=heading,
        points=[
            (-0.17, -0.28),
            (-0.17, -0.14),
            (-0.17, 0.00),
            (-0.17, 0.20),
            (-0.17, 0.38),
        ],
        width=P_STROKE_WIDTH,
        depth=P_DEPTH,
        color=WHITE,
        forward_offset=0.0,
    )

    # Top horizontal part.
    draw_polyline(
        shape=shape,
        actor_ids=actor_ids,
        face_origin=face_origin,
        heading=heading,
        points=[
            (-0.17, 0.34),
            (0.08, 0.34),
        ],
        width=P_STROKE_WIDTH,
        depth=P_DEPTH,
        color=WHITE,
        subdivisions=4,
        forward_offset=0.0,
    )

    # Curved outer bowl of the P.
    bowl_arc = arc_points(
        center_x=0.08,
        center_y=0.20,
        radius=0.14,
        start_deg=90.0,
        end_deg=-90.0,
        segments=P_ARC_SEGMENTS,
    )

    draw_polyline(
        shape=shape,
        actor_ids=actor_ids,
        face_origin=face_origin,
        heading=heading,
        points=bowl_arc,
        width=P_STROKE_WIDTH,
        depth=P_DEPTH,
        color=WHITE,
        forward_offset=0.0,
    )

    # Middle horizontal return to the vertical stem.
    draw_polyline(
        shape=shape,
        actor_ids=actor_ids,
        face_origin=face_origin,
        heading=heading,
        points=[
            bowl_arc[-1],
            (-0.17, 0.06),
        ],
        width=P_STROKE_WIDTH,
        depth=P_DEPTH,
        color=WHITE,
        subdivisions=4,
        forward_offset=0.0,
    )


def spawn_parking_sign(
    shape,
    actor_ids,
    ground_location,
    heading=0.0,
):
    ground = [float(v) for v in ground_location]
    t = tangent(heading)

    # Pole behind the sign.
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

    # Logical face origin at plate center.
    face_origin = plate_center[:]

    # Plain rectangular white outer plate.
    # No circular corner pieces are used in this version.
    spawn_face_box(
        shape=shape,
        actor_ids=actor_ids,
        face_origin=face_origin,
        heading=heading,
        center_x=0.0,
        center_z=0.0,
        size_x=PLATE_WIDTH,
        size_z=PLATE_HEIGHT,
        depth=PLATE_DEPTH,
        color=WHITE,
        forward_offset=0.0,
    )

    # Plain rectangular blue inner plate, slightly smaller so the white
    # border remains visible on all four sides.
    inner_width = PLATE_WIDTH - 2.0 * BORDER_THICKNESS
    inner_height = PLATE_HEIGHT - 2.0 * BORDER_THICKNESS

    spawn_face_box(
        shape=shape,
        actor_ids=actor_ids,
        face_origin=face_origin,
        heading=heading,
        center_x=0.0,
        center_z=0.0,
        size_x=inner_width,
        size_z=inner_height,
        depth=PLATE_DEPTH * 0.88,
        color=BLUE,
        forward_offset=INNER_FORWARD,
    )

    # White P in front of the plate.
    symbol_origin = [
        plate_center[0] - t[0] * SYMBOL_FORWARD,
        plate_center[1] - t[1] * SYMBOL_FORWARD,
        plate_center[2],
    ]

    spawn_parking_symbol(
        shape,
        actor_ids,
        symbol_origin,
        heading,
    )


def main():
    print("Open the QLabs Plane workspace before running this script.")
    print("This v2 test builds a Parking sign with square plate corners and a shorter P leg.")

    qlabs = QuanserInteractiveLabs()

    if not qlabs.open("localhost"):
        print("Unable to connect to QLabs.")
        sys.exit(1)

    qlabs.destroy_all_spawned_actors()

    shape = QLabsBasicShape(qlabs)
    actor_ids = ActorNumberAllocator(start=7000)

    spawn_parking_sign(
        shape=shape,
        actor_ids=actor_ids,
        ground_location=[0.0, 0.0, 0.0],
        heading=0.0,
    )

    print("Parking traffic sign v2 created.")
    print(f"P arc segments: {P_ARC_SEGMENTS}")


if __name__ == "__main__":
    main()
