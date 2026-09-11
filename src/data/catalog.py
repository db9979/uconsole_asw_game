"""Kontakt-Katalog: alle Plattformprofile (Akustik + Verhalten) an einer Stelle.

Die eingebauten Profile werden aus den paketierten ``data.contacts``-JSON-
Ressourcen geladen. Der Katalog enthält:

- 23 U-Boot-Profile (3 Legacy-Archetypen + 20 benannte Klassen)
- 25 feindliche Kampfschiffe (spawnbar, KAMPFSCHIFF)
- 55 zivile Schiffe (Tanker/Passagier/Fracht/Sonstiges)
- Flugzeugprofile (sonar-invisible, nur Radar/ESM)
- 3 Meerestier-Typen, 3 Torpedo-Profile, 1 Dekoy-Profil

Kontakte sind nie an ein einzelnes Profil gebunden: pro Instanz wird aus
Blätterzahl, Takt-Skala und Linien-Offsets ein Fingerprint gerollt
(src/data/fingerprint.py), damit zwei gleiche Klassen unterschiedlich klingen.
"""

import copy
import ipaddress
import json
import math
import os
import re
from dataclasses import dataclass
from datetime import date
from importlib import resources
from types import MappingProxyType
from urllib.parse import urlsplit

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CONTACTS_DIR = os.path.join(_ROOT, "data", "contacts")

CIVIL_CATEGORIES = ("TANKER", "PASSAGIER", "FRACHT", "SONSTIGES")
LEGACY_HOSTILE_SURFACE_KEYS = tuple(f"warship_{index:02d}" for index in range(1, 26))


# ---------------------------------------------------------------------------
# Datenklassen
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class TargetSignature:
    """Akustisches Plattformprofil (passive Sonar-Klassifikation).

    blade_counts: mögliche Schrauben-Blätterzahlen
    rpm_range: (min, max) Wellendrehzahl 1/min (Klassifikation)
    tonal_band_hz: (min, max) Hz der Hauptschraube-Linie bei min..max Fahrt
    cavitation_tendency: 0 (stumm) .. 1 (leicht stark)
    broadband: (level, low_hz, high_hz) für die breitbandige Synthese, sonst None
    secondary_tonals: ((hz, amp, width), ...) z.B. Getriebe/Pumpen-Tonals
    """

    key: str
    label: str
    propulsion: str
    blade_counts: tuple
    rpm_range: tuple
    tonal_band_hz: tuple
    cavitation_tendency: float
    category: str = "FAHRZEUG"
    secondary_tonals: tuple = ()
    broadband: tuple = None
    signature_text: str = ""


@dataclass(frozen=True)
class SubProfile:
    key: str
    name: str
    speed_kn: tuple          # (min, max); max = Patrouillen-Fahrt
    max_depth_m: float
    torpedoes: int
    quiet: float             # 0 laut .. 1 stumm
    aggression: float
    spawn_weight: float
    acoustic: TargetSignature

    @property
    def is_nuclear(self) -> bool:
        """Capability metadata from the JSON propulsion label, not the profile ID."""
        return self.acoustic.propulsion == "elektrisch/Kernantrieb"

    @property
    def requires_air(self) -> bool:
        """Diesel and AIP profiles require an endurance component."""
        return not self.is_nuclear


@dataclass(frozen=True)
class SurfaceProfile:
    key: str
    name: str
    category: str            # TANKER/PASSAGIER/FRACHT/SONSTIGES/KAMPFSCHIFF
    speed_kn: tuple
    callsigns: tuple
    esm_prob: float          # P(Radar/ESM-Emitter an)
    asm_salvo: tuple         # (min, max) feindliche ASMs pro Salve
    asm_cooldown_s: float
    loiter_nm: float         # Patrouillen-Radius um Basis (nur feindlich)
    spawn_weight: float
    acoustic: TargetSignature


@dataclass(frozen=True)
class AircraftProfile:
    key: str
    name: str
    nation: str
    kind: str                # "civil" | "military"
    speed_kn: float
    esm: bool
    esm_range_nm: float
    loiter_nm: tuple         # (min, max)
    spawn_weight: float
    signature_text: str = ""


@dataclass(frozen=True)
class AnimalProfile:
    key: str
    name: str
    depth_min: float
    depth_max: float
    speed_kn: float
    quiet: float
    size_nm: float
    spawn_weight: float
    lines: tuple             # ((hz, amp, width), ...) biologische Tonalität
    signature_text: str = ""


@dataclass(frozen=True)
class TorpedoProfile:
    key: str
    name: str
    used_by: str             # "frigate" | "helo" | "enemy"
    speed_kn: float
    range_nm: float
    hit_dist_nm: float
    acoustic: TargetSignature = None


@dataclass(frozen=True)
class DecoyProfile:
    key: str
    name: str
    life_s: float
    speed_kn: float
    cooldown_s: float
    chance: float
    lines: tuple
    signature_text: str = ""


@dataclass(frozen=True, slots=True)
class ReferenceProfile:
    key: str
    variant: str | None
    variant_year: int | None
    refit_year: int | None
    aliases: tuple[str, ...]
    roles: tuple[str, ...]
    hull_type: str
    displacement_tonnes: float | None
    displacement_basis: str
    length_m: float | None
    beam_waterline_m: float | None
    beam_overall_m: float | None
    flight_deck_width_m: float | None
    draft_m: float | None
    ship_crew: tuple[int, int] | None
    air_group_crew: tuple[int, int] | None


@dataclass(frozen=True, slots=True)
class AcousticLine:
    frequency_hz: float
    relative_level: float
    width_hz: float


@dataclass(frozen=True, slots=True)
class MachineProfile:
    key: str
    cruise_speed_kn: float
    maximum_speed_kn: float
    quiet_speed_kn: float | None
    propulsion_codes: tuple[str, ...]
    motor_rpm: tuple[float, float] | None
    shaft_rpm: tuple[float, float] | None
    propulsor_type: str
    blade_count: int | None
    cruise_lines: tuple[AcousticLine, ...]
    high_speed_lines: tuple[AcousticLine, ...]
    cruise_broadband: tuple[float, float, float] | None
    high_speed_broadband: tuple[float, float, float] | None


@dataclass(frozen=True, slots=True)
class EnduranceProfile:
    key: str
    battery_capacity_kwh: float
    hotel_load_kw: float
    propulsion_max_kw: float
    propulsion_exponent: float
    generator_power_kw: float
    aip_power_kw: float | None
    aip_energy_kwh: float | None
    reserve_start_fraction: float
    reserve_stop_fraction: float
    snorkel_depth_m: float
    radio_duration_s: float


@dataclass(frozen=True, slots=True)
class SensorProfile:
    key: str
    domain: str
    modes: tuple[str, ...]
    emits: bool
    emitter_key: str | None
    synthetic_range_nm: float | None
    sensitivity_db: float | None
    cadence_s: float
    bearing_uncertainty_deg: float | None
    range_uncertainty_nm: float | None
    depth_uncertainty_m: float | None


@dataclass(frozen=True, slots=True)
class EmitterProfile:
    key: str
    domain: str
    frequency_band_hz: tuple[float, float]
    prf_band_hz: tuple[float, float] | None
    modulation_codes: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class WeaponProfile:
    key: str
    weapon_type: str
    target_domains: tuple[str, ...]
    runtime_profile_key: str | None
    maximum_speed_kn: float
    engagement_range_nm: tuple[float, float]
    seeker_type: str
    guidance_type: str
    payload_type: str


@dataclass(frozen=True, slots=True)
class LauncherProfile:
    key: str
    launcher_type: str
    mount_count: int
    ready_count: int
    reload_s: float
    arc_center_deg: float
    arc_width_deg: float
    vls_cells: int | None
    weapon_keys: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class MagazineProfile:
    key: str
    weapon_key: str
    mission_count: int


@dataclass(frozen=True, slots=True)
class CountermeasureProfile:
    key: str
    effect_type: str
    payload_key: str | None
    mission_count: int
    ready_count: int
    reload_s: float


@dataclass(frozen=True, slots=True)
class ProfileSystems:
    profile_key: str
    reference_key: str | None
    machine_key: str | None
    sensor_keys: tuple[str, ...]
    emitter_keys: tuple[str, ...]
    launcher_keys: tuple[str, ...]
    magazine_keys: tuple[str, ...]
    countermeasure_keys: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class CatalogSource:
    id: str
    kind: str
    title: str
    publisher: str | None
    url: str | None
    reference: str
    retrieved: str | None
    license: str | None


@dataclass(frozen=True, slots=True)
class ProvenanceClaim:
    resource: str
    profile_key: str
    field_paths: tuple[str, ...]
    status: str
    source_ids: tuple[str, ...]


def build_catalog() -> "ContactCatalog":
    """Lädt den vollständigen eingebauten Katalog aus Paketressourcen."""
    return _load_catalog_from(resources.files("data.contacts"))


# ---------------------------------------------------------------------------
# Katalog
# ---------------------------------------------------------------------------

class ContactCatalog:
    """Alle Plattformprofile + abgeleitete Listen (Spawn-Pools, Bibliothek)."""

    def __init__(self, subs, surfaces, aircraft, animals, torpedoes, decoys,
                 db_source: str = "data/contacts", library_signatures=(),
                 document_versions=None, documents=None, references=(), machines=(),
                  sensors=(), emitters=(), endurances=(), weapons=(), launchers=(), magazines=(),
                 countermeasures=(), profile_systems=(), profile_resources=None,
                 sources=(), provenance_claims=(), provenance_document=None,
                 runtime_bindings=None):
        self.subs = dict(subs)
        self.surfaces = dict(surfaces)
        self.aircraft = dict(aircraft)
        self.animals = dict(animals)
        self.torpedoes = dict(torpedoes)
        self.decoys = dict(decoys)
        self.db_source = db_source
        self.acoustic_by_key = {}
        for p in (list(self.subs.values()) + list(self.surfaces.values())):
            self.acoustic_by_key[p.acoustic.key] = p.acoustic
        for t in self.torpedoes.values():
            if t.acoustic is not None:
                self.acoustic_by_key[t.acoustic.key] = t.acoustic
        for signature in library_signatures:
            self.acoustic_by_key[signature.key] = signature
        self.acoustic_profiles = tuple(self.acoustic_by_key.values())
        self.civilian_signatures = tuple(
            s for s in self.acoustic_profiles
            if s.category in CIVIL_CATEGORIES)
        # Resource/category selects legacy spawn pools. Runtime side and doctrine
        # belong to the mission instance, never to a reusable platform profile.
        self.civilian_surfaces = tuple(
            p for p in self.surfaces.values() if p.category in CIVIL_CATEGORIES)
        self.hostile_surfaces = tuple(
            p for p in self.surfaces.values() if p.category == "KAMPFSCHIFF")
        legacy_hostile = tuple(
            self.surfaces[key] for key in LEGACY_HOSTILE_SURFACE_KEYS
            if key in self.surfaces)
        self.legacy_hostile_surfaces = legacy_hostile or self.hostile_surfaces
        self.document_versions = MappingProxyType(dict(document_versions or {}))
        self.references = MappingProxyType(dict(references))
        self.machines = MappingProxyType(dict(machines))
        self.endurances = MappingProxyType(dict(endurances))
        self.sensors = MappingProxyType(dict(sensors))
        self.emitters = MappingProxyType(dict(emitters))
        self.weapons = MappingProxyType(dict(weapons))
        self.launchers = MappingProxyType(dict(launchers))
        self.magazines = MappingProxyType(dict(magazines))
        self.countermeasures = MappingProxyType(dict(countermeasures))
        self.profile_systems = MappingProxyType(dict(profile_systems))
        self.profile_resources = MappingProxyType(dict(profile_resources or {}))
        self.sources = MappingProxyType(dict(sources))
        self.provenance_claims = tuple(provenance_claims)
        self.runtime_bindings = MappingProxyType(dict(
            RUNTIME_BINDINGS if runtime_bindings is None else runtime_bindings))
        documents = documents or {}
        self._document_entries = {
            name: copy.deepcopy(document["entries"])
            for name, document in documents.items()
        }
        self._v2_layout = {
            name: {
                field: tuple(item["profile_key"] if field == "profiles" else item["key"]
                             for item in document.get(field, []))
                for field, _ in V2_REGISTRIES
            }
            for name, document in documents.items() if document["version"] == 2
        }
        self._has_provenance = provenance_document is not None

    # --- Auswahl-Hilfen (deterministisch über übergebene rng) ---

    def pick_surface(self, rng, hostile: bool = False):
        pool = (self.legacy_hostile_surfaces if hostile
                else self.civilian_surfaces)
        return _weighted_pick(rng, pool)

    def pick_sub(self, rng, pool=None):
        keys = pool if pool else list(self.subs.keys())
        pool = [self.subs[k] for k in keys if k in self.subs]
        if not pool:
            pool = list(self.subs.values())
        return _weighted_pick(rng, pool)

    def pick_aircraft(self, rng, kind: str):
        pool = [a for a in self.aircraft.values() if a.kind == kind]
        if not pool:
            pool = list(self.aircraft.values())
        return _weighted_pick(rng, pool)

    def pick_animal(self, rng):
        return _weighted_pick(rng, tuple(self.animals.values()))

    def get_torpedo(self, key: str):
        return self.torpedoes.get(key)

    def get_decoy(self, key: str):
        return self.decoys.get(key)

    def acoustic_for(self, key: str) -> TargetSignature | None:
        return self.acoustic_by_key.get(key)

    def reconstruct_documents(self) -> dict:
        """Return a detached, field- and JSON-type-preserving document snapshot."""
        registries = {
            "profiles": self.profile_systems, "references": self.references,
            "machines": self.machines, "sensors": self.sensors,
            "endurances": self.endurances,
            "emitters": self.emitters, "weapons": self.weapons,
            "launchers": self.launchers, "magazines": self.magazines,
            "countermeasures": self.countermeasures,
        }
        result = {}
        for name, version in self.document_versions.items():
            document = {"version": version,
                        "entries": copy.deepcopy(self._document_entries[name])}
            if version == 2:
                for field, _ in V2_REGISTRIES:
                    if field not in self._v2_layout[name] or (
                            field == "endurances" and not self._v2_layout[name][field]):
                        continue
                    document[field] = [
                        _v2_to_dict(registries[field][key])
                        for key in self._v2_layout[name][field]
                    ]
            result[name] = document
        return result

    def reconstruct_provenance(self) -> dict | None:
        """Return the detached source manifest, if the catalog supplied one."""
        if not self._has_provenance:
            return None
        return {
            "version": 1,
            "sources": [_source_to_dict(source) for source in self.sources.values()],
            "claims": [_claim_to_dict(claim) for claim in self.provenance_claims],
        }

    def runtime_snapshot(self) -> dict:
        """Return only the validated values that currently affect simulation."""
        documents = self.reconstruct_documents()
        return {
            "version": RUNTIME_SNAPSHOT_VERSION,
            "entries": {
                name: copy.deepcopy(self._document_entries[name])
                for name in CONTACT_FILENAMES
            },
            "bindings": dict(self.runtime_bindings),
            "components": {
                name: {
                    "version": documents[name]["version"],
                    **{
                        field: copy.deepcopy(documents[name].get(field, []))
                        for field, _ in V2_REGISTRIES
                    },
                }
                for name in CONTACT_FILENAMES
            },
        }


def _weighted_pick(rng, pool):
    weights = [max(0.0, p.spawn_weight) for p in pool]
    total = sum(weights)
    if total <= 0:
        return rng.choice(pool)
    roll = rng.random() * total
    acc = 0.0
    for p, w in zip(pool, weights):
        acc += w
        if roll < acc:
            return p
    return pool[-1]


# ---------------------------------------------------------------------------
# JSON-Loader
# ---------------------------------------------------------------------------

CONTACT_FIELDS = {
    "subs.json": {"key", "name", "speed_kn", "max_depth_m", "torpedoes",
                  "quiet", "aggression", "spawn_weight", "acoustic"},
    "warships.json": {"key", "name", "category", "hostile", "speed_kn",
                      "callsigns", "esm_prob", "asm_salvo", "asm_cooldown_s",
                      "loiter_nm", "spawn_weight", "acoustic"},
    "aircraft.json": {"key", "name", "nation", "kind", "speed_kn", "esm",
                      "esm_range_nm", "loiter_nm", "spawn_weight", "signature_text"},
    "animals.json": {"key", "name", "depth_min", "depth_max", "speed_kn",
                     "quiet", "size_nm", "spawn_weight", "lines", "signature_text"},
    "torpedoes.json": {"key", "name", "used_by", "speed_kn", "range_nm", "hit_dist_nm"},
    "decoys.json": {"key", "name", "life_s", "speed_kn", "cooldown_s",
                    "chance", "lines", "signature_text"},
    "acoustics.json": {"key", "label", "propulsion", "blades", "rpm_range",
                       "tonal_band_hz", "cavitation_tendency", "category",
                       "secondary_tonals", "broadband", "signature_text"},
}
CONTACT_FIELDS["civilians.json"] = CONTACT_FIELDS["warships.json"]
ACOUSTIC_FIELDS = CONTACT_FIELDS["acoustics.json"] - {"key"}
ACOUSTIC_CATEGORIES = (*CIVIL_CATEGORIES, "KAMPFSCHIFF", "U_BOOT", "FAHRZEUG", "BIOLOGISCH")
CONTACT_FILENAMES = tuple(CONTACT_FIELDS)
SOURCES_FILENAME = "sources.json"
KEY_PATTERN = re.compile(r"[a-z][a-z0-9_-]*(?:\.[a-z0-9][a-z0-9_-]*)*\Z")
V2_DOCUMENT_FIELDS = {
    "version", "entries", "profiles", "references", "machines", "sensors",
    "emitters", "weapons", "launchers", "magazines", "countermeasures",
}
V2_OPTIONAL_DOCUMENT_FIELDS = {"endurances"}
PROFILE_SYSTEM_FIELDS = {
    "profile_key", "reference_key", "machine_key", "sensor_keys", "emitter_keys",
    "launcher_keys", "magazine_keys", "countermeasure_keys",
}
REFERENCE_FIELDS = {
    "key", "variant", "variant_year", "refit_year", "aliases", "roles", "hull_type",
    "displacement_tonnes", "displacement_basis", "length_m", "beam_waterline_m",
    "beam_overall_m", "flight_deck_width_m", "draft_m", "ship_crew", "air_group_crew",
}
MACHINE_FIELDS = {
    "key", "cruise_speed_kn", "maximum_speed_kn", "quiet_speed_kn",
    "propulsion_codes", "motor_rpm", "shaft_rpm", "propulsor_type", "blade_count",
    "cruise_lines", "high_speed_lines", "cruise_broadband", "high_speed_broadband",
}
ENDURANCE_FIELDS = {
    "key", "battery_capacity_kwh", "hotel_load_kw", "propulsion_max_kw",
    "propulsion_exponent", "generator_power_kw", "aip_power_kw",
    "aip_energy_kwh", "reserve_start_fraction", "reserve_stop_fraction",
    "snorkel_depth_m", "radio_duration_s",
}
SENSOR_FIELDS = {
    "key", "domain", "modes", "emits", "emitter_key", "synthetic_range_nm",
    "sensitivity_db", "cadence_s", "bearing_uncertainty_deg",
    "range_uncertainty_nm", "depth_uncertainty_m",
}
EMITTER_FIELDS = {"key", "domain", "frequency_band_hz", "prf_band_hz", "modulation_codes"}
WEAPON_FIELDS = {
    "key", "weapon_type", "target_domains", "runtime_profile_key", "maximum_speed_kn",
    "engagement_range_nm", "seeker_type", "guidance_type", "payload_type",
}
LAUNCHER_FIELDS = {
    "key", "launcher_type", "mount_count", "ready_count", "reload_s",
    "arc_center_deg", "arc_width_deg", "vls_cells", "weapon_keys",
}
MAGAZINE_FIELDS = {"key", "weapon_key", "mission_count"}
COUNTERMEASURE_FIELDS = {
    "key", "effect_type", "payload_key", "mission_count", "ready_count", "reload_s",
}
SOURCE_FIELDS = {"id", "kind", "title", "publisher", "url", "reference", "retrieved", "license"}
CLAIM_FIELDS = {"resource", "profile_key", "field_paths", "status", "source_ids"}

REFERENCE_ROLES = {
    "air_defense", "anti_submarine", "attack_submarine", "carrier", "cargo",
    "escort", "maritime_patrol", "passenger_transport", "replenishment", "strike",
    "training",
}
HULL_TYPES = {
    "aircraft_carrier", "container_ship", "cruiser", "destroyer", "frigate",
    "fixed_wing_aircraft", "replenishment_ship", "submarine", "support_ship", "unknown",
}
DISPLACEMENT_BASES = {"deadweight", "full_load", "light", "standard", "submerged", "unknown"}
PROPULSION_CODES = {
    "biological", "diesel", "electric", "gas_turbine", "integrated_electric",
    "nuclear_steam", "other", "steam",
}
PROPULSOR_TYPES = {"propeller", "pumpjet", "waterjet", "other", "unknown"}
SENSOR_DOMAINS = {"ais", "esm", "hfdf", "radar", "sonar", "visual"}
SENSOR_MODES = {"active", "passive"}
MODULATION_CODES = {"continuous_wave", "frequency_agile", "pulse", "pulse_doppler", "unknown"}
WEAPON_TYPES = {"asm", "asroc", "ciws", "sam", "torpedo"}
TARGET_DOMAINS = {"air", "subsurface", "surface"}
SEEKER_TYPES = {"acoustic_active", "acoustic_passive", "command", "infrared", "none", "radar_active"}
GUIDANCE_TYPES = {"command", "datum", "homing", "inertial", "terminal_homing"}
PAYLOAD_TYPES = {"high_explosive", "kinetic", "torpedo"}
LAUNCHER_TYPES = {"ciws", "rail", "torpedo_tube", "vls"}
COUNTERMEASURE_TYPES = {"acoustic_decoy", "chaff", "rf_softkill", "towed_acoustic"}
MAX_CATALOG_DOCUMENT_BYTES = 4 * 1024 * 1024
MAX_CATALOG_ENTRIES = 4096
RUNTIME_SNAPSHOT_VERSION = 2
RUNTIME_BINDINGS = {
    "frigate_torpedo": "frigate_torp",
    "helicopter_torpedo": "helo_torp",
    "enemy_torpedo": "enemy_torp",
    "submarine_decoy": "decoy",
    "civil_flight": "civil_transit",
    "military_flight": "mil_patrol",
}


def _schema_object(value, fields, where, optional=()):
    if not isinstance(value, dict):
        raise ValueError(f"{where}: object expected")
    missing = fields - set(optional) - value.keys()
    extra = value.keys() - fields
    if missing or extra:
        raise ValueError(f"{where}: missing fields {sorted(missing)}; unknown fields {sorted(extra)}")


def _schema_number(value, where, low=0, high=None, positive=False, integer=False):
    if type(value) not in (int, float) or (integer and type(value) is not int):
        raise ValueError(f"{where}: {'integer' if integer else 'number'} expected")
    # Comparing integers directly avoids overflowing float conversion on hostile JSON.
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError(f"{where}: finite number expected")
    if value < low or (positive and value <= 0) or (high is not None and value > high):
        raise ValueError(f"{where}: number outside allowed range")
    if abs(value) > 1e100:
        raise ValueError(f"{where}: number outside safe range")


def _schema_text(value, where):
    if not isinstance(value, str) or not value.strip() or len(value) > 500:
        raise ValueError(f"{where}: non-empty string of at most 500 characters expected")
    if any(ord(char) < 32 and char not in "\n\t" for char in value):
        raise ValueError(f"{where}: control characters not allowed")


def _schema_pair(value, where, high, equal=False, integer=False):
    if not isinstance(value, list) or len(value) != 2:
        raise ValueError(f"{where}: two-item array expected")
    for item in value:
        _schema_number(item, where, high=high, integer=integer)
    if value[0] > value[1] or (not equal and value[0] == value[1]):
        raise ValueError(f"{where}: range must be ordered")


def _schema_lines(value, where):
    if not isinstance(value, list) or len(value) > 256:
        raise ValueError(f"{where}: array of at most 256 lines expected")
    for line in value:
        if not isinstance(line, list) or len(line) != 3:
            raise ValueError(f"{where}: three-item array expected")
        _schema_number(line[0], where, high=100000, positive=True)
        _schema_number(line[1], where, high=1)
        _schema_number(line[2], where, high=10000, positive=True)


def _schema_acoustic(value, where, category=None):
    _schema_object(value, ACOUSTIC_FIELDS, where)
    for field in ("label", "propulsion", "signature_text"):
        _schema_text(value[field], f"{where}.{field}")
    blades = value["blades"]
    if not isinstance(blades, list) or len(blades) > 20:
        raise ValueError(f"{where}.blades: positive integer array expected")
    for blade in blades:
        _schema_number(blade, f"{where}.blades", low=1, high=20, integer=True)
    if len(set(blades)) != len(blades):
        raise ValueError(f"{where}.blades: duplicate value")
    for field in ("rpm_range", "tonal_band_hz"):
        band = value[field]
        _schema_pair(band, f"{where}.{field}", 100000, equal=band == [0, 0])
    _schema_number(value["cavitation_tendency"], f"{where}.cavitation_tendency", high=1)
    if value["category"] not in ACOUSTIC_CATEGORIES or (
            category is not None and value["category"] != category):
        raise ValueError(f"{where}.category: invalid category")
    _schema_lines(value["secondary_tonals"], f"{where}.secondary_tonals")
    broadband = value["broadband"]
    if broadband is not None:
        if not isinstance(broadband, list) or len(broadband) != 3:
            raise ValueError(f"{where}.broadband: null or three-item array expected")
        _schema_number(broadband[0], f"{where}.broadband", high=1)
        _schema_pair(broadband[1:], f"{where}.broadband", 100000)
        _schema_number(broadband[1], f"{where}.broadband", positive=True)


def validate_contact_entry(filename, entry, where="entry"):
    """Strict JSON schema shared by the package loader and offline validator.

    Bounds are defensive authoring limits, not real-platform performance claims.
    Editor documents have their own versioned schema and are not runtime profiles.
    """
    optional = {"acoustic"} if filename == "torpedoes.json" else set()
    _schema_object(entry, CONTACT_FIELDS[filename] | optional, where, optional)
    _schema_text(entry["key"], f"{where}.key")
    if filename == "acoustics.json":
        _schema_acoustic({k: v for k, v in entry.items() if k != "key"}, where)
        return
    _schema_text(entry["name"], f"{where}.name")
    for field in ("nation", "signature_text"):
        if field in entry:
            _schema_text(entry[field], f"{where}.{field}")
    for field in ("hostile", "esm"):
        if field in entry and type(entry[field]) is not bool:
            raise ValueError(f"{where}.{field}: boolean expected")
    for field, maximum in (("quiet", 1), ("aggression", 1), ("esm_prob", 1),
                           ("chance", 1), ("spawn_weight", 100000),
                           ("depth_min", 2000), ("depth_max", 2000),
                           ("esm_range_nm", 5000)):
        if field in entry:
            _schema_number(entry[field], f"{where}.{field}", high=maximum)
    for field, maximum in (("max_depth_m", 2000), ("range_nm", 5000),
                           ("hit_dist_nm", 100), ("size_nm", 100),
                           ("life_s", 604800), ("cooldown_s", 604800)):
        if field in entry:
            _schema_number(entry[field], f"{where}.{field}", high=maximum, positive=True)
    if "lines" in entry:
        _schema_lines(entry["lines"], f"{where}.lines")
    if filename in ("subs.json", "warships.json", "civilians.json"):
        _schema_pair(entry["speed_kn"], f"{where}.speed_kn", 1000)
        category = "U_BOOT" if filename == "subs.json" else entry["category"]
        _schema_acoustic(entry["acoustic"], f"{where}.acoustic", category)
    else:
        _schema_number(entry["speed_kn"], f"{where}.speed_kn", high=5000,
                       positive=filename != "animals.json")
    if filename == "subs.json":
        _schema_number(entry["torpedoes"], f"{where}.torpedoes", high=100, integer=True)
        if entry["acoustic"]["propulsion"] not in (
                "Diesel-elektrisch", "elektrisch/AIP", "elektrisch/Kernantrieb"):
            raise ValueError(f"{where}.acoustic.propulsion: invalid submarine propulsion")
    elif filename in ("warships.json", "civilians.json"):
        allowed = ("KAMPFSCHIFF",) if filename == "warships.json" else CIVIL_CATEGORIES
        if entry["category"] not in allowed:
            raise ValueError(f"{where}.category: invalid surface category")
        if entry["hostile"] != (filename == "warships.json"):
            raise ValueError(f"{where}.hostile: does not match surface catalog")
        callsigns = entry["callsigns"]
        if not isinstance(callsigns, list) or len(callsigns) > 256:
            raise ValueError(f"{where}.callsigns: string array expected")
        for callsign in callsigns:
            _schema_text(callsign, f"{where}.callsigns")
        _schema_pair(entry["asm_salvo"], f"{where}.asm_salvo", 100, equal=True, integer=True)
        _schema_number(entry["asm_cooldown_s"], f"{where}.asm_cooldown_s", high=604800)
        _schema_number(entry["loiter_nm"], f"{where}.loiter_nm", high=5000)
    elif filename == "aircraft.json":
        if entry["kind"] not in ("civil", "military"):
            raise ValueError(f"{where}.kind: invalid aircraft kind")
        _schema_pair(entry["loiter_nm"], f"{where}.loiter_nm", 5000, equal=True)
    elif filename == "animals.json":
        if entry["depth_min"] >= entry["depth_max"]:
            raise ValueError(f"{where}: depth range must be ordered")
    elif filename == "torpedoes.json":
        if entry["used_by"] not in ("frigate", "helo", "enemy"):
            raise ValueError(f"{where}.used_by: invalid torpedo owner")
        if "acoustic" in entry:
            _schema_acoustic(entry["acoustic"], f"{where}.acoustic", "FAHRZEUG")


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
    _schema_nullable_text(value["variant"], f"{where}.variant")
    for field in ("variant_year", "refit_year"):
        _schema_nullable_number(value[field], f"{where}.{field}", low=1850, high=2100, integer=True)
    if (value["variant_year"] is not None and value["refit_year"] is not None
            and value["refit_year"] < value["variant_year"]):
        raise ValueError(f"{where}: refit year precedes variant year")
    _schema_string_array(value["aliases"], f"{where}.aliases", maximum=64)
    _schema_string_array(value["roles"], f"{where}.roles", REFERENCE_ROLES, maximum=16)
    if value["hull_type"] not in HULL_TYPES:
        raise ValueError(f"{where}.hull_type: invalid hull type")
    _schema_nullable_number(value["displacement_tonnes"], f"{where}.displacement_tonnes",
                            high=1_000_000, positive=True)
    if value["displacement_basis"] not in DISPLACEMENT_BASES:
        raise ValueError(f"{where}.displacement_basis: invalid displacement basis")
    if ((value["displacement_tonnes"] is None) !=
            (value["displacement_basis"] == "unknown")):
        raise ValueError(f"{where}: displacement value and basis disagree")
    for field in ("length_m", "beam_waterline_m", "beam_overall_m",
                  "flight_deck_width_m", "draft_m"):
        _schema_nullable_number(value[field], f"{where}.{field}", high=5000, positive=True)
    if (value["beam_waterline_m"] is not None and value["beam_overall_m"] is not None
            and value["beam_overall_m"] < value["beam_waterline_m"]):
        raise ValueError(f"{where}: overall beam below waterline beam")
    for field in ("ship_crew", "air_group_crew"):
        _schema_nullable_pair(value[field], f"{where}.{field}", 100_000,
                              equal=True, integer=True)
    return ReferenceProfile(
        key=value["key"], variant=value["variant"], variant_year=value["variant_year"],
        refit_year=value["refit_year"], aliases=tuple(value["aliases"]),
        roles=tuple(value["roles"]), hull_type=value["hull_type"],
        displacement_tonnes=value["displacement_tonnes"],
        displacement_basis=value["displacement_basis"],
        length_m=value["length_m"], beam_waterline_m=value["beam_waterline_m"],
        beam_overall_m=value["beam_overall_m"],
        flight_deck_width_m=value["flight_deck_width_m"], draft_m=value["draft_m"],
        ship_crew=_nullable_pair(value["ship_crew"], integer=True),
        air_group_crew=_nullable_pair(value["air_group_crew"], integer=True))


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
    _schema_pair(value["frequency_band_hz"], f"{where}.frequency_band_hz", 1e12)
    _schema_number(value["frequency_band_hz"][0], f"{where}.frequency_band_hz", positive=True)
    _schema_nullable_pair(value["prf_band_hz"], f"{where}.prf_band_hz", 1e7,
                          positive=True)
    _schema_string_array(value["modulation_codes"], f"{where}.modulation_codes",
                         MODULATION_CODES, maximum=16, nonempty=True)
    return EmitterProfile(
        key=value["key"], domain=value["domain"],
        frequency_band_hz=_nullable_pair(value["frequency_band_hz"]),
        prf_band_hz=_nullable_pair(value["prf_band_hz"]),
        modulation_codes=tuple(value["modulation_codes"]))


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
        return {
            "key": value.key, "variant": value.variant, "variant_year": value.variant_year,
            "refit_year": value.refit_year, "aliases": list(value.aliases),
            "roles": list(value.roles), "hull_type": value.hull_type,
            "displacement_tonnes": value.displacement_tonnes,
            "displacement_basis": value.displacement_basis, "length_m": value.length_m,
            "beam_waterline_m": value.beam_waterline_m,
            "beam_overall_m": value.beam_overall_m,
            "flight_deck_width_m": value.flight_deck_width_m, "draft_m": value.draft_m,
            "ship_crew": None if value.ship_crew is None else list(value.ship_crew),
            "air_group_crew": (None if value.air_group_crew is None
                                else list(value.air_group_crew)),
        }
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


def _read_document(path) -> dict:
    data = _read_json(path)
    if not isinstance(data, dict) or type(data.get("version")) is not int:
        raise ValueError(f"{path.name}.version: unsupported schema version")
    version = data["version"]
    if version == 1:
        _schema_object(data, {"version", "entries"}, path.name)
    elif version == 2:
        _schema_object(data, V2_DOCUMENT_FIELDS | V2_OPTIONAL_DOCUMENT_FIELDS,
                       path.name, V2_OPTIONAL_DOCUMENT_FIELDS)
    else:
        raise ValueError(f"{path.name}.version: unsupported schema version")
    entries = data["entries"]
    if (not isinstance(entries, list) or not entries
            or len(entries) > MAX_CATALOG_ENTRIES):
        raise ValueError(f"{path.name}.entries: bounded non-empty array expected")
    seen = set()
    for index, entry in enumerate(entries):
        where = f"{path.name}.entries[{index}]"
        validate_contact_entry(path.name, entry, where)
        if version == 2:
            _schema_key(entry["key"], f"{where}.key")
        if entry["key"] in seen:
            raise ValueError(f"{where}: duplicate key {entry['key']!r}")
        seen.add(entry["key"])
    if version == 2:
        for field, factory in V2_REGISTRIES:
            _schema_object_array(data.get(field, []), f"{path.name}.{field}", factory)
    return data


def _read_entries(path) -> list:
    return _read_document(path)["entries"]


def _source_url(value, where):
    _schema_text(value, where)
    if "\\" in value or any(ord(char) < 32 for char in value):
        raise ValueError(f"{where}: invalid public URL")
    parsed = urlsplit(value)
    if (parsed.scheme != "https" or not parsed.hostname or parsed.username is not None
            or parsed.password is not None):
        raise ValueError(f"{where}: public HTTPS URL expected")
    try:
        parsed.port
    except ValueError as exc:
        raise ValueError(f"{where}: public HTTPS URL expected") from exc
    hostname = parsed.hostname.lower()
    local_suffixes = (".local", ".home.arpa", ".internal", ".localhost",
                      ".nip.io", ".sslip.io")
    if (hostname.endswith(".") or hostname.rstrip(".") == "localhost"
            or hostname.endswith(local_suffixes)):
        raise ValueError(f"{where}: public HTTPS URL expected")
    try:
        address = ipaddress.ip_address(hostname)
    except ValueError:
        labels = hostname.split(".")
        if (len(labels) < 2 or all(label.isdigit() for label in labels)
                or any(not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", label)
                       for label in labels)):
            raise ValueError(f"{where}: public HTTPS URL expected")
    else:
        if not address.is_global:
            raise ValueError(f"{where}: public HTTPS URL expected")


def _source_from_dict(value, where):
    _schema_object(value, SOURCE_FIELDS, where)
    _schema_key(value["id"], f"{where}.id")
    if value["kind"] not in ("public_source", "manufacturer", "game_assumption"):
        raise ValueError(f"{where}.kind: invalid source kind")
    _schema_text(value["title"], f"{where}.title")
    _schema_text(value["reference"], f"{where}.reference")
    _schema_nullable_text(value["license"], f"{where}.license")
    if value["kind"] == "game_assumption":
        if any(value[field] is not None for field in ("publisher", "url", "retrieved")):
            raise ValueError(f"{where}: game assumptions cannot cite an external source")
    else:
        _schema_text(value["publisher"], f"{where}.publisher")
        _source_url(value["url"], f"{where}.url")
        if not isinstance(value["retrieved"], str) or not re.fullmatch(
                r"\d{4}-\d{2}-\d{2}", value["retrieved"]):
            raise ValueError(f"{where}.retrieved: ISO date expected")
        try:
            date.fromisoformat(value["retrieved"])
        except ValueError as exc:
            raise ValueError(f"{where}.retrieved: ISO date expected") from exc
    return CatalogSource(
        value["id"], value["kind"], value["title"], value["publisher"], value["url"],
        value["reference"], value["retrieved"], value["license"])


def _claim_from_dict(value, where):
    _schema_object(value, CLAIM_FIELDS, where)
    if value["resource"] not in CONTACT_FIELDS:
        raise ValueError(f"{where}.resource: unknown catalog resource")
    _schema_key(value["profile_key"], f"{where}.profile_key")
    _schema_string_array(value["field_paths"], f"{where}.field_paths",
                         maximum=128, nonempty=True)
    for path in value["field_paths"]:
        if (not path.startswith("/") or "//" in path or "\\" in path or "%" in path
                or "*" in path or any(part in ("", ".", "..")
                                      for part in path[1:].split("/"))):
            raise ValueError(f"{where}.field_paths: invalid logical field path")
    if value["status"] not in ("published", "derived", "game_assumption", "unknown"):
        raise ValueError(f"{where}.status: invalid provenance status")
    _schema_key_array(value["source_ids"], f"{where}.source_ids", maximum=32)
    return ProvenanceClaim(
        value["resource"], value["profile_key"], tuple(value["field_paths"]),
        value["status"], tuple(value["source_ids"]))


def _read_provenance(path):
    data = _read_json(path)
    _schema_object(data, {"version", "sources", "claims"}, path.name)
    if type(data["version"]) is not int or data["version"] != 1:
        raise ValueError(f"{path.name}.version: unsupported schema version")
    sources = _schema_object_array(data["sources"], f"{path.name}.sources",
                                   _source_from_dict, maximum=1024)
    if not isinstance(data["claims"], list) or len(data["claims"]) > 10000:
        raise ValueError(f"{path.name}.claims: bounded array expected")
    claims = tuple(_claim_from_dict(item, f"{path.name}.claims[{index}]")
                   for index, item in enumerate(data["claims"]))
    return data, sources, claims


def _pair(v, name: str) -> tuple:
    try:
        return (float(v[0]), float(v[1]))
    except (TypeError, ValueError, IndexError) as exc:
        raise ValueError(f"{name}: Paar erwartet") from exc


def _entry_values(source):
    return source if isinstance(source, list) else _read_entries(source)


def _acoustic_from_dict(d: dict, key: str, category_default: str,
                        label_default: str = "") -> TargetSignature:
    return TargetSignature(
        key=key, label=d.get("label", label_default or key),
        propulsion=d.get("propulsion", ""),
        blade_counts=tuple(int(b) for b in d.get("blades", ())),
        rpm_range=_pair(d.get("rpm_range", (0, 0)), "acoustic.rpm_range"),
        tonal_band_hz=_pair(d.get("tonal_band_hz", (0, 0)),
                            "acoustic.tonal_band_hz"),
        cavitation_tendency=float(d.get("cavitation_tendency", 0.0)),
        category=d.get("category", category_default),
        secondary_tonals=tuple(
            (float(t[0]), float(t[1]), float(t[2]))
            for t in d.get("secondary_tonals", ())),
        broadband=tuple(d["broadband"]) if d.get("broadband") else None,
        signature_text=d.get("signature_text", ""))


def _load_subs(path: str) -> dict:
    out = {}
    for e in _entry_values(path):
        key = str(e["key"])
        acoustic = _acoustic_from_dict(e.get("acoustic", {}), key,
                                       "U_BOOT", e.get("name", key))
        out[key] = SubProfile(
            key=key, name=e.get("name", key),
            speed_kn=_pair(e.get("speed_kn", (6.0, 12.0)), "speed_kn"),
            max_depth_m=float(e.get("max_depth_m", 200.0)),
            torpedoes=int(e.get("torpedoes", 4)),
            quiet=float(e.get("quiet", 0.8)),
            aggression=float(e.get("aggression", 0.6)),
            spawn_weight=float(e.get("spawn_weight", 1.0)),
            acoustic=acoustic)
    return out


def _load_surfaces(path: str) -> dict:
    out = {}
    for e in _entry_values(path):
        key = str(e["key"])
        cat = e.get("category", "KAMPFSCHIFF")
        out[key] = SurfaceProfile(
            key=key, name=e.get("name", key), category=cat,
            speed_kn=_pair(e.get("speed_kn", (14.0, 24.0)), "speed_kn"),
            callsigns=tuple(e.get("callsigns", ())),
            esm_prob=float(e.get("esm_prob", 0.6)),
            asm_salvo=tuple(e.get("asm_salvo", (0, 0))),
            asm_cooldown_s=float(e.get("asm_cooldown_s", 240.0)),
            loiter_nm=float(e.get("loiter_nm", 0.0)),
            spawn_weight=float(e.get("spawn_weight", 1.0)),
            acoustic=_acoustic_from_dict(e.get("acoustic", {}), key, cat,
                                         e.get("name", key)))
    return out


def _load_aircraft(path: str) -> dict:
    out = {}
    for e in _entry_values(path):
        key = str(e["key"])
        out[key] = AircraftProfile(
            key=key, name=e.get("name", key),
            nation=e.get("nation", "ZIVIL"),
            kind=e.get("kind", "civil"),
            speed_kn=float(e.get(
                "speed_kn", 450.0 if e.get("kind") == "civil" else 200.0)),
            esm=bool(e.get("esm", False)),
            esm_range_nm=float(e.get("esm_range_nm", 0.0)),
            loiter_nm=_pair(e.get("loiter_nm", (0, 0)), "loiter_nm"),
            spawn_weight=float(e.get("spawn_weight", 1.0)),
            signature_text=e.get("signature_text", ""))
    return out


def _load_animals(path: str) -> dict:
    out = {}
    for e in _entry_values(path):
        key = str(e["key"])
        out[key] = AnimalProfile(
            key=key, name=e.get("name", key),
            depth_min=float(e.get("depth_min", 10.0)),
            depth_max=float(e.get("depth_max", 50.0)),
            speed_kn=float(e.get("speed_kn", 2.0)),
            quiet=float(e.get("quiet", 0.5)),
            size_nm=float(e.get("size_nm", 0.3)),
            spawn_weight=float(e.get("spawn_weight", 1.0)),
            lines=tuple((float(t[0]), float(t[1]), float(t[2]))
                        for t in e.get("lines", ())),
            signature_text=e.get("signature_text", ""))
    return out


def _load_torpedoes(path: str) -> dict:
    out = {}
    for e in _entry_values(path):
        key = str(e["key"])
        acoustic = None
        if e.get("acoustic"):
            acoustic = _acoustic_from_dict(e["acoustic"], key, "FAHRZEUG",
                                           e.get("name", key))
        out[key] = TorpedoProfile(
            key=key, name=e.get("name", key),
            used_by=e.get("used_by", "enemy"),
            speed_kn=float(e.get("speed_kn", 28.0)),
            range_nm=float(e.get("range_nm", 30.0)),
            hit_dist_nm=float(e.get("hit_dist_nm", 0.25)),
            acoustic=acoustic)
    return out


def _load_decoys(path: str) -> dict:
    out = {}
    for e in _entry_values(path):
        key = str(e["key"])
        out[key] = DecoyProfile(
            key=key, name=e.get("name", key),
            life_s=float(e.get("life_s", 45.0)),
            speed_kn=float(e.get("speed_kn", 8.0)),
            cooldown_s=float(e.get("cooldown_s", 60.0)),
            chance=float(e.get("chance", 0.5)),
            lines=tuple((float(t[0]), float(t[1]), float(t[2]))
                        for t in e.get("lines", ())),
            signature_text=e.get("signature_text", ""))
    return out


def _load_library_signatures(path) -> tuple:
    return tuple(
        _acoustic_from_dict(entry, str(entry["key"]),
                            entry.get("category", "FAHRZEUG"))
        for entry in _entry_values(path)
    )


def _validate(cat: ContactCatalog) -> None:
    n_platforms = sum(1 for s in cat.acoustic_profiles
                      if s.category != "BIOLOGISCH")
    if n_platforms < 100:
        raise ValueError(f"zu wenige Plattformprofile ({n_platforms} < 100)")
    for key in ("diesel_alt", "aip_modern", "ssn"):
        if key not in cat.subs:
            raise ValueError(f"U-Boot-Prototyp '{key}' fehlt")
    if "enemy_torp" not in cat.torpedoes:
        raise ValueError("Torpedo-Profil 'enemy_torp' fehlt")
    if "decoy" not in cat.decoys:
        raise ValueError("Dekoy-Profil 'decoy' fehlt")
    cats = {p.category for p in cat.civilian_surfaces}
    if not set(CIVIL_CATEGORIES).issubset(cats):
        raise ValueError("zivile Kategorien unvollständig")
    if not cat.aircraft or not cat.animals:
        raise ValueError("Flugzeuge/Tiere fehlen")
    for s in cat.acoustic_profiles:
        if not (0.0 <= s.cavitation_tendency <= 1.0):
            raise ValueError(f"cavitation ausserhalb 0..1: {s.key}")
        # (0, 0) = "kein Band" (z.B. biologische Quellen, Torpedos)
        if s.tonal_band_hz[0] > 0.0 and s.tonal_band_hz[0] >= s.tonal_band_hz[1]:
            raise ValueError(f"tonal_band inversed: {s.key}")
        if s.rpm_range[0] > 0.0 and s.rpm_range[0] >= s.rpm_range[1]:
            raise ValueError(f"rpm_range inversed: {s.key}")
        if s.broadband and s.broadband[1] >= s.broadband[2]:
            raise ValueError(f"broadband-Band inversed: {s.key}")


def _collect_v2(documents, profile_keys_by_resource, runtime_weapon_keys, decoy_keys):
    factories = dict(V2_REGISTRIES)
    registries = {field: {} for field, _ in V2_REGISTRIES if field != "profiles"}
    systems = {}
    profile_resources = {}
    component_keys = set()
    for filename in CONTACT_FILENAMES:
        document = documents[filename]
        if document["version"] != 2:
            continue
        for field, _ in V2_REGISTRIES:
            for index, raw in enumerate(document.get(field, [])):
                parsed = factories[field](raw, f"{filename}.{field}[{index}]")
                key = parsed.profile_key if field == "profiles" else parsed.key
                if field == "profiles":
                    if key not in profile_keys_by_resource[filename]:
                        raise ValueError(f"{filename}.profiles: unknown profile key {key!r}")
                    if key in systems:
                        raise ValueError(f"duplicate v2 profile systems key {key!r}")
                    systems[key] = parsed
                    profile_resources[key] = filename
                else:
                    if key in component_keys:
                        raise ValueError(f"duplicate v2 component key {key!r}")
                    component_keys.add(key)
                    registries[field][key] = parsed

        if filename == "acoustics.json" and any(
                document.get(field, []) for field, _ in V2_REGISTRIES):
            raise ValueError("acoustics.json: library signatures cannot attach platform components")

    references = registries["references"]
    machines = registries["machines"]
    sensors = registries["sensors"]
    emitters = registries["emitters"]
    weapons = registries["weapons"]
    launchers = registries["launchers"]
    magazines = registries["magazines"]
    countermeasures = registries["countermeasures"]
    endurances = registries["endurances"]
    referenced = {field: set() for field in registries}

    for sensor in sensors.values():
        if sensor.emitter_key is not None:
            emitter = emitters.get(sensor.emitter_key)
            if emitter is None or emitter.domain != sensor.domain:
                raise ValueError(f"sensor {sensor.key!r}: unresolved or mismatched emitter")
    for weapon in weapons.values():
        if (weapon.runtime_profile_key is not None
                and weapon.runtime_profile_key not in runtime_weapon_keys):
            raise ValueError(f"weapon {weapon.key!r}: unknown runtime profile key")
        if weapon.runtime_profile_key is not None and weapon.weapon_type != "torpedo":
            raise ValueError(f"weapon {weapon.key!r}: only torpedoes use legacy runtime profiles")
    launcher_compatibility = {
        "torpedo_tube": {"torpedo"},
        "vls": {"asm", "asroc", "sam"},
        "rail": {"asm", "asroc", "sam"},
        "ciws": {"ciws"},
    }
    for launcher in launchers.values():
        missing = set(launcher.weapon_keys) - weapons.keys()
        if missing:
            raise ValueError(f"launcher {launcher.key!r}: unknown weapon keys {sorted(missing)}")
        if any(weapons[key].weapon_type not in launcher_compatibility[launcher.launcher_type]
               for key in launcher.weapon_keys):
            raise ValueError(f"launcher {launcher.key!r}: incompatible weapon type")
        referenced["weapons"].update(launcher.weapon_keys)
    for magazine in magazines.values():
        if magazine.weapon_key not in weapons:
            raise ValueError(f"magazine {magazine.key!r}: unknown weapon key")
        referenced["weapons"].add(magazine.weapon_key)
    for countermeasure in countermeasures.values():
        if countermeasure.payload_key is not None and countermeasure.payload_key not in decoy_keys:
            raise ValueError(f"countermeasure {countermeasure.key!r}: unknown payload key")

    for profile_key, profile in systems.items():
        resource = profile_resources[profile_key]
        if resource in ("animals.json", "torpedoes.json", "decoys.json") and any((
                profile.sensor_keys, profile.emitter_keys, profile.launcher_keys,
                profile.magazine_keys, profile.countermeasure_keys)):
            raise ValueError(f"profile {profile_key!r}: {resource} permits reference and machine only")
        scalar_links = (("references", profile.reference_key), ("machines", profile.machine_key))
        list_links = (
            ("sensors", profile.sensor_keys), ("emitters", profile.emitter_keys),
            ("launchers", profile.launcher_keys), ("magazines", profile.magazine_keys),
            ("countermeasures", profile.countermeasure_keys),
        )
        if not any(value is not None for _, value in scalar_links) and not any(
                values for _, values in list_links):
            raise ValueError(f"profile {profile_key!r}: empty v2 systems attachment")
        for field, key in scalar_links:
            if key is not None:
                if key not in registries[field]:
                    raise ValueError(f"profile {profile_key!r}: unknown {field} key {key!r}")
                referenced[field].add(key)
        for field, keys in list_links:
            missing = set(keys) - registries[field].keys()
            if missing:
                raise ValueError(f"profile {profile_key!r}: unknown {field} keys {sorted(missing)}")
            referenced[field].update(keys)
        sensor_emitters = {
            sensors[key].emitter_key for key in profile.sensor_keys
            if sensors[key].emitter_key is not None
        }
        if not sensor_emitters.issubset(profile.emitter_keys):
            raise ValueError(f"profile {profile_key!r}: sensor emitter not attached to platform")
        compatible = {
            weapon for key in profile.launcher_keys for weapon in launchers[key].weapon_keys
        }
        if any(magazines[key].weapon_key not in compatible for key in profile.magazine_keys):
            raise ValueError(f"profile {profile_key!r}: magazine weapon has no compatible launcher")

    sub_entries = {entry["key"]: entry for entry in documents["subs.json"]["entries"]}
    if documents["subs.json"]["version"] == 2:
        for profile_key, entry in sub_entries.items():
            endurance_key = f"endurance.{profile_key}"
            has_endurance = endurance_key in endurances
            nuclear = entry["acoustic"]["propulsion"] == "elektrisch/Kernantrieb"
            if nuclear == has_endurance:
                requirement = "must not have" if nuclear else "requires"
                raise ValueError(f"submarine profile {profile_key!r} {requirement} endurance")
    if any(key.removeprefix("endurance.") not in sub_entries for key in endurances):
        raise ValueError("endurance component attached outside submarine catalog")
    referenced["endurances"].update(endurances)

    for field, values in registries.items():
        orphaned = values.keys() - referenced[field]
        if orphaned:
            raise ValueError(f"unreferenced v2 {field}: {sorted(orphaned)}")
    return registries, systems, profile_resources


def _claim_value(claim, systems, registries):
    profile = systems.get(claim.profile_key)
    if profile is None:
        raise ValueError(f"sources.json: claim for non-v2 profile {claim.profile_key!r}")
    values = []
    singular = {"reference": ("references", profile.reference_key),
                "machine": ("machines", profile.machine_key)}
    weapon_keys = tuple(dict.fromkeys(
        [weapon for key in profile.launcher_keys
         for weapon in registries["launchers"][key].weapon_keys]
        + [registries["magazines"][key].weapon_key for key in profile.magazine_keys]))
    plural = {"sensors": ("sensors", profile.sensor_keys),
              "emitters": ("emitters", profile.emitter_keys),
              "weapons": ("weapons", weapon_keys),
              "launchers": ("launchers", profile.launcher_keys),
              "magazines": ("magazines", profile.magazine_keys),
              "countermeasures": ("countermeasures", profile.countermeasure_keys),
              "endurances": ("endurances", (
                  f"endurance.{profile.profile_key}",)
                  if f"endurance.{profile.profile_key}" in registries["endurances"] else ())}
    for field_path in claim.field_paths:
        parts = field_path[1:].split("/")
        if parts[0] in singular and len(parts) == 2:
            registry_name, key = singular[parts[0]]
            if key is None:
                raise ValueError(f"sources.json: field path {field_path!r} has no component")
            component, field = registries[registry_name][key], parts[1]
        elif parts[0] in plural and len(parts) == 3:
            registry_name, keys = plural[parts[0]]
            key, field = parts[1], parts[2]
            if key not in keys:
                raise ValueError(f"sources.json: field path {field_path!r} is not attached")
            component = registries[registry_name][key]
        else:
            raise ValueError(f"sources.json: invalid field path {field_path!r}")
        if field == "key" or field not in component.__dataclass_fields__:
            raise ValueError(f"sources.json: invalid field path {field_path!r}")
        values.append((field_path, getattr(component, field)))
    return values


def _validate_provenance(sources, claims, systems, profile_resources, registries,
                         allow_empty=False):
    source_map = {source.id: source for source in sources}
    # Runtime snapshots intentionally exclude provenance prose and URLs while
    # retaining the complete component graph they already validated on import.
    if allow_empty and not sources and not claims:
        return source_map
    coordinates = set()
    for claim in claims:
        if profile_resources.get(claim.profile_key) != claim.resource:
            raise ValueError(f"sources.json: claim resource/profile mismatch for {claim.profile_key!r}")
        resolved = []
        for source_id in claim.source_ids:
            source = source_map.get(source_id)
            if source is None:
                raise ValueError(f"sources.json: unknown source ID {source_id!r}")
            resolved.append(source)
        if claim.status in ("published", "derived"):
            if not resolved or any(source.kind == "game_assumption" for source in resolved):
                raise ValueError("sources.json: published/derived claims require public sources")
        elif claim.status == "game_assumption":
            if len(resolved) != 1 or resolved[0].kind != "game_assumption":
                raise ValueError("sources.json: game assumptions require one game-assumption source")
        elif resolved:
            raise ValueError("sources.json: unknown claims cannot cite sources")
        for field_path, value in _claim_value(claim, systems, registries):
            coordinate = (claim.resource, claim.profile_key, field_path)
            if coordinate in coordinates:
                raise ValueError(f"sources.json: duplicate claim coordinate {coordinate!r}")
            coordinates.add(coordinate)
            if claim.status == "unknown" and value is not None:
                raise ValueError(f"sources.json: unknown claim {field_path!r} must reference null")
            if claim.status != "unknown" and value is None:
                raise ValueError(f"sources.json: sourced claim {field_path!r} cannot reference null")
    expected = set()
    for profile_key, profile in systems.items():
        resource = profile_resources[profile_key]
        for name, key, registry_name in (
                ("reference", profile.reference_key, "references"),
                ("machine", profile.machine_key, "machines")):
            if key is not None:
                component = registries[registry_name][key]
                expected.update((resource, profile_key, f"/{name}/{field}")
                                for field in component.__dataclass_fields__
                                if field != "key")
        plural = (
            ("endurances", ((f"endurance.{profile_key}",)
                            if f"endurance.{profile_key}" in registries["endurances"] else ())),
            ("sensors", profile.sensor_keys),
            ("emitters", profile.emitter_keys),
            ("launchers", profile.launcher_keys),
            ("magazines", profile.magazine_keys),
            ("countermeasures", profile.countermeasure_keys),
        )
        for registry_name, keys in plural:
            for key in keys:
                component = registries[registry_name][key]
                expected.update((resource, profile_key,
                                 f"/{registry_name}/{key}/{field}")
                                for field in component.__dataclass_fields__
                                if field != "key")
        weapon_keys = {
            weapon_key for launcher_key in profile.launcher_keys
            for weapon_key in registries["launchers"][launcher_key].weapon_keys
        } | {
            registries["magazines"][key].weapon_key
            for key in profile.magazine_keys
        }
        for key in weapon_keys:
            component = registries["weapons"][key]
            expected.update((resource, profile_key, f"/weapons/{key}/{field}")
                            for field in component.__dataclass_fields__
                            if field != "key")
    if coordinates != expected:
        missing = sorted(expected - coordinates)
        extra = sorted(coordinates - expected)
        raise ValueError(
            "sources.json: incomplete field coverage "
            f"(missing={missing[:8]}, extra={extra[:8]})")
    return source_map


def _catalog_from_documents(documents, db_source, provenance_document=None,
                            sources=(), claims=(), runtime_bindings=None,
                            allow_empty_provenance=False):
    entries = {filename: document["entries"] for filename, document in documents.items()}
    groups = (
        _load_subs(entries["subs.json"]),
        _load_surfaces(entries["warships.json"]),
        _load_surfaces(entries["civilians.json"]),
        _load_aircraft(entries["aircraft.json"]),
        _load_animals(entries["animals.json"]),
        _load_torpedoes(entries["torpedoes.json"]),
        _load_decoys(entries["decoys.json"]),
    )
    seen = set()
    for group in groups:
        duplicates = seen.intersection(group)
        if duplicates:
            raise ValueError(f"duplicate profile ID: {sorted(duplicates)}")
        seen.update(group)
    library = _load_library_signatures(entries["acoustics.json"])
    if {signature.key for signature in library} != {"animal", *groups[6]}:
        raise ValueError("acoustics.json: must define animal and every decoy library signature")
    # Decoy library aliases are intentional; no library entry may shadow a platform.
    if any(signature.key in group for signature in library for group in groups[:6]):
        raise ValueError("acoustics.json: duplicate platform/library key")
    profile_keys_by_resource = {
        filename: {entry["key"] for entry in document["entries"]}
        for filename, document in documents.items()
    }
    registries, systems, profile_resources = _collect_v2(
        documents, profile_keys_by_resource, set(groups[5]), set(groups[6]))
    source_map = _validate_provenance(
        sources, claims, systems, profile_resources, registries,
        allow_empty=allow_empty_provenance)
    cat = ContactCatalog(
        groups[0], groups[1] | groups[2], *groups[3:],
        db_source=db_source,
        library_signatures=library,
        document_versions={name: document["version"] for name, document in documents.items()},
        documents=documents, references=registries["references"].items(),
        machines=registries["machines"].items(), sensors=registries["sensors"].items(),
        endurances=registries["endurances"].items(),
        emitters=registries["emitters"].items(), weapons=registries["weapons"].items(),
        launchers=registries["launchers"].items(),
        magazines=registries["magazines"].items(),
        countermeasures=registries["countermeasures"].items(),
        profile_systems=systems.items(), profile_resources=profile_resources,
        sources=source_map.items(), provenance_claims=claims,
        provenance_document=provenance_document,
        runtime_bindings=runtime_bindings)
    _validate(cat)
    return cat


def catalog_from_runtime_snapshot(snapshot) -> ContactCatalog:
    """Validate an untrusted save snapshot and reconstruct its runtime catalog."""
    if not isinstance(snapshot, dict) or type(snapshot.get("version")) is not int:
        raise ValueError("catalog_snapshot.version: unsupported schema version")
    version = snapshot["version"]
    _schema_object(snapshot, {"version", "entries", "bindings", "components"},
                   "catalog_snapshot")
    if version != RUNTIME_SNAPSHOT_VERSION:
        raise ValueError("catalog_snapshot.version: unsupported schema version")
    entries = snapshot["entries"]
    _schema_object(entries, set(CONTACT_FILENAMES), "catalog_snapshot.entries")
    documents = {}
    total = 0
    for filename in CONTACT_FILENAMES:
        values = entries[filename]
        if not isinstance(values, list) or not values \
                or len(values) > MAX_CATALOG_ENTRIES:
            raise ValueError(f"catalog_snapshot.entries.{filename}: bounded non-empty array expected")
        seen = set()
        for index, entry in enumerate(values):
            where = f"catalog_snapshot.entries.{filename}[{index}]"
            validate_contact_entry(filename, entry, where)
            _schema_key(entry["key"], f"{where}.key")
            if entry["key"] in seen:
                raise ValueError(f"{where}: duplicate key {entry['key']!r}")
            seen.add(entry["key"])
        total += len(values)
    if total > MAX_CATALOG_ENTRIES:
        raise ValueError("catalog_snapshot.entries: too many entries")
    try:
        encoded = json.dumps(snapshot, allow_nan=False, separators=(",", ":"))
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError("catalog_snapshot: invalid JSON values") from exc
    if len(encoded.encode("utf-8")) > MAX_CATALOG_DOCUMENT_BYTES:
        raise ValueError("catalog_snapshot: document too large")
    bindings = snapshot["bindings"]
    _schema_object(bindings, set(RUNTIME_BINDINGS), "catalog_snapshot.bindings")
    for name, key in bindings.items():
        _schema_key(key, f"catalog_snapshot.bindings.{name}")
    components = snapshot["components"]
    _schema_object(components, set(CONTACT_FILENAMES), "catalog_snapshot.components")
    component_fields = {"version", *(field for field, _ in V2_REGISTRIES)}
    for filename in CONTACT_FILENAMES:
        component = components[filename]
        _schema_object(component, component_fields,
                       f"catalog_snapshot.components.{filename}")
        document_version = component["version"]
        if type(document_version) is not int or document_version not in (1, 2):
            raise ValueError("catalog_snapshot.components: invalid document version")
        if document_version == 1 and any(component[field]
                                          for field, _ in V2_REGISTRIES):
            raise ValueError("catalog_snapshot.components: v1 component data")
        for field, factory in V2_REGISTRIES:
            _schema_object_array(
                component[field], f"catalog_snapshot.components.{filename}.{field}",
                factory)
        documents[filename] = {
            "version": document_version,
            "entries": copy.deepcopy(entries[filename]),
            **{field: copy.deepcopy(component[field]) for field, _ in V2_REGISTRIES},
        }
    cat = _catalog_from_documents(
        documents, "save-snapshot", runtime_bindings=bindings,
        allow_empty_provenance=True)
    expected_torpedoes = {
        "frigate_torpedo": "frigate", "helicopter_torpedo": "helo",
        "enemy_torpedo": "enemy",
    }
    if any(cat.torpedoes.get(bindings[name]) is None
           or cat.torpedoes[bindings[name]].used_by != owner
           for name, owner in expected_torpedoes.items()):
        raise ValueError("catalog_snapshot.bindings: invalid torpedo binding")
    if bindings["submarine_decoy"] not in cat.decoys:
        raise ValueError("catalog_snapshot.bindings: invalid decoy binding")
    if any(cat.aircraft.get(bindings[name]) is None
           or cat.aircraft[bindings[name]].kind != kind
           for name, kind in (("civil_flight", "civil"),
                              ("military_flight", "military"))):
        raise ValueError("catalog_snapshot.bindings: invalid aircraft binding")
    return cat


def _load_catalog_from(base_dir) -> ContactCatalog:
    documents = {
        filename: _read_document(base_dir / filename)
        for filename in CONTACT_FILENAMES
    }
    provenance_path = base_dir / SOURCES_FILENAME
    provenance_document = None
    sources = ()
    claims = ()
    if provenance_path.is_file():
        provenance_document, sources, claims = _read_provenance(provenance_path)
    elif any(document["version"] == 2 for document in documents.values()):
        raise ValueError("sources.json: required when version 2 documents are present")
    return _catalog_from_documents(
        documents, base_dir.name or "data/contacts", provenance_document,
        sources, claims)


def load_catalog(base_dir: str = None, quiet: bool = False) -> ContactCatalog:
    """Lädt einen Katalog; fehlerhafte externe Daten fallen auf Paketdaten zurück."""
    if base_dir is None:
        return build_catalog()
    source = os.fspath(base_dir)
    try:
        from pathlib import Path
        return _load_catalog_from(Path(source))
    except Exception as exc:  # noqa: BLE001 - external data may be user-edited
        if not quiet:
            import sys
            print(f"[kontakt-db] {source}: {exc} - "
                  f"verwende paketierten Katalog", file=sys.stderr)
        return build_catalog()


def rank_signatures(blade_rate_hz: float | None, rpm: float | None,
                    tonal_hz: float | None, cavitation: float, signatures=None
                    ) -> list[tuple[TargetSignature, float]]:
    """Transparente 0..1-Ähnlichkeitswerte fuer die Operator-Analyse.

    Bewertet gegen alle Plattformprofile des aktiven Katalogs
    (ohne BIOLOGISCH-Fangnetz-Profile? Nein: alle Eintraege, wie zuvor).
    """
    signatures = CATALOG.acoustic_profiles if signatures is None else signatures
    if blade_rate_hz is None:
        return [(signature, 0.0) for signature in signatures]
    result = []
    for signature in signatures:
        score = 0.0
        rpm_options = ([rpm] if rpm is not None else
                       [blade_rate_hz * 60.0 / blades
                        for blades in signature.blade_counts])
        if signature.blade_counts and any(
                signature.rpm_range[0] <= value <= signature.rpm_range[1]
                for value in rpm_options):
            score += 0.45
        if tonal_hz is not None and (
                signature.tonal_band_hz[0] <= tonal_hz <= signature.tonal_band_hz[1]):
            score += 0.30
        if signature.blade_counts and rpm is not None:
            estimated_blades = round(blade_rate_hz * 60.0 / rpm)
            if estimated_blades in signature.blade_counts:
                score += 0.10
        score += max(0.0, 0.15 - abs(cavitation - signature.cavitation_tendency) * 0.15)
        result.append((signature, round(min(1.0, score), 3)))
    return sorted(result, key=lambda item: item[1], reverse=True)


CATALOG = load_catalog()
