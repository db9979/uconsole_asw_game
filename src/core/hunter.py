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
from src.core.autocrew import AutocrewController, _nearest_threat, station_key
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
PING_EVERY_S = 600.0            # a bare bearing: a ping that finds nothing only sends the boat running
DIP_PING_EVERY_S = 30.0
HELO_RANGE_NM = 30.0
HELO_GUARD_NM = 8.0             # guarding its post the helicopter stays this close
HELO_DIP_NM = 0.5
HELO_DROP_NM = 1.5
BEARING_DATUM_NM = 8.0          # bearing-only datum: this far down the line
SHIP_FIRE_NM = 6.0
GUARD_FIRE_NM = 3.0             # the frigate's own shot in the submarine's missions
RBU_FIRE_NM = 2.0               # rocket salvo only on a close, fixed boat
FIX_MAX_AGE_S = 900.0
PATTERN_CLEAR_NM = 4.0          # no new buoy pattern where buoys already listen
ESCORT_AHEAD_NM = 3.0           # the escort's station ahead of the convoy
ESCORT_STATION_NM = 2.5         # farther off than this it closes at transit speed
ESCORT_LEASH_NM = 8.0           # an escort prosecutes a datum this close to its convoy
POST_LEASH_NM = 6.0             # breakthrough: the guard prosecutes a datum this close to its post
POST_STATION_NM = 3.0           # and without one returns when this far from it
RADAR_DATUM_S = 600.0           # a mast track stays a datum this long
HQ_DATUM_S = 1800.0             # an HQ datum report stays a datum this long
CORRELATE_DEG = 10.0            # a mast track this close to a sonar bearing is that contact
ASROC_EVERY_S = 120.0
ASROC_DATUM_S = 120.0           # only a datum this fresh is passed on for an ASROC
ESM_DATUM_S = 300.0             # an ESM bearing on a mast radar stays a datum this long
ESM_STEADY_S = 600.0            # a boat's radar is up only briefly; longer is a ship
ESM_CANDIDATES = 3              # a submarine radar among this many library matches
ESM_LOG_MAX = 8                 # ESM bearing lines the hunters' ELOKA keeps (saved)
ESM_LOG_BASE_NM = 1.0           # a new line only this far from the last one's origin
ESM_LOG_FRESH_S = 30.0          # an intercept at most this old is plotted
ESM_FIX_S = 900.0               # lines this old cross into a fix
ESM_FIX_CROSS_DEG = 15.0        # two lines must cross at least this steeply
ESM_FIX_MAX_NM = 60.0           # a fix farther down either line is no fix
SURFACE_EXPLAINS_S = 60.0       # a ship track this fresh on the bearing explains the radar
CLASSIFY_MEAN_S = 180.0         # an operator needs this long on average to call a submarine
AIR_FIX_S = 120.0               # aircraft attack only a position this fresh
LEAD_HQ_S = 3600.0              # HQ's start report of the threat leads the search this long
LEAD_SONAR_S = 1200.0           # a lost submarine bearing is run down this long
LEAD_CLEAR_NM = 3.0             # within this of HQ's reported position its lead is spent
LEAD_MAX_NM = 60.0              # a bearing lead is run down no farther than this
LEAD_KN = 14.0                  # speed down a lead: fast, still listening
HELO_READY_MEAN_S = 600.0       # a datum waits this long on average for the helicopter to launch
_SUPPORT = (("sonar", Station.SONAR), ("radio", Station.RADIO),
            ("eloka", Station.ELOKA), ("damage", Station.DAMAGE),
            ("engine", Station.ENGINE), ("opz", Station.OPZ))


def active(game) -> bool:
    """A crewed boat is in the water and no human sails the frigate, or the
    crew assist lets the AI man every frigate station nobody holds."""
    if game.game_over or game.damage.ship_sunk:
        return False
    if getattr(getattr(game, "autocrew", None), "assist", False):
        return True
    if game._opfor is None:
        return False
    commander = getattr(game, "commander", None)
    return (getattr(game, "local_side", "frigate") == "uboot"
            or bool(getattr(commander, "solo", False)))


def manned(game, station) -> bool:
    """A browser holds the station, or the uConsole operator works it."""
    if game.commander.station_leased(station):
        return True
    return AutocrewController.local_holds(game, station_key(station))


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
    return (detrand.u01(game.seed, "hunter.classify", contact.id, tick)
            < CADENCE_S / (CLASSIFY_MEAN_S * _level_delay(game)))


def _level_delay(game) -> float:
    """The realism level stretches or shortens the crew's reaction times."""
    return config.LEVEL_HUNTER_DELAY.get(getattr(game, "level", config.LEVEL_DEFAULT), 1.0)


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
        if track.last_seen - track.first_seen > ESM_STEADY_S:
            continue            # radiating this long is a ship, not a mast
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


def log_esm(game) -> bool:
    """The ELOKA operator plots the freshest ESM bearing on a mast radar as a
    line from the ship's position, one per nautical mile run, so bearings
    from two places can be crossed. Returns whether a line was added."""
    log = game.hunter_esm
    log[:] = [row for row in log if 0.0 <= game.sim_t - row["t"] <= ESM_FIX_S]
    fresh = [track for track in esm_bearings(game) if track.age(game.sim_t) <= ESM_LOG_FRESH_S]
    if not fresh:
        return False
    track = fresh[0]
    if log and math.hypot(log[-1]["x"] - track.observer_x,
                          log[-1]["y"] - track.observer_y) < ESM_LOG_BASE_NM:
        return False
    log.append(dict(t=float(game.sim_t), x=float(track.observer_x),
                    y=float(track.observer_y), bearing=float(track.bearing) % 360.0))
    del log[:-ESM_LOG_MAX]
    return True


def valid_esm_log(value, save_sim_t: float) -> bool:
    """Save v39 ``hunter_esm``: at most ESM_LOG_MAX lines, oldest first, none
    after the save time, finite positions and bearings in [0, 360)."""
    if not isinstance(value, list) or len(value) > ESM_LOG_MAX:
        return False
    last = None
    for row in value:
        if (not isinstance(row, dict) or set(row) != {"t", "x", "y", "bearing"}
                or any(type(row[key]) is not float or not math.isfinite(row[key])
                       for key in row)
                or not 0.0 <= row["t"] <= save_sim_t
                or not 0.0 <= row["bearing"] < 360.0
                or abs(row["x"]) > 1e6 or abs(row["y"]) > 1e6
                or (last is not None and row["t"] < last)):
            return False
        last = row["t"]
    return True


def cross(a, b):
    """Where two bearing lines meet ahead of both origins, or None."""
    ax, ay = math.sin(math.radians(a["bearing"])), -math.cos(math.radians(a["bearing"]))
    bx, by = math.sin(math.radians(b["bearing"])), -math.cos(math.radians(b["bearing"]))
    det = ax * (-by) - ay * (-bx)
    angle = _off(a["bearing"], b["bearing"])
    if abs(det) < 1e-9 or not ESM_FIX_CROSS_DEG <= angle <= 180.0 - ESM_FIX_CROSS_DEG:
        return None
    dx, dy = b["x"] - a["x"], b["y"] - a["y"]
    ra = (dx * (-by) - dy * (-bx)) / det
    rb = (ax * dy - ay * dx) / det
    if not (0.0 < ra <= ESM_FIX_MAX_NM and 0.0 < rb <= ESM_FIX_MAX_NM):
        return None
    return a["x"] + ra * ax, a["y"] + ra * ay


def esm_fix(game):
    """The newest ESM line crossed with the newest earlier one it meets:
    (x, y, age of the newest line), or None."""
    log = [row for row in game.hunter_esm if 0.0 <= game.sim_t - row["t"] <= ESM_FIX_S]
    if len(log) < 2:
        return None
    newest = log[-1]
    for earlier in reversed(log[:-1]):
        point = cross(earlier, newest)
        if point is not None:
            return point[0], point[1], game.sim_t - newest["t"]
    return None


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
    fix = esm_fix(game)
    if fix is not None:
        positions.append((fix[2], 3, {"x": fix[0], "y": fix[1], "contact": None,
                                      "source": "esm", "age": fix[2]}))
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
    line = (game.hunter_lead or {}).get("sonar")
    point = None if line is None else _sonar_point(game, line)
    if point is None:
        point = lead_point(game)
    if point is not None:
        return {"x": point[0], "y": point[1], "contact": None, "source": "lead", "age": 0.0}
    return None


def set_hq_lead(game, bearing: float, range_nm: float) -> None:
    """HQ's start report of the nearest threat (rounded bearing and range
    from the ship, as the teletype prints it) marks the area to search.
    In the submarine's missions the frigate guards its own post instead."""
    if boat_missions.mode(game) is not None:
        return
    game.hunter_lead = dict(game.hunter_lead or {"hq": None, "sonar": None})
    game.hunter_lead["hq"] = _line(game.sim_t, game.ship.x, game.ship.y, bearing, range_nm)


def _line(t, x, y, bearing, range_nm):
    return dict(t=float(t), x=float(x), y=float(y), bearing=float(bearing) % 360.0,
                range=None if range_nm is None else float(range_nm))


def note_lead(game) -> None:
    """Keep the leads current: a fresh submarine bearing becomes the sonar
    lead (the line from where it was heard); stale leads are dropped."""
    lead = dict(game.hunter_lead or {"hq": None, "sonar": None})
    for contact in hunt_contacts(game):
        if _fresh(game, contact, 5.0):
            lead["sonar"] = _line(game.sim_t, contact.observer_x, contact.observer_y,
                                  contact.bearing, None)
            break
    if lead["sonar"] is not None and _sonar_point(game, lead["sonar"]) is None:
        lead["sonar"] = None
    centre = hq_area(game)
    if lead["hq"] is not None and (centre is None or math.hypot(
            centre[0] - game.ship.x, centre[1] - game.ship.y) <= LEAD_CLEAR_NM):
        lead["hq"] = None
    game.hunter_lead = None if lead == {"hq": None, "sonar": None} else lead


def _sonar_point(game, line):
    """A point ``BEARING_DATUM_NM`` down a lost bearing past the ship, or
    None once the line is stale or the ship has run it out."""
    if not 0.0 <= game.sim_t - line["t"] <= LEAD_SONAR_S:
        return None
    rad = math.radians(line["bearing"])
    ux, uy = math.sin(rad), -math.cos(rad)
    ship = game.ship
    along = max(0.0, (ship.x - line["x"]) * ux + (ship.y - line["y"]) * uy) + BEARING_DATUM_NM
    if along > LEAD_MAX_NM:
        return None
    return line["x"] + along * ux, line["y"] + along * uy


def hq_area(game):
    """The position HQ reported the threat at, or None."""
    line = (game.hunter_lead or {}).get("hq")
    if line is None or not 0.0 <= game.sim_t - line["t"] <= LEAD_HQ_S:
        return None
    rad = math.radians(line["bearing"])
    return (line["x"] + line["range"] * math.sin(rad),
            line["y"] - line["range"] * math.cos(rad))


def lead_point(game):
    """HQ's reported position of the threat, or None without one or once
    the ship has been there."""
    return hq_area(game)


def valid_lead(value, save_sim_t: float) -> bool:
    """Save ``hunter_lead``: None, or the HQ and sonar leads, each None or a
    line of finite floats (range None for a sonar bearing, set for HQ's)
    taken no later than the save."""
    if value is None:
        return True
    if not isinstance(value, dict) or set(value) != {"hq", "sonar"} or value == {
            "hq": None, "sonar": None}:
        return False
    for key, line in value.items():
        if line is None:
            continue
        if not isinstance(line, dict) or set(line) != {"t", "x", "y", "bearing", "range"}:
            return False
        if (line["range"] is None) != (key == "sonar"):
            return False
        numbers = [line[name] for name in ("t", "x", "y", "bearing")]
        if line["range"] is not None:
            numbers.append(line["range"])
        if not (all(type(item) is float and math.isfinite(item) for item in numbers)
                and 0.0 <= line["t"] <= save_sim_t and 0.0 <= line["bearing"] < 360.0
                and abs(line["x"]) <= 1e6 and abs(line["y"]) <= 1e6
                and (line["range"] is None or 0.0 <= line["range"] <= 1e4)):
            return False
    return True


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


def guard_post(game):
    """The breakthrough guard's post (the frigate's scenario start), or None."""
    if boat_missions.mode(game) != "breakthrough":
        return None
    start = config.SCENARIOS.get(game.scenario_key, {}).get("ship_start")
    return None if start is None else (float(start[0]), float(start[1]))


def bridge(game, found) -> str:
    if _nearest_threat(game) is not None:
        return AutocrewController._bridge(game)
    if getattr(game, "baffle_clear", None) is not None:
        return "monitoring"                 # let the baffle clearing finish
    ship = game.ship
    escort = escort_course(game)
    if escort is not None and found is not None:
        # An escort prosecutes near its convoy only, never chasing far off.
        point = datum_point(game, found)
        center = convoy_center(game)
        if math.hypot(point[0] - center[0], point[1] - center[1]) > ESCORT_LEASH_NM:
            found = None
    post = guard_post(game)
    if post is not None and found is not None:
        # Guarding the passage it never lets a boat draw it off its post.
        point = datum_point(game, found)
        if math.hypot(point[0] - post[0], point[1] - post[1]) > POST_LEASH_NM:
            found = None
    if found is None:
        if escort is not None:
            return _steer(game, *escort)
        if post is not None and math.hypot(post[0] - ship.x, post[1] - ship.y) > POST_STATION_NM:
            return _steer(game, _bearing(ship.x, ship.y, *post), SEARCH_KN)
        return _steer(game, search_course(game), SEARCH_KN)
    side = 1.0 if math.floor(game.sim_t / CROSS_LEG_S) % 2 else -1.0
    if found["source"] == "lead":
        return _steer(game, _bearing(ship.x, ship.y, found["x"], found["y"]), LEAD_KN)
    if "x" in found:
        bearing = _bearing(ship.x, ship.y, found["x"], found["y"])
        if math.hypot(found["x"] - ship.x, found["y"] - ship.y) > CLOSE_NM:
            return _steer(game, bearing, TRANSIT_KN)
        return _steer(game, bearing + side * 60.0, CLOSE_KN)
    return _steer(game, found["bearing"] + side * 30.0, LEAD_KN)


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


def guarding(game) -> bool:
    """The frigate guards its post against a breakthrough or a
    reconnaissance boat: a closer shot and a short helicopter (a convoy
    escort keeps its helicopter's full reach)."""
    return boat_missions.mode(game) in ("breakthrough", "recon")


def fire_range_nm(game) -> float:
    """The frigate's own torpedo range: guarding a post against a breakthrough
    or a reconnaissance boat it waits for a closer shot than when it hunts or
    screens a convoy."""
    return GUARD_FIRE_NM if guarding(game) else SHIP_FIRE_NM


def weapons(game, found) -> str:
    observed = any(warning["age_s"] <= 2.0 and warning["source"] != "flood"
                   for warning in game.torpedo_warnings(held=False))
    if observed and not game.nixies and game.nixie_store.ready > 0:
        if game.deploy_nixie_result() is True:
            return "countermeasure"
    if observed and game.rbu_defence_bearing() is not None and game.fire_rbu_defence() == "ok":
        return "countermeasure"
    if game.damage.station_down("weapons"):
        return "monitoring"
    contact = None if found is None else found.get("contact")
    if (contact is None or "x" not in found or contact.range_est is None
            or contact.range_est > fire_range_nm(game)):
        return "monitoring"
    if _running(game, "frigate"):
        # A torpedo is out: a boat close enough gets a rocket salvo on top.
        if (contact.range_est <= RBU_FIRE_NM
                and game.designate_sonar_target(contact) is True
                and game.fire_rbu_at(contact, _attack_depth(game, contact)) == "ok"):
            return "engaged"
        return "monitoring"
    if game.designate_sonar_target(contact) is not True:
        return "monitoring"
    depth = _attack_depth(game, contact)
    return "engaged" if game.launch_torpedo_at(contact, depth) is True else "monitoring"


def _attack_depth(game, contact) -> float:
    return float(config.clamp(contact.depth_est if contact.depth_est is not None
                              else game.torpedo_depth, 10.0, 300.0))


def helicopter(game, found) -> str:
    helo = game.helo
    if game.damage.station_down("flightdeck") or helo.state == "VERLOREN":
        return "monitoring"
    point = datum_point(game, found)
    ship = game.ship
    reach = HELO_GUARD_NM if guarding(game) else HELO_RANGE_NM
    if point is None or math.hypot(point[0] - ship.x, point[1] - ship.y) > reach:
        if helo.state == "AUF":
            if helo.dip_state == "DEPLOYED":
                game.set_helicopter_dipping(False)
            elif helo.dip_state == "STOWED":
                game.return_helicopter()
            return "returning"
        return "monitoring"
    if helo.state == "HANGAR":
        tick = int(math.floor(game.sim_t / CADENCE_S))
        if (detrand.u01(game.seed, "hunter.helo", tick)
                >= CADENCE_S / (HELO_READY_MEAN_S * _level_delay(game))):
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
    if game.damage.station_down("opz") or boat_missions.mode(game) == "breakthrough":
        # A frigate guarding the passage against a breakthrough gets no
        # patrol aircraft; HQ sends it to hunts, convoys and reconnaissance.
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
    if (found is None or "x" not in found or found["source"] in ("hq", "esm", "lead")
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
    if not manned(game, Station.ELOKA):
        log_esm(game)
    note_lead(game)
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
