# Assets

Dieses Verzeichnis ist die vorgesehene Ablage für künftige Medien des Spiels.
Der aktuelle Stand benötigt keine externen Bild-, Schrift- oder Audiodateien:

- Oberfläche, CRT-Effekt und taktische Symbole werden zur Laufzeit mit Pygame
  gezeichnet.
- Sonar-Pings, Maschinenklang, Warnsignale und Kontaktgeräusche werden zur
  Laufzeit algorithmisch mit NumPy synthetisiert.
- Kontaktprofile und die stilisierte Küstenkarte liegen als Projektdaten unter
  `data/`, nicht als Medien in diesem Verzeichnis.

Damit enthält `assets/` derzeit absichtlich nur diese Dokumentation.

## Anforderungen für neue Assets

Für jede später hinzugefügte Datei müssen Herkunft, Urheber, Lizenz, erlaubte
Bearbeitungen und gegebenenfalls ein Link zur Quelle dokumentiert werden. Die
Angaben gehören in `THIRD_PARTY_NOTICES.md` oder in eine eindeutig zugeordnete
Begleitdatei. Dateien ohne nachvollziehbare Weitergaberechte dürfen nicht in
Release-Artefakte aufgenommen werden.

Bevorzugt werden offene Formate und Lizenzen, die eine Weitergabe zusammen mit
dem MIT-lizenzierten Projekt erlauben. Eine kompatible Lizenz ersetzt nicht die
erforderliche Namensnennung oder den Lizenztext des jeweiligen Assets.
