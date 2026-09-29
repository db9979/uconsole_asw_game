# Schnellstart {#quickstart}

Sie führen die U-Jagd-Fregatte F-217 und besetzen neun Stationen. Auftrag: feindliche U-Boote orten, verfolgen, klassifizieren und versenken, ohne das eigene Schiff zu verlieren oder neutrale Schifffahrt zu gefährden.

> Dieses Handbuch beschreibt nur, was die Simulation tatsächlich abbildet. Nicht modellierte Funktionen stehen am Ende jedes Stationskapitels.

## Auftrag und Siegbedingungen {#qs-goal}

- **Sieg:** alle zugewiesenen Ziel-U-Boote versenken oder bis zum Zeitlimit überleben (je nach Mission).
- **Niederlage:** eigenes Schiff sinkt, ein ziviles Schiff wird getroffen, das Ziel entkommt mehr als 150 sm von seinem Startpunkt, oder die Zeit läuft bei einem Versenkungsauftrag ab.
- Zeitwarnungen kommen bei 5, 2 und 1 Minute Restzeit: bei einem Versenkungsauftrag als Frist, bei einem Überlebensauftrag (Konvoi) als Zeit, bis der Konvoi in Sicherheit ist.
- Am Missionsende startet `R` die Mission mit gleichem Seed neu (eine Editor-Mission startet sich selbst neu), `M` führt ins Hauptmenü. Während der Mission bietet `Esc` neben Speichern und Beenden auch "Zum Hauptmenü (ohne Speichern)".
- Punkte: 1000 je versenktem U-Boot, 200 je unverbrauchtem Torpedo, 500 ohne zivile Verluste, bis zu 500 Zeitbonus.

## Stationen {#qs-stations}

Das Schiff ist in neun Stationen gegliedert. Die Tasten `1`-`9` wählen eine Station; erneutes Drücken der Nummer der aktiven Station blättert ihre Seiten.

```text
 1 Brücke      2 Sonar       3 Waffen
 4 Schaden     5 OPZ         6 Funk
 7 Maschine    8 Helikopter  9 EloKa
```

Jede Station zeigt nur, was ihre Sensoren und Bediener wissen. Sonarkontakte sind verrauschte Peilungen, bis Ping, TMA, Boje oder Kreuzpeilung eine Entfernung liefern. Keine Station zeigt „die Wahrheit".

`F2` übergibt die aktuelle Station an die Autocrew; `F3` zeigt, welche Stationen automatisch laufen. Nutzen Sie das, um sich auf ein oder zwei Stationen zu konzentrieren.

## Bedienung {#qs-controls}

Das Spiel läuft mit 1280x720 und ist für Tastatur und Trackball der uConsole ausgelegt. Der Trackball wirkt als Joystick: horizontal steuert er auf der Brücke, vertikal schaltet er sonst die Hauptauswahl der Station. Eine Maus funktioniert ebenfalls: Rad zoomt Karten, Ziehen verschiebt, Klick heftet einen Tooltip an.

Globale Tasten (alle Stationen):

<!-- keys:global -->

Im Remote-Crew-Browser (Commander, `F9`) werden Stationen mit Schaltflächen bedient; die Tastatur hilft bei der Navigation:

<!-- keys:web -->

Die Statuszeile unten zeigt das neueste Ereignis und die wichtigste Telemetrie; `F11` blendet das volle Ereignislog und die Telemetrie über der Station ein, ohne sie anzuhalten oder ihr die Tasten zu nehmen. `F1` (oder `?`) öffnet jederzeit die Hilfe. Sie hat vier Kategorien: globale Tasten, aktuelle Station (Tasten und Standardablauf), Sensoren und Taktik sowie dieses Handbuch. Menüs und Dialoge über einer laufenden Mission (Hilfe, Optionen, Speichern/Laden, Beenden, Nationen, `F9`, Missionsende) zeigen statt der Station die Nachtszene des Startbildschirms hinter einem Konsolen-Panel; die Mission läuft dahinter weiter.

## Unterwasserakustik in fünf Minuten {#qs-acoustics}

- **Passives Sonar liefert nur Peilung.** Jeder Kontakt beginnt als Peillinie. Entfernung liefern aktiver Ping, TMA, Sonarbojen oder Kreuzpeilung.
- **Ortung heißt Signal gegen Rauschen.** Es entscheidet die passive Sonargleichung SE = SL - TL - NL + DI - DT: Quellpegel des Ziels (lauter = weiter), Übertragungsverlust (Ausbreitung, Absorption, Schicht- und Pfadverluste), Rauschen (eigenes Rauschen plus Wind, Regen und Schiffsverkehr in der Nähe) und Gewinn der Antenne. Ab SE >= 0 dB gilt ein Kontakt als geortet. Wind und Regen wirken am stärksten, wenn Sie langsam und leise fahren; bei hoher Eigenfahrt dominiert das eigene Rauschen.
- **Eigene Fahrt ist eigener Lärm.** Der Eigenlärm steigt von 4 kn bis 31 kn, der Höchstfahrt der Fregatte. Ab 15 kn kavitieren die Schrauben, die Passivreichweite fällt auf etwa ein Drittel.
- **Die Sprungschicht (Thermokline) beugt den Schall.** Die passive Ausbreitung wird als Strahlverfolgung durch das echte Schallgeschwindigkeitsprofil gerechnet: über der Schicht trägt ein Oberflächenkanal den Schall weit, darunter liegt eine einige Meilen breite Schattenzone. In tiefem Wasser ist der Schatten stark; in einigen hundert Metern Wassertiefe füllen Bodenreflexionen und Mehrwege ihn ab etwa 10 sm auf, das Verstecken unter der Schicht wirkt dort vor allem auf kurze Distanz. Ein Ping in die Schattenzone erreicht nur 35 % seiner Reichweite.
- **Meeresboden und Oberfläche zählen.** Fels und Kies reflektieren gut, Schluff und Schlick schlucken; rauer Seegang streut hohe Frequenzen. **Konvergenzzonen** entstehen nur dort, wo das Wasser tief genug ist, damit die Strahlen wieder nach oben umkehren.
- **Baffles:** Eigenlärm ist eine weiche 70-Grad-Keule achteraus der Bugsonaranlage (beim Schleppsonar entlang des Kabels). Sie überdeckt, sie blendet nicht vollständig aus.

```text
            Oberfläche
  ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
    Fregatte HMS )))            direkter Pfad
  ---------- Sprungschicht ----------------  -6,5 dB quer
       TAS unter Schicht )))   U-Boot
                                (Schattenzone für flachen Sensor)
  ________________________________________ Meeresboden
```

## Navigationskonventionen {#qs-navigation}

- Entfernungen in Seemeilen (sm), Fahrt in Knoten (kn), Tiefe in Metern, Frequenz in Hz.
- Kurse und Peilungen sind rechtweisende Grad: 000 Nord, im Uhrzeigersinn. Karten sind genordet.
- Das Spiel läuft immer in Echtzeit: eine echte Sekunde ist eine Simulationssekunde. Es gibt weder Zeitraffer noch Pause; auch Menüs, Hilfe, Optionen, Speichern/Laden und ein Fokuswechsel halten die Simulation nicht an.
- Das Schiff dreht höchstens 0,8 Grad pro Sekunde; Fahrtänderungen dauern Minuten. Manöver früh planen.

## Die erste Patrouille {#qs-first-patrol}

1. Hauptmenü: Szenario 1 (Patrouille) mit `1` wählen und mit `Enter` starten.
2. Brücke (`1`): nochmals `1` für die Missionsseite, Auftrag und Zeitlimit lesen.
3. Maschine (`7`): SLOW oder 6-8 kn wählen. Sonar (`2`): Schleppsonar mit `Y` ausbringen.
4. Sonar-Seite BROADBAND: nach einer hellen senkrechten Spur suchen; mit den Pfeiltasten wählen und mit `Enter` verfolgen.
5. Mit `C` klassifizieren, mit `T` TMA einschalten, dann auf der Brücke 30-60 Grad drehen und den neuen Schlag einige Minuten halten.
6. Sobald TMA oder Ping eine Entfernung liefern: Kontakt an die OPZ freigeben (`G`) und als Ziel setzen (`M`).
7. Waffen (`3`): Torpedotiefe auf die gepingte Zieltiefe stellen, mit `T` feuern.
8. Sonar auf anlaufende Torpedos beobachten; kommt einer, FLANK, abdrehen und Nixie ausbringen (`V` in der Waffenzentrale).

## Hauptmenü, Speichern und Optionen {#qs-menu}

- **Erster Start:** Gibt es noch keine `~/.u-jagd/settings.json`, folgt auf den Startbildschirm eine Willkommensseite: „Was möchtest du spielen?“ `1` Fregatte (das Ausbildungsmenü mit Lektion 1 vorgewählt), `2` U-Boot (das Ausbildungsmenü mit Lektion 5, der ersten U-Boot-Lektion, vorgewählt), `3` Remote Crew (öffnet `F9`; nach dem Schließen folgt das Hauptmenü), `4` oder `Esc` Hauptmenü. Pfeiltasten und `Enter` wählen ebenfalls. Was Sie auch wählen, die Seite wird in den Einstellungen vermerkt und nicht wieder gezeigt.
- Menü: `1`-`7` Szenario (4 = Zufall mit eigener Schwierigkeit, 5 bis 7 = U-Boot-Missionen, siehe Referenzkapitel), `W` Weltmodus, `R` neuer Seed, `F` Vollbild, `Enter` Start.
- **Ausbildung** (Hauptmenü): sechs geführte Lektionen, jede eine kurze Mission mit einem Hinweisbanner, das auf Sie wartet: 1 hören und peilen, 2 Zielbewegungsanalyse, 3 Torpedoangriff, 4 Hubschrauber und Sonarbojen; auf dem U-Boot (für diese beiden spielt die uConsole das U-Boot): 5 horchen und unter die Schicht (die Fregatte hören, als Kampfschiff klassifizieren, die Schicht per BT messen und darunter tauchen), 6 eine jagende Fregatte abschütteln (Seite Bedrohung lesen, mit `I` ausweichen, leise und tiefer als 100 m gehen, bis zwei Minuten lang kein Ping mehr kommt; die Fregatte pingt alle 45 s, bis Sie ausweichen, danach nur, solange ihre Pings Sie noch finden, und schießt nie). In den Lektionen 1, 2 und 4 ist das U-Boot neutral und greift nie an; Lektion 3 ist ein echter Angriff, der mit dem Versenken endet. Die übrigen Lektionen enden nach dem letzten Schritt als Sieg. `R` am Ende startet die Lektion neu. Eine gespeicherte Lektion beginnt ihre Hinweise nach dem Laden wieder bei Schritt 1 und überspringt bereits erledigte Schritte. Nach einer Lektion behält die uConsole die gespielte Seite.
- **Kampagne** (Hauptmenü): sechs verkettete Einsätze in dem im Menü gewählten Seegebiet (Welt `W` und Seed; jeder Einsatz bleibt im selben Sektor). Übertragen werden die übrigen Torpedos (mindestens 2, höchstens 10), noch beschädigte Abteilungen, ein verlorener Hubschrauber und Ihr Ansehen bei der Führung (0-100, Start 50: +15 für einen Sieg, -20 für eine Niederlage, -10 für einen zivilen Verlust, +/-3 je erledigtem oder gescheitertem Auftrag). Nach jedem Einsatz läuft das Schiff in den Hafen: `1` volle Werftliegezeit (4 bis 8 Torpedos je nach Ansehen, alle Reparaturen, ein neuer Hubschrauber, Ansehen -5) oder `2` schnell wieder auslaufen (halbe Nachlieferung, Schäden bleiben an Bord, Ansehen +3); `Enter` läuft aus. Die Kampagne endet, wenn das Schiff verloren geht, das Ansehen unter 10 fällt oder der sechste Einsatz vorbei ist. Sie liegt in `~/.u-jagd/campaign.json`, getrennt von den Spielständen: ein während eines Kampagneneinsatzes gespeicherter Platz lädt als normale Mission; damit er zählt, wird der Einsatz aus dem Kampagnenbildschirm erneut gefahren. `N` startet eine neue Kampagne (bei laufender Kampagne zweimal).
- **U-Boot-Kampagne** (Hauptmenü, Kampagne, `Tab`): fünf verkettete U-Boot-Missionen im selben Seegebiet, gespielt auf der U-Boot-Seite: Aufklärung, Durchbruch, Geleitzugangriff, Durchbruch, Geleitzugangriff. Übertragen werden die Torpedos des U-Boots, sein Rumpfschaden (höchstens 60 %) und Ihr Ansehen bei der U-Boot-Führung (0-100, Start 50: +15 für eine gewonnene, -20 für eine verlorene Mission). Nach jeder Mission läuft das U-Boot in seinen Stützpunkt: `1` volle Überholung (volle Torpedobeladung, Rumpf repariert, Ansehen -5) oder `2` schnell wieder auslaufen (die Hälfte von 4 bis 8 Torpedos je nach Ansehen kommt dazu, der Rumpfschaden bleibt, Ansehen +3); `Enter` läuft aus. Sie endet, wenn das U-Boot verloren geht, das Ansehen unter 10 fällt oder die fünfte Mission vorbei ist, und liegt in `~/.u-jagd/boat_campaign.json` neben der Kampagne der Fregatte.
- **Fehler melden** (Hauptmenü): schreibt `~/.u-jagd/bug-report.txt` (Version, Plattform und die neuesten Zeilen aus `~/.u-jagd/crash.log`, Ihr Benutzername aus Pfaden entfernt) und zeigt einen QR-Code, der am Handy ein neues GitHub-Issue mit Version und Plattform öffnet; dort die Datei anhängen. `Enter` öffnet das Issue mit Log in einem Browser, falls das Gerät einen hat, `Esc` geht zurück. Nach einem abgestürzten Start wählt das Hauptmenü diesen Eintrag vor und weist darauf hin. Gesendet wird erst, wenn Sie das Issue mit Ihrem eigenen GitHub-Konto abschicken. Der Windows-Starter („Fehler melden“) und das Einstellungsmenü im Browser haben denselben Link.
- `S` / `L`: Speichern / Laden (Plätze 1-5). Spielstände sind exakt und deterministisch: ein geladenes Spiel läuft identisch weiter.
- **Autosave:** Eine laufende Mission wird alle 5 Minuten und beim Beenden oder Verlassen ins Hauptmenü nach `~/.u-jagd/autosave.json` gespeichert, neben den fünf Plätzen. Das Hauptmenü beginnt dann mit **Einsatz fortsetzen**, das sie exakt weiterführt; nach einem Absturz ist es der letzte 5-Minuten-Stand. Eine beendete Mission (Sieg, Niederlage oder Schiff gesunken) und jede neue Mission löschen den Autosave. Der Web-Host (`--web-host`) speichert nicht automatisch.
- `F10`: Optionen - Sprache, Vollbild, Audio, große Schrift, Tooltips, Bildrate (30 oder 60 FPS; 30 spart Rechenleistung auf der uConsole und ist voreingestellt), Ereignislog/Telemetrie als Statuszeile (Standard, mehr Platz für die Station) oder feste Leiste, Bedienerassistenz aus (Standard: Rohdaten und manuelle Analyse) oder Training (automatische Linienbeschriftung, Blattfrequenz- und Katalog-/Senderkandidaten). Seite 2 (`Bild ab`/`Tab`): welche Seite der uConsole spielt, Fregatte (Standard) oder feindliches U-Boot; nur im Hauptmenü, nie gespeichert. Ein neues Spiel fragt ohnehin zuerst danach. Auf Seite 2 liegen auch die **geglätteten Kartenlinien** (standardmäßig aus; glättet Peilstriche, Küste und Plot, kostet auf der uConsole etwas Rechenzeit). Dazu die **gesprochenen Crew-Meldungen** (standardmäßig aus): die Crew meldet Torpedo im Wasser, neuen Kontakt mit Peilung, Sinkgeräusche, Torpedo los, Treffer, Gefechtsstationen, Seefernaufklärer auf Station und das Missionsende laut, Peilungen Ziffer für Ziffer. Die uConsole spricht über ein installiertes `espeak-ng` (`sudo apt install espeak-ng`) und bleibt ohne es stumm; Remote-Crew-Browser haben einen eigenen Schalter unter Einstellungen (Sprachausgabe des Browsers, in dessen Sprache). Spielt die uConsole das U-Boot, meldet stattdessen dessen Crew (siehe Kapitel Referenz).
- `F9`: Commander / Remote Crew - Browser im LAN können Stationen übernehmen. Eine freie Station wird sofort mit allen ihren Rechten übernommen (auch Direktfeuer und Sonar-Liveaudio, wo die Station sie hat); eine Station, die ein Crewmitglied hält, wird angefragt, und der Host kann sie übergeben. Der Host kann jederzeit eine Station oder einzelne Rechte entziehen und bis zu zwei Browser zu reinen Beobachtern machen (Roster-Taste `O`): sie sehen jede Station beider Einheiten, ohne sie zu halten, können nichts befehlen und erhalten das SimLog mit Zeitstrahl zur Nachbesprechung und JSON-Export. Auf einem Windows-PC startet das Programm `U-Jagd-Windows.exe` das Spiel mit bereits eingeschalteter Remote Crew (Besatzungs- oder Solomodus) und zeigt Browser-Adresse, Beitrittscode und QR-Code; `--remote-crew` macht dasselbe über die Kommandozeile (siehe README). Die Crew-Seite ist für Chrome oder Chromium (auch Edge) auf einem Desktop-PC gebaut; ein anderer Browser zeigt über dem Kopplungscode einen Hinweis, und eine Seite, die dort nicht starten kann, sagt das, statt endlos zu laden. Nach einem Update des Hosts lädt sich eine offene Browserseite einmal selbst neu und läuft so immer mit dem passenden Web-Client.

## Handy-Ausguck und Sehrohr {#qs-phone}

Ein Handy kann als Ausguck auf der Brücke der Fregatte oder am Sehrohr des besetzten U-Boots Wache gehen. `F9` zeigt einen zweiten QR-Code, **Handy-Ausguck**, für die Adresse `https://<Adresse>:<Port+1>/lookout`. Scannen, die Zertifikatswarnung einmal bestätigen, den Wachposten wählen und den daneben angezeigten Kopplungscode eintippen (der Code steht nie im QR-Code). Er darf wie angezeigt eingegeben werden, mit oder ohne Leerzeichen und in jeder Schreibung; O und 0 oder I, l und 1 werden nach der Stelle gelesen. „Falscher Kopplungscode“ heißt genau das; lehnt das Spiel die Adresse selbst ab, sagt die Seite das.

- **Zertifikat:** Das Spiel erzeugt ein eigenes Zertifikat für seine LAN-Adresse (in `~/.u-jagd/tls/`, erneuert bei neuer Adresse). Das Handy warnt einmal, weil keine Zertifizierungsstelle es signiert hat: am iPhone *Details einblenden*, dann *diese Website besuchen*; in Chrome unter Android *Erweitert*, dann *Weiter*. Nur einer solchen sicheren Seite geben Handys Gyroskop und Mikrofon frei.
- **Umsehen:** *Gyro* antippen und das Handy wie ein Fernglas drehen; zum Hoch- und Runterschauen neigen. Ohne Gyroskop wischen. *Voraus* blickt wieder zum Bug, *Zoom* schaltet die Vergrößerung weiter. Am Sehrohr dreht das Handy das Sehrohr selbst, und *Entfernung* nimmt eine Stadimeter-Entfernung auf das Ziel im Fadenkreuz.
- **Melden:** *Sprechen* antippen und sagen, was zu sehen ist, etwa „Schiff Peilung 040, Entfernung 5 Meilen“, „Flugzeug Steuerbord 30“ oder „Torpedo“ (dann gilt die Blickrichtung als Peilung). Kategorien: Kontakt, Schiff, Kriegsschiff, Handelsschiff, Luftfahrzeug, U-Boot, Torpedo. Oder das Ziel im Bild antippen und die Kategorie wählen.
- **Bestätigung:** Eine Meldung zählt nur, wenn der Ausguck dort wirklich etwas dieser Art hat, höchstens 10° neben der Peilung (und mit Entfernung höchstens 40 % oder 1 sm neben seiner Schätzung). Dann erscheint sie auf der Brücke als Ausguck-Spur und im Ereignislog, und die Crew-Browser sprechen sie. Eine Meldung von nichts wird abgelehnt, und das Handy vibriert zweimal.

Solange ein Handy den Ausguck der Brücke hält, meldet der Ausguck Schiffe, Flugzeuge und Torpedos nicht mehr von selbst: nur was der Spieler meldet, erreicht die Brücke (Land wird weiter automatisch gemeldet). Auf dem U-Boot bleibt das Sehrohrbild beim Angriffsrechner, und die eigenen „in Sicht“-Meldungen der Crew weichen den Meldungen des Handys. Die Spracherkennung nutzt den Sprachdienst des Handy-Browsers (Chrome und Safari; Firefox hat keinen, dort das Ziel antippen). Vom Handy-Ausguck wird nichts gespeichert.
