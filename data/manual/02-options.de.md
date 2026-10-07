# Optionen {#options}

`F10` (oder **Optionen** im Hauptmenü oder im Spielmenü) öffnet die Optionen. `Auf`/`Ab` wählen eine Zeile, `Eingabe`/`Links`/`Rechts` ändern sie, `Bild Auf`/`Bild Ab` oder `Tab` wechseln zwischen den beiden Seiten und `Esc` führt zurück. Mit der Maus ändert ein Klick auf eine Zeile sie wie `Eingabe`, die Schaltflächen **<** und **>** an ihrem rechten Ende stellen den Wert zurück oder weiter, und jede Taste in der Hinweiszeile darunter ist klickbar. Die Einstellungen liegen in `~/.u-jagd/settings.json`; eine laufende Mission läuft hinter den Optionen weiter.

![Optionen (F10)](figure:options)

## Seite 1: Bild, Ton und Realismus {#options-page1}

| Zeile | Auswahl |
|---|---|
| Sprache | Englisch, Deutsch |
| Vollbild | an, aus (auch `Alt+Eingabe`) |
| Audio | an, aus |
| Große Schrift | an, aus |
| Kurzinfos | an, aus: Erklärungen unter der Maus; ein Klick heftet eine an |
| Simulationsprotokoll | an, aus: schaltet die Ansicht `F4` frei (Kapitel Werkzeuge) |
| Rotlicht | Automatisch (Nacht, Alarm), Immer an, Aus |
| Farbschema | Taktik Nacht, Taktik Tag, Hoher Kontrast / farbenblind |
| Bildrate | 30 FPS (voreingestellt, spart Rechenleistung auf der uConsole) oder 60 FPS |
| Ereignislog / Telemetrie | Statuszeile (voreingestellt, mehr Platz für die Station; `F11` öffnet das Log) oder feste Leiste |
| Realismus | Einsteiger, Standard, Realistisch (unten) |
| Echtzeit-Verkehr | öffnet die Seite AIS / ADS-B (unten) |
| Commander / lokales Netz (F9) | öffnet die Remote-Crew-Seite (Kapitel Remote Crew) |

- **Rotlicht:** **Automatisch** (Standard) schaltet die Bildschirme nachts und bei Torpedo-, Flugkörper- oder Feueralarm auf gedimmtes Rot, **Immer an** oder **Aus**. Der Browser hat denselben Schalter in seinen Einstellungen. Die Stationsreiter zeigen eine Alarmlampe: gelb stetig für eine Warnung (Wassereinbruch, ein Ping, eine beschädigte Maschine), rot blinkend für Gefahr (Torpedo, Flugkörper, Feuer).
- **Farbschema:** **Taktik Nacht** (Standard: dunkle Flächen, Phosphorgrün, Bernstein und Rot), **Taktik Tag** (helle, entspiegelte Grautöne mit Marineblau und dunkler Schrift für Tageslicht; Wasserfall, LOFAR und DEMON zeichnen dann dunkle Spuren auf hellem Grund wie ein Schreiber) oder **Hoher Kontrast** (farbenblindfreundlich). Der Schalter rechts in der Kopfleiste wechselt per Klick zwischen Dunkel und Hell, an beiden Seiten. Leuchtet das Rotlicht, zeichnet die uConsole dunkel. Die Wahl liegt in `settings.json`, nie im Spielstand, und ändert nur das Bild. Der Browser hat einen eigenen Schalter.

### Realismusstufe {#options-realism}

Die Realismusstufe gilt für die nächste Mission:

- **Einsteiger:** Bedienerassistenz an (automatische Linienbeschriftung, Blattfrequenz- und Katalog- oder Senderkandidaten); der Computergegner greift zögerlicher an, wartet auf eine bessere Schusslösung und klassifiziert und startet als Fregatte seinen Hubschrauber 1,5-mal langsamer. Punkte 75 %.
- **Standard** (voreingestellt): Rohdaten und manuelle Analyse, der kalibrierte Gegner. Punkte 100 %.
- **Realistisch:** keine Assistenz; der Gegner greift entschlossener an, schießt auf eine gröbere Lösung und reagiert als Fregatte 30 % schneller. Punkte 125 %.

Die Stufe stimmt nur den Computergegner ab, nie einen Menschen auf der anderen Seite, und eine laufende Mission behält die Stufe, mit der sie begann (die Zeile sagt dann "ab der nächsten Mission"). Das Endpanel zeigt die Stufe mit ihrem Punktefaktor; Spielstände behalten sie.

### Echtzeit-Verkehr {#options-traffic}

Die Seite **Echtzeit-Verkehr** holt echte Schiffe (AIS Stream, braucht einen eigenen API-Schlüssel) und echte Flugzeuge (OpenSky ADS-B, wahlweise mit eigener OpenSky-Client-ID) in eine Mission, deren Welt ein reales Seegebiet ist. Sie braucht eine Internetverbindung; ohne sie sind die Zeilen ausgegraut. **API-Test** prüft beide Dienste. Platziert wird nur Verkehr bis etwa 150 sm um die Fregatte (höchstens 15 Schiffe und 5 Flugzeuge, zufällig gewählt; ein gewählter Kontakt bleibt, bis es das Gebiet verlässt), und Schiffspositionen werden alle 2 bis 5 Minuten nachgeführt. Ein Klick auf eine Zeile wirkt wie `Eingabe`: Er schaltet einen Dienst ein oder aus oder öffnet sein Feld. Änderungen gelten sofort und werden gespeichert.

## Seite 2: Spielaufbau {#options-page2}

**uConsole spielt:** welche Seite der uConsole spielt, Fregatte (Standard) oder feindliches U-Boot; nur im Hauptmenü, nie gespeichert. Ein neues Spiel fragt ohnehin zuerst danach. Siehe Kapitel U-Boot.

**Grafikstufe** (`Eingabe`/`Rechts` weiter, `Links` zurück): **Sparsam** skaliert mit einfachen Pixeln, lässt das Radar-Nachleuchten weg und beruhigt den Menühintergrund, um auf der uConsole Rechenzeit zu sparen; **Normal** (Standard der uConsole) zeigt alle Effekte; **Voll** (Standard unter Windows) glättet zusätzlich Peilstriche, Küste und Plot. In einem Fenster oder Vollbild deutlich größer als 1280 x 720 (ein PC-Monitor, ein 4K-Bildschirm) zeichnen Normal und Voll Schrift, Linien, Symbole und Karten in der Auflösung des Bildschirms, mit doppelt oder dreifach so vielen Pixeln wie auf der uConsole und genau gleichem Aufbau, und passen das Bild dann an den Bildschirm an; Sparsam skaliert stattdessen das 1280-x-720-Bild. Unter Windows nutzt das Spiel bei einer Anzeigeskalierung von 125 % oder 150 % die echten Bildschirmpixel (das Fenster behält seine Größe), statt das Bild von Windows strecken zu lassen; auf dem Mac nutzt es die echten Pixel des Retina-Bildschirms, statt das Bild von macOS strecken zu lassen. Der eigene Bildschirm der uConsole bleibt bei 1280 x 720. Die Stufe ändert nur das Bild, nie die Simulation oder was eine Station anzeigt.

**Automatisch sparsam** (`+ auto Sparsam` hinter Normal oder Voll, der Standard): Bleibt das Bild 5 Sekunden lang unter 14 Bildern pro Sekunde, zeichnet das Spiel von selbst mit Sparsam und zeigt in der oberen Leiste eine gelbe **ECO**-Lampe; der Hinweis über ihr sagt, warum und wie man es abschaltet. Eine erneut gewählte Grafikstufe beendet es; eine Stufe ohne `+ auto` schaltet das automatische Sparen ab. Es beobachtet nur das Bild und ändert nie die Simulation.

Die **gesprochenen Crew-Meldungen** (standardmäßig aus): die Crew meldet Torpedo im Wasser, neuen Kontakt mit Peilung, Sinkgeräusche, Torpedo los, Treffer, Gefechtsstationen, Seefernaufklärer auf Station und das Missionsende laut, Peilungen Ziffer für Ziffer. Die uConsole spricht über ein installiertes `espeak-ng` (`sudo apt install espeak-ng`) und bleibt ohne es stumm, oder mit natürlicher Stimme, wenn der Sprachdienst des Sprachmodells eingerichtet ist (Kapitel Sprachmodell, Stimme); Remote-Crew-Browser haben einen eigenen Schalter unter Einstellungen (Sprachausgabe des Browsers, in dessen Sprache). Spielt die uConsole das U-Boot, meldet stattdessen dessen Crew (siehe Kapitel U-Boot).

**Mikrofon** (aus als Vorgabe) lässt die Stimmen der Spieler für die Geräuschdisziplin zählen (unten). **Sprachmodell** öffnet die Einstellungen des optionalen Sprachmodells (Kapitel Sprachmodell).

## Geräuschdisziplin und Mikrofon {#ref-noise}

- Ab und zu lässt eine Besatzung ein Werkzeug fallen, schlägt ein Schott zu, stößt an einen Topf oder lässt eine Kette rasseln: ein kurzer metallischer Schlag für 3 s, der das eigene Geräusch erhöht. Eine frische Besatzung patzt etwa zweimal in der Stunde, eine müde oder entmutigte bis fünfmal so oft. Schleichfahrt (der Leisemodus der Fregatte, die Schleichfahrt des U-Boots oder das Liegen auf Grund) senkt das auf 30 %, dafür gehen Reparaturen und Nachladen dann nur mit 75 % voran.
- Bis 4 sm hört der Gegner einen solchen Schlag in seiner Peilung (durch das eigene Maschinengeräusch weniger): Das Sonar der Fregatte meldet einen metallischen Transienten, der Horchraum des U-Boots einen Transienten. Die eigene Besatzung meldet ihr Missgeschick unter Schleichfahrt.

**Mikrofon:** Auch die Stimmen der Spieler zählen. Auf der uConsole ist es die Option *Mikrofon* (aus als Vorgabe); im Browser der Knopf *Mikrofon an* neben dem Ton-Knopf (fragt nach dem Mikrofon). Browser geben das Mikrofon nur einer sicheren Seite: Auf der normalen LAN-Seite (`http://`) sagt das ein Hinweis, und *HTTPS-Seite öffnen* gibt Ihre Stationen frei und öffnet die HTTPS-Adresse des Hosts (Port + 1), wo Sie die Zertifikatswarnung einmal bestätigen und sich mit demselben Code neu koppeln.

Geht das Mikrofon nicht, sagt das Spiel warum: eine Meldung im Einsatz und die Ursache auf Seite 2 der Optionen (kein Mikrofon, lässt sich nicht öffnen oder kein Ton, weil Windows oder macOS den Zugriff sperrt; dort den Mikrofonzugriff für Desktop-Apps oder für U-Jagd erlauben). Ein abgelehntes, fehlendes oder belegtes Mikrofon nennt der Browser im selben Hinweis.

Eine Anzeige aus 20 Feldern zeigt den eigenen Pegel gegen die Schwellen: bis 5 leise (grün, ungehört), 6 bis 11 in der Nähe hörbar (gelb), ab 12 weit hörbar (rot, bei voller Lautstärke bis 2,5 sm). Auf der uConsole steht die Anzeige rechts neben der Statuszeile hinter einem Mikrofonzeichen; unbeleuchtete Felder sind abgedunkelt. Das Feld mit der kleinen Marke darunter ist die lauteste Stimme der Besatzung. Eine Stimme über der Schwelle erhöht das eigene Geräusch um bis zu 20 %; der Gegner hört Stimmen, und die eigene Besatzung wird zur Ruhe ermahnt, wenn es viel zu laut ist. Nur die Pegelzahl verlässt den Browser, nie Ton; sie gilt 1,5 s und wird nie gespeichert.
