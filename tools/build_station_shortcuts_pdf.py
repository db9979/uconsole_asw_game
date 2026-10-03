#!/usr/bin/env python3
"""Generate the printable German station shortcut reference without dependencies."""

from __future__ import annotations

import argparse
from pathlib import Path
from runpy import run_path
import sys
import textwrap


ROOT = Path(__file__).resolve().parents[1]
MARKDOWN_PATH = ROOT / "docs" / "station-shortcuts.de.md"
PDF_PATH = ROOT / "docs" / "station-shortcuts.de.pdf"
VERSION = str(run_path(ROOT / "src" / "core" / "version.py")["APP_VERSION"])

# Global and station keys come from src/core/help.py, the single source of the
# F1 overlay and the player manual, so this sheet cannot drift from the game.
# Only dialog keys, which help.py does not list, are maintained here.
DIALOG_SECTION = ("Eingabe und Dialoge", (
    ("Numerische Eingabe", "Ziffern, Punkt oder Komma; Backspace; Enter bestätigt; Esc bricht ab. Mit der Maus über das eingeblendete Tastenfeld."),
    ("Maus", "Klick auf eine Taste der Tastenleiste drückt sie (gehalten wie die Taste); Reiter oben wechseln die Station; Klick auf Kurs-, Fahrt- oder Tiefenscheibe befiehlt den Wert; Statuslampen, Tastenhinweise, Seitenreiter, Listenzeilen und Werte der Statuszeile anklickbar (Rahmen unter der Maus; Strg+Enter nur an Station 3); Menü- und Dialogzeilen anklickbar; Mausrad blättert; Rechtsklick bricht ab wie Esc. Menü-Symbol in der Kopfzeile: Spielmenü (Hilfe, Optionen, Speichern/Laden, Wetter, Plot, Autocrew, Beenden u. a.); Schließfeld oben rechts in jedem Overlay wirkt wie Esc; Tastenchips für Sonar-Kontaktbefehle (C, T, G, M, Y), OPZ-Zielseite (M, G, ←/→), Begleiter-Befehle und U-Boot-Rohre/Täuschkörper (Shift+M, Strg+M, V). ESSM und ASROC des Begleiters nur per Strg+Enter."),
    ("Hilfe", "←/→/Tab Kategorie; ↑/↓ zeilenweise; Bild↑/Bild↓ seitenweise; im Handbuch [ ] oder , . bzw. 0-9 Kapitel; F1/Esc schließen."),
    ("Speichern/Laden", "1 bis 5 wählt Slot; Enter bestätigt; Esc zurück."),
    ("Beenden-Dialog", "↑/↓ wählen, Enter bestätigen: zurück zum Spiel, speichern und beenden, zum Hauptmenü (ohne Speichern), ohne Speichern beenden; Esc/N schließt."),
    ("Missionsende", "R Neustart mit gleichem Seed (Editor-Mission startet sich selbst neu); M zum Hauptmenü; Esc Beenden-Dialog."),
    ("Commander-Vorschlag", "F6 annehmen; F7 ablehnen; F8 Vorschlagsart; Esc ausblenden."),
    ("SimLog", "↑/↓, Bild↑/Bild↓, Home/End oder Mausrad; M Karte, F Karte einpassen; F4/Esc oder Schließfeld schließen."),
    ("Wetter/Analyse", "0, Esc oder das Schließfeld schließt das Analysefeld."),
    ("Autocrew-Übersicht", "F3, Esc oder das Schließfeld schließt."),
))


def build_sections() -> tuple:
    from src.core import help as game_help
    from src.core import manual
    from src.core.i18n import Translator

    tr = Translator("de").t
    title, rows = game_help.get_global_help(tr)
    sections = [("Global", tuple(rows))]
    for station, chapter in manual.STATION_CHAPTERS.items():
        _, controls, _, _ = game_help.get_help(station, tr)
        sections.append((manual.chapter_title(chapter, "de"), tuple(controls)))
    for getter in (game_help.get_uboot_global_help, game_help.get_uboot_help,
                   game_help.get_menu_help, game_help.get_web_help):
        extra_title, extra_rows = getter(tr)
        sections.append((extra_title.rstrip(":"), tuple(extra_rows)))
    sections.append(DIALOG_SECTION)
    return tuple(sections)


sys.path.insert(0, str(ROOT))
SECTIONS = build_sections()


def _md(text: str) -> str:
    return text.replace("|", "\\|")


def markdown_bytes() -> bytes:
    lines = [
        f"# U-Jagd {VERSION} - Stations- und Tastenkürzel",
        "",
        "Druckfassung: [`station-shortcuts.de.pdf`](station-shortcuts.de.pdf).",
        "Maßgeblich ist die implementierte lokale Bedienung. Stationsnummern und",
        "Tasten sind kontextabhängig; normale Bereitschafts-, Schadens- und",
        "Berechtigungsprüfungen bleiben wirksam.",
        "",
    ]
    for title, rows in SECTIONS:
        lines.extend((f"## {title}", "", "| Taste / Eingabe | Funktion |", "|---|---|"))
        lines.extend(f"| `{_md(key)}` | {_md(action)} |" for key, action in rows)
        lines.append("")
    lines.extend((
        "## Hinweise",
        "",
        "- `Num-Enter` entspricht in Spiel- und Eingabedialogen grundsätzlich `Enter`.",
        "- Wiederholte Keydown-Ereignisse werden ignoriert; nur ausdrücklich als",
        "  gehalten beschriebene Steuerungen arbeiten kontinuierlich.",
        "- Remote Crew verwendet Browser-Bedienelemente; der Abschnitt zum Browser",
        "  nennt nur dessen Tastaturhilfen.",
        "- In der nativen OPZ sind Ereignis-Feed und Telemetrie ausgeblendet; ihre",
        "  Daten laufen weiter, `F11` blendet sie auch dort als Overlay ein.",
        "- Tasten und Beschreibungen der Stationen stammen aus `src/core/help.py`",
        "  (dieselbe Quelle wie die F1-Hilfe und das Handbuch).",
        "- U-Jagd ist ein Spiel und kein Ausbildungs- oder Navigationsprodukt.",
        "",
        "Erzeugt mit `python tools/build_station_shortcuts_pdf.py`.",
    ))
    return ("\n".join(lines) + "\n").encode("utf-8")


def _pdf_escape(text: str) -> bytes:
    text = text.replace("Bild↑", "Bild auf").replace("Bild↓", "Bild ab")
    for symbol, replacement in (("←", "Links"), ("→", "Rechts"),
                                ("↑", "Auf"), ("↓", "Ab")):
        text = text.replace(symbol, replacement)
    return (text.replace("\\", "\\\\").replace("(", "\\(")
            .replace(")", "\\)").encode("cp1252", "replace"))


def _text(command: bytearray, x: float, y: float, text: str,
          *, size: float = 8.5, bold: bool = False) -> None:
    font = b"F2" if bold else b"F1"
    command.extend(b"BT /" + font + f" {size:.1f} Tf 1 0 0 1 {x:.1f} {y:.1f} Tm (".encode())
    command.extend(_pdf_escape(text))
    command.extend(b") Tj ET\n")


def _wrapped_rows(rows: tuple[tuple[str, str], ...]):
    """Yield (key lines, action lines); long key labels wrap in their column."""
    for key, action in rows:
        keys = textwrap.wrap(key, width=19, break_long_words=False,
                             break_on_hyphens=False) or [""]
        wrapped = textwrap.wrap(action, width=78, break_long_words=False,
                                break_on_hyphens=False) or [""]
        yield keys, wrapped


def pdf_bytes() -> bytes:
    pages: list[bytearray] = []
    page = bytearray()
    y = 795.0

    def new_page() -> None:
        nonlocal page, y
        if page:
            pages.append(page)
        page = bytearray(b"0.10 0.18 0.22 rg\n")
        _text(page, 36, 808, "U-Jagd", size=16, bold=True)
        _text(page, 112, 810, f"Stations- und Tastenkürzel | Version {VERSION}",
              size=10, bold=True)
        page.extend(b"0.35 0.55 0.58 RG 36 801 m 559 801 l S\n0 0 0 rg\n")
        y = 784.0

    def section_height(rows: tuple[tuple[str, str], ...]) -> float:
        line_count = sum(max(len(keys), len(wrapped))
                         for keys, wrapped in _wrapped_rows(rows))
        return 24.0 + line_count * 10.5 + len(rows) * 2.0

    new_page()
    for title, rows in SECTIONS:
        needed = section_height(rows)
        if y - needed < 48 and y < 760:
            new_page()
        _text(page, 36, y, title, size=11, bold=True)
        y -= 6
        page.extend(f"0.35 0.55 0.58 RG 36 {y:.1f} m 559 {y:.1f} l S\n0 0 0 rg\n".encode())
        y -= 13
        for keys, wrapped in _wrapped_rows(rows):
            height = max(len(keys), len(wrapped))
            if y - height * 10.5 < 43:
                new_page()
                _text(page, 36, y, title + " (Fortsetzung)", size=10, bold=True)
                y -= 18
            for index, line in enumerate(keys):
                _text(page, 40, y - index * 10.5, line, size=8.2, bold=True)
            for index, line in enumerate(wrapped):
                _text(page, 139, y - index * 10.5, line, size=8.2)
            y -= height * 10.5 + 2.0
        y -= 8
    pages.append(page)

    for index, content in enumerate(pages, 1):
        _text(content, 36, 25, "Lokale uConsole-Bedienung | U-Jagd ist ein Spiel, kein Ausbildungsprodukt.", size=7.2)
        _text(content, 525, 25, f"{index}/{len(pages)}", size=7.2, bold=True)

    objects: dict[int, bytes] = {
        1: b"<< /Type /Catalog /Pages 2 0 R >>",
        3: b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>",
        4: b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>",
    }
    page_ids = []
    for index, content in enumerate(pages):
        page_id = 5 + index * 2
        stream_id = page_id + 1
        page_ids.append(page_id)
        objects[page_id] = (
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] "
            f"/Resources << /Font << /F1 3 0 R /F2 4 0 R >> >> "
            f"/Contents {stream_id} 0 R >>").encode()
        objects[stream_id] = (f"<< /Length {len(content)} >>\nstream\n".encode()
                              + bytes(content) + b"endstream")
    kids = " ".join(f"{page_id} 0 R" for page_id in page_ids)
    objects[2] = f"<< /Type /Pages /Kids [{kids}] /Count {len(page_ids)} >>".encode()

    result = bytearray(b"%PDF-1.4\n%\x00\xe2\xe3\xcf\xd3\n")
    offsets = [0]
    for object_id in range(1, max(objects) + 1):
        offsets.append(len(result))
        result.extend(f"{object_id} 0 obj\n".encode())
        result.extend(objects[object_id])
        result.extend(b"\nendobj\n")
    xref = len(result)
    result.extend(f"xref\n0 {len(offsets)}\n".encode())
    result.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        result.extend(f"{offset:010d} 00000 n \n".encode())
    result.extend((f"trailer\n<< /Size {len(offsets)} /Root 1 0 R >>\n"
                   f"startxref\n{xref}\n%%EOF\n").encode())
    return bytes(result)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true",
                        help="fail when generated files are missing or stale")
    args = parser.parse_args()
    outputs = {MARKDOWN_PATH: markdown_bytes(), PDF_PATH: pdf_bytes()}
    if args.check:
        stale = [path for path, content in outputs.items()
                 if not path.is_file() or path.read_bytes() != content]
        if stale:
            parser.error("stale generated files: " + ", ".join(map(str, stale)))
        print(f"station shortcut documents valid: {len(SECTIONS)} sections")
        return 0
    for path, content in outputs.items():
        path.write_bytes(content)
    print(f"wrote {MARKDOWN_PATH.relative_to(ROOT)} and {PDF_PATH.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
