from types import SimpleNamespace as NS

import pygame
import pytest

from src.core.i18n import Translator, translation_scope
from src.ui import layout, map_view, observations, sonar_view, stations_view, weapons_view


def test_positioned_observation_has_one_canonical_geometry_in_all_presentations():
    ship = NS(x=5.0, y=5.0, course=10.0)
    track = {"x": 10.0, "y": 0.0, "bearing": 270.0, "range_nm": 99.0,
             "source": "RADAR-S"}

    assert observations.position(track) == (10.0, 0.0)
    assert observations.bearing(track, ship) == pytest.approx(45.0)
    assert observations.range_nm(track, ship) == pytest.approx(2.0 ** .5 * 5.0)
    assert observations.format_bearing(track, ship) == "045.0"
    assert "045.0" in observations.format_bearing_pair(track, ship)


@pytest.mark.parametrize("source,uncertainty", [
    ("SONAR-BRG", 2.4),
    ("ESM", None),
    ("HFDF", None),
])
def test_passive_bearing_only_precision_matches_uncertainty(source, uncertainty):
    track = NS(bearing=12.64, source=source,
               bearing_uncertainty_deg=uncertainty)

    assert observations.format_bearing(track) == "013"
    assert "013" in observations.format_bearing_pair(
        track, NS(x=0.0, y=0.0, course=0.0))


def test_sub_half_degree_passive_uncertainty_supports_tenths():
    contact = NS(passive_bearing=12.64, bearing=200.0,
                 bearing_uncertainty_deg=.3, range_est=None)
    assert observations.format_bearing(contact) == "012.6"


@pytest.mark.parametrize("value,expected", [(359.6, "000"), (359.96, "000.0")])
def test_formatted_bearing_wraps_after_rounding(value, expected):
    uncertainty = 2.0 if expected == "000" else .3
    contact = NS(passive_bearing=value, bearing_uncertainty_deg=uncertainty)
    assert observations.format_bearing(contact) == expected


def test_sensor_track_uses_published_sonar_uncertainty():
    track = NS(bearing=42.4, source="SONAR-BRG",
               bearing_uncertainty_deg=1.7)
    assert observations.bearing_uncertainty(track) == 1.7
    assert observations.format_bearing(track) == "042"


def test_bearing_only_views_share_the_same_stabilized_value():
    contact = NS(passive_bearing=87.6, bearing=240.0, range_est=None,
                 bearing_uncertainty_deg=2.0)
    ship = NS(x=0.0, y=0.0, course=0.0)

    assert map_view.observed_bearing(contact) == 87.6
    assert sonar_view._observed_bearing(contact) == 87.6
    assert weapons_view._display_bearing(contact, ship) == 87.6
    assert stations_view._displayed_bearing(contact, ship) == 87.6
    assert observations.format_bearing(contact) == "088"


def test_sonar_sidebar_uses_positioned_bearing_not_passive_bearing(monkeypatch):
    contact = NS(id=4, observed_x=10.0, observed_y=0.0,
                 passive_bearing=240.0, bearing=240.0, range_est=10.0,
                 bearing_uncertainty_deg=2.0, player_class=None,
                 snr=5.0, confidence=.8, last_seen=9.0)
    game = NS(screen=pygame.Surface((1280, 720)),
              ship=NS(x=5.0, y=5.0, course=0.0), sim_t=10.0,
              sonar=NS(active_contacts=lambda: [contact]),
              selected_contact=contact)
    rendered = []
    monkeypatch.setattr(
        sonar_view, "_text",
        lambda screen, text, *args, **kwargs: rendered.append(text))

    sonar_view._draw_contacts(game, pygame.Rect(900, 340, 350, 150))

    assert any("045.0" in text for text in rendered)
    assert not any("240" in text for text in rendered)


def test_raw_active_and_tma_bearings_keep_tenths():
    # Raw evidence passes numeric values directly to the layout formatter.
    assert "012.6" in layout.format_bearing_pair(12.64, 0.0)


def test_sonar_contact_never_falls_through_to_truth_position():
    class ContactLike:
        range_est = None
        passive_bearing = 123.0

        def __getattr__(self, name):
            if name in {"x", "y", "target", "truth"}:
                pytest.fail(f"read hidden truth field {name}")
            raise AttributeError(name)

    contact = ContactLike()
    assert observations.position(contact) == (None, None)
    assert observations.bearing(contact, NS(x=0.0, y=0.0)) == 123.0


def test_observation_and_fix_ages_are_distinct_and_localized():
    track = NS(last_seen=98.0, position_seen=75.0)
    assert observations.observation_age(track, 100.0) == 2.0
    assert observations.position_age(track, 100.0) == 25.0
    for language, words in (("en", ("Observation", "Fix")),
                            ("de", ("Beobachtungsalter", "Fixalter"))):
        with translation_scope(Translator(language).t):
            text = layout.localize(layout.message(
                "observation.ages", observation_age="2", fix_age="25"))
        assert all(word in text for word in words)


@pytest.mark.parametrize("language", ["en", "de"])
def test_new_age_and_uncertainty_tooltip_text_is_bounded_at_large_text(language):
    pygame.font.init()
    layout.configure_for(large_text=True)
    with translation_scope(Translator(language).t):
        payload = layout.tooltip_payload(
            layout.message("sonar.tooltip.contact_title", contact="07"),
            layout.message("observation.bearing_uncertainty", uncertainty="12.3"),
            layout.message("observation.ages", observation_age="999",
                           fix_age="999"))
        rect, lines = layout.tooltip_rect(payload, (1279, 719))
    assert pygame.Rect(0, 0, 1280, 720).contains(rect)
    assert lines
    layout.configure_for(large_text=False)
