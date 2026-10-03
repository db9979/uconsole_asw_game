"""Parsing and serialisation of the v2 profile systems (references,
machines, endurances, sensors, emitters, weapons, launchers, magazines,
countermeasures) and of provenance sources/claims, plus ``V2_REGISTRIES``.
Moved verbatim from ``catalog.py``, which re-exports every name.
"""

import json

from src.data.catalog_types import (
    ReferenceProfile, AcousticLine, MachineProfile, EnduranceProfile,
    SensorProfile, EmitterProfile, WeaponProfile, LauncherProfile,
    MagazineProfile, CountermeasureProfile, ProfileSystems, CatalogSource)
from src.data.catalog_schema import (
    KEY_PATTERN, PROFILE_SYSTEM_FIELDS, REFERENCE_FIELDS, MACHINE_FIELDS,
    ENDURANCE_FIELDS, SENSOR_FIELDS, EMITTER_FIELDS, WEAPON_FIELDS,
    LAUNCHER_FIELDS, MAGAZINE_FIELDS, COUNTERMEASURE_FIELDS, HULL_TYPES,
    PROPULSION_CODES, PROPULSOR_TYPES, SENSOR_DOMAINS, SENSOR_MODES,
    MODULATION_CODES, RADAR_ROLES, RADAR_POWER_CLASSES, WEAPON_TYPES,
    TARGET_DOMAINS, SEEKER_TYPES, GUIDANCE_TYPES, PAYLOAD_TYPES,
    LAUNCHER_TYPES, COUNTERMEASURE_TYPES, MAX_CATALOG_DOCUMENT_BYTES,
    _schema_object, _schema_number, _schema_text, _schema_pair, _schema_lines)


def _schema_key(value, where, prefix=None):
    if (not isinstance(value, str) or len(value) > 96 or KEY_PATTERN.fullmatch(value) is None
            or (prefix is not None and not value.startswith(prefix))):
        raise ValueError(f"{where}: invalid logical key")


def _schema_nullable_text(value, where):
    if value is not None:
        _schema_text(value, where)


def _schema_nullable_number(value, where, low=0, high=None, positive=False, integer=False):
    if value is not None:
        _schema_number(value, where, low=low, high=high, positive=positive, integer=integer)


def _schema_nullable_pair(value, where, high, equal=False, integer=False, positive=False):
    if value is None:
        return
    _schema_pair(value, where, high, equal=equal, integer=integer)
    if positive and value[0] <= 0:
        raise ValueError(f"{where}: positive range expected")


def _schema_string_array(value, where, allowed=None, maximum=128, nonempty=False):
    if not isinstance(value, list) or len(value) > maximum or (nonempty and not value):
        raise ValueError(f"{where}: invalid string array")
    for item in value:
        _schema_text(item, where)
        if allowed is not None and item not in allowed:
            raise ValueError(f"{where}: invalid value {item!r}")
    if len(set(value)) != len(value):
        raise ValueError(f"{where}: duplicate value")


def _schema_key_array(value, where, maximum=128):
    _schema_string_array(value, where, maximum=maximum)
    for item in value:
        _schema_key(item, where)


def _nullable_pair(value, integer=False):
    if value is None:
        return None
    return tuple(value)


def _nullable_broadband(value, where):
    if value is None:
        return None
    if not isinstance(value, list) or len(value) != 3:
        raise ValueError(f"{where}: null or three-item array expected")
    _schema_number(value[0], where, high=1)
    _schema_pair(value[1:], where, 100000)
    _schema_number(value[1], where, positive=True)
    return tuple(value)


def _acoustic_lines(value, where):
    _schema_lines(value, where)
    return tuple(AcousticLine(*line) for line in value)


def _reference_from_dict(value, where):
    _schema_object(value, REFERENCE_FIELDS, where)
    _schema_key(value["key"], f"{where}.key", "reference.")
    if value["hull_type"] not in HULL_TYPES:
        raise ValueError(f"{where}.hull_type: invalid hull type")
    _schema_nullable_number(value["length_m"], f"{where}.length_m", high=5000, positive=True)
    return ReferenceProfile(
        key=value["key"], hull_type=value["hull_type"], length_m=value["length_m"])


def _machine_from_dict(value, where):
    _schema_object(value, MACHINE_FIELDS, where)
    _schema_key(value["key"], f"{where}.key", "machine.")
    for field in ("cruise_speed_kn", "maximum_speed_kn"):
        _schema_number(value[field], f"{where}.{field}", high=1000, positive=True)
    _schema_nullable_number(value["quiet_speed_kn"], f"{where}.quiet_speed_kn",
                            high=1000, positive=True)
    if value["cruise_speed_kn"] > value["maximum_speed_kn"]:
        raise ValueError(f"{where}: cruise speed exceeds maximum speed")
    if value["quiet_speed_kn"] is not None and value["quiet_speed_kn"] > value["cruise_speed_kn"]:
        raise ValueError(f"{where}: quiet speed exceeds cruise speed")
    _schema_string_array(value["propulsion_codes"], f"{where}.propulsion_codes",
                         PROPULSION_CODES, maximum=8, nonempty=True)
    for field in ("motor_rpm", "shaft_rpm"):
        _schema_nullable_pair(value[field], f"{where}.{field}", 100_000, positive=True)
    if value["propulsor_type"] not in PROPULSOR_TYPES:
        raise ValueError(f"{where}.propulsor_type: invalid propulsor type")
    _schema_nullable_number(value["blade_count"], f"{where}.blade_count",
                            low=1, high=20, integer=True)
    cruise_lines = _acoustic_lines(value["cruise_lines"], f"{where}.cruise_lines")
    high_speed_lines = _acoustic_lines(value["high_speed_lines"], f"{where}.high_speed_lines")
    return MachineProfile(
        key=value["key"], cruise_speed_kn=value["cruise_speed_kn"],
        maximum_speed_kn=value["maximum_speed_kn"], quiet_speed_kn=value["quiet_speed_kn"],
        propulsion_codes=tuple(value["propulsion_codes"]),
        motor_rpm=_nullable_pair(value["motor_rpm"]),
        shaft_rpm=_nullable_pair(value["shaft_rpm"]),
        propulsor_type=value["propulsor_type"], blade_count=value["blade_count"],
        cruise_lines=cruise_lines, high_speed_lines=high_speed_lines,
        cruise_broadband=_nullable_broadband(value["cruise_broadband"],
                                             f"{where}.cruise_broadband"),
        high_speed_broadband=_nullable_broadband(value["high_speed_broadband"],
                                                  f"{where}.high_speed_broadband"))


def _endurance_from_dict(value, where):
    _schema_object(value, ENDURANCE_FIELDS, where)
    _schema_key(value["key"], f"{where}.key", "endurance.")
    for field, high in (
            ("battery_capacity_kwh", 1_000_000), ("hotel_load_kw", 100_000),
            ("propulsion_max_kw", 1_000_000), ("generator_power_kw", 1_000_000),
            ("snorkel_depth_m", 50), ("radio_duration_s", 3600)):
        _schema_number(value[field], f"{where}.{field}", high=high, positive=True)
    _schema_number(value["propulsion_exponent"], f"{where}.propulsion_exponent",
                   low=1, high=5)
    for field in ("reserve_start_fraction", "reserve_stop_fraction"):
        _schema_number(value[field], f"{where}.{field}", high=1, positive=True)
    if value["reserve_start_fraction"] >= value["reserve_stop_fraction"]:
        raise ValueError(f"{where}: reserve hysteresis must be ordered")
    for field in ("aip_power_kw", "aip_energy_kwh"):
        _schema_nullable_number(value[field], f"{where}.{field}",
                                high=1_000_000, positive=True)
    if (value["aip_power_kw"] is None) != (value["aip_energy_kwh"] is None):
        raise ValueError(f"{where}: AIP power and energy must both be present or null")
    if value["generator_power_kw"] <= value["hotel_load_kw"]:
        raise ValueError(f"{where}: generator must exceed hotel load")
    return EnduranceProfile(**value)


def _sensor_from_dict(value, where):
    _schema_object(value, SENSOR_FIELDS, where)
    _schema_key(value["key"], f"{where}.key", "sensor.")
    if value["domain"] not in SENSOR_DOMAINS:
        raise ValueError(f"{where}.domain: invalid sensor domain")
    _schema_string_array(value["modes"], f"{where}.modes", SENSOR_MODES,
                         maximum=2, nonempty=True)
    if type(value["emits"]) is not bool:
        raise ValueError(f"{where}.emits: boolean expected")
    if value["emits"] != ("active" in value["modes"]):
        raise ValueError(f"{where}: active mode and emission state disagree")
    if value["emitter_key"] is not None:
        _schema_key(value["emitter_key"], f"{where}.emitter_key", "emitter.")
        if not value["emits"] or value["domain"] != "radar":
            raise ValueError(f"{where}.emitter_key: only emitting radar sensors use emitters")
    if value["domain"] == "radar" and value["emits"] and value["emitter_key"] is None:
        raise ValueError(f"{where}.emitter_key: emitting radar requires an emitter")
    _schema_nullable_number(value["synthetic_range_nm"], f"{where}.synthetic_range_nm",
                            high=5000, positive=True)
    _schema_nullable_number(value["sensitivity_db"], f"{where}.sensitivity_db",
                            low=-300, high=300)
    _schema_number(value["cadence_s"], f"{where}.cadence_s", low=0.05, high=3600)
    _schema_nullable_number(value["bearing_uncertainty_deg"],
                            f"{where}.bearing_uncertainty_deg", high=180)
    _schema_nullable_number(value["range_uncertainty_nm"],
                            f"{where}.range_uncertainty_nm", high=5000)
    _schema_nullable_number(value["depth_uncertainty_m"],
                            f"{where}.depth_uncertainty_m", high=10000)
    return SensorProfile(
        key=value["key"], domain=value["domain"], modes=tuple(value["modes"]),
        emits=value["emits"], emitter_key=value["emitter_key"],
        synthetic_range_nm=value["synthetic_range_nm"],
        sensitivity_db=value["sensitivity_db"], cadence_s=value["cadence_s"],
        bearing_uncertainty_deg=value["bearing_uncertainty_deg"],
        range_uncertainty_nm=value["range_uncertainty_nm"],
        depth_uncertainty_m=value["depth_uncertainty_m"])


def _emitter_from_dict(value, where):
    _schema_object(value, EMITTER_FIELDS, where)
    _schema_key(value["key"], f"{where}.key", "emitter.")
    if value["domain"] != "radar":
        raise ValueError(f"{where}.domain: only radar emitters are supported")
    _schema_pair(value["frequency_band_hz"], f"{where}.frequency_band_hz", 18e9)
    _schema_number(value["frequency_band_hz"][0], f"{where}.frequency_band_hz",
                   low=500e6, high=18e9)
    _schema_nullable_pair(value["prf_band_hz"], f"{where}.prf_band_hz", 1e7,
                          positive=True)
    _schema_string_array(value["modulation_codes"], f"{where}.modulation_codes",
                         MODULATION_CODES, maximum=16, nonempty=True)
    if value["radar_role"] not in RADAR_ROLES:
        raise ValueError(f"{where}.radar_role: invalid radar role")
    if value["power_class"] not in RADAR_POWER_CLASSES:
        raise ValueError(f"{where}.power_class: invalid power class")
    if not isinstance(value["operating_mode"], str) or not value["operating_mode"]:
        raise ValueError(f"{where}.operating_mode: non-empty string expected")
    _schema_number(value["operating_period_s"], f"{where}.operating_period_s",
                   low=.1, high=3600)
    _schema_number(value["on_duration_s"], f"{where}.on_duration_s",
                   low=.05, high=3600)
    if value["on_duration_s"] > value["operating_period_s"]:
        raise ValueError(f"{where}: on duration exceeds operating period")
    return EmitterProfile(
        key=value["key"], domain=value["domain"],
        frequency_band_hz=_nullable_pair(value["frequency_band_hz"]),
        prf_band_hz=_nullable_pair(value["prf_band_hz"]),
        modulation_codes=tuple(value["modulation_codes"]),
        radar_role=value["radar_role"], operating_mode=value["operating_mode"],
        power_class=value["power_class"],
        operating_period_s=value["operating_period_s"],
        on_duration_s=value["on_duration_s"])


def _weapon_from_dict(value, where):
    _schema_object(value, WEAPON_FIELDS, where)
    _schema_key(value["key"], f"{where}.key", "weapon.")
    if value["weapon_type"] not in WEAPON_TYPES:
        raise ValueError(f"{where}.weapon_type: invalid weapon type")
    _schema_string_array(value["target_domains"], f"{where}.target_domains",
                         TARGET_DOMAINS, maximum=3, nonempty=True)
    if value["runtime_profile_key"] is not None:
        _schema_key(value["runtime_profile_key"], f"{where}.runtime_profile_key")
    _schema_number(value["maximum_speed_kn"], f"{where}.maximum_speed_kn",
                   high=100000, positive=True)
    _schema_pair(value["engagement_range_nm"], f"{where}.engagement_range_nm", 50000)
    if value["seeker_type"] not in SEEKER_TYPES:
        raise ValueError(f"{where}.seeker_type: invalid seeker type")
    if value["guidance_type"] not in GUIDANCE_TYPES:
        raise ValueError(f"{where}.guidance_type: invalid guidance type")
    if value["payload_type"] not in PAYLOAD_TYPES:
        raise ValueError(f"{where}.payload_type: invalid payload type")
    return WeaponProfile(
        key=value["key"], weapon_type=value["weapon_type"],
        target_domains=tuple(value["target_domains"]),
        runtime_profile_key=value["runtime_profile_key"],
        maximum_speed_kn=value["maximum_speed_kn"],
        engagement_range_nm=tuple(value["engagement_range_nm"]),
        seeker_type=value["seeker_type"], guidance_type=value["guidance_type"],
        payload_type=value["payload_type"])


def _launcher_from_dict(value, where):
    _schema_object(value, LAUNCHER_FIELDS, where)
    _schema_key(value["key"], f"{where}.key", "launcher.")
    if value["launcher_type"] not in LAUNCHER_TYPES:
        raise ValueError(f"{where}.launcher_type: invalid launcher type")
    for field in ("mount_count", "ready_count"):
        _schema_number(value[field], f"{where}.{field}", high=10000,
                       positive=field == "mount_count", integer=True)
    if value["ready_count"] > value["mount_count"]:
        raise ValueError(f"{where}: ready count exceeds mount count")
    _schema_number(value["reload_s"], f"{where}.reload_s", high=604800)
    _schema_number(value["arc_center_deg"], f"{where}.arc_center_deg", high=360)
    if value["arc_center_deg"] >= 360:
        raise ValueError(f"{where}.arc_center_deg: angle must be below 360")
    _schema_number(value["arc_width_deg"], f"{where}.arc_width_deg", high=360, positive=True)
    _schema_nullable_number(value["vls_cells"], f"{where}.vls_cells",
                            high=10000, positive=True, integer=True)
    if (value["launcher_type"] == "vls") != (value["vls_cells"] is not None):
        raise ValueError(f"{where}: VLS cells must be present only for VLS launchers")
    _schema_key_array(value["weapon_keys"], f"{where}.weapon_keys")
    if not value["weapon_keys"]:
        raise ValueError(f"{where}.weapon_keys: non-empty array expected")
    return LauncherProfile(
        key=value["key"], launcher_type=value["launcher_type"],
        mount_count=value["mount_count"], ready_count=value["ready_count"],
        reload_s=value["reload_s"], arc_center_deg=value["arc_center_deg"],
        arc_width_deg=value["arc_width_deg"], vls_cells=value["vls_cells"],
        weapon_keys=tuple(value["weapon_keys"]))


def _magazine_from_dict(value, where):
    _schema_object(value, MAGAZINE_FIELDS, where)
    _schema_key(value["key"], f"{where}.key", "magazine.")
    _schema_key(value["weapon_key"], f"{where}.weapon_key", "weapon.")
    _schema_number(value["mission_count"], f"{where}.mission_count", high=100000, integer=True)
    return MagazineProfile(value["key"], value["weapon_key"], value["mission_count"])


def _countermeasure_from_dict(value, where):
    _schema_object(value, COUNTERMEASURE_FIELDS, where)
    _schema_key(value["key"], f"{where}.key", "countermeasure.")
    if value["effect_type"] not in COUNTERMEASURE_TYPES:
        raise ValueError(f"{where}.effect_type: invalid countermeasure type")
    if value["payload_key"] is not None:
        _schema_key(value["payload_key"], f"{where}.payload_key")
    for field in ("mission_count", "ready_count"):
        _schema_number(value[field], f"{where}.{field}", high=100000, integer=True)
    if value["ready_count"] > value["mission_count"]:
        raise ValueError(f"{where}: ready count exceeds mission count")
    _schema_number(value["reload_s"], f"{where}.reload_s", high=604800)
    return CountermeasureProfile(
        value["key"], value["effect_type"], value["payload_key"],
        value["mission_count"], value["ready_count"], value["reload_s"])


def _profile_systems_from_dict(value, where):
    _schema_object(value, PROFILE_SYSTEM_FIELDS, where)
    _schema_key(value["profile_key"], f"{where}.profile_key")
    for field in ("reference_key", "machine_key"):
        if value[field] is not None:
            _schema_key(value[field], f"{where}.{field}")
    for field in ("sensor_keys", "emitter_keys", "launcher_keys", "magazine_keys",
                  "countermeasure_keys"):
        _schema_key_array(value[field], f"{where}.{field}")
    return ProfileSystems(
        profile_key=value["profile_key"], reference_key=value["reference_key"],
        machine_key=value["machine_key"], sensor_keys=tuple(value["sensor_keys"]),
        emitter_keys=tuple(value["emitter_keys"]), launcher_keys=tuple(value["launcher_keys"]),
        magazine_keys=tuple(value["magazine_keys"]),
        countermeasure_keys=tuple(value["countermeasure_keys"]))


def _v2_to_dict(value):
    if isinstance(value, ProfileSystems):
        return {
            "profile_key": value.profile_key, "reference_key": value.reference_key,
            "machine_key": value.machine_key, "sensor_keys": list(value.sensor_keys),
            "emitter_keys": list(value.emitter_keys), "launcher_keys": list(value.launcher_keys),
            "magazine_keys": list(value.magazine_keys),
            "countermeasure_keys": list(value.countermeasure_keys),
        }
    if isinstance(value, ReferenceProfile):
        return {"key": value.key, "hull_type": value.hull_type, "length_m": value.length_m}
    if isinstance(value, MachineProfile):
        lines = lambda items: [[line.frequency_hz, line.relative_level, line.width_hz]
                               for line in items]
        return {
            "key": value.key, "cruise_speed_kn": value.cruise_speed_kn,
            "maximum_speed_kn": value.maximum_speed_kn, "quiet_speed_kn": value.quiet_speed_kn,
            "propulsion_codes": list(value.propulsion_codes),
            "motor_rpm": None if value.motor_rpm is None else list(value.motor_rpm),
            "shaft_rpm": None if value.shaft_rpm is None else list(value.shaft_rpm),
            "propulsor_type": value.propulsor_type, "blade_count": value.blade_count,
            "cruise_lines": lines(value.cruise_lines),
            "high_speed_lines": lines(value.high_speed_lines),
            "cruise_broadband": (None if value.cruise_broadband is None
                                  else list(value.cruise_broadband)),
            "high_speed_broadband": (None if value.high_speed_broadband is None
                                      else list(value.high_speed_broadband)),
        }
    if isinstance(value, EnduranceProfile):
        return {field: getattr(value, field) for field in value.__dataclass_fields__}
    if isinstance(value, SensorProfile):
        return {
            "key": value.key, "domain": value.domain, "modes": list(value.modes),
            "emits": value.emits, "emitter_key": value.emitter_key,
            "synthetic_range_nm": value.synthetic_range_nm,
            "sensitivity_db": value.sensitivity_db, "cadence_s": value.cadence_s,
            "bearing_uncertainty_deg": value.bearing_uncertainty_deg,
            "range_uncertainty_nm": value.range_uncertainty_nm,
            "depth_uncertainty_m": value.depth_uncertainty_m,
        }
    if isinstance(value, EmitterProfile):
        return {
            "key": value.key, "domain": value.domain,
            "frequency_band_hz": list(value.frequency_band_hz),
            "prf_band_hz": None if value.prf_band_hz is None else list(value.prf_band_hz),
            "modulation_codes": list(value.modulation_codes),
            "radar_role": value.radar_role,
            "operating_mode": value.operating_mode,
            "power_class": value.power_class,
            "operating_period_s": value.operating_period_s,
            "on_duration_s": value.on_duration_s,
        }
    if isinstance(value, WeaponProfile):
        return {
            "key": value.key, "weapon_type": value.weapon_type,
            "target_domains": list(value.target_domains),
            "runtime_profile_key": value.runtime_profile_key,
            "maximum_speed_kn": value.maximum_speed_kn,
            "engagement_range_nm": list(value.engagement_range_nm),
            "seeker_type": value.seeker_type, "guidance_type": value.guidance_type,
            "payload_type": value.payload_type,
        }
    if isinstance(value, LauncherProfile):
        return {
            "key": value.key, "launcher_type": value.launcher_type,
            "mount_count": value.mount_count, "ready_count": value.ready_count,
            "reload_s": value.reload_s, "arc_center_deg": value.arc_center_deg,
            "arc_width_deg": value.arc_width_deg, "vls_cells": value.vls_cells,
            "weapon_keys": list(value.weapon_keys),
        }
    if isinstance(value, MagazineProfile):
        return {"key": value.key, "weapon_key": value.weapon_key,
                "mission_count": value.mission_count}
    if isinstance(value, CountermeasureProfile):
        return {
            "key": value.key, "effect_type": value.effect_type,
            "payload_key": value.payload_key, "mission_count": value.mission_count,
            "ready_count": value.ready_count, "reload_s": value.reload_s,
        }
    raise TypeError(f"unsupported v2 value {type(value).__name__}")


def _source_to_dict(value):
    return {
        "id": value.id, "kind": value.kind, "title": value.title,
        "publisher": value.publisher, "url": value.url, "reference": value.reference,
        "retrieved": value.retrieved, "license": value.license,
    }


def _claim_to_dict(value):
    return {
        "resource": value.resource, "profile_key": value.profile_key,
        "field_paths": list(value.field_paths), "status": value.status,
        "source_ids": list(value.source_ids),
    }


def _unique_json_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key {key!r}")
        result[key] = value
    return result


def _read_json(path):
    with path.open("rb") as stream:
        raw = stream.read(MAX_CATALOG_DOCUMENT_BYTES + 1)
    if len(raw) > MAX_CATALOG_DOCUMENT_BYTES:
        raise ValueError(f"{path.name}: document exceeds size limit")
    try:
        return json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_json_object)
    except RecursionError as exc:
        raise ValueError(f"{path.name}: JSON nesting limit exceeded") from exc


def _schema_object_array(value, where, factory, maximum=2048):
    if not isinstance(value, list) or len(value) > maximum:
        raise ValueError(f"{where}: bounded array expected")
    result = []
    seen = set()
    for index, item in enumerate(value):
        item_where = f"{where}[{index}]"
        parsed = factory(item, item_where)
        key = (parsed.profile_key if isinstance(parsed, ProfileSystems)
               else parsed.id if isinstance(parsed, CatalogSource) else parsed.key)
        if key in seen:
            raise ValueError(f"{item_where}: duplicate key {key!r}")
        seen.add(key)
        result.append(parsed)
    return tuple(result)


V2_REGISTRIES = (
    ("profiles", _profile_systems_from_dict),
    ("references", _reference_from_dict),
    ("machines", _machine_from_dict),
    ("endurances", _endurance_from_dict),
    ("sensors", _sensor_from_dict),
    ("emitters", _emitter_from_dict),
    ("weapons", _weapon_from_dict),
    ("launchers", _launcher_from_dict),
    ("magazines", _magazine_from_dict),
    ("countermeasures", _countermeasure_from_dict),
)
