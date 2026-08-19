"""Track graphics scene, editable-area constraints, and endpoint snapping."""

import math

from PySide6.QtCore import QPointF, QRectF
from PySide6.QtWidgets import QGraphicsScene

from config import (
    DEFAULT_CANVAS_HEIGHT_M,
    DEFAULT_CANVAS_WIDTH_M,
    ENDPOINT_SNAP_DISTANCE_PX,
    PIXELS_PER_METER,
    WALL_SNAP_DISTANCE_PX,
    SNAP_HEADING_TOLERANCE_DEG,
)
from core.geometry import endpoints_face_each_other, point_distance
from items.base import TrackItem
from items.roads import StraightRoadItem, RoadEndItem, MedianWallItem


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
    # Combined snapping
    # ------------------------------------------------------------------

    def snap_item_position(
        self,
        moving_item: TrackItem,
        proposed_pos: QPointF,
    ) -> QPointF:
        """Apply endpoint snapping first, then road-to-median side snapping."""
        snapped = self.snap_item_position_to_endpoint(moving_item, proposed_pos)
        return self.snap_item_position_to_wall(moving_item, snapped)

    @staticmethod
    def _parallel_rotation(a_deg: float, b_deg: float) -> bool:
        # A road and wall are parallel when their long axes are either aligned
        # or reversed.  Re-use the normal editor heading tolerance.
        difference = abs((float(a_deg) - float(b_deg) + 180.0) % 360.0 - 180.0)
        difference = min(difference, abs(180.0 - difference))
        return difference <= SNAP_HEADING_TOLERANCE_DEG

    @staticmethod
    def _axis_vectors(rotation_deg: float) -> tuple[QPointF, QPointF]:
        angle = math.radians(float(rotation_deg))
        tangent = QPointF(math.cos(angle), math.sin(angle))
        normal = QPointF(-math.sin(angle), math.cos(angle))
        return tangent, normal

    def snap_item_position_to_wall(
        self,
        moving_item: TrackItem,
        proposed_pos: QPointF,
    ) -> QPointF:
        """Snap a straight road edge flush to a median wall (or vice versa).

        The snap changes only the perpendicular coordinate; longitudinal
        placement is preserved.  This lets two carriageways sit cleanly on
        opposite sides of one median barrier without changing their lengths.
        """
        if not self.endpoint_snap_enabled:
            return proposed_pos

        road_types = (StraightRoadItem, RoadEndItem)
        moving_is_road = isinstance(moving_item, road_types)
        moving_is_wall = isinstance(moving_item, MedianWallItem)
        if not (moving_is_road or moving_is_wall):
            return proposed_pos

        best_distance = WALL_SNAP_DISTANCE_PX + 1.0
        best_position = None

        for target in self.track_items():
            if target is moving_item:
                continue

            if moving_is_road and not isinstance(target, MedianWallItem):
                continue
            if moving_is_wall and not isinstance(target, road_types):
                continue
            if not self._parallel_rotation(moving_item.rotation(), target.rotation()):
                continue

            wall = target if moving_is_road else moving_item
            road = moving_item if moving_is_road else target

            # Use the wall long axis as the shared tangent/normal frame.
            tangent, normal = self._axis_vectors(wall.rotation())
            wall_center = target.pos() if moving_is_road else proposed_pos
            road_center = proposed_pos if moving_is_road else target.pos()

            delta = road_center - wall_center
            along = delta.x() * tangent.x() + delta.y() * tangent.y()

            # Do not attract non-overlapping road/wall objects from far away
            # along their length.
            overlap_limit = (
                float(wall.length_px) / 2.0
                + float(road.length_px) / 2.0
                + WALL_SNAP_DISTANCE_PX
            )
            if abs(along) > overlap_limit:
                continue

            signed = delta.x() * normal.x() + delta.y() * normal.y()
            target_abs = float(wall.width_px + road.width_px) / 2.0
            target_signed = target_abs if signed >= 0.0 else -target_abs
            correction = target_signed - signed
            distance = abs(correction)

            if distance > WALL_SNAP_DISTANCE_PX or distance >= best_distance:
                continue

            if moving_is_road:
                candidate = QPointF(
                    proposed_pos.x() + normal.x() * correction,
                    proposed_pos.y() + normal.y() * correction,
                )
            else:
                # signed = road - wall. Moving the wall by +normal*c moves
                # signed by -c, so use the opposite correction.
                candidate = QPointF(
                    proposed_pos.x() - normal.x() * correction,
                    proposed_pos.y() - normal.y() * correction,
                )

            best_distance = distance
            best_position = candidate

        return best_position if best_position is not None else proposed_pos

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
