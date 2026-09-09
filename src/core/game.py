"""Haupt-Game-Loop: Widescreen-Grid (Karte + Station + Feed + Telemetrie),
Zeitraffer 1x-30x, Szenarien, Multi-Slot-Save (W0-W4)."""

import copy
import hashlib
import json
import math
import os
from types import SimpleNamespace

import pygame

from src.audio.engine import AudioEngine
from src.commander.local import CommanderConsole
from src.core import config
from src.core.commands import (MAP_STATIONS, STATION_PAGES, event_feed_heading,
                               station_page_step, toggle_tas)
from src.core.i18n import (Translator, display_value, localized, localize,
                           message, raw_text)
from src.core.preferences import Preferences, save_preferences
from src.core.help import get_global_help, get_help
from src.core.mission import Mission
from src.core.mission_definition import static_preview, validate_mission
from src.core.station import Station
from src.core.version import SAVE_SCHEMA, SAVE_VERSION
from src.data import fingerprint as fingerprint_mod
from src.data.catalog import CATALOG, catalog_from_runtime_snapshot
from src.enemies.animal import Animal
from src.enemies.civilian import CivilianShip
from src.enemies.decoy import Decoy
from src.enemies.sub import Sub
from src.enemies.surface import SurfaceShip
from src.nations.nations import NATIONS, get_nation
from src.sensors.tracks import TrackPicture
from src.sensors.esm import (
    ESM_MAX_ANNOTATIONS,
    ESM_STATE_VERSION,
    ESMCorrelationEvidence,
    ESMMeasurement,
    ESMPicture,
    correlate_observations,
    rank_emitters,
    valid_esm_state,
)
from src.sensors.platform import (
    PlatformSensorSuite,
    exchange_friendly_datalink,
    snapshot_observation,
    validate_suite_state,
)
from src.ship.damage import DamageModel
from src.ship.ship import Ship
from src.sonar.sonar import Contact, SonarSystem, TowState
from src.sonar.tma import BearingPoint, BearingTrack
from src.ui import layout
from src.ui.feedback import EventFeed
from src.ui.map_view import draw_map_view, map_hit_target
from src.ui.splash_view import SPLASH_PING_PERIOD_S, draw_splash
from src.ui.sonar_view import draw_sonar_view
from src.ui.stations_view import (draw_bridge_view, draw_damage_view,
                                  draw_eloka_view, draw_engine_view, draw_opz_view,
                                  draw_radio_view,
                                   draw_helicopter_view, station_hit_target)
from src.ui.stations_view import (damage_compartment_at, eloka_track_at,
                                  opz_ppi_rect)
from src.ui.mission_editor import MissionEditor
from src.ui.unit_editor import UnitEditor, catalog_builtins
from src.ui.viewport import Viewport
from src.ui.weapons_view import (draw_weapons_overlay, draw_weapons_panel,
                                 weapons_hit_target)
from src.ui.sonar_view import sonar_hit_target
from src.air.asm import ASM, ESSM
from src.air.helicopter import Helicopter
from src.air.flights import Flight, FlightManager
from src.air.sonobuoy import Sonobuoy
from src.world.world import World
from src.world.coastline import Coastline
from src.weapons.torpedo import EnemyTorpedo, Torpedo
from src.weapons.asw import (
    ASROC,
    ASW_STATE_VERSION,
    ConsumableStore,
    MAX_ASROCS,
    MAX_TOWED_DECOYS,
    TowedAcousticDecoy,
    WeaponBattery,
    battery_matches_catalog,
    consumable_matches_catalog,
    ownship_loadout,
    valid_asw_state,
)


MAX_SAVE_DOCUMENT_BYTES = 64 * 1024 * 1024
MAX_AIR_PICTURE_TRACKS = 512
MAX_SAVED_ENTITIES = 512
MAX_ENEMY_TORPEDOES = 128
MAX_DECOYS = 128
SAVE_ROOT_FIELDS = {
    "version", "save_schema", "platform_state_version", "catalog_snapshot",
    "seed", "level", "mission_type", "scenario_key", "mission_name",
    "mission_runtime", "world", "sim_t", "mission_time", "time_scale_idx",
    "score", "mission_result", "result_reason", "ship", "torpedoes",
    "chaff_cd", "vls_cells", "ciws_ammo", "roe", "sonar_mode", "radars",
    "asm_sel", "radio_sel", "hq_timer", "damage", "dmg_cursor", "dmg_team",
    "incident", "subs", "animals", "civilians", "warships", "decoys",
    "torpedoes_in_flight", "enemy_torpedoes", "asw", "asms", "essms",
    "buoys", "helo", "flights", "sonar_controls", "sonar", "messages",
    "hfdf_fixes", "hfdf_log", "radio_picture", "air_picture",
    "opz_affiliations", "air_threat_reported", "esm", "next_entity_ids",
    "asm_spawned", "asm_seq", "warship_asm_seq", "torpedo_seq", "buoy_seq",
    "ciws_cooldown_s", "schedulers", "rngs", "ui",
}


def _read_save_document(path):
    if os.path.getsize(path) > MAX_SAVE_DOCUMENT_BYTES:
        raise ValueError("save document too large")
    with open(path, "rb") as stream:
        raw = stream.read(MAX_SAVE_DOCUMENT_BYTES + 1)
    if len(raw) > MAX_SAVE_DOCUMENT_BYTES:
        raise ValueError("save document too large")
    return json.loads(raw.decode("utf-8"))


def _same_save_value(left, right) -> bool:
    """Compare canonical JSON values while treating tuples as JSON arrays."""
    if isinstance(left, dict) and isinstance(right, dict):
        return (set(left) == set(right)
                and all(_same_save_value(left[key], right[key]) for key in left))
    if isinstance(left, (list, tuple)) and isinstance(right, (list, tuple)):
        return (len(left) == len(right)
                and all(_same_save_value(a, b) for a, b in zip(left, right)))
    if isinstance(left, bool) or isinstance(right, bool):
        return type(left) is type(right) and left == right
    if isinstance(left, (int, float)) and isinstance(right, (int, float)):
        return left == right
    return type(left) is type(right) and left == right


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


class Game:
    def __init__(self, seed: int = 42, level: str = None,
                  start_menu: bool = False, fullscreen: bool = None,
                 window_size: tuple = None, show_splash: bool = False,
                  audio_enabled: bool = None, preferences: Preferences = None,
                  language: str = None):
        requested_fullscreen = (preferences.fullscreen
                                if preferences is not None and fullscreen is None
                                else bool(fullscreen))
        requested_audio = (preferences.audio
                           if preferences is not None and audio_enabled is None
                           else (config.AUDIO_ENABLED if audio_enabled is None
                                 else bool(audio_enabled)))
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
        self._sensor_acc = 0.0
        self._esm_acc = 0.0
        self._radio_acc = 0.0
        self._slow_acc = 0.0
        self._apply_text_size()
        self.level = level if level in config.LEVELS else config.DEFAULT_LEVEL
        self.in_menu = start_menu
        self.menu_sel = 1  # Index in LEVEL_ORDER (Default: normal)
        self.seed = seed
        self.world_mode = "procedural"
        # W4: Szenario-Auswahl im Hauptmenü
        self.scenario_key = "s1_patrouille"
        self.menu_screen = "scenario"  # "scenario" | "level" | "briefing"
        self.main_menu = bool(start_menu)
        self.main_menu_sel = 0
        self.editor = None
        self.options_open = False
        self.options_sel = 0
        self.commander = CommanderConsole()
        self.commander_open = False
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
        self.reset(seed)
        self.splash_active = bool(show_splash)
        self.splash_started_at = self._t
        self._splash_ping_cycle = -1

    def _apply_text_size(self) -> None:
        layout.configure_for(self)
        self.font = layout.font(18)
        self.font_big = layout.font(28, bold=True)

    @property
    def radar_range_nm(self) -> float:
        return self.opz_range_nm

    @radar_range_nm.setter
    def radar_range_nm(self, value: float) -> None:
        self.opz_range_nm = value

    def reset(self, seed: int, scenario_key: str = None) -> None:
        """Spielzustand neu aufbauen (Start/Neustart).

        W4: Szenario (config.SCENARIOS) legt Level, Missionstyp und
        Startposition fest. s4_zufall = seed-basiert wie vor dem Refactor.
        """
        import random
        self.runtime_catalog = CATALOG
        self.commander_open = False
        self.audio.stop()
        self._sonar_audio_sequence = -1
        scenario_key = scenario_key or self.scenario_key
        if scenario_key not in config.SCENARIOS:
            scenario_key = "s4_zufall"
        sc = config.SCENARIOS[scenario_key]
        self.scenario_key = scenario_key
        if sc["level"] in config.LEVELS:
            self.level = sc["level"]

        coast = Coastline.load() if self.world_mode == "fixed" else None
        self.world = World(seed=seed, coast=coast)
        start = sc["ship_start"] or (250.0, 250.0)
        sx, sy = self.world.nearest_water(start[0], start[1])
        course = sc["ship_course"]
        if course is None:
            course = 90.0
        self.ship = Ship(x_nm=sx, y_nm=sy, course_deg=course)
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
        self.time_scale_idx = config.TIME_SCALE_DEFAULT
        self.feed = EventFeed()

        # M6: Mission (W4: Szenario kann den Typ fixieren)
        self.mission = Mission(seed, type_key=sc["mission_type"])
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

        # U-Boote laut Mission + Level (M7: HARTE -> mehr AIP-Boote)
        lv = config.LEVELS[self.level]
        plan = list(self.mission.sub_types)
        if (len(plan) < 3 and lv["second_sub_prob"] > 0.0
                and rng.random() < lv["second_sub_prob"]):
            plan.append(rng.choice(lv["second_sub_pool"]))
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
        self.paused = False
        self.running = True
        self.held = set()
        self._map_drag = None
        self._map_drag_moved = False
        # Waffenzentrale (M3, M7: Munitionsbestand je Level)
        self._ownship_loadout = copy.deepcopy(ownship_loadout())
        self.player_torpedo_battery = WeaponBattery.ownship(
            self.level, self._ownship_loadout)
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
        # M5: Schadensmodell + Gegentorpedos (M7: Reparatur-Faktor je Level)
        self.damage = DamageModel(random.Random(seed + 777),
                                  repair_mult=lv["repair_mult"])
        self.enemy_torpedoes = []
        self._observed_enemy_torpedoes = set()
        self.game_over = False
        # M10–M16
        self.sonar_mode = "BOW"                      # "BOW" | "TOWED"
        self.sonar_page = 0
        self.sonar_audio_enabled = True
        self.sonar_volume = 0.5
        self._sonar_audio_sequence = -1
        self._sonar_audio_suspended = False
        self.surface_radar_on = config.RADAR_ON_DEFAULT
        self.air_radar_on = config.RADAR_ON_DEFAULT
        self.opz_range_nm = config.RADAR_RANGE_DEFAULT_NM
        self.roe = config.ROE_DEFAULT                # "STD" | "FREE"
        self.messages: list = []                     # Funkraum-Teletype
        self.dmg_cursor = 0
        self.dmg_team = 1
        self.helo = Helicopter(
            random.Random(seed + 555), self.runtime_catalog.torpedoes[
                self.runtime_catalog.runtime_bindings["helicopter_torpedo"]])
        self.buoys = []
        self.buoy_seq = 0
        self.asms = []
        self.essms = []
        self.vls_cells = config.VLS_CELLS
        self.chaff_cd = 0.0
        self.rng_asm = random.Random(seed + 31337)
        self.asm_spawned = 0
        self.asm_seq = 0
        self.air_threat_reported = False
        self.warship_asm_seq = 0
        self.asm_sel = 0
        self.air_picture = TrackPicture(
            config.RADAR_TRACK_STALE_S, maximum=MAX_AIR_PICTURE_TRACKS)
        self.opz_selected_track_id = None
        self.opz_affiliations = {}
        self.esm_picture = ESMPicture()
        self.eloka_selected_track_key = None
        self.eloka_annotations = {}
        self.radio_picture = TrackPicture(300.0)
        self.radio_sel = 0
        self.hfdf_log = []
        self.hfdf_fixes = {}
        self.ciws_ammo = config.CIWS_AMMO_DEFAULT
        self.ciws_cooldown_s = 0.0
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
        self._joy_acc = 0.0
        self._joy_x_acc = 0.0
        self._joy_turn = 0
        # W3: Luftfahrt (Airbases + Flüge) und W0: Karten-Viewport
        self.flights = FlightManager(
            self.world.coast, random.Random(seed + 2024), self.runtime_catalog)
        self.map_view = Viewport(self.world.size_nm,
                                 config.MAP_ZOOM_MIN_PX_PER_NM,
                                 config.MAP_ZOOM_MAX_PX_PER_NM)
        self._reset_map_view()
        self.hq_msg(message("runtime.hq.roe", roe=self.roe))
        self.hq_msg(message("runtime.hq.weather", sea_state=self.world.sea_state))
        self.feed.add(self.world.format_time(), "mission",
                      self._mission_started_notice())
        # Menu input cannot operate the simulation. Only this unstarted world
        # may be consumed by menu start; loads replace its world/sonar identity.
        self._prepared_menu_mission = (
            seed, self.scenario_key, self.world_mode, self.level,
            id(self.world), id(self.sonar)) if self.in_menu else None

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
        self.reset(int(definition["seed"]), "s4_zufall")
        self.subs, self.civilians, self.warships = [], [], []
        self.animals, self.asms = [], []
        player = definition["player"]
        self.ship.x, self.ship.y = self.world.nearest_water(player["x"], player["y"])
        self.ship.course = self.ship.target_course = float(player["course_deg"])
        self.ship.speed = self.ship.target_speed = config.clamp(
            float(player["speed_kn"]), 0.0, config.SHIP_SPEED_MAX_KN)
        self.ship.order_idx = min(range(len(config.TELEGRAPH_ORDERS)),
                                  key=lambda i: abs(config.TELEGRAPH_ORDERS[i][1]
                                                    - self.ship.target_speed))
        env = definition["environment"]
        self.world.hour = float(env["time_hour"])
        self.world.sea_state = int(env["sea_state"])
        thermo = float(env["thermocline_depth_m"])
        self.world._thermo = [[thermo for _ in row] for row in self.world._thermo]
        lv = config.LEVELS[self.level]
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
        self.in_menu = False
        self.main_menu = False
        self._reset_map_view()
        return True

    def flash(self, text: object, seconds: float = 3.0) -> None:
        self.msg = text
        self.msg_until = self._t + seconds

    def mission_name_display(self):
        """Keep authored mission text opaque while localizing built-ins."""
        if self.custom_mission_definition is not None:
            return raw_text(self.mission.name)
        keys = {"patrouille": "mission.patrol", "doppeljagd": "mission.double",
                "konvoi": "mission.convoy", "nuklearer_abfang": "mission.intercept"}
        return message(keys[self.mission.type_key])

    def mission_level_display(self):
        key = {"leicht": "easy", "normal": "normal", "harte": "hard"}[self.level]
        return message("level." + key)

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

    @property
    def time_scale(self) -> int:
        return config.TIME_SCALE_STEPS[self.time_scale_idx]

    def cycle_time_scale(self, delta: int) -> None:
        self.time_scale_idx = config.clamp(
            self.time_scale_idx + delta, 0, len(config.TIME_SCALE_STEPS) - 1)
        notice = message("status.speed", speed=self.time_scale)
        self.flash(notice, 1.5)
        self.feed.add(self.world.format_time(), "welt", notice)

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

    def _finish_numeric_input(self) -> None:
        """Validate and apply a pending course or speed order."""
        mode = self.input_mode
        value = self.input_buffer.replace(",", ".")
        try:
            number = float(value)
        except ValueError:
            self.flash(message("event.invalid_input"), 2.0)
            return
        if mode in ("course", "bearing"):
            if not 0.0 <= number < 360.0:
                self.flash(message("runtime.numeric.angle"), 2.0)
                return
            if mode == "bearing":
                self.sonar.set_listen_bearing(number)
                self._stop_sonar_audio()
                self.flash(message("runtime.numeric.true_bearing", bearing=f"{number:05.1f}"), 2.0)
            else:
                if self.damage.station_down("bridge"):
                    self.flash(message("event.bridge_down"))
                    self.input_mode = None
                    self.input_buffer = ""
                    return
                self.ship.target_course = number
                self.flash(message("runtime.numeric.course", course=f"{number:03.0f}"), 2.0)
                self.feed.add(self.world.format_time(), "navigation",
                              message("runtime.numeric.course_feed",
                                      course=f"{number:03.0f}"))
        else:
            if not 0.0 <= number <= config.SHIP_SPEED_MAX_KN:
                self.flash(message("runtime.numeric.speed",
                                   maximum=f"{config.SHIP_SPEED_MAX_KN:.0f}"), 2.0)
                return
            self.ship.target_speed = number
            self.ship.order_idx = min(range(len(config.TELEGRAPH_ORDERS)),
                                      key=lambda i: abs(config.TELEGRAPH_ORDERS[i][1]
                                                        - number))
            self.flash(message("runtime.numeric.speed_set", speed=f"{number:.1f}"), 2.0)
            self.feed.add(self.world.format_time(), "navigation",
                          message("runtime.numeric.speed_feed",
                                  speed=f"{number:.1f}"))
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
        elif len(pygame.key.name(key)) == 1 and pygame.key.name(key).isdigit():
            if len(self.input_buffer) < 5:
                self.input_buffer += pygame.key.name(key)
        elif key in (pygame.K_KP0, pygame.K_KP1, pygame.K_KP2, pygame.K_KP3,
                     pygame.K_KP4, pygame.K_KP5, pygame.K_KP6, pygame.K_KP7,
                     pygame.K_KP8, pygame.K_KP9):
            if len(self.input_buffer) < 5:
                self.input_buffer += pygame.key.name(key).strip("[]")
        elif (self.input_mode in ("speed", "bearing")
              and key in (pygame.K_PERIOD, pygame.K_COMMA, pygame.K_KP_PERIOD)
              and "." not in self.input_buffer):
            self.input_buffer += "."

    def _feed_ping(self, tgt, contact) -> None:
        """W1/W2: Ping-Echo-Feed inkl. Echolatenz (W3: Salzwasser-Schallfeld)."""
        dist = tgt.distance_nm(self.ship)
        latenz = self.world.echo_delay_s(dist)
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
                              speed=f"{config.SOUND_SPEED_M_S:.0f}",
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
        elif name == "large_text":
            self._apply_text_size()
        elif name == "tooltips":
            self.tooltips_enabled = bool(value)
            self.pinned_tooltip = None
            self._tooltip_anchor = None
        try:
            save_preferences(self.preferences)
        except OSError:
            self.flash(message("status.preferences_error"), 3.0)

    def compose_frame(self) -> None:
        """Virtuellen 1280x720-Canvas aufs Display bringen (M8/M9).

        FILL_SCREEN=True: Stretch auf die volle Fläche (keine schwarzen
        Balken bei 16:9); False: aspect-correctes Letterbox.
        """
        w, h = pygame.display.get_window_size()
        if w <= 0 or h <= 0:
            w, h = config.SCREEN_W, config.SCREEN_H
        self.display.fill((0, 0, 0))
        if (w, h) == (config.SCREEN_W, config.SCREEN_H):
            self.display.blit(self.screen, (0, 0))
        elif config.FILL_SCREEN:
            self.display.blit(pygame.transform.scale(self.screen, (w, h)),
                              (0, 0))
        else:
            _, ox, oy, sw, sh = letterbox_layout(w, h)
            self.display.blit(
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
                or self.save_ui is not None or self.options_open or self.commander_open)

    def _clear_controls(self) -> None:
        self.held.clear()
        self._joy_turn = 0
        self._joy_acc = 0.0
        self._joy_x_acc = 0.0
        self._map_drag = None
        self._map_drag_moved = False
        self._stop_sonar_audio()

    def _stop_sonar_audio(self) -> None:
        self.audio.stop_sonar()
        self.sonar.reset_audition_audio()
        self._sonar_audio_sequence = -1
        self._sonar_audio_suspended = False

    def _open_administration(self, name: str) -> None:
        """One administrative owner; manual/focus pause remains independent."""
        self._clear_controls()
        self.input_mode = None
        self.input_buffer = ""
        self.help_open = name == "help"
        self.nations_open = name == "nations"
        self.quit_confirm = name == "quit"
        self.save_ui = name if name in ("save", "load") else None
        self.options_open = name == "options"
        self.commander_open = name == "commander"
        if self.commander_open:
            self.commander.prepare()
        self.quit_selection = 0
        self.quit_after_save = False
        self.save_confirm = False
        self.msg = ""
        self.help_page = 0
        self.help_scroll = 0
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
            if key == pygame.K_ESCAPE:
                self.options_open = False
            elif key in (pygame.K_UP, pygame.K_DOWN):
                self.options_sel = (self.options_sel + (1 if key == pygame.K_DOWN else -1)) % 6
            elif key in (pygame.K_LEFT, pygame.K_RIGHT, pygame.K_RETURN, pygame.K_KP_ENTER):
                if self.options_sel == 5:
                    self._open_administration("commander")
                    return
                names = ("language", "fullscreen", "audio", "large_text",
                         "tooltips")
                name = names[self.options_sel]
                value = ("de" if self.preferences.language == "en" else "en") \
                    if name == "language" else not getattr(self.preferences, name)
                self._set_preference(name, value)
        elif self.quit_confirm:
            choices = (0, 2) if self.in_menu else (0, 1, 2)
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
                self.help_page = (self.help_page + (-1 if key == pygame.K_LEFT else 1)) % 3
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
        if canvas is None or self.station not in MAP_STATIONS:
            return None
        if not pygame.Rect(config.MAP_RECT).collidepoint(canvas):
            return None
        return canvas

    def tooltip_at(self, canvas_pos):
        """Return serializable context for the meaningful visual under the pointer."""
        if (not self.tooltips_enabled or canvas_pos is None or self.in_menu
                or self.game_over or self.administration_open):
            return None
        previous = config.STATION_RECT
        config.STATION_RECT = (config.STATION_PANEL_RECT
                               if self.station in MAP_STATIONS
                               else config.FULL_STATION_RECT)
        try:
            if (self.station in MAP_STATIONS
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

    def handle_event(self, e) -> None:
        # Observe actual input transitions, not candidate restoration. Two owner
        # changes within one wall frame must still invalidate queued commands.
        fields = ("paused", "in_menu", "main_menu", "splash_active", "input_mode",
                  "help_open", "nations_open", "quit_confirm", "save_ui",
                  "options_open", "commander_open", "running", "game_over")
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
            self._clear_controls()
            if not self.in_menu and not self.game_over:
                self.paused = True
                self.flash(message("runtime.focus_lost"), 3.0)
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
                self._open_administration("quit")
                return
            if (e.type == pygame.KEYDOWN and e.key == pygame.K_F5
                    and isinstance(self.editor, MissionEditor)
                    and self.editor.mode == "browser"):
                selected = self.editor.selected
                if selected is not None and not selected.builtin:
                    if self.start_custom_mission(selected.data):
                        self.editor = None
                    else:
                        self.editor.status = self.tr("editor.runtime_unsupported")
                return
            if (e.type == pygame.KEYDOWN and e.key == pygame.K_ESCAPE
                    and getattr(self.editor, "mode", "browser") == "browser"):
                self.editor = None
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
        if e.type == pygame.MOUSEBUTTONUP and e.button == 1:
            if self._map_drag is not None and not self._map_drag_moved:
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
                self._handle_administration_key(e.key)
            elif e.type == pygame.MOUSEBUTTONDOWN and e.button == 1:
                canvas = self._window_to_canvas(getattr(e, "pos", None))
                if canvas is not None:
                    if self.commander_open:
                        self.commander.handle_click(self, canvas)
                    elif self.options_open:
                        for index, rect in enumerate(self._options_row_rects()):
                            if rect.collidepoint(canvas):
                                self.options_sel = index
                                if index == 5:
                                    self._open_administration("commander")
                                break
            return
        if e.type != pygame.KEYDOWN:
            if self.input_mode is not None or self.paused or self.in_menu or self.game_over:
                return
            if self.commander.confirm_visible(self):
                if e.type == pygame.MOUSEBUTTONDOWN and e.button == 1:
                    canvas = self._window_to_canvas(getattr(e, "pos", None))
                    if (canvas is not None
                            and self.commander.handle_confirm_click(self, canvas)):
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
            if self.input_mode is not None:
                if e.key == pygame.K_ESCAPE or not self.paused:
                    self._handle_numeric_input(e.key)
                elif e.key == pygame.K_p:
                    self.paused = False
                return
            if e.key == pygame.K_F9:
                self._open_administration("commander")
                return
            if e.key == pygame.K_p and self.commander.confirm_visible(self):
                self._clear_controls()
                self.paused = not self.paused
                self.flash(message("status.paused" if self.paused else "status.resumed"))
                return
            if self.commander.confirm_visible(self):
                if self.commander.handle_confirm_key(self, e.key):
                    return
            if e.key == pygame.K_ESCAPE:
                self._open_administration("quit")
                return
            if e.key == pygame.K_F1:
                self._open_administration("help")
                return
            if e.key == pygame.K_F10 or (e.key == pygame.K_o and self.paused):
                self._open_administration("options")
                return
            if e.key == pygame.K_n and self.station is not Station.SONAR:
                self._open_administration("nations")
                return
            if e.key in (pygame.K_s, pygame.K_l):
                self._open_administration("save" if e.key == pygame.K_s else "load")
                return
            if e.key == pygame.K_p and not self.game_over:
                self._clear_controls()
                self.paused = not self.paused
                self.flash(message("status.paused" if self.paused else "status.resumed"))
                return
            if pygame.K_1 <= e.key <= pygame.K_9:
                self._clear_controls()
                self.pinned_tooltip = None
                self._tooltip_anchor = None
                destination = list(Station)[e.key - pygame.K_1]
                if destination is self.station:
                    if len(STATION_PAGES[self.station]) > 1:
                        self.sonar_page = station_page_step(
                            self.station, self.sonar_page, 1)
                else:
                    self.station = destination
                return
            if e.key == pygame.K_TAB:
                self._clear_controls()
                self.pinned_tooltip = None
                self._tooltip_anchor = None
                order = list(Station)
                step = -1 if getattr(e, "mod", 0) & pygame.KMOD_SHIFT else 1
                self.station = order[(order.index(self.station) + step) % len(order)]
                return
            if self.game_over:
                if e.key == pygame.K_r:
                    self.reset(self.seed)
                return
            if self.paused:
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
            if self.station is Station.SONAR:
                if e.key in (pygame.K_PAGEUP, pygame.K_PAGEDOWN):
                    self.sonar_page = station_page_step(
                        Station.SONAR,
                        self.sonar_page, 1 if e.key == pygame.K_PAGEDOWN else -1)
                    return
                if e.key == pygame.K_e:
                    if self.sonar.measure_environment(self.world, self.ship,
                                                      self.sim_t):
                        depth = self.sonar.bt_profile["thermocline_m"]
                        self.flash(message("runtime.bt.measured", depth=f"{depth:.0f}"))
                        self.feed.add(self.world.format_time(), "sonar",
                                      message("runtime.bt.feed", depth=f"{depth:.0f}"))
                    else:
                        self.flash(message("runtime.bt.cooldown",
                                           seconds=f"{self.sonar.bt_cooldown:.0f}"))
                    return
                if e.key in (pygame.K_u, pygame.K_v):
                    depth = self.sonar.adjust_towed_depth(
                        -10.0 if e.key == pygame.K_u else 10.0,
                        self.ship.speed)
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
                if e.key == pygame.K_d:
                    self.sonar.listen_filtered = not self.sonar.listen_filtered
                    self._stop_sonar_audio()
                    self.flash(message("runtime.listen.filtered" if self.sonar.listen_filtered
                                       else "runtime.listen.broadband"))
                    return
                if e.key in (pygame.K_COMMA, pygame.K_PERIOD):
                    self.sonar_volume = round(config.clamp(self.sonar_volume +
                        (.1 if e.key == pygame.K_PERIOD else -.1), 0.0, 1.0), 1)
                    self.flash(message("runtime.listen.volume",
                                       volume=f"{self.sonar_volume:.0%}"))
                    self._stop_sonar_audio()
                    return
                if e.key in (pygame.K_LEFT, pygame.K_RIGHT):
                    mods = getattr(e, "mod", 0)
                    step = .1 if mods & pygame.KMOD_CTRL else (5.0 if mods & pygame.KMOD_SHIFT else .5)
                    self.sonar.set_listen_bearing(self.sonar.listen_bearing +
                                                 (step if e.key == pygame.K_RIGHT else -step))
                    self._stop_sonar_audio()
                    return
                if e.key in (pygame.K_UP, pygame.K_DOWN):
                    self._cycle_selected_contact(1 if e.key == pygame.K_DOWN else -1)
                    return
                if e.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                    contact = self.selected_contact
                    if self.sonar.focus_locked:
                        self.sonar.focus_locked = False
                        self.flash(message("runtime.listen.manual"))
                    elif contact is not None and self.sim_t - contact.last_seen <= 2.0:
                        self.sonar.set_listen_bearing(contact.bearing)
                        self.sonar.focus_locked = True
                        self.flash(message("runtime.listen.follow", contact=contact.id))
                    else:
                        self.flash(message("runtime.listen.no_contact"))
                    self._stop_sonar_audio()
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
                    self.ship.cycle_telegraph(
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
                    self.damage.unassign_team(self.dmg_team)
                    self.flash(message("runtime.team.withdrawn", team=self.dmg_team))
                else:
                    self._assign_selected_team()
                return
            if e.key in (pygame.K_RETURN, pygame.K_KP_ENTER) \
                    and self.station is Station.RADIO:
                self.capture_hfdf()
                return
            if e.key in (pygame.K_LEFTBRACKET, pygame.K_z):
                self.cycle_time_scale(-1)
            elif e.key in (pygame.K_RIGHTBRACKET, pygame.K_x):
                self.cycle_time_scale(1)
            elif e.key == pygame.K_n:
                if self.station is Station.SONAR:
                    self.sonar.notch_enabled = not self.sonar.notch_enabled
                    self._stop_sonar_audio()
                    self.flash(message("runtime.notch.on" if self.sonar.notch_enabled
                                       else "runtime.notch.off"), 1.5)
                else:
                    self.nations_open = not self.nations_open
            elif e.key == pygame.K_SPACE and self.station is Station.SONAR:
                self.sonar.peak_hold = not self.sonar.peak_hold
                self.flash(message("runtime.peak_hold.on" if self.sonar.peak_hold
                                   else "runtime.peak_hold.off"), 1.5)
            elif e.key in (pygame.K_EQUALS, pygame.K_PLUS, pygame.K_KP_PLUS):
                self.ship.cycle_telegraph(1)
                self.flash(message("runtime.telegraph", order=self.ship.telegraph), 1.5)
            elif e.key in (pygame.K_MINUS, pygame.K_KP_MINUS):
                self.ship.cycle_telegraph(-1)
                self.flash(message("runtime.telegraph", order=self.ship.telegraph), 1.5)
            elif e.key in (pygame.K_i, pygame.K_o) and self.station is Station.SONAR:
                self._adjust_sonar_gain(-3.0 if e.key == pygame.K_i else 3.0)
            elif e.key == pygame.K_a:
                if self.station is Station.SONAR:
                    if self.damage.station_down("sonar"):
                        self.flash(message("runtime.sonar.down"), 3.0)
                    elif (self.sonar_mode == "TOWED"
                          and not self.sonar.tow_status(self.ship.speed)["available"]):
                        pass
                    elif self.sonar.fire_ping():
                        self.flash(message("runtime.ping.sent"), 1.5)
                        self.audio.play_ping()
                        factor = self._sonar_range_factor()
                        self.sonar.queue_ping(self.ship, self._sonar_targets(),
                                              self.world, self.sim_t, factor,
                                              mode=self.sonar_mode)
                elif self.station is Station.ENGINE:
                    self.ship.quiet_mode = not self.ship.quiet_mode
                    self.flash(message("runtime.quiet.on" if self.ship.quiet_mode
                                       else "runtime.quiet.off"))
            elif e.key == pygame.K_r:
                if self.game_over:
                    self.reset(self.seed)
                elif self.station in (Station.OPZ, Station.RADAR):
                    domain = ("air" if getattr(e, "mod", 0)
                              & pygame.KMOD_SHIFT else "surface")
                    self.toggle_radar(domain)
            elif e.key == pygame.K_m:
                if self.station in (Station.SONAR, Station.WEAPONS,
                                    Station.HELICOPTER):
                    self.set_target()
                elif self.station in (Station.OPZ, Station.RADAR):
                    self.designate_opz_track()
            elif e.key == pygame.K_u and self.station is Station.BRIDGE:
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
                    self._adjust_helo_waypoint(bearing_delta=15.0)
            elif e.key == pygame.K_c:
                if self.station is Station.SONAR:
                    self._cycle_classification()
                elif self.station in (Station.OPZ, Station.RADAR):
                    self._cycle_opz_affiliation()
                elif self.station is Station.ELOKA:
                    self._cycle_eloka_annotation()
            elif e.key == pygame.K_b:
                if self.station is Station.SONAR:
                    self._cycle_sonar_mode()
                elif self.station in (Station.WEAPONS, Station.HELICOPTER):
                    self.deploy_buoys()
            elif e.key == pygame.K_y:
                if self.station is Station.SONAR:
                    toggle_tas(self, self.tr)
            elif e.key == pygame.K_h and self.station in (Station.WEAPONS,
                                                          Station.HELICOPTER):
                self.toggle_helo()
            elif e.key == pygame.K_d:
                if self.station in (Station.WEAPONS, Station.HELICOPTER):
                    self.launch_helo_torpedo()
            elif e.key == pygame.K_v and self.station is Station.WEAPONS:
                self.deploy_nixie()
            elif e.key == pygame.K_e:
                if self.station in (Station.OPZ, Station.RADAR):
                    self.launch_essm()
                elif self.station in MAP_STATIONS:
                    self.map_view.set_rect(config.MAP_RECT)
                    self.map_view.zoom(config.MAP_ZOOM_WHEEL_FACTOR)
            elif e.key == pygame.K_g and self.station in (Station.OPZ,
                                                          Station.RADAR):
                self.launch_chaff()
            elif e.key == pygame.K_t:
                if self.station is Station.WEAPONS:
                    self.launch_torpedo()
                elif self.station is Station.SONAR:
                    self.sonar.tma_enabled = not self.sonar.tma_enabled
                    self.flash(message("runtime.tma.on" if self.sonar.tma_enabled
                                       else "runtime.tma.off"), 1.5)
            elif e.key == pygame.K_f:
                if self.station is Station.SONAR:
                    self._cycle_sonar_band()
            elif e.key == pygame.K_k:
                if self.station in MAP_STATIONS:
                    self.map_follow = not self.map_follow
                    self.flash(message("runtime.map_follow.on" if self.map_follow
                                       else "runtime.map_follow.off"), 1.5)
            elif e.key == pygame.K_q and self.station in MAP_STATIONS:
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
            canvas = self._window_to_canvas(getattr(e, "pos", None)
                                            or pygame.mouse.get_pos())
            if (self.station is Station.OPZ and canvas is not None
                    and opz_ppi_rect(config.FULL_STATION_RECT).collidepoint(canvas)):
                self._cycle_radar_range(1 if e.y > 0 else -1)
                return
            pointer = self._map_pointer(getattr(e, "pos", None))
            if pointer is None:
                return
            factor = config.MAP_ZOOM_WHEEL_FACTOR ** e.y
            self.map_view.set_rect(config.MAP_RECT)
            self.map_view.zoom(factor, pivot=pointer)
        elif e.type == pygame.MOUSEBUTTONDOWN:
            if e.button == 1 and not self.in_menu and not self.game_over:
                if self.station is Station.DAMAGE:
                    canvas = self._window_to_canvas(getattr(e, "pos", None))
                    previous = config.STATION_RECT
                    config.STATION_RECT = config.FULL_STATION_RECT
                    try:
                        compartment = damage_compartment_at(self, canvas)
                    finally:
                        config.STATION_RECT = previous
                    if compartment is not None:
                        self.dmg_cursor = list(self.damage.compartments).index(compartment)
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
                self.map_follow = False
                self.map_view.pan_px(dx, dy)
                self._map_drag = pointer

    def _assign_selected_team(self) -> None:
        destination = list(self.damage.compartments)[self.dmg_cursor]
        if self.damage.assign_team(self.dmg_team, destination):
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
        self.sonar_mode = "TOWED" if self.sonar_mode == "BOW" else "BOW"
        self.flash(message("runtime.sonar_array.towed" if self.sonar_mode == "TOWED"
                           else "runtime.sonar_array.bow"), 1.5)

    def _adjust_sonar_gain(self, delta: float) -> None:
        self.sonar.gain_db = config.clamp(self.sonar.gain_db + delta, -12.0, 24.0)
        self._stop_sonar_audio()
        self.flash(message("runtime.sonar_gain", gain=f"{self.sonar.gain_db:+.0f}"), 1.2)

    def _cycle_sonar_band(self) -> None:
        bands = ((0.0, 300.0), (4.0, 80.0), (8.0, 55.0), (20.0, 120.0))
        current = (self.sonar.band_low_hz, self.sonar.band_high_hz)
        try:
            index = bands.index(current)
        except ValueError:
            index = 0
        low, high = bands[(index + 1) % len(bands)]
        self.sonar.band_low_hz, self.sonar.band_high_hz = low, high
        self._stop_sonar_audio()
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
        if self.damage.station_down("opz"):
            self.flash(message("runtime.opz.disabled"))
            return
        if domain == "air":
            self.air_radar_on = not self.air_radar_on
            radar, active = "air", self.air_radar_on
        else:
            self.surface_radar_on = not self.surface_radar_on
            radar, active = "surface", self.surface_radar_on
        suffix = "on" if active else "off"
        self.hq_msg(message(f"runtime.emcon.{radar}.{suffix}.hq"))
        self.flash(message(f"runtime.emcon.{radar}.{suffix}"), 2.0)

    def _cycle_radar_range(self, delta: int) -> None:
        scales = config.RADAR_RANGE_SCALES_NM
        try:
            index = scales.index(float(self.opz_range_nm))
        except ValueError:
            index = len(scales) - 1
        index = max(0, min(len(scales) - 1, index + delta))
        self.opz_range_nm = scales[index]
        self.flash(message("runtime.radar.range", range=f"{self.opz_range_nm:.0f}"), 1.5)

    def radar_weather_severity(self) -> float:
        """0 bis Seegang 4; 0.5/1.0 erst bei schwerem Wetter 5/6."""
        return config.clamp(
            (self.world.sea_state - (config.RADAR_WEATHER_THRESHOLD - 1)) / 2.0,
            0.0, 1.0)

    def radar_effective_range(self, domain: str) -> float:
        loss = (config.RADAR_AIR_WEATHER_LOSS if domain == "air"
                else config.RADAR_SURFACE_WEATHER_LOSS)
        nominal = (config.RADAR_AIR_RANGE_NM if domain == "air"
                   else config.RADAR_SURFACE_RANGE_NM)
        return nominal * (1.0 - loss * self.radar_weather_severity())

    def radar_sweep_bearing(self) -> float:
        """Nautische Peilung: zunehmende Werte drehen Nord -> Ost rechtsherum."""
        return (self._t * config.RADAR_SWEEP_DEG_PER_S) % 360.0

    def toggle_helo(self) -> None:
        if self.helo.airborne:
            self.helo.order_return()
            self.flash(message("runtime.helo.return"))
        else:
            if self.damage.station_down("flightdeck"):
                self.flash(message("runtime.helo.deck_down"))
                return
            if self.helo.state == "VERLOREN":
                self.flash(message("runtime.helo.lost"))
                return
            self.helo.launch(self.ship)
            self.flash(message("runtime.helo.launch", torpedoes=self.helo.torps,
                               buoys=self.helo.buoys_left), 3.0)

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
        if not self.helo.airborne:
            self.flash(message("runtime.helo.not_airborne"))
            return
        if not self.helo.water_entry_clear(self.world):
            self.flash(message("runtime.helo.water_required"))
            return
        self.buoy_seq += 1
        buoy = self.helo.deploy_buoy(self.buoy_seq, world=self.world)
        if buoy is not None:
            self.buoys.append(buoy)
            self.flash(message("runtime.buoy.deployed", buoy=buoy.seq))
            self.feed.add(self.world.format_time(), "sonar",
                          message("runtime.buoy.active", buoy=buoy.seq))
        else:
            self.flash(message("event.no_buoys"))

    def launch_helo_torpedo(self) -> None:
        """Leichttorpedo vom HSP-5 (eigene Munition, nicht Fregatten-Rohre)."""
        if (self.target is None
                or self.sim_t - self.target.last_seen >= config.SONAR_CONTACT_LOST_S):
            self.target = None
            self.flash(message("runtime.target.invalid"))
            return
        blocked = self._target_affiliation_interlock()
        if blocked is not None:
            self.flash(message("runtime.roe.blocked",
                               affiliation=display_value("affiliation", blocked, self.tr)))
            return
        if self.roe == "STD" and not self._contact_range_fresh(self.target):
            self.flash(message("runtime.target.not_located"))
            return
        if self.target.player_class != "U_BOOT":
            self.flash(message("runtime.target.air_class"))
            return
        if not self.helo.airborne:
            self.flash(message("runtime.helo.not_airborne"))
            return
        if self.helo.torps <= 0:
            self.flash(message("runtime.helo_no_torpedoes"))
            return
        if not self.helo.water_entry_clear(self.world):
            self.flash(message("runtime.helo.water_required"))
            return
        tgt = self._find_target(self.target.target_id)
        lv = config.LEVELS[self.level]
        range_nm = (self.target.range_est if self.target.range_est is not None
                    else config.ROE_FREE_LAUNCH_RANGE_NM)
        use_fix = (self._contact_range_fresh(self.target)
                   and self.target.observed_x is not None
                   and self.target.observed_y is not None)
        datum = self.helo.release_datum_from_ship_observation(
            self.ship, self.target.bearing, range_nm,
            bearing_uncertainty_deg=max(0.0, (1.0 - self.target.quality) * 8.0),
            range_uncertainty_nm=self.target.range_sigma_nm or 0.0,
            datum_x=self.target.observed_x if use_fix else None,
            datum_y=self.target.observed_y if use_fix else None)
        torp = self.helo.drop_torpedo(
            tgt, self.torpedo_depth, self.torpedo_seq + 1,
            kill_dist_nm=lv["kill_dist_nm"], kill_depth_m=lv["kill_depth_m"],
            guidance_x=datum.x_nm, guidance_y=datum.y_nm, world=self.world)
        if torp is None:
            return
        self.torpedo_seq += 1
        self.torpedoes.append(torp)
        self.flash(message("runtime.helo_torpedo.launched",
                           torpedo=self.torpedo_seq), 2.0)
        self.feed.add(self.world.format_time(), "waffen",
                      message("runtime.helo_torpedo.feed",
                              torpedo=self.torpedo_seq, contact=self.target.id))

    def _cycle_asm_track(self, delta: int) -> None:
        n = len(self.asm_tracks())
        if n == 0:
            self.asm_sel = 0
            return
        self.asm_sel = (self.asm_sel + delta) % n

    def launch_essm(self) -> None:
        if self.damage.station_down("opz") or self.damage.station_degraded("opz"):
            self.flash(message("runtime.opz.degraded"))
            return
        if self.vls_cells <= 0:
            self.flash(message("runtime.vls.empty"))
            return
        tracks = self.asm_tracks()
        if not tracks:
            self.flash(message("runtime.asm.none"))
            return
        track = tracks[min(self.asm_sel, len(tracks) - 1)]
        if track.range_nm is None or track.range_nm > config.ESSM_RANGE_NM:
            self.flash(message("runtime.asm.range", range=f"{config.ESSM_RANGE_NM:.0f}"))
            return
        if (track.x is None or track.y is None
                or track.age(self.sim_t) > self.air_picture.stale_s):
            self.flash(message("runtime.asm.stale"))
            return
        tgt = next((a for a in self.asms if a.seq == track.target_id), None)
        course = math.degrees(math.atan2(track.x - self.ship.x,
                                        -(track.y - self.ship.y))) % 360.0
        self.essms.append(ESSM(self.ship.x, self.ship.y, course, tgt,
                               len(self.essms) + 1,
                               guidance_x=track.x, guidance_y=track.y,
                               target_id=track.target_id))
        self.vls_cells -= 1
        self.flash(message("runtime.essm.launched", cells=self.vls_cells), 2.0)

    def launch_chaff(self) -> None:
        if self.damage.station_down("opz"):
            self.flash(message("runtime.chaff.disabled"))
            return
        if self.chaff_cd > 0.0:
            self.flash(message("runtime.chaff.cooldown", seconds=f"{self.chaff_cd:.0f}"))
            return
        tracks = self.asm_tracks()
        if tracks:
            track = tracks[min(self.asm_sel, len(tracks) - 1)]
            a = next((item for item in self.asms
                      if item.seq == track.target_id and item.state == "LAUF"), None)
        else:
            a = None
        if a is not None and track.range_nm is not None \
                and track.range_nm <= config.CHAFF_RANGE_NM:
            broke = a.launch_chaff(self.rng_asm)
            self.chaff_cd = config.CHAFF_COOLDOWN_S
            self.flash(message("runtime.chaff.decoyed" if broke
                               else "runtime.chaff.jammed"))
        else:
            self.flash(message("runtime.chaff.none"))

    def deploy_nixie(self) -> None:
        """Deploy one finite towed acoustic countermeasure from own ship."""
        if len(self.nixies) >= MAX_TOWED_DECOYS:
            self.flash(message("runtime.nixie.active"))
            return
        if not self.nixie_store.fire():
            self.flash(message("runtime.nixie.empty"))
            return
        definition = self._ownship_loadout["countermeasure"]
        self.nixie_seq += 1
        self.nixies.append(TowedAcousticDecoy(
            self.nixie_seq, self.ship, life_s=definition["active_life_s"],
            tether_nm=definition["tether_nm"], depth_m=definition["depth_m"]))
        self.flash(message("runtime.nixie.deployed", count=self.nixie_store.remaining_total))

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
        elif self.station in (Station.BRIDGE, Station.ENGINE):
            self.ship.cycle_telegraph(-delta)
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
            self._stop_sonar_audio()
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

    def _update_air_picture(self) -> None:
        """Create noisy observations; consumers never receive world objects."""
        import random
        station_live = not self.damage.station_down("opz")
        surface_live = self.surface_radar_on and station_live
        air_live = self.air_radar_on and station_live
        surface_eff = self.radar_effective_range("surface")
        air_eff = self.radar_effective_range("air")
        error_scale = 1.0 + (config.RADAR_WEATHER_ERROR_GAIN
                             * self.radar_weather_severity())
        for c in self.civilians:
            if c.sunk:
                continue
            dist = c.distance_nm(self.ship)
            bearing = c.bearing_from_frigate(self.ship)
            aspect = config.aspect_rcs_factor(c.course, bearing)
            radar_eligible = surface_live and dist <= surface_eff * aspect
            radar_clear = radar_eligible and not self.world.land_blocks_line(
                self.ship.x, self.ship.y, c.x, c.y)
            if radar_eligible and radar_clear:
                rng = random.Random(c.sensor_seed * 3571 + int(self.sim_t * 2.0))
                bearing_error = config.RADAR_BEARING_ERR_DEG * error_scale
                brg = (bearing + rng.uniform(-bearing_error, bearing_error)) % 360.0
                range_error = config.RADAR_RANGE_ERR_FRAC * error_scale
                measured = max(0.0, dist * (1.0 + rng.uniform(
                    -range_error, range_error)))
                self.air_picture.observe(track_id=f"S-{c.id}", kind="AIS",
                    target_id=c.id, source="RADAR-S/AIS", bearing=brg,
                    range_nm=measured, observer_x=self.ship.x, observer_y=self.ship.y,
                    course=c.course, quality=.95, now=self.sim_t, label=c.name,
                    bearing_uncertainty_deg=bearing_error / math.sqrt(3.0))
        for w in self.warships:
            if w.sunk:
                continue
            dist = w.distance_nm(self.ship)
            bearing = w.bearing_from_frigate(self.ship)
            aspect = config.aspect_rcs_factor(w.course, bearing)
            radar_eligible = surface_live and dist <= surface_eff * aspect
            radar_clear = radar_eligible and not self.world.land_blocks_line(
                self.ship.x, self.ship.y, w.x, w.y)
            if radar_eligible and radar_clear:
                rng = random.Random(w.sensor_seed * 3571 + int(self.sim_t * 2.0))
                bearing_error = config.RADAR_BEARING_ERR_DEG * error_scale
                brg = (bearing + rng.uniform(-bearing_error, bearing_error)) % 360.0
                range_error = config.RADAR_RANGE_ERR_FRAC * error_scale
                measured = max(0.0, dist * (1.0 + rng.uniform(
                    -range_error, range_error)))
                self.air_picture.observe(track_id=f"W-{w.id}", kind="SURFACE",
                    target_id=w.id, source="RADAR-S", bearing=brg,
                    range_nm=measured, observer_x=self.ship.x, observer_y=self.ship.y,
                    course=None, quality=.9, now=self.sim_t,
                    label=f"W-{w.id}",
                    bearing_uncertainty_deg=bearing_error / math.sqrt(3.0))
        for f in self.flights.flights:
            dist = f.distance_nm(self.ship)
            bearing = f.bearing_to_frigate(self.ship)
            radar_eligible = air_live and dist <= air_eff
            radar_clear = radar_eligible and not self.world.land_blocks_line(
                self.ship.x, self.ship.y, f.x, f.y)
            if radar_eligible and radar_clear:
                rng = random.Random((f.seq + 10000) * 3571 + int(self.sim_t * 2.0))
                bearing_error = config.RADAR_BEARING_ERR_DEG * error_scale
                brg = (bearing + rng.uniform(-bearing_error, bearing_error)) % 360.0
                range_error = config.RADAR_RANGE_ERR_FRAC * error_scale
                measured = max(0.0, dist * (1.0 + rng.uniform(
                    -range_error, range_error)))
                self.air_picture.observe(track_id=f"A-{f.seq}", kind="FLG",
                    target_id=f.seq, source="RADAR-L", bearing=brg, range_nm=measured,
                    observer_x=self.ship.x, observer_y=self.ship.y, course=None,
                    quality=.85, now=self.sim_t, label=f"A-{f.seq}",
                    bearing_uncertainty_deg=bearing_error / math.sqrt(3.0))
        for a in self.asms:
            if a.state not in ("LAUF", "CHAFF"):
                continue
            dist = a.distance_nm(self.ship)
            if (a.jamming(self.ship) and dist <= config.ESM_RANGE_NM
                    and not self.world.land_blocks_line(
                        self.ship.x, self.ship.y, a.x, a.y)):
                noise = self._smooth_sensor_noise(
                    a.seq * 7919, self.sim_t, 5.0)
                brg = (a.bearing_to_frigate(self.ship)
                       + noise * 5.0) % 360.0
                self.air_picture.observe(track_id=f"M-{a.seq}", kind="ASM",
                    target_id=a.seq, source="HOJ", bearing=brg, range_nm=None,
                    observer_x=self.ship.x, observer_y=self.ship.y, course=None,
                    quality=.55, now=self.sim_t, label=f"A-{a.seq}",
                    jamming=True, bearing_uncertainty_deg=5.0 / math.sqrt(3.0))
            elif (air_live and dist <= air_eff
                  and not self.world.land_blocks_line(
                      self.ship.x, self.ship.y, a.x, a.y)):
                rng = random.Random(a.seq * 7919 + int(self.sim_t * 2.0))
                bearing_error = config.RADAR_BEARING_ERR_DEG * error_scale
                brg = (a.bearing_to_frigate(self.ship)
                       + rng.uniform(-bearing_error, bearing_error)) % 360.0
                range_error = config.RADAR_RANGE_ERR_FRAC * error_scale
                measured = max(0.0, dist * (1.0 + rng.uniform(
                    -range_error, range_error)))
                self.air_picture.observe(track_id=f"M-{a.seq}", kind="ASM",
                    target_id=a.seq, source="RADAR-L", bearing=brg, range_nm=measured,
                    observer_x=self.ship.x, observer_y=self.ship.y, course=None,
                    quality=.9, now=self.sim_t, label=f"A-{a.seq}",
                    bearing_uncertainty_deg=bearing_error / math.sqrt(3.0))
        self.air_picture.expire(self.sim_t)

    def radar_tracks(self) -> list:
        """Compatibility view of the persistent surface/air picture."""
        return [dict(kind=t.kind, track_id=t.track_id, target_id=t.target_id,
                     source=t.source, dist=t.range_nm, bearing=t.bearing,
                     x=t.x, y=t.y, course=t.course, quality=t.display_quality(
                         self.sim_t, self.air_picture.stale_s), label=t.label,
                     hostile=t.hostile, jamming=t.jamming,
                     age=t.age(self.sim_t), position_seen=t.position_seen,
                     bearing_uncertainty_deg=t.bearing_uncertainty_deg)
                for t in self.air_picture.tracks(self.sim_t)]

    def asm_tracks(self) -> list:
        return [t for t in self.air_picture.tracks(self.sim_t, ("ASM",))
                if t.source in ("RADAR", "RADAR-L", "HOJ")]

    def opz_tracks(self) -> list:
        """Aktuelle beobachtete CIC-Tracks, stabil nach Track-ID sortiert."""
        return self.air_picture.tracks(self.sim_t)

    def selected_opz_track(self):
        return next((track for track in self.opz_tracks()
                     if track.track_id == self.opz_selected_track_id), None)

    def designate_opz_track(self) -> None:
        """Hand an observed CIC track to weapons without exposing world truth."""
        track = self.selected_opz_track()
        if track is None:
            self.flash(message("runtime.cic.none"))
            return
        contact = next((c for c in self.sonar.contacts.values()
                        if c.target_id == track.target_id), None)
        if contact is None:
            self.flash(message("runtime.cic.no_solution"))
            return
        self.selected_contact = contact
        self.target = contact
        self.flash(message("runtime.cic.designated", track=track.track_id))

    def opz_affiliation(self, track_id: str) -> str:
        value = self.opz_affiliations.get(track_id, "UNKNOWN")
        return value if value in config.NATO_AFFILIATIONS else "UNKNOWN"

    def _cycle_opz_track(self, delta: int) -> None:
        tracks = self.opz_tracks()
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
        self.opz_affiliations[track.track_id] = value
        self.flash(message("runtime.cic.affiliation", track=track.track_id,
                           affiliation=display_value("affiliation", value, self.tr)), 2.0)

    def eloka_tracks(self) -> tuple:
        """Return detached passive intercepts in stable picture order."""
        return self.esm_picture.tracks(self.sim_t)

    def selected_eloka_track(self):
        return next((track for track in self.eloka_tracks()
                     if track.track_key == self.eloka_selected_track_key), None)

    def _cycle_eloka_track(self, delta: int) -> None:
        if self.damage.station_down("opz"):
            return
        tracks = self.eloka_tracks()
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

    def eloka_annotation(self, track_key: str) -> str | None:
        emitter_key = self.eloka_annotations.get(track_key)
        emitter = self.runtime_catalog.emitters.get(emitter_key)
        return emitter_key if emitter is not None and emitter.domain == "radar" else None

    def _cycle_eloka_annotation(self) -> None:
        if self.damage.station_down("opz"):
            self.flash(message("runtime.eloka.disabled"))
            return
        track = self.selected_eloka_track()
        if track is None:
            self.flash(message("runtime.eloka.none_select"))
            return
        choices = [candidate.emitter_key for candidate in rank_emitters(
            track, self.runtime_catalog.emitters,
            maximum=len(self.runtime_catalog.emitters))]
        current = self.eloka_annotation(track.track_key)
        index = choices.index(current) if current in choices else -1
        if index + 1 >= len(choices):
            self.eloka_annotations.pop(track.track_key, None)
            assignment = self.tr("common.unknown")
        else:
            assignment = choices[index + 1]
            self.eloka_annotations[track.track_key] = assignment
            while len(self.eloka_annotations) > ESM_MAX_ANNOTATIONS:
                del self.eloka_annotations[min(self.eloka_annotations)]
        self.flash(message("runtime.eloka.annotation",
                           track=track.track_key, assignment=assignment), 2.0)

    def eloka_correlations(self, track=None) -> tuple:
        """Compare ESM and public radar/sonar evidence without target identity."""
        if self.damage.station_down("opz"):
            return ()
        track = track or self.selected_eloka_track()
        if track is None:
            return ()
        raw_evidence = []
        for observed in self.air_picture._tracks.values():
            if (not isinstance(observed.source, str)
                    or not (observed.source.startswith("RADAR")
                            or observed.source.startswith("SONAR"))):
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
        else:
            def measurements():
                for actor in self.civilians + self.warships:
                    if actor.sunk or not actor.emitter:
                        continue
                    distance = actor.distance_nm(self.ship)
                    if (distance > config.ESM_RANGE_NM
                            or self.world.land_blocks_line(
                                self.ship.x, self.ship.y, actor.x, actor.y)):
                        continue
                    yield self._esm_measurement(
                        actor, actor.bearing_from_frigate(self.ship), distance,
                        self._emitter_profile(actor.signature_key), 100_000)
                for flight in self.flights.flights:
                    if not flight.radar_emitting:
                        continue
                    distance = flight.distance_nm(self.ship)
                    if (distance > config.ESM_RANGE_NM
                            or self.world.land_blocks_line(
                                self.ship.x, self.ship.y, flight.x, flight.y)):
                        continue
                    yield self._esm_measurement(
                        flight, flight.bearing_to_frigate(self.ship), distance,
                        self._emitter_profile(flight.akey), 200_000)

            self.esm_picture.observe_batch(measurements(), self.sim_t)
        if self.eloka_selected_track_key not in {
                track.track_key for track in self.eloka_tracks()}:
            self.eloka_selected_track_key = None

    def hfdf_bearings(self) -> list:
        """Current and recently retained HFDF observations."""
        return self.radio_picture.tracks(self.sim_t, ("HF",))

    def _update_radio_picture(self) -> None:
        """Measure transmitting emitters without publishing their positions."""
        if self.damage.station_down("radio"):
            self.radio_picture.expire(self.sim_t)
            return
        for sub in self.subs:
            if not sub.transmitting:
                continue
            dist = sub.distance_nm(self.ship)
            if dist > config.HFDF_RANGE_NM:
                continue
            if self.world.land_blocks_line(self.ship.x, self.ship.y, sub.x, sub.y):
                continue
            seed = getattr(sub, "sensor_seed", sub.id) * 777
            noise = self._smooth_sensor_noise(seed, self.sim_t, 10.0)
            brg = (sub.bearing_from_frigate(self.ship)
                   + noise * config.HFDF_BEARING_ERR_DEG) % 360.0
            self.radio_picture.observe(track_id=f"H-{sub.id}", kind="HF",
                target_id=sub.id, source="HFDF", bearing=brg, range_nm=None,
                observer_x=self.ship.x, observer_y=self.ship.y, course=None,
                quality=.55, now=self.sim_t, label=f"SIG-{sub.id:02d}",
                bearing_uncertainty_deg=config.HFDF_BEARING_ERR_DEG / math.sqrt(3.0))
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
        if report.age(self.sim_t) > config.RADAR_TRACK_STALE_S:
            self.flash(message("runtime.hfdf.stale"))
            return
        measurement = (report.measurement_history[-1]
                       if report.measurement_history else {})
        row = dict(track_id=report.track_id, label=report.label,
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
            self.flash(message("runtime.hfdf.logged", label=report.label,
                               bearing=f"{report.bearing:05.1f}"))
            return
        fix = self._bearing_intersection(previous, row)
        if fix is None:
            self.flash(message("runtime.hfdf.geometry"))
            return
        x, y, geometry = fix
        # Angular errors projected at the two measurement origins. This assumes
        # a stationary emitter throughout the bounded observation span.
        b1, b2 = math.radians(previous["bearing"]), math.radians(row["bearing"])
        sigma_rad = math.radians(config.HFDF_BEARING_ERR_DEG) / math.sqrt(3.0)
        v1 = sigma_rad ** 2 * ((x - previous["observer_x"]) ** 2
                              + (y - previous["observer_y"]) ** 2)
        v2 = sigma_rad ** 2 * ((x - row["observer_x"]) ** 2
                              + (y - row["observer_y"]) ** 2)
        xx = (math.sin(b2) ** 2 * v1 + math.sin(b1) ** 2 * v2) / geometry ** 2
        yy = (math.cos(b2) ** 2 * v1 + math.cos(b1) ** 2 * v2) / geometry ** 2
        xy = -(math.sin(b2) * math.cos(b2) * v1
               + math.sin(b1) * math.cos(b1) * v2) / geometry ** 2
        self.hfdf_fixes[report.track_id] = dict(
            label=report.label, x=x, y=y,
            sigma_nm=math.sqrt(max(0.0, (xx + yy + math.hypot(xx - yy, 2 * xy)) / 2)),
            covariance_nm2=(xx, xy, yy),
            t=row["t"])
        dist = math.hypot(x - row["observer_x"], y - row["observer_y"])
        bearing = math.degrees(math.atan2(
            x - row["observer_x"], -(y - row["observer_y"]))) % 360.0
        self.air_picture.observe(
            track_id=f"H-{report.target_id}", kind="SUB",
            target_id=report.target_id, source="HFDF-FIX", bearing=bearing,
            range_nm=dist, observer_x=row["observer_x"],
            observer_y=row["observer_y"],
            course=None, quality=max(.25, geometry), now=row["t"],
            label=report.label)
        self.flash(message("runtime.hfdf.fix", label=report.label), 3.0)
        self.feed.add(self.world.format_time(), "funk",
                      message("runtime.hfdf.feed", label=report.label))

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
                    self.asms.append(ASM(x, y, course,
                                         self._next_asm_sequence(),
                                         self.rng_asm))

    def _next_asm_sequence(self) -> int:
        self.asm_seq += 1
        return self.asm_seq

    def _maybe_spawn_asm(self) -> None:
        """M16: ASM-Wellen laut Missionsplan (zeitgesteuert, deterministisch)."""
        m = self.mission
        if self.asm_spawned >= m.asm_count:
            return
        need = (config.ASM_SPAWN_FIRST_S
                + self.asm_spawned * config.ASM_SPAWN_INTERVAL_S)
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
        self.asms.append(ASM(x, y, course, self._next_asm_sequence(), self.rng_asm))

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
        self.target = best
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
        if self.target.player_class not in ("U_BOOT", "KAMPFSCHIFF"):
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

    def _target_affiliation_interlock(self):
        """Return a protected OPZ affiliation for the assigned sonar target."""
        if self.target is None:
            return None
        # Operator annotations outlive measurements. Aircraft/missile sequence
        # IDs are a separate namespace and must not annotate a sonar target.
        affiliations = [self.opz_affiliation(f"{prefix}-{self.target.target_id}")
                        for prefix in ("U", "S", "W")]
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
            self._stop_sonar_audio()

    def _cycle_classification(self) -> None:
        if self.selected_contact is None:
            self.flash(message("runtime.contact.none_selected"))
            return
        if self.selected_contact.target_id not in self.sonar.contacts:
            self.selected_contact = None
            return
        c = self.selected_contact
        order = [None] + list(config.PLAYER_CLASSES)
        c.player_class = order[(order.index(c.player_class) + 1) % len(order)]
        self.flash(message("runtime.contact.classified", contact=c.id,
                           classification=display_value("classification",
                                                        c.player_class, self.tr)), 2.0)

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
        blocked = self._target_affiliation_interlock()
        if blocked is not None:
            self.flash(message("runtime.roe.blocked",
                               affiliation=display_value("affiliation", blocked, self.tr)))
            return
        if self.roe == "STD":
            if not self._contact_range_fresh(self.target):
                self.flash(message("runtime.target.not_located"))
                return
            if self.target.player_class not in ("U_BOOT", "KAMPFSCHIFF"):
                self.flash(message("runtime.target.not_classified"))
                return
        else:
            if self.target.player_class not in ("U_BOOT", "KAMPFSCHIFF"):
                self.flash(message("runtime.target.not_classified"))
                return
        active_torpedoes = len([t for t in self.torpedoes if t.state == "RUN"])
        salvo_limit = config.TORP_MAX_IN_AIR[config.TORP_DOCTRINE]
        if active_torpedoes >= salvo_limit:
            self.flash(message("runtime.salvo.limit", limit=salvo_limit))
            return
        if self.torpedo_count <= 0:
            self.flash(message("event.no_torpedoes"))
            return
        if self.player_torpedo_battery.ready_count <= 0:
            self.flash(message("runtime.torpedo.no_tube"))
            return
        if self.damage.station_down("weapons"):
            self.flash(message("runtime.weapons.down"))
            return
        if self.damage.station_degraded("weapons"):
            self.flash(message("runtime.weapons.degraded"))
            return
        tgt = self._find_target(self.target.target_id)
        self.torpedo_seq += 1
        if (self.target.observed_x is not None
                and self.target.observed_y is not None
                and self._contact_range_fresh(self.target)):
            est_x, est_y = self.target.observed_x, self.target.observed_y
        else:
            range_nm = (self.target.range_est if self.target.range_est is not None
                        else config.ROE_FREE_LAUNCH_RANGE_NM)
            est_x = self.ship.x + range_nm * math.sin(math.radians(self.target.bearing))
            est_y = self.ship.y - range_nm * math.cos(math.radians(self.target.bearing))
        course = math.degrees(math.atan2(est_x - self.ship.x,
                                         -(est_y - self.ship.y))) % 360.0
        weapon_key = self.player_torpedo_battery.fire()
        if weapon_key is None:
            self.flash(message("runtime.torpedo.no_tube"))
            return
        weapon_definition = next(
            item
            for item in self._ownship_loadout["weapons"]
            if item["key"] == weapon_key)
        profile_key = weapon_definition["runtime_profile_key"]
        profile = self.runtime_catalog.torpedoes[profile_key]
        self.torpedoes.append(Torpedo(self.ship.x, self.ship.y, course,
                                      self.torpedo_depth, tgt, self.torpedo_seq,
                                      kill_dist_nm=weapon_definition[
                                          "kill_dist_nm_by_level"][self.level],
                                      kill_depth_m=weapon_definition[
                                          "kill_depth_m_by_level"][self.level],
                                      guidance_x=est_x, guidance_y=est_y,
                                      profile=profile))
        self.torpedo_count = self.player_torpedo_battery.remaining_total
        self.audio.play_alert("launch")
        self.flash(message("runtime.torpedo.launched", torpedo=self.torpedo_seq), 2.0)
        self.feed.add(self.world.format_time(), "waffen",
                      message("runtime.torpedo.feed", torpedo=self.torpedo_seq,
                              contact=self.target.id))

    # --- Update ---

    def _sonar_range_factor(self) -> float:
        if self.damage.station_degraded("sonar"):
            return config.DMG_SONAR_DEGRADED_FACTOR
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
                                 launch_weapon_key=launch_weapon_key))

    def update(self, dt: float, audio_dt: float | None = None) -> None:
        """W0: Zeitraffer – sim_dt = dt * time_scale, Sub-Stepping gegen
        Tunneling (Torpedos/CIWS) bei hohen Faktoren. Kosmetische Timer
        (Flash, Scanline) bleiben reele Zeit (self._t). Die Audio-Cadence
        laeuft auf audio_dt (ungeklemmte Reelle Zeit aus dem Main-Loop);
        ohne audio_dt gilt der geklemmte dt-Rahmen."""
        wall_dt = audio_dt if audio_dt is not None else dt
        self.audio.debug_log(wall_dt, receiver=getattr(self.sonar, "receiver", None))
        if self.splash_active:
            splash_elapsed = self._t - self.splash_started_at
            ping_cycle = int(max(0.0, splash_elapsed) / SPLASH_PING_PERIOD_S)
            if ping_cycle != self._splash_ping_cycle:
                self._splash_ping_cycle = ping_cycle
                self.audio.play_ping()
            return
        if not self.running or self.in_menu or self.paused or self.game_over or self.administration_open:
            self.audio.stop()
            self._sonar_audio_sequence = -1
            return
        # Operator adjustments follow wall time; hull and weapon motion do not.
        turn, _ = self.steering_input()
        if not self.damage.station_down("bridge"):
            self.ship.steer_input(dt, turn, 0)
        if self.station is Station.WEAPONS:
            depth_dir = int(pygame.K_UP in self.held) - int(pygame.K_DOWN in self.held)
            self.torpedo_depth = config.clamp(
                self.torpedo_depth + depth_dir * 20.0 * dt, 10.0, 300.0)
        sim_dt = dt * self.time_scale
        n = max(1, int(math.ceil(sim_dt / config.PHYS_SUBSTEP_S)))
        n = min(n, config.PHYS_SUBSTEP_MAX)
        step = sim_dt / n
        for _ in range(n):
            self._update_sim(step)
            if self.game_over:
                break
        self.map_view.set_rect(config.MAP_RECT)
        if self.map_follow:
            self.map_view.cx, self.map_view.cy = self.ship.x, self.ship.y
            self.map_view.clamp_center()
        if not self.game_over:
            self._update_audio(wall_dt)
        else:
            self.audio.stop()
            self._sonar_audio_sequence = -1

    def _update_audio(self, dt: float) -> None:
        """Stream coherent 1x blocks and discard accelerated-time audio."""
        receiver = self.sonar.receiver
        listening = (self.station is Station.SONAR and self.sonar_audio_enabled
                     and not self.damage.station_down("sonar"))
        accelerated = self.time_scale != 1
        if accelerated:
            if not self._sonar_audio_suspended:
                self.audio.stop_sonar(immediate=True)
                self.sonar.reset_audition_audio()
            self._sonar_audio_suspended = True
            self._sonar_audio_sequence = receiver.sequence
        else:
            if self._sonar_audio_suspended:
                self.audio.stop_sonar(immediate=True)
                self.sonar.reset_audition_audio()
                self._sonar_audio_sequence = receiver.sequence
                self._sonar_audio_suspended = False
            if not listening:
                self._stop_sonar_audio()
            else:
                blocks = receiver.blocks_since(self._sonar_audio_sequence)
                if not blocks:
                    self.audio.hold_sonar()
                for sequence, samples in blocks:
                    if (self._sonar_audio_sequence < 0
                            or sequence != self._sonar_audio_sequence + 1):
                        self.audio.stop_sonar(immediate=True)
                        self.sonar.reset_audition_audio()
                    if not self.audio.play_sonar(
                            self.sonar.listening_samples(samples, block_id=sequence),
                            receiver.sample_rate, self.sonar_volume,
                            bearing_deg=self.sonar.listen_bearing,
                            listener_bearing_deg=self.ship.course):
                        break
                    self._sonar_audio_sequence = sequence
        self._audio_timer += dt
        due = self._audio_timer >= config.AUDIO_UPDATE_S
        if not due:
            return
        self._audio_timer %= config.AUDIO_UPDATE_S
        cavitation = 0.8 if self.ship.cavitating else 0.0
        self.audio.update_engine(self.ship.rpm(), blade_count=5,
                                 cavitation=cavitation,
                                 volume=0.0 if listening else 0.08 + 0.08 * self.ship.noise_level())

    def _update_navigation(self, dt: float) -> None:
        """Wendet Steuerung, Brückenschaden und Telegraph auf die Fregatte an."""
        if self.damage.station_down("bridge"):
            self.ship.target_course = self.ship.course
        self.ship.turn_rate_scale = (
            0.5 if self.damage.station_degraded("bridge") else 1.0)
        self.ship.speed_cap = self.damage.engine_speed_cap()
        self.world.update(dt)
        self.ship.update(dt, self.world)
        self._nav_warning_cd = max(0.0, self._nav_warning_cd - dt)
        if self.ship.grounded and self._nav_warning_cd <= 0.0:
            self._nav_warning_cd = 10.0
            self.flash(message("event.grounding"), 4.0)
            self.feed.add(self.world.format_time(), "navigation",
                          message("runtime.grounding.feed"))

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
        all_candidates = [ship_target, *actors, *self.animals, *self.decoys]
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
            suite.update(
                self.sim_t, actor, candidates, self.world, self.runtime_catalog,
                emcon={"radar": getattr(actor, "radar_emitting", False),
                       "ais": getattr(actor, "ais_transmitting", False)},
                unavailable=domains, degraded=degraded)
            # Explicit adapters preserve old profiles until their R10 migration;
            # the actor still receives only a detached observation.
            if not suite.controllers and actor.side == "hostile":
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
        for actor in actors:
            suite = actor.sensor_suite
            if not suite.controllers:
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
            if sub.sunk and not was_sunk:
                if sub.side == "hostile":
                    self.score += config.SCORE_SUNK
                else:
                    self.incident = True
                self.flash(message("runtime.sunk.sub"), 4.0)
                self.feed.add(self.world.format_time(), "mission",
                              message("runtime.sunk.sub_feed", contact=sub.id))
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
        self.helo.update(dt, self.ship, self.world,
                         recovery_available=not self.damage.station_down("flightdeck"))
        for buoy in self.buoys:
            buoy.update(dt)
        self.buoys = [buoy for buoy in self.buoys if buoy.active]
        if self.chaff_cd > 0.0:
            self.chaff_cd = max(0.0, self.chaff_cd - dt)

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
        """Aktualisiert ASM-Wellen, CIWS und ESSM-Abfangflugkoerper."""
        self._drain_warship_asm()
        self._maybe_spawn_asm()
        # One simulated-second burst cadence; probability uses the game rate.
        self.ciws_cooldown_s = max(0.0, getattr(self, "ciws_cooldown_s", 0.0) - dt)
        for asm in self.asms:
            asm.update(dt, self.ship, self.world)
            if asm.state == "TREFFER":
                hit = self.damage.torpedo_hit()
                self.flash(message("runtime.hit.asm", compartments=", ".join(
                    self.damage.compartments[k].name for k in hit)), 5.0)
            elif (asm.state in ("LAUF", "CHAFF")
                  and self.ciws_ammo >= config.CIWS_ROUNDS_PER_ATTEMPT
                  and asm.distance_nm(self.ship) <= config.CIWS_RANGE_NM
                  and self.ciws_cooldown_s <= 0.0
                  and not self.damage.station_down("opz")
                  and not self.world.land_blocks_line(
                      self.ship.x, self.ship.y, asm.x, asm.y)):
                self.ciws_ammo -= config.CIWS_ROUNDS_PER_ATTEMPT
                self.ciws_cooldown_s = 1.0
                if self.rng_asm.random() < 1.0 - math.exp(-config.CIWS_KILL_PPS):
                    asm.state = "ABGEFANGEN"
                    self.audio.play_alert("defense")
                    self.flash(message("runtime.ciws.intercepted"), 3.0)
        observed_asms = {track.target_id: track for track in self.asm_tracks()}
        for essm in self.essms:
            track = observed_asms.get(essm.target_id)
            if (not essm.seeker_acquired and track is not None
                    and track.x is not None and track.y is not None
                    and track.position_seen is not None
                    and self.sim_t - track.position_seen <= self.air_picture.stale_s):
                essm.guidance_x, essm.guidance_y = track.x, track.y
            essm.update(dt, candidates=self.asms, world=self.world)
        self.asms = [a for a in self.asms if a.state in ("LAUF", "CHAFF")]
        self.essms = [e for e in self.essms if e.state == "LAUF"]
        if publish_picture:
            self._update_air_picture()
            observed_threat = bool(self.asm_tracks())
            if observed_threat and not self.air_threat_reported:
                self.flash(message("runtime.threat.air"), 4.0)
                self.feed.add(self.world.format_time(), "waffen", message("runtime.threat.air"))
            self.air_threat_reported = observed_threat

    def _update_enemy_torpedoes(self, dt: float) -> None:
        """Erzeugt und bewegt Feindtorpedos; Treffer werden als Schaden gebucht."""
        self._drain_enemy_torpedoes()
        for torpedo in self.enemy_torpedoes:
            torpedo.update(dt, self.ship, world=self.world,
                           seeker_candidates=self.nixies)
        for torpedo in self.enemy_torpedoes:
            if torpedo.state == "HIT":
                hit = self.damage.torpedo_hit(self._incoming_hit_zone(torpedo))
                self.audio.play_alert("damage")
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
                    launch_weapon_key=weapon.weapon_key)
                payload.break_wire()
                self.torpedoes.append(payload)
            elif weapon.state == "FLIGHT":
                survivors.append(weapon)
        self.asrocs = survivors
        # A launch decision consumes this substep before flight begins.
        self._drain_asrocs()

    def _incoming_hit_zone(self, torpedo) -> str:
        """Naehert die getroffene Schiffszone aus der Angriffsrichtung an."""
        source_bearing = (torpedo.course + 180.0) % 360.0
        relative = config.angle_diff_deg(source_bearing, self.ship.course)
        if abs(relative) <= 45.0:
            return "bow"
        if abs(relative) >= 135.0:
            return "stern"
        return "starboard" if relative > 0.0 else "port"

    def _update_player_torpedoes(self, dt: float) -> None:
        """Bewegt eigene Torpedos und verarbeitet Treffer/Fehlkontakte."""
        for sub in self.subs:
            if (sub.sunk or sub.state == "SINKING"
                    or sub.memory["last_torpedo_age"] < config.SUB_EVADE_DURATION_S):
                continue
            for torpedo in self.torpedoes:
                if (torpedo.state == "RUN"
                        and math.hypot(torpedo.x - sub.x, torpedo.y - sub.y)
                        <= config.TORP_HOME_RANGE_NM
                        and not self.world.sonar_path_blocked(
                            torpedo.x, torpedo.y, torpedo.depth,
                            sub.x, sub.y, sub.depth)):
                    sub.alert_torpedo()
                    break
        for torpedo in self.torpedoes:
            target_id = getattr(torpedo.target, "id", None)
            contact = self.sonar.contacts.get(target_id)
            solution_fresh = self._contact_range_fresh(contact)
            if (solution_fresh and contact.observed_x is not None
                    and contact.observed_y is not None):
                torpedo.wire_update(contact.observed_x, contact.observed_y)
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
            if (isinstance(torpedo.target, SurfaceShip)
                    and torpedo.target.side != "hostile"):
                torpedo.target.sunk = True
                self.incident = True
                self.audio.play_alert("danger")
                self.flash(message("runtime.incident"), 6.0)
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
                    self.flash(message("runtime.sunk.warship"), 4.0)
                    self.feed.add(self.world.format_time(), "mission",
                                  message("runtime.sunk.warship_feed",
                                          contact=torpedo.target.id))
        self.torpedoes = alive

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
            return
        focus = (self._find_target(self.selected_contact.target_id)
                 if self.selected_contact else None)
        self.sonar.update(dt, self.sim_t, self.ship, targets, self.world,
                          range_factor=self._sonar_range_factor(),
                          mode=self.sonar_mode, buoys=self.buoys,
                           focus_tgt=focus,
                           own_cavitation=1.0 if self.ship.cavitating else 0.0,
                           advance_mechanics=False)
        for contact in self.sonar.active_contacts():
            bearing = (contact.passive_bearing
                       if contact.passive_bearing is not None else contact.bearing)
            range_nm = None
            if contact.observed_x is not None and contact.observed_y is not None:
                dx = contact.observed_x - self.ship.x
                dy = contact.observed_y - self.ship.y
                bearing = math.degrees(math.atan2(dx, -dy)) % 360.0
                range_nm = math.hypot(dx, dy)
            observed_kind = {
                "torpedo": "TORP",
                "animal": "SUB",
                "surface": "SURFACE",
            }.get(contact.kind, "UNKNOWN")
            self.air_picture.observe(
                track_id=f"U-{contact.target_id}",
                kind=observed_kind,
                target_id=contact.target_id,
                source=(f"SONAR-{contact.range_source.upper()}"
                        if contact.range_source else "SONAR-BRG"),
                bearing=bearing, range_nm=range_nm,
                observer_x=self.ship.x, observer_y=self.ship.y,
                course=contact.tma_course,
                quality=max(contact.quality, contact.confidence),
                now=contact.last_seen, label=f"K{contact.id}",
                position_time=contact.range_seen,
                bearing_uncertainty_deg=contact.bearing_uncertainty_deg)
        while self.sonar.echo_events:
            echo = self.sonar.echo_events.pop(0)
            self.feed.add(self.world.format_time(), "sonar",
                          message("runtime.echo.feed", contact=echo["contact_id"],
                                  bearing=f"{echo['bearing']:05.1f}",
                                  range=f"{echo['range_nm']:.1f}",
                                  depth=f"{echo['depth_m']:.0f}"))
            self.flash(message("runtime.echo.flash", contact=echo["contact_id"],
                               range=f"{echo['range_nm']:.1f}"), 2.0)
        for contact in self.sonar.active_contacts():
            if contact.id not in prev_cts:
                if contact.range_est:
                    key = ("runtime.contact.new_range_torpedo"
                           if contact.kind == "torpedo"
                           else "runtime.contact.new_range")
                else:
                    key = ("runtime.contact.new_bearing_torpedo"
                           if contact.kind == "torpedo"
                           else "runtime.contact.new_bearing")
                self.feed.add(self.world.format_time(), "sonar",
                              message(key,
                                      contact=contact.id,
                                      bearing=f"{contact.bearing:4.0f}",
                                      range=(f"{contact.range_est:.1f}"
                                             if contact.range_est else ""),
                                      origin=contact.origin))
                if (contact.kind == "torpedo"
                        and contact.target_id not in self._observed_enemy_torpedoes):
                    self._observed_enemy_torpedoes.add(contact.target_id)
                    self.flash(message("runtime.sonar.torpedo",
                                       contact=contact.id), 4.0)

    def _update_damage_and_mission(self, dt: float) -> None:
        """Fortschritt von Schaden, Flugverkehr und Missionszielen."""
        self.damage.update(dt)
        self.flights.update(dt, world=self.world)
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
        self._sensor_acc += dt
        publish_picture = self._sensor_acc >= .25
        if publish_picture:
            self._update_platform_sensors(self._sensor_acc)
        self._update_underwater_entities(dt)
        self._update_aviation(dt)
        self._esm_acc += dt
        self._radio_acc += dt
        self._slow_acc += dt
        self._update_air_defense(dt, publish_picture=publish_picture)
        # M13: Wetter-Hinweise per Teletype
        self.hq_timer -= dt
        if self.hq_timer <= 0.0:
            self.hq_timer = config.WEATHER_BULLETIN_PERIOD_S
            self.hq_msg(message("runtime.hq.profile", sea_state=self.world.sea_state,
                                depth=f"{self.world.thermocline_depth_m(self.ship.x, self.ship.y):.0f}"))
        self._update_enemy_torpedoes(dt)
        self._update_player_torpedoes(dt)
        # A payload entering the water starts moving on the next substep; the
        # current substep was already consumed by ASROC flight.
        self._update_asrocs(dt)
        if self._sensor_acc >= .25:
            sensor_dt = self._sensor_acc
            self._sensor_acc = 0.0
            self._update_sensors(sensor_dt)
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

    def _mission_time_warning(self) -> None:
        """Warn before a deadline so the player can react instead of guessing."""
        remaining = self.mission.remaining_s(self.mission_time)
        for threshold in (300.0, 120.0, 60.0):
            if remaining <= threshold and threshold not in self._mission_warnings:
                self._mission_warnings.add(threshold)
                minutes = int(threshold // 60)
                amount = minutes if minutes else 60
                suffix = "minutes" if minutes else "seconds"
                self.flash(message("runtime.deadline.warning_" + suffix,
                                   amount=amount), 4.0)
                self.feed.add(self.world.format_time(), "mission",
                              message("runtime.deadline.feed_" + suffix,
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
        self.flash(message("runtime.mission.won" if win
                           else "runtime.mission.lost"), 10.0)

    # --- M6: Speichern / Laden ---

    MAX_SAVED_ASMS = 512
    MAX_SAVED_PLAYER_TORPEDOES = 128
    MAX_SAVED_ESSMS = 128

    @staticmethod
    def _rng_state(r) -> list:
        st = r.getstate()
        return [st[0], list(st[1]), st[2]]

    def save_state(self) -> dict:
        """Return the complete canonical save state for this release."""
        entity_groups = {
            "sub": (Sub, self.subs), "animal": (Animal, self.animals),
            "surface": (SurfaceShip, self.civilians + self.warships),
            "decoy": (Decoy, self.decoys),
            "enemy_torpedo": (EnemyTorpedo, self.enemy_torpedoes),
        }
        entity_ids = {entity.id for _, entities in entity_groups.values()
                      for entity in entities}
        asm_ids = {a.seq for a in self.asms}
        return {
            "version": SAVE_VERSION,
            "save_schema": SAVE_SCHEMA,
            "platform_state_version": 1,
            "catalog_snapshot": self.runtime_catalog.runtime_snapshot(),
            "next_entity_ids": {
                key: max(cls._next_id, max((e.id + 1 for e in entities), default=0))
                for key, (cls, entities) in entity_groups.items()},
            "seed": self.seed,
            "mission_type": self.mission.type_key,
            "mission_time": self.mission_time,
            "score": self.score,
            "incident": self.incident,
            "mission_result": self.mission_result,
            "result_reason": self.result_reason,
            "ship": dict(x=self.ship.x, y=self.ship.y, course=self.ship.course,
                         target_course=self.ship.target_course,
                         speed=self.ship.speed, target_speed=self.ship.target_speed,
                         order_idx=self.ship.order_idx,
                         turn_rate_scale=self.ship.turn_rate_scale,
                         rudder_angle=self.ship.rudder_angle,
                         yaw_rate=self.ship.yaw_rate,
                         roll=self.ship.roll, pitch=self.ship.pitch,
                         quiet_mode=self.ship.quiet_mode,
                         clock=self.ship._clock),
            "torpedoes": dict(total=self.torpedo_total, count=self.torpedo_count,
                               depth=self.torpedo_depth),
            "asw": {
                "version": ASW_STATE_VERSION,
                "loadout": copy.deepcopy(self._ownship_loadout),
                "player_battery": self.player_torpedo_battery.serialize(),
                "countermeasure": self.nixie_store.serialize(),
                "nixies": [item.serialize() for item in self.nixies],
                "nixie_seq": self.nixie_seq,
                "asrocs": [item.serialize() for item in self.asrocs],
                "asroc_seq": self.asroc_seq,
            },
            "level": self.level,
            "mission_name": self.mission.name,
            "mission_runtime": dict(
                name=self.mission.name, win_mode=self.mission.win_mode,
                time_limit_s=self.mission.time_limit_s,
                asm_count=self.mission.asm_count,
                custom_definition=self.custom_mission_definition),
            "damage": dict(
                repair_mult=self.damage.repair_mult,
                compartments={k: dict(state=c.state, flood=c.flood, fire=c.fire)
                              for k, c in self.damage.compartments.items()},
                teams={str(k): v for k, v in self.damage.teams.items()}),
            "world": dict(hour=self.world.hour,
                           sea_state=self.world.sea_state,
                           weather_shift_timer=self.world.weather_shift_timer,
                           mode=self.world_mode,
                           generator=("natural-earth-v1"
                                      if self.world_mode == "procedural"
                                      else "fixed-reference-v1"),
                           coast=self.world.coast.to_dict()),
            "sonar_mode": self.sonar_mode,
            "sonar_controls": dict(
                gain_db=self.sonar.gain_db,
                band_low_hz=self.sonar.band_low_hz,
                band_high_hz=self.sonar.band_high_hz,
                notch_enabled=self.sonar.notch_enabled,
                peak_hold=self.sonar.peak_hold,
                focus_locked=self.sonar.focus_locked,
                tma_enabled=self.sonar.tma_enabled,
                listen_bearing=self.sonar.listen_bearing,
                listen_filtered=self.sonar.listen_filtered,
                sonar_page=self.sonar_page, audio_enabled=self.sonar_audio_enabled,
                volume=self.sonar_volume),
            "radars": dict(surface=self.surface_radar_on,
                           air=self.air_radar_on,
                           range_nm=self.opz_range_nm),
            "roe": self.roe,
            "asm_spawned": self.asm_spawned,
            "air_threat_reported": self.air_threat_reported,
            "asm_seq": max([self.asm_seq, self.asm_spawned] + list(asm_ids)
                           + [e.target_id for e in self.essms if e.target_id is not None]
                           + [t.target_id for t in self.air_picture._tracks.values()
                              if t.kind == "ASM"]),
            "warship_asm_seq": self.warship_asm_seq,
            "vls_cells": self.vls_cells,
            "ciws_ammo": self.ciws_ammo,
            "ciws_cooldown_s": self.ciws_cooldown_s,
            "air_picture": self.air_picture.serialize(),
            "opz_affiliations": dict(self.opz_affiliations),
            "esm": {
                "version": ESM_STATE_VERSION,
                "track_seq": self.esm_picture.track_seq,
                "picture": self.esm_picture.serialize(),
                "selected_track_key": self.eloka_selected_track_key,
                "annotations": [
                    {"track_key": track_key, "emitter_key": emitter_key}
                    for track_key, emitter_key in sorted(
                        self.eloka_annotations.items())
                ],
            },
            "radio_picture": self.radio_picture.serialize(),
            "radio_sel": self.radio_sel,
            "hfdf_log": self.hfdf_log,
            "hfdf_fixes": self.hfdf_fixes,
            "schedulers": dict(sensor=self._sensor_acc,
                                esm=self._esm_acc,
                                radio=self._radio_acc,
                               slow=self._slow_acc),
            "torpedo_seq": self.torpedo_seq,
            "buoy_seq": self.buoy_seq,
            "chaff_cd": self.chaff_cd,
            "hq_timer": self.hq_timer,
            "asm_sel": self.asm_sel,
            "dmg_cursor": self.dmg_cursor,
            "dmg_team": self.dmg_team,
            "messages": [list(m) for m in self.messages],
            "helo": dict(state=self.helo.state, x=self.helo.x, y=self.helo.y,
                          torpedo_profile_key=self.helo.torpedo_profile.key,
                          course=self.helo.course, torps=self.helo.torps,
                          buoys_left=self.helo.buoys_left, fuel_s=self.helo.fuel_s,
                          waypoint_x=self.helo.waypoint_x,
                          waypoint_y=self.helo.waypoint_y),
            "subs": [dict(id=s.id, x=s.x, y=s.y, depth=s.depth, course=s.course,
                           state=s.state, speed=s.speed, damage=s.damage,
                           torpedoes_left=s.torpedoes_left, heard_ping=s.heard_ping,
                           asw_battery=(s.weapon_battery.serialize()
                                        if s.weapon_battery is not None else None),
                           countermeasure_store=(s.countermeasure_store.serialize()
                                                 if s.countermeasure_store is not None
                                                 else None),
                          stype=s.stype.key, start_pos=s.start_pos,
                          evac_left=s.evac_left, sink_left=s.sink_left,
                           quiet_mult=s.quiet_mult, attack_mult=s.attack_mult,
                           attack_cooldown=s.attack_cooldown,
                           attack_left=s.attack_left,
                           fingerprint=s.fingerprint.to_dict(),
                          torpedo_alerted=s.torpedo_alerted,
                           decoy_cd=s._decoy_cd,
                           turn_left=s.turn_left, turn_delta=s.turn_delta,
                           target_course=s.target_course,
                           target_depth=s.target_depth,
                           evade_offset=s.evade_offset,
                          sensor_seed=s.sensor_seed,
                           memory={key: (None if key in (
                               "last_ping_age", "last_torpedo_age")
                               and value == float("inf") else value)
                               for key, value in s.memory.items()},
                           pending_torpedoes=list(s.pending_torpedoes),
                           pending_decoys=list(s.pending_decoys),
                           decision_reason=s.decision_reason,
                           platform=s.sensor_suite.serialize())
                     for s in self.subs],
            "animals": [dict(id=a.id, x=a.x, y=a.y, depth=a.depth,
                             course=a.course, speed=a.speed,
                              atype=a.atype.key, dead=a.dead,
                              turn_left=a.turn_left, turn_delta=a.turn_delta,
                              target_course=a.target_course,
                              target_depth=a.target_depth,
                             sensor_seed=a.sensor_seed)
                        for a in self.animals],
            "civilians": [dict(id=c.id, x=c.x, y=c.y, course=c.course,
                                speed=c.speed, name=c.name, sunk=c.sunk,
                                damage=c.damage, emitter=c.emitter,
                                depth=c.depth, signature_key=c.signature_key,
                                 turn_left=c.turn_left, turn_delta=c.turn_delta,
                                 target_course=c.target_course,
                                 target_speed=c.target_speed,
                                 orbit_direction=c.orbit_direction,
                                 sensor_contact=c.sensor_contact,
                                 sensor_contact_age=c.sensor_contact_age,
                                 sunk_score_awarded=c.sunk_score_awarded,
                                 sensor_seed=c.sensor_seed,
                                 fingerprint=c.fingerprint.to_dict(),
                                 platform=c.sensor_suite.serialize())
                          for c in self.civilians],
            "warships": [dict(id=w.id, x=w.x, y=w.y, course=w.course,
                               speed=w.speed, name=w.name, sunk=w.sunk,
                               damage=w.damage, emitter=w.emitter,
                               depth=w.depth, signature_key=w.signature_key,
                                turn_left=w.turn_left, turn_delta=w.turn_delta,
                                target_course=w.target_course,
                                target_speed=w.target_speed,
                                waypoint=(list(w.waypoint)
                                          if w.waypoint is not None else None),
                                orbit_direction=w.orbit_direction,
                                sensor_contact=w.sensor_contact,
                                sensor_contact_age=w.sensor_contact_age,
                                sunk_score_awarded=w.sunk_score_awarded,
                                 pending_asm=list(w.pending_asm),
                                 asroc_battery=(w.asroc_battery.serialize()
                                                if w.asroc_battery is not None
                                                else None),
                                 pending_asroc=list(w.pending_asroc),
                                 asw_last_seen=w.asw_last_seen,
                               sensor_seed=w.sensor_seed,
                               attack_left=w.attack_left,
                                anchor=(list(w.anchor)
                                        if w.anchor is not None else None),
                                fingerprint=w.fingerprint.to_dict(),
                                platform=w.sensor_suite.serialize())
                          for w in self.warships],
            "decoys": [dict(id=d.id, x=d.x, y=d.y, depth=d.depth,
                              course=d.course, speed=d.speed, life=d.life,
                              sensor_seed=d.sensor_seed,
                              profile_key=d.profile.key, source_id=d.source_id)
                       for d in self.decoys],
            # Phase 2: laufende Projektil-/Sensoren-Objekte
            "torpedoes_in_flight": [
                dict(x=t.x, y=t.y, course=t.course, depth=t.depth,
                     travel=t.travel, state=t.state, idx=t.idx,
                     target_depth=t.target_depth,
                      target_id=(t.target.id if t.target is not None
                                 and t.target.id in entity_ids else None),
                      speed_kn=t.speed_kn,
                      range_nm=t.range_nm, terminal_active=t.terminal_active,
                     guidance_x=t.guidance_x, guidance_y=t.guidance_y,
                      seeker_acquired=(t.seeker_acquired and t.target is not None
                                       and t.target.id in entity_ids),
                       profile_key=t.profile_key, launch_origin=t.launch_origin,
                       launch_platform_id=t.launch_platform_id,
                       launch_weapon_key=t.launch_weapon_key,
                     search_phase=t._search_phase, midcourse=t._midcourse,
                     midcourse_timer=t._midcourse_timer,
                     kill_dist_nm=t.kill_dist_nm, kill_depth_m=t.kill_depth_m)
                for t in self.torpedoes],
            "enemy_torpedoes": [
                dict(id=t.id, x=t.x, y=t.y, course=t.course, depth=t.depth,
                      travel=t.travel, idx=t.idx, profile_key=t.profile_key,
                      guidance_x=t.guidance_x, guidance_y=t.guidance_y,
                       terminal_active=t.terminal_active,
                       seeker_acquired=t.seeker_acquired,
                       launch_platform_id=t.launch_platform_id,
                       launch_weapon_key=t.launch_weapon_key,
                       seeker_target=("ship" if t._seeker_target is self.ship else
                                     f"nixie:{t._seeker_target.seq}"
                                     if t._seeker_target in self.nixies else None))
                for t in self.enemy_torpedoes],
            "asms": [dict(x=a.x, y=a.y, course=a.course, seq=a.seq,
                           state=a.state, jammer=a.jammer,
                           age_s=a.age_s, travel=a.travel,
                          chaff_left=a.chaff_left, broken=a.broken)
                     for a in self.asms],
            "essms": [dict(x=e.x, y=e.y, course=e.course, seq=e.seq,
                            state=e.state, travel=e.travel,
                            guidance_x=e.guidance_x, guidance_y=e.guidance_y,
                            track_target_id=e.target_id,
                            seeker_acquired=(e.seeker_acquired and e.target is not None
                                             and e.target.seq in asm_ids),
                            target_id=(e.target.seq if e.target is not None
                                       and e.target.seq in asm_ids else None))
                      for e in self.essms],
            "buoys": [dict(x=b.x, y=b.y, seq=b.seq, battery_s=b.battery_s)
                      for b in self.buoys],
            "flights": {
                "seq": self.flights._seq,
                "spawn_cd": self.flights._spawn_cd,
                "items": [dict(kind=f.kind, seq=f.seq,
                                 base_id=f.base_id,
                                 dest_id=f.dest.get("id") if f.dest else None,
                                 x=f.x, y=f.y, course=f.course,
                                 akey=f.akey,
                                  loiter_nm=f.loiter_nm,
                                  radar_emitting=f.radar_emitting,
                                  sensor_bearing=f.sensor_bearing, sensor_age=f.sensor_age,
                                 waypoints=getattr(f, "waypoints", None),
                                 waypoint_idx=getattr(f, "waypoint_idx", 0),
                                total_dist=f.total_dist,
                                traveled=f.traveled, active=f.active,
                                platform=f.sensor_suite.serialize())
                           for f in self.flights.flights],
            },
            "sonar": {
                "next_id": max(
                    self.sonar._next_contact_id,
                    max((contact.id + 1 for contact in self.sonar.contacts.values()),
                        default=1)),
                "contacts": {
                    str(cid): dict(
                        contact_id=c.id, target_id=c.target_id, origin=c.origin, kind=c.kind,
                        bearing=c.bearing, range_est=c.range_est,
                        range_sigma_nm=c.range_sigma_nm,
                        range_source=c.range_source, range_seen=c.range_seen,
                        confidence=c.confidence,
                        quality=c.quality, last_seen=c.last_seen,
                        depth_est=c.depth_est, depth_sigma_m=c.depth_sigma_m,
                        player_class=c.player_class,
                        signature=c.signature, snr=c.snr,
                        passive_bearing=c.passive_bearing,
                        raw_bearing=c.raw_bearing,
                        raw_bearings=c.raw_bearings,
                        passive_epoch=c._passive_epoch,
                        bearing_filter_t=c._bearing_filter_t,
                        bearing_filter_rate_deg_s=c._bearing_filter_rate_deg_s,
                        bearing_filter_uncertainty_deg=(
                            c._bearing_filter_uncertainty_deg),
                        bearing_uncertainty_deg=c.bearing_uncertainty_deg,
                        ping_pos=c.ping_pos,
                        observed_x=c.observed_x, observed_y=c.observed_y,
                        array_observations=c.array_observations,
                        fusion_status=c.fusion_status,
                        fusion_delta_deg=c.fusion_delta_deg,
                        fused_quality=c.fused_quality,
                        tma_pos=c.tma_pos, tma_course=c.tma_course,
                        tma_speed=c.tma_speed, tma_quality=c.tma_quality,
                        tma_seen=c.tma_seen, buoy_fixes=list(c.buoy_fixes[-80:]))
                    for cid, c in self.sonar.contacts.items()},
                "lofar": self.sonar.lofar_history,
                "lofar_times": self.sonar.lofar_times,
                "lofar_bearings": self.sonar.lofar_bearings,
                "broadband": self.sonar.broadband_history,
                "history_times": self.sonar.history_times,
                "tracks": {
                    str(target_id): [
                        dict(t=p.t, bearing=p.bearing, fx=p.fx, fy=p.fy,
                             fcourse=p.fcourse,
                             uncertainty_deg=p.uncertainty_deg)
                        for p in track.pts]
                    for target_id, track in self.sonar._tracks.items()},
                "track_versions": {
                    str(target_id): track.version
                    for target_id, track in self.sonar._tracks.items()},
                "tma_versions": {
                    str(target_id): version
                    for target_id, version in self.sonar._tma_versions.items()},
                "tma_next": {
                    str(target_id): next_t
                    for target_id, next_t in self.sonar._tma_next.items()},
                "pending_pings": [dict(target_id=p["target"].id,
                                        sent_at=p["sent_at"],
                                        ready_at=p["ready_at"],
                                        range_factor=p["range_factor"],
                                        mode=p["mode"],
                                        snapshot=dict(p["snapshot"]))
                                  for p in self.sonar._pending_pings
                                  if p["target"].id in entity_ids],
                "towed_depth_m": self.sonar.towed_depth_m,
                "towed_depth_target_m": self.sonar.towed_depth_target_m,
                "tow_state": self.sonar.tow_state.value,
                "tow_payout": self.sonar.tow_payout,
                "tow_heading_deg": self.sonar.tow_heading_deg,
                "tow_settle_s": self.sonar._tow_settle_s,
                "tow_handling_ok": self.sonar._tow_handling_ok,
                "ping_cooldown": self.sonar.ping_cooldown,
                "ping_active": self.sonar.ping_active,
                "ping_anim_timer": self.sonar._ping_anim_timer,
                "echo_history": list(self.sonar.echo_history),
                "bt_profile": self.sonar.bt_profile,
                "bt_cooldown": self.sonar.bt_cooldown,
            },
            "sim_t": self.sim_t,
            "time_scale_idx": self.time_scale_idx,
            "scenario_key": self.scenario_key,
            "ui": dict(
                station=self.station.name,
                target_id=self.target.target_id if self.target else None,
                selected_contact_id=(self.selected_contact.id
                                     if self.selected_contact else None),
                opz_selected_track_id=self.opz_selected_track_id,
                map_cx=self.map_view.cx, map_cy=self.map_view.cy,
                map_scale=self.map_view.scale,
                map_follow=self.map_follow,
                paused=self.paused,
                tooltips_enabled=getattr(self, "tooltips_enabled", True),
                pinned_tooltip=layout.valid_tooltip(
                    getattr(self, "pinned_tooltip", None)),
                tooltip_anchor=list(self._tooltip_anchor)
                if self._tooltip_anchor is not None else None,
            ),
            "rngs": {
                "world": self._rng_state(self.rng_world),
                "world_weather": self._rng_state(self.world.rng),
                "asm": self._rng_state(self.rng_asm),
                "damage": self._rng_state(self.damage.rng),
                "helo": self._rng_state(self.helo.rng),
                "sonar": self._rng_state(self.sonar.rng),
                "flight": self._rng_state(self.flights.rng),
                "asw": self._rng_state(self.rng_asw),
            },
        }

    def save_game(self, path: str = None) -> str:
        import tempfile
        path = path or config.SAVE_PATH
        parent = os.path.dirname(os.path.abspath(path))
        os.makedirs(parent, exist_ok=True)
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(mode="w", dir=parent, delete=False) as f:
                temporary = f.name
                json.dump(self.save_state(), f, indent=1, allow_nan=False)
                f.flush()
                os.fsync(f.fileno())
            os.replace(temporary, path)
        finally:
            if temporary is not None and os.path.exists(temporary):
                os.unlink(temporary)
        return path

    @staticmethod
    def _restore_rng(r: "random.Random", data) -> None:
        r.setstate((data[0], tuple(data[1]), data[2]))

    def load_state(self, data: dict) -> None:
        """Restore transactionally, including direct in-memory callers."""
        if not self._load_save_data(data):
            raise ValueError("invalid save state")

    def _restore_state(self, data: dict) -> None:
        import random

        def restore_entity(cls, *args, **kwargs):
            # Constructors allocate first. Account for these temporary IDs even
            # if a later constructor/restoration step fails.
            self._restore_id_allocations[cls] += 1
            return cls(*args, **kwargs)

        def restore_platform(entity, row, profile_key):
            state = row["platform"]
            side = state["side"]
            doctrine = state["doctrine"]
            entity.side = side
            entity.doctrine = doctrine
            entity.sensor_suite = PlatformSensorSuite(
                self.runtime_catalog, profile_key, entity.sensor_seed,
                side=side, doctrine=doctrine, now=self.sim_t,
                datalink_group=state["datalink_group"])
            entity.sensor_suite.restore(
                state, self.runtime_catalog, profile_key, self.sim_t)

        seed = data["seed"]
        w = data["world"]
        coast_data = w["coast"]
        coast = Coastline(coast_data, float(coast_data["world_nm"]))
        self.world_mode = w["mode"]
        self.world = World(seed=seed, coast=coast)
        self.world.hour = w["hour"]
        self.world.sea_state = w["sea_state"]
        self.world.weather_shift_timer = w["weather_shift_timer"]
        self.seed = seed
        self.sonar = SonarSystem(
            seed=seed, acoustic_profiles=self.runtime_catalog.acoustic_profiles)
        rng = random.Random(seed + 99999)
        self.rng_world = rng
        self.flights = FlightManager(
            self.world.coast, random.Random(seed + 2024), self.runtime_catalog)
        ship = data["ship"]
        self.ship = Ship(x_nm=ship["x"], y_nm=ship["y"],
                         course_deg=ship["course"])
        self.ship.target_course = ship["target_course"]
        self.ship.speed = ship["speed"]
        self.ship.target_speed = ship["target_speed"]
        self.ship.order_idx = ship["order_idx"]
        self.ship.turn_rate_scale = ship["turn_rate_scale"]
        self.ship.rudder_angle = ship["rudder_angle"]
        self.ship.yaw_rate = ship["yaw_rate"]
        self.ship.roll = ship["roll"]
        self.ship.pitch = ship["pitch"]
        self.ship.quiet_mode = ship["quiet_mode"]
        self.ship._clock = ship["clock"]
        self.mission = Mission(seed, type_key=data["mission_type"])
        runtime_mission = data["mission_runtime"]
        self.mission.name = runtime_mission["name"]
        self.mission.win_mode = runtime_mission["win_mode"]
        self.mission.time_limit_s = float(runtime_mission["time_limit_s"])
        self.mission.asm_count = runtime_mission["asm_count"]
        self.custom_mission_definition = runtime_mission["custom_definition"]
        if self.custom_mission_definition is not None:
            environment = self.custom_mission_definition.get("environment", {})
            thermo = environment.get("thermocline_depth_m")
            if isinstance(thermo, (int, float)) and not isinstance(thermo, bool):
                self.world._thermo = [[float(thermo) for _ in row]
                                      for row in self.world._thermo]
        self.mission_time = data["mission_time"]
        self.score = data["score"]
        self.incident = data["incident"]
        self.sim_t = data["sim_t"]
        saved_scale_idx = data["time_scale_idx"]
        self.time_scale_idx = saved_scale_idx
        self.scenario_key = data["scenario_key"]
        self.level = data["level"]
        tp = data["torpedoes"]
        self.torpedo_total = tp["total"]
        self.torpedo_count = tp["count"]
        self.torpedo_depth = tp["depth"]
        asw = data["asw"]
        self._ownship_loadout = copy.deepcopy(asw["loadout"])
        self.player_torpedo_battery = WeaponBattery.restore(
            asw["player_battery"])
        self.nixie_store = ConsumableStore.restore(asw["countermeasure"])
        self.nixies = [TowedAcousticDecoy.restore(row, self.ship)
                       for row in asw["nixies"]]
        self.nixie_seq = asw["nixie_seq"]
        self.asrocs = [ASROC.restore(row) for row in asw["asrocs"]]
        self.asroc_seq = asw["asroc_seq"]
        self.target = None
        self.selected_contact = None
        self.torpedoes = []
        self.enemy_torpedoes = []
        self.warships = []
        self.warship_anchor = None
        # Schadenszustand (Phase 2: repair_mult wiederherstellen)
        dmg = data["damage"]
        self.damage = DamageModel(random.Random(seed + 777),
                                  repair_mult=dmg["repair_mult"])
        for k, c in dmg["compartments"].items():
            self.damage.compartments[k].state = c["state"]
            self.damage.compartments[k].flood = c["flood"]
            self.damage.compartments[k].fire = c["fire"]
        self.damage.teams.update({int(k): v for k, v in dmg["teams"].items()})
        self.damage.total = sum(c.flood for c in self.damage.compartments.values())
        self.damage.ship_sunk = self.damage.total >= config.DMG_SHIP_SINK_TOTAL
        # M10–M16
        self.sonar_mode = data["sonar_mode"]
        sonar_controls = data["sonar_controls"]
        self.sonar.gain_db = sonar_controls["gain_db"]
        self.sonar.band_low_hz = sonar_controls["band_low_hz"]
        self.sonar.band_high_hz = sonar_controls["band_high_hz"]
        self.sonar.notch_enabled = sonar_controls["notch_enabled"]
        self.sonar.peak_hold = sonar_controls["peak_hold"]
        self.sonar.focus_locked = sonar_controls["focus_locked"]
        self.sonar.tma_enabled = sonar_controls["tma_enabled"]
        self.sonar.listen_bearing = sonar_controls["listen_bearing"]
        self.sonar.listen_filtered = sonar_controls["listen_filtered"]
        self.sonar.beam_width_deg = 6.0 if self.sonar_mode == "TOWED" else 12.0
        self.sonar._receiver_mode = self.sonar_mode
        self.sonar_page = sonar_controls["sonar_page"]
        self.sonar_audio_enabled = sonar_controls["audio_enabled"]
        self.sonar_volume = sonar_controls["volume"]
        self._sonar_audio_sequence = -1
        radars = data["radars"]
        self.surface_radar_on = radars["surface"]
        self.air_radar_on = radars["air"]
        self.opz_range_nm = radars["range_nm"]
        self.roe = data["roe"]
        self.asm_spawned = data["asm_spawned"]
        self.air_threat_reported = data["air_threat_reported"]
        self.vls_cells = data["vls_cells"]
        self.ciws_ammo = data["ciws_ammo"]
        self.ciws_cooldown_s = data["ciws_cooldown_s"]
        self.air_picture = TrackPicture(
            config.RADAR_TRACK_STALE_S, maximum=MAX_AIR_PICTURE_TRACKS)
        self.air_picture.restore(data["air_picture"])
        self.opz_affiliations = dict(data["opz_affiliations"])
        self.opz_selected_track_id = None
        self.esm_picture = ESMPicture()
        self.eloka_selected_track_key = None
        self.eloka_annotations = {}
        esm = data["esm"]
        self.esm_picture.restore(esm["picture"], esm["track_seq"], self.sim_t)
        self.eloka_selected_track_key = esm["selected_track_key"]
        self.eloka_annotations = {
            row["track_key"]: row["emitter_key"]
            for row in esm["annotations"]
        }
        self.radio_picture = TrackPicture(300.0)
        self.radio_picture.restore(data["radio_picture"])
        self.radio_sel = data["radio_sel"]
        self.hfdf_log = list(data["hfdf_log"])
        self.hfdf_fixes = dict(data["hfdf_fixes"])
        schedulers = data["schedulers"]
        self._sensor_acc = schedulers["sensor"]
        self._esm_acc = schedulers["esm"]
        self._radio_acc = schedulers["radio"]
        self._slow_acc = schedulers["slow"]
        self.torpedo_seq = data["torpedo_seq"]
        self.messages = [tuple(m) for m in data["messages"]]
        self.buoys = []
        self.buoy_seq = data["buoy_seq"]
        self.asms = []
        self.essms = []
        self.chaff_cd = data["chaff_cd"]
        self.dmg_cursor = data["dmg_cursor"]
        self.dmg_team = data["dmg_team"]
        self.asm_sel = data["asm_sel"]
        self.hq_timer = data["hq_timer"]
        self.rng_asm = random.Random(seed + 31337)
        self.rng_asw = random.Random(seed + 27182)
        self._joy_acc = 0.0
        self._joy_x_acc = 0.0
        self._joy_turn = 0
        hd = data["helo"]
        helo_profile_key = hd["torpedo_profile_key"]
        self.helo = Helicopter(
            random.Random(seed + 555),
            self.runtime_catalog.torpedoes[helo_profile_key])
        self.helo.state = hd["state"]
        self.helo.x, self.helo.y = hd["x"], hd["y"]
        self.helo.course = hd["course"]
        self.helo.torps = hd["torps"]
        self.helo.buoys_left = hd["buoys_left"]
        self.helo.fuel_s = hd["fuel_s"]
        self.helo.waypoint_x = hd["waypoint_x"]
        self.helo.waypoint_y = hd["waypoint_y"]
        # U-Boote (Phase 2: vollstaendiger KI-Zustand)
        self.subs = []
        for sd in data["subs"]:
            sub_profile = self.runtime_catalog.subs[sd["stype"]]
            decoy_profile = self.runtime_catalog.decoys[
                self.runtime_catalog.runtime_bindings["submarine_decoy"]]
            enemy_torpedo_profile = self.runtime_catalog.torpedoes[
                self.runtime_catalog.runtime_bindings["enemy_torpedo"]]
            s = restore_entity(Sub, sd["x"], sd["y"], depth_m=sd["depth"], course_deg=sd["course"],
                    stype_key=sd["stype"], rng=rng, profile=sub_profile,
                    decoy_profile=decoy_profile,
                    enemy_torpedo_profile=enemy_torpedo_profile,
                    side=sd["platform"]["side"],
                    runtime_catalog=self.runtime_catalog, asw_rng=self.rng_asw)
            s.id = sd["id"]
            s.start_pos = tuple(sd["start_pos"])
            s.state = sd["state"]
            s.speed = sd["speed"]
            s.damage = sd["damage"]
            s.torpedoes_left = sd["torpedoes_left"]
            if sd["asw_battery"] is not None:
                s.weapon_battery = WeaponBattery.restore(sd["asw_battery"])
            if sd["countermeasure_store"] is not None:
                s.countermeasure_store = ConsumableStore.restore(
                    sd["countermeasure_store"])
            s.heard_ping = sd["heard_ping"]
            s.evac_left = sd["evac_left"]
            s.sink_left = sd["sink_left"]
            s.sunk = sd["state"] == "SUNK"
            s.quiet_mult = sd["quiet_mult"]
            s.attack_mult = sd["attack_mult"]
            s.attack_cooldown = sd["attack_cooldown"]
            s.attack_left = sd["attack_left"]
            s.torpedo_alerted = sd["torpedo_alerted"]
            s._decoy_cd = sd["decoy_cd"]
            s.turn_left = sd["turn_left"]
            s.turn_delta = sd["turn_delta"]
            s.target_course = sd["target_course"]
            s.target_depth = sd["target_depth"]
            s.evade_offset = sd["evade_offset"]
            s.sensor_seed = sd["sensor_seed"]
            s.fingerprint = fingerprint_mod.Fingerprint.from_dict(
                sd["fingerprint"])
            restore_platform(s, sd, sd["stype"])
            s.memory.update(sd["memory"])
            for age in ("last_ping_age", "last_torpedo_age"):
                if s.memory[age] is None:
                    s.memory[age] = float("inf")
            s.pending_torpedoes = [tuple(row) for row in sd["pending_torpedoes"]]
            s.pending_decoys = [tuple(row) for row in sd["pending_decoys"]]
            s.decision_reason = sd["decision_reason"]
            self.subs.append(s)
        # Tiere
        self.animals = []
        for ad in data["animals"]:
            a = restore_entity(
                Animal, ad["x"], ad["y"], ad["atype"], rng=rng,
                depth_m=ad["depth"],
                profile=self.runtime_catalog.animals[ad["atype"]])
            a.id = ad["id"]
            a.course = ad["course"]
            a.speed = ad["speed"]
            a.dead = ad["dead"]
            a.turn_left = ad["turn_left"]
            a.turn_delta = ad["turn_delta"]
            a.target_course = ad["target_course"]
            a.target_depth = ad["target_depth"]
            a.sensor_seed = ad["sensor_seed"]
            self.animals.append(a)
        # Zivile
        self.civilians = []
        for cd in data["civilians"]:
            prof = self.runtime_catalog.surfaces[cd["signature_key"]]
            c = restore_entity(
                SurfaceShip, cd["x"], cd["y"], rng=rng, profile=prof,
                side=cd["platform"]["side"],
                doctrine=cd["platform"]["doctrine"],
                runtime_catalog=self.runtime_catalog)
            c.id = cd["id"]
            c.course = cd["course"]
            c.speed = cd["speed"]
            c.depth = cd["depth"]
            c.name = cd["name"]
            c.sunk = cd["sunk"]
            c.damage = cd["damage"]
            c.emitter = cd["emitter"]
            c.turn_left = cd["turn_left"]
            c.turn_delta = cd["turn_delta"]
            c.target_course = cd["target_course"]
            c.target_speed = cd["target_speed"]
            c.orbit_direction = cd["orbit_direction"]
            c.sensor_contact = (tuple(cd["sensor_contact"])
                                if cd["sensor_contact"] is not None else None)
            c.sensor_contact_age = cd["sensor_contact_age"]
            c.sunk_score_awarded = cd["sunk_score_awarded"]
            c.sensor_seed = cd["sensor_seed"]
            c.fingerprint = fingerprint_mod.Fingerprint.from_dict(
                cd["fingerprint"])
            restore_platform(c, cd, c.signature_key)
            self.civilians.append(c)
        # KAMPFSCHIFF: feindliche Kriegsschiffe (v4)
        self.warships = []
        for wd in data["warships"]:
            prof = self.runtime_catalog.surfaces[wd["signature_key"]]
            w = restore_entity(
                SurfaceShip, wd["x"], wd["y"], rng=rng,
                side=wd["platform"]["side"],
                doctrine=wd["platform"]["doctrine"],
                profile=prof, runtime_catalog=self.runtime_catalog)
            w.id = wd["id"]
            w.course = wd["course"]
            w.speed = wd["speed"]
            w.name = wd["name"]
            w.sunk = wd["sunk"]
            w.damage = wd["damage"]
            w.emitter = wd["emitter"]
            w.turn_left = wd["turn_left"]
            w.turn_delta = wd["turn_delta"]
            w.target_course = wd["target_course"]
            w.target_speed = wd["target_speed"]
            w.waypoint = (tuple(wd["waypoint"])
                          if wd["waypoint"] is not None else None)
            w.orbit_direction = wd["orbit_direction"]
            w.sensor_contact = (tuple(wd["sensor_contact"])
                                if wd["sensor_contact"] is not None else None)
            w.sensor_contact_age = wd["sensor_contact_age"]
            w.sunk_score_awarded = wd["sunk_score_awarded"]
            w.pending_asm = [tuple(row) for row in wd["pending_asm"]]
            if wd["asroc_battery"] is not None:
                w.asroc_battery = WeaponBattery.restore(wd["asroc_battery"])
            w.pending_asroc = [dict(row) for row in wd["pending_asroc"]]
            w.asw_last_seen = wd["asw_last_seen"]
            w.sensor_seed = wd["sensor_seed"]
            w.attack_left = wd["attack_left"]
            w.anchor = tuple(wd["anchor"]) if wd["anchor"] is not None else None
            w.fingerprint = fingerprint_mod.Fingerprint.from_dict(
                wd["fingerprint"])
            restore_platform(w, wd, w.signature_key)
            self.warships.append(w)
        # W2: Dekoys
        self.decoys = []
        for dd in data["decoys"]:
            decoy_key = dd["profile_key"]
            decoy_profile = self.runtime_catalog.decoys[decoy_key]
            d = restore_entity(
                Decoy, dd["x"], dd["y"], dd["depth"], rng,
                decoy_profile, self.runtime_catalog.acoustic_for(decoy_key),
                source_id=dd["source_id"])
            d.id = dd["id"]
            d.course = dd["course"]
            d.speed = dd["speed"]
            d.life = dd["life"]
            d.dead = False
            d.sensor_seed = dd["sensor_seed"]
            self.decoys.append(d)
        # Phase 2: laufende Entitaeten + Sensoren
        by_id = ({s.id: s for s in self.subs}
                  | {a.id: a for a in self.animals}
                  | {d.id: d for d in self.decoys}
                  | {c.id: c for c in self.civilians}
                  | {w.id: w for w in self.warships})
        for td in data["torpedoes_in_flight"]:
            tgt = by_id.get(td.get("target_id"))
            torpedo_key = td["profile_key"]
            profile = self.runtime_catalog.torpedoes[torpedo_key]
            t = Torpedo(td["x"], td["y"], td["course"],
                        td["target_depth"], tgt,
                        td["idx"],
                        kill_dist_nm=td["kill_dist_nm"],
                        kill_depth_m=td["kill_depth_m"],
                        speed_kn=td["speed_kn"],
                         guidance_x=td["guidance_x"], guidance_y=td["guidance_y"],
                         range_nm=td["range_nm"], profile=profile,
                         launch_origin=td["launch_origin"],
                         launch_platform_id=td["launch_platform_id"],
                         launch_weapon_key=td["launch_weapon_key"])
            t.depth = td["depth"]
            t.travel = td["travel"]
            t.seeker_acquired = td["seeker_acquired"]
            t.terminal_active = td["terminal_active"]
            t.state = td["state"]
            t._search_phase = td["search_phase"]
            t._midcourse = td["midcourse"]
            t._midcourse_timer = td["midcourse_timer"]
            self.torpedoes.append(t)
        for ed in data["enemy_torpedoes"]:
            enemy_key = ed["profile_key"]
            profile = self.runtime_catalog.torpedoes[enemy_key]
            self.enemy_torpedoes.append(
                restore_entity(EnemyTorpedo, ed["x"], ed["y"], ed["course"], ed["depth"],
                                 ed["idx"], profile=profile,
                                 guidance_x=ed["guidance_x"],
                                 guidance_y=ed["guidance_y"],
                                 launch_platform_id=ed["launch_platform_id"],
                                 launch_weapon_key=ed["launch_weapon_key"]))
            self.enemy_torpedoes[-1].travel = ed["travel"]
            self.enemy_torpedoes[-1].id = ed["id"]
            self.enemy_torpedoes[-1].terminal_active = ed["terminal_active"]
            self.enemy_torpedoes[-1].seeker_acquired = ed["seeker_acquired"]
            seeker_target = ed["seeker_target"]
            self.enemy_torpedoes[-1]._seeker_target = (
                (self.ship if seeker_target == "ship" else
                 next((item for item in self.nixies
                       if seeker_target == f"nixie:{item.seq}"), None))
                if self.enemy_torpedoes[-1].seeker_acquired else None)
        by_id.update((t.id, t) for t in self.enemy_torpedoes)
        for torpedo, td in zip(self.torpedoes, data["torpedoes_in_flight"]):
            torpedo.target = by_id.get(td.get("target_id"))
            torpedo._seeker_target = torpedo.target if torpedo.seeker_acquired else None
        self.asms = []
        for a in data["asms"]:
            asm = ASM(a["x"], a["y"], a["course"], a["seq"], self.rng_asm)
            asm.state = a["state"]
            asm.jammer = a["jammer"]
            asm.chaff_left = a["chaff_left"]
            asm.broken = a["broken"]
            asm.age_s = a["age_s"]
            asm.travel = a["travel"]
            self.asms.append(asm)
        self.warship_asm_seq = data["warship_asm_seq"]
        self.essms = []
        for e in data["essms"]:
            tgt = next((a for a in self.asms if a.seq == e.get("target_id")),
                       None)
            essm = ESSM(e["x"], e["y"], e["course"], tgt, e["seq"],
                        guidance_x=e["guidance_x"],
                        guidance_y=e["guidance_y"],
                        target_id=e["track_target_id"])
            essm.travel = e["travel"]
            essm.state = e["state"]
            essm.seeker_acquired = e["seeker_acquired"]
            self.essms.append(essm)
        self.asm_seq = data["asm_seq"]
        for bd in data["buoys"]:
            b = Sonobuoy(bd["x"], bd["y"], bd["seq"])
            b.battery_s = bd["battery_s"]
            self.buoys.append(b)
        flight_data = data["flights"]
        bases = {b["id"]: b for b in self.world.coast.airbases}
        restored = []
        for fd in flight_data["items"]:
                base = bases[fd["base_id"]]
                dest = bases.get(fd["dest_id"])
                flight = Flight(fd["kind"], base, dest=dest,
                                loiter_nm=fd["loiter_nm"],
                                 rng=self.flights.rng, seq=fd["seq"],
                                 akey=fd["akey"], catalog=self.runtime_catalog,
                                 side=fd["platform"]["side"],
                                 doctrine=fd["platform"]["doctrine"])
                flight.x = fd["x"]
                flight.y = fd["y"]
                flight.course = fd["course"]
                flight.total_dist = fd["total_dist"]
                flight.traveled = fd["traveled"]
                flight.radar_emitting = fd["radar_emitting"]
                flight.sensor_bearing = fd["sensor_bearing"]
                flight.sensor_age = fd["sensor_age"]
                flight.active = fd["active"]
                restore_platform(flight, fd, flight.akey)
                if flight.dest is None and fd["waypoints"]:
                    flight.waypoints = [tuple(p) for p in fd["waypoints"]]
                    flight.waypoint_idx = fd["waypoint_idx"]
                restored.append(flight)
        self.flights.flights = restored
        self.flights._seq = flight_data["seq"]
        self.flights._spawn_cd = flight_data["spawn_cd"]
        sn = data.get("sonar")
        if sn:
            self.sonar._next_contact_id = sn.get("next_id", 1)
            for cid, cd in sn.get("contacts", {}).items():
                c = Contact(contact_id=cd.get("contact_id", int(cid)), target_id=cd["target_id"],
                            origin=cd.get("origin", "passiv"),
                            kind=cd.get("kind", "sub"))
                c.bearing = cd.get("bearing", 0.0)
                c.range_est = cd.get("range_est")
                c.range_sigma_nm = cd.get("range_sigma_nm")
                c.range_source = cd.get("range_source")
                c.range_seen = cd.get("range_seen")
                c.confidence = cd.get("confidence", 0.0)
                c.quality = cd.get("quality", 0.0)
                c.last_seen = cd.get("last_seen", 0.0)
                c.depth_est = cd.get("depth_est")
                c.depth_sigma_m = cd.get("depth_sigma_m")
                c.player_class = cd.get("player_class")
                c.signature = cd.get("signature", "")
                c.snr = cd.get("snr", -99.0)
                c.passive_bearing = cd.get("passive_bearing")
                c.raw_bearing = cd.get("raw_bearing")
                c.raw_bearings = [tuple(row) for row in cd.get(
                    "raw_bearings", [])[-config.BEARING_TRACK_MAX_PTS:]]
                c._passive_epoch = cd.get("passive_epoch")
                c._bearing_filter_t = cd.get("bearing_filter_t")
                c._bearing_filter_rate_deg_s = cd.get(
                    "bearing_filter_rate_deg_s", 0.0)
                c.bearing_uncertainty_deg = cd.get("bearing_uncertainty_deg")
                c._bearing_filter_uncertainty_deg = cd.get(
                    "bearing_filter_uncertainty_deg",
                    c.bearing_uncertainty_deg)
                c.ping_pos = tuple(cd["ping_pos"]) if cd.get("ping_pos") else None
                c.observed_x = cd.get("observed_x")
                c.observed_y = cd.get("observed_y")
                c.array_observations = dict(cd.get("array_observations", {}))
                c.fusion_status = cd.get("fusion_status", "KEINE DATEN")
                c.fusion_delta_deg = cd.get("fusion_delta_deg")
                c.fused_quality = cd.get("fused_quality", 0.0)
                c.tma_pos = tuple(cd["tma_pos"]) if cd.get("tma_pos") else None
                c.tma_course = cd.get("tma_course")
                c.tma_speed = cd.get("tma_speed")
                c.tma_quality = cd.get("tma_quality", 0.0)
                c.tma_seen = cd.get("tma_seen", c.range_seen if c.range_source == "tma" else None)
                c.buoy_fixes = [tuple(row) for row in cd.get("buoy_fixes", [])]
                c._fx = self.ship.x
                c._fy = self.ship.y
                if c.observed_x is None or c.observed_y is None:
                    if c.range_source == "tma" and c.tma_pos is not None:
                        c.observed_x, c.observed_y = c.tma_pos
                    elif c.range_source == "ping" and c.ping_pos is not None:
                        c.observed_x, c.observed_y = c.ping_pos
                    elif c.range_source in ("ping", "buoy") \
                            and c.range_est is not None:
                        brg = math.radians(c.bearing)
                        c.observed_x = self.ship.x + c.range_est * math.sin(brg)
                        c.observed_y = self.ship.y - c.range_est * math.cos(brg)
                        if c.range_source == "ping":
                            c.ping_pos = (c.observed_x, c.observed_y)
                self.sonar.contacts[c.target_id] = c
            self.sonar.lofar_history = [list(col)
                                        for col in sn.get("lofar", [])]
            self.sonar.lofar_times = list(sn.get("lofar_times", []))
            self.sonar.lofar_bearings = list(sn.get("lofar_bearings", []))
            self.sonar.broadband_history = [list(row) for row in sn.get("broadband", [])]
            self.sonar.history_times = list(sn.get("history_times", []))
            self.sonar.towed_depth_m = sn.get(
                "towed_depth_m", config.SONAR_TOWED_DEPTH_M)
            self.sonar.towed_depth_target_m = sn.get(
                "towed_depth_target_m", self.sonar.towed_depth_m)
            try:
                self.sonar.tow_state = TowState(sn.get("tow_state", "STOWED"))
            except (TypeError, ValueError):
                self.sonar.tow_state = TowState.STOWED
            self.sonar.tow_payout = config.clamp(float(sn.get("tow_payout", 0.0)), 0.0, 1.0)
            self.sonar.tow_heading_deg = float(sn.get("tow_heading_deg", 0.0)) % 360.0
            self.sonar._tow_settle_s = config.clamp(
                float(sn.get("tow_settle_s", 0.0)), 0.0, config.SONAR_TOWED_SETTLE_S)
            self.sonar._tow_handling_ok = bool(sn.get("tow_handling_ok", True))
            self.sonar.ping_cooldown = max(0.0, float(sn.get("ping_cooldown", 0.0)))
            self.sonar.ping_active = bool(sn.get("ping_active", False))
            self.sonar._ping_anim_timer = max(0.0, float(sn.get("ping_anim_timer", 0.0)))
            self.sonar.echo_history = list(sn.get("echo_history", []))[-config.SONAR_ECHO_HISTORY_MAX:]
            self.sonar.bt_profile = sn.get("bt_profile")
            self.sonar.bt_cooldown = sn.get("bt_cooldown", 0.0)
            track_versions = sn.get("track_versions", {})
            for target_id, points in sn.get("tracks", {}).items():
                track = BearingTrack()
                track.pts = [BearingPoint(p["t"], p["bearing"], p["fx"],
                                          p["fy"], p["fcourse"],
                                          p.get("uncertainty_deg"))
                             for p in points[-config.BEARING_TRACK_MAX_PTS:]]
                track.version = track_versions.get(target_id, len(track.pts))
                self.sonar._tracks[int(target_id)] = track
            self.sonar._tma_versions = {
                int(target_id): version
                for target_id, version in sn.get("tma_versions", {}).items()
                if int(target_id) in self.sonar._tracks
            }
            self.sonar._tma_next = {
                int(target_id): float(next_t)
                for target_id, next_t in sn.get("tma_next", {}).items()
                if int(target_id) in self.sonar._tracks
            }
            for pd in sn.get("pending_pings", []):
                target = by_id.get(pd.get("target_id"))
                if target is not None:
                    mode = pd["mode"]
                    self.sonar._pending_pings.append({
                        "target": target,
                        "frigate": self.ship,
                        "world": self.world,
                        "sent_at": pd["sent_at"],
                        "ready_at": pd["ready_at"],
                        "range_factor": pd["range_factor"],
                        "mode": mode,
                        "snapshot": dict(pd["snapshot"]),
                    })
        self._last_tow_state = self.sonar.tow_state
        self._observed_enemy_torpedoes.update(
            contact.target_id for contact in self.sonar.contacts.values()
            if contact.kind == "torpedo")
        # Phase 2: RNG-Zustaende (deterministischer Fortgang)
        rg = data["rngs"]
        self._restore_rng(rng, rg["world"])
        self._restore_rng(self.world.rng, rg["world_weather"])
        self._restore_rng(self.rng_asm, rg["asm"])
        self._restore_rng(self.damage.rng, rg["damage"])
        self._restore_rng(self.helo.rng, rg["helo"])
        self._restore_rng(self.sonar.rng, rg["sonar"])
        self._restore_rng(self.flights.rng, rg["flight"])
        self._restore_rng(self.rng_asw, rg["asw"])
        # Zustand und sichtbarer Bedienfokus
        ui = data.get("ui", {})
        self.station = Station[ui["station"]]
        self.paused = bool(ui.get("paused", False))
        self.running = True
        self.held = set()
        self.msg = ""
        self.msg_until = 0.0
        self.input_mode = None
        self.input_buffer = ""
        self._mission_warnings = set()
        self._open_administration("")
        self._t = 0.0
        self.map_view.scale = ui.get("map_scale", config.MAP_ZOOM_DEFAULT_PX_PER_NM)
        self.map_view.cx = ui.get("map_cx", self.ship.x)
        self.map_view.cy = ui.get("map_cy", self.ship.y)
        self.map_follow = bool(ui.get("map_follow", True))
        self.tooltips_enabled = bool(ui.get("tooltips_enabled", True))
        self.pinned_tooltip = (layout.valid_tooltip(ui.get("pinned_tooltip"))
                               if self.tooltips_enabled else None)
        anchor = ui.get("tooltip_anchor")
        valid_anchor = (isinstance(anchor, list) and len(anchor) == 2
                        and all(isinstance(value, (int, float))
                                and math.isfinite(value) for value in anchor))
        self._tooltip_anchor = (tuple(anchor) if self.pinned_tooltip is not None
                                and valid_anchor else None)
        self.map_view.clamp_center()
        target_id = ui.get("target_id")
        selected_id = ui.get("selected_contact_id")
        opz_selected_id = ui.get("opz_selected_track_id")
        if isinstance(opz_selected_id, str):
            self.opz_selected_track_id = opz_selected_id
        if target_id is not None:
            self.target = self.sonar.contacts.get(int(target_id))
        if selected_id is not None:
            self.selected_contact = next((c for c in self.sonar.contacts.values()
                                          if c.id == int(selected_id)), None)
        if self.selected_contact is not None and self.sonar.focus_locked:
            self.sonar._listen_target_id = self.selected_contact.target_id
        self.mission_result = data.get("mission_result")
        self.result_reason = data.get("result_reason", "")
        self.game_over = bool(self.damage.ship_sunk) or self.incident \
            or self.mission_result is not None

    def load_game(self, path: str = None) -> bool:
        path = path or config.SAVE_PATH
        if not os.path.exists(path):
            return False
        try:
            data = _read_save_document(path)
        except (OSError, ValueError, RecursionError):
            return False
        return self._load_save_data(data)

    @staticmethod
    def _catalog_for_save(data):
        if (not isinstance(data, dict) or data.get("version") != SAVE_VERSION
                or data.get("save_schema") != SAVE_SCHEMA):
            raise ValueError("unsupported save version")
        return catalog_from_runtime_snapshot(data["catalog_snapshot"])

    @staticmethod
    def _valid_save_document(data, runtime_catalog=None) -> bool:
        def finite_number(value) -> bool:
            try:
                return (isinstance(value, (int, float))
                        and not isinstance(value, bool) and math.isfinite(value))
            except OverflowError:
                return False

        def finite_tree(value, path=()) -> bool:
            if len(path) > 100:
                return False
            if value is None or isinstance(value, (str, bool)):
                return True
            if isinstance(value, (int, float)):
                return finite_number(value)
            if isinstance(value, dict):
                return all(isinstance(key, str) and finite_tree(item, path + (key,))
                           for key, item in value.items())
            if isinstance(value, (list, tuple)):
                return all(finite_tree(item, path + (index,))
                           for index, item in enumerate(value))
            return False

        def bounded(value, low=0.0, high=1_000_000.0) -> bool:
            return finite_number(value) and low <= value <= high

        def identity(value) -> bool:
            return type(value) is int and 1 <= value <= 2**63 - 1

        if not isinstance(data, dict):
            return False
        version = data.get("version")
        if (type(version) is not int or version != SAVE_VERSION
                or data.get("save_schema") != SAVE_SCHEMA):
            return False
        if set(data) != SAVE_ROOT_FIELDS:
            return False
        platform_state_version = data.get("platform_state_version")
        if type(platform_state_version) is not int or platform_state_version != 1:
            return False
        save_sim_t = data.get("sim_t", 0.0)
        if not finite_number(save_sim_t) or not 0.0 <= save_sim_t <= 1e12:
            return False
        if not finite_tree(data):
            return False
        try:
            if runtime_catalog is None:
                runtime_catalog = Game._catalog_for_save(data)
            elif not _same_save_value(
                    runtime_catalog.runtime_snapshot(), data["catalog_snapshot"]):
                return False
        except Exception:
            return False
        if ("esm" not in data
                or not valid_esm_state(data["esm"], save_sim_t,
                                       runtime_catalog.emitters)):
            return False
        torpedo_inventory = data.get("torpedoes")
        if (not isinstance(torpedo_inventory, dict)
                or set(torpedo_inventory) != {"total", "count", "depth"}
                or type(torpedo_inventory["total"]) is not int
                or type(torpedo_inventory["count"]) is not int
                or not 0 <= torpedo_inventory["count"] <= torpedo_inventory["total"] <= 100
                or not bounded(torpedo_inventory["depth"], 0, 10000)):
            return False
        if data.get("level") not in config.LEVELS:
            return False
        if ("asw" not in data or not valid_asw_state(
                    data["asw"], torpedo_inventory["total"],
                    torpedo_inventory["count"], data.get("level"),
                    runtime_catalog)):
            return False
        rng_data = data.get("rngs")
        rng_keys = {
            "world", "world_weather", "asm", "damage", "helo", "sonar",
            "flight", "asw",
        }
        if not isinstance(rng_data, dict) or set(rng_data) != rng_keys:
            return False
        for raw_rng in rng_data.values():
            try:
                if (not isinstance(raw_rng, list) or len(raw_rng) != 3
                        or not isinstance(raw_rng[1], list)):
                    return False
                import random
                random.Random().setstate(
                    (raw_rng[0], tuple(raw_rng[1]), raw_rng[2]))
            except (TypeError, ValueError, OverflowError):
                return False

        def platform_speed_limit(profile_key, profile) -> float:
            systems = runtime_catalog.profile_systems.get(profile_key)
            if systems is not None and systems.machine_key is not None:
                return runtime_catalog.machines[systems.machine_key].maximum_speed_kn
            speed = profile.speed_kn
            return speed[1] if isinstance(speed, tuple) else speed
        air_rows = data.get("air_picture", [])
        required_track_fields = {
            "track_id", "kind", "target_id", "source", "bearing",
            "range_nm", "x", "y", "course", "quality", "last_seen", "label",
        }
        if (not isinstance(air_rows, list)
                or len(air_rows) > MAX_AIR_PICTURE_TRACKS):
            return False
        for row in air_rows:
            if (not isinstance(row, dict)
                    or not required_track_fields <= set(row)
                    or any(not isinstance(row[key], str) or len(row[key]) > 128
                           for key in ("track_id", "kind", "source", "label"))
                    or type(row["target_id"]) is not int or row["target_id"] < 0
                    or not bounded(row["bearing"], 0, 360)
                    or row["bearing"] == 360
                    or not bounded(row["quality"], 0, 1)
                    or not bounded(row["last_seen"], 0, save_sim_t)):
                return False
            if ((row["x"] is None) != (row["y"] is None)
                    or any(value is not None and not bounded(
                        value, -1_000_000, 1_000_000)
                           for value in (row["x"], row["y"]))
                    or (row["range_nm"] is not None
                        and not bounded(row["range_nm"], 0, 1_000_000))
                    or (row["course"] is not None
                        and (not bounded(row["course"], 0, 360)
                             or row["course"] == 360))):
                return False
            position_seen = row.get("position_seen")
            uncertainty = row.get("bearing_uncertainty_deg")
            if ((position_seen is not None
                 and not bounded(position_seen, 0, save_sim_t))
                    or (uncertainty is not None
                        and not bounded(uncertainty, .05, 180))):
                return False
        fixes = data.get("hfdf_fixes", {})
        reports = data.get("hfdf_log", [])
        if not isinstance(fixes, dict) or len(fixes) > 10000:
            return False
        if not isinstance(reports, list) or len(reports) > 20:
            return False
        for report in reports:
            if (not isinstance(report, dict)
                    or not isinstance(report.get("track_id"), str)
                    or not isinstance(report.get("label"), str)
                    or not bounded(report.get("t"))
                    or not bounded(report.get("bearing"), 0, 360)
                    or not all(bounded(report.get(key), -1_000_000, 1_000_000)
                               for key in ("observer_x", "observer_y"))):
                return False
        for fix in fixes.values():
            if (not isinstance(fix, dict) or not isinstance(fix.get("label"), str)
                    or not bounded(fix.get("t")) or not bounded(fix.get("sigma_nm"))
                    or not all(bounded(fix.get(key), -1_000_000, 1_000_000)
                               for key in ("x", "y"))):
                return False
            covariance = fix.get("covariance_nm2")
            if covariance is not None:
                if (not isinstance(covariance, (list, tuple)) or len(covariance) != 3
                        or not all(bounded(value, -1e12, 1e12) for value in covariance)):
                    return False
                xx, xy, yy = covariance
                if xx < 0 or yy < 0 or xy * xy > xx * yy + 1e-9 * max(1., xx * yy):
                    return False
        affiliations = data.get("opz_affiliations")
        if (not isinstance(affiliations, dict)
                or len(affiliations) > MAX_AIR_PICTURE_TRACKS
                or any(not isinstance(track_id, str)
                       or not 1 <= len(track_id) <= 128
                       or value not in config.NATO_AFFILIATIONS
                       for track_id, value in affiliations.items())):
            return False
        ship = data.get("ship")
        if not isinstance(ship, dict):
            return False
        radars = data.get("radars")
        if (not isinstance(radars, dict)
                or set(radars) != {"surface", "air", "range_nm"}
                or type(radars["surface"]) is not bool
                or type(radars["air"]) is not bool
                or radars["range_nm"] not in config.RADAR_RANGE_SCALES_NM):
            return False
        order = ship.get("order_idx", config.TELEGRAPH_DEFAULT)
        if type(order) is not int or not 0 <= order < len(config.TELEGRAPH_ORDERS):
            return False
        team = data.get("dmg_team", 1)
        if type(team) is not int or not 1 <= team <= DamageModel.TEAM_COUNT:
            return False
        from src.ship.damage import COMPARTMENTS
        compartment_keys = {key for key, _ in COMPARTMENTS}
        damage = data.get("damage")
        if not isinstance(damage, dict):
            return False
        teams = damage.get("teams")
        compartments = damage.get("compartments")
        if not isinstance(teams, dict) or not isinstance(compartments, dict):
            return False
        if any(key not in {str(i) for i in range(1, DamageModel.TEAM_COUNT + 1)}
               or (room is not None and (not isinstance(room, str)
                                         or room not in compartment_keys))
               for key, room in teams.items()):
            return False
        if any(key not in compartment_keys or not isinstance(room, dict)
               or room.get("state") not in ("OK", "FLUTEND", "BESCHAEDIGT", "ZERSTOERT")
               or not bounded(room.get("flood"), 0, 1000)
               or not bounded(room.get("fire", 0), 0, 1000)
               for key, room in compartments.items()):
            return False

        groups = {"sub": ("subs",), "animal": ("animals",),
                  "surface": ("civilians", "warships"), "decoy": ("decoys",),
                  "enemy_torpedo": ("enemy_torpedoes",)}
        max_ship_noise = Ship(0, 0, speed_kn=config.SHIP_SPEED_MAX_KN).noise_level()
        max_salvo = max(profile.asm_salvo[1]
                        for profile in runtime_catalog.surfaces.values())
        pending_missiles = 0
        pending_asrocs = 0
        pending_enemy_torpedoes = 0
        pending_decoys = 0
        spent_asrocs = {}
        used_asrocs = {}
        spent_decoys = {}
        used_decoys = {}
        spent_enemy_torpedoes = {}
        used_enemy_torpedoes = {}
        entity_ids, group_ids = set(), {}
        for key, names in groups.items():
            group_ids[key] = set()
            for name in names:
                entries = data.get(name, [])
                if not isinstance(entries, list) or len(entries) > MAX_SAVED_ENTITIES:
                    return False
                for entry in entries:
                    if not isinstance(entry, dict):
                        return False
                    # Early civilian saves may not contain an ID.
                    entity_id = entry.get("id")
                    if entity_id is not None:
                        if not identity(entity_id) or entity_id in entity_ids:
                            return False
                        entity_ids.add(entity_id)
                        group_ids[key].add(entity_id)
                    elif name not in ("civilians", "warships", "decoys", "enemy_torpedoes"):
                        return False
                    if any(not bounded(entry.get(axis), -1_000_000, 1_000_000)
                           for axis in ("x", "y")):
                        return False
                    if name == "subs":
                        profile_key = entry.get("stype")
                        profile = runtime_catalog.subs.get(profile_key)
                        if profile is None:
                            return False
                    elif name == "animals":
                        profile_key = entry.get("atype")
                        if profile_key not in runtime_catalog.animals:
                            return False
                    elif name in ("civilians", "warships"):
                        profile_key = entry.get("signature_key")
                        profile = runtime_catalog.surfaces.get(profile_key)
                        if profile is None:
                            return False
                    elif name == "decoys":
                        profile_key = entry.get("profile_key")
                        decoy_profile = runtime_catalog.decoys.get(profile_key)
                        if decoy_profile is None:
                            return False
                        source_id = entry.get("source_id")
                        if (
                                set(entry) != {"id", "x", "y", "depth", "course",
                                               "speed", "life", "sensor_seed",
                                               "profile_key", "source_id"}
                                or not identity(source_id)
                                or source_id not in group_ids["sub"]
                                or not bounded(entry.get("depth"), 0, 10000)
                                or not bounded(entry.get("course"), 0, 360)
                                or entry.get("course") == 360
                                or decoy_profile is None
                                or entry.get("speed") != config.kn_to_nm_per_s(
                                    decoy_profile.speed_kn)
                                or not bounded(entry.get("life"), .000001,
                                               decoy_profile.life_s)
                                or type(entry.get("sensor_seed")) is not int
                                or not 0 <= entry["sensor_seed"] < 2**31):
                            return False
                        if source_id is not None:
                            used_decoys[source_id] = used_decoys.get(source_id, 0) + 1
                    elif name == "enemy_torpedoes":
                        if not {
                                "profile_key", "guidance_x", "guidance_y",
                                "terminal_active", "seeker_acquired",
                                "seeker_target", "travel", "launch_platform_id",
                                "launch_weapon_key"} <= set(entry):
                            return False
                        profile_key = entry.get("profile_key")
                        profile = runtime_catalog.torpedoes.get(profile_key)
                        if profile is None or profile.used_by != "enemy":
                            return False
                        gx, gy = entry.get("guidance_x"), entry.get("guidance_y")
                        if ((gx is None) != (gy is None)
                                or gx is None
                                or (gx is not None and (
                                    not bounded(gx, -1_000_000, 1_000_000)
                                    or not bounded(gy, -1_000_000, 1_000_000)))
                                or type(entry.get("terminal_active", False)) is not bool
                                or type(entry.get("seeker_acquired", False)) is not bool
                                or not bounded(entry.get("travel", 0), 0,
                                               profile.range_nm if profile else 10000)):
                            return False
                        seeker = entry.get("seeker_target")
                        nixie_ids = {row["seq"] for row in (
                            data.get("asw", {}).get("nixies", [])
                            if isinstance(data.get("asw"), dict) else [])}
                        valid_seeker = (seeker is None or seeker == "ship"
                                        or (isinstance(seeker, str)
                                            and seeker.startswith("nixie:")
                                            and seeker[6:].isdigit()
                                            and int(seeker[6:]) in nixie_ids))
                        acquired = entry.get("seeker_acquired", False)
                        launch_platform_id = entry.get("launch_platform_id")
                        launch_weapon_key = entry.get("launch_weapon_key")
                        if (not identity(launch_platform_id)
                                or launch_platform_id not in group_ids["sub"]
                                or (launch_weapon_key is not None
                                    and (not isinstance(launch_weapon_key, str)
                                         or runtime_catalog.weapons.get(
                                             launch_weapon_key) is None
                                         or runtime_catalog.weapons[
                                             launch_weapon_key].weapon_type != "torpedo"
                                         or runtime_catalog.weapons[
                                             launch_weapon_key].runtime_profile_key
                                             != profile_key))):
                            return False
                        launch_key = (launch_platform_id, launch_weapon_key)
                        used_enemy_torpedoes[launch_key] = (
                            used_enemy_torpedoes.get(launch_key, 0) + 1)
                        if (not valid_seeker or acquired != (seeker is not None)
                                or (acquired and not entry["terminal_active"])
                                or not bounded(entry.get("course"), 0, 360)
                                or entry.get("course") == 360
                                or not bounded(entry.get("depth"), 0, 10000)
                                or not identity(entry.get("idx"))):
                            return False
                    if name in ("subs", "civilians", "warships"):
                        if (not bounded(
                                entry.get("speed"), 0,
                                platform_speed_limit(profile_key, profile))):
                            return False
                        platform = entry.get("platform")
                        if (platform_state_version == 1 and platform is None) \
                                or (platform is not None and (
                                    profile_key is None
                                    or not validate_suite_state(
                                        platform, runtime_catalog, profile_key,
                                        save_sim_t))):
                            return False
                    if name in ("civilians", "warships"):
                        if type(entry.get("emitter", False)) is not bool:
                            return False
                        sensor_seed = entry.get("sensor_seed")
                        if (type(sensor_seed) is not int
                                or not 0 <= sensor_seed < 2**31):
                            return False
                        observed = entry.get("sensor_contact")
                        if (observed is not None and (
                                not isinstance(observed, (list, tuple)) or len(observed) != 2
                                or any(not bounded(value, -1_000_000, 1_000_000) for value in observed))):
                            return False
                        if not bounded(entry.get("sensor_contact_age", config.RADAR_TRACK_STALE_S),
                                       0, config.RADAR_TRACK_STALE_S):
                            return False
                        direction = entry.get("orbit_direction", 1)
                        if type(direction) is not int or direction not in (-1, 1):
                            return False
                        awarded = entry.get("sunk_score_awarded", False)
                        if type(awarded) is not bool or (awarded and not entry.get("sunk", False)):
                            return False
                        if name == "warships":
                            if not {
                                    "asroc_battery", "pending_asroc",
                                    "asw_last_seen"} <= set(entry):
                                return False
                            battery = entry.get("asroc_battery")
                            expected_battery = WeaponBattery.from_catalog(
                                runtime_catalog, profile_key, "asroc")
                            if ((battery is None) !=
                                    (expected_battery is None)):
                                return False
                            if battery is not None and not battery_matches_catalog(
                                    battery, runtime_catalog, profile_key, "asroc"):
                                return False
                            if battery is not None:
                                restored_battery = WeaponBattery.restore(battery)
                                if entity_id is None:
                                    return False
                                for weapon_key in restored_battery.weapon_keys:
                                    capacity = sum(
                                        item.capacity
                                        for item in restored_battery.magazines.values()
                                        if item.weapon_key == weapon_key)
                                    remaining = sum(
                                        item.stowed
                                        for item in restored_battery.magazines.values()
                                        if item.weapon_key == weapon_key)
                                    remaining += sum(
                                        tube.loaded_weapon_key == weapon_key
                                        or tube.loading_weapon_key == weapon_key
                                        for tube in restored_battery.tubes)
                                    spent_asrocs[(entity_id, weapon_key)] = (
                                        capacity - remaining)
                            last_seen = entry.get("asw_last_seen", -1.0)
                            if (not finite_number(last_seen)
                                    or not -1.0 <= last_seen <= save_sim_t):
                                return False
                            pending_asroc = entry.get("pending_asroc", [])
                            if (not isinstance(pending_asroc, list)
                                    or len(pending_asroc) > MAX_ASROCS
                                    or (battery is not None and
                                        len(pending_asroc) >
                                        WeaponBattery.restore(
                                            battery).capacity_total -
                                        WeaponBattery.restore(
                                            battery).remaining_total)):
                                return False
                            for row in pending_asroc:
                                if (not isinstance(row, dict)
                                        or set(row) != {"x", "y", "datum_x",
                                                       "datum_y", "weapon_key",
                                                       "target_depth_m"}
                                        or any(not bounded(row.get(field),
                                                               -1_000_000, 1_000_000)
                                               for field in ("x", "y", "datum_x",
                                                             "datum_y"))
                                        or not bounded(row.get("target_depth_m"),
                                                       0, 10000)):
                                    return False
                                weapon = runtime_catalog.weapons.get(
                                    row.get("weapon_key"))
                                if (weapon is None or weapon.weapon_type != "asroc"
                                        or battery is None
                                        or row["weapon_key"] not in
                                            battery["weapon_keys"]):
                                    return False
                                key = (entity_id, row["weapon_key"])
                                used_asrocs[key] = used_asrocs.get(key, 0) + 1
                            pending_asrocs += len(pending_asroc)
                            if pending_asrocs > MAX_ASROCS:
                                return False
                    if name == "subs":
                        if not {
                                "asw_battery", "countermeasure_store"} <= set(entry):
                            return False
                        torpedoes_left = entry.get("torpedoes_left")
                        if (type(torpedoes_left) is not int
                                or not 0 <= torpedoes_left <= 100):
                            return False
                        battery = entry.get("asw_battery")
                        expected_battery = WeaponBattery.from_catalog(
                            runtime_catalog, profile_key, "torpedo")
                        if ((battery is None) !=
                                (expected_battery is None)):
                            return False
                        if battery is not None and not battery_matches_catalog(
                                battery, runtime_catalog, profile_key, "torpedo"):
                            return False
                        if battery is not None:
                            restored_battery = WeaponBattery.restore(battery)
                            for weapon_key in restored_battery.weapon_keys:
                                capacity = sum(
                                    item.capacity for item in
                                    restored_battery.magazines.values()
                                    if item.weapon_key == weapon_key)
                                remaining = sum(
                                    item.stowed for item in
                                    restored_battery.magazines.values()
                                    if item.weapon_key == weapon_key)
                                remaining += sum(
                                    tube.loaded_weapon_key == weapon_key
                                    or tube.loading_weapon_key == weapon_key
                                    for tube in restored_battery.tubes)
                                spent_enemy_torpedoes[(entity_id, weapon_key)] = (
                                    capacity - remaining)
                        else:
                            spent_enemy_torpedoes[(entity_id, None)] = max(
                                0, profile.torpedoes - torpedoes_left)
                        store = entry.get("countermeasure_store")
                        expected_store = ConsumableStore.from_catalog(
                            runtime_catalog, profile_key, "acoustic_decoy")
                        if ((store is None) != (expected_store is None)):
                            return False
                        if store is not None and not consumable_matches_catalog(
                                store, runtime_catalog, profile_key,
                                "acoustic_decoy"):
                            return False
                        if store is not None:
                            consumables = ConsumableStore.restore(store)
                            spent_decoys[entity_id] = (
                                consumables.capacity - consumables.remaining_total)
                        battery = entry.get("asw_battery")
                        store = entry.get("countermeasure_store")
                        if (battery is not None
                                and WeaponBattery.restore(battery).remaining_total
                                != entry.get("torpedoes_left")):
                            return False
                        memory = entry.get("memory", {})
                        if not isinstance(memory, dict):
                            return False
                        for age in ("last_ping_age", "last_torpedo_age"):
                            value = memory.get(age)
                            if value is not None and not bounded(value, 0, 1e12):
                                return False
                        if not bounded(memory.get("contact_age", config.SUB_EVADE_DURATION_S),
                                       0, config.SUB_EVADE_DURATION_S):
                            return False
                        bearing = memory.get("contact_bearing")
                        if bearing is not None and (not bounded(bearing, 0, 360) or bearing == 360):
                            return False
                        observed = memory.get("contact")
                        if observed is not None:
                            if (not isinstance(observed, dict)
                                    or set(observed) != {"x", "y", "speed", "course", "noise"}
                                    or any(not bounded(observed[axis], -1_000_000, 1_000_000)
                                           for axis in ("x", "y"))
                                    or not bounded(observed["speed"], 0, 100)
                                    or not bounded(observed["course"], 0, 360)
                                    or not bounded(observed["noise"], 0, max_ship_noise)):
                                return False
                    for pending, width in (("pending_torpedoes", 9),
                                           ("pending_decoys", 2), ("pending_asm", 3)):
                        rows = entry.get(pending, [])
                        if (not isinstance(rows, list) or len(rows) > 10000
                                or any(not isinstance(row, (list, tuple))
                                       or len(row) != width
                                       or (pending != "pending_torpedoes"
                                           and any(not bounded(
                                               v, -1_000_000, 1_000_000)
                                                   for v in row))
                                       or (pending == "pending_asm" and not identity(row[2]))
                                       for row in rows)):
                            return False
                        if pending == "pending_torpedoes" and rows:
                            if (name != "subs" or len(rows) > 2
                                    or (battery is not None and len(rows) >
                                        WeaponBattery.restore(
                                            battery).capacity_total -
                                        WeaponBattery.restore(
                                            battery).remaining_total)):
                                return False
                            for row in rows:
                                if (any(not bounded(value, -1_000_000, 1_000_000)
                                        for value in row[:6])
                                        or not isinstance(row[6], str)
                                        or not identity(row[7])
                                        or row[7] != entity_id):
                                    return False
                                pending_profile = runtime_catalog.torpedoes.get(row[6])
                                weapon_key = row[8]
                                if (pending_profile is None
                                        or pending_profile.used_by != "enemy"
                                        or (battery is None) != (weapon_key is None)
                                        or (weapon_key is not None and (
                                            weapon_key not in battery["weapon_keys"]
                                            or runtime_catalog.weapons[
                                                weapon_key].runtime_profile_key
                                                != row[6]))):
                                    return False
                                key = (entity_id, weapon_key)
                                used_enemy_torpedoes[key] = (
                                    used_enemy_torpedoes.get(key, 0) + 1)
                            pending_enemy_torpedoes += len(rows)
                            if (pending_enemy_torpedoes
                                    + len(data.get("enemy_torpedoes", []))
                                    > MAX_ENEMY_TORPEDOES):
                                return False
                        if pending == "pending_decoys" and rows:
                            if name != "subs" or len(rows) > 1:
                                return False
                            if store is not None:
                                consumables = ConsumableStore.restore(store)
                                if len(rows) > consumables.capacity - \
                                        consumables.remaining_total:
                                    return False
                            used_decoys[entity_id] = (
                                used_decoys.get(entity_id, 0) + len(rows))
                            pending_decoys += len(rows)
                            if (pending_decoys
                                    + len(data.get("decoys", [])) > MAX_DECOYS):
                                return False
                        if pending == "pending_asm" and rows:
                            if name != "warships":
                                return False
                            profile_key = entry.get("signature_key")
                            if profile_key is not None and not isinstance(profile_key, str):
                                return False
                            profile = runtime_catalog.surfaces.get(profile_key)
                            low, high = profile.asm_salvo if profile is not None else (1, max_salvo)
                            if any(not low <= row[2] <= high for row in rows):
                                return False
                            pending_missiles += sum(row[2] for row in rows)
                            if pending_missiles > Game.MAX_SAVED_ASMS:
                                return False
        if any(count > spent_enemy_torpedoes.get(key, 0)
               for key, count in used_enemy_torpedoes.items()):
            return False
        for row in data["asw"]["asrocs"]:
            key = (row["launch_platform_id"], row["weapon_key"])
            used_asrocs[key] = used_asrocs.get(key, 0) + 1
        if any(count > spent_asrocs.get(key, 0)
               for key, count in used_asrocs.items()):
            return False
        if any(count > spent_decoys.get(source_id, 0)
               for source_id, count in used_decoys.items()):
            return False
        if len(entity_ids) > MAX_SAVED_ENTITIES:
            return False
        next_ids = data.get("next_entity_ids", {})
        if (not isinstance(next_ids, dict) or set(next_ids) != set(groups)
                or any(not identity(value) or value <= max(group_ids[key], default=0)
                       for key, value in next_ids.items())):
            return False
        for key in ("asm_seq", "asm_spawned", "warship_asm_seq"):
            value = data.get(key, 0)
            if type(value) is not int or not 0 <= value <= 2**63 - 1:
                return False
        if not bounded(data.get("ciws_cooldown_s", 0), 0, 1):
            return False
        if type(data.get("air_threat_reported", False)) is not bool:
            return False
        flights = data.get("flights", {})
        if (not isinstance(flights, dict)
                or not isinstance(flights.get("items", []), list)
                or len(flights.get("items", [])) > FlightManager.MAX_FLIGHTS):
            return False
        for flight in flights.get("items", []):
            if not isinstance(flight, dict):
                return False
            bearing = flight.get("sensor_bearing")
            if (type(flight.get("radar_emitting", False)) is not bool
                    or not bounded(flight.get("sensor_age", config.RADAR_TRACK_STALE_S),
                                   0, config.RADAR_TRACK_STALE_S)
                    or (bearing is not None and (not bounded(bearing, 0, 360) or bearing == 360))):
                return False
            profile = runtime_catalog.aircraft.get(flight.get("akey"))
            if profile is None or profile.kind != flight.get("kind"):
                return False
            platform = flight.get("platform")
            if (platform_state_version == 1 and platform is None) \
                    or (platform is not None and (
                        profile is None or not validate_suite_state(
                            platform, runtime_catalog, profile.key, save_sim_t))):
                return False
        helo = data.get("helo")
        if not isinstance(helo, dict):
            return False
        if isinstance(helo, dict):
            required_helo = {"state", "x", "y", "course", "torps",
                             "buoys_left", "fuel_s", "waypoint_x", "waypoint_y"}
            if not required_helo <= set(helo):
                return False
            if (helo.get("state") not in ("HANGAR", "AUF", "ZURUECK", "VERLOREN")
                    or not bounded(helo.get("x"), -1_000_000, 1_000_000)
                    or not bounded(helo.get("y"), -1_000_000, 1_000_000)
                    or not bounded(helo.get("course"), 0, 360)
                    or helo.get("course") == 360
                    or type(helo.get("torps")) is not int
                    or not 0 <= helo["torps"] <= config.HELO_TORPS
                    or type(helo.get("buoys_left")) is not int
                    or not 0 <= helo["buoys_left"] <= config.BUOY_COUNT
                    or not bounded(helo.get("fuel_s"), 0, config.HELO_FUEL_S)):
                return False
            wx, wy = helo.get("waypoint_x"), helo.get("waypoint_y")
            if ((wx is None) != (wy is None)
                    or (wx is not None and (
                        not bounded(wx, -1_000_000, 1_000_000)
                        or not bounded(wy, -1_000_000, 1_000_000)))):
                return False
        if isinstance(helo, dict):
            profile = runtime_catalog.torpedoes.get(helo.get("torpedo_profile_key"))
            if profile is None or profile.used_by != "helo":
                return False
        buoys = data.get("buoys", [])
        if not isinstance(buoys, list) or len(buoys) > config.BUOY_COUNT:
            return False
        buoy_ids = set()
        for buoy in buoys:
            if (not isinstance(buoy, dict)
                    or set(buoy) != {"x", "y", "seq", "battery_s"}
                    or not bounded(buoy.get("x"), -1_000_000, 1_000_000)
                    or not bounded(buoy.get("y"), -1_000_000, 1_000_000)
                    or not identity(buoy.get("seq"))
                    or buoy["seq"] in buoy_ids
                    or not bounded(buoy.get("battery_s"), .000001,
                                   config.BUOY_BATTERY_S)):
                return False
            buoy_ids.add(buoy["seq"])
        if (isinstance(helo, dict)
                and len(buoys) > config.BUOY_COUNT - helo["buoys_left"]):
            return False
        asms = data.get("asms", [])
        torpedoes = data.get("torpedoes_in_flight", [])
        essms = data.get("essms", [])
        if (not isinstance(asms, list) or len(asms) > Game.MAX_SAVED_ASMS
                or not isinstance(torpedoes, list)
                or len(torpedoes) > Game.MAX_SAVED_PLAYER_TORPEDOES
                or not isinstance(essms, list)
                or len(essms) > Game.MAX_SAVED_ESSMS
                or any(not isinstance(row, dict)
                       for rows in (asms, torpedoes, essms) for row in rows)):
            return False
        if len(asms) + pending_missiles > Game.MAX_SAVED_ASMS:
            return False
        asm_ids = set()
        for asm in asms:
            seq = asm.get("seq")
            if not identity(seq) or seq in asm_ids:
                return False
            asm_ids.add(seq)
            if (asm.get("state", "LAUF") not in ("LAUF", "CHAFF", "ABGEFANGEN", "TREFFER", "VERLOREN")
                    or not bounded(asm.get("age_s", 0), 0, ASM.LIFE_S)
                    or not bounded(asm.get("travel", 0), 0, ASM.RANGE_NM)):
                return False
        if "asm_seq" in data and data["asm_seq"] < max(asm_ids, default=0):
            return False
        for weapon in torpedoes + essms:
            if any(not bounded(weapon.get(axis), -1_000_000, 1_000_000)
                   for axis in ("x", "y")):
                return False
            for flag in ("terminal_active", "seeker_acquired"):
                if flag in weapon and type(weapon[flag]) is not bool:
                    return False
            if ("guidance_x" in weapon) != ("guidance_y" in weapon):
                return False
            gx, gy = weapon.get("guidance_x"), weapon.get("guidance_y")
            if (gx is None) != (gy is None) or (gx is not None and (
                    not bounded(gx, -1_000_000, 1_000_000)
                    or not bounded(gy, -1_000_000, 1_000_000))):
                return False
        active_origins = {"frigate": 0, "helo": 0, "asroc": 0}
        for torpedo in torpedoes:
            if torpedo.get("guidance_x") is None:
                return False
            target_id = torpedo.get("target_id")
            if target_id is not None and (not identity(target_id)
                    or target_id not in entity_ids):
                return False
            profile_key = torpedo.get("profile_key")
            profile = runtime_catalog.torpedoes.get(profile_key)
            if profile is None or profile.used_by not in ("frigate", "helo"):
                return False
            distance = torpedo.get("range_nm", Torpedo.RANGE_NM)
            if (not bounded(distance, .001, 10000)
                    or not identity(torpedo.get("idx"))
                    or not bounded(torpedo.get("speed_kn", Torpedo.SPEED_KN), 0, 10000)
                    or not bounded(torpedo.get("depth", 5), 0, 10000)
                    or not bounded(torpedo.get("target_depth", 5), 0, 10000)
                    or not bounded(torpedo.get("travel", 0), 0, distance)
                    or not bounded(torpedo.get("midcourse_timer", 0), 0, Torpedo.WIRE_BREAK_S)
                    or not {"search_phase", "midcourse"} <= set(torpedo)
                    or not bounded(torpedo.get("search_phase", 0), 0, 1e12)
                    or not bounded(torpedo.get("midcourse", torpedo.get("course")),
                                   0, 360)
                    or torpedo.get("midcourse", torpedo.get("course")) == 360
                    or torpedo.get("state", "RUN") not in ("RUN", "HIT", "SASE")):
                return False
            if torpedo.get("seeker_acquired", False) and target_id is None:
                return False
            origin = torpedo.get("launch_origin")
            launch_platform_id = torpedo.get("launch_platform_id")
            launch_weapon_key = torpedo.get("launch_weapon_key")
            if (origin not in active_origins
                    or not {"launch_platform_id", "launch_weapon_key"}
                    <= set(torpedo)
                    or (origin == "asroc" and (
                        not identity(launch_platform_id)
                        or not isinstance(launch_weapon_key, str)
                        or runtime_catalog.weapons.get(launch_weapon_key) is None
                        or runtime_catalog.weapons[
                            launch_weapon_key].weapon_type != "asroc"))
                    or (origin != "asroc" and (
                        launch_platform_id is not None
                        or launch_weapon_key is not None))):
                return False
            loadout_weapons = data["asw"]["loadout"]["weapons"]
            own_weapon = next((item for item in loadout_weapons
                               if item["runtime_profile_key"] == profile_key), None)
            if origin == "frigate" and own_weapon is not None:
                expected_hit_distance = own_weapon[
                    "kill_dist_nm_by_level"][data["level"]]
                expected_hit_depth = own_weapon[
                    "kill_depth_m_by_level"][data["level"]]
            elif origin == "helo":
                expected_hit_distance = config.LEVELS[
                    data["level"]]["kill_dist_nm"]
                expected_hit_depth = config.LEVELS[
                    data["level"]]["kill_depth_m"]
            else:
                expected_hit_distance = profile.hit_dist_nm
                expected_hit_depth = Torpedo.KILL_DEPTH_M
            if ((origin == "frigate" and profile.used_by != "frigate")
                    or (profile.used_by == "frigate" and own_weapon is None)
                    or torpedo.get("speed_kn") != profile.speed_kn
                    or distance != profile.range_nm
                    or torpedo.get("kill_dist_nm") != expected_hit_distance
                    or torpedo.get("kill_depth_m") != expected_hit_depth
                    or (origin in ("helo", "asroc")
                        and profile.used_by != "helo")
                    or (torpedo.get("seeker_acquired", False)
                        and not torpedo.get("terminal_active", False))):
                return False
            active_origins[origin] += 1
            if origin == "asroc":
                key = (launch_platform_id, launch_weapon_key)
                used_asrocs[key] = used_asrocs.get(key, 0) + 1
        player_battery = WeaponBattery.restore(data["asw"]["player_battery"])
        if active_origins["frigate"] > (
                player_battery.capacity_total - player_battery.remaining_total):
            return False
        if (not isinstance(helo, dict)
                or active_origins["helo"] > config.HELO_TORPS - helo["torps"]):
            return False
        if any(count > spent_asrocs.get(key, 0)
               for key, count in used_asrocs.items()):
            return False
        torpedo_seq = data.get("torpedo_seq", 0)
        buoy_seq = data.get("buoy_seq", 0)
        if (type(torpedo_seq) is not int or not 0 <= torpedo_seq <= 2**63 - 1
                or type(buoy_seq) is not int or not 0 <= buoy_seq <= 2**63 - 1
                or torpedo_seq < max(
                    (row["idx"] for row in torpedoes), default=0)
                or buoy_seq < max(buoy_ids, default=0)):
            return False
        for essm in essms:
            target_id = essm.get("target_id")
            track_id = essm.get("track_target_id")
            if ((target_id is not None and (not identity(target_id)
                                           or target_id not in asm_ids))
                    or not identity(essm.get("seq"))
                    or (track_id is not None and not identity(track_id))
                    or not bounded(essm.get("travel", 0), 0, config.ESSM_RANGE_NM)
                    or essm.get("state", "LAUF") not in ("LAUF", "HIT", "SASE")
                    or (essm.get("seeker_acquired", False)
                        and target_id is None)
                    or essm.get("guidance_x") is None):
                return False
            if "asm_seq" in data and track_id is not None and track_id > data["asm_seq"]:
                return False
        world = data.get("world")
        if world is not None and not isinstance(world, dict):
            return False
        if isinstance(world, dict) and world.get("mode", "fixed") not in (
                "fixed", "procedural"):
            return False
        schedulers = data.get("schedulers", {})
        if not isinstance(schedulers, dict):
            return False
        for key, limit in (("sensor", .25), ("esm", .5),
                           ("radio", .5), ("slow", .5)):
            value = schedulers.get(key, 0.0)
            if not finite_number(value) or not 0.0 <= value < limit:
                return False
        sonar = data.get("sonar")
        if not isinstance(sonar, dict):
            return False
        for key in ("lofar", "lofar_times", "lofar_bearings",
                    "broadband", "history_times", "echo_history",
                    "pending_pings"):
            if key in sonar and not isinstance(sonar[key], list):
                return False
        for key in ("lofar", "broadband"):
            if any(not isinstance(row, list)
                   or any(not finite_number(value) for value in row)
                   for row in sonar.get(key, [])):
                return False
        for key in ("lofar_times", "lofar_bearings", "history_times"):
            if any(not finite_number(value) for value in sonar.get(key, [])):
                return False
        contacts = sonar.get("contacts", {})
        if not isinstance(contacts, dict):
            return False
        contact_ids = [contact.get("contact_id")
                       for contact in contacts.values()
                       if isinstance(contact, dict)]
        next_contact_id = sonar.get("next_id")
        if (not identity(next_contact_id)
                or any(not identity(contact_id) for contact_id in contact_ids)
                or next_contact_id <= max(contact_ids, default=0)):
            return False
        for contact in contacts.values():
            if not isinstance(contact, dict):
                return False
            reports = contact.get("array_observations", {})
            if not isinstance(reports, dict) or not set(reports) <= {"BOW", "TOWED"}:
                return False
            for report in reports.values():
                if (not isinstance(report, dict)
                        or not {"bearing", "quality", "snr", "last_seen"} <= set(report)
                        or not set(report) <= {"bearing", "quality", "snr", "last_seen", "uncertainty_deg"}
                        or not bounded(report["bearing"], 0, 360) or report["bearing"] == 360
                        or not bounded(report["quality"], 0, 1)
                        or not bounded(report["snr"], -200, 200)
                        or not bounded(report["last_seen"], 0, 1e12)
                        or ("uncertainty_deg" in report
                            and not bounded(report["uncertainty_deg"], .05, 180))):
                    return False
            tma_seen = contact.get("tma_seen")
            if tma_seen is not None and not bounded(tma_seen, 0, 1e12):
                return False
            fixes = contact.get("buoy_fixes", [])
            if (not isinstance(fixes, list) or len(fixes) > 80
                    or any(not isinstance(row, (list, tuple)) or len(row) != 4
                           or not bounded(row[0], 0, 1e12)
                           or any(not bounded(v, -1_000_000, 1_000_000) for v in row[1:3])
                           or not bounded(row[3], 0, 1) for row in fixes)):
                return False
            history = contact.get("raw_bearings", [])
            if (not isinstance(history, list)
                    or len(history) > config.BEARING_TRACK_MAX_PTS
                    or any(not isinstance(row, (list, tuple)) or len(row) != 3
                           or any(not finite_number(value) for value in row)
                           or not 0.0 <= row[1] < 360.0
                           or not 0.0 <= row[2] <= 180.0
                           for row in history)):
                return False
            uncertainty = contact.get("bearing_uncertainty_deg")
            if (uncertainty is not None
                    and (not finite_number(uncertainty)
                         or not 0.0 <= uncertainty <= 180.0)):
                return False
            passive_bearing = contact.get("passive_bearing")
            if (passive_bearing is not None
                    and (not finite_number(passive_bearing)
                         or not 0.0 <= passive_bearing < 360.0)):
                return False
            epoch = contact.get("passive_epoch")
            if epoch is not None and (not isinstance(epoch, int)
                                      or isinstance(epoch, bool) or epoch < 0):
                return False
            filter_t = contact.get("bearing_filter_t")
            if (filter_t is not None
                    and (not finite_number(filter_t) or filter_t < 0.0)):
                return False
            filter_rate = contact.get("bearing_filter_rate_deg_s", 0.0)
            if (not finite_number(filter_rate)
                    or abs(filter_rate) > config.SONAR_BEARING_RATE_MAX_DEG_S):
                return False
            filter_uncertainty = contact.get("bearing_filter_uncertainty_deg")
            if (filter_uncertainty is not None
                    and (not finite_number(filter_uncertainty)
                         or not 0.05 <= filter_uncertainty <= 180.0)):
                return False
            if (filter_t is None and filter_rate != 0.0) \
                    or (filter_t is not None
                        and (passive_bearing is None
                             or filter_uncertainty is None)):
                return False
        echoes = sonar.get("echo_history", [])
        if any(not isinstance(item, dict)
               or not finite_number(item.get("t"))
               or not finite_number(item.get("contact_id"))
               or any(name in item and not finite_number(item[name])
                      for name in ("bearing", "range_nm", "range_sigma_nm",
                                   "depth_m", "depth_sigma_m", "snr_db"))
               for item in echoes):
            return False
        tracks = sonar.get("tracks", {})
        if not isinstance(tracks, dict):
            return False
        if any(not isinstance(points, list)
               or len(points) > config.BEARING_TRACK_MAX_PTS
               or any(not isinstance(point, dict)
                       or any(not finite_number(point.get(name))
                              for name in ("t", "bearing", "fx", "fy",
                                           "fcourse"))
                       or ("uncertainty_deg" in point
                           and (not finite_number(point["uncertainty_deg"])
                                or not 0.05 <= point["uncertainty_deg"] <= 180.0))
                       for point in points)
               for points in tracks.values()):
            return False
        track_versions = sonar.get("track_versions", {})
        tma_versions = sonar.get("tma_versions", {})
        tma_next = sonar.get("tma_next", {})
        if any(not isinstance(values, dict)
               for values in (track_versions, tma_versions, tma_next)):
            return False
        if any(not isinstance(value, int) or isinstance(value, bool)
               or not 0 <= value <= 1_000_000_000
               for values in (track_versions, tma_versions)
               for value in values.values()):
            return False
        if any(not finite_number(value) or value < 0.0
               for value in tma_next.values()):
            return False
        try:
            all_keys = (set(tracks) | set(track_versions)
                        | set(tma_versions) | set(tma_next))
            if any(not isinstance(key, str) or str(int(key)) != key
                   for key in all_keys):
                return False
            gate_keys = ({int(key) for key in track_versions}
                         | {int(key) for key in tma_versions}
                         | {int(key) for key in tma_next})
            track_keys = {int(key) for key in tracks}
        except (TypeError, ValueError):
            return False
        if any(key < 0 for key in gate_keys | track_keys) \
                or not gate_keys <= track_keys:
            return False
        if any(track_versions.get(key, len(points)) < len(points)
               for key, points in tracks.items()):
            return False
        if any(value > track_versions.get(key, len(tracks[key]))
               for key, value in tma_versions.items()):
            return False
        sim_t = data.get("sim_t", 0.0)
        if (not finite_number(sim_t) or sim_t < 0.0
                or any(value > sim_t + config.TMA_RESOLVE_EVERY_S
                       for value in tma_next.values())
                or any(contact.get("bearing_filter_t") is not None
                       and contact["bearing_filter_t"] > sim_t
                       for contact in contacts.values())):
            return False
        pending_pings = sonar.get("pending_pings", [])
        # 25000 s covers two-way propagation across the 10000 NM snapshot bound.
        if len(pending_pings) > SonarSystem.MAX_PENDING_PINGS or any(not isinstance(item, dict)
               or set(item) != {"target_id", "sent_at", "ready_at", "range_factor", "mode", "snapshot"}
               or not identity(item.get("target_id"))
               or item["target_id"] not in entity_ids
               or any(not bounded(item.get(key, 0), 0, 1e12)
                      for key in ("sent_at", "ready_at"))
               or not bounded(item.get("range_factor", 1), 0, 100)
               or item.get("mode", "BOW") not in ("BOW", "TOWED")
               or item.get("sent_at", sim_t) > sim_t
               or not 0 <= item.get("ready_at", sim_t) - item.get("sent_at", sim_t) <= 25000
               or not SonarSystem.valid_ping_snapshot(item["snapshot"])
               or not item["sent_at"] <= item["snapshot"]["t"] <= sim_t
               for item in pending_pings):
            return False
        return True

    def _load_save_data(self, data: dict) -> bool:
        import copy

        try:
            runtime_catalog = self._catalog_for_save(data)
        except (KeyError, TypeError, ValueError, OverflowError, RecursionError):
            return False
        if not self._valid_save_document(data, runtime_catalog):
            return False
        candidate = copy.copy(self)
        candidate.runtime_catalog = runtime_catalog
        candidate.held = set(self.held)
        candidate.map_view = copy.copy(self.map_view)
        candidate._observed_enemy_torpedoes = set(
            self._observed_enemy_torpedoes)
        candidate.audio = copy.copy(self.audio)
        candidate.audio.stop_sonar = lambda: None
        id_classes = (Sub, Animal, SurfaceShip, Decoy, EnemyTorpedo)
        next_ids = tuple(cls._next_id for cls in id_classes)
        candidate._restore_id_allocations = dict.fromkeys(id_classes, 0)
        restored = False
        try:
            candidate._restore_state(data)
            canonical = candidate.save_state()
            # Constructor allocations are rolled back below; they are not part
            # of the candidate's persisted identity high-water marks.
            canonical["next_entity_ids"] = data["next_entity_ids"]
            if not _same_save_value(canonical, data):
                return False
            restored = True
        except Exception:
            return False
        finally:
            groups = (("sub", candidate.subs), ("animal", candidate.animals),
                      ("surface", candidate.civilians + candidate.warships),
                      ("decoy", candidate.decoys),
                      ("enemy_torpedo", candidate.enemy_torpedoes))
            for cls, baseline, (key, entities) in zip(id_classes, next_ids, groups):
                current = cls._next_id
                # Never rewind another instance's allocations. Remove only a
                # contiguous run known to consist solely of restoration IDs.
                if current == baseline + candidate._restore_id_allocations[cls]:
                    current = baseline
                if restored:
                    current = max(current, data["next_entity_ids"][key],
                                  max((entity.id + 1 for entity in entities), default=1))
                cls._next_id = current
            del candidate._restore_id_allocations
        candidate.audio = self.audio
        self.__dict__.update(candidate.__dict__)
        self.in_menu = False
        self.main_menu = False
        return True

    # --- W4: Save-Slots 1-5 ---

    def save_to_slot(self, slot: int) -> None:
        if type(slot) is not int or not 1 <= slot <= 5:
            raise ValueError("slot must be an integer from 1 to 5")
        path = os.path.join(config.SAVE_DIR, f"slot{slot}.json")
        self.save_game(path)
        self.flash(message("status.saved", slot=slot), 2.0)
        self.feed.add(self.world.format_time(), "mission",
                      message("status.save_feed", slot=slot))

    def load_from_slot(self, slot: int) -> bool:
        if type(slot) is not int or not 1 <= slot <= 5:
            raise ValueError("slot must be an integer from 1 to 5")
        path = os.path.join(config.SAVE_DIR, f"slot{slot}.json")
        if not os.path.exists(path):
            return False
        try:
            data = _read_save_document(path)
        except (OSError, ValueError, RecursionError):
            return False
        if not self._load_save_data(data):
            return False
        self.flash(message("status.loaded", slot=slot), 2.0)
        return True

    # --- W4: Hauptmenü (Szenario -> [Level] -> Briefing) ---

    def _reset_map_view(self) -> None:
        """Standard-Karte: Detail-Zoom, Kamera folgt der Fregatte."""
        self.map_view.set_rect(config.MAP_RECT)
        self.map_view.scale = config.MAP_ZOOM_DEFAULT_PX_PER_NM
        self.map_view.cx = self.ship.x
        self.map_view.cy = self.ship.y
        self.map_view.clamp_center()
        self.map_follow = True

    def _reroll_menu_seed(self) -> None:
        """Choose a menu seed uniformly without repeating the current value."""
        import random

        upper = 1_000_000_000
        rng = random.SystemRandom()
        if 1 <= self.seed < upper:
            candidate = rng.randrange(1, upper - 1)
            if candidate >= self.seed:
                candidate += 1
        else:
            candidate = rng.randrange(1, upper)
        self.seed = candidate

    def _start_menu_mission(self) -> None:
        """Consume an exact pristine menu preparation, otherwise replace it."""
        prepared = (self.seed, self.scenario_key, self.world_mode, self.level,
                    id(self.world), id(self.sonar))
        reuse = (self.in_menu and self._prepared_menu_mission == prepared
                 and self.sim_t == 0.0 and self.mission_time == 0.0
                 and self.custom_mission_definition is None
                 and self.mission_result is None and not self.game_over
                 and self.running and not self.paused)
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

    def _handle_menu_key(self, key) -> None:
        if key == pygame.K_f:
            self.toggle_fullscreen()
            return
        if key == pygame.K_w:
            self.world_mode = ("fixed" if self.world_mode == "procedural"
                               else "procedural")
            return
        if key == pygame.K_r:
            self._reroll_menu_seed()
            return
        if self.main_menu:
            entries = ("new", "load", "mission_editor", "unit_editor", "options", "quit")
            if key == pygame.K_UP:
                self.main_menu_sel = (self.main_menu_sel - 1) % len(entries)
            elif key == pygame.K_DOWN:
                self.main_menu_sel = (self.main_menu_sel + 1) % len(entries)
            elif key in (pygame.K_RETURN, pygame.K_SPACE):
                action = entries[self.main_menu_sel]
                if action == "new":
                    self.main_menu = False
                    self.menu_screen = "scenario"
                    self.menu_sel = 0
                elif action == "load":
                    self._open_administration("load")
                elif action == "mission_editor":
                    profiles = set(catalog_builtins(CATALOG))
                    self.editor = MissionEditor(tr=self.tr, profile_keys=profiles)
                elif action == "unit_editor":
                    self.editor = UnitEditor(catalog_builtins(CATALOG), tr=self.tr)
                elif action == "options":
                    self._open_administration("options")
                else:
                    self._open_administration("quit")
            elif key in (pygame.K_ESCAPE, pygame.K_q):
                self._open_administration("quit")
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
                self.menu_screen = "level" if sc["level"] is None else "briefing"
                if self.menu_screen == "level":
                    self.menu_sel = config.LEVEL_ORDER.index(self.level)
            elif key in (pygame.K_ESCAPE, pygame.K_q):
                self._open_administration("quit")
            return
        if self.menu_screen == "level":
            n = len(config.LEVEL_ORDER)
            if key == pygame.K_UP:
                self.menu_sel = (self.menu_sel - 1) % n
            elif key == pygame.K_DOWN:
                self.menu_sel = (self.menu_sel + 1) % n
            elif key in (pygame.K_1, pygame.K_2, pygame.K_3):
                self.menu_sel = {"1": 0, "2": 1, "3": 2} \
                    [pygame.key.name(key)]
            elif key in (pygame.K_RETURN, pygame.K_SPACE):
                self.level = config.LEVEL_ORDER[self.menu_sel]
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
            f = font or self.font
            text = localize(text)
            surf = f.render(text, True, color)
            s.blit(surf, surf.get_rect(center=(cx, y)))

        center("U-JAGD – FREGATTE F-217", 100, self.font_big)

        if self.main_menu:
            labels = ("menu.new_game", "menu.load", "menu.mission_editor",
                      "menu.unit_editor", "option.title", "menu.quit")
            for i, key in enumerate(labels):
                marker = "> " if i == self.main_menu_sel else "  "
                color = config.COLOR_TEXT if i == self.main_menu_sel else config.COLOR_TEXT_DIM
                center(message("menu.choice", marker=marker,
                               label=self.tr(key).upper()), 205 + i * 50, color=color)
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
                lv = (self.tr("level." + {"leicht": "easy", "normal": "normal",
                                          "harte": "hard"}[sc["level"]])
                      if sc["level"] else "-")
                title = self.tr("scenario." + scenario_names[key] + ".title")
                center(message("menu.scenario_choice", index=i + 1,
                               marker=marker, title=title, level=lv),
                       240 + i * 40, color=col)
        elif self.menu_screen == "level":
            center(self.tr("menu.choose_difficulty"),
                   180, color=config.COLOR_TEXT_DIM)
            for i, key in enumerate(config.LEVEL_ORDER):
                marker = "► " if i == self.menu_sel else "  "
                col = config.COLOR_TEXT if i == self.menu_sel \
                    else config.COLOR_TEXT_DIM
                level_key = {"leicht": "easy", "normal": "normal", "harte": "hard"}[key]
                center(message("menu.level_choice", index=i + 1, marker=marker,
                               level=self.tr("level." + level_key),
                               description=self.tr("level." + level_key + "_desc")),
                       260 + i * 44, color=col)
        else:  # briefing
            sc = config.SCENARIOS[self.scenario_key]
            scenario_key = {"s1_patrouille": "patrol", "s2_doppeljagd": "double",
                            "s3_abfang": "intercept", "s4_zufall": "random"}[self.scenario_key]
            center(self.tr("scenario." + scenario_key + ".title"), 170,
                   self.font_big, config.COLOR_WARN)
            layout.blit_block(s, self.tr("scenario." + scenario_key + ".brief"),
                              cx - 420, 210, 840, 180,
                              color=config.COLOR_TEXT, size=16)
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

        if self.world_mode == "procedural":
            from src.world.real_coast import sector_for_seed
            sector, _ = sector_for_seed(self.seed)
            world_label = sector["name"]
        else:
            world_label = self.tr("menu.fixed_chart")
        center(self.tr("menu.world_status", world=world_label, seed=self.seed),
               config.SCREEN_H - 68, color=config.COLOR_OK)
        center(self.tr("menu.seed_fullscreen", seed=self.seed,
                       action=self.tr("menu.windowed" if self.fullscreen
                                      else "menu.fullscreen")),
               config.SCREEN_H - 40, color=config.COLOR_TEXT_DIM)

    # --- W0: Draw-Grid ---

    @localized
    def draw(self) -> None:
        self._apply_text_size()
        s = self.screen
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
        elif self.in_menu:
            self.draw_menu()
        else:
            self.draw_top_bar()
            map_station = self.station in (Station.BRIDGE, Station.WEAPONS,
                                           Station.HELICOPTER)
            config.STATION_RECT = (config.STATION_PANEL_RECT if map_station
                                   else config.FULL_STATION_RECT)
            if map_station:
                draw_map_view(self)
                if self.station is Station.WEAPONS:
                    draw_weapons_overlay(self)
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
            self.draw_bottom_feed()
            self.draw_bottom_telemetry()
            self.draw_navigation_input()
            if self.game_over:
                self.draw_end_panel()
            if self.paused and not self.administration_open:
                self.draw_pause_overlay()
            config.STATION_RECT = config.STATION_PANEL_RECT
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
        elif self.commander_open:
            self.commander.draw(self)
        self.commander.draw_confirm(self)
        if self.msg and self._t < self.msg_until:
            layout.blit_block(s, localize(self.msg), 22, 62, config.SCREEN_W - 44, 76,
                              config.COLOR_WARN, size=28, align="center")
        if (not self.in_menu and not self.splash_active and self.editor is None
                and self.tooltips_enabled
                and not self.administration_open and not self.game_over):
            canvas = self._window_to_canvas(pygame.mouse.get_pos())
            payload = self.pinned_tooltip or self.tooltip_at(canvas)
            anchor = self._tooltip_anchor if self.pinned_tooltip else canvas
            if payload is not None and anchor is not None:
                layout.draw_tooltip(s, payload, anchor,
                                    (0, 0, config.SCREEN_W, config.SCREEN_H))
        if self._scanlines is not None:
            s.blit(self._scanlines, (0, 0))

    @localized
    def draw_navigation_input(self) -> None:
        """Show the active numeric command without hiding the simulation."""
        if self.input_mode is None:
            return
        label = self.tr("input." + self.input_mode)
        rect = pygame.Rect(330, 92, 620, 62)
        pygame.draw.rect(self.screen, (8, 20, 14), rect)
        pygame.draw.rect(self.screen, config.COLOR_WARN, rect, 2)
        layout.blit_line(self.screen, self.tr("input.value", label=label,
                                              value=self.input_buffer),
                         (rect.x + 14, rect.y + 8, rect.w - 28, 22),
                         config.COLOR_TEXT, size=18)
        layout.blit_line(self.screen, self.tr("input.hint"),
                         (rect.x + 14, rect.y + 34, rect.w - 28, 18),
                         config.COLOR_TEXT_DIM, size=12)

    @localized
    def draw_top_bar(self) -> None:
        layout.configure_for(self)
        s = self.screen
        pygame.draw.rect(s, (14, 24, 18), (0, 0, config.SCREEN_W, config.TOP_BAR_H))
        pygame.draw.line(s, config.COLOR_SONAR_RING,
                         (0, config.TOP_BAR_H - 1),
                         (config.SCREEN_W, config.TOP_BAR_H - 1), 1)
        sc = config.SCENARIOS[self.scenario_key]
        station = display_value("station", self.station.name, self.tr).upper()
        scenario = (localize(self.mission_name_display())
                    if self.custom_mission_definition is not None else
                    self.tr("scenario." + {"s1_patrouille": "patrol", "s2_doppeljagd": "double",
                                             "s3_abfang": "intercept", "s4_zufall": "random"}[self.scenario_key] + ".title"))
        txt = self.tr("top.status", station=station, scenario=scenario,
                      time=self.world.format_time(), speed=f"{self.ship.speed:4.1f}",
                      course=f"{self.ship.course:4.0f}")
        if self.paused:
            txt += "   || PAUSE"
        x = 920
        layout.blit_line(s, txt, (10, 4, x - 24, config.TOP_BAR_H - 8),
                         config.COLOR_TEXT, size=18)
        for i, ts in enumerate(config.TIME_SCALE_STEPS):
            col = config.COLOR_TEXT if i == self.time_scale_idx \
                else config.COLOR_TEXT_DIM
            layout.blit_line(s, f"{ts}x", (x + i * 50, 4, 48, config.TOP_BAR_H - 8),
                             col, size=16)
        layout.blit_line(s, "control.help.time_keys", (x + len(config.TIME_SCALE_STEPS) * 50, 4,
                                   40, config.TOP_BAR_H - 8), config.COLOR_TEXT_DIM, size=14)

    @localized
    def draw_bottom_feed(self) -> None:
        s = self.screen
        x, y, w, h = config.FEED_RECT
        pygame.draw.rect(s, (10, 18, 14), (x, y, w, h))
        pygame.draw.rect(s, config.COLOR_SONAR_RING, (x, y, w, h), 1)
        s.blit(self.font.render(
            localize(event_feed_heading(self.station)),
            True, config.COLOR_TEXT_DIM), (x + 8, y + 5))
        ly = y + 27
        for e in self.feed.recent(6):
            tag = e.tag()
            col = e.color()
            prefix = f"[{e.stamp}] {tag:4s} "
            s.blit(self.font.render(prefix, True, config.COLOR_TEXT_DIM),
                   (x + 8, ly))
            txt = localize(e.text)
            original = txt
            pw = self.font.size(prefix)[0]
            maxw = w - 16 - pw
            while txt and self.font.size(txt)[0] > maxw:
                txt = txt[:-1]
            if txt != original:
                txt += "…"
            s.blit(self.font.render(txt, True, col),
                   (x + 8 + pw, ly))
            ly += 23

    @localized
    def draw_bottom_telemetry(self) -> None:
        s = self.screen
        x, y, w, h = config.TELEMETRY_RECT
        pygame.draw.rect(s, (10, 18, 14), (x, y, w, h))
        pygame.draw.rect(s, config.COLOR_SONAR_RING, (x, y, w, h), 1)
        s.blit(self.font.render(localize("TELEMETRIE"), True, config.COLOR_TEXT_DIM),
               (x + 8, y + 5))
        profile = self.sonar.bt_profile
        thermo = (f"~{profile['thermocline_m']:.0f}m BT" if profile else "-- BT")
        rows = [
            ("telemetry.course_speed", f"{self.ship.course:4.0f}°  {self.ship.speed:4.1f} kn"),
            ("telemetry.noise", f"{self.ship.noise_level() * 100:3.0f} %"
                     + ("  KAV!" if self.ship.cavitating else "")),
            ("telemetry.sea_state", f"GG {self.world.sea_state}  Thermo {thermo}"),
            ("telemetry.flooding", f"{self.damage.total:3.0f}/"
                         f"{len(self.damage.compartments) * 100} "
                         f"({self.damage.avg_flood():.0f}%)"),
            ("telemetry.torpedoes", f"{self.torpedo_count}/{self.torpedo_total}  "
                         f"{self.torpedo_depth:3.0f} m"),
            ("telemetry.vls_chaff", f"{self.vls_cells}/{config.VLS_CELLS} / {self.chaff_cd:.0f}s"),
            ("telemetry.helo_roe", ("AN" if self.helo.airborne else "Hangar")
                          + f"  |  ROE {self.roe}"),
            ("telemetry.time_scale", f"x{self.time_scale}  ([ / ])"),
        ]
        ly = y + 26
        for label, val in rows:
            layout.status_line(s, x + 8, ly, w - 16, label, val,
                               label_w=100, size=13)
            ly += 18

    def _help_lines(self) -> tuple[list[str], int]:
        """Wrap before scrolling so every line remains reachable at either size."""
        layout.configure_for(self)
        intro, keys, params, tactics = get_help(self.station, self.tr)
        if self.help_page == 0:
            title, bindings = get_global_help(self.tr)
            text = title + "\n\n" + "\n".join(f"{k:<18} {a}" for k, a in bindings)
        elif self.help_page == 1:
            text = intro + "\n\n" + "\n".join(f"{k:<18} {a}" for k, a in keys)
        else:
            text = self.tr("help.sensors_tactics") + "\n\n" + "\n\n".join(params + tactics)
        face = layout.font(17)
        return layout.wrap_text(text, face, 960), max(1, 500 // layout._line_height(face))

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
        pygame.draw.rect(s, (12, 24, 18), (bx, by, bw, bh))
        pygame.draw.rect(s, config.COLOR_SONAR_RING, (bx, by, bw, bh), 2)
        help_title = self.tr("help.title", station=display_value(
            "station", self.station.name, self.tr).upper())
        layout.blit_line(s, help_title, (bx + 18, by + 10, bw - 36, 40),
                         config.COLOR_TEXT, size=28)
        x = bx + 20
        w = bw - 40
        y = by + 52
        lines, visible = self._help_lines()
        scroll = min(getattr(self, "help_scroll", 0), max(0, len(lines) - visible))
        layout.blit_block(s, "\n".join(lines[scroll:scroll + visible]), x, y, w, 500,
                          config.COLOR_TEXT, size=17, min_size=17)
        layout.blit_block(s, self.tr("control.help.scroll_hint", page=self.help_page + 1,
                                    pages=3, first=scroll + 1,
                                    last=min(len(lines), scroll + visible), total=len(lines)),
                          x, by + bh - 62, w, 54, config.COLOR_TEXT_DIM, size=14)

    @localized
    def draw_nations_overlay(self) -> None:
        s = self.screen
        dim = pygame.Surface((config.SCREEN_W, config.SCREEN_H), pygame.SRCALPHA)
        dim.fill((0, 0, 0, 160))
        s.blit(dim, (0, 0))
        bw, bh = 1100, 620
        bx = (config.SCREEN_W - bw) // 2
        by = (config.SCREEN_H - bh) // 2
        pygame.draw.rect(s, (12, 24, 18), (bx, by, bw, bh))
        pygame.draw.rect(s, config.COLOR_SONAR_RING, (bx, by, bw, bh), 2)
        s.blit(self.font_big.render(localize("NATIONEN & EINHEITEN"), True, config.COLOR_TEXT),
               (bx + 18, by + 12))
        cw, ch = 520, 260
        for i, key in enumerate(list(NATIONS.keys())[:4]):
            n = NATIONS[key]
            cx = bx + 18 + (i % 2) * (cw + 14)
            cyy = by + 52 + (i // 2) * (ch + 12)
            pygame.draw.rect(s, (14, 24, 18), (cx, cyy, cw, ch))
            pygame.draw.rect(s, n["color"], (cx, cyy, cw, ch), 1)
            s.blit(self.font_big.render(localize(message(
                "nations.card_title", flag=n["flag"], name=localize(n["name"]),
                status=self.tr("nations.hostile") if n["hostile"] else "")),
                True, n["color"]), (cx + 12, cyy + 10))
            layout.blit_block(s, n["desc"], cx + 12, cyy + 44, cw - 24, 130,
                              color=config.COLOR_TEXT, size=13)
            s.blit(self.font.render(localize(message(
                "nations.radar_value", radar=localize(n["radar"]))),
                True, config.COLOR_TEXT_DIM),
                   (cx + 12, cyy + 184))
            s.blit(self.font.render(localize(message(
                "nations.submarine_count", count=n["submarines"])),
                                    True, config.COLOR_TEXT_DIM),
                   (cx + 12, cyy + 206))
        s.blit(self.font.render(localize("N: schließen"), True, config.COLOR_TEXT_DIM),
               (bx + bw - 120, by + bh - 26))

    @localized
    def draw_save_ui(self) -> None:
        s = self.screen
        mode = self.tr("common.save" if self.save_ui == "save" else "common.load").upper()
        dim = pygame.Surface((config.SCREEN_W, config.SCREEN_H), pygame.SRCALPHA)
        dim.fill((0, 0, 0, 150))
        s.blit(dim, (0, 0))
        bw, bh = 620, 340
        bx = (config.SCREEN_W - bw) // 2
        by = (config.SCREEN_H - bh) // 2
        pygame.draw.rect(s, (12, 24, 18), (bx, by, bw, bh))
        pygame.draw.rect(s, config.COLOR_SONAR_RING, (bx, by, bw, bh), 2)
        layout.blit_line(s, self.tr("save.title", mode=mode),
                         (bx + 18, by + 14, bw - 36, 30), config.COLOR_TEXT, size=19)
        ly = by + 66
        for slot in range(1, 6):
            info = self.save_info[slot - 1] if len(self.save_info) == 5 else "--"
            selected = slot == self.save_slot
            col = config.COLOR_WARN if selected else config.COLOR_TEXT_DIM
            layout.blit_line(s, message("save.slot", marker=">" if selected else " ",
                                         slot=slot, info=localize(info)),
                             (bx + 24, ly, bw - 48, 28), col, size=17)
            ly += 38
        hint = "save.paused"
        if self.save_confirm:
            hint = ("save.overwrite" if self.save_ui == "save"
                    else "save.replace")
        layout.blit_line(s, hint, (bx + 18, by + bh - 50, bw - 36, 30),
                         config.COLOR_WARN, size=16)

    @localized
    def draw_end_panel(self) -> None:
        """M8: Endpanel mit Score-Bruchrechnung und Hinweisen."""
        s = self.screen
        dim = pygame.Surface((config.SCREEN_W, config.SCREEN_H), pygame.SRCALPHA)
        dim.fill((0, 0, 0, 140))
        s.blit(dim, (0, 0))
        w, h = 560, 300
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
             if self.mission_result == "SIEG" else "end.expired",
             config.COLOR_TEXT_DIM, False),
            ("", config.COLOR_TEXT, False),
            ("end.restart", config.COLOR_TEXT_DIM, False),
        ]
        ly = y + 40
        for text, c, big in lines:
            if not text:
                ly += 14
                continue
            text = localize(text)
            f = self.font_big if big else self.font
            r = f.render(text, True, c).get_rect(center=(config.SCREEN_W // 2, ly))
            s.blit(f.render(text, True, c), r)
            ly += 36 if big else 26

    @staticmethod
    def _options_row_rects():
        return tuple(pygame.Rect(292, 204 + index * 52, 696, 42) for index in range(6))

    @localized
    def draw_options_overlay(self) -> None:
        rect = pygame.Rect(260, 100, 760, 540)
        pygame.draw.rect(self.screen, (7, 18, 13), rect)
        pygame.draw.rect(self.screen, config.COLOR_WARN, rect, 2)
        layout.blit_line(self.screen, "option.title", (292, 126, 696, 44),
                         config.COLOR_WARN, size=28, align="center")
        values = (
            self.tr("option.language") + ": " + self.tr("option.language." + self.preferences.language),
            self.tr("option.fullscreen") + ": " + self.tr("common.on" if self.preferences.fullscreen else "common.off"),
            self.tr("option.audio") + ": " + self.tr("common.on" if self.audio.available else "common.off"),
            self.tr("option.large_text") + ": " + self.tr("common.on" if self.preferences.large_text else "common.off"),
            self.tr("option.tooltips") + ": "
            + self.tr("common.on" if self.tooltips_enabled else "common.off"),
            self.tr("commander.local.option"),
        )
        for index, (value, row) in enumerate(zip(values, self._options_row_rects())):
            color = config.COLOR_TEXT if index == self.options_sel else config.COLOR_TEXT_DIM
            prefix = "> " if index == self.options_sel else "  "
            layout.blit_line(self.screen, raw_text(prefix + value), row, color, size=18)
        layout.blit_block(self.screen,
                          "commander.local.options_hint",
                          292, 560, 696, 58, config.COLOR_TEXT_DIM, size=16,
                          align="center")

    @localized
    def draw_pause_overlay(self) -> None:
        s = self.screen
        dim = pygame.Surface((config.SCREEN_W, config.SCREEN_H), pygame.SRCALPHA)
        dim.fill((0, 0, 0, 90))
        s.blit(dim, (0, 0))
        pause = localize("PAUSE")
        r = self.font_big.render(pause, True, config.COLOR_TEXT).get_rect(
            center=(config.SCREEN_W // 2, config.SCREEN_H // 2 - 40))
        s.blit(self.font_big.render(pause, True, config.COLOR_TEXT), r)
        resume = localize("P = weiter")
        r = self.font.render(resume, True, config.COLOR_TEXT_DIM).get_rect(
            center=(config.SCREEN_W // 2, config.SCREEN_H // 2))
        s.blit(self.font.render(resume, True, config.COLOR_TEXT_DIM), r)

    @localized
    def draw_quit_overlay(self) -> None:
        """Require an explicit confirmation before leaving a live mission."""
        s = self.screen
        dim = pygame.Surface((config.SCREEN_W, config.SCREEN_H), pygame.SRCALPHA)
        dim.fill((0, 0, 0, 155))
        s.blit(dim, (0, 0))
        rect = pygame.Rect(280, 205, 720, 290)
        pygame.draw.rect(s, (12, 24, 18), rect)
        pygame.draw.rect(s, config.COLOR_WARN, rect, 2)
        layout.blit_line(s, "quit.title", (rect.x + 20, rect.y + 22,
                         rect.w - 40, 30), config.COLOR_WARN, size=24)
        layout.blit_line(s, "quit.warning",
                         (rect.x + 20, rect.y + 68, rect.w - 40, 22),
                         config.COLOR_TEXT, size=13)
        choices = (("quit.menu", "common.exit") if self.in_menu else
                   ("quit.game", "quit.save", "quit.no_save"))
        for index, label in enumerate(choices):
            selected = index == self.quit_selection
            layout.blit_line(s, message("menu.choice",
                                        marker="> " if selected else "  ",
                                        label=self.tr(label)),
                             (rect.x + 20, rect.y + 112 + index * 36, rect.w - 40, 30),
                             config.COLOR_WARN if selected else config.COLOR_TEXT,
                             size=20)
        layout.blit_line(s, "control.quit_hint",
                         (rect.x + 20, rect.bottom - 40, rect.w - 40, 26),
                         config.COLOR_TEXT_DIM, size=16)

    # --- Main loop ---

    def run(self) -> None:
        try:
            while self.running:
                if self.auto_quit is not None:
                    self.auto_quit -= 1
                    if self.auto_quit <= 0:
                        self.running = False
                wall_dt = self.clock.tick(config.FPS) / 1000.0
                dt = min(wall_dt, 0.1)
                self._t += dt
                for e in pygame.event.get():
                    self.handle_event(e)
                self.commander.pump(self)
                self.update(dt, audio_dt=wall_dt)
                self.draw()
                self.compose_frame()
        finally:
            try:
                self.commander.stop()
            finally:
                self.audio.shutdown()
                pygame.quit()
