"""Base class shared by all editor items."""

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QBrush, QColor, QPainter, QPen, QPolygonF
from PySide6.QtWidgets import QGraphicsItem, QGraphicsSimpleTextItem

from config import (
    GRID_PIXELS,
    DEFAULT_ROAD_WIDTH_M,
    DEFAULT_GUIDE_WIDTH_M,
    DEFAULT_GUIDE_POSITION,
    DEFAULT_GUIDE_CUSTOM_OFFSET_M,
    DEFAULT_GUIDE_COLOR,
    DEFAULT_GUIDE_RGB,
    DEFAULT_GUIDE_STYLE,
    GUIDE_COLOR_RGB,
    GUIDE_COLORS,
    CONNECTION_COLOR,
    CONNECTION_OUTLINE_COLOR,
    PIXELS_PER_METER,
    ROAD_MARKING_COLORS,
    DEFAULT_EDGE_A_MARKING_COLOR,
    DEFAULT_EDGE_A_MARKING_STYLE,
    DEFAULT_CENTER_MARKING_COLOR,
    DEFAULT_CENTER_MARKING_STYLE,
    DEFAULT_EDGE_B_MARKING_COLOR,
    DEFAULT_EDGE_B_MARKING_STYLE,
    DEFAULT_END_BAR_MARKING_COLOR,
    DEFAULT_END_BAR_MARKING_STYLE,
)
from core.geometry import (
    make_object_id,
    normalize_angle,
    scene_to_world,
    snap_value,
)

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

        # Optional road-marking visibility. Road items expose these through
        # supports_road_markings(); other scene objects simply ignore them.
        self.show_edge_a = True
        self.show_center_line = True
        self.show_edge_b = True
        self.show_end_bar = True

        self.edge_a_marking_color = DEFAULT_EDGE_A_MARKING_COLOR
        self.edge_a_marking_style = DEFAULT_EDGE_A_MARKING_STYLE
        self.center_marking_color = DEFAULT_CENTER_MARKING_COLOR
        self.center_marking_style = DEFAULT_CENTER_MARKING_STYLE
        self.edge_b_marking_color = DEFAULT_EDGE_B_MARKING_COLOR
        self.edge_b_marking_style = DEFAULT_EDGE_B_MARKING_STYLE
        self.end_bar_marking_color = DEFAULT_END_BAR_MARKING_COLOR
        self.end_bar_marking_style = DEFAULT_END_BAR_MARKING_STYLE

    def draw_facing_indicator(
        self,
        painter: QPainter,
        rect,
        *,
        axis: str = "x",
    ):
        """Draw an editor-only arrow showing the actor's exported front side.

        Actor rotations transform this local-space marker automatically. The
        marker is visual guidance only and is never serialized or exported.
        """
        painter.save()
        color = QColor(35, 190, 235)
        pen = QPen(color, 2.4)
        pen.setCosmetic(True)
        painter.setPen(pen)
        painter.setBrush(color)

        if axis == "y":
            tip = QPointF(0.0, rect.bottom() - 2.0)
            start = QPointF(0.0, min(0.0, rect.top() + rect.height() * 0.30))
            wing = max(4.0, min(8.0, rect.width() * 0.12))
            depth = max(6.0, min(11.0, rect.height() * 0.20))
            head = QPolygonF([
                tip,
                QPointF(tip.x() - wing, tip.y() - depth),
                QPointF(tip.x() + wing, tip.y() - depth),
            ])
            label_rect = rect.adjusted(3, rect.height() * 0.55, -3, -2)
        else:
            tip = QPointF(rect.right() - 2.0, 0.0)
            start = QPointF(min(0.0, rect.left() + rect.width() * 0.30), 0.0)
            wing = max(4.0, min(8.0, rect.height() * 0.12))
            depth = max(6.0, min(11.0, rect.width() * 0.20))
            head = QPolygonF([
                tip,
                QPointF(tip.x() - depth, tip.y() - wing),
                QPointF(tip.x() - depth, tip.y() + wing),
            ])
            label_rect = rect.adjusted(rect.width() * 0.48, 2, -2, -2)

        painter.drawLine(start, tip)
        painter.drawPolygon(head)

        if self.isSelected() and rect.width() >= 45 and rect.height() >= 30:
            font = painter.font()
            font.setBold(True)
            font.setPointSizeF(max(6.0, min(8.0, font.pointSizeF())))
            painter.setFont(font)
            painter.drawText(label_rect, Qt.AlignmentFlag.AlignCenter, "FRONT")
        painter.restore()

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
    # Road-marking visibility API
    # ------------------------------------------------------------

    def supports_road_markings(self) -> bool:
        return False

    def road_marking_dict(self) -> dict:
        return {
            "edge_a": bool(self.show_edge_a),
            "edge_a_color": str(self.edge_a_marking_color),
            "edge_a_style": str(self.edge_a_marking_style),
            "center": bool(self.show_center_line),
            "center_color": str(self.center_marking_color),
            "center_style": str(self.center_marking_style),
            "edge_b": bool(self.show_edge_b),
            "edge_b_color": str(self.edge_b_marking_color),
            "edge_b_style": str(self.edge_b_marking_style),
            "end_bar": bool(self.show_end_bar),
            "end_bar_color": str(self.end_bar_marking_color),
            "end_bar_style": str(self.end_bar_marking_style),
        }

    def load_road_marking_dict(self, data: dict | None):
        data = data or {}
        self.show_edge_a = bool(data.get("edge_a", True))
        self.show_center_line = bool(data.get("center", True))
        self.show_edge_b = bool(data.get("edge_b", True))
        self.show_end_bar = bool(data.get("end_bar", True))

        self.edge_a_marking_color = str(
            data.get("edge_a_color", DEFAULT_EDGE_A_MARKING_COLOR)
        )
        self.edge_a_marking_style = str(
            data.get("edge_a_style", DEFAULT_EDGE_A_MARKING_STYLE)
        )
        self.center_marking_color = str(
            data.get("center_color", DEFAULT_CENTER_MARKING_COLOR)
        )
        self.center_marking_style = str(
            data.get("center_style", DEFAULT_CENTER_MARKING_STYLE)
        )
        self.edge_b_marking_color = str(
            data.get("edge_b_color", DEFAULT_EDGE_B_MARKING_COLOR)
        )
        self.edge_b_marking_style = str(
            data.get("edge_b_style", DEFAULT_EDGE_B_MARKING_STYLE)
        )
        self.end_bar_marking_color = str(
            data.get("end_bar_color", DEFAULT_END_BAR_MARKING_COLOR)
        )
        self.end_bar_marking_style = str(
            data.get("end_bar_style", DEFAULT_END_BAR_MARKING_STYLE)
        )

    def road_marking_pen(self, key: str, width_px: float) -> QPen:
        """Return the editor pen for one configurable road marking."""
        if key == "edge_a":
            color_name = self.edge_a_marking_color
            style_name = self.edge_a_marking_style
        elif key == "center":
            color_name = self.center_marking_color
            style_name = self.center_marking_style
        elif key == "edge_b":
            color_name = self.edge_b_marking_color
            style_name = self.edge_b_marking_style
        else:
            color_name = self.end_bar_marking_color
            style_name = self.end_bar_marking_style

        color = ROAD_MARKING_COLORS.get(
            color_name, ROAD_MARKING_COLORS["white"]
        )
        style = (
            Qt.PenStyle.DashLine
            if style_name == "dashed"
            else Qt.PenStyle.SolidLine
        )
        pen = QPen(color, float(width_px), style)
        pen.setCapStyle(Qt.PenCapStyle.FlatCap)
        return pen

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
                # Deserialization constructs items before adding them to a
                # scene. Preserve those saved coordinates exactly: a road
                # endpoint snap can legitimately leave the item's origin off
                # the grid. Re-snapping here used to break connected roads
                # whenever a snapshot-based Undo rebuilt the scene.
                scene = self.scene()
                if scene is None:
                    return value

                # First snap the item's origin to the 1 m grid.
                proposed = QPointF(
                    snap_value(value.x(), GRID_PIXELS),
                    snap_value(value.y(), GRID_PIXELS),
                )

                # Then allow endpoint snapping to override the origin grid.
                if hasattr(scene, "snap_item_position"):
                    proposed = scene.snap_item_position(self, proposed)

                # The editable canvas is a fill/design boundary, not a hard
                # movement boundary. Items remain freely draggable as in v1.0.1.

                return proposed

        result = super().itemChange(change, value)

        if change in (
            QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged,
            QGraphicsItem.GraphicsItemChange.ItemSelectedHasChanged,
            QGraphicsItem.GraphicsItemChange.ItemRotationHasChanged,
        ):
            scene = self.scene()
            if scene is not None and hasattr(scene, "notify_selection_or_geometry_changed"):
                scene.notify_selection_or_geometry_changed()

        return result

    def rotate_step(self, amount_deg: float):
        self.setRotation(normalize_angle(self.rotation() + amount_deg))

        # After rotating, try a tiny endpoint re-snap without changing the
        # current center intentionally. This makes a manually aligned piece
        # settle onto a nearby connection after the correct heading is chosen.
        scene = self.scene()
        if scene is not None and hasattr(scene, "snap_item_position"):
            snapped = scene.snap_item_position(self, self.pos())
            if snapped != self.pos():
                self.setPos(snapped)
            if hasattr(scene, "notify_selection_or_geometry_changed"):
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
        from registry import create_track_item_from_dict
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
