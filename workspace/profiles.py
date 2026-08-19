"""QLabs Open World size profiles used by the workspace-cover platform.

World dimensions below are transcribed from the Quanser Interactive Labs API
workspace documentation.  The platform top-Z values are *editor defaults*, not
Quanser-published workspace heights; users can change them from the toolbar.
"""

WORKSPACE_PLATFORM_PROFILES = {
    "cityscape": {
        "label": "Cityscape",
        "module": "Cityscape",
        "size_x_m": 500.0,
        "size_y_m": 500.0,
        "center_x_m": 0.0,
        "center_y_m": 0.0,
        "default_bottom_z_m": -5.0,
        "default_top_z_m": 100.0,
        "default_spline_z_m": 1.0,
        "environment_support": "confirmed",
        "size_note": "Approx. 500 m × 500 m; origin centered in the world.",
    },
    "cityscape_lite": {
        "label": "Cityscape Lite",
        "module": "CityscapeLite",
        "size_x_m": 500.0,
        "size_y_m": 500.0,
        "center_x_m": 0.0,
        "center_y_m": 0.0,
        "default_bottom_z_m": -5.0,
        "default_top_z_m": 100.0,
        "default_spline_z_m": 1.0,
        "environment_support": "unknown",
        "size_note": "500 m × 500 m; origin centered in the world.",
    },
    "townscape": {
        "label": "Townscape",
        "module": "Townscape",
        "size_x_m": 500.0,
        "size_y_m": 500.0,
        "center_x_m": 0.0,
        "center_y_m": 0.0,
        "default_bottom_z_m": -5.0,
        "default_top_z_m": 100.0,
        "default_spline_z_m": 1.0,
        "environment_support": "unknown",
        "size_note": "Approx. 500 m × 500 m; origin centered in the world.",
    },
    "townscape_lite": {
        "label": "Townscape Lite",
        "module": "TownscapeLite",
        "size_x_m": 500.0,
        "size_y_m": 500.0,
        "center_x_m": 0.0,
        "center_y_m": 0.0,
        "default_bottom_z_m": -5.0,
        "default_top_z_m": 100.0,
        "default_spline_z_m": 1.0,
        "environment_support": "unknown",
        "size_note": "Approx. 500 m × 500 m; origin centered in the world.",
    },
    "open_road": {
        "label": "Open Road",
        "module": "OpenRoad",
        "size_x_m": 10000.0,
        "size_y_m": 5000.0,
        # For custom-track overlay work, centre the cover on the editor origin.
        # This makes the Open Road platform visually aligned with the canvas
        # and avoids the confusing south-edge offset used by the native map.
        "center_x_m": 0.0,
        "center_y_m": 0.0,
        "default_bottom_z_m": -10.0,
        "default_top_z_m": 250.0,
        "default_spline_z_m": 1.0,
        "environment_support": "confirmed",
        "size_note": "Approx. 10 km × 5 km; cover is centred on the editor canvas for custom-track placement.",
    },
    "plane": {
        "label": "Plane",
        "module": "Plane",
        "size_x_m": 20000.0,
        "size_y_m": 20000.0,
        "center_x_m": 0.0,
        "center_y_m": 0.0,
        "default_bottom_z_m": -2.0,
        "default_top_z_m": 1.0,
        "default_spline_z_m": 0.05,
        "environment_support": "unknown",
        "size_note": "20,000 m × 20,000 m; origin centered in the world.",
    },
    "studio": {
        "label": "Studio",
        "module": "Studio",
        "size_x_m": 15.0,
        "size_y_m": 14.0,
        "center_x_m": 0.0,
        "center_y_m": 0.0,
        "default_bottom_z_m": -1.0,
        "default_top_z_m": 3.0,
        "default_spline_z_m": 0.10,
        "environment_support": "indoor",
        "size_note": "15 m × 14 m indoor room; ceiling is 2.5 m.",
    },
    "warehouse": {
        "label": "Warehouse",
        "module": "Warehouse",
        "size_x_m": 50.0,
        "size_y_m": 30.0,
        "center_x_m": 0.0,
        "center_y_m": 0.0,
        "default_bottom_z_m": -1.0,
        "default_top_z_m": 7.0,
        "default_spline_z_m": 0.10,
        "environment_support": "indoor",
        "size_note": "50 m × 30 m indoor warehouse; ceiling is 5.5 m.",
    },
}

DEFAULT_WORKSPACE_PLATFORM_PROFILE = "plane"
DEFAULT_WORKSPACE_PLATFORM_COLOR_RGB = (54, 60, 66)


def workspace_platform_profile(key: str) -> dict:
    """Return a copy of a known workspace profile, falling back to Plane."""
    selected = WORKSPACE_PLATFORM_PROFILES.get(
        str(key), WORKSPACE_PLATFORM_PROFILES[DEFAULT_WORKSPACE_PLATFORM_PROFILE]
    )
    return dict(selected)


# Main Workspace selector modes map to the footprint/profile table above.
# ``custom`` is retained for backward compatibility and represents Plane.
WORKSPACE_MODE_TO_PROFILE = {
    "custom": "plane",
    "open_road": "open_road",
    "cityscape": "cityscape",
    "cityscape_lite": "cityscape_lite",
    "townscape": "townscape",
    "townscape_lite": "townscape_lite",
    "studio": "studio",
    "warehouse": "warehouse",
}


def workspace_profile_key_for_mode(mode: str) -> str:
    """Return the workspace profile key associated with an editor mode."""
    return WORKSPACE_MODE_TO_PROFILE.get(str(mode), "plane")


def workspace_mode_profile(mode: str) -> dict:
    """Return a profile copy for the selected main workspace mode."""
    return workspace_platform_profile(workspace_profile_key_for_mode(mode))


def workspace_mode_label(mode: str) -> str:
    """Return the QLabs-facing label for an editor workspace mode."""
    return str(workspace_mode_profile(mode).get("label", "Plane"))


def workspace_mode_default_spline_z(mode: str) -> float:
    """Safe default Z for spline roads/markings on the native workspace."""
    return float(workspace_mode_profile(mode).get("default_spline_z_m", 0.05))
