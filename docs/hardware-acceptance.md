# Hardware-Abnahme auf der uConsole

Headless-CI ist keine Hardware-Abnahme. Diese Checkliste sammelt die
Prüfpunkte, die nur auf dem echten Gerät (uConsole, CM5, 1280x720, 30 FPS
Voreinstellung) beantwortet werden können. Jeder Release-Eintrag in
`docs/verification-log.md` verweist auf den Stand dieser Liste; ein leeres
Ergebnisfeld heißt "nicht geprüft", nie "bestanden".

Vorgehen für jeden Lauf:

1. Aktuellen Branch installieren (`python -m pip install -e .`), Saves und
   `settings.json` unter `~/.u-jagd/` vorher sichern.
2. `python main.py` im Vollbild starten, Sprache Deutsch und Englisch je
   einmal, Großschrift einmal.
3. Perf-Debug einschalten (F9-Verwaltung, `perf_debug.log` unter
   `~/.u-jagd/`) und die Zeile mit `frame_ms`, `sim_ms`, `commander_max_ms`
   nach dem Lauf in die Tabelle übernehmen.
4. Ergebnis je Zeile: `ok`, `abweichung: <Beschreibung>` oder leer.

## Allgemein (jeder Release)

| Prüfpunkt | Vorgehen | Erwartung | Ergebnis |
|---|---|---|---|
| Frame-Zeit 30 FPS | 10 Minuten Szenario 2, Sonarstation, Perf-Debug | `frame_ms` Mittel unter 33, Maximum außerhalb des Starts unter 100 | |
| Frame-Zeit 60 FPS | wie oben mit Option 60 FPS | Mittel unter 17, kein Dauer-Catch-up (`sim_dropped` 0) | |
| Mixer | 10 Minuten Sonarraum hören | keine Knackser, keine Stille über 0,75 s (`channel_idle` 0) | |
| Lesbarkeit | jede Station in DE mit Großschrift | kein abgeschnittener Text, kein Überlappen | |
| Remote Crew Last | maximale Clientzahl, 10 Minuten | `commander_max_ms` unter 60, keine Reconnect-Schleifen | |
| Thermik | 30 Minuten Dauerlauf | keine Drosselung (`vcgencmd get_throttled` = 0x0) | |

## Phase 0: Audio-Soak

| Prüfpunkt | Vorgehen | Erwartung | Ergebnis |
|---|---|---|---|
| Hörabnahme lokal | 10 Minuten Sonarraum, dabei F1/F9/Optionen öffnen und schließen | kein Aussetzer beim Öffnen von Overlays | |
| Hörabnahme Browser | PC im WLAN, `python tools/audio_soak.py client --host <uConsole>` 10 Minuten | Exitcode 0, keine Lücke über 0,75 s | |
| WLAN-Stromsparen | `iw dev wlan0 get power_save` | `off` (siehe `docs/install-uconsole.md`) | |

## Phase 2: Kernzerlegung

| Prüfpunkt | Vorgehen | Erwartung | Ergebnis |
|---|---|---|---|
| Frame-Zeit unverändert | Allgemein-Lauf vor und nach dem Merge vergleichen | `frame_ms` Mittel innerhalb 10 % von 1.2.0 | |
| Stationswechsel | alle neun Stationen und Seiten durchschalten | keine Hänger, keine Fehlermeldung im Log | |

## Phase 9: Boot-Seite (Sehrohr)

| Prüfpunkt | Vorgehen | Erwartung | Ergebnis |
|---|---|---|---|
| Sehrohrseite | uConsole spielt das Boot, Mast oben (Station 5, `P`), Führung Seite 3 oder Mast & ESM Seite 2 | Horizont, Peilskala und Silhouetten lesbar, 30 FPS gehalten; `←/→` schwenken fließend | |
| Nachtsicht | Startzeit 02:00 | Bild dunkler, Silhouetten nur nahe; Fregatte bei 2 sm noch zu sehen | |
| Stadimeter | Fregatte im Fadenkreuz, `Enter` | Bootslog meldet Entfernung; Sichtungsliste zeigt Entfernung mit ±; Waffenseite schießt auf den Kontakt mit VISUAL-Fix | |
| Dieselgeräusch | Boot schnorchelt, Fregatte hört auf LOFAR | Linien bei 50/100 Hz sichtbar, Breitband lauter | |
| Browser Sehrohr | Rolle Mast & ESM im Browser, Mast oben | Canvas zeichnet, Schwenkknöpfe und Formular wirken, Sichtungsliste und Stadimeter wie am uConsole | |

## Phase 10: Grafik

| Prüfpunkt | Vorgehen | Erwartung | Ergebnis |
|---|---|---|---|
| Anti-Aliasing | Option `aa_lines` an/aus, Brücke mit Karte | Mehrkosten unter 1 ms je Frame, sonst Voreinstellung aus lassen | |
| Tag/Nacht-Karte | Startzeiten 06:00, 12:00, 22:00 | Wasserfläche in drei Stufen getönt, Kontraste lesbar | |

## Phase 11: Web-Client

| Prüfpunkt | Vorgehen | Erwartung | Ergebnis |
|---|---|---|---|
| Push gegen Poll | maximale Clientzahl, Host-CPU beobachten | Push nicht teurer als Poll (`commander_max_ms`) | |
| Wasserfall im Browser | 2560x1440, Sonarrolle | flüssig, keine Aussetzer im Audio | |

## Phase 12: Rollen und Nachbesprechung

| Prüfpunkt | Vorgehen | Erwartung | Ergebnis |
|---|---|---|---|
| Sprachfunk Standard | Client pairt, spricht ohne F9-Eingriff | hörbar; F9-Zeile schaltet ab und trennt Sprecher | |
| Beobachterrolle | zwei Beobachter plus volle Crew | Host-CPU im Rahmen, Beobachter kann nichts befehlen | |
