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

# The common ``weather_station`` block: own-ship atmosphere (every role) and
# the crewed boat's weather block (submarine roles instead of flight weather,
# whose atmosphere omits the flying-only cloud ceiling and icing).
WEATHER_ATMOSPHERE_FIELDS = (
    "weather", "precipitation", "rain_intensity", "visibility_nm", "sea_state",
    "wind_from_deg", "wind_kn", "gust_kn", "beaufort", "pressure_hpa",
    "pressure_tendency_hpa_3h", "pressure_trend", "storm_warning", "air_temp_c",
    "sea_temp_c", "cloud_cover", "ceiling_ft", "icing", "sun_elevation_deg",
    "daylight", "moon_phase", "moon_illumination", "time")
WEATHER_BOAT_ATMOSPHERE_FIELDS = tuple(
    key for key in WEATHER_ATMOSPHERE_FIELDS if key not in ("ceiling_ft", "icing"))
WEATHER_BOAT_FIELDS = (
    "mast_radar_nm", "mast_radar_calm_nm", "sighting_nm", "sighting_ref_nm",
    "ambient_bands_hz", "ambient_excess_db", "snorkel_available", "snorkeling",
    "snorkel_max_kn", "snorkel_noise_db", "snorkel_lines_hz")

_UBOOT_COMMAND_SHAPE = ("navigation", "status", "weapons", "alarms", "contacts",
                        "own_weapons", "designated_target_ref", "feed", "scope", "plant")
# The boat's plant and stores (``plant``): numbers, then the air block.
UBOOT_PLANT_FIELDS = (
    "propulsion", "phase", "battery_kwh", "battery_capacity_kwh", "aip_kwh",
    "aip_capacity_kwh", "aip_kw", "load_kw", "supply_kw", "net_kw", "empty_s",
    "full_s", "generator_kw", "fuel_l", "fuel_capacity_l", "charge_rate",
    "snorkel_rate", "endurance", "air")
UBOOT_AIR_FIELDS = ("o2_pct", "co2_pct", "absorber_pct", "absorber_sets", "candles",
                    "candle_left_s", "level", "efficiency")
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
