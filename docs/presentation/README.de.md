# U-Jagd – Simulation und Abhängigkeiten

Ausführliche deutschsprachige Präsentation mit 60 Folien zum lokalen Arbeitsstand
vom 24. September 2026, Anwendungsversion 1.1.0. Die Darstellung umfasst
Architektur, Zeitsteuerung, Geografie und Umwelt, Schiffsphysik, Akustik und
Sensoren, TMA und Fusion, Gegner, Waffen, Schäden, Crew, Live-Verkehr und Persistenz.

## Dateien

- [PowerPoint-Präsentation](U-Jagd-Simulation.de.pptx): bearbeitbare Texte,
  Diagramme und vollständige Sprechernotizen mit Quellen pro Folie.
- [PDF-Präsentation](U-Jagd-Simulation.de.pdf): 60 Seiten mit durchsuchbarem
  Text, eingebetteten Schriften und Vektorgrafiken.
- [Sprechernotizen und Quellen](Sprechernotizen-und-Quellen.de.md): vollständiger,
  durchsuchbarer Begleittext einschließlich aller Folieninhalte.
- [Folienübersicht](Folienuebersicht.jpg): Kontaktbogen des gesamten Foliensatzes.
- [Quelleninventar](Quelleninventar.json): 116 Pythonmodule mit Symbolen,
  internen Imports und SHA-256; zusätzlich relevante Ressourcen und Tests.
- [Prüfprotokoll](Pruefprotokoll.de.md): ausgeführte Prüfungen und deren Grenzen.

## Verwendung

Der volle Vortrag ist für etwa 60–90 Minuten einschließlich Erläuterungen gedacht.
Als kürzerer Einstieg eignen sich die Folien 1–8, 11, 17, 22, 28–30, 33–34,
40, 44, 46, 48–50 und 55–59. Die Zeitangabe ist eine Vortragsempfehlung,
keine gemessene Spieldauer.

Die Quellen beziehen sich auf den vorliegenden lokalen Arbeitsbaum, einschließlich
bereits vorhandener Änderungen. Historische Dokumente wurden bei Abweichungen
nicht als aktueller Implementierungsvertrag übernommen. Besonders wichtig:
fester Echtzeitfaktor 1, externer Live-Verkehr als zusätzliche Eingangsgröße,
transiente Audiopuffer und manuelle OPZ-Fusion ohne allgemeine Triangulation.

Die Screenshots sind vorhandene Repository-Abbildungen. Die Diagramme wurden
für diese Dokumentation erstellt. Private Referenz-PDFs wurden nicht verwendet.
Die Aussagen über physikalische Näherungen beschreiben das implementierte
Spielmodell und dessen Grenzen.

## Erneut erzeugen

Benötigt werden `python-pptx`, `Pillow` und `reportlab` sowie die lokalen
DejaVu-Sans-Schriften. Diese Werkzeuge sind keine Spiel-Laufzeitabhängigkeiten.

```sh
.venv/bin/python docs/presentation/build_presentation.py
```

Das Skript legt die Dateien in diesem Verzeichnis neu an. Änderungen an Inhalten
erfolgen in der `SLIDES`-Definition des Skripts. Die Quellinventur wird beim
Erzeugen aktualisiert; Präsentationstexte werden dabei nicht automatisch aus
geändertem Spielcode neu interpretiert.

PowerPoint verwendet die Schrift DejaVu Sans. Die PDF bettet sie ein und ist die
stabile Ansicht für Systeme, auf denen diese Schrift nicht installiert ist.
