"""Retake the manual's screenshots in the light theme and rebuild the manual.

Usage: python tools/capture_manual_figures.py [--no-pdf]

The manual's pictures (``![caption](figure:<name>)`` in data/manual) are taken
in Tactical Day, the light theme, so a printed manual needs little ink. This
runs tools/capture_screenshots.py and tools/capture_commander.py with
``--theme day`` into a scratch folder, copies exactly the pictures the manual
uses (both languages) to docs/manual/figures, removes pictures it no longer
uses, then runs tools/build_manual.py and tools/build_manual_pdf.py. Run it
again after every visible change to the stations; it needs Chromium on PATH.
The README keeps its own night captures in docs/screenshots.
"""

import argparse
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.core import manual  # noqa: E402

FIGURES = ROOT / "docs" / "manual" / "figures"


def wanted() -> set:
    """File names of every figure the manual uses, in every language."""
    files = set()
    for chapter in manual.CHAPTERS:
        for lang in manual.LANGUAGES:
            blocks = manual.parse(manual.load_source(chapter, lang), lambda key: key)
            files.update(manual.figure_file(manual.figure_name(block), lang)
                         for block in blocks if block.kind == "figure")
    return files


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--no-pdf", action="store_true",
                        help="rebuild the Markdown manual but not the PDFs")
    args = parser.parse_args(argv)
    files = wanted()
    python = sys.executable
    with tempfile.TemporaryDirectory(prefix="u-jagd-figures-") as work:
        out = Path(work)
        for tool in ("capture_screenshots.py", "capture_commander.py"):
            subprocess.run([python, str(ROOT / "tools" / tool), "--theme", "day",
                            "--output", str(out)], check=True, cwd=ROOT)
        missing = sorted(name for name in files if not (out / name).is_file())
        if missing:
            raise SystemExit(f"captures missing for the manual: {', '.join(missing)}")
        FIGURES.mkdir(parents=True, exist_ok=True)
        for stale in FIGURES.glob("*.png"):
            if stale.name not in files:
                stale.unlink()
        for name in sorted(files):
            shutil.copyfile(out / name, FIGURES / name)
    print(f"{len(files)} manual figures in {FIGURES.relative_to(ROOT)}")
    subprocess.run([python, str(ROOT / "tools" / "build_manual.py")], check=True, cwd=ROOT)
    if not args.no_pdf:
        subprocess.run([python, str(ROOT / "tools" / "build_manual_pdf.py")],
                       check=True, cwd=ROOT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
