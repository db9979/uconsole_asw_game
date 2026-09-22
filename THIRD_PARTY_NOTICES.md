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
- `data/coastlines/region.json` ist die feste, stilisierte Legacy-Kartenoption
  und keine reale Navigations- oder Vermessungsquelle.

## Geografische Daten

`data/coastlines/real_sectors.json.gz` ist ein abgeleitetes Laufzeit-Dataset.
Seine im Katalog eingebettete, reproduzierbare Provenienz lautet exakt:

| Quelle | Stand und Rechte | Fixierung |
|---|---|---|
| Natural Earth | `Natural Earth 1:50m Admin 0 Countries v5.1.1`; Public Domain | Commit `9380cca83db5f9aef52d5e762765100745f84b27`; SHA-256 `3e458fc036ad0a66411f2c1e6cac49c5d7bfb81cb1123bc513b22511a2b7fdeb`; <https://github.com/nvkelso/natural-earth-vector> |
| Wikidata | `Wikidata airbase (Q695850) coordinate query snapshot`; CC0 1.0; abgerufen am `2026-09-06` | SHA-256 `f7126b7680afe9dcbb76ee8212ac82175e5b8e586f8fb3fafe57a071a8a6ffa9`; Abfrage: `?item wdt:P31/wdt:P279* wd:Q695850; wdt:P625 ?coord; optional P17` |

Die Build-Transformation lädt äußere Länderpolygone und englische bzw.
administrative Ländernamen, verwirft ohne topologisches Dateline-Splitting nicht
verarbeitbare Außenringe, projiziert Längen-/Breitengrade lokal
equirektangulär mit 60 NM je Breitengrad, schneidet und rundet Polygone auf
500 x 500 NM und entfernt sehr kleine Flächen. Kandidaten entstehen
deterministisch um reale Stützpunktkoordinaten. Es werden nur Sektoren mit
zusammenhängendem zentralem Fahrwasser, geeignetem Landanteil und mindestens
vier plausibel küstennahen Stützpunkten ausgewählt; eine 5-Grad-Zellenauswahl
begrenzt regionale Häufung. Pro Sektor bleiben höchstens zwölf stabil sortierte
Stützpunkteinträge. Das Ergebnis sind genau 128 vorvalidierte Sektoren; der Seed
wählt einen Katalogeintrag.

Geografische, Länder- und Militärstützpunktnamen sowie die Stützpunktkoordinaten
stammen aus diesen Quellen. Die Gameplay-Rollen `friendly`, `hostile`, `neutral`
und `civil` werden unabhängig von realen Staaten deterministisch als fiktionale
Übungsrollen vergeben. Bathymetrie stammt aus keiner geografischen Quelle: Sie
wird als 17-x-17-Raster synthetisch aus Küstenabstand, trigonometrischer
Variation und einem Sektor-Seed erzeugt. Sämtliche abgeleiteten Karten und
Tiefen sind nicht für Navigation, Vermessung oder reale Einsatzplanung geeignet.

Natural Earth, Wikidata, ihre Beitragenden und Rechteinhaber sind weder mit
U-Jagd verbunden noch unterstützen, billigen oder empfehlen sie das Projekt.

## Private Designreferenzen

Drei WaveOps-PDF-Dokumente wurden privat als Designreferenzen bereitgestellt.
Sie sind all-rights-reserved und nicht Bestandteil dieses Repositorys oder
eines Distributionspakets. Es werden weder Text noch Bilder, Gestaltung oder
Daten daraus gebündelt oder kopiert. Berücksichtigt wurde ausschließlich
abstrakte Inspiration für Arbeitsabläufe. Weitere Abgrenzung:
[`docs/design-references.md`](docs/design-references.md).

Für später hinzugefügte Medien gelten die Dokumentationsanforderungen in
[`assets/README.md`](assets/README.md). Markennamen und Produktnamen gehören
gegebenenfalls ihren jeweiligen Inhabern; ihre Nennung bedeutet keine
Verbindung, Billigung oder Empfehlung.
