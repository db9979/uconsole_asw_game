# Umsetzungsplan U-Jagd

## Aktueller Ausbau: strenge Simulation auf uConsole

Die folgende Roadmap konkretisiert die historischen Phasen weiter unten.
Zielplattform ist die uConsole; eine native 1280x800-Oberflaeche ist geplant,
aber noch nicht umgesetzt. Die laufende Simulation verwendet weiterhin das
alte Zeitmodell; das Speicherformat ist mit Lieferung 2 auf v4 umgestellt
(Kontakt-DB, Fingerprints, warships-Block).

### Festgelegte Entscheidungen

- Stationen 1-8: Bruecke, Sonar, Waffen, Schaden, OPZ, Funk, Maschine, Helikopter.
- Verwaltung pausiert; bereits gesetzte manuelle/Fokus-Pause bleibt erhalten.
- Keine operativen Befehle in Pause. U/V-Zahleneingaben bleiben im Livebetrieb.
- Alte Saves werden spaeter als Snapshot importiert, nicht mit einer zweiten
  Legacy-Engine ausgefuehrt. Originaldateien bleiben unveraendert.
- Physikalische Simulationszeit und Bedien-/Audiozeit werden getrennt.
- Sensorwissen ist die einzige Grundlage fuer Anzeige, Klassifikation und
  Feuerleitung; Weltwahrheit bleibt der Sensorerzeugung/Trefferwirkung vorbehalten.
- Genau 100 bereinigte Kernplattformen muessen erzeugbar und parametrisiert sein;
  Legacy-Profile, Tiere und Dekoys zaehlen nicht dazu.
- Nicht verifizierte Akustikdaten bleiben gekennzeichnete Modellannahmen.

### Lieferung 1: sichere Bedienung und Pruefbasis

Implementiert:

- pytest und eigenstaendiger Smoke isolieren SAVE_DIR und SAVE_PATH.
- Verwaltungsansichten blockieren Tastatur, Maus und Joystick im Hintergrund.
- Esc schliesst die aktive Ansicht; Esc/Q/Fenster-Schliessen fragen vor dem Ende.
- Beenden hat die sichere Vorauswahl Zurueck; Speichern und beenden ist erst
  nach Missionsstart verfuegbar und beendet nur nach erfolgreichem Schreiben.
- Slots werden mit 1-5 ausgewaehlt und mit Enter bestaetigt. Ueberschreiben
  und Ersetzen einer Mission benoetigen eine weitere Bestaetigung.
- Speichern erfolgt ueber temporaere Datei und atomaren Austausch; ein
  Schreibfehler laesst den alten Spielstand erhalten. Slot-Metadaten werden
  beim Oeffnen statt pro Frame gelesen.
- Fokusverlust und Kontextwechsel loeschen gehaltene Steuerungen und Karten-Drag.
- Stationen 1-8, Tab/Shift+Tab; Schaden: Links/Rechts Raum, Auf/Ab Team,
  Enter zuweisen, Ruecktaste zurueckziehen. Keine stille Verdraengung von Teams.
- U/V-Eingaben bleiben bei ungueltigen Werten korrigierbar, inkl. Ziffernblock.
- Telegraph +/- gilt auch im Sonar, ohne STOP/FLANK-Wrap; I/O Sonar-Gain;
  Z/X oder [/] Zeitraffer; P Pause; Alt+Enter Vollbild.
- Hilfe hat getrennte Seiten fuer globale Tasten, Station und Erklaerungen.
- Verschachtelte Layoutclips schneiden sich; lange Woerter und Textbloecke
  bleiben in ihren Rechtecken.
- Szenario-/Schwierigkeitsauswahl und Dialogreihenfolge nach Missionsende repariert.

Abnahmebefehle (aus dem Projektverzeichnis):

```sh
.venv/bin/pytest -q
.venv/bin/python tools/smoke_full.py
```

Die Tests sind Headless-Pruefungen, kein Nachweis fuer Lesbarkeit, Audioqualitaet
oder FPS auf echter uConsole-Hardware. Der bisherige Smoke ist noch kein
verbindlicher Zehn-Minuten-Dauerlauf. Seine bedingten Fachpruefungen werden in
spaeteren Lieferungen durch zwingende Szenarien ergaenzt.

### Lieferung 2: Kontakt-DB, Fingerprints und Kampfschiff (Implementiert)

- `src/data/catalog.py` ist SSoT fuer alle Plattformprofile (20 neue U-Boot-
  Klassen + 3 Legacy, 25 Kriegsschiffe, 55 Zivile, 2 Flugzeugprofile, 3 Tiere,
  3 Torpedos, 1 Dekoy); Export/Import ueber `data/contacts/*.json`,
  Pruefung mit `tools/gen_contacts.py --check` (Schema: docs/contacts-db.md).
- `src/audio/database.py` ist ein Kompatibilitaets-Shim auf den Katalog.
- Per-Instanz-Fingerprints (`src/data/fingerprint.py`): deterministisch aus
  sensor_seed (Blattzahl, Tacho-Faktor, Ton-Offsets, Kavitations-/
  Breitband-Skalierung), im Save v4 persistiert.
- Gemeinsame Empfangssignalkette: Receiver mischt pro-Quellen-Breitband und
  Eigen-Kavitation bandlimitiert (80-380 Hz); ohne Daten bit-identisch.
- Feindtorpedos sind im passiven Sonar hoerbar (Subharmonische + Tonales,
  `kind="torpedo"`); Sonarkontakte kennen jetzt sub/surface/torpedo/decoy/animal.
- KAMPFSCHIFF als Spieler-Klasse: feindliche Kriegsschiffe (loitern um
  feindliche Basis, ASM-Salven < 35 NM), Radar-/ESM-Tracks, versenkbare
  Torpedo-Ziele, Save/Load v4 inkl. `warships`-Block und Torpedo-IDs.
- Zivilschiffe sind jetzt auch passive Sonarkontakte (GDD 14 angepasst).
- Tests: test_contacts_catalog.py, test_fingerprint.py, test_warship.py;
  278 Tests + Smoke-Test bestanden.

### Ausstehende Lieferungen

1. Zeitvertrag, fester Tick/Akkumulator, Bewegung aller Entitaeten und neues
   versioniertes Speicher-/Migrationsschema gemeinsam vorbereiten.
2. Beobachtungsmodell, Kontaktalter, kausale Pingereignisse und konsistente
   Ziel-/Kontakt-IDs; Feuerleitung und KI auf begrenztes Wissen umstellen.
3. Quellen fuer alle 100 Kernplattformen erfassen und dokumentieren;
   gemeinsame Empfangssignalkette aus Lieferung 2 vertiefen.
4. Native 1280x800-Ansichten, vollstaendige DEMON/TMA-Anzeige und durchsuchbare
   Akustikbibliothek mit manuellen Hypothesen und synthetischen Hoerbeispielen.
5. Snapshot-Import v1-v3, transaktionales Laden auch strukturell beschaedigter
   Dateien, vollstaendige deterministische Fortsetzung, Missionsbalance.
6. Instrumentierung, gezielte Optimierung und uConsole-Hardwareabnahme.

Die bisherigen Wahrheitszugriffe, widerspruechliche Zeitbasis und unvollstaendige
100-Profil-Integration sind durch Lieferung 1 ausdruecklich noch nicht behoben.

### Zusammenarbeit und Freigaben

- Simulation: Zeit/Bewegung/Sensorwissen/Waffen.
- UI: Tastatur, Layout, Stationsansichten und Bibliotheksansicht.
- Akustik/Daten: Profile, Quellen, Empfangsmodell und Analyse.
- QA: Regressionen, Migration, sichere Fixtures und Performance.
- Ein Integrationsverantwortlicher fuer game.py; keine parallelen Edits an
  denselben Orchestrierungs-, Eingabe- oder Speicherfunktionen.

Gemeinsame Datenvertraege zuerst, dann isolierte Module parallel bearbeiten.
Physik/Speicherformat erst gemeinsam freigeben. Performanceziele sind vorlaeufig
30 FPS bei 1x und sichtbares Eingabefeedback unter 100 ms auf echter Hardware;
tragfaehige Zeitrafferstufen werden gemessen, nicht vorausgesetzt.

## Ziel

Ein deterministisches 2D-ASW-Taktikspiel fuer Singleplayer auf der uConsole:
Der Spieler fuehrt eine Fregatte, baut aus unvollstaendigen Sensorinformationen
eine Zielspur auf und trifft Entscheidungen unter Zeit-, ROE- und Schadensdruck.

## Phasen

### A. Technische Basis

- Python/Pygame-Projekt standardisieren.
- Simulationsloop in Domänenschritte zerlegen.
- Save/Load versionieren und laufende Entitaeten einschliessen.
- Deterministische RNG-Streams und Headless-Tests etablieren.

### B. Sensorik

- Passivsonar: Bearing-only mit SNR und Peilfehler.
- Aktivsonar: Reichweite/Tiefe gegen Aufklaerungsrisiko.
- TMA: Spur, Qualitaet und Unsicherheit.
- Sonarbojen, Towed Array, LOFAR, Radar, ESM und HFDF zusammenfuehren.

### C. Gegner-KI

- Reaktive Zustaende ohne Omniscience.
- Taktisches Gedaechtnis fuer Ping, Torpedo, Kontaktalter und Schaden.
- Utility-Auswahl fuer Verstecken, Lauer, Angriff, Dekoy und Flucht.
- Reaktionszeit und typspezifische Doktrin.

### D. Waffen und Schaden

- Drahttorpedo, Suchlauf, Tiefenfehler und Dekoy-Wirkung.
- Trefferzonen statt rein zufaelliger Kompartimente.
- Feuer, Flutung, Reparatur und Funktionsausfall als Kaskade.

### E. Mission und Praesentation

- Missionserfolg, ROE und zivile Risiken klar rueckmelden.
- Balancing-Metriken und deterministische Szenarien.
- CRT/UI, Audio-Feedback und Tutorial-Informationen.

## Bewusste Grenze

Echtes Co-op ist nicht Teil dieser Ausbaustufe. Dafuer werden spaeter ein
autoritativer Simulationsserver, Input-Replikation, Snapshot-Interpolation,
Reconnect und Konfliktloesung benoetigt. Die Simulationssysteme werden deshalb
deterministisch und entkoppelt gehalten, damit diese Erweiterung moeglich bleibt.

## Definition of Done

- Jede Simulationsregel ist als Unit- oder Integration-Test reproduzierbar.
- Headless-Smoke-Test laeuft zehn Minuten ohne Crash.
- Save/Load veraendert keine beobachtbare Spielregel.
- Gegner-KI kann Entscheidungen und Gruende im Debug-Modus ausgeben.
- Keine neue Mechanik ohne klare Spielerinformation und Gegenmassnahme.
