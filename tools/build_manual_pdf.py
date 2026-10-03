#!/usr/bin/env python3
"""Print the bilingual player manual to PDF with a local headless Chromium.

Usage: python tools/build_manual_pdf.py [--language all|de|en]

The PDF is rendered from the same blocks as the F1 manual reader, the Remote
Crew /manual pages and docs/manual/*.md (src/core/manual.py), so key tables and
standard procedures always match src/core/help.py. An installed Chromium is
required; nothing is downloaded. The browser runs with a throw-away profile.
"""

import argparse
import datetime
import html
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

from src.core import manual  # noqa: E402
from src.core.version import APP_VERSION  # noqa: E402

OUT_DIR = ROOT / "docs" / "manual"
OUTPUTS = {"de": OUT_DIR / "handbuch.de.pdf", "en": OUT_DIR / "manual.en.pdf"}
SUBTITLE = {"de": "Spielerhandbuch, Version {version}, Stand {date}",
            "en": "Player manual, version {version}, as of {date}"}

PRINT_CSS = """
@page { size: A4; margin: 16mm 15mm 18mm 15mm; }
body { font-family: "DejaVu Sans", "Liberation Sans", Arial, sans-serif;
       font-size: 9.6pt; line-height: 1.38; color: #111; margin: 0; }
.manual-head h1 { font-size: 22pt; margin: 0 0 2mm 0; }
.manual-head .subtitle { color: #444; margin: 0 0 6mm 0; }
.toc { page-break-after: always; }
.toc h2 { font-size: 13pt; }
.toc ol { columns: 2; column-gap: 10mm; list-style: none; padding-left: 0; }
.toc a { color: #111; text-decoration: none; }
article { page-break-before: always; }
h1, h2, h3, h4 { page-break-after: avoid; break-after: avoid; }
h2 { font-size: 16pt; border-bottom: 1.5pt solid #1b4d3e; padding-bottom: 1mm; }
h3 { font-size: 12pt; margin-top: 5mm; }
h4 { font-size: 10.5pt; }
table { border-collapse: collapse; width: 100%; margin: 2mm 0 3mm 0;
        page-break-inside: avoid; break-inside: avoid; }
th, td { border: 0.5pt solid #999; padding: 1mm 1.6mm; vertical-align: top;
         text-align: left; }
th { background: #e6efe9; }
code { font-family: "DejaVu Sans Mono", monospace; font-size: 8.8pt;
       background: #f1f1f1; padding: 0 0.6mm; }
pre { font-family: "DejaVu Sans Mono", monospace; font-size: 8.2pt;
      background: #f5f5f5; border: 0.5pt solid #ccc; padding: 2mm;
      white-space: pre-wrap; page-break-inside: avoid; break-inside: avoid; }
pre code { background: none; padding: 0; }
blockquote { border-left: 2pt solid #1b4d3e; margin: 2mm 0; padding: 0 0 0 3mm;
             color: #333; }
ol, ul { padding-left: 6mm; }
li { margin: 0.6mm 0; }
figure { margin: 3mm 0 4mm 0; text-align: center; page-break-inside: avoid;
         break-inside: avoid; }
figure img { max-width: 100%; max-height: 105mm; border: 0.5pt solid #999; }
figcaption { font-size: 8.6pt; color: #333; margin-top: 1mm; font-style: italic; }
"""
# Light (Tactical Day) captures from tools/capture_manual_figures.py: they
# print with little ink.
SCREENSHOTS = ROOT / "docs" / "manual" / "figures"


def print_html(lang: str, date: str) -> str:
    # Screenshots stay lossless PNG: the station text must stay readable.
    page = manual.html_page(lang, SCREENSHOTS.as_uri())
    # The print stylesheet is self-contained: drop the web design-system links.
    page = re.sub(r'<link rel="stylesheet" href="/css/[a-z]+\.css">\n', "", page)
    page = page.replace('<link rel="stylesheet" href="/manual.css">',
                        f"<style>{PRINT_CSS}</style>")
    # No web navigation in print; add the release line under the title.
    page = re.sub(r'<a class="lang-switch"[^>]*>.*?</a>', "", page, count=1)
    subtitle = html.escape(SUBTITLE[lang].format(version=APP_VERSION, date=date))
    return page.replace("</h1></header>",
                        f'</h1><p class="subtitle">{subtitle}</p></header>', 1)


def render(chromium: str, source: Path, target: Path, profile: Path) -> None:
    subprocess.run(
        [chromium, "--headless", "--disable-gpu", "--no-sandbox",
         "--no-first-run", "--disable-extensions", "--disable-sync",
         f"--user-data-dir={profile}", "--no-pdf-header-footer",
         f"--print-to-pdf={target}", source.as_uri()],
        check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        timeout=180)
    if not target.is_file() or target.stat().st_size == 0:
        raise RuntimeError(f"Chromium wrote no PDF for {source.name}")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--language", choices=("all", *manual.LANGUAGES),
                        default="all")
    args = parser.parse_args(argv)
    chromium = (shutil.which("chromium") or shutil.which("chromium-browser")
                or shutil.which("google-chrome"))
    if not chromium:
        parser.error("an installed Chromium is required; no browser is downloaded")
    date = datetime.date.today().isoformat()
    languages = manual.LANGUAGES if args.language == "all" else (args.language,)
    with tempfile.TemporaryDirectory(prefix="u-jagd-manual-pdf-") as work:
        work = Path(work)
        for lang in languages:
            source = work / f"manual.{lang}.html"
            source.write_text(print_html(lang, date), encoding="utf-8")
            staged = work / OUTPUTS[lang].name
            render(chromium, source, staged, work / "profile")
            OUT_DIR.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(staged, OUTPUTS[lang])
            print(f"wrote {OUTPUTS[lang].relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
