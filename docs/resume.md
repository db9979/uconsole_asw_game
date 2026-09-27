# Wiederaufnahme

## Stand

Stand 2026-09-11 auf Branch `main`. Der vollstaendig softwareabgenommene
R9-R19-Kandidat ist Commit `e42a678`. Die vier letzten inhaltlichen
Projektcommits bis zu diesem Kandidaten sind:

- `e42a678` 0.1.7-Fidelity-Meilensteine R9-R19,
- `7d52faf` 0.1.7 Sensor- und ASW-Systeme,
- `1aae70d` begrenzter Sonar-Hold und Wall-Time-Audioauslieferung,
- `fb7a6ce` Audio-Pufferdiagnose.

Der Kandidat samt Hydroakustik-/Analyzer-Follow-up wurde nach ausdruecklicher
Freigabe vollstaendig committed. Der nachfolgende reine Dokumentationsschritt
aktualisiert diesen Handoff. Es ist kein Push oder Release-Upload erfolgt.
Vor einer Veroeffentlichung sind Status, Gesamtdiff, Dateiauswahl und sichere
lokale GitHub-Authentifizierung erneut zu pruefen.

## Aktuelle Arbeit

Der aktuelle Persistenzvertrag schreibt und laedt ausschliesslich Save v10 mit
dem exakten Tag `u-jagd-save-v10`. Katalogsnapshot v2,
`platform_state_version: 1`, ESM, ASW und alle acht RNG-Streams sind Pflicht.
V1-v9, zukuenftige Versionen, Snapshot v1, unbekannte oder unvollstaendige
Schemata und nichtfinite Werte werden vor dem Kandidaten-Restore transaktional
abgelehnt. Es gibt keine Saveformatmigration.

R0-Verifikation:

- Fokussierter Save-/Version-/Startup-/Runtime-/Packaging-Lauf: 442 bestanden.
- `main.py --version`: `0.1.7`.
- `git diff --check`: sauber.

R1 ist umgesetzt: Eine nicht pausierende Crew-MessageBox zeigt Ziel- und
Navigationsvorschlaege mit Zielvorrang. F6/F7 entscheiden lokal, F8 wechselt,
Esc unterdrueckt nur die aktuelle Sequenz. Nur diese Tasten und Klicks innerhalb
der Box werden konsumiert; andere Stationsbedienung laeuft weiter. Autoritaets-,
Lease-, Verbindungs- und Weltverlust schliessen die Box.

R2 ist umgesetzt: Die gekoppelte Webkonsole besitzt die vier ARIA-Tabs
Operations, Lookout, Guide und Contacts. Operations enthaelt unveraendert das
bisherige Lagebild; R2 lieferte fuer die drei spaeteren Ansichten lokalisierte
Platzhalter, von denen R6 inzwischen Lookout aktiviert hat.
Tabwechsel behalten Auswahl, Entwuerfe, Kartenansicht und Panel-Scrollpositionen
bei und senden keine Befehle. Shell und Dokument bleiben exakt im Viewport; nur
Tab- und Panelinhalte scrollen.

R0-R2-Verifikation:

- R1 Input-/Commander-Fokus: 80 bestanden.
- Save-/Runtime-/Commander-Regression: 297 bestanden.
- Commander-Assets und vollstaendige Chromium-Layoutmatrix: 38 bestanden.
- Vollstaendige Suite: 1817 bestanden in 421.37 Sekunden.
- `tools/gen_contacts.py --check`: 106 Akustikprofile gueltig.
- `tools/smoke_full.py`: `SMOKE-OK`.
- `git diff --check`: sauber.
- Commander-Bilder 1920x1080 und 2560x1440 fuer die feste Tab-Shell neu erzeugt.

R3 ist umgesetzt: Gemischte v1/v2-Profildokumente behalten unveraenderte
Legacy-Runtime-Eintraege und ergaenzen streng typisierte, unveraenderliche
Referenz-, Maschinen-, Sensor-, Emitter-, Waffen-, Launcher-, Magazin- und
Gegenmassnahmenregister. Querverweise, Namespaces, Zahlen, Emissionsvertrag,
Launcherkompatibilitaet, Dateigroesse, Eintragszahl und JSON-Tiefe sind begrenzt.
Die typbasierte Rekonstruktion erhaelt jedes v2-Feld und den JSON-Zahltyp.
`sources.json` verbindet Profil/Feldpfad mit `published`, `derived`,
`game_assumption` oder `unknown`, ohne Werte zu duplizieren oder URLs abzurufen.
Die damalige R3-Baseline war ehrlich leer; alle acht Profildateien blieben v1.

R3-Verifikation:

- Katalog-v1/v2-, Provenienz- und Packaging-Fokus: 164 bestanden.
- Vollstaendige Suite nach R3: 1862 bestanden in 442.36 Sekunden.
- `tools/gen_contacts.py --check`: 106 Akustikprofile gueltig.
- `tools/smoke_full.py`: `SMOKE-OK`.
- `git diff --check`: sauber.

R4 ist umgesetzt: Arleigh Burke Flight IIA, Ticonderoga Baseline 2, Type 055,
Virginia Block III, Yasen-M und der generische Panamax-Archetyp sind nach v2
migriert; Type 052D, Type 901 und Nimitz wurden als neue, nicht zufaellig
spawnende Keys angehaengt. Der Katalog enthaelt 115 Runtime- und 109
Akustikprofile. Der feindliche Legacy-Zufallspool bleibt exakt bei den bisherigen
25 Kriegsschiffen.

Alle Pilotfelder besitzen einen eindeutigen `published`-, `derived`-,
`game_assumption`- oder `unknown`-Claim. LOFAR-Zustaende sind relativ normalisiert.
18 Sensoren, 7 Emitter sowie je 8 grobe Waffen-, Launcher-, Magazin- und
Gegenmassnahmenobjekte sind validiert. Zum damaligen R4-Stand waren Maschinen,
Sensoren, Waffen, Launcher, Magazine und Gegenmassnahmen noch nicht
runtimewirksam. Type 901 hat keine Nachversorgungslogik, Nimitz keinen Carrier
Wing. Missionsbeladung und Launcher-/VLS-Kapazitaet bleiben getrennt.

R4-/Snapshot-Verifikation:

- Katalog-v1/v2, Provenienz, Runtimeparitaet und Validator: 166 bestanden.
- Save-Snapshot, historische Saves und Continuation: 215 bestanden.
- Vollstaendige Suite: 1878 bestanden in 505.26 Sekunden.
- `tools/gen_contacts.py --check`: 109 Akustikprofile gueltig.
- `tools/smoke_full.py`: `SMOKE-OK`.
- `git diff --check`: sauber.

R5 ist umgesetzt: Plattformprofile tragen keine Runtimehostilitaet mehr. Seite
und Doktrin werden je Instanz aus Built-in- oder Custom-Mission gesetzt und im
Save erhalten; dieselbe Klasse kann auf entgegengesetzten Seiten laufen. Das
historische JSON-Feld `hostile` bleibt ausschliesslich als validierte
Legacy-Spawnpool-Markierung erhalten. Nicht hostile Einheiten duerfen keine
eingehenden Legacywaffen erzeugen; Trefferfolgen, Score und Incident richten sich
nach der Instanzseite.

Die neun Piloten verwenden ihre v2-Maschinenwerte fuer Cruise-/Maximal-/Leisefahrt,
rumpfbezogene Manovriergrenzen und Cruise-/Hochfahrt-Akustik. Radar, ESM, Sonar
und AIS besitzen getrennte Controller mit fester seedbasierter Phase, eigenem
Scanindex und unabhaengigem EMCON. Lokale und Friendly-Datalink-Bilder sind auf je
64 observation-only Tracks begrenzt. Sensoren scannen alle physisch passenden
Domains; Radar sieht keine getauchten Ziele, Sonar keine Luftziele und U-Boot-ESM
erfordert Oberflaecheneinsatz. Bestehender Schaden deaktiviert oder degradiert
zugeordnete Sensoren. KI und Legacy-Waffenfreigabe erhalten nur frische eigene
oder Datalink-Beobachtungen, keine Entityreferenz.

Save v10 ist die einzige aeussere Version. `catalog_snapshot` v2 friert auch die
Komponenten ein. `platform_state_version: 1` speichert Seite, Doktrin,
Controllerphasen und beide begrenzten Bilder. Profilbezogene Maximalfahrt wird
bei Custom-Missionen und v10-Saves strikt erzwungen.

R5-Verifikation:

- Plattform-/Save-/Determinismus-/Beobachtungsfokus: 364 bestanden.
- Vollstaendige Suite: 1907 bestanden in 449.97 Sekunden.
- `tools/gen_contacts.py --check`: 109 Akustikprofile gueltig.
- `tools/smoke_full.py`: `SMOKE-OK`.
- `git diff --check`: sauber.
- Physische Audio-/LAN-/Thermalabnahme bleibt offen.

R6 ist umgesetzt: Lookout ist eine eigene nordorientierte, schiffszentrierte
Commander-Ansicht. Sie verwendet ausschliesslich den abgeloesten Zustandssnapshot,
nie Kartengeometrie oder Simulationsobjekte. Eigenes Schiff, Kursvektor und
Entfernungsringe werden zusammen mit Positionsbeobachtungen als Punkten und
reinen Peilungen als Randmarken dargestellt. Seeklasse und der verbindliche
Tag-/Nachtzustand kommen aus dem additiven Protocol-1-Feld `environment`; in
Menue, Editor und Splash bleiben beide Werte `null`.

Der Darstellungsbereich ist unabhaengig von der Operations-Karte und rein lokal;
Mausrad, Tasten und Schaltflaechen senden keine Anfrage. Eine navigierbare
Textalternative bildet die Canvas-Beobachtungen ab. Aktive Backing-Stores sind
auf acht Millionen Pixel begrenzt, der inaktive Canvas wird freigegeben. Die
kompakte Darstellung behaelt auf kurzen Landscape- und 400-Prozent-Reflow-
Ansichten zwei getrennte Ringe und erreichbare Bedienelemente. Redaktion und
direktes Trennen loeschen Umweltdaten, Beobachtungen, Textalternative und Canvas.

R6-Verifikation:

- Commander-/i18n-Fokus einschliesslich Browser und Layout: 510 bestanden.
- Chromium-Browservertrag: 6 bestanden, darunter 4 Hauptbreiten.
- Dichte EN/DE-Matrix: 20 bestanden; kurze Landscape-/400-Prozent-Matrix:
  6 bestanden.
- Vollstaendige Suite: 1917 bestanden in 480.64 Sekunden.
- `tools/gen_contacts.py --check`: 109 Akustikprofile gueltig.
- `tools/smoke_full.py`: `SMOKE-OK`.
- `git diff --check`: sauber; abschliessende unabhaengige Review ohne Befund.
- Physische Zwei-PC-LAN-, Browser- und uConsole-Abnahme bleibt offen.

R7 ist umgesetzt: `Station.ELOKA` ist als neunte kanonische Station am Enum-Ende
angehaengt und ueber Taste 9 sowie den Tab-Zyklus erreichbar. Die passive
Workstation zeigt ein eigenstaendiges, auf 64 Auffassungen begrenztes
`esm_picture` mit opaken monotonen Schluesseln, Peilung und Unsicherheit,
beobachteter Frequenz, PRF, Modulation, Qualitaet und Alter. Eigene Radar- und
ESM-Evidenz entstehen parallel; ESM bleibt bei abgeschaltetem Eigenradar aktiv.
OPZ-Zerstoerung deaktiviert Messung und Bedienung, ohne das Schadensmodell um ein
zehntes Abteil zu erweitern.

Messwertassoziation und Kandidatenranking verwenden ausschliesslich abgeloeste
Messwerte und stabile Katalog-Emitterkeys. Radar-/Sonarbezuege vergleichen Zeit,
Peilung und beobachtete Position; Entity-ID, Objektbezug und wahrer Emitterkey
werden weder im ESM-Bild gespeichert noch fuer die Korrelation gelesen. Manuelle
Radarart-Zuordnungen bleiben getrennte Bedienerannotation. Das gemeinsame
Korrelationslagebild ist auf 512 Tracks begrenzt; Commander bleibt unveraendert
bei seiner eigenen 256er Projektion.

Save v10 enthaelt zwingend einen intern versionierten `esm`-Block fuer
Bild-Hochwasserstand, Auffassungen, Auswahl und Annotationen sowie die
ESM-Schedulerphase. Malformed ESM-, korrelationsrelevante Lagebild-,
Emitterzustands- und Fluganzahldaten werden vor dem Kandidaten-Commit abgelehnt;
die Station bleibt als symbolischer Wert `"ELOKA"` statt als Index erhalten.

R7-Verifikation:

- Fokussierte Sensor-/Save-/Commander-/UI-Matrix: 785 bestanden.
- Vollstaendige Suite: 1945 bestanden in 529.51 Sekunden.
- `tools/gen_contacts.py --check`: 109 Akustikprofile gueltig.
- `tools/smoke_full.py`: `SMOKE-OK` einschliesslich aller neun Stationen.
- Sdist und Wheel 0.1.7 erfolgreich gebaut; `src/sensors/esm.py` ist paketiert.
- `git diff --check`: sauber; drei unabhaengige Reviewrunden abschliessend ohne
  verbleibenden Befund.
- EN/DE-, Pseudolocale-, Large-Text-, Tooltip- und 1280x720-Layoutabnahme sind in
  der Suite enthalten; neue ELOKA-Einzel- und Uebersichtsabbildungen erzeugt.
- Physische uConsole-Audio-/Performance- und Zwei-PC-LAN-Abnahme bleibt offen.

R8 ist implementiert: typisierte ASW-Magazine und Rohre, Reload, endliche
Fregatten-/Hubschrauber-/U-Boot-Bestaende, ASROC, Nixie und reaktive
U-Boot-Dekoys verwenden Katalogprofile und einen eigenen gespeicherten
`rng_asw`. Laufende Waffen tragen Startursprung und Plattform-/Waffenprovenienz;
Datumfuehrung und terminale Sucher setzen ohne versteckte Zielposition fort.

Der Savevertrag wurde anschliessend bewusst auf v10-only umgestellt. Writer und
Loader verwenden die zentralen Konstanten `SAVE_VERSION = 10` und
`SAVE_SCHEMA = "u-jagd-save-v10"`. Das Wurzelschema ist exakt, alle acht
RNG-Streams sind Pflicht, und ein Kandidat muss sich nach dem Restore wieder
kanonisch zum Eingabedokument serialisieren. Dadurch werden auch fehlende oder
unbekannte verschachtelte Felder abgelehnt. Die v1-v8-Fixtures und alle
Migrationsabnahmen wurden entfernt; v1-v9 werden nur noch als Ablehnungsfaelle
geprueft. Sonar-ID-Hochwasser, ASW-Storeverbrauch, Plattform-/Waffenprovenienz,
Helikopterabschuesse und OPZ-Affiliationen werden strikt und transaktional
validiert. Ein abgelaufener Ping-Animationtimer wird auf null geklemmt, sodass
auch nach langen Simulationslaeufen jeder vom Writer erzeugte Save kanonisch
wieder ladbar bleibt.

R8-/v10-Verifikation:

- Vollstaendige Suite: 1927 bestanden in 528.76 Sekunden.
- `tools/gen_contacts.py --check`: 109 Akustikprofile gueltig.
- `tools/smoke_full.py`: `SMOKE-OK`, einschliesslich v10-Slot-Roundtrip.
- Sdist und Wheel 0.1.7 erfolgreich gebaut.
- `git diff --check`: sauber.
- Physische uConsole-Audio-/Performance- und Zwei-PC-LAN-Abnahme bleibt offen.

R9 ist implementiert: Die Luftabwehr verwendet profilierte ASM, SAM/ESSM, VLS,
CIWS und Chaff. VLS-Kapazitaet, Missionsbeladung und zwei Feuerkanaele sind
getrennt; Magazine, CIWS-Munition und Softkill sind endlich. SAM, Chaff und CIWS
benoetigen eine frische Positionsbeobachtung. Eigenradar hat bei gleichem
Messzeitpunkt Vorrang vor Datalink; nur der eigene `blue`-Verbund liefert
Feuerleitdaten. Datalinkwahrheit bleibt auf der Sensorerzeugungsgrenze, danach
arbeiten Waffen ausschliesslich mit abgeloesten, gespeicherten Tracks.

Der aktuelle v10-Writer speichert den intern versionierten Luftabwehrblock und
profilierte laufende Flugkoerper strikt. Ausschliesslich beim Laden einer Datei
wird das exakt erkennbare R8-v10-Layout ohne diesen Block eng auf den heutigen
Zustand angehoben; direkte aktuelle Dokumente mit fehlendem Feld bleiben
ungueltig. Andere Versionen und allgemeine Saveformatmigration bleiben verboten.

R9-Verifikation:

- Fokussierte Luftabwehr-/Save-/Continuation-Abnahme: 200 bestanden.
- Vollstaendige Suite: 1953 bestanden in 464.25 Sekunden.
- `tools/gen_contacts.py --check`: 109 Akustikprofile gueltig.
- `tools/smoke_full.py`: `SMOKE-OK`.
- Sdist und Wheel 0.1.7 erfolgreich gebaut; Luftabwehrdaten und -modul paketiert.
- `git diff --check`: sauber; abschliessende unabhaengige Review ohne
  funktionalen Befund.
- Restrisiko: Der R8-v10-Kompatibilitaetstest erzeugt die exakte alte Struktur
  programmgesteuert statt aus einer grossen eingefrorenen Fixturedatei.

R10 ist implementiert: Alle 115 Kontaktprofile in den acht Ressourcen sind auf
das v2-Komponentenmodell migriert. Profilkeys, Reihenfolge, Spawnpools und
Legacyadapter bleiben erhalten. Referenz-, Maschinen-, Sensor-, Emitter-,
Waffen-, Launcher-, Magazin- und Gegenmassnahmenfelder besitzen vollstaendige,
feldgenaue Claims mit `published`, `derived`, `game_assumption` oder `unknown`.
Der gemeinsame Loader erzwingt diese Abdeckung; nur der bereits validierte,
provenienzfreie Runtime-Snapshot im v10-Save darf sie gezielt auslassen.

U-Boot-Gegenmassnahmen verwenden nun die katalogisierten endlichen Stores. Das
ist der einzige bewusst dokumentierte Gameplayunterschied der Migration und
verwendet weiterhin den gespeicherten ASW-RNG-Stream. Tiere, Torpedos, Decoys
und reine Akustiksignaturen koennen keine unzulaessigen operativen Komponenten
tragen. Save-Snapshots bleiben runtime-only und enthalten keine Quellenprosa
oder URLs.

R10-Verifikation:

- Fokussierte Katalog-/Runtime-/Save-/Determinismusmatrix: 288 bestanden.
- Vollstaendige Suite: 2083 bestanden in 530.86 Sekunden.
- `tools/gen_contacts.py --check`: 109 Akustikprofile gueltig.
- `tools/smoke_full.py`: `SMOKE-OK`.
- Sdist und Wheel 0.1.7 erfolgreich gebaut; alle acht v2-Ressourcen und
  `sources.json` sind paketiert.
- `git diff --check`: sauber; unabhaengiger Reviewbefund zur leeren
  Provenienzausnahme behoben und mit Regressionstest abgesichert.
- Physische uConsole- und Zwei-Geraete-LAN-Abnahme bleibt offen.

R11 ist implementiert: `src/data/contact_analysis.py` liefert eine reine,
begrenzte und von Liveentitaeten getrennte Projektion aller 115 Katalogprofile.
Der fontfreie Generator erzeugt reproduzierbar 232 PNGs: sechs generische
dimensionsbasierte Silhouetten sowie Cruise-/High-Akustikbilder nur fuer die 113
Profile mit entsprechenden Maschinendaten. Manifest, Hashes, Dimensionen,
Dateimengen und Gesamtgroesse werden strikt validiert; Symlinks und andere
nicht-regulaere Ausgabeeintraege werden abgelehnt.

Commander erhaelt beim lokalen Start 233 vorgebaute, exakt allowlistete Routen
ohne requestbasierte Pfadinterpretation. Das Contacts-Panel validiert das
verschachtelte Schema, verwendet ausschliesslich `textContent`, scrollt intern
und bleibt von operativer Trackauswahl sowie allen Befehlen unabhaengig. Der
lokale Tactical Unit Analyzer verwendet dieselbe Projektion im bestehenden
administrativen `editor`-Owner, blockiert die Simulation und haelt maximal vier
dekodierte Bildsurfaces.

R11-Verifikation:

- Fokussierte R11-/Commander-/Layoutmatrix: 341 bestanden; zusaetzlich alle 38
  EN/DE-, Zoom- und Viewport-Layoutfaelle bestanden.
- Vollstaendige Suite: 2109 bestanden in 690.89 Sekunden.
- Beide Generatorchecks erfolgreich: 109 Akustikprofile und 232 PNG-Assets.
- `tools/smoke_full.py`: `SMOKE-OK`.
- Sdist und Wheel 0.1.7 erfolgreich gebaut; Manifest und exakte PNG-Menge sind
  paketiert und durch isolierte Installationstests abgedeckt.
- `git diff --check`: sauber; Reviewbefunde zu Symlinks, Browserschema und
  wiederholter Bilddekodierung behoben.
- Physische uConsole-Lesbarkeit/Performance und Zwei-Geraete-LAN bleiben offen.

Die spaetere Hydroakustik-DSP-Arbeit ersetzt den damaligen R11-Bildvertrag,
ohne die obige historische Verifikationsnotiz umzuschreiben: Silhouetten und
ihre sechs Routen entfallen vollstaendig. Der Generator liefert nun exakt 226
fontfreie 320x180-Kompositdiagramme (113 Cruise und 113 High) mit fester
logarithmischer Frequenzachse, getrennten Tonal-/Breitbandbelegen und einem nur
aus Wellen-RPM sowie optionaler Blattzahl abgeleiteten DEMON-Hypothesenstreifen.

`src/audio/hydroacoustics.py` stellt dazu eine streng begrenzte, typisierte und
rein synthetische NumPy-DSP-Bibliothek bereit: blockkontinuierliche Quelle mit
lokalem RNG, geglaetteter Distanz-/Thermoklinenkanal, LOFAR-STFT und PCM-only
DEMON. Die Liveintegration behaelt den bestehenden Receiver und faerbt dessen
Ton- und Breitbandanteile nur mit einer bei 100 Hz auf 1 normierten relativen
R17-Kurve; Detektion, Saves, Mixerwarteschlangen und Simulation bleiben davon
getrennt. Das Demowerkzeug liegt ausschliesslich unter `tools/`.

Analyzer-Review-Follow-up: Die 226 Bilder verwenden nun den festen Bereich
5 Hz-10 kHz, damit auch 6, 8, 8,5 und 9,75 Hz getrennte logarithmische Spalten
belegen. Diskrete Katalogtonlinien bleiben begrenzte, ueberlappend
max-komponierte Spitzen ohne erfundene Verbindung; Breitband bleibt ein
Plateau ueber genau dem gelieferten Intervall. Der 0-80-Hz-Streifen ist als
synthetische profilweite Wellen-/optionale BPF-Hypothese gekennzeichnet und wird
nur im Cruise-Referenzbild belegt. Lokale und Commander-EN/DE-Legenden stellen
ausdruecklich klar, dass dies keine Aufnahme oder Messung ist und fehlende Daten
nicht abgeleitet werden. Der historische R11-Verifikationsblock oben bleibt
unveraendert; die aktive R11-Silhouettenanforderung im Plan ist superseded.

Analyzer-Bilder als Stationsschirme (ersetzt den Absatz davor): Die
Akustikbilder zeigen jetzt, wie die Spur an der Sonarstation aussieht. Der
Generator spielt die Katalogsignatur durch den echten `AcousticReceiver`
(stetiger Kontakt im Horchstrahl, eigenes Schiff gestoppt, Seegang 3) und
rendert oben den LOFAR-Wasserfall 0-300 Hz linear mit Live-Spektrum, unten den
DEMON-Wasserfall 0-50 Hz mit gemessener Modulationsspitze, beide ueber
`sonar_view.waterfall_pixels` (dieselbe Phosphor-Abbildung wie die Station).
Die Radarbilder zeigen je Katalog-Emitter HF-/PRF-Band und den
ELOKA-Signal-Fingerabdruck (`esm.signal_fingerprint`) je Katalogmodulation. Die
Katalog-Wellen-/BPF-Hypothesenstreifen entfallen. In die Bilder geschrieben
sind die gemessenen Werte: LOFAR-Spitzenfrequenzen, DEMON-Modulationsspitze,
HF/PRF je Fingerabdruck. Das Druck-PDF (`tools/gen_unit_reference_pdf.py`)
zeigt dieselben Schirme und Werte hell auf Weiss (dunkle Wasserfalltinte,
grosse Schrift); durch die Wasserfaelle waechst es auf rund 11,7 MB.

R12 ist implementiert: Die Commander-Webanleitung besitzt acht semantische
Abschnitte zu Kopplung und lokaler Freigabe, Operationen/Ausguck,
Beobachtungsalter und Bewertungen, Ziel-/Navigationsvorschlaegen und
Meldungsabgleich, ELOKA/EMCON, Kontaktanalysator, LAN-Sicherheit/Neuverbindung
und den verbotenen Fernaktionen. Alle 42 neuen Texte liegen mit exakter
EN/DE-Paritaet im Rootkatalog und werden nur ueber `textContent` beziehungsweise
`data-i18n` eingesetzt. Die interne Navigation verschiebt und fokussiert nur das
Guide-Panel, nie das Dokument.

Die Inhaltsreview korrigierte zwei Uebertreibungen: Browser-Trennen vergisst nur
das lokale Credential und ersetzt keinen sofortigen F9-Widerruf; Commander
veroeffentlicht aktuell kein eigenes ELOKA-Verzeichnis. Die fokussierte gesamte
Commander-Matrix bestand mit 521 Tests, Guide/Layout/i18n nach Korrektur mit 64
Tests und die Vollsuite mit 2111 Tests in 640.94 Sekunden. Sdist und Wheel 0.1.7
wurden anschliessend erfolgreich gebaut.

R13-Softwarecheckpoint ist damit abgeschlossen: Vollsuite, beide
Generatorchecks, Smoke, Build, exakte Wheel-/sdist-Ressourcen, isolierte
Wheelinstallation, v10-Save-Abnahme, Browsermatrix und echte lokale
Loopbacktests sind gruen. Manifest und Paket enthalten nur selbst erzeugte,
fontfreie Analysebilder; der Quellen-/Lizenzscan ergab keine neue
Drittkomponente. Die physische uConsole-/Thermal-/Audio- und Zwei-Geraete-
LAN-Abnahme bleibt ausdruecklich offen; R13 ist gemaess Plan kein Pausenpunkt.

R14 ist implementiert: Sonar besitzt die sichtbaren Hoermodi Breitband,
gefiltert und Heterodyn sowie einen strukturierten Dauerstatus fuer globale und
lokale Freigabe, Geraeteverfuegbarkeit, Gain, Band, Notch, Kopfhoererlautstaerke
und Stummschaltung oberhalb 1x. A/B-, Gain-, Band- und Notchwechsel verwenden
einen kurzen blockkontinuierlichen Uebergang auf dem vollstaendigen Beam-Mix;
Analyse, Simulation und RNG bleiben von Wiedergabe und Lautstaerke getrennt.

PING-, TMA- und SONOBUOY-Fixe koexistieren je Kontakt mit getrenntem Mess- und
Publikationszeitpunkt, Unsicherheit und optionaler Tiefenunsicherheit. Alterung
erfolgt in Simulationszeit ohne Rendering. Bruecke und Commander verwenden
abgeloeste, begrenzte Fixprojektionen; Draw und Hit-Test teilen die sichtbare
Unsicherheitsgeometrie, und abgelaufene Marker sind nicht klickbar. Der strikte
v10-Save speichert Hoermodus und Fixe; nur die exakte vorherige R13-v10-Form wird
beim Dateiladen eng erkannt.

R14-Verifikation:

- Breite Audio-/Fix-/Save-/Commander-Matrix nach Reviewfixes: 635 bestanden.
- Karten-/Performance-Regressionen: 41 bestanden.
- Vollstaendige Suite: 2124 bestanden in 628.08 Sekunden.
- Beide Generatorchecks, `SMOKE-OK`, sdist/Wheel 0.1.7 und `git diff --check`
  erfolgreich.
- Reviewbefunde zu OLA-Anlaufabfall, TMA-`fixed_at` und Fix-Hitgeometrie behoben.
- Physischer 1x-Kopfhoerer-/Lautsprechertest bleibt offen.

R15 ist implementiert: Die sechs Sonarseiten bleiben getrennt und verwenden ein
862x386 grosses Hauptpanel sowie mindestens drei sichtbare Kontaktzeilen. LOFAR
ordnet Livespektrum, grossen Wasserfall, Beam-/Filterstatus, gemessene Tonlinien,
explizit per `K` gewaehlte Harmonikhypothesen und Kontakte getrennt an. DEMON
zeigt Evidenz, Blade-Rate, RPM-Hypothesen fuer angenommene Blattzahlen und
hoechstens drei Katalogkandidaten ohne Entity-/Fingerprintwahrheit.

Der lokalisierte zweizeilige Footer besitzt getrennte sichere Segmente fuer
Seite, Array, Gain, Band/Filter, Harmonik, Notch, Peak-Hold und Audio. Kontakt-,
Echo-, Tab- und Segmentgeometrien werden gemeinsam fuer Draw und Hit-Test
erzeugt; unsichtbare Raender und Zeilengaps reagieren nicht. 1280x800 wird
seitenrichtig letterboxed, Balkenraum abgelehnt und sicherheitskritische Aktionen
bleiben von beilaufigen Einzelklicks getrennt. Quellen-, Betriebs- und
Evidenzalter sind seitenspezifisch und dauerhaft innerhalb der Panels sichtbar.

R15-Verifikation:

- R15-Matrix: 72 bestanden; Review-Nachbesserungen fokussiert: 146 bestanden.
- Breite Sonar-/Input-/Layoutmatrix: 446 bestanden.
- Vollstaendige Suite: 2199 bestanden in 605.26 Sekunden.
- Beide Generatorchecks, `SMOKE-OK`, sdist/Wheel 0.1.7 und `git diff --check`
  erfolgreich.
- Reviewbefunde zu Detailclipping, Draw-/Hit-Raendern, Evidenzsemantik,
  automatischer Harmonik und harter deutscher DEMON-Achse behoben.
- Physischer 1280x720-Kontrast-/Trackballtest bleibt offen.

R16 ist umgesetzt: 12 relevante nichtnukleare U-Bootprofile besitzen einen
streng typisierten, ausdruecklich fiktiven `game_assumption`-Enduranceblock.
Die deterministische Komponente bilanziert Batterie, Hotel-/Propulsionslast,
Generator und optionale AIP-Reaktanten mit Reservehysterese. Diesel laedt erst
ab der tatsaechlich erreichten Schnorchel-Toleranzgrenze; `SNORKEL`, `RADIO` und
`DESCENDING` sind getrennte Phasen. Nach dem Abtauchen wird Restzeit wieder an
die jeweilige PATROLLE-/EVADE-/LAUER-Logik uebergeben.

Save v10 bleibt das einzige aeussere Format. Endurancezustand und erweiterter
Katalogsnapshot sind kanonisch Pflicht. Nur die exakt typgleiche kanonische
prae-R16-v10-Dateiform wird eng angehoben; bool/int/float-Nahformen, unbekannte
Felder und unvollstaendige Zustaende werden transaktional abgelehnt. Der alte
`SNOCKEL`-Countdown wird ohne zusaetzlichen Patrouillen-RNG-Draw fortgesetzt.

R16-Verifikation:

- Abschliessende R16-/Save-/Katalog-/Determinismusmatrix: 326 bestanden.
- Vollstaendige Suite: 2260 bestanden in 712.16 Sekunden.
- `tools/gen_contacts.py --check`: 109 Akustikprofile gueltig.
- `tools/smoke_full.py`: `SMOKE-OK`.
- sdist und Wheel 0.1.7 erfolgreich gebaut; `git diff --check` sauber.
- Unabhaengige Nachpruefung der Schwellen-, Restzeit- und 1024er-Grenzfaelle
  ohne verbleibenden Befund.
- Physischer Endurance-Langlauf auf der uConsole bleibt bis R19 offen.

R17 ist umgesetzt: `src/sonar/propagation.py` liefert ein reines, unveraenderliches
synthetisches Schallgeschwindigkeitsprofil und hoechstens vier stabile
Direkt-/Refraktions-/Oberflaechen-/Bodenpfade mit maximal drei Segmenten. Vier
kanonische Frequenzbaender, 500 NM Reichweite, frequenzabhaengige Daempfung,
profilbasierte Laufzeit, Terrainfreiheit, CZ-Fokussierung und begrenzter Nachhall
sind deterministisch und ohne RNG, Wall-Time oder Renderzustand berechnet.

BT-Messung und passive Eigen-/Plattformsensoren verwenden dasselbe Wahrprofil;
Messrauschen und RNG-Reihenfolge des BT bleiben erhalten. Passive Propagation
laeuft nur auf den bestehenden Sensorkadenzen. Aktive Ping-Snapshots,
`World.echo_delay_s()`, Torpedosucher/-kollision, physische Terrainabfragen und
die Anzahl aktiver Echos wurden nicht geaendert. Der abgeleitete Solver besitzt
keinen gespeicherten Cachezustand.

R17-Verifikation:

- Abschliessende Propagation-/Save-/Sonar-/Plattformmatrix: 425 bestanden.
- ASW-/Propagation-/Plattformregression nach Vollsuitebefund: 203 bestanden.
- Vollstaendige Suite: 2293 bestanden in 624.76 Sekunden.
- `tools/gen_contacts.py --check`: 109 Akustikprofile gueltig.
- `tools/smoke_full.py`: `SMOKE-OK`.
- sdist und Wheel 0.1.7 erfolgreich gebaut; `git diff --check` sauber.
- Reviewschaerfungen fuer CZ-Konsistenz, Nullreichweite, flache/kollineare Pfade,
  BT-Saves und reduzierte Welt-Stubs sind regressionsgeprueft.
- Physische uConsole-Sensorkadenz-/Kostenmessung bleibt bis R19 offen.

R18 ist umgesetzt: Nur neu erzeugte Welten erhalten deterministische kontrollierte
synthetische Untiefen im bestehenden Bathymetriesnapshot und hullsichere Starts.
Geladene alte Snapshots werden weder regeneriert noch nachgeruestet und sind in
beide Richtungen von aufruferseitigen Mutationen abgeloest. Die fiktive kanonische
Hullannahme umfasst Masse, Laenge, Breite, Tiefgang und Kielreserve.

`src/world/grounding.py` trennt physische Hull-Sweeps strikt von
`sonar_path_blocked()` und R17-Propagation. Translation und Drehung pruefen
konservativ begrenzt die ueberstrichene Hullflaeche gegen Land, Weltrand und das
bilineare Tiefenminimum. Der erste sichere Punkt, Kontaktart/-lage/-normale,
Latch und letzte sichere Pose werden gespeichert. ASTERN ist ein separater
nichtnegativer Fahrtzustand unter STOP; Bergung bleibt ebenfalls gesweept.
Ein Eintritt in Kontakt erzeugt genau einen deterministischen energie- und
lageabhaengigen Schaden auf den vorhandenen neun Abteilen ohne RNG-Zugriff.

R18-Verifikation:

- Abschliessende R18-Blockermatrix: 459 bestanden; finale Grounding-/Save-/
  Determinismusmatrix nach Normalenhaertung: 259 bestanden.
- Integrierte Vollsuite mit R18 und Hydroakustik-Follow-up: 2321 bestanden in
  675.87 Sekunden; die anschliessende Normalenhaertung ist fokussiert gruen.
- `tools/gen_contacts.py --check`: 109 Akustikprofile gueltig; `SMOKE-OK`.
- Reviews zu malformed Bathymetrie, duennem Land, Hull-Innentiefen,
  kanonischer Hull, drehendem Sweep, Snapshot-Ablosung und physischer
  Kontaktkonsistenz sind regressionsgeprueft.
- Physische uConsole-Groundingkosten, Trackball-ASTERN und Lesbarkeit bleiben
  fuer R19 offen.

R19-Softwareabnahme und verpflichtender Pausenpunkt sind erreicht. Nach
ausdruecklicher Git-Freigabe wurde der vollstaendige Kandidat einschliesslich
Runtime, Tests und 226 Analyzerdateien als `e42a678` committed. Der Arbeitsbaum
war unmittelbar danach sauber; es wurde nicht gepusht.

R19-Verifikation:

- Vollstaendige Suite: 2363 bestanden in 1107.32 Sekunden.
- Save-v10-/Versions-/Transaktions-/Continuationmatrix: 299 bestanden.
- Echte Loopback- und Chromium-Commander-Matrix: 506 bestanden, keine Skips.
- Neun Stationen, 1280x800-Letterbox, EN/DE, Grossschrift und Pseudolocale:
  384 bestanden.
- Audio-/Hydroakustik-/Bounded-Processing: 331 bestanden; R9/R16-R18 und
  explizite Performancegrenzen: 202 bestanden.
- Katalog-/Provenienz-/Asset-/Packaging-/Sicherheitsmatrix: 347 bestanden.
- `tools/gen_contacts.py --check`: 109 Akustikprofile gueltig.
- `tools/gen_contact_analysis_images.py --check`: 226 PNGs, keine Silhouetten.
- `tools/smoke_full.py`: `SMOKE-OK`; sdist/Wheel 0.1.7 erfolgreich gebaut und
  in getrennten Umgebungen mit Ressourcen-/Versionspruefung installiert.
- Keine privaten PDFs, Silhouetten, externen Audio-/Font-/Drittbilder,
  Zugangsdaten, lokalen Saves oder Debuglogs im Artefakt gefunden.
- `git diff --check` sauber. Dedizierte CVE-/SAST-Werkzeuge wie `pip-audit`,
  Bandit oder Semgrep waren nicht installiert; Abhaengigkeits-, Credential-,
  DOM-Sink- und Commander-Sicherheitstests sind gruen.

Release-HOLD und offene physische Abnahme:

- 1280x720-uConsole: neun Stationen, Kontrast, Tastatur und Trackball.
- Zwei reale Geraete: LAN-Kopplung/API, private Bindung und Firewall.
- Kopfhoerer/Lautsprecher bei 1x: Klickfreiheit, Filter-/Gainwechsel und
  Hydroakustik-Dauerlauf.
- Endurance-Langlauf, Propagations-/Groundingkosten, Framezeit, Thermalverhalten
  und Throttling auf der Zielhardware.

Die vorangegangene 0.1.6-Stabilisierung ist umgesetzt, aber noch nicht durch die
Hardware abgenommen:

- blockkontinuierliche Breitband-/Kavitations-/Hoerfilter-OLA mit definiertem
  Erstzustand, Freigabetail und idempotentem Receiversequenz-Retry,
- 1x-Audio-Hold bei fehlendem neuen Block; Sonar oberhalb 1x stumm und ohne
  spaeteres Backlog,
- korrekter Pygame-Begriff `AUDIO_MIXER_BUFFER_SAMPLES` statt einer falschen
  Millisekundenannahme,
- Wall-Time-Diagnose mit sicherem, nur bei Opt-in erzeugtem Logpfad,
- Commander-Alarme ohne verborgene ASM-/TORP-Typableitung,
- `proposal_pending` statt Ueberschreiben wartender Vorschlaege,
- Ports 1024-65535, mit Port 0 nur fuer isolierte/ephemere Tests,
- responsiver 0.1.6-Browservertrag mit erlaubtem vertikalem Dokument-Scrollen,
  ohne Ueberlagerung oder horizontale Ueberbreite,
- aktualisierte Audio-, Commander- und Navigationsdokumentation.

Verifikation der 0.1.6-Softwarebasis:

- Kombinierter Audio-/Commander-/Browser-/i18n-/Packaging-Lauf: 705 bestanden.
- Review-Nachbesserungen fokussiert: 512 bestanden.
- Vollstaendige Suite: 1779 bestanden in 564.48 Sekunden.
- `tools/gen_contacts.py --check`: 106 Akustikprofile gueltig.
- `tools/smoke_full.py`: `SMOKE-OK`.
- sdist und Wheel 0.1.6 erfolgreich gebaut.
- Wheel ausserhalb des Quellbaums installiert; Version, paketierte
  Commander-Ressourcen und echte Loopback-Kopplung: `WHEEL-LOOPBACK-OK`.
- Commander-Bilder 1920x1080 und 2560x1440 neu erzeugt und visuell auf
  Ueberlagerung, Kartenmassstab und erreichbare Navigation geprueft.
- `git diff --check` ist sauber. Code-/Daten-/Testpatch auf Basis `1aae70d`:
  SHA-256 `4f52d9dea37b97a3208ec729f9edbe6492f6f213286c9c000020e51bb11d64aa`.

## Post-R19-Arbeit (2026-09-11, noch nicht committed)

R20 Luftangriff: Feindliche Angriffsflugzeuge greifen die Fregatte in
Wellen an. `src/air/raid.py` liefert `RaidPhase` (APPROACH/ATTACK/RETREAT)
und `Raider` (Wendegrenze, tangentiale Stand-off-Orbit am
Waffenbereichsrand, ASM-Salven im Cooldown-Takt, 180-Grad-Retreat,
Despawn bei Rausradius/Weltende). Wellen spawnen ausserhalb der
Luft-Radarreichweite (110-140 NM), begrenzt auf `RAID_MAX_CONCURRENT`,
gated durch den Missions-ASM-Druck; Custom Missions ohne ASM bleiben
raid-frei. Salven werden als bestehende ASM-Objekte abgelaesen
(`_drain_raider_asm`). Raider erscheinen im Air Picture als anonyme
FLG-Tracks (`R-{seq}`, hostile bleibt false). Der neue Loadout-Block
`aa_gun` (240 Schuss, 60 NM, 8 Schuss/Gruppe, 1.5 s Zyklus, 50 % Treffer
nach Evasion-Korrektur) feuert nur gegen frische FLG-Beobachtungen und
senkt `hp`; bei hp <= 0 ist der Raider abgeschossen. Loadout v2 faegt
`raider` und `aa_gun` hinzu; der Save-`air_defense`-Zustandsblock ist
v2 (AA-Munition/-Zyklus, Raider, `raider_seq`, `waves_spawned`) und
`rngs` traegt den neunten Stream `raid` (seed+40424). Das exakte
pra-R20-Layout wird eng durch `_upgrade_pre_r20_v10` angehoben (R9-
Rueckfuellung entsprechend). i18n: `runtime.raid.incoming`/`downed`,
OPZ-Kopfzeile zeigt FLAK-Munition; das Missionsziel kündigt Luftangriffe
an. 30 neue Tests in `tests/test_air_raid.py`.

SimLog: Options-Toggle (`Preferences.simlog`, default aus, Zeile 6 des
F10-Menüs, Commander-Zeile rückt auf 7) zeichnet ein session-only
begrenztes Protokoll auf (`SIMLOG_MAX_ENTRIES` = 256, monotoner seq):
alle Feed-Ereignisse (Rohtext, lokalisiert erst beim Publish) plus alle
`SIMLOG_INTERVAL_S` = 10 Simulationssekunden ein vollstaendiger,
rein lesender Zustandssnapshot (`Game._simlog_state_data()`: Schiffs-
Pose/Schaden/Stationen, Waffenbestaende, alle Einheiten mit
Position/Kurs/Zustand, alle Projektile, Flug-/Raid-Tracks, Welt).
Aufnahme laeuft nur im Simulationsfortschritt. Die Bridge publiziert
den gefingerabdruck-geprueften, bytebegrenzten und bei redacted Phasen
leeren JSON-Array ueber die neue authentifizierte Commander-Route
`/api/v1/simlog`. Die versteckte Read-only-Web-Ansicht `#simlog` rendert
Ereignisse und (neueste 25) Snapshots als JSON-Details und ist nicht aus
der UI verlinkt. 21 Tests in `tests/test_simlog.py`.

Weitere Batch-Arbeiten: Zivile Luftfahrt (role-basierte Airbase-Klassen,
geometrische Via-Routen 30 NM an der Fregatte vorbei, verkuerfter
Spawn-Cooldown, 10 Tests), ELOKA-Radarart zeigt Katalog-Plattformnamen
statt `emitter.*`-Platzhalter (4 Stellen, 3 Tests), Audio-Hoerprobe im
Kontakt-Analysator (Space/Button, deterministische 3-s-Synthese aus
Katalogprofil, 6 Tests), Sonar-Seiten-Hotkeys trennen Seitenwechsel
innerhalb einer Station vom Stationstausch und koerzen den
Audio-Stream nicht (1 Regressionstest), Space im Kontakt-Analysator
slaegt die zugehoerige TEXTINPUT-Verarbeitung, sobald die Hoerprobe
abgespielt wurde (kein Leerzeichen mehr im Suchfilter).

Verifikation: Vollsuite 2440 bestanden; `tools/gen_contacts.py --check`:
109 Akustikprofile gueltig; `tools/smoke_full.py`: SMOKE-OK;
`git diff --check`: sauber. Der Arbeitsbaum ist nicht committed;
Hardwareabnahme bleibt wie oben offen.

## Remote Crew M4 (2026-09-12, noch nicht committed)

Der deterministische Protocol-v2-Command-Gateway ist umgesetzt. Die exakte
generische Envelope bindet Request-ID und monotonen Client-Seq an Station,
Lease-Generation, Weltsession, Weltepoch und Ressourcenrevision. Der Transport
verwendet Cookie, exakten Origin und CSRF, nimmt nur registrierte Actions an und
haelt abgeloeste FIFO-Envelopes bei 64 global, acht je Client sowie 64
Dedup-Eintraegen je Client. Main-Thread-Drain erfolgt in kanonischer
Stationsreihenfolge, dann Client-Ordinal und FIFO. Direkt vor Ausfuehrung werden
Session, Rolle, Generation, Grants, Alter, Live-Phase und Weltkontext atomar
erneut geprueft. Ergebnisse sind terminal, begrenzt und nur in der erzeugenden
Session ueber `/api/v2/results` sichtbar.

Zum M4-Abnahmestand war als einzige Action das nebenwirkungsfreie `acknowledge`
registriert; der nachfolgende M6.1-Abschnitt ergaenzt die Bridge-Actions.
Administrative Wechsel, Pause/Fokusverlust, Rollenfreigabe/-entzug, Disconnect
und Weltersatz verwerfen unsichere Queues und leeren den vorbereiteten
Held-Control-Zustand. Protocol v1 und Save v10 bleiben unveraendert.

M4-Verifikation:

- Finaler M4-/v1-Server-/v2-Session-/Bridge-Lauf: 357 bestanden.
- Loop-/Save-v10-/Browser-/Projection-/Continuation-Lauf: 291 bestanden.
- `python -m compileall -q src tests/test_commander_commands_v2.py`: sauber.
- `tools/smoke_full.py`: `SMOKE-OK`.
- `git diff --check`: sauber.

## Remote Crew M6.1 Bridge (2026-09-12, noch nicht committed)

Nur der erste M6-Stationsschnitt ist umgesetzt; M6 insgesamt bleibt offen.
Protocol v2 registriert die geschlossenen, ausschliesslich der Bridge-Rolle
erlaubten Actions `bridge_set_course` mit exakt `{course}` (0 bis unter 360)
und `bridge_set_speed` mit exakt `{speed_kn}` (0 bis 25 kn). Beide laufen im
Main Thread ueber dieselben ergebnisliefernden `Game`-Order-Helper wie die
lokale Zahleneingabe. Kursausfall der Bruecke sowie Vorausfahrt-, Telegraph-
und Asternverhalten bleiben lokal und remote identisch; Remote-Befehle wechseln
weder Station, Auswahl, Eingabemodus, gehaltene Tasten noch Fokus.

Die v2-Bridge-Webansicht besitzt ein eigenes lokalisiertes Direct-Order-Panel
mit Ist-/Sollwerten und strikten Zahleneingaben. Grant, Lease, Live-Phase,
veraltete Verbindung und Brueckenausfall sperren die passenden Controls.
Session-Metadaten liefern den naechsten monotonen Command-Seq fuer Reloads.
Eine kryptographische ID, genau ein ausstehender Befehl, isoliertes
`/api/v2/results`-Polling und kein automatisches Wiederholen bei unklarem HTTP-
Ergebnis begrenzen die Ausfuehrung. Legacy-Vorschlag/Klassifikation/Affiliation
bleiben fuer alle v2-Rollen deaktiviert. Protocol v1 und Save v10 sind
unveraendert.

M6.1-Verifikation:

- Commander-Server/Bridge/v1/v2/Browser-Fokus: 460 bestanden.
- M6.1-Command/Projection/Assets/Browser/Layout-Gesamtlauf: 125 bestanden.
- Finaler Command/Session/Projection-Nachlauf: 68 bestanden; finaler
  Asset/Browser/EN-DE-Pseudolocale-Layout/i18n-Nachlauf: 36 bestanden.
- Save-v10-/Katalogsnapshot-/Determinismus-/Continuation-Fokus: 187 bestanden.
- i18n-Paritaet und Pseudolocale: 17 bestanden.
- `tools/gen_contacts.py --check`: 109 Akustikprofile gueltig.
- `tools/smoke_full.py`: `SMOKE-OK`.
- `compileall` und `git diff --check`: sauber.

## Remote Crew F9 Host-Menue und stabiler Beitrittscode (2026-09-12, noch nicht committed)

Das native F9-Hauptmenue enthaelt nur noch Dienst Start/Stopp, Bindeadresse,
Port und den Zugang zur geraeumigen Host-Besatzungsliste. Doppelte Legacy-
Freigabe-, Widerruf-, Zielvorschlags- und Navigationszeilen samt Zusammenfassungen
wurden entfernt. Die bestehende lokale F6/F7-Bestaetigungsbox bleibt fuer
Protocol v1 unveraendert zustaendig. URL und Status sind groesser; der explizit
lokalisierte, gruppierte Beitrittscode `DDD LLL` ist der visuelle Fokus und wird
in EN, DE, Pseudolokalisierung und Grossschrift begrenzt dargestellt.

Der intern ungruppierte Code bleibt waehrend der Lebensdauer desselben
`CommanderServer`-/`CommanderConsole`-Spielobjekts konstant: erfolgreiche v1-
und v2-Kopplungen, mehrere Clients, reine Lesezugriffe, Logout, Client-/Rollen-
Widerruf, Lease-Ablauf sowie Dienst Stopp/Start rotieren ihn nicht. Der fuenfte
Fehlversuch innerhalb des bestehenden rollenden Minutenlimits rotiert ihn als
Security-Lockout. `server.revoke()` markiert weiterhin den bewussten neuen
Server-/Spielkontext; der vorhandene Bridge-Weltersatzpfad widerruft damit alle
Sitzungen und rotiert den Code. Der Code bleibt fluechtig und erscheint weder
in Save v10 noch in Einstellungen.

## OPZ-Beobachtungs-Follow-up (2026-09-12)

ELOKA gibt eine Auffassung erst nach gueltiger Bedienerannotation als reine
`ESM`-Peilung an das gemeinsame OPZ-Bild frei. Die Freigabe besitzt eine von
Simulations-Entities und anderen Sensordomaenen getrennte opake Kennung, keine
Position, Entfernung, Kurs- oder Zugehoerigkeitswahrheit. Loeschen oder Wechsel
der Annotation beendet die Aktualisierung der vorherigen Freigabe; sie altert
mit dem vorhandenen 30-s-Bildvertrag aus.

Der Brueckenausguck erzeugt unabhaengige `LOOKOUT`-Positionsbeobachtungen fuer
aktive Oberflaechenfahrzeuge, U-Boote bis einschliesslich 2 m Tiefe sowie aktive
zivile/militaerische Flugzeuge und Raider. Explizite Grundreichweiten sind 12,
5 und 20 NM; Nachtfaktor 0,35, Seegangsverlust 0,08 je Stufe,
Peilfehler +/-0,6 Grad und Entfernungsfehler +/-6 %. Land sperrt die Sichtlinie.
Messungen laufen in stabiler Reihenfolge auf 0,5-s-Epochen mit lokalen,
deterministischen Seeds und veraendern keinen globalen RNG. LOOKOUT und Radar
bleiben getrennte Beobachtungen. Protocol-v2-Bruecke erhaelt LOOKOUT, OPZ beide
neuen Quellen; andere Rollen erhalten sie nicht.

Verifikation dieses Follow-ups:

- Sensor-/ESM-/OPZ-/Commander-Projektion-/Save-/Determinismus-/i18n-Fokus:
  518 bestanden.
- Abschliessender ESM-/OPZ-/Projection-Nachlauf: 77 bestanden.
- Air-Picture-/Runtime-/Air-Defense-Querschnitt: 178 bestanden.
- `tools/gen_contacts.py --check`: 109 Akustikprofile gueltig.
- `tools/smoke_full.py`: `SMOKE-OK`.
- `compileall` und `git diff --check`: sauber.

## Native OPZ-Fusion (2026-09-12)

Sonarkontakte bleiben bis zu einer gueltigen expliziten Sonar-Klassifizierung
privat. Die Freigabe erzeugt eine unabhaengige opake OPZ-Beobachtung ohne
Entity-/Kontaktkennung und ohne aus `Contact.kind` abgeleitete Domaene. Ohne
aktuellen Ping-, TMA- oder Bojenfix bleibt sie eine reine Peilung; Ruecksetzen auf
unbekannt zieht sie sofort zurueck. Die private Sonar-v2-Projektion behaelt alle
frischen Hoerkontakte.

Die OPZ kann 2 bis 8 markierte aktuelle Meldungen manuell fusionieren, maximal
32 Fusionen. Es gibt keine automatische Korrelation. Fusionen, Markierungen,
Klassifizierungen und lokale Unterdrueckung sind fluechtig, werden nicht in Save
v10 geschrieben und koennen weder Zielzuweisung noch Luftbild, Waffen oder KI
beeinflussen. Native Tastatur- und Mausbedienung verwenden eine gemeinsame
`opz_regions`-Geometrie; die bekannte Kueste bleibt auch bei ausgeschaltetem
Radar gedimmt sichtbar.

Der Browser-Schnitt fuer Sonar-Klassifizierung/Freigabe und OPZ-Lagebild/Fusion
ist umgesetzt. Exakte v2-Actions werden nach Rolle, Lease, Weltkontext, Revision,
Alter, Stationsschaden, aktueller opaker Referenz und Quellenhoheit erneut auf dem
Main Thread geprueft. Der OPZ-Browser verarbeitet exakt `observations`, `fusions`,
`radar`, `source_classifications` und `own_assets`, zeigt bekannte Kueste sowie
rein kosmetische Radarbereiche und bietet lokale Markierung/Unterdrueckung.
Legacy-v2-Vorschlaege bleiben deaktiviert. Protocol v1 und Save v10 sind
unveraendert.

## Remote-Crew-Stationsparitaet (2026-09-13)

Alle neun v2-Rollen besitzen eigene responsive Webstationen. Die Projektionen
liefern ausschliesslich detached, rollenbezogene Daten. Bruecke, Waffen, OPZ,
Funk und Hubschrauber zeigen ihre jeweils freigegebenen Karten; Sonar zeigt
Broadband- und LOFAR-Wasserfall, DEMON, TMA, BT/Umwelt und aktive Echos. Schaden,
Maschine und ELOKA besitzen eigene Schemata, Instrumente und Diagramme. Leere,
veraltete, beschaedigte, pausierte und widerrufene Zustaende werden getrennt
dargestellt.

M6 ist in Software vollstaendig bedienbar. M7 erlaubt genau Schiffstorpedo,
Hubschraubertorpedo, Nixie, ESSM und Chaff ueber aktuelle rollenbezogene opake
Referenzen. Direkte Wirkung verlangt `command`, `direct_fire`, Presence unter
zwei Sekunden und Befehlsalter unter einer Sekunde. Lokale und entfernte Eingaben
verwenden dieselben Main-Thread-Helper. ASROC, CIWS und AA bleiben automatisch
beziehungsweise ausserhalb der Websteuerung.

Sonar-Liveaudio ist ein eigener Host-Grant. Der Main Thread publiziert maximal
zwei immutable 250-ms-Bloecke des bereits modellierten gemischten Receivers als
Mono-PCM mit 4096 Hz. HTTP-Threads sehen keine NumPy-, Kontakt- oder
Simulationsobjekte; Rollen-/Grantverlust, Blockade, Beschleunigung, Sonarschaden
und Weltwechsel leeren den Stream.

Aktuelle Softwareverifikation: Vollsuite 2659 bestanden in 1055,02 Sekunden,
Katalogpruefung 109 Profile, `SMOKE-OK`, Sdist/Wheel erfolgreich und
`git diff --check` sauber. Offen bleibt die physische Mehrgeraete-, Audio-,
Latenz-, Last- und Thermalabnahme auf der 1280x720-uConsole.

## Web-Arbeitsplaetze und Stationsanfragen (2026-09-13)

Die fruehere Aussage vollstaendiger Darstellungsparitaet war durch die damaligen
Tests nicht belegt. Der bisherige Kartenstapel wurde nach Betreiberfeedback
ueberarbeitet: Hauptinstrument links, separat scrollbar angeordnete Bedienung
rechts, kompakter Kopfbereich und einklappbare Zusatzinformationen. Mobile
Ansichten ordnen Instrument und Bedienung untereinander an. Alle neun Rollen
verwenden diesen Arbeitsplatzaufbau. Die alten allgemeinen Reiter sind in v2
durch Stationsnavigation und ein Nebenmenue fuer Stationshilfe, Referenzbibliothek,
Bruecken-Sichtausguck und Stationsfreigabe ersetzt. V1 behaelt seine Navigation.

Korrekturen: Karten-Y-Achse und Pan-Richtung entsprechen nun der nativen Karte;
bekannte Orts-/Flugplatznamen, Tiefenraster und Kursvektoren werden angezeigt.
Sonar uebertraegt 80 historische Zeilen und alle 180 Broadband-Bins, verarbeitet
Gain/Filter wie lokal und zeigt Zeit-/Frequenzachsen, LOFAR-Spektrum sowie eine
gemeinsame TMA-Zeitachse. Diagramme verwenden tatsaechliche Messwerte; eine
pixelgleiche Darstellung wird nicht behauptet.

Webaudio: normale Session-Erneuerungen verwerfen keine gueltigen Audiobloecke
mehr. Timeouts und temporaere Serverfehler lassen die Abrufkette weiterlaufen;
ein begrenzter Startpuffer faengt Jitter ab. PCM-Socketwrites erfolgen ausserhalb
des Serverlocks. Regressionstests fuehren den echten JavaScript-Audiolifecycle
mit Session-Race, Timeout, temporaerem Fehler und Widerruf aus.

Neue Stationsanfragen oeffnen am Host einen administrativen Dialog mit Spieler,
Station und den Rechten Bedienung, direkte Waffenfreigabe und Sonaraudio.
Freigeben uebernimmt Station und Rechte atomar; belegte Stationen werden nicht
uebernommen. Ablehnen und Spaeter sind moeglich. Andere Eingabe-/Dialogbesitzer
werden nicht verdraengt, wiederholtes Polling oeffnet keine weiteren Popups,
zurueckgezogene Anfragen verschwinden. Alle Anfragen/Rechte bleiben transient.

Verifikation: 2665 Tests bestanden in 1180,99 Sekunden; der echte Chromiumlauf
prueft zusaetzlich Instrumentbreite, Anordnung und Sichtbarkeit bei 1280x720.
Katalogvalidator: 109 Profile; Smoke: SMOKE-OK. Die praktische Abnahme auf den
Browsergeraeten (Lesbarkeit, Bedienfluss und Audio ueber reales WLAN) bleibt
ausdruecklich offen.

## Remote-Crew-Laufzeit und Bedienfluss (2026-09-13)

Bei mindestens einer aktiven Remote-Station halten F1-Hilfe, der laufende
F8-Kontaktanalysator, F9-Crewverwaltung und F10-Optionen die autoritative
Simulation sowie Browserstationen live. Ohne aktive Crew bleibt das bisherige
Pausenverhalten erhalten. Manuelle Pause, Fokusverlust, Nationen, Save/Load,
Quit, echte Editoren, Menues und Splash blockieren weiterhin. Dieselbe
Entscheidung steuert Simulation, v2-Phase, Commands, Projektion und Sonaraudio;
Owner-Wechsel invalidieren weiterhin bereits wartende Commands.

Der Browser trennt jetzt den Wechsel zwischen gehaltenen Leases von der Aktion
`Station hinzufuegen`. Eine genehmigte Anfrage erhaelt normale Bedienrechte und
oeffnet die neue Station automatisch; direkte Waffenfreigabe und Sonaraudio
bleiben separate Host-Rechte. Im Broadband-Wasserfall setzt ein Klick oder Tap
die manuelle Horchpeilung und loest Kontaktfokus. LOFAR bleibt reine Analyse.

Softwareverifikation: 2699 Tests bestanden in 1150,57 Sekunden, inklusive echter
Chromiumlaeufe fuer Desktop und Mobil. Katalogvalidator: 109 Profile; Smoke:
`SMOKE-OK`; Sdist und Wheel fuer 0.2.0 erfolgreich gebaut; `git diff --check`
sauber. Physische Mehrgeraete-, Audio-, WLAN-, Last- und Thermalabnahme auf der
uConsole bleibt offen.

## Naechster Schritt

Der verifizierte 0.2.0-Kandidat wurde als `5203707` lokal committed. Es erfolgte
kein Push und kein Release-Upload.

1. Vor einem Release die oben aufgefuehrten physischen Abnahmen
   durchfuehren.

## 0.1.7 Entscheidungen

Der verbindliche Gesamtplan steht in `docs/plan-0.1.7.md`. Kerngrenzen:

- Ausschliesslich Save v10 schreiben und laden; keine Migration.
- Szenario bestimmt Seite; Plattformprofile sind neutral.
- Neun Plattformen als Pilot, danach familienweise Gesamtkatalogmigration.
- Oeffentliche Referenzdaten plus klar synthetische Akustik-/Radarspielwerte.
- Runtime bis ASW-Tier 2 und Luftabwehr-Tier 3.
- Nimitz-Luftgruppe, Type-901-Nachversorgung, LACM, Geschuetzkrieg und
  Verbandsoperationen bleiben Tier 4.
- Private WaveOps-/MNW-Unterlagen liefern weder Daten noch Bilder, Layouts oder
  abgeleitete Diagramme.
- Pakete B-F sind freigegeben und folgen nach R13 in der festgelegten Reihenfolge.
- R15 umfasst verbindlich die verdichtete, seitenspezifische Sonardarstellung
  fuer LOFAR und DEMON, strukturierte Footer-Segmente und die Abnahme des
  1280x720-Canvas in einem letterboxed 1280x800-Fenster.
- Nach der abschliessenden B-F-Gesamtabnahme verpflichtend pausieren.

## Offene Hardwareabnahme

- Dauerhaft Motor, Sonar und Alarme auf der 1280x720-uConsole bei 1x abhoeren.
- Mit `U_JAGD_AUDIO_DEBUG=1` Framedauer, Holds, Drops und Evictions beobachten.
- 1x/5x/1x-Wechsel ohne Backlog oder Klick pruefen.
- Zwei physische Geraete, Firewall, Reconnect, Browseraudio und lange
  Kontakt-/Ereignislisten im LAN pruefen.

Keine Codes, Tokens oder andere Zugangsdaten in diese Datei eintragen.

## 0.2.1 Release-Kandidat (2026-09-14)

Version 0.2.1 umfasst deterministisches Seewetter mit Sensor-/Helikopterwirkung
und animierten lokalen/Browserinstrumenten, stationsbezogene Autocrew,
Treibstoff- und erweiterte Maschinenraumdaten, vervollständigte Remote-Crew-
Stationen sowie den temporaeren uConsole-WPA2-Hotspot mit eng begrenztem
System-Helper. Save bleibt exakt v10; Commander v1 und v2 bleiben getrennte
Protokollvertraege.

Die deutsch/englische Haupt-, Installations-, Koop- und Protokolldokumentation ist
aktualisiert. `docs/station-shortcuts.de.md` und das reproduzierbare dreiseitige
A4-PDF `docs/station-shortcuts.de.pdf` enthalten die implementierte lokale
Bedienung aller neun Stationen. Erzeugung und Driftpruefung erfolgen mit
`python tools/build_station_shortcuts_pdf.py [--check]`.

Softwareverifikation: 317 fokussierte Kern-/Save-/Wetter-/Autocrew-/Hotspot-/
Commander-Tests, vier echte Chromium-Vertraege, 123 Startup-/i18n-/Layout-Tests
und zwei Pakettests bestanden. Katalogvalidator: 109 Profile; Smoke: `SMOKE-OK`;
PDF: A4, drei Seiten, unverschluesselt, ohne Skripte oder Metadatenstrom. Ein
Gesamtlauf erreichte vor dem Ausfuehrungszeitlimit 26 Prozent ohne Fehler. Die
physische WLAN-, Mehrgeraete-, Audio-, Lesbarkeits-, Last- und Thermalabnahme auf
der uConsole bleibt offen.

## 0.2.2 Release-Kandidat (2026-09-14)

Version 0.2.2 stellt Remote Crew vollständig auf API-Protokoll v2 um. Alle
`/api/v1/*`-Routen sind entfernt und liefern 404 ohne Weiterleitung oder Fallback.
Browser verwenden ausschließlich Cookie-Sitzungen mit Origin-/CSRF-Schutz.
Ziel- und Navigationsvorschläge bleiben bis zur lokalen Host-Annahme wirkungslose
Staging-Anfragen. Ereignisse beachten Sitzungs-, Rollen- und
Beobachtungsgrenzen. Das separat freigegebene SimLog ist eine auf 64 abgelöste
Full-Truth-Diagnose-Snapshots begrenzte Ausnahme. Save bleibt exakt v10.

Softwareverifikation: vollständige Suite mit 2467 bestandenen und 26 abgelösten
Layoutfällen; darin vier Browser-Sitzungsverträge. Der nach Review erweiterte
fokussierte Release-Satz bestand mit 311 Tests und deckt SimLog-Epochwechsel,
Freigabewiderruf, sofortige Rollencache-Grenzen, Cache-Löschung beim Widerruf,
reine Lobby-Clients, Alarm-Ausgangsbasen und unsichere Befehlssequenzen ab.
Katalogvalidator: 109 Profile;
Smoke: `SMOKE-OK`; Paketbau: 0.2.2-sdist und -Wheel erfolgreich; Stationsreferenz
reproduzierbar; `git diff --check` sauber. Der Kandidat ist uncommitted und wurde
nicht gepusht oder veröffentlicht.

Offen bleibt ausschließlich die physische Hotspot-, Mehrgeräte-, Audio-,
Lesbarkeits-, Last- und Thermalabnahme auf der uConsole.

## Native OPZ-Kartenkamera (2026-09-20)

Die native OPZ verwendet jetzt den eigenen Arbeitsbereich `(0, 30, 1280, 690)`
und eine nordorientierte rechteckige Karte mit unabhängiger `Viewport`-Kamera.
Mausrad-Zoom bleibt unter dem Zeiger verankert und reicht bis 5 NM Radius,
Ziehen schwenkt die Karte und beendet Follow, `K` schaltet OPZ-Follow separat.
Bild↑/Bild↓ verändert weiterhin ausschließlich den schiffszentrierten
Radarbereich 10/20/40/80/120 NM; Sweep, Clutter und Ringe werden an der frei
navigierten Karte geclippt. Ereignis-Feed und Telemetrie werden in der OPZ nur
nicht gezeichnet und laufen unverändert weiter.

Der Kamerazustand wird als optionale Erweiterung im unveränderten v11-`ui`-
Objekt gespeichert. Vollständige ältere v11-UI-Zustände ohne die vier neuen
Felder erhalten sichere schiffszentrierte Standardwerte; partielle, typfalsche
oder nicht endliche Zustände werden vor dem transaktionalen Commit abgewiesen.
Remote Crew und die Kameras anderer Kartenstationen bleiben unverändert.

## 0.2.3 Release-Kandidat (2026-09-18)

Version 0.2.3 ergänzt ein zentrales Theme-System (`src/ui/theme.py`), das
Standard- und High-Contrast-Farbpaletten für `config.COLOR_*`, `sonar_view`
und den Unit-Editor konsolidiert und bei jedem Zeichenaufruf über
`layout.configure_for()` neu anwendet. Jede der neun Stationen bekommt zwei
Unterseiten (Tab-Leiste, z. B. Bridge: Navigation/Mission, Weapons:
Targeting/Ammunition) mit gemeinsamer Tab-Hit-Test-/Zeichenlogik in
`stations_view.py`; Seiten- und Tastenbelegung stehen in
`core/commands.py:STATION_PAGES` und `core/i18n.py`'s `station_page`-
Anzeigeschlüsseln. Weapons und OPZ bekommen manuelle Freigabeschalter für
FLAK (`F`) und CIWS (`I`), die als zusätzliche UND-Bedingung neben den
bestehenden Frische-/Reichweiten-/Munitions-/Stationsausfall-Prüfungen der
Auto-Feuerlogik greifen. Die Autocrew-Brücke weicht jetzt beobachteten
ASM-/Torpedo-Bedrohungen aus (Kursumkehr + Flankenfahrt, nur auf durch
`world.hull_is_safe()` geprüften Kursen) und korrigiert eigenständig einen
projizierten Aufsitzer, wenn kein Ziel bedroht; die Waffen-Autocrew
verschießt Torpedos auf den nächsten klassifizierten Feindkontakt. Die
TMA-Loesung (`sonar/tma.py`) bekommt eine Re-Solve-Hysterese
(`TMA_HYSTERESIS_RMSE_MARGIN_DEG`), die zwischen fast gleichwertigen
Peilungslösungen nicht mehr bei jedem Update hin- und herspringt, und
`SensorTrack.derived_motion()` schätzt Kurs/Speed jetzt per
Kleinste-Quadrate-Fit über das gesamte gehaltene Messfenster statt nur aus
den letzten zwei Fixes. Separat dazu: ein aktiver Radar-Suchkopf für ASM
(`seeker_active_range_nm`, 18 NM), der ab Terminalphase eine eigene
ESM-Signatur (9,0-9,5 GHz, Puls-Doppler) unabhängig vom bestehenden
Jammer-/HOJ-Pfad ins ESM-Bild speist – eine frühere, RWR-basierte Warnung vor
einer ansteuernden Rakete, bevor das Suchradar sie erfasst; siehe
`docs/simulation-gaps.md` Abschnitt 6 für die zwei dazu noch offenen
Folgepunkte (Radarhorizont für den ASM-Rumpf selbst, Anflug-Höhenprofil des
Raiders).

Beim Fertigstellen dieses unfertig vorgefundenen Standes wurden zwei echte
Fehler behoben: `autocrew._nearest_threat()` verglich beim Unentschieden
einen String-Track-Schlüssel (ASM) gegen eine Integer-Kontakt-ID (Torpedo)
und stürzte ab, sobald beide gleichzeitig unbekannte Reichweite hatten;
`AutocrewController._bridge()` befahl den Ausweichkurs ungeprüft, ohne die
Grundberührungsprüfung der direkt darunterliegenden Korrekturlogik zu
verwenden. Beide sind durch Regressionstests abgesichert
(`tests/test_autocrew.py`). Dazu kam ein Layoutfehler in
`commander/local.py`: `_hotspot_qr()` war noch auf die alte 132px-Box
skaliert, obwohl das Hotspot-Layout inzwischen zwei nebeneinander stehende
105px-QR-Codes zeichnet. Drei bereits gemergte Tests hingen an inzwischen
veralteten Annahmen und wurden korrigiert statt den Code danach zu richten:
`tests/test_startup.py`/`tests/test_packaging.py` prüften noch die
Versionszeichenkette „0.2.2", und `tests/test_ui_performance.py` patchte
`config.COLOR_DEEP` direkt, was das neue Theme-System bei jedem Zeichenaufruf
wieder überschreibt – der Test patcht jetzt stattdessen
`theme.CONFIG_COLORS_STANDARD`, die tatsächliche Quelle.

Softwareverifikation: vollständige Suite 2641 bestanden, 26 abgelöst (offene
Hardwareabnahme), 0 Fehler. Katalogvalidator: 111 akustische Profile.
Smoke: `SMOKE-OK`. Paketbau: 0.2.3-sdist und -Wheel erfolgreich.
`docs/screenshots/*.png` wurden mit `tools/capture_screenshots.py` für
beide Sprachen neu erzeugt (Stationsseiten-Tabs, CIWS/FLAK-Freigabe sichtbar).
Der Kandidat ist uncommitted und wurde nicht gepusht oder veröffentlicht.

Offen bleibt ausschließlich die physische Hotspot-, Mehrgeräte-, Audio-,
Lesbarkeits-, Last- und Thermalabnahme auf der uConsole.

## Optionaler Webspiel-Modus (2026-09-21)

`--web-host --public-origin https://...` startet einen fensterlosen Raum hinter
einem eigenen HTTPS-Proxy auf Loopback. `--web-bind PRIVATE_IP` erlaubt einen
Proxy auf einem anderen Gerät im vertrauenswürdigen LAN. Ein einmaliger Terminal-Code richtet das
dauerhafte Host-Passwort ein. Das Host-Konto verwaltet Crew-Leases und Freigaben
im Browser, nutzt die neun vorhandenen v2-Stationen und die Solo-Spielsteuerung.
Die Weboptionen halten Live-Daten-Schlüssel aus Antworten heraus. Der Host-Ausfall pausiert das Spiel nach 15 Sekunden. Der neue Modus ist
optional; bestehender Commander LAN und v10-Spielstände bleiben unverändert.

Offene Abnahme: echter HTTPS-Proxy mit mehreren Geräten, Audio/WebSocket im LAN,
Lesbarkeit bei Zoom und Last/Temperatur auf dem Zielgerät.

## Audio-Aufräumung und Perf-Diagnose-Hook (2026-09-22)

Analyse von Audio, Simulations-Takten und CPU-Schonung auf uConsole und
Webbrowser ergab: Das Echtzeit-Audio-System (lokaler Pygame-Mixer mit
reservierten Kanälen und bounded Queues; Remote-Crew-Sonar-/Hubschrauber-
Audio per WebSocket mit AudioWorklet-Jitterpuffer und HTTP-Fallback) war
bereits vollständig gebaut. Die Sim-Takt-Frage ist beantwortet: Physik läuft
strikt in Echtzeit (ein Substep pro Frame bei 60 FPS), Zeitraffer existiert im
Code nicht mehr; die Akkumulator-Drosselung teurer Systeme (Sonar-Kontaktbild
4 Hz, ESM/Funk/Schaden 2 Hz, Autocrew-Stationen 0,5–5 s) ist bewusste
CPU-Schonung, unabhängig vom eigenen 0,25-s-Takt der Audio-Blockerzeugung.

Auf Nutzerwunsch entfernt: die nie aufgerufene kontinuierliche
Eigenschiffs-Motor-/Rotor-Ambience (`AudioEngine.update_engine`/
`update_helicopter` samt State, RNG-Strom und den beiden reservierten
Mixer-Kanälen; `propeller_block`/`helicopter_block`/`ship_ambience_block`
aus `src/audio/synthesis.py`). Vier Doku-Stellen (EN/DE) korrigiert, die eine
im Browser-Client nie vorhandene Kavitations-Ambience beschrieben.

Neu: ein optionaler, bounded `U_JAGD_PERF_DEBUG=1`-Hook
(`Game._perf_debug_log`) protokolliert 1×/s Zeitanteile von Physik-Substeps,
Audio-Publish, Remote-Crew-Pump und Draw/Compose nach
`~/.u-jagd/perf_debug.log` — bislang gab es keinerlei Timing-Instrumentierung
im Code. Die symlink-sichere, größenbegrenzte Schreiblogik wurde aus
`AudioEngine.debug_log()` in `src/core/debuglog.append_bounded_log()`
extrahiert und von beiden genutzt.

Offen: die eigentliche Diagnose der gemeldeten Sonar-Audio-Aussetzer im
Webbrowser braucht eine Reproduktion auf echter uConsole-Hardware
(`U_JAGD_AUDIO_DEBUG=1` plus `window.uJagdAudioDiagnostics` im Browser), um
Netzwerk-Jitter, falschen Transport oder uConsole-seitige Produktionslücken
zu unterscheiden, bevor Jitterpuffer/Backpressure/Reconnect gezielt
angepasst werden.

Softwareverifikation: volle Suite zweimal 2933/2934 bestanden, 26 abgelöst,
0 Fehler; Katalogvalidator 111 akustische Profile; `smoke_full.py`
SMOKE-OK.

## Physik-Upgrade 1.1.0 / Save v12 (2026-09-23, Branch `sim-gaps-v12`)

Alle Luecken aus `docs/simulation-gaps.md` sind in den Phasen 0-12 geschlossen
(Abschlussprotokoll mit Commit je Zeile in `docs/simulation-gaps.md`). Save v12
ist exakt; v11-Staende von 1.0.0 werden abgelehnt. Versioniert als 1.1.0.

- Kalibrierung: `python tools/calibrate.py --check` (77 Metriken gegen den
  1.0.0-Stand, Abweichungen begruendet in `tests/calibration/deviations.json`).
  Der Abschnitt `air` wurde mit derselben Sonde auf dem 1.0.0-Baum gemessen.
- Performance: ein 0,1-s-Simulationsschritt kostet auf dem ARM-Entwicklungshost
  im Mittel 6,7 ms (drei Seeds, wie 1.0.0). Groesster Einzelposten war die
  ELOKA-Emitterbewertung; sie ist jetzt pro Fingerabdruck begrenzt gecacht.
  Raytrace-Tabellen (LRU), Radar-Reichweitenbrueche und ESM-Analysen sind reine,
  begrenzte Caches.
- Offen fuer die Hardwareabnahme auf der uConsole (1280x720): Bildrate bei
  maximaler Zeitraffung mit Luftangriff und mehreren Torpedos, Lesbarkeit der
  neuen ELOKA-Zeile (Pegel/Entfernung/Umlauf) und der HFDF-Frequenz, sowie das
  Verhalten der 4-s-Radarumlaeufe auf dem OPZ-Bild.
- Merge: der Branch entstand parallel zu einer Handbuch-Session auf `main`
  (AGENTS.md, README, Handbuch); beim Zusammenfuehren diese Dateien pruefen.

## Sonar-Audio ohne Aussetzer (2026-09-26)

Die seit dem 22.09. offene Diagnose der Browser-Aussetzer ist abgeschlossen; die
Analyse lief auf dem Zielgeraet (CM5, 16 GB) mit dem neuen Lasttest.

- Ursache der Aussetzer "nach Tastendruck am uConsole": jede lokale
  Eingabeaenderung (F1, F9, Optionen, Zahleneingabe) erhoehte die Welt-Epoche,
  `prepare_*_audio` leerte den Ring und setzte die Blocknummer auf 0. Der
  Browser verband den Socket neu, das Worklet behielt aber `lastSequence` und
  verwarf jeden neuen Block (`sequence <= lastSequence`), bis die Zaehlung den
  alten Stand ueberholte: Granular-Ersatz, dann Stale-Rauschen, so lange, wie
  der Client vorher zugehoert hatte. Fix: Nummerierung je Rolle monoton ueber
  die Server-Lebensdauer (Clear ueberspringt eine Nummer), Retune markiert eine
  Diskontinuitaet (`mark_audio_discontinuity`), Reconnect mit `?after=` statt
  Neusendung, Duplikate werden im Worklet gezaehlt statt stumm verworfen.
- Messung: Empfaenger-Synthese 4-19 ms pro 0,25-s-Block (2-24 Quellen), Filter,
  Resampling und PCM zusammen unter 0,6 ms; die Audioerzeugung war nie das
  Problem. Der Remote-Crew-Publish kostete pro 2-Hz-Veroeffentlichung 60-120 ms
  Hauptthread (5 Mio. `deepcopy`-Aufrufe, Requantisierung der kompletten
  600-s-Sonar-Historien, `json.loads`/Re-Encode der Sonarprojektion, Roster pro
  Frame). Nach Zeilen-Cache je Sonarstation (schwach referenziert, exakt gleiche
  Ergebnisse), flachen Rollenkopien, Bytes-basierter Kompaktprojektion und 4-Hz-
  Roster: rund ein Sechstel der Pump-Zeit.
- Puffer fuer 16 GB: lokal Vorlauf/Ziel 1,5 s, Warteschlange 5 s, Refill 1 s,
  Stale 3 s, SDL-Mixerpuffer 2048 Samples (93 ms); Browser Prime/Ziel 2 s, Max
  6 s, Refill 4 Bloecke, Stale 3 s; `SIM_CATCHUP_MAX_S` 2,5 s (Invariante:
  Warteschlange >= Ziel + Catch-up + Block, damit im Aufholen nie ein Block
  abgelehnt und aus dem Zwei-Block-Empfaengerfenster verdraengt wird);
  Audio-Socket 6 s Sendetoleranz, neueste acht Bloecke fuer cursorlose Sockets.
- Neue Zaehler: `channel_idle` (Mixerkanal leer bei geprimtem Strom = hoerbarer
  Dip), `pump_late`/`pump_late_max_ms`, `input_gaps`; `perf_debug.log` mit
  `commander_max_ms`, `events_ms`, `traffic_ms`; Server `audio_stream_stats()`
  (uebersprungene Bloecke, Sendetimeouts, Diskontinuitaeten, Verbindungen);
  Browser `droppedBlocks`/`evictedBlocks`.
- `tools/audio_soak.py host` (echter Mixer oder `--dummy-audio`, N Clients,
  Epoch-Sprung/Retune-Takt, `--profile`) und `client` (PC im WLAN). Ergebnis
  auf dem CM5 mit echtem Mixer, 9 Clients, 14 Epoch-Spruengen, 4 Retunes ueber
  67 s: 0 Unterlaeufe, 0 leere Kanaele, 0 Stillen > 0,75 s in beiden Streams,
  frame_max ausserhalb des Starts 168 ms (vor Phase D), sim_dropped 0.
- Regressionstests: monotone Sequenzen je Rolle, Resume-Cursor, Duplikat-
  Zaehlung im Worklet, Bridge-Diskontinuitaet bei Retune, Browsertest prueft
  jetzt weiterlaufende, streng steigende Bloecke nach Epoch-Spruengen, Idle-/
  Late-Zaehler, Puffer-Invariante, Soak-Werkzeug headless.
- Offen: Hoerabnahme mit echtem Browser-PC ueber WLAN (`tools/audio_soak.py
  client`, `window.uJagdAudioDiagnostics`), WLAN-Stromsparen am uConsole
  abschalten (docs/install-uconsole). `test_real_v2_role_states_survive_...`
  (Helikopter-LOFAR-Ansicht zu klein) schlug bereits vor dieser Arbeit fehl.

## Durchlauf 1.3 (ab 2026-09-26, Branch `plan-1.3`)

Arbeitsvorlage: `docs/plan-1.3.md`. Ein Commit je Phasenschritt, kein Push.
Wiederaufnahme: `git log --oneline main..plan-1.3` zeigt die fertigen
Schritte; diese Tabelle nennt Stand, Zahlen und offene Punkte je Phase.

| Phase | Stand | Commit | Suite | Offen |
|---|---|---|---|---|
| 0 Audio-Soak | fertig (Auftraggeber) | `ef45a4f` | siehe Abschnitt "Sonar-Audio ohne Aussetzer" | Hoerabnahme auf Hardware |
| 1 Crew-Zustand (Save v15) | fertig | siehe `git log` | 3404 bestanden, 26 uebersprungen, 47 min seriell unter Last | zwei vorbestehende Fehlschlaege (unten) |

| 3 Tests/Checkliste | fertig | siehe `git log` | 3406 bestanden parallel in 16:34 (seriell unter Last 47 min) | Ziel 2 min verfehlt: kritischer Pfad ist `test_calibration` (556 s, jetzt `slow`) |

Notizen Phase 3:

- pytest-xdist 3.8 in `.venv` und im `dev`-Extra; `addopts = "-n auto --dist
  loadgroup"`. `conftest.py` markiert jedes Modul, das Chromium startet, als
  `browser` und verteilt diese Module auf zwei `xdist_group`-Gruppen, damit
  hoechstens zwei Chromium-Instanzen gleichzeitig laufen (mehr davon liessen
  DOM-Probe-Tests unter Last ausfallen).
- `slow` markiert: `test_calibration.py`, `test_smoke_full.py`,
  `test_contact_analysis_images.py`, `test_unit_reference_pdf.py`. Lokal
  iterieren mit `-m "not browser and not slow"`.
- `test_solo_console_tabs_keep_state_and_host_controls_drive_the_game` pumpt
  das Spiel mit Wanduhr-Budget; unter Last brauchte Chromium ueber 80 s, das
  Budget ist jetzt 150 s.
- `docs/hardware-acceptance.md` angelegt; `docs/verification-log.md`
  verweist darauf. `tests/test_project_config.py` haelt die pyproject-Vertraege.

| 2 Kernzerlegung | fertig | e062bb2, 1a9ba36, a26a459, 22b5b16, 6998cf0, 6e898c2, facd86e | volle Suite und Kalibrierung am Ende der Phase (siehe unten) | keine Datei ueber 2500 Zeilen (`tests/test_module_size.py`) |

Notizen Phase 2:

- `Game` ist jetzt eine Komposition aus Mixins: `SaveMixin` (`game_save.py`,
  Validator in `save_validate.py`, Grenzen in `limits.py`), `SimMixin`
  (`game_sim.py`, `SIM_ORDER` + `tests/test_sim_order.py`), `EventMixin`
  (`game_events.py`), `MissionBridgeMixin` (`mission_bridge.py`), dazu ueber
  den Plan hinaus `DrawMixin` (`game_draw.py`), `OperatorMixin`
  (`game_operator.py`) und `PicturesMixin` (`game_pictures.py`), damit die
  2500-Zeilen-Grenze haelt; `game.py` (705 Zeilen) ist nur noch
  Composition Root. Alle Verschiebungen wortgleich (Skript im Scratchpad:
  Methoden per Namensliste, Importblock kopiert, pyflakes-geprueft, ungenutzte
  Importe entfernt). `game.py` re-exportiert die Namen, die Tests importieren.
- Tests, die Modulnamen patchen, zeigen jetzt auf das Modul, in dem der Name
  nachgeschlagen wird (`game_draw.save_preferences`, `game_events.*_test_connection`,
  `game_save.MAX_SAVE_DOCUMENT_BYTES`, `save_validate.CATALOG`, `routes.time`).
- Stationsansichten: `src/ui/stations/{common,bridge,opz,eloka,radio,engine,
  helicopter,damage}.py`; `stations_view.py` Facade mit `station_hit_target`.
- Server: `src/commander/v2/{wire,commands,routes}.py` statt der im Plan
  genannten `routes_v2/streams/sessions`: Leases und Sitzungen sind mit
  `CommanderServer` verflochten und bleiben dort (1763 Zeilen); die Grant-Tabelle
  `station_grants` liegt in `wire.py`, der Logger heisst weiter
  `src.commander.server`.
- Perf (headless, `_update_sim(0.1)`, drei Seeds, 1200 Schritte): vorher
  4,49 ms, nachher 4,27 ms je Substep. Hardware-Frame-Zeit bleibt Pruefpunkt.
- Abweichung vom Plan: zwischen den Schritten liefen fokussierte Tests plus
  Smoke; die volle Suite und die Kalibrierung liefen nach Schritt 1 und nach
  Schritt 6. Unter paralleler Last flackern
  `test_solo_console_tabs_keep_state_and_host_controls_drive_the_game` (Budget
  jetzt 300 s, eigene xdist-Gruppe), `test_default_off_has_no_network_or_server_resources`
  (Thread-Zaehlung) und `test_audio_websocket_resumes_behind_the_browser_cursor`
  (409 stream_exists); alle drei bestehen einzeln.

Vorbestehende Fehlschlaege (auf `main` ef45a4f identisch, nicht Teil des
Durchlaufs): `test_commander_browser_sessions_v2.py::test_real_v2_role_states_survive_unpublished_admin_grants_and_presence`
(beide Aufloesungen, Helikopter-LOFAR-Ansicht) und
`test_opfor_web.py::test_submarine_sonar_filters_and_audio_survive_host_input`
(Stufe "audio after host input"). Beide sind Browser-Tests; sie werden je
Phase mit `--deselect` ausgenommen und am Ende des Durchlaufs gemeldet.

Notizen Phase 1:

- `crew` ist ein Objekt oder `null` (ein besetztes Boot, `Game._opfor`), nicht
  eine Liste: das Spiel kennt genau eine Crew-Bindung.
- Sub-Zeile zusaetzlich: `manual`, `order_course`, `order_speed`,
  `order_depth`, `last_bottom_m`, `manual_ping_pending`
  (`SUB_CREW_FIELDS`); `endurance.manual` folgt `manual` beim Laden.
- Der Sonar-Save/-Restore/-Validator der Fregatte ist in
  `Game._sonar_controls_state`, `_sonar_system_state`,
  `_restore_sonar_controls`, `_restore_sonar_system` und die Closures
  `valid_sonar_controls`/`valid_sonar` gezogen und dient dem Boot unter
  `sonar_perspective`. Fuer das Boot gelten zusaetzlich die Quell-IDs
  `OWNSHIP_TARGET_ID` und `OWN_TORPEDO_TARGET_BASE + idx` als Kontaktziele.
- Halte-Regel: nach einem Load bleibt die Crew-Bindung fuer
  `UBOOT_RESTORE_HOLD_S` (600 s Sim) bestehen, auch ohne gehaltene Station;
  `_sync_opfor` gibt das Boot erst danach an die KI. `crew.hold_s` haelt den
  Restwert (exakter Round-Trip), ein Load setzt ihn auf das Maximum.
- `ui.local_side` wird gespeichert und geladen (uConsole-Seite).
- Anzeigehistorien des Sonars (Breitband/LOFAR/Echo) sind nach einem Load
  nicht bitgleich (transienter Overlap-Add-Zustand des Audioempfaengers, wie
  bei der Fregatte); der Continuation-Test vergleicht sie deshalb nicht,
  alle Simulationsfelder sind ueber 300 s identisch.
