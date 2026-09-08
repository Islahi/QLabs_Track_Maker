"""Main application window.

This module preserves the complete v1.0.1 UI/workflow while the domain
objects, scene, view, geometry, workspace data, registry, and exporter live
in separate modules.
"""

import json
import math
from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, QSettings, Qt, QTimer
from PySide6.QtGui import (
    QAction,
    QColor,
    QKeySequence,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QIntValidator,
)
from PySide6.QtWidgets import (
    QCheckBox,
    QApplication,
    QComboBox,
    QDoubleSpinBox,
    QDialog,
    QDialogButtonBox,
    QDockWidget,
    QFileDialog,
    QFrame,
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
    QSizePolicy,
    QSpinBox,
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
    OPEN_ROAD_REFERENCE_MEASURED_LANE_FROM_SEPARATOR,
    OPEN_ROAD_REFERENCE_MEASURED_TO_SEPARATOR_NORMAL_SIGN,
    OPEN_ROAD_REFERENCE_MEASURED_TO_SEPARATOR_OFFSET_M,
    OPEN_ROAD_NEW_ACTOR_GROUND_EMBED_M,
    OPEN_ROAD_CROSSWALK_SURFACE_OFFSET_M,
    CROSSWALK_MARKER_LENGTH_M,
    CROSSWALK_MARKER_WIDTH_M,
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
    WORKSPACE_CITYSCAPE,
    WORKSPACE_CITYSCAPE_LITE,
    WORKSPACE_TOWNSCAPE,
    WORKSPACE_TOWNSCAPE_LITE,
    WORKSPACE_MODES,
    DEFAULT_CANVAS_WIDTH_M,
    DEFAULT_CANVAS_HEIGHT_M,
    DEFAULT_SCENERY_FILL_STYLE,
    DEFAULT_SCENERY_FILL_DENSITY,
    DEFAULT_ROADSIDE_RESERVE_M,
    DEFAULT_BUILDING_ROAD_BAND_M,
    ROAD_MARKING_COLOR_RGB,
    ROAD_MARKING_STYLES,
)
from core.geometry import (
    normalize_angle,
    scene_to_world,
    snap_value,
    world_to_scene,
)
from workspace.open_road import (
    load_open_road_reference,
    open_road_display_reference,
    _offset_world_polyline,
    _world_polyline_path,
)
from workspace.cityscape import load_cityscape_reference
from workspace.townscape import load_townscape_reference
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
from items.reference import ReferenceImageItem
from items.sketch import (
    SketchGuideItem,
    SketchLineItem,
    SketchArcItem,
    SketchCircleItem,
)
from items.roads import (
    StraightRoadItem,
    ContinuousRoadItem,
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
from ui.theme import app_stylesheet, system_uses_dark_theme
from services.scenery_filler import SceneryAutoFiller
from services.undo_manager import SnapshotUndoManager

class TrackEditorWindow(QMainWindow):
    VERSION = "2.0.0-dev"

    def __init__(self):
        super().__init__()

        self.user_settings = QSettings("QLabs", "TrackEditor")
        self.theme_preference = str(
            self.user_settings.value("appearance/theme", "system")
        ).lower()
        if self.theme_preference not in {"system", "light", "dark"}:
            self.theme_preference = "system"
        self._dark_theme = (
            system_uses_dark_theme()
            if self.theme_preference == "system"
            else self.theme_preference == "dark"
        )
        self.setStyleSheet(app_stylesheet(self._dark_theme))

        self.current_file: Path | None = None
        try:
            self.rotation_step_deg = float(
                self.user_settings.value("editor/rotation_step", 45.0)
            )
        except (TypeError, ValueError):
            self.rotation_step_deg = 45.0
        if self.rotation_step_deg not in {0.5, 1.0, 5.0, 15.0, 30.0, 45.0, 90.0}:
            self.rotation_step_deg = 45.0
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
        self.workspace_platform_center_x_m = float(default_platform.get("center_x_m", 0.0))
        self.workspace_platform_center_y_m = float(default_platform.get("center_y_m", 0.0))
        self.workspace_platform_size_x_m = float(default_platform["size_x_m"])
        self.workspace_platform_size_y_m = float(default_platform["size_y_m"])
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
        try:
            (
                self.cityscape_reference,
                self.cityscape_reference_source,
            ) = load_cityscape_reference()
        except FileNotFoundError:
            # Keep the editor usable if a packaged/user Cityscape reference is
            # missing. The workspace remains selectable, but no road overlay
            # will be drawn until a valid JSON is added.
            self.cityscape_reference = {"road_references": []}
            self.cityscape_reference_source = "unavailable"

        raster_path = str(self.cityscape_reference.get("_raster_path", "") or "")
        self.cityscape_reference_pixmap = (
            QPixmap(raster_path) if raster_path else QPixmap()
        )

        try:
            (
                self.townscape_reference,
                self.townscape_reference_source,
            ) = load_townscape_reference()
        except FileNotFoundError:
            self.townscape_reference = {"raster_reference": {}}
            self.townscape_reference_source = "unavailable"

        town_raster_path = str(
            self.townscape_reference.get("_raster_path", "") or ""
        )
        self.townscape_reference_pixmap = (
            QPixmap(town_raster_path) if town_raster_path else QPixmap()
        )

        self.workspace_mode = WORKSPACE_CUSTOM
        self.workspace_spline_z_m = workspace_mode_default_spline_z(
            self.workspace_mode
        )
        self.workspace_show_road_reference = True
        self.workspace_show_navigation_regions = True
        self.workspace_show_reference_points = True
        self.workspace_show_reference_labels = True

        self.path_edit_actor_id = None
        self.continuous_road_drawing = False
        self.continuous_road_points: list[QPointF] = []
        self.continuous_road_item: ContinuousRoadItem | None = None
        self.continuous_road_preview: QPointF | None = None
        self.sketch_tool_mode: str | None = None
        self.sketch_tool_points: list[QPointF] = []
        self.sketch_tool_preview: QPointF | None = None
        self.sketch_trim_active = False
        self.sketch_trim_preview: QPointF | None = None
        self.scenery_brush_active = False
        self.scenery_brush_start: QPointF | None = None
        self.scenery_brush_preview: QPointF | None = None

        self.setWindowTitle(f"QLabs Track Editor v{self.VERSION}")
        self.resize(1500, 920)

        self.scene = TrackScene(self)
        self.view = TrackView(self.scene)
        self.view.setMouseTracking(True)
        self.scenery_filler = SceneryAutoFiller(self.scene, self.view)

        self._build_ui()
        self.view.set_dark_theme(self._dark_theme)
        app = QApplication.instance()
        if app is not None:
            app.styleHints().colorSchemeChanged.connect(self._system_theme_changed)
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

    def _system_theme_changed(self, color_scheme):
        """Apply Windows/desktop appearance changes without restarting."""
        if self.theme_preference != "system":
            return
        dark = color_scheme == Qt.ColorScheme.Dark
        if dark == self._dark_theme:
            return
        self._dark_theme = dark
        self.setStyleSheet(app_stylesheet(dark))
        self.view.set_dark_theme(dark)

    def theme_preference_changed(self):
        """Apply and remember System, Light, or Dark appearance selection."""
        preference = str(self.theme_combo.currentData() or "system")
        self.theme_preference = preference
        self.user_settings.setValue("appearance/theme", preference)
        dark = system_uses_dark_theme() if preference == "system" else preference == "dark"
        self._dark_theme = dark
        self.setStyleSheet(app_stylesheet(dark))
        self.view.set_dark_theme(dark)

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
        inspector_contents.setObjectName("inspectorPanel")
        # Let the scroll area's viewport own the inspector width.  Giving the
        # contents competing min/max widths made the main-window size hint
        # change whenever actor-specific groups were shown or hidden.
        inspector_layout = QVBoxLayout(inspector_contents)
        inspector_layout.setContentsMargins(6, 0, 6, 0)
        inspector_layout.setSpacing(6)
        inspector_layout.setSizeConstraint(QLayout.SizeConstraint.SetDefaultConstraint)

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
        self.selection_label.setObjectName("selectionSummary")
        self.selection_label.setWordWrap(True)
        info_layout.addWidget(self.selection_label)
        inspector_layout.addWidget(self.info_group)

        # --------------------------------------------------------
        # Editable properties
        # --------------------------------------------------------
        self.properties_group = QGroupBox("PROPERTIES")
        self.properties_form = QFormLayout(self.properties_group)

        self.prop_x = self._make_spinbox(-10000.0, 10000.0, 0.10, 2, " m")
        self.prop_y = self._make_spinbox(-10000.0, 10000.0, 0.10, 2, " m")
        self.prop_rotation = self._make_spinbox(0.0, 359.99, 0.10, 2, "°")
        self.prop_rotation.setToolTip(
            "Actor orientation. Follow the cyan FRONT arrow on the canvas."
        )
        self.prop_length = self._make_spinbox(1.0, 1000.0, 1.0, 1, " m")
        self.prop_width = self._make_spinbox(0.05, 50.0, 0.05, 2, " m")
        self.prop_lanes = QSpinBox()
        self.prop_lanes.setRange(1, 12)
        self.prop_lanes.setValue(2)
        self.prop_lanes.setKeyboardTracking(False)
        self.prop_lanes.setToolTip(
            "Total traffic lanes. Changing this preserves the current per-lane width."
        )
        self.prop_radius = self._make_spinbox(1.0, 1000.0, 1.0, 1, " m")
        self.prop_arm = self._make_spinbox(2.0, 1000.0, 1.0, 1, " m")
        self.prop_height = self._make_spinbox(0.05, 20.0, 0.05, 2, " m")

        self.properties_form.addRow("X", self.prop_x)
        self.properties_form.addRow("Y", self.prop_y)
        self.properties_form.addRow("Orientation", self.prop_rotation)
        self.properties_form.addRow("Length", self.prop_length)
        self.properties_form.addRow("Width", self.prop_width)
        self.properties_form.addRow("Lanes", self.prop_lanes)
        self.properties_form.addRow("Radius", self.prop_radius)
        self.properties_form.addRow("Arm", self.prop_arm)
        self.properties_form.addRow("Height", self.prop_height)

        self.prop_x.valueChanged.connect(self.apply_position_properties)
        self.prop_y.valueChanged.connect(self.apply_position_properties)
        self.prop_rotation.valueChanged.connect(self.apply_rotation_property)
        self.prop_length.valueChanged.connect(self.apply_length_property)
        self.prop_width.valueChanged.connect(self.apply_width_property)
        self.prop_lanes.valueChanged.connect(self.apply_lane_count_property)
        self.prop_radius.valueChanged.connect(self.apply_radius_property)
        self.prop_arm.valueChanged.connect(self.apply_arm_property)
        self.prop_height.valueChanged.connect(self.apply_height_property)

        # Effective QLabs dimensions are read-only and derived from project scale.
        self.prop_effective = QLabel("")
        self.prop_effective.setWordWrap(True)
        self.prop_effective.setStyleSheet(
            "background: #20242a; padding: 6px; border-radius: 4px; color: #cfd6de;"
        )
        self.prop_effective.hide()

        inspector_layout.addWidget(self.properties_group)

        # --------------------------------------------------------
        # Continuous-road node tools
        # --------------------------------------------------------
        self.continuous_road_group = QGroupBox("ROAD PATH")
        continuous_layout = QVBoxLayout(self.continuous_road_group)
        self.continuous_road_help = QLabel(
            "Drag cyan nodes on the canvas. Double-click a node to remove it."
        )
        self.continuous_road_help.setWordWrap(True)
        continuous_layout.addWidget(self.continuous_road_help)
        self.continuous_road_smooth = QCheckBox("Smooth through control nodes")
        self.continuous_road_smooth.toggled.connect(
            self.apply_selected_continuous_road_smoothing
        )
        continuous_layout.addWidget(self.continuous_road_smooth)

        continuous_buttons = QHBoxLayout()
        self.continuous_add_node_button = QPushButton("Insert Node")
        self.continuous_remove_node_button = QPushButton("Remove Last")
        self.continuous_reverse_button = QPushButton("Reverse")
        continuous_buttons.addWidget(self.continuous_add_node_button)
        continuous_buttons.addWidget(self.continuous_remove_node_button)
        continuous_buttons.addWidget(self.continuous_reverse_button)
        continuous_layout.addLayout(continuous_buttons)

        self.continuous_add_node_button.clicked.connect(
            self.insert_selected_continuous_road_node
        )
        self.continuous_remove_node_button.clicked.connect(
            self.remove_selected_continuous_road_last_node
        )
        self.continuous_reverse_button.clicked.connect(
            self.reverse_selected_continuous_road
        )
        self.continuous_road_group.setVisible(False)
        inspector_layout.addWidget(self.continuous_road_group)

        self.sketch_guide_group = QGroupBox("CAD ROAD GUIDE")
        sketch_guide_layout = QVBoxLayout(self.sketch_guide_group)
        self.sketch_guide_help = QLabel()
        self.sketch_guide_help.setWordWrap(True)
        sketch_guide_layout.addWidget(self.sketch_guide_help)
        self.sketch_generate_selected_button = QPushButton(
            "Generate Road and Remove Guides"
        )
        self.sketch_generate_selected_button.clicked.connect(
            self.generate_roads_from_sketch
        )
        sketch_guide_layout.addWidget(self.sketch_generate_selected_button)
        self.sketch_guide_group.setVisible(False)
        inspector_layout.addWidget(self.sketch_guide_group)

        # --------------------------------------------------------
        # Reference image controls
        # --------------------------------------------------------
        self.reference_image_group = QGroupBox("REFERENCE IMAGE")
        reference_form = QFormLayout(self.reference_image_group)

        self.prop_reference_file = QLabel("")
        self.prop_reference_file.setWordWrap(True)
        self.prop_reference_file.setStyleSheet(
            "background: #20242a; padding: 5px; border-radius: 4px;"
        )

        self.prop_reference_width = self._make_spinbox(
            0.10, 50000.0, 0.10, 2, " m"
        )
        self.prop_reference_height = self._make_spinbox(
            0.10, 50000.0, 0.10, 2, " m"
        )
        self.prop_reference_opacity = self._make_spinbox(
            0.05, 1.0, 0.05, 2
        )

        self.prop_reference_lock_aspect = QCheckBox(
            "Keep image aspect ratio"
        )
        self.prop_reference_lock_aspect.setChecked(True)

        self.prop_reference_lock_position = QCheckBox(
            "Lock position / resize"
        )

        reference_button_row = QWidget()
        reference_button_layout = QHBoxLayout(reference_button_row)
        reference_button_layout.setContentsMargins(0, 0, 0, 0)
        reference_button_layout.setSpacing(5)

        self.reference_replace_button = QPushButton("Replace...")
        self.reference_fit_canvas_button = QPushButton("Fit Canvas")
        reference_button_layout.addWidget(self.reference_replace_button)
        reference_button_layout.addWidget(self.reference_fit_canvas_button)

        reference_form.addRow("File", self.prop_reference_file)
        reference_form.addRow("Width", self.prop_reference_width)
        reference_form.addRow("Height", self.prop_reference_height)
        reference_form.addRow("Opacity", self.prop_reference_opacity)
        reference_form.addRow(self.prop_reference_lock_aspect)
        reference_form.addRow(self.prop_reference_lock_position)
        reference_form.addRow(reference_button_row)

        self.prop_reference_width.valueChanged.connect(
            lambda value: self.apply_reference_image_size(
                "width", value
            )
        )
        self.prop_reference_height.valueChanged.connect(
            lambda value: self.apply_reference_image_size(
                "height", value
            )
        )
        self.prop_reference_opacity.valueChanged.connect(
            self.apply_reference_image_opacity
        )
        self.prop_reference_lock_aspect.toggled.connect(
            self.apply_reference_image_lock_aspect
        )
        self.prop_reference_lock_position.toggled.connect(
            self.apply_reference_image_lock_position
        )
        self.reference_replace_button.clicked.connect(
            self.replace_reference_image
        )
        self.reference_fit_canvas_button.clicked.connect(
            self.fit_selected_reference_image_to_canvas
        )

        self.reference_image_group.setVisible(False)
        inspector_layout.addWidget(self.reference_image_group)


        # --------------------------------------------------------
        # Road marking customization
        # --------------------------------------------------------
        self.markings_group = QGroupBox("ROAD MARKINGS")
        markings_form = QFormLayout(self.markings_group)

        def _make_marking_row():
            row_widget = QWidget()
            row_layout = QHBoxLayout(row_widget)
            row_layout.setContentsMargins(0, 0, 0, 0)
            row_layout.setSpacing(5)

            enabled = QCheckBox()
            enabled.setToolTip("Show this marking")
            color = QComboBox()
            for color_name in ROAD_MARKING_COLOR_RGB:
                color.addItem(color_name.title(), color_name)
            color.setFixedWidth(92)

            style = QComboBox()
            for label, value in ROAD_MARKING_STYLES:
                style.addItem(label, value)
            style.setFixedWidth(92)

            row_layout.addWidget(enabled)
            row_layout.addWidget(color)
            row_layout.addWidget(style)
            row_layout.addStretch(1)
            return row_widget, enabled, color, style

        (
            self.prop_marking_edge_a_row,
            self.prop_marking_edge_a,
            self.prop_marking_edge_a_color,
            self.prop_marking_edge_a_style,
        ) = _make_marking_row()
        (
            self.prop_marking_center_row,
            self.prop_marking_center,
            self.prop_marking_center_color,
            self.prop_marking_center_style,
        ) = _make_marking_row()
        (
            self.prop_marking_edge_b_row,
            self.prop_marking_edge_b,
            self.prop_marking_edge_b_color,
            self.prop_marking_edge_b_style,
        ) = _make_marking_row()
        (
            self.prop_marking_end_bar_row,
            self.prop_marking_end_bar,
            self.prop_marking_end_bar_color,
            self.prop_marking_end_bar_style,
        ) = _make_marking_row()

        markings_form.addRow("Edge A", self.prop_marking_edge_a_row)
        markings_form.addRow("Center", self.prop_marking_center_row)
        markings_form.addRow("Edge B", self.prop_marking_edge_b_row)
        markings_form.addRow("End bar", self.prop_marking_end_bar_row)

        marking_editors = (
            self.prop_marking_edge_a,
            self.prop_marking_edge_a_color,
            self.prop_marking_edge_a_style,
            self.prop_marking_center,
            self.prop_marking_center_color,
            self.prop_marking_center_style,
            self.prop_marking_edge_b,
            self.prop_marking_edge_b_color,
            self.prop_marking_edge_b_style,
            self.prop_marking_end_bar,
            self.prop_marking_end_bar_color,
            self.prop_marking_end_bar_style,
        )
        for editor in marking_editors:
            if isinstance(editor, QCheckBox):
                editor.toggled.connect(self.apply_road_marking_properties)
            else:
                editor.currentIndexChanged.connect(self.apply_road_marking_properties)

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
        self.guide_group = QGroupBox("LANE GUIDE")
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
        guide_form.addRow("Offset", self.prop_guide_offset)
        guide_form.addRow("Color", self.prop_guide_color)
        guide_form.addRow("RGB", rgb_widget)
        guide_form.addRow("Width", self.prop_guide_width)
        guide_form.addRow("Style", self.prop_guide_style)
        guide_form.addRow("Scale width", self.prop_guide_scale_width)

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
        self.inspector_scroll = QScrollArea()
        self.inspector_scroll.setWidgetResizable(True)
        self.inspector_scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded
        )
        self.inspector_scroll.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded
        )
        self.inspector_scroll.setWidget(inspector_contents)
        # The inspector lives in a resizable dock. Long forms can wrap and,
        # as a final fallback, scroll horizontally instead of disappearing.
        self.inspector_scroll.setMinimumWidth(280)
        self.inspector_scroll.setMaximumWidth(16777215)
        for form in inspector_contents.findChildren(QFormLayout):
            form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
            form.setFieldGrowthPolicy(
                QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow
            )

        # --------------------------------------------------------
        # Canvas
        # --------------------------------------------------------
        canvas_container = QWidget()
        canvas_layout = QVBoxLayout(canvas_container)
        canvas_layout.setContentsMargins(0, 0, 0, 0)
        canvas_layout.addWidget(self.view)

        bottom_contents = QWidget()
        bottom = QHBoxLayout(bottom_contents)
        bottom.setContentsMargins(0, 0, 0, 0)
        bottom.setSizeConstraint(QLayout.SizeConstraint.SetMinimumSize)
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
        bottom_scroll = QScrollArea()
        bottom_scroll.setObjectName("canvasStatusScroll")
        bottom_scroll.setFrameShape(QFrame.Shape.NoFrame)
        bottom_scroll.setWidgetResizable(True)
        bottom_scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded
        )
        bottom_scroll.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        bottom_scroll.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Fixed,
        )
        bottom_scroll.setWidget(bottom_contents)
        canvas_layout.addWidget(bottom_scroll)

        body.addWidget(canvas_container, 1)
        root.addLayout(body, 1)

        self.setCentralWidget(central)

        self.inspector_dock = QDockWidget("Inspector", self)
        self.inspector_dock.setObjectName("inspectorDock")
        self.inspector_dock.setAllowedAreas(
            Qt.DockWidgetArea.LeftDockWidgetArea
            | Qt.DockWidgetArea.RightDockWidgetArea
        )
        self.inspector_dock.setFeatures(
            QDockWidget.DockWidgetFeature.DockWidgetMovable
            | QDockWidget.DockWidgetFeature.DockWidgetFloatable
        )
        self.inspector_dock.setMinimumWidth(300)
        self.inspector_dock.setWidget(self.inspector_scroll)
        self.addDockWidget(
            Qt.DockWidgetArea.RightDockWidgetArea,
            self.inspector_dock,
        )
        self.resizeDocks(
            [self.inspector_dock],
            [380],
            Qt.Orientation.Horizontal,
        )

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
                if (
                    obj.get("type") == ContinuousRoadItem.TYPE_NAME
                    and bool(obj.get("auto_connector", False))
                ):
                    continue
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

        import_reference_action = QAction("Import Reference Image...", self)
        import_reference_action.setShortcut(QKeySequence("Ctrl+I"))
        import_reference_action.triggered.connect(self.add_reference_image)

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
        file_menu.addAction(import_reference_action)
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

    def _apply_new_open_road_actor_z_default(self, item: TrackItem):
        """Assign a sensible Base Z offset to newly added native Open Road actors.

        Open Road terrain elevation itself is resolved automatically by the
        exporter from the measured XYZ trajectory.  Base Z therefore remains a
        *relative* fine-tuning offset.  New ground actors are embedded slightly
        to hide their base, while crosswalks stay just above the surface to
        avoid z-fighting.  QCar spawn clearance is handled separately by the
        exporter so a moving QCar can settle/follow the true road elevation.
        """
        if self.workspace_mode != WORKSPACE_OPEN_ROAD:
            return
        if bool(self.workspace_platform_enabled):
            return
        if not isinstance(item, SceneActorItem):
            return

        if isinstance(item, SecondaryQCarItem):
            # QCar +1.5 m spawn clearance is transient and must not be stored as
            # Base Z, otherwise a waypoint-driven QCar would remain floating.
            item.z_m = 0.0
        elif isinstance(item, CrosswalkItem):
            item.z_m = float(OPEN_ROAD_CROSSWALK_SURFACE_OFFSET_M)
        else:
            item.z_m = float(OPEN_ROAD_NEW_ACTOR_GROUND_EMBED_M)

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
        self._apply_new_open_road_actor_z_default(item)
        item.setSelected(True)
        self.update_selection_info()
        self._commit_undo_transaction()

    def _workspace_new_road_width_m(self) -> float:
        """Width assigned to newly created road components in this workspace."""
        return workspace_mode_default_road_width(self.workspace_mode)


    def add_reference_image(self):
        """Import an image as a movable/resizable tracing reference."""
        file_name, _ = QFileDialog.getOpenFileName(
            self,
            "Import Reference Image",
            "",
            (
                "Images (*.png *.jpg *.jpeg *.bmp *.webp);;"
                "All Files (*)"
            ),
        )
        if not file_name:
            return

        item = ReferenceImageItem(
            image_path=file_name,
        )

        # Fit the newly imported image inside most of the editable canvas while
        # preserving the image's native aspect ratio.
        aspect = max(item.native_aspect_ratio(), 1e-9)
        max_width = max(1.0, self.canvas_width_m * 0.90)
        max_height = max(1.0, self.canvas_height_m * 0.90)

        width_m = max_width
        height_m = width_m / aspect

        if height_m > max_height:
            height_m = max_height
            width_m = height_m * aspect

        item.set_dimensions_m(
            width_m,
            height_m,
        )
        self._add_item_at_view_center(item)

    def _reference_image_item(self):
        item = self._single_selected_item()
        return item if isinstance(item, ReferenceImageItem) else None

    def replace_reference_image(self):
        item = self._reference_image_item()
        if item is None:
            return

        file_name, _ = QFileDialog.getOpenFileName(
            self,
            "Replace Reference Image",
            item.image_path,
            (
                "Images (*.png *.jpg *.jpeg *.bmp *.webp);;"
                "All Files (*)"
            ),
        )
        if not file_name:
            return

        self._begin_undo_transaction("Replace reference image")
        item.set_image_path(file_name)

        if item.lock_aspect_ratio:
            aspect = max(item.native_aspect_ratio(), 1e-9)
            item.set_dimensions_m(
                item.width_m,
                item.width_m / aspect,
            )

        self.scene.update()
        self.update_selection_info()
        self._commit_undo_transaction()

    def fit_selected_reference_image_to_canvas(self):
        item = self._reference_image_item()
        if item is None:
            return

        self._begin_undo_transaction("Fit reference image to canvas")

        aspect = max(item.native_aspect_ratio(), 1e-9)
        max_width = max(1.0, self.canvas_width_m * 0.95)
        max_height = max(1.0, self.canvas_height_m * 0.95)

        width_m = max_width
        height_m = width_m / aspect

        if height_m > max_height:
            height_m = max_height
            width_m = height_m * aspect

        item.set_dimensions_m(width_m, height_m)
        item.setPos(QPointF(0.0, 0.0))

        self.scene.update()
        self.update_selection_info()
        self._commit_undo_transaction()


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

    def toggle_continuous_road_drawing(self, enabled: bool):
        if enabled:
            self.start_continuous_road_drawing()
        else:
            self.finish_continuous_road_drawing()

    def _set_continuous_road_button_checked(self, checked: bool):
        button = getattr(self.top_bar, "continuous_road_button", None)
        if button is None:
            return
        button.blockSignals(True)
        button.setChecked(bool(checked))
        button.blockSignals(False)

    def start_continuous_road_drawing(self):
        if self.continuous_road_drawing:
            return
        self.cancel_sketch_trim(silent=True)
        self.cancel_scenery_brush(silent=True)
        self.cancel_sketch_tool()
        self.finish_path_editing()
        self.scene.clearSelection()
        self.continuous_road_drawing = True
        self.continuous_road_points = []
        self.continuous_road_item = None
        self.continuous_road_preview = None
        self._begin_undo_transaction("Draw continuous road")
        self._set_continuous_road_button_checked(True)
        self.view.setFocus()
        self.statusBar().showMessage(
            "Continuous road: left-click nodes; Backspace removes the last node; "
            "right-click or Enter finishes; Esc cancels."
        )
        self.view.viewport().update()

    def update_continuous_road_preview(self, scene_pos: QPointF):
        if not self.continuous_road_drawing:
            return
        self.continuous_road_preview = self.scene.snap_drawing_point(
            scene_pos,
            exclude_item=self.continuous_road_item,
        )
        self.view.viewport().update()

    def add_continuous_road_node(self, scene_pos: QPointF):
        if not self.continuous_road_drawing:
            return
        point = self.scene.snap_drawing_point(
            scene_pos,
            exclude_item=self.continuous_road_item,
        )
        if self.continuous_road_points:
            previous = self.continuous_road_points[-1]
            if math.hypot(point.x() - previous.x(), point.y() - previous.y()) < 5.0:
                self.statusBar().showMessage(
                    "Place the next road node at least 0.25 m away.",
                    2500,
                )
                return

        self.continuous_road_points.append(QPointF(point))
        self.continuous_road_preview = QPointF(point)

        if len(self.continuous_road_points) == 2:
            anchor = self.continuous_road_points[0]
            item = ContinuousRoadItem(
                points_m=[
                    (0.0, 0.0),
                    (
                        (self.continuous_road_points[1].x() - anchor.x())
                        / PIXELS_PER_METER,
                        -(self.continuous_road_points[1].y() - anchor.y())
                        / PIXELS_PER_METER,
                    ),
                ],
                width_m=self._workspace_new_road_width_m(),
            )
            # Position before scene insertion so the exact endpoint snap is
            # retained rather than interpreted as an item move.
            item.setPos(anchor)
            self.scene.addItem(item)
            item.setSelected(True)
            self.continuous_road_item = item
        elif len(self.continuous_road_points) > 2 and self.continuous_road_item is not None:
            self.continuous_road_item.set_scene_points(self.continuous_road_points)

        self.view.viewport().update()

    def remove_last_continuous_road_node(self):
        if not self.continuous_road_drawing or not self.continuous_road_points:
            return
        self.continuous_road_points.pop()
        if len(self.continuous_road_points) < 2:
            if self.continuous_road_item is not None:
                self.scene.removeItem(self.continuous_road_item)
                self.continuous_road_item = None
        elif self.continuous_road_item is not None:
            self.continuous_road_item.set_scene_points(self.continuous_road_points)
        self.continuous_road_preview = (
            QPointF(self.continuous_road_points[-1])
            if self.continuous_road_points
            else None
        )
        self.view.viewport().update()

    def finish_continuous_road_drawing(self):
        if not self.continuous_road_drawing:
            self._set_continuous_road_button_checked(False)
            return
        has_road = self.continuous_road_item is not None and len(
            self.continuous_road_points
        ) >= 2
        self.continuous_road_drawing = False
        self.continuous_road_preview = None
        self._set_continuous_road_button_checked(False)

        if has_road:
            self._commit_undo_transaction()
            self.statusBar().showMessage(
                "Continuous road created. Select it and drag its cyan nodes to reshape it.",
                4500,
            )
        else:
            if self.continuous_road_item is not None:
                self.scene.removeItem(self.continuous_road_item)
            self.undo_manager.cancel()
            self._update_undo_controls()
            self.statusBar().showMessage("Continuous road drawing cancelled.", 2500)

        self.continuous_road_points = []
        self.continuous_road_item = None
        self.view.viewport().update()

    def cancel_continuous_road_drawing(self):
        if not self.continuous_road_drawing:
            return
        if self.continuous_road_item is not None:
            self.scene.removeItem(self.continuous_road_item)
        self.continuous_road_drawing = False
        self.continuous_road_points = []
        self.continuous_road_item = None
        self.continuous_road_preview = None
        self.undo_manager.cancel()
        self._update_undo_controls()
        self._set_continuous_road_button_checked(False)
        self.statusBar().showMessage("Continuous road drawing cancelled.", 2500)
        self.view.viewport().update()

    # ------------------------------------------------------------
    # CAD road-guide sketching
    # ------------------------------------------------------------

    def _set_sketch_tool_buttons(self, active_mode: str | None):
        for mode, name in (
            ("line", "sketch_line_button"),
            ("arc", "sketch_arc_button"),
            ("circle", "sketch_circle_button"),
        ):
            button = getattr(self.top_bar, name, None)
            if button is None:
                continue
            button.blockSignals(True)
            button.setChecked(mode == active_mode)
            button.blockSignals(False)

    def toggle_sketch_tool(self, mode: str, enabled: bool):
        mode = str(mode)
        if enabled:
            self.start_sketch_tool(mode)
        elif self.sketch_tool_mode == mode:
            self.cancel_sketch_tool()

    def start_sketch_tool(self, mode: str):
        if mode not in {"line", "arc", "circle"}:
            return
        self.cancel_sketch_trim(silent=True)
        self.cancel_scenery_brush(silent=True)
        if self.continuous_road_drawing:
            self.finish_continuous_road_drawing()
        if self.sketch_tool_mode is not None:
            self.cancel_sketch_tool()
        self.finish_path_editing()
        self.scene.clearSelection()
        self.sketch_tool_mode = mode
        self.sketch_tool_points = []
        self.sketch_tool_preview = None
        self._set_sketch_tool_buttons(mode)
        self.view.setFocus()
        instructions = {
            "line": "Line guide: click start and end.",
            "arc": "Arc guide: click start, a point on the arc, then end.",
            "circle": "Circle guide: click center, then a point defining radius.",
        }
        self.statusBar().showMessage(
            instructions[mode] + " Right-click or Esc cancels."
        )
        self.view.viewport().update()

    def cancel_sketch_tool(self):
        if self.sketch_tool_mode is None:
            self._set_sketch_tool_buttons(None)
            return
        self.sketch_tool_mode = None
        self.sketch_tool_points = []
        self.sketch_tool_preview = None
        self.undo_manager.cancel()
        self._update_undo_controls()
        self._set_sketch_tool_buttons(None)
        self.statusBar().showMessage("Road-guide sketch cancelled.", 2000)
        self.view.viewport().update()

    def _sketch_snap_point(self, scene_pos: QPointF) -> QPointF:
        # The middle point of a three-point arc is a shape control rather than
        # a road connection, so it uses only the grid. Endpoints use the full
        # endpoint/circle-perimeter snap system.
        if self.sketch_tool_mode == "arc" and len(self.sketch_tool_points) == 1:
            return QPointF(
                snap_value(scene_pos.x(), GRID_PIXELS),
                snap_value(scene_pos.y(), GRID_PIXELS),
            )
        snapped = self.scene.snap_drawing_point(scene_pos)
        if self.sketch_tool_mode == "line" and len(self.sketch_tool_points) == 1:
            origin = self.sketch_tool_points[0]
            dx = snapped.x() - origin.x()
            dy = snapped.y() - origin.y()
            tolerance = math.tan(math.radians(7.0))
            if abs(dy) <= abs(dx) * tolerance:
                snapped.setY(origin.y())
            elif abs(dx) <= abs(dy) * tolerance:
                snapped.setX(origin.x())
        return snapped

    def update_sketch_tool_preview(self, scene_pos: QPointF):
        if self.sketch_tool_mode is None:
            return
        self.sketch_tool_preview = self._sketch_snap_point(scene_pos)
        self.view.viewport().update()

    @staticmethod
    def _guide_points_m(scene_points: list[QPointF], anchor: QPointF) -> list[tuple[float, float]]:
        return [
            (
                (point.x() - anchor.x()) / PIXELS_PER_METER,
                -(point.y() - anchor.y()) / PIXELS_PER_METER,
            )
            for point in scene_points
        ]

    def add_sketch_tool_point(self, scene_pos: QPointF):
        mode = self.sketch_tool_mode
        if mode is None:
            return
        point = self._sketch_snap_point(scene_pos)
        if self.sketch_tool_points and math.hypot(
            point.x() - self.sketch_tool_points[-1].x(),
            point.y() - self.sketch_tool_points[-1].y(),
        ) < 5.0:
            self.statusBar().showMessage("Choose a different sketch point.", 2000)
            return

        if not self.sketch_tool_points:
            self._begin_undo_transaction(f"Draw road-guide {mode}")
        self.sketch_tool_points.append(QPointF(point))
        self.sketch_tool_preview = QPointF(point)
        required = 3 if mode == "arc" else 2
        if len(self.sketch_tool_points) < required:
            self.view.viewport().update()
            return

        anchor = self.sketch_tool_points[0]
        if mode == "line":
            guide = SketchLineItem(
                points_m=self._guide_points_m(self.sketch_tool_points, anchor)
            )
            guide.setPos(anchor)
        elif mode == "arc":
            guide = SketchArcItem(
                points_m=self._guide_points_m(self.sketch_tool_points, anchor)
            )
            guide.setPos(anchor)
        else:
            center, radius_point = self.sketch_tool_points
            radius_m = math.hypot(
                radius_point.x() - center.x(),
                radius_point.y() - center.y(),
            ) / PIXELS_PER_METER
            guide = SketchCircleItem(radius_m=max(1.0, radius_m))
            guide.setPos(center)

        self.scene.addItem(guide)
        guide.setSelected(True)
        self.register_sketch_circle_ports(guide)
        self.sketch_tool_points = []
        self.sketch_tool_preview = None
        self._set_sketch_tool_buttons(mode)
        self._commit_undo_transaction()
        self.statusBar().showMessage(
            f"{guide.DISPLAY_NAME} created. Drag its orange handles to resize it; "
            f"use Generate Road when the sketch is ready. {mode.title()} remains active; "
            "right-click or Esc to exit the tool.",
            5000,
        )
        self.view.viewport().update()

    def remove_last_sketch_tool_point(self):
        if self.sketch_tool_mode is None or not self.sketch_tool_points:
            return
        self.sketch_tool_points.pop()
        self.sketch_tool_preview = (
            QPointF(self.sketch_tool_points[-1])
            if self.sketch_tool_points
            else None
        )
        self.view.viewport().update()

    # ------------------------------------------------------------
    # CAD guide trimming
    # ------------------------------------------------------------

    def _set_sketch_trim_button_checked(self, checked: bool):
        button = getattr(self.top_bar, "sketch_trim_button", None)
        if button is None:
            return
        button.blockSignals(True)
        button.setChecked(bool(checked))
        button.blockSignals(False)

    def toggle_sketch_trim(self, enabled: bool):
        if enabled:
            self.start_sketch_trim()
        else:
            self.cancel_sketch_trim()

    def start_sketch_trim(self):
        if self.sketch_trim_active:
            return
        self.cancel_scenery_brush(silent=True)
        if self.continuous_road_drawing:
            self.finish_continuous_road_drawing()
        self.cancel_sketch_tool()
        self.finish_path_editing()
        self.scene.clearSelection()
        self.sketch_trim_active = True
        self.sketch_trim_preview = None
        self._set_sketch_trim_button_checked(True)
        self.view.setFocus()
        self.view.setCursor(Qt.CursorShape.CrossCursor)
        self.statusBar().showMessage(
            "Trim: click the unwanted guide segment between crossings. "
            "For a crossed circle, the removed section leaves an exact arc. "
            "Right-click or Esc exits."
        )
        self.view.viewport().update()

    def cancel_sketch_trim(self, *, silent: bool = False):
        was_active = self.sketch_trim_active
        self.sketch_trim_active = False
        self.sketch_trim_preview = None
        self._set_sketch_trim_button_checked(False)
        if was_active and hasattr(self, "view"):
            self.view.unsetCursor()
        if was_active and not silent:
            self.statusBar().showMessage("Trim tool closed.", 2000)
        if hasattr(self, "view"):
            self.view.viewport().update()

    @staticmethod
    def _polyline_metrics(points: list[QPointF]) -> tuple[list[float], float]:
        cumulative = [0.0]
        for start, end in zip(points, points[1:]):
            cumulative.append(
                cumulative[-1]
                + math.hypot(end.x() - start.x(), end.y() - start.y())
            )
        return cumulative, cumulative[-1] if cumulative else 0.0

    @staticmethod
    def _polyline_point_at(
        points: list[QPointF],
        cumulative: list[float],
        distance: float,
    ) -> QPointF:
        if not points:
            return QPointF()
        total = cumulative[-1]
        distance = max(0.0, min(total, float(distance)))
        for index in range(len(points) - 1):
            start_distance = cumulative[index]
            end_distance = cumulative[index + 1]
            if distance <= end_distance or index == len(points) - 2:
                segment_length = end_distance - start_distance
                ratio = 0.0 if segment_length <= 1e-9 else (
                    (distance - start_distance) / segment_length
                )
                start = points[index]
                end = points[index + 1]
                return QPointF(
                    start.x() + (end.x() - start.x()) * ratio,
                    start.y() + (end.y() - start.y()) * ratio,
                )
        return QPointF(points[-1])

    @classmethod
    def _polyline_slice(
        cls,
        points: list[QPointF],
        cumulative: list[float],
        start_distance: float,
        end_distance: float,
    ) -> list[QPointF]:
        if end_distance <= start_distance or len(points) < 2:
            return []
        result = [cls._polyline_point_at(points, cumulative, start_distance)]
        for index, distance in enumerate(cumulative[1:-1], start=1):
            if start_distance < distance < end_distance:
                result.append(QPointF(points[index]))
        result.append(cls._polyline_point_at(points, cumulative, end_distance))
        return result

    @staticmethod
    def _nearest_on_polyline(
        scene_pos: QPointF,
        points: list[QPointF],
        cumulative: list[float],
    ) -> tuple[QPointF, float, float]:
        best_point = QPointF(points[0])
        best_distance = float("inf")
        best_along = 0.0
        for index, (start, end) in enumerate(zip(points, points[1:])):
            dx = end.x() - start.x()
            dy = end.y() - start.y()
            length_squared = dx * dx + dy * dy
            ratio = 0.0
            if length_squared > 1e-12:
                ratio = (
                    (scene_pos.x() - start.x()) * dx
                    + (scene_pos.y() - start.y()) * dy
                ) / length_squared
                ratio = max(0.0, min(1.0, ratio))
            candidate = QPointF(start.x() + dx * ratio, start.y() + dy * ratio)
            distance = math.hypot(
                candidate.x() - scene_pos.x(),
                candidate.y() - scene_pos.y(),
            )
            if distance < best_distance:
                best_point = candidate
                best_distance = distance
                segment_length = cumulative[index + 1] - cumulative[index]
                best_along = cumulative[index] + segment_length * ratio
        return best_point, best_distance, best_along

    def _closest_sketch_guide(self, scene_pos: QPointF):
        best = None
        for guide in self.scene.track_items():
            if not isinstance(guide, SketchGuideItem):
                continue
            points = list(guide.sampled_scene_points())
            if len(points) < 2:
                continue
            cumulative, total = self._polyline_metrics(points)
            if total <= 1e-6:
                continue
            point, distance, along = self._nearest_on_polyline(
                scene_pos, points, cumulative
            )
            if best is None or distance < best[1]:
                best = (guide, distance, point, along, points, cumulative, total)
        return best

    def update_sketch_trim_preview(self, scene_pos: QPointF):
        if not self.sketch_trim_active:
            return
        closest = self._closest_sketch_guide(scene_pos)
        tolerance = max(
            0.45 * PIXELS_PER_METER,
            12.0 / max(0.10, abs(self.view.transform().m11())),
        )
        self.sketch_trim_preview = (
            QPointF(closest[2])
            if closest is not None and closest[1] <= tolerance
            else QPointF(scene_pos)
        )
        self.view.viewport().update()

    def _guide_trim_distances(
        self,
        guide: SketchGuideItem,
        points: list[QPointF],
        cumulative: list[float],
        total: float,
    ) -> list[float]:
        cuts = []
        for node in self.scene.sketch_connection_nodes():
            for member in node["members"]:
                if member["guide"] is not guide:
                    continue
                segment = int(member["segment"])
                if not (0 <= segment < len(points) - 1):
                    continue
                ratio = max(0.0, min(1.0, float(member["ratio"])))
                segment_length = cumulative[segment + 1] - cumulative[segment]
                cuts.append(cumulative[segment] + segment_length * ratio)

        # Roads also act as valid cutting boundaries, so an overlong guide can
        # be trimmed exactly where it crosses an existing road centerline.
        for road in self.scene.track_items():
            for centerline in self.scene.road_centerline_polylines(road):
                for guide_segment, (start, end) in enumerate(zip(points, points[1:])):
                    segment_length = cumulative[guide_segment + 1] - cumulative[guide_segment]
                    for road_start, road_end in zip(centerline, centerline[1:]):
                        crossing = self.scene._segment_intersection(
                            start, end, road_start, road_end
                        )
                        if crossing is None:
                            continue
                        _, guide_ratio, _ = crossing
                        cuts.append(
                            cumulative[guide_segment] + segment_length * guide_ratio
                        )

        tolerance = 0.08 * PIXELS_PER_METER
        normalized = []
        for distance in sorted(cuts):
            if isinstance(guide, SketchCircleItem):
                distance %= total
            if not normalized or abs(distance - normalized[-1]) > tolerance:
                normalized.append(distance)
        if (
            isinstance(guide, SketchCircleItem)
            and len(normalized) > 1
            and total - normalized[-1] + normalized[0] <= tolerance
        ):
            normalized.pop()
        return normalized

    def _create_trimmed_guide(
        self,
        source: SketchGuideItem,
        scene_points: list[QPointF],
    ) -> SketchGuideItem | None:
        cumulative, total = self._polyline_metrics(scene_points)
        if total < 0.25 * PIXELS_PER_METER:
            return None
        start = scene_points[0]
        if isinstance(source, SketchLineItem):
            guide = SketchLineItem(
                points_m=self._guide_points_m(
                    [start, scene_points[-1]], start
                )
            )
        else:
            middle = self._polyline_point_at(
                scene_points, cumulative, total / 2.0
            )
            guide = SketchArcItem(
                points_m=self._guide_points_m(
                    [start, middle, scene_points[-1]], start
                )
            )
        guide.setPos(start)
        return guide

    def trim_sketch_guide_at(self, scene_pos: QPointF):
        if not self.sketch_trim_active:
            return
        closest = self._closest_sketch_guide(scene_pos)
        tolerance = max(
            0.45 * PIXELS_PER_METER,
            12.0 / max(0.10, abs(self.view.transform().m11())),
        )
        if closest is None or closest[1] > tolerance:
            self.statusBar().showMessage(
                "No guide under the trim cursor.", 2500
            )
            return

        guide, _, _, clicked_along, points, cumulative, total = closest
        cuts = self._guide_trim_distances(guide, points, cumulative, total)
        pieces: list[list[QPointF]] = []

        if isinstance(guide, SketchCircleItem):
            if len(cuts) < 2:
                self.statusBar().showMessage(
                    "A circle needs at least two guide/road crossings before it can be trimmed.",
                    4500,
                )
                return
            remove_start = cuts[-1]
            remove_end = cuts[0] + total
            for index, start_distance in enumerate(cuts):
                end_distance = (
                    cuts[index + 1] if index + 1 < len(cuts) else cuts[0] + total
                )
                candidate_click = clicked_along
                if candidate_click < start_distance:
                    candidate_click += total
                if start_distance <= candidate_click <= end_distance:
                    remove_start = start_distance
                    remove_end = end_distance
                    break

            keep_start = remove_end % total
            keep_length = total - (remove_end - remove_start)
            if keep_length < 0.25 * PIXELS_PER_METER:
                self.statusBar().showMessage(
                    "That trim would remove the whole circle.", 3000
                )
                return
            keep_end = keep_start + keep_length
            if keep_end <= total + 1e-6:
                first = self._polyline_slice(
                    points, cumulative, keep_start, min(total, keep_end)
                )
            else:
                first = self._polyline_slice(points, cumulative, keep_start, total)
                remainder = keep_end - total
                second = self._polyline_slice(points, cumulative, 0.0, remainder)
                if first and second:
                    first.extend(second[1:])
                elif second:
                    first = second
            pieces = [first]
        else:
            interior_cuts = [
                distance
                for distance in cuts
                if 1e-6 < distance < total - 1e-6
            ]
            if not interior_cuts:
                self.statusBar().showMessage(
                    "This guide has no interior guide/road crossing to trim against.",
                    4500,
                )
                return
            boundaries = [0.0] + interior_cuts + [total]
            remove_index = len(boundaries) - 2
            for index, (start_distance, end_distance) in enumerate(
                zip(boundaries, boundaries[1:])
            ):
                if start_distance <= clicked_along <= end_distance:
                    remove_index = index
                    break
            remove_start = boundaries[remove_index]
            remove_end = boundaries[remove_index + 1]
            if remove_start > 1e-6:
                pieces.append(
                    self._polyline_slice(points, cumulative, 0.0, remove_start)
                )
            if remove_end < total - 1e-6:
                pieces.append(
                    self._polyline_slice(points, cumulative, remove_end, total)
                )

        replacements = [
            replacement
            for replacement in (
                self._create_trimmed_guide(guide, piece) for piece in pieces
            )
            if replacement is not None
        ]
        if not replacements:
            self.statusBar().showMessage(
                "That trim would leave no usable guide segment.", 3000
            )
            return

        self._begin_undo_transaction("Trim road guide")
        self.scene.clearSelection()
        self.scene.removeItem(guide)
        for replacement in replacements:
            self.scene.addItem(replacement)
            replacement.setSelected(True)
            self.register_sketch_circle_ports(replacement)
        self.scene.update()
        self.update_selection_info()
        self._commit_undo_transaction()
        self.statusBar().showMessage(
            f"Trimmed {guide.DISPLAY_NAME}; kept {len(replacements)} segment"
            f"{'s' if len(replacements) != 1 else ''}. Trim remains active.",
            4500,
        )
        self.view.viewport().update()

    def register_sketch_circle_ports(self, guide: TrackItem):
        if isinstance(guide, SketchCircleItem):
            return
        if not isinstance(guide, (SketchLineItem, SketchArcItem)):
            return
        circles = [
            item
            for item in self.scene.track_items()
            if isinstance(item, SketchCircleItem)
        ]
        changed = False
        for connection in guide.connection_points_scene():
            point = connection["pos"]
            for circle in circles:
                candidate = circle.nearest_connection_candidate_scene(point)
                if candidate is None:
                    continue
                if math.hypot(
                    candidate.x() - point.x(),
                    candidate.y() - point.y(),
                ) <= 0.10 * PIXELS_PER_METER:
                    before = len(circle.ports_deg)
                    circle.add_port_scene(point)
                    changed = changed or len(circle.ports_deg) != before
        if changed:
            self.scene.update()

    def _apply_guide_geometry_to_road(
        self,
        guide: SketchGuideItem,
        road: ContinuousRoadItem,
    ) -> bool:
        scene_points = self.scene.sketch_road_points(guide)
        if len(scene_points) < 2:
            return False
        anchor = scene_points[0]
        road.setRotation(0.0)
        road.set_pos_exact(anchor)
        road.set_points_m(self._generated_local_points(scene_points, anchor))
        road.smooth = False
        road.source_guide_id = str(guide.object_id)
        road.update()
        return True

    def sync_generated_road_from_guide(self, guide: TrackItem) -> bool:
        """Live-update the road owned by an edited CAD guide, if it exists."""
        if not isinstance(guide, SketchGuideItem) or not guide.generated_road_id:
            return False
        road = next(
            (
                item
                for item in self.scene.track_items()
                if isinstance(item, ContinuousRoadItem)
                and str(item.object_id) == str(guide.generated_road_id)
            ),
            None,
        )
        if road is None:
            return False
        changed = self._apply_guide_geometry_to_road(guide, road)
        if changed:
            self.scene.update()
        return changed

    @staticmethod
    def _generated_local_points(scene_points: list[QPointF], anchor: QPointF):
        return [
            (
                (point.x() - anchor.x()) / PIXELS_PER_METER,
                -(point.y() - anchor.y()) / PIXELS_PER_METER,
            )
            for point in scene_points
        ]

    @staticmethod
    def _polyline_length_px(points: list[QPointF]) -> float:
        return sum(
            math.hypot(end.x() - start.x(), end.y() - start.y())
            for start, end in zip(points, points[1:])
        )

    @staticmethod
    def _trim_polyline_start(
        points: list[QPointF],
        distance_px: float,
    ) -> list[QPointF]:
        remaining = max(0.0, float(distance_px))
        for index, (start, end) in enumerate(zip(points, points[1:])):
            length = math.hypot(end.x() - start.x(), end.y() - start.y())
            if length <= 1e-9:
                continue
            if remaining < length:
                ratio = remaining / length
                cut = QPointF(
                    start.x() + (end.x() - start.x()) * ratio,
                    start.y() + (end.y() - start.y()) * ratio,
                )
                return [cut] + [QPointF(point) for point in points[index + 1:]]
            remaining -= length
        return [QPointF(points[-1])]

    @classmethod
    def _trim_polyline_end(
        cls,
        points: list[QPointF],
        distance_px: float,
    ) -> list[QPointF]:
        return list(reversed(cls._trim_polyline_start(
            list(reversed(points)),
            distance_px,
        )))

    @classmethod
    def _join_paths_with_fillet(
        cls,
        first: list[QPointF],
        second: list[QPointF],
        road_width_px: float,
    ) -> list[QPointF]:
        """Join two endpoint-connected paths with a tangent circular fillet."""
        if len(first) < 2 or len(second) < 2:
            return [QPointF(point) for point in first + second[1:]]
        node = QPointF(
            (first[-1].x() + second[0].x()) / 2.0,
            (first[-1].y() + second[0].y()) / 2.0,
        )
        first = [QPointF(point) for point in first]
        second = [QPointF(point) for point in second]
        first[-1] = QPointF(node)
        second[0] = QPointF(node)

        incoming = node - first[-2]
        outgoing = second[1] - node
        in_length = math.hypot(incoming.x(), incoming.y())
        out_length = math.hypot(outgoing.x(), outgoing.y())
        if in_length <= 1e-6 or out_length <= 1e-6:
            return first + second[1:]
        incoming /= in_length
        outgoing /= out_length
        dot = max(-1.0, min(1.0,
            incoming.x() * outgoing.x() + incoming.y() * outgoing.y()
        ))
        turn_angle = math.acos(dot)
        if turn_angle <= math.radians(5.0) or turn_angle >= math.radians(170.0):
            return first + second[1:]

        tangent_factor = math.tan(turn_angle / 2.0)
        if tangent_factor <= 1e-6:
            return first + second[1:]
        desired_radius = max(2.0 * PIXELS_PER_METER, road_width_px * 0.75)
        available = min(
            cls._polyline_length_px(first) * 0.35,
            cls._polyline_length_px(second) * 0.35,
        )
        tangent_distance = min(desired_radius * tangent_factor, available)
        if tangent_distance <= 0.25 * PIXELS_PER_METER:
            return first + second[1:]
        radius = tangent_distance / tangent_factor

        trimmed_first = cls._trim_polyline_end(first, tangent_distance)
        trimmed_second = cls._trim_polyline_start(second, tangent_distance)
        if not trimmed_first or not trimmed_second:
            return first + second[1:]
        start = trimmed_first[-1]
        end = trimmed_second[0]
        normal_in = QPointF(-incoming.y(), incoming.x())
        normal_out = QPointF(-outgoing.y(), outgoing.x())
        denominator = (
            normal_in.x() * normal_out.y()
            - normal_in.y() * normal_out.x()
        )
        if abs(denominator) <= 1e-8:
            return first + second[1:]
        delta = end - start
        along_normal = (
            delta.x() * normal_out.y() - delta.y() * normal_out.x()
        ) / denominator
        center = start + normal_in * along_normal
        measured_radius = math.hypot(start.x() - center.x(), start.y() - center.y())
        if measured_radius <= 1e-6:
            return first + second[1:]

        start_angle = math.atan2(start.y() - center.y(), start.x() - center.x())
        end_angle = math.atan2(end.y() - center.y(), end.x() - center.x())
        cross = incoming.x() * outgoing.y() - incoming.y() * outgoing.x()
        if cross >= 0.0:
            sweep = (end_angle - start_angle) % math.tau
        else:
            sweep = -((start_angle - end_angle) % math.tau)
        if abs(sweep) > math.pi:
            sweep += -math.tau if sweep > 0.0 else math.tau
        samples = max(4, int(math.ceil(abs(math.degrees(sweep)) / 5.0)))
        arc = [
            QPointF(
                center.x() + measured_radius * math.cos(start_angle + sweep * step / samples),
                center.y() + measured_radius * math.sin(start_angle + sweep * step / samples),
            )
            for step in range(samples + 1)
        ]
        return trimmed_first[:-1] + arc + trimmed_second[1:]

    def _connected_guide_paths(
        self,
        guides: list[SketchGuideItem],
        road_width_px: float,
    ) -> list[list[QPointF]]:
        """Merge endpoint-connected open guides into filleted road chains."""
        output: list[list[QPointF]] = []
        records = []
        endpoint_tolerance = 0.12 * PIXELS_PER_METER
        nodes: list[dict] = []

        def node_for(point: QPointF, record_index: int, endpoint: int) -> int:
            for node_index, node in enumerate(nodes):
                if math.hypot(
                    point.x() - node["pos"].x(),
                    point.y() - node["pos"].y(),
                ) <= endpoint_tolerance:
                    node["refs"].append((record_index, endpoint))
                    return node_index
            nodes.append({"pos": QPointF(point), "refs": [(record_index, endpoint)]})
            return len(nodes) - 1

        for guide in guides:
            points = self.scene.sketch_road_points(guide)
            if len(points) < 2:
                continue
            closed = math.hypot(
                points[0].x() - points[-1].x(),
                points[0].y() - points[-1].y(),
            ) <= endpoint_tolerance
            if closed:
                output.append([QPointF(point) for point in points])
                continue
            record_index = len(records)
            records.append({"points": points, "nodes": [None, None]})
            records[-1]["nodes"][0] = node_for(points[0], record_index, 0)
            records[-1]["nodes"][1] = node_for(points[-1], record_index, 1)

        visited: set[int] = set()
        for start_index, record in enumerate(records):
            if start_index in visited:
                continue
            entry_endpoint = 0
            for candidate in (0, 1):
                node_id = record["nodes"][candidate]
                if len(nodes[node_id]["refs"]) != 2:
                    entry_endpoint = candidate
                    break

            current_index = start_index
            current_entry = entry_endpoint
            current_path: list[QPointF] = []
            while current_index not in visited:
                visited.add(current_index)
                current = records[current_index]
                oriented = (
                    [QPointF(point) for point in current["points"]]
                    if current_entry == 0
                    else [QPointF(point) for point in reversed(current["points"])]
                )
                current_path = (
                    oriented
                    if not current_path
                    else self._join_paths_with_fillet(
                        current_path,
                        oriented,
                        road_width_px,
                    )
                )
                exit_endpoint = 1 - current_entry
                exit_node = current["nodes"][exit_endpoint]
                refs = nodes[exit_node]["refs"]
                if len(refs) != 2:
                    break
                next_ref = next(
                    (ref for ref in refs if ref[0] != current_index),
                    None,
                )
                if next_ref is None or next_ref[0] in visited:
                    break
                current_index, current_entry = next_ref
            if len(current_path) >= 2:
                output.append(current_path)
        return output

    def generate_roads_from_sketch(self):
        selected_guides = [
            item
            for item in self.scene.selected_track_items()
            if isinstance(item, SketchGuideItem)
        ]
        guides = selected_guides or [
            item
            for item in self.scene.track_items()
            if isinstance(item, SketchGuideItem)
        ]
        if not guides:
            QMessageBox.information(
                self,
                "No Road Guides",
                "Draw a Line, Arc, or Circle guide first, then generate the road.",
            )
            return

        self._begin_undo_transaction("Generate roads from CAD guides")
        connection_nodes = self.scene.sketch_connection_nodes()
        for node in connection_nodes:
            for member in node["members"]:
                member_guide = member["guide"]
                if isinstance(member_guide, SketchCircleItem):
                    member_guide.add_port_scene(node["pos"])
        stale_ids = {
            str(guide.generated_road_id)
            for guide in guides
            if guide.generated_road_id
        }
        for item in list(self.scene.track_items()):
            if isinstance(item, ContinuousRoadItem) and str(item.object_id) in stale_ids:
                self.scene.removeItem(item)

        width_m = self._workspace_new_road_width_m()
        road_paths = self._connected_guide_paths(
            guides,
            width_m * PIXELS_PER_METER,
        )
        created_roads: list[ContinuousRoadItem] = []
        for scene_points in road_paths:
            anchor = scene_points[0]
            road = ContinuousRoadItem(
                points_m=self._generated_local_points(scene_points, anchor),
                width_m=width_m,
                smooth=False,
            )
            # The CAD geometry is already resolved. Do not let the normal
            # movable-item grid/endpoint snapping shift separate generated
            # paths away from one another when they enter the scene.
            road.set_pos_exact(anchor)
            self.scene.addItem(road)
            created_roads.append(road)

        self.scene.clearSelection()
        for guide in guides:
            self.scene.removeItem(guide)
        if len(created_roads) == 1:
            created_roads[0].setSelected(True)

        self.scene.update()
        self.update_selection_info()
        self._commit_undo_transaction()
        self.statusBar().showMessage(
            f"Generated {len(created_roads)} continuous road"
            f"{'s' if len(created_roads) != 1 else ''}; removed "
            f"{len(guides)} guide{'s' if len(guides) != 1 else ''}.",
            5000,
        )

    @staticmethod
    def _coordinate_spin(value: float) -> QDoubleSpinBox:
        spin = QDoubleSpinBox()
        spin.setRange(-100000.0, 100000.0)
        spin.setDecimals(3)
        spin.setSingleStep(0.5)
        spin.setSuffix(" m")
        spin.setValue(float(value))
        return spin

    def _point_position_dialog(
        self,
        title: str,
        scene_point: QPointF,
    ) -> QPointF | None:
        x_m, y_m = scene_to_world(scene_point)
        dialog = QDialog(self)
        dialog.setWindowTitle(title)
        form = QFormLayout(dialog)
        x_spin = self._coordinate_spin(x_m)
        y_spin = self._coordinate_spin(y_m)
        form.addRow("X", x_spin)
        form.addRow("Y", y_spin)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        form.addRow(buttons)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return None
        return world_to_scene(x_spin.value(), y_spin.value())

    def edit_sketch_control_point(
        self,
        guide: SketchGuideItem,
        index: int,
        role: str,
    ):
        if guide.scene() is not self.scene:
            return
        if isinstance(guide, SketchCircleItem) and role == "radius":
            dialog = QDialog(self)
            dialog.setWindowTitle("Set Circle Radius")
            form = QFormLayout(dialog)
            radius_spin = self._coordinate_spin(guide.radius_m)
            radius_spin.setRange(1.0, 100000.0)
            form.addRow("Radius", radius_spin)
            buttons = QDialogButtonBox(
                QDialogButtonBox.StandardButton.Ok
                | QDialogButtonBox.StandardButton.Cancel
            )
            buttons.accepted.connect(dialog.accept)
            buttons.rejected.connect(dialog.reject)
            form.addRow(buttons)
            if dialog.exec() != QDialog.DialogCode.Accepted:
                return
            self._begin_undo_transaction("Set circle radius")
            guide.prepareGeometryChange()
            guide.radius_m = radius_spin.value()
            guide._sync_handle_positions([
                (QPointF(guide.radius_px, 0.0), "radius")
            ])
            guide._geometry_changed()
            self._commit_undo_transaction()
            return

        points = getattr(guide, "points_px", [])
        if not (0 <= index < len(points)):
            return
        target_scene = self._point_position_dialog(
            "Set Guide Point Position",
            guide.mapToScene(points[index]),
        )
        if target_scene is None:
            return
        local = guide.mapFromScene(target_scene)
        if isinstance(guide, SketchLineItem):
            other = guide.points_px[1 - index]
            if guide.axis_constraint == "horizontal":
                local.setY(other.y())
            elif guide.axis_constraint == "vertical":
                local.setX(other.x())
        self._begin_undo_transaction("Set guide point position")
        guide.handle_moved(index, role, local)
        definitions = (
            [(guide.points_px[0], "endpoint"), (guide.points_px[1], "endpoint")]
            if isinstance(guide, SketchLineItem)
            else [
                (guide.points_px[0], "endpoint"),
                (guide.points_px[1], "control"),
                (guide.points_px[2], "endpoint"),
            ]
        )
        guide._sync_handle_positions(definitions)
        self.register_sketch_circle_ports(guide)
        self._commit_undo_transaction()

    def set_sketch_line_constraint(
        self,
        guide: SketchLineItem,
        constraint: str,
        moved_index: int,
    ):
        if guide.scene() is not self.scene or constraint not in {"", "horizontal", "vertical"}:
            return
        moved_index = 0 if int(moved_index) == 0 else 1
        other_index = 1 - moved_index
        self._begin_undo_transaction("Change line constraint")
        guide.prepareGeometryChange()
        guide.axis_constraint = constraint
        if constraint == "horizontal":
            guide.points_px[moved_index].setY(guide.points_px[other_index].y())
        elif constraint == "vertical":
            guide.points_px[moved_index].setX(guide.points_px[other_index].x())
        guide._sync_handle_positions([
            (guide.points_px[0], "endpoint"),
            (guide.points_px[1], "endpoint"),
        ])
        guide._geometry_changed()
        self._commit_undo_transaction()

    def edit_continuous_road_control_point(
        self,
        road: ContinuousRoadItem,
        index: int,
    ):
        points = road.local_points_px()
        if road.scene() is not self.scene or not (0 <= index < len(points)):
            return
        target_scene = self._point_position_dialog(
            "Set Road Point Position",
            road.mapToScene(points[index]),
        )
        if target_scene is None:
            return
        local = road.mapFromScene(target_scene)
        values = list(road.points_m)
        values[index] = (
            local.x() / PIXELS_PER_METER,
            -local.y() / PIXELS_PER_METER,
        )
        self._begin_undo_transaction("Set road point position")
        road.set_points_m(values)
        self.update_selection_info()
        self._commit_undo_transaction()

    def insert_continuous_road_control_point(
        self,
        road: ContinuousRoadItem,
        index: int,
        *,
        before: bool,
    ):
        points = list(road.points_m)
        neighbor = index - 1 if before else index + 1
        if road.scene() is not self.scene or not (
            0 <= index < len(points) and 0 <= neighbor < len(points)
        ):
            return
        midpoint = (
            (points[index][0] + points[neighbor][0]) / 2.0,
            (points[index][1] + points[neighbor][1]) / 2.0,
        )
        insertion = index if before else index + 1
        self._begin_undo_transaction("Insert continuous-road point")
        points.insert(insertion, midpoint)
        road.set_points_m(points)
        self.update_selection_info()
        self._commit_undo_transaction()

    def delete_continuous_road_control_point(
        self,
        road: ContinuousRoadItem,
        index: int,
    ):
        if road.scene() is not self.scene or len(road.points_m) <= 2:
            return
        self._begin_undo_transaction("Delete continuous-road point")
        road.remove_node(index)
        self.update_selection_info()
        self._commit_undo_transaction()

    def add_crosswalk(self):
        crosswalk = CrosswalkItem()
        selected = self._single_selected_item()
        if (
            selected is not None
            and selected.supports_road_markings()
            and hasattr(selected, "width_m")
        ):
            lane_count = max(1, int(getattr(selected, "lane_count", 2)))
            crosswalk.length_m = max(
                0.25,
                float(selected.width_m) / float(lane_count),
            )
            crosswalk.sync_resize_handle()
        self._add_item_at_view_center(crosswalk)

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
            "size_x_m": max(0.1, float(self.workspace_platform_size_x_m)),
            "size_y_m": max(0.1, float(self.workspace_platform_size_y_m)),
            "center_x_m": float(self.workspace_platform_center_x_m),
            "center_y_m": float(self.workspace_platform_center_y_m),
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
        cx = data["center_x_m"]
        cy = data["center_y_m"]
        self.workspace_platform_info_label.setText(
            f"{size_text}  •  center {cx:g}, {cy:g} m  •  {support_text}"
        )
        self.workspace_platform_info_label.setToolTip(
            data.get("size_note", "")
            + "\nCenter X/Y and Size X/Y are editable cover geometry; the profile only supplies defaults."
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

        # A profile change deliberately loads a sensible starting footprint and
        # height. The user can immediately tune X/Y position, X/Y size and Z.
        widgets = (
            self.workspace_platform_center_x_spin,
            self.workspace_platform_center_y_spin,
            self.workspace_platform_size_x_spin,
            self.workspace_platform_size_y_spin,
            self.workspace_platform_top_z_spin,
            self.workspace_platform_bottom_z_spin,
        )
        for widget in widgets:
            widget.blockSignals(True)
        try:
            self.workspace_platform_center_x_spin.setValue(
                float(profile.get("center_x_m", 0.0))
            )
            self.workspace_platform_center_y_spin.setValue(
                float(profile.get("center_y_m", 0.0))
            )
            self.workspace_platform_size_x_spin.setValue(float(profile["size_x_m"]))
            self.workspace_platform_size_y_spin.setValue(float(profile["size_y_m"]))
            self.workspace_platform_top_z_spin.setValue(
                float(profile["default_top_z_m"])
            )
            self.workspace_platform_bottom_z_spin.setValue(
                float(profile["default_bottom_z_m"])
            )
        finally:
            for widget in widgets:
                widget.blockSignals(False)

        self.workspace_platform_center_x_m = float(profile.get("center_x_m", 0.0))
        self.workspace_platform_center_y_m = float(profile.get("center_y_m", 0.0))
        self.workspace_platform_size_x_m = float(profile["size_x_m"])
        self.workspace_platform_size_y_m = float(profile["size_y_m"])
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
        self.workspace_platform_center_x_m = float(
            self.workspace_platform_center_x_spin.value()
        )
        self.workspace_platform_center_y_m = float(
            self.workspace_platform_center_y_spin.value()
        )
        self.workspace_platform_size_x_m = max(
            0.1, float(self.workspace_platform_size_x_spin.value())
        )
        self.workspace_platform_size_y_m = max(
            0.1, float(self.workspace_platform_size_y_spin.value())
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
        # Backward compatible: older projects do not contain these overrides,
        # so fall back to the selected workspace profile geometry.
        self.workspace_platform_center_x_m = float(
            data.get("center_x_m", profile.get("center_x_m", 0.0))
        )
        self.workspace_platform_center_y_m = float(
            data.get("center_y_m", profile.get("center_y_m", 0.0))
        )
        self.workspace_platform_size_x_m = max(
            0.1, float(data.get("size_x_m", profile["size_x_m"]))
        )
        self.workspace_platform_size_y_m = max(
            0.1, float(data.get("size_y_m", profile["size_y_m"]))
        )
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
            self.workspace_platform_center_x_spin,
            self.workspace_platform_center_y_spin,
            self.workspace_platform_size_x_spin,
            self.workspace_platform_size_y_spin,
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
            self.workspace_platform_center_x_spin.setValue(
                self.workspace_platform_center_x_m
            )
            self.workspace_platform_center_y_spin.setValue(
                self.workspace_platform_center_y_m
            )
            self.workspace_platform_size_x_spin.setValue(
                self.workspace_platform_size_x_m
            )
            self.workspace_platform_size_y_spin.setValue(
                self.workspace_platform_size_y_m
            )
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

    def _auto_size_compact_workspace_canvas(self):
        """Resize the editable canvas around Cityscape/Townscape references.

        The editor canvas is centered on QLabs (0, 0), while the calibrated
        raster bounds are not necessarily symmetric about the origin.  Use
        the largest absolute X/Y extent plus a small design margin, then round
        up to a clean 5 m increment.  This is only called when the user
        actively switches workspace; saved project canvas dimensions remain
        authoritative when a JSON project is reopened.
        """
        if self.workspace_mode in (WORKSPACE_CITYSCAPE, WORKSPACE_CITYSCAPE_LITE):
            bounds = self.cityscape_reference.get("bounds", {})
        elif self.workspace_mode in (WORKSPACE_TOWNSCAPE, WORKSPACE_TOWNSCAPE_LITE):
            bounds = self.townscape_reference.get("bounds", {})
        else:
            return

        min_x = float(bounds.get("min_x", -30.0))
        max_x = float(bounds.get("max_x", 30.0))
        min_y = float(bounds.get("min_y", -30.0))
        max_y = float(bounds.get("max_y", 30.0))
        margin_m = 8.0

        width_m = 2.0 * (max(abs(min_x), abs(max_x)) + margin_m)
        height_m = 2.0 * (max(abs(min_y), abs(max_y)) + margin_m)
        width_m = max(40.0, math.ceil(width_m / 5.0) * 5.0)
        height_m = max(40.0, math.ceil(height_m / 5.0) * 5.0)

        self.canvas_width_m = width_m
        self.canvas_height_m = height_m
        self.canvas_width_spin.blockSignals(True)
        self.canvas_height_spin.blockSignals(True)
        try:
            self.canvas_width_spin.setValue(width_m)
            self.canvas_height_spin.setValue(height_m)
        finally:
            self.canvas_width_spin.blockSignals(False)
            self.canvas_height_spin.blockSignals(False)

        self.scene.set_editable_area_size(width_m, height_m)

    def _schedule_compact_workspace_autofit(self):
        """Fit after Qt finishes the current combo/layout update."""
        if self.workspace_mode in (
            WORKSPACE_CITYSCAPE,
            WORKSPACE_CITYSCAPE_LITE,
            WORKSPACE_TOWNSCAPE,
            WORKSPACE_TOWNSCAPE_LITE,
        ):
            QTimer.singleShot(0, self.fit_selected_workspace)

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

        # Compact mapped workspaces use the calibrated road-reference bounds
        # to size the editable design canvas automatically.
        self._auto_size_compact_workspace_canvas()

        # Keep the optional cover-box profile aligned with the selected main
        # workspace, without automatically enabling the cover itself.
        self._sync_workspace_platform_profile_to_mode()
        self._apply_workspace_mode(fit_reference=False)
        self._schedule_compact_workspace_autofit()
        if self.workspace_mode not in (
            WORKSPACE_CITYSCAPE, WORKSPACE_CITYSCAPE_LITE,
            WORKSPACE_TOWNSCAPE, WORKSPACE_TOWNSCAPE_LITE,
        ):
            self.fit_selected_workspace()
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
        self.workspace_platform_center_x_m = float(profile.get("center_x_m", 0.0))
        self.workspace_platform_center_y_m = float(profile.get("center_y_m", 0.0))
        self.workspace_platform_size_x_m = float(profile["size_x_m"])
        self.workspace_platform_size_y_m = float(profile["size_y_m"])
        self.workspace_platform_top_z_m = float(profile["default_top_z_m"])
        self.workspace_platform_bottom_z_m = float(profile["default_bottom_z_m"])

        widgets = (
            self.workspace_platform_profile_combo,
            self.workspace_platform_center_x_spin,
            self.workspace_platform_center_y_spin,
            self.workspace_platform_size_x_spin,
            self.workspace_platform_size_y_spin,
            self.workspace_platform_top_z_spin,
            self.workspace_platform_bottom_z_spin,
        )
        for widget in widgets:
            widget.blockSignals(True)
        try:
            index = self.workspace_platform_profile_combo.findData(profile_key)
            if index >= 0:
                self.workspace_platform_profile_combo.setCurrentIndex(index)
            self.workspace_platform_center_x_spin.setValue(
                self.workspace_platform_center_x_m
            )
            self.workspace_platform_center_y_spin.setValue(
                self.workspace_platform_center_y_m
            )
            self.workspace_platform_size_x_spin.setValue(
                self.workspace_platform_size_x_m
            )
            self.workspace_platform_size_y_spin.setValue(
                self.workspace_platform_size_y_m
            )
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

    def _cityscape_scene_rect(
        self,
        margin_m: float = 20.0,
    ) -> QRectF:
        """Return the traced Cityscape road-reference bounds in scene units."""
        bounds = self.cityscape_reference.get("bounds", {})
        min_x = float(bounds.get("min_x", -80.0))
        max_x = float(bounds.get("max_x", 80.0))
        min_y = float(bounds.get("min_y", -60.0))
        max_y = float(bounds.get("max_y", 60.0))

        left = (min_x - margin_m) * PIXELS_PER_METER
        right = (max_x + margin_m) * PIXELS_PER_METER
        top = -(max_y + margin_m) * PIXELS_PER_METER
        bottom = -(min_y - margin_m) * PIXELS_PER_METER
        return QRectF(left, top, right - left, bottom - top)

    def _townscape_scene_rect(
        self,
        margin_m: float = 20.0,
    ) -> QRectF:
        """Return the calibrated Townscape road-reference bounds in scene units."""
        bounds = self.townscape_reference.get("bounds", {})
        min_x = float(bounds.get("min_x", -30.0))
        max_x = float(bounds.get("max_x", 30.0))
        min_y = float(bounds.get("min_y", -20.0))
        max_y = float(bounds.get("max_y", 20.0))

        left = (min_x - margin_m) * PIXELS_PER_METER
        right = (max_x + margin_m) * PIXELS_PER_METER
        top = -(max_y + margin_m) * PIXELS_PER_METER
        bottom = -(min_y - margin_m) * PIXELS_PER_METER
        return QRectF(left, top, right - left, bottom - top)

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
        cityscape = self.workspace_mode in (
            WORKSPACE_CITYSCAPE, WORKSPACE_CITYSCAPE_LITE
        )
        townscape = self.workspace_mode in (
            WORKSPACE_TOWNSCAPE, WORKSPACE_TOWNSCAPE_LITE
        )
        mapped_workspace = open_road or cityscape or townscape
        profile = workspace_mode_profile(self.workspace_mode)
        label = workspace_mode_label(self.workspace_mode)

        # Open Road, Cityscape/Cityscape Lite, and Townscape/Townscape Lite
        # have mapped placement references.  The Lite variants intentionally
        # share the same calibrated road geometry as their full counterparts.
        self.workspace_show_road_checkbox.setEnabled(mapped_workspace)
        self.workspace_show_nav_checkbox.setEnabled(mapped_workspace)
        self.workspace_show_points_checkbox.setEnabled(mapped_workspace)
        self.workspace_show_labels_checkbox.setEnabled(mapped_workspace)
        self.fit_workspace_button.setEnabled(True)

        if mapped_workspace:
            # Reference coordinates are already native QLabs metres, so a
            # second project scale would make actor placement misleading.
            
            self.project_scale_combo.setEnabled(True)
            self.custom_scale_denominator.setEnabled(True)

            self.scale_help_label.setText(
                f"{label} reference coordinates are native QLabs meters. "
                "Project scale is locked to 1:1 while this workspace is selected."
            )

            if open_road:
                display_reference = open_road_display_reference(
                    self.open_road_reference
                )
                raw_count = int(display_reference.get("raw_point_count", 0))
                display_count = int(
                    display_reference.get("display_point_count", raw_count)
                )
                loop_distance_m = display_reference.get(
                    "completed_loop_distance_m", None
                )
                return_distance_m = display_reference.get(
                    "return_distance_m", None
                )
                tolerance_m = display_reference.get(
                    "simplify_tolerance_m", None
                )

                measurement_text = ""
                if display_reference.get("measured", False):
                    measurement_text = (
                        f"Measured QCar world-transform reference: {raw_count:,} raw "
                        "X/Y/Z samples"
                    )
                    if loop_distance_m is not None:
                        measurement_text += (
                            f"; first completed loop ≈ "
                            f"{float(loop_distance_m) / 1000.0:.2f} km"
                        )
                    if return_distance_m is not None:
                        measurement_text += (
                            f" and closes within {float(return_distance_m):.2f} m "
                            "of the start"
                        )
                    if tolerance_m is not None:
                        measurement_text += (
                            f". Display uses {display_count:,} points with a "
                            f"{float(tolerance_m):.1f} m XY simplification tolerance. "
                        )
                    else:
                        measurement_text += ". "
                else:
                    calibration = self.open_road_reference.get("calibration", {})
                    rms = calibration.get("anchor_rms_error_m", None)
                    measurement_text = "Documentation-derived placement reference. "
                    if rms is not None:
                        measurement_text += (
                            f"Approximate anchor-fit RMS: {float(rms):.1f} m. "
                        )

                self.workspace_reference_note.setText(
                    measurement_text
                    + "The editor draws the measured path in X/Y; recorded Z remains "
                    "available in the JSON but is not represented by this top-down view. "
                    f"The logger path is calibrated as lane "
                    f"{OPEN_ROAD_REFERENCE_MEASURED_LANE_FROM_SEPARATOR} (middle) of the "
                    "three-lane upper carriageway on the South/start straight. The "
                    f"approximate separator center is therefore offset "
                    f"{OPEN_ROAD_REFERENCE_MEASURED_TO_SEPARATOR_OFFSET_M:.3f} m toward "
                    "the driver's left from the recorded trajectory. Lane edges and the "
                    "median remain visual estimates, not surveyed geometry. "
                    f"Spline Z defaults to {self.workspace_spline_z_m:.2f} m. "
                    f"Visual context width ≈ {OPEN_ROAD_REFERENCE_TOTAL_WIDTH_M:.1f} m "
                    f"({OPEN_ROAD_REFERENCE_LANES_PER_SIDE} lanes each direction, "
                    f"{OPEN_ROAD_REFERENCE_LANE_WIDTH_M:.1f} m/lane + "
                    f"{OPEN_ROAD_REFERENCE_SEPARATOR_WIDTH_M:.2f} m separator). "
                    f"Source data: {self.open_road_reference_source}."
                )

                self.scene.setSceneRect(
                    self._open_road_scene_rect().united(
                        self.scene.editable_area_rect().adjusted(
                            -500.0, -500.0, 500.0, 500.0
                        )
                    )
                )
            elif cityscape:
                calibration = self.cityscape_reference.get("calibration", {})
                rms = calibration.get("anchor_rms_error_m", None)
                maximum = calibration.get("anchor_max_error_m", None)
                accuracy_text = ""
                if rms is not None:
                    accuracy_text += f" Anchor-fit RMS ≈ {float(rms):.2f} m."
                if maximum is not None:
                    accuracy_text += f" Max anchor residual ≈ {float(maximum):.2f} m."

                raster_meta = self.cityscape_reference.get("raster_reference", {})
                if raster_meta and not self.cityscape_reference_pixmap.isNull():
                    reference_description = (
                        "Cityscape calibrated raster placement reference rectified from "
                        "an actual QLabs top-down view using the validation-marker "
                        "coordinates. The raster is editor-only and is never exported. "
                    )
                else:
                    reference_description = (
                        "Cityscape fallback vector placement reference derived from "
                        "the documentation image. "
                    )

                self.workspace_reference_note.setText(
                    reference_description
                    + "The navigation overlay shows only Quanser's documented 400 m × "
                    "400 m outer boundary; internal obstacle holes are not reconstructed. "
                    f"Native-workspace track base Z: {self.workspace_spline_z_m:.2f} m."
                    + accuracy_text
                    + f" Source data: {self.cityscape_reference_source}."
                )

                self.scene.setSceneRect(
                    self._workspace_profile_scene_rect().united(
                        self._cityscape_scene_rect(margin_m=30.0)
                    ).united(
                        self.scene.editable_area_rect().adjusted(
                            -500.0, -500.0, 500.0, 500.0
                        )
                    )
                )
            else:
                calibration = self.townscape_reference.get("calibration", {})
                rms = calibration.get("marker_anchor_rms_error_m", None)
                maximum = calibration.get("marker_anchor_max_error_m", None)
                accuracy_text = ""
                if rms is not None:
                    accuracy_text += f" Four-marker RMS ≈ {float(rms):.3f} m."
                if maximum is not None:
                    accuracy_text += f" Max marker residual ≈ {float(maximum):.3f} m."

                self.workspace_reference_note.setText(
                    "Townscape calibrated raster placement reference rectified from "
                    "QLabs top-down captures using four temporary validation markers: "
                    "Open World Origin, Car Spawn Spot, Road Parking 1, and Road "
                    "Parking 2. The clean raster is editor-only and is never exported. "
                    "The same road geometry is used for Townscape and Townscape Lite. "
                    "The navigation overlay shows only Quanser's documented 400 m × "
                    "400 m outer boundary. "
                    f"Native-workspace track base Z: {self.workspace_spline_z_m:.2f} m."
                    + accuracy_text
                    + f" Source data: {self.townscape_reference_source}."
                )

                self.scene.setSceneRect(
                    self._workspace_profile_scene_rect().united(
                        self._townscape_scene_rect(margin_m=30.0)
                    ).united(
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
        """Fit the selected mapped reference or native workspace footprint."""
        if self.workspace_mode == WORKSPACE_OPEN_ROAD:
            rect = self._open_road_scene_rect(margin_m=250.0)
        elif self.workspace_mode in (WORKSPACE_CITYSCAPE, WORKSPACE_CITYSCAPE_LITE):
            rect = self._cityscape_scene_rect(margin_m=8.0)
        elif self.workspace_mode in (WORKSPACE_TOWNSCAPE, WORKSPACE_TOWNSCAPE_LITE):
            rect = self._townscape_scene_rect(margin_m=8.0)
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

    def _draw_cityscape_reference(
        self,
        painter: QPainter,
        rect: QRectF,
    ):
        reference = self.cityscape_reference
        view_scale = max(abs(self.view.transform().m11()), 1e-9)

        # Documented outer path-finding boundary. Quanser notes that buildings,
        # trees, fences and other obstacles create holes inside it; only the
        # outer 400 m × 400 m boundary is therefore shown here.
        if self.workspace_show_navigation_regions:
            nav_pen = QPen(QColor(255, 95, 75, 190), 2, Qt.PenStyle.DashLine)
            nav_pen.setCosmetic(True)
            painter.setPen(nav_pen)
            painter.setBrush(QColor(255, 80, 70, 18))
            for region in reference.get("navigation_regions", []):
                polygon = region.get("polygon", [])
                if len(polygon) < 3:
                    continue
                path = QPainterPath()
                first = world_to_scene(float(polygon[0][0]), float(polygon[0][1]))
                path.moveTo(first)
                for point in polygon[1:]:
                    path.lineTo(world_to_scene(float(point[0]), float(point[1])))
                path.closeSubpath()
                painter.drawPath(path)

        if self.workspace_show_road_reference:
            raster = reference.get("raster_reference", {})
            bounds = raster.get("world_bounds", {})
            pixmap = self.cityscape_reference_pixmap

            if raster and bounds and not pixmap.isNull():
                min_x = float(bounds.get("min_x", -25.0))
                max_x = float(bounds.get("max_x", 30.0))
                min_y = float(bounds.get("min_y", -18.0))
                max_y = float(bounds.get("max_y", 55.0))

                target = QRectF(
                    min_x * PIXELS_PER_METER,
                    -max_y * PIXELS_PER_METER,
                    (max_x - min_x) * PIXELS_PER_METER,
                    (max_y - min_y) * PIXELS_PER_METER,
                )

                painter.save()
                painter.setOpacity(float(raster.get("opacity", 0.86)))
                painter.setPen(Qt.PenStyle.NoPen)
                painter.drawPixmap(target, pixmap, QRectF(pixmap.rect()))
                painter.restore()
            else:
                # Legacy fallback retained for projects that only contain the
                # older documentation-derived vector trace.
                road_width_px = DEFAULT_ROAD_WIDTH_M * PIXELS_PER_METER
                surface_pen = QPen(QColor(74, 80, 88, 205), road_width_px)
                surface_pen.setCosmetic(False)
                surface_pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
                surface_pen.setCapStyle(Qt.PenCapStyle.RoundCap)

                edge_pen = QPen(QColor(242, 245, 248, 220), 1.5)
                edge_pen.setCosmetic(True)

                center_pen = QPen(
                    QColor(255, 205, 65, 190),
                    1.0,
                    Qt.PenStyle.DotLine,
                )
                center_pen.setCosmetic(True)

                for road in reference.get("road_references", []):
                    points = road.get("points", [])
                    closed = bool(road.get("closed", False))
                    if len(points) < 2:
                        continue

                    path = _world_polyline_path(points, closed)
                    painter.setPen(surface_pen)
                    painter.setBrush(Qt.BrushStyle.NoBrush)
                    painter.drawPath(path)

                    half_width = DEFAULT_ROAD_WIDTH_M / 2.0
                    painter.setPen(edge_pen)
                    for sign in (-1.0, 1.0):
                        offset_points = _offset_world_polyline(
                            points, sign * half_width, closed
                        )
                        painter.drawPath(
                            _world_polyline_path(offset_points, closed)
                        )

                    painter.setPen(center_pen)
                    painter.drawPath(path)

        if self.workspace_show_reference_points:
            point_pen = QPen(QColor(255, 220, 80, 245), 2)
            point_pen.setCosmetic(True)
            painter.setPen(point_pen)
            painter.setBrush(QColor(255, 190, 55, 220))
            marker_radius_scene = 5.0 / view_scale
            label_positions = []

            for point in reference.get("reference_points", []):
                scene_pos = world_to_scene(
                    float(point.get("x", 0.0)),
                    float(point.get("y", 0.0)),
                )
                painter.drawEllipse(scene_pos, marker_radius_scene, marker_radius_scene)
                if self.workspace_show_reference_labels:
                    label_positions.append((painter.worldTransform().map(scene_pos), str(point.get("name", ""))))

            if label_positions:
                painter.save()
                painter.resetTransform()
                font = painter.font()
                font.setPixelSize(11)
                painter.setFont(font)
                painter.setPen(QPen(QColor(255, 235, 145, 245), 1))
                for device_pos, text in label_positions:
                    painter.drawText(device_pos + QPointF(8.0, -6.0), text)
                painter.restore()

    def _draw_townscape_reference(
        self,
        painter: QPainter,
        rect: QRectF,
    ):
        reference = self.townscape_reference
        view_scale = max(abs(self.view.transform().m11()), 1e-9)

        if self.workspace_show_navigation_regions:
            nav_pen = QPen(QColor(255, 95, 75, 190), 2, Qt.PenStyle.DashLine)
            nav_pen.setCosmetic(True)
            painter.setPen(nav_pen)
            painter.setBrush(QColor(255, 80, 70, 18))
            for region in reference.get("navigation_regions", []):
                polygon = region.get("polygon", [])
                if len(polygon) < 3:
                    continue
                path = QPainterPath()
                first = world_to_scene(float(polygon[0][0]), float(polygon[0][1]))
                path.moveTo(first)
                for point in polygon[1:]:
                    path.lineTo(world_to_scene(float(point[0]), float(point[1])))
                path.closeSubpath()
                painter.drawPath(path)

        if self.workspace_show_road_reference:
            raster = reference.get("raster_reference", {})
            bounds = raster.get("world_bounds", {})
            pixmap = self.townscape_reference_pixmap
            if raster and bounds and not pixmap.isNull():
                min_x = float(bounds.get("min_x", -24.0))
                max_x = float(bounds.get("max_x", 28.0))
                min_y = float(bounds.get("min_y", -16.0))
                max_y = float(bounds.get("max_y", 14.0))
                target = QRectF(
                    min_x * PIXELS_PER_METER,
                    -max_y * PIXELS_PER_METER,
                    (max_x - min_x) * PIXELS_PER_METER,
                    (max_y - min_y) * PIXELS_PER_METER,
                )
                painter.save()
                painter.setOpacity(float(raster.get("opacity", 0.88)))
                painter.setPen(Qt.PenStyle.NoPen)
                painter.drawPixmap(target, pixmap, QRectF(pixmap.rect()))
                painter.restore()

        if self.workspace_show_reference_points:
            point_pen = QPen(QColor(255, 220, 80, 245), 2)
            point_pen.setCosmetic(True)
            painter.setPen(point_pen)
            painter.setBrush(QColor(255, 190, 55, 220))
            marker_radius_scene = 5.0 / view_scale
            label_positions = []
            for point in reference.get("reference_points", []):
                scene_pos = world_to_scene(
                    float(point.get("x", 0.0)),
                    float(point.get("y", 0.0)),
                )
                painter.drawEllipse(scene_pos, marker_radius_scene, marker_radius_scene)
                if self.workspace_show_reference_labels:
                    label_positions.append(
                        (painter.worldTransform().map(scene_pos), str(point.get("name", "")))
                    )

            if label_positions:
                painter.save()
                painter.resetTransform()
                font = painter.font()
                font.setPixelSize(11)
                painter.setFont(font)
                painter.setPen(QPen(QColor(255, 235, 145, 245), 1))
                for device_pos, text in label_positions:
                    painter.drawText(device_pos + QPointF(8.0, -6.0), text)
                painter.restore()

    def draw_workspace_reference(
        self,
        painter: QPainter,
        rect: QRectF,
    ):
        if self.workspace_mode in (WORKSPACE_CITYSCAPE, WORKSPACE_CITYSCAPE_LITE):
            self._draw_cityscape_reference(painter, rect)
            return

        if self.workspace_mode in (WORKSPACE_TOWNSCAPE, WORKSPACE_TOWNSCAPE_LITE):
            self._draw_townscape_reference(painter, rect)
            return

        if self.workspace_mode != WORKSPACE_OPEN_ROAD:
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
        # Measured QCar trajectory + approximate lane-width context
        # --------------------------------------------------------
        if self.workspace_show_road_reference:
            # The packaged logger data contains 46k+ raw 3-D samples.  The
            # loader extracts the first completed lap and simplifies only its
            # display copy; the full X/Y/Z recording remains untouched in the
            # reference JSON.
            road_data = open_road_display_reference(reference)
            points = road_data.get("points", [])
            road_closed = bool(road_data.get("closed", False))

            if len(points) >= 2:
                # The measured samples are the QCar's lane center. During the
                # logger run the car occupied lane 2 (middle lane) of the
                # upper three-lane carriageway on the South/start straight.
                # Reconstruct an approximate separator/road centerline by
                # moving from the measured lane toward the driver's left.
                measured_path = _world_polyline_path(
                    points,
                    road_closed,
                )
                road_center_points = _offset_world_polyline(
                    points,
                    OPEN_ROAD_REFERENCE_MEASURED_TO_SEPARATOR_NORMAL_SIGN
                    * OPEN_ROAD_REFERENCE_MEASURED_TO_SEPARATOR_OFFSET_M,
                    road_closed,
                )
                road_path = _world_polyline_path(
                    road_center_points,
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
                            road_center_points,
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
                        road_center_points,
                        side_sign * outer_offset,
                        road_closed,
                    )
                    painter.drawPath(
                        _world_polyline_path(
                            edge_points,
                            road_closed,
                        )
                    )

                # Thin measured reference so the actual logged QCar lane
                # trajectory remains visible in its calibrated middle-lane
                # position inside the approximate road-width context.
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
                painter.drawPath(measured_path)

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
        self.user_settings.setValue("editor/rotation_step", self.rotation_step_deg)
        self.rotate_btn.setText(f"Rotate +{self.rotation_step_deg:g}°")
        self.rotate_btn.setToolTip(
            f"Rotate selected +{self.rotation_step_deg:g}° (R)"
        )
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
            self.prop_lanes,
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
            self._set_property_row_visible(self.prop_lanes, False)
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

            elif isinstance(item, ContinuousRoadItem):
                self._set_property_row_visible(self.prop_width, True)
                self.prop_width.setValue(item.width_m)

            elif isinstance(item, (Curve90RoadItem, Curve45RoadItem)):
                self._set_property_row_visible(self.prop_radius, True)
                self._set_property_row_visible(self.prop_width, True)
                self.prop_radius.setValue(item.radius_m)
                self.prop_width.setValue(item.width_m)

            elif isinstance(item, SketchCircleItem):
                self._set_property_row_visible(self.prop_radius, True)
                self.prop_radius.setValue(item.radius_m)

            elif isinstance(item, (TJunctionItem, CrossIntersectionItem)):
                self._set_property_row_visible(self.prop_arm, True)
                self._set_property_row_visible(self.prop_width, True)
                self.prop_arm.setValue(item.arm_length_m)
                self.prop_width.setValue(item.width_m)

            elif isinstance(item, CrosswalkItem):
                self._set_property_row_visible(self.prop_length, True)
                self._set_property_row_visible(self.prop_width, True)
                self.prop_length.setValue(item.length_m)
                self.prop_width.setValue(item.width_m)

            if (
                item.supports_road_markings()
                and not bool(getattr(item, "auto_connector", False))
            ):
                self._set_property_row_visible(self.prop_lanes, True)
                self.prop_lanes.setValue(int(getattr(item, "lane_count", 2)))

            self.prop_effective.setText(self._effective_text(item))
        finally:
            self._block_property_signals(False)
            self._property_refreshing = False

    def _refresh_continuous_road_editor(self, item: TrackItem | None):
        road = item if isinstance(item, ContinuousRoadItem) else None
        self.continuous_road_group.setVisible(road is not None)
        if road is None:
            return
        self.continuous_road_help.setText(
            f"{len(road.points_m)} nodes · {road.total_length_m:.1f} m. "
            "Drag cyan nodes on the canvas. Right-click a node for exact "
            "position, insert, and delete controls."
        )
        self.continuous_road_smooth.blockSignals(True)
        self.continuous_road_smooth.setChecked(road.smooth)
        self.continuous_road_smooth.blockSignals(False)
        self.continuous_remove_node_button.setEnabled(len(road.points_m) > 2)

    def _refresh_sketch_guide_editor(self, item: TrackItem | None):
        guide = item if isinstance(item, SketchGuideItem) else None
        self.sketch_guide_group.setVisible(guide is not None)
        if guide is None:
            return
        intersections = sum(
            1
            for node in self.scene.sketch_connection_nodes()
            if any(member["guide"] is guide for member in node["members"])
        )
        connections = len(guide.connection_points_local()) + intersections
        generated = "Yes" if guide.generated_road_id else "Not yet"
        self.sketch_guide_help.setText(
            f"Logical connections: {connections} "
            f"({intersections} crossing{'s' if intersections != 1 else ''})\n"
            f"Generated road: {generated}\n"
            "Drag the orange handles on the canvas to resize or reshape this "
            "guide. Right-click a handle for precise controls. Generation "
            "consumes the guide and leaves an editable continuous road."
        )

    def apply_selected_continuous_road_smoothing(self, checked: bool):
        road = self._single_selected_item()
        if not isinstance(road, ContinuousRoadItem):
            return
        self._begin_undo_transaction("Change continuous-road smoothing")
        road.prepareGeometryChange()
        road.smooth = bool(checked)
        road.update()
        self.scene.update()
        self.update_selection_info()
        self._commit_undo_transaction()

    def _set_scenery_brush_button_checked(self, checked: bool):
        button = getattr(self.top_bar, "area_fill_button", None)
        if button is None:
            return
        button.blockSignals(True)
        button.setChecked(bool(checked))
        button.blockSignals(False)

    def toggle_scenery_brush(self, enabled: bool):
        if enabled:
            self.start_scenery_brush()
        else:
            self.cancel_scenery_brush()

    def start_scenery_brush(self):
        if self.scenery_brush_active:
            return
        self.cancel_sketch_trim(silent=True)
        if self.continuous_road_drawing:
            self.finish_continuous_road_drawing()
        self.cancel_sketch_tool()
        self.finish_path_editing()
        self.scene.clearSelection()
        self.scenery_brush_active = True
        self.scenery_brush_start = None
        self.scenery_brush_preview = None
        self._set_scenery_brush_button_checked(True)
        self.view.setFocus()
        self.view.setCursor(Qt.CursorShape.CrossCursor)
        self.statusBar().showMessage(
            "Environment brush: drag a rectangle to generate the selected scenery style. "
            "The brush stays active; right-click or Esc exits."
        )
        self.view.viewport().update()

    def cancel_scenery_brush(self, *, silent: bool = False):
        was_active = self.scenery_brush_active
        old_rect = self._scenery_brush_selection_rect()
        self.scenery_brush_active = False
        self.scenery_brush_start = None
        self.scenery_brush_preview = None
        self._set_scenery_brush_button_checked(False)
        if was_active and hasattr(self, "view"):
            self.view.unsetCursor()
        if was_active and not silent:
            self.statusBar().showMessage("Environment brush closed.", 2000)
        if hasattr(self, "view"):
            self._update_scenery_brush_overlay(old_rect)

    def _scenery_brush_selection_rect(self) -> QRectF | None:
        if self.scenery_brush_start is None or self.scenery_brush_preview is None:
            return None
        return QRectF(
            self.scenery_brush_start,
            self.scenery_brush_preview,
        ).normalized()

    def _update_scenery_brush_overlay(
        self,
        old_rect: QRectF | None = None,
    ):
        """Repaint only the old/new brush overlay instead of the whole canvas."""
        new_rect = self._scenery_brush_selection_rect()
        dirty_rect = None
        for candidate in (old_rect, new_rect):
            if candidate is None:
                continue
            dirty_rect = (
                QRectF(candidate)
                if dirty_rect is None
                else dirty_rect.united(candidate)
            )
        if dirty_rect is None:
            return
        viewport_rect = self.view.mapFromScene(dirty_rect).boundingRect()
        self.view.viewport().update(viewport_rect.adjusted(-5, -5, 5, 5))

    def _clamp_to_editable_area(self, scene_pos: QPointF) -> QPointF:
        area = self.scene.editable_area_rect()
        return QPointF(
            max(area.left(), min(area.right(), scene_pos.x())),
            max(area.top(), min(area.bottom(), scene_pos.y())),
        )

    def begin_scenery_brush(self, scene_pos: QPointF):
        if not self.scenery_brush_active:
            return
        point = self._clamp_to_editable_area(scene_pos)
        self.scenery_brush_start = QPointF(point)
        self.scenery_brush_preview = QPointF(point)
        self._update_scenery_brush_overlay()

    def update_scenery_brush_preview(self, scene_pos: QPointF):
        if not self.scenery_brush_active or self.scenery_brush_start is None:
            return
        old_rect = self._scenery_brush_selection_rect()
        self.scenery_brush_preview = self._clamp_to_editable_area(scene_pos)
        self._update_scenery_brush_overlay(old_rect)

    def finish_scenery_brush(self, scene_pos: QPointF):
        if not self.scenery_brush_active or self.scenery_brush_start is None:
            return
        old_rect = self._scenery_brush_selection_rect()
        end = self._clamp_to_editable_area(scene_pos)
        target_rect = QRectF(self.scenery_brush_start, end).normalized()
        self.scenery_brush_start = None
        self.scenery_brush_preview = None
        self._update_scenery_brush_overlay(old_rect)

        if (
            target_rect.width() < PIXELS_PER_METER
            or target_rect.height() < PIXELS_PER_METER
        ):
            self.statusBar().showMessage(
                "Brush area is too small; drag at least 1 m in both directions.",
                3500,
            )
            self.view.viewport().update()
            return

        self.scenery_fill_settings_changed()
        self._begin_undo_transaction("Brush-fill scenery")
        created = self.scenery_filler.fill_editable_open_space(
            style=self.scenery_fill_style,
            density=self.scenery_fill_density,
            roadside_reserve_m=self.roadside_reserve_m,
            building_road_band_m=self.building_road_band_m,
            target_rect_scene=target_rect,
        )
        self.scene.clearSelection()
        self.scene.update()
        self.update_selection_info()
        self._commit_undo_transaction()
        if created:
            width_m = target_rect.width() / PIXELS_PER_METER
            height_m = target_rect.height() / PIXELS_PER_METER
            self.statusBar().showMessage(
                f"Generated {len(created)} scenery objects in the "
                f"{width_m:.1f} m × {height_m:.1f} m brush area. "
                "Drag another area or right-click to exit.",
                6500,
            )
        else:
            self.statusBar().showMessage(
                "No suitable space was found in that brush area. Try a larger area, "
                "Park style, or a smaller roadside reserve.",
                6500,
            )
        self.view.viewport().update()

    def insert_selected_continuous_road_node(self):
        road = self._single_selected_item()
        if not isinstance(road, ContinuousRoadItem):
            return
        points = list(road.points_m)
        segment_index = max(
            range(len(points) - 1),
            key=lambda index: math.hypot(
                points[index + 1][0] - points[index][0],
                points[index + 1][1] - points[index][1],
            ),
        )
        start = points[segment_index]
        end = points[segment_index + 1]
        midpoint = (
            (start[0] + end[0]) / 2.0,
            (start[1] + end[1]) / 2.0,
        )
        self._begin_undo_transaction("Insert continuous-road node")
        points.insert(segment_index + 1, midpoint)
        road.set_points_m(points)
        self.update_selection_info()
        self._commit_undo_transaction()

    def remove_selected_continuous_road_last_node(self):
        road = self._single_selected_item()
        if not isinstance(road, ContinuousRoadItem) or len(road.points_m) <= 2:
            return
        self._begin_undo_transaction("Remove continuous-road node")
        road.remove_node(len(road.points_m) - 1)
        self.update_selection_info()
        self._commit_undo_transaction()

    def reverse_selected_continuous_road(self):
        road = self._single_selected_item()
        if not isinstance(road, ContinuousRoadItem):
            return
        self._begin_undo_transaction("Reverse continuous road")
        road.set_points_m(list(reversed(road.points_m)))
        self.update_selection_info()
        self._commit_undo_transaction()


    def _refresh_reference_image_editor(
        self,
        item: TrackItem | None,
    ):
        supported = isinstance(item, ReferenceImageItem)
        self.reference_image_group.setVisible(supported)

        if not supported:
            return

        widgets = (
            self.prop_reference_width,
            self.prop_reference_height,
            self.prop_reference_opacity,
            self.prop_reference_lock_aspect,
            self.prop_reference_lock_position,
        )

        for widget in widgets:
            widget.blockSignals(True)

        try:
            self.prop_reference_file.setText(
                item.image_path or "Missing image"
            )
            self.prop_reference_width.setValue(
                float(item.width_m)
            )
            self.prop_reference_height.setValue(
                float(item.height_m)
            )
            self.prop_reference_opacity.setValue(
                float(item.image_opacity)
            )
            self.prop_reference_lock_aspect.setChecked(
                bool(item.lock_aspect_ratio)
            )
            self.prop_reference_lock_position.setChecked(
                bool(item.lock_position)
            )
        finally:
            for widget in widgets:
                widget.blockSignals(False)

    def apply_reference_image_size(
        self,
        changed_dimension: str,
        value: float,
    ):
        if self._property_refreshing:
            return

        item = self._reference_image_item()
        if item is None:
            return

        self._begin_undo_transaction(
            "Resize reference image"
        )

        width_m = float(item.width_m)
        height_m = float(item.height_m)
        aspect = max(item.native_aspect_ratio(), 1e-9)

        if changed_dimension == "width":
            width_m = float(value)
            if item.lock_aspect_ratio:
                height_m = width_m / aspect
        else:
            height_m = float(value)
            if item.lock_aspect_ratio:
                width_m = height_m * aspect

        item.set_dimensions_m(width_m, height_m)
        self.scene.update()
        self.update_selection_info()
        self._commit_undo_transaction()

    def apply_reference_image_opacity(self, value: float):
        item = self._reference_image_item()
        if item is None:
            return

        self._begin_undo_transaction(
            "Change reference image opacity"
        )
        item.image_opacity = max(
            0.05,
            min(1.0, float(value)),
        )
        item.update()
        self.scene.update()
        self.update_selection_info()
        self._commit_undo_transaction()

    def apply_reference_image_lock_aspect(self, checked: bool):
        item = self._reference_image_item()
        if item is None:
            return

        self._begin_undo_transaction(
            "Change reference image aspect lock"
        )
        item.lock_aspect_ratio = bool(checked)
        item.update()
        self._commit_undo_transaction()

    def apply_reference_image_lock_position(self, checked: bool):
        item = self._reference_image_item()
        if item is None:
            return

        self._begin_undo_transaction(
            "Change reference image lock"
        )
        item.set_position_locked(bool(checked))
        self.update_selection_info()
        self._commit_undo_transaction()


    def _refresh_road_markings_editor(self, item: TrackItem | None):
        supported = item is not None and item.supports_road_markings()
        self.markings_group.setVisible(supported)
        if not supported:
            return

        self._marking_refreshing = True
        widgets = (
            self.prop_marking_edge_a,
            self.prop_marking_edge_a_color,
            self.prop_marking_edge_a_style,
            self.prop_marking_center,
            self.prop_marking_center_color,
            self.prop_marking_center_style,
            self.prop_marking_edge_b,
            self.prop_marking_edge_b_color,
            self.prop_marking_edge_b_style,
            self.prop_marking_end_bar,
            self.prop_marking_end_bar_color,
            self.prop_marking_end_bar_style,
        )
        for widget in widgets:
            widget.blockSignals(True)

        def _set_combo(combo, value):
            index = combo.findData(value)
            combo.setCurrentIndex(index if index >= 0 else 0)

        try:
            self.prop_marking_edge_a.setChecked(bool(item.show_edge_a))
            _set_combo(self.prop_marking_edge_a_color, item.edge_a_marking_color)
            _set_combo(self.prop_marking_edge_a_style, item.edge_a_marking_style)

            self.prop_marking_center.setChecked(bool(item.show_center_line))
            _set_combo(self.prop_marking_center_color, item.center_marking_color)
            _set_combo(self.prop_marking_center_style, item.center_marking_style)

            self.prop_marking_edge_b.setChecked(bool(item.show_edge_b))
            _set_combo(self.prop_marking_edge_b_color, item.edge_b_marking_color)
            _set_combo(self.prop_marking_edge_b_style, item.edge_b_marking_style)

            self.prop_marking_end_bar.setChecked(bool(item.show_end_bar))
            _set_combo(self.prop_marking_end_bar_color, item.end_bar_marking_color)
            _set_combo(self.prop_marking_end_bar_style, item.end_bar_marking_style)

            road_end = isinstance(item, RoadEndItem)
            self.prop_marking_end_bar_row.setVisible(road_end)
            label = self.markings_group.layout().labelForField(
                self.prop_marking_end_bar_row
            )
            if label is not None:
                label.setVisible(road_end)
        finally:
            for widget in widgets:
                widget.blockSignals(False)
            self._marking_refreshing = False

    def apply_road_marking_properties(self, *args):
        if self._marking_refreshing:
            return
        item = self._single_selected_item()
        if item is None or not item.supports_road_markings():
            return

        self._begin_undo_transaction("Change road markings")
        item.show_edge_a = self.prop_marking_edge_a.isChecked()
        item.edge_a_marking_color = str(self.prop_marking_edge_a_color.currentData())
        item.edge_a_marking_style = str(self.prop_marking_edge_a_style.currentData())

        item.show_center_line = self.prop_marking_center.isChecked()
        item.center_marking_color = str(self.prop_marking_center_color.currentData())
        item.center_marking_style = str(self.prop_marking_center_style.currentData())

        item.show_edge_b = self.prop_marking_edge_b.isChecked()
        item.edge_b_marking_color = str(self.prop_marking_edge_b_color.currentData())
        item.edge_b_marking_style = str(self.prop_marking_edge_b_style.currentData())

        item.show_end_bar = self.prop_marking_end_bar.isChecked()
        item.end_bar_marking_color = str(self.prop_marking_end_bar_color.currentData())
        item.end_bar_marking_style = str(self.prop_marking_end_bar_style.currentData())

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
        if hasattr(item, "sync_resize_handle"):
            item.prepareGeometryChange()
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

        if hasattr(item, "sync_resize_handle"):
            item.sync_resize_handle()
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
        self.cancel_sketch_trim(silent=True)
        self.cancel_scenery_brush(silent=True)
        if self.continuous_road_drawing:
            self.finish_continuous_road_drawing()
        self.cancel_sketch_tool()
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

        if isinstance(item, ReferenceImageItem):
            return (
                "Editor-only tracing reference\n"
                "Not exported to QLabs\n"
                f"Width: {item.width_m:.2f} m\n"
                f"Height: {item.height_m:.2f} m\n"
                f"Angle: {normalize_angle(item.rotation()):.2f}°"
            )

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
                base_scale = effective_actor_scale * CROSSWALK_QLABS_BASE_SCALE
                lines.append(
                    "Crosswalk QLabs scale: "
                    f"X {base_scale * item.length_m / CROSSWALK_MARKER_LENGTH_M:.3f}, "
                    f"Y {base_scale * item.width_m / CROSSWALK_MARKER_WIDTH_M:.3f}"
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
        if not isinstance(
            item,
            (StraightRoadItem, RoadEndItem, MedianWallItem, CrosswalkItem),
        ):
            return
        self._begin_undo_transaction(
            "Resize crosswalk" if isinstance(item, CrosswalkItem) else "Resize road"
        )
        item.prepareGeometryChange()
        minimum_length = 0.25 if isinstance(item, CrosswalkItem) else 1.0
        item.length_m = max(minimum_length, float(value))
        if hasattr(item, "sync_resize_handle"):
            item.sync_resize_handle()
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
        if isinstance(item, MedianWallItem):
            minimum_width = 0.05
        elif isinstance(item, CrosswalkItem):
            minimum_width = 0.25
        else:
            minimum_width = 1.0
        item.width_m = max(minimum_width, float(value))

        # Curves require a positive inner radius.
        if isinstance(item, (Curve90RoadItem, Curve45RoadItem)):
            minimum_radius = item.width_m / 2.0 + 0.5
            if item.radius_m < minimum_radius:
                item.radius_m = minimum_radius
        elif isinstance(item, (TJunctionItem, CrossIntersectionItem)):
            item.arm_length_m = max(item.arm_length_m, item.width_m)

        if hasattr(item, "sync_resize_handle"):
            item.sync_resize_handle()

        self._geometry_property_changed(item)
        self._commit_undo_transaction()

    def apply_lane_count_property(self, value: int):
        if self._property_refreshing:
            return
        item = self._single_selected_item()
        if (
            item is None
            or not item.supports_road_markings()
            or bool(getattr(item, "auto_connector", False))
            or not hasattr(item, "width_m")
        ):
            return

        old_count = max(1, int(getattr(item, "lane_count", 2)))
        new_count = max(1, min(12, int(value)))
        if new_count == old_count:
            return

        # Lane count is the total across the whole road. Preserve the existing
        # lane width so adding lanes expands the carriageway predictably.
        lane_width_m = max(0.5, float(item.width_m) / float(old_count))
        self._begin_undo_transaction("Change road lane count")
        item.prepareGeometryChange()
        item.lane_count = new_count
        item.width_m = max(1.0, lane_width_m * new_count)

        if isinstance(item, (Curve90RoadItem, Curve45RoadItem)):
            item.radius_m = max(item.radius_m, item.width_m / 2.0 + 0.5)
        elif isinstance(item, (TJunctionItem, CrossIntersectionItem)):
            item.arm_length_m = max(item.arm_length_m, item.width_m)

        self.prop_width.blockSignals(True)
        self.prop_width.setValue(item.width_m)
        self.prop_width.blockSignals(False)
        if isinstance(item, (Curve90RoadItem, Curve45RoadItem)):
            self.prop_radius.blockSignals(True)
            self.prop_radius.setValue(item.radius_m)
            self.prop_radius.blockSignals(False)
        elif isinstance(item, (TJunctionItem, CrossIntersectionItem)):
            self.prop_arm.blockSignals(True)
            self.prop_arm.setValue(item.arm_length_m)
            self.prop_arm.blockSignals(False)

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
        if not isinstance(item, (Curve90RoadItem, Curve45RoadItem, SketchCircleItem)):
            return

        self._begin_undo_transaction("Change curve radius")
        item.prepareGeometryChange()
        minimum_radius = (
            item.width_m / 2.0 + 0.5
            if isinstance(item, (Curve90RoadItem, Curve45RoadItem))
            else 1.0
        )
        item.radius_m = max(minimum_radius, float(value))
        if isinstance(item, SketchCircleItem):
            item._sync_handle_positions([(QPointF(item.radius_px, 0.0), "radius")])
            self.sync_generated_road_from_guide(item)
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
            summary = selected[0].selection_text().splitlines()[0]
            self.selection_label.setText(summary)
            self._refresh_property_editor(selected[0])
            self._refresh_continuous_road_editor(selected[0])
            self._refresh_sketch_guide_editor(selected[0])
            self._refresh_camera_editor(selected[0])
            self._refresh_actor_editor(selected[0])
            self._refresh_experiment_editor(selected[0])
            self._refresh_guide_editor(selected[0])
            self._refresh_road_markings_editor(selected[0])
            self._refresh_reference_image_editor(selected[0])
        elif len(selected) > 1:
            self.selection_label.setText(f"{len(selected)} objects selected")
            self._refresh_property_editor(None)
            self._refresh_continuous_road_editor(None)
            self._refresh_sketch_guide_editor(None)
            self._refresh_camera_editor(None)
            self._refresh_actor_editor(None)
            self._refresh_experiment_editor(None)
            self._refresh_guide_editor(None)
            self._refresh_road_markings_editor(None)
            self._refresh_reference_image_editor(None)
        else:
            self.selection_label.setText("None")
            self._refresh_property_editor(None)
            self._refresh_continuous_road_editor(None)
            self._refresh_sketch_guide_editor(None)
            self._refresh_camera_editor(None)
            self._refresh_actor_editor(None)
            self._refresh_experiment_editor(None)
            self._refresh_guide_editor(None)
            self._refresh_road_markings_editor(None)
            self._refresh_reference_image_editor(None)

    def update_cursor_label(self, x_m: float, y_m: float):
        self.cursor_label.setText(f"Cursor: X {x_m:.1f} m | Y {y_m:.1f} m")

    def update_zoom_label(self):
        zoom_percent = self.view.transform().m11() * 100.0
        self.zoom_label.setText(f"Zoom: {zoom_percent:.0f}%")

    # ------------------------------------------------------------
    # QLabs export
    # ------------------------------------------------------------

    def export_qlabs_setup(self):
        self.cancel_sketch_trim(silent=True)
        self.cancel_scenery_brush(silent=True)
        self.cancel_sketch_tool()
        if self.continuous_road_drawing:
            self.finish_continuous_road_drawing()
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
            "The Open Road visual overlay remains editor-only; native Open Road exports now embed "
            "a compact measured XYZ elevation profile so all actors can follow local road height. "
            "Base Z remains an added per-actor offset, and Cover mode keeps its flat Top Z surface. "
            "The exported setup stays running while movement or trigger monitoring is required.",
        )

    # ------------------------------------------------------------
    # Save / load
    # ------------------------------------------------------------

    def track_data(self) -> dict:
        objects = [
            item.to_dict()
            for item in self.scene.track_items()
            if not bool(getattr(item, "auto_connector", False))
        ]

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
        self.cancel_sketch_trim(silent=True)
        self.cancel_scenery_brush(silent=True)
        self.cancel_sketch_tool()
        self.cancel_continuous_road_drawing()
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
        self.cancel_sketch_trim(silent=True)
        self.cancel_scenery_brush(silent=True)
        self.cancel_sketch_tool()
        if self.continuous_road_drawing:
            self.finish_continuous_road_drawing()
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

        self.cancel_sketch_trim(silent=True)
        self.cancel_scenery_brush(silent=True)
        self.cancel_sketch_tool()
        self.cancel_continuous_road_drawing()

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
                if (
                    obj.get("type") == ContinuousRoadItem.TYPE_NAME
                    and bool(obj.get("auto_connector", False))
                ):
                    continue
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
