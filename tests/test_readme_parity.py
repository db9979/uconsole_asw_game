"""README.md and README.de.md stay translations of each other.

Both must have the same sections in the same order, and each section the same
code blocks, table rows, list items, inline code count, images and link
targets (German screenshots and documents mapped to their English names), and
the same current release.
"""

import re
from collections import Counter
from pathlib import Path

from src.core.version import APP_VERSION

ROOT = Path(__file__).resolve().parents[1]


def _sections(path):
    sections = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("#"):
            sections.append((line.split(" ", 1)[0], []))
        elif sections:
            sections[-1][1].append(line)
    return sections


def _target(target):
    """A link or image target with its language variant mapped to English."""
    target = target.split("#", 1)[0]
    target = re.sub(r"(^|/)de-", r"\1", target)
    target = target.replace("commander-v2-de-", "commander-v2-en-")
    target = re.sub(r"\.(de|en)\.md$", ".md", target)
    return {"docs/install-uconsole.md": "docs/install-uconsole.md",
            "README.de.md": "README.md"}.get(target, target)


def _shape(lines):
    text = "\n".join(lines)
    targets = re.findall(r"\]\(([^)]+)\)", text) + re.findall(r'<img src="([^"]+)"', text)
    return dict(
        code_blocks=text.count("```"),
        table_rows=sum(1 for line in lines if line.startswith("|")),
        list_items=sum(1 for line in lines if re.match(r"\s*(?:[-*]|\d+\.) ", line)),
        inline_code=len(re.findall(r"`[^`\n]+`", text)),
        targets=Counter(_target(target) for target in targets if not target.startswith("#")),
    )


def test_english_and_german_readme_have_the_same_structure():
    english = _sections(ROOT / "README.md")
    german = _sections(ROOT / "README.de.md")
    assert [level for level, _ in english] == [level for level, _ in german]
    for (level, en_lines), (_level, de_lines) in zip(english, german):
        heading = next(line for line in (ROOT / "README.md").read_text(
            encoding="utf-8").splitlines() if line.startswith(level))
        assert _shape(en_lines) == _shape(de_lines), heading


def test_both_readmes_name_the_current_release():
    english = (ROOT / "README.md").read_text(encoding="utf-8")
    german = (ROOT / "README.de.md").read_text(encoding="utf-8")
    assert f"Current release: **{APP_VERSION}**" in english
    assert f"Release {APP_VERSION} " in english
    assert f"Aktuelle Version: **{APP_VERSION}**" in german
    assert f"Version {APP_VERSION} " in german
