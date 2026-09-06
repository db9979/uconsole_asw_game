"""Headless instrument tests using observations, never world targets."""

from types import SimpleNamespace as NS

import numpy as np
import pygame
import pytest

from src.core import config
from src.ui import sonar_view as view


@pytest.fixture
def game(monkeypatch):
    pygame.font.init()
    monkeypatch.setattr(config, "STATION_RECT", (0, 30, 1280, 510))
    view._WATERFALL_CACHE.clear()
    sonar = NS(broadband_history=[], lofar_history=[], history_times=[],
               lofar_times=[], lofar_bearings=[], listen_bearing=30.,
               beam_width_deg=12., focus_locked=False, gain_db=0.,
               band_low_hz=0., band_high_hz=300., notch_enabled=False,
               peak_hold=False, _tracks={}, signature_candidates=[],
               demon_analysis=None, receiver=NS(sequence=1, spectrum=[0.] * 110,
                                               peaks=[], demon_spectrum=[0.] * 80),
               active_contacts=lambda: [])
    return NS(screen=pygame.Surface((1280, 720)), sonar=sonar, sonar_page=0,
              selected_contact=None, sim_t=100., ship=NS(speed=0.),
              audio=NS(available=False), sonar_audio_enabled=False, sonar_volume=.5)


def test_waterfall_newest_top_and_frequency_increases_right():
    surface = view.waterfall_surface([[1., 0.], [0., .5]], 20, 20)
    assert surface.get_at((0, 0))[:3] == view.NAVY
    assert surface.get_at((19, 0)).g > view.NAVY[1]
    assert surface.get_at((0, 19))[:3] == view.CYAN
    assert surface.get_at((19, 19))[:3] == view.NAVY


@pytest.mark.parametrize("rows", [[], [[0.] * 180] * 4])
def test_no_signal_does_not_invent_noise(rows):
    pixels = pygame.surfarray.array3d(view.waterfall_surface(rows, 120, 60))
    assert np.all(pixels == view.NAVY)


def test_gain_changes_intensity_not_orientation():
    rows = [[0., .1], [.2, 0.]]
    normal = view.waterfall_surface(rows, 20, 20)
    gained = view.waterfall_surface(rows, 20, 20, 6.)
    assert gained.get_at((0, 0)).g > normal.get_at((0, 0)).g
    assert gained.get_at((19, 0))[:3] == view.NAVY


def test_broadband_interpolation_is_circular_and_preserves_real_bins():
    row = np.zeros(180)
    row[0], row[-1] = 1.0, .5
    plotted = view._circular_broadband(row, 359)
    assert plotted[0] == pytest.approx(1.0)
    assert plotted[-1] == pytest.approx(1.0)
    assert plotted[-2] > .5
    assert np.max(plotted[2:350]) < 1.0


def test_broadband_tooltip_snaps_to_two_degree_source_bin(game):
    game.sonar.broadband_history = [list(np.arange(180) / 180.0)]
    station = pygame.Rect(config.STATION_RECT)
    body = pygame.Rect(station.x + 12, station.y + 73,
                       station.w - 24, station.h - 124)
    rail_w = min(350, max(240, round(body.w * .28)))
    main = pygame.Rect(body.x, body.y, body.w - rail_w - 12, body.h)
    plot = pygame.Rect(main.x + 57, main.y + 61, main.w - 83, main.h - 108)
    payload = view.sonar_hit_target(game, (plot.right - 1, plot.centery))
    assert payload["id"] == "sonar:broadband:0.0"
    assert any("2-degree" in line and "180 bins" in line
               for line in payload["lines"])


@pytest.mark.parametrize("index", [20, 50, 90, 109])
def test_lofar_nonlinear_bins_land_at_true_linear_hz(index):
    row = np.zeros(110)
    row[index] = 1
    linear = view._linear_lofar(row, 1201)
    peak_hz = np.argmax(linear) * 300 / 1200
    assert peak_hz == pytest.approx(config.lofar_bin_freq(index), abs=.5)


@pytest.mark.parametrize("page", range(6))
def test_all_pages_clip_to_station_and_restore_clip(game, page):
    game.sonar_page = page
    game.screen.fill((201, 12, 93))
    clip = pygame.Rect(4, 2, 1268, 710)
    game.screen.set_clip(clip)
    view.draw_sonar_view(game)
    assert game.screen.get_clip() == clip
    pixels = pygame.surfarray.array3d(game.screen)
    assert np.all(pixels[:, :30] == (201, 12, 93))
    assert np.all(pixels[:, 540:] == (201, 12, 93))
    assert np.all(pixels[:4] == (201, 12, 93))
    assert tuple(pixels[20, 110]) == view.PANEL


def test_unfocused_noise_is_displayed_and_render_is_read_only(game):
    game.sonar.broadband_history = [[.08] * 180, [.4] * 180]
    before = [row[:] for row in game.sonar.broadband_history]
    keys = set(vars(game.sonar))
    rect = pygame.Rect(0, 0, 180, 80)
    view._waterfall(game, 0, rect)
    assert game.screen.get_at((90, 0)).g > game.screen.get_at((90, 79)).g
    assert game.sonar.broadband_history == before
    assert set(vars(game.sonar)) == keys
    assert game.selected_contact is None


def test_lofar_receiver_fallback_without_history_or_contact(game):
    game.sonar.receiver.spectrum[90] = .7
    rect = pygame.Rect(0, 0, 601, 60)
    view._waterfall(game, 1, rect)
    assert game.screen.get_at((405, 20)).g > 120


def test_cache_reuses_bitmap_and_invalidates_history_controls_size_sequence(game):
    game.sonar.broadband_history = [[.1] * 180]
    rect = pygame.Rect(0, 0, 180, 80)
    view._waterfall(game, 0, rect)
    first = next(iter(view._WATERFALL_CACHE.values()))[0]
    view._waterfall(game, 0, rect)
    assert len(view._WATERFALL_CACHE) == 1
    assert next(iter(view._WATERFALL_CACHE.values()))[0] is first
    game.sonar.broadband_history[0][0] = .8
    game.sonar.receiver.sequence += 1
    view._waterfall(game, 0, rect)
    assert len(view._WATERFALL_CACHE) == 2
    game.sonar.gain_db = 6
    view._waterfall(game, 0, rect)
    assert len(view._WATERFALL_CACHE) == 3
    view._waterfall(game, 0, rect.inflate(1, 1))
    assert len(view._WATERFALL_CACHE) == 4
    game.sonar.receiver.sequence += 1
    view._waterfall(game, 0, rect)
    assert len(view._WATERFALL_CACHE) == 4
    assert all(value[0] is not first for value in view._WATERFALL_CACHE.values())


def test_peak_hold_overlays_max_but_does_not_freeze_waterfall(game, monkeypatch):
    game.sonar.lofar_history = [[.1] * 110, [.7] * 110]
    panel = pygame.Rect(0, 0, 890, 386)
    traces = []
    monkeypatch.setattr(view, "_trace", lambda screen, rect, values, color=view.CYAN:
                        traces.append((np.asarray(values), color)))
    view._draw_waterfall(game, panel, 1)
    before = pygame.surfarray.array3d(game.screen)[57:864, 127:278].copy()
    game.sonar.peak_hold = True
    view._draw_waterfall(game, panel, 1)
    after = pygame.surfarray.array3d(game.screen)[57:864, 127:278]
    np.testing.assert_array_equal(before, after)
    assert traces[-1][1] == view.AMBER
    assert np.allclose(traces[-1][0], .7)
    game.sonar.peak_spectrum = [.9] * 110
    view._draw_waterfall(game, panel, 1)
    assert np.allclose(traces[-1][0], .9)


def test_tma_wrap_uses_observed_track_only(game):
    points = [NS(t=t, bearing=b) for t, b in [(0, 358), (10, 1), (20, 3)]]
    times, bearings = view._bearing_series(points)
    np.testing.assert_allclose(times, [0, 10, 20])
    np.testing.assert_allclose(bearings, [358, 361, 363])
    game.selected_contact = NS(id=1, target_id=99)
    game.sonar._tracks[99] = NS(pts=points)
    game.sonar_page = 3
    # The fake has no world, target, subs, position or truth-derived signature.
    view.draw_sonar_view(game)


def test_tma_summary_reports_observed_rate_legs_and_clear_states():
    short = NS(pts=[NS(t=0., bearing=358., fcourse=0.),
                    NS(t=20., bearing=0., fcourse=0.)])
    summary = view.tma_observation_summary(short, 20.)
    assert summary["state"] == "ZU WENIG HISTORIE"
    assert summary["rate"] == pytest.approx(6.0)
    assert summary["legs"] == 1

    weak = NS(pts=[NS(t=t, bearing=90. + t / 60., fcourse=0.)
                   for t in (0., 60., 120., 180.)])
    assert view.tma_observation_summary(weak, 180.)["state"] == "SCHWACHE GEOMETRIE"

    useful = NS(pts=[NS(t=t, bearing=90. + t / 60., fcourse=course)
                     for t, course in ((0., 0.), (60., 0.), (120., 20.), (180., 20.))])
    summary = view.tma_observation_summary(useful, 180., solution_quality=.1)
    assert summary["state"] == "KONVERGIEREND"
    assert summary["geometry"] == "BRAUCHBAR"
    assert summary["legs"] == 2
    assert view.tma_observation_summary(useful, 211.)["state"] == "VERALTET"


def test_contact_window_keeps_last_selection_visible(game, monkeypatch):
    contacts = [NS(id=i, bearing=i * 10) for i in range(1, 21)]
    game.sonar.active_contacts = lambda: contacts
    game.selected_contact = contacts[-1]
    texts = []
    monkeypatch.setattr(view, "_text", lambda screen, text, *a, **kw: texts.append(text))
    view._draw_contacts(game, pygame.Rect(900, 340, 350, 150))
    assert any("K20" in text for text in texts)
    assert not any("K01" in text for text in texts)
    assert any("/20" in text for text in texts)
    assert game.selected_contact is contacts[-1]


def test_demon_requires_envelope_evidence_and_labels_hypotheses(game, monkeypatch):
    game.sonar.demon_analysis = dict(blade_rate_hz=20., confidence=.8)
    game.sonar.signature_candidates = [(NS(label=f"Candidate {i}"), .9 - i * .1)
                                       for i in range(3)]
    texts = []
    monkeypatch.setattr(view, "_text", lambda screen, text, *a, **kw: texts.append(text))
    rect = pygame.Rect(900, 100, 350, 254)
    view._draw_details(game, rect, 2)
    assert not any("Candidate" in text for text in texts)
    game.sonar.receiver.demon_spectrum[19] = .8
    texts.clear()
    view._draw_details(game, rect, 2)
    assert sum("Candidate" in text for text in texts) == 3
    assert any("REFERENZ" in text for text in texts)
    assert any("OBSERVED" in text for text in texts)
    assert any("ALTERNATIVE" in text for text in texts)
    assert any("3: 400 RPM" in text for text in texts)
    assert any("4: 300 RPM" in text for text in texts)


def test_minimal_preintegration_fields_render(game):
    game.sonar = NS(active_contacts=lambda: [])
    del game.sonar_page
    view.draw_sonar_view(game)
    for page in range(1, 6):
        game.sonar_page = page
        view.draw_sonar_view(game)


def test_station_layout_has_large_plot_and_readable_contact_window(game, monkeypatch):
    panels = []
    contact_panels = []
    monkeypatch.setattr(view, "_draw_waterfall", lambda game, rect, page: panels.append(rect))
    monkeypatch.setattr(view, "_draw_contacts", lambda game, rect: contact_panels.append(rect))
    view.draw_sonar_view(game)
    assert panels[0].w >= 850
    assert panels[0].h >= 380
    assert contact_panels[0].w == 350
    assert (contact_panels[0].h - 33) // 43 >= 3


def test_station_header_uses_divided_status_groups_without_microtext(game, monkeypatch):
    drawn = []
    monkeypatch.setattr(view, "_text", lambda screen, text, rect, color=view.TEXT,
                        size=14, align="left": drawn.append((text, pygame.Rect(rect), size)))

    view.draw_sonar_view(game)

    groups = [item for item in drawn if item[0].startswith(("ARRAY", "LISTENING", "FILTER"))]
    assert [item[0].split()[0] for item in groups] == ["ARRAY", "LISTENING", "FILTER"]
    assert len({item[1].x for item in groups}) == 3
    assert min(size for _, _, size in drawn) >= 12


def test_demon_chart_uses_actual_envelope_bins_on_hz_axis(game, monkeypatch):
    game.sonar.receiver.demon_spectrum[19] = .8
    traces = []
    monkeypatch.setattr(view, "_trace", lambda screen, rect, values, *args:
                        traces.append(np.asarray(values)))
    view._draw_demon(game, pygame.Rect(0, 0, 890, 386))
    assert len(traces) == 1
    assert len(traces[0]) == 81
    assert np.argmax(traces[0]) == 20
    assert traces[0][20] == .8


def test_drawing_never_reads_contact_identity_or_world_truth(game):
    class ObservedContact:
        id = 1
        target_id = 42
        bearing = 90.
        player_class = None

        def __getattr__(self, name):
            if name in {"kind", "signature", "target", "x", "y", "depth", "display_label"}:
                pytest.fail(f"Renderer read truth-derived field: {name}")
            raise AttributeError(name)

    game.selected_contact = ObservedContact()
    game.sonar.active_contacts = lambda: [game.selected_contact]
    for page in range(6):
        game.sonar_page = page
        view.draw_sonar_view(game)


def test_environment_page_uses_measured_profile(game, monkeypatch):
    game.sonar.bt_profile = {
        "t": 90.0, "thermocline_m": 80.0, "water_depth_m": 300.0,
        "sea_state": 3, "depths_m": [0.0, 80.0, 300.0],
        "speeds_m_s": [1504.0, 1502.5, 1505.0],
        "cz_bands_nm": [[40.0, 70.0]],
    }
    game.sonar.towed_depth_m = 95.0
    game.sonar.towed_depth_target_m = 110.0
    texts = []
    monkeypatch.setattr(view, "_text", lambda screen, text, *args, **kwargs:
                        texts.append(text))
    game.sonar_page = 4
    view.draw_sonar_view(game)
    assert any("Thermocline ~80" in text for text in texts)
    assert any("95m -> 110m" in text for text in texts)
    assert any("CZ prediction 40-70" in text for text in texts)


def test_active_history_is_age_bounded_copied_and_does_not_read_contacts(game):
    game.sim_t = 200.0
    source = [
        dict(t=70., contact_id=1, bearing=10., range_nm=2., snr_db=4.),
        dict(t=100., contact_id=2, bearing=20., range_nm=3., snr_db=5.),
        dict(t=199., contact_id=3, bearing=30., range_nm=4.,
             range_sigma_nm=.2, depth_m=80., depth_sigma_m=6., snr_db=8., mode="BOW"),
    ]
    game.sonar.echo_history = source
    echoes = view.active_echoes(game.sonar, game.sim_t)
    assert [echo["contact_id"] for echo in echoes] == [2, 3]
    assert echoes[-1]["age_s"] == 1
    assert "age_s" not in source[-1]

    game.sonar.active_contacts = lambda: pytest.fail("ACTIVE read live contacts")
    game.selected_contact = NS(
        __getattr__=lambda self, name: pytest.fail(f"ACTIVE read contact {name}"))
    game.sonar_page = 5
    view.draw_sonar_view(game)


def test_active_page_draws_range_uncertainty_and_readiness(game, monkeypatch):
    game.sim_t = 50.
    game.sonar.echo_history = [
        dict(t=49., contact_id=7, bearing=45., range_nm=8.,
             range_sigma_nm=.4, depth_m=120., depth_sigma_m=9.,
             snr_db=10., mode="BOW")]
    game.sonar.ping_ready = False
    game.sonar.ping_cooldown_remaining = 17.
    texts, amber_lines = [], []
    monkeypatch.setattr(view, "_text", lambda screen, text, *args, **kwargs:
                        texts.append(text))
    original_line = pygame.draw.line

    def record_line(surface, color, start, end, width=1):
        if color == view.AMBER:
            amber_lines.append((start, end, width))
        return original_line(surface, color, start, end, width)

    monkeypatch.setattr(pygame.draw, "line", record_line)
    game.sonar_page = 5
    view.draw_sonar_view(game)
    assert any("PING 17s" in text for text in texts)
    assert any("8.00 +/- 0.40 NM" in text for text in texts)
    assert len(amber_lines) >= 2  # A-scope interval and radial interval.


@pytest.mark.parametrize("page", range(6))
def test_every_sonar_page_shows_tas_payout_and_stability(game, page, monkeypatch):
    game.sonar.tow_status = lambda speed=None: dict(
        state="DEPLOYING", payout=.42, payout_percent=42., available=False,
        handling_ok=False, performance=.25, depth_m=50., depth_target_m=70.)
    texts = []
    monkeypatch.setattr(view, "_text", lambda screen, text, *args, **kwargs:
                        texts.append(text))
    game.sonar_page = page
    view.draw_sonar_view(game)
    assert any("TAS DEPLOYING 42% STABILITY 25% PAUSE" in text
               for text in texts)


def test_sonar_view_accepts_optional_translator(game, monkeypatch):
    texts = []
    monkeypatch.setattr(view, "_text", lambda screen, text, *args, **kwargs:
                        texts.append(text))
    game.sonar_page = 5
    view.draw_sonar_view(game, lambda text: f"TR:{text}")
    assert "TR:station.sonar / TR:enum.sonar_page.active" in texts
    assert "TR:ACTIVE / ECHO-AUSWERTUNG" in texts
