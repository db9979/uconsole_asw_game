"""Shared station command metadata used by input and contextual hints."""

from src.core.i18n import Translator, message
from src.core.station import Station


MAP_STATIONS = frozenset((
    Station.BRIDGE,
    Station.WEAPONS,
    Station.HELICOPTER,
))

STATION_PAGES = {
    Station.BRIDGE: ("BRIDGE",),
    Station.SONAR: (
        "BROADBAND",
        "LOFAR",
        "DEMON",
        "TMA",
        "UMWELT/FUSION",
        "ACTIVE",
    ),
    Station.WEAPONS: ("WEAPONS",),
    Station.DAMAGE: ("DAMAGE",),
    Station.OPZ: ("OPZ",),
    Station.RADIO: ("RADIO",),
    Station.ENGINE: ("ENGINE",),
    Station.HELICOPTER: ("HELICOPTER",),
    Station.ELOKA: ("ELOKA",),
}

# Compatibility export for callers that have not moved to station metadata yet.
SONAR_PAGE_COUNT = len(STATION_PAGES[Station.SONAR])


STATION_COMMAND_HINTS = {
    Station.BRIDGE: "Links/Rechts Kurs | Auf/Ab Telegraph | U/V Direkt | Q/E Zoom | K Follow",
    Station.SONAR: "Peilung Links/Rechts | Kontakt Auf/Ab | A Ping | Y TAS | M Ziel",
    Station.WEAPONS: "control.hint.weapons",
    Station.DAMAGE: "Links/Rechts Raum | Auf/Ab Team | Enter Zuweisen",
    Station.OPZ: "control.hint.opz",
    Station.RADIO: "Auf/Ab HFDF | Enter Protokoll",
    Station.ENGINE: "Auf/Ab Telegraph | A Leise | V Fahrt",
    Station.HELICOPTER: "control.hint.helicopter",
    Station.ELOKA: "control.hint.eloka",
}


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


def station_command_hint(station: Station, tr=None) -> str:
    """Translate command metadata, retaining the historical German default."""
    text = STATION_COMMAND_HINTS.get(station, "")
    return (tr or Translator("de").t)(text)
