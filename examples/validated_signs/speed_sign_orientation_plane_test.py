"""
Plane-only validation for the known-good QLabs speed-limit sign geometry.

This file intentionally copies the speed-limit construction model from the
user-provided qlabs_setup_open_road.py and removes all unrelated experiment
code. It spawns four signs around the origin so each sign faces toward the
center of the Plane workspace:

    North: 60 km/h, heading +90 deg
    East:  30 km/h, heading   0 deg
    South: 100 km/h, heading -90 deg
    West:  80 km/h, heading 180 deg

Open Quanser Interactive Labs in the Plane workspace before running it.
"""

import math
import sys

import numpy as np

from qvl.qlabs import QuanserInteractiveLabs
from qvl.basic_shape import QLabsBasicShape


# ================================================================
# Sign dimensions copied from the known-good implementation
# ================================================================

SIGN_POST_HEIGHT = 3.0
SIGN_POST_WIDTH = 0.16
SIGN_CENTER_HEIGHT = 3.0
SIGN_DIAMETER = 2.2
SIGN_PLATE_DEPTH = 0.12


# ================================================================
# Test layout
# ================================================================

# Each sign is positioned around the origin and oriented for traffic
# approaching from the center. Therefore the visible face points inward.
TEST_SIGNS = [
    # speed, base position, heading
    (30,  [12.0,  0.0, 0.0], 0.0),
    (60,  [0.0,  12.0, 0.0], math.pi / 2.0),
    (80,  [-12.0, 0.0, 0.0], math.pi),
    (100, [0.0, -12.0, 0.0], -math.pi / 2.0),
]


# ================================================================
# Utility
# ================================================================

class ActorNumberAllocator:
    """Simple unique actor-number allocator for BasicShape actors."""

    def __init__(self, start=1000):
        self._next = start

    def next(self):
        value = self._next
        self._next += 1
        return value


def tangent(heading):
    """Return the horizontal unit vector along the travel direction."""
    return np.array([
        math.cos(heading),
        math.sin(heading),
        0.0,
    ])


def spawn_basic_shape(
    shape,
    actor_ids,
    location,
    rotation,
    scale,
    configuration,
    color,
    enable_collisions=True,
):
    """Spawn and color one BasicShape actor."""

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
        color=color,
        roughness=0.8,
        metallic=False,
        waitForConfirmation=True,
    )

    shape.set_enable_collisions(
        enable_collisions,
        waitForConfirmation=True,
    )

    # Keep every sign component static during this geometry test.
    shape.set_enable_dynamics(
        False,
        waitForConfirmation=True,
    )

    return actor_number


# ================================================================
# Seven-segment speed-limit sign
# ================================================================

SEVEN_SEGMENTS = {
    "0": {"a", "b", "c", "d", "e", "f"},
    "1": {"b", "c"},
    "2": {"a", "b", "g", "e", "d"},
    "3": {"a", "b", "c", "d", "g"},
    "4": {"f", "g", "b", "c"},
    "5": {"a", "f", "g", "c", "d"},
    "6": {"a", "f", "g", "e", "c", "d"},
    "7": {"a", "b", "c"},
    "8": {"a", "b", "c", "d", "e", "f", "g"},
    "9": {"a", "b", "c", "d", "f", "g"},
}


def spawn_speed_limit_sign(
    shape,
    actor_ids,
    ground_location,
    heading,
    speed_kmh,
):
    """Build one circular red/white speed-limit sign from BasicShape actors."""

    ground = np.array(ground_location, dtype=float)
    t = tangent(heading)
    n_left = np.array([
        math.sin(heading),
        -math.cos(heading),
        0.0,
    ])

    # ------------------------------------------------------------
    # Post
    # ------------------------------------------------------------
    post_center = ground + np.array([
        0.0,
        0.0,
        SIGN_POST_HEIGHT / 2.0,
    ])

    spawn_basic_shape(
        shape=shape,
        actor_ids=actor_ids,
        location=post_center,
        rotation=[0.0, 0.0, 0.0],
        scale=[SIGN_POST_WIDTH, SIGN_POST_WIDTH, SIGN_POST_HEIGHT],
        configuration=QLabsBasicShape.SHAPE_CUBE,
        color=[0.45, 0.45, 0.45],
        enable_collisions=True,
    )

    plate_center = ground + np.array([
        0.0,
        0.0,
        SIGN_CENTER_HEIGHT,
    ])

    # IMPORTANT: this is the known-good orientation.
    # The cylinder is pitched 90 degrees, then yawed by road heading.
    plate_rotation = [
        0.0,
        math.pi / 2.0,
        heading,
    ]

    # ------------------------------------------------------------
    # Red outer plate
    # ------------------------------------------------------------
    spawn_basic_shape(
        shape=shape,
        actor_ids=actor_ids,
        location=plate_center,
        rotation=plate_rotation,
        scale=[
            SIGN_DIAMETER,
            SIGN_DIAMETER,
            SIGN_PLATE_DEPTH,
        ],
        configuration=QLabsBasicShape.SHAPE_CYLINDER,
        color=[0.85, 0.03, 0.03],
        enable_collisions=False,
    )

    # ------------------------------------------------------------
    # White inner plate, slightly toward approaching traffic
    # ------------------------------------------------------------
    white_center = plate_center - t * 0.07

    spawn_basic_shape(
        shape=shape,
        actor_ids=actor_ids,
        location=white_center,
        rotation=plate_rotation,
        scale=[
            SIGN_DIAMETER * 0.78,
            SIGN_DIAMETER * 0.78,
            SIGN_PLATE_DEPTH * 0.55,
        ],
        configuration=QLabsBasicShape.SHAPE_CYLINDER,
        color=[0.96, 0.96, 0.96],
        enable_collisions=False,
    )

    # ------------------------------------------------------------
    # Seven-segment digits
    # ------------------------------------------------------------
    number = str(int(speed_kmh))

    digit_width = 0.42
    digit_height = 0.88
    digit_gap = 0.14
    segment_thickness = 0.095
    digit_depth = 0.055

    total_width = (
        len(number) * digit_width
        + (len(number) - 1) * digit_gap
    )

    first_digit_center = (
        -total_width / 2.0
        + digit_width / 2.0
    )

    # Known-good face orientation for digit cubes.
    digit_yaw = heading + math.pi / 2.0

    horizontal_length = digit_width * 0.82
    vertical_length = digit_height * 0.38

    segment_definitions = {
        "a": (0.0, +digit_height / 2.0, horizontal_length, segment_thickness),
        "g": (0.0, 0.0, horizontal_length, segment_thickness),
        "d": (0.0, -digit_height / 2.0, horizontal_length, segment_thickness),
        "f": (-digit_width / 2.0, +digit_height / 4.0, segment_thickness, vertical_length),
        "b": (+digit_width / 2.0, +digit_height / 4.0, segment_thickness, vertical_length),
        "e": (-digit_width / 2.0, -digit_height / 4.0, segment_thickness, vertical_length),
        "c": (+digit_width / 2.0, -digit_height / 4.0, segment_thickness, vertical_length),
    }

    digit_face_origin = plate_center - t * 0.13

    for digit_index, digit in enumerate(number):
        if digit not in SEVEN_SEGMENTS:
            continue

        digit_lateral_center = (
            first_digit_center
            + digit_index * (digit_width + digit_gap)
        )

        for segment_name in SEVEN_SEGMENTS[digit]:
            (
                lateral_offset,
                vertical_offset,
                lateral_size,
                vertical_size,
            ) = segment_definitions[segment_name]

            segment_center = (
                digit_face_origin
                + n_left * (
                    digit_lateral_center
                    + lateral_offset
                )
                + np.array([
                    0.0,
                    0.0,
                    vertical_offset,
                ])
            )

            spawn_basic_shape(
                shape=shape,
                actor_ids=actor_ids,
                location=segment_center,
                rotation=[
                    0.0,
                    0.0,
                    digit_yaw,
                ],
                scale=[
                    lateral_size,
                    digit_depth,
                    vertical_size,
                ],
                configuration=QLabsBasicShape.SHAPE_CUBE,
                color=[0.02, 0.02, 0.02],
                enable_collisions=False,
            )


# ================================================================
# Main
# ================================================================


def main():
    print("Open QLabs in the Plane workspace before running this test.")
    print("The four signs are arranged around the origin and face inward.")
    print("East  = 30 km/h / heading 0 deg")
    print("North = 60 km/h / heading +90 deg")
    print("West  = 80 km/h / heading 180 deg")
    print("South = 100 km/h / heading -90 deg")

    qlabs = QuanserInteractiveLabs()

    print("Connecting to QLabs...")
    if not qlabs.open("localhost"):
        print("Unable to connect to QLabs.")
        sys.exit(1)

    print("Connected.")

    qlabs.destroy_all_spawned_actors()

    shape = QLabsBasicShape(qlabs)
    actor_ids = ActorNumberAllocator(start=1000)

    for speed_kmh, ground_location, heading in TEST_SIGNS:
        spawn_speed_limit_sign(
            shape=shape,
            actor_ids=actor_ids,
            ground_location=ground_location,
            heading=heading,
            speed_kmh=speed_kmh,
        )

    print("Speed-limit orientation test spawned successfully.")
    print("Inspect all four signs from around the origin.")
    print("Do not integrate into the editor yet; first confirm all four faces/digits look correct.")


if __name__ == "__main__":
    main()
