#!/usr/bin/env python3
"""Render the A4 promotional poster (German and English) to PNG and PDF.

The hero image is the start-screen scene of ``src/ui/splash_view.py`` drawn
with Pygame, the four small screenshots come from ``docs/screenshots/`` and the
two QR codes (download: ``releases/latest``; support: ``SUPPORT_URL`` of
``src/ui/support.py``) are made with ``segno`` (``pip install segno``). The
layout lives in ``docs/poster/template/poster.<lang>.html`` and is rendered by
Chromium (on ``PATH``) at 2480 x 3508 px, i.e. A4 portrait at 300 dpi.

Outputs: ``docs/poster/u-jagd-poster-a4.<lang>.png`` and ``.pdf``. Run it
after the screenshots or the splash scene change; it has no ``--check`` because
Chromium's raster output is not byte-stable across versions.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import zlib

ROOT = Path(__file__).resolve().parents[1]
POSTER = ROOT / "docs" / "poster"
TEMPLATES = POSTER / "template"
SCREENSHOTS = ROOT / "docs" / "screenshots"
DOWNLOAD_URL = "https://github.com/db9979/uconsole_asw_game/releases/latest"
WIDTH, HEIGHT = 2480, 3508
SCENE_T = 2.5  # the hull ping has just reached the submarine
LANGS = ("de", "en")


def render_scene(target: Path) -> None:
    """The splash scene without its console corner brackets, 1280 x 720."""
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
    sys.path.insert(0, str(ROOT))
    import pygame
    from src.ui import splash_view
    pygame.init()
    pygame.display.set_mode((1, 1))
    surface = pygame.Surface((1280, 720))
    frame = splash_view._draw_frame
    splash_view._draw_frame = lambda _surface: None
    try:
        splash_view.draw_scene(surface, SCENE_T)
    finally:
        splash_view._draw_frame = frame
    pygame.image.save(surface, str(target))


def render_qr(url: str, target: Path) -> None:
    import segno
    segno.make(url, error="m").save(str(target), scale=10, border=0, dark="#03070f",
                                    light=None)


def support_url() -> str:
    text = (ROOT / "src" / "ui" / "support.py").read_text(encoding="utf-8")
    return re.search(r'^SUPPORT_URL = "([^"]+)"$', text, re.M).group(1)


def set_png_dpi(path: Path, dpi: int = 300) -> None:
    """Insert a pHYs chunk so print tools read the PNG as 300 dpi."""
    data = path.read_bytes()
    ppm = round(dpi / 0.0254)
    body = b"pHYs" + struct.pack(">IIB", ppm, ppm, 1)
    chunk = struct.pack(">I", 9) + body + struct.pack(">I", zlib.crc32(body))
    end_of_ihdr = 8 + 4 + 4 + 13 + 4
    path.write_bytes(data[:end_of_ihdr] + chunk + data[end_of_ihdr:])


def crop_png(source: Path, target: Path) -> None:
    import pygame
    image = pygame.image.load(str(source))
    pygame.image.save(image.subsurface((0, 0, WIDTH, HEIGHT)).copy(), str(target))
    set_png_dpi(target)


def build(chromium: str, work: Path) -> None:
    render_scene(work / "scene.png")
    render_qr(DOWNLOAD_URL, work / "qr_download.svg")
    render_qr(support_url(), work / "qr_coffee.svg")
    base = [chromium, "--headless", "--no-sandbox", "--disable-gpu", "--hide-scrollbars",
            "--force-device-scale-factor=1", f"--user-data-dir={work / 'profile'}"]
    for lang in LANGS:
        html = (TEMPLATES / f"poster.{lang}.html").read_text(encoding="utf-8")
        page = work / f"poster.{lang}.html"
        page.write_text(html.replace("SCREENSHOTS/", SCREENSHOTS.as_uri() + "/"),
                        encoding="utf-8")
        raw = work / f"raw.{lang}.png"
        # The headless window is taller than the page so the full A4 height
        # lands in the viewport; the crop drops the rest.
        subprocess.run(base + [f"--window-size={WIDTH},{HEIGHT + 400}",
                               "--virtual-time-budget=3000", f"--screenshot={raw}",
                               page.as_uri()], check=True, capture_output=True)
        crop_png(raw, POSTER / f"u-jagd-poster-a4.{lang}.png")
        subprocess.run(base + ["--no-pdf-header-footer", "--virtual-time-budget=3000",
                               f"--print-to-pdf={POSTER / f'u-jagd-poster-a4.{lang}.pdf'}",
                               page.as_uri()], check=True, capture_output=True)
        print(f"wrote docs/poster/u-jagd-poster-a4.{lang}.png and .pdf")


def main() -> int:
    argparse.ArgumentParser(description=__doc__).parse_args()
    chromium = (shutil.which("chromium") or shutil.which("chromium-browser")
                or shutil.which("google-chrome"))
    if not chromium:
        print("Chromium not found on PATH", file=sys.stderr)
        return 1
    with tempfile.TemporaryDirectory() as tmp:
        build(chromium, Path(tmp))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
