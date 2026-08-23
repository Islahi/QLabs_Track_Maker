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
from core.geometry import endpoints_face_each_other, point_distance, snap_value
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
    # CAD sketch topology
    # ------------------------------------------------------------------

    @staticmethod
    def _segment_intersection(
        a: QPointF,
        b: QPointF,
        c: QPointF,
        d: QPointF,
    ) -> tuple[QPointF, float, float] | None:
        """Return the finite-segment intersection and both segment ratios."""
        ab_x = b.x() - a.x()
        ab_y = b.y() - a.y()
        cd_x = d.x() - c.x()
        cd_y = d.y() - c.y()
        denominator = ab_x * cd_y - ab_y * cd_x
        if abs(denominator) <= 1e-8:
            return None

        ac_x = c.x() - a.x()
        ac_y = c.y() - a.y()
        along_ab = (ac_x * cd_y - ac_y * cd_x) / denominator
        along_cd = (ac_x * ab_y - ac_y * ab_x) / denominator
        tolerance = 1e-6
        if not (
            -tolerance <= along_ab <= 1.0 + tolerance
            and -tolerance <= along_cd <= 1.0 + tolerance
        ):
            return None
        return (
            QPointF(a.x() + along_ab * ab_x, a.y() + along_ab * ab_y),
            max(0.0, min(1.0, along_ab)),
            max(0.0, min(1.0, along_cd)),
        )

    def sketch_connection_nodes(self) -> list[dict]:
        """Find real intersections between the current CAD guide paths.

        Circle guides are sampled to short chords, so the same routine works
        for line-line, line-arc, line-circle, and arc-circle connections.
        Coincident endpoints are folded into one node.
        """
        guides = [
            item
            for item in self.track_items()
            if callable(getattr(item, "is_sketch_guide", None))
            and item.is_sketch_guide()
        ]
        nodes: list[dict] = []
        merge_distance_px = 0.08 * PIXELS_PER_METER

        for first_index, first in enumerate(guides):
            first_points = first.sampled_scene_points()
            first_bounds = first.sceneBoundingRect()
            for second in guides[first_index + 1:]:
                second_bounds = second.sceneBoundingRect()
                if not first_bounds.intersects(second_bounds):
                    continue
                second_points = second.sampled_scene_points()
                for first_segment, (a, b) in enumerate(
                    zip(first_points, first_points[1:])
                ):
                    for second_segment, (c, d) in enumerate(
                        zip(second_points, second_points[1:])
                    ):
                        crossing = self._segment_intersection(a, b, c, d)
                        if crossing is None:
                            continue
                        point, first_ratio, second_ratio = crossing
                        merged = None
                        for node in nodes:
                            if point_distance(point, node["pos"]) <= merge_distance_px:
                                merged = node
                                break
                        if merged is None:
                            merged = {"pos": point, "members": []}
                            nodes.append(merged)
                        for guide, segment, ratio in (
                            (first, first_segment, first_ratio),
                            (second, second_segment, second_ratio),
                        ):
                            if not any(
                                member["guide"] is guide
                                for member in merged["members"]
                            ):
                                merged["members"].append({
                                    "guide": guide,
                                    "segment": segment,
                                    "ratio": ratio,
                                })
        return nodes

    def sketch_road_points(self, guide: TrackItem) -> list[QPointF]:
        """Insert logical crossing nodes into one guide's sampled path."""
        points = list(guide.sampled_scene_points())
        if len(points) < 2:
            return points
        insertions: dict[int, list[tuple[float, QPointF]]] = {}
        for node in self.sketch_connection_nodes():
            for member in node["members"]:
                if member["guide"] is not guide:
                    continue
                segment = int(member["segment"])
                ratio = float(member["ratio"])
                # Existing segment endpoints are already real guide nodes.
                if 1e-6 < ratio < 1.0 - 1e-6:
                    insertions.setdefault(segment, []).append(
                        (ratio, QPointF(node["pos"]))
                    )

        result: list[QPointF] = []
        for segment, point in enumerate(points[:-1]):
            result.append(QPointF(point))
            for _, crossing in sorted(insertions.get(segment, [])):
                if point_distance(result[-1], crossing) > 0.01:
                    result.append(crossing)
        result.append(QPointF(points[-1]))
        return result

    # ------------------------------------------------------------------
    # Combined snapping
    # ------------------------------------------------------------------

    def snap_drawing_point(
        self,
        scene_point: QPointF,
        *,
        exclude_item: TrackItem | None = None,
        heading_deg: float | None = None,
    ) -> QPointF:
        """Snap a road control point to the grid or a nearby road endpoint.

        Unlike ``snap_item_position`` this operates on one explicit scene
        point, which is what the continuous-road drawing and node handles
        need. Endpoint coordinates win over the regular one-metre grid.
        """
        snapped = QPointF(
            snap_value(scene_point.x(), PIXELS_PER_METER),
            snap_value(scene_point.y(), PIXELS_PER_METER),
        )
        if not self.endpoint_snap_enabled:
            return snapped
        best_distance = ENDPOINT_SNAP_DISTANCE_PX + 1.0
        best_point = None

        for target_item in self.track_items():
            if target_item is exclude_item:
                continue
            for connection in target_item.connection_points_scene():
                if heading_deg is not None and not endpoints_face_each_other(
                    heading_deg,
                    connection["heading_deg"],
                ):
                    continue
                distance = point_distance(scene_point, connection["pos"])
                if distance <= ENDPOINT_SNAP_DISTANCE_PX and distance < best_distance:
                    best_distance = distance
                    best_point = connection["pos"]

            # Closed sketch primitives such as circles have no arbitrary
            # PowerPoint-style fixed handles. They offer the geometrically
            # nearest point on their perimeter and gain a persistent port only
            # when another guide actually connects there.
            candidate_getter = getattr(
                target_item,
                "nearest_connection_candidate_scene",
                None,
            )
            if callable(candidate_getter):
                candidate = candidate_getter(scene_point)
                if candidate is not None:
                    distance = point_distance(scene_point, candidate)
                    if distance <= ENDPOINT_SNAP_DISTANCE_PX and distance < best_distance:
                        best_distance = distance
                        best_point = candidate

        return QPointF(best_point) if best_point is not None else snapped

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
