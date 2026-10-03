"""Contact-document schema: field sets, enumerations and limits of the
packaged catalog JSON, and the value checks of a legacy contact entry
(``validate_contact_entry``).  Moved verbatim from ``catalog.py``, which
re-exports every name.
"""

import math
import re
from urllib.parse import urlsplit

from src.data.catalog_types import (
    CIVIL_CATEGORIES)


CONTACT_FIELDS = {
    "subs.json": {"key", "name", "speed_kn", "max_depth_m", "torpedoes",
                  "quiet", "aggression", "spawn_weight", "acoustic",
                  "wiki_url", "default_faction", "rcs_m2"},
    "warships.json": {"key", "name", "category", "hostile", "speed_kn",
                      "callsigns", "esm_prob", "asm_salvo", "asm_cooldown_s",
                      "loiter_nm", "spawn_weight", "acoustic",
                      "wiki_url", "default_faction", "rcs_m2"},
    "aircraft.json": {"key", "name", "nation", "kind", "speed_kn", "esm",
                      "esm_range_nm", "loiter_nm", "spawn_weight", "signature_text",
                      "wiki_url", "default_faction", "rcs_m2"},
    "animals.json": {"key", "name", "depth_min", "depth_max", "speed_kn",
                     "quiet", "size_nm", "spawn_weight", "lines", "signature_text"},
    "torpedoes.json": {"key", "name", "used_by", "speed_kn", "range_nm", "hit_dist_nm"},
    "decoys.json": {"key", "name", "life_s", "speed_kn", "cooldown_s",
                    "chance", "lines", "signature_text"},
    "acoustics.json": {"key", "label", "propulsion", "blades", "rpm_range",
                       "tonal_band_hz", "cavitation_tendency", "category",
                       "secondary_tonals", "broadband", "signature_text",
                       "lofar_base_freq_hz", "cavitation_speed_knots", "audio_sample_id"},
}
CONTACT_FIELDS["civilians.json"] = CONTACT_FIELDS["warships.json"]
ACOUSTIC_FIELDS = CONTACT_FIELDS["acoustics.json"] - {"key"}
# Entry-level fields that may be entirely absent (authoring not yet done for
# that profile), mirroring the pre-existing torpedoes.json "acoustic" optionality.
ENTRY_OPTIONAL_FIELDS = {"wiki_url", "default_faction", "rcs_m2"}
ACOUSTIC_OPTIONAL_FIELDS = {"lofar_base_freq_hz", "cavitation_speed_knots", "audio_sample_id"}
DEFAULT_FACTIONS = ("FREUND", "FEIND", "NEUTRAL")
ACOUSTIC_CATEGORIES = (*CIVIL_CATEGORIES, "KAMPFSCHIFF", "U_BOOT", "FAHRZEUG", "BIOLOGISCH")
CONTACT_FILENAMES = tuple(CONTACT_FIELDS)
SOURCES_FILENAME = "sources.json"
KEY_PATTERN = re.compile(r"[a-z][a-z0-9_-]*(?:\.[a-z0-9][a-z0-9_-]*)*\Z")
V2_DOCUMENT_FIELDS = {
    "version", "entries", "profiles", "references", "machines", "sensors",
    "emitters", "weapons", "launchers", "magazines", "countermeasures",
}
V2_OPTIONAL_DOCUMENT_FIELDS = {"endurances"}
PROFILE_SYSTEM_FIELDS = {
    "profile_key", "reference_key", "machine_key", "sensor_keys", "emitter_keys",
    "launcher_keys", "magazine_keys", "countermeasure_keys",
}
REFERENCE_FIELDS = {"key", "hull_type", "length_m"}
MACHINE_FIELDS = {
    "key", "cruise_speed_kn", "maximum_speed_kn", "quiet_speed_kn",
    "propulsion_codes", "motor_rpm", "shaft_rpm", "propulsor_type", "blade_count",
    "cruise_lines", "high_speed_lines", "cruise_broadband", "high_speed_broadband",
}
ENDURANCE_FIELDS = {
    "key", "battery_capacity_kwh", "hotel_load_kw", "propulsion_max_kw",
    "propulsion_exponent", "generator_power_kw", "aip_power_kw",
    "aip_energy_kwh", "reserve_start_fraction", "reserve_stop_fraction",
    "snorkel_depth_m", "radio_duration_s",
}
SENSOR_FIELDS = {
    "key", "domain", "modes", "emits", "emitter_key", "synthetic_range_nm",
    "sensitivity_db", "cadence_s", "bearing_uncertainty_deg",
    "range_uncertainty_nm", "depth_uncertainty_m",
}
EMITTER_FIELDS = {
    "key", "domain", "frequency_band_hz", "prf_band_hz", "modulation_codes",
    "radar_role", "operating_mode", "power_class", "operating_period_s",
    "on_duration_s",
}
LEGACY_EMITTER_FIELDS = {
    "key", "domain", "frequency_band_hz", "prf_band_hz", "modulation_codes",
}
WEAPON_FIELDS = {
    "key", "weapon_type", "target_domains", "runtime_profile_key", "maximum_speed_kn",
    "engagement_range_nm", "seeker_type", "guidance_type", "payload_type",
}
LAUNCHER_FIELDS = {
    "key", "launcher_type", "mount_count", "ready_count", "reload_s",
    "arc_center_deg", "arc_width_deg", "vls_cells", "weapon_keys",
}
MAGAZINE_FIELDS = {"key", "weapon_key", "mission_count"}
COUNTERMEASURE_FIELDS = {
    "key", "effect_type", "payload_key", "mission_count", "ready_count", "reload_s",
}
SOURCE_FIELDS = {"id", "kind", "title", "publisher", "url", "reference", "retrieved", "license"}
CLAIM_FIELDS = {"resource", "profile_key", "field_paths", "status", "source_ids"}

HULL_TYPES = {
    "aircraft_carrier", "container_ship", "cruiser", "destroyer", "frigate",
    "fixed_wing_aircraft", "replenishment_ship", "submarine", "support_ship", "unknown",
}
PROPULSION_CODES = {
    "biological", "diesel", "electric", "gas_turbine", "integrated_electric",
    "nuclear_steam", "other", "steam",
}
PROPULSOR_TYPES = {"propeller", "pumpjet", "waterjet", "other", "unknown"}
SENSOR_DOMAINS = {"ais", "esm", "hfdf", "radar", "sonar", "visual"}
SENSOR_MODES = {"active", "passive"}
MODULATION_CODES = {"continuous_wave", "frequency_agile", "pulse", "pulse_doppler", "unknown"}
RADAR_ROLES = {"navigation", "surface_search", "air_search", "multi_function",
               "fire_control", "missile_seeker"}
RADAR_POWER_CLASSES = {"low", "medium", "high"}
# Radars of the frigate's own aircraft (helicopter, patrol aircraft): a
# library like the missile seekers, radiated by those assets, never by a
# catalog platform.
OWN_ASSET_EMITTER_PREFIX = "emitter.own_asset."
WEAPON_TYPES = {"asm", "asroc", "ciws", "sam", "torpedo"}
TARGET_DOMAINS = {"air", "subsurface", "surface"}
SEEKER_TYPES = {"acoustic_active", "acoustic_passive", "command", "infrared", "none", "radar_active"}
GUIDANCE_TYPES = {"command", "datum", "homing", "inertial", "terminal_homing"}
PAYLOAD_TYPES = {"high_explosive", "kinetic", "torpedo"}
LAUNCHER_TYPES = {"ciws", "rail", "torpedo_tube", "vls"}
COUNTERMEASURE_TYPES = {"acoustic_decoy", "chaff", "rf_softkill", "towed_acoustic"}
MAX_CATALOG_DOCUMENT_BYTES = 4 * 1024 * 1024
MAX_CATALOG_ENTRIES = 4096
RUNTIME_SNAPSHOT_VERSION = 2
RUNTIME_BINDINGS = {
    "frigate_torpedo": "frigate_torp",
    "helicopter_torpedo": "helo_torp",
    "enemy_torpedo": "enemy_torp",
    "submarine_decoy": "decoy",
    "civil_flight": "civil_transit",
    "military_flight": "mil_patrol",
}


def _schema_object(value, fields, where, optional=()):
    if not isinstance(value, dict):
        raise ValueError(f"{where}: object expected")
    missing = fields - set(optional) - value.keys()
    extra = value.keys() - fields
    if missing or extra:
        raise ValueError(f"{where}: missing fields {sorted(missing)}; unknown fields {sorted(extra)}")


def _schema_number(value, where, low=0, high=None, positive=False, integer=False):
    if type(value) not in (int, float) or (integer and type(value) is not int):
        raise ValueError(f"{where}: {'integer' if integer else 'number'} expected")
    # Comparing integers directly avoids overflowing float conversion on hostile JSON.
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError(f"{where}: finite number expected")
    if value < low or (positive and value <= 0) or (high is not None and value > high):
        raise ValueError(f"{where}: number outside allowed range")
    if abs(value) > 1e100:
        raise ValueError(f"{where}: number outside safe range")


def _schema_text(value, where):
    if not isinstance(value, str) or not value.strip() or len(value) > 500:
        raise ValueError(f"{where}: non-empty string of at most 500 characters expected")
    if any(ord(char) < 32 and char not in "\n\t" for char in value):
        raise ValueError(f"{where}: control characters not allowed")


def _schema_wiki_url(value, where):
    _schema_text(value, where)
    parsed = urlsplit(value)
    if (parsed.scheme != "https" or not parsed.hostname
            or not parsed.hostname.lower().endswith(".wikipedia.org")
            or not parsed.path.startswith("/wiki/")):
        raise ValueError(f"{where}: https://<lang>.wikipedia.org/wiki/... URL expected")


def _schema_pair(value, where, high, equal=False, integer=False):
    if not isinstance(value, list) or len(value) != 2:
        raise ValueError(f"{where}: two-item array expected")
    for item in value:
        _schema_number(item, where, high=high, integer=integer)
    if value[0] > value[1] or (not equal and value[0] == value[1]):
        raise ValueError(f"{where}: range must be ordered")


def _schema_lines(value, where):
    if not isinstance(value, list) or len(value) > 256:
        raise ValueError(f"{where}: array of at most 256 lines expected")
    for line in value:
        if not isinstance(line, list) or len(line) != 3:
            raise ValueError(f"{where}: three-item array expected")
        _schema_number(line[0], where, high=100000, positive=True)
        _schema_number(line[1], where, high=1)
        _schema_number(line[2], where, high=10000, positive=True)


def _schema_number_array(value, where, maximum=32, high=100000):
    if not isinstance(value, list) or len(value) > maximum:
        raise ValueError(f"{where}: bounded number array expected")
    for item in value:
        _schema_number(item, where, high=high, positive=True)


def _schema_acoustic(value, where, category=None):
    _schema_object(value, ACOUSTIC_FIELDS, where, ACOUSTIC_OPTIONAL_FIELDS)
    for field in ("label", "propulsion", "signature_text"):
        _schema_text(value[field], f"{where}.{field}")
    if "lofar_base_freq_hz" in value:
        if not value["lofar_base_freq_hz"]:
            raise ValueError(f"{where}.lofar_base_freq_hz: omit the field instead of an empty array")
        _schema_number_array(value["lofar_base_freq_hz"], f"{where}.lofar_base_freq_hz")
    if "cavitation_speed_knots" in value:
        _schema_number(value["cavitation_speed_knots"],
                       f"{where}.cavitation_speed_knots", high=1000, positive=True)
    if "audio_sample_id" in value:
        _schema_text(value["audio_sample_id"], f"{where}.audio_sample_id")
    blades = value["blades"]
    if not isinstance(blades, list) or len(blades) > 20:
        raise ValueError(f"{where}.blades: positive integer array expected")
    for blade in blades:
        _schema_number(blade, f"{where}.blades", low=1, high=20, integer=True)
    if len(set(blades)) != len(blades):
        raise ValueError(f"{where}.blades: duplicate value")
    for field in ("rpm_range", "tonal_band_hz"):
        band = value[field]
        _schema_pair(band, f"{where}.{field}", 100000, equal=band == [0, 0])
    _schema_number(value["cavitation_tendency"], f"{where}.cavitation_tendency", high=1)
    if value["category"] not in ACOUSTIC_CATEGORIES or (
            category is not None and value["category"] != category):
        raise ValueError(f"{where}.category: invalid category")
    _schema_lines(value["secondary_tonals"], f"{where}.secondary_tonals")
    broadband = value["broadband"]
    if broadband is not None:
        if not isinstance(broadband, list) or len(broadband) != 3:
            raise ValueError(f"{where}.broadband: null or three-item array expected")
        _schema_number(broadband[0], f"{where}.broadband", high=1)
        _schema_pair(broadband[1:], f"{where}.broadband", 100000)
        _schema_number(broadband[1], f"{where}.broadband", positive=True)


def validate_contact_entry(filename, entry, where="entry"):
    """Strict JSON schema shared by the package loader and offline validator.

    Bounds are defensive authoring limits, not real-platform performance claims.
    Editor documents have their own versioned schema and are not runtime profiles.
    """
    optional = {"acoustic"} if filename == "torpedoes.json" else set()
    if filename in ("subs.json", "warships.json", "civilians.json", "aircraft.json"):
        optional = optional | ENTRY_OPTIONAL_FIELDS
    elif filename == "acoustics.json":
        optional = optional | ACOUSTIC_OPTIONAL_FIELDS
    _schema_object(entry, CONTACT_FIELDS[filename] | optional, where, optional)
    _schema_text(entry["key"], f"{where}.key")
    if filename == "acoustics.json":
        _schema_acoustic({k: v for k, v in entry.items() if k != "key"}, where)
        return
    _schema_text(entry["name"], f"{where}.name")
    if "wiki_url" in entry:
        _schema_wiki_url(entry["wiki_url"], f"{where}.wiki_url")
    if "default_faction" in entry and entry["default_faction"] not in DEFAULT_FACTIONS:
        raise ValueError(f"{where}.default_faction: invalid faction")
    if "rcs_m2" in entry:
        _schema_number(entry["rcs_m2"], f"{where}.rcs_m2", high=200000, positive=True)
    for field in ("nation", "signature_text"):
        if field in entry:
            _schema_text(entry[field], f"{where}.{field}")
    for field in ("hostile", "esm"):
        if field in entry and type(entry[field]) is not bool:
            raise ValueError(f"{where}.{field}: boolean expected")
    for field, maximum in (("quiet", 1), ("aggression", 1), ("esm_prob", 1),
                           ("chance", 1), ("spawn_weight", 100000),
                           ("depth_min", 2000), ("depth_max", 2000),
                           ("esm_range_nm", 5000)):
        if field in entry:
            _schema_number(entry[field], f"{where}.{field}", high=maximum)
    for field, maximum in (("max_depth_m", 2000), ("range_nm", 5000),
                           ("hit_dist_nm", 100), ("size_nm", 100),
                           ("life_s", 604800), ("cooldown_s", 604800)):
        if field in entry:
            _schema_number(entry[field], f"{where}.{field}", high=maximum, positive=True)
    if "lines" in entry:
        _schema_lines(entry["lines"], f"{where}.lines")
    if filename in ("subs.json", "warships.json", "civilians.json"):
        _schema_pair(entry["speed_kn"], f"{where}.speed_kn", 1000)
        category = "U_BOOT" if filename == "subs.json" else entry["category"]
        _schema_acoustic(entry["acoustic"], f"{where}.acoustic", category)
    else:
        _schema_number(entry["speed_kn"], f"{where}.speed_kn", high=5000,
                       positive=filename != "animals.json")
    if filename == "subs.json":
        _schema_number(entry["torpedoes"], f"{where}.torpedoes", high=100, integer=True)
        if entry["acoustic"]["propulsion"] not in (
                "Diesel-elektrisch", "elektrisch/AIP", "elektrisch/Kernantrieb"):
            raise ValueError(f"{where}.acoustic.propulsion: invalid submarine propulsion")
    elif filename in ("warships.json", "civilians.json"):
        allowed = ("KAMPFSCHIFF",) if filename == "warships.json" else CIVIL_CATEGORIES
        if entry["category"] not in allowed:
            raise ValueError(f"{where}.category: invalid surface category")
        if entry["hostile"] != (filename == "warships.json"):
            raise ValueError(f"{where}.hostile: does not match surface catalog")
        callsigns = entry["callsigns"]
        if not isinstance(callsigns, list) or len(callsigns) > 256:
            raise ValueError(f"{where}.callsigns: string array expected")
        for callsign in callsigns:
            _schema_text(callsign, f"{where}.callsigns")
        _schema_pair(entry["asm_salvo"], f"{where}.asm_salvo", 100, equal=True, integer=True)
        _schema_number(entry["asm_cooldown_s"], f"{where}.asm_cooldown_s", high=604800)
        _schema_number(entry["loiter_nm"], f"{where}.loiter_nm", high=5000)
    elif filename == "aircraft.json":
        if entry["kind"] not in ("civil", "military"):
            raise ValueError(f"{where}.kind: invalid aircraft kind")
        _schema_pair(entry["loiter_nm"], f"{where}.loiter_nm", 5000, equal=True)
    elif filename == "animals.json":
        if entry["depth_min"] >= entry["depth_max"]:
            raise ValueError(f"{where}: depth range must be ordered")
    elif filename == "torpedoes.json":
        if entry["used_by"] not in ("frigate", "helo", "enemy"):
            raise ValueError(f"{where}.used_by: invalid torpedo owner")
        if "acoustic" in entry:
            _schema_acoustic(entry["acoustic"], f"{where}.acoustic", "FAHRZEUG")
