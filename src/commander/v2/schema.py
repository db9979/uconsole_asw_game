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
# HQ tasks in the radio room (``src/core/tasking.py``): the reported
# position and the task's clock, never the raft's or a ship's true position.
RADIO_TASK_FIELDS = ("id", "type", "state", "name", "persons", "x", "y", "radius_nm",
                     "course", "speed_kn", "bearing", "range_nm", "respond_s",
                     "remaining_s", "progress", "sighted", "verdict", "points",
                     "can_answer")
RADIO_TASK_KINDS = ("sar", "identify", "datum", "ras", "emcon")
# The crew's watch bill, fatigue and morale (``src/core/crew.py``): the
# frigate's on the bridge and damage roles, the boat's in ``damage_control``.
CREW_FIELDS = ("on_watch", "watches", "watch_left_s", "turnover", "action_stations",
               "morale", "effectiveness")
CREW_WATCH_FIELDS = ("index", "fatigue", "on_duty")
# The patrol aircraft in the OPZ's own assets (``src/air/mpa.py``):
# commanded own-force datalink state, never what it has not reported.
MPA_FIELDS = ("state", "airborne", "x", "y", "course", "bearing", "range_nm",
              "waypoint_x", "waypoint_y", "station_left_s", "ready_in_s",
              "sorties_left", "buoys", "torpedoes", "radar", "buoy_mode", "pattern",
              "pattern_points", "datalink", "relayed")
MPA_STATES = ("BASE", "TRANSIT", "STATION", "RTB")
RADIO_TASK_STATES = ("offered", "active", "done", "failed", "declined")

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

# The eyepieces' sky (``src/ui/sight_scene.py``): light, cloud and weather
# in the picture, sun and moon; the bridge lookout's binoculars (``lookout``).
SKY_FIELDS = ("light", "dusk", "cloud", "precipitation", "intensity", "wind_from_deg",
              "sun_bearing", "sun_alt_deg", "moon_bearing", "moon_alt_deg",
              "moon_illumination", "moon_waxing")
LOOKOUT_GLASSES_FIELDS = ("course", "fov_deg", "visibility_nm", "sea_state", "horizon_offset",
                          "horizon_tilt", "sky", "outlines")
LOOKOUT_OUTLINE_FIELDS = ("bearing", "span_deg", "cls", "stale")
SIGHT_CLASSES = ("warship", "merchant", "aircraft", "torpedo", "unknown")

_UBOOT_COMMAND_SHAPE = ("navigation", "status", "weapons", "alarms", "contacts",
                        "own_weapons", "designated_target_ref", "feed", "scope", "plant",
                        "esm", "ballast", "damage_control", "threat", "radio")
# The boat's plant and stores (``plant``): numbers, then the air block.
UBOOT_PLANT_FIELDS = (
    "propulsion", "phase", "battery_kwh", "battery_capacity_kwh", "aip_kwh",
    "aip_capacity_kwh", "aip_kw", "load_kw", "supply_kw", "net_kw", "empty_s",
    "full_s", "generator_kw", "fuel_l", "fuel_capacity_l", "charge_rate",
    "snorkel_rate", "endurance", "air")
UBOOT_AIR_FIELDS = ("o2_pct", "co2_pct", "absorber_pct", "absorber_sets", "candles",
                    "candle_left_s", "level", "efficiency")
# The boat's tanks, trim and high-pressure air (``ballast``): flags first,
# then numbers (kilograms, bar, degrees, m/s; + heavy / bow down / sinking).
UBOOT_BALLAST_FLAGS = ("blowing", "venting", "auto", "pumping", "compressor")
UBOOT_BALLAST_FIELDS = UBOOT_BALLAST_FLAGS + (
    "hp_air_bar", "hp_air_max_bar", "blows_left", "mbt_pct", "regulating_kg",
    "regulating_order_kg", "regulating_capacity_kg", "trim_kg", "trim_order_kg",
    "trim_capacity_kg", "load_kg", "flooding_kg", "residual_kg", "trim_deg", "drift_mps")
# The boat's compartments and damage-control teams (``damage_control``).
UBOOT_DAMAGE_FIELDS = ("power", "pumping", "compartments", "teams", "crew")
UBOOT_COMPARTMENT_FIELDS = ("name", "water_kg", "capacity_kg", "leak_pct", "fire_pct",
                            "chlorine_pct", "closed", "down")
UBOOT_DC_TEAM_FIELDS = ("team", "compartment", "task", "transit_s")
UBOOT_COMPARTMENTS = ("bow", "control", "quarters", "battery", "engine", "stern")
UBOOT_DC_TASKS = ("idle", "seal", "pump", "fire")
# The boat's own ESM picture (``esm``): mast state, then one row per emitter
# with its bearing history (own positions) and the crew's cross-fix.
UBOOT_ESM_FIELDS = ("mast_up", "mast_s", "mast_time_s", "mast_threat", "mast_radar_nm",
                    "wash", "emitters")
UBOOT_ESM_EMITTER_FIELDS = (
    "number", "label", "bearing", "bearing_uncertainty_deg", "frequency_hz", "band",
    "prf_hz", "modulation", "signal_db", "trend", "trend_db_min", "age_s", "live",
    "quality", "classification", "candidates", "range_estimate_nm", "mast_threat",
    "scan", "scan_period_s", "history", "fix")
UBOOT_ESM_HISTORY_FIELDS = ("age_s", "x", "y", "bearing")
UBOOT_ESM_CANDIDATE_FIELDS = ("name", "role", "fit")
# The boat's counter-detection picture (``threat``, src/core/boat_threat.py):
# its own intercepts, layer, noise and mast, and the evasion order (``plan``).
UBOOT_THREAT_FIELDS = ("intercepts", "counts", "loudest_db", "echo_likely", "trend",
                       "layer", "layer_m", "depth_m", "noise", "mast", "esm_count",
                       "advice", "plan")
UBOOT_INTERCEPT_FIELDS = ("type", "bearing", "level_db", "age_s")
UBOOT_INTERCEPT_KINDS = ("hull", "dipping", "buoy", "splash", "torpedo")
UBOOT_THREAT_ADVICE = ("uboot.advice.torpedo", "uboot.advice.mast_down",
                       "uboot.advice.slow_down", "uboot.advice.measure_layer",
                       "uboot.advice.go_below", "uboot.advice.evade")
UBOOT_EVADE_PLAN_FIELDS = ("type", "bearing", "course", "speed_kn", "depth_m", "silent",
                           "decoy")
# The boat's radio room (``radio``, src/core/boat_radio.py): schedule,
# transmissions, HQ's latest contact report and the message log.
UBOOT_RADIO_FIELDS = ("antenna", "broadcast", "copied", "next_s", "copy", "send",
                      "transmitting", "sitreps", "ack_due", "report", "log")
UBOOT_RADIO_LOG_FIELDS = ("seq", "type", "age_s", "number", "ack", "report")
UBOOT_RADIO_LOG_KINDS = ("broadcast", "sent", "aborted")
UBOOT_RADIO_REPORT_FIELDS = ("x", "y", "radius_nm", "course", "speed_kn", "age_s")
UBOOT_ESM_FIX_FIELDS = ("x", "y", "major_nm", "minor_nm", "axis_deg", "lines", "consistent")
# Top-level keys of every role payload (exact sets on both sides).
ROLE_SHAPES = {
    "bridge": ("navigation", "orders", "threat", "systems", "tactical_summary", "sightings",
               "crew", "lookout"),
    "sonar": ("observations", "settings", "visualization"),
    "weapons": ("inventory", "readiness", "designated_target", "navigation", "tactical",
                "target_choices", "depth_m", "tubes", "settings", "own_weapons",
                "active_assets"),
    "damage": ("compartments", "teams", "total", "sunk", "stability", "crew"),
    "opz": ("observations", "fusions", "radar", "defense", "asm_observations",
            "source_classifications", "radar_blips", "designated_target_ref", "own_assets"),
    "radio": ("observations", "logged_fixes", "logged_bearings", "messages", "station_down",
              "navigation", "tactical", "tasks"),
    "engine": ("propulsion", "machinery", "controls", "environment_effects"),
    "helicopter": ("asset", "waypoint", "buoys", "buoy_observations", "acoustic",
                   "navigation", "tactical", "target_choices", "readiness",
                   "dip_observations", "dip_environment"),
    "eloka": ("intercepts", "station_down", "status", "hardware"),
    **{role: _UBOOT_COMMAND_SHAPE for role in OPFOR_ROLES if role != "uboot_sonar"},
    "uboot_sonar": ("observations", "settings", "visualization"),
}
