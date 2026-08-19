import math
import sys

from qvl.qlabs import QuanserInteractiveLabs
from qvl.basic_shape import QLabsBasicShape


# ================================================================
# No Overtaking traffic sign - Plane test v2
# ================================================================
# Improved car symbol closer to the real sign reference:
#   - red outer ring
#   - white inner face
#   - outlined red car on the left
#   - filled black car on the right
# Both cars are built from custom face geometry using many thin boxes.
# ================================================================

RED = [0.82, 0.08, 0.08]
WHITE = [0.98, 0.98, 0.98]
BLACK = [0.08, 0.08, 0.08]
POST_GRAY = [0.55, 0.55, 0.57]

POST_HEIGHT = 2.30
POST_WIDTH = 0.08
POST_BACK_OFFSET = 0.10

PLATE_CENTER_Z = 2.45
OUTER_DIAMETER = 1.22
INNER_DIAMETER = 0.96
PLATE_DEPTH = 0.08
INNER_FACE_FORWARD = 0.012
SYMBOL_FORWARD = 0.050
FACE_BOX_DEPTH = 0.025

CAR_STROKE = 0.028
WINDOW_STROKE = 0.020
DETAIL_DEPTH_STEP = 0.002


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


def logical_to_world(face_origin, heading, x_left, z_up):
    n_left = left_axis(heading)
    return [
        face_origin[0] + n_left[0] * float(x_left),
        face_origin[1] + n_left[1] * float(x_left),
        face_origin[2] + float(z_up),
    ]


def segment_rotation(heading, p1, p2):
    dx = float(p2[0]) - float(p1[0])
    dz = float(p2[1]) - float(p1[1])
    length = math.hypot(dx, dz)
    if length <= 1e-9:
        return None

    n_left = left_axis(heading)
    face_normal = [-v for v in tangent(heading)]
    x_axis = [n_left[0] * dx / length, n_left[1] * dx / length, dz / length]
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
    forward_offset=0.0,
    roughness=0.12,
):
    dx = float(p2[0]) - float(p1[0])
    dz = float(p2[1]) - float(p1[1])
    length = math.hypot(dx, dz)
    if length <= 1e-9:
        return

    midpoint = ((float(p1[0]) + float(p2[0])) / 2.0, (float(p1[1]) + float(p2[1])) / 2.0)
    t = tangent(heading)
    center = logical_to_world(face_origin, heading, midpoint[0], midpoint[1])
    center = [
        center[0] - t[0] * float(forward_offset),
        center[1] - t[1] * float(forward_offset),
        center[2],
    ]
    rotation = segment_rotation(heading, p1, p2)

    spawn_shape(
        shape=shape,
        actor_ids=actor_ids,
        location=center,
        rotation=rotation,
        scale=[length * 1.04, FACE_BOX_DEPTH, float(width)],
        configuration=QLabsBasicShape.SHAPE_CUBE,
        color=color,
        roughness=roughness,
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
    color,
    forward_offset=0.0,
    roughness=0.15,
):
    t = tangent(heading)
    center = logical_to_world(face_origin, heading, center_x, center_z)
    center = [
        center[0] - t[0] * float(forward_offset),
        center[1] - t[1] * float(forward_offset),
        center[2],
    ]

    spawn_shape(
        shape=shape,
        actor_ids=actor_ids,
        location=center,
        rotation=[0.0, math.pi / 2.0, heading],
        scale=[float(size_x), float(size_z), FACE_BOX_DEPTH],
        configuration=QLabsBasicShape.SHAPE_CUBE,
        color=color,
        roughness=roughness,
        collisions=False,
    )


def draw_polyline(
    shape,
    actor_ids,
    face_origin,
    heading,
    points,
    width,
    color,
    forward_offset=0.0,
):
    if len(points) < 2:
        return
    for i in range(len(points) - 1):
        spawn_face_segment(
            shape,
            actor_ids,
            face_origin,
            heading,
            points[i],
            points[i + 1],
            width=width,
            color=color,
            forward_offset=forward_offset,
        )


def draw_horizontal_fill_rows(
    shape,
    actor_ids,
    face_origin,
    heading,
    center_x,
    z_values,
    half_widths,
    color,
    row_height=0.022,
    forward_offset=0.001,
):
    """Fill a silhouette using stacked horizontal boxes."""
    for z, half_w in zip(z_values, half_widths):
        spawn_face_box(
            shape, actor_ids, face_origin, heading,
            center_x=center_x,
            center_z=z,
            size_x=2.0 * half_w,
            size_z=row_height,
            color=color,
            forward_offset=forward_offset,
            roughness=0.10,
        )


def spawn_better_car(
    shape,
    actor_ids,
    face_origin,
    heading,
    center_x,
    body_color,
    outline_only=False,
):
    """Draw a cleaner car icon closer to the reference no-overtaking sign."""

    # Silhouette tuned to match the reference icon more closely.
    roof_y = 0.095
    shoulder_y = 0.022
    body_mid_y = -0.010
    body_bottom_y = -0.082
    leg_bottom_y = -0.145

    top_left = (center_x - 0.072, roof_y)
    top_right = (center_x + 0.072, roof_y)
    shoulder_left = (center_x - 0.108, shoulder_y)
    shoulder_right = (center_x + 0.108, shoulder_y)
    side_left = (center_x - 0.132, body_mid_y)
    side_right = (center_x + 0.132, body_mid_y)
    lower_left = (center_x - 0.132, body_bottom_y)
    lower_right = (center_x + 0.132, body_bottom_y)
    tab_left = (center_x - 0.148, -0.052)
    tab_right = (center_x + 0.148, -0.052)
    leg_left_x = center_x - 0.095
    leg_right_x = center_x + 0.095

    if not outline_only:
        # Black car fill built from wide horizontal rows only, so no unwanted vertical line appears in the middle.
        fill_rows = [
            (0.058, 0.074),
            (0.036, 0.090),
            (0.014, 0.108),
            (-0.010, 0.122),
            (-0.034, 0.126),
            (-0.058, 0.126),
        ]
        for zc, half_w in fill_rows:
            spawn_face_box(
                shape, actor_ids, face_origin, heading,
                center_x=center_x,
                center_z=zc,
                size_x=2.0 * half_w,
                size_z=0.022,
                color=body_color,
                forward_offset=0.000,
                roughness=0.10,
            )

        # Window opening made from two horizontal rows only.
        for zc, half_w in [(0.040, 0.046), (0.024, 0.056)]:
            spawn_face_box(
                shape, actor_ids, face_origin, heading,
                center_x=center_x,
                center_z=zc,
                size_x=2.0 * half_w,
                size_z=0.016,
                color=WHITE,
                forward_offset=0.003,
                roughness=0.08,
            )

        # Number plate.
        spawn_face_box(
            shape, actor_ids, face_origin, heading,
            center_x=center_x,
            center_z=-0.055,
            size_x=0.050,
            size_z=0.024,
            color=WHITE,
            forward_offset=0.003,
            roughness=0.08,
        )

        # Side light bars.
        for sx in (-0.100, 0.100):
            spawn_face_box(
                shape, actor_ids, face_origin, heading,
                center_x=center_x + sx,
                center_z=-0.028,
                size_x=0.012,
                size_z=0.056,
                color=WHITE,
                forward_offset=0.003,
                roughness=0.08,
            )
    else:
        # Outline car: only the white details inside the red outline.
        spawn_face_box(
            shape, actor_ids, face_origin, heading,
            center_x=center_x,
            center_z=-0.055,
            size_x=0.050,
            size_z=0.024,
            color=WHITE,
            forward_offset=0.003,
            roughness=0.08,
        )
        for sx in (-0.100, 0.100):
            spawn_face_box(
                shape, actor_ids, face_origin, heading,
                center_x=center_x + sx,
                center_z=-0.028,
                size_x=0.012,
                size_z=0.056,
                color=WHITE,
                forward_offset=0.003,
                roughness=0.08,
            )

    # Outer silhouette.
    draw_polyline(
        shape, actor_ids, face_origin, heading,
        [top_left, top_right],
        width=CAR_STROKE, color=body_color, forward_offset=DETAIL_DEPTH_STEP,
    )
    draw_polyline(
        shape, actor_ids, face_origin, heading,
        [top_left, shoulder_left, side_left, lower_left],
        width=CAR_STROKE, color=body_color, forward_offset=DETAIL_DEPTH_STEP,
    )
    draw_polyline(
        shape, actor_ids, face_origin, heading,
        [top_right, shoulder_right, side_right, lower_right],
        width=CAR_STROKE, color=body_color, forward_offset=DETAIL_DEPTH_STEP,
    )
    draw_polyline(
        shape, actor_ids, face_origin, heading,
        [lower_left, lower_right],
        width=CAR_STROKE, color=body_color, forward_offset=DETAIL_DEPTH_STEP,
    )

    # Side tabs.
    draw_polyline(
        shape, actor_ids, face_origin, heading,
        [tab_left, (center_x - 0.132, -0.052)],
        width=CAR_STROKE, color=body_color, forward_offset=DETAIL_DEPTH_STEP,
    )
    draw_polyline(
        shape, actor_ids, face_origin, heading,
        [(center_x + 0.132, -0.052), tab_right],
        width=CAR_STROKE, color=body_color, forward_offset=DETAIL_DEPTH_STEP,
    )

    # Lower legs.
    draw_polyline(
        shape, actor_ids, face_origin, heading,
        [(leg_left_x, body_bottom_y), (leg_left_x, leg_bottom_y)],
        width=CAR_STROKE, color=body_color, forward_offset=DETAIL_DEPTH_STEP,
    )
    draw_polyline(
        shape, actor_ids, face_origin, heading,
        [(leg_right_x, body_bottom_y), (leg_right_x, leg_bottom_y)],
        width=CAR_STROKE, color=body_color, forward_offset=DETAIL_DEPTH_STEP,
    )


def spawn_no_overtaking_sign(shape, actor_ids, ground_location, heading=0.0):
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

    plate_center = [ground[0], ground[1], ground[2] + PLATE_CENTER_Z]

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

    # White inner face.
    inner_face_center = [
        plate_center[0] - t[0] * INNER_FACE_FORWARD,
        plate_center[1] - t[1] * INNER_FACE_FORWARD,
        plate_center[2],
    ]
    spawn_shape(
        shape=shape,
        actor_ids=actor_ids,
        location=inner_face_center,
        rotation=[0.0, math.pi / 2.0, heading],
        scale=[INNER_DIAMETER, INNER_DIAMETER, PLATE_DEPTH * 0.82],
        configuration=QLabsBasicShape.SHAPE_CYLINDER,
        color=WHITE,
        roughness=0.22,
        collisions=False,
    )

    face_origin = [
        plate_center[0] - t[0] * SYMBOL_FORWARD,
        plate_center[1] - t[1] * SYMBOL_FORWARD,
        plate_center[2],
    ]

    # Left red outlined car and right black filled car.
    spawn_better_car(
        shape=shape,
        actor_ids=actor_ids,
        face_origin=face_origin,
        heading=heading,
        center_x=-0.17,
        body_color=RED,
        outline_only=True,
    )
    spawn_better_car(
        shape=shape,
        actor_ids=actor_ids,
        face_origin=face_origin,
        heading=heading,
        center_x=0.15,
        body_color=BLACK,
        outline_only=False,
    )


def main():
    print("Open the QLabs Plane workspace before running this script.")
    print("This v6 test removes the black car center line artifact and makes the sign icon strokes thicker.")

    qlabs = QuanserInteractiveLabs()
    if not qlabs.open("localhost"):
        print("Unable to connect to QLabs.")
        sys.exit(1)

    qlabs.destroy_all_spawned_actors()
    shape = QLabsBasicShape(qlabs)
    actor_ids = ActorNumberAllocator(start=7000)

    spawn_no_overtaking_sign(
        shape=shape,
        actor_ids=actor_ids,
        ground_location=[0.0, 0.0, 0.0],
        heading=0.0,
    )

    print("No Overtaking traffic sign v6 created.")
    print("Check whether the black car center artifact is gone and the icon lines look thicker.")


if __name__ == "__main__":
    main()
