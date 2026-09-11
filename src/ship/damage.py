"""Schadensmodell: Stationsräume, Flutung, Feuer und Reparaturteams."""

import math
import random

from src.core import config

COMPARTMENTS = [
    ("bridge", "Brücke"),
    ("sonar", "Sonarzentrale"),
    ("weapons", "Waffenzentrale"),
    ("opz", "OPZ / CIC"),
    ("radio", "Funk / Antennen"),
    ("engine", "Maschinerie"),
    ("flightdeck", "Flugdeck / Hangar"),
    ("hull_left", "Rumpf links"),
    ("hull_right", "Rumpf rechts"),
]

COMPARTMENT_ADJACENCY = {
    "bridge": ("sonar",),
    "sonar": ("bridge", "weapons", "opz", "hull_left", "hull_right"),
    "weapons": ("sonar", "opz", "engine", "hull_left", "hull_right"),
    "opz": ("sonar", "weapons", "radio", "hull_left", "hull_right"),
    "radio": ("opz", "flightdeck", "hull_left", "hull_right"),
    "engine": ("weapons", "flightdeck", "hull_left", "hull_right"),
    "flightdeck": ("radio", "engine", "hull_left", "hull_right"),
    "hull_left": ("sonar", "weapons", "opz", "radio", "engine", "flightdeck"),
    "hull_right": ("sonar", "weapons", "opz", "radio", "engine", "flightdeck"),
}


class Compartment:
    """Zustand: OK -> FLUTEND/BESCHAEDIGT -> ZERSTOERT."""

    def __init__(self, key: str, name: str):
        self.key = key
        self.name = name
        self.state = "OK"
        self.flood = 0.0  # 0..100 %
        self.fire = 0.0   # M14: Brand 0..100 % (>100 = Kompartiment ZERSTOERT)

    def hit(self, rng: random.Random) -> None:
        if self.state != "ZERSTOERT":
            self.state = "FLUTEND"
        self.flood = max(self.flood, rng.uniform(10.0, 30.0))
        if rng.random() < config.DMG_FIRE_START_CHANCE:
            self.fire = max(self.fire, rng.uniform(*config.DMG_FIRE_START))

    def update(self, dt: float, repaired: bool,
               repair_rate: float = config.DMG_REPAIR_RATE,
               fire_teams: int = 0) -> None:
        if self.state == "ZERSTOERT":
            return

        if self.state == "FLUTEND":
            self.flood += config.DMG_FLOOD_RATE * dt
        elif self.state == "BESCHAEDIGT":
            self.flood += config.DMG_LEAK_RATE * dt

        if repaired:
            self.flood -= repair_rate * dt
            if self.state == "FLUTEND" and self.flood <= 35.0:
                self.state = "BESCHAEDIGT"
            if self.flood <= 0.0:
                self.flood = 0.0
                self.state = "OK"

        if self.state in ("FLUTEND", "BESCHAEDIGT") \
                and self.flood >= config.DMG_DESTROY_FLOOD:
            self.state = "ZERSTOERT"
            self.flood = config.DMG_DESTROY_FLOOD

        # M14: Brand – breitet sich von selbst aus, wird von Löschteams gelöscht
        if self.fire > 0.0 and self.state != "ZERSTOERT":
            self.fire += config.DMG_FIRE_RATE * dt
            self.fire -= config.DMG_FIRE_REPAIR_RATE * fire_teams * dt
            if self.fire <= 0.0:
                self.fire = 0.0
            if self.fire >= config.DMG_FIRE_KILL and self.state != "ZERSTOERT":
                self.state = "ZERSTOERT"
                self.flood = max(self.flood, config.DMG_DESTROY_FLOOD)


class DamageModel:
    """Fregatten-Schäden + Reparaturteams (1–3)."""

    TEAM_COUNT = 3

    def __init__(self, rng: random.Random, repair_mult: float = 1.0):
        self.rng = rng
        self.repair_mult = repair_mult   # M7: Level-Faktor Reparaturrate
        self.compartments = {k: Compartment(k, n) for k, n in COMPARTMENTS}
        self.teams: dict[int, str | None] = {1: None, 2: None, 3: None}
        self.total = 0.0
        self.ship_sunk = False

    # --- Ereignisse ---

    def torpedo_hit(self, hit_zone: str | None = None) -> list[str]:
        """Ermittelt 1–2 getroffene Kompartimente.

        Eine Trefferzone verschiebt die Wahrscheinlichkeit zur passenden
        Abteilung, ersetzt aber nicht den Zufallsanteil eines Gefechtstreffers.
        Ohne Zone bleibt das bisherige Verhalten erhalten.
        """
        keys = [k for k in self.compartments]
        n = self.rng.choice((1, 2))
        preferred = {
            "bow": ["bridge", "sonar", "hull_left", "hull_right"],
            "stern": ["engine", "flightdeck", "weapons", "hull_left", "hull_right"],
            "port": ["hull_left", "engine", "weapons"],
            "starboard": ["hull_right", "engine", "weapons"],
            "center": ["weapons", "opz", "radio", "engine", "hull_left", "hull_right"],
        }.get(hit_zone, [])
        chosen = []
        if preferred and self.rng.random() < 0.70:
            chosen.append(self.rng.choice(preferred))
        remaining = [k for k in keys if k not in chosen]
        if len(chosen) < n:
            chosen.extend(self.rng.sample(remaining, n - len(chosen)))
        for k in chosen:
            self.compartments[k].hit(self.rng)
        return chosen

    def grounding_impact(self, energy_j: float, longitudinal: float,
                         lateral: float) -> dict[str, float]:
        """Apply deterministic localized flooding without consuming RNG state."""
        energy = max(0.0, float(energy_j))
        severity = min(100.0, math.sqrt(energy / 1_000_000.0) * 1.8)
        side = "hull_right" if lateral >= 0.0 else "hull_left"
        if longitudinal > 0.35:
            local = "sonar" if abs(lateral) < 0.5 else "bridge"
        elif longitudinal < -0.35:
            local = "engine" if abs(lateral) < 0.5 else "flightdeck"
        else:
            local = "weapons" if abs(lateral) < 0.5 else side
        allocations = {side: severity, local: severity * 0.55}
        applied = {}
        for key, amount in allocations.items():
            compartment = self.compartments[key]
            old = compartment.flood
            compartment.flood = min(config.DMG_DESTROY_FLOOD,
                                    compartment.flood + amount)
            if compartment.state != "ZERSTOERT" and amount > 0.0:
                compartment.state = ("ZERSTOERT"
                                     if compartment.flood >= config.DMG_DESTROY_FLOOD
                                     else "FLUTEND")
            applied[key] = compartment.flood - old
        self._recompute_totals()
        return applied

    def _recompute_totals(self) -> None:
        self.total = sum(c.flood for c in self.compartments.values())
        if self.total >= config.DMG_SHIP_SINK_TOTAL:
            self.ship_sunk = True

    # --- Steuerung ---

    def repair_candidates(self) -> list[str]:
        return [k for k, c in self.compartments.items()
                if c.state != "ZERSTOERT" and (c.state != "OK" or c.fire > 0.0)]

    def assign_team_cycle(self, team: int) -> str | None:
        """Team auf das nächste (oder weitere) betroffene Kompartiment."""
        cands = self.repair_candidates()
        if not cands:
            self.teams[team] = None
            return None
        cur = self.teams.get(team)
        if cur in cands:
            nxt = cands[(cands.index(cur) + 1) % len(cands)]
        else:
            nxt = cands[0]
        self.teams[team] = nxt
        return nxt

    def assign_team(self, team: int, destination: str) -> bool:
        """Assign explicitly without silently displacing another team."""
        if team not in self.teams or destination not in self.repair_candidates():
            return False
        self.teams[team] = destination
        return True

    def unassign_team(self, team: int) -> None:
        self.teams[team] = None

    def teams_on(self, key: str) -> list[int]:
        return [t for t, k in self.teams.items() if k == key]

    def repair_rates(self, key: str) -> tuple[float, float]:
        """Flood/fire removal per second with the current team assignment."""
        count = len(self.teams_on(key))
        factor = 0.0 if not count else 1.0 + .6 * (count - 1)
        return (config.DMG_REPAIR_RATE * self.repair_mult * factor,
                config.DMG_FIRE_REPAIR_RATE * count)

    def compartment_trend(self, key: str) -> dict:
        """Pure instantaneous net rates, excluding random spread/transitions.

        Rates are percentage points per simulation second. Destroyed rooms and
        a sunk ship cannot improve; zero-valued hazards cannot fall below zero.
        """
        c = self.compartments[key]
        repairable = not self.ship_sunk and c.state != "ZERSTOERT"
        flood_rate = fire_rate = 0.0
        if repairable:
            flood_repair, fire_repair = self.repair_rates(key)
            flood_rate = (config.DMG_FLOOD_RATE if c.state == "FLUTEND" else
                          config.DMG_LEAK_RATE if c.state == "BESCHAEDIGT" else 0.0)
            flood_rate -= flood_repair
            if c.flood <= 0.0:
                flood_rate = max(0.0, flood_rate)
            if c.fire > 0.0:
                fire_rate = config.DMG_FIRE_RATE - fire_repair
        return {"flood_rate": flood_rate, "fire_rate": fire_rate,
                "repairable": repairable}

    # --- Abfragen ---

    def station_state(self, key: str) -> str:
        return self.compartments[key].state

    def station_down(self, key: str) -> bool:
        return self.compartments[key].state == "ZERSTOERT"

    def station_degraded(self, key: str) -> bool:
        return self.compartments[key].state in ("FLUTEND", "BESCHAEDIGT") \
            or self.compartments[key].fire > 0.0

    def avg_flood(self) -> float:
        return self.total / len(self.compartments)

    def engine_speed_cap(self) -> float:
        if self.station_down("engine"):
            return 8.0
        if self.station_degraded("engine"):
            return 15.0
        return config.SHIP_SPEED_MAX_KN

    # --- Update ---

    def update(self, dt: float) -> None:
        if self.ship_sunk:
            return
        for c in self.compartments.values():
            teams = self.teams_on(c.key)
            flood_repair, _ = self.repair_rates(c.key)
            c.update(dt, bool(teams), flood_repair,
                     fire_teams=len(teams))
        # M14: Brandausbreitung in benachbarte Kompartimente
        for c in list(self.compartments.values()):
            if c.fire > 0.0 and \
                    self.rng.random() < config.DMG_FIRE_SPREAD_PPS * dt:
                neighbors = [self.compartments[key]
                             for key in COMPARTMENT_ADJACENCY[c.key]
                             if self.compartments[key].fire <= 0.0
                             and self.compartments[key].state != "ZERSTOERT"]
                if neighbors:
                    o = self.rng.choice(neighbors)
                    o.fire = self.rng.uniform(*config.DMG_FIRE_START)
        for team, key in self.teams.items():
            c = self.compartments[key] if key is not None else None
            if c is not None and c.state == "OK" and c.fire <= 0.0:
                self.teams[team] = None
        self._recompute_totals()
