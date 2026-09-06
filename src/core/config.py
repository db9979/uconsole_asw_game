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
AUDIO_ENABLED = True
AUDIO_SAMPLE_RATE = 22050
AUDIO_UPDATE_S = 0.25

# M8: CRT-Scanline-Overlay (subtiler Phosphor-Look)
CRT_SCANLINES = False
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
FEED_RECT = (0, MAIN_BOTTOM, 960, BOTTOM_H)                    # (0,540,960,180)
TELEMETRY_RECT = (960, MAIN_BOTTOM, 320, BOTTOM_H)             # (960,540,320,180)

# --- Zeitsteuerung: eine gemeinsame physikalische Simulationszeit ---
# Bei 1x gilt strikt: 1 reale Sekunde = 1 Simulationssekunde. Der Faktor bleibt
# als Kompatibilitaetsname bestehen, darf aber keine versteckte Kompression sein.
TACTICAL_TIME_SCALE = 1.0
# Spielminuten pro Simulationssekunde: ergibt eine reale 24-h-Uhr.
GAME_TIME_PER_SEC = 1.0 / 60.0
# Zeitraffer beschleunigt die gesamte Simulation bewusst und genau einmal.
TIME_SCALE_STEPS = (1, 5, 15, 30, 60, 120)
TIME_SCALE_DEFAULT = 0            # Index (1x = Echtzeit-Baseline)
PHYS_SUBSTEP_S = 0.05             # max. sim-Sekunden pro Physik-Substep (Anti-Tunneling:
                                  # 45 kn legen in 0.05 s ca. 0.000625 NM zurueck)
PHYS_SUBSTEP_MAX = 240            # haelt auch 0.1-s-Frames bei 120x stabil
MAP_ZOOM_MIN_PX_PER_NM = 1.0      # ganze Welt sichtbar (500 NM in 510 px)
MAP_ZOOM_MAX_PX_PER_NM = 14.0     # Detail-Zoom (~36 NM in 510 px)
MAP_ZOOM_DEFAULT_PX_PER_NM = 10.0 # Start-Zoom (~51 NM hoch, ~64 NM breit)
MAP_ZOOM_WHEEL_FACTOR = 1.25      # stufenlos pro Mausrad-Schritt

# Welt
WORLD_SIZE_NM = 500.0     # quadratische Welt in NM
NM_PER_PX_MAP = 1.0

# Fregatte
SHIP_SPEED_MIN_KN = 4.0
SHIP_SPEED_MAX_KN = 25.0
SHIP_SPEED_START_KN = 12.0
SHIP_TUR_RATE_DEG_PER_S = 0.8         # max. Kurssatz des Schiffes
SHIP_TURN_INPUT_DEG_PER_S = 75.0      # Zielkurs-Drehung bei gedrückter Taste
SHIP_SPEED_RESP_KN_PER_S = 0.08       # ca. 2-4 min bis volle Fahrt
SHIP_SPEED_INPUT_KN_PER_S = 3.0       # Zielgeschw.-Anpassung bei gedrückter Taste

# Sonar (Captain's Log §1)
SONAR_PASSIVE_BASE_NM = 20.0          # Basis-Grundreichweite passiv
SONAR_ACTIVE_BASE_NM = 18.0           # Basis-Grundreichweite aktiv (Ping)
SONAR_PING_COOLDOWN_S = 30.0          # Sende-/Auswertezyklus
SONAR_PING_FIX_MAX_AGE_S = 120.0      # Unsicherheit waechst danach stark
SONAR_PING_HEAR_RANGE_NM = 60.0       # Intercept deutlich weiter als Echo
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
SUB_PATROL_TURN_PERIOD_S = 600.0
# W2: Taktik-Erweiterung
SUB_LUER_DURATION_S = (300.0, 900.0) # LAUER: still liegen + lauschen
SUB_LUER_DIST_NM = 25.0              # LAUER nur, wenn Fregatte naeher
SUB_TORPEDO_ALERT_NM = 35.0          # Torpedostart akustisch hörbar
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

# M5: Schadensmodell (Raten in sim-Sekunden)
DMG_FLOOD_RATE = 0.10          # schwere Flutung: Minuten bis kritisch
DMG_LEAK_RATE = 0.025          # stabilisierte Restleckage
DMG_REPAIR_RATE = 0.12         # Abpumpung pro Reparaturteam
DMG_DESTROY_FLOOD = 70.0       # % Flutung -> Kompartiment ZERSTOERT
DMG_SHIP_SINK_TOTAL = 540.0    # 60 % mittlere Flutung über neun Räume
DMG_SONAR_DEGRADED_FACTOR = 0.5  # Sonar-Reichweitenfaktor bei gestörter Sonarzentrale
ENEMY_TORP_SPEED_KN = 28.0
ENEMY_TORP_RANGE_NM = 30.0
ENEMY_TORP_HIT_DIST_NM = 0.25
ENEMY_TORP_QUIET = 0.10            # laut – passiv gut auffindbar
SUB_ATTACK_COOLDOWN_S = 90.0

# M9: Sensormatrix & manuelle Kontakt-Klassifizierung
# Passiv (Geräusche): nur Peilung. Ping: Position+Tiefe. Radar: Position.
# ESM: nur Peilung von Radargeräten ziviler Schiffe.
ESM_RANGE_NM = 150.0            # ESM-"Reichweite" (Peilung von Radargeräten)
ESM_BEARING_ERR_DEG = 3.0       # ESM-Peilungsfehler (± Grad)
ESM_EMITTER_PROB = 0.6          # Anteil ziviler Schiffe mit aktivem Radargerät
CONTACT_SIG_CONF = 0.40         # Konfidenz, ab der die Geräusch-Signatur lesbar ist
PLAYER_CLASSES = ("U_BOOT", "KAMPFSCHIFF", "BIOLOGISCH", "FAHRZEUG")
PLAYER_CLASS_LABELS = {
    "U_BOOT": "U-Boot",
    "KAMPFSCHIFF": "Kampfschiff",
    "BIOLOGISCH": "Biologisch",
    "FAHRZEUG": "Fahrzeug",
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

# M10: Telegraph & Maschinenraum (diskrete Motorenbefehle)
TELEGRAPH_ORDERS = (
    ("STOP", 0.0),
    ("SLOW", 6.0),
    ("HALF", 10.0),
    ("FULL", 16.0),
    ("FLANK", 25.0),
)
TELEGRAPH_DEFAULT = 2           # Index (HALF)
SHIP_RPM_MIN = 20.0             # Leerlauf-RPM
SHIP_RPM_PER_KN = 2.4
SHIP_MAX_RUDDER_DEG = 30.0
SHIP_RUDDER_RATE_DEG_PER_S = 4.0
SHIP_YAW_RESPONSE_S = 10.0
SHIP_MAX_YAW_RATE_DEG_PER_S = 0.8
SHIP_YAW_DAMPING = 2.0
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
SONAR_FUSION_CONFIRM_DEG = 5.0
SONAR_FUSION_DIVERGENT_DEG = 9.0
SONAR_BT_COOLDOWN_S = 60.0
SONAR_PAGE_COUNT = 6
CZ_BANDS = ((40.0, 70.0), (90.0, 130.0))  # Konvergenzzonen (NM, vom Schallfenster)
CZ_BONUS_NM = 25.0              # zusätzliche passive Reichweite in der Zone

# W1: LOFAR-Wasserfall (hohe Auflösung im niedrigen Hz-Bereich)
LOFAR_FMAX_HZ = 300.0
LOFAR_BINS = 110               # 0-40 Hz @1 Hz, 40-100 Hz @2 Hz, 100-300 Hz @5 Hz
LOFAR_HISTORY_COLS = 80
LOFAR_SAMPLE_S = 0.25          # sim-Sekunden pro Wasserfall-Spalte

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
RADAR_BEARING_ERR_DEG = 0.8
RADAR_RANGE_ERR_FRAC = 0.015
# Observation filters operate on sensor epochs, not render/physics substeps.
OBS_RADAR_EPOCH_S = 0.5
OBS_BEARING_EPOCH_S = 5.0
OBS_RADAR_SMOOTH_TAU_S = 1.5
OBS_BEARING_SMOOTH_TAU_S = 4.0
OBS_HISTORY_MAX = 12

# M13: Funkraum / HFDF
SNOCKEL_DURATION_S = 30.0       # Sendezeit beim Schnorcheln
SNOCKEL_TRIGGER_PPS = 0.003     # Tröge-Wahrscheinlichkeit pro s (nur Diesel/AIP)
SNOCKEL_TRANSMIT_NOISE = -0.20  # Lärmänderung beim Senden (negativ = lauter)
HFDF_RANGE_NM = 120.0
HFDF_BEARING_ERR_DEG = 8.0
WEATHER_BULLETIN_PERIOD_S = 1800.0
WEATHER_SHIFT_PERIOD_S = 3600.0
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
HELO_FUEL_S = 7200.0
HELO_FUEL_RESERVE_S = 1200.0
HELO_RETURN_DIST_NM = 0.3
HELO_TORPS = 2                  # Leichttorpedos pro Start
BUOY_COUNT = 5
BUOY_SPACING_NM = 3.0
BUOY_RANGE_NM = 8.0
BUOY_BATTERY_S = 3600.0
HELO_TORP_SPEED_KN = _HELO_TORP_PROFILE.speed_kn

# M16: Fliegerabwehr (physikalische Geschwindigkeiten)
ASM_SPAWN_DIST_NM = (30.0, 40.0)
ASM_SPEED_KN = 500.0
ASM_JAM_PROB = 0.4
ASM_JAM_BREAK_NM = 20.0         # darunter: Durchstoß, Track wird sichtbar
ASM_SPAWN_FIRST_S = 600.0
ASM_SPAWN_INTERVAL_S = 1200.0
ESSM_SPEED_KN = 2200.0
ESSM_KILL_DIST_NM = 0.12
ESSM_RANGE_NM = 30.0
VLS_CELLS = 6
CIWS_RANGE_NM = 1.5
CIWS_KILL_PPS = 0.35
CIWS_AMMO_DEFAULT = 180
CIWS_ROUNDS_PER_ATTEMPT = 6
CHAFF_COOLDOWN_S = 8.0
CHAFF_RANGE_NM = 8.0
CHAFF_BREAK_P = 0.4

# M15: HSP-5 (Sea Lynx)
HELO_SPEED_KN = 120.0

# W3: Luftfahrt & Airbases (physikalische Knoten)
FLIGHT_SPEED_KN = 200.0
FLIGHT_CIVIL_SPEED_KN = 450.0
FLIGHT_LOITER_NM = (15.0, 30.0) # Patrouillen-Kreis um Airbase
FLIGHT_ATTACK_RANGE_NM = 35.0   # Abschussentfernung für ASM

# W1: TMA (Peilungs-Tracking -> Position + Geschwindigkeit)
TMA_MIN_PTS = 4                 # minimal Peilungen
TMA_MIN_SPAN_S = 180.0          # mehrere Minuten Peilungsbaseline
TMA_RESOLVE_EVERY_S = 2.0       # max. TMA-Re-Solve-Rate pro Ziel (sim-s, CPU-Schutz)
TMA_MIN_COURSE_CHG_DEG = 6.0    # Fregatte muss manövrieren (Beobachtbarkeit)
TMA_MAX_RANGE_NM = 45.0         # Lösungsraum
TMA_SEARCH_STEP_S = 1.5         # Zeit-Schritt der Geschwindigkeits-Suche
TMA_QUALITY_DB = 8.0            # Peil-RMSE (°), ab dem Qualität 0 wird
TMA_RANGE_MIN_QUALITY = 0.35    # TMA-Range erst ab dieser Qualität nutzen
TMA_FINE_COURSE_STEP_DEG = 3
TMA_FINE_SPEED_STEP_KN = 0.5
TMA_PRESENTATION_ALPHA = 0.35
BEARING_TRACK_MAX_PTS = 60
BEARING_TRACK_MIN_INTERVAL_S = 1.0  # sim-s zwischen Peilungen im Track
BEARING_ERR_BOW_DEG = 6.0           # Peilfehler Basis: Bug-Array (±)
BEARING_ERR_TOWED_DEG = 2.0         # Peilfehler Basis: Schleppsonar (±)
BEARING_ERR_SPEED_FACTOR = 0.12     # relativer Aufschlag pro kn Eigenfahrt
BEARING_ERR_QUALITY_SPAN = 0.9      # Fehlerfaktor: 1.4 - SPAN*quality
SONAR_BEARING_NOISE_EPOCH_S = 2.0

# M7: Schwierigkeitslevel (GDD §9)
# quiet_mult: Faktor auf U-Boot-Stillheit (<1 = lauter/easier zu finden)
# repair_mult: Faktor auf Reparaturrate | torp_total: Munitionsbestand
# kill_dist/kill_depth: Treffer-Toleranz der eigenen Torpedos
# enemy_attack_mult / enemy_cooldown_s: Gegenangriff der U-Boote
# second_sub_prob: Chance für ein zusätzliches AIP/SSN-Boot (0.0 -> RNG-Sequenz
#   der M2–M6-Spawns bleibt unverändert)
LEVELS = {
    "leicht": dict(
        label="Leicht", desc="lauter, treffsicher, schnellere Reparatur",
        quiet_mult=0.8, repair_mult=1.5,
        torp_total=6, kill_dist_nm=0.20, kill_depth_m=20.0,
        enemy_attack_mult=0.7, enemy_cooldown_s=1200.0,
        second_sub_prob=0.0,
        second_sub_pool=["aip_modern", "ssn"]),
    "normal": dict(
        label="Normal", desc="Ausgewogene Jagd",
        quiet_mult=1.0, repair_mult=1.0,
        torp_total=6, kill_dist_nm=0.135, kill_depth_m=15.0,
        enemy_attack_mult=1.0, enemy_cooldown_s=900.0,
        second_sub_prob=0.0,
        second_sub_pool=["aip_modern", "ssn"]),
    "harte": dict(
        label="Hart", desc="wenig Munition, schnelle Konter, AIP-Boote",
        quiet_mult=1.0, repair_mult=1.0,
        torp_total=4, kill_dist_nm=0.135, kill_depth_m=15.0,
        enemy_attack_mult=1.5, enemy_cooldown_s=600.0,
        second_sub_prob=0.85,
        second_sub_pool=["aip_modern", "ssn", "aip_modern"]),
}
LEVEL_ORDER = ["leicht", "normal", "harte"]
DEFAULT_LEVEL = "normal"

# M6: Missions-System
SAVE_DIR = os.path.expanduser("~/.u-jagd")
SAVE_PATH = os.path.join(SAVE_DIR, "save.json")   # Legacy (v1)
SAVE_SLOTS = 5
MISSION_ESCAPE_RADIUS_NM = 150.0   # Ziel-Boot gilt als entkommen ab dieser Distanz zum Startpunkt
SCORE_SUNK = 1000                  # pro versenktem Ziel-U-Boot
SCORE_AMMO_BONUS = 200             # pro ungenutztem Torpedo (Sieg)
SCORE_CIVIL_BONUS = 500            # keine zivilen Verluste (Sieg)
SCORE_TIME_BONUS_MAX = 500         # Zeitbonus, anteilig nach verbleibender Zeit

# Missionstypen: Zeitfenster in Simulationssekunden; bei 1x identisch zu real.
# Lange Einsatzfenster: Aufmerksamkeits-/Suchphasen sollen bei 1x nicht nach
# wenigen Minuten enden. Zeitraffer bleibt für die operative Beschleunigung.
# win = "sink" (Ziel versenken) oder "survive" (Zeitlimit überstehen)
MISSION_TYPES = {
    "patrouille": dict(
        name="Patrouille", weight=40, subs=1,
        sub_types=["diesel_alt", "aip_modern", "ssn"],
        animals=(2, 4), civilians=(2, 3), asm=(0, 1), warships=(0, 1),
        time_limit_s=10800, win="sink"),
    "doppeljagd": dict(
        name="Doppeljagd", weight=25, subs=2,
        sub_types=["diesel_alt", "aip_modern", "ssn"],
        animals=(2, 3), civilians=(1, 2), asm=(1, 2), warships=(1, 2),
        time_limit_s=18000, win="sink"),
    "konvoi": dict(
        name="Konvoi-Schutz", weight=20, subs=2,
        sub_types=["aip_modern", "ssn"],
        animals=(1, 3), civilians=(3, 4), asm=(0, 1), warships=(1, 2),
        time_limit_s=14400, win="survive"),
    "nuklearer_abfang": dict(
        name="Nuklearer-Abfang", weight=15, subs=1,
        sub_types=["ssn"],
        animals=(0, 2), civilians=(1, 2), asm=(1, 2), warships=(0, 1),
        time_limit_s=10800, win="sink"),
}

# W4: Vordefinierte Szenarien (eigene Briefings, Startposition, Schwierigkeit)
SCENARIO_ORDER = ("s1_patrouille", "s2_doppeljagd", "s3_abfang", "s4_zufall")
SCENARIOS = {
    "s1_patrouille": dict(
        title="Patrouille Nordsee",
        level="leicht",
        mission_type="patrouille",
        ship_start=(300.0, 380.0), ship_course=300.0,
        briefing=("Auftrag: Sektor NORDSEE-Nord überwachen. Ein alter Diesel- "
                  "Jäger wurde im westlichen Sektor gemeldet. Ziel: Identifizieren, "
                  "klassifizieren und versenken – ohne zivile Verluste."),
        win_text="Ziel-U-Boot versenkt",
        lose_text="Ziel entkommt / Zeitlimit / Fregatte gesunken / ziviler Verlust",
    ),
    "s2_doppeljagd": dict(
        title="Doppeljagd Ostsee",
        level="normal",
        mission_type="doppeljagd",
        ship_start=(250.0, 300.0), ship_course=0.0,
        briefing=("Auftrag: Zwei U-Boote operieren im OSTSEE-Sektor (eines davon "
                  "möglicherweise AIP – nahezu stumm). Belegungen: ESM-Wellen "
                  "werden erwartet. Ziel: Beide Boote versenken, zivile Schifffahrt "
                  "schützen, ASM-Wellen abwehren."),
        win_text="Beide Ziel-U-Boote versenkt",
        lose_text="Ziel entkommt / Zeitlimit / Fregatte gesunken / ziviler Verlust",
    ),
    "s3_abfang": dict(
        title="Nuklearer Abfang",
        level="harte",
        mission_type="nuklearer_abfang",
        ship_start=(320.0, 250.0), ship_course=270.0,
        briefing=("Auftrag: Hochwertiges nukleares U-Boot (SSN) dringt in den "
                  "Sektor ein – extrem leise, taucht tief unter die Thermokline, "
                  "kontert aktiv. Nur 4 Torpedos an Bord. Ziel: Versenken, bevor es "
                  "die Zone verlässt. ASM-Abwehr ist überlebenswichtig."),
        win_text="SSN vor Zeitablauf versenkt",
        lose_text="SSN entkommt / Zeitlimit / Fregatte gesunken",
    ),
    "s4_zufall": dict(
        title="Freie Jagd (Zufall)",
        level=None,          # Level-Auswahlmenü danach
        mission_type=None,   # seed-basierter Missions-Typ
        ship_start=None, ship_course=None,
        briefing="Zufällige Mission – Typ und Schwierigkeit nach Auswahl.",
        win_text="",
        lose_text="",
    ),
}

# Farben (CRT-Grün-Theme)
COLOR_BG = (8, 14, 10)
# Gemeinsamer geografischer Hintergrund fuer Karte und PPI.
COLOR_GEO_BG = (5, 18, 34)
COLOR_GRID = (20, 38, 28)
COLOR_GEO_GRID = (18, 49, 72)
COLOR_TEXT = (140, 230, 160)
COLOR_TEXT_DIM = (105, 158, 126)
COLOR_WARN = (230, 190, 60)
COLOR_DANGER = (230, 80, 70)
COLOR_OK = (90, 210, 120)
COLOR_SONAR_RING = (40, 90, 60)
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

# W3: Feed-Kategorien (Farbe, Kürzel)
FEED_CATEGORIES = {
    "navigation": (COLOR_TEXT, "NAV"),
    "funk": (COLOR_ESM, "FUNK"),
    "sonar": (COLOR_OK, "SONAR"),
    "waffen": (COLOR_WARN, "WAF"),
    "schaden": (COLOR_DANGER, "SCH"),
    "mission": (COLOR_CONTACT, "MIS"),
    "welt": (COLOR_TEXT_DIM, "WET"),
}
FEED_MAX_ENTRIES = 200


def aspect_rcs_factor(course_target: float, bearing_from_frigate: float) -> float:
    """M12: Radar-RCS-Aspect: Breitseite zur Fregatte = stärkste Rückmeldung
    (0.55 = Spitzseiten-Aspect, 1.0 = Breitseite). Kanten sind in nautischen
    Grad (0° = Nord, im Uhrzeigersinn)."""
    rel = math.radians(bearing_from_frigate - course_target)
    return 0.55 + 0.45 * abs(math.sin(rel))


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
