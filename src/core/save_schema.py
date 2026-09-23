"""Declarative exact key sets for the ``u-jagd-save-v12`` document.

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
    "ciws_cooldown_s", "schedulers", "rngs", "ui",
    "autocrew", "ais",
})

RNG_STREAMS = frozenset({
    "world", "world_weather", "asm", "damage", "helo", "sonar",
    "flight", "asw", "raid",
})

SHIP_FIELDS = frozenset({
    "x", "y", "course", "target_course", "speed", "target_speed",
    "order_idx", "astern", "hull", "grounding", "turn_rate_scale",
    "rudder_angle", "yaw_rate", "roll", "pitch", "quiet_mode", "clock",
    "fuel_capacity_kg", "fuel_kg", "roll_rate", "pitch_rate", "wake",
})

WORLD_FIELDS = frozenset({
    "hour", "sea_state", "weather_shift_timer", "mode", "generator", "coast",
    "ocean",
})

DAMAGE_FIELDS = frozenset({"repair_mult", "compartments", "teams"})
COMPARTMENT_FIELDS = frozenset({"state", "flood", "fire"})
COMPARTMENT_STATES = ("OK", "FLUTEND", "BESCHAEDIGT", "ZERSTOERT")
