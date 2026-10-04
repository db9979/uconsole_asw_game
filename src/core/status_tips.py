"""Why a status lamp shows what it shows: hover notes for the stations.

Every lamp, traffic light or release on the stations gets a note naming the
current reason from the real game state and, where the operator can change
it, what to do (with the keys drawn as key caps).  The same notes reach the
uConsole (``console.lamp(tip=...)``) and the browser (``lamp_tips`` in the
role state).  They read only what the station itself may show: own ship,
own commanded assets, own instruments and the station's published
observations.

A note is ``{"title": message, "lines": [message, ...], "keys": [token]}``
with localizable messages; :func:`localized` words it for one language.
"""

from __future__ import annotations

import math

from src.core import config
from src.core.i18n import display_message, localize, message, raw_text

# Key tokens of both catalogs (the German texts write Umschalt/Strg).
SHIFT_A = ("Shift+A", "Umschalt+A")
CTRL_R = ("Ctrl+R", "Strg+R")


LEVELS = ("", "off", "on", "caution", "alarm")


def note(label, value, *lines, keys=(), level: str = "") -> dict:
    """A note titled ``label: value`` (``value`` may be empty); ``level``
    is the lamp's own level where a browser draws the lamp from the note."""
    label = message(label) if isinstance(label, str) else label
    value = message(value) if isinstance(value, str) and value else value
    title = message("analyzer.value", label=label, value=value) if value else label
    return {"title": title, "label": label, "value": value or "", "level": level,
            "lines": [line for line in lines if line], "keys": [str(key) for key in keys]}


def localized(tip: dict, translator=None) -> dict:
    """The note in one language: plain strings, keys kept."""
    return {"title": str(localize(tip["title"], translator))[:120],
            "label": str(localize(tip["label"], translator))[:60],
            "value": str(localize(tip["value"], translator))[:60] if tip["value"] else "",
            "level": tip["level"] if tip["level"] in LEVELS else "",
            "lines": [str(localize(line, translator))[:240] for line in tip["lines"][:8]],
            "keys": [str(key)[:16] for key in tip.get("keys", ())[:8]]}


def payload(tip: dict) -> dict:
    """The uConsole tooltip payload of a note."""
    from src.ui import layout
    return layout.tooltip_payload(tip["title"], *tip["lines"], keys=tip.get("keys", ()))


def lazy(build, name: str):
    """A function giving the uConsole payload of note ``name`` of
    ``build()``: evaluated only while the pointer is over the lamp."""
    return lambda: payload(build()[name])


def _f(value, digits: int = 0) -> str:
    return f"{float(value):.{digits}f}"


# --- Helicopter -----------------------------------------------------------------


def launch_limits(weather: dict) -> tuple[list, list]:
    """(over, near) of the launch weather: one message per limit beyond or
    within 80 % of its value (``game.helicopter_weather()`` decides)."""
    ceiling = weather["ceiling_ft"]
    rows = (
        ("weather.flight.wind", weather["wind_speed_kn"], config.HELO_LAUNCH_WIND_MAX_KN, False),
        ("weather.flight.gust", weather["gust_kn"], config.HELO_LAUNCH_GUST_MAX_KN, False),
        ("weather.flight.crosswind", weather["crosswind_kn"],
         config.HELO_LAUNCH_CROSSWIND_MAX_KN, False),
        ("weather.flight.sea", weather["sea_state"], config.HELO_LAUNCH_SEA_STATE_MAX, False),
        ("weather.flight.visibility", weather["visibility_nm"],
         config.HELO_LAUNCH_VISIBILITY_MIN_NM, True),
    ) + ((("weather.flight.ceiling", ceiling, config.HELO_CEILING_MIN_FT, True),)
         if ceiling is not None else ())
    over, near = [], []
    for key, value, limit, minimum in rows:
        digits = 1 if key in ("weather.flight.visibility",) else 0
        text = message(key, value=_f(value, digits), limit=_f(limit, digits))
        if (value < limit) if minimum else (value > limit):
            over.append(message("tip.limit.over", item=text))
        elif (limit / max(value, 1e-3) if minimum else value / limit) >= 0.8:
            near.append(message("tip.limit.near", item=text))
    if weather["icing"] == "severe":
        over.append(message("tip.helo.icing_severe"))
    return over, near


def _dip_limits(weather: dict) -> list:
    rows = (
        ("weather.flight.wind", weather["wind_speed_kn"], config.HELO_DIP_WIND_MAX_KN, False),
        ("weather.flight.sea", weather["sea_state"], config.HELO_DIP_SEA_STATE_MAX, False),
        ("weather.flight.visibility", weather["visibility_nm"],
         config.HELO_DIP_VISIBILITY_MIN_NM, True),
    )
    over = []
    for key, value, limit, minimum in rows:
        digits = 1 if key == "weather.flight.visibility" else 0
        if (value < limit) if minimum else (value > limit):
            over.append(message("tip.limit.over", item=message(
                key, value=_f(value, digits), limit=_f(limit, digits))))
    if weather["icing"] != "none":
        over.append(message("tip.helo.dip_icing"))
    return over


def _deck_lines(game, weather) -> list:
    """Why the deck window is open or shut (own ship's motion)."""
    from src.air import helicopter as helicopter_physics
    ship = game.ship
    roll, pitch = abs(float(ship.roll)), abs(float(ship.pitch))
    quiet = float(getattr(ship, "deck_quiet_s", 0.0))
    lines = []
    if roll > helicopter_physics.DECK_ROLL_LIMIT_DEG:
        lines.append(message("tip.limit.over", item=message(
            "helo.deck.roll", roll=_f(roll, 1), limit=_f(helicopter_physics.DECK_ROLL_LIMIT_DEG))))
    if pitch > helicopter_physics.DECK_PITCH_LIMIT_DEG:
        lines.append(message("tip.limit.over", item=message(
            "helo.deck.pitch", pitch=_f(pitch, 1),
            limit=_f(helicopter_physics.DECK_PITCH_LIMIT_DEG, 1))))
    if weather["deck_safe"]:
        return [message("tip.helo.deck.open", roll=_f(roll, 1), pitch=_f(pitch, 1),
                        quiet=_f(min(quiet, 999.0)))]
    if not lines:
        lines.append(message("tip.helo.deck.quiet", quiet=_f(quiet),
                             window=_f(helicopter_physics.DECK_WINDOW_S)))
    lines.append(message("tip.helo.deck.do"))
    return lines


def _launch_order_line(game, weather) -> dict | None:
    """What the launch key does now, or why it cannot launch."""
    helo = game.helo
    if helo.state == "VERLOREN":
        return message("tip.helo.lost")
    if helo.airborne:
        return message("tip.helo.airborne_recall")
    if game.damage.station_down("flightdeck"):
        return message("tip.helo.deck_down")
    if not weather["launch_safe"]:
        return message("tip.helo.launch_wait")
    return message("tip.helo.launch_go")


def helicopter(game) -> dict:
    """Notes of the helicopter station's lamps (state strip and systems)."""
    helo = game.helo
    weather = game.helicopter_weather()
    deck_down = game.damage.station_down("flightdeck")
    status = weather["status"]
    over, near = launch_limits(weather)
    launch_lines = list(over)
    if status == "no_go":
        launch_lines.append(message("tip.helo.launch.no_go_do"))
        if weather["crosswind_kn"] > config.HELO_LAUNCH_CROSSWIND_MAX_KN:
            launch_lines.append(message("tip.helo.crosswind_do"))
    else:
        launch_lines += near
        if weather["icing"] == "light":
            launch_lines.append(message(
                "tip.helo.icing_light",
                percent=_f((config.HELO_ICING_FUEL_FACTOR - 1.0) * 100.0)))
        if not near and weather["icing"] == "none":
            launch_lines.append(message("tip.helo.launch.clear"))
    launch_lines.append(_launch_order_line(game, weather))
    notes = {
        "launch": note("helo.console.launch_weather", message("weather.flight." + status),
                       *launch_lines, keys=("H", "C"),
                       level={"clear": "on", "limited": "caution"}.get(status, "alarm")),
        "deck": note("helo.console.deck_window",
                     message("helo.console.deck_open" if weather["deck_safe"]
                             else "helo.console.deck_wait"),
                     *_deck_lines(game, weather), keys=("C", "V"),
                     level="on" if weather["deck_safe"] else "caution"),
    }
    dip_over = _dip_limits(weather)
    notes["dip"] = note(
        "helo.console.dip_weather",
        message("weather.flight.dip_ok" if weather["dipping_safe"]
                else "weather.flight.dip_blocked"),
        *(dip_over + [message("tip.helo.dip_blocked_do")] if dip_over
          else [message("tip.helo.dip_ok")]),
        level="on" if weather["dipping_safe"] else "alarm")
    # Dome, ping, water entry and radar.
    if not helo.airborne:
        why_not = message("tip.helo.lost" if helo.state == "VERLOREN"
                          else "tip.helo.not_airborne")
    elif helo.state != "AUF":
        why_not = message("tip.helo.returning")
    else:
        why_not = None
    dome_value = message("enum.helo_dip." + helo.dip_state)
    if helo.dip_state == "DEPLOYED":
        dome_lines = [message("tip.helo.dome.deployed_line", depth=_f(helo.dip_depth_m)),
                      message("tip.helo.dome.raise")]
    elif helo.dip_state == "DEPLOYING":
        dome_lines = [message("tip.helo.dome.deploying_line", depth=_f(helo.dip_depth_m),
                              target=_f(helo.dip_depth_target_m))]
    elif helo.dip_state == "RETRIEVING":
        dome_lines = [message("tip.helo.dome.retrieving_line", depth=_f(helo.dip_depth_m))]
    elif why_not is not None:
        dome_lines = [why_not]
    elif not weather["dipping_safe"]:
        dome_lines = [message("tip.helo.dome.weather")]
    elif helo.dip_depth_limit(game.world) < config.HELO_DIP_DEPTH_MIN_M:
        dome_lines = [message("tip.helo.dome.shallow", minimum=_f(config.HELO_DIP_DEPTH_MIN_M))]
    else:
        dome_lines = [message("tip.helo.dome.lower", target=_f(helo.dip_depth_target_m))]
    notes["dome"] = note("helo.lamp.dome", dome_value, *dome_lines, keys=("Y",))
    if helo.dip_ping_ready:
        ping_value, ping_lines = "ui.ready", [message("tip.helo.ping.ready")]
    elif helo.dip_available:
        ping_value = "tip.value.reloading"
        ping_lines = [message("tip.helo.ping.cooldown",
                              seconds=_f(max(0.0, helo.dip_ping_cooldown)))]
    else:
        ping_value = "ui.not_ready"
        ping_lines = [why_not or message("tip.helo.ping.no_dome")]
    notes["ping"] = note("helo.lamp.ping", ping_value, *ping_lines, keys=SHIFT_A + ("Y",))
    world = game.world
    if not helo.airborne:
        water_lines = [why_not]
    elif not (0 <= helo.x <= world.size_nm and 0 <= helo.y <= world.size_nm):
        water_lines = [message("tip.helo.water.outside")]
    elif world.on_land(helo.x, helo.y):
        water_lines = [message("tip.helo.water.land")]
    else:
        depth = float(world.depth_m(helo.x, helo.y))
        water_lines = [message("tip.helo.water.ok" if depth > 5.0 else "tip.helo.water.shallow",
                               depth=_f(depth))]
    water_ok = helo.airborne and helo.water_entry_clear(world)
    notes["water"] = note("helo.lamp.water",
                          "helo.console.deck_open" if water_ok else "weather.flight.dip_blocked", *water_lines)
    radar_on = game.helo_radar_active()
    if radar_on:
        radar_lines = [message("tip.helo.radar.on")]
    elif not helo.airborne:
        radar_lines = [why_not]
    elif helo.dip_state != "STOWED":
        radar_lines = [message("tip.helo.radar.dome")]
    else:
        radar_lines = [message("tip.helo.radar.off")]
    notes["radar"] = note("helo.console.radar", "ui.on" if radar_on else "ui.off",
                          *radar_lines, keys=CTRL_R, level="on" if radar_on else "off")
    # The state strip: exactly one lamp lit.
    state = helo.state
    fuel_min = _f(max(0.0, helo.fuel_s) / 60.0)
    notes["state_hangar"] = note(
        "helo.console.state.hangar", "",
        message("tip.helo.state.hangar" if state == "HANGAR" else "tip.helo.state.out"))
    if state != "HANGAR":
        deck_lines = [message("tip.helo.state.deck_out")]
    elif deck_down:
        deck_lines = [message("tip.helo.deck_down")]
    elif weather["launch_safe"]:
        deck_lines = [message("tip.helo.launch_go")]
    else:
        deck_lines = (over if status == "no_go" else []) + (
            [] if weather["deck_safe"] else _deck_lines(game, weather)[:1])
        deck_lines.append(message("tip.helo.launch_wait"))
    notes["state_deck"] = note("helo.console.state.deck", "", *deck_lines, keys=("H", "C", "V"))
    notes["state_airborne"] = note(
        "helo.console.state.airborne", "",
        message("tip.helo.lost") if state == "VERLOREN" else
        message("tip.helo.state.flying", fuel=fuel_min) if helo.airborne else why_not)
    notes["state_dipping"] = note(
        "helo.console.state.dipping", "",
        *(dome_lines if helo.airborne else [why_not]), keys=("Y",))
    notes["state_returning"] = note(
        "helo.console.state.returning", "",
        message("tip.helo.state.returning", fuel=fuel_min) if state == "ZURUECK"
        else message("tip.helo.state.not_returning"), keys=("H",))
    return notes


# --- Weapons (frigate) --------------------------------------------------------------

_READINESS_LINES = {
    "BLOCKIERT: KEIN ZIEL": "tip.weapons.why.no_target",
    "BLOCKIERT: KEINE ENTFERNUNG": "tip.weapons.why.no_range",
    "BLOCKIERT: NICHT ALS U-BOOT/KAMPFSCHIFF KLASSIFIZIERT": "tip.weapons.why.classification",
    "BLOCKIERT: KEINE TORPEDOS": "tip.weapons.why.no_torpedoes",
    "BLOCKIERT: KEIN ROHR BEREIT": "tip.weapons.why.no_tube",
    "BLOCKIERT: SALVENLIMIT": "tip.weapons.why.salvo_limit",
    "BLOCKIERT: WAFFENZENTRALE GESTOERT": "tip.weapons.why.weapons_down",
    "BLOCKIERT: WAFFEN GESPERRT": "tip.weapons.why.weapons_tight",
    "FEUER FREI": "tip.weapons.why.clear",
}


def _readiness_line(game, readiness: str):
    if readiness.startswith("BLOCKIERT: ZUGEHOERIGKEIT"):
        return message("tip.weapons.why.affiliation")
    key = _READINESS_LINES.get(readiness)
    if key == "tip.weapons.why.salvo_limit":
        return message(key, limit=config.TORP_MAX_IN_AIR[config.TORP_DOCTRINE])
    if key == "tip.weapons.why.no_tube":
        battery = game.player_torpedo_battery
        if battery.loading_count <= 0:
            return message("tip.weapons.why.no_tube_idle")
        return message(key, seconds=_f(max(0.0, battery.next_reload_s)))
    return message(key) if key else None


def weapons(game) -> dict:
    """Notes of the weapons station's interlock chain and tube lamps."""
    contact = game.target
    readiness = game.torpedo_readiness()[0]
    fresh = contact is not None and game._contact_range_fresh(contact)
    classified = (contact is not None
                  and game.weapon_classification(contact) in ("U_BOOT", "KAMPFSCHIFF"))
    protected = readiness.startswith("BLOCKIERT: ZUGEHOERIGKEIT")
    authorized = classified and not protected
    notes = {}
    if contact is None or readiness == "BLOCKIERT: KEIN ZIEL":
        notes["target"] = note("ui.target", "ui.no_target",
                               message("tip.weapons.target.none"), keys=("M",), level="caution")
    else:
        notes["target"] = note("ui.target", "panel.assigned",
                               message("tip.weapons.target.set", contact=contact.id,
                                       age=_f(max(0.0, game.sim_t - contact.last_seen))),
                               message("tip.weapons.target.change"), keys=("M",), level="on")
    if fresh:
        seen = contact.range_seen if contact.range_seen is not None else contact.last_seen
        notes["fix"] = note("weapons.fix", "panel.valid", message(
            "tip.weapons.fix.valid", range=_f(contact.range_est, 1),
            age=_f(max(0.0, game.sim_t - seen))), level="on")
    elif contact is not None and game.roe == "FREE":
        notes["fix"] = note("weapons.fix", "weapons.manual_datum",
                            message("tip.weapons.fix.free",
                                    range=_f(config.ROE_FREE_LAUNCH_RANGE_NM)),
                            level="caution")
    else:
        notes["fix"] = note("weapons.fix", "panel.pending",
                            message("tip.weapons.fix.none" if contact is not None
                                    else "tip.weapons.target.none_short"),
                            message("tip.weapons.fix.do") if contact is not None else None,
                            keys=SHIFT_A, level="caution")
    if authorized:
        roe_lines = [message("tip.weapons.roe.ok", roe=game.roe)]
    elif contact is None:
        roe_lines = [message("tip.weapons.target.none_short")]
    elif protected:
        roe_lines = [message("tip.weapons.why.affiliation")]
    else:
        roe_lines = [message("tip.weapons.why.classification")]
    notes["roe"] = note(raw_text("ROE"), "panel.authorized" if authorized else "panel.blocked",
                        *roe_lines, level="on" if authorized else "caution")
    clear = readiness == "FEUER FREI"
    notes["weapon"] = note("weapons.weapon", "ui.ready" if clear else "panel.blocked",
                           _readiness_line(game, readiness),
                           message("tip.weapons.fire") if clear else None,
                           keys=("Ctrl+Enter", "Strg+Enter"), level="on" if clear else "caution")
    notes["flak"] = note(raw_text("FLAK"), "panel.authorized" if game.flak_authorized else "panel.blocked",
                         message("tip.weapons.flak.free" if game.flak_authorized
                                 else "tip.weapons.flak.tight"), keys=("F",),
                         level="on" if game.flak_authorized else "caution")
    battery = getattr(game, "player_torpedo_battery", None)
    for tube in getattr(battery, "tubes", ())[:8]:
        number = tube.index + 1
        if tube.loaded_weapon_key is not None:
            value, line = "weapons.lamp.loaded", message("tip.weapons.tube.loaded")
        elif tube.loading_weapon_key is not None:
            value = raw_text(f"{tube.reload_remaining_s:.0f} s")
            line = message("tip.weapons.tube.loading", seconds=_f(tube.reload_remaining_s))
        else:
            value = "weapons.lamp.empty"
            stowed = sum(item.stowed for item in battery.magazines.values())
            line = (message("tip.weapons.tube.empty", count=stowed) if stowed > 0
                    else message("tip.weapons.tube.empty_store"))
        notes[f"tube_{number}"] = note(
            message("weapons.lamp.tube", number=number), value, line,
            level="on" if tube.loaded_weapon_key is not None else
            "caution" if tube.loading_weapon_key is not None else "off")
    return notes


# --- Engine room (frigate) ----------------------------------------------------------


def _speed_cap_lines(game) -> list:
    damage = game.damage
    cap = damage.engine_speed_cap()
    loss = abs(damage.trim_deg()) * 0.5
    if damage.station_down("engine"):
        lines = [message("tip.engine.cap.down", cap=_f(cap))]
    elif damage.station_degraded("engine"):
        lines = [message("tip.engine.cap.degraded", cap=_f(cap))]
    elif cap < config.SHIP_SPEED_MAX_KN - .05:
        lines = [message("tip.engine.cap.trim", trim=_f(damage.trim_deg(), 1), loss=_f(loss, 1))]
    else:
        return [message("tip.engine.cap.none", cap=_f(config.SHIP_SPEED_MAX_KN))]
    lines.append(message("tip.engine.cap.do"))
    return lines


def _room_lines(room, name_key: str) -> list:
    lines = [message("tip.engine.room.state", room=message(name_key),
                     flood=_f(room.flood), fire=_f(room.fire))]
    if room.fire > 0 or room.flood > 0 or room.state != "OK":
        lines.append(message("tip.engine.room.do"))
    return lines


def engine(game) -> dict:
    """Notes of the engine room's propulsion and annunciator lamps."""
    ship, damage = game.ship, game.damage
    plant = getattr(ship, "plant_mode", "AUTO")
    notes = {
        "shaft": note("panel.shaft", "", message(
            "tip.engine.shaft", speed=_f(ship.speed, 1), order=_f(ship.target_speed, 1)),
            message("tip.engine.shaft_do"), keys=("↑/↓", "V")),
        "plant": note("ui.plant_mode", "", message("tip.engine.plant." + plant.lower()),
                      message("tip.engine.plant_do"), keys=("G",)),
        "quiet": note("ui.acoustic_mode", "", message(
            "tip.engine.quiet.on" if ship.quiet_mode else "tip.engine.quiet.off"), keys=("A",)),
        "cavitation": note("engine.lamp.cavitation", "", message(
            "tip.engine.cavitation.on" if ship.cavitating else "tip.engine.cavitation.off",
            speed=_f(ship.speed, 1), onset=_f(config.CAVITATION_KN)), keys=("V",)),
        "speed_cap": note("view.engine.speed_limit", "", *_speed_cap_lines(game), keys=("Enter",)),
    }
    error = abs((ship.course - ship.target_course + 180) % 360 - 180)
    notes["course"] = note("engine.course", "", message(
        "tip.engine.course.on" if error < 1 else "tip.engine.course.turning",
        course=f"{ship.course:03.0f}", target=f"{ship.target_course:03.0f}", error=_f(error)),
        message("tip.engine.course_do"), keys=("C",))
    machinery = damage.compartments.get("engine")
    if machinery is not None:
        lines = _room_lines(machinery, "engine.room.engine")
        notes["machinery"] = note("engine.lamp.machinery", "", *lines, keys=("Enter",))
        notes["flooding"] = note("engine.lamp.flooding", "", *lines, keys=("Enter",))
        notes["fire"] = note("engine.lamp.fire", "", *lines, keys=("Enter",))
    teams = damage.teams_on("engine")
    notes["repairs"] = note("engine.repairs", "", message(
        "tip.engine.repairs.on" if teams else "tip.engine.repairs.off",
        teams=", ".join(str(team) for team in teams)))
    fraction = ship.fuel_kg / ship.fuel_capacity_kg if ship.fuel_capacity_kg > 0 else 0.0
    notes["fuel"] = note("engine.fuel", "", message(
        "tip.engine.fuel.low" if fraction <= 0.25 else "tip.engine.fuel.ok",
        percent=_f(fraction * 100.0)))
    rooms = list(damage.compartments.values())
    fires = sum(1 for room in rooms if room.fire > 0)
    flooded = sum(1 for room in rooms if room.flood > 0)
    notes["fires_aboard"] = note("engine.lamp.fires_aboard", "", message(
        "tip.engine.fires" if fires else "tip.engine.no_fires", count=fires), keys=("Enter",))
    notes["flooded"] = note("engine.lamp.flooded", "", message(
        "tip.engine.flooded" if flooded else "tip.engine.no_flood", count=flooded), keys=("Enter",))
    heel = abs(damage.list_deg())
    notes["list"] = note("panel.hull_list", "", message(
        "tip.engine.list" if heel > .05 else "tip.engine.list.even", list=_f(heel, 1)))
    grounded = bool(getattr(ship, "grounded", False))
    notes["grounded"] = note("engine.lamp.grounded", "", message(
        "tip.engine.grounded.on" if grounded else "tip.engine.grounded.off"))
    sea = getattr(game.world, "effective_sea_state", game.world.sea_state)
    available = game.sonar_mode != "TOWED" or game.sonar._tow_available()
    notes["sonar"] = note("engine.lamp.sonar", "", message(
        "tip.engine.sonar" if available else "tip.engine.sonar.tas"),
        message("tip.engine.sonar.noise"))
    notes["sea"] = note("panel.sea_state", "", message(
        "tip.engine.sea.rough" if sea >= 5 else "tip.engine.sea.ok", sea=_f(sea, 1)))
    for key in ("hull_right", "hull_left"):
        room = damage.compartments.get(key)
        if room is not None:
            notes[key] = note(f"engine.room.{key}", "", *_room_lines(room, f"engine.room.{key}"),
                              keys=("Enter",))
    return notes


# --- ELOKA and sonar --------------------------------------------------------------


def eloka(game) -> dict:
    """Notes of the ELOKA lamps: ESM receiver, jammer, automatic ECM, tone."""
    jammer = game.ecm_jammer
    channels = list(getattr(jammer, "channels", ()))
    down = game.damage.station_down("opz")
    notes = {
        "esm": note("eloka.lamp.esm", "", message(
            "tip.eloka.esm.down" if down else "tip.eloka.esm.on"),
            message("tip.engine.cap.do") if down else None,
            keys=("Enter",) if down else (), level="alarm" if down else "on"),
        "jammer": note("eloka.lamp.jammer", "", message(
            "tip.eloka.jammer.on" if channels else "tip.eloka.jammer.off",
            count=len(channels), limit=jammer.MAX_CHANNELS), keys=("E", "Shift+E", "Umschalt+E"),
            level="caution" if channels else "off"),
        "auto": note("eloka.lamp.auto", "", message(
            "tip.eloka.auto.on" if jammer.auto_enabled else "tip.eloka.auto.off"), keys=("A",),
            level="on" if jammer.auto_enabled else "off"),
    }
    audio = bool(getattr(game, "eloka_audio_enabled", False))
    notes["tone"] = note("eloka.lamp.tone", "", message(
        "tip.eloka.tone.on" if audio else "tip.eloka.tone.off"), keys=("J",),
        level="on" if audio else "off")
    return notes


def sonar(game) -> dict:
    """Notes of the listening console's lamps: ping, audio, peak hold."""
    station = game.sonar
    if getattr(station, "ping_active", False):
        ping_value, ping_lines = "tip.sonar.ping.out", [message("tip.sonar.ping.active")]
    elif getattr(station, "ping_ready", True):
        ping_value, ping_lines = "ui.ready", [message("tip.sonar.ping.ready")]
    else:
        ping_value = "tip.value.reloading"
        ping_lines = [message("tip.sonar.ping.cooldown",
                              seconds=_f(getattr(station, "ping_cooldown_remaining", 0.0)))]
    ping_lines.append(message("tip.sonar.ping.betray"))
    audio = bool(getattr(game, "sonar_audio_enabled", False))
    peak = bool(getattr(station, "peak_hold", False))
    return {
        "ping": note("sonar.lamp.ping", ping_value, *ping_lines, keys=SHIFT_A),
        "audio": note("sonar.lamp.audio", "ui.on" if audio else "ui.off", message(
            "tip.sonar.audio.on" if audio else "tip.sonar.audio.off"), keys=("J",)),
        "peak": note("sonar.lamp.peak", "ui.on" if peak else "ui.off", message(
            "tip.sonar.peak.on" if peak else "tip.sonar.peak.off"),
            keys=("Space", "Leertaste")),
    }


# --- The crewed submarine -----------------------------------------------------------

COMPARTMENT_NAMES = ("bow", "control", "quarters", "battery", "engine", "stern")

FIRE_KEYS = ("Ctrl+Enter", "Strg+Enter")


def _boat_fire(sub) -> dict:
    reason = sub.fire_readiness()
    if reason is None:
        return note("uboot.panel.fire_control", "uboot.local.fire_ready",
                    message("tip.uboot.fire.ready"), keys=FIRE_KEYS, level="alarm")
    lines = [message("uboot.reason." + reason)]
    lines.append(message({
        "not_ready": "tip.uboot.fire.not_ready",
        "uboot_compartment_down": "tip.uboot.fire.room_down",
        "no_torpedoes": "tip.uboot.fire.no_torpedoes",
        "reloading": "tip.uboot.fire.reloading",
        "uboot_tube_dry": "tip.uboot.fire.dry",
        "out_of_arc": "tip.uboot.fire.arc",
    }.get(reason, "tip.uboot.fire.not_ready")))
    return note("uboot.panel.fire_control", "uboot.reason." + reason, *lines,
                keys=("M", "Shift+M", "Umschalt+M", "Enter"), level="caution")


def boat(game, crew) -> dict:
    """Notes of the crewed submarine's lamps: navigation, fire control,
    tubes, plant and the picked compartment (own boat and own chart)."""
    from src.core import boat_nav, opfor
    from src.ship.route import bearing_to
    sub, orders = crew.sub, crew.orders
    notes = {"fire": _boat_fire(sub)}
    for number, (state, left) in enumerate(opfor.tube_states(sub), start=1):
        notes[f"tube_{number}"] = note(
            message("weapons.lamp.tube", number=number),
            message(f"uboot.tube_state.{state}", seconds=_f(left or 0.0)),
            message("tip.uboot.tube." + state, seconds=_f(left or 0.0)),
            keys=("M", "Shift+M", "Umschalt+M", "Ctrl+M", "Strg+M"),
            level={"flooded": "on", "empty": "off"}.get(state, "caution"))
    # Navigation readouts.
    on_order = abs(sub.order_depth - sub.depth) < 1.0
    notes["depth"] = note("uboot.pilot.lamp.depth", "", message(
        "tip.uboot.depth.held" if on_order else "tip.uboot.depth.changing",
        depth=_f(sub.depth), order=_f(sub.order_depth)), message("tip.uboot.depth.do"),
        keys=("D",))
    bottom = sub.last_bottom_m
    sounded = bottom is not None and math.isfinite(bottom)
    notes["sounding"] = note("uboot.pilot.lamp.sounding", "", message(
        "tip.uboot.sounding" if sounded else "tip.uboot.sounding.none",
        bottom=_f(bottom or 0.0)))
    if sounded:
        keel = bottom - sub.depth
        warn = config.UBOOT_UNDER_KEEL_WARN_M
        notes["keel"] = note("uboot.pilot.lamp.keel", "", message(
            "tip.uboot.keel.low" if keel < warn else "tip.uboot.keel.tight" if keel < 2 * warn
            else "tip.uboot.keel.ok", keel=_f(keel), warn=_f(warn), double=_f(2 * warn)),
            keys=("D",))
    else:
        notes["keel"] = note("uboot.pilot.lamp.keel", "", message("tip.uboot.sounding.none"))
    obstacle = orders.obstacle_ahead_nm
    notes["ahead"] = note("uboot.pilot.lamp.ahead", "", message(
        "tip.uboot.ahead.shoal" if obstacle is not None else "tip.uboot.ahead.clear",
        range=_f(obstacle or 0.0, 1), look=_f(config.UBOOT_OBSTACLE_LOOKAHEAD_NM)),
        message("tip.uboot.ahead.do") if obstacle is not None else None, keys=("C", "D"))
    progress = boat_nav.fix_progress(crew)
    if progress > 0.0:
        position = [message("tip.uboot.position.fixing", percent=_f(progress * 100.0),
                            seconds=_f(config.UBOOT_GPS_FIX_S))]
    else:
        error = boat_nav.uncertainty_nm(crew)
        position = [message("tip.uboot.position.dr", error=_f(error, 1),
                            age=_f(orders.nav[2] / 60.0)),
                    message("tip.uboot.position.do", seconds=_f(config.UBOOT_GPS_FIX_S))]
    notes["position"] = note("uboot.pilot.lamp.position", "", *position, keys=("P",))
    route = orders.route
    if route.active:
        bx, by = boat_nav.position(crew)
        x, y = route.points[route.index]
        notes["route"] = note("uboot.pilot.lamp.route", "", message(
            "tip.uboot.route.on", number=route.index + 1, count=len(route.points),
            bearing=f"{bearing_to(bx, by, x, y):03.0f}"), message("tip.uboot.route.do"),
            keys=("W", "Backspace"))
    else:
        notes["route"] = note("uboot.pilot.lamp.route", "", message("tip.uboot.route.off"),
                              keys=("W",))
    # The plant.
    notes["silent"] = note("uboot.mode.silent", "", message(
        "tip.uboot.silent.on" if orders.silent else "tip.uboot.silent.off"), keys=("A",))
    endurance = sub.endurance
    if endurance is None:
        snorkel = [message("tip.uboot.snorkel.nuclear")]
    elif sub.snorkeling:
        snorkel = [message("tip.uboot.snorkel.on")]
    else:
        snorkel = [message("tip.uboot.snorkel.off",
                           depth=_f(endurance.profile.snorkel_depth_m))]
    if getattr(sub, "radar_hold_s", 0.0) > 0.0:
        snorkel.append(message("tip.uboot.snorkel.radar", seconds=_f(sub.radar_hold_s)))
    notes["snorkel"] = note("uboot.mode.snorkel", "", *snorkel, keys=("N", "D"))
    notes["bottom"] = note("uboot.mode.bottom", "", message(
        "tip.uboot.bottom.on" if orders.bottomed else "tip.uboot.bottom.off"),
        keys=("Shift+G", "Umschalt+G"))
    notes["cavitation"] = note("engine.lamp.cavitation", "", message(
        "tip.uboot.cavitation.on" if sub.cavitating else "tip.uboot.cavitation.off",
        speed=_f(sub.speed, 1)), keys=("V", "D"))
    notes["blow"] = note("uboot.label.blow", "", message(
        "tip.uboot.blow.ready" if sub.blow_available else "tip.uboot.blow.spent"),
        keys=("Shift+B", "Umschalt+B"))
    phase = endurance.phase if endurance is not None else None
    notes["plant"] = note(display_message("endurance_phase", phase) if phase
                          else "uboot.lamp.reactor", "", message(
        "tip.uboot.plant.reactor" if endurance is None else "tip.uboot.plant.diesel"),
        keys=("R", "N"))
    # The picked compartment (damage control).
    control = sub.damage_control
    from src.enemies.damage_control import COMPARTMENTS
    index = int(getattr(crew, "dc_selected", 0) or 0) % len(COMPARTMENTS)
    room = control.compartments[index]
    name = message(f"uboot.compartment.{COMPARTMENTS[index]}")
    send = message("tip.uboot.dc.send")
    notes["dc_water"] = note("uboot.dc.lamp.water", "", message(
        "tip.uboot.dc.water" if room.water_kg > 0 else "tip.uboot.dc.dry",
        room=name, tonnes=_f(room.water_kg / 1000.0, 1)),
        send if room.water_kg > 0 else None, keys=("Enter",))
    notes["dc_leak"] = note("uboot.dc.lamp.leak", "", message(
        "tip.uboot.dc.leak" if room.leak > 0 else "tip.uboot.dc.no_leak", room=name),
        send if room.leak > 0 else None, keys=("Enter",))
    notes["dc_fire"] = note("uboot.dc.lamp.fire", "", message(
        "tip.uboot.dc.fire" if room.fire > 0 else "tip.uboot.dc.no_fire", room=name),
        send if room.fire > 0 else None, keys=("Enter",))
    notes["dc_gas"] = note("uboot.dc.lamp.gas", "", message(
        "tip.uboot.dc.gas" if room.chlorine > 0 else "tip.uboot.dc.no_gas", room=name),
        keys=("I",))
    notes["dc_bulkhead"] = note("uboot.dc.lamp.bulkhead", "", message(
        "tip.uboot.dc.closed" if room.closed else "tip.uboot.dc.open", room=name), keys=("I",))
    power = control.power()
    notes["dc_power"] = note("uboot.dc.lamp.power", "", message(
        "tip.uboot.dc.power" if power else "tip.uboot.dc.no_power"))
    return notes


def boat_systems(game, crew) -> dict:
    """Notes of the browser's plant and damage-control lamps of the boat."""
    sub = crew.sub
    endurance, ballast, control = sub.endurance, sub.ballast, sub.damage_control
    notes = {}

    def add(name, label, key, *keys, **params):
        notes[name] = note(label, "", message(key, **params), keys=keys)

    add("motor", "uboot.lamp.reactor" if endurance is None else "commander.web.uboot_lamp_motor",
        "tip.uboot.sys.motor", "V", speed=_f(sub.speed, 1),
        maximum=_f(sub.motion.maximum_speed_kn, 1))
    if endurance is not None:
        profile = endurance.profile
        add("generator", "commander.web.uboot_lamp_generator",
            "tip.uboot.sys.generator_on" if sub.snorkeling else "tip.uboot.sys.generator_off",
            "N", kw=_f(profile.generator_power_kw))
        if profile.aip_power_kw is not None:
            add("aip", "commander.web.uboot_aip", "tip.uboot.sys.aip",
                left=_f(endurance.aip_energy_kwh), kw=_f(profile.aip_power_kw))
        balance = endurance.forecast(sub.speed, sub.motion.maximum_speed_kn)
        battery = (endurance.battery_kwh / profile.battery_capacity_kwh * 100.0
                   if profile.battery_capacity_kwh else 0.0)
        hours = endurance.submerged_hours(sub.speed, sub.motion.maximum_speed_kn)
        add("battery", "commander.web.uboot_battery",
            "tip.uboot.sys.battery_low" if battery <= 20.0 else "tip.uboot.sys.battery",
            "N", "V", percent=_f(battery), hours=_f(min(hours, 999.0), 1))
        add("charging", "commander.web.uboot_lamp_charging",
            "tip.uboot.sys.charging" if balance["net_kw"] > 0 else "tip.uboot.sys.draining",
            "R", "N", kw=_f(abs(balance["net_kw"])))
        fuel = (endurance.fuel_kwh / endurance.fuel_capacity_kwh * 100.0
                if endurance.fuel_capacity_kwh else 0.0)
        add("fuel", "commander.web.uboot_lamp_fuel", "tip.uboot.sys.fuel", percent=_f(fuel))
        air = endurance.air
        level = air.level()
        add("o2", "commander.web.uboot_o2", "tip.uboot.sys.o2_" + level, "O",
            o2=_f(air.o2_pct, 1), caution=_f(config.UBOOT_AIR_CAUTION_O2_PCT),
            danger=_f(config.UBOOT_AIR_DANGER_O2_PCT))
        add("co2", "commander.web.uboot_co2", "tip.uboot.sys.co2_" + level, "Shift+O",
            "Umschalt+O", "N", co2=_f(air.co2_pct, 2),
            caution=_f(config.UBOOT_AIR_CAUTION_CO2_PCT),
            danger=_f(config.UBOOT_AIR_DANGER_CO2_PCT))
        add("absorber", "commander.web.uboot_absorber",
            "tip.uboot.sys.absorber" if air.absorber_left > 0 else "tip.uboot.sys.absorber_spent",
            "Shift+O", "Umschalt+O", percent=_f(air.absorber_left * 100.0),
            sets=int(air.absorber_sets))
        add("candle", "commander.web.uboot_lamp_candle",
            "tip.uboot.sys.candle_on" if air.candle_left_s > 0 else "tip.uboot.sys.candle_off",
            "O", seconds=_f(air.candle_left_s), candles=int(air.candles))
    add("mbt", "commander.web.uboot_mbt", "tip.uboot.sys.mbt", "Shift+B", "Umschalt+B", "H",
        percent=_f(ballast.mbt * 100.0))
    add("blowing", "commander.web.uboot_lamp_blowing",
        "tip.uboot.sys.blowing" if ballast.blowing else "tip.uboot.sys.not_blowing")
    add("venting", "commander.web.uboot_lamp_venting",
        "tip.uboot.sys.venting" if ballast.venting else "tip.uboot.sys.vents_shut")
    add("hp_air", "commander.web.uboot_hp_air", "tip.uboot.sys.hp_air", "N",
        bar=_f(ballast.hp_air_bar), maximum=_f(config.UBOOT_HP_AIR_MAX_BAR),
        blows=int(ballast.blows_left()))
    compressor = (sub.snorkeling and sub.snorkel_rate != "vent" and control.power()
                  and ballast.hp_air_bar < config.UBOOT_HP_AIR_MAX_BAR)
    add("compressor", "commander.web.uboot_lamp_compressor",
        "tip.uboot.sys.compressor_on" if compressor else "tip.uboot.sys.compressor_off", "N")
    add("pumps", "commander.web.uboot_pumps",
        "tip.uboot.sys.pumps_on" if ballast.pumping else "tip.uboot.sys.pumps_off")
    add("trim_auto", "commander.web.uboot_trim_auto",
        "tip.uboot.sys.trim_auto_on" if ballast.auto else "tip.uboot.sys.trim_auto_off", "Z")
    trim = ballast.trim_deg(sub.flood_moment_kg())
    add("trim", "commander.web.uboot_trim_angle", "tip.uboot.sys.trim", "Z",
        trim=_f(trim, 1))
    power = control.power()
    add("power", "uboot.dc.lamp.power", "tip.uboot.dc.power" if power else "tip.uboot.dc.no_power")
    flooding = sub.flooding_kg()
    add("flooding", "uboot.dc.lamp.water",
        "tip.uboot.sys.flooding" if flooding > 0 else "tip.uboot.sys.no_flooding", "Enter",
        tonnes=_f(flooding / 1000.0, 1))
    rooms = control.compartments
    add("leak", "uboot.dc.lamp.leak", "tip.uboot.sys.rooms_leak", "Enter",
        count=sum(1 for room in rooms if room.leak > 0))
    add("fire", "uboot.dc.lamp.fire", "tip.uboot.sys.rooms_fire", "Enter",
        count=sum(1 for room in rooms if room.fire > 0))
    add("gas", "uboot.dc.lamp.gas", "tip.uboot.sys.rooms_gas", "I",
        count=sum(1 for room in rooms if room.chlorine > 0))
    add("overdepth", "commander.web.uboot_lamp_overdepth",
        "tip.uboot.sys.overdepth" if sub.depth > sub.stype.max_depth_m else "tip.uboot.sys.depth_ok",
        "D", depth=_f(sub.depth), test=_f(sub.stype.max_depth_m), crush=_f(sub.crush_depth_m))
    add("ascent", "commander.web.uboot_emergency_ascent",
        "tip.uboot.sys.ascent" if sub.emergency_ascent else "tip.uboot.sys.no_ascent",
        "Shift+B", "Umschalt+B")
    add("down", "commander.web.damage_lamp_destroyed", "tip.uboot.sys.rooms_down", "Enter",
        count=sum(1 for name in COMPARTMENT_NAMES if control.down(name)))
    add("bulkheads", "commander.web.uboot_dc_lamp_bulkheads", "tip.uboot.sys.bulkheads", "I",
        count=sum(1 for room in rooms if room.closed))
    busy = sum(1 for team in control.teams if team["task"] != "idle")
    add("teams", "commander.web.damage_lamp_teams", "tip.uboot.sys.teams", "Enter",
        busy=busy, total=len(control.teams))
    add("pumping", "commander.web.uboot_dc_lamp_bilge",
        "tip.uboot.sys.bilge_on" if control.pumping else "tip.uboot.sys.bilge_off")
    return notes


# --- Remote Crew ------------------------------------------------------------------

LAMP_TIPS_MAX = 80
_ROLE_NOTES = {
    "helicopter": helicopter,
    "weapons": weapons,
    "engine": engine,
    "eloka": eloka,
    "sonar": sonar,
    "uboot_sonar": sonar,
}


def for_role(game, role: str, translator=None, crew=None) -> dict:
    """The localized notes of one browser role's lamps (``lamp_tips``);
    a submarine command role needs its ``crew`` (the crewed boat)."""
    if crew is not None and role != "uboot_sonar":
        notes = {**boat(game, crew), **{f"sys_{name}": tip for name, tip
                                        in boat_systems(game, crew).items()}}
    else:
        build = _ROLE_NOTES.get(role)
        if build is None:
            return {}
        notes = build(game)
    return {name: localized(tip, translator)
            for name, tip in list(notes.items())[:LAMP_TIPS_MAX]}
