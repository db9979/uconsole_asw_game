"""Shared station command metadata used by input and contextual hints."""

from src.core import config
from src.core.station import Station


MAP_STATIONS = frozenset((
    Station.BRIDGE,
    Station.WEAPONS,
    Station.HELICOPTER,
))

SONAR_PAGE_COUNT = 6
# Game owns page selection but imports this module before handling input. Keep
# the shared count authoritative until page selection is moved here entirely.
config.SONAR_PAGE_COUNT = SONAR_PAGE_COUNT


STATION_COMMAND_HINTS = {
    Station.BRIDGE: "Links/Rechts Kurs | Auf/Ab Telegraph | U/V Direkt | Q/E Zoom | K Follow",
    Station.SONAR: "Peilung Links/Rechts | Kontakt Auf/Ab | A Ping | Y TAS | M Ziel",
    Station.WEAPONS: "Auf/Ab Tiefe | Links/Rechts Kontakt | M Ziel | Q/E Zoom | K Follow",
    Station.DAMAGE: "Links/Rechts Raum | Auf/Ab Team | Enter Zuweisen",
    Station.OPZ: "Links/Rechts ASM | Auf/Ab CIC | M Uebergabe | Bild Radarbereich",
    Station.RADIO: "Auf/Ab HFDF | Enter Protokoll",
    Station.ENGINE: "Auf/Ab Telegraph | A Leise | V Fahrt",
    Station.HELICOPTER: "Links/Rechts Peilung | Auf/Ab Distanz | M Ziel | Q/E Zoom | K Follow",
}


def event_feed_heading(station: Station) -> str:
    """Keep the event log separate from station command instructions."""
    return "EREIGNIS-FEED"


def sonar_page_step(current: int, delta: int) -> int:
    """Cycle all sonar analysis pages, including the ACTIVE workstation."""
    return (int(current) + int(delta)) % SONAR_PAGE_COUNT


def toggle_tas(game, tr=None) -> bool:
    """Deploy or retrieve TAS through the public sonar command API."""
    translate = tr or getattr(game, "tr", None)
    sonar = game.sonar
    speed = getattr(getattr(game, "ship", None), "speed", 0.0)
    changed = sonar.toggle_tow(speed)
    status = sonar.tow_status(speed)
    if not changed:
        message = (translate("status.tas.fault") if translate
                   else "TAS STOERUNG: Bedienung gesperrt")
    else:
        key = ("status.tas.deploy" if status["state"] == "DEPLOYING"
               else "status.tas.retrieve")
        message = translate(key) if translate else (
            "TAS ausbringen" if status["state"] == "DEPLOYING" else "TAS einholen")
        if not status["handling_ok"]:
            message += " | " + (translate("status.tas.speed") if translate
                                else "Fahrt 3-12 kn erforderlich")
    flash = getattr(game, "flash", None)
    if flash is not None:
        flash(message, 2.0)
    feed = getattr(game, "feed", None)
    world = getattr(game, "world", None)
    if feed is not None and world is not None:
        feed.add(world.format_time(), "sonar", message)
    return changed


def station_command_hint(station: Station, tr=None) -> str:
    """Return a translatable station hint without changing existing metadata."""
    text = STATION_COMMAND_HINTS.get(station, "")
    return (tr or (lambda value: value))(text)
