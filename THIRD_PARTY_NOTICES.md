# Drittanbieterhinweise

U-Jagd selbst steht unter der MIT-Lizenz. Die folgenden Laufzeitabhängigkeiten
werden nicht als Quellcode in diesem Repository geführt, sondern bei der
Installation separat bezogen. Sie unterliegen ihren eigenen Lizenzbedingungen.

## Python-Pakete

| Komponente | Verwendung | Projekt / Lizenzhinweis |
|---|---|---|
| Pygame | Fenster, Eingabe, Rendering und Audioausgabe | <https://www.pygame.org/>; überwiegend GNU LGPL 2.1, einzelne eingebundene Komponenten können abweichende kompatible Lizenzen besitzen |
| NumPy | numerische Berechnung und Audiosynthese | <https://numpy.org/>; BSD-3-Clause mit zusätzlichen Hinweisen für gebündelte Komponenten |

Die maßgeblichen Lizenztexte werden von den installierten Distributionen
mitgeliefert. Vor einer Weitergabe eines gebauten Pakets sind deren
Distributionsdateien und Lizenzverzeichnisse in der konkret verwendeten Version
zu prüfen und beizubehalten.

## Projektinhalte und Assets

- Das Repository enthält derzeit keine übernommenen Bild-, Audio- oder
  Schriftdateien Dritter.
- Sonar-, Maschinen- und Alarmklänge werden zur Laufzeit algorithmisch aus
  NumPy-Signalen synthetisiert. Anzeigen und Symbole werden durch Projektcode
  gezeichnet; es werden keine vorgerenderten Medien ausgeliefert.
- `data/contacts/*.json` enthält für das Spiel erstellte Modellprofile. Namen
  realer oder realistisch anmutender Plattformklassen bezeichnen keine
  Übernahme geschützter Herstellerdaten und keine technische Verifikation.
- `data/coastlines/region.json` ist eine stilisierte, projektspezifische
  Spielkarte und keine reale Navigations- oder Vermessungsquelle.

Für später hinzugefügte Medien gelten die Dokumentationsanforderungen in
[`assets/README.md`](assets/README.md). Markennamen und Produktnamen gehören
gegebenenfalls ihren jeweiligen Inhabern; ihre Nennung bedeutet keine
Verbindung, Billigung oder Empfehlung.
