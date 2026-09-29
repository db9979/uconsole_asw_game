"""AI hunters: the frigate, its helicopter and the patrol aircraft hunt a
crewed boat when nobody plays the frigate.

With the uConsole on the boat side (``local_side == "uboot"``) or a solo
browser playing the submarine, the frigate would otherwise only react. The
hunter crews every frigate station no browser holds: it classifies what the
sonar hears against the signature library, builds a datum from its own
sensors, searches, closes, pings, sends the helicopter and the patrol
aircraft, and attacks a located boat. The OPZ marks the radar blips of a
raised mast into tracks; a mast track, an HF/DF fix and an HQ datum report
compete by age for the datum, and a mast track on a sonar bearing places the
contact. Without a position, the ESM bearing of a mast radar (an intercept
the library matches to a submarine radar, with no radar or AIS ship on its
bearing) competes with the HF/DF bearings for the search line. A located boat is passed over the datalink to friendly escorts,
whose ASROC fire on it when it lies in their range.

Observation boundary: every decision reads the frigate's own contacts, HF/DF
bearings and fixes, never the boat's position, class or identity. Stateless:
each decision derives from the simulation time, the seed and saved sensor
state (contacts, fixes, radar marks, the HQ task board), so the hunt needs no
state of its own and a loaded game continues it identically.
"""

from __future__ import annotations

import math
from functools import lru_cache

from src.core import boat_missions, config, detrand
from src.core.autocrew import AutocrewController, _nearest_threat
from src.core.station import Station

CADENCE_S = 2.0
SEARCH_KN = 10.0
TRANSIT_KN = 18.0
CLOSE_KN = 8.0
CLOSE_NM = 6.0                  # inside this a position datum is worked, not run at
NET_CLEAR_NM = 1.0              # look this far past the turning lookahead for nets
SEARCH_LEG_S = 600.0            # zigzag leg of the search
SEARCH_BOX_S = 1800.0           # the zigzag's base course turns 90° this often
CROSS_LEG_S = 300.0             # side of the crossing course for bearing motion
PING_EVERY_S = 60.0
DIP_PING_EVERY_S = 30.0
HELO_RANGE_NM = 30.0
HELO_DIP_NM = 0.5
HELO_DROP_NM = 1.5
BEARING_DATUM_NM = 8.0          # bearing-only datum: this far down the line
SHIP_FIRE_NM = 6.0
FIX_MAX_AGE_S = 900.0
PATTERN_CLEAR_NM = 4.0          # no new buoy pattern where buoys already listen
ESCORT_AHEAD_NM = 3.0           # the escort's station ahead of the convoy
ESCORT_STATION_NM = 2.5         # farther off than this it closes at transit speed
ESCORT_LEASH_NM = 8.0           # an escort prosecutes a datum this close to its convoy
RADAR_DATUM_S = 600.0           # a mast track stays a datum this long
HQ_DATUM_S = 1800.0             # an HQ datum report stays a datum this long
CORRELATE_DEG = 10.0            # a mast track this close to a sonar bearing is that contact
ASROC_EVERY_S = 120.0
ASROC_DATUM_S = 120.0           # only a datum this fresh is passed on for an ASROC
ESM_DATUM_S = 300.0             # an ESM bearing on a mast radar stays a datum this long
ESM_CANDIDATES = 3              # a submarine radar among this many library matches
SURFACE_EXPLAINS_S = 60.0       # a ship track this fresh on the bearing explains the radar
CLASSIFY_MEAN_S = 180.0         # an operator needs this long on average to call a submarine
AIR_FIX_S = 120.0               # aircraft attack only a position this fresh
HELO_READY_MEAN_S = 600.0       # a datum waits this long on average for the helicopter to launch
_SUPPORT = (("sonar", Station.SONAR), ("radio", Station.RADIO),
            ("eloka", Station.ELOKA), ("damage", Station.DAMAGE),
            ("engine", Station.ENGINE), ("opz", Station.OPZ))


def active(game) -> bool:
    """A crewed boat is in the water and no human sails the frigate."""
    if game._opfor is None or game.game_over or game.damage.ship_sunk:
        return False
    commander = getattr(game, "commander", None)
    return (getattr(game, "local_side", "frigate") == "uboot"
            or bool(getattr(commander, "solo", False)))


def manned(game, station) -> bool:
    return bool(game.commander.station_leased(station))


@lru_cache(maxsize=1)
def _sub_signatures(catalog) -> tuple:
    """Signature phrases the library knows only from submarine profiles."""
    categories = {}
    for profile in catalog.acoustic_profiles:
        text = profile.signature_text
        if text:
            categories.setdefault(text, set()).add(profile.category)
    return tuple(sorted(text for text, kinds in categories.items() if kinds == {"U_BOOT"}))


def sub_signatures(game) -> tuple:
    return _sub_signatures(game.runtime_catalog)


@lru_cache(maxsize=1)
def _sub_emitters(catalog) -> frozenset:
    """Emitter keys the library knows only from submarine profiles."""
    owners = {}
    for profile_key, systems in catalog.profile_systems.items():
        resource = catalog.profile_resources.get(profile_key)
        for emitter_key in systems.emitter_keys:
            owners.setdefault(emitter_key, set()).add(resource == "subs.json")
    return frozenset(key for key, kinds in owners.items() if kinds == {True})


def sub_emitters(game) -> frozenset:
    return _sub_emitters(game.runtime_catalog)


def _bearing(x0, y0, x1, y1) -> float:
    return math.degrees(math.atan2(x1 - x0, -(y1 - y0))) % 360.0


def _off(a, b) -> float:
    return abs(((a - b + 180.0) % 360.0) - 180.0)


def _fresh(game, contact, age_s=config.SONAR_CONTACT_LOST_S) -> bool:
    return 0.0 <= game.sim_t - contact.last_seen < age_s


def hunt_contacts(game) -> list:
    """Sonar contacts classified as a submarine, freshest fix first."""
    rows = [contact for contact in game.sonar.contacts.values()
            if _fresh(game, contact)
            and game.weapon_classification(contact) == "U_BOOT"
            and game._target_affiliation_interlock(contact) is None]
    return sorted(rows, key=lambda contact: (
        not (game._contact_range_fresh(contact) and contact.observed_x is not None),
        game.sim_t - contact.last_seen, contact.id))


def _recognised(game, contact) -> bool:
    """The operator takes ``CLASSIFY_MEAN_S`` on average to recognise the
    sound: a stateless draw per cadence tick and contact."""
    tick = int(math.floor(game.sim_t / CADENCE_S))
    return detrand.u01(game.seed, "hunter.classify", contact.id, tick) < CADENCE_S / CLASSIFY_MEAN_S


def classify(game) -> bool:
    """Classify a fresh unknown contact whose sound the library knows only
    from submarines, as an operator comparing it with the library would."""
    phrases = sub_signatures(game)
    for contact in sorted(game.sonar.contacts.values(), key=lambda item: item.id):
        if (contact.player_class is None and _fresh(game, contact, 5.0)
                and any(phrase in (contact.signature or "") for phrase in phrases)
                and _recognised(game, contact)):
            if game.classify_sonar_contact(contact, "U_BOOT") is True:
                return True
    return False


def mark_blips(game) -> int:
    """The OPZ marks every unmarked radar blip into a track, as an operator
    would; returns how many."""
    marked = 0
    for blip in list(game.radar_blip_view()):
        if game.mark_radar_blip(blip["seq"]) is True:
            marked += 1
    return marked


def mast_tracks(game) -> list:
    """Marked mast tracks (``R-`` tracks the OPZ started from a blip) with a
    measured position, freshest first."""
    rows = [track for track in game.radar_tracks()
            if str(track["track_id"]).startswith("R-") and track["x"] is not None
            and track["y"] is not None and track["age"] <= RADAR_DATUM_S]
    return sorted(rows, key=lambda track: (track["age"], track["track_id"]))


def hq_datums(game) -> list:
    """Submarine datums HQ has reported (offered or accepted tasks)."""
    rows = [task for task in game.tasking.tasks
            if task["kind"] == "datum" and task["state"] in ("offered", "active")
            and 0.0 <= game.sim_t - task["report_t"] <= HQ_DATUM_S]
    return sorted(rows, key=lambda task: (-task["report_t"], task["id"]))


def _surface_bearings(game) -> list:
    """Bearings of fresh radar and AIS ship tracks from the frigate."""
    ship = game.ship
    rows = []
    for track in game.air_picture._tracks.values():
        source = str(getattr(track, "source", ""))
        if not (source.startswith("RADAR") or "AIS" in source.upper()):
            continue
        seen = getattr(track, "last_seen", None)
        if seen is None or not 0.0 <= game.sim_t - seen <= SURFACE_EXPLAINS_S:
            continue
        if track.x is not None and track.y is not None:
            rows.append(_bearing(ship.x, ship.y, track.x, track.y))
        elif track.bearing is not None:
            rows.append(float(track.bearing))
    return rows


def esm_bearings(game) -> list:
    """ESM intercepts of a mast radar, freshest first: the library ranks a
    submarine radar among its best matches and no ship the frigate tracks
    by radar or AIS lies on the bearing. Reads the intercept only."""
    if game.damage.station_down("opz"):
        return []
    sub_keys = sub_emitters(game)
    surface = None
    rows = []
    for track in game.eloka_tracks():
        age = track.age(game.sim_t)
        if age > ESM_DATUM_S:
            continue
        analysis = game.eloka_analysis(track)
        if analysis is None or not any(
                candidate.emitter_key in sub_keys
                for candidate in analysis.candidates[:ESM_CANDIDATES]):
            continue
        if surface is None:
            surface = _surface_bearings(game)
        if any(_off(track.bearing, bearing) <= CORRELATE_DEG for bearing in surface):
            continue
        rows.append((age, track.track_key, track))
    return [track for _, _, track in sorted(rows, key=lambda row: (row[0], row[1]))]


def _on_bearing(game, track, contacts):
    """The sonar contact whose bearing runs through a mast track, or None."""
    ship = game.ship
    bearing = _bearing(ship.x, ship.y, track["x"], track["y"])
    near = [contact for contact in contacts if _off(contact.bearing, bearing) <= CORRELATE_DEG]
    return min(near, key=lambda contact: (_off(contact.bearing, bearing), contact.id),
               default=None)


def datum(game):
    """The best estimate of the boat: a position, a bearing line, or None.

    A fresh sonar fix wins; otherwise the freshest of a mast track, an HF/DF
    fix and an HQ datum report; otherwise a sonar bearing, else the freshest
    HF/DF or ESM bearing."""
    contacts = hunt_contacts(game)
    for contact in contacts:
        if game._contact_range_fresh(contact) and contact.observed_x is not None:
            return {"x": contact.observed_x, "y": contact.observed_y,
                    "contact": contact, "source": "sonar", "age": 0.0}
    positions = []
    for track in mast_tracks(game):
        positions.append((track["age"], 0, {
            "x": track["x"], "y": track["y"], "contact": _on_bearing(game, track, contacts),
            "source": "radar", "age": track["age"]}))
    for key, fix in sorted(game.hfdf_fixes.items()):
        age = game.sim_t - fix["t"]
        if 0.0 <= age <= FIX_MAX_AGE_S:
            positions.append((age, 1, {"x": fix["x"], "y": fix["y"], "contact": None,
                                       "source": "hfdf", "age": age}))
    for task in hq_datums(game):
        age = game.sim_t - task["report_t"]
        positions.append((age, 2, {"x": task["x"], "y": task["y"], "contact": None,
                                   "source": "hq", "age": age}))
    if positions:
        return min(positions, key=lambda row: (row[0], row[1]))[2]
    if contacts:
        return {"bearing": contacts[0].bearing, "contact": contacts[0], "source": "sonar"}
    bearings = [(report.age(game.sim_t), 0, report.track_id, report.bearing, "hfdf")
                for report in game.hfdf_bearings()
                if report.age(game.sim_t) <= config.RADAR_TRACK_STALE_S]
    bearings += [(track.age(game.sim_t), 1, track.track_key, track.bearing, "esm")
                 for track in esm_bearings(game)]
    if bearings:
        _, _, _, bearing, source = min(bearings)
        return {"bearing": bearing, "contact": None, "source": source}
    return None


def datum_point(game, found):
    """A position to send aircraft to: the datum, or down its bearing line."""
    if found is None:
        return None
    if "x" in found:
        x, y = found["x"], found["y"]
    else:
        rad = math.radians(found["bearing"])
        x = game.ship.x + BEARING_DATUM_NM * math.sin(rad)
        y = game.ship.y - BEARING_DATUM_NM * math.cos(rad)
    size = float(game.world.size_nm)
    return config.clamp(x, 0.0, size), config.clamp(y, 0.0, size)


def _running(game, origin: str) -> bool:
    """One weapon of a launcher at a time: look, then shoot again."""
    return any(torpedo.state == "RUN" and torpedo.launch_origin == origin
               for torpedo in game.torpedoes)


def _window(game, period: float) -> bool:
    """True once per ``period``: the cadence tick that crosses its boundary."""
    return math.floor(game.sim_t / period) != math.floor((game.sim_t - CADENCE_S) / period)


def _steer(game, course: float, speed: float) -> str:
    ship = game.ship

    def safe(heading):
        lookahead = max(0.5, max(ship.speed, speed) * (120.0 / 3600.0))
        rad = math.radians(heading)
        ahead = lookahead + NET_CLEAR_NM
        # Reported drift nets are on the chart: steer round them.
        if game.net_ahead(ship.x, ship.y, ship.x + ahead * math.sin(rad),
                          ship.y - ahead * math.cos(rad)):
            return False
        return game.world.hull_is_safe(ship.x + lookahead * math.sin(rad),
                                       ship.y - lookahead * math.cos(rad),
                                       heading, ship.hull_spec)

    heading = next((candidate for candidate in ((course + delta) % 360.0 for delta in
                                                (0.0, 30.0, -30.0, 60.0, -60.0, 90.0,
                                                 -90.0, 135.0, -135.0, 180.0))
                    if safe(candidate)), None)
    changed = False
    if heading is not None and _off(ship.target_course, heading) > 5.0:
        changed = game.order_course(heading) == "ok"
    speed = min(speed, config.SHIP_SPEED_MAX_KN)
    if abs(ship.target_speed - speed) > 0.5:
        changed = game.order_speed(speed) == "ok" or changed
    return "hunting" if changed else "monitoring"


def search_course(game) -> float:
    base = detrand.u01(game.seed, "hunter-search", 0) * 360.0
    box = math.floor(game.sim_t / SEARCH_BOX_S)
    leg = math.floor(game.sim_t / SEARCH_LEG_S)
    return (base + 90.0 * box + (45.0 if leg % 2 else -45.0)) % 360.0


def convoy_center(game):
    ships = [ship for ship in boat_missions.convoy(game) if not ship.sunk]
    if not ships:
        return None
    return (sum(ship.x for ship in ships) / len(ships),
            sum(ship.y for ship in ships) / len(ships))


def escort_course(game):
    """Course and speed that keep the frigate with the convoy it escorts
    (the merchants' own AIS positions), or None without a convoy."""
    ships = [ship for ship in boat_missions.convoy(game) if not ship.sunk]
    if not ships:
        return None
    cx, cy = convoy_center(game)
    course = ships[0].course
    rad = math.radians(course)
    # Screen ahead of the convoy, weaving across its track.
    ax, ay = cx + ESCORT_AHEAD_NM * math.sin(rad), cy - ESCORT_AHEAD_NM * math.cos(rad)
    ship = game.ship
    if math.hypot(ax - ship.x, ay - ship.y) > ESCORT_STATION_NM:
        return _bearing(ship.x, ship.y, ax, ay), TRANSIT_KN
    side = 1.0 if math.floor(game.sim_t / CROSS_LEG_S) % 2 else -1.0
    return course + side * 45.0, ships[0].speed + 2.0


def bridge(game, found) -> str:
    if _nearest_threat(game) is not None:
        return AutocrewController._bridge(game)
    ship = game.ship
    escort = escort_course(game)
    if escort is not None and found is not None:
        # An escort prosecutes near its convoy only, never chasing far off.
        point = datum_point(game, found)
        center = convoy_center(game)
        if math.hypot(point[0] - center[0], point[1] - center[1]) > ESCORT_LEASH_NM:
            found = None
    if found is None:
        if escort is not None:
            return _steer(game, *escort)
        return _steer(game, search_course(game), SEARCH_KN)
    side = 1.0 if math.floor(game.sim_t / CROSS_LEG_S) % 2 else -1.0
    if "x" in found:
        bearing = _bearing(ship.x, ship.y, found["x"], found["y"])
        if math.hypot(found["x"] - ship.x, found["y"] - ship.y) > CLOSE_NM:
            return _steer(game, bearing, TRANSIT_KN)
        return _steer(game, bearing + side * 60.0, CLOSE_KN)
    return _steer(game, found["bearing"] + side * 30.0, SEARCH_KN + 2.0)


def sonar(game) -> str:
    if game.damage.station_down("sonar"):
        return "monitoring"
    if classify(game):
        return "classified"
    contacts = hunt_contacts(game)
    if (contacts and not game._contact_range_fresh(contacts[0])
            and _fresh(game, contacts[0], 30.0) and _window(game, PING_EVERY_S)
            and game.send_active_ping() is True):
        return "ping"
    return AutocrewController._sonar(game)


def weapons(game, found) -> str:
    observed = any(warning["age_s"] <= 2.0 and warning["source"] != "flood"
                   for warning in game.torpedo_warnings(held=False))
    if observed and not game.nixies and game.nixie_store.ready > 0:
        if game.deploy_nixie_result() is True:
            return "countermeasure"
    if game.damage.station_down("weapons"):
        return "monitoring"
    contact = None if found is None else found.get("contact")
    if (contact is None or "x" not in found or contact.range_est is None
            or contact.range_est > SHIP_FIRE_NM
            or _running(game, "frigate")):
        return "monitoring"
    if game.designate_sonar_target(contact) is not True:
        return "monitoring"
    depth = config.clamp(contact.depth_est if contact.depth_est is not None
                         else game.torpedo_depth, 10.0, 300.0)
    return "engaged" if game.launch_torpedo_at(contact, float(depth)) is True else "monitoring"


def helicopter(game, found) -> str:
    helo = game.helo
    if game.damage.station_down("flightdeck") or helo.state == "VERLOREN":
        return "monitoring"
    point = datum_point(game, found)
    ship = game.ship
    if point is None or math.hypot(point[0] - ship.x, point[1] - ship.y) > HELO_RANGE_NM:
        if helo.state == "AUF":
            if helo.dip_state == "DEPLOYED":
                game.set_helicopter_dipping(False)
            elif helo.dip_state == "STOWED":
                game.return_helicopter()
            return "returning"
        return "monitoring"
    if helo.state == "HANGAR":
        tick = int(math.floor(game.sim_t / CADENCE_S))
        if detrand.u01(game.seed, "hunter.helo", tick) >= CADENCE_S / HELO_READY_MEAN_S:
            return "monitoring"                     # the deck readies the helicopter
        # The hunters fly with the search radar on (as before its switch).
        helo.radar_on = True
        return "launched" if game.launch_helicopter() is True else "monitoring"
    if helo.state != "AUF":
        return "monitoring"
    contact = found.get("contact")
    if (contact is not None and "x" in found and helo.torps > 0
            and found.get("age", 0.0) <= AIR_FIX_S and not _running(game, "helo")
            and math.hypot(helo.x - found["x"], helo.y - found["y"]) <= HELO_DROP_NM):
        depth = config.clamp(contact.depth_est if contact.depth_est is not None
                             else game.torpedo_depth, 10.0, 300.0)
        if game.launch_helicopter_torpedo_at(contact, float(depth)) is True:
            return "engaged"
    near = math.hypot(helo.x - point[0], helo.y - point[1])
    if helo.dip_state == "DEPLOYED":
        if near > 2.0 and "x" in found:            # a bearing alone: keep listening
            game.set_helicopter_dipping(False)
            return "moving"
        # On a bare bearing the dip only listens: a ping would tell the
        # boat where the helicopter hunts before anything is located.
        if ("x" in found and _window(game, DIP_PING_EVERY_S)
                and game.send_helicopter_dipping_ping() is True):
            return "ping"
        return "dipping"
    if helo.dip_state != "STOWED":
        return "monitoring"
    waypoint = (helo.waypoint_x, helo.waypoint_y)
    if (None in waypoint
            or math.hypot(waypoint[0] - point[0], waypoint[1] - point[1]) > 0.5):
        game.set_helicopter_waypoint(float(point[0]), float(point[1]))
        return "moving"
    if near <= HELO_DIP_NM and game.set_helicopter_dipping(True) is True:
        return "dipping"
    return "moving"


def mpa(game, found) -> str:
    aircraft = game.mpa
    if game.damage.station_down("opz"):
        return "monitoring"
    point = datum_point(game, found) if found is not None and "x" in found else None
    if point is None:
        return "monitoring"
    if aircraft.state == "BASE":
        if aircraft.available(game.sim_t) and game.request_mpa() is True:
            return "requested"
        return "monitoring"
    if aircraft.state not in ("TRANSIT", "STATION"):
        return "monitoring"
    if not aircraft.radar_on:
        game.set_mpa_radar(True)
    contact = found.get("contact")
    if (contact is not None and "x" in found and aircraft.torps > 0
            and found.get("age", 0.0) <= AIR_FIX_S and not _running(game, "mpa")
            and game.designate_sonar_target(contact) is True
            and game.mpa_attack() is True):
        return "engaged"
    if aircraft.pattern_queue:
        return "moving"
    waypoint = (aircraft.waypoint_x, aircraft.waypoint_y)
    if (None in waypoint
            or math.hypot(waypoint[0] - point[0], waypoint[1] - point[1]) > 1.0):
        game.set_mpa_waypoint(float(point[0]), float(point[1]))
        return "moving"
    listening = any(math.hypot(buoy.x - point[0], buoy.y - point[1]) <= PATTERN_CLEAR_NM
                    for buoy in game.buoys)
    if (not listening and aircraft.buoys_left > 0
            and math.hypot(aircraft.x - point[0], aircraft.y - point[1]) <= 3.0
            and game.set_mpa_pattern("circle") is True):
        return "buoys"
    return "moving"


def asroc(game, found) -> str:
    """Pass a fresh located datum over the datalink: the nearest friendly
    escort with an ASROC in range fires one (one weapon in the water at a time)."""
    if (found is None or "x" not in found or found["source"] == "hq"
            or found.get("age", 0.0) > ASROC_DATUM_S
            or _running(game, "asroc") or game.asrocs or not _window(game, ASROC_EVERY_S)):
        return "monitoring"
    contact = found.get("contact")
    depth = None if contact is None else contact.depth_est
    escorts = [ship for ship in game.warships
               if ship.side == "friendly" and not ship.sunk
               and ship.asroc_weapon_key() is not None and not ship.pending_asroc]
    for ship in sorted(escorts, key=lambda item: (
            math.hypot(item.x - found["x"], item.y - found["y"]), item.id)):
        if ship.fire_asroc_at(float(found["x"]), float(found["y"]), depth):
            return "asroc"
    return "monitoring"


def update(game, dt: float) -> None:
    """Run the hunt on its cadence; stations a browser holds are left alone."""
    if math.floor(game.sim_t / CADENCE_S) == math.floor((game.sim_t - dt) / CADENCE_S):
        return
    if not active(game):
        return
    for key, station in _SUPPORT:
        if key == "sonar" or game.autocrew.enabled[key] or manned(game, station):
            continue
        getattr(AutocrewController, f"_{key}")(game)
    if not manned(game, Station.SONAR):
        sonar(game)
    if not manned(game, Station.OPZ):
        mark_blips(game)
    found = datum(game)
    if not manned(game, Station.BRIDGE):
        bridge(game, found)
    if not manned(game, Station.WEAPONS):
        weapons(game, found)
        asroc(game, found)
    if not manned(game, Station.HELICOPTER):
        helicopter(game, found)
    if not manned(game, Station.OPZ):
        mpa(game, found)
