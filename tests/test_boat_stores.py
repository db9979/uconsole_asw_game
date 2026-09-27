"""Stage A: the crewed boat's energy and stores (diesel, charge rate, air)."""

import sys
from pathlib import Path

import pygame
import pytest

from src.commander.projections import _uboot_plant
from src.core import config, uboot_local
from src.enemies.endurance import SubmarineEndurance
from src.enemies.life_support import BoatAir
from src.ui import layout

sys.path.insert(0, str(Path(__file__).parent))
from test_opfor_sub import _crewed  # noqa: E402
from test_uboot_scope import _key, _local_boat  # noqa: E402


def _diesel_boat():
    game, server, bridge = _crewed()
    sub = game.opfor.sub
    assert sub.endurance is not None
    return game, bridge, sub


def test_air_goes_stale_dived_and_the_stores_restore_it():
    air = BoatAir()
    air.absorber_left = 0.0
    air.absorber_sets = 0
    notices = []
    for _ in range(12):
        notices += air.update(3600.0, ventilating=False, automatic=False)
    assert air.co2_pct > config.UBOOT_AIR_DANGER_CO2_PCT
    assert air.level() == "danger" and air.efficiency() < 1.0
    assert "air_caution" in notices and "air_danger" in notices
    # A candle adds its oxygen over its burn time; only one burns at a time.
    air.candles = 2
    o2 = air.o2_pct
    assert air.burn_candle() is True and air.burn_candle() == "uboot_candle_burning"
    air.update(config.UBOOT_AIR_CANDLE_BURN_S, ventilating=False, automatic=False)
    assert air.o2_pct > o2 + 0.5 * config.UBOOT_AIR_CANDLE_O2_PCT
    # Snorkelling flushes the boat toward fresh air.
    air.update(6 * config.UBOOT_AIR_VENT_TAU_S, ventilating=True, automatic=False)
    assert air.co2_pct < 0.5 and air.level() == "ok"
    assert air.change_absorber() == "uboot_no_absorbers"


def test_a_fresh_absorber_holds_co2_down():
    fresh, spent = BoatAir(), BoatAir()
    fresh.change_absorber()
    spent.absorber_left = 0.0
    for air in (fresh, spent):
        air.update(4 * 3600.0, ventilating=False, automatic=False)
    assert fresh.co2_pct < spent.co2_pct - 1.0


def test_air_state_round_trips_and_rejects_bad_values():
    air = BoatAir()
    air.update(1800.0, ventilating=False, automatic=False)
    state = air.serialize()
    assert BoatAir.restore(state).serialize() == state
    for field, value in (("co2_pct", float("nan")), ("candles", 99), ("absorber_left", 2.0)):
        with pytest.raises(ValueError):
            BoatAir.restore(dict(state, **{field: value}))
    with pytest.raises(ValueError):
        BoatAir.restore({**state, "extra": 1})


def test_snorkelling_burns_diesel_at_the_ordered_rate():
    _game, _bridge, sub = _diesel_boat()
    profile = sub.endurance.profile
    burned = {}
    for rate in config.UBOOT_CHARGE_RATES:
        endurance = SubmarineEndurance(profile)
        endurance.manual = True
        endurance.battery_kwh = profile.battery_capacity_kwh * 0.2
        endurance.set_charge_rate(rate)
        endurance.start_snorkel(profile.snorkel_depth_m)
        fuel = endurance.fuel_kwh
        endurance.update(600.0, 0.0, 20.0, profile.snorkel_depth_m)
        burned[rate] = fuel - endurance.fuel_kwh
    assert burned["full"] > burned["half"] > 0.0 == burned["vent"]
    # Dry bunkers: snorkelling no longer charges.
    endurance = SubmarineEndurance(profile)
    endurance.manual = True
    endurance.fuel_kwh = 0.0
    endurance.battery_kwh = profile.battery_capacity_kwh * 0.2
    endurance.start_snorkel(profile.snorkel_depth_m)
    battery = endurance.battery_kwh
    endurance.update(600.0, 0.0, 20.0, profile.snorkel_depth_m)
    assert endurance.battery_kwh < battery
    state = endurance.serialize()
    assert SubmarineEndurance.restore(profile, state).serialize() == state


def test_engine_room_orders_the_stores_over_remote_crew():
    game, bridge, sub = _diesel_boat()
    apply = bridge._apply_opfor_action
    assert apply(game, "uboot_charge_rate", {"rate": "half"}, "uboot_engine") is True
    assert sub.endurance.charge_rate == "half"
    sets, candles = sub.endurance.air.absorber_sets, sub.endurance.air.candles
    assert apply(game, "uboot_absorber", {}, "uboot_engine") is True
    assert apply(game, "uboot_o2_candle", {}, "uboot_engine") is True
    assert sub.endurance.air.absorber_sets == sets - 1
    assert sub.endurance.air.candles == candles - 1
    # Only the engine room owns them.
    assert apply(game, "uboot_absorber", {}, "uboot_nav") is False
    plant = _uboot_plant(sub)
    assert plant["charge_rate"] == "half" and plant["air"]["candles"] == candles - 1
    assert plant["endurance"] and all(row["hours"] > 0 for row in plant["endurance"])


def test_uconsole_stores_page_and_keys():
    game, boat = _local_boat()
    sub = boat.sub
    if sub.endurance is None:
        pytest.skip("nuclear boat in this seed")
    uboot_local.set_local_station(game, "uboot_engine")
    boat.command_page = 1
    with layout.capture_geometry() as boxes:
        game.draw()
    titles = {row["title"] for row in boxes}
    assert {"uboot.panel.energy", "uboot.panel.endurance", "uboot.panel.air"} <= titles
    _key(game, pygame.K_r)
    assert sub.endurance.charge_rate == "half"
    candles = sub.endurance.air.candles
    _key(game, pygame.K_o)
    assert sub.endurance.air.candles == candles - 1


def test_an_ai_boat_comes_up_to_air_the_boat():
    _game, _bridge, sub = _diesel_boat()
    sub.release_manual()                     # the AI has the boat again
    sub.endurance.manual = False
    air = sub.endurance.air
    air.co2_pct = config.UBOOT_AIR_DANGER_CO2_PCT + 0.5
    air.absorber_sets = 0
    air.absorber_left = 0.0
    sub.endurance.phase = "SUBMERGED"
    sub._update_air(1.0)
    assert sub.endurance.phase == "ASCENDING"
