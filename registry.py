"""Central item registry/factory for JSON reconstruction."""

from items.roads import (
    StraightRoadItem,
    ContinuousRoadItem,
    Curve90RoadItem,
    Curve45RoadItem,
    TJunctionItem,
    CrossIntersectionItem,
    RoadEndItem,
    MedianWallItem,
)
from items.vehicles import QCar2StartItem
from items.actors import (
    TrafficLightItem,
    StopSignItem,
    YieldSignItem,
    RoundaboutSignItem,
    CatalogTrafficSignItem,
    CrosswalkItem,
    BuildingBoxItem,
)
from items.experiment import (
    PersonItem,
    AnimalItem,
    SecondaryQCarItem,
    TriggerZoneItem,
)
from items.environment import (
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
)
from items.base import TrackItem
from items.reference import ReferenceImageItem
from items.sketch import SketchLineItem, SketchArcItem, SketchCircleItem

TRACK_ITEM_CLASSES = {
    StraightRoadItem.TYPE_NAME: StraightRoadItem,
    ContinuousRoadItem.TYPE_NAME: ContinuousRoadItem,
    Curve90RoadItem.TYPE_NAME: Curve90RoadItem,
    Curve45RoadItem.TYPE_NAME: Curve45RoadItem,
    TJunctionItem.TYPE_NAME: TJunctionItem,
    CrossIntersectionItem.TYPE_NAME: CrossIntersectionItem,
    RoadEndItem.TYPE_NAME: RoadEndItem,
    MedianWallItem.TYPE_NAME: MedianWallItem,
    QCar2StartItem.TYPE_NAME: QCar2StartItem,
    TrafficLightItem.TYPE_NAME: TrafficLightItem,
    StopSignItem.TYPE_NAME: StopSignItem,
    YieldSignItem.TYPE_NAME: YieldSignItem,
    RoundaboutSignItem.TYPE_NAME: RoundaboutSignItem,
    CatalogTrafficSignItem.TYPE_NAME: CatalogTrafficSignItem,
    CrosswalkItem.TYPE_NAME: CrosswalkItem,
    BuildingBoxItem.TYPE_NAME: BuildingBoxItem,
    OfficeBuildingItem.TYPE_NAME: OfficeBuildingItem,
    ApartmentBuildingItem.TYPE_NAME: ApartmentBuildingItem,
    ShopBuildingItem.TYPE_NAME: ShopBuildingItem,
    SteppedTowerItem.TYPE_NAME: SteppedTowerItem,
    RoundTreeItem.TYPE_NAME: RoundTreeItem,
    PineTreeItem.TYPE_NAME: PineTreeItem,
    ParkBenchItem.TYPE_NAME: ParkBenchItem,
    LampPostItem.TYPE_NAME: LampPostItem,
    TrashBinItem.TYPE_NAME: TrashBinItem,
    PlanterItem.TYPE_NAME: PlanterItem,
    FountainItem.TYPE_NAME: FountainItem,
    PersonItem.TYPE_NAME: PersonItem,
    AnimalItem.TYPE_NAME: AnimalItem,
    SecondaryQCarItem.TYPE_NAME: SecondaryQCarItem,
    TriggerZoneItem.TYPE_NAME: TriggerZoneItem,
    ReferenceImageItem.TYPE_NAME: ReferenceImageItem,
    SketchLineItem.TYPE_NAME: SketchLineItem,
    SketchArcItem.TYPE_NAME: SketchArcItem,
    SketchCircleItem.TYPE_NAME: SketchCircleItem,
}

def create_track_item_from_dict(data: dict) -> TrackItem | None:
    item_type = data.get("type")
    cls = TRACK_ITEM_CLASSES.get(item_type)
    if cls is None:
        return None
    item = cls.from_dict(data)
    if item is not None:
        item.set_readable_identifier(str(data.get("identifier", "")))
    return item
