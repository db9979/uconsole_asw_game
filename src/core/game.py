"""Haupt-Game-Loop: Widescreen-Grid, Echtzeit, Szenarien und Multi-Slot-Save."""

import os
import threading
from collections import deque
from contextlib import contextmanager

import pygame

from src.audio.engine import AudioEngine
from src.audio.speech import Speaker, find_engine
from src.commander.local import CommanderConsole
from src.core import config
from src.core.callouts import CalloutLog
from src.core.i18n import Translator
from src.core.preferences import Preferences
from src.network.connectivity import ConnectivityMonitor
from src.network.live_traffic import LiveTrafficManager
from src.core.station import Station  # noqa: F401  (tests read game_module.Station)
from src.core import opfor
from src.core.limits import (MAX_DECOYS, MAX_ENEMY_TORPEDOES,
                             MAX_OPZ_TRACK_LABELS, MAX_SAVED_ASMS, MAX_SAVED_ENTITIES,
                             MAX_SAVED_ESSMS, MAX_SAVED_PLAYER_TORPEDOES,
                             MAX_TRACK_DISPLAY_ID_LEN)
# ``CATALOG`` and the entity classes are re-exported for the tests that
# import or patch them through ``src.core.game``.
from src.data.catalog import CATALOG  # noqa: F401
from src.enemies.animal import Animal  # noqa: F401
from src.enemies.sub import Sub  # noqa: F401
from src.enemies.surface import SurfaceShip  # noqa: F401
from src.sonar.station import install_station_properties
from src.ui.editor_widgets import TextField
from src.ui import simlog_map
# Shared display/help constants and helpers (re-exported for tests/tools).
from src.core.game_shared import (  # noqa: F401
    HELP_MANUAL_PAGE, HELP_PAGE_COUNT, SONAR_BAND_PRESETS, TMA_ACCEPT_MIN_FIT,
    letterbox_layout, make_scanlines)
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
from src.core.game_asw import AswWeaponsMixin
from src.core.game_rbu import RbuMixin
from src.core.game_casualties import CasualtiesMixin
from src.core.game_sim import (
    SimMixin,
    SONAR_CLASS_KINDS,
    LOOKOUT_MODEL,
    TORPEDO_WAKE_VISIBLE_NM,
    TORPEDO_WAKE_VISIBLE_DEPTH_M)
from src.core.game_radar import CIWS_TRACK_RANGE_NM, RadarPictureMixin
from src.core.game_events import (EventMixin, _ECO_REFRESH_EVENTS)
from src.core.mission_bridge import (MissionBridgeMixin)
from src.core.game_draw import (DrawMixin)
from src.core.game_operator import (OperatorMixin)
from src.core.game_pictures import (PicturesMixin)
from src.core.game_tasking import TaskingMixin
from src.core.game_rescue import RescueMixin
from src.core.game_incidents import IncidentsMixin
from src.core.game_crew import CrewMixin
from src.core.game_noise import NoiseMixin
from src.core.game_daily import DailyMixin
from src.core.game_mpa import MpaMixin
from src.core.game_consort import ConsortMixin
from src.core.game_debrief import DebriefMixin
from src.core.game_training import TrainingMixin
from src.core.game_custom import CustomMissionMixin
from src.core.game_campaign import CampaignMixin
from src.core.game_autosave import AutosaveMixin, CONTINUE_ENTRY
from src.core.game_resilience import ResilienceMixin
from src.core.game_reports import ReportsMixin
from src.core.game_logbook import LogbookMixin
from src.core.game_bugreport import (BUG_REPORT_ENTRY, MAIN_MENU_ENTRIES,
                                     BugReportMixin)
from src.core.game_welcome import WelcomeMixin
from src.core.game_lobby import LobbyMixin
from src.core.game_server import ServerModeMixin
from src.core.game_update import UpdateNoticeMixin
from src.core.game_llm import LlmMixin
from src.core.game_advisor import AdvisorUiMixin
from src.core.game_voice import VoiceMixin
from src.core.game_talk import TalkMixin
from src.core.game_habits import HabitsMixin
from src.core.game_reset import ResetMixin


class Game(PicturesMixin, OperatorMixin, DrawMixin, MissionBridgeMixin, EventMixin, SimMixin,
           RadarPictureMixin, AswWeaponsMixin, RbuMixin, CasualtiesMixin,
           SaveMixin, TaskingMixin, RescueMixin, IncidentsMixin, CrewMixin, NoiseMixin, DailyMixin, MpaMixin, ConsortMixin, DebriefMixin,
           TrainingMixin, CustomMissionMixin, CampaignMixin, LogbookMixin, ReportsMixin, BugReportMixin, AutosaveMixin, WelcomeMixin,
           LobbyMixin, ServerModeMixin, UpdateNoticeMixin, ResilienceMixin, LlmMixin, AdvisorUiMixin, VoiceMixin, TalkMixin,
           HabitsMixin,
           ResetMixin):
    # Options overlay rows in display order; the last two open sub-menus.
    _OPTION_ROWS = ("language", "fullscreen", "audio", "large_text", "tooltips",
                    "simlog", "night_mode", "theme", "frame_rate",
                    "bottom_panel", "level", "live_traffic", "commander")
    # Second options page: game setup.  The local side is per launch and never
    # persisted (the frigate is always the default).
    _OPTION_ROWS_SETUP = ("local_side", "graphics", "speech", "microphone", "llm")
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
        self.level = config.LEVEL_DEFAULT
        self.menu_difficulty = (dict(difficulty) if difficulty
                                and _valid_difficulty_dict(difficulty)
                                else dict(config.DEFAULT_DIFFICULTY))
        # Free-hunt choice for the start report; fixed scenarios set their own.
        self.menu_hq_intel = "coarse"
        # Start weather and time of the next scenario/campaign mission.
        self.start_weather = "random"
        self.start_time = "random"
        # The length the player chose last (a first launch: short).
        self.start_length = (self.preferences.mission_length
                             if self.preferences.mission_length in config.START_LENGTH_CHOICES
                             else "normal")
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
        self._init_update_notice()
        self._init_logbook()
        self._init_autosave()
        self._init_resilience()
        self._autosave_armed = False
        if self.main_menu and self.autosave_available:
            # A mission was left running (quit or crash): offer "Continue".
            self.main_menu_sel = self.main_menu_index(CONTINUE_ENTRY)
        elif self.bug_report_offer and self.main_menu:
            # The last launch crashed: preselect "Report a bug".
            self.main_menu_sel = self.main_menu_index(BUG_REPORT_ENTRY)
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
        # Optional language model (off by default; src/core/game_llm.py).
        self._init_llm()
        self._init_voice()
        self._init_talk()
        self._init_advisor_ui()
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
        self._autosave_armed = True
        # First launch (no settings.json): the welcome page replaces the menu.
        self._init_lobby()
        self._init_server_mode()
        self._init_welcome(start_menu)
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
