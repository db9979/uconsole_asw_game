"""Radio tasking in the world: offers, the radio room's answer, progress.

``TaskingMixin`` connects the saved :class:`~src.core.tasking.TaskBoard` to
the simulation.  HQ positions are reports (with their error), shown on the
shared chart as the radio operator's plot; progress and completion are
judged from own ship and own helicopter, the lookout's published
identifications and, inside the model, the raft and the named ship.
"""

import math

from src.core import boat_missions, commander_traits, config, detrand, free_roam, hunter
from src.core import tasking
from src.core.i18n import message, raw_text
from src.core.tasking import TaskBoard
from src.core.game_rescue import persons_left
from src.enemies.civilian import CivilianShip
from src.sensors import lookout_id
from src.weapons import depth_charge


class TaskingMixin:
    """HQ orders and incidents during a built-in mission."""

    def _reset_tasking(self) -> None:
        first = detrand.uniform(*config.TASK_FIRST_OFFER_S, self.seed, "task-first")
        self.tasking = TaskBoard(first)
        self.task_sel = 0

    # --- geometry and presentation -------------------------------------------

    def _task_bearing_range(self, x: float, y: float) -> tuple[float, float]:
        dx, dy = x - self.ship.x, y - self.ship.y
        return math.degrees(math.atan2(dx, -dy)) % 360.0, math.hypot(dx, dy)

    def task_position(self, task) -> tuple[float, float]:
        """The reported position now (a supply ship dead-reckoned on)."""
        if task["course"] is not None and task["report_t"] is not None:
            return tasking.dead_reckon(task["x"], task["y"], task["course"],
                                       task["speed_kn"], self.sim_t - task["report_t"])
        return task["x"], task["y"]

    def task_view(self) -> list:
        """Detached rows for the radio room (newest first); no hidden truth."""
        rows = []
        for task in reversed(self.tasking.tasks):
            x, y = self.task_position(task)
            bearing, distance = self._task_bearing_range(x, y)
            state = task["state"]
            rows.append(dict(
                id=task["id"], kind=task["kind"], state=state,
                name=task["name"], persons=task["persons"],
                x=x, y=y, radius_nm=task["radius_nm"],
                course=task["course"], speed_kn=task["speed_kn"],
                bearing=bearing, range_nm=distance,
                respond_s=(max(0.0, task["respond_by_t"] - self.sim_t)
                           if state == "offered" else None),
                remaining_s=(max(0.0, task["deadline_t"] - self.sim_t)
                             if state in tasking.OPEN_STATES
                             and task["deadline_t"] is not None else None),
                progress=task["progress"], sighted=task["sighted"],
                verdict=task["verdict"], points=task["points"]))
        return rows

    def selected_task(self):
        rows = self.tasking.tasks
        if not rows:
            return None
        index = min(max(0, self.task_sel), len(rows) - 1)
        return list(reversed(rows))[index]

    def _cycle_task(self, delta: int) -> None:
        count = len(self.tasking.tasks)
        self.task_sel = (self.task_sel + delta) % count if count else 0

    def _task_label(self, task) -> str:
        return f"{task['kind'].upper()} {task['id']}"

    def _task_plot(self, task) -> None:
        """The radio operator plots the reported position on the chart."""
        self._task_unplot(task)
        label = self._task_label(task)
        if task["kind"] == "ras":
            result = self.plot_add("dr", task["x"], task["y"], label,
                                   course=task["course"], speed_kn=task["speed_kn"])
            if type(result) is int:
                # The DR line starts at the report time, not at plotting.
                for item in self.plot.objects:
                    if item["id"] == result:
                        item["t"] = float(task["report_t"])
        else:
            result = self.plot_add("circle", task["x"], task["y"], label,
                                   radius_nm=task["radius_nm"])
        task["plot_id"] = result if type(result) is int else None

    def _task_unplot(self, task) -> None:
        if task["plot_id"] is not None:
            self.plot.remove(task["plot_id"])
            task["plot_id"] = None

    def _task_notice(self, key: str, task, seconds: float = 5.0, **params) -> None:
        """HQ/radio traffic about one task: teletype, feed and a banner."""
        text = message(key, task=self._task_label(task),
                       name=raw_text(task["name"] or "-"), **params)
        self.hq_msg(text)
        self.flash(text, seconds)

    def _task_position_params(self, x: float, y: float) -> dict:
        bearing, distance = self._task_bearing_range(x, y)
        return dict(x=f"{x:.1f}", y=f"{y:.1f}", bearing=f"{bearing:03.0f}",
                    range=f"{distance:.1f}")

    # --- the radio room's answer ---------------------------------------------

    def accept_task(self, task_id):
        task = self.tasking.get(task_id)
        if task is None:
            return "stale_ref"
        if task["state"] != "offered" or self.game_over:
            return "not_ready"
        if self.damage.station_down("radio"):
            return "radio_down"
        task["state"] = "active"
        if task["kind"] == "emcon":
            # ``deadline_t`` holds the ordered silence from the offer on.
            task["deadline_t"] = self.sim_t + task["deadline_t"] - task["offered_t"]
            task["report_t"] = self.sim_t
        elif task["kind"] != "sar":
            task["deadline_t"] = self.sim_t + config.TASK_DURATION_S[task["kind"]]
        if task["kind"] != "emcon":
            self._task_plot(task)
        self._task_notice("task.accepted." + task["kind"], task, 4.0)
        return True

    def decline_task(self, task_id, by_crew: bool = False):
        """Decline an offered task; ``by_crew``: the radio autocrew declines
        for an operator who is busy elsewhere, without a penalty."""
        task = self.tasking.get(task_id)
        if task is None:
            return "stale_ref"
        if task["state"] != "offered" or self.game_over:
            return "not_ready"
        if self.damage.station_down("radio"):
            return "radio_down"
        if by_crew:
            self._close_task(task, "declined", notice="task.crew_declined", points=0)
        else:
            self._close_task(task, "declined")
        return True

    def _task_accept_selected(self) -> None:
        task = self.selected_task()
        result = self.accept_task(task["id"]) if task is not None else "stale_ref"
        if result is not True:
            self.flash(message("runtime.task." + result), 2.0)

    def _task_decline_selected(self) -> None:
        task = self.selected_task()
        result = self.decline_task(task["id"]) if task is not None else "stale_ref"
        if result is not True:
            self.flash(message("runtime.task." + result), 2.0)

    def _close_task(self, task, state: str, notice: str | None = None,
                    points: int | None = None) -> None:
        if points is None:
            points = config.SCORE_TASK[task["kind"]][("done", "failed", "declined").index(state)]
        task["state"] = state
        task["ended_t"] = self.sim_t
        task["points"] = points
        self.score += points
        self._task_unplot(task)
        self._task_notice(notice or f"task.{state}.{task['kind']}", task, 5.0,
                          points=f"{points:+d}")
        morale = getattr(self, "_crew_event", None)
        if morale is not None:
            morale(f"task_{state}_{task['kind']}")

    # --- the schedule ----------------------------------------------------------

    def _commander_hint(self, dt: float) -> None:
        """Early in a mission HQ sometimes hints at the enemy commander's
        character (``commander_traits``): to the frigate about the first AI
        submarine, to a crewed boat about an AI hunter frigate's captain."""
        at = commander_traits.HINT_AT_S
        if not self.mission_time - dt < at <= self.mission_time or self.game_over:
            return
        boat = self._opfor
        subs = sorted((sub for sub in self.subs if sub.side == "hostile" and not sub.sunk
                       and (boat is None or sub is not boat.sub)), key=lambda sub: sub.id)
        if subs and commander_traits.hinted(self.seed, "frigate"):
            self.hq_msg(message("hq.commander_hint." + commander_traits.sub_kind(subs[0])))
        if (boat is not None and hunter.active(self)
                and commander_traits.hinted(self.seed, "uboot")):
            boat.orders.event("hq_hint_" + commander_traits.hunter_kind(self.seed))

    def _update_tasking(self, dt: float) -> None:
        self._commander_hint(dt)
        board = getattr(self, "tasking", None)
        if board is None or self.game_over:
            return
        self._update_helo_hoist(dt)
        for task in list(board.open_tasks()):
            if task["state"] == "offered":
                if task["kind"] == "sar":
                    self._drift_raft(task, dt)
                if self.sim_t >= task["respond_by_t"]:
                    self._close_task(task, "declined", notice="task.no_answer")
                continue
            getattr(self, "_progress_task_" + task["kind"])(task, dt)
        # A free patrol has no cap and a shorter interval (free_roam.py).
        interval, cap = free_roam.task_interval(self)
        if (board.enabled and self.sim_t >= board.next_offer_t
                and (cap is None or board.offers < cap)
                and len(board.open_tasks()) < config.TASK_MAX_OPEN):
            self._offer_task()
            board.next_offer_t = self.sim_t + detrand.uniform(
                *interval, self.seed, "task-interval", board.offers)

    def _offer_task(self, kind: str | None = None, requested: bool = False,
                    target=None):
        """Offer the next task (``kind`` forces one, for tests and drills;
        ``requested``: own ship asked for it, so HQ's own reasons are moot;
        ``target``: the ship an identify task names, from an incident)."""
        board = self.tasking
        index = board.offers
        builders = [name for name in tasking.KINDS
                    if (kind is None or name == kind)
                    and (requested or target is not None
                         or getattr(self, "_task_candidate_" + name)())]
        if not builders:
            board.offers += 1
            return None
        kind = builders[int(detrand.u01(self.seed, "task-kind", index) * len(builders))]
        task = (self._build_task_identify(index, target) if target is not None
                else getattr(self, "_build_task_" + kind)(index))
        if task is None:
            board.offers += 1
            return None
        base = dict(kind=kind, state="offered", offered_t=self.sim_t,
                    respond_by_t=self.sim_t + config.TASK_RESPONSE_S,
                    deadline_t=None, ended_t=None, course=None, speed_kn=None,
                    report_t=self.sim_t, name=None, persons=0, target_id=None,
                    true_x=None, true_y=None, progress=0.0, sighted=False,
                    plot_id=None, verdict=None, points=0, aboard=0)
        task = board.add({**base, **task})
        self.task_sel = 0
        key = "task.offer." + kind
        params = self._task_position_params(task["x"], task["y"])
        if kind == "sar":
            params["persons"] = task["persons"]
            params["minutes"] = f"{(task['deadline_t'] - self.sim_t) / 60.0:.0f}"
        elif kind == "ras":
            params["course"] = f"{task['course']:03.0f}"
            params["speed"] = f"{task['speed_kn']:.0f}"
        elif kind == "emcon":
            params["minutes"] = f"{(task['deadline_t'] - self.sim_t) / 60.0:.0f}"
        text = message(key, task=self._task_label(task),
                       name=raw_text(task["name"] or "-"), **params)
        self.hq_msg(text)
        if not requested:
            # Said aloud on the bridge (callouts.py) with a short radio tone.
            self.announce(message("runtime.task.offered", task=self._task_label(task)),
                          "funk", 5.0)
            self.audio.play_alert("task")
        if kind == "sar":
            self._emit_sound("alarm")
        return task

    # --- candidates ------------------------------------------------------------

    def _task_candidate_sar(self) -> bool:
        return not self.tasking.active("sar")

    def _identify_candidates(self) -> list:
        return [ship for ship in sorted(self.civilians, key=lambda item: item.id)
                if not ship.sunk and ship.side == "neutral"
                and getattr(ship, "live_mmsi", None) is None
                and math.hypot(ship.x - self.ship.x, ship.y - self.ship.y)
                <= config.TASK_IDENTIFY_RANGE_NM
                and not any(task["target_id"] == ship.id
                            for task in self.tasking.tasks if task["kind"] == "identify")]

    def _task_candidate_identify(self) -> bool:
        return bool(self._identify_candidates())

    def _task_candidate_datum(self) -> bool:
        # In scenarios 8 and 9 HQ has no intelligence on the boat: the
        # frigate knows only what it guards.
        if boat_missions.mode(self) in boat_missions.UNREPORTED_MODES:
            return False
        return any(sub.side == "hostile" and not sub.sunk for sub in self.subs)

    def _task_candidate_ras(self) -> bool:
        if any(task["kind"] == "ras" for task in self.tasking.tasks):
            return False
        profile = self.runtime_catalog.surfaces.get(config.TASK_RAS_PROFILE)
        low_fuel = (self.ship.fuel_kg
                    < config.TASK_RAS_FUEL_FRACTION * self.ship.fuel_capacity_kg)
        stores = self.ras_shortfall()
        return profile is not None and (low_fuel or any(
            stores[key] > 0 for key in ("torpedoes", "asroc", "depth_charges")))

    def _task_candidate_patrol(self) -> bool:
        # Only a free patrol holds sectors for HQ.
        return free_roam.frigate_side(self) and not any(
            task["kind"] == "patrol" for task in self.tasking.open_tasks())

    def _task_candidate_emcon(self) -> bool:
        return ((self.surface_radar_on or self.air_radar_on)
                and not self.tasking.active("emcon"))

    # --- builders ----------------------------------------------------------------

    def _task_water_point(self, index: int, tag: str, low: float, high: float):
        """A deterministic point in deep enough water ``low..high`` NM away."""
        for attempt in range(8):
            angle = math.radians(360.0 * detrand.u01(self.seed, tag + "-brg", index, attempt))
            distance = detrand.uniform(low, high, self.seed, tag + "-rng", index, attempt)
            x = config.clamp(self.ship.x + distance * math.sin(angle),
                             5.0, self.world.size_nm - 5.0)
            y = config.clamp(self.ship.y - distance * math.cos(angle),
                             5.0, self.world.size_nm - 5.0)
            if not self.world.on_land(x, y) and self.world.depth_m(x, y) > 20.0:
                return x, y
        return None

    def _build_task_sar(self, index: int):
        point = self._task_water_point(index, "task-sar", *config.TASK_SAR_RANGE_NM)
        if point is None:
            return None
        tx, ty = point
        sigma = config.TASK_SAR_REPORT_SIGMA_NM
        name = tasking.DISTRESS_NAMES[int(detrand.u01(self.seed, "task-sar-name", index)
                                          * len(tasking.DISTRESS_NAMES))]
        sst = self.world.ocean.sea_surface_temperature_c(self.world.hour)
        return dict(
            x=tx + sigma * detrand.normal(self.seed, "task-sar-ex", index),
            y=ty + sigma * detrand.normal(self.seed, "task-sar-ey", index),
            radius_nm=config.TASK_SAR_RADIUS_NM, name=name,
            persons=2 + int(detrand.u01(self.seed, "task-sar-persons", index) * 5),
            true_x=tx, true_y=ty,
            deadline_t=self.sim_t + tasking.survival_s(sst))

    def _build_task_identify(self, index: int, ship=None):
        if ship is None:
            ships = self._identify_candidates()
            ship = ships[int(detrand.u01(self.seed, "task-id-ship", index) * len(ships))]
        sigma = config.TASK_IDENTIFY_REPORT_SIGMA_NM
        return dict(
            x=ship.x + sigma * detrand.normal(self.seed, "task-id-ex", index),
            y=ship.y + sigma * detrand.normal(self.seed, "task-id-ey", index),
            radius_nm=config.TASK_IDENTIFY_RADIUS_NM,
            name=str(ship.name)[:tasking.MAX_NAME] or "-", target_id=ship.id,
            verdict=None)

    def _build_task_datum(self, index: int):
        hostile = [sub for sub in sorted(self.subs, key=lambda item: item.id)
                   if sub.side == "hostile" and not sub.sunk]
        if detrand.u01(self.seed, "task-datum-real", index) < config.TASK_DATUM_REAL:
            sub = hostile[int(detrand.u01(self.seed, "task-datum-sub", index) * len(hostile))]
            sigma = config.TASK_DATUM_SIGMA_NM
            x = sub.x + sigma * detrand.normal(self.seed, "task-datum-ex", index)
            y = sub.y + sigma * detrand.normal(self.seed, "task-datum-ey", index)
            x, y = self.world.nearest_water(
                config.clamp(x, 1.0, self.world.size_nm - 1.0),
                config.clamp(y, 1.0, self.world.size_nm - 1.0))
        else:
            point = self._task_water_point(index, "task-datum",
                                           *config.TASK_DATUM_FALSE_RANGE_NM)
            if point is None:
                return None
            x, y = point
        return dict(x=x, y=y, radius_nm=config.TASK_DATUM_RADIUS_NM)

    def _build_task_ras(self, index: int):
        point = self._task_water_point(index, "task-ras", *config.TASK_RAS_RANGE_NM)
        if point is None:
            return None
        x, y = point
        # The supply ship steams across the line to own ship.
        to_ship = math.degrees(math.atan2(self.ship.x - x, -(self.ship.y - y))) % 360.0
        side = 90.0 if detrand.u01(self.seed, "task-ras-side", index) < 0.5 else -90.0
        course = round((to_ship + side) % 360.0 / 5.0) * 5.0 % 360.0
        tanker = CivilianShip(
            x, y, rng=self.rng_world, side="friendly", doctrine="surface_transit",
            profile=self.runtime_catalog.surfaces[config.TASK_RAS_PROFILE],
            runtime_catalog=self.runtime_catalog)
        tanker.course = tanker.target_course = course
        tanker.speed = tanker.target_speed = config.TASK_RAS_SPEED_KN
        # It holds course and speed through the replenishment window.
        tanker.turn_left = config.TASK_RESPONSE_S + config.TASK_DURATION_S["ras"]
        self.civilians.append(tanker)
        return dict(x=x, y=y, radius_nm=1.0, course=course,
                    speed_kn=config.TASK_RAS_SPEED_KN,
                    name=str(tanker.name)[:tasking.MAX_NAME] or "-",
                    target_id=tanker.id)

    def _build_task_patrol(self, index: int):
        point = self._task_water_point(index, "task-patrol", *config.FREE_PATROL_RANGE_NM)
        if point is None:
            return None
        return dict(x=point[0], y=point[1], radius_nm=config.FREE_PATROL_RADIUS_NM)

    def _build_task_emcon(self, index: int):
        duration = detrand.uniform(*config.TASK_EMCON_S, self.seed, "task-emcon", index)
        return dict(x=self.ship.x, y=self.ship.y, radius_nm=1.0,
                    deadline_t=self.sim_t + duration)

    # --- progress ----------------------------------------------------------------

    def _task_expired(self, task) -> bool:
        if self.sim_t >= task["deadline_t"]:
            self._close_task(task, "failed")
            return True
        return False

    def _drift_raft(self, task, dt: float) -> None:
        u, v = self.world.current_vec(task["true_x"], task["true_y"])
        leeway = config.kn_to_nm_per_s(self.world.wind_speed_kn) * config.TASK_SAR_LEEWAY
        towards = math.radians((self.world.wind_from_deg + 180.0) % 360.0)
        x = task["true_x"] + (config.kn_to_nm_per_s(u) + leeway * math.sin(towards)) * dt
        y = task["true_y"] - (config.kn_to_nm_per_s(v) + leeway * math.cos(towards)) * dt
        task["true_x"] = config.clamp(x, 0.0, self.world.size_nm)
        task["true_y"] = config.clamp(y, 0.0, self.world.size_nm)

    def _helo_on_task(self) -> bool:
        return self.helo.state == "AUF"

    def _progress_task_sar(self, task, dt: float) -> None:
        self._drift_raft(task, dt)
        if persons_left(task) == 0:
            # Everybody out of the water: done once the helicopter's cabin
            # is empty again (back on deck, ``game_rescue``).
            if task["aboard"] == 0:
                self._close_task(task, "done")
            return
        if self.sim_t >= task["deadline_t"]:
            task["aboard"] = 0
        if self._task_expired(task):
            return
        rx, ry = task["true_x"], task["true_y"]
        ship_d = math.hypot(self.ship.x - rx, self.ship.y - ry)
        helo_d = (math.hypot(self.helo.x - rx, self.helo.y - ry)
                  if self._helo_on_task() else math.inf)
        if not task["sighted"]:
            sight = (config.TASK_SAR_SIGHT_NIGHT_NM if self.world.is_night()
                     else config.TASK_SAR_SIGHT_DAY_NM)
            sight = min(sight, float(getattr(self.world, "visibility_nm", sight)))
            if min(ship_d, helo_d) <= sight:
                task["sighted"] = True
                task["x"], task["y"] = rx, ry
                task["radius_nm"] = 0.3
                task["report_t"] = self.sim_t
                self._task_plot(task)
                bearing, distance = self._task_bearing_range(rx, ry)
                self.announce(message("task.sar.sighted", task=self._task_label(task),
                                      bearing=f"{bearing:03.0f}",
                                      range=f"{distance:.1f}"), "ausguck", 5.0)
        elif min(ship_d, helo_d) <= 2.0 * config.TASK_SAR_SIGHT_DAY_NM:
            # Kept in sight: the chart position follows the raft.
            task["x"], task["y"] = rx, ry
        # The ship alongside takes the raft's crew over the side; the
        # helicopter lifts them one by one on order (``game_rescue``).
        if ship_d <= config.TASK_SAR_SHIP_NM and self.ship.speed <= config.TASK_SAR_SHIP_KN:
            task["progress"] = min(1.0, task["progress"] + dt / config.TASK_SAR_SHIP_S)
            if task["progress"] >= 1.0 and task["aboard"] == 0:
                self._close_task(task, "done")

    def _progress_task_identify(self, task, dt: float) -> None:
        ship = self._civilian_by_id(task["target_id"])
        if ship is None or ship.sunk:
            self._close_task(task, "failed")
            return
        if self._task_expired(task):
            return
        track = self.air_picture.current(
            "L-" + self._observation_key("surface", ship.id), self.sim_t)
        by_lookout = (track is not None and track.source == "LOOKOUT"
                      and lookout_id.decode(track.label)[0] >= lookout_id.IDENTIFIED)
        by_helo = (self._helo_on_task() and math.hypot(
            self.helo.x - ship.x, self.helo.y - ship.y) <= config.TASK_IDENTIFY_HELO_NM
                   and float(getattr(self.world, "visibility_nm", 10.0))
                   >= config.TASK_IDENTIFY_HELO_NM)
        if not (by_lookout or by_helo):
            return
        index = task["id"]
        suspect = detrand.u01(self.seed, "task-id-verdict", index) < config.TASK_IDENTIFY_SUSPECT
        task["verdict"] = "suspect" if suspect else "clear"
        task["progress"] = 1.0
        self._close_task(task, "done")
        if not suspect:
            self._task_notice("task.verdict.clear", task, 4.0)
            return
        hostile = [sub for sub in sorted(self.subs, key=lambda item: item.id)
                   if sub.side == "hostile" and not sub.sunk]
        if not hostile:
            self._task_notice("task.verdict.suspect_gone", task, 4.0)
            return
        sub = min(hostile, key=lambda item: (math.hypot(item.x - ship.x, item.y - ship.y),
                                              item.id))
        sigma = config.TASK_SUSPECT_SIGMA_NM
        x = sub.x + sigma * detrand.normal(self.seed, "task-id-sx", index)
        y = sub.y + sigma * detrand.normal(self.seed, "task-id-sy", index)
        self._task_notice("task.verdict.suspect", task, 6.0,
                          **self._task_position_params(x, y),
                          sigma=f"{2.0 * sigma:.0f}")

    def _civilian_by_id(self, entity_id):
        return next((ship for ship in self.civilians if ship.id == entity_id), None)

    def _progress_task_datum(self, task, dt: float) -> None:
        if self._task_expired(task):
            return
        inside = math.hypot(self.ship.x - task["x"], self.ship.y - task["y"]) <= task["radius_nm"]
        if self._helo_on_task():
            inside = inside or math.hypot(self.helo.x - task["x"],
                                          self.helo.y - task["y"]) <= task["radius_nm"]
        if inside:
            task["progress"] = min(1.0, task["progress"] + dt / config.TASK_DATUM_SEARCH_S)
            if task["progress"] >= 1.0:
                self._close_task(task, "done")

    # --- replenishment at sea ------------------------------------------------

    def ras_shortfall(self) -> dict:
        """What the supply ship still has to pass over, per store (VLS cells
        cannot be reloaded at sea)."""
        loadout = self._air_defense_loadout
        return dict(
            fuel_kg=max(0.0, self.ship.fuel_capacity_kg - self.ship.fuel_kg),
            torpedoes=max(0, self.player_torpedo_battery.capacity_total
                          - self.player_torpedo_battery.remaining_total),
            asroc=max(0, depth_charge.OWN_ASROC_STOCK - self.own_asrocs_left),
            depth_charges=max(0, depth_charge.DEPTH_CHARGE_STOCK - self.depth_charges_left),
            decoys=max(0, self.nixie_store.capacity - self.nixie_store.remaining_total),
            ciws=max(0, loadout["ciws"]["ammo"] - self.ciws_ammo),
            gun=max(0, loadout["aa_gun"]["ammo"] - self.aa_ammo))

    def ras_needed(self) -> bool:
        stores = self.ras_shortfall()
        return (stores["fuel_kg"] > config.TASK_RAS_FULL_FRACTION * self.ship.fuel_capacity_kg
                or any(value > 0 for key, value in stores.items() if key != "fuel_kg"))

    def ras_stores_line(self):
        """The stores the transfer fills, as they stand aboard now."""
        capacity = self.ship.fuel_capacity_kg
        return message(
            "radio.task.ras_stores",
            fuel=f"{self.ship.fuel_kg / capacity:.0%}" if capacity > 0.0 else "-",
            torpedoes=f"{self.player_torpedo_battery.remaining_total}"
                      f"/{self.player_torpedo_battery.capacity_total}",
            asroc=f"{self.own_asrocs_left}/{depth_charge.OWN_ASROC_STOCK}",
            charges=f"{self.depth_charges_left}/{depth_charge.DEPTH_CHARGE_STOCK}")

    def request_ras(self):
        """The radio room asks HQ for a supply ship: offered and accepted at
        once. Returns True or a refusal code."""
        board = getattr(self, "tasking", None)
        if board is None or not board.enabled or self.game_over:
            return "not_ready"
        if self.damage.station_down("radio"):
            return "radio_down"
        rows = [task for task in board.tasks if task["kind"] == "ras"]
        if any(task["state"] in tasking.OPEN_STATES for task in rows):
            return "ras_open"
        ended = [task["ended_t"] for task in rows if task["ended_t"] is not None]
        if ended and self.sim_t - max(ended) < config.TASK_RAS_REQUEST_COOLDOWN_S:
            return "ras_cooldown"
        if not self.ras_needed():
            return "ras_full"
        if self.runtime_catalog.surfaces.get(config.TASK_RAS_PROFILE) is None:
            return "ras_unavailable"
        task = self._offer_task("ras", requested=True)
        if task is None:
            return "ras_unavailable"
        return self.accept_task(task["id"])

    def _ras_request_selected(self) -> None:
        result = self.request_ras()
        if result is not True:
            self.flash(message("runtime.task." + result), 2.5)

    def _ras_transfer(self, before: float, after: float, dt: float) -> None:
        """Fuel flows while alongside; the stores come over in loads, each a
        share of what is still missing, so a breakaway keeps what came over."""
        ship = self.ship
        ship.fuel_kg = min(ship.fuel_capacity_kg,
                           ship.fuel_kg + ship.fuel_capacity_kg * dt / config.TASK_RAS_S)
        loads = config.TASK_RAS_LOADS
        done = min(loads, int(after * loads + 1e-9))
        if done <= min(loads, int(before * loads + 1e-9)):
            return
        left = loads - done + 1
        stores = self.ras_shortfall()
        share = {key: -(-value // left) for key, value in stores.items() if key != "fuel_kg"}
        self.player_torpedo_battery.restock(share["torpedoes"])
        self.torpedo_count = self.player_torpedo_battery.remaining_total
        self.own_asrocs_left += share["asroc"]
        self.depth_charges_left += share["depth_charges"]
        self.nixie_store.restock(share["decoys"])
        self.ciws_ammo += share["ciws"]
        self.aa_ammo += share["gun"]
        if any(share.values()):
            self.feed.add(self.world.format_time(), "funk", self.ras_stores_line())

    def _progress_task_ras(self, task, dt: float) -> None:
        tanker = self._civilian_by_id(task["target_id"])
        if tanker is None or tanker.sunk:
            self._close_task(task, "failed")
            return
        if self._task_expired(task):
            return
        alongside = (math.hypot(self.ship.x - tanker.x, self.ship.y - tanker.y)
                     <= config.TASK_RAS_NM
                     and abs(self.ship.speed - tanker.speed) <= config.TASK_RAS_SPEED_TOL_KN)
        if not alongside:
            return
        if task["progress"] <= 0.0:
            self._task_notice("task.ras.alongside", task, 4.0)
        before = task["progress"]
        task["progress"] = min(1.0, before + dt / config.TASK_RAS_S)
        self._ras_transfer(before, task["progress"], dt)
        if task["progress"] >= 1.0:
            self.ship.fuel_kg = self.ship.fuel_capacity_kg
            self._close_task(task, "done")

    def _progress_task_patrol(self, task, dt: float) -> None:
        """Hold the sector: own ship inside it for ``FREE_PATROL_HOLD_S``."""
        if self._task_expired(task):
            return
        if math.hypot(self.ship.x - task["x"], self.ship.y - task["y"]) <= task["radius_nm"]:
            task["progress"] = min(1.0, task["progress"] + dt / config.FREE_PATROL_HOLD_S)
            if task["progress"] >= 1.0:
                self._close_task(task, "done")

    def _progress_task_emcon(self, task, dt: float) -> None:
        radiating = self.surface_radar_on or self.air_radar_on
        if radiating and self.sim_t - task["report_t"] > config.TASK_EMCON_GRACE_S:
            self._close_task(task, "failed")
            return
        span = task["deadline_t"] - task["report_t"]
        task["progress"] = config.clamp((self.sim_t - task["report_t"]) / max(span, 1.0),
                                        0.0, 1.0)
        if self.sim_t >= task["deadline_t"]:
            self._close_task(task, "done")
