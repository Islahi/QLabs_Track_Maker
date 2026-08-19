"""Editor-only image reference used for manual map tracing."""

from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QGraphicsItem

from config import (
    DEFAULT_REFERENCE_IMAGE_OPACITY,
    DEFAULT_REFERENCE_IMAGE_WIDTH_M,
    MIN_REFERENCE_IMAGE_SIZE_M,
    MAX_REFERENCE_IMAGE_SIZE_M,
    PIXELS_PER_METER,
    REFERENCE_IMAGE_HANDLE_PX,
    REFERENCE_IMAGE_Z,
    SELECTION_COLOR,
)
from core.geometry import normalize_angle, scene_to_world, world_to_scene
from items.base import TrackItem


class ReferenceImageItem(TrackItem):
    """Movable, resizable and rotatable editor-only image reference.

    The image is intentionally a TrackItem so it participates in save/load and
    undo, but the QLabs exporter ignores this TYPE_NAME.
    """

    TYPE_NAME = "reference_image"
    DISPLAY_NAME = "Reference Image"

    def __init__(
        self,
        image_path: str = "",
        width_m: float = DEFAULT_REFERENCE_IMAGE_WIDTH_M,
        height_m: float | None = None,
        object_id: str | None = None,
    ):
        super().__init__(object_id=object_id)

        self.image_path = str(image_path or "")
        self.image_opacity = float(DEFAULT_REFERENCE_IMAGE_OPACITY)
        self.lock_aspect_ratio = True
        self.lock_position = False

        self._pixmap = QPixmap()
        self._resizing = False

        self.reload_pixmap()

        native_aspect = self.native_aspect_ratio()
        self.width_m = max(
            MIN_REFERENCE_IMAGE_SIZE_M,
            min(MAX_REFERENCE_IMAGE_SIZE_M, float(width_m)),
        )

        if height_m is None:
            height_m = self.width_m / max(native_aspect, 1e-9)

        self.height_m = max(
            MIN_REFERENCE_IMAGE_SIZE_M,
            min(MAX_REFERENCE_IMAGE_SIZE_M, float(height_m)),
        )

        # Keep the tracing image behind every normal editor object.
        self.setZValue(REFERENCE_IMAGE_Z)

        # Reference images should be positionable more precisely than the
        # normal 1 m item grid, so itemChange below deliberately bypasses
        # TrackItem's grid snapping.
        self.setFlag(
            QGraphicsItem.GraphicsItemFlag.ItemIsMovable,
            True,
        )

    # ------------------------------------------------------------------
    # Image data
    # ------------------------------------------------------------------

    def reload_pixmap(self):
        if self.image_path:
            self._pixmap = QPixmap(self.image_path)
        else:
            self._pixmap = QPixmap()
        self.update()

    def set_image_path(self, image_path: str):
        self.image_path = str(image_path or "")
        self.reload_pixmap()

    def native_aspect_ratio(self) -> float:
        if not self._pixmap.isNull() and self._pixmap.height() > 0:
            return self._pixmap.width() / self._pixmap.height()
        if getattr(self, "height_m", 0.0) > 0:
            return float(self.width_m) / float(self.height_m)
        return 1.0

    def set_dimensions_m(self, width_m: float, height_m: float):
        width_m = max(
            MIN_REFERENCE_IMAGE_SIZE_M,
            min(MAX_REFERENCE_IMAGE_SIZE_M, float(width_m)),
        )
        height_m = max(
            MIN_REFERENCE_IMAGE_SIZE_M,
            min(MAX_REFERENCE_IMAGE_SIZE_M, float(height_m)),
        )

        self.prepareGeometryChange()
        self.width_m = width_m
        self.height_m = height_m
        self.update()

    def set_position_locked(self, locked: bool):
        self.lock_position = bool(locked)
        self.setFlag(
            QGraphicsItem.GraphicsItemFlag.ItemIsMovable,
            not self.lock_position,
        )
        self.update()

    # ------------------------------------------------------------------
    # Geometry / painting
    # ------------------------------------------------------------------

    @property
    def width_px(self) -> float:
        return self.width_m * PIXELS_PER_METER

    @property
    def height_px(self) -> float:
        return self.height_m * PIXELS_PER_METER

    def boundingRect(self) -> QRectF:
        margin = REFERENCE_IMAGE_HANDLE_PX + 4.0
        return QRectF(
            -self.width_px / 2.0 - margin,
            -self.height_px / 2.0 - margin,
            self.width_px + 2.0 * margin,
            self.height_px + 2.0 * margin,
        )

    def image_rect(self) -> QRectF:
        return QRectF(
            -self.width_px / 2.0,
            -self.height_px / 2.0,
            self.width_px,
            self.height_px,
        )

    def resize_handle_rect(self) -> QRectF:
        rect = self.image_rect()
        size = float(REFERENCE_IMAGE_HANDLE_PX)
        return QRectF(
            rect.right() - size / 2.0,
            rect.bottom() - size / 2.0,
            size,
            size,
        )

    def paint(self, painter: QPainter, option, widget=None):
        rect = self.image_rect()

        painter.save()
        painter.setOpacity(max(0.05, min(1.0, self.image_opacity)))

        if not self._pixmap.isNull():
            painter.drawPixmap(
                rect,
                self._pixmap,
                QRectF(self._pixmap.rect()),
            )
        else:
            painter.setPen(QPen(QColor(170, 90, 90), 2))
            painter.setBrush(QColor(75, 45, 45, 180))
            painter.drawRect(rect)
            painter.drawLine(rect.topLeft(), rect.bottomRight())
            painter.drawLine(rect.topRight(), rect.bottomLeft())

        painter.restore()

        if self.isSelected():
            pen = QPen(SELECTION_COLOR, 2.0)
            pen.setCosmetic(True)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(rect)

            if not self.lock_position:
                painter.setBrush(SELECTION_COLOR)
                painter.drawRect(self.resize_handle_rect())

    # ------------------------------------------------------------------
    # Interaction
    # ------------------------------------------------------------------

    def itemChange(self, change, value):
        # Bypass TrackItem's 1 m movement snapping for reference images.
        result = QGraphicsItem.itemChange(self, change, value)

        if change in (
            QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged,
            QGraphicsItem.GraphicsItemChange.ItemSelectedHasChanged,
            QGraphicsItem.GraphicsItemChange.ItemRotationHasChanged,
        ):
            scene = self.scene()
            if scene is not None and hasattr(
                scene,
                "notify_selection_or_geometry_changed",
            ):
                scene.notify_selection_or_geometry_changed()

        return result

    def mousePressEvent(self, event):
        if (
            event.button() == Qt.MouseButton.LeftButton
            and self.isSelected()
            and not self.lock_position
            and self.resize_handle_rect().contains(event.pos())
        ):
            self._resizing = True
            scene = self.scene()
            if (
                scene is not None
                and hasattr(scene, "window")
                and hasattr(scene.window, "_begin_undo_transaction")
            ):
                scene.window._begin_undo_transaction(
                    "Resize reference image"
                )
            event.accept()
            return

        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if not self._resizing:
            super().mouseMoveEvent(event)
            return

        local_pos = event.pos()

        new_width_m = max(
            MIN_REFERENCE_IMAGE_SIZE_M,
            2.0 * max(1.0, local_pos.x()) / PIXELS_PER_METER,
        )

        if self.lock_aspect_ratio:
            aspect = max(self.native_aspect_ratio(), 1e-9)
            new_height_m = new_width_m / aspect
        else:
            new_height_m = max(
                MIN_REFERENCE_IMAGE_SIZE_M,
                2.0 * max(1.0, local_pos.y()) / PIXELS_PER_METER,
            )

        self.set_dimensions_m(
            min(new_width_m, MAX_REFERENCE_IMAGE_SIZE_M),
            min(new_height_m, MAX_REFERENCE_IMAGE_SIZE_M),
        )

        scene = self.scene()
        if (
            scene is not None
            and hasattr(scene, "notify_selection_or_geometry_changed")
        ):
            scene.notify_selection_or_geometry_changed()

        event.accept()

    def mouseReleaseEvent(self, event):
        if self._resizing:
            self._resizing = False
            scene = self.scene()
            if (
                scene is not None
                and hasattr(scene, "window")
                and hasattr(scene.window, "_commit_undo_transaction")
            ):
                scene.window._commit_undo_transaction()
            event.accept()
            return

        super().mouseReleaseEvent(event)

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def to_dict(self) -> dict:
        data = self.base_dict()
        data.update(
            {
                "image_path": self.image_path,
                "width_m": round(float(self.width_m), 4),
                "height_m": round(float(self.height_m), 4),
                "opacity": round(float(self.image_opacity), 4),
                "lock_aspect_ratio": bool(self.lock_aspect_ratio),
                "lock_position": bool(self.lock_position),
                "editor_only": True,
            }
        )
        return data

    @classmethod
    def from_dict(cls, data: dict):
        item = cls(
            image_path=str(data.get("image_path", "")),
            width_m=float(
                data.get(
                    "width_m",
                    DEFAULT_REFERENCE_IMAGE_WIDTH_M,
                )
            ),
            height_m=float(
                data.get(
                    "height_m",
                    DEFAULT_REFERENCE_IMAGE_WIDTH_M,
                )
            ),
            object_id=data.get("id"),
        )

        item.image_opacity = max(
            0.05,
            min(1.0, float(data.get("opacity", DEFAULT_REFERENCE_IMAGE_OPACITY))),
        )
        item.lock_aspect_ratio = bool(
            data.get("lock_aspect_ratio", True)
        )
        item.set_position_locked(
            bool(data.get("lock_position", False))
        )

        item.setPos(
            world_to_scene(
                float(data.get("x", 0.0)),
                float(data.get("y", 0.0)),
            )
        )
        item.setRotation(
            float(data.get("rotation_deg", 0.0))
        )
        return item

    def selection_text(self) -> str:
        x_m, y_m = scene_to_world(self.pos())
        file_name = (
            Path(self.image_path).name
            if self.image_path
            else "missing image"
        )

        return (
            f"{self.DISPLAY_NAME}\n"
            f"File: {file_name}\n"
            f"X: {x_m:.2f} m\n"
            f"Y: {y_m:.2f} m\n"
            f"Angle: {normalize_angle(self.rotation()):.2f}°\n"
            f"Size: {self.width_m:.2f} × {self.height_m:.2f} m\n"
            f"Opacity: {self.image_opacity:.2f}\n"
            "Editor only — not exported to QLabs"
        )
