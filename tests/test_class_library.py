"""Sonar class library: catalog classes sorted by fit to the operator's own
line marks, on both sonar rooms, never from the hidden contact."""

import sys
from pathlib import Path

from src.commander.projections import _sonar
from src.core.game import Game
from src.data.catalog import CATALOG
from src.sonar import class_library
from src.ui.contact_analyzer import ContactAnalyzer

sys.path.insert(0, str(Path(__file__).parent))
from test_opfor_sub import _crewed  # noqa: E402


def _signature(key):
    return next(sig for sig in CATALOG.acoustic_profiles if sig.key == key)


def _marks_for(signature):
    """Marks an operator would set on a class running mid-range."""
    rpm = sum(signature.rpm_range) / 2.0
    shaft = rpm / 60.0
    blades = signature.blade_counts[0]
    tonal = sum(signature.tonal_band_hz) / 2.0
    return shaft, shaft * blades, tonal


def test_no_marks_no_library():
    assert class_library.rank(CATALOG.acoustic_profiles) == []
    assert class_library.marks_count(None, None, None) == 0
    assert class_library.marks_count(float("nan"), 0.0, -1.0) == 0


def test_the_true_class_fits_fully_and_ranks_on_top():
    signature = _signature("ssn")
    shaft, blade, tonal = _marks_for(signature)
    fit, parts = class_library.grade(signature, shaft, blade, tonal)
    assert fit == 1.0 and set(parts) == {"rpm", "blades", "tonal"}
    ranked = class_library.rank(CATALOG.acoustic_profiles, shaft, blade, tonal)
    assert ranked[0][1] == 1.0
    assert "ssn" in {sig.key for sig, fit in ranked[:3]}
    fits = [fit for _sig, fit in ranked]
    assert fits == sorted(fits, reverse=True)
    assert len(ranked) <= class_library.MAX_ROWS


def test_wrong_blade_count_and_far_rpm_lower_the_fit():
    signature = _signature("diesel_alt")          # 4 or 5 blades, 90-220 rpm
    shaft = 150.0 / 60.0
    assert class_library.grade(signature, shaft, shaft * 7)[1]["blades"] == 0.0
    assert class_library.grade(signature, shaft, shaft * 4.5)[1]["blades"] == 0.0
    far = class_library.grade(signature, 600.0 / 60.0)[0]
    near = class_library.grade(signature, 240.0 / 60.0)[0]
    assert far == 0.0 and 0.0 < near < 1.0


def test_ranking_is_deterministic_and_stable():
    marks = (2.0, 10.0, 15.0)
    first = class_library.rank(CATALOG.acoustic_profiles, *marks, limit=1000)
    second = class_library.rank(tuple(reversed(CATALOG.acoustic_profiles)), *marks, limit=1000)
    assert [(sig.key, fit) for sig, fit in first] == [(sig.key, fit) for sig, fit in second]


def test_frigate_sonar_page_and_analyzer_use_the_marks():
    game = Game(seed=4, start_menu=False, audio_enabled=False)
    assert game.sonar_class_library() == [] and game.sonar_library_marks() == 0
    shaft, blade, tonal = _marks_for(_signature("aip_modern"))
    game.sonar_tools.shaft_hz, game.sonar_tools.blade_hz = shaft, blade
    game.sonar_harmonic_hz = tonal
    assert game.sonar_library_marks() == 3
    ranked = game.sonar_class_library(3)
    assert len(ranked) == 3 and ranked[0][1] == 1.0
    fits = game._library_fits()
    analyzer = ContactAnalyzer(fits=fits)
    keys = [profile["key"] for profile in analyzer.profiles]
    known = [fits[key] for key in keys if key in fits]
    assert known == sorted(known, reverse=True)
    assert analyzer._list_labels()[0].strip().startswith("100%")
    assert ContactAnalyzer()._list_labels()[0][0] != " "
    tools = _sonar(game, [], None, None, {})["settings"]["tools"]
    assert tools["library_marks"] == 3 and len(tools["library"]) == 3
    assert set(tools["library"][0]) == {"name", "fit"}


def test_the_crewed_boat_sonar_has_its_own_library():
    game, _server, _bridge = _crewed(seed=78)
    boat = game.opfor
    shaft, blade, tonal = _marks_for(_signature("warship_01")
                                     if any(sig.key == "warship_01"
                                            for sig in CATALOG.acoustic_profiles)
                                     else CATALOG.acoustic_profiles[5])
    with game.sonar_perspective(boat.station):
        game.sonar_tools.shaft_hz, game.sonar_tools.blade_hz = shaft, blade
        game.sonar_harmonic_hz = tonal
        assert game.sonar_library_marks() == 3
        assert game.sonar_class_library(3)[0][1] == 1.0
    # The frigate's own marks are untouched by the boat's.
    assert game.sonar_library_marks() == 0
