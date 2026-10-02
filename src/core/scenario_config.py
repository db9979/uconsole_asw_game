"""Mission types, the free patrol and the scenario definitions.

Pure data, moved verbatim from ``config.py`` (which re-exports every name,
so ``config.SCENARIOS`` and friends stay the lookup point for callers and
for tests that patch them).
"""

# Missionstypen: Zeitfenster in Echtzeit-Simulationssekunden.
# Lange Einsatzfenster lassen Zeit für Aufmerksamkeits- und Suchphasen.
# win = "sink" (Ziel versenken) oder "survive" (Zeitlimit überstehen)
# Free patrol (src/core/free_roam.py): the "time limit" is out of reach
# (about three years), so the patrol ends only when own ship is lost.
FREE_TIME_LIMIT_S = 1.0e8
# Encounters: the first after FIRST_S, then one every INTERVAL_S (stateless
# draws keyed by seed and count). The frigate meets a hostile submarine, a
# neutral one in transit, an air raid or merchants; the submarine's hunter
# gets a lead on it, or merchants pass. At most MAX_HOSTILE hostile and
# MAX_NEUTRAL neutral submarines are about at once; far-off units (beyond
# RECYCLE_NM of both sides, unheard) are reused for the next encounter.
FREE_FIRST_ENCOUNTER_S = (300.0, 600.0)
FREE_ENCOUNTER_INTERVAL_S = (900.0, 1800.0)
FREE_ENCOUNTER_WEIGHTS = {"frigate": (("sub", 4), ("neutral_sub", 1), ("raid", 1),
                                      ("merchants", 2)),
                          "uboot": (("hunt", 2), ("merchants", 3))}
FREE_MAX_HOSTILE = 2
FREE_MAX_NEUTRAL = 1
FREE_MAX_MERCHANTS = 10            # merchants about before more are brought in
FREE_SUB_SPAWN_NM = (18.0, 30.0)
FREE_MERCHANT_SPAWN_NM = (12.0, 22.0)
FREE_MERCHANT_GROUP = (1, 3)
FREE_RECYCLE_NM = 70.0
FREE_RECYCLE_QUIET_S = 1200.0
FREE_HUNT_SIGMA_NM = 8.0           # error of the lead the frigate gets on the boat
FREE_HUNT_AFTER_S = 1800.0          # no reported hunt in the first half hour
FREE_HUNT_GAP_S = 3600.0            # and at most one an hour
FREE_LOG_MAX = 8
FREE_NEUTRAL_SUNK = 1000           # penalty: a neutral submarine sunk
FREE_RAID_AFTER_S = 1800.0          # no air raid in the first half hour
# HQ tasks of the frigate: endless, more often than in a scenario.
FREE_TASK_FIRST_S = (120.0, 300.0)
FREE_TASK_INTERVAL_S = (600.0, 1200.0)
FREE_PATROL_RANGE_NM = (12.0, 25.0)
FREE_PATROL_RADIUS_NM = 4.0
FREE_PATROL_HOLD_S = 900.0          # inside the sector this long fulfils it
# Incidents at sea: endless, more often.
FREE_INCIDENT_FIRST_S = (600.0, 1200.0)
FREE_INCIDENT_INTERVAL_S = (1200.0, 2400.0)
# HQ orders of the submarine: almost every broadcast while none is open.
FREE_ORDER_P = 0.85
FREE_ORDER_S = {"attack": 3600.0, "landing": 3600.0, "supply": 2700.0, "recon": 3600.0}
FREE_ORDER_POINTS = {"area": (150, -50), "report": (100, -50), "silence": (100, -50),
                     "attack": (400, -150), "landing": (400, -150), "supply": (100, 0),
                     "recon": (300, -100)}
FREE_MERCHANT_SUNK = 100            # any other merchant the boat sinks
FREE_FRIGATE_SUNK = 1500            # the boat sinks the hunting frigate
FREE_LANDING_HOLD_S = 300.0         # swimmers out: shallow and slow this long
FREE_LANDING_MAX_NM = 40.0          # a coast farther off is not ordered
FREE_SUPPLY_HOLD_S = 300.0          # alongside the supply boat this long
FREE_SUPPLY_RADIUS_NM = 1.0
FREE_SUPPLY_KN = 3.0
FREE_ATTACK_RANGE_NM = (10.0, 20.0)
FREE_ATTACK_SIGMA_NM = 1.5
MISSION_TYPES = {
    "patrouille": dict(
        name="Patrouille", weight=40, subs=1,
        sub_types=["diesel_alt", "aip_modern", "ssn"],
        animals=(2, 4), civilians=(2, 3), asm=(0, 1), warships=(0, 1),
        time_limit_s=10800, short_time_limit_s=1800, win="sink"),
    "doppeljagd": dict(
        name="Doppeljagd", weight=25, subs=2,
        sub_types=["diesel_alt", "aip_modern", "ssn"],
        animals=(2, 3), civilians=(1, 2), asm=(1, 2), warships=(1, 2),
        time_limit_s=18000, short_time_limit_s=3600, win="sink"),
    "konvoi": dict(
        name="Konvoi-Schutz", weight=20, subs=2,
        sub_types=["aip_modern", "ssn"],
        animals=(1, 3), civilians=(3, 4), asm=(0, 1), warships=(1, 2),
        time_limit_s=14400, short_time_limit_s=2700, win="survive"),
    "nuklearer_abfang": dict(
        name="Nuklearer-Abfang", weight=15, subs=1,
        sub_types=["ssn"],
        animals=(0, 2), civilians=(1, 2), asm=(1, 2), warships=(0, 1),
        time_limit_s=10800, short_time_limit_s=2700, win="sink"),
    # Boat missions: the objective is the submarine's (src/core/boat_missions.py).
    "durchbruch": dict(
        name="Durchbruch", weight=0, subs=1,
        sub_types=["diesel_alt", "aip_modern"],
        animals=(1, 2), civilians=(1, 2), asm=(0, 0), warships=(0, 0),
        time_limit_s=18000, short_time_limit_s=3600,
        short_spawn_nm=(4.0, 6.0), short_scale=0.2, win="breakthrough"),
    "aufklaerung": dict(
        name="Aufklaerung", weight=0, subs=1,
        sub_types=["diesel_alt", "aip_modern"],
        animals=(1, 2), civilians=(1, 2), asm=(0, 0), warships=(0, 0),
        time_limit_s=7200, short_time_limit_s=2700,
        short_spawn_nm=(10.0, 16.0), win="recon"),
    "geleitzug": dict(
        name="Geleitzug", weight=0, subs=1,
        sub_types=["diesel_alt", "aip_modern"],
        animals=(1, 2), civilians=(0, 0), asm=(0, 0), warships=(0, 0),
        time_limit_s=10800, short_time_limit_s=2100, win="convoy_attack"),
    "meerenge": dict(
        name="Meerenge", weight=0, subs=1,
        sub_types=["diesel_alt", "aip_modern"],
        animals=(1, 2), civilians=(1, 2), asm=(0, 0), warships=(0, 0),
        time_limit_s=14400, short_time_limit_s=2700, win="strait"),
    "kampfschwimmer": dict(
        name="Kampfschwimmer", weight=0, subs=1,
        sub_types=["diesel_alt", "aip_modern"],
        animals=(1, 2), civilians=(1, 2), asm=(0, 0), warships=(0, 0),
        time_limit_s=21600, short_time_limit_s=2700,
        short_scale=0.25, win="swimmers"),
    "versorger": dict(
        name="Versorger", weight=0, subs=1,
        sub_types=["diesel_alt", "aip_modern"],
        animals=(1, 2), civilians=(0, 0), asm=(0, 0), warships=(0, 0),
        time_limit_s=10800, short_time_limit_s=2700,
        short_scale=0.75, win="escort"),
    # Scenarios 11 to 20 (src/core/mission_modes.py).
    # ``scale``, ``spawn_nm`` and ``goal_fraction`` tune the full length the way
    # the ``short_*`` keys tune the short variant (AI-against-AI fairness).
    "datum": dict(
        name="Datum", weight=0, subs=1,
        sub_types=["diesel_alt", "aip_modern"],
        animals=(1, 2), civilians=(1, 2), asm=(0, 0), warships=(0, 0),
        time_limit_s=7200, short_time_limit_s=2700, short_scale=0.5, win="datum"),
    "fuehlung": dict(
        name="Fuehlung", weight=0, subs=1,
        sub_types=["ssn"],
        animals=(1, 2), civilians=(1, 2), asm=(0, 0), warships=(0, 0),
        time_limit_s=7200, short_time_limit_s=2700, short_scale=0.5,
        scale=0.6, goal_fraction=0.8,
        win="trail"),
    "versorgung": dict(
        name="Versorgung", weight=0, subs=1,
        sub_types=["diesel_alt", "aip_modern"],
        animals=(1, 2), civilians=(0, 0), asm=(0, 0), warships=(0, 0),
        time_limit_s=7200, short_time_limit_s=2700, short_scale=0.5, win="ras"),
    "seenot": dict(
        name="Seenot", weight=0, subs=1,
        sub_types=["diesel_alt", "aip_modern"],
        animals=(1, 2), civilians=(0, 0), asm=(0, 0), warships=(0, 0),
        time_limit_s=7200, short_time_limit_s=2700, short_scale=0.75, scale=1.95,
        win="rescue"),
    "duell": dict(
        name="Duell", weight=0, subs=1,
        sub_types=["aip_modern"],
        animals=(1, 2), civilians=(3, 5), asm=(0, 0), warships=(0, 0),
        time_limit_s=10800, short_time_limit_s=2700, spawn_nm=(8.0, 12.0), win="duel"),
    "heimkehr": dict(
        name="Heimkehr", weight=0, subs=1,
        sub_types=["diesel_alt", "aip_modern"],
        animals=(1, 2), civilians=(1, 2), asm=(0, 0), warships=(0, 0),
        time_limit_s=18000, short_time_limit_s=3600, short_scale=0.35, scale=0.35,
        win="homecoming"),
    "abholung": dict(
        name="Abholung", weight=0, subs=1,
        sub_types=["diesel_alt", "aip_modern"],
        animals=(1, 2), civilians=(1, 2), asm=(0, 0), warships=(0, 0),
        time_limit_s=21600, short_time_limit_s=2700, short_scale=0.25, win="pickup"),
    "lauschposten": dict(
        name="Lauschposten", weight=0, subs=1,
        sub_types=["diesel_alt", "aip_modern"],
        animals=(1, 2), civilians=(1, 2), asm=(0, 0), warships=(0, 0),
        time_limit_s=14400, short_time_limit_s=2700, short_scale=0.5, win="elint"),
    # Group hunt (src/core/game_consort.py): the frigate and its consort.
    "suchgruppe": dict(
        name="Suchgruppe", weight=0, subs=2,
        sub_types=["aip_modern", "ssn"],
        animals=(2, 3), civilians=(2, 3), asm=(0, 0), warships=(0, 0),
        time_limit_s=14400, short_time_limit_s=2700, spawn_nm=(8.0, 14.0), win="sink"),
    # The breakthrough against frigate and destroyer: a quiet boat that starts
    # close and whose goal lies just beyond the frigate's position, in both
    # lengths (tuned with the fairness measurement).
    "jagdgruppe": dict(
        name="Jagdgruppe", weight=0, subs=1,
        sub_types=["aip_modern"],
        animals=(1, 2), civilians=(1, 2), asm=(0, 0), warships=(0, 0),
        time_limit_s=5400, short_time_limit_s=3600, spawn_nm=(4.0, 6.0),
        scale=0.15, short_spawn_nm=(4.0, 6.0), short_scale=0.15, win="breakthrough"),
    # Free patrol (src/core/free_roam.py): no time limit, no short variant.
    # The frigate starts alone; encounters bring the submarines later.
    "freifahrt": dict(
        name="Freie Fahrt", weight=0, subs=0,
        sub_types=["diesel_alt", "aip_modern", "ssn"],
        animals=(2, 4), civilians=(3, 5), asm=(0, 0), warships=(0, 0),
        time_limit_s=FREE_TIME_LIMIT_S, win="free"),
    "freifahrt_uboot": dict(
        name="Freie Fahrt", weight=0, subs=1,
        sub_types=["diesel_alt", "aip_modern"],
        animals=(2, 4), civilians=(3, 5), asm=(0, 0), warships=(0, 0),
        time_limit_s=FREE_TIME_LIMIT_S, win="free_boat"),
}
BOAT_CONVOY_SIZE = 4               # merchants in the escorted convoy
BOAT_CONVOY_SINK = 2               # the boat wins after sinking this many
BOAT_CONVOY_SPEED_KN = 8.0
BOAT_CONVOY_SPACING_NM = 1.0
BOAT_CONVOY_WARHEAD = 100.0        # a heavyweight hit breaks a merchant
# The boat starts on the convoy's bow, this far ahead of it and this far off
# its track to one side (the lesser plus up to the spread), so it can wait
# for a convoy it could not overtake without running into the screen ahead.
BOAT_CONVOY_BOAT_AHEAD_NM = 10.0
BOAT_CONVOY_BOAT_SIDE_NM = 5.0
BOAT_CONVOY_BOAT_SIDE_SPREAD_NM = 3.0
# Mission geography (src/core/mission_geo.py): water shallower than this
# is a wall for a dived boat.
MISSION_GEO_WALL_DEPTH_M = 30.0
# Strait blockade: the narrowest passage this wide near the nominal start,
# with open water this far along it on both sides; without one the gate is
# a declared barrier line this wide across open water.
STRAIT_SEARCH_NM = 100.0
STRAIT_MIN_NM = 4.0
STRAIT_MAX_NM = 24.0
STRAIT_CHANNEL_NM = 16.0
STRAIT_DISTANCE_WEIGHT = 0.1
STRAIT_OPEN_HALF_NM = 8.0
STRAIT_ENTRY_NM = 12.0             # the boat starts this far before the gate
STRAIT_EXIT_NM = 6.0               # its goal lies this far beyond it
STRAIT_TRAFFIC = 6                 # merchants passing through the strait
STRAIT_TRAFFIC_SPACING_NM = 5.0
STRAIT_TRAFFIC_TURN_NM = 14.0      # this far beyond the gate a merchant comes back
# Combat swimmers: a zone off a coast near the nominal start, with at
# least this much water, the coast within this distance behind it and open
# sea for the approach. The boat stops in the zone at swimmer depth for the
# lock-out; the frigate guards a coast section around it.
SWIMMER_SEARCH_NM = 100.0
SWIMMER_MIN_WATER_M = 30.0
SWIMMER_COAST_NM = 3.0
SWIMMER_APPROACH_NM = 8.0
SWIMMER_ZONE_NM = 1.0
SWIMMER_DEPTH_M = 20.0             # swimmers leave through the lock this shallow
SWIMMER_SPEED_KN = 1.5             # at most this slow
SWIMMER_HOLD_S = 600.0             # for this long without a break
SWIMMER_GUARD_NM = 26.0            # radius of the coast section the frigate guards
SWIMMER_GUARD_SHIFT_NM = 13.0      # its centre lies up to this far along the coast
# The frigate starts this share of the section's radius along the coast
# from its centre (at one end of its sweep, drawn from the seed).
SWIMMER_GUARD_START = 0.7
# Supply ship escort: a replenishment ship on a zigzag, the frigate close
# by, the boat ahead of it; one hit from the boat decides it.
ESCORT_SPEED_KN = 12.0
ESCORT_FRIGATE_ABEAM_NM = 1.5      # the frigate starts this far on its beam
ESCORT_CLEAR_NM = 45.0             # clear water ahead of the base course
ESCORT_ZIGZAG_LEG_S = 480.0
ESCORT_ZIGZAG_DEG = (20.0, 40.0)   # each leg this far off the base course
ESCORT_WARHEAD = 100.0
# Boat missions: the goal lies this far beyond the frigate's start, seen from
# the boat's start, and counts as reached within the radius.
BOAT_GOAL_BEYOND_NM = 5.0
BOAT_GOAL_RADIUS_NM = 3.0
BOAT_GOAL_MIN_DEPTH_M = 40.0
# The AI boat's mission legs (src/core/boat_ai.py) when nobody crews it.
BOAT_AI_TRANSIT_KN = 6.0           # quiet transit below the layer
BOAT_AI_PERISCOPE_KN = 3.0         # at periscope depth or creeping in to fire
BOAT_AI_BELOW_LAYER_M = 30.0
BOAT_AI_MIN_WATER_M = 30.0         # the leg detours round shallower water
BOAT_AI_SIGHT_NM = 5.0             # recon: come up and sight the frigate this close
# Recon: at periscope depth the boat raises its periscope for one look every
# SCOPE_CYCLE_S (phase per boat), LOOK_S long; the head sweeps round from
# the bow in SWEEP_S and sights the frigate only where the optics make it
# out.  While raised it is a mast the frigate's and the aircraft's radars see.
BOAT_AI_SCOPE_CYCLE_S = 90.0
BOAT_AI_SCOPE_LOOK_S = 24.0
BOAT_AI_SCOPE_SWEEP_S = 16.0
BOAT_AI_ATTACK_NM = 4.0            # a patrol raid: fire at a merchant this close
BOAT_AI_CONVOY_ATTACK_NM = 3.0     # convoy attack: fire at a merchant this close
# Escort: a lone, zigzagging supply ship is fired at from farther off.
BOAT_AI_ESCORT_ATTACK_NM = 5.25
# ... from this far abeam of its base track, clear of the escort ahead of it.
BOAT_AI_ESCORT_ABEAM_NM = 4.75
BOAT_AI_CLOSING_KN = 4.0           # close a running target this much faster than it
BOAT_AI_FIRE_EVERY_S = 60.0
# Frigate missions: an AI patrol boat torpedoes a merchant within
# BOAT_AI_ATTACK_NM on this fraction of its fire windows, while it is not
# hunted, the frigate is farther than SUB_RAID_FRIGATE_NM and it keeps more
# than SUB_RAID_KEEP_TORPEDOES for the frigate. A lost merchant costs score.
SUB_RAID_P = 0.15
SUB_RAID_QUIET_S = 600.0
SUB_RAID_FRIGATE_NM = 10.0
SUB_RAID_KEEP_TORPEDOES = 2
SCORE_MERCHANT_LOST = 300
BOAT_AI_PREFLOOD_MARGIN_NM = 3.0   # quiet tube flooding starts this far outside
# A hunted or closely watched boat creeps: this slow once the frigate is
# within BOAT_AI_THREAT_NM (its own contact) or for BOAT_AI_HUNTED_S after a
# ping or a torpedo was heard.
BOAT_AI_CREEP_KN = 4.0
BOAT_AI_THREAT_NM = 8.0
BOAT_AI_HUNTED_S = 300.0
# Breakthrough: a frigate this close to the leg ahead is passed this far off.
BOAT_AI_DETOUR_NM = 6.0
BOAT_AI_DETOUR_DEG = 45.0
# Convoy attack: lie in wait this far ahead of the convoy and abeam of its
# track, hovering at the wait speed until the merchants come into range.
BOAT_AI_AMBUSH_AHEAD_NM = 2.0
BOAT_AI_AMBUSH_ABEAM_NM = 3.0
BOAT_AI_AMBUSH_ARRIVE_NM = 1.0
BOAT_AI_WAIT_KN = 2.0
# Strait: hide under a merchant passing the same way this close, this far
# astern of it. Swimmers: come up to swimmer depth this far from the zone.
BOAT_AI_SHADOW_NM = 3.0
BOAT_AI_SHADOW_ASTERN_NM = 0.3
BOAT_AI_SWIMMER_APPROACH_NM = 1.0
# Strait and swimmers: the boat sneaks towards a guarded area this slowly.
BOAT_AI_STEALTH_KN = 4.0
# A mission boat ignores a ping from farther than this (its sonar cannot
# hold the boat there) and evades a closer one at BOAT_AI_EVADE_KN; a
# torpedo still makes it run.
BOAT_AI_PING_IGNORE_NM = 5.0
# ... and may fire back down the bearing of such a ping this long after it.
BOAT_AI_COUNTERFIRE_S = 30.0
BOAT_AI_EVADE_KN = 5.0
# A mission boat attacks a located frigate this many times as readily.
BOAT_AI_ATTACK_MULT = 4.0
# ... and in scenarios 8 to 10, where it must slip past the guard.
BOAT_AI_GUARDED_ATTACK_MULT = 12.0
# Scenarios 11 to 20 (src/core/mission_modes.py). Distances shrink in the
# short variant by the mission type's ``short_scale``.
# Flaming datum: a merchant torpedoed at the nominal start; the boat starts
# beside the wreck and must slip out of the datum circle, the frigate comes
# in from far off with the exact datum.
DATUM_ESCAPE_NM = 12.0
DATUM_FRIGATE_NM = 20.0
DATUM_BOAT_NM = 1.0
DATUM_SPRINT_KN = 9.0              # the boat runs while the frigate is far off
DATUM_SPRINT_S = 1800.0
# Trail: peacetime, weapons tight. HQ hands the contact over ahead of the
# frigate; it must hold sonar contact for a share of the time limit and
# never lose it for too long at a stretch.
TRAIL_START_NM = 6.0
TRAIL_FRESH_S = 30.0               # a contact heard this lately ...
TRAIL_FIX_S = 600.0                # ... and located this lately counts as held
TRAIL_GOAL_FRACTION = 0.5
TRAIL_LOST_S = 1200.0
TRAIL_SPRINT_KN = 22.0
TRAIL_LEG_S = 600.0                # the hunted boat's sprint-and-drift cycle
TRAIL_SPRINT_S = 240.0
TRAIL_DRIFT_KN = 4.0
TRAIL_WEAVE_DEG = 60.0
# Replenishment at sea: a tanker on a straight course; the frigate starts
# low on fuel on its quarter and must lie alongside for the transfer.
RAS_FRIGATE_NM = 3.0                # the frigate starts on the tanker's quarter
RAS_BOAT_AHEAD_NM = 20.0           # the boat waits this far ahead on the tanker's bow
RAS_FUEL_START = 0.4
RAS_LEASH_NM = 4.0                 # the AI frigate prosecutes a datum this close to the tanker
RAS_STATION_NM = 0.15              # its station abeam of the tanker
# Rescue: two life rafts of a ditched patrol aircraft; the boat waits near them.
RESCUE_FRIGATE_NM = 18.0
RESCUE_SPREAD_NM = 2.5
RESCUE_BOAT_NM = 3.0
RESCUE_PERSONS = (5, 4)
# Duel: the boat seeks out the frigate and attacks it.
DUEL_CLOSE_NM = 6.0
# Damaged homecoming: the boat starts damaged with half a battery and must
# reach its home area; the frigate comes in on its flank.
HOMECOMING_NM = 20.0
HOMECOMING_FRIGATE_NM = 12.0
HOMECOMING_DAMAGE = 30.0
HOMECOMING_BATTERY = 0.5
# Agent pick-up: the swimmers' zone and coast section; the team comes aboard
# like the swimmers leave, then the boat runs out to deep water.
PICKUP_HOLD_S = 600.0
PICKUP_ESCAPE_NM = 15.0
# Listening post: the boat records the hunters' radars at periscope depth
# with the mast up (``ELINT_GOAL_S`` emitter-seconds from at least
# ``ELINT_EMITTERS`` kinds within range) and reports them by radio.
ELINT_START_NM = 22.0
ELINT_RANGE_NM = 25.0
ELINT_GOAL_S = 900.0
ELINT_EMITTERS = 2
ELINT_STANDOFF_NM = 12.0

# W4: Vordefinierte Szenarien (eigene Briefings, Startposition, Schwierigkeit)
# hq_intel: "coarse" = HQ meldet nur grob Peilung/Entfernung einer Bedrohung,
# "exact" = HQ benennt zusätzlich die eingesetzten feindlichen Einheiten
# (Typ und Anzahl); None = im Menü wählbar. Nur die Startmeldung hängt davon
# ab, deshalb gehört die Einstellung nicht in den gespeicherten Schwierigkeitssatz.
HQ_INTEL_MODES = ("coarse", "exact")
# Start weather and time of day of a scenario or campaign mission, chosen in
# the briefing, lobby or campaign menu ("random" keeps the seed's own). A
# chosen weather holds for the whole mission, its sea within the kind's band.
START_WEATHER_CHOICES = ("random", "fair", "rain", "storm", "fog")
START_WEATHER_SEA_STATE = {"fair": 1, "rain": 3, "storm": 5, "fog": 1}
START_TIME_CHOICES = ("random", "dawn", "day", "dusk", "night")
START_TIME_HOURS = {"dawn": 6.0, "day": 12.0, "dusk": 19.0, "night": 1.0}
# Mission length (briefing, lobby, campaign, web host): "short" is the
# 30 to 60 minute variant of a scenario (``short_time_limit_s`` of its
# mission type), starting closer to the action: the hostile submarines spawn
# nearer (``SHORT_SUB_SPAWN_NM``) and a boat mission's own start distances
# shrink by ``SHORT_DISTANCE_SCALE``; a mission type may set its own
# ``short_spawn_nm`` (first boat) and ``short_scale``. Each variant is tuned
# with the AI-against-AI fairness measurement. Goals stay the same. The free hunt has
# its own time limit and no short variant. A save keeps the shorter time
# limit, which is how a loaded mission knows it is short.
START_LENGTH_CHOICES = ("normal", "short")
SHORT_SUB_SPAWN_NM = ((5.0, 8.0), (8.0, 14.0))   # first boat, every further one
SHORT_DISTANCE_SCALE = 0.5
SCENARIO_ORDER = ("s1_patrouille", "s2_doppeljagd", "s3_abfang", "s4_zufall",
                  "s11_geleitschutz", "s12_datum", "s13_fuehlung",
                  "s14_hafenschutz", "s15_versorgung", "s16_seenot",
                  "s21_suchgruppe",
                  "s5_durchbruch", "s6_aufklaerung", "s7_geleitzug",
                  "s8_meerenge", "s9_kampfschwimmer", "s10_versorger",
                  "s17_duell", "s18_heimkehr", "s19_abholung", "s20_lauschposten",
                  "s22_jagdgruppe", "frei_fregatte", "frei_uboot")
# Catalog name of each scenario (``scenario.<name>.title`` and friends).
SCENARIO_NAMES = {"s1_patrouille": "patrol", "s2_doppeljagd": "double",
                  "s3_abfang": "intercept", "s4_zufall": "random",
                  "s5_durchbruch": "breakthrough", "s6_aufklaerung": "recon",
                  "s7_geleitzug": "convoy_attack", "s8_meerenge": "strait",
                  "s9_kampfschwimmer": "swimmers", "s10_versorger": "escort",
                  "s11_geleitschutz": "convoy_escort", "s12_datum": "datum",
                  "s13_fuehlung": "trail", "s14_hafenschutz": "harbour",
                  "s15_versorgung": "ras", "s16_seenot": "rescue",
                  "s17_duell": "duel", "s18_heimkehr": "homecoming",
                  "s19_abholung": "pickup", "s20_lauschposten": "elint",
                  "s21_suchgruppe": "search_group", "s22_jagdgruppe": "hunter_group",
                  "frei_fregatte": "free", "frei_uboot": "free_boat"}
SCENARIOS = {
    "s1_patrouille": dict(
        title="Patrouille",
        difficulty=dict(quiet_mult=0.8, repair_mult=1.5, torpedo_count=6,
                       kill_dist_nm=0.20, kill_depth_m=20.0,
                       enemy_attack_mult=0.7, enemy_cooldown_s=1200.0,
                       enemy_solution_threshold=0.25,
                       second_sub_prob=0.0),
        mission_type="patrouille",
        hq_intel="exact",
        ship_start=(300.0, 380.0), ship_course=300.0,
        # Kein Seename hier: Welt/Seed sind im Menü frei wählbar (W/R), die
        # tatsächliche Karte kann von jeder Namensnennung abweichen.
        briefing=("Auftrag: Zugewiesenen Einsatzsektor überwachen. Ein alter Diesel- "
                  "Jäger wurde im westlichen Sektor gemeldet. Ziel: Identifizieren, "
                  "klassifizieren und versenken – ohne zivile Verluste."),
        win_text="Ziel-U-Boot versenkt",
        lose_text="Ziel entkommt / Zeitlimit / Fregatte gesunken / ziviler Verlust",
    ),
    "s2_doppeljagd": dict(
        title="Doppeljagd",
        difficulty=dict(quiet_mult=1.0, repair_mult=1.0, torpedo_count=8,
                       kill_dist_nm=0.135, kill_depth_m=15.0,
                       enemy_attack_mult=1.0, enemy_cooldown_s=900.0,
                       enemy_solution_threshold=0.25,
                       second_sub_prob=0.0),
        mission_type="doppeljagd",
        hq_intel="coarse",
        ship_start=(250.0, 300.0), ship_course=0.0,
        briefing=("Auftrag: Zwei U-Boote operieren im Einsatzsektor (eines davon "
                  "möglicherweise AIP – nahezu stumm). Belegungen: ESM-Wellen "
                  "werden erwartet. Ziel: Beide U-Boote versenken, zivile Schifffahrt "
                  "schützen, ASM-Wellen abwehren."),
        win_text="Beide Ziel-U-Boote versenkt",
        lose_text="Ziel entkommt / Zeitlimit / Fregatte gesunken / ziviler Verlust",
    ),
    "s3_abfang": dict(
        title="Nuklearer Abfang",
        difficulty=dict(quiet_mult=1.0, repair_mult=1.0, torpedo_count=6,
                       kill_dist_nm=0.135, kill_depth_m=15.0,
                       enemy_attack_mult=1.5, enemy_cooldown_s=600.0,
                       enemy_solution_threshold=0.15,
                       second_sub_prob=0.85),
        mission_type="nuklearer_abfang",
        hq_intel="coarse",
        ship_start=(320.0, 250.0), ship_course=270.0,
        briefing=("Auftrag: Hochwertiges nukleares U-Boot (SSN) dringt in den "
                  "Sektor ein – extrem leise, taucht tief unter die Thermokline, "
                  "kontert aktiv. Nur 6 Torpedos an Bord. Ziel: Versenken, bevor es "
                  "die Zone verlässt. ASM-Abwehr ist überlebenswichtig."),
        win_text="SSN vor Zeitablauf versenkt",
        lose_text="SSN entkommt / Zeitlimit / Fregatte gesunken",
    ),
    "s5_durchbruch": dict(
        title="Durchbruch",
        difficulty=dict(quiet_mult=1.0, repair_mult=1.0, torpedo_count=6,
                       kill_dist_nm=0.135, kill_depth_m=15.0,
                       enemy_attack_mult=1.0, enemy_cooldown_s=900.0,
                       enemy_solution_threshold=0.25,
                       second_sub_prob=0.0),
        mission_type="durchbruch",
        hq_intel="coarse",
        ship_start=(260.0, 300.0), ship_course=90.0,
        boat=True,
        briefing="U-Boot: Das Zielgebiet hinter der Fregatte erreichen.",
        win_text="U-Boot aufgehalten",
        lose_text="U-Boot bricht durch / Fregatte gesunken",
    ),
    "s6_aufklaerung": dict(
        title="Aufklaerung",
        difficulty=dict(quiet_mult=1.0, repair_mult=1.0, torpedo_count=6,
                       kill_dist_nm=0.135, kill_depth_m=15.0,
                       enemy_attack_mult=1.0, enemy_cooldown_s=900.0,
                       enemy_solution_threshold=0.25,
                       second_sub_prob=0.0),
        mission_type="aufklaerung",
        hq_intel="coarse",
        ship_start=(280.0, 320.0), ship_course=0.0,
        boat=True,
        briefing="U-Boot: Die Fregatte sichten und per Funk melden.",
        win_text="Meldung verhindert",
        lose_text="U-Boot meldet die Fregatte / Fregatte gesunken",
    ),
    "s7_geleitzug": dict(
        title="Geleitzug",
        difficulty=dict(quiet_mult=1.0, repair_mult=1.0, torpedo_count=6,
                       kill_dist_nm=0.135, kill_depth_m=15.0,
                       enemy_attack_mult=1.0, enemy_cooldown_s=900.0,
                       enemy_solution_threshold=0.25,
                       second_sub_prob=0.0),
        mission_type="geleitzug",
        hq_intel="coarse",
        ship_start=(250.0, 300.0), ship_course=90.0,
        boat=True,
        briefing="U-Boot: Zwei Handelsschiffe des Geleitzugs versenken.",
        win_text="Geleitzug geschuetzt",
        lose_text="Zwei Handelsschiffe verloren / Fregatte gesunken",
    ),
    # Scenarios 8 to 10: ship_start is the nominal start the mission
    # geography is searched from (src/core/mission_geo.py).
    "s8_meerenge": dict(
        title="Meerengen-Sperre",
        difficulty=dict(quiet_mult=1.0, repair_mult=1.0, torpedo_count=6,
                       kill_dist_nm=0.135, kill_depth_m=15.0,
                       enemy_attack_mult=1.0, enemy_cooldown_s=900.0,
                       enemy_solution_threshold=0.25,
                       second_sub_prob=0.0),
        mission_type="meerenge",
        hq_intel="coarse",
        ship_start=(250.0, 180.0), ship_course=90.0,
        boat=True,
        briefing="U-Boot: Durch die Meerenge, die die Fregatte sperrt.",
        win_text="Meerenge gehalten",
        lose_text="U-Boot passiert die Meerenge / Fregatte gesunken",
    ),
    "s9_kampfschwimmer": dict(
        title="Kampfschwimmer",
        difficulty=dict(quiet_mult=1.0, repair_mult=1.0, torpedo_count=6,
                       kill_dist_nm=0.135, kill_depth_m=15.0,
                       enemy_attack_mult=1.0, enemy_cooldown_s=300.0,
                       enemy_solution_threshold=0.25,
                       second_sub_prob=0.0),
        mission_type="kampfschwimmer",
        hq_intel="coarse",
        ship_start=(440.0, 100.0), ship_course=0.0,
        boat=True,
        briefing="U-Boot: Kampfschwimmer vor der Kueste absetzen.",
        win_text="Kueste geschuetzt",
        lose_text="Kampfschwimmer abgesetzt / Fregatte gesunken",
    ),
    "s10_versorger": dict(
        title="Versorgerschutz",
        difficulty=dict(quiet_mult=1.0, repair_mult=1.0, torpedo_count=6,
                       kill_dist_nm=0.135, kill_depth_m=15.0,
                       enemy_attack_mult=1.0, enemy_cooldown_s=900.0,
                       enemy_solution_threshold=0.25,
                       second_sub_prob=0.0),
        mission_type="versorger",
        hq_intel="coarse",
        ship_start=(150.0, 350.0), ship_course=90.0,
        boat=True,
        briefing="U-Boot: Den Versorger im Zickzack treffen.",
        win_text="Versorger geschuetzt",
        lose_text="Versorger versenkt / Fregatte gesunken",
    ),
    # Scenarios 11 to 20 (src/core/mission_modes.py; 1.3.133).
    "s11_geleitschutz": dict(
        title="Geleitschutz",
        difficulty=dict(quiet_mult=1.0, repair_mult=1.0, torpedo_count=6,
                       kill_dist_nm=0.135, kill_depth_m=15.0,
                       enemy_attack_mult=1.0, enemy_cooldown_s=900.0,
                       enemy_solution_threshold=0.25,
                       second_sub_prob=0.0),
        mission_type="geleitzug",
        hq_intel="coarse",
        ship_start=(250.0, 300.0), ship_course=90.0,
        briefing="Fregatte: Einen Geleitzug aus vier Frachtern schuetzen.",
        win_text="Geleitzug geschuetzt",
        lose_text="Zwei Frachter verloren / Fregatte gesunken",
    ),
    "s12_datum": dict(
        title="Brennendes Datum",
        difficulty=dict(quiet_mult=1.0, repair_mult=1.0, torpedo_count=6,
                       kill_dist_nm=0.135, kill_depth_m=15.0,
                       enemy_attack_mult=1.0, enemy_cooldown_s=900.0,
                       enemy_solution_threshold=0.25,
                       second_sub_prob=0.0),
        mission_type="datum",
        hq_intel="coarse",
        ship_start=(300.0, 300.0), ship_course=0.0,
        briefing="Fregatte: Das U-Boot vom Untergangsort eines Frachters aus jagen.",
        win_text="U-Boot versenkt",
        lose_text="U-Boot entkommt / Zeitlimit / Fregatte gesunken",
    ),
    "s13_fuehlung": dict(
        title="Fuehlung halten",
        difficulty=dict(quiet_mult=1.0, repair_mult=1.0, torpedo_count=6,
                       kill_dist_nm=0.135, kill_depth_m=15.0,
                       enemy_attack_mult=1.0, enemy_cooldown_s=900.0,
                       enemy_solution_threshold=0.25,
                       second_sub_prob=0.0),
        mission_type="fuehlung",
        hq_intel="coarse",
        ship_start=(260.0, 320.0), ship_course=90.0,
        briefing="Fregatte: Ein fremdes Atom-U-Boot ohne Waffen verfolgen.",
        win_text="Fuehlung gehalten",
        lose_text="Fuehlung verloren / Zeitlimit",
    ),
    "s14_hafenschutz": dict(
        title="Hafenschutz",
        difficulty=dict(quiet_mult=1.0, repair_mult=1.0, torpedo_count=6,
                       kill_dist_nm=0.135, kill_depth_m=15.0,
                       enemy_attack_mult=1.0, enemy_cooldown_s=300.0,
                       enemy_solution_threshold=0.25,
                       second_sub_prob=0.0),
        mission_type="kampfschwimmer",
        hq_intel="coarse",
        ship_start=(440.0, 100.0), ship_course=0.0,
        briefing="Fregatte: Kampfschwimmer vor der eigenen Kueste verhindern.",
        win_text="Kueste geschuetzt",
        lose_text="Kampfschwimmer abgesetzt / Fregatte gesunken",
    ),
    "s15_versorgung": dict(
        title="Versorgung auf See",
        difficulty=dict(quiet_mult=1.0, repair_mult=1.0, torpedo_count=6,
                       kill_dist_nm=0.135, kill_depth_m=15.0,
                       enemy_attack_mult=1.0, enemy_cooldown_s=900.0,
                       enemy_solution_threshold=0.25,
                       second_sub_prob=0.0),
        mission_type="versorgung",
        hq_intel="coarse",
        ship_start=(200.0, 350.0), ship_course=90.0,
        briefing="Fregatte: Laengsseits eines Tankers Treibstoff uebernehmen.",
        win_text="Versorgung abgeschlossen",
        lose_text="Tanker versenkt / Zeitlimit / Fregatte gesunken",
    ),
    "s16_seenot": dict(
        title="Seenot unter Bedrohung",
        difficulty=dict(quiet_mult=1.0, repair_mult=1.0, torpedo_count=6,
                       kill_dist_nm=0.135, kill_depth_m=15.0,
                       enemy_attack_mult=1.0, enemy_cooldown_s=900.0,
                       enemy_solution_threshold=0.25,
                       second_sub_prob=0.0),
        mission_type="seenot",
        hq_intel="coarse",
        ship_start=(320.0, 280.0), ship_course=0.0,
        briefing="Fregatte: Notgewasserte Flugzeugbesatzung retten.",
        win_text="Besatzung gerettet",
        lose_text="Besatzung verloren / Zeitlimit / Fregatte gesunken",
    ),
    "s17_duell": dict(
        title="Duell",
        difficulty=dict(quiet_mult=1.4, repair_mult=1.0, torpedo_count=6,
                       kill_dist_nm=0.135, kill_depth_m=15.0,
                       enemy_attack_mult=1.5, enemy_cooldown_s=300.0,
                       enemy_solution_threshold=0.35,
                       second_sub_prob=0.0),
        mission_type="duell",
        hq_intel="coarse",
        ship_start=(300.0, 300.0), ship_course=0.0,
        boat=True,
        briefing="U-Boot: Die Fregatte versenken.",
        win_text="Fregatte ueberlebt",
        lose_text="Fregatte gesunken",
    ),
    "s18_heimkehr": dict(
        title="Angeschlagen heim",
        difficulty=dict(quiet_mult=1.0, repair_mult=1.0, torpedo_count=6,
                       kill_dist_nm=0.135, kill_depth_m=15.0,
                       enemy_attack_mult=1.0, enemy_cooldown_s=900.0,
                       enemy_solution_threshold=0.25,
                       second_sub_prob=0.0),
        mission_type="heimkehr",
        hq_intel="coarse",
        ship_start=(280.0, 300.0), ship_course=90.0,
        boat=True,
        briefing="U-Boot: Beschaedigt den Heimathafen erreichen.",
        win_text="U-Boot aufgehalten",
        lose_text="U-Boot erreicht den Heimathafen / Fregatte gesunken",
    ),
    "s19_abholung": dict(
        title="Agenten abholen",
        difficulty=dict(quiet_mult=1.0, repair_mult=1.0, torpedo_count=6,
                       kill_dist_nm=0.135, kill_depth_m=15.0,
                       enemy_attack_mult=1.0, enemy_cooldown_s=900.0,
                       enemy_solution_threshold=0.25,
                       second_sub_prob=0.0),
        mission_type="abholung",
        hq_intel="coarse",
        ship_start=(440.0, 100.0), ship_course=0.0,
        boat=True,
        briefing="U-Boot: Ein Team an der Kueste abholen und entkommen.",
        win_text="Abholung verhindert",
        lose_text="Team abgeholt / Fregatte gesunken",
    ),
    "s20_lauschposten": dict(
        title="Lauschposten",
        difficulty=dict(quiet_mult=1.0, repair_mult=1.0, torpedo_count=6,
                       kill_dist_nm=0.135, kill_depth_m=15.0,
                       enemy_attack_mult=1.0, enemy_cooldown_s=900.0,
                       enemy_solution_threshold=0.25,
                       second_sub_prob=0.0),
        mission_type="lauschposten",
        hq_intel="coarse",
        ship_start=(300.0, 300.0), ship_course=0.0,
        boat=True,
        briefing="U-Boot: Funk und Radar der Fregatte aufzeichnen und melden.",
        win_text="Aufklaerung verhindert",
        lose_text="Aufklaerung gemeldet / Fregatte gesunken",
    ),
    # Group hunt: the frigate with its consort destroyer (src/core/consort.py).
    "s21_suchgruppe": dict(
        title="Suchgruppe",
        difficulty=dict(quiet_mult=1.0, repair_mult=1.0, torpedo_count=8,
                       kill_dist_nm=0.135, kill_depth_m=15.0,
                       enemy_attack_mult=1.0, enemy_cooldown_s=900.0,
                       enemy_solution_threshold=0.25,
                       second_sub_prob=0.0),
        mission_type="suchgruppe",
        hq_intel="coarse",
        ship_start=(250.0, 300.0), ship_course=0.0,
        consort=True,
        briefing="Suchgruppe: Fregatte und Zerstoerer jagen zwei U-Boote.",
        win_text="Beide U-Boote versenkt",
        lose_text="Zeitlimit / Fregatte gesunken",
    ),
    "s22_jagdgruppe": dict(
        title="Jagdgruppe",
        difficulty=dict(quiet_mult=1.0, repair_mult=1.0, torpedo_count=6,
                       kill_dist_nm=0.135, kill_depth_m=15.0,
                       enemy_attack_mult=1.0, enemy_cooldown_s=900.0,
                       enemy_solution_threshold=0.25,
                       second_sub_prob=0.0),
        mission_type="jagdgruppe",
        hq_intel="coarse",
        ship_start=(260.0, 300.0), ship_course=90.0,
        boat=True, consort=True,
        # The destroyer comes off a long patrol with two ASROC left.
        consort_asroc=2,
        briefing="U-Boot: Durch die Jagdgruppe aus Fregatte und Zerstoerer brechen.",
        win_text="U-Boot aufgehalten",
        lose_text="U-Boot bricht durch / Fregatte gesunken",
    ),
    # Free patrol on either side (src/core/free_roam.py; 1.3.135).
    "frei_fregatte": dict(
        title="Freie Fahrt",
        difficulty=dict(quiet_mult=1.0, repair_mult=1.0, torpedo_count=8,
                       kill_dist_nm=0.135, kill_depth_m=15.0,
                       enemy_attack_mult=1.0, enemy_cooldown_s=900.0,
                       enemy_solution_threshold=0.25,
                       second_sub_prob=0.0),
        mission_type="freifahrt",
        hq_intel="coarse",
        ship_start=(300.0, 300.0), ship_course=0.0,
        briefing="Fregatte: Freie Fahrt ohne Zeitlimit, Funkauftraege erfuellen.",
        win_text="",
        lose_text="Fregatte gesunken / ziviler Verlust",
    ),
    "frei_uboot": dict(
        title="Freie Fahrt",
        difficulty=dict(quiet_mult=1.0, repair_mult=1.0, torpedo_count=8,
                       kill_dist_nm=0.135, kill_depth_m=15.0,
                       enemy_attack_mult=1.0, enemy_cooldown_s=900.0,
                       enemy_solution_threshold=0.25,
                       second_sub_prob=0.0),
        mission_type="freifahrt_uboot",
        hq_intel="coarse",
        ship_start=(300.0, 300.0), ship_course=0.0,
        boat=True,
        briefing="U-Boot: Freie Fahrt ohne Zeitlimit, Befehle der Fuehrung erfuellen.",
        win_text="",
        lose_text="U-Boot gesunken",
    ),
    "s4_zufall": dict(
        title="Freie Jagd (Zufall)",
        difficulty=None,     # Custom-Schwierigkeit-Bildschirm danach
        mission_type=None,   # aus difficulty zusammengesetzt
        hq_intel=None,       # im Schwierigkeits-Bildschirm wählbar
        ship_start=None, ship_course=None,
        briefing="Zufällige Mission – Typ und Schwierigkeit nach Auswahl.",
        win_text="",
        lose_text="",
    ),
}
