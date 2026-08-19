"""Primary QCar2 start marker."""

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen

from config import (
    QCAR2_DESIGN_LENGTH_M,
    QCAR2_DESIGN_WIDTH_M,
    QCAR_CAMERA_THIRD_PERSON,
    QCAR_CAMERA_FIRST_PERSON,
    PIXELS_PER_METER,
    SELECTION_COLOR,
    SELECTION_LINE_WIDTH_PX,
)
from core.geometry import world_to_scene
from items.base import TrackItem

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
