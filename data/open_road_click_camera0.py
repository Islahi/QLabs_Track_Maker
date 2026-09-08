"""
Open Road Click-to-Camera Utility
=================================

Standalone PySide6 utility for Quanser QLabs Open Road.

What it does
------------
1. Loads the measured Open Road trajectory from open_road_reference.json.
2. Draws the first completed Open Road lap.
3. Connects to QLabs.
4. When you left-click the map, a QLabsFreeCamera is moved above that X/Y
   using the measured Open Road Z at that location, and the camera is possessed.

Controls
--------
- Left click: move QLabs camera to clicked map position.
- Mouse wheel: zoom.
- Middle/right drag: pan.
- Reset View: fit the whole recorded Open Road loop.

Expected files
--------------
Place this script either:
- beside open_road_reference.json, or
- in the Track Maker project root where data/open_road_reference.json exists.

Requirements
------------
- PySide6
- Quanser qvl Python package
- QLabs running with the Open Road workspace loaded
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

from PySide6.QtCore import QPointF, Qt, Signal
from PySide6.QtGui import QColor, QMouseEvent, QPainter, QPainterPath, QPen, QWheelEvent
from PySide6.QtWidgets import (
    QApplication,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)


# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------

DEFAULT_HOST = "localhost"
DEFAULT_CAMERA_ACTOR = 990

# Camera is placed this many metres above the measured Open Road elevation.
DEFAULT_CAMERA_HEIGHT_M = 80.0

# QLabs free-camera rotation uses [roll, pitch, yaw] in degrees.
# +90 pitch is intended as a top-down view. If your QLabs installation shows
# the camera looking upward, change this to -90 in the GUI.
DEFAULT_PITCH_DEG = 90.0
DEFAULT_YAW_DEG = 0.0
DEFAULT_FOV_DEG = 70

# The logger started while the QCar was still settling laterally.  Use the same
# stable seam strategy as the Track Maker Open Road renderer.
LOOP_SEAM_LEAD_IN_M = 200.0
LOOP_MIN_DISTANCE_M = 10_000.0
LOOP_RETURN_RADIUS_M = 25.0

# Logged QCar was in the middle lane of the upper three-lane carriageway.
LANE_WIDTH_M = 4.0
MEDIAN_WIDTH_M = 0.25
LOGGED_LANE_OFFSET_FROM_MEDIAN_M = MEDIAN_WIDTH_M / 2.0 + 1.5 * LANE_WIDTH_M
TOTAL_APPROX_ROAD_WIDTH_M = 6.0 * LANE_WIDTH_M + MEDIAN_WIDTH_M


# ---------------------------------------------------------------------------
# Reference loading and geometry
# ---------------------------------------------------------------------------

def find_reference_file(explicit: Path | None) -> Path:
    if explicit is not None:
        explicit = explicit.expanduser().resolve()
        if explicit.is_file():
            return explicit
        raise FileNotFoundError(f"Reference file not found: {explicit}")

    script_dir = Path(__file__).resolve().parent
    candidates = [
        script_dir / "open_road_reference.json",
        script_dir / "data" / "open_road_reference.json",
        Path.cwd() / "open_road_reference.json",
        Path.cwd() / "data" / "open_road_reference.json",
    ]

    for candidate in candidates:
        if candidate.is_file():
            return candidate.resolve()

    raise FileNotFoundError(
        "Could not find open_road_reference.json. Put it beside this script, "
        "inside data/, or pass --reference PATH."
    )


def load_measured_points(path: Path) -> tuple[dict, list[list[float]]]:
    with path.open("r", encoding="utf-8") as handle:
        document = json.load(handle)

    if document.get("workspace") != "Open Road":
        raise ValueError("The JSON file is not an Open Road reference.")

    road = document.get("road_reference", {})
    raw = road.get("points", [])
    points: list[list[float]] = []

    for point in raw:
        if len(point) < 3:
            continue
        x, y, z = map(float, point[:3])
        if math.isfinite(x) and math.isfinite(y) and math.isfinite(z):
            points.append([x, y, z])

    if len(points) < 2:
        raise ValueError("The reference contains fewer than two valid XYZ points.")

    return document, points


def cumulative_distances(points: list[list[float]]) -> list[float]:
    result = [0.0]
    for index in range(1, len(points)):
        ax, ay = points[index - 1][:2]
        bx, by = points[index][:2]
        result.append(result[-1] + math.hypot(bx - ax, by - ay))
    return result


def extract_stable_completed_loop(points: list[list[float]]) -> tuple[list[list[float]], dict]:
    """Find the first completed lap, placing the visual seam after 200 m."""
    if len(points) < 2:
        return points, {"closed": False}

    cumulative = cumulative_distances(points)

    seam_index = 0
    for index, distance_m in enumerate(cumulative):
        if distance_m >= LOOP_SEAM_LEAD_IN_M:
            seam_index = index
            break

    sx, sy = points[seam_index][:2]
    entered_return_zone = False
    best_return: tuple[float, int, float] | None = None

    for index in range(seam_index + 1, len(points)):
        travelled = cumulative[index] - cumulative[seam_index]
        if travelled < LOOP_MIN_DISTANCE_M:
            continue

        x, y = points[index][:2]
        distance_to_start = math.hypot(x - sx, y - sy)

        if distance_to_start <= LOOP_RETURN_RADIUS_M:
            entered_return_zone = True
            if best_return is None or distance_to_start < best_return[0]:
                best_return = (distance_to_start, index, travelled)
            continue

        if entered_return_zone:
            break

    if best_return is None:
        return points[seam_index:], {
            "closed": False,
            "start_index": seam_index,
            "end_index": None,
            "distance_m": cumulative[-1] - cumulative[seam_index],
            "return_distance_m": None,
        }

    return_distance, end_index, travelled = best_return
    loop = [list(p) for p in points[seam_index : end_index + 1]]

    # Display-only closure: keep measured Z, but snap final XY to first XY.
    if len(loop) >= 2:
        loop[-1][0] = loop[0][0]
        loop[-1][1] = loop[0][1]

    return loop, {
        "closed": True,
        "start_index": seam_index,
        "end_index": end_index,
        "distance_m": travelled,
        "return_distance_m": return_distance,
    }


def point_segment_distance_sq(px: float, py: float, a, b) -> tuple[float, float]:
    ax, ay = float(a[0]), float(a[1])
    bx, by = float(b[0]), float(b[1])
    dx = bx - ax
    dy = by - ay
    denominator = dx * dx + dy * dy

    if denominator <= 1e-12:
        return (px - ax) ** 2 + (py - ay) ** 2, 0.0

    t = ((px - ax) * dx + (py - ay) * dy) / denominator
    t = max(0.0, min(1.0, t))
    qx = ax + t * dx
    qy = ay + t * dy
    return (px - qx) ** 2 + (py - qy) ** 2, t


def measured_surface_z(
    x: float,
    y: float,
    points: list[list[float]],
) -> tuple[float, float, float, float]:
    """Return interpolated Z and nearest measured XY point."""
    best_distance_sq = float("inf")
    best_z = float(points[0][2])
    best_x = float(points[0][0])
    best_y = float(points[0][1])

    for index in range(len(points) - 1):
        a = points[index]
        b = points[index + 1]
        distance_sq, t = point_segment_distance_sq(x, y, a, b)

        if distance_sq >= best_distance_sq:
            continue

        ax, ay, az = map(float, a[:3])
        bx, by, bz = map(float, b[:3])
        best_distance_sq = distance_sq
        best_x = ax + t * (bx - ax)
        best_y = ay + t * (by - ay)
        best_z = az + t * (bz - az)

    return best_z, best_x, best_y, math.sqrt(best_distance_sq)


def rdp_simplify(points: list[list[float]], tolerance_m: float = 3.0) -> list[list[float]]:
    """Iterative Ramer-Douglas-Peucker simplification using XY only."""
    if len(points) <= 2:
        return list(points)

    tolerance_sq = tolerance_m * tolerance_m
    keep = [False] * len(points)
    keep[0] = True
    keep[-1] = True
    stack = [(0, len(points) - 1)]

    while stack:
        start_index, end_index = stack.pop()
        if end_index <= start_index + 1:
            continue

        a = points[start_index]
        b = points[end_index]
        best_index = None
        best_distance_sq = -1.0

        for index in range(start_index + 1, end_index):
            p = points[index]
            distance_sq, _ = point_segment_distance_sq(
                float(p[0]), float(p[1]), a, b
            )
            if distance_sq > best_distance_sq:
                best_distance_sq = distance_sq
                best_index = index

        if best_index is not None and best_distance_sq > tolerance_sq:
            keep[best_index] = True
            stack.append((start_index, best_index))
            stack.append((best_index, end_index))

    return [point for index, point in enumerate(points) if keep[index]]


def offset_polyline_xy(
    points: list[list[float]],
    offset_m: float,
    closed: bool = True,
) -> list[tuple[float, float]]:
    clean = [(float(p[0]), float(p[1])) for p in points if len(p) >= 2]

    if (
        closed
        and len(clean) >= 3
        and math.hypot(clean[-1][0] - clean[0][0], clean[-1][1] - clean[0][1]) < 1e-6
    ):
        clean = clean[:-1]

    if len(clean) < 2:
        return clean

    result: list[tuple[float, float]] = []
    count = len(clean)

    for index, (x, y) in enumerate(clean):
        if closed:
            px, py = clean[(index - 1) % count]
            nx, ny = clean[(index + 1) % count]
        elif index == 0:
            px, py = clean[index]
            nx, ny = clean[index + 1]
        elif index == count - 1:
            px, py = clean[index - 1]
            nx, ny = clean[index]
        else:
            px, py = clean[index - 1]
            nx, ny = clean[index + 1]

        tx = nx - px
        ty = ny - py
        length = math.hypot(tx, ty)

        if length <= 1e-9:
            result.append((x, y))
            continue

        # Left-hand normal relative to recorded QCar travel direction.
        normal_x = -ty / length
        normal_y = tx / length
        result.append((x + normal_x * offset_m, y + normal_y * offset_m))

    return result


# ---------------------------------------------------------------------------
# QLabs free-camera controller
# ---------------------------------------------------------------------------

class QLabsCameraController:
    def __init__(self) -> None:
        self.qlabs = None
        self.camera = None
        self.host = None
        self.actor_number = None

    @property
    def connected(self) -> bool:
        return self.qlabs is not None and self.camera is not None

    def close(self) -> None:
        if self.qlabs is not None:
            try:
                self.qlabs.close()
            except Exception:
                pass
        self.qlabs = None
        self.camera = None

    def connect(
        self,
        host: str,
        actor_number: int,
        initial_location: list[float],
        initial_rotation_deg: list[float],
        fov_deg: int,
    ) -> None:
        self.close()

        # Import lazily so the map can still open and show a useful error if
        # the script is launched outside the Quanser Python environment.
        from qvl.qlabs import QuanserInteractiveLabs
        from qvl.free_camera import QLabsFreeCamera

        qlabs = QuanserInteractiveLabs()
        if not qlabs.open(host):
            raise ConnectionError(f"Could not connect to QLabs at {host!r}.")

        camera = QLabsFreeCamera(qlabs, verbose=True)
        camera.actorNumber = int(actor_number)

        if not camera.ping():
            status = camera.spawn_id_degrees(
                actorNumber=int(actor_number),
                location=initial_location,
                rotation=initial_rotation_deg,
                waitForConfirmation=True,
            )
            if status != 0:
                qlabs.close()
                raise RuntimeError(
                    f"Could not spawn free camera actor {actor_number}; "
                    f"QLabs returned status {status}."
                )

        camera.set_camera_properties(
            int(fov_deg),
            False,   # depthOfField
            8.0,     # aperture ignored when DOF is off
            10.0,    # focus distance ignored when DOF is off
        )

        if not camera.possess():
            qlabs.close()
            raise RuntimeError("Free camera exists, but QLabs could not possess it.")

        self.qlabs = qlabs
        self.camera = camera
        self.host = host
        self.actor_number = int(actor_number)

    def move_to(
        self,
        x: float,
        y: float,
        surface_z: float,
        height_m: float,
        pitch_deg: float,
        yaw_deg: float,
        fov_deg: int,
    ) -> list[float]:
        if not self.connected:
            raise RuntimeError("Not connected to QLabs.")

        location = [
            float(x),
            float(y),
            float(surface_z) + float(height_m),
        ]
        rotation = [0.0, float(pitch_deg), float(yaw_deg)]

        self.camera.set_camera_properties(
            int(fov_deg),
            False,
            8.0,
            10.0,
        )

        if not self.camera.set_transform_degrees(location, rotation):
            raise RuntimeError("QLabs rejected the camera transform.")

        # Re-possess in case the user changed the current camera in QLabs.
        self.camera.possess()
        return location


# ---------------------------------------------------------------------------
# Interactive map widget
# ---------------------------------------------------------------------------

class OpenRoadMap(QWidget):
    pointClicked = Signal(float, float, float, float)

    def __init__(self, raw_loop_points: list[list[float]], parent=None) -> None:
        super().__init__(parent)
        self.setMinimumSize(900, 520)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        self.raw_loop_points = raw_loop_points
        self.display_points = rdp_simplify(raw_loop_points, tolerance_m=3.0)

        # Reconstruct approximate road median from the measured middle-lane path.
        self.median_points = offset_polyline_xy(
            self.display_points,
            LOGGED_LANE_OFFSET_FROM_MEDIAN_M,
            closed=True,
        )

        xs = [float(p[0]) for p in raw_loop_points]
        ys = [float(p[1]) for p in raw_loop_points]
        self.data_min_x = min(xs)
        self.data_max_x = max(xs)
        self.data_min_y = min(ys)
        self.data_max_y = max(ys)

        self.data_center_x = (self.data_min_x + self.data_max_x) / 2.0
        self.data_center_y = (self.data_min_y + self.data_max_y) / 2.0

        self.center_x = self.data_center_x
        self.center_y = self.data_center_y
        self.zoom = 1.0

        self.selected: tuple[float, float, float, float] | None = None
        self.hover_world: tuple[float, float] | None = None

        self._pan_active = False
        self._pan_last = QPointF()

    def reset_view(self) -> None:
        self.center_x = self.data_center_x
        self.center_y = self.data_center_y
        self.zoom = 1.0
        self.update()

    def fit_scale(self) -> float:
        margin = 34.0
        width = max(1.0, self.width() - 2.0 * margin)
        height = max(1.0, self.height() - 2.0 * margin)
        span_x = max(1.0, self.data_max_x - self.data_min_x)
        span_y = max(1.0, self.data_max_y - self.data_min_y)
        return min(width / span_x, height / span_y)

    def pixels_per_metre(self) -> float:
        return self.fit_scale() * self.zoom

    def world_to_screen(self, x: float, y: float) -> QPointF:
        scale = self.pixels_per_metre()
        return QPointF(
            self.width() / 2.0 + (x - self.center_x) * scale,
            self.height() / 2.0 - (y - self.center_y) * scale,
        )

    def screen_to_world(self, pos: QPointF) -> tuple[float, float]:
        scale = max(self.pixels_per_metre(), 1e-12)
        return (
            self.center_x + (pos.x() - self.width() / 2.0) / scale,
            self.center_y - (pos.y() - self.height() / 2.0) / scale,
        )

    def make_path(self, points) -> QPainterPath:
        path = QPainterPath()
        if not points:
            return path

        p0 = self.world_to_screen(float(points[0][0]), float(points[0][1]))
        path.moveTo(p0)

        for point in points[1:]:
            p = self.world_to_screen(float(point[0]), float(point[1]))
            path.lineTo(p)

        return path

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.fillRect(self.rect(), QColor(32, 36, 42))

        scale = self.pixels_per_metre()

        # Approximate six-lane road band.  At whole-map zoom it is clamped to a
        # few pixels so the route remains visible; at closer zoom it approaches
        # the actual 24.25 m visual width.
        road_width_px = max(3.0, min(80.0, TOTAL_APPROX_ROAD_WIDTH_M * scale))
        road_pen = QPen(QColor(91, 96, 104), road_width_px)
        road_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        road_pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(road_pen)
        painter.drawPath(self.make_path(self.median_points))

        # Median/barrier center.
        median_width_px = max(1.0, min(12.0, MEDIAN_WIDTH_M * scale))
        median_pen = QPen(QColor(184, 170, 122), median_width_px)
        median_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(median_pen)
        painter.drawPath(self.make_path(self.median_points))

        # Actual measured QCar trajectory.
        trajectory_pen = QPen(QColor(255, 205, 70), 2.0)
        trajectory_pen.setCosmetic(True)
        painter.setPen(trajectory_pen)
        painter.drawPath(self.make_path(self.display_points))

        # World origin.
        origin = self.world_to_screen(0.0, 0.0)
        axis_pen = QPen(QColor(95, 155, 205, 140), 1.0)
        axis_pen.setCosmetic(True)
        painter.setPen(axis_pen)
        painter.drawLine(QPointF(origin.x(), 0), QPointF(origin.x(), self.height()))
        painter.drawLine(QPointF(0, origin.y()), QPointF(self.width(), origin.y()))

        # Selected click.
        if self.selected is not None:
            x, y, z, distance_to_trace = self.selected
            p = self.world_to_screen(x, y)

            selected_pen = QPen(QColor(80, 220, 145), 2.0)
            selected_pen.setCosmetic(True)
            painter.setPen(selected_pen)
            painter.setBrush(QColor(80, 220, 145, 80))
            painter.drawEllipse(p, 7.0, 7.0)

            painter.setPen(QColor(235, 240, 245))
            label = (
                f"  X {x:.2f}  Y {y:.2f}  road Z {z:.2f} m"
                f"  | nearest trace {distance_to_trace:.1f} m"
            )
            painter.drawText(p + QPointF(9.0, -9.0), label)

        # Hover coordinate readout.
        painter.setPen(QColor(225, 230, 235))
        if self.hover_world is not None:
            hx, hy = self.hover_world
            painter.drawText(12, 22, f"Cursor: X {hx:.1f} m   Y {hy:.1f} m")

        painter.setPen(QColor(185, 193, 202))
        painter.drawText(
            12,
            self.height() - 12,
            "Left click: move QLabs camera   |   Wheel: zoom   |   Middle/right drag: pan",
        )

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        pos = event.position()
        self.hover_world = self.screen_to_world(pos)

        if self._pan_active:
            delta = pos - self._pan_last
            scale = max(self.pixels_per_metre(), 1e-12)
            self.center_x -= delta.x() / scale
            self.center_y += delta.y() / scale
            self._pan_last = pos

        self.update()

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() in (Qt.MouseButton.MiddleButton, Qt.MouseButton.RightButton):
            self._pan_active = True
            self._pan_last = event.position()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            return

        if event.button() == Qt.MouseButton.LeftButton:
            x, y = self.screen_to_world(event.position())
            z, nearest_x, nearest_y, distance_to_trace = measured_surface_z(
                x, y, self.raw_loop_points
            )
            self.selected = (x, y, z, distance_to_trace)
            self.pointClicked.emit(x, y, z, distance_to_trace)
            self.update()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() in (Qt.MouseButton.MiddleButton, Qt.MouseButton.RightButton):
            self._pan_active = False
            self.unsetCursor()

    def wheelEvent(self, event: QWheelEvent) -> None:
        mouse_pos = event.position()
        before_x, before_y = self.screen_to_world(mouse_pos)

        steps = event.angleDelta().y() / 120.0
        factor = 1.25 ** steps
        self.zoom = max(0.35, min(300.0, self.zoom * factor))

        after_x, after_y = self.screen_to_world(mouse_pos)
        self.center_x += before_x - after_x
        self.center_y += before_y - after_y
        self.update()


# ---------------------------------------------------------------------------
# Main window
# ---------------------------------------------------------------------------

class MainWindow(QMainWindow):
    def __init__(
        self,
        reference_path: Path,
        document: dict,
        raw_points: list[list[float]],
        loop_points: list[list[float]],
        loop_info: dict,
    ) -> None:
        super().__init__()
        self.setWindowTitle("QLabs Open Road Click-to-Camera")
        self.resize(1280, 760)

        self.reference_path = reference_path
        self.document = document
        self.raw_points = raw_points
        self.loop_points = loop_points
        self.loop_info = loop_info
        self.controller = QLabsCameraController()

        root = QWidget()
        self.setCentralWidget(root)
        outer = QVBoxLayout(root)

        controls = QHBoxLayout()
        outer.addLayout(controls)

        connection_form = QFormLayout()
        controls.addLayout(connection_form)

        self.host_edit = QLineEdit(DEFAULT_HOST)
        connection_form.addRow("QLabs host", self.host_edit)

        self.camera_actor_spin = QSpinBox()
        self.camera_actor_spin.setRange(0, 2_000_000_000)
        self.camera_actor_spin.setValue(DEFAULT_CAMERA_ACTOR)
        connection_form.addRow("Free camera actor", self.camera_actor_spin)

        camera_form = QFormLayout()
        controls.addLayout(camera_form)

        self.height_spin = QDoubleSpinBox()
        self.height_spin.setRange(1.0, 2000.0)
        self.height_spin.setDecimals(1)
        self.height_spin.setValue(DEFAULT_CAMERA_HEIGHT_M)
        self.height_spin.setSuffix(" m")
        camera_form.addRow("Height above road", self.height_spin)

        self.pitch_spin = QDoubleSpinBox()
        self.pitch_spin.setRange(-180.0, 180.0)
        self.pitch_spin.setDecimals(1)
        self.pitch_spin.setValue(DEFAULT_PITCH_DEG)
        self.pitch_spin.setSuffix("°")
        camera_form.addRow("Pitch", self.pitch_spin)

        self.yaw_spin = QDoubleSpinBox()
        self.yaw_spin.setRange(-180.0, 180.0)
        self.yaw_spin.setDecimals(1)
        self.yaw_spin.setValue(DEFAULT_YAW_DEG)
        self.yaw_spin.setSuffix("°")
        camera_form.addRow("Yaw", self.yaw_spin)

        self.fov_spin = QSpinBox()
        self.fov_spin.setRange(5, 150)
        self.fov_spin.setValue(DEFAULT_FOV_DEG)
        self.fov_spin.setSuffix("°")
        camera_form.addRow("Field of view", self.fov_spin)

        buttons = QVBoxLayout()
        controls.addLayout(buttons)

        self.connect_button = QPushButton("Connect / Reconnect QLabs")
        self.connect_button.clicked.connect(self.connect_qlabs)
        buttons.addWidget(self.connect_button)

        self.reset_button = QPushButton("Reset Map View")
        buttons.addWidget(self.reset_button)

        buttons.addStretch(1)

        self.status_label = QLabel("Not connected to QLabs.")
        self.status_label.setWordWrap(True)
        controls.addWidget(self.status_label, 1)

        self.map_widget = OpenRoadMap(loop_points)
        self.map_widget.pointClicked.connect(self.on_map_clicked)
        self.reset_button.clicked.connect(self.map_widget.reset_view)
        outer.addWidget(self.map_widget, 1)

        loop_km = float(loop_info.get("distance_m", 0.0)) / 1000.0
        return_error = loop_info.get("return_distance_m")
        if return_error is None:
            return_text = "not detected"
        else:
            return_text = f"{float(return_error):.2f} m"

        self.info_label = QLabel(
            f"Reference: {reference_path}  |  "
            f"raw points: {len(raw_points):,}  |  "
            f"displayed lap: {loop_km:.2f} km  |  "
            f"loop closure: {return_text}"
        )
        self.info_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        outer.addWidget(self.info_label)

    def connect_qlabs(self) -> None:
        try:
            # Initial camera position uses the first point on the measured loop.
            x, y, z = map(float, self.loop_points[0][:3])
            self.controller.connect(
                host=self.host_edit.text().strip() or DEFAULT_HOST,
                actor_number=self.camera_actor_spin.value(),
                initial_location=[x, y, z + self.height_spin.value()],
                initial_rotation_deg=[
                    0.0,
                    self.pitch_spin.value(),
                    self.yaw_spin.value(),
                ],
                fov_deg=self.fov_spin.value(),
            )
            self.status_label.setText(
                f"Connected to QLabs. Free camera actor "
                f"{self.camera_actor_spin.value()} is possessed. Click the map."
            )
        except Exception as exc:
            self.status_label.setText(f"QLabs connection failed: {exc}")
            QMessageBox.critical(self, "QLabs connection failed", str(exc))

    def on_map_clicked(
        self,
        x: float,
        y: float,
        surface_z: float,
        distance_to_trace: float,
    ) -> None:
        if not self.controller.connected:
            self.status_label.setText(
                f"Selected X={x:.2f}, Y={y:.2f}, road Z≈{surface_z:.2f} m. "
                "Connect to QLabs to move the camera."
            )
            return

        try:
            location = self.controller.move_to(
                x=x,
                y=y,
                surface_z=surface_z,
                height_m=self.height_spin.value(),
                pitch_deg=self.pitch_spin.value(),
                yaw_deg=self.yaw_spin.value(),
                fov_deg=self.fov_spin.value(),
            )
            self.status_label.setText(
                f"Camera moved to X={location[0]:.2f}, Y={location[1]:.2f}, "
                f"Z={location[2]:.2f} m. "
                f"Measured surface Z≈{surface_z:.2f} m; "
                f"click is {distance_to_trace:.1f} m from the logged trajectory."
            )
        except Exception as exc:
            self.status_label.setText(f"Camera move failed: {exc}")
            QMessageBox.warning(self, "Camera move failed", str(exc))

    def closeEvent(self, event) -> None:
        self.controller.close()
        super().closeEvent(event)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Display the measured QLabs Open Road map and move a free "
        "camera to clicked world coordinates."
    )
    parser.add_argument(
        "--reference",
        type=Path,
        default=None,
        help="Path to open_road_reference.json",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    try:
        reference_path = find_reference_file(args.reference)
        document, raw_points = load_measured_points(reference_path)
        loop_points, loop_info = extract_stable_completed_loop(raw_points)
    except Exception as exc:
        print(f"Could not load Open Road reference: {exc}", file=sys.stderr)
        return 1

    app = QApplication(sys.argv)
    window = MainWindow(
        reference_path=reference_path,
        document=document,
        raw_points=raw_points,
        loop_points=loop_points,
        loop_info=loop_info,
    )
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
