"""
QLabs Track Editor configuration.

Values are preserved from v1.0.1 so the modular OOP rewrite keeps the
same editor geometry and behavior.
"""

from PySide6.QtGui import QColor

APP_NAME = "QLabs Track Editor"
APP_VERSION = "2.0.0-dev"
WINDOW_WIDTH = 1500
WINDOW_HEIGHT = 920

PIXELS_PER_METER = 20.0
GRID_METERS = 1.0
GRID_PIXELS = PIXELS_PER_METER * GRID_METERS
MAJOR_GRID_EVERY = 5

# Editable canvas boundary. It defines the design/fill area; manual items can
# still be moved freely outside it for inspection and layout work.
DEFAULT_CANVAS_WIDTH_M = 120.0
DEFAULT_CANVAS_HEIGHT_M = 80.0
MIN_CANVAS_SIZE_M = 20.0
MAX_CANVAS_SIZE_M = 50000.0

# Scenery auto-fill defaults. Roadside reserve is measured outward from the
# road footprint, leaving a clear verge for signs, lights, crosswalk hardware,
# pedestrians placed intentionally, and other roadside experiment objects.
DEFAULT_SCENERY_FILL_STYLE = "suburban"
DEFAULT_SCENERY_FILL_DENSITY = "medium"
DEFAULT_ROADSIDE_RESERVE_M = 4.0
# Auto-filled buildings are restricted to a corridor beside a road. This is
# the maximum distance from the physical road edge to a building center.
DEFAULT_BUILDING_ROAD_BAND_M = 18.0

DEFAULT_ROAD_LENGTH_M = 20.0
DEFAULT_ROAD_WIDTH_M = 8.4
DEFAULT_CURVE_RADIUS_M = 10.0
DEFAULT_JUNCTION_ARM_M = 12.0
DEFAULT_ROAD_END_LENGTH_M = 8.0

# Default height used for exported spline roads/markings/guides when a
# workspace-specific saved value is not present.
DEFAULT_SPLINE_Z_M = 1.20

# Full-scale footprint used only for the editor QCar2 start marker.
# The real QLabs QCar actor is uniformly scaled by the project scale.
QCAR2_DESIGN_LENGTH_M = 4.6
QCAR2_DESIGN_WIDTH_M = 1.9

# Open Road visual-width estimate/calibration.
# The user's latest QLabs comparison indicates that the native overlay reads
# closest in the editor at roughly 4.3 m per displayed lane, three lanes per
# carriageway, with about a 0.5 m centre divider/barrier.
OPEN_ROAD_REFERENCE_LANES_PER_SIDE = 3
OPEN_ROAD_REFERENCE_LANE_WIDTH_M = 4
OPEN_ROAD_REFERENCE_SEPARATOR_WIDTH_M = 0.25
OPEN_ROAD_REFERENCE_CARRIAGEWAY_WIDTH_M = (
    OPEN_ROAD_REFERENCE_LANES_PER_SIDE * OPEN_ROAD_REFERENCE_LANE_WIDTH_M
)
OPEN_ROAD_REFERENCE_TOTAL_WIDTH_M = (
    2.0
    * OPEN_ROAD_REFERENCE_LANES_PER_SIDE
    * OPEN_ROAD_REFERENCE_LANE_WIDTH_M
    + OPEN_ROAD_REFERENCE_SEPARATOR_WIDTH_M
)

# Median/barrier wall defaults. The wall is an editor/exportable static object
# and straight roads can snap flush to either side of it.
DEFAULT_MEDIAN_WALL_LENGTH_M = 20.0
DEFAULT_MEDIAN_WALL_WIDTH_M = 0.5
DEFAULT_MEDIAN_WALL_HEIGHT_M = 0.85
MEDIAN_WALL_COLOR = QColor(172, 166, 154)
WALL_SNAP_DISTANCE_M = 1.0
WALL_SNAP_DISTANCE_PX = WALL_SNAP_DISTANCE_M * PIXELS_PER_METER

# Symbolic editor footprints for scene actors. These are for 2-D layout
# readability; the QLabs exporter uses each actor's actual QLabs scale.
ACTOR_MARKER_SIZE_M = 2.0
CROSSWALK_MARKER_LENGTH_M = 4.2
CROSSWALK_MARKER_WIDTH_M = 2.1
# QLabs' crosswalk asset is wider than the road geometry used by this editor.
# This base multiplier makes Actor scale=1.0 fit a typical 6 m two-lane road.
CROSSWALK_QLABS_BASE_SCALE = 0.55

DEFAULT_BUILDING_LENGTH_M = 10.0
DEFAULT_BUILDING_WIDTH_M = 8.0
DEFAULT_BUILDING_HEIGHT_M = 5.0
DEFAULT_BUILDING_RGB = (145, 155, 170)

QCAR_CAMERA_THIRD_PERSON = "third_person"
QCAR_CAMERA_FIRST_PERSON = "first_person"

EXPERIMENT_SPAWN_IMMEDIATE = "immediate"
EXPERIMENT_SPAWN_TRIGGERED = "triggered"

TRIGGER_ACTION_ACTIVATE_ACTOR = "activate_actor"
TRIGGER_ACTION_TRAFFIC_LIGHT = "change_traffic_light"

DEFAULT_TRIGGER_RADIUS_M = 5.0

MOVEMENT_ONCE = "once"
MOVEMENT_LOOP = "loop"
MOVEMENT_PINGPONG = "pingpong"

DEFAULT_SECONDARY_QCAR_SPEED_MPS = 8.0
DEFAULT_PATH_REACHED_TOLERANCE_M = 0.45

WEATHER_PRESETS = (
    ("Clear skies", "clear_skies"),
    ("Partly cloudy", "partly_cloudy"),
    ("Cloudy", "cloudy"),
    ("Overcast", "overcast"),
    ("Foggy", "foggy"),
    ("Light rain", "light_rain"),
    ("Rain", "rain"),
    ("Thunderstorm", "thunderstorm"),
    ("Light snow", "light_snow"),
    ("Snow", "snow"),
    ("Blizzard", "blizzard"),
)

ROTATION_STEP_DEG = 15.0

# An endpoint must be this close to another compatible endpoint to snap.
ENDPOINT_SNAP_DISTANCE_M = 1.0
ENDPOINT_SNAP_DISTANCE_PX = ENDPOINT_SNAP_DISTANCE_M * PIXELS_PER_METER

# Connection headings should face approximately opposite directions.
# With 15-degree rotation steps, 20 degrees allows one-step tolerance.
SNAP_HEADING_TOLERANCE_DEG = 20.0


# ================================================================
# Shared road appearance
# ================================================================

ROAD_COLOR = QColor(75, 75, 75)
EDGE_LINE_COLOR = QColor(240, 240, 240)
CENTER_LINE_COLOR = QColor(255, 215, 0)
SELECTION_COLOR = QColor(0, 170, 255)
CONNECTION_COLOR = QColor(70, 220, 140)
CONNECTION_OUTLINE_COLOR = QColor(20, 70, 45)

EDGE_LINE_WIDTH_PX = 2
CENTER_LINE_WIDTH_PX = 3
SELECTION_LINE_WIDTH_PX = 3

# Same inset used by the working v0.1 straight-road rendering.
EDGE_LINE_INSET_PX = 8.0

# Per-road marking defaults. Each line can be enabled/disabled and can use its
# own color and solid/dashed style in both the editor and QLabs export.
DEFAULT_EDGE_A_MARKING_COLOR = "white"
DEFAULT_EDGE_A_MARKING_STYLE = "solid"
DEFAULT_CENTER_MARKING_COLOR = "yellow"
DEFAULT_CENTER_MARKING_STYLE = "dashed"
DEFAULT_EDGE_B_MARKING_COLOR = "white"
DEFAULT_EDGE_B_MARKING_STYLE = "solid"
DEFAULT_END_BAR_MARKING_COLOR = "white"
DEFAULT_END_BAR_MARKING_STYLE = "solid"

ROAD_MARKING_COLOR_RGB = {
    "white": (240, 240, 240),
    "yellow": (255, 215, 0),
    "blue": (60, 160, 255),
    "red": (255, 80, 80),
    "black": (25, 25, 25),
}

ROAD_MARKING_COLORS = {
    name: QColor(*rgb)
    for name, rgb in ROAD_MARKING_COLOR_RGB.items()
}

ROAD_MARKING_STYLES = (
    ("Solid", "solid"),
    ("Dashed", "dashed"),
)

# Lane-following guide defaults. These are design/full-scale dimensions.
DEFAULT_GUIDE_WIDTH_M = 0.10
DEFAULT_GUIDE_POSITION = "left"
DEFAULT_GUIDE_CUSTOM_OFFSET_M = -1.5
DEFAULT_GUIDE_COLOR = "yellow"
DEFAULT_GUIDE_RGB = (255, 215, 0)
DEFAULT_GUIDE_STYLE = "solid"

# RGB values are kept separately from QColor so they can also be
# written directly into the project JSON and later converted to
# QLabs' normalized [0..1] spline color format by the exporter.
GUIDE_COLOR_RGB = {
    "yellow": (255, 215, 0),
    "white": (255, 255, 255),
    "blue": (60, 160, 255),
    "red": (255, 80, 80),
}

GUIDE_COLORS = {
    name: QColor(*rgb)
    for name, rgb in GUIDE_COLOR_RGB.items()
}

PROJECT_SCALES = [
    ("1:1", 1.0),
    ("1:2", 0.5),
    ("1:5", 0.2),
    ("1:10", 0.1),
]



WORKSPACE_CUSTOM = 'custom'
WORKSPACE_OPEN_ROAD = 'open_road'
WORKSPACE_CITYSCAPE = 'cityscape'
WORKSPACE_CITYSCAPE_LITE = 'cityscape_lite'
WORKSPACE_TOWNSCAPE = 'townscape'
WORKSPACE_TOWNSCAPE_LITE = 'townscape_lite'
WORKSPACE_STUDIO = 'studio'
WORKSPACE_WAREHOUSE = 'warehouse'

# Native QLabs workspace modes offered by the main Workspace selector.
# WORKSPACE_CUSTOM remains the backward-compatible value for Plane/custom maps.
WORKSPACE_MODES = (
    WORKSPACE_CUSTOM,
    WORKSPACE_OPEN_ROAD,
    WORKSPACE_CITYSCAPE,
    WORKSPACE_CITYSCAPE_LITE,
    WORKSPACE_TOWNSCAPE,
    WORKSPACE_TOWNSCAPE_LITE,
    WORKSPACE_STUDIO,
    WORKSPACE_WAREHOUSE,
)
OPEN_ROAD_REFERENCE_FILENAME = 'open_road_reference.json'
CITYSCAPE_REFERENCE_FILENAME = 'cityscape_reference.json'
TOWNSCAPE_REFERENCE_FILENAME = 'townscape_reference.json'

# ================================================================
# Manual tracing / reference image defaults
# ================================================================

# Reference images exist only in the editor. They are never exported to QLabs.
DEFAULT_REFERENCE_IMAGE_OPACITY = 0.45
DEFAULT_REFERENCE_IMAGE_WIDTH_M = 60.0
MIN_REFERENCE_IMAGE_SIZE_M = 0.10
MAX_REFERENCE_IMAGE_SIZE_M = 50000.0
REFERENCE_IMAGE_Z = -50.0
REFERENCE_IMAGE_HANDLE_PX = 12.0
