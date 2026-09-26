"""Plan 1.3, phase 2: no source module grows back into a monolith."""

from pathlib import Path

LIMIT = 2500
SRC = Path(__file__).resolve().parent.parent / "src"


def test_no_source_module_exceeds_the_line_limit():
    oversized = {
        str(path.relative_to(SRC.parent)): count
        for path in SRC.rglob("*.py")
        if (count := sum(1 for _ in path.open(encoding="utf-8"))) > LIMIT
    }
    assert not oversized, oversized
