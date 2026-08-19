"""Road components from Track Editor v1.0.1."""

import math

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPainterPathStroker, QPen

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
        edge_pen = QPen(EDGE_LINE_COLOR, EDGE_LINE_WIDTH_PX)
        painter.setPen(edge_pen)

        if self.show_edge_a:
            painter.drawLine(
                QPointF(-self.length_px / 2.0, -self.width_px / 2.0 + EDGE_LINE_INSET_PX),
                QPointF(self.length_px / 2.0, -self.width_px / 2.0 + EDGE_LINE_INSET_PX),
            )

        if self.show_edge_b:
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

        if self.show_center_line:
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

        edge_pen = QPen(EDGE_LINE_COLOR, EDGE_LINE_WIDTH_PX)
        painter.setPen(edge_pen)
        if self.show_edge_a:
            painter.drawPath(self._arc_path_for_radius(outer_radius))
        if self.show_edge_b:
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
        if self.show_center_line:
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

        edge_pen = QPen(EDGE_LINE_COLOR, EDGE_LINE_WIDTH_PX)
        painter.setPen(edge_pen)
        if self.show_edge_a:
            painter.drawLine(
                QPointF(-self.length_px / 2.0, -self.width_px / 2.0 + EDGE_LINE_INSET_PX),
                QPointF(self.length_px / 2.0, -self.width_px / 2.0 + EDGE_LINE_INSET_PX),
            )
        if self.show_edge_b:
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
        if self.show_center_line:
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
        if self.show_end_bar:
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

        edge_pen = QPen(EDGE_LINE_COLOR, EDGE_LINE_WIDTH_PX)
        painter.setPen(edge_pen)

        # Edge A: upper horizontal edge + left stem side.
        if self.show_edge_a:
            painter.drawLine(QPointF(-self.arm_px, -inset_y), QPointF(self.arm_px, -inset_y))
            painter.drawLine(QPointF(-inset_x, half_w), QPointF(-inset_x, self.arm_px))

        # Edge B: lower horizontal pieces + right stem side.
        if self.show_edge_b:
            painter.drawLine(QPointF(-self.arm_px, inset_y), QPointF(-half_w, inset_y))
            painter.drawLine(QPointF(half_w, inset_y), QPointF(self.arm_px, inset_y))
            painter.drawLine(QPointF(inset_x, half_w), QPointF(inset_x, self.arm_px))

        center_pen = QPen(CENTER_LINE_COLOR, CENTER_LINE_WIDTH_PX, Qt.PenStyle.DashLine)
        painter.setPen(center_pen)
        if self.show_center_line:
            # Stop center markings at the central junction area.
            painter.drawLine(QPointF(-self.arm_px, 0.0), QPointF(-half_w, 0.0))
            painter.drawLine(QPointF(half_w, 0.0), QPointF(self.arm_px, 0.0))
            painter.drawLine(QPointF(0.0, half_w), QPointF(0.0, self.arm_px))

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

        edge_pen = QPen(EDGE_LINE_COLOR, EDGE_LINE_WIDTH_PX)
        painter.setPen(edge_pen)

        # Edge A: upper horizontal and left vertical boundaries.
        if self.show_edge_a:
            painter.drawLine(QPointF(-self.arm_px, -edge), QPointF(-half_w, -edge))
            painter.drawLine(QPointF(half_w, -edge), QPointF(self.arm_px, -edge))
            painter.drawLine(QPointF(-edge, -self.arm_px), QPointF(-edge, -half_w))
            painter.drawLine(QPointF(-edge, half_w), QPointF(-edge, self.arm_px))

        # Edge B: lower horizontal and right vertical boundaries.
        if self.show_edge_b:
            painter.drawLine(QPointF(-self.arm_px, edge), QPointF(-half_w, edge))
            painter.drawLine(QPointF(half_w, edge), QPointF(self.arm_px, edge))
            painter.drawLine(QPointF(edge, -self.arm_px), QPointF(edge, -half_w))
            painter.drawLine(QPointF(edge, half_w), QPointF(edge, self.arm_px))

        center_pen = QPen(CENTER_LINE_COLOR, CENTER_LINE_WIDTH_PX, Qt.PenStyle.DashLine)
        painter.setPen(center_pen)
        if self.show_center_line:
            # Four separate arm markings; the intersection center stays clear.
            painter.drawLine(QPointF(-self.arm_px, 0.0), QPointF(-half_w, 0.0))
            painter.drawLine(QPointF(half_w, 0.0), QPointF(self.arm_px, 0.0))
            painter.drawLine(QPointF(0.0, -self.arm_px), QPointF(0.0, -half_w))
            painter.drawLine(QPointF(0.0, half_w), QPointF(0.0, self.arm_px))

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
