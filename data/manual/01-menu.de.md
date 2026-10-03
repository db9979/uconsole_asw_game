# Hauptmenü und Spielstart {#menu}

Nach dem Startbildschirm öffnet das Hauptmenü. `Auf`/`Ab` (oder die Maus) wählen einen Eintrag, `Enter` öffnet ihn, `Esc` fragt, ob das Spiel beendet werden soll. Jede Seite, die von dort aus erreicht wird, führt mit `Esc` zurück.

![Hauptmenü](figure:main-menu)

## Einträge des Hauptmenüs {#menu-entries}

| Eintrag | Was er tut |
|---|---|
| Einsatz fortsetzen | Setzt den automatisch gesicherten Einsatz fort; nur vorhanden, solange es eine automatische Sicherung gibt |
| Neuer Einsatz | Seite, Szenario, Einweisung (unten) |
| Tageseinsatz | Ein fester Einsatz je Seite und Tag |
| Mehrspieler | Die Lobby mit Remote Crew (Kapitel Remote Crew) |
| Server (nur Browser) | Die uConsole stellt nur bereit; alle spielen im Browser |
| Ausbildung | Sechs geführte Lektionen (unten) |
| Kampagne | Feldzug für jede Seite (Kapitel Szenarien und Missionen) |
| Einsatzbuch | Dienstbuch und Auszeichnungen (Kapitel Nach dem Einsatz) |
| Einsatz laden | Lädt Platz 1-5 |
| Missionseditor | Eigene Missionen (Kapitel Missions- und Einheiteneditor) |
| Einheiteneditor | Eigene Einheitenprofile (Kapitel Missions- und Einheiteneditor) |
| Taktischer Einheitenanalysator | Nur lesender Katalog aller Einheiten (Kapitel Missions- und Einheiteneditor) |
| Optionen | Einstellungen (Kapitel Optionen) |
| Fehler melden | Fehlerbericht mit QR-Code (unten) |
| Beenden | Beendet das Spiel |

## Erster Start {#menu-welcome}

Gibt es noch keine `~/.u-jagd/settings.json`, folgt auf den Startbildschirm eine Willkommensseite: „Was möchtest du spielen?“ `1` Fregatte (das Ausbildungsmenü mit Lektion 1 vorgewählt), `2` U-Boot (das Ausbildungsmenü mit Lektion 5, der ersten U-Boot-Lektion, vorgewählt), `3` Remote Crew (öffnet die Mehrspieler-Lobby; `Esc` dort führt ins Hauptmenü), `4` oder `Esc` Hauptmenü. Pfeiltasten und `Enter` wählen ebenfalls. Was Sie auch wählen, die Seite wird in den Einstellungen vermerkt und nicht wieder gezeigt.

## Neuer Einsatz: Seite und Szenario {#menu-new}

Ein neues Spiel fragt zuerst nach der Seite (`1` Fregatte, `2` U-Boot) und listet dann nur deren Szenarien: jede Seite zählt ab `1`: `1`-`9` und `0` (das zehnte; das elfte und zwölfte mit den Pfeiltasten) auf jeder Seite (Fregatte 4 = Zufall mit eigener Schwierigkeit) (siehe Kapitel Szenarien und Missionen), `Esc` zurück zur Seitenwahl; `W` Weltmodus, `R` neuer Seed, `F` Vollbild (diese drei nur im Hauptmenü und auf den Szenarioseiten: Liste, Schwierigkeit, Einsatzbesprechung), `Enter` Start.

Die Liste zeigt neun Zeilen auf einmal und rollt mit der Auswahl (`Auf`/`Ab`, Mausrad, `Bild auf`/`Bild ab` eine Seite, `Pos1`/`Ende` erste und letzte Zeile; bei festem realem Sektor wählen `[`/`]` den Sektor); ein Balken am rechten Rand zeigt die Lage in der Liste, darunter steht der Anfang der Einsatzbesprechung des gewählten Szenarios. Die eigenen Missionen und die Schwierigkeitsliste der freien Jagd rollen genauso.

**Eigene Missionen:** Das Startmenü zeigt nach den Szenarien der gewählten Seite die Zeile „Eigene Missionen“ (`O` oder `Enter` auf der Zeile). Sie öffnet die Missionen des Missionseditors für diese Seite; `Enter` startet eine. Die Mehrspieler-Lobby bietet sie in ihrer Missionszeile nach den Szenarien an, der Solo-Browser im Dialog „Neues Spiel“ und unter „Eigene Missionen“ in der Gastgeberleiste (siehe Kapitel Missions- und Einheiteneditor).

## Einweisung: Wetter, Uhrzeit und Länge {#menu-briefing}

![Einsatzbesprechung vor dem Start: Auftrag, Seegebiet, Kräfte und Siegbedingungen](figure:mission-briefing)

**Wetter und Uhrzeit:** Das Briefing jedes Szenarios (bei 4 nach der Schwierigkeit), die Einsatzbesprechung eines Brennpunkts der Kampagne, die Mehrspieler-Lobby und der Dialog „Neues Spiel“ im Browser wählen das Wetter (Zufall, schön, Regen, Sturm, Nebel) und die Uhrzeit (Zufall, Morgengrauen 06:00, Tag 12:00, Abenddämmerung 19:00, Nacht 01:00): `Auf`/`Ab` wählt die Zeile, `Links`/`Rechts` ändert sie. Zufall behält, was der Seed ergibt.

Ein gewähltes Wetter hält die ganze Mission (Seegang schön und Nebel 1, Regen 3, Sturm 5; die See ändert sich nur innerhalb von 0-2, 2-4 und 5-6; ein Sturm bringt Gewitter mit Blitz, Donner und Sferics), und Wetterfronten ziehen dann keine durch; die Uhr läuft von der gewählten Zeit weiter. Die Wahl gilt bis zum Beenden des Spiels für jede neue Mission, auch für `R` am Missionsende; sie wird mit der Mission gespeichert, nicht in den Einstellungen.

**Kurzeinsatz:** An denselben Stellen gibt es eine dritte Zeile, die Länge: volle Mission oder Kurzeinsatz (nicht bei Szenario 4, dessen Zeitlimit eine eigene Einstellung ist).

Ein Kurzeinsatz behält sein Ziel, hat aber ein kürzeres Zeitlimit und beginnt näher am Geschehen: Patrouille 30 min, Doppeljagd 60 min, Nuklearer Abfang 45 min, Durchbruch 60 min, Jagdgruppe 60 min, Aufklärung 45 min, Geleitzug 35 min, Meerengen-Sperre 45 min, Kampfschwimmer 45 min, Versorgerschutz 45 min, Geleitschutz 35 min, Angeschlagen heim 60 min, jedes andere neue Szenario 45 min. Das erste feindliche U-Boot beginnt 5-8 sm von der Fregatte (Durchbruch und Jagdgruppe 4-6 sm, Aufklärung 10-16 sm) und jedes weitere 8-14 sm; in einer U-Boot-Mission rücken auch das Ziel hinter der Fregatte, Ein- und Ausfahrt der Meerenge, der Anmarsch der Kampfschwimmer und der Platz vor dem Bug des Geleitzugs oder Versorgers näher.

Jeder Kurzeinsatz wurde mit KI-gegen-KI-Partien so eingestellt, dass beide Seiten etwa gleich oft gewinnen. Sein Name trägt „(Kurzeinsatz)“, und er wird wie jede Mission gespeichert.

## Ausbildung {#menu-training}

**Ausbildung** bietet sechs geführte Lektionen. Jede ist eine kurze Mission mit einem Hinweisbanner, das auf Sie wartet; `Auf`/`Ab` oder `1`-`6` wählen, `Enter` startet:

| Lektion | Seite | Was Sie üben |
|---|---|---|
| 1 Hören und peilen | Fregatte | Ein U-Boot im Sonar finden, verfolgen und klassifizieren |
| 2 Zielbewegungsanalyse (TMA) | Fregatte | TMA einschalten, einen zweiten Schlag fahren und eine Entfernung erhalten |
| 3 Torpedoangriff | Fregatte | Ein feindliches U-Boot orten, klassifizieren, zuweisen und versenken |
| 4 Hubschrauber und Sonarbojen | Fregatte | Den Hubschrauber starten, eine Boje werfen und das U-Boot darauf hören |
| 5 Horchen und unter die Schicht | U-Boot | Die Fregatte hören, als Kampfschiff klassifizieren, die Schicht per BT messen und darunter tauchen |
| 6 Eine jagende Fregatte abschütteln | U-Boot | Seite Bedrohung lesen, mit `I` ausweichen, leise und tiefer als 100 m gehen, bis zwei Minuten lang kein Ping mehr kommt |

Für die Lektionen 5 und 6 spielt die uConsole das U-Boot. In Lektion 6 pingt die Fregatte alle 45 s, bis Sie ausweichen, danach nur, solange ihre Pings Sie noch finden, und sie schießt nie.

In den Lektionen 1, 2 und 4 ist das U-Boot neutral und greift nie an; Lektion 3 ist ein echter Angriff, der mit dem Versenken endet. Die übrigen Lektionen enden nach dem letzten Schritt als Sieg. `R` am Ende startet die Lektion neu. Eine gespeicherte Lektion beginnt ihre Hinweise nach dem Laden wieder bei Schritt 1 und überspringt bereits erledigte Schritte. Nach einer Lektion behält die uConsole die gespielte Seite.

## Tageseinsatz {#ref-daily}

- *Tageseinsatz* im Hauptmenü bietet je Seite und Tag einen festen Einsatz, für alle Spieler gleich: Das Datum wählt Szenario und Seed und damit das echte Seegebiet, Wetter und Tageszeit. Die Länge ist immer die normale.
- Die Seite zeigt den heutigen Bestwert jeder Seite; ein beendeter Tageseinsatz (auch nach Mitternacht, für den von gestern) hält den besten Sieg 30 Tage im Einsatzbuch. Die Realismusstufe ist die eigene Einstellung.

## Speichern, Laden und automatische Sicherung {#menu-save}

`S` speichert, `L` lädt (Plätze 1-5). Spielstände sind exakt und deterministisch: ein geladenes Spiel läuft identisch weiter. Ein Spielstand einer älteren Version (Spielstandformat v38, Version 1.3.98, oder neuer) lädt weiterhin: Er wird beim Laden auf das aktuelle Format gebracht, Plätze und automatische Sicherung gleichermaßen.

**Autosave:** Eine laufende Mission wird alle 5 Minuten und beim Beenden oder Verlassen ins Hauptmenü nach `~/.u-jagd/autosave.json` gespeichert, neben den fünf Plätzen. Das Hauptmenü beginnt dann mit **Einsatz fortsetzen**, das sie exakt weiterführt; nach einem Absturz ist es der letzte Wiederherstellungspunkt, höchstens eine Minute alt. Eine beendete Mission (Sieg, Niederlage oder Schiff gesunken) und jede neue Mission löschen den Autosave. Der Web-Host (`--web-host`) speichert nicht automatisch.

**Fehlerschutz:** Eine Stationsanzeige, die sich nicht zeichnen lässt, zeigt „Anzeige gestört“, während die Mission weiterläuft; ein Fehler in der Simulation setzt die Mission auf ihren Wiederherstellungspunkt von höchstens einer Minute vorher zurück (eine Kopie im Speicher, die nie einzeln geschrieben wird) und meldet das im Ereignisprotokoll. Browser der Remote Crew bekommen ihre Stationen wie nach dem Laden zurück. Nach wiederholten Fehlern wird die Mission gesichert und das Hauptmenü öffnet mit **Einsatz fortsetzen**. Jeder abgefangene Fehler landet in `~/.u-jagd/crash.log` für einen Fehlerbericht.

## Update-Hinweis {#menu-update}

Neue Versionen werden nie von selbst installiert. Beim Start fragt das Spiel einmal bei GitHub, ob es ein neueres Release gibt; dann zeigen der Startbildschirm (oben rechts) und das Hauptmenü (links neben den Einträgen) dessen Version, den Eintrag aus dem Änderungsprotokoll in der Spielsprache und nur dann eine Warnung, wenn Spielstände dieser Version (auch die automatische Sicherung) zu alt sind, als dass das neue Release sie auf den aktuellen Stand bringen könnte.

`U` oder ein Klick auf **Jetzt updaten** installiert es: Auf der uConsole schließt das Spiel, das kleine Fenster des Starters zeigt Download und Prüfung, und die neue Version startet; das Windows-Programm lädt die neue Datei im Hintergrund (Fortschritt auf dem Knopf), prüft Größe und SHA-256-Prüfsumme, schließt sich, ersetzt sich selbst und startet die neue Version; die macOS-App macht dasselbe mit dem Zip für ihren Prozessor (Apple Silicon oder Intel): Sie entpackt die neue `U-Jagd.app` neben sich, schließt sich, tauscht das Bundle aus (das alte wird erst gelöscht, wenn das neue an seinem Platz ist) und öffnet die neue Version, sofern sie in ihren Ordner schreiben darf (sonst öffnet sie die Release-Seite); jede andere Installation öffnet die Release-Seite.

Schlägt die Prüfung fehl, steht an derselben Stelle, dass und warum (keine Verbindung zu GitHub, die Verbindung ließ sich per Zertifikat nicht prüfen oder ein Fehler von GitHub), und `U` oder ein Klick prüft erneut; mit `U_JAGD_NO_UPDATE=1` wird nichts geprüft.

## Fehler melden {#menu-bug}

**Fehler melden** im Hauptmenü schreibt `~/.u-jagd/bug-report.txt` (Version, Plattform und die neuesten Zeilen aus `~/.u-jagd/crash.log`, Ihr Benutzername aus Pfaden entfernt) und zeigt einen QR-Code, der am Handy ein neues GitHub-Issue mit Version und Plattform öffnet; dort die Datei anhängen. `Enter` öffnet das Issue mit Log in einem Browser, falls das Gerät einen hat, `Esc` geht zurück. Nach einem abgestürzten Start wählt das Hauptmenü diesen Eintrag vor und weist darauf hin. Gesendet wird erst, wenn Sie das Issue mit Ihrem eigenen GitHub-Konto abschicken. Das Einstellungsmenü im Browser hat denselben Link.

## Spielstart {#menu-launch}

Auf einem Windows-PC startet das Programm `U-Jagd-Windows.exe` mit denselben Kommandozeilenoptionen direkt ins Spiel; ein eigenes Starterfenster gibt es nicht (auf einem Mac arbeitet die App `U-Jagd.app` genauso), und **Mehrspieler** im Hauptmenü (oder `--multiplayer`, unten) öffnet die Lobby mit eingeschalteter Remote Crew.

Kommandozeilenoptionen beim Start (gleich für das Windows-Programm und die macOS-App):

- `--windowed` und `--no-audio` übersteuern die gespeicherte Vollbild- und Audio-Einstellung für einen Start.
- `--multiplayer` öffnet die Mehrspieler-Lobby direkt nach dem Startbildschirm.
- `--server` startet den Servermodus nur für Browser (Kapitel Remote Crew).
- `--solo-crew` startet Remote Crew im Solo-Modus: Ein Browser bedient alle Stationen (Kapitel Remote Crew).
- Eine Zahl als einziges Argument setzt den Seed der Welt.

## Menütasten {#menu-keys}

Menütasten (Hauptmenü und seine Seiten; `F1` in einem Menü zeigt sie):

<!-- keys:menu -->
