# Installation auf der ClockworkPi uConsole

Diese Anleitung beschreibt Installation, Start und Aktualisierung von U-Jagd
aus dem Repository <https://github.com/db9979/uconsole_asw_game>. Zielsystem ist
eine uConsole mit Debian-basierter ClockworkPi-Distribution, insbesondere ein
CM5-System. Befehle ohne `sudo` laufen als normaler Benutzer.

## 1. System vorbereiten

Terminal öffnen und Paketlisten sowie vorhandene Pakete aktualisieren:

```sh
sudo apt update
sudo apt upgrade
sudo apt install git python3 python3-venv python3-pip
```

Für das Spiel werden Python 3.11 oder neuer, Pygame 2.6 oder neuer und NumPy 2.0
oder neuer erwartet. Version prüfen:

```sh
python3 --version
```

## 2. Repository beziehen

```sh
git clone https://github.com/db9979/uconsole_asw_game.git
cd uconsole_asw_game
```

Falls das Repository bereits vorhanden ist, nicht erneut klonen, sondern im
bestehenden Verzeichnis mit dem Abschnitt „Aktualisieren“ fortfahren.

## 3. Virtuelle Umgebung anlegen

Eine virtuelle Umgebung verhindert Konflikte mit den vom System verwalteten
Python-Paketen:

```sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Nach einem Neustart oder in einem neuen Terminal muss die Umgebung erneut
aktiviert werden:

```sh
cd uconsole_asw_game
. .venv/bin/activate
```

## 4. Starten

Normaler Start im Vollbild:

```sh
python main.py
```

Start im Fenster, etwa zur Fehlerdiagnose:

```sh
python main.py --windowed
```

Reproduzierbarer Start mit numerischem Seed:

```sh
python main.py 12345 --windowed
```

Start ohne Audio beziehungsweise Versionsprüfung:

```sh
python main.py --no-audio
python main.py --version
```

Dies sind die aktuell unterstützten Startparameter. Im Startmenü wählst du das
Szenario mit Pfeiltasten oder Ziffern und bestätigst mit `Enter` oder Leertaste.
`W` wählt einen der 128 seedbestimmten realen 500-NM-Sektoren oder die feste
Legacy-Referenzkarte; `R` erzeugt einen neuen Seed. Derselbe Seed und Weltmodus
erzeugen reproduzierbar dieselbe Welt. Die realen Namen und Küsten sind kein
Navigationsprodukt; Tiefen sind synthetisch, und militärische Gameplay-Rollen
sind fiktionale Übungsrollen.
`F` schaltet dort den Vollbildmodus um. Im Spiel öffnet `F1` die
kontextabhängige Hilfe; `Alt+Enter` wechselt jederzeit zwischen Vollbild und
Fenster.

Die Arbeitsoberfläche rendert nativ auf einem 1280 x 720 Pixel großen Canvas.
Sie wird im Vollbild auf die verfügbare Displayfläche skaliert; im Fenstermodus
ist 1280 x 720 die native Größe.

## 5. Optional als Paket installieren

Für einen systemunabhängigen Kommandoeinstieg innerhalb der virtuellen Umgebung:

```sh
python -m pip install -e .
u-jagd --windowed
```

Der direkte Start mit `python main.py` bleibt für einen Git-Checkout der
einfachste Weg. Kontakt- und Küstendaten sind in der Paketkonfiguration enthalten.

Im Spiel öffnet `Esc` den Beenden-Dialog beziehungsweise schließt die laufende
Eingabe oder Verwaltungsansicht. `Q`/`E` zoomen ausschließlich auf Brücke,
Waffen- und Helikopterstation. Die Hinweise im Ereignis-Feed sind auf die aktive
Station begrenzt; die vollständige kontextabhängige Belegung steht unter `F1`.

## 6. Aktualisieren

Vor dem Update das Spiel beenden. Im Repository und mit aktivierter virtueller
Umgebung:

```sh
git pull --ff-only
. .venv/bin/activate
python -m pip install -r requirements.txt
```

Bei einer editierbaren Paketinstallation zusätzlich ausführen:

```sh
python -m pip install -e .
```

Lokale Speicherstände unter `~/.u-jagd/` werden durch `git pull` nicht
verändert. Eigene Änderungen im Repository können ein Fast-Forward-Update
blockieren; in diesem Fall zuerst mit `git status` prüfen und die Änderungen
bewusst sichern oder committen.

## 7. Deinstallation

Bei ausschließlichem Start aus dem Checkout genügt es, das Repository und seine
virtuelle Umgebung zu entfernen. Eine Paketinstallation wird in der aktivierten
Umgebung so entfernt:

```sh
python -m pip uninstall u-jagd
```

Speicherstände bleiben unter `~/.u-jagd/` erhalten und müssen bei Bedarf separat
gelöscht werden.

## Fehlerbehebung

### `externally-managed-environment`

Die Installation wurde außerhalb der virtuellen Umgebung versucht. Keine
Systemprüfung mit `--break-system-packages` umgehen, sondern:

```sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.txt
```

### Pygame lässt sich nicht installieren

Zuerst `pip` in der virtuellen Umgebung aktualisieren. Falls für die verwendete
ARM-/Python-Kombination kein passendes Wheel angeboten wird und Pygame lokal
gebaut werden muss, die üblichen Build- und SDL2-Header installieren:

```sh
sudo apt install build-essential python3-dev pkg-config \
  libsdl2-dev libsdl2-image-dev libsdl2-mixer-dev libsdl2-ttf-dev
python -m pip install -r requirements.txt
```

### Schwarzes Fenster oder `No available video device`

- Das Spiel aus einer laufenden grafischen Desktop-Sitzung starten, nicht aus
  einer reinen SSH-Sitzung.
- Zuerst `python main.py --windowed` testen.
- Prüfen, ob `DISPLAY` gesetzt ist: `printenv DISPLAY`.
- Nicht dauerhaft `SDL_VIDEODRIVER=dummy` setzen; der Dummy-Treiber ist nur für
  automatisierte, nicht sichtbare Tests geeignet.

### Kein Ton oder ALSA-Warnungen

Ausgabegerät und Lautstärke im Desktop beziehungsweise mit `alsamixer` prüfen.
Pygame kann ein bestimmtes ALSA-Gerät über die Umgebungsvariable
`AUDIODEV` verwenden. Das Spiel fängt Fehler beim Öffnen des Audiogeräts ab und
läuft dann absichtlich stumm weiter; fehlender Ton verhindert den Start nicht.

### Schlechte Leistung oder hohe CPU-Last

- Andere grafik- oder CPU-intensive Programme schließen.
- Fenstermodus testen und das Fenster nicht unnötig groß skalieren.
- Sicherstellen, dass keine Debug- oder Remote-Desktop-Sitzung Software-Rendering
  erzwingt.
- Mit `python -m pip show pygame numpy` prüfen, ob beide Pakete in der aktiven
  virtuellen Umgebung installiert sind.

### Kontakt-DB wird nicht geladen

Beim Start kann die Meldung `[kontakt-db] ... verwende eingebauten
Default-Katalog` erscheinen. Im Git-Checkout prüfen:

```sh
test -f data/contacts/subs.json
test -f data/coastlines/region.json
test -f data/coastlines/real_sectors.json.gz
```

Fehlende oder lokal veränderte Dateien mit `git status` untersuchen. Die
Kontakt-DB besitzt einen eingebauten Fallback. Die feste Legacy-Karte kann bei
fehlender Datei leer sein; ein fehlender oder beschädigter Katalog der realen
Sektoren verhindert dagegen den Start dieses Weltmodus. Bei einer
Paketinstallation das Paket erneut aus dem aktuellen Checkout installieren.

### Speichern oder Laden schlägt fehl

Speicherstände liegen in `~/.u-jagd/`. Rechte und freien Platz prüfen:

```sh
ls -ld "$HOME" "$HOME/.u-jagd"
df -h "$HOME"
```

Das Spiel nie mit `sudo` starten, da sonst root-eigene Speicherdateien entstehen
können. Falls das bereits passiert ist, Eigentümer des Verzeichnisses gezielt
korrigieren.

### Diagnoseinformationen erfassen

Für einen Fehlerbericht sind mindestens diese Angaben hilfreich:

```sh
python3 --version
python -m pip show pygame numpy
uname -a
git rev-parse --short HEAD
```

Dazu den genauen Startbefehl, die vollständige Terminalausgabe und die Angabe,
ob Vollbild, Fenstermodus, Bild oder Audio betroffen sind, notieren.
