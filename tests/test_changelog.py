"""The READMEs carry only the latest release; the history lives in the changelogs."""

from pathlib import Path

from tools import changelog_notes

ROOT = Path(__file__).resolve().parents[1]


def test_readmes_show_only_the_current_release_and_changelogs_lead_with_it():
    assert changelog_notes.check(ROOT) == []


def test_changelogs_have_the_same_releases_in_both_languages():
    en = changelog_notes.versions((ROOT / "CHANGELOG.md").read_text(encoding="utf-8"))
    de = changelog_notes.versions((ROOT / "CHANGELOG.de.md").read_text(encoding="utf-8"))
    assert en == de and "1.0.0" in en


def test_release_notes_are_one_changelog_entry():
    text = "# Changelog\n\n## 1.0.1\n\nNew.\n\n## 1.0.0\n\nOld.\n"
    assert changelog_notes.entry(text, "1.0.1") == "New."
    assert changelog_notes.entry(text, "1.0.0") == "Old."
