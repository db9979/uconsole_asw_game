[English README](README.md)

# U-Jagd

[![Buy me a coffee](https://img.shields.io/badge/Buy%20me%20a%20coffee-support-FFDD00?logo=buymeacoffee&logoColor=black)](https://buymeacoffee.com/zquu1xu570)

U-Jagd ist ein Echtzeit-Spiel zur U-Boot-Jagd, gebaut für die ClockworkPi
uConsole (1280 x 720) und auch für Windows und macOS erhältlich. Sie führen
die Fregatte F-217 mit neun Stationen oder ein U-Boot mit sieben und jagen die
andere Seite oder entkommen ihr. Freunde können Stationen im Browser im selben
Netz besetzen.

Aktuelle Version: **1.3.209**

Version 1.3.209 zeigt die Karten in echten geografischen Koordinaten. In
einem echten Seegebiet zeigt das Kartengitter jetzt Längen- und Breitengrade
in Grad und Minuten, beim Hineinzoomen feiner (5 Grad bis 0,1 Minute), oben
links steht die eigene Position wie 53°19,9'N 007°00,9'E (auf dem U-Boot der
gekoppelte Ort), und der Tooltip des Mauszeigers nennt die Position darunter,
auf der uConsole wie im Browser. Die Gitterzahlen bleiben jetzt auch über
Land lesbar. Entfernungen, Ringe und Maßstab bleiben in sm, das Spiel spielt
sich wie bisher; die stilisierte feste Karte behält ihr sm-Gitter. Tasten
bleiben gleich. Spielstände sind v52; v38 bis v51 laden weiter.

Frühere Versionen: [CHANGELOG.de.md](CHANGELOG.de.md).

U-Jagd ist ein Hobbyprojekt eines einzelnen Entwicklers. Es ist ein Spiel,
kein Ausbildungs- oder Navigationsprodukt, und seine Systeme sind bewusst
vereinfacht.

## Screenshots

### uConsole (1280 x 720)

<table>
<tr>
<td width="50%" align="center"><a href="docs/screenshots/de-frigate-binoculars-day.png"><img src="docs/screenshots/de-frigate-binoculars-day.png" alt="Fernglas der Fregatte, Tag"></a><br><sub>Fernglas der Fregatte, Tag</sub></td>
<td width="50%" align="center"><a href="docs/screenshots/de-uboot-periscope-night.png"><img src="docs/screenshots/de-uboot-periscope-night.png" alt="Sehrohr des U-Boots, Nacht"></a><br><sub>Sehrohr des U-Boots, Nacht</sub></td>
</tr>
</table>

Stationen der Fregatte:

<table>
<tr>
<td width="33%" align="center"><a href="docs/screenshots/de-station-bridge.png"><img src="docs/screenshots/de-station-bridge.png" alt="Brücke"></a><br><sub>Brücke</sub></td>
<td width="33%" align="center"><a href="docs/screenshots/de-station-sonar.png"><img src="docs/screenshots/de-station-sonar.png" alt="Sonar"></a><br><sub>Sonar</sub></td>
<td width="33%" align="center"><a href="docs/screenshots/de-station-weapons.png"><img src="docs/screenshots/de-station-weapons.png" alt="Waffen"></a><br><sub>Waffen</sub></td>
</tr>
<tr>
<td width="33%" align="center"><a href="docs/screenshots/de-station-opz-cic.png"><img src="docs/screenshots/de-station-opz-cic.png" alt="OPZ"></a><br><sub>OPZ</sub></td>
<td width="33%" align="center"><a href="docs/screenshots/de-station-eloka.png"><img src="docs/screenshots/de-station-eloka.png" alt="ELOKA"></a><br><sub>ELOKA</sub></td>
<td width="33%" align="center"><a href="docs/screenshots/de-station-helicopter.png"><img src="docs/screenshots/de-station-helicopter.png" alt="Hubschrauber"></a><br><sub>Hubschrauber</sub></td>
</tr>
</table>

Stationen des U-Boots:

<table>
<tr>
<td width="33%" align="center"><a href="docs/screenshots/de-uboot-command.png"><img src="docs/screenshots/de-uboot-command.png" alt="Führung"></a><br><sub>Führung</sub></td>
<td width="33%" align="center"><a href="docs/screenshots/de-uboot-sonar.png"><img src="docs/screenshots/de-uboot-sonar.png" alt="Sonar"></a><br><sub>Sonar</sub></td>
<td width="33%" align="center"><a href="docs/screenshots/de-uboot-navigation.png"><img src="docs/screenshots/de-uboot-navigation.png" alt="Navigation"></a><br><sub>Navigation</sub></td>
</tr>
</table>

Mehr: [Leckwehr](docs/screenshots/de-station-damage-control.png), [Funk](docs/screenshots/de-station-radio.png), [Maschine](docs/screenshots/de-station-engineering.png), [Waffen des U-Boots](docs/screenshots/de-uboot-weapons.png), [Maschine des U-Boots](docs/screenshots/de-uboot-engine.png), [Hauptmenü](docs/screenshots/de-main-menu.png) und [Missionseditor](docs/screenshots/de-mission-editor-detail.png).

### Browser (1920 x 1080)

<table>
<tr>
<td width="50%" align="center"><a href="docs/screenshots/commander-v2-de-opz-desktop.png"><img src="docs/screenshots/commander-v2-de-opz-desktop.png" alt="OPZ"></a><br><sub>OPZ</sub></td>
<td width="50%" align="center"><a href="docs/screenshots/commander-v2-de-sonar-desktop.png"><img src="docs/screenshots/commander-v2-de-sonar-desktop.png" alt="Sonar"></a><br><sub>Sonar</sub></td>
</tr>
</table>

Mehr: die [vollständige deutsche/englische Browser-Galerie](docs/screenshots/commander-captures.de.md).

## Funktionen

- Zwei Seiten: die Fregatte F-217 (neun Stationen) oder ein U-Boot (sieben Stationen).
- Zwölf Szenarien je Seite einschließlich Freier Fahrt, dazu Ausbildung,
  Tagesmission, Kampagne und Kurzeinsätze.
- Passives und aktives Sonar mit Schleppsonar und Tiefensonar (VDS), LOFAR,
  DEMON und Zielbewegungsanalyse nur aus Peilungen; Radar, ELOKA und Funk.
- Hubschrauber, Seefernaufklärer, Torpedos, Wasserbomben und ein
  Geleitzerstörer; Leckwehr mit Feuer, Wassereinbruch und Verwundeten.
- Immer Echtzeit: keine Pause und keine Zeitraffung. Freie Stationen
  besetzt die KI-Besatzung.
- Mehrspieler im Browser: jeder Spieler übernimmt eine oder mehrere
  Stationen, Handys kommen per QR-Code als Ausguck dazu.
- Missions- und Einheiteneditor mit Austausch; Deutsch und Englisch; helles,
  dunkles und kontrastreiches Farbschema.
- Ein optionales Sprachmodell für Funksprüche und einen Ersten Offizier; das
  Spiel funktioniert ohne es vollständig offline.

## Herunterladen und installieren

### Windows

`U-Jagd-Windows.exe` aus der
[neuesten Version](https://github.com/db9979/uconsole_asw_game/releases/latest)
laden und starten. Das Programm ist nicht signiert, daher kann SmartScreen
beim ersten Start warnen („Weitere Informationen", „Trotzdem ausführen").

### macOS (Apple Silicon)

`U-Jagd-macOS-arm64.zip` aus der
[neuesten Version](https://github.com/db9979/uconsole_asw_game/releases/latest)
laden, entpacken und `U-Jagd.app` in „Programme" ziehen. Die App ist nicht
notarisiert: einmal per Rechtsklick, **Öffnen** starten (macOS 15:
**Systemeinstellungen > Datenschutz & Sicherheit > Dennoch öffnen**). Für
Intel-Macs gibt es keinen Build.

### uConsole und Linux

Ein Befehl installiert das Spiel auf der uConsole mit Menüeintrag:

```sh
curl -fsSL https://raw.githubusercontent.com/db9979/uconsole_asw_game/main/packaging/uconsole/install.sh | sh
```

Auf jedem anderen Linux-System (Python 3.11 oder neuer):

```sh
git clone https://github.com/db9979/uconsole_asw_game.git
cd uconsole_asw_game
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.txt
python main.py
```

Einzelheiten und Fehlerhilfe: [Installationsanleitung für die uConsole](docs/install-uconsole.md).

### Updates

Es wird nichts automatisch installiert. Gibt es eine neuere Version, zeigen
Startbildschirm und Hauptmenü ihren Änderungseintrag und bieten **Jetzt
updaten** an. Spielstände und Einstellungen in `~/.u-jagd/` bleiben erhalten.

## Gemeinsam spielen

Im Hauptmenü **Mehrspieler** wählen. Die Lobby zeigt eine Adresse, einen
Kopplungscode und einen QR-Code; die anderen öffnen sie im Browser im selben
Netz und übernehmen Stationen, den Rest besetzt die KI. `python main.py --server`
lässt alle Spieler im Browser spielen. Unverschlüsseltes HTTP nur im eigenen,
vertrauenswürdigen Heimnetz verwenden. Einrichtung und Sicherheit:
[Remote-Crew-Anleitung](docs/commander-coop.de.md) und
[Webspiel im LAN](docs/web-host.de.md).

## Dokumentation

- Im Spiel öffnet `F1` die Kontexthilfe und das vollständige Handbuch.
- Handbuch: [Markdown](docs/manual/manual.de.md), PDF auf [Englisch](docs/manual/manual.en.pdf)
  und [Deutsch](docs/manual/handbuch.de.pdf).
- Druckbare Tastenübersicht: [Stations- und Tastenkürzel](docs/station-shortcuts.de.pdf).
- Remote-Crew-Protokoll und Sicherheit: [Protokoll](docs/commander-protocol.de.md).
- Versionsgeschichte: [CHANGELOG.de.md](CHANGELOG.de.md).

## Entwicklung

```sh
python -m pip install -e '.[dev]'
pytest
```

Architektur, Regeln und alle Prüfungen beschreibt [AGENTS.md](AGENTS.md).

## Weltdaten und Haftungsausschluss

Die Küsten stammen aus 128 Sektoren, abgeleitet aus Natural Earth und
Wikidata; echte Orts- und Stützpunktnamen können daher vorkommen. Ihre Rollen
im Spiel sind erfunden, und Wassertiefen, Reichweiten und Plattformdaten sind
Werte des Spielmodells. Nichts davon eignet sich für Navigation oder
Einsatzplanung. Quellen und Lizenzen:
[`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md).

## Unterstützung

U-Jagd ist kostenlos. Wenn es Ihnen gefällt, können Sie es unter
[buymeacoffee.com/zquu1xu570](https://buymeacoffee.com/zquu1xu570) unterstützen.

## Lizenz

Code und Projektdokumentation stehen unter der MIT-Lizenz, siehe
[`LICENSE`](LICENSE). Pygame, NumPy, Quelldaten und Schriften behalten ihre
eigenen Lizenzen, siehe [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md).
