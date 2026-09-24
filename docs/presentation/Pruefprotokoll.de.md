# Prüfprotokoll zur Präsentation

Stand: 24. September 2026. Geprüft wurde der lokale Arbeitsbaum; bereits
vorhandene Änderungen an Spielcode, Ressourcen und Tests wurden nicht bearbeitet.
Die neu erstellten Projektdateien liegen ausschließlich in `docs/presentation/`.

## Inhaltliche Grundlage

- AST-Inventur aller 116 Pythonmodule unter `src/`, einschließlich Symbolen,
  interner Imports und Dateihashes.
- Vertiefte Analyse der Simulationsschleife und der relevanten Fachmodelle,
  Ressourcen, Tests und aktuellen Dokumentation; Quellpfade je Folie.
- Explizite Trennung von aktuellem Code, historischen Beschreibungen,
  illustrativen Beispielen, Repository-Screenshots und Modellgrenzen.
- Berücksichtigte Besonderheiten: fester Faktor 1; Live-Verkehr mit externen
  Meldungen und Wanduhr; Transienz der Audioempfänger und OPZ-Fusionsarbeitsfläche;
  neue Wetter-/Flugwetterkopplung des lokalen Arbeitsstands.

Die Inventur ist keine Behauptung, jede Zeile manuell geprüft zu haben. Die
Präsentation deckt die relevanten Subsysteme ab und vertieft ihre tatsächlichen
Aufruf-, Informations- und Wirkungsbeziehungen.

## Ausgeführte Verhaltensprüfungen

Erster Lauf: **64 bestanden**.

```sh
.venv/bin/python -m pytest -q \
  tests/test_realtime_movement.py tests/test_weather_station.py \
  tests/test_sensor_tracks_core.py tests/test_opz_fusion.py \
  tests/test_torpedo_physics.py tests/test_damage_stability.py
```

Zweiter Lauf: **155 bestanden**.

```sh
.venv/bin/python -m pytest -q \
  tests/test_determinism.py tests/test_runtime_continuation.py \
  tests/test_active_sonar_snapshot.py tests/test_autocrew.py
```

Damit sind insgesamt **219 gezielte Tests bestanden**. Es wurde kein vollständiger
Release-Testlauf und kein Hardwaretest auf einer uConsole durchgeführt.

Zusätzlicher Kalibrierungslauf: **77/77 Metriken innerhalb der Toleranz**,
unter Berücksichtigung der bereits hinterlegten begründeten Abweichungen.

```sh
.venv/bin/python tools/calibrate.py --check
```

## Dokumentprüfung

- PowerPoint erneut mit `python-pptx` geladen: genau 60 Folien.
- Jede Folie enthält Sprechernotizen und einen Quellenabschnitt.
- Alle verwendeten Quellenpfade existieren im Repository.
- Position und Ausdehnung sämtlicher PowerPoint-Objekte liegen auf der Folie.
- ZIP-Integrität und XML-Struktur der PowerPoint-Datei geprüft.
- Der Erzeuger prüft Textbreiten, Zeilenzahl und verfügbare Höhe; kein Überlauf.
- PDF mit `pdfinfo`: 60 Seiten im Format 16:9.
- PDF mit `pdftotext`: Inhalte als echter Text extrahierbar.
- Kontaktbogen aller Folien und ausgewählte Folien in voller Größe visuell geprüft.
- Aus der fertigen PDF gerenderte Folien 29, 53 und 60 visuell geprüft.

Die PowerPoint-Datei wurde in dieser Umgebung nicht mit Microsoft PowerPoint
oder LibreOffice gerendert, da diese Anwendungen hier nicht installiert sind.
Die PDF und Bildvorschauen stammen aus denselben Layoutdaten; die PDF hat
eingebettete Schriften. PowerPoint kann bei fehlendem DejaVu Sans eine
Ersatzschrift verwenden. Die PPTX-Prüfung ist daher eine Struktur-/Layoutprüfung,
kein vollständiger Office-Kompatibilitätstest.

## Reproduzierbarkeit und Werkzeuge

Die Erzeugung verwendet `python-pptx`, `Pillow` und `ReportLab`. Diese Pakete wurden
in die lokale Projekt-venv installiert; `pyproject.toml` und `requirements.txt`
wurden dafür nicht geändert. Das Skript erstellt Folien, PDF, Begleittext,
Vorschauen und Quelleninventar gemeinsam. Bereits vorhandene Spieltests wurden
unverändert ausgeführt.
