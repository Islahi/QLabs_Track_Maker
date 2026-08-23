"""CAD-style editable guide primitives used to generate road geometry."""

from __future__ import annotations

import math

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPainterPathStroker, QPen
from PySide6.QtWidgets import QGraphicsEllipseItem, QGraphicsItem, QMenu

from config import PIXELS_PER_METER, SELECTION_COLOR
from core.geometry import snap_value, world_to_scene
from items.base import TrackItem


SKETCH_COLOR = QColor(45, 200, 235)
SKETCH_PORT_COLOR = QColor(75, 225, 135)
SKETCH_HANDLE_COLOR = QColor(255, 185, 65)


def _path_from_points(points: list[QPointF]) -> QPainterPath:
    path = QPainterPath()
    if points:
        path.moveTo(points[0])
        for point in points[1:]:
            path.lineTo(point)
    return path


def _local_world_points(points_m) -> list[QPointF]:
    result = []
    for value in points_m or []:
        if isinstance(value, (list, tuple)) and len(value) >= 2:
            result.append(
                QPointF(
                    float(value[0]) * PIXELS_PER_METER,
                    -float(value[1]) * PIXELS_PER_METER,
                )
            )
    return result


def _points_to_world_m(points: list[QPointF]) -> list[list[float]]:
    return [
        [
            round(point.x() / PIXELS_PER_METER, 4),
            round(-point.y() / PIXELS_PER_METER, 4),
        ]
        for point in points
    ]


def sample_three_point_arc(
    start: QPointF,
    middle: QPointF,
    end: QPointF,
) -> list[QPointF]:
    """Return a circular arc through three editor-space points."""
    x1, y1 = start.x(), start.y()
    x2, y2 = middle.x(), middle.y()
    x3, y3 = end.x(), end.y()
    determinant = 2.0 * (
        x1 * (y2 - y3)
        + x2 * (y3 - y1)
        + x3 * (y1 - y2)
    )
    if abs(determinant) <= 1e-6:
        return [QPointF(start), QPointF(middle), QPointF(end)]

    q1 = x1 * x1 + y1 * y1
    q2 = x2 * x2 + y2 * y2
    q3 = x3 * x3 + y3 * y3
    cx = (
        q1 * (y2 - y3)
        + q2 * (y3 - y1)
        + q3 * (y1 - y2)
    ) / determinant
    cy = (
        q1 * (x3 - x2)
        + q2 * (x1 - x3)
        + q3 * (x2 - x1)
    ) / determinant
    radius = math.hypot(x1 - cx, y1 - cy)
    if radius <= 1e-6:
        return [QPointF(start), QPointF(middle), QPointF(end)]

    a_start = math.atan2(y1 - cy, x1 - cx)
    a_middle = math.atan2(y2 - cy, x2 - cx)
    a_end = math.atan2(y3 - cy, x3 - cx)
    tau = math.tau
    ccw_end = (a_end - a_start) % tau
    ccw_middle = (a_middle - a_start) % tau
    sweep = ccw_end if ccw_middle <= ccw_end else -(tau - ccw_end)
    samples = max(8, int(math.ceil(abs(math.degrees(sweep)) / 5.0)))
    return [
        QPointF(
            cx + radius * math.cos(a_start + sweep * step / samples),
            cy + radius * math.sin(a_start + sweep * step / samples),
        )
        for step in range(samples + 1)
    ]


class _SketchHandle(QGraphicsEllipseItem):
    RADIUS_PX = 7.0

    def __init__(self, guide: "SketchGuideItem", index: int, role: str):
        r = self.RADIUS_PX
        super().__init__(-r, -r, r * 2.0, r * 2.0, guide)
        self.guide = guide
        self.index = int(index)
        self.role = str(role)
        self._syncing = False
        self._dragging = False
        self.is_control_handle = True
        self.setFlags(
            QGraphicsItem.GraphicsItemFlag.ItemIsMovable
            | QGraphicsItem.GraphicsItemFlag.ItemIsSelectable
            | QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges
        )
        self.setZValue(6000)
        self.setPen(QPen(QColor(250, 250, 250), 1.4))
        self.setBrush(SKETCH_HANDLE_COLOR)
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.setToolTip(f"Drag to resize/reshape ({self.role})")

    def itemChange(self, change, value):
        if (
            change == QGraphicsItem.GraphicsItemChange.ItemPositionChange
            and isinstance(value, QPointF)
            and not self._syncing
        ):
            return self.guide.snap_handle_local(self.index, self.role, value)
        result = super().itemChange(change, value)
        if (
            change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged
            and not self._syncing
        ):
            self.guide.handle_moved(self.index, self.role, self.pos())
        return result

    def mousePressEvent(self, event):
        self.guide.setSelected(True)
        self.setSelected(True)
        if event.button() == Qt.MouseButton.LeftButton:
            self._dragging = True
            scene = self.scene()
            if scene is not None and hasattr(scene, "window"):
                scene.window.begin_canvas_undo(f"Resize {self.guide.DISPLAY_NAME}")
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._dragging:
            proposed = self.guide.mapFromScene(event.scenePos())
            self.setPos(self.guide.snap_handle_local(self.index, self.role, proposed))
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self._dragging and event.button() == Qt.MouseButton.LeftButton:
            self._dragging = False
            scene = self.scene()
            if scene is not None and hasattr(scene, "window"):
                if hasattr(scene.window, "register_sketch_circle_ports"):
                    scene.window.register_sketch_circle_ports(self.guide)
                scene.window.end_canvas_undo()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def contextMenuEvent(self, event):
        self.guide.setSelected(True)
        self.setSelected(True)
        scene = self.scene()
        if scene is None or not hasattr(scene, "window"):
            event.ignore()
            return
        window = scene.window
        menu = QMenu()
        exact_label = (
            "Set exact radius…"
            if self.role == "radius"
            else "Set exact point position…"
        )
        exact_action = menu.addAction(exact_label)
        constraint_actions = {}
        if isinstance(self.guide, SketchLineItem):
            constraint_menu = menu.addMenu("Line constraint")
            for label, value in (
                ("Free angle", ""),
                ("Horizontal", "horizontal"),
                ("Vertical", "vertical"),
            ):
                action = constraint_menu.addAction(label)
                action.setCheckable(True)
                action.setChecked(self.guide.axis_constraint == value)
                constraint_actions[action] = value
        menu.addSeparator()
        generate_action = menu.addAction("Generate Road and Remove Guide(s)")
        chosen = menu.exec(event.screenPos())
        if chosen is exact_action:
            window.edit_sketch_control_point(self.guide, self.index, self.role)
        elif chosen is generate_action:
            window.generate_roads_from_sketch()
        elif chosen in constraint_actions:
            window.set_sketch_line_constraint(
                self.guide,
                constraint_actions[chosen],
                self.index,
            )
        event.accept()


class SketchGuideItem(TrackItem):
    """Base for non-exported, directly editable CAD guide geometry."""

    DISPLAY_NAME = "Road Guide"

    def __init__(self, object_id: str | None = None, generated_road_id: str = ""):
        super().__init__(object_id=object_id)
        self.generated_road_id = str(generated_road_id or "")
        self._handles: list[_SketchHandle] = []
        self.setZValue(300)

    def is_sketch_guide(self) -> bool:
        return True

    def sampled_local_points(self) -> list[QPointF]:
        raise NotImplementedError

    def sampled_scene_points(self) -> list[QPointF]:
        return [self.mapToScene(point) for point in self.sampled_local_points()]

    def _guide_path(self) -> QPainterPath:
        return _path_from_points(self.sampled_local_points())

    def boundingRect(self) -> QRectF:
        stroker = QPainterPathStroker()
        stroker.setWidth(24.0)
        return stroker.createStroke(self._guide_path()).boundingRect()

    def shape(self) -> QPainterPath:
        stroker = QPainterPathStroker()
        stroker.setWidth(14.0)
        return stroker.createStroke(self._guide_path())

    def _paint_path(self, painter: QPainter):
        if self.isSelected():
            selected = QPen(SELECTION_COLOR, 5.0)
            selected.setCosmetic(True)
            selected.setCapStyle(Qt.PenCapStyle.RoundCap)
            selected.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            painter.setPen(selected)
            painter.drawPath(self._guide_path())

        pen = QPen(SKETCH_COLOR, 2.2, Qt.PenStyle.DashLine)
        pen.setCosmetic(True)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(self._guide_path())

    def _replace_handles(self, definitions: list[tuple[QPointF, str]]):
        scene = self.scene()
        for handle in self._handles:
            handle.setParentItem(None)
            if scene is not None:
                scene.removeItem(handle)
        self._handles.clear()
        for index, (point, role) in enumerate(definitions):
            handle = _SketchHandle(self, index, role)
            handle._syncing = True
            handle.setPos(point)
            handle._syncing = False
            handle.setVisible(self.isSelected())
            self._handles.append(handle)

    def _sync_handle_positions(self, definitions: list[tuple[QPointF, str]]):
        if len(definitions) != len(self._handles):
            self._replace_handles(definitions)
            return
        for handle, (point, role) in zip(self._handles, definitions):
            handle.role = role
            handle._syncing = True
            handle.setPos(point)
            handle._syncing = False

    def snap_handle_local(self, index: int, role: str, proposed: QPointF) -> QPointF:
        scene = self.scene()
        if scene is None:
            return proposed
        scene_point = self.mapToScene(proposed)
        if role == "control":
            snapped_scene = QPointF(
                snap_value(scene_point.x(), PIXELS_PER_METER),
                snap_value(scene_point.y(), PIXELS_PER_METER),
            )
        else:
            snapped_scene = scene.snap_drawing_point(
                scene_point,
                exclude_item=self,
            )
        return self.mapFromScene(snapped_scene)

    def handle_moved(self, index: int, role: str, point: QPointF):
        raise NotImplementedError

    def itemChange(self, change, value):
        result = super().itemChange(change, value)
        if change == QGraphicsItem.GraphicsItemChange.ItemSelectedHasChanged:
            for handle in getattr(self, "_handles", []):
                handle.setVisible(bool(value))
        elif change in (
            QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged,
            QGraphicsItem.GraphicsItemChange.ItemRotationHasChanged,
        ):
            scene = self.scene()
            if scene is not None and hasattr(scene, "window"):
                scene.window.sync_generated_road_from_guide(self)
        return result

    def _geometry_changed(self):
        self.update()
        scene = self.scene()
        if scene is not None:
            scene.update()
            if hasattr(scene, "notify_selection_or_geometry_changed"):
                scene.notify_selection_or_geometry_changed()
            if hasattr(scene, "window"):
                scene.window.sync_generated_road_from_guide(self)

    def _sketch_base_dict(self) -> dict:
        data = self.base_dict()
        if self.generated_road_id:
            data["generated_road_id"] = self.generated_road_id
        return data

    def duplicate(self):
        # A copied guide must generate its own road instead of updating the
        # road that belongs to the original guide.
        copy = super().duplicate()
        if isinstance(copy, SketchGuideItem):
            copy.generated_road_id = ""
        return copy


class SketchLineItem(SketchGuideItem):
    TYPE_NAME = "sketch_line"
    DISPLAY_NAME = "Road Guide Line"

    def __init__(
        self,
        points_m=None,
        axis_constraint: str = "",
        object_id: str | None = None,
        generated_road_id: str = "",
    ):
        super().__init__(object_id, generated_road_id)
        points = _local_world_points(points_m or [(0.0, 0.0), (20.0, 0.0)])
        self.points_px = points[:2] if len(points) >= 2 else [QPointF(), QPointF(400, 0)]
        inferred = ""
        if abs(self.points_px[1].y() - self.points_px[0].y()) <= 1e-6:
            inferred = "horizontal"
        elif abs(self.points_px[1].x() - self.points_px[0].x()) <= 1e-6:
            inferred = "vertical"
        self.axis_constraint = str(axis_constraint or inferred)
        self._replace_handles([
            (self.points_px[0], "endpoint"),
            (self.points_px[1], "endpoint"),
        ])

    def sampled_local_points(self) -> list[QPointF]:
        return [QPointF(point) for point in self.points_px]

    def paint(self, painter: QPainter, option, widget=None):
        self._paint_path(painter)

    def handle_moved(self, index: int, role: str, point: QPointF):
        if not (0 <= index < 2):
            return
        other = self.points_px[1 - index]
        if math.hypot(point.x() - other.x(), point.y() - other.y()) < 5.0:
            self._sync_handle_positions([
                (self.points_px[0], "endpoint"),
                (self.points_px[1], "endpoint"),
            ])
            return
        self.prepareGeometryChange()
        self.points_px[index] = QPointF(point)
        self._geometry_changed()

    def snap_handle_local(self, index: int, role: str, proposed: QPointF) -> QPointF:
        snapped = super().snap_handle_local(index, role, proposed)
        other = self.points_px[1 - index]
        if self.axis_constraint == "horizontal":
            snapped.setY(other.y())
        elif self.axis_constraint == "vertical":
            snapped.setX(other.x())
        return snapped

    def connection_points_local(self) -> list[dict]:
        delta = self.points_px[1] - self.points_px[0]
        angle = math.degrees(math.atan2(delta.y(), delta.x()))
        return [
            {"name": "start", "pos": self.points_px[0], "heading_deg": angle + 180.0},
            {"name": "end", "pos": self.points_px[1], "heading_deg": angle},
        ]

    def to_dict(self) -> dict:
        data = self._sketch_base_dict()
        data["points_m"] = _points_to_world_m(self.points_px)
        if self.axis_constraint:
            data["axis_constraint"] = self.axis_constraint
        return data

    @classmethod
    def from_dict(cls, data: dict):
        item = cls(
            points_m=data.get("points_m"),
            axis_constraint=data.get("axis_constraint", ""),
            object_id=data.get("id"),
            generated_road_id=data.get("generated_road_id", ""),
        )
        item.setPos(world_to_scene(float(data.get("x", 0.0)), float(data.get("y", 0.0))))
        item.setRotation(float(data.get("rotation_deg", 0.0)))
        return item

    def selection_text(self) -> str:
        length_m = math.hypot(
            self.points_px[1].x() - self.points_px[0].x(),
            self.points_px[1].y() - self.points_px[0].y(),
        ) / PIXELS_PER_METER
        constraint = self.axis_constraint.title() if self.axis_constraint else "Free angle"
        return super().selection_text() + f"\nLength: {length_m:.2f} m\nConnections: 2 endpoints\nConstraint: {constraint}"


class SketchArcItem(SketchGuideItem):
    TYPE_NAME = "sketch_arc"
    DISPLAY_NAME = "Road Guide Arc"

    def __init__(
        self,
        points_m=None,
        object_id: str | None = None,
        generated_road_id: str = "",
    ):
        super().__init__(object_id, generated_road_id)
        default = [(0.0, 0.0), (8.0, 5.0), (16.0, 0.0)]
        points = _local_world_points(points_m or default)
        self.points_px = points[:3] if len(points) >= 3 else _local_world_points(default)
        self._replace_handles([
            (self.points_px[0], "endpoint"),
            (self.points_px[1], "control"),
            (self.points_px[2], "endpoint"),
        ])

    def sampled_local_points(self) -> list[QPointF]:
        return sample_three_point_arc(*self.points_px)

    def paint(self, painter: QPainter, option, widget=None):
        self._paint_path(painter)

    def handle_moved(self, index: int, role: str, point: QPointF):
        if not (0 <= index < 3):
            return
        self.prepareGeometryChange()
        self.points_px[index] = QPointF(point)
        self._geometry_changed()

    def connection_points_local(self) -> list[dict]:
        points = self.sampled_local_points()
        if len(points) < 2:
            return []
        start = points[0] - points[1]
        end = points[-1] - points[-2]
        return [
            {
                "name": "start",
                "pos": points[0],
                "heading_deg": math.degrees(math.atan2(start.y(), start.x())),
            },
            {
                "name": "end",
                "pos": points[-1],
                "heading_deg": math.degrees(math.atan2(end.y(), end.x())),
            },
        ]

    def to_dict(self) -> dict:
        data = self._sketch_base_dict()
        data["points_m"] = _points_to_world_m(self.points_px)
        return data

    @classmethod
    def from_dict(cls, data: dict):
        item = cls(
            points_m=data.get("points_m"),
            object_id=data.get("id"),
            generated_road_id=data.get("generated_road_id", ""),
        )
        item.setPos(world_to_scene(float(data.get("x", 0.0)), float(data.get("y", 0.0))))
        item.setRotation(float(data.get("rotation_deg", 0.0)))
        return item

    def selection_text(self) -> str:
        return super().selection_text() + "\nConnections: 2 arc endpoints\nResize: drag start/control/end handles"


class SketchCircleItem(SketchGuideItem):
    TYPE_NAME = "sketch_circle"
    DISPLAY_NAME = "Road Guide Circle"

    def __init__(
        self,
        radius_m: float = 10.0,
        ports_deg=None,
        object_id: str | None = None,
        generated_road_id: str = "",
    ):
        super().__init__(object_id, generated_road_id)
        self.radius_m = max(1.0, float(radius_m))
        self.ports_deg = [float(value) % 360.0 for value in (ports_deg or [])]
        self._replace_handles([(QPointF(self.radius_px, 0.0), "radius")])

    @property
    def radius_px(self) -> float:
        return self.radius_m * PIXELS_PER_METER

    def sampled_local_points(self) -> list[QPointF]:
        # Keep roundabouts visually smooth while placing a firm upper bound on
        # exported spline control points and QLabs rendering work.
        count = min(96, max(32, int(math.ceil(self.radius_m * 4.0))))
        return [
            QPointF(
                self.radius_px * math.cos(math.tau * index / count),
                self.radius_px * math.sin(math.tau * index / count),
            )
            for index in range(count + 1)
        ]

    def paint(self, painter: QPainter, option, widget=None):
        self._paint_path(painter)
        painter.setPen(QPen(QColor(245, 245, 245), 1.2))
        painter.setBrush(SKETCH_PORT_COLOR)
        for connection in self.connection_points_local():
            painter.drawEllipse(connection["pos"], 5.0, 5.0)

    def snap_handle_local(self, index: int, role: str, proposed: QPointF) -> QPointF:
        if role != "radius":
            return super().snap_handle_local(index, role, proposed)
        radius_m = max(1.0, math.hypot(proposed.x(), proposed.y()) / PIXELS_PER_METER)
        radius_m = round(radius_m * 2.0) / 2.0
        return QPointF(radius_m * PIXELS_PER_METER, 0.0)

    def handle_moved(self, index: int, role: str, point: QPointF):
        if role != "radius":
            return
        self.prepareGeometryChange()
        self.radius_m = max(1.0, point.x() / PIXELS_PER_METER)
        self._geometry_changed()

    def nearest_connection_candidate_scene(self, scene_point: QPointF) -> QPointF | None:
        local = self.mapFromScene(scene_point)
        distance = math.hypot(local.x(), local.y())
        if distance <= 1e-9 or abs(distance - self.radius_px) > 1.5 * PIXELS_PER_METER:
            return None
        scale = self.radius_px / distance
        return self.mapToScene(QPointF(local.x() * scale, local.y() * scale))

    def add_port_scene(self, scene_point: QPointF):
        local = self.mapFromScene(scene_point)
        angle = math.degrees(math.atan2(local.y(), local.x())) % 360.0
        if any(abs((angle - existing + 180.0) % 360.0 - 180.0) <= 4.0 for existing in self.ports_deg):
            return
        self.ports_deg.append(angle)
        self.ports_deg.sort()
        self.update()

    def connection_points_local(self) -> list[dict]:
        return [
            {
                "name": f"port_{index + 1}",
                "pos": QPointF(
                    self.radius_px * math.cos(math.radians(angle)),
                    self.radius_px * math.sin(math.radians(angle)),
                ),
                "heading_deg": angle,
            }
            for index, angle in enumerate(self.ports_deg)
        ]

    def to_dict(self) -> dict:
        data = self._sketch_base_dict()
        data.update({
            "radius_m": self.radius_m,
            "ports_deg": [round(value, 4) for value in self.ports_deg],
        })
        return data

    @classmethod
    def from_dict(cls, data: dict):
        item = cls(
            radius_m=float(data.get("radius_m", 10.0)),
            ports_deg=data.get("ports_deg", []),
            object_id=data.get("id"),
            generated_road_id=data.get("generated_road_id", ""),
        )
        item.setPos(world_to_scene(float(data.get("x", 0.0)), float(data.get("y", 0.0))))
        item.setRotation(float(data.get("rotation_deg", 0.0)))
        return item

    def selection_text(self) -> str:
        return (
            super().selection_text()
            + f"\nRadius: {self.radius_m:.2f} m"
            + f"\nDynamic road ports: {len(self.ports_deg)}"
            + "\nResize: drag the orange radius handle"
        )
