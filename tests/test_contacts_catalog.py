"""Kontakt-Katalog (Kontakt-DB): Vollstaendigkeit, JSON-Load, Ranking."""

from importlib import resources

from src.audio import database
from src.data import catalog
from src.data.catalog import CATALOG, load_catalog


def test_catalog_completeness():
    assert len(CATALOG.subs) == 23
    for key in ("diesel_alt", "aip_modern", "ssn"):
        assert key in CATALOG.subs
    assert len(CATALOG.hostile_surfaces) == 25
    assert len(CATALOG.civilian_surfaces) == 55
    assert set(CATALOG.aircraft) >= {"mil_patrol", "civil_transit"}
    assert set(CATALOG.animals) == {"whale", "fish_school", "jellyfish"}
    assert "enemy_torp" in CATALOG.torpedoes
    assert "decoy" in CATALOG.decoys
    assert len(CATALOG.acoustic_profiles) == 106


def test_builtin_catalog_loads_from_package_resources():
    loaded = load_catalog()
    assert loaded.db_source == "contacts"
    contact_files = resources.files("data.contacts")
    assert (contact_files / "subs.json").is_file()
    assert (contact_files / "acoustics.json").is_file()
    assert catalog.build_catalog().subs == loaded.subs
    for key in ("diesel_alt", "ssn"):
        a, b = CATALOG.acoustic_by_key[key], loaded.acoustic_by_key[key]
        assert (a.blade_counts, a.rpm_range, a.tonal_band_hz, a.broadband,
                a.cavitation_tendency) == \
               (b.blade_counts, b.rpm_range, b.tonal_band_hz, b.broadband,
                b.cavitation_tendency)


def test_invalid_external_catalog_falls_back_to_packaged_data(tmp_path):
    loaded = load_catalog(tmp_path, quiet=True)
    assert loaded.db_source == "contacts"
    assert loaded.subs == CATALOG.subs


def test_broadband_bands_are_within_sonar_range():
    for profile in CATALOG.acoustic_profiles:
        if profile.broadband:
            level, low, high = profile.broadband
            assert 0.0 <= level <= 1.0
            assert 0.0 < low < high <= 400.0


def test_rank_signatures_prefers_matching_sub_profile():
    # AIP-Messung: Blattfrequenz 10 Hz, 120 U/min, Tonales 25 Hz
    ranked = database.rank_signatures(10.0, 120.0, 25.0, 0.2)
    assert ranked
    top_sig, top_score = ranked[0]
    assert top_sig.category == "U_BOOT"
    assert top_score >= 0.95
    assert "diesel_alt" not in {sig.key for sig, _ in ranked[:3]}


def test_rank_signatures_scores_enemy_torpedo_for_sweep():
    # Torpedo-Messung: Blattfrequenz 60 Hz (Unterton 45–75 Hz), Tonales in
    # 90–150 Hz (Kreisch), hohe Kavitations-Anzeige. Zivile Bandbreiten
    # ueberlappen sich stark, daher gilt: Tonales + Kavitation sichern
    # einen brauchbaren Score, und das Tonalfenster deckt 120 Hz ab.
    ranked = {sig.key: score for sig, score in
              database.rank_signatures(60.0, None, 120.0, 0.9)}
    sig = CATALOG.acoustic_by_key["enemy_torp"]
    assert sig.tonal_band_hz[0] <= 120.0 <= sig.tonal_band_hz[1]
    assert ranked["enemy_torp"] >= 0.30


def test_civilian_signatures_are_subset_of_profiles():
    civ = {p.key for p in CATALOG.civilian_signatures}
    prof = {p.key for p in CATALOG.acoustic_profiles}
    assert civ <= prof


def test_database_shim_exports():
    assert database.TARGET_DATABASE is CATALOG.acoustic_profiles
    assert database.SIGNATURES_BY_KEY is CATALOG.acoustic_by_key
    assert database.CIVILIAN_SIGNATURES is CATALOG.civilian_signatures
    assert database.signature_for_key("ssn") is CATALOG.acoustic_by_key["ssn"]
