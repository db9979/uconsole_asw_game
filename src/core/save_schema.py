"""Declarative exact key sets for the ``u-jagd-save-v47`` document.

Every persisted block whose shape is validated exactly is declared here, so a
new saved field is added in exactly three places: this module,
``Game.save_state()`` and ``Game._restore_state()``.  The loader additionally
re-serializes every restored candidate and requires byte-for-byte equality
with the input, so a field missing from any of the three places fails loudly.
"""

SAVE_ROOT_FIELDS = frozenset({
    "version", "save_schema", "platform_state_version", "catalog_snapshot",
    "seed", "level", "mission_type", "scenario_key", "mission_name",
    "mission_runtime", "world", "sim_t", "mission_time", "time_scale_idx",
    "score", "mission_result", "result_reason", "ship", "torpedoes",
    "chaff_cd", "vls_cells", "ciws_ammo", "roe", "sonar_mode", "radars",
    "asm_sel", "radio_sel", "hq_timer", "damage", "dmg_cursor", "dmg_team",
    "incident", "subs", "animals", "civilians", "warships", "decoys",
    "torpedoes_in_flight", "enemy_torpedoes", "asw", "air_defense", "asms", "essms",
    "buoys", "helo", "flights", "sonar_controls", "sonar", "messages",
    "hfdf_fixes", "hfdf_log", "radio_picture", "air_picture",
    "opz_affiliations", "air_threat_reported", "esm", "next_entity_ids",
    "asm_spawned", "asm_seq", "warship_asm_seq", "torpedo_seq", "buoy_seq",
    "ciws_cooldown_s", "ciws_mount_deg", "chaff_clouds", "chaff_seq",
    "schedulers", "rngs", "ui",
    "autocrew", "ais", "plot",
    "crew", "weapon_settings", "mission_events",
    "ping_intercepts", "tasking", "watch", "mpa", "radar_marks", "route",
    "incidents", "baffle_clear", "hq_reports", "rbu", "casualties", "hunter_esm",
    "knuckles", "hunter_lead", "swimmer_hold_s", "mission_progress", "free_roam", "consort",
})

# Save v25: the surface radar's unmarked mast echoes and marked boats
# (``Game.radar_blips``, ``radar_blip_seq``, ``_radar_marked``).
RADAR_MARKS_FIELDS = frozenset({"blip_seq", "blips", "marked"})
RADAR_BLIP_FIELDS = frozenset({"seq", "t", "target", "bearing", "range_nm", "error",
                               "observer_x", "observer_y", "x", "y"})
RADAR_MARKED_MAX = 64

# Save v16: foreign active pings still travelling to the frigate, as
# [arrival sim time, source x, source y] in arrival order.
PING_INTERCEPTS_MAX = 16

# Save v15: the operator's torpedo settings (plan 1.3, phase 4).
WEAPON_SETTINGS_FIELDS = frozenset({"torpedo_type", "pattern", "enable_nm", "salvo"})

# Save v15: the crewed submarine binding (``Game._opfor``), or None.
CREW_FIELDS = frozenset({
    "sub_id", "orders", "command_page", "chart_follow", "plot", "esm", "feed",
    "feed_seq", "hold_s", "station", "watch", "radio",
})
CREW_ORDERS_FIELDS = frozenset({
    "silent", "bottomed", "mast", "alarm_seq", "ping_bearing",
    "torpedo_bearing", "esm", "wires", "known_torpedoes",
    "last_course", "torpedo_depth", "salvo", "pending_bearing",
    "steer_torpedo", "events", "battery_state", "keel_warned",
    "obstacle_warned", "obstacle_ahead_nm",
    "scope_rel_deg", "sightings", "sightings_seen", "tdc", "tubes",
    "baffle_clear", "buoy",
})
# Save v24: the attack computer's stadimeter marks, ``{ref: {target_id, marks}}``
# with marks ``[t, x, y]`` in time order.
CREW_TDC_FIELDS = frozenset({"target_id", "marks"})
# One periscope sighting of the crewed boat (plan 1.3, phase 9).
CREW_SIGHTING_FIELDS = frozenset({
    "ref", "target_id", "kind", "cls", "bearing", "span_deg", "aspect",
    "quality", "first_t", "t", "range_nm", "range_sigma_nm", "range_t",
})
CREW_WIRE_FIELDS = frozenset({"state", "ship_out_nm", "stress_s"})
CREW_WIRE_STATES = ("ACTIVE", "BROKEN", "CUT")
CREW_BATTERY_STATES = ("ok", "low", "empty")
CREW_FEED_FIELDS = frozenset({"seq", "t", "stamp", "category", "text"})
CREW_STATION_FIELDS = frozenset({
    "mode", "controls", "sonar", "selected_contact_id", "target_id", "rng",
})
# Sub rows carry the crew-facing orders beside the AI state.
# Sub rows also carry the difficulty's fire-control convergence threshold.
SUB_AI_FIELDS = frozenset({"solution_threshold"})
SUB_CREW_FIELDS = frozenset({
    "manual", "order_course", "order_speed", "order_depth", "last_bottom_m",
    "manual_ping_pending", "ballast", "damage_control",
})

RNG_STREAMS = frozenset({
    "world", "world_weather", "asm", "damage", "helo", "sonar",
    "flight", "asw", "raid",
})

SHIP_FIELDS = frozenset({
    "x", "y", "course", "target_course", "speed", "target_speed",
    "order_idx", "astern", "hull", "grounding", "turn_rate_scale",
    "rudder_angle", "yaw_rate", "roll", "pitch", "quiet_mode", "plant_mode", "clock",
    "fuel_capacity_kg", "fuel_kg", "roll_rate", "pitch_rate", "wake", "deck_quiet_s",
})

WORLD_FIELDS = frozenset({
    "hour", "sea_state", "weather_shift_timer", "mode", "generator", "coast",
    "ocean", "weather_override",
})

DAMAGE_FIELDS = frozenset({"repair_mult", "compartments", "teams",
                           "team_position", "team_eta", "patch_kits",
                           "cooked_off", "capsized", "draft_m"})
COMPARTMENT_FIELDS = frozenset({"state", "flood", "fire", "hole_m2", "heat_s",
                                "shorted", "counterflood"})
COMPARTMENT_STATES = ("OK", "FLUTEND", "BESCHAEDIGT", "ZERSTOERT")
