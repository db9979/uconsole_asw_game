#!/usr/bin/env python3
"""Generate the printable German station shortcut reference without dependencies."""

from __future__ import annotations

import argparse
from pathlib import Path
from runpy import run_path
import textwrap


ROOT = Path(__file__).resolve().parents[1]
MARKDOWN_PATH = ROOT / "docs" / "station-shortcuts.de.md"
PDF_PATH = ROOT / "docs" / "station-shortcuts.de.pdf"
VERSION = str(run_path(ROOT / "src" / "core" / "version.py")["APP_VERSION"])

SECTIONS = (
    ("Global", (
        ("1 bis 9", "Station direkt wählen; aktive Stationsnummer erneut drücken, um verfügbare Seiten weiterzuschalten."),
        ("Tab / Shift+Tab", "Nächste / vorherige Station."),
        ("P", "Pause oder Fortsetzen."),
        ("[ / Z", "Zeitraffer verringern."),
        ("] / X", "Zeitraffer erhöhen."),
        ("+ / -", "Maschinentelegraf vor / zurück; auch Num+ / Num-."),
        ("F1", "Kontextsensitive Hilfe öffnen."),
        ("F2", "Autocrew der aktuellen Station ein- oder ausschalten."),
        ("F3", "Autocrew-Übersicht öffnen."),
        ("F4", "SimLog öffnen, sofern die Option aktiviert ist."),
        ("F8", "Taktischen Einheitenanalysator öffnen; bei Commander-Vorschlägen Vorschlagsart wechseln."),
        ("F9", "Lokale Commander-/Remote-Crew-Verwaltung öffnen."),
        ("F10", "Optionen öffnen; während Pause funktioniert zusätzlich O."),
        ("N", "Nationen-/Einheitenansicht öffnen; nicht am Sonar."),
        ("S / L", "Speichern / Laden; L ist in der OPZ stattdessen der Fusionsbefehl."),
        ("Alt+Enter", "Vollbild umschalten."),
        ("Esc", "Fixierten Tooltip lösen, Eingabe/Ansicht abbrechen oder Beenden-Dialog öffnen."),
    )),
    ("1  Brücke", (
        ("← / → halten", "Sollkurs kontinuierlich nach Backbord / Steuerbord ändern."),
        ("↑ / ↓", "Maschinentelegraf vor / zurück."),
        ("U", "Sollkurs numerisch eingeben."),
        ("V", "Sollfahrt numerisch eingeben."),
        ("Q / E", "Karte heraus- / hineinzoomen."),
        ("K", "Kartenverfolgung ein- oder ausschalten."),
        ("Mausrad / Ziehen", "Karte um Mausposition zoomen / verschieben."),
        ("Klick auf Objekt", "Tooltip fixieren; beobachtbaren Sonarkontakt gegebenenfalls wählen."),
    )),
    ("2  Sonar", (
        ("Bild↑ / Bild↓", "Vorherige / nächste Sonarseite: Broadband, LOFAR, DEMON, TMA, Environment, ACTIVE."),
        ("2", "Bei bereits aktivem Sonar zur nächsten Sonarseite."),
        ("Shift+A", "Aktiven Schiffssonar-Ping senden."),
        ("Shift+B", "Empfangsarray zwischen HMS/Bug und TAS/Schlepparray wechseln."),
        ("Y", "TAS ausbringen oder einholen."),
        ("E", "Bathythermografische Messung durchführen."),
        ("U / V", "TAS-/VDS-Solltiefe um 10 m heben / senken."),
        ("R", "Horchpeilung numerisch eingeben."),
        ("← / →", "Horchpeilung um 0,5° ändern; Shift: 5°, Strg: 0,1°."),
        ("↑ / ↓", "Vorherigen / nächsten Kontakt wählen."),
        ("Enter", "Gewähltem Kontakt folgen; bei Fokus zur manuellen Peilung zurückkehren."),
        ("J", "Sonar-Hörton ein- oder ausschalten."),
        (", / .", "Hörlautstärke um 10 % verringern / erhöhen."),
        ("A / B / H", "Breitband-, gefilterten oder Heterodyn-Hörmodus wählen."),
        ("D", "Zwischen Breitband und gefiltertem Hören wechseln."),
        ("I / O", "Empfangsverstärkung um 3 dB verringern / erhöhen."),
        ("F", "Frequenzband weit / tief / mittel wechseln."),
        ("N", "Eigenantriebs-Notchfilter ein- oder ausschalten."),
        ("K", "Erkannte Harmonik-Hypothese wählen oder löschen."),
        ("Leertaste", "LOFAR-Peak-Hold ein- oder ausschalten."),
        ("T / C / G / M", "TMA umschalten / klassifizieren / an OPZ freigeben / als Waffenziel setzen."),
        ("Maus", "Seitentab oder Kontakt wählen; im Broadband-Wasserfall Horchpeilung setzen."),
    )),
    ("3  Waffen", (
        ("↑ / ↓ halten", "Torpedo-Solltiefe zwischen 10 und 300 m ändern."),
        ("← / →", "Vorherigen / nächsten Sonarkontakt wählen."),
        ("M", "Gewählten Sonarkontakt als Ziel setzen."),
        ("T / Strg+Enter", "Schiffstorpedo starten; Bereitschafts- und ROE-Prüfungen gelten."),
        ("H", "Helikopter starten oder zurückrufen."),
        ("B / D", "Sonarboje absetzen / Helikoptertorpedo abwerfen."),
        ("V", "Nixie-Schleppköder ausbringen."),
        ("Q / E / K", "Kartenzoom heraus / hinein / Verfolgung umschalten."),
        ("Mausrad / Ziehen", "Karte zoomen / verschieben."),
    )),
    ("4  Schadensabwehr", (
        ("← / →", "Vorherige / nächste Abteilung wählen."),
        ("↑ / ↓", "Reparaturteam 1 bis 3 wählen."),
        ("Enter", "Gewähltes Team der gewählten Abteilung zuweisen."),
        ("Backspace", "Gewähltes Team zurückziehen."),
        ("Klick auf Abteilung", "Abteilung wählen und Zuweisung des aktuell gewählten Teams versuchen."),
        ("1 bis 9", "Wechselt immer die Station; wählt kein Reparaturteam."),
    )),
    ("5  OPZ / CIC", (
        ("↑ / ↓", "Vorherigen / nächsten CIC-Track wählen."),
        ("C / F", "Klassifikation / NATO-Zugehörigkeit des gewählten Tracks ändern."),
        ("Leertaste", "Gewählten Rohbericht markieren oder Markierung entfernen."),
        ("L / Shift+L", "Aus markierten Meldungen Fusion bilden / gewählte Fusion auflösen."),
        ("Backspace", "Alle Markierungen leeren."),
        ("Delete / H", "Bericht unterdrücken / Anzeige unterdrückter Meldungen umschalten."),
        ("M", "CIC-Track an Sonar/Waffen übergeben."),
        ("Bild↑ / Bild↓", "Radar-Anzeigebereich vergrößern / verkleinern."),
        ("← / →", "Vorheriges / nächstes ASM-Ziel wählen."),
        ("E / Strg+Enter", "ESSM starten; Bereitschafts- und ROE-Prüfungen gelten."),
        ("G", "Chaff ausbringen."),
        ("R / Shift+R", "Seezielradar / Luftraumradar ein- oder ausschalten."),
        ("Mausrad / Klick", "PPI-Bereich ändern / dargestellten Bericht wählen."),
    )),
    ("6  Funk", (
        ("↑ / ↓", "Vorheriges / nächstes HFDF-Signal wählen."),
        ("Enter", "HFDF-Peilung zusammen mit der eigenen Position protokollieren."),
    )),
    ("7  Maschinenraum", (
        ("↑ / ↓", "Maschinentelegraf vor / zurück."),
        ("A", "Schleichfahrt / Normalbetrieb umschalten."),
        ("U", "Sollkurs numerisch eingeben."),
        ("V", "Sollfahrt numerisch eingeben."),
        ("+ / -", "Globaler Maschinentelegraf vor / zurück."),
    )),
    ("8  Helikopter", (
        ("H", "Helikopter starten oder zurückrufen; Wettergrenzen gelten für den Start."),
        ("← / →", "Wegpunktpeilung um 15° ändern."),
        ("↑ / ↓", "Wegpunktentfernung um 1 NM erhöhen / verringern."),
        ("M", "Sonarkontakt als Lufttorpedoziel setzen."),
        ("B", "Sonarboje an aktueller Position absetzen."),
        ("Y", "Tauchsonar ausbringen oder einholen."),
        ("U / V", "Tauchsonar-Solltiefe um 10 m heben / senken."),
        ("A", "Aktiven Tauchsonar-Ping senden."),
        ("D / Strg+Enter", "Leichttorpedo abwerfen."),
        ("Q / E / K", "Kartenzoom heraus / hinein / Verfolgung umschalten."),
        ("Klick in freie Karte", "Wegpunkt direkt setzen; Objektklick wählt stattdessen Objekt/Tooltip."),
    )),
    ("9  EloKa / ESM", (
        ("↑ / ↓", "Vorherige / nächste passive ESM-Auffassung wählen."),
        ("C", "Manuelle Radarart-Zuordnung wechseln."),
        ("Klick auf Track", "Auffassung wählen und gegebenenfalls Tooltip fixieren."),
    )),
    ("Eingabe und Dialoge", (
        ("Numerische Eingabe", "Ziffern, Punkt oder Komma; Backspace; Enter bestätigt; Esc bricht ab."),
        ("Hilfe", "←/→/Tab Kategorie; ↑/↓ zeilenweise; Bild↑/Bild↓ seitenweise; F1/Esc schließen."),
        ("Speichern/Laden", "1 bis 5 wählt Slot; Enter bestätigt; Esc zurück."),
        ("Commander-Vorschlag", "F6 annehmen; F7 ablehnen; F8 Vorschlagsart; Esc ausblenden."),
        ("SimLog", "↑/↓, Bild↑/Bild↓, Home/End oder Mausrad; F4/Esc schließen."),
    )),
)


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
        lines.extend(f"| `{key}` | {action} |" for key, action in rows)
        lines.append("")
    lines.extend((
        "## Hinweise",
        "",
        "- `Num-Enter` entspricht in Spiel- und Eingabedialogen grundsätzlich `Enter`.",
        "- Wiederholte Keydown-Ereignisse werden ignoriert; nur ausdrücklich als",
        "  gehalten beschriebene Steuerungen arbeiten kontinuierlich.",
        "- Remote Crew verwendet Browser-Bedienelemente. Dieses Blatt beschreibt die",
        "  lokale Tastatur- und Mausbedienung auf der uConsole.",
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
    for key, action in rows:
        wrapped = textwrap.wrap(action, width=78, break_long_words=False,
                                break_on_hyphens=False) or [""]
        yield key, wrapped


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
        line_count = sum(len(wrapped) for _, wrapped in _wrapped_rows(rows))
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
        for key, wrapped in _wrapped_rows(rows):
            if y - len(wrapped) * 10.5 < 43:
                new_page()
                _text(page, 36, y, title + " (Fortsetzung)", size=10, bold=True)
                y -= 18
            _text(page, 40, y, key, size=8.2, bold=True)
            for index, line in enumerate(wrapped):
                _text(page, 139, y - index * 10.5, line, size=8.2)
            y -= len(wrapped) * 10.5 + 2.0
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
