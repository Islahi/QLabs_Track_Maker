"""Spawn temporary Cityscape calibration markers at Quanser-published coordinates.

Run this while the Cityscape workspace is open. The script does not clear any
existing actors. Press Enter to remove only the markers created by this script.

Use this to visually compare the editor's Cityscape overlay with QLabs before
using the reference for precise experimental placement.
"""

from qvl.qlabs import QuanserInteractiveLabs
from qvl.basic_shape import QLabsBasicShape


MARKERS = [
    # name, (x, y, z), RGB
    ("Open World Origin", (0.000, 0.000, 0.10), (1.00, 0.20, 0.20)),
    ("Road Parking 1", (-13.093, -7.572, 0.10), (0.20, 0.75, 1.00)),
    ("Road Parking 2", (-18.078, -2.879, 0.10), (0.20, 1.00, 0.45)),
    ("Parking Spot 1", (-5.987, 14.643, 0.10), (1.00, 0.75, 0.20)),
    ("Parking Spot 4", (3.978, 33.322, 0.10), (0.90, 0.25, 1.00)),
]


def spawn_marker(qlabs, name, location, color):
    actor = QLabsBasicShape(qlabs)
    status, actor_number = actor.spawn(
        location=list(location),
        rotation=[0.0, 0.0, 0.0],
        scale=[1.15, 1.15, 0.20],
        configuration=QLabsBasicShape.SHAPE_CYLINDER,
        waitForConfirmation=True,
    )
    if status != 0:
        print(f"FAILED: {name}: status={status}")
        return None

    actor.set_material_properties(
        color=list(color),
        roughness=0.25,
        metallic=False,
        waitForConfirmation=True,
    )
    actor.set_enable_dynamics(False, waitForConfirmation=True)
    actor.set_enable_collisions(False, waitForConfirmation=True)

    print(
        f"{name:18s} -> actor {actor_number:4d} at "
        f"({location[0]:8.3f}, {location[1]:8.3f}, {location[2]:5.2f})"
    )
    return actor


def main():
    qlabs = QuanserInteractiveLabs()
    if not qlabs.open("localhost"):
        raise RuntimeError("Could not connect to QLabs at localhost")

    actors = []
    try:
        print("Connected. Spawning Cityscape reference markers...\n")
        for name, location, color in MARKERS:
            actor = spawn_marker(qlabs, name, location, color)
            if actor is not None:
                actors.append(actor)

        print("\nCompare these marker locations with the Cityscape overlay.")
        input("Press Enter to remove these markers... ")
    finally:
        for actor in reversed(actors):
            try:
                actor.destroy()
            except Exception as exc:
                print(f"Warning: marker cleanup failed: {exc}")
        qlabs.close()
        print("Markers removed; QLabs connection closed.")


if __name__ == "__main__":
    main()
