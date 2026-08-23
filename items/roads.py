"""Road components from Track Editor v1.0.1."""

import math

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPainterPathStroker, QPen
from PySide6.QtWidgets import QGraphicsEllipseItem, QGraphicsItem, QMenu

from config import (
    PIXELS_PER_METER,
    DEFAULT_ROAD_LENGTH_M,
    DEFAULT_ROAD_WIDTH_M,
    DEFAULT_CURVE_RADIUS_M,
    DEFAULT_JUNCTION_ARM_M,
    DEFAULT_ROAD_END_LENGTH_M,
    ROAD_COLOR,
    EDGE_LINE_COLOR,
    CENTER_LINE_COLOR,
    SELECTION_COLOR,
    EDGE_LINE_WIDTH_PX,
    CENTER_LINE_WIDTH_PX,
    SELECTION_LINE_WIDTH_PX,
    EDGE_LINE_INSET_PX,
    DEFAULT_MEDIAN_WALL_LENGTH_M,
    DEFAULT_MEDIAN_WALL_WIDTH_M,
    DEFAULT_MEDIAN_WALL_HEIGHT_M,
    MEDIAN_WALL_COLOR,
)
from core.geometry import world_to_scene
from items.base import TrackItem


def _path_from_points(points: list[QPointF]) -> QPainterPath:
    path = QPainterPath()
    if not points:
        return path
    path.moveTo(points[0])
    for point in points[1:]:
        path.lineTo(point)
    return path


def _offset_polyline(points: list[QPointF], offset: float) -> list[QPointF]:
    """Return a stable mitered offset for an open or closed polyline."""
    if len(points) < 2 or abs(offset) <= 1e-9:
        return [QPointF(point) for point in points]

    closed = len(points) >= 4 and math.hypot(
        points[0].x() - points[-1].x(),
        points[0].y() - points[-1].y(),
    ) <= 1e-6
    vertices = points[:-1] if closed else points
    normals: list[QPointF] = []
    segment_count = len(vertices) if closed else len(vertices) - 1
    for index in range(segment_count):
        start = vertices[index]
        end = vertices[(index + 1) % len(vertices)]
        dx = end.x() - start.x()
        dy = end.y() - start.y()
        length = math.hypot(dx, dy)
        if length <= 1e-9:
            normals.append(QPointF(0.0, 0.0))
        else:
            # Positive offset is the visual left side of the direction of
            # travel (screen Y grows downward).
            normals.append(QPointF(dy / length, -dx / length))

    result: list[QPointF] = []
    for index, point in enumerate(vertices):
        if not closed and index == 0:
            normal = normals[0]
            result.append(point + normal * offset)
            continue
        if not closed and index == len(vertices) - 1:
            normal = normals[-1]
            result.append(point + normal * offset)
            continue

        previous = normals[(index - 1) % len(normals)]
        following = normals[index]
        bisector = previous + following
        bisector_length = math.hypot(bisector.x(), bisector.y())
        if bisector_length <= 1e-6:
            result.append(point + following * offset)
            continue

        bisector = QPointF(
            bisector.x() / bisector_length,
            bisector.y() / bisector_length,
        )
        denominator = bisector.x() * following.x() + bisector.y() * following.y()
        if abs(denominator) <= 0.20:
            miter_distance = offset
        else:
            miter_distance = offset / denominator

        # Avoid extreme spikes at very acute control-node angles.
        maximum = max(abs(offset), abs(offset) * 4.0)
        miter_distance = max(-maximum, min(maximum, miter_distance))
        result.append(point + bisector * miter_distance)

    if closed and result:
        result.append(QPointF(result[0]))
    return result


def _smooth_polyline(points: list[QPointF], samples_per_segment: int = 8) -> list[QPointF]:
    """Sample an open Catmull-Rom curve through all control nodes."""
    if len(points) < 3:
        return [QPointF(point) for point in points]

    result: list[QPointF] = []
    samples = max(3, int(samples_per_segment))
    for index in range(len(points) - 1):
        p0 = points[max(0, index - 1)]
        p1 = points[index]
        p2 = points[index + 1]
        p3 = points[min(len(points) - 1, index + 2)]
        for step in range(samples):
            t = step / samples
            t2 = t * t
            t3 = t2 * t
            x = 0.5 * (
                2.0 * p1.x()
                + (-p0.x() + p2.x()) * t
                + (2.0 * p0.x() - 5.0 * p1.x() + 4.0 * p2.x() - p3.x()) * t2
                + (-p0.x() + 3.0 * p1.x() - 3.0 * p2.x() + p3.x()) * t3
            )
            y = 0.5 * (
                2.0 * p1.y()
                + (-p0.y() + p2.y()) * t
                + (2.0 * p0.y() - 5.0 * p1.y() + 4.0 * p2.y() - p3.y()) * t2
                + (-p0.y() + 3.0 * p1.y() - 3.0 * p2.y() + p3.y()) * t3
            )
            result.append(QPointF(x, y))
    result.append(QPointF(points[-1]))
    return result


class _ContinuousRoadNodeHandle(QGraphicsEllipseItem):
    """Draggable child handle used to reshape a continuous road."""

    RADIUS_PX = 7.0

    def __init__(self, road: "ContinuousRoadItem", index: int):
        radius = self.RADIUS_PX
        super().__init__(-radius, -radius, radius * 2.0, radius * 2.0, road)
        self.road = road
        self.index = int(index)
        self._syncing = False
        self._dragging = False
        self.is_control_handle = True
        self.setFlags(
            QGraphicsItem.GraphicsItemFlag.ItemIsMovable
            | QGraphicsItem.GraphicsItemFlag.ItemIsSelectable
            | QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges
        )
        self.setAcceptHoverEvents(True)
        self.setZValue(5000)
        self.setPen(QPen(QColor(235, 245, 250), 1.5))
        self.setBrush(QColor(40, 185, 225))
        self.setToolTip(
            "Drag to reshape the road. Double-click a node to remove it."
        )

    def itemChange(self, change, value):
        if (
            change == QGraphicsItem.GraphicsItemChange.ItemPositionChange
            and isinstance(value, QPointF)
            and not self._syncing
        ):
            return self.road.snap_node_local(self.index, value)

        result = super().itemChange(change, value)
        if (
            change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged
            and not self._syncing
        ):
            self.road.node_handle_moved(self.index, self.pos())
        return result

    def mousePressEvent(self, event):
        self.road.setSelected(True)
        self.setSelected(True)
        if event.button() == Qt.MouseButton.LeftButton:
            self._dragging = True
            scene = self.scene()
            if scene is not None and hasattr(scene, "window"):
                scene.window.begin_canvas_undo("Reshape continuous road")
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._dragging:
            proposed = self.road.mapFromScene(event.scenePos())
            self.setPos(self.road.snap_node_local(self.index, proposed))
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self._dragging and event.button() == Qt.MouseButton.LeftButton:
            self._dragging = False
            scene = self.scene()
            if scene is not None and hasattr(scene, "window"):
                scene.window.end_canvas_undo()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def contextMenuEvent(self, event):
        self.road.setSelected(True)
        self.setSelected(True)
        scene = self.scene()
        if scene is None or not hasattr(scene, "window"):
            event.ignore()
            return
        window = scene.window
        menu = QMenu()
        exact_action = menu.addAction("Set exact point position…")
        before_action = menu.addAction("Insert point before")
        before_action.setEnabled(self.index > 0)
        after_action = menu.addAction("Insert point after")
        after_action.setEnabled(self.index < len(self.road.points_m) - 1)
        menu.addSeparator()
        delete_action = menu.addAction("Delete point")
        delete_action.setEnabled(len(self.road.points_m) > 2)
        chosen = menu.exec(event.screenPos())
        if chosen is exact_action:
            window.edit_continuous_road_control_point(self.road, self.index)
        elif chosen is before_action:
            window.insert_continuous_road_control_point(self.road, self.index, before=True)
        elif chosen is after_action:
            window.insert_continuous_road_control_point(self.road, self.index, before=False)
        elif chosen is delete_action:
            window.delete_continuous_road_control_point(self.road, self.index)
        event.accept()

    def mouseDoubleClickEvent(self, event):
        if len(self.road.points_m) <= 2:
            event.accept()
            return
        scene = self.scene()
        if scene is not None and hasattr(scene, "window"):
            scene.window._begin_undo_transaction("Remove continuous-road node")
        self.road.remove_node(self.index)
        if scene is not None and hasattr(scene, "window"):
            scene.window._commit_undo_transaction()
        event.accept()

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

    def supports_road_markings(self) -> bool:
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
        if self.show_edge_a:
            painter.setPen(self.road_marking_pen("edge_a", EDGE_LINE_WIDTH_PX))
            painter.drawLine(
                QPointF(-self.length_px / 2.0, -self.width_px / 2.0 + EDGE_LINE_INSET_PX),
                QPointF(self.length_px / 2.0, -self.width_px / 2.0 + EDGE_LINE_INSET_PX),
            )

        if self.show_edge_b:
            painter.setPen(self.road_marking_pen("edge_b", EDGE_LINE_WIDTH_PX))
            painter.drawLine(
                QPointF(-self.length_px / 2.0, self.width_px / 2.0 - EDGE_LINE_INSET_PX),
                QPointF(self.length_px / 2.0, self.width_px / 2.0 - EDGE_LINE_INSET_PX),
            )

        # ========================================================
        # Configurable center line
        # ========================================================
        if self.show_center_line:
            painter.setPen(self.road_marking_pen("center", CENTER_LINE_WIDTH_PX))
            for offset in self.lane_divider_offsets_px(self.width_px):
                painter.drawLine(
                    QPointF(-self.length_px / 2.0, offset),
                    QPointF(self.length_px / 2.0, offset),
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
                "road_markings": self.road_marking_dict(),
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
        item.load_road_marking_dict(data.get("road_markings"))
        return item

    def selection_text(self) -> str:
        return (
            super().selection_text()
            + f"\nLength: {self.length_m:.1f} m"
            + f"\nWidth: {self.width_m:.1f} m"
        )


class ContinuousRoadItem(TrackItem):
    """One editable road following an arbitrary connected polyline."""

    TYPE_NAME = "continuous_road"
    DISPLAY_NAME = "Continuous Road"

    def __init__(
        self,
        points_m: list[tuple[float, float]] | None = None,
        width_m: float = DEFAULT_ROAD_WIDTH_M,
        smooth: bool = False,
        source_guide_id: str = "",
        auto_connector: bool = False,
        object_id: str | None = None,
    ):
        super().__init__(object_id=object_id)
        self.width_m = max(1.0, float(width_m))
        self.smooth = bool(smooth)
        self.source_guide_id = str(source_guide_id or "")
        self.auto_connector = bool(auto_connector)
        self.points_m = self._clean_points(
            points_m or [(0.0, 0.0), (DEFAULT_ROAD_LENGTH_M, 0.0)]
        )
        self._node_handles: list[_ContinuousRoadNodeHandle] = []
        if self.auto_connector:
            self.setFlag(
                QGraphicsItem.GraphicsItemFlag.ItemIsMovable,
                False,
            )
            self.setFlag(
                QGraphicsItem.GraphicsItemFlag.ItemIsSelectable,
                False,
            )
            self.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
            self.setZValue(11)
        else:
            self._rebuild_node_handles()

    @staticmethod
    def _clean_points(points) -> list[tuple[float, float]]:
        cleaned: list[tuple[float, float]] = []
        for value in points:
            if not isinstance(value, (list, tuple)) or len(value) < 2:
                continue
            point = (float(value[0]), float(value[1]))
            if cleaned and math.hypot(
                point[0] - cleaned[-1][0],
                point[1] - cleaned[-1][1],
            ) < 0.05:
                continue
            cleaned.append(point)
        if len(cleaned) < 2:
            return [(0.0, 0.0), (DEFAULT_ROAD_LENGTH_M, 0.0)]
        return cleaned

    @property
    def total_length_m(self) -> float:
        points = self.rendered_points_px()
        return sum(
            math.hypot(end.x() - start.x(), end.y() - start.y())
            / PIXELS_PER_METER
            for start, end in zip(points, points[1:])
        )

    @property
    def length_m(self) -> float:
        """Expose total length to the shared effective-dimension summary."""
        return self.total_length_m

    def supports_guide_line(self) -> bool:
        return True

    def supports_road_markings(self) -> bool:
        return True

    def local_points_px(self) -> list[QPointF]:
        return [
            QPointF(x_m * PIXELS_PER_METER, -y_m * PIXELS_PER_METER)
            for x_m, y_m in self.points_m
        ]

    def scene_points(self) -> list[QPointF]:
        return [self.mapToScene(point) for point in self.local_points_px()]

    def rendered_points_px(self) -> list[QPointF]:
        points = self.local_points_px()
        return _smooth_polyline(points) if self.smooth else points

    def set_scene_points(self, scene_points: list[QPointF]):
        if len(scene_points) < 2:
            return
        local_points = [self.mapFromScene(point) for point in scene_points]
        self.set_points_m(
            [
                (
                    point.x() / PIXELS_PER_METER,
                    -point.y() / PIXELS_PER_METER,
                )
                for point in local_points
            ]
        )

    def set_points_m(self, points_m):
        cleaned = self._clean_points(points_m)
        self.prepareGeometryChange()
        self.points_m = cleaned
        if not self.auto_connector:
            self._rebuild_node_handles()
        self.update()
        scene = self.scene()
        if scene is not None:
            scene.update()

    def append_scene_point(self, scene_point: QPointF):
        points = self.scene_points()
        points.append(QPointF(scene_point))
        self.set_scene_points(points)

    def remove_node(self, index: int):
        if len(self.points_m) <= 2 or not (0 <= index < len(self.points_m)):
            return
        points = list(self.points_m)
        del points[index]
        self.set_points_m(points)

    def _rebuild_node_handles(self):
        scene = self.scene()
        for handle in self._node_handles:
            handle.setParentItem(None)
            if scene is not None:
                scene.removeItem(handle)
        self._node_handles.clear()

        selected = self.isSelected()
        for index, point in enumerate(self.local_points_px()):
            handle = _ContinuousRoadNodeHandle(self, index)
            handle._syncing = True
            handle.setPos(point)
            handle._syncing = False
            handle.setVisible(selected)
            self._node_handles.append(handle)

    def snap_node_local(self, index: int, proposed_local: QPointF) -> QPointF:
        scene = self.scene()
        if scene is None:
            return proposed_local

        proposed_scene = self.mapToScene(proposed_local)
        heading = None
        points = self.local_points_px()
        if len(points) >= 2:
            if index == 0:
                neighbor_scene = self.mapToScene(points[1])
                heading = math.degrees(
                    math.atan2(
                        proposed_scene.y() - neighbor_scene.y(),
                        proposed_scene.x() - neighbor_scene.x(),
                    )
                )
            elif index == len(points) - 1:
                neighbor_scene = self.mapToScene(points[-2])
                heading = math.degrees(
                    math.atan2(
                        proposed_scene.y() - neighbor_scene.y(),
                        proposed_scene.x() - neighbor_scene.x(),
                    )
                )

        snapped_scene = scene.snap_drawing_point(
            proposed_scene,
            exclude_item=self,
            heading_deg=heading,
        )
        snapped_local = self.mapFromScene(snapped_scene)

        # Do not let a handle collapse onto an adjacent node.
        minimum_px = 0.25 * PIXELS_PER_METER
        for neighbor_index in (index - 1, index + 1):
            if not (0 <= neighbor_index < len(points)):
                continue
            neighbor = points[neighbor_index]
            if math.hypot(
                snapped_local.x() - neighbor.x(),
                snapped_local.y() - neighbor.y(),
            ) < minimum_px:
                return points[index]
        return snapped_local

    def node_handle_moved(self, index: int, local_point: QPointF):
        if not (0 <= index < len(self.points_m)):
            return
        self.prepareGeometryChange()
        self.points_m[index] = (
            local_point.x() / PIXELS_PER_METER,
            -local_point.y() / PIXELS_PER_METER,
        )
        self.update()
        scene = self.scene()
        if scene is not None:
            scene.update()
            if hasattr(scene, "notify_selection_or_geometry_changed"):
                scene.notify_selection_or_geometry_changed()

    def center_path(self) -> QPainterPath:
        return _path_from_points(self.rendered_points_px())

    def boundingRect(self) -> QRectF:
        path = self.center_path()
        stroker = QPainterPathStroker()
        stroker.setWidth(self.width_m * PIXELS_PER_METER + 20.0)
        stroker.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        return stroker.createStroke(path).boundingRect()

    def shape(self) -> QPainterPath:
        stroker = QPainterPathStroker()
        stroker.setWidth(self.width_m * PIXELS_PER_METER)
        stroker.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        return stroker.createStroke(self.center_path())

    @staticmethod
    def _configure_path_pen(pen: QPen):
        pen.setCapStyle(Qt.PenCapStyle.FlatCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)

    def paint(self, painter: QPainter, option, widget=None):
        points = self.rendered_points_px()
        center_path = _path_from_points(points)
        road_width_px = self.width_m * PIXELS_PER_METER

        if self.auto_connector:
            center = QPointF(0.0, 0.0)
            if self.isSelected():
                painter.setPen(QPen(SELECTION_COLOR, 4.0))
                painter.setBrush(ROAD_COLOR)
                painter.drawEllipse(
                    center,
                    road_width_px / 2.0 + 3.0,
                    road_width_px / 2.0 + 3.0,
                )
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(ROAD_COLOR)
            painter.drawEllipse(
                center,
                road_width_px / 2.0,
                road_width_px / 2.0,
            )
            return

        if self.isSelected():
            selection_pen = QPen(SELECTION_COLOR, road_width_px + 7.0)
            self._configure_path_pen(selection_pen)
            painter.setPen(selection_pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawPath(center_path)

        road_pen = QPen(ROAD_COLOR, road_width_px)
        self._configure_path_pen(road_pen)
        painter.setPen(road_pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(center_path)

        edge_offset = max(1.0, road_width_px / 2.0 - EDGE_LINE_INSET_PX)
        if self.show_edge_a:
            pen = self.road_marking_pen("edge_a", EDGE_LINE_WIDTH_PX)
            self._configure_path_pen(pen)
            painter.setPen(pen)
            painter.drawPath(_path_from_points(_offset_polyline(points, edge_offset)))

        if self.show_edge_b:
            pen = self.road_marking_pen("edge_b", EDGE_LINE_WIDTH_PX)
            self._configure_path_pen(pen)
            painter.setPen(pen)
            painter.drawPath(_path_from_points(_offset_polyline(points, -edge_offset)))

        if self.show_center_line:
            pen = self.road_marking_pen("center", CENTER_LINE_WIDTH_PX)
            self._configure_path_pen(pen)
            painter.setPen(pen)
            for offset in self.lane_divider_offsets_px(road_width_px):
                painter.drawPath(
                    _path_from_points(_offset_polyline(points, offset))
                )

        if self.guide_enabled:
            guide_offset = -self.resolved_guide_offset_m() * PIXELS_PER_METER
            pen = self.guide_pen()
            self._configure_path_pen(pen)
            painter.setPen(pen)
            painter.drawPath(
                _path_from_points(_offset_polyline(points, guide_offset))
            )

        self.draw_connection_handles(painter)

    def connection_points_local(self) -> list[dict]:
        if self.auto_connector:
            return []
        points = self.rendered_points_px()
        if len(points) < 2:
            return []

        start_delta = points[0] - points[1]
        end_delta = points[-1] - points[-2]
        return [
            {
                "name": "start",
                "pos": points[0],
                "heading_deg": math.degrees(
                    math.atan2(start_delta.y(), start_delta.x())
                ),
            },
            {
                "name": "end",
                "pos": points[-1],
                "heading_deg": math.degrees(
                    math.atan2(end_delta.y(), end_delta.x())
                ),
            },
        ]

    def itemChange(self, change, value):
        result = super().itemChange(change, value)
        if change == QGraphicsItem.GraphicsItemChange.ItemSelectedHasChanged:
            for handle in getattr(self, "_node_handles", []):
                handle.setVisible(bool(value))
        return result

    def to_dict(self) -> dict:
        data = self.base_dict()
        data.update(
            {
                "points_m": [
                    [round(x_m, 4), round(y_m, 4)]
                    for x_m, y_m in self.points_m
                ],
                "width_m": self.width_m,
                "smooth": self.smooth,
                "guide_line": self.guide_dict(),
                "road_markings": self.road_marking_dict(),
            }
        )
        if self.source_guide_id:
            data["source_guide_id"] = self.source_guide_id
        if self.auto_connector:
            data["auto_connector"] = True
        return data

    @classmethod
    def from_dict(cls, data: dict):
        item = cls(
            points_m=data.get("points_m"),
            width_m=float(data.get("width_m", DEFAULT_ROAD_WIDTH_M)),
            smooth=bool(data.get("smooth", False)),
            source_guide_id=data.get("source_guide_id", ""),
            auto_connector=bool(data.get("auto_connector", False)),
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
        item.load_road_marking_dict(data.get("road_markings"))
        return item

    def selection_text(self) -> str:
        if self.auto_connector:
            return super().selection_text() + f"\nAutomatic seamless junction\nWidth: {self.width_m:.1f} m"
        return (
            super().selection_text()
            + f"\nNodes: {len(self.points_m)}"
            + f"\nLength: {self.total_length_m:.1f} m"
            + f"\nWidth: {self.width_m:.1f} m"
            + ("\nCorners: Smooth" if self.smooth else "\nCorners: Straight")
            + "\nDrag cyan nodes to reshape; double-click to remove a node."
        )


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

    def supports_road_markings(self) -> bool:
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

        if self.show_edge_a:
            painter.setPen(self.road_marking_pen("edge_a", EDGE_LINE_WIDTH_PX))
            painter.drawPath(self._arc_path_for_radius(outer_radius))
        if self.show_edge_b:
            painter.setPen(self.road_marking_pen("edge_b", EDGE_LINE_WIDTH_PX))
            painter.drawPath(self._arc_path_for_radius(inner_radius))

        # ========================================================
        # Configurable center line
        # ========================================================
        if self.show_center_line:
            painter.setPen(self.road_marking_pen("center", CENTER_LINE_WIDTH_PX))
            for offset in self.lane_divider_offsets_px(self.width_px):
                painter.drawPath(
                    self._arc_path_for_radius(max(2.0, self.radius_px + offset))
                )

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
                "road_markings": self.road_marking_dict(),
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
        item.load_road_marking_dict(data.get("road_markings"))
        return item

    def selection_text(self) -> str:
        return (
            super().selection_text()
            + f"\nRadius: {self.radius_m:.1f} m"
            + f"\nWidth: {self.width_m:.1f} m"
        )

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

    def supports_road_markings(self) -> bool:
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

        if self.show_edge_a:
            painter.setPen(self.road_marking_pen("edge_a", EDGE_LINE_WIDTH_PX))
            painter.drawLine(
                QPointF(-self.length_px / 2.0, -self.width_px / 2.0 + EDGE_LINE_INSET_PX),
                QPointF(self.length_px / 2.0, -self.width_px / 2.0 + EDGE_LINE_INSET_PX),
            )
        if self.show_edge_b:
            painter.setPen(self.road_marking_pen("edge_b", EDGE_LINE_WIDTH_PX))
            painter.drawLine(
                QPointF(-self.length_px / 2.0, self.width_px / 2.0 - EDGE_LINE_INSET_PX),
                QPointF(self.length_px / 2.0, self.width_px / 2.0 - EDGE_LINE_INSET_PX),
            )

        if self.show_center_line:
            painter.setPen(self.road_marking_pen("center", CENTER_LINE_WIDTH_PX))
            for offset in self.lane_divider_offsets_px(self.width_px):
                painter.drawLine(
                    QPointF(-self.length_px / 2.0, offset),
                    QPointF(self.length_px / 2.0 - 18.0, offset),
                )

        if self.guide_enabled:
            offset_px = self.resolved_guide_offset_m() * PIXELS_PER_METER
            painter.setPen(self.guide_pen())
            painter.drawLine(
                QPointF(-self.length_px / 2.0, offset_px),
                QPointF(self.length_px / 2.0 - 18.0, offset_px),
            )

        # Closed road-end marking.
        if self.show_end_bar:
            painter.setPen(self.road_marking_pen("end_bar", 4))
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
                "road_markings": self.road_marking_dict(),
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
        item.load_road_marking_dict(data.get("road_markings"))
        return item

    def selection_text(self) -> str:
        return (
            super().selection_text()
            + f"\nLength: {self.length_m:.1f} m"
            + f"\nWidth: {self.width_m:.1f} m"
        )

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

    def supports_guide_line(self) -> bool:
        return True

    def supports_road_markings(self) -> bool:
        return True

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

        # Edge A: upper horizontal edge + left stem side.
        if self.show_edge_a:
            painter.setPen(self.road_marking_pen("edge_a", EDGE_LINE_WIDTH_PX))
            painter.drawLine(QPointF(-self.arm_px, -inset_y), QPointF(self.arm_px, -inset_y))
            painter.drawLine(QPointF(-inset_x, half_w), QPointF(-inset_x, self.arm_px))

        # Edge B: lower horizontal pieces + right stem side.
        if self.show_edge_b:
            painter.setPen(self.road_marking_pen("edge_b", EDGE_LINE_WIDTH_PX))
            painter.drawLine(QPointF(-self.arm_px, inset_y), QPointF(-half_w, inset_y))
            painter.drawLine(QPointF(half_w, inset_y), QPointF(self.arm_px, inset_y))
            painter.drawLine(QPointF(inset_x, half_w), QPointF(inset_x, self.arm_px))

        if self.show_center_line:
            painter.setPen(self.road_marking_pen("center", CENTER_LINE_WIDTH_PX))
            # Stop each lane divider at the central junction area.
            for offset in self.lane_divider_offsets_px(self.width_px):
                painter.drawLine(
                    QPointF(-self.arm_px, offset), QPointF(-half_w, offset)
                )
                painter.drawLine(
                    QPointF(half_w, offset), QPointF(self.arm_px, offset)
                )
                painter.drawLine(
                    QPointF(-offset, half_w), QPointF(-offset, self.arm_px)
                )

        # Optional lane-following guide.  The horizontal guide continues
        # through the junction; the stem guide uses the corresponding lateral
        # offset for traffic travelling outward along the stem.
        if self.guide_enabled:
            offset_px = self.resolved_guide_offset_m() * PIXELS_PER_METER
            painter.setPen(self.guide_pen())
            painter.drawLine(
                QPointF(-self.arm_px, offset_px),
                QPointF(self.arm_px, offset_px),
            )
            painter.drawLine(
                QPointF(-offset_px, 0.0),
                QPointF(-offset_px, self.arm_px),
            )

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
        data.update(
            {
                "arm_length_m": self.arm_length_m,
                "width_m": self.width_m,
                "guide_line": self.guide_dict(),
                "road_markings": self.road_marking_dict(),
            }
        )
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
        item.load_guide_dict(data.get("guide_line"))
        item.load_road_marking_dict(data.get("road_markings"))
        return item

    def selection_text(self) -> str:
        return (
            super().selection_text()
            + f"\nArm length: {self.arm_length_m:.1f} m"
            + f"\nWidth: {self.width_m:.1f} m"
        )

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

    def supports_guide_line(self) -> bool:
        return True

    def supports_road_markings(self) -> bool:
        return True

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

        # Edge A: upper horizontal and left vertical boundaries.
        if self.show_edge_a:
            painter.setPen(self.road_marking_pen("edge_a", EDGE_LINE_WIDTH_PX))
            painter.drawLine(QPointF(-self.arm_px, -edge), QPointF(-half_w, -edge))
            painter.drawLine(QPointF(half_w, -edge), QPointF(self.arm_px, -edge))
            painter.drawLine(QPointF(-edge, -self.arm_px), QPointF(-edge, -half_w))
            painter.drawLine(QPointF(-edge, half_w), QPointF(-edge, self.arm_px))

        # Edge B: lower horizontal and right vertical boundaries.
        if self.show_edge_b:
            painter.setPen(self.road_marking_pen("edge_b", EDGE_LINE_WIDTH_PX))
            painter.drawLine(QPointF(-self.arm_px, edge), QPointF(-half_w, edge))
            painter.drawLine(QPointF(half_w, edge), QPointF(self.arm_px, edge))
            painter.drawLine(QPointF(edge, -self.arm_px), QPointF(edge, -half_w))
            painter.drawLine(QPointF(edge, half_w), QPointF(edge, self.arm_px))

        if self.show_center_line:
            painter.setPen(self.road_marking_pen("center", CENTER_LINE_WIDTH_PX))
            # Separate approach markings keep the intersection center clear.
            for offset in self.lane_divider_offsets_px(self.width_px):
                painter.drawLine(
                    QPointF(-self.arm_px, offset), QPointF(-half_w, offset)
                )
                painter.drawLine(
                    QPointF(half_w, offset), QPointF(self.arm_px, offset)
                )
                painter.drawLine(
                    QPointF(-offset, -self.arm_px), QPointF(-offset, -half_w)
                )
                painter.drawLine(
                    QPointF(-offset, half_w), QPointF(-offset, self.arm_px)
                )

        # Optional guide lines across both straight approaches of the
        # intersection.  They remain editable with the same left/center/right
        # offset, width, color, and style controls as normal roads.
        if self.guide_enabled:
            offset_px = self.resolved_guide_offset_m() * PIXELS_PER_METER
            painter.setPen(self.guide_pen())
            painter.drawLine(
                QPointF(-self.arm_px, offset_px),
                QPointF(self.arm_px, offset_px),
            )
            painter.drawLine(
                QPointF(-offset_px, -self.arm_px),
                QPointF(-offset_px, self.arm_px),
            )

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
        data.update(
            {
                "arm_length_m": self.arm_length_m,
                "width_m": self.width_m,
                "guide_line": self.guide_dict(),
                "road_markings": self.road_marking_dict(),
            }
        )
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
        item.load_guide_dict(data.get("guide_line"))
        item.load_road_marking_dict(data.get("road_markings"))
        return item

    def selection_text(self) -> str:
        return (
            super().selection_text()
            + f"\nArm length: {self.arm_length_m:.1f} m"
            + f"\nWidth: {self.width_m:.1f} m"
        )


class MedianWallItem(TrackItem):
    """Straight concrete median/barrier that roads can snap flush against."""

    TYPE_NAME = "median_wall"
    DISPLAY_NAME = "Median Wall"

    def __init__(
        self,
        length_m: float = DEFAULT_MEDIAN_WALL_LENGTH_M,
        width_m: float = DEFAULT_MEDIAN_WALL_WIDTH_M,
        height_m: float = DEFAULT_MEDIAN_WALL_HEIGHT_M,
        object_id: str | None = None,
    ):
        super().__init__(object_id=object_id)
        self.length_m = max(0.5, float(length_m))
        self.width_m = max(0.05, float(width_m))
        self.height_m = max(0.05, float(height_m))
        self.setZValue(18)

    @property
    def length_px(self) -> float:
        return self.length_m * PIXELS_PER_METER

    @property
    def width_px(self) -> float:
        return self.width_m * PIXELS_PER_METER

    def boundingRect(self) -> QRectF:
        margin = 6.0
        return QRectF(
            -self.length_px / 2.0 - margin,
            -self.width_px / 2.0 - margin,
            self.length_px + margin * 2.0,
            self.width_px + margin * 2.0,
        )

    def paint(self, painter: QPainter, option, widget=None):
        rect = QRectF(
            -self.length_px / 2.0,
            -self.width_px / 2.0,
            self.length_px,
            self.width_px,
        )
        painter.setPen(QPen(QColor(120, 116, 110), 1.2))
        painter.setBrush(MEDIAN_WALL_COLOR)
        painter.drawRect(rect)

        # A narrow highlight makes the barrier readable at low zoom.
        highlight = QPen(QColor(215, 210, 200), 1.0)
        highlight.setCosmetic(True)
        painter.setPen(highlight)
        painter.drawLine(
            QPointF(-self.length_px / 2.0, 0.0),
            QPointF(self.length_px / 2.0, 0.0),
        )

        if self.isSelected():
            selection_pen = QPen(SELECTION_COLOR, SELECTION_LINE_WIDTH_PX)
            selection_pen.setCosmetic(True)
            painter.setPen(selection_pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(rect)

    def to_dict(self) -> dict:
        data = self.base_dict()
        data.update(
            {
                "length_m": float(self.length_m),
                "width_m": float(self.width_m),
                "height_m": float(self.height_m),
            }
        )
        return data

    @classmethod
    def from_dict(cls, data: dict):
        item = cls(
            length_m=float(data.get("length_m", DEFAULT_MEDIAN_WALL_LENGTH_M)),
            width_m=float(data.get("width_m", DEFAULT_MEDIAN_WALL_WIDTH_M)),
            height_m=float(data.get("height_m", DEFAULT_MEDIAN_WALL_HEIGHT_M)),
            object_id=data.get("id"),
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
            + f"\nLength: {self.length_m:.1f} m"
            + f"\nWidth: {self.width_m:.2f} m"
            + f"\nHeight: {self.height_m:.2f} m"
            + "\nRoad-edge snap: Enabled"
        )
