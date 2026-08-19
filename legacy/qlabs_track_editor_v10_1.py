"""
QLabs Track Editor v1.0.1

Prototype road-network editor for designing QLabs/QCar2 tracks.

v0.5 additions
--------------
- Project scale selection: 1:1, 1:2, 1:5, 1:10 or custom.
- Canvas remains in full-scale design meters; QLabs effective dimensions are shown separately.
- Lane-following guide line for straight, 45-degree, 90-degree and road-end pieces.
- Guide position: left lane, center, right lane or custom lateral offset.
- Guide color: yellow, white, blue, red, or custom RGB (0-255).
- Custom RGB uses direct text-entry boxes instead of spin buttons.
- Selected object, properties, and lane-guide controls live in a fixed right inspector.
- Guide style: solid or dashed.
- Guide width can either scale with the project or remain fixed for camera visibility.
- Adds a movable/rotatable QCar2 Start marker.
- Adds File > Export QLabs Setup... and a sidebar export button.
- Generated QLabs scripts create road surfaces with QLabsSplineLine.
- Exports white edge markings and dashed yellow center markings.
- Lane-following guides export as solid or generated dashed spline segments.
- Project scale is applied to road geometry, markings, guide offsets, QCar position, and QCar actor scale.
- Adds QLabs scene actors: traffic light, stop/yield/roundabout signs, crosswalk, and building/box.
- Adds actor Z, scale, project-scaling, configuration, state/color, and building properties.
- Adds QCar2 camera selection: first-person front CSI or third-person trailing.
- Exports all v0.6 actors into the generated QLabs setup script.
- Adds experiment actors: pedestrian and animal.
- Pedestrian/animal can spawn immediately or be activated by a trigger zone.
- Optional movement destination and gait are exported using QLabs move_to().
- Adds circular QCar trigger zones with one-shot/re-arm behavior.
- Trigger actions: activate experiment actor or change a traffic light.
- Generated setup monitors QCar2 world position while triggers exist.
- Crosswalk QLabs base scale reduced to better fit a 6 m road.
- Adds secondary/environment QCar2 actors with scripted waypoint playback.
- Adds map-click waypoint drawing for pedestrians, animals, and secondary QCars.
- Movement modes: Once, Loop, and Ping-pong.
- Optional actor despawn after a one-shot route finishes.
- Adds outdoor weather preset and time-of-day project settings.
- Preserves older track JSON compatibility.
- v0.9: pedestrians and animals use manual waypoint playback rather than
  QLabs move_to(), removing navigation-area dependence.
- Manual character playback uses a tiny collision-free BasicShape motion proxy
  parented to the character, then moves that proxy with the same interpolation
  approach used by environment QCars.
- Junction center markings stop before the central intersection area.
- Human-readable identifiers are shown for QCars, people, animals, and traffic lights.
- v1.0 adds a documentation-derived Open Road workspace reference overlay.
- Open Road reference geometry is visual-only: it is not selectable, spawned, or exported.
- Optional Open Road navigation-region and published-reference-point overlays.
- Open Road projects use native QLabs X/Y meters and therefore lock project scale to 1:1.
- The large Open Road workspace uses an adaptive grid and expanded low-range zoom.
- v1.0.1 renders the Open Road reference as an approximate six-lane-width corridor
  (3 lanes per direction plus a center separator) instead of a single cosmetic line.
- v1.0.1 raises the exported primary QCar2 spawn to Z = 2 * project scale.

Editor coordinates are stored in meters. Qt scene Y grows downward, while
world/QLabs-style Y is presented as growing upward.
"""

import json
import math
import sys
import uuid
from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (
    QAction,
    QBrush,
    QColor,
    QKeySequence,
    QPainter,
    QPainterPath,
    QPainterPathStroker,
    QPen,
    QIntValidator,
)
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGraphicsItem,
    QGraphicsScene,
    QGraphicsSimpleTextItem,
    QGraphicsView,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QLayout,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)


# ================================================================
# Editor units / geometry
# ================================================================

PIXELS_PER_METER = 20.0
GRID_METERS = 1.0
GRID_PIXELS = PIXELS_PER_METER * GRID_METERS
MAJOR_GRID_EVERY = 5

DEFAULT_ROAD_LENGTH_M = 20.0
DEFAULT_ROAD_WIDTH_M = 6.0
DEFAULT_CURVE_RADIUS_M = 10.0
DEFAULT_JUNCTION_ARM_M = 12.0
DEFAULT_ROAD_END_LENGTH_M = 8.0

# Full-scale footprint used only for the editor QCar2 start marker.
# The real QLabs QCar actor is uniformly scaled by the project scale.
QCAR2_DESIGN_LENGTH_M = 4.6
QCAR2_DESIGN_WIDTH_M = 1.9

# Open Road v1.0.1 visual-width estimate.
# The documentation-derived path is only an approximate 2-D center reference.
# For inspection, render it as 3 lanes in each direction plus a separator.
# Initial lane width follows the user's estimate of roughly one scale-1 QCar
# width per lane. Change OPEN_ROAD_REFERENCE_LANE_WIDTH_M if visual comparison
# against QLabs shows that the real lanes are wider.
OPEN_ROAD_REFERENCE_LANES_PER_SIDE = 3
OPEN_ROAD_REFERENCE_LANE_WIDTH_M = 1.5 * QCAR2_DESIGN_WIDTH_M
OPEN_ROAD_REFERENCE_SEPARATOR_WIDTH_M = 1.0
OPEN_ROAD_REFERENCE_TOTAL_WIDTH_M = (
    2.0
    * OPEN_ROAD_REFERENCE_LANES_PER_SIDE
    * OPEN_ROAD_REFERENCE_LANE_WIDTH_M
    + OPEN_ROAD_REFERENCE_SEPARATOR_WIDTH_M
)

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


# ================================================================
# Workspace reference overlays
# ================================================================

WORKSPACE_CUSTOM = "custom"
WORKSPACE_OPEN_ROAD = "open_road"

OPEN_ROAD_REFERENCE_FILENAME = "open_road_reference.json"

# v1.0 reads open_road_reference.json beside the editor when available.
# A built-in copy is retained so the editor remains usable as one Python file.
OPEN_ROAD_REFERENCE_FALLBACK = {'format': 'qlabs_workspace_reference', 'version': 1, 'workspace': 'Open Road', 'units': 'meters', 'source': {'documentation_page': 'https://qlabs.quanserdocs.com/en/latest/Workspaces/Open_Road.html', 'reference_image': 'https://qlabs.quanserdocs.com/en/latest/_images/open_road_nav.png', 'note': '2-D visual reference derived from the Quanser Open Road documentation image; not a surveyed engineering/CAD map.'}, 'calibration': {'method': 'Affine fit from documentation-image navigation-region centers to Quanser-published navigation-origin X/Y coordinates.', 'image_width_px': 1327, 'image_height_px': 368, 'pixel_to_world_affine': {'x': [-15.113717240067471, -0.038040122766943796, 10036.060811344756], 'y': [-0.0036763978982973975, 15.241151251190585, -5056.498281774547]}, 'anchor_rms_error_m': 11.568986820842193, 'anchor_max_error_m': 17.73663435845868, 'anchors': [{'name': 'North-West', 'pixel': [169.5, 98.0], 'world_xy': [7481.05, -3569.5], 'fit_error_m': 12.092267691802453}, {'name': 'North', 'pixel': [464.0, 58.0], 'world_xy': [3005.7, -4165.4], 'fit_error_m': 17.73663435845868}, {'name': 'North-East', 'pixel': [959.0, 85.5], 'world_xy': [-4454.1, -3761.0], 'fit_error_m': 8.236296853268025}, {'name': 'South', 'pixel': [663.0, 332.0], 'world_xy': [0.788, 2.415], 'fit_error_m': 2.59193018661041}]}, 'bounds': {'min_x': -8898.219731645771, 'max_x': 9450.06123853274, 'min_y': -4678.219446122708, 'max_y': 125.30564733743904}, 'road_reference': {'closed': True, 'kind': 'documentation_centerline_reference', 'points': [[418.259, -2864.111], [403.183, -2879.356], [342.728, -2879.37], [282.35, -2909.867], [252.198, -2940.357], [237.199, -2986.084], [101.517, -3123.287], [41.101, -3138.543], [26.025, -3153.788], [-19.316, -3153.799], [-34.392, -3169.044], [-155.264, -3184.315], [-170.339, -3199.559], [-200.567, -3199.567], [-245.832, -3230.06], [-276.059, -3230.067], [-321.324, -3260.561], [-351.552, -3260.568], [-411.93, -3291.065], [-442.082, -3321.555], [-487.385, -3336.807], [-623.104, -3458.769], [-638.218, -3458.773], [-788.937, -3626.462], [-788.86, -3656.945], [-819.012, -3687.434], [-818.936, -3717.917], [-864.087, -3794.133], [-878.972, -3885.584], [-909.047, -3946.556], [-908.895, -4007.521], [-923.971, -4022.765], [-923.705, -4129.453], [-938.78, -4144.698], [-938.286, -4342.833], [-923.134, -4358.071], [-922.754, -4510.482], [-937.829, -4525.727], [-937.753, -4556.209], [-1013.132, -4632.433], [-1073.51, -4662.931], [-1103.738, -4662.938], [-1118.814, -4678.183], [-1269.951, -4678.219], [-1285.102, -4662.982], [-1360.709, -4647.759], [-1708.781, -4464.95], [-1739.008, -4464.957], [-1754.16, -4449.72], [-1814.615, -4449.735], [-1829.767, -4434.497], [-1950.677, -4434.526], [-1965.752, -4449.771], [-2056.435, -4449.793], [-2071.51, -4465.038], [-2131.965, -4465.053], [-2147.041, -4480.298], [-2207.496, -4480.312], [-2222.571, -4495.557], [-2298.14, -4495.576], [-2313.216, -4510.82], [-2494.58, -4510.865], [-2509.732, -4495.627], [-2539.959, -4495.634], [-2600.49, -4465.167], [-3145.916, -3931.859], [-3206.447, -3901.391], [-3236.674, -3901.399], [-3251.826, -3886.161], [-3312.281, -3886.176], [-3327.432, -3870.938], [-3448.342, -3870.968], [-3463.418, -3886.213], [-3538.986, -3886.231], [-3554.062, -3901.476], [-3614.517, -3901.491], [-3629.593, -3916.735], [-3659.82, -3916.743], [-3674.896, -3931.988], [-3705.123, -3931.995], [-3720.199, -3947.24], [-3750.426, -3947.247], [-3765.502, -3962.492], [-3795.729, -3962.499], [-3810.805, -3977.744], [-3841.032, -3977.751], [-3856.108, -3992.996], [-3886.336, -3993.004], [-3946.714, -4023.501], [-4007.169, -4023.515], [-4022.245, -4038.76], [-4188.496, -4038.801], [-4203.648, -4023.563], [-4233.875, -4023.571], [-4264.14, -4008.337], [-4370.203, -3901.674], [-4385.469, -3840.713], [-4400.62, -3825.476], [-4400.735, -3779.753], [-4415.886, -3764.515], [-4415.962, -3734.033], [-4446.342, -3673.076], [-4552.404, -3566.413], [-4764.263, -3459.777], [-4809.604, -3459.788], [-4824.755, -3444.55], [-4991.006, -3444.591], [-5006.158, -3429.353], [-5127.068, -3429.383], [-5142.22, -3414.145], [-5202.713, -3398.919], [-5263.32, -3337.969], [-5308.965, -3216.051], [-5339.269, -3185.576], [-5399.99, -3078.902], [-5490.938, -2972.236], [-5490.976, -2956.995], [-5566.735, -2880.808], [-5566.773, -2865.567], [-5884.96, -2545.58], [-5900.074, -2545.583], [-5960.681, -2484.633], [-5975.795, -2484.637], [-6066.667, -2408.453], [-6112.046, -2393.223], [-6142.35, -2362.748], [-6369.322, -2256.115], [-6535.573, -2256.156], [-6626.141, -2301.901], [-6656.292, -2332.391], [-6746.86, -2378.136], [-6897.655, -2515.344], [-6912.769, -2515.347], [-7048.45, -2652.551], [-7063.564, -2652.554], [-7259.548, -2850.737], [-7259.509, -2865.978], [-7304.737, -2911.713], [-7304.66, -2942.195], [-7334.812, -2972.685], [-7364.887, -3033.657], [-7364.811, -3064.139], [-7379.887, -3079.384], [-7379.773, -3125.107], [-7394.848, -3140.352], [-7394.734, -3186.076], [-7409.81, -3201.32], [-7409.658, -3262.285], [-7424.733, -3277.53], [-7424.657, -3308.012], [-7439.733, -3323.257], [-7454.694, -3384.225], [-7605.451, -3536.674], [-7786.588, -3628.165], [-7877.232, -3643.428], [-7892.308, -3658.673], [-7952.762, -3658.687], [-7967.838, -3673.932], [-8254.999, -3674.002], [-8270.15, -3658.764], [-8345.719, -3658.783], [-8360.871, -3643.545], [-8466.705, -3628.33], [-8481.857, -3613.093], [-8557.463, -3597.87], [-8708.791, -3521.701], [-8814.853, -3415.038], [-8830.119, -3354.077], [-8845.271, -3338.84], [-8845.347, -3308.358], [-8860.498, -3293.12], [-8860.689, -3216.914], [-8875.84, -3201.677], [-8876.145, -3079.748], [-8891.296, -3064.51], [-8898.22, -290.621], [-8883.144, -275.376], [-8883.22, -244.894], [-8853.107, -199.163], [-8838.145, -138.195], [-8777.881, -61.974], [-8717.502, -31.477], [-8687.274, -31.47], [-8672.199, -16.225], [-8611.744, -16.21], [-8596.668, -0.965], [4234.878, 2.156], [4250.03, -13.082], [8784.145, -11.979], [8829.41, 18.515], [8859.637, 18.522], [8980.395, 79.516], [9025.736, 79.527], [9086.115, 110.024], [9252.328, 125.306], [9267.479, 110.068], [9312.82, 110.079], [9388.579, 33.892], [9434.149, -57.544], [9434.225, -88.026], [9449.377, -103.264], [9450.061, -377.605], [9434.986, -392.849], [9435.252, -499.537], [9420.176, -514.782], [9405.291, -606.233], [9360.178, -697.691], [9299.913, -773.911], [9179.156, -834.905], [9133.814, -834.916], [9073.436, -865.413], [9028.094, -865.424], [8907.337, -926.418], [8771.656, -1063.622], [8696.468, -1216.052], [8696.582, -1261.775], [8681.506, -1277.02], [8681.81, -1398.949], [8696.962, -1414.187], [8697.152, -1490.392], [8712.304, -1505.63], [8712.418, -1551.353], [8727.57, -1566.591], [8742.874, -1642.793], [8773.215, -1688.509], [8773.291, -1718.991], [8788.443, -1734.229], [8788.519, -1764.711], [8818.899, -1825.668], [8819.013, -1871.392], [8849.393, -1932.349], [8849.735, -2069.519], [8864.887, -2084.757], [8865.876, -2481.027], [8850.8, -2496.272], [8851.028, -2587.719], [8835.953, -2602.963], [8821.143, -2724.896], [8806.068, -2740.141], [8791.144, -2816.351], [8746.031, -2907.808], [8550.047, -3105.991], [8504.934, -3197.449], [8505.011, -3227.931], [8489.935, -3243.176], [8490.125, -3319.382], [8475.049, -3334.627], [8475.392, -3471.797], [8460.316, -3487.042], [8460.392, -3517.524], [8415.279, -3608.982], [8339.901, -3685.206], [8309.711, -3700.455], [8113.233, -3700.503], [8098.081, -3685.265], [7962.058, -3685.298], [7931.907, -3715.788], [7901.679, -3715.795], [7856.414, -3746.289], [7826.187, -3746.296], [7765.808, -3776.793], [7629.784, -3776.826], [7554.064, -3715.88], [7538.722, -3624.437], [7523.57, -3609.199], [7508.304, -3548.238], [7387.09, -3426.338], [7356.825, -3411.105], [7311.483, -3411.116], [7296.332, -3395.878], [7235.877, -3395.893], [7220.801, -3411.138], [7160.346, -3411.152], [7145.271, -3426.397], [7009.285, -3441.672], [6994.133, -3426.434], [6933.64, -3411.208], [6903.337, -3380.733], [6857.729, -3274.056], [6797.122, -3213.106], [6706.326, -3167.404], [6676.099, -3167.412], [6660.947, -3152.174], [6630.719, -3152.182], [6570.188, -3121.714], [6494.62, -3121.732], [6479.468, -3106.495], [6373.672, -3106.521], [6358.596, -3121.765], [6298.142, -3121.78], [6237.763, -3152.277], [6207.611, -3182.767], [6207.687, -3213.249], [6192.612, -3228.494], [6193.03, -3396.147], [6208.182, -3411.384], [6208.41, -3502.831], [6223.562, -3518.068], [6208.753, -3640.001], [6118.299, -3731.47], [6103.185, -3731.474], [6042.844, -3777.212], [6012.617, -3777.219], [5997.541, -3792.464], [5937.086, -3792.479], [5922.01, -3807.724], [5816.176, -3792.508], [5785.911, -3777.275], [5710.152, -3701.087], [5679.773, -3640.13], [5679.696, -3609.648], [5649.317, -3548.69], [5649.203, -3502.967], [5634.051, -3487.73], [5633.861, -3411.524], [5618.709, -3396.286], [5618.519, -3320.081], [5603.367, -3304.843], [5603.253, -3259.12], [5588.101, -3243.882], [5588.025, -3213.4], [5572.873, -3198.162], [5542.342, -3076.241], [5481.582, -2954.326], [5375.482, -2832.423], [5345.255, -2832.43], [5330.103, -2817.192], [5239.421, -2817.214], [5118.663, -2878.208], [5028.209, -2969.677], [5013.209, -3015.405], [4937.907, -3122.111], [4938.059, -3183.076], [4922.983, -3198.32], [4923.364, -3350.732], [4878.251, -3442.19], [4817.948, -3503.169], [4817.986, -3518.41], [4757.684, -3579.39], [4757.722, -3594.631], [4667.268, -3686.1], [4607.117, -3808.044], [4546.852, -3884.264], [4501.777, -3990.963], [4471.626, -4021.453], [4381.4, -4204.369], [4366.515, -4295.819], [4351.439, -4311.064], [4351.515, -4341.546], [4336.44, -4356.791], [4321.478, -4417.76], [4246.1, -4493.984], [4185.721, -4524.481], [3913.674, -4524.547], [3792.612, -4463.612], [3701.93, -4463.634], [3686.854, -4478.879], [3641.513, -4478.89], [3611.362, -4509.379], [3490.604, -4570.373], [3430.149, -4570.388], [3415.073, -4585.633], [3294.164, -4585.662], [3233.633, -4555.195], [3172.988, -4479.004], [3172.912, -4448.521], [3142.532, -4387.564], [3142.418, -4341.841], [3096.848, -4250.405], [2945.331, -4098.03], [2930.217, -4098.034], [2884.762, -4052.321], [2869.648, -4052.325], [2824.193, -4006.612], [2809.079, -4006.616], [2763.624, -3960.904], [2748.51, -3960.907], [2642.448, -3854.245], [2642.41, -3839.004], [2612.106, -3808.529], [2596.84, -3747.568], [2581.689, -3732.331], [2581.346, -3595.16], [2566.195, -3579.923], [2566.004, -3503.717], [2535.625, -3442.76], [2475.018, -3381.81], [2323.69, -3305.641], [2247.932, -3229.453], [2232.59, -3138.01], [2247.665, -3122.765], [2247.551, -3077.042], [2292.664, -2985.584], [2292.246, -2817.931], [2231.639, -2756.981], [2050.274, -2757.026], [2035.198, -2772.27], [1989.857, -2772.281], [1974.782, -2787.526], [1929.44, -2787.537], [1914.365, -2802.782], [1838.834, -2818.042], [1687.963, -2924.766], [1672.85, -2924.77], [1642.698, -2955.26], [1597.395, -2970.512], [1567.244, -3001.002], [1506.865, -3031.499], [1461.524, -3031.51], [1446.448, -3046.755], [1355.728, -3031.535], [1340.576, -3016.298], [1295.235, -3016.309], [1280.083, -3001.071], [1234.742, -3001.083], [1219.59, -2985.845], [1159.135, -2985.86], [1143.984, -2970.622], [1083.529, -2970.637], [1068.377, -2955.4], [1007.922, -2955.414], [992.77, -2940.177], [917.202, -2940.195], [902.05, -2924.958], [781.102, -2909.746], [765.95, -2894.508], [584.548, -2879.311], [569.396, -2864.074]]}, 'navigation_regions': [{'name': 'North-West', 'polygon': [[7978.009, -4020.6], [6965.389, -4020.846], [6963.107, -3106.377], [7975.726, -3106.131]]}, {'name': 'North', 'polygon': [[3733.07, -4829.414], [2312.381, -4829.76], [2309.109, -3519.021], [3729.799, -3518.675]]}, {'name': 'North-East', 'polygon': [[-3885.575, -4297.827], [-5034.217, -4298.106], [-5036.918, -3215.984], [-3888.276, -3215.705]]}, {'name': 'South', 'polygon': [[1046.72, -333.925], [-1038.973, -334.433], [-1040.646, 336.178], [1045.047, 336.685]]}], 'reference_points': [{'name': 'North-West', 'x': 7481.05, 'y': -3569.5, 'z': 172.9}, {'name': 'North', 'x': 3005.7, 'y': -4165.4, 'z': 172.9}, {'name': 'North-East', 'x': -4454.1, 'y': -3761.0, 'z': 172.9}, {'name': 'South', 'x': 0.788, 'y': 2.415, 'z': 194.1}]}


def open_road_reference_file_path() -> Path:
    return Path(__file__).resolve().with_name(OPEN_ROAD_REFERENCE_FILENAME)


def load_open_road_reference() -> tuple[dict, str]:
    """Load the optional external Open Road reference JSON.

    If the JSON is missing or invalid, the built-in copy is used. The overlay
    is deliberately a 2-D documentation reference, not surveyed road geometry.
    """
    path = open_road_reference_file_path()

    if path.exists():
        try:
            with path.open("r", encoding="utf-8") as handle:
                data = json.load(handle)

            if (
                data.get("format") == "qlabs_workspace_reference"
                and data.get("workspace") == "Open Road"
                and data.get("road_reference", {}).get("points")
            ):
                return data, path.name
        except (OSError, json.JSONDecodeError, TypeError, ValueError):
            pass

    return OPEN_ROAD_REFERENCE_FALLBACK, "built-in reference"


# ================================================================
# Helpers
# ================================================================

def scene_to_world(scene_pos: QPointF) -> tuple[float, float]:
    """Convert Qt scene coordinates to editor/QLabs-style XY meters."""
    x_m = scene_pos.x() / PIXELS_PER_METER
    y_m = -scene_pos.y() / PIXELS_PER_METER
    return x_m, y_m


def world_to_scene(x_m: float, y_m: float) -> QPointF:
    """Convert editor/QLabs-style XY meters to Qt scene coordinates."""
    return QPointF(
        x_m * PIXELS_PER_METER,
        -y_m * PIXELS_PER_METER,
    )

def _offset_world_polyline(
    points: list,
    offset_m: float,
    closed: bool = False,
) -> list[tuple[float, float]]:
    """Return a simple normal-offset copy of a world-XY polyline.

    This is used only to visualize approximate Open Road lane boundaries.
    It is intentionally not exported and should not be treated as surveyed
    road geometry.
    """
    clean = [
        (float(point[0]), float(point[1]))
        for point in points
        if len(point) >= 2
    ]

    count = len(clean)
    if count < 2:
        return clean

    result = []

    for index, (x, y) in enumerate(clean):
        if closed:
            prev_x, prev_y = clean[(index - 1) % count]
            next_x, next_y = clean[(index + 1) % count]
        elif index == 0:
            prev_x, prev_y = clean[index]
            next_x, next_y = clean[index + 1]
        elif index == count - 1:
            prev_x, prev_y = clean[index - 1]
            next_x, next_y = clean[index]
        else:
            prev_x, prev_y = clean[index - 1]
            next_x, next_y = clean[index + 1]

        tangent_x = next_x - prev_x
        tangent_y = next_y - prev_y
        length = math.hypot(tangent_x, tangent_y)

        if length <= 1e-9:
            result.append((x, y))
            continue

        # Left-hand unit normal in world XY.
        normal_x = -tangent_y / length
        normal_y = tangent_x / length

        result.append(
            (
                x + normal_x * float(offset_m),
                y + normal_y * float(offset_m),
            )
        )

    return result


def _world_polyline_path(
    points: list,
    closed: bool = False,
) -> QPainterPath:
    """Create a QPainterPath from world-XY coordinates."""
    path = QPainterPath()

    if not points:
        return path

    first = world_to_scene(
        float(points[0][0]),
        float(points[0][1]),
    )
    path.moveTo(first)

    for point in points[1:]:
        path.lineTo(
            world_to_scene(
                float(point[0]),
                float(point[1]),
            )
        )

    if closed:
        path.closeSubpath()

    return path


def snap_value(value: float, step: float) -> float:
    return round(value / step) * step


def normalize_angle(degrees: float) -> float:
    angle = degrees % 360.0
    if math.isclose(angle, 360.0):
        angle = 0.0
    return angle


def shortest_angle_difference(a_deg: float, b_deg: float) -> float:
    """Return signed shortest angle difference a-b in [-180, 180)."""
    return (a_deg - b_deg + 180.0) % 360.0 - 180.0


def endpoints_face_each_other(heading_a: float, heading_b: float) -> bool:
    """True when endpoint outward headings are approximately opposite."""
    difference = abs(shortest_angle_difference(heading_a, heading_b))
    return abs(180.0 - difference) <= SNAP_HEADING_TOLERANCE_DEG


def point_distance(a: QPointF, b: QPointF) -> float:
    return math.hypot(a.x() - b.x(), a.y() - b.y())


def make_object_id() -> str:
    return uuid.uuid4().hex[:12]



# ================================================================
# QLabs setup exporter
# ================================================================

def build_qlabs_setup_source(track_data: dict) -> str:
    # The returned source is standalone. It only imports Quanser libraries
    # when the exported file itself is run on the QLabs machine.
    embedded_track = repr(track_data)

    workspace_mode = str(
        track_data.get("workspace", {}).get("mode", WORKSPACE_CUSTOM)
    )
    workspace_label = (
        "Open Road"
        if workspace_mode == WORKSPACE_OPEN_ROAD
        else "Plane / selected custom workspace"
    )

    template = r'''# Generated by QLabs Track Editor v1.0.1
#
# Open Quanser Interactive Labs in the __WORKSPACE_LABEL__ workspace before running.
#
# v1.0 exports:
#   - road surfaces
#   - white road-edge markings
#   - dashed yellow road-center markings
#   - enabled lane-following guide lines
#   - traffic lights, road signs, crosswalks, and building boxes
#   - one QCar2 start pose (if present)
#   - selectable first/third-person QCar camera
#   - pedestrian/animal experiment actors with navmesh-free manual waypoint playback
#   - secondary scripted QCar2 actors
#   - waypoint paths with once/loop/ping-pong playback and optional despawn
#   - QCar position trigger zones and trigger actions
#   - outdoor weather preset and time of day
#   - the QCar2 real-time model

import math
import sys
import time

from qvl.qlabs import QuanserInteractiveLabs
from qvl.spline_line import QLabsSplineLine
from qvl.qcar2 import QLabsQCar2
from qvl.real_time import QLabsRealTime

from qvl.traffic_light import QLabsTrafficLight
from qvl.stop_sign import QLabsStopSign
from qvl.yield_sign import QLabsYieldSign
from qvl.roundabout_sign import QLabsRoundaboutSign
from qvl.crosswalk import QLabsCrosswalk
from qvl.basic_shape import QLabsBasicShape
from qvl.person import QLabsPerson
from qvl.animal import QLabsAnimal
from qvl.environment_outdoors import QLabsEnvironmentOutdoors

import pal.resources.rtmodels as rtmodels


TRACK_DATA = __TRACK_DATA__
ACTOR_HANDLES = {}
MOVEMENT_STATES = {}
NEXT_SECONDARY_QCAR_ACTOR_NUMBER = 100

# People and animals do not expose a direct transform setter. For manual
# waypoint playback we parent each moving character to a tiny BasicShape and
# move that proxy instead. Parenting is a QLabs kinematic relationship, so the
# character follows without using the Open World's navigation mesh.
MANUAL_CHARACTER_PROXY_SCALE = 0.001

ROAD_COLOR = [75 / 255.0, 75 / 255.0, 75 / 255.0]
ROAD_Z = 0.0

# All overlays sit slightly above the road surface to avoid z-fighting.
MARKING_Z = 0.021
GUIDE_Z = 0.023

EDGE_COLOR = [240 / 255.0, 240 / 255.0, 240 / 255.0]
CENTER_COLOR = [255 / 255.0, 215 / 255.0, 0 / 255.0]

# These are derived from the editor's visual constants:
# 20 px = 1 design meter
# edge inset = 8 px = 0.40 m
# edge width = 2 px = 0.10 m
# center width = 3 px = 0.15 m
EDGE_INSET_DESIGN_M = 0.40
EDGE_LINE_WIDTH_DESIGN_M = 0.10
CENTER_LINE_WIDTH_DESIGN_M = 0.15

# Approximate the editor's Qt dashed center line in full-scale design meters.
CENTER_DASH_LENGTH_DESIGN_M = 0.60
CENTER_DASH_GAP_DESIGN_M = 0.30

# Separate spline actors can show a tiny visual seam even when their
# centerline endpoints coincide. The exporter detects actual snapped
# endpoint pairs and places a short same-width road patch across the join.
JOIN_MATCH_TOLERANCE_DESIGN_M = 0.08
JOIN_PATCH_LENGTH_DESIGN_M = 0.60

GUIDE_PRESET_RGB = {
    "yellow": [255, 215, 0],
    "white": [255, 255, 255],
    "blue": [60, 160, 255],
    "red": [255, 80, 80],
}

DASH_LENGTH_DESIGN_M = 1.5
DASH_GAP_DESIGN_M = 1.0
CROSSWALK_QLABS_BASE_SCALE = 0.55
PATH_REACHED_TOLERANCE_DESIGN_M = 0.45


def apply_environment_settings(qlabs):
    settings = TRACK_DATA.get("environment", {}) or {}
    if not bool(settings.get("enabled", True)):
        return

    env = QLabsEnvironmentOutdoors(qlabs)
    weather_name = str(settings.get("weather", "clear_skies"))
    weather_map = {
        "clear_skies": env.CLEAR_SKIES,
        "partly_cloudy": env.PARTLY_CLOUDY,
        "cloudy": env.CLOUDY,
        "overcast": env.OVERCAST,
        "foggy": env.FOGGY,
        "light_rain": env.LIGHT_RAIN,
        "rain": env.RAIN,
        "thunderstorm": env.THUNDERSTORM,
        "light_snow": env.LIGHT_SNOW,
        "snow": env.SNOW,
        "blizzard": env.BLIZZARD,
    }
    env.set_weather_preset(weather_map.get(weather_name, env.CLEAR_SKIES))
    env.set_time_of_day(max(0.0, min(24.0, float(settings.get("time_of_day", 12.0)))))


def clamp(value, low, high):
    return max(low, min(high, value))


def project_scale():
    return float(TRACK_DATA.get("project", {}).get("scale_factor", 1.0))


def rotate_local_world(local_x, local_y, editor_rotation_deg):
    # Editor/Qt positive rotation is clockwise because screen Y points down.
    # QLabs/world uses the normal XY convention, therefore negate the angle.
    angle = math.radians(-float(editor_rotation_deg))
    c = math.cos(angle)
    s = math.sin(angle)
    return (
        local_x * c - local_y * s,
        local_x * s + local_y * c,
    )


def local_to_world_design(obj, local_x, local_y):
    rx, ry = rotate_local_world(
        local_x,
        local_y,
        obj.get("rotation_deg", 0.0),
    )
    return (
        float(obj.get("x", 0.0)) + rx,
        float(obj.get("y", 0.0)) + ry,
    )


def scaled_world_point(obj, local_x, local_y):
    scale = project_scale()
    x, y = local_to_world_design(obj, local_x, local_y)
    return x * scale, y * scale


def editor_yaw_to_qlabs_radians(editor_rotation_deg):
    return math.radians(-float(editor_rotation_deg))


def spawn_straight_spline(qlabs, p1, p2, width, color, z=ROAD_Z):
    spline = QLabsSplineLine(qlabs)
    spline.spawn(
        location=[0, 0, 0],
        scale=[1, 1, 1],
        configuration=QLabsSplineLine.LINEAR,
    )
    spline.set_points(
        color=color,
        pointList=[
            [p1[0], p1[1], z, width],
            [p2[0], p2[1], z, width],
        ],
        alignEndPointTangents=False,
    )


def spawn_arc_spline(
    qlabs,
    center,
    yaw_rad,
    radius,
    start_angle_deg,
    end_angle_deg,
    width,
    color,
    z=ROAD_Z,
):
    spline = QLabsSplineLine(qlabs)
    spline.spawn(
        location=[center[0], center[1], z],
        rotation=[0, 0, yaw_rad],
        scale=[1, 1, 1],
        configuration=QLabsSplineLine.CURVE,
    )

    sweep = abs(end_angle_deg - start_angle_deg)
    num_points = max(4, int(math.ceil(sweep / 12.0)) + 1)

    spline.arc_from_center_degrees(
        radius=radius,
        startAngle=start_angle_deg,
        endAngle=end_angle_deg,
        lineWidth=width,
        color=color,
        numSplinePoints=num_points,
    )


def spawn_dashed_straight(
    qlabs,
    p1,
    p2,
    width,
    color,
    z=GUIDE_Z,
    dash_design_m=DASH_LENGTH_DESIGN_M,
    gap_design_m=DASH_GAP_DESIGN_M,
):
    dx = p2[0] - p1[0]
    dy = p2[1] - p1[1]
    length = math.hypot(dx, dy)
    if length <= 1e-9:
        return

    ux = dx / length
    uy = dy / length

    scale = project_scale()
    dash = max(0.003, float(dash_design_m) * scale)
    gap = max(0.002, float(gap_design_m) * scale)

    cursor = 0.0
    while cursor < length - 1e-9:
        end = min(length, cursor + dash)
        a = (p1[0] + ux * cursor, p1[1] + uy * cursor)
        b = (p1[0] + ux * end, p1[1] + uy * end)
        spawn_straight_spline(qlabs, a, b, width, color, z=z)
        cursor = end + gap


def spawn_dashed_arc(
    qlabs,
    center,
    yaw_rad,
    radius,
    turn_angle_deg,
    width,
    color,
    z=GUIDE_Z,
    dash_design_m=DASH_LENGTH_DESIGN_M,
    gap_design_m=DASH_GAP_DESIGN_M,
):
    total_length = abs(math.radians(turn_angle_deg) * radius)
    if total_length <= 1e-9 or radius <= 1e-9:
        return

    scale = project_scale()
    dash = max(0.003, float(dash_design_m) * scale)
    gap = max(0.002, float(gap_design_m) * scale)

    cursor = 0.0
    while cursor < total_length - 1e-9:
        end = min(total_length, cursor + dash)

        start_angle = 90.0 - math.degrees(cursor / radius)
        end_angle = 90.0 - math.degrees(end / radius)

        spawn_arc_spline(
            qlabs,
            center=center,
            yaw_rad=yaw_rad,
            radius=radius,
            start_angle_deg=start_angle,
            end_angle_deg=end_angle,
            width=width,
            color=color,
            z=z,
        )
        cursor = end + gap


def resolved_guide_offset_design(obj):
    guide = obj.get("guide_line", {}) or {}
    position = str(guide.get("position", "left"))
    road_width = float(obj.get("width_m", 6.0))

    if position == "left":
        return -road_width / 4.0
    if position == "right":
        return road_width / 4.0
    if position == "center":
        return 0.0
    return float(guide.get("custom_offset_m", -road_width / 4.0))


def guide_color(obj):
    guide = obj.get("guide_line", {}) or {}
    name = str(guide.get("color", "yellow"))

    if name == "custom":
        rgb = guide.get("rgb", [255, 215, 0])
    else:
        rgb = GUIDE_PRESET_RGB.get(name, GUIDE_PRESET_RGB["yellow"])

    if not isinstance(rgb, (list, tuple)) or len(rgb) != 3:
        rgb = [255, 215, 0]

    return [
        clamp(float(rgb[0]), 0.0, 255.0) / 255.0,
        clamp(float(rgb[1]), 0.0, 255.0) / 255.0,
        clamp(float(rgb[2]), 0.0, 255.0) / 255.0,
    ]


def guide_width_effective(obj):
    guide = obj.get("guide_line", {}) or {}
    width = max(0.001, float(guide.get("width_m", 0.1)))
    if bool(guide.get("scale_width_with_project", True)):
        width *= project_scale()
    return width


def curve_center_design_local(radius_design, turn_angle_deg):
    # Center of the editor's 45/90 degree circular component,
    # represented in local world-oriented XY coordinates.
    theta = math.radians(turn_angle_deg)
    cx = -0.5 * radius_design * math.sin(theta)
    cy = -0.5 * radius_design * (1.0 + math.cos(theta))
    return cx, cy


def spawn_road_surface(qlabs, obj):
    obj_type = str(obj.get("type", ""))
    scale = project_scale()
    width = max(0.001, float(obj.get("width_m", 6.0)) * scale)

    if obj_type == "straight_road":
        length = float(obj.get("length_m", 20.0))
        p1 = scaled_world_point(obj, -length / 2.0, 0.0)
        p2 = scaled_world_point(obj, length / 2.0, 0.0)
        spawn_straight_spline(qlabs, p1, p2, width, ROAD_COLOR)
        return

    if obj_type == "road_end":
        length = float(obj.get("length_m", 8.0))
        p1 = scaled_world_point(obj, -length / 2.0, 0.0)
        p2 = scaled_world_point(obj, length / 2.0, 0.0)
        spawn_straight_spline(qlabs, p1, p2, width, ROAD_COLOR)
        return

    if obj_type in ("curve_45", "curve_90"):
        turn = 45.0 if obj_type == "curve_45" else 90.0
        radius_design = float(obj.get("radius_m", 10.0))
        local_center = curve_center_design_local(radius_design, turn)
        center = scaled_world_point(obj, local_center[0], local_center[1])

        spawn_arc_spline(
            qlabs,
            center=center,
            yaw_rad=editor_yaw_to_qlabs_radians(obj.get("rotation_deg", 0.0)),
            radius=radius_design * scale,
            start_angle_deg=90.0,
            end_angle_deg=90.0 - turn,
            width=width,
            color=ROAD_COLOR,
            z=ROAD_Z,
        )
        return

    if obj_type == "t_junction":
        arm = float(obj.get("arm_length_m", 12.0))

        p1 = scaled_world_point(obj, -arm, 0.0)
        p2 = scaled_world_point(obj, arm, 0.0)
        spawn_straight_spline(qlabs, p1, p2, width, ROAD_COLOR)

        # Stem is screen-down in the editor, which is world -Y.
        p3 = scaled_world_point(obj, 0.0, 0.0)
        p4 = scaled_world_point(obj, 0.0, -arm)
        spawn_straight_spline(qlabs, p3, p4, width, ROAD_COLOR)
        return

    if obj_type == "cross_intersection":
        arm = float(obj.get("arm_length_m", 12.0))

        p1 = scaled_world_point(obj, -arm, 0.0)
        p2 = scaled_world_point(obj, arm, 0.0)
        spawn_straight_spline(qlabs, p1, p2, width, ROAD_COLOR)

        p3 = scaled_world_point(obj, 0.0, arm)
        p4 = scaled_world_point(obj, 0.0, -arm)
        spawn_straight_spline(qlabs, p3, p4, width, ROAD_COLOR)



def marking_width_effective(design_width_m):
    return max(0.001, float(design_width_m) * project_scale())


def spawn_center_dashes_straight(qlabs, obj, p1_local, p2_local):
    p1 = scaled_world_point(obj, p1_local[0], p1_local[1])
    p2 = scaled_world_point(obj, p2_local[0], p2_local[1])
    spawn_dashed_straight(
        qlabs,
        p1,
        p2,
        marking_width_effective(CENTER_LINE_WIDTH_DESIGN_M),
        CENTER_COLOR,
        z=MARKING_Z,
        dash_design_m=CENTER_DASH_LENGTH_DESIGN_M,
        gap_design_m=CENTER_DASH_GAP_DESIGN_M,
    )


def spawn_road_markings(qlabs, obj):
    """Export the markings drawn by the editor for each road component."""
    obj_type = str(obj.get("type", ""))
    scale = project_scale()

    edge_width = marking_width_effective(EDGE_LINE_WIDTH_DESIGN_M)
    road_width_design = float(obj.get("width_m", 6.0))
    half_width = road_width_design / 2.0
    edge_offset = max(0.01, half_width - EDGE_INSET_DESIGN_M)

    # ------------------------------------------------------------
    # Straight road
    # ------------------------------------------------------------
    if obj_type == "straight_road":
        length = float(obj.get("length_m", 20.0))

        for local_y in (+edge_offset, -edge_offset):
            p1 = scaled_world_point(obj, -length / 2.0, local_y)
            p2 = scaled_world_point(obj, length / 2.0, local_y)
            spawn_straight_spline(
                qlabs, p1, p2, edge_width, EDGE_COLOR, z=MARKING_Z
            )

        spawn_center_dashes_straight(
            qlabs,
            obj,
            (-length / 2.0, 0.0),
            (length / 2.0, 0.0),
        )
        return

    # ------------------------------------------------------------
    # Road end
    # ------------------------------------------------------------
    if obj_type == "road_end":
        length = float(obj.get("length_m", 8.0))

        for local_y in (+edge_offset, -edge_offset):
            p1 = scaled_world_point(obj, -length / 2.0, local_y)
            p2 = scaled_world_point(obj, length / 2.0, local_y)
            spawn_straight_spline(
                qlabs, p1, p2, edge_width, EDGE_COLOR, z=MARKING_Z
            )

        # Center line stops 0.9 design meters before the closed end,
        # matching the editor.
        spawn_center_dashes_straight(
            qlabs,
            obj,
            (-length / 2.0, 0.0),
            (length / 2.0 - 0.90, 0.0),
        )

        # Closed road-end line is 0.30 design meters inside the end.
        end_x = length / 2.0 - 0.30
        a = scaled_world_point(obj, end_x, +edge_offset)
        b = scaled_world_point(obj, end_x, -edge_offset)
        spawn_straight_spline(
            qlabs,
            a,
            b,
            marking_width_effective(0.20),
            EDGE_COLOR,
            z=MARKING_Z,
        )
        return

    # ------------------------------------------------------------
    # Circular curves
    # ------------------------------------------------------------
    if obj_type in ("curve_45", "curve_90"):
        turn = 45.0 if obj_type == "curve_45" else 90.0
        radius_design = float(obj.get("radius_m", 10.0))
        local_center = curve_center_design_local(radius_design, turn)
        center = scaled_world_point(obj, local_center[0], local_center[1])
        yaw = editor_yaw_to_qlabs_radians(obj.get("rotation_deg", 0.0))

        outer_radius = (radius_design + edge_offset) * scale
        inner_radius = max(0.001, (radius_design - edge_offset) * scale)

        spawn_arc_spline(
            qlabs,
            center=center,
            yaw_rad=yaw,
            radius=outer_radius,
            start_angle_deg=90.0,
            end_angle_deg=90.0 - turn,
            width=edge_width,
            color=EDGE_COLOR,
            z=MARKING_Z,
        )
        spawn_arc_spline(
            qlabs,
            center=center,
            yaw_rad=yaw,
            radius=inner_radius,
            start_angle_deg=90.0,
            end_angle_deg=90.0 - turn,
            width=edge_width,
            color=EDGE_COLOR,
            z=MARKING_Z,
        )

        spawn_dashed_arc(
            qlabs,
            center=center,
            yaw_rad=yaw,
            radius=radius_design * scale,
            turn_angle_deg=turn,
            width=marking_width_effective(CENTER_LINE_WIDTH_DESIGN_M),
            color=CENTER_COLOR,
            z=MARKING_Z,
            dash_design_m=CENTER_DASH_LENGTH_DESIGN_M,
            gap_design_m=CENTER_DASH_GAP_DESIGN_M,
        )
        return

    # ------------------------------------------------------------
    # T-junction
    # ------------------------------------------------------------
    if obj_type == "t_junction":
        arm = float(obj.get("arm_length_m", 12.0))

        # Horizontal upper edge is continuous.
        a = scaled_world_point(obj, -arm, +edge_offset)
        b = scaled_world_point(obj, arm, +edge_offset)
        spawn_straight_spline(qlabs, a, b, edge_width, EDGE_COLOR, z=MARKING_Z)

        # Lower horizontal edge has an opening for the stem.
        for x1, x2 in ((-arm, -half_width), (half_width, arm)):
            a = scaled_world_point(obj, x1, -edge_offset)
            b = scaled_world_point(obj, x2, -edge_offset)
            spawn_straight_spline(qlabs, a, b, edge_width, EDGE_COLOR, z=MARKING_Z)

        # Stem side edges.
        for local_x in (-edge_offset, +edge_offset):
            a = scaled_world_point(obj, local_x, -half_width)
            b = scaled_world_point(obj, local_x, -arm)
            spawn_straight_spline(qlabs, a, b, edge_width, EDGE_COLOR, z=MARKING_Z)

        # Center markings stop at the mouth of the junction rather than
        # crossing the central shared road area.
        spawn_center_dashes_straight(qlabs, obj, (-arm, 0.0), (-half_width, 0.0))
        spawn_center_dashes_straight(qlabs, obj, (half_width, 0.0), (arm, 0.0))
        spawn_center_dashes_straight(qlabs, obj, (0.0, -half_width), (0.0, -arm))
        return

    # ------------------------------------------------------------
    # Four-way intersection
    # ------------------------------------------------------------
    if obj_type == "cross_intersection":
        arm = float(obj.get("arm_length_m", 12.0))

        # Horizontal road edge segments, leaving vertical opening.
        for local_y in (+edge_offset, -edge_offset):
            for x1, x2 in ((-arm, -half_width), (half_width, arm)):
                a = scaled_world_point(obj, x1, local_y)
                b = scaled_world_point(obj, x2, local_y)
                spawn_straight_spline(
                    qlabs, a, b, edge_width, EDGE_COLOR, z=MARKING_Z
                )

        # Vertical road edge segments, leaving horizontal opening.
        for local_x in (-edge_offset, +edge_offset):
            for y1, y2 in ((arm, half_width), (-half_width, -arm)):
                a = scaled_world_point(obj, local_x, y1)
                b = scaled_world_point(obj, local_x, y2)
                spawn_straight_spline(
                    qlabs, a, b, edge_width, EDGE_COLOR, z=MARKING_Z
                )

        # Four separate arm markings; keep the intersection center clear.
        spawn_center_dashes_straight(qlabs, obj, (-arm, 0.0), (-half_width, 0.0))
        spawn_center_dashes_straight(qlabs, obj, (half_width, 0.0), (arm, 0.0))
        spawn_center_dashes_straight(qlabs, obj, (0.0, arm), (0.0, half_width))
        spawn_center_dashes_straight(qlabs, obj, (0.0, -half_width), (0.0, -arm))
        return


def _rotate_vector_world(vx, vy, editor_rotation_deg):
    """Rotate a local world vector by the object's editor rotation."""
    return rotate_local_world(vx, vy, editor_rotation_deg)


def _connection_points_design(obj):
    """Return connectable road endpoints in full-scale design coordinates.

    Each entry contains:
      x, y      world/design position
      tx, ty    unit tangent axis (direction sign is irrelevant)
      width_m   road width
    """
    obj_type = str(obj.get("type", ""))
    width = float(obj.get("width_m", 6.0))
    rotation = float(obj.get("rotation_deg", 0.0))

    local = []

    if obj_type == "straight_road":
        length = float(obj.get("length_m", 20.0))
        local = [
            (-length / 2.0, 0.0, 1.0, 0.0),
            ( length / 2.0, 0.0, 1.0, 0.0),
        ]

    elif obj_type == "road_end":
        length = float(obj.get("length_m", 8.0))
        # Only the open side is connectable.
        local = [
            (-length / 2.0, 0.0, 1.0, 0.0),
        ]

    elif obj_type in ("curve_45", "curve_90"):
        turn = 45.0 if obj_type == "curve_45" else 90.0
        theta = math.radians(turn)
        radius = float(obj.get("radius_m", 10.0))

        dx = radius * math.sin(theta)
        dy = radius * (1.0 - math.cos(theta))

        # Editor scene Y is inverted relative to world Y.
        # Start tangent is horizontal; end tangent follows the arc.
        local = [
            (-dx / 2.0, +dy / 2.0, 1.0, 0.0),
            (+dx / 2.0, -dy / 2.0, math.cos(theta), -math.sin(theta)),
        ]

    elif obj_type == "t_junction":
        arm = float(obj.get("arm_length_m", 12.0))
        local = [
            (-arm, 0.0, 1.0, 0.0),
            (+arm, 0.0, 1.0, 0.0),
            (0.0, -arm, 0.0, 1.0),
        ]

    elif obj_type == "cross_intersection":
        arm = float(obj.get("arm_length_m", 12.0))
        local = [
            (-arm, 0.0, 1.0, 0.0),
            (+arm, 0.0, 1.0, 0.0),
            (0.0, +arm, 0.0, 1.0),
            (0.0, -arm, 0.0, 1.0),
        ]

    else:
        return []

    result = []

    for lx, ly, ltx, lty in local:
        x, y = local_to_world_design(obj, lx, ly)
        tx, ty = _rotate_vector_world(ltx, lty, rotation)

        mag = math.hypot(tx, ty)
        if mag <= 1e-9:
            continue

        result.append({
            "x": x,
            "y": y,
            "tx": tx / mag,
            "ty": ty / mag,
            "width_m": width,
            "object_id": obj.get("id"),
        })

    return result


def _axis_alignment(a, b):
    """Return absolute tangent-axis alignment in [0,1]."""
    return abs(a["tx"] * b["tx"] + a["ty"] * b["ty"])


def spawn_connection_patches(qlabs, objects):
    """Bridge tiny rendering seams only at actual road connections."""
    endpoints = []

    for obj in objects:
        endpoints.extend(_connection_points_design(obj))

    used_pairs = set()

    for i, a in enumerate(endpoints):
        for j in range(i + 1, len(endpoints)):
            b = endpoints[j]

            # Never connect two endpoints belonging to the same component.
            if a.get("object_id") == b.get("object_id"):
                continue

            dx = b["x"] - a["x"]
            dy = b["y"] - a["y"]
            distance = math.hypot(dx, dy)

            if distance > JOIN_MATCH_TOLERANCE_DESIGN_M:
                continue

            # The editor's snapping system only joins compatible headings.
            # Retain that protection in the exporter.
            if _axis_alignment(a, b) < math.cos(math.radians(12.0)):
                continue

            pair_key = tuple(sorted((i, j)))
            if pair_key in used_pairs:
                continue
            used_pairs.add(pair_key)

            cx_design = (a["x"] + b["x"]) / 2.0
            cy_design = (a["y"] + b["y"]) / 2.0

            # Average the tangent axes while making their signs consistent.
            dot = a["tx"] * b["tx"] + a["ty"] * b["ty"]
            sign = 1.0 if dot >= 0.0 else -1.0

            tx = a["tx"] + sign * b["tx"]
            ty = a["ty"] + sign * b["ty"]

            mag = math.hypot(tx, ty)
            if mag <= 1e-9:
                tx, ty = a["tx"], a["ty"]
            else:
                tx /= mag
                ty /= mag

            half_patch = JOIN_PATCH_LENGTH_DESIGN_M / 2.0

            p1_design = (
                cx_design - tx * half_patch,
                cy_design - ty * half_patch,
            )
            p2_design = (
                cx_design + tx * half_patch,
                cy_design + ty * half_patch,
            )

            scale = project_scale()

            p1 = (
                p1_design[0] * scale,
                p1_design[1] * scale,
            )
            p2 = (
                p2_design[0] * scale,
                p2_design[1] * scale,
            )

            patch_width = max(a["width_m"], b["width_m"]) * scale

            spawn_straight_spline(
                qlabs,
                p1,
                p2,
                patch_width,
                ROAD_COLOR,
                z=ROAD_Z + 0.0005,
            )


def spawn_guide(qlabs, obj):
    guide = obj.get("guide_line", {}) or {}
    if not bool(guide.get("enabled", False)):
        return

    obj_type = str(obj.get("type", ""))
    if obj_type not in ("straight_road", "road_end", "curve_45", "curve_90"):
        return

    style = str(guide.get("style", "solid"))
    width = guide_width_effective(obj)
    color = guide_color(obj)
    offset_design = resolved_guide_offset_design(obj)

    if obj_type in ("straight_road", "road_end"):
        length = float(obj.get("length_m", 20.0))

        # Editor local Y is the opposite sign of world local Y.
        local_y_world = -offset_design

        start_x = -length / 2.0
        end_x = length / 2.0

        if obj_type == "road_end":
            end_x -= min(0.9, max(0.0, length * 0.25))

        p1 = scaled_world_point(obj, start_x, local_y_world)
        p2 = scaled_world_point(obj, end_x, local_y_world)

        if style == "dashed":
            spawn_dashed_straight(qlabs, p1, p2, width, color, z=GUIDE_Z)
        else:
            spawn_straight_spline(qlabs, p1, p2, width, color, z=GUIDE_Z)
        return

    turn = 45.0 if obj_type == "curve_45" else 90.0
    radius_design = float(obj.get("radius_m", 10.0))
    local_center = curve_center_design_local(radius_design, turn)
    center = scaled_world_point(obj, local_center[0], local_center[1])

    # Matches the editor: left/negative offset is the larger curve radius.
    guide_radius_design = max(0.1, radius_design - offset_design)
    guide_radius = guide_radius_design * project_scale()
    yaw = editor_yaw_to_qlabs_radians(obj.get("rotation_deg", 0.0))

    if style == "dashed":
        spawn_dashed_arc(
            qlabs,
            center=center,
            yaw_rad=yaw,
            radius=guide_radius,
            turn_angle_deg=turn,
            width=width,
            color=color,
            z=GUIDE_Z,
        )
    else:
        spawn_arc_spline(
            qlabs,
            center=center,
            yaw_rad=yaw,
            radius=guide_radius,
            start_angle_deg=90.0,
            end_angle_deg=90.0 - turn,
            width=width,
            color=color,
            z=GUIDE_Z,
        )



def actor_effective_scale(obj):
    multiplier = max(0.001, float(obj.get("actor_scale", 1.0)))
    if bool(obj.get("scale_with_project", True)):
        multiplier *= project_scale()
    return multiplier


def actor_location(obj, extra_z=0.0):
    scale = project_scale()
    return [
        float(obj.get("x", 0.0)) * scale,
        float(obj.get("y", 0.0)) * scale,
        float(obj.get("z_m", 0.0)) * scale + extra_z,
    ]


def normalized_rgb(rgb, fallback=(145, 155, 170)):
    if not isinstance(rgb, (list, tuple)) or len(rgb) != 3:
        rgb = fallback
    return [
        clamp(float(rgb[0]), 0.0, 255.0) / 255.0,
        clamp(float(rgb[1]), 0.0, 255.0) / 255.0,
        clamp(float(rgb[2]), 0.0, 255.0) / 255.0,
    ]


def _movement_route_design(obj):
    """Return route points in design meters, including the actor start point."""
    start = [float(obj.get("x", 0.0)), float(obj.get("y", 0.0))]
    raw_points = obj.get("path_points", []) or []
    points = [start]

    for raw in raw_points:
        if isinstance(raw, (list, tuple)) and len(raw) >= 2:
            points.append([float(raw[0]), float(raw[1])])

    # Backward compatibility with v0.7 single destination fields.
    if len(points) == 1 and bool(obj.get("move_on_activation", False)):
        destination = [
            float(obj.get("destination_x_m", start[0])),
            float(obj.get("destination_y_m", start[1])),
        ]
        if math.hypot(destination[0] - start[0], destination[1] - start[1]) > 1e-6:
            points.append(destination)

    return points


def _scaled_route(obj):
    scale = project_scale()
    z = max(0.005, float(obj.get("z_m", 0.0)) * scale)
    return [[p[0] * scale, p[1] * scale, z] for p in _movement_route_design(obj)]


def _movement_speed_for_actor(actor, obj):
    """Return manual route speed in QLabs world metres/second.

    Character gait constants are used as the design-scale speed presets, then
    scaled with the project exactly like an environment QCar route. This keeps
    route travel time consistent when a full-size design is exported at 1:10.
    """
    obj_type = str(obj.get("type", ""))
    gait = str(obj.get("movement_gait", "walk"))
    scale = project_scale()

    if obj_type == "person":
        design_speed = {
            "standing": float(actor.STANDING),
            "walk": float(actor.WALK),
            "jog": float(actor.JOG),
            "run": float(actor.RUN),
        }.get(gait, float(actor.WALK))
        return max(0.0, design_speed * scale)

    if obj_type == "animal":
        animal_type = str(obj.get("animal_type", "goat"))
        speed_map = {
            "goat": {
                "standing": float(actor.GOAT_STANDING),
                "walk": float(actor.GOAT_WALK),
                "run": float(actor.GOAT_RUN),
            },
            "sheep": {
                "standing": float(actor.SHEEP_STANDING),
                "walk": float(actor.SHEEP_WALK),
                "run": float(actor.SHEEP_RUN),
            },
            "cow": {
                "standing": float(actor.COW_STANDING),
                "walk": float(actor.COW_WALK),
                "run": float(actor.COW_RUN),
            },
        }
        speeds = speed_map.get(animal_type, speed_map["goat"])
        design_speed = speeds.get(gait, speeds["walk"])
        return max(0.0, design_speed * scale)

    if obj_type == "secondary_qcar2":
        # Keep travel time invariant when the full design is scaled down.
        return max(0.01, float(obj.get("movement_speed_mps", 8.0)) * scale)

    return 0.0


def _register_actor_handle(obj, actor):
    """Expose an actor by both stable object id and readable identifier."""
    object_id = str(obj.get("id", ""))
    identifier = str(obj.get("identifier", ""))
    if object_id:
        ACTOR_HANDLES[object_id] = actor
    if identifier:
        ACTOR_HANDLES[identifier] = actor


def _unregister_actor_handle(obj):
    object_id = str(obj.get("id", ""))
    identifier = str(obj.get("identifier", ""))
    if object_id:
        ACTOR_HANDLES.pop(object_id, None)
    if identifier:
        ACTOR_HANDLES.pop(identifier, None)


def _create_character_motion_proxy(qlabs, actor, obj, start_location, start_yaw):
    """Create a tiny kinematic parent for a person or animal.

    QLabsPerson/QLabsAnimal expose AI move_to(), but not a direct set_transform
    API. QLabsActor parenting is generic, while QLabsBasicShape does expose
    set_transform(). A nearly invisible, collision-free BasicShape therefore
    gives us a documented transform target that carries the character with it.
    """
    proxy = QLabsBasicShape(qlabs)
    status, actor_number = proxy.spawn(
        location=list(start_location),
        rotation=[0.0, 0.0, float(start_yaw)],
        scale=[MANUAL_CHARACTER_PROXY_SCALE] * 3,
        configuration=QLabsBasicShape.SHAPE_CUBE,
        waitForConfirmation=True,
    )
    if status != 0:
        print("Unable to spawn manual motion proxy for", obj.get("id"), "status", status)
        return None

    # It is only a transform carrier; it must not interfere with physics.
    proxy.set_enable_collisions(False, waitForConfirmation=True)
    proxy.set_enable_dynamics(False, waitForConfirmation=True)

    parent_status = actor.parent_with_current_world_transform(
        parentClassID=QLabsBasicShape.ID_BASIC_SHAPE,
        parentActorNumber=actor_number,
        parentComponent=0,
        waitForConfirmation=True,
    )
    if parent_status != 0:
        print("Unable to parent manual character", obj.get("id"), "status", parent_status)
        try:
            proxy.destroy()
        except Exception:
            pass
        return None

    return proxy


def _finish_movement(object_id, state):
    actor = state["actor"]
    obj = state["obj"]
    proxy = state.get("motion_proxy")

    if bool(obj.get("despawn_on_finish", False)):
        try:
            actor.destroy()
        except Exception as exc:
            print("Unable to despawn actor", object_id, exc)
        if proxy is not None:
            try:
                proxy.destroy()
            except Exception as exc:
                print("Unable to despawn motion proxy", object_id, exc)
        _unregister_actor_handle(obj)

    MOVEMENT_STATES.pop(object_id, None)


def _advance_route_state(object_id, state):
    route = state["route"]
    mode = str(state["obj"].get("movement_mode", "once"))
    idx = int(state["target_index"])
    direction = int(state.get("direction", 1))

    if mode == "once":
        if idx >= len(route) - 1:
            _finish_movement(object_id, state)
            return False
        state["target_index"] = idx + 1
        return True

    if mode == "loop":
        state["target_index"] = 0 if idx >= len(route) - 1 else idx + 1
        return True

    # ping-pong
    if direction > 0 and idx >= len(route) - 1:
        state["direction"] = -1
        state["target_index"] = max(0, idx - 1)
    elif direction < 0 and idx <= 0:
        state["direction"] = 1
        state["target_index"] = min(len(route) - 1, idx + 1)
    else:
        state["target_index"] = idx + direction
    return True


def initialize_actor_movement(qlabs, obj, actor):
    if not bool(obj.get("move_on_activation", False)):
        return

    route = _scaled_route(obj)
    if len(route) < 2:
        return

    object_id = str(obj.get("id", ""))
    if not object_id:
        return


    obj_type = str(obj.get("type", ""))
    initial_yaw = editor_yaw_to_qlabs_radians(obj.get("rotation_deg", 0.0))
    motion_proxy = None

    if obj_type in {"person", "animal"}:
        motion_proxy = _create_character_motion_proxy(
            qlabs, actor, obj, route[0], initial_yaw
        )
        if motion_proxy is None:
            print("Manual route disabled for", object_id, "because proxy setup failed.")
            return

    state = {
        "actor": actor,
        "obj": obj,
        "route": route,
        "target_index": 1,
        "direction": 1,
        "position": list(route[0]),
        "last_update": time.time(),
        "yaw": initial_yaw,
        "motion_proxy": motion_proxy,
    }
    MOVEMENT_STATES[object_id] = state


def _set_manual_character_transform(state, position, yaw):
    proxy = state.get("motion_proxy")
    if proxy is None:
        return False
    return proxy.set_transform(
        location=list(position),
        rotation=[0.0, 0.0, float(yaw)],
        scale=[MANUAL_CHARACTER_PROXY_SCALE] * 3,
        waitForConfirmation=False,
    )


def _set_secondary_qcar_transform(actor, position, yaw):
    return actor.set_transform_and_request_state(
        location=list(position),
        rotation=[0.0, 0.0, float(yaw)],
        enableDynamics=False,
        headlights=False,
        leftTurnSignal=False,
        rightTurnSignal=False,
        brakeSignal=False,
        reverseSignal=False,
        waitForConfirmation=False,
    )


def update_actor_movements():
    """Advance all manual waypoint actors with one shared interpolation loop.

    People, animals, and environment QCars now use the same route-index,
    once/loop/ping-pong, dt, speed, and heading logic. Only the final transform
    command differs: QCars move themselves, while characters move their tiny
    BasicShape parent. No character move_to() call is made.
    """
    now = time.time()
    tolerance = max(0.03, PATH_REACHED_TOLERANCE_DESIGN_M * project_scale())

    for object_id, state in list(MOVEMENT_STATES.items()):
        actor = state["actor"]
        obj = state["obj"]
        route = state["route"]
        target = route[int(state["target_index"])]
        obj_type = str(obj.get("type", ""))

        if obj_type not in {"person", "animal", "secondary_qcar2"}:
            continue

        dt = max(0.001, min(0.10, now - float(state.get("last_update", now))))
        state["last_update"] = now

        pos = state["position"]
        dx = target[0] - pos[0]
        dy = target[1] - pos[1]
        distance = math.hypot(dx, dy)

        if distance <= tolerance:
            pos[0], pos[1], pos[2] = target[0], target[1], target[2]
            if not _advance_route_state(object_id, state):
                yaw = float(state.get("yaw", 0.0))
                if obj_type == "secondary_qcar2":
                    _set_secondary_qcar_transform(actor, pos, yaw)
                else:
                    _set_manual_character_transform(state, pos, yaw)
                continue

            target = state["route"][int(state["target_index"])]
            dx = target[0] - pos[0]
            dy = target[1] - pos[1]
            distance = math.hypot(dx, dy)

        yaw = float(state.get("yaw", 0.0))
        if distance > 1e-9:
            speed = _movement_speed_for_actor(actor, obj)
            travel = min(distance, speed * dt)
            ux, uy = dx / distance, dy / distance
            pos[0] += ux * travel
            pos[1] += uy * travel
            yaw = math.atan2(uy, ux)
            state["yaw"] = yaw

        if obj_type == "secondary_qcar2":
            _set_secondary_qcar_transform(actor, pos, yaw)
        else:
            _set_manual_character_transform(state, pos, yaw)


def spawn_scene_actor(qlabs, obj):
    global NEXT_SECONDARY_QCAR_ACTOR_NUMBER

    obj_type = str(obj.get("type", ""))
    yaw = editor_yaw_to_qlabs_radians(obj.get("rotation_deg", 0.0))
    actor_scale = actor_effective_scale(obj)
    uniform_scale = [actor_scale, actor_scale, actor_scale]
    configuration = int(obj.get("configuration", 0))

    if obj_type == "traffic_light":
        actor = QLabsTrafficLight(qlabs)
        actor.spawn(location=actor_location(obj), rotation=[0, 0, yaw], scale=uniform_scale,
                    configuration=configuration, waitForConfirmation=True)
        color_name = str(obj.get("traffic_color", "red"))
        color_map = {"off": actor.COLOR_NONE, "red": actor.COLOR_RED,
                     "yellow": actor.COLOR_YELLOW, "green": actor.COLOR_GREEN}
        actor.set_color(color=color_map.get(color_name, actor.COLOR_RED), waitForConfirmation=True)
        return actor

    if obj_type == "stop_sign":
        actor = QLabsStopSign(qlabs)
        actor.spawn(location=actor_location(obj), rotation=[0, 0, yaw], scale=uniform_scale,
                    configuration=0, waitForConfirmation=True)
        return actor

    if obj_type == "yield_sign":
        actor = QLabsYieldSign(qlabs)
        actor.spawn(location=actor_location(obj), rotation=[0, 0, yaw], scale=uniform_scale,
                    configuration=0, waitForConfirmation=True)
        return actor

    if obj_type == "roundabout_sign":
        actor = QLabsRoundaboutSign(qlabs)
        actor.spawn(location=actor_location(obj), rotation=[0, 0, yaw], scale=uniform_scale,
                    configuration=0, waitForConfirmation=True)
        return actor

    if obj_type == "crosswalk":
        actor = QLabsCrosswalk(qlabs)
        location = actor_location(obj)
        location[2] = max(location[2], 0.005)
        fitted_scale = actor_scale * CROSSWALK_QLABS_BASE_SCALE
        actor.spawn(location=location, rotation=[0, 0, yaw],
                    scale=[fitted_scale, fitted_scale, fitted_scale],
                    configuration=configuration, waitForConfirmation=True)
        return actor

    if obj_type == "building_box":
        actor = QLabsBasicShape(qlabs)
        dimension_scale = project_scale() if bool(obj.get("scale_with_project", True)) else 1.0
        length = max(0.01, float(obj.get("length_m", 10.0)) * dimension_scale)
        width = max(0.01, float(obj.get("width_m", 8.0)) * dimension_scale)
        height = max(0.01, float(obj.get("height_m", 5.0)) * dimension_scale)
        base_z = float(obj.get("z_m", 0.0)) * project_scale()
        center_location = [float(obj.get("x", 0.0)) * project_scale(),
                           float(obj.get("y", 0.0)) * project_scale(), base_z + height / 2.0]
        actor.spawn(location=center_location, rotation=[0, 0, yaw], scale=[length, width, height],
                    configuration=QLabsBasicShape.SHAPE_CUBE, waitForConfirmation=True)
        actor.set_material_properties(color=normalized_rgb(obj.get("rgb", [145, 155, 170])),
                                      roughness=0.65, metallic=False, waitForConfirmation=True)
        return actor

    if obj_type == "person":
        actor = QLabsPerson(qlabs)
        actor.spawn(location=actor_location(obj), rotation=[0, 0, yaw], scale=uniform_scale,
                    configuration=int(obj.get("person_configuration", 0)), waitForConfirmation=True)
        return actor

    if obj_type == "animal":
        actor = QLabsAnimal(qlabs)
        animal_type = str(obj.get("animal_type", "goat"))
        config_map = {"goat": actor.GOAT, "sheep": actor.SHEEP, "cow": actor.COW}
        actor.spawn(location=actor_location(obj), rotation=[0, 0, yaw], scale=uniform_scale,
                    configuration=config_map.get(animal_type, actor.GOAT), waitForConfirmation=True)
        return actor

    if obj_type == "secondary_qcar2":
        actor = QLabsQCar2(qlabs)
        actor_number = NEXT_SECONDARY_QCAR_ACTOR_NUMBER
        NEXT_SECONDARY_QCAR_ACTOR_NUMBER += 1
        actor.spawn_id(
            actorNumber=actor_number,
            location=actor_location(obj, extra_z=0.005),
            rotation=[0, 0, yaw],
            scale=uniform_scale,
            configuration=0,
            waitForConfirmation=True,
        )
        return actor

    return None


def spawn_scene_actors(qlabs, objects):
    scene_types = {"traffic_light", "stop_sign", "yield_sign", "roundabout_sign",
                   "crosswalk", "building_box", "person", "animal", "secondary_qcar2"}

    for obj in objects:
        obj_type = obj.get("type")
        if obj_type not in scene_types:
            continue
        if obj_type in {"person", "animal", "secondary_qcar2"} and str(obj.get("spawn_mode", "immediate")) == "triggered":
            continue

        actor = spawn_scene_actor(qlabs, obj)
        object_id = str(obj.get("id", ""))
        if actor is not None and object_id:
            _register_actor_handle(obj, actor)
            initialize_actor_movement(qlabs, obj, actor)


def object_by_id(objects, object_id):
    reference = str(object_id or "")
    for obj in objects:
        if str(obj.get("id", "")) == reference:
            return obj
        if str(obj.get("identifier", "")) == reference:
            return obj
    return None


def activate_experiment_actor(qlabs, objects, target_id):
    target_id = str(target_id or "")
    if not target_id:
        print("Trigger has no experiment actor target.")
        return
    if target_id in ACTOR_HANDLES:
        print("Experiment actor already active:", target_id)
        return

    target = object_by_id(objects, target_id)
    if target is None:
        print("Trigger target not found:", target_id)
        return
    if target.get("type") not in {"person", "animal", "secondary_qcar2"}:
        print("Trigger target is not a movable experiment actor:", target_id)
        return

    actor = spawn_scene_actor(qlabs, target)
    if actor is not None:
        _register_actor_handle(target, actor)
        initialize_actor_movement(qlabs, target, actor)
        print("Activated experiment actor:", target_id)


def set_target_traffic_light(objects, target_id, color_name):
    target_id = str(target_id or "")
    actor = ACTOR_HANDLES.get(target_id)
    target = object_by_id(objects, target_id)
    if actor is None or target is None or target.get("type") != "traffic_light":
        print("Traffic-light trigger target is unavailable:", target_id)
        return
    color_map = {"off": actor.COLOR_NONE, "red": actor.COLOR_RED,
                 "yellow": actor.COLOR_YELLOW, "green": actor.COLOR_GREEN}
    actor.set_color(color=color_map.get(str(color_name), actor.COLOR_RED), waitForConfirmation=True)
    print("Traffic light", target_id, "->", color_name)


def fire_trigger(qlabs, objects, trigger):
    action = str(trigger.get("action", "activate_actor"))
    target_id = trigger.get("target_id", "")
    if action == "activate_actor":
        activate_experiment_actor(qlabs, objects, target_id)
    elif action == "change_traffic_light":
        set_target_traffic_light(objects, target_id, str(trigger.get("traffic_color", "green")))
    else:
        print("Unknown trigger action:", action)


def run_experiment_runtime(qlabs, qcar, objects):
    triggers = [obj for obj in objects if obj.get("type") == "trigger_zone"]
    if not triggers and not MOVEMENT_STATES:
        return

    if triggers and qcar is None:
        print("Trigger zones require the primary QCar2 start actor; trigger monitoring disabled.")
        triggers = []

    print("Experiment runtime active. Press Ctrl+C to stop.")
    scale = project_scale()
    armed = {str(trigger.get("id")): True for trigger in triggers}
    fired = set()

    try:
        while triggers or MOVEMENT_STATES:
            if triggers and qcar is not None:
                status, location, rotation, qcar_scale = qcar.get_world_transform()
                if status:
                    qx, qy = float(location[0]), float(location[1])
                    for trigger in triggers:
                        trigger_id = str(trigger.get("id", ""))
                        if bool(trigger.get("one_shot", True)) and trigger_id in fired:
                            continue
                        cx = float(trigger.get("x", 0.0)) * scale
                        cy = float(trigger.get("y", 0.0)) * scale
                        radius = max(0.01, float(trigger.get("radius_m", 5.0)) * scale)
                        inside = math.hypot(qx - cx, qy - cy) <= radius
                        if inside and armed.get(trigger_id, True):
                            print("Trigger entered:", trigger_id)
                            fire_trigger(qlabs, objects, trigger)
                            armed[trigger_id] = False
                            if bool(trigger.get("one_shot", True)):
                                fired.add(trigger_id)
                        elif not inside:
                            armed[trigger_id] = True

            update_actor_movements()
            time.sleep(0.03)

            # Once all one-shot triggers are fired, only movement states keep runtime alive.
            if triggers and all(bool(t.get("one_shot", True)) and str(t.get("id", "")) in fired for t in triggers):
                triggers = []

    except KeyboardInterrupt:
        print("Experiment runtime stopped.")



def spawn_qcar2(qlabs):
    starts = [
        obj
        for obj in TRACK_DATA.get("objects", [])
        if obj.get("type") == "qcar2_start"
    ]

    if not starts:
        print("No QCar2 Start marker in track; roads only.")
        return None

    obj = starts[0]
    scale = project_scale()

    qcar = QLabsQCar2(qlabs)
    qcar.spawn_id(
        actorNumber=0,
        location=[
            float(obj.get("x", 0.0)) * scale,
            float(obj.get("y", 0.0)) * scale,
            2.0 * scale,  # Spawn high to reduce initial road/terrain collision risk.
        ],
        rotation=[
            0,
            0,
            editor_yaw_to_qlabs_radians(obj.get("rotation_deg", 0.0)),
        ],
        scale=[scale, scale, scale],
        configuration=0,
        waitForConfirmation=True,
    )
    _register_actor_handle(obj, qcar)
    return qcar


def main():
    print("Connecting to QLabs...")
    qlabs = QuanserInteractiveLabs()

    if not qlabs.open("localhost"):
        print("Unable to connect to QLabs.")
        print("Open QLabs in the __WORKSPACE_LABEL__ workspace and try again.")
        sys.exit(1)

    print("Connected to QLabs.")

    qlabs.destroy_all_spawned_actors()
    QLabsRealTime().terminate_all_real_time_models()
    time.sleep(0.5)

    apply_environment_settings(qlabs)

    objects = TRACK_DATA.get("objects", [])

    for obj in objects:
        spawn_road_surface(qlabs, obj)

    # Fill only genuine snapped road joints. This removes tiny spline-cap
    # seams without changing the editor's road coordinates or free endpoints.
    spawn_connection_patches(qlabs, objects)

    # Overlay road markings slightly above the road surface.
    for obj in objects:
        spawn_road_markings(qlabs, obj)

    # Lane-following guides sit a little higher than the normal markings.
    for obj in objects:
        spawn_guide(qlabs, obj)

    # Static QLabs scene actors.
    spawn_scene_actors(qlabs, objects)

    qcar = spawn_qcar2(qlabs)

    if qcar is not None:
        QLabsRealTime().start_real_time_model(rtmodels.QCAR2)
        time.sleep(0.5)

        starts = [
            obj
            for obj in objects
            if obj.get("type") == "qcar2_start"
        ]
        camera_view = (
            str(starts[0].get("camera_view", "third_person"))
            if starts
            else "third_person"
        )

        if camera_view == "first_person":
            qcar.possess(QLabsQCar2.CAMERA_CSI_FRONT)
        else:
            qcar.possess(QLabsQCar2.CAMERA_TRAILING)

    run_experiment_runtime(qlabs, qcar, objects)

    print(
        "QLabs track created. Project scale = "
        + str(TRACK_DATA.get("project", {}).get("scale_name", "1:1"))
    )


if __name__ == "__main__":
    main()
'''

    return template.replace("__TRACK_DATA__", embedded_track).replace("__WORKSPACE_LABEL__", workspace_label)


# ================================================================
# Base track component
# ================================================================

class TrackItem(QGraphicsItem):
    """Base class for movable/selectable track components."""

    TYPE_NAME = "track_item"
    DISPLAY_NAME = "Track Item"

    def __init__(self, object_id: str | None = None):
        super().__init__()

        self.object_id = object_id or make_object_id()

        # Human-readable alias used by selected actor classes. The stable
        # object_id remains the reference stored by trigger links.
        self.identifier = ""
        self._identifier_label = None
        self._identifier_label_y_px = 0.0

        self.setFlags(
            QGraphicsItem.GraphicsItemFlag.ItemIsMovable
            | QGraphicsItem.GraphicsItemFlag.ItemIsSelectable
            | QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges
        )

        self.setAcceptHoverEvents(True)
        self.setZValue(10)

        # Optional lane-following guide-line settings. Components that do not
        # support a guide simply ignore these values.
        self.guide_enabled = False
        self.guide_position = DEFAULT_GUIDE_POSITION
        self.guide_custom_offset_m = DEFAULT_GUIDE_CUSTOM_OFFSET_M
        self.guide_width_m = DEFAULT_GUIDE_WIDTH_M
        self.guide_color_name = DEFAULT_GUIDE_COLOR

        # Stores the user's custom RGB choice even while one of the
        # four preset colors is active.
        self.guide_rgb = tuple(DEFAULT_GUIDE_RGB)

        self.guide_style = DEFAULT_GUIDE_STYLE
        self.guide_scale_width = True

    # ------------------------------------------------------------
    # Human-readable identifier label
    # ------------------------------------------------------------

    def enable_identifier_label(self, label_y_px: float):
        """Create a non-interactive map label that stays readable while zooming."""
        self._identifier_label_y_px = float(label_y_px)

        if self._identifier_label is None:
            label = QGraphicsSimpleTextItem("", self)
            label.setFlag(
                QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations,
                True,
            )
            label.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
            label.setBrush(QBrush(QColor(245, 245, 245)))
            label.setZValue(1000)
            self._identifier_label = label

        self._update_identifier_label()

    def set_readable_identifier(self, identifier: str):
        self.identifier = str(identifier or "")
        self._update_identifier_label()

    def _update_identifier_label(self):
        if self._identifier_label is None:
            return

        self._identifier_label.setText(self.identifier)
        self._identifier_label.setVisible(bool(self.identifier))

        if not self.identifier:
            return

        rect = self._identifier_label.boundingRect()
        self._identifier_label.setPos(
            -rect.width() / 2.0,
            self._identifier_label_y_px,
        )

    # ------------------------------------------------------------
    # Lane-following guide API
    # ------------------------------------------------------------

    def supports_guide_line(self) -> bool:
        return False

    def resolved_guide_offset_m(self) -> float:
        """Return lateral guide offset in design meters.

        For a road travelling locally from left to right, negative is the
        driver's left side and positive is the driver's right side.
        """
        width_m = float(getattr(self, "width_m", DEFAULT_ROAD_WIDTH_M))
        if self.guide_position == "left":
            return -width_m / 4.0
        if self.guide_position == "right":
            return width_m / 4.0
        if self.guide_position == "center":
            return 0.0
        return float(self.guide_custom_offset_m)

    def guide_pen(self) -> QPen:
        if self.guide_color_name == "custom":
            r, g, b = self.guide_rgb
            color = QColor(
                max(0, min(255, int(r))),
                max(0, min(255, int(g))),
                max(0, min(255, int(b))),
            )
        else:
            color = GUIDE_COLORS.get(
                self.guide_color_name,
                GUIDE_COLORS["yellow"],
            )

        width_px = max(1.0, self.guide_width_m * PIXELS_PER_METER)
        style = (
            Qt.PenStyle.DashLine
            if self.guide_style == "dashed"
            else Qt.PenStyle.SolidLine
        )
        pen = QPen(color, width_px, style)
        pen.setCapStyle(Qt.PenCapStyle.FlatCap)
        return pen

    def guide_dict(self) -> dict:
        return {
            "enabled": bool(self.guide_enabled),
            "position": self.guide_position,
            "custom_offset_m": float(self.guide_custom_offset_m),
            "width_m": float(self.guide_width_m),
            "color": self.guide_color_name,
            "rgb": [
                int(self.guide_rgb[0]),
                int(self.guide_rgb[1]),
                int(self.guide_rgb[2]),
            ],
            "style": self.guide_style,
            "scale_width_with_project": bool(self.guide_scale_width),
        }

    def load_guide_dict(self, data: dict | None):
        data = data or {}
        self.guide_enabled = bool(data.get("enabled", False))
        self.guide_position = str(data.get("position", DEFAULT_GUIDE_POSITION))
        self.guide_custom_offset_m = float(
            data.get("custom_offset_m", DEFAULT_GUIDE_CUSTOM_OFFSET_M)
        )
        self.guide_width_m = max(0.01, float(data.get("width_m", DEFAULT_GUIDE_WIDTH_M)))
        self.guide_color_name = str(data.get("color", DEFAULT_GUIDE_COLOR))

        # v0.4 projects did not contain an explicit RGB field.
        rgb_data = data.get("rgb")
        if (
            isinstance(rgb_data, (list, tuple))
            and len(rgb_data) == 3
        ):
            self.guide_rgb = tuple(
                max(0, min(255, int(value)))
                for value in rgb_data
            )
        else:
            self.guide_rgb = tuple(
                GUIDE_COLOR_RGB.get(
                    self.guide_color_name,
                    DEFAULT_GUIDE_RGB,
                )
            )

        if (
            self.guide_color_name not in GUIDE_COLOR_RGB
            and self.guide_color_name != "custom"
        ):
            self.guide_color_name = DEFAULT_GUIDE_COLOR

        self.guide_style = str(data.get("style", DEFAULT_GUIDE_STYLE))
        self.guide_scale_width = bool(data.get("scale_width_with_project", True))

    # ------------------------------------------------------------
    # Connection API
    # ------------------------------------------------------------

    def connection_points_local(self) -> list[dict]:
        """Return local connection definitions.

        Each definition is:
            {
                "name": str,
                "pos": QPointF,
                "heading_deg": float
            }

        heading_deg is the *outward* direction from the component in Qt/local
        angle convention. It is used only to avoid snapping incompatible ends.
        """
        return []

    def connection_points_scene(self) -> list[dict]:
        points = []
        for connection in self.connection_points_local():
            points.append(
                {
                    "name": connection["name"],
                    "pos": self.mapToScene(connection["pos"]),
                    "heading_deg": normalize_angle(
                        connection["heading_deg"] + self.rotation()
                    ),
                }
            )
        return points

    def connection_points_scene_for_position(self, proposed_pos: QPointF) -> list[dict]:
        """Connection points as if the item were located at proposed_pos.

        ItemPositionChange occurs before Qt applies the new position. Since all
        track items are top-level scene items, a simple position delta gives the
        proposed scene endpoint coordinates.
        """
        delta = proposed_pos - self.pos()
        points = []
        for connection in self.connection_points_scene():
            points.append(
                {
                    "name": connection["name"],
                    "pos": connection["pos"] + delta,
                    "heading_deg": connection["heading_deg"],
                }
            )
        return points

    def draw_connection_handles(self, painter: QPainter):
        """Draw endpoint handles only while the component is selected."""
        if not self.isSelected():
            return

        handle_radius = 5.0
        handle_pen = QPen(CONNECTION_OUTLINE_COLOR, 1.5)
        handle_pen.setCosmetic(True)

        painter.setPen(handle_pen)
        painter.setBrush(CONNECTION_COLOR)

        for connection in self.connection_points_local():
            p = connection["pos"]
            painter.drawEllipse(
                p,
                handle_radius,
                handle_radius,
            )

    # ------------------------------------------------------------
    # Shared interaction
    # ------------------------------------------------------------

    def itemChange(self, change, value):
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionChange:
            if isinstance(value, QPointF):
                # First snap the item's origin to the 1 m grid.
                proposed = QPointF(
                    snap_value(value.x(), GRID_PIXELS),
                    snap_value(value.y(), GRID_PIXELS),
                )

                # Then allow endpoint snapping to override the origin grid.
                scene = self.scene()
                if isinstance(scene, TrackScene):
                    proposed = scene.snap_item_position_to_endpoint(self, proposed)

                return proposed

        result = super().itemChange(change, value)

        if change in (
            QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged,
            QGraphicsItem.GraphicsItemChange.ItemSelectedHasChanged,
            QGraphicsItem.GraphicsItemChange.ItemRotationHasChanged,
        ):
            scene = self.scene()
            if isinstance(scene, TrackScene):
                scene.notify_selection_or_geometry_changed()

        return result

    def rotate_step(self, amount_deg: float):
        self.setRotation(normalize_angle(self.rotation() + amount_deg))

        # After rotating, try a tiny endpoint re-snap without changing the
        # current center intentionally. This makes a manually aligned piece
        # settle onto a nearby connection after the correct heading is chosen.
        scene = self.scene()
        if isinstance(scene, TrackScene):
            snapped = scene.snap_item_position_to_endpoint(self, self.pos())
            if snapped != self.pos():
                self.setPos(snapped)
            scene.notify_selection_or_geometry_changed()

    # ------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------

    def base_dict(self) -> dict:
        x_m, y_m = scene_to_world(self.pos())
        data = {
            "type": self.TYPE_NAME,
            "id": self.object_id,
            "x": round(x_m, 4),
            "y": round(y_m, 4),
            "rotation_deg": round(normalize_angle(self.rotation()), 4),
        }
        if self.identifier:
            data["identifier"] = self.identifier
        return data

    def to_dict(self) -> dict:
        raise NotImplementedError

    @classmethod
    def from_dict(cls, data: dict):
        raise NotImplementedError

    def duplicate(self):
        """Create a copy with a new object id and a new readable alias."""
        data = self.to_dict().copy()
        data["id"] = make_object_id()
        data.pop("identifier", None)
        return create_track_item_from_dict(data)

    def selection_text(self) -> str:
        x_m, y_m = scene_to_world(self.pos())
        identifier_line = (
            f"Identifier: {self.identifier}\n"
            if self.identifier
            else ""
        )
        return (
            f"{self.DISPLAY_NAME}\n"
            f"{identifier_line}"
            f"X: {x_m:.1f} m\n"
            f"Y: {y_m:.1f} m\n"
            f"Rotation: {normalize_angle(self.rotation()):.1f}°"
        )


# ================================================================
# Straight road
# ================================================================

class StraightRoadItem(TrackItem):
    TYPE_NAME = "straight_road"
    DISPLAY_NAME = "Straight Road"

    def __init__(
        self,
        length_m: float = DEFAULT_ROAD_LENGTH_M,
        width_m: float = DEFAULT_ROAD_WIDTH_M,
        object_id: str | None = None,
    ):
        super().__init__(object_id=object_id)

        self.length_m = float(length_m)
        self.width_m = float(width_m)

    def supports_guide_line(self) -> bool:
        return True

    @property
    def length_px(self) -> float:
        return self.length_m * PIXELS_PER_METER

    @property
    def width_px(self) -> float:
        return self.width_m * PIXELS_PER_METER

    def boundingRect(self) -> QRectF:
        margin = 8.0
        return QRectF(
            -self.length_px / 2.0 - margin,
            -self.width_px / 2.0 - margin,
            self.length_px + margin * 2.0,
            self.width_px + margin * 2.0,
        )

    def paint(self, painter: QPainter, option, widget=None):
        road_rect = QRectF(
            -self.length_px / 2.0,
            -self.width_px / 2.0,
            self.length_px,
            self.width_px,
        )

        # ========================================================
        # Road body
        # ========================================================
        # This is the exact rendering approach confirmed working
        # in the v0.1 discussion: no permanent segment outline.
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(ROAD_COLOR)
        painter.drawRect(road_rect)

        # ========================================================
        # White edge lines
        # ========================================================
        edge_pen = QPen(EDGE_LINE_COLOR, EDGE_LINE_WIDTH_PX)
        painter.setPen(edge_pen)

        painter.drawLine(
            QPointF(-self.length_px / 2.0, -self.width_px / 2.0 + EDGE_LINE_INSET_PX),
            QPointF(self.length_px / 2.0, -self.width_px / 2.0 + EDGE_LINE_INSET_PX),
        )

        painter.drawLine(
            QPointF(-self.length_px / 2.0, self.width_px / 2.0 - EDGE_LINE_INSET_PX),
            QPointF(self.length_px / 2.0, self.width_px / 2.0 - EDGE_LINE_INSET_PX),
        )

        # ========================================================
        # Yellow center line
        # ========================================================
        center_pen = QPen(
            CENTER_LINE_COLOR,
            CENTER_LINE_WIDTH_PX,
            Qt.PenStyle.DashLine,
        )
        painter.setPen(center_pen)

        painter.drawLine(
            QPointF(-self.length_px / 2.0, 0),
            QPointF(self.length_px / 2.0, 0),
        )

        # ========================================================
        # Optional lane-following guide line
        # ========================================================
        if self.guide_enabled:
            offset_px = self.resolved_guide_offset_m() * PIXELS_PER_METER
            painter.setPen(self.guide_pen())
            painter.drawLine(
                QPointF(-self.length_px / 2.0, offset_px),
                QPointF(self.length_px / 2.0, offset_px),
            )

        # ========================================================
        # Selection outline
        # ========================================================
        if self.isSelected():
            selection_pen = QPen(SELECTION_COLOR, SELECTION_LINE_WIDTH_PX)
            selection_pen.setCosmetic(True)

            painter.setPen(selection_pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(road_rect)

        self.draw_connection_handles(painter)

    def connection_points_local(self) -> list[dict]:
        return [
            {
                "name": "start",
                "pos": QPointF(-self.length_px / 2.0, 0.0),
                "heading_deg": 180.0,
            },
            {
                "name": "end",
                "pos": QPointF(self.length_px / 2.0, 0.0),
                "heading_deg": 0.0,
            },
        ]

    def to_dict(self) -> dict:
        data = self.base_dict()
        data.update(
            {
                "length_m": self.length_m,
                "width_m": self.width_m,
                "guide_line": self.guide_dict(),
            }
        )
        return data

    @classmethod
    def from_dict(cls, data: dict):
        item = cls(
            length_m=float(data.get("length_m", DEFAULT_ROAD_LENGTH_M)),
            width_m=float(data.get("width_m", DEFAULT_ROAD_WIDTH_M)),
            object_id=data.get("id"),
        )
        item.setPos(
            world_to_scene(
                float(data.get("x", 0.0)),
                float(data.get("y", 0.0)),
            )
        )
        item.setRotation(float(data.get("rotation_deg", 0.0)))
        item.load_guide_dict(data.get("guide_line"))
        return item

    def selection_text(self) -> str:
        return (
            super().selection_text()
            + f"\nLength: {self.length_m:.1f} m"
            + f"\nWidth: {self.width_m:.1f} m"
        )


# ================================================================
# 90-degree curved road
# ================================================================

class Curve90RoadItem(TrackItem):
    """Quarter-circle road.

    At rotation 0 degrees:
        - start endpoint is at upper-left of the curve's center box,
          with outward heading 180 degrees (left).
        - end endpoint is at lower-right,
          with outward heading 90 degrees (down in Qt scene coordinates).

    The item can be rotated in 15-degree increments like a straight road.
    """

    TYPE_NAME = "curve_90"
    DISPLAY_NAME = "90° Curve"

    def __init__(
        self,
        radius_m: float = DEFAULT_CURVE_RADIUS_M,
        width_m: float = DEFAULT_ROAD_WIDTH_M,
        object_id: str | None = None,
    ):
        super().__init__(object_id=object_id)

        self.radius_m = float(radius_m)
        self.width_m = float(width_m)

        if self.radius_m <= self.width_m / 2.0:
            # Keep the inner edge radius positive.
            self.radius_m = self.width_m / 2.0 + 0.5

    def supports_guide_line(self) -> bool:
        return True

    @property
    def radius_px(self) -> float:
        return self.radius_m * PIXELS_PER_METER

    @property
    def width_px(self) -> float:
        return self.width_m * PIXELS_PER_METER

    def _circle_center(self) -> QPointF:
        # Centerline runs from (-r/2,-r/2) to (+r/2,+r/2).
        return QPointF(-self.radius_px / 2.0, self.radius_px / 2.0)

    def _arc_path_for_radius(self, arc_radius_px: float) -> QPainterPath:
        """Quarter-circle path around the fixed curve center."""
        c = self._circle_center()
        r = arc_radius_px
        k = 0.5522847498307936 * r

        start = QPointF(c.x(), c.y() - r)
        end = QPointF(c.x() + r, c.y())

        path = QPainterPath(start)
        path.cubicTo(
            QPointF(c.x() + k, c.y() - r),
            QPointF(c.x() + r, c.y() - k),
            end,
        )
        return path

    def center_path(self) -> QPainterPath:
        return self._arc_path_for_radius(self.radius_px)

    def shape(self) -> QPainterPath:
        stroker = QPainterPathStroker()
        stroker.setWidth(self.width_px)
        stroker.setCapStyle(Qt.PenCapStyle.FlatCap)
        stroker.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        return stroker.createStroke(self.center_path())

    def boundingRect(self) -> QRectF:
        shape_rect = self.shape().boundingRect()
        return shape_rect.adjusted(-8.0, -8.0, 8.0, 8.0)

    def paint(self, painter: QPainter, option, widget=None):
        painter.setBrush(Qt.BrushStyle.NoBrush)

        # ========================================================
        # Road body
        # ========================================================
        road_pen = QPen(ROAD_COLOR, self.width_px)
        road_pen.setCapStyle(Qt.PenCapStyle.FlatCap)
        road_pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(road_pen)
        painter.drawPath(self.center_path())

        # ========================================================
        # White edge lines
        # ========================================================
        half_width = self.width_px / 2.0
        edge_offset = max(1.0, half_width - EDGE_LINE_INSET_PX)

        outer_radius = self.radius_px + edge_offset
        inner_radius = max(2.0, self.radius_px - edge_offset)

        edge_pen = QPen(EDGE_LINE_COLOR, EDGE_LINE_WIDTH_PX)
        painter.setPen(edge_pen)
        painter.drawPath(self._arc_path_for_radius(outer_radius))
        painter.drawPath(self._arc_path_for_radius(inner_radius))

        # ========================================================
        # Yellow dashed center line
        # ========================================================
        center_pen = QPen(
            CENTER_LINE_COLOR,
            CENTER_LINE_WIDTH_PX,
            Qt.PenStyle.DashLine,
        )
        painter.setPen(center_pen)
        painter.drawPath(self.center_path())

        # ========================================================
        # Optional lane-following guide line
        # ========================================================
        if self.guide_enabled:
            offset_px = self.resolved_guide_offset_m() * PIXELS_PER_METER
            guide_radius = max(2.0, self.radius_px - offset_px)
            painter.setPen(self.guide_pen())
            painter.drawPath(self._arc_path_for_radius(guide_radius))

        # ========================================================
        # Selection outline around actual curved road shape
        # ========================================================
        if self.isSelected():
            selection_pen = QPen(SELECTION_COLOR, SELECTION_LINE_WIDTH_PX)
            selection_pen.setCosmetic(True)
            painter.setPen(selection_pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawPath(self.shape())

        self.draw_connection_handles(painter)

    def connection_points_local(self) -> list[dict]:
        r = self.radius_px
        return [
            {
                "name": "start",
                "pos": QPointF(-r / 2.0, -r / 2.0),
                "heading_deg": 180.0,
            },
            {
                "name": "end",
                "pos": QPointF(r / 2.0, r / 2.0),
                "heading_deg": 90.0,
            },
        ]

    def to_dict(self) -> dict:
        data = self.base_dict()
        data.update(
            {
                "radius_m": self.radius_m,
                "width_m": self.width_m,
                "guide_line": self.guide_dict(),
            }
        )
        return data

    @classmethod
    def from_dict(cls, data: dict):
        item = cls(
            radius_m=float(data.get("radius_m", DEFAULT_CURVE_RADIUS_M)),
            width_m=float(data.get("width_m", DEFAULT_ROAD_WIDTH_M)),
            object_id=data.get("id"),
        )
        item.setPos(
            world_to_scene(
                float(data.get("x", 0.0)),
                float(data.get("y", 0.0)),
            )
        )
        item.setRotation(float(data.get("rotation_deg", 0.0)))
        item.load_guide_dict(data.get("guide_line"))
        return item

    def selection_text(self) -> str:
        return (
            super().selection_text()
            + f"\nRadius: {self.radius_m:.1f} m"
            + f"\nWidth: {self.width_m:.1f} m"
        )



# ================================================================
# 45-degree curved road
# ================================================================

class Curve45RoadItem(Curve90RoadItem):
    """45-degree circular road bend.

    At rotation 0 degrees the road enters from the left and turns 45 degrees
    clockwise/downward in Qt scene coordinates. The connection headings remain
    compatible with the generic endpoint snapping system.
    """

    TYPE_NAME = "curve_45"
    DISPLAY_NAME = "45° Curve"
    TURN_ANGLE_DEG = 45.0

    def _centerline_end_delta(self) -> QPointF:
        theta = math.radians(self.TURN_ANGLE_DEG)
        return QPointF(
            self.radius_px * math.sin(theta),
            self.radius_px * (1.0 - math.cos(theta)),
        )

    def _circle_center(self) -> QPointF:
        end = self._centerline_end_delta()
        shift = QPointF(-end.x() / 2.0, -end.y() / 2.0)
        return QPointF(shift.x(), shift.y() + self.radius_px)

    def _arc_path_for_radius(self, arc_radius_px: float) -> QPainterPath:
        c = self._circle_center()
        theta = math.radians(self.TURN_ANGLE_DEG)
        start_phi = -math.pi / 2.0

        steps = 28
        phi = start_phi
        first = QPointF(
            c.x() + arc_radius_px * math.cos(phi),
            c.y() + arc_radius_px * math.sin(phi),
        )
        path = QPainterPath(first)

        for i in range(1, steps + 1):
            phi = start_phi + theta * (i / steps)
            path.lineTo(
                QPointF(
                    c.x() + arc_radius_px * math.cos(phi),
                    c.y() + arc_radius_px * math.sin(phi),
                )
            )

        return path

    def connection_points_local(self) -> list[dict]:
        end_delta = self._centerline_end_delta()
        start = QPointF(-end_delta.x() / 2.0, -end_delta.y() / 2.0)
        end = QPointF(end_delta.x() / 2.0, end_delta.y() / 2.0)
        return [
            {
                "name": "start",
                "pos": start,
                "heading_deg": 180.0,
            },
            {
                "name": "end",
                "pos": end,
                "heading_deg": self.TURN_ANGLE_DEG,
            },
        ]


# ================================================================
# Road end
# ================================================================

class RoadEndItem(TrackItem):
    """Short terminal road segment with one connectable end."""

    TYPE_NAME = "road_end"
    DISPLAY_NAME = "Road End"

    def __init__(
        self,
        length_m: float = DEFAULT_ROAD_END_LENGTH_M,
        width_m: float = DEFAULT_ROAD_WIDTH_M,
        object_id: str | None = None,
    ):
        super().__init__(object_id=object_id)
        self.length_m = float(length_m)
        self.width_m = float(width_m)

    def supports_guide_line(self) -> bool:
        return True

    @property
    def length_px(self) -> float:
        return self.length_m * PIXELS_PER_METER

    @property
    def width_px(self) -> float:
        return self.width_m * PIXELS_PER_METER

    def boundingRect(self) -> QRectF:
        margin = 8.0
        return QRectF(
            -self.length_px / 2.0 - margin,
            -self.width_px / 2.0 - margin,
            self.length_px + margin * 2.0,
            self.width_px + margin * 2.0,
        )

    def paint(self, painter: QPainter, option, widget=None):
        road_rect = QRectF(
            -self.length_px / 2.0,
            -self.width_px / 2.0,
            self.length_px,
            self.width_px,
        )

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(ROAD_COLOR)
        painter.drawRect(road_rect)

        edge_pen = QPen(EDGE_LINE_COLOR, EDGE_LINE_WIDTH_PX)
        painter.setPen(edge_pen)
        painter.drawLine(
            QPointF(-self.length_px / 2.0, -self.width_px / 2.0 + EDGE_LINE_INSET_PX),
            QPointF(self.length_px / 2.0, -self.width_px / 2.0 + EDGE_LINE_INSET_PX),
        )
        painter.drawLine(
            QPointF(-self.length_px / 2.0, self.width_px / 2.0 - EDGE_LINE_INSET_PX),
            QPointF(self.length_px / 2.0, self.width_px / 2.0 - EDGE_LINE_INSET_PX),
        )

        center_pen = QPen(
            CENTER_LINE_COLOR,
            CENTER_LINE_WIDTH_PX,
            Qt.PenStyle.DashLine,
        )
        painter.setPen(center_pen)
        painter.drawLine(
            QPointF(-self.length_px / 2.0, 0.0),
            QPointF(self.length_px / 2.0 - 18.0, 0.0),
        )

        if self.guide_enabled:
            offset_px = self.resolved_guide_offset_m() * PIXELS_PER_METER
            painter.setPen(self.guide_pen())
            painter.drawLine(
                QPointF(-self.length_px / 2.0, offset_px),
                QPointF(self.length_px / 2.0 - 18.0, offset_px),
            )

        # Closed road-end marking.
        end_pen = QPen(EDGE_LINE_COLOR, 4)
        painter.setPen(end_pen)
        painter.drawLine(
            QPointF(self.length_px / 2.0 - 6.0, -self.width_px / 2.0 + 8.0),
            QPointF(self.length_px / 2.0 - 6.0, self.width_px / 2.0 - 8.0),
        )

        if self.isSelected():
            selection_pen = QPen(SELECTION_COLOR, SELECTION_LINE_WIDTH_PX)
            selection_pen.setCosmetic(True)
            painter.setPen(selection_pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(road_rect)

        self.draw_connection_handles(painter)

    def connection_points_local(self) -> list[dict]:
        return [
            {
                "name": "connection",
                "pos": QPointF(-self.length_px / 2.0, 0.0),
                "heading_deg": 180.0,
            }
        ]

    def to_dict(self) -> dict:
        data = self.base_dict()
        data.update(
            {
                "length_m": self.length_m,
                "width_m": self.width_m,
                "guide_line": self.guide_dict(),
            }
        )
        return data

    @classmethod
    def from_dict(cls, data: dict):
        item = cls(
            length_m=float(data.get("length_m", DEFAULT_ROAD_END_LENGTH_M)),
            width_m=float(data.get("width_m", DEFAULT_ROAD_WIDTH_M)),
            object_id=data.get("id"),
        )
        item.setPos(
            world_to_scene(
                float(data.get("x", 0.0)),
                float(data.get("y", 0.0)),
            )
        )
        item.setRotation(float(data.get("rotation_deg", 0.0)))
        item.load_guide_dict(data.get("guide_line"))
        return item

    def selection_text(self) -> str:
        return (
            super().selection_text()
            + f"\nLength: {self.length_m:.1f} m"
            + f"\nWidth: {self.width_m:.1f} m"
        )


# ================================================================
# T-junction
# ================================================================

class TJunctionItem(TrackItem):
    TYPE_NAME = "t_junction"
    DISPLAY_NAME = "T-Junction"

    def __init__(
        self,
        arm_length_m: float = DEFAULT_JUNCTION_ARM_M,
        width_m: float = DEFAULT_ROAD_WIDTH_M,
        object_id: str | None = None,
    ):
        super().__init__(object_id=object_id)
        self.arm_length_m = float(arm_length_m)
        self.width_m = float(width_m)

    @property
    def arm_px(self) -> float:
        return self.arm_length_m * PIXELS_PER_METER

    @property
    def width_px(self) -> float:
        return self.width_m * PIXELS_PER_METER

    def shape(self) -> QPainterPath:
        half_w = self.width_px / 2.0
        path = QPainterPath()
        path.addRect(QRectF(-self.arm_px, -half_w, self.arm_px * 2.0, self.width_px))
        path.addRect(QRectF(-half_w, -half_w, self.width_px, self.arm_px + half_w))
        return path.simplified()

    def boundingRect(self) -> QRectF:
        return self.shape().boundingRect().adjusted(-8.0, -8.0, 8.0, 8.0)

    def paint(self, painter: QPainter, option, widget=None):
        half_w = self.width_px / 2.0
        inset_y = half_w - EDGE_LINE_INSET_PX
        inset_x = half_w - EDGE_LINE_INSET_PX

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(ROAD_COLOR)
        painter.drawPath(self.shape())

        edge_pen = QPen(EDGE_LINE_COLOR, EDGE_LINE_WIDTH_PX)
        painter.setPen(edge_pen)

        # Horizontal top edge remains continuous.
        painter.drawLine(QPointF(-self.arm_px, -inset_y), QPointF(self.arm_px, -inset_y))

        # Bottom edge is broken where the stem opens.
        painter.drawLine(QPointF(-self.arm_px, inset_y), QPointF(-half_w, inset_y))
        painter.drawLine(QPointF(half_w, inset_y), QPointF(self.arm_px, inset_y))

        # Stem side edges.
        painter.drawLine(QPointF(-inset_x, half_w), QPointF(-inset_x, self.arm_px))
        painter.drawLine(QPointF(inset_x, half_w), QPointF(inset_x, self.arm_px))

        center_pen = QPen(CENTER_LINE_COLOR, CENTER_LINE_WIDTH_PX, Qt.PenStyle.DashLine)
        painter.setPen(center_pen)
        # Stop center markings at the central junction area.
        painter.drawLine(QPointF(-self.arm_px, 0.0), QPointF(-half_w, 0.0))
        painter.drawLine(QPointF(half_w, 0.0), QPointF(self.arm_px, 0.0))
        painter.drawLine(QPointF(0.0, half_w), QPointF(0.0, self.arm_px))

        if self.isSelected():
            selection_pen = QPen(SELECTION_COLOR, SELECTION_LINE_WIDTH_PX)
            selection_pen.setCosmetic(True)
            painter.setPen(selection_pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawPath(self.shape())

        self.draw_connection_handles(painter)

    def connection_points_local(self) -> list[dict]:
        return [
            {"name": "left", "pos": QPointF(-self.arm_px, 0.0), "heading_deg": 180.0},
            {"name": "right", "pos": QPointF(self.arm_px, 0.0), "heading_deg": 0.0},
            {"name": "stem", "pos": QPointF(0.0, self.arm_px), "heading_deg": 90.0},
        ]

    def to_dict(self) -> dict:
        data = self.base_dict()
        data.update({"arm_length_m": self.arm_length_m, "width_m": self.width_m})
        return data

    @classmethod
    def from_dict(cls, data: dict):
        item = cls(
            arm_length_m=float(data.get("arm_length_m", DEFAULT_JUNCTION_ARM_M)),
            width_m=float(data.get("width_m", DEFAULT_ROAD_WIDTH_M)),
            object_id=data.get("id"),
        )
        item.setPos(world_to_scene(float(data.get("x", 0.0)), float(data.get("y", 0.0))))
        item.setRotation(float(data.get("rotation_deg", 0.0)))
        return item

    def selection_text(self) -> str:
        return (
            super().selection_text()
            + f"\nArm length: {self.arm_length_m:.1f} m"
            + f"\nWidth: {self.width_m:.1f} m"
        )


# ================================================================
# 4-way intersection
# ================================================================

class CrossIntersectionItem(TrackItem):
    TYPE_NAME = "cross_intersection"
    DISPLAY_NAME = "4-Way Intersection"

    def __init__(
        self,
        arm_length_m: float = DEFAULT_JUNCTION_ARM_M,
        width_m: float = DEFAULT_ROAD_WIDTH_M,
        object_id: str | None = None,
    ):
        super().__init__(object_id=object_id)
        self.arm_length_m = float(arm_length_m)
        self.width_m = float(width_m)

    @property
    def arm_px(self) -> float:
        return self.arm_length_m * PIXELS_PER_METER

    @property
    def width_px(self) -> float:
        return self.width_m * PIXELS_PER_METER

    def shape(self) -> QPainterPath:
        half_w = self.width_px / 2.0
        path = QPainterPath()
        path.addRect(QRectF(-self.arm_px, -half_w, self.arm_px * 2.0, self.width_px))
        path.addRect(QRectF(-half_w, -self.arm_px, self.width_px, self.arm_px * 2.0))
        return path.simplified()

    def boundingRect(self) -> QRectF:
        return self.shape().boundingRect().adjusted(-8.0, -8.0, 8.0, 8.0)

    def paint(self, painter: QPainter, option, widget=None):
        half_w = self.width_px / 2.0
        edge = half_w - EDGE_LINE_INSET_PX

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(ROAD_COLOR)
        painter.drawPath(self.shape())

        edge_pen = QPen(EDGE_LINE_COLOR, EDGE_LINE_WIDTH_PX)
        painter.setPen(edge_pen)

        # Horizontal road edge segments, leaving openings for vertical road.
        painter.drawLine(QPointF(-self.arm_px, -edge), QPointF(-half_w, -edge))
        painter.drawLine(QPointF(half_w, -edge), QPointF(self.arm_px, -edge))
        painter.drawLine(QPointF(-self.arm_px, edge), QPointF(-half_w, edge))
        painter.drawLine(QPointF(half_w, edge), QPointF(self.arm_px, edge))

        # Vertical road edge segments, leaving openings for horizontal road.
        painter.drawLine(QPointF(-edge, -self.arm_px), QPointF(-edge, -half_w))
        painter.drawLine(QPointF(-edge, half_w), QPointF(-edge, self.arm_px))
        painter.drawLine(QPointF(edge, -self.arm_px), QPointF(edge, -half_w))
        painter.drawLine(QPointF(edge, half_w), QPointF(edge, self.arm_px))

        center_pen = QPen(CENTER_LINE_COLOR, CENTER_LINE_WIDTH_PX, Qt.PenStyle.DashLine)
        painter.setPen(center_pen)
        # Four separate arm markings; the intersection center stays clear.
        painter.drawLine(QPointF(-self.arm_px, 0.0), QPointF(-half_w, 0.0))
        painter.drawLine(QPointF(half_w, 0.0), QPointF(self.arm_px, 0.0))
        painter.drawLine(QPointF(0.0, -self.arm_px), QPointF(0.0, -half_w))
        painter.drawLine(QPointF(0.0, half_w), QPointF(0.0, self.arm_px))

        if self.isSelected():
            selection_pen = QPen(SELECTION_COLOR, SELECTION_LINE_WIDTH_PX)
            selection_pen.setCosmetic(True)
            painter.setPen(selection_pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawPath(self.shape())

        self.draw_connection_handles(painter)

    def connection_points_local(self) -> list[dict]:
        return [
            {"name": "left", "pos": QPointF(-self.arm_px, 0.0), "heading_deg": 180.0},
            {"name": "right", "pos": QPointF(self.arm_px, 0.0), "heading_deg": 0.0},
            {"name": "top", "pos": QPointF(0.0, -self.arm_px), "heading_deg": 270.0},
            {"name": "bottom", "pos": QPointF(0.0, self.arm_px), "heading_deg": 90.0},
        ]

    def to_dict(self) -> dict:
        data = self.base_dict()
        data.update({"arm_length_m": self.arm_length_m, "width_m": self.width_m})
        return data

    @classmethod
    def from_dict(cls, data: dict):
        item = cls(
            arm_length_m=float(data.get("arm_length_m", DEFAULT_JUNCTION_ARM_M)),
            width_m=float(data.get("width_m", DEFAULT_ROAD_WIDTH_M)),
            object_id=data.get("id"),
        )
        item.setPos(world_to_scene(float(data.get("x", 0.0)), float(data.get("y", 0.0))))
        item.setRotation(float(data.get("rotation_deg", 0.0)))
        return item

    def selection_text(self) -> str:
        return (
            super().selection_text()
            + f"\nArm length: {self.arm_length_m:.1f} m"
            + f"\nWidth: {self.width_m:.1f} m"
        )



# ================================================================
# QCar2 start marker
# ================================================================

class QCar2StartItem(TrackItem):
    TYPE_NAME = "qcar2_start"
    DISPLAY_NAME = "QCar2 Start"

    def __init__(self, object_id: str | None = None):
        super().__init__(object_id=object_id)
        self.camera_view = QCAR_CAMERA_THIRD_PERSON

        # Keep the editor-only QCar start marker above roads and scene
        # geometry regardless of JSON save/load reconstruction order.
        # This affects only the 2-D editor display; exported QLabs Z is
        # still controlled independently by the exporter.
        self.setZValue(50)
        self.enable_identifier_label(self.width_px / 2.0 + 8.0)

    @property
    def length_px(self) -> float:
        return QCAR2_DESIGN_LENGTH_M * PIXELS_PER_METER

    @property
    def width_px(self) -> float:
        return QCAR2_DESIGN_WIDTH_M * PIXELS_PER_METER

    def boundingRect(self) -> QRectF:
        margin = 14.0
        return QRectF(
            -self.length_px / 2.0 - margin,
            -self.width_px / 2.0 - margin,
            self.length_px + margin * 2.0,
            self.width_px + margin * 2.0,
        )

    def paint(self, painter: QPainter, option, widget=None):
        body = QRectF(
            -self.length_px / 2.0,
            -self.width_px / 2.0,
            self.length_px,
            self.width_px,
        )

        painter.setPen(QPen(QColor(25, 80, 130), 2))
        painter.setBrush(QColor(55, 150, 225))
        painter.drawRoundedRect(body, 6.0, 6.0)

        # Yellow nose/arrow: local +X is QCar forward.
        front_x = self.length_px / 2.0
        arrow = QPainterPath()
        arrow.moveTo(front_x + 12.0, 0.0)
        arrow.lineTo(front_x - 6.0, -10.0)
        arrow.lineTo(front_x - 6.0, 10.0)
        arrow.closeSubpath()

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(255, 210, 70))
        painter.drawPath(arrow)

        heading_pen = QPen(QColor(245, 245, 245), 2)
        heading_pen.setCosmetic(True)
        painter.setPen(heading_pen)
        painter.drawLine(
            QPointF(-self.length_px * 0.20, 0.0),
            QPointF(self.length_px * 0.30, 0.0),
        )

        if self.isSelected():
            selection_pen = QPen(SELECTION_COLOR, SELECTION_LINE_WIDTH_PX)
            selection_pen.setCosmetic(True)
            painter.setPen(selection_pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(body.adjusted(-3.0, -3.0, 3.0, 3.0))

    def to_dict(self) -> dict:
        data = self.base_dict()
        data["camera_view"] = self.camera_view
        return data

    @classmethod
    def from_dict(cls, data: dict):
        item = cls(object_id=data.get("id"))
        item.camera_view = str(
            data.get("camera_view", QCAR_CAMERA_THIRD_PERSON)
        )
        item.setPos(
            world_to_scene(
                float(data.get("x", 0.0)),
                float(data.get("y", 0.0)),
            )
        )
        item.setRotation(float(data.get("rotation_deg", 0.0)))
        return item

    def selection_text(self) -> str:
        camera_label = (
            "First person (front CSI)"
            if self.camera_view == QCAR_CAMERA_FIRST_PERSON
            else "Third person (trailing)"
        )
        return (
            super().selection_text()
            + "\nForward: local +X"
            + f"\nCamera: {camera_label}"
        )



# ================================================================
# QLabs scene actor items
# ================================================================

class SceneActorItem(TrackItem):
    TYPE_NAME = "scene_actor"
    DISPLAY_NAME = "Scene Actor"

    def __init__(
        self,
        object_id: str | None = None,
        z_m: float = 0.0,
        actor_scale: float = 1.0,
        scale_with_project: bool = True,
        configuration: int = 0,
    ):
        super().__init__(object_id=object_id)
        self.z_m = float(z_m)
        self.actor_scale = max(0.01, float(actor_scale))
        self.scale_with_project = bool(scale_with_project)
        self.configuration = int(configuration)
        self.setZValue(25)

    def actor_dict(self) -> dict:
        data = self.base_dict()
        data.update(
            {
                "z_m": round(float(self.z_m), 4),
                "actor_scale": round(float(self.actor_scale), 4),
                "scale_with_project": bool(self.scale_with_project),
                "configuration": int(self.configuration),
            }
        )
        return data

    def load_actor_dict(self, data: dict):
        self.z_m = float(data.get("z_m", 0.0))
        self.actor_scale = max(0.01, float(data.get("actor_scale", 1.0)))
        self.scale_with_project = bool(data.get("scale_with_project", True))
        self.configuration = int(data.get("configuration", 0))

    def selection_text(self) -> str:
        return (
            super().selection_text()
            + f"\nZ: {self.z_m:.2f} m"
            + f"\nActor scale: {self.actor_scale:.2f}"
            + (
                "\nScale with project: Yes"
                if self.scale_with_project
                else "\nScale with project: No"
            )
        )


class TrafficLightItem(SceneActorItem):
    TYPE_NAME = "traffic_light"
    DISPLAY_NAME = "Traffic Light"

    def __init__(self, object_id: str | None = None):
        super().__init__(object_id=object_id)
        self.traffic_color = "red"
        self.enable_identifier_label(
            ACTOR_MARKER_SIZE_M * PIXELS_PER_METER / 2.0 + 6.0
        )

    def boundingRect(self) -> QRectF:
        s = ACTOR_MARKER_SIZE_M * PIXELS_PER_METER
        return QRectF(-s / 2, -s / 2, s, s)

    def paint(self, painter: QPainter, option, widget=None):
        rect = self.boundingRect().adjusted(4, 4, -4, -4)
        painter.setPen(QPen(QColor(35, 35, 35), 2))
        painter.setBrush(QColor(60, 60, 65))
        painter.drawRoundedRect(rect, 5, 5)

        colors = {
            "off": QColor(80, 80, 80),
            "red": QColor(240, 65, 65),
            "yellow": QColor(245, 210, 60),
            "green": QColor(70, 215, 100),
        }
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(colors.get(self.traffic_color, colors["red"]))
        painter.drawEllipse(QPointF(0, 0), 7, 7)

        # Front-facing arrow.
        painter.setPen(QPen(QColor(230, 230, 230), 2))
        painter.drawLine(QPointF(0, 0), QPointF(rect.right() + 8, 0))

        if self.isSelected():
            pen = QPen(SELECTION_COLOR, SELECTION_LINE_WIDTH_PX)
            pen.setCosmetic(True)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(rect.adjusted(-3, -3, 3, 3))

    def to_dict(self) -> dict:
        data = self.actor_dict()
        data["traffic_color"] = self.traffic_color
        return data

    @classmethod
    def from_dict(cls, data: dict):
        item = cls(object_id=data.get("id"))
        item.load_actor_dict(data)
        item.traffic_color = str(data.get("traffic_color", "red"))
        item.setPos(world_to_scene(float(data.get("x", 0.0)), float(data.get("y", 0.0))))
        item.setRotation(float(data.get("rotation_deg", 0.0)))
        return item

    def selection_text(self) -> str:
        return (
            super().selection_text()
            + f"\nConfiguration: {self.configuration}"
            + f"\nInitial light: {self.traffic_color.title()}"
        )


class SignActorItem(SceneActorItem):
    SIGN_TEXT = "SIGN"
    SIGN_COLOR = QColor(220, 80, 80)

    def boundingRect(self) -> QRectF:
        s = ACTOR_MARKER_SIZE_M * PIXELS_PER_METER
        return QRectF(-s / 2, -s / 2, s, s)

    def paint(self, painter: QPainter, option, widget=None):
        rect = self.boundingRect().adjusted(4, 4, -4, -4)
        painter.setPen(QPen(QColor(245, 245, 245), 2))
        painter.setBrush(self.SIGN_COLOR)
        painter.drawEllipse(rect)

        painter.setPen(QPen(QColor(255, 255, 255), 2))
        painter.drawLine(QPointF(0, 0), QPointF(rect.right() + 8, 0))
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, self.SIGN_TEXT)

        if self.isSelected():
            pen = QPen(SELECTION_COLOR, SELECTION_LINE_WIDTH_PX)
            pen.setCosmetic(True)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(rect.adjusted(-3, -3, 3, 3))

    def to_dict(self) -> dict:
        return self.actor_dict()

    @classmethod
    def from_dict(cls, data: dict):
        item = cls(object_id=data.get("id"))
        item.load_actor_dict(data)
        item.setPos(world_to_scene(float(data.get("x", 0.0)), float(data.get("y", 0.0))))
        item.setRotation(float(data.get("rotation_deg", 0.0)))
        return item


class StopSignItem(SignActorItem):
    TYPE_NAME = "stop_sign"
    DISPLAY_NAME = "Stop Sign"
    SIGN_TEXT = "STOP"
    SIGN_COLOR = QColor(205, 55, 55)


class YieldSignItem(SignActorItem):
    TYPE_NAME = "yield_sign"
    DISPLAY_NAME = "Yield Sign"
    SIGN_TEXT = "YIELD"
    SIGN_COLOR = QColor(230, 150, 45)


class RoundaboutSignItem(SignActorItem):
    TYPE_NAME = "roundabout_sign"
    DISPLAY_NAME = "Roundabout Sign"
    SIGN_TEXT = "R"
    SIGN_COLOR = QColor(70, 125, 220)


class CrosswalkItem(SceneActorItem):
    TYPE_NAME = "crosswalk"
    DISPLAY_NAME = "Crosswalk"

    @property
    def length_px(self):
        return CROSSWALK_MARKER_LENGTH_M * PIXELS_PER_METER

    @property
    def width_px(self):
        return CROSSWALK_MARKER_WIDTH_M * PIXELS_PER_METER

    def boundingRect(self) -> QRectF:
        return QRectF(
            -self.length_px / 2,
            -self.width_px / 2,
            self.length_px,
            self.width_px,
        )

    def paint(self, painter: QPainter, option, widget=None):
        rect = self.boundingRect()
        painter.setPen(QPen(QColor(220, 220, 220), 1))
        painter.setBrush(QColor(80, 80, 85))
        painter.drawRect(rect)

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(245, 245, 245))
        stripe_count = 7
        stripe_w = self.length_px / (stripe_count * 2.0)
        for i in range(stripe_count):
            x = rect.left() + (2 * i + 0.5) * stripe_w
            painter.drawRect(
                QRectF(x, rect.top(), stripe_w, rect.height())
            )

        if self.isSelected():
            pen = QPen(SELECTION_COLOR, SELECTION_LINE_WIDTH_PX)
            pen.setCosmetic(True)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(rect)

    def to_dict(self) -> dict:
        return self.actor_dict()

    @classmethod
    def from_dict(cls, data: dict):
        item = cls(object_id=data.get("id"))
        item.load_actor_dict(data)
        item.setPos(world_to_scene(float(data.get("x", 0.0)), float(data.get("y", 0.0))))
        item.setRotation(float(data.get("rotation_deg", 0.0)))
        return item

    def selection_text(self) -> str:
        return super().selection_text() + f"\nConfiguration: {self.configuration}"


class BuildingBoxItem(SceneActorItem):
    TYPE_NAME = "building_box"
    DISPLAY_NAME = "Building / Box"

    def __init__(self, object_id: str | None = None):
        super().__init__(object_id=object_id)
        self.length_m = DEFAULT_BUILDING_LENGTH_M
        self.width_m = DEFAULT_BUILDING_WIDTH_M
        self.height_m = DEFAULT_BUILDING_HEIGHT_M
        self.rgb = tuple(DEFAULT_BUILDING_RGB)

    @property
    def length_px(self):
        return self.length_m * PIXELS_PER_METER

    @property
    def width_px(self):
        return self.width_m * PIXELS_PER_METER

    def boundingRect(self) -> QRectF:
        return QRectF(
            -self.length_px / 2,
            -self.width_px / 2,
            self.length_px,
            self.width_px,
        )

    def paint(self, painter: QPainter, option, widget=None):
        rect = self.boundingRect()
        painter.setPen(QPen(QColor(55, 60, 68), 2))
        painter.setBrush(QColor(*self.rgb))
        painter.drawRect(rect)

        painter.setPen(QPen(QColor(230, 230, 235), 1))
        painter.drawLine(rect.topLeft(), rect.bottomRight())
        painter.drawLine(rect.topRight(), rect.bottomLeft())

        if self.isSelected():
            pen = QPen(SELECTION_COLOR, SELECTION_LINE_WIDTH_PX)
            pen.setCosmetic(True)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(rect)

    def to_dict(self) -> dict:
        data = self.actor_dict()
        data.update(
            {
                "length_m": float(self.length_m),
                "width_m": float(self.width_m),
                "height_m": float(self.height_m),
                "rgb": [int(self.rgb[0]), int(self.rgb[1]), int(self.rgb[2])],
            }
        )
        return data

    @classmethod
    def from_dict(cls, data: dict):
        item = cls(object_id=data.get("id"))
        item.load_actor_dict(data)
        item.length_m = max(0.1, float(data.get("length_m", DEFAULT_BUILDING_LENGTH_M)))
        item.width_m = max(0.1, float(data.get("width_m", DEFAULT_BUILDING_WIDTH_M)))
        item.height_m = max(0.1, float(data.get("height_m", DEFAULT_BUILDING_HEIGHT_M)))
        rgb = data.get("rgb", DEFAULT_BUILDING_RGB)
        if not isinstance(rgb, (list, tuple)) or len(rgb) != 3:
            rgb = DEFAULT_BUILDING_RGB
        item.rgb = tuple(max(0, min(255, int(v))) for v in rgb)
        item.setPos(world_to_scene(float(data.get("x", 0.0)), float(data.get("y", 0.0))))
        item.setRotation(float(data.get("rotation_deg", 0.0)))
        return item

    def selection_text(self) -> str:
        return (
            super().selection_text()
            + f"\nLength: {self.length_m:.1f} m"
            + f"\nWidth: {self.width_m:.1f} m"
            + f"\nHeight: {self.height_m:.1f} m"
            + f"\nRGB: {self.rgb[0]}, {self.rgb[1]}, {self.rgb[2]}"
        )



# ================================================================
# Experiment actors and trigger zones
# ================================================================

class ExperimentActorItem(SceneActorItem):
    """Common editor data for people/animals used in experiments."""

    def __init__(self, object_id: str | None = None):
        super().__init__(object_id=object_id)
        self.spawn_mode = EXPERIMENT_SPAWN_IMMEDIATE
        self.move_on_activation = False
        self.destination_x_m = 0.0
        self.destination_y_m = 0.0
        self.movement_gait = "walk"
        self.path_points_m = []
        self.movement_mode = MOVEMENT_ONCE
        self.despawn_on_finish = False

    def experiment_actor_dict(self) -> dict:
        data = self.actor_dict()
        data.update(
            {
                "spawn_mode": self.spawn_mode,
                "move_on_activation": bool(self.move_on_activation),
                "destination_x_m": float(self.destination_x_m),
                "destination_y_m": float(self.destination_y_m),
                "movement_gait": self.movement_gait,
                "path_points": [
                    [float(point[0]), float(point[1])]
                    for point in self.path_points_m
                ],
                "movement_mode": self.movement_mode,
                "despawn_on_finish": bool(self.despawn_on_finish),
            }
        )
        return data

    def load_experiment_actor_dict(self, data: dict):
        self.load_actor_dict(data)
        self.spawn_mode = str(
            data.get("spawn_mode", EXPERIMENT_SPAWN_IMMEDIATE)
        )
        self.move_on_activation = bool(data.get("move_on_activation", False))
        self.destination_x_m = float(
            data.get("destination_x_m", data.get("x", 0.0))
        )
        self.destination_y_m = float(
            data.get("destination_y_m", data.get("y", 0.0))
        )
        self.movement_gait = str(data.get("movement_gait", "walk"))
        raw_path = data.get("path_points", []) or []
        self.path_points_m = []
        for point in raw_path:
            if isinstance(point, (list, tuple)) and len(point) >= 2:
                self.path_points_m.append([float(point[0]), float(point[1])])
        self.movement_mode = str(data.get("movement_mode", MOVEMENT_ONCE))
        if self.movement_mode not in {MOVEMENT_ONCE, MOVEMENT_LOOP, MOVEMENT_PINGPONG}:
            self.movement_mode = MOVEMENT_ONCE
        self.despawn_on_finish = bool(data.get("despawn_on_finish", False))

    def selection_text(self) -> str:
        spawn_text = (
            "Triggered"
            if self.spawn_mode == EXPERIMENT_SPAWN_TRIGGERED
            else "Immediate"
        )
        text = super().selection_text() + f"\nSpawn: {spawn_text}"
        if self.move_on_activation:
            text += (
                f"\nWaypoints: {len(self.path_points_m)}"
                f"\nMovement: {self.movement_mode.title()}"
                f"\nGait: {self.movement_gait.title()}"
            )
            if self.movement_mode == MOVEMENT_ONCE:
                text += f"\nDespawn after route: {'Yes' if self.despawn_on_finish else 'No'}"
        return text


class PersonItem(ExperimentActorItem):
    TYPE_NAME = "person"
    DISPLAY_NAME = "Pedestrian"

    def __init__(self, object_id: str | None = None):
        super().__init__(object_id=object_id)
        self.person_configuration = 0
        self.enable_identifier_label(
            ACTOR_MARKER_SIZE_M * PIXELS_PER_METER / 2.0 + 6.0
        )

    def boundingRect(self) -> QRectF:
        s = ACTOR_MARKER_SIZE_M * PIXELS_PER_METER
        return QRectF(-s / 2, -s / 2, s, s)

    def paint(self, painter: QPainter, option, widget=None):
        rect = self.boundingRect().adjusted(5, 5, -5, -5)

        painter.setPen(QPen(QColor(35, 35, 35), 2))
        painter.setBrush(QColor(90, 190, 235))
        painter.drawEllipse(
            QPointF(0, rect.top() + rect.height() * 0.28),
            6,
            6,
        )

        painter.setPen(QPen(QColor(90, 190, 235), 5))
        painter.drawLine(
            QPointF(0, rect.top() + rect.height() * 0.42),
            QPointF(0, rect.bottom() - 5),
        )
        painter.drawLine(
            QPointF(0, rect.center().y()),
            QPointF(rect.right() - 4, rect.center().y()),
        )

        # Forward arrow (+X).
        painter.setPen(QPen(QColor(255, 220, 70), 2))
        painter.drawLine(QPointF(0, 0), QPointF(rect.right() + 8, 0))

        if self.spawn_mode == EXPERIMENT_SPAWN_TRIGGERED:
            dash_pen = QPen(QColor(210, 140, 255), 2, Qt.PenStyle.DashLine)
            dash_pen.setCosmetic(True)
            painter.setPen(dash_pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(rect)

        if self.isSelected():
            pen = QPen(SELECTION_COLOR, SELECTION_LINE_WIDTH_PX)
            pen.setCosmetic(True)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(rect.adjusted(-3, -3, 3, 3))

    def to_dict(self) -> dict:
        data = self.experiment_actor_dict()
        data["person_configuration"] = int(self.person_configuration)
        return data

    @classmethod
    def from_dict(cls, data: dict):
        item = cls(object_id=data.get("id"))
        item.load_experiment_actor_dict(data)
        item.person_configuration = max(
            0, min(11, int(data.get("person_configuration", 0)))
        )
        item.setPos(
            world_to_scene(
                float(data.get("x", 0.0)),
                float(data.get("y", 0.0)),
            )
        )
        item.setRotation(float(data.get("rotation_deg", 0.0)))
        return item

    def selection_text(self) -> str:
        return (
            super().selection_text()
            + f"\nPerson configuration: {self.person_configuration}"
        )


class AnimalItem(ExperimentActorItem):
    TYPE_NAME = "animal"
    DISPLAY_NAME = "Animal"

    def __init__(self, object_id: str | None = None):
        super().__init__(object_id=object_id)
        self.animal_type = "goat"
        self.enable_identifier_label(
            ACTOR_MARKER_SIZE_M * PIXELS_PER_METER / 2.0 + 6.0
        )

    def boundingRect(self) -> QRectF:
        s = ACTOR_MARKER_SIZE_M * PIXELS_PER_METER
        return QRectF(-s / 2, -s / 2, s, s)

    def paint(self, painter: QPainter, option, widget=None):
        rect = self.boundingRect().adjusted(5, 5, -5, -5)

        animal_colors = {
            "goat": QColor(220, 200, 150),
            "sheep": QColor(235, 235, 225),
            "cow": QColor(170, 125, 95),
        }

        painter.setPen(QPen(QColor(45, 45, 45), 2))
        painter.setBrush(animal_colors.get(self.animal_type, animal_colors["goat"]))
        painter.drawEllipse(rect.adjusted(3, 7, -7, -7))
        painter.drawEllipse(
            QPointF(rect.right() - 4, rect.center().y()),
            6,
            5,
        )

        painter.setPen(QPen(QColor(255, 220, 70), 2))
        painter.drawLine(QPointF(0, 0), QPointF(rect.right() + 8, 0))

        if self.spawn_mode == EXPERIMENT_SPAWN_TRIGGERED:
            dash_pen = QPen(QColor(210, 140, 255), 2, Qt.PenStyle.DashLine)
            dash_pen.setCosmetic(True)
            painter.setPen(dash_pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(rect)

        if self.isSelected():
            pen = QPen(SELECTION_COLOR, SELECTION_LINE_WIDTH_PX)
            pen.setCosmetic(True)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(rect.adjusted(-3, -3, 3, 3))

    def to_dict(self) -> dict:
        data = self.experiment_actor_dict()
        data["animal_type"] = self.animal_type
        return data

    @classmethod
    def from_dict(cls, data: dict):
        item = cls(object_id=data.get("id"))
        item.load_experiment_actor_dict(data)
        item.animal_type = str(data.get("animal_type", "goat"))
        if item.animal_type not in {"goat", "sheep", "cow"}:
            item.animal_type = "goat"
        item.setPos(
            world_to_scene(
                float(data.get("x", 0.0)),
                float(data.get("y", 0.0)),
            )
        )
        item.setRotation(float(data.get("rotation_deg", 0.0)))
        return item

    def selection_text(self) -> str:
        return super().selection_text() + f"\nAnimal: {self.animal_type.title()}"


class SecondaryQCarItem(ExperimentActorItem):
    TYPE_NAME = "secondary_qcar2"
    DISPLAY_NAME = "Environment QCar2"

    def __init__(self, object_id: str | None = None):
        super().__init__(object_id=object_id)
        self.movement_speed_mps = DEFAULT_SECONDARY_QCAR_SPEED_MPS
        self.setZValue(45)
        self.enable_identifier_label(self.width_px / 2.0 + 8.0)

    @property
    def length_px(self):
        return QCAR2_DESIGN_LENGTH_M * PIXELS_PER_METER

    @property
    def width_px(self):
        return QCAR2_DESIGN_WIDTH_M * PIXELS_PER_METER

    def boundingRect(self) -> QRectF:
        margin = 8.0
        return QRectF(-self.length_px/2-margin, -self.width_px/2-margin,
                      self.length_px+2*margin, self.width_px+2*margin)

    def paint(self, painter: QPainter, option, widget=None):
        body = QRectF(-self.length_px/2, -self.width_px/2, self.length_px, self.width_px)
        painter.setPen(QPen(QColor(80, 55, 20), 2))
        painter.setBrush(QColor(235, 155, 55))
        painter.drawRoundedRect(body, 6, 6)
        painter.setPen(QPen(QColor(255, 245, 220), 2))
        painter.drawLine(QPointF(-self.length_px*0.2, 0), QPointF(self.length_px*0.3, 0))
        painter.setPen(QPen(QColor(255, 220, 70), 2))
        painter.drawLine(QPointF(0, 0), QPointF(self.length_px/2 + 10, 0))
        if self.spawn_mode == EXPERIMENT_SPAWN_TRIGGERED:
            pen = QPen(QColor(210, 140, 255), 2, Qt.PenStyle.DashLine); pen.setCosmetic(True)
            painter.setPen(pen); painter.setBrush(Qt.BrushStyle.NoBrush); painter.drawRect(body)
        if self.isSelected():
            pen = QPen(SELECTION_COLOR, SELECTION_LINE_WIDTH_PX); pen.setCosmetic(True)
            painter.setPen(pen); painter.setBrush(Qt.BrushStyle.NoBrush); painter.drawRect(body.adjusted(-3,-3,3,3))

    def to_dict(self) -> dict:
        data = self.experiment_actor_dict()
        data["movement_speed_mps"] = float(self.movement_speed_mps)
        return data

    @classmethod
    def from_dict(cls, data: dict):
        item = cls(object_id=data.get("id"))
        item.load_experiment_actor_dict(data)
        item.movement_speed_mps = max(0.1, float(data.get("movement_speed_mps", DEFAULT_SECONDARY_QCAR_SPEED_MPS)))
        item.setPos(world_to_scene(float(data.get("x",0.0)), float(data.get("y",0.0))))
        item.setRotation(float(data.get("rotation_deg",0.0)))
        return item

    def selection_text(self) -> str:
        return super().selection_text() + f"\\nPath speed: {self.movement_speed_mps:.1f} m/s"


class TriggerZoneItem(TrackItem):
    TYPE_NAME = "trigger_zone"
    DISPLAY_NAME = "QCar Trigger Zone"

    def __init__(self, object_id: str | None = None):
        super().__init__(object_id=object_id)
        self.radius_m = DEFAULT_TRIGGER_RADIUS_M
        self.action = TRIGGER_ACTION_ACTIVATE_ACTOR
        self.target_id = ""
        self.traffic_color = "green"
        self.one_shot = True
        self.setZValue(70)

    @property
    def radius_px(self) -> float:
        return self.radius_m * PIXELS_PER_METER

    def boundingRect(self) -> QRectF:
        r = self.radius_px
        margin = 5.0
        return QRectF(
            -r - margin,
            -r - margin,
            2 * (r + margin),
            2 * (r + margin),
        )

    def paint(self, painter: QPainter, option, widget=None):
        r = self.radius_px
        rect = QRectF(-r, -r, 2 * r, 2 * r)

        zone_pen = QPen(
            QColor(220, 110, 255, 220),
            2,
            Qt.PenStyle.DashLine,
        )
        zone_pen.setCosmetic(True)
        painter.setPen(zone_pen)
        painter.setBrush(QColor(180, 80, 220, 35))
        painter.drawEllipse(rect)

        painter.setPen(QPen(QColor(240, 190, 255), 2))
        painter.drawLine(QPointF(-8, 0), QPointF(8, 0))
        painter.drawLine(QPointF(0, -8), QPointF(0, 8))

        if self.isSelected():
            pen = QPen(SELECTION_COLOR, SELECTION_LINE_WIDTH_PX)
            pen.setCosmetic(True)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawEllipse(rect)

    def to_dict(self) -> dict:
        data = self.base_dict()
        data.update(
            {
                "radius_m": float(self.radius_m),
                "action": self.action,
                "target_id": self.target_id,
                "traffic_color": self.traffic_color,
                "one_shot": bool(self.one_shot),
            }
        )
        return data

    @classmethod
    def from_dict(cls, data: dict):
        item = cls(object_id=data.get("id"))
        item.radius_m = max(
            0.1,
            float(data.get("radius_m", DEFAULT_TRIGGER_RADIUS_M)),
        )
        item.action = str(
            data.get("action", TRIGGER_ACTION_ACTIVATE_ACTOR)
        )
        item.target_id = str(data.get("target_id", ""))
        item.traffic_color = str(data.get("traffic_color", "green"))
        item.one_shot = bool(data.get("one_shot", True))
        item.setPos(
            world_to_scene(
                float(data.get("x", 0.0)),
                float(data.get("y", 0.0)),
            )
        )
        item.setRotation(float(data.get("rotation_deg", 0.0)))
        return item

    def selection_text(self) -> str:
        action_text = (
            "Activate experiment actor"
            if self.action == TRIGGER_ACTION_ACTIVATE_ACTOR
            else "Change traffic light"
        )
        return (
            super().selection_text()
            + f"\nRadius: {self.radius_m:.1f} m"
            + f"\nAction: {action_text}"
            + f"\nOne shot: {'Yes' if self.one_shot else 'No'}"
        )


# ================================================================
# Component registry / factory
# ================================================================

TRACK_ITEM_CLASSES = {
    StraightRoadItem.TYPE_NAME: StraightRoadItem,
    Curve90RoadItem.TYPE_NAME: Curve90RoadItem,
    Curve45RoadItem.TYPE_NAME: Curve45RoadItem,
    TJunctionItem.TYPE_NAME: TJunctionItem,
    CrossIntersectionItem.TYPE_NAME: CrossIntersectionItem,
    RoadEndItem.TYPE_NAME: RoadEndItem,
    QCar2StartItem.TYPE_NAME: QCar2StartItem,
    TrafficLightItem.TYPE_NAME: TrafficLightItem,
    StopSignItem.TYPE_NAME: StopSignItem,
    YieldSignItem.TYPE_NAME: YieldSignItem,
    RoundaboutSignItem.TYPE_NAME: RoundaboutSignItem,
    CrosswalkItem.TYPE_NAME: CrosswalkItem,
    BuildingBoxItem.TYPE_NAME: BuildingBoxItem,
    PersonItem.TYPE_NAME: PersonItem,
    AnimalItem.TYPE_NAME: AnimalItem,
    SecondaryQCarItem.TYPE_NAME: SecondaryQCarItem,
    TriggerZoneItem.TYPE_NAME: TriggerZoneItem,
}


def create_track_item_from_dict(data: dict) -> TrackItem | None:
    item_type = data.get("type")
    cls = TRACK_ITEM_CLASSES.get(item_type)
    if cls is None:
        return None
    item = cls.from_dict(data)
    if item is not None:
        item.set_readable_identifier(str(data.get("identifier", "")))
    return item


# ================================================================
# Scene
# ================================================================

class TrackScene(QGraphicsScene):
    def __init__(self, window):
        super().__init__(-4000, -4000, 8000, 8000)
        self.window = window
        self.endpoint_snap_enabled = True
        self.selectionChanged.connect(self.notify_selection_or_geometry_changed)

    def notify_selection_or_geometry_changed(self):
        self.window.update_selection_info()

    def selected_track_items(self) -> list[TrackItem]:
        return [
            item
            for item in self.selectedItems()
            if isinstance(item, TrackItem)
        ]

    def track_items(self) -> list[TrackItem]:
        return [
            item
            for item in self.items()
            if isinstance(item, TrackItem)
        ]

    def snap_item_position_to_endpoint(
        self,
        moving_item: TrackItem,
        proposed_pos: QPointF,
    ) -> QPointF:
        """Return a position adjusted so compatible endpoints meet.

        The nearest pair inside ENDPOINT_SNAP_DISTANCE_PX wins. Heading
        compatibility prevents, for example, a horizontal road from snapping
        sideways onto a perpendicular road end.
        """
        if not self.endpoint_snap_enabled:
            return proposed_pos

        moving_connections = moving_item.connection_points_scene_for_position(
            proposed_pos
        )
        if not moving_connections:
            return proposed_pos

        best_distance = ENDPOINT_SNAP_DISTANCE_PX + 1.0
        best_offset = None

        for target_item in self.track_items():
            if target_item is moving_item:
                continue

            for moving_connection in moving_connections:
                for target_connection in target_item.connection_points_scene():
                    if not endpoints_face_each_other(
                        moving_connection["heading_deg"],
                        target_connection["heading_deg"],
                    ):
                        continue

                    distance = point_distance(
                        moving_connection["pos"],
                        target_connection["pos"],
                    )

                    if distance <= ENDPOINT_SNAP_DISTANCE_PX and distance < best_distance:
                        best_distance = distance
                        best_offset = (
                            target_connection["pos"] - moving_connection["pos"]
                        )

        if best_offset is not None:
            return proposed_pos + best_offset

        return proposed_pos


# ================================================================
# Graphics view
# ================================================================

class TrackView(QGraphicsView):
    def __init__(self, scene: TrackScene):
        super().__init__(scene)

        self.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        self.setViewportUpdateMode(
            QGraphicsView.ViewportUpdateMode.BoundingRectViewportUpdate
        )
        self.setTransformationAnchor(
            QGraphicsView.ViewportAnchor.AnchorUnderMouse
        )
        self.setResizeAnchor(
            QGraphicsView.ViewportAnchor.AnchorViewCenter
        )

        self.setDragMode(QGraphicsView.DragMode.RubberBandDrag)
        self.setBackgroundBrush(QColor(27, 30, 34))

        self.editor_window = scene.window
        self._middle_panning = False
        self._last_pan_pos = None

    def drawBackground(self, painter: QPainter, rect: QRectF):
        painter.fillRect(rect, QColor(27, 30, 34))

        # v1.0 adaptive grid:
        # Open Road spans many kilometers. A fixed 1 m grid would create
        # thousands of invisible sub-pixel lines when zoomed out, so choose
        # the smallest useful spacing for the current zoom.
        view_scale = max(abs(self.transform().m11()), 1e-9)
        grid_candidates_m = (
            1.0,
            2.0,
            5.0,
            10.0,
            25.0,
            50.0,
            100.0,
            250.0,
            500.0,
            1000.0,
            2500.0,
        )

        grid_m = grid_candidates_m[-1]
        for candidate_m in grid_candidates_m:
            if candidate_m * PIXELS_PER_METER * view_scale >= 16.0:
                grid_m = candidate_m
                break

        grid_px = grid_m * PIXELS_PER_METER

        left = math.floor(rect.left() / grid_px) * grid_px
        top = math.floor(rect.top() / grid_px) * grid_px

        minor_lines = []
        major_lines = []

        x = left
        line_index = int(round(left / grid_px))
        while x <= rect.right():
            target = major_lines if line_index % 5 == 0 else minor_lines
            target.append((QPointF(x, rect.top()), QPointF(x, rect.bottom())))
            x += grid_px
            line_index += 1

        y = top
        line_index = int(round(top / grid_px))
        while y <= rect.bottom():
            target = major_lines if line_index % 5 == 0 else minor_lines
            target.append((QPointF(rect.left(), y), QPointF(rect.right(), y)))
            y += grid_px
            line_index += 1

        minor_pen = QPen(QColor(45, 49, 55), 1)
        minor_pen.setCosmetic(True)
        painter.setPen(minor_pen)
        for p1, p2 in minor_lines:
            painter.drawLine(p1, p2)

        major_pen = QPen(QColor(63, 69, 77), 1)
        major_pen.setCosmetic(True)
        painter.setPen(major_pen)
        for p1, p2 in major_lines:
            painter.drawLine(p1, p2)

        # Draw the selected workspace map as a non-interactive background.
        self.editor_window.draw_workspace_reference(painter, rect)

        # World axes stay visible above the reference overlay.
        x_axis_pen = QPen(QColor(180, 70, 70), 2)
        x_axis_pen.setCosmetic(True)
        painter.setPen(x_axis_pen)
        painter.drawLine(QPointF(rect.left(), 0), QPointF(rect.right(), 0))

        y_axis_pen = QPen(QColor(70, 150, 210), 2)
        y_axis_pen.setCosmetic(True)
        painter.setPen(y_axis_pen)
        painter.drawLine(QPointF(0, rect.top()), QPointF(0, rect.bottom()))

    def drawForeground(self, painter: QPainter, rect: QRectF):
        super().drawForeground(painter, rect)

        editing_id = getattr(self.editor_window, "path_edit_actor_id", None)
        for item in self.scene().track_items():
            if not isinstance(item, ExperimentActorItem):
                continue
            if not item.path_points_m:
                continue

            selected = item.isSelected() or str(item.object_id) == str(editing_id)
            color = QColor(255, 185, 65, 235) if isinstance(item, SecondaryQCarItem) else QColor(190, 110, 255, 220)
            if not selected:
                color.setAlpha(120)

            path_pen = QPen(color, 2.5 if selected else 1.5)
            path_pen.setCosmetic(True)
            painter.setPen(path_pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)

            points = [item.scenePos()] + [world_to_scene(p[0], p[1]) for p in item.path_points_m]
            for i in range(len(points)-1):
                painter.drawLine(points[i], points[i+1])

            pin_radius = 6.0 / max(0.15, self.transform().m11())
            painter.setBrush(color)
            for idx, point in enumerate(points[1:], start=1):
                painter.drawEllipse(point, pin_radius, pin_radius)

    def wheelEvent(self, event):
        zoom_in = 1.15
        zoom_out = 1.0 / zoom_in
        factor = zoom_in if event.angleDelta().y() > 0 else zoom_out

        current_scale = self.transform().m11()
        next_scale = current_scale * factor

        if 0.001 <= next_scale <= 8.0:
            self.scale(factor, factor)
            self.editor_window.update_zoom_label()

        event.accept()

    def mousePressEvent(self, event):
        if getattr(self.editor_window, "path_edit_actor_id", None):
            if event.button() == Qt.MouseButton.LeftButton:
                self.editor_window.add_movement_waypoint(
                    self.mapToScene(event.position().toPoint())
                )
                event.accept()
                return
            if event.button() == Qt.MouseButton.RightButton:
                self.editor_window.finish_path_editing()
                event.accept()
                return

        if event.button() == Qt.MouseButton.MiddleButton:
            self._middle_panning = True
            self._last_pan_pos = event.position()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._middle_panning and self._last_pan_pos is not None:
            delta = event.position() - self._last_pan_pos
            self._last_pan_pos = event.position()

            self.horizontalScrollBar().setValue(
                self.horizontalScrollBar().value() - int(delta.x())
            )
            self.verticalScrollBar().setValue(
                self.verticalScrollBar().value() - int(delta.y())
            )
            event.accept()
            return

        scene_pos = self.mapToScene(event.position().toPoint())
        x_m, y_m = scene_to_world(scene_pos)
        self.editor_window.update_cursor_label(x_m, y_m)

        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.MiddleButton:
            self._middle_panning = False
            self._last_pan_pos = None
            self.unsetCursor()
            event.accept()
            return
        super().mouseReleaseEvent(event)


# ================================================================
# Main window
# ================================================================

class TrackEditorWindow(QMainWindow):
    VERSION = "1.0.1"

    def __init__(self):
        super().__init__()

        self.current_file: Path | None = None
        self.rotation_step_deg = ROTATION_STEP_DEG
        self._property_refreshing = False
        self._guide_refreshing = False

        # Project scale affects the future QLabs export/effective dimensions.
        # The editor canvas itself remains in full-scale design meters.
        self.project_scale_factor = 1.0
        self.project_scale_name = "1:1"

        self.environment_enabled = True
        self.environment_weather = "clear_skies"
        self.environment_time_of_day = 12.0

        # Workspace-reference state. Open Road uses the documentation-derived
        # 2-D map for placement only; it is never turned into QLabs actors.
        (
            self.open_road_reference,
            self.open_road_reference_source,
        ) = load_open_road_reference()

        self.workspace_mode = WORKSPACE_CUSTOM
        self.workspace_show_road_reference = True
        self.workspace_show_navigation_regions = True
        self.workspace_show_reference_points = True
        self.workspace_show_reference_labels = True

        self.path_edit_actor_id = None

        self.setWindowTitle(f"QLabs Track Editor v{self.VERSION}")
        self.resize(1500, 920)

        self.scene = TrackScene(self)
        self.view = TrackView(self.scene)
        self.view.setMouseTracking(True)

        self._build_ui()
        self._build_actions()
        self._set_workspace_from_data({})

        self.view.centerOn(0, 0)
        self.update_zoom_label()
        self.update_selection_info()

    # ------------------------------------------------------------
    # UI helpers
    # ------------------------------------------------------------

    def _make_spinbox(
        self,
        minimum: float,
        maximum: float,
        step: float = 1.0,
        decimals: int = 1,
        suffix: str = "",
    ) -> QDoubleSpinBox:
        spin = QDoubleSpinBox()
        spin.setRange(minimum, maximum)
        spin.setSingleStep(step)
        spin.setDecimals(decimals)
        spin.setKeyboardTracking(False)
        if suffix:
            spin.setSuffix(suffix)
        return spin

    def _rgb_input_value(self, field: QLineEdit, fallback: int = 0) -> int:
        """Return a clamped integer from an RGB text field."""
        value_text = field.text().strip()
        if value_text == "":
            value = int(fallback)
            field.setText(str(value))
            return max(0, min(255, value))

        try:
            value = int(value_text)
        except ValueError:
            value = int(fallback)

        value = max(0, min(255, value))
        if field.text() != str(value):
            field.setText(str(value))
        return value

    def _add_palette_button(self, layout, text: str, callback):
        btn = QPushButton(text)
        btn.clicked.connect(callback)
        layout.addWidget(btn)
        return btn

    # ------------------------------------------------------------
    # UI
    # ------------------------------------------------------------

    def _build_ui(self):
        central = QWidget()
        root = QHBoxLayout(central)
        root.setContentsMargins(6, 6, 6, 6)

        # Scrollable sidebar so the growing component library remains usable.
        sidebar_contents = QWidget()
        sidebar_contents.setMinimumWidth(285)
        side_layout = QVBoxLayout(sidebar_contents)

        # Dedicated right-side inspector. Keeping selection/property controls
        # outside the component sidebar means they remain visible without
        # scrolling while the component library can continue to grow.
        inspector_contents = QWidget()
        inspector_contents.setMinimumWidth(330)
        inspector_contents.setMaximumWidth(360)
        inspector_layout = QVBoxLayout(inspector_contents)
        inspector_layout.setContentsMargins(6, 0, 6, 0)
        inspector_layout.setSpacing(6)

        # Tell the enclosing QScrollArea to respect the inspector's
        # actual content height. This is especially important as the
        # actor/experiment/property panels grow.
        inspector_layout.setSizeConstraint(
            QLayout.SizeConstraint.SetMinAndMaxSize
        )

        # --------------------------------------------------------
        # Project scale
        # --------------------------------------------------------
        project_group = QGroupBox("PROJECT SCALE")
        project_layout = QVBoxLayout(project_group)

        scale_row = QHBoxLayout()
        scale_row.addWidget(QLabel("Scale:"))
        self.project_scale_combo = QComboBox()
        for name, factor in PROJECT_SCALES:
            self.project_scale_combo.addItem(name, factor)
        self.project_scale_combo.addItem("Custom", None)
        self.project_scale_combo.currentIndexChanged.connect(self.project_scale_changed)
        scale_row.addWidget(self.project_scale_combo, 1)
        project_layout.addLayout(scale_row)

        custom_row = QHBoxLayout()
        self.custom_scale_label = QLabel("Custom 1 :")
        self.custom_scale_denominator = self._make_spinbox(1.0, 1000.0, 1.0, 2)
        self.custom_scale_denominator.setValue(10.0)
        self.custom_scale_denominator.valueChanged.connect(self.custom_scale_changed)
        custom_row.addWidget(self.custom_scale_label)
        custom_row.addWidget(self.custom_scale_denominator, 1)
        self.custom_scale_label.setVisible(False)
        self.custom_scale_denominator.setVisible(False)
        project_layout.addLayout(custom_row)

        self.scale_help_label = QLabel(
            "Canvas values stay in full-scale design meters. The selected scale "
            "is applied to QLabs effective dimensions/export."
        )
        self.scale_help_label.setWordWrap(True)
        self.scale_help_label.setStyleSheet("color: #aeb6bf; font-size: 11px;")
        project_layout.addWidget(self.scale_help_label)

        self.scale_preview_label = QLabel("6.00 m design road → 6.00 m in QLabs")
        self.scale_preview_label.setWordWrap(True)
        project_layout.addWidget(self.scale_preview_label)
        self.project_group = project_group
        side_layout.addWidget(project_group)

        # --------------------------------------------------------
        # Workspace reference
        # --------------------------------------------------------
        workspace_group = QGroupBox("WORKSPACE REFERENCE")
        workspace_layout = QVBoxLayout(workspace_group)

        workspace_row = QHBoxLayout()
        workspace_row.addWidget(QLabel("Workspace:"))

        self.workspace_mode_combo = QComboBox()
        self.workspace_mode_combo.addItem(
            "Custom / Plane",
            WORKSPACE_CUSTOM,
        )
        self.workspace_mode_combo.addItem(
            "Open Road",
            WORKSPACE_OPEN_ROAD,
        )
        self.workspace_mode_combo.currentIndexChanged.connect(
            self.workspace_mode_changed
        )
        workspace_row.addWidget(self.workspace_mode_combo, 1)
        workspace_layout.addLayout(workspace_row)

        self.workspace_show_road_checkbox = QCheckBox(
            "Road reference"
        )
        self.workspace_show_road_checkbox.setChecked(True)
        self.workspace_show_road_checkbox.toggled.connect(
            self.workspace_display_changed
        )
        workspace_layout.addWidget(
            self.workspace_show_road_checkbox
        )

        self.workspace_show_nav_checkbox = QCheckBox(
            "Navigation regions"
        )
        self.workspace_show_nav_checkbox.setChecked(True)
        self.workspace_show_nav_checkbox.toggled.connect(
            self.workspace_display_changed
        )
        workspace_layout.addWidget(
            self.workspace_show_nav_checkbox
        )

        self.workspace_show_points_checkbox = QCheckBox(
            "Published reference points"
        )
        self.workspace_show_points_checkbox.setChecked(True)
        self.workspace_show_points_checkbox.toggled.connect(
            self.workspace_display_changed
        )
        workspace_layout.addWidget(
            self.workspace_show_points_checkbox
        )

        self.workspace_show_labels_checkbox = QCheckBox(
            "Reference labels"
        )
        self.workspace_show_labels_checkbox.setChecked(True)
        self.workspace_show_labels_checkbox.toggled.connect(
            self.workspace_display_changed
        )
        workspace_layout.addWidget(
            self.workspace_show_labels_checkbox
        )

        self.fit_workspace_button = QPushButton(
            "Fit Open Road to View"
        )
        self.fit_workspace_button.clicked.connect(
            self.fit_open_road_reference
        )
        workspace_layout.addWidget(
            self.fit_workspace_button
        )

        self.workspace_reference_note = QLabel()
        self.workspace_reference_note.setWordWrap(True)
        self.workspace_reference_note.setStyleSheet(
            "color: #aeb6bf; font-size: 11px;"
        )
        workspace_layout.addWidget(
            self.workspace_reference_note
        )

        side_layout.addWidget(workspace_group)
        self.workspace_group = workspace_group

        # --------------------------------------------------------
        # Outdoor environment
        # --------------------------------------------------------
        weather_group = QGroupBox("OUTDOOR ENVIRONMENT")
        weather_form = QFormLayout(weather_group)

        self.environment_enabled_checkbox = QCheckBox("Apply on export")
        self.environment_enabled_checkbox.setChecked(True)
        self.environment_enabled_checkbox.toggled.connect(self.environment_settings_changed)

        self.weather_combo = QComboBox()
        for label, value in WEATHER_PRESETS:
            self.weather_combo.addItem(label, value)
        self.weather_combo.currentIndexChanged.connect(self.environment_settings_changed)

        self.time_of_day_spin = self._make_spinbox(0.0, 24.0, 0.5, 1, " h")
        self.time_of_day_spin.setValue(12.0)
        self.time_of_day_spin.valueChanged.connect(self.environment_settings_changed)

        weather_form.addRow("Environment", self.environment_enabled_checkbox)
        weather_form.addRow("Weather", self.weather_combo)
        weather_form.addRow("Time of day", self.time_of_day_spin)

        weather_note = QLabel("QLabs outdoor-environment features depend on the selected Open World workspace.")
        weather_note.setWordWrap(True)
        weather_note.setStyleSheet("color: #aeb6bf; font-size: 11px;")
        weather_form.addRow(weather_note)
        side_layout.addWidget(weather_group)

        # --------------------------------------------------------
        # Road segments
        # --------------------------------------------------------
        road_group = QGroupBox("ROAD SEGMENTS")
        road_layout = QVBoxLayout(road_group)
        self._add_palette_button(road_layout, "+ Straight Road", self.add_straight_road)
        self._add_palette_button(road_layout, "+ 45° Curve", self.add_curve_45)
        self._add_palette_button(road_layout, "+ 90° Curve", self.add_curve_90)
        side_layout.addWidget(road_group)

        # --------------------------------------------------------
        # Junctions and endings
        # --------------------------------------------------------
        junction_group = QGroupBox("JUNCTIONS / ENDINGS")
        junction_layout = QVBoxLayout(junction_group)
        self._add_palette_button(junction_layout, "+ T-Junction", self.add_t_junction)
        self._add_palette_button(
            junction_layout,
            "+ 4-Way Intersection",
            self.add_cross_intersection,
        )
        self._add_palette_button(junction_layout, "+ Road End", self.add_road_end)
        side_layout.addWidget(junction_group)

        # --------------------------------------------------------
        # Traffic / roadside actors
        # --------------------------------------------------------
        traffic_actor_group = QGroupBox("TRAFFIC / ROADSIDE ACTORS")
        traffic_actor_layout = QVBoxLayout(traffic_actor_group)
        self._add_palette_button(
            traffic_actor_layout, "+ Traffic Light", self.add_traffic_light
        )
        self._add_palette_button(
            traffic_actor_layout, "+ Stop Sign", self.add_stop_sign
        )
        self._add_palette_button(
            traffic_actor_layout, "+ Yield Sign", self.add_yield_sign
        )
        self._add_palette_button(
            traffic_actor_layout, "+ Roundabout Sign", self.add_roundabout_sign
        )
        self._add_palette_button(
            traffic_actor_layout, "+ Crosswalk", self.add_crosswalk
        )
        side_layout.addWidget(traffic_actor_group)

        # --------------------------------------------------------
        # Environment
        # --------------------------------------------------------
        environment_group = QGroupBox("ENVIRONMENT")
        environment_layout = QVBoxLayout(environment_group)
        self._add_palette_button(
            environment_layout, "+ Building / Box", self.add_building_box
        )
        side_layout.addWidget(environment_group)

        # --------------------------------------------------------
        # Experiment actors / triggers
        # --------------------------------------------------------
        experiment_group = QGroupBox("EXPERIMENT")
        experiment_layout = QVBoxLayout(experiment_group)

        self._add_palette_button(
            experiment_layout,
            "+ Pedestrian",
            self.add_person,
        )
        self._add_palette_button(
            experiment_layout,
            "+ Animal",
            self.add_animal,
        )
        self._add_palette_button(
            experiment_layout,
            "+ QCar Trigger Zone",
            self.add_trigger_zone,
        )

        experiment_note = QLabel(
            "Triggered people/animals remain visible in the editor but are "
            "spawned in QLabs only when their trigger fires. v1.0 moves "
            "people and animals manually along waypoint paths, so those "
            "routes do not depend on the Open World navigation areas."
        )
        experiment_note.setWordWrap(True)
        experiment_note.setStyleSheet("color: #aeb6bf; font-size: 11px;")
        experiment_layout.addWidget(experiment_note)

        side_layout.addWidget(experiment_group)

        # --------------------------------------------------------
        # QLabs / vehicle
        # --------------------------------------------------------
        qlabs_group = QGroupBox("QLABS / VEHICLE")
        qlabs_layout = QVBoxLayout(qlabs_group)

        self._add_palette_button(
            qlabs_layout,
            "+ QCar2 Start",
            self.add_qcar2_start,
        )
        self._add_palette_button(
            qlabs_layout,
            "+ Environment QCar2",
            self.add_secondary_qcar,
        )

        export_btn = QPushButton("Export QLabs Setup...")
        export_btn.clicked.connect(self.export_qlabs_setup)
        qlabs_layout.addWidget(export_btn)

        qlabs_note = QLabel(
            "Add one QCar2 start pose, then export a standalone setup script. "
            "For Open Road projects, load the Open Road workspace in QLabs first. "
            "The v1.0 reference overlay is editor-only and is not exported."
        )
        qlabs_note.setWordWrap(True)
        qlabs_note.setStyleSheet("color: #aeb6bf; font-size: 11px;")
        qlabs_layout.addWidget(qlabs_note)

        side_layout.addWidget(qlabs_group)

        # --------------------------------------------------------
        # Snapping
        # --------------------------------------------------------
        snap_group = QGroupBox("SNAPPING")
        snap_layout = QVBoxLayout(snap_group)

        self.endpoint_snap_checkbox = QCheckBox(
            f"Endpoint snap ({ENDPOINT_SNAP_DISTANCE_M:g} m)"
        )
        self.endpoint_snap_checkbox.setChecked(True)
        self.endpoint_snap_checkbox.toggled.connect(self.set_endpoint_snap_enabled)
        snap_layout.addWidget(self.endpoint_snap_checkbox)

        snap_help = QLabel(
            "Green dots are connection points. Compatible ends snap when they "
            "are close and face each other. Junctions expose 3 or 4 endpoints."
        )
        snap_help.setWordWrap(True)
        snap_help.setStyleSheet("color: #aeb6bf; font-size: 11px;")
        snap_layout.addWidget(snap_help)
        side_layout.addWidget(snap_group)

        # --------------------------------------------------------
        # Editing tools
        # --------------------------------------------------------
        edit_group = QGroupBox("EDITING")
        edit_layout = QVBoxLayout(edit_group)

        rotation_row = QHBoxLayout()
        rotation_row.addWidget(QLabel("Rotation step:"))
        self.rotation_step_combo = QComboBox()
        for step in (5, 15, 30, 45, 90):
            self.rotation_step_combo.addItem(f"{step}°", float(step))
        self.rotation_step_combo.setCurrentText("15°")
        self.rotation_step_combo.currentIndexChanged.connect(self.rotation_step_changed)
        rotation_row.addWidget(self.rotation_step_combo, 1)
        edit_layout.addLayout(rotation_row)

        duplicate_btn = QPushButton("Duplicate Selected")
        duplicate_btn.clicked.connect(self.duplicate_selected)
        edit_layout.addWidget(duplicate_btn)

        self.rotate_btn = QPushButton("Rotate +15°")
        self.rotate_btn.clicked.connect(lambda: self.rotate_selected(self.rotation_step_deg))
        edit_layout.addWidget(self.rotate_btn)

        delete_btn = QPushButton("Delete Selected")
        delete_btn.clicked.connect(self.delete_selected)
        edit_layout.addWidget(delete_btn)
        side_layout.addWidget(edit_group)

        # --------------------------------------------------------
        # Selected-object summary
        # --------------------------------------------------------
        self.info_group = QGroupBox("SELECTED OBJECT")
        info_layout = QVBoxLayout(self.info_group)

        info_control_row = QHBoxLayout()
        info_control_row.addStretch(1)

        self.info_toggle_button = QPushButton("−")
        self.info_toggle_button.setToolTip(
            "Minimize / expand the selected-object summary"
        )
        self.info_toggle_button.setFixedSize(26, 22)
        self.info_toggle_button.clicked.connect(
            self.toggle_selected_object_summary
        )
        info_control_row.addWidget(self.info_toggle_button)

        info_layout.addLayout(info_control_row)

        self.selection_label = QLabel("None")
        self.selection_label.setWordWrap(True)
        self.selection_label.setStyleSheet(
            "background: #20242a; padding: 8px; border-radius: 4px;"
        )
        info_layout.addWidget(self.selection_label)
        inspector_layout.addWidget(self.info_group)

        # --------------------------------------------------------
        # Editable properties
        # --------------------------------------------------------
        self.properties_group = QGroupBox("PROPERTIES")
        self.properties_form = QFormLayout(self.properties_group)

        self.prop_x = self._make_spinbox(-10000.0, 10000.0, 1.0, 1, " m")
        self.prop_y = self._make_spinbox(-10000.0, 10000.0, 1.0, 1, " m")
        self.prop_rotation = self._make_spinbox(0.0, 359.9, 1.0, 1, "°")
        self.prop_length = self._make_spinbox(1.0, 1000.0, 1.0, 1, " m")
        self.prop_width = self._make_spinbox(1.0, 50.0, 0.5, 1, " m")
        self.prop_radius = self._make_spinbox(1.0, 1000.0, 1.0, 1, " m")
        self.prop_arm = self._make_spinbox(2.0, 1000.0, 1.0, 1, " m")

        self.properties_form.addRow("X", self.prop_x)
        self.properties_form.addRow("Y", self.prop_y)
        self.properties_form.addRow("Rotation", self.prop_rotation)
        self.properties_form.addRow("Length", self.prop_length)
        self.properties_form.addRow("Width", self.prop_width)
        self.properties_form.addRow("Radius", self.prop_radius)
        self.properties_form.addRow("Arm length", self.prop_arm)

        self.prop_x.valueChanged.connect(self.apply_position_properties)
        self.prop_y.valueChanged.connect(self.apply_position_properties)
        self.prop_rotation.valueChanged.connect(self.apply_rotation_property)
        self.prop_length.valueChanged.connect(self.apply_length_property)
        self.prop_width.valueChanged.connect(self.apply_width_property)
        self.prop_radius.valueChanged.connect(self.apply_radius_property)
        self.prop_arm.valueChanged.connect(self.apply_arm_property)

        # Effective QLabs dimensions are read-only and derived from project scale.
        self.prop_effective = QLabel("")
        self.prop_effective.setWordWrap(True)
        self.prop_effective.setStyleSheet(
            "background: #20242a; padding: 6px; border-radius: 4px; color: #cfd6de;"
        )
        self.properties_form.addRow("QLabs effective", self.prop_effective)

        inspector_layout.addWidget(self.properties_group)

        # --------------------------------------------------------
        # QCar2 camera
        # --------------------------------------------------------
        self.camera_group = QGroupBox("QCAR2 CAMERA")
        camera_form = QFormLayout(self.camera_group)

        self.prop_camera_view = QComboBox()
        self.prop_camera_view.addItem(
            "Third person (trailing)",
            QCAR_CAMERA_THIRD_PERSON,
        )
        self.prop_camera_view.addItem(
            "First person (front CSI)",
            QCAR_CAMERA_FIRST_PERSON,
        )
        self.prop_camera_view.currentIndexChanged.connect(
            self.apply_camera_property
        )
        camera_form.addRow("View", self.prop_camera_view)

        camera_note = QLabel(
            "First person uses QCar2 CAMERA_CSI_FRONT. "
            "Third person uses CAMERA_TRAILING."
        )
        camera_note.setWordWrap(True)
        camera_note.setStyleSheet("color: #aeb6bf; font-size: 11px;")
        camera_form.addRow(camera_note)

        self.camera_group.setVisible(False)
        inspector_layout.addWidget(self.camera_group)

        # --------------------------------------------------------
        # QLabs actor properties
        # --------------------------------------------------------
        self.actor_group = QGroupBox("QLABS ACTOR")
        actor_form = QFormLayout(self.actor_group)

        self.prop_actor_z = self._make_spinbox(-100.0, 1000.0, 0.05, 3, " m")
        self.prop_actor_scale = self._make_spinbox(0.01, 100.0, 0.1, 2, "")
        self.prop_actor_scale_project = QCheckBox("Scale actor with project")

        self.prop_actor_configuration = QComboBox()
        for config in range(3):
            self.prop_actor_configuration.addItem(f"Configuration {config}", config)

        self.prop_traffic_color = QComboBox()
        self.prop_traffic_color.addItem("Off", "off")
        self.prop_traffic_color.addItem("Red", "red")
        self.prop_traffic_color.addItem("Yellow", "yellow")
        self.prop_traffic_color.addItem("Green", "green")

        self.prop_building_length = self._make_spinbox(0.1, 1000.0, 0.5, 2, " m")
        self.prop_building_width = self._make_spinbox(0.1, 1000.0, 0.5, 2, " m")
        self.prop_building_height = self._make_spinbox(0.1, 1000.0, 0.5, 2, " m")

        self.prop_building_r = QLineEdit(str(DEFAULT_BUILDING_RGB[0]))
        self.prop_building_g = QLineEdit(str(DEFAULT_BUILDING_RGB[1]))
        self.prop_building_b = QLineEdit(str(DEFAULT_BUILDING_RGB[2]))

        for rgb_input in (
            self.prop_building_r,
            self.prop_building_g,
            self.prop_building_b,
        ):
            rgb_input.setValidator(QIntValidator(0, 255, rgb_input))
            rgb_input.setMaximumWidth(52)
            rgb_input.setAlignment(Qt.AlignmentFlag.AlignCenter)

        building_rgb_widget = QWidget()
        building_rgb_layout = QHBoxLayout(building_rgb_widget)
        building_rgb_layout.setContentsMargins(0, 0, 0, 0)
        building_rgb_layout.setSpacing(5)
        building_rgb_layout.addWidget(QLabel("R"))
        building_rgb_layout.addWidget(self.prop_building_r)
        building_rgb_layout.addWidget(QLabel("G"))
        building_rgb_layout.addWidget(self.prop_building_g)
        building_rgb_layout.addWidget(QLabel("B"))
        building_rgb_layout.addWidget(self.prop_building_b)

        actor_form.addRow("Base Z", self.prop_actor_z)
        actor_form.addRow("Actor scale", self.prop_actor_scale)
        actor_form.addRow("Project scale", self.prop_actor_scale_project)
        actor_form.addRow("Configuration", self.prop_actor_configuration)
        actor_form.addRow("Initial light", self.prop_traffic_color)
        actor_form.addRow("Box length", self.prop_building_length)
        actor_form.addRow("Box width", self.prop_building_width)
        actor_form.addRow("Box height", self.prop_building_height)
        actor_form.addRow("Box RGB", building_rgb_widget)

        self.prop_actor_z.valueChanged.connect(self.apply_actor_properties)
        self.prop_actor_scale.valueChanged.connect(self.apply_actor_properties)
        self.prop_actor_scale_project.toggled.connect(self.apply_actor_properties)
        self.prop_actor_configuration.currentIndexChanged.connect(
            self.apply_actor_properties
        )
        self.prop_traffic_color.currentIndexChanged.connect(
            self.apply_actor_properties
        )
        self.prop_building_length.valueChanged.connect(self.apply_actor_properties)
        self.prop_building_width.valueChanged.connect(self.apply_actor_properties)
        self.prop_building_height.valueChanged.connect(self.apply_actor_properties)
        self.prop_building_r.editingFinished.connect(self.apply_actor_properties)
        self.prop_building_g.editingFinished.connect(self.apply_actor_properties)
        self.prop_building_b.editingFinished.connect(self.apply_actor_properties)

        self.actor_group.setVisible(False)
        inspector_layout.addWidget(self.actor_group)

        # --------------------------------------------------------
        # Experiment properties
        # --------------------------------------------------------
        self.experiment_group = QGroupBox("EXPERIMENT")
        experiment_form = QFormLayout(self.experiment_group)

        self.prop_experiment_spawn_mode = QComboBox()
        self.prop_experiment_spawn_mode.addItem(
            "Immediate",
            EXPERIMENT_SPAWN_IMMEDIATE,
        )
        self.prop_experiment_spawn_mode.addItem(
            "Triggered",
            EXPERIMENT_SPAWN_TRIGGERED,
        )

        self.prop_person_configuration = QComboBox()
        for config in range(12):
            self.prop_person_configuration.addItem(
                f"Person {config}",
                config,
            )

        self.prop_animal_type = QComboBox()
        self.prop_animal_type.addItem("Goat", "goat")
        self.prop_animal_type.addItem("Sheep", "sheep")
        self.prop_animal_type.addItem("Cow", "cow")

        self.prop_experiment_move = QCheckBox("Move after activation")
        self.prop_destination_x = self._make_spinbox(
            -10000.0, 10000.0, 0.5, 2, " m"
        )
        self.prop_destination_y = self._make_spinbox(
            -10000.0, 10000.0, 0.5, 2, " m"
        )

        self.prop_movement_gait = QComboBox()

        self.prop_movement_mode = QComboBox()
        self.prop_movement_mode.addItem("Once", MOVEMENT_ONCE)
        self.prop_movement_mode.addItem("Loop", MOVEMENT_LOOP)
        self.prop_movement_mode.addItem("Ping-pong", MOVEMENT_PINGPONG)

        self.prop_despawn_on_finish = QCheckBox("Despawn after route")
        self.prop_secondary_qcar_speed = self._make_spinbox(0.1, 100.0, 0.5, 1, " m/s")

        self.path_widget = QWidget()
        path_widget = self.path_widget
        path_layout = QVBoxLayout(path_widget)
        path_layout.setContentsMargins(0, 0, 0, 0)
        path_layout.setSpacing(4)
        self.path_summary_label = QLabel("0 waypoints")
        self.path_summary_label.setStyleSheet("color: #aeb6bf;")
        path_layout.addWidget(self.path_summary_label)
        path_buttons = QHBoxLayout()
        self.path_draw_button = QPushButton("Draw / Add")
        self.path_remove_button = QPushButton("Remove last")
        self.path_clear_button = QPushButton("Clear")
        self.path_draw_button.clicked.connect(self.start_path_editing)
        self.path_remove_button.clicked.connect(self.remove_last_waypoint)
        self.path_clear_button.clicked.connect(self.clear_movement_path)
        path_buttons.addWidget(self.path_draw_button)
        path_buttons.addWidget(self.path_remove_button)
        path_buttons.addWidget(self.path_clear_button)
        path_layout.addLayout(path_buttons)

        self.prop_trigger_radius = self._make_spinbox(
            0.1, 1000.0, 0.5, 2, " m"
        )

        self.prop_trigger_action = QComboBox()
        self.prop_trigger_action.addItem(
            "Activate experiment actor",
            TRIGGER_ACTION_ACTIVATE_ACTOR,
        )
        self.prop_trigger_action.addItem(
            "Change traffic light",
            TRIGGER_ACTION_TRAFFIC_LIGHT,
        )

        self.prop_trigger_target = QComboBox()

        self.prop_trigger_traffic_color = QComboBox()
        self.prop_trigger_traffic_color.addItem("Off", "off")
        self.prop_trigger_traffic_color.addItem("Red", "red")
        self.prop_trigger_traffic_color.addItem("Yellow", "yellow")
        self.prop_trigger_traffic_color.addItem("Green", "green")

        self.prop_trigger_one_shot = QCheckBox("Fire once only")
        self.prop_trigger_one_shot.setChecked(True)

        experiment_form.addRow(
            "Spawn mode",
            self.prop_experiment_spawn_mode,
        )
        experiment_form.addRow(
            "Person",
            self.prop_person_configuration,
        )
        experiment_form.addRow(
            "Animal",
            self.prop_animal_type,
        )
        experiment_form.addRow(
            "Movement",
            self.prop_experiment_move,
        )
        experiment_form.addRow(
            "Destination X",
            self.prop_destination_x,
        )
        experiment_form.addRow(
            "Destination Y",
            self.prop_destination_y,
        )
        experiment_form.addRow(
            "Gait",
            self.prop_movement_gait,
        )
        experiment_form.addRow("Path", path_widget)
        experiment_form.addRow("Route mode", self.prop_movement_mode)
        experiment_form.addRow("Finish", self.prop_despawn_on_finish)
        experiment_form.addRow("QCar speed", self.prop_secondary_qcar_speed)
        experiment_form.addRow(
            "Trigger radius",
            self.prop_trigger_radius,
        )
        experiment_form.addRow(
            "Action",
            self.prop_trigger_action,
        )
        experiment_form.addRow(
            "Target",
            self.prop_trigger_target,
        )
        experiment_form.addRow(
            "Light color",
            self.prop_trigger_traffic_color,
        )
        experiment_form.addRow(
            "Behavior",
            self.prop_trigger_one_shot,
        )

        self.prop_experiment_spawn_mode.currentIndexChanged.connect(
            self.apply_experiment_properties
        )
        self.prop_person_configuration.currentIndexChanged.connect(
            self.apply_experiment_properties
        )
        self.prop_animal_type.currentIndexChanged.connect(
            self.apply_experiment_properties
        )
        self.prop_experiment_move.toggled.connect(
            self.apply_experiment_properties
        )
        self.prop_destination_x.valueChanged.connect(
            self.apply_experiment_properties
        )
        self.prop_destination_y.valueChanged.connect(
            self.apply_experiment_properties
        )
        self.prop_movement_gait.currentIndexChanged.connect(
            self.apply_experiment_properties
        )
        self.prop_movement_mode.currentIndexChanged.connect(self.apply_experiment_properties)
        self.prop_despawn_on_finish.toggled.connect(self.apply_experiment_properties)
        self.prop_secondary_qcar_speed.valueChanged.connect(self.apply_experiment_properties)
        self.prop_trigger_radius.valueChanged.connect(
            self.apply_experiment_properties
        )
        self.prop_trigger_action.currentIndexChanged.connect(
            self._trigger_action_changed
        )
        self.prop_trigger_target.currentIndexChanged.connect(
            self.apply_experiment_properties
        )
        self.prop_trigger_traffic_color.currentIndexChanged.connect(
            self.apply_experiment_properties
        )
        self.prop_trigger_one_shot.toggled.connect(
            self.apply_experiment_properties
        )

        self.experiment_group.setVisible(False)
        inspector_layout.addWidget(self.experiment_group)

        # --------------------------------------------------------
        # Lane-following guide line
        # --------------------------------------------------------
        self.guide_group = QGroupBox("LANE-FOLLOWING GUIDE")
        guide_form = QFormLayout(self.guide_group)

        self.prop_guide_enabled = QCheckBox("Enabled")
        self.prop_guide_position = QComboBox()
        self.prop_guide_position.addItem("Left lane", "left")
        self.prop_guide_position.addItem("Center", "center")
        self.prop_guide_position.addItem("Right lane", "right")
        self.prop_guide_position.addItem("Custom offset", "custom")
        self.prop_guide_offset = self._make_spinbox(-50.0, 50.0, 0.1, 2, " m")
        self.prop_guide_color = QComboBox()
        for name in ("yellow", "white", "blue", "red"):
            self.prop_guide_color.addItem(name.title(), name)
        self.prop_guide_color.addItem("Custom RGB", "custom")

        self.prop_guide_r = QLineEdit("255")
        self.prop_guide_g = QLineEdit("215")
        self.prop_guide_b = QLineEdit("0")

        for rgb_input in (
            self.prop_guide_r,
            self.prop_guide_g,
            self.prop_guide_b,
        ):
            rgb_input.setValidator(QIntValidator(0, 255, rgb_input))
            rgb_input.setMaximumWidth(52)
            rgb_input.setAlignment(Qt.AlignmentFlag.AlignCenter)

        rgb_widget = QWidget()
        rgb_layout = QHBoxLayout(rgb_widget)
        rgb_layout.setContentsMargins(0, 0, 0, 0)
        rgb_layout.setSpacing(5)
        rgb_layout.addWidget(QLabel("R"))
        rgb_layout.addWidget(self.prop_guide_r)
        rgb_layout.addWidget(QLabel("G"))
        rgb_layout.addWidget(self.prop_guide_g)
        rgb_layout.addWidget(QLabel("B"))
        rgb_layout.addWidget(self.prop_guide_b)

        self.prop_guide_width = self._make_spinbox(0.01, 5.0, 0.01, 2, " m")
        self.prop_guide_style = QComboBox()
        self.prop_guide_style.addItem("Solid", "solid")
        self.prop_guide_style.addItem("Dashed", "dashed")
        self.prop_guide_scale_width = QCheckBox("Scale width with project")

        guide_form.addRow("Guide", self.prop_guide_enabled)
        guide_form.addRow("Position", self.prop_guide_position)
        guide_form.addRow("Custom offset", self.prop_guide_offset)
        guide_form.addRow("Color", self.prop_guide_color)
        guide_form.addRow("RGB (0-255)", rgb_widget)
        guide_form.addRow("Design width", self.prop_guide_width)
        guide_form.addRow("Style", self.prop_guide_style)
        guide_form.addRow("QLabs width", self.prop_guide_scale_width)

        guide_note = QLabel(
            "Left/right place the guide at the center of each half of a two-lane road. "
            "Disable width scaling if a 1:10 line becomes too thin for camera detection."
        )
        guide_note.setWordWrap(True)
        guide_note.setStyleSheet("color: #aeb6bf; font-size: 11px;")
        guide_form.addRow(guide_note)

        self.prop_guide_enabled.toggled.connect(self.apply_guide_properties)
        self.prop_guide_position.currentIndexChanged.connect(self.apply_guide_properties)
        self.prop_guide_offset.valueChanged.connect(self.apply_guide_properties)
        self.prop_guide_color.currentIndexChanged.connect(self.apply_guide_properties)
        self.prop_guide_r.editingFinished.connect(self.apply_guide_properties)
        self.prop_guide_g.editingFinished.connect(self.apply_guide_properties)
        self.prop_guide_b.editingFinished.connect(self.apply_guide_properties)
        self.prop_guide_width.valueChanged.connect(self.apply_guide_properties)
        self.prop_guide_style.currentIndexChanged.connect(self.apply_guide_properties)
        self.prop_guide_scale_width.toggled.connect(self.apply_guide_properties)

        self.guide_group.setVisible(False)
        inspector_layout.addWidget(self.guide_group)
        inspector_layout.addStretch(1)

        side_layout.addStretch(1)

        self.help_label = QLabel()
        self.help_label.setWordWrap(True)
        self.help_label.setStyleSheet("color: #bfc6ce;")
        side_layout.addWidget(self.help_label)
        self._update_help_text()

        sidebar_scroll = QScrollArea()
        sidebar_scroll.setWidgetResizable(True)
        sidebar_scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        sidebar_scroll.setWidget(sidebar_contents)
        sidebar_scroll.setFixedWidth(300)

        # The inspector is independently scrollable from the component
        # library. This keeps long property/experiment/path panels usable
        # without sacrificing canvas height.
        inspector_scroll = QScrollArea()
        inspector_scroll.setWidgetResizable(True)
        inspector_scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        inspector_scroll.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded
        )
        inspector_scroll.setWidget(inspector_contents)
        inspector_scroll.setMinimumWidth(345)
        inspector_scroll.setMaximumWidth(380)

        # --------------------------------------------------------
        # Canvas
        # --------------------------------------------------------
        canvas_container = QWidget()
        canvas_layout = QVBoxLayout(canvas_container)
        canvas_layout.setContentsMargins(0, 0, 0, 0)
        canvas_layout.addWidget(self.view)

        bottom = QHBoxLayout()
        self.cursor_label = QLabel("Cursor: X 0.0 m | Y 0.0 m")
        self.zoom_label = QLabel("Zoom: 100%")
        self.snap_status_label = QLabel("Endpoint snap: ON")
        self.scale_status_label = QLabel("Scale: 1:1")
        bottom.addWidget(self.cursor_label)
        bottom.addStretch(1)
        self.grid_status_label = QLabel("Grid: adaptive")
        bottom.addWidget(self.grid_status_label)
        bottom.addSpacing(20)
        bottom.addWidget(self.scale_status_label)
        bottom.addSpacing(20)
        bottom.addWidget(self.snap_status_label)
        bottom.addSpacing(20)
        bottom.addWidget(self.zoom_label)
        canvas_layout.addLayout(bottom)

        root.addWidget(sidebar_scroll)
        root.addWidget(canvas_container, 1)
        root.addWidget(inspector_scroll)

        self.setCentralWidget(central)

    def toggle_selected_object_summary(self):
        """Collapse/expand only the summary contents.

        The selected object itself and all editable properties remain active.
        """
        currently_visible = self.selection_label.isVisible()

        self.selection_label.setVisible(not currently_visible)
        self.info_toggle_button.setText(
            "+" if currently_visible else "−"
        )
        self.info_toggle_button.setToolTip(
            "Expand selected-object summary"
            if currently_visible
            else "Minimize selected-object summary"
        )

        # Let the scroll area's size constraint update immediately.
        self.info_group.updateGeometry()

    def _build_actions(self):
        new_action = QAction("New", self)
        new_action.setShortcut(QKeySequence.StandardKey.New)
        new_action.triggered.connect(self.new_track)

        open_action = QAction("Open...", self)
        open_action.setShortcut(QKeySequence.StandardKey.Open)
        open_action.triggered.connect(self.load_track)

        save_action = QAction("Save", self)
        save_action.setShortcut(QKeySequence.StandardKey.Save)
        save_action.triggered.connect(self.save_track)

        save_as_action = QAction("Save As...", self)
        save_as_action.setShortcut(QKeySequence.StandardKey.SaveAs)
        save_as_action.triggered.connect(lambda: self.save_track(save_as=True))

        export_action = QAction("Export QLabs Setup...", self)
        export_action.setShortcut(QKeySequence("Ctrl+E"))
        export_action.triggered.connect(self.export_qlabs_setup)

        quit_action = QAction("Exit", self)
        quit_action.setShortcut(QKeySequence.StandardKey.Quit)
        quit_action.triggered.connect(self.close)

        rotate_action = QAction("Rotate +Step", self)
        rotate_action.setShortcut(QKeySequence("R"))
        rotate_action.triggered.connect(
            lambda: self.rotate_selected(self.rotation_step_deg)
        )
        self.addAction(rotate_action)

        rotate_back_action = QAction("Rotate -Step", self)
        rotate_back_action.setShortcut(QKeySequence("Shift+R"))
        rotate_back_action.triggered.connect(
            lambda: self.rotate_selected(-self.rotation_step_deg)
        )
        self.addAction(rotate_back_action)

        duplicate_action = QAction("Duplicate", self)
        duplicate_action.setShortcut(QKeySequence("Ctrl+D"))
        duplicate_action.triggered.connect(self.duplicate_selected)
        self.addAction(duplicate_action)

        delete_action = QAction("Delete", self)
        delete_action.setShortcut(QKeySequence("Delete"))
        delete_action.triggered.connect(self.delete_selected)
        self.addAction(delete_action)

        file_menu = self.menuBar().addMenu("File")
        file_menu.addAction(new_action)
        file_menu.addAction(open_action)
        file_menu.addSeparator()
        file_menu.addAction(save_action)
        file_menu.addAction(save_as_action)
        file_menu.addSeparator()
        file_menu.addAction(export_action)
        file_menu.addSeparator()
        file_menu.addAction(quit_action)

        edit_menu = self.menuBar().addMenu("Edit")
        edit_menu.addAction(duplicate_action)
        edit_menu.addAction(rotate_action)
        edit_menu.addAction(rotate_back_action)
        edit_menu.addAction(delete_action)

    # ------------------------------------------------------------
    # Component creation
    # ------------------------------------------------------------

    def _used_readable_identifiers(self, exclude=None) -> set[str]:
        return {
            str(item.identifier)
            for item in self.scene.track_items()
            if item is not exclude and getattr(item, "identifier", "")
        }

    def _next_readable_identifier(self, prefix: str, start_index: int = 0, exclude=None) -> str:
        used = self._used_readable_identifiers(exclude=exclude)
        index = int(start_index)
        while f"{prefix}{index}" in used:
            index += 1
        return f"{prefix}{index}"

    def _assign_readable_identifier_if_needed(self, item: TrackItem):
        if getattr(item, "identifier", ""):
            item.set_readable_identifier(item.identifier)
            return

        if isinstance(item, QCar2StartItem):
            item.set_readable_identifier("QCar_0")
        elif isinstance(item, SecondaryQCarItem):
            item.set_readable_identifier(
                self._next_readable_identifier("QCar_", 1, exclude=item)
            )
        elif isinstance(item, PersonItem):
            item.set_readable_identifier(
                self._next_readable_identifier("person", 0, exclude=item)
            )
        elif isinstance(item, AnimalItem):
            item.set_readable_identifier(
                self._next_readable_identifier("animal", 0, exclude=item)
            )
        elif isinstance(item, TrafficLightItem):
            item.set_readable_identifier(
                self._next_readable_identifier("trafficLight", 0, exclude=item)
            )

    def _ensure_all_readable_identifiers(self):
        # Reserve QCar_0 for the primary controlled QCar before assigning
        # secondary vehicle aliases.
        ordered = sorted(
            self.scene.track_items(),
            key=lambda item: 0 if isinstance(item, QCar2StartItem) else 1,
        )
        for item in ordered:
            self._assign_readable_identifier_if_needed(item)

    def _add_item_at_view_center(self, item: TrackItem):
        center_scene = self.view.mapToScene(self.view.viewport().rect().center())
        item.setPos(
            QPointF(
                snap_value(center_scene.x(), GRID_PIXELS),
                snap_value(center_scene.y(), GRID_PIXELS),
            )
        )

        self._assign_readable_identifier_if_needed(item)

        self.scene.clearSelection()
        self.scene.addItem(item)
        item.setSelected(True)
        self.update_selection_info()

    def add_straight_road(self):
        self._add_item_at_view_center(StraightRoadItem())

    def add_curve_45(self):
        self._add_item_at_view_center(Curve45RoadItem())

    def add_curve_90(self):
        self._add_item_at_view_center(Curve90RoadItem())

    def add_t_junction(self):
        self._add_item_at_view_center(TJunctionItem())

    def add_cross_intersection(self):
        self._add_item_at_view_center(CrossIntersectionItem())

    def add_road_end(self):
        self._add_item_at_view_center(RoadEndItem())

    def add_traffic_light(self):
        self._add_item_at_view_center(TrafficLightItem())

    def add_stop_sign(self):
        self._add_item_at_view_center(StopSignItem())

    def add_yield_sign(self):
        self._add_item_at_view_center(YieldSignItem())

    def add_roundabout_sign(self):
        self._add_item_at_view_center(RoundaboutSignItem())

    def add_crosswalk(self):
        self._add_item_at_view_center(CrosswalkItem())

    def add_building_box(self):
        self._add_item_at_view_center(BuildingBoxItem())

    def add_person(self):
        item = PersonItem()
        center = self.view.mapToScene(
            self.view.viewport().rect().center()
        )
        x_m, y_m = scene_to_world(center)
        item.destination_x_m = x_m
        item.destination_y_m = y_m
        self._add_item_at_view_center(item)

    def add_animal(self):
        item = AnimalItem()
        center = self.view.mapToScene(
            self.view.viewport().rect().center()
        )
        x_m, y_m = scene_to_world(center)
        item.destination_x_m = x_m
        item.destination_y_m = y_m
        self._add_item_at_view_center(item)

    def add_trigger_zone(self):
        self._add_item_at_view_center(TriggerZoneItem())

    def add_secondary_qcar(self):
        item = SecondaryQCarItem()
        center = self.view.mapToScene(self.view.viewport().rect().center())
        x_m, y_m = scene_to_world(center)
        item.destination_x_m = x_m
        item.destination_y_m = y_m
        self._add_item_at_view_center(item)

    def add_qcar2_start(self):
        existing = [
            item
            for item in self.scene.track_items()
            if isinstance(item, QCar2StartItem)
        ]

        if existing:
            self.scene.clearSelection()
            existing[0].setSelected(True)
            self.view.centerOn(existing[0])
            self.update_selection_info()
            QMessageBox.information(
                self,
                "QCar2 Start",
                "This project already has a QCar2 Start marker. "
                "The existing marker has been selected.",
            )
            return

        self._add_item_at_view_center(QCar2StartItem())

    def environment_settings_changed(self, *args):
        self.environment_enabled = self.environment_enabled_checkbox.isChecked()
        self.environment_weather = str(self.weather_combo.currentData() or "clear_skies")
        self.environment_time_of_day = float(self.time_of_day_spin.value())

    def _set_environment_from_data(self, data: dict):
        self.environment_enabled = bool(data.get("enabled", True))
        self.environment_weather = str(data.get("weather", "clear_skies"))
        self.environment_time_of_day = max(0.0, min(24.0, float(data.get("time_of_day", 12.0))))

        self.environment_enabled_checkbox.blockSignals(True)
        self.weather_combo.blockSignals(True)
        self.time_of_day_spin.blockSignals(True)
        try:
            self.environment_enabled_checkbox.setChecked(self.environment_enabled)
            idx = self.weather_combo.findData(self.environment_weather)
            self.weather_combo.setCurrentIndex(max(0, idx))
            self.time_of_day_spin.setValue(self.environment_time_of_day)
        finally:
            self.environment_enabled_checkbox.blockSignals(False)
            self.weather_combo.blockSignals(False)
            self.time_of_day_spin.blockSignals(False)

    # ------------------------------------------------------------
    # Workspace reference
    # ------------------------------------------------------------

    def workspace_mode_changed(self, *args):
        self.workspace_mode = str(
            self.workspace_mode_combo.currentData()
            or WORKSPACE_CUSTOM
        )
        self._apply_workspace_mode(fit_reference=True)

    def workspace_display_changed(self, *args):
        self.workspace_show_road_reference = (
            self.workspace_show_road_checkbox.isChecked()
        )
        self.workspace_show_navigation_regions = (
            self.workspace_show_nav_checkbox.isChecked()
        )
        self.workspace_show_reference_points = (
            self.workspace_show_points_checkbox.isChecked()
        )
        self.workspace_show_reference_labels = (
            self.workspace_show_labels_checkbox.isChecked()
        )

        self.view.viewport().update()

    def _set_workspace_from_data(self, workspace: dict):
        mode = str(
            workspace.get("mode", WORKSPACE_CUSTOM)
        )

        if mode not in {
            WORKSPACE_CUSTOM,
            WORKSPACE_OPEN_ROAD,
        }:
            mode = WORKSPACE_CUSTOM

        road = bool(
            workspace.get(
                "show_road_reference",
                True,
            )
        )
        nav = bool(
            workspace.get(
                "show_navigation_regions",
                True,
            )
        )
        points = bool(
            workspace.get(
                "show_reference_points",
                True,
            )
        )
        labels = bool(
            workspace.get(
                "show_reference_labels",
                True,
            )
        )

        widgets = (
            self.workspace_mode_combo,
            self.workspace_show_road_checkbox,
            self.workspace_show_nav_checkbox,
            self.workspace_show_points_checkbox,
            self.workspace_show_labels_checkbox,
        )

        for widget in widgets:
            widget.blockSignals(True)

        try:
            index = self.workspace_mode_combo.findData(
                mode
            )
            self.workspace_mode_combo.setCurrentIndex(
                max(0, index)
            )

            self.workspace_show_road_checkbox.setChecked(
                road
            )
            self.workspace_show_nav_checkbox.setChecked(
                nav
            )
            self.workspace_show_points_checkbox.setChecked(
                points
            )
            self.workspace_show_labels_checkbox.setChecked(
                labels
            )
        finally:
            for widget in widgets:
                widget.blockSignals(False)

        self.workspace_mode = mode
        self.workspace_show_road_reference = road
        self.workspace_show_navigation_regions = nav
        self.workspace_show_reference_points = points
        self.workspace_show_reference_labels = labels

        self._apply_workspace_mode(
            fit_reference=False
        )

    def _open_road_scene_rect(
        self,
        margin_m: float = 500.0,
    ) -> QRectF:
        bounds = self.open_road_reference.get(
            "bounds",
            {},
        )

        min_x = float(
            bounds.get("min_x", -9500.0)
        )
        max_x = float(
            bounds.get("max_x", 9500.0)
        )
        min_y = float(
            bounds.get("min_y", -5000.0)
        )
        max_y = float(
            bounds.get("max_y", 500.0)
        )

        left = (
            min_x
            - margin_m
        ) * PIXELS_PER_METER
        right = (
            max_x
            + margin_m
        ) * PIXELS_PER_METER

        # Qt Y grows downward, so larger world Y is the scene top.
        top = -(
            max_y
            + margin_m
        ) * PIXELS_PER_METER
        bottom = -(
            min_y
            - margin_m
        ) * PIXELS_PER_METER

        return QRectF(
            left,
            top,
            right - left,
            bottom - top,
        )

    def _custom_scene_rect(self) -> QRectF:
        default_rect = QRectF(
            -4000.0,
            -4000.0,
            8000.0,
            8000.0,
        )

        items_rect = self.scene.itemsBoundingRect()

        if items_rect.isNull():
            return default_rect

        return default_rect.united(
            items_rect.adjusted(
                -1000.0,
                -1000.0,
                1000.0,
                1000.0,
            )
        )

    def _apply_workspace_mode(
        self,
        fit_reference: bool = False,
    ):
        open_road = (
            self.workspace_mode
            == WORKSPACE_OPEN_ROAD
        )

        for widget in (
            self.workspace_show_road_checkbox,
            self.workspace_show_nav_checkbox,
            self.workspace_show_points_checkbox,
            self.workspace_show_labels_checkbox,
            self.fit_workspace_button,
        ):
            widget.setEnabled(open_road)

        if open_road:
            # The overlay is already expressed in native QLabs world meters.
            # Scaling those X/Y coordinates would move actors to the wrong
            # physical location, so Open Road reference projects are 1:1.
            if self.project_scale_combo.currentIndex() != 0:
                self.project_scale_combo.setCurrentIndex(0)

            self.project_scale_combo.setEnabled(
                False
            )
            self.custom_scale_denominator.setEnabled(
                False
            )

            self.scale_help_label.setText(
                "Open Road reference coordinates are native QLabs meters. "
                "Project scale is locked to 1:1 while this workspace is selected."
            )

            calibration = self.open_road_reference.get(
                "calibration",
                {},
            )

            rms = calibration.get(
                "anchor_rms_error_m",
                None,
            )

            accuracy_text = (
                f" Approximate anchor-fit RMS: {float(rms):.1f} m."
                if rms is not None
                else ""
            )

            self.workspace_reference_note.setText(
                "2-D documentation-derived placement overlay only; "
                "it contains no road elevation/Z and is never exported. "
                f"Visual road width ≈ {OPEN_ROAD_REFERENCE_TOTAL_WIDTH_M:.1f} m "
                f"({OPEN_ROAD_REFERENCE_LANES_PER_SIDE} lanes each direction, "
                f"{OPEN_ROAD_REFERENCE_LANE_WIDTH_M:.1f} m/lane + "
                f"{OPEN_ROAD_REFERENCE_SEPARATOR_WIDTH_M:.1f} m separator)."
                + accuracy_text
                + f" Source data: {self.open_road_reference_source}."
            )

            self.scene.setSceneRect(
                self._open_road_scene_rect()
            )

            if fit_reference:
                self.fit_open_road_reference()

        else:
            self.project_scale_combo.setEnabled(
                True
            )
            self.custom_scale_denominator.setEnabled(
                True
            )

            self.scale_help_label.setText(
                "Canvas values stay in full-scale design meters. "
                "The selected scale is applied to QLabs effective dimensions/export."
            )

            self.workspace_reference_note.setText(
                "No built-in workspace reference is shown. "
                "Use the normal road components to design a custom track."
            )

            self.scene.setSceneRect(
                self._custom_scene_rect()
            )

            if fit_reference:
                self.view.centerOn(
                    0.0,
                    0.0,
                )

        self.view.viewport().update()
        self.update_zoom_label()

    def fit_open_road_reference(self):
        if (
            self.workspace_mode
            != WORKSPACE_OPEN_ROAD
        ):
            return

        rect = self._open_road_scene_rect(
            margin_m=250.0
        )

        if rect.isValid():
            self.view.fitInView(
                rect,
                Qt.AspectRatioMode.KeepAspectRatio,
            )

            self.update_zoom_label()

    def draw_workspace_reference(
        self,
        painter: QPainter,
        rect: QRectF,
    ):
        if (
            self.workspace_mode
            != WORKSPACE_OPEN_ROAD
        ):
            return

        reference = self.open_road_reference
        view_scale = max(
            abs(self.view.transform().m11()),
            1e-9,
        )

        # --------------------------------------------------------
        # Navigation-region overlay
        # --------------------------------------------------------
        if self.workspace_show_navigation_regions:
            nav_pen = QPen(
                QColor(
                    255,
                    95,
                    75,
                    210,
                ),
                2,
            )
            nav_pen.setCosmetic(True)

            painter.setPen(nav_pen)
            painter.setBrush(
                QColor(
                    255,
                    80,
                    70,
                    32,
                )
            )

            for region in reference.get(
                "navigation_regions",
                [],
            ):
                polygon = region.get(
                    "polygon",
                    [],
                )

                if len(polygon) < 3:
                    continue

                path = QPainterPath()

                first = world_to_scene(
                    float(polygon[0][0]),
                    float(polygon[0][1]),
                )
                path.moveTo(first)

                for point in polygon[1:]:
                    path.lineTo(
                        world_to_scene(
                            float(point[0]),
                            float(point[1]),
                        )
                    )

                path.closeSubpath()
                painter.drawPath(path)

        # --------------------------------------------------------
        # Documentation-derived road loop + approximate lane width
        # --------------------------------------------------------
        if self.workspace_show_road_reference:
            road_data = reference.get(
                "road_reference",
                {},
            )
            points = road_data.get(
                "points",
                [],
            )
            road_closed = bool(
                road_data.get(
                    "closed",
                    False,
                )
            )

            if len(points) >= 2:
                road_path = _world_polyline_path(
                    points,
                    road_closed,
                )

                # Physical-width road band. This is deliberately NOT a
                # cosmetic pen: its width is expressed in world metres so
                # QCar/start markers can be compared against it at 1:1 scale.
                road_surface_pen = QPen(
                    QColor(
                        74,
                        80,
                        88,
                        210,
                    ),
                    OPEN_ROAD_REFERENCE_TOTAL_WIDTH_M
                    * PIXELS_PER_METER,
                )
                road_surface_pen.setCosmetic(False)
                road_surface_pen.setJoinStyle(
                    Qt.PenJoinStyle.RoundJoin
                )
                road_surface_pen.setCapStyle(
                    Qt.PenCapStyle.RoundCap
                )
                painter.setPen(road_surface_pen)
                painter.setBrush(
                    Qt.BrushStyle.NoBrush
                )
                painter.drawPath(road_path)

                # Approximate center separator band.
                separator_pen = QPen(
                    QColor(
                        40,
                        44,
                        50,
                        245,
                    ),
                    OPEN_ROAD_REFERENCE_SEPARATOR_WIDTH_M
                    * PIXELS_PER_METER,
                )
                separator_pen.setCosmetic(False)
                separator_pen.setJoinStyle(
                    Qt.PenJoinStyle.RoundJoin
                )
                separator_pen.setCapStyle(
                    Qt.PenCapStyle.RoundCap
                )
                painter.setPen(separator_pen)
                painter.drawPath(road_path)

                lane_width = (
                    OPEN_ROAD_REFERENCE_LANE_WIDTH_M
                )
                half_separator = (
                    OPEN_ROAD_REFERENCE_SEPARATOR_WIDTH_M
                    / 2.0
                )

                # White dashed lane dividers inside each 3-lane carriageway.
                lane_divider_pen = QPen(
                    QColor(
                        230,
                        234,
                        238,
                        220,
                    ),
                    1.5,
                )
                lane_divider_pen.setCosmetic(True)
                lane_divider_pen.setStyle(
                    Qt.PenStyle.DashLine
                )
                lane_divider_pen.setDashPattern(
                    [7.0, 7.0]
                )

                painter.setPen(lane_divider_pen)

                for side_sign in (-1.0, 1.0):
                    for divider_index in range(
                        1,
                        OPEN_ROAD_REFERENCE_LANES_PER_SIDE,
                    ):
                        offset_m = side_sign * (
                            half_separator
                            + divider_index * lane_width
                        )

                        divider_points = _offset_world_polyline(
                            points,
                            offset_m,
                            road_closed,
                        )
                        painter.drawPath(
                            _world_polyline_path(
                                divider_points,
                                road_closed,
                            )
                        )

                # Solid outer road edges.
                outer_edge_pen = QPen(
                    QColor(
                        245,
                        247,
                        250,
                        235,
                    ),
                    2.0,
                )
                outer_edge_pen.setCosmetic(True)
                outer_edge_pen.setStyle(
                    Qt.PenStyle.SolidLine
                )
                painter.setPen(outer_edge_pen)

                outer_offset = (
                    half_separator
                    + OPEN_ROAD_REFERENCE_LANES_PER_SIDE
                    * lane_width
                )

                for side_sign in (-1.0, 1.0):
                    edge_points = _offset_world_polyline(
                        points,
                        side_sign * outer_offset,
                        road_closed,
                    )
                    painter.drawPath(
                        _world_polyline_path(
                            edge_points,
                            road_closed,
                        )
                    )

                # Thin center reference so the original documentation-derived
                # trajectory remains visible inside the separator.
                center_reference_pen = QPen(
                    QColor(
                        255,
                        200,
                        70,
                        185,
                    ),
                    1.0,
                )
                center_reference_pen.setCosmetic(True)
                center_reference_pen.setStyle(
                    Qt.PenStyle.DotLine
                )
                painter.setPen(center_reference_pen)
                painter.drawPath(road_path)

        # --------------------------------------------------------
        # Published QLabs reference coordinates
        # --------------------------------------------------------
        if self.workspace_show_reference_points:
            point_pen = QPen(
                QColor(
                    255,
                    220,
                    80,
                    245,
                ),
                2,
            )
            point_pen.setCosmetic(True)
            painter.setPen(point_pen)
            painter.setBrush(
                QColor(
                    255,
                    190,
                    55,
                    220,
                )
            )

            marker_radius_scene = (
                6.0
                / view_scale
            )

            label_positions = []

            for point in reference.get(
                "reference_points",
                [],
            ):
                scene_pos = world_to_scene(
                    float(point.get("x", 0.0)),
                    float(point.get("y", 0.0)),
                )

                painter.drawEllipse(
                    scene_pos,
                    marker_radius_scene,
                    marker_radius_scene,
                )

                if self.workspace_show_reference_labels:
                    label_positions.append(
                        (
                            painter.worldTransform().map(
                                scene_pos
                            ),
                            str(
                                point.get(
                                    "name",
                                    "",
                                )
                            ),
                        )
                    )

            # Labels are painted in viewport/device coordinates so they remain
            # readable even when the full 18 km loop is fitted on screen.
            if label_positions:
                painter.save()
                painter.resetTransform()

                font = painter.font()
                font.setPixelSize(12)
                painter.setFont(font)

                painter.setPen(
                    QPen(
                        QColor(
                            255,
                            235,
                            150,
                        ),
                        1,
                    )
                )

                for device_pos, label in label_positions:
                    painter.drawText(
                        QPointF(
                            device_pos.x() + 9.0,
                            device_pos.y() - 8.0,
                        ),
                        label,
                    )

                painter.restore()

    # ------------------------------------------------------------
    # Project scale
    # ------------------------------------------------------------

    def project_scale_changed(self):
        factor = self.project_scale_combo.currentData()
        custom = factor is None
        self.custom_scale_label.setVisible(custom)
        self.custom_scale_denominator.setVisible(custom)

        if custom:
            self.custom_scale_changed()
            return

        self.project_scale_factor = float(factor)
        self.project_scale_name = self.project_scale_combo.currentText()
        self._refresh_scale_ui()

    def custom_scale_changed(self):
        if self.project_scale_combo.currentData() is not None:
            return
        denominator = max(1.0, float(self.custom_scale_denominator.value()))
        self.project_scale_factor = 1.0 / denominator
        self.project_scale_name = f"1:{denominator:g}"
        self._refresh_scale_ui()

    def _refresh_scale_ui(self):
        effective = DEFAULT_ROAD_WIDTH_M * self.project_scale_factor
        self.scale_preview_label.setText(
            f"{DEFAULT_ROAD_WIDTH_M:.2f} m design road → {effective:.3f} m in QLabs"
        )
        self.scale_status_label.setText(f"Scale: {self.project_scale_name}")
        self.update_selection_info()

    def _set_project_scale_from_data(self, project: dict):
        factor = float(project.get("scale_factor", 1.0))
        name = str(project.get("scale_name", ""))

        for i in range(self.project_scale_combo.count() - 1):
            item_factor = self.project_scale_combo.itemData(i)
            if item_factor is not None and math.isclose(float(item_factor), factor, rel_tol=1e-9):
                self.project_scale_combo.setCurrentIndex(i)
                return

        # Unknown/custom scale. Store it as a 1:N denominator.
        self.project_scale_combo.setCurrentIndex(self.project_scale_combo.count() - 1)
        denominator = 1.0 / max(factor, 1e-9)
        self.custom_scale_denominator.setValue(denominator)
        self.project_scale_factor = factor
        self.project_scale_name = name or f"1:{denominator:g}"
        self._refresh_scale_ui()

    # ------------------------------------------------------------
    # Editing
    # ------------------------------------------------------------

    def rotation_step_changed(self):
        value = self.rotation_step_combo.currentData()
        self.rotation_step_deg = float(value) if value is not None else ROTATION_STEP_DEG
        self.rotate_btn.setText(f"Rotate +{self.rotation_step_deg:g}°")
        self._update_help_text()

    def _update_help_text(self):
        self.help_label.setText(
            "Controls\n"
            "• Left drag: move/select\n"
            "• Mouse wheel: zoom\n"
            "• Middle drag: pan\n"
            f"• R: rotate +{self.rotation_step_deg:g}°\n"
            f"• Shift+R: rotate -{self.rotation_step_deg:g}°\n"
            "• Ctrl+D: duplicate\n"
            "• Delete: remove"
        )

    def rotate_selected(self, amount_deg: float):
        for item in self.scene.selected_track_items():
            item.rotate_step(amount_deg)
        self.scene.update()
        self.update_selection_info()

    def duplicate_selected(self):
        originals = self.scene.selected_track_items()
        if not originals:
            return

        self.scene.clearSelection()
        offset = world_to_scene(2.0, -2.0)

        snap_was_enabled = self.scene.endpoint_snap_enabled
        self.scene.endpoint_snap_enabled = False

        try:
            for original in originals:
                copy = original.duplicate()
                if copy is None:
                    continue

                copy.setPos(original.pos() + offset)
                copy.setRotation(original.rotation())
                copy.set_readable_identifier("")
                self._assign_readable_identifier_if_needed(copy)
                self.scene.addItem(copy)
                copy.setSelected(True)
        finally:
            self.scene.endpoint_snap_enabled = snap_was_enabled

        self.update_selection_info()

    def delete_selected(self):
        for item in list(self.scene.selectedItems()):
            self.scene.removeItem(item)
        self.update_selection_info()

    def set_endpoint_snap_enabled(self, enabled: bool):
        self.scene.endpoint_snap_enabled = enabled
        self.snap_status_label.setText(
            "Endpoint snap: ON" if enabled else "Endpoint snap: OFF"
        )

    # ------------------------------------------------------------
    # Property editor
    # ------------------------------------------------------------

    def _single_selected_item(self) -> TrackItem | None:
        selected = self.scene.selected_track_items()
        if len(selected) == 1:
            return selected[0]
        return None

    def _set_property_row_visible(self, field, visible: bool):
        label = self.properties_form.labelForField(field)
        if label is not None:
            label.setVisible(visible)
        field.setVisible(visible)

    def _block_property_signals(self, blocked: bool):
        for widget in (
            self.prop_x,
            self.prop_y,
            self.prop_rotation,
            self.prop_length,
            self.prop_width,
            self.prop_radius,
            self.prop_arm,
        ):
            widget.blockSignals(blocked)

    def _refresh_property_editor(self, item: TrackItem | None):
        self._property_refreshing = True
        self._block_property_signals(True)

        try:
            self.properties_group.setEnabled(item is not None)

            # Hide type-specific fields by default.
            self._set_property_row_visible(self.prop_length, False)
            self._set_property_row_visible(self.prop_width, False)
            self._set_property_row_visible(self.prop_radius, False)
            self._set_property_row_visible(self.prop_arm, False)

            if item is None:
                self.prop_effective.setText("")
                return

            x_m, y_m = scene_to_world(item.pos())
            self.prop_x.setValue(x_m)
            self.prop_y.setValue(y_m)
            self.prop_rotation.setValue(normalize_angle(item.rotation()))

            if isinstance(item, (StraightRoadItem, RoadEndItem)):
                self._set_property_row_visible(self.prop_length, True)
                self._set_property_row_visible(self.prop_width, True)
                self.prop_length.setValue(item.length_m)
                self.prop_width.setValue(item.width_m)

            elif isinstance(item, (Curve90RoadItem, Curve45RoadItem)):
                self._set_property_row_visible(self.prop_radius, True)
                self._set_property_row_visible(self.prop_width, True)
                self.prop_radius.setValue(item.radius_m)
                self.prop_width.setValue(item.width_m)

            elif isinstance(item, (TJunctionItem, CrossIntersectionItem)):
                self._set_property_row_visible(self.prop_arm, True)
                self._set_property_row_visible(self.prop_width, True)
                self.prop_arm.setValue(item.arm_length_m)
                self.prop_width.setValue(item.width_m)

            self.prop_effective.setText(self._effective_text(item))
        finally:
            self._block_property_signals(False)
            self._property_refreshing = False

    def _set_actor_row_visible(self, field, visible: bool):
        layout = self.actor_group.layout()
        label = layout.labelForField(field)
        if label is not None:
            label.setVisible(visible)
        field.setVisible(visible)

    def _refresh_camera_editor(self, item: TrackItem | None):
        supported = isinstance(item, QCar2StartItem)
        self.camera_group.setVisible(supported)
        if not supported:
            return

        self.prop_camera_view.blockSignals(True)
        try:
            idx = self.prop_camera_view.findData(item.camera_view)
            self.prop_camera_view.setCurrentIndex(max(0, idx))
        finally:
            self.prop_camera_view.blockSignals(False)

    def apply_camera_property(self):
        if self._property_refreshing:
            return
        item = self._single_selected_item()
        if not isinstance(item, QCar2StartItem):
            return

        item.camera_view = str(self.prop_camera_view.currentData())
        self.update_selection_info()

    def _refresh_actor_editor(self, item: TrackItem | None):
        supported = isinstance(item, SceneActorItem)
        self.actor_group.setVisible(supported)
        if not supported:
            return

        widgets = (
            self.prop_actor_z,
            self.prop_actor_scale,
            self.prop_actor_scale_project,
            self.prop_actor_configuration,
            self.prop_traffic_color,
            self.prop_building_length,
            self.prop_building_width,
            self.prop_building_height,
            self.prop_building_r,
            self.prop_building_g,
            self.prop_building_b,
        )
        for widget in widgets:
            widget.blockSignals(True)

        try:
            self._set_actor_row_visible(self.prop_actor_configuration, False)
            self._set_actor_row_visible(self.prop_traffic_color, False)
            self._set_actor_row_visible(self.prop_building_length, False)
            self._set_actor_row_visible(self.prop_building_width, False)
            self._set_actor_row_visible(self.prop_building_height, False)

            building_rgb_widget = self.prop_building_r.parentWidget()
            rgb_label = self.actor_group.layout().labelForField(building_rgb_widget)
            if rgb_label is not None:
                rgb_label.setVisible(False)
            building_rgb_widget.setVisible(False)

            self.prop_actor_z.setValue(item.z_m)
            self.prop_actor_scale.setValue(item.actor_scale)
            self.prop_actor_scale_project.setChecked(item.scale_with_project)

            if isinstance(item, (TrafficLightItem, CrosswalkItem)):
                self._set_actor_row_visible(self.prop_actor_configuration, True)
                idx = self.prop_actor_configuration.findData(item.configuration)
                self.prop_actor_configuration.setCurrentIndex(max(0, idx))

            if isinstance(item, TrafficLightItem):
                self._set_actor_row_visible(self.prop_traffic_color, True)
                idx = self.prop_traffic_color.findData(item.traffic_color)
                self.prop_traffic_color.setCurrentIndex(max(0, idx))

            if isinstance(item, BuildingBoxItem):
                self._set_actor_row_visible(self.prop_building_length, True)
                self._set_actor_row_visible(self.prop_building_width, True)
                self._set_actor_row_visible(self.prop_building_height, True)
                self.prop_building_length.setValue(item.length_m)
                self.prop_building_width.setValue(item.width_m)
                self.prop_building_height.setValue(item.height_m)

                self.prop_building_r.setText(str(int(item.rgb[0])))
                self.prop_building_g.setText(str(int(item.rgb[1])))
                self.prop_building_b.setText(str(int(item.rgb[2])))

                if rgb_label is not None:
                    rgb_label.setVisible(True)
                building_rgb_widget.setVisible(True)
        finally:
            for widget in widgets:
                widget.blockSignals(False)

    def apply_actor_properties(self, *args):
        item = self._single_selected_item()
        if not isinstance(item, SceneActorItem):
            return

        item.z_m = float(self.prop_actor_z.value())
        item.actor_scale = max(0.01, float(self.prop_actor_scale.value()))
        item.scale_with_project = self.prop_actor_scale_project.isChecked()

        if isinstance(item, (TrafficLightItem, CrosswalkItem)):
            item.configuration = int(
                self.prop_actor_configuration.currentData() or 0
            )

        if isinstance(item, TrafficLightItem):
            item.traffic_color = str(self.prop_traffic_color.currentData())

        if isinstance(item, BuildingBoxItem):
            item.prepareGeometryChange()
            item.length_m = max(0.1, float(self.prop_building_length.value()))
            item.width_m = max(0.1, float(self.prop_building_width.value()))
            item.height_m = max(0.1, float(self.prop_building_height.value()))
            item.rgb = (
                self._rgb_input_value(self.prop_building_r, item.rgb[0]),
                self._rgb_input_value(self.prop_building_g, item.rgb[1]),
                self._rgb_input_value(self.prop_building_b, item.rgb[2]),
            )

        item.update()
        self.scene.update()
        self.update_selection_info()

    def _set_experiment_row_visible(self, field, visible: bool):
        layout = self.experiment_group.layout()
        label = layout.labelForField(field)
        if label is not None:
            label.setVisible(visible)
        field.setVisible(visible)

    def _populate_gait_combo(self, item, current_gait: str):
        self.prop_movement_gait.blockSignals(True)
        try:
            self.prop_movement_gait.clear()

            if isinstance(item, PersonItem):
                choices = (
                    ("Standing", "standing"),
                    ("Walk", "walk"),
                    ("Jog", "jog"),
                    ("Run", "run"),
                )
            else:
                choices = (
                    ("Standing", "standing"),
                    ("Walk", "walk"),
                    ("Run", "run"),
                )

            for label, value in choices:
                self.prop_movement_gait.addItem(label, value)

            idx = self.prop_movement_gait.findData(current_gait)
            self.prop_movement_gait.setCurrentIndex(max(0, idx))
        finally:
            self.prop_movement_gait.blockSignals(False)

    def _trigger_candidates(self, action: str):
        items = self.scene.track_items()

        if action == TRIGGER_ACTION_TRAFFIC_LIGHT:
            return [
                item
                for item in items
                if isinstance(item, TrafficLightItem)
            ]

        return [
            item
            for item in items
            if isinstance(item, (PersonItem, AnimalItem, SecondaryQCarItem))
        ]

    def _populate_trigger_targets(
        self,
        trigger: TriggerZoneItem,
    ):
        action = trigger.action
        candidates = self._trigger_candidates(action)

        self.prop_trigger_target.blockSignals(True)
        try:
            self.prop_trigger_target.clear()
            self.prop_trigger_target.addItem("— Select target —", "")

            for candidate in candidates:
                readable = (
                    candidate.identifier
                    if getattr(candidate, "identifier", "")
                    else str(candidate.object_id)[:8]
                )
                label = f"{candidate.DISPLAY_NAME} [{readable}]"
                self.prop_trigger_target.addItem(
                    label,
                    str(candidate.object_id),
                )

            if (
                trigger.target_id
                and self.prop_trigger_target.findData(trigger.target_id) < 0
            ):
                self.prop_trigger_target.addItem(
                    f"Missing target [{trigger.target_id[:8]}]",
                    trigger.target_id,
                )

            idx = self.prop_trigger_target.findData(trigger.target_id)
            self.prop_trigger_target.setCurrentIndex(max(0, idx))
        finally:
            self.prop_trigger_target.blockSignals(False)

    def start_path_editing(self):
        item = self._single_selected_item()
        if not isinstance(item, ExperimentActorItem):
            return
        self.path_edit_actor_id = str(item.object_id)
        self.path_draw_button.setText("Click map... (right-click ends)")
        self.view.setCursor(Qt.CursorShape.CrossCursor)
        self.view.viewport().update()

    def finish_path_editing(self):
        self.path_edit_actor_id = None
        self.view.unsetCursor()
        if hasattr(self, "path_draw_button"):
            self.path_draw_button.setText("Draw / Add")
        self.view.viewport().update()

    def _path_edit_actor(self):
        if not self.path_edit_actor_id:
            return None
        for item in self.scene.track_items():
            if isinstance(item, ExperimentActorItem) and str(item.object_id) == str(self.path_edit_actor_id):
                return item
        return None

    def add_movement_waypoint(self, scene_pos: QPointF):
        item = self._path_edit_actor()
        if item is None:
            self.finish_path_editing()
            return
        x_m, y_m = scene_to_world(scene_pos)
        item.path_points_m.append([round(x_m, 3), round(y_m, 3)])
        item.move_on_activation = True
        self.path_summary_label.setText(f"{len(item.path_points_m)} waypoints")
        self.view.viewport().update()
        self.update_selection_info()

    def remove_last_waypoint(self):
        item = self._single_selected_item()
        if not isinstance(item, ExperimentActorItem) or not item.path_points_m:
            return
        item.path_points_m.pop()
        self.view.viewport().update()
        self.update_selection_info()

    def clear_movement_path(self):
        item = self._single_selected_item()
        if not isinstance(item, ExperimentActorItem):
            return
        item.path_points_m.clear()
        self.finish_path_editing()
        self.view.viewport().update()
        self.update_selection_info()

    def _refresh_experiment_editor(self, item: TrackItem | None):
        supported = isinstance(
            item,
            (ExperimentActorItem, TriggerZoneItem),
        )
        self.experiment_group.setVisible(supported)

        if not supported:
            return

        path_label = self.experiment_group.layout().labelForField(self.path_widget)
        is_actor = isinstance(item, ExperimentActorItem)
        self.path_widget.setVisible(is_actor)
        if path_label is not None:
            path_label.setVisible(is_actor)

        fields = (
            self.prop_experiment_spawn_mode,
            self.prop_person_configuration,
            self.prop_animal_type,
            self.prop_experiment_move,
            self.prop_destination_x,
            self.prop_destination_y,
            self.prop_movement_gait,
            self.prop_movement_mode,
            self.prop_despawn_on_finish,
            self.prop_secondary_qcar_speed,
            self.prop_trigger_radius,
            self.prop_trigger_action,
            self.prop_trigger_target,
            self.prop_trigger_traffic_color,
            self.prop_trigger_one_shot,
        )

        for field in fields:
            field.blockSignals(True)

        try:
            # Start hidden, then expose only the rows relevant to selection.
            for field in fields:
                self._set_experiment_row_visible(field, False)

            if isinstance(item, ExperimentActorItem):
                self._set_experiment_row_visible(
                    self.prop_experiment_spawn_mode,
                    True,
                )
                self._set_experiment_row_visible(
                    self.prop_experiment_move,
                    True,
                )
                self._set_experiment_row_visible(
                    self.prop_destination_x,
                    True,
                )
                self._set_experiment_row_visible(
                    self.prop_destination_y,
                    True,
                )
                self._set_experiment_row_visible(
                    self.prop_movement_gait,
                    True,
                )
                self._set_experiment_row_visible(self.prop_movement_mode, True)
                self._set_experiment_row_visible(self.prop_despawn_on_finish, True)

                idx = self.prop_experiment_spawn_mode.findData(
                    item.spawn_mode
                )
                self.prop_experiment_spawn_mode.setCurrentIndex(
                    max(0, idx)
                )

                self.prop_experiment_move.setChecked(
                    item.move_on_activation
                )
                self.prop_destination_x.setValue(
                    item.destination_x_m
                )
                self.prop_destination_y.setValue(
                    item.destination_y_m
                )

                if isinstance(item, PersonItem):
                    self._set_experiment_row_visible(
                        self.prop_person_configuration,
                        True,
                    )
                    idx = self.prop_person_configuration.findData(
                        item.person_configuration
                    )
                    self.prop_person_configuration.setCurrentIndex(
                        max(0, idx)
                    )

                if isinstance(item, AnimalItem):
                    self._set_experiment_row_visible(
                        self.prop_animal_type,
                        True,
                    )
                    idx = self.prop_animal_type.findData(item.animal_type)
                    self.prop_animal_type.setCurrentIndex(max(0, idx))

                if isinstance(item, SecondaryQCarItem):
                    self._set_experiment_row_visible(self.prop_movement_gait, False)
                    self._set_experiment_row_visible(self.prop_secondary_qcar_speed, True)
                    self.prop_secondary_qcar_speed.setValue(item.movement_speed_mps)
                else:
                    self._populate_gait_combo(item, item.movement_gait)

                idx = self.prop_movement_mode.findData(item.movement_mode)
                self.prop_movement_mode.setCurrentIndex(max(0, idx))
                self.prop_despawn_on_finish.setChecked(item.despawn_on_finish)
                self.prop_despawn_on_finish.setEnabled(item.movement_mode == MOVEMENT_ONCE)
                self.path_summary_label.setText(f"{len(item.path_points_m)} waypoints")

                movement_enabled = item.move_on_activation
                self.prop_destination_x.setEnabled(movement_enabled)
                self.prop_destination_y.setEnabled(movement_enabled)
                self.prop_movement_gait.setEnabled(movement_enabled)

            elif isinstance(item, TriggerZoneItem):
                self._set_experiment_row_visible(
                    self.prop_trigger_radius,
                    True,
                )
                self._set_experiment_row_visible(
                    self.prop_trigger_action,
                    True,
                )
                self._set_experiment_row_visible(
                    self.prop_trigger_target,
                    True,
                )
                self._set_experiment_row_visible(
                    self.prop_trigger_one_shot,
                    True,
                )

                self.prop_trigger_radius.setValue(item.radius_m)

                idx = self.prop_trigger_action.findData(item.action)
                self.prop_trigger_action.setCurrentIndex(max(0, idx))

                self._populate_trigger_targets(item)

                show_light = (
                    item.action == TRIGGER_ACTION_TRAFFIC_LIGHT
                )
                self._set_experiment_row_visible(
                    self.prop_trigger_traffic_color,
                    show_light,
                )

                idx = self.prop_trigger_traffic_color.findData(
                    item.traffic_color
                )
                self.prop_trigger_traffic_color.setCurrentIndex(
                    max(0, idx)
                )
                self.prop_trigger_one_shot.setChecked(item.one_shot)

        finally:
            for field in fields:
                field.blockSignals(False)

    def _trigger_action_changed(self, *args):
        if self._property_refreshing:
            return

        item = self._single_selected_item()
        if not isinstance(item, TriggerZoneItem):
            return

        item.action = str(self.prop_trigger_action.currentData())
        item.target_id = ""
        self._refresh_experiment_editor(item)
        self.update_selection_info()

    def apply_experiment_properties(self, *args):
        if self._property_refreshing:
            return

        item = self._single_selected_item()

        if isinstance(item, ExperimentActorItem):
            item.spawn_mode = str(
                self.prop_experiment_spawn_mode.currentData()
            )
            item.move_on_activation = (
                self.prop_experiment_move.isChecked()
            )
            item.destination_x_m = float(
                self.prop_destination_x.value()
            )
            item.destination_y_m = float(
                self.prop_destination_y.value()
            )
            gait = self.prop_movement_gait.currentData()
            if gait is not None and not isinstance(item, SecondaryQCarItem):
                item.movement_gait = str(gait)

            item.movement_mode = str(self.prop_movement_mode.currentData() or MOVEMENT_ONCE)
            item.despawn_on_finish = self.prop_despawn_on_finish.isChecked()
            self.prop_despawn_on_finish.setEnabled(item.movement_mode == MOVEMENT_ONCE)

            if isinstance(item, SecondaryQCarItem):
                item.movement_speed_mps = max(0.1, float(self.prop_secondary_qcar_speed.value()))

            if isinstance(item, PersonItem):
                item.person_configuration = int(
                    self.prop_person_configuration.currentData() or 0
                )

            if isinstance(item, AnimalItem):
                item.animal_type = str(
                    self.prop_animal_type.currentData() or "goat"
                )

            self.prop_destination_x.setEnabled(
                item.move_on_activation
            )
            self.prop_destination_y.setEnabled(
                item.move_on_activation
            )
            self.prop_movement_gait.setEnabled(
                item.move_on_activation
            )

            item.update()
            self.update_selection_info()
            return

        if isinstance(item, TriggerZoneItem):
            item.prepareGeometryChange()
            item.radius_m = max(
                0.1,
                float(self.prop_trigger_radius.value()),
            )
            item.action = str(
                self.prop_trigger_action.currentData()
            )
            item.target_id = str(
                self.prop_trigger_target.currentData() or ""
            )
            item.traffic_color = str(
                self.prop_trigger_traffic_color.currentData()
            )
            item.one_shot = self.prop_trigger_one_shot.isChecked()

            item.update()
            self.scene.update()
            self.update_selection_info()

    def _refresh_guide_editor(self, item: TrackItem | None):
        supported = item is not None and item.supports_guide_line()
        self.guide_group.setVisible(bool(supported))
        if not supported:
            return

        self._guide_refreshing = True
        widgets = (
            self.prop_guide_enabled,
            self.prop_guide_position,
            self.prop_guide_offset,
            self.prop_guide_color,
            self.prop_guide_r,
            self.prop_guide_g,
            self.prop_guide_b,
            self.prop_guide_width,
            self.prop_guide_style,
            self.prop_guide_scale_width,
        )
        for widget in widgets:
            widget.blockSignals(True)

        try:
            self.prop_guide_enabled.setChecked(item.guide_enabled)
            idx = self.prop_guide_position.findData(item.guide_position)
            self.prop_guide_position.setCurrentIndex(max(0, idx))
            self.prop_guide_offset.setValue(item.guide_custom_offset_m)
            self.prop_guide_offset.setEnabled(item.guide_position == "custom")
            idx = self.prop_guide_color.findData(item.guide_color_name)
            self.prop_guide_color.setCurrentIndex(max(0, idx))

            if item.guide_color_name == "custom":
                shown_rgb = item.guide_rgb
                rgb_enabled = True
            else:
                shown_rgb = GUIDE_COLOR_RGB.get(
                    item.guide_color_name,
                    DEFAULT_GUIDE_RGB,
                )
                rgb_enabled = False

            self.prop_guide_r.setText(str(int(shown_rgb[0])))
            self.prop_guide_g.setText(str(int(shown_rgb[1])))
            self.prop_guide_b.setText(str(int(shown_rgb[2])))
            self.prop_guide_r.setEnabled(rgb_enabled)
            self.prop_guide_g.setEnabled(rgb_enabled)
            self.prop_guide_b.setEnabled(rgb_enabled)

            self.prop_guide_width.setValue(item.guide_width_m)
            idx = self.prop_guide_style.findData(item.guide_style)
            self.prop_guide_style.setCurrentIndex(max(0, idx))
            self.prop_guide_scale_width.setChecked(item.guide_scale_width)
        finally:
            for widget in widgets:
                widget.blockSignals(False)
            self._guide_refreshing = False

    def apply_guide_properties(self, *args):
        if self._guide_refreshing:
            return
        item = self._single_selected_item()
        if item is None or not item.supports_guide_line():
            return

        item.guide_enabled = self.prop_guide_enabled.isChecked()
        item.guide_position = str(self.prop_guide_position.currentData())
        item.guide_custom_offset_m = float(self.prop_guide_offset.value())

        selected_color = str(self.prop_guide_color.currentData())
        color_combo_changed = self.sender() is self.prop_guide_color
        item.guide_color_name = selected_color

        if selected_color == "custom":
            # Restore the stored custom color when switching from a preset.
            if color_combo_changed:
                rgb = item.guide_rgb
                for widget, value in (
                    (self.prop_guide_r, rgb[0]),
                    (self.prop_guide_g, rgb[1]),
                    (self.prop_guide_b, rgb[2]),
                ):
                    widget.blockSignals(True)
                    widget.setText(str(int(value)))
                    widget.blockSignals(False)

            item.guide_rgb = (
                self._rgb_input_value(self.prop_guide_r, item.guide_rgb[0]),
                self._rgb_input_value(self.prop_guide_g, item.guide_rgb[1]),
                self._rgb_input_value(self.prop_guide_b, item.guide_rgb[2]),
            )
            rgb_enabled = True
        else:
            # Preset selected: show its actual RGB numbers while keeping
            # the previously entered custom RGB stored for later.
            preset_rgb = GUIDE_COLOR_RGB.get(
                selected_color,
                DEFAULT_GUIDE_RGB,
            )

            for widget, value in (
                (self.prop_guide_r, preset_rgb[0]),
                (self.prop_guide_g, preset_rgb[1]),
                (self.prop_guide_b, preset_rgb[2]),
            ):
                widget.blockSignals(True)
                widget.setText(str(int(value)))
                widget.blockSignals(False)

            rgb_enabled = False

        self.prop_guide_r.setEnabled(rgb_enabled)
        self.prop_guide_g.setEnabled(rgb_enabled)
        self.prop_guide_b.setEnabled(rgb_enabled)

        item.guide_width_m = max(0.01, float(self.prop_guide_width.value()))
        item.guide_style = str(self.prop_guide_style.currentData())
        item.guide_scale_width = self.prop_guide_scale_width.isChecked()
        self.prop_guide_offset.setEnabled(item.guide_position == "custom")
        item.update()
        self.scene.update()
        self.update_selection_info()

    def _effective_text(self, item: TrackItem | None) -> str:
        if item is None:
            return ""
        f = self.project_scale_factor
        x_m, y_m = scene_to_world(item.pos())
        lines = [
            f"Scale {self.project_scale_name}",
            f"X: {x_m * f:.3f} m",
            f"Y: {y_m * f:.3f} m",
        ]
        if hasattr(item, "width_m"):
            lines.append(f"Width: {float(item.width_m) * f:.3f} m")
        if hasattr(item, "length_m"):
            lines.append(f"Length: {float(item.length_m) * f:.3f} m")
        if hasattr(item, "radius_m"):
            lines.append(f"Radius: {float(item.radius_m) * f:.3f} m")
        if hasattr(item, "arm_length_m"):
            lines.append(f"Arm: {float(item.arm_length_m) * f:.3f} m")
        if isinstance(item, QCar2StartItem):
            lines.append(f"QCar actor scale: {f:.3f}")
            lines.append(f"QLabs yaw: {-normalize_angle(item.rotation()):.1f}°")
            lines.append(
                "Camera: First person"
                if item.camera_view == QCAR_CAMERA_FIRST_PERSON
                else "Camera: Third person"
            )
        if isinstance(item, TriggerZoneItem):
            lines.append(
                f"Trigger radius: {item.radius_m * f:.3f} m"
            )

        if isinstance(item, SceneActorItem):
            effective_actor_scale = (
                item.actor_scale * f
                if item.scale_with_project
                else item.actor_scale
            )
            if isinstance(item, CrosswalkItem):
                lines.append(
                    f"Crosswalk QLabs scale: {effective_actor_scale * CROSSWALK_QLABS_BASE_SCALE:.3f}"
                )
            else:
                lines.append(f"Actor scale: {effective_actor_scale:.3f}")
            lines.append(f"Base Z: {item.z_m * f:.3f} m")
            if isinstance(item, BuildingBoxItem):
                dimension_factor = f if item.scale_with_project else 1.0
                lines.append(
                    f"Box: {item.length_m * dimension_factor:.3f} × "
                    f"{item.width_m * dimension_factor:.3f} × "
                    f"{item.height_m * dimension_factor:.3f} m"
                )
        if item.supports_guide_line() and item.guide_enabled:
            lines.append(f"Guide offset: {item.resolved_guide_offset_m() * f:.3f} m")
            guide_width = item.guide_width_m * f if item.guide_scale_width else item.guide_width_m
            lines.append(f"Guide width: {guide_width:.3f} m")
        return "\n".join(lines)

    def _geometry_property_changed(self, item: TrackItem):
        item.update()
        self.scene.update()

        # If a resized endpoint remains near another endpoint, settle it again.
        if self.scene.endpoint_snap_enabled:
            snapped = self.scene.snap_item_position_to_endpoint(item, item.pos())
            if snapped != item.pos():
                item.setPos(snapped)

        self.update_selection_info()

    def apply_position_properties(self):
        if self._property_refreshing:
            return
        item = self._single_selected_item()
        if item is None:
            return
        item.setPos(world_to_scene(self.prop_x.value(), self.prop_y.value()))
        self.update_selection_info()

    def apply_rotation_property(self, value: float):
        if self._property_refreshing:
            return
        item = self._single_selected_item()
        if item is None:
            return

        item.setRotation(normalize_angle(value))
        if self.scene.endpoint_snap_enabled:
            snapped = self.scene.snap_item_position_to_endpoint(item, item.pos())
            if snapped != item.pos():
                item.setPos(snapped)
        self.scene.update()
        self.update_selection_info()

    def apply_length_property(self, value: float):
        if self._property_refreshing:
            return
        item = self._single_selected_item()
        if not isinstance(item, (StraightRoadItem, RoadEndItem)):
            return
        item.prepareGeometryChange()
        item.length_m = max(1.0, float(value))
        self._geometry_property_changed(item)

    def apply_width_property(self, value: float):
        if self._property_refreshing:
            return
        item = self._single_selected_item()
        if item is None or not hasattr(item, "width_m"):
            return

        item.prepareGeometryChange()
        item.width_m = max(1.0, float(value))

        # Curves require a positive inner radius.
        if isinstance(item, (Curve90RoadItem, Curve45RoadItem)):
            minimum_radius = item.width_m / 2.0 + 0.5
            if item.radius_m < minimum_radius:
                item.radius_m = minimum_radius

        self._geometry_property_changed(item)

    def apply_radius_property(self, value: float):
        if self._property_refreshing:
            return
        item = self._single_selected_item()
        if not isinstance(item, (Curve90RoadItem, Curve45RoadItem)):
            return

        item.prepareGeometryChange()
        minimum_radius = item.width_m / 2.0 + 0.5
        item.radius_m = max(minimum_radius, float(value))
        self._geometry_property_changed(item)

    def apply_arm_property(self, value: float):
        if self._property_refreshing:
            return
        item = self._single_selected_item()
        if not isinstance(item, (TJunctionItem, CrossIntersectionItem)):
            return

        item.prepareGeometryChange()
        item.arm_length_m = max(item.width_m, float(value))
        self._geometry_property_changed(item)

    # ------------------------------------------------------------
    # Status
    # ------------------------------------------------------------

    def update_selection_info(self):
        selected = self.scene.selected_track_items()

        if len(selected) == 1:
            self.selection_label.setText(selected[0].selection_text())
            self._refresh_property_editor(selected[0])
            self._refresh_camera_editor(selected[0])
            self._refresh_actor_editor(selected[0])
            self._refresh_experiment_editor(selected[0])
            self._refresh_guide_editor(selected[0])
        elif len(selected) > 1:
            self.selection_label.setText(f"{len(selected)} objects selected")
            self._refresh_property_editor(None)
            self._refresh_camera_editor(None)
            self._refresh_actor_editor(None)
            self._refresh_experiment_editor(None)
            self._refresh_guide_editor(None)
        else:
            self.selection_label.setText("None")
            self._refresh_property_editor(None)
            self._refresh_camera_editor(None)
            self._refresh_actor_editor(None)
            self._refresh_experiment_editor(None)
            self._refresh_guide_editor(None)

    def update_cursor_label(self, x_m: float, y_m: float):
        self.cursor_label.setText(f"Cursor: X {x_m:.1f} m | Y {y_m:.1f} m")

    def update_zoom_label(self):
        zoom_percent = self.view.transform().m11() * 100.0
        self.zoom_label.setText(f"Zoom: {zoom_percent:.0f}%")

    # ------------------------------------------------------------
    # QLabs export
    # ------------------------------------------------------------

    def export_qlabs_setup(self):
        qcar_starts = [
            item
            for item in self.scene.track_items()
            if isinstance(item, QCar2StartItem)
        ]

        if not qcar_starts:
            result = QMessageBox.question(
                self,
                "No QCar2 Start",
                "No QCar2 Start marker is present. Export the road network "
                "without spawning a QCar2?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.Yes,
            )
            if result != QMessageBox.StandardButton.Yes:
                return

        if self.current_file is not None:
            default_name = f"{self.current_file.stem}_qlabs_setup.py"
            default_path = str(self.current_file.with_name(default_name))
        else:
            default_path = "qlabs_track_setup.py"

        file_name, _ = QFileDialog.getSaveFileName(
            self,
            "Export QLabs Setup",
            default_path,
            "Python Files (*.py)",
        )
        if not file_name:
            return

        path = Path(file_name)
        if path.suffix.lower() != ".py":
            path = path.with_suffix(".py")

        source = build_qlabs_setup_source(self.track_data())

        try:
            compile(source, str(path), "exec")
            path.write_text(source, encoding="utf-8")
        except (OSError, SyntaxError) as exc:
            QMessageBox.critical(self, "Export Failed", str(exc))
            return

        workspace_label = (
            "Open Road"
            if self.workspace_mode == WORKSPACE_OPEN_ROAD
            else "Plane / selected custom workspace"
        )

        QMessageBox.information(
            self,
            "QLabs Export Complete",
            "QLabs setup script created:\n"
            f"{path}\n\n"
            f"Open QLabs in the {workspace_label} workspace, then run the exported Python file.\n\n"
            "v1.0.1 keeps navmesh-free manual waypoint playback for people/animals, the same "
            "interpolation logic used by environment QCars, readable actor aliases, clear junction "
            "centers, movement loops/despawn, triggers, and outdoor weather/time settings. "
            "The Open Road reference overlay is editor-only and is not exported. The exported "
            "setup stays running while movement or trigger monitoring is required.",
        )

    # ------------------------------------------------------------
    # Save / load
    # ------------------------------------------------------------

    def track_data(self) -> dict:
        objects = [item.to_dict() for item in self.scene.track_items()]

        return {
            "format": "qlabs_track_editor",
            "version": self.VERSION,
            "units": "meters",
            "project": {
                "scale_name": self.project_scale_name,
                "scale_factor": self.project_scale_factor,
            },
            "environment": {
                "enabled": self.environment_enabled,
                "weather": self.environment_weather,
                "time_of_day": self.environment_time_of_day,
            },
            "workspace": {
                "mode": self.workspace_mode,
                "show_road_reference": self.workspace_show_road_reference,
                "show_navigation_regions": self.workspace_show_navigation_regions,
                "show_reference_points": self.workspace_show_reference_points,
                "show_reference_labels": self.workspace_show_reference_labels,
            },
            "objects": objects,
        }

    def new_track(self):
        self.scene.clear()
        self.project_scale_combo.setCurrentIndex(0)
        self._set_environment_from_data({})
        self._set_workspace_from_data({})
        self.finish_path_editing()
        self.current_file = None
        self.setWindowTitle(f"QLabs Track Editor v{self.VERSION}")
        self.update_selection_info()

    def save_track(self, save_as: bool = False):
        path = self.current_file

        if path is None or save_as:
            file_name, _ = QFileDialog.getSaveFileName(
                self,
                "Save Track",
                "track.json",
                "JSON Track Files (*.json)",
            )
            if not file_name:
                return
            path = Path(file_name)
            if path.suffix.lower() != ".json":
                path = path.with_suffix(".json")

        try:
            with path.open("w", encoding="utf-8") as f:
                json.dump(self.track_data(), f, indent=2)
        except OSError as exc:
            QMessageBox.critical(self, "Save Failed", str(exc))
            return

        self.current_file = path
        self.setWindowTitle(f"QLabs Track Editor v{self.VERSION} — {path.name}")

    def load_track(self):
        file_name, _ = QFileDialog.getOpenFileName(
            self,
            "Open Track",
            "",
            "JSON Track Files (*.json)",
        )
        if not file_name:
            return

        path = Path(file_name)

        try:
            with path.open("r", encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, json.JSONDecodeError) as exc:
            QMessageBox.critical(self, "Open Failed", str(exc))
            return

        if data.get("format") != "qlabs_track_editor":
            QMessageBox.warning(
                self,
                "Unsupported File",
                "Not a QLabs Track Editor file.",
            )
            return

        self._set_project_scale_from_data(data.get("project", {}))
        self._set_environment_from_data(data.get("environment", {}))
        self._set_workspace_from_data(data.get("workspace", {}))
        self.finish_path_editing()
        self.scene.clear()

        snap_was_enabled = self.scene.endpoint_snap_enabled
        self.scene.endpoint_snap_enabled = False
        unsupported_types = set()

        try:
            for obj in data.get("objects", []):
                item = create_track_item_from_dict(obj)
                if item is not None:
                    self.scene.addItem(item)
                else:
                    unsupported_types.add(str(obj.get("type", "unknown")))
        finally:
            self.scene.endpoint_snap_enabled = snap_was_enabled

        self._ensure_all_readable_identifiers()

        if unsupported_types:
            QMessageBox.information(
                self,
                "Some Objects Skipped",
                "Unsupported component types were skipped:\n"
                + "\n".join(sorted(unsupported_types)),
            )

        self.current_file = path
        self.setWindowTitle(f"QLabs Track Editor v{self.VERSION} — {path.name}")

        if self.workspace_mode == WORKSPACE_OPEN_ROAD:
            self.fit_open_road_reference()
        else:
            self.view.centerOn(0, 0)

        self.update_selection_info()


# ================================================================
# Application
# ================================================================

def main():
    app = QApplication(sys.argv)
    app.setApplicationName("QLabs Track Editor")

    window = TrackEditorWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
