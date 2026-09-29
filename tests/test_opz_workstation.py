"""OPZ/CIC: Track-Fokus, NATO-Symbole und Persistenz."""

from types import SimpleNamespace as NS

import pygame
import pytest

from src.core import config
from src.core.game import Game
from src.core.station import Station
from src.sonar.sonar import Contact
from src.ui import layout, nato_symbols
from src.ui import stations_view
from src.core.i18n import localize


def press(game, key, mod=0):
    game.handle_event(pygame.event.Event(pygame.KEYDOWN, key=key, mod=mod))


def observe(game, track_id, kind, source="RADAR", range_nm=10.0):
    return game.air_picture.observe(
        track_id=track_id, kind=kind, target_id=int(track_id.split("-")[1]),
        source=source, bearing=90.0, range_nm=range_nm,
        observer_x=game.ship.x, observer_y=game.ship.y, course=45.0,
        quality=.8, now=game.sim_t, label=track_id)


def opz_game():
    game = Game(seed=31, start_menu=False)
    game.station = Station.OPZ
    game.air_picture._tracks.clear()
    return game


def opz_id(game, source_id):
    game.opz_source_observations()
    return next(key for key, source in game._opz_source_bindings.items()
                if getattr(source, "track_id", None) == source_id)


def test_up_down_selects_all_cic_domains_without_changing_asm_target():
    game = opz_game()
    observe(game, "S-1", "AIS")
    observe(game, "A-2", "FLG")
    observe(game, "M-3", "ASM")
    game.asm_sel = 2

    press(game, pygame.K_DOWN)
    first = game.opz_selected_track_id
    assert first in {track.track_id for track in game.opz_tracks()}
    press(game, pygame.K_DOWN)
    assert game.opz_selected_track_id != first
    assert game.asm_sel == 2
    assert not game.held


def test_shift_f_filters_contact_register_without_removing_picture_tracks():
    game = opz_game()
    observe(game, "S-1", "AIS", source="RADAR")
    observe(game, "A-2", "FLG", source="DATALINK")
    all_ids = {track.track_id for track in game.opz_tracks()}

    press(game, pygame.K_f, pygame.KMOD_SHIFT)
    assert game.opz_contact_filter == "RADAR"
    assert {track.source for track in game.filtered_opz_tracks()} == {"RADAR"}
    assert {track.track_id for track in game.opz_tracks()} == all_ids

    press(game, pygame.K_DOWN)
    assert game.selected_opz_track().source == "RADAR"


def test_opz_joystick_step_uses_cic_focus_not_asm_target():
    game = opz_game()
    observe(game, "S-1", "AIS")
    observe(game, "M-3", "ASM")
    game.asm_sel = 1
    game._joy_step(1)
    assert game.opz_selected_track_id in {track.track_id for track in game.opz_tracks()}
    assert game.asm_sel == 1


def test_f_cycles_selected_track_affiliation_and_c_classifies():
    game = opz_game()
    observe(game, "S-1", "AIS")
    press(game, pygame.K_DOWN)
    assert game.opz_affiliation("S-1") == "UNKNOWN"
    selected = game.opz_selected_track_id
    press(game, pygame.K_f)
    assert game.opz_affiliation(selected) == "FRIEND"
    press(game, pygame.K_f)
    assert game.opz_affiliation(selected) == "NEUTRAL"
    press(game, pygame.K_c)
    assert game.opz_source_classification(selected) == "U_BOOT"


def test_j_edits_selected_track_id_for_opz_and_source_station():
    game = opz_game()
    contact = Contact(1, 41, "passiv", "sub")
    contact.update_passive(30.0, .8, .8, "", game.sim_t)
    contact.released_to_opz = True
    game.sonar.contacts[contact.target_id] = contact
    game.opz_selected_track_id = game.opz_tracks()[0].observation_id

    press(game, pygame.K_j)
    for key in (pygame.K_s, pygame.K_u, pygame.K_b, pygame.K_MINUS,
                pygame.K_4, pygame.K_1):
        press(game, key)
    press(game, pygame.K_RETURN)

    assert game.selected_opz_track().label == "SUB-41"
    assert game.private_sonar_observations()[0].label == "SUB-41"
    assert game.contact_display_id(contact) == "SUB-41"


def test_surface_and_air_radars_toggle_independently():
    game = opz_game()
    assert game.surface_radar_on and game.air_radar_on
    press(game, pygame.K_r)
    assert not game.surface_radar_on and game.air_radar_on
    press(game, pygame.K_r, pygame.KMOD_SHIFT)
    assert not game.surface_radar_on and not game.air_radar_on
    press(game, pygame.K_r)
    assert game.surface_radar_on and not game.air_radar_on


def test_range_keys_cycle_display_scale_without_changing_sensor_maximum():
    game = opz_game()
    assert game.opz_range_nm == 40.0
    press(game, pygame.K_PAGEDOWN)
    assert game.opz_range_nm == 20.0
    press(game, pygame.K_PAGEUP)
    assert game.opz_range_nm == 40.0
    press(game, pygame.K_PAGEUP)
    assert game.opz_range_nm == 80.0
    before = game.radar_effective_range("surface")
    press(game, pygame.K_PAGEUP)
    assert game.radar_effective_range("surface") == before


def test_radar_sweep_turns_clockwise_in_simulation_time():
    game = opz_game()
    game.radar_scan_phase = 0.0
    assert game.radar_sweep_bearing() == 0.0
    game._t += 5.0  # wall time alone does not turn the antenna
    assert game.radar_sweep_bearing() == 0.0
    game.paused = False
    for _ in range(10):
        game._update_sim(0.1)
    assert game.radar_sweep_bearing() == pytest.approx(90.0)
    for _ in range(10):
        game._update_sim(0.1)
    assert game.radar_sweep_bearing() == pytest.approx(180.0)


def test_blip_glow_follows_sweep_and_then_expires():
    game = opz_game()
    game.radar_scan_phase = 90.0  # Sweep steht auf Ost/90 Grad.
    assert stations_view._radar_glow(game, 90.0) == 1.0
    assert 0.0 < stations_view._radar_glow(game, 0.0) < 1.0
    assert stations_view._radar_glow(game, 100.0) == 0.0


def test_sea_clutter_shortens_radar_range_progressively():
    """Radar equation with GIT-type sea clutter: small losses in moderate
    seas, the 1.0.0 anchors (-12.5 % / -25 % surface) at sea state 5/6."""
    game = opz_game()
    game.radar_rain_severity = lambda: 0.0  # isolate the clutter term
    ranges = []
    for sea_state in range(7):
        game.world.sea_state = sea_state
        ranges.append(game.radar_effective_range("surface"))
        assert game.radar_effective_range("air") <= config.RADAR_AIR_RANGE_NM
    assert ranges == sorted(ranges, reverse=True)
    assert ranges[0] == pytest.approx(config.RADAR_SURFACE_RANGE_NM, rel=.01)
    assert ranges[4] >= .93 * config.RADAR_SURFACE_RANGE_NM
    assert ranges[5] == pytest.approx(.875 * config.RADAR_SURFACE_RANGE_NM, rel=.02)
    assert ranges[6] == pytest.approx(.75 * config.RADAR_SURFACE_RANGE_NM, rel=.01)


def test_separate_radars_publish_only_their_domains(monkeypatch):
    game = opz_game()
    monkeypatch.setattr(game.world, "land_blocks_line", lambda *args: False)
    civilian = game.civilians[0]
    civilian.x, civilian.y = game.ship.x + 5.0, game.ship.y
    civilian.emitter = False
    flight = game.flights.flights[0]
    flight.x, flight.y = game.ship.x + 5.0, game.ship.y
    game.civilians = [civilian]
    game.warships = []
    game.flights.flights = [flight]
    game.asms = []

    game.surface_radar_on, game.air_radar_on = True, False
    game._update_air_picture(full_scan=True)
    assert {track.kind for track in game.opz_tracks()
            if track.source.startswith("RADAR")} == {"SURFACE"}

    game.air_picture._tracks.clear()
    game.surface_radar_on, game.air_radar_on = False, True
    game._update_air_picture(full_scan=True)
    assert {track.kind for track in game.opz_tracks()
            if track.source.startswith("RADAR")} == {"FLG"}


def test_annotation_survives_track_expiry_and_reacquisition():
    game = opz_game()
    observe(game, "A-2", "FLG")
    game.opz_affiliations["A-2"] = "HOSTILE"
    game.sim_t = game.air_picture.stale_s + 1.0
    assert game.opz_tracks() == []
    assert game.opz_affiliation("A-2") == "HOSTILE"

    observe(game, "A-2", "FLG")
    assert game.opz_affiliation("A-2") == "HOSTILE"


def test_opz_focus_and_affiliations_survive_save_load():
    game = opz_game()
    observe(game, "S-1", "AIS")
    game.opz_selected_track_id = opz_id(game, "S-1")
    game.opz_affiliations = {game.opz_selected_track_id: "NEUTRAL"}
    game.surface_radar_on = False
    game.air_radar_on = True
    game.opz_range_nm = 10.0
    data = game.save_state()

    loaded = Game(seed=1, start_menu=False)
    loaded.load_state(data)
    assert loaded.opz_selected_track_id == game.opz_selected_track_id
    assert loaded.opz_affiliation(game.opz_selected_track_id) == "NEUTRAL"
    assert not loaded.surface_radar_on and loaded.air_radar_on
    assert loaded.opz_range_nm == 10.0


def test_v10_without_opz_fields_is_rejected_transactionally():
    game = opz_game()
    data = game.save_state()
    data.pop("opz_affiliations")
    data.pop("radars")
    data["ui"].pop("opz_selected_track_id")

    loaded = Game(seed=1, start_menu=False)
    before = loaded.save_state()
    assert not loaded._load_save_data(data)
    assert loaded.save_state() == before


def test_v10_rejects_invalid_opz_affiliation_transactionally():
    game = opz_game()
    before = game.save_state()
    data = game.save_state()
    data["opz_affiliations"]["bad"] = "INVALID"

    assert not game._load_save_data(data)
    assert game.save_state() == before


def test_opz_draws_positioned_and_bearing_only_tracks():
    game = opz_game()
    observe(game, "S-1", "AIS")
    observe(game, "A-2", "FLG")
    observe(game, "M-3", "ASM")
    observe(game, "M-4", "ASM", source="HOJ", range_nm=None)
    game.opz_selected_track_id = opz_id(game, "A-2")
    game.opz_affiliations.update({opz_id(game, "A-2"): "FRIEND",
                                  opz_id(game, "M-3"): "HOSTILE"})
    game.draw()


def test_native_opz_uses_full_height_and_suppresses_bottom_panels(monkeypatch):
    game = opz_game()
    calls = []
    monkeypatch.setattr(game, "draw_bottom_feed", lambda: calls.append("feed"))
    monkeypatch.setattr(game, "draw_bottom_telemetry",
                        lambda: calls.append("telemetry"))
    game.draw()
    assert calls == []
    regions = stations_view.opz_regions(config.OPZ_STATION_RECT)
    assert regions["map"].bottom > config.MAIN_BOTTOM
    assert regions["sidebar"].right == config.SCREEN_W


def test_selected_track_sidebar_is_an_evidence_ledger(monkeypatch):
    game = opz_game()
    observe(game, "S-1", "AIS")
    game.opz_selected_track_id = opz_id(game, "S-1")
    game.opz_affiliations[game.opz_selected_track_id] = "NEUTRAL"
    lines = []
    original = stations_view.layout.blit_line

    def record(screen, text, *args, **kwargs):
        lines.append(localize(text, game.tr))
        return original(screen, text, *args, **kwargs)

    monkeypatch.setattr(stations_view.layout, "blit_line", record)
    game.station_page = 1
    stations_view.draw_opz_view(game)
    assert any("Source" in line and "RADAR" in line for line in lines)
    assert any("Bearing" in line and "available" in line for line in lines)
    assert any("Range" in line and "available" in line for line in lines)
    assert any("Course" in line and "available" in line for line in lines)
    assert game.tr("opz.line.depth_unavailable") in lines
    assert game.tr("opz.line.speed_unavailable") in lines
    assert any("Age/Q" in line for line in lines)
    assert any("Affiliation" in line and "Neutral" in line for line in lines)


def test_selected_track_sidebar_reports_sonar_depth_and_speed(monkeypatch):
    game = opz_game()
    contact = Contact(1, 1, "passiv", "sub")
    contact.update_passive(30.0, .8, .8, "hidden producer label", game.sim_t)
    contact.update_ping(30.0, 4.0, 40.0, .9, game.sim_t)
    contact.tma_course = 270.0
    contact.tma_speed = 12.0
    contact._publish_fix("TMA", game.sim_t, game.sim_t,
                         game.ship.x + 4, game.ship.y, .3, .8)
    contact.player_class = "U_BOOT"
    contact.released_to_opz = True
    game.sonar.contacts[1] = contact
    game.opz_selected_track_id = game.opz_tracks()[0].track_id
    lines = []
    original = stations_view.layout.blit_line

    def record(screen, text, *args, **kwargs):
        lines.append(localize(text, game.tr))
        return original(screen, text, *args, **kwargs)

    monkeypatch.setattr(stations_view.layout, "blit_line", record)
    game.station_page = 1
    stations_view.draw_opz_view(game)
    assert any("Depth" in line and "40" in line and "available" in line
               for line in lines)
    assert any("Speed" in line and "12.0" in line and "available" in line
               for line in lines)


def test_known_coastline_is_requested_even_without_surface_radar(monkeypatch):
    game = opz_game()
    calls = []

    def contours(x, y, radius):
        calls.append((x, y, radius))
        return [((x - 1.0, y), (x + 1.0, y))]

    monkeypatch.setattr(game.world.coast, "contour_segments_in_circle", contours)
    game._t = 0.0
    game.surface_radar_on = True
    game.draw()
    assert calls and calls[-1][2] <= game.opz_range_nm

    calls.clear()
    game.surface_radar_on = False
    game.draw()
    assert calls and calls[-1][2] == game.opz_range_nm


def test_chart_tracks_are_independent_of_selected_radar_range(monkeypatch):
    game = opz_game()
    observe(game, "S-1", "AIS", range_nm=30.0)
    calls = []
    original = nato_symbols.draw_symbol

    def record(*args, **kwargs):
        calls.append((args, kwargs))
        return original(*args, **kwargs)

    monkeypatch.setattr(nato_symbols, "draw_symbol", record)
    game.opz_range_nm = 20.0
    game.draw()
    assert len(calls) == 2
    calls.clear()
    game.opz_range_nm = 40.0
    game.draw()
    assert len(calls) == 2


def test_scope_prefers_public_radar_range_and_shows_all_scale_controls(monkeypatch):
    game = opz_game()
    observe(game, "S-1", "AIS", range_nm=30.0)
    game.opz_range_nm = 40.0
    game.radar_range_nm = 20.0
    symbols = []
    original_symbol = nato_symbols.draw_symbol

    def record_symbol(*args, **kwargs):
        symbols.append(args[2:4])
        return original_symbol(*args, **kwargs)

    monkeypatch.setattr(nato_symbols, "draw_symbol", record_symbol)
    with layout.capture_text() as text:
        stations_view.draw_opz_view(game)

    assert symbols == [("FRIEND", "SURFACE"), ("UNKNOWN", "SURFACE")]
    footer_y = pygame.Rect(config.STATION_RECT).bottom - 28
    footer = " ".join(entry["text"] for entry in text
                      if abs(entry["rect"].y - footer_y) <= 4)
    assert "PgUp/Dn" in footer
    assert "20 NM" in footer
    assert all(str(scale) in footer for scale in (10, 20, 40, 80, 120))


def test_opz_ppi_hit_rect_is_bounded_at_1280x720(monkeypatch):
    monkeypatch.setattr(config, "STATION_RECT", config.OPZ_STATION_RECT)
    regions = stations_view.opz_regions()
    ppi = regions["chart"]
    assert pygame.Rect(0, 0, 1280, 720).contains(ppi)
    assert ppi.right <= int(config.STATION_RECT[2] * .75)
    assert regions["map"].contains(ppi)
    assert regions["map"] == ppi
    assert regions["map"].bottom > config.MAIN_BOTTOM
    assert all(not regions["map"].colliderect(regions[action])
               for action in ("classify", "affiliate", "mark", "fusion"))


def test_opz_draws_recognizable_chart_beneath_disabled_radar(monkeypatch):
    game = opz_game()
    monkeypatch.setattr(config, "STATION_RECT", config.OPZ_STATION_RECT)
    ship_x, ship_y = game.ship.x, game.ship.y
    game.world.coast.landmasses = [NS(
        name="Chart land", bounds=(ship_x + 2, ship_y + 2,
                                    ship_x + 6, ship_y + 6),
        points=[(ship_x + 2, ship_y + 2), (ship_x + 6, ship_y + 2),
                (ship_x + 6, ship_y + 6), (ship_x + 2, ship_y + 6)])]
    game.world.coast._bathymetry = None
    game.surface_radar_on = game.air_radar_on = False
    game.screen.fill((201, 12, 93))

    stations_view.draw_opz_view(game)

    regions = stations_view.opz_regions()
    ppi, chart = regions["chart"], regions["map"]
    view = stations_view._opz_view(game, ppi)
    land_pixel = tuple(map(int, view.world_to_screen(ship_x + 4, ship_y + 4)))
    assert game.screen.get_at(land_pixel)[:3] == config.COLOR_LAND
    assert game.screen.get_at((chart.left + 4, chart.centery))[:3] != (201, 12, 93)


def test_contact_scale_does_not_track_selected_radar_range(monkeypatch):
    game = opz_game()
    observe(game, "S-1", "AIS", range_nm=10.0)
    positions = []

    def symbol(surface, position, affiliation, domain, *args, **kwargs):
        if affiliation != "FRIEND":
            positions.append(position)
        return nato_symbols.AFFILIATION_COLORS[affiliation]

    monkeypatch.setattr(nato_symbols, "draw_symbol", symbol)
    center_x = stations_view.opz_ppi_rect().centerx
    game.radar_range_nm = 20.0
    stations_view.draw_opz_view(game)
    near_displacement = positions[-1][0] - center_x
    game.radar_range_nm = 40.0
    stations_view.draw_opz_view(game)
    far_displacement = positions[-1][0] - center_x

    assert near_displacement == far_displacement


def test_unreleased_legacy_sonar_mirrors_are_not_opz_rows(monkeypatch):
    game = opz_game()
    observe(game, "U-1", "SUB", source="SONAR-PING")
    observe(game, "T-2", "TORP", source="SONAR")
    game.opz_affiliations.update({"U-1": "FRIEND", "T-2": "HOSTILE"})
    rows = []
    original = stations_view.layout.blit_line

    def record(screen, text, rect, color, *args, **kwargs):
        if " UBT " in text or " TOR " in text:
            rows.append((text, color))
        return original(screen, text, rect, color, *args, **kwargs)

    monkeypatch.setattr(stations_view.layout, "blit_line", record)
    stations_view.draw_opz_view(game)

    assert rows == []
    assert (stations_view.OPZ_DOMAIN_COLORS["SUBSURFACE"] ==
            config.COLOR_CONTACT_UBOOT)
    assert (stations_view.OPZ_DOMAIN_COLORS["UNDERWATER_WEAPON"] ==
            config.COLOR_CONTACT_MISSILE)
    # W2: sub vs. inbound weapon are different threats and must not render
    # in near-identical reds (COLOR_CONTACT_UBOOT vs. the old COLOR_DANGER).
    assert (stations_view.OPZ_DOMAIN_COLORS["SUBSURFACE"]
            != stations_view.OPZ_DOMAIN_COLORS["UNDERWATER_WEAPON"])


def test_weather_clutter_is_absent_before_five_and_deterministic_at_six():
    game = opz_game()
    first = pygame.Surface((240, 240))
    second = pygame.Surface((240, 240))
    first.fill((0, 0, 0))
    empty = pygame.image.tobytes(first, "RGB")
    game.world.sea_state = 4
    stations_view._draw_radar_clutter(game, first, (120, 120), 100)
    assert pygame.image.tobytes(first, "RGB") == empty

    game.world.sea_state = 6
    game._t = 1.5
    first.fill((0, 0, 0))
    second.fill((0, 0, 0))
    stations_view._draw_radar_clutter(game, first, (120, 120), 100)
    stations_view._draw_radar_clutter(game, second, (120, 120), 100)
    assert pygame.image.tobytes(first, "RGB") == pygame.image.tobytes(second, "RGB")
    assert game.opz_tracks() == []  # Bildrauschen wird nie zum Sensortrack.


def test_nato_symbol_frames_draw_for_every_affiliation_and_domain():
    for affiliation in config.NATO_AFFILIATIONS:
        for domain in ("SURFACE", "AIR", "MISSILE"):
            surface = pygame.Surface((40, 40))
            surface.fill((0, 0, 0))
            color = nato_symbols.draw_symbol(
                surface, (20, 20), affiliation, domain, selected=True)
            assert color == nato_symbols.AFFILIATION_COLORS[affiliation]
            assert pygame.mask.from_threshold(
                surface, color, threshold=(1, 1, 1, 255)).count() > 0


def test_own_airborne_helicopter_is_direct_friend_air_datalink_not_track(monkeypatch):
    symbols = []
    sensor_tracks = []

    def symbol(surface, position, affiliation, domain, *args, **kwargs):
        symbols.append((affiliation, domain, position))
        return (100, 220, 150)

    game = opz_game()
    game.air_picture._tracks.clear()
    game.helo.state = "AUF"
    game.helo.x, game.helo.y = game.ship.x + 10.0, game.ship.y
    game.helo.course = 0.0
    game.surface_radar_on = game.air_radar_on = False
    monkeypatch.setattr(nato_symbols, "draw_symbol", symbol)

    stations_view.draw_opz_view(game)

    assert [(affiliation, domain) for affiliation, domain, _ in symbols] == [
        ("FRIEND", "SURFACE"), ("FRIEND", "AIR")]
    assert sensor_tracks == []
