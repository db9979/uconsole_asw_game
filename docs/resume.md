# Wiederaufnahme

## Stand

Stand 2026-09-11 auf Branch `main`, Basis-HEAD `7d52faf`. Die vier letzten
Projektcommits sind:

- `1a8e278` Commander LAN co-op web console, Version 0.1.6,
- `fb7a6ce` Audio-Pufferdiagnose,
- `1aae70d` begrenzter Sonar-Hold und Wall-Time-Audioauslieferung,
- `7d52faf` 0.1.7 Sensor- und ASW-Systeme.

Der Arbeitsbaum enthaelt den vollstaendig softwareabgenommenen, noch
uncommittierten R9-R19-Kandidaten samt Hydroakustik-/Analyzer-Follow-up.
Vorhandene Aenderungen wurden nicht
verworfen. Fuer diese uncommittierten Aenderungen ist kein Push oder
Release-Upload erfolgt.
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

R19-Softwareabnahme und verpflichtender Pausenpunkt sind erreicht. Es existiert
kein neuer Commit; der Kandidat liegt als grosser absichtlich uncommittierter
Arbeitsbaum auf Basis `7d52faf`. Ohne ausdrueckliche Git-Freigabe wurde nichts
gestaged, committed oder gepusht. Ein Build nur aus Basis-HEAD reproduziert den
Kandidaten nicht; ungetrackte Runtime-, Test- und 226 Analyzerdateien muessen bei
einer spaeter autorisierten Commitvorbereitung bewusst einbezogen werden.

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

## Naechster Schritt

1. Verpflichtend pausieren.
2. Erst nach ausdruecklicher Freigabe Status/Gesamtdiff pruefen, den kompletten
   Kandidaten gezielt stagen und einen reproduzierbaren Commit vorbereiten.
3. Vor einem Release die oben aufgefuehrten physischen Abnahmen durchfuehren.
4. Nicht ohne ausdrueckliche Freigabe committen oder pushen.

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
