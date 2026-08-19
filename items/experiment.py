"""Experiment actors, environment QCars, and trigger zones."""

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPen

from config import (
    ACTOR_MARKER_SIZE_M,
    PIXELS_PER_METER,
    QCAR2_DESIGN_LENGTH_M,
    QCAR2_DESIGN_WIDTH_M,
    EXPERIMENT_SPAWN_IMMEDIATE,
    EXPERIMENT_SPAWN_TRIGGERED,
    TRIGGER_ACTION_ACTIVATE_ACTOR,
    TRIGGER_ACTION_TRAFFIC_LIGHT,
    DEFAULT_TRIGGER_RADIUS_M,
    MOVEMENT_ONCE,
    MOVEMENT_LOOP,
    MOVEMENT_PINGPONG,
    DEFAULT_SECONDARY_QCAR_SPEED_MPS,
    SELECTION_COLOR,
    SELECTION_LINE_WIDTH_PX,
)
from core.geometry import world_to_scene
from items.actors import SceneActorItem
from items.base import TrackItem

class ExperimentActorItem(SceneActorItem):
    """Common editor data for people/animals used in experiments."""

    def __init__(self, object_id: str | None = None):
        super().__init__(object_id=object_id)
        self.spawn_mode = EXPERIMENT_SPAWN_IMMEDIATE
        self.move_on_activation = False
        self.destination_x_m = 0.0
        self.destination_y_m = 0.0
        self.movement_gait = "walk"
        self.path_points_m = []
        self.movement_mode = MOVEMENT_ONCE
        self.despawn_on_finish = False

    def experiment_actor_dict(self) -> dict:
        data = self.actor_dict()
        data.update(
            {
                "spawn_mode": self.spawn_mode,
                "move_on_activation": bool(self.move_on_activation),
                "destination_x_m": float(self.destination_x_m),
                "destination_y_m": float(self.destination_y_m),
                "movement_gait": self.movement_gait,
                "path_points": [
                    [float(point[0]), float(point[1])]
                    for point in self.path_points_m
                ],
                "movement_mode": self.movement_mode,
                "despawn_on_finish": bool(self.despawn_on_finish),
            }
        )
        return data

    def load_experiment_actor_dict(self, data: dict):
        self.load_actor_dict(data)
        self.spawn_mode = str(
            data.get("spawn_mode", EXPERIMENT_SPAWN_IMMEDIATE)
        )
        self.move_on_activation = bool(data.get("move_on_activation", False))
        self.destination_x_m = float(
            data.get("destination_x_m", data.get("x", 0.0))
        )
        self.destination_y_m = float(
            data.get("destination_y_m", data.get("y", 0.0))
        )
        self.movement_gait = str(data.get("movement_gait", "walk"))
        raw_path = data.get("path_points", []) or []
        self.path_points_m = []
        for point in raw_path:
            if isinstance(point, (list, tuple)) and len(point) >= 2:
                self.path_points_m.append([float(point[0]), float(point[1])])
        self.movement_mode = str(data.get("movement_mode", MOVEMENT_ONCE))
        if self.movement_mode not in {MOVEMENT_ONCE, MOVEMENT_LOOP, MOVEMENT_PINGPONG}:
            self.movement_mode = MOVEMENT_ONCE
        self.despawn_on_finish = bool(data.get("despawn_on_finish", False))

    def selection_text(self) -> str:
        spawn_text = (
            "Triggered"
            if self.spawn_mode == EXPERIMENT_SPAWN_TRIGGERED
            else "Immediate"
        )
        text = super().selection_text() + f"\nSpawn: {spawn_text}"
        if self.move_on_activation:
            text += (
                f"\nWaypoints: {len(self.path_points_m)}"
                f"\nMovement: {self.movement_mode.title()}"
                f"\nGait: {self.movement_gait.title()}"
            )
            if self.movement_mode == MOVEMENT_ONCE:
                text += f"\nDespawn after route: {'Yes' if self.despawn_on_finish else 'No'}"
        return text

class PersonItem(ExperimentActorItem):
    TYPE_NAME = "person"
    DISPLAY_NAME = "Pedestrian"

    def __init__(self, object_id: str | None = None):
        super().__init__(object_id=object_id)
        self.person_configuration = 0
        self.enable_identifier_label(
            ACTOR_MARKER_SIZE_M * PIXELS_PER_METER / 2.0 + 6.0
        )

    def boundingRect(self) -> QRectF:
        s = ACTOR_MARKER_SIZE_M * PIXELS_PER_METER
        return QRectF(-s / 2, -s / 2, s, s)

    def paint(self, painter: QPainter, option, widget=None):
        rect = self.boundingRect().adjusted(5, 5, -5, -5)

        painter.setPen(QPen(QColor(35, 35, 35), 2))
        painter.setBrush(QColor(90, 190, 235))
        painter.drawEllipse(
            QPointF(0, rect.top() + rect.height() * 0.28),
            6,
            6,
        )

        painter.setPen(QPen(QColor(90, 190, 235), 5))
        painter.drawLine(
            QPointF(0, rect.top() + rect.height() * 0.42),
            QPointF(0, rect.bottom() - 5),
        )
        painter.drawLine(
            QPointF(0, rect.center().y()),
            QPointF(rect.right() - 4, rect.center().y()),
        )

        # Forward arrow (+X).
        painter.setPen(QPen(QColor(255, 220, 70), 2))
        painter.drawLine(QPointF(0, 0), QPointF(rect.right() + 8, 0))

        if self.spawn_mode == EXPERIMENT_SPAWN_TRIGGERED:
            dash_pen = QPen(QColor(210, 140, 255), 2, Qt.PenStyle.DashLine)
            dash_pen.setCosmetic(True)
            painter.setPen(dash_pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(rect)

        if self.isSelected():
            pen = QPen(SELECTION_COLOR, SELECTION_LINE_WIDTH_PX)
            pen.setCosmetic(True)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(rect.adjusted(-3, -3, 3, 3))

    def to_dict(self) -> dict:
        data = self.experiment_actor_dict()
        data["person_configuration"] = int(self.person_configuration)
        return data

    @classmethod
    def from_dict(cls, data: dict):
        item = cls(object_id=data.get("id"))
        item.load_experiment_actor_dict(data)
        item.person_configuration = max(
            0, min(11, int(data.get("person_configuration", 0)))
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
        return (
            super().selection_text()
            + f"\nPerson configuration: {self.person_configuration}"
        )

class AnimalItem(ExperimentActorItem):
    TYPE_NAME = "animal"
    DISPLAY_NAME = "Animal"

    def __init__(self, object_id: str | None = None):
        super().__init__(object_id=object_id)
        self.animal_type = "goat"
        self.enable_identifier_label(
            ACTOR_MARKER_SIZE_M * PIXELS_PER_METER / 2.0 + 6.0
        )

    def boundingRect(self) -> QRectF:
        s = ACTOR_MARKER_SIZE_M * PIXELS_PER_METER
        return QRectF(-s / 2, -s / 2, s, s)

    def paint(self, painter: QPainter, option, widget=None):
        rect = self.boundingRect().adjusted(5, 5, -5, -5)

        animal_colors = {
            "goat": QColor(220, 200, 150),
            "sheep": QColor(235, 235, 225),
            "cow": QColor(170, 125, 95),
            "camel": QColor(198, 145, 82),
        }

        painter.setPen(QPen(QColor(45, 45, 45), 2))
        painter.setBrush(animal_colors.get(self.animal_type, animal_colors["goat"]))

        if self.animal_type == "camel":
            # Side-view camel marker with two humps and a raised neck.
            body = rect.adjusted(3, 9, -8, -7)
            painter.drawEllipse(body)
            painter.drawEllipse(QPointF(body.center().x() - 5, body.top() + 1), 6, 6)
            painter.drawEllipse(QPointF(body.center().x() + 4, body.top() + 1), 6, 6)
            painter.setPen(QPen(animal_colors["camel"], 5))
            painter.drawLine(
                QPointF(body.right() - 1, body.center().y()),
                QPointF(rect.right() - 2, rect.top() + 7),
            )
            painter.setPen(QPen(QColor(45, 45, 45), 2))
            painter.drawEllipse(QPointF(rect.right() - 1, rect.top() + 5), 5, 4)
        else:
            painter.drawEllipse(rect.adjusted(3, 7, -7, -7))
            painter.drawEllipse(
                QPointF(rect.right() - 4, rect.center().y()),
                6,
                5,
            )

        painter.setPen(QPen(QColor(255, 220, 70), 2))
        painter.drawLine(QPointF(0, 0), QPointF(rect.right() + 8, 0))

        if self.spawn_mode == EXPERIMENT_SPAWN_TRIGGERED:
            dash_pen = QPen(QColor(210, 140, 255), 2, Qt.PenStyle.DashLine)
            dash_pen.setCosmetic(True)
            painter.setPen(dash_pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(rect)

        if self.isSelected():
            pen = QPen(SELECTION_COLOR, SELECTION_LINE_WIDTH_PX)
            pen.setCosmetic(True)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(rect.adjusted(-3, -3, 3, 3))

    def to_dict(self) -> dict:
        data = self.experiment_actor_dict()
        data["animal_type"] = self.animal_type
        return data

    @classmethod
    def from_dict(cls, data: dict):
        item = cls(object_id=data.get("id"))
        item.load_experiment_actor_dict(data)
        item.animal_type = str(data.get("animal_type", "goat"))
        if item.animal_type not in {"goat", "sheep", "cow", "camel"}:
            item.animal_type = "goat"
        item.setPos(
            world_to_scene(
                float(data.get("x", 0.0)),
                float(data.get("y", 0.0)),
            )
        )
        item.setRotation(float(data.get("rotation_deg", 0.0)))
        return item

    def selection_text(self) -> str:
        return super().selection_text() + f"\nAnimal: {self.animal_type.title()}"

class SecondaryQCarItem(ExperimentActorItem):
    TYPE_NAME = "secondary_qcar2"
    DISPLAY_NAME = "Environment QCar2"

    def __init__(self, object_id: str | None = None):
        super().__init__(object_id=object_id)
        self.movement_speed_mps = DEFAULT_SECONDARY_QCAR_SPEED_MPS
        self.setZValue(45)
        self.enable_identifier_label(self.width_px / 2.0 + 8.0)

    @property
    def length_px(self):
        return QCAR2_DESIGN_LENGTH_M * PIXELS_PER_METER

    @property
    def width_px(self):
        return QCAR2_DESIGN_WIDTH_M * PIXELS_PER_METER

    def boundingRect(self) -> QRectF:
        margin = 8.0
        return QRectF(-self.length_px/2-margin, -self.width_px/2-margin,
                      self.length_px+2*margin, self.width_px+2*margin)

    def paint(self, painter: QPainter, option, widget=None):
        body = QRectF(-self.length_px/2, -self.width_px/2, self.length_px, self.width_px)
        painter.setPen(QPen(QColor(80, 55, 20), 2))
        painter.setBrush(QColor(235, 155, 55))
        painter.drawRoundedRect(body, 6, 6)
        painter.setPen(QPen(QColor(255, 245, 220), 2))
        painter.drawLine(QPointF(-self.length_px*0.2, 0), QPointF(self.length_px*0.3, 0))
        painter.setPen(QPen(QColor(255, 220, 70), 2))
        painter.drawLine(QPointF(0, 0), QPointF(self.length_px/2 + 10, 0))
        if self.spawn_mode == EXPERIMENT_SPAWN_TRIGGERED:
            pen = QPen(QColor(210, 140, 255), 2, Qt.PenStyle.DashLine); pen.setCosmetic(True)
            painter.setPen(pen); painter.setBrush(Qt.BrushStyle.NoBrush); painter.drawRect(body)
        if self.isSelected():
            pen = QPen(SELECTION_COLOR, SELECTION_LINE_WIDTH_PX); pen.setCosmetic(True)
            painter.setPen(pen); painter.setBrush(Qt.BrushStyle.NoBrush); painter.drawRect(body.adjusted(-3,-3,3,3))

    def to_dict(self) -> dict:
        data = self.experiment_actor_dict()
        data["movement_speed_mps"] = float(self.movement_speed_mps)
        return data

    @classmethod
    def from_dict(cls, data: dict):
        item = cls(object_id=data.get("id"))
        item.load_experiment_actor_dict(data)
        item.movement_speed_mps = max(0.1, float(data.get("movement_speed_mps", DEFAULT_SECONDARY_QCAR_SPEED_MPS)))
        item.setPos(world_to_scene(float(data.get("x",0.0)), float(data.get("y",0.0))))
        item.setRotation(float(data.get("rotation_deg",0.0)))
        return item

    def selection_text(self) -> str:
        return super().selection_text() + f"\\nPath speed: {self.movement_speed_mps:.1f} m/s"

class TriggerZoneItem(TrackItem):
    TYPE_NAME = "trigger_zone"
    DISPLAY_NAME = "QCar Trigger Zone"

    def __init__(self, object_id: str | None = None):
        super().__init__(object_id=object_id)
        self.radius_m = DEFAULT_TRIGGER_RADIUS_M
        self.action = TRIGGER_ACTION_ACTIVATE_ACTOR
        self.target_id = ""
        self.traffic_color = "green"
        self.one_shot = True
        self.setZValue(70)

    @property
    def radius_px(self) -> float:
        return self.radius_m * PIXELS_PER_METER

    def boundingRect(self) -> QRectF:
        r = self.radius_px
        margin = 5.0
        return QRectF(
            -r - margin,
            -r - margin,
            2 * (r + margin),
            2 * (r + margin),
        )

    def paint(self, painter: QPainter, option, widget=None):
        r = self.radius_px
        rect = QRectF(-r, -r, 2 * r, 2 * r)

        zone_pen = QPen(
            QColor(220, 110, 255, 220),
            2,
            Qt.PenStyle.DashLine,
        )
        zone_pen.setCosmetic(True)
        painter.setPen(zone_pen)
        painter.setBrush(QColor(180, 80, 220, 35))
        painter.drawEllipse(rect)

        painter.setPen(QPen(QColor(240, 190, 255), 2))
        painter.drawLine(QPointF(-8, 0), QPointF(8, 0))
        painter.drawLine(QPointF(0, -8), QPointF(0, 8))

        if self.isSelected():
            pen = QPen(SELECTION_COLOR, SELECTION_LINE_WIDTH_PX)
            pen.setCosmetic(True)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawEllipse(rect)

    def to_dict(self) -> dict:
        data = self.base_dict()
        data.update(
            {
                "radius_m": float(self.radius_m),
                "action": self.action,
                "target_id": self.target_id,
                "traffic_color": self.traffic_color,
                "one_shot": bool(self.one_shot),
            }
        )
        return data

    @classmethod
    def from_dict(cls, data: dict):
        item = cls(object_id=data.get("id"))
        item.radius_m = max(
            0.1,
            float(data.get("radius_m", DEFAULT_TRIGGER_RADIUS_M)),
        )
        item.action = str(
            data.get("action", TRIGGER_ACTION_ACTIVATE_ACTOR)
        )
        item.target_id = str(data.get("target_id", ""))
        item.traffic_color = str(data.get("traffic_color", "green"))
        item.one_shot = bool(data.get("one_shot", True))
        item.setPos(
            world_to_scene(
                float(data.get("x", 0.0)),
                float(data.get("y", 0.0)),
            )
        )
        item.setRotation(float(data.get("rotation_deg", 0.0)))
        return item

    def selection_text(self) -> str:
        action_text = (
            "Activate experiment actor"
            if self.action == TRIGGER_ACTION_ACTIVATE_ACTOR
            else "Change traffic light"
        )
        return (
            super().selection_text()
            + f"\nRadius: {self.radius_m:.1f} m"
            + f"\nAction: {action_text}"
            + f"\nOne shot: {'Yes' if self.one_shot else 'No'}"
        )
