# Entwicklungsplan 0.1.6

## Verbindlicher Umfang

Zuerst Commander-Webkonsole fuer zwei Spieler im vertrauenswuerdigen LAN:
Kommandant im Browser, Besatzung auf der uConsole. Anschliessend dokumentierter
Pausenpunkt. Keine automatische Fortsetzung der spaeteren Sonar-/Stationspakete.

- Browserauswahl ist lokal und veraendert keinen Hoerfokus.
- Klassifizierung und Zugehoerigkeit nach lokaler Freigabe gemeinsam editierbar.
- Zielvorschlaege werden erst nach Bestaetigung der Besatzung uebernommen.
- Keine Fernbedienung von Waffen, Sensoren, Steuerung, ROE, Zeit oder Saves.
- Kommunikation ueber Markierungen und externe Sprache; kein Sprachchat,
  Freitextchat oder allgemeines Auftragssystem im ersten Meilenstein.
- Server standardmaessig aus; Zugang und Befehlsfreigabe nur fuer diese Sitzung.
- Kopplungscode: genau drei Ziffern plus drei Grossbuchstaben (z.B. 482KMT),
  fuenf Minuten gueltig, maximal fuenf Fehlversuche pro rollender Minute.
  Der lange Bearer-Sitzungsschluessel bleibt davon unabhaengig.
- Version 0.1.6 ist unabhaengig vom weiterhin gueltigen Saveformat v8.

Neuer Auftrag vom 2026-09-07 (Pakete G-L):

- G: Crew-MessageBox an der uConsole: Ziel- und Navigationsvorschlaege des
  Commanders in einer festen, nicht blockierenden Box annehmen oder
  ablehnen.
- H: Sound knackt an der uConsole. Root-Cause-Analyse und Puffer-/
  Lastmassnahmen im Audio-Pfad; keine Simulationsaenderung.
- I: Bridge Lookout: 2D-Topdown-Aussenansicht im Commander-Browser
  (Schiff, Kurs, Seeklasse, Kontakte - nur Beobachtungsdaten).
- J: Eloka (ESM-Zentrale) als neue 9. Station: Radarstrahlen und
  Radartypen auswerten, Klassifizierung und Kontaktbestimmung.
- K: Commander-Webkonsole: komplette detaillierte Anleitung je Sprache,
  Kontakt-Datenbank mit Radar- und Sonar-Fingerprints samt Analyse-
  Bildern; Gesamtdarstellung passt auf einen Bildschirm ohne vertikales
  Scrollen.
- L: Kontakt-Profile auf Basis offener Real-Plattform-Daten neu
  befuellen (alle Eintraege, Keys stabil), erweitertes Schema
  (Dimensions, Crew, Maschinen, Sensoren/Bewaffnung, LOFAR in zwei
  Fahrzustanden).

Pakete B-F bleiben vertagt; sie starten nach G-L nur mit erneuter
Anweisung. Im Repo: keine WaveOps-/MNW-Texte, -Bilder oder -Layouts;
offene Quellen und dokumentierte Spiel-Modellwerte.

## Ausgangsstand

Branch main, letzter Commit 3bf30bf (Harden world seed selection).
Die umfangreichen vorausgehenden Review-Korrekturen sind uncommittet und werden
erhalten. Zuletzt vor diesem Meilenstein: 1311 Tests, Smoke, Katalog und Build
erfolgreich. Das ist keine Verifikation der neuen Netzwerkfunktion.

## Arbeitspakete

| ID | Inhalt | Status | Abnahme |
|---|---|---|---|
| A0 | Ausgangsstand und wiederaufnehmbarer Plan | geprueft | vorhandene Aenderungen erhalten |
| A1 | Beobachtungsprojektion und autoritative Commander-Bruecke | geprueft | keine versteckte Wahrheit, reine GETs, sichere Referenzen |
| A2 | Begrenzter LAN-HTTP-Server und lokale Optionen | geprueft | Kopplung, Freigabe, Widerruf, Shutdown, Host/Origin-Limits |
| A3 | Responsive Browserlage | geprueft | Chromium-Vertrag bei 1920/2560/3840 und 390 CSS-Pixeln |
| A4 | Annotationen, Zielvorschlag/Bestaetigung und Alarme | geprueft | echte Loopback-HTTP-Integration plus Browservertraege |
| A5 | Version/Anleitungen/Ressourcen/Tests/Git-Vorbereitung | geprueft | 1648 Tests, Smoke/Katalog/Build, installiertes Wheel geprueft |
| PAUSE | Uebergabe schreiben und stoppen | erreicht | docs/resume.md nennt naechsten kleinsten Schritt |
| B | Sonarhoerbild und Sonarlage auf Bruecke | nach Pause | hoerbare Filter, A/B, Filterstatus, korrekte Fixpublikation |
| C | Tastenkontrast, Wertefarben, Maus und Stationsabnahme | nach B | alle acht Stationen und sechs Sonarseiten |
| D | Batterie-/AIP-Endurance | spaeter | Energiebilanz, Reserven, reale Schnorcheltiefe, Save-Fortsetzung |
| E | Erweiterte synthetische Schallausbreitung | spaeter | begrenzte Strahlen/Reflexionen, Physik-/Akustik-API getrennt |
| F | Grundberuehrung und lokalisierte Schaeden | spaeter | gesweepter Kielkontakt, Stranden, Pumpen/Lecks, Migration |
| G | Crew-MessageBox: Vorschlaege annehmen/ablehnen, nicht blockierend | offen | Live-Box, Key-/Maus-Vertrag, i18n, keine Save-Aenderung |
| H | uConsole-Audio knackt (Puffer/Last) | umgesetzt | Puffer 1024 ms, Diagnose-Log; uConsole-Dauerlauf abwarten |
| I | Bridge Lookout: 2D-Topdown im Commander-Browser | offen | Lookout-Tab in allen Groessen, nur Snapshot-Beobachtungen |
| J | Eloka/ESM: neue 9. Station, Radartyp-Auswertung | offen | K_9, Katalog-Radarfelder, 9-Stationen-Tests/Doku, Save v8 |
| K | Web: Ein-Bildschirm, Anleitung EN/DE, Kontakt-DB mit Bildern | offen | kein vertikales Scrollen 390-3840 px EN/DE, Asset-Tests |
| L | Kontakt-Profile: Real-Basis, Schema v2, Keys stabil | offen | Validator v1+v2, Smoke-Anzahl, deterministischer Fingerprint |

## A1-A4 Architektur und Grenzen

Der Spielthread erzeugt begrenzte oeffentliche Snapshots und wendet erlaubte
Anfragen an. HTTP-Handler kennen kein Game und rufen kein Pygame auf. Browser
pollt etwa zweimal pro Sekunde; statische Kartendaten werden pro Welt abgelegt.
Keine Video-/Sonarstreamingfunktion, kein CDN, keine benoetigte Node-Toolchain.

Snapshots enthalten eigene Lage/Bereitschaft, bekannte Missionsinformationen,
oeffentliche Tracks mit getrenntem Mess-/Fixalter, Annotationen, Zielvorschlag
und Alarme. Unbekannt bleibt null; reine Peilungen erhalten keinen erfundenen Ort.
Kein Save-Dump, Seed, RNG, versteckte Einheitenliste oder rohe Entity-ID.

Ein gekoppelter Commander, kurzlebiger Sitzungsschluessel, lokale Freigabe.
Host-/Origin-Pruefung, feste Routen, JSON-Schema, Request-/Queue-/Worker-Limits.
Nur vertrauenswuerdiges LAN: HTTP verschluesselt nicht, kein Internetbetrieb.
Reset/erfolgreiches Laden erzeugt eine neue Sitzung. Pause/Administration/Editor
sperrt Aenderungen. Alte, doppelte, widerspruechliche Anfragen werden abgewiesen.

Zielvorschlag und Besatzungsziel sind sichtbar verschieden. Annahme prueft die
aktuelle Beobachtung erneut. Tonalarme brauchen eine Browserbenutzergeste und
werden nach Wiederverbindung nicht als historischer Stapel wiederholt.

## B-C Nach Wiederaufnahme

- Sonar zeigt dauerhaft Audioverfuegbarkeit, Breitband/gefiltert, Gain, Band,
  Notch und Lautstaerke. Aktuell macht D den Band-/Notchfilter hoerbar; Gain
  wirkt auch im Breitbandmodus. Anzeigeverarbeitung ist davon getrennt.
- Abhoerband einstellbar, sinnvoller hoerbarer Traegerbandmodus, direkter A/B-
  Vergleich, kurze saubere Filterwechsel. Keine geheime Solo-Entity-Wiedergabe.
- Alle gueltigen beobachteten Sonarfixes auf Bruecke und Commander; Fixquelle,
  Alter und Unsicherheit sichtbar. Keine unsichtbaren klickbaren Marker.
- Strukturierte farbige Tastensegmente: Tasten helles Cyan, Beschreibungen hellgrau,
  Labels gedaempft, Werte heller. Alarm-/NATO-Farben behalten ihre Bedeutung.
- Maus: Kontakt/Marker waehlen, Tabs umschalten, explizite Aktionen und Optionen;
  niemals Waffenstart als Nebeneffekt eines Klicks. Tooltippraeferenz unabhaengig.
- Neu erfassen: acht Stationen, sechs Sonarseiten, belegt/selektiert/veraltet,
  EN/DE, normale/grosse Schrift. Pro Bild Befund und Korrekturstatus festhalten.

## D-F Modellentscheidungen

Batterie/AIP: strukturierte ausdruecklich fiktive Profile mit kWh/kW, Hotel- und
fahrtabhaengiger Last, begrenzter Generatorleistung, Reaktantenvorrat, Reserve-
hysterese und gespeicherten Uebergangsphasen. Keine Dieselaufladung vor tatsaechlich
erreichter Schnorcheltiefe. Funkbetrieb getrennt. Klassennamen sind keine Quelle
fuer verifizierte Leistungsdaten; aktuelle Antriebszuordnungen vorher pruefen.

Akustik: gemeinsames synthetisches Schallgeschwindigkeitsprofil samt BT-Messung,
frequenzabhaengige Daempfung/Laufzeit, danach begrenzte Strahlen, Brechung,
Oberflaechen-/Bodenreflexionen und Nachhall. Eine vollstaendige breitbandige
3-D-Wellenloesung ueber 500 NM ist auf der uConsole nicht ausfuehrbar. Physische
Terrainkollision darf nicht von akustischer Mehrwegerreichbarkeit abhaengen.
Ein spaeteres Senden/Auftreffen/Rueckkehr-Ereignismodell ersetzt die jetzige
eingefrorene Echoannahme nur mit expliziter Kompatibilitaetsentscheidung.

Grundberuehrung: zuerst geeignete synthetische Flachwassergrundlage (aktuell
35-m-Mindesttiefe generierter Wasserzellen beachten), fiktive Rumpfparameter,
gesweepter Kielkontakt/erste sichere Position, Streifen/Aufsetzen/Stranden.
Lokaler Schaden nach Kontaktlage und dissipierter Energie, keine Wiederholung
des vollen Aufpralls pro Frame. Spaeter Wasser-/Leckvolumina, Pumpen, Abdichten,
getrennte hydraulische Verbindungen; bestehende Brandnachbarschaft ist kein
hydraulisches Modell. Saveversion erst bei konkreter Semantikaenderung
entscheiden.

## G-L Umsetzung vom 2026-09-07

Reihenfolge und Abhaengigkeiten: G und H sind unabhaengig und koennen zuerst
gehen. L ist Datengrundlage fuer J (Radarfelder) und K3 (Kontakt-DB und
Bilder). K1 (Ein-Bildschirm-Layout/Tabs) ist Voraussetzung fuer I sowie
K2/K3. Vorschlag: H, G, L, K1, K2, I, J, K3.

### G Crew-MessageBox an der uConsole

- Feste, nicht blockierende MessageBox fuer ausstehende Commander-
  Vorschlaege (Ziel und Navigation): annehmen oder ablehnen. Simulation und
  Stationsbedienung laufen weiter; die Box ist kein Admin-Overlay und nimmt
  keinen globalen Eingabe-Owner.
- Ausloeser: bestehender pending-Vorschlag (bridge.pump,
  src/commander/local.py:79-99). Statt des 3s-Flashes bleibt die Box
  sichtbar, bis entschieden, verwiesen (Lease, Widerruf, Bridge-Down) oder
  per Esc ohne Entscheidung geschlossen ist.
- Aktionen rufen bridge.accept_proposal/reject_proposal bzw.
  accept/reject_navigation auf (bridge.py:668-706); Annahme prueft die
  aktuelle Beobachtung erneut. Keine neuen Save-Felder: Vorschlaege sind
  keine Save-Felder.
- Eingabe: explizite Annahme-/Ablehnungstasten und Maus (waehlen, dann
  bestaetigen; kein versehentliches Akzeptieren durch Einzelnklick).
  Box-Keys werden vor Stations-Keys abgefangen; Key-Repeat bleibt ignoriert;
  Held-Controls clearen bei Uebergaben wie bisher.
- i18n: neue Schluessel (commander.confirm.*), exakte EN/DE-Paritaet.
- Tests: Statusuebergaenge (pending, accepted, rejected, expired, closed),
  Eingabepraezedenz ohne Key-Leck, deterministische Abfolge, EN/DE und
  beide Schriftgroessen.
- Abnahme: Box bei Ziel- und Navigationsvorschlag live nutzbar, F9-Overlay
  unveraendert, keine Save-Aenderung.

### H uConsole-Audio knackt

- Defekt: Knacken und Ploppen im Audio an der uConsole (Low-Power-Ziel).
- Verdachtsstellen (Ist-Zustand): fester Mixer-Puffer buffer=512 ms
  (src/core/game.py:99, src/audio/engine.py:61); Blocklaenge 0.25 s gleich
  Cadence 0.25 s ohne Reserve; Gesamtpuffer rund 0.76 s (512 ms Device plus
  ein gequeued Block). Pro 0.25-s-Tick auf dem Hauptthread: Receiver-DSP
  (bis 128 Quellen mal 32 Tonale, Bandrauschen via rfft, 8192-Punkt-Analyse
  plus DEMON in float64), Motorblock-Synthese, Resampling 4096 auf
  Mixer-Rate (np.interp), Limiter, int16, make_sound-Kopie.
- Vorgehen: 1) Messung auf der uConsole: Framedauer um den 0.25-s-Tick,
  engine_dropped_blocks und Receiver-Evictions, Korrelation mit den
  Knackern. 2) Massnahmen nach Messung, kombinierbar: groesserer
  Mixer-Puffer (Latenz gegen Stabilitaet abwaegen), Vorabberechnung und
  Kappung der statischen DSP-Arbeit (float32, Quellenbegrenzung,
  Noise-Blocke cachen und nur bei Parameterwechsel neu erzeugen),
  Audio-Update frueher im _update_sim() aufrufen.
- Keine Simulationsaenderung; Audio bleibt optional; Pfade ohne Audio
  bleiben unveraendert. Bei geaenderter Pufferkonstante mitanpassen:
  test_mixer_preinit (test_game_integration.py) und Buffer-Kwargs-
  Assertions (test_audio.py).
- Abnahme: kein Knacken bei dauerhaftem Motor, Sonar und Alarmton auf der
  uConsole (Dauerpruefung), headless-Suite gruen.

#### H Implementierung (abgeschlossen 2026-09-07)

- `AUDIO_MIXER_BUFFER_MS = 1024` in src/core/config.py; verwendet in
  game.py (pre_init) und engine.py (Fallback-Init). 1024 ms Puffer plus
  ein 0.25-s-Block ergeben ca. 1.27 s Gesamtpuffer – ausreichend Reserve
  für uConsole-Framedauern über 0.25 s.
- `evicted_blocks`-Counter in AcousticReceiver (receiver.py): zahlt Block-
  Evidenzen (Deque-Vollstand) mit, sichtbar im Debug-Log.
- `AudioEngine.debug_log(dt, receiver)`: opt-in über `U_JAGD_AUDIO_DEBUG=1`.
  Schreibt ca. 1×/s (Wall-Time) eine Zeile nach `~/.u-jagd/audio_debug.log`:
  engine_drops, underruns, sonar_drops, alert_drops, evictions, rate, ch.
  Kein No-Op-Kosten ohne Env-Variable (ein Bool-Check pro Frame).
- Keine Simulations- oder RNG-Änderung. Keine Save-Auswirkungen.
- Tests: buffer-Assertions in test_game_integration.py und test_audio.py
  auf `config.AUDIO_MIXER_BUFFER_MS` aktualisiert; neuer Test
  `test_audio_debug_log_is_opt_in_and_throttled`.
- Eskalation (falls uConsole immer noch knackt): Puffer auf 2048 ms,
  float32-DSP im Receiver, Noise-Block-Cache bei Parameterwechsel,
  Quellenbegrenzung (MAX_SOURCES < 128).


### I Bridge Lookout (2D-Topdown)

- Neue Ansicht "Lookout" als Tab im Operations-View der Webkonsole:
  2D-Topdown von oben (Bruecken-Optik ohne 3D).
- Inhalt: eigenes Schiff zentral als Silhouette, gedreht nach Kurs; Seekarte
  aus dem bestehenden Chart-Snapshot (pro Revision gecachet);
  beobachtete Kontakte (positionierte Fixe als Punkte, reine Peilungen als
  Kantenmarkierungen - wie die Kartenansicht); Reichweitenringe,
  Kurs-Skala, Eigenbewegungsvektor; Seeklasse 0-6 und Tag/Nacht
  (bestehendes clock.world).
- Neue Snapshot-Felder (Allowlist, bridge.py): sea_state (Integer 0-6, aus
  game.world.sea_state). Sichtweite ist aktuell nicht modelliert.
  validateState in app.js und Redaktions-Tests entsprechend erweitern.
- Keine neue Simulation, keine Entity-Referenzen, keine versteckte
  Wahrheit: ausschliesslich erlaubte Beobachtungen aus dem Snapshot.
- UI: i18n-Keys EN/DE, nur Canvas, CSP-konform, keine neuen externen
  Assets.
- Abnahme: Lookout passt in die Ein-Bildschirm-Ansicht (K1) bei allen
  Chromium-Testgroessen EN/DE; neue Snapshot-Felder in Unit- und
  Redaktionstests.

### J Eloka (ESM-Zentrale, neue 9. Station)

- Neue Station 9 "Eloka" (ESM-Zentrale, Taste K_9): Radarstrahlen
  (ESM-Pulse) und Radartypen auswerten, Klassifizierung und
  Kontaktbestimmung.
- Datenbasis: ESM- und Emittier-Felder aus L (Kontaktkatalog v2):
  Radartyp-Bezeichnung, Frequenzband (min/max in Hz), PRF-Band,
  Modulationsart pro Plattform.
- Simulation: ESM-Beobachtung (aktuell nur Peilung plus Ungenauigkeit,
  game._update_air_picture) erzaehlt im Track beobachtete Pulsmerkmale
  (Frequenzschaetzung, PRF-Schaetzung, Peilung, Peilgenauigkeit).
  Radartyp-Kandidaten sind Katalogreferenzen, keine Entity-Identitaeten;
  UI und Auswertung konsumieren nur Track- und Beobachtungsdaten
  (Beobachtungsgrenze bleibt erhalten).
- Station-UI: Peilbild (ESM ist peilungsbasiert; Position nur aus
  Kreuzpeilung oder anderer Domain), Emittierliste mit Kandidaten-
  Klassifizierung, manuelle Radartyp-Zuordnung pro Track (Operatoren-
  Annotation wie Klassifizierung und Zugehoerigkeit, nicht abgeleitete
  Wahrheit), Korrelation mit bestehenden Radar- und Sonar-Tracks.
- Stationsverdrahtung: station.py (9. Enum-Mitglied), K_9 in game.py,
  commands.py (STATION_PAGES, Command-Hints), DISPLAY_KEYS in i18n.py,
  EN/DE-Keys, Draw-Dispatch, Stations-Keys und Joystick, Input-Clear bei
  Stationswechsel, Schadensmodell-Station (Ja/Nein beim Start entscheiden),
  test_stations.py (K_1 bis K_9) und test_tooltips.py.
- Save v8: Stationsindex ist serialisiert; Ladegrenzen 1-9 pruefen, alte
  Saves (Index bis 8) unveraendert; keine neue Save-Version.
  Determinismus: keine neuen RNG-Ziehungen oder Reihenfolgeaenderungen.
- Doku: GDD-Stationstabelle, help.py und help.*-Keys,
  workstation-review.md (acht auf neun Stationen), Abnahme von Paket C
  ("alle acht Stationen") entsprechend aktualisieren.
- Abnahme: K_9 erreichbar, ESM-Auswertung in EN/DE, Katalogfelder valide,
  9-Stationen-Tests und Doku konsistent, Save/Load mit Stationsindex 9.

### K Webkonsole (Ein-Bildschirm, Anleitung, Kontakt-DB)

- K1 Ein-Bildschirm-Layout: die Seite scrollt heute vertikal (Masthead,
  Mission, 72vh-Chart, Support-Grid und Footer ueber 100svh). Neuaufbau:
  Views als Tabs (Operations, Lookout, Anleitung, Kontakte);
  nur Panel-interne Scrollbereiche (overflow:auto).
  tests/test_commander_layout.py erweitern: Document-Hoehe bis zur
  Viewport-Hoehe (kein vertikales Scrollen) bei allen Chromium-
  Testgroessen (390 CSS px bis 3840 px) in EN und DE.
- K2 Anleitung: komplette, detaillierte Bedienungsanleitung im Webkonsole-
  Tab, je Sprache EN/DE; nur commander.web.*-i18n-Schluessel mit exakter
  Paritaet, kein JSON in data/commander (Asset-Test). Inhalt:
  Kopplung und Verbindung, Freigaben, Ansichten,
  Beobachtungs- und Klassifizierungs-Workflow, Ziel- und
  Navigationsvorschlag, Eloka (nach J), EMCON- und Sicherheitshinweise.
  Sektionen mit interner Navigation; kein vertikales Dokument-Scrollen.
- K3 Kontakt-Datenbank: Referenzdatenbank im Tab "Kontakte" fuer Analyse
  und Kontaktbestimmung. Pro Profil: Name, Kategorie, Geschwindigkeit,
  Crew, Verdrangung, Rolle; Sonar-Fingerprint (Blattzahlen, RPM-Band,
  Tonalband, Kavitation, Breitband, Sekundaertonale, Signaturentext,
  LOFAR in zwei Fahrzustanden); Radar- und Emittier-Daten aus L (vor L:
  "keine Daten").
- Analyse- und Silhouetten-Bilder: je Profil ein statisches Sonar-
  Analyse-Bild (LOFAR/Spektrum) und eine Silhouette (einfache Umriss-
  Zeichnung aus dimensions Laenge/Breite). Programmatisch und
  deterministisch erzeugt (neues Tool tools/gen_contact_analysis_images.py,
  fester Seed und Groesse, Hash-Manifest), aus dem eigenen Akustikblock und
  den Dimensionsdaten; keine WaveOps-Bilder. Provenanz- und
  Reproduzierbarkeitsregeln wie real_sectors.json.gz. Auslieferung:
  pyproject data.commander-Glob um *.png erweitern, exakt gemappte,
  erlaubte Routen (kein Pfad-Traversal), CSP img-src 'self'.
- Datenquelle: paketierter Katalog (data/contacts SSoT) via
  src/data/catalog.py; keine Simulationsojekte, keine Live-Entity-Daten.
- Abnahme: kein vertikales Scrollen in allen Testgroessen und Sprachen,
  Anleitung komplett in EN/DE, DB mit Fingerprints und beiden
  Bildtypen pro Profil, Asset-/CSP-/Layout-Tests erweitert und gruen.

### L Kontakt-Profile (Real-Basis, Schema v2)

- Ziel: alle Katalog-Eintraege (23 U-Boote, 25 Kriegsschiffe, 55 Zivile,
  2 Flugzeuge, 3 Tiere, 3 Torpedos, 1 Dekoy) auf Basis offener
  Real-Plattform-Daten neu befuellen. Werte bleiben dokumentierte
  Spiel-Modellannahmen (Disclaimer in docs/contacts-db.md); keine
  WaveOps-/MNW-Texte, -Bilder oder -Layouts im Repo.
- Keys stabil: keine Umbenennungen; Saves und User-Missionen
  referenzieren ueber signature_key (game.py:3388, 3417, 3949).
  Archetypen diesel_alt, aip_modern und ssn sind Szenario-Pools
  (config.py) und bleiben generische Archetypen. Fehlende
  Real-Plattformen (z.B. Nimitz, Type 052D, Type 901) als neue Keys an
  das Ende der Serie (warship_26, warship_27, ...).
- Schema Version 2: Dokumentversion 2; Loader und Validator akzeptieren v1
  und v2 (v1 ohne neue Felder bleibt valide, externe Kataloge moeglich);
  neue Felder sind bei v2 erlaubt und wenn vorhanden, strikt validiert.
- Neue optionale Top-Level-Blocke (nur v2):
  - dimensions: displacement_tons, length_m, beam_m, draft_m
  - crew (Integer), role (String)
  - machinery: engine_type, engine_rpm, shafts, blades_per_shaft,
    shaft_rpm_cruise, shaft_rpm_max
  - sensors_and_armament: radar, sonar, guns, missiles, close_in, decoys,
    ew_suite (Strings; "None" erlaubt)
- Akustik-Block (v2): lofar_cruise_hz und lofar_high_hz (Tonallinien in
  zwei Fahrzustanden); bestehende Felder bleiben, LOFAR-Listen ergaenzen
  das Modell.
- Runtime-Verbrauch (selektiv): speed_kn auf Cruise/Max neu befuellen;
  shaft_rpm_cruise/max auf rpm_range und blades_per_shaft auf blades
  ueberfuehren; LOFAR-Listen in Sonar-Synthese und rank_signatures()
  je nach Zielgeschwindigkeit auswahlen (interpoliert);
  sensors_and_armament.radar fuer ESM/Eloka (J). Dimensions, Crew, Rolle
  und Bewaffnungsdetails sind Referenzdaten fuer K2/K3 ohne
  Simulationswirkung in diesem Meilenstein (Validierung impliziert keine
  Runtime-Unterstuetzung).
- Validator und Doku: tools/gen_contacts.py auf v2 erweitern,
  docs/contacts-db.md aktualisieren (Struktur, Felder, Beispiele).
- Fingerprint: neue Felder deterministisch in roll_from_seed()
  (src/data/fingerprint.py) aufnehmen; keine neue RNG-Ziehung-Reihenfolge.
- Tests: test_contacts_catalog.py Profil-Anzahl aktualisieren (aktuell
  106), v2-Schema und v1-Kompatibilitaet, LOFAR-2-Zustaende in Synthese
  und Klassifizierung, Save/Load mit unveraenderter signature_key;
  Smoke- und Katalog-Checks aktualisieren.
- Abnahme: alle bestehenden Keys erhalten (keine Save- oder
  Mission-Breaks), Validator akzeptiert v1 und v2, Fingerprint
  deterministisch, 2-Zustands-LOFAR in Tests verifiziert.

## Verifikation und Unterbrechung
Commander-Meilenstein abgeschlossen am 2026-09-07. Letzte Gesamtsuite:
1648 passed in 278.28s, einschliesslich Chromium-Vertraegen. Smoke SMOKE-OK,
106 Akustikprofile valide, sdist/Wheel 0.1.6 erfolgreich gebaut. Separat
installiertes Wheel ausserhalb des Quellbaums: Webressourcen, echte Loopback-
Kopplung im DDDLLL-Format und Beobachtungs-API erfolgreich geprueft.
git diff --check sauber; keine GitHub-PATs in Projektdateien gefunden.

Browserbilder mit echtem Game/Bridge/Server ueber Loopback visuell geprueft:
docs/screenshots/commander-overview.png und commander-wide.png; Methode und
Grenzen in commander-captures.md daneben. Lokale Verwaltung ohne aktiven
Zugangscode in commander-options.png. Kein realer Zwei-PC-/uConsole-Hardwaretest.

Die vorausgehenden Reviewkorrekturen und der Commander-Meilenstein liegen noch
uncommittet zusammen auf main. Kein Commit, Push oder Release-Upload in diesem
Meilenstein ausgefuehrt. Vor Veroeffentlichung Diff/Dateiauswahl gezielt pruefen
und sichere lokale GitHub-Authentifizierung verwenden. Keine Zugangsdaten in
diesen Plan, Anleitungen oder Commitnachrichten uebernehmen.

Jedes Paket fuehrt Quellen/Annahmen, Dateien, Tests und offene Fehler auf.
Gesamtabnahme: pytest, tools/gen_contacts.py --check, tools/smoke_full.py,
python -m build, Installation ausserhalb des Quellbaums, Netzwerk-/Browsertests.
Keine Hardware-/Zwei-PC-Abnahme behaupten, wenn nur headless getestet wurde.

Pakete G-L tragen eigene Abnahmen: uConsole-Audio-Dauerpruefung (H),
Ein-Bildschirm-Assertions im Chromium-Layout (K1), 9-Stationen-Vertraege (J),
deterministische Analyse-/Silhouetten-Bilder (K3, L). Neue Daten-/
Katalogaenderungen (L) verlangen aktualisierte Smoke-/Katalog-Checks und
einen neuen Build-Verifizierungsschritt.

Vor Pause docs/resume.md aktualisieren: Branch/Commit, uncommittete Dateien,
letzter Teststand, Startanweisung, offene Risiken, naechster kleiner Schritt.
Keine Zugangscodes oder Tokens dokumentieren. Git-Push nur nach tatsaechlicher
Ausfuehrung als erfolgt markieren; bestehende Reviewarbeit nicht ueberschreiben.
