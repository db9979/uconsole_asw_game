# 10 U-Boot {#submarine}

## Überblick {#sub-overview}

Eine zweite Crew kann das U-Boot auf der uConsole oder im Browser spielen (Lobby, `F9` oder ein neues Spiel als U-Boot). Das Boot hat sieben Stationen; jeder Befehl wird nur von der Station angenommen, der er gehört, und eine KI besetzt jede freie Station, wenn die Crew-Hilfe an ist. Dieses Kapitel nennt Aufgabe und Standardablauf jeder Station; die Tastentabelle und die Einsätze des Bootes stehen im Kapitel Referenz (*Bemanntes gegnerisches U-Boot*).

## Kommandant {#sub-command}

Der Kommandant sieht das ganze Boot: Karte, Navigation, Waffen und Kontakte, das Sehrohr und die Bedrohungsseite. Er befiehlt Kurs, Fahrt und Tiefe, legt das Boot auf Grund, pingt, nimmt ein BT und weicht auf den frischesten Alarm aus.

<!-- sop:uboot_command -->

## Sonar {#sub-sonar}

Der Sonarraum des U-Boots arbeitet wie der der Fregatte, ohne Schleppsonar, OPZ-Freigabe, Plot und Telegraph. Achteraus ist das Rumpfsonar in der Hecklücke taub.

<!-- sop:uboot_sonar -->

## Waffen {#sub-weapons}

Die Waffenstation lädt und flutet die Rohre, stellt Lauftiefe und Fächer ein, schießt auf einen gewählten Kontakt oder eine eingegebene Peilung, lenkt die drahtgelenkten Torpedos und stößt Täuschkörper aus. Die Seite hat neben der Karte zwei Spalten: Kontaktkarten (ein Klick wählt einen Kontakt) über der Schusslage sowie die Feuerleitung über den Rohrlampen. Der Feuerleitkasten zeigt die Suchkopf-Einstellung der nächsten Schüsse; an der Waffenstation feuert ein Klick auf das rote Feuerfeld wie `Strg+Enter`.

<!-- sop:uboot_weapons -->

## Maschinenraum {#sub-engine}

Der Maschinenraum fährt Telegraph, Schnorchel und Laderate, Schleichfahrt, die Trimmzellen und das Notanblasen, hält die Luft atembar und führt die Leckwehrtrupps.

<!-- sop:uboot_engine -->

## Mast & ESM {#sub-esm}

Mast & ESM fährt den Mast an Sehrohrtiefe aus, hört auf der ESM-Rose nach Radaren, klassifiziert die Sender, plottet Kreuzpeilungen und schaut durchs Sehrohr. Ein Klick auf eine Zeile der Senderliste wählt diesen Sender, wie ↑/↓.

<!-- sop:uboot_esm -->

## Navigation {#sub-nav}

Die Navigation befiehlt Kurs und Tiefe, achtet auf Kiel und Untiefen auf Lotsenkarte und Echolot, führt die Koppelnavigation und steuert die Route.

<!-- sop:uboot_nav -->

## Funkraum {#sub-radio}

Der Funkraum schreibt die Sendungen des HQ mit, liest Befehle und Kontaktmeldungen des HQ und sendet Lagemeldungen.

<!-- sop:uboot_radio -->

## Koppelnavigation und Route {#sub-dead-reckoning}

- Getaucht kennt das Boot seinen Ort nur durch Koppeln. Der gekoppelte Ort wandert vom wahren Ort weg: durch eine gleichmäßige Versetzung bis 0,4 kn, die Log und Kreisel nicht sehen (die Trägheitsnavigation eines Atomboots wandert nur 0,3-mal so viel), dazu einmal pro Minute ein kleiner Zufallsschritt; der Fehler bleibt unter 8 sm.
- Die Karte der Crew (Küste, Tiefen, Hindernisse, Einsatzziel, HQ-Meldungen und Route) liegt dort, wo der Navigator sie gegenüber dem Boot vermutet. Das Boot selbst, seine eigenen Sonarkontakte und eigenen Torpedos bleiben dort, wo das Boot sie misst.
- Ein GPS-Fix: 20 s Mast oben an Sehrohrtiefe setzen den gekoppelten Ort wieder auf den wahren. Die Lampe **Koppelort** auf der Seite Karte & Echolot zeigt die eigene Fehlerschätzung des Navigators und die Minuten seit dem Fix oder den laufenden Fix.
- Kartencheck voraus und Route rechnen vom gekoppelten Ort; ein alter Fix kann das Boot so in Wasser führen, das die Karte für frei hält.
- Die Route: ein Rechtsklick auf die Karte setzt einen Wegpunkt (höchstens 8), `W` legt eine Zickzack- oder Quadratsuche ab dem Boot und schaltet weiter bis aus, `Rücktaste` löscht sie. Jeder Kursbefehl vom Ruder und jedes Ausweichen beendet die Route; das Klären der Hecklücke hat das Ruder, solange es läuft. Im Browser macht **Wegpunkte auf der Karte setzen** Klicks auf die Karte zu Wegpunkten.

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
- Der Plot behält seine Marken dort, wo sie gegenüber dem Boot gezeichnet wurden; er wandert mit einem Fix nicht mit.
- Keine eigene Zentrale und kein LI-Platz; Trimm und Ballast bleiben beim Maschinenraum.
