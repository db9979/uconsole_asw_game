"""Own-mission library over Remote Crew: the solo host lists, uploads, edits,
deletes and starts the Mission Editor's missions; crew sessions cannot."""

import json
import time

import pytest

from src.commander.missions import MISSION_UPLOAD_MAX_BYTES, valid_mission_op
from src.core.mission_definition import default_mission
from test_commander_solo import (game, host, host_view, pair, request, server,  # noqa: F401
                                 session_of, solo)


def _mission(key="user.web_side", name="Web mission"):
    mission = default_mission(key)
    mission["name"] = name
    mission["objective"].update(type="survive")
    return mission


def _post(s, body):
    return request(s.server, "/api/v2/missions", "POST", body, s.cookie, session_of(s)["csrf"])


def _frame(s):
    s.bridge.pump(s.game, s.server, now=time.monotonic())


def _library(s):
    status, _, body = request(s.server, "/api/v2/missions", cookie=s.cookie)
    assert status == 200
    return body


def test_library_is_the_solo_hosts_and_lists_saved_missions(solo):
    from src.data.user_content import default_store
    from src.core import config
    default_store(config.SAVE_DIR).save("mission", _mission())
    solo.bridge._missions._checked_at = None
    _frame(solo)
    library = _library(solo)
    assert [row["key"] for row in library["missions"]] == ["user.web_side"]
    row = library["missions"][0]
    assert row["valid"] and row["side"] == "frigate" and row["data"]["name"] == "Web mission"
    assert host_view(solo)["missions_revision"] == library["revision"]
    status, _, catalog = request(solo.server, "/api/v2/editor/catalog", cookie=solo.cookie)
    assert status == 200 and catalog["world_size_nm"] == 500.0
    assert any(profile["key"] == "diesel_alt" for profile in catalog["profiles"])
    assert len(catalog["sectors"]) == 128
    status, _, coast = request(solo.server, "/api/v2/editor/sector?i=17", cookie=solo.cookie)
    assert status == 200 and coast["index"] == 17 and coast["outlines"]
    assert request(solo.server, "/api/v2/editor/sector?i=999", cookie=solo.cookie)[0] == 404
    assert request(solo.server, "/api/v2/missions")[0] == 401


def test_save_import_delete_and_start_through_the_queue(solo):
    status, _, reply = _post(solo, {"protocol": 2, "id": "m1", "op": "save",
                                    "mission": _mission(), "overwrite": False})
    assert (status, reply) == (202, {"status": "pending", "id": "m1"})
    _frame(solo)
    library = _library(solo)
    assert library["results"][-1] == {"id": "m1", "status": "applied", "reason": "ok",
                                      "issues": []}
    assert [row["key"] for row in library["missions"]] == ["user.web_side"]
    # A second save of the same key needs the overwrite flag.
    _post(solo, {"protocol": 2, "id": "m2", "op": "save",
                 "mission": _mission(name="Other"), "overwrite": False})
    _frame(solo)
    assert _library(solo)["results"][-1]["reason"] == "exists"
    # An invalid mission comes back with its issues in both languages.
    broken = _mission("user.broken")
    broken["seed"] = -1
    _post(solo, {"protocol": 2, "id": "m3", "op": "save", "mission": broken,
                 "overwrite": False})
    _frame(solo)
    result = _library(solo)["results"][-1]
    assert result["status"] == "rejected" and result["issues"][0]["path"] == "seed"
    assert result["issues"][0]["en"] and result["issues"][0]["de"]
    bundle = {"format": "u-jagd.editor-bundle", "version": 1,
              "missions": [_mission("user.imported", "Imported")], "units": []}
    _post(solo, {"protocol": 2, "id": "m4", "op": "import", "bundle": bundle,
                 "overwrite": False})
    _frame(solo)
    assert {row["key"] for row in _library(solo)["missions"]} == {"user.web_side",
                                                                  "user.imported"}
    result = host(solo, "host_start_mission", {"key": "user.imported"}, "s1")
    assert result["reasoncode"] == "ok"
    assert solo.game.custom_mission_definition["key"] == "user.imported"
    assert host(solo, "host_start_mission", {"key": "user.none"}, "s2")["reasoncode"] == \
        "no_mission"
    _frame(solo)
    _post(solo, {"protocol": 2, "id": "m5", "op": "delete", "key": "user.imported"})
    _frame(solo)
    assert [row["key"] for row in _library(solo)["missions"]] == ["user.web_side"]


def test_requests_are_strict_and_bounded(solo):
    assert not valid_mission_op({"protocol": 2, "id": "x", "op": "save",
                                 "mission": {}, "overwrite": False, "extra": 1})
    assert not valid_mission_op({"protocol": 2, "id": "x", "op": "rename", "key": "a"})
    assert not valid_mission_op({"protocol": 2, "id": "", "op": "delete", "key": "a"})
    assert _post(solo, {"protocol": 2, "id": "x", "op": "delete"})[0] == 400
    for index in range(4):
        _post(solo, {"protocol": 2, "id": f"q{index}", "op": "delete", "key": "user.none"})
    assert _post(solo, {"protocol": 2, "id": "q5", "op": "delete", "key": "user.none"})[0] == 429
    _frame(solo)
    # A body over the bound is refused from its length alone.
    import http.client
    host_, port = solo.server.address
    connection = http.client.HTTPConnection(host_, port, timeout=3)
    connection.putrequest("POST", "/api/v2/missions")
    for name, value in (("Origin", f"http://{host_}:{port}"),
                        ("Content-Type", "application/json"),
                        ("Content-Length", str(MISSION_UPLOAD_MAX_BYTES + 1)),
                        ("Cookie", solo.cookie)):
        connection.putheader(name, value)
    connection.endheaders()
    assert connection.getresponse().status == 413
    connection.close()
    assert request(solo.server, "/api/v2/missions", "POST", {"protocol": 2}, solo.cookie)[0] == 403


def test_crew_sessions_have_no_mission_library(server, game):  # noqa: F811
    game.commander.bridge.pump(game, server, now=time.monotonic())
    status, headers, session = pair(server, "Crew")
    assert status == 200
    cookie = headers["Set-Cookie"].split(";", 1)[0]
    assert request(server, "/api/v2/missions", cookie=cookie)[0] == 403
    status, _, _ = request(server, "/api/v2/missions", "POST",
                           {"protocol": 2, "id": "x", "op": "delete", "key": "user.a"},
                           cookie, session["csrf"])
    assert status == 403


@pytest.mark.parametrize("params", [{}, {"key": "nope"}, {"key": "user.a", "x": 1},
                                    {"key": 5}])
def test_start_mission_params_are_strict(params):
    from src.commander.v2.commands import V2_ACTION_REGISTRY
    assert V2_ACTION_REGISTRY["host_start_mission"].validate_params(params) is not True


def test_publication_is_json(solo):
    _frame(solo)
    json.dumps(_library(solo))
