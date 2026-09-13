[English README](README.md)

# U-Jagd

U-Jagd ist ein Echtzeit-Taktikspiel zur U-Boot-Jagd für Linux, das für die
Arbeitsfläche von 1280 x 720 Pixeln der ClockworkPi uConsole entwickelt wurde.
Sie führen eine fiktive Fregatte und wechseln zwischen neun Arbeitsplätzen, um
zu navigieren, zu suchen, Kontakte zu klassifizieren, Ziele zu bekämpfen und das
Schiff einsatzfähig zu halten.

Aktuelle Version: **0.2.0**

Dies ist eine frühe spielbare Version. Sie ist ein Spiel und kein Ausbildungs-
oder Navigationsprodukt. Die Systeme sind vereinfacht und erheben nicht den
Anspruch, geheime Fähigkeiten, Daten oder Einsatzgrundsätze nachzubilden.

## Screenshots

![U-Jagd-Hauptmenü](docs/screenshots/main-menu.png)

![Brücke, Sonar, Waffen und Schadensabwehr](docs/screenshots/stations-overview-1.png)

![OPZ/CIC, Funk, Maschinenraum und Helikopter](docs/screenshots/stations-overview-2.png)

![Elektronische Kampfführung / ESM](docs/screenshots/stations-overview-3.png)

Arbeitsplätze in voller Auflösung: [Brücke](docs/screenshots/station-bridge.png),
[Sonar](docs/screenshots/station-sonar.png),
[Waffen](docs/screenshots/station-weapons.png),
[Schadensabwehr](docs/screenshots/station-damage-control.png),
[OPZ/CIC](docs/screenshots/station-opz-cic.png),
[Funk](docs/screenshots/station-radio.png),
[Maschinenraum](docs/screenshots/station-engineering.png),
[Helikopter](docs/screenshots/station-helicopter.png) und
[Elektronische Kampfführung/ESM](docs/screenshots/station-eloka.png).

Beispiel der Schadensabwehr mit vorgegebenen Flutungen, Bränden, ausgefallenen
Zonen und Reparaturtrupps:
[F-217-Schadensschema](docs/screenshots/damage-control-alert.png).

Commander-Browser: [OPZ/CIC mit 1920 x 1080](docs/screenshots/commander-v2-de-opz-desktop.png),
[Sonar mit 1920 x 1080](docs/screenshots/commander-v2-de-sonar-desktop.png) und die
[vollständige deutsche/englische Desktop- und Mobilmatrix](docs/screenshots/commander-captures.de.md).
[Lokale Commander-Optionen](docs/screenshots/commander-options.png).

## Highlights

- Neun Stationen: Brücke, Sonar, Waffen, Schadensabwehr, OPZ/CIC, Funk,
  Maschinenraum, Helikopterdeck und Elektronische Kampfführung/ESM.
- Vier integrierte Szenarien, drei Schwierigkeitsgrade, Pause sowie 1x-, 5x-,
  15x-, 30x-, 60x- und 120x-Zeitraffer.
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

## Voraussetzungen

- Linux
- Python 3.11 oder neuer
- Pygame 2.6 oder neuer
- NumPy 2.0 oder neuer
- Eine von Pygame unterstützte Anzeige
- Ein Audiogerät ist optional; ist kein Audiogerät verfügbar, wird der Start
  lautlos fortgesetzt

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

Systempakete, Aktualisierungen und Fehlerbehebung für die ClockworkPi uConsole
sind in [`docs/install-uconsole.md`](docs/install-uconsole.md) beschrieben.

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

## Spiel starten

Das Hauptmenü enthält Einträge für ein neues Spiel, Laden, Missionseditor,
Einheiteneditor, Optionen und Beenden. Bei einem neuen Spiel folgen die Auswahl
des Szenarios und, beim Zufallsszenario, die Auswahl des Schwierigkeitsgrads.

- `W` wechselt zwischen dem durch den Seed gewählten realen Sektor und der
  festen klassischen Referenzkarte.
- `R` erzeugt einen neuen Seed.
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

Drücken Sie im Spiel `F1`, um die vollständige kontextsensitive Hilfe
aufzurufen. Die wichtigsten globalen Bedienelemente sind:

| Eingabe | Aktion |
|---|---|
| `1` bis `9` | Brücke, Sonar, Waffen, Schadensabwehr, OPZ/CIC, Funk, Maschinenraum, Helikopter, Elektronische Kampfführung/ESM; erneutes Drücken der Nummer der aktiven Station wechselt, sofern vorhanden, zur nächsten Seite |
| `Tab` / `Shift+Tab` | Nächste / vorherige Station |
| `P` | Pause / fortsetzen |
| `F1` | Kontextsensitive Hilfe |
| `F10` | Optionen; während der Pause öffnet auch `O` die Optionen |
| `F9` | Lokale Commander-LAN-Verwaltung |
| `S` / `L` | Speichern / Laden über die Plätze 1 bis 5 |
| `Z` / `X` oder `[` / `]` | Zeitraffer verlangsamen / beschleunigen |
| `+` / `-` | Maschinentelegraf |
| `Alt+Enter` | Vollbildmodus umschalten |
| `Ctrl+Enter` | Primäre Waffenaktion an den Stationen Waffen, OPZ/CIC oder Helikopter; die normalen Bereitschaftsprüfungen gelten |
| `Q` / `E` oder Mausrad | Sichtbare Karten an den Stationen Brücke, Waffen und Helikopter zoomen |
| Ziehen mit der Maus | Eine sichtbare Karte verschieben und die Kameraverfolgung ausschalten |
| `K` | Kameraverfolgung auf einer sichtbaren Karte umschalten |
| `Esc` | Einen fixierten Hinweis entfernen, die aktuelle Ansicht/Eingabe abbrechen oder die Beenden-Bestätigung öffnen |

Stationstasten sind bewusst kontextabhängig. Beispielsweise sendet `A` am Sonar
einen aktiven Ping, ändert im Maschinenraum jedoch den Akustikmodus. Verwenden
Sie `F1`, statt davon auszugehen, dass eine Taste an jeder Station dieselbe
Bedeutung hat.

In der Hilfe wechselt Links/Rechts die Kategorie; Auf/Ab oder Page Up/Page Down
scrollt den Inhalt. Bestehende stationsbezogene Tastenkürzel für Waffen bleiben
verfügbar. Gedrückt gehaltene Kurs- und Torpedotiefensteuerungen verwenden
Echtzeit und nicht den gewählten Simulationsfaktor.

Klicken Sie bei der Schadensabwehr auf eine Zone oder deren Beschriftung, um sie
auszuwählen. Sind Kontexthinweise aktiviert, fixiert der Klick zugleich ihre
Details; ein Trupp wird dadurch nie zugewiesen. Auf/Ab wählt einen Trupp, Enter
weist ihn zu und Backspace zieht ihn ab. Flutungs- und Brandtrends zeigen die
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

Bei 1x verarbeitet die Sonar-Wiedergabe die begrenzte Blockübergabe des
Empfängers der Reihe nach und versucht einen nicht angenommenen Block erneut,
wenn die Wiedergabewarteschlange voll ist. Bei einem Überlauf startet der Stream
neu, statt unzusammenhängende Abtastwerte zu verbinden. Oberhalb von 1x ist die
Sonar-Wiedergabe stumm; Empfängerblöcke werden verworfen und nicht später
nachgespielt. Die Analyse bleibt unabhängig von Wiedergabeverfügbarkeit und
Lautstärke. Nach dem Laden eines Spielstands durchläuft DSP bewusst erneut seine
Anlaufphase; gespeicherte taktische Beobachtungen bleiben erhalten.

Die Sonarbedienung umfasst:

- `A`: Einen aktiven Ping senden; der Sender hat 30 Sekunden Abklingzeit.
- `B`: HMS oder TAS als Empfangs-/Sende-Array auswählen.
- `Y`: TAS ausbringen oder einholen.
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
Echos erzeugen, nachdem genügend Kabel ausgebracht wurde. Wird `A` bei nicht
verfügbarem TAS gedrückt, wird der Befehl abgelehnt, ohne zu senden oder die
gemeinsame Ping-Abklingzeit zu verbrauchen. Die aktive Reichweite von TAS ist
geringer als die von HMS; sein Hauptvorteil liegt in der Genauigkeit passiver
Peilungen und der Leistung gegen passend geschichtete Kontakte nach dem
Einschwingen.

## Radar-Hinweise

In der OPZ/CIC wählen `Page Up` und `Page Down` ausschließlich Anzeigebereiche
von **10, 20, 40, 80 oder 120 NM**; sie wechseln weder die Seite noch die
Sensorleistung. Die modellierten Erfassungsgrenzen bei klarem Wetter betragen
30 NM für das Seezielradar und 100 NM für das Luftraumradar, mit
Leistungseinbußen ab Seegang 5. Seeziel- und Luftraumradar können mit `R` und
`Shift+R` getrennt gesteuert werden.

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
v10 gespeichert.

## Commander-LAN-Koop

Verwenden Sie auf der uConsole **F10 > Commander LAN** oder **F9**. Wählen Sie bei
ausgeschaltetem Dienst ausdrücklich eine private IPv4-Adresse und aktivieren Sie
ihn anschließend. Öffnen Sie auf jedem Besatzungsgerät die angezeigte URL. Die
Voreinstellung `127.0.0.1:8765` gilt nur für das lokale Gerät und ist von anderen
Geräten nicht erreichbar. Eine Router-Portweiterleitung ist weder erforderlich
noch unterstützt.

Koppeln Sie den Browser mit dem sechsstelligen Code: **drei Ziffern gefolgt von
drei Großbuchstaben**, beispielsweise `482KMT`. Codes laufen nach fünf Minuten
ab; fünf falsche Versuche innerhalb einer gleitenden Minute sperren weitere
Versuche vorübergehend. Browser-Eingaben in Kleinbuchstaben werden in
Großbuchstaben umgewandelt. Das Beispiel ist kein gültiger Zugangscode.

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

Solange ein Browser eine Stations-Lease besitzt, ist die Bedienung der
entsprechenden Station auf der uConsole schreibgeschützt. Host-Verwaltung, Pause
und der Wechsel zu einer anderen Station bleiben verfügbar; der Widerruf der
Lease stellt die lokale Bedienung sofort wieder her.

Der Dienst startet **bei jedem Programmstart ausgeschaltet**. Zugriffe und
Freigaben werden nicht gespeichert. Zugangsdaten, Clients, Stations-Leases,
Netzwerkwarteschlangen, Entwürfe und nicht angenommene Befehle gelangen weder in
Spielstände noch in die Einstellungen. Ein Austausch der Welt widerruft aktive
Berechtigungen im nächsten Frame des Hauptthreads. Manuelle Pause, Fokusverlust,
Speichern/Laden, Beenden, Länderübersicht, die eigentlichen Editoren, Menüs und
Splashscreen sperren Änderungen aus dem Browser. Bei einer aktiven Crew-Station
lassen die F1-Hilfe, der spielinterne F8-Analysator, die Crew-Verwaltung mit F9
und die Optionen mit F10 Simulation und Browser-Stationen weiterlaufen.
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

Anwendungsversion **0.2.0**, API-Protokolle **v1** und **v2** sowie
Speicherformat **v10** sind voneinander unabhängige Kompatibilitätsverträge. Das
rollenorientierte Remote-Crew-System verwendet Protokoll v2; das ältere
Commander-Protokoll v1 bleibt für die Kompatibilität unverändert und wird nicht
stillschweigend um v2-Felder oder -Berechtigungen erweitert.

**Sicherheit:** HTTP ist unverschlüsselt. Verwenden Sie den Dienst nur in einem
vertrauenswürdigen LAN. Internet-Hosting, Bindung an Wildcard-Adressen, CDN,
ferne Steuerung von Einsatzregeln, Zeit oder Speicherständen sowie verborgene
Entity-Daten werden nicht bereitgestellt. Siehe
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

Validiert bedeutet nicht, dass ein Wert zur Laufzeit wirksam ist. In Version
0.2.0 gilt:

- Eine Benutzermission kann nur dann mit `F5` aus der Browseransicht des
  Missionseditors gestartet werden, wenn sie die unterstützte Laufzeitteilmenge
  verwendet.
- Wirksame Missionswerte sind Seed und Name; Platzierungssektoren einer festen
  500-NM-Welt; Position, Kurs und Fahrt des Spielerschiffs; Seegang, Startzeit
  und Thermoklinentiefe; exakte integrierte U-Boot- und Überwasserprofile mit
  ihrer Platzierung, ihrem Kurs, ihrer Fahrt und der Tiefe der U-Boote; sowie
  Ziele vom Typ `sink` oder `survive` mit einem Zeitlimit.
- Eine Laufzeitmission muss eine 500-NM-Welt vom Typ `fixed` und Wetter vom Typ
  `clear` festlegen. Andere Weltgrößen und Referenzwelten werden abgelehnt. Die
  Weltdefinition des Editors ersetzt nicht den Küstendatensatz des Spiels.
- Platzierte U-Boote müssen feindlich sein. Bei einem Ziel vom Typ `sink` muss
  dessen Zielliste exakt allen platzierten U-Booten entsprechen.
- Zufallsgruppen, zeitgesteuerte Ereignisse, Ziele vom Typ `protect` und `reach`,
  Luftfahrzeuge, Tiere, Torpedos, Täuschkörper und selbst erstellte
  Einheitenprofile werden für das Spielen der Mission abgelehnt und nicht
  stillschweigend ignoriert.
- Ausgaben des Einheiteneditors sind ausschließlich Validierungs- und
  Erstellungsdaten. Derzeit beeinflusst kein Feld eines Benutzer-Einheitenprofils
  die laufende Simulation.

## Spielstände und Benutzerdaten

Version 0.2.0 schreibt und lädt ausschließlich das Speicherformat **v10**. V10
verlangt das exakte Schema `u-jagd-save-v10` einschließlich des aktuellen
Schnappschusses des Laufzeitkatalogs und des gesamten Zustands für die
deterministische Fortsetzung. Ältere, neuere, fehlerhafte oder unvollständige
Spielstände werden abgelehnt, ohne das laufende Spiel zu ersetzen.

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
sind in [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md) dokumentiert. Privates
WaveOps/MNW-Material ist keine Quelle des Repositorys. Es werden daraus weder
Texte, Bilder, Layouts, Daten, Nachahmungen, Transkriptionen noch abgeleitete
Materialien verwendet.

## Entwicklung und Tests

Die Prüfung der Arbeitsplätze und Modelle, umgesetzte Korrekturen, verbleibende
Modellgrenzen und die Checkliste für die Hardware-Abnahme sind in
[`docs/workstation-review.md`](docs/workstation-review.md) dokumentiert.
Aktuelle Arbeiten werden in [`docs/plan-0.1.8.md`](docs/plan-0.1.8.md) und
[`docs/resume.md`](docs/resume.md) verfolgt. Der abgeschlossene
Stabilisierungsplan für 0.1.6 bleibt unter
[`docs/plan-0.1.6.md`](docs/plan-0.1.6.md) verfügbar.

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

## Lizenz und Danksagungen

Der Projektcode und die projektspezifische Dokumentation stehen unter der
MIT-Lizenz; siehe [`LICENSE`](LICENSE). Pygame, NumPy, geografische Quelldaten
und alle zukünftigen Assets behalten ihre jeweiligen Lizenzen und
Attributionsanforderungen. Siehe
[`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md) und
[`assets/README.md`](assets/README.md).
