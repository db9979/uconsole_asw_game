"""Boat atmosphere of a conventional submarine: oxygen, carbon dioxide and
the stores that keep them breathable (fictional, deterministic, no RNG).

The crew breathes the boat's air: oxygen falls and carbon dioxide rises with
the time dived.  Absorber cartridges take CO2 out in proportion to its
concentration until the set is spent; oxygen candles each burn for a fixed
time; snorkelling (the head valve open, diesels running or only the fans)
flushes the boat back toward fresh air.  Nuclear boats make their own oxygen
and scrub continuously, so they carry no ``BoatAir``.
"""

import math

from src.core import config

AIR_LEVELS = ("ok", "caution", "danger")
STATE_FIELDS = frozenset({
    "version", "o2_pct", "co2_pct", "absorber_left", "absorber_sets",
    "candles", "candle_left_s",
})


class BoatAir:
    VERSION = 1

    def __init__(self):
        self.o2_pct = config.UBOOT_AIR_START_O2_PCT
        self.co2_pct = config.UBOOT_AIR_START_CO2_PCT
        self.absorber_left = config.UBOOT_AIR_START_ABSORBER_LEFT
        self.absorber_sets = config.UBOOT_AIR_ABSORBER_SETS
        self.candles = config.UBOOT_AIR_O2_CANDLES
        self.candle_left_s = 0.0

    # --- model -------------------------------------------------------------

    def update(self, dt: float, *, ventilating: bool, automatic: bool) -> list:
        """Advance the atmosphere by ``dt`` seconds; return new notice keys.

        ``automatic``: the AI's crew changes spent absorbers and burns a
        candle by itself; a player crew orders both.
        """
        if not math.isfinite(dt) or dt < 0.0:
            raise ValueError("air dt must be finite and non-negative")
        before = self.level()
        spent_before = self.absorber_left <= 0.0
        hours = dt / 3600.0
        self.o2_pct -= config.UBOOT_AIR_O2_USE_PCT_H * hours
        self.co2_pct += config.UBOOT_AIR_CO2_RISE_PCT_H * hours
        if self.absorber_left > 0.0:
            removal = min(self.co2_pct - config.UBOOT_AIR_FRESH_CO2_PCT,
                          config.UBOOT_AIR_ABSORBER_K_H * self.co2_pct * hours)
            removal = max(0.0, min(removal, self.absorber_left
                                   * config.UBOOT_AIR_ABSORBER_CAPACITY_PCT))
            self.co2_pct -= removal
            self.absorber_left = max(
                0.0, self.absorber_left - removal / config.UBOOT_AIR_ABSORBER_CAPACITY_PCT)
        if self.candle_left_s > 0.0:
            burn = min(dt, self.candle_left_s)
            self.o2_pct += (config.UBOOT_AIR_CANDLE_O2_PCT
                            * burn / config.UBOOT_AIR_CANDLE_BURN_S)
            self.candle_left_s = max(0.0, self.candle_left_s - dt)
        if ventilating:
            keep = math.exp(-dt / config.UBOOT_AIR_VENT_TAU_S)
            self.o2_pct = (config.UBOOT_AIR_FRESH_O2_PCT
                           + (self.o2_pct - config.UBOOT_AIR_FRESH_O2_PCT) * keep)
            self.co2_pct = (config.UBOOT_AIR_FRESH_CO2_PCT
                            + (self.co2_pct - config.UBOOT_AIR_FRESH_CO2_PCT) * keep)
        self.o2_pct = min(config.UBOOT_AIR_FRESH_O2_PCT + 2.0, max(0.0, self.o2_pct))
        self.co2_pct = min(20.0, max(config.UBOOT_AIR_FRESH_CO2_PCT, self.co2_pct))
        if automatic:
            if self.absorber_left <= 0.0 and self.absorber_sets > 0:
                self.change_absorber()
            if (self.o2_pct < config.UBOOT_AIR_AUTO_CANDLE_O2_PCT
                    and self.candle_left_s <= 0.0 and self.candles > 0):
                self.burn_candle()
        notices = []
        after = self.level()
        if AIR_LEVELS.index(after) > AIR_LEVELS.index(before):
            notices.append(f"air_{after}")
        if self.absorber_left <= 0.0 and not spent_before:
            notices.append("absorber_spent")
        return notices

    def level(self) -> str:
        """Alarm state of the air: ``ok``, ``caution`` or ``danger``."""
        if (self.co2_pct >= config.UBOOT_AIR_DANGER_CO2_PCT
                or self.o2_pct <= config.UBOOT_AIR_DANGER_O2_PCT):
            return "danger"
        if (self.co2_pct >= config.UBOOT_AIR_CAUTION_CO2_PCT
                or self.o2_pct <= config.UBOOT_AIR_CAUTION_O2_PCT):
            return "caution"
        return "ok"

    def efficiency(self) -> float:
        """Crew performance (1 fresh air, down to the floor in foul air)."""
        co2 = max(0.0, (self.co2_pct - config.UBOOT_AIR_EFFECT_CO2_PCT)
                  / config.UBOOT_AIR_EFFECT_SPAN_PCT)
        o2 = max(0.0, (config.UBOOT_AIR_EFFECT_O2_PCT - self.o2_pct)
                 / config.UBOOT_AIR_EFFECT_SPAN_PCT)
        return max(config.UBOOT_AIR_EFFICIENCY_FLOOR,
                   1.0 - 0.5 * min(1.0, co2) - 0.5 * min(1.0, o2))

    # --- crew orders -------------------------------------------------------

    def change_absorber(self):
        """Fit a fresh absorber set (the spent remainder is thrown away)."""
        if self.absorber_sets <= 0:
            return "uboot_no_absorbers"
        self.absorber_sets -= 1
        self.absorber_left = 1.0
        return True

    def burn_candle(self):
        """Light one oxygen candle (one at a time)."""
        if self.candle_left_s > 0.0:
            return "uboot_candle_burning"
        if self.candles <= 0:
            return "uboot_no_candles"
        self.candles -= 1
        self.candle_left_s = config.UBOOT_AIR_CANDLE_BURN_S
        return True

    # --- persistence -------------------------------------------------------

    def serialize(self) -> dict:
        return dict(version=self.VERSION, o2_pct=self.o2_pct, co2_pct=self.co2_pct,
                    absorber_left=self.absorber_left, absorber_sets=self.absorber_sets,
                    candles=self.candles, candle_left_s=self.candle_left_s)

    @classmethod
    def restore(cls, state) -> "BoatAir":
        if not isinstance(state, dict) or set(state) != STATE_FIELDS:
            raise ValueError("invalid air state fields")
        if type(state["version"]) is not int or state["version"] != cls.VERSION:
            raise ValueError("unsupported air state version")
        limits = dict(o2_pct=config.UBOOT_AIR_FRESH_O2_PCT + 2.0, co2_pct=20.0,
                      absorber_left=1.0, candle_left_s=config.UBOOT_AIR_CANDLE_BURN_S)
        for field, high in limits.items():
            value = state[field]
            if (type(value) not in (int, float) or not math.isfinite(value)
                    or not 0.0 <= value <= high):
                raise ValueError(f"invalid air state {field}")
        for field, high in (("absorber_sets", config.UBOOT_AIR_ABSORBER_SETS),
                            ("candles", config.UBOOT_AIR_O2_CANDLES)):
            if type(state[field]) is not int or not 0 <= state[field] <= high:
                raise ValueError(f"invalid air state {field}")
        result = cls()
        for field in ("o2_pct", "co2_pct", "absorber_left", "candle_left_s"):
            setattr(result, field, float(state[field]))
        result.absorber_sets = state["absorber_sets"]
        result.candles = state["candles"]
        return result
