"""The custom-mission runtime bridge: which authored mission fields the
running simulation honours (``Game.start_custom_mission``) and the menu
entry points that start a mission (``Game`` mixin).

Verbatim moves from ``game.py`` (plan 1.3, phase 2, step 4). Phase 13 widens
the accepted subset here."""

import json
import math


from src.core import config, crashlog
from src.core.i18n import message, raw_text
from src.core.mission_definition import (_stable_seed, reference_sector_index,
                                         static_preview, validate_mission)
from src.air.flights import Flight
from src.enemies.animal import Animal
from src.core.tasking import TaskBoard
from src.core.incidents import IncidentBoard
from src.enemies.civilian import CivilianShip
from src.enemies.decoy import Decoy
from src.enemies.sub import Sub
from src.enemies.surface import SurfaceShip
from src.ui.unit_editor import catalog_builtins
from src.core.limits import MAX_ENEMY_TORPEDOES
from src.data.catalog import CATALOG
from src.data.user_content import default_store
from src.data.user_profiles import extend_catalog, referenced_user_keys
from src.weapons.torpedo import EnemyTorpedo
# Shared display/help constants and helpers (re-exported for tests/tools).
# Names tests and tools import from ``src.core.game`` (kept as re-exports).
from src.core.game_save import _valid_difficulty_dict


class MissionBridgeMixin:
    """Mission start half of ``Game``: built-in scenarios and the editor bridge."""

    def user_unit_profiles(self, keys) -> list[dict] | None:
        """The validated Unit Editor profiles for ``keys`` from the user
        store (``~/.u-jagd/units``), or None when one is missing or invalid."""
        store = default_store(config.SAVE_DIR)
        units = []
        for key in keys:
            try:
                units.append(store.load("unit", key))
            except (OSError, ValueError, TypeError, KeyError):
                return None
        return units

    def start_custom_mission(self, definition: dict, user_units=None) -> bool:
        """Start the currently runtime-effective subset of an authored mission.

        A 500 NM fixed or reference world, player/environment values, exact
        units of every kind (built-in or user profiles from the Unit Editor;
        a placed torpedo is a hostile torpedo already running), random
        groups, timed events and sink/survive/protect/reach objectives are
        effective. Other world sizes are rejected rather than silently
        ignored. ``user_units`` defaults to the referenced profiles in the
        user store.
        """
        user_keys = referenced_user_keys(definition) if isinstance(definition, dict) else []
        if user_units is None:
            user_units = self.user_unit_profiles(user_keys) if user_keys else []
        if user_units is None:
            return False
        user_units = [unit for unit in user_units if unit.get("key") in user_keys]
        try:
            catalog = extend_catalog(CATALOG, user_units)
        except (ValueError, KeyError, TypeError):
            return False
        if validate_mission(definition, catalog_builtins(catalog).keys()):
            return False
        world = definition["world"]
        reference_sector = (reference_sector_index(world.get("reference"))
                            if world["kind"] == "reference" else None)
        objective = definition["objective"]
        if (float(world["size_nm"]) != config.WORLD_SIZE_NM
                or world["kind"] not in ("fixed", "reference")
                or (world["kind"] == "reference" and reference_sector is None)):
            return False
        preview = static_preview(definition)
        markers = {item["id"]: item for item in preview["markers"]}
        exact = definition["units"]["exact"]
        placeable = (catalog.subs | catalog.surfaces | catalog.aircraft
                     | catalog.animals | catalog.decoys)
        group_profiles = [profile for group in definition["units"]["random_groups"]
                          for profile in group["profiles"]]
        # A placed torpedo is a hostile weapon already running at the frigate.
        torpedoes = [unit for unit in exact if unit["profile"] in catalog.torpedoes]
        if (any(profile not in placeable for profile in
                [unit["profile"] for unit in exact if unit not in torpedoes] + group_profiles)
                or any(catalog.torpedoes[unit["profile"]].used_by != "enemy"
                       or unit["side"] != "hostile" for unit in torpedoes)
                or len(torpedoes) > MAX_ENEMY_TORPEDOES):
            return False
        for unit in exact:
            profile_key = unit["profile"]
            profile = catalog.subs.get(profile_key) or catalog.surfaces.get(profile_key)
            if profile is None:
                continue                      # aircraft, animals, decoys: profile speed
            systems = catalog.profile_systems.get(profile_key)
            maximum_speed = (
                catalog.machines[systems.machine_key].maximum_speed_kn
                if systems is not None and systems.machine_key is not None else
                (profile.speed_kn[1] if isinstance(profile.speed_kn, tuple)
                 else profile.speed_kn))
            if float(unit.get("speed_kn", 0.0)) > maximum_speed:
                return False
        expected_targets = {unit["id"] for unit in exact
                            if unit["profile"] in catalog.subs
                            and unit["side"] == "hostile"}
        if objective["type"] == "sink" and set(objective["target_ids"]) != expected_targets:
            return False
        if objective["type"] == "protect":
            # Protected units are placed friendly or neutral units.
            sides = {unit["id"]: unit["side"] for unit in exact}
            if any(sides.get(target) not in ("friendly", "neutral")
                   for target in objective["target_ids"]):
                return False
        if objective["type"] == "reach" and objective.get("reach") is None:
            return False
        # A fixed-coordinate world keeps the game's current world mode (as
        # before); a reference world selects its packaged real sector.
        self.reset(int(definition["seed"]), "s4_zufall", publish_intel=False,
                   reference_sector=reference_sector)
        # Built-in plus the referenced user profiles; the save's catalog
        # snapshot carries them, so the mission continues after a load.
        self.runtime_catalog = catalog
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
        self.world.set_weather_override(env["weather"])
        thermo = float(env["thermocline_depth_m"])
        self.world._thermo = [[thermo for _ in row] for row in self.world._thermo]
        self.mission_units = {}
        for unit in exact:
            entity = self._place_mission_entity(unit, markers[unit["id"]])
            if entity is None:
                return False
            self.mission_units[unit["id"]] = self._mission_entity_id(entity)
        # Random groups: placed now unless a spawn event brings them later.
        spawned_later = {event["target_id"] for event in definition["events"]
                         if event["type"] == "spawn"}
        for marker in preview["markers"]:
            if marker["source"] == "seeded_random" and marker["group_id"] not in spawned_later:
                self._place_group_member(definition, marker)
        self.mission_events_pending = [event["id"] for event in preview["events"]]
        self.mission.name = definition["name"]
        self.mission.win_mode = definition["objective"]["type"]
        self.mission.time_limit_s = float(definition["objective"]["time_limit_s"])
        self.mission.sub_count = len(self.subs)
        self.mission.animal_count = self.mission.civilian_count = 0
        self.mission.asm_count = self.mission.warship_count = 0
        self.custom_mission_definition = json.loads(json.dumps(definition))
        # An authored mission brings its own events: no radio tasking.
        self.tasking = TaskBoard(None)
        self.incidents = IncidentBoard(None)
        # The patrol aircraft flies from the airfield nearest the placed ship.
        self._reset_mpa()
        self.feed.entries[-1].text = self._mission_started_notice()
        self.hq_msg(self._initial_threat_notice())
        self.in_menu = False
        self.main_menu = False
        self._reset_map_view()
        return True

    FLASH_TEXT_SIZE = 18
    FLASH_MAX_LINES = 2

    def _place_group_member(self, definition: dict, marker: dict) -> None:
        """Instantiate one seeded random-group member at its preview marker
        (course and speed from the mission seed, the group's side)."""
        group = next(group for group in definition["units"]["random_groups"]
                     if group["id"] == marker["group_id"])
        salt = _stable_seed(int(definition["seed"]), f"member:{marker['id']}")
        spec = dict(id=marker["id"], profile=marker["profile"], side=group["side"],
                    course_deg=float(salt % 360), speed_kn=config.MISSION_GROUP_SPEED_KN,
                    depth_m=config.MISSION_GROUP_DEPTH_M)
        entity = self._place_mission_entity(spec, marker)
        if entity is not None:
            self.mission_units[marker["id"]] = self._mission_entity_id(entity)

    def _place_mission_entity(self, unit: dict, marker: dict):
        """Create the placed entity of a mission unit spec (profile, side,
        course/speed/depth) at its marker; None for a profile the runtime
        cannot place."""
        x, y = self.world.nearest_water(marker["x"], marker["y"])
        profile = unit["profile"]
        lv = self.difficulty
        if profile in self.runtime_catalog.subs:
            entity = Sub(x, y, float(unit.get("depth_m", 60.0)),
                         float(unit.get("course_deg", 0.0)), profile,
                         self.rng_world, quiet_mult=lv["quiet_mult"],
                         attack_mult=lv["enemy_attack_mult"],
                         attack_cooldown_s=lv["enemy_cooldown_s"],
                         solution_threshold=lv["enemy_solution_threshold"],
                         profile=self.runtime_catalog.subs[profile],
                         decoy_profile=self.runtime_catalog.decoys[
                             self.runtime_catalog.runtime_bindings["submarine_decoy"]],
                         enemy_torpedo_profile=self.runtime_catalog.torpedoes[
                             self.runtime_catalog.runtime_bindings["enemy_torpedo"]],
                         side=unit["side"], runtime_catalog=self.runtime_catalog,
                         asw_rng=self.rng_asw)
            entity.speed = float(unit.get("speed_kn", 0.0))
            self.subs.append(entity)
            return entity
        if profile in self.runtime_catalog.surfaces:
            if self.runtime_catalog.surfaces[profile].category == "KAMPFSCHIFF":
                entity = SurfaceShip(
                    x, y, rng=self.rng_world, side=unit["side"],
                    doctrine="surface_combatant",
                    profile=self.runtime_catalog.surfaces[profile],
                    runtime_catalog=self.runtime_catalog)
                self.warships.append(entity)
            else:
                entity = CivilianShip(
                    x, y, rng=self.rng_world, side=unit["side"], doctrine="surface_transit",
                    profile=self.runtime_catalog.surfaces[profile],
                    runtime_catalog=self.runtime_catalog)
                self.civilians.append(entity)
            entity.course = entity.target_course = float(unit.get("course_deg", 0.0))
            entity.speed = entity.target_speed = float(unit.get("speed_kn", 0.0))
            return entity
        if profile in self.runtime_catalog.aircraft:
            # An aircraft belongs to the nearest charted airbase (the save
            # restores it from that base) and patrols a box around its spot.
            bases = self.world.coast.airbases
            if not bases:
                return None
            ax, ay = float(marker["x"]), float(marker["y"])
            base = min(bases, key=lambda item: (math.hypot(item["x"] - ax, item["y"] - ay),
                                                str(item["id"])))
            aircraft = self.runtime_catalog.aircraft[profile]
            entity = Flight(aircraft.kind, base, dest=None,
                            loiter_nm=config.MISSION_AIRCRAFT_LOITER_NM,
                            rng=self.flights.rng, seq=self.flights.next_seq(),
                            akey=profile, catalog=self.runtime_catalog, side=unit["side"])
            entity.x, entity.y = ax, ay
            entity.course = float(unit.get("course_deg", 0.0))
            # Aircraft fly at their profile speed (the save keeps no other).
            half = config.MISSION_AIRCRAFT_LOITER_NM
            entity.waypoints = [(ax + half, ay - half), (ax + half, ay + half),
                                (ax - half, ay + half), (ax - half, ay - half)]
            entity.waypoint_idx = 0
            entity.total_dist = None
            entity.traveled = 0.0
            self.flights.flights.append(entity)
            return entity
        if profile in self.runtime_catalog.animals:
            entity = Animal(x, y, profile, self.rng_world,
                            depth_m=(float(unit["depth_m"]) if "depth_m" in unit else None),
                            profile=self.runtime_catalog.animals[profile])
            entity.course = entity.target_course = float(unit.get("course_deg", entity.course))
            if float(unit.get("speed_kn", 0.0)) > 0.0:
                entity.speed = float(unit["speed_kn"])
            self.animals.append(entity)
            return entity
        if profile in self.runtime_catalog.torpedoes:
            # A torpedo already running at the start: straight on its
            # course until its seeker acquires (no launching unit).
            entity = EnemyTorpedo(x, y, float(unit.get("course_deg", 0.0)),
                                  float(unit.get("depth_m", 30.0)),
                                  len(self.enemy_torpedoes) + 1,
                                  profile=self.runtime_catalog.torpedoes[profile])
            self.enemy_torpedoes.append(entity)
            return entity
        if profile in self.runtime_catalog.decoys:
            # A placed decoy lies still at its spot (no launching unit).
            entity = Decoy(x, y, float(unit.get("depth_m", 60.0)), self.rng_world,
                           profile=self.runtime_catalog.decoys[profile])
            entity.course = float(unit.get("course_deg", entity.course))
            entity.speed = 0.0
            self.decoys.append(entity)
            return entity
        return None

    def _run_mission_events(self) -> None:
        """Authored events whose time has come, in order: a feed message
        (verbatim), a group spawn, a weather change or an objective decision."""
        definition = self.custom_mission_definition
        if definition is None or not self.mission_events_pending:
            return
        events = {event["id"]: event for event in definition["events"]}
        while self.mission_events_pending:
            event = events.get(self.mission_events_pending[0])
            if event is None:
                self.mission_events_pending.pop(0)
                continue
            if self.mission_time < float(event["at_s"]):
                return
            self.mission_events_pending.pop(0)
            kind = event["type"]
            if kind == "message":
                self.feed.add(self.world.format_time(), "mission", raw_text(event["message"]))
            elif kind == "spawn":
                for marker in static_preview(definition)["markers"]:
                    if (marker["source"] == "seeded_random"
                            and marker["group_id"] == event["target_id"]
                            and marker["id"] not in self.mission_units):
                        self._place_group_member(definition, marker)
                self.feed.add(self.world.format_time(), "mission",
                              message("runtime.mission.group_spawned"))
            elif kind == "weather":
                self.world.set_weather_override(event["weather"])
                weather_key = {"clear": "weather.kind.clear", "rain": "weather.kind.rain",
                               "storm": "weather.kind.storm", "fog": "weather.kind.fog"}
                self.feed.add(self.world.format_time(), "mission",
                              message("runtime.mission.weather_changed",
                                      weather=message(weather_key[event["weather"]])))
            elif kind == "objective" and self.mission_result is None:
                self._end_mission(event["action"] == "complete",
                                  raw_text(event["message"]) if event.get("message")
                                  else message("end.reason.event_complete"
                                               if event["action"] == "complete"
                                               else "end.reason.event_fail"))

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

    def _start_menu_mission(self) -> None:
        """Consume an exact pristine menu preparation, otherwise replace it."""
        sc = config.SCENARIOS[self.scenario_key]
        candidate_difficulty = {**config.DEFAULT_DIFFICULTY,
                                **(sc["difficulty"] if sc["difficulty"] is not None
                                   else self.menu_difficulty)}
        prepared = (self.seed, self.scenario_key, self.world_mode,
                    tuple(candidate_difficulty[name]
                          for name in config.DIFFICULTY_FIELD_ORDER),
                    self.hq_intel_mode(), self._preferred_level(),
                    self.start_weather, self.start_time,
                    id(self.world), id(self.sonar))
        reuse = (self.in_menu and self._prepared_menu_mission == prepared
                 and self.sim_t == 0.0 and self.mission_time == 0.0
                 and self.custom_mission_definition is None
                 and self.mission_result is None and not self.game_over
                 and self.running)
        self._prepared_menu_mission = None
        self.in_menu = False
        self.main_menu = False
        crashlog.note(f"mission {self.scenario_key}, world {self.world_mode}, "
                      f"seed {self.seed}, side {self.local_side}")
        if not reuse:
            self.reset(self.seed, self.scenario_key)
            return
        self._clear_controls()
        self.audio.stop()
        self.msg = ""
        self.msg_until = 0.0
        self._t = 0.0

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

    def _return_to_main_menu(self) -> None:
        """Leave the current mission (running or finished) without saving.

        The old world stays behind the menu until the next start replaces it;
        nothing is simulated while the menu owns the screen. A mission still
        running is kept in the autosave, so "Continue" can resume it.
        """
        self.autosave_on_exit()
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
        if self.lobby_round:
            # A mission started from the lobby returns the crew there.
            self.open_lobby()

    def _apply_start_environment(self) -> None:
        """The chosen start weather and time of day ("random" keeps the
        seed's). Runs in ``reset`` before anything draws from the world;
        a custom mission then sets its own authored environment."""
        weather = getattr(self, "start_weather", "random")
        hour = config.START_TIME_HOURS.get(getattr(self, "start_time", "random"))
        if hour is not None:
            self.world.hour = hour
        if weather in config.START_WEATHER_SEA_STATE:
            self.world.sea_state = config.START_WEATHER_SEA_STATE[weather]
            self.world.refresh_weather()
            self.world.set_weather_override(weather)

    def cycle_start_choice(self, kind: str, step: int) -> None:
        """Left/Right on a weather or time row of the briefing, lobby or
        campaign menu."""
        attribute, choices = (("start_weather", config.START_WEATHER_CHOICES)
                              if kind == "weather"
                              else ("start_time", config.START_TIME_CHOICES))
        current = getattr(self, attribute, "random")
        index = choices.index(current) if current in choices else 0
        setattr(self, attribute, choices[(index + step) % len(choices)])

    def start_choice_text(self, kind: str):
        """'Weather: rain' / 'Time of day: night' for a menu row."""
        value = self.start_weather if kind == "weather" else self.start_time
        return message(f"menu.start_{kind}", value=message(f"menu.start_{kind}.{value}"))

    def hq_intel_mode_menu(self) -> str:
        return (self.menu_hq_intel if self.menu_hq_intel in config.HQ_INTEL_MODES
                else "coarse")

    def _mission_started_notice(self):
        return message("runtime.mission.started",
                       name=self.mission_name_display(),
                       level=message("level." + self.level
                                     if self.level in config.LEVELS
                                     else "level." + config.LEVEL_DEFAULT),
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
        if domain == "underwater":
            from src.core import hunter
            hunter.set_hq_lead(self, bearing, distance)
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

    def mission_name_display(self):
        """Keep authored mission text opaque while localizing built-ins."""
        if self.custom_mission_definition is not None:
            return raw_text(self.mission.name)
        keys = {"patrouille": "mission.patrol", "doppeljagd": "mission.double",
                "konvoi": "mission.convoy", "nuklearer_abfang": "mission.intercept",
                "durchbruch": "mission.breakthrough", "aufklaerung": "mission.recon",
                "geleitzug": "mission.convoy_attack",
                "custom": "mission.custom"}
        return message(keys[self.mission.type_key])

    def mission_level_display(self):
        level = self.level if self.level in config.LEVELS else config.LEVEL_DEFAULT
        return message("level.display", level=self.tr("level." + level),
                       factor=round(config.LEVEL_SCORE_FACTOR[level] * 100))

    def mission_description_display(self):
        if self.custom_mission_definition is not None:
            return raw_text(self.custom_mission_definition.get("description", ""))
        scenario = config.SCENARIO_NAMES[self.scenario_key]
        return "scenario." + scenario + ".brief"

    def mission_entity(self, unit_id: str):
        """The placed entity a mission unit id names (own bookkeeping), or None."""
        entity_id = self.mission_units.get(unit_id)
        if entity_id is None:
            return None
        for group in (self.subs, self.civilians, self.warships, self.animals, self.decoys,
                      self.enemy_torpedoes):
            for entity in group:
                if entity.id == entity_id:
                    return entity
        for flight in self.flights.flights:
            if flight.seq == entity_id:       # flights are numbered by sequence
                return flight
        return None

    @staticmethod
    def _mission_entity_id(entity) -> int:
        return int(entity.seq if isinstance(entity, Flight) else entity.id)

    def mission_objective_display(self):
        if self.custom_mission_definition is not None:
            objective_type = self.custom_mission_definition["objective"]["type"]
            return message({"survive": "mission.objective.convoy",
                            "protect": "mission.objective.protect",
                            "reach": "mission.objective.reach"}.get(
                                objective_type, "mission.objective.sink"))
        if self.mission.win_mode in ("breakthrough", "recon", "convoy_attack"):
            objective = message("mission.objective." + self.mission.win_mode)
        elif self.mission.win_mode == "survive":
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
