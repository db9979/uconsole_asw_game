"""Haupt-Game-Loop: Widescreen-Grid, Echtzeit, Szenarien und Multi-Slot-Save."""

import copy
import hashlib
import json
import math
import os
import threading
import time
import weakref
from collections import deque
from contextlib import contextmanager
from dataclasses import replace
from types import SimpleNamespace

import pygame

from src.audio.engine import AudioEngine
from src.audio.receiver import AcousticReceiver
from src.audio.preview import unit_sonar_preview
from src.commander.local import CommanderConsole
from src.core import config
from src.core import detrand
from src.core import plot as plot_geometry
from src.core.plot import PlotLayer
from src.core.autocrew import AutocrewController, station_key
from src.core.commands import MAP_STATIONS, STATION_PAGES, station_page_step, toggle_tas
from src.core.debuglog import append_bounded_log
from src.core.i18n import (Translator, display_value, localized, localize,
                           message, raw_text, translation_scope)
from src.core.preferences import Preferences, save_preferences
from src.network.adsb_client import test_connection as adsb_test_connection
from src.network.ais_client import test_connection as ais_test_connection
from src.network.connectivity import ConnectivityMonitor
from src.network.live_traffic import LiveTrafficManager
from src.core.help import get_global_help, get_help, get_sop, get_uboot_help
from src.core import manual
from src.core.mission import Mission
from src.core.mission_definition import static_preview, validate_mission
from src.core.station import Station
from src.core import opfor
from src.core import uboot_local
from src.core.limits import (MAX_AIR_PICTURE_TRACKS, MAX_DECOYS, MAX_ENEMY_TORPEDOES,
                             MAX_OPZ_TRACK_LABELS, MAX_SAVED_ASMS, MAX_SAVED_ENTITIES,
                             MAX_SAVED_ESSMS, MAX_SAVED_PLAYER_TORPEDOES,
                             MAX_TRACK_DISPLAY_ID_LEN)
from src.sensors.ais import AISReceiver
from src.sensors import radar as radar_physics
from src.sensors import visual as visual_physics
from src.sensors import lookout_id
from src.sensors import threat_cue
from src.world import atmosphere as atmosphere_physics
from src.world import ocean as ocean_physics
from src.sonar import raytrace as sonar_raytrace
from src.sonar import analysis_tools
from src.sonar import tma_operator
from src.sensors import hfdf as hf_physics
from src.sonar import equation as sonar_equation
from src.sonar import propagation as sonar_propagation
from src.physics import torpedo_dyn
from src.physics import ship_dynamics
from src.weapons import ciws as ciws_physics
from src.sensors.platform import MAST_DEPTH_M
from src.data.catalog import CATALOG, EmitterProfile
from src.enemies.animal import Animal
from src.enemies.civilian import CivilianShip
from src.enemies.decoy import Decoy
from src.enemies.sub import Sub
from src.enemies.surface import SurfaceShip
from src.nations.nations import reference_summary
from src.sensors.tracks import TrackPicture
from src.sensors.fusion import OPZFusionPicture, OPZObservation, source_classification
from src.sensors.esm import (
    ESM_MAX_ANNOTATIONS,
    ESMCorrelationEvidence,
    ECM_SIGNAL_FRESH_S,
    ECM_TECHNIQUES,
    ECMJammer,
    ESMMeasurement,
    ESMPicture,
    RadarSuiteController,
    scan_for_signals,
    analyze_signal,
    correlate_observations,
    estimated_range_nm,
    filter_and_sort_tracks,
    library_emitters,
    rank_emitters)
from src.sensors.platform import exchange_friendly_datalink, snapshot_observation
from src.ship.damage import DamageModel
from src.ship.ship import Ship
from src.sonar.sonar import Contact, SonarSystem, TowState
from src.sonar.station import SonarStation, install_station_properties
from src.ui import layout
from src.ui import observations
from src.ui.editor_widgets import TextField
from src.ui.feedback import EventFeed
from src.ui.map_view import draw_map_view, map_hit_target
from src.ui.splash_view import SPLASH_PING_PERIOD_S, draw_splash
from src.ui.sonar_view import draw_sonar_view, sonar_click_target, sonar_hit_target
from src.ui.weather_station import draw_weather_station
from src.ui import uboot_view
from src.ui.stations_view import (draw_autocrew_overview, draw_bridge_view,
                                  draw_damage_view, draw_eloka_view,
                                  draw_engine_view, draw_opz_view,
                                  draw_radio_view,
                                   draw_helicopter_view, station_hit_target)
from src.ui.stations_view import (damage_compartment_at, eloka_track_at,
                                    helicopter_acoustic_hit, opz_action_at, opz_ppi_rect,
                                    station_page_tab_at)
from src.ui.mission_editor import MissionEditor
from src.ui.unit_editor import UnitEditor, catalog_builtins
from src.ui.contact_analyzer import ContactAnalyzer
from src.ui import simlog_map
from src.ui.simlog_view import draw_simlog_view
from src.ui.viewport import Viewport
from src.ui.weapons_view import (draw_weapons_overlay, draw_weapons_panel,
                                 weapons_hit_target)
from src.air.asm import ASM, ESSM
from src.air import chaff as chaff_physics
from src.air.helicopter import Helicopter
from src.air import helicopter as helicopter_physics
from src.air.flights import Flight, FlightManager
from src.air.raid import Raider
from src.world.world import World
from src.world.coastline import Coastline
from src.weapons.torpedo import EnemyTorpedo, Torpedo
from src.weapons.asw import (
    ASROC,
    ConsumableStore,
    MAX_ASROCS,
    MAX_TOWED_DECOYS,
    TowedAcousticDecoy,
    WeaponBattery,
    ownship_loadout)
from src.weapons.air_defense import air_defense_loadout, make_softkill_store
# Names tests and tools import from ``src.core.game`` (kept as re-exports).
from src.core.save_schema import SAVE_ROOT_FIELDS  # noqa: F401
from src.core.game_save import (
    SaveMixin,
    _read_save_document,
    _valid_difficulty_dict,
    _same_save_value,
    _same_save_value_strict,
    MAX_SAVE_DOCUMENT_BYTES)


# F1 overlay categories: global keys, station, sensors/tactics, manual reader.
HELP_PAGE_COUNT = 4
HELP_MANUAL_PAGE = 3
# Operator TMA: the residuals must show no systematic trend beyond the
# averaged bearing noise before a hypothesis can be accepted as a fix.
TMA_ACCEPT_MIN_FIT = 0.3
# Operator sonar classification -> published track kind (domain symbol).
SONAR_CLASS_KINDS = {
    "U_BOOT": "SUB",
    "KAMPFSCHIFF": "SURFACE",
    "FAHRZEUG": "SURFACE",
    "TORPEDO": "TORP",
}
SONAR_BAND_PRESETS = {
    "FULL": (0.0, 300.0),
    "LOW": (4.0, 80.0),
    "SHAFT": (8.0, 55.0),
    "MID": (20.0, 120.0),
}


def letterbox_layout(win_w: int, win_h: int,
                     base_w: int = config.SCREEN_W,
                     base_h: int = config.SCREEN_H) -> tuple:
    """Aspect-correcte Anordnung des virtuellen Canvas im Fenster."""
    scale = min(win_w / base_w, win_h / base_h)
    sw, sh = int(base_w * scale), int(base_h * scale)
    return scale, (win_w - sw) // 2, (win_h - sh) // 2, sw, sh


def make_scanlines(w: int, h: int, alpha: int = config.SCANLINE_ALPHA):
    """Vorberechnetes CRT-Scanline-Overlay (einmalig, SRCALPHA)."""
    s = pygame.Surface((w, h), pygame.SRCALPHA)
    for y in range(0, h, 3):
        s.fill((0, 0, 0, alpha), (0, y, w, 1))
    return s


def make_night_overlay(w: int, h: int, color: tuple = config.NIGHT_MODE_COLOR):
    """W2: Rotlicht-Nachtsicht - Multiply-Blend unterdrückt Grün/Blau,
    Rotanteil bleibt (Nachtsichtschutz an Bord)."""
    s = pygame.Surface((w, h))
    s.fill(color)
    return s


# Input and window changes redraw an eco frame at once; pointer motion does not.
_ECO_REFRESH_EVENTS = frozenset(
    getattr(pygame, name) for name in (
        "KEYDOWN", "MOUSEBUTTONDOWN", "VIDEOEXPOSE", "VIDEORESIZE", "WINDOWSHOWN",
        "WINDOWEXPOSED", "WINDOWRESIZED", "WINDOWSIZECHANGED", "WINDOWRESTORED",
        "WINDOWFOCUSGAINED", "WINDOWFOCUSLOST") if hasattr(pygame, name))


TORPEDO_WAKE_VISIBLE_NM = 1.5
TORPEDO_WAKE_VISIBLE_DEPTH_M = 15.0
# Close-in weapon system: own Ku-band search/track radar that keeps an
# inbound missile under continuous track inside this range.
CIWS_TRACK_RANGE_NM = 3.0
# Koschmieder lookout model anchored to the 1.0.0 day/calm/clear ranges.
LOOKOUT_MODEL = visual_physics.LookoutModel(
    {"SURFACE": config.LOOKOUT_SURFACE_RANGE_NM, "SUB": config.LOOKOUT_SUB_RANGE_NM,
     "FLG": config.LOOKOUT_AIR_RANGE_NM, "TORP": TORPEDO_WAKE_VISIBLE_NM,
     "LAND": config.LOOKOUT_LAND_RANGE_NM},
    config.WEATHER_VISIBILITY_MAX_NM)


class Game(SaveMixin):
    # Options overlay rows in display order; the last two open sub-menus.
    _OPTION_ROWS = ("language", "fullscreen", "audio", "large_text", "tooltips",
                    "simlog", "night_mode", "high_contrast", "frame_rate",
                    "bottom_panel", "operator_assist", "live_traffic", "commander")
    # Second options page: game setup.  The local side is per launch and never
    # persisted (the frigate is always the default).
    _OPTION_ROWS_SETUP = ("local_side",)
    _OPTION_PAGES = (_OPTION_ROWS, _OPTION_ROWS_SETUP)

    def __init__(self, seed: int = 42, difficulty: dict = None,
                  start_menu: bool = False, fullscreen: bool = None,
                 window_size: tuple = None, show_splash: bool = False,
                  audio_enabled: bool = None, preferences: Preferences = None,
                  language: str = None, web_mode: bool = False):
        self.web_mode = bool(web_mode)
        if self.web_mode:
            os.environ["SDL_VIDEODRIVER"] = "dummy"
            os.environ["SDL_AUDIODRIVER"] = "dummy"
        requested_fullscreen = (preferences.fullscreen
                                if preferences is not None and fullscreen is None
                                else bool(fullscreen))
        requested_audio = (preferences.audio
                           if preferences is not None and audio_enabled is None
                           else (config.AUDIO_ENABLED if audio_enabled is None
                                 else bool(audio_enabled)))
        if self.web_mode:
            requested_audio = False
        self.preferences = preferences or Preferences(
            language=language or Preferences.defaults().language,
            fullscreen=requested_fullscreen, audio=requested_audio)
        if language is not None and language != self.preferences.language:
            from dataclasses import replace
            self.preferences = replace(self.preferences, language=language)
        self.translator = Translator(self.preferences.language)
        self.tr = self.translator.t
        pygame.mixer.pre_init(frequency=config.AUDIO_SAMPLE_RATE, size=-16,
                              channels=config.AUDIO_CHANNELS,
                              buffer=config.AUDIO_MIXER_BUFFER_SAMPLES)
        pygame.init()
        self._joysticks = {}
        if pygame.joystick.get_init():
            for index in range(pygame.joystick.get_count()):
                self._open_joystick(index)
        pygame.display.set_caption(self.tr("app.title"))
        if requested_fullscreen:
            # Echtes Vollbild: (0,0)+FULLSCREEN laesst SDL die native
            # Desktop-Aufloesung waehlen -> deckt Taskleiste ab, keine
            # schwarzen Balken. FILL_SCREEN streckt den virtuellen
            # 1280x720-Canvas danach auf die volle Flaeche.
            self.display = pygame.display.set_mode((0, 0), pygame.FULLSCREEN)
            self.fullscreen = True
        else:
            size = tuple(window_size) if window_size else (
                config.SCREEN_W, config.SCREEN_H)
            self.display = pygame.display.set_mode(size, pygame.RESIZABLE)
            self.fullscreen = False
        self.screen = pygame.Surface((config.SCREEN_W, config.SCREEN_H))
        self._scanlines = make_scanlines(config.SCREEN_W, config.SCREEN_H) \
            if config.CRT_SCANLINES else None
        self._night_overlay = make_night_overlay(config.SCREEN_W, config.SCREEN_H)
        self.clock = pygame.time.Clock()
        self.audio = AudioEngine(sample_rate=config.AUDIO_SAMPLE_RATE,
                                 enabled=requested_audio)
        self._audio_timer = 0.0
        self._perf_debug_enabled = (
            os.environ.get("U_JAGD_PERF_DEBUG", "") not in ("", "0"))
        self._perf_debug_due = 0.0
        self._perf_frames = 0
        self._perf_sim_s = 0.0
        self._perf_substeps = 0
        self._perf_audio_s = 0.0
        self._perf_commander_s = 0.0
        self._perf_commander_max_s = 0.0
        self._perf_events_s = 0.0
        self._perf_traffic_s = 0.0
        self._perf_draw_s = 0.0
        self._perf_frame_max_s = 0.0
        self._sim_debt_s = 0.0
        self._sim_dropped_s = 0.0
        self._frame_clock_reset = True
        self._sound_event_seq = 0
        self._sound_events = deque(maxlen=16)
        # Pulse type per transmission time, for the echo sound only (audio,
        # never saved; after a load the current pulse is used).
        self._ping_pulses = {}
        self._eco_drawn_at = float("-inf")
        self._sensor_acc = 0.0
        self._esm_acc = 0.0
        self._radio_acc = 0.0
        self._slow_acc = 0.0
        self._apply_text_size()
        self.level = "custom"
        self.menu_difficulty = (dict(difficulty) if difficulty
                                and _valid_difficulty_dict(difficulty)
                                else dict(config.DEFAULT_DIFFICULTY))
        # Free-hunt choice for the start report; fixed scenarios set their own.
        self.menu_hq_intel = "coarse"
        self.in_menu = start_menu
        self.menu_sel = 0  # Index in DIFFICULTY_FIELD_ORDER or SCENARIO_ORDER
        self.seed = seed
        self.world_mode = "procedural"
        # W4: Szenario-Auswahl im Hauptmenü
        self.scenario_key = "s1_patrouille"
        self.menu_screen = "scenario"  # "scenario" | "difficulty" | "briefing"
        self.main_menu = bool(start_menu)
        self.main_menu_sel = 0
        self.editor = None
        self.simlog_view_open = False
        self.simlog_view_scroll = 0
        self.simlog_view_map = False
        self.simlog_map_fit = simlog_map.FIT_WORLD
        self.options_open = False
        self.options_sel = 0
        self.options_page = 0
        self.commander = CommanderConsole()
        self.commander_open = False
        self.live_traffic = LiveTrafficManager()
        self.connectivity = ConnectivityMonitor()
        self.live_traffic_open = False
        self.live_traffic_sel = 0
        self.live_traffic_field: TextField | None = None
        self.live_traffic_field_name: str | None = None
        # ("idle" | "running" | "ok" | "no_key" | "error", fehlertext | None)
        self.live_traffic_test_result: dict[str, tuple[str, str | None]] = {
            "ais": ("idle", None), "adsb": ("idle", None)}
        self._live_traffic_test_thread: threading.Thread | None = None
        self.menu_back = False
        # W0: neue UI-Zustände
        self.help_open = False
        self.nations_open = False
        self.quit_confirm = False
        self.save_ui = None  # None | "save" | "load"
        self.save_slot = 1
        self._map_drag = None
        self._map_drag_moved = False
        self.map_follow = True
        self.opz_map_follow = True
        # Which side the uConsole plays: "frigate", or "uboot" with the
        # frigate left to Remote Crew/autocrew.  Chosen in the menu, kept by
        # a save (v15 ``ui.local_side``) so a load resumes the same seat.
        self.local_side = "frigate"
        self._opfor_hold_s = 0.0
        self._uboot_dispatch = False
        self._uboot_ui = False
        self._uboot_chart_drag = None
        self.reset(seed)
        self.splash_active = bool(show_splash)
        self.splash_started_at = self._t
        self._splash_ping_cycle = -1

    def _apply_text_size(self) -> None:
        layout.configure_for(self)
        self.font = layout.font(18)
        self.font_big = layout.font(28, bold=True)
        # Menus get a larger baseline than in-game HUD text: more free
        # space per screen, and no risk to the already-tuned station views
        # that also read `self.font`/`self.font_big`.
        self.menu_font = layout.font(21)
        self.menu_font_big = layout.font(34, bold=True)

    @property
    def radar_range_nm(self) -> float:
        return self.opz_range_nm

    @radar_range_nm.setter
    def radar_range_nm(self, value: float) -> None:
        self.opz_range_nm = value

    # --- sonar workstations: frigate and crewed submarine ------------------

    @contextmanager
    def sonar_perspective(self, station):
        """Temporarily make ``station`` the active sonar workstation.

        Operator methods (``set_sonar_*``, TMA, classification ...), the sonar
        projections and the sonar view then act on that station's system and
        observer.  Only use it on the main thread, around one command, one
        projection or one draw call.
        """
        previous = self._sonar_ctx
        self._sonar_ctx = station
        try:
            yield station
        finally:
            self._sonar_ctx = previous

    @property
    def sonar_station(self):
        return self._sonar_ctx

    @property
    def sonar_observer(self):
        """The listening platform of the active sonar workstation."""
        observer = self._sonar_ctx.observer
        return self.ship if observer is None else observer

    def _sonar_down(self) -> bool:
        down = self._sonar_ctx.down
        return self.damage.station_down("sonar") if down is None else bool(down())

    def _sonar_notice(self, notice, seconds: float = 2.0) -> None:
        """Operator feedback of the active workstation, never across sides."""
        if self._sonar_ctx is self._frigate_sonar:
            self.flash(notice, seconds)
            self.feed.add(self.world.format_time(), "sonar", notice)
        elif self._opfor is not None and self._sonar_ctx is self._opfor.station:
            self._opfor.notice(self.sim_t, "sonar", notice,
                               stamp=self.world.format_time())

    # --- crewed hostile submarine (Remote Crew ``uboot`` roles) ------------

    @property
    def opfor(self):
        """The crewed submarine binding, or None."""
        return self._opfor

    def claim_opfor_sub(self):
        """Bind (or keep) the crewed submarine; the AI stops commanding it."""
        boat = self._opfor
        if boat is not None and boat.sub in self.subs:
            return boat
        sub = opfor.choose_boat(self)
        if sub is None:
            self._opfor = None
            return None
        sub.claim_manual()
        self._opfor = opfor.CrewedBoat(sub, self.runtime_catalog)
        return self._opfor

    def release_opfor_sub(self) -> None:
        """Hand the crewed submarine back to the AI."""
        boat = self._opfor
        self._opfor = None
        if boat is not None and boat.sub in self.subs and not boat.sub.sunk:
            boat.sub.release_manual()

    def reset(self, seed: int, scenario_key: str = None, *, publish_intel: bool = True) -> None:
        """Spielzustand neu aufbauen (Start/Neustart).

        W4: Szenario (config.SCENARIOS) legt Level, Missionstyp und
        Startposition fest. s4_zufall = seed-basiert wie vor dem Refactor.
        """
        import random
        # The frigate's sonar workstation; ``game.sonar`` & co. delegate to it.
        self._frigate_sonar = SonarStation(kind="frigate")
        self._sonar_ctx = self._frigate_sonar
        # A crewed hostile submarine (save v15 ``crew``); the hold keeps a
        # loaded binding until its crew returns or the AI takes the boat back.
        self._opfor = None
        self._opfor_hold_s = 0.0
        self.runtime_catalog = CATALOG
        self.commander_open = False
        self.audio.stop()
        self._frame_clock_reset = True
        self._sound_events.clear()
        self._ping_pulses.clear()
        self._sonar_audio_sequence = -1
        scenario_key = scenario_key or self.scenario_key
        if scenario_key not in config.SCENARIOS:
            scenario_key = "s4_zufall"
        sc = config.SCENARIOS[scenario_key]
        self.scenario_key = scenario_key
        self.difficulty = {**config.DEFAULT_DIFFICULTY,
                           **(sc["difficulty"] if sc["difficulty"] is not None
                              else self.menu_difficulty)}
        self.level = "custom"

        coast = Coastline.load() if self.world_mode == "fixed" else None
        self.world = World(seed=seed, coast=coast)
        if sc["difficulty"] is None:
            self.world.sea_state = int(self.difficulty["sea_state_start"])
            self.world.refresh_weather()
        start = sc["ship_start"] or (250.0, 250.0)
        course = sc["ship_course"]
        if course is None:
            course = 90.0
        sx, sy = self.world.nearest_safe_hull(start[0], start[1], course)
        self.ship = Ship(x_nm=sx, y_nm=sy, course_deg=course)
        self.live_traffic.configure(self, self.world, self.preferences)
        self.sonar = SonarSystem(
            seed=seed, acoustic_profiles=self.runtime_catalog.acoustic_profiles)
        self._last_tow_state = self.sonar.tow_state
        rng = random.Random(seed)
        self.rng_world = rng  # Phase 2: geteilt mit allen Entitäten (Save/Load)
        self.rng_asw = random.Random(seed + 27182)
        self.seed = seed
        self.sim_t = 0.0
        self._sensor_acc = 0.0
        self._esm_acc = 0.0
        self._radio_acc = 0.0
        self._slow_acc = 0.0
        self.simlog = deque(maxlen=config.SIMLOG_MAX_ENTRIES)
        self._simlog_seq = 0
        self._simlog_acc = 0.0
        self.feed = EventFeed(sink=self._record_simlog)

        # M6: Mission (W4: Szenario kann den Typ fixieren)
        self.mission = Mission(seed, type_key=sc["mission_type"],
                               difficulty=self.difficulty)
        self.custom_mission_definition = None
        self.mission_time = 0.0
        self.score = 0
        self.mission_result = None   # None | "SIEG" | "VERLOREN"
        self.result_reason = ""

        def at_dist(min_nm, max_nm):
            ang = rng.uniform(0, 360)
            dist = rng.uniform(min_nm, max_nm)
            x = config.clamp(
                self.ship.x + dist * math.cos(math.radians(ang)),
                5.0, self.world.size_nm - 5.0)
            y = config.clamp(
                self.ship.y + dist * math.sin(math.radians(ang)),
                5.0, self.world.size_nm - 5.0)
            return self.world.nearest_water(x, y)  # W3: nie in Land spawnen

        # U-Boote laut Mission + Custom-Difficulty (second_sub_prob -> Bonus-Boot)
        lv = self.difficulty
        plan = list(self.mission.sub_types)
        if (len(plan) < 3 and lv["second_sub_prob"] > 0.0
                and rng.random() < lv["second_sub_prob"]):
            plan.append(rng.choice(config.SECOND_SUB_POOL))
        self.subs = []
        for i, stype in enumerate(plan):
            min_d, max_d = (12.0, 20.0) if i == 0 else (22.0, 45.0)
            sx, sy = at_dist(min_d, max_d)
            s = Sub(sx, sy,
                    depth_m=rng.uniform(40.0, min(
                        100.0, self.runtime_catalog.subs[stype].max_depth_m * 0.5)),
                    course_deg=rng.uniform(0, 360), stype_key=stype, rng=rng,
                    quiet_mult=lv["quiet_mult"],
                    attack_mult=lv["enemy_attack_mult"],
                    attack_cooldown_s=lv["enemy_cooldown_s"],
                    profile=self.runtime_catalog.subs[stype],
                    decoy_profile=self.runtime_catalog.decoys[
                        self.runtime_catalog.runtime_bindings["submarine_decoy"]],
                     enemy_torpedo_profile=self.runtime_catalog.torpedoes[
                         self.runtime_catalog.runtime_bindings["enemy_torpedo"]],
                    side="hostile", runtime_catalog=self.runtime_catalog,
                    asw_rng=self.rng_asw)
            self.subs.append(s)

        # Meerestiere (M4): Falschkontakte
        self.animals = []
        for _ in range(self.mission.animal_count):
            ax, ay = at_dist(15.0, 90.0)
            animal_key = rng.choice(["whale", "fish_school", "jellyfish"])
            self.animals.append(Animal(
                ax, ay, animal_key, rng=rng,
                profile=self.runtime_catalog.animals[animal_key]))

        # Zivile Schiffe (M4): AIS + Radar, jetzt auch passive Sonarkontakte
        self.civilians = []
        for _ in range(self.mission.civilian_count):
            cx, cy = at_dist(20.0, 100.0)
            self.civilians.append(CivilianShip(
                cx, cy, rng=rng,
                profile=self.runtime_catalog.pick_surface(rng, hostile=False),
                side="neutral", doctrine="surface_transit",
                runtime_catalog=self.runtime_catalog))

        # KAMPFSCHIFF (Kontakt-DB): feindliche Kriegsschiffe loiteren um
        # die feindliche Basis und feuern ASM, wenn die Fregatte naehert.
        self.warships = []
        self.warship_anchor = None
        base = self.world.coast.hostile_base()
        if base is not None and self.mission.warship_count > 0:
            bx, by = self.world.nearest_water(
                base["x"] + rng.uniform(-30.0, 30.0),
                base["y"] + rng.uniform(-30.0, 30.0))
            self.warship_anchor = (bx, by)
            for _ in range(self.mission.warship_count):
                angle = rng.uniform(0.0, math.tau)
                radius = rng.uniform(8.0, 18.0)
                wx, wy = self.world.nearest_water(
                    bx + math.cos(angle) * radius,
                    by + math.sin(angle) * radius)
                w = SurfaceShip(
                    wx, wy, rng=rng, hostile=True,
                    profile=self.runtime_catalog.pick_surface(rng, hostile=True),
                    side="hostile", doctrine="surface_combatant",
                    runtime_catalog=self.runtime_catalog)
                w.anchor = self.warship_anchor
                self.warships.append(w)

        # W2: Akustische Dekoys (werden bei Torpedo-Alarm abgeworfen)
        self.decoys = []
        self.incident = False
        self.station = Station.BRIDGE
        self.autocrew = AutocrewController()
        self.autocrew_overview_open = False
        self.weather_station_open = False
        # F11 event history/telemetry overlay: display only, never an input
        # owner, so every station stays operable underneath it.
        self.feed_overlay_open = False
        self.feed_overlay_scroll = 0
        self.running = True
        self.simlog_view_open = False
        self.simlog_view_scroll = 0
        self.simlog_view_map = False
        self.simlog_map_fit = simlog_map.FIT_WORLD
        self.held = set()
        self._map_drag = None
        self._map_drag_moved = False
        # Waffenzentrale (M3, Munitionsbestand aus Custom-Difficulty)
        self._ownship_loadout = copy.deepcopy(ownship_loadout())
        self.player_torpedo_battery = WeaponBattery.ownship(
            int(self.difficulty["torpedo_count"]), self._ownship_loadout)
        self.torpedo_total = self.player_torpedo_battery.capacity_total
        self.torpedo_count = self.player_torpedo_battery.remaining_total
        self.torpedo_depth = 60.0
        self.target = None
        self.selected_contact = None  # M9: im Sonar-Panel markierter Kontakt
        self.torpedoes = []
        self.torpedo_seq = 0
        self.asrocs = []
        self.asroc_seq = 0
        self.nixie_store = ConsumableStore.ownship(self._ownship_loadout)
        self.nixies = []
        self.nixie_seq = 0
        self.msg = ""
        self.msg_until = 0.0
        self.input_mode = None       # "course" or "speed"
        self.input_buffer = ""
        self._t = 0.0
        self.auto_quit = None  # Test-Hook: Frames bis Auto-Ende
        # M5: Schadensmodell + Gegentorpedos (Reparatur-Faktor aus Custom-Difficulty)
        self.damage = DamageModel(random.Random(seed + 777),
                                  repair_mult=self.difficulty["repair_mult"])
        self.enemy_torpedoes = []
        # Presentation-only torpedo intercept memory (see _update_torpedo_cues);
        # rebuilt from the saved torpedo state on load, never saved itself.
        self.torpedo_cues = []
        self._torpedo_cues_reported = weakref.WeakKeyDictionary()
        self.game_over = False
        # M10–M16
        self.sonar_mode = "BOW"                      # "BOW" | "TOWED"
        self.sonar_page = 0
        self.station_page = 0
        self.lookout_range_nm = 12.0                 # bridge lookout page scale (UI only)
        self.helo_acoustic_page = 1
        self.sonar_harmonic_hz = None
        # Operator LOFAR/DEMON tools: cursor, marks, integration (UI only).
        self.sonar_tools = analysis_tools.AcousticToolState()
        # Operator TMA hypotheses per sonar target (transient UI state).
        self.tma_hypotheses = {}
        # Shared operator plot layer (chart marks, rulers, bearing lines...).
        self.plot = PlotLayer()
        self._reset_plot_ui()
        # Display-only CRT controls are intentionally transient: they affect no
        # observation, simulation or v10 save contract.
        self.sonar_display_palette = "green"
        self.sonar_display_black = 0.0
        self.sonar_display_contrast = 1.6
        self.sonar_display_history = 1.0
        self.sonar_audio_enabled = True
        self.helo_audio_enabled = True
        self.sonar_volume = 0.5
        self._sonar_audio_sequence = -1
        self._sonar_audio_suspended = False
        # Local ESM cues belong to the ELOKA workstation.  The browser receives
        # the detached event separately and applies its own role/audio gate.
        self.eloka_audio_enabled = True
        self.surface_radar_on = config.RADAR_ON_DEFAULT
        self.air_radar_on = config.RADAR_ON_DEFAULT
        self.opz_range_nm = config.RADAR_RANGE_DEFAULT_NM
        self.roe = config.ROE_DEFAULT                # "STD" | "FREE"
        self.messages: list = []                     # Funkraum-Teletype
        self._reset_lookout_reports()
        self.dmg_cursor = 0
        self.dmg_team = 1
        self.helo = Helicopter(
            random.Random(seed + 555), self.runtime_catalog.torpedoes[
                self.runtime_catalog.runtime_bindings["helicopter_torpedo"]])
        self.buoys = []
        self.buoy_seq = 0
        self.helo_buoy_mode = "PASSIVE"
        self.helo_sensor_source = "DIP"
        self.helo_listen_source = "DIP"
        self.helo_listen_bearing = None
        self.helo_audio_band = "FULL"
        self.helo_audition = SonarSystem(seed=seed + 45678, acoustic_profiles=())
        self.helo_receiver = AcousticReceiver(seed=seed + 45677)
        self.helo_spectra = []
        self.helo_broadband_history = []
        self.helo_demon_history = []
        self._helo_receiver_timer = 0.0
        self.asms = []
        self.essms = []
        self._air_defense_loadout = copy.deepcopy(air_defense_loadout())
        self.asm_speed_kn = self._air_defense_loadout["asm"]["speed_kn"]
        self.vls_loadout_total = self._air_defense_loadout["vls"]["sam_loadout"]
        self.vls_cells = self._air_defense_loadout["vls"]["sam_loadout"]
        self.essm_seq = 0
        self.softkill_store = make_softkill_store(self._air_defense_loadout)
        self.chaff_cd = 0.0
        self.chaff_clouds: list = []
        self.chaff_seq = 0
        self.ciws_mount_deg = 0.0
        self.rng_asm = random.Random(seed + 31337)
        self.asm_spawned = 0
        self.asm_seq = 0
        self.air_threat_reported = False
        self.warship_asm_seq = 0
        self.asm_sel = 0
        self.air_picture = TrackPicture(
            config.RADAR_TRACK_STALE_S, maximum=MAX_AIR_PICTURE_TRACKS)
        # Unmarked mast/snorkel echoes (transient display, never saved) and the
        # boats whose echoes the OPZ marked into a track: sub id -> track id.
        self.radar_blips = deque(maxlen=config.RADAR_BLIP_MAX)
        self.radar_blip_seq = 0
        self._radar_marked = {}
        self.ais = AISReceiver(seed)
        self.opz_selected_track_id = None
        self.opz_contact_filter = "ALL"
        self.opz_affiliations = {}
        # Operator-authored display identifiers are deliberately separate from
        # opaque observation IDs.  Every station renders these labels while
        # commands continue to use the non-public observation identity.
        self.opz_track_labels = {}
        self.opz_fusion = OPZFusionPicture()
        self._opz_source_bindings = {}
        self._opz_world_identity = id(self.world)
        self.esm_picture = ESMPicture()
        self.ecm_jammer = ECMJammer()
        self.eloka_selected_track_key = None
        self.eloka_status_filter = "OPERATIONAL"
        self.eloka_threat_filter = "ALL"
        self.eloka_band_filter = "ALL"
        self.eloka_annotations = {}
        self.radio_picture = TrackPicture(300.0)
        self.radio_sel = 0
        self.hfdf_log = []
        self.hfdf_fixes = {}
        self.ciws_ammo = self._air_defense_loadout["ciws"]["ammo"]
        self.ciws_cooldown_s = 0.0
        # Rotating search antenna in simulation time (saved): targets are
        # looked at only when the beam sweeps past them.
        self.radar_scan_phase = 0.0
        self.radar_scan_pending_deg = 0.0
        self.ciws_authorized = True  # session-only fire-release gate, OPZ "I"
        self.aa_ammo = self._air_defense_loadout["aa_gun"]["ammo"]
        self.aa_cooldown_s = 0.0
        self.flak_authorized = True  # session-only fire-release gate, Weapons "F"
        # Real ADS-B traffic: HOSTILE is a manual OPZ classification (see
        # affiliate_opz_observation) but never authorizes weapons on its own -
        # engaging a real contact needs an explicit, freshly re-affirmed
        # confirmation so an accidental IFF slip can't autofire straight into
        # a political incident.
        self.live_engage_confirm_pending = None  # icao24 awaiting confirmation
        self.live_engage_authorized = set()       # icao24s cleared to engage
        self.raiders = []
        self.raid_seq = 0
        self.raid_waves_spawned = 0
        self._raider_visible_last = False
        self.rng_raid = random.Random(seed + 40424)
        self.hq_timer = 15.0
        self._mission_warnings = set()
        self.tooltips_enabled = self.preferences.tooltips
        self.pinned_tooltip = None
        self._tooltip_anchor = None
        self._nav_warning_cd = 0.0
        self.quit_confirm = False
        self.quit_selection = 0
        self.quit_after_save = False
        self.help_open = False
        self.nations_open = False
        self.save_ui = None
        self.save_confirm = False
        self.save_info = []
        self.help_page = 0
        self.help_manual_chapter = 0
        self._joy_acc = 0.0
        self._joy_x_acc = 0.0
        self._joy_turn = 0
        # W3: Luftfahrt (Airbases + Flüge) und W0: Karten-Viewport
        self.flights = FlightManager(
            self.world.coast, random.Random(seed + 2024), self.runtime_catalog,
            near=(self.ship.x, self.ship.y))
        self.map_view = Viewport(self.world.size_nm,
                                 config.MAP_ZOOM_MIN_PX_PER_NM,
                                 config.MAP_ZOOM_MAX_PX_PER_NM)
        self.opz_map_view = Viewport(self.world.size_nm, 1.0, 100.0)
        self._reset_map_view()
        self.hq_msg(message("runtime.hq.roe", roe=self.roe))
        weather = self.world.weather_values()
        self.hq_msg(message(
            "runtime.hq.weather", sea_state=f"{weather['sea_state']:.1f}",
            wind_from=f"{weather['wind_from_deg']:.0f}",
            wind_speed=f"{weather['wind_speed_kn']:.0f}",
            rain=f"{weather['rain_intensity']:.0%}",
            visibility=f"{weather['visibility_nm']:.1f}"))
        self.feed.add(self.world.format_time(), "mission",
                      self._mission_started_notice())
        if publish_intel:
            self.hq_msg(self._initial_threat_notice())
            if self.hq_intel_mode() == "exact":
                self.hq_msg(self._threat_identification_notice())
        # Menu input cannot operate the simulation. Only this unstarted world
        # may be consumed by menu start; loads replace its world/sonar identity.
        self._prepared_menu_mission = (
            seed, self.scenario_key, self.world_mode,
            tuple(self.difficulty[name] for name in config.DIFFICULTY_FIELD_ORDER),
            self.hq_intel_mode(), id(self.world), id(self.sonar)) if self.in_menu else None

    def start_custom_mission(self, definition: dict) -> bool:
        """Start the currently runtime-effective subset of an authored mission.

        Fixed player/environment values, built-in submarine/surface units and
        sink/survive objectives are effective. Events, random groups, custom
        world sizes and protect/reach objectives remain editor-only and are
        rejected rather than silently ignored.
        """
        if validate_mission(definition, catalog_builtins(self.runtime_catalog).keys()):
            return False
        if (definition["events"] or definition["units"]["random_groups"]
                or definition["objective"]["type"] not in ("sink", "survive")
                or float(definition["world"]["size_nm"]) != config.WORLD_SIZE_NM
                or definition["world"]["kind"] != "fixed"
                or definition["environment"]["weather"] != "clear"):
            return False
        markers = {item["id"]: item for item in static_preview(definition)["markers"]}
        exact = definition["units"]["exact"]
        if any(unit["profile"] not in self.runtime_catalog.subs | self.runtime_catalog.surfaces
               for unit in exact):
            return False
        for unit in exact:
            profile_key = unit["profile"]
            profile = (self.runtime_catalog.subs.get(profile_key)
                       or self.runtime_catalog.surfaces[profile_key])
            systems = self.runtime_catalog.profile_systems.get(profile_key)
            maximum_speed = (
                self.runtime_catalog.machines[systems.machine_key].maximum_speed_kn
                if systems is not None and systems.machine_key is not None else
                (profile.speed_kn[1] if isinstance(profile.speed_kn, tuple)
                 else profile.speed_kn))
            if float(unit.get("speed_kn", 0.0)) > maximum_speed:
                return False
        expected_targets = {unit["id"] for unit in exact
                            if unit["profile"] in self.runtime_catalog.subs
                            and unit["side"] == "hostile"}
        if (definition["objective"]["type"] == "sink"
                and set(definition["objective"]["target_ids"]) != expected_targets):
            return False
        self.reset(int(definition["seed"]), "s4_zufall", publish_intel=False)
        self.subs, self.civilians, self.warships = [], [], []
        self.animals, self.asms = [], []
        player = definition["player"]
        self.ship.course = self.ship.target_course = float(player["course_deg"])
        self.ship.x, self.ship.y = self.world.nearest_safe_hull(
            player["x"], player["y"], self.ship.course, self.ship.hull_spec)
        self.ship.last_safe_pose = (self.ship.x, self.ship.y, self.ship.course)
        self.ship.speed = self.ship.target_speed = config.clamp(
            float(player["speed_kn"]), 0.0, config.SHIP_SPEED_MAX_KN)
        self.ship.order_idx = min(range(len(config.TELEGRAPH_ORDERS)),
                                  key=lambda i: abs(config.TELEGRAPH_ORDERS[i][1]
                                                    - self.ship.target_speed))
        env = definition["environment"]
        self.world.hour = float(env["time_hour"])
        self.world.sea_state = int(env["sea_state"])
        self.world.refresh_weather()
        thermo = float(env["thermocline_depth_m"])
        self.world._thermo = [[thermo for _ in row] for row in self.world._thermo]
        lv = self.difficulty
        for unit in exact:
            marker = markers[unit["id"]]
            x, y = self.world.nearest_water(marker["x"], marker["y"])
            profile = unit["profile"]
            if profile in self.runtime_catalog.subs:
                entity = Sub(x, y, float(unit.get("depth_m", 60.0)),
                             float(unit.get("course_deg", 0.0)), profile,
                             self.rng_world, quiet_mult=lv["quiet_mult"],
                             attack_mult=lv["enemy_attack_mult"],
                             attack_cooldown_s=lv["enemy_cooldown_s"],
                             profile=self.runtime_catalog.subs[profile],
                             decoy_profile=self.runtime_catalog.decoys[
                                 self.runtime_catalog.runtime_bindings[
                                     "submarine_decoy"]],
                              enemy_torpedo_profile=self.runtime_catalog.torpedoes[
                                  self.runtime_catalog.runtime_bindings[
                                      "enemy_torpedo"]],
                               side=unit["side"], runtime_catalog=self.runtime_catalog,
                               asw_rng=self.rng_asw)
                entity.speed = float(unit.get("speed_kn", 0.0))
                self.subs.append(entity)
            elif self.runtime_catalog.surfaces[profile].category == "KAMPFSCHIFF":
                entity = SurfaceShip(
                    x, y, rng=self.rng_world, side=unit["side"],
                    doctrine="surface_combatant",
                    profile=self.runtime_catalog.surfaces[profile],
                    runtime_catalog=self.runtime_catalog)
                entity.course = entity.target_course = float(unit.get("course_deg", 0.0))
                entity.speed = entity.target_speed = float(unit.get("speed_kn", 0.0))
                self.warships.append(entity)
            else:
                entity = CivilianShip(
                    x, y, rng=self.rng_world,
                    side=unit["side"], doctrine="surface_transit",
                    profile=self.runtime_catalog.surfaces[profile],
                    runtime_catalog=self.runtime_catalog)
                entity.course = entity.target_course = float(unit.get("course_deg", 0.0))
                entity.speed = entity.target_speed = float(unit.get("speed_kn", 0.0))
                self.civilians.append(entity)
        self.mission.name = definition["name"]
        self.mission.win_mode = definition["objective"]["type"]
        self.mission.time_limit_s = float(definition["objective"]["time_limit_s"])
        self.mission.sub_count = len(self.subs)
        self.mission.animal_count = self.mission.civilian_count = 0
        self.mission.asm_count = self.mission.warship_count = 0
        self.custom_mission_definition = json.loads(json.dumps(definition))
        self.feed.entries[-1].text = self._mission_started_notice()
        self.hq_msg(self._initial_threat_notice())
        self.in_menu = False
        self.main_menu = False
        self._reset_map_view()
        return True

    FLASH_TEXT_SIZE = 18
    FLASH_MAX_LINES = 2

    def flash_banner_rect(self) -> pygame.Rect:
        """Opaque, text-sized banner in the free right part of the top bar.

        It starts right of the status line, so it never prints over a map,
        station tabs or chart labels; only a message too long for one line
        grows downward (at most two lines).
        """
        face = layout.font(layout.scaled_size(self.FLASH_TEXT_SIZE))
        left = max(config.SCREEN_W // 2,
                   getattr(self, "_top_status_right", 0) + 16)
        max_w = config.SCREEN_W - 6 - left
        lines = layout.wrap_text(localize(self.msg), face, max_w - 20)
        lines = lines[:self.FLASH_MAX_LINES] or [""]
        width = min(max_w, max(face.size(line)[0] for line in lines) + 20)
        height = max(config.TOP_BAR_H - 4,
                     len(lines) * layout._line_height(face) + 6)
        return pygame.Rect(config.SCREEN_W - 6 - width, 2, width, height)

    def _draw_flash_banner(self, surface) -> None:
        # The banner covers what lies beneath it instead of printing over
        # the map and the station tabs.
        box = self.flash_banner_rect()
        pygame.draw.rect(surface, config.COLOR_OVERLAY_BG, box)
        pygame.draw.rect(surface, config.COLOR_WARN, box, 1)
        layout.blit_block(surface, localize(self.msg), box.x + 10, box.y + 3,
                          box.w - 20, box.h - 6, config.COLOR_WARN,
                          size=self.FLASH_TEXT_SIZE, align="center", valign="center")

    def flash(self, text: object, seconds: float = 3.0) -> None:
        if (getattr(self, "local_side", "frigate") == "uboot"
                and not getattr(self, "_uboot_ui", False)):
            # The frigate's banners never reach the submarine player.
            return
        self.msg = text
        self.msg_until = self._t + seconds

    def announce(self, text: object, category: str, seconds: float = 3.0) -> None:
        """Show and retain one operational message in the event feed.

        Input prompts, selection feedback and display-only settings continue to
        use :meth:`flash`; simulation events and completed orders use this path
        so their message does not disappear with the transient banner.
        """
        self.flash(text, seconds)
        self.feed.add(self.world.format_time(), category, text)

    def mission_name_display(self):
        """Keep authored mission text opaque while localizing built-ins."""
        if self.custom_mission_definition is not None:
            return raw_text(self.mission.name)
        keys = {"patrouille": "mission.patrol", "doppeljagd": "mission.double",
                "konvoi": "mission.convoy", "nuklearer_abfang": "mission.intercept",
                "custom": "mission.custom"}
        return message(keys[self.mission.type_key])

    def mission_level_display(self):
        return message("level.custom")

    def mission_description_display(self):
        if self.custom_mission_definition is not None:
            return raw_text(self.custom_mission_definition.get("description", ""))
        scenario = {"s1_patrouille": "patrol", "s2_doppeljagd": "double",
                    "s3_abfang": "intercept", "s4_zufall": "random"}[self.scenario_key]
        return "scenario." + scenario + ".brief"

    def mission_objective_display(self):
        if self.custom_mission_definition is not None:
            objective_type = self.custom_mission_definition["objective"]["type"]
            return message("mission.objective.convoy" if objective_type == "survive"
                           else "mission.objective.sink")
        if self.mission.win_mode == "survive":
            objective = message("mission.objective.convoy")
        elif self.mission.type_key == "nuklearer_abfang":
            objective = message("mission.objective.intercept")
        else:
            objective = message("mission.objective.sink")
        extras = []
        if self.mission.asm_count:
            extras.append(message("mission.objective.asm",
                                  count=self.mission.asm_count))
        if self.mission.warship_count:
            extras.append(message("mission.objective.warship",
                                  count=self.mission.warship_count))
        if len(extras) == 2:
            extra = message("mission.objective.extras", first=extras[0], second=extras[1])
        else:
            extra = extras[0] if extras else ""
        return message("mission.objective.summary", objective=objective, extras=extra)

    def _mission_started_notice(self):
        return message("runtime.mission.started",
                       name=self.mission_name_display(),
                       level=self.mission_level_display(),
                       objective=self.mission_objective_display())

    def _initial_threat_notice(self):
        """Return one coarse, static intelligence cue for the mission start."""
        candidates = [target for target in self.subs if target.side == "hostile"]
        domain = "underwater"
        if not candidates:
            candidates = [target for target in self.warships
                          if target.side == "hostile"]
            domain = "surface"
        if not candidates:
            return message("runtime.hq.threat_unknown")
        target = min(candidates, key=lambda item: math.hypot(
            item.x - self.ship.x, item.y - self.ship.y))
        dx, dy = target.x - self.ship.x, target.y - self.ship.y
        bearing = int(((math.degrees(math.atan2(dx, -dy)) % 360.0 + 22.5)
                       // 45.0) * 45.0) % 360
        distance = max(5, int((math.hypot(dx, dy) + 2.5) // 5.0) * 5)
        return message(f"runtime.hq.threat_{domain}", bearing=f"{bearing:03d}",
                       range=distance)

    def hq_intel_mode(self) -> str:
        """Start-report detail: fixed per scenario, chosen for the free hunt."""
        fixed = config.SCENARIOS.get(self.scenario_key, {}).get("hq_intel")
        mode = fixed if fixed is not None else self.menu_hq_intel
        return mode if mode in config.HQ_INTEL_MODES else "coarse"

    def _threat_identification_notice(self):
        """HQ names the hostile forces committed to this mission.

        Authored mission intelligence at the start, like the briefing: type
        and number of the deployed hostile units (catalog names, as listed in
        the analyser) and the expected air-raid waves. Positions stay coarse.
        """
        counts = {}
        for unit in (*self.subs, *self.warships):
            if getattr(unit, "side", "hostile") != "hostile":
                continue
            # A submarine keeps its catalog profile in ``stype.profile``.
            profile = getattr(getattr(unit, "stype", None), "profile", None) \
                or getattr(unit, "profile", None)
            key = getattr(profile, "key", None)
            name = self.profile_name(key) if key is not None else None
            if not name or name == key:
                name = getattr(profile, "name", None) or name
            if name:
                counts[name] = counts.get(name, 0) + 1
        items = [message("runtime.hq.intel_unit", count=count, name=raw_text(name))
                 for name, count in counts.items()]
        if self.mission.asm_count:
            items.append(message("runtime.hq.intel_air",
                                 count=self.mission.asm_count))
        if not items:
            return message("runtime.hq.intel_none")
        units = items[-1]
        for item in reversed(items[:-1]):
            units = message("runtime.hq.intel_list", first=item, rest=units)
        return message("runtime.hq.intel_exact", units=units)

    def start_new_game(self, scenario_key: str, world_mode: str,
                       difficulty: dict = None, seed: int = None) -> bool:
        """Start a mission through the same path as the main menu.

        Only ``s4_zufall`` lets the operator pick a custom difficulty; every
        other scenario fixes its own. Without a seed the menu's uniform
        re-roll is used, so a host-approved caller can never pin a seed by
        accident.
        """
        if (scenario_key not in config.SCENARIOS
                or world_mode not in ("fixed", "procedural", "real_fixed")
                or difficulty is not None and not _valid_difficulty_dict(difficulty)
                or seed is not None and not (
                    type(seed) is int and 1 <= seed < 1_000_000_000)):
            return False
        self.scenario_key = scenario_key
        self.world_mode = world_mode
        if (difficulty is not None
                and config.SCENARIOS[scenario_key]["difficulty"] is None):
            self.menu_difficulty = dict(difficulty)
        if seed is None:
            self._reroll_menu_seed()
        else:
            self.seed = seed
        self._prepared_menu_mission = None
        self._start_menu_mission()
        return True

    def hq_msg(self, text: object) -> None:
        """M13/W3: Teletype-Nachricht – Funkraum-Verkehr + Ereignis-Feed."""
        stamp = self.world.format_time()
        self.messages.append((stamp, text))
        if len(self.messages) > 40:
            self.messages.pop(0)
        self.feed.add(stamp, "funk", text)

    def _begin_numeric_input(self, mode: str) -> None:
        """Open a keyboard-first entry for a navigation order."""
        self._clear_controls()
        self.input_mode = mode
        if mode == "bearing":
            self.input_buffer = ""
            prompt = message("runtime.input.bearing",
                             current=f"{self.sonar.listen_bearing:05.1f}")
        elif mode == "plot_speed":
            self.input_buffer = ""
            prompt = message("plot.input.speed")
        elif mode == "course":
            self.input_buffer = ""
            prompt = message("runtime.input.course",
                             current=f"{self.ship.target_course:03.0f}")
        else:
            self.input_buffer = ""
            prompt = message("runtime.input.speed",
                             current=f"{self.ship.target_speed:.1f}")
        self.flash(message("runtime.input.pending", prompt=localize(prompt, self.tr),
                            value=self.input_buffer), 60.0)

    def _begin_track_id_input(self) -> None:
        """Open bounded OPZ entry for the selected track's shared display ID."""
        track = self.selected_opz_track()
        if track is None:
            self.flash(message("runtime.cic.none_select"), 2.0)
            return
        self._clear_controls()
        self.input_mode = "track_id"
        self.input_buffer = ""
        self.flash(message("runtime.input.track_id", current=track.label), 60.0)

    def _navigation_order_live(self) -> bool:
        # The simulation never pauses: menus and overlays own local input only,
        # so crew orders stay live behind them.
        return (self.running and not self.game_over
                and not self.in_menu and not self.main_menu
                and not self.splash_active
                and self.input_mode in (None, "course", "speed"))

    def _set_course_order(self, course: float, station: str) -> str:
        """Apply a validated shared helm order for one local station owner."""
        if type(course) not in (int, float):
            return "invalid_value"
        try:
            valid = math.isfinite(course) and 0.0 <= course < 360.0
        except OverflowError:
            valid = False
        if not valid:
            return "invalid_value"
        if not self._navigation_order_live():
            return "phase_blocked"
        if self.damage.station_down(station):
            return f"{station}_down"
        self.ship.target_course = course
        self.feed.add(self.world.format_time(), "navigation",
                      message("runtime.numeric.course_feed", course=f"{course:03.0f}"))
        return "ok"

    def order_course(self, course: float) -> str:
        """Apply a Bridge course order and return a stable result code."""
        return self._set_course_order(course, "bridge")

    def set_engine_course(self, course: float) -> str:
        """Set the common course controller from the machinery station."""
        return self._set_course_order(course, "engine")

    def order_speed(self, speed_kn: float) -> str:
        """Apply a validated ahead-speed order and return a stable result code."""
        if type(speed_kn) not in (int, float):
            return "invalid_value"
        try:
            valid = (math.isfinite(speed_kn)
                     and 0.0 <= speed_kn <= config.SHIP_SPEED_MAX_KN)
        except OverflowError:
            valid = False
        if not valid:
            return "invalid_value"
        if not self._navigation_order_live():
            return "phase_blocked"
        if self.ship.fuel_kg <= 0.0:
            return "no_fuel"
        self.ship.target_speed = speed_kn
        self.ship.astern = False
        self.ship.order_idx = min(range(len(config.TELEGRAPH_ORDERS)),
                                  key=lambda i: abs(config.TELEGRAPH_ORDERS[i][1]
                                                    - speed_kn))
        self.feed.add(self.world.format_time(), "navigation",
                      message("runtime.numeric.speed_feed", speed=f"{speed_kn:.1f}"))
        return "ok"

    def set_engine_telegraph(self, order: str):
        if type(order) is not str:
            return "invalid_value"
        if self.damage.station_down("engine"):
            return "engine_down"
        if self.ship.fuel_kg <= 0.0:
            return "no_fuel"
        if order == "ASTERN":
            self.ship.astern = True
            self.ship.order_idx = 0
            self.ship.target_speed = config.ASTERN_SPEED_KN
        else:
            index = next((i for i, item in enumerate(config.TELEGRAPH_ORDERS)
                          if item[0] == order), None)
            if index is None:
                return "invalid_value"
            self.ship.astern = False
            self.ship.order_idx = index
            self.ship.target_speed = config.TELEGRAPH_ORDERS[index][1]
        return True

    def _cycle_engine_telegraph(self, delta: int):
        orders = ("ASTERN", *(item[0] for item in config.TELEGRAPH_ORDERS))
        index = orders.index(self.ship.telegraph)
        return self.set_engine_telegraph(
            orders[config.clamp(index + delta, 0, len(orders) - 1)])

    def set_engine_speed(self, speed_kn: float):
        if self.damage.station_down("engine"):
            return "engine_down"
        return self.order_speed(speed_kn)

    def set_quiet_mode(self, enabled: bool):
        if type(enabled) is not bool:
            return "invalid_value"
        if self.damage.station_down("engine"):
            return "engine_down"
        self.ship.quiet_mode = enabled
        return True

    def assign_damage_team(self, team: int, compartment: str):
        if type(team) is not int or type(compartment) is not str:
            return "invalid_value"
        if team not in self.damage.teams or compartment not in self.damage.compartments:
            return "invalid_value"
        if self.damage.ship_sunk:
            return "not_ready"
        if not self.damage.assign_team(team, compartment):
            return "not_ready"
        return True

    def unassign_damage_team(self, team: int, compartment: str):
        if (type(team) is not int or type(compartment) is not str
                or team not in self.damage.teams
                or compartment not in self.damage.compartments):
            return "invalid_value"
        if self.damage.teams[team] != compartment:
            return "stale_ref"
        self.damage.unassign_team(team)
        return True

    def set_sonar_listen_bearing(self, bearing: float):
        if (type(bearing) not in (int, float) or not 0 <= bearing < 360
                or not math.isfinite(bearing)):
            return "invalid_value"
        if self._sonar_down():
            return "sonar_down"
        # Retuning keeps the listening stream running: the receiver reset is a
        # sequence gap that _update_audio joins without a silent re-buffer.
        self.sonar.set_listen_bearing(bearing)
        return True

    def set_sonar_focus(self, contact):
        if self._sonar_down():
            return "sonar_down"
        if (not isinstance(contact, Contact)
                or self.sonar.contacts.get(contact.target_id) is not contact):
            return "stale_ref"
        if not 0 <= self.sim_t - contact.last_seen <= 2.0:
            return "stale_ref"
        self.selected_contact = contact
        self.sonar.set_listen_bearing(contact.bearing)
        self.sonar.focus_locked = True
        self.sonar._listen_target_id = contact.target_id
        return True

    def clear_sonar_focus(self):
        if self._sonar_down():
            return "sonar_down"
        self.sonar.focus_locked = False
        self.sonar._listen_target_id = None
        return True

    def set_sonar_array_mode(self, mode: str):
        if mode not in ("BOW", "TOWED") or type(mode) is not str:
            return "invalid_value"
        if self._sonar_down():
            return "sonar_down"
        self.sonar_mode = mode
        return True

    def set_sonar_tas(self, deployed: bool):
        if type(deployed) is not bool:
            return "invalid_value"
        if self._sonar_down():
            return "sonar_down"
        state = self.sonar.tow_status(self.sonar_observer.speed)["state"]
        if state == "FAULT":
            return "tas_fault"
        is_deploying = state in ("DEPLOYING", "STREAMED")
        if deployed == is_deploying:
            return True
        return True if self.sonar.toggle_tow(self.sonar_observer.speed) else "tas_fault"

    def set_sonar_tow_depth(self, depth_m: float):
        if (type(depth_m) not in (int, float)
                or not config.SONAR_TOWED_DEPTH_MIN_M <= depth_m
                <= config.SONAR_TOWED_DEPTH_MAX_M or not math.isfinite(depth_m)):
            return "invalid_value"
        if self._sonar_down():
            return "sonar_down"
        if self.sonar.tow_state != TowState.STREAMED:
            return "not_ready"
        limit = max(config.SONAR_TOWED_DEPTH_MIN_M,
                    config.SONAR_TOWED_DEPTH_MAX_M
                    - self.sonar_observer.speed * config.SONAR_TOWED_SPEED_SHALLOW_M_PER_KN)
        if depth_m > limit:
            return "not_ready"
        self.sonar.towed_depth_target_m = depth_m
        return True

    def measure_sonar_bt(self):
        if self._sonar_down():
            return "sonar_down"
        return (True if self.sonar.measure_environment(
            self.world, self.sonar_observer, self.sim_t) else "not_ready")

    def send_active_ping(self):
        if self._opfor is not None and self._sonar_ctx is self._opfor.station:
            return opfor.send_ping(self, self._opfor)
        if self._sonar_down():
            return "sonar_down"
        if (self.sonar_mode == "TOWED"
                and not self.sonar.tow_status(self.ship.speed)["available"]):
            return "not_ready"
        if not self.sonar.fire_ping():
            return "not_ready"
        self._remember_ping_pulse()
        self._emit_sound("sonar_ping")
        self.sonar.queue_ping(self.ship, self._sonar_targets(), self.world,
                              self.sim_t, self._sonar_range_factor(),
                              mode=self.sonar_mode)
        return True

    def set_helicopter_dipping(self, deployed: bool):
        if type(deployed) is not bool:
            return "invalid_value"
        if self.damage.station_down("flightdeck"):
            return "flightdeck_down"
        if not self.helo.airborne:
            return "not_ready"
        if deployed and not self.helicopter_weather()["dipping_safe"]:
            return "weather_unsafe"
        if not self.helo.set_dipping(deployed, self.world):
            return "water_required" if deployed else "not_ready"
        return True

    def set_helicopter_dip_depth(self, depth_m: float):
        if (type(depth_m) not in (int, float) or isinstance(depth_m, bool)
                or not math.isfinite(depth_m)
                or not config.HELO_DIP_DEPTH_MIN_M <= depth_m
                <= config.HELO_DIP_DEPTH_MAX_M):
            return "invalid_value"
        if (not self.helo.airborne
                or self.helo.dip_state not in ("DEPLOYING", "DEPLOYED")):
            return "not_ready"
        return (True if self.helo.set_dip_depth(depth_m, self.world)
                else "water_required")

    def send_helicopter_dipping_ping(self):
        if self.damage.station_down("sonar"):
            return "sonar_down"
        if not self.helo.fire_dipping_ping():
            return "not_ready"
        self._remember_ping_pulse()
        self._emit_sound("sonar_ping")
        self.sonar.queue_ping(self.helo, self._sonar_targets(), self.world,
                              self.sim_t, self._sonar_range_factor(),
                              mode="DIPPING")
        return True

    def set_sonar_tma_enabled(self, enabled: bool):
        if type(enabled) is not bool:
            return "invalid_value"
        if self._sonar_down():
            return "sonar_down"
        self.sonar.tma_enabled = enabled
        return True

    def set_sonar_gain(self, gain_db: float):
        if (type(gain_db) not in (int, float) or not -12 <= gain_db <= 24
                or not math.isfinite(gain_db)):
            return "invalid_value"
        if self._sonar_down():
            return "sonar_down"
        self.sonar.gain_db = gain_db
        return True

    def set_sonar_audition_mode(self, mode: str):
        if type(mode) is not str or mode not in ("BROADBAND", "FILTERED", "HETERODYNE"):
            return "invalid_value"
        if self._sonar_down():
            return "sonar_down"
        self.sonar.set_audition_mode(mode)
        return True

    def set_sonar_band_preset(self, preset: str):
        band = SONAR_BAND_PRESETS.get(preset) if type(preset) is str else None
        if band is None:
            return "invalid_value"
        if self._sonar_down():
            return "sonar_down"
        self.sonar.band_low_hz, self.sonar.band_high_hz = band
        return True

    def set_sonar_notch(self, enabled: bool):
        if type(enabled) is not bool:
            return "invalid_value"
        if self._sonar_down():
            return "sonar_down"
        self.sonar.notch_enabled = enabled
        return True

    def set_sonar_peak_hold(self, enabled: bool):
        if type(enabled) is not bool:
            return "invalid_value"
        if self._sonar_down():
            return "sonar_down"
        self.sonar.peak_hold = enabled
        return True

    def sonar_harmonic_candidates(self):
        return tuple(sorted({float(hz) for hz, _ in list(
            getattr(self.sonar.receiver, "peaks", []))[:6]
            if type(hz) in (int, float) and math.isfinite(hz)
            and 0 < float(hz) <= config.LOFAR_FMAX_HZ}))

    def set_sonar_harmonic(self, frequency_hz):
        if self._sonar_down():
            return "sonar_down"
        if frequency_hz is None:
            self.sonar_harmonic_hz = None
            return True
        if (type(frequency_hz) not in (int, float)
                or not 0 < frequency_hz <= config.LOFAR_FMAX_HZ
                or not math.isfinite(frequency_hz)):
            return "invalid_value"
        # Any operator-chosen fundamental (the cursor), not only detected peaks.
        self.sonar_harmonic_hz = float(frequency_hz)
        return True

    def designate_sonar_target(self, contact):
        if self._sonar_down():
            return "sonar_down"
        if (not isinstance(contact, Contact)
                or self.sonar.contacts.get(contact.target_id) is not contact
                or not 0 <= self.sim_t - contact.last_seen
                < config.SONAR_CONTACT_LOST_S):
            return "stale_ref"
        self.target = contact
        return True

    def _finish_numeric_input(self) -> None:
        """Validate and apply a pending course or speed order."""
        mode = self.input_mode
        if mode == "track_id":
            track = self.selected_opz_track()
            result = ("stale_ref" if track is None else
                      self.set_opz_track_label(track.observation_id,
                                               self.input_buffer))
            if result is not True:
                self.flash(message("runtime.cic.track_id_invalid"), 2.0)
                return
            self.flash(message("runtime.cic.track_id_set",
                               track=self.input_buffer.upper()), 2.0)
            self.input_mode = None
            self.input_buffer = ""
            return
        value = self.input_buffer.replace(",", ".")
        try:
            number = float(value)
        except ValueError:
            self.flash(message("event.invalid_input"), 2.0)
            return
        if mode == "plot_speed":
            pending = self._plot_dr_pending
            self.input_mode = None
            self.input_buffer = ""
            self._plot_dr_pending = None
            if pending is not None:
                self._plot_flash_result(self.plot_add(
                    "dr", pending[0], pending[1], course=pending[2],
                    speed_kn=number))
            return
        if mode in ("course", "bearing"):
            if not 0.0 <= number < 360.0:
                self.flash(message("runtime.numeric.angle"), 2.0)
                return
            if mode == "bearing":
                if self.set_sonar_listen_bearing(number) is not True:
                    self.flash(message("event.invalid_input"), 2.0)
                    return
                self.flash(message("runtime.numeric.true_bearing", bearing=f"{number:05.1f}"), 2.0)
            else:
                result = (self.set_engine_course(number)
                          if self.station is Station.ENGINE else self.order_course(number))
                if result in ("bridge_down", "engine_down"):
                    self.flash(message("event.bridge_down" if result == "bridge_down"
                                       else "engine.limit.down"))
                    self.input_mode = None
                    self.input_buffer = ""
                    return
                if result != "ok":
                    self.flash(message("event.invalid_input"), 2.0)
                    return
                self.flash(message("runtime.numeric.course", course=f"{number:03.0f}"), 2.0)
        else:
            if not 0.0 <= number <= config.SHIP_SPEED_MAX_KN:
                self.flash(message("runtime.numeric.speed",
                                   maximum=f"{config.SHIP_SPEED_MAX_KN:.0f}"), 2.0)
                return
            result = (self.set_engine_speed(number) if self.station is Station.ENGINE
                      else self.order_speed(number))
            if result not in (True, "ok"):
                self.flash(message("event.invalid_input"), 2.0)
                return
            self.flash(message("runtime.numeric.speed_set", speed=f"{number:.1f}"), 2.0)
        self.input_mode = None
        self.input_buffer = ""

    def _handle_numeric_input(self, key: int) -> None:
        if key == pygame.K_ESCAPE:
            self.input_mode = None
            self.input_buffer = ""
            self.flash(message("event.input_cancelled"), 1.5)
        elif key in (pygame.K_RETURN, pygame.K_KP_ENTER):
            self._finish_numeric_input()
        elif key == pygame.K_BACKSPACE:
            self.input_buffer = self.input_buffer[:-1]
        elif self.input_mode == "track_id":
            name = pygame.key.name(key)
            if (len(self.input_buffer) < MAX_TRACK_DISPLAY_ID_LEN
                    and len(name) == 1 and name.isascii()
                    and (name.isalnum() or name == "-")):
                self.input_buffer += name.upper()
            elif (len(self.input_buffer) < MAX_TRACK_DISPLAY_ID_LEN
                  and key in (pygame.K_MINUS, pygame.K_KP_MINUS)):
                self.input_buffer += "-"
        elif len(pygame.key.name(key)) == 1 and pygame.key.name(key).isdigit():
            if len(self.input_buffer) < 5:
                self.input_buffer += pygame.key.name(key)
        elif key in (pygame.K_KP0, pygame.K_KP1, pygame.K_KP2, pygame.K_KP3,
                     pygame.K_KP4, pygame.K_KP5, pygame.K_KP6, pygame.K_KP7,
                     pygame.K_KP8, pygame.K_KP9):
            if len(self.input_buffer) < 5:
                self.input_buffer += pygame.key.name(key).strip("[]")
        elif (self.input_mode in ("speed", "bearing", "plot_speed")
              and key in (pygame.K_PERIOD, pygame.K_COMMA, pygame.K_KP_PERIOD)
              and "." not in self.input_buffer):
            self.input_buffer += "."

    def _feed_ping(self, tgt, contact) -> None:
        """W1/W2: Ping-Echo-Feed inkl. Echolatenz (W3: Salzwasser-Schallfeld)."""
        dist = tgt.distance_nm(self.ship)
        mx, my = (self.ship.x + tgt.x) * .5, (self.ship.y + tgt.y) * .5
        latenz = self.world.echo_delay_s(dist, mx, my)
        klass = {"diesel_alt": "Diesel", "aip_modern": "AIP",
                 "ssn": "Nuclear propulsion?"}.get(
            getattr(tgt, "stype", None) and tgt.stype.key or "",
            "unknown") if getattr(tgt, "stype", None) else \
            ("Decoy?" if getattr(tgt, "kind", "") == "decoy"
             else ("biological" if hasattr(tgt, "atype") else "vessel"))
        self.feed.add(self.world.format_time(), "sonar",
                      message("runtime.ping.feed", contact=tgt.id,
                              bearing=f"{contact.bearing:4.0f}",
                              range=f"{contact.range_est:4.1f}",
                              latency=f"{latenz:3.1f}",
                              speed=f"{self.world.mean_sound_speed_m_s(mx, my):.0f}",
                              classification=klass))

    # --- Display (M8): Letterbox-Scaling + Vollbild ---

    def toggle_fullscreen(self, persist: bool = True) -> None:
        """Vollbild: (0,0)+FULLSCREEN = native Desktop-Größe (deckt Taskleiste
        ab, keine schwarzen Balken). Zurück = 1280x720-Fenster."""
        self.fullscreen = not self.fullscreen
        if self.fullscreen:
            self.display = pygame.display.set_mode((0, 0), pygame.FULLSCREEN)
        else:
            self.display = pygame.display.set_mode(
                (config.SCREEN_W, config.SCREEN_H), pygame.RESIZABLE)
        if persist:
            from dataclasses import replace
            self.preferences = replace(self.preferences, fullscreen=self.fullscreen)
            try:
                save_preferences(self.preferences)
            except OSError:
                pass
        self.flash(message("event.fullscreen_on" if self.fullscreen
                           else "event.fullscreen_off"), 2.0)

    def _set_preference(self, name: str, value) -> None:
        from dataclasses import replace
        self.preferences = replace(self.preferences, **{name: value})
        if name == "language":
            self.translator = Translator(value)
            self.tr = self.translator.t
            self.pinned_tooltip = None
            self._tooltip_anchor = None
            pygame.display.set_caption(self.tr("app.title"))
            if self.editor is not None:
                self.editor.tr = self.tr
            self.flash(message("status.language_changed",
                               language=self.tr("option.language." + value)), 2.0)
        elif name == "fullscreen" and bool(value) != self.fullscreen:
            self.toggle_fullscreen(persist=False)
        elif name == "audio":
            self.audio.shutdown()
            self.audio = AudioEngine(sample_rate=config.AUDIO_SAMPLE_RATE,
                                     enabled=bool(value))
            self._audio_timer = 0.0
            self._sonar_audio_sequence = -1
        elif name in ("large_text", "high_contrast"):
            self._apply_text_size()
        elif name == "tooltips":
            self.tooltips_enabled = bool(value)
            self.pinned_tooltip = None
            self._tooltip_anchor = None
        try:
            save_preferences(self.preferences)
        except OSError:
            self.flash(message("status.preferences_error"), 3.0)

    def _record_simlog(self, stamp: str, category: str, text) -> None:
        """Simulationsprotokoll: alle Feed-Ereignisse, optionsgesteuert, begrenzt.

        Speichert das Rohtext (message-/RawText-Objekt); die Lokalisierung
        erfolgt erst beim Commander-Publish (Sprache kann wechseln).
        """
        if not self.preferences.simlog:
            return
        self._simlog_seq += 1
        self.simlog.append({
            "seq": self._simlog_seq,
            "t": self.sim_t,
            "stamp": stamp,
            "cat": category,
            "text": text,
        })

    def _record_simlog_state(self, dt: float) -> None:
        """Periodischer Zustandssnapshot des kompletten Simulationshintergrunds.

        Rein lesend (kein RNG, keine Zustandsaenderung); Laeuft nur im
        Simulationsfortschritt, nicht in Pause/Menue/Editor.
        """
        if not self.preferences.simlog:
            self._simlog_acc = 0.0
            return
        self._simlog_acc += dt
        if self._simlog_acc < config.SIMLOG_INTERVAL_S:
            return
        self._simlog_acc = 0.0
        self._simlog_seq += 1
        self.simlog.append({
            "seq": self._simlog_seq,
            "t": self.sim_t,
            "stamp": self.world.format_time(),
            "cat": "state",
            "text": "",
            "data": self._simlog_state_data(),
        })

    def _simlog_state_data(self) -> dict:
        """Kompakter, JSON-faechiger Zustand aller Einheiten, Waffen und Welt."""
        def r2(v):
            return None if v is None else round(float(v), 2)

        def r1(v):
            return None if v is None else round(float(v), 1)

        ship = self.ship
        snap = {
            "mission_t": r2(self.mission_time),
            "result": self.mission_result,
            "world": {"hour": r1(self.world.hour),
                      "sea_state": self.world.sea_state,
                      "night": self.world.is_night()},
            "ship": {"x": r2(ship.x), "y": r2(ship.y),
                     "course": r1(ship.course), "speed": r1(ship.speed),
                     "damage": r1(self.damage.total),
                     "sunk": self.damage.ship_sunk,
                     "stations": {k: self.damage.station_down(k)
                                  for k in ("bridge", "sonar", "weapons", "opz",
                                            "radio", "engine", "flightdeck")}},
            "weapons": {"torpedoes": self.torpedo_count,
                        "vls": self.vls_cells, "ciws": self.ciws_ammo,
                        "aa": self.aa_ammo, "chaff_cd": r2(self.chaff_cd)},
            "subs": [{"id": s.id, "x": r2(s.x), "y": r2(s.y),
                      "depth": r1(s.depth), "course": r1(s.course),
                      "speed": r1(s.speed), "state": s.state,
                      "torps": s.torpedoes_left, "sunk": s.sunk}
                     for s in self.subs],
            "surfaces": ([{"id": w.id, "kind": "warship",
                           "name": getattr(w, "name", None),
                           "callsign": getattr(w, "callsign", None),
                           "mmsi": None, "imo": None, "ship_type": None,
                           "destination": None, "draught_m": None,
                           "length_m": None, "width_m": None,
                           "nav_status": None, "ais_heading": None,
                           "position_accuracy": None, "x": r2(w.x),
                           "y": r2(w.y), "course": r1(w.course),
                           "speed": r1(w.speed), "sunk": w.sunk,
                           "damage": r1(w.damage)}
                          for w in self.warships]
                         + [{"id": c.id, "kind": "civilian",
                             "name": getattr(c, "name", None),
                             "callsign": getattr(c, "callsign", None),
                             "mmsi": getattr(c, "live_mmsi", None),
                             "imo": getattr(c, "live_ais_details", {}).get("imo"),
                             "ship_type": getattr(c, "live_ais_details", {}).get("ship_type"),
                             "destination": getattr(c, "live_ais_details", {}).get("destination"),
                             "draught_m": getattr(c, "live_ais_details", {}).get("draught_m"),
                             "length_m": getattr(c, "live_ais_details", {}).get("length_m"),
                             "width_m": getattr(c, "live_ais_details", {}).get("width_m"),
                             "nav_status": getattr(c, "live_ais_details", {}).get("nav_status"),
                             "ais_heading": getattr(c, "live_ais_details", {}).get("heading"),
                             "position_accuracy": getattr(c, "live_ais_details", {}).get("position_accuracy"),
                             "x": r2(c.x),
                             "y": r2(c.y), "course": r1(c.course),
                             "speed": r1(c.speed), "sunk": c.sunk,
                             "damage": r1(c.damage)}
                            for c in self.civilians]),
            "animals": [{"id": a.id, "x": r2(a.x), "y": r2(a.y),
                         "dead": a.dead} for a in self.animals],
            "torpedoes": [{"id": t.id, "x": r2(t.x), "y": r2(t.y),
                           "depth": r1(t.depth), "course": r1(t.course),
                           "state": t.state,
                           "target": (t.target.id if t.target is not None
                                      else None)}
                          for t in self.torpedoes],
            "enemy_torpedoes": [{"id": t.id, "x": r2(t.x), "y": r2(t.y),
                                 "depth": r1(t.depth), "course": r1(t.course),
                                 "state": t.state}
                                for t in self.enemy_torpedoes],
            "decoys": [{"id": d.id, "x": r2(d.x), "y": r2(d.y),
                        "depth": r1(d.depth), "life": r1(d.life),
                        "dead": d.dead} for d in self.decoys],
            "asms": [{"seq": a.seq, "x": r2(a.x), "y": r2(a.y),
                      "course": r1(a.course), "state": a.state,
                      "jammer": a.jammer} for a in self.asms],
            "essms": [{"seq": e.seq, "x": r2(e.x), "y": r2(e.y),
                       "course": r1(e.course), "state": e.state}
                      for e in self.essms],
            "asrocs": [{"seq": a.seq, "x": r2(a.x), "y": r2(a.y),
                        "course": r1(a.course), "state": a.state}
                       for a in self.asrocs],
            "nixies": [{"seq": n.seq, "x": r2(n.x), "y": r2(n.y),
                        "depth": r1(n.depth), "dead": n.dead}
                       for n in self.nixies],
            "buoys": [{"seq": b.seq, "x": r2(b.x), "y": r2(b.y),
                       "battery_s": r1(b.battery_s), "active": b.active}
                      for b in self.buoys],
            "helo": {"state": self.helo.state, "x": r2(self.helo.x),
                     "y": r2(self.helo.y), "airborne": self.helo.airborne},
            "flights": ([{"seq": f.seq, "kind": f.kind, "callsign": None,
                          "icao24": None, "x": r2(f.x), "y": r2(f.y),
                          "course": r1(f.course), "speed": r1(f.speed),
                          "alt_m": None}
                         for f in self.flights.flights]
                        + [{"seq": a.seq, "kind": "live",
                            "callsign": a.callsign, "icao24": a.icao24,
                            "x": r2(a.x), "y": r2(a.y),
                            "course": r1(a.course), "speed": r1(a.speed),
                            "alt_m": r1(a.altitude_m)}
                           for a in sorted(self.live_traffic.aircraft.values(),
                                           key=lambda item: item.seq)
                           if not a.despawned]),
            "raiders": [{"seq": r.seq, "x": r2(r.x), "y": r2(r.y),
                         "course": r1(r.course), "phase": r.phase.value,
                         "hp": r.hp, "pending_asm": r.pending_asm}
                        for r in self.raiders],
            "radars": {"surface": self.surface_radar_on,
                       "air": self.air_radar_on},
        }
        return snap

    def compose_frame(self) -> None:
        """Virtuellen 1280x720-Canvas aufs Display bringen (M8/M9).

        FILL_SCREEN=True: Stretch auf die volle Fläche (keine schwarzen
        Balken bei 16:9); False: aspect-correctes Letterbox.
        """
        w, h = pygame.display.get_window_size()
        if w <= 0 or h <= 0:
            w, h = config.SCREEN_W, config.SCREEN_H
        # Unter X11/XWayland ersetzt pygame die Display-Surface nach dem ersten
        # Event-Pump/Resize durch ein neues Objekt; das gemerkte self.display
        # ist dann 0x0 und der Blit scheitert mit "Surfaces must not be locked".
        display = pygame.display.get_surface()
        if display is None:
            return
        self.display = display
        display.fill((0, 0, 0))
        if (w, h) == (config.SCREEN_W, config.SCREEN_H):
            display.blit(self.screen, (0, 0))
        elif config.FILL_SCREEN:
            display.blit(pygame.transform.scale(self.screen, (w, h)), (0, 0))
        else:
            _, ox, oy, sw, sh = letterbox_layout(w, h)
            display.blit(
                pygame.transform.scale(self.screen, (sw, sh)), (ox, oy))
        pygame.display.flip()

    # --- Input ---

    def _open_joystick(self, index: int) -> None:
        """Retain SDL device handles; unavailable devices remain optional."""
        try:
            device = pygame.joystick.Joystick(index)
            device.init()
            self._joysticks[device.get_instance_id()] = device
        except pygame.error:
            pass

    @property
    def administration_open(self) -> bool:
        return (self.help_open or self.nations_open or self.quit_confirm
                or self.save_ui is not None or self.options_open or self.commander_open
                or self.live_traffic_open)

    def _clear_station_input(self) -> None:
        self.held.clear()
        self._joy_turn = 0
        self._joy_acc = 0.0
        self._joy_x_acc = 0.0
        self._map_drag = None
        self._map_drag_moved = False

    def _clear_controls(self) -> None:
        self._clear_station_input()
        self._stop_sonar_audio()
        self._frame_clock_reset = True

    def _local_station_input_locked(self) -> bool:
        if (not self.autocrew.enabled[station_key(self.station)]
                and not self.commander.station_leased(self.station)):
            return False
        self._clear_station_input()
        self.input_mode = None
        self.input_buffer = ""
        return True

    def _stop_sonar_audio(self) -> None:
        self.audio.stop_sonar(immediate=True)
        self.sonar.reset_audition_audio()
        self.helo_audition.reset_audition_audio()
        self._sonar_audio_sequence = -1
        self._sonar_audio_suspended = False

    def _open_administration(self, name: str) -> None:
        """One administrative owner; manual/focus pause remains independent."""
        self._clear_controls()
        self.input_mode = None
        self.input_buffer = ""
        if name == "nations":
            self._nations_summary = reference_summary(self.world.coast,
                                                      self.runtime_catalog)
        self.help_open = name == "help"
        self.nations_open = name == "nations"
        self.quit_confirm = name == "quit"
        self.save_ui = name if name in ("save", "load") else None
        self.options_open = name == "options"
        self.commander_open = name == "commander"
        if self.commander_open:
            self.commander.prepare()
        self.live_traffic_open = name == "live_traffic"
        if self.live_traffic_open:
            self.live_traffic_sel = 0
            self.live_traffic_field = None
            self.live_traffic_field_name = None
            self.connectivity.start()
        self.quit_selection = 0
        self.quit_after_save = False
        self.save_confirm = False
        self.msg = ""
        self.help_page = 0
        self.help_scroll = 0
        self.help_manual_chapter = manual.CHAPTERS.index(
            manual.STATION_CHAPTERS.get(self.station, "quickstart"))
        if self.save_ui is not None:
            self.save_info = []
            for slot in range(1, 6):
                path = os.path.join(config.SAVE_DIR, f"slot{slot}.json")
                try:
                    data = _read_save_document(path)
                    if not isinstance(data, dict):
                        raise ValueError("Kein Spielstand")
                    info = message("save.slot_info",
                                   name=data.get("mission_name", "?"),
                                   level=data.get("level", "?"))
                except FileNotFoundError:
                    info = message("save.empty")
                except (OSError, ValueError):
                    info = message("save.unreadable")
                self.save_info.append(info)

    def _handle_administration_key(self, key: int) -> None:
        enter = key in (pygame.K_RETURN, pygame.K_KP_ENTER)
        if self.commander_open:
            self.commander.handle_key(self, key)
        elif self.options_open:
            rows = self._option_rows()
            if key == pygame.K_ESCAPE:
                self.options_open = False
            elif key in (pygame.K_PAGEUP, pygame.K_PAGEDOWN, pygame.K_TAB):
                self._set_options_page(self.options_page
                                       + (-1 if key == pygame.K_PAGEUP else 1))
            elif key in (pygame.K_UP, pygame.K_DOWN):
                self.options_sel = ((self.options_sel + (1 if key == pygame.K_DOWN else -1))
                                    % len(rows))
            elif key in (pygame.K_LEFT, pygame.K_RIGHT, pygame.K_RETURN, pygame.K_KP_ENTER):
                name = rows[self.options_sel]
                if name == "local_side":
                    self._toggle_local_side()
                    return
                if name in ("live_traffic", "commander"):
                    self._open_administration(name)
                    return
                if name == "language":
                    value = "de" if self.preferences.language == "en" else "en"
                elif name == "frame_rate":
                    choices = config.FPS_CHOICES
                    step = -1 if key == pygame.K_LEFT else 1
                    value = choices[(choices.index(self.frame_rate()) + step) % len(choices)]
                elif name == "operator_assist":
                    value = ("off" if self.operator_assist() else "training")
                elif name == "bottom_panel":
                    choices = layout.BOTTOM_PANEL_MODES
                    value = choices[(choices.index(self.bottom_panel_mode()) + 1)
                                    % len(choices)]
                else:
                    value = not getattr(self.preferences, name)
                self._set_preference(name, value)
        elif self.live_traffic_open:
            self._handle_live_traffic_key(key)
        elif self.quit_confirm:
            choices = (0, 2) if self.in_menu else (0, 1, 3, 2)
            if key in (pygame.K_ESCAPE, pygame.K_n):
                self.quit_confirm = False
            elif key in (pygame.K_UP, pygame.K_DOWN):
                self.quit_selection = (self.quit_selection +
                                       (1 if key == pygame.K_DOWN else -1)) % len(choices)
            elif enter:
                action = choices[self.quit_selection]
                if action == 0:
                    self.quit_confirm = False
                elif action == 1:
                    self._open_administration("save")
                    self.quit_after_save = True
                elif action == 3:
                    self._return_to_main_menu()
                else:
                    self.running = False
        elif self.save_ui is not None:
            if key == pygame.K_ESCAPE:
                if self.save_confirm:
                    self.save_confirm = False
                elif self.quit_after_save:
                    self._open_administration("quit")
                else:
                    self.save_ui = None
            elif pygame.K_1 <= key <= pygame.K_5:
                self.save_slot = key - pygame.K_1 + 1
                self.save_confirm = False
            elif enter:
                path = os.path.join(config.SAVE_DIR, f"slot{self.save_slot}.json")
                if not self.save_confirm and (self.save_ui == "load" or os.path.exists(path)):
                    self.save_confirm = True
                    return
                try:
                    if self.save_ui == "save":
                        self.save_to_slot(self.save_slot)
                        if self.quit_after_save:
                            self.running = False
                    elif not self.load_from_slot(self.save_slot):
                        self.flash(message("save.invalid"), 4.0)
                        return
                except (OSError, ValueError) as exc:
                    self.flash(message("runtime.save.error", error=str(exc)), 4.0)
                    return
                self.save_ui = None
                self.save_confirm = False
                self.quit_after_save = False
        elif self.help_open:
            if key in (pygame.K_ESCAPE, pygame.K_F1):
                self.help_open = False
            elif key in (pygame.K_LEFT, pygame.K_RIGHT, pygame.K_TAB):
                self.help_page = (self.help_page + (-1 if key == pygame.K_LEFT else 1)) \
                    % HELP_PAGE_COUNT
                self.help_scroll = 0
            elif self.help_page == HELP_MANUAL_PAGE and key in (
                    pygame.K_LEFTBRACKET, pygame.K_RIGHTBRACKET,
                    pygame.K_COMMA, pygame.K_PERIOD):
                step = 1 if key in (pygame.K_RIGHTBRACKET, pygame.K_PERIOD) else -1
                self.help_manual_chapter = (self.help_manual_chapter + step) \
                    % len(manual.CHAPTERS)
                self.help_scroll = 0
            elif self.help_page == HELP_MANUAL_PAGE and pygame.K_0 <= key <= pygame.K_9:
                self.help_manual_chapter = key - pygame.K_0
                self.help_scroll = 0
            elif key == pygame.K_HOME:
                self.help_scroll = 0
            elif key in (pygame.K_UP, pygame.K_DOWN, pygame.K_PAGEUP, pygame.K_PAGEDOWN):
                lines, visible = self._help_lines()
                step = visible if key in (pygame.K_PAGEUP, pygame.K_PAGEDOWN) else 1
                if key in (pygame.K_UP, pygame.K_PAGEUP):
                    step = -step
                self.help_scroll = max(0, min(max(0, len(lines) - visible),
                                              getattr(self, "help_scroll", 0) + step))
        elif self.nations_open and key in (pygame.K_ESCAPE, pygame.K_n):
            self.nations_open = False

    _LIVE_TRAFFIC_ROWS = ("live_ais_enabled", "live_adsb_enabled",
                         "aisstream_api_key", "opensky_credentials", "test")

    def _start_live_traffic_test(self) -> None:
        """Einmaliger Hintergrund-Test, ob AIS-/ADS-B-API erreichbar sind.

        Laeuft in einem eigenen Daemon-Thread (Netzwerk-I/O darf die
        Spiel-Loop nie blockieren, siehe `ais_client`/`adsb_client`);
        `live_traffic_test_result` wird ausschliesslich vom Worker-Thread
        geschrieben und nur im Hauptthread gelesen (Overlay-Zeichnen).
        """
        if (self._live_traffic_test_thread is not None
                and self._live_traffic_test_thread.is_alive()):
            return
        bbox = self.live_traffic._bounding_box_latlon()
        ais_key = self.preferences.aisstream_api_key.strip()
        adsb_credentials = self.preferences.opensky_credentials.strip()
        self.live_traffic_test_result = {
            "ais": ("running", None) if ais_key else ("no_key", None),
            "adsb": ("running", None),
        }

        def _run() -> None:
            result = dict(self.live_traffic_test_result)
            if ais_key:
                ok, reason = ais_test_connection(ais_key, bbox)
                result["ais"] = ("ok", None) if ok else ("error", reason)
            ok, reason = adsb_test_connection(adsb_credentials, bbox)
            result["adsb"] = ("ok", None) if ok else ("error", reason)
            self.live_traffic_test_result = result

        self._live_traffic_test_thread = threading.Thread(
            target=_run, name="live-traffic-test", daemon=True)
        self._live_traffic_test_thread.start()

    def _live_traffic_can_enable(self, name: str) -> bool:
        if not self.connectivity.online:
            return False
        if name == "live_ais_enabled":
            return bool(self.preferences.aisstream_api_key.strip())
        return True

    def _handle_live_traffic_key(self, key: int) -> None:
        name = self._LIVE_TRAFFIC_ROWS[self.live_traffic_sel]
        if self.live_traffic_field is not None:
            if key == pygame.K_ESCAPE:
                self.live_traffic_field = None
                self.live_traffic_field_name = None
            elif key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                self._set_preference(self.live_traffic_field_name,
                                     self.live_traffic_field.value.strip())
                self.live_traffic_field = None
                self.live_traffic_field_name = None
                self.live_traffic.configure(self, self.world, self.preferences)
            return
        if key == pygame.K_ESCAPE:
            self.connectivity.stop()
            self.live_traffic_open = False
            return
        if key in (pygame.K_UP, pygame.K_DOWN):
            self.live_traffic_sel = (self.live_traffic_sel
                                     + (1 if key == pygame.K_DOWN else -1)
                                     ) % len(self._LIVE_TRAFFIC_ROWS)
            return
        if key not in (pygame.K_LEFT, pygame.K_RIGHT, pygame.K_RETURN, pygame.K_KP_ENTER):
            return
        if name == "test":
            self._start_live_traffic_test()
            return
        if name in ("aisstream_api_key", "opensky_credentials"):
            self.live_traffic_field = TextField(
                value=getattr(self.preferences, name), maximum=256)
            self.live_traffic_field_name = name
            return
        new_value = not getattr(self.preferences, name)
        if new_value and not self._live_traffic_can_enable(name):
            self.flash(message("live_traffic.needs_prerequisite"), 3.0)
            return
        self._set_preference(name, new_value)
        self.live_traffic.configure(self, self.world, self.preferences)

    def _window_to_canvas(self, pos):
        """Convert display coordinates to the virtual 1280x720 canvas."""
        if pos is None:
            return None
        win_w, win_h = pygame.display.get_window_size()
        if win_w <= 0 or win_h <= 0:
            return None
        if config.FILL_SCREEN:
            return (pos[0] * config.SCREEN_W / win_w,
                    pos[1] * config.SCREEN_H / win_h)
        scale, ox, oy, sw, sh = letterbox_layout(win_w, win_h)
        if not (ox <= pos[0] < ox + sw and oy <= pos[1] < oy + sh):
            return None
        return ((pos[0] - ox) / scale, (pos[1] - oy) / scale)

    def _map_pointer(self, event_pos=None):
        """Return a virtual-canvas pointer only when the map is visible."""
        pos = event_pos if event_pos is not None else pygame.mouse.get_pos()
        canvas = self._window_to_canvas(pos)
        if canvas is None or not self._map_station_visible():
            return None
        if not pygame.Rect(config.MAP_RECT).collidepoint(canvas):
            return None
        return canvas

    def _map_station_visible(self) -> bool:
        return (self.station in MAP_STATIONS
                and not (self.station is Station.HELICOPTER
                         and self.station_page == 3))

    def _opz_map_pointer(self, event_pos=None):
        """Return a canvas pointer only over the native OPZ chart."""
        if self.station is not Station.OPZ:
            return None
        pos = event_pos if event_pos is not None else pygame.mouse.get_pos()
        canvas = self._window_to_canvas(pos)
        if canvas is None:
            return None
        chart = opz_ppi_rect(config.OPZ_STATION_RECT)
        return canvas if chart.collidepoint(canvas) else None

    def tooltip_at(self, canvas_pos):
        """Return serializable context for the meaningful visual under the pointer."""
        if (not self.tooltips_enabled or canvas_pos is None or self.in_menu
                or self.game_over or self.administration_open):
            return None
        previous = config.STATION_RECT
        config.STATION_RECT = (config.STATION_PANEL_RECT
                               if self._map_station_visible() else
                               config.OPZ_STATION_RECT
                               if self.station is Station.OPZ else
                               config.FULL_STATION_RECT)
        try:
            if (self._map_station_visible()
                    and pygame.Rect(config.MAP_RECT).collidepoint(canvas_pos)):
                return map_hit_target(self, canvas_pos)
            if self.station is Station.SONAR:
                return sonar_hit_target(self, canvas_pos)
            if self.station is Station.WEAPONS:
                return weapons_hit_target(self, canvas_pos)
            return station_hit_target(self, canvas_pos)
        finally:
            config.STATION_RECT = previous

    def _pin_tooltip_at(self, event_pos) -> bool:
        if not self.tooltips_enabled:
            return False
        canvas = self._window_to_canvas(event_pos)
        payload = self.tooltip_at(canvas)
        if payload is None:
            return False
        payload = dict(payload, lines=[self.tr("tooltip.snapshot", time=f"{self.sim_t:.1f}")]
                       + list(payload.get("lines", [])))
        self.pinned_tooltip = layout.valid_tooltip(payload)
        self._tooltip_anchor = tuple(canvas)
        return self.pinned_tooltip is not None

    def bottom_panel_mode(self) -> str:
        mode = getattr(self.preferences, "bottom_panel", "docked")
        return mode if mode in layout.BOTTOM_PANEL_MODES else "docked"

    def handle_event(self, e) -> None:
        with layout.bottom_panel_regions(self.bottom_panel_mode()):
            self._handle_event(e)

    def _handle_event(self, e) -> None:
        # Observe actual input transitions, not candidate restoration. Two owner
        # changes within one wall frame must still invalidate queued commands.
        fields = ("in_menu", "main_menu", "splash_active", "input_mode",
                  "help_open", "nations_open", "quit_confirm", "save_ui",
                  "options_open", "commander_open", "live_traffic_open",
                  "simlog_view_open",
                  "autocrew_overview_open", "weather_station_open",
                  "running", "game_over")
        before = tuple(getattr(self, field) for field in fields), id(self.editor)
        try:
            self._handle_owned_event(e)
        finally:
            after = tuple(getattr(self, field) for field in fields), id(self.editor)
            if before != after:
                self.commander.invalidate_commands()

    def _handle_owned_event(self, e) -> None:
        if e.type == pygame.JOYDEVICEADDED:
            self._open_joystick(e.device_index)
            return
        if e.type == pygame.JOYDEVICEREMOVED:
            device = self._joysticks.pop(e.instance_id, None)
            if device is not None:
                device.quit()
            self._clear_controls()
            return
        if e.type == pygame.WINDOWFOCUSLOST:
            # Real time never stops; losing focus only releases held controls.
            self._clear_controls()
            return
        if e.type == pygame.KEYDOWN and getattr(e, "repeat", False):
            return
        if (e.type == pygame.KEYDOWN
                and e.key in (pygame.K_RETURN, pygame.K_KP_ENTER)
                and getattr(e, "mod", 0) & pygame.KMOD_ALT):
            self.toggle_fullscreen()
            return
        if self.splash_active:
            if e.type == pygame.QUIT:
                self.running = False
            elif (e.type == pygame.KEYDOWN
                  and self._t - self.splash_started_at >= .35):
                self.splash_active = False
            return
        if e.type == pygame.KEYUP:
            self.held.discard(e.key)
            return
        if self.editor is not None:
            if e.type == pygame.QUIT:
                self.editor = None
                self.audio.stop_preview()
                self._open_administration("quit")
                return
            if (e.type == pygame.KEYDOWN and e.key == pygame.K_F5
                    and isinstance(self.editor, MissionEditor)
                    and self.editor.mode == "browser"):
                selected = self.editor.selected
                if selected is not None and not selected.builtin:
                    if self.start_custom_mission(selected.data):
                        self.editor = None
                        self.audio.stop_preview()
                    else:
                        self.editor.status = self.tr("editor.runtime_unsupported")
                return
            if (e.type == pygame.KEYDOWN and e.key == pygame.K_ESCAPE
                    and getattr(self.editor, "mode", "browser") == "browser"):
                self.editor = None
                self.audio.stop_preview()
                if self.in_menu:
                    self.main_menu = True
                return
            if e.type in (pygame.JOYAXISMOTION, pygame.JOYBUTTONDOWN):
                return
            if e.type in (pygame.MOUSEBUTTONDOWN, pygame.MOUSEBUTTONUP,
                          pygame.MOUSEMOTION, pygame.MOUSEWHEEL):
                pos = getattr(e, "pos", pygame.mouse.get_pos())
                canvas = self._window_to_canvas(pos)
                if canvas is None:
                    return
                attrs = dict(e.dict, pos=canvas)
                if hasattr(e, "rel"):
                    previous = self._window_to_canvas((pos[0] - e.rel[0], pos[1] - e.rel[1]))
                    attrs["rel"] = ((canvas[0] - previous[0], canvas[1] - previous[1])
                                    if previous is not None else (0, 0))
                e = pygame.event.Event(e.type, attrs)
            self.editor.handle_event(e)
            return
        if self.simlog_view_open:
            if e.type == pygame.QUIT:
                self._close_simlog_view()
                self._open_administration("quit")
                return
            if e.type == pygame.JOYHATMOTION:
                _, y = e.value
                if y:
                    self._scroll_simlog_view(6 if y < 0 else -6)
                return
            if e.type == pygame.MOUSEWHEEL:
                self._scroll_simlog_view(-e.y * 3)
                return
            if e.type == pygame.KEYDOWN:
                if e.key in (pygame.K_F4, pygame.K_ESCAPE):
                    self._close_simlog_view()
                    return
                if e.key == pygame.K_m:
                    self.simlog_view_map = not self.simlog_view_map
                    return
                if e.key == pygame.K_f and self.simlog_view_map:
                    self.simlog_map_fit = (
                        simlog_map.FIT_UNITS
                        if self.simlog_map_fit == simlog_map.FIT_WORLD
                        else simlog_map.FIT_WORLD)
                    return
                if self.simlog_view_map:
                    return
                if e.key in (pygame.K_UP, pygame.K_DOWN, pygame.K_PAGEUP,
                             pygame.K_PAGEDOWN, pygame.K_HOME, pygame.K_END):
                    amount = {pygame.K_UP: -1, pygame.K_DOWN: 1,
                              pygame.K_PAGEUP: -15, pygame.K_PAGEDOWN: 15,
                              pygame.K_HOME: -10000, pygame.K_END: 10000}[e.key]
                    self._scroll_simlog_view(amount)
                    return
                return
            return
        if self.autocrew_overview_open:
            if e.type == pygame.QUIT:
                self.autocrew_overview_open = False
                self._open_administration("quit")
            elif (e.type == pygame.KEYDOWN
                  and e.key in (pygame.K_F3, pygame.K_ESCAPE)):
                self.autocrew_overview_open = False
                self._clear_station_input()
            return
        if self.weather_station_open:
            # The read-only panel owns input: 0 / Esc close it, nothing leaks
            # to the station underneath.
            if e.type == pygame.QUIT:
                self.weather_station_open = False
                self._open_administration("quit")
            elif (e.type == pygame.KEYDOWN
                  and e.key in (pygame.K_0, pygame.K_KP0, pygame.K_ESCAPE)):
                self.weather_station_open = False
                self._clear_station_input()
            return
        if (self.local_side == "uboot" and not self.in_menu
                and not self.administration_open
                and e.type in (pygame.MOUSEBUTTONDOWN, pygame.MOUSEBUTTONUP,
                               pygame.MOUSEMOTION, pygame.MOUSEWHEEL,
                               pygame.JOYAXISMOTION, pygame.JOYBUTTONDOWN,
                               pygame.JOYBUTTONUP, pygame.JOYHATMOTION)):
            # The frigate's pointer and trackball controls do not exist aboard
            # the boat; only the boat's chart and page tabs take the mouse.
            if e.type in (pygame.MOUSEBUTTONDOWN, pygame.MOUSEBUTTONUP,
                          pygame.MOUSEMOTION, pygame.MOUSEWHEEL):
                uboot_local.handle_pointer(self, e)
            return
        if e.type == pygame.MOUSEBUTTONUP and e.button == 1:
            if self._local_station_input_locked():
                return
            if self._map_drag is not None and not self._map_drag_moved:
                if self.station is Station.OPZ:
                    self._pin_tooltip_at(getattr(e, "pos", None))
                    self._map_drag = None
                    self._map_drag_moved = False
                    return
                canvas = self._window_to_canvas(getattr(e, "pos", None))
                hit = map_hit_target(self, canvas) if canvas is not None else None
                hit_id = hit.get("id", "") if isinstance(hit, dict) else ""
                parts = hit_id.split(":")
                if len(parts) >= 3 and parts[:2] == ["map", "sonar"] \
                        and parts[2].isascii() and parts[2].isdigit():
                    contact_id = int(parts[2])
                    contact = next((item for item in self.sonar.active_contacts()
                                    if item.id == contact_id), None)
                    if contact is not None:
                        self.selected_contact = contact
                        self._pin_tooltip_at(getattr(e, "pos", None))
                elif (self.station is Station.HELICOPTER and canvas is not None
                      and hit_id.startswith("chart:")):
                    self.map_view.set_rect(config.MAP_RECT)
                    x_nm, y_nm = self.map_view.screen_to_world(*canvas)
                    if self.set_helicopter_waypoint(x_nm, y_nm) is True:
                        bearing, distance = self._helo_waypoint_polar()
                        self.flash(message("runtime.helo.waypoint",
                                           bearing=f"{bearing:03.0f}",
                                           range=f"{distance:.0f}"), 1.5)
                else:
                    self._pin_tooltip_at(getattr(e, "pos", None))
            self._map_drag = None
            self._map_drag_moved = False
            return
        if e.type == pygame.QUIT:
            if not self.quit_confirm:
                self._open_administration("quit")
            return
        if (e.type == pygame.KEYDOWN and e.key == pygame.K_ESCAPE
                and self.pinned_tooltip is not None):
            self.pinned_tooltip = None
            self._tooltip_anchor = None
            return
        if self.administration_open:
            if e.type == pygame.KEYDOWN:
                if (self.live_traffic_field is not None
                        and e.key not in (pygame.K_RETURN, pygame.K_KP_ENTER,
                                         pygame.K_ESCAPE)):
                    self.live_traffic_field.handle_event(e)
                else:
                    self._handle_administration_key(e.key)
            elif e.type == pygame.TEXTINPUT and self.live_traffic_field is not None:
                self.live_traffic_field.handle_text(e.text)
            elif e.type == pygame.MOUSEBUTTONDOWN and e.button == 1:
                canvas = self._window_to_canvas(getattr(e, "pos", None))
                if canvas is not None:
                    if self.commander_open:
                        self.commander.handle_click(self, canvas)
                    elif self.options_open:
                        rows = self._option_rows()
                        for page, rect in enumerate(self._options_page_rects()):
                            if rect.collidepoint(canvas):
                                self._set_options_page(page)
                                break
                        for index, rect in enumerate(self._options_row_rects()[:len(rows)]):
                            if rect.collidepoint(canvas):
                                self.options_sel = index
                                name = rows[index]
                                if name in ("live_traffic", "commander"):
                                    self._open_administration(name)
                                elif name == "local_side":
                                    self._toggle_local_side()
                                break
            return
        if (e.type == pygame.TEXTINPUT and getattr(e, "text", "") == "?"
                and self.input_mode is None):
            # Layout-independent help key (US Shift+/, DE Shift+ß).
            self._open_administration("help")
            return
        if e.type != pygame.KEYDOWN:
            if self.input_mode is not None or self.in_menu or self.game_over:
                return
            if self.commander.confirm_visible(self):
                if e.type == pygame.MOUSEBUTTONDOWN and e.button == 1:
                    canvas = self._window_to_canvas(getattr(e, "pos", None))
                    if (canvas is not None
                            and self.commander.handle_confirm_click(self, canvas)):
                        return
            if self._local_station_input_locked():
                return
        if e.type == pygame.KEYDOWN:
            if self.in_menu:
                if e.key == pygame.K_F1:
                    self._open_administration("help")
                elif e.key == pygame.K_F9:
                    self._open_administration("commander")
                else:
                    self._handle_menu_key(e.key)
                return
            if self.local_side == "uboot" and not self._uboot_dispatch:
                uboot_local.handle_key(self, e)
                return
            if self.input_mode is not None and self._local_station_input_locked():
                pass
            elif self.input_mode is not None:
                self._handle_numeric_input(e.key)
                return
            if e.key == pygame.K_F9:
                self._open_administration("commander")
                return
            if self.commander.confirm_visible(self):
                if self.commander.handle_confirm_key(self, e.key):
                    return
            if (self.plot_mode and not self.game_over
                    and self._handle_plot_key(e.key, getattr(e, "mod", 0))):
                return
            if e.key == pygame.K_ESCAPE:
                self._open_administration("quit")
                return
            if e.key == pygame.K_F1:
                self._open_administration("help")
                return
            if e.key == pygame.K_F10:
                self._open_administration("options")
                return
            if e.key == pygame.K_F11:
                self.feed_overlay_open = not self.feed_overlay_open
                self.feed_overlay_scroll = 0
                return
            if e.key == pygame.K_F8:
                self._open_analyzer_in_game()
                return
            if e.key == pygame.K_F2:
                enabled = self.autocrew.toggle(self.station, self.sim_t)
                self._clear_station_input()
                self.flash(message("autocrew.toggled.on" if enabled
                                   else "autocrew.toggled.off",
                                   station=display_value(
                                       "station", self.station.name, self.tr)))
                return
            if e.key == pygame.K_F3:
                self._clear_station_input()
                self.autocrew_overview_open = True
                return
            if e.key in (pygame.K_0, pygame.K_KP0):
                self._clear_station_input()
                self.pinned_tooltip = None
                self._tooltip_anchor = None
                self.weather_station_open = True
                return
            if e.key == pygame.K_F4:
                self._open_simlog_view()
                return
            if (e.key == pygame.K_n and self.station is not Station.SONAR
                    and not (self.station is Station.HELICOPTER
                             and self.station_page == 3)):
                self._open_administration("nations")
                return
            if e.key in (pygame.K_s, pygame.K_l) and not (
                    e.key == pygame.K_l and self.station is Station.OPZ):
                self._open_administration("save" if e.key == pygame.K_s else "load")
                return
            if pygame.K_1 <= e.key <= pygame.K_9:
                destination = list(Station)[e.key - pygame.K_1]
                self.pinned_tooltip = None
                self._tooltip_anchor = None
                if destination is self.station:
                    # Page cycle: clear held controls, but keep the station's
                    # audio stream continuous (no stop/restart blip).
                    self._clear_station_input()
                    if self.station is Station.SONAR:
                        self.sonar_page = station_page_step(
                            Station.SONAR, self.sonar_page, 1)
                    elif len(STATION_PAGES[self.station]) > 1:
                        self.station_page = station_page_step(
                            self.station, self.station_page, 1)
                else:
                    self._clear_controls()
                    self.station = destination
                    self.station_page = (2 if destination is Station.HELICOPTER
                                         else 0)
                return
            if e.key == pygame.K_TAB:
                self._clear_controls()
                self.pinned_tooltip = None
                self._tooltip_anchor = None
                order = list(Station)
                step = -1 if getattr(e, "mod", 0) & pygame.KMOD_SHIFT else 1
                self.station = order[(order.index(self.station) + step) % len(order)]
                self.station_page = (2 if self.station is Station.HELICOPTER
                                     else 0)
                return
            if self.game_over:
                if e.key == pygame.K_r:
                    definition = self.custom_mission_definition
                    if definition is None or not self.start_custom_mission(
                            json.loads(json.dumps(definition))):
                        self.reset(self.seed)
                elif e.key == pygame.K_m:
                    self._return_to_main_menu()
                return
            if self._local_station_input_locked():
                return
            if e.key == pygame.K_p and self._plot_view() is not None:
                self.toggle_plot_mode()
                return
            if (e.key in (pygame.K_RETURN, pygame.K_KP_ENTER)
                    and getattr(e, "mod", 0) & pygame.KMOD_CTRL):
                if self.station is Station.WEAPONS:
                    self.launch_torpedo()
                    return
                if self.station is Station.OPZ:
                    self.launch_essm()
                    return
                if self.station is Station.HELICOPTER:
                    self.launch_helo_torpedo()
                    return
            if (self.station is Station.HELICOPTER and self.station_page == 3
                    and e.key in (pygame.K_PAGEUP, pygame.K_PAGEDOWN)):
                step = 1 if e.key == pygame.K_PAGEDOWN else -1
                self.helo_acoustic_page = (self.helo_acoustic_page + step) % 3
                return
            if self.station is Station.SONAR:
                mods = getattr(e, "mod", 0)
                if e.key == pygame.K_c and mods & pygame.KMOD_SHIFT:
                    self._cycle_sonar_display_palette()
                    return
                if e.key == pygame.K_h and mods & pygame.KMOD_SHIFT:
                    self._cycle_sonar_display_history()
                    return
                if e.key in (pygame.K_i, pygame.K_o) and mods & (
                        pygame.KMOD_SHIFT | pygame.KMOD_CTRL):
                    delta = -1.0 if e.key == pygame.K_i else 1.0
                    if mods & pygame.KMOD_SHIFT:
                        self._adjust_sonar_display_contrast(delta * .2)
                    else:
                        self._adjust_sonar_display_black(delta * .01)
                    return
                if e.key in (pygame.K_PAGEUP, pygame.K_PAGEDOWN):
                    self.sonar_page = station_page_step(
                        Station.SONAR,
                        self.sonar_page, 1 if e.key == pygame.K_PAGEDOWN else -1)
                    return
                if e.key == pygame.K_w:
                    pulse = self.sonar.cycle_pulse()
                    self.flash(message("runtime.sonar.pulse",
                                       pulse=message(f"sonar.pulse.{pulse.lower()}")))
                    return
                if e.key == pygame.K_e:
                    if self.measure_sonar_bt() is True:
                        depth = self.sonar.bt_profile["thermocline_m"]
                        self.flash(message("runtime.bt.measured", depth=f"{depth:.0f}"))
                        # The log of the listening side: never the frigate's
                        # feed while the uConsole plays the submarine.
                        notice = message("runtime.bt.feed", depth=f"{depth:.0f}")
                        if self._sonar_ctx is self._frigate_sonar:
                            self.feed.add(self.world.format_time(), "sonar", notice)
                        elif self._opfor is not None and self._sonar_ctx is self._opfor.station:
                            self._opfor.notice(self.sim_t, "sonar", notice,
                                               stamp=self.world.format_time())
                    else:
                        self.flash(message("runtime.bt.cooldown",
                                           seconds=f"{self.sonar.bt_cooldown:.0f}"))
                    return
                if e.key in (pygame.K_u, pygame.K_v):
                    requested = config.clamp(
                        self.sonar.towed_depth_target_m
                        + (-10.0 if e.key == pygame.K_u else 10.0),
                        config.SONAR_TOWED_DEPTH_MIN_M,
                        config.SONAR_TOWED_DEPTH_MAX_M)
                    self.set_sonar_tow_depth(requested)
                    depth = self.sonar.towed_depth_target_m
                    self.flash(message("runtime.tas.depth", depth=f"{depth:.0f}"))
                    return
                if e.key == pygame.K_r:
                    self._begin_numeric_input("bearing")
                    return
                if e.key == pygame.K_j:
                    self.sonar_audio_enabled = not self.sonar_audio_enabled
                    self._stop_sonar_audio()
                    self.flash(message("runtime.sonar_audio.on" if self.sonar_audio_enabled
                                       else "runtime.sonar_audio.off"))
                    return
                if e.key == pygame.K_k and self.sonar_page == 3:
                    self._tma_key(e)
                    return
                if e.key == pygame.K_k:
                    self._cycle_sonar_harmonic()
                    return
                if e.key == pygame.K_x and self.sonar_page in (0, 4):
                    self._tas_side_key(e)
                    return
                if e.key in (pygame.K_z, pygame.K_x) and self.sonar_page in (1, 2):
                    self._sonar_cursor_key(e)
                    return
                if self.sonar_page == 3 and e.key in (pygame.K_z, pygame.K_x,
                                                      pygame.K_q, pygame.K_k):
                    self._tma_key(e)
                    return
                if e.key == pygame.K_q:
                    if getattr(e, "mod", 0) & pygame.KMOD_SHIFT:
                        self.set_sonar_vernier(not self.sonar_tools.vernier)
                        self.flash(message("runtime.vernier.on" if self.sonar_tools.vernier
                                           else "runtime.vernier.off"), 1.5)
                    else:
                        seconds = self.sonar_tools.cycle_integration()
                        self.flash(message("runtime.integration", seconds=seconds), 1.5)
                    return
                if e.key == pygame.K_d:
                    mode = ("BROADBAND" if self.sonar.audition_mode == "FILTERED"
                            else "FILTERED")
                    self._set_sonar_audition_mode(mode)
                    return
                if e.key in (pygame.K_a, pygame.K_b, pygame.K_h) \
                        and not getattr(e, "mod", 0) & pygame.KMOD_SHIFT:
                    self._set_sonar_audition_mode({pygame.K_a: "BROADBAND",
                                                   pygame.K_b: "FILTERED",
                                                   pygame.K_h: "HETERODYNE"}[e.key])
                    return
                if e.key in (pygame.K_COMMA, pygame.K_PERIOD):
                    self.sonar_volume = round(config.clamp(self.sonar_volume +
                        (.1 if e.key == pygame.K_PERIOD else -.1), 0.0, 1.0), 1)
                    self.flash(message("runtime.listen.volume",
                                        volume=f"{self.sonar_volume:.0%}"))
                    return
                if e.key in (pygame.K_LEFT, pygame.K_RIGHT):
                    mods = getattr(e, "mod", 0)
                    step = .1 if mods & pygame.KMOD_CTRL else (5.0 if mods & pygame.KMOD_SHIFT else .5)
                    self.set_sonar_listen_bearing((self.sonar.listen_bearing +
                        (step if e.key == pygame.K_RIGHT else -step)) % 360.0)
                    return
                if e.key in (pygame.K_UP, pygame.K_DOWN):
                    self._cycle_selected_contact(1 if e.key == pygame.K_DOWN else -1)
                    return
                if e.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                    contact = self.selected_contact
                    if self.sonar.focus_locked:
                        if self.clear_sonar_focus() is True:
                            self.flash(message("runtime.listen.manual"))
                    elif contact is not None and self.set_sonar_focus(contact) is True:
                        self.flash(message("runtime.listen.follow", contact=contact.id))
                    else:
                        self.flash(message("runtime.listen.no_contact"))
                    return
            if self.station in (Station.OPZ, Station.RADAR) and \
                    e.key in (pygame.K_PAGEUP, pygame.K_PAGEDOWN):
                self._cycle_radar_range(
                    1 if e.key == pygame.K_PAGEUP else -1)
                return
            if e.key in (pygame.K_UP, pygame.K_DOWN):
                if self.station is Station.DAMAGE:
                    self.dmg_team = (self.dmg_team - 1 +
                                     (1 if e.key == pygame.K_DOWN else -1)) % 3 + 1
                elif self.station is Station.WEAPONS:
                    self.held.add(e.key)
                elif self.station is Station.BRIDGE:
                    self.ship.cycle_telegraph(
                        1 if e.key == pygame.K_UP else -1)
                    self.flash(message("runtime.telegraph", order=self.ship.telegraph), 1.5)
                elif self.station is Station.ENGINE:
                    self._cycle_engine_telegraph(
                        1 if e.key == pygame.K_UP else -1)
                    self.flash(message("runtime.telegraph", order=self.ship.telegraph), 1.5)
                elif self.station is Station.HELICOPTER:
                    self._adjust_helo_waypoint(
                        range_delta=1.0 if e.key == pygame.K_UP else -1.0)
                elif self.station is Station.RADIO:
                    self._cycle_hfdf(1 if e.key == pygame.K_DOWN else -1)
                elif self.station in (Station.OPZ, Station.RADAR):
                    self._cycle_opz_track(1 if e.key == pygame.K_DOWN else -1)
                elif self.station is Station.ELOKA:
                    self._cycle_eloka_track(1 if e.key == pygame.K_DOWN else -1)
                return
            if e.key in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_BACKSPACE) and self.station is Station.DAMAGE:
                if e.key == pygame.K_BACKSPACE:
                    destination = self.damage.teams[self.dmg_team]
                    if destination is not None:
                        self.unassign_damage_team(self.dmg_team, destination)
                    self.flash(message("runtime.team.withdrawn", team=self.dmg_team))
                else:
                    self._assign_selected_team()
                return
            if e.key in (pygame.K_RETURN, pygame.K_KP_ENTER) \
                    and self.station is Station.RADIO:
                self.capture_hfdf()
                return
            if e.key in (pygame.K_RETURN, pygame.K_KP_ENTER) \
                    and self.station is Station.OPZ:
                self.confirm_live_engagement()
                return
            if e.key == pygame.K_n and self.station is Station.HELICOPTER and self.station_page == 3:
                self.set_helicopter_audio_notch(not self.helo_audition.notch_enabled)
                return
            if (e.key == pygame.K_n and self.station is Station.SONAR
                    and getattr(e, "mod", 0) & pygame.KMOD_SHIFT):
                current = getattr(self.sonar, "operator_notch_hz", None)
                cursor = self.sonar_tools.lofar_cursor_hz
                self.set_sonar_operator_notch(None if current == cursor else cursor)
                notch = self.sonar.operator_notch_hz
                if notch is None:
                    self.flash(message("runtime.operator_notch.off"), 1.5)
                else:
                    self.flash(message("runtime.operator_notch.on",
                                       frequency=f"{notch:.1f}"), 1.5)
                return
            if e.key == pygame.K_n:
                if self.station is Station.SONAR:
                    self.set_sonar_notch(not self.sonar.notch_enabled)
                    self.flash(message("runtime.notch.on" if self.sonar.notch_enabled
                                       else "runtime.notch.off"), 1.5)
                else:
                    self.nations_open = not self.nations_open
            elif e.key == pygame.K_SPACE and self.station is Station.SONAR:
                self.set_sonar_peak_hold(not self.sonar.peak_hold)
                self.flash(message("runtime.peak_hold.on" if self.sonar.peak_hold
                                   else "runtime.peak_hold.off"), 1.5)
            elif e.key == pygame.K_SPACE and self.station is Station.OPZ:
                self._toggle_opz_mark()
            elif e.key == pygame.K_l and self.station is Station.OPZ:
                if getattr(e, "mod", 0) & pygame.KMOD_SHIFT:
                    self._dissolve_opz_fusion()
                else:
                    self._create_opz_fusion()
            elif e.key == pygame.K_j and self.station is Station.OPZ:
                self._begin_track_id_input()
            elif e.key == pygame.K_j and self.station is Station.HELICOPTER:
                if not self.helo_audio_enabled and not self.helicopter_audio_ready():
                    self.flash(message("runtime.sonar_audio.receiver_required"))
                    return
                self.helo_audio_enabled = not self.helo_audio_enabled
                self._stop_sonar_audio()
                self.flash(message("runtime.sonar_audio.on" if self.helo_audio_enabled
                                   else "runtime.sonar_audio.off"))
            elif e.key in (pygame.K_COMMA, pygame.K_PERIOD) \
                    and self.station is Station.BRIDGE and self.station_page == 2:
                self._cycle_lookout_range(1 if e.key == pygame.K_PERIOD else -1)
            elif e.key in (pygame.K_COMMA, pygame.K_PERIOD) \
                    and self.station is Station.HELICOPTER and self.station_page == 3:
                self.sonar_volume = round(config.clamp(self.sonar_volume +
                    (.1 if e.key == pygame.K_PERIOD else -.1), 0.0, 1.0), 1)
                self.flash(message("runtime.listen.volume",
                                   volume=f"{self.sonar_volume:.0%}"))
            elif e.key == pygame.K_BACKSPACE and self.station is Station.OPZ:
                self.opz_fusion.marked.clear()
            elif e.key == pygame.K_DELETE and self.station is Station.OPZ:
                self._toggle_opz_suppression()
            elif e.key in (pygame.K_EQUALS, pygame.K_PLUS, pygame.K_KP_PLUS):
                self.ship.cycle_telegraph(1)
                self.flash(message("runtime.telegraph", order=self.ship.telegraph), 1.5)
            elif e.key in (pygame.K_MINUS, pygame.K_KP_MINUS):
                self.ship.cycle_telegraph(-1)
                self.flash(message("runtime.telegraph", order=self.ship.telegraph), 1.5)
            elif e.key in (pygame.K_i, pygame.K_o) and self.station is Station.SONAR:
                self._adjust_sonar_gain(-3.0 if e.key == pygame.K_i else 3.0)
            elif e.key in (pygame.K_i, pygame.K_o) and self.station is Station.HELICOPTER and self.station_page == 3:
                self.set_helicopter_audio_gain(config.clamp(
                    self.helo_audition.gain_db + (-3.0 if e.key == pygame.K_i else 3.0), -12.0, 24.0))
            elif e.key == pygame.K_i and self.station is Station.OPZ:
                if self.set_ciws_authorized(not self.ciws_authorized) is True:
                    self.flash(message(
                        "runtime.ciws.authorized" if self.ciws_authorized
                        else "runtime.ciws.withheld"), 1.5)
            elif e.key == pygame.K_a and (self.station is not Station.SONAR
                                           or getattr(e, "mod", 0) & pygame.KMOD_SHIFT):
                if self.station is Station.SONAR:
                    result = self.send_active_ping()
                    if result == "sonar_down":
                        self.flash(message("runtime.sonar.down"), 3.0)
                    elif result is True:
                        self.flash(message("runtime.ping.sent"), 1.5)
                elif self.station is Station.ENGINE:
                    if self.set_quiet_mode(not self.ship.quiet_mode) is True:
                        self.flash(message("runtime.quiet.on" if self.ship.quiet_mode
                                           else "runtime.quiet.off"))
                elif self.station is Station.HELICOPTER:
                    result = self.send_helicopter_dipping_ping()
                    self.flash(message("runtime.helo.dip_ping_sent" if result is True
                                       else "runtime.helo.dip_ping_unavailable"))
                elif self.station is Station.ELOKA:
                    self.set_ecm_auto(not self.ecm_jammer.auto_enabled)
                    self.flash(message("runtime.eloka.auto_on"
                                       if self.ecm_jammer.auto_enabled else
                                       "runtime.eloka.auto_off"), 1.5)
            elif e.key == pygame.K_r:
                if self.station in (Station.OPZ, Station.RADAR):
                    domain = ("air" if getattr(e, "mod", 0)
                              & pygame.KMOD_SHIFT else "surface")
                    self.toggle_radar(domain)
                elif self.station is Station.HELICOPTER and self.station_page == 3:
                    self.set_helicopter_listen_bearing(None)
            elif e.key == pygame.K_m:
                if self.station in (Station.SONAR, Station.WEAPONS,
                                    Station.HELICOPTER):
                    self.set_target()
                elif self.station in (Station.OPZ, Station.RADAR):
                    self.designate_opz_track()
                elif self.station is Station.ELOKA:
                    self.eloka_audio_enabled = not self.eloka_audio_enabled
                    self.flash(message("runtime.eloka_audio.on"
                                       if self.eloka_audio_enabled else
                                       "runtime.eloka_audio.off"))
            elif e.key == pygame.K_u and self.station in (Station.BRIDGE,
                                                           Station.ENGINE):
                self._begin_numeric_input("course")
            elif e.key == pygame.K_LEFT:
                if self.station is Station.BRIDGE:
                    self.held.add(e.key)
                elif self.station is Station.WEAPONS:
                    self._cycle_selected_contact(-1)
                elif self.station in (Station.OPZ, Station.RADAR):
                    self._cycle_asm_track(-1)
                elif self.station is Station.DAMAGE:
                    n = len(self.damage.compartments)
                    self.dmg_cursor = (self.dmg_cursor - 1) % n
                elif self.station is Station.HELICOPTER:
                    if self.station_page == 3:
                        self.set_helicopter_listen_bearing(
                            ((self.helo_listen_bearing or 0.0) - 5.0) % 360.0)
                    else:
                        self._adjust_helo_waypoint(bearing_delta=-15.0)
            elif e.key == pygame.K_RIGHT:
                if self.station is Station.BRIDGE:
                    self.held.add(e.key)
                elif self.station is Station.WEAPONS:
                    self._cycle_selected_contact(1)
                elif self.station in (Station.OPZ, Station.RADAR):
                    self._cycle_asm_track(1)
                elif self.station is Station.DAMAGE:
                    n = len(self.damage.compartments)
                    self.dmg_cursor = (self.dmg_cursor + 1) % n
                elif self.station is Station.HELICOPTER:
                    if self.station_page == 3:
                        self.set_helicopter_listen_bearing(
                            ((self.helo_listen_bearing or 0.0) + 5.0) % 360.0)
                    else:
                        self._adjust_helo_waypoint(bearing_delta=15.0)
            elif e.key == pygame.K_c:
                if self.station in (Station.SONAR, Station.HELICOPTER):
                    self._cycle_classification()
                elif self.station in (Station.OPZ, Station.RADAR):
                    self._cycle_opz_classification()
                elif self.station is Station.ELOKA:
                    self._cycle_eloka_annotation()
            elif e.key == pygame.K_j and self.station is Station.ELOKA:
                if getattr(e, "mod", 0) & pygame.KMOD_SHIFT:
                    technique = self._cycle_jamming_technique(
                        self.selected_eloka_track())
                    technique_names = {
                        "noise": message("eloka.technique.noise"),
                        "rgpo": message("eloka.technique.rgpo"),
                        "vgpo": message("eloka.technique.vgpo"),
                        "false_targets": message(
                            "eloka.technique.false_targets"),
                    }
                    notice = (message("runtime.eloka.technique",
                                      technique=technique_names[technique])
                              if technique in technique_names else
                              message("runtime.eloka.jamming_off"))
                    self.flash(notice, 1.5)
                else:
                    result = self.deploy_jamming(self.selected_eloka_track())
                    self.flash(message("runtime.eloka.jamming_on"
                                       if result is True else
                                       "runtime.eloka.jamming_off"), 1.5)
            elif e.key == pygame.K_b and (self.station is not Station.SONAR
                                           or getattr(e, "mod", 0) & pygame.KMOD_SHIFT):
                if self.station is Station.SONAR:
                    self._cycle_sonar_mode()
                elif self.station in (Station.WEAPONS, Station.HELICOPTER):
                    if self.station is Station.HELICOPTER and getattr(e, "mod", 0) & pygame.KMOD_SHIFT:
                        self.set_helicopter_buoy_mode(
                            "ACTIVE" if self.helo_buoy_mode == "PASSIVE" else "PASSIVE")
                        self.flash(message("helo.buoy_mode.active" if self.helo_buoy_mode == "ACTIVE"
                                           else "helo.buoy_mode.passive"))
                    else:
                        self.deploy_buoys()
                elif self.station is Station.ELOKA:
                    self._cycle_eloka_filter("band")
                elif self.station is Station.OPZ:
                    self._mark_newest_blip()
            elif e.key == pygame.K_y:
                if self.station is Station.SONAR:
                    if self.damage.station_down("sonar"):
                        self.flash(message("runtime.sonar.down"), 3.0)
                    else:
                        toggle_tas(self, self.tr)
                elif self.station is Station.HELICOPTER:
                    deploy = self.helo.dip_state in ("STOWED", "RETRIEVING")
                    result = self.set_helicopter_dipping(deploy)
                    if result is True:
                        self.flash(message("runtime.helo.dip_deploy" if deploy
                                           else "runtime.helo.dip_retrieve"))
                    elif result == "weather_unsafe":
                        self.flash(message("runtime.helo.weather_unsafe"))
                    else:
                        self.flash(message("runtime.helo.dip_unavailable"))
            elif e.key == pygame.K_h and self.station in (Station.WEAPONS,
                                                           Station.HELICOPTER):
                self.toggle_helo()
            elif e.key == pygame.K_h and self.station is Station.OPZ:
                self.opz_fusion.show_suppressed = not self.opz_fusion.show_suppressed
                self.opz_selected_track_id = None
            elif e.key == pygame.K_d:
                if self.station in (Station.WEAPONS, Station.HELICOPTER):
                    if self.station is Station.HELICOPTER and self.station_page == 3 \
                            and getattr(e, "mod", 0) & pygame.KMOD_SHIFT:
                        modes = ("BROADBAND", "FILTERED", "HETERODYNE")
                        self.set_helicopter_audio_mode(modes[
                            (modes.index(self.helo_audition.audition_mode) + 1) % len(modes)])
                    else:
                        self.launch_helo_torpedo()
            elif e.key == pygame.K_v and self.station is Station.WEAPONS:
                self.deploy_nixie()
            elif e.key in (pygame.K_u, pygame.K_v) \
                    and self.station is Station.HELICOPTER:
                requested = config.clamp(
                    self.helo.dip_depth_target_m
                    + (-10.0 if e.key == pygame.K_u else 10.0),
                    config.HELO_DIP_DEPTH_MIN_M, config.HELO_DIP_DEPTH_MAX_M)
                if self.set_helicopter_dip_depth(requested) is True:
                    self.flash(message("runtime.helo.dip_depth",
                                       depth=f"{self.helo.dip_depth_target_m:.0f}"))
            elif e.key == pygame.K_e:
                if self.station in (Station.OPZ, Station.RADAR):
                    self.launch_essm()
                elif self._map_station_visible():
                    self.map_view.set_rect(config.MAP_RECT)
                    self.map_view.zoom(config.MAP_ZOOM_WHEEL_FACTOR)
            elif e.key == pygame.K_g and self.station in (Station.OPZ,
                                                           Station.RADAR):
                self.launch_chaff()
            elif e.key == pygame.K_g and self.station is Station.SONAR:
                self._toggle_sonar_release()
            elif e.key == pygame.K_g and self.station is Station.HELICOPTER:
                if getattr(e, "mod", 0) & pygame.KMOD_SHIFT:
                    self._toggle_sonar_release()
                else:
                    self._cycle_helo_contact(1)
            elif e.key == pygame.K_t:
                if self.station is Station.WEAPONS:
                    self.launch_torpedo()
                elif self.station is Station.SONAR:
                    self.set_sonar_tma_enabled(not self.sonar.tma_enabled)
                    self.flash(message("runtime.tma.on" if self.sonar.tma_enabled
                                       else "runtime.tma.off"), 1.5)
                elif self.station is Station.HELICOPTER:
                    if self.station_page == 3:
                        sources = ["DIP", *(f"SB{b.seq}" for b in self.buoys
                                            if b.active and b.mode == "PASSIVE")]
                        current = sources.index(self.helo_listen_source) \
                            if self.helo_listen_source in sources else -1
                        self.set_helicopter_listen_source(sources[(current + 1) % len(sources)])
                        return
                    self.helo_sensor_source = ("BUOY" if self.helo_sensor_source == "DIP"
                                               else "DIP")
                    if self.helo_sensor_source == "BUOY":
                        seq = next((seq for seq in sorted(
                            getattr(self.selected_contact, "buoy_reports", {}))
                            if any(b.seq == seq for b in self.buoys)),
                            self.buoys[0].seq if self.buoys else None)
                        if seq is not None:
                            self.set_helicopter_listen_source(f"SB{seq}")
                    else:
                        self.set_helicopter_listen_source("DIP")
                    self.flash(message("helo.source.buoy" if self.helo_sensor_source == "BUOY"
                                       else "helo.source.dip"))
            elif e.key == pygame.K_f:
                if self.station is Station.SONAR and getattr(e, "mod", 0) & pygame.KMOD_SHIFT:
                    bands = analysis_tools.DEMON_BANDS_HZ
                    current = tuple(self.sonar.receiver.demon_band_hz)
                    index = bands.index(current) if current in bands else -1
                    low, high = bands[(index + 1) % len(bands)]
                    self.set_sonar_demon_band(low, high)
                    self.flash(message("runtime.demon_band", low=f"{low:.0f}",
                                       high=f"{high:.0f}"), 1.5)
                elif self.station is Station.SONAR and getattr(e, "mod", 0) & pygame.KMOD_CTRL:
                    offsets = analysis_tools.HETERODYNE_OFFSETS_HZ
                    current = self.sonar.heterodyne_hz
                    index = offsets.index(current) if current in offsets else -1
                    self.set_sonar_heterodyne(offsets[(index + 1) % len(offsets)])
                    self.flash(message("runtime.heterodyne",
                                       frequency=f"{self.sonar.heterodyne_hz:.0f}"), 1.5)
                elif self.station is Station.SONAR:
                    self._cycle_sonar_band()
                elif self.station is Station.ELOKA:
                    self._cycle_eloka_filter(
                        "threat" if getattr(e, "mod", 0) & pygame.KMOD_SHIFT
                        else "status")
                elif self.station is Station.OPZ:
                    if getattr(e, "mod", 0) & pygame.KMOD_SHIFT:
                        self._cycle_opz_contact_filter()
                    else:
                        self._cycle_opz_affiliation()
                elif self.station is Station.WEAPONS:
                    if self.set_flak_authorized(not self.flak_authorized) is True:
                        self.flash(message(
                            "runtime.flak.authorized" if self.flak_authorized
                            else "runtime.flak.withheld"), 1.5)
                elif self.station is Station.HELICOPTER:
                    if self.station_page == 3 and getattr(e, "mod", 0) & pygame.KMOD_SHIFT:
                        bands = tuple(SONAR_BAND_PRESETS)
                        self.set_helicopter_audio_band(bands[
                            (bands.index(self.helo_audio_band) + 1) % len(bands)])
                        return
                    if self.selected_contact is None:
                        return
                    contact = self.selected_contact
                    result = self.qualify_helicopter_contact(
                        contact, not contact.helo_qualified)
                    if result is True:
                        self.flash(message("helo.contact.confirmed" if contact.helo_qualified
                                           else "helo.contact.unconfirmed", contact=contact.id))
            elif e.key == pygame.K_k:
                if self.station is Station.OPZ:
                    self.opz_map_follow = not self.opz_map_follow
                    if self.opz_map_follow:
                        self._configure_opz_map_view()
                        self.opz_map_view.cx = self.ship.x
                        self.opz_map_view.cy = self.ship.y
                        self.opz_map_view.clamp_center()
                    self.flash(message("runtime.map_follow.on" if self.opz_map_follow
                                       else "runtime.map_follow.off"), 1.5)
                elif self._map_station_visible():
                    self.map_follow = not self.map_follow
                    self.flash(message("runtime.map_follow.on" if self.map_follow
                                       else "runtime.map_follow.off"), 1.5)
            elif e.key == pygame.K_q and self._map_station_visible():
                self.map_view.set_rect(config.MAP_RECT)
                self.map_view.zoom(1.0 / config.MAP_ZOOM_WHEEL_FACTOR)
            elif e.key == pygame.K_v and self.station in (Station.BRIDGE,
                                                          Station.ENGINE):
                self._begin_numeric_input("speed")
        elif e.type == pygame.JOYAXISMOTION:
            if e.axis == 0:
                if self.station is Station.BRIDGE:
                    self._joy_turn = (1 if e.value > 0.25 else
                                      -1 if e.value < -0.25 else 0)
                else:
                    self._joy_turn = 0
                    self._joy_x_acc += e.value * 0.6
                    if abs(self._joy_x_acc) > 0.8:
                        step = 1 if self._joy_x_acc > 0.0 else -1
                        self._joy_x_acc = 0.0
                        self._joy_horizontal_step(step)
            elif e.axis == 1:
                self._joy_acc += e.value * 0.6
                if self._joy_acc > 0.8:
                    self._joy_acc = 0.0
                    self._joy_step(1)
                elif self._joy_acc < -0.8:
                    self._joy_acc = 0.0
                    self._joy_step(-1)
        elif e.type == pygame.JOYBUTTONDOWN:
            if self.station is Station.DAMAGE and e.button in (0, 1, 2):
                self.dmg_team = e.button + 1
                self._assign_selected_team()
        elif e.type == pygame.MOUSEWHEEL:
            # Wheel-Events haben nicht in allen SDL-Versionen ein pos.
            if self.in_menu or self.game_over or e.y == 0:
                return
            if self.feed_overlay_open:
                canvas = self._window_to_canvas(
                    getattr(e, "pos", None) or pygame.mouse.get_pos())
                if canvas is not None and self.feed_overlay_rect().collidepoint(canvas):
                    # Wheel up reads older entries.
                    self.feed_overlay_scroll = max(0, self.feed_overlay_scroll + e.y * 3)
                    return
            pointer = self._opz_map_pointer(getattr(e, "pos", None))
            if pointer is not None:
                chart = opz_ppi_rect(config.OPZ_STATION_RECT)
                self._configure_opz_map_view(chart)
                self.opz_map_view.zoom(
                    config.MAP_ZOOM_WHEEL_FACTOR ** e.y, pivot=pointer)
                return
            pointer = self._map_pointer(getattr(e, "pos", None))
            if pointer is None:
                return
            factor = config.MAP_ZOOM_WHEEL_FACTOR ** e.y
            self.map_view.set_rect(config.MAP_RECT)
            self.map_view.zoom(factor, pivot=pointer)
        elif e.type == pygame.MOUSEBUTTONDOWN:
            if (e.button == 1 and self.plot_mode and not self.in_menu
                    and not self.game_over
                    and self._handle_plot_click(getattr(e, "pos", None))):
                return
            if e.button == 1 and not self.in_menu and not self.game_over:
                if self.station is Station.HELICOPTER and self.station_page == 3:
                    canvas = self._window_to_canvas(getattr(e, "pos", None))
                    hit = helicopter_acoustic_hit(self, canvas)
                    if hit is not None:
                        if hit[0] == "page":
                            self.helo_acoustic_page = hit[1]
                        elif hit[0] == "deck":
                            self.station_page = 2
                        elif hit[0] == "contact":
                            self.selected_contact = next(
                                (contact for contact in self.sonar.active_contacts()
                                 if contact.id == hit[1]), None)
                        else:
                            self.set_helicopter_listen_bearing(hit[1])
                        return
                if (self.station is not Station.SONAR
                        and not (self.station is Station.HELICOPTER
                                 and self.station_page == 3)
                        and len(STATION_PAGES[self.station]) > 1
                        and not self._station_overlay_open):
                    canvas = self._window_to_canvas(getattr(e, "pos", None))
                    station_rect = (config.STATION_PANEL_RECT
                                    if self._map_station_visible() else
                                    config.OPZ_STATION_RECT
                                    if self.station is Station.OPZ else
                                    config.FULL_STATION_RECT)
                    page_index = station_page_tab_at(
                        canvas, pygame.Rect(station_rect),
                        len(STATION_PAGES[self.station]))
                    if page_index is not None:
                        self.station_page = page_index
                        self._clear_station_input()
                        self.pinned_tooltip = None
                        self._tooltip_anchor = None
                        return
                if self.station is Station.SONAR:
                    canvas = self._window_to_canvas(getattr(e, "pos", None))
                    previous = config.STATION_RECT
                    config.STATION_RECT = config.FULL_STATION_RECT
                    try:
                        target = sonar_click_target(self, canvas)
                    finally:
                        config.STATION_RECT = previous
                    if target is not None and self._handle_sonar_click(target):
                        self.pinned_tooltip = None
                        self._tooltip_anchor = None
                        return
                if self.station is Station.DAMAGE:
                    canvas = self._window_to_canvas(getattr(e, "pos", None))
                    previous = config.STATION_RECT
                    config.STATION_RECT = config.FULL_STATION_RECT
                    try:
                        compartment = damage_compartment_at(
                            self, canvas,
                            page=int(getattr(self, "station_page", 0)))
                    finally:
                        config.STATION_RECT = previous
                    if compartment is not None:
                        self.dmg_cursor = list(self.damage.compartments).index(compartment)
                        self._assign_selected_team()
                        self._pin_tooltip_at(getattr(e, "pos", None))
                        return
                if self.station is Station.ELOKA:
                    canvas = self._window_to_canvas(getattr(e, "pos", None))
                    track = eloka_track_at(self, canvas, config.FULL_STATION_RECT)
                    if track is not None:
                        self.eloka_selected_track_key = track.track_key
                        self.pinned_tooltip = None
                        self._tooltip_anchor = None
                        self._pin_tooltip_at(getattr(e, "pos", None))
                        return
                if self.station is Station.OPZ:
                    canvas = self._window_to_canvas(getattr(e, "pos", None))
                    action = opz_action_at(self, canvas, config.OPZ_STATION_RECT)
                    if isinstance(action, tuple) and action[0] == "select":
                        self.opz_selected_track_id = action[1]
                    elif isinstance(action, tuple) and action[0] == "blip":
                        self.mark_radar_blip(action[1])
                    elif action == "classify":
                        self._cycle_opz_classification()
                    elif action == "affiliate":
                        self._cycle_opz_affiliation()
                    elif action == "mark":
                        self._toggle_opz_mark()
                    elif action == "fusion":
                        self._create_opz_fusion()
                    else:
                        action = None
                    if action is not None:
                        self.pinned_tooltip = None
                        self._tooltip_anchor = None
                        return
                    pointer = self._opz_map_pointer(getattr(e, "pos", None))
                    if pointer is not None:
                        self._map_drag = pointer
                        self._map_drag_moved = False
                        return
                pointer = self._map_pointer(getattr(e, "pos", None))
                if pointer is not None:
                    self._map_drag = pointer
                    self._map_drag_moved = False
                    return
                if self._pin_tooltip_at(getattr(e, "pos", None)):
                    self._map_drag = None
                    return
        elif e.type == pygame.MOUSEMOTION:
            if self._map_drag is not None:
                pointer = self._window_to_canvas(getattr(e, "pos", None))
                if pointer is None:
                    return
                dx = pointer[0] - self._map_drag[0]
                dy = pointer[1] - self._map_drag[1]
                # Retain the press origin until cumulative displacement is a drag.
                if not self._map_drag_moved and abs(dx) + abs(dy) <= 2:
                    return
                self._map_drag_moved = True
                if self.station is Station.OPZ:
                    self.opz_map_follow = False
                    self.opz_map_view.pan_px(dx, dy)
                else:
                    self.map_follow = False
                    self.map_view.pan_px(dx, dy)
                self._map_drag = pointer

    def _assign_selected_team(self) -> None:
        destination = list(self.damage.compartments)[self.dmg_cursor]
        if self.assign_damage_team(self.dmg_team, destination) is True:
            self.flash(message("runtime.team.assigned", team=self.dmg_team,
                               compartment=message("compartment." + destination)))
        else:
            self.flash(message("runtime.team.rejected"))

    def steering_input(self) -> tuple:
        """Turn direction from held keys/Trackball (-1/0/+1).
        M10: Fahrtsatz kommt über den Telegraphen (+/-), nicht per Dauer-Taste."""
        if self.station is not Station.BRIDGE:
            return 0, 0
        turn = 0
        if pygame.K_RIGHT in self.held:
            turn += 1
        if pygame.K_LEFT in self.held:
            turn -= 1
        if self._joy_turn:
            turn = max(-1, min(1, turn + self._joy_turn))
        return turn, 0

    # --- M10–M16: Neue Stationen & Waffensysteme ---

    def _cycle_sonar_mode(self) -> None:
        self.set_sonar_array_mode("TOWED" if self.sonar_mode == "BOW" else "BOW")
        self.flash(message("runtime.sonar_array.towed" if self.sonar_mode == "TOWED"
                           else "runtime.sonar_array.bow"), 1.5)

    def _handle_sonar_click(self, target) -> bool:
        """Execute the sonar view's closed allowlist of non-critical actions."""
        if not isinstance(target, dict) or target.get("safe") is not True:
            return False
        action = target.get("action")
        if action == "page_set":
            value = target.get("value")
            if type(value) is not int or not 0 <= value < len(STATION_PAGES[Station.SONAR]):
                return False
            self.sonar_page = value
        elif action == "page":
            self.sonar_page = station_page_step(Station.SONAR, self.sonar_page, 1)
        elif action in ("contact", "echo", "contact_listen"):
            contact_id = target.get("value")
            contact = next((item for item in self.sonar.active_contacts()
                            if item.id == contact_id), None)
            if contact is None:
                return False
            if action == "contact_listen":
                if self.set_sonar_focus(contact) is not True:
                    return False
            else:
                self.selected_contact = contact
        elif action == "listen_bearing":
            value = target.get("value")
            if (type(value) not in (int, float) or not math.isfinite(value)
                    or not 0 <= value < 360):
                return False
            self.set_sonar_listen_bearing(value)
            self.flash(message("runtime.numeric.true_bearing",
                               bearing=f"{value:05.1f}"), 2.0)
        elif action == "array":
            self._cycle_sonar_mode()
        elif action == "gain":
            self._adjust_sonar_gain(3.0)
        elif action == "band_filter":
            self._cycle_sonar_band()
        elif action == "notch":
            self.set_sonar_notch(not self.sonar.notch_enabled)
            self.flash(message("runtime.notch.on" if self.sonar.notch_enabled
                               else "runtime.notch.off"), 1.5)
        elif action == "harmonic":
            self._cycle_sonar_harmonic()
        elif action == "tma_accept":
            self._accept_tma_with_notice(self._tma_contact())
        elif action == "integration":
            seconds = self.sonar_tools.cycle_integration()
            self.flash(message("runtime.integration", seconds=seconds), 1.5)
        elif action == "cursor":
            pass   # the cursor moves with Z/X; the segment is a readout
        elif action == "peak":
            self.set_sonar_peak_hold(not self.sonar.peak_hold)
            self.flash(message("runtime.peak_hold.on" if self.sonar.peak_hold
                               else "runtime.peak_hold.off"), 1.5)
        elif action == "audio":
            self.sonar_audio_enabled = not self.sonar_audio_enabled
            self._stop_sonar_audio()
            self.flash(message("runtime.sonar_audio.on" if self.sonar_audio_enabled
                               else "runtime.sonar_audio.off"))
        else:
            return False
        return True

    def _cycle_sonar_harmonic(self) -> None:
        """K: mark the line under the operator cursor (LOFAR fundamental,
        DEMON shaft then blade line); pressing again on the mark clears it."""
        page = "demon" if self.sonar_page == 2 else "lofar"
        if self.mark_sonar_cursor(page) is not True:
            return
        tools = self.sonar_tools
        if page == "demon":
            key = ("runtime.demon.blade" if tools.blade_hz is not None
                   else "runtime.demon.shaft" if tools.shaft_hz is not None
                   else "runtime.demon.cleared")
            self.flash(message(key, frequency=f"{tools.demon_cursor_hz:.1f}"), 1.5)
        elif self.sonar_harmonic_hz is None:
            self.flash(message("runtime.harmonic.cleared"), 1.5)
        else:
            self.flash(message("runtime.harmonic.selected",
                               frequency=f"{self.sonar_harmonic_hz:.1f}"), 1.5)

    def _sonar_cursor_key(self, e) -> None:
        """Z/X move the frequency cursor; Shift: 10 Hz; Ctrl on LOFAR sets
        the band-pass low (Z) or high (X) edge at the cursor."""
        page = "demon" if self.sonar_page == 2 else "lofar"
        mods = getattr(e, "mod", 0)
        tools = self.sonar_tools
        if page == "lofar" and mods & pygame.KMOD_CTRL:
            cursor = tools.lofar_cursor_hz
            low, high = self.sonar.band_low_hz, self.sonar.band_high_hz
            low, high = ((cursor, high) if e.key == pygame.K_z else (low, cursor))
            if self.set_sonar_band(low, high) is True:
                self.flash(message("runtime.sonar_band", low=f"{low:.1f}",
                                   high=f"{high:.1f}"), 1.5)
            return
        fine = page == "demon" or tools.vernier
        step = 10.0 if mods & pygame.KMOD_SHIFT else (0.5 if fine else 1.0)
        current = tools.demon_cursor_hz if page == "demon" else tools.lofar_cursor_hz
        self.set_sonar_cursor(page, current + (step if e.key == pygame.K_x else -step))

    # --- Operator TMA (sonar page 3) ---

    def _tma_contact(self):
        contact = self.selected_contact
        if contact is None or contact.target_id not in self.sonar.contacts:
            return None
        return contact

    def _tma_points(self, contact):
        track = self.sonar._tracks.get(getattr(contact, "target_id", None))
        return list(getattr(track, "pts", ()))

    def tma_hypothesis(self, contact):
        hypothesis = self.tma_hypotheses.get(contact.target_id)
        if hypothesis is None:
            hypothesis = tma_operator.default_hypothesis(self._tma_points(contact))
        return hypothesis

    def set_tma_hypothesis(self, contact, course, speed_kn, range_nm):
        if contact is None or contact.target_id not in self.sonar.contacts:
            return "stale_ref"
        if any(type(value) not in (int, float) or not math.isfinite(value)
               for value in (course, speed_kn, range_nm)):
            return "invalid_value"
        if self._sonar_down():
            return "sonar_down"
        self.tma_hypotheses[contact.target_id] = tma_operator.Hypothesis(
            float(course), float(speed_kn), float(range_nm)).clamped()
        while len(self.tma_hypotheses) > 64:
            self.tma_hypotheses.pop(next(iter(self.tma_hypotheses)))
        return True

    def tma_evaluation(self, contact):
        points = self._tma_points(contact)
        return tma_operator.evaluate(points, self.tma_hypothesis(contact))

    def accept_tma(self, contact):
        """Write the operator's hypothesis as the contact's TMA fix."""
        if contact is None or contact.target_id not in self.sonar.contacts:
            return "stale_ref"
        if self._sonar_down():
            return "sonar_down"
        points = self._tma_points(contact)
        evaluation = tma_operator.evaluate(points, self.tma_hypothesis(contact))
        if evaluation is None:
            return "not_ready"
        if evaluation["observability"] < 0.5:
            return "unobservable"
        if evaluation["fit"] < TMA_ACCEPT_MIN_FIT:
            return "poor_fit"
        hypothesis = self.tma_hypothesis(contact)
        position = tma_operator.position_at(points, hypothesis, self.sim_t)
        contact.accept_operator_tma(position, hypothesis.course,
                                    hypothesis.speed_kn, evaluation["quality"],
                                    self.sim_t)
        return True

    def copy_tma_proposal(self, contact):
        """Training aid: start the hypothesis from the automatic solver."""
        if not self.operator_assist():
            return "not_available"
        if contact is None:
            return "stale_ref"
        proposal = self.sonar.tma_proposals.get(contact.target_id)
        points = self._tma_points(contact)
        if proposal is None or not points:
            return "not_ready"
        # The proposal's position is at its newest bearing; its range from
        # that observation point seeds the hypothesis range.
        ref = points[-1]
        return self.set_tma_hypothesis(
            contact, proposal.course, proposal.speed,
            math.hypot(proposal.pos[0] - ref.fx, proposal.pos[1] - ref.fy))

    def _accept_tma_with_notice(self, contact) -> None:
        result = self.accept_tma(contact) if contact is not None else "stale_ref"
        if result is True:
            self.flash(message("runtime.tma.accepted", contact=contact.id,
                               quality=f"{contact.tma_quality:.0%}"), 2.0)
        elif result == "poor_fit":
            self.flash(message("runtime.tma.poor_fit"), 2.0)
        elif result == "unobservable":
            self.flash(message("runtime.tma.unobservable"), 2.0)
        else:
            self.flash(message("runtime.tma.not_ready"), 2.0)

    def _tma_key(self, e) -> None:
        """TMA page: Z/X course -/+ (Shift fine), Ctrl+Z/X speed -/+,
        Q / Shift+Q range -/+, K accept, Shift+K copy the solver proposal."""
        contact = self._tma_contact()
        if contact is None:
            self.flash(message("runtime.tma.no_contact"), 1.5)
            return
        mods = getattr(e, "mod", 0)
        hypothesis = self.tma_hypothesis(contact)
        course, speed, rng = hypothesis.course, hypothesis.speed_kn, hypothesis.range_nm
        if e.key == pygame.K_k:
            if mods & pygame.KMOD_SHIFT:
                result = self.copy_tma_proposal(contact)
                self.flash(message("runtime.tma.copied" if result is True
                                   else "runtime.tma.no_proposal"), 1.5)
                return
            self._accept_tma_with_notice(contact)
            return
        sign = 1.0 if e.key == pygame.K_x else -1.0
        if e.key == pygame.K_q:
            rng += (tma_operator.RANGE_FINE_NM if mods & pygame.KMOD_CTRL
                    else tma_operator.RANGE_STEP_NM) * (1.0 if mods & pygame.KMOD_SHIFT
                                                        else -1.0)
        elif mods & pygame.KMOD_CTRL:
            speed += tma_operator.SPEED_STEP_KN * sign
        else:
            course += (tma_operator.COURSE_FINE_DEG if mods & pygame.KMOD_SHIFT
                       else tma_operator.COURSE_STEP_DEG) * sign
        self.set_tma_hypothesis(contact, course, speed, rng)

    def operator_assist(self) -> bool:
        """Training aids (auto peaks, blade-rate/catalog ranking, ESM IDs) on?"""
        return getattr(self.preferences, "operator_assist", "off") == "training"

    def set_sonar_cursor(self, page, frequency_hz):
        if page not in ("lofar", "demon"):
            return "invalid_value"
        if (type(frequency_hz) not in (int, float)
                or not math.isfinite(frequency_hz)):
            return "invalid_value"
        if self._sonar_down():
            return "sonar_down"
        value = analysis_tools.clamp_cursor(frequency_hz, page)
        if page == "lofar":
            self.sonar_tools.lofar_cursor_hz = value
        else:
            self.sonar_tools.demon_cursor_hz = value
        return True

    def mark_sonar_cursor(self, page):
        if page not in ("lofar", "demon"):
            return "invalid_value"
        if self._sonar_down():
            return "sonar_down"
        tools = self.sonar_tools
        if page == "demon":
            tools.mark_demon(tools.demon_cursor_hz)
            return True
        cursor = tools.lofar_cursor_hz
        if (self.sonar_harmonic_hz is not None
                and abs(self.sonar_harmonic_hz - cursor) < 1e-6):
            return self.set_sonar_harmonic(None)
        return self.set_sonar_harmonic(cursor)

    def set_sonar_integration(self, seconds):
        if type(seconds) is not int or seconds not in analysis_tools.INTEGRATION_CHOICES_S:
            return "invalid_value"
        self.sonar_tools.integration_s = seconds
        return True

    def set_sonar_vernier(self, enabled):
        if type(enabled) is not bool:
            return "invalid_value"
        self.sonar_tools.vernier = enabled
        return True

    def set_sonar_band(self, low_hz, high_hz):
        """Free band-pass edges (low 0 = low-pass, high 300 = high-pass)."""
        if (any(type(value) not in (int, float) or not math.isfinite(value)
                for value in (low_hz, high_hz))
                or not 0.0 <= low_hz < high_hz <= config.LOFAR_FMAX_HZ):
            return "invalid_value"
        if self._sonar_down():
            return "sonar_down"
        self.sonar.band_low_hz, self.sonar.band_high_hz = float(low_hz), float(high_hz)
        return True

    def set_tas_side(self, contact, action: str):
        """Operator decision on a towed-only contact's array side.

        ``flip`` shows the other side (and reopens a confirmed choice);
        ``confirm`` commits the shown side. Nothing is decided automatically.
        """
        if contact is None or contact.target_id not in self.sonar.contacts:
            return "stale_ref"
        if action not in ("flip", "confirm"):
            return "invalid_value"
        if self._sonar_down():
            return "sonar_down"
        if action == "flip":
            if not contact.towed_ambiguous:
                if not contact.towed_resolved:
                    return "not_ambiguous"
                contact.towed_ambiguous, contact.towed_resolved = True, False
                contact.ambiguity_axis = self.sonar.tow_heading_deg
            contact.towed_side = "PORT" if contact.towed_side == "STBD" else "STBD"
            return True
        if not contact.towed_ambiguous:
            return "not_ambiguous"
        contact.towed_ambiguous, contact.towed_resolved = False, True
        contact.mirror_bearing = contact.ambiguity_axis = None
        return True

    def _tas_side_key(self, e) -> None:
        contact = self.selected_contact
        action = "confirm" if getattr(e, "mod", 0) & pygame.KMOD_SHIFT else "flip"
        result = self.set_tas_side(contact, action)
        if result is True:
            self.flash(message("runtime.tas_side.confirmed" if action == "confirm"
                               else "runtime.tas_side.flipped",
                               contact=self.contact_display_id(contact),
                               side=contact.towed_side), 1.5)
        else:
            self.flash(message("runtime.tas_side.not_ambiguous"), 1.5)

    def set_sonar_demon_band(self, low_hz, high_hz):
        if (low_hz, high_hz) not in analysis_tools.DEMON_BANDS_HZ:
            return "invalid_value"
        if self._sonar_down():
            return "sonar_down"
        self.sonar.receiver.demon_band_hz = (float(low_hz), float(high_hz))
        return True

    def set_sonar_heterodyne(self, frequency_hz):
        if frequency_hz not in analysis_tools.HETERODYNE_OFFSETS_HZ:
            return "invalid_value"
        if self._sonar_down():
            return "sonar_down"
        self.sonar.heterodyne_hz = float(frequency_hz)
        return True

    def set_sonar_operator_notch(self, frequency_hz):
        if frequency_hz is not None and (
                type(frequency_hz) not in (int, float) or not math.isfinite(frequency_hz)
                or not 0.0 < frequency_hz <= config.LOFAR_FMAX_HZ):
            return "invalid_value"
        if self._sonar_down():
            return "sonar_down"
        self.sonar.operator_notch_hz = (None if frequency_hz is None
                                        else float(frequency_hz))
        return True

    def _adjust_sonar_gain(self, delta: float) -> None:
        self.set_sonar_gain(config.clamp(self.sonar.gain_db + delta, -12.0, 24.0))
        self.flash(message("runtime.sonar_gain", gain=f"{self.sonar.gain_db:+.0f}"), 1.2)

    def _cycle_sonar_display_palette(self) -> None:
        palettes = ("green", "amber", "cyan")
        current = (palettes.index(self.sonar_display_palette)
                   if self.sonar_display_palette in palettes else -1)
        self.sonar_display_palette = palettes[(current + 1) % len(palettes)]
        self.flash(message("runtime.sonar_palette",
                           palette=self.sonar_display_palette.upper()), 1.2)

    def _adjust_sonar_display_contrast(self, delta: float) -> None:
        self.sonar_display_contrast = round(config.clamp(
            self.sonar_display_contrast + delta, .5, 4.0), 1)
        self.flash(message("runtime.sonar_contrast",
                           contrast=f"{self.sonar_display_contrast:.1f}"), 1.2)

    def _adjust_sonar_display_black(self, delta: float) -> None:
        self.sonar_display_black = round(config.clamp(
            self.sonar_display_black + delta, 0.0, .8), 2)
        self.flash(message("runtime.sonar_black_level",
                           level=f"{self.sonar_display_black:.2f}"), 1.2)

    def _cycle_sonar_display_history(self) -> None:
        depths = (.25, .5, 1.0)
        current = next((index for index, value in enumerate(depths)
                        if abs(self.sonar_display_history - value) < 1e-6), -1)
        self.sonar_display_history = depths[(current + 1) % len(depths)]
        self.flash(message("runtime.sonar_history",
                           history=f"{self.sonar_display_history:.0%}"), 1.2)

    def _set_sonar_audition_mode(self, mode: str) -> None:
        if self.set_sonar_audition_mode(mode) is not True:
            return
        key = {"BROADBAND": "runtime.listen.broadband",
               "FILTERED": "runtime.listen.filtered",
               "HETERODYNE": "runtime.listen.heterodyne"}[mode]
        self.flash(message(key), 1.2)

    def sonar_audio_status(self) -> dict:
        status = self.audio.availability_status()
        locally_ready = (self.station is Station.SONAR and self.sonar_audio_enabled
                         and not self.damage.station_down("sonar"))
        return dict(status, local_enabled=bool(self.sonar_audio_enabled),
                    mode=self.sonar.audition_mode, gain_db=self.sonar.gain_db,
                    band_hz=[self.sonar.band_low_hz, self.sonar.band_high_hz],
                    notch=bool(self.sonar.notch_enabled), volume=self.sonar_volume,
                    stale=bool(self.audio.sonar_stale),
                    audible=bool(status["global_enabled"]
                                 and status["device_available"] and locally_ready))

    def _cycle_sonar_band(self) -> None:
        bands = tuple(SONAR_BAND_PRESETS.values())
        current = (self.sonar.band_low_hz, self.sonar.band_high_hz)
        try:
            index = bands.index(current)
        except ValueError:
            index = 0
        low, high = bands[(index + 1) % len(bands)]
        preset = next(key for key, value in SONAR_BAND_PRESETS.items()
                      if value == (low, high))
        self.set_sonar_band_preset(preset)
        self.flash(message("runtime.sonar_band", low=f"{low:.0f}",
                           high=f"{high:.0f}"), 1.5)

    @property
    def radar_on(self) -> bool:
        """Kompatibilitaet fuer alte Aufrufer/Saves: beide Radare gemeinsam."""
        return self.surface_radar_on and self.air_radar_on

    @radar_on.setter
    def radar_on(self, value: bool) -> None:
        self.surface_radar_on = bool(value)
        self.air_radar_on = bool(value)

    def toggle_radar(self, domain: str = "surface") -> None:
        enabled = not (self.air_radar_on if domain == "air"
                       else self.surface_radar_on)
        if self.set_opz_radar(domain, enabled) is not True:
            self.flash(message("runtime.opz.disabled"))
            return
        if domain == "air":
            radar, active = "air", self.air_radar_on
        else:
            radar, active = "surface", self.surface_radar_on
        suffix = "on" if active else "off"
        self.hq_msg(message(f"runtime.emcon.{radar}.{suffix}.hq"))
        self.flash(message(f"runtime.emcon.{radar}.{suffix}"), 2.0)

    def set_opz_radar(self, domain: str, enabled: bool):
        """Set one OPZ radar from a validated local or remote station action."""
        if self.damage.station_down("opz"):
            return "opz_down"
        if domain not in ("surface", "air") or type(enabled) is not bool:
            return "invalid_value"
        setattr(self, f"{domain}_radar_on", enabled)
        return True

    def set_opz_range(self, range_nm: float):
        if self.damage.station_down("opz"):
            return "opz_down"
        if type(range_nm) not in (int, float) or range_nm not in config.RADAR_RANGE_SCALES_NM:
            return "invalid_value"
        self.opz_range_nm = float(range_nm)
        return True

    def _cycle_lookout_range(self, delta: int) -> None:
        """Bridge lookout page: step the display scale (presentation only)."""
        scales = config.LOOKOUT_DISPLAY_RANGES_NM
        current = getattr(self, "lookout_range_nm", 12.0)
        index = min(range(len(scales)), key=lambda i: abs(scales[i] - current))
        self.lookout_range_nm = scales[max(0, min(len(scales) - 1, index + delta))]
        self.flash(message("runtime.lookout.range", range=f"{self.lookout_range_nm:.0f}"), 1.5)

    def lookout_sightings(self) -> list:
        """Current bridge-lookout tracks (measured bearing/range, visual label)."""
        return [track for track in self.air_picture.tracks(self.sim_t)
                if track.source == "LOOKOUT" and track.x is not None and track.y is not None]

    def _cycle_radar_range(self, delta: int) -> None:
        scales = config.RADAR_RANGE_SCALES_NM
        try:
            index = scales.index(float(self.opz_range_nm))
        except ValueError:
            index = len(scales) - 1
        index = max(0, min(len(scales) - 1, index + delta))
        if self.set_opz_range(scales[index]) is not True:
            return
        self.flash(message("runtime.radar.range", range=f"{self.opz_range_nm:.0f}"), 1.5)

    def radar_weather_severity(self) -> float:
        """0 bis Seegang 4; 0.5/1.0 erst bei schwerem Wetter 5/6."""
        return config.clamp(
            (getattr(self.world, "effective_sea_state", self.world.sea_state)
             - (config.RADAR_WEATHER_THRESHOLD - 1)) / 2.0,
            0.0, 1.0)

    def radar_rain_severity(self) -> float:
        return config.clamp(getattr(self.world, "rain_intensity", 0.0), 0.0, 1.0)

    def radar_effective_range(self, domain: str) -> float:
        """Range of Pd = 0.5 per look for a reference target (radar equation
        with sea clutter, rain attenuation and console damage)."""
        nominal = (config.RADAR_AIR_RANGE_NM if domain == "air"
                   else config.RADAR_SURFACE_RANGE_NM)
        conditions = self._radar_conditions()
        return nominal * radar_physics.detection_fraction(
            domain, conditions["sea_state"], conditions["rain_intensity"],
            nominal, conditions["capability"])

    def _asm_jammer_to_noise(self, asm, distance: float) -> float:
        """Self-screening noise jammer of a missile, solved from its profiled
        burn-through range (J/S ~ R^2): inside it the skin echo wins."""
        if not asm.jammer:
            return 0.0
        burn_through = asm.profile["jam_break_nm"]
        skin = radar_physics.snr(burn_through, config.RADAR_AIR_RANGE_NM)
        return radar_physics.jammer_to_noise(distance, burn_through, skin)

    def _radar_conditions(self) -> dict:
        # Damage to the operations room (radar consoles, power) degrades the
        # radar continuously rather than only at destruction.
        capability = (1.0 if not self.damage.station_degraded("opz")
                      else 0.5 + 0.5 * self.damage.capability("opz"))
        return dict(
            sea_state=getattr(self.world, "effective_sea_state", self.world.sea_state),
            rain_intensity=self.radar_rain_severity(), capability=capability)

    def _radar_look(self, domain: str, key: int, distance: float, bearing: float,
                    *, swept_deg: float, rcs_factor: float = 1.0,
                    jnr: float = 0.0) -> bool:
        """One antenna look: the beam must have passed the bearing and the
        Swerling-1/CFAR detector must declare the echo (deterministic draw)."""
        if not radar_physics.swept(bearing, self.radar_scan_phase, swept_deg):
            return False
        nominal = (config.RADAR_AIR_RANGE_NM if domain == "air"
                   else config.RADAR_SURFACE_RANGE_NM)
        sinr = radar_physics.sinr(distance, nominal, rcs_factor=rcs_factor,
                                  domain=domain, jnr=jnr,
                                  **self._radar_conditions())
        tick = math.floor(self.sim_t * 4.0 + 1e-6)
        return (detrand.u01(self.seed, "radar-look-" + domain, key, tick)
                < radar_physics.pd_from_sinr(sinr))

    @staticmethod
    def _mast_up(sub) -> bool:
        """A mast or snorkel head above the water: the crew's raised mast or
        snorkel, or an AI boat snorkelling or at radio depth."""
        from src.sensors.platform import MAST_DEPTH_M
        if sub.sunk or sub.depth > MAST_DEPTH_M:
            return False
        crew = getattr(sub, "crew", None)
        if sub.manual and crew is not None and crew.mast:
            return True
        endurance = sub.endurance
        return endurance is not None and endurance.phase in ("SNORKEL", "RADIO")

    def _update_mast_echoes(self, surface_live, swept_deg, error_scale) -> None:
        """Surface-radar looks at raised masts: a bare blip, or an update of
        the track the OPZ marked for that boat."""
        for sub_id, (_track_id, last) in tuple(self._radar_marked.items()):
            if self.sim_t - last > config.RADAR_TRACK_STALE_S:
                del self._radar_marked[sub_id]
        if not surface_live:
            return
        horizon = config.radar_horizon_nm(config.RADAR_ANTENNA_HEIGHT_M,
                                          config.SUB_MAST_HEIGHT_M)
        tick = math.floor(self.sim_t * 4.0 + 1e-6)
        for sub in self.subs:
            if not self._mast_up(sub):
                continue
            dist = math.hypot(sub.x - self.ship.x, sub.y - self.ship.y)
            bearing = math.degrees(math.atan2(sub.x - self.ship.x,
                                              -(sub.y - self.ship.y))) % 360.0
            if (dist > horizon or not self._radar_look(
                    "surface", sub.sensor_seed, dist, bearing, swept_deg=swept_deg,
                    rcs_factor=config.SUB_MAST_RCS_FACTOR)
                    or self.world.land_blocks_line(self.ship.x, self.ship.y, sub.x, sub.y)):
                continue
            bearing_error = config.RADAR_BEARING_ERR_DEG * error_scale
            range_error = config.RADAR_RANGE_ERR_FRAC * error_scale
            brg = (bearing + detrand.uniform(-bearing_error, bearing_error, self.seed,
                                             "radar-mast-brg", sub.sensor_seed, tick)) % 360.0
            measured = max(0.0, dist * (1.0 + detrand.uniform(
                -range_error, range_error, self.seed, "radar-mast-rng", sub.sensor_seed, tick)))
            marked = self._radar_marked.get(sub.id)
            if marked is not None:
                self._observe_mast(marked[0], sub.id, brg, measured,
                                   self.ship.x, self.ship.y, bearing_error)
                continue
            self.radar_blip_seq += 1
            rad = math.radians(brg)
            self.radar_blips.append(dict(
                seq=self.radar_blip_seq, t=float(self.sim_t), target=sub.id,
                bearing=brg, range_nm=measured, error=bearing_error,
                observer_x=self.ship.x, observer_y=self.ship.y,
                x=self.ship.x + measured * math.sin(rad),
                y=self.ship.y - measured * math.cos(rad)))

    def _observe_mast(self, track_id, sub_id, bearing, range_nm, observer_x, observer_y,
                      bearing_error) -> None:
        self._radar_marked[sub_id] = (track_id, float(self.sim_t))
        self.air_picture.observe(track_id=track_id, kind="SURFACE", target_id=sub_id,
            source="RADAR-S", bearing=bearing, range_nm=range_nm,
            observer_x=observer_x, observer_y=observer_y, course=None, quality=.5,
            now=self.sim_t, label=track_id,
            bearing_uncertainty_deg=bearing_error / math.sqrt(3.0))

    def radar_blip_view(self) -> list:
        """Unmarked radar blips still glowing (measured positions only)."""
        if not (self.surface_radar_on and not self.damage.station_down("opz")):
            return []
        return [blip for blip in self.radar_blips
                if 0.0 <= self.sim_t - blip["t"] < config.RADAR_BLIP_LIFE_S
                and blip["target"] not in self._radar_marked]

    def mark_radar_blip(self, seq):
        """OPZ: start a radar track from a blip (its measurement only)."""
        if type(seq) is not int:
            return "invalid_value"
        blip = next((item for item in self.radar_blip_view() if item["seq"] == seq), None)
        if blip is None:
            return "stale_ref"
        track_id = f"R-{blip['seq']}"
        self._observe_mast(track_id, blip["target"], blip["bearing"], blip["range_nm"],
                           blip["observer_x"], blip["observer_y"], blip["error"])
        self.announce(message("runtime.opz.blip_marked", track=track_id), "opz", 2.0)
        return True

    def _mark_newest_blip(self) -> None:
        blips = self.radar_blip_view()
        if not blips:
            self.flash(message("runtime.opz.no_blip"), 1.5)
            return
        self.mark_radar_blip(blips[-1]["seq"])

    def radar_sweep_bearing(self) -> float:
        """Nautische Peilung: zunehmende Werte drehen Nord -> Ost rechtsherum."""
        return self.radar_scan_phase

    def toggle_helo(self) -> None:
        if self.helo.airborne:
            if self.return_helicopter() is True:
                self.announce(message("runtime.helo.return"), "waffen")
        else:
            result = self.launch_helicopter()
            if result == "flightdeck_down":
                self.flash(message("runtime.helo.deck_down"))
                return
            if result == "weather_unsafe":
                self.flash(message("runtime.helo.weather_unsafe"))
                return
            if result is not True:
                self.flash(message("runtime.helo.lost"))
                return
            self.announce(message("runtime.helo.launch", torpedoes=self.helo.torps,
                                  buoys=self.helo.buoys_left), "waffen", 3.0)

    def atmosphere(self) -> dict:
        """Own-ship atmosphere (barometer, thermometer, wind, sky), derived
        from the weather system; observation-safe (no future values)."""
        world = self.world
        weather = world.weather_values()
        kind = world.weather_kind()
        source_sea, target_sea, elapsed = world.weather_epoch()
        pressure, tendency = atmosphere_physics.barometer(
            self.seed, source_sea, target_sea, elapsed)
        trend = atmosphere_physics.pressure_trend(tendency)
        rain = weather["rain_intensity"]
        wind = weather["wind_speed_kn"]
        sst = world.ocean.sea_surface_temperature_c(world.hour)
        cloud = atmosphere_physics.cloud_cover(kind, rain)
        air = atmosphere_physics.air_temperature_c(
            sst, world.ocean.day_of_year, world.hour, weather["wind_from_deg"],
            wind, cloud)
        precipitation = atmosphere_physics.precipitation(rain, air)
        latitude = world.latitude_deg()
        latitude = (atmosphere_physics.DEFAULT_LATITUDE_DEG if latitude is None
                    else latitude)
        sun = atmosphere_physics.sun_elevation_deg(
            latitude, world.ocean.day_of_year, world.hour)
        lunar_age = self.lunar_age_days()
        return dict(
            weather=("snow" if precipitation == "snow" else kind),
            precipitation=precipitation, rain_intensity=rain,
            visibility_nm=weather["visibility_nm"],
            sea_state=int(round(weather["sea_state"])),
            wind_from_deg=weather["wind_from_deg"], wind_kn=wind,
            gust_kn=atmosphere_physics.gust_kn(wind, weather["sea_state"]),
            beaufort=atmosphere_physics.beaufort(wind),
            pressure_hpa=pressure, pressure_tendency_hpa_3h=tendency,
            pressure_trend=trend,
            storm_warning=atmosphere_physics.storm_warning(pressure, trend),
            air_temp_c=air, sea_temp_c=sst, cloud_cover=cloud,
            ceiling_ft=atmosphere_physics.cloud_ceiling_ft(
                kind, rain, weather["visibility_nm"]),
            icing=atmosphere_physics.icing(air, precipitation, wind),
            sun_elevation_deg=sun,
            daylight=atmosphere_physics.daylight(sun),
            moon_phase=atmosphere_physics.moon_phase(lunar_age),
            moon_illumination=visual_physics.moon_illumination(lunar_age),
            time=world.format_time())

    def helicopter_weather(self) -> dict:
        """Return one shared, observation-safe flight-weather decision."""
        weather = self.world.weather_values()
        atmosphere = self.atmosphere()
        relative = math.radians(config.angle_diff_deg(
            weather["wind_from_deg"], self.ship.course))
        crosswind = abs(weather["wind_speed_kn"] * math.sin(relative))
        launch_safe = (
            weather["wind_speed_kn"] <= config.HELO_LAUNCH_WIND_MAX_KN
            and crosswind <= config.HELO_LAUNCH_CROSSWIND_MAX_KN
            and weather["visibility_nm"] >= config.HELO_LAUNCH_VISIBILITY_MIN_NM
            and weather["sea_state"] <= config.HELO_LAUNCH_SEA_STATE_MAX)
        gust = atmosphere["gust_kn"]
        ceiling = atmosphere["ceiling_ft"]
        icing = atmosphere["icing"]
        launch_weather = (launch_safe
                          and gust <= config.HELO_LAUNCH_GUST_MAX_KN
                          and (ceiling is None or ceiling >= config.HELO_CEILING_MIN_FT)
                          and icing != "severe")
        # Launch and recovery also need a deck-motion window (own ship).
        deck_safe = helicopter_physics.deck_within_limits(self.ship.roll, self.ship.pitch)
        launch_safe = launch_weather and deck_safe
        dipping_safe = (
            weather["wind_speed_kn"] <= config.HELO_DIP_WIND_MAX_KN
            and weather["visibility_nm"] >= config.HELO_DIP_VISIBILITY_MIN_NM
            and weather["sea_state"] <= config.HELO_DIP_SEA_STATE_MAX
            # Winch and cable ice up: no dipping in icing conditions.
            and icing == "none")
        # Flight-weather category: NO-GO outside the launch weather limits,
        # LIMITED near a limit (80 %) or in light icing, else CLEAR.
        margins = (
            weather["wind_speed_kn"] / config.HELO_LAUNCH_WIND_MAX_KN,
            gust / config.HELO_LAUNCH_GUST_MAX_KN,
            crosswind / config.HELO_LAUNCH_CROSSWIND_MAX_KN,
            weather["sea_state"] / config.HELO_LAUNCH_SEA_STATE_MAX,
            config.HELO_LAUNCH_VISIBILITY_MIN_NM / max(weather["visibility_nm"], 1e-3),
            (0.0 if ceiling is None else config.HELO_CEILING_MIN_FT / max(ceiling, 1.0)))
        status = ("no_go" if not launch_weather else
                  "limited" if icing != "none" or max(margins) >= 0.8 else "clear")
        return dict(weather, crosswind_kn=crosswind, deck_safe=deck_safe,
                    launch_safe=launch_safe, dipping_safe=dipping_safe,
                    gust_kn=gust, ceiling_ft=ceiling, icing=icing, status=status)

    WEATHER_PROFILE_STALE_S = 1800.0
    WEATHER_PROFILE_STALE_NM = 10.0
    WEATHER_RAY_SOURCE_DEPTH_M = 5.0      # hull sonar

    def weather_station_data(self) -> dict:
        """Observation-safe data for the weather & sonar analysis panel.

        Atmosphere and flight weather come from own-ship instruments.  The
        ocean profile - layer, sound-speed curve, shadow zone, SOFAR axis,
        rays - exists only after the sonar has taken a bathythermograph
        measurement, and is always that measurement (with its age), never
        the modelled truth."""
        atmosphere = self.atmosphere()
        flight = self.helicopter_weather()
        effects = dict(
            solar_heating=(atmosphere["daylight"] == "day"
                           and atmosphere["sun_elevation_deg"] >= 20.0
                           and atmosphere["cloud_cover"] < 0.6),
            wind_mixing=atmosphere["wind_kn"] >= ocean_physics.MLD_WIND_THRESHOLD_KN,
            freshwater=atmosphere["precipitation"] != "none")
        return dict(
            atmosphere=atmosphere, effects=effects,
            flight=dict(
                status=flight["status"], launch_safe=flight["launch_safe"],
                dipping_safe=flight["dipping_safe"], deck_safe=flight["deck_safe"],
                wind_kn=flight["wind_speed_kn"], gust_kn=flight["gust_kn"],
                crosswind_kn=flight["crosswind_kn"],
                visibility_nm=flight["visibility_nm"],
                ceiling_ft=flight["ceiling_ft"], icing=flight["icing"],
                sea_state=int(round(flight["sea_state"])),
                # A crewed boat's instruments never report the frigate's motion.
                roll_deg=(self.ship.roll if self._sonar_ctx is self._frigate_sonar
                          else 0.0),
                pitch_deg=(self.ship.pitch if self._sonar_ctx is self._frigate_sonar
                           else 0.0),
                limits=dict(
                    wind_kn=config.HELO_LAUNCH_WIND_MAX_KN,
                    gust_kn=config.HELO_LAUNCH_GUST_MAX_KN,
                    crosswind_kn=config.HELO_LAUNCH_CROSSWIND_MAX_KN,
                    visibility_nm=config.HELO_LAUNCH_VISIBILITY_MIN_NM,
                    ceiling_ft=config.HELO_CEILING_MIN_FT,
                    sea_state=config.HELO_LAUNCH_SEA_STATE_MAX,
                    roll_deg=helicopter_physics.DECK_ROLL_LIMIT_DEG,
                    pitch_deg=helicopter_physics.DECK_PITCH_LIMIT_DEG)),
            profile=self._weather_station_profile())

    def _weather_station_profile(self) -> dict | None:
        bt = self.sonar.bt_profile
        if bt is None:
            return None
        age = max(0.0, self.sim_t - bt["t"])
        observer = self.sonar_observer
        offset = math.hypot(observer.x - bt["x"], observer.y - bt["y"])
        # Wind of the measurement's sea-state band keeps the picture fixed
        # for one measurement (a pure, cached function of it).
        wind = ocean_physics.MLD_WIND_THRESHOLD_KN * bt["sea_state"] / 3.0
        picture = sonar_raytrace.ray_picture(
            bt["depths_m"], bt["speeds_m_s"], bt["water_depth_m"],
            self.WEATHER_RAY_SOURCE_DEPTH_M, self.world.seabed_at(bt["x"], bt["y"]),
            wind, bt["thermocline_m"])
        dip = None
        if (self._sonar_ctx is self._frigate_sonar and self.helo.airborne
                and self.helo.dip_state != "STOWED"):
            dip = ("below" if self.helo.dip_depth_m >= bt["thermocline_m"]
                   else "above")
        return dict(
            age_s=age, offset_nm=offset,
            stale=(age > self.WEATHER_PROFILE_STALE_S
                   or offset > self.WEATHER_PROFILE_STALE_NM),
            thermocline_m=bt["thermocline_m"], water_depth_m=bt["water_depth_m"],
            depths_m=list(bt["depths_m"]), speeds_m_s=list(bt["speeds_m_s"]),
            sofar_axis_m=ocean_physics.sofar_axis_m(
                bt["depths_m"], bt["speeds_m_s"], bt["water_depth_m"]),
            cz_bands_nm=[list(band) for band in bt["cz_bands_nm"]],
            range_nm=picture["range_nm"], rays=picture["rays"],
            depth_edges_m=picture["depth_edges_m"], shadow=picture["shadow"],
            dip_relative_to_layer=dip)

    def launch_helicopter(self):
        if self.damage.station_down("flightdeck"):
            return "flightdeck_down"
        if not self.helicopter_weather()["launch_safe"]:
            return "weather_unsafe"
        if self.helo.state != "HANGAR":
            return "not_ready"
        self.helo.launch(self.ship)
        return True

    def return_helicopter(self):
        if not self.helo.airborne:
            return "not_ready"
        self.helo.order_return()
        return True

    def set_helicopter_waypoint(self, x: float, y: float):
        if (type(x) not in (int, float) or type(y) not in (int, float)
                or not 0 <= x <= self.world.size_nm
                or not 0 <= y <= self.world.size_nm
                or not math.isfinite(x) or not math.isfinite(y)):
            return "invalid_value"
        if self.helo.state == "VERLOREN":
            return "not_ready"
        self.helo.set_waypoint(x, y)
        return True

    def _helo_waypoint_polar(self) -> tuple[float, float]:
        if self.helo.waypoint_x is None or self.helo.waypoint_y is None:
            return self.ship.course, 2.0
        dx = self.helo.waypoint_x - self.ship.x
        dy = self.helo.waypoint_y - self.ship.y
        return math.degrees(math.atan2(dx, -dy)) % 360.0, math.hypot(dx, dy)

    def _adjust_helo_waypoint(self, bearing_delta: float = 0.0,
                              range_delta: float = 0.0) -> None:
        bearing, distance = self._helo_waypoint_polar()
        bearing = (bearing + bearing_delta) % 360.0
        distance = config.clamp(distance + range_delta, 1.0, 30.0)
        self.helo.set_waypoint(
            self.ship.x + distance * math.sin(math.radians(bearing)),
            self.ship.y - distance * math.cos(math.radians(bearing)))
        self.flash(message("runtime.helo.waypoint", bearing=f"{bearing:03.0f}",
                           range=f"{distance:.0f}"), 1.5)

    def deploy_buoys(self) -> None:
        result = self.deploy_helicopter_buoy()
        if result == "not_ready":
            self.flash(message("runtime.helo.not_airborne"))
            return
        if result == "water_required":
            self.flash(message("runtime.helo.water_required"))
            return
        if result is True:
            buoy = self.buoys[-1]
            self.flash(message("runtime.buoy.deployed", buoy=buoy.seq))
            self.feed.add(self.world.format_time(), "sonar",
                          message("runtime.buoy.active", buoy=buoy.seq))
        else:
            self.flash(message("event.no_buoys"))

    def deploy_helicopter_buoy(self):
        if not self.helo.airborne:
            return "not_ready"
        if not self.helo.water_entry_clear(self.world):
            return "water_required"
        if self.helo.buoys_left <= 0:
            return "no_buoys"
        next_sequence = self.buoy_seq + 1
        buoy = self.helo.deploy_buoy(next_sequence, world=self.world,
                                    mode=getattr(self, "helo_buoy_mode", "PASSIVE"))
        if buoy is None:
            return "not_ready"
        self.buoy_seq = next_sequence
        self.buoys.append(buoy)
        if buoy.mode == "PASSIVE" and not self.helicopter_audio_ready():
            self.set_helicopter_listen_source(f"SB{buoy.seq}")
        return True

    def set_helicopter_buoy_mode(self, mode: str):
        if mode not in ("PASSIVE", "ACTIVE") or type(mode) is not str:
            return "invalid_value"
        self.helo_buoy_mode = mode
        return True

    def set_helicopter_listen_source(self, source: str):
        if source != "DIP":
            if (type(source) is not str or not source.startswith("SB")
                    or not source[2:].isdigit() or len(source) > 5):
                return "invalid_value"
            seq = int(source[2:])
            if not any(b.seq == seq and b.active for b in self.buoys):
                return "stale_ref"
        if source != self.helo_listen_source:
            self.helo_listen_source = source
            self.helo_receiver.reset()
            self.helo_audition.reset_audition_audio()
            self.helo_spectra.clear()
            self.helo_broadband_history.clear()
            self.helo_demon_history.clear()
            self._helo_receiver_timer = 0.0
        return True

    def set_helicopter_listen_bearing(self, bearing):
        if bearing is not None and (type(bearing) not in (int, float)
                                    or not math.isfinite(bearing)
                                    or not 0 <= bearing < 360):
            return "invalid_value"
        self.helo_listen_bearing = bearing
        return True

    def set_helicopter_audio_mode(self, mode: str):
        if type(mode) is not str or not self.helo_audition.set_audition_mode(mode):
            return "invalid_value"
        return True

    def set_helicopter_audio_band(self, preset: str):
        band = SONAR_BAND_PRESETS.get(preset) if type(preset) is str else None
        if band is None:
            return "invalid_value"
        self.helo_audition.band_low_hz, self.helo_audition.band_high_hz = band
        self.helo_audio_band = preset
        return True

    def set_helicopter_audio_gain(self, gain_db):
        if type(gain_db) not in (int, float) or not math.isfinite(gain_db) \
                or not -12 <= gain_db <= 24:
            return "invalid_value"
        self.helo_audition.gain_db = float(gain_db)
        return True

    def set_helicopter_audio_notch(self, enabled):
        if type(enabled) is not bool:
            return "invalid_value"
        self.helo_audition.notch_enabled = enabled
        return True

    def helicopter_audio_ready(self) -> bool:
        """The selected helicopter hydrophone must be in the water."""
        source = self.helo_listen_source
        if source == "DIP":
            return self.helo.dip_available and self.helo.dip_depth_m > 0.0
        if not source.startswith("SB") or not source[2:].isdigit():
            return False
        seq = int(source[2:])
        return any(b.seq == seq and b.active and b.mode == "PASSIVE"
                   for b in self.buoys)

    def launch_helo_torpedo(self) -> None:
        """Leichttorpedo vom HSP-5 (eigene Munition, nicht Fregatten-Rohre)."""
        if (self.target is None
                or self.sim_t - self.target.last_seen >= config.SONAR_CONTACT_LOST_S):
            self.target = None
            self.flash(message("runtime.target.invalid"))
            return
        self.launch_helicopter_torpedo_at(self.target, self.torpedo_depth)

    def launch_helicopter_torpedo_at(self, contact, depth_m: float):
        """Release a helicopter torpedo against one explicit sonar observation."""
        if (contact is None or type(depth_m) not in (int, float)
                or not math.isfinite(depth_m) or not 10 <= depth_m <= 300
                or self.sim_t - contact.last_seen >= config.SONAR_CONTACT_LOST_S):
            self.flash(message("runtime.target.invalid"))
            return "invalid_target"
        blocked = self._target_affiliation_interlock(contact)
        if blocked is not None:
            self.flash(message("runtime.roe.blocked",
                               affiliation=display_value("affiliation", blocked, self.tr)))
            return "roe_blocked"
        if self.roe == "STD" and not self._contact_range_fresh(contact):
            self.flash(message("runtime.target.not_located"))
            return "not_located"
        if self.weapon_classification(contact) != "U_BOOT":
            self.flash(message("runtime.target.air_class"))
            return "not_classified"
        if not self.helo.airborne:
            self.flash(message("runtime.helo.not_airborne"))
            return "not_ready"
        if self.helo.torps <= 0:
            self.flash(message("runtime.helo_no_torpedoes"))
            return "empty"
        if not self.helo.water_entry_clear(self.world):
            self.flash(message("runtime.helo.water_required"))
            return "water_required"
        tgt = self._find_target(contact.target_id)
        lv = self.difficulty
        range_nm = (contact.range_est if contact.range_est is not None
                    else config.ROE_FREE_LAUNCH_RANGE_NM)
        use_fix = (self._contact_range_fresh(contact)
                   and contact.observed_x is not None
                   and contact.observed_y is not None)
        datum = self.helo.release_datum_from_ship_observation(
            self.ship, contact.bearing, range_nm,
            bearing_uncertainty_deg=max(0.0, (1.0 - contact.quality) * 8.0),
            range_uncertainty_nm=contact.range_sigma_nm or 0.0,
            datum_x=contact.observed_x if use_fix else None,
            datum_y=contact.observed_y if use_fix else None)
        torp = self.helo.drop_torpedo(
            tgt, depth_m, self.torpedo_seq + 1,
            kill_dist_nm=lv["kill_dist_nm"], kill_depth_m=lv["kill_depth_m"],
            guidance_x=datum.x_nm, guidance_y=datum.y_nm, world=self.world)
        if torp is None:
            return "not_ready"
        self.torpedo_seq += 1
        self.torpedoes.append(torp)
        self._emit_sound("water_entry")
        self.flash(message("runtime.helo_torpedo.launched",
                           torpedo=self.torpedo_seq), 2.0)
        self.feed.add(self.world.format_time(), "waffen",
                      message("runtime.helo_torpedo.feed",
                              torpedo=self.torpedo_seq, contact=contact.id))
        return True

    @staticmethod
    def _missile_seq(track):
        """Internal missile sequence behind an ``M-`` air track, else None.

        An ASM cue can also sit on an aircraft track; fire control resolves
        the engaged weapon only through the missile's own track namespace.
        """
        track_id = str(getattr(track, "track_id", ""))
        suffix = track_id[2:]
        return int(suffix) if track_id.startswith("M-") and suffix.isdigit() else None

    def _cycle_asm_track(self, delta: int) -> None:
        n = len(self.asm_tracks())
        if n == 0:
            self.asm_sel = 0
            return
        self.asm_sel = (self.asm_sel + delta) % n

    def launch_essm(self) -> None:
        tracks = self.asm_tracks()
        track = tracks[min(self.asm_sel, len(tracks) - 1)] if tracks else None
        self.launch_essm_at(track)

    def launch_essm_at(self, track):
        """Launch against an explicit current positioned ASM observation."""
        profiles = self._air_defense_loadout
        if self.damage.station_down("opz") or self.damage.station_degraded("opz"):
            self.flash(message("runtime.opz.degraded"))
            return "opz_degraded"
        if self.vls_cells <= 0:
            self.flash(message("runtime.vls.empty"))
            return "empty"
        if len(self.essms) >= profiles["vls"]["fire_channels"]:
            self.flash(message("runtime.vls.empty"))
            return "active_limit"
        if not any(item is track for item in self.asm_tracks()):
            self.flash(message("runtime.asm.none"))
            return "invalid_target"
        sam = profiles["sam"]
        if track.range_nm is None or track.range_nm > sam["range_nm"]:
            self.flash(message("runtime.asm.range", range=f"{sam['range_nm']:.0f}"))
            return "out_of_range"
        if (track.x is None or track.y is None or track.position_seen is None
                or self.sim_t - track.position_seen
                > sam["observation_max_age_s"]):
            self.flash(message("runtime.asm.stale"))
            return "stale_ref"
        missile_seq = self._missile_seq(track)
        tgt = next((a for a in self.asms if a.seq == missile_seq), None)
        course = math.degrees(math.atan2(track.x - self.ship.x,
                                        -(track.y - self.ship.y))) % 360.0
        self.essm_seq += 1
        self.essms.append(ESSM(self.ship.x, self.ship.y, course, tgt,
                               self.essm_seq,
                               guidance_x=track.x, guidance_y=track.y,
                               target_id=missile_seq, profile=sam))
        self.vls_cells -= 1
        self._emit_sound("missile_launch")
        self.announce(message("runtime.essm.launched", cells=self.vls_cells),
                      "waffen", 2.0)
        return True

    def launch_chaff(self) -> None:
        tracks = self.asm_tracks()
        track = tracks[min(self.asm_sel, len(tracks) - 1)] if tracks else None
        self.launch_chaff_at(track)

    def launch_chaff_at(self, track):
        """Deploy one softkill round against an explicit ASM observation."""
        if self.damage.station_down("opz"):
            self.flash(message("runtime.chaff.disabled"))
            return "opz_down"
        if self.softkill_store.ready <= 0:
            self.flash(message("runtime.chaff.cooldown", seconds=f"{self.chaff_cd:.0f}"))
            return "not_ready"
        if track is None or not any(item is track for item in self.asm_tracks()):
            self.flash(message("runtime.chaff.none"))
            return "invalid_target"
        a = next((item for item in self.asms
                  if item.seq == self._missile_seq(track)
                  and item.state == "LAUF"), None)
        profile = self._air_defense_loadout["softkill"]
        if (a is not None and track.range_nm is not None
                and track.position_seen is not None
                and self.sim_t - track.position_seen <= self._air_defense_loadout[
                    "sam"]["observation_max_age_s"]
                and track.range_nm <= profile["range_nm"]
                and self.softkill_store.fire()):
            self.chaff_seq += 1
            threat = math.degrees(math.atan2(a.x - self.ship.x,
                                             -(a.y - self.ship.y))) % 360.0
            cloud = chaff_physics.ChaffCloud(
                self.chaff_seq, *chaff_physics.lay_position(
                    self.ship.x, self.ship.y, threat, self.chaff_seq))
            self.chaff_clouds = (self.chaff_clouds + [cloud])[
                -chaff_physics.MAX_CLOUDS:]
            arrival = (math.hypot(a.x - cloud.x, a.y - cloud.y)
                       / max(config.kn_to_nm_per_s(a.speed_kn), 1e-9))
            broke = a.launch_chaff(self.rng_asm, profile, cloud_seq=cloud.seq,
                                   arrival_s=arrival)
            self.chaff_cd = min(self.softkill_store.loading, default=0.0)
            self.announce(message("runtime.chaff.decoyed" if broke
                                  else "runtime.chaff.jammed"), "waffen")
            return True
        else:
            self.flash(message("runtime.chaff.none"))
            return "stale_ref"

    def deploy_nixie(self) -> None:
        """Deploy one finite towed acoustic countermeasure from own ship."""
        self.deploy_nixie_result()

    def deploy_nixie_result(self):
        if len(self.nixies) >= MAX_TOWED_DECOYS:
            self.flash(message("runtime.nixie.active"))
            return "active_limit"
        if not self.nixie_store.fire():
            self.flash(message("runtime.nixie.empty"))
            return "empty"
        definition = self._ownship_loadout["countermeasure"]
        self.nixie_seq += 1
        self.nixies.append(TowedAcousticDecoy(
            self.nixie_seq, self.ship, life_s=definition["active_life_s"],
            tether_nm=definition["tether_nm"], depth_m=definition["depth_m"]))
        self.announce(message("runtime.nixie.deployed",
                              count=self.nixie_store.remaining_total), "waffen")
        return True

    def set_flak_authorized(self, authorized: bool):
        """Fire-release gate for the AA gun; it never engages FLG raiders
        while withheld, regardless of ammo/cooldown/range readiness."""
        if type(authorized) is not bool:
            return "invalid_value"
        if self.damage.station_down("weapons"):
            return "weapons_down"
        self.flak_authorized = authorized
        return True

    def set_ciws_authorized(self, authorized: bool):
        """Fire-release gate for CIWS; it never engages inbound ASMs while
        withheld, regardless of ammo/cooldown/range readiness."""
        if type(authorized) is not bool:
            return "invalid_value"
        if self.damage.station_down("opz"):
            return "opz_down"
        self.ciws_authorized = authorized
        return True

    def _joy_step(self, delta: int) -> None:
        """uConsole-Trackball Y-Achse: stationsabhängiger Schritt."""
        if self.in_menu or self.game_over:
            return
        if self.station is Station.DAMAGE:
            self.dmg_team = (self.dmg_team - 1 + delta) % 3 + 1
        elif self.station is Station.SONAR:
            self._cycle_selected_contact(delta)
        elif self.station is Station.WEAPONS:
            self.torpedo_depth = config.clamp(
                self.torpedo_depth - delta * 10.0, 10.0, 300.0)
        elif self.station is Station.OPZ:
            self._cycle_opz_track(delta)
        elif self.station is Station.ELOKA:
            self._cycle_eloka_track(delta)
        elif self.station is Station.RADIO:
            self._cycle_hfdf(delta)
        elif self.station is Station.HELICOPTER:
            self._adjust_helo_waypoint(range_delta=float(-delta))
        elif self.station is Station.BRIDGE:
            self.ship.cycle_telegraph(-delta)
            self.flash(message("runtime.telegraph", order=self.ship.telegraph), 1.5)
        elif self.station is Station.ENGINE:
            self._cycle_engine_telegraph(-delta)
            self.flash(message("runtime.telegraph", order=self.ship.telegraph), 1.5)

    def _joy_horizontal_step(self, delta: int) -> None:
        """uConsole-Trackball X-Achse: selection or bearing step."""
        if self.in_menu or self.game_over:
            return
        if self.station is Station.DAMAGE:
            n = len(self.damage.compartments)
            self.dmg_cursor = (self.dmg_cursor + delta) % n
        elif self.station is Station.SONAR:
            self.sonar.set_listen_bearing(self.sonar.listen_bearing + delta * .5)
        elif self.station is Station.WEAPONS:
            self._cycle_selected_contact(delta)
        elif self.station is Station.OPZ:
            self._cycle_asm_track(delta)
        elif self.station is Station.HELICOPTER:
            self._adjust_helo_waypoint(bearing_delta=float(delta * 15))

    @staticmethod
    def _smooth_sensor_noise(seed: int, now: float,
                             period_s: float) -> float:
        """Deterministic, smoothly correlated unit noise on simulation time."""
        import random
        scaled = now / period_s
        epoch = math.floor(scaled)
        fraction = scaled - epoch
        blend = fraction * fraction * (3.0 - 2.0 * fraction)
        first = random.Random(seed + epoch * 104729).uniform(-1.0, 1.0)
        second = random.Random(seed + (epoch + 1) * 104729).uniform(-1.0, 1.0)
        return first + (second - first) * blend

    def _observation_key(self, namespace: str, identity: object) -> str:
        value = f"{self.seed}:{namespace}:{identity}".encode("utf-8")
        return hashlib.blake2b(value, digest_size=8).hexdigest().upper()

    def lunar_age_days(self) -> float:
        """Lunar age: seeded per world, advancing with simulation time."""
        return (detrand.u01(self.seed, "lunar-age") * visual_physics.SYNODIC_MONTH_D
                + self.sim_t / 86400.0) % visual_physics.SYNODIC_MONTH_D

    def moon_illumination(self) -> float:
        """Illuminated lunar fraction."""
        return visual_physics.moon_illumination(self.lunar_age_days())

    def _reset_lookout_reports(self) -> None:
        """Transient bridge-lookout report log (like the feed, never saved)."""
        self.lookout_reports: list[dict] = []
        self._lookout_land_seen: set[int] = set()
        self._lookout_land_epoch: int | None = None

    def _lookout_environment(self) -> dict:
        return dict(
            visibility_nm=getattr(self.world, "visibility_nm",
                                  config.WEATHER_VISIBILITY_MAX_NM),
            night=self.world.is_night(), illumination=self.moon_illumination(),
            sea_state=getattr(self.world, "effective_sea_state", self.world.sea_state))

    def _lookout_observe(self, actor, namespace: str, kind: str,
                         seed: int, altitude_m: float | None = None,
                         classes: tuple | None = None) -> None:
        import random

        dx, dy = actor.x - self.ship.x, actor.y - self.ship.y
        distance = math.hypot(dx, dy)
        environment = self._lookout_environment()
        margin = LOOKOUT_MODEL.margin(kind, distance, altitude_m=altitude_m,
                                      **environment)
        if (margin < 1.0 or self.world.land_blocks_line(
                self.ship.x, self.ship.y, actor.x, actor.y)):
            return
        bearing = math.degrees(math.atan2(dx, -dy)) % 360.0
        epoch = math.floor((self.sim_t + 1e-9) / config.LOOKOUT_EPOCH_S)
        rng = random.Random(seed * 65537 + epoch * 104729 + 0x4C4F4F4B)
        measured_bearing = (bearing + rng.uniform(
            -config.LOOKOUT_BEARING_ERR_DEG,
            config.LOOKOUT_BEARING_ERR_DEG)) % 360.0
        measured_range = max(0.0, distance * (1.0 + rng.uniform(
            -config.LOOKOUT_RANGE_ERR_FRAC, config.LOOKOUT_RANGE_ERR_FRAC)))
        # Contrast margin: just above threshold is a doubtful sighting.
        quality = config.clamp(.5 + .45 * (1.0 - 1.0 / margin), .5, .95)
        identity = getattr(actor, "id", getattr(actor, "seq", 0))
        track_id = "L-" + self._observation_key(namespace, identity)
        # Johnson criteria: the class needs a finer resolved silhouette than
        # the sighting, the type finer still.  A class once made out is held
        # while the lookout keeps the contact.
        level = lookout_id.DETECTED
        recognized = identified = type_key = None
        if classes is not None:
            recognized, identified, type_key = classes
            if LOOKOUT_MODEL.margin(
                    kind, distance, altitude_m=altitude_m,
                    detail=lookout_id.RECOGNIZE_CYCLES / lookout_id.CLASS_SIZE[recognized],
                    **environment) >= 1.0:
                level = lookout_id.RECOGNIZED
                if LOOKOUT_MODEL.margin(
                        kind, distance, altitude_m=altitude_m,
                        detail=lookout_id.IDENTIFY_CYCLES / lookout_id.CLASS_SIZE[identified],
                        **environment) >= 1.0:
                    level = lookout_id.IDENTIFIED
        previous = self.air_picture.current(track_id, self.sim_t)
        previous_level = (lookout_id.decode(previous.label)[0]
                          if previous is not None and previous.source == "LOOKOUT" else -1)
        level = max(level, previous_level)
        label = lookout_id.encode(level, recognized, identified, type_key)
        # A bare detection only says what the eye sees: something on the
        # surface or a wake. Submarine/torpedo domains need recognition.
        published_kind = (kind if level >= lookout_id.RECOGNIZED
                          or kind in ("SURFACE", "FLG")
                          else "SURFACE" if kind == "SUB" else "UNKNOWN")
        track = self.air_picture.observe(
            track_id=track_id,
            kind=published_kind, target_id=0, source="LOOKOUT",
            bearing=measured_bearing, range_nm=measured_range,
            observer_x=self.ship.x, observer_y=self.ship.y, course=None,
            quality=quality, now=self.sim_t, label=label,
            bearing_uncertainty_deg=(config.LOOKOUT_BEARING_ERR_DEG
                                     / math.sqrt(3.0)))
        # One report per new sighting and per step up in recognition; a call
        # inside the same measurement epoch leaves the track unchanged.
        if level > previous_level and track.label == label:
            self._lookout_report(kind, label, measured_bearing, measured_range)

    def lookout_report_text(self, report: dict):
        """Localizable report line: 'Bridge lookout: frigate bearing 040, 3.8 NM'."""
        return message("lookout.report", what=self.lookout_report_what(report),
                       bearing=f"{report['bearing']:03.0f}",
                       range=f"{report['range_nm']:.1f}")

    def lookout_report_what(self, report: dict):
        if report["code"] is None:
            return message(f"lookout.detect.{report['kind'].lower()}")
        what = message(f"lookout.class.{report['code'].lower()}")
        if report["type_name"]:
            what = message("lookout.with_type", what=what,
                           type=raw_text(report["type_name"]))
        return what

    def lookout_visual_what(self, label):
        """What the lookout reported for a visual track label, or None."""
        _level, code, type_key = lookout_id.decode(label)
        if code is None:
            return None
        return self.lookout_report_what(dict(
            kind=None, code=code, type_name=self.lookout_type_name(type_key)))

    def lookout_type_name(self, type_key: str | None) -> str | None:
        if type_key is None:
            return None
        profile = (self.runtime_catalog.surfaces.get(type_key)
                   or self.runtime_catalog.aircraft.get(type_key))
        return None if profile is None else str(profile.name)

    def _lookout_report(self, kind: str, label: str, bearing: float,
                        range_nm: float) -> None:
        level, code, type_key = lookout_id.decode(label)
        report = dict(t=self.sim_t, stamp=self.world.format_time(), kind=kind,
                      level=level, code=code,
                      type_name=self.lookout_type_name(type_key),
                      bearing=bearing % 360.0, range_nm=range_nm)
        self.lookout_reports.append(report)
        del self.lookout_reports[:-config.LOOKOUT_REPORTS_MAX]
        text = self.lookout_report_text(report)
        if kind in ("TORP", "SUB") and level > lookout_id.DETECTED:
            self.announce(text, "ausguck", 4.0)
        else:
            self.feed.add(self.world.format_time(), "ausguck", text)

    def _update_lookout_land(self) -> None:
        """'Land in sight': nearest coast of each landmass on a slow cadence."""
        epoch = math.floor((self.sim_t + 1e-9) / config.LOOKOUT_LAND_CHECK_S)
        if epoch == self._lookout_land_epoch:
            return
        self._lookout_land_epoch = epoch
        environment = self._lookout_environment()
        horizon = visual_physics.optical_horizon_nm(
            visual_physics.LOOKOUT_EYE_HEIGHT_M, visual_physics.TARGET_HEIGHT_M["LAND"])
        ox, oy = self.ship.x, self.ship.y
        seen = set()
        for index, landmass in enumerate(self.world.coast.landmasses):
            left, top, right, bottom = landmass.bounds
            if (max(left - ox, 0.0, ox - right) > horizon
                    or max(top - oy, 0.0, oy - bottom) > horizon):
                continue
            best = None
            points = landmass.points
            for position, first in enumerate(points):
                second = points[(position + 1) % len(points)]
                sx, sy = second[0] - first[0], second[1] - first[1]
                length = sx * sx + sy * sy
                along = (0.0 if length <= 1e-12 else max(0.0, min(1.0, (
                    (ox - first[0]) * sx + (oy - first[1]) * sy) / length)))
                px, py = first[0] + sx * along, first[1] + sy * along
                distance = math.hypot(px - ox, py - oy)
                if best is None or distance < best[0]:
                    best = (distance, px, py)
            if best is None or LOOKOUT_MODEL.margin(
                    "LAND", best[0], **environment) < 1.0:
                continue
            seen.add(index)
            if index not in self._lookout_land_seen:
                bearing = math.degrees(math.atan2(best[1] - ox, -(best[2] - oy))) % 360.0
                self._lookout_report("LAND", lookout_id.encode(
                    lookout_id.RECOGNIZED, "LAND", "LAND", None), bearing, best[0])
        self._lookout_land_seen = seen

    def _update_lookout_picture(self) -> None:
        """Publish bounded visual fixes without correlating sensor identities."""
        # A shallow-running torpedo leaves a visible bubble track by day in a
        # moderate sea.
        if (not self.world.is_night()
                and getattr(self.world, "effective_sea_state", self.world.sea_state) <= 3.0):
            for torpedo in sorted(self.enemy_torpedoes, key=lambda item: item.id):
                if (torpedo.state == "RUN" and torpedo.depth <= TORPEDO_WAKE_VISIBLE_DEPTH_M
                        and math.hypot(torpedo.x - self.ship.x, torpedo.y - self.ship.y)
                        <= TORPEDO_WAKE_VISIBLE_NM):
                    self._lookout_observe(torpedo, "torpedo-wake", "TORP",
                                          torpedo.id, classes=("TORPEDO_WAKE",
                                                               "TORPEDO_WAKE", None))
        for actor in sorted(self.civilians + self.warships,
                            key=lambda item: item.id):
            if not actor.sunk:
                self._lookout_observe(
                    actor, "surface", "SURFACE", actor.sensor_seed,
                    classes=lookout_id.surface_classes(getattr(actor, "profile", None)))
        for actor in sorted(self.subs, key=lambda item: item.id):
            if (not actor.sunk and actor.state != "SINKING"
                    and actor.depth <= config.LOOKOUT_SUB_SURFACED_MAX_DEPTH_M):
                self._lookout_observe(actor, "sub", "SUB", actor.sensor_seed,
                                      classes=("SUBMARINE", "SUBMARINE", None))
        for actor in sorted(self.flights.flights, key=lambda item: item.seq):
            if actor.active:
                self._lookout_observe(
                    actor, "flight", "FLG", actor.sensor_seed + 200_000,
                    altitude_m=actor.altitude_m,
                    classes=lookout_id.aircraft_classes(
                        getattr(actor, "kind", "military"), getattr(actor, "akey", None)))
        for actor in sorted(self.raiders, key=lambda item: item.seq):
            if not actor.despawned and actor.hp > 0:
                self._lookout_observe(
                    actor, "raider", "FLG", actor.seq + 400_000,
                    altitude_m=getattr(actor, "altitude_m", 0.0),
                    classes=lookout_id.aircraft_classes("military", None))
        for actor in sorted(self.live_traffic.aircraft.values(),
                            key=lambda item: item.seq):
            if not actor.despawned:
                self._lookout_observe(
                    actor, "live_air", "FLG", actor.seq + 800_000,
                    altitude_m=getattr(actor, "altitude_m", 0.0),
                    # Indistinguishable from simulated civil traffic.
                    classes=lookout_id.aircraft_classes("civil", None))
        self._update_lookout_land()

    def _update_air_picture(self, full_scan: bool = False) -> None:
        """Create noisy observations; consumers never receive world objects.

        Radar contacts are looked at only where the rotating antenna swept
        since the previous publication (``full_scan`` treats the call as one
        complete revolution) and only when the detector declares the echo.
        """
        import random
        station_live = not self.damage.station_down("opz")
        surface_live = self.surface_radar_on and station_live
        air_live = self.air_radar_on and station_live
        swept_deg = 360.0 if full_scan else self.radar_scan_pending_deg
        self.radar_scan_pending_deg = 0.0
        self.ais.update(self.sim_t, self.civilians, self.ship, self.world)
        error_scale = 1.0 + (config.RADAR_WEATHER_ERROR_GAIN
                             * self.radar_weather_severity()
                             + config.RADAR_RAIN_ERROR_GAIN
                             * self.radar_rain_severity())
        for c in self.civilians:
            if c.sunk:
                continue
            dist = c.distance_nm(self.ship)
            bearing = c.bearing_from_frigate(self.ship)
            aspect = config.aspect_rcs_factor(c.course, bearing)
            horizon = config.radar_horizon_nm(
                config.RADAR_ANTENNA_HEIGHT_M, config.RADAR_SURFACE_TARGET_HEIGHT_M)
            radar_eligible = (surface_live and dist <= horizon
                              and self._radar_look("surface", c.sensor_seed, dist,
                                                   bearing, swept_deg=swept_deg,
                                                   rcs_factor=aspect ** 4))
            radar_clear = radar_eligible and not self.world.land_blocks_line(
                self.ship.x, self.ship.y, c.x, c.y)
            if radar_eligible and radar_clear:
                rng = random.Random(c.sensor_seed * 3571 + int(self.sim_t * 2.0))
                bearing_error = config.RADAR_BEARING_ERR_DEG * error_scale
                brg = (bearing + rng.uniform(-bearing_error, bearing_error)) % 360.0
                range_error = config.RADAR_RANGE_ERR_FRAC * error_scale
                measured = max(0.0, dist * (1.0 + rng.uniform(
                    -range_error, range_error)))
                # Radar measures position only. Name and course of a civilian
                # are known only from AIS reports the receiver has decoded.
                self.air_picture.observe(track_id=f"S-{c.id}", kind="SURFACE",
                    target_id=c.id, source="RADAR-S", bearing=brg,
                    range_nm=measured, observer_x=self.ship.x, observer_y=self.ship.y,
                    course=self.ais.course_for(c.id, self.sim_t), quality=.95,
                    now=self.sim_t, label=self.ais.label_for(c.id) or f"S-{c.id}",
                    bearing_uncertainty_deg=bearing_error / math.sqrt(3.0))
        for w in self.warships:
            if w.sunk:
                continue
            dist = w.distance_nm(self.ship)
            bearing = w.bearing_from_frigate(self.ship)
            aspect = config.aspect_rcs_factor(w.course, bearing)
            horizon = config.radar_horizon_nm(
                config.RADAR_ANTENNA_HEIGHT_M, config.RADAR_SURFACE_TARGET_HEIGHT_M)
            radar_eligible = (surface_live and dist <= horizon
                              and self._radar_look("surface", w.sensor_seed, dist,
                                                   bearing, swept_deg=swept_deg,
                                                   rcs_factor=aspect ** 4))
            radar_clear = radar_eligible and not self.world.land_blocks_line(
                self.ship.x, self.ship.y, w.x, w.y)
            if radar_eligible and radar_clear:
                rng = random.Random(w.sensor_seed * 3571 + int(self.sim_t * 2.0))
                bearing_error = config.RADAR_BEARING_ERR_DEG * error_scale
                brg = (bearing + rng.uniform(-bearing_error, bearing_error)) % 360.0
                range_error = config.RADAR_RANGE_ERR_FRAC * error_scale
                measured = max(0.0, dist * (1.0 + rng.uniform(
                    -range_error, range_error)))
                # Same S-<id> form as civilians (shared SurfaceShip ID counter):
                # the track ID must not reveal that a contact is a warship.
                self.air_picture.observe(track_id=f"S-{w.id}", kind="SURFACE",
                    target_id=w.id, source="RADAR-S", bearing=brg,
                    range_nm=measured, observer_x=self.ship.x, observer_y=self.ship.y,
                    course=None, quality=.9, now=self.sim_t,
                    label=f"S-{w.id}",
                    bearing_uncertainty_deg=bearing_error / math.sqrt(3.0))
        self._update_mast_echoes(surface_live, swept_deg, error_scale)
        for f in self.flights.flights:
            dist = f.distance_nm(self.ship)
            bearing = f.bearing_to_frigate(self.ship)
            horizon = config.radar_horizon_nm(
                config.RADAR_ANTENNA_HEIGHT_M, f.altitude_m)
            radar_eligible = (air_live and dist <= horizon
                              and self._radar_look("air", f.seq + 10000, dist,
                                                   bearing, swept_deg=swept_deg))
            radar_clear = radar_eligible and not self.world.land_blocks_line(
                self.ship.x, self.ship.y, f.x, f.y)
            if radar_eligible and radar_clear:
                rng = random.Random((f.seq + 10000) * 3571 + int(self.sim_t * 2.0))
                bearing_error = config.RADAR_BEARING_ERR_DEG * error_scale
                brg = (bearing + rng.uniform(-bearing_error, bearing_error)) % 360.0
                range_error = config.RADAR_RANGE_ERR_FRAC * error_scale
                measured = max(0.0, dist * (1.0 + rng.uniform(
                    -range_error, range_error)))
                altitude = config.measure_altitude_m(rng, f.altitude_m, error_scale)
                self.air_picture.observe(track_id=f"A-{f.seq}",
                    kind=self._radar_air_kind(f"A-{f.seq}", altitude),
                    target_id=f.seq, source="RADAR-L", bearing=brg, range_nm=measured,
                    observer_x=self.ship.x, observer_y=self.ship.y, course=None,
                    quality=.85, now=self.sim_t, label=f"A-{f.seq}",
                    bearing_uncertainty_deg=bearing_error / math.sqrt(3.0),
                    altitude_m=altitude)
        for r in self.raiders:
            dist = r.distance_nm(self.ship)
            bearing = r.bearing_from_frigate(self.ship)
            horizon = config.radar_horizon_nm(
                config.RADAR_ANTENNA_HEIGHT_M, getattr(r, "altitude_m", 0.0))
            radar_eligible = (air_live and dist <= horizon
                              and self._radar_look("air", r.seq + 60000, dist,
                                                   bearing, swept_deg=swept_deg))
            radar_clear = radar_eligible and not self.world.land_blocks_line(
                self.ship.x, self.ship.y, r.x, r.y)
            if radar_eligible and radar_clear:
                rng = random.Random((r.seq + 60000) * 3571 + int(self.sim_t * 2.0))
                bearing_error = config.RADAR_BEARING_ERR_DEG * error_scale
                brg = (bearing + rng.uniform(-bearing_error, bearing_error)) % 360.0
                range_error = config.RADAR_RANGE_ERR_FRAC * error_scale
                measured = max(0.0, dist * (1.0 + rng.uniform(
                    -range_error, range_error)))
                altitude = config.measure_altitude_m(
                    rng, getattr(r, "altitude_m", 0.0), error_scale)
                self.air_picture.observe(track_id=f"R-{r.seq}",
                    kind=self._radar_air_kind(f"R-{r.seq}", altitude),
                    target_id=r.seq, source="RADAR-L", bearing=brg,
                    range_nm=measured,
                    observer_x=self.ship.x, observer_y=self.ship.y, course=None,
                    quality=.85, now=self.sim_t, label=f"A-{r.seq}",
                    bearing_uncertainty_deg=bearing_error / math.sqrt(3.0),
                    altitude_m=altitude)
        for live in self.live_traffic.aircraft.values():
            if live.despawned:
                continue
            dist = live.distance_nm(self.ship)
            bearing = live.bearing_from_frigate(self.ship)
            horizon = config.radar_horizon_nm(
                config.RADAR_ANTENNA_HEIGHT_M, getattr(live, "altitude_m", 0.0))
            radar_eligible = (air_live and dist <= horizon
                              and self._radar_look("air", live.seq + 90000, dist,
                                                   bearing, swept_deg=swept_deg))
            radar_clear = radar_eligible and not self.world.land_blocks_line(
                self.ship.x, self.ship.y, live.x, live.y)
            if radar_eligible and radar_clear:
                rng = random.Random((live.seq + 90000) * 3571 + int(self.sim_t * 2.0))
                bearing_error = config.RADAR_BEARING_ERR_DEG * error_scale
                brg = (bearing + rng.uniform(-bearing_error, bearing_error)) % 360.0
                range_error = config.RADAR_RANGE_ERR_FRAC * error_scale
                measured = max(0.0, dist * (1.0 + rng.uniform(
                    -range_error, range_error)))
                # Selbe Track-ID-Form wie simulierte Fluege (A-<seq>, geteilter
                # Zaehler via FlightManager.next_seq): reale und simulierte
                # Luftkontakte sind fuer den Spieler ununterscheidbar.
                altitude = config.measure_altitude_m(
                    rng, live.altitude_m, error_scale)
                self.air_picture.observe(track_id=f"A-{live.seq}",
                    kind=self._radar_air_kind(f"A-{live.seq}", altitude),
                    target_id=live.seq, source="RADAR-L", bearing=brg,
                    range_nm=measured,
                    observer_x=self.ship.x, observer_y=self.ship.y, course=None,
                    quality=.85, now=self.sim_t, label=f"A-{live.seq}",
                    bearing_uncertainty_deg=bearing_error / math.sqrt(3.0),
                    altitude_m=altitude)
        ciws_track = station_live and self.ciws_authorized
        for a in self.asms:
            if a.state not in ("LAUF", "CHAFF"):
                continue
            dist = a.distance_nm(self.ship)
            # A sea-skimmer is below the radar (and radio) horizon until close.
            if dist > config.radar_horizon_nm(config.RADAR_ANTENNA_HEIGHT_M,
                                              a.altitude_m):
                continue
            if (a.jamming(self.ship) and dist <= config.ESM_RANGE_NM
                    and not self.world.land_blocks_line(
                        self.ship.x, self.ship.y, a.x, a.y)):
                noise = self._smooth_sensor_noise(
                    a.seq * 7919, self.sim_t, 5.0)
                brg = (a.bearing_to_frigate(self.ship)
                       + noise * 5.0) % 360.0
                self.air_picture.observe(track_id=f"M-{a.seq}",
                    kind=self._radar_air_kind(f"M-{a.seq}", None, jamming=True),
                    target_id=a.seq, source="HOJ", bearing=brg, range_nm=None,
                    observer_x=self.ship.x, observer_y=self.ship.y, course=None,
                    quality=.55, now=self.sim_t, label=f"A-{a.seq}",
                    jamming=True, bearing_uncertainty_deg=5.0 / math.sqrt(3.0))
            elif ((air_live or ciws_track)
                  and self._radar_look(
                      "air", a.seq + 120000, dist, a.bearing_to_frigate(self.ship),
                      # The CIWS search/track radar holds close-in missiles
                      # continuously; beyond it only the rotating antenna looks.
                      swept_deg=(360.0 if ciws_track and dist <= CIWS_TRACK_RANGE_NM
                                 else swept_deg if air_live else 0.0),
                      jnr=self._asm_jammer_to_noise(a, dist))
                  and not self.world.land_blocks_line(
                      self.ship.x, self.ship.y, a.x, a.y)):
                rng = random.Random(a.seq * 7919 + int(self.sim_t * 2.0))
                bearing_error = config.RADAR_BEARING_ERR_DEG * error_scale
                brg = (a.bearing_to_frigate(self.ship)
                       + rng.uniform(-bearing_error, bearing_error)) % 360.0
                range_error = config.RADAR_RANGE_ERR_FRAC * error_scale
                measured = max(0.0, dist * (1.0 + rng.uniform(
                    -range_error, range_error)))
                altitude = config.measure_altitude_m(rng, a.altitude_m, error_scale)
                self.air_picture.observe(track_id=f"M-{a.seq}",
                    kind=self._radar_air_kind(f"M-{a.seq}", altitude),
                    target_id=a.seq, source="RADAR-L", bearing=brg, range_nm=measured,
                    observer_x=self.ship.x, observer_y=self.ship.y, course=None,
                    quality=.9, now=self.sim_t, label=f"A-{a.seq}",
                    bearing_uncertainty_deg=bearing_error / math.sqrt(3.0),
                    altitude_m=altitude)
        self._update_lookout_picture()
        self.air_picture.expire(self.sim_t)

    def _radar_air_kind(self, track_id: str, altitude_m, jamming: bool = False) -> str:
        """Threat evaluation from this track's own measurements only."""
        previous = self.air_picture.current(track_id, self.sim_t)
        return threat_cue.air_track_kind(
            None if previous is None else previous.kind,
            None if previous is None else previous.derived_motion()[1],
            altitude_m, jamming)

    def radar_tracks(self) -> list:
        """Compatibility view of the persistent surface/air picture."""
        tracks = []
        for t in self.air_picture.tracks(self.sim_t):
            if "AIS" in t.source.upper():
                continue
            derived_course, derived_speed = t.derived_motion()
            tracks.append(dict(
                kind=t.kind, track_id=t.track_id, target_id=t.target_id,
                source=t.source, dist=t.range_nm, bearing=t.bearing,
                x=t.x, y=t.y,
                course=t.course if t.course is not None else derived_course,
                speed_kn=derived_speed,
                quality=t.display_quality(self.sim_t, self.air_picture.stale_s),
                label=self.opz_track_label(
                    self._opz_observation_id("picture", t.track_id),
                    self._opz_observation_id("picture", t.track_id)[-6:]),
                hostile=t.hostile, jamming=t.jamming,
                age=t.age(self.sim_t), position_seen=t.position_seen,
                bearing_uncertainty_deg=t.bearing_uncertainty_deg,
                altitude_m=t.altitude_m,
                visual=t.label if t.source == "LOOKOUT" else None))
        return tracks

    def _opz_observation_id(self, namespace: str, identity: object) -> str:
        return "O-" + self._observation_key("opz-" + namespace, identity)

    def opz_track_label(self, observation_id: str, fallback: str) -> str:
        """Return the one shared, operator-visible ID for an observation."""
        return self.opz_track_labels.get(observation_id, fallback)

    def contact_display_id(self, contact: Contact) -> str:
        if self._sonar_ctx is not self._frigate_sonar:
            # A crewed boat's contacts never carry frigate OPZ labels.
            return f"K{contact.id:02d}"
        observation_id = self._opz_observation_id("sonar", contact.target_id)
        return self.opz_track_label(observation_id, f"K{contact.id:02d}")

    def set_opz_track_label(self, observation_id: str, label: str):
        """Assign an OPZ-authored display ID without changing track identity."""
        if self.damage.station_down("opz"):
            return "opz_down"
        if (type(label) is not str or not 1 <= len(label) <= MAX_TRACK_DISPLAY_ID_LEN
                or not label.isascii()
                or any(not (char.isalnum() or char == "-") for char in label)
                or not any(char.isalnum() for char in label)):
            return "invalid_value"
        current = {item.observation_id for item in self.opz_published_observations()}
        if observation_id not in current:
            return "stale_ref"
        if (observation_id not in self.opz_track_labels
                and len(self.opz_track_labels) >= MAX_OPZ_TRACK_LABELS):
            del self.opz_track_labels[next(iter(self.opz_track_labels))]
        self.opz_track_labels[observation_id] = label.upper()
        return True

    def _detached_air_observations(self) -> list[OPZObservation]:
        observations = []
        bindings = {}
        for track in self.air_picture.tracks(self.sim_t):
            # Sonar owns its release policy and detached report identity. Legacy
            # save-backed mirrors are never consumed as OPZ source reports.
            if track.source.startswith("SONAR") or "AIS" in track.source.upper():
                continue
            observation_id = self._opz_observation_id("picture", track.track_id)
            classification = (self.opz_fusion.classifications.get(observation_id)
                              if (track.source.startswith("RADAR")
                                  or track.source == "HOJ")
                              else self.released_esm_labels().get(track.track_id)
                              if track.source == "ESM" else None)
            kind = "UNKNOWN" if track.source == "ESM" else track.kind
            derived_course, derived_speed = track.derived_motion()
            observation = OPZObservation(
                observation_id, track.source, kind, track.bearing, track.range_nm,
                track.x, track.y,
                track.course if track.course is not None else derived_course,
                track.quality, track.last_seen,
                self.opz_track_label(observation_id, observation_id[-6:]), classification,
                track.bearing_uncertainty_deg, track.position_seen, track.jamming,
                speed_kn=derived_speed, altitude_m=track.altitude_m,
                visual=track.label if track.source == "LOOKOUT" else None)
            observations.append(observation)
            bindings[observation_id] = track
        self._opz_source_bindings = bindings
        return observations

    def _sonar_opz_observations(self, released_only: bool) -> list[OPZObservation]:
        """Return detached Sonar reports without carrying contact identity."""
        observations = []
        for _, contact in sorted(self.sonar.contacts.items()):
            if ((released_only and not contact.released_to_opz)
                    or not 0.0 <= self.sim_t - contact.last_seen
                    < config.SONAR_CONTACT_LOST_S):
                continue
            observation_id = self._opz_observation_id("sonar", contact.target_id)
            fixes = tuple(fix for fix in contact.active_fixes(self.sim_t)
                          if fix["source"] not in ("DIPPING", "SONOBUOY"))
            ship_passive_seen = (contact._bearing_filter_t
                                 if contact._bearing_filter_t is not None
                                 else contact.last_seen)
            ship_passive_current = (contact.passive_bearing is not None
                                    and 0 <= self.sim_t - ship_passive_seen
                                    < config.SONAR_CONTACT_LOST_S)
            if released_only and not ship_passive_current and not fixes:
                continue
            fix_by_source = {item["source"]: item for item in fixes}
            fix = max(fixes, key=lambda item: (item["fixed_at"], item["source"])) \
                if fixes else None
            x = fix["x"] if fix is not None else None
            y = fix["y"] if fix is not None else None
            observer_x = (contact.ship_observer_x
                          if ship_passive_current and contact.ship_observer_x is not None
                          else self.ship.x if ship_passive_current
                          else contact.observer_x)
            observer_y = (contact.ship_observer_y
                          if ship_passive_current and contact.ship_observer_y is not None
                          else self.ship.y if ship_passive_current
                          else contact.observer_y)
            bearing_uncertainty_deg = contact.bearing_uncertainty_deg
            if x is not None and y is not None:
                dx, dy = x - self.ship.x, y - self.ship.y
                bearing = math.degrees(math.atan2(dx, -dy)) % 360.0
                range_nm = math.hypot(dx, dy)
                source = "SONAR-" + fix["source"]
            elif ship_passive_current:
                bearing = contact.passive_bearing
                range_nm = None
                source = contact.passive_source
            elif not released_only and contact.dip_bearing is not None:
                bearing = contact.dip_bearing
                range_nm = None
                source = "SONAR-DIP-BRG"
                observer_x, observer_y = contact.dip_observer_x, contact.dip_observer_y
                bearing_uncertainty_deg = contact.dip_bearing_uncertainty_deg
            else:
                continue
            course = contact.tma_course if "TMA" in fix_by_source else None
            speed = contact.tma_speed if "TMA" in fix_by_source else None
            depth = (contact.depth_est
                     if "PING" in fix_by_source or "DIPPING" in fix_by_source
                     else None)
            observation = OPZObservation(
                observation_id, source, "UNKNOWN", bearing, range_nm, x, y, course,
                max(contact.quality, contact.confidence),
                (fix["measured_at"] if fix is not None
                 else ship_passive_seen if ship_passive_current
                 else contact.last_seen),
                self.opz_track_label(observation_id, f"K{contact.id:02d}"), (contact.player_class
                                      if contact.player_class in config.PLAYER_CLASSES
                                      else None),
                bearing_uncertainty_deg,
                fix["measured_at"] if fix is not None else None,
                depth_m=depth, speed_kn=speed,
                observer_x=observer_x, observer_y=observer_y,
                released_to_opz=contact.released_to_opz)
            observations.append(observation)
            self._opz_source_bindings[observation_id] = contact
        return observations

    def private_sonar_observations(self) -> tuple[OPZObservation, ...]:
        """Fresh private acoustic reports for role-specific projections."""
        return tuple((*self._sonar_opz_observations(False),
                      *self._buoy_opz_observations(released_only=False)))

    def _helicopter_opz_observations(self) -> list[OPZObservation]:
        """The helicopter's separately released, measured dip reports."""
        reports = []
        for _, contact in sorted(self.sonar.contacts.items()):
            if not contact.dip_released_to_opz:
                continue
            passive = (contact.dip_bearing is not None
                       and contact.dip_last_seen is not None
                       and 0 <= self.sim_t - contact.dip_last_seen
                       < config.SONAR_CONTACT_LOST_S)
            fixes = [fix for fix in contact.active_fixes(self.sim_t)
                     if fix["source"] == "DIPPING"]
            fix = max(fixes, key=lambda item: item["fixed_at"]) if fixes else None
            if not passive and fix is None:
                continue
            origin_x = contact.dip_observer_x if passive else contact.observer_x
            origin_y = contact.dip_observer_y if passive else contact.observer_y
            bearing = (contact.dip_bearing if passive else math.degrees(
                math.atan2(fix["x"] - origin_x, -(fix["y"] - origin_y))) % 360.0)
            range_nm = (None if passive else math.hypot(
                fix["x"] - origin_x, fix["y"] - origin_y))
            observation_id = self._opz_observation_id("sonar-dip", contact.target_id)
            reports.append(OPZObservation(
                observation_id,
                "SONAR-DIP-BRG" if passive else "SONAR-DIPPING",
                "UNKNOWN", bearing, range_nm,
                None if passive else fix["x"],
                None if passive else fix["y"], None,
                max(contact.quality, contact.confidence),
                max(contact.dip_last_seen if passive else 0.0,
                    fix["measured_at"] if fix is not None else 0.0),
                self.opz_track_label(observation_id, f"K{contact.id:02d} H"),
                contact.player_class if contact.player_class in config.PLAYER_CLASSES
                else None,
                contact.dip_bearing_uncertainty_deg if passive else None,
                fix["measured_at"] if not passive else None,
                depth_m=fix["depth_m"] if not passive else None,
                observer_x=origin_x, observer_y=origin_y,
                released_to_opz=True))
            self._opz_source_bindings[observation_id] = contact
        return reports

    def _buoy_opz_observations(self, released_only=True) -> list[OPZObservation]:
        reports = []
        for _, contact in sorted(self.sonar.contacts.items()):
            if released_only and (not contact.helo_qualified
                                  or not contact.buoy_released_to_opz):
                continue
            for seq, row in sorted(contact.buoy_reports.items()):
                if not 0 <= self.sim_t - row["measured_at"] < config.SONAR_CONTACT_LOST_S:
                    continue
                observation_id = self._opz_observation_id(
                    f"sonar-buoy-{seq}", contact.target_id)
                reports.append(OPZObservation(
                    observation_id, f"SONAR-BUOY-{seq:02d}-{row['mode']}", "UNKNOWN",
                    row["bearing"], row["range_nm"], row["x"], row["y"],
                    None, row["quality"], row["measured_at"],
                    self.opz_track_label(observation_id, f"B{seq:02d} K{contact.id:02d}"),
                    contact.player_class, row["bearing_uncertainty_deg"],
                    row["measured_at"] if row["x"] is not None else None,
                    observer_x=row["observer_x"], observer_y=row["observer_y"],
                    released_to_opz=bool(contact.helo_qualified
                                         and contact.buoy_released_to_opz)))
                self._opz_source_bindings[observation_id] = contact
        return reports

    def opz_source_observations(self) -> tuple[OPZObservation, ...]:
        if id(self.world) != self._opz_world_identity:
            self.opz_fusion.clear()
            self.opz_track_labels.clear()
            self.opz_selected_track_id = None
            self._opz_world_identity = id(self.world)
        observations = self._detached_air_observations()
        observations.extend(self._sonar_opz_observations(True))
        observations.extend(self._helicopter_opz_observations())
        observations.extend(self._buoy_opz_observations())
        return tuple(sorted(observations, key=lambda item: item.observation_id))

    def opz_published_observations(self) -> tuple[OPZObservation, ...]:
        """Shared OPZ picture, unaffected by host-local suppression."""
        observations = self.opz_source_observations()
        self.opz_fusion.prune(observations)
        fused = [self.opz_fusion.computed(item, observations, self.sim_t,
                                          self.air_picture.stale_s)
                 for item in self.opz_fusion.fusions.values()]
        fused = [replace(item, label=self.opz_track_label(
            item.observation_id, item.label)) for item in fused if item is not None]
        return tuple(sorted((*observations, *(item for item in fused if item is not None)),
                            key=lambda item: item.observation_id))

    def asm_tracks(self) -> list:
        return [t for t in self.air_picture.tracks(self.sim_t, ("ASM",))
                if t.source in ("RADAR", "RADAR-L", "HOJ", "DATALINK")]

    def opz_tracks(self) -> list:
        """Host-visible OPZ reports, with local suppression applied."""
        observations = self.opz_source_observations()
        visible = self.opz_fusion.visible(observations, self.sim_t,
                                          self.air_picture.stale_s)
        return [replace(item, label=self.opz_track_label(
            item.observation_id, item.label)) for item in visible]

    def filtered_opz_tracks(self) -> list:
        """Presentation-only OPZ register filter; never alters observations."""
        tracks = self.opz_tracks()
        selected = getattr(self, "opz_contact_filter", "ALL")
        if selected == "ALL":
            return tracks
        if selected in ("RADAR", "SONAR"):
            return [track for track in tracks
                    if track.source.startswith(selected)]
        if selected == "ESM":
            return [track for track in tracks if track.source == "ESM"]
        kind_domains = {
            "AIS": "SURFACE", "SURFACE": "SURFACE", "SUB": "SUBSURFACE",
            "TORP": "SUBSURFACE", "FLG": "AIR", "ASM": "AIR",
        }
        # Sonar reports carry no sensor domain; the operator's classification
        # (an annotation, not truth) sorts them into the display filter.
        class_domains = {
            "U_BOOT": "SUBSURFACE", "TORPEDO": "SUBSURFACE",
            "KAMPFSCHIFF": "SURFACE", "FAHRZEUG": "SURFACE", "FLUGZEUG": "AIR",
        }
        return [track for track in tracks
                if kind_domains.get(track.kind, class_domains.get(
                    track.classification, "UNKNOWN")) == selected]

    def _cycle_opz_contact_filter(self) -> None:
        filters = ("ALL", "RADAR", "SONAR", "ESM", "AIR", "SURFACE",
                   "SUBSURFACE")
        current = getattr(self, "opz_contact_filter", "ALL")
        index = filters.index(current) if current in filters else 0
        self.opz_contact_filter = filters[(index + 1) % len(filters)]
        tracks = self.filtered_opz_tracks()
        if not any(track.track_id == self.opz_selected_track_id
                   for track in tracks):
            self.opz_selected_track_id = tracks[0].track_id if tracks else None
        self.flash(message(
            "runtime.cic.filter",
            filter=display_value("contact_filter", self.opz_contact_filter,
                                 self.tr)), 1.5)

    # --- Shared operator plot layer ----------------------------------------

    PLOT_TOOL_KEYS = {pygame.K_m: "mark", pygame.K_r: "ruler",
                      pygame.K_b: "bearing", pygame.K_c: "circle",
                      pygame.K_d: "dr"}
    PLOT_CURSOR_STEP_PX = 6
    PLOT_CURSOR_STEP_FAST_PX = 40
    PLOT_PICK_PX = 12

    def _reset_plot_ui(self) -> None:
        """Transient plot-mode state; the drawing itself lives in ``plot``."""
        self.plot_mode = False
        self.plot_tool = "mark"
        self.plot_cursor = (0.0, 0.0)
        self.plot_anchor = None
        self._plot_dr_pending = None

    # ``layer`` selects another crew's plot (the crewed submarine's own);
    # by default the frigate crew's shared plot.
    def plot_add(self, kind, x, y, label="", *, layer=None, **fields):
        """Add one crew drawing at sim time now; returns its id or an error."""
        if kind not in plot_geometry.KINDS:
            return "invalid_value"
        target = self.plot if layer is None else layer
        return target.add({"kind": kind, "label": label,
                           "t": float(self.sim_t), "x": x, "y": y, **fields})

    def plot_remove(self, object_id, *, layer=None):
        return True if (self.plot if layer is None else layer).remove(object_id) else "stale_ref"

    def plot_clear(self, *, layer=None):
        (self.plot if layer is None else layer).clear()
        return True

    def plot_relabel(self, object_id, label, *, layer=None):
        if not plot_geometry.valid_label(label):
            return "invalid_value"
        return True if (self.plot if layer is None else layer).relabel(object_id, label) else "stale_ref"

    def _plot_view(self):
        """The chart camera of the current station, or None without a chart."""
        if self.station is Station.OPZ:
            self._configure_opz_map_view()
            return self.opz_map_view
        if self._map_station_visible():
            self.map_view.set_rect(config.MAP_RECT)
            return self.map_view
        return None

    def toggle_plot_mode(self):
        if self.plot_mode:
            self._reset_plot_ui()
            self.flash(message("plot.flash.off"), 1.5)
            return False
        if self._plot_view() is None:
            self.flash(message("plot.flash.no_chart"), 2.0)
            return None
        self._clear_station_input()
        self.plot_mode = True
        self.plot_anchor = None
        self.plot_cursor = (self.ship.x, self.ship.y)
        self.flash(message("plot.flash.on"), 2.0)
        return True

    def _plot_flash_result(self, result) -> None:
        if isinstance(result, str):
            self.flash(message("plot.flash.full" if result == "full"
                               else "plot.flash.invalid"), 2.0)
        else:
            item = next((obj for obj in self.plot.objects if obj["id"] == result), None)
            if item is not None:
                self.flash(message("plot.flash.added", label=item["label"]), 1.5)

    def _plot_commit_point(self, x=None, y=None) -> None:
        """Enter/click: place the cursor point for the active tool."""
        if x is not None:
            self.plot_cursor = (x, y)
        cx, cy = self.plot_cursor
        tool = self.plot_tool
        if tool == "mark":
            self._plot_flash_result(self.plot_add("mark", cx, cy))
            return
        if tool == "bearing":
            brg, dist = plot_geometry.bearing_distance(self.ship.x, self.ship.y, cx, cy)
            result = (self.plot_add("bearing", self.ship.x, self.ship.y,
                                    bearing=round(brg, 1) % 360.0)
                      if dist > 0.0 else "invalid_value")
            self._plot_flash_result(result)
            return
        if self.plot_anchor is None:
            self.plot_anchor = (cx, cy)
            self.flash(message("plot.flash.second_point"), 2.0)
            return
        ax, ay = self.plot_anchor
        self.plot_anchor = None
        brg, dist = plot_geometry.bearing_distance(ax, ay, cx, cy)
        if tool == "ruler":
            result = self.plot_add("ruler", ax, ay, x2=cx, y2=cy)
        elif tool == "circle":
            result = self.plot_add("circle", ax, ay, radius_nm=round(dist, 2))
        else:
            if dist <= 0.0:
                self._plot_flash_result("invalid_value")
                return
            self._plot_dr_pending = (ax, ay, round(brg, 1) % 360.0)
            self._begin_numeric_input("plot_speed")
            return
        self._plot_flash_result(result)

    def _handle_plot_key(self, key: int, mod: int) -> bool:
        """Plot-mode keys; returns True when the key was consumed."""
        view = self._plot_view()
        if view is None or self._local_station_input_locked():
            self._reset_plot_ui()
            return False
        if key == pygame.K_p or (key == pygame.K_ESCAPE and self.plot_anchor is None):
            self.toggle_plot_mode()
            return True
        if key == pygame.K_ESCAPE:
            self.plot_anchor = None
            return True
        steps = {pygame.K_LEFT: (-1, 0), pygame.K_RIGHT: (1, 0),
                 pygame.K_UP: (0, -1), pygame.K_DOWN: (0, 1)}
        if key in steps:
            px = (self.PLOT_CURSOR_STEP_FAST_PX if mod & pygame.KMOD_SHIFT
                  else self.PLOT_CURSOR_STEP_PX)
            step = px / max(view.scale, 1e-6)
            dx, dy = steps[key]
            limit = self.world.size_nm
            self.plot_cursor = (config.clamp(self.plot_cursor[0] + dx * step, 0.0, limit),
                                config.clamp(self.plot_cursor[1] + dy * step, 0.0, limit))
            return True
        if key in self.PLOT_TOOL_KEYS:
            self.plot_tool = self.PLOT_TOOL_KEYS[key]
            self.plot_anchor = None
            return True
        if key in (pygame.K_RETURN, pygame.K_KP_ENTER):
            self._plot_commit_point()
            return True
        if key in (pygame.K_BACKSPACE, pygame.K_DELETE):
            if mod & pygame.KMOD_SHIFT:
                self.plot_clear()
                self.flash(message("plot.flash.cleared"), 1.5)
                return True
            item = self.plot.nearest(*self.plot_cursor,
                                     self.PLOT_PICK_PX / max(view.scale, 1e-6))
            if item is not None:
                self.plot_remove(item["id"])
                self.flash(message("plot.flash.removed", label=item["label"]), 1.5)
            return True
        return False

    def _handle_plot_click(self, pos) -> bool:
        """Left click on the chart in plot mode places a point there."""
        view = self._plot_view()
        canvas = self._window_to_canvas(pos) if pos is not None else None
        if view is None or canvas is None:
            return False
        if not pygame.Rect(view.rect).collidepoint(canvas):
            return False
        x, y = view.screen_to_world(*canvas)
        limit = self.world.size_nm
        self._plot_commit_point(config.clamp(x, 0.0, limit), config.clamp(y, 0.0, limit))
        return True

    def selected_opz_track(self):
        return next((track for track in self.opz_tracks()
                     if track.track_id == self.opz_selected_track_id), None)

    def designate_opz_track(self) -> None:
        """Hand an observed CIC track to weapons without exposing world truth."""
        track = self.selected_opz_track()
        if track is None:
            self.flash(message("runtime.cic.none"))
            return
        result = self.designate_opz_observation(track.observation_id)
        if result is not True:
            ambiguous = (track.source == "FUSION"
                         and len(self._fusion_contacts(track)) > 1)
            self.flash(message("runtime.cic.fusion_ambiguous" if ambiguous
                               else "runtime.cic.no_solution"))
            return
        self.selected_contact = self.target
        self.flash(message("runtime.cic.designated", track=track.track_id))

    def designate_opz_observation(self, observation_id: str):
        if self.damage.station_down("opz"):
            return "opz_down"
        track = next((item for item in self.opz_published_observations()
                      if item.observation_id == observation_id), None)
        if track is None:
            return "stale_ref"
        if track.source == "FUSION":
            # A fusion hands over its sonar report only when that is unique.
            contacts = self._fusion_contacts(track)
            contact = contacts[0] if len(contacts) == 1 else None
        else:
            bound = self._opz_source_bindings.get(track.observation_id)
            contact = (bound if isinstance(bound, Contact) else
                       next((c for c in self.sonar.contacts.values()
                             if getattr(bound, "target_id", None) == c.target_id),
                            None))
        if (contact is None or self.sonar.contacts.get(contact.target_id) is not contact
                or not 0 <= self.sim_t - contact.last_seen
                < config.SONAR_CONTACT_LOST_S):
            return "no_solution"
        self.target = contact
        return True

    def _fusion_contacts(self, track) -> list:
        """Distinct sonar contacts behind the member reports of one fusion."""
        contacts = []
        for member in getattr(track, "members", ()):
            bound = self._opz_source_bindings.get(member)
            if isinstance(bound, Contact) and not any(
                    item is bound for item in contacts):
                contacts.append(bound)
        return contacts

    def opz_affiliation(self, track_id: str) -> str:
        if track_id not in self.opz_affiliations:
            source_key = getattr(self._opz_source_bindings.get(track_id),
                                 "track_id", None)
            bound = self._opz_source_bindings.get(track_id)
            if isinstance(bound, Contact):
                legacy_key = f"U-{bound.target_id}"
                if legacy_key in self.opz_affiliations:
                    track_id = legacy_key
            if source_key in self.opz_affiliations:
                track_id = source_key
            else:
                opaque = next((key for key, source in self._opz_source_bindings.items()
                               if getattr(source, "track_id", None) == track_id), None)
                if opaque is not None:
                    track_id = opaque
        value = self.opz_fusion.fusion_affiliations.get(
            track_id, self.opz_affiliations.get(track_id, "UNKNOWN"))
        return value if value in config.NATO_AFFILIATIONS else "UNKNOWN"

    def opz_source_classification(self, observation_id: str) -> str | None:
        return source_classification(observation_id,
                                     self.opz_published_observations())

    def classify_sonar_contact(self, contact, classification):
        if self._sonar_down():
            return "sonar_down"
        if classification is not None and classification not in config.PLAYER_CLASSES:
            return "invalid_value"
        if (not isinstance(contact, Contact)
                or self.sonar.contacts.get(contact.target_id) is not contact):
            return "stale_ref"
        if not 0 <= self.sim_t - contact.last_seen < config.SONAR_CONTACT_LOST_S:
            return "stale_ref"
        contact.player_class = classification
        return True

    def release_sonar_contact(self, contact, released: bool, *, source="sonar"):
        if type(released) is not bool:
            return "invalid_value"
        if source not in ("sonar", "helicopter", "buoy"):
            return "invalid_value"
        if self.damage.station_down("sonar"):
            return "sonar_down"
        if (not isinstance(contact, Contact)
                or self.sonar.contacts.get(contact.target_id) is not contact
                or not 0 <= self.sim_t - contact.last_seen
                < config.SONAR_CONTACT_LOST_S):
            return "stale_ref"
        if source == "helicopter":
            dip_current = (contact.dip_last_seen is not None
                           and 0 <= self.sim_t - contact.dip_last_seen
                           < config.SONAR_CONTACT_LOST_S)
            dip_fix = any(fix["source"] == "DIPPING"
                          for fix in contact.active_fixes(self.sim_t))
            if not dip_current and not dip_fix:
                return "stale_ref"
            if released and not contact.helo_qualified:
                return "not_qualified"
            contact.dip_released_to_opz = released
        elif source == "buoy":
            if not any(0 <= self.sim_t - row["measured_at"] < config.SONAR_CONTACT_LOST_S
                       for row in contact.buoy_reports.values()):
                return "stale_ref"
            if released and not contact.helo_qualified:
                return "not_qualified"
            contact.buoy_released_to_opz = released
        else:
            contact.released_to_opz = released
        return True

    def qualify_helicopter_contact(self, contact, qualified: bool):
        if type(qualified) is not bool:
            return "invalid_value"
        if self.damage.station_down("sonar"):
            return "sonar_down"
        if (not isinstance(contact, Contact)
                or self.sonar.contacts.get(contact.target_id) is not contact
                or not 0 <= self.sim_t - contact.last_seen < config.SONAR_CONTACT_LOST_S):
            return "stale_ref"
        if not (any(0 <= self.sim_t - row["measured_at"]
                    < config.SONAR_CONTACT_LOST_S
                    for row in contact.buoy_reports.values())
                or contact.dip_last_seen is not None
                and 0 <= self.sim_t - contact.dip_last_seen
                < config.SONAR_CONTACT_LOST_S
                or any(fix["source"] == "DIPPING"
                       for fix in contact.active_fixes(self.sim_t))):
            return "stale_ref"
        contact.helo_qualified = qualified
        if not qualified:
            contact.dip_released_to_opz = False
            contact.buoy_released_to_opz = False
        return True

    def classify_opz_observation(self, observation_id: str, classification):
        if self.damage.station_down("opz"):
            return "opz_down"
        if classification is not None and classification not in config.PLAYER_CLASSES:
            return "invalid_value"
        track = next((item for item in self.opz_published_observations()
                      if item.observation_id == observation_id), None)
        if track is None:
            return "stale_ref"
        if track.source.startswith("SONAR"):
            # A sonar-origin contact is classified on the contact itself
            # (shared with the Sonar/Helicopter stations), not in the OPZ
            # fusion overlay used for radar-only tracks.
            contact = self._opz_source_bindings.get(observation_id)
            if (not isinstance(contact, Contact)
                    or self.sonar.contacts.get(contact.target_id) is not contact):
                return "stale_ref"
            return self.classify_sonar_contact(contact, classification)
        if not (track.source.startswith("RADAR")
                or track.source in ("HOJ", "FUSION")):
            return "source_owned"
        if classification is None:
            self.opz_fusion.classifications.pop(observation_id, None)
        else:
            self.opz_fusion.classifications[observation_id] = classification
        return True

    def affiliate_opz_observation(self, observation_id: str, affiliation: str):
        if self.damage.station_down("opz"):
            return "opz_down"
        if affiliation not in config.NATO_AFFILIATIONS:
            return "invalid_value"
        track = next((item for item in self.opz_published_observations()
                      if item.observation_id == observation_id), None)
        if track is None:
            return "stale_ref"
        destination = (self.opz_fusion.fusion_affiliations
                       if track.source == "FUSION" else self.opz_affiliations)
        destination[observation_id] = affiliation
        self._sync_live_engagement_hold(observation_id, track.track_id, affiliation)
        return True

    def _live_aircraft_icao_for_track_id(self, track_id) -> str | None:
        """Resolve an air-picture 'A-<seq>' track id to its live ADS-B icao24,
        if that id happens to be bound to a real LiveAircraft rather than a
        simulated Flight (both intentionally share the same id namespace)."""
        if not isinstance(track_id, str) or not track_id.startswith("A-"):
            return None
        try:
            seq = int(track_id[2:])
        except ValueError:
            return None
        return next((icao24 for icao24, aircraft in self.live_traffic.aircraft.items()
                     if aircraft.seq == seq), None)

    def _sync_live_engagement_hold(self, observation_id: str, display_id: str,
                                    affiliation: str) -> None:
        """Real ADS-B traffic is indistinguishable from a simulated contact,
        so a manual HOSTILE call on it is a possible political incident, not
        a weapons release. Any prior engagement confirmation is revoked here
        and must be freshly re-affirmed (confirm_live_engagement) every time
        the classification turns HOSTILE again."""
        bound = self._opz_source_bindings.get(observation_id)
        icao24 = self._live_aircraft_icao_for_track_id(getattr(bound, "track_id", None))
        if icao24 is None:
            return
        self.live_engage_authorized.discard(icao24)
        if affiliation == "HOSTILE":
            self.live_engage_confirm_pending = icao24
            self.flash(message("runtime.cic.hostile_confirm_required",
                               track=display_id), 5.0)
            self.feed.add(self.world.format_time(), "opz",
                          message("runtime.cic.hostile_confirm_required",
                                  track=display_id))
        elif self.live_engage_confirm_pending == icao24:
            self.live_engage_confirm_pending = None

    def live_engagement_pending_for_observation(self, observation_id: str) -> bool:
        """Whether this OPZ observation is the live contact currently
        awaiting an attack confirmation (see _sync_live_engagement_hold)."""
        if self.live_engage_confirm_pending is None:
            return False
        bound = self._opz_source_bindings.get(observation_id)
        icao24 = self._live_aircraft_icao_for_track_id(getattr(bound, "track_id", None))
        return icao24 == self.live_engage_confirm_pending

    def confirm_live_engagement(self) -> bool:
        """OPZ 'Enter': explicit player affirmation to fire on the live,
        real-world contact currently awaiting confirmation after being
        classified HOSTILE. See _sync_live_engagement_hold."""
        icao24 = self.live_engage_confirm_pending
        if icao24 is None or icao24 not in self.live_traffic.aircraft:
            return False
        self.live_engage_authorized.add(icao24)
        self.live_engage_confirm_pending = None
        self.flash(message("runtime.cic.hostile_confirmed"), 2.5)
        self.feed.add(self.world.format_time(), "opz",
                      message("runtime.cic.hostile_confirmed"))
        return True

    def create_opz_fusion(self, observation_ids):
        if self.damage.station_down("opz"):
            return "opz_down"
        if (type(observation_ids) not in (list, tuple)
                or not config.OPZ_FUSION_MEMBER_MIN <= len(observation_ids)
                <= config.OPZ_FUSION_MEMBER_MAX
                or len(set(observation_ids)) != len(observation_ids)):
            return "invalid_value"
        sources = self.opz_source_observations()
        current = {item.observation_id for item in sources}
        if any(key not in current for key in observation_ids):
            return "stale_ref"
        self.opz_fusion.marked = set(observation_ids)
        fusion = self.opz_fusion.create(sources)
        if fusion is None:
            return "fusion_rejected"
        self.opz_selected_track_id = fusion.fusion_id
        return True

    def dissolve_opz_fusion(self, observation_id: str):
        if self.damage.station_down("opz"):
            return "opz_down"
        if observation_id not in self.opz_fusion.fusions:
            return "stale_ref"
        self.opz_fusion.dissolve(observation_id)
        if self.opz_selected_track_id == observation_id:
            self.opz_selected_track_id = None
        return True

    def _cycle_opz_track(self, delta: int) -> None:
        tracks = self.filtered_opz_tracks()
        if not tracks:
            self.opz_selected_track_id = None
            return
        ids = [track.track_id for track in tracks]
        try:
            index = ids.index(self.opz_selected_track_id)
        except ValueError:
            index = -1 if delta > 0 else 0
        self.opz_selected_track_id = ids[(index + delta) % len(ids)]

    def _cycle_opz_affiliation(self) -> None:
        track = self.selected_opz_track()
        if track is None:
            self.flash(message("runtime.cic.none_select"))
            return
        current = self.opz_affiliation(track.track_id)
        order = config.NATO_AFFILIATIONS
        value = order[(order.index(current) + 1) % len(order)]
        if self.affiliate_opz_observation(track.track_id, value) is not True:
            return
        self.flash(message("runtime.cic.affiliation", track=track.track_id,
                           affiliation=display_value("affiliation", value, self.tr)), 2.0)

    def _cycle_opz_classification(self) -> None:
        track = self.selected_opz_track()
        if track is None:
            self.flash(message("runtime.cic.none_select"))
            return
        if track.source.startswith("SONAR"):
            contact = self._opz_source_bindings.get(track.observation_id)
            if not isinstance(contact, Contact):
                self.flash(message("runtime.cic.source_owned"))
                return
            current = contact.player_class
        elif (track.source.startswith("RADAR")
              or track.source in ("HOJ", "FUSION")):
            current = self.opz_fusion.classifications.get(track.observation_id)
        else:
            self.flash(message("runtime.cic.source_owned"))
            return
        order = (None, *config.PLAYER_CLASSES)
        value = order[(order.index(current) + 1) % len(order)]
        self.classify_opz_observation(track.observation_id, value)

    def _toggle_opz_mark(self) -> None:
        track = self.selected_opz_track()
        if track is None or track.source == "FUSION":
            return
        if track.observation_id in self.opz_fusion.marked:
            self.opz_fusion.marked.remove(track.observation_id)
        else:
            self.opz_fusion.marked.add(track.observation_id)

    def _create_opz_fusion(self) -> None:
        result = self.create_opz_fusion(tuple(self.opz_fusion.marked))
        if result is not True:
            self.flash(message("runtime.cic.fusion_rejected"))

    def _dissolve_opz_fusion(self) -> None:
        if self.opz_selected_track_id:
            self.dissolve_opz_fusion(self.opz_selected_track_id)

    def _toggle_opz_suppression(self) -> None:
        track = self.selected_opz_track()
        if track is None:
            return
        key = track.observation_id
        if key in self.opz_fusion.suppressed:
            self.opz_fusion.suppressed.remove(key)
        else:
            self.opz_fusion.suppressed.add(key)

    def eloka_tracks(self) -> tuple:
        """Return detached passive intercepts in stable picture order."""
        return self.esm_picture.tracks(self.sim_t)

    def eloka_visible_tracks(self) -> tuple:
        """Return the one filtered/sorted list used by ELOKA presentation."""
        return filter_and_sort_tracks(
            self.eloka_tracks(), self.sim_t, self.eloka_display_analysis,
            status=self.eloka_status_filter,
            minimum_threat=self.eloka_threat_filter,
            band=self.eloka_band_filter,
            annotated_keys=self.eloka_annotations,
            jamming_keys=(channel.track_key
                          for channel in self.ecm_jammer.channels))

    def _reconcile_eloka_selection(self) -> None:
        visible = self.eloka_visible_tracks()
        keys = {track.track_key for track in visible}
        if self.eloka_selected_track_key not in keys:
            self.eloka_selected_track_key = (visible[0].track_key
                                             if visible else None)

    def _cycle_eloka_filter(self, kind: str) -> None:
        names = {
            "status": ("eloka_status_filter",
                       ("OPERATIONAL", "LIVE", "MEMORY", "ALL")),
            "threat": ("eloka_threat_filter",
                       ("ALL", "LOW", "MEDIUM", "HIGH", "CRITICAL")),
            "band": ("eloka_band_filter",
                     ("ALL", "A_C", "D", "E_F", "G_H", "I_J", "K")),
        }
        attribute, values = names[kind]
        current = getattr(self, attribute)
        setattr(self, attribute, values[(values.index(current) + 1) % len(values)])
        self._reconcile_eloka_selection()

    def selected_eloka_track(self):
        return next((track for track in self.eloka_tracks()
                     if track.track_key == self.eloka_selected_track_key), None)

    def _cycle_eloka_track(self, delta: int) -> None:
        if self.damage.station_down("opz"):
            return
        tracks = self.eloka_visible_tracks()
        if not tracks:
            self.eloka_selected_track_key = None
            return
        keys = [track.track_key for track in tracks]
        try:
            index = keys.index(self.eloka_selected_track_key)
        except ValueError:
            index = -1 if delta > 0 else 0
        self.eloka_selected_track_key = keys[(index + delta) % len(keys)]

    def eloka_candidates(self, track=None) -> tuple:
        if self.damage.station_down("opz"):
            return ()
        track = track or self.selected_eloka_track()
        return (() if track is None else
                rank_emitters(track, self.runtime_catalog.emitters))

    def eloka_display_candidates(self, track=None) -> tuple:
        """Emitter choices shown to the operator: ranked with scores only as
        a training aid; otherwise an unranked library range lookup."""
        if self.operator_assist():
            return self.eloka_candidates(track)
        if self.damage.station_down("opz"):
            return ()
        track = track or self.selected_eloka_track()
        return (() if track is None else
                library_emitters(track, self.runtime_catalog.emitters))

    def eloka_display_analysis(self, track=None):
        """Radar type/threat inferred from the catalog: training aid only."""
        return self.eloka_analysis(track) if self.operator_assist() else None

    def eloka_display_range(self, track):
        return self.eloka_range_estimate(track) if self.operator_assist() else None

    ELOKA_ANALYSIS_CACHE_MAX = 256

    def eloka_analysis(self, track=None):
        track = track or self.selected_eloka_track()
        if track is None:
            return None
        # The ranking depends only on the measured fingerprint and the
        # immutable runtime catalog; memoize it (bounded, never saved).
        emitters = self.runtime_catalog.emitters
        if self.__dict__.get("_eloka_analysis_owner") is not emitters:
            self._eloka_analysis_owner = emitters
            self._eloka_analysis_cache = {}
        key = (track.frequency_hz, track.prf_hz, track.modulation_code)
        cache = self._eloka_analysis_cache
        result = cache.get(key)
        if result is None:
            if len(cache) >= self.ELOKA_ANALYSIS_CACHE_MAX:
                cache.clear()
            result = cache[key] = analyze_signal(track, emitters)
        return result

    def eloka_range_estimate(self, track=None) -> float | None:
        """Range implied by the intercept's peak level, assuming the power
        class of the best-ranked catalog hypothesis (never emitter truth)."""
        track = track or self.selected_eloka_track()
        analysis = self.eloka_analysis(track)
        if analysis is None or not analysis.candidates or track.signal_db <= 0.0:
            return None
        emitter = self.runtime_catalog.emitters.get(
            analysis.candidates[0].emitter_key)
        return estimated_range_nm(track, getattr(emitter, "power_class", "medium"))

    def deploy_jamming(self, track, technique=None):
        if self.damage.station_down("opz"):
            return "opz_down"
        if track is None or not any(item is track for item in self.eloka_tracks()):
            return "stale_ref"
        return self.ecm_jammer.deploy_jamming(
            track, self.sim_t, technique=technique)

    def set_jamming_technique(self, track, technique: str):
        if self.damage.station_down("opz"):
            return "opz_down"
        if track is None or not any(item is track for item in self.eloka_tracks()):
            return "stale_ref"
        return self.ecm_jammer.set_technique(track, technique, self.sim_t)

    def _cycle_jamming_technique(self, track) -> str | None:
        if track is None:
            return None
        channel = next((item for item in self.ecm_jammer.channels
                        if item.track_key == track.track_key), None)
        current = (channel.technique if channel is not None else
                   self.ecm_jammer.recommended_technique(track))
        index = ECM_TECHNIQUES.index(current)
        technique = ECM_TECHNIQUES[(index + 1) % len(ECM_TECHNIQUES)]
        return (technique if self.set_jamming_technique(track, technique) is True
                else None)

    def set_jamming(self, track, enabled: bool):
        if type(enabled) is not bool:
            return "invalid"
        active = (track is not None and any(
            channel.track_key == track.track_key
            for channel in self.ecm_jammer.channels))
        if active == enabled:
            return True
        return self.deploy_jamming(track)

    def set_ecm_auto(self, enabled: bool):
        if type(enabled) is not bool:
            return "invalid"
        if self.damage.station_down("opz"):
            return "opz_down"
        self.ecm_jammer.auto_enabled = enabled
        if not enabled:
            self.ecm_jammer.channels = [channel for channel in
                self.ecm_jammer.channels if not channel.automatic]
        return True

    def _update_ecm(self) -> None:
        tracks = self.eloka_tracks()
        self.ecm_jammer.update(
            tracks, self.sim_t, operational=not self.damage.station_down("opz"))
        if not self.ecm_jammer.auto_enabled:
            return
        occupied = {channel.track_key for channel in self.ecm_jammer.channels}
        threat_order = {"critical": 0, "high": 1, "medium": 2, "low": 3,
                        "unknown": 4}
        choices = []
        for track in tracks:
            if (track.track_key in occupied
                    or track.age(self.sim_t) > ECM_SIGNAL_FRESH_S):
                continue
            analysis = analyze_signal(track, self.runtime_catalog.emitters)
            if (analysis.threat_level not in ("critical", "high")
                    or not analysis.candidates
                    or analysis.candidates[0].score < .65):
                continue
            choices.append((threat_order[analysis.threat_level],
                            track.age(self.sim_t), -track.quality,
                            track.track_key, track))
        for *_, track in sorted(choices):
            if len(self.ecm_jammer.channels) >= self.ecm_jammer.MAX_CHANNELS:
                break
            self.ecm_jammer.deploy_jamming(track, self.sim_t, automatic=True)

    def eloka_annotation(self, track_key: str) -> str | None:
        emitter_key = self.eloka_annotations.get(track_key)
        emitter = self.runtime_catalog.emitters.get(emitter_key)
        return emitter_key if emitter is not None and emitter.domain == "radar" else None

    def eloka_emitter_name(self, emitter_key: str | None) -> str | None:
        """Display name of the platform owning an ESM emitter, or None."""
        if not isinstance(emitter_key, str):
            return None
        return self.runtime_catalog.emitter_name(emitter_key)

    def eloka_annotation_name(self, track_key: str) -> str | None:
        """Operator annotation resolved to the owning platform's name."""
        return self.eloka_emitter_name(self.eloka_annotation(track_key))

    def annotate_eloka_intercept(self, track, emitter_key: str):
        if self.damage.station_down("opz"):
            return "opz_down"
        if not any(item is track for item in self.eloka_tracks()):
            return "stale_ref"
        candidates = {item.emitter_key for item in rank_emitters(
            track, self.runtime_catalog.emitters,
            maximum=len(self.runtime_catalog.emitters))}
        if type(emitter_key) is not str or emitter_key not in candidates:
            return "stale_ref"
        previous = self.eloka_annotation(track.track_key)
        if previous is not None and previous != emitter_key:
            self._remove_released_esm(track.track_key, previous)
        self.eloka_annotations[track.track_key] = emitter_key
        while len(self.eloka_annotations) > ESM_MAX_ANNOTATIONS:
            del self.eloka_annotations[min(self.eloka_annotations)]
        self._publish_released_esm()
        return True

    def clear_eloka_annotation(self, track):
        if self.damage.station_down("opz"):
            return "opz_down"
        if not any(item is track for item in self.eloka_tracks()):
            return "stale_ref"
        previous = self.eloka_annotation(track.track_key)
        self.eloka_annotations.pop(track.track_key, None)
        if previous is not None:
            self._remove_released_esm(track.track_key, previous)
        self._publish_released_esm()
        return True

    def _remove_released_esm(self, track_key: str, emitter_key: str) -> None:
        identity = self._observation_key(
            "esm-release", f"{track_key}:{emitter_key}")
        self.air_picture._tracks.pop(f"E-{identity}", None)

    def _cycle_eloka_annotation(self) -> None:
        if self.damage.station_down("opz"):
            self.flash(message("runtime.eloka.disabled"))
            return
        track = self.selected_eloka_track()
        if track is None:
            self.flash(message("runtime.eloka.none_select"))
            return
        # Training: likeliest first. Otherwise the library range lookup in
        # name order, so the first press does not reveal the best match.
        choices = ([candidate.emitter_key for candidate in rank_emitters(
            track, self.runtime_catalog.emitters,
            maximum=len(self.runtime_catalog.emitters))]
            if self.operator_assist() else sorted(
                (candidate.emitter_key for candidate in library_emitters(
                    track, self.runtime_catalog.emitters,
                    maximum=len(self.runtime_catalog.emitters))),
                key=lambda key: (str(self.eloka_emitter_name(key) or key), key)))
        current = self.eloka_annotation(track.track_key)
        index = choices.index(current) if current in choices else -1
        if index + 1 >= len(choices):
            self.clear_eloka_annotation(track)
            assignment = self.tr("common.unknown")
        else:
            key = choices[index + 1]
            self.annotate_eloka_intercept(track, key)
            assignment = self.eloka_emitter_name(key) or key
        self.flash(message("runtime.eloka.annotation",
                           track=track.track_key, assignment=assignment), 2.0)

    def _publish_released_esm(self) -> None:
        """Release only operator-classified, bearing-only ESM observations."""
        for track in self.eloka_tracks():
            emitter_key = self.eloka_annotation(track.track_key)
            label = self.eloka_emitter_name(emitter_key)
            if emitter_key is None or label is None:
                continue
            identity = self._observation_key(
                "esm-release", f"{track.track_key}:{emitter_key}")
            self.air_picture.observe(
                track_id=f"E-{identity}", kind="UNKNOWN", target_id=0,
                source="ESM", bearing=track.bearing, range_nm=None,
                observer_x=track.observer_x, observer_y=track.observer_y,
                course=None, quality=track.quality, now=track.last_seen,
                label=label, hostile=False,
                bearing_uncertainty_deg=track.bearing_uncertainty_deg)

    def released_esm_labels(self) -> dict[str, str]:
        """Return detached operator-approved labels keyed by public track ID."""
        released = {}
        for track in self.eloka_tracks():
            emitter_key = self.eloka_annotation(track.track_key)
            label = self.eloka_emitter_name(emitter_key)
            if emitter_key is not None and label is not None:
                identity = self._observation_key(
                    "esm-release", f"{track.track_key}:{emitter_key}")
                released[f"E-{identity}"] = label
        return released

    def eloka_correlations(self, track=None) -> tuple:
        """Compare ESM and public radar evidence without target identity."""
        if self.damage.station_down("opz"):
            return ()
        track = track or self.selected_eloka_track()
        if track is None:
            return ()
        raw_evidence = []
        for observed in self.air_picture._tracks.values():
            if (not isinstance(observed.source, str)
                    or not observed.source.startswith("RADAR")
                    or "AIS" in observed.source.upper()):
                continue
            values = (observed.bearing, observed.last_seen)
            optional = (observed.bearing_uncertainty_deg, observed.x,
                        observed.y, observed.position_seen)
            if (not all(isinstance(value, (int, float))
                        and not isinstance(value, bool) and math.isfinite(value)
                        for value in values)
                    or any(value is not None and (
                        not isinstance(value, (int, float))
                        or isinstance(value, bool) or not math.isfinite(value))
                           for value in optional)
                    or (observed.x is None) != (observed.y is None)
                    or not 0.0 <= observed.bearing < 360.0):
                continue
            observed_at = (observed.position_seen if observed.x is not None
                           and observed.position_seen is not None
                           else observed.last_seen)
            if not 0.0 <= observed_at <= self.sim_t \
                    or self.sim_t - observed_at > 30.0:
                continue
            raw_evidence.append((observed.source, observed.bearing,
                                 observed.bearing_uncertainty_deg,
                                 observed.x, observed.y, observed_at))
        evidence = []
        evidence_order = lambda row: (
            row[0], row[1], -1.0 if row[2] is None else row[2],
            0 if row[3] is None else 1,
            0.0 if row[3] is None else row[3],
            0.0 if row[4] is None else row[4], row[5])
        used_keys = set()
        for values in sorted(raw_evidence, key=evidence_order):
            source, bearing, uncertainty, x, y, observed_at = values
            digest = hashlib.blake2b(repr(values).encode("utf-8"),
                                     digest_size=5).hexdigest().upper()
            track_id = f"OBS-{digest}"
            suffix = 2
            while track_id in used_keys:
                track_id = f"OBS-{digest}-{suffix}"
                suffix += 1
            used_keys.add(track_id)
            evidence.append(ESMCorrelationEvidence(
                track_id=track_id, source=source, bearing=bearing,
                bearing_uncertainty_deg=uncertainty, x=x, y=y,
                observed_at=observed_at))
        return correlate_observations(track, evidence, self.sim_t)

    def _emitter_profile(self, profile_key: str):
        systems = self.runtime_catalog.profile_systems.get(profile_key)
        if systems is None:
            return None
        return next((self.runtime_catalog.emitters[key]
                     for key in sorted(systems.emitter_keys)
                     if key in self.runtime_catalog.emitters
                     and self.runtime_catalog.emitters[key].domain == "radar"), None)

    @staticmethod
    def _asm_seeker_emitter(profile: dict) -> EmitterProfile:
        """Terminal active-radar seeker signature of an inbound ASM."""
        return EmitterProfile(
            key=profile["key"] + ".seeker", domain="radar",
            frequency_band_hz=tuple(profile["seeker_frequency_hz"]),
            prf_band_hz=tuple(profile["seeker_prf_hz"]),
            modulation_codes=(profile["seeker_modulation"],),
            radar_role="missile_seeker", operating_mode="terminal_search",
            power_class="medium", operating_period_s=.5, on_duration_s=.5)

    def _radar_signals(self, actor, profile_key: str, *, enabled=True,
                       synthetic=False, fire_control=False, terminal=False):
        systems = self.runtime_catalog.profile_systems.get(profile_key)
        if systems is None:
            return ()
        emitters = [self.runtime_catalog.emitters[key]
                    for key in systems.emitter_keys
                    if key in self.runtime_catalog.emitters]
        return RadarSuiteController(
            emitters, int(getattr(actor, "sensor_seed", 0)),
            synthetic_assumption=synthetic).active_signals(
                self.sim_t, actor.x, actor.y, enabled=enabled,
                fire_control=fire_control, terminal=terminal)

    def own_radar_signals(self):
        """Internal own-force emissions available to hostile ESM simulation."""
        profile_key = "warship_25"
        systems = self.runtime_catalog.profile_systems.get(profile_key)
        if systems is None or self.damage.station_down("opz"):
            return ()
        emitters = []
        for key in systems.emitter_keys:
            emitter = self.runtime_catalog.emitters[key]
            role = emitter.radar_role
            if ((role in ("navigation", "surface_search") and self.surface_radar_on)
                    or role == "air_search" and self.air_radar_on
                    or role == "multi_function"
                    and (self.surface_radar_on or self.air_radar_on)
                    or role == "fire_control" and self.selected_opz_track() is not None):
                emitters.append(emitter)
        return RadarSuiteController(emitters, self.seed + 0x52414441).active_signals(
            self.sim_t, self.ship.x, self.ship.y,
            fire_control=self.selected_opz_track() is not None)

    def _signal_measurements(self, actor, signals):
        seed = int(getattr(actor, "sensor_seed", 0))
        return scan_for_signals(
            signals, observer_x=self.ship.x, observer_y=self.ship.y,
            now=self.sim_t, maximum_range_nm=config.ESM_RANGE_NM,
            bearing_error_deg=config.ESM_BEARING_ERR_DEG,
            noise_for=lambda signal: self._smooth_sensor_noise(
                seed * 1009 + int(signal.signal_id[1:9], 16),
                self.sim_t, 5.0),
            line_of_sight=lambda signal: not self.world.land_blocks_line(
                self.ship.x, self.ship.y, signal.x, signal.y),
            level_noise_for=lambda signal: detrand.normal(
                self.seed, "esm-level", int(signal.signal_id[1:9], 16),
                math.floor(self.sim_t * 2.0 + 1e-6)))

    def _ecm_effect_against_asm(self, asm):
        if not asm.seeker_active(self.ship) or not self.ecm_jammer.channels:
            return None
        emitter = self._asm_seeker_emitter(asm.profile)
        signals = RadarSuiteController((emitter,), asm.sensor_seed).active_signals(
            self.sim_t, asm.x, asm.y, terminal=True)
        if not signals:
            return None
        blocked = self.world.land_blocks_line(
            self.ship.x, self.ship.y, asm.x, asm.y)
        return self.ecm_jammer.effect_details_on(
            signals[0], asm.distance_nm(self.ship), line_of_sight=not blocked,
            operational=not self.damage.station_down("opz"),
            burn_through_nm=asm.profile["jam_break_nm"])

    def _esm_measurement(self, actor, bearing: float, distance: float,
                         emitter, namespace: int) -> ESMMeasurement:
        import random

        seed = int(getattr(actor, "sensor_seed", 0)) + namespace
        rng = random.Random(seed * 65537 + 0x45534D)
        if emitter is None:
            frequency = rng.uniform(2e9, 12e9)
            prf = rng.uniform(200.0, 1500.0)
            modulation = "unknown"
        else:
            frequency = rng.uniform(*emitter.frequency_band_hz)
            prf = (rng.uniform(*emitter.prf_band_hz)
                   if emitter.prf_band_hz is not None else None)
            modulation = rng.choice(emitter.modulation_codes)
        uncertainty = config.ESM_BEARING_ERR_DEG / math.sqrt(3.0)
        noise = self._smooth_sensor_noise(seed * 1009, self.sim_t, 5.0)
        return ESMMeasurement(
            observer_x=self.ship.x,
            observer_y=self.ship.y,
            bearing=(bearing + noise * config.ESM_BEARING_ERR_DEG) % 360.0,
            bearing_uncertainty_deg=uncertainty,
            frequency_hz=frequency,
            prf_hz=prf,
            modulation_code=modulation,
            quality=config.clamp(.9 - .45 * distance / config.ESM_RANGE_NM,
                                 .35, .9),
            observed_at=self.sim_t,
        )

    def _update_esm_picture(self) -> None:
        """Publish passive intercepts independently from own-radar evidence."""
        if self.damage.station_down("opz"):
            self.esm_picture.expire(self.sim_t)
            self._update_ecm()
        else:
            def measurements():
                for sub in self.subs:
                    # Mast radar is possible only near periscope/snorkel depth
                    # and outside evasion/attack phases.
                    enabled = (not sub.sunk and sub.depth <= 20.0
                               and sub.state == "PATROLLE")
                    signals = self._radar_signals(
                        sub, sub.stype.key, enabled=enabled)
                    yield from self._signal_measurements(sub, signals)
                for actor in self.civilians + self.warships:
                    if actor.sunk or not actor.emitter:
                        continue
                    signals = self._radar_signals(
                        actor, actor.signature_key, enabled=actor.radar_emitting,
                        synthetic=actor.live_mmsi is not None,
                        fire_control=actor in self.warships
                        and bool(actor.pending_asm))
                    yield from self._signal_measurements(actor, signals)
                for flight in self.flights.flights:
                    signals = self._radar_signals(
                        flight, flight.akey,
                        enabled=flight.radar_emitting or flight.kind == "civil",
                        synthetic=flight.kind == "civil",
                        fire_control=flight.akey == "su_25")
                    yield from self._signal_measurements(flight, signals)
                for live in sorted(self.live_traffic.aircraft.values(),
                                   key=lambda item: item.seq):
                    profile_key = self.runtime_catalog.runtime_bindings[
                        "civil_flight"]
                    signals = self._radar_signals(
                        live, profile_key, enabled=True, synthetic=True)
                    yield from self._signal_measurements(live, signals)
                for raider in sorted(self.raiders, key=lambda item: item.seq):
                    signals = self._radar_signals(
                        raider, "su_25", enabled=not raider.despawned,
                        fire_control=raider.fc_radar_on)
                    yield from self._signal_measurements(raider, signals)
                for asm in self.asms:
                    emitter = self._asm_seeker_emitter(asm.profile)
                    signals = RadarSuiteController(
                        (emitter,), asm.sensor_seed).active_signals(
                            self.sim_t, asm.x, asm.y,
                            terminal=asm.seeker_active(self.ship))
                    yield from self._signal_measurements(asm, signals)

            protected = set(self.eloka_annotations)
            protected.update(channel.track_key for channel in self.ecm_jammer.channels)
            previous_operational = {
                track.track_key for track in self.eloka_tracks()
                if filter_and_sort_tracks(
                    (track,), self.sim_t, self.eloka_analysis,
                    annotated_keys=self.eloka_annotations,
                    jamming_keys=protected)}
            self.esm_picture.observe_batch(
                measurements(), self.sim_t, protected_keys=protected)
            self._update_ecm()
            operational = {track.track_key for track in filter_and_sort_tracks(
                self.eloka_tracks(), self.sim_t, self.eloka_analysis,
                annotated_keys=self.eloka_annotations,
                jamming_keys=(channel.track_key
                              for channel in self.ecm_jammer.channels))}
            if operational - previous_operational:
                self._emit_sound("esm_contact")
            self._publish_released_esm()
        self._reconcile_eloka_selection()

    def hfdf_bearings(self) -> list:
        """Current and recently retained HFDF observations."""
        return self.radio_picture.tracks(self.sim_t, ("HF",))

    def hfdf_display_id(self, report) -> str:
        """Return the stable public identifier for an HFDF observation."""
        track_id = report if isinstance(report, str) else report.track_id
        return "H-" + self._observation_key("hfdf-display", track_id)[-6:]

    def _update_radio_picture(self) -> None:
        """Measure transmitting emitters without publishing their positions."""
        if self.damage.station_down("radio"):
            self.radio_picture.expire(self.sim_t)
            return
        night = self.world.is_night()
        for sub in self.subs:
            if not sub.transmitting:
                continue
            dist = sub.distance_nm(self.ship)
            seed = getattr(sub, "sensor_seed", sub.id)
            # One call keeps its frequency; a new 5-minute schedule window
            # may pick another one for the path to the shore station.
            frequency = hf_physics.transmit_frequency_mhz(
                seed, math.floor(self.sim_t / 300.0), night)
            mode = hf_physics.propagation_mode(
                dist, frequency, night, config.HFDF_RANGE_NM)
            if mode is None:
                continue
            if (mode == "GROUND" and self.world.land_blocks_line(
                    self.ship.x, self.ship.y, sub.x, sub.y)):
                continue
            error = config.HFDF_BEARING_ERR_DEG * (
                hf_physics.SKY_WAVE_BEARING_FACTOR if mode == "SKY" else 1.0)
            noise = self._smooth_sensor_noise(seed * 777, self.sim_t, 10.0)
            brg = (sub.bearing_from_frigate(self.ship) + noise * error) % 360.0
            self.radio_picture.observe(track_id=f"H-{sub.id}", kind="HF",
                target_id=sub.id, source="HFDF", bearing=brg, range_nm=None,
                observer_x=self.ship.x, observer_y=self.ship.y, course=None,
                quality=.55 if mode == "GROUND" else .4, now=self.sim_t,
                label=f"SIG-{sub.id:02d}",
                bearing_uncertainty_deg=error / math.sqrt(3.0),
                frequency_hz=round(frequency * 1e6, -2), propagation=mode)
        self.radio_picture.expire(self.sim_t)

    def _cycle_hfdf(self, delta: int) -> None:
        reports = self.hfdf_bearings()
        self.radio_sel = 0 if not reports else (self.radio_sel + delta) % len(reports)

    @staticmethod
    def _bearing_intersection(first: dict, second: dict):
        """Intersect two nautical bearing rays; return None for weak geometry."""
        b1, b2 = math.radians(first["bearing"]), math.radians(second["bearing"])
        r = (math.sin(b1), -math.cos(b1))
        s = (math.sin(b2), -math.cos(b2))
        denom = r[0] * s[1] - r[1] * s[0]
        if abs(denom) < math.sin(math.radians(12.0)):
            return None
        qx, qy = second["observer_x"] - first["observer_x"], \
            second["observer_y"] - first["observer_y"]
        along_first = (qx * s[1] - qy * s[0]) / denom
        along_second = (qx * r[1] - qy * r[0]) / denom
        if along_first < 0.0 or along_second < 0.0:
            return None
        return (first["observer_x"] + along_first * r[0],
                first["observer_y"] + along_first * r[1], abs(denom))

    def capture_hfdf(self) -> None:
        reports = self.hfdf_bearings()
        if not reports:
            self.flash(message("runtime.hfdf.none"))
            return
        report = reports[min(self.radio_sel, len(reports) - 1)]
        self.capture_hfdf_report(report)

    def capture_hfdf_report(self, report):
        if self.damage.station_down("radio"):
            return "radio_down"
        if not any(item is report for item in self.hfdf_bearings()):
            return "stale_ref"
        if report.age(self.sim_t) > config.RADAR_TRACK_STALE_S:
            self.flash(message("runtime.hfdf.stale"))
            return "stale_ref"
        measurement = (report.measurement_history[-1]
                       if report.measurement_history else {})
        display_id = self.hfdf_display_id(report)
        row = dict(track_id=report.track_id, label=display_id,
                   bearing=measurement.get("bearing", report.bearing),
                   observer_x=measurement.get("observer_x", self.ship.x),
                   observer_y=measurement.get("observer_y", self.ship.y),
                   t=measurement.get("t", report.last_seen))
        self.hfdf_log.append(row)
        self.hfdf_log = self.hfdf_log[-20:]
        previous = next((item for item in reversed(self.hfdf_log[:-1])
                          if item["track_id"] == report.track_id
                          and 0 < row["t"] - item["t"] <= 300.0
                         and math.hypot(item["observer_x"] - row["observer_x"],
                                        item["observer_y"] - row["observer_y"]) >= 1.0), None)
        if previous is None:
            self.announce(message("runtime.hfdf.logged", label=display_id,
                                  bearing=f"{report.bearing:05.1f}"), "funk")
            return True
        fix = self._bearing_intersection(previous, row)
        if fix is None:
            self.announce(message("runtime.hfdf.geometry"), "funk")
            return True
        x, y, geometry = fix
        # Angular errors projected at the two measurement origins. This assumes
        # a stationary emitter throughout the bounded observation span.
        b1, b2 = math.radians(previous["bearing"]), math.radians(row["bearing"])
        # Sky-wave intercepts carry the larger ionospheric-tilt uncertainty.
        sigma_rad = math.radians(report.bearing_uncertainty_deg
                                 or config.HFDF_BEARING_ERR_DEG / math.sqrt(3.0))
        v1 = sigma_rad ** 2 * ((x - previous["observer_x"]) ** 2
                              + (y - previous["observer_y"]) ** 2)
        v2 = sigma_rad ** 2 * ((x - row["observer_x"]) ** 2
                              + (y - row["observer_y"]) ** 2)
        xx = (math.sin(b2) ** 2 * v1 + math.sin(b1) ** 2 * v2) / geometry ** 2
        yy = (math.cos(b2) ** 2 * v1 + math.cos(b1) ** 2 * v2) / geometry ** 2
        xy = -(math.sin(b2) * math.cos(b2) * v1
               + math.sin(b1) * math.cos(b1) * v2) / geometry ** 2
        self.hfdf_fixes[report.track_id] = dict(
            label=display_id, x=x, y=y,
            sigma_nm=math.sqrt(max(0.0, (xx + yy + math.hypot(xx - yy, 2 * xy)) / 2)),
            covariance_nm2=(xx, xy, yy),
            t=row["t"])
        dist = math.hypot(x - row["observer_x"], y - row["observer_y"])
        bearing = math.degrees(math.atan2(
            x - row["observer_x"], -(y - row["observer_y"]))) % 360.0
        self.air_picture.observe(
            track_id=f"H-{report.target_id}", kind="UNKNOWN",
            target_id=report.target_id, source="HFDF-FIX", bearing=bearing,
            range_nm=dist, observer_x=row["observer_x"],
            observer_y=row["observer_y"],
            course=None, quality=max(.25, geometry), now=row["t"],
            label=display_id)
        self.flash(message("runtime.hfdf.fix", label=display_id), 3.0)
        self.feed.add(self.world.format_time(), "funk",
                      message("runtime.hfdf.feed", label=display_id))
        return True

    def _drain_warship_asm(self) -> None:
        """Kampfschiff-Salven aus pending_asm werden zu ASM-Objekten."""
        for w in self.warships:
            if w.sunk:
                continue
            pending, w.pending_asm = w.pending_asm, []
            for x, y, n in pending:
                for i in range(n):
                    course = (math.degrees(math.atan2(w.sensor_contact[0] - x,
                                                      -(w.sensor_contact[1] - y))) % 360.0
                              if w.sensor_contact is not None else w.course)
                    self.warship_asm_seq += 1
                    # Ship-launched: booster from the launcher's speed; the
                    # launcher's sensor contact is the inertial datum.
                    self.asms.append(ASM(
                        x, y, course, self._next_asm_sequence(), self.rng_asm,
                        self._air_defense_loadout["asm"],
                        launch_speed_kn=w.speed, altitude_m=10.0,
                        datum=w.sensor_contact))

    def _next_asm_sequence(self) -> int:
        self.asm_seq += 1
        return self.asm_seq

    def _maybe_spawn_asm(self) -> None:
        """M16: ASM-Wellen laut Missionsplan (zeitgesteuert, deterministisch)."""
        m = self.mission
        if self.asm_spawned >= m.asm_count:
            return
        need = (config.ASM_SPAWN_FIRST_S
                + self.asm_spawned * self.mission.asm_interval_s)
        if self.mission_time < need:
            return
        self.asm_spawned += 1
        d = self.rng_asm.uniform(*config.ASM_SPAWN_DIST_NM)
        ang = self.rng_asm.uniform(0.0, 360.0)
        x = config.clamp(self.ship.x + d * math.cos(math.radians(ang)),
                         0.0, self.world.size_nm)
        y = config.clamp(self.ship.y + d * math.sin(math.radians(ang)),
                         0.0, self.world.size_nm)
        course = math.degrees(math.atan2(self.ship.x - x, -(self.ship.y - y))) % 360.0
        # A wave appears already in cruise flight, aimed by its (unseen)
        # launcher at the ship's position at that moment.
        self.asms.append(ASM(x, y, course, self._next_asm_sequence(), self.rng_asm,
                              self._air_defense_loadout["asm"],
                              datum=(self.ship.x, self.ship.y)))

    # --- R20: Luftangriff (feindliche Angriffsflugzeug-Wellen) ---

    def _spawn_raid_wave(self, profile: dict) -> None:
        """Eine Welle Angriffsflugzeuge außerhalb der Radarreichweite spawnen."""
        size = self.rng_raid.randint(*config.RAID_WAVE_SIZE)
        for _ in range(size):
            d = self.rng_raid.uniform(*config.RAID_SPAWN_DIST_NM)
            ang = self.rng_raid.uniform(0.0, 360.0)
            x = config.clamp(self.ship.x + d * math.cos(math.radians(ang)),
                             0.0, self.world.size_nm)
            y = config.clamp(self.ship.y + d * math.sin(math.radians(ang)),
                             0.0, self.world.size_nm)
            course = (math.degrees(math.atan2(self.ship.x - x,
                                              -(self.ship.y - y))) % 360.0)
            self.raid_seq += 1
            self.raiders.append(Raider(x, y, course, self.raid_seq,
                                       self.rng_raid, profile))
        self.raid_waves_spawned += 1

    def _update_raiders(self, dt: float, publish_picture: bool = True) -> None:
        """R20: Raid-Wellen, Bewegung/Phasen, Salven-Ablöse und Flak-Einsatz."""
        profiles = self._air_defense_loadout
        if (self.mission.asm_count > 0
                and len(self.raiders) < config.RAID_MAX_CONCURRENT
                and self.mission_time >= config.RAID_FIRST_WAVE_S
                + self.raid_waves_spawned * self.mission.raid_interval_s):
            self._spawn_raid_wave(profiles["raider"])
        for raider in self.raiders:
            raider.update(dt, self.ship, world=self.world)
        self.aa_cooldown_s = max(0.0, self.aa_cooldown_s - dt)
        aa = profiles["aa_gun"]
        observed = {}
        # Live-Flugzeuge tragen absichtlich dasselbe "A-<seq>"-Format wie
        # simulierte Fluege (siehe FlightManager.next_seq) - der exakte,
        # eindeutige Seq-Wert je LiveAircraft macht die Zuordnung trotzdem
        # kollisionsfrei, ohne dass ein eigenes, erkennbares Praefix noetig
        # waere.
        observed_a_tracks = {}
        for track in self.air_picture.tracks(self.sim_t, ("FLG", "ASM")):
            if track.track_id.startswith("R-"):
                observed[track.track_id] = track
            elif track.track_id.startswith("A-"):
                observed_a_tracks[track.track_id] = track
        for raider in self.raiders:
            if raider.hp <= 0:
                continue
            track = observed.get(f"R-{raider.seq}")
            if (self.flak_authorized
                    and track is not None and track.x is not None and track.y is not None
                    and track.position_seen is not None
                    and self.sim_t - track.position_seen
                    <= aa["observation_max_age_s"]
                    and track.range_nm is not None
                    and track.range_nm <= aa["range_nm"]
                    and self.aa_ammo >= aa["rounds_per_attempt"]
                    and self.aa_cooldown_s <= 0.0
                    and not self.damage.station_down("weapons")
                    and not self.world.land_blocks_line(
                        self.ship.x, self.ship.y, track.x, track.y)):
                self.aa_ammo -= aa["rounds_per_attempt"]
                self.aa_cooldown_s = aa["cycle_s"]
                self._emit_sound("gunfire")
                # Pk composes base accuracy with evasion and a range falloff:
                # closer raiders are easier hard-kill targets for the AA gun.
                distance_factor = 1.0 - 0.5 * config.clamp(
                    track.range_nm / max(0.01, aa["range_nm"]), 0.0, 1.0)
                if (self.rng_raid.random()
                        < aa["hit_probability"] * (1.0 - raider.evasion) * distance_factor):
                    raider.hp -= 1
                    if raider.hp <= 0:
                        raider.despawned = True
                        self.audio.play_alert("defense")
                        self.flash(message("runtime.raid.downed"), 3.0)
                        self.feed.add(self.world.format_time(), "waffen",
                                      message("runtime.raid.downed"))
        self.raiders = [r for r in self.raiders if not r.despawned]
        # Echter ADS-B-Verkehr ist nie automatisch feindlich: die Flak darf
        # ihn nur treffen, wenn der Spieler den konkreten OPZ-Track manuell
        # als HOSTILE eingestuft hat (dieselbe IFF-Klassifizierung wie fuer
        # jeden anderen Radar-/Sonar-Kontakt). Ohne diese bewusste
        # Fehleinschaetzung bleibt Realverkehr fuer die Waffen unantastbar,
        # daher gilt hier - anders als vorher - die reale Geschuetzreichweite.
        for live in list(self.live_traffic.aircraft.values()):
            if live.despawned:
                continue
            track_id = f"A-{live.seq}"
            if self.opz_affiliation(track_id) != "HOSTILE":
                continue
            if live.icao24 not in self.live_engage_authorized:
                continue
            track = observed_a_tracks.get(track_id)
            if (self.flak_authorized
                    and track is not None and track.x is not None and track.y is not None
                    and track.position_seen is not None
                    and self.sim_t - track.position_seen
                    <= aa["observation_max_age_s"]
                    and track.range_nm is not None
                    and track.range_nm <= aa["range_nm"]
                    and self.aa_ammo >= aa["rounds_per_attempt"]
                    and self.aa_cooldown_s <= 0.0
                    and not self.damage.station_down("weapons")
                    and not self.world.land_blocks_line(
                        self.ship.x, self.ship.y, track.x, track.y)):
                self.aa_ammo -= aa["rounds_per_attempt"]
                self.aa_cooldown_s = aa["cycle_s"]
                self._emit_sound("gunfire")
                distance_factor = 1.0 - 0.5 * config.clamp(
                    track.range_nm / max(0.01, aa["range_nm"]), 0.0, 1.0)
                if self.rng_raid.random() < aa["hit_probability"] * distance_factor:
                    live.hit()
                    if live.despawned:
                        self.live_traffic.mark_aircraft_destroyed(live.icao24)
                        self.incident = True
                        self.audio.play_alert("danger")
                        self.flash(message("runtime.live_air.downed"), 4.0)
                        self.feed.add(self.world.format_time(), "waffen",
                                      message("runtime.live_air.downed"))
        if publish_picture:
            # No "raid incoming" call: radar cannot tell an attack aircraft
            # from other air traffic. Threat alerts come from the measured
            # ASM cue (speed/altitude/jamming) and operator annotations.
            self._raider_visible_last = bool(observed)

    def _drain_raider_asm(self) -> None:
        """R20: Raid-Salven werden zu ASM-Objekten gegen die Fregatte."""
        for raider in self.raiders:
            pending, raider.pending_asm = raider.pending_asm, 0
            for _ in range(pending):
                course = raider.course_to_frigate(self.ship)
                # Air-launched at the raider's speed and pop-up height; its
                # fire-control radar supplied the datum.
                self.asms.append(ASM(
                    raider.x, raider.y, course, self._next_asm_sequence(),
                    self.rng_asm, self._air_defense_loadout["asm"],
                    launch_speed_kn=raider.speed_kn, altitude_m=raider.altitude_m,
                    datum=(self.ship.x, self.ship.y)))

    # --- Waffenzentrale ---

    def set_target(self) -> None:
        contacts = [c for c in self.sonar.active_contacts()
                    if self.sim_t - c.last_seen < config.SONAR_CONTACT_LOST_S]
        if not contacts:
            self.target = None
            self.flash(message("runtime.contacts.none"))
            return
        if self.selected_contact in contacts:
            best = self.selected_contact
        else:
            best = max(contacts, key=lambda c: c.confidence)
        if self.designate_sonar_target(best) is not True:
            return
        self.flash(message("runtime.target.set", contact=best.id), 2.0)

    def torpedo_readiness(self) -> tuple[str, tuple]:
        """Return an operator-readable fire-control state and color."""
        if (self.target is None
                or self.sim_t - self.target.last_seen >= config.SONAR_CONTACT_LOST_S):
            return "BLOCKIERT: KEIN ZIEL", config.COLOR_WARN
        blocked = self._target_affiliation_interlock()
        if blocked is not None:
            return (f"BLOCKIERT: ZUGEHOERIGKEIT {blocked}",
                    config.COLOR_DANGER)
        if not self._contact_range_fresh(self.target) and self.roe == "STD":
            return "BLOCKIERT: KEINE ENTFERNUNG", config.COLOR_WARN
        if self.weapon_classification(self.target) not in ("U_BOOT", "KAMPFSCHIFF"):
            return ("BLOCKIERT: NICHT ALS U-BOOT/KAMPFSCHIFF KLASSIFIZIERT",
                    config.COLOR_WARN)
        if self.torpedo_count <= 0:
            return "BLOCKIERT: KEINE TORPEDOS", config.COLOR_DANGER
        if self.player_torpedo_battery.ready_count <= 0:
            return "BLOCKIERT: KEIN ROHR BEREIT", config.COLOR_WARN
        if len([t for t in self.torpedoes if t.state == "RUN"]) >= \
                config.TORP_MAX_IN_AIR[config.TORP_DOCTRINE]:
            return "BLOCKIERT: SALVENLIMIT", config.COLOR_WARN
        if self.damage.station_down("weapons") or \
                self.damage.station_degraded("weapons"):
            return "BLOCKIERT: WAFFENZENTRALE GESTOERT", config.COLOR_DANGER
        return "FEUER FREI", config.COLOR_OK

    def _contact_affiliations(self, contact) -> list:
        """Return every OPZ affiliation annotation bound to a sonar target."""
        if contact is None:
            return []
        # Operator annotations outlive measurements. Aircraft/missile sequence
        # IDs are a separate namespace and must not annotate a sonar target.
        affiliations = [self.opz_affiliations.get(
            f"{prefix}-{contact.target_id}", "UNKNOWN")
            for prefix in ("U", "S")]
        self.opz_source_observations()
        affiliations.extend(
            self.opz_affiliation(observation_id)
            for observation_id, source in self._opz_source_bindings.items()
            if (source is contact or getattr(source, "target_id", None)
                == contact.target_id and str(
                    getattr(source, "track_id", "")).split("-", 1)[0]
                in ("U", "S")))
        # An affiliation set on an OPZ fusion covers every sonar report in it.
        affiliations.extend(
            self.opz_fusion.fusion_affiliations[fusion.fusion_id]
            for fusion in self._contact_fusions(contact)
            if fusion.fusion_id in self.opz_fusion.fusion_affiliations)
        return affiliations

    def _contact_fusions(self, contact) -> list:
        """Intact OPZ fusions holding a report bound to this sonar contact.

        Read-only: a fusion counts only while all its member reports are
        current (the condition ``OPZFusion.prune`` applies), so the result
        never depends on whether a frame pruned the register first.
        """
        if contact is None or not self.opz_fusion.fusions:
            return []
        current = {item.observation_id for item in self.opz_source_observations()}
        bindings = self._opz_source_bindings
        return [fusion for _, fusion in sorted(self.opz_fusion.fusions.items())
                if set(fusion.members) <= current
                and any(bindings.get(member) is contact
                        for member in fusion.members)]

    def weapon_classification(self, contact) -> str | None:
        """Operator class that fire control uses for one sonar contact.

        The sonar contact's own class wins; otherwise the class the OPZ gave a
        fusion holding this contact's report applies.
        """
        if contact is None:
            return None
        if contact.player_class in config.PLAYER_CLASSES:
            return contact.player_class
        return next((self.opz_fusion.classifications[fusion.fusion_id]
                     for fusion in self._contact_fusions(contact)
                     if self.opz_fusion.classifications.get(fusion.fusion_id)
                     in config.PLAYER_CLASSES), None)

    def contact_affiliation(self, contact) -> str:
        """Resolve one affiliation for a contact, FRIEND/NEUTRAL taking
        precedence over HOSTILE so callers stay conservative by default."""
        affiliations = self._contact_affiliations(contact)
        return next((value for value in ("FRIEND", "NEUTRAL", "HOSTILE")
                     if value in affiliations), "UNKNOWN")

    def _target_affiliation_interlock(self, contact=None):
        """Return a protected OPZ affiliation for the assigned sonar target."""
        contact = self.target if contact is None else contact
        if contact is None:
            return None
        affiliations = self._contact_affiliations(contact)
        return next((value for value in ("FRIEND", "NEUTRAL")
                     if value in affiliations), None)

    def _contact_range_fresh(self, contact) -> bool:
        if contact is None or contact.range_est is None:
            return False
        observed_at = (contact.range_seen if contact.range_seen is not None
                       else contact.last_seen)
        return self.sim_t - observed_at <= config.SONAR_CONTACT_LOST_S

    # --- M9: Kontakt-Auswahl & manuelle Klassifizierung ---

    def _cycle_selected_contact(self, delta: int) -> None:
        cs = sorted((c for c in self.sonar.contacts.values()
                     if self.sim_t - c.last_seen < config.SONAR_CONTACT_LOST_S),
                    key=lambda c: c.id)
        if not cs:
            self.selected_contact = None
            return
        try:
            i = cs.index(self.selected_contact)
        except ValueError:
            i = -1
        self.selected_contact = cs[(i + delta) % len(cs)]
        if self.sonar.focus_locked:
            self.sonar.reset_listening_history()

    def _cycle_helo_contact(self, delta: int) -> None:
        """W2: browse only what the helicopter's own dip has plotted - its
        own active/passive picture, independent of the ship's sonar picture -
        so the operator can select one and release it to CIC from here."""
        cs = sorted((c for c in self.sonar.contacts.values()
                     if (c.dip_last_seen is not None
                         and 0 <= self.sim_t - c.dip_last_seen
                         < config.SONAR_CONTACT_LOST_S)
                     or any(fix["source"] == "DIPPING"
                            for fix in c.active_fixes(self.sim_t))
                     or any(0 <= self.sim_t - row["measured_at"]
                            < config.SONAR_CONTACT_LOST_S
                            for row in c.buoy_reports.values())),
                    key=lambda c: c.id)
        if not cs:
            self.selected_contact = None
            self.flash(message("runtime.contact.none_selected"))
            return
        try:
            i = cs.index(self.selected_contact)
        except ValueError:
            i = -1
        self.selected_contact = cs[(i + delta) % len(cs)]

    def _cycle_classification(self) -> None:
        if self.selected_contact is None:
            self.flash(message("runtime.contact.none_selected"))
            return
        if self.selected_contact.target_id not in self.sonar.contacts:
            self.selected_contact = None
            return
        c = self.selected_contact
        order = [None] + list(config.PLAYER_CLASSES)
        value = order[(order.index(c.player_class) + 1) % len(order)]
        if self.classify_sonar_contact(c, value) is not True:
            return
        self.flash(message("runtime.contact.classified", contact=c.id,
                           classification=display_value("classification",
                                                        c.player_class, self.tr)), 2.0)

    def _toggle_sonar_release(self) -> None:
        contact = self.selected_contact
        if contact is None:
            self.flash(message("runtime.contact.none_selected"))
            return
        helicopter = self.station is Station.HELICOPTER
        buoy = helicopter and self.helo_sensor_source == "BUOY"
        released = not (contact.buoy_released_to_opz if buoy else
                        contact.dip_released_to_opz if helicopter
                        else contact.released_to_opz)
        if self.release_sonar_contact(contact, released,
                                      source="buoy" if buoy else
                                      "helicopter" if helicopter else "sonar") is not True:
            return
        self.flash(message("runtime.sonar.release" if released
                           else "runtime.sonar.withdraw",
                           contact=contact.id), 2.0)

    def _find_target(self, target_id: int):
        for s in self.subs:
            if s.id == target_id:
                return s
        for a in self.animals:
            if a.id == target_id:
                return a
        for d in self.decoys:
            if d.id == target_id:
                return d
        for civilian in self.civilians:
            if civilian.id == target_id:
                return civilian
        for w in self.warships:
            if w.id == target_id:
                return w
        for t in self.enemy_torpedoes:
            if t.id == target_id:
                return t
        return None

    def launch_torpedo(self) -> None:
        if (self.target is None
                or self.sim_t - self.target.last_seen >= config.SONAR_CONTACT_LOST_S):
            self.target = None
            self.flash(message("runtime.target.invalid"))
            return
        self.launch_torpedo_at(self.target, self.torpedo_depth)

    def launch_torpedo_at(self, contact, depth_m: float):
        """Launch from ownship against one explicit sonar observation."""
        if (contact is None or type(depth_m) not in (int, float)
                or not math.isfinite(depth_m) or not 10 <= depth_m <= 300
                or self.sim_t - contact.last_seen >= config.SONAR_CONTACT_LOST_S):
            self.flash(message("runtime.target.invalid"))
            return "invalid_target"
        blocked = self._target_affiliation_interlock(contact)
        if blocked is not None:
            self.flash(message("runtime.roe.blocked",
                               affiliation=display_value("affiliation", blocked, self.tr)))
            return "roe_blocked"
        if self.roe == "STD":
            if not self._contact_range_fresh(contact):
                self.flash(message("runtime.target.not_located"))
                return "not_located"
            if self.weapon_classification(contact) not in ("U_BOOT", "KAMPFSCHIFF"):
                self.flash(message("runtime.target.not_classified"))
                return "not_classified"
        else:
            if self.weapon_classification(contact) not in ("U_BOOT", "KAMPFSCHIFF"):
                self.flash(message("runtime.target.not_classified"))
                return "not_classified"
        active_torpedoes = len([t for t in self.torpedoes if t.state == "RUN"])
        salvo_limit = config.TORP_MAX_IN_AIR[config.TORP_DOCTRINE]
        if active_torpedoes >= salvo_limit:
            self.flash(message("runtime.salvo.limit", limit=salvo_limit))
            return "salvo_limit"
        if self.torpedo_count <= 0:
            self.flash(message("event.no_torpedoes"))
            return "empty"
        if self.player_torpedo_battery.ready_count <= 0:
            self.flash(message("runtime.torpedo.no_tube"))
            return "no_tube"
        if self.damage.station_down("weapons"):
            self.flash(message("runtime.weapons.down"))
            return "weapons_down"
        if self.damage.station_degraded("weapons"):
            self.flash(message("runtime.weapons.degraded"))
            return "weapons_degraded"
        tgt = self._find_target(contact.target_id)
        if (contact.observed_x is not None
                and contact.observed_y is not None
                and self._contact_range_fresh(contact)):
            est_x, est_y = contact.observed_x, contact.observed_y
        else:
            range_nm = (contact.range_est if contact.range_est is not None
                        else config.ROE_FREE_LAUNCH_RANGE_NM)
            est_x = self.ship.x + range_nm * math.sin(math.radians(contact.bearing))
            est_y = self.ship.y - range_nm * math.cos(math.radians(contact.bearing))
        course = math.degrees(math.atan2(est_x - self.ship.x,
                                         -(est_y - self.ship.y))) % 360.0
        weapon_key = self.player_torpedo_battery.fire()
        if weapon_key is None:
            self.flash(message("runtime.torpedo.no_tube"))
            return "no_tube"
        self.torpedo_seq += 1
        weapon_definition = next(
            item
            for item in self._ownship_loadout["weapons"]
            if item["key"] == weapon_key)
        profile_key = weapon_definition["runtime_profile_key"]
        profile = self.runtime_catalog.torpedoes[profile_key]
        self.torpedoes.append(Torpedo(self.ship.x, self.ship.y, course,
                                      depth_m, tgt, self.torpedo_seq,
                                      kill_dist_nm=self.difficulty["kill_dist_nm"],
                                      kill_depth_m=self.difficulty["kill_depth_m"],
                                      guidance_x=est_x, guidance_y=est_y,
                                      profile=profile, time_since_launch=0.0))
        self.torpedo_count = self.player_torpedo_battery.remaining_total
        # W2: the launch transient itself is a loud, one-time acoustic event,
        # audible passively much farther than a torpedo's own terminal seeker
        # ever gets (TORP_HOME_RANGE_NM) - distinct concept, separate gate.
        for sub in self.subs:
            if (not sub.sunk and sub.state != "SINKING"
                    and math.hypot(self.ship.x - sub.x, self.ship.y - sub.y)
                    <= config.SUB_TORPEDO_ALERT_NM
                    and not self.world.sonar_path_blocked(
                        self.ship.x, self.ship.y, 5.0,
                        sub.x, sub.y, sub.depth)):
                sub.alert_torpedo(source=(self.ship.x, self.ship.y))
        for warship in self.warships:
            if (not warship.sunk and warship.doctrine == "surface_combatant"
                    and math.hypot(self.ship.x - warship.x, self.ship.y - warship.y)
                    <= config.SUB_TORPEDO_ALERT_NM
                    and not self.world.sonar_path_blocked(
                        self.ship.x, self.ship.y, 5.0,
                        warship.x, warship.y, warship.depth)):
                bearing = math.degrees(math.atan2(
                    self.ship.x - warship.x,
                    -(self.ship.y - warship.y))) % 360.0
                warship.alert_torpedo(bearing)
                if (warship.countermeasures_left > 0 and warship.side == "hostile"
                        and len(self.decoys) < MAX_DECOYS):
                    # Stream an acoustic decoy while turning away.
                    warship.countermeasures_left -= 1
                    decoy_profile = self.runtime_catalog.decoys[
                        self.runtime_catalog.runtime_bindings["submarine_decoy"]]
                    self.decoys.append(Decoy(
                        warship.x, warship.y, 10.0, self.rng_asw, decoy_profile,
                        self.runtime_catalog.acoustic_for(decoy_profile.key),
                        source_id=warship.id))
        self._emit_sound("torpedo_launch")
        self.flash(message("runtime.torpedo.launched", torpedo=self.torpedo_seq), 2.0)
        self.feed.add(self.world.format_time(), "waffen",
                      message("runtime.torpedo.feed", torpedo=self.torpedo_seq,
                              contact=contact.id))
        return True

    # --- Update ---

    def _sonar_range_factor(self) -> float:
        """Continuous sonar-room capability: an undamaged room keeps full
        range, a degraded one falls to DMG_SONAR_DEGRADED_FACTOR and below."""
        if self.damage.station_degraded("sonar"):
            return config.DMG_SONAR_DEGRADED_FACTOR * (
                0.5 + 0.5 * self.damage.capability("sonar"))
        return 1.0

    def _sonar_targets(self) -> list:
        """Akustisch auffassbare Ziele: Boote, Tiere, Dekoys, Zivilverkehr,
        feindliche Schiffe und laufende Feindtorpedos."""
        return ([s for s in self.subs if not s.sunk]
                + [a for a in self.animals if not a.dead]
                + [d for d in self.decoys if not d.dead]
                + [c for c in self.civilians if not c.sunk]
                + [w for w in self.warships if not w.sunk]
                + [t for t in self.enemy_torpedoes if t.state == "RUN"])

    def _drain_enemy_torpedoes(self) -> None:
        for sub in self.subs:
            while (sub.pending_torpedoes
                   and len(self.enemy_torpedoes) < MAX_ENEMY_TORPEDOES):
                row = sub.pending_torpedoes.pop(0)
                x, y, course, depth = row[:4]
                guidance = row[4:6] if len(row) >= 6 else (None, None)
                profile_key, launch_platform_id, launch_weapon_key = row[6:9]
                self.enemy_torpedoes.append(
                    EnemyTorpedo(x, y, course, depth,
                                 len(self.enemy_torpedoes) + 1,
                                 profile=self.runtime_catalog.torpedoes[profile_key],
                                 guidance_x=guidance[0], guidance_y=guidance[1],
                                 launch_platform_id=launch_platform_id,
                                 launch_weapon_key=launch_weapon_key,
                                 time_since_launch=0.0))

    def update(self, dt: float, audio_dt: float | None = None) -> None:
        with layout.bottom_panel_regions(self.bottom_panel_mode()):
            self._update(dt, audio_dt)

    def _update(self, dt: float, audio_dt: float | None = None) -> None:
        """Advance simulation in real time with bounded physics substeps."""
        wall_dt = audio_dt if audio_dt is not None else dt
        self.audio.debug_log(wall_dt, receiver=getattr(self.sonar, "receiver", None))
        if self.splash_active:
            splash_elapsed = self._t - self.splash_started_at
            ping_cycle = int(max(0.0, splash_elapsed) / SPLASH_PING_PERIOD_S)
            if ping_cycle != self._splash_ping_cycle:
                self._splash_ping_cycle = ping_cycle
                self.audio.play_ping()
            self._frame_clock_reset = True
            return
        # The game always runs in real time: overlays, menus opened over a
        # mission and focus loss never stop it. Only no mission (menu) or a
        # finished one has nothing to simulate.
        if not self.running or self.in_menu or self.main_menu or self.game_over:
            # Nothing is caught up after the menu or game over.
            self._frame_clock_reset = True
            self.audio.stop()
            self._sonar_audio_sequence = -1
            return
        playing_boat = self.local_side == "uboot"
        self.audio.local_effects = not playing_boat
        if playing_boat and self._opfor is None:
            self.claim_opfor_sub()
        # Operator adjustments follow wall time; hull and weapon motion do not.
        turn, _ = (0.0, 0.0) if playing_boat else self.steering_input()
        if not playing_boat and not self.damage.station_down("bridge"):
            self.ship.steer_input(dt, turn, 0)
        if self.station is Station.WEAPONS and not playing_boat:
            depth_dir = int(pygame.K_UP in self.held) - int(pygame.K_DOWN in self.held)
            self.torpedo_depth = config.clamp(
                self.torpedo_depth + depth_dir * 20.0 * dt, 10.0, 300.0)
        sim_dt = dt
        n = max(1, int(math.ceil(sim_dt / config.PHYS_SUBSTEP_S)))
        n = min(n, config.PHYS_SUBSTEP_MAX)
        step = sim_dt / n
        sim_started = time.perf_counter() if self._perf_debug_enabled else None
        for _ in range(n):
            self._update_sim(step)
            if self.game_over:
                break
        if sim_started is not None:
            self._perf_sim_s += time.perf_counter() - sim_started
            self._perf_substeps += n
        self.map_view.set_rect(config.MAP_RECT)
        if self.map_follow:
            self.map_view.cx, self.map_view.cy = self.ship.x, self.ship.y
            self.map_view.clamp_center()
        self._configure_opz_map_view()
        if self.opz_map_follow:
            self.opz_map_view.cx, self.opz_map_view.cy = self.ship.x, self.ship.y
            self.opz_map_view.clamp_center()
        if not self.game_over:
            audio_started = time.perf_counter() if self._perf_debug_enabled else None
            if playing_boat:
                # The local mixer plays the boat's own sonar room only.
                if self._opfor is not None and self.station is Station.SONAR:
                    with self.sonar_perspective(self._opfor.station):
                        self._update_audio(wall_dt)
                else:
                    self._stop_sonar_audio()
            else:
                self._update_audio(wall_dt)
            if audio_started is not None:
                self._perf_audio_s += time.perf_counter() - audio_started
        else:
            self.audio.stop()
            self._sonar_audio_sequence = -1

    def _update_audio(self, dt: float) -> None:
        """Stream opt-in sonar; there is no continuous own-ship ambience."""
        helicopter = self.station is Station.HELICOPTER
        receiver = self.helo_receiver if helicopter else self.sonar.receiver
        listening = (self.helo_audio_enabled and self.helicopter_audio_ready()
                     if helicopter else self.station is Station.SONAR
                     and self.sonar_audio_enabled
                     and not self._sonar_down())
        if not listening:
            self._stop_sonar_audio()
        else:
            blocks = receiver.blocks_since(self._sonar_audio_sequence)
            if not blocks:
                self.audio.hold_sonar()
            for sequence, samples in blocks:
                if (self._sonar_audio_sequence < 0
                        or sequence != self._sonar_audio_sequence + 1):
                    if self._sonar_audio_sequence < 0:
                        self.audio.stop_sonar(immediate=True)
                    else:
                        self.audio.discontinue_sonar_input()
                    (self.helo_audition if helicopter else self.sonar).reset_audition_audio()
                if not self.audio.play_sonar(
                        (self.helo_audition if helicopter else self.sonar).listening_samples(
                            samples, block_id=sequence),
                        receiver.sample_rate, self.sonar_volume,
                        bearing_deg=0 if helicopter else self.sonar.listen_bearing,
                        listener_bearing_deg=0 if helicopter else self.ship.course,
                        buffered=True):
                    break
                self._sonar_audio_sequence = sequence

    def _emit_sound(self, kind: str) -> None:
        """Play locally and publish a bounded, detached browser sound cue."""
        if kind == "sonar_ping":
            self.audio.play_ping()
        elif kind == "esm_contact":
            if (self.station is Station.ELOKA
                    and self.eloka_audio_enabled
                    and not self.damage.station_down("opz")):
                self.audio.play_alert("esm")
        else:
            self.audio.play_effect(kind)
        self._sound_event_seq += 1
        self._sound_events.append(dict(seq=self._sound_event_seq, kind=kind))

    ECHO_LOUD_SNR_DB = 12.0

    def _remember_ping_pulse(self) -> None:
        self._ping_pulses[self.sim_t] = self.sonar.ping_pulse
        while len(self._ping_pulses) > 32:
            del self._ping_pulses[next(iter(self._ping_pulses))]

    def _emit_echo(self, echo: dict) -> None:
        """Make one arrived echo audible: local synthesis and a browser cue.

        The simulation already delays the echo by its two-way travel time;
        this only turns the measured return (pulse, echo SNR) into sound.
        """
        pulse = self._ping_pulses.get(echo.get("t"), self.sonar.ping_pulse)
        pulse = pulse if pulse in ("CW", "LFM") else "CW"
        snr_db = float(echo.get("snr_db", 0.0))
        level = config.clamp((snr_db + 5.0) / 35.0, 0.0, 1.0)
        self.audio.play_echo(pulse, level)
        cue = f"sonar_echo_{pulse.lower()}"
        if snr_db < self.ECHO_LOUD_SNR_DB:
            cue += "_faint"
        self._sound_event_seq += 1
        self._sound_events.append(dict(seq=self._sound_event_seq, kind=cue))

    def _play_unit_audio(self, profile_key: str, mode: str, machine) -> None:
        """Kontakt-Katalog-Hörprobe: deterministisches Einheiten-Sample abspielen."""
        rate = self.audio.sample_rate
        key = ("sonar", "unit_preview", profile_key, mode, rate)
        self.audio.play_unit_preview(
            lambda: unit_sonar_preview(profile_key, machine, mode, rate), key)

    def _make_analyzer(self) -> ContactAnalyzer:
        """Read-only Kontakt-Katalog-Browser (Menue und In-Game, F8)."""
        return ContactAnalyzer(
            tr=self.tr, on_play_sample=self._play_unit_audio,
            on_stop_sample=self.audio.stop_preview,
            preview_active=self.audio.preview_playing)

    def _open_analyzer_in_game(self) -> None:
        """TUA im laufenden Spiel: Simulation laeuft weiter, Esc kehrt ins Spiel zurueck.

        With a sonar contact selected, Enter assigns the browsed profile to
        it (the operator's catalog comparison result)."""
        self._clear_controls()
        contact = self.selected_contact
        if contact is None or contact.target_id not in self.sonar.contacts:
            self.editor = self._make_analyzer()
            return
        analyzer = self._make_analyzer()
        analyzer.on_assign = lambda key: self.assign_contact_profile(contact, key)
        analyzer.assign_label = self.contact_display_id(contact)
        analyzer.current_assignment = lambda: self.profile_name(contact.player_profile)
        self.editor = analyzer

    def profile_name(self, key):
        """Display name of a catalog profile (as listed in the analyser)."""
        if key is None:
            return None
        names = self.__dict__.get("_profile_names")
        if names is None:
            from src.data.contact_analysis import project_contact_catalog
            names = {row["key"]: str(row["name"])
                     for row in project_contact_catalog()["profiles"]}
            self._profile_names = names
        return names.get(key, key)

    def assign_contact_profile(self, contact, profile_key):
        """Operator annotation: this contact matches that catalog profile."""
        if contact is None or contact.target_id not in self.sonar.contacts:
            return "stale_ref"
        if profile_key is not None and (
                type(profile_key) is not str
                or profile_key not in self.runtime_catalog.profile_systems):
            return "invalid_value"
        contact.player_profile = profile_key
        if profile_key is None:
            notice = message("runtime.profile.cleared",
                             contact=self.contact_display_id(contact))
        else:
            notice = message("runtime.profile.assigned",
                             contact=self.contact_display_id(contact),
                             profile=raw_text(self.profile_name(profile_key)))
        self._sonar_notice(notice, 2.0)
        return True

    def _open_simlog_view(self) -> None:
        """F4: Live-Protokoll-Ansicht; nur bei aktiver simlog-Option."""
        if not self.preferences.simlog:
            self.flash(message("simlog.view_disabled"), 2.0)
            return
        self._clear_station_input()
        self.simlog_view_open = True
        self.simlog_view_scroll = 0
        self.simlog_view_map = False

    def _close_simlog_view(self) -> None:
        self.simlog_view_open = False
        self.simlog_view_scroll = 0
        self.simlog_view_map = False
        self._clear_station_input()

    def _scroll_simlog_view(self, amount: int) -> None:
        self.simlog_view_scroll = max(0, self.simlog_view_scroll + amount)

    def _update_navigation(self, dt: float) -> None:
        """Wendet Steuerung, Brückenschaden und Telegraph auf die Fregatte an."""
        if self.damage.station_down("bridge"):
            self.ship.target_course = self.ship.course
        self.ship.turn_rate_scale = (
            0.5 if self.damage.station_degraded("bridge") else 1.0)
        self.ship.speed_cap = self.damage.engine_speed_cap()
        # Steering gear sits aft under the flight deck; a destroyed room
        # jams the rudder where it is. Stabilizer fins are lost with either
        # hull side destroyed. Floodwater adds displacement.
        self.ship.steering_jammed = self.damage.station_down("flightdeck")
        self.ship.stabilizers_ok = not (self.damage.station_down("hull_left")
                                        or self.damage.station_down("hull_right"))
        self.ship.flood_percent = (self.damage.flood_mass_kg()
                                   / ship_dynamics.HULL.flood_kg_per_percent)
        self.ship.update_fuel(dt)
        self.world.update(dt)
        contact = self.ship.update(dt, self.world, self.damage.list_deg())
        if contact is not None:
            speed_m_s = self.ship.last_impact_speed_kn * 1852.0 / 3600.0
            heading = math.radians(self.ship.course)
            normal_factor = abs(math.sin(heading) * contact.normal_x
                                - math.cos(heading) * contact.normal_y)
            if normal_factor <= 1e-9:
                normal_factor = 1.0
            normal_speed = speed_m_s * normal_factor
            energy_j = (0.5 * self.ship.hull_spec.mass_t * 1000.0
                        * normal_speed ** 2)
            self.damage.grounding_impact(
                energy_j, contact.hull_longitudinal, contact.hull_lateral)
            notice = message(f"event.grounding.{contact.kind}")
            self.flash(notice, 4.0)
            self.feed.add(self.world.format_time(), "navigation",
                          message("runtime.grounding.feed", kind=notice))

    def _shipping_noise_contacts(self) -> int:
        """Merchant traffic within 50 NM that feeds distant-shipping noise."""
        return sum(1 for ship in self.civilians
                   if not ship.sunk and ship.distance_nm(self.ship) <= 50.0)

    def _update_platform_sensors(self, dt: float) -> None:
        """Run independent NPC sensors before any actor makes a decision."""
        ship_target = SimpleNamespace(
            id=0, x=self.ship.x, y=self.ship.y, depth=5.0,
            course=self.ship.course, speed=self.ship.speed, active=True,
            sunk=False, side="friendly", name=None, sensor_domain="surface",
            radar_emitting=(not self.damage.station_down("opz")
                            and (self.surface_radar_on or self.air_radar_on)),
            ais_transmitting=False, noise_level=self.ship.noise_level)
        actors = sorted(
            self.subs + self.civilians + self.warships + self.flights.flights,
            key=lambda actor: (type(actor).__name__,
                               getattr(actor, "id", getattr(actor, "seq", 0))))
        suites = []
        all_candidates = [ship_target, *actors, *self.animals, *self.decoys,
                          *self.asms]
        for actor in actors:
            suite = actor.sensor_suite
            suites.append(suite)
            actor._tactical_observation = None
            actor._asw_observation = None
            domains = set()
            degraded = set()
            if getattr(actor, "sunk", False) or getattr(actor, "damage", 0.0) >= 75.0:
                domains = {"radar", "esm", "sonar", "ais"}
            elif getattr(actor, "damage", 0.0) >= 34.0:
                degraded = {"radar", "esm", "sonar", "ais"}
            candidates = [candidate for candidate in all_candidates
                          if getattr(candidate, "side", None) != actor.side]
            suite.datalink_reachable = not (
                isinstance(actor, Sub) and actor.depth > MAST_DEPTH_M
                and getattr(getattr(actor, "endurance", None), "phase", "")
                not in ("SNORKEL", "RADIO"))
            suite.update(
                self.sim_t, actor, candidates, self.world, self.runtime_catalog,
                emcon={"radar": getattr(actor, "radar_emitting", False),
                       "ais": getattr(actor, "ais_transmitting", False)},
                unavailable=domains, degraded=degraded)
            # Metadata-only R10 submarine components retain the established
            # tactical gate; the actor still receives only a detached observation.
            legacy_observation = (not suite.controllers or getattr(
                actor, "legacy_observation_model", False))
            if legacy_observation and actor.side == "hostile":
                distance = math.hypot(actor.x - self.ship.x, actor.y - self.ship.y)
                blocked = self.world.land_blocks_line(
                    actor.x, actor.y, self.ship.x, self.ship.y)
                if (isinstance(actor, Sub) and distance < 20.0
                        and (actor.memory["last_ping_age"] <= dt
                             or (self.ship.noise_level() >= 0.75 and distance < 18.0))
                        and not self.world.sonar_path_blocked(
                            actor.x, actor.y, actor.depth,
                            self.ship.x, self.ship.y, 5.0)):
                    actor._tactical_observation = snapshot_observation(
                        actor, self.ship, domain="sonar", now=self.sim_t)
                elif (isinstance(actor, SurfaceShip) and actor.emitter
                      and distance <= config.WARSHIP_ASM_RANGE_NM and not blocked):
                    actor._tactical_observation = snapshot_observation(
                        actor, self.ship, domain="radar", now=self.sim_t)
                elif (isinstance(actor, Flight) and actor.esm
                      and ship_target.radar_emitting
                      and distance <= actor.esm_range_nm and not blocked):
                    actor._tactical_observation = snapshot_observation(
                        actor, self.ship, domain="esm", now=self.sim_t,
                        positioned=False)
        exchange_friendly_datalink(suites, self.sim_t)
        # Friendly platforms publish detached radar fixes into the own-ship air
        # picture. Candidate identity is used only at this sensor-generation
        # boundary; downstream weapons consume the resulting saved observation.
        for actor in actors:
            suite = actor.sensor_suite
            if actor.side != "friendly" or suite.datalink_group != "blue":
                continue
            for asm in self.asms:
                for report in suite.tracks_for_candidate(asm, self.sim_t):
                    if (report.domain != "radar" or report.x is None
                            or report.y is None or report.range_nm is None):
                        continue
                    dx, dy = report.x - self.ship.x, report.y - self.ship.y
                    self.air_picture.observe(
                        track_id=f"M-{asm.seq}", kind="ASM", target_id=asm.seq,
                        source="DATALINK",
                        bearing=math.degrees(math.atan2(dx, -dy)) % 360.0,
                        range_nm=math.hypot(dx, dy), observer_x=self.ship.x,
                        observer_y=self.ship.y, course=report.course,
                        quality=report.quality, now=report.last_seen,
                        position_time=report.last_seen, label=f"A-{asm.seq}",
                        bearing_uncertainty_deg=report.bearing_uncertainty_deg)
        for actor in actors:
            suite = actor.sensor_suite
            if (not suite.controllers
                    or getattr(actor, "legacy_observation_model", False)):
                continue
            tracks = suite.tactical_tracks(self.sim_t)
            preferred = ("sonar" if isinstance(actor, Sub) else
                         "esm" if isinstance(actor, Flight) else "radar")
            actor._tactical_observation = next(
                (track for track in tracks if track.domain == preferred),
                tracks[0] if tracks else None)
            if isinstance(actor, SurfaceShip):
                actor._asw_observation = next(
                    (track for track in tracks
                     if track.domain == "sonar"
                     and track.fix_source in ("ACTIVE", "TMA", "BUOY", "FUSED")
                     and track.x is not None and track.y is not None), None)

    def _update_underwater_entities(self, dt: float) -> None:
        """Aktualisiert U-Boote, Tiere, Zivile und Dekoys."""
        for sub in self.subs:
            was_sunk = sub.sunk
            sub.update(dt, getattr(sub, "_tactical_observation", None), self.world)
            if (sub.pinged_this_tick
                    and math.hypot(sub.x - self.ship.x, sub.y - self.ship.y)
                    <= config.SONAR_PING_HEAR_RANGE_NM
                    and not self.world.sonar_path_blocked(
                        sub.x, sub.y, sub.depth, self.ship.x, self.ship.y, 5.0)):
                bearing = math.degrees(math.atan2(
                    sub.x - self.ship.x, -(sub.y - self.ship.y))) % 360.0
                self.flash(message("runtime.enemy_ping.detected",
                                   bearing=f"{bearing:05.1f}"), 3.0)
                self.audio.play_alert("danger")
                self.feed.add(self.world.format_time(), "sonar",
                              message("runtime.enemy_ping.feed",
                                      bearing=f"{bearing:05.1f}"))
            if sub.sunk and not was_sunk:
                if sub.side == "hostile":
                    self.score += config.SCORE_SUNK
                else:
                    self.incident = True
                self._report_breakup_noise(sub.x, sub.y, sub.depth, sub.id)
            if sub.sunk and sub.side == "hostile" and self.roe != "FREE":
                self.roe = "FREE"
                self.hq_msg(message("runtime.roe_free_confirmed"))
        for animal in self.animals:
            animal.update(dt, self.world)
        for civilian in self.civilians:
            civilian.update(dt, getattr(civilian, "_tactical_observation", None),
                            self.world)
        for w in self.warships:
            w.update(dt, getattr(w, "_tactical_observation", None), self.world,
                     asw_observation=getattr(w, "_asw_observation", None))
        for sub in self.subs:
            while sub.pending_decoys and len(self.decoys) < MAX_DECOYS:
                dx, dy = sub.pending_decoys.pop(0)
                decoy_profile = self.runtime_catalog.decoys[
                    self.runtime_catalog.runtime_bindings["submarine_decoy"]]
                self.decoys.append(Decoy(
                    dx, dy, sub.depth, self.rng_asw, decoy_profile,
                    self.runtime_catalog.acoustic_for(decoy_profile.key),
                    source_id=sub.id))
        for decoy in self.decoys:
            decoy.update(dt, self.world)
        self.decoys = [decoy for decoy in self.decoys if not decoy.dead]

    def _update_aviation(self, dt: float) -> None:
        """Aktualisiert HSP-5, Sonarbojen und Chaff-Kühlzeit."""
        if (self.helo.dip_state in ("DEPLOYING", "DEPLOYED")
                and not self.helicopter_weather()["dipping_safe"]):
            self.helo.set_dipping(False, self.world)
        icing = (self.atmosphere()["icing"] if self.helo.airborne else "none")
        self.helo.update(dt, self.ship, self.world,
                         recovery_available=not self.damage.station_down("flightdeck")
                         and helicopter_physics.deck_within_limits(
                             self.ship.roll, self.ship.pitch),
                         fuel_factor=(config.HELO_ICING_FUEL_FACTOR
                                      if icing != "none" else 1.0))
        for buoy in self.buoys:
            buoy.update(dt, self.world)
        self.buoys = [buoy for buoy in self.buoys if buoy.active]
        self.softkill_store.update(dt)
        self.chaff_cd = min(self.softkill_store.loading, default=0.0)

    def _update_asw_stores(self, dt: float) -> None:
        scale = (0.0 if self.damage.station_down("weapons") else
                 .5 if self.damage.station_degraded("weapons") else 1.0)
        self.player_torpedo_battery.update(dt, scale)
        self.torpedo_count = self.player_torpedo_battery.remaining_total
        self.nixie_store.update(dt)
        for decoy in self.nixies:
            decoy.update(dt, self.ship, self.world)
        self.nixies = [decoy for decoy in self.nixies if not decoy.dead]

    def _update_air_defense(self, dt: float, publish_picture: bool = True) -> None:
        """Aktualisiert ASM-Wellen, CIWS und ESSM-Abfangflugkorper."""
        profiles = self._air_defense_loadout
        self._drain_warship_asm()
        self._drain_raider_asm()
        self._maybe_spawn_asm()
        self._auto_ecm_softkill()
        # Softkill state is resolved by ASM.update before layered hardkill.
        self.ciws_cooldown_s = max(0.0, getattr(self, "ciws_cooldown_s", 0.0) - dt)
        for cloud in self.chaff_clouds:
            cloud.update(dt, self.world.wind_from_deg, self.world.wind_speed_kn)
        self.chaff_clouds = [cloud for cloud in self.chaff_clouds if cloud.active]
        clouds = {cloud.seq: cloud for cloud in self.chaff_clouds}
        for asm in self.asms:
            asm.update(dt, self.ship, self.world,
                       ecm_effect=self._ecm_effect_against_asm(asm),
                       chaff_target=clouds.get(asm.chaff_cloud))
            if asm.state == "TREFFER":
                hit = self.damage.missile_hit(*self._hull_impact(asm.x, asm.y))
                self._emit_sound("explosion")
                self.announce(message("runtime.hit.asm", compartments=", ".join(
                    self.damage.compartments[k].name for k in hit)),
                    "schaden", 5.0)
        observed_asms = {self._missile_seq(track): track
                         for track in self.asm_tracks()
                         if self._missile_seq(track) is not None}
        for essm in self.essms:
            track = observed_asms.get(essm.target_id)
            if (not essm.seeker_acquired and track is not None
                    and track.x is not None and track.y is not None
                    and track.position_seen is not None
                    and self.sim_t - track.position_seen
                    <= profiles["sam"]["observation_max_age_s"]):
                essm.guidance_x, essm.guidance_y = track.x, track.y
            essm.update(dt, candidates=self.asms, world=self.world)
        ciws = profiles["ciws"]
        # CIWS fire control works on its latest own measurement, not on the
        # smoothed OPZ track range.
        def fc_range(track):
            return (track.raw_range_nm if track.raw_range_nm is not None
                    else track.range_nm)

        # The mount slews towards the nearest fresh close-in missile track.
        close_tracks = sorted(
            (fc_range(track), track.track_id, track) for track in observed_asms.values()
            if fc_range(track) is not None and fc_range(track) <= ciws["range_nm"]
            and track.position_seen is not None
            and self.sim_t - track.position_seen <= ciws["observation_max_age_s"])
        if self.ciws_authorized and close_tracks:
            self.ciws_mount_deg = ciws_physics.slew(
                self.ciws_mount_deg, close_tracks[0][2].bearing, dt)
        for asm in self.asms:
            track = observed_asms.get(asm.seq)
            if (self.ciws_authorized
                    and asm.state in ("LAUF", "CHAFF")
                    and not (asm.state == "CHAFF" and asm.broken)
                    and track is not None
                    and track.x is not None and track.y is not None
                    and track.position_seen is not None
                    and self.sim_t - track.position_seen
                    <= ciws["observation_max_age_s"]
                    and self.ciws_ammo >= ciws["rounds_per_attempt"]
                    and fc_range(track) is not None
                    and fc_range(track) <= ciws["range_nm"]
                    and self.ciws_cooldown_s <= 0.0
                    and ciws_physics.on_target(self.ciws_mount_deg, track.bearing)
                    and not self.damage.station_down("opz")
                    and not self.world.land_blocks_line(
                        self.ship.x, self.ship.y, track.x, track.y)):
                self.ciws_ammo -= ciws["rounds_per_attempt"]
                self.ciws_cooldown_s = ciws["cycle_s"]
                self._emit_sound("gunfire")
                # Burst physics at the true geometry: dispersion and
                # prediction error over the rounds' time of flight; a missile
                # that arrives first cannot be stopped by this burst.
                distance = asm.distance_nm(self.ship)
                time_to_go = distance / max(config.kn_to_nm_per_s(asm.speed_kn), 1e-9)
                kill = (0.0 if time_to_go <= ciws_physics.time_of_flight_s(distance)
                        else ciws_physics.burst_kill_probability(
                            distance, ciws["rounds_per_attempt"],
                            asm.jamming(self.ship), ciws["kill_probability"]))
                if self.rng_asm.random() < kill:
                    asm.state = "ABGEFANGEN"
                    self.audio.play_alert("defense")
                    self.announce(message("runtime.ciws.intercepted"),
                                  "waffen", 3.0)
        self.asms = [a for a in self.asms if a.state in ("LAUF", "CHAFF")]
        self.essms = [e for e in self.essms if e.state == "LAUF"]
        if publish_picture:
            self._update_air_picture()
            observed_threat = bool(self.asm_tracks())
            if observed_threat and not self.air_threat_reported:
                self.flash(message("runtime.threat.air"), 4.0)
                self.feed.add(self.world.format_time(), "waffen", message("runtime.threat.air"))
            self.air_threat_reported = observed_threat

    def _auto_ecm_softkill(self) -> None:
        """Couple critical terminal ECM tracks to the finite RF decoy store."""
        if (not self.ecm_jammer.auto_enabled or self.softkill_store.ready <= 0
                or self.damage.station_down("opz")):
            return
        by_target = {self._missile_seq(track): track
                     for track in self.asm_tracks()
                     if self._missile_seq(track) is not None}
        softkill_range = self._air_defense_loadout["softkill"]["range_nm"]
        candidates = []
        for asm in self.asms:
            track = by_target.get(asm.seq)
            effect = self._ecm_effect_against_asm(asm)
            if (asm.state != "LAUF" or track is None or track.range_nm is None
                    or track.range_nm > softkill_range or effect is None
                    or effect.effectiveness <= 0.0):
                continue
            candidates.append((track.range_nm, track.track_id, track))
        if candidates:
            self.launch_chaff_at(min(candidates, key=lambda item: item[:2])[2])

    def _update_enemy_torpedoes(self, dt: float) -> None:
        """Erzeugt und bewegt Feindtorpedos; Treffer werden als Schaden gebucht."""
        self._drain_enemy_torpedoes()
        for torpedo in self.enemy_torpedoes:
            torpedo.update(dt, self.ship, world=self.world,
                           seeker_candidates=self.nixies)
        for torpedo in self.enemy_torpedoes:
            if torpedo.state == "HIT":
                distance_m = max(1.0, math.hypot(torpedo.x - self.ship.x,
                                                 torpedo.y - self.ship.y) * 1852.0)
                # Shock factor sets the hole size relative to a 20 m burst.
                hit = self.damage.torpedo_hit(
                    impact=self._hull_impact(torpedo.x, torpedo.y),
                    hole_scale=config.clamp(20.0 / distance_m, 0.5, 3.0))
                self._emit_sound("explosion")
                text = ", ".join(self.damage.compartments[k].name for k in hit)
                self.flash(message("runtime.hit.torpedo", compartments=text), 5.0)
                self.feed.add(self.world.format_time(), "schaden",
                              message("runtime.hit.damage", compartments=text))
        self.enemy_torpedoes = [t for t in self.enemy_torpedoes
                                if t.state == "RUN"]

    def _drain_asrocs(self) -> None:
        for ship in self.warships:
            pending, ship.pending_asroc = ship.pending_asroc, []
            room = max(0, MAX_ASROCS - len(self.asrocs))
            ship.pending_asroc = pending[room:]
            for row in pending[:room]:
                weapon = self.runtime_catalog.weapons[row["weapon_key"]]
                self.asroc_seq += 1
                self.asrocs.append(ASROC(
                    row["x"], row["y"], row["datum_x"], row["datum_y"],
                    self.asroc_seq, weapon.key,
                    self.runtime_catalog.runtime_bindings["helicopter_torpedo"],
                    weapon.maximum_speed_kn, weapon.engagement_range_nm[1],
                    ship.side, row["target_depth_m"], ship.id))

    def _update_asrocs(self, dt: float) -> None:
        survivors = []
        for weapon in self.asrocs:
            if weapon.update(dt, self.world):
                profile = self.runtime_catalog.torpedoes[
                    weapon.payload_profile_key]
                self.torpedo_seq += 1
                payload = Torpedo(
                    weapon.x, weapon.y, weapon.course, weapon.target_depth_m,
                    None, self.torpedo_seq, guidance_x=weapon.datum_x,
                    guidance_y=weapon.datum_y, profile=profile,
                    launch_origin="asroc",
                    launch_platform_id=weapon.launch_platform_id,
                    launch_weapon_key=weapon.weapon_key, time_since_launch=0.0)
                payload.break_wire()
                self.torpedoes.append(payload)
            elif weapon.state == "FLIGHT":
                survivors.append(weapon)
        self.asrocs = survivors
        # A launch decision consumes this substep before flight begins.
        self._drain_asrocs()

    def _hull_impact(self, x_nm: float, y_nm: float) -> tuple[float, float]:
        """Impact point in hull coordinates (bow/starboard positive, -1..1)."""
        dx, dy = (x_nm - self.ship.x) * 1852.0, (y_nm - self.ship.y) * 1852.0
        heading = math.radians(self.ship.course)
        forward = dx * math.sin(heading) - dy * math.cos(heading)
        starboard = dx * math.cos(heading) + dy * math.sin(heading)
        half_length = self.ship.hull_spec.length_m / 2.0
        half_beam = self.ship.hull_spec.beam_m / 2.0
        if math.hypot(forward, starboard) < 1e-6:
            return 0.0, 0.0
        # Project onto the hull outline along the approach direction.
        scale = max(abs(forward) / half_length, abs(starboard) / half_beam, 1.0)
        return (config.clamp(forward / scale / half_length, -1.0, 1.0),
                config.clamp(starboard / scale / half_beam, -1.0, 1.0))

    def _incoming_hit_zone(self, torpedo) -> str:
        """Naehert die getroffene Schiffszone aus der Angriffsrichtung an."""
        source_bearing = (torpedo.course + 180.0) % 360.0
        relative = config.angle_diff_deg(source_bearing, self.ship.course)
        if abs(relative) <= 45.0:
            return "bow"
        if abs(relative) >= 135.0:
            return "stern"
        return "starboard" if relative > 0.0 else "port"

    def _sub_hears_torpedo(self, sub, torpedo, distance_nm: float) -> bool:
        """Passive sonar equation for a running torpedo heard by a boat.

        The figure of merit reproduces TORP_RUNNING_NOISE_RANGE_NM for a
        quiet boat and a torpedo at cruise speed; propagation, ambient noise,
        the boat's own noise and the torpedo's speed-dependent level decide."""
        if distance_nm > 3.0 * config.TORP_RUNNING_NOISE_RANGE_NM:
            return False
        frequency = torpedo_dyn.RUNNING_NOISE_BAND_HZ
        excess = sonar_propagation.ray_excess_db(
            self.world, sub.x, sub.y, max(sub.depth, 1.0), torpedo.x, torpedo.y,
            max(torpedo.depth, 1.0), frequency)
        absorption = sonar_equation.francois_garrison_db_per_km(frequency)
        terms = sonar_equation.passive_terms(
            frequency_hz=frequency, distance_nm=max(distance_nm, 0.01),
            target_bonus=10.0 ** (torpedo.source_level_offset_db() / 20.0),
            excess_path_loss_db=(0.0 if excess is None else excess
                                 - sonar_propagation.ray_reference_excess_db(
                                     config.TORP_RUNNING_NOISE_RANGE_NM, frequency))
            # Absorption is part of the reference-range figure of merit too.
            - absorption * config.TORP_RUNNING_NOISE_RANGE_NM * 1.852,
            absorption_db_per_km=absorption,
            legacy_absorption_db=0.0,
            own_range_factor=max(0.2, 1.0 - 0.8 * sub.noise_level()),
            array_range_factor=(config.TORP_RUNNING_NOISE_RANGE_NM
                                / config.SONAR_PASSIVE_BASE_NM),
            sea_state=float(getattr(self.world, "effective_sea_state",
                                    self.world.sea_state)),
            rain=float(getattr(self.world, "rain_intensity", 0.0)),
            shipping_contacts=self.sonar.shipping_contacts)
        return terms.signal_excess_db > 0.0

    def _update_player_torpedoes(self, dt: float) -> None:
        """Bewegt eigene Torpedos und verarbeitet Treffer/Fehlkontakte."""
        for sub in self.subs:
            if (sub.sunk or sub.state == "SINKING"
                    or sub.memory["last_torpedo_age"] < config.SUB_EVADE_DURATION_S):
                continue
            for torpedo in self.torpedoes:
                if torpedo.state != "RUN":
                    continue
                dist = math.hypot(torpedo.x - sub.x, torpedo.y - sub.y)
                if (dist <= config.TORP_HOME_RANGE_NM
                        and not self.world.sonar_path_blocked(
                            torpedo.x, torpedo.y, torpedo.depth,
                            sub.x, sub.y, sub.depth)):
                    sub.alert_torpedo(source=(torpedo.x, torpedo.y))
                    break
                # W2: graduated passive notice of a running torpedo's own
                # noise, between pure terminal homing and the loud one-time
                # launch transient - additive, does not replace either.
                if (self._sub_hears_torpedo(sub, torpedo, dist)
                        and not self.world.sonar_path_blocked(
                            torpedo.x, torpedo.y, torpedo.depth,
                            sub.x, sub.y, sub.depth)):
                    sub.alert_torpedo(source=(torpedo.x, torpedo.y))
                    break
        for torpedo in self.torpedoes:
            target_id = getattr(torpedo.target, "id", None)
            contact = self.sonar.contacts.get(target_id)
            solution_fresh = self._contact_range_fresh(contact)
            if (solution_fresh and contact.observed_x is not None
                    and contact.observed_y is not None):
                torpedo.wire_update(contact.observed_x, contact.observed_y)
            if torpedo.launch_origin == "frigate":
                torpedo.wire_tension_update(dt, self.ship.speed,
                                            self.ship.yaw_rate)
            torpedo.update(dt, seeker_candidates=(
                [s for s in self.subs if not s.sunk]
                + [d for d in self.decoys if not d.dead]
                + [w for w in self.warships if not w.sunk]
                + [a for a in self.animals if not a.dead]
                + [c for c in self.civilians if not c.sunk]), world=self.world,
                collision_candidates=self.civilians)
        alive = []
        for torpedo in self.torpedoes:
            if torpedo.state == "RUN":
                alive.append(torpedo)
                continue
            if torpedo.state != "HIT":
                continue
            self._emit_sound("explosion")
            if (isinstance(torpedo.target, SurfaceShip)
                    and torpedo.target.side != "hostile"):
                torpedo.target.sunk = True
                self.incident = True
                self.live_traffic.mark_ship_destroyed(
                    getattr(torpedo.target, "live_mmsi", None))
                self.audio.play_alert("danger")
                self.flash(message("runtime.incident"), 6.0)
                self.feed.add(self.world.format_time(), "waffen",
                              message("runtime.incident"))
                continue
            contact = self.sonar.contacts.get(getattr(torpedo.target, "id", None))
            if contact is not None and self.sim_t - contact.last_seen < config.SONAR_CONTACT_LOST_S:
                self.flash(message("runtime.hit.contact",
                                   contact=contact.id), 3.0)
                self.feed.add(self.world.format_time(), "waffen",
                              message("runtime.hit.contact", contact=contact.id))
            if getattr(torpedo.target, "hostile", False):
                if (torpedo.target.sunk
                        and not torpedo.target.sunk_score_awarded):
                    torpedo.target.sunk_score_awarded = True
                    self.score += config.SCORE_SUNK
                    self._report_breakup_noise(
                        torpedo.target.x, torpedo.target.y,
                        getattr(torpedo.target, "depth", 0.0),
                        torpedo.target.id)
        self.torpedoes = alive

    def _report_breakup_noise(self, x: float, y: float, depth: float,
                              key: int) -> None:
        """A sinking hull is heard, not identified: bearing only, no class.

        Kill assessment stays with the operator; the score is shown only in
        the mission debrief.
        """
        if (self.damage.station_down("sonar")
                or math.hypot(x - self.ship.x, y - self.ship.y)
                > config.TORP_TRANSIENT_HEAR_NM
                or self.world.sonar_path_blocked(x, y, depth,
                                                 self.ship.x, self.ship.y, 5.0)):
            return
        bearing = threat_cue.measured_cue_bearing(
            math.degrees(math.atan2(x - self.ship.x, -(y - self.ship.y))) % 360.0,
            self.seed, 500_000 + int(key), self.sim_t)
        notice = message("runtime.breakup_noise", bearing=f"{bearing:05.1f}")
        self.flash(notice, 4.0)
        self.feed.add(self.world.format_time(), "sonar", notice)

    def _update_helicopter_audio(self, dt: float, targets) -> None:
        """Synthesize only presently measured helicopter channels, at 4 Hz."""
        if (self.station is not Station.HELICOPTER
                and not self.commander.station_leased(Station.HELICOPTER)):
            return
        if not self.helicopter_audio_ready():
            return
        self._helo_receiver_timer += dt
        if self._helo_receiver_timer + 1e-9 < self.helo_receiver.block_s:
            return
        seq = (int(self.helo_listen_source[2:])
               if self.helo_listen_source.startswith("SB") else None)
        reports = []
        for target in targets:
            contact = self.sonar.contacts.get(target.id)
            if contact is None:
                continue
            if seq is None:
                if (not self.helo.dip_available or contact.dip_last_seen is None
                        or not 0 <= self.sim_t - contact.dip_last_seen < 2.0):
                    continue
                bearing = contact.dip_bearing
                quality = contact.quality
            else:
                row = contact.buoy_reports.get(seq)
                if row is None or not 0 <= self.sim_t - row["measured_at"] < 2.0:
                    continue
                bearing = row["bearing"]
                quality = row["quality"]
            if bearing is None:
                continue
            source = dict(bearing=bearing, level=quality,
                          lines=target.lofar_lines(self.sim_t),
                          seed=getattr(target, "sensor_seed", target.id))
            broadband = getattr(target, "broadband", lambda: {})()
            if isinstance(broadband, dict) and broadband.get("level", 0) > 0:
                source["broadband"] = broadband
            reports.append((contact, source))
        selected = next((row for contact, row in reports
                         if contact is self.selected_contact), None)
        listen_bearing = (self.helo_listen_bearing if self.helo_listen_bearing is not None
                          else (selected or reports[0][1])["bearing"] if reports else 0.0)
        while self._helo_receiver_timer + 1e-9 >= self.helo_receiver.block_s:
            self._helo_receiver_timer = max(0.0, self._helo_receiver_timer
                                            - self.helo_receiver.block_s)
            self.helo_receiver.update(
                [row for _, row in reports], listen_bearing, 18.0,
                .2 if seq is None else .05,
                getattr(self.world, "effective_sea_state", self.world.sea_state),
                0.0)
            self.helo_spectra.append(tuple(self.helo_receiver.spectrum))
            del self.helo_spectra[:-128]
            self.helo_broadband_history.append(tuple(self.helo_receiver.broadband))
            del self.helo_broadband_history[:-128]
            self.helo_demon_history.append(tuple(self.helo_receiver.demon_spectrum))
            del self.helo_demon_history[:-128]

    def _update_sensors(self, dt: float) -> None:
        """Aktualisiert Sonar-Kontakte, TMA und Kontaktfeed."""
        if self.target is not None and self.target.target_id not in self.sonar.contacts:
            self.target = None
        if (self.selected_contact is not None
                and self.selected_contact.target_id not in self.sonar.contacts):
            self.selected_contact = None
        prev_cts = {c.id for c in self.sonar.contacts.values()}
        targets = self._sonar_targets()
        if self.damage.station_down("sonar"):
            if self.sonar.lofar_history:
                self.sonar.reset_listening_history()
                self.sonar.broadband_history.clear()
                self.sonar.history_times.clear()
                self.sonar.broadband_long_history.clear()
                self.sonar.broadband_long_times.clear()
                self.sonar._broadband_long_accumulator.clear()
            self.sonar.update_dipping_passive(
                dt, self.sim_t, self.helo, targets, self.world,
                range_factor=self._sonar_range_factor())
            self._update_helicopter_audio(dt, targets)
            return
        focus = (self._find_target(self.selected_contact.target_id)
                 if self.selected_contact else None)
        self.sonar.shipping_contacts = self._shipping_noise_contacts()
        self.sonar.update(dt, self.sim_t, self.ship, targets, self.world,
                          range_factor=self._sonar_range_factor(),
                          mode=self.sonar_mode, buoys=self.buoys,
                           focus_tgt=focus,
                           own_cavitation=1.0 if self.ship.cavitating else 0.0,
                           advance_mechanics=False)
        self.sonar.update_dipping_passive(
            dt, self.sim_t, self.helo, targets, self.world,
            range_factor=self._sonar_range_factor())
        self._update_helicopter_audio(dt, targets)
        for contact in self.sonar.active_contacts():
            bearing = (contact.passive_bearing
                       if contact.passive_bearing is not None else contact.bearing)
            range_nm = None
            active_fixes = contact.active_fixes(self.sim_t)
            if contact.observed_x is not None and contact.observed_y is not None:
                dx = contact.observed_x - self.ship.x
                dy = contact.observed_y - self.ship.y
                bearing = math.degrees(math.atan2(dx, -dy)) % 360.0
                range_nm = math.hypot(dx, dy)
            # The domain symbol follows the operator's classification; the
            # contact's underlying entity type is never published.
            observed_kind = SONAR_CLASS_KINDS.get(contact.player_class, "UNKNOWN")
            self.air_picture.observe(
                track_id=f"U-{contact.target_id}",
                kind=observed_kind,
                target_id=contact.target_id,
                source=(f"SONAR-{max(active_fixes, key=lambda fix: (fix['fixed_at'], fix['source']))['source']}"
                        if active_fixes
                        else contact.passive_source),
                bearing=bearing, range_nm=range_nm,
                observer_x=self.ship.x, observer_y=self.ship.y,
                course=contact.tma_course,
                quality=max(contact.quality, contact.confidence),
                now=contact.last_seen, label=f"K{contact.id}",
                position_time=contact.range_seen,
                bearing_uncertainty_deg=contact.bearing_uncertainty_deg)
        while self.sonar.echo_events:
            echo = self.sonar.echo_events.pop(0)
            self._emit_echo(echo)
            if echo["contact_id"] == 0:
                self.feed.add(self.world.format_time(), "sonar",
                              message("runtime.echo.unassociated",
                                      bearing=f"{echo['bearing']:05.1f}",
                                      range=f"{echo['range_nm']:.1f}"))
                continue
            self.feed.add(self.world.format_time(), "sonar",
                          message("runtime.echo.feed", contact=echo["contact_id"],
                                  bearing=f"{echo['bearing']:05.1f}",
                                  range=f"{echo['range_nm']:.1f}",
                                  depth=f"{echo['depth_m']:.0f}"))
            self.flash(message("runtime.echo.flash", contact=echo["contact_id"],
                               range=f"{echo['range_nm']:.1f}"), 2.0)
        for contact in self.sonar.active_contacts():
            if contact.id not in prev_cts:
                key = ("runtime.contact.new_range" if contact.range_est
                       else "runtime.contact.new_bearing")
                self.feed.add(self.world.format_time(), "sonar",
                              message(key,
                                      contact=contact.id,
                                      bearing=f"{contact.bearing:4.0f}",
                                      range=(f"{contact.range_est:.1f}"
                                             if contact.range_est else ""),
                                      origin=contact.origin))
        self._update_torpedo_cues()

    def current_torpedo_cues(self) -> list:
        """Torpedo intercepts audible right now, as detached measurements.

        A pure function of the saved torpedo state and simulation time: a
        launch transient or HF seeker pulses on a noisy bearing. The weapon's
        type or identity is never published; only the intercept is.
        """
        if self.damage.station_down("sonar"):
            return []
        cues = []
        for torpedo in self.enemy_torpedoes:
            if torpedo.state != "RUN":
                continue
            distance = math.hypot(torpedo.x - self.ship.x, torpedo.y - self.ship.y)
            kind = threat_cue.torpedo_cue_kind(
                torpedo.time_since_launch, torpedo.terminal_active, distance)
            if kind is None or self.world.sonar_path_blocked(
                    torpedo.x, torpedo.y, torpedo.depth,
                    self.ship.x, self.ship.y, 5.0):
                continue
            true_bearing = math.degrees(math.atan2(
                torpedo.x - self.ship.x, -(torpedo.y - self.ship.y))) % 360.0
            key = (int(torpedo.launch_platform_id or 0) * 1000
                   + int(getattr(torpedo, "idx", 0)))
            cues.append({"kind": kind, "t": self.sim_t, "torpedo": torpedo,
                         "bearing": threat_cue.measured_cue_bearing(
                             true_bearing, self.seed, key, self.sim_t)})
        return cues

    def _update_torpedo_cues(self) -> None:
        """Announce each intercept once and hold it briefly on the alarm board."""
        self.torpedo_cues = [cue for cue in self.torpedo_cues
                             if self.sim_t - cue["t"] <= config.TORP_CUE_HOLD_S]
        for cue in self.current_torpedo_cues():
            torpedo = cue.pop("torpedo")
            reported = self._torpedo_cues_reported.setdefault(torpedo, set())
            self.torpedo_cues = [held for held in self.torpedo_cues
                                 if held["serial"] != id(torpedo)]
            self.torpedo_cues.append(dict(cue, serial=id(torpedo)))
            if cue["kind"] in reported:
                continue
            reported.add(cue["kind"])
            notice = message(f"runtime.torpedo_cue.{cue['kind']}",
                             bearing=f"{cue['bearing']:05.1f}")
            self.flash(notice, 4.0)
            self.audio.play_alert("danger")
            self.feed.add(self.world.format_time(), "sonar", notice)

    def torpedo_warnings(self, held: bool = True) -> list:
        """Detached torpedo alarms: held intercepts plus operator-classified
        TORPEDO contacts. `held=False` uses only intercepts audible now."""
        cues = (self.torpedo_cues if held else self.current_torpedo_cues())
        rows = [{"source": cue["kind"], "bearing": cue["bearing"],
                 "age_s": self.sim_t - cue["t"], "contact": None}
                for cue in cues]
        rows += [{"source": "classified", "bearing": contact.bearing,
                  "age_s": self.sim_t - contact.last_seen, "contact": contact.id}
                 for contact in self.sonar.active_contacts()
                 if contact.player_class == "TORPEDO"]
        return sorted(rows, key=lambda row: (row["age_s"], row["bearing"]))

    def _update_damage_and_mission(self, dt: float) -> None:
        """Fortschritt von Schaden, Flugverkehr und Missionszielen."""
        self.damage.update(dt, draft_m=self.ship.dynamic_draft_m())
        self.flights.update(dt, world=self.world,
                            near=(self.ship.x, self.ship.y))
        self._check_mission_end()

    def _update_sim(self, dt: float) -> None:
        self.sim_t += dt
        self.mission_time += dt
        self._mission_time_warning()
        self._update_navigation(dt)
        self._update_asw_stores(dt)
        self.sonar.advance_mechanics(dt, self.sim_t, self.ship)
        if self.sonar.tow_state != self._last_tow_state:
            keys = {TowState.STREAMED: "status.tas.streamed",
                    TowState.STOWED: "status.tas.stowed",
                    TowState.FAULT: "status.tas.fault"}
            key = keys.get(self.sonar.tow_state)
            if key is not None:
                notice = message(key)
                self.flash(notice, 3.0)
                self.feed.add(self.world.format_time(), "sonar", notice)
            self._last_tow_state = self.sonar.tow_state
        if self._opfor is not None:
            if self._opfor.sub not in self.subs:
                self._opfor = None
                self._opfor_hold_s = 0.0
            else:
                opfor.advance_mechanics(self, self._opfor, dt)
                self._opfor_hold_s = max(0.0, self._opfor_hold_s - dt)
        sweep = config.RADAR_SWEEP_DEG_PER_S * dt
        self.radar_scan_phase = (self.radar_scan_phase + sweep) % 360.0
        self.radar_scan_pending_deg = min(360.0, self.radar_scan_pending_deg + sweep)
        self._sensor_acc += dt
        publish_picture = self._sensor_acc >= .25
        if publish_picture:
            self._update_platform_sensors(self._sensor_acc)
        self._update_underwater_entities(dt)
        self._update_aviation(dt)
        self._esm_acc += dt
        self._radio_acc += dt
        self._slow_acc += dt
        self._update_raiders(dt, publish_picture=publish_picture)
        self._update_air_defense(dt, publish_picture=publish_picture)
        # M13: Wetter-Hinweise per Teletype
        self.hq_timer -= dt
        if self.hq_timer <= 0.0:
            self.hq_timer = config.WEATHER_BULLETIN_PERIOD_S
            weather = self.world.weather_values()
            self.hq_msg(message(
                "runtime.hq.profile", sea_state=f"{weather['sea_state']:.1f}",
                depth=f"{self.world.thermocline_depth_m(self.ship.x, self.ship.y):.0f}",
                tide=f"{self.world.tide_m(self.ship.x, self.ship.y):+.1f}",
                sst=f"{self.world.ocean.sea_surface_temperature_c(self.world.hour):.1f}",
                wind_from=f"{weather['wind_from_deg']:.0f}",
                wind_speed=f"{weather['wind_speed_kn']:.0f}",
                rain=f"{weather['rain_intensity']:.0%}",
                visibility=f"{weather['visibility_nm']:.1f}"))
        self._update_enemy_torpedoes(dt)
        self._update_player_torpedoes(dt)
        # A payload entering the water starts moving on the next substep; the
        # current substep was already consumed by ASROC flight.
        self._update_asrocs(dt)
        if self._sensor_acc >= .25:
            sensor_dt = self._sensor_acc
            self._sensor_acc = 0.0
            self._update_sensors(sensor_dt)
            if self._opfor is not None:
                opfor.update_sonar(self, self._opfor, sensor_dt)
                opfor.update_wires(self, self._opfor, sensor_dt)
                opfor.update_crew(self, self._opfor)
        if self._esm_acc >= .5:
            self._esm_acc = 0.0
            self._update_esm_picture()
        if self._radio_acc >= .5:
            self._radio_acc = 0.0
            self._update_radio_picture()
        if self._slow_acc >= .5:
            slow_dt = self._slow_acc
            self._slow_acc = 0.0
            self._update_damage_and_mission(slow_dt)
        # Automation consumes observations published in this substep; actuator
        # changes take effect on the following physics substep.
        self.autocrew.update(self)
        self._record_simlog_state(dt)

    def _mission_time_warning(self) -> None:
        """Warn before a deadline so the player can react instead of guessing."""
        remaining = self.mission.remaining_s(self.mission_time)
        for threshold in (300.0, 120.0, 60.0):
            if remaining <= threshold and threshold not in self._mission_warnings:
                self._mission_warnings.add(threshold)
                minutes = int(threshold // 60)
                amount = minutes if minutes else 60
                suffix = "minutes" if minutes else "seconds"
                # Running out the clock wins a survive mission: announce the
                # remaining time as progress, not as a deadline.
                prefix = ("runtime.survive." if self.mission.win_mode == "survive"
                          else "runtime.deadline.")
                self.flash(message(prefix + "warning_" + suffix,
                                   amount=amount), 4.0)
                self.feed.add(self.world.format_time(), "mission",
                              message(prefix + "feed_" + suffix,
                                      amount=amount))

    # --- M6: Missions-Endbedingungen & Score ---

    def _torus_dist(self, x1, y1, x2, y2) -> float:
        """Legacy name; the generated world has hard, non-toroidal edges."""
        return math.hypot(x1 - x2, y1 - y2)

    def _check_mission_end(self) -> None:
        if self.mission_result is not None:
            return
        m = self.mission
        if self.damage.ship_sunk:
            self._end_mission(False, message("end.reason.frigate_sunk"))
            return
        if self.incident:
            self._end_mission(False, message("end.reason.incident"))
            return
        if m.win_mode == "sink":
            targets = [sub for sub in self.subs if sub.side == "hostile"]
            for sub in targets:
                if not sub.sunk and \
                        self._torus_dist(sub.x, sub.y, *sub.start_pos) > config.MISSION_ESCAPE_RADIUS_NM:
                    self._end_mission(False, message("end.reason.sub_escaped",
                                                     contact=sub.id))
                    return
            if all(sub.sunk for sub in targets):
                self._end_mission(True, message("end.reason.targets_sunk"))
                return
            if self.mission_time >= m.time_limit_s:
                self._end_mission(False, message("end.reason.time_limit"))
                return
        else:
            if self.mission_time >= m.time_limit_s:
                self._end_mission(True, message("end.reason.convoy_survived"))

    def _end_mission(self, win: bool, reason: object) -> None:
        self.mission_result = "SIEG" if win else "VERLOREN"
        self.result_reason = reason
        self.game_over = True
        self.input_mode = None
        self.input_buffer = ""
        self._clear_controls()
        if win:
            bonus = int(self.mission.remaining_s(self.mission_time)
                        / self.mission.time_limit_s * config.SCORE_TIME_BONUS_MAX)
            self.score += bonus + config.SCORE_AMMO_BONUS * self.torpedo_count
            if not self.incident:
                self.score += config.SCORE_CIVIL_BONUS
        self.announce(message("runtime.mission.won" if win
                              else "runtime.mission.lost"), "mission", 10.0)

    # --- M6: Speichern / Laden ---

    MAX_SAVED_ASMS = MAX_SAVED_ASMS
    MAX_SAVED_PLAYER_TORPEDOES = MAX_SAVED_PLAYER_TORPEDOES
    MAX_SAVED_ESSMS = MAX_SAVED_ESSMS

    def _reset_map_view(self) -> None:
        """Standard-Karte: Detail-Zoom, Kamera folgt der Fregatte."""
        self.map_view.set_rect(config.MAP_RECT)
        self.map_view.scale = config.MAP_ZOOM_DEFAULT_PX_PER_NM
        self.map_view.cx = self.ship.x
        self.map_view.cy = self.ship.y
        self.map_view.clamp_center()
        self.map_follow = True
        self._configure_opz_map_view()
        self.opz_map_view.scale = min(self.opz_map_view.rect[2],
                                      self.opz_map_view.rect[3]) / (
            2.0 * config.OPZ_MAP_DEFAULT_RADIUS_NM)
        self.opz_map_view.cx = self.ship.x
        self.opz_map_view.cy = self.ship.y
        self.opz_map_view.clamp_center()
        self.opz_map_follow = True

    def _configure_opz_map_view(self, chart=None) -> None:
        chart = pygame.Rect(chart or opz_ppi_rect(config.OPZ_STATION_RECT))
        self.opz_map_view.world_size = self.world.size_nm
        self.opz_map_view.set_rect(tuple(chart))
        self.opz_map_view.min_scale = min(chart.w, chart.h) / self.world.size_nm
        self.opz_map_view.max_scale = max(
            self.opz_map_view.min_scale, min(chart.w, chart.h) / (
                2.0 * config.OPZ_MAP_MAX_ZOOM_RADIUS_NM))
        self.opz_map_view.scale = config.clamp(
            self.opz_map_view.scale, self.opz_map_view.min_scale,
            self.opz_map_view.max_scale)

    def _reroll_menu_seed(self) -> None:
        """Choose a menu seed uniformly without repeating the current value."""
        import random

        upper = 1_000_000_000
        rng = random.SystemRandom()
        if self.world_mode == "real_fixed":
            # Change the mission seed while keeping the selected sector.
            sector = self.seed % 128
            low = 1 if sector == 0 else 0
            high = (upper - 1 - sector) // 128 + 1
            old_seed = self.seed
            candidate = rng.randrange(low, high - 1)
            if sector + 128 * candidate >= old_seed:
                candidate += 1
            self.seed = sector + 128 * candidate
            return
        if 1 <= self.seed < upper:
            candidate = rng.randrange(1, upper - 1)
            if candidate >= self.seed:
                candidate += 1
        else:
            candidate = rng.randrange(1, upper)
        self.seed = candidate

    def _start_menu_mission(self) -> None:
        """Consume an exact pristine menu preparation, otherwise replace it."""
        sc = config.SCENARIOS[self.scenario_key]
        candidate_difficulty = {**config.DEFAULT_DIFFICULTY,
                                **(sc["difficulty"] if sc["difficulty"] is not None
                                   else self.menu_difficulty)}
        prepared = (self.seed, self.scenario_key, self.world_mode,
                    tuple(candidate_difficulty[name]
                          for name in config.DIFFICULTY_FIELD_ORDER),
                    self.hq_intel_mode(), id(self.world), id(self.sonar))
        reuse = (self.in_menu and self._prepared_menu_mission == prepared
                 and self.sim_t == 0.0 and self.mission_time == 0.0
                 and self.custom_mission_definition is None
                 and self.mission_result is None and not self.game_over
                 and self.running)
        self._prepared_menu_mission = None
        self.in_menu = False
        self.main_menu = False
        if not reuse:
            self.reset(self.seed, self.scenario_key)
            return
        self._clear_controls()
        self.audio.stop()
        self.msg = ""
        self.msg_until = 0.0
        self._t = 0.0

    def _return_to_main_menu(self) -> None:
        """Leave the current mission (running or finished) without saving.

        The old world stays behind the menu until the next start replaces it;
        nothing is simulated while the menu owns the screen.
        """
        self._open_administration("none")
        self.quit_confirm = False
        self.simlog_view_open = False
        self.autocrew_overview_open = False
        self.weather_station_open = False
        self.feed_overlay_open = False
        self.pinned_tooltip = None
        self._tooltip_anchor = None
        self._reset_plot_ui()
        self.audio.stop()
        self._sonar_audio_sequence = -1
        self._prepared_menu_mission = None
        self._frame_clock_reset = True
        self.in_menu = True
        self.main_menu = True
        self.main_menu_sel = 0
        self.menu_screen = "scenario"
        self.menu_sel = 0

    def hq_intel_mode_menu(self) -> str:
        return (self.menu_hq_intel if self.menu_hq_intel in config.HQ_INTEL_MODES
                else "coarse")

    def _handle_menu_key(self, key) -> None:
        if key == pygame.K_f:
            self.toggle_fullscreen()
            return
        if key == pygame.K_w:
            self.world_mode = {"procedural": "fixed", "fixed": "real_fixed",
                               "real_fixed": "procedural"}[self.world_mode]
            return
        if self.world_mode == "real_fixed" and key in (pygame.K_PAGEUP, pygame.K_PAGEDOWN):
            delta = -1 if key == pygame.K_PAGEUP else 1
            sector = (self.seed % 128 + delta) % 128
            candidate = self.seed - self.seed % 128 + sector
            if candidate == 0:
                candidate += 128
            elif candidate >= 1_000_000_000:
                candidate -= 128
            self.seed = candidate
            return
        if key == pygame.K_r:
            self._reroll_menu_seed()
            return
        if self.main_menu:
            entries = ("new", "load", "mission_editor", "unit_editor",
                       "contact_analyzer", "options", "quit")
            if key == pygame.K_UP:
                self.main_menu_sel = (self.main_menu_sel - 1) % len(entries)
            elif key == pygame.K_DOWN:
                self.main_menu_sel = (self.main_menu_sel + 1) % len(entries)
            elif key in (pygame.K_RETURN, pygame.K_SPACE):
                action = entries[self.main_menu_sel]
                if action == "new":
                    # A new game first asks which unit the uConsole plays.
                    self.main_menu = False
                    self.menu_screen = "side"
                    self.menu_sel = 1 if self.local_side == "uboot" else 0
                elif action == "load":
                    self._open_administration("load")
                elif action == "mission_editor":
                    profiles = set(catalog_builtins(CATALOG))
                    self.editor = MissionEditor(tr=self.tr, profile_keys=profiles)
                elif action == "unit_editor":
                    self.editor = UnitEditor(catalog_builtins(CATALOG), tr=self.tr)
                elif action == "contact_analyzer":
                    self.editor = self._make_analyzer()
                elif action == "options":
                    self._open_administration("options")
                else:
                    self._open_administration("quit")
            elif key in (pygame.K_ESCAPE, pygame.K_q):
                self._open_administration("quit")
            return
        if self.menu_screen == "side":
            if key in (pygame.K_UP, pygame.K_DOWN, pygame.K_LEFT, pygame.K_RIGHT, pygame.K_TAB):
                self.menu_sel = 1 - self.menu_sel
            elif key in (pygame.K_1, pygame.K_2):
                self.menu_sel = 0 if key == pygame.K_1 else 1
            elif key in (pygame.K_RETURN, pygame.K_SPACE):
                self.local_side = ("frigate", "uboot")[self.menu_sel]
                self.menu_screen = "scenario"
                self.menu_sel = 0
            elif key in (pygame.K_ESCAPE, pygame.K_q):
                self.main_menu = True
                self.main_menu_sel = 0
            return
        if self.menu_screen == "scenario":
            n = len(config.SCENARIO_ORDER)
            if key == pygame.K_UP:
                self.menu_sel = (self.menu_sel - 1) % n
            elif key == pygame.K_DOWN:
                self.menu_sel = (self.menu_sel + 1) % n
            elif key in (pygame.K_1, pygame.K_2, pygame.K_3, pygame.K_4):
                self.menu_sel = {"1": 0, "2": 1, "3": 2, "4": 3} \
                    [pygame.key.name(key)]
            elif key in (pygame.K_RETURN, pygame.K_SPACE):
                self.scenario_key = config.SCENARIO_ORDER[self.menu_sel]
                sc = config.SCENARIOS[self.scenario_key]
                self.menu_screen = "difficulty" if sc["difficulty"] is None else "briefing"
                if self.menu_screen == "difficulty":
                    self.menu_sel = 0
            elif key in (pygame.K_ESCAPE, pygame.K_q):
                self.main_menu = True
                self.main_menu_sel = 0
            return
        if self.menu_screen == "difficulty":
            # The last row (after the saved difficulty fields) is the HQ intel.
            n = len(config.DIFFICULTY_FIELD_ORDER) + 1
            intel_row = self.menu_sel == n - 1
            if key == pygame.K_UP:
                self.menu_sel = (self.menu_sel - 1) % n
            elif key == pygame.K_DOWN:
                self.menu_sel = (self.menu_sel + 1) % n
            elif key in (pygame.K_LEFT, pygame.K_RIGHT) and intel_row:
                modes = config.HQ_INTEL_MODES
                self.menu_hq_intel = modes[(modes.index(self.hq_intel_mode_menu())
                                            + (1 if key == pygame.K_RIGHT else -1))
                                           % len(modes)]
            elif key in (pygame.K_LEFT, pygame.K_RIGHT):
                name = config.DIFFICULTY_FIELD_ORDER[self.menu_sel]
                kind, low, high, step, _default = config.DIFFICULTY_FIELDS[name]
                delta = step * (1 if key == pygame.K_RIGHT else -1)
                value = config.clamp(self.menu_difficulty[name] + delta, low, high)
                self.menu_difficulty[name] = (
                    int(round(value)) if kind is int else round(value, 6))
            elif key in (pygame.K_RETURN, pygame.K_SPACE):
                self.scenario_key = "s4_zufall"
                self._start_menu_mission()
            elif key == pygame.K_ESCAPE:
                self.menu_screen = "scenario"
                self.menu_sel = 3
            return
        # briefing
        if key in (pygame.K_RETURN, pygame.K_SPACE):
            self._start_menu_mission()
        elif key == pygame.K_ESCAPE:
            self.menu_screen = "scenario"

    @localized
    def draw_menu(self) -> None:
        """W4: Szenario -> (Level bei s4) -> Briefing -> Start."""
        s = self.screen
        s.fill(config.COLOR_BG)
        cx = config.SCREEN_W // 2

        def center(text: str, y: int, font=None, color=config.COLOR_TEXT) -> None:
            f = font or self.menu_font
            text = localize(text)
            surf = f.render(text, True, color)
            s.blit(surf, surf.get_rect(center=(cx, y)))

        center("U-JAGD – FREGATTE F-217", 100, self.menu_font_big)

        if self.main_menu:
            labels = ("menu.new_game", "menu.load", "menu.mission_editor",
                      "menu.unit_editor", "menu.contact_analyzer", "option.title",
                      "menu.quit")
            for i, key in enumerate(labels):
                marker = "> " if i == self.main_menu_sel else "  "
                color = config.COLOR_TEXT if i == self.main_menu_sel else config.COLOR_TEXT_DIM
                center(message("menu.choice", marker=marker,
                               label=self.tr(key).upper()), 185 + i * 47, color=color)
        elif self.menu_screen == "side":
            center(self.tr("menu.choose_side"), 170, color=config.COLOR_TEXT_DIM)
            for i, side in enumerate(("frigate", "uboot")):
                selected = i == self.menu_sel
                center(message("menu.choice", marker="► " if selected else "  ",
                               label=self.tr(f"menu.side.{side}")),
                       250 + i * 90, self.menu_font_big if selected else None,
                       config.COLOR_TEXT if selected else config.COLOR_TEXT_DIM)
                layout.blit_line(s, f"menu.side.{side}.note", (cx - 420, 285 + i * 90, 840, 26),
                                 config.COLOR_TEXT_DIM, size=18, align="center")
            center(self.tr("menu.side_hint"), 470, color=config.COLOR_TEXT_DIM)
        elif self.menu_screen == "scenario":
            center(self.tr("menu.choose_scenario"),
                   150, color=config.COLOR_TEXT_DIM)
            scenario_names = {"s1_patrouille": "patrol", "s2_doppeljagd": "double",
                              "s3_abfang": "intercept", "s4_zufall": "random"}
            for i, key in enumerate(config.SCENARIO_ORDER):
                sc = config.SCENARIOS[key]
                marker = "► " if i == self.menu_sel else "  "
                col = config.COLOR_TEXT if i == self.menu_sel \
                    else config.COLOR_TEXT_DIM
                lv = self.tr("menu.difficulty_fixed" if sc["difficulty"] is not None
                             else "menu.difficulty_custom")
                title = self.tr("scenario." + scenario_names[key] + ".title")
                center(message("menu.scenario_choice", index=i + 1,
                               marker=marker, title=title, level=lv),
                       240 + i * 40, color=col)
        elif self.menu_screen == "difficulty":
            center(self.tr("menu.choose_difficulty"),
                   150, color=config.COLOR_TEXT_DIM)
            row_h = 26
            for i, name in enumerate(config.DIFFICULTY_FIELD_ORDER):
                kind, _low, _high, _step, _default = config.DIFFICULTY_FIELDS[name]
                marker = "► " if i == self.menu_sel else "  "
                col = config.COLOR_TEXT if i == self.menu_sel \
                    else config.COLOR_TEXT_DIM
                value = self.menu_difficulty[name]
                value_text = (str(value) if kind is int
                             else f"{value:.3f}".rstrip("0").rstrip("."))
                center(message("menu.difficulty_choice", marker=marker,
                               label=self.tr("difficulty." + name),
                               value=value_text),
                       190 + i * row_h, color=col)
            i = len(config.DIFFICULTY_FIELD_ORDER)
            selected = i == self.menu_sel
            center(message("menu.difficulty_choice",
                           marker="► " if selected else "  ",
                           label=self.tr("menu.hq_intel"),
                           value=self.tr("menu.hq_intel." + self.hq_intel_mode_menu())),
                   190 + i * row_h,
                   color=config.COLOR_TEXT if selected else config.COLOR_TEXT_DIM)
        else:  # briefing
            sc = config.SCENARIOS[self.scenario_key]
            scenario_key = {"s1_patrouille": "patrol", "s2_doppeljagd": "double",
                            "s3_abfang": "intercept", "s4_zufall": "random"}[self.scenario_key]
            center(self.tr("scenario." + scenario_key + ".title"), 170,
                   self.menu_font_big, config.COLOR_WARN)
            layout.blit_block(s, self.tr("scenario." + scenario_key + ".brief"),
                              cx - 420, 210, 840, 180,
                              color=config.COLOR_TEXT, size=20)
            if sc["win_text"]:
                center(message("menu.goal_value",
                               goal=self.tr("scenario." + scenario_key + ".win")),
                       420, color=config.COLOR_OK)
            if sc["lose_text"]:
                center(message("menu.loss_value",
                               loss=self.tr("scenario." + scenario_key + ".lose")), 448,
                       color=config.COLOR_DANGER)
            center(self.tr("menu.start_hint"), 520,
                   color=config.COLOR_TEXT_DIM)
            center(message("menu.local_side", side=message(
                "menu.local_side.uboot" if self.local_side == "uboot"
                else "menu.local_side.frigate")), 556,
                color=config.COLOR_WARN if self.local_side == "uboot"
                else config.COLOR_TEXT_DIM)

        if self.world_mode in ("procedural", "real_fixed"):
            from src.world.real_coast import sector_for_seed
            sector, _ = sector_for_seed(self.seed)
            world_label = sector["name"]
            if self.world_mode == "real_fixed":
                center(self.tr("menu.real_fixed_hint", sector=sector["id"]),
                       config.SCREEN_H - 95, color=config.COLOR_TEXT_DIM)
        else:
            world_label = self.tr("menu.fixed_chart")
        center(self.tr("menu.world_status", world=world_label, seed=self.seed),
               config.SCREEN_H - 68, color=config.COLOR_OK)
        center(self.tr("menu.seed_fullscreen", seed=self.seed,
                       action=self.tr("menu.windowed" if self.fullscreen
                                      else "menu.fullscreen")),
               config.SCREEN_H - 40, color=config.COLOR_TEXT_DIM)

    # --- W0: Draw-Grid ---

    @property
    def _station_overlay_open(self) -> bool:
        """A full-station overlay (F3 autocrew, 0 weather) replaces the station."""
        return self.autocrew_overview_open or self.weather_station_open

    @localized
    def _eco_display_active(self) -> bool:
        """Solo browser is live: the uConsole shows a cheap status screen.

        Pure display decision; it never touches simulation state, saves or input.
        """
        return (self.running and not self.splash_active and self.editor is None
                and not self.simlog_view_open and not self.in_menu
                and not self.main_menu and not self.administration_open
                and not self.game_over and not self._station_overlay_open
                and self.commander.eco_display_ready(self))

    def _skip_eco_frame(self) -> bool:
        """True while the last eco frame is still current (draw and blit skipped)."""
        if not self._eco_display_active():
            self._eco_drawn_at = float("-inf")
            return False
        if self._t - self._eco_drawn_at < config.ECO_REDRAW_S:
            return True
        self._eco_drawn_at = self._t
        return False

    @localized
    def draw_eco_display(self) -> None:
        s = self.screen
        panel = pygame.Rect(240, 90, 800, 360)
        layout.panel(s, panel)
        x, w = panel.x + 24, panel.w - 48
        layout.blit_line(s, "eco.title", (x, panel.y + 16, w, 36),
                         config.COLOR_WARN, size=28, align="center")
        layout.blit_block(s, "eco.subtitle", x, panel.y + 66, w, 66,
                          config.COLOR_TEXT, size=20, align="center", valign="center")
        address = getattr(self.commander, "address", None)
        if address is not None:
            url = raw_text(f"http://{address[0]}:{address[1]}/")
            proxy = getattr(self.commander, "public_origin", None)
            layout.blit_line(s, message("commander.local.url_proxy", url=url,
                                        proxy=raw_text(proxy + "/"))
                             if proxy else message("commander.local.url", url=url),
                (x, panel.y + 150, w, 32), config.COLOR_TEXT, size=22, align="center")
        layout.blit_line(s, message(
            "eco.state.running", time=raw_text(self.world.format_time())),
            (x, panel.y + 200, w, 32), config.COLOR_OK,
            size=24, align="center")
        layout.blit_line(s, "eco.hint", (x, panel.bottom - 56, w, 30),
                         config.COLOR_TEXT_DIM, size=16, align="center")

    def draw(self) -> None:
        # One translation scope for the whole frame: text drawn directly here
        # (flash banner, overlays) must follow the game language, not the
        # process-wide default translator.
        with layout.bottom_panel_regions(self.bottom_panel_mode()), \
                translation_scope(self.tr):
            self._draw()

    def _draw(self) -> None:
        self._apply_text_size()
        s = self.screen
        eco = self._eco_display_active()
        s.fill(config.COLOR_BG)
        if self.splash_active:
            draw_splash(s, self._t - self.splash_started_at, self.tr)
        elif self.editor is not None:
            self.editor.draw(s)
            if isinstance(self.editor, MissionEditor) and self.editor.mode == "browser":
                hint = self.font.render(localize("F5: start selected runtime-compatible mission"),
                                        True, config.COLOR_OK)
                s.blit(hint, (config.SCREEN_W - hint.get_width() - 20,
                              config.SCREEN_H - 68))
        elif self.simlog_view_open:
            draw_simlog_view(self)
        elif self.in_menu:
            self.draw_menu()
        elif self.local_side == "uboot":
            uboot_view.draw(self)
        elif eco:
            self.draw_top_bar()
            self.draw_eco_display()
            self.draw_bottom_panel()
        else:
            self.draw_top_bar()
            map_station = (not self._station_overlay_open
                           and self._map_station_visible())
            previous_rect = config.STATION_RECT
            try:
                config.STATION_RECT = (config.STATION_PANEL_RECT if map_station else
                                       # The weather panel takes the whole
                                       # screen below the top bar.
                                       config.OPZ_STATION_RECT
                                       if self.weather_station_open
                                       or (self.station is Station.OPZ
                                           and not self._station_overlay_open) else
                                       config.FULL_STATION_RECT)
                if self.autocrew_overview_open:
                    with layout.clip_to(s, config.STATION_RECT):
                        draw_autocrew_overview(self)
                elif self.weather_station_open:
                    with layout.clip_to(s, config.STATION_RECT):
                        draw_weather_station(self)
                elif map_station:
                    draw_map_view(self)
                    if self.station is Station.WEAPONS:
                        draw_weapons_overlay(self)
                if not self._station_overlay_open:
                    with layout.clip_to(s, config.STATION_RECT):
                        if self.station is Station.SONAR:
                            draw_sonar_view(self)
                        elif self.station is Station.WEAPONS:
                            draw_weapons_panel(self)
                        elif self.station is Station.DAMAGE:
                            draw_damage_view(self)
                        elif self.station is Station.OPZ:
                            draw_opz_view(self)
                        elif self.station is Station.RADIO:
                            draw_radio_view(self)
                        elif self.station is Station.ENGINE:
                            draw_engine_view(self)
                        elif self.station is Station.HELICOPTER:
                            draw_helicopter_view(self)
                        elif self.station is Station.ELOKA:
                            draw_eloka_view(self)
                        else:
                            draw_bridge_view(self)
                if (self.station is not Station.OPZ and not self.weather_station_open
                        and not self.feed_overlay_open):
                    self.draw_bottom_panel()
                if self.feed_overlay_open:
                    self.draw_feed_overlay()
                self.draw_navigation_input()
                if self.game_over:
                    self.draw_end_panel()
            finally:
                config.STATION_RECT = previous_rect
        if self.quit_confirm:
            self.draw_quit_overlay()
        elif self.help_open:
            self.draw_help_overlay()
        elif self.nations_open:
            self.draw_nations_overlay()
        elif self.save_ui is not None:
            self.draw_save_ui()
        elif self.options_open:
            self.draw_options_overlay()
        elif self.live_traffic_open:
            self.draw_live_traffic_overlay()
        elif self.commander_open:
            self.commander.draw(self)
        self.commander.draw_confirm(self)
        if self.msg and self._t < self.msg_until:
            self._draw_flash_banner(s)
        if (not self.in_menu and not self.splash_active and self.editor is None
                and not self.simlog_view_open and not self._station_overlay_open
                and self.tooltips_enabled and not eco
                and self.local_side != "uboot"
                and not self.administration_open and not self.game_over):
            canvas = self._window_to_canvas(pygame.mouse.get_pos())
            payload = self.pinned_tooltip or self.tooltip_at(canvas)
            anchor = self._tooltip_anchor if self.pinned_tooltip else canvas
            if payload is not None and anchor is not None:
                layout.draw_tooltip(s, payload, anchor,
                                    (0, 0, config.SCREEN_W, config.SCREEN_H))
        if self._scanlines is not None:
            s.blit(self._scanlines, (0, 0))
        if self.preferences.night_mode:
            s.blit(self._night_overlay, (0, 0), special_flags=pygame.BLEND_MULT)

    @localized
    def draw_navigation_input(self) -> None:
        """Show the active numeric command without hiding the simulation."""
        if self.input_mode is None:
            return
        label = self.tr("input." + self.input_mode)
        rect = pygame.Rect(280, 88, 720, 70)
        pygame.draw.rect(self.screen, config.COLOR_OVERLAY_BG, rect)
        pygame.draw.rect(self.screen, config.COLOR_WARN, rect, 2)
        layout.blit_line(self.screen, self.tr("input.value", label=label,
                                              value=self.input_buffer),
                         (rect.x + 14, rect.y + 8, rect.w - 28, 26),
                         config.COLOR_TEXT, size=20)
        layout.blit_line(self.screen, self.tr("input.hint"),
                         (rect.x + 14, rect.y + 38, rect.w - 28, 22),
                         config.COLOR_TEXT_DIM, size=14)

    @localized
    def top_bar_scenario(self) -> str:
        """Mission title shown in the top status bar."""
        if self.custom_mission_definition is not None:
            return localize(self.mission_name_display())
        return self.tr("scenario." + {"s1_patrouille": "patrol", "s2_doppeljagd": "double",
                                      "s3_abfang": "intercept", "s4_zufall": "random"}
                       [self.scenario_key] + ".title")

    def draw_top_bar(self) -> None:
        layout.configure_for(self)
        s = self.screen
        pygame.draw.rect(s, config.COLOR_PANEL_BG, (0, 0, config.SCREEN_W, config.TOP_BAR_H))
        pygame.draw.line(s, config.COLOR_SONAR_RING,
                         (0, config.TOP_BAR_H - 1),
                         (config.SCREEN_W, config.TOP_BAR_H - 1), 1)
        station = display_value("station", self.station.name, self.tr).upper()
        scenario = self.top_bar_scenario()
        txt = self.tr("top.status", station=station, scenario=scenario,
                      time=self.world.format_time(), speed=f"{self.ship.speed:4.1f}",
                      course=f"{self.ship.course:4.0f}")
        layout.blit_line(s, txt, (10, 4, config.SCREEN_W - 20,
                                  config.TOP_BAR_H - 8),
                         config.COLOR_TEXT, size=18)
        self._top_status_right = 10 + layout.font(layout.scaled_size(18)).size(
            localize(txt))[0]

    def draw_bottom_panel(self, entries=None, rows=None, heading="feed.heading",
                          ticker_keys=None, ticker_hint="ticker.hint") -> None:
        """Event feed and telemetry: docked band or one status ticker.

        ``entries``/``rows`` replace the frigate's feed and telemetry (the
        crewed submarine's own log and readings use the same band).
        """
        if self.bottom_panel_mode() == "ticker":
            self.draw_status_ticker(entries, rows, ticker_keys, ticker_hint)
        else:
            self.draw_bottom_feed(entries, heading)
            self.draw_bottom_telemetry(rows)

    def _feed_lines(self, width: int, face, entries=None) -> list:
        """Wrap feed entries (oldest first) into (text, colour, is_first) rows.

        Entries wrap onto continuation lines under the text column; nothing
        is ever cut off with an ellipsis.
        """
        rows = []
        for entry in self.feed.entries if entries is None else entries:
            prefix = f"[{entry.stamp}] {entry.tag():4s} "
            indent = face.size(prefix)[0]
            wrapped = layout.wrap_text(localize(entry.text), face,
                                       max(40, width - indent)) or [""]
            rows.append((prefix, wrapped[0], entry.color(), indent))
            rows.extend(("", line, entry.color(), indent) for line in wrapped[1:])
        return rows

    def _blit_feed_rows(self, rect, rows, scroll: int = 0) -> None:
        """Draw wrapped feed rows bottom-up (newest at the bottom)."""
        face = layout.font(16)
        pitch = layout._line_height(face)
        visible = max(1, rect.h // pitch)
        end = max(0, len(rows) - scroll)
        shown = rows[max(0, end - visible):end]
        y = rect.bottom - len(shown) * pitch
        with layout.clip_to(self.screen, rect):
            for prefix, text, color, indent in shown:
                if prefix:
                    layout.blit_line(self.screen, raw_text(prefix),
                                     (rect.x, y, indent, pitch),
                                     config.COLOR_TEXT_DIM, size=16)
                layout.blit_line(self.screen, raw_text(text),
                                 (rect.x + indent, y, rect.w - indent, pitch),
                                 color, size=16)
                y += pitch

    @localized
    def draw_bottom_feed(self, entries=None, heading="feed.heading") -> None:
        s = self.screen
        x, y, w, h = config.FEED_RECT
        pygame.draw.rect(s, config.COLOR_FEED_BG, (x, y, w, h))
        pygame.draw.rect(s, config.COLOR_SONAR_RING, (x, y, w, h), 1)
        layout.blit_line(s, heading, (x + 8, y + 3, w - 16, 20),
                         config.COLOR_TEXT_DIM, size=16)
        body = pygame.Rect(x + 8, y + 25, w - 16, h - 29)
        face = layout.font(16)
        self._blit_feed_rows(body, self._feed_lines(body.w, face, entries))

    @localized
    def draw_bottom_telemetry(self, rows=None) -> None:
        s = self.screen
        x, y, w, h = config.TELEMETRY_RECT
        pygame.draw.rect(s, config.COLOR_FEED_BG, (x, y, w, h))
        pygame.draw.rect(s, config.COLOR_SONAR_RING, (x, y, w, h), 1)
        layout.blit_line(s, "panel.telemetry", (x + 8, y + 3, w - 16, 20),
                         config.COLOR_TEXT_DIM, size=16)
        self._blit_telemetry_rows(pygame.Rect(x + 8, y + 25, w - 16, h - 29),
                                  short=True, rows=rows)

    def _blit_telemetry_rows(self, rect, short: bool, rows=None) -> None:
        face = layout.font(16)
        rows = observations.telemetry_rows(self) if rows is None else rows
        pitch = max(layout._line_height(face), rect.h // max(1, len(rows)))
        labels = [localize(observations.telemetry_label(key, short))
                  for key, *_rest in rows]
        label_w = max(face.size(label)[0] for label in labels) + 10
        colors = {"ok": config.COLOR_TEXT, "warn": config.COLOR_WARN,
                  "danger": config.COLOR_DANGER}
        for index, ((_key, value, level, _compact), label) in enumerate(zip(rows, labels)):
            y = rect.y + index * pitch
            layout.blit_line(self.screen, raw_text(label), (rect.x, y, label_w, pitch),
                             config.COLOR_TEXT_DIM, size=16)
            layout.blit_line(self.screen, value, (rect.x + label_w, y,
                                                  rect.w - label_w, pitch),
                             colors[level], size=16)

    def _ticker_telemetry_text(self, width: int | None = None, rows=None,
                               keys=None) -> str:
        """Compact telemetry for the ticker, most important readings first.

        Readings that do not fit are left out whole (never clipped); the
        F11 overlay always shows all of them.
        """
        parts = []
        keys = observations.TICKER_KEYS if keys is None else keys
        rows = observations.telemetry_rows(self) if rows is None else rows
        for key, _value, _level, compact in rows:
            if key in keys:
                label = observations.telemetry_label(key, short=True)
                parts.append(f"{localize(label)} {localize(compact)}")
        face = layout.font(16)
        while width is not None and len(parts) > 1 and face.size(
                " \u00b7 ".join(parts))[0] > width:
            parts.pop()
        return " \u00b7 ".join(parts)

    @localized
    def draw_status_ticker(self, entries=None, rows=None, keys=None,
                           hint_key="ticker.hint") -> None:
        """One 22 px strip: newest event (scrolls if long) + key telemetry."""
        s = self.screen
        rect = layout.ticker_rect()
        pygame.draw.rect(s, config.COLOR_FEED_BG, rect)
        pygame.draw.line(s, config.COLOR_SONAR_RING, rect.topleft, rect.topright, 1)
        face = layout.font(16)
        rows = observations.telemetry_rows(self) if rows is None else rows
        telemetry = self._ticker_telemetry_text(int(rect.w * .6) - 16, rows, keys)
        level = ("danger" if any(row[2] == "danger" for row in rows)
                 else "warn" if any(row[2] == "warn" for row in rows) else "ok")
        colors = {"ok": config.COLOR_TEXT, "warn": config.COLOR_WARN,
                  "danger": config.COLOR_DANGER}
        tele_w = face.size(telemetry)[0] + 16
        tele_rect = pygame.Rect(rect.right - tele_w, rect.y + 2, tele_w - 8, rect.h - 2)
        layout.blit_line(s, raw_text(telemetry), tele_rect, colors[level],
                         size=16, align="right")
        hint = localize(hint_key) if hint_key else ""
        hint_w = face.size(hint)[0] + 12 if hint else 0
        if hint:
            layout.blit_line(s, raw_text(hint), (rect.x + 6, rect.y + 2, hint_w, rect.h - 2),
                             config.COLOR_TEXT_DIM, size=16)
        feed_rect = pygame.Rect(rect.x + 6 + hint_w, rect.y + 2,
                                tele_rect.x - 12 - (rect.x + 6 + hint_w), rect.h - 2)
        latest = self.feed.recent(1) if entries is None else list(entries)[-1:]
        if not latest or feed_rect.w <= 20:
            return
        entry = latest[0]
        text = f"[{entry.stamp}] {entry.tag()} {localize(entry.text)}"
        width = face.size(text)[0]
        with layout.clip_to(s, feed_rect):
            if width <= feed_rect.w:
                layout.blit_line(s, raw_text(text), feed_rect, entry.color(), size=16)
            else:
                # Marquee instead of an ellipsis: the full line stays readable.
                gap = 60
                offset = int(self._t * config.TICKER_SCROLL_PX_S) % (width + gap)
                surface = layout.font(16).render(text, True, entry.color())
                s.blit(surface, (feed_rect.x - offset, feed_rect.y))
                s.blit(surface, (feed_rect.x - offset + width + gap, feed_rect.y))

    def feed_overlay_rect(self) -> pygame.Rect:
        return pygame.Rect(0, config.SCREEN_H - 330, config.SCREEN_W, 330)

    @localized
    def draw_feed_overlay(self) -> None:
        """F11: full event history and telemetry over the station (display only)."""
        s = self.screen
        rect = self.feed_overlay_rect()
        shade = pygame.Surface(rect.size, pygame.SRCALPHA)
        shade.fill((*config.COLOR_FEED_BG, 238))
        s.blit(shade, rect.topleft)
        pygame.draw.rect(s, config.COLOR_WARN, rect, 1)
        tele_w = 360
        feed = pygame.Rect(rect.x + 10, rect.y + 30, rect.w - tele_w - 30, rect.h - 40)
        tele = pygame.Rect(rect.right - tele_w - 10, rect.y + 30, tele_w, rect.h - 40)
        face = layout.font(16)
        rows = self._feed_lines(feed.w, face)
        visible = max(1, feed.h // layout._line_height(face))
        self.feed_overlay_scroll = max(0, min(self.feed_overlay_scroll,
                                              len(rows) - visible))
        layout.blit_line(s, message("feed.overlay.title",
                                    shown=min(len(rows), visible), total=len(rows)),
                         (rect.x + 10, rect.y + 5, feed.w, 22), config.COLOR_WARN,
                         size=16)
        layout.blit_line(s, "panel.telemetry", (tele.x, rect.y + 5, tele.w, 22),
                         config.COLOR_WARN, size=16)
        self._blit_feed_rows(feed, rows, self.feed_overlay_scroll)
        pygame.draw.line(s, config.COLOR_SONAR_RING, (tele.x - 10, feed.y),
                         (tele.x - 10, feed.bottom), 1)
        self._blit_telemetry_rows(pygame.Rect(tele.x, tele.y, tele.w, 7 * 26),
                                  short=False)
        layout.blit_block(s, "feed.overlay.hint", tele.x, tele.bottom - 44, tele.w,
                          44, config.COLOR_TEXT_DIM, size=16)

    def _help_lines(self) -> tuple[list[str], int]:
        """Wrap before scrolling so every line remains reachable at either size."""
        layout.configure_for(self)
        intro, keys, params, tactics = get_help(self.station, self.tr)
        face = layout.font(18)
        visible = max(1, 500 // layout._line_height(face))
        if self.help_page == HELP_MANUAL_PAGE:
            chapter = manual.CHAPTERS[self.help_manual_chapter % len(manual.CHAPTERS)]
            blocks = manual.chapter_blocks(chapter, manual.manual_language(self.tr))
            width = max(20, 960 // max(1, face.size("M")[0]))
            # Leading blanks survive word wrapping only as no-break spaces.
            lines = [line[:len(line) - len(line.lstrip(" "))].replace(" ", "\u00a0")
                     + line.lstrip(" ") for line in manual.text_lines(blocks, width)]
            return lines, visible
        if self.help_page == 0:
            title, bindings = get_global_help(self.tr)
            text = title + "\n\n" + "\n".join(f"{k:<18} {a}" for k, a in bindings)
        elif self.help_page == 1 and self.local_side == "uboot":
            title, bindings = get_uboot_help(self.tr)
            text = title + "\n\n" + "\n".join(f"{k:<18} {a}" for k, a in bindings)
        elif self.help_page == 1:
            sop = get_sop(self.station, self.tr)
            text = (intro + "\n\n" + "\n".join(f"{k:<18} {a}" for k, a in keys)
                    + "\n\n" + self.tr("help.sop.title") + "\n"
                    + "\n".join(f"{n}. {step}" for n, step in enumerate(sop, 1)))
        else:
            text = self.tr("help.sensors_tactics") + "\n\n" + "\n\n".join(params + tactics)
        return layout.wrap_text(text, face, 960), visible

    @localized
    def draw_help_overlay(self) -> None:
        layout.configure_for(self)
        s = self.screen
        dim = pygame.Surface((config.SCREEN_W, config.SCREEN_H), pygame.SRCALPHA)
        dim.fill((0, 0, 0, 170))
        s.blit(dim, (0, 0))
        bw, bh = 1000, 620
        bx = (config.SCREEN_W - bw) // 2
        by = (config.SCREEN_H - bh) // 2
        pygame.draw.rect(s, config.COLOR_PANEL_BG, (bx, by, bw, bh))
        pygame.draw.rect(s, config.COLOR_SONAR_RING, (bx, by, bw, bh), 2)
        help_title = self.tr("help.title", station=display_value(
            "station", self.station.name, self.tr).upper())
        layout.blit_line(s, help_title, (bx + 18, by + 10, bw - 36, 40),
                         config.COLOR_TEXT, size=30)
        x = bx + 20
        w = bw - 40
        y = by + 52
        lines, visible = self._help_lines()
        scroll = min(getattr(self, "help_scroll", 0), max(0, len(lines) - visible))
        body = "\n".join(lines[scroll:scroll + visible])
        if self.help_page == HELP_MANUAL_PAGE:
            body = raw_text(body)
            hint = self.tr("help.manual.hint",
                           chapter=self.help_manual_chapter % len(manual.CHAPTERS) + 1,
                           chapters=len(manual.CHAPTERS), first=scroll + 1,
                           last=min(len(lines), scroll + visible), total=len(lines))
        else:
            hint = self.tr("control.help.scroll_hint", page=self.help_page + 1,
                           pages=HELP_PAGE_COUNT, first=scroll + 1,
                           last=min(len(lines), scroll + visible), total=len(lines))
        layout.blit_block(s, body, x, y, w, 500, config.COLOR_TEXT, size=18, min_size=18)
        layout.blit_block(s, hint, x, by + bh - 62, w, 54, config.COLOR_TEXT_DIM, size=16)

    @localized
    def draw_nations_overlay(self) -> None:
        s = self.screen
        dim = pygame.Surface((config.SCREEN_W, config.SCREEN_H), pygame.SRCALPHA)
        dim.fill((0, 0, 0, 160))
        s.blit(dim, (0, 0))
        bw, bh = 1100, 620
        bx = (config.SCREEN_W - bw) // 2
        by = (config.SCREEN_H - bh) // 2
        pygame.draw.rect(s, config.COLOR_PANEL_BG, (bx, by, bw, bh))
        pygame.draw.rect(s, config.COLOR_SONAR_RING, (bx, by, bw, bh), 2)
        layout.blit_line(s, "panel.nations", (bx + 18, by + 12, bw - 36, 38),
                         config.COLOR_TEXT, size=30)
        summary = getattr(self, "_nations_summary", None)
        if summary is None:
            summary = reference_summary(self.world.coast, self.runtime_catalog)
            self._nations_summary = summary
        legacy_country_names = {
            "HANSE": "nations.country.hanse",
            "BOREN": "nations.country.boren",
            "SKANDIA": "nations.country.skandia",
        }
        countries = ", ".join(self.tr(legacy_country_names[c])
                              if c in legacy_country_names else c
                              for c in summary["countries"]) or self.tr("nations.none")
        cards = (
            ("nations.area", self.tr("nations.countries", countries=countries)
             + "\n\n" + self.tr("nations.reference_note"), config.COLOR_FLIGHT),
            ("nations.friendly", "\n".join(summary["friendly"]), config.COLOR_OK),
            ("nations.hostile", self.tr("nations.subs", count=len(summary["hostile_subs"]))
             + "\n" + ", ".join(summary["hostile_subs"])
             + "\n\n" + self.tr("nations.surfaces", count=len(summary["hostile_surfaces"]))
             + "\n" + ", ".join(summary["hostile_surfaces"]), config.COLOR_DANGER),
            ("nations.other", self.tr("nations.neutral_military", count=summary["neutral_military"])
             + "\n\n" + self.tr("nations.civilian", count=summary["civilian"])
             + "\n\n" + self.tr("nations.catalog_hint"), config.COLOR_CONTACT_ZIVIL),
        )
        cw, ch = 520, 260
        for i, (title, body, color) in enumerate(cards):
            cx = bx + 18 + (i % 2) * (cw + 14)
            cyy = by + 52 + (i // 2) * (ch + 12)
            pygame.draw.rect(s, config.COLOR_PANEL_BG, (cx, cyy, cw, ch))
            pygame.draw.rect(s, color, (cx, cyy, cw, ch), 1)
            layout.blit_line(s, title, (cx + 12, cyy + 8, cw - 24, 36), color, size=24)
            layout.blit_block(s, body, cx + 12, cyy + 50, cw - 24, ch - 58,
                              color=config.COLOR_TEXT, size=18)
        layout.blit_line(s, "nations.close", (bx + bw - 160, by + bh - 30, 140, 24),
                         config.COLOR_TEXT_DIM, size=16, align="right")

    @localized
    def draw_save_ui(self) -> None:
        s = self.screen
        mode = self.tr("common.save" if self.save_ui == "save" else "common.load").upper()
        dim = pygame.Surface((config.SCREEN_W, config.SCREEN_H), pygame.SRCALPHA)
        dim.fill((0, 0, 0, 150))
        s.blit(dim, (0, 0))
        bw, bh = 660, 380
        bx = (config.SCREEN_W - bw) // 2
        by = (config.SCREEN_H - bh) // 2
        pygame.draw.rect(s, config.COLOR_PANEL_BG, (bx, by, bw, bh))
        pygame.draw.rect(s, config.COLOR_SONAR_RING, (bx, by, bw, bh), 2)
        layout.blit_line(s, self.tr("save.title", mode=mode),
                         (bx + 18, by + 14, bw - 36, 34), config.COLOR_TEXT, size=22)
        ly = by + 70
        for slot in range(1, 6):
            info = self.save_info[slot - 1] if len(self.save_info) == 5 else "--"
            selected = slot == self.save_slot
            col = config.COLOR_WARN if selected else config.COLOR_TEXT_DIM
            layout.blit_line(s, message("save.slot", marker=">" if selected else " ",
                                         slot=slot, info=localize(info)),
                             (bx + 24, ly, bw - 48, 32), col, size=19)
            ly += 42
        hint = "save.live"
        if self.save_confirm:
            hint = ("save.overwrite" if self.save_ui == "save"
                    else "save.replace")
        layout.blit_line(s, hint, (bx + 18, by + bh - 54, bw - 36, 34),
                         config.COLOR_WARN, size=18)

    @localized
    def draw_end_panel(self) -> None:
        """M8: Endpanel mit Score-Bruchrechnung und Hinweisen."""
        s = self.screen
        dim = pygame.Surface((config.SCREEN_W, config.SCREEN_H), pygame.SRCALPHA)
        dim.fill((0, 0, 0, 140))
        s.blit(dim, (0, 0))
        w, h = 700, 340
        x = (config.SCREEN_W - w) // 2
        y = (config.SCREEN_H - h) // 2
        pygame.draw.rect(s, (12, 26, 18), (x, y, w, h))
        pygame.draw.rect(s, config.COLOR_TEXT_DIM, (x, y, w, h), 2)
        col = config.COLOR_OK if self.mission_result == "SIEG" else config.COLOR_DANGER
        result = self.tr("end.victory" if self.mission_result == "SIEG"
                         else "end.defeat")
        lines = [
            (message("end.result", result=result,
                     reason=localize(self.result_reason)), col, True),
            ("", config.COLOR_TEXT, False),
            (message("end.score_value", score=self.score), config.COLOR_TEXT, True),
            (message("end.mission_level", mission=self.mission_name_display(),
                     level=self.mission_level_display()),
             config.COLOR_TEXT_DIM, False),
            (message("end.time_remaining",
                     remaining=self.mission.format_remaining(self.mission_time))
             if (self.mission_result == "SIEG"
                 or self.mission_time < self.mission.time_limit_s)
             else "end.expired",
             config.COLOR_TEXT_DIM, False),
            ("", config.COLOR_TEXT, False),
            ("end.restart", config.COLOR_TEXT_DIM, False),
        ]
        ly = y + 44
        for text, c, big in lines:
            if not text:
                ly += 16
                continue
            size = 26 if big else 20
            height = 36 if big else 26
            layout.blit_line(s, text, (x + 16, ly, w - 32, height), c,
                             size=size, align="center")
            ly += 42 if big else 30

    @staticmethod
    def _options_row_rects():
        return tuple(pygame.Rect(292, 118 + index * 40, 696, 36)
                     for index in range(max(len(page) for page in Game._OPTION_PAGES)))

    @staticmethod
    def _options_page_rects():
        """Clickable page tabs left and right of the options title."""
        return tuple(pygame.Rect(292 + index * 590, 70, 106, 36)
                     for index in range(len(Game._OPTION_PAGES)))

    def _option_rows(self) -> tuple:
        page = self.options_page if 0 <= self.options_page < len(self._OPTION_PAGES) else 0
        return self._OPTION_PAGES[page]

    def _set_options_page(self, page: int) -> None:
        self.options_page = page % len(self._OPTION_PAGES)
        self.options_sel = 0

    def local_side_locked(self) -> bool:
        """The uConsole's side is chosen outside a mission only."""
        return not self.in_menu

    def _toggle_local_side(self) -> None:
        if not self.local_side_locked():
            uboot_local.toggle_side(self)

    @localized
    def draw_options_overlay(self) -> None:
        # Panel/row geometry is sized so the footer hint always starts below
        # the last row with margin, never overlapping it (was previously a
        # fixed y=612 footer colliding with row 9's box at y=620-662).
        rect = pygame.Rect(260, 40, 760, 660)
        pygame.draw.rect(self.screen, config.COLOR_OVERLAY_BG, rect)
        pygame.draw.rect(self.screen, config.COLOR_WARN, rect, 2)
        layout.blit_line(self.screen, "option.title", (292, 64, 696, 48),
                         config.COLOR_WARN, size=32, align="center")
        for page, tab in enumerate(self._options_page_rects()):
            active = page == self.options_page
            pygame.draw.rect(self.screen, config.COLOR_WARN if active
                             else config.COLOR_TEXT_DIM, tab, 1)
            layout.blit_line(self.screen, message("option.page", page=page + 1,
                                                  pages=len(self._OPTION_PAGES)),
                             tab.inflate(-8, -4), config.COLOR_WARN if active
                             else config.COLOR_TEXT_DIM, size=18, align="center")
        if self._option_rows() is self._OPTION_ROWS_SETUP:
            self._draw_options_setup_page()
            return
        values = (
            self.tr("option.language") + ": " + self.tr("option.language." + self.preferences.language),
            self.tr("option.fullscreen") + ": " + self.tr("common.on" if self.preferences.fullscreen else "common.off"),
            self.tr("option.audio") + ": " + self.tr("common.on" if self.audio.available else "common.off"),
            self.tr("option.large_text") + ": " + self.tr("common.on" if self.preferences.large_text else "common.off"),
            self.tr("option.tooltips") + ": "
            + self.tr("common.on" if self.tooltips_enabled else "common.off"),
            self.tr("option.simlog") + ": "
            + self.tr("common.on" if self.preferences.simlog else "common.off"),
            self.tr("option.night_mode") + ": "
            + self.tr("common.on" if self.preferences.night_mode else "common.off"),
            self.tr("option.high_contrast") + ": "
            + self.tr("common.on" if self.preferences.high_contrast else "common.off"),
            self.tr("option.frame_rate", fps=self.frame_rate()),
            self.tr("option.bottom_panel") + ": "
            + self.tr("option.bottom_panel." + self.bottom_panel_mode()),
            self.tr("option.operator_assist") + ": "
            + self.tr("option.operator_assist." + ("training" if self.operator_assist()
                                                   else "off")),
            self.tr("option.live_traffic"),
            self.tr("commander.local.option"),
        )
        for index, (value, row) in enumerate(zip(values, self._options_row_rects())):
            color = config.COLOR_TEXT if index == self.options_sel else config.COLOR_TEXT_DIM
            prefix = "> " if index == self.options_sel else "  "
            layout.blit_line(self.screen, raw_text(prefix + value), row, color, size=20)
        layout.blit_block(self.screen,
                          "commander.local.options_hint",
                          292, 650, 696, 46, config.COLOR_TEXT_DIM, size=18,
                          align="center")

    def _draw_options_setup_page(self) -> None:
        row = self._options_row_rects()[0]
        locked = self.local_side_locked()
        value = (self.tr("option.local_side") + ": "
                 + self.tr("option.local_side." + self.local_side))
        selected = self.options_sel == 0
        color = (config.COLOR_TEXT_DIM if locked or not selected else config.COLOR_TEXT)
        layout.blit_line(self.screen, raw_text(("> " if selected else "  ") + value),
                         row, color, size=20)
        layout.blit_block(self.screen, "option.local_side.help",
                          row.x + 24, row.bottom + 10, row.w - 24, 150,
                          config.COLOR_TEXT_DIM, size=18)
        if locked:
            layout.blit_block(self.screen, "option.local_side.locked",
                              row.x + 24, row.bottom + 170, row.w - 24, 50,
                              config.COLOR_WARN, size=18)
        layout.blit_block(self.screen,
                          "commander.local.options_hint",
                          292, 650, 696, 46, config.COLOR_TEXT_DIM, size=18,
                          align="center")

    @staticmethod
    def _live_traffic_row_rects():
        return tuple(pygame.Rect(292, 150 + index * 84, 696, 44) for index in range(5))

    @staticmethod
    def _mask_credential(value: str) -> str:
        value = (value or "").strip()
        if not value:
            return "-"
        return f"...{value[-4:]}" if len(value) > 4 else "*" * len(value)

    @localized
    def draw_live_traffic_overlay(self) -> None:
        rect = pygame.Rect(260, 40, 760, 660)
        pygame.draw.rect(self.screen, config.COLOR_OVERLAY_BG, rect)
        pygame.draw.rect(self.screen, config.COLOR_WARN, rect, 2)
        layout.blit_line(self.screen, "live_traffic.title", (292, 64, 696, 48),
                         config.COLOR_WARN, size=32, align="center")
        online = self.connectivity.online
        status_key = ("live_traffic.online" if online
                     else "live_traffic.offline" if online is False
                     else "live_traffic.checking")
        layout.blit_line(self.screen, status_key, (292, 108, 696, 28),
                         config.COLOR_TEXT_DIM, size=16, align="center")
        rows = self._live_traffic_row_rects()
        names = self._LIVE_TRAFFIC_ROWS
        toggle_labels = (
            self.tr("live_traffic.ais_toggle") + ": "
            + self.tr("common.on" if self.preferences.live_ais_enabled else "common.off"),
            self.tr("live_traffic.adsb_toggle") + ": "
            + self.tr("common.on" if self.preferences.live_adsb_enabled else "common.off"),
        )
        for index in range(2):
            color = (config.COLOR_TEXT if index == self.live_traffic_sel
                     else config.COLOR_TEXT_DIM)
            if not getattr(self.preferences, names[index]) \
                    and not self._live_traffic_can_enable(names[index]):
                color = config.COLOR_TEXT_DIM
            prefix = "> " if index == self.live_traffic_sel else "  "
            layout.blit_line(self.screen, raw_text(prefix + toggle_labels[index]),
                             rows[index], color, size=20)
        for index, key in ((2, "aisstream_api_key"), (3, "opensky_credentials")):
            color = config.COLOR_TEXT if index == self.live_traffic_sel else config.COLOR_TEXT_DIM
            prefix = "> " if index == self.live_traffic_sel else "  "
            label = self.tr("live_traffic.aisstream_key" if key == "aisstream_api_key"
                            else "live_traffic.opensky_key")
            row = rows[index]
            layout.blit_line(self.screen, raw_text(prefix + label),
                             (row.x, row.y, row.w, 22), color, size=18)
            field_rect = pygame.Rect(row.x, row.y + 24, row.w, 30)
            if self.live_traffic_field is not None and self.live_traffic_field_name == key:
                self.live_traffic_field.draw(self.screen, field_rect, focused=True)
            else:
                layout.blit_line(self.screen,
                                 raw_text(self._mask_credential(getattr(self.preferences, key))),
                                 field_rect, config.COLOR_TEXT_DIM, size=16)
        test_row = rows[4]
        color = config.COLOR_TEXT if self.live_traffic_sel == 4 else config.COLOR_TEXT_DIM
        prefix = "> " if self.live_traffic_sel == 4 else "  "
        layout.blit_line(self.screen, raw_text(prefix + self.tr("live_traffic.test_action")),
                         (test_row.x, test_row.y, test_row.w, 22), color, size=18)
        status_line = self.tr("live_traffic.test_result",
                              ais=self._live_traffic_test_label("ais"),
                              adsb=self._live_traffic_test_label("adsb"))
        layout.blit_line(self.screen, raw_text(status_line),
                         (test_row.x, test_row.y + 24, test_row.w, 24),
                         config.COLOR_TEXT_DIM, size=16)
        layout.blit_block(self.screen,
                          "live_traffic.hint",
                          292, 636, 696, 58, config.COLOR_TEXT_DIM, size=16,
                          align="center")

    def _live_traffic_test_label(self, side: str) -> str:
        status, reason = self.live_traffic_test_result.get(side, ("idle", None))
        if status == "running":
            return self.tr("live_traffic.test_running")
        if status == "no_key":
            return self.tr("live_traffic.test_no_key")
        if status == "ok":
            return self.tr("live_traffic.test_ok")
        if status == "error":
            return self.tr("live_traffic.test_error", reason=(reason or "?")[:80])
        return self.tr("live_traffic.test_idle")

    @localized
    def draw_quit_overlay(self) -> None:
        """Require an explicit confirmation before leaving a live mission."""
        s = self.screen
        dim = pygame.Surface((config.SCREEN_W, config.SCREEN_H), pygame.SRCALPHA)
        dim.fill((0, 0, 0, 155))
        s.blit(dim, (0, 0))
        choices = (("quit.menu", "common.exit") if self.in_menu else
                   ("quit.game", "quit.save", "quit.main_menu", "quit.no_save"))
        rect = pygame.Rect(260, 185 - 20 * (len(choices) - 3),
                           760, 330 + 40 * (len(choices) - 3))
        pygame.draw.rect(s, config.COLOR_PANEL_BG, rect)
        pygame.draw.rect(s, config.COLOR_WARN, rect, 2)
        layout.blit_line(s, "quit.title", (rect.x + 20, rect.y + 22,
                         rect.w - 40, 36), config.COLOR_WARN, size=28)
        layout.blit_line(s, "quit.warning",
                         (rect.x + 20, rect.y + 74, rect.w - 40, 26),
                         config.COLOR_TEXT, size=16)
        for index, label in enumerate(choices):
            selected = index == self.quit_selection
            layout.blit_line(s, message("menu.choice",
                                        marker="> " if selected else "  ",
                                        label=self.tr(label)),
                             (rect.x + 20, rect.y + 124 + index * 40, rect.w - 40, 32),
                             config.COLOR_WARN if selected else config.COLOR_TEXT,
                             size=22)
        layout.blit_line(s, "control.quit_hint",
                         (rect.x + 20, rect.bottom - 44, rect.w - 40, 28),
                         config.COLOR_TEXT_DIM, size=18)

    # --- Main loop ---

    def _perf_debug_log(self, wall_dt: float) -> None:
        """Optional 1 Hz diagnostics line, enabled via U_JAGD_PERF_DEBUG=1.

        Appends bounded per-frame-average phase timings (physics substeps,
        audio publish, Remote Crew pump, draw/compose) to perf_debug.log
        inside the save directory, for on-device (uConsole) CPU diagnosis.
        Purely measures wall time already spent in existing calls; never
        alters simulation timing, input, or rendering. No-op unless enabled.
        """
        if not self._perf_debug_enabled:
            return
        try:
            wall_dt = float(wall_dt)
        except (TypeError, ValueError, OverflowError):
            return
        if not math.isfinite(wall_dt) or wall_dt <= 0.0:
            return
        self._perf_frames += 1
        self._perf_frame_max_s = max(self._perf_frame_max_s, wall_dt)
        self._perf_debug_due += wall_dt
        if self._perf_debug_due < 1.0:
            return
        self._perf_debug_due %= 1.0
        frames = self._perf_frames
        line = ("t={t:.1f} fps={fps} substeps_avg={sub:.2f} sim_ms={sim:.2f} "
                "audio_ms={audio:.2f} commander_ms={cmd:.2f} "
                "commander_max_ms={cmdmax:.1f} events_ms={events:.2f} "
                "traffic_ms={traffic:.2f} "
                "draw_ms={draw:.2f} frame_max_ms={fmax:.1f} "
                "sim_lag_ms={lag:.1f} sim_dropped_ms={drop:.1f}\n").format(
            t=time.monotonic(), fps=frames, sub=self._perf_substeps / frames,
            fmax=1000 * self._perf_frame_max_s, lag=1000 * self._sim_debt_s,
            drop=1000 * self._sim_dropped_s,
            sim=1000 * self._perf_sim_s / frames,
            audio=1000 * self._perf_audio_s / frames,
            cmd=1000 * self._perf_commander_s / frames,
            cmdmax=1000 * self._perf_commander_max_s,
            events=1000 * self._perf_events_s / frames,
            traffic=1000 * self._perf_traffic_s / frames,
            draw=1000 * self._perf_draw_s / frames)
        append_bounded_log(config.SAVE_DIR, "perf_debug.log", line,
                           config.PERF_DEBUG_LOG_MAX_BYTES)
        self._perf_frames = 0
        self._perf_sim_s = 0.0
        self._perf_substeps = 0
        self._perf_audio_s = 0.0
        self._perf_commander_s = 0.0
        self._perf_commander_max_s = 0.0
        self._perf_events_s = 0.0
        self._perf_traffic_s = 0.0
        self._perf_draw_s = 0.0
        self._perf_frame_max_s = 0.0

    def _frame_dt(self, wall_dt: float) -> float:
        """Simulation seconds for this frame from wall time and bounded debt.

        A frame never advances more than SIM_FRAME_DT_MAX, but the remainder of
        a slow frame is caught up over the next frames, so simulation time (and
        the sonar audio produced in it) keeps pace with wall-clock playback.
        Debt above SIM_CATCHUP_MAX_S is dropped. After a pause, menu, overlay,
        load or world reset the first frame is only clamped, never caught up.
        """
        try:
            wall_dt = float(wall_dt)
        except (TypeError, ValueError, OverflowError):
            wall_dt = 0.0
        if not math.isfinite(wall_dt) or wall_dt < 0.0:
            wall_dt = 0.0
        if self._frame_clock_reset:
            self._frame_clock_reset = False
            self._sim_debt_s = 0.0
            return min(wall_dt, config.SIM_FRAME_DT_MAX)
        debt = self._sim_debt_s + wall_dt
        if debt > config.SIM_CATCHUP_MAX_S:
            self._sim_dropped_s += debt - config.SIM_CATCHUP_MAX_S
            debt = config.SIM_CATCHUP_MAX_S
        dt = min(debt, config.SIM_FRAME_DT_MAX)
        self._sim_debt_s = debt - dt
        return dt

    def frame_rate(self) -> int:
        """Active frame-rate cap from the saved preference."""
        value = getattr(self.preferences, "frame_rate", config.FPS_DEFAULT)
        return value if value in config.FPS_CHOICES else config.FPS_DEFAULT

    def run(self) -> None:
        try:
            while self.running:
                if self.auto_quit is not None:
                    self.auto_quit -= 1
                    if self.auto_quit <= 0:
                        self.running = False
                wall_dt = self.clock.tick(self.frame_rate()) / 1000.0
                dt = self._frame_dt(wall_dt)
                self._t += dt
                events_started = (time.perf_counter()
                                  if self._perf_debug_enabled else None)
                for e in pygame.event.get():
                    if not self.web_mode:
                        self.handle_event(e)
                        if e.type in _ECO_REFRESH_EVENTS:
                            self._eco_drawn_at = float("-inf")
                if events_started is not None:
                    self._perf_events_s += time.perf_counter() - events_started
                commander_started = (time.perf_counter()
                                     if self._perf_debug_enabled else None)
                self.commander.pump(self)
                if commander_started is not None:
                    now = time.perf_counter()
                    self._perf_commander_s += now - commander_started
                    self._perf_commander_max_s = max(
                        self._perf_commander_max_s, now - commander_started)
                    commander_started = now
                self.live_traffic.pump(self)
                if commander_started is not None:
                    self._perf_traffic_s += time.perf_counter() - commander_started
                self.update(dt, audio_dt=wall_dt)
                self._perf_debug_log(wall_dt)
                if self.web_mode:
                    continue
                if self._skip_eco_frame():
                    continue
                draw_started = time.perf_counter() if self._perf_debug_enabled else None
                self.draw()
                self.compose_frame()
                if draw_started is not None:
                    self._perf_draw_s += time.perf_counter() - draw_started
        finally:
            try:
                self.commander.stop()
            finally:
                try:
                    self.connectivity.stop()
                    self.live_traffic.stop()
                finally:
                    self.audio.shutdown()
                    pygame.quit()


install_station_properties(Game)
