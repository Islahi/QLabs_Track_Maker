"""Spawn temporary Townscape calibration markers at Quanser-published coordinates.

Run while Townscape or Townscape Lite is open. The script does not clear other
actors. Press Enter to remove only the markers created by this script.

The packaged Townscape v2.4 reference was calibrated from these four marker
locations. Run this utility again whenever you want to independently revalidate
the current QLabs workspace/camera alignment after a simulator update.
"""

from qvl.qlabs import QuanserInteractiveLabs
from qvl.basic_shape import QLabsBasicShape


MARKERS = [
    ("Open World Origin", (0.000, 0.000, 0.10), (1.00, 0.20, 0.20), 0.72),
    ("Car Spawn Spot", (0.000, -1.300, 0.10), (1.00, 0.78, 0.20), 0.52),
    ("Road Parking 1", (-13.093, -7.572, 0.10), (0.20, 0.75, 1.00), 0.72),
    ("Road Parking 2", (-18.078, -2.879, 0.10), (0.20, 1.00, 0.45), 0.72),
]


def spawn_marker(qlabs, name, location, color, diameter):
    actor = QLabsBasicShape(qlabs)
    status, actor_number = actor.spawn(
        location=list(location),
        rotation=[0.0, 0.0, 0.0],
        scale=[diameter, diameter, 0.20],
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
        print("Connected. Spawning Townscape reference markers...\n")
        for name, location, color, diameter in MARKERS:
            actor = spawn_marker(qlabs, name, location, color, diameter)
            if actor is not None:
                actors.append(actor)

        print("\nSwitch to a true top-down view and capture all four markers.")
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
