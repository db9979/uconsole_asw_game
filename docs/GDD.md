# GDD – U-Jagd (Game Design Document)

> Historisches Design-/Entwicklungsdokument. Aktueller Stand: Version 0.1.7,
> Save v10 als einziges Schreib- und Ladeformat. Verbindliche laufende Arbeit:
> `plan-0.1.7.md` und
> `resume.md`. Alte Phasen- und Save-v7-Aussagen unten sind keine aktuellen APIs.

**Projekt:** u-jagd | **Plattform:** ClockworkPi uConsole (Debian 13, RPi CM5)
**Rendering:** natives 1280×720-Canvas; Vollbild skaliert auf die verfügbare Displayfläche.
**Engine:** Python 3.13 + pygame 2.6 (venv) | **Modus:** Echtzeit mit Pause | **Sprache:** Deutsch

---

## 1. Konzept
Der Spieler ist Kommandant einer U-Jagd-Fregatte. In Echtzeit (mit Pause) führt er
die Fregatte über eine Seekarte, jagt U-Boote mit aktivem/passivem Sonar und
Torpedos, meidet zivile Schiffe und sortiert Tier-Falschkontakte heraus – während
Schäden an Bord repariert werden müssen.

**Elevator Pitch:** „Hunter-Killer-Drama im Taktik-Modus: Du sitzt an der
Sonarzentrale deiner Fregatte – jedes Ping, jeder Kurs, jeder Torpedo entscheidet."

## 2. Spieler-Loop (pro Mission)
1. **Mission erhalten** (z. B. „U-Jagd in Sektor 7, 3 Kontakte gemeldet")
2. **Navigation**: Kurs/Geschwindigkeit wählen (Fahrt = Lärm = schlechteres Sonar)
3. **Suche**: Sonar passiv/aktiv → Kontakte (echt, falsch, zivil)
4. **Identifikation**: Typ bestimmen (U-Boot-Typ / zivil / Tier)
5. **Angriff**: Torpedo-Tiefe setzen, Start, Führung, (Multi-)Treffer → U-Boot sinkt
6. **Gegenschlag**: U-Boote kontern → Schadensmodell + Reparaturteams
7. **Erfolg/Abbruch**: Ziel versenkt / zivil verletzt / Fregatte gesunken / Zeit überschritten

## 3. Stationen (Spiel-Views, umschaltbar über 1–8)
| Taste | Station | Inhalt |
|---|---|---|
| 1 | Brücke | Seekarte (Fregatte, Küsten, AIS), Kurs/Geschw.-Regler, Mission-Text |
| 2 | Sonarzentrale | Sonar-Kreisbild + Kontaktliste (Richtung/Distanz/Qualität/Konfidenz), Ping-Steuerung |
| 3 | Waffenzentrale | Ziel-Select, Torpedo-Tiefe, Munitionsstand, Start-Button |
| 4 | Schadensbekämpfung | Kompartiment-Schema, Flutungs-Anzeige, Reparaturteams (3 Teams) zuweisen |
| 5 | OPZ/CIC | Radar-Scope, AIS, ESM/HOJ, Lagebild, VLS, ESSM, CIWS, Chaff |
| 6 | Funkraum | HFDF-Peilungen, HQ-Teletype, Morseband |
| 7 | Maschinenraum | Telegraph, RPM, Eigenlärm, Kavitation, Fahrtgrenze |
| 8 | Helikopter-Deck | HSP-5-Status, Treibstoff, Bojen, Lufttorpedos, Datenlink |

**Steuerung (globale):**
- `P`: Pause | `F1`: kontextabhängige Hilfe | `Esc`: Eingabe/Ansicht schließen
  oder Beenden-Dialog mit sicherer Vorauswahl
- Verwaltung pausiert, keine operativen Befehle in Pause; U/V-Eingaben bleiben live.
- `U`/`V`: Zielkurs/Zielfahrt direkt eingeben | `Alt+Enter`: Vollbild
- `↑/↓`: Kurs/Ruder (Brücke/Engine) bzw. Torpedotiefe (Waffen)
- `+/−`: Telegraph/Motorenbefehl | `B`: Sonar-Array oder Bojen (stationsabhängig)
- `A`: Aktiver Ping (Sonar) | `M`: Kontakt markieren (Ziel setzen)
- `T`: Torpedo-Start (Waffenzentrale)
- Station 4: Links/Rechts Raum, Auf/Ab Team, Enter zuweisen, Backspace zurückziehen
- `R` (nach Game-Over): Neustart | `Tab`/`Shift+Tab`: Stationen wechseln (auch 1–8 direkt)
- `Z`/`X` oder `[`/`]`: Zeitraffer; Sonar `I`/`O`: Gain; Space nur Sonar-Peak-Hold
- `S`: Speichern (JSON) | `L`: Laden (M6)
- Slots 1-5 auswählen, Enter bestätigen; Überschreiben/Laden zusätzlich bestätigen.
- `Q`/`E`: Kartenzoom ausschließlich auf Brücke, Waffen- und
  Helikopterstation; `Q` ist keine Beenden-Taste.
- Kurzhinweise im Ereignis-Feed sind stationsbezogen und nennen nur Befehle der
  aktiven Station; `F1` enthält globale und stationsspezifische Seiten.

Der aktuelle Ausbaustand, bekannte Grenzen und die weitere Roadmap stehen in
`implementation-plan.md`. Die folgenden Fachkapitel enthalten teilweise noch
historische Zielbeschreibungen, keine vollständige Implementierungszusage.

## 4. Welt & Dynamik
- **Karte**: Der Seed wählt stabil einen von genau 128 vorvalidierten realen
  500×500-NM-Küstensektoren. Küsten, geografische/Ländernamen und Namen realer
  Militärstützpunkte stammen aus den in `THIRD_PARTY_NOTICES.md` fixierten
  Quellen. Alternativ bleibt die feste stilisierte Legacy-Karte wählbar.
- **Übungsrollen und Tiefe**: Freundliche, feindliche und neutrale Rollen sind
  unabhängig von den realen Namen zugewiesene fiktionale Übungsrollen. Die
  Bathymetrie ist seedbasierte Synthese aus Küstenabstand und Variation, keine
  reale Vermessung und nicht navigationstauglich.
- **Tag/Nacht**: 24h-Zyklus (24h pro Mission, beschleunigt 1 min = 1 h),
  beeinflusst Radar-Sichtbarkeit & Stimmung.
- **Wetter**: Seegang 0–6, Regen/Nebel (Radar-Sicht), ändert sich pro Mission.
- **Thermokline**: Tiefe 15–120 m, driftet langs; Schall-Schatten-Zone darunter;
  je wärmer das Szenario, desto flacher die Schicht.
- **Kontakte (Falsch)**: Tiere (Wale/Fischschwärme/Quallen) spawnen pro Gebiet;
  haben eigene Bewegung/Lebensdauer; „Konfidenz" steigt über Zeit (Beobachtung).

## 5. U-Boot-KI (Zustandsautomat)
Zustände: `PATROLLE` → (Kontakt) → `EVALUATION` → (`VERMEIDUNG` | `LAUER` | `ANGRIFF`)
- `VERMEIDUNG`: Tiefe unter Thermokline + Kurs 90° ab Fregatte + Langsamfahrt
- `LAUER`: still liegen, passiv lauschen
- `ANGRIFF`: Kurs zur Fregatte, Torpedo-Abgabe (nur bei guter Reichweite & tiefe Position)
- `GESCHAENDIGT` (nach Treffer): Flucht zum flachsten Punkt / Kontrollverlust
- `GESUNKEN`: aus dem Spiel
- Entscheidungen mit „Reaktionszeit" (5–15 s) – kein Omniscient-KI, reagiert nur
  auf detektierte Sonar-/Radar-Ereignisse (Ping gehört, Torpedo startet, etc.).

## 6. Schadensmodell (Fregatte)
- 6 Kompartimente (s. Captain's Log §4.1), jeweils Zustand: OK / BESCHAEDIGT / FLUTEND / ZERSTOERT
- Torpedotreffer (vom U-Boot) → 1–2 Kompartimente betroffen (nach Trefferpunkt)
- Flutung: Flutungsrate je Kompartiment; bei >70 % → Station unwiederbringlich (ZERSTOERT)
- Reparaturteams (3): Zuweisung → Reparatur (Zeit je Schadensklasse) → Zustand → OK
- Global: Flutungs-Summe > Schwelle → Schiff kippt/sinkt → Mission verloren
- Stationen-Ausfall = Gameplay-Folge (z. B. Sonarzentrale ZERSTOERT = kein Sonar mehr)

## 7. Erfolg/Defeat
- **Sieg**: Ziel-U-Boot versenkt, keine zivilen Verluste, Fregatte am Leben
- **Niederlage**: Fregatte gesunken / ziviles Schiff versenkt (politischer Vorfall)
  / Missionszeit überschritten (Sektoralarm) / U-Boot entkam (Kontakt verloren + Zone verlassen)
- **Score**: Versenkungen, Zeit, Munitions-Sparbonus, Zivil-Schutz-Bonus

## 8. Missions-System (M6)
- **Missions-Typen**: Patrouille (1 Boot), Doppeljagd (2 Boote), Konvoi-Schutz
  (Zivile eskortieren + U-Boot im Gebiet), Nuklearer-Abfang (SSN, Zeitdruck)
- **Zufall**: Seed-basierte Erzeugung (Typen, Startpositionen, Tierdichte, Thermokline)
- **Save/Load**: Mission-Zustand als JSON; Save v7 bettet einen kanonischen,
  deterministischen Snapshot von Küstengeometrie, Stützpunkten, Metadaten und
  synthetischer Bathymetrie ein. Das Laden hängt damit nicht von einer späteren
  Generator- oder Katalogversion ab.

## 9. Schwierigkeit (implementiert in M7, `config.LEVELS`)
- `LEICHT`: U-Boote lauter (quiet_mult 0.8), Torpedos toleranter
  (Treffer-Radius 0,20 NM / 20 m Tiefe), Reparatur ×1,5, Gegnerangriff gedämpft
- `NORMAL`: Baseline (6 Torpedos, 0,135 NM / 15 m, Standard-Cooldown 90 s)
- `HARTE`: nur 4 Torpedos, U-Boote kontern schneller (Rate ×1,5, Cooldown 45 s),
  85 % Chance für ein zusätzliches AIP/SSN-Boot
- Auswahl im Startmenü (Tasten 1/2/3, Enter/Space = Start); `main.py` startet
  immer im Menü

## 10. UI/UX (natives 1280×720-Canvas)
- **Hauptlayout**: linke Hälfte = Haupt-View der aktiven Station, rechte Hälfte =
  sekundäre Info (Kontaktliste / Kompartiment / Munition) + HUD-Leiste oben
  (Uhrzeit, Kurs, Geschw., Flutungs-Summe, Munition, Mission-Status)
- **Sonar-Kreisbild**: Fregatte in der Mitte, 360°, stationsabhängige Skalierung,
  Kontakte als farbige Punkte (grün = zivil/AIS, gelb = unbestimmt, rot = U-Boot-Verdacht)
- **Radar-PPI**: dunkelblaues geografisches PPI, 360°, Darstellungsbereiche
  10/20/40/80/120 NM. Die nominelle Sensorreichweite ist davon getrennt:
  30 NM für Seeziele und 100 NM für Luftziele; Wetter und Stationsschaden
  können sie reduzieren.
- **Gemeinsames Lagebild**: NATO-ähnliche Symbole für See, Luft und Flugkörper;
  der eigene HSP-5 erscheint als freundliches Luftsymbol aus Datalink-Daten.
- **Geografische Karten**: dunkelblaue Seekarten und PPI-Flächen mit
  zurückhaltender blauer synthetischer Tiefenstaffelung.
- **Hud-Stile**: dunkel, phosphor-grün (CRT-Feeling), große lesbare Zahlen
- **Menüs**: Pause-Menü (Fortsetzen/Neustart/Optionen), Start-Menü (Mission/Schwierigkeit)

## 11. Audio (prozedural)
- Sonar-Ping (Ton + Abkling-Echo), passiver Hintergrund (Schiffsmaschinen-Rauschen),
  Torpedo-Start-Signal, Warnsummer (Kollision/Schaden), Wal-Laut (stereo-Pan nach Richtung)

## 12. Non-Goals (bewusst außen vor)
- Kein 3D, keine Crew-Charaktere mit Namen (nur Rollen), keine Diplomatie-Dialoge,
  kein Multiplayer, keine Navigation oder reale Einsatzplanung mit den
  abgeleiteten Geodaten und der synthetischen Bathymetrie,
  keine Munitions-Nachlieferung mid-Mission.

## 13. Meilenstein-Definition of Done
Jeder Meilenstein ist fertig, wenn:
- Feature spielbar (auch kurz) und stabil (kein Crash nach 10 Min)
- Headless-Smoke-Test läuft (`SDL_VIDEODRIVER=dummy`)
- Releventer Logik: Unit-Test mit Seed (deterministisch)

## 14. Implementierungsstatus M4 (M4-Neuzugänge)
- **Mehrere U-Boot-Typen**: 1× `diesel_alt` garantiert; optional 2. Boot
  `aip_modern` (Geisterschwärmer) oder `ssn` (Knochenbrecher), seed-basiert.
- **Meerestiere** (`src/enemies/animal.py`): `whale` (80–200 m, 6 kn),
  `fish_school` (30–80 m, 2 kn), `jellyfish` (5–25 m, 0.5 kn). Wandern langsam,
  erzeugen passive Sonarkontakte mit `kind="animal"`. 2–4 pro Mission.
- **Kontakt-Klassifikation**: Sonar-Kontakte haben `kind` (sub/animal). Ab
  50 % Konfidenz zeigt das Sonar-Panel „Sig.: mechanisch / biologisch" –
  Spieler soll Tiere erkennen und nicht abschießen.
- **Zivile Schiffe** (`src/enemies/civilian.py`): 2–3 pro Mission, 6–12 kn,
  mit AIS-Rufzeichen. Sichtbar auf Brücken-Karte und innerhalb der nominellen
  30-NM-Seeradarreichweite; der PPI-Darstellungsbereich ist separat wählbar.
  Namen + Status-Label. (Aktualisiert in §23: zivile Schiffe sind jetzt auch
  passive Sonarkontakte – „nie im Sonar" gilt nicht mehr.)
- **Politischer Vorfall**: Torpedo innerhalb `CIVILIAN_HIT_RADIUS_NM` (0.2 NM)
  eines Zivilschiffs → `incident=True`, Schiff wird rot markiert, Torpedo
  verworfen, Warnbanner + Eintrag im Radar-View.
- **Torpedo**: kann auch Tier-Kontakte angreifen (Duck-Typing
  `sunk/state/hit()`); Treffer auf Tier = „Biologischer Kontakt getroffen".
- **Tests**: `/tmp/opencode/m4_smoke.py` (Spawn-Determinismus, Tier-Kontakt,
  Vorfall, Tier-Treffer, Game-Loop) – alle grün, M2/M3 ohne Regression.

## 15. Implementierungsstatus M5 (Schaden & Gegenschlag)
- **Schadensmodell** (`src/ship/damage.py`): 6 Kompartimente
  (`bridge`, `sonar`, `weapons`, `engine`, `hull_left`, `hull_right`),
  Zustände OK / BESCHAEDIGT / FLUTEND / ZERSTOERT. Torpedotreffer → 1–2
  zufällige Kompartimente FLUTEND (Start 10–30 %).
- **Flutung/Reparatur**: FLUTEND +3,0 %/s, BESCHAEDIGT +0,8 %/s (Leck),
  Reparaturteam −8,0 %/s; ≤35 % → BESCHAEDIGT, ≤0 % → OK, ≥70 % → ZERSTOERT
  (unreparierbar). Summe ≥360/600 → Fregatte sinkt → Game-Over.
- **Stationen-Effekte**: Maschinerie gestört/aus → Fahrt-Cap 15/8 kn;
  Brücke gestört → Ruder 50 % langsamer, aus → keine Kursänderung;
  Sonarzentrale aus → kein Sonar + Ping blockiert, gestört → Reichweite ×0.5;
  Waffenzentrale gestört/aus → Torpedo-Start blockiert.
- **U-Boot-Gegenschlag**: Sub-Attribute `torpedoes_left`, `attack_left`;
  Angriff bei EVADE + gehörtem Ping (<30 NM, Raten ~0.04·(0.5+Lärm)·agg/s)
  oder lauter Fregatte (<40 NM, ~0.015·agg/s), `aggression`: diesel_alt 0.5,
  aip_modern 0.7, ssn 1.0; Cooldown 90 s. Feindtorpedos: 28 kn, geradlinig,
  30 NM Reichweite, Treffer bei ≤0.25 NM an der Fregatte.
- **Steuerung Station 4**: `1/2/3` = Team 1/2/3 zum nächsten
  Schadens-Objekt (Cycle); `R` nach Game-Over = Neustart (gleicher Seed).
- **Tests**: `/tmp/opencode/m5_smoke.py` (Treffer→Flut, Reparatur, Sinken,
  Fahrt-Limits, SSN-Angriff, Gegentorpedo-HIT, Game-Over+Restart,
  Game-Loop mit Schaden) – alle grün, M2/M3/M4 ohne Regression.

## 16. Implementierungsstatus M6 (Missions-System)
- **Missions-System** (`src/core/mission.py`): Seed-basierte Missionstyp-Auswahl mit Gewichten
  (Patrouille 40 %, Doppeljagd 25 %, Konvoi-Schutz 20 %, Nuklearer-Abfang 15 %).
  Jeder Typ definiert Boot-Anzahl/-Typen, Tier-/Zivil-Spawn-Bereich und Zeitlimit.
- **Erfolg/Defeat** (GDD §7):
  - Sieg: alle Ziel-Boote versenkt (sink-Modus) bzw. Zeitlimit bei Konvoi überstanden.
  - Niederlage: Fregatte gesunken, politischer Vorfall (Zivilschiff getroffen),
    Ziel-Boot entkommen (>150 NM vom Startpunkt, Torus-Abstand), Zeitlimit abgelaufen.
- **Score**: 1000 pro versenktem U-Boot + Zeitbonus (anteilig, max. 500)
  + 200 pro ungenutztem Torpedo + 500 Zivil-Schutz-Bonus (nur bei Sieg).
- **Historischer M6-Stand**: `S` speicherte Mission, Schiff, Schaden, Teams,
  U-Boote, Tiere, Zivile und Munition. Der aktuelle Stand ist Save v7 mit fünf
  Slots und eingebettetem Welt-Snapshot; siehe §21 und §24.
- **Missions-HUD**: Name, Ziel, Restzeit und Score im Sidepanel (alle Stationen).
 - **Tests**: `/tmp/opencode/m6_smoke.py` (Determinismus, alle 4 Typen, Sieg/Defeat-Pfade,
   Flucht, Zeitlimit, Save/Load-Roundtrip, Game-Loop) – alle grün,
   M2–M5 ohne Regression.

## 17. Implementierungsstatus M7 (Schwierigkeitslevel & Startmenü)
- **Level-Config** (`config.LEVELS`, `LEVEL_ORDER`, `DEFAULT_LEVEL`):
  `leicht` / `normal` / `harte` mit `quiet_mult`, `repair_mult`, `torp_total`,
  `kill_dist_nm` / `kill_depth_m`, `enemy_attack_mult`, `enemy_cooldown_s`,
  `second_sub_prob` / `second_sub_pool`, dazu `label` + `desc` fürs Menü.
- **Startmenü** (`game.py`): `Game(seed, level, start_menu)` zeigt
  `draw_menu()` (Titel, 1/2/3-Auswahl, Seed); `update()` ist im Menü
  inaktiv. Tasten: `1/2/3` Auswahl, `Enter`/`Space`/`KP_Enter` Start
  (setzt Level + `reset(seed)`), `Esc` beendet. `main.py` startet
  immer mit `start_menu=True` und zufälligem Seed (Seed-Arg bleibt).
- **Level-Effekte**: Munition (`harte` 4 statt 6), Torpedo-Treffer-Toleranz
  pro Instanz (`torpedo.py`: `kill_dist_nm` / `kill_depth_m`), Lautstärke
  der U-Boote (`sub.py`: `quiet_mult` auf `quiet_factor`), Reparaturrate
  (`damage.py`: `repair_mult` durch `DamageModel` → `Compartment.update`
  durchgereicht), Gegenangriff (`attack_mult`-Rate + `attack_cooldown_s`),
  zweites Boot nur bei `second_sub_prob > 0` (RNG-Sequenz der M2–M6-Spawns
  bleibt bei `leicht`/`normal` unverändert).
- **HUD**: Level im Sidepanel; Flash beim Start mit Level + Mission.
- **Tests**: `/tmp/opencode/m7_smoke.py` (Level-Config, Level-Spiel-Parameter,
  Reparatur-Faktor, Torpedo-Toleranz, Startmenü-Flow, Determinismus je
  Seed+Level) – grün; M2–M7 ohne Regression.

## 18. Implementierungsstatus M8 (Polish & Vollbild/Scaling)
- **Historischer Scaling-Schritt, heute 1280×720**: Die Logik rendert auf
  `self.screen` mit nativ 1280×720; `Game.compose_frame()` skaliert den Canvas
  auf `self.display`. Die optionale Letterbox-Berechnung bleibt vorhanden.
- **Vollbild**: `F` toggle (Menü + Spiel), Konstrukt-Param `fullscreen=True`,
  CLI-Flag `--fullscreen` in `main.py`; `toggle_fullscreen()` mit
  pygame-Fallback auf `set_mode`; die aktuelle globale Belegung ist
  `Alt+Enter`.
- **End-Panel** (`draw_end_panel()`): SIEG/VERLOREN mit Grund, Score, Mission/Level,
  Restzeit + R/Esc-Hinweis; ersetzt das frühere 2-zeilige HUD-Banner.
- **Pause-Overlay** (`draw_pause_overlay()`): Verdunkelung + „PAUSE / P = weiter";
  zusätzlich **Auto-Pause bei WINDOWFOCUSLOST** (nur im Spiel, nicht im Menü).
- **Flash-Nachrichten** wandern vom Zentrum an den oberen Bildschirmrand
  (bedecken nicht mehr das Sonar-Zentrum).
- **CRT-Scanline-Overlay** (`config.CRT_SCANLINES`, `SCANLINE_ALPHA=14`):
  vorberechnete SRCALPHA-Fläche, pro Frame 1× Blit.
- **Sidepanel-Hilfe** ergänzt: „P Pause | F Vollbild", „S Speichern | L Laden".
- **Tests**: `/tmp/opencode/m8_smoke.py` (letterbox_layout für 1:1/0.5x/Breit-
  und Hochformat, compose_frame bei 640×400, Fullscreen-Konstrukt + Toggle +
  K_f, End-Panel SIEG/VERLOREN in allen Stationen, Pause-Overlay, Scanlines,
  Auto-Pause) – grün; M2–M8 ohne Regression.

## 19. Implementierungsstatus M9 (Sensormatrix, manuelle Klassifizierung, ESM, echtes Vollbild)
- **Sensormatrix (Kern von M9)**: Passives Hören liefert **nur Peilung**
  (`Contact.range_est = None`, `positioned`-Property); Position + Tiefe gibt es
  erst nach **aktivem Ping** (`update_ping()`), nur innerhalb der aktiven
  Reichweite (18 NM × Seegang × Thermokline). `apply_ping()`/`update()` in
  `sonar.py` entsprechend umgestellt; `Contact.decay()` entfernt ungenutzte
  Kontakte (Konfidenz-Abfall + `SONAR_CONTACT_LOST_S`).
- **Geräusch-Signaturen** (`acoustic_signature()` in `sub.py`/`animal.py`):
  „mechanisch · {Antrieb} · {Frequenz nach Zustand/Fahrt}" bzw.
  „biologisch · {Art}". Signatur im Kontakt erst ab
  `CONTACT_SIG_CONF = 0.40` Konfidenz lesbar (Gate in `SonarSystem.update`).
- **Manuelle Klassifizierung**: `player_class`
  (None | U_BOOT | BIOLOGISCH | FAHRZEUG) wird vom Spieler per `C` zykliert
  (Station 2); Kontakt-Auswahl per `←`/`→` (`_cycle_selected_contact`,
  `selected_contact` im Sonar-Panel + Ring-Markierung). Farbe des Kontakts folgt
  der manuellen Klassifizierung (`sonar_view._contact_color`).
- **Start-Gates** (`launch_torpedo()`): (1) Ziel gültig, (2) Kontakt geortet
  („erst pingen"), (3) als U-Boot klassifiziert („nicht als U-Boot
  klassifiziert") – dann erst Munitions-/Station-Checks.
- **ESM** (`game.esm_contacts()`, `civilian.emitter`): Zivile Schiffe mit
  aktivem Radargerät (60 %) liefern jenseits der nominellen
  Seeradarreichweite (30 NM) bis
  `ESM_RANGE_NM = 150` nur **Peilungen** (±3°, deterministisch per
  `c.id*1000 + t//5`); Radar-Station zeigt Peilstriche + Panel-Zeile.
- **UI-Anpassungen**: Sonar-Scope rendert unpositionierte Kontakte als
  Randaufleuchtung („(Peilung)" + Ring), Panel zeigt `Sig.`/`Dst --`;
  Waffenzentrale: Zielkreuz nur bei geortetem Kontakt, sonst Peilstrich +
  Hinweiszeilen („erst pingen", „Klassifizieren: C").
- **Echtes Vollbild (Fix des M8-Feedbacks)**: `Game._desktop_size()` holt die
  tatsächliche Desktop-Auflösung (`pygame.display.get_desktop()`);
  `fullscreen=True` startet mit Desktop-Größe + `FULLSCREEN`-Flag (deckt
  Taskleiste ab), `toggle_fullscreen()` wechselt zu/von 1280×720-Fenster.
  **Fill- statt Letterbox**: `config.FILL_SCREEN = True` streckt den virtuellen
  Canvas auf die gesamte Fensterfläche (keine schwarzen Balken bei 16:9);
  `letterbox_layout()` bleibt für `FILL_SCREEN=False` verfügbar.
- **Desktop-Shortcut**: `/home/db/Desktop/u-jagd.desktop`
  (`Exec=…/main.py --fullscreen`, `Terminal=false`).
- **Save/Load**: `selected_contact` bei `load_state` zurückgesetzt.
- **Tests**: `/tmp/opencode/m9_smoke.py` (passiv nur Peilung, Signatur-Gating,
   Ping→Position+Tiefe+Ausweichen, Kontakt-Verfall, Start-Gates,
   Klassifizierungs-Zyklus, `←/→`-Auswahl mit Wrap, ESM-In-/Auswahl +
   Peilungsfehler, Views mit M9-Zustand, Vollbild-Desktop-Größe + Toggle) –
   grün; M2–M9 ohne Regression (m2/m3/m4 an M9-Anforderungen angepasst:
   Ping-Tests auf 10 NM, Klassifizierung vor Torpedostart,
   `signature` statt `signature_hint`).

## 20. Implementierungsstatus M10–M16 (Szenario 2: „U-Jagd 2010s")

### M10 – Maschinenraum & Telegraph
- `Ship`: `order_idx`, `telegraph`-Property, `cycle_telegraph(delta)`
  (Wrap-Logik über `TELEGRAPH_ORDERS`), `cavitating`, `noise_level()` mit
  Kavitations-Boost (ab `CAVITATION_KN`, `CAVITATION_PASSIVE_FACTOR`),
  `rpm()`, Roll/Pitch in `update(dt, world)` (Seegang-abhängig).
- Steuung: Geschwindigkeit kommt nur noch über den Telegraphen
  (`+`/`-`/Joystick-Trackball Y, `STEER_SPEED`-Raten entfallen); `K_UP/K_DOWN`
  = Ruder außer in der Waffenzentrale (dort = Torpedotiefe 10–300 m).
- Station 8 ENGINE: `draw_engine_view()` (Befehl, RPM, Lärm%, Kavitation,
  Maschinerie-Fehler). Passive Sonar-Reichweite reagiert auf Seegang +
  Kavitation (`passive_sonar_range_nm`).

### M11 – Sonar-Suite
- `SonarSystem.update(..., mode, buoys, focus_tgt)`: Array-Wechsel
  `BOW`/`TOWED` (`SONAR_ARRAY_*_PASSIVE/PING`, `SONAR_TOWED_SPEED_PENALTY`),
  Konvergenzzone-Band (`CZ_BANDS` + `CZ_BONUS_NM`), Bojen-Detektion
  (`sonobuoy.py`, quality 0.9, Konfidenz ×2), LOFAR-Wasserfall
  (`lofar_history`, `LOFAR_SAMPLE_S`, `LOFAR_BINS` – nur fokussiertes Ziel,
  `lofar_lines()` in `sub.py`/`animal.py`).
- Station 2: `draw_lofar_strip()` + Array-/CZ-Labels im Sonar-Scope.

### M12 – OPZ/CIC & EMCON
- Station 5 OPZ: `draw_opz_view()` führt See-, Luft- und Flugkörper-Tracks
  einschließlich JAMMER/HOJ, VLS-Stand, CIWS und Chaff-Kühlzeit. `Auf/Ab`
  wählt einen stabilen CIC-Fokus; `C` setzt die NATO-Zugehörigkeit
  (unbekannt/freundlich/neutral/feindlich). Der Rahmen wird passend zur
  beobachteten Domäne gezeichnet und bleibt bei Trackverlust sowie Save/Load
  erhalten. `Links/Rechts` wählt davon getrennt das ESSM-Ziel.
- `radar_on` schaltet das Radargerät
  (EMCON): `R` schaltet See-, `Shift+R` Luftraumüberwachung; bei
  ausgeschalteten Radaren liefert das Lagebild nur andere Sensorquellen wie
  ESM/HOJ. `Bild Auf/Ab` wählt 10/20/40/80/120 NM Darstellungsbereich. Bei an:
  lokale, kreisbeschnittene Küstenreflexe, rechtsdrehender Sweep und AIS-Tracks
  mit `aspect_rcs_factor` + Seegang-Faktor, ASM-Tracks (Jammer-ASMs jenseits
  `ASM_JAM_BREAK_NM` nur als HOJ-Peilung ±5°).
- Seegang 0–4 beeinflusst Radar nicht. Erst ab Seegang 5 erscheinen
  deterministisches See-/Wetterclutter, größere Messfehler und reduzierte
  effektive Reichweite; Clutter wird nie zum auswählbaren Track.
- `Station.RADAR` ist nur noch ein Alias der gemeinsamen OPZ/CIC-Station.

### M13 – Funkraum & HFDF
- Station 7 RADIO: `draw_radio_view()` (HFDF-Peilungen, Teletype-Band
  `messages`/Cap 40, Morse-Ticker `_to_morse`).
- U-Boot: `SNOCKEL`-Zustand (`SNOCKEL_DURATION_S`, nur Diesel/AIP bei
  `SNOKEL_TRIGGER_PPS`/Luftdruck-Analog), `transmitting`, lauterer
  `quiet_factor` (`SNOCKEL_TRANSMIT_NOISE`), Signatur „Funkverkehr".
- `hfdf_bearings()`: Peilung ±`HFDF_BEARING_ERR_DEG` nur bei Senden und
  ≤ `HFDF_RANGE_NM`; Wetter-Bulletins per Teletype alle
  `WEATHER_BULLETIN_PERIOD_S` (`hq_msg` in `game.update`).

### M14 – Schadens-Modell 2.0 (Feuer)
- `ship/damage.py`: `Compartment.fire`, `hit(rng)` startet Brand
  (`DMG_FIRE_START`, `DMG_FIRE_START_CHANCE`), `update(dt, repaired,
  repair_rate, fire_teams)` (Brandausbreitung `DMG_FIRE_SPREAD_PPS`, Löschrate
  `DMG_FIRE_REPAIR_RATE`), `repair_candidates()`/`station_degraded()` inkl.
  Feuer; `DamageModel.update()` propagiert Brände zwischen Abteilungen.
- Station 4: Seitenriss-View `draw_damage_view()` (6 Abteilungen, Feuer
  markiert, Cursor `←/→` mit Wrap + Joystick).

### M15 – Waffensystem 2.0 (Drahttorpedo, HSP-5)
- `torpedo.py`: Drahtführung – jenseits `TORP_HOME_RANGE_NM` Serpentin-Suchlauf
  (Sinus um Mittelkurs, `TORP_MIDCOURSE_UPDATE_S`, Amplituden-Fade-out),
  darunter Zielverfolgung (100°/s Ruder) mit Drosselung bei >60° Kursabweichung
  (verhindert Ziel-Orbits); Tiefe per proportionalen Regelkreis;
  `speed_kn`-Parameter (Leichttorpedo).
- `helicopter.py` (Sea Lynx HSP-5): `HANGAR`/`AUF`/`ZURUECK`, Patrouillen-Offset
  vor der Fregatte, `deploy_buoys()` (`BUOY_SPACING_NM`, Batterie
  `BUOY_BATTERY_S`), `drop_torpedo()` (`HELO_TORP_SPEED_KN`, eigene Munition
  `HELO_TORPS`).
- Start-Gates erweitert um ROE: `launch_torpedo()`/`launch_helo_torpedo()`
  (STD = geortet + klassifiziert, FREE = klassifiziert; Salven-Doktrin
  `TORP_DOCTRINE`/`TORP_MAX_IN_AIR`).
- Station 3: HSP-5-Zeile, Salven-Doktrin, Torpedotiefe per `↑/↓`.

### M16 – Flak (ASM-Wellen, CIWS, ESSM, Chaff)
- `mission.py`: `asm_count` aus `spec["asm"]`, Zieltext „… N× ASM!".
- `asm.py`: feindliche ASMs (Homing oder Jammer→HOJ, `ASM_JAM_BREAK_NM`,
  Chaff-Reaktion `CHAFF_BREAK_P`) + eigene `ESSM` (VLS,
  `ESSM_RANGE_NM`/`ESSM_KILL_DIST_NM`); `game._maybe_spawn_asm()` (Wellen zu
  `ASM_SPAWN_FIRST_S`/`INTERVAL`), CIWS-Autoshot (`CIWS_RANGE_NM`,
  `CIWS_KILL_PPS`), Chaff (`CHAFF_RANGE_NM`/`COOLDOWN`), ESM-Quietschen im
  Teletype.
- **ROE-FREE nach erstem Kill**: versenkt ein Torpedo ein U-Boot, schaltet
  `game.update` die `roe` automatisch auf FREE (HQ-Meldung im Teletype).
- Save/Load: `torpedo_seq`, `buoy_seq` zusätzlich persistiert.
- **Tests**: `/tmp/opencode/m10_smoke.py` … `m16_smoke.py` – grün; M0–M16 ohne
   Regression (m4: Serpentin-Suchlauf neu validiert; m9: Station-Scoping für
   `←/→/C`).

## 21. Implementierungsstatus M17–M19 (Architektur, Persistenz, ASW-Tiefe)

- **M17 Architektur**: Der Simulationsschritt ist in Navigation, Unterwasser-
  Entitäten, Luftfahrt, Fliegerabwehr, Feindtorpedos, eigene Torpedos, Sensorik
  sowie Schaden/Mission getrennt. `Game` orchestriert die Reihenfolge.
- **M18 Persistenz**: Save-Version 3 stellt Weltzeit/Wetter, RNG-Zustände,
  Sonarkontakte/LOFAR, laufende Waffen, Bojen, Flugverkehr und KI-Zustände
  wieder her. Version 1/2 bleiben mit Defaults ladbar.
- **M19 ASW-Modell**: Kontakte führen Reichweiten-/Tiefenunsicherheit; TMA-
  Qualität beeinflusst die Entfernungsstreuung. U-Boote besitzen lokales
  taktisches Gedächtnis und Utility-Scores für Verstecken, Lauer, Angriff und
  Flucht. Fregattentreffer berücksichtigen die Angriffsrichtung und bevorzugte
  Trefferzonen.
- **Tests**: Repository-Test-Suite unter `tests/` mit Determinismus-,
  Persistenz-, Sensorik-, TMA-, KI-, Schadens- und Headless-Smoke-Tests.

## 22. Implementierungsstatus M20–M21 (Audio und Echo-Pipeline)

- **M20 Audio**: `src/audio/engine.py` bietet fehlertolerante Pygame-Ausgabe,
  gecachte NumPy-Synthese fuer Ping und Maschinen-/Propellerbloecke. Audio ist
  blockweise und nicht pro Frame erzeugt; ohne Audiogeraet laeuft die Simulation
  lautlos weiter.
- **M21 Akustikanalyse**: `src/audio/demon.py` berechnet ein DEMON-
  Huellenspektrum mit Blattfrequenz, RPM-Kandidaten, Konfidenz und
  Kavitation. `database.py` enthaelt transparente Kandidatenscores fuer
  Diesel-, AIP-, SSN-, Zivil-, Biologie- und Dekoy-Signaturen.
- **Aktivsonar**: Ein Ping erzeugt die U-Boot-Warnung sofort; Echo-Kontakte
  werden erst nach der Schalllaufzeit `2R/c` aktualisiert. Ausstehende Echos
  werden gespeichert und geladen.
- **Stations-Audit**: Bedienung und Übergaben zwischen Stationen werden durch
  `tests/test_stations.py` sowie den vollständigen Headless-Smoke-Test geprüft.

## 23. Kontakt-DB, Fingerprints & Kampfschiff (aktuelle Runde)

- **Kontakt-DB als SSoT**: `src/data/catalog.py` ist die einzige Quelle für
  alle Plattformprofile (23 U-Boote, 25 Kampfschiffe, 55 Zivile, 2 Flugzeug-
  Profile, 3 Tiere, 3 Torpedos, 1 Dekoy). Exportiert nach
  `data/contacts/*.json` (Schema: `docs/contacts-db.md`);
  `tools/gen_contacts.py` erzeugt/prüft die Dateien. Die alte
  `src/audio/database.py` ist nur noch ein Kompatibilitäts-Shim.
- **Per-Instanz-Fingerprint** (`src/data/fingerprint.py`): Jede Entität
  (U-Boot, Schiff, Dekoy) trägt einen aus `sensor_seed` deterministisch
  gerollten Fingerprint (Blattzahl, Tacho-Faktor ±15 %, Ton-Offsets ±0.5 Hz,
  Kavitations-/Breitband-Skalierung) – seit Save v4 gespeichert und geladen;
  das aktuelle Format ist Save v7.
- **Breitband-Akustik**: `AcousticReceiver.update(..., own_cavitation=0.0)`
  mischt pro-Quelle bandlimitiertes Rauschen (`broadband`-Dict) und die
  eigene Kavitation (80–380 Hz, bei `ship.cavitating`). Ohne Daten bleibt
  das Audio bit-identisch (21 Receiver-Tests).
- **Feindtorpedos hörbar**: `EnemyTorpedo` liefert LOFAR-Linien
  (Subharmonische 45–75 Hz + Tonales 90–150 Hz) und Breitband; Sonar-Kontakte
  erhalten `kind="torpedo"`, Feed zeigt „Torpedo-Verdacht".
- **KAMPFSCHIFF**: Neue Spielerklasse (Klassifizierung C bei Radar/ESM-
  Track). Feindliche Kriegsschiffe (`SurfaceShip(hostile=True)`,
  `src/enemies/surface.py`) loiteren um die feindliche Basis, feuern ASM-
  Salven (< 35 NM), sind im Radar (Hostile-AIS-Tracks), ESM und Sonar
  (kind="surface") sichtbar. Torpedos dürfen sie versenken (3 Treffer,
  +1000 Punkte). Save/Load v4 speichert `warships`-Block.
- **Zivile im Sonar**: Zivilschiffe erscheinen jetzt auch als passive
  Sonarkontakte (kind="surface", `kind="sub"` nur für U-Boote); die alte
  Regel „Zivile nie im Sonar" (siehe §14) ist damit abgeschafft.
- **Missions-Spec**: `warships`-Ziehung pro Mission (patrouille 0–1,
  doppeljagd/konvoi 1–2, nuklearer_abfang 0–1); Briefing benennt die Anzahl.
- **Tests**: `tests/test_contacts_catalog.py`, `tests/test_fingerprint.py`,
  `tests/test_warship.py` (zusätzlich zu den 259 Baseline-Tests; aktuell
  278 grün, Smoke-Test durchläuft).

## 24. Reale Sektoren, Kartendarstellung und Save v7

- `data/coastlines/real_sectors.json.gz` enthält genau 128 reale,
  vorvalidierte 500-NM-Sektoren. `seed % 128` wählt stabil den Sektor.
- Natural Earth liefert abgeleitete Küsten- und Ländernamen; ein fixierter
  Wikidata-Snapshot liefert reale Militärstützpunktnamen und Koordinaten. Exakte
  Versionen, Prüfsummen, Transformationen und Rechte stehen in
  `THIRD_PARTY_NOTICES.md`. Es gibt keine Billigung durch die Quellenanbieter.
- Gameplay-Zugehörigkeiten der Stützpunkte sind unabhängig vergebene fiktionale
  Übungsrollen. Die Bathymetrie wird synthetisch erzeugt. Sämtliche Kartendaten
  sind nicht navigationstauglich.
- Die feste `data/coastlines/region.json` bleibt als Legacy-Kartenoption.
- Geografische Karten und Radar-PPI verwenden einen dunkelblauen gemeinsamen
  Hintergrund. Der eigene HSP-5 wird auf Karte und PPI als freundliches
  NATO-ähnliches Luftsymbol dargestellt.
- Save v7 speichert den kanonischen Welt-Snapshot einschließlich Geometrie,
  Stützpunkten, Provenienzmetadaten und Bathymetrie. Ein gespeicherter Sektor
  wird beim Laden direkt restauriert und nicht neu generiert.
