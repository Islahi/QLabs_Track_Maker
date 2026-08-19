"""Track graphics scene, editable-area constraints, and endpoint snapping."""

from PySide6.QtCore import QPointF, QRectF
from PySide6.QtWidgets import QGraphicsScene

from config import (
    DEFAULT_CANVAS_HEIGHT_M,
    DEFAULT_CANVAS_WIDTH_M,
    ENDPOINT_SNAP_DISTANCE_PX,
    PIXELS_PER_METER,
)
from core.geometry import endpoints_face_each_other, point_distance
from items.base import TrackItem


class TrackScene(QGraphicsScene):
    """Scene with a user-defined canvas used as the scenery-fill/design area."""

    def __init__(self, window):
        # Keep a generous scene rectangle so Open Road reference data can still
        # be viewed. The *editable* rectangle below is the actual design area.
        super().__init__(-600000, -600000, 1200000, 1200000)
        self.window = window
        self.endpoint_snap_enabled = True
        self._editable_width_m = DEFAULT_CANVAS_WIDTH_M
        self._editable_height_m = DEFAULT_CANVAS_HEIGHT_M
        self.selectionChanged.connect(self.notify_selection_or_geometry_changed)

    # ------------------------------------------------------------------
    # Editable canvas area
    # ------------------------------------------------------------------

    @property
    def editable_width_m(self) -> float:
        return self._editable_width_m

    @property
    def editable_height_m(self) -> float:
        return self._editable_height_m

    def set_editable_area_size(self, width_m: float, height_m: float):
        """Set the centered editable design area in full-scale metres."""
        self._editable_width_m = max(1.0, float(width_m))
        self._editable_height_m = max(1.0, float(height_m))
        self.update()

    def editable_area_rect(self) -> QRectF:
        width_px = self._editable_width_m * PIXELS_PER_METER
        height_px = self._editable_height_m * PIXELS_PER_METER
        return QRectF(
            -width_px / 2.0,
            -height_px / 2.0,
            width_px,
            height_px,
        )

    def constrain_item_position(self, item: TrackItem, proposed_pos: QPointF) -> QPointF:
        """Optional helper for callers that explicitly need canvas clamping.

        Normal mouse movement intentionally does not call this method; the canvas
        rectangle primarily defines where automatic scenery filling may occur.
        """
        area = self.editable_area_rect()

        # Use the item's current scene footprint and translate it to the proposed
        # position. This preserves the current rotation and custom item shape.
        current_rect = item.mapRectToScene(item.boundingRect()).boundingRect()
        delta = proposed_pos - item.pos()
        proposed_rect = current_rect.translated(delta)

        # If an item is larger than the whole canvas, keep its center at the
        # canvas center rather than oscillating between opposite edges.
        if proposed_rect.width() > area.width():
            proposed_pos.setX(area.center().x())
            proposed_rect.moveCenter(QPointF(area.center().x(), proposed_rect.center().y()))
        else:
            if proposed_rect.left() < area.left():
                shift = area.left() - proposed_rect.left()
                proposed_pos.setX(proposed_pos.x() + shift)
                proposed_rect.translate(shift, 0.0)
            if proposed_rect.right() > area.right():
                shift = area.right() - proposed_rect.right()
                proposed_pos.setX(proposed_pos.x() + shift)
                proposed_rect.translate(shift, 0.0)

        if proposed_rect.height() > area.height():
            proposed_pos.setY(area.center().y())
        else:
            if proposed_rect.top() < area.top():
                shift = area.top() - proposed_rect.top()
                proposed_pos.setY(proposed_pos.y() + shift)
                proposed_rect.translate(0.0, shift)
            if proposed_rect.bottom() > area.bottom():
                shift = area.bottom() - proposed_rect.bottom()
                proposed_pos.setY(proposed_pos.y() + shift)

        return proposed_pos

    # ------------------------------------------------------------------
    # Item helpers
    # ------------------------------------------------------------------

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

    # ------------------------------------------------------------------
    # Endpoint snapping
    # ------------------------------------------------------------------

    def snap_item_position_to_endpoint(
        self,
        moving_item: TrackItem,
        proposed_pos: QPointF,
    ) -> QPointF:
        """Return a position adjusted so compatible endpoints meet."""
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
                        best_offset = target_connection["pos"] - moving_connection["pos"]

        if best_offset is not None:
            return proposed_pos + best_offset

        return proposed_pos
