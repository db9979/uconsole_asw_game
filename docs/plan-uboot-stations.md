# Plan: Boots-Stationen ausbauen (Maschine, Mast & ESM, Tauchzellen, Leckwehr)

Stand 2026-09-27, Basis `main` 4b2ad15 (1.3.0, Save v16). Auftrag von Dominik
nach der Hardware-Abnahme: Stationen 4 und 5 der Bootsseite im Web ausbauen,
Schadensabwehr, ESM für Kartierung und Auswertung, Vorräte (Treibstoff,
Sauerstoff), Tauchzellen und weitere Bootsinformationen.

Dieser Plan beschreibt Ziele und Reihenfolge. Er ist kein Vertrag: jede Stufe
wird mit Tests, Handbuch (EN/DE), `help.py` und i18n-Parität geliefert, wie
`AGENTS.md` es verlangt.

## Ist-Zustand

| Thema | Modelliert heute | uConsole zeigt | Browser zeigt |
|---|---|---|---|
| Energie | Batterie und AIP in kWh, Phasen, Last aus Hotel- und Fahrlast, Laden nur beim Schnorcheln (`src/enemies/endurance.py`); Katalogwerte in `data/contacts/subs.json` (`endurance.*`) | Batterie in %, Phase als Rohtext | Batterie in %, Phase |
| Treibstoff | nicht modelliert (Schnorcheln lädt unbegrenzt); Treibstoff gibt es nur für die Fregatte (`src/ship/ship.py`) | – | – |
| Luft (O2/CO2) | nicht modelliert | – | – |
| Tauchzellen, Trimm, Pressluft | nicht modelliert; Tiefe ist rein kinematisch; Anblasen ist ein einziges Ja/Nein (`blow_available`) | „Anblasen verfügbar“ | „Anblasen verfügbar“ |
| Schaden | ein Skalar `Sub.damage` 0–100: Treffer, Ermüdung unter Testtiefe, Wassereinbruch ab 30 %, Sonarraum fällt ab 90 % aus | Schaden in % | Schaden in % |
| ESM | nur Peilung, Qualität, Alter (max. 16), nur mit Mast oben (`src/sensors/platform.py`, `src/core/opfor.py`) | Peilrose, Liste | Peilrose, Liste; kein Kartenbezug |

Wiederverwendbar von der Fregatte: Abteilungs- und Trupp-Logik
(`src/ship/damage.py`, Station 4 der Fregatte), ESM-Auswertung mit Frequenz,
PRF, Modulation und Bibliotheksabgleich (`src/sensors/esm.py`,
`src/ui/stations/eloka.py`, `_eloka()` in `src/commander/projections.py`),
Treibstoffbuchhaltung (`src/ship/ship.py`).

## Stufen

### Stufe A: Maschine (Station 4) mit Energie und Vorräten

- Energiebilanz sichtbar: Last und Erzeugung in kW, Restzeit bis Batterie
  leer oder voll bei aktueller Fahrt, Laderate beim Schnorcheln, AIP-Vorrat
  (die Werte rechnet `EnergyFlow` schon, sie werden nur nicht gezeigt).
- Ausdauer-Rechner: „bei X kn reicht die Batterie bis HH:MM“.
- Neu modelliert: Dieseltreibstoff (Verbrauch beim Schnorcheln und
  Aufgetauchtfahren), Luft (O2 sinkt, CO2 steigt mit der Tauchzeit;
  Absorberpatronen und O2-Kerzen als Vorrat; Lüften beim Schnorcheln).
  Folgen: ab CO2 über etwa 3 % sinkt die Crew-Leistung (langsamere
  Reaktion), ab etwa 5 % muss das Boot lüften.
- Befehle: Lüften, O2 zusetzen, Absorber wechseln, Laderate wählen.
- Web: großflächige Maschinenseite für den PC; uConsole: kompakte Zeilen auf
  der bestehenden Maschinenseite.

### Stufe B: Mast & ESM (Station 5) für Kartierung und Auswertung

- Das Boot bekommt echte Signalmerkmale (Band, PRF, Scan, Stärke) über
  denselben Signalweg wie die Fregatte (`scan_for_signals` mit dem Boot als
  Beobachter), nie die wahre Identität oder Position des Senders.
- Emitterliste mit Einstufung durch die Crew (Annotation, keine Wahrheit)
  und Bibliotheksvorschlag wie an der ELOKA der Fregatte.
- Kartierung: Peilstrahlen auf der Bootskarte und im Plot, Peilverlauf über
  mehrere Mastperioden, Kreuzpeilung aus eigener Bewegung mit Fehlerellipse,
  in den Plot übernehmbar.
- Auswertung: Stärketrend, Warnung „Radar erfasst Mast“, empfohlene
  Mastzeit aus dem Seegang (nutzt den neuen Wetterblock „Boot“).

### Stufe C: Tauchzellen, Trimm und Pressluft

- Haupt-, Regel- und Trimmzellen mit Füllstand; Pressluftvorrat (Anblasen
  mehrmals statt einmal, Nachfüllen beim Schnorcheln).
- Trimm ändert sich durch Torpedoabschuss und Wassereinbruch; Pumpen machen
  Lärm.
- Schnittbild des Boots mit Zellen im Web; Zahlen auf der uConsole.

### Stufe D: Schadensabwehr (Leckwehr)

- Fünf bis sechs Abteilungen (Bugraum, Zentrale, Wohnraum, Batterieraum,
  Maschine, Heck) statt eines Schadenswerts.
- Wassereinbruch abhängig von der Tiefe, Brand, Chlorgas bei Seewasser im
  Batterieraum, Stromausfall.
- Zwei Leckwehrtrupps: abdichten, lenzen, löschen, Schotten schließen.
- Folgen für Stationen, Fahrt und Auftrieb (hängt an Stufe C).
- Anfangs als zweite Seite der Station 4, damit keine neue Rolle nötig ist.

### Ausblick (nur Richtung)

Ermüdung der Crew, Wachwechsel, Moral.

## Reihenfolge und Abhängigkeiten

A → B → C → D. A und B sind unabhängig voneinander und bringen am schnellsten
sichtbaren Nutzen. C ist Voraussetzung für die Auftriebsfolgen in D.

## Auswirkungen

- **Spielstand:** A, C und D fügen neuen Bootszustand hinzu (Vorräte, Zellen,
  Abteilungen). Das heißt Save v17; v16-Stände werden wie bisher ohne
  Migration abgewiesen. B braucht nur dann einen Bump, wenn Crew-Einstufungen
  gespeichert werden.
- **Kalibrierung:** Alles, was den Bootslärm (Pumpen, Lüften) oder die
  Höchstfahrt ändert, verschiebt `sonar.passive_nm.*` und `sub.*` in
  `tools/calibrate.py`. Solche Änderungen werden bewusst in
  `tests/calibration/deviations.json` begründet.
- **KI-Boote:** Offene Frage, ob sie dieselben Vorräte bekommen (dann
  schnorcheln sie bei Luft- oder Batteriemangel). Das macht die Jagd
  realistischer, verschiebt aber die Kalibrierung.
- **Beobachtungsgrenze:** Eigener Bootszustand ist erlaubte Wahrheit. ESM
  bleibt Messung: Peilung mit Unsicherheit, geschätzte Entfernung aus
  Signalstärke, Crew-Annotationen; nie `target_id` oder wahre Identität.
- **uConsole-Last:** Neue Projektionen bleiben begrenzt und werden nur bei
  Änderung neu gebaut; jede Stufe endet mit einem Perf-Lauf auf der
  uConsole.

## Entscheidungen für Dominik

1. Umfang A bis D so in Ordnung?
2. Save v17 für neuen Bootszustand (alte Stände laden danach nicht)?
3. Bekommen KI-Boote dieselben Vorräte?
4. Leckwehr zunächst als Seite von Station 4 oder gleich als eigene
   Browserrolle?
5. Reihenfolge A → B → C → D?

## Stufe E und weitere Punkte (Stand 2026-09-28, App 1.3.1)

Erledigt:

- **Funkraum (7. Bootsstation, Save v22):** Rundspruch der Führung alle
  10 Minuten mit Feindlagemeldung, Lagemeldung per KW (die Fregatte kann
  peilen), Funktagebuch; uConsole Taste 7, Browser-Rolle `uboot_radio`.
- **Luftfahrzeugradare im Boots-ESM:** Katalog-Emitter
  `emitter.own_asset.helicopter.radar` und `emitter.own_asset.mpa.radar`;
  der Hubschrauber strahlt im Flug (nicht beim Tauchen), das MPA nur mit
  eingeschaltetem Radar.

Offen, in dieser Reihenfolge (Dominik, 2026-09-28: "ja nehme das in den
plan mit auf und setzte das auch um"):

1. ~~**KI-Jäger**~~ erledigt in 1.3.4 (`src/core/hunter.py`): Fregatte,
   Hubschrauber und MPA jagen das Boot, wenn niemand die Fregatte spielt
   (uConsole auf dem Boot oder Solo-Browser als U-Boot), auf jeder Station,
   die kein Browser hält. Datum aus Sonar und HF/DF; Radarechos, ESM und
   Führungsmeldungen werden noch nicht zugeordnet, kein ASROC.
2. **Bootsmissionen und Bootskampagne:** Durchbruch, Angriff auf einen
   Geleitzug, Aufklärung; baut auf Punkt 1 auf.
3. **Angriffsrechner am Sehrohr:** Lösung aus Peilung, Stadimeter und Lage,
   Vorhaltewinkel für den Torpedo.
4. **Atmosphäre:** Bootsgeräusche, Wasserbomben/Detonationen,
   Druckkörperknacken in der Tiefe, gedämpftes Licht bei Schleichfahrt.
5. **ESM-Bibliothek:** Kandidaten nach Passung (PRF, Modulation) statt
   Katalogreihenfolge sortieren, damit das Hubschrauberradar in der Liste
   bleibt.
