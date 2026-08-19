import math
import sys

from qvl.qlabs import QuanserInteractiveLabs
from qvl.basic_shape import QLabsBasicShape


# ================================================================
# No Parking traffic sign - Plane test with "P"
# ================================================================
# Standard prohibition-style circular sign:
#   - red outer ring
#   - blue inner face
#   - white "P" inside the circle
#   - red diagonal slash
# The pole is shifted slightly behind the sign plate so it does not cover the
# visible face from the front.
# ================================================================


RED = [0.82, 0.08, 0.08]
BLUE = [0.06, 0.36, 0.78]
WHITE = [0.98, 0.98, 0.98]
POST_GRAY = [0.55, 0.55, 0.57]

POST_HEIGHT = 2.30
POST_WIDTH = 0.08
POST_BACK_OFFSET = 0.10

PLATE_CENTER_Z = 2.45
OUTER_DIAMETER = 1.22
INNER_DIAMETER = 0.96
PLATE_DEPTH = 0.08
INNER_FACE_FORWARD = 0.012
LETTER_FORWARD = 0.040
SLASH_FORWARD = 0.055

# Face geometry.
STROKE_DEPTH = 0.025
P_STROKE_WIDTH = 0.11
P_SYMBOL_SCALE = 1.18

# Slash geometry on the sign face.
SLASH_WIDTH = 0.13
SLASH_LENGTH = 1.02
SLASH_ANGLE_DEG = -45.0


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


def logical_to_world(face_origin, heading, point, scale=1.0):
    lateral = float(point[0]) * scale
    vertical = float(point[1]) * scale
    n_left = left_axis(heading)

    return [
        face_origin[0] + n_left[0] * lateral,
        face_origin[1] + n_left[1] * lateral,
        face_origin[2] + vertical,
    ]


def segment_rotation(heading, p1, p2, scale=1.0):
    du = (float(p2[0]) - float(p1[0])) * scale
    dv = (float(p2[1]) - float(p1[1])) * scale
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
    color,
    scale=1.0,
):
    du = (float(p2[0]) - float(p1[0])) * scale
    dv = (float(p2[1]) - float(p1[1])) * scale
    length = math.hypot(du, dv)

    if length <= 1e-9:
        return

    midpoint = (
        (float(p1[0]) + float(p2[0])) / 2.0,
        (float(p1[1]) + float(p2[1])) / 2.0,
    )

    center = logical_to_world(face_origin, heading, midpoint, scale=scale)
    rotation = segment_rotation(heading, p1, p2, scale=scale)

    spawn_shape(
        shape=shape,
        actor_ids=actor_ids,
        location=center,
        rotation=rotation,
        scale=[length * 1.06, STROKE_DEPTH, width],
        configuration=QLabsBasicShape.SHAPE_CUBE,
        color=color,
        roughness=0.12,
        collisions=False,
    )


def draw_p_letter(shape, actor_ids, face_origin, heading):
    # Logical P geometry centered on the sign face.
    segments = [
        ((-0.12, -0.26), (-0.12, 0.24)),  # left stem
        ((-0.12, 0.24), (0.08, 0.24)),    # top bar
        ((-0.12, 0.02), (0.06, 0.02)),    # middle bar
        ((0.08, 0.24), (0.08, 0.02)),     # right stem of bowl
    ]

    for p1, p2 in segments:
        spawn_face_segment(
            shape,
            actor_ids,
            face_origin,
            heading,
            p1,
            p2,
            width=P_STROKE_WIDTH,
            color=WHITE,
            scale=P_SYMBOL_SCALE,
        )


def spawn_no_parking_sign(shape, actor_ids, ground_location, heading=0.0):
    ground = [float(v) for v in ground_location]
    t = tangent(heading)

    # Pole (moved behind the sign face)
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

    # Main circular plate: red outer ring + blue inner face
    plate_center = [
        ground[0],
        ground[1],
        ground[2] + PLATE_CENTER_Z,
    ]

    # Red outer circle.
    spawn_shape(
        shape=shape,
        actor_ids=actor_ids,
        location=plate_center,
        rotation=[0.0, math.pi / 2.0, heading],
        scale=[OUTER_DIAMETER, OUTER_DIAMETER, PLATE_DEPTH],
        configuration=QLabsBasicShape.SHAPE_CYLINDER,
        color=RED,
        roughness=0.22,
        collisions=False,
    )

    # Blue inner face slightly toward the viewer so the red ring stays visible.
    blue_face_center = [
        plate_center[0] - t[0] * INNER_FACE_FORWARD,
        plate_center[1] - t[1] * INNER_FACE_FORWARD,
        plate_center[2],
    ]
    spawn_shape(
        shape=shape,
        actor_ids=actor_ids,
        location=blue_face_center,
        rotation=[0.0, math.pi / 2.0, heading],
        scale=[INNER_DIAMETER, INNER_DIAMETER, PLATE_DEPTH * 0.82],
        configuration=QLabsBasicShape.SHAPE_CYLINDER,
        color=BLUE,
        roughness=0.22,
        collisions=False,
    )

    # White "P" inside the sign.
    letter_origin = [
        plate_center[0] - t[0] * LETTER_FORWARD,
        plate_center[1] - t[1] * LETTER_FORWARD,
        plate_center[2],
    ]
    draw_p_letter(shape, actor_ids, letter_origin, heading)

    # Red diagonal slash on the face.
    slash_center = [
        plate_center[0] - t[0] * SLASH_FORWARD,
        plate_center[1] - t[1] * SLASH_FORWARD,
        plate_center[2],
    ]

    spawn_shape(
        shape=shape,
        actor_ids=actor_ids,
        location=slash_center,
        rotation=[
            0.0,
            math.radians(SLASH_ANGLE_DEG),
            heading - math.pi / 2.0,
        ],
        scale=[SLASH_LENGTH, STROKE_DEPTH, SLASH_WIDTH],
        configuration=QLabsBasicShape.SHAPE_CUBE,
        color=RED,
        roughness=0.12,
        collisions=False,
    )


def main():
    print("Open the QLabs Plane workspace before running this script.")
    print('This test builds a No Parking sign with a bigger "P" inside the circle.')

    qlabs = QuanserInteractiveLabs()
    if not qlabs.open("localhost"):
        print("Unable to connect to QLabs.")
        sys.exit(1)

    qlabs.destroy_all_spawned_actors()

    shape = QLabsBasicShape(qlabs)
    actor_ids = ActorNumberAllocator(start=7000)

    spawn_no_parking_sign(
        shape=shape,
        actor_ids=actor_ids,
        ground_location=[0.0, 0.0, 0.0],
        heading=0.0,
    )

    print("No Parking traffic sign created.")
    print('Added a bigger white "P" inside the blue circle.')


if __name__ == "__main__":
    main()
