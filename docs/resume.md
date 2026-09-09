# Wiederaufnahme

## Stand

Stand 2026-09-08 auf Branch `main`, HEAD `ed4dcc7`. `HEAD` entspricht
`origin/main`. Die vier letzten Projektcommits sind:

- `1a8e278` Commander LAN co-op web console, Version 0.1.6,
- `fb7a6ce` Audio-Pufferdiagnose,
- `1aae70d` begrenzter Sonar-Hold und Wall-Time-Audioauslieferung,
- `ed4dcc7` OpenCode-Workflow.

Der Arbeitsbaum enthaelt die noch uncommittierte 0.1.6-Stabilisierung sowie
R0 bis R8 von 0.1.7. Vorhandene Aenderungen wurden nicht
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

1. R9 Flugkoerperabwehr gemaess `docs/plan-0.1.7.md` als naechstes
   Runtimepaket umsetzen.
2. Vor jeder weiteren Komponenten-Runtimewirkung den v10-Snapshot und die
   Split-Run-Abnahme additiv erweitern.
3. Physische uConsole-Audio-/Performance- und Zwei-PC-LAN-Pruefung durchfuehren
   oder weiterhin ausdruecklich als offen dokumentieren.
4. Nur bei angeforderter Git-Freigabe committen/pushen.

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
