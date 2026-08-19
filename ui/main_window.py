"""Main application window.

This module preserves the complete v1.0.1 UI/workflow while the domain
objects, scene, view, geometry, workspace data, registry, and exporter live
in separate modules.
"""

import json
import math
from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (
    QAction,
    QColor,
    QKeySequence,
    QPainter,
    QPainterPath,
    QPen,
    QIntValidator,
)
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QLayout,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from config import (
    PIXELS_PER_METER,
    GRID_PIXELS,
    DEFAULT_ROAD_WIDTH_M,
    QCAR_CAMERA_THIRD_PERSON,
    QCAR_CAMERA_FIRST_PERSON,
    OPEN_ROAD_REFERENCE_LANES_PER_SIDE,
    OPEN_ROAD_REFERENCE_LANE_WIDTH_M,
    OPEN_ROAD_REFERENCE_CARRIAGEWAY_WIDTH_M,
    OPEN_ROAD_REFERENCE_SEPARATOR_WIDTH_M,
    OPEN_ROAD_REFERENCE_TOTAL_WIDTH_M,
    CROSSWALK_QLABS_BASE_SCALE,
    DEFAULT_BUILDING_RGB,
    EXPERIMENT_SPAWN_IMMEDIATE,
    EXPERIMENT_SPAWN_TRIGGERED,
    TRIGGER_ACTION_ACTIVATE_ACTOR,
    TRIGGER_ACTION_TRAFFIC_LIGHT,
    MOVEMENT_ONCE,
    MOVEMENT_LOOP,
    MOVEMENT_PINGPONG,
    WEATHER_PRESETS,
    ROTATION_STEP_DEG,
    ENDPOINT_SNAP_DISTANCE_M,
    DEFAULT_GUIDE_RGB,
    GUIDE_COLOR_RGB,
    PROJECT_SCALES,
    WORKSPACE_CUSTOM,
    WORKSPACE_OPEN_ROAD,
    WORKSPACE_MODES,
    DEFAULT_CANVAS_WIDTH_M,
    DEFAULT_CANVAS_HEIGHT_M,
    DEFAULT_SCENERY_FILL_STYLE,
    DEFAULT_SCENERY_FILL_DENSITY,
    DEFAULT_ROADSIDE_RESERVE_M,
    DEFAULT_BUILDING_ROAD_BAND_M,
)
from core.geometry import (
    normalize_angle,
    scene_to_world,
    snap_value,
    world_to_scene,
)
from workspace.open_road import (
    load_open_road_reference,
    _offset_world_polyline,
    _world_polyline_path,
)
from workspace.profiles import (
    DEFAULT_WORKSPACE_PLATFORM_COLOR_RGB,
    DEFAULT_WORKSPACE_PLATFORM_PROFILE,
    WORKSPACE_PLATFORM_PROFILES,
    workspace_platform_profile,
    workspace_profile_key_for_mode,
    workspace_mode_profile,
    workspace_mode_label,
    workspace_mode_default_spline_z,
    workspace_mode_default_road_width,
)
from export.qlabs_exporter import build_qlabs_setup_source
from core.traffic_sign_catalog import DEFAULT_TRAFFIC_SIGN_KEY, TRAFFIC_SIGN_CATALOG
from items.base import TrackItem
from items.roads import (
    StraightRoadItem,
    Curve45RoadItem,
    Curve90RoadItem,
    TJunctionItem,
    CrossIntersectionItem,
    RoadEndItem,
    MedianWallItem,
)
from items.vehicles import QCar2StartItem
from items.actors import (
    SceneActorItem,
    TrafficLightItem,
    StopSignItem,
    YieldSignItem,
    RoundaboutSignItem,
    CatalogTrafficSignItem,
    CrosswalkItem,
    BuildingBoxItem,
)
from items.experiment import (
    ExperimentActorItem,
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
from registry import create_track_item_from_dict
from ui.scene import TrackScene
from ui.view import TrackView
from ui.top_bar import TopControlBar
from services.scenery_filler import SceneryAutoFiller
from services.undo_manager import SnapshotUndoManager

class TrackEditorWindow(QMainWindow):
    VERSION = "2.0.0-dev"

    def __init__(self):
        super().__init__()

        self.current_file: Path | None = None
        self.rotation_step_deg = ROTATION_STEP_DEG
        self._property_refreshing = False
        self._guide_refreshing = False
        self._marking_refreshing = False

        # Project scale affects the future QLabs export/effective dimensions.
        # The editor canvas itself remains in full-scale design meters.
        self.project_scale_factor = 1.0
        self.project_scale_name = "1:1"

        self.environment_enabled = True
        self.environment_weather = "clear_skies"
        self.environment_time_of_day = 12.0

        # Optional workspace-cover platform.  The generated QLabs setup can
        # place a static BasicShape box over an existing workspace and use its
        # top surface as the Z=0 plane for every exported track object.
        default_platform = workspace_platform_profile(
            DEFAULT_WORKSPACE_PLATFORM_PROFILE
        )
        self.workspace_platform_enabled = False
        self.workspace_platform_profile = DEFAULT_WORKSPACE_PLATFORM_PROFILE
        self.workspace_platform_top_z_m = float(
            default_platform["default_top_z_m"]
        )
        self.workspace_platform_bottom_z_m = float(
            default_platform["default_bottom_z_m"]
        )
        self.workspace_platform_color_rgb = list(
            DEFAULT_WORKSPACE_PLATFORM_COLOR_RGB
        )

        # User-defined editable canvas and scenery-fill settings. The scene
        # enforces this rectangle as the design boundary; auto-fill never uses
        # pixels outside it.
        self.canvas_width_m = DEFAULT_CANVAS_WIDTH_M
        self.canvas_height_m = DEFAULT_CANVAS_HEIGHT_M
        self.scenery_fill_style = DEFAULT_SCENERY_FILL_STYLE
        self.scenery_fill_density = DEFAULT_SCENERY_FILL_DENSITY
        self.roadside_reserve_m = DEFAULT_ROADSIDE_RESERVE_M
        self.building_road_band_m = DEFAULT_BUILDING_ROAD_BAND_M

        # Snapshot-based history gives every heterogeneous editor item a common
        # undo mechanism without coupling the UI to each concrete item class.
        self.undo_manager = SnapshotUndoManager(max_steps=60)
        self._history_suspended = False

        # Workspace-reference state. Open Road uses the documentation-derived
        # 2-D map for placement only; it is never turned into QLabs actors.
        (
            self.open_road_reference,
            self.open_road_reference_source,
        ) = load_open_road_reference()

        self.workspace_mode = WORKSPACE_CUSTOM
        self.workspace_spline_z_m = workspace_mode_default_spline_z(
            self.workspace_mode
        )
        self.workspace_show_road_reference = True
        self.workspace_show_navigation_regions = True
        self.workspace_show_reference_points = True
        self.workspace_show_reference_labels = True

        self.path_edit_actor_id = None

        self.setWindowTitle(f"QLabs Track Editor v{self.VERSION}")
        self.resize(1500, 920)

        self.scene = TrackScene(self)
        self.view = TrackView(self.scene)
        self.view.setMouseTracking(True)
        self.scenery_filler = SceneryAutoFiller(self.scene, self.view)

        self._build_ui()
        self._build_actions()
        self._set_workspace_from_data({})
        self._set_workspace_platform_from_data({})
        self._set_canvas_from_data({})
        self._set_scenery_fill_from_data({})

        self.view.centerOn(0, 0)
        self.update_zoom_label()
        self.update_selection_info()
        self._update_undo_controls()

    # ------------------------------------------------------------
    # UI helpers
    # ------------------------------------------------------------

    def _make_spinbox(
        self,
        minimum: float,
        maximum: float,
        step: float = 1.0,
        decimals: int = 1,
        suffix: str = "",
    ) -> QDoubleSpinBox:
        spin = QDoubleSpinBox()
        spin.setRange(minimum, maximum)
        spin.setSingleStep(step)
        spin.setDecimals(decimals)
        spin.setKeyboardTracking(False)
        if suffix:
            spin.setSuffix(suffix)
        return spin

    def _rgb_input_value(self, field: QLineEdit, fallback: int = 0) -> int:
        """Return a clamped integer from an RGB text field."""
        value_text = field.text().strip()
        if value_text == "":
            value = int(fallback)
            field.setText(str(value))
            return max(0, min(255, value))

        try:
            value = int(value_text)
        except ValueError:
            value = int(fallback)

        value = max(0, min(255, value))
        if field.text() != str(value):
            field.setText(str(value))
        return value

    def _add_palette_button(self, layout, text: str, callback):
        btn = QPushButton(text)
        btn.clicked.connect(callback)
        layout.addWidget(btn)
        return btn

    # ------------------------------------------------------------
    # UI
    # ------------------------------------------------------------

    def _build_ui(self):
        """Build the compact top-toolbar layout and right-side inspector."""
        central = QWidget()
        root = QVBoxLayout(central)
        root.setContentsMargins(6, 6, 6, 6)
        root.setSpacing(6)

        # The old 300 px left sidebar has been replaced by a compact
        # two-row top bar. Long component names live in tooltips while
        # the visible creation controls are symbolic icons.
        self.top_bar = TopControlBar(self)
        root.addWidget(self.top_bar)

        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(6)

        # Dedicated right-side inspector remains independent and scrollable.
        inspector_contents = QWidget()
        inspector_contents.setMinimumWidth(330)
        inspector_contents.setMaximumWidth(360)
        inspector_layout = QVBoxLayout(inspector_contents)
        inspector_layout.setContentsMargins(6, 0, 6, 0)
        inspector_layout.setSpacing(6)
        inspector_layout.setSizeConstraint(
            QLayout.SizeConstraint.SetMinAndMaxSize
        )

        # --------------------------------------------------------
        # Selected-object summary
        # --------------------------------------------------------
        self.info_group = QGroupBox("SELECTED OBJECT")
        info_layout = QVBoxLayout(self.info_group)

        info_control_row = QHBoxLayout()
        info_control_row.addStretch(1)

        self.info_toggle_button = QPushButton("−")
        self.info_toggle_button.setToolTip(
            "Minimize / expand the selected-object summary"
        )
        self.info_toggle_button.setFixedSize(26, 22)
        self.info_toggle_button.clicked.connect(
            self.toggle_selected_object_summary
        )
        info_control_row.addWidget(self.info_toggle_button)

        info_layout.addLayout(info_control_row)

        self.selection_label = QLabel("None")
        self.selection_label.setWordWrap(True)
        self.selection_label.setStyleSheet(
            "background: #20242a; padding: 8px; border-radius: 4px;"
        )
        info_layout.addWidget(self.selection_label)
        inspector_layout.addWidget(self.info_group)

        # --------------------------------------------------------
        # Editable properties
        # --------------------------------------------------------
        self.properties_group = QGroupBox("PROPERTIES")
        self.properties_form = QFormLayout(self.properties_group)

        self.prop_x = self._make_spinbox(-10000.0, 10000.0, 1.0, 1, " m")
        self.prop_y = self._make_spinbox(-10000.0, 10000.0, 1.0, 1, " m")
        self.prop_rotation = self._make_spinbox(0.0, 359.9, 1.0, 1, "°")
        self.prop_length = self._make_spinbox(1.0, 1000.0, 1.0, 1, " m")
        self.prop_width = self._make_spinbox(0.05, 50.0, 0.05, 2, " m")
        self.prop_radius = self._make_spinbox(1.0, 1000.0, 1.0, 1, " m")
        self.prop_arm = self._make_spinbox(2.0, 1000.0, 1.0, 1, " m")
        self.prop_height = self._make_spinbox(0.05, 20.0, 0.05, 2, " m")

        self.properties_form.addRow("X", self.prop_x)
        self.properties_form.addRow("Y", self.prop_y)
        self.properties_form.addRow("Rotation", self.prop_rotation)
        self.properties_form.addRow("Length", self.prop_length)
        self.properties_form.addRow("Width", self.prop_width)
        self.properties_form.addRow("Radius", self.prop_radius)
        self.properties_form.addRow("Arm length", self.prop_arm)
        self.properties_form.addRow("Height", self.prop_height)

        self.prop_x.valueChanged.connect(self.apply_position_properties)
        self.prop_y.valueChanged.connect(self.apply_position_properties)
        self.prop_rotation.valueChanged.connect(self.apply_rotation_property)
        self.prop_length.valueChanged.connect(self.apply_length_property)
        self.prop_width.valueChanged.connect(self.apply_width_property)
        self.prop_radius.valueChanged.connect(self.apply_radius_property)
        self.prop_arm.valueChanged.connect(self.apply_arm_property)
        self.prop_height.valueChanged.connect(self.apply_height_property)

        # Effective QLabs dimensions are read-only and derived from project scale.
        self.prop_effective = QLabel("")
        self.prop_effective.setWordWrap(True)
        self.prop_effective.setStyleSheet(
            "background: #20242a; padding: 6px; border-radius: 4px; color: #cfd6de;"
        )
        self.properties_form.addRow("QLabs effective", self.prop_effective)

        inspector_layout.addWidget(self.properties_group)

        # --------------------------------------------------------
        # Road marking visibility
        # --------------------------------------------------------
        self.markings_group = QGroupBox("ROAD MARKINGS")
        markings_form = QFormLayout(self.markings_group)

        self.prop_marking_edge_a = QCheckBox("Show")
        self.prop_marking_center = QCheckBox("Show")
        self.prop_marking_edge_b = QCheckBox("Show")
        self.prop_marking_end_bar = QCheckBox("Show")

        markings_form.addRow("Edge A", self.prop_marking_edge_a)
        markings_form.addRow("Center line", self.prop_marking_center)
        markings_form.addRow("Edge B", self.prop_marking_edge_b)
        markings_form.addRow("Road-end bar", self.prop_marking_end_bar)

        markings_note = QLabel(
            "Turn off individual spline markings. Edge A/B correspond to the "
            "two road boundaries; this is useful when a road is placed flush "
            "against a median wall."
        )
        markings_note.setWordWrap(True)
        markings_note.setStyleSheet("color: #aeb6bf; font-size: 11px;")
        markings_form.addRow(markings_note)

        self.prop_marking_edge_a.toggled.connect(self.apply_road_marking_properties)
        self.prop_marking_center.toggled.connect(self.apply_road_marking_properties)
        self.prop_marking_edge_b.toggled.connect(self.apply_road_marking_properties)
        self.prop_marking_end_bar.toggled.connect(self.apply_road_marking_properties)

        self.markings_group.setVisible(False)
        inspector_layout.addWidget(self.markings_group)

        # --------------------------------------------------------
        # QCar2 camera
        # --------------------------------------------------------
        self.camera_group = QGroupBox("QCAR2 CAMERA")
        camera_form = QFormLayout(self.camera_group)

        self.prop_camera_view = QComboBox()
        self.prop_camera_view.addItem(
            "Third person (trailing)",
            QCAR_CAMERA_THIRD_PERSON,
        )
        self.prop_camera_view.addItem(
            "First person (front CSI)",
            QCAR_CAMERA_FIRST_PERSON,
        )
        self.prop_camera_view.currentIndexChanged.connect(
            self.apply_camera_property
        )
        camera_form.addRow("View", self.prop_camera_view)

        camera_note = QLabel(
            "First person uses QCar2 CAMERA_CSI_FRONT. "
            "Third person uses CAMERA_TRAILING."
        )
        camera_note.setWordWrap(True)
        camera_note.setStyleSheet("color: #aeb6bf; font-size: 11px;")
        camera_form.addRow(camera_note)

        self.camera_group.setVisible(False)
        inspector_layout.addWidget(self.camera_group)

        # --------------------------------------------------------
        # QLabs actor properties
        # --------------------------------------------------------
        self.actor_group = QGroupBox("QLABS ACTOR")
        actor_form = QFormLayout(self.actor_group)

        self.prop_actor_z = self._make_spinbox(-100.0, 1000.0, 0.05, 3, " m")
        self.prop_actor_scale = self._make_spinbox(0.01, 100.0, 0.1, 2, "")
        self.prop_actor_scale_project = QCheckBox("Scale actor with project")

        self.prop_actor_configuration = QComboBox()
        for config in range(3):
            self.prop_actor_configuration.addItem(f"Configuration {config}", config)

        self.prop_traffic_color = QComboBox()
        self.prop_traffic_color.addItem("Off", "off")
        self.prop_traffic_color.addItem("Red", "red")
        self.prop_traffic_color.addItem("Yellow", "yellow")
        self.prop_traffic_color.addItem("Green", "green")

        self.prop_catalog_sign_type = QComboBox()
        for sign_key, sign_label, _family, _short in TRAFFIC_SIGN_CATALOG:
            self.prop_catalog_sign_type.addItem(sign_label, sign_key)

        self.prop_building_length = self._make_spinbox(0.1, 1000.0, 0.5, 2, " m")
        self.prop_building_width = self._make_spinbox(0.1, 1000.0, 0.5, 2, " m")
        self.prop_building_height = self._make_spinbox(0.1, 1000.0, 0.5, 2, " m")

        self.prop_building_r = QLineEdit(str(DEFAULT_BUILDING_RGB[0]))
        self.prop_building_g = QLineEdit(str(DEFAULT_BUILDING_RGB[1]))
        self.prop_building_b = QLineEdit(str(DEFAULT_BUILDING_RGB[2]))

        for rgb_input in (
            self.prop_building_r,
            self.prop_building_g,
            self.prop_building_b,
        ):
            rgb_input.setValidator(QIntValidator(0, 255, rgb_input))
            rgb_input.setMaximumWidth(52)
            rgb_input.setAlignment(Qt.AlignmentFlag.AlignCenter)

        building_rgb_widget = QWidget()
        building_rgb_layout = QHBoxLayout(building_rgb_widget)
        building_rgb_layout.setContentsMargins(0, 0, 0, 0)
        building_rgb_layout.setSpacing(5)
        building_rgb_layout.addWidget(QLabel("R"))
        building_rgb_layout.addWidget(self.prop_building_r)
        building_rgb_layout.addWidget(QLabel("G"))
        building_rgb_layout.addWidget(self.prop_building_g)
        building_rgb_layout.addWidget(QLabel("B"))
        building_rgb_layout.addWidget(self.prop_building_b)

        actor_form.addRow("Base Z", self.prop_actor_z)
        actor_form.addRow("Actor scale", self.prop_actor_scale)
        actor_form.addRow("Project scale", self.prop_actor_scale_project)
        actor_form.addRow("Configuration", self.prop_actor_configuration)
        actor_form.addRow("Initial light", self.prop_traffic_color)
        actor_form.addRow("Traffic sign", self.prop_catalog_sign_type)
        actor_form.addRow("Box length", self.prop_building_length)
        actor_form.addRow("Box width", self.prop_building_width)
        actor_form.addRow("Box height", self.prop_building_height)
        actor_form.addRow("Box RGB", building_rgb_widget)

        self.prop_actor_z.valueChanged.connect(self.apply_actor_properties)
        self.prop_actor_scale.valueChanged.connect(self.apply_actor_properties)
        self.prop_actor_scale_project.toggled.connect(self.apply_actor_properties)
        self.prop_actor_configuration.currentIndexChanged.connect(
            self.apply_actor_properties
        )
        self.prop_traffic_color.currentIndexChanged.connect(
            self.apply_actor_properties
        )
        self.prop_catalog_sign_type.currentIndexChanged.connect(
            self.apply_actor_properties
        )
        self.prop_building_length.valueChanged.connect(self.apply_actor_properties)
        self.prop_building_width.valueChanged.connect(self.apply_actor_properties)
        self.prop_building_height.valueChanged.connect(self.apply_actor_properties)
        self.prop_building_r.editingFinished.connect(self.apply_actor_properties)
        self.prop_building_g.editingFinished.connect(self.apply_actor_properties)
        self.prop_building_b.editingFinished.connect(self.apply_actor_properties)

        self.actor_group.setVisible(False)
        inspector_layout.addWidget(self.actor_group)

        # --------------------------------------------------------
        # Experiment properties
        # --------------------------------------------------------
        self.experiment_group = QGroupBox("EXPERIMENT")
        experiment_form = QFormLayout(self.experiment_group)

        self.prop_experiment_spawn_mode = QComboBox()
        self.prop_experiment_spawn_mode.addItem(
            "Immediate",
            EXPERIMENT_SPAWN_IMMEDIATE,
        )
        self.prop_experiment_spawn_mode.addItem(
            "Triggered",
            EXPERIMENT_SPAWN_TRIGGERED,
        )

        self.prop_person_configuration = QComboBox()
        for config in range(12):
            self.prop_person_configuration.addItem(
                f"Person {config}",
                config,
            )

        self.prop_animal_type = QComboBox()
        self.prop_animal_type.addItem("Goat", "goat")
        self.prop_animal_type.addItem("Sheep", "sheep")
        self.prop_animal_type.addItem("Cow", "cow")
        self.prop_animal_type.addItem("Camel", "camel")

        self.prop_experiment_move = QCheckBox("Move after activation")
        self.prop_destination_x = self._make_spinbox(
            -10000.0, 10000.0, 0.5, 2, " m"
        )
        self.prop_destination_y = self._make_spinbox(
            -10000.0, 10000.0, 0.5, 2, " m"
        )

        self.prop_movement_gait = QComboBox()

        self.prop_movement_mode = QComboBox()
        self.prop_movement_mode.addItem("Once", MOVEMENT_ONCE)
        self.prop_movement_mode.addItem("Loop", MOVEMENT_LOOP)
        self.prop_movement_mode.addItem("Ping-pong", MOVEMENT_PINGPONG)

        self.prop_despawn_on_finish = QCheckBox("Despawn after route")
        self.prop_secondary_qcar_speed = self._make_spinbox(0.1, 100.0, 0.5, 1, " m/s")

        self.path_widget = QWidget()
        path_widget = self.path_widget
        path_layout = QVBoxLayout(path_widget)
        path_layout.setContentsMargins(0, 0, 0, 0)
        path_layout.setSpacing(4)
        self.path_summary_label = QLabel("0 waypoints")
        self.path_summary_label.setStyleSheet("color: #aeb6bf;")
        path_layout.addWidget(self.path_summary_label)
        path_buttons = QHBoxLayout()
        self.path_draw_button = QPushButton("Draw / Add")
        self.path_remove_button = QPushButton("Remove last")
        self.path_clear_button = QPushButton("Clear")
        self.path_draw_button.clicked.connect(self.start_path_editing)
        self.path_remove_button.clicked.connect(self.remove_last_waypoint)
        self.path_clear_button.clicked.connect(self.clear_movement_path)
        path_buttons.addWidget(self.path_draw_button)
        path_buttons.addWidget(self.path_remove_button)
        path_buttons.addWidget(self.path_clear_button)
        path_layout.addLayout(path_buttons)

        self.prop_trigger_radius = self._make_spinbox(
            0.1, 1000.0, 0.5, 2, " m"
        )

        self.prop_trigger_action = QComboBox()
        self.prop_trigger_action.addItem(
            "Activate experiment actor",
            TRIGGER_ACTION_ACTIVATE_ACTOR,
        )
        self.prop_trigger_action.addItem(
            "Change traffic light",
            TRIGGER_ACTION_TRAFFIC_LIGHT,
        )

        self.prop_trigger_target = QComboBox()

        self.prop_trigger_traffic_color = QComboBox()
        self.prop_trigger_traffic_color.addItem("Off", "off")
        self.prop_trigger_traffic_color.addItem("Red", "red")
        self.prop_trigger_traffic_color.addItem("Yellow", "yellow")
        self.prop_trigger_traffic_color.addItem("Green", "green")

        self.prop_trigger_one_shot = QCheckBox("Fire once only")
        self.prop_trigger_one_shot.setChecked(True)

        experiment_form.addRow(
            "Spawn mode",
            self.prop_experiment_spawn_mode,
        )
        experiment_form.addRow(
            "Person",
            self.prop_person_configuration,
        )
        experiment_form.addRow(
            "Animal",
            self.prop_animal_type,
        )
        experiment_form.addRow(
            "Movement",
            self.prop_experiment_move,
        )
        experiment_form.addRow(
            "Destination X",
            self.prop_destination_x,
        )
        experiment_form.addRow(
            "Destination Y",
            self.prop_destination_y,
        )
        experiment_form.addRow(
            "Gait",
            self.prop_movement_gait,
        )
        experiment_form.addRow("Path", path_widget)
        experiment_form.addRow("Route mode", self.prop_movement_mode)
        experiment_form.addRow("Finish", self.prop_despawn_on_finish)
        experiment_form.addRow("QCar speed", self.prop_secondary_qcar_speed)
        experiment_form.addRow(
            "Trigger radius",
            self.prop_trigger_radius,
        )
        experiment_form.addRow(
            "Action",
            self.prop_trigger_action,
        )
        experiment_form.addRow(
            "Target",
            self.prop_trigger_target,
        )
        experiment_form.addRow(
            "Light color",
            self.prop_trigger_traffic_color,
        )
        experiment_form.addRow(
            "Behavior",
            self.prop_trigger_one_shot,
        )

        self.prop_experiment_spawn_mode.currentIndexChanged.connect(
            self.apply_experiment_properties
        )
        self.prop_person_configuration.currentIndexChanged.connect(
            self.apply_experiment_properties
        )
        self.prop_animal_type.currentIndexChanged.connect(
            self.apply_experiment_properties
        )
        self.prop_experiment_move.toggled.connect(
            self.apply_experiment_properties
        )
        self.prop_destination_x.valueChanged.connect(
            self.apply_experiment_properties
        )
        self.prop_destination_y.valueChanged.connect(
            self.apply_experiment_properties
        )
        self.prop_movement_gait.currentIndexChanged.connect(
            self.apply_experiment_properties
        )
        self.prop_movement_mode.currentIndexChanged.connect(self.apply_experiment_properties)
        self.prop_despawn_on_finish.toggled.connect(self.apply_experiment_properties)
        self.prop_secondary_qcar_speed.valueChanged.connect(self.apply_experiment_properties)
        self.prop_trigger_radius.valueChanged.connect(
            self.apply_experiment_properties
        )
        self.prop_trigger_action.currentIndexChanged.connect(
            self._trigger_action_changed
        )
        self.prop_trigger_target.currentIndexChanged.connect(
            self.apply_experiment_properties
        )
        self.prop_trigger_traffic_color.currentIndexChanged.connect(
            self.apply_experiment_properties
        )
        self.prop_trigger_one_shot.toggled.connect(
            self.apply_experiment_properties
        )

        self.experiment_group.setVisible(False)
        inspector_layout.addWidget(self.experiment_group)

        # --------------------------------------------------------
        # Lane-following guide line
        # --------------------------------------------------------
        self.guide_group = QGroupBox("LANE-FOLLOWING GUIDE")
        guide_form = QFormLayout(self.guide_group)

        self.prop_guide_enabled = QCheckBox("Enabled")
        self.prop_guide_position = QComboBox()
        self.prop_guide_position.addItem("Left lane", "left")
        self.prop_guide_position.addItem("Center", "center")
        self.prop_guide_position.addItem("Right lane", "right")
        self.prop_guide_position.addItem("Custom offset", "custom")
        self.prop_guide_offset = self._make_spinbox(-50.0, 50.0, 0.1, 2, " m")
        self.prop_guide_color = QComboBox()
        for name in ("yellow", "white", "blue", "red"):
            self.prop_guide_color.addItem(name.title(), name)
        self.prop_guide_color.addItem("Custom RGB", "custom")

        self.prop_guide_r = QLineEdit("255")
        self.prop_guide_g = QLineEdit("215")
        self.prop_guide_b = QLineEdit("0")

        for rgb_input in (
            self.prop_guide_r,
            self.prop_guide_g,
            self.prop_guide_b,
        ):
            rgb_input.setValidator(QIntValidator(0, 255, rgb_input))
            rgb_input.setMaximumWidth(52)
            rgb_input.setAlignment(Qt.AlignmentFlag.AlignCenter)

        rgb_widget = QWidget()
        rgb_layout = QHBoxLayout(rgb_widget)
        rgb_layout.setContentsMargins(0, 0, 0, 0)
        rgb_layout.setSpacing(5)
        rgb_layout.addWidget(QLabel("R"))
        rgb_layout.addWidget(self.prop_guide_r)
        rgb_layout.addWidget(QLabel("G"))
        rgb_layout.addWidget(self.prop_guide_g)
        rgb_layout.addWidget(QLabel("B"))
        rgb_layout.addWidget(self.prop_guide_b)

        self.prop_guide_width = self._make_spinbox(0.01, 5.0, 0.01, 2, " m")
        self.prop_guide_style = QComboBox()
        self.prop_guide_style.addItem("Solid", "solid")
        self.prop_guide_style.addItem("Dashed", "dashed")
        self.prop_guide_scale_width = QCheckBox("Scale width with project")

        guide_form.addRow("Guide", self.prop_guide_enabled)
        guide_form.addRow("Position", self.prop_guide_position)
        guide_form.addRow("Custom offset", self.prop_guide_offset)
        guide_form.addRow("Color", self.prop_guide_color)
        guide_form.addRow("RGB (0-255)", rgb_widget)
        guide_form.addRow("Design width", self.prop_guide_width)
        guide_form.addRow("Style", self.prop_guide_style)
        guide_form.addRow("QLabs width", self.prop_guide_scale_width)

        guide_note = QLabel(
            "Left/right place the guide at the center of each half of a two-lane road. "
            "T-junctions and 4-way intersections export guide splines on every straight arm. "
            "Disable width scaling if a 1:10 line becomes too thin for camera detection."
        )
        guide_note.setWordWrap(True)
        guide_note.setStyleSheet("color: #aeb6bf; font-size: 11px;")
        guide_form.addRow(guide_note)

        self.prop_guide_enabled.toggled.connect(self.apply_guide_properties)
        self.prop_guide_position.currentIndexChanged.connect(self.apply_guide_properties)
        self.prop_guide_offset.valueChanged.connect(self.apply_guide_properties)
        self.prop_guide_color.currentIndexChanged.connect(self.apply_guide_properties)
        self.prop_guide_r.editingFinished.connect(self.apply_guide_properties)
        self.prop_guide_g.editingFinished.connect(self.apply_guide_properties)
        self.prop_guide_b.editingFinished.connect(self.apply_guide_properties)
        self.prop_guide_width.valueChanged.connect(self.apply_guide_properties)
        self.prop_guide_style.currentIndexChanged.connect(self.apply_guide_properties)
        self.prop_guide_scale_width.toggled.connect(self.apply_guide_properties)

        self.guide_group.setVisible(False)
        inspector_layout.addWidget(self.guide_group)
        inspector_layout.addStretch(1)

        # The inspector is independently scrollable from the component
        # library. This keeps long property/experiment/path panels usable
        # without sacrificing canvas height.
        inspector_scroll = QScrollArea()
        inspector_scroll.setWidgetResizable(True)
        inspector_scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        inspector_scroll.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded
        )
        inspector_scroll.setWidget(inspector_contents)
        inspector_scroll.setMinimumWidth(345)
        inspector_scroll.setMaximumWidth(380)

        # --------------------------------------------------------
        # Canvas
        # --------------------------------------------------------
        canvas_container = QWidget()
        canvas_layout = QVBoxLayout(canvas_container)
        canvas_layout.setContentsMargins(0, 0, 0, 0)
        canvas_layout.addWidget(self.view)

        bottom = QHBoxLayout()
        self.cursor_label = QLabel("Cursor: X 0.0 m | Y 0.0 m")
        self.zoom_label = QLabel("Zoom: 100%")
        self.snap_status_label = QLabel("Endpoint/wall snap: ON")
        self.scale_status_label = QLabel("Scale: 1:1")
        bottom.addWidget(self.cursor_label)
        bottom.addStretch(1)
        self.grid_status_label = QLabel("Grid: adaptive")
        bottom.addWidget(self.grid_status_label)
        bottom.addSpacing(20)
        bottom.addWidget(self.scale_status_label)
        bottom.addSpacing(20)
        bottom.addWidget(self.snap_status_label)
        bottom.addSpacing(20)
        bottom.addWidget(self.zoom_label)
        canvas_layout.addLayout(bottom)

        body.addWidget(canvas_container, 1)
        body.addWidget(inspector_scroll)
        root.addLayout(body, 1)

        self.setCentralWidget(central)

    def toggle_selected_object_summary(self):
        """Collapse/expand only the summary contents.

        The selected object itself and all editable properties remain active.
        """
        currently_visible = self.selection_label.isVisible()

        self.selection_label.setVisible(not currently_visible)
        self.info_toggle_button.setText(
            "+" if currently_visible else "−"
        )
        self.info_toggle_button.setToolTip(
            "Expand selected-object summary"
            if currently_visible
            else "Minimize selected-object summary"
        )

        # Let the scroll area's size constraint update immediately.
        self.info_group.updateGeometry()

    # ------------------------------------------------------------
    # Undo history
    # ------------------------------------------------------------

    def _update_undo_controls(self):
        can_undo = self.undo_manager.can_undo
        label = self.undo_manager.next_undo_label
        tooltip = f"Undo {label} (Ctrl+Z)" if can_undo and label else "Undo last edit (Ctrl+Z)"

        if hasattr(self, "undo_action"):
            self.undo_action.setEnabled(can_undo)
            self.undo_action.setText(f"Undo {label}" if can_undo and label else "Undo")
        if hasattr(self, "undo_button"):
            self.undo_button.setEnabled(can_undo)
            self.undo_button.setToolTip(tooltip)

    def _begin_undo_transaction(self, label: str):
        if self._history_suspended:
            return
        self.undo_manager.begin(label, self.track_data())

    def _commit_undo_transaction(self):
        if self._history_suspended:
            return False
        changed = self.undo_manager.commit(self.track_data())
        self._update_undo_controls()
        return changed

    def begin_canvas_undo(self, label: str = "Move item"):
        """Begin a mouse-driven canvas edit; selection-only clicks are ignored."""
        self._begin_undo_transaction(label)

    def end_canvas_undo(self):
        self._commit_undo_transaction()

    def undo_last_action(self):
        entry = self.undo_manager.pop_undo()
        if entry is None:
            self._update_undo_controls()
            return

        label, snapshot = entry
        self._history_suspended = True
        try:
            self._restore_track_snapshot(snapshot)
        finally:
            self._history_suspended = False

        self._update_undo_controls()
        self.statusBar().showMessage(f"Undid: {label}", 3500)

    def _restore_track_snapshot(self, data: dict):
        """Restore one in-memory project snapshot without changing its file path."""
        self._set_project_scale_from_data(data.get("project", {}))
        self._set_environment_from_data(data.get("environment", {}))
        self._set_workspace_from_data(data.get("workspace", {}))
        self._set_workspace_platform_from_data(data.get("workspace_platform", {}))

        objects_data = data.get("objects", []) or []
        canvas_data = data.get("canvas")
        if not isinstance(canvas_data, dict):
            canvas_data = self._inferred_canvas_data(objects_data)
        self._set_canvas_from_data(canvas_data)
        self._set_scenery_fill_from_data(data.get("scenery_fill", {}))

        self.finish_path_editing()
        self.scene.clear()

        snap_was_enabled = self.scene.endpoint_snap_enabled
        self.scene.endpoint_snap_enabled = False
        try:
            for obj in objects_data:
                item = create_track_item_from_dict(obj)
                if item is not None:
                    self.scene.addItem(item)
        finally:
            self.scene.endpoint_snap_enabled = snap_was_enabled

        self._ensure_all_readable_identifiers()
        self.scene.clearSelection()
        self.scene.update()
        self.view.viewport().update()
        self.update_selection_info()

    def _build_actions(self):
        new_action = QAction("New", self)
        new_action.setShortcut(QKeySequence.StandardKey.New)
        new_action.triggered.connect(self.new_track)

        open_action = QAction("Open...", self)
        open_action.setShortcut(QKeySequence.StandardKey.Open)
        open_action.triggered.connect(self.load_track)

        save_action = QAction("Save", self)
        save_action.setShortcut(QKeySequence.StandardKey.Save)
        save_action.triggered.connect(self.save_track)

        save_as_action = QAction("Save As...", self)
        save_as_action.setShortcut(QKeySequence.StandardKey.SaveAs)
        save_as_action.triggered.connect(lambda: self.save_track(save_as=True))

        export_action = QAction("Export QLabs Setup...", self)
        export_action.setShortcut(QKeySequence("Ctrl+E"))
        export_action.triggered.connect(self.export_qlabs_setup)

        self.undo_action = QAction("Undo", self)
        self.undo_action.setShortcut(QKeySequence.StandardKey.Undo)
        self.undo_action.triggered.connect(self.undo_last_action)
        self.undo_action.setEnabled(False)
        self.addAction(self.undo_action)

        quit_action = QAction("Exit", self)
        quit_action.setShortcut(QKeySequence.StandardKey.Quit)
        quit_action.triggered.connect(self.close)

        rotate_action = QAction("Rotate +Step", self)
        rotate_action.setShortcut(QKeySequence("R"))
        rotate_action.triggered.connect(
            lambda: self.rotate_selected(self.rotation_step_deg)
        )
        self.addAction(rotate_action)

        rotate_back_action = QAction("Rotate -Step", self)
        rotate_back_action.setShortcut(QKeySequence("Shift+R"))
        rotate_back_action.triggered.connect(
            lambda: self.rotate_selected(-self.rotation_step_deg)
        )
        self.addAction(rotate_back_action)

        duplicate_action = QAction("Duplicate", self)
        duplicate_action.setShortcut(QKeySequence("Ctrl+D"))
        duplicate_action.triggered.connect(self.duplicate_selected)
        self.addAction(duplicate_action)

        delete_action = QAction("Delete", self)
        delete_action.setShortcut(QKeySequence("Delete"))
        delete_action.triggered.connect(self.delete_selected)
        self.addAction(delete_action)

        file_menu = self.menuBar().addMenu("File")
        file_menu.addAction(new_action)
        file_menu.addAction(open_action)
        file_menu.addSeparator()
        file_menu.addAction(save_action)
        file_menu.addAction(save_as_action)
        file_menu.addSeparator()
        file_menu.addAction(export_action)
        file_menu.addSeparator()
        file_menu.addAction(quit_action)

        edit_menu = self.menuBar().addMenu("Edit")
        edit_menu.addAction(self.undo_action)
        edit_menu.addSeparator()
        edit_menu.addAction(duplicate_action)
        edit_menu.addAction(rotate_action)
        edit_menu.addAction(rotate_back_action)
        edit_menu.addAction(delete_action)

    # ------------------------------------------------------------
    # Component creation
    # ------------------------------------------------------------

    def _used_readable_identifiers(self, exclude=None) -> set[str]:
        return {
            str(item.identifier)
            for item in self.scene.track_items()
            if item is not exclude and getattr(item, "identifier", "")
        }

    def _next_readable_identifier(self, prefix: str, start_index: int = 0, exclude=None) -> str:
        used = self._used_readable_identifiers(exclude=exclude)
        index = int(start_index)
        while f"{prefix}{index}" in used:
            index += 1
        return f"{prefix}{index}"

    def _assign_readable_identifier_if_needed(self, item: TrackItem):
        if getattr(item, "identifier", ""):
            item.set_readable_identifier(item.identifier)
            return

        if isinstance(item, QCar2StartItem):
            item.set_readable_identifier("QCar_0")
        elif isinstance(item, SecondaryQCarItem):
            item.set_readable_identifier(
                self._next_readable_identifier("QCar_", 1, exclude=item)
            )
        elif isinstance(item, PersonItem):
            item.set_readable_identifier(
                self._next_readable_identifier("person", 0, exclude=item)
            )
        elif isinstance(item, AnimalItem):
            item.set_readable_identifier(
                self._next_readable_identifier("animal", 0, exclude=item)
            )
        elif isinstance(item, TrafficLightItem):
            item.set_readable_identifier(
                self._next_readable_identifier("trafficLight", 0, exclude=item)
            )

    def _ensure_all_readable_identifiers(self):
        # Reserve QCar_0 for the primary controlled QCar before assigning
        # secondary vehicle aliases.
        ordered = sorted(
            self.scene.track_items(),
            key=lambda item: 0 if isinstance(item, QCar2StartItem) else 1,
        )
        for item in ordered:
            self._assign_readable_identifier_if_needed(item)

    def _add_item_at_view_center(self, item: TrackItem):
        self._begin_undo_transaction(f"Add {item.DISPLAY_NAME}")
        center_scene = self.view.mapToScene(self.view.viewport().rect().center())
        proposed = QPointF(
            snap_value(center_scene.x(), GRID_PIXELS),
            snap_value(center_scene.y(), GRID_PIXELS),
        )

        self._assign_readable_identifier_if_needed(item)

        self.scene.clearSelection()
        # Add first so normal TrackItem snapping/selection behavior applies.
        # The canvas rectangle limits auto-fill, but does not lock manual dragging.
        self.scene.addItem(item)
        item.setPos(proposed)
        item.setSelected(True)
        self.update_selection_info()
        self._commit_undo_transaction()

    def _workspace_new_road_width_m(self) -> float:
        """Width assigned to newly created road components in this workspace."""
        return workspace_mode_default_road_width(self.workspace_mode)

    def add_straight_road(self):
        self._add_item_at_view_center(
            StraightRoadItem(width_m=self._workspace_new_road_width_m())
        )

    def add_curve_45(self):
        self._add_item_at_view_center(
            Curve45RoadItem(width_m=self._workspace_new_road_width_m())
        )

    def add_curve_90(self):
        self._add_item_at_view_center(
            Curve90RoadItem(width_m=self._workspace_new_road_width_m())
        )

    def add_t_junction(self):
        self._add_item_at_view_center(
            TJunctionItem(width_m=self._workspace_new_road_width_m())
        )

    def add_cross_intersection(self):
        self._add_item_at_view_center(
            CrossIntersectionItem(width_m=self._workspace_new_road_width_m())
        )

    def add_road_end(self):
        self._add_item_at_view_center(
            RoadEndItem(width_m=self._workspace_new_road_width_m())
        )

    def add_median_wall(self):
        self._add_item_at_view_center(MedianWallItem())

    def add_traffic_light(self):
        self._add_item_at_view_center(TrafficLightItem())

    def add_stop_sign(self):
        self._add_item_at_view_center(StopSignItem())

    def add_yield_sign(self):
        self._add_item_at_view_center(YieldSignItem())

    def add_roundabout_sign(self):
        self._add_item_at_view_center(RoundaboutSignItem())

    def add_catalog_traffic_sign(self):
        item = CatalogTrafficSignItem()
        combo = getattr(self.top_bar, "catalog_sign_combo", None)
        if combo is not None and combo.currentData() is not None:
            item.sign_type = str(combo.currentData())
        self._add_item_at_view_center(item)

    def add_crosswalk(self):
        self._add_item_at_view_center(CrosswalkItem())

    def add_building_box(self):
        self._add_item_at_view_center(BuildingBoxItem())

    # Detailed building gallery
    def add_office_building(self):
        self._add_item_at_view_center(OfficeBuildingItem())

    def add_apartment_building(self):
        self._add_item_at_view_center(ApartmentBuildingItem())

    def add_shop_building(self):
        self._add_item_at_view_center(ShopBuildingItem())

    def add_stepped_tower(self):
        self._add_item_at_view_center(SteppedTowerItem())

    # Park gallery
    def add_round_tree(self):
        self._add_item_at_view_center(RoundTreeItem())

    def add_pine_tree(self):
        self._add_item_at_view_center(PineTreeItem())

    def add_park_bench(self):
        self._add_item_at_view_center(ParkBenchItem())

    def add_lamp_post(self):
        self._add_item_at_view_center(LampPostItem())

    def add_trash_bin(self):
        self._add_item_at_view_center(TrashBinItem())

    def add_planter(self):
        self._add_item_at_view_center(PlanterItem())

    def add_fountain(self):
        self._add_item_at_view_center(FountainItem())

    def auto_fill_open_space(self):
        """Fill open space inside the editable canvas with static scenery only.

        The fill service never creates moving/experiment actors, QCars, traffic
        controls, signs, crosswalks, or triggers. A configurable clear verge is
        preserved beyond every road edge for manually placed roadside objects.
        """
        self.scenery_fill_settings_changed()
        self._begin_undo_transaction("Auto-fill scenery")
        created = self.scenery_filler.fill_editable_open_space(
            style=self.scenery_fill_style,
            density=self.scenery_fill_density,
            roadside_reserve_m=self.roadside_reserve_m,
            building_road_band_m=self.building_road_band_m,
        )

        if created:
            self.scene.clearSelection()
            self.scene.update()
            self.statusBar().showMessage(
                f"Filled editable canvas with {len(created)} static scenery objects "
                f"({self.scenery_fill_style}, {self.scenery_fill_density}; "
                f"roadside reserve {self.roadside_reserve_m:.1f} m).",
                7000,
            )
        else:
            self.statusBar().showMessage(
                "No suitable open space was found inside the editable canvas. "
                "Try lower density, a larger canvas, or a smaller roadside reserve.",
                8000,
            )

        self.update_selection_info()
        self._commit_undo_transaction()

    # ------------------------------------------------------------
    # Editable canvas / scenery fill
    # ------------------------------------------------------------

    def canvas_area_changed(self, *args):
        if not hasattr(self, "canvas_width_spin"):
            return
        self.canvas_width_m = float(self.canvas_width_spin.value())
        self.canvas_height_m = float(self.canvas_height_spin.value())
        self.scene.set_editable_area_size(
            self.canvas_width_m,
            self.canvas_height_m,
        )
        if self.workspace_mode == WORKSPACE_OPEN_ROAD:
            self.scene.setSceneRect(
                self._open_road_scene_rect().united(
                    self.scene.editable_area_rect().adjusted(-500.0, -500.0, 500.0, 500.0)
                )
            )
        elif self.workspace_mode != WORKSPACE_CUSTOM:
            self.scene.setSceneRect(
                self._workspace_profile_scene_rect().united(
                    self.scene.editable_area_rect().adjusted(-500.0, -500.0, 500.0, 500.0)
                )
            )
        else:
            self.scene.setSceneRect(self._custom_scene_rect())
        self.view.viewport().update()
        self.statusBar().showMessage(
            f"Editable canvas: {self.canvas_width_m:.0f} m × {self.canvas_height_m:.0f} m",
            3500,
        )

    def fit_editable_area(self, *args):
        rect = self.scene.editable_area_rect().adjusted(-20.0, -20.0, 20.0, 20.0)
        self.view.fitInView(rect, Qt.AspectRatioMode.KeepAspectRatio)
        self.update_zoom_label()

    def scenery_fill_settings_changed(self, *args):
        if not hasattr(self, "fill_style_combo"):
            return
        self.scenery_fill_style = str(
            self.fill_style_combo.currentData() or DEFAULT_SCENERY_FILL_STYLE
        )
        self.scenery_fill_density = str(
            self.fill_density_combo.currentData() or DEFAULT_SCENERY_FILL_DENSITY
        )
        self.roadside_reserve_m = max(
            0.0,
            float(self.roadside_reserve_spin.value()),
        )
        self.building_road_band_m = max(
            self.roadside_reserve_m + 2.0,
            float(self.building_road_band_spin.value()),
        )

    def _set_canvas_from_data(self, data: dict):
        data = data or {}
        self.canvas_width_m = max(1.0, float(data.get("width_m", DEFAULT_CANVAS_WIDTH_M)))
        self.canvas_height_m = max(1.0, float(data.get("height_m", DEFAULT_CANVAS_HEIGHT_M)))

        if hasattr(self, "canvas_width_spin"):
            self.canvas_width_spin.blockSignals(True)
            self.canvas_height_spin.blockSignals(True)
            try:
                self.canvas_width_spin.setValue(self.canvas_width_m)
                self.canvas_height_spin.setValue(self.canvas_height_m)
            finally:
                self.canvas_width_spin.blockSignals(False)
                self.canvas_height_spin.blockSignals(False)

        self.scene.set_editable_area_size(self.canvas_width_m, self.canvas_height_m)
        if self.workspace_mode == WORKSPACE_OPEN_ROAD:
            self.scene.setSceneRect(
                self._open_road_scene_rect().united(
                    self.scene.editable_area_rect().adjusted(-500.0, -500.0, 500.0, 500.0)
                )
            )
        elif self.workspace_mode != WORKSPACE_CUSTOM:
            self.scene.setSceneRect(
                self._workspace_profile_scene_rect().united(
                    self.scene.editable_area_rect().adjusted(-500.0, -500.0, 500.0, 500.0)
                )
            )
        else:
            self.scene.setSceneRect(self._custom_scene_rect())
        self.view.viewport().update()

    def _set_scenery_fill_from_data(self, data: dict):
        data = data or {}
        self.scenery_fill_style = str(
            data.get("style", DEFAULT_SCENERY_FILL_STYLE)
        )
        if self.scenery_fill_style not in {"urban", "suburban", "park"}:
            self.scenery_fill_style = DEFAULT_SCENERY_FILL_STYLE

        self.scenery_fill_density = str(
            data.get("density", DEFAULT_SCENERY_FILL_DENSITY)
        )
        if self.scenery_fill_density not in {"low", "medium", "high"}:
            self.scenery_fill_density = DEFAULT_SCENERY_FILL_DENSITY

        self.roadside_reserve_m = max(
            0.0,
            float(data.get("roadside_reserve_m", DEFAULT_ROADSIDE_RESERVE_M)),
        )
        self.building_road_band_m = max(
            self.roadside_reserve_m + 2.0,
            float(data.get("building_road_band_m", DEFAULT_BUILDING_ROAD_BAND_M)),
        )

        if hasattr(self, "fill_style_combo"):
            controls = (
                self.fill_style_combo,
                self.fill_density_combo,
                self.roadside_reserve_spin,
                self.building_road_band_spin,
            )
            for control in controls:
                control.blockSignals(True)
            try:
                index = self.fill_style_combo.findData(self.scenery_fill_style)
                self.fill_style_combo.setCurrentIndex(max(0, index))
                index = self.fill_density_combo.findData(self.scenery_fill_density)
                self.fill_density_combo.setCurrentIndex(max(0, index))
                self.roadside_reserve_spin.setValue(self.roadside_reserve_m)
                self.building_road_band_spin.setValue(self.building_road_band_m)
            finally:
                for control in controls:
                    control.blockSignals(False)

    @staticmethod
    def _inferred_canvas_data(objects: list[dict]) -> dict:
        """Choose a sensible canvas for older files without canvas metadata."""
        if not objects:
            return {
                "width_m": DEFAULT_CANVAS_WIDTH_M,
                "height_m": DEFAULT_CANVAS_HEIGHT_M,
            }

        max_x = max(abs(float(obj.get("x", 0.0))) for obj in objects)
        max_y = max(abs(float(obj.get("y", 0.0))) for obj in objects)
        return {
            "width_m": max(DEFAULT_CANVAS_WIDTH_M, 2.0 * (max_x + 25.0)),
            "height_m": max(DEFAULT_CANVAS_HEIGHT_M, 2.0 * (max_y + 25.0)),
        }

    def add_person(self):
        item = PersonItem()
        center = self.view.mapToScene(
            self.view.viewport().rect().center()
        )
        x_m, y_m = scene_to_world(center)
        item.destination_x_m = x_m
        item.destination_y_m = y_m
        self._add_item_at_view_center(item)

    def add_animal(self):
        item = AnimalItem()
        center = self.view.mapToScene(
            self.view.viewport().rect().center()
        )
        x_m, y_m = scene_to_world(center)
        item.destination_x_m = x_m
        item.destination_y_m = y_m
        self._add_item_at_view_center(item)

    def add_trigger_zone(self):
        self._add_item_at_view_center(TriggerZoneItem())

    def add_secondary_qcar(self):
        item = SecondaryQCarItem()
        center = self.view.mapToScene(self.view.viewport().rect().center())
        x_m, y_m = scene_to_world(center)
        item.destination_x_m = x_m
        item.destination_y_m = y_m
        self._add_item_at_view_center(item)

    def add_qcar2_start(self):
        existing = [
            item
            for item in self.scene.track_items()
            if isinstance(item, QCar2StartItem)
        ]

        if existing:
            self.scene.clearSelection()
            existing[0].setSelected(True)
            self.view.centerOn(existing[0])
            self.update_selection_info()
            QMessageBox.information(
                self,
                "QCar2 Start",
                "This project already has a QCar2 Start marker. "
                "The existing marker has been selected.",
            )
            return

        self._add_item_at_view_center(QCar2StartItem())

    def environment_settings_changed(self, *args):
        self.environment_enabled = self.environment_enabled_checkbox.isChecked()
        self.environment_weather = str(self.weather_combo.currentData() or "clear_skies")
        self.environment_time_of_day = float(self.time_of_day_spin.value())

    def _set_environment_from_data(self, data: dict):
        self.environment_enabled = bool(data.get("enabled", True))
        self.environment_weather = str(data.get("weather", "clear_skies"))
        self.environment_time_of_day = max(0.0, min(24.0, float(data.get("time_of_day", 12.0))))

        self.environment_enabled_checkbox.blockSignals(True)
        self.weather_combo.blockSignals(True)
        self.time_of_day_spin.blockSignals(True)
        try:
            self.environment_enabled_checkbox.setChecked(self.environment_enabled)
            idx = self.weather_combo.findData(self.environment_weather)
            self.weather_combo.setCurrentIndex(max(0, idx))
            self.time_of_day_spin.setValue(self.environment_time_of_day)
        finally:
            self.environment_enabled_checkbox.blockSignals(False)
            self.weather_combo.blockSignals(False)
            self.time_of_day_spin.blockSignals(False)

    # ------------------------------------------------------------
    # Workspace cover platform
    # ------------------------------------------------------------

    def _workspace_platform_profile_data(self) -> dict:
        return workspace_platform_profile(self.workspace_platform_profile)

    def workspace_platform_project_data(self) -> dict:
        """Return the resolved platform geometry written into project/export data."""
        profile = self._workspace_platform_profile_data()
        top_z = float(self.workspace_platform_top_z_m)
        bottom_z = min(float(self.workspace_platform_bottom_z_m), top_z - 0.05)
        return {
            "enabled": bool(self.workspace_platform_enabled),
            "profile": self.workspace_platform_profile,
            "workspace_label": str(profile["label"]),
            "workspace_module": str(profile["module"]),
            "size_x_m": float(profile["size_x_m"]),
            "size_y_m": float(profile["size_y_m"]),
            "center_x_m": float(profile.get("center_x_m", 0.0)),
            "center_y_m": float(profile.get("center_y_m", 0.0)),
            "bottom_z_m": bottom_z,
            "top_z_m": top_z,
            "rgb": list(self.workspace_platform_color_rgb),
            "environment_support": str(profile.get("environment_support", "unknown")),
            "size_note": str(profile.get("size_note", "")),
        }

    def _update_workspace_platform_info(self):
        if not hasattr(self, "workspace_platform_info_label"):
            return
        data = self.workspace_platform_project_data()
        sx = data["size_x_m"]
        sy = data["size_y_m"]
        if max(sx, sy) >= 1000.0:
            size_text = f"{sx / 1000.0:g} × {sy / 1000.0:g} km"
        else:
            size_text = f"{sx:g} × {sy:g} m"
        support = data.get("environment_support", "unknown")
        if support == "confirmed":
            support_text = "weather documented"
        elif support == "indoor":
            support_text = "indoor workspace"
        else:
            support_text = "weather support varies by QLabs workspace/release"
        self.workspace_platform_info_label.setText(
            f"{size_text}  •  {support_text}"
        )
        self.workspace_platform_info_label.setToolTip(
            data.get("size_note", "")
            + "\nTop Z is an editor-selected cover height, not a published workspace height."
        )

    def workspace_platform_profile_changed(self, *args):
        self._begin_undo_transaction("Change workspace cover profile")
        key = str(
            self.workspace_platform_profile_combo.currentData()
            or DEFAULT_WORKSPACE_PLATFORM_PROFILE
        )
        profile = workspace_platform_profile(key)
        self.workspace_platform_profile = key

        # A profile change deliberately loads a sensible starting height.  The
        # user can immediately tune Top Z/Bottom Z for their QLabs release.
        self.workspace_platform_top_z_spin.blockSignals(True)
        self.workspace_platform_bottom_z_spin.blockSignals(True)
        try:
            self.workspace_platform_top_z_spin.setValue(
                float(profile["default_top_z_m"])
            )
            self.workspace_platform_bottom_z_spin.setValue(
                float(profile["default_bottom_z_m"])
            )
        finally:
            self.workspace_platform_top_z_spin.blockSignals(False)
            self.workspace_platform_bottom_z_spin.blockSignals(False)

        self.workspace_platform_top_z_m = float(profile["default_top_z_m"])
        self.workspace_platform_bottom_z_m = float(profile["default_bottom_z_m"])
        self._update_workspace_platform_info()
        self.view.viewport().update()
        self._commit_undo_transaction()

    def workspace_platform_settings_changed(self, *args):
        self._begin_undo_transaction("Change workspace cover")
        self.workspace_platform_enabled = (
            self.workspace_platform_enabled_checkbox.isChecked()
        )
        self.workspace_platform_profile = str(
            self.workspace_platform_profile_combo.currentData()
            or DEFAULT_WORKSPACE_PLATFORM_PROFILE
        )
        self.workspace_platform_top_z_m = float(
            self.workspace_platform_top_z_spin.value()
        )
        self.workspace_platform_bottom_z_m = float(
            self.workspace_platform_bottom_z_spin.value()
        )

        if self.workspace_platform_bottom_z_m >= self.workspace_platform_top_z_m:
            self.workspace_platform_bottom_z_m = self.workspace_platform_top_z_m - 0.05
            self.workspace_platform_bottom_z_spin.blockSignals(True)
            try:
                self.workspace_platform_bottom_z_spin.setValue(
                    self.workspace_platform_bottom_z_m
                )
            finally:
                self.workspace_platform_bottom_z_spin.blockSignals(False)

        self._update_workspace_platform_info()
        self.view.viewport().update()
        self._commit_undo_transaction()

    def _set_workspace_platform_from_data(self, data: dict):
        if not isinstance(data, dict):
            data = {}

        key = str(data.get("profile", DEFAULT_WORKSPACE_PLATFORM_PROFILE))
        if key not in WORKSPACE_PLATFORM_PROFILES:
            key = DEFAULT_WORKSPACE_PLATFORM_PROFILE
        profile = workspace_platform_profile(key)

        self.workspace_platform_enabled = bool(data.get("enabled", False))
        self.workspace_platform_profile = key
        self.workspace_platform_top_z_m = float(
            data.get("top_z_m", profile["default_top_z_m"])
        )
        self.workspace_platform_bottom_z_m = float(
            data.get("bottom_z_m", profile["default_bottom_z_m"])
        )
        if self.workspace_platform_bottom_z_m >= self.workspace_platform_top_z_m:
            self.workspace_platform_bottom_z_m = self.workspace_platform_top_z_m - 0.05

        rgb = data.get("rgb", DEFAULT_WORKSPACE_PLATFORM_COLOR_RGB)
        if not isinstance(rgb, (list, tuple)) or len(rgb) != 3:
            rgb = DEFAULT_WORKSPACE_PLATFORM_COLOR_RGB
        self.workspace_platform_color_rgb = [
            max(0, min(255, int(value))) for value in rgb
        ]

        widgets = (
            self.workspace_platform_enabled_checkbox,
            self.workspace_platform_profile_combo,
            self.workspace_platform_top_z_spin,
            self.workspace_platform_bottom_z_spin,
        )
        for widget in widgets:
            widget.blockSignals(True)
        try:
            self.workspace_platform_enabled_checkbox.setChecked(
                self.workspace_platform_enabled
            )
            index = self.workspace_platform_profile_combo.findData(key)
            self.workspace_platform_profile_combo.setCurrentIndex(max(0, index))
            self.workspace_platform_top_z_spin.setValue(
                self.workspace_platform_top_z_m
            )
            self.workspace_platform_bottom_z_spin.setValue(
                self.workspace_platform_bottom_z_m
            )
        finally:
            for widget in widgets:
                widget.blockSignals(False)

        self._update_workspace_platform_info()
        if hasattr(self, "view"):
            self.view.viewport().update()

    def workspace_platform_scene_rect(self) -> QRectF:
        data = self.workspace_platform_project_data()
        width_px = data["size_x_m"] * PIXELS_PER_METER
        height_px = data["size_y_m"] * PIXELS_PER_METER
        center = world_to_scene(data["center_x_m"], data["center_y_m"])
        return QRectF(
            center.x() - width_px / 2.0,
            center.y() - height_px / 2.0,
            width_px,
            height_px,
        )

    def fit_workspace_platform(self):
        rect = self.workspace_platform_scene_rect()
        if rect.isNull() or rect.isEmpty():
            return
        self.view.fitInView(
            rect.adjusted(-40.0, -40.0, 40.0, 40.0),
            Qt.AspectRatioMode.KeepAspectRatio,
        )
        self.update_zoom_label()

    def draw_workspace_platform_reference(self, painter: QPainter, visible_rect: QRectF):
        if not self.workspace_platform_enabled:
            return
        platform_rect = self.workspace_platform_scene_rect()
        if not platform_rect.intersects(visible_rect):
            return

        painter.save()
        painter.setBrush(QColor(78, 105, 116, 34))
        outline = QPen(QColor(90, 205, 230, 210), 2, Qt.PenStyle.DashLine)
        outline.setCosmetic(True)
        painter.setPen(outline)
        painter.drawRect(platform_rect)
        painter.restore()

    # ------------------------------------------------------------
    # Workspace reference
    # ------------------------------------------------------------

    def workspace_mode_changed(self, *args):
        self._begin_undo_transaction("Change workspace")
        self.workspace_mode = str(
            self.workspace_mode_combo.currentData()
            or WORKSPACE_CUSTOM
        )

        # Each native workspace gets a tested/default spline height so QLabs
        # spline roads/guide lines are not buried below the native road mesh.
        # Open Road uses 1.2 m. The value remains editable.
        self.workspace_spline_z_m = workspace_mode_default_spline_z(
            self.workspace_mode
        )
        self.workspace_spline_z_spin.blockSignals(True)
        try:
            self.workspace_spline_z_spin.setValue(self.workspace_spline_z_m)
        finally:
            self.workspace_spline_z_spin.blockSignals(False)

        # Keep the optional cover-box profile aligned with the selected main
        # workspace, without automatically enabling the cover itself.
        self._sync_workspace_platform_profile_to_mode()
        self._apply_workspace_mode(fit_reference=True)
        self._refresh_scale_ui()
        self._commit_undo_transaction()

    def workspace_spline_z_changed(self, *args):
        self._begin_undo_transaction("Change workspace spline Z")
        self.workspace_spline_z_m = float(self.workspace_spline_z_spin.value())
        self._apply_workspace_mode(fit_reference=False)
        self._commit_undo_transaction()

    def _sync_workspace_platform_profile_to_mode(self):
        profile_key = workspace_profile_key_for_mode(self.workspace_mode)
        if profile_key not in WORKSPACE_PLATFORM_PROFILES:
            return

        profile = workspace_platform_profile(profile_key)
        self.workspace_platform_profile = profile_key
        self.workspace_platform_top_z_m = float(profile["default_top_z_m"])
        self.workspace_platform_bottom_z_m = float(profile["default_bottom_z_m"])

        widgets = (
            self.workspace_platform_profile_combo,
            self.workspace_platform_top_z_spin,
            self.workspace_platform_bottom_z_spin,
        )
        for widget in widgets:
            widget.blockSignals(True)
        try:
            index = self.workspace_platform_profile_combo.findData(profile_key)
            if index >= 0:
                self.workspace_platform_profile_combo.setCurrentIndex(index)
            self.workspace_platform_top_z_spin.setValue(
                self.workspace_platform_top_z_m
            )
            self.workspace_platform_bottom_z_spin.setValue(
                self.workspace_platform_bottom_z_m
            )
        finally:
            for widget in widgets:
                widget.blockSignals(False)

        self._update_workspace_platform_info()

    def workspace_display_changed(self, *args):
        self.workspace_show_road_reference = (
            self.workspace_show_road_checkbox.isChecked()
        )
        self.workspace_show_navigation_regions = (
            self.workspace_show_nav_checkbox.isChecked()
        )
        self.workspace_show_reference_points = (
            self.workspace_show_points_checkbox.isChecked()
        )
        self.workspace_show_reference_labels = (
            self.workspace_show_labels_checkbox.isChecked()
        )

        self.view.viewport().update()

    def _set_workspace_from_data(self, workspace: dict):
        mode = str(
            workspace.get("mode", WORKSPACE_CUSTOM)
        )

        if mode not in set(WORKSPACE_MODES):
            mode = WORKSPACE_CUSTOM

        spline_z = float(
            workspace.get(
                "spline_z_m",
                workspace_mode_default_spline_z(mode),
            )
        )

        road = bool(
            workspace.get(
                "show_road_reference",
                True,
            )
        )
        nav = bool(
            workspace.get(
                "show_navigation_regions",
                True,
            )
        )
        points = bool(
            workspace.get(
                "show_reference_points",
                True,
            )
        )
        labels = bool(
            workspace.get(
                "show_reference_labels",
                True,
            )
        )

        widgets = (
            self.workspace_mode_combo,
            self.workspace_spline_z_spin,
            self.workspace_show_road_checkbox,
            self.workspace_show_nav_checkbox,
            self.workspace_show_points_checkbox,
            self.workspace_show_labels_checkbox,
        )

        for widget in widgets:
            widget.blockSignals(True)

        try:
            index = self.workspace_mode_combo.findData(
                mode
            )
            self.workspace_mode_combo.setCurrentIndex(
                max(0, index)
            )
            self.workspace_spline_z_spin.setValue(spline_z)

            self.workspace_show_road_checkbox.setChecked(
                road
            )
            self.workspace_show_nav_checkbox.setChecked(
                nav
            )
            self.workspace_show_points_checkbox.setChecked(
                points
            )
            self.workspace_show_labels_checkbox.setChecked(
                labels
            )
        finally:
            for widget in widgets:
                widget.blockSignals(False)

        self.workspace_mode = mode
        self.workspace_spline_z_m = spline_z
        self.workspace_show_road_reference = road
        self.workspace_show_navigation_regions = nav
        self.workspace_show_reference_points = points
        self.workspace_show_reference_labels = labels

        self._apply_workspace_mode(
            fit_reference=False
        )

    def _open_road_scene_rect(
        self,
        margin_m: float = 500.0,
    ) -> QRectF:
        bounds = self.open_road_reference.get(
            "bounds",
            {},
        )

        min_x = float(
            bounds.get("min_x", -9500.0)
        )
        max_x = float(
            bounds.get("max_x", 9500.0)
        )
        min_y = float(
            bounds.get("min_y", -5000.0)
        )
        max_y = float(
            bounds.get("max_y", 500.0)
        )

        left = (
            min_x
            - margin_m
        ) * PIXELS_PER_METER
        right = (
            max_x
            + margin_m
        ) * PIXELS_PER_METER

        # Qt Y grows downward, so larger world Y is the scene top.
        top = -(
            max_y
            + margin_m
        ) * PIXELS_PER_METER
        bottom = -(
            min_y
            - margin_m
        ) * PIXELS_PER_METER

        return QRectF(
            left,
            top,
            right - left,
            bottom - top,
        )

    def _workspace_profile_scene_rect(self, mode: str | None = None) -> QRectF:
        """Return the documented footprint for a native workspace mode."""
        selected_mode = self.workspace_mode if mode is None else str(mode)
        profile = workspace_mode_profile(selected_mode)
        width_px = float(profile["size_x_m"]) * PIXELS_PER_METER
        height_px = float(profile["size_y_m"]) * PIXELS_PER_METER
        center = world_to_scene(
            float(profile.get("center_x_m", 0.0)),
            float(profile.get("center_y_m", 0.0)),
        )
        return QRectF(
            center.x() - width_px / 2.0,
            center.y() - height_px / 2.0,
            width_px,
            height_px,
        )

    def _custom_scene_rect(self) -> QRectF:
        default_rect = QRectF(-4000.0, -4000.0, 8000.0, 8000.0)
        editable_rect = self.scene.editable_area_rect().adjusted(
            -500.0, -500.0, 500.0, 500.0
        )
        result = default_rect.united(editable_rect)

        items_rect = self.scene.itemsBoundingRect()
        if not items_rect.isNull():
            result = result.united(
                items_rect.adjusted(-1000.0, -1000.0, 1000.0, 1000.0)
            )
        return result

    def _apply_workspace_mode(
        self,
        fit_reference: bool = False,
    ):
        open_road = self.workspace_mode == WORKSPACE_OPEN_ROAD
        profile = workspace_mode_profile(self.workspace_mode)
        label = workspace_mode_label(self.workspace_mode)

        # Open Road is the only workspace with the detailed 2-D reference
        # overlay. The fit button remains available for all other workspaces
        # and fits their documented footprint instead.
        for widget in (
            self.workspace_show_road_checkbox,
            self.workspace_show_nav_checkbox,
            self.workspace_show_points_checkbox,
            self.workspace_show_labels_checkbox,
        ):
            widget.setEnabled(open_road)
        self.fit_workspace_button.setEnabled(True)

        if open_road:
            # Open Road reference coordinates are native QLabs meters.
            if self.project_scale_combo.currentIndex() != 0:
                self.project_scale_combo.setCurrentIndex(0)

            self.project_scale_combo.setEnabled(False)
            self.custom_scale_denominator.setEnabled(False)

            self.scale_help_label.setText(
                "Open Road reference coordinates are native QLabs meters. "
                "Project scale is locked to 1:1 while this workspace is selected."
            )

            calibration = self.open_road_reference.get("calibration", {})
            rms = calibration.get("anchor_rms_error_m", None)
            accuracy_text = (
                f" Approximate anchor-fit RMS: {float(rms):.1f} m."
                if rms is not None
                else ""
            )

            self.workspace_reference_note.setText(
                "2-D documentation-derived placement overlay only; "
                "it contains no road elevation/Z and is never exported. "
                f"Spline Z defaults to {self.workspace_spline_z_m:.2f} m so "
                "custom splines remain above the native road mesh. "
                f"Visual road width ≈ {OPEN_ROAD_REFERENCE_TOTAL_WIDTH_M:.1f} m "
                f"({OPEN_ROAD_REFERENCE_LANES_PER_SIDE} lanes each direction, "
                f"{OPEN_ROAD_REFERENCE_LANE_WIDTH_M:.1f} m/lane + "
                f"{OPEN_ROAD_REFERENCE_SEPARATOR_WIDTH_M:.1f} m separator). "
                f"New road components default to one carriageway: "
                f"{OPEN_ROAD_REFERENCE_CARRIAGEWAY_WIDTH_M:.1f} m."
                + accuracy_text
                + f" Source data: {self.open_road_reference_source}."
            )

            self.scene.setSceneRect(
                self._open_road_scene_rect().united(
                    self.scene.editable_area_rect().adjusted(
                        -500.0, -500.0, 500.0, 500.0
                    )
                )
            )
        else:
            self.project_scale_combo.setEnabled(True)
            self.custom_scale_denominator.setEnabled(True)

            self.scale_help_label.setText(
                "Canvas values stay in full-scale design meters. "
                "The selected scale is applied to QLabs effective dimensions/export."
            )

            sx = float(profile["size_x_m"])
            sy = float(profile["size_y_m"])
            self.workspace_reference_note.setText(
                f"{label} selected. No detailed road-reference overlay is packaged "
                f"for this workspace. Documented footprint: {sx:g} × {sy:g} m. "
                f"Native-workspace spline Z: {self.workspace_spline_z_m:.2f} m. "
                "Use the normal road components to design the custom overlay."
            )

            if self.workspace_mode == WORKSPACE_CUSTOM:
                self.scene.setSceneRect(self._custom_scene_rect())
            else:
                self.scene.setSceneRect(
                    self._workspace_profile_scene_rect().united(
                        self.scene.editable_area_rect().adjusted(
                            -500.0, -500.0, 500.0, 500.0
                        )
                    )
                )

        if fit_reference:
            self.fit_selected_workspace()

        self.view.viewport().update()
        self.update_zoom_label()

    def fit_selected_workspace(self):
        """Fit Open Road reference or the selected native workspace footprint."""
        if self.workspace_mode == WORKSPACE_OPEN_ROAD:
            rect = self._open_road_scene_rect(margin_m=250.0)
        elif self.workspace_mode == WORKSPACE_CUSTOM:
            rect = self.scene.editable_area_rect().adjusted(-40.0, -40.0, 40.0, 40.0)
        else:
            rect = self._workspace_profile_scene_rect().adjusted(-40.0, -40.0, 40.0, 40.0)

        if rect.isValid() and not rect.isEmpty():
            self.view.fitInView(rect, Qt.AspectRatioMode.KeepAspectRatio)
            self.update_zoom_label()

    def fit_open_road_reference(self):
        # Backward-compatible action target used by older UI code.
        self.fit_selected_workspace()

    def draw_workspace_reference(
        self,
        painter: QPainter,
        rect: QRectF,
    ):
        if (
            self.workspace_mode
            != WORKSPACE_OPEN_ROAD
        ):
            return

        reference = self.open_road_reference
        view_scale = max(
            abs(self.view.transform().m11()),
            1e-9,
        )

        # --------------------------------------------------------
        # Navigation-region overlay
        # --------------------------------------------------------
        if self.workspace_show_navigation_regions:
            nav_pen = QPen(
                QColor(
                    255,
                    95,
                    75,
                    210,
                ),
                2,
            )
            nav_pen.setCosmetic(True)

            painter.setPen(nav_pen)
            painter.setBrush(
                QColor(
                    255,
                    80,
                    70,
                    32,
                )
            )

            for region in reference.get(
                "navigation_regions",
                [],
            ):
                polygon = region.get(
                    "polygon",
                    [],
                )

                if len(polygon) < 3:
                    continue

                path = QPainterPath()

                first = world_to_scene(
                    float(polygon[0][0]),
                    float(polygon[0][1]),
                )
                path.moveTo(first)

                for point in polygon[1:]:
                    path.lineTo(
                        world_to_scene(
                            float(point[0]),
                            float(point[1]),
                        )
                    )

                path.closeSubpath()
                painter.drawPath(path)

        # --------------------------------------------------------
        # Documentation-derived road loop + approximate lane width
        # --------------------------------------------------------
        if self.workspace_show_road_reference:
            road_data = reference.get(
                "road_reference",
                {},
            )
            points = road_data.get(
                "points",
                [],
            )
            road_closed = bool(
                road_data.get(
                    "closed",
                    False,
                )
            )

            if len(points) >= 2:
                road_path = _world_polyline_path(
                    points,
                    road_closed,
                )

                # Physical-width road band. This is deliberately NOT a
                # cosmetic pen: its width is expressed in world metres so
                # QCar/start markers can be compared against it at 1:1 scale.
                road_surface_pen = QPen(
                    QColor(
                        74,
                        80,
                        88,
                        210,
                    ),
                    OPEN_ROAD_REFERENCE_TOTAL_WIDTH_M
                    * PIXELS_PER_METER,
                )
                road_surface_pen.setCosmetic(False)
                road_surface_pen.setJoinStyle(
                    Qt.PenJoinStyle.RoundJoin
                )
                road_surface_pen.setCapStyle(
                    Qt.PenCapStyle.RoundCap
                )
                painter.setPen(road_surface_pen)
                painter.setBrush(
                    Qt.BrushStyle.NoBrush
                )
                painter.drawPath(road_path)

                # Approximate center separator band.
                separator_pen = QPen(
                    QColor(
                        40,
                        44,
                        50,
                        245,
                    ),
                    OPEN_ROAD_REFERENCE_SEPARATOR_WIDTH_M
                    * PIXELS_PER_METER,
                )
                separator_pen.setCosmetic(False)
                separator_pen.setJoinStyle(
                    Qt.PenJoinStyle.RoundJoin
                )
                separator_pen.setCapStyle(
                    Qt.PenCapStyle.RoundCap
                )
                painter.setPen(separator_pen)
                painter.drawPath(road_path)

                lane_width = (
                    OPEN_ROAD_REFERENCE_LANE_WIDTH_M
                )
                half_separator = (
                    OPEN_ROAD_REFERENCE_SEPARATOR_WIDTH_M
                    / 2.0
                )

                # White dashed lane dividers inside each 3-lane carriageway.
                lane_divider_pen = QPen(
                    QColor(
                        230,
                        234,
                        238,
                        220,
                    ),
                    1.5,
                )
                lane_divider_pen.setCosmetic(True)
                lane_divider_pen.setStyle(
                    Qt.PenStyle.DashLine
                )
                lane_divider_pen.setDashPattern(
                    [7.0, 7.0]
                )

                painter.setPen(lane_divider_pen)

                for side_sign in (-1.0, 1.0):
                    for divider_index in range(
                        1,
                        OPEN_ROAD_REFERENCE_LANES_PER_SIDE,
                    ):
                        offset_m = side_sign * (
                            half_separator
                            + divider_index * lane_width
                        )

                        divider_points = _offset_world_polyline(
                            points,
                            offset_m,
                            road_closed,
                        )
                        painter.drawPath(
                            _world_polyline_path(
                                divider_points,
                                road_closed,
                            )
                        )

                # Solid outer road edges.
                outer_edge_pen = QPen(
                    QColor(
                        245,
                        247,
                        250,
                        235,
                    ),
                    2.0,
                )
                outer_edge_pen.setCosmetic(True)
                outer_edge_pen.setStyle(
                    Qt.PenStyle.SolidLine
                )
                painter.setPen(outer_edge_pen)

                outer_offset = (
                    half_separator
                    + OPEN_ROAD_REFERENCE_LANES_PER_SIDE
                    * lane_width
                )

                for side_sign in (-1.0, 1.0):
                    edge_points = _offset_world_polyline(
                        points,
                        side_sign * outer_offset,
                        road_closed,
                    )
                    painter.drawPath(
                        _world_polyline_path(
                            edge_points,
                            road_closed,
                        )
                    )

                # Thin center reference so the original documentation-derived
                # trajectory remains visible inside the separator.
                center_reference_pen = QPen(
                    QColor(
                        255,
                        200,
                        70,
                        185,
                    ),
                    1.0,
                )
                center_reference_pen.setCosmetic(True)
                center_reference_pen.setStyle(
                    Qt.PenStyle.DotLine
                )
                painter.setPen(center_reference_pen)
                painter.drawPath(road_path)

        # --------------------------------------------------------
        # Published QLabs reference coordinates
        # --------------------------------------------------------
        if self.workspace_show_reference_points:
            point_pen = QPen(
                QColor(
                    255,
                    220,
                    80,
                    245,
                ),
                2,
            )
            point_pen.setCosmetic(True)
            painter.setPen(point_pen)
            painter.setBrush(
                QColor(
                    255,
                    190,
                    55,
                    220,
                )
            )

            marker_radius_scene = (
                6.0
                / view_scale
            )

            label_positions = []

            for point in reference.get(
                "reference_points",
                [],
            ):
                scene_pos = world_to_scene(
                    float(point.get("x", 0.0)),
                    float(point.get("y", 0.0)),
                )

                painter.drawEllipse(
                    scene_pos,
                    marker_radius_scene,
                    marker_radius_scene,
                )

                if self.workspace_show_reference_labels:
                    label_positions.append(
                        (
                            painter.worldTransform().map(
                                scene_pos
                            ),
                            str(
                                point.get(
                                    "name",
                                    "",
                                )
                            ),
                        )
                    )

            # Labels are painted in viewport/device coordinates so they remain
            # readable even when the full 18 km loop is fitted on screen.
            if label_positions:
                painter.save()
                painter.resetTransform()

                font = painter.font()
                font.setPixelSize(12)
                painter.setFont(font)

                painter.setPen(
                    QPen(
                        QColor(
                            255,
                            235,
                            150,
                        ),
                        1,
                    )
                )

                for device_pos, label in label_positions:
                    painter.drawText(
                        QPointF(
                            device_pos.x() + 9.0,
                            device_pos.y() - 8.0,
                        ),
                        label,
                    )

                painter.restore()

    # ------------------------------------------------------------
    # Project scale
    # ------------------------------------------------------------

    def project_scale_changed(self):
        factor = self.project_scale_combo.currentData()
        custom = factor is None
        self.custom_scale_label.setVisible(custom)
        self.custom_scale_denominator.setVisible(custom)

        if custom:
            self.custom_scale_changed()
            return

        self.project_scale_factor = float(factor)
        self.project_scale_name = self.project_scale_combo.currentText()
        self._refresh_scale_ui()

    def custom_scale_changed(self):
        if self.project_scale_combo.currentData() is not None:
            return
        denominator = max(1.0, float(self.custom_scale_denominator.value()))
        self.project_scale_factor = 1.0 / denominator
        self.project_scale_name = f"1:{denominator:g}"
        self._refresh_scale_ui()

    def _refresh_scale_ui(self):
        design_width = workspace_mode_default_road_width(self.workspace_mode)
        effective = design_width * self.project_scale_factor
        self.scale_preview_label.setText(
            f"{design_width:.2f} m workspace-default road → {effective:.3f} m in QLabs"
        )
        self.scale_status_label.setText(f"Scale: {self.project_scale_name}")
        self.update_selection_info()

    def _set_project_scale_from_data(self, project: dict):
        factor = float(project.get("scale_factor", 1.0))
        name = str(project.get("scale_name", ""))

        for i in range(self.project_scale_combo.count() - 1):
            item_factor = self.project_scale_combo.itemData(i)
            if item_factor is not None and math.isclose(float(item_factor), factor, rel_tol=1e-9):
                self.project_scale_combo.setCurrentIndex(i)
                return

        # Unknown/custom scale. Store it as a 1:N denominator.
        self.project_scale_combo.setCurrentIndex(self.project_scale_combo.count() - 1)
        denominator = 1.0 / max(factor, 1e-9)
        self.custom_scale_denominator.setValue(denominator)
        self.project_scale_factor = factor
        self.project_scale_name = name or f"1:{denominator:g}"
        self._refresh_scale_ui()

    # ------------------------------------------------------------
    # Editing
    # ------------------------------------------------------------

    def rotation_step_changed(self):
        value = self.rotation_step_combo.currentData()
        self.rotation_step_deg = float(value) if value is not None else ROTATION_STEP_DEG
        self.rotate_btn.setText(f"Rotate +{self.rotation_step_deg:g}°")
        self._update_help_text()

    def _update_help_text(self):
        self.help_label.setText(
            "Controls\n"
            "• Left drag: move/select\n"
            "• Mouse wheel: zoom\n"
            "• Middle drag: pan\n"
            f"• R: rotate +{self.rotation_step_deg:g}°\n"
            f"• Shift+R: rotate -{self.rotation_step_deg:g}°\n"
            "• Ctrl+D: duplicate\n"
            "• Delete: remove"
        )

    def rotate_selected(self, amount_deg: float):
        selected = self.scene.selected_track_items()
        if not selected:
            return
        self._begin_undo_transaction("Rotate selection")
        for item in selected:
            item.rotate_step(amount_deg)
        self.scene.update()
        self.update_selection_info()
        self._commit_undo_transaction()

    def duplicate_selected(self):
        originals = self.scene.selected_track_items()
        if not originals:
            return

        self._begin_undo_transaction("Duplicate selection")
        self.scene.clearSelection()
        offset = world_to_scene(2.0, -2.0)

        snap_was_enabled = self.scene.endpoint_snap_enabled
        self.scene.endpoint_snap_enabled = False

        try:
            for original in originals:
                copy = original.duplicate()
                if copy is None:
                    continue

                copy.setRotation(original.rotation())
                copy.set_readable_identifier("")
                self._assign_readable_identifier_if_needed(copy)
                self.scene.addItem(copy)
                copy.setPos(original.pos() + offset)
                copy.setSelected(True)
        finally:
            self.scene.endpoint_snap_enabled = snap_was_enabled

        self.update_selection_info()
        self._commit_undo_transaction()

    def delete_selected(self):
        selected = list(self.scene.selectedItems())
        if not selected:
            return
        self._begin_undo_transaction("Delete selection")
        for item in selected:
            self.scene.removeItem(item)
        self.update_selection_info()
        self._commit_undo_transaction()

    def set_endpoint_snap_enabled(self, enabled: bool):
        self.scene.endpoint_snap_enabled = enabled
        self.snap_status_label.setText(
            "Endpoint/wall snap: ON" if enabled else "Endpoint/wall snap: OFF"
        )

    # ------------------------------------------------------------
    # Property editor
    # ------------------------------------------------------------

    def _single_selected_item(self) -> TrackItem | None:
        selected = self.scene.selected_track_items()
        if len(selected) == 1:
            return selected[0]
        return None

    def _set_property_row_visible(self, field, visible: bool):
        label = self.properties_form.labelForField(field)
        if label is not None:
            label.setVisible(visible)
        field.setVisible(visible)

    def _block_property_signals(self, blocked: bool):
        for widget in (
            self.prop_x,
            self.prop_y,
            self.prop_rotation,
            self.prop_length,
            self.prop_width,
            self.prop_radius,
            self.prop_arm,
            self.prop_height,
        ):
            widget.blockSignals(blocked)

    def _refresh_property_editor(self, item: TrackItem | None):
        self._property_refreshing = True
        self._block_property_signals(True)

        try:
            self.properties_group.setEnabled(item is not None)

            # Hide type-specific fields by default.
            self._set_property_row_visible(self.prop_length, False)
            self._set_property_row_visible(self.prop_width, False)
            self._set_property_row_visible(self.prop_radius, False)
            self._set_property_row_visible(self.prop_arm, False)
            self._set_property_row_visible(self.prop_height, False)

            if item is None:
                self.prop_effective.setText("")
                return

            x_m, y_m = scene_to_world(item.pos())
            self.prop_x.setValue(x_m)
            self.prop_y.setValue(y_m)
            self.prop_rotation.setValue(normalize_angle(item.rotation()))

            if isinstance(item, MedianWallItem):
                self._set_property_row_visible(self.prop_length, True)
                self._set_property_row_visible(self.prop_width, True)
                self._set_property_row_visible(self.prop_height, True)
                self.prop_length.setValue(item.length_m)
                self.prop_width.setValue(item.width_m)
                self.prop_height.setValue(item.height_m)

            elif isinstance(item, (StraightRoadItem, RoadEndItem)):
                self._set_property_row_visible(self.prop_length, True)
                self._set_property_row_visible(self.prop_width, True)
                self.prop_length.setValue(item.length_m)
                self.prop_width.setValue(item.width_m)

            elif isinstance(item, (Curve90RoadItem, Curve45RoadItem)):
                self._set_property_row_visible(self.prop_radius, True)
                self._set_property_row_visible(self.prop_width, True)
                self.prop_radius.setValue(item.radius_m)
                self.prop_width.setValue(item.width_m)

            elif isinstance(item, (TJunctionItem, CrossIntersectionItem)):
                self._set_property_row_visible(self.prop_arm, True)
                self._set_property_row_visible(self.prop_width, True)
                self.prop_arm.setValue(item.arm_length_m)
                self.prop_width.setValue(item.width_m)

            self.prop_effective.setText(self._effective_text(item))
        finally:
            self._block_property_signals(False)
            self._property_refreshing = False

    def _refresh_road_markings_editor(self, item: TrackItem | None):
        supported = item is not None and item.supports_road_markings()
        self.markings_group.setVisible(supported)
        if not supported:
            return

        self._marking_refreshing = True
        widgets = (
            self.prop_marking_edge_a,
            self.prop_marking_center,
            self.prop_marking_edge_b,
            self.prop_marking_end_bar,
        )
        for widget in widgets:
            widget.blockSignals(True)
        try:
            self.prop_marking_edge_a.setChecked(bool(item.show_edge_a))
            self.prop_marking_center.setChecked(bool(item.show_center_line))
            self.prop_marking_edge_b.setChecked(bool(item.show_edge_b))
            self.prop_marking_end_bar.setChecked(bool(item.show_end_bar))
            self.prop_marking_end_bar.setVisible(isinstance(item, RoadEndItem))
            label = self.markings_group.layout().labelForField(self.prop_marking_end_bar)
            if label is not None:
                label.setVisible(isinstance(item, RoadEndItem))
        finally:
            for widget in widgets:
                widget.blockSignals(False)
            self._marking_refreshing = False

    def apply_road_marking_properties(self):
        if self._marking_refreshing:
            return
        item = self._single_selected_item()
        if item is None or not item.supports_road_markings():
            return

        self._begin_undo_transaction("Change road markings")
        item.show_edge_a = self.prop_marking_edge_a.isChecked()
        item.show_center_line = self.prop_marking_center.isChecked()
        item.show_edge_b = self.prop_marking_edge_b.isChecked()
        item.show_end_bar = self.prop_marking_end_bar.isChecked()
        item.update()
        self.scene.update()
        self.update_selection_info()
        self._commit_undo_transaction()

    def _set_actor_row_visible(self, field, visible: bool):
        layout = self.actor_group.layout()
        label = layout.labelForField(field)
        if label is not None:
            label.setVisible(visible)
        field.setVisible(visible)

    def _refresh_camera_editor(self, item: TrackItem | None):
        supported = isinstance(item, QCar2StartItem)
        self.camera_group.setVisible(supported)
        if not supported:
            return

        self.prop_camera_view.blockSignals(True)
        try:
            idx = self.prop_camera_view.findData(item.camera_view)
            self.prop_camera_view.setCurrentIndex(max(0, idx))
        finally:
            self.prop_camera_view.blockSignals(False)

    def apply_camera_property(self):
        if self._property_refreshing:
            return
        item = self._single_selected_item()
        if not isinstance(item, QCar2StartItem):
            return

        self._begin_undo_transaction("Change QCar camera")
        item.camera_view = str(self.prop_camera_view.currentData())
        self.update_selection_info()
        self._commit_undo_transaction()

    def _refresh_actor_editor(self, item: TrackItem | None):
        supported = isinstance(item, SceneActorItem)
        self.actor_group.setVisible(supported)
        if not supported:
            return

        widgets = (
            self.prop_actor_z,
            self.prop_actor_scale,
            self.prop_actor_scale_project,
            self.prop_actor_configuration,
            self.prop_traffic_color,
            self.prop_catalog_sign_type,
            self.prop_building_length,
            self.prop_building_width,
            self.prop_building_height,
            self.prop_building_r,
            self.prop_building_g,
            self.prop_building_b,
        )
        for widget in widgets:
            widget.blockSignals(True)

        try:
            self._set_actor_row_visible(self.prop_actor_configuration, False)
            self._set_actor_row_visible(self.prop_traffic_color, False)
            self._set_actor_row_visible(self.prop_catalog_sign_type, False)
            self._set_actor_row_visible(self.prop_building_length, False)
            self._set_actor_row_visible(self.prop_building_width, False)
            self._set_actor_row_visible(self.prop_building_height, False)

            building_rgb_widget = self.prop_building_r.parentWidget()
            rgb_label = self.actor_group.layout().labelForField(building_rgb_widget)
            if rgb_label is not None:
                rgb_label.setVisible(False)
            building_rgb_widget.setVisible(False)

            self.prop_actor_z.setValue(item.z_m)
            self.prop_actor_scale.setValue(item.actor_scale)
            self.prop_actor_scale_project.setChecked(item.scale_with_project)

            if isinstance(item, (TrafficLightItem, CrosswalkItem)):
                self._set_actor_row_visible(self.prop_actor_configuration, True)
                idx = self.prop_actor_configuration.findData(item.configuration)
                self.prop_actor_configuration.setCurrentIndex(max(0, idx))

            if isinstance(item, TrafficLightItem):
                self._set_actor_row_visible(self.prop_traffic_color, True)
                idx = self.prop_traffic_color.findData(item.traffic_color)
                self.prop_traffic_color.setCurrentIndex(max(0, idx))

            if isinstance(item, CatalogTrafficSignItem):
                self._set_actor_row_visible(self.prop_catalog_sign_type, True)
                idx = self.prop_catalog_sign_type.findData(item.sign_type)
                self.prop_catalog_sign_type.setCurrentIndex(max(0, idx))

            if isinstance(item, BuildingBoxItem):
                self._set_actor_row_visible(self.prop_building_length, True)
                self._set_actor_row_visible(self.prop_building_width, True)
                self._set_actor_row_visible(self.prop_building_height, True)
                self.prop_building_length.setValue(item.length_m)
                self.prop_building_width.setValue(item.width_m)
                self.prop_building_height.setValue(item.height_m)

                self.prop_building_r.setText(str(int(item.rgb[0])))
                self.prop_building_g.setText(str(int(item.rgb[1])))
                self.prop_building_b.setText(str(int(item.rgb[2])))

                if rgb_label is not None:
                    rgb_label.setVisible(True)
                building_rgb_widget.setVisible(True)
        finally:
            for widget in widgets:
                widget.blockSignals(False)

    def apply_actor_properties(self, *args):
        item = self._single_selected_item()
        if not isinstance(item, SceneActorItem):
            return

        self._begin_undo_transaction("Edit actor properties")
        item.z_m = float(self.prop_actor_z.value())
        item.actor_scale = max(0.01, float(self.prop_actor_scale.value()))
        item.scale_with_project = self.prop_actor_scale_project.isChecked()

        if isinstance(item, (TrafficLightItem, CrosswalkItem)):
            item.configuration = int(
                self.prop_actor_configuration.currentData() or 0
            )

        if isinstance(item, TrafficLightItem):
            item.traffic_color = str(self.prop_traffic_color.currentData())

        if isinstance(item, CatalogTrafficSignItem):
            item.sign_type = str(
                self.prop_catalog_sign_type.currentData() or DEFAULT_TRAFFIC_SIGN_KEY
            )

        if isinstance(item, BuildingBoxItem):
            item.prepareGeometryChange()
            item.length_m = max(0.1, float(self.prop_building_length.value()))
            item.width_m = max(0.1, float(self.prop_building_width.value()))
            item.height_m = max(0.1, float(self.prop_building_height.value()))
            item.rgb = (
                self._rgb_input_value(self.prop_building_r, item.rgb[0]),
                self._rgb_input_value(self.prop_building_g, item.rgb[1]),
                self._rgb_input_value(self.prop_building_b, item.rgb[2]),
            )

        item.update()
        self.scene.update()
        self.update_selection_info()
        self._commit_undo_transaction()

    def _set_experiment_row_visible(self, field, visible: bool):
        layout = self.experiment_group.layout()
        label = layout.labelForField(field)
        if label is not None:
            label.setVisible(visible)
        field.setVisible(visible)

    def _populate_gait_combo(self, item, current_gait: str):
        self.prop_movement_gait.blockSignals(True)
        try:
            self.prop_movement_gait.clear()

            if isinstance(item, PersonItem):
                choices = (
                    ("Standing", "standing"),
                    ("Walk", "walk"),
                    ("Jog", "jog"),
                    ("Run", "run"),
                )
            else:
                choices = (
                    ("Standing", "standing"),
                    ("Walk", "walk"),
                    ("Run", "run"),
                )

            for label, value in choices:
                self.prop_movement_gait.addItem(label, value)

            idx = self.prop_movement_gait.findData(current_gait)
            self.prop_movement_gait.setCurrentIndex(max(0, idx))
        finally:
            self.prop_movement_gait.blockSignals(False)

    def _trigger_candidates(self, action: str):
        items = self.scene.track_items()

        if action == TRIGGER_ACTION_TRAFFIC_LIGHT:
            return [
                item
                for item in items
                if isinstance(item, TrafficLightItem)
            ]

        return [
            item
            for item in items
            if isinstance(item, (PersonItem, AnimalItem, SecondaryQCarItem))
        ]

    def _populate_trigger_targets(
        self,
        trigger: TriggerZoneItem,
    ):
        action = trigger.action
        candidates = self._trigger_candidates(action)

        self.prop_trigger_target.blockSignals(True)
        try:
            self.prop_trigger_target.clear()
            self.prop_trigger_target.addItem("— Select target —", "")

            for candidate in candidates:
                readable = (
                    candidate.identifier
                    if getattr(candidate, "identifier", "")
                    else str(candidate.object_id)[:8]
                )
                label = f"{candidate.DISPLAY_NAME} [{readable}]"
                self.prop_trigger_target.addItem(
                    label,
                    str(candidate.object_id),
                )

            if (
                trigger.target_id
                and self.prop_trigger_target.findData(trigger.target_id) < 0
            ):
                self.prop_trigger_target.addItem(
                    f"Missing target [{trigger.target_id[:8]}]",
                    trigger.target_id,
                )

            idx = self.prop_trigger_target.findData(trigger.target_id)
            self.prop_trigger_target.setCurrentIndex(max(0, idx))
        finally:
            self.prop_trigger_target.blockSignals(False)

    def start_path_editing(self):
        item = self._single_selected_item()
        if not isinstance(item, ExperimentActorItem):
            return
        self.path_edit_actor_id = str(item.object_id)
        self.path_draw_button.setText("Click map... (right-click ends)")
        self.view.setCursor(Qt.CursorShape.CrossCursor)
        self.view.viewport().update()

    def finish_path_editing(self):
        self.path_edit_actor_id = None
        self.view.unsetCursor()
        if hasattr(self, "path_draw_button"):
            self.path_draw_button.setText("Draw / Add")
        self.view.viewport().update()

    def _path_edit_actor(self):
        if not self.path_edit_actor_id:
            return None
        for item in self.scene.track_items():
            if isinstance(item, ExperimentActorItem) and str(item.object_id) == str(self.path_edit_actor_id):
                return item
        return None

    def add_movement_waypoint(self, scene_pos: QPointF):
        item = self._path_edit_actor()
        if item is None:
            self.finish_path_editing()
            return
        x_m, y_m = scene_to_world(scene_pos)
        item.path_points_m.append([round(x_m, 3), round(y_m, 3)])
        item.move_on_activation = True
        self.path_summary_label.setText(f"{len(item.path_points_m)} waypoints")
        self.view.viewport().update()
        self.update_selection_info()

    def remove_last_waypoint(self):
        item = self._single_selected_item()
        if not isinstance(item, ExperimentActorItem) or not item.path_points_m:
            return
        item.path_points_m.pop()
        self.view.viewport().update()
        self.update_selection_info()

    def clear_movement_path(self):
        item = self._single_selected_item()
        if not isinstance(item, ExperimentActorItem):
            return
        item.path_points_m.clear()
        self.finish_path_editing()
        self.view.viewport().update()
        self.update_selection_info()

    def _refresh_experiment_editor(self, item: TrackItem | None):
        supported = isinstance(
            item,
            (ExperimentActorItem, TriggerZoneItem),
        )
        self.experiment_group.setVisible(supported)

        if not supported:
            return

        path_label = self.experiment_group.layout().labelForField(self.path_widget)
        is_actor = isinstance(item, ExperimentActorItem)
        self.path_widget.setVisible(is_actor)
        if path_label is not None:
            path_label.setVisible(is_actor)

        fields = (
            self.prop_experiment_spawn_mode,
            self.prop_person_configuration,
            self.prop_animal_type,
            self.prop_experiment_move,
            self.prop_destination_x,
            self.prop_destination_y,
            self.prop_movement_gait,
            self.prop_movement_mode,
            self.prop_despawn_on_finish,
            self.prop_secondary_qcar_speed,
            self.prop_trigger_radius,
            self.prop_trigger_action,
            self.prop_trigger_target,
            self.prop_trigger_traffic_color,
            self.prop_trigger_one_shot,
        )

        for field in fields:
            field.blockSignals(True)

        try:
            # Start hidden, then expose only the rows relevant to selection.
            for field in fields:
                self._set_experiment_row_visible(field, False)

            if isinstance(item, ExperimentActorItem):
                self._set_experiment_row_visible(
                    self.prop_experiment_spawn_mode,
                    True,
                )
                self._set_experiment_row_visible(
                    self.prop_experiment_move,
                    True,
                )
                self._set_experiment_row_visible(
                    self.prop_destination_x,
                    True,
                )
                self._set_experiment_row_visible(
                    self.prop_destination_y,
                    True,
                )
                self._set_experiment_row_visible(
                    self.prop_movement_gait,
                    True,
                )
                self._set_experiment_row_visible(self.prop_movement_mode, True)
                self._set_experiment_row_visible(self.prop_despawn_on_finish, True)

                idx = self.prop_experiment_spawn_mode.findData(
                    item.spawn_mode
                )
                self.prop_experiment_spawn_mode.setCurrentIndex(
                    max(0, idx)
                )

                self.prop_experiment_move.setChecked(
                    item.move_on_activation
                )
                self.prop_destination_x.setValue(
                    item.destination_x_m
                )
                self.prop_destination_y.setValue(
                    item.destination_y_m
                )

                if isinstance(item, PersonItem):
                    self._set_experiment_row_visible(
                        self.prop_person_configuration,
                        True,
                    )
                    idx = self.prop_person_configuration.findData(
                        item.person_configuration
                    )
                    self.prop_person_configuration.setCurrentIndex(
                        max(0, idx)
                    )

                if isinstance(item, AnimalItem):
                    self._set_experiment_row_visible(
                        self.prop_animal_type,
                        True,
                    )
                    idx = self.prop_animal_type.findData(item.animal_type)
                    self.prop_animal_type.setCurrentIndex(max(0, idx))

                if isinstance(item, SecondaryQCarItem):
                    self._set_experiment_row_visible(self.prop_movement_gait, False)
                    self._set_experiment_row_visible(self.prop_secondary_qcar_speed, True)
                    self.prop_secondary_qcar_speed.setValue(item.movement_speed_mps)
                else:
                    self._populate_gait_combo(item, item.movement_gait)

                idx = self.prop_movement_mode.findData(item.movement_mode)
                self.prop_movement_mode.setCurrentIndex(max(0, idx))
                self.prop_despawn_on_finish.setChecked(item.despawn_on_finish)
                self.prop_despawn_on_finish.setEnabled(item.movement_mode == MOVEMENT_ONCE)
                self.path_summary_label.setText(f"{len(item.path_points_m)} waypoints")

                movement_enabled = item.move_on_activation
                self.prop_destination_x.setEnabled(movement_enabled)
                self.prop_destination_y.setEnabled(movement_enabled)
                self.prop_movement_gait.setEnabled(movement_enabled)

            elif isinstance(item, TriggerZoneItem):
                self._set_experiment_row_visible(
                    self.prop_trigger_radius,
                    True,
                )
                self._set_experiment_row_visible(
                    self.prop_trigger_action,
                    True,
                )
                self._set_experiment_row_visible(
                    self.prop_trigger_target,
                    True,
                )
                self._set_experiment_row_visible(
                    self.prop_trigger_one_shot,
                    True,
                )

                self.prop_trigger_radius.setValue(item.radius_m)

                idx = self.prop_trigger_action.findData(item.action)
                self.prop_trigger_action.setCurrentIndex(max(0, idx))

                self._populate_trigger_targets(item)

                show_light = (
                    item.action == TRIGGER_ACTION_TRAFFIC_LIGHT
                )
                self._set_experiment_row_visible(
                    self.prop_trigger_traffic_color,
                    show_light,
                )

                idx = self.prop_trigger_traffic_color.findData(
                    item.traffic_color
                )
                self.prop_trigger_traffic_color.setCurrentIndex(
                    max(0, idx)
                )
                self.prop_trigger_one_shot.setChecked(item.one_shot)

        finally:
            for field in fields:
                field.blockSignals(False)

    def _trigger_action_changed(self, *args):
        if self._property_refreshing:
            return

        item = self._single_selected_item()
        if not isinstance(item, TriggerZoneItem):
            return

        self._begin_undo_transaction("Change trigger action")
        item.action = str(self.prop_trigger_action.currentData())
        item.target_id = ""
        self._refresh_experiment_editor(item)
        self.update_selection_info()
        self._commit_undo_transaction()

    def apply_experiment_properties(self, *args):
        if self._property_refreshing:
            return

        item = self._single_selected_item()

        if isinstance(item, ExperimentActorItem):
            self._begin_undo_transaction("Edit experiment actor")
            item.spawn_mode = str(
                self.prop_experiment_spawn_mode.currentData()
            )
            item.move_on_activation = (
                self.prop_experiment_move.isChecked()
            )
            item.destination_x_m = float(
                self.prop_destination_x.value()
            )
            item.destination_y_m = float(
                self.prop_destination_y.value()
            )
            gait = self.prop_movement_gait.currentData()
            if gait is not None and not isinstance(item, SecondaryQCarItem):
                item.movement_gait = str(gait)

            item.movement_mode = str(self.prop_movement_mode.currentData() or MOVEMENT_ONCE)
            item.despawn_on_finish = self.prop_despawn_on_finish.isChecked()
            self.prop_despawn_on_finish.setEnabled(item.movement_mode == MOVEMENT_ONCE)

            if isinstance(item, SecondaryQCarItem):
                item.movement_speed_mps = max(0.1, float(self.prop_secondary_qcar_speed.value()))

            if isinstance(item, PersonItem):
                item.person_configuration = int(
                    self.prop_person_configuration.currentData() or 0
                )

            if isinstance(item, AnimalItem):
                item.animal_type = str(
                    self.prop_animal_type.currentData() or "goat"
                )

            self.prop_destination_x.setEnabled(
                item.move_on_activation
            )
            self.prop_destination_y.setEnabled(
                item.move_on_activation
            )
            self.prop_movement_gait.setEnabled(
                item.move_on_activation
            )

            item.update()
            self.update_selection_info()
            self._commit_undo_transaction()
            return

        if isinstance(item, TriggerZoneItem):
            self._begin_undo_transaction("Edit trigger zone")
            item.prepareGeometryChange()
            item.radius_m = max(
                0.1,
                float(self.prop_trigger_radius.value()),
            )
            item.action = str(
                self.prop_trigger_action.currentData()
            )
            item.target_id = str(
                self.prop_trigger_target.currentData() or ""
            )
            item.traffic_color = str(
                self.prop_trigger_traffic_color.currentData()
            )
            item.one_shot = self.prop_trigger_one_shot.isChecked()

            item.update()
            self.scene.update()
            self.update_selection_info()
            self._commit_undo_transaction()

    def _refresh_guide_editor(self, item: TrackItem | None):
        supported = item is not None and item.supports_guide_line()
        self.guide_group.setVisible(bool(supported))
        if not supported:
            return

        self._guide_refreshing = True
        widgets = (
            self.prop_guide_enabled,
            self.prop_guide_position,
            self.prop_guide_offset,
            self.prop_guide_color,
            self.prop_guide_r,
            self.prop_guide_g,
            self.prop_guide_b,
            self.prop_guide_width,
            self.prop_guide_style,
            self.prop_guide_scale_width,
        )
        for widget in widgets:
            widget.blockSignals(True)

        try:
            self.prop_guide_enabled.setChecked(item.guide_enabled)
            idx = self.prop_guide_position.findData(item.guide_position)
            self.prop_guide_position.setCurrentIndex(max(0, idx))
            self.prop_guide_offset.setValue(item.guide_custom_offset_m)
            self.prop_guide_offset.setEnabled(item.guide_position == "custom")
            idx = self.prop_guide_color.findData(item.guide_color_name)
            self.prop_guide_color.setCurrentIndex(max(0, idx))

            if item.guide_color_name == "custom":
                shown_rgb = item.guide_rgb
                rgb_enabled = True
            else:
                shown_rgb = GUIDE_COLOR_RGB.get(
                    item.guide_color_name,
                    DEFAULT_GUIDE_RGB,
                )
                rgb_enabled = False

            self.prop_guide_r.setText(str(int(shown_rgb[0])))
            self.prop_guide_g.setText(str(int(shown_rgb[1])))
            self.prop_guide_b.setText(str(int(shown_rgb[2])))
            self.prop_guide_r.setEnabled(rgb_enabled)
            self.prop_guide_g.setEnabled(rgb_enabled)
            self.prop_guide_b.setEnabled(rgb_enabled)

            self.prop_guide_width.setValue(item.guide_width_m)
            idx = self.prop_guide_style.findData(item.guide_style)
            self.prop_guide_style.setCurrentIndex(max(0, idx))
            self.prop_guide_scale_width.setChecked(item.guide_scale_width)
        finally:
            for widget in widgets:
                widget.blockSignals(False)
            self._guide_refreshing = False

    def apply_guide_properties(self, *args):
        if self._guide_refreshing:
            return
        item = self._single_selected_item()
        if item is None or not item.supports_guide_line():
            return

        self._begin_undo_transaction("Edit lane guide")
        item.guide_enabled = self.prop_guide_enabled.isChecked()
        item.guide_position = str(self.prop_guide_position.currentData())
        item.guide_custom_offset_m = float(self.prop_guide_offset.value())

        selected_color = str(self.prop_guide_color.currentData())
        color_combo_changed = self.sender() is self.prop_guide_color
        item.guide_color_name = selected_color

        if selected_color == "custom":
            # Restore the stored custom color when switching from a preset.
            if color_combo_changed:
                rgb = item.guide_rgb
                for widget, value in (
                    (self.prop_guide_r, rgb[0]),
                    (self.prop_guide_g, rgb[1]),
                    (self.prop_guide_b, rgb[2]),
                ):
                    widget.blockSignals(True)
                    widget.setText(str(int(value)))
                    widget.blockSignals(False)

            item.guide_rgb = (
                self._rgb_input_value(self.prop_guide_r, item.guide_rgb[0]),
                self._rgb_input_value(self.prop_guide_g, item.guide_rgb[1]),
                self._rgb_input_value(self.prop_guide_b, item.guide_rgb[2]),
            )
            rgb_enabled = True
        else:
            # Preset selected: show its actual RGB numbers while keeping
            # the previously entered custom RGB stored for later.
            preset_rgb = GUIDE_COLOR_RGB.get(
                selected_color,
                DEFAULT_GUIDE_RGB,
            )

            for widget, value in (
                (self.prop_guide_r, preset_rgb[0]),
                (self.prop_guide_g, preset_rgb[1]),
                (self.prop_guide_b, preset_rgb[2]),
            ):
                widget.blockSignals(True)
                widget.setText(str(int(value)))
                widget.blockSignals(False)

            rgb_enabled = False

        self.prop_guide_r.setEnabled(rgb_enabled)
        self.prop_guide_g.setEnabled(rgb_enabled)
        self.prop_guide_b.setEnabled(rgb_enabled)

        item.guide_width_m = max(0.01, float(self.prop_guide_width.value()))
        item.guide_style = str(self.prop_guide_style.currentData())
        item.guide_scale_width = self.prop_guide_scale_width.isChecked()
        self.prop_guide_offset.setEnabled(item.guide_position == "custom")
        item.update()
        self.scene.update()
        self.update_selection_info()
        self._commit_undo_transaction()

    def _effective_text(self, item: TrackItem | None) -> str:
        if item is None:
            return ""
        f = self.project_scale_factor
        x_m, y_m = scene_to_world(item.pos())
        lines = [
            f"Scale {self.project_scale_name}",
            f"X: {x_m * f:.3f} m",
            f"Y: {y_m * f:.3f} m",
        ]
        if hasattr(item, "width_m"):
            lines.append(f"Width: {float(item.width_m) * f:.3f} m")
        if hasattr(item, "length_m"):
            lines.append(f"Length: {float(item.length_m) * f:.3f} m")
        if hasattr(item, "radius_m"):
            lines.append(f"Radius: {float(item.radius_m) * f:.3f} m")
        if hasattr(item, "arm_length_m"):
            lines.append(f"Arm: {float(item.arm_length_m) * f:.3f} m")
        if isinstance(item, MedianWallItem):
            lines.append(f"Height: {float(item.height_m) * f:.3f} m")
        if isinstance(item, QCar2StartItem):
            lines.append(f"QCar actor scale: {f:.3f}")
            lines.append(f"QLabs yaw: {-normalize_angle(item.rotation()):.1f}°")
            lines.append(
                "Camera: First person"
                if item.camera_view == QCAR_CAMERA_FIRST_PERSON
                else "Camera: Third person"
            )
        if isinstance(item, TriggerZoneItem):
            lines.append(
                f"Trigger radius: {item.radius_m * f:.3f} m"
            )

        if isinstance(item, SceneActorItem):
            effective_actor_scale = (
                item.actor_scale * f
                if item.scale_with_project
                else item.actor_scale
            )
            if isinstance(item, CrosswalkItem):
                lines.append(
                    f"Crosswalk QLabs scale: {effective_actor_scale * CROSSWALK_QLABS_BASE_SCALE:.3f}"
                )
            else:
                lines.append(f"Actor scale: {effective_actor_scale:.3f}")
            lines.append(f"Base Z: {item.z_m * f:.3f} m")
            if isinstance(item, BuildingBoxItem):
                dimension_factor = f if item.scale_with_project else 1.0
                lines.append(
                    f"Box: {item.length_m * dimension_factor:.3f} × "
                    f"{item.width_m * dimension_factor:.3f} × "
                    f"{item.height_m * dimension_factor:.3f} m"
                )
        if item.supports_guide_line() and item.guide_enabled:
            lines.append(f"Guide offset: {item.resolved_guide_offset_m() * f:.3f} m")
            guide_width = item.guide_width_m * f if item.guide_scale_width else item.guide_width_m
            lines.append(f"Guide width: {guide_width:.3f} m")
        return "\n".join(lines)

    def _geometry_property_changed(self, item: TrackItem):
        item.update()
        self.scene.update()

        # If a resized endpoint remains near another endpoint, settle it again.
        if self.scene.endpoint_snap_enabled:
            snapped = self.scene.snap_item_position(item, item.pos())
            if snapped != item.pos():
                item.setPos(snapped)

        self.update_selection_info()

    def apply_position_properties(self):
        if self._property_refreshing:
            return
        item = self._single_selected_item()
        if item is None:
            return
        self._begin_undo_transaction("Move item")
        item.setPos(world_to_scene(self.prop_x.value(), self.prop_y.value()))
        self.update_selection_info()
        self._commit_undo_transaction()

    def apply_rotation_property(self, value: float):
        if self._property_refreshing:
            return
        item = self._single_selected_item()
        if item is None:
            return

        self._begin_undo_transaction("Rotate item")
        item.setRotation(normalize_angle(value))
        if self.scene.endpoint_snap_enabled:
            snapped = self.scene.snap_item_position(item, item.pos())
            if snapped != item.pos():
                item.setPos(snapped)
        self.scene.update()
        self.update_selection_info()
        self._commit_undo_transaction()

    def apply_length_property(self, value: float):
        if self._property_refreshing:
            return
        item = self._single_selected_item()
        if not isinstance(item, (StraightRoadItem, RoadEndItem, MedianWallItem)):
            return
        self._begin_undo_transaction("Resize road")
        item.prepareGeometryChange()
        item.length_m = max(1.0, float(value))
        self._geometry_property_changed(item)
        self._commit_undo_transaction()

    def apply_width_property(self, value: float):
        if self._property_refreshing:
            return
        item = self._single_selected_item()
        if item is None or not hasattr(item, "width_m"):
            return

        self._begin_undo_transaction("Change width")
        item.prepareGeometryChange()
        minimum_width = 0.05 if isinstance(item, MedianWallItem) else 1.0
        item.width_m = max(minimum_width, float(value))

        # Curves require a positive inner radius.
        if isinstance(item, (Curve90RoadItem, Curve45RoadItem)):
            minimum_radius = item.width_m / 2.0 + 0.5
            if item.radius_m < minimum_radius:
                item.radius_m = minimum_radius

        self._geometry_property_changed(item)
        self._commit_undo_transaction()

    def apply_height_property(self, value: float):
        if self._property_refreshing:
            return
        item = self._single_selected_item()
        if not isinstance(item, MedianWallItem):
            return
        self._begin_undo_transaction("Change wall height")
        item.height_m = max(0.05, float(value))
        item.update()
        self.scene.update()
        self.update_selection_info()
        self._commit_undo_transaction()

    def apply_radius_property(self, value: float):
        if self._property_refreshing:
            return
        item = self._single_selected_item()
        if not isinstance(item, (Curve90RoadItem, Curve45RoadItem)):
            return

        self._begin_undo_transaction("Change curve radius")
        item.prepareGeometryChange()
        minimum_radius = item.width_m / 2.0 + 0.5
        item.radius_m = max(minimum_radius, float(value))
        self._geometry_property_changed(item)
        self._commit_undo_transaction()

    def apply_arm_property(self, value: float):
        if self._property_refreshing:
            return
        item = self._single_selected_item()
        if not isinstance(item, (TJunctionItem, CrossIntersectionItem)):
            return

        self._begin_undo_transaction("Change junction arm")
        item.prepareGeometryChange()
        item.arm_length_m = max(item.width_m, float(value))
        self._geometry_property_changed(item)
        self._commit_undo_transaction()

    # ------------------------------------------------------------
    # Status
    # ------------------------------------------------------------

    def update_selection_info(self):
        selected = self.scene.selected_track_items()

        if len(selected) == 1:
            self.selection_label.setText(selected[0].selection_text())
            self._refresh_property_editor(selected[0])
            self._refresh_camera_editor(selected[0])
            self._refresh_actor_editor(selected[0])
            self._refresh_experiment_editor(selected[0])
            self._refresh_guide_editor(selected[0])
            self._refresh_road_markings_editor(selected[0])
        elif len(selected) > 1:
            self.selection_label.setText(f"{len(selected)} objects selected")
            self._refresh_property_editor(None)
            self._refresh_camera_editor(None)
            self._refresh_actor_editor(None)
            self._refresh_experiment_editor(None)
            self._refresh_guide_editor(None)
            self._refresh_road_markings_editor(None)
        else:
            self.selection_label.setText("None")
            self._refresh_property_editor(None)
            self._refresh_camera_editor(None)
            self._refresh_actor_editor(None)
            self._refresh_experiment_editor(None)
            self._refresh_guide_editor(None)
            self._refresh_road_markings_editor(None)

    def update_cursor_label(self, x_m: float, y_m: float):
        self.cursor_label.setText(f"Cursor: X {x_m:.1f} m | Y {y_m:.1f} m")

    def update_zoom_label(self):
        zoom_percent = self.view.transform().m11() * 100.0
        self.zoom_label.setText(f"Zoom: {zoom_percent:.0f}%")

    # ------------------------------------------------------------
    # QLabs export
    # ------------------------------------------------------------

    def export_qlabs_setup(self):
        qcar_starts = [
            item
            for item in self.scene.track_items()
            if isinstance(item, QCar2StartItem)
        ]

        if not qcar_starts:
            result = QMessageBox.question(
                self,
                "No QCar2 Start",
                "No QCar2 Start marker is present. Export the road network "
                "without spawning a QCar2?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.Yes,
            )
            if result != QMessageBox.StandardButton.Yes:
                return

        if self.current_file is not None:
            default_name = f"{self.current_file.stem}_qlabs_setup.py"
            default_path = str(self.current_file.with_name(default_name))
        else:
            default_path = "qlabs_track_setup.py"

        file_name, _ = QFileDialog.getSaveFileName(
            self,
            "Export QLabs Setup",
            default_path,
            "Python Files (*.py)",
        )
        if not file_name:
            return

        path = Path(file_name)
        if path.suffix.lower() != ".py":
            path = path.with_suffix(".py")

        source = build_qlabs_setup_source(self.track_data())

        try:
            compile(source, str(path), "exec")
            path.write_text(source, encoding="utf-8")
        except (OSError, SyntaxError) as exc:
            QMessageBox.critical(self, "Export Failed", str(exc))
            return

        platform_data = self.workspace_platform_project_data()
        workspace_label = (
            str(platform_data.get("workspace_label", "selected workspace"))
            if platform_data.get("enabled", False)
            else (
                workspace_mode_label(self.workspace_mode)
            )
        )

        QMessageBox.information(
            self,
            "QLabs Export Complete",
            "QLabs setup script created:\n"
            f"{path}\n\n"
            f"Open QLabs in the {workspace_label} workspace, then run the exported Python file.\n\n"
            "v1.0.1 keeps navmesh-free manual waypoint playback for people/animals, the same "
            "interpolation logic used by environment QCars, readable actor aliases, clear junction "
            "centers, movement loops/despawn, triggers, and outdoor weather/time settings. "
            "The Open Road reference overlay is editor-only and is not exported. The exported "
            "setup stays running while movement or trigger monitoring is required.",
        )

    # ------------------------------------------------------------
    # Save / load
    # ------------------------------------------------------------

    def track_data(self) -> dict:
        objects = [item.to_dict() for item in self.scene.track_items()]

        return {
            "format": "qlabs_track_editor",
            "version": self.VERSION,
            "units": "meters",
            "project": {
                "scale_name": self.project_scale_name,
                "scale_factor": self.project_scale_factor,
            },
            "canvas": {
                "width_m": self.canvas_width_m,
                "height_m": self.canvas_height_m,
            },
            "scenery_fill": {
                "style": self.scenery_fill_style,
                "density": self.scenery_fill_density,
                "roadside_reserve_m": self.roadside_reserve_m,
                "building_road_band_m": self.building_road_band_m,
            },
            "environment": {
                "enabled": self.environment_enabled,
                "weather": self.environment_weather,
                "time_of_day": self.environment_time_of_day,
            },
            "workspace_platform": self.workspace_platform_project_data(),
            "workspace": {
                "mode": self.workspace_mode,
                "label": workspace_mode_label(self.workspace_mode),
                "spline_z_m": float(self.workspace_spline_z_m),
                "show_road_reference": self.workspace_show_road_reference,
                "show_navigation_regions": self.workspace_show_navigation_regions,
                "show_reference_points": self.workspace_show_reference_points,
                "show_reference_labels": self.workspace_show_reference_labels,
            },
            "objects": objects,
        }

    def new_track(self):
        self.scene.clear()
        self.project_scale_combo.setCurrentIndex(0)
        self._set_environment_from_data({})
        self._set_workspace_from_data({})
        self._set_workspace_platform_from_data({})
        self._set_canvas_from_data({})
        self._set_scenery_fill_from_data({})
        self.finish_path_editing()
        self.current_file = None
        self.undo_manager.clear()
        self._update_undo_controls()
        self.setWindowTitle(f"QLabs Track Editor v{self.VERSION}")
        self.update_selection_info()

    def save_track(self, save_as: bool = False):
        path = self.current_file

        if path is None or save_as:
            file_name, _ = QFileDialog.getSaveFileName(
                self,
                "Save Track",
                "track.json",
                "JSON Track Files (*.json)",
            )
            if not file_name:
                return
            path = Path(file_name)
            if path.suffix.lower() != ".json":
                path = path.with_suffix(".json")

        try:
            with path.open("w", encoding="utf-8") as f:
                json.dump(self.track_data(), f, indent=2)
        except OSError as exc:
            QMessageBox.critical(self, "Save Failed", str(exc))
            return

        self.current_file = path
        self.setWindowTitle(f"QLabs Track Editor v{self.VERSION} — {path.name}")

    def load_track(self):
        file_name, _ = QFileDialog.getOpenFileName(
            self,
            "Open Track",
            "",
            "JSON Track Files (*.json)",
        )
        if not file_name:
            return

        path = Path(file_name)

        try:
            with path.open("r", encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, json.JSONDecodeError) as exc:
            QMessageBox.critical(self, "Open Failed", str(exc))
            return

        if data.get("format") != "qlabs_track_editor":
            QMessageBox.warning(
                self,
                "Unsupported File",
                "Not a QLabs Track Editor file.",
            )
            return

        self._set_project_scale_from_data(data.get("project", {}))
        self._set_environment_from_data(data.get("environment", {}))
        self._set_workspace_from_data(data.get("workspace", {}))
        self._set_workspace_platform_from_data(data.get("workspace_platform", {}))
        objects_data = data.get("objects", []) or []
        canvas_data = data.get("canvas")
        if not isinstance(canvas_data, dict):
            canvas_data = self._inferred_canvas_data(objects_data)
        self._set_canvas_from_data(canvas_data)
        self._set_scenery_fill_from_data(data.get("scenery_fill", {}))
        self.finish_path_editing()
        self.scene.clear()

        snap_was_enabled = self.scene.endpoint_snap_enabled
        self.scene.endpoint_snap_enabled = False
        unsupported_types = set()

        try:
            for obj in objects_data:
                item = create_track_item_from_dict(obj)
                if item is not None:
                    self.scene.addItem(item)
                else:
                    unsupported_types.add(str(obj.get("type", "unknown")))
        finally:
            self.scene.endpoint_snap_enabled = snap_was_enabled

        self._ensure_all_readable_identifiers()

        if unsupported_types:
            QMessageBox.information(
                self,
                "Some Objects Skipped",
                "Unsupported component types were skipped:\n"
                + "\n".join(sorted(unsupported_types)),
            )

        self.current_file = path
        self.setWindowTitle(f"QLabs Track Editor v{self.VERSION} — {path.name}")

        if self.workspace_mode == WORKSPACE_OPEN_ROAD:
            self.fit_open_road_reference()
        elif self.workspace_mode != WORKSPACE_CUSTOM:
            self.fit_selected_workspace()
        else:
            self.view.centerOn(0, 0)

        self.update_selection_info()
        self.undo_manager.clear()
        self._update_undo_controls()
