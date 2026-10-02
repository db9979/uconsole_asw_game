"""Save migration: older save documents are lifted to the current format.

Each step turns a document of format ``n`` into one of format ``n + 1`` and
only adds what that format introduced, with the value a running game of the
older release effectively had (the feature did not exist yet).  The result
then goes through the same strict validation and candidate restore as any
current save; a document this module cannot lift stays rejected.

Rules for a format change: bump ``SAVE_VERSION``, add the step here, and add
a frozen sample of the old format to ``tests/data/saves/`` (written by the
release before the change, ``tools/make_save_sample.py``).
``tests/test_save_migrate.py`` loads every sample.

Pure functions on plain JSON data; nothing here touches a running game.
"""

from __future__ import annotations

import copy

from src.core.version import SAVE_VERSION

# Oldest format a step exists for (release 1.3.98, 2026-09-29).
MIGRATE_FROM = 38


def _v38_to_v39(doc: dict) -> None:
    # The AI hunters' ESM bearing lines for a cross-fix.
    doc["hunter_esm"] = []


def _v39_to_v40(doc: dict) -> None:
    # The crew assist that lets the AI man every free station (off before).
    autocrew = doc.get("autocrew")
    if isinstance(autocrew, dict) and autocrew.get("version") == 1:
        autocrew["version"] = 2
        autocrew.setdefault("assist", False)


def _v40_to_v41(doc: dict) -> None:
    # Knuckles (bubble slicks of hard turns) and the flight deck's quiet time.
    doc["knuckles"] = []
    ship = doc.get("ship")
    if isinstance(ship, dict):
        ship.setdefault("deck_quiet_s", 60.0)


def _v41_to_v42(doc: dict) -> None:
    # The crewed boat's towed buoy antenna: stowed.
    crew = doc.get("crew")
    if isinstance(crew, dict) and isinstance(crew.get("orders"), dict):
        crew["orders"].setdefault("buoy", [0.0, False, False])


def _v42_to_v43(doc: dict) -> None:
    # The AI hunters' leads from HQ's start report and a lost bearing.
    doc["hunter_lead"] = None


def _v43_to_v44(doc: dict) -> None:
    # The combat swimmers' lock-out (mission s9, which no older save runs).
    doc["swimmer_hold_s"] = 0.0


def _v44_to_v45(doc: dict) -> None:
    # The counters of scenarios 13, 19 and 20, which no older save runs.
    doc["mission_progress"] = dict(hold_s=0.0, count_s=0.0, gap_s=0.0, phase=0, flags=0)


def _v45_to_v46(doc: dict) -> None:
    # A free patrol's block (no older save runs one) and the boat radio's
    # order fields of the free patrol's own kinds.
    doc["free_roam"] = None
    crew = doc.get("crew")
    radio = crew.get("radio") if isinstance(crew, dict) else None
    if isinstance(radio, dict) and radio.get("version") == 2:
        radio["version"] = 3
        for order in radio.get("orders") or ():
            if isinstance(order, dict):
                order.update(target_id=None, name=None, course=None, speed_kn=None,
                             since=None, points=0)


def _v46_to_v47(doc: dict) -> None:
    # The group hunt's consort destroyer (scenarios 21 and 22, which no older save runs).
    doc["consort"] = None


def _v47_to_v48(doc: dict) -> None:
    # A crewed boat's seeker settings, dead reckoning and route, and each
    # running hostile torpedo's search: what 1.3.140 did (straight, seeker on
    # 3 NM before the datum, an exact position, no route).
    crew = doc.get("crew")
    orders = crew.get("orders") if isinstance(crew, dict) else None
    if isinstance(orders, dict):
        orders.update(torpedo_pattern="straight", torpedo_enable_nm=3.0,
                      nav=[0.0, 0.0, 0.0, 0.0, 0],
                      route={"points": [], "index": 0, "kind": "manual"})
    for torpedo in doc.get("enemy_torpedoes") or ():
        if isinstance(torpedo, dict):
            torpedo.update(pattern="straight", enable_nm=3.0, search_phase=0.0,
                           turns_done=0.0, search_course=None)


def _v48_to_v49(doc: dict) -> None:
    # The optional language model (1.3.146): no advisor help, no experimental
    # opponent, as every mission before it.
    doc["llm"] = {"advisor_sides": [], "experimental": False, "opfor": None}


def _v49_to_v50(doc: dict) -> None:
    # The enemy's knowledge of the player's habits (1.3.166): nothing known,
    # as in every mission before it.
    doc["habits"] = {"side": "frigate", "known": []}


STEPS = {
    38: _v38_to_v39,
    39: _v39_to_v40,
    40: _v40_to_v41,
    41: _v41_to_v42,
    42: _v42_to_v43,
    43: _v43_to_v44,
    44: _v44_to_v45,
    45: _v45_to_v46,
    46: _v46_to_v47,
    47: _v47_to_v48,
    48: _v48_to_v49,
    49: _v49_to_v50,
}


def schema_tag(version: int) -> str:
    return f"u-jagd-save-v{version}"


def document_version(data) -> int | None:
    """The format of a save document whose version and tag agree, else None."""
    if not isinstance(data, dict):
        return None
    version = data.get("version")
    if type(version) is not int or data.get("save_schema") != schema_tag(version):
        return None
    return version


def can_migrate(data) -> bool:
    version = document_version(data)
    return version is not None and MIGRATE_FROM <= version < SAVE_VERSION


def migrate(data):
    """Return ``data`` lifted to ``SAVE_VERSION`` (a copy), or ``data`` itself
    when it is current or cannot be lifted (validation then decides)."""
    if not can_migrate(data):
        return data
    doc = copy.deepcopy(data)
    version = doc["version"]
    while version < SAVE_VERSION:
        step = STEPS.get(version)
        if step is None:
            return data
        step(doc)
        version += 1
        doc["version"] = version
        doc["save_schema"] = schema_tag(version)
    return doc
