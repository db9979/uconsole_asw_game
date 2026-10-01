"""Theatre campaign ("Feldzug"): the front situation and its hotspots.

Pure model shared by the frigate's campaign (``src/core/campaign.py``) and
the submarine's (``src/core/boat_campaign.py``).  A theatre has

* the front situation ``lage`` (0..100, start 50),
* the enemy's strength in the sea area (``enemy``, start 6) that an enemy
  sunk lowers, and the own side's ``losses`` (start 0) that a lost or
  ignored defence mission raises,
* up to three regular hotspots and, while the situation allows it, the
  decisive hotspot.  Each hotspot is one of the side's built-in scenarios
  (played exactly as from the scenario menu) with a marker position on the
  sector map and a NATO-alphabet name.

The player picks one open hotspot per mission.  Afterwards the played
hotspot closes, the others age (a hotspot left open for ``EXPIRE_AFTER``
missions closes; an ignored defence hotspot counts as a loss) and new ones
open: which roles open depends on the situation (a weak front opens
defence missions, a strong one strikes), so results branch.  The campaign
ends by the situation (see ``OUTCOMES``), never after a fixed count, with
``MISSIONS_MAX`` as the bound for a drawn-out stalemate.

Everything here is deterministic: positions and picks come from the
stateless ``detrand`` stream keyed by the campaign's base seed and the
hotspot's serial number, and the land test reads only packaged coastline
data.
"""

from __future__ import annotations

import math

from src.core import detrand

LAGE_START, LAGE_MAX = 50, 100
ENEMY_START = 6
LOSSES_MAX = 4                    # this many losses: the front is overrun
MISSIONS_MAX = 12                 # no decision by then: stalemate
OPEN_REGULAR = 3                  # regular hotspots open at a time
EXPIRE_AFTER = 3                  # missions a hotspot waits before it closes
DECISIVE_LAGE = 75                # the decisive hotspot opens from here
EXPIRED_DEFENCE_LAGE = -4         # an ignored defence hotspot
NEXT_ID_MAX = 10_000
ROLES = ("patrol", "strike", "defence", "decisive")
# Change of the situation for a mission won / lost, by the hotspot's role.
# Winning the decisive hotspot ends the campaign with victory.
STAKES = {"patrol": (8, -8), "strike": (12, -6), "defence": (8, -12),
          "decisive": (0, -15)}
SIDES = ("frigate", "boat")
SCENARIO_ROLES = {
    "frigate": {
        "s1_patrouille": "patrol", "s13_fuehlung": "patrol",
        "s2_doppeljagd": "strike", "s12_datum": "strike",
        "s11_geleitschutz": "defence", "s14_hafenschutz": "defence",
        "s15_versorgung": "defence", "s16_seenot": "defence",
        "s3_abfang": "decisive",
    },
    "boat": {
        "s6_aufklaerung": "patrol", "s8_meerenge": "patrol",
        "s20_lauschposten": "patrol",
        "s7_geleitzug": "strike", "s9_kampfschwimmer": "strike",
        "s10_versorger": "strike",
        "s5_durchbruch": "defence", "s18_heimkehr": "defence",
        "s19_abholung": "defence",
        "s17_duell": "decisive",
    },
}
# The roles a newly opened hotspot fills, by situation band.
BAND_LOW, BAND_HIGH = 35, 65
BANDS = (("defence", "defence", "patrol"),      # lage < BAND_LOW
         ("defence", "patrol", "strike"),       # BAND_LOW <= lage < BAND_HIGH
         ("strike", "strike", "patrol"))        # lage >= BAND_HIGH
OUTCOMES = ("victory", "cleared", "supremacy",             # won
            "sunk", "defeat", "overrun", "relieved",       # lost
            "stalemate")                                   # draw
WON_OUTCOMES = ("victory", "cleared", "supremacy")
LOST_OUTCOMES = ("sunk", "defeat", "overrun", "relieved")
NAMES = ("ALFA", "BRAVO", "CHARLIE", "DELTA", "ECHO", "FOXTROT", "GOLF", "HOTEL",
         "INDIA", "JULIETT", "KILO", "LIMA", "MIKE", "NOVEMBER", "OSCAR", "PAPA",
         "QUEBEC", "ROMEO", "SIERRA", "TANGO", "UNIFORM", "VICTOR", "WHISKEY",
         "XRAY", "YANKEE", "ZULU")
MAP_NM = 500
MAP_MARGIN_NM = 50
MIN_SEPARATION_NM = 110.0
PLACE_ATTEMPTS = 32
FIELDS = frozenset({"lage", "enemy", "losses", "missions", "outcome", "next_id",
                    "hotspots"})
HOTSPOT_FIELDS = frozenset({"id", "scenario", "x", "y", "age"})


def status_of(outcome) -> str:
    """The campaign status an outcome gives (``active`` while undecided)."""
    if outcome is None:
        return "active"
    if outcome in WON_OUTCOMES:
        return "won"
    return "lost" if outcome in LOST_OUTCOMES else "draw"


def band(lage: int) -> tuple:
    return BANDS[0] if lage < BAND_LOW else BANDS[1] if lage < BAND_HIGH else BANDS[2]


# --- the land test (packaged coastline data only, bounded cache) -----------------

_LAND_CACHE: dict = {}


def _landmasses(sector_index: int) -> tuple:
    """The real sector's land and the legacy fixed chart's, for the marker
    test: a marker stands in open water on either map."""
    cached = _LAND_CACHE.get(sector_index)
    if cached is not None:
        return cached
    from src.world.coastline import Coastline, Landmass
    from src.world.real_coast import sector_for_index
    try:
        sector, _ = sector_for_index(sector_index)
        lands = [Landmass(land["name"], land["nation"], [tuple(p) for p in land["points"]])
                 for land in sector["landmasses"]]
    except (RuntimeError, ValueError):
        lands = []
    lands.extend(Coastline.load().landmasses)
    _LAND_CACHE[sector_index] = tuple(lands)     # at most 128 entries
    return _LAND_CACHE[sector_index]


def _on_land(lands, x: float, y: float) -> bool:
    return any(land.contains(x, y) for land in lands)


class Theatre:
    """The front situation and its open hotspots for one side's campaign."""

    def __init__(self, side: str, base_seed: int):
        if side not in SIDES:
            raise ValueError("unknown theatre side")
        self.side = side
        self.base_seed = int(base_seed)
        self.lage = LAGE_START
        self.enemy = ENEMY_START
        self.losses = 0
        self.missions = 0
        self.outcome: str | None = None
        self.next_id = 0
        self.hotspots: list[dict] = []
        self.refill()

    # --- reading ------------------------------------------------------------------

    @property
    def roles(self) -> dict:
        return SCENARIO_ROLES[self.side]

    def role(self, hotspot: dict) -> str:
        return self.roles[hotspot["scenario"]]

    def hotspot(self, hotspot_id) -> dict | None:
        for spot in self.hotspots:
            if spot["id"] == hotspot_id:
                return spot
        return None

    def ordered(self) -> list[dict]:
        """Open hotspots in display order (by serial number)."""
        return sorted(self.hotspots, key=lambda spot: spot["id"])

    def name(self, hotspot: dict) -> str:
        return f"{NAMES[(self.base_seed + 7 * hotspot['id']) % len(NAMES)]}-{hotspot['id'] + 1}"

    def mission_seed(self) -> int:
        """Same ``seed % 128`` (same real sector) for every mission."""
        seed = self.base_seed + 128 * self.missions
        return seed if seed < 1_000_000_000 else self.base_seed

    # --- opening hotspots -------------------------------------------------------------

    def _place(self, serial: int) -> tuple[int, int]:
        lands = _landmasses(self.base_seed % 128)
        span = MAP_NM - 2 * MAP_MARGIN_NM
        best = None
        for attempt in range(PLACE_ATTEMPTS):
            x = MAP_MARGIN_NM + int(span * detrand.u01(
                self.base_seed, "theatre-x-" + self.side, serial, attempt))
            y = MAP_MARGIN_NM + int(span * detrand.u01(
                self.base_seed, "theatre-y-" + self.side, serial, attempt))
            if _on_land(lands, x, y):
                continue
            gap = min((math.hypot(x - spot["x"], y - spot["y"]) for spot in self.hotspots),
                      default=MAP_NM)
            if gap >= MIN_SEPARATION_NM:
                return x, y
            if best is None or gap > best[0]:
                best = (gap, x, y)
        if best is not None:
            return best[1], best[2]
        return MAP_NM // 2, MAP_NM // 2

    def _open(self, scenario: str) -> None:
        serial = self.next_id
        x, y = self._place(serial)
        self.hotspots.append(dict(id=serial, scenario=scenario, x=x, y=y, age=0))
        self.next_id = min(NEXT_ID_MAX, serial + 1)

    def _pick(self, role: str, avoid: str | None) -> str | None:
        """A scenario of ``role`` that is not open yet (deterministic draw)."""
        open_keys = {spot["scenario"] for spot in self.hotspots}
        regular = [key for key, kind in self.roles.items() if kind != "decisive"]
        for pool in ([key for key in regular if self.roles[key] == role],
                     regular):
            choices = [key for key in pool if key not in open_keys and key != avoid]
            if not choices:
                choices = [key for key in pool if key not in open_keys]
            if choices:
                index = int(detrand.u01(self.base_seed, "theatre-pick-" + self.side,
                                        self.next_id) * len(choices))
                return choices[min(index, len(choices) - 1)]
        return None

    def refill(self, avoid: str | None = None) -> None:
        """Open regular hotspots up to ``OPEN_REGULAR`` (roles by the
        situation band) and the decisive one while the situation allows it."""
        if self.outcome is not None:
            return
        wanted = list(band(self.lage))
        for spot in self.hotspots:
            if self.role(spot) in wanted:
                wanted.remove(self.role(spot))
        while sum(1 for s in self.hotspots if self.role(s) != "decisive") < OPEN_REGULAR:
            role = wanted.pop(0) if wanted else "patrol"
            scenario = self._pick(role, avoid)
            if scenario is None or self.next_id >= NEXT_ID_MAX:
                break
            self._open(scenario)
        decisive = [s for s in self.hotspots if self.role(s) == "decisive"]
        if self.lage >= DECISIVE_LAGE and not decisive and self.next_id < NEXT_ID_MAX:
            self._open(next(key for key, kind in self.roles.items() if kind == "decisive"))
        elif self.lage < DECISIVE_LAGE:
            self.hotspots = [s for s in self.hotspots if self.role(s) != "decisive"]

    # --- a mission's result -------------------------------------------------------

    def resolve(self, hotspot_id: int, *, won: bool, enemy_sunk: int, sunk: bool,
                relieved: bool = False) -> bool:
        """The mission at ``hotspot_id`` ended: situation, counters,
        hotspots and perhaps the campaign's outcome.  False when no such
        hotspot is open (nothing changes)."""
        spot = self.hotspot(hotspot_id)
        if spot is None or self.outcome is not None:
            return False
        role = self.role(spot)
        self.hotspots.remove(spot)
        self.missions += 1
        self.enemy = max(0, self.enemy - max(0, min(int(enemy_sunk), ENEMY_START)))
        win_delta, loss_delta = STAKES[role]
        if won:
            self.lage += win_delta
        else:
            self.lage += loss_delta
            if role == "defence":
                self.losses += 1
        # The hotspots left waiting age; the ones waited too long close.
        kept = []
        for other in self.hotspots:
            if self.role(other) == "decisive":
                kept.append(other)
                continue
            other["age"] += 1
            if other["age"] < EXPIRE_AFTER:
                kept.append(other)
            elif self.role(other) == "defence":
                self.losses += 1
                self.lage += EXPIRED_DEFENCE_LAGE
        self.hotspots = kept
        self.lage = int(max(0, min(LAGE_MAX, self.lage)))
        self.losses = min(LOSSES_MAX, self.losses)
        self.outcome = self._decide(won and role == "decisive", sunk, relieved)
        if self.outcome is None:
            self.refill(avoid=spot["scenario"])
        else:
            self.hotspots = []
        return True

    def _decide(self, decisive_won: bool, sunk: bool, relieved: bool):
        if sunk:
            return "sunk"
        if decisive_won:
            return "victory"
        if self.enemy <= 0:
            return "cleared"
        if self.lage >= LAGE_MAX:
            return "supremacy"
        if self.lage <= 0:
            return "defeat"
        if self.losses >= LOSSES_MAX:
            return "overrun"
        if relieved:
            return "relieved"
        if self.missions >= MISSIONS_MAX:
            return "stalemate"
        return None

    # --- file ------------------------------------------------------------------

    def serialize(self) -> dict:
        return dict(lage=self.lage, enemy=self.enemy, losses=self.losses,
                    missions=self.missions, outcome=self.outcome, next_id=self.next_id,
                    hotspots=[dict(spot) for spot in self.ordered()])

    @staticmethod
    def valid_state(side: str, state) -> bool:
        if side not in SIDES or not isinstance(state, dict) or set(state) != FIELDS:
            return False

        def integer(value, low, high):
            return type(value) is int and low <= value <= high

        if not (integer(state["lage"], 0, LAGE_MAX)
                and integer(state["enemy"], 0, ENEMY_START)
                and integer(state["losses"], 0, LOSSES_MAX)
                and integer(state["missions"], 0, MISSIONS_MAX)
                and integer(state["next_id"], 0, NEXT_ID_MAX)):
            return False
        outcome = state["outcome"]
        if outcome is not None and outcome not in OUTCOMES:
            return False
        roles = SCENARIO_ROLES[side]
        spots = state["hotspots"]
        if not isinstance(spots, list) or len(spots) > OPEN_REGULAR + 1:
            return False
        ids, keys, regular, decisive = set(), set(), 0, 0
        for spot in spots:
            if not isinstance(spot, dict) or set(spot) != HOTSPOT_FIELDS:
                return False
            if not (integer(spot["id"], 0, state["next_id"] - 1)
                    and integer(spot["x"], 0, MAP_NM) and integer(spot["y"], 0, MAP_NM)
                    and integer(spot["age"], 0, EXPIRE_AFTER - 1)):
                return False
            if type(spot["scenario"]) is not str or spot["scenario"] not in roles:
                return False
            if spot["id"] in ids or spot["scenario"] in keys:
                return False
            ids.add(spot["id"])
            keys.add(spot["scenario"])
            if roles[spot["scenario"]] == "decisive":
                decisive += 1
            else:
                regular += 1
        if outcome is not None:
            return not spots
        return regular <= OPEN_REGULAR and decisive <= 1 and (
            decisive == 0 or state["lage"] >= DECISIVE_LAGE) and regular >= 1

    @classmethod
    def restore(cls, side: str, base_seed: int, state) -> "Theatre":
        if not cls.valid_state(side, state):
            raise ValueError("invalid theatre state")
        theatre = cls.__new__(cls)
        theatre.side = side
        theatre.base_seed = int(base_seed)
        for key in ("lage", "enemy", "losses", "missions", "outcome", "next_id"):
            setattr(theatre, key, state[key])
        theatre.hotspots = [dict(spot) for spot in state["hotspots"]]
        return theatre

    @classmethod
    def from_legacy(cls, side: str, base_seed: int, results: list, status: str) -> "Theatre":
        """A version-1 campaign (a fixed chain of legs) as a theatre: every
        mission won moved the situation +8 and sank one enemy, every one
        lost -8; a finished chain keeps its result (completed chain:
        victory; lost: sunk or relieved)."""
        theatre = cls(side, base_seed)
        theatre.hotspots = []
        theatre.next_id = 0
        for result in results:
            won = result == "won"
            theatre.lage += 8 if won else -8
            theatre.enemy -= 1 if won else 0
        theatre.lage = int(max(1, min(LAGE_MAX - 1, theatre.lage)))
        theatre.enemy = int(max(1, theatre.enemy))
        theatre.missions = min(len(results), MISSIONS_MAX)
        if status == "won":
            theatre.outcome = "victory"
        elif status == "lost":
            theatre.outcome = "sunk" if results and results[-1] == "sunk" else "relieved"
        else:
            theatre.refill()
        return theatre
