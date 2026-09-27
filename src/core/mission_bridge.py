"""The custom-mission runtime bridge: which authored mission fields the
running simulation honours (``Game.start_custom_mission``) and the menu
entry points that start a mission (``Game`` mixin).

Verbatim moves from ``game.py`` (plan 1.3, phase 2, step 4). Phase 13 widens
the accepted subset here."""

import json
import math


from src.core import config
from src.core.i18n import message, raw_text
from src.core.mission_definition import static_preview, validate_mission
from src.enemies.civilian import CivilianShip
from src.enemies.sub import Sub
from src.enemies.surface import SurfaceShip
from src.ui.unit_editor import catalog_builtins
# Shared display/help constants and helpers (re-exported for tests/tools).
# Names tests and tools import from ``src.core.game`` (kept as re-exports).
from src.core.game_save import _valid_difficulty_dict


class MissionBridgeMixin:
    """Mission start half of ``Game``: built-in scenarios and the editor bridge."""

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
                             solution_threshold=lv["enemy_solution_threshold"],
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
