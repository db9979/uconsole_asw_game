"""Globale Konfiguration & Einheitenkonversionen.

Einheiten: Nautische Meilen (NM) und Knoten (kn).
1 kn = 1 NM/h.

Layout: Widescreen-Grid 1280x720 (Top-Bar / 2x Hauptpanel / Bottom-Feed).
"""

import math
import os

from src.data.catalog import CATALOG


def _required_catalog_profile(kind: str, key: str):
    profiles = getattr(CATALOG, kind, None)
    if profiles is None or key not in profiles:
        raise RuntimeError(
            f"Kontaktkatalog unvollstaendig: {kind}-Profil '{key}' fehlt")
    return profiles[key]


_DECOY_PROFILE = _required_catalog_profile("decoys", "decoy")
_HELO_TORP_PROFILE = _required_catalog_profile("torpedoes", "helo_torp")

# Display: virtuelles 1280x720-Canvas (uConsole: Stretch per FILL_SCREEN).
SCREEN_W = 1280
SCREEN_H = 720
FPS = 60
# Keep tactical circles and bearings geometrically correct on arbitrary windows.
# Unused space is letterboxed instead of stretching the virtual canvas.
FILL_SCREEN = False
# Selectable frame-rate cap (settings.json "frame_rate"). 30 FPS halves render
# work on the uConsole and leaves CPU/GIL headroom for the audio pump and the
# Remote Crew server threads; FPS stays the canvas/test reference maximum.
FPS_CHOICES = (30, 60)
FPS_DEFAULT = 30
# Main loop: no single frame advances the simulation by more than
# SIM_FRAME_DT_MAX, but wall time lost to a slow frame is carried as a bounded
# debt and caught up over the following frames. Sonar audio is produced in
# simulation time and played in wall time, so dropping that time would drain
# every playback buffer. Debt beyond SIM_CATCHUP_MAX_S (a real hang) is dropped.
# 2.5 s matches the sonar listening leads (1.5 s local, 2 s browser) so a
# stall that long is concealed and then fully caught up instead of cut.
SIM_FRAME_DT_MAX = 0.1
SIM_CATCHUP_MAX_S = 2.5
AUDIO_ENABLED = True
AUDIO_SAMPLE_RATE = 22050
AUDIO_UPDATE_S = 0.25
# Solo Remote Crew: while the paired browser is live the uConsole only redraws a
# small status screen (display only; the simulation is unaffected).
ECO_REDRAW_S = 0.25
ECO_PRESENCE_POLL_S = 0.5
ECO_PRESENCE_MAX_AGE_S = 5.0
# Pygame specifies its mixer buffer in samples. 2048 samples are about 93 ms
# at 22050 Hz: the SDL audio thread then survives PipeWire/CPU scheduling
# hiccups of that length on the uConsole without an xrun crackle (one-shot
# cues start up to 93 ms later, which is not noticeable). Longer gaps are
# handled in software: locally by the AudioEngine's buffered-sonar queue
# (SONAR_BUFFER_MAX_S), and for Remote Crew by the server's 40-block ring
# buffer of 0.25 s blocks, ~10 s (SONAR_AUDIO_RING_BLOCKS in
# src/commander/server.py).
AUDIO_MIXER_BUFFER_SAMPLES = 2048
# Mono output: halves per-block synthesis, resampling and mixer workload on
# the low-power uConsole; stereo bearing panning is skipped in mono.
AUDIO_CHANNELS = 1
# Bounded size of the optional U_JAGD_PERF_DEBUG main-loop timing log; see
# Game._perf_debug_log. Mirrors AudioEngine.DEBUG_LOG_MAX_BYTES.
PERF_DEBUG_LOG_MAX_BYTES = 1_000_000

# M8: CRT-Scanline-Overlay (subtiler Phosphor-Look)
CRT_SCANLINES = False
# W2: Rotlicht-Nachtmodus (Preferences.night_mode) - Multiply-Blend-Farbe
NIGHT_MODE_COLOR = (255, 60, 60)
SCANLINE_ALPHA = 14

# --- W0: 3-Teil-Grid (Widescreen 1280x720) ---
TOP_BAR_H = 30                       # oberer Statusbalken
BOTTOM_H = 180                       # Funk-Log & Telemetrie
MAIN_TOP = TOP_BAR_H                 # 30
MAIN_BOTTOM = SCREEN_H - BOTTOM_H    # 540
MAP_RECT = (0, MAIN_TOP, 640, MAIN_BOTTOM - MAIN_TOP)          # (0,30,640,510)
STATION_RECT = (640, MAIN_TOP, 640, MAIN_BOTTOM - MAIN_TOP)    # (640,30,640,510)
STATION_PANEL_RECT = STATION_RECT
FULL_STATION_RECT = (0, MAIN_TOP, SCREEN_W, MAIN_BOTTOM - MAIN_TOP)
OPZ_STATION_RECT = (0, MAIN_TOP, SCREEN_W, SCREEN_H - MAIN_TOP)
FEED_RECT = (0, MAIN_BOTTOM, 960, BOTTOM_H)                    # (0,540,960,180)
TELEMETRY_RECT = (960, MAIN_BOTTOM, 320, BOTTOM_H)             # (960,540,320,180)
BOTTOM_PANEL_MODES = ("ticker", "docked")  # see layout.bottom_panel_regions
TICKER_SCROLL_PX_S = 40.0           # marquee speed for a long ticker line (wall time)

# --- Zeitsteuerung: eine gemeinsame physikalische Simulationszeit ---
# Das Spiel laeuft immer in Echtzeit, ohne Pause und ohne Zeitraffer:
# 1 reale Sekunde = 1 Simulationssekunde.
# Spielminuten pro Simulationssekunde: ergibt eine reale 24-h-Uhr.
GAME_TIME_PER_SEC = 1.0 / 60.0
PHYS_SUBSTEP_S = 0.05             # max. sim-Sekunden pro Physik-Substep (Anti-Tunneling:
                                  # 45 kn legen in 0.05 s ca. 0.000625 NM zurueck)
PHYS_SUBSTEP_MAX = 240
MAP_ZOOM_MIN_PX_PER_NM = 1.0      # ganze Welt sichtbar (500 NM in 510 px)
MAP_ZOOM_MAX_PX_PER_NM = 1400.0   # Detail-Zoom (0.5 NM in 668 px Kartenhoehe)
MAP_ZOOM_DEFAULT_PX_PER_NM = 10.0 # Start-Zoom (~51 NM hoch, ~64 NM breit)
MAP_ZOOM_WHEEL_FACTOR = 1.25      # stufenlos pro Mausrad-Schritt
# Q/E springen auf feste Kartenhoehen (NM), von der ganzen Welt bis 0.5 NM.
MAP_ZOOM_STEPS_NM = (500.0, 250.0, 100.0, 50.0, 25.0, 10.0, 5.0, 2.0, 1.0, 0.5)
OPZ_MAP_DEFAULT_RADIUS_NM = 40.0
OPZ_MAP_MAX_ZOOM_RADIUS_NM = 0.25

# Welt
WORLD_SIZE_NM = 500.0     # quadratische Welt in NM
# W2: Meeresstroemung - raumabhaengiges, aber schwaches Feld (Schelfmeer-
# Groessenordnung); wirkt als reiner Driftzusatz zur eigenen Fahrt.
CURRENT_MAX_KN = 1.0
NM_PER_PX_MAP = 1.0

# Fregatte
SHIP_SPEED_MIN_KN = 4.0
SHIP_SPEED_MAX_KN = 31.0
# 1.0.0 top speed: own noise and wake keep their 1.0.0 scale below it and
# only grow further between 25 kn and SHIP_SPEED_MAX_KN.
SHIP_SPEED_REFERENCE_KN = 25.0
SHIP_SPEED_START_KN = 12.0
SHIP_TUR_RATE_DEG_PER_S = 0.8         # max. Kurssatz des Schiffes
SHIP_TURN_INPUT_DEG_PER_S = 75.0      # Zielkurs-Drehung bei gedrückter Taste
SHIP_SPEED_RESP_KN_PER_S = 0.08       # ca. 2-4 min bis volle Fahrt (Legacy-Name)
# W2: hydrodynamische Fahrtantwort - Exponential-Verzug statt fixer Rampe
# (Schub/Widerstand-Gleichgewicht: schnelle Anfangsbeschleunigung, die sich
# asymptotisch dem Zielwert naehert, statt linear bis zum Anschlag zu laufen).
SHIP_SPEED_TAU_S = 40.0
SHIP_SPEED_INPUT_KN_PER_S = 3.0       # Zielgeschw.-Anpassung bei gedrückter Taste

# Sonar (Captain's Log §1)
SONAR_PASSIVE_BASE_NM = 20.0          # Basis-Grundreichweite passiv
SONAR_ACTIVE_BASE_NM = 18.0           # Basis-Grundreichweite aktiv (Ping)
SONAR_PING_COOLDOWN_S = 30.0          # Sende-/Auswertezyklus
SONAR_PING_FIX_MAX_AGE_S = 120.0      # Unsicherheit waechst danach stark
SONAR_PING_HEAR_RANGE_NM = 60.0       # Intercept deutlich weiter als Echo
# Bearing error (1 sigma) of a foreign active ping heard by ear, as the
# crewed boat's alarm bearing.
PING_INTERCEPT_SIGMA_DEG = 2.0
SONAR_PING_RANGE_ERROR_NM = 0.18      # max. gleichverteilter Messfehler
SONAR_PING_DEPTH_ERROR_M = 12.0       # max. gleichverteilter Messfehler
SONAR_ECHO_HISTORY_MAX = 80           # persistente ACTIVE-Beobachtungen
SONAR_THERMO_PASSIVE_ABOVE = 1.15     # Ziel über Thermokline: besser
SONAR_THERMO_PASSIVE_BELOW = 0.55     # Ziel unter Thermokline: schlechter
SONAR_THERMO_ACTIVE_BELOW = 0.35      # Ping in Schattenzone
SONAR_PASSIVE_RANGE_ERR = 0.25        # passive Distanz-Schätzung +/-25 %
SONAR_CONF_PASSIVE_PER_S = 0.012      # Verarbeitung braucht belastbare Historie
SONAR_CONF_PING_BONUS = 0.30          # Konfidenz-Sprung pro Echo
SONAR_CONF_DECAY_PER_S = 0.003        # langsames Auslaufen einer Spur
SONAR_CONTACT_LOST_S = 120.0          # taktisch nutzbare Track-Historie

# W1: SNR-/Peilmodell (faktorielle Dekomposition der passiven Reichweite)
# SNR_dB = 20*log10(R_eff/d)  –  R_eff aus folgenden Faktoren:
SONAR_SNR_DETECT_DB = 0.0            # Grenzwert: SNR >= 0 dB = detektiert
SONAR_SNR_QUALITY_SPAN_DB = 14.0     # SNR bei dem Qualität=1.0 (0 dB = ~0)
# (Peilfehler: siehe unten, Block "W1: TMA" – BEARING_ERR_*)

# W2: Schallausbreitung (Captain's Log §1)
SOUND_SPEED_M_S = 1500.0             # Schall in Salzwasser
THERMO_SHADOW_BONUS_DB = 22.0        # Brechung an Sprungschicht: Schattenzone
CZ_CONVERGENCE_GAIN_DB = 8.0         # Konvergenzzone: Fokus unterhalb/oberhalb

# U-Boot-KI (M2: Patrouille + Ausweichen; sim-Sekunden)
SUB_EVADE_DURATION_S = 240.0
# W2: Tiefenaenderung mit Traegheit statt sofort voller Rate (Auftrieb/
# Anstellwinkel-Ersatz) - begrenzt, wie schnell sich depth_rate_mps aendert.
SUB_DEPTH_ACCEL_MPS2 = 0.15
SUB_PATROL_TURN_PERIOD_S = 600.0
# W2: Taktik-Erweiterung
SUB_LUER_DURATION_S = (300.0, 900.0) # LAUER: still liegen + lauschen
SUB_LUER_DIST_NM = 25.0              # LAUER nur, wenn Fregatte naeher
SUB_TORPEDO_ALERT_NM = 35.0          # Torpedostart akustisch hörbar
# W2: aggressive Boote riskieren gelegentlich einen aktiven Ping zur
# Zielaufklärung - laut, sofort gehört, kein Dauerzustand (nur Peilung/Flash,
# keine Feuerlösung).
SUB_ACTIVE_PING_MIN_AGGRESSION = 0.6
SUB_ACTIVE_PING_MAX_RANGE_NM = 15.0
SUB_ACTIVE_PING_CHANCE_PER_S = 0.01
SUB_ACTIVE_PING_COOLDOWN_S = 120.0
# Kompatibilitaetsnamen; das geladene JSON-Profil ist die Laufzeitquelle.
SUB_DECOY_CHANCE = _DECOY_PROFILE.chance
SUB_DECOY_LIFE_S = _DECOY_PROFILE.life_s
SUB_DECOY_COOLDOWN_S = _DECOY_PROFILE.cooldown_s
SUB_DECOY_SPEED_KN = _DECOY_PROFILE.speed_kn

# M4: Zivile Schiffe & Radar
CIVILIAN_HIT_RADIUS_NM = 0.2   # Torpedo-Annäherung, die als Vorfall zählt
RADAR_RANGE_NM = 40.0          # Kompatibilitaetswert
RADAR_SURFACE_RANGE_NM = 30.0
RADAR_AIR_RANGE_NM = 100.0

# KAMPFSCHIFF (Kontakt-DB): feindliche Kriegsschiffe loiteren um ihre Basis
# und feuern ASM-Salven, wenn die Fregatte in Reichweite ist.
WARSHIP_ASM_RANGE_NM = 35.0    # Abstand, ab dem Salven möglich sind
WARSHIP_TORPEDO_DECOYS = 2       # acoustic decoys a combatant can stream
WARSHIP_TORPEDO_EVADE_S = 90.0  # W2: Torpedoalarm -> harte Wende, dann weiter

# M5: Schadensmodell (Raten in sim-Sekunden)
DMG_FLOOD_RATE = 0.10          # schwere Flutung: Minuten bis kritisch
DMG_LEAK_RATE = 0.025          # stabilisierte Restleckage
DMG_REPAIR_RATE = 0.12         # Abpumpung pro Reparaturteam
DMG_DESTROY_FLOOD = 70.0       # % Flutung -> Kompartiment ZERSTOERT
DMG_SHIP_SINK_TOTAL = 540.0    # 60 % mittlere Flutung über neun Räume
DMG_SONAR_DEGRADED_FACTOR = 0.5  # Sonar-Reichweitenfaktor bei gestörter Sonarzentrale
ENEMY_TORP_SPEED_KN = 40.0
ENEMY_TORP_RANGE_NM = 20.0
ENEMY_TORP_HIT_DIST_NM = 0.25
ENEMY_TORP_QUIET = 0.10            # laut – passiv gut auffindbar
SUB_ATTACK_COOLDOWN_S = 90.0
# An AI boat with a located frigate this close attacks even a quiet frigate
# (per-second chance x aggression); a loud frigate draws fire from 18 NM.
SUB_SOLUTION_ATTACK_NM = 10.0
SUB_SOLUTION_ATTACK_RATE = 0.003

# M9: Sensormatrix & manuelle Kontakt-Klassifizierung
# Passiv (Geräusche): nur Peilung. Ping: Position+Tiefe. Radar: Position.
# ESM: nur Peilung von Radargeräten ziviler Schiffe.
ESM_RANGE_NM = 150.0            # ESM-"Reichweite" (Peilung von Radargeräten)
ESM_BEARING_ERR_DEG = 3.0       # ESM-Peilungsfehler (± Grad)
ESM_EMITTER_PROB = 0.6          # Anteil ziviler Schiffe mit aktivem Radargerät
# Bridge lookout: explicit horizon/recognition assumptions. A submarine is
# visually surfaced only at or above 2 m; at periscope or snorkel depth only
# its raised mast and feather are seen (LOOKOUT_FEATHER_RANGE_NM for the full
# plume by day in calm, clear air; a slow head shows much less).
LOOKOUT_SURFACE_RANGE_NM = 12.0
LOOKOUT_SUB_RANGE_NM = 5.0
LOOKOUT_AIR_RANGE_NM = 20.0
LOOKOUT_SUB_SURFACED_MAX_DEPTH_M = 2.0
LOOKOUT_FEATHER_RANGE_NM = 3.5
# The crewed boat's crew warns of a visible feather above this speed.
UBOOT_FEATHER_WARN_KN = 5.0
LOOKOUT_NIGHT_FACTOR = 0.35
# The 24-hour clock's daylight window (lookout, chart tint, bridge sky).
DAYLIGHT_START_H = 5.5
DAYLIGHT_END_H = 19.5
DUSK_HALF_WIDTH_H = 1.0            # chart tint: "dusk" this close to either edge
LOOKOUT_SEA_STATE_LOSS = 0.08
LOOKOUT_BEARING_ERR_DEG = 0.6
LOOKOUT_RANGE_ERR_FRAC = 0.06
LOOKOUT_EPOCH_S = 0.5
# Crewed hostile submarine (manual crew controls; the AI never uses these).
UBOOT_SILENT_MAX_KN = 5.0          # silent running: speed ceiling
UBOOT_SNORKEL_MAX_KN = 6.0         # snorkelling: speed ceiling (mast drag)
# Surfaced (fully up, src/enemies/sub.py ``command_surface``): diesels run in
# the open air, a bridge watch looks out, a crash dive floods the tanks first.
UBOOT_SURFACED_DEPTH_M = 2.0       # at or above this the boat is surfaced
UBOOT_SURFACE_MAX_KN = 12.0        # on the diesels at the surface (or the boat's maximum)
UBOOT_SURFACE_DIESEL_FACTOR = 1.3  # generator power without the snorkel head's losses
UBOOT_MBT_LP_BLOW_S = 120.0        # low-pressure blower empties the main ballast
UBOOT_BRIDGE_EYE_HEIGHT_M = 6.0    # the bridge watch on the conning tower
UBOOT_CRASH_DIVE_DEPTH_M = 40.0    # a crash dive's ordered depth (within safe depth)
UBOOT_CRASH_DIVE_NOISE_S = 8.0     # flooding vents: a transient the enemy may hear
UBOOT_BOTTOM_CLEARANCE_M = 3.0     # lying on the bottom: keel clearance
UBOOT_BATTERY_WARN_FRACTION = 0.20 # battery warning / nearly empty
UBOOT_BATTERY_EMPTY_FRACTION = 0.03
UBOOT_SPEED_STEPS_KN = (0.0, 3.0, 6.0, 10.0, 15.0)   # telegraph steps (+ maximum)
UBOOT_SALVO_SPREAD_DEG = 4.0       # two-torpedo spread: +/- this
# Save v15: a loaded crewed boat keeps its crew binding this long (sim
# seconds) while no station is held, so a returning crew resumes its orders;
# afterwards the AI takes the boat back as after a crew's departure.
UBOOT_RESTORE_HOLD_S = 600.0
UBOOT_TORPEDO_MIN_DEPTH_M = 5.0
UBOOT_TORPEDO_MAX_DEPTH_M = 300.0
UBOOT_WIRE_TURN_DEG_S = 8.0       # wire-steered torpedo turn rate
UBOOT_WIRE_MAX_KN = 10.0           # own speed that strains the wire
UBOOT_WIRE_MAX_YAW_DEG_S = 1.5
UBOOT_OBSTACLE_LOOKAHEAD_NM = 5.0  # chart check ahead of the ordered course
UBOOT_UNDER_KEEL_WARN_M = 15.0
UBOOT_LAYER_MARGIN_M = 15.0   # depth presets: this far above / twice below the layer
UBOOT_PRESET_MIN_M = 20.0
# Counter-detection picture of the crewed boat (display only, never saved):
# intercepted pings by source (the intercept receiver tells them apart by
# frequency), their received level and buoy splashes heard by the sonar room.
UBOOT_PING_SOURCE_DB = {"hull": 225.0, "dipping": 217.0, "buoy": 205.0}
UBOOT_PING_ECHO_LIKELY_DB = 150.0   # a ping this loud surely returned an echo
UBOOT_INTERCEPTS_MAX = 24
UBOOT_THREAT_WINDOW_S = 300.0       # the threat page summarises this long
UBOOT_BUOY_PING_HEAR_NM = 12.0      # an active buoy's ping reaches the boat
UBOOT_SPLASH_HEAR_NM = 4.0          # a buoy entering the water is heard
UBOOT_SPLASH_SIGMA_DEG = 6.0
# Diesel boats at snorkel depth: the running diesels raise the radiated
# level and add firing-rate lines to the boat's LOFAR signature (plan 1.3,
# phase 9; the catalog keeps its 1.0.0 acoustic profiles unchanged).
# Seeded random groups of a user mission: members start at this course-free
# speed and depth (course from the mission seed).
MISSION_GROUP_SPEED_KN = 4.0
# A placed aircraft patrols a box of this half-width around its position.
MISSION_AIRCRAFT_LOITER_NM = 10.0
MISSION_GROUP_DEPTH_M = 60.0
UBOOT_SNORKEL_NOISE_DB = 12.0
UBOOT_SNORKEL_LINES = ((50.0, 0.85, 2.0), (100.0, 0.55, 1.5))  # (Hz, amp, width)
UBOOT_SNORKEL_QUIET_LOSS = 0.25
# Snorkel charge rate of a crewed diesel boat (the AI always charges at full
# rate): fraction of generator power, radiated-level and quietness penalty,
# and diesel-line amplitude.  "vent" runs only the fans through the snorkel
# to air the boat (no diesels, no charging).
UBOOT_CHARGE_RATES = ("full", "half", "vent")
UBOOT_CHARGE_POWER = {"full": 1.0, "half": 0.5, "vent": 0.0}
UBOOT_CHARGE_NOISE_DB = {"full": 12.0, "half": 9.0, "vent": 4.0}
UBOOT_CHARGE_QUIET_LOSS = {"full": 0.25, "half": 0.18, "vent": 0.06}
UBOOT_CHARGE_LINE_SCALE = {"full": 1.0, "half": 0.7, "vent": 0.0}
# Radio room of the crewed boat (fictional schedule).  HQ sends a new
# submarine broadcast every BROADCAST_S; copying needs the antenna (raised
# mast at periscope depth) up for COPY_S.  A situation report is TX_S of HF
# transmission (HF-DF can bear it).  A broadcast carries a contact report on
# the frigate with probability INTEL_P (always after a situation report,
# then with the sharper radius); the report is AGE_S old.
UBOOT_RADIO_BROADCAST_S = 600.0
UBOOT_RADIO_COPY_S = 20.0
UBOOT_RADIO_TX_S = 20.0
UBOOT_RADIO_LOG_MAX = 12
UBOOT_RADIO_INTEL_P = 0.6
UBOOT_RADIO_REPORT_AGE_S = (300.0, 900.0)
UBOOT_RADIO_REPORT_RADIUS_NM = 4.0
UBOOT_RADIO_REPORT_SHARP_NM = 2.0
# VLF: the loop antenna copies the broadcast down to VLF_DEPTH_M without the
# mast, but the slow VLF signal needs VLF_COPY_S.  From broadcast
# ORDER_FIRST on, a broadcast carries a new HQ order with probability
# ORDER_P while none is open, at most ORDER_MAX per mission: proceed to an
# area (AREA_NM away, RADIUS_NM wide, within AREA_S), send a situation report
# within REPORT_S, or keep radio silence for SILENCE_S.
UBOOT_RADIO_VLF_DEPTH_M = 25.0
UBOOT_RADIO_VLF_COPY_S = 60.0
# Towed buoy antenna (src/core/buoy_antenna.py): copies the broadcast down to
# BUOY_DEPTH_M at BUOY_SPEED_KN or less; the cable parts above BUOY_TEAR_KN.
UBOOT_BUOY_DEPTH_M = 60.0
UBOOT_BUOY_SPEED_KN = 6.0
UBOOT_BUOY_TEAR_KN = 10.0
UBOOT_BUOY_STREAM_S = 60.0
UBOOT_BUOY_COPY_S = 30.0
UBOOT_BUOY_TRAIL_NM = 0.15            # cable length astern (~280 m)
UBOOT_BUOY_RCS_FACTOR = 0.004         # radar echo relative to a ship (a mast is 0.01)
UBOOT_BUOY_HEIGHT_M = 0.3             # above the water (radar horizon)
UBOOT_BUOY_VISUAL = 0.3               # eye contrast vs. a mast's full feather (bare head 0.15)
# Dead reckoning of a crewed boat (src/core/boat_nav.py): dived, the navigated
# position drifts at up to DR_DRIFT_KN (a nuclear boat's inertial navigation
# at DR_NUCLEAR_FACTOR of it) plus a random walk of DR_WALK_NM a minute, up to
# DR_ERROR_MAX_NM; GPS_FIX_S with the mast raised at periscope depth fixes it.
UBOOT_DR_DRIFT_KN = 0.4
UBOOT_DR_WALK_NM = 0.02
UBOOT_DR_NUCLEAR_FACTOR = 0.3
UBOOT_DR_ERROR_MAX_NM = 8.0
UBOOT_DR_SURFACE_M = 3.0
UBOOT_GPS_FIX_S = 20.0
UBOOT_ORDER_FIRST = 2
UBOOT_ORDER_P = 0.5
UBOOT_ORDER_MAX = 4
UBOOT_ORDER_AREA_NM = (8.0, 15.0)
UBOOT_ORDER_RADIUS_NM = 3.0
UBOOT_ORDER_AREA_S = 2400.0
UBOOT_ORDER_REPORT_S = 1800.0
UBOOT_ORDER_SILENCE_S = 1200.0
UBOOT_ORDER_MIN_DEPTH_M = 60.0     # an ordered area lies in water this deep
# Diesel fuel of conventional boats (fictional): the bunkers hold this many
# hours of full generator power; a mission starts mid-patrol at this fill.
# Displayed as litres of diesel per kWh of generator output.
UBOOT_DIESEL_ENDURANCE_H = 300.0
UBOOT_DIESEL_START_FRACTION = 0.65
UBOOT_DIESEL_L_PER_KWH = 0.27
UBOOT_FUEL_LOW_FRACTION = 0.10
# Boat atmosphere of conventional boats (fictional rates for the whole crew;
# nuclear boats make their own oxygen).  Percent by volume; a mission starts
# some hours after the last snorkel.
UBOOT_AIR_FRESH_O2_PCT = 20.9
UBOOT_AIR_FRESH_CO2_PCT = 0.04
UBOOT_AIR_START_O2_PCT = 19.9
UBOOT_AIR_START_CO2_PCT = 0.9
UBOOT_AIR_START_ABSORBER_LEFT = 0.45
UBOOT_AIR_O2_USE_PCT_H = 0.45
UBOOT_AIR_CO2_RISE_PCT_H = 0.45
UBOOT_AIR_ABSORBER_K_H = 0.5          # CO2 taken out per hour, per % CO2
UBOOT_AIR_ABSORBER_CAPACITY_PCT = 3.0 # CO2 one fresh set takes out in all
UBOOT_AIR_ABSORBER_SETS = 8
UBOOT_AIR_O2_CANDLES = 12
UBOOT_AIR_CANDLE_O2_PCT = 1.0         # O2 one candle adds ...
UBOOT_AIR_CANDLE_BURN_S = 900.0       # ... over this burn time
UBOOT_AIR_VENT_TAU_S = 300.0          # snorkel airing: time constant to fresh air
UBOOT_AIR_AUTO_CANDLE_O2_PCT = 19.0   # the AI's crew lights a candle below this
UBOOT_AIR_CAUTION_CO2_PCT = 3.0
UBOOT_AIR_DANGER_CO2_PCT = 5.0
UBOOT_AIR_CAUTION_O2_PCT = 18.0
UBOOT_AIR_DANGER_O2_PCT = 16.0
# Crew performance in foul air (torpedo reload): full up to these values,
# half as fast this many percent beyond each, never below the floor.
UBOOT_AIR_EFFECT_CO2_PCT = 2.0
UBOOT_AIR_EFFECT_O2_PCT = 18.0
UBOOT_AIR_EFFECT_SPAN_PCT = 4.0
UBOOT_AIR_EFFICIENCY_FLOOR = 0.3
# Crewed boat ballast, trim and high-pressure air (src/enemies/ballast.py).
UBOOT_HP_AIR_MAX_BAR = 200.0        # air bottles full
UBOOT_HP_AIR_START_BAR = 200.0
UBOOT_HP_BLOW_BAR = 60.0            # one emergency blow of the main ballast
UBOOT_HP_COMPRESSOR_BAR_S = 0.05    # refill while snorkelling on the diesels
UBOOT_MBT_BLOW_S = 20.0             # main ballast empty after a blow
UBOOT_MBT_VENT_S = 40.0             # vents open: main ballast flooded again
UBOOT_MBT_SURFACE_DEPTH_M = 10.0    # blown boat: no deeper than this until flooded
UBOOT_REGULATING_KG = 8000.0        # regulating tank: +/- this around neutral
UBOOT_TRIM_TANK_KG = 3000.0         # trim water moved fore/aft at most
UBOOT_REGULATING_PUMP_KG_S = 25.0
UBOOT_TRIM_PUMP_KG_S = 15.0
UBOOT_PUMP_DEADBAND_KG = 20.0
UBOOT_REGULATING_STEP_KG = 500.0    # one crew order to the regulating tank
UBOOT_TRIM_STEP_KG = 250.0          # one crew order to the trim tanks
UBOOT_TORPEDO_KG = 1500.0           # a torpedo out of a bow tube
UBOOT_LOAD_MAX_KG = 60000.0
UBOOT_BUOYANCY_MPS_PER_T = 0.03     # sink/rise rate per tonne out of trim
UBOOT_BUOYANCY_MAX_MPS = 2.0
UBOOT_TRIM_DEG_PER_T = 1.0          # trim angle per tonne of moment
UBOOT_TRIM_MAX_DEG = 15.0
UBOOT_TRIM_WARN_DEG = 3.0
UBOOT_HEAVY_WARN_KG = 2000.0        # boat heavy/light beyond this: log it
UBOOT_PUMP_NOISE_DB = 3.0           # trim pumps running
UBOOT_PUMP_QUIET_LOSS = 0.05
UBOOT_PUMP_LINE = (120.0, 0.35, 3.0)   # (Hz, amp, width)
# Damage control of the crewed boat (stage D, fictional): six compartments
# bow to stern (bow, control, quarters, battery, engine, stern).
UBOOT_DC_CAPACITY_KG = (40000.0, 40000.0, 30000.0, 30000.0, 40000.0, 30000.0)
UBOOT_DC_ARM = (1.0, 0.5, 0.15, -0.15, -0.6, -1.0)   # moment arm, + forward
UBOOT_DC_LEAK_KG_S = 40.0           # full reference hole at 100 m
UBOOT_DC_LEAK_PER_PCT = 0.015       # hole size per % of hit damage
UBOOT_DC_SECOND_HIT_PCT = 50.0      # a hit this heavy holes a neighbour too
UBOOT_DC_FIRE_CHANCE_PCT = 150.0    # fire chance = damage / this
UBOOT_DC_FIRE_START = 0.2
UBOOT_DC_FATIGUE_LEAK = 0.3         # hull fatigue crack beyond test depth
# A crewed boat below its test depth (``Sub._hull_failure``): chance that a
# failure is a crack (per unit of excess over test depth, capped), else a
# shaft/valve seal or a bolted fitting; hull damage (%) each adds.
UBOOT_HULL_FRACTURE_PER_EXCESS = 1.5
UBOOT_HULL_FRACTURE_MAX = 0.6
UBOOT_HULL_SEAL_CHANCE = 0.3
UBOOT_HULL_FRACTURE_DAMAGE = 30.0
UBOOT_HULL_SEAL_DAMAGE = 12.0
UBOOT_HULL_BOLTS_DAMAGE = 6.0
# The crew calls "approaching test depth" when a crewed boat passes this
# fraction of its test depth going down, and "below test depth" beyond it.
UBOOT_TEST_DEPTH_WARN_FRACTION = 0.9
# Boat atmosphere (cues only, never simulation): the hull creaks from
# UBOOT_CREAK_START of test depth, a check every UBOOT_CREAK_TICK_S with a
# chance growing to 1 at test depth; detonations are heard out to
# UBOOT_DETONATION_HEARD_NM, "close" inside UBOOT_DETONATION_NEAR_NM, with a
# bearing error of UBOOT_DETONATION_BEARING_SD_DEG.
UBOOT_CREAK_START = 0.6
UBOOT_CREAK_TICK_S = 4.0
UBOOT_CREAK_MIN_CHANCE = 0.1
UBOOT_DETONATION_HEARD_NM = 30.0
UBOOT_DETONATION_NEAR_NM = 2.0
UBOOT_DETONATION_BEARING_SD_DEG = 3.0
UBOOT_SOUND_EVENTS_MAX = 16
# Silent running: red, dimmed light (multiply, then a red floor so dark blues redden).
UBOOT_SILENT_LIGHT = (255, 110, 95)
UBOOT_SILENT_LIGHT_FLOOR = (36, 0, 0)
UBOOT_DC_SPILL_FRACTION = 0.5       # water above this spills (and smothers fire)
UBOOT_DC_SPILL_KG_S = 20.0
UBOOT_DC_FIRE_GROW_S = 120.0
UBOOT_DC_FIRE_SPREAD_S = 90.0
UBOOT_DC_FIRE_STARVE_S = 180.0      # a fire behind closed bulkheads dies
UBOOT_DC_CHLORINE_WATER_KG = 2000.0
UBOOT_DC_CHLORINE_RISE_S = 120.0
UBOOT_DC_CHLORINE_DECAY_S = 600.0
UBOOT_DC_POWER_WATER_KG = 5000.0    # battery room water that cuts the power
UBOOT_DC_DOWN_WATER = 0.5           # fraction of a compartment: station out
UBOOT_DC_DOWN_FIRE = 0.5
UBOOT_DC_DOWN_GAS = 0.5
UBOOT_DC_TRANSIT_S = 8.0            # per compartment walked
UBOOT_DC_SEAL_S = 60.0              # one team seals a full hole
UBOOT_DC_FIRE_FIGHT_S = 60.0        # one team puts out a full fire
UBOOT_DC_PUMP_KG_S = 30.0
UBOOT_DC_HAND_PUMP = 0.25           # pump rate without power
UBOOT_DC_GAS_FACTOR = 0.5           # work rate in gas masks
UBOOT_DC_STERN_SPEED_FACTOR = 0.5   # shaft and motor room flooded
# Periscope of the crewed boat (plan 1.3, phase 9).
# A crewed submarine's tubes: each is loaded on order (the launcher's reload
# time) and must be flooded before it fires; flooding is briefly audible.
UBOOT_TUBE_FLOOD_S = 20.0
UBOOT_TUBE_FLOOD_NOISE_S = 4.0
UBOOT_TUBE_FLOOD_QUIET_S = 60.0      # slow flooding: quiet, heard only close
SUB_AI_PREFLOOD_NM = 15.0            # an AI boat floods quietly on a closer fix
SUB_FLOOD_SEQ_MAX = 1_000_000
TORP_FLOOD_HEAR_NM = 8.0             # frigate hears loud tube flooding (quiet own ship)
TORP_FLOOD_QUIET_HEAR_NM = 1.5       # ... and slow, quiet flooding
UBOOT_TUBE_STATES = ("dry", "flooding", "flooded")
UBOOT_SCOPE_EYE_HEIGHT_M = 2.5      # optics just above the surface
UBOOT_SCOPE_FOV_DEG = 32.0          # field of view of the low-power optics
UBOOT_SCOPE_POWERS = (1.0, 4.0)     # low power (1.5x) and high power (6x)
UBOOT_SCOPE_ELEVATION_DEG = (-10.0, 60.0)   # the head tilts up for the sky
UBOOT_SCOPE_STEP_DEG = 2.0          # arrow keys turn the scope by this
UBOOT_SCOPE_STEP_FAST_DEG = 10.0    # ... and with Shift by this
UBOOT_SCOPE_BEARING_ERR_DEG = 1.0   # sigma of a periscope bearing
UBOOT_SIGHTINGS_MAX = 16
UBOOT_SIGHTING_LOST_S = 10.0        # a sighting vanishes this long after it was last seen
UBOOT_STADIMETER_ERR_FRAC = 0.25    # range uncertainty of a stadimeter reading
UBOOT_STADIMETER_WINDOW_DEG = 3.0   # the crosshair must be this close to the sighting
# Assumed hull lengths of the stadimeter by recognized class (m); an
# unrecognized surface contact is measured as a generic frigate.
UBOOT_STADIMETER_LENGTHS_M = {"warship": 130.0, "merchant": 150.0, "unknown": 130.0}
# The periscope attack computer: stadimeter marks per sighting (saved in
# ``crew.orders.tdc``), fitted to the target's course and speed.
UBOOT_TDC_TARGETS_MAX = 8           # sightings with marks at a time
UBOOT_TDC_MARKS_MAX = 6             # marks kept per sighting (the latest)
UBOOT_TDC_WINDOW_S = 900.0          # a mark older than this drops out of the fit
UBOOT_TDC_MIN_BASE_S = 60.0         # first to last mark needed for a solution
UBOOT_TDC_MAX_SPEED_KN = 40.0       # a faster fit is rejected as a bad mark
UBOOT_TDC_GOOD_BASE_S = 300.0       # a base this long gives full quality

# The boat's own ESM (mast raised): intercepts, emitter memory, cross-fix.
UBOOT_ESM_SCAN_S = 1.0              # one intercept scan per second of sim time
UBOOT_ESM_BEARING_ERR_DEG = 4.0     # +- bearing error of the mast antenna (coarser than the frigate)
UBOOT_ESM_ANTENNA_M = 3.0         # the ESM antenna on the raised mast (radar horizon)
UBOOT_ESM_SHIP_ANTENNA_M = 20.0     # assumed antenna height of a ship's radar (horizon)
UBOOT_ESM_MEMORY_S = 1800.0         # an emitter stays in the crew's list this long after its last intercept
UBOOT_ESM_LIVE_S = 10.0             # ... and counts as live (strobe, warning) this long
UBOOT_ESM_EMITTERS_MAX = 16
UBOOT_ESM_HISTORY_MAX = 40          # bearing-history samples per emitter (20 min)
UBOOT_ESM_HISTORY_STEP_S = 30.0     # at most one history sample per emitter this often
UBOOT_ESM_DRIFT_DEG_PER_MIN = 3.0   # the association gate widens this much per minute of silence
UBOOT_ESM_DRIFT_MAX_DEG = 45.0
UBOOT_ESM_FIX_WINDOW_S = 1200.0     # a cross-fix uses the history of the last 20 minutes
UBOOT_ESM_FIX_MIN_SAMPLES = 3
UBOOT_ESM_FIX_EMITTER_KN = 8.0     # assumed emitter drift: older lines count for less
UBOOT_ESM_FIX_MIN_SWING_DEG = 8.0   # own motion must swing the bearing this much (baseline)
UBOOT_ESM_FIX_MAX_AXIS_NM = 40.0    # a longer error ellipse is no fix (baseline too short)
UBOOT_ESM_FIX_MAX_AXIS_RATIO = 1.0  # ... as is one longer than the range itself
UBOOT_ESM_FIX_CONFIDENCE = 2.4477   # 95 % error ellipse (sqrt of chi-square, 2 dof)
UBOOT_ESM_FIX_CHI2_MAX = 4.0        # a worse fit marks the fix inconsistent (moving emitter)
UBOOT_ESM_TREND_WINDOW_S = 300.0    # signal-strength trend over the last five minutes
UBOOT_ESM_TREND_DB_PER_MIN = 0.5    # a slope beyond this reads rising/falling
UBOOT_ESM_WASH_SEA_STATE = 3.0      # from this sea state waves wash over the mast antenna ...
UBOOT_ESM_WASH_PER_SEA = 0.12       # ... losing this fraction of scans per sea state above it
UBOOT_ESM_WASH_MAX = 0.6
# Scan period: the interval between an emitter's main-beam hits (the level
# peaks; close in the side lobes are heard in between). A rotating search
# radar reads its rotation period, a tracking/fire-control radar
# illuminates steadily (every scan). Measured only over gaps up to
# SCAN_GAP_MAX_S with no washed scan in between, read after SCAN_MEASURE_S.
UBOOT_ESM_SCAN_GAP_MAX_S = 12.0
UBOOT_ESM_SCAN_MEASURE_S = 8.0
UBOOT_ESM_STEADY_S = 1.5
UBOOT_ESM_SCAN_ALPHA = 0.35
UBOOT_ESM_PEAK_DB = 10.0          # a main-beam hit reads within this of the held peak (side lobes -25 dB)
# Recommended mast time: short in a calm sea (the mast stands out of the
# clutter), longer when sea clutter hides it; short whenever an intercepted
# search radar is close enough to see the mast.
UBOOT_MAST_TIME_BASE_S = 60.0
UBOOT_MAST_TIME_CLUTTER_S = 240.0
UBOOT_MAST_TIME_THREAT_S = 20.0

# Display scales of the bridge lookout page (NM, radius of the scope).
LOOKOUT_DISPLAY_RANGES_NM = (2.0, 5.0, 12.0, 20.0, 30.0)
# Bridge lookout binoculars over the chart (display only): field of view and
# training steps (',' / '.', Shift for the fast step).
LOOKOUT_GLASSES_FOV_DEG = 16.0
LOOKOUT_GLASSES_STEP_DEG = 5.0
LOOKOUT_GLASSES_STEP_FAST_DEG = 20.0
# Zoom binoculars: the field narrows 16, 8, 4 degrees; tilt 20 down to 45 up.
LOOKOUT_GLASSES_POWERS = (1.0, 2.0, 4.0)
LOOKOUT_GLASSES_ELEVATION_DEG = (-20.0, 45.0)
# Tilting the binoculars or the periscope head (Shift: fast).
SIGHT_TILT_STEP_DEG = 2.0
SIGHT_TILT_STEP_FAST_DEG = 10.0
# Land in sight: day/clear range of a coast with 50 m hills, checked on a
# slow cadence; a landmass is reported again only after it dropped out of
# sight.
LOOKOUT_LAND_RANGE_NM = 20.0
# Day/clear range at which a running torpedo's wake is seen (lookout, periscope).
TORPEDO_WAKE_VISIBLE_NM = 1.5
LOOKOUT_LAND_CHECK_S = 10.0
LOOKOUT_REPORTS_MAX = 24
# The lookout calls a lit vessel's lights again only when what they tell
# (her aspect or her work) changes, at most this often per contact.
LOOKOUT_LIGHTS_REPORT_S = 120.0
# An AI submarine at periscope depth that holds the frigate reports it to
# its headquarters once per window, 20 s on HF (heard by the frigate's HF/DF);
# only while its last contact is at most this old.
SUB_REPORT_PERIOD_S = 1800.0
SUB_REPORT_TX_S = 20.0
SUB_REPORT_CONTACT_S = 600.0
# Phone lookout (Remote Crew ``lookout``/``uboot_lookout``): a called sighting
# is confirmed within this bearing, and a called range within this fraction
# (at least the minimum) of the eye's own estimate.
LOOKOUT_CALL_BEARING_TOL_DEG = 10.0
LOOKOUT_CALL_RANGE_TOL_FRAC = 0.4
LOOKOUT_CALL_RANGE_MIN_NM = 1.0
CONTACT_SIG_CONF = 0.40         # Konfidenz, ab der die Geräusch-Signatur lesbar ist
PLAYER_CLASSES = ("U_BOOT", "KAMPFSCHIFF", "BIOLOGISCH", "FAHRZEUG",
                  "FLUGZEUG", "TORPEDO")
PLAYER_CLASS_LABELS = {
    "U_BOOT": "U-Boot",
    "KAMPFSCHIFF": "Kampfschiff",
    "BIOLOGISCH": "Biologisch",
    "FAHRZEUG": "Fahrzeug",
    "FLUGZEUG": "Flugzeug",
    "TORPEDO": "Torpedo",
}

# OPZ/CIC: manuell gesetzte NATO-Zugehoerigkeit. Die Domaene (See, Luft,
# Flugkoerper) stammt nur aus dem beobachteten Sensor-Track.
NATO_AFFILIATIONS = ("UNKNOWN", "FRIEND", "NEUTRAL", "HOSTILE")
NATO_AFFILIATION_LABELS = {
    "UNKNOWN": "Unbekannt",
    "FRIEND": "Freund",
    "NEUTRAL": "Neutral",
    "HOSTILE": "Feind",
}
OPZ_FUSION_MAX = 32
OPZ_FUSION_MEMBER_MIN = 2
OPZ_FUSION_MEMBER_MAX = 8
# OPZ correlation suggestions (src/sensors/fusion.py ``suggest_correlations``):
# two published reports from different sensors on the same bearing from the
# frigate. The bearing gate is the base plus both reports' bearing
# uncertainties (root-sum-square, missing ones count as the default), capped;
# reports with positions must also lie within the position gate (plus a share
# of their range). Only reports seen within the age limit are compared.
OPZ_SUGGEST_MAX = 4
OPZ_SUGGEST_CANDIDATES_MAX = 48
OPZ_SUGGEST_DISMISSED_MAX = 32
OPZ_SUGGEST_BEARING_BASE_DEG = 1.5
OPZ_SUGGEST_BEARING_DEFAULT_UNC_DEG = 2.0
OPZ_SUGGEST_BEARING_MAX_DEG = 8.0
OPZ_SUGGEST_POSITION_NM = 1.5
OPZ_SUGGEST_POSITION_RANGE_SHARE = 0.1
OPZ_SUGGEST_MAX_AGE_S = 30.0
OPZ_SUGGEST_OBSERVER_NM = 0.5
# Motion and signature: when both reports carry a course and at least one
# moves faster than MIN_SPEED_KN, their courses must agree within COURSE_DEG;
# when both carry a speed, within SPEED_KN plus a share of the faster.  Two
# operator classifications must be equal (and an AIS report never pairs with
# a submarine, biological or aircraft classification); an agreeing class
# multiplies the score by CLASS_BONUS.  AIS reports count while their
# dynamic data is fresh, up to AIS_MAX_AGE_S.
OPZ_SUGGEST_MIN_SPEED_KN = 3.0
OPZ_SUGGEST_COURSE_DEG = 35.0
OPZ_SUGGEST_SPEED_KN = 4.0
OPZ_SUGGEST_SPEED_SHARE = 0.25
OPZ_SUGGEST_CLASS_BONUS = 0.7
OPZ_SUGGEST_AIS_MAX_AGE_S = 600.0
# Automatic OPZ fusion (``auto_fusion_plan``): every INTERVAL_S of simulation
# time the OPZ fuses reports of different sensors that lie on top of each
# other: inside every suggestion gate, with a score of at most SCORE_MAX, at
# least one side with a position fix, and no second candidate from the same
# sensor family on either side. Anything less clear stays a suggestion.
OPZ_AUTO_FUSE_INTERVAL_S = 1.0
OPZ_AUTO_FUSE_SCORE_MAX = 0.35
# AIS reports in the OPZ: satellite-navigation positions, so a small bearing
# uncertainty and a high report quality.
AIS_OPZ_QUALITY = 0.95
AIS_OPZ_BEARING_UNC_DEG = 0.2

# M10: Telegraph & Maschinenraum (diskrete Motorenbefehle)
TELEGRAPH_ORDERS = (
    ("STOP", 0.0),
    ("SLOW", 6.0),
    ("HALF", 10.0),
    ("FULL", 16.0),
    ("FLANK", 31.0),
)
TELEGRAPH_DEFAULT = 2           # Index (HALF)
ASTERN_SPEED_KN = 3.0           # Fiktive Bergungsfahrt; separater Zustand
SHIP_RPM_MIN = 20.0             # Leerlauf-RPM
SHIP_RPM_PER_KN = 2.4
SHIP_FUEL_CAPACITY_KG = 500_000.0
SHIP_FUEL_HOTEL_KG_H = 400.0
SHIP_FUEL_MAX_PROPULSION_KG_H = 14_110.0
SHIP_FUEL_ASTERN_FACTOR = 1.15
SHIP_MAX_RUDDER_DEG = 30.0
SHIP_RUDDER_RATE_DEG_PER_S = 4.0
SHIP_YAW_RESPONSE_S = 10.0
SHIP_MAX_YAW_RATE_DEG_PER_S = 0.8
SHIP_YAW_DAMPING = 2.0
# Asymmetric flooding heels the ship toward the heavier side (list) and makes
# it want to yaw that way, requiring constant rudder correction to hold a
# straight course - a small, bounded game model of a real damage-control
# effect, derived purely from the existing hull_left/hull_right flood state
# (no new persisted ship state).
SHIP_LIST_DEG_PER_FLOOD_PCT = 0.15
SHIP_MAX_LIST_DEG = 15.0
SHIP_LIST_YAW_GAIN = 0.05        # deg/s of persistent yaw pull per degree of list
TAS_AMBIGUITY_RESOLVE_DEG = 20.0   # own turn that resolves TAS left/right
CAVITATION_KN = 15.0            # Schraubenkavitation ab dieser Fahrt
CAVITATION_PASSIVE_FACTOR = 0.35   # passives Sonar bei Kavitation: Sensor "bricht"
SEA_STATE_SONAR_FACTOR = 0.06     # passiver Reichweiten-Abzug pro Seegang-Grad

# M11: Sonar-Suite (Bug-/Towed-Array, Konvergenzzone)
SONAR_ARRAY_BOW_PASSIVE = 1.0
SONAR_ARRAY_BOW_PING = 1.0
SONAR_ARRAY_TOWED_PASSIVE = 1.4   # Towed-Array: besser, verliert aber mit Fahrt
SONAR_ARRAY_TOWED_PING = 0.8
SONAR_TOWED_SPEED_PENALTY = 0.03  # passiver Abzug pro kn bei Towed-Array
SONAR_TOWED_DEPTH_M = 50.0        # Schleppsonar-Tiefe (SNR: Tiefe = stabiler)
SONAR_TOWED_DEEP_BONUS = 1.25     # Towed: Ziel im Tiefenband 30-250 m = besser
SONAR_TOWED_DEPTH_MIN_M = 20.0
SONAR_TOWED_DEPTH_MAX_M = 260.0
SONAR_TOWED_DEPTH_RATE_M_S = 4.0
SONAR_TOWED_SPEED_SHALLOW_M_PER_KN = 4.0
SONAR_TOWED_DEPLOY_S = 360.0
SONAR_TOWED_RETRIEVE_S = 480.0
SONAR_TOWED_HANDLING_MIN_KN = 3.0
SONAR_TOWED_HANDLING_MAX_KN = 12.0
SONAR_TOWED_MAX_SAFE_KN = 20.0
SONAR_TOWED_AVAILABLE_PAYOUT = 0.95
SONAR_TOWED_SETTLE_S = 30.0
SONAR_TOWED_HEADING_LAG_S = 45.0
SONAR_TOWED_SELF_NOISE_FACTOR = 0.35
# Baffles: every hull-mounted passive array (the frigate's bow sonar, a
# submarine's) is deaf in this half-angle around its own stern; towed
# arrays and the VDS still hear there.  Clearing the baffles turns the
# ordered course by BAFFLE_CLEAR_TURN_DEG for BAFFLE_CLEAR_HOLD_S and then
# returns to the previous course.
SONAR_BAFFLE_HALF_DEG = 30.0
BAFFLE_CLEAR_TURN_DEG = 60.0
BAFFLE_CLEAR_HOLD_S = 120.0
# An AI submarine that finds itself in the frigate's baffles inside this
# range trails it there instead of running away.
SUB_BAFFLE_TRAIL_NM = 6.0
# Variable-depth sonar (VDS): a body lowered astern on a short cable. It is
# unambiguous like the hull array, sits away from the hull's noise and can be
# put below the layer. Handling (lowering and recovery) needs 3-15 kn and a
# sea state of at most 5; above 24 kn a lowered body is lost (FAULT).
SONAR_VDS_DEPTH_M = 50.0
SONAR_VDS_DEPTH_MIN_M = 20.0
SONAR_VDS_DEPTH_MAX_M = 300.0
SONAR_VDS_DEPTH_RATE_M_S = 3.0
SONAR_VDS_SPEED_SHALLOW_M_PER_KN = 8.0
SONAR_VDS_DEPLOY_S = 120.0
SONAR_VDS_RETRIEVE_S = 120.0
SONAR_VDS_HANDLING_MIN_KN = 3.0
SONAR_VDS_HANDLING_MAX_KN = 15.0
SONAR_VDS_MAX_SEA_STATE = 5
SONAR_VDS_MAX_SAFE_KN = 24.0
SONAR_VDS_SETTLE_S = 20.0
SONAR_ARRAY_VDS_PASSIVE = 1.15
SONAR_ARRAY_VDS_PING = 1.1
SONAR_VDS_SELF_NOISE_FACTOR = 0.6
SONAR_FUSION_CONFIRM_DEG = 5.0
SONAR_FUSION_DIVERGENT_DEG = 9.0
SONAR_BT_COOLDOWN_S = 60.0
# Deep expendable bathythermograph: to the seabed, at most this deep, so a
# deep sound channel (SOFAR axis) can be measured.
SONAR_BT_MAX_DEPTH_M = 1500.0
SONAR_PAGE_COUNT = 6
CZ_BANDS = ((40.0, 70.0), (90.0, 130.0))  # Konvergenzzonen (NM, vom Schallfenster)
CZ_BONUS_NM = 25.0              # zusätzliche passive Reichweite in der Zone

# W1: LOFAR-Wasserfall (hohe Auflösung im niedrigen Hz-Bereich)
LOFAR_FMAX_HZ = 300.0
LOFAR_BINS = 110               # 0-40 Hz @1 Hz, 40-100 Hz @2 Hz, 100-300 Hz @5 Hz
LOFAR_HISTORY_COLS = 80
LOFAR_SAMPLE_S = 0.25          # sim-Sekunden pro Wasserfall-Spalte
# Display-only, decimated histories.  The fine receiver history remains the
# save-compatible 20 s buffer above; these bounded rings provide operator time
# context without changing detections or the v10 save schema.
SONAR_BROADBAND_LONG_SAMPLE_S = 2.0
SONAR_BROADBAND_LONG_ROWS = 120       # four minutes
SONAR_DEMON_HISTORY_ROWS = 120        # thirty seconds at receiver cadence

# M12: OPZ / EMCON
RADAR_ON_DEFAULT = True
RADAR_RANGE_SCALES_NM = (10.0, 20.0, 40.0, 80.0, 120.0)
RADAR_RANGE_DEFAULT_NM = 40.0
RADAR_SWEEP_DEG_PER_S = 90.0
RADAR_AFTERGLOW_S = 3.2
RADAR_WEATHER_THRESHOLD = 5
RADAR_SURFACE_WEATHER_LOSS = 0.25
RADAR_AIR_WEATHER_LOSS = 0.10
RADAR_WEATHER_ERROR_GAIN = 1.5
RADAR_TRACK_STALE_S = 30.0
# A raised submarine mast or snorkel head: a tiny, low echo (relative to the
# broadside reference ship) that sea clutter soon hides.  It shows as a bare
# blip on the PPI only; the OPZ must mark it to start a radar track.
SUB_MAST_HEIGHT_M = 1.5
# An AI submarine's ESM hears an own aircraft's search radar (helicopter or
# patrol aircraft, switched on) while its mast or snorkel is up and the
# aircraft is above its radar horizon: it goes deep and stays down.
SUB_RADAR_ALERT_LOOK_S = 5.0        # one ESM look per boat and period
SUB_RADAR_ALERT_P = 0.8             # chance a look catches the main beam
SUB_RADAR_ALERT_NM = 40.0           # beyond this the intercept is ignored
SUB_RADAR_HOLD_S = 900.0            # stays deep this long after an intercept
SUB_RADAR_HOLD_MIN_BATTERY = 0.05   # below this battery it must snorkel anyway
SUB_RADAR_DIVE_M = 40.0             # goes this far below snorkel depth
SUB_MAST_RCS_FACTOR = 0.01
SUB_SURFACED_RCS_FACTOR = 0.1       # a surfaced boat's hull and conning tower
SUB_SURFACED_HEIGHT_M = 3.0
RADAR_BLIP_LIFE_S = 6.0
RADAR_BLIP_MAX = 24
RADAR_BLIP_GATE_NM = 1.0
RADAR_BEARING_ERR_DEG = 0.8
RADAR_RANGE_ERR_FRAC = 0.015
# Air-search radar height estimate: a game model of a 3D radar's altitude
# channel, noisier than range (fraction of altitude plus a fixed floor).
RADAR_ALTITUDE_ERR_FRAC = 0.04
RADAR_ALTITUDE_ERR_M = 60.0
OBS_ALTITUDE_SMOOTH = 0.35
# Observation filters operate on sensor epochs, not render/physics substeps.
OBS_RADAR_EPOCH_S = 0.5
OBS_BEARING_EPOCH_S = 5.0
OBS_RADAR_SMOOTH_TAU_S = 1.5
OBS_BEARING_SMOOTH_TAU_S = 4.0
# 12 fixes at the 0.5s epoch above is only a 6s regression window - far too
# short for bearing/range noise to average out against typical contact
# displacement (the raw slope's noise scales with window_span^-1.5), which is
# what made the derived course/speed swing wildly between re-fits. 60 fixes
# (30s) keeps a still-responsive window while cutting that noise by roughly
# an order of magnitude.
OBS_HISTORY_MAX = 60
# Presentation-only slew cap for the derived (bearing-only) contact course:
# real hulls turn at well under 1.5 deg/s (see motion_limits()), so capping
# the DISPLAYED course at this rate keeps it stable between per-fix least
# squares re-fits without ever lagging behind an actual maneuver noticeably.
OBS_DERIVED_COURSE_MAX_RATE_DEG_S = 3.0
# Same idea for the derived (bearing-only) contact speed: every simulated
# contact type that ever goes through this path (ships, flights, ASMs) flies
# at a constant true speed once spawned/launched - there is no real maneuver
# to keep up with - so a per-fix noise-driven jump here is pure display
# jitter and can be damped hard without ever lagging a genuine change.
OBS_DERIVED_SPEED_MAX_RATE_KN_S = 5.0
MOTION_VECTOR_WINDOW_MIN = 3.0

# M13: Funkraum / HFDF
SNOCKEL_TRANSMIT_NOISE = -0.20  # Lärmänderung beim Senden (negativ = lauter)
HFDF_RANGE_NM = 120.0
HFDF_BEARING_ERR_DEG = 8.0
WEATHER_BULLETIN_PERIOD_S = 1800.0
WEATHER_SHIFT_PERIOD_S = 3600.0
WEATHER_TRANSITION_S = 600.0
WEATHER_WIND_MAX_KN = 60.0
WEATHER_VISIBILITY_MIN_NM = 0.25
WEATHER_VISIBILITY_MAX_NM = 30.0
RADAR_RAIN_SURFACE_LOSS = 0.10
RADAR_RAIN_AIR_LOSS = 0.20
RADAR_RAIN_ERROR_GAIN = 0.75
# Own radar antenna/mast height for the geometric radar horizon (standard
# "4/3 Earth radius" refraction constant). Sea-skimming threats at very low
# altitude/height stay below this horizon until they close to short range,
# regardless of the nominal power-limited radar range above.
RADAR_ANTENNA_HEIGHT_M = 20.0
# Target-side heights for the same horizon term, applied to contacts that
# previously used only the flat power-limited range (civilians/warships/
# regular air traffic) - raiders already used this via their own altitude_m.
RADAR_SURFACE_TARGET_HEIGHT_M = 10.0
FLIGHT_RADAR_ALTITUDE_M = 3000.0
FLIGHT_ALTITUDE_SPREAD = 0.6    # per-flight altitude 0.7x..1.3x of the above


def flight_altitude_m(seq: int) -> float:
    """Deterministic per-flight altitude (no RNG draw, save-compatible)."""
    unit = (int(seq) * 7919 % 101) / 100.0
    return FLIGHT_RADAR_ALTITUDE_M * (
        1.0 - FLIGHT_ALTITUDE_SPREAD / 2.0 + FLIGHT_ALTITUDE_SPREAD * unit)


def measure_altitude_m(rng, altitude_m: float, error_scale: float = 1.0) -> float:
    """Noisy radar altitude estimate from a caller-owned RNG stream."""
    fraction = RADAR_ALTITUDE_ERR_FRAC * error_scale
    return max(0.0, altitude_m * (1.0 + rng.uniform(-fraction, fraction))
               + rng.uniform(-RADAR_ALTITUDE_ERR_M, RADAR_ALTITUDE_ERR_M))
HELO_LAUNCH_WIND_MAX_KN = 32.0
HELO_LAUNCH_CROSSWIND_MAX_KN = 22.0
HELO_LAUNCH_VISIBILITY_MIN_NM = 2.0
HELO_LAUNCH_GUST_MAX_KN = 40.0
HELO_CEILING_MIN_FT = 300.0
HELO_ICING_FUEL_FACTOR = 1.2   # anti-/de-icing power in light icing
HELO_LAUNCH_SEA_STATE_MAX = 5.0
HELO_DIP_WIND_MAX_KN = 30.0
HELO_DIP_VISIBILITY_MIN_NM = 1.0
HELO_DIP_SEA_STATE_MAX = 5.0
ROE_DEFAULT = "STD"             # STD: geortet+klassifiziert | FREE: nur klassifiziert
ROE_FREE_LAUNCH_RANGE_NM = 10.0 # FREE: Schätzweite ohne Ping beim Abschuss

# M14: Brand (Schadens-2.0)
DMG_FIRE_RATE = 0.08            # Brandentwicklung über Minuten
DMG_FIRE_REPAIR_RATE = 0.14     # %/s pro Lösch-Team
DMG_FIRE_SPREAD_PPS = 0.0002    # Nachbarbrand-Risiko pro Sekunde
DMG_FIRE_START_CHANCE = 0.35    # Brand-Chance je Treffer
DMG_FIRE_START = (20.0, 40.0)
DMG_FIRE_KILL = 100.0           # Brand > 100 % -> Kompartiment ZERSTOERT

# M15: Waffensystem 2.0 (Drahttorpedo, Doktrin, Hubschrauber)
TORP_DOCTRINE = "SHOOT_LOOK_SHOOT"
TORP_MAX_IN_AIR = {"SHOOT_LOOK_SHOOT": 2, "SEMI_CONTINUOUS": 4}
TORP_HOME_RANGE_NM = 1.2        # darunter: Homing, sonst Serpentin-Suchlauf
TORP_MIDCOURSE_UPDATE_S = 0.5   # Draht-Mittelkurs-Update (Serpentin)
TORP_SPOOLUP_S = 2.0            # Anlaufzeit bis Marschgeschwindigkeit
TORP_SPOOLUP_MIN_FRAC = 0.25    # Anfangsgeschwindigkeit als Bruchteil (Rohrabschuss)
TORP_RUNNING_NOISE_RANGE_NM = 6.0  # passive Eigenlaerm-Reichweite eines laufenden Torpedos
# Measured torpedo cues (src/sensors/threat_cue.py): intercepts, never the
# entity type. The launch transient carries as far as the frigate's own
# launch is heard by submarines; HF seeker pulses are heard beyond homing range.
TORP_TRANSIENT_HEAR_NM = SUB_TORPEDO_ALERT_NM
TORP_SEEKER_INTERCEPT_NM = 6.0
TORP_CUE_BEARING_SIGMA_DEG = 3.0
TORP_CUE_HOLD_S = 60.0          # a cue stays on the alarm board this long
# Radar threat evaluation: an inbound air track this fast and this low (or a
# jamming strobe) raises the ASM cue. Low attack aircraft can trigger it too.
ASM_CUE_SPEED_KN = 300.0
ASM_CUE_ALTITUDE_M = 150.0
HELO_FUEL_S = 7200.0
HELO_FUEL_RESERVE_S = 1200.0
HELO_RETURN_DIST_NM = 0.3
HELO_TORPS = 2                  # Leichttorpedos pro Start
HELO_DIP_DEPTH_MIN_M = 15.0
HELO_DIP_DEPTH_DEFAULT_M = 75.0
HELO_DIP_DEPTH_MAX_M = 300.0
HELO_DIP_DEPTH_RATE_M_S = 2.5
HELO_DIP_BOTTOM_CLEARANCE_M = 10.0
HELO_DIP_PASSIVE_RANGE_NM = 18.0
HELO_DIP_ACTIVE_RANGE_NM = 14.0
HELO_DIP_PING_COOLDOWN_S = 30.0
HELO_DIP_BEARING_ERR_DEG = 2.0
BUOY_COUNT = 5
BUOY_SPACING_NM = 3.0
BUOY_RANGE_NM = 8.0
BUOY_BATTERY_S = 3600.0
BUOY_PING_COOLDOWN_S = 30.0
HELO_TORP_SPEED_KN = _HELO_TORP_PROFILE.speed_kn

# M16: Fliegerabwehr (physikalische Geschwindigkeiten)
ASM_SPAWN_DIST_NM = (30.0, 40.0)
ASM_SPAWN_FIRST_S = 600.0
ASM_SPAWN_INTERVAL_S = 1200.0

# R20: Luftangriffs-Wellen (feindliche Jagdbomber vs. Fregatte)
RAID_FIRST_WAVE_S = 1500.0
RAID_WAVE_INTERVAL_S = 900.0
RAID_WAVE_SIZE = (1, 2)
RAID_SPAWN_DIST_NM = (110.0, 140.0)
RAID_MAX_CONCURRENT = 3
RAIDER_ATTACK_WINDOW_S = 90.0

# M15: HSP-5 (Sea Lynx)
HELO_SPEED_KN = 120.0

# W3: Luftfahrt & Airbases (physikalische Knoten)
FLIGHT_SPEED_KN = 200.0
FLIGHT_CIVIL_SPEED_KN = 450.0
FLIGHT_LOITER_NM = (15.0, 30.0) # Patrouillen-Kreis um Airbase
FLIGHT_ATTACK_RANGE_NM = 35.0   # Abschussentfernung für ASM
# Zivile Routen werden geometrisch an die Fregatte angebunden, damit sie
# radar-einsehbar bleiben: liegt die Gerade Basis->Ziel innerhalb von
# FLIGHT_CIVIL_PASS_NM an ihr, bleibt die Route direkt; sonst lenkt ein
# Weichpunkt sie auf FLIGHT_CIVIL_VIA_NM an (reine Geometrie, keine RNG).
FLIGHT_CIVIL_PASS_NM = 60.0
FLIGHT_CIVIL_VIA_NM = 30.0

# W1: TMA (Peilungs-Tracking -> Position + Geschwindigkeit)
TMA_MIN_PTS = 4                 # minimal Peilungen
TMA_MIN_SPAN_S = 180.0          # mehrere Minuten Peilungsbaseline
TMA_RESOLVE_EVERY_S = 4.0       # max. TMA-Re-Solve-Rate pro Ziel (sim-s, CPU-Schutz)
TMA_MIN_COURSE_CHG_DEG = 6.0    # Fregatte muss manövrieren (Beobachtbarkeit)
TMA_MAX_RANGE_NM = 45.0         # Lösungsraum
TMA_SEARCH_STEP_S = 1.5         # Zeit-Schritt der Geschwindigkeits-Suche
TMA_QUALITY_DB = 8.0            # Peil-RMSE (°), ab dem Qualität 0 wird
TMA_RANGE_MIN_QUALITY = 0.35    # TMA-Range erst ab dieser Qualität nutzen
TMA_FINE_COURSE_STEP_DEG = 3
TMA_FINE_SPEED_STEP_KN = 0.5
TMA_PRESENTATION_ALPHA = 0.35
TMA_HYSTERESIS_RMSE_MARGIN_DEG = 1.0  # keep the previous solve unless a fresh
                                       # candidate fits the bearings clearly
                                       # better - stops re-solves from hopping
                                       # between near-tied local optima
TMA_DEFAULT_BEARING_SIGMA_DEG = 3.5
TMA_ROBUST_SIGMA = 2.5          # Huber-Grenze in Mess-Standardabweichungen
BEARING_TRACK_MAX_PTS = 80      # 4-s-Fenster umfasst gut fünf Minuten
BEARING_TRACK_MIN_INTERVAL_S = 4.0  # unabhaengige TMA-Peilungen
BEARING_ERR_BOW_DEG = 6.0           # Peilfehler Basis: Bug-Array (±)
BEARING_ERR_VDS_DEG = 4.0           # Peilfehler Basis: VDS (eindeutig)
BEARING_ERR_TOWED_DEG = 2.0         # Peilfehler Basis: Schleppsonar (±)
BEARING_ERR_SPEED_FACTOR = 0.12     # relativer Aufschlag pro kn Eigenfahrt
BEARING_ERR_QUALITY_SPAN = 0.9      # Fehlerfaktor: 1.4 - SPAN*quality
SONAR_BEARING_NOISE_EPOCH_S = 2.0
SONAR_BEARING_DISPLAY_TAU_S = 7.0
SONAR_BEARING_RATE_MAX_DEG_S = 8.0

# Custom-Schwierigkeit (ersetzt das ehemalige feste M7-4-Stufen-System,
# GDD §9/§17/§25): jede Achse ist einzeln vom Spieler wählbar, identisch in der
# uConsole-Menüführung und im Remote-Crew-Web-Host-Dialog. Beide Oberflächen
# iterieren ausschließlich über diese Tabelle - keine Regler-Grenzen sind
# irgendwo dupliziert.
#
# Kampf-Balance (bisher pro Level in LEVELS):
#   quiet_mult: Faktor auf U-Boot-Stillheit (<1 = lauter/leichter zu finden)
#   repair_mult: Faktor auf Reparaturrate | torpedo_count: Munitionsbestand
#   kill_dist_nm/kill_depth_m: Treffer-Toleranz der eigenen Torpedos
#     (Fregatte und Helo teilen sich diesen einen Wert)
#   enemy_attack_mult/enemy_cooldown_s: Gegenangriff der U-Boote
#   second_sub_prob: Chance für ein zusätzliches Bonus-Boot aus
#     SECOND_SUB_POOL (0.0 -> RNG-Sequenz der Basis-Spawns bleibt unverändert)
# Missions-Zusammensetzung (bisher pro Missionstyp in MISSION_TYPES, nur für
# die freie Mission s4_zufall wirksam - feste Szenarien nutzen weiterhin
# MISSION_TYPES intern):
#   sea_state_start: Anfangsseegang (0-6, Sturm ab hohen Werten)
#   sub_count/warship_count/civilian_count/animal_count: Objektzahlen
#   air_raid_count: Anzahl Luftangriffs-Wellen (0 = keine)
#   air_raid_freq_mult: Taktfaktor (>1 = häufiger)
#   time_limit_s: Missions-Zeitlimit in Echtzeitsekunden
#
# name: (python_type, min, max, step, default)
DIFFICULTY_FIELDS = {
    "quiet_mult":         (float, 0.5,    1.5,    0.05,  1.0),
    "repair_mult":        (float, 0.3,    2.0,    0.1,   1.0),
    "torpedo_count":      (int,   2,      10,     1,     6),
    "kill_dist_nm":       (float, 0.05,   0.30,   0.005, 0.135),
    "kill_depth_m":       (float, 5.0,    30.0,   1.0,   15.0),
    "enemy_attack_mult":  (float, 0.3,    2.0,    0.1,   1.0),
    "enemy_cooldown_s":   (float, 300.0,  1800.0, 30.0,  900.0),
    # Plan 1.3 phase 5: the AI boat fires on its own TMA only once the
    # solution's range sigma over range is at or below this fraction.
    "enemy_solution_threshold": (float, 0.05, 0.40, 0.05, 0.20),
    "second_sub_prob":    (float, 0.0,    1.0,    0.05,  0.0),
    "sea_state_start":    (int,   0,      6,      1,     3),
    "sub_count":          (int,   1,      3,      1,     1),
    "warship_count":      (int,   0,      3,      1,     0),
    "civilian_count":     (int,   0,      6,      1,     3),
    "animal_count":       (int,   0,      6,      1,     3),
    "air_raid_count":     (int,   0,      8,      1,     0),
    "air_raid_freq_mult": (float, 0.25,   4.0,    0.25,  1.0),
    "time_limit_s":       (int,   1800,   36000,  300,   10800),
}
DIFFICULTY_FIELD_ORDER = tuple(DIFFICULTY_FIELDS)
DEFAULT_DIFFICULTY = {name: spec[4] for name, spec in DIFFICULTY_FIELDS.items()}
# Realism levels (preference ``level``, saved per mission as ``level``).
# The level tunes only the computer opponent and the displays, never a human
# on the other side: an AI submarine attacks more or less eagerly and waits
# for a better or worse firing solution, and the AI frigate (when the
# uConsole commands the submarine) classifies and calls its helicopter
# slower or faster.  Beginner also turns the operator assistance on,
# Realistic turns it off.  The mission score is multiplied by the factor.
LEVELS = ("beginner", "standard", "realistic")
LEVEL_DEFAULT = "standard"
LEVEL_SCORE_FACTOR = {"beginner": 0.75, "standard": 1.0, "realistic": 1.25}
# Multipliers on the mission's difficulty values (clamped to their bounds).
LEVEL_ENEMY = {
    "beginner": {"enemy_attack_mult": 0.6, "enemy_solution_threshold": 0.75},
    "standard": {},
    "realistic": {"enemy_attack_mult": 1.3, "enemy_solution_threshold": 1.25},
}
# Multiplier on the AI frigate's mean classification and helicopter times.
LEVEL_HUNTER_DELAY = {"beginner": 1.5, "standard": 1.0, "realistic": 0.7}

def apply_level(difficulty: dict, level: str) -> dict:
    """The difficulty values with a realism level's enemy multipliers."""
    result = dict(difficulty)
    for name, factor in LEVEL_ENEMY.get(level, {}).items():
        kind, low, high = DIFFICULTY_FIELDS[name][:3]
        result[name] = kind(clamp(result[name] * factor, low, high))
    return result

# Fester Pool für die Bonus-"zweites U-Boot"-Ziehung (2:1 Richtung AIP,
# entspricht dem bisherigen "harte"/"hardcore"-Pool).
SECOND_SUB_POOL = ("aip_modern", "ssn", "aip_modern")

# M6: Missions-System
SAVE_DIR = os.path.expanduser("~/.u-jagd")
SAVE_PATH = os.path.join(SAVE_DIR, "save.json")   # Legacy (v1)
# A running mission is written to SAVE_DIR/autosave.json this often (wall
# seconds) and on a normal quit; "Continue" in the main menu resumes it.
AUTOSAVE_INTERVAL_S = 300.0
# Fault resilience (src/core/game_resilience.py): a running mission keeps an
# in-memory recovery snapshot this often (wall seconds); a simulation error
# restores it.  More than RECOVERY_MAX_RESTORES restores within
# RECOVERY_WINDOW_S (frame seconds) give up to the main menu with "Continue".
RECOVERY_SNAPSHOT_INTERVAL_S = 60.0
RECOVERY_WINDOW_S = 300.0
RECOVERY_MAX_RESTORES = 2
SAVE_SLOTS = 5
MISSION_ESCAPE_RADIUS_NM = 150.0   # Ziel-Boot gilt als entkommen ab dieser Distanz zum Startpunkt
SCORE_SUNK = 1000                  # pro versenktem Ziel-U-Boot
SCORE_AMMO_BONUS = 200             # pro ungenutztem Torpedo (Sieg)
SCORE_CIVIL_BONUS = 500            # keine zivilen Verluste (Sieg)
SCORE_TIME_BONUS_MAX = 500         # Zeitbonus, anteilig nach verbleibender Zeit

# Incidents at sea (src/core/incidents.py): schedule and the four kinds.
INCIDENT_FIRST_S = (1200.0, 2400.0)
INCIDENT_INTERVAL_S = (1800.0, 3000.0)
INCIDENT_MAX = 6
INCIDENT_NET_RANGE_NM = (3.0, 7.0)     # net across the track this far ahead
INCIDENT_NET_SPREAD_DEG = 25.0
INCIDENT_NET_LENGTH_NM = 2.0
INCIDENT_NET_DEPTH_M = 20.0            # hangs from the surface to this depth
INCIDENT_NET_HIT_NM = 0.03             # within this of the line: over the net
INCIDENT_NET_S = 3600.0                # the fishing boat hauls it after this
INCIDENT_NET_TRANSIENT_S = 20.0        # a submarine tearing free
SCORE_NET_TORN = 100
# Free radio messages of the frigate to HQ (src/core/hq_reports.py): a
# contact report or a request for support is an HF call of RADIO_TX_S,
# one every RADIO_REPORT_INTERVAL_S.  While it goes out, a submarine with
# its antenna up can take an HF/DF bearing on the frigate.  A contact report
# counts at the mission's end when a hostile submarine was within
# CONTACT_REPORT_CONFIRM_NM of the reported fix (at most
# CONTACT_REPORT_SCORED of them).
RADIO_TX_S = 20.0
RADIO_REPORT_INTERVAL_S = 600.0
CONTACT_REPORT_CONFIRM_NM = 3.0
CONTACT_REPORT_SCORED = 3
SCORE_CONTACT_REPORT = 150
INCIDENT_FRONT_LEAD_S = 600.0          # HQ's warning ahead of the front
INCIDENT_FRONT_S = (1800.0, 3600.0)
INCIDENT_DARK_RANGE_NM = (8.0, 15.0)
INCIDENT_DARK_SPEED_KN = (8.0, 13.0)
INCIDENT_DARK_S = 7200.0
INCIDENT_WHALES_RANGE_NM = (3.0, 6.0)
INCIDENT_WHALES_COUNT = (2, 4)
INCIDENT_WHALES_S = 3600.0
# Emergencies aboard: a man overboard survives this long in the water; the
# ship picks him up within this distance at no more than this speed, the
# helicopter hovering within it.
INCIDENT_OVERBOARD_S = 1200.0
INCIDENT_OVERBOARD_PICKUP_NM = 0.1
INCIDENT_OVERBOARD_PICKUP_KN = 5.0
SCORE_OVERBOARD_LOST = 300
SCORE_OVERBOARD_SAVED = 100
AUTOCREW_RESUME_SPEED_KN = 12.0   # Bridge autocrew speed after a recovery
INCIDENT_RUDDER_JAM_S = 60.0           # rudder jammed, then emergency steering
INCIDENT_RUDDER_S = 600.0
INCIDENT_BOAT_S = 900.0                # a jammed snorkel valve / battery gas

# Radio tasking (``src/core/tasking.py``): HQ orders and incidents in the
# built-in scenarios.  The first offer comes after 15-25 minutes, the next
# every 25-45 minutes, never more than two tasks open at once.
TASK_FIRST_OFFER_S = (900.0, 1500.0)
TASK_INTERVAL_S = (1500.0, 2700.0)
TASK_MAX_OFFERS = 6
TASK_MAX_OPEN = 2
TASK_RESPONSE_S = 300.0            # accept or decline inside this window
TASK_DURATION_S = {"identify": 2400.0, "datum": 3000.0, "ras": 3600.0, "patrol": 3600.0}
TASK_EMCON_S = (1200.0, 1800.0)    # ordered radar silence
TASK_EMCON_GRACE_S = 90.0          # time to switch the radars off
TASK_SAR_RANGE_NM = (10.0, 25.0)   # distress position from own ship
TASK_SAR_REPORT_SIGMA_NM = 0.5     # EPIRB position error
TASK_SAR_RADIUS_NM = 1.5           # search circle on the chart
TASK_SAR_LEEWAY = 0.03             # raft windage, fraction of the wind
TASK_SAR_SHIP_NM = 0.25            # alongside: this close ...
TASK_SAR_SHIP_KN = 3.0             # ... at or below this speed
TASK_SAR_SHIP_S = 240.0            # to take the survivors aboard
TASK_SAR_HELO_NM = 0.3             # helicopter overhead the raft
TASK_SAR_HELO_S_PER_PERSON = 60.0  # one hoist cycle per survivor
TASK_SAR_SIGHT_DAY_NM = 2.0        # raft in sight (daylight)
TASK_SAR_SIGHT_NIGHT_NM = 3.0      # strobe light at night
TASK_IDENTIFY_REPORT_SIGMA_NM = 2.0
TASK_IDENTIFY_RADIUS_NM = 3.0
TASK_IDENTIFY_RANGE_NM = 60.0      # only merchants this close are named
TASK_IDENTIFY_HELO_NM = 1.0        # helicopter crew identifies close aboard
TASK_IDENTIFY_SUSPECT = 0.35       # share of merchants HQ then flags
TASK_SUSPECT_SIGMA_NM = 6.0        # datum error HQ passes on a suspect
TASK_DATUM_REAL = 0.75             # share of datums with a boat behind them
TASK_DATUM_SIGMA_NM = 3.0
TASK_DATUM_RADIUS_NM = 5.0
TASK_DATUM_FALSE_RANGE_NM = (15.0, 40.0)
TASK_DATUM_SEARCH_S = 600.0        # search time inside the circle
TASK_RAS_RANGE_NM = (18.0, 28.0)   # supply ship's start from own ship
TASK_RAS_SPEED_KN = 12.0
TASK_RAS_NM = 0.3                  # station alongside
TASK_RAS_SPEED_TOL_KN = 3.0
TASK_RAS_S = 900.0                 # time alongside for the transfer
TASK_RAS_FUEL_FRACTION = 0.7       # offered below this fuel ...
TASK_RAS_PROFILE = "tanker_04"     # friendly supply ship (catalog key)
TASK_RAS_LOADS = 5                 # stores come over in this many loads
TASK_RAS_FULL_FRACTION = 0.05      # a request needs this much fuel missing ...
TASK_RAS_REQUEST_COOLDOWN_S = 1200.0  # ... and this long since the last one
SCORE_TASK = {                     # (done, failed, declined)
    "sar": (600, -400, -200),
    "identify": (250, -100, -100),
    "datum": (250, -150, -200),
    "ras": (100, 0, 0),
    "emcon": (200, -250, -200),
    "patrol": (250, -100, -50),
}

# Crew fatigue, watches and morale (src/core/crew.py; game assumptions).
# A real watch is four hours; the game relieves the watch every hour so a
# session sees the rotation.  Normal rotation keeps the duty watch fresh
# (effectiveness 1.0); action stations tire everybody.
CREW_WATCH_S = 3600.0              # duty watch relieved after this
CREW_TURNOVER_S = 60.0             # new watch settling in
CREW_TURNOVER_FACTOR = 0.85
CREW_TIRE_WATCH_S = 4.0 * 3600.0   # duty watch: fatigue 0 -> 1
CREW_TIRE_ACTION_S = 1.5 * 3600.0  # action stations: everybody
CREW_RECOVER_S = 1.5 * 3600.0      # off watch: fatigue 1 -> 0
CREW_FATIGUE_FREE = 0.25           # fatigue below this costs nothing
CREW_FATIGUE_WEIGHT = 0.6          # effectiveness lost per unit above it
CREW_ACTION_BONUS = 1.1            # alert crew at action stations
CREW_MORALE_START = 0.7
CREW_MORALE_WEIGHT = 0.2           # effectiveness per unit of morale
CREW_MORALE_FATIGUE = 0.5          # low morale tires faster
CREW_DAMAGE_STRESS = 1.5           # fatigue pace while fighting damage
CREW_EFFECT_MIN = 0.5
CREW_EFFECT_MAX = 1.15
CREW_SONAR_DB = 10.0               # dB of recognition differential per unit lost

# Maritime patrol aircraft on call (src/air/mpa.py; game assumptions for a
# P-8-like aircraft: fast transit, slow low search on station).
MPA_TRANSIT_KN = 300.0
MPA_STATION_KN = 200.0
MPA_TURN_DEG_S = 3.0
MPA_ENDURANCE_S = 5.0 * 3600.0      # fuel from take-off
MPA_RESERVE_S = 900.0               # landing reserve on top of the way home
MPA_TURNAROUND_S = 1800.0           # on the ground between sorties
MPA_SORTIES = 2                     # per mission
MPA_ARRIVE_NM = 2.0                 # beyond the 1 NM turn radius at 200 kn
MPA_DROP_POINT_NM = 1.2             # buoy run: released to land on the planned point
MPA_ORBIT_NM = 3.0
MPA_BUOYS = 16
MPA_TORPS = 2
MPA_ALTITUDE_M = 300.0              # search altitude (radar horizon)
MPA_MAD_ALTITUDE_M = 60.0           # MAD run: low passes over the waypoint
MPA_MAD_KN = 180.0
MPA_MAD_LEG_NM = 2.0                # turns back this far past the waypoint
MPA_MAD_LOOK_S = 1.0                # one MAD look per hull and second
# The own aircraft's search radars in the emitter library (heard by the
# crewed boat's ESM; data/contacts/aircraft.json).
MPA_RADAR_EMITTER = "emitter.own_asset.mpa.radar"
HELO_RADAR_EMITTER = "emitter.own_asset.helicopter.radar"
# The bow slams (a sound) when it pitches down through this angle in a
# heavy sea at speed.
HULL_SLAM_PITCH_DEG = 3.5
HULL_SLAM_MIN_KN = 8.0
HULL_SLAM_SEA_STATE = 4
AIRCREW_HOVER_EYE_M = 20.0        # a hovering (dipping) crew's eye height
HELO_RADAR_ALTITUDE_M = 150.0      # transit altitude for the radar horizon
HELO_RADAR_RANGE_NM = 40.0          # helicopter surface-search range, large ship
MPA_RADAR_RANGE_NM = 60.0           # nominal surface-search range, large ship
MPA_RADAR_LOOK_S = 2.0              # one look per target per scan
MPA_RADAR_BEARING_ERR_DEG = 1.0
MPA_RADAR_RANGE_ERR_FRAC = 0.02
MPA_RELAY_NM = 50.0                 # buoys heard only this close to the aircraft
MPA_DATALINK_NM = 250.0             # aircraft to ship link (line of sight at altitude)
MPA_DROP_NM = 2.0                   # torpedo release this close to the datum
MPA_NO_BASE_OFFSET_NM = 150.0       # no friendly airfield: arrives from the map edge
# Group hunt (src/core/consort.py): the consort destroyer of scenarios 21 and 22.
CONSORT_PROFILE = "warship_01"      # catalog key: hull sonar and ASROC
CONSORT_CALLSIGN = "LUETJENS"
CONSORT_STATION_NM = 5.0            # formation station off the frigate (sonar baseline)
CONSORT_HOLD_KN = 4.0
CONSORT_SEARCH_KN = 10.0            # quiet enough for the hull sonar
CONSORT_TRANSIT_KN = 18.0
CONSORT_SPRINT_KN = 26.0
CONSORT_SEARCH_ORBIT_NM = 4.0
CONSORT_PROSECUTE_ORBIT_NM = 2.0
CONSORT_DATALINK_NM = 100.0         # Link 11 (HF) to the frigate
CONSORT_REPORT_S = 10.0             # cadence of the passive cross-fix
CONSORT_PASSIVE_NM = 8.0           # its hull sonar hears a submarine this far
CONSORT_PASSIVE_MAX_KN = 15.0      # faster, its own flow noise deafens it
CONSORT_XFIX_MIN_DEG = 15.0         # poorer cuts are not reported
CONSORT_XFIX_MAX_NM = 30.0
CONSORT_PING_S = 20.0               # active sonar transmission interval
CONSORT_ACTIVE_RANGE_NM = 5.0
CONSORT_ACTIVE_ERR_NM = 0.15
CONSORT_ACTIVE_DEPTH_ERR_M = 15.0
CONSORT_HEAR_PING_NM = 25.0         # submarines intercept its pings this far
CONSORT_FIX_FRESH_S = 120.0         # weapons free: shoot only on fixes this fresh
CONSORT_SHOT_GAP_S = 180.0          # at most one ASROC this often
CONSORT_AUTO_FIX_S = 600.0          # auto mode prosecutes a submarine fix this fresh

# Mission types, free patrol and scenarios live in scenario_config.py.
from src.core.scenario_config import *  # noqa: E402,F401,F403


def scenario_side(key: str) -> str:
    """The side a scenario is played from: "uboot" for a boat mission, else "frigate"."""
    return "uboot" if SCENARIOS[key].get("boat") else "frigate"


def scenarios_for_side(side: str) -> tuple:
    """Scenarios listed for ``side`` in the menus, in ``SCENARIO_ORDER``."""
    return tuple(key for key in SCENARIO_ORDER if scenario_side(key) == side)


# Farben (CRT-Grün-Theme)
COLOR_BG = (4, 9, 15)
# Gemeinsamer geografischer Hintergrund fuer Karte und PPI.
COLOR_GEO_BG = (5, 18, 34)
COLOR_GRID = (16, 36, 42)
COLOR_GEO_GRID = (18, 49, 72)
COLOR_TEXT = (150, 240, 205)
COLOR_TEXT_DIM = (98, 160, 148)
COLOR_WARN = (230, 190, 60)
COLOR_DANGER = (230, 80, 70)
COLOR_OK = (80, 212, 160)
COLOR_SONAR_RING = (40, 96, 90)
COLOR_CONTACT = (255, 255, 255)
COLOR_CONTACT_ZIVIL = (90, 200, 120)
COLOR_CONTACT_WARSHIP = (230, 120, 60)
COLOR_CONTACT_UNBEST = (230, 200, 80)
COLOR_CONTACT_UBOOT = (230, 90, 70)
COLOR_CONTACT_BIO = (110, 200, 200)
COLOR_LAND = (25, 43, 55)
COLOR_LAND_EDGE = (76, 126, 153)
COLOR_SHALLOW = (12, 43, 68)
COLOR_DEEP = (4, 24, 48)
COLOR_ESM = (140, 150, 220)
COLOR_HFDF = (200, 140, 220)
COLOR_FLIGHT = (220, 180, 90)
# Operator plot layer (grease pencil): distinct from every contact colour.
COLOR_PLOT = (255, 160, 230)
# W2: OPZ-Domänenfarbe für Flugkörper/Torpedo - eigene Farbe, da COLOR_DANGER
# und COLOR_CONTACT_UBOOT (Unterwasser-Domäne) sonst fast ununterscheidbar sind.
COLOR_CONTACT_MISSILE = (235, 70, 180)
COLOR_FEED_BG = (5, 12, 18)       # event feed / telemetry / ticker ground
COLOR_PANEL_BG = (8, 18, 25)      # top bar and panel boxes
COLOR_OVERLAY_BG = (5, 14, 20)     # dialogs over a running mission
COLOR_SELECT_BG = (18, 58, 56)     # selected list row
COLOR_ALARM_BG = (10, 22, 28)      # bridge alarm bar
COLOR_TAB_ACTIVE = (18, 60, 62)    # active page tab / selected sonar row

# W3: Feed-Kategorien (Farbe, Kürzel)
FEED_CATEGORIES = {
    "navigation": (COLOR_TEXT, "NAV"),
    "funk": (COLOR_ESM, "FUNK"),
    "sonar": (COLOR_OK, "SONAR"),
    "waffen": (COLOR_WARN, "WAF"),
    "opz": (COLOR_ESM, "OPZ"),
    "schaden": (COLOR_DANGER, "SCH"),
    "mission": (COLOR_CONTACT, "MIS"),
    "welt": (COLOR_TEXT_DIM, "WET"),
    "ausguck": (COLOR_CONTACT, "AUSG"),
}
FEED_MAX_ENTRIES = 200

# Simulationsprotokoll (Option, versteckte Commander-Ansicht):
# Feed-Events plus alle SIMLOG_INTERVAL_S Simulationssekunden ein vollstaendiger
# Zustandssnapshot aller Einheiten/Waffen/Welt für Monitoring und Verifikation.
SIMLOG_MAX_ENTRIES = 256
SIMLOG_INTERVAL_S = 10.0

# Mission debrief (``src/core/debrief.py``): always recorded, shown only after
# the mission ends, never saved.  Frames thin out (and the interval doubles)
# when the cap is reached, so memory stays bounded on the uConsole.
DEBRIEF_INTERVAL_S = 10.0          # mission seconds between frames at start
DEBRIEF_EVENT_S = 1.0              # event checks (first contact, shots, hits)
DEBRIEF_MAX_FRAMES = 360
DEBRIEF_MAX_EVENTS = 160
DEBRIEF_DAMAGE_STEP = 10.0         # own damage points per damage event
DEBRIEF_MISSED_NM = 4.0            # "missed chance": a hostile boat this close ...
DEBRIEF_MISSED_S = 300.0           # ... unheard for at least this long


def aspect_rcs_factor(course_target: float, bearing_from_frigate: float) -> float:
    """M12: Radar-RCS-Aspect: Breitseite zur Fregatte = stärkste Rückmeldung
    (0.55 = Spitzseiten-Aspect, 1.0 = Breitseite). Kanten sind in nautischen
    Grad (0° = Nord, im Uhrzeigersinn)."""
    rel = math.radians(bearing_from_frigate - course_target)
    return 0.55 + 0.45 * abs(math.sin(rel))


def radar_horizon_nm(height_a_m: float, height_b_m: float) -> float:
    """Geometric two-way radar horizon (standard 4/3-Earth-radius refraction):
    2.2256 * (sqrt(h_a) + sqrt(h_b)) in NM for heights in metres. A game
    model of the real effect that low-altitude/low-freeboard targets (a
    sea-skimming missile, a periscope) are invisible to radar until they
    close inside this range, independent of the sensor's nominal power-
    limited range."""
    return 2.2256 * (math.sqrt(max(0.0, height_a_m)) + math.sqrt(max(0.0, height_b_m)))


def nm_to_px(nm: float, nm_per_px: float = NM_PER_PX_MAP) -> float:
    return nm / nm_per_px


def km_to_nm(km: float) -> float:
    return km / 1.852


def kn_to_nm_per_s(kn: float) -> float:
    """Knoten -> NM pro (Spiel-)Sekunde."""
    return kn / 3600.0


def clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def angle_diff_deg(a: float, b: float) -> float:
    """Kleinste Winkel-Differenz (grad) zwischen zwei Kursen."""
    d = (a - b + 540.0) % 360.0 - 180.0
    return d


# --- W1: LOFAR-Bin-Indexierung (fein im niedrigen Hz-Bereich) ---

def lofar_bin(freq_hz: float) -> int:
    """Frequenz (Hz) -> LOFAR-Bin (0..LOFAR_BINS-1)."""
    if freq_hz <= 40.0:
        return int(max(0.0, min(40.0, freq_hz)))
    if freq_hz <= 100.0:
        return 40 + int((freq_hz - 40.0) / 2.0)
    return min(LOFAR_BINS - 1, 40 + 30 + int((freq_hz - 100.0) / 5.0))


def lofar_bin_freq(b: int) -> float:
    """Mittlere Frequenz eines LOFAR-Bins (Hz)."""
    if b < 40:
        return b + 0.5
    if b < 70:
        return 40.0 + (b - 40) * 2.0 + 1.0
    return 100.0 + (b - 70) * 5.0 + 2.5
