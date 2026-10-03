"""The closed Remote Crew v2 command surface: per-action parameter validators,
the action registry and the command envelope (verbatim from ``server.py``)."""


from dataclasses import dataclass
import json
import math
import unicodedata

from src.core import plot
from src.core.config import (NATO_AFFILIATIONS, PLAYER_CLASSES,
                             RADAR_RANGE_SCALES_NM, SHIP_SPEED_MAX_KN,
                             HELO_DIP_DEPTH_MIN_M, HELO_DIP_DEPTH_MAX_M,
                             DIFFICULTY_FIELDS, SAVE_SLOTS, SCENARIO_ORDER,
                             START_LENGTH_CHOICES, START_TIME_CHOICES,
                             START_WEATHER_CHOICES)
from src.commander.v2.wire import (
    HOST_ROLE,
    ROLES,
    STATIONS,
    _V2_COMMAND_FIELDS)


@dataclass(frozen=True)
class V2Action:
    """Closed command metadata; M6/M7 add schemas and main-thread handlers here."""

    stations: frozenset
    validate_params: object
    direct_fire: bool = False
    phases: frozenset = frozenset({"live"})
    # Only operator annotations of the shared picture are optimistic edits that
    # must match the crew assessment revision the browser saw. Every other
    # action resolves its opaque refs (if any) at apply time, so an unrelated
    # contact change must not reject it.
    revision_bound: bool = False


def _no_params(params):
    return type(params) is dict and not params


def _course_params(params):
    return (type(params) is dict and set(params) == {"course"}
            and type(params["course"]) in (int, float)
            and 0 <= params["course"] < 360)


def _speed_params(params):
    return (type(params) is dict and set(params) == {"speed_kn"}
            and type(params["speed_kn"]) in (int, float)
            and 0 <= params["speed_kn"] <= SHIP_SPEED_MAX_KN)


def _ref(value):
    return (type(value) is str and 1 <= len(value) <= 64
            and not any(unicodedata.category(char).startswith("C") for char in value))


def _classification_params(params):
    return (type(params) is dict and set(params) == {"ref", "classification"}
            and _ref(params["ref"])
            and (params["classification"] is None
                 or params["classification"] in PLAYER_CLASSES))


def _release_params(params):
    return (type(params) is dict and set(params) == {"ref", "released"}
            and _ref(params["ref"]) and type(params["released"]) is bool)


def _affiliation_params(params):
    return (type(params) is dict and set(params) == {"ref", "affiliation"}
            and _ref(params["ref"])
            and params["affiliation"] in NATO_AFFILIATIONS)


def _fusion_refs_params(params):
    refs = params.get("refs") if type(params) is dict and set(params) == {"refs"} else None
    return (type(refs) is list and 2 <= len(refs) <= 8
            and all(_ref(ref) for ref in refs) and len(set(refs)) == len(refs))


def _suggestion_refs_params(params):
    refs = params.get("refs") if type(params) is dict and set(params) == {"refs"} else None
    return (type(refs) is list and len(refs) == 2
            and all(_ref(ref) for ref in refs) and refs[0] != refs[1])


def _single_ref_params(params):
    return type(params) is dict and set(params) == {"ref"} and _ref(params["ref"])


def _track_label_params(params):
    if (type(params) is not dict or set(params) != {"ref", "label"}
            or not _ref(params["ref"]) or type(params["label"]) is not str):
        return False
    label = params["label"]
    return (1 <= len(label) <= 16 and label.isascii()
            and any(char.isalnum() for char in label)
            and all(char.isalnum() or char == "-" for char in label))


def _torpedo_params(params):
    return (type(params) is dict and set(params) == {"ref", "depth_m"}
            and _ref(params["ref"])
            and type(params["depth_m"]) in (int, float)
            and math.isfinite(params["depth_m"])
            and 10 <= params["depth_m"] <= 300)


def _torpedo_settings_params(params):
    return (type(params) is dict
            and set(params) == {"torpedo_type", "pattern", "enable_nm", "salvo"}
            and isinstance(params["torpedo_type"], str)
            and 1 <= len(params["torpedo_type"]) <= 64
            and params["pattern"] in ("snake", "circle", "helix")
            and type(params["enable_nm"]) in (int, float)
            and math.isfinite(params["enable_nm"])
            and 0.6 <= params["enable_nm"] <= 3.0
            and type(params["salvo"]) is int and params["salvo"] in (1, 2))


def _radar_params(params):
    return (type(params) is dict and set(params) == {"domain", "enabled"}
            and params["domain"] in ("surface", "air")
            and type(params["enabled"]) is bool)


def _range_params(params):
    return (type(params) is dict and set(params) == {"range_nm"}
            and type(params["range_nm"]) in (int, float)
            and params["range_nm"] in RADAR_RANGE_SCALES_NM)


# Rejections of the crewed submarine's own orders (their own vocabulary,
# never the frigate's words).
UBOOT_REASONS = frozenset((
    "uboot_no_torpedoes", "uboot_reloading", "uboot_out_of_arc", "uboot_no_decoys",
    "uboot_no_threat",
    "uboot_too_deep", "uboot_no_snorkel", "uboot_no_wire", "uboot_mast_depth", "uboot_buoy_lost",
    "uboot_mast_down", "uboot_no_sighting", "uboot_no_stadimeter",
    "uboot_no_absorbers", "uboot_no_candles", "uboot_candle_burning",
    "uboot_no_air_stores", "uboot_no_hp_air", "uboot_compartment_down",
    "uboot_no_antenna", "uboot_transmitting", "uboot_no_solution",
    "uboot_tube_dry", "uboot_tubes_full", "uboot_no_dry_tube", "uboot_route_full",
    "uboot_not_surfaced"))


def _uboot_tube_params(params):
    """``{"tube": index}`` (0-based) or ``{"tube": None}`` for the next one."""
    return (type(params) is dict and set(params) == {"tube"}
            and (params["tube"] is None
                 or (type(params["tube"]) is int and 0 <= params["tube"] < 32)))


def _uboot_ballast_params(params):
    return (type(params) is dict and set(params) == {"tank", "direction"}
            and type(params["tank"]) is str and params["tank"] in ("regulating", "trim")
            and type(params["direction"]) is int and params["direction"] in (-1, 1))


_UBOOT_COMPARTMENTS = ("bow", "control", "quarters", "battery", "engine", "stern")


def _uboot_dc_team_params(params):
    return (type(params) is dict and set(params) == {"team", "compartment", "task"}
            and type(params["team"]) is int and params["team"] in (0, 1)
            and type(params["compartment"]) is str
            and params["compartment"] in _UBOOT_COMPARTMENTS
            and type(params["task"]) is str
            and params["task"] in ("idle", "seal", "pump", "fire"))


def _uboot_bulkhead_params(params):
    return (type(params) is dict and set(params) == {"compartment", "closed"}
            and type(params["compartment"]) is str
            and params["compartment"] in _UBOOT_COMPARTMENTS
            and type(params["closed"]) is bool)


def _bool_params(name):
    return lambda params: (type(params) is dict and set(params) == {name}
                           and type(params[name]) is bool)


def _enum_params(name, values):
    return lambda params: (type(params) is dict and set(params) == {name}
                           and type(params[name]) is str
                           and params[name] in values)


def _bounded_number_params(name, minimum, maximum, *, nullable=False):
    def validate(params):
        if type(params) is not dict or set(params) != {name}:
            return False
        value = params[name]
        if nullable and value is None:
            return True
        return (type(value) in (int, float)
                and minimum <= value <= maximum and math.isfinite(value))
    return validate


_COMPARTMENTS = frozenset(("bridge", "sonar", "weapons", "opz", "radio",
                           "engine", "flightdeck", "hull_left", "hull_right"))


def _sonar_cursor_params(params):
    return (type(params) is dict and set(params) == {"page", "frequency_hz"}
            and params["page"] in ("lofar", "demon")
            and type(params["frequency_hz"]) in (int, float)
            and math.isfinite(params["frequency_hz"])
            and 0.0 <= params["frequency_hz"] <= 300.0)


def _sonar_band_params(params):
    return (type(params) is dict and set(params) == {"low_hz", "high_hz"}
            and all(type(params[name]) in (int, float) and math.isfinite(params[name])
                    for name in ("low_hz", "high_hz"))
            and 0.0 <= params["low_hz"] < params["high_hz"] <= 300.0)


def _tas_side_params(params):
    return (type(params) is dict and set(params) == {"ref", "action"}
            and type(params["ref"]) is str and 0 < len(params["ref"]) <= 64
            and params["action"] in ("flip", "confirm"))


def _demon_band_params(params):
    return (type(params) is dict and set(params) == {"low_hz", "high_hz"}
            and (params["low_hz"], params["high_hz"]) in ((200, 800), (400, 1400),
                                                          (1000, 2000)))


def _assign_profile_params(params):
    key = params.get("profile_key") if type(params) is dict else None
    return (type(params) is dict and set(params) == {"ref", "profile_key"}
            and type(params["ref"]) is str and 0 < len(params["ref"]) <= 64
            and (key is None or (type(key) is str and 0 < len(key) <= 64)))


def _tma_hypothesis_params(params):
    return (type(params) is dict
            and set(params) == {"ref", "course", "speed_kn", "range_nm"}
            and type(params["ref"]) is str and 0 < len(params["ref"]) <= 64
            and all(type(params[name]) in (int, float) and math.isfinite(params[name])
                    for name in ("course", "speed_kn", "range_nm"))
            and 0.0 <= params["course"] < 360.0 and 0.0 <= params["speed_kn"] <= 45.0
            and 0.2 <= params["range_nm"] <= 60.0)


def _plot_add_params(params):
    shape = params.get("shape") if type(params) is dict else None
    if shape not in plot.KINDS:
        return False
    item = {("kind" if key == "shape" else key): value for key, value in params.items()}
    return (set(item) == plot.command_fields(shape)
            and plot.valid_object(dict(item, id=1, t=0.0)))


def _plot_id(value):
    return type(value) is int and 1 <= value <= plot.MAX_ID


def _plot_remove_params(params):
    return type(params) is dict and set(params) == {"id"} and _plot_id(params["id"])


def _plot_relabel_params(params):
    return (type(params) is dict and set(params) == {"id", "label"}
            and _plot_id(params["id"]) and plot.valid_label(params["label"]))


def _integration_params(params):
    return (type(params) is dict and set(params) == {"seconds"}
            and type(params["seconds"]) is int and params["seconds"] in (2, 8, 16, 64))


def _team_compartment_params(params):
    return (type(params) is dict and set(params) == {"team", "compartment"}
            and type(params["team"]) is int and 1 <= params["team"] <= 3
            and type(params["compartment"]) is str
            and params["compartment"] in _COMPARTMENTS)


def _annotation_params(params):
    return (type(params) is dict and set(params) == {"ref", "candidate_ref"}
            and _ref(params["ref"]) and _ref(params["candidate_ref"]))


def _ecm_technique_params(params):
    return (type(params) is dict and set(params) == {"ref", "technique"}
            and _ref(params["ref"])
            and params["technique"] in (
                "noise", "rgpo", "vgpo", "false_targets"))


def _waypoint_params(params):
    return (type(params) is dict and set(params) == {"x", "y"}
            and all(type(params[key]) in (int, float)
                    and 0 <= params[key] <= 1000 and math.isfinite(params[key])
                    for key in ("x", "y")))


def _uboot_depth_params(params):
    return (type(params) is dict and set(params) == {"depth_m"}
            and type(params["depth_m"]) in (int, float)
            and math.isfinite(params["depth_m"])
            and 0 <= params["depth_m"] <= 1000)


def _uboot_speed_params(params):
    return (type(params) is dict and set(params) == {"speed_kn"}
            and type(params["speed_kn"]) in (int, float)
            and math.isfinite(params["speed_kn"])
            and 0 <= params["speed_kn"] <= 40)


def _uboot_scope_params(params):
    """Train the periscope: its line of sight relative to the bow."""
    return (type(params) is dict and set(params) == {"relative_deg"}
            and type(params["relative_deg"]) in (int, float)
            and math.isfinite(params["relative_deg"])
            and 0 <= params["relative_deg"] < 360)


# What a phone lookout may call (src/core/phone_lookout.py CATEGORIES).
LOOKOUT_CALL_CATEGORIES = ("contact", "ship", "warship", "merchant", "aircraft",
                           "submarine", "torpedo")


def _lookout_call_params(params):
    """A phone lookout's call: what, the true bearing and, if said, a range."""
    if type(params) is not dict or set(params) != {"category", "bearing", "range_nm"}:
        return False
    bearing, range_nm = params["bearing"], params["range_nm"]
    return (type(params["category"]) is str
            and params["category"] in LOOKOUT_CALL_CATEGORIES
            and type(bearing) in (int, float) and math.isfinite(bearing)
            and 0 <= bearing < 360
            and (range_nm is None or type(range_nm) in (int, float)
                 and math.isfinite(range_nm) and 0 < range_nm <= 60))


def _uboot_esm_emitter_params(params):
    """One emitter of the boat's ESM list, by the crew's running number."""
    return (type(params) is dict and set(params) == {"emitter"}
            and type(params["emitter"]) is int and 1 <= params["emitter"] <= 2**53)


def _uboot_esm_classify_params(params):
    """Classify an emitter from its library suggestions (-1 clears it)."""
    return (type(params) is dict and set(params) == {"emitter", "candidate"}
            and type(params["emitter"]) is int and 1 <= params["emitter"] <= 2**53
            and type(params["candidate"]) is int and -1 <= params["candidate"] < 16)


def _uboot_wire_params(params):
    """Steer a wired crew torpedo: its ref and the new datum from the boat."""
    return (type(params) is dict and set(params) == {"ref", "bearing", "range_nm"}
            and _ref(params["ref"])
            and all(type(params[key]) in (int, float) and math.isfinite(params[key])
                    for key in ("bearing", "range_nm"))
            and 0 <= params["bearing"] < 360 and 0.05 <= params["range_nm"] <= 40)


def _uboot_waypoint_params(params):
    """A route waypoint in chart coordinates (NM, inside the world)."""
    return (type(params) is dict and set(params) == {"x", "y"}
            and all(type(params[key]) in (int, float) and math.isfinite(params[key])
                    and 0 <= params[key] <= 10_000 for key in ("x", "y")))


def _uboot_torpedo_settings_params(params):
    """Search pattern and seeker enable point (0.6 to 3 NM before the datum)."""
    return (type(params) is dict and set(params) == {"pattern", "enable_nm"}
            and params["pattern"] in ("straight", "snake", "circle", "helix")
            and type(params["enable_nm"]) in (int, float)
            and math.isfinite(params["enable_nm"])
            and 0.6 <= params["enable_nm"] <= 3.0)


def _uboot_fire_params(params):
    """A crew shot: a sonar contact ref, or a free bearing with optional range;
    run depth (optional) and one or two torpedoes."""
    if type(params) is not dict or set(params) != {"ref", "bearing", "range_nm",
                                                    "depth_m", "salvo"}:
        return False
    ref, bearing, range_nm = params["ref"], params["bearing"], params["range_nm"]
    depth = params["depth_m"]
    if type(params["salvo"]) is not int or params["salvo"] not in (1, 2):
        return False
    if depth is not None and not (type(depth) in (int, float) and math.isfinite(depth)
                                  and 5 <= depth <= 300):
        return False
    if (ref is None) == (bearing is None):
        return False
    if ref is not None and not _ref(ref):
        return False
    if bearing is not None and not (type(bearing) in (int, float)
                                    and math.isfinite(bearing) and 0 <= bearing < 360):
        return False
    return range_nm is None or (type(range_nm) in (int, float)
                                and math.isfinite(range_nm)
                                and 0.05 <= range_nm <= 40)


def _bearing_params(params):
    return (type(params) is dict and set(params) == {"bearing"}
            and type(params["bearing"]) in (int, float)
            and 0 <= params["bearing"] < 360
            and math.isfinite(params["bearing"]))


def _navigation_proposal_params(params):
    if (type(params) is not dict or not params
            or not set(params) <= {"course", "speed_kn"}):
        return False
    course = params.get("course")
    speed = params.get("speed_kn")
    return ((course is None or type(course) in (int, float)
             and math.isfinite(course) and 0 <= course < 360)
            and (speed is None or type(speed) in (int, float)
                 and math.isfinite(speed) and 0 <= speed <= SHIP_SPEED_MAX_KN)
            and (course is not None or speed is not None))


def _ref_enabled_params(params):
    return (type(params) is dict and set(params) == {"ref", "enabled"}
            and _ref(params.get("ref"))
            and type(params.get("enabled")) is bool)


def _task_params(params):
    return (type(params) is dict and set(params) == {"task"}
            and type(params["task"]) is int and 1 <= params["task"] <= 10_000)


def _slot_params(params):
    return (type(params) is dict and set(params) == {"slot"}
            and type(params["slot"]) is int and 1 <= params["slot"] <= SAVE_SLOTS)


def _instructor_environment_params(params):
    return (type(params) is dict and set(params) == {"sea_state", "event"}
            and type(params["sea_state"]) is int
            and 0 <= params["sea_state"] <= 6
            and (params["event"] is None or params["event"] in (
                "targets_quiet", "targets_cruise", "targets_flank",
                "torpedo_transient")))


def _mission_key_params(params):
    """An own mission's store key (``user.<lowercase/digit/_/->``)."""
    if type(params) is not dict or set(params) != {"key"} or type(params["key"]) is not str:
        return False
    from src.data.validation import validate_user_key
    return not validate_user_key(params["key"])


def _lobby_choice(value) -> bool:
    """A lobby mission choice: a scenario, ``daily``, ``campaign:<id>`` or
    ``own:<user key>`` (the game checks it against the side's options)."""
    if type(value) is not str or not 1 <= len(value) <= 96:
        return False
    if value in SCENARIO_ORDER or value == "daily":
        return True
    if value.startswith("campaign:"):
        digits = value[len("campaign:"):]
        return digits.isdigit() and digits.isascii() and len(digits) <= 4
    if value.startswith("own:"):
        from src.data.validation import validate_user_key
        return not validate_user_key(value[len("own:"):])
    return False


def _lobby_set_params(params):
    """The server-mode leader's lobby choices, all at once."""
    return (type(params) is dict
            and set(params) == {"side", "choice", "versus", "weather", "time", "length"}
            and params["side"] in ("frigate", "uboot")
            and _lobby_choice(params["choice"])
            and params["versus"] in ("ai", "crew")
            and type(params["weather"]) is str and params["weather"] in START_WEATHER_CHOICES
            and type(params["time"]) is str and params["time"] in START_TIME_CHOICES
            and type(params["length"]) is str and params["length"] in START_LENGTH_CHOICES)


def _lobby_campaign_params(params):
    return (type(params) is dict and set(params) == {"side", "action"}
            and params["side"] in ("frigate", "uboot")
            and params["action"] in ("new", "refit", "quick"))


def _ordinal_params(params):
    return (type(params) is dict and set(params) == {"ordinal"}
            and type(params["ordinal"]) is int and 0 <= params["ordinal"] <= 2 ** 53 - 1)


def _new_game_params(params):
    required = {"scenario", "world_mode"}
    if (type(params) is not dict or not required <= set(params)
            or not set(params) <= required | {"difficulty", "seed", "weather", "time",
                                                  "length"}):
        return False
    if ("weather" in params and params["weather"] not in START_WEATHER_CHOICES
            or "time" in params and params["time"] not in START_TIME_CHOICES
            or "length" in params and params["length"] not in START_LENGTH_CHOICES):
        return False
    if not (type(params["scenario"]) is str and params["scenario"] in SCENARIO_ORDER
            and type(params["world_mode"]) is str
            and params["world_mode"] in ("fixed", "procedural", "real_fixed")
            and ("seed" not in params or type(params["seed"]) is int
                 and 1 <= params["seed"] < 1_000_000_000)):
        return False
    if "difficulty" not in params:
        return True
    difficulty = params["difficulty"]
    if type(difficulty) is not dict or set(difficulty) != set(DIFFICULTY_FIELDS):
        return False
    for name, (kind, low, high, _step, _default) in DIFFICULTY_FIELDS.items():
        amount = difficulty[name]
        if kind is int:
            if type(amount) is not int or not low <= amount <= high:
                return False
        elif (type(amount) not in (int, float) or isinstance(amount, bool)
                or not math.isfinite(amount) or not low <= amount <= high):
            return False
    return True


_HOST_ANY = frozenset({"live"})
_HOST_REPLACING = frozenset({"live", "menu", "ended"})
_HOST_STATIONS = frozenset({HOST_ROLE})
_HOST_MENU = frozenset({"menu"})
# The boat's own plot: its commander and navigator draw on it.
_UBOOT_PLOT = ("uboot", "uboot_nav")

V2_ACTION_REGISTRY = {
    "acknowledge": V2Action(frozenset(ROLES), _no_params),
    # Shared chart plot: every station may draw, relabel and erase.
    # The submarine commander's plot actions reach the boat's own plot.
    "plot_add": V2Action(frozenset((*STATIONS, *_UBOOT_PLOT)), _plot_add_params),
    "plot_remove": V2Action(frozenset((*STATIONS, *_UBOOT_PLOT)), _plot_remove_params),
    "plot_relabel": V2Action(frozenset((*STATIONS, *_UBOOT_PLOT)), _plot_relabel_params),
    "plot_clear": V2Action(frozenset((*STATIONS, *_UBOOT_PLOT)), _no_params),
    # Solo-only host controls: admitted only for a session carrying the host
    # surface, and each action states the exact phases it may run in.
    "host_save": V2Action(_HOST_STATIONS, _slot_params, phases=_HOST_ANY),
    "host_load": V2Action(_HOST_STATIONS, _slot_params, phases=_HOST_REPLACING),
    "host_new_game": V2Action(_HOST_STATIONS, _new_game_params,
                              phases=_HOST_REPLACING),
    "host_instructor_environment": V2Action(
        _HOST_STATIONS, _instructor_environment_params, phases=_HOST_ANY),
    "host_start_mission": V2Action(_HOST_STATIONS, _mission_key_params,
                                   phases=_HOST_REPLACING),
    # Server mode: the leading browser runs the lobby (``game_server.py``).
    "host_lobby_set": V2Action(_HOST_STATIONS, _lobby_set_params, phases=_HOST_MENU),
    "host_lobby_start": V2Action(_HOST_STATIONS, _no_params, phases=_HOST_MENU),
    "host_lobby_cancel": V2Action(_HOST_STATIONS, _no_params, phases=_HOST_MENU),
    "host_lobby_campaign": V2Action(_HOST_STATIONS, _lobby_campaign_params,
                                    phases=_HOST_MENU),
    "host_end_mission": V2Action(_HOST_STATIONS, _no_params,
                                 phases=frozenset({"live", "ended"})),
    "host_pass_lead": V2Action(_HOST_STATIONS, _ordinal_params, phases=_HOST_REPLACING),
    "bridge_set_course": V2Action(frozenset({"bridge"}), _course_params),
    "bridge_set_speed": V2Action(frozenset({"bridge"}), _speed_params),
    # Autopilot route: waypoints on the chart, search patterns, clear.
    "bridge_route_add": V2Action(frozenset({"bridge"}), _waypoint_params),
    "bridge_route_pattern": V2Action(frozenset({"bridge"}),
                                     _enum_params("pattern", ("zigzag", "square"))),
    "bridge_route_clear": V2Action(frozenset({"bridge"}), _no_params),
    # Swing the course to hear into the hull sonar's baffles, then return.
    "bridge_clear_baffles": V2Action(frozenset({"bridge"}), _no_params),
    "propose_navigation": V2Action(frozenset({"bridge"}),
                                    _navigation_proposal_params),
    "sonar_classify": V2Action(frozenset({"sonar", "helicopter", "uboot_sonar"}), _classification_params,
        revision_bound=True),
    "sonar_set_release": V2Action(frozenset({"sonar", "helicopter"}), _release_params,
        revision_bound=True),
    "helicopter_qualify": V2Action(frozenset({"helicopter"}), _ref_enabled_params,
        revision_bound=True),
    "helicopter_buoy_release": V2Action(frozenset({"helicopter"}), _release_params,
        revision_bound=True),
    "propose_target": V2Action(frozenset({"sonar"}), _single_ref_params,
        revision_bound=True),
    "clear_target_proposal": V2Action(frozenset({"sonar"}), _no_params),
    "opz_classify": V2Action(frozenset({"opz"}), _classification_params,
        revision_bound=True),
    "opz_affiliate": V2Action(frozenset({"opz"}), _affiliation_params,
        revision_bound=True),
    "opz_set_track_id": V2Action(frozenset({"opz"}), _track_label_params,
        revision_bound=True),
    "opz_create_fusion": V2Action(frozenset({"opz"}), _fusion_refs_params,
        revision_bound=True),
    "opz_dissolve_fusion": V2Action(frozenset({"opz"}), _single_ref_params,
        revision_bound=True),
    "opz_dismiss_suggestion": V2Action(frozenset({"opz"}), _suggestion_refs_params),
    "opz_set_radar": V2Action(frozenset({"opz"}), _radar_params),
    "opz_mark_blip": V2Action(frozenset({"opz"}), _single_ref_params),
    "opz_set_ciws": V2Action(frozenset({"opz"}), _bool_params("enabled")),
    "opz_set_range": V2Action(frozenset({"opz"}), _range_params),
    "opz_designate_target": V2Action(frozenset({"opz"}), _single_ref_params),
    "engine_set_telegraph": V2Action(frozenset({"engine"}), _enum_params(
        "order", ("ASTERN", "STOP", "SLOW", "HALF", "FULL", "FLANK"))),
    "engine_set_course": V2Action(frozenset({"engine"}), _course_params),
    "engine_set_speed": V2Action(frozenset({"engine"}), _speed_params),
    "engine_set_quiet_mode": V2Action(frozenset({"engine"}),
                                      _bool_params("enabled")),
    "engine_set_plant": V2Action(frozenset({"engine"}),
                                 _enum_params("mode", ("AUTO", "DIESEL", "TURBINE"))),
    "damage_counterflood": V2Action(frozenset({"damage"}), _bool_params("enabled")),
    # Crew watch bill: action stations from the bridge or damage control,
    # the watch relieved by damage control (the ship's company is its job).
    "crew_action_stations": V2Action(frozenset({"bridge", "damage"}),
                                     _bool_params("enabled")),
    "crew_watch_change": V2Action(frozenset({"damage"}), _no_params),
    # The wounded: medical team to the next station, men to the worst one.
    "crew_casualty_medic": V2Action(frozenset({"damage"}), _no_params),
    "crew_casualty_reassign": V2Action(frozenset({"damage"}), _no_params),
    "damage_assign_team": V2Action(frozenset({"damage"}),
                                   _team_compartment_params),
    "damage_unassign_team": V2Action(frozenset({"damage"}),
                                     _team_compartment_params),
    "radio_capture_hfdf": V2Action(frozenset({"radio"}), _single_ref_params),
    # HQ tasks: the radio room answers an offer (the task's own number).
    "radio_task_accept": V2Action(frozenset({"radio"}), _task_params),
    "radio_task_decline": V2Action(frozenset({"radio"}), _task_params),
    "radio_request_ras": V2Action(frozenset({"radio"}), _no_params),
    # The radio room's own HF calls to HQ (the enemy can DF them).
    "radio_contact_report": V2Action(frozenset({"radio"}), _no_params),
    "radio_request_support": V2Action(frozenset({"radio"}), _no_params),
    "eloka_annotate": V2Action(frozenset({"eloka"}), _annotation_params,
        revision_bound=True),
    "eloka_clear_annotation": V2Action(frozenset({"eloka"}), _single_ref_params,
        revision_bound=True),
    "eloka_set_jamming": V2Action(frozenset({"eloka"}), _ref_enabled_params),
    "eloka_set_technique": V2Action(
        frozenset({"eloka"}), _ecm_technique_params),
    "eloka_set_auto": V2Action(frozenset({"eloka"}), _bool_params("enabled")),
    "sonar_set_listen_bearing": V2Action(frozenset({"sonar", "uboot_sonar"}), _bearing_params),
    "sonar_set_focus": V2Action(frozenset({"sonar", "uboot_sonar"}), _single_ref_params),
    "sonar_clear_focus": V2Action(frozenset({"sonar", "uboot_sonar"}), _no_params),
    "sonar_set_array_mode": V2Action(frozenset({"sonar"}),
        _enum_params("mode", ("BOW", "TOWED", "VDS"))),
    "sonar_set_tas": V2Action(frozenset({"sonar"}), _bool_params("deployed")),
    "sonar_set_tow_depth": V2Action(frozenset({"sonar"}),
        _bounded_number_params("depth_m", 20, 260)),
    "sonar_set_vds": V2Action(frozenset({"sonar"}), _bool_params("deployed")),
    "sonar_set_vds_depth": V2Action(frozenset({"sonar"}),
        _bounded_number_params("depth_m", 20, 300)),
    # The submarine commander may ping and take a BT without its sonar room.
    "sonar_measure_bt": V2Action(frozenset({"sonar", "uboot_sonar", "uboot"}), _no_params),
    "sonar_active_ping": V2Action(frozenset({"sonar", "uboot_sonar", "uboot"}), _no_params),
    "sonar_set_tma_enabled": V2Action(frozenset({"sonar", "uboot_sonar"}),
                                      _bool_params("enabled")),
    "sonar_set_gain": V2Action(frozenset({"sonar", "uboot_sonar"}),
        _bounded_number_params("gain_db", -12, 24)),
    "sonar_set_audition_mode": V2Action(frozenset({"sonar", "uboot_sonar"}),
        _enum_params("mode", ("BROADBAND", "FILTERED", "HETERODYNE"))),
    "sonar_set_band_preset": V2Action(frozenset({"sonar", "uboot_sonar"}),
        _enum_params("preset", ("FULL", "LOW", "SHAFT", "MID"))),
    "sonar_set_notch": V2Action(frozenset({"sonar", "uboot_sonar"}), _bool_params("enabled")),
    "sonar_set_cursor": V2Action(frozenset({"sonar", "uboot_sonar"}), _sonar_cursor_params),
    "sonar_mark_line": V2Action(frozenset({"sonar", "uboot_sonar"}),
        _enum_params("page", ("lofar", "demon"))),
    "sonar_set_integration": V2Action(frozenset({"sonar", "uboot_sonar"}), _integration_params),
    "sonar_set_vernier": V2Action(frozenset({"sonar", "uboot_sonar"}), _bool_params("enabled")),
    "sonar_set_band": V2Action(frozenset({"sonar", "uboot_sonar"}), _sonar_band_params),
    "sonar_set_operator_notch": V2Action(frozenset({"sonar", "uboot_sonar"}),
        _bounded_number_params("frequency_hz", 0.000001, 300, nullable=True)),
    "sonar_set_peak_hold": V2Action(frozenset({"sonar", "uboot_sonar"}),
                                    _bool_params("enabled")),
    "sonar_set_harmonic": V2Action(frozenset({"sonar", "uboot_sonar"}),
        _bounded_number_params("frequency_hz", 0.000001, 300, nullable=True)),
    "sonar_designate_target": V2Action(frozenset({"sonar", "uboot_sonar"}), _single_ref_params),
    "sonar_tma_set": V2Action(frozenset({"sonar", "uboot_sonar"}), _tma_hypothesis_params),
    "sonar_assign_profile": V2Action(frozenset({"sonar", "uboot_sonar"}), _assign_profile_params),
    "sonar_tas_side": V2Action(frozenset({"sonar"}), _tas_side_params),
    "sonar_set_demon_band": V2Action(frozenset({"sonar", "uboot_sonar"}), _demon_band_params),
    "sonar_set_heterodyne": V2Action(frozenset({"sonar", "uboot_sonar"}),
        _bounded_number_params("frequency_hz", 400, 1200)),
    "sonar_tma_accept": V2Action(frozenset({"sonar", "uboot_sonar"}), _single_ref_params),
    "sonar_tma_copy_proposal": V2Action(frozenset({"sonar", "uboot_sonar"}), _single_ref_params),
    "helicopter_launch": V2Action(frozenset({"helicopter"}), _no_params),
    "helicopter_return": V2Action(frozenset({"helicopter"}), _no_params),
    "helicopter_set_waypoint": V2Action(frozenset({"helicopter"}),
                                        _waypoint_params),
    "helicopter_deploy_buoy": V2Action(frozenset({"helicopter"}), _no_params),
    "helicopter_set_pattern": V2Action(frozenset({"helicopter"}),
                                       _enum_params("kind", ("single", "field", "barrier", "circle"))),
    "helicopter_set_mad": V2Action(frozenset({"helicopter"}), _bool_params("enabled")),
    "helicopter_set_radar": V2Action(frozenset({"helicopter"}), _bool_params("enabled")),
    "helicopter_set_buoy_mode": V2Action(frozenset({"helicopter"}),
        _enum_params("mode", ("PASSIVE", "ACTIVE"))),
    "helicopter_set_listen_source": V2Action(frozenset({"helicopter"}),
        lambda params: (type(params) is dict and set(params) == {"source"}
                        and type(params["source"]) is str
                        and (params["source"] == "DIP" or
                             params["source"].startswith("SB")
                             and params["source"][2:].isdigit()
                             and len(params["source"]) <= 5))),
    "helicopter_set_listen_bearing": V2Action(frozenset({"helicopter"}),
        _bounded_number_params("bearing", 0.0, 359.99999999999994)),
    "helicopter_clear_listen_bearing": V2Action(frozenset({"helicopter"}), _no_params),
    "helicopter_set_audio_mode": V2Action(frozenset({"helicopter"}),
        _enum_params("mode", ("BROADBAND", "FILTERED", "HETERODYNE"))),
    "helicopter_set_audio_band": V2Action(frozenset({"helicopter"}),
        _enum_params("preset", ("FULL", "LOW", "SHAFT", "MID"))),
    "helicopter_set_audio_gain": V2Action(frozenset({"helicopter"}),
        _bounded_number_params("gain_db", -12.0, 24.0)),
    "helicopter_set_audio_notch": V2Action(frozenset({"helicopter"}),
        _bool_params("enabled")),
    "helicopter_set_dipping": V2Action(frozenset({"helicopter"}),
                                        _bool_params("deployed")),
    "helicopter_set_dip_depth": V2Action(frozenset({"helicopter"}),
        _bounded_number_params("depth_m", HELO_DIP_DEPTH_MIN_M,
                               HELO_DIP_DEPTH_MAX_M)),
    "helicopter_dipping_ping": V2Action(frozenset({"helicopter"}), _no_params),
    "weapons_launch_torpedo": V2Action(
        frozenset({"weapons"}), _torpedo_params, direct_fire=True),
    "helicopter_launch_torpedo": V2Action(
        frozenset({"weapons", "helicopter"}), _torpedo_params,
        direct_fire=True),
    "weapons_deploy_nixie": V2Action(
        frozenset({"weapons"}), _no_params, direct_fire=True),
    "weapons_fire_asroc": V2Action(
        frozenset({"weapons"}), _torpedo_params, direct_fire=True),
    "weapons_drop_depth_charges": V2Action(
        frozenset({"weapons"}), _torpedo_params, direct_fire=True),
    "weapons_fire_rbu": V2Action(
        frozenset({"weapons"}), _torpedo_params, direct_fire=True),
    "weapons_rbu_defence": V2Action(
        frozenset({"weapons"}), _no_params, direct_fire=True),
    "weapons_set_torpedo_settings": V2Action(
        frozenset({"weapons"}), _torpedo_settings_params),
    "opz_launch_essm": V2Action(
        frozenset({"opz"}), _single_ref_params, direct_fire=True),
    "opz_launch_chaff": V2Action(
        frozenset({"opz"}), _single_ref_params, direct_fire=True),
    # The patrol aircraft (OPZ page 3): its torpedo goes on the designated
    # sonar contact and counts as direct fire.
    "mpa_request": V2Action(frozenset({"opz"}), _no_params),
    "mpa_return": V2Action(frozenset({"opz"}), _no_params),
    "mpa_set_waypoint": V2Action(frozenset({"opz"}), _waypoint_params),
    "mpa_set_pattern": V2Action(frozenset({"opz"}), _enum_params(
        "kind", ("single", "field", "barrier", "circle"))),
    "mpa_drop_buoy": V2Action(frozenset({"opz"}), _no_params),
    "mpa_set_buoy_mode": V2Action(frozenset({"opz"}),
                                  _enum_params("mode", ("PASSIVE", "ACTIVE"))),
    "mpa_set_radar": V2Action(frozenset({"opz"}), _bool_params("enabled")),
    "mpa_set_mad": V2Action(frozenset({"opz"}), _bool_params("enabled")),
    "mpa_attack": V2Action(frozenset({"opz"}), _no_params, direct_fire=True),
    # The consort destroyer of a group hunt (OPZ page 4): its ASROC is direct fire.
    "consort_set_mode": V2Action(frozenset({"opz"}), _enum_params(
        "mode", ("auto", "formation", "search", "prosecute", "hold"))),
    "consort_set_point": V2Action(frozenset({"opz"}), _waypoint_params),
    "consort_set_station": V2Action(frozenset({"opz"}), _enum_params(
        "station", ("starboard", "ahead", "port", "astern"))),
    "consort_set_active": V2Action(frozenset({"opz"}), _bool_params("enabled")),
    "consort_set_weapons": V2Action(frozenset({"opz"}), _bool_params("enabled")),
    "consort_fire": V2Action(frozenset({"opz"}), _no_params, direct_fire=True),
    # The crewed submarine's commander.
    # Each boat order belongs to the station that does it aboard; the commander
    # keeps course, speed and depth.
    "uboot_set_course": V2Action(frozenset({"uboot", "uboot_nav"}), _course_params),
    "uboot_clear_baffles": V2Action(frozenset({"uboot", "uboot_nav"}), _no_params),
    # The navigation's route: chart waypoints, a search pattern, or none.
    "uboot_route_waypoint": V2Action(frozenset({"uboot_nav"}), _uboot_waypoint_params),
    "uboot_route_pattern": V2Action(frozenset({"uboot_nav"}),
                                    _enum_params("pattern", ("zigzag", "square"))),
    "uboot_route_clear": V2Action(frozenset({"uboot_nav"}), _no_params),
    # The weapons officer's seeker settings for the following shots.
    "uboot_torpedo_settings": V2Action(frozenset({"uboot_weapons"}),
                                       _uboot_torpedo_settings_params),
    "uboot_set_speed": V2Action(frozenset({"uboot", "uboot_engine"}), _uboot_speed_params),
    "uboot_set_depth": V2Action(frozenset({"uboot", "uboot_nav"}), _uboot_depth_params),
    "uboot_fire": V2Action(frozenset({"uboot_weapons"}), _uboot_fire_params,
                           direct_fire=True),
    "uboot_decoy": V2Action(frozenset({"uboot_weapons"}), _no_params),
    # The torpedo room loads each tube and floods it before the shot.
    "uboot_tube_load": V2Action(frozenset({"uboot_weapons"}), _uboot_tube_params),
    "uboot_tube_flood": V2Action(frozenset({"uboot_weapons"}), _uboot_tube_params),
    "uboot_tube_flood_quiet": V2Action(frozenset({"uboot_weapons"}), _uboot_tube_params),
    "uboot_evade": V2Action(frozenset({"uboot", "uboot_nav"}), _no_params),
    "uboot_blow": V2Action(frozenset({"uboot", "uboot_engine"}), _no_params),
    "uboot_snorkel": V2Action(frozenset({"uboot_engine"}), _bool_params("enabled")),
    # The engine room also keeps the boat's air and sets the charge rate.
    "uboot_charge_rate": V2Action(frozenset({"uboot_engine"}),
                                  _enum_params("rate", ("full", "half", "vent"))),
    "uboot_absorber": V2Action(frozenset({"uboot_engine"}), _no_params),
    "uboot_o2_candle": V2Action(frozenset({"uboot_engine"}), _no_params),
    # ... and trims the boat (the engineer's automatic trim, or by hand).
    "uboot_trim_auto": V2Action(frozenset({"uboot", "uboot_engine"}), _bool_params("enabled")),
    "uboot_ballast": V2Action(frozenset({"uboot", "uboot_engine"}), _uboot_ballast_params),
    # ... and runs damage control: two teams, the bulkheads.
    "uboot_dc_team": V2Action(frozenset({"uboot", "uboot_engine"}), _uboot_dc_team_params),
    "uboot_bulkhead": V2Action(frozenset({"uboot", "uboot_engine"}), _uboot_bulkhead_params),
    # ... and keeps the watch bill (Command orders action stations as well).
    "uboot_action_stations": V2Action(frozenset({"uboot", "uboot_engine"}),
                                      _bool_params("enabled")),
    "uboot_watch_change": V2Action(frozenset({"uboot", "uboot_engine"}), _no_params),
    "uboot_casualty_medic": V2Action(frozenset({"uboot", "uboot_engine"}), _no_params),
    "uboot_casualty_reassign": V2Action(frozenset({"uboot", "uboot_engine"}), _no_params),
    "uboot_mast": V2Action(frozenset({"uboot", "uboot_esm", "uboot_radio"}),
                           _bool_params("enabled")),
    # The radio room sends the boat's situation report to HQ (HF, bearable).
    "uboot_radio_send": V2Action(frozenset({"uboot_radio"}), _no_params),
    # The towed buoy antenna: stream (enabled) or recover it.
    "uboot_buoy": V2Action(frozenset({"uboot", "uboot_radio"}), _bool_params("enabled")),
    "uboot_wire_steer": V2Action(frozenset({"uboot_weapons"}), _uboot_wire_params),
    "uboot_wire_cut": V2Action(frozenset({"uboot_weapons"}), _single_ref_params),
    "uboot_silent": V2Action(frozenset({"uboot", "uboot_engine"}), _bool_params("enabled")),
    "uboot_bottom": V2Action(frozenset({"uboot", "uboot_nav"}), _bool_params("enabled")),
    # Surface (enabled) or, from the surface, a crash dive.
    "uboot_surface": V2Action(frozenset({"uboot", "uboot_nav"}), _bool_params("enabled")),
    # The periscope: Command and the mast station train it and read the stadimeter.
    # The phone on the periscope (``uboot_lookout``) trains it and reads the
    # stadimeter too.
    "uboot_scope_bearing": V2Action(frozenset({"uboot", "uboot_esm", "uboot_lookout"}),
                                    _uboot_scope_params),
    "uboot_scope_mark": V2Action(frozenset({"uboot", "uboot_esm", "uboot_lookout"}),
                                 _no_params),
    # Command fires on the attack computer's solution of the crosshair sighting.
    "uboot_scope_fire": V2Action(frozenset({"uboot"}), _no_params),
    # The mast station evaluates its ESM picture: classify, transfer to the plot.
    "uboot_esm_classify": V2Action(frozenset({"uboot", "uboot_esm"}),
                                   _uboot_esm_classify_params),
    "uboot_esm_plot": V2Action(frozenset({"uboot", "uboot_esm"}), _uboot_esm_emitter_params),
    # Phone lookouts call what they see; the bridge or the boat hears only that.
    "lookout_call": V2Action(frozenset({"lookout", "uboot_lookout"}), _lookout_call_params),
}


@dataclass(frozen=True)
class V2CommandEnvelope:
    """Detached transport record containing no session or simulation objects."""

    session_digest: bytes
    client_id: str
    client_ordinal: int
    role: str
    lease_generation: int
    active_generation: int
    received_at: float
    body_bytes: bytes
    command_id: str
    seq: int

    def body(self):
        return json.loads(self.body_bytes.decode("ascii"), object_pairs_hook=_object,
                          parse_float=_number, parse_constant=_number)


def _v2_command_valid(command):
    if (type(command) is not dict or set(command) != _V2_COMMAND_FIELDS
            or command.get("protocol") != 2):
        return False
    action = command.get("action")
    spec = V2_ACTION_REGISTRY.get(action) if type(action) is str else None
    if (spec is None or type(command.get("station")) is not str
            or command["station"] not in spec.stations):
        return False
    # The host surface has no station-activation context to bind to.
    if command["station"] == HOST_ROLE and command.get("active_generation") != 0:
        return False
    for field in ("id", "world_session"):
        value = command.get(field)
        if (type(value) is not str or not 1 <= len(value) <= 64
                or any(unicodedata.category(char).startswith("C") for char in value)):
            return False
    for field in ("seq", "station_generation", "active_generation", "world_epoch",
                  "resource_revision"):
        maximum = 2**53 - 2 if field == "seq" else 2**53 - 1
        if type(command.get(field)) is not int or not 0 <= command[field] <= maximum:
            return False
    return spec.validate_params(command.get("params")) is True


def _object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate key")
        result[key] = value
    return result


def _number(text):
    value = float(text)
    if not math.isfinite(value):
        raise ValueError("nonfinite number")
    return value
