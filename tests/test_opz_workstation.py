"""OPZ/CIC: Track-Fokus, NATO-Symbole und Persistenz."""

from types import SimpleNamespace as NS

import pygame

from src.core import config
from src.core.game import Game
from src.core.station import Station
from src.ui import nato_symbols
from src.ui import stations_view


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


def test_up_down_selects_all_cic_domains_without_changing_asm_target():
    game = opz_game()
    observe(game, "S-1", "AIS")
    observe(game, "A-2", "FLG")
    observe(game, "M-3", "ASM")
    game.asm_sel = 2

    press(game, pygame.K_DOWN)
    assert game.opz_selected_track_id == "A-2"
    press(game, pygame.K_DOWN)
    assert game.opz_selected_track_id == "M-3"
    assert game.asm_sel == 2
    assert not game.held


def test_opz_joystick_step_uses_cic_focus_not_asm_target():
    game = opz_game()
    observe(game, "S-1", "AIS")
    observe(game, "M-3", "ASM")
    game.asm_sel = 1
    game._joy_step(1)
    assert game.opz_selected_track_id == "M-3"
    assert game.asm_sel == 1


def test_c_cycles_selected_track_affiliation():
    game = opz_game()
    observe(game, "S-1", "AIS")
    press(game, pygame.K_DOWN)
    assert game.opz_affiliation("S-1") == "UNKNOWN"
    press(game, pygame.K_c)
    assert game.opz_affiliation("S-1") == "FRIEND"
    press(game, pygame.K_c)
    assert game.opz_affiliation("S-1") == "NEUTRAL"


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
    assert game.radar_effective_range("surface") == config.RADAR_SURFACE_RANGE_NM


def test_radar_sweep_bearing_turns_clockwise():
    game = opz_game()
    game._t = 0.0
    assert game.radar_sweep_bearing() == 0.0
    game._t = 1.0
    assert game.radar_sweep_bearing() == 90.0
    game._t = 2.0
    assert game.radar_sweep_bearing() == 180.0


def test_blip_glow_follows_sweep_and_then_expires():
    game = opz_game()
    game._t = 1.0  # Sweep steht auf Ost/90 Grad.
    assert stations_view._radar_glow(game, 90.0) == 1.0
    assert 0.0 < stations_view._radar_glow(game, 0.0) < 1.0
    assert stations_view._radar_glow(game, 100.0) == 0.0


def test_weather_has_no_radar_effect_until_sea_state_five():
    game = opz_game()
    for sea_state in range(5):
        game.world.sea_state = sea_state
        assert game.radar_weather_severity() == 0.0
        assert game.radar_effective_range("surface") == config.RADAR_SURFACE_RANGE_NM
        assert game.radar_effective_range("air") == config.RADAR_AIR_RANGE_NM
    game.world.sea_state = 5
    assert game.radar_weather_severity() == .5
    assert game.radar_effective_range("surface") < config.RADAR_RANGE_NM
    game.world.sea_state = 6
    assert game.radar_weather_severity() == 1.0


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
    game._update_air_picture()
    assert {track.kind for track in game.opz_tracks()} == {"AIS"}

    game.air_picture._tracks.clear()
    game.surface_radar_on, game.air_radar_on = False, True
    game._update_air_picture()
    assert {track.kind for track in game.opz_tracks()} == {"FLG"}


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
    game.opz_selected_track_id = "S-1"
    game.opz_affiliations = {"S-1": "NEUTRAL", "bad": "INVALID"}
    game.surface_radar_on = False
    game.air_radar_on = True
    game.opz_range_nm = 10.0
    data = game.save_state()

    loaded = Game(seed=1, start_menu=False)
    loaded.load_state(data)
    assert loaded.opz_selected_track_id == "S-1"
    assert loaded.opz_affiliation("S-1") == "NEUTRAL"
    assert "bad" not in loaded.opz_affiliations
    assert not loaded.surface_radar_on and loaded.air_radar_on
    assert loaded.opz_range_nm == 10.0


def test_old_save_defaults_to_unknown_without_opz_fields():
    game = opz_game()
    data = game.save_state()
    data.pop("opz_affiliations")
    data.pop("radars")
    data["ui"].pop("opz_selected_track_id")

    loaded = Game(seed=1, start_menu=False)
    loaded.load_state(data)
    assert loaded.opz_selected_track_id is None
    assert loaded.opz_affiliations == {}
    assert loaded.surface_radar_on == data["radar_on"]
    assert loaded.air_radar_on == data["radar_on"]


def test_opz_draws_positioned_and_bearing_only_tracks():
    game = opz_game()
    observe(game, "S-1", "AIS")
    observe(game, "A-2", "FLG")
    observe(game, "M-3", "ASM")
    observe(game, "M-4", "ASM", source="HOJ", range_nm=None)
    game.opz_selected_track_id = "A-2"
    game.opz_affiliations.update({"A-2": "FRIEND", "M-3": "HOSTILE"})
    game.draw()


def test_selected_track_sidebar_is_an_evidence_ledger(monkeypatch):
    game = opz_game()
    observe(game, "S-1", "AIS")
    game.opz_selected_track_id = "S-1"
    game.opz_affiliations["S-1"] = "NEUTRAL"
    lines = []
    original = stations_view.layout.blit_line

    def record(screen, text, *args, **kwargs):
        lines.append(text)
        return original(screen, text, *args, **kwargs)

    monkeypatch.setattr(stations_view.layout, "blit_line", record)
    stations_view.draw_opz_view(game)
    assert any("Quelle" in line and "RADAR" in line for line in lines)
    assert any("Peilung" in line and "vorhanden" in line for line in lines)
    assert any("Entfernung" in line and "vorhanden" in line for line in lines)
    assert any("Kurs" in line and "vorhanden" in line for line in lines)
    assert any("Alter/Q" in line for line in lines)
    assert any("Zuordnung" in line and "Neutral" in line for line in lines)


def test_coast_reflections_are_requested_only_with_surface_radar(monkeypatch):
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
    assert calls == []


def test_scope_hides_positioned_tracks_outside_selected_range(monkeypatch):
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
    assert len(calls) == 1  # nur eigenes Schiff
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
    lines = []
    original_symbol = nato_symbols.draw_symbol
    original_line = stations_view.layout.blit_line

    def record_symbol(*args, **kwargs):
        symbols.append(args[2:4])
        return original_symbol(*args, **kwargs)

    def record_line(screen, text, *args, **kwargs):
        lines.append(text)
        return original_line(screen, text, *args, **kwargs)

    monkeypatch.setattr(nato_symbols, "draw_symbol", record_symbol)
    monkeypatch.setattr(stations_view.layout, "blit_line", record_line)
    stations_view.draw_opz_view(game)

    assert symbols == [("FRIEND", "SURFACE")]
    footer = next(line for line in lines if "PgUp/PgDn" in line)
    assert "BEREICH 20 NM" in footer and "Rad ueber PPI" in footer
    assert all(str(scale) in footer for scale in (10, 20, 40, 80, 120))


def test_opz_ppi_hit_rect_is_bounded_at_1280x720(monkeypatch):
    monkeypatch.setattr(config, "STATION_RECT", (0, 30, 1280, 510))
    ppi = stations_view.opz_ppi_rect()
    assert pygame.Rect(0, 0, 1280, 720).contains(ppi)
    assert ppi.right <= int(config.STATION_RECT[2] * .66)


def test_contact_scale_tracks_selected_range(monkeypatch):
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

    assert near_displacement == 2 * far_displacement


def test_underwater_tracks_have_table_codes_and_affiliation_colors(monkeypatch):
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

    assert [code for code in (" UBT ", " TOR ")
            if any(code in text for text, _ in rows)] == [" UBT ", " TOR "]
    assert {color for _, color in rows} == {
        nato_symbols.AFFILIATION_COLORS["FRIEND"],
        nato_symbols.AFFILIATION_COLORS["HOSTILE"],
    }
    assert (stations_view.OPZ_DOMAIN_COLORS["SUBSURFACE"] ==
            config.COLOR_CONTACT_UBOOT)
    assert (stations_view.OPZ_DOMAIN_COLORS["UNDERWATER_WEAPON"] ==
            config.COLOR_DANGER)


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
    monkeypatch.setattr(config, "STATION_RECT", (0, 30, 1280, 510))
    symbols = []
    sensor_tracks = []

    def symbol(surface, position, affiliation, domain, *args, **kwargs):
        symbols.append((affiliation, domain, position))
        return (100, 220, 150)

    game = NS(
        screen=pygame.Surface((1280, 720)), opz_range_nm=40.0,
        ship=NS(x=100.0, y=100.0, course=0.0),
        helo=NS(airborne=True, x=110.0, y=100.0),
        damage=NS(station_down=lambda station: False),
        surface_radar_on=False, air_radar_on=False,
        radar_tracks=lambda: sensor_tracks,
        opz_selected_track_id=None, asm_tracks=lambda: [],
        radar_weather_severity=lambda: 0.0,
        world=NS(sea_state=2), vls_cells=8, chaff_cd=0.0,
        selected_opz_track=lambda: None, ciws_ammo=100,
    )
    monkeypatch.setattr(nato_symbols, "draw_symbol", symbol)

    stations_view.draw_opz_view(game)

    assert [(affiliation, domain) for affiliation, domain, _ in symbols] == [
        ("FRIEND", "SURFACE"), ("FRIEND", "AIR")]
    assert sensor_tracks == []
