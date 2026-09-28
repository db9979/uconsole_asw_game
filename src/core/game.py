"""Haupt-Game-Loop: Widescreen-Grid, Echtzeit, Szenarien und Multi-Slot-Save."""

import copy
import math
import os
import threading
import weakref
from collections import deque
from contextlib import contextmanager

import pygame

from src.audio.engine import AudioEngine
from src.audio.receiver import AcousticReceiver
from src.audio.speech import Speaker, find_engine
from src.commander.local import CommanderConsole
from src.core import config
from src.core.plot import PlotLayer
from src.core.autocrew import AutocrewController
from src.core.callouts import CalloutLog
from src.core.i18n import Translator, message
from src.core.preferences import Preferences
from src.network.connectivity import ConnectivityMonitor
from src.network.live_traffic import LiveTrafficManager
from src.core.mission import Mission
from src.core.station import Station
from src.core import opfor
from src.core.limits import (MAX_AIR_PICTURE_TRACKS, MAX_DECOYS, MAX_ENEMY_TORPEDOES,
                             MAX_OPZ_TRACK_LABELS, MAX_SAVED_ASMS, MAX_SAVED_ENTITIES,
                             MAX_SAVED_ESSMS, MAX_SAVED_PLAYER_TORPEDOES,
                             MAX_TRACK_DISPLAY_ID_LEN)
from src.sensors.ais import AISReceiver
from src.sonar import analysis_tools
from src.data.catalog import CATALOG
from src.enemies.animal import Animal
from src.enemies.civilian import CivilianShip
from src.enemies.sub import Sub
from src.enemies.surface import SurfaceShip
from src.sensors.tracks import TrackPicture
from src.sensors.fusion import OPZFusionPicture
from src.sensors.esm import ECMJammer, ESMPicture
from src.ship.damage import DamageModel
from src.ship.ship import Ship
from src.sonar.sonar import SonarSystem
from src.sonar.station import SonarStation, install_station_properties
from src.ui.editor_widgets import TextField
from src.ui.feedback import EventFeed
from src.ui import simlog_map
from src.ui.viewport import Viewport
from src.air.helicopter import Helicopter
from src.air.flights import FlightManager
from src.world.world import World
from src.world.coastline import Coastline
from src.weapons.asw import ConsumableStore, WeaponBattery, ownship_loadout
from src.weapons.air_defense import air_defense_loadout, make_softkill_store
# Shared display/help constants and helpers (re-exported for tests/tools).
from src.core.game_shared import (  # noqa: F401
    HELP_MANUAL_PAGE, HELP_PAGE_COUNT, SONAR_BAND_PRESETS, TMA_ACCEPT_MIN_FIT,
    letterbox_layout, make_night_overlay, make_scanlines)
# Entity classes tests import from ``src.core.game`` (kept as re-exports).
from src.enemies.decoy import Decoy  # noqa: F401
from src.weapons.torpedo import EnemyTorpedo  # noqa: F401
# ``src.core.game.layout`` is a monkeypatch target of the input tests.
from src.ui import layout  # noqa: F401
# Names tests and tools import from ``src.core.game`` (kept as re-exports).
from src.core.save_schema import SAVE_ROOT_FIELDS  # noqa: F401
from src.core.game_save import (
    SaveMixin,
    _read_save_document,
    _valid_difficulty_dict,
    _same_save_value,
    _same_save_value_strict,
    MAX_SAVE_DOCUMENT_BYTES)
from src.core.game_sim import (
    SimMixin,
    SONAR_CLASS_KINDS,
    LOOKOUT_MODEL,
    CIWS_TRACK_RANGE_NM,
    TORPEDO_WAKE_VISIBLE_NM,
    TORPEDO_WAKE_VISIBLE_DEPTH_M)
from src.core.game_events import (EventMixin, _ECO_REFRESH_EVENTS)
from src.core.mission_bridge import (MissionBridgeMixin)
from src.core.game_draw import (DrawMixin)
from src.core.game_operator import (OperatorMixin)
from src.core.game_pictures import (PicturesMixin)
from src.core.game_tasking import TaskingMixin
from src.core.game_crew import CrewMixin
from src.core.game_mpa import MpaMixin
from src.core.game_debrief import DebriefMixin
from src.core.game_training import TrainingMixin
from src.core.game_campaign import CampaignMixin
from src.core.game_bugreport import (BUG_REPORT_ENTRY, MAIN_MENU_ENTRIES,
                                     BugReportMixin)


class Game(PicturesMixin, OperatorMixin, DrawMixin, MissionBridgeMixin, EventMixin, SimMixin,
           SaveMixin, TaskingMixin, CrewMixin, MpaMixin, DebriefMixin,
           TrainingMixin, CampaignMixin, BugReportMixin):
    # Options overlay rows in display order; the last two open sub-menus.
    _OPTION_ROWS = ("language", "fullscreen", "audio", "large_text", "tooltips",
                    "simlog", "night_mode", "high_contrast", "frame_rate",
                    "bottom_panel", "operator_assist", "live_traffic", "commander")
    # Second options page: game setup.  The local side is per launch and never
    # persisted (the frigate is always the default).
    _OPTION_ROWS_SETUP = ("local_side", "aa_lines", "speech")
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
        # Spoken crew reports (transient; see src/core/callouts.py).
        self.callouts = CalloutLog()
        self.speaker = Speaker(find_engine())
        # Pulse type per transmission time, for the echo sound only (audio,
        # never saved; after a load the current pulse is used).
        self._ping_pulses = {}
        # Foreign active pings still travelling to the frigate:
        # (arrival sim time, source x, source y). Transient, never saved.
        self._ping_intercepts = []
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
        self._init_bug_report()
        if self.bug_report_offer and self.main_menu:
            # The last launch crashed: preselect "Report a bug".
            self.main_menu_sel = MAIN_MENU_ENTRIES.index(BUG_REPORT_ENTRY)
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
        self._opfor.watch = self._boat_watch(self._opfor)
        self._apply_crew_effects()
        return self._opfor

    def release_opfor_sub(self) -> None:
        """Hand the crewed submarine back to the AI."""
        boat = self._opfor
        self._opfor = None
        if boat is not None:
            # The AI crew works at the calibrated pace again.
            boat.sub.damage_control.crew_factor = 1.0
        if boat is not None and boat.sub in self.subs and not boat.sub.sunk:
            boat.sub.release_manual()

    def reset(self, seed: int, scenario_key: str = None, *, publish_intel: bool = True,
              reference_sector: int | None = None,
              difficulty_override: dict | None = None) -> None:
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
        self.callouts.clear()
        self.callouts.spoken = self.callouts.seq
        self.speaker.stop()
        self._ping_pulses.clear()
        self._ping_intercepts.clear()
        self._sonar_audio_sequence = -1
        scenario_key = scenario_key or self.scenario_key
        if scenario_key not in config.SCENARIOS:
            scenario_key = "s4_zufall"
        sc = config.SCENARIOS[scenario_key]
        self.scenario_key = scenario_key
        self.difficulty = {**config.DEFAULT_DIFFICULTY,
                           **(sc["difficulty"] if sc["difficulty"] is not None
                              else self.menu_difficulty),
                           # A campaign leg brings its carried torpedo stock.
                           **(difficulty_override or {})}
        self.level = "custom"

        if reference_sector is not None:
            # A mission's reference world: the named real sector, not seed % 128.
            self.world_mode = "real_fixed"
            coast = Coastline.generate(seed, sector_index=reference_sector)
        else:
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
        # Mission unit id -> entity id of the placed unit (custom missions).
        self.mission_units = {}
        # Authored events not yet run, in order of their time (custom missions).
        self.mission_events_pending = []
        self.mission_time = 0.0
        self.score = 0
        # HQ orders and incidents (save ``tasking``); none in custom missions.
        self._reset_tasking()
        # Watches, fatigue and morale of the frigate crew (save ``watch``).
        self._reset_crew()
        # Post-mission debrief recording (transient, never saved).
        self._reset_debrief()
        # A guided lesson's coach (set by start_training, never saved).
        self.training = None
        # Whether this mission is the current campaign leg (never saved).
        self.campaign_mission = False
        self._campaign_leg_shown = False
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
                    solution_threshold=lv["enemy_solution_threshold"],
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

        if self.mission.win_mode == "convoy_attack":
            from src.core import boat_missions
            boat_missions.spawn_convoy(self)

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
        # Operator weapon settings (save v15 ``weapon_settings``): torpedo type,
        # terminal search pattern, seeker enable point and salvo size.
        self.torpedo_type = self._ownship_loadout["weapons"][0]["key"]
        self.player_torpedo_battery.preferred_weapon_key = self.torpedo_type
        self.torpedo_pattern = "snake"
        self.torpedo_enable_nm = config.TORP_HOME_RANGE_NM
        self.torpedo_salvo = 1
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
        self.lookout_glasses = False                 # binoculars over the chart (UI only)
        self.lookout_glasses_rel = 0.0               # their line of sight off the bow
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
        # The maritime patrol aircraft on call (save ``mpa``).
        self._reset_mpa()
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
        # Unmarked mast/snorkel echoes and the boats whose echoes the OPZ
        # marked into a track: sub id -> (track id, last echo). Saved since
        # v25 (``radar_marks``): the AI hunters act on them.
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

    @property
    def radar_on(self) -> bool:
        """Kompatibilitaet fuer alte Aufrufer/Saves: beide Radare gemeinsam."""
        return self.surface_radar_on and self.air_radar_on

    @radar_on.setter
    def radar_on(self, value: bool) -> None:
        self.surface_radar_on = bool(value)
        self.air_radar_on = bool(value)

install_station_properties(Game)
