"""Validated custom traffic-sign catalog used by the editor and exporter.

Only signs that were individually built and checked in the Plane workspace are
listed here.  Native QLabs signs (Stop, Yield, and Roundabout) remain separate
toolbar items and are not duplicated in this custom catalog.
"""

DEFAULT_TRAFFIC_SIGN_KEY = "front_or_right"

TRAFFIC_SIGN_CATALOG = (
    ("front_or_right", "Front or Right", "mandatory", "↑↱"),
    ("front_or_left", "Front or Left", "mandatory", "↑↰"),
    ("right_turn", "Right Turn", "warning", "↱"),
    ("left_turn", "Left Turn", "warning", "↰"),
    ("u_turn", "U Turn", "mandatory", "U"),
    ("no_u_turn", "No U Turn", "prohibition", "U"),
    ("right_or_left", "Right or Left", "mandatory", "↙↘"),
    ("parking", "Parking", "parking", "P"),
    ("no_parking", "No Parking", "prohibition", "P"),
    ("no_overtaking", "No Overtaking", "prohibition", "||"),
    ("pedestrian_crossing", "Pedestrian Crossing", "warning", "PED"),
    ("speed_30", "Speed 30", "speed", "30"),
    ("speed_40", "Speed 40", "speed", "40"),
    ("speed_50", "Speed 50", "speed", "50"),
    ("speed_60", "Speed 60", "speed", "60"),
    ("speed_80", "Speed 80", "speed", "80"),
    ("speed_100", "Speed 100", "speed", "100"),
)

TRAFFIC_SIGN_META = {
    key: {
        "key": key,
        "display": display,
        "family": family,
        "short": short,
    }
    for key, display, family, short in TRAFFIC_SIGN_CATALOG
}

TRAFFIC_SIGN_KEYS = tuple(item[0] for item in TRAFFIC_SIGN_CATALOG)


def traffic_sign_display(key: str) -> str:
    """Return a readable label for a validated custom sign key."""
    return TRAFFIC_SIGN_META.get(
        str(key),
        TRAFFIC_SIGN_META[DEFAULT_TRAFFIC_SIGN_KEY],
    )["display"]
