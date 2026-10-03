"""Shared station command metadata used by input and contextual hints."""

from src.core.i18n import message
from src.core.station import Station


MAP_STATIONS = frozenset((
    Station.BRIDGE,
    Station.WEAPONS,
    Station.HELICOPTER,
))

STATION_PAGES = {
    Station.BRIDGE: ("BRIDGE_NAV", "BRIDGE_MISSION", "BRIDGE_LOOKOUT"),
    Station.SONAR: (
        "BROADBAND",
        "LOFAR",
        "DEMON",
        "TMA",
        "UMWELT/FUSION",
        "ACTIVE",
    ),
    Station.WEAPONS: ("WEAPONS_TARGET", "WEAPONS_AMMO"),
    Station.DAMAGE: ("DAMAGE_PLAN", "DAMAGE_DETAIL", "DAMAGE_CREW"),
    Station.OPZ: ("OPZ_PICTURE", "OPZ_TARGET", "OPZ_MPA", "OPZ_GROUP", "OPZ_DISPLAY"),
    Station.RADIO: ("RADIO_HFDF", "RADIO_MESSAGES", "RADIO_TASKS"),
    Station.ENGINE: ("ENGINE_TELEGRAPH", "ENGINE_SYSTEMS"),
    Station.HELICOPTER: ("HELO_STATUS", "HELO_MISSION", "HELO_SONAR", "HELO_ACOUSTIC"),
    Station.ELOKA: ("ELOKA_INTERCEPTS", "ELOKA_EVIDENCE"),
}

# Compatibility export for callers that have not moved to station metadata yet.
SONAR_PAGE_COUNT = len(STATION_PAGES[Station.SONAR])


def event_feed_heading(station: Station) -> str:
    """Keep the event log separate from station command instructions."""
    return "EREIGNIS-FEED"


def station_page_step(station: Station, current: int, delta: int) -> int:
    """Cycle through the pages declared for a station."""
    return (int(current) + int(delta)) % len(STATION_PAGES[station])


def sonar_page_step(current: int, delta: int) -> int:
    """Compatibility wrapper for cycling sonar analysis pages."""
    return station_page_step(Station.SONAR, current, delta)


def toggle_tas(game, tr=None) -> bool:
    """Deploy or retrieve TAS through the public sonar command API."""
    sonar = game.sonar
    speed = getattr(getattr(game, "ship", None), "speed", 0.0)
    changed = sonar.toggle_tow(speed)
    status = sonar.tow_status(speed)
    if not changed:
        notice = message("status.tas.fault")
    else:
        key = ("status.tas.deploy" if status["state"] == "DEPLOYING"
               else "status.tas.retrieve")
        notice = message(key)
        if not status["handling_ok"]:
            notice = message("status.tas.handling", action=notice,
                             speed=message("status.tas.speed"))
    flash = getattr(game, "flash", None)
    if flash is not None:
        flash(notice, 2.0)
    feed = getattr(game, "feed", None)
    world = getattr(game, "world", None)
    if feed is not None and world is not None:
        feed.add(world.format_time(), "sonar", notice)
    return changed


def toggle_vds(game, tr=None) -> bool:
    """Lower or recover the variable-depth sonar through the sonar command API."""
    sonar = game.sonar
    status = sonar.vds_status()
    result = game.set_sonar_vds(status["state"] in ("STOWED", "RETRIEVING"))
    status = sonar.vds_status(getattr(getattr(game, "ship", None), "speed", 0.0),
                              game._sea_state_now())
    if result is not True:
        notice = message("status.vds.fault")
    else:
        notice = message("status.vds.deploy" if status["state"] == "DEPLOYING"
                         else "status.vds.retrieve")
        if not status["handling_ok"]:
            notice = message("status.vds.handling", action=notice)
    flash = getattr(game, "flash", None)
    if flash is not None:
        flash(notice, 2.0)
    feed = getattr(game, "feed", None)
    world = getattr(game, "world", None)
    if feed is not None and world is not None:
        feed.add(world.format_time(), "sonar", notice)
    return result is True
