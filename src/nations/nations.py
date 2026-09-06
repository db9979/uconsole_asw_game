"""W3: Nationen im Operationsbereich (Nations-Screen, Taste N).

Reichtweite je Nation + Basis-Infrastruktur. Basis-Positionen kommen aus
data/coastlines/region.json (Coastline.airbases).
"""

from src.core import config

NATIONS = {
    "HANSE": {
        "name": "Hansebund",
        "flag": "HANSE",
        "color": config.COLOR_CONTACT_ZIVIL,
        "hostile": False,
        "desc": ("Verbündete Marine. Fregatte F-217 stationiert in WESTHAVEN. "
                 "Zivile Schifffahrt und HSP-5-Flugfeld NORDHAVN."),
        "radar": "AN (Allied – Tracks werden mit AIS geteilt)",
        "submarines": "–",
    },
    "BOREN": {
        "name": "Borenia",
        "flag": "BOREN",
        "color": config.COLOR_DANGER,
        "hostile": True,
        "desc": ("Gegnerische Marine. Operiert U-Boot-Floot (Diesel, AIP, "
                 "nuklear) aus GOTH-OST. Feindliche ASMs starten von dort. "
                 "ESM/Chaff gegen unsere Radargeräte."),
        "radar": "FEINDLICH (ESM-Abwehr, Chaff)",
        "submarines": "U-27 (Altmetall) · U-58 (AIP) · SSN-7 (Kern)",
    },
    "SKANDIA": {
        "name": "Skandia",
        "flag": "SKANDIA",
        "color": config.COLOR_FLIGHT,
        "hostile": False,
        "desc": ("Neutraler Küstenstaat. Flugfeld OSTLAND – zivile Patrouillen "
                 "und Küstenbeobachtung. Keine Feindseligkeit, aber Luftraum "
                 "beachten (Kollisionswarnung auf der Karte)."),
        "radar": "NEUTRAL (Küstenbeobachtung)",
        "submarines": "–",
    },
    "ZIVIL": {
        "name": "Zivile Schifffahrt",
        "flag": "CIV",
        "color": config.COLOR_CONTACT_ZIVIL,
        "hostile": False,
        "desc": ("Zivile Frachter und Küstenfahrer (AIS-identifiziert). "
                 "Sonderregeln (ROE): keine Torpedos! Politischer Vorfall = "
                 "Mission verloren."),
        "radar": "AIS (identifiziert, nie anfeuern)",
        "submarines": "–",
    },
}


def get_nation(key: str) -> dict:
    return NATIONS.get(key, NATIONS["ZIVIL"])
