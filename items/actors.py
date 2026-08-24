"""Traffic, roadside, and simple environment editor actors."""

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPen, QPolygonF
from PySide6.QtWidgets import QGraphicsEllipseItem, QGraphicsItem

from config import (
    ACTOR_MARKER_SIZE_M,
    CROSSWALK_MARKER_LENGTH_M,
    CROSSWALK_MARKER_WIDTH_M,
    DEFAULT_BUILDING_LENGTH_M,
    DEFAULT_BUILDING_WIDTH_M,
    DEFAULT_BUILDING_HEIGHT_M,
    DEFAULT_BUILDING_RGB,
    PIXELS_PER_METER,
    SELECTION_COLOR,
    SELECTION_LINE_WIDTH_PX,
)
from core.geometry import world_to_scene
from core.traffic_sign_catalog import (
    DEFAULT_TRAFFIC_SIGN_KEY,
    TRAFFIC_SIGN_META,
    TRAFFIC_SIGN_KEYS,
    traffic_sign_display,
)
from items.base import TrackItem

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


class _ActorResizeHandle(QGraphicsEllipseItem):
    """Canvas corner handle shared by resizable actors and scenery."""

    RADIUS_PX = 7.0

    def __init__(self, owner: "ResizableSceneActorItem"):
        radius = self.RADIUS_PX
        super().__init__(-radius, -radius, radius * 2.0, radius * 2.0, owner)
        self.owner = owner
        self._dragging = False
        self.is_control_handle = True
        self.setFlag(
            QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations,
            True,
        )
        self.setZValue(6000)
        self.setPen(QPen(QColor(245, 250, 252), 1.5))
        self.setBrush(QColor(40, 185, 225))
        self.setCursor(Qt.CursorShape.SizeFDiagCursor)
        self.setToolTip("Drag to resize. Use the inspector for exact values.")

    def mousePressEvent(self, event):
        self.owner.setSelected(True)
        if event.button() == Qt.MouseButton.LeftButton:
            self._dragging = True
            scene = self.scene()
            if scene is not None and hasattr(scene, "window"):
                scene.window.begin_canvas_undo(f"Resize {self.owner.DISPLAY_NAME}")
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._dragging:
            self.owner.resize_from_handle(self.owner.mapFromScene(event.scenePos()))
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


class ResizableSceneActorItem(SceneActorItem):
    """Scene actor with a selected-only lower-right resize handle."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._resize_handle = _ActorResizeHandle(self)
        self._resize_handle.setVisible(False)

    def resize_rect_local(self) -> QRectF:
        return self.boundingRect()

    def sync_resize_handle(self):
        handle = getattr(self, "_resize_handle", None)
        if handle is not None:
            handle.setPos(self.resize_rect_local().bottomRight())

    def resize_from_handle(self, point: QPointF):
        raise NotImplementedError

    def _resized_on_canvas(self):
        self.sync_resize_handle()
        self.update()
        scene = self.scene()
        if scene is not None:
            scene.update()
            if hasattr(scene, "notify_selection_or_geometry_changed"):
                scene.notify_selection_or_geometry_changed()

    def itemChange(self, change, value):
        result = super().itemChange(change, value)
        if change == QGraphicsItem.GraphicsItemChange.ItemSelectedHasChanged:
            handle = getattr(self, "_resize_handle", None)
            if handle is not None:
                handle.setVisible(bool(value))
                if bool(value):
                    self.sync_resize_handle()
        return result

class TrafficLightItem(SceneActorItem):
    TYPE_NAME = "traffic_light"
    DISPLAY_NAME = "Traffic Light"
    QLABS_ORIENTATION_AXIS = "y"

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

        # Indicate the direction seen by approaching traffic, matching the
        # sign FRONT arrows. The native boom itself extends along local -X,
        # while its signal face looks along local +Y in editor coordinates.
        self.draw_facing_indicator(
            painter,
            rect,
            axis=self.QLABS_ORIENTATION_AXIS,
        )

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

        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, self.SIGN_TEXT)
        self.draw_facing_indicator(painter, rect, axis="x")

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

class CatalogTrafficSignItem(SceneActorItem):
    """One of the Plane-validated custom traffic signs.

    Native QLabs Stop, Yield, and Roundabout signs are separate actor types.
    This item is reserved for the custom BasicShape signs developed and tested
    in this project.
    """

    TYPE_NAME = "traffic_sign_catalog"
    DISPLAY_NAME = "Traffic Sign"
    QLABS_ORIENTATION_AXIS = "-x"

    def __init__(self, object_id: str | None = None):
        super().__init__(object_id=object_id)
        self.sign_type = DEFAULT_TRAFFIC_SIGN_KEY
        self.enable_identifier_label(
            ACTOR_MARKER_SIZE_M * PIXELS_PER_METER / 2.0 + 6.0
        )

    def boundingRect(self) -> QRectF:
        s = ACTOR_MARKER_SIZE_M * PIXELS_PER_METER
        return QRectF(-s / 2, -s / 2, s, s)

    def paint(self, painter: QPainter, option, widget=None):
        rect = self.boundingRect().adjusted(5, 5, -5, -5)
        meta = TRAFFIC_SIGN_META.get(
            self.sign_type,
            TRAFFIC_SIGN_META[DEFAULT_TRAFFIC_SIGN_KEY],
        )
        family = meta["family"]

        painter.setPen(QPen(QColor(238, 238, 238), 2))
        painter.setBrush(QColor(245, 245, 240))

        if family == "warning":
            painter.setPen(QPen(QColor(215, 60, 55), 3))
            painter.setBrush(QColor(250, 245, 225))
            painter.drawPolygon(
                QPolygonF([
                    QPointF(0, rect.top() + 2),
                    QPointF(rect.right() - 2, rect.bottom() - 2),
                    QPointF(rect.left() + 2, rect.bottom() - 2),
                ])
            )
        elif family == "mandatory":
            painter.setPen(QPen(QColor(235, 235, 235), 1.5))
            painter.setBrush(QColor(45, 105, 190))
            painter.drawEllipse(rect)
        elif family == "parking":
            painter.setPen(QPen(QColor(235, 235, 235), 1.5))
            painter.setBrush(QColor(35, 115, 190))
            painter.drawRect(rect)
        else:  # prohibition / speed
            painter.setPen(QPen(QColor(205, 45, 45), 3))
            painter.setBrush(QColor(248, 248, 240))
            painter.drawEllipse(rect)

        # Symbol/text marker.  QLabs geometry uses its own compact symbol set.
        if family == "mandatory":
            painter.setPen(QPen(QColor(250, 250, 250), 1.3))
        else:
            painter.setPen(QPen(QColor(25, 25, 25), 1.3))
        font = painter.font()
        font.setBold(True)
        font.setPointSizeF(max(6.0, font.pointSizeF() - 1.0))
        painter.setFont(font)
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, str(meta["short"]))

        # Red slash for selected prohibition signs where it helps readability.
        if family == "prohibition" and self.sign_type in {
            "no_u_turn", "no_parking"
        }:
            painter.setPen(QPen(QColor(210, 45, 45), 3))
            painter.drawLine(rect.bottomLeft(), rect.topRight())

        # The custom BasicShape sign face is built toward local -X by the
        # exporter (_asg_world uses -tangent for its visible/front surface).
        self.draw_facing_indicator(
            painter,
            rect,
            axis=self.QLABS_ORIENTATION_AXIS,
        )

        if self.isSelected():
            pen = QPen(SELECTION_COLOR, SELECTION_LINE_WIDTH_PX)
            pen.setCosmetic(True)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(rect.adjusted(-3, -3, 3, 3))

    def to_dict(self) -> dict:
        data = self.actor_dict()
        data["sign_type"] = self.sign_type
        return data

    @classmethod
    def from_dict(cls, data: dict):
        item = cls(object_id=data.get("id"))
        item.load_actor_dict(data)
        item.sign_type = str(data.get("sign_type", DEFAULT_TRAFFIC_SIGN_KEY))
        if item.sign_type not in TRAFFIC_SIGN_KEYS:
            item.sign_type = DEFAULT_TRAFFIC_SIGN_KEY
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
            + f"\nSign: {traffic_sign_display(self.sign_type)}"
        )


class CrosswalkItem(ResizableSceneActorItem):
    TYPE_NAME = "crosswalk"
    DISPLAY_NAME = "Crosswalk"

    def __init__(
        self,
        object_id: str | None = None,
        length_m: float = CROSSWALK_MARKER_LENGTH_M,
        width_m: float = CROSSWALK_MARKER_WIDTH_M,
    ):
        self.length_m = max(0.25, float(length_m))
        self.width_m = max(0.25, float(width_m))
        super().__init__(object_id=object_id)
        self.sync_resize_handle()

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

    def resize_from_handle(self, point: QPointF):
        self.prepareGeometryChange()
        self.length_m = max(0.25, abs(float(point.x())) * 2.0 / PIXELS_PER_METER)
        self.width_m = max(0.25, abs(float(point.y())) * 2.0 / PIXELS_PER_METER)
        self._resized_on_canvas()

    def to_dict(self) -> dict:
        data = self.actor_dict()
        data.update({
            "length_m": round(float(self.length_m), 4),
            "width_m": round(float(self.width_m), 4),
        })
        return data

    @classmethod
    def from_dict(cls, data: dict):
        item = cls(
            object_id=data.get("id"),
            length_m=float(data.get("length_m", CROSSWALK_MARKER_LENGTH_M)),
            width_m=float(data.get("width_m", CROSSWALK_MARKER_WIDTH_M)),
        )
        item.load_actor_dict(data)
        item.setPos(world_to_scene(float(data.get("x", 0.0)), float(data.get("y", 0.0))))
        item.setRotation(float(data.get("rotation_deg", 0.0)))
        item.sync_resize_handle()
        return item

    def selection_text(self) -> str:
        return (
            super().selection_text()
            + f"\nConfiguration: {self.configuration}"
            + f"\nSpan: {self.length_m:.2f} m"
            + f"\nDepth: {self.width_m:.2f} m"
            + "\nDrag the cyan corner handle to resize"
        )

class BuildingBoxItem(ResizableSceneActorItem):
    TYPE_NAME = "building_box"
    DISPLAY_NAME = "Building / Box"

    def __init__(self, object_id: str | None = None):
        super().__init__(object_id=object_id)
        self.length_m = DEFAULT_BUILDING_LENGTH_M
        self.width_m = DEFAULT_BUILDING_WIDTH_M
        self.height_m = DEFAULT_BUILDING_HEIGHT_M
        self.rgb = tuple(DEFAULT_BUILDING_RGB)
        self.sync_resize_handle()

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
        self.draw_facing_indicator(painter, rect, axis="y")

        if self.isSelected():
            pen = QPen(SELECTION_COLOR, SELECTION_LINE_WIDTH_PX)
            pen.setCosmetic(True)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(rect)

    def resize_from_handle(self, point: QPointF):
        self.prepareGeometryChange()
        self.length_m = max(0.1, abs(float(point.x())) * 2.0 / PIXELS_PER_METER)
        self.width_m = max(0.1, abs(float(point.y())) * 2.0 / PIXELS_PER_METER)
        self._resized_on_canvas()

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
        item.sync_resize_handle()
        return item

    def selection_text(self) -> str:
        return (
            super().selection_text()
            + f"\nLength: {self.length_m:.1f} m"
            + f"\nWidth: {self.width_m:.1f} m"
            + f"\nHeight: {self.height_m:.1f} m"
            + f"\nRGB: {self.rgb[0]}, {self.rgb[1]}, {self.rgb[2]}"
            + "\nDrag the cyan corner handle to resize"
        )
