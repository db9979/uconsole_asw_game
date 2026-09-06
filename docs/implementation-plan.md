# Umsetzungsplan U-Jagd

## Aktueller Ausbau: strenge Simulation auf uConsole

Die folgende Roadmap konkretisiert die historischen Phasen weiter unten.
Zielplattform ist die uConsole; die Arbeitsoberflaeche rendert nativ in
1280x720 und wird im Vollbild auf die Displayflaeche skaliert. Die laufende
Simulation verwendet weiterhin das alte Zeitmodell; das aktuelle Speicherformat
ist v7 und enthaelt neben Kontakt-DB, Fingerprints und `warships`-Block einen
kanonischen Snapshot der vollstaendigen Weltgeometrie.

### Festgelegte Entscheidungen

- Stationen 1-8: Bruecke, Sonar, Waffen, Schaden, OPZ, Funk, Maschine, Helikopter.
- Verwaltung pausiert; bereits gesetzte manuelle/Fokus-Pause bleibt erhalten.
- Keine operativen Befehle in Pause. U/V-Zahleneingaben bleiben im Livebetrieb.
- Save v7 restauriert eingebettete Welt-Snapshots generatorunabhaengig. Der
  weiter unten geplante robuste Import aelterer Saves bleibt davon getrennt;
  Originaldateien bleiben unveraendert.
- Der Standard-Weltmodus waehlt per Seed einen von genau 128 realen,
  vorvalidierten 500-NM-Sektoren. Die feste stilisierte Karte bleibt als
  Legacy-Option verfuegbar.
- Reale geografische, Laender- und Militaerstuetzpunktnamen bleiben erhalten;
  Gameplay-Rollen sind unabhaengig vergebene fiktionale Uebungsrollen.
  Bathymetrie ist synthetisch und nicht navigationstauglich.
- Geografische Karte und Radar-PPI verwenden dunkelblaue Flaechen. Der eigene
  HSP-5 wird als freundliches NATO-aehnliches Luftsymbol angezeigt.
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
- Esc schliesst die aktive Eingabe/Ansicht oder oeffnet den Beenden-Dialog;
  Fenster-Schliessen fragt ebenfalls nach. Q/E sind ausschliesslich Kartenzoom
  auf Bruecke, Waffen und Helikopter, nicht Beenden.
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
- Ereignis-Feed-Hinweise sind stationsbezogen und enthalten nur am sichtbaren
  Arbeitsplatz gueltige Befehle.
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
  Breitband-Skalierung), seit Save v4 und weiterhin in Save v7 persistiert.
- Gemeinsame Empfangssignalkette: Receiver mischt pro-Quellen-Breitband und
  Eigen-Kavitation bandlimitiert (80-380 Hz); ohne Daten bit-identisch.
- Feindtorpedos sind im passiven Sonar hoerbar (Subharmonische + Tonales,
  `kind="torpedo"`); Sonarkontakte kennen jetzt sub/surface/torpedo/decoy/animal.
- KAMPFSCHIFF als Spieler-Klasse: feindliche Kriegsschiffe (loitern um
  feindliche Basis, ASM-Salven < 35 NM), Radar-/ESM-Tracks, versenkbare
  Torpedo-Ziele; der mit v4 eingefuehrte `warships`-Block und die Torpedo-IDs
  sind im aktuellen Save v7 enthalten.
- Zivilschiffe sind jetzt auch passive Sonarkontakte (GDD 14 angepasst).
- Tests: test_contacts_catalog.py, test_fingerprint.py, test_warship.py;
  278 Tests + Smoke-Test bestanden.

### Reale Sektoren, Kartendarstellung und Persistenz (Implementiert)

- `data/coastlines/real_sectors.json.gz` enthaelt genau 128 reale 500-NM-
  Kuestensektoren; die Seedabbildung ist stabil und deckt alle 128 Eintraege ab.
- Natural Earth 1:50m Admin 0 Countries v5.1.1 und ein fixierter Wikidata-CC0-
  Snapshot liefern Kuesten, Laender- und Stuetzpunktnamen. Exakte Provenienz,
  Pruefsummen, Transformationen und der Ausschluss einer Billigung stehen in
  `THIRD_PARTY_NOTICES.md`.
- Sektorwahl und synthetische 17x17-Bathymetrie sind deterministisch. Reale
  Nationen bestimmen keine freundliche oder feindliche Gameplay-Rolle.
- Save v7 bettet `Coastline.to_dict()` mit Geometrie, Stuetzpunkten,
  Bathymetrie und Provenienzmetadaten ein; Laden restauriert diesen Snapshot
  ohne erneute Generierung.
- Die feste stilisierte `region.json` ist weiterhin im Startmenue waehlbar.
- Native 1280x720-Oberflaeche; dunkelblaue geografische Karten/PPI;
  freundliches NATO-aehnliches Luftsymbol fuer den eigenen HSP-5.
- OPZ-Darstellungsbereiche: 10/20/40/80/120 NM. Nominelle Radarreichweiten:
  30 NM See und 100 NM Luft, getrennt von der Darstellungsskala.

### Ausstehende Lieferungen

1. Zeitvertrag, fester Tick/Akkumulator, Bewegung aller Entitaeten und neues
   versioniertes Speicher-/Migrationsschema gemeinsam vorbereiten.
2. Beobachtungsmodell, Kontaktalter, kausale Pingereignisse und konsistente
   Ziel-/Kontakt-IDs; Feuerleitung und KI auf begrenztes Wissen umstellen.
3. Quellen fuer alle 100 Kernplattformen erfassen und dokumentieren;
   gemeinsame Empfangssignalkette aus Lieferung 2 vertiefen.
4. Vollstaendige DEMON/TMA-Anzeige und durchsuchbare Akustikbibliothek mit
   manuellen Hypothesen und synthetischen Hoerbeispielen.
5. Robuster Legacy-Snapshot-Import, transaktionales Laden auch strukturell
   beschaedigter Dateien, vollstaendige deterministische Fortsetzung und
   Missionsbalance. Save v7-Welt-Snapshots sind generatorunabhaengig; v6-Snapshots bleiben lauffaehig.
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
