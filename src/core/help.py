"""Catalog-keyed, context-sensitive help for all eight stations."""

from src.core.i18n import Translator
from src.core.station import Station


_GLOBAL_HELP = (
    "help.global.title",
    [
        ("Tab / Shift+Tab", "help.next_station"),
        ("1 / 2 / 3 / 4", "help.global.stations_1"),
        ("5 / 6 / 7 / 8", "help.global.stations_2"),
        ("help.key.station_number", "help.repeat_station"),
        ("P", "help.pause"),
        ("help.key.time_scale", "help.time_scale"),
        ("help.key.arrows", "help.station_control"),
        ("U / V", "help.global.course_speed"),
        ("+ / -", "help.global.telegraph"),
        ("F1", "help.global.display"),
        ("N", "help.global.nations"),
        ("S / L", "help.save_load"),
        ("Alt+Enter", "help.fullscreen"),
        ("help.key.mouse_zoom", "help.global.map_zoom"),
        ("Drag", "help.global.map_pan"),
        ("K", "help.global.map_follow"),
        ("Esc", "help.cancel"),
    ],
)


def _station(intro, controls, notes, tactic):
    return intro, controls, notes, [tactic]


STATION_HELP = {
    Station.BRIDGE: _station(
        "help.bridge.intro",
        [("<- / ->", "help.control.rudder"), ("help.key.up_down", "help.control.telegraph_up"),
         ("U", "help.control.course_input"), ("V", "help.control.speed_input"),
         ("+ / -", "help.control.engine_order"), ("help.key.chart", "help.control.mouse_map"),
         ("Q / E", "help.control.zoom"), ("K", "help.control.follow")],
        ["help.note.bridge_noise", "help.note.bridge_coast"], "help.note.bridge_tactic"),
    Station.SONAR: _station(
        "help.sonar.intro",
        [("A", "help.control.active_ping"), ("B", "help.control.array"),
         ("Y", "help.control.tas"), ("help.key.page_spaced", "help.control.pages"),
         ("2", "help.control.repeat_sonar_page"), ("E", "help.control.bt"),
         ("U / V", "help.control.tas_depth"), ("R", "help.control.listen_input"),
         ("<- / ->", "help.control.bearing_step"), ("help.key.up_down", "help.control.contact_select"),
         ("Enter", "help.control.track_bearing"), ("J | , / .", "help.control.audio"),
         ("D", "help.control.filter"), ("I / O", "help.control.gain"),
         ("F", "help.control.band"), ("N", "help.control.notch"),
         ("SPACE", "help.control.peak"), ("T", "help.control.tma"),
         ("C", "help.control.classify"), ("M", "help.control.target")],
        ["help.note.passive", "help.note.tma", "help.note.waterfall",
         "help.note.audio_model", "help.note.demon", "help.note.gain",
         "help.note.snr", "help.note.shadow", "help.note.parallel",
         "help.note.ghost", "help.note.tas_handling", "help.note.tas_depth",
         "help.note.active"], "help.note.sonar_tactic"),
    Station.WEAPONS: _station(
        "help.weapons.intro",
        [("M", "help.control.target_from_sonar"), ("help.key.up_down", "help.control.torp_depth"),
         ("<- / ->", "help.control.target_select"), ("T", "help.control.fire"),
         ("H", "help.control.helo_toggle"), ("B", "help.control.buoy"),
         ("D", "help.control.air_torp"), ("Q / E", "help.control.zoom"),
         ("K", "help.control.follow")],
        ["help.note.roe", "help.note.target_depth", "help.note.salvo"],
        "help.note.weapon_tactic"),
    Station.DAMAGE: _station(
        "help.damage.intro",
        [("<- / ->", "help.control.compartment"), ("help.key.up_down", "help.control.team"),
         ("Enter", "help.control.assign"), ("Backspace", "help.control.withdraw"),
         ("1-8", "help.control.station_only")],
        ["help.note.damage_states", "help.note.destroyed", "help.note.sinking",
         "help.note.fire", "help.note.assignment"], "help.note.damage_tactic"),
    Station.OPZ: _station(
        "help.opz.intro",
        [("help.key.up_down", "help.control.cic_track"), ("C", "help.control.affiliation"),
         ("M", "help.control.designate"), ("help.key.page_spaced", "help.control.radar_range"),
         ("<- / ->", "help.control.asm_track"), ("E", "help.control.essm"),
         ("G", "help.control.chaff"), ("R", "help.control.surface_radar"),
         ("Shift+R", "help.control.air_radar")],
        ["help.note.radar", "help.note.ais_esm", "help.note.nato", "help.note.ciws",
         "help.note.jammer", "help.note.clutter", "help.note.chaff"],
        "help.note.air_defense"),
    Station.RADIO: _station(
        "help.radio.intro",
        [("help.key.up_down", "help.control.hfdf"), ("Enter", "help.control.log_bearing")],
        ["help.note.hfdf", "help.note.teletype", "help.note.hfdf_map"],
        "help.note.hfdf_tactic"),
    Station.ENGINE: _station(
        "help.engine.intro",
        [("+ / -", "help.control.engine"), ("help.key.up_down", "help.control.telegraph_up"),
         ("A", "help.control.quiet"), ("V", "help.control.speed_input")],
        ["help.note.cavitation", "help.note.engine_damage", "help.note.noise_range",
         "help.note.quiet"], "help.note.engine_tactic"),
    Station.HELICOPTER: _station(
        "help.helo.intro",
        [("H", "help.control.helo_toggle"), ("help.key.arrows", "help.control.waypoint"),
         ("M", "help.control.helo_target"), ("B", "help.control.drop_buoy"),
         ("D", "help.control.drop_torp"), ("Q / E", "help.control.zoom"),
         ("K", "help.control.follow")],
        ["help.note.helo_stores", "help.note.helo_fuel", "help.note.buoys",
         "help.note.helo_roe", "help.note.shared_controls"], "help.note.helo_tactic"),
}


def _translate_help(data, tr):
    intro, controls, notes, tactics = data
    return (tr(intro), [(tr(key), tr(action)) for key, action in controls],
            [tr(text) for text in notes], [tr(text) for text in tactics])


def get_global_help(tr=None) -> tuple:
    tr = tr or Translator("de").t
    title, controls = _GLOBAL_HELP
    return tr(title), [(tr(key), tr(action)) for key, action in controls]


# Compatibility for callers that display the historical German default.
GLOBAL_HELP = get_global_help()


def get_help(station: Station, tr=None) -> tuple:
    """Return localized station help from stable catalog keys."""
    tr = tr or Translator("de").t
    data = STATION_HELP.get(station, ("help.unknown_station", [], [], []))
    return _translate_help(data, tr)
