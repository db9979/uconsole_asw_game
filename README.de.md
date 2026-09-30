[English README](README.md)

# U-Jagd

[![Buy me a coffee](https://img.shields.io/badge/Buy%20me%20a%20coffee-support-FFDD00?logo=buymeacoffee&logoColor=black)](https://buymeacoffee.com/zquu1xu570)

Optionaler Browserbetrieb für einen vollständigen LAN-Spielraum: siehe
[Webspiel im LAN](docs/web-host.de.md). Der Modus startet mit `--web-host` und
benötigt einen eigenen HTTPS-Reverse-Proxy.

U-Jagd ist ein Echtzeit-Taktikspiel zur U-Boot-Jagd für Linux, das für die
Arbeitsfläche von 1280 x 720 Pixeln der ClockworkPi uConsole entwickelt wurde.
Sie führen eine fiktive Fregatte und wechseln zwischen neun Arbeitsplätzen, um
zu navigieren, zu suchen, Kontakte zu klassifizieren, Ziele zu bekämpfen und das
Schiff einsatzfähig zu halten.

Aktuelle Version: **1.3.100**

Version 1.3.100 bringt die Stationen Sonar, Elektronische Kampfführung, Funk
und Waffen in den Konsolenstil der Maschinen- und Schadensbildschirme. Das
Sonar von Fregatte und U-Boot bekommt dunklere Leuchtschirme, eine Horchkonsole
mit Lampen für Ping, Ton und Spitzenwert-Halten und eine nordorientierte
Peilrose mit Horchrichtung, toten Winkeln, eigenem Kurs und Kontaktpeilungen;
jede Kontaktzeile trägt eine Lampe und einen Balken für den Störabstand. Das
Tauchsonar des Hubschraubers zeigt Lampen für Dom, Ping und Wassereintritt,
eine Anzeige der Wassersäule und Peilkeile so breit wie ihr Fehler, und seine
Wasserfälle nutzen die Leuchtfarben des Schiffs. ESM und KW-Peilung bekommen
Peilrosen, die Waffenseiten Rohr- und Sperrlampen und Magazintanks. Im Browser
bekommen Sonar und Hubschrauber dieselbe Rose und Lampen, die Waffenkarte
Lampen und Rohrsäulen und das ESM-Sichtgerät eine Rose mit Skala.

Frühere Versionen: [CHANGELOG.de.md](CHANGELOG.de.md).

Dies ist ein von einem einzelnen Entwickler erstelltes Hobbyprojekt. Es ist ein Spiel und kein Ausbildungs-
oder Navigationsprodukt. Die Systeme sind vereinfacht und erheben nicht den
Anspruch, geheime Fähigkeiten, Daten oder Einsatzgrundsätze nachzubilden.

## Screenshots

### uConsole (1280 x 720)

Das Fernglas des Ausgucks auf der Fregatte und das Sehrohr des U-Boots, bei Tag und bei Nacht, mit den Schiffen im Okular:

<table>
<tr>
<td width="50%" align="center"><a href="docs/screenshots/de-frigate-binoculars-day.png"><img src="docs/screenshots/de-frigate-binoculars-day.png" alt="Fregatte: Fernglas, Tag"></a><br><sub>Fregatte: Fernglas, Tag</sub></td>
<td width="50%" align="center"><a href="docs/screenshots/de-frigate-binoculars-night.png"><img src="docs/screenshots/de-frigate-binoculars-night.png" alt="Fregatte: Fernglas, Nacht"></a><br><sub>Fregatte: Fernglas, Nacht</sub></td>
</tr>
<tr>
<td width="50%" align="center"><a href="docs/screenshots/de-uboot-periscope-day.png"><img src="docs/screenshots/de-uboot-periscope-day.png" alt="U-Boot: Sehrohr, Tag"></a><br><sub>U-Boot: Sehrohr, Tag</sub></td>
<td width="50%" align="center"><a href="docs/screenshots/de-uboot-periscope-night.png"><img src="docs/screenshots/de-uboot-periscope-night.png" alt="U-Boot: Sehrohr, Nacht"></a><br><sub>U-Boot: Sehrohr, Nacht</sub></td>
</tr>
</table>

Arbeitsplätze der Fregatte:

<table>
<tr>
<td width="33%" align="center"><a href="docs/screenshots/de-station-bridge.png"><img src="docs/screenshots/de-station-bridge.png" alt="Brücke"></a><br><sub>Brücke</sub></td>
<td width="33%" align="center"><a href="docs/screenshots/de-station-sonar.png"><img src="docs/screenshots/de-station-sonar.png" alt="Sonar"></a><br><sub>Sonar</sub></td>
<td width="33%" align="center"><a href="docs/screenshots/de-station-weapons.png"><img src="docs/screenshots/de-station-weapons.png" alt="Waffen"></a><br><sub>Waffen</sub></td>
</tr>
<tr>
<td width="33%" align="center"><a href="docs/screenshots/de-station-opz-cic.png"><img src="docs/screenshots/de-station-opz-cic.png" alt="OPZ/CIC"></a><br><sub>OPZ/CIC</sub></td>
<td width="33%" align="center"><a href="docs/screenshots/de-station-eloka.png"><img src="docs/screenshots/de-station-eloka.png" alt="Elektronische Kampfführung/ESM"></a><br><sub>Elektronische Kampfführung/ESM</sub></td>
<td width="33%" align="center"><a href="docs/screenshots/de-station-damage-control.png"><img src="docs/screenshots/de-station-damage-control.png" alt="Schadensabwehr"></a><br><sub>Schadensabwehr</sub></td>
</tr>
<tr>
<td width="33%" align="center"><a href="docs/screenshots/de-station-radio.png"><img src="docs/screenshots/de-station-radio.png" alt="Funk"></a><br><sub>Funk</sub></td>
<td width="33%" align="center"><a href="docs/screenshots/de-station-engineering.png"><img src="docs/screenshots/de-station-engineering.png" alt="Maschinenraum"></a><br><sub>Maschinenraum</sub></td>
<td width="33%" align="center"><a href="docs/screenshots/de-station-helicopter.png"><img src="docs/screenshots/de-station-helicopter.png" alt="Helikopter"></a><br><sub>Helikopter</sub></td>
</tr>
</table>

Als U-Boot spielen (`--play-sub`):

<table>
<tr>
<td width="33%" align="center"><a href="docs/screenshots/de-uboot-command.png"><img src="docs/screenshots/de-uboot-command.png" alt="Führung"></a><br><sub>Führung</sub></td>
<td width="33%" align="center"><a href="docs/screenshots/de-uboot-sonar.png"><img src="docs/screenshots/de-uboot-sonar.png" alt="Sonar"></a><br><sub>Sonar</sub></td>
<td width="33%" align="center"><a href="docs/screenshots/de-uboot-weapons.png"><img src="docs/screenshots/de-uboot-weapons.png" alt="Waffen"></a><br><sub>Waffen</sub></td>
</tr>
<tr>
<td width="33%" align="center"><a href="docs/screenshots/de-uboot-engine.png"><img src="docs/screenshots/de-uboot-engine.png" alt="Maschine"></a><br><sub>Maschine</sub></td>
<td width="33%" align="center"><a href="docs/screenshots/de-uboot-mast-esm.png"><img src="docs/screenshots/de-uboot-mast-esm.png" alt="Mast & ESM"></a><br><sub>Mast & ESM</sub></td>
<td width="33%" align="center"><a href="docs/screenshots/de-uboot-navigation.png"><img src="docs/screenshots/de-uboot-navigation.png" alt="Navigation"></a><br><sub>Navigation</sub></td>
</tr>
</table>

Menüs und Editoren:

<table>
<tr>
<td width="33%" align="center"><a href="docs/screenshots/de-main-menu.png"><img src="docs/screenshots/de-main-menu.png" alt="Hauptmenü"></a><br><sub>Hauptmenü</sub></td>
<td width="33%" align="center"><a href="docs/screenshots/de-mission-briefing.png"><img src="docs/screenshots/de-mission-briefing.png" alt="Einsatzbesprechung"></a><br><sub>Einsatzbesprechung</sub></td>
<td width="33%" align="center"><a href="docs/screenshots/de-mission-editor-detail.png"><img src="docs/screenshots/de-mission-editor-detail.png" alt="Missionseditor-Vorschau"></a><br><sub>Missionseditor-Vorschau</sub></td>
</tr>
</table>

Mehr: [U-Boot-Funkraum](docs/screenshots/de-uboot-radio.png), [Beispiel der Schadensabwehr](docs/screenshots/de-damage-control-alert.png), [U-Boot-Leckwehr](docs/screenshots/de-uboot-damage-control.png), [Szenarioauswahl](docs/screenshots/de-mission-scenario-selection.png), [Optionen](docs/screenshots/de-options.png), [Missionseditor](docs/screenshots/de-mission-editor.png), [Einheiteneditor](docs/screenshots/de-unit-editor.png) und der [taktische Einheitenanalysator](docs/screenshots/de-contact-analyzer.png).

### Remote-Crew-Browser (1920 x 1080)

<table>
<tr>
<td width="50%" align="center"><a href="docs/screenshots/commander-v2-de-binoculars-day.png"><img src="docs/screenshots/commander-v2-de-binoculars-day.png" alt="Brücke: Fernglas des Ausgucks, Tag"></a><br><sub>Brücke: Fernglas des Ausgucks, Tag</sub></td>
<td width="50%" align="center"><a href="docs/screenshots/commander-v2-de-periscope-night.png"><img src="docs/screenshots/commander-v2-de-periscope-night.png" alt="U-Boot Mast & ESM: Sehrohr, Nacht"></a><br><sub>U-Boot Mast & ESM: Sehrohr, Nacht</sub></td>
</tr>
<tr>
<td width="50%" align="center"><a href="docs/screenshots/commander-v2-de-opz-desktop.png"><img src="docs/screenshots/commander-v2-de-opz-desktop.png" alt="OPZ/CIC"></a><br><sub>OPZ/CIC</sub></td>
<td width="50%" align="center"><a href="docs/screenshots/commander-v2-de-sonar-desktop.png"><img src="docs/screenshots/commander-v2-de-sonar-desktop.png" alt="Sonar"></a><br><sub>Sonar</sub></td>
</tr>
<tr>
<td colspan="2" align="center"><a href="docs/screenshots/commander-v2-de-uboot-engine-desktop.png"><img src="docs/screenshots/commander-v2-de-uboot-engine-desktop.png" alt="U-Boot-Maschinenraum: Maschinenleitstand"></a><br><sub>U-Boot-Maschinenraum: Maschinenleitstand</sub></td>
</tr>
</table>

Mehr: [Fernglas bei Nacht](docs/screenshots/commander-v2-de-binoculars-night.png), [Sehrohr bei Tag](docs/screenshots/commander-v2-de-periscope-day.png), [Sonar mit 2560 x 1440](docs/screenshots/commander-wide.png), die [vollständige deutsche/englische Desktop- und Mobilmatrix](docs/screenshots/commander-captures.de.md) und die [lokalen Remote-Crew-Optionen](docs/screenshots/de-commander-options.png).

Alle Bilder nach einem Update neu erzeugen: `python tools/capture_screenshots.py`
(uConsole-Ansichten, ohne Bildschirm) und `python tools/capture_commander.py`
(Browser-Ansichten; braucht ein installiertes Chromium im `PATH`).

## Highlights

- Neun Stationen: Brücke, Sonar, Waffen, Schadensabwehr, OPZ/CIC, Funk,
  Maschinenraum, Helikopterdeck und Elektronische Kampfführung/ESM.
- Vier integrierte Szenarien, frei einstellbarer eigener Schwierigkeitsgrad und durchgehende Echtzeitsimulation (keine Pause, kein Zeitraffer).
- Passives HMS und Schleppsonar, aktives Sonar, Breitband- und LOFAR-Anzeigen,
  DEMON-Analyse, Bathythermografmessungen und rein peilungsbasierte TMA.
- Seeziel- und Luftraumradar, AIS, ESM, HFDF, manuelle Klassifikation und
  Zugehörigkeitsbewertung sowie ein gemeinsames Lagebild.
- Schiffs- und Helikoptertorpedos, Sonarbojen, feindliche Flugkörper, ESSM,
  CIWS und Düppel.
- Zivile Schifffahrt, feindliche Überwasserschiffe, Luftfahrzeuge, biologische
  Kontakte und akustische Täuschkörper.
- Flutung, Feuer, neun auswählbare Zonen in einem prozedural erzeugten
  F-217-Systemschema und drei zuweisbare Reparaturtrupps. Das Schema ist fiktiv
  und kein realer F123-Abteilungsplan.
- Fünf lokale Speicherplätze mit deterministischen Weltzuständen.
- Englische und deutsche Oberflächenkataloge, Erkennung der Systemsprache und
  ein Optionsbildschirm.
- Kontexthinweise an allen neun Stationen: Mit dem Mauszeiger erscheint eine
  vorübergehende Erklärung; ein Linksklick auf ein angezeigtes Element fixiert
  den Hinweis. `Esc` entfernt eine Fixierung, bevor der Beenden-Dialog geöffnet
  wird.
- Eine native Oberfläche mit 1280 x 720 Pixeln, die bei Bedarf unter Wahrung des
  Seitenverhältnisses mit Balken dargestellt wird. Karten und Symbole zeichnet
  Pygame; Audio wird zur Laufzeit synthetisiert.
- Optionale Remote Crew für vertrauenswürdige LANs: Mehrere authentifizierte
  Browser-Clients können exklusive Stationsrollen innehaben, zwischen ihren
  behaltenen Rollen wechseln, dieselben beobachtungsbasierten Bedienelemente
  nutzen und mit einer getrennten Freigabe direkt Waffen einsetzen.
  Die Browserkonsole ist ein Gefechtszentrale-Layout auf einer Bildschirmseite
  für große Desktop-Monitore: Statusleiste, zentrales Instrument und
  einklappbare Seitenleisten. `python main.py --solo-crew` (oder die F9-Zeile
  „Crew-Modus“) lässt einen einzigen Browser alle neun Stationen samt
  Speichern/Laden und neuem Spiel bedienen, während die uConsole der
  Simulationsserver bleibt; siehe [Einrichtung von Remote Crew](docs/commander-coop.de.md).
- Konservative stationsbezogene Autocrew mit `F2` und einer Übersicht mit `F3`.
  Remote Crew pausiert Autocrew nur für die jeweils belegte Station.
- Deterministisches Seewetter mit Wind, Regen, Sicht und weichen
  Seegangübergängen. Wetter beeinflusst Radar, Ausguck, Sonar und
  Helikoptergrenzen, erzeugt aber keine verborgene Winddrift.
- Modellierter Treibstoffverbrauch mit Ausdauer, Reichweite und Reparaturtrends
  im Maschinenraum.

## Windows-Programm

Lade `U-Jagd-Windows.exe` aus dem
[neuesten Release](https://github.com/db9979/uconsole_asw_game/releases/latest)
und starte es; Python ist nicht nötig. Im Starterfenster wählst du den
Besatzungsmodus (mehrere Browser, je eine Station) oder den Solomodus (ein
Browser bedient alle Stationen), ob dieser PC das U-Boot spielt, Fenster oder
Vollbild, Ton und Port, und das Feld **Sprache** oben stellt Starter, Spiel
und Besatzungs-Browser zwischen English und Deutsch um (in den Einstellungen
gespeichert); **Server starten** öffnet dann das Spielfenster, und
Remote Crew lauscht bereits auf der privaten LAN-Adresse des PCs. Der Starter
zeigt Browser-Adresse, Beitrittscode und QR-Code; Stationsanfragen bestätigst
du wie auf dem uConsole im Spielfenster (F9). Windows fragt eventuell einmal,
ob U-Jagd private Netzwerke nutzen darf: zulassen, sonst können sich andere
Geräte nicht verbinden. **Server stoppen** beendet das Spiel (nicht
gespeicherter Fortschritt geht verloren), und der Link unten öffnet die
"Buy me a coffee"-Seite; das Protokoll liegt in
`%USERPROFILE%\.u-jagd\logs\server.log`.

Bei jedem Start fragt das Programm GitHub, ob es ein neueres Release gibt, und
bietet **Update installieren** an: Es lädt die neue Datei, prüft Größe und
SHA-256-Prüfsumme, schließt sich, ersetzt sich selbst und startet die neue
Version (eine liegengebliebene `U-Jagd-Windows.exe.new` löscht es beim
nächsten Start). Das Programm ist nicht
signiert, deshalb warnt Windows SmartScreen beim ersten Start eventuell
("Weitere Informationen", "Trotzdem ausführen"). Spielstände und Einstellungen
liegen wie unter Linux in `%USERPROFILE%\.u-jagd\`.

Der Workflow `.github/workflows/windows.yml` baut das Programm mit PyInstaller
(`packaging/windows/u-jagd-windows.spec`) bei jedem Push und Pull Request,
führt seinen Selbsttest ohne Bildschirm aus (kurze Mission plus
Remote-Crew-Seiten) und veröffentlicht auf `main` einmal je Version das
Release `v<APP_VERSION>`; danach löscht er alle älteren Releases, sodass nur das
neueste samt seinem Git-Tag stehen bleibt (ältere `vX.Y.Z`-Tags werden mit
gelöscht). Selbst bauen unter Windows:
`python -m pip install -e ".[windows]"` und
`pyinstaller packaging/windows/u-jagd-windows.spec`.

## Voraussetzungen

- Linux (oder Windows mit dem fertigen [Windows-Programm](#windows-programm))
- Python 3.11 oder neuer
- Pygame 2.6 oder neuer
- NumPy 2.0 oder neuer
- Eine von Pygame unterstützte Anzeige
- Ein Audiogerät ist optional; ist kein Audiogerät verfügbar, wird der Start
  lautlos fortgesetzt

## Schnellstart

Auf der ClockworkPi uConsole installiert ein einziger Befehl das Spiel mit
Menüeintrag und automatischem Update (jeder Start holt das neueste Release;
ohne Netz startet die installierte Version):

```sh
curl -fsSL https://raw.githubusercontent.com/db9979/uconsole_asw_game/main/packaging/uconsole/install.sh | sh
```

Manuelle Einrichtung auf jedem Linux-System:

```sh
git clone https://github.com/db9979/uconsole_asw_game.git
cd uconsole_asw_game
python3 -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python main.py
```

Details zum Installer, Systempakete, manuelle Aktualisierungen und
Fehlerbehebung für die ClockworkPi uConsole sind in [`docs/install-uconsole.md`](docs/install-uconsole.md) beschrieben.

## Kommandozeile

Der Standardstart verwendet entsprechend der gespeicherten Einstellung den
Vollbildmodus und wählt einen zufälligen Missions-Seed:

```sh
python main.py
```

Folgende Argumente werden unterstützt:

```sh
python main.py 12345
python main.py 12345 --windowed
python main.py --no-audio
python main.py --version
```

`--windowed` und `--no-audio` überschreiben für diesen Start die entsprechenden
gespeicherten Optionen. Es gibt weder `--fullscreen` noch eine
Kommandozeilenoption für die Sprache. Nach einer Paketinstallation ist derselbe
Einstiegspunkt als `u-jagd` verfügbar, beispielsweise `u-jagd --windowed`.

`python main.py --remote-crew` startet Remote Crew beim Start im
Besatzungsmodus auf der ersten privaten LAN-Adresse, wie es die F9-Zeile tun
würde (`--solo-crew` entsprechend im Solomodus; `--web-port` wählt den Port,
Standard 8765). `--status-file PFAD` schreibt Remote-Crew-Adresse und
Beitrittscode als JSON nach `PFAD`, sobald sie sich ändern; der
Windows-Starter liest diese Datei.

## Spiel starten

Das Hauptmenü enthält Einträge für ein neues Spiel, Laden, Missionseditor,
Einheiteneditor, Optionen und Beenden. Bei einem neuen Spiel folgen die Auswahl
des Szenarios und, beim Zufallsszenario, ein Bildschirm für den eigenen
Schwierigkeitsgrad (Tarnung der U-Boote, Reparaturgeschwindigkeit, Torpedoanzahl
und Treffertoleranz, Aggressivität des Gegners, Anfangsseegang, Anzahl von
U-Booten, Kriegsschiffen und Verkehr, Häufigkeit von Luftangriffen und
Zeitlimit).

- `W` wechselt zwischen dem durch den Seed gewählten realen Sektor, der
  festen klassischen Referenzkarte und einem fest wählbaren realen Sektor.
- Im festen realen Modus wählen `Bild auf`/`Bild ab` den Küstenabschnitt.
- `R` erzeugt einen neuen Seed; im festen realen Modus bleibt der Abschnitt erhalten.
- `F` schaltet im Menü den Vollbildmodus um.
- Mit den Pfeiltasten wird ein Eintrag ausgewählt; `Enter` oder `Space`
  bestätigt ihn.

Ein Seed wählt einen von 128 aus realen Daten abgeleiteten Küstensektoren mit
500 NM Ausdehnung und erzeugt im selben Weltmodus immer dieselbe Welt. Die feste
klassische Karte bleibt als getrennte stilisierte Option verfügbar.

Beim Missionsstart geht im Funkraum ein grober, statischer Aufklärungshinweis
auf mögliche Unterwasser- oder feindliche Überwasseraktivität ein. Peilung und
Entfernung sind bewusst grob gerundet, die Position ist ausdrücklich unbestätigt
und stellt keinen Sensor-Fix dar. Ist keine verlässliche anfängliche Position
verfügbar, fordert die Meldung dazu auf, den Missionssektor mit den Bordsensoren
aufzuklären.

## Steuerung

Drücken Sie im Spiel `F1` (oder `?`), um die kontextsensitive Hilfe aufzurufen;
ihre vierte Kategorie ist das vollständige Spielerhandbuch (Schnellstart, ein
Kapitel je Station mit Anzeigen, Tasten, Standardablauf und Tipps sowie
Referenzdaten). Dasselbe Handbuch liegt als
[`docs/manual/manual.de.md`](docs/manual/manual.de.md) /
[`manual.en.md`](docs/manual/manual.en.md) vor und wird von Remote Crew unter
`/manual-de` und `/manual-en` ausgeliefert. Druckfassungen liegen als
[`docs/manual/handbuch.de.pdf`](docs/manual/handbuch.de.pdf) /
[`manual.en.pdf`](docs/manual/manual.en.pdf) vor (`python tools/build_manual_pdf.py`,
benötigt ein lokales Chromium). Eine
vollständige druckbare Übersicht der lokalen Tastenkürzel steht als
[`docs/station-shortcuts.de.pdf`](docs/station-shortcuts.de.pdf) bereit; die
Textquelle ist [`docs/station-shortcuts.de.md`](docs/station-shortcuts.de.md).
Die wichtigsten globalen Bedienelemente sind:

| Eingabe | Aktion |
|---|---|
| `1` bis `9` | Brücke, Sonar, Waffen, Schadensabwehr, OPZ/CIC, Funk, Maschinenraum, Helikopter, Elektronische Kampfführung/ESM; erneutes Drücken der Nummer der aktiven Station wechselt, sofern vorhanden, zur nächsten Seite |
| `F` / `Shift+F` / `B` bei ESM | Signalstatus-, Mindestbedrohungs- und Frequenzbandfilter wechseln |
| `Tab` / `Shift+Tab` | Nächste / vorherige Station |
| `F1` / `?` | Kontextsensitive Hilfe; Kategorie 4 ist das vollständige Handbuch |
| `0` | Wetter- und Sonar-Analysefeld über jeder Station |
| `F11` | Vollständiges Ereignislog und Telemetrie über der Station (läuft weiter) |
| `N` | Nationen und Einheiten (am Sonar: Notchfilter) |
| `P` | Plotmodus auf Brücken-/Waffen-/Helikopterkarte und OPZ-Karte: Marken, Lineal, Peillinien, Kreise, Koppellinien (`M R B C D`, `Enter`/Klick, `Backspace`) |
| `F2` / `F3` | Autocrew der aktuellen Station umschalten / Autocrew-Übersicht öffnen |
| `F4` | SimLog öffnen, sofern aktiviert |
| `F8` | Taktischen Einheitenanalysator öffnen; gegebenenfalls sichtbaren Commander-Vorschlag wechseln |
| `F10` | Optionen |
| `F9` | Lokale Commander-LAN-Verwaltung |
| `S` / `L` | Speichern / Laden über die Plätze 1 bis 5; in der OPZ ist `L` der kontextbezogene Fusionsbefehl |
| `+` / `-` | Maschinentelegraf |
| `Alt+Enter` | Vollbildmodus umschalten |
| `Ctrl+Enter` | Primäre Waffenaktion an den Stationen Waffen, OPZ/CIC oder Helikopter; die normalen Bereitschaftsprüfungen gelten |
| `Q` / `E` oder Mausrad | Karten an den Stationen Brücke, Waffen und Helikopter zoomen; die OPZ-Karte zoomt mit dem Mausrad |
| Ziehen mit der Maus | Eine sichtbare Karte einschließlich der OPZ-Karte verschieben und ihre eigene Kameraverfolgung ausschalten |
| `K` | Kameraverfolgung auf der aktuellen Karte oder der OPZ-Karte umschalten |
| `Esc` | Einen fixierten Hinweis entfernen, die aktuelle Ansicht/Eingabe abbrechen oder die Beenden-Bestätigung öffnen (zurück zum Spiel, speichern und beenden, Hauptmenü, ohne Speichern beenden) |
| `R` / `M` nach Missionsende | Neustart mit gleichem Seed / zurück zum Hauptmenü |

Stationstasten sind bewusst kontextabhängig. Beispielsweise sendet `Shift+A` am
Sonar einen aktiven Ping, während dort `A` den Breitband-Hörmodus wählt und
`A` im Maschinenraum den Akustikmodus ändert. Verwenden
Sie `F1`, statt davon auszugehen, dass eine Taste an jeder Station dieselbe
Bedeutung hat.

In der Hilfe wechselt Links/Rechts die Kategorie; Auf/Ab oder Page Up/Page Down
scrollt den Inhalt. Bestehende stationsbezogene Tastenkürzel für Waffen bleiben
verfügbar. Gedrückt gehaltene Kurs- und Torpedotiefensteuerungen verwenden
Echtzeit.

Der Ereignis-Feed am unteren Rand gilt stationsübergreifend. Er bewahrt operative
Meldungen, abgeschlossene Befehle und Alarme auf, darunter Missionsergebnis,
Waffen- und Abwehrereignisse, Schaden, Funkverkehr und Navigation.
Kurzlebige Eingabe-, Fehler-, Auswahl- und Anzeigehinweise bleiben im
Statusbanner, damit sie die operative Historie nicht verdrängen.

Klicken Sie bei der Schadensabwehr auf eine Zone oder deren Beschriftung, um sie
auszuwählen und die Zuweisung des aktuell gewählten Trupps zu versuchen. Sind
Kontexthinweise aktiviert, fixiert der Klick zugleich ihre Details. Auf/Ab wählt
einen Trupp, Enter weist ihn zu und Backspace zieht ihn ab. Flutungs- und
Brandtrends zeigen die
Nettorate des Modells einschließlich der Auswirkungen von Schwierigkeitsgrad und
mehreren Trupps.

## Sonar-Hinweise

Passives Sonar liefert unsichere Peilungen, keine tatsächlichen Positionen oder
Tiefen. TMA benötigt eine Peilungshistorie und Manöver des eigenen Schiffs, bevor
eine brauchbare Schätzung von Position und Bewegung möglich ist. Aktive Echos
liefern nach der modellierten Schalllaufzeit gemessene Peilung, Entfernung und
Tiefe mit Unsicherheit; sie bleiben auf der Seite `ACTIVE` erhalten und
verblassen mit zunehmendem Alter. Ein aktiver Fix läuft ab, und eine Aussendung
kann U-Boote aus größerer Entfernung alarmieren, als die Fregatte ein Echo
empfangen kann. Abschattung durch die Küste, Seegang, Geometrie der
Thermokline, Eigengeräusch und Array-Auswahl beeinflussen die Ergebnisse.

TMA- und Sonarbojen-Fixes laufen ebenfalls unabhängig davon ab, ob weiterhin
passiv etwas gehört wird. Hinweise zu historischen Plotpunkten beziehen sich auf
die angezeigte Messung. Aktive Echos behalten die zum Sendezeitpunkt eingefrorene
Geometrie; eine getrennte auslaufende Welle und das Abfangen durch einen bewegten
Empfänger werden nicht simuliert, und Ping-Warnungen für U-Boote erfolgen
weiterhin sofort.

Die Sonar-Wiedergabe verarbeitet die begrenzte Blockübergabe des
Empfängers der Reihe nach und versucht einen nicht angenommenen Block erneut,
wenn die Wiedergabewarteschlange voll ist. Bei einem Überlauf startet der Stream
neu, statt unzusammenhängende Abtastwerte zu verbinden. Die Analyse bleibt unabhängig von Wiedergabeverfügbarkeit und
Lautstärke. Nach dem Laden eines Spielstands durchläuft DSP bewusst erneut seine
Anlaufphase; gespeicherte taktische Beobachtungen bleiben erhalten.

Die Sonarbedienung umfasst:

- `Shift+A`: Einen aktiven Ping senden; der Sender hat 30 Sekunden Abklingzeit.
- `Shift+B`: HMS, TAS oder VDS als Empfangs-/Sende-Array auswählen.
- `A` / `B` / `H`: Breitband-, gefilterten oder Heterodyn-Hörmodus wählen.
- `Y`: TAS ausbringen oder einholen.
- `Shift+Y`: VDS fieren oder hieven (3-15 kn, Seegang bis 5).
- `U` / `V`: Nach dem Ausbringen die TAS/VDS-Solltiefe anpassen.
- `Page Up` / `Page Down`: Zwischen den Seiten Broadband, LOFAR, DEMON, TMA,
  Environment und ACTIVE wechseln.
- `2` bei bereits aktivem Sonar: Zur nächsten Sonarseite wechseln.

Das Bedienen des TAS schreitet nur zwischen 3 und 12 kn voran. Das Ausbringen
dauert sechs Simulationsminuten, das Einholen acht; das vollständig ausgebrachte
Array benötigt weitere 30 Sekunden zum Einschwingen, bevor es seine volle
Leistung erreicht. Außerhalb des Bereichs von 3 bis 12 kn pausiert die Bedienung.
Werden bei ausgebrachtem Kabel 20 kn überschritten, fällt das Array für den Rest
des aktuellen Spiels aus. Die TAS-Tiefe wird ebenfalls durch die Schiffsfahrt
begrenzt.

Die Auswahl von TAS macht es nicht automatisch verfügbar: Ein TAS-Ping kann erst
Echos erzeugen, nachdem genügend Kabel ausgebracht wurde. Wird `Shift+A` bei nicht
verfügbarem TAS gedrückt, wird der Befehl abgelehnt, ohne zu senden oder die
gemeinsame Ping-Abklingzeit zu verbrauchen. Die aktive Reichweite von TAS ist
geringer als die von HMS; sein Hauptvorteil liegt in der Genauigkeit passiver
Peilungen und der Leistung gegen passend geschichtete Kontakte nach dem
Einschwingen.

## Radar-Hinweise

In der OPZ/CIC wählen `Page Up` und `Page Down` den schiffszentrierten
Radarbereich von **10, 20, 40, 80 oder 120 NM**; sie verschieben oder zoomen die
Karte nicht und wechseln weder die Seite noch die Sensorleistung. Die
bildschirmhohe, genordete OPZ-Karte hat eine eigene Kamera: Das Mausrad zoomt
um den Mauszeiger bis auf 5 NM Radius, Ziehen auf freier Kartenfläche
verschiebt sie, und `K` schaltet die Verfolgung des eigenen Schiffs um. Anfangs
zeigt sie etwa 40 NM Radius. Ereignis-Feed und Telemetrie sammeln weiter,
während sie an dieser Station ausgeblendet sind, und erscheinen an anderen
Stationen unverändert wieder. Die modellierten Erfassungsgrenzen bei klarem Wetter betragen
30 NM für das Seezielradar und 100 NM für das Luftraumradar, mit
Leistungseinbußen ab Seegang 5 und durch Regenclutter. Seeziel- und
Luftraumradar können mit `R` und `Shift+R` getrennt gesteuert werden.

## Sprache und Optionen

Beim ersten Start wählt U-Jagd bei einer deutschen Systemsprache Deutsch und bei
einer englischen oder nicht unterstützten Systemsprache Englisch. Im
Optionsbildschirm kann ausdrücklich zwischen `en` und `de` gewechselt werden;
dort werden außerdem Vollbildmodus, Audio, Großschrift und Kontexthinweise
eingestellt.

Die Einstellungen für Sprache, Vollbildmodus, Audio, Großschrift und
Kontexthinweise werden in `~/.u-jagd/settings.json` geschrieben. Der Zustand der
Kontexthinweise gilt daher global und wird für die deterministische
Wiederherstellung bestehender Sitzungen zusätzlich in Spielständen des Formats
v31 gespeichert.

## Commander-LAN-Koop

Verwenden Sie auf der uConsole **F10 > Commander LAN** oder **F9**. Wählen Sie bei
ausgeschaltetem Dienst ausdrücklich eine private IPv4-Adresse und aktivieren Sie
ihn anschließend. Öffnen Sie auf jedem Besatzungsgerät die angezeigte URL. Die
Voreinstellung `127.0.0.1:8765` gilt nur für das lokale Gerät und ist von anderen
Geräten nicht erreichbar. Eine Router-Portweiterleitung ist weder erforderlich
noch unterstützt.

Soll dieselbe Crew- oder Solo-Sitzung zusätzlich über einen eigenen
HTTPS-Reverse-Proxy erreichbar sein, starten Sie das Spiel mit
`--public-origin https://asw.example.net` (bei Bedarf mit `--solo-crew`) und
lassen den Proxy auf die in F9 angezeigte LAN-Adresse zeigen. Die LAN-Adresse
bleibt nutzbar; F9 zeigt dann beide Adressen. Details und Sicherheitshinweise:
[`docs/web-host.de.md`](docs/web-host.de.md).

Alternativ kann die uConsole einen temporären WPA2-Hotspot für Remote Crew
bereitstellen. Installieren Sie dafür einmalig den eng begrenzten Helper mit
`sudo ./packaging/uconsole/install-hotspot-helper.sh`, wählen Sie in F9 den
Hotspot-Netzmodus und aktivieren Sie den Dienst. U-Jagd erzeugt bei jedem Start
eine neue SSID und ein neues WLAN-Passwort und speichert beides nicht. Beim
Beenden von Remote Crew wird der Hotspot entfernt und die vorherige
WLAN-Verbindung wiederhergestellt. Das Spiel selbst darf nicht mit `sudo`
gestartet werden.

Koppeln Sie den Browser mit dem sechsstelligen Code: **drei Ziffern gefolgt von
drei Großbuchstaben**, beispielsweise `482KMT`. Fünf falsche Versuche innerhalb
einer gleitenden Minute sperren weitere Versuche vorübergehend. Der angezeigte
Code bleibt für weitere Besatzungsmitglieder gültig, bis der Host den Zugriff
widerruft oder der fünfte Fehlversuch ihn erneuert. Browser-Eingaben in
Kleinbuchstaben werden in Großbuchstaben umgewandelt. Das Beispiel ist kein
gültiger Zugangscode.

Nach der Kopplung fordert jeder Browser eine oder mehrere Stationen an. Der Host
vergibt jede Station exklusiv; mit der Genehmigung wird die normale
Stationsbedienung automatisch aktiviert, während Sonaraudio und direktes Feuer
getrennte Freigaben bleiben. Ein Browser zeigt jeweils eine aktive Station an,
fordert über **Station hinzufügen** eine weitere an und behält seine anderen
Stations-Leases für einen schnellen Wechsel über die Stationsauswahl. Eine
genehmigte zusätzliche Station wird automatisch geöffnet. Jeder Befehl wird im
Hauptthread der Simulation erneut
anhand von Stationsschaden, Aktualität der Beobachtung, Bestand, Bereitschaft,
Einsatzregeln und aktueller Weltgeneration geprüft. Die Kommunikation ist
weiterhin auf eine externe Sprachverbindung angewiesen; Mikrofon und Chat sind
nicht enthalten.

Die Sonarbesatzung kann Zielvorschläge und die Brückenbesatzung Kurs- und
Fahrtvorschläge bereitstellen. Diese Anfragen wirken niemals direkt: Der Host
prüft sie lokal und nimmt sie an oder lehnt sie ab. Browseralarme bleiben
rollenbegrenzt. Das separat vom Host freigegebene, schreibgeschützte SimLog ist
eine Diagnoseausnahme und zeigt abgelöste Full-Truth-Snapshots einschließlich
versteckter Einheiten; eine Neuverbindung setzt eine stille
Ereignis-Ausgangsbasis, anstatt alte Alarme erneut abzuspielen.

Solange ein Browser eine Stations-Lease besitzt, ist die Bedienung der
entsprechenden Station auf der uConsole schreibgeschützt. Host-Verwaltung
und der Wechsel zu einer anderen Station bleiben verfügbar; der Widerruf der
Lease stellt die lokale Bedienung sofort wieder her.

Der Dienst startet **bei jedem Programmstart ausgeschaltet**. Zugriffe und
Freigaben werden nicht gespeichert. Zugangsdaten, Clients, Stations-Leases,
Netzwerkwarteschlangen, Entwürfe und nicht angenommene Befehle gelangen weder in
Spielstände noch in die Einstellungen. Ein Austausch der Welt widerruft aktive
Berechtigungen im nächsten Frame des Hauptthreads. Die Mission läuft immer in
Echtzeit: lokale Menüs und Overlays (Hilfe, Optionen, Speichern/Laden,
Beenden-Abfrage, F8-Analysator, F9-Verwaltung) und ein Fokusverlust pausieren sie
nie, Browser-Stationen bleiben dahinter bedienbar. Nur Hauptmenü und Splashscreen
sperren Änderungen aus dem Browser.
Sonarklang im Browser erfordert eine ausdrückliche Host-Freigabe und eine lokale
Benutzeraktion; nach einer Neuverbindung werden alte Audiodaten nicht
nachgespielt. Die Hörmodi Broadband, Filtered und Heterodyne verwenden die
gewählten Einstellungen für Band, Kerbfilter und Verstärkung. Ein Klick oder Tap
auf den Broadband-Wasserfall setzt die manuelle Horchpeilung des Sonars; LOFAR
tut dies nicht. Dieselbe lokale Ton-Schaltfläche aktiviert auf der Brücke ein
synthetisiertes Eigenschiff-Kavitationsgeräusch. Es verwendet ausschließlich die
projizierte Kavitationswarnung und steuert niemals das uConsole-Audio.
Beim Überfahren eines nicht verfügbaren Browser-Bedienelements erscheint der
aktuelle lokalisierte Grund, etwa fehlende Freigabe, Stationsschaden, Abklingzeit,
leerer Bestand, ausstehender Befehl oder die TAS-Fahrtgrenze.

Anwendungsversion, API-Protokoll **v2** und Speicherformat **v31** sind
voneinander unabhängige Kompatibilitätsverträge. Remote Crew verwendet
ausschließlich Protokoll v2; sämtliche Legacy-Routen unter `/api/v1/*` sind
entfernt und liefern 404.

**Sicherheit von Commander LAN:** HTTP ist unverschlüsselt. Verwenden Sie den
Dienst nur in einem vertrauenswürdigen LAN. Internet-Hosting, Bindung an
Wildcard-Adressen, CDN, ferne Steuerung von Einsatzregeln, Zeit oder
Speicherständen sowie verborgene Entity-Daten werden nicht bereitgestellt. Der
getrennte Webspiel-Modus verlangt einen HTTPS-Proxy und eine Host-Anmeldung. Siehe
[Einrichtung von Remote Crew](docs/commander-coop.de.md) und
[Protokoll/Sicherheit](docs/commander-protocol.de.md).

## Editoren und aktuelle Einschränkungen

Das Hauptmenü enthält einen Missionseditor und einen Einheiteneditor. Sie bieten
schreibgeschützte integrierte Bibliotheken, die Anzeige von Benutzerinhalten,
Validierung, Klonen, editierbare typisierte Felder und eine deterministische
statische Missionsvorschau. Missionsautoren können exakte Platzierungen,
Seed-basierte Zufallsgruppen, Ziele und zeitgesteuerte Ereignisse bearbeiten.
Einheitenautoren können alle sechs Profilarten erstellen und verschachtelte
Akustik- und Listendaten über sichere strukturierte Eingaben bearbeiten.
`Ctrl+E` und `Ctrl+I` dienen zum Exportieren und Importieren von Bundles. Die
JSON-Vorlagen unter `data/editor_templates/` beschreiben die akzeptierten
Schemata; Benutzerdateien werden unter `~/.u-jagd/missions/` und
`~/.u-jagd/units/` gespeichert.

Validiert bedeutet nicht, dass ein Wert zur Laufzeit wirksam ist. In dieser
Version gilt:

- Eine Benutzermission kann nur dann mit `F5` aus der Browseransicht des
  Missionseditors gestartet werden, wenn sie die unterstützte Laufzeitteilmenge
  verwendet.
- Eine Laufzeitmission braucht eine 500-NM-Welt: `fixed` (der aktuelle
  Weltmodus des Spiels) oder `reference` mit einem der 128 mitgelieferten
  realen Sektoren (`sector:0` bis `sector:127`, im Editor aus einer Liste
  gewählt). Andere Weltgrößen werden abgelehnt. Die Weltdefinition des Editors
  ersetzt nicht den Küstendatensatz des Spiels.
- Wirksame Missionswerte sind Seed, Name und Beschreibung; Position, Kurs und
  Fahrt des Spielerschiffs; Seegang, Startzeit, Thermoklinentiefe und eine
  vorgegebene Wetterart; exakte Einheiten aller Arten, integriert oder aus
  dem Einheiteneditor (U-Boote, Überwasserschiffe, Luftfahrzeuge mit
  Profilfahrt vom nächsten Flugplatz der Karte, Tiere, stationäre
  Täuschkörper und feindliche Torpedos, die schon auf ihrem Kurs laufen) mit
  Platzierung, Kurs, Fahrt und Tiefe; Seed-basierte Zufallsgruppen;
  zeitgesteuerte Ereignisse (Meldung, Erscheinen, Wetter, Ziel); sowie Ziele
  vom Typ `sink`, `survive`, `protect` oder `reach` mit einem Zeitlimit.
- Bei `sink` muss die Zielliste exakt allen platzierten feindlichen U-Booten
  entsprechen; `protect`-Ziele müssen platzierte befreundete oder neutrale
  Einheiten sein; `reach` braucht ein Zielgebiet.
- Eigene Einheitenprofile wirken in den Missionen, die sie verwenden: Name,
  Fahrtbereich, Tiefe, Torpedozahl, Verhalten, Akustik und Häufigkeit. Ein
  eigenes U-Boot übernimmt Sensoren, Rohre, Täuschkörper und
  Batterie-/Diesel-/AIP-Anlage vom eingebauten Boot seines Antriebs
  (Stichworte `nuclear`/`Kern`, `AIP`, sonst dieselelektrisch). Zusätze aus dem
  Wikipedia-Import (Radar, Waffen, Gegenmaßnahmen) bleiben beschreibend. Ein
  fehlendes oder ungültiges Profil lehnt die Mission ab; eingebaute Szenarien
  verwenden nie Benutzerprofile.
- Platzieren lassen sich nur feindliche Torpedos, immer feindlich; Torpedos der
  Fregatte und des Helikopters werden abgelehnt und nicht stillschweigend
  ignoriert.

## Spielstände und Benutzerdaten

Dieser Stand schreibt und lädt ausschließlich das Speicherformat **v31**. V31
verlangt das exakte Schema `u-jagd-save-v31` einschließlich der gemeldeten Positionen empfangener AIS-Meldungen, der Befehle der Führung an das besetzte U-Boot, der sinkenden Wasserbomben und der eigenen ASROC- und Wasserbombenbestände der Fregatte, der Autopilot-Route der Fregatte, der Umlaufzeit-Referenz des U-Boot-ESM, der Rohrzustände des besetzten U-Boots, der Radarpunkte und OPZ-Markierungen der Fregatte, der Marken des Angriffsrechners, des Tiefensonars
der Fregatte, des Funkraums des besetzten U-Boots, der Auftragstafel
der Führung, der Wachpläne beider Crews, des Seefernaufklärers und des Besitzers
jeder Boje, des aktuellen
Schnappschusses des Laufzeitkatalogs, des gesamten Zustands für die
deterministische Fortsetzung, des Crew-Zustands des besetzten U-Boots (Befehle,
Modi, Mast, Drähte, Plot, Alarmpeilungen, seine Sonarstation und sein ESM-Bild),
solange eine Crew das U-Boot führt, von Tauchzellen, Trimm, Pressluft, Abteilungen und Leckwehrtrupps jedes U-Boots, von
Diesel, Laderate und Luftvorräten jedes konventionellen U-Boots und der fremden
Aktivpings, deren Schall noch zur Fregatte unterwegs ist. Ältere (auch alle v11-Spielstände von 1.0.0),
neuere, fehlerhafte oder unvollständige Spielstände werden ohne Migration
abgelehnt, ohne das laufende Spiel zu ersetzen.

Die fünf Speicherplätze sind `~/.u-jagd/slot1.json` bis `slot5.json`.
Spielstände enthalten einen Schnappschuss der Küstengeometrie und der
synthetischen Bathymetrie, damit ein bestehendes Spiel nicht mit einer späteren
Version des Weltgenerators neu erzeugt wird.

## Weltdaten und Haftungsausschluss

`data/coastlines/real_sectors.json.gz` enthält exakt 128 vorab validierte
500-NM-Sektoren, die aus Ländergeometrien von Natural Earth und einem
Wikidata-Schnappschuss von Flugplatzkoordinaten abgeleitet wurden. Daher können
echte Orts-, Länder- und Militärstützpunktnamen sowie Quellkoordinaten erscheinen.
Freundliche, feindliche, neutrale und zivile Rollen werden unabhängig davon als
fiktive Übungsrollen zugewiesen und beschreiben weder die realen Staaten noch die
realen Einrichtungen.

Die Bathymetrie ist synthetisch; alle taktischen Reichweiten,
Plattformleistungen, akustischen Eigenschaften, Zugehörigkeiten und Übungsrollen
sind Daten des Spielmodells. Nichts in diesem Repository eignet sich für
Navigation, Vermessung, die Bestimmung realer Fähigkeiten oder Einsatzplanung.
U-Jagd steht weder mit Natural Earth, Wikidata, deren Mitwirkenden,
Plattformherstellern, militärischen Organisationen, Regierungen oder Inhabern
von Rechten an Quellen in Verbindung noch wird es von ihnen unterstützt.

Die genaue Herkunft, Versionen, Hashes, Hinweise zur Verarbeitung und Lizenzen
sind in [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md) dokumentiert.

## Entwicklung und Tests

Die Prüfung der Arbeitsplätze und Modelle, umgesetzte Korrekturen, verbleibende
Modellgrenzen und die Checkliste für die Hardware-Abnahme sind in
[`docs/workstation-review.md`](docs/workstation-review.md) dokumentiert.
Aktuelle Arbeiten werden in [`docs/plan-1.3.md`](docs/plan-1.3.md) und
[`docs/resume.md`](docs/resume.md) verfolgt.

Installieren Sie das Projekt und die Entwicklungsabhängigkeit und führen Sie
anschließend die Testsuite aus:

```sh
python -m pip install -e '.[dev]'
pytest
```

Validieren Sie den erzeugten Kontaktkatalog mit:

```sh
python tools/gen_contacts.py --check
```

Erzeugen Sie ein Wheel mit einem PEP-517-Frontend:

```sh
python -m pip install build
python -m build
```

## Unterstützen

U-Jagd ist ein kostenloses Hobbyprojekt von Dominik Bornhäußer. Wenn es dir
gefällt, kannst du die Entwicklung unter
[buymeacoffee.com/zquu1xu570](https://buymeacoffee.com/zquu1xu570) unterstützen.
Das Spiel zeigt den Link nur dort, wo gerade niemand spielt: als QR-Code im
Hauptmenü des uConsole sowie auf den Remote-Crew-Seiten Kopplung, Lobby und
Einstellungen und auf der Admin-Seite des Webspiels. GitHub zeigt ihn als
Sponsor-Knopf des Repositorys.

## Lizenz und Danksagungen

Der Projektcode und die projektspezifische Dokumentation stehen unter der
MIT-Lizenz; siehe [`LICENSE`](LICENSE). Pygame, NumPy, geografische Quelldaten
und alle zukünftigen Assets behalten ihre jeweiligen Lizenzen und
Attributionsanforderungen. Siehe
[`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md) und
[`assets/README.md`](assets/README.md).
