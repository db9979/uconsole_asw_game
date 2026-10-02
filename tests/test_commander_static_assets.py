"""The Remote Crew static asset manifest (src/commander/assets.py)."""
import hashlib
import re

import pytest

from commander_web import ASSET_DIR, ROOT, tree_files
from src.commander.assets import MIME_TYPES, static_assets, tree_assets


def _write(path, data=b"x"):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def _fixture(root):
    for name in ("index.html", "lookout.html", "sonar-audio-worklet.js", "noise-mic.js",
                 "manual.css", "admin.html", "admin.js", "admin.css", "voice.js", "voice-worklet.js"):
        _write(root / name, name.encode())


def test_trees_are_served_with_allowlisted_types_only(tmp_path):
    _fixture(tmp_path)
    _write(tmp_path / "js" / "net" / "request.js", b"export {}")
    _write(tmp_path / "css" / "tokens.css", b":root{}")
    _write(tmp_path / "fonts" / "a.woff2", b"wOF2")
    _write(tmp_path / "fonts" / "ofl-a.txt", b"OFL")
    _write(tmp_path / "js" / "notes.md", b"never served")
    _write(tmp_path / "js" / "image.svg", b"<svg/>")
    _write(tmp_path / "js" / "__pycache__" / "x.js", b"skip")
    _write(tmp_path / "images" / "x.css", b"not a tree")
    assets = static_assets(False, tmp_path)
    assert assets["/js/net/request.js"] == (MIME_TYPES[".js"], b"export {}")
    assert assets["/css/tokens.css"][0] == "text/css; charset=utf-8"
    assert assets["/fonts/a.woff2"] == ("font/woff2", b"wOF2")
    assert assets["/fonts/ofl-a.txt"][0].startswith("text/plain")
    assert not any(route.endswith((".md", ".svg")) or "__pycache__" in route
                   or route.startswith("/images") for route in assets)
    # The local crew listener has no admin/voice routes; the web host has both.
    assert "/admin" not in assets and "/voice.js" not in assets
    assert {"/admin", "/voice.js"} <= static_assets(True, tmp_path).keys()


@pytest.mark.parametrize("bad", ["Upper/x.js", "a b/x.js", ".hidden/x.js", "a/b/c/d/x.js"])
def test_unexpected_directories_are_rejected(tmp_path, bad):
    _write(tmp_path / "js" / bad)
    with pytest.raises(ValueError):
        tree_assets(tmp_path)


def test_packaged_trees_match_the_manifest():
    served = tree_assets()
    assert {f"/{path.as_posix()}" for path in tree_files()
            if path.suffix in MIME_TYPES} == set(served)
    assert served["/fonts/inter-variable.woff2"][0] == "font/woff2"


def test_font_files_match_documented_provenance():
    notices = (ROOT / "THIRD_PARTY_NOTICES.md").read_text(encoding="utf-8")
    fonts = sorted((ASSET_DIR / "fonts").glob("*.woff2"))
    assert [path.name for path in fonts] == [
        "inter-variable.woff2", "jetbrains-mono-bold.woff2", "jetbrains-mono-regular.woff2"]
    for path in fonts:
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        assert f"`{path.name}`" in notices and digest in notices, path.name
    for license_name in ("ofl-inter.txt", "ofl-jetbrains-mono.txt"):
        text = (ASSET_DIR / "fonts" / license_name).read_text(encoding="utf-8")
        assert "SIL Open Font License, Version 1.1" in text
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert re.search(r'license-files = \[[^]]*"data/commander/fonts/ofl-\*\.txt"', pyproject)
