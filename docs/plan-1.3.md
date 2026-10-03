# Umsetzungsplan 1.3 (Detailfassung, Stand 2026-09-26)

Ausgangspunkt: U-Jagd 1.2.0 auf `main` (Commit `4e04c89`), Save v14-only,
Remote-Crew-Protokoll v2. Dieser Plan ist die Arbeitsvorlage für eine
unbeaufsichtigte Umsetzung aller Phasen 0 bis 13 in einem Durchlauf. Er
ersetzt die Roadmap-Fassung vom selben Tag. Jede Phase nennt Entscheidungen,
exakte Namen, Werte, betroffene Dateien, Tests und Abnahmekriterien. Wo der
Plan "Annahme" sagt, wurde die Entscheidung am 2026-09-26 getroffen und gilt,
bis der Auftraggeber sie ändert.

## 0. Entscheidungen des Auftraggebers (2026-09-26)

| Frage | Entscheidung |
|---|---|
| Umfang | Alle Phasen 0 bis 13. Phase 14 (zwei besetzte Plattformen) bleibt Richtung, nicht Arbeit. |
| Git | Branch `plan-1.3` von `main`. Ein Commit je Phasenschritt mit grüner Suite. Kein Push. Merge nach Abnahme durch den Auftraggeber. |
| Fehlschlag | Phase auf den letzten grünen Commit zurücksetzen, Grund in `docs/resume.md`, mit der nächsten unabhängigen Phase weiter. |
| Hardware | Keine Abnahme auf der uConsole während des Durchlaufs. Alle Prüfpunkte kommen nach `docs/hardware-acceptance.md`. |
| Kernzerlegung | Vollständig, alle sechs Schritte. |
| Sehrohr | uConsole und Web. |
| Sprachfunk | Standardmäßig aktiv, Host schaltet in F9 ab. |
| Kampagne | Nicht in 1.3. Phase 13 umfasst nur die Missionslaufzeit. |
| Missionslaufzeit | Referenzwelten und Sektoren, Ziele protect und reach, Zufallsgruppen und Ereignisse, platzierte Flugzeuge/Tiere/Dekoys. Benutzerprofile bleiben ohne Wirkung. |
| Zweiter Torpedo | Zweite Leichtgewichts-Generation, generischer Katalogschlüssel. |
| Version | 1.3.0 in `src/core/version.py`, README und Notices angepasst, kein `python -m build`. |
| KI-Stärke | Realismus vor Trefferquote. |
| Tests | pytest-xdist installieren, `-n auto` als Standard. |
| Verschlüsselung | Bleibt ausgeschlossen. `--public-origin https://…` mit externem Proxy ist der einzige HTTPS-Pfad. |

Weiter ausgeschlossen: Zeitbeschleunigung, Pause, 3D, Änderungen an
`data/coastlines/real_sectors.json.gz` oder an `seed % 128`, neue
Drittanbieter-Assets, Benutzerprofile aus dem Unit-Editor als Laufzeitwirkung.

## 1. Arbeitsregeln für den Durchlauf

- **Umgebung.** Python aus `.venv/bin/python`. Tests mit
  `.venv/bin/python -m pytest`. Niemals `~/.u-jagd/` berühren; Skripte und
  Werkzeuge isolieren `SAVE_DIR`/Settings in ein Temp-Verzeichnis.
- **Start.** `git checkout -b plan-1.3` auf `main`. Vorher `git status`
  sichten: die 17 geänderten Dateien und die zwei neuen Dateien gehören zu
  Phase 0.
- **Commit-Regel.** Jeder Schritt endet mit `git diff --check`, den in der
  Phase genannten Fokus-Tests, der vollen Suite und den Werkzeugprüfungen
  (Abschnitt 19), dann einem Commit mit englischem Betreff in der Form der
  bestehenden Historie ("Weapons: second lightweight torpedo, search
  patterns, enable point") und der Attributionszeile aus der Sitzung.
- **Fortschritt.** Nach jedem Commit wird die Tabelle "Durchlauf 1.3" in
  `docs/resume.md` fortgeschrieben (Phase, Schritt, Commit, Testzahl,
  Laufzeit, offene Punkte). Sie ist die Wiederaufnahmestelle nach einem
  Kontextverlust: `git log --oneline main..plan-1.3` zeigt, was fertig ist.
- **Fehlschlag.** Ein Schritt gilt als gescheitert, wenn nach zwei
  Korrekturversuchen Tests rot bleiben, ein Widerspruch zu `AGENTS.md`
  entsteht oder eine Entscheidung nötig wäre, die dieser Plan nicht abdeckt.
  Dann `git checkout -- . && git clean -fd` auf den letzten grünen Commit,
  Eintrag in `docs/resume.md` mit Grund und Stand, weiter mit der nächsten
  Phase, die laut Abhängigkeitstabelle (Abschnitt 18) nicht auf der
  gescheiterten aufbaut.
- **Verträge.** `AGENTS.md` ist Vertrag. Beobachtungsgrenze, Determinismus,
  Echtzeit, Save-Regeln, i18n-Parität und Handbuchpflicht gelten in jeder
  Phase. Neue Zufallszüge nur über `src/core/detrand.py`.
- **Handbuch.** Jede Bedien- oder Mechanikänderung ändert im selben Commit
  `src/core/help.py`, `data/manual/<nn>-<kapitel>.en.md` und `.de.md` mit
  identischer Blockstruktur, `data/i18n/en.json` und `de.json`, dann
  `python tools/build_manual.py` und `pytest tests/test_manual.py`.
- **Kalibrierung.** `python tools/calibrate.py --check` nach jeder Phase mit
  Physik- oder Sensorwirkung. `tests/calibration/golden.json` wird nie neu
  aufgenommen; Abweichungen kommen mit `phase` und `reason` nach
  `tests/calibration/deviations.json` (Format wie die bestehenden Einträge).
- **Sprache.** Neue Dokumente unter `docs/` auf Deutsch, Code-Kommentare und
  Commit-Betreffs auf Englisch, wie im Bestand.

## 2. Gemeinsame Verträge

### 2.1 Save v15

- Tag `u-jagd-save-v15`, definiert in `src/core/save_schema.py` (Modul-Docstring,
  `SAVE_ROOT_FIELDS`) und den drei Stellen `Game.save_state()`,
  `Game._restore_state()` und Kandidatenvalidierung. Der Loader verlangt weiter
  byteweise Re-Serialisierungsgleichheit.
- v14 wird abgelehnt wie bisher v13, ohne Migration. Alle Tests und Fixtures,
  die `u-jagd-save-v14` enthalten, werden auf v15 gehoben; ein Test hält fest,
  dass ein v14-Dokument abgelehnt wird.
- Neue Wurzelfelder (angelegt in Phase 1, erweitert in 4 bis 9 und 13):
  `crew`, `weapon_settings`, `ai_solutions`, `helo_pattern`, `ocean_floor`,
  `plant`, `mission_events`. Die exakten Schlüssel je Block stehen in der
  jeweiligen Phase. Jeder Block ist ein exaktes Schlüssel-Set in
  `save_schema.py`; Werte sind endlich, typisiert, gebunden.
- Ein Round-Trip-Test je Block und ein gemeinsamer Continuation-Test
  (Speichern bei t, Laden, 300 s weiter, Zustand identisch mit dem Lauf ohne
  Speichern) in `tests/test_save_v15.py`.

### 2.2 i18n

- Namensräume: `help.control.*` für Tastenzeilen, `help.note.*` für
  Stationshinweise, `help.sop.<station>.<n>` für Verfahren, `ui.<station>.*`
  für Anzeigetexte, `commander.web.*` für den Browser, `option.*` für
  Einstellungen, `mission.*` für Missionslaufzeit. Nur benannte Platzhalter.
- Jeder neue Schlüssel in `en.json` und `de.json` im selben Commit;
  `tests/test_i18n.py` ist die Parität.

### 2.3 Tastenbelegung

- Stationstasten sind kontextgebunden und stehen in `STATION_HELP` in
  `src/core/help.py`. Vor jeder neuen Belegung wird `_GLOBAL_HELP` und die
  Tabelle der Zielstation auf Kollision geprüft. Die in den Phasen genannten
  Tasten wurden gegen den Stand vom 2026-09-26 geprüft; stellt sich beim
  Umsetzen eine Kollision heraus, gilt: Shift-Variante derselben Taste, dann
  die nächste freie Buchstabentaste, und die Wahl wird in `docs/resume.md`
  notiert.

### 2.4 Projektion und Web-Schema

- Jedes neue Feld in einer Rollenprojektion (`src/commander/projections.py`,
  `src/commander/bridge.py`) wird im selben Commit in
  `data/commander/js/state/schema.js` (`validateV2State`) ergänzt.
  `tests/test_commander_projection_schema.py` prüft die Parität; ab Phase 11
  erzeugt `tools/gen_web_schema.py` die Datei.
- Keine Wahrheitsfelder: Position, Kurs, Tiefe, Klasse, Seite fremder
  Einheiten erreichen die Projektion nur über `SensorTrack`/Kontakt/Fix mit
  Alter und Qualität.

### 2.5 Neue Kommandos der Remote Crew

- Neue Stationsbefehle werden in der Allowlist des Befehlspfads
  (`src/commander/bridge.py`, Kommandonamen als Strings, kein Methodendispatch
  aus Netzdaten) und in `data/commander/js/net/commands.js` ergänzt. Jeder
  Befehl läuft durch dieselben Frische-, Schadens-, Bestands-, ROE- und
  Bereitschaftsprüfungen wie die lokale Taste.

## 3. Phase 0: Audio-Soak abschließen

Ziel: Den Arbeitsbaum (17 geänderte Dateien, `tools/audio_soak.py`,
`tests/test_tools_audio_soak.py`) fertigstellen und in zwei Commits einchecken.

Inhalt laut Diff: Mixer-Puffer 512 → 2048 Samples
(`config.AUDIO_MIXER_BUFFER_SAMPLES`), `config.SIM_CATCHUP_MAX_S` 1.0 → 2.5 s,
Perf-Debug in `Game` (Commander-Maximum, Event- und Traffic-Zeit je Frame),
Server- und Worklet-Änderungen zur Stream-Kontinuität bei Epochenwechsel,
Soak-Werkzeug mit `host`- und `client`-Modus.

Schritte:

1. `git status` und `git diff --stat` sichten. Zum Audio-Commit gehören
   neben den 17 Code-/Testdateien und den zwei neuen Dateien auch die am
   2026-09-26 parallel geänderten Dokumente `docs/resume.md` (Abschnitt
   "Sonar-Audio ohne Aussetzer"), `docs/commander-protocol.md`/`.de.md`,
   `docs/install-uconsole.md`/`.en.md` (WLAN-Stromsparen) und
   `docs/manual/manual.*.md`. In `AGENTS.md` gehört die Zeile mit dem Verweis
   auf `docs/plan-1.3.md` zum Plan-Commit, jede andere Zeile zum
   Audio-Commit; getrennt stagen. Der Durchlauf beginnt erst, wenn keine
   andere Sitzung mehr im Arbeitsbaum schreibt.
2. Prosa prüfen, die 512 Samples oder 1 s Catch-up nennt:
   `grep -rn "512\|1\.0 s\|SIM_CATCHUP" README.md docs/ data/manual/ src/core/config.py`.
   Treffer im Handbuch oder README auf die neuen Werte bringen.
3. Fokus-Tests: `tests/test_audio.py`, `tests/test_commander_audio_recovery.py`,
   `tests/test_commander_audio_worklet.py`, `tests/test_commander_sonar_websocket.py`,
   `tests/test_commander_sessions_v2.py`, `tests/test_commander_bridge.py`,
   `tests/test_tools_audio_soak.py`, `tests/test_game_integration.py`,
   `tests/test_opfor_web.py`.
4. `python tools/audio_soak.py host --dummy-audio --clients 4 --bump-every 20`
   mit Exitcode 0. Dauer laut Werkzeug-Default; bei Bedarf `--duration 120`,
   falls die Option existiert, sonst Default.
5. Volle Suite, Werkzeugprüfungen, Commit 1 "Audio: 93 ms mixer buffer,
   2.5 s catch-up, stream continuity across epochs, soak tool".
6. Commit 2 "Docs: plan 1.3 and AGENTS pointer" mit `docs/plan-1.3.md` und
   der AGENTS-Zeile.

Hardware-Prüfpunkte (Checkliste): 10 Minuten Sonarraum auf der uConsole ohne
Knacken bei 30 FPS, ein PC im WLAN im `client`-Modus ohne Lücke.

## 4. Phase 1: Save v15 mit Crew-Zustand des Bootes

Ziel: Nach einem Load bleibt ein besetztes Boot besetzt, mit Modi, Mast,
Drähten, Plot und Alarmpeilungen. Behebt den ersten Eintrag unter "Not
modelled" in `data/manual/10-reference.*.md`.

Annahmen:

- A1.1 Remote-Crew-Leases bleiben transient. Nach dem Load werden die
  Boot-Stationen neu verleast, wie bei einem Weltwechsel. Der Solo-Modus
  behält seine Sitzung.
- A1.2 Das Boot bleibt auch dann manuell (`sub.manual`), wenn beim Laden kein
  Client die Station hält; es fährt dann seine gespeicherten Befehle weiter,
  bis die KI es per `release_manual()` übernimmt oder ein Spieler die Station
  nimmt. Das entspricht dem Verhalten bei Verbindungsverlust heute.
- A1.3 Die lokal gespielte Seite (Fregatte oder Boot, Commit `4d2500f`) und
  die aktive Station werden im bestehenden `ui`-Block gespeichert, falls sie
  dort noch fehlen.

Änderungen:

- `src/core/opfor.py`: `CrewOrders.to_save()`/`from_save()`,
  `CrewWire.to_save()`/`from_save()`, `CrewedBoat.to_save()`/`from_save()`.
  Docstrings "transient, never saved" entfallen.
- `src/core/save_schema.py`: Wurzelfeld `crew` = Liste je besetztem Boot:
  `sub_id`, `orders`, `command_page`, `chart_follow`, `plot`, `feed`,
  `feed_seq`, `station`.
  `orders` = exaktes Set `silent`, `bottomed`, `mast`, `alarm_seq`,
  `ping_bearing`, `torpedo_bearing`, `esm`, `esm_seen`, `wires`,
  `known_torpedoes`, `last_course`, `torpedo_depth`, `salvo`,
  `pending_bearing`, `steer_torpedo`, `battery_state`, `keel_warned`,
  `obstacle_warned`, `obstacle_ahead_nm`.
  `wires` = Map Torpedo-ID → `state` (`ACTIVE|BROKEN|CUT`), `ship_out_nm`,
  `stress_s`.
  `feed` = Liste bis `OPFOR_FEED_MAX` aus `seq`, `t`, `category`, `text`,
  `stamp`; `text` wird so gespeichert, wie `notice()` es ablegt (Katalogschlüssel
  plus Werte, nicht übersetzter Text), damit ein Sprachwechsel nach dem Load
  greift.
  `plot` = `PlotLayer.to_save()` (existiert für den Fregattenplot).
  `station` = Sonarstation des Bootes im selben Format wie die Blöcke
  `sonar_controls` und `sonar` der Fregatte. Dafür werden die beiden
  Serialisierer aus `Game.save_state()`/`_restore_state()` in Funktionen
  `sonar_station_state(station)` und `restore_sonar_station(station, data)`
  gezogen und von Fregatte und Boot genutzt. (Umgesetzt als Methoden
  `_sonar_system_state`/`_restore_sonar_system` in `src/core/game_save.py`;
  die Prüfung liegt in `src/core/save_validate_sonar.py`. Ein Modul
  `save_sonar.py` gibt es nicht.)
- `Sub`-Zeile im `subs`-Block: zusätzlich `manual`, `order_course`,
  `order_speed`, `order_depth`, `last_bottom_m`, `manual_ping_pending` und
  jedes weitere Attribut, das `command_*`, `_steer_to_orders`,
  `_update_surface_cycle` oder `snorkeling` liest oder schreibt (beim Umsetzen
  aus dem Code ermitteln und in `docs/resume.md` auflisten).
- `enemy_torpedoes`-Zeile: unverändert; die Drahtdaten liegen im `crew`-Block.
- `Game._restore_state()`: nach Wiederherstellung der Boote und Torpedos je
  `crew`-Eintrag `CrewedBoat.from_save()` aufrufen, Sub per `sub_id` binden,
  Drähte nur für noch existierende Torpedo-IDs annehmen (sonst Ablehnung des
  Dokuments, keine stille Reparatur). Danach Remote-Crew-Weltwechsel
  auslösen (bestehender Pfad), Solo-Sitzung behalten.
- Tag auf `u-jagd-save-v15`, alle Tests/Fixtures anheben.

Tests (`tests/test_save_v15.py`, neu):

- `test_round_trip_crewed_boat_with_two_wires`
- `test_continuation_after_load_matches_unsaved_run` (300 s, Boot manuell mit
  Kursbefehl, ein Torpedo am Draht)
- `test_v14_document_rejected`
- `test_crew_block_missing_key_rejected`
- `test_wire_for_unknown_torpedo_rejected`
- `test_load_keeps_local_boat_side_and_station`
- `tests/test_opfor_web.py`: Solo-Sitzung überlebt Load, Boot-Stationen sind
  neu zu nehmen, Befehle vor dem Neu-Nehmen werden abgelehnt.

Handbuch: `10-reference` "Not modelled": Eintrag "Crew state … is not saved"
entfällt; neuer Satz unter Remote Crew, dass nach einem Load jede
Boot-Station neu genommen wird. README-Abschnitt Save auf v15.

## 5. Phase 3: Testlauf und Abnahmecheckliste (vor Phase 2)

Ziel: Suite unter zwei Minuten, feste Hardware-Checkliste. Wird vor Phase 2
gemacht, damit die Zerlegung mit schneller Suite läuft.

Schritte:

1. `.venv/bin/python -m pip install pytest-xdist`; `pyproject.toml` `dev`-Extra
   um `pytest-xdist>=3` erweitern; `[tool.pytest.ini_options]`:
   `addopts = "-n auto"`, `markers = ["slow: …", "browser: …", "hardware: …"]`.
2. Isolation je Worker prüfen: Save-Pfade, Settings, Commander-Ports
   (Loopback-Server in Tests müssen Port 0 oder je Worker eigene Ports nutzen),
   SDL-Dummy-Umgebungsvariablen. Wo `tests/commander_fixtures.py` oder
   `tests/commander_web.py` feste Pfade/Ports setzen, mit `worker_id` oder
   `tmp_path_factory` isolieren.
3. Alle Tests, die Chromium starten (Nutzer von `tests/commander_web.py`),
   mit `@pytest.mark.browser` markieren; Tests über 20 s mit `slow`.
4. `--durations=20` auswerten; bei den zehn teuersten Tests Fixture-Sharing
   auf Modulebene, wenn kein Zustand geteilt wird.
5. `docs/hardware-acceptance.md` anlegen: Kopf mit Zweck, dann eine Tabelle
   je Phase mit Prüfpunkt, Vorgehen, Erwartung, Feld für Ergebnis. Die
   Prüfpunkte kommen aus den Abschnitten "Hardware-Prüfpunkte" dieses Plans.
   `docs/verification-log.md` verweist künftig darauf.
6. Zielwert: volle Suite unter 120 s auf dem Entwicklungsrechner. Wird er
   verfehlt, wird das gemessene Ergebnis in `docs/resume.md` notiert; die
   Phase gilt trotzdem als bestanden, wenn die Suite parallel grün ist.

Tests: Suite grün mit `-n auto` und mit `-n 0`. `tests/test_packaging.py`
prüft weiter, dass `xdist` keine Laufzeitabhängigkeit ist.

## 6. Phase 2: Kern zerlegen

Ziel: `src/core/game.py` (12.654 Zeilen), `src/ui/stations_view.py` (2.994),
`src/commander/server.py` (3.582) in Module mit einer Verantwortung, ohne
Verhaltensänderung. Sechs Schritte, jeder ein Commit.

Regeln: reine Verschiebung, keine Signaturänderung an Methoden, die Tests
aufrufen, keine Feature-Arbeit. `Game` bleibt Fassade: Methoden, die Tests
oder Remote Crew nutzen, bleiben als Delegation erhalten. Nach jedem Schritt
volle Suite, `tools/smoke_full.py`, `tools/calibrate.py --check`,
`tests/test_determinism.py`.

Schritte:

1. `src/core/game_save.py`: `save_state`, `_restore_state`, Kandidatenprüfung,
   atomares Schreiben, Slot-Funktionen, dazu die Sonar-Serialisierer aus
   Phase 1. Die Dokumentprüfung liegt in `src/core/save_validate.py` mit
   `save_validate_crew.py`, `save_validate_sonar.py`,
   `save_validate_entities.py`, `save_validate_weapons.py` und
   `save_validate_common.py`.
2. `src/core/game_sim.py`: `_update_sim()` und alles, was nur von dort
   aufgerufen wird (Entitätsupdates, Sweep-Kollision, Sensorgenerierung).
   Die Update-Reihenfolge wird als Modulkonstante `SIM_ORDER` dokumentiert und
   durch `tests/test_sim_order.py` eingefroren (Reihenfolge der aufgerufenen
   Hilfsfunktionen bei einem Schritt).
3. `src/core/game_events.py`: `handle_event()` und die Präzedenzkette
   (Splash, Editor, Tooltip-Esc, Verwaltung, Menü, Zahleneingabe, Station).
   Bestehende Tests in `tests/test_input_focus.py` und
   `tests/test_input_consistency.py` bleiben unverändert grün.
4. `src/core/mission_bridge.py`: `start_custom_mission` und die
   Editor-Laufzeitbrücke.
5. `src/ui/stations/`: ein Modul je Station (`bridge.py`, `sonar.py`, …,
   `helicopter.py`, `eloka.py`); `stations_view.py` bleibt Dispatcher mit
   Draw/Hit-Test-Einstieg. Draw- und Hit-Test-Geometrie bleiben im selben
   Modul.
6. `src/commander/v2/routes.py` (HTTP-Routen und WebSockets, Cookies,
   CSRF, Pairing), `src/commander/audio_streams.py` (Sonar- und
   Voice-Streams), `src/commander/station_leases.py` (Stationsleases),
   `src/commander/v2/wire.py`/`commands.py` (Konstanten, Framing,
   Befehlsregister); `server.py` hält Sitzungen, Veröffentlichung und
   Wiring. (Die ursprünglich geplanten Namen `routes_v2.py`, `streams.py`
   und `sessions.py` gibt es nicht.)

Abnahme: neuer Test `tests/test_module_size.py`: keine Datei unter `src/`
über 2.500 Zeilen. Perf-Debug-Ausgabe (Phase 0) eines 120-s-Smoke-Laufs
vor Schritt 1 und nach Schritt 6 in `docs/resume.md` festhalten.

Hardware-Prüfpunkte: Frame-Zeit 10 Minuten auf der uConsole bei 30 FPS
unverändert gegenüber 1.2.0 (Perf-Debug-Mittelwert).

## 7. Phase 4: Waffen der Fregatte

Ziel: Zweiter Leichttorpedo, wählbares Suchmuster, Enable-Punkt, Salve.

Annahmen (Werte):

- A4.1 Katalogschlüssel `frigate_torp_mk2`, Name "Leichttorpedo Mk2
  (Fregatte)" / EN "Lightweight torpedo Mk2 (frigate)". `speed_kn` 55,
  `range_nm` 8, `hit_dist_nm` 0.12, Sinkrate und Maximaltiefe wie
  `frigate_torp` plus 30 % Maximaltiefe, falls das Profil eine kennt.
  Einträge in `entries`, `profiles`, `references`, `machines` nach dem
  Muster von `frigate_torp`. `sources.json`: `game_assumption`.
- A4.2 Bestand: Der Szenario-Torpedovorrat N bleibt in Summe gleich:
  Mk1 = N − floor(N/3), Mk2 = floor(N/3). Szenario 3 (4 Torpedos): 3 + 1.
- A4.3 Suchmuster: `snake` (bisher, Default), `circle` (Radius 0.4 NM um den
  Enable-Punkt), `helix` (ab Enable-Punkt expandierend, Schritt 0.15 NM je
  Umlauf, maximal 1.0 NM). Existiert im ASROC-Pfad in `src/weapons/asw.py`
  bereits eine Helix-Suche, wird sie geteilt, sonst neu als pure Funktion.
- A4.4 Enable-Punkt `enable_nm` 0.6 bis 3.0 in Schritten von 0.2, Default
  1.2 (bisheriger fester Wert).
- A4.5 Salve: 1 oder 2; bei 2 ein Spread von ±8° um die Schusslinie, zweiter
  Torpedo 4 s nach dem ersten. Die Spread-Mechanik des Bootes (`044b4b7`)
  wird als pure Funktion in `src/physics/torpedo_dyn.py` geteilt.

Änderungen:

- `src/physics/torpedo_dyn.py`: `search_offset(pattern, phase, elapsed_nm)`
  pur; `spread_courses(course, count, angle)`.
- `src/weapons/torpedo.py`: `pattern`, `enable_nm` als Konstruktorparameter,
  Serialisierung in der `torpedoes_in_flight`-Zeile (Save v15).
- `Game`: `weapon_settings`-Block im Save: `torpedo_type` (Schlüssel),
  `pattern`, `enable_nm`, `salvo`, `stock` (Map Schlüssel → Anzahl). Das
  bisherige Wurzelfeld `torpedoes` bleibt als Summe für alte Anzeigen.
- Tasten (Waffenstation): `W` Torpedotyp wechseln, `X` Suchmuster wechseln,
  `, / .` Enable-Punkt −/+, `Y` Salve 1/2. (`N` und `P` sind global belegt:
  Nationen und Plotmodus.) `help.control.torp_type`,
  `torp_pattern`, `torp_enable`, `torp_salvo`; Hinweis `help.note.torp_types`.
- Anzeige: Waffenstation zeigt Typ, Bestand je Typ, Muster, Enable-Punkt,
  Salve in der Statuszeile. Web `stations/weapons.js` mit denselben vier
  Steuerelementen; Befehle `torpedo_type`, `torpedo_pattern`,
  `torpedo_enable`, `torpedo_salvo`.
- Score: 200 je unbenutztem Torpedo, weiterhin über die Summe.

Tests (`tests/test_weapons_torpedo_options.py`, neu):

- Mustergeometrie pur (Schlange unverändert zum Bestand, Kreis bleibt im
  Radius, Helix expandiert bis Maximum).
- Freigabe je Typ (kein Schuss bei Bestand 0 des gewählten Typs).
- Salve 2: zwei Torpedos, Kurse ±8°, zweiter 4 s später.
- Round-Trip `weapon_settings` und Torpedo mit Muster/Enable-Punkt.
- Kalibrierung: `torpedo.run_time_s.frigate_torp`, `travel_nm.frigate_torp`
  unverändert (Default = Mk1, Schlange, 1.2 NM).

Handbuch `03-weapons`: Abschnitt Torpedotypen und Suchmuster; unter "Not
modelled" entfallen "no selectable search pattern/enable point" und "one
torpedo type for the ship"; "no selectable salvo doctrine" entfällt.
Tiefenbomben/ASROC bleiben "Not modelled".

## 8. Phase 5: Gegner-KI mit eigener Zielanalyse

Ziel: Das KI-Boot schießt auf eine gemessene Lösung mit Fehler und Alter.
Bestand: `Sub.tma_track` (`BearingTrack`), `tma_next_t`, `_ingest_bearing`,
`_launch_data(observation)`. Neu ist die explizite Lösung mit Unsicherheit
und die Konvergenzbedingung.

Annahmen:

- A5.1 `src/sonar/ai_tma.py` (pur): `solve(track_points, own_track) →
  Solution(x, y, course, speed, sigma_range_nm, sigma_course_deg, t)` über
  `src/sonar/tma_lm.py`. Keine neue Mathematik. (Umgesetzt ohne eigenes
  Modul: `solution_sigma_nm`/`solution_converged` und die Lösung des Bootes
  liegen in `src/enemies/sub.py` über `src/sonar/tma.py`; Tests in
  `tests/test_ai_tma.py`.)
- A5.2 Schussbedingung: `sigma_range_nm / range_nm <= threshold` und Lösung
  jünger als 90 s. `threshold` aus einem neuen Schwierigkeitsfeld
  `enemy_solution_threshold` in `config.DIFFICULTY_FIELDS` (float, 0.05 bis
  0.40, Schritt 0.05): Szenario 1/2 = 0.25, Szenario 3 = 0.15, Zufall
  Default 0.20. Der Wert liegt im `level`-Block des Saves (bestehendes
  Feld, neue Spalte).
- A5.3 Ein Zielmanöver nach der letzten Peilung (Kursänderung über 30°)
  wird von der Lösung erst nach drei neuen Peilungen abgebildet; bis dahin
  läuft ein Torpedo auf das alte Datum.
- A5.4 Koordination: Ein Boot mit Mast oder Schnorchel oben teilt seine
  Lösung nach 60 s Verzögerung mit allen anderen Booten seiner Seite; die
  empfangene Lösung ist eine Beobachtung mit Alter, keine Wahrheit. Kein
  Reichweitenlimit (Funk). Kein Teilen ohne Mast/Schnorchel.
- A5.5 Bestehende Schwierigkeitsfaktoren `enemy_attack_mult`,
  `enemy_cooldown_s` bleiben.

Änderungen: `Sub`: Attribute `ai_solution`, `shared_solution`,
`share_timer_s`; `_maybe_attack` prüft A5.2; Save-Wurzelfeld `ai_solutions`
(Liste je Boot: `sub_id`, `solution`, `shared`, `share_timer_s`). Detrand-Tag
`ai_tma` für Peilrauschen, falls ein neuer Zug nötig wird.

Tests (`tests/test_ai_tma.py`, neu): Lösungsfehler sinkt mit Dauer; steigt
nach Zielmanöver; kein Schuss über Schwelle; Teilen nur mit Mast/Schnorchel;
Determinismus zweier Läufe; Round-Trip. Ein fester Drei-Seed-Lauf misst die
KI-Trefferquote und hält sie als Band im Test fest (kein Golden-Eintrag, da
die Metrik dort nicht existiert).

Handbuch `10-reference` (Boot/KI) und `02-sonar` Hinweis: Ausweichmanöver
nach einer erkannten Peilung verschlechtern die gegnerische Lösung.

## 9. Phase 8: Schiff und Schaden (vor Phase 6, klein)

Annahmen:

- A8.1 Gegenfluten: Schadensstation Taste `C` flutet das gegenüberliegende
  Abteil des gewählten; Krängung sinkt, Tiefgang steigt. `compartments`-Zeile
  erhält `counterflood` (0..1). Gegenfluten ist nur bei Schlagseite über 5°
  wirksam und stoppt automatisch bei unter 1°.
- A8.2 Trimm: `damage.trim_deg` aus Flutvolumen vorn/achtern; wirkt −0.5 kn
  Höchstfahrt je Grad und +1 dB Eigengeräusch am Bugsonar je Grad Bug-lastig.
  `src/physics/ship_dynamics.py`: `trim_deg(flood_fore, flood_aft, model)`.
- A8.3 Anlagenwahl: Maschinenstation Taste `G` wechselt `AUTO` (bisher) /
  `DIESEL` (Höchstfahrt 18 kn, Eigengeräusch −4 dB) / `TURBINE` (Höchstfahrt
  wie bisher, +3 dB, +25 % Verbrauch). Werte im `machines`-Register des
  Fregattenprofils, falls dort ein Feld dafür existiert, sonst als
  `config`-Konstanten mit Kommentar "Annahme 1.3".
- A8.4 Save: `plant` = `mode`; `damage.trim_deg`; `compartments.counterflood`.

Tests (`tests/test_damage_trim_plant.py`): Gegenfluten reduziert Krängung
und stoppt bei 1°; Trimm reduziert Höchstfahrt; Anlage DIESEL begrenzt Fahrt;
Kalibrierung mit AUTO unverändert; Round-Trip.

Handbuch `04-damage` und `07-engine`: "no counter-flooding", "no longitudinal
trim", "no separate gas turbine / diesel plant selection" entfallen.

## 10. Phase 6: Hubschrauber

Annahmen:

- A6.1 Muster: `single` (bisher), `field` (3x3, Abstand 1.0 NM),
  `barrier` (5 Bojen quer zur Peilung zum Ziel-Wegpunkt, Abstand 1.0 NM),
  `circle` (6 Bojen, Radius 1.5 NM um den Wegpunkt). Ein Muster ist eine
  Warteschlange von Abwurfpunkten, die der Helikopter nacheinander anfliegt
  und mit dem bestehenden Einzelabwurf bedient. Abbruch mit erneuter Wahl von
  `single`. Kein Kanalmanagement (bleibt "Not modelled").
- A6.2 MAD: Taste `Shift+M` schaltet den MAD-Anflug ein: Helikopter fliegt
  auf 30 m, kein Tauchsonar, Fahrt 90 kn. `src/sensors/mad.py` (pur):
  `detects(slant_m, sea_state, seed, tick)` mit Schwellwert 400 m Schrägdistanz,
  Sicherheit 0.9 unter 250 m, linear bis 0 bei 400 m, Zug über `detrand`
  (Tag `mad`). Ergebnis ist ein `SensorTrack` der Domäne `mad` mit Position
  = Helikopterposition zum Zeitpunkt, ohne Kurs, Tiefe oder Klasse. Kalibrierung:
  kein Effekt auf bestehende Metriken.
- A6.3 Taste `X` auf der Helikopterstation wechselt das Muster (`P` ist
  global der Plotmodus). Die Seite-3-Tasten (`help.key.p3_*`) werden vor der
  Belegung von `X` und `Shift+M` auf Kollision geprüft.
- A6.4 Save: `helo_pattern` = `kind`, `queue` (Liste x/y), `mad_mode`.

Änderungen: `src/air/helicopter.py` (Musterqueue, MAD-Modus, Höhe),
`src/air/sonobuoy.py` unverändert, `Game`-Helikopterpfad, Helikopterstation
uConsole und Web (`stations/helicopter.js`), Befehle `helo_pattern`,
`helo_mad`. Manual `08-helicopter`: "no buoy patterns", "no MAD" entfallen;
"no radar on the helicopter" und "only one helicopter" bleiben.

Tests (`tests/test_helicopter_patterns_mad.py`): Geometrie der drei Muster;
Abbruch leert die Queue; MAD-Detektion nur unter Schrägdistanz und nur im
MAD-Modus; Projektion ohne Wahrheitsfelder; Round-Trip.

## 11. Phase 7: Akustik-Werkzeuge

Annahmen:

- A7.1 Bodentypen `rock`, `sand`, `mud` je 10-NM-Zelle deterministisch aus
  Seed und Bathymetrie (`src/world/ocean.py`, `bottom_type(x, y)`): Fels bei
  Hangneigung über 2°, Schlick bei Tiefe über 1.500 m, sonst Sand.
  Bodenverlust je Reflexion in `src/sonar/raytrace.py`: Fels 2 dB, Sand 6 dB,
  Schlick 12 dB bei 10° Grazing, linear mit dem Grazing-Winkel. Der
  Referenzboden (Sand) reproduziert den bisherigen Verlust, damit die
  Golden-Metriken `sonar.passive_nm.*`/`active_nm.*` unverändert bleiben;
  gelingt das nicht exakt, Deviation mit Begründung.
- A7.2 Konvergenzzonen: aus der Verlusttabelle Minima jenseits 15 NM;
  Anzeige im Wasserprofil nur nach BT-Messung (Taste `E`), als Ringe auf der
  Sonarkarte mit Alter der Messung. Kein Wahrheits-Fallback.
- A7.3 Ekelund: pure Funktion `ekelund_range_nm(rate1_deg_s, rate2_deg_s,
  across1_kn, across2_kn)` in `src/sonar/tma.py`; verlangt zwei Beine mit
  Kursänderung über 30° und je 90 s Peilungen; Ergebnis Fix mit Unsicherheit
  ±20 %. Dot-Stack: Anzeige der Peilresiduen je Hypothese auf der TMA-Seite,
  rein visuell. Taste `T` wechselt weiter die Methode
  (Hypothese → Ekelund → Dot-Stack).
- A7.4 VDS: dritte Arrayart `VDS` neben `BOW` und `TOWED` in
  `src/sonar/sonar.py`; `Shift+B` wechselt zyklisch; `U / V` setzen die Tiefe
  des gewählten Arrays; VDS-Tiefe 20 bis 300 m, Ausbringen 120 s, Seegang
  maximal 5. Eigener Kontaktstrom mit Arraykennung. Save: `sonar_controls`
  um `vds_depth`, `vds_state` erweitert.

Tests (Bodentypen in `tests/test_ocean_environment.py`,
`tests/test_raytrace.py` und `tests/test_sonar_equation.py`; dazu
`tests/test_tma_methods.py`, `tests/test_vds.py`): Verlust monoton nach Bodentyp; CZ nur nach BT;
Ekelund-Formel gegen Handrechnung; VDS-Kontakte im `SensorTrack`-Format;
Kalibrierung; Round-Trip.

Handbuch `02-sonar`: alle vier Einträge unter "Not modelled" entfallen,
TPSW bleibt draußen (wird nicht gebaut).

## 12. Phase 9: Boot-Seite

Annahmen:

- A9.1 Dieselgeräusch beim Schnorcheln: neues optionales Feld
  `snorkel_broadband_db` (Default +12 dB) und `snorkel_lines` (zwei Linien bei
  50 und 100 Hz relativ) in `data/contacts/acoustics.json` für alle
  Dieselboote; `tools/gen_contacts.py` validiert das Feld; `Sub.noise_level`
  und `lofar_lines` berücksichtigen es beim Schnorcheln.
- A9.2 Sehrohrbild: dritte Seite `UBOOT_SCOPE` in `UBOOT_PAGES`
  (`src/ui/uboot_view.py`), sichtbar nur bei Mast oben (`P`); sonst zeigt
  die Seite "Mast eingefahren". Horizontlinie, Peilring, Kursanzeige, Tag/
  Nacht aus `src/world/atmosphere.py`, Seegang als Horizontbewegung
  (Phasenfunktion aus `ship_dynamics.wave_slope_rad`). `←/→` drehen das
  Rohr in 2°-Schritten, `Shift+←/→` 10°; `↑/↓` wählen wie auf den anderen
  Bootsseiten den Kontakt (bestehende Belegung `help.key.arrows`).
- A9.3 Sichtungen: Kontakte innerhalb der Sichtweite aus
  `src/sensors/visual.py` (Fregattenausguck) werden als Silhouetten gezeichnet
  (prozedural nach Rumpftyp aus `references`: Länge, Typ). Eine Sichtung ist
  ein `SensorTrack` der Domäne `visual` im Kontaktstrom des Bootes (Peilung,
  Zeit, grobe Klasse "Kriegsschiff/Handelsschiff/klein", keine Entfernung).
- A9.4 Stadimeter: Taste `Enter` auf der Sehrohrseite misst den gewählten
  Kontakt: Entfernung = Referenzlänge des identifizierten Typs / Winkel;
  ohne Klassifikation wird die Länge einer generischen Fregatte (130 m)
  angenommen. Ergebnis ist ein Fix mit ±25 % Unsicherheit, gültig 120 s.
- A9.5 Web: `stations/uboot.js` erhält die Ansicht "Sehrohr" mit demselben
  Bild auf einem Canvas; Befehle `scope_bearing`, `scope_mark`.
- A9.6 Kein Funkverkehr des Bootes (bleibt "Not modelled").

Tests (`tests/test_uboot_scope.py`): Sichtung nur bei Mast oben und
innerhalb Sichtweite; Nachts kürzere Sichtweite; Stadimeter-Fix mit
Unsicherheit; Projektion ohne Wahrheit; Layout DE/Großschrift/Pseudolokale;
Chromium-Test der Web-Ansicht.

Handbuch `10-reference`: "No periscope view" und "Snorkelling adds no diesel
noise" entfallen; `help.py` Boot-Tabelle um die Sehrohrtasten.

## 13. Phase 10: Grafik

- A10.1 Einstellung `aa_lines` (`option.aa_lines`, Default aus) in
  `src/core/preferences.py` und im Optionsmenü: Karten- und Plotlinien über
  `pygame.gfxdraw.aaline`/`aapolygon`. Per Perf-Debug messbar; Default aus,
  weil die uConsole-Kosten unbekannt sind (Hardware-Prüfpunkt).
- A10.2 Tageszeit im Kartenbild: Tönung der Wasserfläche nach
  `world.hour` in drei Stufen (Tag, Dämmerung, Nacht) über die Theme-Tokens
  (`89bf5be`), kein neuer Farbwert außerhalb der Tokens. Web `views/chart.js`
  identisch.
- A10.3 Wetter im Kartenbild: Regen-/Sturmband als gestricheltes Feld aus
  `world`-Wetterzustand, nur Anzeige.
- A10.4 Fregattenausguck (Brückenseite 3, `95c4b7f`) nutzt denselben
  Horizont-Renderer wie das Sehrohr aus Phase 9.

Tests: Optionen-Round-Trip in `tests/test_preferences.py`; Layout-Tests;
Chromium-Bilder 1920x1080/2560x1440 neu erzeugt.

Hardware-Prüfpunkte: Frame-Zeit mit `aa_lines` an/aus, Lesbarkeit bei Nacht.

## 14. Phase 11: Web-Client

- A11.1 `tools/gen_web_schema.py`: erzeugt `data/commander/js/state/schema.js`
  deterministisch aus der Python-Allowlist (`projections.py`, `bridge.py`);
  `--check` in der Werkzeugliste (Abschnitt 19). Der bestehende Paritätstest
  bleibt als zweite Sicherung.
- A11.2 Zustands-Push: WebSocket `/ws/v2/state` je Sitzung; der Server sendet
  die Rollenprojektion bei Änderung, höchstens 4 Hz, mit
  Heartbeat 2 s; bounded Queue (8 Nachrichten) mit Verwerfen der ältesten;
  Client (`js/net/`) fällt nach zwei ausgebliebenen Heartbeats auf das
  bestehende Polling zurück und versucht alle 10 s den Push erneut.
  Gleiche Projektionen, gleiche CSRF/Origin-Prüfung beim Aufbau.
- A11.3 Wasserfall und Karte über `OffscreenCanvas`, wenn verfügbar (kein
  Secure-Context-Zwang), sonst bisheriger Pfad. Bounds-Culling vor
  Punkttransformation. Ziel unter 4 ms je Frame bei 2560x1440 (Messung im
  Chromium-Test protokolliert).
- A11.4 Alle neuen Texte mit EN/DE-Parität, sichere DOM-Einfügung.

Tests: Generator deterministisch und `--check` rot bei Abweichung; Push und
Poll liefern identischen Zustand; Fallback nach Verbindungsverlust;
Chromium-Layoutmatrix.

Hardware-Prüfpunkte: Host-CPU mit maximaler Clientzahl bei Push gegenüber
Poll.

## 15. Phase 12: Rollen, Nachbesprechung, Sprachfunk

- A12.1 Rolle `observer`: Pseudo-Rolle wie `host`, vom Host in F9 vergeben,
  höchstens 2 gleichzeitig, nur lesend; erhält die SimLog-Vollwahrheit
  (bestehende Capability) und alle Stationsansichten schreibgeschützt. Jeder
  Befehl wird abgelehnt. Transient, nie im Save.
- A12.2 Nachbesprechung: `views/simlog.js` erhält einen Zeitstrahl mit
  Ereignismarken (Schuss, Treffer, Kontakt, Verlust) und Scrubbing über die
  gespeicherte SimLog-Historie; Export als JSON-Download ohne RNG-,
  Credential- oder Settings-Daten. Nur für `observer` und `host`.
- A12.3 Sprachfunk: `_voice_enabled` startet mit `True`; F9-Zeile schaltet
  ab; Abschalten trennt aktive Sprecher. Test in
  `tests/test_commander_voice.py` angepasst.
- Voraussetzung: Phase 2 Schritt 6.

Tests: Observer kann nichts befehlen; Observer-Projektion enthält keine
Objekte, RNG oder Credentials; Export-JSON ohne verbotene Schlüssel;
Zeitstrahl-Rendering im Chromium-Test.

## 16. Phase 13: Missionslaufzeit = Editorumfang

Ziel: `Game.start_custom_mission` (nach Phase 2 in
`src/core/mission_bridge.py`) akzeptiert die vier gewählten Bereiche.
Benutzerprofile bleiben abgelehnt.

Schritte, je ein Commit:

1. **Referenzwelten.** `world.kind == "reference"` mit `world.reference`
   als logischem Sektorschlüssel des Katalogs (Form wie im Sektor-Loader,
   z. B. `sector:<index>`; der genaue Schlüssel wird aus
   `src/world/real_coast.py` übernommen). Größe bleibt 500 NM; andere Größen
   weiter abgelehnt. Der Editor bietet die 128 Sektoren als Auswahl. Reset
   über den bestehenden Real-Welt-Pfad mit dem Sektorindex statt `seed % 128`.
2. **Ziele.** `protect`: `target_ids` sind Einheiten der Seite `friendly` oder
   `neutral`; verloren, wenn eine versenkt wird; gewonnen bei Zeitablauf.
   `reach`: Zielpunkt aus dem Definitionsfeld (Validator-Zeilen zu
   `objective`), Radius 2 NM Default; gewonnen beim Erreichen, verloren bei
   Zeitablauf. Beide nutzen den bestehenden Ergebnispfad
   (`mission_result`, `result_reason`).
3. **Zufallsgruppen und Ereignisse.** Gruppen werden beim Start über
   `static_preview` mit `_stable_seed` platziert (bereits deterministisch).
   Ereignisse laufen nach `at_s`: `message` → Meldung im Feed (Text aus der
   Definition, nicht übersetzt), `spawn` → Gruppe instanziieren, `weather` →
   Wetter setzen, `objective` → `complete`/`fail`. Save: Wurzelfeld
   `mission_events` = Liste noch ausstehender Ereignis-IDs plus die
   Definition (bereits in `mission_runtime`, falls dort vorhanden).
   Wetter ungleich `clear` beim Start wird damit ebenfalls akzeptiert.
4. **Weitere Einheiten.** Flugzeuge aus `aircraft.json` über den Flugpfad
   (`src/air/flights.py`), Tiere über `Animal`, Dekoys als statische
   `Decoy` an der Position. Alle als exakt platzierte Einheiten mit Kurs/Fahrt.

Jede Stufe entfernt die passende Bedingung in der Ablehnungsliste und ergänzt
`docs/commander-coop.md`, das Handbuch (`00-quickstart`, `10-reference`)
und den Abschnitt "Current intentional limits" in `AGENTS.md`.

Tests (`tests/test_mission_runtime.py`, neu): je Stufe Start und Ablauf
einer Definition, Determinismus zweier Läufe, Ablehnung von Benutzerprofilen
und fremden Weltgrößen bleibt, Round-Trip `mission_events`, Editor-`F5`-Tests
in `tests/test_mission_editor.py` angepasst.

## 17. Abschluss des Durchlaufs

1. `src/core/version.py` → `1.3.0`. README: Release-Absatz, Save v15,
   neue Funktionen in der Reihenfolge der Phasen. `THIRD_PARTY_NOTICES.md`
   nur prüfen (keine neuen Assets erwartet).
2. `AGENTS.md`: Zeile 1 Version und Save v15; "Current intentional limits"
   nach Phase 13; "Player documentation" unverändert.
3. `python tools/build_manual.py`, `docs/manual/` neu erzeugt.
4. `docs/resume.md`: Abschnitt "Durchlauf 1.3" mit Tabelle aller Phasen,
   Commits, Testzahl, Laufzeit, gescheiterten Phasen und offenen Punkten.
5. `docs/verification-log.md`: Eintrag mit Revision, Suite, Katalog, Smoke,
   Kalibrierung, "Not covered: Hardware, siehe hardware-acceptance.md".
6. `docs/hardware-acceptance.md`: alle Prüfpunkte der Phasen 0, 2, 9, 10,
   11, 12 mit leerem Ergebnisfeld.
7. Letzter Commit "Release 1.3.0 candidate: version, README, documents".
   Kein Push, kein Build.

## 18. Reihenfolge, Abhängigkeiten, Zeitrahmen

| Reihe | Phase | Größe | Voraussetzung | Save v15 | Kalibrierung | Hardware-Punkte |
|---|---|---|---|---|---|---|
| 1 | 0 Audio-Soak | S | – | nein | nein | ja |
| 2 | 1 Crew-Zustand | M | 0 | legt an | nein | nein |
| 3 | 3 Tests/Checkliste | S | – | nein | nein | nein |
| 4 | 2 Kernzerlegung | L | 1, 3 | nein | ja | ja |
| 5 | 4 Waffen Fregatte | M | 1 | ja | ja | nein |
| 6 | 5 KI-TMA | M | 1 | ja | ja | nein |
| 7 | 8 Schiff/Schaden | S | 1 | ja | ja | nein |
| 8 | 6 Hubschrauber | M | 1 | ja | ja | nein |
| 9 | 7 Akustik | L | 1 | ja | ja | nein |
| 10 | 9 Boot-Seite | M | 1 | ja | nein | ja |
| 11 | 10 Grafik | S | 9 | nein | nein | ja |
| 12 | 11 Web-Client | M | 2 | nein | nein | ja |
| 13 | 12 Rollen/Debrief | M | 2, 11 | nein | nein | ja |
| 14 | 13 Missionslaufzeit | L | 2 | ja | nein | nein |
| 15 | Abschluss | S | alle | – | – | – |

Zeitregel: Überschreitet eine Phase zwei Stunden ohne grünen Zwischenstand,
gilt die Fehlschlagregel aus Abschnitt 1. Scheitert Phase 2, laufen 11, 12
und 13 trotzdem auf den bestehenden großen Dateien; der Abschluss vermerkt
das. Scheitert Phase 1, entfallen alle Save-v15-Erweiterungen; die Phasen 4
bis 9 werden dann ohne Persistenz nicht begonnen, sondern übersprungen.

## 19. Prüfbefehle nach jedem Schritt

```sh
.venv/bin/python -m pytest
.venv/bin/python tools/gen_contacts.py --check
.venv/bin/python tools/build_manual.py --check
.venv/bin/python tools/calibrate.py --check
.venv/bin/python tools/smoke_full.py
.venv/bin/python tools/gen_web_schema.py --check   # ab Phase 11
git diff --check
```
