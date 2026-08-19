"""Compact top control bar for the QLabs Track Editor.

This replaces the wide left-hand palette. Project/workspace/environment
settings live in a compact first row. Object creation and editing actions use
symbol buttons in the second row; full names remain available as tooltips.
"""

from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from config import (
    PROJECT_SCALES,
    WEATHER_PRESETS,
    WORKSPACE_CUSTOM,
    WORKSPACE_OPEN_ROAD,
    WORKSPACE_CITYSCAPE,
    WORKSPACE_CITYSCAPE_LITE,
    WORKSPACE_TOWNSCAPE,
    WORKSPACE_TOWNSCAPE_LITE,
    WORKSPACE_STUDIO,
    WORKSPACE_WAREHOUSE,
    ENDPOINT_SNAP_DISTANCE_M,
    DEFAULT_CANVAS_WIDTH_M,
    DEFAULT_CANVAS_HEIGHT_M,
    MIN_CANVAS_SIZE_M,
    MAX_CANVAS_SIZE_M,
    DEFAULT_ROADSIDE_RESERVE_M,
    DEFAULT_BUILDING_ROAD_BAND_M,
    DEFAULT_SCENERY_FILL_STYLE,
    DEFAULT_SCENERY_FILL_DENSITY,
)
from ui.icons import make_tool_icon
from core.traffic_sign_catalog import TRAFFIC_SIGN_CATALOG
from workspace.profiles import (
    DEFAULT_WORKSPACE_PLATFORM_PROFILE,
    WORKSPACE_PLATFORM_PROFILES,
    workspace_mode_default_spline_z,
)

class TimeOfDaySpinBox(QDoubleSpinBox):
    """Decimal-hour spin box displayed as a familiar HH:MM clock time."""

    def textFromValue(self, value: float) -> str:
        total_minutes = int(round(float(value) * 60.0))
        total_minutes = max(0, min(24 * 60, total_minutes))
        hours, minutes = divmod(total_minutes, 60)
        return f"{hours:02d}:{minutes:02d}"

    def valueFromText(self, text: str) -> float:
        cleaned = text.strip()
        if ":" in cleaned:
            try:
                hours_text, minutes_text = cleaned.split(":", 1)
                hours = int(hours_text)
                minutes = int(minutes_text)
                hours = max(0, min(24, hours))
                minutes = max(0, min(59, minutes))
                if hours == 24:
                    minutes = 0
                return hours + minutes / 60.0
            except ValueError:
                pass
        return super().valueFromText(text)


class TopControlBar(QWidget):
    """Compact top bar with settings, tools, and scenery galleries."""

    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self.setObjectName("topControlBar")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        self.setStyleSheet(
            "#topControlBar {"
            "background: #202327;"
            "border: 1px solid #383d43;"
            "border-radius: 6px;"
            "}"
            "QToolButton {"
            "background: #2a2e33;"
            "border: 1px solid #41464d;"
            "border-radius: 5px;"
            "padding: 3px;"
            "}"
            "QToolButton:hover { background: #343a40; border-color: #5a626b; }"
            "QToolButton:pressed { background: #1f6f9d; }"
            "QToolButton:checked { background: #235d78; border-color: #4eb2e8; }"
            "QLabel#toolCategory { color: #aeb6bf; font-size: 10px; font-weight: 600; }"
        )

        root = QVBoxLayout(self)
        root.setContentsMargins(8, 6, 8, 6)
        root.setSpacing(5)

        self.settings_row = QHBoxLayout()
        self.settings_row.setSpacing(7)
        root.addLayout(self.settings_row)

        self.tools_row = QHBoxLayout()
        self.tools_row.setSpacing(4)
        root.addLayout(self.tools_row)

        self.gallery_row = QHBoxLayout()
        self.gallery_row.setSpacing(4)
        root.addLayout(self.gallery_row)

        self.platform_row = QHBoxLayout()
        self.platform_row.setSpacing(6)
        root.addLayout(self.platform_row)

        self._build_settings_row()
        self._build_tools_row()
        self._build_gallery_row()
        self._build_platform_row()
        self._expose_controls_to_window()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _separator() -> QFrame:
        line = QFrame()
        line.setFrameShape(QFrame.Shape.VLine)
        line.setFrameShadow(QFrame.Shadow.Sunken)
        line.setFixedHeight(28)
        return line

    @staticmethod
    def _category(text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("toolCategory")
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setMinimumWidth(38)
        return label

    def _icon_button(
        self,
        kind: str,
        tooltip: str,
        callback,
        *,
        checkable: bool = False,
        checked: bool = False,
    ) -> QToolButton:
        button = QToolButton()
        button.setIcon(make_tool_icon(kind, 30))
        button.setIconSize(QSize(26, 26))
        button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        button.setFixedSize(36, 34)
        button.setToolTip(tooltip)
        button.setCheckable(checkable)
        if checkable:
            button.setChecked(checked)
            button.toggled.connect(callback)
        else:
            button.clicked.connect(callback)
        return button

    # ------------------------------------------------------------------
    # Settings row
    # ------------------------------------------------------------------

    def _build_settings_row(self):
        row = self.settings_row

        # Project scale
        row.addWidget(QLabel("Scale"))
        self.project_scale_combo = QComboBox()
        self.project_scale_combo.setMinimumWidth(82)
        for name, factor in PROJECT_SCALES:
            self.project_scale_combo.addItem(name, factor)
        self.project_scale_combo.addItem("Custom", None)
        self.project_scale_combo.currentIndexChanged.connect(
            self.window.project_scale_changed
        )
        row.addWidget(self.project_scale_combo)

        self.custom_scale_label = QLabel("1 :")
        self.custom_scale_denominator = self.window._make_spinbox(
            1.0, 1000.0, 1.0, 2
        )
        self.custom_scale_denominator.setFixedWidth(78)
        self.custom_scale_denominator.setValue(10.0)
        self.custom_scale_denominator.valueChanged.connect(
            self.window.custom_scale_changed
        )
        self.custom_scale_label.setVisible(False)
        self.custom_scale_denominator.setVisible(False)
        row.addWidget(self.custom_scale_label)
        row.addWidget(self.custom_scale_denominator)

        self.scale_preview_label = QLabel("6.00 m → 6.00 m")
        self.scale_preview_label.setToolTip(
            "Design dimensions remain in full-scale meters; this preview shows the effective QLabs scale."
        )
        row.addWidget(self.scale_preview_label)

        row.addWidget(self._separator())

        # Editable canvas. The rectangle is centered on world origin and acts
        # as the real design boundary for manual editing and scenery fill.
        row.addWidget(QLabel("Canvas"))
        row.addWidget(QLabel("W"))
        self.canvas_width_spin = self.window._make_spinbox(
            MIN_CANVAS_SIZE_M, MAX_CANVAS_SIZE_M, 10.0, 0, " m"
        )
        self.canvas_width_spin.setFixedWidth(86)
        self.canvas_width_spin.setValue(DEFAULT_CANVAS_WIDTH_M)
        self.canvas_width_spin.setToolTip("Editable canvas width")
        self.canvas_width_spin.valueChanged.connect(self.window.canvas_area_changed)
        row.addWidget(self.canvas_width_spin)

        row.addWidget(QLabel("H"))
        self.canvas_height_spin = self.window._make_spinbox(
            MIN_CANVAS_SIZE_M, MAX_CANVAS_SIZE_M, 10.0, 0, " m"
        )
        self.canvas_height_spin.setFixedWidth(86)
        self.canvas_height_spin.setValue(DEFAULT_CANVAS_HEIGHT_M)
        self.canvas_height_spin.setToolTip("Editable canvas height")
        self.canvas_height_spin.valueChanged.connect(self.window.canvas_area_changed)
        row.addWidget(self.canvas_height_spin)

        self.fit_canvas_button = self._icon_button(
            "fit",
            "Fit editable canvas area to the view",
            self.window.fit_editable_area,
        )
        self.fit_canvas_button.setFixedSize(30, 28)
        row.addWidget(self.fit_canvas_button)

        row.addWidget(self._separator())

        # Workspace
        row.addWidget(QLabel("Workspace"))
        self.workspace_mode_combo = QComboBox()
        self.workspace_mode_combo.setMinimumWidth(146)
        self.workspace_mode_combo.addItem("Plane / Custom", WORKSPACE_CUSTOM)
        self.workspace_mode_combo.addItem("Open Road", WORKSPACE_OPEN_ROAD)
        self.workspace_mode_combo.addItem("Cityscape", WORKSPACE_CITYSCAPE)
        self.workspace_mode_combo.addItem("Cityscape Lite", WORKSPACE_CITYSCAPE_LITE)
        self.workspace_mode_combo.addItem("Townscape", WORKSPACE_TOWNSCAPE)
        self.workspace_mode_combo.addItem("Townscape Lite", WORKSPACE_TOWNSCAPE_LITE)
        self.workspace_mode_combo.addItem("Studio", WORKSPACE_STUDIO)
        self.workspace_mode_combo.addItem("Warehouse", WORKSPACE_WAREHOUSE)
        self.workspace_mode_combo.setToolTip(
            "QLabs workspace used by the exported setup. Open Road also has a "
            "2-D editor reference overlay."
        )
        self.workspace_mode_combo.currentIndexChanged.connect(
            self.window.workspace_mode_changed
        )
        row.addWidget(self.workspace_mode_combo)

        row.addWidget(QLabel("Spline Z"))
        self.workspace_spline_z_spin = self.window._make_spinbox(
            -20.0, 1000.0, 0.05, 2, " m"
        )
        self.workspace_spline_z_spin.setFixedWidth(82)
        self.workspace_spline_z_spin.setValue(
            workspace_mode_default_spline_z(WORKSPACE_CUSTOM)
        )
        self.workspace_spline_z_spin.setToolTip(
            "Native-workspace Z height for exported spline roads and guide lines. "
            "Spline roads default to 1.20 m so they remain above native road surfaces. "
            "When Workspace box is enabled, the box Top Z is used instead."
        )
        self.workspace_spline_z_spin.valueChanged.connect(
            self.window.workspace_spline_z_changed
        )
        row.addWidget(self.workspace_spline_z_spin)

        # Overlay toggles are compact symbols. Tooltips hold the long labels.
        self.workspace_show_road_checkbox = QToolButton()
        self.workspace_show_road_checkbox.setText("≋")
        self.workspace_show_road_checkbox.setToolTip("Show Open Road road reference")
        self.workspace_show_road_checkbox.setCheckable(True)
        self.workspace_show_road_checkbox.setChecked(True)
        self.workspace_show_road_checkbox.setFixedSize(30, 28)
        self.workspace_show_road_checkbox.toggled.connect(
            self.window.workspace_display_changed
        )
        row.addWidget(self.workspace_show_road_checkbox)

        self.workspace_show_nav_checkbox = QToolButton()
        self.workspace_show_nav_checkbox.setText("▧")
        self.workspace_show_nav_checkbox.setToolTip("Show Open Road navigation regions")
        self.workspace_show_nav_checkbox.setCheckable(True)
        self.workspace_show_nav_checkbox.setChecked(True)
        self.workspace_show_nav_checkbox.setFixedSize(30, 28)
        self.workspace_show_nav_checkbox.toggled.connect(
            self.window.workspace_display_changed
        )
        row.addWidget(self.workspace_show_nav_checkbox)

        self.workspace_show_points_checkbox = QToolButton()
        self.workspace_show_points_checkbox.setText("●")
        self.workspace_show_points_checkbox.setToolTip("Show published Open Road reference points")
        self.workspace_show_points_checkbox.setCheckable(True)
        self.workspace_show_points_checkbox.setChecked(True)
        self.workspace_show_points_checkbox.setFixedSize(30, 28)
        self.workspace_show_points_checkbox.toggled.connect(
            self.window.workspace_display_changed
        )
        row.addWidget(self.workspace_show_points_checkbox)

        self.workspace_show_labels_checkbox = QToolButton()
        self.workspace_show_labels_checkbox.setText("A")
        self.workspace_show_labels_checkbox.setToolTip("Show Open Road reference labels")
        self.workspace_show_labels_checkbox.setCheckable(True)
        self.workspace_show_labels_checkbox.setChecked(True)
        self.workspace_show_labels_checkbox.setFixedSize(30, 28)
        self.workspace_show_labels_checkbox.toggled.connect(
            self.window.workspace_display_changed
        )
        row.addWidget(self.workspace_show_labels_checkbox)

        self.fit_workspace_button = self._icon_button(
            "fit",
            "Fit selected workspace/reference to the view",
            self.window.fit_open_road_reference,
        )
        self.fit_workspace_button.setFixedSize(30, 28)
        row.addWidget(self.fit_workspace_button)

        row.addWidget(self._separator())

        # Outdoor environment
        # Keep the control compact, but make its meaning obvious at a glance:
        #     ☀ Environment    Clear skies    🕒 12:00
        self.environment_enabled_checkbox = QCheckBox("☀ Environment")
        self.environment_enabled_checkbox.setToolTip(
            "Apply outdoor environment settings on export"
        )
        self.environment_enabled_checkbox.setChecked(True)
        self.environment_enabled_checkbox.toggled.connect(
            self.window.environment_settings_changed
        )
        row.addWidget(self.environment_enabled_checkbox)

        self.weather_combo = QComboBox()
        self.weather_combo.setMinimumWidth(112)
        for label, value in WEATHER_PRESETS:
            self.weather_combo.addItem(label, value)
        self.weather_combo.currentIndexChanged.connect(
            self.window.environment_settings_changed
        )
        row.addWidget(self.weather_combo)

        time_icon = QLabel("🕒")
        time_icon.setToolTip("QLabs time of day")
        row.addWidget(time_icon)

        self.time_of_day_spin = TimeOfDaySpinBox()
        self.time_of_day_spin.setRange(0.0, 24.0)
        self.time_of_day_spin.setSingleStep(0.5)
        self.time_of_day_spin.setDecimals(2)
        self.time_of_day_spin.setKeyboardTracking(False)
        self.time_of_day_spin.setFixedWidth(82)
        self.time_of_day_spin.setValue(12.0)
        self.time_of_day_spin.setToolTip(
            "QLabs time of day (HH:MM; 0.5-hour steps)"
        )
        self.time_of_day_spin.valueChanged.connect(
            self.window.environment_settings_changed
        )
        row.addWidget(self.time_of_day_spin)

        row.addStretch(1)

        # Hidden compatibility labels: existing window logic updates these.
        self.scale_help_label = QLabel()
        self.scale_help_label.hide()
        self.workspace_reference_note = QLabel()
        self.workspace_reference_note.hide()
        self.help_label = QLabel()
        self.help_label.hide()

    # ------------------------------------------------------------------
    # Tool row
    # ------------------------------------------------------------------

    def _build_tools_row(self):
        row = self.tools_row

        row.addWidget(self._category("ROAD"))
        row.addWidget(self._icon_button("straight", "Straight Road", self.window.add_straight_road))
        row.addWidget(self._icon_button("curve45", "45° Curve", self.window.add_curve_45))
        row.addWidget(self._icon_button("curve90", "90° Curve", self.window.add_curve_90))
        row.addWidget(self._icon_button("tjunction", "T-Junction", self.window.add_t_junction))
        row.addWidget(self._icon_button("intersection", "4-Way Intersection", self.window.add_cross_intersection))
        row.addWidget(self._icon_button("road_end", "Road End", self.window.add_road_end))
        row.addWidget(self._icon_button("wall", "Median / Barrier Wall", self.window.add_median_wall))

        row.addWidget(self._separator())
        row.addWidget(self._category("TRACE"))
        row.addWidget(
            self._icon_button(
                "reference_image",
                "Import image reference for manual tracing",
                self.window.add_reference_image,
            )
        )

        row.addWidget(self._separator())
        row.addWidget(self._category("TRAFFIC"))
        row.addWidget(self._icon_button("traffic_light", "Traffic Light", self.window.add_traffic_light))
        row.addWidget(self._icon_button("stop", "Stop Sign", self.window.add_stop_sign))
        row.addWidget(self._icon_button("yield", "Yield Sign", self.window.add_yield_sign))
        row.addWidget(self._icon_button("roundabout", "Roundabout Sign", self.window.add_roundabout_sign))

        self.catalog_sign_combo = QComboBox()
        self.catalog_sign_combo.setFixedWidth(132)
        self.catalog_sign_combo.setToolTip("Validated custom traffic sign to add")
        for sign_key, sign_label, _family, _short in TRAFFIC_SIGN_CATALOG:
            self.catalog_sign_combo.addItem(sign_label, sign_key)
        row.addWidget(self.catalog_sign_combo)

        row.addWidget(self._icon_button(
            "traffic_sign_catalog",
            "Add selected validated custom traffic sign",
            self.window.add_catalog_traffic_sign,
        ))
        row.addWidget(self._icon_button("crosswalk", "Crosswalk", self.window.add_crosswalk))

        row.addWidget(self._separator())
        row.addWidget(self._category("EXP"))
        row.addWidget(self._icon_button("person", "Pedestrian", self.window.add_person))
        row.addWidget(self._icon_button("animal", "Animal", self.window.add_animal))
        row.addWidget(self._icon_button("trigger", "QCar Trigger Zone", self.window.add_trigger_zone))

        row.addWidget(self._separator())
        row.addWidget(self._category("QCAR"))
        row.addWidget(self._icon_button("qcar_start", "QCar2 Start", self.window.add_qcar2_start))
        row.addWidget(self._icon_button("qcar_env", "Environment QCar2", self.window.add_secondary_qcar))

        row.addWidget(self._separator())
        row.addWidget(self._category("EDIT"))

        self.undo_button = self._icon_button(
            "undo", "Undo last edit (Ctrl+Z)", self.window.undo_last_action
        )
        self.undo_button.setEnabled(False)
        row.addWidget(self.undo_button)

        self.duplicate_button = self._icon_button(
            "duplicate", "Duplicate selected (Ctrl+D)", self.window.duplicate_selected
        )
        row.addWidget(self.duplicate_button)

        self.rotate_btn = self._icon_button(
            "rotate", "Rotate selected +15° (R)", lambda: self.window.rotate_selected(self.window.rotation_step_deg)
        )
        row.addWidget(self.rotate_btn)

        self.rotation_step_combo = QComboBox()
        self.rotation_step_combo.setFixedWidth(62)
        for step in (0.5, 1, 5, 15, 30, 45, 90):
            self.rotation_step_combo.addItem(f"{step}°", float(step))
        self.rotation_step_combo.setCurrentText("15°")
        self.rotation_step_combo.setToolTip("Rotation step. Exact angles can also be typed in the Properties panel.")
        self.rotation_step_combo.currentIndexChanged.connect(
            self.window.rotation_step_changed
        )
        row.addWidget(self.rotation_step_combo)

        self.delete_button = self._icon_button(
            "delete", "Delete selected (Delete)", self.window.delete_selected
        )
        row.addWidget(self.delete_button)

        self.endpoint_snap_checkbox = self._icon_button(
            "snap",
            f"Endpoint + median-wall snapping ({ENDPOINT_SNAP_DISTANCE_M:g} m)",
            self.window.set_endpoint_snap_enabled,
            checkable=True,
            checked=True,
        )
        row.addWidget(self.endpoint_snap_checkbox)

        self.export_button = self._icon_button(
            "export", "Export QLabs Setup...", self.window.export_qlabs_setup
        )
        row.addWidget(self.export_button)

        row.addStretch(1)

    # ------------------------------------------------------------------
    # Building + park gallery row
    # ------------------------------------------------------------------

    def _build_gallery_row(self):
        row = self.gallery_row

        row.addWidget(self._category("BUILD"))
        row.addWidget(self._icon_button("building", "Simple Building / Box", self.window.add_building_box))
        row.addWidget(self._icon_button("office", "Office Building", self.window.add_office_building))
        row.addWidget(self._icon_button("apartment", "Apartment Building", self.window.add_apartment_building))
        row.addWidget(self._icon_button("shop", "Commercial Shop", self.window.add_shop_building))
        row.addWidget(self._icon_button("tower", "Stepped Tower", self.window.add_stepped_tower))

        row.addWidget(self._separator())
        row.addWidget(self._category("PARK"))
        row.addWidget(self._icon_button("tree", "Round Tree", self.window.add_round_tree))
        row.addWidget(self._icon_button("pine", "Pine Tree", self.window.add_pine_tree))
        row.addWidget(self._icon_button("bench", "Park Bench", self.window.add_park_bench))
        row.addWidget(self._icon_button("lamp", "Lamp Post", self.window.add_lamp_post))
        row.addWidget(self._icon_button("bin", "Trash Bin", self.window.add_trash_bin))
        row.addWidget(self._icon_button("planter", "Planter", self.window.add_planter))
        row.addWidget(self._icon_button("fountain", "Fountain", self.window.add_fountain))

        row.addWidget(self._separator())
        row.addWidget(self._category("FILL"))

        self.fill_style_combo = QComboBox()
        self.fill_style_combo.setFixedWidth(92)
        self.fill_style_combo.addItem("Urban", "urban")
        self.fill_style_combo.addItem("Suburban", "suburban")
        self.fill_style_combo.addItem("Park", "park")
        style_index = self.fill_style_combo.findData(DEFAULT_SCENERY_FILL_STYLE)
        self.fill_style_combo.setCurrentIndex(max(0, style_index))
        self.fill_style_combo.setToolTip("Scenery fill style")
        self.fill_style_combo.currentIndexChanged.connect(
            self.window.scenery_fill_settings_changed
        )
        row.addWidget(self.fill_style_combo)

        self.fill_density_combo = QComboBox()
        self.fill_density_combo.setFixedWidth(82)
        self.fill_density_combo.addItem("Low", "low")
        self.fill_density_combo.addItem("Medium", "medium")
        self.fill_density_combo.addItem("High", "high")
        density_index = self.fill_density_combo.findData(DEFAULT_SCENERY_FILL_DENSITY)
        self.fill_density_combo.setCurrentIndex(max(0, density_index))
        self.fill_density_combo.setToolTip("Scenery fill density")
        self.fill_density_combo.currentIndexChanged.connect(
            self.window.scenery_fill_settings_changed
        )
        row.addWidget(self.fill_density_combo)

        self.roadside_reserve_spin = self.window._make_spinbox(
            0.0, 30.0, 0.5, 1, " m"
        )
        self.roadside_reserve_spin.setFixedWidth(82)
        self.roadside_reserve_spin.setValue(DEFAULT_ROADSIDE_RESERVE_M)
        self.roadside_reserve_spin.setToolTip(
            "Clear roadside reserve beyond the road edge for signs and manually placed roadside objects"
        )
        self.roadside_reserve_spin.valueChanged.connect(
            self.window.scenery_fill_settings_changed
        )
        row.addWidget(self.roadside_reserve_spin)

        row.addWidget(QLabel("Bldg"))
        self.building_road_band_spin = self.window._make_spinbox(
            3.0, 80.0, 1.0, 1, " m"
        )
        self.building_road_band_spin.setFixedWidth(82)
        self.building_road_band_spin.setValue(DEFAULT_BUILDING_ROAD_BAND_M)
        self.building_road_band_spin.setToolTip(
            "Maximum distance from a road edge where auto-filled buildings may be placed"
        )
        self.building_road_band_spin.valueChanged.connect(
            self.window.scenery_fill_settings_changed
        )
        row.addWidget(self.building_road_band_spin)

        self.auto_fill_button = self._icon_button(
            "autofill",
            "Fill the editable canvas with static buildings/park scenery while preserving the roadside reserve",
            self.window.auto_fill_open_space,
        )
        row.addWidget(self.auto_fill_button)

        row.addStretch(1)


    # ------------------------------------------------------------------
    # Workspace cover / weather platform row
    # ------------------------------------------------------------------

    def _build_platform_row(self):
        row = self.platform_row

        row.addWidget(self._category("COVER"))

        self.workspace_platform_enabled_checkbox = QCheckBox("Workspace box")
        self.workspace_platform_enabled_checkbox.setToolTip(
            "Spawn a static BasicShape box over the selected QLabs workspace and "
            "raise the exported track to the box top surface"
        )
        self.workspace_platform_enabled_checkbox.setChecked(False)
        self.workspace_platform_enabled_checkbox.toggled.connect(
            self.window.workspace_platform_settings_changed
        )
        row.addWidget(self.workspace_platform_enabled_checkbox)

        self.workspace_platform_profile_combo = QComboBox()
        self.workspace_platform_profile_combo.setMinimumWidth(168)
        for key, profile in WORKSPACE_PLATFORM_PROFILES.items():
            sx = profile["size_x_m"]
            sy = profile["size_y_m"]
            if max(sx, sy) >= 1000.0:
                size_text = f"{sx/1000:g}×{sy/1000:g} km"
            else:
                size_text = f"{sx:g}×{sy:g} m"
            self.workspace_platform_profile_combo.addItem(
                f"{profile['label']}  {size_text}", key
            )
        profile_index = self.workspace_platform_profile_combo.findData(
            DEFAULT_WORKSPACE_PLATFORM_PROFILE
        )
        self.workspace_platform_profile_combo.setCurrentIndex(max(0, profile_index))
        self.workspace_platform_profile_combo.setToolTip(
            "QLabs workspace footprint used for the cover box"
        )
        self.workspace_platform_profile_combo.currentIndexChanged.connect(
            self.window.workspace_platform_profile_changed
        )
        row.addWidget(self.workspace_platform_profile_combo)

        row.addWidget(QLabel("Top Z"))
        self.workspace_platform_top_z_spin = self.window._make_spinbox(
            0.05, 1000.0, 5.0, 1, " m"
        )
        self.workspace_platform_top_z_spin.setFixedWidth(88)
        default_profile = WORKSPACE_PLATFORM_PROFILES[DEFAULT_WORKSPACE_PLATFORM_PROFILE]
        self.workspace_platform_top_z_spin.setValue(
            float(default_profile["default_top_z_m"])
        )
        self.workspace_platform_top_z_spin.setToolTip(
            "Top surface height of the workspace cover. All exported roads and "
            "actors are raised by this amount. Raise it if native workspace "
            "geometry protrudes through the platform."
        )
        self.workspace_platform_top_z_spin.valueChanged.connect(
            self.window.workspace_platform_settings_changed
        )
        row.addWidget(self.workspace_platform_top_z_spin)

        row.addWidget(QLabel("Bottom Z"))
        self.workspace_platform_bottom_z_spin = self.window._make_spinbox(
            -1000.0, 999.0, 5.0, 1, " m"
        )
        self.workspace_platform_bottom_z_spin.setFixedWidth(88)
        self.workspace_platform_bottom_z_spin.setValue(
            float(default_profile["default_bottom_z_m"])
        )
        self.workspace_platform_bottom_z_spin.setToolTip(
            "Bottom of the cover box; must remain below Top Z"
        )
        self.workspace_platform_bottom_z_spin.valueChanged.connect(
            self.window.workspace_platform_settings_changed
        )
        row.addWidget(self.workspace_platform_bottom_z_spin)

        self.fit_workspace_platform_button = self._icon_button(
            "fit",
            "Fit the selected workspace cover footprint to the editor view",
            self.window.fit_workspace_platform,
        )
        self.fit_workspace_platform_button.setFixedSize(30, 28)
        row.addWidget(self.fit_workspace_platform_button)

        self.workspace_platform_info_label = QLabel()
        self.workspace_platform_info_label.setObjectName("toolCategory")
        self.workspace_platform_info_label.setToolTip(
            "Published QLabs world size. Platform Top Z is an editor setting, not a published world height."
        )
        row.addWidget(self.workspace_platform_info_label)

        row.addStretch(1)

    # ------------------------------------------------------------------
    # Compatibility aliases
    # ------------------------------------------------------------------

    def _expose_controls_to_window(self):
        """Keep the existing main-window methods unchanged during the UI refactor."""
        names = (
            "project_scale_combo",
            "custom_scale_label",
            "custom_scale_denominator",
            "scale_preview_label",
            "scale_help_label",
            "canvas_width_spin",
            "canvas_height_spin",
            "fit_canvas_button",
            "workspace_mode_combo",
            "workspace_spline_z_spin",
            "workspace_show_road_checkbox",
            "workspace_show_nav_checkbox",
            "workspace_show_points_checkbox",
            "workspace_show_labels_checkbox",
            "fit_workspace_button",
            "workspace_reference_note",
            "environment_enabled_checkbox",
            "weather_combo",
            "time_of_day_spin",
            "endpoint_snap_checkbox",
            "rotation_step_combo",
            "rotate_btn",
            "fill_style_combo",
            "fill_density_combo",
            "roadside_reserve_spin",
            "building_road_band_spin",
            "workspace_platform_enabled_checkbox",
            "workspace_platform_profile_combo",
            "workspace_platform_top_z_spin",
            "workspace_platform_bottom_z_spin",
            "fit_workspace_platform_button",
            "workspace_platform_info_label",
            "undo_button",
            "help_label",
        )
        for name in names:
            setattr(self.window, name, getattr(self, name))
