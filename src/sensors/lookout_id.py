"""Visual recognition by the bridge lookout (pure functions).

A sighting passes three levels, after the Johnson criteria for resolving a
target's critical dimension: detection (1 cycle), recognition of the class
(4 cycles) and identification of the type (6.4 cycles).  The lookout uses
7x50 binoculars; on a moving ship their effective resolution gain is taken
as 2, so recognition needs 2 and identification 3.2 cycles of the naked-eye
detection threshold.  Larger targets are resolved further out
(``size_factor``); the contrast still decays with range (Koschmieder).

The class is what a trained lookout can see of the silhouette.  It is
reported as an observation on the lookout's visual track; it never sets the
operator's classification or affiliation.  Live AIS/ADS-B contacts carry the
same generic catalog profiles as simulated traffic, so their visual reports
are indistinguishable.  Nothing here edits the contact catalog: the classes
are derived from the existing profile keys, categories and names.
"""

from __future__ import annotations

DETECTED, RECOGNIZED, IDENTIFIED = 0, 1, 2
RECOGNIZE_CYCLES = 2.0
IDENTIFY_CYCLES = 3.2
LABEL_PREFIX = "VISUAL"

# Class code -> relative size of the silhouette against the calibrated
# detection height of its kind (SURFACE 12 m, SUB 3 m, FLG 6 m).
CLASS_SIZE = {
    "MERCHANT": 1.5, "TANKER": 1.6, "CARGO": 1.5, "PASSENGER": 1.6,
    "WARSHIP": 1.0, "CARRIER": 2.0, "CRUISER": 1.2, "DESTROYER": 1.0,
    "FRIGATE": 0.9, "CORVETTE": 0.7, "MINE_WARFARE": 0.6, "NAVAL_AUXILIARY": 1.3,
    "SERVICE": 0.7, "TUG": 0.6, "RESEARCH": 0.7, "OFFSHORE": 0.8,
    "FISHING": 0.6, "SMALL_CRAFT": 0.4, "RESCUE": 0.45,
    "SUBMARINE": 1.0,
    "AIRLINER": 1.4, "MILITARY_AIRCRAFT": 0.9, "COMBAT_AIRCRAFT": 0.9,
    "TORPEDO_WAKE": 1.0, "SHIP": 1.0, "LAND": 1.0,
}
CLASSES = tuple(CLASS_SIZE)

# (recognized class, identified class) for the non-warship catalog entries.
_AUX = {
    "aux_01": ("WARSHIP", "MINE_WARFARE"),
    "aux_02": ("SERVICE", "TUG"),
    "aux_03": ("SMALL_CRAFT", "RESCUE"),
    "aux_04": ("SERVICE", "RESEARCH"),
    "aux_05": ("SERVICE", "RESEARCH"),
    "aux_06": ("SERVICE", "OFFSHORE"),
    "aux_07": ("FISHING", "FISHING"),
    "aux_08": ("SERVICE", "RESEARCH"),
    "aux_09": ("SERVICE", "TUG"),
    "aux_10": ("SMALL_CRAFT", "SMALL_CRAFT"),
}
_CATEGORY = {"TANKER": "TANKER", "FRACHT": "CARGO", "PASSAGIER": "PASSENGER"}
# Warship type from the catalog name (German catalog names).
_WARSHIP_WORDS = (("Nimitz", "CARRIER"), ("Flottenversorger", "NAVAL_AUXILIARY"),
                  ("Kreuzer", "CRUISER"), ("Zerstoerer", "DESTROYER"),
                  ("Fregatte", "FRIGATE"), ("Korvette", "CORVETTE"),
                  ("20380", "CORVETTE"))


def _warship(name: str) -> str:
    for word, code in _WARSHIP_WORDS:
        if word in name:
            return code
    return "WARSHIP"


def surface_classes(profile) -> tuple[str, str, str | None]:
    """(recognized, identified, type key) for a surface ship profile.

    Only warships reveal a type (their class silhouette); merchant ships are
    identified by name and AIS, not by their outline."""
    key = str(getattr(profile, "key", ""))
    category = str(getattr(profile, "category", ""))
    name = str(getattr(profile, "name", ""))
    if key in _AUX:
        recognized, identified = _AUX[key]
        return recognized, identified, None
    if category in _CATEGORY:
        return "MERCHANT", _CATEGORY[category], None
    if category == "KAMPFSCHIFF" or key.startswith("warship_"):
        identified = _warship(name)
        recognized = "CARRIER" if identified == "CARRIER" else "WARSHIP"
        return recognized, identified, key or None
    return "SHIP", "SHIP", None


def aircraft_classes(kind: str, profile_key: str | None) -> tuple[str, str, str | None]:
    """(recognized, identified, type key) for an aircraft.

    Civil traffic, simulated or live ADS-B, shares one generic profile, so
    the lookout names no airliner type."""
    if kind == "civil":
        return "AIRLINER", "AIRLINER", None
    return "MILITARY_AIRCRAFT", "COMBAT_AIRCRAFT", profile_key


def encode(level: int, recognized: str, identified: str,
           type_key: str | None) -> str:
    """Track label carrying the visual report (saved with the track)."""
    if level <= DETECTED:
        return LABEL_PREFIX
    if level == RECOGNIZED:
        return f"{LABEL_PREFIX}:R:{recognized}"
    return f"{LABEL_PREFIX}:I:{identified}" + (f":{type_key}" if type_key else "")


def decode(label) -> tuple[int, str | None, str | None]:
    """(level, class, type key) from a lookout track label; invalid -> level -1."""
    if label == LABEL_PREFIX:
        return DETECTED, None, None
    if type(label) is not str or not label.startswith(LABEL_PREFIX + ":"):
        return -1, None, None
    parts = label.split(":")
    if len(parts) == 3 and parts[1] == "R" and parts[2] in CLASS_SIZE:
        return RECOGNIZED, parts[2], None
    if parts[1:2] == ["I"] and len(parts) in (3, 4) and parts[2] in CLASS_SIZE:
        return IDENTIFIED, parts[2], (parts[3] if len(parts) == 4 else None)
    return -1, None, None


def type_keys(catalog) -> set:
    """Catalog keys a visual identification may name."""
    return set(catalog.surfaces) | set(catalog.aircraft)


def valid_label(label, keys) -> bool:
    level, _code, type_key = decode(label)
    return level >= 0 and (type_key is None or type_key in keys)


__all__ = ["DETECTED", "RECOGNIZED", "IDENTIFIED", "RECOGNIZE_CYCLES",
           "IDENTIFY_CYCLES", "CLASS_SIZE", "CLASSES", "surface_classes",
           "aircraft_classes", "encode", "decode", "type_keys", "valid_label"]
