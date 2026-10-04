"""Kontakt-Katalog: alle Plattformprofile (Akustik + Verhalten) an einer Stelle.

Die eingebauten Profile werden aus den paketierten ``data.contacts``-JSON-
Ressourcen geladen. Der Katalog enthält:

- 23 U-Boot-Profile (3 Legacy-Archetypen + 20 benannte Klassen); der zufällige
  Spawn-Pool (``spawn_weight``) ist auf die russischen Klassen konzentriert
- 5 Kampfschiff-Profile in ``warships.json`` (KAMPFSCHIFF); der tatsächliche
  Zufalls-Feind-Pool (``LEGACY_HOSTILE_SURFACE_KEYS``) ist auf die russischen
  Klassen + Projekt 20380 begrenzt; die neue F217 *Bayern* ist dort ebenfalls
  gelistet, aber ``default_faction: "FREUND"`` und nicht im Zufalls-Pool
- 80 zivile Schiffe (Tanker/Passagier/Fracht/Sonstiges), davon 25 real-benannte
  Marinen, die zu neutralem Drittparteien-Verkehr umklassifiziert wurden
- Flugzeugprofile (sonar-invisible, nur Radar/ESM)
- 3 Meerestier-Typen, 3 Torpedo-Profile, 1 Dekoy-Profil

Siehe "Russland-Feindgrundlage" weiter unten für den Hintergrund dieser
Umklassifizierung und die neuen optionalen Felder (``wiki_url``,
``default_faction``, ``rcs_m2``, akustische LOFAR-Zusatzfelder).

Kontakte sind nie an ein einzelnes Profil gebunden: pro Instanz wird aus
Blätterzahl, Takt-Skala und Linien-Offsets ein Fingerprint gerollt
(src/data/fingerprint.py), damit zwei gleiche Klassen unterschiedlich klingen.
"""

import copy
import ipaddress
import json
import os
import re
from datetime import date
from importlib import resources
from types import MappingProxyType
from urllib.parse import urlsplit

# Verbatim moves: the types, schema and v2 systems live in their own
# modules; the names imported through this facade are listed in __all__.
from src.data.catalog_types import (CIVIL_CATEGORIES,
                                    LEGACY_HOSTILE_SURFACE_KEYS,
                                    TargetSignature, SubProfile,
                                    SurfaceProfile, AircraftProfile,
                                    AnimalProfile, TorpedoProfile,
                                    DecoyProfile, EnduranceProfile,
                                    EmitterProfile, CatalogSource,
                                    ProvenanceClaim)
from src.data.catalog_schema import (CONTACT_FIELDS, ACOUSTIC_FIELDS,
                                     ENTRY_OPTIONAL_FIELDS,
                                     ACOUSTIC_OPTIONAL_FIELDS,
                                     CONTACT_FILENAMES, SOURCES_FILENAME,
                                     V2_DOCUMENT_FIELDS,
                                     V2_OPTIONAL_DOCUMENT_FIELDS,
                                     LEGACY_EMITTER_FIELDS, SOURCE_FIELDS,
                                     CLAIM_FIELDS, OWN_ASSET_EMITTER_PREFIX,
                                     MAX_CATALOG_DOCUMENT_BYTES,
                                     MAX_CATALOG_ENTRIES,
                                     RUNTIME_SNAPSHOT_VERSION,
                                     RUNTIME_BINDINGS, _schema_object,
                                     _schema_text, validate_contact_entry)
from src.data.catalog_systems import (_schema_key, _schema_nullable_text,
                                      _schema_string_array, _schema_key_array,
                                      _endurance_from_dict, _v2_to_dict,
                                      _source_to_dict, _claim_to_dict,
                                      _read_json, _schema_object_array,
                                      V2_REGISTRIES)

# The names other modules, tests and tools import through this facade
# (the other imports above serve this module itself).
__all__ = [
    "ACOUSTIC_FIELDS",
    "ACOUSTIC_OPTIONAL_FIELDS",
    "CATALOG",
    "CIVIL_CATEGORIES",
    "CONTACTS_DIR",
    "CONTACT_FIELDS",
    "CONTACT_FILENAMES",
    "ContactCatalog",
    "ENTRY_OPTIONAL_FIELDS",
    "EmitterProfile",
    "EnduranceProfile",
    "MAX_CATALOG_DOCUMENT_BYTES",
    "MAX_CATALOG_ENTRIES",
    "OWN_ASSET_EMITTER_PREFIX",
    "RUNTIME_BINDINGS",
    "SOURCES_FILENAME",
    "TargetSignature",
    "V2_REGISTRIES",
    "build_catalog",
    "catalog_from_runtime_snapshot",
    "load_catalog",
    "rank_signatures",
    "validate_contact_entry",
    "_endurance_from_dict",
    "_load_catalog_from",
    "_read_document",
    "_read_json",
    "_v2_to_dict",
]

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CONTACTS_DIR = os.path.join(_ROOT, "data", "contacts")


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
        emitter_names = {}
        for profile_key, resource in self.profile_resources.items():
            name = None
            for entry in self._document_entries.get(resource, ()):
                if entry.get("key") == profile_key:
                    name = entry.get("name")
                    break
            if not name:
                continue
            systems = self.profile_systems.get(profile_key)
            if systems is None:
                continue
            for emitter_key in systems.emitter_keys:
                emitter_names[emitter_key] = name
        self.emitter_names = MappingProxyType(emitter_names)

    def emitter_name(self, emitter_key: str) -> str | None:
        """Display name of the platform owning an emitter, or None."""
        if not isinstance(emitter_key, str):
            return None
        return self.emitter_names.get(emitter_key)

    # --- Auswahl-Hilfen (deterministisch über übergebene rng) ---

    def pick_surface(self, rng, hostile: bool = False):
        pool = (self.legacy_hostile_surfaces if hostile
                else self.civilian_surfaces)
        return _weighted_pick(rng, pool)

    def pick_civilian_by_category(self, rng, category: str):
        """Ziviles Profil einer Kategorie (TANKER/FRACHT/PASSAGIER/...);
        faellt auf ein beliebiges ziviles Profil zurueck, falls keines der
        Kategorie existiert (z. B. fuer aus AIS-Daten abgeleitete Kontakte)."""
        pool = tuple(p for p in self.civilian_surfaces if p.category == category)
        return _weighted_pick(rng, pool or self.civilian_surfaces)

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
        signature_text=d.get("signature_text", ""),
        lofar_base_freq_hz=tuple(float(f) for f in d.get("lofar_base_freq_hz", ())),
        cavitation_speed_knots=(float(d["cavitation_speed_knots"])
                                if d.get("cavitation_speed_knots") is not None else None),
        audio_sample_id=d.get("audio_sample_id", ""))


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
            acoustic=acoustic,
            wiki_url=e.get("wiki_url"),
            default_faction=e.get("default_faction"),
            rcs_m2=(float(e["rcs_m2"]) if e.get("rcs_m2") is not None else None))
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
                                         e.get("name", key)),
            wiki_url=e.get("wiki_url"),
            default_faction=e.get("default_faction"),
            rcs_m2=(float(e["rcs_m2"]) if e.get("rcs_m2") is not None else None))
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
            signature_text=e.get("signature_text", ""),
            wiki_url=e.get("wiki_url"),
            default_faction=e.get("default_faction"),
            rcs_m2=(float(e["rcs_m2"]) if e.get("rcs_m2") is not None else None))
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
        if len(profile.emitter_keys) > 4:
            raise ValueError(f"profile {profile_key!r}: radar suite exceeds four emitters")
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
    # Missile seekers are a weapon library: they radiate from an inbound
    # round, never from a platform suite, so no profile references them.
    for emitter in emitters.values():
        if emitter.radar_role == "missile_seeker":
            if emitter.key in referenced["emitters"]:
                raise ValueError(f"emitter {emitter.key!r}: missile seeker attached to a platform")
            referenced["emitters"].add(emitter.key)
        elif emitter.key.startswith(OWN_ASSET_EMITTER_PREFIX):
            if emitter.key in referenced["emitters"]:
                raise ValueError(f"emitter {emitter.key!r}: own-asset radar attached to a platform")
            referenced["emitters"].add(emitter.key)

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


def _normalize_legacy_emitters(values):
    """Recognize the one pre-emissions same-v10 component shape exactly."""
    if (not values or not all(isinstance(row, dict)
                              and set(row) == LEGACY_EMITTER_FIELDS
                              for row in values)):
        return values
    normalized = []
    for original in values:
        row = copy.deepcopy(original)
        key = row["key"]
        aircraft = "mil_patrol" in key or "su_25" in key
        role = ("air_search" if aircraft else
                "multi_function" if ".warship_" in key else "navigation")
        row.update(
            radar_role=role,
            operating_mode=("mission_search" if aircraft else
                            "combined_search" if role == "multi_function"
                            else "navigation"),
            power_class=("medium" if aircraft else
                         "high" if role == "multi_function" else "low"),
            operating_period_s=10.0, on_duration_s=10.0)
        normalized.append(row)
    return normalized


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
            values = (_normalize_legacy_emitters(component[field])
                      if field == "emitters" else component[field])
            _schema_object_array(
                values, f"catalog_snapshot.components.{filename}.{field}",
                factory)
        documents[filename] = {
            "version": document_version,
            "entries": copy.deepcopy(entries[filename]),
            **{field: copy.deepcopy(
                _normalize_legacy_emitters(component[field])
                if field == "emitters" else component[field])
               for field, _ in V2_REGISTRIES},
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
