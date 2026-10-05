"""Own-mission library over Remote Crew (solo host surface, transport side).

The solo session (the one browser holding every station) may list, download,
upload, edit and delete the Mission Editor's missions and start one. This
module holds the server half: the main thread publishes the library
(``publish_missions_v2``), the editor catalog and the packaged sector coasts;
an upload, save or delete arrives at ``POST /api/v2/missions``, is checked for
shape and size here and queued as a detached item for the main thread, which
alone touches the user store (``src/commander/mission_library.py``). Starting
a mission is the ordinary host command ``host_start_mission``.

Everything here is transient: never saved, never in settings. Credentials
and session data never enter a publication.
"""

from __future__ import annotations

import unicodedata
from collections import deque

from src.commander.v2.wire import _json_bytes

# Upload body bound (a bundle file is at most 1 MiB, plus the envelope).
MISSION_UPLOAD_MAX_BYTES = 1024 * 1024 + 4096
# Library publication bound (all missions with their referenced user units).
MISSIONS_MAX_BYTES = 3 * 1024 * 1024
EDITOR_CATALOG_MAX_BYTES = 512 * 1024
SECTOR_MAX_BYTES = 192 * 1024  # 1:10m coast of the largest sector ~105 KB
MISSION_OPS_PENDING_MAX = 4
MISSION_OPS = ("save", "import", "delete", "generate")
GENERATE_REQUEST_MAX = 500
_BLANK = _json_bytes({"protocol": 2, "revision": 0, "missions": [], "units": [],
                      "user_profiles": [], "results": [], "truncated": False})


def _text_id(value) -> bool:
    return (type(value) is str and 1 <= len(value) <= 64
            and not any(unicodedata.category(char).startswith("C") for char in value))


def valid_mission_op(body) -> bool:
    """Shape of one library request (content is validated on the main thread)."""
    if type(body) is not dict or body.get("protocol") != 2 or not _text_id(body.get("id")):
        return False
    op = body.get("op")
    if op == "delete":
        return set(body) == {"protocol", "id", "op", "key"} and _text_id(body["key"])
    if op == "save":
        return (set(body) == {"protocol", "id", "op", "mission", "overwrite"}
                and type(body["mission"]) is dict and type(body["overwrite"]) is bool)
    if op == "generate":
        # A mission from a few words (optional language model, src/llm/mission_gen.py).
        request = body.get("request")
        return (set(body) == {"protocol", "id", "op", "request", "side"}
                and body["side"] in ("frigate", "uboot") and type(request) is str
                and 0 < len(request.strip()) <= GENERATE_REQUEST_MAX
                and all(char.isprintable() for char in request))
    if op == "import":
        return (set(body) == {"protocol", "id", "op", "bundle", "overwrite"}
                and type(body["bundle"]) is dict and type(body["overwrite"]) is bool)
    return False


class MissionOp:
    """One queued library request, detached from the transport."""

    __slots__ = ("client_id", "ordinal", "body")

    def __init__(self, client_id, ordinal, body):
        self.client_id = client_id
        self.ordinal = ordinal
        self.body = body


class MissionLibraryServerMixin:
    """Library publications and the request queue of ``CommanderServer``."""

    def _init_missions(self):
        self._v2_missions = _BLANK
        self._v2_editor_catalog = None
        self._v2_sectors = {}
        self._mission_ops = deque()

    def _clear_missions_locked(self):
        self._v2_missions = _BLANK
        self._mission_ops.clear()

    def enqueue_mission_op_locked(self, session, body) -> str:
        """"pending", or why not: "forbidden", "invalid", "queue_full"."""
        if not self._host_surface(session):
            return "forbidden"
        if not valid_mission_op(body):
            return "invalid"
        if len(self._mission_ops) >= MISSION_OPS_PENDING_MAX:
            return "queue_full"
        self._mission_ops.append(MissionOp(session["client_id"], session["ordinal"], body))
        return "pending"

    def take_mission_ops(self) -> list:
        """Detach the queued requests whose session still holds the host surface."""
        with self._lock:
            ops, self._mission_ops = list(self._mission_ops), deque()
            live = {(session["client_id"], session["ordinal"])
                    for session in self._sessions_v2.values()
                    if self._host_surface(session)}
        return [op for op in ops if (op.client_id, op.ordinal) in live]

    def publish_missions_v2(self, library: dict) -> None:
        encoded = _json_bytes(library)
        if len(encoded) > MISSIONS_MAX_BYTES:
            raise ValueError("v2 mission library size limit exceeded")
        with self._lock:
            self._v2_missions = encoded

    def publish_editor_catalog_v2(self, catalog: dict, sectors: dict) -> None:
        """The static editor catalog and the packaged sector coasts (once)."""
        encoded = _json_bytes(catalog)
        coasts = {int(index): _json_bytes(value) for index, value in sectors.items()}
        if (len(encoded) > EDITOR_CATALOG_MAX_BYTES
                or any(len(value) > SECTOR_MAX_BYTES for value in coasts.values())):
            raise ValueError("v2 editor catalog size limit exceeded")
        with self._lock:
            self._v2_editor_catalog = encoded
            self._v2_sectors = coasts

    @property
    def editor_catalog_published(self) -> bool:
        with self._lock:
            return self._v2_editor_catalog is not None

    def mission_route_body_locked(self, session, path):
        """GET bodies of the library routes, None when not available."""
        if not self._host_surface(session):
            return None
        if path == "/api/v2/missions":
            return self._v2_missions
        if path == "/api/v2/editor/catalog":
            return self._v2_editor_catalog
        prefix = "/api/v2/editor/sector?i="
        if path.startswith(prefix):
            digits = path[len(prefix):]
            if digits.isdigit() and len(digits) <= 3:
                return self._v2_sectors.get(int(digits))
        return None
