"""Published observations, alarms and reports never reveal an entity's type.

Differential checks: swapping the hidden entity type behind a measurement
must not change what the operator is shown; only operator classifications
and measured cues may.
"""

import pytest

from src.core import config
from src.core.game import Game
from src.core.i18n import localize
from src.sensors import threat_cue
from src.sonar.sonar import Contact


@pytest.fixture
def game(monkeypatch):
    value = Game(seed=4242, start_menu=False, audio_enabled=False)
    monkeypatch.setattr(value.world, "sonar_path_blocked", lambda *args: False)
    monkeypatch.setattr(value.world, "land_blocks_line", lambda *args: False)
    value.subs = []
    value.animals = value.civilians = value.warships = []
    value.enemy_torpedoes = []
    return value


def _publish_contact(game, monkeypatch, kind, player_class=None):
    contact = Contact(31, 7001, "passiv", kind)
    contact.update_passive(123.0, .8, .8, "", game.sim_t)
    contact.player_class = player_class

    def fake_update(*args, **kwargs):
        game.sonar.contacts[contact.target_id] = contact

    monkeypatch.setattr(game.sonar, "update", fake_update)
    game._update_sensors(.25)
    return game.air_picture.current("U-7001", game.sim_t)


@pytest.mark.parametrize("kind", ["sub", "surface", "animal", "decoy", "torpedo"])
def test_sonar_domain_ignores_entity_type(game, monkeypatch, kind):
    track = _publish_contact(game, monkeypatch, kind)
    assert track.kind == "UNKNOWN"
    assert not game.torpedo_warnings()


@pytest.mark.parametrize("player_class,expected", [
    ("U_BOOT", "SUB"), ("KAMPFSCHIFF", "SURFACE"), ("FAHRZEUG", "SURFACE"),
    ("TORPEDO", "TORP"), ("BIOLOGISCH", "UNKNOWN"), (None, "UNKNOWN")])
def test_sonar_domain_follows_operator_classification(game, monkeypatch,
                                                      player_class, expected):
    track = _publish_contact(game, monkeypatch, "animal", player_class)
    assert track.kind == expected


def test_new_contact_report_is_identical_for_every_entity_type(monkeypatch):
    texts = set()
    for kind in ("sub", "torpedo", "surface", "animal"):
        game = Game(seed=4243, start_menu=False, audio_enabled=False)
        game.enemy_torpedoes = []
        _publish_contact(game, monkeypatch, kind)
        texts.add(localize(game.feed.recent(1)[0].text, game.tr))
    assert len(texts) == 1
    assert "torpedo" not in next(iter(texts)).lower()


def test_operator_torpedo_classification_raises_the_alarm(game, monkeypatch):
    _publish_contact(game, monkeypatch, "surface", "TORPEDO")
    (warning,) = game.torpedo_warnings()
    assert warning["source"] == "classified" and warning["contact"] == 31


def test_torpedo_cues_are_intercepts_only():
    assert threat_cue.torpedo_cue_kind(0.0, False, 20.0) == "transient"
    assert threat_cue.torpedo_cue_kind(0.0, False,
                                       config.TORP_TRANSIENT_HEAR_NM + 1) is None
    assert threat_cue.torpedo_cue_kind(config.TORP_SPOOLUP_S, False, 1.0) is None
    assert threat_cue.torpedo_cue_kind(config.TORP_SPOOLUP_S, True, 2.0) == "seeker"
    assert threat_cue.torpedo_cue_kind(
        config.TORP_SPOOLUP_S, True, config.TORP_SEEKER_INTERCEPT_NM + 1) is None
    first = threat_cue.measured_cue_bearing(90.0, 5, 11, 12.0)
    assert first == threat_cue.measured_cue_bearing(90.0, 5, 11, 12.1)
    assert first != threat_cue.measured_cue_bearing(90.0, 5, 11, 12.3)


def test_air_kind_comes_from_measured_speed_altitude_and_jamming():
    fast, slow = config.ASM_CUE_SPEED_KN + 50, config.ASM_CUE_SPEED_KN - 50
    low, high = config.ASM_CUE_ALTITUDE_M - 50, config.ASM_CUE_ALTITUDE_M + 500
    assert threat_cue.air_track_kind(None, None, low, False) == "FLG"
    assert threat_cue.air_track_kind("FLG", fast, low, False) == "ASM"
    assert threat_cue.air_track_kind("FLG", fast, high, False) == "FLG"
    assert threat_cue.air_track_kind("FLG", slow, low, False) == "FLG"
    assert threat_cue.air_track_kind(None, None, None, True) == "ASM"
    assert threat_cue.air_track_kind("ASM", slow, high, False) == "ASM"


def test_no_sensor_publishes_a_hard_coded_submarine_domain():
    import inspect
    # HFDF fixes once published kind="SUB": any HF intercept meant "submarine".
    assert 'kind="SUB"' not in inspect.getsource(Game)


def test_breakup_noise_names_no_class(game):
    game._report_breakup_noise(game.ship.x + 3.0, game.ship.y, 50.0, 17)
    text = localize(game.msg, game.tr)
    assert text.startswith("SONAR: breaking-up noises")
    assert not any(word in text.lower()
                   for word in ("submarine", "warship", "sunk", "+1000"))


def test_dip_layer_is_unknown_until_the_dome_passes_it(game, monkeypatch):
    from src.commander import projections
    helo = game.helo
    monkeypatch.setattr(game.world, "thermocline_depth_m", lambda *args: 60.0)
    monkeypatch.setattr(game.world, "depth_m", lambda *args: 500.0)
    monkeypatch.setattr(helo, "water_entry_clear", lambda *args: True)
    helo.state = "AUF"
    helo.dip_state = "STOWED"
    helo.dip_depth_m = 0.0
    before = projections._helicopter(game, [], {}, {})["dip_environment"]
    assert before["thermocline_m"] is None and before["water_depth_m"] == 500.0
    helo.dip_state = "DEPLOYED"
    helo.dip_depth_m = 40.0
    above = projections._helicopter(game, [], {}, {})["dip_environment"]
    assert above["thermocline_m"] is None
    helo.dip_depth_m = 80.0
    below = projections._helicopter(game, [], {}, {})["dip_environment"]
    assert below["thermocline_m"] == 60.0 and below["below_thermocline"] is True


def test_web_maps_draw_nato_symbols_from_published_fields():
    from commander_web import client_js
    app = client_js()
    role_map = app[app.index("function drawRoleMap"):app.index("function drawRoleMap") + 12000]
    chart = app[app.index("function drawChart()"):app.index("function drawSymbolOn")]
    # Both web maps use the same affiliation frame + domain glyph as the
    # uConsole, fed only by the operator affiliation and observed domain.
    assert "drawNatoSymbol(plot.context, x, y, row.affiliation, row.domain" in role_map
    assert "drawSymbol(x, y, track.domain, color, fontSize * .65, track.affiliation)" in chart
    for frame in ('"HOSTILE"', '"NEUTRAL"', '"FRIEND"'):
        assert frame in app[app.index("function drawNatoSymbol"):]
