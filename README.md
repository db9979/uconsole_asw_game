# U-Jagd

U-Jagd ist ein deutschsprachiges Echtzeit-Taktikspiel zur U-Boot-Jagd (ASW).
Als Kommandant einer Fregatte koordinierst du Brücke, Sonar, Waffen,
Schadensabwehr, OPZ, Funk, Maschine und Bordhubschrauber. Das Spiel ist für die
ClockworkPi uConsole ausgelegt, läuft aber auch auf anderen Linux-Systemen mit
Python und Pygame.

Aktuelle Projektversion: **0.1.0**

<img width="1139" height="634" alt="image" src="https://github.com/user-attachments/assets/df2501a0-f46e-4f0f-878c-2d0d9159c025" />


> Entwicklungsstand: spielbarer früher Release. Bedienung, Balancing und
> Plattformunterstützung können sich noch ändern.

## Funktionen

- vier Szenarien mit wählbarer prozeduraler Welt oder fester Referenzkarte
- seedbasierte Küsten, Inseln, Airbases und taktische Bathymetrie
- aktive und passive Sonararbeit mit HMS/TAS, LOFAR, DEMON und TMA
- Radar, AIS, ESM/HFDF und manuelle Kontaktklassifizierung
- Torpedos, Bordhubschrauber, Sonarbojen und Flugkörperabwehr
- zivile Schifffahrt, biologische Falschkontakte und Küstengeometrie
- Schadens-, Feuer- und Reparatursystem
- Pause und mehrere Zeitrafferstufen
- fünf lokale Speicherstände
- prozedural synthetisierte Audio- und Anzeigeelemente ohne mitgelieferte
  Medienpakete

Das ausführliche Spieldesign und der technische Status stehen in
[`docs/GDD.md`](docs/GDD.md) und
[`docs/implementation-plan.md`](docs/implementation-plan.md).

## Voraussetzungen

- Python 3.11 oder neuer
- ein von Pygame unterstütztes Display
- optional ein Audiogerät; ohne verfügbares Audiogerät läuft das Spiel stumm

Die Python-Laufzeitabhängigkeiten sind `pygame` und `numpy`. Auf der uConsole
sind Python 3.13 und Pygame 2.6 die derzeit dokumentierte Zielumgebung.

## Schnellstart

```sh
git clone https://github.com/db9979/uconsole_asw_game.git
cd uconsole_asw_game
python3 -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python main.py
```

Eine uConsole-spezifische Schritt-für-Schritt-Anleitung mit Systempaketen,
Updates und Fehlerdiagnose steht in
[`docs/install-uconsole.md`](docs/install-uconsole.md).

## Startparameter

Ohne Parameter startet das Spiel im Vollbild und erzeugt einen zufälligen Seed:

```sh
python main.py
```

Für ein reproduzierbares Spiel kann ein ganzzahliger Seed angegeben werden:

```sh
python main.py 12345
```

Für den Fenstermodus ist `--windowed` implementiert:

```sh
python main.py 12345 --windowed
```

Audio kann gezielt deaktiviert und die Version abgefragt werden:

```sh
python main.py --no-audio
python main.py --version
```

Nach einer Paketinstallation steht derselbe Einstiegspunkt als `u-jagd` zur
Verfügung, zum Beispiel `u-jagd --windowed`.

## Bedienung

Das Startmenü führt durch Szenario, gegebenenfalls Schwierigkeit und Briefing.
Mit `W` wechselst du dort zwischen prozeduraler Welt und fester Referenzkarte;
`R` erzeugt einen neuen Missions-Seed.
Im Spiel zeigt `F1` die vollständige kontextabhängige Tastenhilfe.

| Taste | Funktion |
|---|---|
| `1` bis `8` | Brücke, Sonar, Waffen, Schaden, OPZ, Funk, Maschine, Helikopter |
| `Tab` / `Shift+Tab` | nächste / vorherige Station |
| `P` | Pause / weiter |
| `F1` | Hilfe |
| `S` / `L` | speichern / laden, Slot 1 bis 5 |
| `Z` / `X` oder `[` / `]` | Zeitraffer langsamer / schneller |
| `+` / `-` | Maschinentelegraf |
| `Alt+Enter` | Vollbild umschalten |
| `Q` / `E` | Kartenzoom auf Brücke, Waffen- und Helikopterstation |
| `Q` / `Esc` | Beenden-Dialog |

Stationsabhängige Befehle, insbesondere Sonar-, Ziel- und Waffensteuerung,
sollten über `F1` nachgeschlagen werden. Die Belegung ändert ihre Bedeutung je
nach aktiver Station.

## Speicherstände und Daten

Speicherstände werden standardmäßig unter `~/.u-jagd/` abgelegt. Das Verzeichnis
`data/contacts/` enthält die erweiterbaren Kontaktprofile; Schema und Fallback
sind in [`docs/contacts-db.md`](docs/contacts-db.md) beschrieben.
`data/coastlines/region.json` enthält einen stilisierten, nicht für Navigation
geeigneten Nordsee-/Ostsee-Sektor. Beide Datenverzeichnisse werden bei
Paket-Builds mit aufgenommen.

Die Namen, Leistungswerte, Küsten und akustischen Profile sind spielerische
Modellannahmen. Sie sind keine verifizierten militärischen oder geografischen
Referenzdaten.

## Entwicklung

```sh
python -m pip install -e '.[dev]'
pytest
```

Ein Wheel kann mit einem PEP-517-Frontend wie `build` erzeugt werden:

```sh
python -m pip install build
python -m build
```

`pytest` ist nur eine Entwicklungsabhängigkeit und steht deshalb im optionalen
Extra `dev`, nicht in `requirements.txt`.

## Assets und Drittanbieter

Das Repository enthält derzeit keine externen Bild-, Schrift- oder Audiodateien.
Audio wird zur Laufzeit mit NumPy synthetisiert; die Oberfläche wird mit Pygame
gezeichnet. Regeln für spätere Medien liegen in [`assets/README.md`](assets/README.md).
Hinweise zu Python-Abhängigkeiten und Daten stehen in
[`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md).

## Lizenz

Der Projektcode und die projektspezifische Dokumentation stehen unter der
MIT-Lizenz, siehe [`LICENSE`](LICENSE). Drittanbieterkomponenten behalten ihre
jeweiligen Lizenzen.
