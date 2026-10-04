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
        ("help.key.page_spaced", "help.global.pages"),
        ("Ctrl+Enter", "help.global.fire"),
        ("help.key.arrows", "help.station_control"),
        ("+ / -", "help.global.telegraph"),
        ("F1 / ?", "help.global.display"),
        ("F2", "help.global.autocrew_toggle"),
        ("Shift+F2", "help.global.crew_assist"),
        ("F3", "help.global.autocrew_overview"),
        ("0", "help.global.weather_station"),
        ("F7", "help.global.advisor"),
        ("F8", "help.global.analyzer"),
        ("F4", "help.global.simlog_view"),
        ("F9", "help.global.commander"),
        ("F10", "control.help.options"),
        ("F11", "help.global.feed_overlay"),
        ("N", "help.global.nations"),
        ("help.key.save_load_opz", "help.save_load"),
        ("Alt+Enter", "help.fullscreen"),
        ("help.key.mouse_zoom", "help.global.map_zoom"),
        ("Drag", "help.global.map_pan"),
        ("K", "help.global.map_follow"),
        ("help.key.mouse_click", "help.global.mouse_click"),
        ("help.key.mouse_right", "help.global.mouse_right"),
        ("help.key.menu_icon", "help.global.menu_icon"),
        ("P", "help.global.plot"),
        ("help.key.plot_keys", "help.global.plot_keys"),
        ("Esc", "help.cancel"),
        ("R / M", "help.global.mission_end"), ("D", "help.global.debrief"),
    ],
)


def _station(intro, controls, notes, tactic):
    return intro, controls, notes, [tactic]


STATION_HELP = {
    Station.BRIDGE: _station(
        "help.bridge.intro",
        [("<- / ->", "help.control.rudder"), ("help.key.up_down", "help.control.telegraph_up"),
         ("C", "help.control.course_input"), ("V", "help.control.speed_input"),
         ("+ / -", "help.control.engine_order"), ("help.key.chart", "help.control.mouse_map"),
         ("Q / E", "help.control.zoom"), ("K", "help.control.follow"),
         (", / .", "help.bridge.lookout_range"), ("B", "help.bridge.lookout_glasses"),
         ("↑/↓ · ←/→ · Q/E · Space", "help.bridge.glasses_optics"),
         ("G", "help.control.action_stations"), ("W", "help.bridge.route_pattern"),
         ("help.key.route_click", "help.bridge.route_waypoint"),
         ("Backspace", "help.bridge.route_clear"), ("Ctrl+B", "help.bridge.clear_baffles")],
        ["help.note.bridge_noise", "help.note.bridge_coast", "help.note.crew"],
        "help.note.bridge_tactic"),
    Station.SONAR: _station(
        "help.sonar.intro",
        [("Shift+A", "help.control.active_ping"), ("Shift+B", "help.control.array"),
         ("Y", "help.control.tas"), ("Shift+Y", "help.control.vds"),
         ("help.key.page_spaced", "help.control.pages"),
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
          ("Shift+T (TMA)", "help.control.tma_method"),
          ("SPACE", "help.control.peak"), ("T", "help.control.tma"),
          ("C", "help.control.classify"), ("G", "help.control.sonar_release"),
          ("M", "help.control.target")],
        ["help.note.passive", "help.note.tma", "help.note.waterfall",
         "help.note.audio_model", "help.note.demon", "help.note.gain",
         "help.note.snr", "help.note.shadow", "help.note.parallel",
         "help.note.ghost", "help.note.tas_handling", "help.note.tas_depth",
         "help.note.vds", "help.note.active"], "help.note.sonar_tactic"),
    Station.WEAPONS: _station(
        "help.weapons.intro",
        [("M", "help.control.target_from_sonar"), ("help.key.up_down_hold", "help.control.torp_depth"),
         ("T", "help.control.torp_depth_input"),
         ("<- / ->", "help.control.target_select"), ("Ctrl+Enter", "help.control.fire"),
          ("W", "help.control.torp_type"), ("X", "help.control.torp_pattern"),
          (", / .", "help.control.torp_enable"), ("Y", "help.control.torp_salvo"),
          ("H", "help.control.helo_toggle"), ("B", "help.control.buoy"),
          ("D", "help.control.air_torp"), ("V", "help.control.nixie"),
          ("A", "help.control.asroc"), ("Z", "help.control.depth_charges"),
          ("R", "help.control.rbu"), ("Shift+R", "help.control.rbu_defence"),
          ("Q / E", "help.control.zoom"),
         ("K", "help.control.follow"), ("F", "help.control.flak_release")],
        ["help.note.roe", "help.note.target_depth", "help.note.salvo",
         "help.note.torp_types"],
        "help.note.weapon_tactic"),
    Station.DAMAGE: _station(
        "help.damage.intro",
        [("<- / ->", "help.control.compartment"), ("help.key.up_down", "help.control.team"),
         ("Enter", "help.control.assign"), ("Backspace", "help.control.withdraw"),
         ("C", "help.control.counterflood"),
         ("W", "help.control.watch_change"), ("G", "help.control.action_stations_crew"),
         ("M", "help.control.casualty_medic"), ("U", "help.control.casualty_reassign"),
         ("1-9", "help.control.station_only"), ("control.help.click", "control.help.compartment")],
        ["help.note.damage_states", "help.note.destroyed", "help.note.sinking",
         "help.note.fire", "help.note.assignment", "help.note.counterflood",
         "help.note.crew"],
        "help.note.damage_tactic"),
    Station.OPZ: _station(
        "help.opz.intro",
        [("help.key.up_down", "help.control.cic_track"), ("C", "help.control.opz_classify"),
          ("F", "help.control.affiliation"),
          ("Shift+F", "help.control.opz_filter"),
          ("J", "help.control.opz_track_id"),
          ("Space / L / Shift+L", "help.control.opz_fusion"),
          ("U / Shift+U", "help.control.opz_suggestion"),
          ("Delete / H", "help.control.opz_suppress"),
          ("M", "help.control.designate"), ("Q / E", "help.control.radar_range"),
         ("<- / ->", "help.control.asm_track"), ("Ctrl+Enter", "help.control.essm"),
          ("G", "help.control.chaff"), ("R", "help.control.surface_radar"),
          ("Shift+R", "help.control.air_radar"), ("I", "help.control.ciws_release"),
          ("Backspace", "help.control.opz_clear_marks"),
          ("B", "help.control.opz_blip"),
          ("Enter", "help.control.confirm_live_engage"),
          ("K", "help.control.follow"),
          ("H", "help.control.mpa_request"), ("W", "help.control.mpa_waypoint"),
          ("X / Shift+X", "help.control.mpa_pattern"), ("B", "help.control.mpa_buoy"),
          ("Shift+B", "help.control.mpa_buoy_mode"), ("Ctrl+R", "help.control.mpa_radar"),
          ("Shift+M", "help.control.mpa_mad"),
          ("D", "help.control.mpa_attack"),
          ("Y / F / H", "help.control.consort_orders"),
          ("X / W", "help.control.consort_point"),
          ("Shift+A", "help.control.consort_active"),
          ("Shift+W", "help.control.consort_weapons"),
          ("Ctrl+Enter", "help.control.consort_fire"),
          ("help.key.opz_display", "help.control.opz_display"),
          ("Backspace", "help.control.opz_display_reset_row"),
          ("Shift+Backspace", "help.control.opz_display_reset")],
        ["help.note.radar", "help.note.ais_esm", "help.note.nato", "help.note.ciws",
         "help.note.jammer", "help.note.clutter", "help.note.chaff", "help.note.mpa",
         "help.note.consort", "help.note.opz_display"],
        "help.note.air_defense"),
    Station.RADIO: _station(
        "help.radio.intro",
        [("help.key.up_down", "help.control.hfdf"), ("Enter", "help.control.log_bearing"),
         ("help.key.up_down", "help.control.task_select"),
         ("A / Enter", "help.control.task_accept"), ("D", "help.control.task_decline"),
         ("R", "help.control.ras_request"), ("K", "help.control.contact_report"),
         ("H", "help.control.request_support")],
        ["help.note.hfdf", "help.note.teletype", "help.note.hfdf_map", "help.note.hfdf_chart",
         "help.note.tasking"],
        "help.note.hfdf_tactic"),
    Station.ENGINE: _station(
        "help.engine.intro",
        [("+ / -", "help.control.engine"), ("help.key.up_down", "help.control.telegraph_up"),
          ("A", "help.control.quiet"), ("G", "help.control.plant"),
          ("C", "help.control.course_input"),
          ("V", "help.control.speed_input")],
        ["help.note.cavitation", "help.note.engine_damage", "help.note.noise_range",
         "help.note.quiet", "help.note.plant"], "help.note.engine_tactic"),
    Station.HELICOPTER: _station(
        "help.helo.intro",
        [("H", "help.control.helo_toggle"), ("help.key.arrows", "help.control.waypoint"),
          ("W", "help.control.helo_waypoint_contact"),
          ("M", "help.control.helo_target"), ("B", "help.control.drop_buoy"),
          ("Shift+B", "help.control.buoy_mode"),
          ("X", "help.control.buoy_pattern"), ("Shift+M", "help.control.mad"),
          ("Ctrl+R", "help.control.helo_radar"),
          ("Z", "help.control.helo_hoist"),
          ("T", "help.control.helo_source"), ("F", "help.control.helo_qualify"),
          ("C", "help.control.classify"),
          ("G", "help.control.helo_contact_release"),
          ("Shift+↑ / ↓", "help.control.helo_contact_select"),
          ("Y", "help.control.dip_toggle"), ("U / V", "help.control.dip_depth"),
          ("Shift+A", "help.control.dip_ping"),
          ("Ctrl+Enter / D", "help.control.drop_torp"), ("Q / E", "help.control.zoom"),
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
        ["help.note.helo_stores", "help.note.helo_console", "help.note.helo_fuel",
          "help.note.helo_rescue",
          "help.note.buoys",
          "help.note.buoy_patterns", "help.note.mad",
          "help.note.helo_roe", "help.note.shared_controls"], "help.note.helo_tactic"),
    Station.ELOKA: _station(
        "help.eloka.intro",
        [("help.key.up_down", "help.control.eloka_select"),
         ("F / Shift+F / Ctrl+F", "help.control.eloka_filters"),
         ("C", "help.control.eloka_annotation"),
         ("E", "help.control.eloka_jamming"),
         ("Shift+E", "help.control.eloka_technique"),
         ("A", "help.control.eloka_auto"),
         ("J", "help.control.eloka_audio")],
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
# The crewed submarine's stations (``uboot_local`` station ids) and their
# procedures (``help.sop.uboot.<slug>.*``, manual markers ``sop:uboot_<slug>``).
UBOOT_SOP_SLUGS = {"uboot": "command", "uboot_sonar": "sonar", "uboot_weapons": "weapons",
                   "uboot_engine": "engine", "uboot_esm": "esm", "uboot_nav": "nav",
                   "uboot_radio": "radio"}
UBOOT_SOP = {station: tuple(f"help.sop.uboot.{slug}.{step}" for step in range(1, 6))
             for station, slug in UBOOT_SOP_SLUGS.items()}

# Global keys while the uConsole plays the submarine (``uboot_local.handle_key``):
# only what works aboard (no F2/F3/F4/F8, N, P plot there).
_UBOOT_GLOBAL_HELP = (
    "help.uboot_global.title",
    [
        ("Tab / Shift+Tab", "help.next_station"),
        ("1 … 7", "help.uboot_global.stations"),
        ("help.key.station_number", "help.repeat_station"),
        ("help.key.page_spaced", "help.global.pages"),
        ("Ctrl+Enter", "help.uboot_global.fire"),
        ("Shift+A", "help.uboot_global.ping"),
        ("F1 / ?", "help.global.display"),
        ("Shift+F2", "help.global.crew_assist"),
        ("0", "help.uboot.weather"),
        ("F7", "help.global.advisor"),
        ("F9", "help.global.commander"),
        ("F10", "control.help.options"),
        ("F11", "help.global.feed_overlay"),
        ("S / L", "help.uboot_global.save_load"),
        ("Alt+Enter", "help.fullscreen"),
        ("Esc", "help.cancel"),
        ("R / M", "help.global.mission_end"), ("D", "help.global.debrief"),
    ],
)

# Main menu pages (``GameEventsMixin._handle_menu_key`` and the pages' own handlers).
_MENU_HELP = (
    "help.menu.title",
    [
        ("help.key.up_down", "help.menu.select"),
        ("Enter", "help.menu.enter"),
        ("Esc / Q", "help.menu.back"),
        ("help.key.page_spaced", "help.menu.page"),
        ("Home / End", "help.menu.ends"),
        ("W", "help.menu.world"),
        ("R", "help.menu.seed"),
        ("[ / ]", "help.menu.sector"),
        ("F", "help.menu.fullscreen"),
        ("← / → / Tab", "help.menu.logbook_side"),
        ("A", "help.menu.logbook_review"),
        ("B", "help.menu.logbook_report"),
        ("L", "help.menu.logbook_learns"),
        ("Enter / Esc", "help.menu.logbook_back"),
        ("F1 / F9", "help.menu.admin"),
    ],
)

# Remote Crew browser keys (``data/commander/js`` keydown handlers).
_WEB_HELP = (
    "help.web.title",
    [
        ("1-9", "help.web.station_select"),
        ("[ / ]", "help.web.station_step"),
        ("?", "help.web.guide"),
        ("help.key.arrows", "help.web.list_select"),
        ("Home / End", "help.web.list_ends"),
        ("+ / - · Q / E", "help.web.map_zoom"),
        ("help.key.web_map_pan", "help.web.map_pan"),
        ("help.key.web_map_hover", "help.web.map_hover"),
        ("0", "help.web.weather_station"),
        ("help.key.web_plot", "help.web.plot"),
        (", / .", "help.web.docks"),
        ("L", "help.web.log"),
        ("Esc", "help.web.overlay_close"),
    ],
)


# The uConsole playing the hostile submarine (new game "Hostile submarine", the lobby or Options page 2).
_UBOOT_HELP = (
    "help.uboot.title",
    [
        ("1 … 7 / Tab", "help.uboot.views"),
        ("C / V / D", "help.uboot.orders"),
        ("U / J / H", "help.uboot.presets"),
        ("help.key.page", "help.uboot.pages"),
        ("Q / E", "help.uboot.zoom"),
        ("K", "help.uboot.follow"),
        ("help.key.uboot_drag", "help.uboot.drag"),
        ("help.key.mouse_click", "help.uboot.pilot_click"),
        ("help.key.arrows", "help.uboot.contact"),
        ("help.key.uboot_fire", "help.uboot.fire"),
        ("F", "help.uboot.fire_bearing"),
        ("V", "help.uboot.decoy"),
        ("M", "help.uboot.tube_load"),
        ("Shift+M", "help.uboot.tube_flood"),
        ("Ctrl+M", "help.uboot.tube_flood_quiet"),
        ("help.key.uboot_blow", "help.uboot.blow"),
        ("T", "help.uboot.torpedo_depth"),
        ("Y", "help.uboot.salvo"),
        ("X", "help.uboot.torpedo_pattern"),
        (", / .", "help.uboot.torpedo_enable"),
        ("W", "help.uboot.wire_steer"),
        ("Shift+W", "help.uboot.wire_cut"),
        ("A", "help.uboot.silent"),
        ("Shift+A", "help.uboot_global.ping"),
        ("Shift+G", "help.uboot.bottom"),
        ("Shift+H", "help.uboot.surface"),
        ("H", "help.uboot.crash_dive"),
        ("N", "help.uboot.snorkel"),
        ("P", "help.uboot.mast"),
        ("help.key.arrows", "help.uboot.esm_select"),
        ("C / ← / →", "help.uboot.esm_classify"),
        ("help.key.enter", "help.uboot.esm_plot"),
        ("help.key.left_right", "help.uboot.scope_turn"),
        ("↑/↓ · Q/E · Space", "help.uboot.scope_optics"),
        ("help.key.enter", "help.uboot.stadimeter"),
        ("help.key.uboot_fire", "help.uboot.scope_fire"),
        ("+ / -", "help.uboot.telegraph"),
        ("help.key.uboot_sonar", "help.uboot.sonar"),
        ("R", "help.uboot.charge_rate"),
        ("Shift+O", "help.uboot.absorber"),
        ("O", "help.uboot.o2_candle"),
        ("help.key.arrows", "help.uboot.regulating"),
        ("help.key.left_right", "help.uboot.trim"),
        ("Z", "help.uboot.trim_auto"),
        ("help.key.arrows", "help.uboot.dc_select"),
        ("help.key.enter", "help.uboot.dc_team"),
        ("I", "help.uboot.dc_bulkhead"),
        ("I", "help.uboot.evade"),
        ("help.key.enter", "help.uboot.radio_send"),
        ("B", "help.uboot.buoy"),
        ("W", "help.uboot.watch_change"),
        ("M", "help.uboot.casualty_medic"),
        ("U", "help.uboot.casualty_reassign"),
        ("G", "help.uboot.action_stations"),
        ("Ctrl+B", "help.uboot.clear_baffles"),
        ("help.key.route_click", "help.uboot.route_waypoint"),
        ("W", "help.uboot.route_pattern"),
        ("Backspace", "help.uboot.route_clear"),
        ("0", "help.uboot.weather"),
        ("S / L / F9", "help.uboot.admin"),
        ("help.key.menu_icon", "help.global.menu_icon"),
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


def get_uboot_global_help(tr=None) -> tuple:
    """Return the localized global keys of the local submarine side."""
    tr = tr or Translator("de").t
    title, controls = _UBOOT_GLOBAL_HELP
    return tr(title), [(tr(key), tr(action)) for key, action in controls]


def get_menu_help(tr=None) -> tuple:
    """Return the localized keys of the main menu pages."""
    tr = tr or Translator("de").t
    title, controls = _MENU_HELP
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


def get_uboot_sop(station: str, tr=None) -> list:
    """Return the localized standard procedure of one submarine station."""
    tr = tr or Translator("de").t
    return [tr(key) for key in UBOOT_SOP.get(station, ())]


def get_web_help(tr=None) -> tuple:
    """Return the localized Remote Crew browser key table."""
    tr = tr or Translator("de").t
    title, controls = _WEB_HELP
    return tr(title), [(tr(key), tr(action)) for key, action in controls]
