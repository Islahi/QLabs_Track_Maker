"""Static scenery auto-fill for the user-defined editable canvas.

The filler intentionally uses *only* static composite environment assets from
``items.environment``. It never creates QCars, pedestrians, animals, trigger
zones, traffic lights, traffic signs, or any other experiment/traffic actor.

Road clearance is handled with scene-space QPainterPath geometry rather than
large axis-aligned road rectangles. This makes filling reliable around rotated
and curved roads while preserving a configurable roadside reserve for signs,
lights, crosswalk equipment, and other manually placed roadside objects.
"""

from __future__ import annotations

import random

from PySide6.QtCore import QPointF, QRectF
from PySide6.QtGui import QPainterPath, QPainterPathStroker

from config import (
    DEFAULT_BUILDING_ROAD_BAND_M,
    PIXELS_PER_METER,
)
from items.environment import (
    ApartmentBuildingItem,
    EnvironmentAssetItem,
    FountainItem,
    LampPostItem,
    OfficeBuildingItem,
    ParkBenchItem,
    PineTreeItem,
    PlanterItem,
    RoundTreeItem,
    ShopBuildingItem,
    SteppedTowerItem,
    TrashBinItem,
)
from items.roads import (
    ContinuousRoadItem,
    CrossIntersectionItem,
    Curve45RoadItem,
    Curve90RoadItem,
    RoadEndItem,
    StraightRoadItem,
    TJunctionItem,
)


ROAD_TYPES = (
    ContinuousRoadItem,
    StraightRoadItem,
    Curve45RoadItem,
    Curve90RoadItem,
    TJunctionItem,
    CrossIntersectionItem,
    RoadEndItem,
)

BUILDING_TYPES = (
    OfficeBuildingItem,
    ApartmentBuildingItem,
    ShopBuildingItem,
    SteppedTowerItem,
)

TREE_TYPES = (
    RoundTreeItem,
    PineTreeItem,
)

PARK_FURNITURE_TYPES = (
    ParkBenchItem,
    LampPostItem,
    TrashBinItem,
    PlanterItem,
    FountainItem,
)

# Every class in these mixes is a static EnvironmentAssetItem. No experiment or
# vehicle actor can enter the auto-fill selection path.
STYLE_MIXES = {
    "urban": (
        (
            OfficeBuildingItem,
            ApartmentBuildingItem,
            ShopBuildingItem,
            SteppedTowerItem,
            RoundTreeItem,
            PineTreeItem,
            ParkBenchItem,
            LampPostItem,
            TrashBinItem,
            PlanterItem,
            FountainItem,
        ),
        (9, 8, 8, 5, 3, 1, 2, 5, 3, 4, 1),
    ),
    "suburban": (
        (
            OfficeBuildingItem,
            ApartmentBuildingItem,
            ShopBuildingItem,
            SteppedTowerItem,
            RoundTreeItem,
            PineTreeItem,
            ParkBenchItem,
            LampPostItem,
            TrashBinItem,
            PlanterItem,
            FountainItem,
        ),
        (4, 7, 3, 1, 10, 7, 3, 3, 1, 3, 1),
    ),
    "park": (
        (
            RoundTreeItem,
            PineTreeItem,
            ParkBenchItem,
            LampPostItem,
            TrashBinItem,
            PlanterItem,
            FountainItem,
        ),
        (12, 9, 5, 4, 2, 5, 2),
    ),
}

DENSITY_SETTINGS = {
    "low": {"area_per_item_m2": 260.0, "grid_step_m": 7.0, "max_items": 55},
    "medium": {"area_per_item_m2": 150.0, "grid_step_m": 5.0, "max_items": 95},
    "high": {"area_per_item_m2": 90.0, "grid_step_m": 3.5, "max_items": 150},
}


class SceneryAutoFiller:
    """Place static scenery inside the editable canvas without blocking roads."""

    EDGE_MARGIN_M = 1.0
    EXISTING_CLEARANCE_M = 0.6

    # Extra space beyond the user-selected roadside reserve. Buildings must
    # also remain inside a finite road-side corridor so they form a streetscape
    # instead of being scattered across the whole canvas.
    BUILDING_EXTRA_ROAD_CLEARANCE_M = 1.5
    TREE_EXTRA_ROAD_CLEARANCE_M = 0.75
    PARK_EXTRA_ROAD_CLEARANCE_M = 0.0

    def __init__(self, scene, view):
        self.scene = scene
        self.view = view

    def fill_editable_open_space(
        self,
        *,
        style: str = "suburban",
        density: str = "medium",
        roadside_reserve_m: float = 4.0,
        building_road_band_m: float = DEFAULT_BUILDING_ROAD_BAND_M,
        target_rect_scene: QRectF | None = None,
    ) -> list[EnvironmentAssetItem]:
        """Populate open space in the canvas or a selected rectangular area."""

        style = style if style in STYLE_MIXES else "suburban"
        density = density if density in DENSITY_SETTINGS else "medium"
        roadside_reserve_m = max(0.0, float(roadside_reserve_m))
        building_road_band_m = max(
            roadside_reserve_m + self.BUILDING_EXTRA_ROAD_CLEARANCE_M + 0.5,
            float(building_road_band_m),
        )

        canvas_target = self.scene.editable_area_rect().adjusted(
            self.EDGE_MARGIN_M * PIXELS_PER_METER,
            self.EDGE_MARGIN_M * PIXELS_PER_METER,
            -self.EDGE_MARGIN_M * PIXELS_PER_METER,
            -self.EDGE_MARGIN_M * PIXELS_PER_METER,
        )
        target_rect = canvas_target
        if target_rect_scene is not None:
            target_rect = canvas_target.intersected(target_rect_scene.normalized())
        if target_rect.isEmpty():
            return []

        existing_items = list(self.scene.track_items())
        roads = [item for item in existing_items if isinstance(item, ROAD_TYPES)]

        # Existing objects reserve only their real scene footprint. Trigger zones
        # and other non-physical logic items do not block scenery placement.
        existing_entries = []
        for item in existing_items:
            item_type = getattr(item, "TYPE_NAME", "")
            if (
                isinstance(item, ROAD_TYPES)
                or item_type == "trigger_zone"
                or str(item_type).startswith("sketch_")
            ):
                continue
            existing_entries.append(self._path_entry(self._item_scene_path(item)))

        density_cfg = DENSITY_SETTINGS[density]
        area_m2 = (
            target_rect.width() / PIXELS_PER_METER
            * target_rect.height() / PIXELS_PER_METER
        )
        target_count = min(
            int(density_cfg["max_items"]),
            max(4, int(area_m2 / float(density_cfg["area_per_item_m2"]))),
        )

        # Keep candidate generation bounded on very large canvases (for
        # example Open Road). Aim for roughly 10 candidate positions per
        # requested item instead of creating millions of grid points. Small
        # brush rectangles previously inherited the full-canvas 150-item
        # budget, which caused avoidable lag after several fills.
        base_step_m = float(density_cfg["grid_step_m"])
        adaptive_step_m = (
            area_m2 / max(1.0, float(target_count) * 10.0)
        ) ** 0.5
        step_px = max(base_step_m, adaptive_step_m) * PIXELS_PER_METER
        points = self._candidate_points(target_rect, step_px)

        # Deterministic per scene size/count but changes after each fill click,
        # so repeated clicks can use remaining gaps instead of repeating a failed
        # sequence exactly.
        rng = random.Random(
            20260817
            + len(existing_items) * 7919
            + int(target_rect.width()) * 17
            + int(target_rect.height())
        )
        rng.shuffle(points)
        candidate_budget = min(1200, max(80, target_count * 10))
        if len(points) > candidate_budget:
            del points[candidate_budget:]

        classes, weights = STYLE_MIXES[style]
        created: list[EnvironmentAssetItem] = []
        created_entries: list[tuple[QRectF, QPainterPath]] = []

        # Precompute road exclusion paths at the three clearance levels. This is
        # both faster and more accurate than using a rotated road's bounding box.
        road_paths = [self._item_scene_path(road) for road in roads]
        road_exclusions = {
            "building": [
                self._path_entry(self._inflated_path(
                    road_path,
                    roadside_reserve_m + self.BUILDING_EXTRA_ROAD_CLEARANCE_M,
                ))
                for road_path in road_paths
            ],
            "tree": [
                self._path_entry(self._inflated_path(
                    road_path,
                    roadside_reserve_m + self.TREE_EXTRA_ROAD_CLEARANCE_M,
                ))
                for road_path in road_paths
            ],
            "park": [
                self._path_entry(self._inflated_path(
                    road_path,
                    roadside_reserve_m + self.PARK_EXTRA_ROAD_CLEARANCE_M,
                ))
                for road_path in road_paths
            ],
        }

        # Buildings are allowed only in a corridor beside a road. The inner
        # exclusion above preserves the clear roadside reserve; this outer zone
        # prevents buildings from appearing in unrelated corners of the canvas.
        building_outer_zones = [
            self._path_entry(self._inflated_path(
                road_path,
                building_road_band_m,
            ))
            for road_path in road_paths
        ]

        for point in points:
            if len(created) >= target_count:
                break

            attempted = set()
            for _ in range(min(5, len(classes))):
                asset_class = rng.choices(classes, weights=weights, k=1)[0]
                if asset_class in attempted:
                    continue
                attempted.add(asset_class)

                # Safety guard: future changes to STYLE_MIXES cannot accidentally
                # add a moving/experiment actor to the fill operation.
                if not issubclass(asset_class, EnvironmentAssetItem):
                    continue

                # Buildings require an actual road and their center must lie
                # inside the configured road-side building corridor. Park
                # assets are still free to populate the remaining canvas.
                if asset_class in BUILDING_TYPES:
                    if not building_outer_zones:
                        continue
                    if not any(
                        bounds.contains(point) and zone.contains(point)
                        for bounds, zone in building_outer_zones
                    ):
                        continue

                candidate = asset_class()
                candidate.auto_generated = True
                candidate.setPos(point)
                self._apply_random_rotation(candidate, rng)

                candidate_path = self._item_scene_path(candidate)
                candidate_rect = candidate_path.boundingRect()

                if not target_rect.contains(candidate_rect):
                    continue

                road_group = self._road_group(candidate)
                if self._intersects_any(
                    candidate_path,
                    road_exclusions[road_group],
                ):
                    continue

                candidate_clear = self._inflated_path(
                    candidate_path,
                    self.EXISTING_CLEARANCE_M,
                )
                if self._intersects_any(candidate_clear, existing_entries):
                    continue
                if self._intersects_any(candidate_clear, created_entries):
                    continue

                self.scene.addItem(candidate)
                created.append(candidate)
                created_entries.append(self._path_entry(candidate_path))
                break

        return created

    # Backward-compatible method name used by one older toolbar build.
    def fill_visible_open_space(self) -> list[EnvironmentAssetItem]:
        return self.fill_editable_open_space()

    @staticmethod
    def _road_group(candidate: EnvironmentAssetItem) -> str:
        if isinstance(candidate, BUILDING_TYPES):
            return "building"
        if isinstance(candidate, TREE_TYPES):
            return "tree"
        return "park"

    @staticmethod
    def _apply_random_rotation(candidate: EnvironmentAssetItem, rng: random.Random):
        if isinstance(candidate, BUILDING_TYPES):
            candidate.setRotation(rng.choice((0.0, 90.0, 180.0, 270.0)))
        elif isinstance(candidate, (ParkBenchItem, PlanterItem, FountainItem)):
            candidate.setRotation(rng.choice((0.0, 90.0, 180.0, 270.0)))
        else:
            candidate.setRotation(rng.choice((0.0, 45.0, 90.0, 135.0)))

    @staticmethod
    def _item_scene_path(item) -> QPainterPath:
        """Return the item's actual scene-space selectable/physical shape."""
        try:
            local_path = item.shape()
            return item.mapToScene(local_path)
        except Exception:
            path = QPainterPath()
            path.addRect(item.mapRectToScene(item.boundingRect()).boundingRect())
            return path

    @staticmethod
    def _path_entry(path: QPainterPath) -> tuple[QRectF, QPainterPath]:
        return path.boundingRect(), path

    @staticmethod
    def _intersects_any(
        candidate: QPainterPath,
        entries: list[tuple[QRectF, QPainterPath]],
    ) -> bool:
        candidate_bounds = candidate.boundingRect()
        return any(
            candidate_bounds.intersects(bounds) and candidate.intersects(path)
            for bounds, path in entries
        )

    @staticmethod
    def _inflated_path(path: QPainterPath, clearance_m: float) -> QPainterPath:
        clearance_px = max(0.0, float(clearance_m)) * PIXELS_PER_METER
        if clearance_px <= 0.0:
            return QPainterPath(path)
        stroker = QPainterPathStroker()
        stroker.setWidth(clearance_px * 2.0)
        return path.united(stroker.createStroke(path))

    @staticmethod
    def _candidate_points(target_rect: QRectF, step_px: float) -> list[QPointF]:
        if step_px <= 0.0:
            return []

        points = []
        x = target_rect.left() + step_px / 2.0
        while x <= target_rect.right() - step_px / 2.0:
            y = target_rect.top() + step_px / 2.0
            while y <= target_rect.bottom() - step_px / 2.0:
                points.append(QPointF(x, y))
                y += step_px
            x += step_px
        return points
