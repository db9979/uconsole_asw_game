"""Ballast, trim and high-pressure air of a crewed submarine (fictional,
deterministic, no RNG).

Main ballast tanks are flooded while the boat is dived; an emergency blow
empties them with high-pressure air, and the boat floods them again (vents
open) before it can dive after a blow.  The regulating tank takes the boat's
weight changes (a torpedo leaving the tube makes it lighter, flooding
through a holed hull heavier); the trim tanks move water fore and aft
against the moment of the same loads.  With the automatic trim on, the
engineer pumps both toward a neutral boat; a crew may also order the set
points itself.  Pumping is audible.  Whatever the tanks do not take up is a
residual weight and a trim angle that push the boat off its ordered depth
unless the hydroplanes (with speed) hold it.  Floodwater in the
compartments (``damage_control.py``) counts as weight and moment the same
way.  The compressor refills the air bottles while the boat snorkels with
the diesels running; without power neither pumps nor compressor run.

The AI's boats keep their tanks trimmed without this model; only a crewed
boat carries its effects.
"""

import math

from src.core import config

STATE_FIELDS = frozenset({
    "version", "hp_air_bar", "mbt", "blowing", "venting", "auto",
    "regulating_kg", "trim_kg", "regulating_order_kg", "trim_order_kg",
    "load_kg", "load_trim_kg",
})
TANKS = ("regulating", "trim")


class BoatBallast:
    VERSION = 1

    def __init__(self):
        self.hp_air_bar = config.UBOOT_HP_AIR_START_BAR
        self.mbt = 1.0                       # main ballast flooded (dived)
        self.blowing = False
        self.venting = False
        self.auto = True
        self.regulating_kg = 0.0             # water beyond neutral (+ heavier)
        self.trim_kg = 0.0                   # moved forward (+ bow heavy)
        self.regulating_order_kg = 0.0
        self.trim_order_kg = 0.0
        self.load_kg = 0.0                   # torpedoes gone (+ heavier)
        self.load_trim_kg = 0.0              # their moment (+ bow heavy)
        self.pumping = False                 # this step (display and noise)

    # --- derived -----------------------------------------------------------

    def residual_kg(self, flooding_kg: float = 0.0) -> float:
        """Weight the tanks do not take up (+ heavy, - light); ``flooding_kg``
        is the water in the compartments (``damage_control.py``)."""
        return self.regulating_kg + self.load_kg + flooding_kg

    def trim_deg(self, flood_moment_kg: float = 0.0) -> float:
        """Trim angle from the uncompensated moment (+ bow down)."""
        moment_t = (self.trim_kg + self.load_trim_kg + flood_moment_kg) / 1000.0
        return config.clamp(moment_t * config.UBOOT_TRIM_DEG_PER_T,
                            -config.UBOOT_TRIM_MAX_DEG, config.UBOOT_TRIM_MAX_DEG)

    def vertical_drift_mps(self, flooding_kg: float, speed_kn: float,
                           flood_moment_kg: float = 0.0) -> float:
        """Depth change the tanks cause (+ down) before the planes act."""
        heavy = self.residual_kg(flooding_kg) / 1000.0 * config.UBOOT_BUOYANCY_MPS_PER_T
        angle = (config.kn_to_nm_per_s(max(speed_kn, 0.0)) * 1852.0
                 * math.sin(math.radians(self.trim_deg(flood_moment_kg))))
        return config.clamp(heavy + angle, -config.UBOOT_BUOYANCY_MAX_MPS,
                            config.UBOOT_BUOYANCY_MAX_MPS)

    def blows_left(self) -> int:
        return int(self.hp_air_bar // config.UBOOT_HP_BLOW_BAR)

    def can_blow(self) -> bool:
        return self.hp_air_bar >= config.UBOOT_HP_BLOW_BAR and not self.blowing

    def dived(self) -> bool:
        return self.mbt >= 1.0

    def neutral_targets(self, flooding_kg: float = 0.0, flood_moment_kg: float = 0.0) -> tuple:
        """Set points that make the boat neutral, within tank capacity."""
        regulating = config.clamp(-(self.load_kg + flooding_kg),
                                  -config.UBOOT_REGULATING_KG, config.UBOOT_REGULATING_KG)
        trim = config.clamp(-(self.load_trim_kg + flood_moment_kg), -config.UBOOT_TRIM_TANK_KG,
                            config.UBOOT_TRIM_TANK_KG)
        return regulating, trim

    # --- model -------------------------------------------------------------

    def update(self, dt: float, *, flooding_kg: float = 0.0, flood_moment_kg: float = 0.0,
               compressor: bool, vent_ordered: bool, power: bool = True) -> list:
        """Advance pumps, tanks and air by ``dt`` seconds; return notice keys.
        Without power the trim pumps and the compressor stand still."""
        if not math.isfinite(dt) or dt < 0.0:
            raise ValueError("ballast dt must be finite and non-negative")
        notices = []
        if self.auto:
            self.regulating_order_kg, self.trim_order_kg = self.neutral_targets(
                flooding_kg, flood_moment_kg)
        moved = 0.0
        for field, order, rate in () if not power else (
                ("regulating_kg", self.regulating_order_kg, config.UBOOT_REGULATING_PUMP_KG_S),
                ("trim_kg", self.trim_order_kg, config.UBOOT_TRIM_PUMP_KG_S)):
            value = getattr(self, field)
            gap = order - value
            if abs(gap) <= config.UBOOT_PUMP_DEADBAND_KG:
                # Close enough: stop the pump, finish the last few kilos.
                setattr(self, field, value + gap)
                continue
            step = config.clamp(gap, -rate * dt, rate * dt)
            setattr(self, field, value + step)
            moved += abs(step)
        self.pumping = moved > 0.0
        if self.blowing:
            self.mbt = max(0.0, self.mbt - dt / config.UBOOT_MBT_BLOW_S)
            if self.mbt <= 0.0:
                self.blowing = False
        elif self.mbt < 1.0 and vent_ordered:
            if not self.venting:
                self.venting = True
                notices.append("tanks_venting")
            self.mbt = min(1.0, self.mbt + dt / config.UBOOT_MBT_VENT_S)
            if self.mbt >= 1.0:
                self.venting = False
                notices.append("tanks_flooded")
        if compressor and power and self.hp_air_bar < config.UBOOT_HP_AIR_MAX_BAR:
            self.hp_air_bar = min(config.UBOOT_HP_AIR_MAX_BAR,
                                  self.hp_air_bar + config.UBOOT_HP_COMPRESSOR_BAR_S * dt)
        return notices

    def torpedo_away(self) -> None:
        """A torpedo left a bow tube: the boat is lighter and bow light."""
        self.load_kg = max(-config.UBOOT_LOAD_MAX_KG,
                           self.load_kg - config.UBOOT_TORPEDO_KG)
        self.load_trim_kg = max(-config.UBOOT_LOAD_MAX_KG,
                                self.load_trim_kg - config.UBOOT_TORPEDO_KG)

    # --- crew orders -------------------------------------------------------

    def blow(self):
        """Blow main ballast with one charge of high-pressure air."""
        if not self.can_blow():
            return "uboot_no_hp_air"
        self.hp_air_bar -= config.UBOOT_HP_BLOW_BAR
        self.blowing = True
        self.venting = False
        return True

    def set_auto(self, enabled):
        if type(enabled) is not bool:
            return "invalid_value"
        self.auto = enabled
        return True

    def step(self, tank, direction):
        """Move a tank's set point one step (+ flood / forward); manual trim."""
        if tank not in TANKS or type(direction) is not int or direction not in (-1, 1):
            return "invalid_value"
        self.auto = False
        if tank == "regulating":
            self.regulating_order_kg = config.clamp(
                self.regulating_order_kg + direction * config.UBOOT_REGULATING_STEP_KG,
                -config.UBOOT_REGULATING_KG, config.UBOOT_REGULATING_KG)
        else:
            self.trim_order_kg = config.clamp(
                self.trim_order_kg + direction * config.UBOOT_TRIM_STEP_KG,
                -config.UBOOT_TRIM_TANK_KG, config.UBOOT_TRIM_TANK_KG)
        return True

    # --- persistence -------------------------------------------------------

    def serialize(self) -> dict:
        return dict(version=self.VERSION, hp_air_bar=self.hp_air_bar, mbt=self.mbt,
                    blowing=self.blowing, venting=self.venting, auto=self.auto,
                    regulating_kg=self.regulating_kg, trim_kg=self.trim_kg,
                    regulating_order_kg=self.regulating_order_kg,
                    trim_order_kg=self.trim_order_kg, load_kg=self.load_kg,
                    load_trim_kg=self.load_trim_kg)

    @classmethod
    def restore(cls, state) -> "BoatBallast":
        if not isinstance(state, dict) or set(state) != STATE_FIELDS:
            raise ValueError("invalid ballast state fields")
        if type(state["version"]) is not int or state["version"] != cls.VERSION:
            raise ValueError("unsupported ballast state version")
        for field in ("blowing", "venting", "auto"):
            if type(state[field]) is not bool:
                raise ValueError(f"invalid ballast state {field}")
        regulating, trim = config.UBOOT_REGULATING_KG, config.UBOOT_TRIM_TANK_KG
        limits = dict(hp_air_bar=(0.0, config.UBOOT_HP_AIR_MAX_BAR), mbt=(0.0, 1.0),
                      regulating_kg=(-regulating, regulating), trim_kg=(-trim, trim),
                      regulating_order_kg=(-regulating, regulating),
                      trim_order_kg=(-trim, trim),
                      load_kg=(-config.UBOOT_LOAD_MAX_KG, 0.0),
                      load_trim_kg=(-config.UBOOT_LOAD_MAX_KG, 0.0))
        for field, (low, high) in limits.items():
            value = state[field]
            if (type(value) not in (int, float) or isinstance(value, bool)
                    or not math.isfinite(value) or not low <= value <= high):
                raise ValueError(f"invalid ballast state {field}")
        if (state["blowing"] and state["venting"]) or (
                state["venting"] and state["mbt"] >= 1.0):
            raise ValueError("inconsistent ballast tank state")
        result = cls()
        for field in limits:
            setattr(result, field, float(state[field]))
        for field in ("blowing", "venting", "auto"):
            setattr(result, field, state[field])
        return result
