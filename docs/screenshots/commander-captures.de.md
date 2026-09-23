# Commander-Browseraufnahmen

Diese reproduzierbaren Demonstrationsbilder verwenden die ausgelieferten
Browserdateien, den produktiven `CommanderServer`, die `CommanderBridge` und ein
echtes `Game`. Sie verwenden weder nachgebildete API-Antworten noch gestreckte
uConsole-Arbeitsplatzbilder. Sie sind kein Nachweis einer LAN- oder
Hardwareabnahme mit zwei Rechnern.

## Desktop-Arbeitsplätze

Alle Desktop-Aufnahmen sind 1920 x 1080 Pixel groß, verwenden Seed 1234,
durchlaufen eine echte Protocol-v2-Kopplung, erhalten ihre Arbeitsplatz-Lease vom
Host und zeigen ausschließlich die dafür freigegebene Projektion.

| Arbeitsplatz | Deutsch | Englisch |
| --- | --- | --- |
| Brücke | [PNG](commander-v2-de-bridge-desktop.png) | [PNG](commander-v2-en-bridge-desktop.png) |
| Sonar | [PNG](commander-v2-de-sonar-desktop.png) | [PNG](commander-v2-en-sonar-desktop.png) |
| Waffen | [PNG](commander-v2-de-weapons-desktop.png) | [PNG](commander-v2-en-weapons-desktop.png) |
| Schadensabwehr | [PNG](commander-v2-de-damage-desktop.png) | [PNG](commander-v2-en-damage-desktop.png) |
| OPZ/CIC | [PNG](commander-v2-de-opz-desktop.png) | [PNG](commander-v2-en-opz-desktop.png) |
| Funk | [PNG](commander-v2-de-radio-desktop.png) | [PNG](commander-v2-en-radio-desktop.png) |
| Maschinenraum | [PNG](commander-v2-de-engine-desktop.png) | [PNG](commander-v2-en-engine-desktop.png) |
| Helikopter | [PNG](commander-v2-de-helicopter-desktop.png) | [PNG](commander-v2-en-helicopter-desktop.png) |
| Elektronische Kampfführung/ESM | [PNG](commander-v2-de-eloka-desktop.png) | [PNG](commander-v2-en-eloka-desktop.png) |

`commander-overview.png` ist für bestehende README-Verweise ein Alias der
englischen OPZ/CIC-Aufnahme. `commander-wide.png` ist eine eigene englische
Sonaraufnahme mit 2560 x 1440 Pixeln.

## Mobilansichten

Die Aufnahmen mit 500 x 844 Pixeln prüfen das responsive einspaltige Layout.
Chromium erzwingt im Headless-Modus eine Mindestbreite von 500 CSS-Pixeln;
schmalere reale Geräte verwenden denselben mobilen Umbruchpunkt.

| Szene | Bild |
| --- | --- |
| Englische Arbeitsplatzanfrage | [PNG](commander-v2-en-lobby-mobile.png) |
| Englische Sonarfilter | [PNG](commander-v2-en-sonar-mobile.png) |
| Deutsche Funkmeldungen | [PNG](commander-v2-de-radio-mobile.png) |
| Deutsche Mehrstationsauswahl | [PNG](commander-v2-de-multi-station-mobile.png) |

## Reproduktion

Aus dem Repository-Stammverzeichnis mit installierten Projektabhängigkeiten und
Chromium:

```sh
python tools/capture_commander.py
python tools/capture_commander.py --output /tmp/commander-review --seed 1234
```

Das optionale Werkzeug lädt keinen Browser herunter und benötigt weder Node noch
Playwright. Es führt 360 normale Spielschritte zu je 1/60 Sekunde aus, friert die
Simulation ein und aktualisiert anschließend nur die Main-Thread-Projektion mit
einer deterministischen Aufnahmeuhr. Die Sonarbeispiele verwenden den echten
gefilterten Abhörzustand. Vorgegebene Eigenschiffschäden demonstrieren die
Schadensabwehr; Kontakte und Missionsinformationen stammen weiterhin nur aus den
Beobachtungen des Spiels.

Das Skript bindet ausschließlich `127.0.0.1` an einem temporären Port. Seine nur
im Speicher ergänzte Browserautomatisierung führt eine echte v2-Kopplung und
Cookie-Wiederaufnahme aus. Der Host weist anschließend die benötigte Lease zu und
aktiviert den Arbeitsplatz; die Mehrstationsansicht erhält drei getrennte Leases.
Es wird kein Simulationsbefehl gesendet. Kein HTTP-Thread greift auf `Game` zu.

Ein temporäres HOME und ein Inkognito-Chromium-Profil schützen echte Nutzerdaten.
Zugangsdaten werden weder ausgegeben noch in eine URL, Quelldatei oder das DOM
geschrieben und nicht absichtlich gespeichert. Alle Bilder werden vor der
Veröffentlichung zwischengelagert. Danach werden Dienst und Kopplung beendet,
ergänzte Cache-Dateien gelöscht und Listener sowie Worker auf sauberes Ende
geprüft.

## Prüfung und Grenzen

Die Neuerzeugung vom 13.09.2026 prüfte für jedes Bild die erwartete Sprache und
Rolle, eine gesunde Verbindung, das gezeichnete Arbeitsplatzinstrument,
erforderliche Sonar-, Funk- oder Mehrstationsinhalte, leere Zugangsdatenfelder,
das nicht auslesbare HttpOnly-Sitzungscookie, exakte PNG-Abmessungen, fehlenden
horizontalen Überlauf, keine erfassten JavaScriptfehler und ein sauberes
Serverende. Zusätzlich wurden die vollständigen Desktop- und Mobilübersichten auf
lesbare, unbeschnittene Inhalte kontrolliert.

Die Bilder wahren die Beobachtungsgrenze: unbekannte gegnerische Entfernung,
Tiefe, Kurs, Identität und Position werden nicht für die Anzeige erfunden. Sie
belegen nicht die Kopplung zweier echter Rechner, WLAN-Zuverlässigkeit, physische
Touch-Ergonomie, WebAudio-Ausgabe oder uConsole-Leistung. Befehlsausführung,
Berechtigungen, responsive Layouts und Browserinteraktionen besitzen getrennte
automatisierte Vertragstests.
