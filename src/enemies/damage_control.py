"""Damage control of a crewed submarine (fictional, deterministic).

Six compartments from bow to stern.  A hit holes one or two of them (leak
0..1) and may start a fire.  Water comes in through a hole with the square
root of the depth (orifice law), spills into open neighbours once a
compartment is half full, and puts out a fire it covers.  Seawater in the
battery room makes chlorine gas; a flooded or burning battery room cuts the
power (no motor, no electric pumps).  A closed bulkhead keeps water, fire and
gas in its compartment and starves a fire there.

Two damage-control teams walk the boat (transit per compartment) and seal a
leak, pump a compartment (hand pumps without power) or fight a fire; gas
halves their work.  What the teams do not stop is water in the boat: its
weight and its moment fore and aft go into the trim (``ballast.py``), and a
compartment that is flooded, burning or gassed takes its station down.

Only a crewed boat carries this model; the AI keeps its single damage value.
New random draws (where a hit lands, whether it burns) use ``detrand``.
"""

import math

from src.core import config, detrand

COMPARTMENTS = ("bow", "control", "quarters", "battery", "engine", "stern")
TASKS = ("seal", "pump", "fire", "idle")
TEAMS = 2
COMPARTMENT_FIELDS = frozenset({"water_kg", "leak", "fire", "chlorine", "closed"})
TEAM_FIELDS = frozenset({"compartment", "task", "transit_s"})
STATE_FIELDS = frozenset({"version", "compartments", "teams", "hits"})


def capacity_kg(index: int) -> float:
    return float(config.UBOOT_DC_CAPACITY_KG[index])


class _Compartment:
    __slots__ = ("water_kg", "leak", "fire", "chlorine", "closed")

    def __init__(self):
        self.water_kg = 0.0
        self.leak = 0.0          # hole size (1 = the reference hole)
        self.fire = 0.0          # intensity 0..1
        self.chlorine = 0.0      # gas concentration 0..1
        self.closed = False      # bulkheads shut


class BoatDamageControl:
    VERSION = 1

    def __init__(self):
        self.compartments = [_Compartment() for _ in COMPARTMENTS]
        self.teams = [dict(compartment="quarters", task="idle", transit_s=0.0)
                      for _ in range(TEAMS)]
        self.hits = 0                        # counter for the hit draws
        self.pumping = False                 # this step (display)
        # Crew watch performance (derived from the crew state, not saved).
        self.crew_factor = 1.0

    # --- derived -----------------------------------------------------------

    def total_water_kg(self) -> float:
        return sum(c.water_kg for c in self.compartments)

    def water_moment_kg(self) -> float:
        """Floodwater moment fore (+) and aft (-), in kg at the tank arm."""
        return sum(c.water_kg * arm for c, arm in
                   zip(self.compartments, config.UBOOT_DC_ARM))

    def power(self) -> bool:
        battery = self.compartments[COMPARTMENTS.index("battery")]
        return (battery.water_kg < config.UBOOT_DC_POWER_WATER_KG
                and battery.fire < config.UBOOT_DC_DOWN_FIRE)

    def down(self, name: str) -> bool:
        """The compartment is flooded, burning or gassed: its station is out."""
        index = COMPARTMENTS.index(name)
        c = self.compartments[index]
        return (c.water_kg >= config.UBOOT_DC_DOWN_WATER * capacity_kg(index)
                or c.fire >= config.UBOOT_DC_DOWN_FIRE
                or c.chlorine >= config.UBOOT_DC_DOWN_GAS)

    def any_damage(self) -> bool:
        return any(c.leak > 0.0 or c.fire > 0.0 or c.chlorine > 0.0 or c.water_kg > 0.0
                   for c in self.compartments)

    def teams_in(self, name: str) -> list:
        return [index for index, team in enumerate(self.teams)
                if team["compartment"] == name]

    # --- hits --------------------------------------------------------------

    def apply_hit(self, amount: float, seed: int) -> list:
        """Hole the compartment where a hit of ``amount`` % lands (a heavy
        one its neighbour too) and maybe start a fire; returns notices."""
        if not math.isfinite(amount) or amount <= 0.0:
            return []
        self.hits += 1
        index = min(len(COMPARTMENTS) - 1,
                    int(detrand.u01(seed, "dc-hit", self.hits) * len(COMPARTMENTS)))
        leak = min(1.0, amount * config.UBOOT_DC_LEAK_PER_PCT)
        struck = [(index, leak)]
        if amount >= config.UBOOT_DC_SECOND_HIT_PCT:
            side = -1 if detrand.u01(seed, "dc-side", self.hits) < 0.5 else 1
            other = index + side if 0 <= index + side < len(COMPARTMENTS) else index - side
            struck.append((other, leak * 0.5))
        notices = []
        for number, (where, size) in enumerate(struck):
            c = self.compartments[where]
            c.leak = min(1.0, c.leak + size)
            notices.append(("dc_leak", dict(compartment=COMPARTMENTS[where])))
            if detrand.u01(seed, "dc-fire", self.hits, number) < min(
                    1.0, amount / config.UBOOT_DC_FIRE_CHANCE_PCT):
                if c.fire <= 0.0:
                    notices.append(("dc_fire", dict(compartment=COMPARTMENTS[where])))
                c.fire = max(c.fire, config.UBOOT_DC_FIRE_START)
        return notices

    # --- model -------------------------------------------------------------

    def update(self, dt: float, *, depth_m: float) -> list:
        """Advance leaks, spill, fire, gas and the teams; return notices."""
        if not math.isfinite(dt) or dt < 0.0 or not math.isfinite(depth_m):
            raise ValueError("damage control inputs must be finite")
        notices = []
        was_power = self.power()
        was_gas = self.compartments[COMPARTMENTS.index("battery")].chlorine > 0.0
        before = [(c.leak > 0.0, c.fire > 0.0,
                   c.water_kg >= capacity_kg(index) * 0.999)
                  for index, c in enumerate(self.compartments)]
        head = math.sqrt(max(depth_m, 1.0) / 100.0)
        for index, c in enumerate(self.compartments):
            if c.leak > 0.0:
                c.water_kg = min(capacity_kg(index), c.water_kg
                                 + config.UBOOT_DC_LEAK_KG_S * c.leak * head * dt)
        self._spill(dt)
        self._burn(dt)
        self._gas(dt)
        self.pumping = False
        power = self.power()
        for team in self.teams:
            self._work(team, dt, power)
        for index, c in enumerate(self.compartments):
            leaking, burning, full = before[index]
            name = COMPARTMENTS[index]
            if leaking and c.leak <= 0.0:
                notices.append(("dc_leak_sealed", dict(compartment=name)))
            if burning and c.fire <= 0.0:
                notices.append(("dc_fire_out", dict(compartment=name)))
            elif not burning and c.fire > 0.0:
                notices.append(("dc_fire", dict(compartment=name)))
            if not full and c.water_kg >= capacity_kg(index) * 0.999:
                notices.append(("dc_flooded", dict(compartment=name)))
        if not was_gas and self.compartments[COMPARTMENTS.index("battery")].chlorine > 0.0:
            notices.append(("dc_chlorine", {}))
        if was_power != self.power():
            notices.append(("dc_power_restored" if self.power() else "dc_power_lost", {}))
        return notices

    def _neighbours(self, index: int):
        for other in (index - 1, index + 1):
            if 0 <= other < len(COMPARTMENTS):
                yield other

    def _spill(self, dt: float) -> None:
        """Water above half a compartment runs into open neighbours."""
        moves = [0.0] * len(COMPARTMENTS)
        for index, c in enumerate(self.compartments):
            spare = c.water_kg - config.UBOOT_DC_SPILL_FRACTION * capacity_kg(index)
            if c.closed or spare <= 0.0:
                continue
            for other in self._neighbours(index):
                target = self.compartments[other]
                if target.closed or target.water_kg >= capacity_kg(other):
                    continue
                amount = min(config.UBOOT_DC_SPILL_KG_S * dt, spare / 2.0)
                moves[index] -= amount
                moves[other] += amount
        for index, c in enumerate(self.compartments):
            c.water_kg = config.clamp(c.water_kg + moves[index], 0.0, capacity_kg(index))

    def _burn(self, dt: float) -> None:
        """Fires grow, spread to open neighbours, die under water or behind
        closed bulkheads; a team fighting one keeps it from growing."""
        spread = [0.0] * len(COMPARTMENTS)
        for index, c in enumerate(self.compartments):
            if c.fire <= 0.0:
                continue
            if c.water_kg >= config.UBOOT_DC_SPILL_FRACTION * capacity_kg(index):
                c.fire = 0.0                          # smothered by the water
                continue
            if c.closed:
                c.fire = max(0.0, c.fire - dt / config.UBOOT_DC_FIRE_STARVE_S)
                continue
            if not self._fought(index):
                c.fire = min(1.0, c.fire + dt / config.UBOOT_DC_FIRE_GROW_S)
            if c.fire >= 1.0:
                for other in self._neighbours(index):
                    if not self.compartments[other].closed:
                        spread[other] += dt / config.UBOOT_DC_FIRE_SPREAD_S
        for index, c in enumerate(self.compartments):
            if spread[index] > 0.0 and c.water_kg < (
                    config.UBOOT_DC_SPILL_FRACTION * capacity_kg(index)):
                c.fire = min(1.0, c.fire + spread[index])

    def _fought(self, index: int) -> bool:
        """A team on the spot keeps the fire from growing."""
        return any(team["compartment"] == COMPARTMENTS[index] and team["task"] == "fire"
                   and team["transit_s"] <= 0.0 for team in self.teams)

    def _gas(self, dt: float) -> None:
        """Seawater on the battery makes chlorine; it drifts through open
        bulkheads and clears slowly once the battery is dry."""
        battery_index = COMPARTMENTS.index("battery")
        battery = self.compartments[battery_index]
        if battery.water_kg >= config.UBOOT_DC_CHLORINE_WATER_KG:
            battery.chlorine = min(1.0, battery.chlorine + dt / config.UBOOT_DC_CHLORINE_RISE_S)
        drift = [0.0] * len(COMPARTMENTS)
        for index, c in enumerate(self.compartments):
            if c.chlorine >= 0.5 and not c.closed:
                for other in self._neighbours(index):
                    if not self.compartments[other].closed:
                        drift[other] += 0.5 * dt / config.UBOOT_DC_CHLORINE_RISE_S
        for index, c in enumerate(self.compartments):
            rising = index == battery_index and (
                battery.water_kg >= config.UBOOT_DC_CHLORINE_WATER_KG)
            if drift[index] > 0.0:
                c.chlorine = min(c.chlorine + drift[index],
                                 max(c.chlorine, battery.chlorine))
            elif not rising and c.chlorine > 0.0:
                c.chlorine = max(0.0, c.chlorine - dt / config.UBOOT_DC_CHLORINE_DECAY_S)

    def _work(self, team: dict, dt: float, power: bool) -> None:
        if team["transit_s"] > 0.0:
            team["transit_s"] = max(0.0, team["transit_s"] - dt)
            return
        index = COMPARTMENTS.index(team["compartment"])
        c = self.compartments[index]
        rate = config.UBOOT_DC_GAS_FACTOR if c.chlorine >= 0.5 else 1.0
        rate *= self.crew_factor
        swamped = c.water_kg >= 0.9 * capacity_kg(index)
        task = team["task"]
        if task == "seal" and not swamped:
            c.leak = max(0.0, c.leak - rate * dt / config.UBOOT_DC_SEAL_S)
        elif task == "fire" and not swamped:
            c.fire = max(0.0, c.fire - rate * dt / config.UBOOT_DC_FIRE_FIGHT_S)
        elif task == "pump" and c.water_kg > 0.0:
            pump = config.UBOOT_DC_PUMP_KG_S * (1.0 if power else config.UBOOT_DC_HAND_PUMP)
            gas = config.UBOOT_DC_GAS_FACTOR if c.chlorine >= 0.5 else 1.0
            c.water_kg = max(0.0, c.water_kg - gas * pump * dt)
            self.pumping = self.pumping or power

    # --- crew orders -------------------------------------------------------

    def order_team(self, team, compartment, task):
        """Send a team to a compartment with a task (transit per bulkhead)."""
        if (type(team) is not int or not 0 <= team < TEAMS
                or compartment not in COMPARTMENTS or task not in TASKS):
            return "invalid_value"
        row = self.teams[team]
        if row["compartment"] != compartment:
            hops = abs(COMPARTMENTS.index(row["compartment"]) - COMPARTMENTS.index(compartment))
            row["transit_s"] = hops * config.UBOOT_DC_TRANSIT_S
            row["compartment"] = compartment
        row["task"] = task
        return True

    def set_bulkhead(self, compartment, closed):
        if compartment not in COMPARTMENTS or type(closed) is not bool:
            return "invalid_value"
        self.compartments[COMPARTMENTS.index(compartment)].closed = closed
        return True

    # --- persistence -------------------------------------------------------

    def serialize(self) -> dict:
        return dict(
            version=self.VERSION, hits=self.hits,
            compartments={name: dict(water_kg=c.water_kg, leak=c.leak, fire=c.fire,
                                     chlorine=c.chlorine, closed=c.closed)
                          for name, c in zip(COMPARTMENTS, self.compartments)},
            teams=[dict(team) for team in self.teams])

    @classmethod
    def restore(cls, state) -> "BoatDamageControl":
        if not isinstance(state, dict) or set(state) != STATE_FIELDS:
            raise ValueError("invalid damage control fields")
        if type(state["version"]) is not int or state["version"] != cls.VERSION:
            raise ValueError("unsupported damage control version")
        if type(state["hits"]) is not int or not 0 <= state["hits"] <= 1_000_000:
            raise ValueError("invalid damage control hits")
        compartments, teams = state["compartments"], state["teams"]
        if not isinstance(compartments, dict) or set(compartments) != set(COMPARTMENTS):
            raise ValueError("invalid damage control compartments")
        if not isinstance(teams, list) or len(teams) != TEAMS:
            raise ValueError("invalid damage control teams")
        result = cls()
        result.hits = state["hits"]
        for index, name in enumerate(COMPARTMENTS):
            row = compartments[name]
            if not isinstance(row, dict) or set(row) != COMPARTMENT_FIELDS:
                raise ValueError("invalid compartment fields")
            if type(row["closed"]) is not bool:
                raise ValueError("invalid compartment bulkhead")
            for field, high in (("water_kg", capacity_kg(index)), ("leak", 1.0),
                                ("fire", 1.0), ("chlorine", 1.0)):
                value = row[field]
                if (type(value) not in (int, float) or isinstance(value, bool)
                        or not math.isfinite(value) or not 0.0 <= value <= high):
                    raise ValueError(f"invalid compartment {field}")
            c = result.compartments[index]
            c.water_kg, c.leak = float(row["water_kg"]), float(row["leak"])
            c.fire, c.chlorine = float(row["fire"]), float(row["chlorine"])
            c.closed = row["closed"]
        for index, row in enumerate(teams):
            if (not isinstance(row, dict) or set(row) != TEAM_FIELDS
                    or row["compartment"] not in COMPARTMENTS or row["task"] not in TASKS):
                raise ValueError("invalid team")
            transit = row["transit_s"]
            if (type(transit) not in (int, float) or isinstance(transit, bool)
                    or not math.isfinite(transit)
                    or not 0.0 <= transit <= config.UBOOT_DC_TRANSIT_S * len(COMPARTMENTS)):
                raise ValueError("invalid team transit")
            result.teams[index] = dict(compartment=row["compartment"], task=row["task"],
                                       transit_s=float(transit))
        return result
