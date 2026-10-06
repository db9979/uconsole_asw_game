# Remote Crew und Mehrspieler {#multiplayer}

Remote Crew lässt Browser im lokalen Netz Stationen übernehmen. Die uConsole bleibt die einzige Simulation: Die Browser senden Befehle und zeigen das eigene Lagebild ihrer Station, das Spiel selbst rechnen sie nie. Ein Browser hält nur Stationen einer Einheit, Fregatte oder U-Boot.

## Mehrspieler-Lobby {#mp-lobby}

**Mehrspieler** (Hauptmenü): die Lobby, in der sich die Besatzung vor einem Einsatz trifft. Sie startet Remote Crew selbst im Crew-Modus und zeigt QR-Code, Adresse und Beitrittscode. Auf dem eigenen Hotspot des uConsole zeigt sie zwei nummerierte Schritte nebeneinander: **1** den WLAN-QR-Code mit WLAN-Name und Passwort (dem Hotspot beitreten), **2** den Seiten-QR-Code mit Adresse und Beitrittscode (die Crew-Seite öffnen).

Ein Browser, der bei offener Lobby koppelt, bekommt die erste freie Station der Einheit des uConsole, in dieser Reihenfolge: Fregatte Brücke, Sonar, Waffen, Hubschrauber, OPZ, EloKa, Funk, Maschine, Schadensabwehr; U-Boot Führung, Sonar, Waffen, Mast & ESM, Navigation, Maschine, Funkraum (zuerst die Stationen, die Urteil brauchen; die Routinestationen hält die KI-Crew gut). Die Browser können Einheit und Stationen jederzeit wechseln und drücken **Bereit**; sie sehen die Mission, was der uConsole spielt, und jedes Crewmitglied mit Stationen und Bereit-Häkchen.

Am uConsole wählen `Auf`/`Ab` eine Zeile und `Links`/`Rechts` ändern sie (mit der Maus stellt ein Klick ins linke Drittel einer Zeile zurück, sonst weiter): die Mission, die Einheit des uConsole und die Station, die er zeigt, oder **keine, nur Gastgeber**: Dann spielt der uConsole keine Station, die Browser können jede übernehmen, und die KI besetzt den Rest. **Mission für alle starten** startet einen Countdown von fünf Sekunden, den jeder Browser sieht; dann beginnt die Mission für alle gleichzeitig, und der uConsole öffnet seine gewählte Station. Ist ein Crewmitglied mit Station noch nicht bereit, fragt das erste `Eingabe` nach, ein zweites startet trotzdem. `Esc` bricht einen Countdown ab, sonst geht es zurück ins Hauptmenü, und Remote Crew läuft weiter.

Endet eine Mission, die aus der Lobby gestartet wurde, kehren alle mit ihren Stationen in die Lobby zurück; die Bereit-Häkchen beginnen wieder von vorn. Jede Mission aus der Lobby, an der ein Browser teilnimmt (oder mit nur Gastgeber), hat die Crew-Hilfe an (`Umschalt+F2`); allein startet sie als Solospiel mit ausgeschalteter Crew-Hilfe. `F9` öffnet aus der Lobby die vollständigen Remote-Crew-Einstellungen. Mit `--multiplayer` gestartet, öffnet das Spiel die Lobby direkt nach dem Startbild.

## Crew gegen Crew {#mp-versus}

**Crew gegen Crew** (Lobby-Zeile **Gegner**): *KI* (Standard) setzt jeden Browser wie oben auf die Einheit der uConsole; *zweite Crew* lässt zwei Teams gegeneinander spielen, die Crew der Fregatte gegen die des U-Boots.

Ein Browser, der dann koppelt, kommt in das Team mit weniger Menschen (bei Gleichstand die Fregatte, die mehr Stationen hat); die uConsole zählt für ihre Einheit, außer sie ist nur Gastgeber. Die Browser-Lobby zeigt beide Teams mit einem blauen (Fregatte) oder roten (U-Boot) Streifen. Hat ein Team niemanden, fragt das erste `Eingabe` nach, ein zweites startet trotzdem, und die KI besetzt diese Einheit.

Ab dem Start bleibt jeder Browser die ganze Runde in seinem Team: Er kann innerhalb seiner Einheit die Station wechseln, aber nie eine der anderen Einheit übernehmen. Jedes Team sieht nur das Lagebild der eigenen Einheit (wie immer), und im Web-Host-Raum hat jede Einheit ihren eigenen Sprechfunk, sodass eine Crew die andere nie hört. Am Ende nennt die Abschlusstafel das Ergebnis jeder Einheit aus ihrer eigenen Sicht („Fregatte: Sieg, U-Boot: Niederlage“), und jeder Browser bekommt das Ergebnis seiner Einheit in seine Ereignisliste.

Ist die uConsole in einer Runde Crew gegen Crew nur Gastgeber, zeigt sie statt einer Station die **Spielleitung**: Mission, Restzeit und wer welche Station beider Einheiten besetzt (ein Name oder KI), nie ein Lagebild, und sie spielt keine Sonar- oder Effektgeräusche; dort wirken nur `F1`, `F9` und `Esc`. Die Szenarien sind dieselben wie gegen die KI, ihre Ausgewogenheit (beide Seiten gewinnen, siehe Kapitel Hauptmenü, Einweisung) gilt also auch für zwei Crews.

## Servermodus (nur Browser) {#mp-server}

**Server (nur Browser)** (Hauptmenü, oder `--server` beim Start): Die uConsole dient nur als Server, alle spielen im Browser, auf beiden Einheiten, allein oder gemeinsam. Sie öffnet die Lobby mit eingeschaltetem Remote Crew, spielt selbst keine Station (die Stationszeile steht fest auf nur Host) und zeigt nur QR-Code, Adresse, Beitrittscode und die Besatzung.

Der erste Browser der Besatzung, der beitritt, ist der **Spielleiter** (in der Lobby jedes Browsers markiert): Er wählt in der Lobby die Einheit, den Einsatz (ein Szenario, die Tagesmission, einen Brennpunkt der Kampagne der gewählten Einheit mit den Hafenentscheidungen der Kampagne oder eine eigene Mission), den Gegner (KI oder zweite Crew), Wetter, Tageszeit und Einsatzlänge und startet den Countdown mit **Für alle starten** (ein zweiter Klick, wenn jemand noch nicht bereit ist). Gegen die KI wechselt bei einem Wechsel der Einheit jeder Browser auf die ersten freien Stationen der neuen Einheit. Allein spielt der Spielleiter solo: Die KI besetzt jede Station, die er nicht hält.

Während eines Einsatzes zeigt die uConsole den Schiedsrichter-Bildschirm mit der Beitrittszeile und dem Namen des Spielleiters; die Host-Leiste des Spielleiters behält Speichern und Laden und bekommt **Zurück zur Lobby**, das den Einsatz für alle beendet. Die Besatzung behält ihre Stationen über jeden Start, jedes Laden und jede Rückkehr. Mit **Leitung abgeben** neben dem Namen eines Crewmitglieds gibt der Spielleiter die Leitung ab; bleibt er eine Weile weg, geht sie von selbst an das nächste Crewmitglied. Ausguck-Telefone und Beobachter leiten nie.

`Esc` auf der uConsole verlässt den Server-Modus zum Hauptmenü. Nichts davon wird gespeichert.

## Remote-Crew-Seite (F9) {#mp-f9}

`F9`: Commander / Remote Crew - Browser im LAN können Stationen übernehmen. Die Seite hat einen Schalter, **Mehrspieler**: `Eingabe` schaltet ihn auf der ersten lokalen Netzwerkadresse ein oder, wenn die uConsole kein Netz hat, auf ihrem eigenen Hotspot (sofern der Hotspot-Helfer installiert ist; der uConsole-Installer `install.sh` richtet ihn ein, wenn er kann, und gibt sonst einen Hinweis aus). Der Hotspot behält WLAN-Name und Passwort von einem Start zum nächsten, sodass ein Handy oder PC, das einmal beigetreten ist, sich von selbst wieder verbindet. Auf dem Hotspot zeigt die Seite beide Schritte zusammen: **1** den WLAN-QR-Code mit Name und Passwort, **2** den Seiten-QR-Code mit dem Beitrittscode.

![Remote-Crew-Verwaltung (F9) auf der uConsole](figure:commander-options)

**Crew** zeigt die Spieler und ihre Stationen. **Erweiterte Netzwerkeinstellungen** blendet Netzwerkmodus (LAN oder Hotspot), Adresse und Port zur Handwahl ein; sie ändern sich nur bei ausgeschaltetem Mehrspieler. Dort erzeugt, solange Mehrspieler aus ist, **Neues Hotspot-Passwort** ein neues Hotspot-Passwort und behält den Namen; jedes Gerät muss dann mit dem neuen WLAN-QR-Code neu beitreten.

Eine freie Station wird sofort mit allen ihren Rechten übernommen (auch Direktfeuer und Sonar-Liveaudio, wo die Station sie hat); eine Station, die ein Crewmitglied hält, wird angefragt, und der Inhaber (er sieht die Anfrage mit den Knöpfen Übergeben / Station behalten) oder der Host kann sie übergeben. Eine Station hat immer alle ihre Rechte; der Host kann jederzeit eine Station entziehen, das SimLog geben oder nehmen (Roster-Taste `L`) und bis zu zwei Browser zu reinen Beobachtern machen (Roster-Taste `O`): sie sehen jede Station beider Einheiten, ohne sie zu halten, können nichts befehlen und erhalten das SimLog mit Zeitstrahl zur Nachbesprechung und JSON-Export.

Die Crew-Seiten öffnen in der gespeicherten Sprache des Hosts (`F10`-Optionen auf der uConsole); der Knopf English/Deutsch in der Statusleiste des Browsers stellt nur diesen Browser um. Die Crew-Seite ist für Chrome oder Chromium (auch Edge) auf einem Desktop-PC gebaut; ein anderer Browser zeigt über dem Kopplungscode einen Hinweis, und eine Seite, die dort nicht starten kann, sagt das, statt endlos zu laden. Nach einem Update des Hosts lädt sich eine offene Browserseite einmal selbst neu und läuft so immer mit dem passenden Web-Client.

Eine Browserstation hat drei Spalten: links die Kontaktliste, in der Mitte die Anzeige, rechts den Stationsbereich mit dem Kontaktdetail darunter. Damit die Bedienung ohne Scrollen Platz hat, klappt eine leere Kontaktliste zur schmalen Leiste und das Kontaktdetail zur Titelzeile zusammen, solange kein Kontakt gewählt ist; beides öffnet sich wieder, sobald es etwas zu zeigen gibt, und bleibt so, wie Sie es von Hand umgeschaltet haben. Die Missionsübersicht steht als eine Zeile **Auftrag** oben im Stationsbereich und klappt mit einem Klick auf. Ein Wert, für den noch nichts gemeldet ist, steht als grauer Strich; der Mauszeiger darüber nennt den Grund. Auf dem Handy liegen Sprache, Ton, Mikrofon, Einstellungen und Werkzeuge hinter dem Knopf ☰.

## Crew-Modus, Solo-Modus und Web-Host {#mp-modes}

Remote Crew läuft normalerweise im **Crew-Modus**: Jeder Browser hält die Stationen, die der Host ihm gibt, und die KI oder die uConsole besetzt den Rest. Mit `--solo-crew` gestartet, läuft es nur für diesen Start im **Solo-Modus**: Ein gekoppelter Browser hält alle Stationen seiner Einheit und darf auch die Host-Befehle Speichern, Laden und Neues Spiel sowie die Bibliothek der eigenen Missionen nutzen (Kapitel Missions- und Einheiteneditor). Editoren, Optionen, Beenden und die Netzwerkeinstellungen bleiben auf der uConsole, und in keinem Modus gibt es eine Pause.

Im Solo-Modus hält der eine Browser alle neun Stationen der Fregatte oder mit **U-Boot spielen** in der Host-Leiste alle sieben Stationen des U-Boots (zurück mit **Fregatte spielen**). Der Host-Dialog **Neues Spiel** wählt auch die **Seite** (*Fregatte F-217* oder *U-Boot*); als U-Boot führen die **KI-Jäger** Fregatte, Hubschrauber und Seefernaufklärer. Ein Solo-Browser (Remote Crew im Solo-Modus) wählt die Seite genauso: sein Dialog **Neues Spiel** hat ein Feld *Seite*, und mit *U-Boot* übernimmt die Sitzung die sieben Stationen des U-Boots, während die KI-Jäger die Fregatte besetzen.

`--web-host` betreibt einen reinen Browser-Raum hinter einem eigenen HTTPS-Reverse-Proxy (`--public-origin` nennt dessen Adresse); er speichert nicht automatisch. Die Einrichtung beschreibt die Web-Host-Anleitung der Projektdokumentation.

## Handy-Ausguck und Sehrohr {#qs-phone}

Ein Handy kann als Ausguck auf der Brücke der Fregatte oder am Sehrohr des besetzten U-Boots Wache gehen. `F9` zeigt einen zweiten QR-Code, **Handy-Ausguck**, für die Adresse `https://<Adresse>:<Port+1>/lookout`. Scannen, die Zertifikatswarnung einmal bestätigen, den Wachposten wählen und den daneben angezeigten Kopplungscode eintippen (der Code steht nie im QR-Code). Er darf wie angezeigt eingegeben werden, mit oder ohne Leerzeichen und in jeder Schreibung; verwechselbare Zeichen wie O und 0, I, l und 1 oder S und 5 werden nach der Stelle gelesen. „Falscher Kopplungscode“ heißt genau das und zeigt den Code, den das Spiel bekommen hat; lehnt das Spiel die Adresse selbst ab, sagt die Seite das.

![Fernglas und Sehrohr bei Tag und Nacht (links Fregatte, rechts U-Boot)](figure:sight-overview)

- **Zertifikat:** Das Spiel erzeugt ein eigenes Zertifikat für seine LAN-Adresse (in `~/.u-jagd/tls/`, erneuert bei neuer Adresse). Das Handy warnt einmal, weil keine Zertifizierungsstelle es signiert hat: am iPhone *Details einblenden*, dann *diese Website besuchen*; in Chrome unter Android *Erweitert*, dann *Weiter*. Nur einer solchen sicheren Seite geben Handys Gyroskop und Mikrofon frei.
- **Umsehen:** *Gyro* antippen und das Handy wie ein Fernglas drehen; zum Hoch- und Runterschauen neigen. Ohne Gyroskop wischen. *Voraus* blickt wieder zum Bug, *Zoom* schaltet die Vergrößerung weiter. Am Sehrohr dreht das Handy das Sehrohr selbst, und *Entfernung* nimmt eine Stadimeter-Entfernung auf das Ziel im Fadenkreuz.
- **Melden:** *Sprechen* antippen und sagen, was zu sehen ist, etwa „Schiff Peilung 040, Entfernung 5 Meilen“, „Flugzeug Steuerbord 30“ oder „Torpedo“ (dann gilt die Blickrichtung als Peilung). Kategorien: Kontakt, Schiff, Kriegsschiff, Handelsschiff, Luftfahrzeug, U-Boot, Torpedo. Oder das Ziel im Bild antippen und die Kategorie wählen.
- **Bestätigung:** Eine Meldung zählt nur, wenn der Ausguck dort wirklich etwas dieser Art hat, höchstens 10° neben der Peilung (und mit Entfernung höchstens 40 % oder 1 sm neben seiner Schätzung). Dann erscheint sie auf der Brücke als Ausguck-Spur und im Ereignislog, und die Crew-Browser sprechen sie. Eine Meldung von nichts wird abgelehnt, und das Handy vibriert zweimal.

Solange ein Handy den Ausguck der Brücke hält, meldet der Ausguck Schiffe, Flugzeuge und Torpedos nicht mehr von selbst: nur was der Spieler meldet, erreicht die Brücke (Land wird weiter automatisch gemeldet). Auf dem U-Boot bleibt das Sehrohrbild beim Angriffsrechner, und die eigenen „in Sicht“-Meldungen der Crew weichen den Meldungen des Handys. Die Spracherkennung nutzt den Sprachdienst des Handy-Browsers (Chrome auf Android, Safari auf dem iPhone mit eingeschalteter Siri- und Diktierfunktion; Firefox und andere Browser auf dem iPhone haben keinen, dort das Ziel antippen). Scheitert sie, nennt die Seite den Grund. Vom Handy-Ausguck wird nichts gespeichert.

## Browser-Tasten {#mp-keys}

Im Remote-Crew-Browser (Commander, `F9`) werden Stationen mit Schaltflächen oder mit denselben Tasten wie auf der uConsole bedient; jedes Bedienelement mit Taste zeigt sie als blaue Tastenkappe hinter der Beschriftung, und solange der Cursor in einem Feld steht, wirkt keine Taste. Tasten für Befehle und Feuer drücken nur das passende Bedienelement und durchlaufen dieselben Prüfungen wie ein Klick:

<!-- keys:web -->

## Nicht im Browser {#mp-gaps}

Der Browser folgt der uConsole Station für Station. Der Solo-Browser hat außerdem das **Einsatzbuch** des Hauptmenüs (Dienstzeit, Bestwerte, Auszeichnungen und was der Gegner gelernt hat, für Fregatte und U-Boot) und die **Ausbildung** (die neun Lektionen mit ihren Haken und der nächsten markiert; eine U-Boot-Lektion wechselt den Browser zuerst auf das U-Boot). Was der Browser noch nicht hat:

- **Ausbildung im Servermodus:** die Lobby des Servermodus startet nur Einsätze; Lektionen starten aus einem Solo-Browser oder auf der uConsole.
- **Zusätze der Einsatzbuch-Seite:** "Gegner lernt mit" ein- und ausschalten (`L`), die Auswertung der Dienstzeit durch das Sprachmodell und der Gefechtsbericht bleiben auf der Einsatzbuch-Seite der uConsole; der Browser zeigt die Dienstzeit nur zum Lesen.
- **Leckwehr:** die Wahl einer Abteilung mit `←`/`→` hat keine Taste; die Abteilung in der Abteilungsliste wählen.
- **Hubschrauber:** die Tasten der Akustikseiten, die es nur auf der Hubschrauberanzeige der uConsole gibt, haben im Browser kein Gegenstück.
- **Stationen durchschalten:** `Tab` schaltet nicht durch die Stationen; die Nummer der Station (`1`-`9`) wählen, dieselbe Nummer noch einmal blättert ihre Seite um.
- **Nur am Host:** Optionen, die Editoren auf der uConsole, Beenden, Netzverwaltung und Zugangsdaten bleiben absichtlich auf der uConsole.
