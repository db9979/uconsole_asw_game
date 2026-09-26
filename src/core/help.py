"""Catalog-keyed, context-sensitive help for all nine stations."""

from src.core.i18n import Translator
from src.core.station import Station


_GLOBAL_HELP = (
    "help.global.title",
    [
        ("Tab / Shift+Tab", "help.next_station"),
        ("1 / 2 / 3 / 4", "help.global.stations_1"),
        ("5 / 6 / 7 / 8", "help.global.stations_2"),
        ("9", "help.global.stations_3"),
        ("help.key.station_number", "help.repeat_station"),
        ("help.key.arrows", "help.station_control"),
        ("+ / -", "help.global.telegraph"),
        ("F1 / ?", "help.global.display"),
        ("F2", "help.global.autocrew_toggle"),
        ("F3", "help.global.autocrew_overview"),
        ("0", "help.global.weather_station"),
        ("F8", "help.global.analyzer"),
        ("F4", "help.global.simlog_view"),
        ("F9", "help.global.commander"),
        ("F10", "control.help.options"),
        ("F11", "help.global.feed_overlay"),
        ("N", "help.global.nations"),
        ("S / L", "help.save_load"),
        ("Alt+Enter", "help.fullscreen"),
        ("help.key.mouse_zoom", "help.global.map_zoom"),
        ("Drag", "help.global.map_pan"),
        ("K", "help.global.map_follow"),
        ("P", "help.global.plot"),
        ("help.key.plot_keys", "help.global.plot_keys"),
        ("Esc", "help.cancel"),
        ("R / M", "help.global.mission_end"),
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
        [("Shift+A", "help.control.active_ping"), ("Shift+B", "help.control.array"),
         ("Y", "help.control.tas"), ("help.key.page_spaced", "help.control.pages"),
         ("2", "help.control.repeat_sonar_page"), ("E", "help.control.bt"),
         ("W", "help.control.pulse"),
         ("U / V", "help.control.tas_depth"), ("R", "help.control.listen_input"),
         ("<- / ->", "help.control.bearing_step"), ("help.key.up_down", "help.control.contact_select"),
         ("Enter", "help.control.track_bearing"), ("J | , / .", "help.control.audio"),
         ("A / B / H", "help.control.audition_modes"),
         ("D", "help.control.filter"), ("I / O", "help.control.gain"),
          ("Shift+I / Shift+O", "help.control.display_contrast"),
          ("Ctrl+I / Ctrl+O", "help.control.display_black"),
          ("Shift+C", "help.control.display_palette"),
          ("Shift+H", "help.control.display_history"),
          ("F", "help.control.band"), ("N", "help.control.notch"),
          ("K", "help.control.harmonic"),
          ("Z / X", "help.control.sonar_cursor"),
          ("Ctrl+Z / Ctrl+X", "help.control.sonar_band_edges"),
          ("Q", "help.control.sonar_integration"),
          ("Shift+Q", "help.control.sonar_vernier"),
          ("Shift+N", "help.control.sonar_operator_notch"),
          ("Shift+F", "help.control.sonar_demon_band"),
          ("Ctrl+F", "help.control.sonar_heterodyne"),
          ("X / Shift+X (BB)", "help.control.tas_side"),
          ("Z / X (TMA)", "help.control.tma_course"),
          ("Ctrl+Z / Ctrl+X (TMA)", "help.control.tma_speed"),
          ("Q / Shift+Q (TMA)", "help.control.tma_range"),
          ("K / Shift+K (TMA)", "help.control.tma_accept"),
          ("SPACE", "help.control.peak"), ("T", "help.control.tma"),
          ("C", "help.control.classify"), ("G", "help.control.sonar_release"),
          ("M", "help.control.target")],
        ["help.note.passive", "help.note.tma", "help.note.waterfall",
         "help.note.audio_model", "help.note.demon", "help.note.gain",
         "help.note.snr", "help.note.shadow", "help.note.parallel",
         "help.note.ghost", "help.note.tas_handling", "help.note.tas_depth",
         "help.note.active"], "help.note.sonar_tactic"),
    Station.WEAPONS: _station(
        "help.weapons.intro",
        [("M", "help.control.target_from_sonar"), ("help.key.up_down_hold", "help.control.torp_depth"),
         ("<- / ->", "help.control.target_select"), ("T / Ctrl+Enter", "help.control.fire"),
          ("H", "help.control.helo_toggle"), ("B", "help.control.buoy"),
          ("D", "help.control.air_torp"), ("V", "help.control.nixie"),
          ("Q / E", "help.control.zoom"),
         ("K", "help.control.follow"), ("F", "help.control.flak_release")],
        ["help.note.roe", "help.note.target_depth", "help.note.salvo"],
        "help.note.weapon_tactic"),
    Station.DAMAGE: _station(
        "help.damage.intro",
        [("<- / ->", "help.control.compartment"), ("help.key.up_down", "help.control.team"),
         ("Enter", "help.control.assign"), ("Backspace", "help.control.withdraw"),
         ("1-9", "help.control.station_only"), ("control.help.click", "control.help.compartment")],
        ["help.note.damage_states", "help.note.destroyed", "help.note.sinking",
         "help.note.fire", "help.note.assignment"], "help.note.damage_tactic"),
    Station.OPZ: _station(
        "help.opz.intro",
        [("help.key.up_down", "help.control.cic_track"), ("C", "help.control.opz_classify"),
          ("F", "help.control.affiliation"),
          ("Shift+F", "help.control.opz_filter"),
          ("J", "help.control.opz_track_id"),
          ("Space / L / Shift+L", "help.control.opz_fusion"),
          ("Delete / H", "help.control.opz_suppress"),
          ("M", "help.control.designate"), ("help.key.page_spaced", "help.control.radar_range"),
         ("<- / ->", "help.control.asm_track"), ("E / Ctrl+Enter", "help.control.essm"),
          ("G", "help.control.chaff"), ("R", "help.control.surface_radar"),
          ("Shift+R", "help.control.air_radar"), ("I", "help.control.ciws_release"),
          ("Backspace", "help.control.opz_clear_marks"),
          ("Enter", "help.control.confirm_live_engage"),
          ("K", "help.control.follow")],
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
          ("A", "help.control.quiet"), ("U", "help.control.course_input"),
          ("V", "help.control.speed_input")],
        ["help.note.cavitation", "help.note.engine_damage", "help.note.noise_range",
         "help.note.quiet"], "help.note.engine_tactic"),
    Station.HELICOPTER: _station(
        "help.helo.intro",
        [("H", "help.control.helo_toggle"), ("help.key.arrows", "help.control.waypoint"),
          ("M", "help.control.helo_target"), ("B", "help.control.drop_buoy"),
          ("Shift+B", "help.control.buoy_mode"),
          ("T", "help.control.helo_source"), ("F", "help.control.helo_qualify"),
          ("C", "help.control.classify"),
          ("G / Shift+G", "help.control.helo_contact_release"),
          ("Y", "help.control.dip_toggle"), ("U / V", "help.control.dip_depth"),
          ("A", "help.control.dip_ping"),
          ("D / Ctrl+Enter", "help.control.drop_torp"), ("Q / E", "help.control.zoom"),
         ("K", "help.control.follow"),
          ("help.key.p3_pages", "help.control.helo_acoustic_pages"),
          ("help.key.p3_bearing", "help.control.helo_listen_bearing"),
          ("help.key.p3_reset", "help.control.helo_listen_reset"),
          ("help.key.p3_source", "help.control.helo_listen_source"),
          ("help.key.p3_audio", "help.control.audio"),
          ("help.key.p3_gain", "help.control.gain"),
          ("help.key.p3_notch", "help.control.notch"),
          ("help.key.p3_mode", "help.control.helo_audition_mode"),
          ("help.key.p3_band", "help.control.helo_band")],
        ["help.note.helo_stores", "help.note.helo_fuel", "help.note.buoys",
          "help.note.helo_roe", "help.note.shared_controls"], "help.note.helo_tactic"),
    Station.ELOKA: _station(
        "help.eloka.intro",
        [("help.key.up_down", "help.control.eloka_select"),
         ("F / Shift+F / B", "help.control.eloka_filters"),
         ("C", "help.control.eloka_annotation"),
         ("J", "help.control.eloka_jamming"),
         ("Shift+J", "help.control.eloka_technique"),
         ("A", "help.control.eloka_auto"),
         ("M", "help.control.eloka_audio")],
        ["help.note.eloka_passive", "help.note.eloka_candidates",
         "help.note.eloka_correlation", "help.note.eloka_damage"],
        "help.note.eloka_tactic"),
}


# Standard operating procedure per station: ordered catalog keys shared by the
# F1 station page and the player manual (``<!-- sop:<station> -->``).
_SOP_SLUGS = {
    Station.BRIDGE: "bridge", Station.SONAR: "sonar", Station.WEAPONS: "weapons",
    Station.DAMAGE: "damage", Station.OPZ: "opz", Station.RADIO: "radio",
    Station.ENGINE: "engine", Station.HELICOPTER: "helo", Station.ELOKA: "eloka",
}
STATION_SOP = {station: tuple(f"help.sop.{slug}.{step}" for step in range(1, 6))
               for station, slug in _SOP_SLUGS.items()}

# Remote Crew browser keys (``data/commander/js`` keydown handlers).
_WEB_HELP = (
    "help.web.title",
    [
        ("1-9", "help.web.station_select"),
        ("[ / ]", "help.web.station_step"),
        ("?", "help.web.guide"),
        ("help.key.arrows", "help.web.list_select"),
        ("Home / End", "help.web.list_ends"),
        ("+ / -", "help.web.map_zoom"),
        ("help.key.web_map_pan", "help.web.map_pan"),
        ("help.key.web_map_hover", "help.web.map_hover"),
        ("0", "help.web.weather_station"),
        ("help.key.web_plot", "help.web.plot"),
        (", / .", "help.web.docks"),
        ("L", "help.web.log"),
        ("Esc", "help.web.overlay_close"),
    ],
)


# The uConsole playing the hostile submarine (--play-sub / Options page 2).
_UBOOT_HELP = (
    "help.uboot.title",
    [
        ("1 / 2 / Tab", "help.uboot.views"),
        ("C / V / D", "help.uboot.orders"),
        ("help.key.page", "help.uboot.pages"),
        ("Q / E", "help.uboot.zoom"),
        ("K", "help.uboot.follow"),
        ("help.key.uboot_drag", "help.uboot.drag"),
        ("help.key.arrows", "help.uboot.contact"),
        ("help.key.uboot_fire", "help.uboot.fire"),
        ("F", "help.uboot.fire_bearing"),
        ("X", "help.uboot.decoy"),
        ("help.key.uboot_blow", "help.uboot.blow"),
        ("help.key.uboot_sonar", "help.uboot.sonar"),
        ("S / L / F9", "help.uboot.admin"),
    ],
)


def get_uboot_help(tr=None) -> tuple:
    """Return the localized key table of the local submarine side."""
    tr = tr or Translator("de").t
    title, controls = _UBOOT_HELP
    return tr(title), [(tr(key), tr(action)) for key, action in controls]


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


def get_sop(station: Station, tr=None) -> list:
    """Return the localized standard procedure steps for one station."""
    tr = tr or Translator("de").t
    return [tr(key) for key in STATION_SOP.get(station, ())]


def get_web_help(tr=None) -> tuple:
    """Return the localized Remote Crew browser key table."""
    tr = tr or Translator("de").t
    title, controls = _WEB_HELP
    return tr(title), [(tr(key), tr(action)) for key, action in controls]
