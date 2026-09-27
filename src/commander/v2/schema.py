"""Web-state allowlists shared by the projections and the browser schema.

``tools/gen_web_schema.py`` renders these tuples into the generated block of
``data/commander/js/state/schema.js`` (``--check`` in CI); the projections
import the row field tuples from here so Python and JavaScript cannot drift.
"""

from src.commander.v2.wire import OPFOR_ROLES

TACTICAL_FIELDS = ("ref", "label", "domain", "source", "affiliation",
                   "bearing", "range_nm", "x", "y", "course", "speed_kn",
                   "altitude_m", "observer_x", "observer_y", "quality",
                   "age_s", "bearing_uncertainty_deg", "range_uncertainty_nm",
                   "visual_class", "visual_type")
SONAR_FIELDS = ("ref", "label", "source", "classification", "profile", "bearing",
                "range_nm", "x", "y", "depth_m", "course", "speed_kn",
                "quality", "age_s", "fix_age_s", "bearing_uncertainty_deg",
                "range_uncertainty_nm", "observer_x", "observer_y",
                "released_to_opz", "fixes")
RADIO_FIELDS = ("ref", "label", "bearing", "quality", "age_s",
                "bearing_uncertainty_deg")
HELICOPTER_TACTICAL_FIELDS = TACTICAL_FIELDS + ("classification", "released_to_opz")

_UBOOT_COMMAND_SHAPE = ("navigation", "status", "weapons", "alarms", "contacts",
                        "own_weapons", "designated_target_ref", "feed", "scope")
# Top-level keys of every role payload (exact sets on both sides).
ROLE_SHAPES = {
    "bridge": ("navigation", "orders", "threat", "systems", "tactical_summary", "sightings"),
    "sonar": ("observations", "settings", "visualization"),
    "weapons": ("inventory", "readiness", "designated_target", "navigation", "tactical",
                "target_choices", "depth_m", "tubes", "settings", "own_weapons",
                "active_assets"),
    "damage": ("compartments", "teams", "total", "sunk", "stability"),
    "opz": ("observations", "fusions", "radar", "defense", "asm_observations",
            "source_classifications", "radar_blips", "designated_target_ref", "own_assets"),
    "radio": ("observations", "logged_fixes", "logged_bearings", "messages", "station_down",
              "navigation", "tactical"),
    "engine": ("propulsion", "machinery", "controls", "environment_effects"),
    "helicopter": ("asset", "waypoint", "buoys", "buoy_observations", "acoustic",
                   "navigation", "tactical", "target_choices", "readiness",
                   "dip_observations", "dip_environment"),
    "eloka": ("intercepts", "station_down", "status", "hardware"),
    **{role: _UBOOT_COMMAND_SHAPE for role in OPFOR_ROLES if role != "uboot_sonar"},
    "uboot_sonar": ("observations", "settings", "visualization"),
}
