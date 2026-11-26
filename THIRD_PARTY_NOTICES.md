# Drittanbieterhinweise

U-Jagd selbst steht unter der PolyForm Strict License 1.0.0 (siehe `LICENSE`). Die folgenden Laufzeitabhängigkeiten
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

- Das Repository enthält keine übernommenen Bild- oder Audiodateien Dritter.
  Übernommene Schriftdateien sind ausschließlich die unten unter
  „Schriften der Web-Oberfläche“ und „Schrift der uConsole-Oberfläche“
  aufgeführten.
- Sonar-, Maschinen- und Alarmklänge werden zur Laufzeit algorithmisch aus
  NumPy-Signalen synthetisiert. Anzeigen und Symbole werden durch Projektcode
  gezeichnet; es werden keine vorgerenderten Medien ausgeliefert.
- `data/unit_models/tiefenkontakt.json.gz` und `data/commander/js/views/tk/*.js`
  enthalten die vereinfachten Schiffs- und U-Boot-Modelle aus Tiefenkontakt
  (<https://github.com/db9979/tiefenkontakt>, MIT-Lizenz, Copyright (c) 2026
  db9979, derselbe Autor wie U-Jagd), erzeugt mit
  `tools/tiefenkontakt/export_models.mts` und `tools/build_tk_models.py`;
  der verwendete Commit steht in der Datei.
- `src/ui/ocean.py` und `data/commander/js/views/ocean.js` sind eine
  Übertragung der Wasseroberfläche von Tiefenkontakt (Wellenzüge aus
  `waves.ts`, Schattierung aus dem Ozean-Shader; MIT-Lizenz, siehe oben) in
  einen 2D-Zeichner. `src/ui/skyshade.py` und `data/commander/js/views/sky.js`
  übertragen ebenso den Himmel von Tiefenkontakt (Himmels-Shader aus
  `sky.ts`: Wolkendecke, Zirren, Sonnenhof, Dunstband; MIT-Lizenz).
- `data/sky/bright_stars.json` und `data/commander/js/views/star-catalog.js`
  enthalten die 986 Sterne heller als 4,6 mag aus dem Yale Bright Star
  Catalogue, 5. revidierte Ausgabe (Hoffleit & Warren 1991, VizieR V/50,
  NASA/ADC, gemeinfrei), wie Tiefenkontakt sie packt (MIT-Lizenz), kopiert mit
  `tools/build_star_catalog.py`; der verwendete Commit steht in der Datei.
  `src/ui/stars.py` und `data/commander/js/views/stars.js` übertragen den
  Sternhimmel von Tiefenkontakt (`astro.ts`, `stars.ts`, Milchstraße aus
  `sky.ts`; MIT-Lizenz).
- `data/contacts/*.json` enthält für das Spiel erstellte Modellprofile. Namen
  realer oder realistisch anmutender Plattformklassen bezeichnen keine
  Übernahme geschützter Herstellerdaten und keine technische Verifikation.
- `data/coastlines/region.json` ist die feste, stilisierte Legacy-Kartenoption
  und keine reale Navigations- oder Vermessungsquelle.

## Schriften der Web-Oberfläche

Die Remote-Crew-Weboberfläche (`data/commander/fonts/`) liefert zwei
Schriftfamilien unverändert aus den offiziellen Release-Archiven aus. Beide
stehen unter der SIL Open Font License 1.1. Die Lizenztexte liegen jeweils
neben den Schriftdateien und werden mit Wheel und sdist ausgeliefert. Die
Schriften werden nicht verkauft, nicht umbenannt und nicht verändert
(kein Subsetting).

| Komponente | Dateien | Quelle und Fixierung |
|---|---|---|
| Inter 4.1, © 2016 The Inter Project Authors, OFL-1.1 | `inter-variable.woff2` (= `web/InterVariable.woff2`), `ofl-inter.txt` (= `LICENSE.txt`) | <https://github.com/rsms/inter/releases/download/v4.1/Inter-4.1.zip>, Archiv-SHA-256 `9883fdd4a49d4fb66bd8177ba6625ef9a64aa45899767dde3d36aa425756b11e`; Datei-SHA-256 `693b77d4f32ee9b8bfc995589b5fad5e99adf2832738661f5402f9978429a8e3` |
| JetBrains Mono 2.304, © 2020 The JetBrains Mono Project Authors, OFL-1.1 | `jetbrains-mono-regular.woff2`, `jetbrains-mono-bold.woff2` (= `fonts/webfonts/JetBrainsMono-{Regular,Bold}.woff2`), `ofl-jetbrains-mono.txt` (= `OFL.txt`) | <https://github.com/JetBrains/JetBrainsMono/releases/download/v2.304/JetBrainsMono-2.304.zip>, Archiv-SHA-256 `6f6376c6ed2960ea8a963cd7387ec9d76e3f629125bc33d1fdcd7eb7012f7bbf`; Datei-SHA-256 `a9cb1cd82332b23a47e3a1239d25d13c86d16c4220695e34b243effa999f45f2` (Regular), `c503cc5ec5f8b2c7666b7ecda1adf44bd45f2e6579b2eba0fc292150416588a2` (Bold) |

## Schrift der uConsole-Oberfläche

Die Pygame-Oberfläche (`data/fonts/`) zeichnet alle Texte mit JetBrains Mono
2.304, damit jede Plattform dieselben Zeichenbreiten und Zeilenhöhen hat.
Die TTF-Dateien stammen unverändert aus demselben offiziellen Release-Archiv
wie die Web-Schrift; Lizenz, Urheber und Bedingungen sind identisch
(SIL Open Font License 1.1, nicht verkauft, nicht umbenannt, nicht verändert).
Der Lizenztext liegt neben den Schriftdateien und wird mit Wheel und sdist
ausgeliefert.

| Komponente | Dateien | Quelle und Fixierung |
|---|---|---|
| JetBrains Mono 2.304, © 2020 The JetBrains Mono Project Authors, OFL-1.1 | `jetbrains-mono-regular.ttf`, `jetbrains-mono-bold.ttf` (= `fonts/ttf/JetBrainsMono-{Regular,Bold}.ttf`), `ofl-jetbrains-mono.txt` (= `OFL.txt`) | <https://github.com/JetBrains/JetBrainsMono/releases/download/v2.304/JetBrainsMono-2.304.zip>, Archiv-SHA-256 `6f6376c6ed2960ea8a963cd7387ec9d76e3f629125bc33d1fdcd7eb7012f7bbf`; Datei-SHA-256 `a0bf60ef0f83c5ed4d7a75d45838548b1f6873372dfac88f71804491898d138f` (Regular), `5590990c82e097397517f275f430af4546e1c45cff408bde4255dad142479dcb` (Bold) |

## Geografische Daten

`data/coastlines/real_sectors.json.gz` ist ein abgeleitetes Laufzeit-Dataset.
Seine im Katalog eingebettete, reproduzierbare Provenienz lautet exakt:

| Quelle | Stand und Rechte | Fixierung |
|---|---|---|
| Natural Earth | `Natural Earth 1:10m Admin 0 Countries v5.1.1`; Public Domain | Commit `9380cca83db5f9aef52d5e762765100745f84b27`; SHA-256 `239eec57ac17f100a11e2536cffc56752c318b50ae765b0918ff7aab4ce8f255` (`geojson/ne_10m_admin_0_countries.geojson`); <https://github.com/nvkelso/natural-earth-vector> |
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

Seit 1.3.214 werden die Sektoren in zwei Schritten erzeugt (`build`, dann
`refine`). `build` wählt Sektoren, Mittelpunkte und Stützpunkte wie oben aus
`Natural Earth 1:50m Admin 0 Countries v5.1.1` (gleicher Commit, SHA-256
`3e458fc036ad0a66411f2c1e6cac49c5d7bfb81cb1123bc513b22511a2b7fdeb`); dieser
Zwischenkatalog hat SHA-256
`595b70d6b9290bfcb10a500f7d1be2162b6b5337fc7e7f0f6932dfe7bd8c6979` und liegt
als `data/coastlines/real_sectors.json.gz` von 1.3.205 in der Git-Historie.
`refine` behält Kennungen, Mittelpunkte, Stützpunkte und Reihenfolge und
zeichnet das Land jedes Sektors aus der 1:10m-Ausgabe neu (gleiche
Projektion und gleicher Zuschnitt, Douglas-Peucker-Vereinfachung mit
0,05 NM Toleranz); Ländernamen und Sektornamen werden daraus neu bestimmt.

Geografische, Länder- und Militärstützpunktnamen sowie die Stützpunktkoordinaten
stammen aus diesen Quellen. Die Gameplay-Rollen `friendly`, `hostile`, `neutral`
und `civil` werden unabhängig von realen Staaten deterministisch als fiktionale
Übungsrollen vergeben.

Seit 1.3.299 stammen Wassertiefen und Deckschicht aus
`data/coastlines/real_ocean.json.gz` (SHA-256
`e45f14140a16dd97fc671c1bf59d23aba262f8355e9114085243c9edfb7f61f1`, erzeugt
von `tools/build_real_ocean.py` am 2026-11-25):

| Quelle | Stand und Rechte | Verwendung |
|---|---|---|
| NOAA NGDC ETOPO1 | 1-Bogenminuten-Relief (Ice Surface), ERDDAP-Datensatz `etopo180`; Daten der US-Regierung, frei nutz- und weitergebbar | jeder dritte Gitterpunkt, Mittel der Wasserpunkte um jeden Punkt eines 33-x-33-Rasters je Sektor; <https://coastwatch.pfeg.noaa.gov/erddap/griddap/etopo180> |
| NOAA NCEI World Ocean Atlas 2023 | Temperatur, 1 Grad, Monatsmittel `decav` (`woa23_decav_tMMmn01.csv.gz`); Daten der US-Regierung, frei nutz- und weitergebbar | Oberflächentemperatur (Mittel) und Deckschichttiefe (Median, 0,5 Grad C unter der Oberfläche) je Sektor und Monat; <https://www.ncei.noaa.gov/products/world-ocean-atlas> |

Seit 1.3.302 stammen die Landhöhen der Küsten und Berge auf dem Horizont aus
`data/coastlines/real_relief.json.gz` (SHA-256
`aeeb96bc62f0ea9fa3bce27806ae09f27f48de4f8d15b245c59e86cc1ef4041a`, erzeugt
von `tools/build_real_relief.py` am 2026-11-26): NOAA NGDC ETOPO1 (ERDDAP-Datensatz
`etopo180`, Daten der US-Regierung, frei nutz- und weitergebbar), jeder zweite
Gitterpunkt (etwa 2 sm), nur Höhen über dem Meer, in Kacheln von 1 Grad um die
128 Sektoren. Die Landfarben (Sand, Gras, Fels, Schnee) folgen dem Gelände von
Tiefenkontakt (MIT-Lizenz, siehe oben).

Bis zu drei erfundene Untiefen je Sektor liegen weiterhin auf dem Schelf.
Ohne Eintrag (eigene Karten) bleibt die synthetische 17-x-17-Bathymetrie aus
Küstenabstand, trigonometrischer Variation und einem Sektor-Seed. Sämtliche
abgeleiteten Karten und Tiefen sind nicht für Navigation, Vermessung oder
reale Einsatzplanung geeignet.

Natural Earth, Wikidata, NOAA, ihre Beitragenden und Rechteinhaber sind weder mit
U-Jagd verbunden noch unterstützen, billigen oder empfehlen sie das Projekt.

Für später hinzugefügte Medien gelten die Dokumentationsanforderungen in
[`assets/README.md`](assets/README.md). Markennamen und Produktnamen gehören
gegebenenfalls ihren jeweiligen Inhabern; ihre Nennung bedeutet keine
Verbindung, Billigung oder Empfehlung.
