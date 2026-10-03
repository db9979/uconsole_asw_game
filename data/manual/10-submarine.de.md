# 10 U-Boot {#submarine}

## Überblick {#sub-overview}

Eine zweite Crew kann das U-Boot auf der uConsole oder im Browser spielen (Lobby, `F9` oder ein neues Spiel als U-Boot). Das U-Boot hat sieben Stationen; jeder Befehl wird nur von der Station angenommen, der er gehört, und eine KI besetzt jede freie Station, wenn die Crew-Hilfe an ist. Dieses Kapitel nennt Aufgabe und Standardablauf jeder Station; die Tastentabelle und die Einsätze des U-Bootes stehen im Kapitel Referenz (*Bemanntes gegnerisches U-Boot*).

Auf der uConsole wechseln `1` bis `7` die Stationen, dieselbe Zahl noch einmal (oder `Bild↑`/`Bild↓`) blättert die Seiten der Station. Jede Station hat unten eine Tastenleiste; ein Klick auf eine Taste dort, auf eine Lampe oder eine Skala wirkt wie die Taste. Die vollständige Tastentabelle steht im Referenzkapitel (*Das U-Boot auf der uConsole spielen*); die Browser-Stationen haben dieselben Befehle als Schaltflächen.

| Station | Seiten |
|---|---|
| 1 Führung | Navigation, Waffen & Kontakte, Sehrohr, Bedrohung |
| 2 Sonar | Breitband, LOFAR, DEMON, TMA, Umwelt, Aktiv (wie das Sonar der Fregatte) |
| 3 Waffen | Rohre und Feuerleitung |
| 4 Maschine | Anlage, Vorräte, Zellen, Leckwehr |
| 5 Mast & ESM | ESM, Sehrohr |
| 6 Navigation | Karte & Echolot, Navigation, Bedrohung |
| 7 Funk | Funk |

## Führung {#sub-command}

Die Führung sieht das ganze U-Boot: Karte, Navigation, Waffen und Kontakte, das Sehrohr und die Bedrohungsseite. Sie befiehlt Kurs, Fahrt und Tiefe, legt das U-Boot auf Grund, pingt, nimmt ein BT und weicht auf den frischesten Alarm aus.

- **Navigation (Seite 1):** die Karte mit den eigenen Kontakten und Peillinien, die Skalen für Kurs, Fahrt und Tiefe und der Tiefenbalken. `C`, `V` und `D` befehlen Kurs, Fahrt und Tiefe; `U`, `J` und `H` gehen auf Sehrohr-, Unter-Schicht- oder tiefe Tiefe (mit `Umschalt` Schnorchel- und Über-Schicht-Tiefe); ein Klick auf eine Skala befiehlt diesen Wert.
- **Waffen & Kontakte (Seite 2):** die Rohre und die Kontaktliste, wie die Waffenstation sie sieht, um den Angriff mitzuverfolgen.
- **Sehrohr (Seite 3):** der Blick durch den Kopf auf Sehrohrtiefe mit ausgefahrenem Mast. `←`/`→` schwenken, `↑`/`↓` neigen, `Q`/`E` schalten schwache und starke Vergrößerung, `Leertaste` den Stabilisator; `Enter` nimmt eine Stadimeter-Entfernung der Sichtung unter dem Fadenkreuz, `Strg+Enter` schießt auf die Lösung des Angriffsrechners.
- **Bedrohung (Seite 4):** die jüngsten Pings, Torpedogeräusche und Radarauffassungen mit ihren Peilungen. `I` weicht dem jüngsten Alarm aus, `Strg+B` klärt die Hecklücke, `G` ruft Gefechtsstationen.
- Im Browser pingt die Führung auch und nimmt ein BT; auf der uConsole macht das der Sonarraum (`2`, `Umschalt+A`).

![U-Boot-Führung auf der uConsole](figure:uboot-command)

<!-- sop:uboot_command -->

## Sonar {#sub-sonar}

Der Sonarraum des U-Boots arbeitet wie der der Fregatte, ohne Schleppsonar, OPZ-Freigabe, Plot und Telegraph. Achteraus ist das Rumpfsonar in der Hecklücke taub.

- Die sechs Seiten und ihre Tasten sind die des Fregattensonars (Kapitel 2): Breitband-Wasserfall, LOFAR-Linien, DEMON-Wellendrehzahl, TMA, Umwelt mit BT, aktive Pings mit `Umschalt+A`.
- Das Rumpfsonar horcht in der eigenen Tiefe: über der Schicht hört es Überwasserschiffe gut, darunter ist es gegen sie abgeschirmt. Achteraus liegt die taube Hecklücke; deshalb ab und zu bei der Führung ein Klären der Hecklücke anfordern.

![U-Boot-Sonar](figure:uboot-sonar)

<!-- sop:uboot_sonar -->

## Waffen {#sub-weapons}

Die Waffenstation lädt und flutet die Rohre, stellt Lauftiefe und Fächer ein, schießt auf einen gewählten Kontakt oder eine eingegebene Peilung, lenkt die drahtgelenkten Torpedos und stößt Täuschkörper aus. Der Feuerleitkasten zeigt die Suchkopf-Einstellung der nächsten Schüsse.

- **Rohre:** jedes Rohr ist leer, geladen (trocken) oder geflutet; nur ein geflutetes Rohr feuert. `M` lädt das nächste leere Rohr, `Strg+M` flutet das nächste geladene langsam (60 s, kaum hörbar), `Umschalt+M` schnell (20 s, laut).
- **Feuerleitung:** `↑`/`↓` wählen einen Kontakt mit frischer Entfernung, `T` stellt die Lauftiefe, `Y` Einzelschuss oder Zweierfächer, `X` das Suchmuster und `,`/`.` den Scharfschaltpunkt; `Strg+Enter` schießt. `F` schießt ohne Kontakt auf eine eingegebene Peilung und Entfernung.
- **Draht und Täuschkörper:** `W` lenkt den jüngsten drahtgelenkten Torpedo auf eine neue Peilung, `Umschalt+W` kappt den Draht; `V` stößt einen Täuschkörper aus.

![U-Boot-Waffen](figure:uboot-weapons)

<!-- sop:uboot_weapons -->

## Maschinenraum {#sub-engine}

Der Maschinenraum fährt Telegraph, Schnorchel und Laderate, Schleichfahrt, die Trimmzellen und das Notanblasen, hält die Luft atembar und führt die Leckwehrtrupps.

- **Anlage (Seite 1):** Telegraph (`+`/`-`), Schleichfahrt (`A`, höchstens 5 kn), Schnorchel (`N`) und die Werte von Batterie, Diesel und E-Maschine.
- **Vorräte (Seite 2):** Batterie, Kraftstoff, Kohlendioxid und Sauerstoff. `R` schaltet die Laderate beim Schnorcheln (voll, halb, nur Luft), `Umschalt+O` setzt einen frischen Absorbersatz ein, `O` zündet eine Sauerstoffkerze.
- **Zellen (Seite 3):** Regel- und Trimmzellen. `↑`/`↓` lenzen oder fluten die Regelzelle, `←`/`→` verschieben Trimmwasser, `Z` schaltet die Trimmautomatik; `Umschalt+B` ist das einmalige Notanblasen.
- **Leckwehr (Seite 4):** die Abteilungen mit Wasser, Lecks, Feuer und Gas. `↑`/`↓` wählen eine Abteilung, `←`/`→` eine Aufgabe, `Enter` schickt Trupp 1 (`Umschalt+Enter` Trupp 2), `I` schließt oder öffnet ihre Schotten; `W`, `M` und `U` lösen die Wache ab, schicken den Sanitätstrupp und besetzen die am schwersten getroffene Station neu.

![U-Boot-Maschine](figure:uboot-engine)

![U-Boot-Leckwehr (Maschine, Seite 4)](figure:uboot-damage-control)

![U-Boot-Maschine im Remote-Crew-Browser](figure:web-uboot-engine-desktop)

<!-- sop:uboot_engine -->

## Mast & ESM {#sub-esm}

Mast & ESM fährt den Mast an Sehrohrtiefe aus, hört auf der ESM-Rose nach Radaren, klassifiziert die Sender, plottet Kreuzpeilungen und schaut durchs Sehrohr.

- **ESM (Seite 1):** mit ausgefahrenem Mast (`P`, nur auf Sehrohrtiefe) zeigt die Rose jedes gehörte Radar mit Peilung und Pegel. `↑`/`↓` wählen einen Sender, `←`/`→` klassifizieren ihn aus der Bibliothek (eine Anmerkung, nie die Wahrheit), `Enter` gibt seine Kreuzpeilung oder Peillinie in den Plot des U-Boots. Ein Hauptkeulentreffer heißt, dass das Radar den Mast womöglich schon sieht.
- **Sehrohr (Seite 2):** dasselbe Sehrohr wie Seite 3 der Führung, ohne Schuss.

![Mast/ESM](figure:uboot-mast-esm)

![Sehrohr bei Tag](figure:uboot-periscope-day)

![Sehrohr bei Nacht](figure:uboot-periscope-night)

![Sehrohr im Remote-Crew-Browser](figure:web-periscope-day)

<!-- sop:uboot_esm -->

## Navigation {#sub-nav}

Die Navigation befiehlt Kurs und Tiefe, achtet auf Kiel und Untiefen auf Lotsenkarte und Echolot, führt die Koppelnavigation und steuert die Route.

- **Karte & Echolot (Seite 1):** die Lotsenkarte um das U-Boot mit Tiefen, Untiefen und Land, das Echolot mit dem Wasser unter dem Kiel und die Lampe für den Koppelort. Ein Linksklick befiehlt den Kurs zu diesem Punkt.
- **Navigation (Seite 2):** die Lagekarte wie Seite 1 der Führung; ein Rechtsklick setzt einen Wegpunkt, `W` legt eine Zickzack- oder Quadratsuche, `Rück` löscht die Route.
- **Bedrohung (Seite 3):** wie die Bedrohungsseite der Führung; `I` weicht aus, `Umschalt+G` legt das U-Boot in flachem Wasser auf Grund.

![U-Boot-Navigation](figure:uboot-navigation)

<!-- sop:uboot_nav -->

## Funkraum {#sub-radio}

Der Funkraum schreibt die Sendungen des HQ mit, liest Befehle und Kontaktmeldungen des HQ und sendet Lagemeldungen.

- Die Seite zeigt, wann die nächste Sendung des HQ kommt, ob eine Antenne oben ist (Mast `P` auf Sehrohrtiefe oder die Schleppbojenantenne `B` bis 60 m bei höchstens 6 kn), die Befehle und Kontaktmeldungen des HQ und das Protokoll.
- `Enter` sendet eine Lagemeldung; dazu muss der Mast oben sein, und die Fregatte kann sie mit KW-Peilung orten.

![U-Boot-Funkraum](figure:uboot-radio)

<!-- sop:uboot_radio -->

## Koppelnavigation und Route {#sub-dead-reckoning}

- Getaucht kennt das U-Boot seinen Ort nur durch Koppeln. Der gekoppelte Ort wandert vom wahren Ort weg: durch eine gleichmäßige Versetzung bis 0,4 kn, die Log und Kreisel nicht sehen (die Trägheitsnavigation eines Atomboots wandert nur 0,3-mal so viel), dazu einmal pro Minute ein kleiner Zufallsschritt; der Fehler bleibt unter 8 sm.
- Die Karte der Crew (Küste, Tiefen, Hindernisse, Einsatzziel, HQ-Meldungen und Route) liegt dort, wo der Navigator sie gegenüber dem U-Boot vermutet. Das U-Boot selbst, seine eigenen Sonarkontakte und eigenen Torpedos bleiben dort, wo das U-Boot sie misst.
- Ein GPS-Fix: 20 s Mast oben an Sehrohrtiefe setzen den gekoppelten Ort wieder auf den wahren. Die Lampe **Koppelort** auf der Seite Karte & Echolot zeigt die eigene Fehlerschätzung des Navigators und die Minuten seit dem Fix oder den laufenden Fix.
- Kartencheck voraus und Route rechnen vom gekoppelten Ort; ein alter Fix kann das U-Boot so in Wasser führen, das die Karte für frei hält.
- Die Route: ein Rechtsklick auf die Karte setzt einen Wegpunkt (höchstens 8), `W` legt eine Zickzack- oder Quadratsuche ab dem U-Boot und schaltet weiter bis aus, `Rücktaste` löscht sie. Jeder Kursbefehl vom Ruder und jedes Ausweichen beendet die Route; das Klären der Hecklücke hat das Ruder, solange es läuft. Im Browser macht **Wegpunkte auf der Karte setzen** Klicks auf die Karte zu Wegpunkten.

## Torpedo-Suchkopf {#sub-seeker}

- `X` schaltet das Suchmuster der nächsten Schüsse weiter: gerade (wie bisher), Schlange, Kreis oder Helix. Der Torpedo läuft gerade zum Datum; ist sein Suchkopf an und hat nichts gefunden, sucht er in diesem Muster.
- `,` und `.` verschieben den Einschaltpunkt zwischen 0,6 und 3,0 sm vor dem Datum in Schritten von 0,2 sm (Vorgabe 3,0 sm). Ein später Einschaltpunkt hält den Suchkopf länger blind, so dass er Täuschkörper und andere Schiffe auf dem Weg nicht nimmt.
- Ein Torpedo im Wasser behält die Einstellung, mit der er geschossen wurde; die Waffen-Karte im Browser stellt beides mit **Anwenden** ein.

## Auftauchen und Alarmtauchen {#sub-surface}

- `Shift+H` (Browser: **Auftauchen**, Kommando oder Navigation) lässt das U-Boot an die Oberfläche gehen. Bei 2 m oder weniger ist es aufgetaucht: Das Niederdruckgebläse bläst die Hauptzellen in 2 Minuten aus (ohne Pressluft aus den Flaschen), das Luk ist offen und das U-Boot lüftet sich.
- Aufgetaucht laufen die Diesel (`N`) an der freien Luft: bis 12 kn (oder die Höchstfahrt des U-Boots) statt 6 kn am Schnorchel, und der Generator gibt das 1,3-fache seiner Schnorchelleistung, die Batterie lädt also schneller.
- Die Brückenwache sieht aus 6 m statt aus den 2,5 m des Sehrohrs und damit weiter; ihre Meldungen beginnen mit **Brücke:**, ein Flugzeug meldet sie als Alarm. Die Sehrohrseite zeigt den Blick der Brückenwache.
- Auch der Gegner sieht ein aufgetauchtes U-Boot: Das Überwasserradar der Fregatte und die Radare von Hubschrauber und Seefernaufklärer sehen Rumpf und Turm (das Zehnfache des Echos eines Masts), Ausgucks sehen es mit dem Auge.
- `H` von der Oberfläche oder mit ausgeblasenen Zellen (Browser: **Alarmtauchen**) ist das Alarmtauchen: Alarm, Masten und Schnorchel ein, Flutventile auf, äußerste Kraft, befohlene Tiefe 40 m. Ausgeblasene Zellen halten das U-Boot über 10 m, bis die Flutventile sie geflutet haben (bis 40 s), und das Fluten ist ein Geräusch, das der Gegner hören kann. Aus mehr als 12 m Tiefe wird Alarmtauchen abgelehnt.

## Nicht modelliert {#sub-limits}

- Keine Ortsbestimmung über Landmarken, Lotungen oder Sterne; nur GPS löscht den Koppelfehler.
- Der Plot behält seine Marken dort, wo sie gegenüber dem U-Boot gezeichnet wurden; er wandert mit einem Fix nicht mit.
- Keine eigene Zentrale und kein LI-Platz; Trimm und Ballast bleiben beim Maschinenraum.
