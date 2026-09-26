"""Export the bilingual player manual to docs/manual/.

Usage: python tools/build_manual.py [--check]

The packaged chapters in data/manual/ are the source. Key tables and standard
procedures are expanded from src/core/help.py and the i18n catalogs, so the
exported Markdown matches the F1 overlay and the Remote Crew /manual pages.
With --check nothing is written; the command fails if an export is stale.
Run it after every change to controls, stations, mechanics, or manual text.
"""

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

from src.core import manual  # noqa: E402

OUT_DIR = ROOT / "docs" / "manual"


def exports() -> dict:
    return {OUT_DIR / f"manual.{lang}.md": manual.markdown(lang)
            for lang in manual.LANGUAGES}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true",
                        help="fail if docs/manual is out of date; write nothing")
    args = parser.parse_args(argv)
    stale = []
    for path, text in exports().items():
        current = path.read_text(encoding="utf-8") if path.is_file() else None
        if current == text:
            continue
        if args.check:
            stale.append(path.relative_to(ROOT))
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
            print(f"wrote {path.relative_to(ROOT)}")
    if stale:
        print("stale manual export (run python tools/build_manual.py): "
              + ", ".join(map(str, stale)), file=sys.stderr)
        return 1
    if args.check:
        print("manual export up to date")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
