"""Haupt-Game-Loop: Widescreen-Grid (Karte + Station + Feed + Telemetrie),
Zeitraffer 1x-30x, Szenarien, Multi-Slot-Save (W0-W4)."""

import json
import math
import os

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
from src.data import fingerprint as fingerprint_mod
from src.data.catalog import CATALOG
from src.enemies.animal import Animal
from src.enemies.civilian import CivilianShip
from src.enemies.decoy import Decoy
from src.enemies.sub import SUB_TYPES, Sub
from src.enemies.surface import SurfaceShip
from src.nations.nations import NATIONS, get_nation
from src.sensors.tracks import TrackPicture
from src.ship.damage import DamageModel
from src.ship.ship import Ship
from src.sonar.sonar import Contact, SonarSystem, TowState
from src.sonar.tma import BearingPoint, BearingTrack
from src.ui import layout
from src.ui.feedback import EventFeed
from src.ui.map_view import draw_map_view, map_hit_target
from src.ui.splash_view import draw_splash
from src.ui.sonar_view import draw_sonar_view
from src.ui.stations_view import (draw_bridge_view, draw_damage_view,
                                  draw_engine_view, draw_opz_view,
                                  draw_radio_view, draw_radar_view,
                                   draw_helicopter_view, station_hit_target)
from src.ui.stations_view import damage_compartment_at, opz_ppi_rect
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
                              buffer=config.AUDIO_MIXER_BUFFER_MS)
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
        self.splash_duration_s = 4.5

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
        self.sonar = SonarSystem(seed=seed)
        self._last_tow_state = self.sonar.tow_state
        rng = random.Random(seed)
        self.rng_world = rng  # Phase 2: geteilt mit allen Entitäten (Save/Load)
        self.seed = seed
        self.sim_t = 0.0
        self._sensor_acc = 0.0
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
                    depth_m=rng.uniform(40.0, min(100.0, SUB_TYPES[stype].max_depth_m * 0.5)),
                    course_deg=rng.uniform(0, 360), stype_key=stype, rng=rng,
                    quiet_mult=lv["quiet_mult"],
                    attack_mult=lv["enemy_attack_mult"],
                    attack_cooldown_s=lv["enemy_cooldown_s"])
            self.subs.append(s)

        # Meerestiere (M4): Falschkontakte
        self.animals = []
        for _ in range(self.mission.animal_count):
            ax, ay = at_dist(15.0, 90.0)
            self.animals.append(Animal(ax, ay,
                                       rng.choice(["whale", "fish_school", "jellyfish"]),
                                       rng=rng))

        # Zivile Schiffe (M4): AIS + Radar, jetzt auch passive Sonarkontakte
        self.civilians = []
        for _ in range(self.mission.civilian_count):
            cx, cy = at_dist(20.0, 100.0)
            self.civilians.append(CivilianShip(cx, cy, rng=rng))

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
                w = SurfaceShip(wx, wy, rng=rng, hostile=True)
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
        self.torpedo_total = lv["torp_total"]
        self.torpedo_count = lv["torp_total"]
        self.torpedo_depth = 60.0
        self.target = None
        self.selected_contact = None  # M9: im Sonar-Panel markierter Kontakt
        self.torpedoes = []
        self.torpedo_seq = 0
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
        self.surface_radar_on = config.RADAR_ON_DEFAULT
        self.air_radar_on = config.RADAR_ON_DEFAULT
        self.opz_range_nm = config.RADAR_RANGE_DEFAULT_NM
        self.roe = config.ROE_DEFAULT                # "STD" | "FREE"
        self.messages: list = []                     # Funkraum-Teletype
        self.dmg_cursor = 0
        self.dmg_team = 1
        self.helo = Helicopter(random.Random(seed + 555))
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
        self.air_picture = TrackPicture(config.RADAR_TRACK_STALE_S)
        self.opz_selected_track_id = None
        self.opz_affiliations = {}
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
        self.flights = FlightManager(self.world.coast, random.Random(seed + 2024))
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
        if validate_mission(definition, catalog_builtins(CATALOG).keys()):
            return False
        if (definition["events"] or definition["units"]["random_groups"]
                or definition["objective"]["type"] not in ("sink", "survive")
                or float(definition["world"]["size_nm"]) != config.WORLD_SIZE_NM
                or definition["world"]["kind"] != "fixed"
                or definition["environment"]["weather"] != "clear"):
            return False
        markers = {item["id"]: item for item in static_preview(definition)["markers"]}
        exact = definition["units"]["exact"]
        if any(unit["profile"] not in CATALOG.subs | CATALOG.surfaces
               for unit in exact):
            return False
        if any(unit["profile"] in CATALOG.subs and unit["side"] != "hostile"
               for unit in exact):
            return False
        expected_targets = {unit["id"] for unit in exact
                            if unit["profile"] in CATALOG.subs}
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
            if profile in CATALOG.subs:
                entity = Sub(x, y, float(unit.get("depth_m", 60.0)),
                             float(unit.get("course_deg", 0.0)), profile,
                             self.rng_world, quiet_mult=lv["quiet_mult"],
                             attack_mult=lv["enemy_attack_mult"],
                             attack_cooldown_s=lv["enemy_cooldown_s"])
                entity.speed = float(unit.get("speed_kn", 0.0))
                self.subs.append(entity)
            elif unit["side"] == "hostile":
                entity = SurfaceShip(
                    x, y, rng=self.rng_world, hostile=True,
                    profile=CATALOG.surfaces[profile])
                entity.course = entity.target_course = float(unit.get("course_deg", 0.0))
                entity.speed = entity.target_speed = float(unit.get("speed_kn", 0.0))
                self.warships.append(entity)
            else:
                entity = CivilianShip(
                    x, y, rng=self.rng_world, profile=CATALOG.surfaces[profile])
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
        self._sonar_audio_sequence = -1

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
                    with open(path) as f:
                        data = json.load(f)
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
            elif (e.type in (pygame.KEYDOWN, pygame.MOUSEBUTTONDOWN)
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
        if e.type != pygame.KEYDOWN and (self.input_mode is not None
                                         or self.paused or self.in_menu or self.game_over):
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
            if pygame.K_1 <= e.key <= pygame.K_8:
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
            esm_eligible = c.emitter and dist <= config.ESM_RANGE_NM
            radar_clear = (radar_eligible or esm_eligible) and not self.world.land_blocks_line(
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
            elif esm_eligible and radar_clear:
                noise = self._smooth_sensor_noise(
                    c.sensor_seed * 1000, self.sim_t, 5.0)
                brg = (bearing + noise * config.ESM_BEARING_ERR_DEG) % 360.0
                self.air_picture.observe(track_id=f"S-{c.id}", kind="SURFACE",
                    target_id=c.id, source="ESM", bearing=brg, range_nm=None,
                    observer_x=self.ship.x, observer_y=self.ship.y, course=None,
                    quality=.4, now=self.sim_t, label=f"S-{c.id}",
                    bearing_uncertainty_deg=config.ESM_BEARING_ERR_DEG / math.sqrt(3.0))
        for w in self.warships:
            if w.sunk:
                continue
            dist = w.distance_nm(self.ship)
            bearing = w.bearing_from_frigate(self.ship)
            aspect = config.aspect_rcs_factor(w.course, bearing)
            radar_eligible = surface_live and dist <= surface_eff * aspect
            esm_eligible = w.emitter and dist <= config.ESM_RANGE_NM
            radar_clear = (radar_eligible or esm_eligible) and not self.world.land_blocks_line(
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
            elif esm_eligible and radar_clear:
                noise = self._smooth_sensor_noise(
                    w.sensor_seed * 1000, self.sim_t, 5.0)
                brg = (bearing + noise * config.ESM_BEARING_ERR_DEG) % 360.0
                self.air_picture.observe(track_id=f"W-{w.id}", kind="SURFACE",
                    target_id=w.id, source="ESM", bearing=brg, range_nm=None,
                    observer_x=self.ship.x, observer_y=self.ship.y, course=None,
                    quality=.5, now=self.sim_t, label=f"W-{w.id}",
                    bearing_uncertainty_deg=config.ESM_BEARING_ERR_DEG / math.sqrt(3.0))
        for f in self.flights.flights:
            dist = f.distance_nm(self.ship)
            bearing = f.bearing_to_frigate(self.ship)
            radar_eligible = air_live and dist <= air_eff
            esm_eligible = f.radar_emitting and dist <= config.ESM_RANGE_NM
            radar_clear = (radar_eligible or esm_eligible) and not self.world.land_blocks_line(
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
            elif esm_eligible and radar_clear:
                noise = self._smooth_sensor_noise(
                    (f.seq + 20000) * 3571, self.sim_t, 5.0)
                brg = (bearing + noise * config.ESM_BEARING_ERR_DEG) % 360.0
                self.air_picture.observe(track_id=f"A-{f.seq}", kind="FLG",
                    target_id=f.seq, source="ESM", bearing=brg, range_nm=None,
                    observer_x=self.ship.x, observer_y=self.ship.y, course=None,
                    quality=.45, now=self.sim_t, label=f"E-{f.seq}",
                    bearing_uncertainty_deg=config.ESM_BEARING_ERR_DEG / math.sqrt(3.0))
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

    def esm_contacts(self) -> list:
        """M9: ESM-Peilungen von Radargeräten ziviler Schiffe (nur Richtung)."""
        out = []
        for c in self.civilians:
            if c.sunk or not c.emitter:
                continue
            if c.distance_nm(self.ship) > config.ESM_RANGE_NM:
                continue
            noise = self._smooth_sensor_noise(
                getattr(c, "sensor_seed", c.id) * 1000, self.sim_t, 5.0)
            bearing = (c.bearing_from_frigate(self.ship)
                       + noise * config.ESM_BEARING_ERR_DEG) % 360.0
            out.append((c, bearing))
        for w in self.warships:
            if w.sunk or not w.emitter:
                continue
            if w.distance_nm(self.ship) > config.ESM_RANGE_NM:
                continue
            noise = self._smooth_sensor_noise(
                getattr(w, "sensor_seed", w.id) * 1000, self.sim_t, 5.0)
            bearing = (w.bearing_from_frigate(self.ship)
                       + noise * config.ESM_BEARING_ERR_DEG) % 360.0
            out.append((w, bearing))
        return out

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
        lv = config.LEVELS[self.level]
        self.torpedoes.append(Torpedo(self.ship.x, self.ship.y, course,
                                       self.torpedo_depth, tgt, self.torpedo_seq,
                                       kill_dist_nm=lv["kill_dist_nm"],
                                       kill_depth_m=lv["kill_depth_m"],
                                       guidance_x=est_x, guidance_y=est_y))
        self.torpedo_count -= 1
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
            while sub.pending_torpedoes:
                x, y, course, depth = sub.pending_torpedoes.pop(0)
                self.enemy_torpedoes.append(
                    EnemyTorpedo(x, y, course, depth,
                                 len(self.enemy_torpedoes) + 1))

    def update(self, dt: float, audio_dt: float | None = None) -> None:
        """W0: Zeitraffer – sim_dt = dt * time_scale, Sub-Stepping gegen
        Tunneling (Torpedos/CIWS) bei hohen Faktoren. Kosmetische Timer
        (Flash, Scanline) bleiben reele Zeit (self._t). Die Audio-Cadence
        laeuft auf audio_dt (ungeklemmte Reelle Zeit aus dem Main-Loop);
        ohne audio_dt gilt der geklemmte dt-Rahmen."""
        if self.splash_active:
            if self._t - self.splash_started_at >= self.splash_duration_s:
                self.splash_active = False
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
            self._update_audio(audio_dt if audio_dt is not None else dt)
        else:
            self.audio.stop()
            self._sonar_audio_sequence = -1

    def _update_audio(self, dt: float) -> None:
        """Drain coherent 1x blocks; accelerated listening is a sampled preview."""
        listening = (self.station is Station.SONAR and self.sonar_audio_enabled
                     and not self.damage.station_down("sonar"))
        if not listening:
            self._stop_sonar_audio()
        self._audio_timer += dt
        due = self._audio_timer >= config.AUDIO_UPDATE_S
        preview = self.time_scale != 1
        if listening and (not preview or due):
            receiver = self.sonar.receiver
            blocks = receiver.blocks_since(self._sonar_audio_sequence)
            if preview:
                blocks = blocks[-1:]
            for sequence, samples in blocks:
                if self._sonar_audio_sequence < 0 or sequence != self._sonar_audio_sequence + 1:
                    self.audio.stop_sonar(immediate=True)
                if not self.audio.play_sonar(
                        self.sonar.listening_samples(samples),
                        receiver.sample_rate, self.sonar_volume,
                        bearing_deg=self.sonar.listen_bearing,
                        listener_bearing_deg=self.ship.course,
                        hold=self.time_scale == 1):
                    break
                self._sonar_audio_sequence = sequence
        if not due:
            return
        self._audio_timer %= config.AUDIO_UPDATE_S
        cavitation = 0.8 if self.ship.cavitating else 0.0
        self.audio.update_engine(self.ship.rpm(), blade_count=5,
                                 cavitation=cavitation,
                                 volume=0.0 if listening else 0.08 + 0.08 * self.ship.noise_level())
        self.audio.debug_log(dt, receiver=self.sonar.receiver)

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

    def _update_underwater_entities(self, dt: float) -> None:
        """Aktualisiert U-Boote, Tiere, Zivile und Dekoys."""
        for sub in self.subs:
            was_sunk = sub.sunk
            sub.update(dt, self.ship, self.world)
            if sub.sunk and not was_sunk:
                self.score += config.SCORE_SUNK
                self.flash(message("runtime.sunk.sub"), 4.0)
                self.feed.add(self.world.format_time(), "mission",
                              message("runtime.sunk.sub_feed", contact=sub.id))
            if sub.sunk and self.roe != "FREE":
                self.roe = "FREE"
                self.hq_msg(message("runtime.roe_free_confirmed"))
        for animal in self.animals:
            animal.update(dt, self.world)
        for civilian in self.civilians:
            civilian.update(dt, self.ship, self.world)
        for w in self.warships:
            w.update(dt, self.ship, self.world)
        for sub in self.subs:
            while sub.pending_decoys:
                dx, dy = sub.pending_decoys.pop(0)
                self.decoys.append(Decoy(dx, dy, sub.depth, self.rng_asm))
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
            torpedo.update(dt, self.ship, world=self.world)
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
            if torpedo.target in self.civilians:
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
        self.flights.update(dt, self.ship, world=self.world,
                            ship_emitting=(not self.damage.station_down("opz")
                                           and (self.surface_radar_on or self.air_radar_on)))
        self._check_mission_end()

    def _update_sim(self, dt: float) -> None:
        self.sim_t += dt
        self.mission_time += dt
        self._mission_time_warning()
        self._update_navigation(dt)
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
        self._update_underwater_entities(dt)
        self._update_aviation(dt)
        self._sensor_acc += dt
        self._radio_acc += dt
        self._slow_acc += dt
        publish_picture = self._sensor_acc >= .25
        self._update_air_defense(dt, publish_picture=publish_picture)
        # M13: Wetter-Hinweise per Teletype
        self.hq_timer -= dt
        if self.hq_timer <= 0.0:
            self.hq_timer = config.WEATHER_BULLETIN_PERIOD_S
            self.hq_msg(message("runtime.hq.profile", sea_state=self.world.sea_state,
                                depth=f"{self.world.thermocline_depth_m(self.ship.x, self.ship.y):.0f}"))
        self._update_enemy_torpedoes(dt)
        self._update_player_torpedoes(dt)
        if self._sensor_acc >= .25:
            sensor_dt = self._sensor_acc
            self._sensor_acc = 0.0
            self._update_sensors(sensor_dt)
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
            for sub in self.subs:
                if not sub.sunk and \
                        self._torus_dist(sub.x, sub.y, *sub.start_pos) > config.MISSION_ESCAPE_RADIUS_NM:
                    self._end_mission(False, message("end.reason.sub_escaped",
                                                     contact=sub.id))
                    return
            if all(sub.sunk for sub in self.subs):
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

    MAX_SAVED_ASMS = 10_000  # Existing collection ceiling also bounds queued expansion.

    @staticmethod
    def _rng_state(r) -> list:
        st = r.getstate()
        return [st[0], list(st[1]), st[2]]

    def save_state(self) -> dict:
        """v8: kompletter Simulationszustand mit physikalischer Echtzeitbewegung.

        Neu gegenüber v3: Kampfschiffe (warships), Feindtorpedo-IDs,
        Fingerprint-Daten, Flugzeug-Profilkeys, Zivil-Schadenszustand
        (sunk/damage statt hit).
        """
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
            "version": 8,
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
            # radar_on bleibt fuer externe/alte Leser erhalten; radars ist v4-additiv.
            "radar_on": self.radar_on,
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
            "radio_picture": self.radio_picture.serialize(),
            "radio_sel": self.radio_sel,
            "hfdf_log": self.hfdf_log,
            "hfdf_fixes": self.hfdf_fixes,
            "schedulers": dict(sensor=self._sensor_acc,
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
                          course=self.helo.course, torps=self.helo.torps,
                          buoys_left=self.helo.buoys_left, fuel_s=self.helo.fuel_s,
                          waypoint_x=self.helo.waypoint_x,
                          waypoint_y=self.helo.waypoint_y),
            "subs": [dict(id=s.id, x=s.x, y=s.y, depth=s.depth, course=s.course,
                          state=s.state, speed=s.speed, damage=s.damage,
                          torpedoes_left=s.torpedoes_left, heard_ping=s.heard_ping,
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
                          decision_reason=s.decision_reason)
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
                                fingerprint=c.fingerprint.to_dict())
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
                               sensor_seed=w.sensor_seed,
                               attack_left=w.attack_left,
                               anchor=(list(w.anchor)
                                       if w.anchor is not None else None),
                               fingerprint=w.fingerprint.to_dict())
                          for w in self.warships],
            "decoys": [dict(id=d.id, x=d.x, y=d.y, depth=d.depth,
                            course=d.course, speed=d.speed, life=d.life,
                            sensor_seed=d.sensor_seed)
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
                     search_phase=t._search_phase, midcourse=t._midcourse,
                     midcourse_timer=t._midcourse_timer,
                     kill_dist_nm=t.kill_dist_nm, kill_depth_m=t.kill_depth_m)
                for t in self.torpedoes],
            "enemy_torpedoes": [
                dict(id=t.id, x=t.x, y=t.y, course=t.course, depth=t.depth,
                     travel=t.travel, idx=t.idx)
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
                                traveled=f.traveled, active=f.active)
                           for f in self.flights.flights],
            },
            "sonar": {
                "next_id": self.sonar._next_contact_id,
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
                # Old in-memory queues (without a snapshot) freeze at save pose;
                # normal runtime queues already carry their transmit measurement.
                "pending_pings": [dict(target_id=p["target"].id,
                                        sent_at=p["sent_at"],
                                        ready_at=p["ready_at"],
                                        range_factor=p["range_factor"],
                                        mode=p["mode"],
                                        snapshot=(dict(p["snapshot"]) if "snapshot" in p else
                                                  self.sonar._measure_ping(
                                                      p["frigate"], p["target"], self.sim_t,
                                                      p["target"].distance_nm(p["frigate"]),
                                                      self.sonar._active_range_nm(
                                                          p["target"], p["world"],
                                                          p["range_factor"], p["mode"]))))
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
        if data:
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

        seed = data["seed"]
        w = data.get("world")
        if data.get("version", 1) >= 6 and w and w.get("coast"):
            coast_data = w["coast"]
            coast = Coastline(coast_data, float(coast_data.get(
                "world_nm", config.WORLD_SIZE_NM)))
            self.world_mode = w.get("mode", "procedural")
        else:
            coast = Coastline.load()
            self.world_mode = "fixed"
        self.world = World(seed=seed, coast=coast)
        if w:
            self.world.hour = w.get("hour", self.world.hour)
            self.world.sea_state = w.get("sea_state", self.world.sea_state)
            self.world.weather_shift_timer = w.get("weather_shift_timer", 0.0)
        self.seed = seed
        self.sonar = SonarSystem(seed=seed)
        rng = random.Random(seed + 99999)
        self.rng_world = rng
        self.flights = FlightManager(self.world.coast, random.Random(seed + 2024))
        ship = data["ship"]
        self.ship = Ship(x_nm=ship["x"], y_nm=ship["y"],
                         course_deg=ship["course"])
        self.ship.target_course = ship["target_course"]
        self.ship.speed = ship["speed"]
        self.ship.target_speed = ship["target_speed"]
        self.ship.order_idx = ship.get("order_idx", config.TELEGRAPH_DEFAULT)
        self.ship.turn_rate_scale = ship.get("turn_rate_scale", 1.0)
        self.ship.rudder_angle = ship.get("rudder_angle", 0.0)
        self.ship.yaw_rate = ship.get("yaw_rate", 0.0)
        self.ship.roll = ship.get("roll", 0.0)
        self.ship.pitch = ship.get("pitch", 0.0)
        self.ship.quiet_mode = ship.get("quiet_mode", False)
        self.ship._clock = ship.get("clock", 0.0)
        self.mission = Mission(seed, type_key=data.get("mission_type"))
        runtime_mission = data.get("mission_runtime", {})
        if isinstance(runtime_mission, dict):
            self.mission.name = str(runtime_mission.get("name", self.mission.name))
            win_mode = runtime_mission.get("win_mode", self.mission.win_mode)
            self.mission.win_mode = win_mode if win_mode in ("sink", "survive") else self.mission.win_mode
            limit = runtime_mission.get("time_limit_s", self.mission.time_limit_s)
            self.mission.time_limit_s = max(1.0, float(limit))
            self.mission.asm_count = max(0, int(runtime_mission.get(
                "asm_count", self.mission.asm_count)))
            custom = runtime_mission.get("custom_definition")
            self.custom_mission_definition = custom if isinstance(custom, dict) else None
            if self.custom_mission_definition is not None:
                environment = self.custom_mission_definition.get("environment", {})
                thermo = environment.get("thermocline_depth_m")
                if isinstance(thermo, (int, float)) and not isinstance(thermo, bool):
                    self.world._thermo = [[float(thermo) for _ in row]
                                          for row in self.world._thermo]
        else:
            self.custom_mission_definition = None
        self.mission_time = data["mission_time"]
        self.score = data["score"]
        self.incident = data["incident"]
        self.sim_t = data.get("sim_t", 0.0)
        saved_scale_idx = data.get("time_scale_idx", config.TIME_SCALE_DEFAULT)
        if data.get("version", 1) <= 4:
            # Alte Saves verwendeten (1, 2, 5, 10, 30); unklare Zwischenwerte
            # werden konservativ statt auf einen hoeheren Faktor abgebildet.
            saved_scale_idx = {0: 0, 1: 0, 2: 1, 3: 1, 4: 3}.get(
                saved_scale_idx, config.TIME_SCALE_DEFAULT)
        self.time_scale_idx = config.clamp(
            saved_scale_idx, 0, len(config.TIME_SCALE_STEPS) - 1)
        self.scenario_key = data.get("scenario_key", self.scenario_key)
        self.level = data.get("level", self.level)
        tp = data["torpedoes"]
        self.torpedo_total = tp["total"]
        self.torpedo_count = tp["count"]
        self.torpedo_depth = tp["depth"]
        self.target = None
        self.selected_contact = None
        self.torpedoes = []
        self.enemy_torpedoes = []
        self.warships = []
        self.warship_anchor = None
        # Schadenszustand (Phase 2: repair_mult wiederherstellen)
        dmg = data["damage"]
        self.damage = DamageModel(random.Random(seed + 777),
                                  repair_mult=dmg.get("repair_mult", 1.0))
        for k, c in dmg["compartments"].items():
            self.damage.compartments[k].state = c["state"]
            self.damage.compartments[k].flood = c["flood"]
            self.damage.compartments[k].fire = c.get("fire", 0.0)
        self.damage.teams.update({int(k): v for k, v in dmg["teams"].items()})
        self.damage.total = sum(c.flood for c in self.damage.compartments.values())
        self.damage.ship_sunk = self.damage.total >= config.DMG_SHIP_SINK_TOTAL
        # M10–M16
        self.sonar_mode = data.get("sonar_mode", "BOW")
        if self.sonar_mode not in ("BOW", "TOWED"):
            self.sonar_mode = "BOW"
        sonar_controls = data.get("sonar_controls", {})
        self.sonar.gain_db = sonar_controls.get("gain_db", 0.0)
        self.sonar.band_low_hz = sonar_controls.get("band_low_hz", 0.0)
        self.sonar.band_high_hz = sonar_controls.get("band_high_hz", config.LOFAR_FMAX_HZ)
        self.sonar.notch_enabled = sonar_controls.get("notch_enabled", False)
        self.sonar.peak_hold = sonar_controls.get("peak_hold", False)
        self.sonar.focus_locked = sonar_controls.get("focus_locked", False)
        self.sonar.tma_enabled = sonar_controls.get("tma_enabled", True)
        self.sonar.listen_bearing = float(sonar_controls.get("listen_bearing", 0.0)) % 360.0
        self.sonar.listen_filtered = bool(sonar_controls.get("listen_filtered", False))
        self.sonar.beam_width_deg = 6.0 if self.sonar_mode == "TOWED" else 12.0
        self.sonar._receiver_mode = self.sonar_mode
        self.sonar_page = int(sonar_controls.get("sonar_page", 0)) \
            % config.SONAR_PAGE_COUNT
        self.sonar_audio_enabled = bool(sonar_controls.get("audio_enabled", True))
        self.sonar_volume = config.clamp(float(sonar_controls.get("volume", .5)), 0.0, 1.0)
        self._sonar_audio_sequence = -1
        legacy_radar = bool(data.get("radar_on", config.RADAR_ON_DEFAULT))
        radars = data.get("radars", {})
        if isinstance(radars, dict):
            self.surface_radar_on = bool(radars.get("surface", legacy_radar))
            self.air_radar_on = bool(radars.get("air", legacy_radar))
            range_nm = float(radars.get("range_nm",
                                        config.RADAR_RANGE_DEFAULT_NM))
            self.opz_range_nm = (range_nm if range_nm in config.RADAR_RANGE_SCALES_NM
                                 else config.RADAR_RANGE_DEFAULT_NM)
        else:
            self.surface_radar_on = legacy_radar
            self.air_radar_on = legacy_radar
            self.opz_range_nm = config.RADAR_RANGE_DEFAULT_NM
        self.roe = data.get("roe", config.ROE_DEFAULT)
        self.asm_spawned = data.get("asm_spawned", 0)
        self.air_threat_reported = data.get("air_threat_reported", False)
        self.vls_cells = data.get("vls_cells", config.VLS_CELLS)
        self.ciws_ammo = data.get("ciws_ammo", config.CIWS_AMMO_DEFAULT)
        self.ciws_cooldown_s = data.get("ciws_cooldown_s", 0.0)
        self.air_picture = TrackPicture(config.RADAR_TRACK_STALE_S)
        self.air_picture.restore(data.get("air_picture", []))
        raw_affiliations = data.get("opz_affiliations", {})
        self.opz_affiliations = {
            str(track_id): value for track_id, value in raw_affiliations.items()
            if value in config.NATO_AFFILIATIONS
        } if isinstance(raw_affiliations, dict) else {}
        self.opz_selected_track_id = None
        self.radio_picture = TrackPicture(300.0)
        self.radio_picture.restore(data.get("radio_picture", []))
        self.radio_sel = data.get("radio_sel", 0)
        self.hfdf_log = list(data.get("hfdf_log", []))
        self.hfdf_fixes = dict(data.get("hfdf_fixes", {}))
        schedulers = data.get("schedulers", {})
        if not isinstance(schedulers, dict):
            raise ValueError("invalid scheduler state")

        def scheduler_acc(name: str, limit: float) -> float:
            value = schedulers.get(name, 0.0)
            if (not isinstance(value, (int, float)) or isinstance(value, bool)
                    or not math.isfinite(value) or not 0.0 <= value < limit):
                raise ValueError("invalid scheduler accumulator")
            return float(value)

        self._sensor_acc = scheduler_acc("sensor", .25)
        self._radio_acc = scheduler_acc("radio", .5)
        self._slow_acc = scheduler_acc("slow", .5)
        self.torpedo_seq = data.get("torpedo_seq", 0)
        self.messages = [tuple(m) for m in data.get("messages", [])]
        self.buoys = []
        self.buoy_seq = data.get("buoy_seq", 0)
        self.asms = []
        self.essms = []
        self.chaff_cd = data.get("chaff_cd", 0.0)
        self.dmg_cursor = data.get("dmg_cursor", 0)
        self.dmg_team = data.get("dmg_team", 1)
        self.asm_sel = data.get("asm_sel", 0)
        self.hq_timer = data.get("hq_timer", 15.0)
        self.rng_asm = random.Random(seed + 31337)
        self._joy_acc = 0.0
        self._joy_x_acc = 0.0
        self._joy_turn = 0
        hd = data.get("helo")
        self.helo = Helicopter(random.Random(seed + 555))
        if hd:
            self.helo.state = hd["state"]
            self.helo.x, self.helo.y = hd["x"], hd["y"]
            self.helo.course = hd["course"]
            self.helo.torps = hd.get("torps", config.HELO_TORPS)
            self.helo.buoys_left = hd.get("buoys_left", config.BUOY_COUNT)
            self.helo.fuel_s = hd.get("fuel_s", 0.0)
            self.helo.waypoint_x = hd.get("waypoint_x")
            self.helo.waypoint_y = hd.get("waypoint_y")
        # U-Boote (Phase 2: vollstaendiger KI-Zustand)
        self.subs = []
        for sd in data["subs"]:
            s = restore_entity(Sub, sd["x"], sd["y"], depth_m=sd["depth"], course_deg=sd["course"],
                    stype_key=sd["stype"], rng=rng)
            s.id = sd["id"]
            s.start_pos = tuple(sd["start_pos"])
            s.state = sd["state"]
            s.speed = sd["speed"]
            s.damage = sd["damage"]
            s.torpedoes_left = sd["torpedoes_left"]
            s.heard_ping = sd["heard_ping"]
            s.evac_left = sd["evac_left"]
            s.sink_left = sd["sink_left"]
            s.sunk = sd["state"] == "SUNK"
            s.quiet_mult = sd.get("quiet_mult", 1.0)
            s.attack_mult = sd.get("attack_mult", 1.0)
            s.attack_cooldown = sd.get("attack_cooldown",
                                       config.LEVELS[self.level]["enemy_cooldown_s"])
            s.attack_left = sd.get("attack_left", s.attack_cooldown)
            s.torpedo_alerted = sd.get("torpedo_alerted", False)
            s._decoy_cd = sd.get("decoy_cd", 0.0)
            s.turn_left = sd.get("turn_left", config.SUB_PATROL_TURN_PERIOD_S)
            s.turn_delta = sd.get("turn_delta", 0.0)
            s.target_course = sd.get("target_course", s.course)
            s.target_depth = sd.get("target_depth", s.depth)
            s.evade_offset = sd.get("evade_offset", s.evade_offset)
            s.sensor_seed = sd.get("sensor_seed", s.sensor_seed)
            s.fingerprint = (fingerprint_mod.Fingerprint.from_dict(sd["fingerprint"])
                             if sd.get("fingerprint") else
                             fingerprint_mod.roll_from_seed(
                                 s.sensor_seed, s.stype.acoustic))
            s.memory.update(sd.get("memory", {}))
            for age in ("last_ping_age", "last_torpedo_age"):
                if s.memory[age] is None:
                    s.memory[age] = float("inf")
            s.pending_torpedoes = [tuple(row) for row in sd.get("pending_torpedoes", [])]
            s.pending_decoys = [tuple(row) for row in sd.get("pending_decoys", [])]
            s.decision_reason = sd.get("decision_reason", "Patrouille")
            self.subs.append(s)
        # Tiere
        self.animals = []
        for ad in data["animals"]:
            a = restore_entity(Animal, ad["x"], ad["y"], ad["atype"], rng=rng, depth_m=ad.get("depth"))
            a.id = ad["id"]
            a.course = ad["course"]
            a.speed = ad["speed"]
            a.dead = ad["dead"]
            a.turn_left = ad.get("turn_left", 0.0)
            a.turn_delta = ad.get("turn_delta", 0.0)
            a.target_course = ad.get("target_course", a.course)
            a.target_depth = ad.get("target_depth", a.depth)
            a.sensor_seed = ad.get("sensor_seed", a.sensor_seed)
            self.animals.append(a)
        # Zivile
        self.civilians = []
        for cd in data["civilians"]:
            prof = CATALOG.surfaces.get(cd.get("signature_key"))
            c = restore_entity(SurfaceShip, cd["x"], cd["y"], rng=rng, profile=prof)
            if cd.get("id"):
                c.id = cd["id"]
            c.course = cd["course"]
            c.speed = cd["speed"]
            c.depth = cd.get("depth", 5.0)
            c.name = cd["name"]
            c.sunk = bool(cd.get("sunk", cd.get("hit", False)))
            c.damage = (float(cd["damage"]) if "damage" in cd
                        else (100.0 if c.sunk else 0.0))
            c.emitter = cd.get("emitter", c.emitter)
            c.turn_left = cd.get("turn_left", 0.0)
            c.turn_delta = cd.get("turn_delta", 0.0)
            c.target_course = cd.get("target_course", c.course)
            c.target_speed = cd.get("target_speed", c.speed)
            c.orbit_direction = cd.get("orbit_direction", c.orbit_direction)
            c.sensor_contact = tuple(cd["sensor_contact"]) if cd.get("sensor_contact") is not None else None
            c.sensor_contact_age = cd.get("sensor_contact_age", config.RADAR_TRACK_STALE_S)
            c.sunk_score_awarded = cd.get("sunk_score_awarded", c.sunk)
            c.sensor_seed = cd.get("sensor_seed", c.sensor_seed)
            c.fingerprint = (fingerprint_mod.Fingerprint.from_dict(cd["fingerprint"])
                             if cd.get("fingerprint") else
                             fingerprint_mod.roll_from_seed(
                                 c.sensor_seed, c.profile.acoustic))
            self.civilians.append(c)
        # KAMPFSCHIFF: feindliche Kriegsschiffe (v4)
        self.warships = []
        for wd in data.get("warships", []):
            prof = CATALOG.surfaces.get(wd.get("signature_key"))
            w = restore_entity(SurfaceShip, wd["x"], wd["y"], rng=rng, hostile=True,
                            profile=prof)
            if wd.get("id"):
                w.id = wd["id"]
            w.course = wd["course"]
            w.speed = wd["speed"]
            w.name = wd["name"]
            w.sunk = bool(wd.get("sunk", False))
            w.damage = float(wd.get("damage", 0.0))
            w.emitter = wd.get("emitter", w.emitter)
            w.turn_left = wd.get("turn_left", 0.0)
            w.turn_delta = wd.get("turn_delta", 0.0)
            w.target_course = wd.get("target_course", w.course)
            w.target_speed = wd.get("target_speed", w.speed)
            w.waypoint = tuple(wd["waypoint"]) if wd.get("waypoint") else None
            w.orbit_direction = wd.get("orbit_direction", w.orbit_direction)
            w.sensor_contact = tuple(wd["sensor_contact"]) if wd.get("sensor_contact") is not None else None
            w.sensor_contact_age = wd.get("sensor_contact_age", config.RADAR_TRACK_STALE_S)
            w.sunk_score_awarded = wd.get("sunk_score_awarded", w.sunk)
            w.pending_asm = [tuple(row) for row in wd.get("pending_asm", [])]
            w.sensor_seed = wd.get("sensor_seed", w.sensor_seed)
            w.attack_left = wd.get("attack_left", 0.0)
            w.anchor = tuple(wd["anchor"]) if wd.get("anchor") else None
            w.fingerprint = (fingerprint_mod.Fingerprint.from_dict(wd["fingerprint"])
                             if wd.get("fingerprint") else
                             fingerprint_mod.roll_from_seed(
                                 w.sensor_seed, w.profile.acoustic))
            self.warships.append(w)
        # W2: Dekoys
        self.decoys = []
        for dd in data.get("decoys", []):
            d = restore_entity(Decoy, dd["x"], dd["y"], dd["depth"], rng)
            if dd.get("id"):
                d.id = dd["id"]
            d.course = dd["course"]
            d.speed = dd["speed"]
            d.life = dd["life"]
            d.dead = False
            d.sensor_seed = dd.get("sensor_seed", d.sensor_seed)
            self.decoys.append(d)
        # Phase 2: laufende Entitaeten + Sensoren
        by_id = ({s.id: s for s in self.subs}
                  | {a.id: a for a in self.animals}
                  | {d.id: d for d in self.decoys}
                  | {c.id: c for c in self.civilians}
                  | {w.id: w for w in self.warships})
        for td in data.get("torpedoes_in_flight", []):
            tgt = by_id.get(td.get("target_id"))
            t = Torpedo(td["x"], td["y"], td["course"],
                        td.get("target_depth", self.torpedo_depth), tgt,
                        td["idx"],
                        kill_dist_nm=td.get("kill_dist_nm"),
                        kill_depth_m=td.get("kill_depth_m"),
                        speed_kn=td.get("speed_kn"),
                         guidance_x=td.get("guidance_x"),
                         guidance_y=td.get("guidance_y"), range_nm=td.get("range_nm"))
            t.depth = td.get("depth", 5.0)
            t.travel = td.get("travel", 0.0)
            t.seeker_acquired = td.get("seeker_acquired", False)
            t.terminal_active = td.get("terminal_active", t.seeker_acquired)
            t.state = td.get("state", "RUN")
            t._search_phase = td.get("search_phase", 0.0)
            t._midcourse = td.get("midcourse", t.course)
            t._midcourse_timer = td.get("midcourse_timer", 0.0)
            self.torpedoes.append(t)
        for ed in data.get("enemy_torpedoes", []):
            self.enemy_torpedoes.append(
                restore_entity(EnemyTorpedo, ed["x"], ed["y"], ed["course"], ed["depth"],
                              ed.get("idx", 0)))
            self.enemy_torpedoes[-1].travel = ed.get("travel", 0.0)
            self.enemy_torpedoes[-1].id = ed.get("id", self.enemy_torpedoes[-1].id)
        by_id.update((t.id, t) for t in self.enemy_torpedoes)
        for torpedo, td in zip(self.torpedoes, data.get("torpedoes_in_flight", [])):
            torpedo.target = by_id.get(td.get("target_id"))
            if "terminal_active" not in td and "range_nm" not in td and torpedo.target is None:
                # Old serializers retained an acquired decoy ID after retirement.
                # Keep terminal search, the commanded datum and wire age intact.
                torpedo.seeker_acquired = False
            torpedo._seeker_target = torpedo.target if torpedo.seeker_acquired else None
        self.asms = []
        for a in data.get("asms", []):
            asm = ASM(a["x"], a["y"], a["course"], a["seq"], self.rng_asm)
            asm.state = a.get("state", "LAUF")
            asm.jammer = a.get("jammer", False)
            asm.chaff_left = a.get("chaff_left", 0.0)
            asm.broken = a.get("broken", False)
            asm.age_s = a.get("age_s", 0.0)
            asm.travel = a.get("travel", 0.0)
            self.asms.append(asm)
        self.warship_asm_seq = data.get("warship_asm_seq", max(
            (a.seq - 1000 for a in self.asms if a.seq >= 1000), default=0))
        self.essms = []
        for e in data.get("essms", []):
            tgt = next((a for a in self.asms if a.seq == e.get("target_id")),
                       None)
            # Legacy ESSMs may outlive their ASM. Missing guidance follows the
            # saved flight path, never a reconstructed hidden target position.
            remaining = max(0.0, config.ESSM_RANGE_NM - e.get("travel", 0.0))
            essm = ESSM(e["x"], e["y"], e["course"], tgt, e["seq"],
                        guidance_x=e.get("guidance_x", e["x"] + remaining
                                         * math.sin(math.radians(e["course"]))),
                        guidance_y=e.get("guidance_y", e["y"] - remaining
                                         * math.cos(math.radians(e["course"]))),
                        target_id=e.get("track_target_id", e.get("target_id")))
            essm.travel = e.get("travel", 0.0)
            essm.state = e.get("state", "LAUF")
            essm.seeker_acquired = e.get("seeker_acquired", False)
            self.essms.append(essm)
        self.asm_seq = data.get("asm_seq", max(
            [self.asm_spawned] + [a.seq for a in self.asms]
            + [e.target_id for e in self.essms if e.target_id is not None]
            + [t.target_id for t in self.air_picture._tracks.values() if t.kind == "ASM"]))
        for bd in data.get("buoys", []):
            b = Sonobuoy(bd["x"], bd["y"], bd["seq"])
            b.battery_s = bd.get("battery_s", config.BUOY_BATTERY_S)
            self.buoys.append(b)
        flight_data = data.get("flights")
        if flight_data:
            bases = {b["id"]: b for b in self.world.coast.airbases}
            restored = []
            for fd in flight_data.get("items", []):
                base = bases.get(fd.get("base_id"))
                if base is None:
                    continue
                dest = bases.get(fd.get("dest_id"))
                flight = Flight(fd["kind"], base, dest=dest,
                                loiter_nm=fd.get("loiter_nm"),
                                rng=self.flights.rng, seq=fd["seq"],
                                akey=fd.get("akey"))
                flight.x = fd["x"]
                flight.y = fd["y"]
                flight.course = fd["course"]
                flight.total_dist = fd.get("total_dist")
                flight.traveled = fd.get("traveled", 0.0)
                flight.radar_emitting = fd.get("radar_emitting", flight.radar_emitting)
                flight.sensor_bearing = fd.get("sensor_bearing")
                flight.sensor_age = fd.get("sensor_age", config.RADAR_TRACK_STALE_S)
                flight.active = fd.get("active", True)
                if flight.dest is None and fd.get("waypoints"):
                    flight.waypoints = [tuple(p) for p in fd["waypoints"]]
                    flight.waypoint_idx = fd.get("waypoint_idx", 0)
                restored.append(flight)
            self.flights.flights = restored
            self.flights._seq = flight_data.get("seq", 0)
            self.flights._spawn_cd = flight_data.get("spawn_cd", 600.0)
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
                    mode = pd.get("mode", "BOW")
                    if "snapshot" in pd:
                        snapshot = dict(pd["snapshot"])
                    else:
                        # v1-v8 legacy queues have no transmit pose. Freeze once
                        # at the saved pose/time, conservatively rejecting a
                        # currently undetectable target; keep the original deadline.
                        # This uses seed/time noise, never shared RNG draws or AI warnings.
                        from src.sonar.sonar import tgt_gone
                        distance = target.distance_nm(self.ship)
                        active_range = self.sonar._active_range_nm(
                            target, self.world, pd.get("range_factor", 1.0), mode)
                        source_depth = self.sonar.towed_depth_m if mode == "TOWED" else 5.0
                        if (tgt_gone(target) or distance >= active_range
                                or (mode == "TOWED" and not self.sonar._tow_available())
                                or self.world.sonar_path_blocked(
                                    self.ship.x, self.ship.y, source_depth,
                                    target.x, target.y, target.depth)):
                            continue
                        snapshot = self.sonar._measure_ping(
                            self.ship, target, self.sim_t, distance, active_range)
                    self.sonar._pending_pings.append({
                        "target": target,
                        "frigate": self.ship,
                        "world": self.world,
                        "sent_at": pd.get("sent_at", self.sim_t),
                        "ready_at": pd.get("ready_at", self.sim_t),
                        "range_factor": pd.get("range_factor", 1.0),
                        "mode": mode,
                        "snapshot": snapshot,
                    })
        self._last_tow_state = self.sonar.tow_state
        self._observed_enemy_torpedoes.update(
            contact.target_id for contact in self.sonar.contacts.values()
            if contact.kind == "torpedo")
        # Phase 2: RNG-Zustaende (deterministischer Fortgang)
        rg = data.get("rngs", {})
        self._restore_rng(rng, rg.get("world"))
        self._restore_rng(self.world.rng, rg.get("world_weather"))
        self._restore_rng(self.rng_asm, rg.get("asm"))
        self._restore_rng(self.damage.rng, rg.get("damage"))
        self._restore_rng(self.helo.rng, rg.get("helo"))
        self._restore_rng(self.sonar.rng, rg.get("sonar"))
        self._restore_rng(self.flights.rng, rg.get("flight"))
        # Zustand und sichtbarer Bedienfokus
        ui = data.get("ui", {})
        self.station = Station.__members__.get(ui.get("station"), Station.BRIDGE)
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
            with open(path) as f:
                data = json.load(f)
        except (OSError, ValueError, RecursionError):
            return False
        return self._load_save_data(data)

    @staticmethod
    def _valid_save_document(data) -> bool:
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
                # Historical v1-v8 saves emitted these two explicit sentinels.
                return finite_number(value) or (
                    len(path) == 4 and path[0] == "subs"
                    and type(path[1]) is int and path[2] == "memory"
                    and path[3] in ("last_ping_age", "last_torpedo_age")
                    and value == float("inf"))
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
        if type(version) is not int or not 1 <= version <= 8:
            return False
        if not finite_tree(data):
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
        ship = data.get("ship")
        if not isinstance(ship, dict):
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
        max_salvo = max(profile.asm_salvo[1] for profile in CATALOG.surfaces.values())
        pending_missiles = 0
        entity_ids, group_ids = set(), {}
        for key, names in groups.items():
            group_ids[key] = set()
            for name in names:
                entries = data.get(name, [])
                if not isinstance(entries, list) or len(entries) > 10000:
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
                    if name in ("civilians", "warships"):
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
                    if name == "subs":
                        memory = entry.get("memory", {})
                        if not isinstance(memory, dict):
                            return False
                        for age in ("last_ping_age", "last_torpedo_age"):
                            value = memory.get(age)
                            if value is not None and value != float("inf") and not bounded(value, 0, 1e12):
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
                    for pending, width in (("pending_torpedoes", 4),
                                           ("pending_decoys", 2), ("pending_asm", 3)):
                        rows = entry.get(pending, [])
                        if (not isinstance(rows, list) or len(rows) > 10000
                                or any(not isinstance(row, (list, tuple)) or len(row) != width
                                       or any(not bounded(v, -1_000_000, 1_000_000) for v in row)
                                       or (pending == "pending_asm" and not identity(row[2]))
                                       for row in rows)):
                            return False
                        if pending == "pending_asm" and rows:
                            if name != "warships":
                                return False
                            profile_key = entry.get("signature_key")
                            if profile_key is not None and not isinstance(profile_key, str):
                                return False
                            profile = CATALOG.surfaces.get(profile_key)
                            low, high = profile.asm_salvo if profile is not None else (1, max_salvo)
                            if any(not low <= row[2] <= high for row in rows):
                                return False
                            pending_missiles += sum(row[2] for row in rows)
                            if pending_missiles > Game.MAX_SAVED_ASMS:
                                return False
        next_ids = data.get("next_entity_ids", {})
        if (not isinstance(next_ids, dict) or not set(next_ids) <= set(groups)
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
        if not isinstance(flights, dict) or not isinstance(flights.get("items", []), list):
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
        asms = data.get("asms", [])
        torpedoes = data.get("torpedoes_in_flight", [])
        essms = data.get("essms", [])
        if any(not isinstance(rows, list) or len(rows) > 10000
               or any(not isinstance(row, dict) for row in rows)
               for rows in (asms, torpedoes, essms)):
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
        for torpedo in torpedoes:
            target_id = torpedo.get("target_id")
            legacy_target = "terminal_active" not in torpedo and "range_nm" not in torpedo
            if target_id is not None and (not identity(target_id)
                    or (target_id not in entity_ids and not legacy_target)):
                return False
            distance = torpedo.get("range_nm", Torpedo.RANGE_NM)
            if (not bounded(distance, .001, 10000)
                    or not identity(torpedo.get("idx"))
                    or not bounded(torpedo.get("speed_kn", Torpedo.SPEED_KN), 0, 10000)
                    or not bounded(torpedo.get("depth", 5), 0, 10000)
                    or not bounded(torpedo.get("target_depth", 5), 0, 10000)
                    or not bounded(torpedo.get("travel", 0), 0, distance)
                    or not bounded(torpedo.get("midcourse_timer", 0), 0, Torpedo.WIRE_BREAK_S)
                    or torpedo.get("state", "RUN") not in ("RUN", "HIT", "SASE")):
                return False
            if torpedo.get("seeker_acquired", False) and target_id is None and not legacy_target:
                return False
        for essm in essms:
            target_id = essm.get("target_id")
            track_id = essm.get("track_target_id")
            legacy_target = not any(key in essm for key in (
                "guidance_x", "guidance_y", "track_target_id", "seeker_acquired"))
            if ((target_id is not None and (not identity(target_id)
                                           or (target_id not in asm_ids and not legacy_target)))
                    or not identity(essm.get("seq"))
                    or (track_id is not None and not identity(track_id))
                    or not bounded(essm.get("travel", 0), 0, config.ESSM_RANGE_NM)
                    or essm.get("state", "LAUF") not in ("LAUF", "HIT", "SASE")
                    or (essm.get("seeker_acquired", False) and target_id is None and not legacy_target)
                    or ("guidance_x" in essm and essm["guidance_x"] is None)):
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
        for key, limit in (("sensor", .25), ("radio", .5), ("slow", .5)):
            value = schedulers.get(key, 0.0)
            if not finite_number(value) or not 0.0 <= value < limit:
                return False
        sonar = data.get("sonar")
        if sonar is None:
            return True
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
               or not set(item) <= {"target_id", "sent_at", "ready_at", "range_factor", "mode", "snapshot"}
               or not identity(item.get("target_id"))
               or ("snapshot" in item and item["target_id"] not in entity_ids)
               or any(not bounded(item.get(key, 0), 0, 1e12)
                      for key in ("sent_at", "ready_at"))
               or not bounded(item.get("range_factor", 1), 0, 100)
               or item.get("mode", "BOW") not in ("BOW", "TOWED")
               or item.get("sent_at", sim_t) > sim_t
               or not 0 <= item.get("ready_at", sim_t) - item.get("sent_at", sim_t) <= 25000
               or ("snapshot" in item and (
                   not SonarSystem.valid_ping_snapshot(item["snapshot"])
                   or not item.get("sent_at", sim_t) <= item["snapshot"]["t"] <= sim_t))
               for item in pending_pings):
            return False
        return True

    def _load_save_data(self, data: dict) -> bool:
        import copy

        if not self._valid_save_document(data):
            return False
        candidate = copy.copy(self)
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
                    current = max(current, data.get("next_entity_ids", {}).get(key, 1),
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
            with open(path) as f:
                data = json.load(f)
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
            draw_splash(s, self._t - self.splash_started_at,
                        self.splash_duration_s, self.tr)
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
