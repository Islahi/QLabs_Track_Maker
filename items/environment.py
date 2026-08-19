"""Reusable building and park scenery items for the 2-D editor.

These items represent composite QLabs scenery assembled from QLabsBasicShape
actors by the standalone exporter.  The editor intentionally draws a compact
symbolic footprint rather than every individual cube/sphere/cone part.
"""

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPen

from config import PIXELS_PER_METER, SELECTION_COLOR, SELECTION_LINE_WIDTH_PX
from core.geometry import world_to_scene
from items.actors import SceneActorItem


class EnvironmentAssetItem(SceneActorItem):
    """Base class for fixed-design composite scenery assets."""

    TYPE_NAME = "environment_asset"
    DISPLAY_NAME = "Environment Asset"
    FOOTPRINT_LENGTH_M = 2.0
    FOOTPRINT_WIDTH_M = 2.0
    MARKER_COLOR = QColor(105, 120, 110)
    MARKER_KIND = "box"
    MARKER_TEXT = ""

    def __init__(self, object_id: str | None = None):
        super().__init__(object_id=object_id)
        # True only for scenery created by the automatic fill service. This is
        # persisted so generated scenery can be identified later without
        # confusing it with experiment/traffic actors.
        self.auto_generated = False

    @property
    def length_px(self) -> float:
        return self.FOOTPRINT_LENGTH_M * PIXELS_PER_METER

    @property
    def width_px(self) -> float:
        return self.FOOTPRINT_WIDTH_M * PIXELS_PER_METER

    def boundingRect(self) -> QRectF:
        margin = 5.0
        return QRectF(
            -self.length_px / 2.0 - margin,
            -self.width_px / 2.0 - margin,
            self.length_px + 2.0 * margin,
            self.width_px + 2.0 * margin,
        )

    def _asset_rect(self) -> QRectF:
        return QRectF(
            -self.length_px / 2.0,
            -self.width_px / 2.0,
            self.length_px,
            self.width_px,
        )

    def paint(self, painter: QPainter, option, widget=None):
        rect = self._asset_rect()
        kind = self.MARKER_KIND

        painter.setPen(QPen(QColor(48, 52, 56), 2))
        painter.setBrush(self.MARKER_COLOR)

        if kind == "tree":
            canopy_r = min(rect.width(), rect.height()) * 0.36
            painter.setBrush(QColor(55, 145, 70))
            painter.drawEllipse(QPointF(0, 0), canopy_r, canopy_r)
            painter.setBrush(QColor(88, 57, 35))
            painter.drawEllipse(QPointF(0, 0), 3.5, 3.5)

        elif kind == "pine":
            painter.setBrush(QColor(42, 112, 58))
            triangle = [
                QPointF(0, rect.top() + 2),
                QPointF(rect.right() - 2, rect.bottom() - 2),
                QPointF(rect.left() + 2, rect.bottom() - 2),
            ]
            from PySide6.QtGui import QPolygonF
            painter.drawPolygon(QPolygonF(triangle))
            painter.setBrush(QColor(88, 57, 35))
            painter.drawRect(QRectF(-3, -2, 6, rect.height() * 0.35))

        elif kind == "bench":
            painter.setBrush(QColor(139, 84, 40))
            seat = QRectF(rect.left() + 3, -4, rect.width() - 6, 8)
            painter.drawRoundedRect(seat, 2, 2)
            painter.setPen(QPen(QColor(55, 55, 58), 2))
            painter.drawLine(QPointF(rect.left() + 7, 4), QPointF(rect.left() + 7, rect.bottom() - 2))
            painter.drawLine(QPointF(rect.right() - 7, 4), QPointF(rect.right() - 7, rect.bottom() - 2))

        elif kind == "lamp":
            painter.setPen(QPen(QColor(65, 68, 72), 3))
            painter.drawLine(QPointF(0, rect.bottom() - 2), QPointF(0, rect.top() + 6))
            painter.setPen(QPen(QColor(80, 80, 82), 1.5))
            painter.setBrush(QColor(244, 225, 145))
            painter.drawEllipse(QPointF(0, rect.top() + 4), 6, 6)

        elif kind == "bin":
            painter.setBrush(QColor(35, 105, 65))
            painter.drawRoundedRect(rect.adjusted(3, 2, -3, -2), 2, 2)
            painter.setPen(QPen(QColor(30, 32, 34), 2))
            painter.drawLine(QPointF(rect.left() + 4, rect.top() + 4), QPointF(rect.right() - 4, rect.top() + 4))

        elif kind == "planter":
            painter.setBrush(QColor(139, 82, 45))
            painter.drawRect(rect)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(55, 145, 70))
            painter.drawEllipse(QPointF(-rect.width() * 0.20, 0), 7, 7)
            painter.drawEllipse(QPointF(rect.width() * 0.18, 0), 8, 8)

        elif kind == "fountain":
            painter.setBrush(QColor(115, 120, 125))
            painter.drawRect(rect)
            painter.setPen(QPen(QColor(95, 180, 230), 2))
            painter.setBrush(QColor(65, 140, 205))
            inner = rect.adjusted(5, 5, -5, -5)
            painter.drawEllipse(inner)
            painter.setBrush(QColor(190, 190, 185))
            painter.drawEllipse(QPointF(0, 0), 4, 4)

        elif kind == "tower":
            # Top-down stepped footprint with an obvious front entrance and
            # facade glazing. The standalone QLabs exporter mirrors this with
            # real BasicShape doors/windows on the stepped tower.
            painter.setBrush(self.MARKER_COLOR)
            painter.setPen(QPen(QColor(48, 52, 56), 2))
            painter.drawRect(rect)
            painter.setBrush(QColor(72, 82, 101))
            painter.drawRect(rect.adjusted(6, 6, -6, -6))
            painter.setBrush(QColor(61, 72, 92))
            painter.drawRect(rect.adjusted(12, 12, -12, -12))

            # Front edge is the local bottom side.
            painter.setPen(QPen(QColor(220, 225, 230), 1))
            painter.drawLine(rect.bottomLeft(), rect.bottomRight())
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(175, 210, 230))
            for x in (-rect.width() * 0.30, rect.width() * 0.30):
                painter.drawRect(QRectF(x - 3, rect.top() + 5, 6, 4))
                painter.drawRect(QRectF(x - 3, rect.bottom() - 11, 6, 4))
            painter.setBrush(QColor(45, 38, 32))
            painter.drawRect(QRectF(-5, rect.bottom() - 7, 10, 7))
            painter.setPen(QPen(QColor(245, 245, 245), 1))
            painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, self.MARKER_TEXT)

        else:
            # Building marker: footprint, front edge, and simple window grid.
            painter.drawRect(rect)
            painter.setPen(QPen(QColor(220, 225, 230), 1))
            painter.drawLine(rect.bottomLeft(), rect.bottomRight())
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(175, 210, 230))
            usable_w = max(10.0, rect.width() - 12.0)
            for column in range(3):
                x = rect.left() + 6.0 + column * usable_w / 3.0
                painter.drawRect(QRectF(x, rect.top() + 6, 5, 5))
            if self.MARKER_TEXT:
                painter.setPen(QPen(QColor(245, 245, 245), 1))
                painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, self.MARKER_TEXT)

        if self.isSelected():
            pen = QPen(SELECTION_COLOR, SELECTION_LINE_WIDTH_PX)
            pen.setCosmetic(True)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(rect.adjusted(-2, -2, 2, 2))

    def to_dict(self) -> dict:
        data = self.actor_dict()
        if self.auto_generated:
            data["auto_generated"] = True
        return data

    @classmethod
    def from_dict(cls, data: dict):
        item = cls(object_id=data.get("id"))
        item.load_actor_dict(data)
        item.auto_generated = bool(data.get("auto_generated", False))
        item.setPos(
            world_to_scene(
                float(data.get("x", 0.0)),
                float(data.get("y", 0.0)),
            )
        )
        item.setRotation(float(data.get("rotation_deg", 0.0)))
        return item

    def selection_text(self) -> str:
        text = super().selection_text() + "\nStatic composite BasicShape asset"
        if self.auto_generated:
            text += "\nGenerated by scenery fill"
        return text


# ---------------------------------------------------------------------------
# Building gallery
# ---------------------------------------------------------------------------

class OfficeBuildingItem(EnvironmentAssetItem):
    TYPE_NAME = "office_building"
    DISPLAY_NAME = "Office Building"
    FOOTPRINT_LENGTH_M = 4.5
    FOOTPRINT_WIDTH_M = 4.0
    MARKER_COLOR = QColor(52, 82, 115)
    MARKER_TEXT = "OFF"


class ApartmentBuildingItem(EnvironmentAssetItem):
    TYPE_NAME = "apartment_building"
    DISPLAY_NAME = "Apartment Building"
    FOOTPRINT_LENGTH_M = 6.0
    FOOTPRINT_WIDTH_M = 4.5
    MARKER_COLOR = QColor(166, 143, 108)
    MARKER_TEXT = "APT"


class ShopBuildingItem(EnvironmentAssetItem):
    TYPE_NAME = "shop_building"
    DISPLAY_NAME = "Commercial Shop"
    FOOTPRINT_LENGTH_M = 6.0
    FOOTPRINT_WIDTH_M = 5.0
    MARKER_COLOR = QColor(145, 48, 45)
    MARKER_TEXT = "SHOP"


class SteppedTowerItem(EnvironmentAssetItem):
    TYPE_NAME = "stepped_tower"
    DISPLAY_NAME = "Stepped Tower"
    FOOTPRINT_LENGTH_M = 5.5
    FOOTPRINT_WIDTH_M = 5.5
    MARKER_COLOR = QColor(83, 91, 108)
    MARKER_KIND = "tower"
    MARKER_TEXT = "TWR"


# ---------------------------------------------------------------------------
# Park gallery
# ---------------------------------------------------------------------------

class RoundTreeItem(EnvironmentAssetItem):
    TYPE_NAME = "round_tree"
    DISPLAY_NAME = "Round Tree"
    FOOTPRINT_LENGTH_M = 2.8
    FOOTPRINT_WIDTH_M = 2.8
    MARKER_KIND = "tree"


class PineTreeItem(EnvironmentAssetItem):
    TYPE_NAME = "pine_tree"
    DISPLAY_NAME = "Pine Tree"
    FOOTPRINT_LENGTH_M = 2.8
    FOOTPRINT_WIDTH_M = 2.8
    MARKER_KIND = "pine"


class ParkBenchItem(EnvironmentAssetItem):
    TYPE_NAME = "park_bench"
    DISPLAY_NAME = "Park Bench"
    FOOTPRINT_LENGTH_M = 2.4
    FOOTPRINT_WIDTH_M = 0.8
    MARKER_KIND = "bench"


class LampPostItem(EnvironmentAssetItem):
    TYPE_NAME = "lamp_post"
    DISPLAY_NAME = "Lamp Post"
    FOOTPRINT_LENGTH_M = 0.8
    FOOTPRINT_WIDTH_M = 0.8
    MARKER_KIND = "lamp"


class TrashBinItem(EnvironmentAssetItem):
    TYPE_NAME = "trash_bin"
    DISPLAY_NAME = "Trash Bin"
    FOOTPRINT_LENGTH_M = 0.8
    FOOTPRINT_WIDTH_M = 0.8
    MARKER_KIND = "bin"


class PlanterItem(EnvironmentAssetItem):
    TYPE_NAME = "planter"
    DISPLAY_NAME = "Planter"
    FOOTPRINT_LENGTH_M = 2.0
    FOOTPRINT_WIDTH_M = 1.2
    MARKER_KIND = "planter"


class FountainItem(EnvironmentAssetItem):
    TYPE_NAME = "fountain"
    DISPLAY_NAME = "Fountain"
    FOOTPRINT_LENGTH_M = 3.5
    FOOTPRINT_WIDTH_M = 3.5
    MARKER_KIND = "fountain"
